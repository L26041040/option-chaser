"""機會搜尋：跨標的搜尋後端（OS-04／#393，母票 #389 §5／§7／§8／§9）。

釘住：

- `POST /api/opportunity/search` 只限 SU／SA（Normal 403）；來源未設定 409
  「尚未設定分析師資料來源」。
- 省略 `symbols` ＝ 共識清單（`GET /api/opportunity/consensus`）的入選集合；
  傳了必須是入選集合的子集（否則 400）。
- 每次呼叫處理一檔（沿用 refresh run 的「一次一組」與 45 秒預算），其餘
  放 `remaining`；續跑不重複、不遺漏。
- **計算等價（硬性，#389 §5.2／C5）**：同一份 chain fixture 下，搜尋結果
  列逐欄等於「手動建立同參數劇本」所得的同家族代表候選——同一個測試
  裡兩條路都走。
- 錯誤隔離（抓鏈失敗、零候選）、Global Vendor Fuse 熔斷停止、fetch_cap
  截斷、看跌方向沿用既有推導。
"""
from __future__ import annotations

import dataclasses
from datetime import timedelta

from fastapi.testclient import TestClient

from api_app.analyst_source import FixtureAnalystSource
from api_app.clock import ny_today
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError
from scripts.gen_contract_sample import _sample_dividend_loader, _sample_rate_loader
from tests._role_session import grant_role

ANALYST_FIXTURE = "tests/fixtures/analyst_targets_fixture.json"
CHAIN_FIXTURE = "tests/fixtures/xyz_v7_butterfly_moderate.json"
FIXTURE_SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
# 測試資料在固定評估日（2026-09-28）下的入選集合（見
# tests/test_api_opportunity_consensus.py 的設計表）：AAA mean 120、EEE mean 110。
SELECTED = ["AAA", "EEE"]
ALL_FAMILIES = ["single-leg", "vertical-spread", "butterfly"]
CRON = {"Authorization": "Bearer test-secret"}
_DEFAULT = {"mode": "default", "provider": None}


def _chain(**changes):
    snap = load_snapshot(CHAIN_FIXTURE)
    return dataclasses.replace(snap, **changes) if changes else snap


def _app(storage=None, *, role="superuser", source="fixture", fetch=None,
         **overrides):
    storage = storage if storage is not None else MemoryStorage()
    if role != "normal":
        grant_role(storage, role, owner_id="solo")
    if source == "fixture":
        source = FixtureAnalystSource(ANALYST_FIXTURE)
    chain = _chain()
    # 利率曲線與配息用固定假資料（同 contracts 樣本）：不連外、結果決定性。
    overrides.setdefault("rate_loader", _sample_rate_loader)
    overrides.setdefault("dividend_loader", _sample_dividend_loader)
    client = TestClient(create_app(
        identity_resolver=lambda: "solo", storage=storage,
        analyst_source=source, cron_secret="test-secret",
        fetch=fetch or (lambda symbol: chain), **overrides))
    return client, storage


def _ready(client, symbols=FIXTURE_SYMBOLS, **extra):
    """母體設成自訂清單、跑一次共識更新——共識清單因此有入選股。"""
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "custom", "custom_symbols": symbols,
                               **extra}})
    assert r.status_code == 200, r.text
    while True:   # 預算調小的測試裡 cron 也是一次一檔，跑到完
        r = client.get("/api/cron/consensus-refresh", headers=CRON)
        assert r.status_code == 200, r.text
        if not r.json()["remaining"]:
            break


def _search(client, body=None, status=200):
    r = client.post("/api/opportunity/search", json=body or {})
    assert r.status_code == status, r.text
    return r.json()


# ---------- 權限與來源 ----------

def test_normal_user_is_refused_with_403():
    client, _ = _app(role="normal")
    r = client.post("/api/opportunity/search", json={})
    assert r.status_code == 403


