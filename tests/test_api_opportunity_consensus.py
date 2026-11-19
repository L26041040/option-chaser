"""分析師共識：資料來源介面、全站共識快取、每日 cron、共識清單 API（OS-03／#392）。

母票 #389 §2／§3／§7／§8（以 #389 留言 A1–A4 為準）。釘住：

- 來源**預設未設定**（`analyst_source=None`）：清單回 `configured: false`、
  cron 回 `skipped`，什麼都不做——本輪沒有任何真實來源。
- 固定測試資料（`FixtureAnalystSource`，ticker AAA…GGG）只在測試注入，
  回應帶 `source.is_fixture = true`。
- 同一交易日最多抓一次上游；失敗保留上一份成功資料並標其 as_of；cron
  受 refresh 預算約束、跑不完的下次接續。
- 清單只讀快取：改門檻後立即改變、不重打上游。
- 只限 SU／SA；Normal 403。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import FixtureAnalystSource, ProviderResult
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import AnalystTargetRecord
from tests._role_session import grant_role

FIXTURE = "tests/fixtures/analyst_targets_fixture.json"
FIXTURE_SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
CRON = {"Authorization": "Bearer test-secret"}
_DEFAULT = {"mode": "default", "provider": None}


class CountingSource:
    """包住任何來源、記錄每檔被呼叫幾次（驗證「同日不重抓」用）。"""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name
        self.is_fixture = inner.is_fixture
        self.calls: list[str] = []

    def fetch(self, symbol: str, today: date) -> ProviderResult:
        self.calls.append(symbol)
        return self.inner.fetch(symbol, today)


def _app(storage, *, source=None, role="superuser", **overrides):
    if role != "normal":
        grant_role(storage, role, owner_id="solo")
    return TestClient(create_app(identity_resolver=lambda: "solo", storage=storage,
                                 analyst_source=source, cron_secret="test-secret",
                                 **overrides))


def _use_custom_universe(client, symbols=FIXTURE_SYMBOLS, **extra):
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "custom", "custom_symbols": symbols,
                               **extra}})
    assert r.status_code == 200, r.text


def _consensus(client):
    r = client.get("/api/opportunity/consensus")
    assert r.status_code == 200, r.text
    return r.json()


def _items(body):
    return {i["symbol"]: i for i in body["items"]}


# ---------- 來源未設定（預設） ----------

def test_unconfigured_source_lists_nothing_and_says_so():
    client = _app(MemoryStorage())
    body = _consensus(client)
    assert body["source"] == {"configured": False, "name": None, "is_fixture": False}
    assert body["items"] == []
    assert body["message"] == "尚未設定分析師資料來源"


def test_unconfigured_source_cron_is_skipped_and_touches_nothing():
    storage = MemoryStorage()
    client = _app(storage)
    r = client.get("/api/cron/consensus-refresh", headers=CRON)
    assert r.status_code == 200
    assert r.json() == {"skipped": "source_not_configured"}
    assert storage.consensus_refresh_states() == {}



# ---------- 固定測試資料來源 ----------

def _fixture_client(storage=None, *, source=None, **kw):
    storage = storage or MemoryStorage()
    client = _app(storage, source=source or FixtureAnalystSource(FIXTURE), **kw)
    _use_custom_universe(client)
    return client, storage


def _run_cron(client):
    r = client.get("/api/cron/consensus-refresh", headers=CRON)
    assert r.status_code == 200, r.text
    return r.json()


def _sample_symbols():
    from api_app.search_universe import resolve_universe
    return resolve_universe(None).symbols


def test_fixture_source_is_flagged_as_fixture_in_the_response():
    client, _ = _fixture_client()
    body = _consensus(client)
    assert body["source"] == {"configured": True, "name": "fixture", "is_fixture": True}
    assert "message" not in body


def test_symbols_without_cache_are_listed_as_not_yet_refreshed():
    """母體內沒有快取的 symbol 一律以 no_data 列出（附原因），不得省略。"""
    client, _ = _fixture_client()
    items = _consensus(client)["items"]
    assert [i["symbol"] for i in items] == FIXTURE_SYMBOLS
    for i in items:
        assert i["status"] == "no_data"
        assert i["reasons"] == ["no_data: 尚未更新"]
        assert i["gate"] == {"first": False, "second": False, "selected": False,
                             "reasons": ["no_data: 尚未更新"]}


def test_fixture_list_matches_the_designed_scenarios_after_cron():
    """`scripts/gen_analyst_targets_fixture.py` 的設計表：每檔的狀態與兩關結果。"""
    client, _ = _fixture_client()
    _run_cron(client)
    items = _items(_consensus(client))
    expect = {  # symbol: (status, first, second, selected)
        "AAA": ("ok", True, True, True),
        "BBB": ("ok", True, False, False),
        "CCC": ("ok", False, True, False),
        "DDD": ("insufficient_analysts", False, False, False),
        "EEE": ("ok", True, True, True),
        "FFF": ("no_data", False, False, False),
        "GGG": ("source_error", False, False, False),
    }
    got = {s: (i["status"], i["gate"]["first"], i["gate"]["second"],
               i["gate"]["selected"]) for s, i in items.items()}
    assert got == expect


def test_fixture_numbers_for_the_passing_symbol():
    client, _ = _fixture_client()
    _run_cron(client)
    aaa = _items(_consensus(client))["AAA"]
    assert aaa["as_of"] == "2026-09-28"
    assert aaa["n_analysts"] == 7
    assert aaa["mean"] == 120.0
    # 目標價 105…135（間隔 5）：樣本 stdev = 5·√(28/6) ≈ 10.8012
    assert aaa["stdev"] == pytest.approx(10.8012, abs=1e-4)
    assert aaa["dispersion"] == pytest.approx(0.090010, abs=1e-6)
    assert aaa["percentile"] == pytest.approx(6 / 44)
    assert aaa["history_points"] == 44
    assert aaa["coverage"] == "partial"
    assert aaa["freshness_share"] == 1.0
    assert aaa["reasons"] == []
    assert aaa["gate"]["reasons"] == []
    # #390 暫定規則：today 所在月 + 12 個月
    assert aaa["target_month"] == "2027-09"
    assert aaa["refresh_error"] is None


def test_split_is_adjusted_not_flagged():
    client, _ = _fixture_client()
    _run_cron(client)
    eee = _items(_consensus(client))["EEE"]
    assert eee["status"] == "ok" and eee["mean"] == 110.0


def test_consensus_only_source_is_no_data_with_reason():
    client, _ = _fixture_client()
    _run_cron(client)
    fff = _items(_consensus(client))["FFF"]
    assert fff["status"] == "no_data"
    assert fff["reasons"][0] == "no_data: 來源僅有共識值，沒有個別目標價"
    assert fff["mean"] is None and fff["dispersion"] is None


def test_insufficient_analysts_still_shows_the_numbers_but_fails_both_gates():
    client, _ = _fixture_client()
    _run_cron(client)
    ddd = _items(_consensus(client))["DDD"]
    assert ddd["n_analysts"] == 3
    assert ddd["reasons"][0].startswith("insufficient_analysts")
    assert ddd["gate"]["selected"] is False


def test_universe_summary_counts():
    client, _ = _fixture_client()
    _run_cron(client)
    u = _consensus(client)["universe"]
    assert u["id"] == "custom" and u["provisional"] is False
    assert u["symbols"] == 7
    assert u["with_data"] == 5          # AAA BBB CCC DDD EEE（FFF 無資料、GGG 失敗）
    assert u["insufficient"] == 1       # DDD
    assert u["coverage"] == {"complete": 1, "partial": 2, "unknown": 2}
    assert u["as_of"] == "2026-09-28"


def test_default_universe_is_the_provisional_sample():
    storage = MemoryStorage()
    client = _app(storage, source=FixtureAnalystSource(FIXTURE))
    body = _consensus(client)
    assert body["universe"]["id"] == "sample-large-cap"
    assert body["universe"]["provisional"] is True
    assert body["universe"]["symbols"] == len(body["items"]) == 50


def test_thresholds_and_rules_are_reported():
    client, _ = _fixture_client()
    body = _consensus(client)
    assert body["thresholds"] == {"percentile_max": 20, "dispersion_max": 10}
    assert body["rules"]["provisional"] is True
    assert body["rules"]["n_min"] == 5
    assert body["rules"]["rules_version"] == "provisional-389"


# ---------- 改門檻：立即生效、不重打上游 ----------

def test_changing_thresholds_changes_the_list_without_refetching():
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source)
    _run_cron(client)
    calls = len(source.calls)
    assert _items(_consensus(client))["BBB"]["gate"]["selected"] is False

    _use_custom_universe(client, dispersion_max=16)   # BBB 分歧度 ≈ 15.1%
    body = _consensus(client)
    assert body["thresholds"]["dispersion_max"] == 16
    assert _items(body)["BBB"]["gate"]["selected"] is True

    _use_custom_universe(client, percentile_max=10)   # AAA 百分位 6/44 ≈ 13.6%
    aaa = _items(_consensus(client))["AAA"]
    assert aaa["gate"]["first"] is False and aaa["gate"]["second"] is True
    assert len(source.calls) == calls


# ---------- cron：同日不重抓、失敗保留上一份、游標接續 ----------

def test_cron_requires_the_secret():
    client, storage = _fixture_client()
    assert client.get("/api/cron/consensus-refresh").status_code == 401
    assert client.get("/api/cron/consensus-refresh",
                      headers={"Authorization": "Bearer nope"}).status_code == 401
    assert storage.consensus_refresh_states() == {}


def test_cron_refreshes_sample_universe_union_every_owner_custom_list():
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source)
    body = _run_cron(client)
    assert sorted(source.calls) == sorted(set(FIXTURE_SYMBOLS) | set(_sample_symbols()))
    assert body["remaining"] == []
    assert body["failed"] == 1          # GGG


def test_cron_twice_on_the_same_trading_day_does_not_refetch():
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source)
    _run_cron(client)
    first = len(source.calls)
    again = _run_cron(client)
    assert len(source.calls) == first
    assert again["processed"] == 0
    assert again["already_attempted_today"] == first


def test_cron_on_the_next_trading_day_refetches(monkeypatch):
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source)
    _run_cron(client)
    first = len(source.calls)
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 29))
    _run_cron(client)
    assert len(source.calls) == 2 * first
    assert _items(_consensus(client))["AAA"]["as_of"] == "2026-09-29"


def _seed_custom_list(storage, owner_id, role, symbols):
    """直接寫 storage：Normal 透過 API 本來就寫不進（403），這裡模擬「升權時
    存下、後來被降回 Normal」或舊資料殘留的情況。"""
    from api_app.storage import DataSourceSettings, UsageSetting
    grant_role(storage, role, owner_id=owner_id)
    storage.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="default"), historical_iv=UsageSetting(mode="default"),
        updated_at="2026-09-01T00:00:00+00:00", owner_id=owner_id,
        opportunity_search={"universe_id": "custom", "custom_symbols": symbols}))


def test_cron_merges_custom_lists_only_from_superuser_and_superadmin_owners():
    storage = MemoryStorage()
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client = _app(storage, source=source)
    _seed_custom_list(storage, "su-owner", "superuser", ["SUONE"])
    _seed_custom_list(storage, "sa-owner", "superadmin", ["SAONE"])
    _seed_custom_list(storage, "normal-owner", "normal", ["NORMONE"])
    _run_cron(client)
    assert sorted(source.calls) == sorted({*_sample_symbols(), "SUONE", "SAONE"})


def test_cron_universe_is_capped_with_the_sample_first_then_sorted_custom():
    storage = MemoryStorage()
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client = _app(storage, source=source, consensus_refresh_symbol_cap=52)
    _seed_custom_list(storage, "su-owner", "superuser", ["ZZZ", "MMM", "AAPL", "BBB"])
    body = _run_cron(client)
    # 樣本 50 檔（含 AAPL）先；自訂清單去重後依代號排序 BBB、MMM、ZZZ，只剩 2 個名額。
    assert sorted(source.calls) == sorted({*_sample_symbols(), "BBB", "MMM"})
    assert body["remaining"] == []


def test_cron_universe_cap_defaults_to_200():
    storage = MemoryStorage()
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client = _app(storage, source=source)
    for n in range(5):
        _seed_custom_list(storage, f"su-{n}", "superuser",
                          [f"X{n}{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(50)])
    _run_cron(client)
    assert len(source.calls) == 200
    assert set(_sample_symbols()) <= set(source.calls)


class FlakySource:
    """第一次成功（五位分析師）、`fail` 打開後一律丟例外。"""

    name = "flaky"
    is_fixture = True

    def __init__(self):
        self.fail = False

    def fetch(self, symbol, today):
        if self.fail:
            raise TimeoutError("上游逾時")
        recs = tuple(AnalystTargetRecord(symbol=symbol, analyst_key=f"F{i}",
                                         firm=f"F{i}", target_price=Decimal(p),
                                         published_on=date(2026, 9, 1))
                     for i, p in enumerate(("110", "115", "120", "125", "130")))
        return ProviderResult(records=recs, coverage="complete")


def test_upstream_failure_keeps_the_previous_snapshot_and_its_as_of(monkeypatch):
    source = FlakySource()
    storage = MemoryStorage()
    client = _app(storage, source=source)
    _use_custom_universe(client, ["AAA"])
    _run_cron(client)
    before = _items(_consensus(client))["AAA"]
    assert before["as_of"] == "2026-09-28" and before["mean"] == 120.0

    source.fail = True
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 29))
    assert _run_cron(client)["failed"] >= 1
    after = _items(_consensus(client))["AAA"]
    assert after["as_of"] == "2026-09-28"
    assert after["mean"] == 120.0
    assert after["refresh_error"] == {"day": "2026-09-29",
                                      "message": "資料來源丟出例外：上游逾時"}


def test_failure_without_any_previous_snapshot_is_source_error():
    client, _ = _fixture_client()
    _run_cron(client)
    ggg = _items(_consensus(client))["GGG"]
    assert ggg["status"] == "source_error"
    assert ggg["reasons"] == ["source_error: 逾時（測試資料模擬上游失敗）"]
    assert ggg["as_of"] is None


def test_cron_cursor_resumes_where_the_budget_ran_out():
    """預算 0：每次只處理一檔；剩下的依序由下一次呼叫接續，不重複、不遺漏。"""
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source, refresh_run_budget=timedelta(0))
    total = len(set(FIXTURE_SYMBOLS) | set(_sample_symbols()))

    first = _run_cron(client)
    assert first["processed"] == 1
    assert len(first["remaining"]) == total - 1
    second = _run_cron(client)
    assert second["processed"] == 1
    assert second["remaining"] == first["remaining"][1:]

    for _ in range(total):
        if not _run_cron(client)["remaining"]:
            break
    assert len(source.calls) == len(set(source.calls)) == total


def test_cron_cursor_prefers_symbols_least_recently_attempted(monkeypatch):
    """跑不完的尾巴隔天先跑——不會每天都從頭開始、尾巴永遠輪不到。"""
    source = CountingSource(FixtureAnalystSource(FIXTURE))
    client, _ = _fixture_client(source=source, refresh_run_budget=timedelta(0))
    first = _run_cron(client)
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 29))
    next_day = _run_cron(client)
    assert source.calls[1] == first["remaining"][0]      # 從沒嘗試過的先
    assert next_day["remaining"][-1] == source.calls[0]  # 昨天跑過的排最後


# ---------- 權限 ----------

def test_normal_user_gets_403():
    client = _app(MemoryStorage(), source=FixtureAnalystSource(FIXTURE), role="normal")
    assert client.get("/api/opportunity/consensus").status_code == 403


@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_superuser_and_superadmin_get_200(role):
    client = _app(MemoryStorage(), source=FixtureAnalystSource(FIXTURE), role=role)
    assert client.get("/api/opportunity/consensus").status_code == 200


# ---------- 每日摘要 ----------

def _digest_text(client, monkeypatch):
    sent = {}

    def fake_send(text, **kwargs):
        sent["text"] = text
        return False

    monkeypatch.setattr(main_module, "send_digest_email", fake_send)
    assert client.get("/api/cron/daily-digest", headers=CRON).status_code == 200
    return sent["text"]


def test_daily_digest_reports_consensus_refresh_counts(monkeypatch):
    client, _ = _fixture_client()
    _run_cron(client)
    text = _digest_text(client, monkeypatch)
    # 母體 50 檔樣本＋7 檔自訂：GGG 失敗；其餘 56 檔算出 Snapshot，其中
    # AAA／BBB／CCC／EEE 為 ok（另 52 檔資料不足或無資料）；預設門檻下入選 AAA、EEE。
    assert "分析師共識更新" in text
    assert "來源：fixture（測試資料，非真實市場資料）" in text
    assert "成功：56" in text
    assert "失敗：1" in text
    assert "資料不足或無資料：52" in text
    assert "入選（預設門檻 20%／10%）：2" in text


def test_daily_digest_says_when_the_source_is_not_configured(monkeypatch):
    client = _app(MemoryStorage())
    text = _digest_text(client, monkeypatch)
    assert "分析師共識更新" in text
    assert "尚未設定分析師資料來源" in text


def test_consensus_refresh_is_scheduled_once_a_day_before_the_digest():
    import json
    from pathlib import Path
    crons = {c["path"]: c["schedule"]
             for c in json.loads(Path("vercel.json").read_text())["crons"]}
    minute, hour, dom, month, dow = crons["/api/cron/consensus-refresh"].split()
    assert minute.isdigit() and hour.isdigit() and dom == "*" and month == "*"
    digest_hour = int(crons["/api/cron/daily-digest"].split()[1])
    assert int(hour) < digest_hour   # 摘要讀得到當天的更新統計


# ---------- 契約樣本（前端 mock 與後端共用） ----------

def test_opportunity_consensus_sample_matches_the_live_response():
    """`contracts/opportunity_consensus_sample.json` 是前端 vitest／e2e mock
    的唯一來源；後端改了回應而沒重產樣本，這條先紅。評估日固定，因此
    逐欄（含數值）比對，不只比欄位集合。"""
    import json
    from pathlib import Path

    from scripts.gen_opportunity_consensus_sample import build_sample

    sample_path = Path("contracts/opportunity_consensus_sample.json")
    assert sample_path.exists(), "請跑 scripts/gen_opportunity_consensus_sample.py"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    assert build_sample() == sample, (
        "共識清單回應與契約樣本不一致——請跑 "
        "scripts/gen_opportunity_consensus_sample.py 重產，並確認前端 mock 跟著更新")
    assert sample["source"]["is_fixture"] is True
    assert {i["status"] for i in sample["items"]} == {
        "ok", "insufficient_analysts", "no_data", "source_error"}


# ---------- 規則可設定、不寫死（user story 40） ----------

def test_injected_n_min_changes_outcomes_without_code_changes():
    """`create_app(consensus_rules=...)`：同一份資料，N_min 從 5 降到 3，
    DDD（3 位分析師）就不再是 insufficient_analysts；規則區塊照實回報。"""
    from option_chaser.consensus import ConsensusRules
    client, _ = _fixture_client(consensus_rules=ConsensusRules(n_min=3, version="r-test"))
    _run_cron(client)
    body = _consensus(client)
    ddd = _items(body)["DDD"]
    assert not any(r.startswith("insufficient_analysts") for r in ddd["reasons"])
    assert body["rules"]["n_min"] == 3
    assert body["rules"]["rules_version"] == "r-test"
    assert ddd["rules_version"] == "r-test"


class MarchSource:
    """五位分析師都在 2026-03-02 發布——發布日中位數與「今天」差半年。"""

    name = "march"
    is_fixture = True

    def fetch(self, symbol, today):
        recs = tuple(AnalystTargetRecord(symbol=symbol, analyst_key=f"F{i}",
                                         firm=f"F{i}", target_price=Decimal(p),
                                         published_on=date(2026, 3, 2))
                     for i, p in enumerate(("110", "115", "120", "125", "130")))
        return ProviderResult(records=recs, coverage="complete")


@pytest.mark.parametrize("rule, expected", [
    (None, "2027-09"),                             # 暫定預設 fixed_12m：今天所在月 + 12
    ("median_published_plus_12m", "2027-03"),      # 發布日中位數 2026-03-02 + 12
])
def test_injected_target_month_rule_is_used_and_reported(rule, expected):
    storage = MemoryStorage()
    client = _app(storage, source=MarchSource(), target_month_rule=rule)
    _use_custom_universe(client, ["AAA"])
    _run_cron(client)
    body = _consensus(client)
    assert body["rules"]["target_month_rule"] == (rule or "fixed_12m")
    assert _items(body)["AAA"]["target_month"] == expected


def test_unknown_target_month_rule_is_rejected_at_startup():
    with pytest.raises(ValueError):
        create_app(identity_resolver=lambda: "solo", storage=MemoryStorage(),
                   target_month_rule="next-blue-moon")


# ---------- FixtureAnalystSource 帶完整欄位（A2／A3 走 provider） ----------

def _write_fixture(tmp_path, symbols):
    import json
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"name": "fixture-tmp", "symbols": symbols}),
                    encoding="utf-8")
    return FixtureAnalystSource(path)


def _post_split(n=4):
    return [{"analyst_key": f"Post {i}", "firm": f"Post {i}",
             "target_price": str(150 + 5 * (i % 3)), "published_on": "2026-09-01"}
            for i in range(n)]


def test_a2_record_already_split_adjusted_is_not_adjusted_twice_through_the_api(tmp_path):
    source = _write_fixture(tmp_path, {"SPL": {
        "coverage": "complete",
        "splits": [{"effective_on": "2026-08-03", "ratio": "4"}],
        "records": [{"analyst_key": "Pre", "firm": "Pre", "target_price": "150",
                     "published_on": "2026-07-01",
                     "split_adjusted_through": "2026-08-10"}, *_post_split()]}})
    client = _app(MemoryStorage(), source=source)
    _use_custom_universe(client, ["SPL"])
    _run_cron(client)
    spl = _items(_consensus(client))["SPL"]
    assert spl["n_analysts"] == 5
    assert spl["low"] == 150.0                     # 不會變成 150 / 4 = 37.5


def test_a3_same_day_records_pick_the_latest_retrieval_through_the_api(tmp_path):
    source = _write_fixture(tmp_path, {"TIE": {
        "coverage": "complete", "splits": [],
        "records": [
            {"analyst_key": "Firm X", "firm": "Firm X", "target_price": "100",
             "published_on": "2026-09-01", "retrieved_at": "2026-09-01T10:00:00+00:00"},
            {"analyst_key": "firm  x ", "firm": "Firm X", "target_price": "200",
             "published_on": "2026-09-01", "retrieved_at": "2026-09-01T09:00:00+00:00"},
            *_post_split()]}})
    client = _app(MemoryStorage(), source=source)
    _use_custom_universe(client, ["TIE"])
    _run_cron(client)
    tie = _items(_consensus(client))["TIE"]
    assert tie["n_analysts"] == 5                  # 兩種寫法是同一位分析師
    assert (tie["low"], tie["high"]) == (100.0, 160.0)   # 晚抓到的 100 勝，不是較高的 200


def test_fixture_source_populates_retrieved_at_and_split_adjusted_through(tmp_path):
    from datetime import datetime, timezone
    source = _write_fixture(tmp_path, {"SPL": {"records": [
        {"analyst_key": "A", "firm": "A", "target_price": "10",
         "published_on": "2026-07-01", "split_adjusted_through": "2026-08-10",
         "retrieved_at": "2026-09-27T21:00:00+00:00"},
        {"analyst_key": "B", "firm": "B", "target_price": "11",
         "published_on": "2026-07-02"}]}})
    a, b = source.fetch("SPL", date(2026, 9, 28)).records
    assert a.split_adjusted_through == date(2026, 8, 10)
    assert a.retrieved_at == datetime(2026, 9, 27, 21, 0, tzinfo=timezone.utc)
    # 檔案沒寫抓取時間：以這次抓取的日期（UTC 零時）為準，絕不留空。
    assert b.retrieved_at == datetime(2026, 9, 28, tzinfo=timezone.utc)
    assert b.split_adjusted_through is None