def test_super_admin_can_search():
    client, _ = _app(role="superadmin")
    _ready(client)
    assert _search(client)["processed"] == ["AAA"]


def test_unconfigured_source_is_409_and_does_not_pretend():
    client, _ = _app(source=None)
    r = client.post("/api/opportunity/search", json={})
    assert r.status_code == 409
    assert "尚未設定分析師資料來源" in r.text


# ---------- 計算等價（硬性，#389 §5.2／C5） ----------

def test_search_rows_equal_the_manually_created_scenario_field_by_field():
    """同一份 chain fixture：(a) 搜尋 AAA；(b) 把結果列的 `scenario` 原封不動
    送進既有 `POST /api/scenarios`、再走既有刷新。每個家族的結果列必須
    逐欄等於該劇本存下的同家族代表候選（與它在候選池裡的完整候選）。"""
    client, storage = _app()
    _ready(client)
    body = _search(client, {"symbols": ["AAA"]})
    assert body["failures"] == [] and body["processed"] == ["AAA"]
    rows = {r["family"]: r for r in body["rows"]}
    assert set(rows) == set(ALL_FAMILIES)   # 這份 chain 三個家族都有候選

    scenario = rows["single-leg"]["scenario"]
    assert scenario == {"symbol": "AAA", "target_price": 120.0,
                        "target_month": "2027-09", "strategies": ALL_FAMILIES}
    assert all(r["scenario"] == scenario for r in rows.values())
    created = client.post("/api/scenarios", json=scenario)
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    refreshed = client.post(f"/api/scenarios/{sid}/refresh")
    assert refreshed.status_code == 200, refreshed.text

    saved = storage.latest_result(sid, owner="solo")
    assert set(saved.per_family) == set(rows)
    for family, rep in saved.per_family.items():
        row = rows[family]
        candidate = saved.view["candidate_pool"][rep["candidate_key"]]
        assert row["symbol"] == "AAA"
        assert row["subtype"] == rep["strategy"]
        assert row["candidate_key"] == rep["candidate_key"]
        assert row["legs"] == rep["legs"]
        assert row["expiry"] == rep["expiry"]
        assert row["target_return"] == rep["baseline_return"]
        assert row["entry_cost"] == candidate["natural_cost"]
        assert row["max_loss_per_contract"] == candidate["max_loss_per_contract"]
        assert row["breakeven"] == candidate["breakeven"]
        assert row["buffer_days"] == candidate["buffer_days"]
        assert row["target_month"] == "2027-09"
    # 劇本清單卡片（既有 API）的冠軍＝搜尋結果裡報酬最高的那一列。
    card = refreshed.json()["representative_candidate"]
    best = max(rows.values(), key=lambda r: r["target_return"])
    assert card["candidate_key"] == best["candidate_key"]
    assert refreshed.json()["best_return"] == best["target_return"]


def test_rows_carry_the_consensus_summary_and_no_banned_field_names():
    client, _ = _app()
    _ready(client)
    body = _search(client, {"symbols": ["AAA"]})
    consensus = client.get("/api/opportunity/consensus").json()
    aaa = next(i for i in consensus["items"] if i["symbol"] == "AAA")
    for row in body["rows"]:
        assert row["consensus"] == {k: aaa[k] for k in (
            "mean", "n_analysts", "dispersion", "percentile", "as_of", "coverage",
            # V2-05（#407）只新增欄位
            "price", "price_date", "price_at", "price_kind",
            "target_upside_pct", "target_upside_reason")}
        assert row["consensus"]["coverage"] == "partial"

    def keys(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from keys(v)
        elif isinstance(x, list):
            for v in x:
                yield from keys(v)
    banned = ("expected", "probability", "win")
    assert not [k for k in keys(body) if any(b in k.lower() for b in banned)]


def test_row_price_is_the_consensus_update_quote_not_the_option_chain_spot():
    """V2-05（#407）：結果列的目前股價是共識更新時存下的報價（fixture AAA：
    100.00，2026-09-25 收盤），不是這次選擇權搜尋帶回的 spot（這裡是 135）。"""
    chain = _chain(spot=135.0)
    client, _ = _app(fetch=lambda s: chain)
    _ready(client)
    body = _search(client, {"symbols": ["AAA"]})
    assert body["rows"]
    for row in body["rows"]:
        c = row["consensus"]
        assert (c["price"], c["price_date"], c["price_kind"]) == (100.0, "2026-09-25", "close")
        assert c["target_upside_pct"] == 20.0 and c["target_upside_reason"] is None


def test_search_writes_no_scenario_or_result():
    client, storage = _app()
    _ready(client)
    _search(client, {"symbols": ["AAA"]})
    assert client.get("/api/scenarios").json() == []


# ---------- 預設集合＝共識入選清單；一次一檔；續跑 ----------

def test_default_symbols_are_the_consensus_selected_list_one_per_call():
    client, _ = _app()
    _ready(client)
    listed = [i["symbol"] for i in client.get("/api/opportunity/consensus").json()["items"]
              if i["gate"]["selected"]]
    assert listed == SELECTED
    first = _search(client)
    assert first["processed"] == ["AAA"] and first["remaining"] == ["EEE"]
    assert first["fetches_used"] == 1
    assert first["truncated"] is False and first["stopped_reason"] is None
    second = _search(client, {"symbols": first["remaining"]})
    assert second["processed"] == ["EEE"] and second["remaining"] == []
    assert {r["symbol"] for r in first["rows"]} == {"AAA"}
    assert {r["symbol"] for r in second["rows"]} == {"EEE"}
    assert second["rows"][0]["scenario"]["target_price"] == 110.0


def test_continuation_under_a_tight_budget_neither_repeats_nor_skips():
    client, _ = _app(refresh_run_group_limit=10, refresh_run_budget=timedelta(seconds=0))
    _ready(client)
    seen: list[str] = []
    body = _search(client)
    calls = 1
    while True:
        assert not set(body["processed"]) & set(seen)
        seen += body["processed"]
        if not body["remaining"]:
            break
        body = _search(client, {"symbols": body["remaining"]})
        calls += 1
    assert seen == SELECTED and calls == len(SELECTED)


def test_group_limit_lets_one_call_cover_every_selected_symbol():
    client, _ = _app(refresh_run_group_limit=10)
    _ready(client)
    body = _search(client)
    assert body["processed"] == SELECTED and body["remaining"] == []
    assert body["fetches_used"] == 2


# ---------- 錯誤隔離 ----------

def test_one_fetch_failure_is_isolated_and_the_next_symbol_still_runs():
    chain = _chain()

    def fetch(symbol):
        if symbol == "AAA":
            raise FetchError("模擬上游失敗")
        return chain

    client, _ = _app(fetch=fetch, refresh_run_group_limit=10)
    _ready(client)
    body = _search(client)
    assert body["processed"] == SELECTED and body["remaining"] == []
    assert [(f["symbol"], f["reason"]) for f in body["failures"]] == [("AAA", "fetch_failed")]
    assert "抓不到 AAA 的報價" in body["failures"][0]["message"]
    assert {r["symbol"] for r in body["rows"]} == {"EEE"}


def test_zero_candidates_is_a_failure_and_other_symbols_are_unaffected():
    with_flies, without_flies = _chain(), load_snapshot(
        "tests/fixtures/xyz_v4_six_expiries.json")   # 只有 call，湊不出蝶式
    client, _ = _app(fetch=lambda s: with_flies if s == "AAA" else without_flies,
                     refresh_run_group_limit=10)
    _ready(client)
    body = _search(client, {"strategies": ["butterfly"]})
    assert [(f["symbol"], f["reason"]) for f in body["failures"]] == [("EEE", "no_candidates")]
    assert [(r["symbol"], r["family"]) for r in body["rows"]] == [("AAA", "butterfly")]
    assert body["strategies"] == ["butterfly"]


def test_zero_candidates_failure_says_why_in_the_engine_s_own_words():
    """LIVE-T4（#400）：真實 chain 才常見的零候選要說清楚卡在哪——基準到期日
    （最接近目標月份、劇本頭條取的那一期）與引擎自己對每個策略的狀態與訊息
    （方向不適用而沒跑的策略不算原因）。**不放寬任何過濾規則**。"""
    with_flies, without_flies = _chain(), load_snapshot(
        "tests/fixtures/xyz_v4_six_expiries.json")
    client, _ = _app(fetch=lambda s: with_flies if s == "AAA" else without_flies,
                     refresh_run_group_limit=10)
    _ready(client)
    failure = _search(client, {"strategies": ["butterfly"]})["failures"][0]
    assert failure["symbol"] == "EEE" and failure["reason"] == "no_candidates"
    assert failure["baseline_expiry"] == "2026-12-18"
    assert failure["other_expiries"] == []
    assert failure["strategies"] == [{
        "strategy": "call-fly", "status": "empty", "n_qualified": 0,
        "message": "目前沒有符合流動性與報價條件的合約。"}]
    assert failure["message"] == (
        "EEE 在基準到期日 2026-12-18（最接近目標月份 2027-09）沒有合格候選；"
        "Call Butterfly：目前沒有符合流動性與報價條件的合約。")


def test_baseline_expiry_without_quotes_is_named_even_when_other_expiries_qualify():
    """真實 chain 的長天期合約常常沒有報價：目標月份附近那一期（基準到期日）
    全被既有過濾剔除時，即使別的到期日有合格候選也照實是零候選（與手動建立
    同參數劇本一致——劇本頭條同樣只取基準到期日），並列出哪些到期日其實
    有候選，讓使用者知道不是整條鏈都不能用。"""
    base = _chain()
    no_quotes_at_baseline = dataclasses.replace(base, contracts=tuple(
        dataclasses.replace(c, bid=None, ask=None) if c.expiry == "2026-12-18" else c
        for c in base.contracts))
    client, _ = _app(fetch=lambda s: no_quotes_at_baseline)
    _ready(client)
    body = _search(client, {"symbols": ["AAA"]})
    assert body["rows"] == []
    failure = body["failures"][0]
    assert failure["reason"] == "no_candidates"
    assert failure["baseline_expiry"] == "2026-12-18"
    assert failure["other_expiries"] == ["2026-09-18", "2026-10-16"]
    assert failure["message"].startswith(
        "AAA 在基準到期日 2026-12-18（最接近目標月份 2027-09）沒有合格候選；"
        "其他到期日有合格候選（2026-09-18、2026-10-16），但劇本頭條只取基準到期日")
    # 與手動建立同參數劇本一致：既有劇本同樣沒有代表候選。
    created = client.post("/api/scenarios", json={
        "symbol": "AAA", "target_price": 120.0, "target_month": "2027-09",
        "strategies": ALL_FAMILIES})
    sid = created.json()["id"]
    refreshed = client.post(f"/api/scenarios/{sid}/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["representative_candidate"] is None


def test_a_family_missing_from_a_successful_symbol_is_explained_not_silently_dropped():
    """有結果的股票，某個選了的家族卻沒有列（真實 chain：長天期流動性差、
    Butterfly 窮舉逾時）→ `incomplete` 照實說是哪個家族、引擎怎麼說；方向
    不適用（引擎本來就不跑）不算。"""
    calls_only = load_snapshot("tests/fixtures/xyz_v4_six_expiries.json")   # 湊不出蝶式
    client, _ = _app(fetch=lambda s: calls_only)
    _ready(client)
    body = _search(client, {"symbols": ["EEE"]})
    assert body["failures"] == []
    assert sorted(r["family"] for r in body["rows"]) == ["single-leg", "vertical-spread"]
    assert body["incomplete"] == [{
        "symbol": "EEE", "families": ["butterfly"],
        "strategies": [{"strategy": "call-fly", "status": "empty", "n_qualified": 0,
                        "message": "目前沒有符合流動性與報價條件的合約。"}],
        "message": "EEE 的 Butterfly 沒有結果：Call Butterfly：目前沒有符合流動性與報價條件的合約。"}]
    # 三個家族都有列的股票不會出現在 incomplete。
    assert _search(client, {"symbols": ["EEE"],
                            "strategies": ["single-leg"]})["incomplete"] == []


# ---------- 成本：Global Vendor Fuse、fetch_cap ----------

def test_global_vendor_fuse_stops_the_search_and_returns_remaining():
    storage = MemoryStorage()
    client, _ = _app(storage, global_vendor_daily_budget=5, refresh_run_group_limit=10)
    _ready(client)
    storage.record_metric("chain_fetch_count", ny_today().isoformat(),
                          source="cboe", symbol="ANY", count=5)
    body = _search(client)
    assert body["stopped_reason"] == "fused"
    assert body["processed"] == [] and body["remaining"] == SELECTED
    assert body["rows"] == [] and body["failures"] == []
    assert body["message"] == ("今日全站報價查詢預算已用完，畫面沿用既有資料，"
                               "請稍後或明天再試")


def test_fuse_tripping_mid_search_keeps_the_finished_part():
    storage = MemoryStorage()
    chain = _chain()

    def fetch(symbol):   # 抓完 AAA 這一次，剛好把今天的全站預算用完
        storage.record_metric("chain_fetch_count", ny_today().isoformat(),
                              source="cboe", symbol=symbol, count=5)
        return chain

    client, _ = _app(storage, fetch=fetch, global_vendor_daily_budget=5,
                     refresh_run_group_limit=10)
    _ready(client)
    body = _search(client)
    assert body["stopped_reason"] == "fused"
    assert body["processed"] == ["AAA"] and body["remaining"] == ["EEE"]
    assert {r["symbol"] for r in body["rows"]} == {"AAA"}


def test_fetch_cap_overflow_is_returned_as_deferred_not_dropped():
    """§8「單次搜尋達 fetch_cap：停止並回傳 remaining；使用者可稍後接續」：
    超出上限的檔放在 `deferred`（不自動續跑——那會繞過上限），使用者
    明確再發一次搜尋才處理。"""
    client, _ = _app(opportunity_fetch_cap=1, refresh_run_group_limit=10)
    _ready(client)
    body = _search(client)
    assert body["fetch_cap"] == 1 and body["truncated"] is True
    assert body["processed"] == ["AAA"] and body["remaining"] == []
    assert body["deferred"] == ["EEE"]
    later = _search(client, {"symbols": body["deferred"]})
    assert later["processed"] == ["EEE"] and later["deferred"] == []
    assert later["truncated"] is False


def test_deferred_symbols_are_capped_again_when_searched():
    client, _ = _app(opportunity_fetch_cap=1, refresh_run_group_limit=10)
    _ready(client)
    body = _search(client, {"symbols": ["EEE", "AAA"]})
    assert body["processed"] == ["EEE"] and body["deferred"] == ["AAA"]


def test_fetch_cap_defaults_to_50():
    client, _ = _app()
    _ready(client)
    body = _search(client)
    assert body["fetch_cap"] == 50 and body["truncated"] is False
    assert body["deferred"] == []


def test_search_response_carries_the_sort_options_from_settings():
    """排序選項（含顯示文字）只有一份來源：`opportunity_settings`，設定頁
    與搜尋頁都讀後端給的。"""
    client, _ = _app()
    _ready(client)
    body = _search(client, {"symbols": ["AAA"]})
    settings = client.get("/api/settings").json()["opportunity_search_options"]
    assert body["sort_options"] == settings["sorts"]
    assert [o["id"] for o in body["sort_options"]] == ["return", "cost", "max_loss"]
    assert all(o["label"] for o in body["sort_options"])


# ---------- 請求驗證 ----------

def test_symbols_outside_the_selected_list_are_400():
    client, _ = _app()
    _ready(client)
    for symbols in (["BBB"], ["AAA", "ZZZ"]):
        r = client.post("/api/opportunity/search", json={"symbols": symbols})
        assert r.status_code == 400, r.text
    assert "BBB" in client.post("/api/opportunity/search",
                                json={"symbols": ["BBB"]}).json()["detail"]


def test_overlong_symbols_list_is_rejected_with_422():
    client, _ = _app()
    _ready(client)
    r = client.post("/api/opportunity/search",
                    json={"symbols": [f"S{i}" for i in range(501)]})
    assert r.status_code == 422, r.text


def test_unknown_family_or_sort_is_422():
    client, _ = _app()
    _ready(client)
    for body in ({"strategies": ["single_leg"]}, {"strategies": []},
                 {"sort": "probability"}, {"cursor": 1}):
        assert client.post("/api/opportunity/search", json=body).status_code == 422


def test_strategies_and_sort_default_to_settings():
    client, _ = _app()
    _ready(client, strategies=["vertical-spread"], sort="cost")
    body = _search(client, {"symbols": ["AAA"]})
    assert body["strategies"] == ["vertical-spread"] and body["sort"] == "cost"
    assert [r["family"] for r in body["rows"]] == ["vertical-spread"]
    assert body["rows"][0]["scenario"]["strategies"] == ["vertical-spread"]


def test_rows_are_sorted_by_the_requested_key():
    client, _ = _app()
    _ready(client)
    by_return = _search(client, {"symbols": ["AAA"]})["rows"]
    returns = [r["target_return"] for r in by_return]
    assert returns == sorted(returns, reverse=True)
    by_cost = _search(client, {"symbols": ["AAA"], "sort": "cost"})["rows"]
    costs = [r["entry_cost"] for r in by_cost]
    assert costs == sorted(costs)
    by_loss = _search(client, {"symbols": ["AAA"], "sort": "max_loss"})["rows"]
    losses = [r["max_loss_per_contract"] for r in by_loss]
    assert losses == sorted(losses)


# ---------- 方向沿用既有推導 ----------

def test_mean_below_spot_yields_bearish_structures():
    bearish_chain = _chain(spot=135.0)   # AAA 平均目標價 120 < 現價 135
    client, _ = _app(fetch=lambda s: bearish_chain)
    _ready(client)
    rows = {r["family"]: r for r in _search(client, {"symbols": ["AAA"]})["rows"]}
    assert {f: r["subtype"] for f, r in rows.items()} == {
        "single-leg": "long-put", "vertical-spread": "bear-put-spread",
        "butterfly": "put-fly"}


# ---------- 契約樣本（前端 mock 與後端共用） ----------

def test_opportunity_search_sample_matches_the_live_response():
    """`contracts/opportunity_search_sample.json` 是前端 vitest／e2e mock 的
    唯一來源；後端改了回應而沒重產樣本，這條先紅。逐欄（含數值）比對。"""
    import json
    from pathlib import Path

    from scripts.gen_opportunity_search_sample import build_sample

    sample_path = Path("contracts/opportunity_search_sample.json")
    assert sample_path.exists(), "請跑 scripts/gen_opportunity_search_sample.py"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    assert build_sample() == sample, (
        "搜尋回應與契約樣本不一致——請跑 scripts/gen_opportunity_search_sample.py "
        "重產，並確認前端 mock 跟著更新")
    assert {r["family"] for r in sample["rows"]} == set(ALL_FAMILIES)
    assert [f["reason"] for f in sample["failures"]] == ["fetch_failed"]
