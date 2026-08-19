"""Historical IV 端點與模組閘門（#126）。

最重要的一條不是「算得對」，而是**鎖著的時候一個請求都不發**——
`historical_surface` 注入一個會 assert 失敗的假體，任何偷跑都會紅燈。
"""
import dataclasses
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage import ContractHistory, IvBackfillRun, IvObservation
from api_app.storage.memory import MemoryStorage
from option_chaser import ivhistory, ivtrend
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ivhistory import SurfacePoint
from option_chaser.ivhistory import sampling_schedule
from option_chaser.models import FetchError, QuotaExhausted
from option_chaser.workspace import ny_today
from option_chaser.ratecurve import RateCurve

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
PROVIDER = providers.MARKETDATA_APP.id
TOKEN = "mdapp_live_SECRET1234abcd"

_RATE = RateCurve(curve_date="2026-07-31",
                  nodes=((0.5, 0.041), (1.0, 0.042), (2.0, 0.043), (3.0, 0.044)))
_DIV = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                       distributions=(DividendRecord("2026-06-01", 1.2),))


def _rate_loader(today):
    return _RATE, "假曲線"


def _dividend_loader(symbol, today):
    return _DIV, "假配息"


def _snap():
    return dataclasses.replace(load_snapshot(FIX), source="cboe")


def _surface_never_called(*args, **kwargs):
    raise AssertionError("鎖著的時候不得對 vendor 發任何請求")


def _grid():
    """一個蓋得夠寬的網格，任何合理座標都插得出來。"""
    # delta 一路蓋到 0.001／0.999：真實的鏈有深價外與深價內履約價，而
    # 這份 fixture 的兩腿 Spread 候選落在 0.03–0.06，長天期 Long Call
    # 深價內候選（#139）算出來的 delta 可以逼近 1（例如 strike 遠低於
    # spot 的長天期 call ≈0.9998）。網格不夠寬時引擎會（正確地）拒絕
    # 外插，那時測到的是「拒絕外插」而不是本來要測的東西。
    pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d)
           for dte in (1, 30, 90, 365, 1200)
           for d in (0.0001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.9999)]
    return {"call": pts, "put": pts}


def _rich_surface(*_args, **_kwargs):
    return _grid()


class Recorder:
    """記錄每一次 vendor 呼叫的 (symbol, 日期)——「已有日期不重抓」與
    「同一天不重複燒額度」都只能靠這個斷言。"""

    def __init__(self, fail=None):
        self.calls: list[tuple[str, str]] = []
        self._fail = fail

    def __call__(self, provider, symbol, on_date, token, expiration=None,
                observer=None):
        self.calls.append((symbol, on_date))
        if self._fail is not None:
            raise self._fail
        return _grid()

    @property
    def dates(self):
        return [d for _, d in self.calls]


def _contract_history_empty(provider, occ_symbol, from_date, to_date, token,
                            observer=None):
    """HIVT-02（#153）路徑的預設假體——existing 測試不關心 legs
    欄位，只需要「不打真的 vendor、安靜回空序列」，跟 `_rich_surface`
    對舊 (tenor, delta) 家族的角色對應。"""
    return []


def _client(db, *, surface=_surface_never_called,
           contract_history=_contract_history_empty):
    return TestClient(create_app(
        storage=db, fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=surface, contract_history=contract_history))


@pytest.fixture
def db():
    return MemoryStorage()


def _scenario(client, *, target_price=130.0, target_month="2026-09"):
    """建立**並跑一次分析**——建立本身不分析，沒有結果就沒有候選可查。"""
    sid = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": target_price,
        "target_month": target_month}).json()["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    return sid


def _unlock(client, *, mode="custom", verified=True):
    client.put("/api/settings", json={
        "market_data": {"mode": "default", "provider": None},
        "historical_iv": {"mode": mode,
                          "provider": PROVIDER if mode == "custom" else None}})
    if mode == "custom":
        client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
        if verified:
            client.post(f"/api/settings/credentials/{PROVIDER}/test")


def _candidate_key(client, sid):
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for c in g["candidates"]:
                return c["candidate_key"]
    raise AssertionError("樣本裡沒有候選可用")


def _get(client, sid, key):
    return client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})


# ---------- 閘門 ----------

def test_locked_by_default_and_no_vendor_request_is_made(db):
    """預設是「無」——模組鎖著，而且一個 vendor 請求都不發。"""
    client = _client(db)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    assert _get(client, sid, key).status_code == 403


def test_settings_report_the_module_as_disabled_by_default(db):
    client = _client(db)
    assert client.get("/api/settings").json()["historical_iv_enabled"] is False


def test_custom_without_a_credential_stays_locked(db):
    client = _client(db)
    _unlock(client, mode="custom", verified=False)
    client.delete(f"/api/settings/credentials/{PROVIDER}")
    assert client.get("/api/settings").json()["historical_iv_enabled"] is False


def test_custom_with_an_unverified_credential_stays_locked(db):
    """存了 token 但沒測過＝還沒證明能用，不進半殘狀態。"""
    client = _client(db)
    _unlock(client, verified=False)
    assert client.get("/api/settings").json()["historical_iv_enabled"] is False
    sid = _scenario(client)
    assert _get(client, sid, _candidate_key(client, sid)).status_code == 403


def test_a_failed_verification_keeps_the_module_locked(db):
    client = TestClient(create_app(
        storage=db, fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(False, "認證被拒"),
        historical_surface=_surface_never_called))
    _unlock(client, verified=True)
    assert client.get("/api/settings").json()["historical_iv_enabled"] is False


def test_verified_custom_unlocks_the_module(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    assert client.get("/api/settings").json()["historical_iv_enabled"] is True
    sid = _scenario(client)
    assert _get(client, sid, _candidate_key(client, sid)).status_code == 200


def test_switching_back_to_default_relocks_and_stops_requests(db):
    """關掉之後不是「留著舊資料」，是整個回到鎖住、零請求。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    assert _get(client, sid, key).status_code == 200

    client.put("/api/settings", json={
        "market_data": {"mode": "default", "provider": None},
        "historical_iv": {"mode": "default", "provider": None}})
    assert client.get("/api/settings").json()["historical_iv_enabled"] is False
    assert _get(client, sid, key).status_code == 403


# ---------- 序列本身 ----------

def test_series_comes_from_the_cache_and_is_re_anchored(db):
    """序列的每一點對應快取裡的一天觀測，在候選自己的座標上重新插值。

    HIVT-04（#155）：舊的 `points`（帶 buy_iv／sell_iv／atm_iv 子欄位）
    已從回應信封移除，Normalized Skew 自己的走勢圖改讀
    `normalized_skew_points`——內部計算完全沒變，只是信封窄了。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    cached = db.iv_observation_dates("XYZ")
    assert [p["date"] for p in body["normalized_skew_points"]] == cached
    assert body["metrics"]["normalized_skew"]["value"] is not None


def test_normalized_skew_points_only_carry_date_and_normalized_skew(db):
    """HIVT-04：舊 `points` 的 buy_iv／sell_iv／atm_iv 子欄位真的消失了
    ——不是換個信封鍵名字繼續夾帶被取代的資料。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    point = _get(client, sid, _candidate_key(client, sid)).json()[
        "normalized_skew_points"][0]
    assert set(point) == {"date", "normalized_skew"}


def _prefill(db, symbol="XYZ"):
    """把整份排程灌進快取——模擬 backfill 已經跑完的那一天。"""
    from api_app.main import _surface_to_rows
    from api_app.storage import IvObservation

    for day in sampling_schedule(symbol, ny_today()):
        db.save_iv_observation(IvObservation(
            symbol=symbol, observed_on=day,
            surface=_surface_to_rows(_grid()),
            fetched_at="2026-08-12T00:00:00+00:00"))


def test_percentiles_are_reported_once_the_cache_has_any_valid_observation(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    _prefill(db)
    metrics = _get(client, sid, _candidate_key(client, sid)).json()["metrics"]
    assert metrics["normalized_skew"]["percentile"] is not None
    assert metrics["normalized_skew"]["count"] > 0


# ---------- Long Call 單腳候選（#139／spec #137）----------
#
# **範圍查證（施工前發現，記錄在此供後續票參照）**：Scenario 端點
# （`/api/scenarios` → `/refresh`）目前只跑 `_MVP_STRATEGIES =
# ("bull-call-spread",)`——Long Call 完全不是 Scenario 流程會產生的
# 候選，這是比「ivhistory 對單腳回 None」更上層的既有 MVP 範圍限制，
# 不是這張票的範圍（那是另一個層級的產品決策，改它會牽動候選產生／
# 排序／劇本清單，遠超過 Historical IV 這張票）。legacy 的
# `/api/analyze`（adhoc，V1 遺留）仍接受任意 `strategies`、能產生真正
# 由引擎算出的 long-call 候選，但那個端點本身不落盤，查不到
# iv-history。以下測試借用它產生**真實引擎輸出**的 long-call 候選
# （不是手造假資料），再手動存一筆 `ResultRecord` 掛到一個真的
# Scenario 底下，藉此在端點層驗證「單腳候選資料路徑」本身，不需要、
# 也不擅自變更 Scenario 產生候選的策略範圍。

def _long_call_candidate_key_and_view(client):
    """借 legacy adhoc 端點跑一次真正的 long-call 分析，回傳
    (candidate_key, view)——candidate 是引擎真實輸出，不是手造的。

    單腳策略沒有 `expiry_top10` 分組（T9 附錄A7：範圍限定 Spread 路徑）
    ——候選在扁平的 `r["candidates"]` 清單裡（#139 施工中查證）。"""
    resp = client.post("/api/analyze", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["long-call"]})
    assert resp.status_code == 200, resp.text
    view = resp.json()
    for r in view["results"]:
        for c in r.get("candidates") or []:
            return c["candidate_key"], view
    raise AssertionError("adhoc long-call 分析沒有產生任何候選")


def _attach_result(db, sid, view, *, analyzed_at="2026-08-12T00:00:00+00:00"):
    """把一份 view 直接存成該 Scenario 的最新結果——繞過 `/refresh`
    （那條路徑目前只跑 bull-call-spread），純粹是為了在端點層測試單腳
    資料路徑，不代表產品裁示 Scenario 該支援 long-call。"""
    from api_app.storage import ResultRecord

    db.save_result(ResultRecord(scenario_id=sid, analyzed_at=analyzed_at,
                                view=view))


def test_a_long_call_candidate_returns_200_not_the_old_blanket_none(db):
    """現況：`spread_coordinates` 對單腳直接回 None，端點回『這個候選算
    不出座標』的空白訊息。這是那個限制的解除——單腳候選現在也能拿到
    正常的 200 回應。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)

    resp = _get(client, sid, key)
    assert resp.status_code == 200
    assert resp.json()["candidate_key"] == key


def test_a_long_call_candidate_has_no_normalized_skew(db):
    """單腳候選結構上沒有 Normalized Skew——`count == 0`，不是新的錯誤
    狀態（HIVT-04：舊 buy_iv／atm_iv reanchored 次要顯示已移除，改由
    `legs.buy` 供應，見 test_legs_field_omits_the_sell_key_entirely_
    for_a_single_leg_candidate）。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)
    _prefill(db)

    body = _get(client, sid, key).json()
    assert body["metrics"]["normalized_skew"] == \
        {"value": None, "percentile": None, "count": 0,
         "trend_4w": None, "trend_base_count": 0}
    assert all(p["normalized_skew"] is None
              for p in body["normalized_skew_points"])


def test_a_long_call_candidate_still_honours_the_gate(db):
    """單腳候選一樣受閘門管——未解鎖照樣 403，不繞過既有規則。單一
    client 全程不解鎖：`/api/analyze`（產生 long-call 候選用）不受這個
    閘門管，不需要先解鎖才能借它拿到候選（settings 是 db 層共享狀態，
    兩個各自解鎖／不解鎖的 client 會互相汙染，見既有
    `test_switching_back_to_default_relocks_and_stops_requests` 的
    單一 client 慣例）。"""
    client = _client(db)   # 全程不呼叫 _unlock
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)

    assert _get(client, sid, key).status_code == 403


def test_two_leg_spread_candidates_are_unaffected_by_the_single_leg_path(db):
    """回歸：既有兩腿路徑（Scenario 正常 `/refresh` 產生的
    bull-call-spread 候選）Normalized Skew 行為與數值完全不因這次修改
    而變（HIVT-04：買／賣腿次要顯示已移除，改由 `legs` 供應）。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)   # Scenario 流程目前只有 spread 候選
    _prefill(db)
    body = _get(client, sid, key).json()
    m = body["metrics"]["normalized_skew"]
    assert m["percentile"] is not None
    assert m["count"] > 0
    assert m["value"] is not None


def test_a_coordinate_outside_the_grid_is_left_blank_not_faked(db):
    """網格只蓋短天期時，這個候選在歷史每一天都插不出值——留空，不是拿
    最長那格頂替（#114 AC 明文）。count 因此是 0，這是唯一容許「不給
    percentile」的情況：真的一筆可比觀測都沒有（#133），不是門檻判定。"""
    narrow = [SurfacePoint(dte=d, delta=x, iv=0.2)
              for d in (1, 5) for x in (0.4, 0.5, 0.6)]
    client = _client(db, surface=lambda *a, **k: {"call": narrow, "put": narrow})
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["normalized_skew_points"], "應該有觀測，只是每一點都插不出值"
    assert all(p["normalized_skew"] is None
              for p in body["normalized_skew_points"])
    assert body["metrics"]["normalized_skew"] == \
        {"value": None, "percentile": None, "count": 0,
         "trend_4w": None, "trend_base_count": 0}
    assert body["status"] == "ok"   # backfill 本身沒失敗，只是這個候選的
                                    # 座標在這個網格裡真的找不到可比的點


def test_a_vendor_failure_is_reported_rather_than_swallowed(db):
    def broken(*_a, **_k):
        raise FetchError("額度用盡")

    client = _client(db, surface=broken)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["normalized_skew_points"] == []
    assert "額度用盡" in body["note"]


def test_an_unknown_candidate_is_a_404_not_an_empty_series(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    assert _get(client, sid, "no-such-candidate").status_code == 404


def test_the_token_never_appears_in_the_response(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    assert TOKEN not in _get(client, sid, _candidate_key(client, sid)).text


# ---------- enrich-only 紅線 ----------

def test_iv_history_failure_does_not_break_refresh(db):
    """刷新流程與 IV 抓取隔離：IV 端點掛掉，劇本照樣刷得動。"""
    def broken(*_a, **_k):
        raise FetchError("vendor 掛了")

    client = _client(db, surface=broken)
    _unlock(client)
    sid = _scenario(client)
    assert client.post(f"/api/scenarios/{sid}/refresh").status_code == 200


def test_unlocking_iv_history_changes_no_candidate_and_no_ordering(db):
    """整組結果在解鎖前後**逐位元相同**——這就是「移除整個 IV 模組後
    每個候選的命運與順序不變」的另一面。"""
    locked = _client(db, surface=_surface_never_called)
    sid = _scenario(locked)
    before = locked.get(f"/api/scenarios/{sid}").json()["latest_result"]

    unlocked = _client(db, surface=_rich_surface)
    _unlock(unlocked)
    unlocked.post(f"/api/scenarios/{sid}/refresh")
    after = unlocked.get(f"/api/scenarios/{sid}").json()["latest_result"]

    def identities(view):
        return [[c["candidate_key"] for c in g["candidates"]]
                for r in view["results"] for g in r.get("expiry_top10") or []]

    assert identities(before) == identities(after)
    assert before["baseline_expiry"] == after["baseline_expiry"]


def test_the_analysis_view_gains_no_iv_history_field(db):
    """IV 歷史走自己的端點，不摻進 view dict——摻進去就有機會被排序讀到。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    assert "iv_history" not in view
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for c in g["candidates"]:
                assert not any("iv_history" in k for k in c)


def _function_source(module_src: str, name: str) -> str:
    """用 AST 找出一個函式的原始碼片段——不管它是模組層級還是巢狀在
    `create_app()` 裡的 closure，`ast.walk` 都找得到，不必靠「下一個
    def」這種對縮排敏感、遇到巢狀函式會誤判邊界的字串式切法。"""
    import ast

    tree = ast.parse(module_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(module_src, node)
    raise AssertionError(f"找不到函式 {name}")


def test_exact_contract_pipeline_never_calls_the_reanchoring_functions():
    """spec #151 §7／Testing Decisions 的對稱隔離測試——上面
    `test_the_analysis_view_gains_no_iv_history_field` 證的是「新家族
    不外洩進舊家族的資料形狀」，這裡證反方向：新家族（`legs` 回應）的
    產生路徑完全不呼叫舊 (tenor,delta) 重錨定家族的任何函式。逐函式
    （而不是整個 main.py）檢查，因為 main.py 本身合法地為舊家族呼叫
    這些函式——隔離紅線畫在新家族自己的函式邊界，不是整個檔案。"""
    import api_app.main as main

    src = open(main.__file__, encoding="utf-8").read()
    forbidden = ("reanchor_spread", "iv_at(", "spread_coordinates(",
                "leg_coordinate(", "nearby_expirations(")
    exact_contract_functions = (
        "_leg_contract_identity", "_identity_context",
        "_emit_contract_history_telemetry", "_ensure_contract_history",
        "_emit_leg_stat_metrics", "_leg_historical_iv_payload",
    )
    for fn_name in exact_contract_functions:
        body = _function_source(src, fn_name)
        for name in forbidden:
            assert name not in body, f"{fn_name} 引用了 {name}"


# ---------- 快取、漸進補齊、額度（#130） ----------

def test_backfill_only_touches_dates_the_cache_is_missing(db):
    """已有日期一次都不重抓——這是整個 quota 架構的地基。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)

    _get(client, sid, key)
    first = set(rec.dates)
    assert first, "第一次應該真的去抓"

    # 清掉「今天已跑過」的閘，讓它有機會再抓一次
    db.save_iv_backfill_run(IvBackfillRun(symbol="XYZ", ran_on="1900-01-01",
                                          outcome="ok"))
    rec.calls.clear()
    _get(client, sid, key)
    assert not (set(rec.dates) & first), "已經在快取裡的日期被重抓了"


def test_a_second_scenario_on_the_same_symbol_costs_no_quota(db):
    """同一 ticker 的第二個劇本完全靠快取——需求方紅線。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    a = _scenario(client)
    _get(client, a, _candidate_key(client, a))
    rec.calls.clear()

    b = _scenario(client, target_price=140.0)
    _get(client, b, _candidate_key(client, b))
    assert rec.calls == [], "第二個同 ticker 劇本不該再打 vendor"


def test_a_different_target_does_not_trigger_a_refetch(db):
    """target price／target month 不同都不是重抓的理由。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    a = _scenario(client)
    _get(client, a, _candidate_key(client, a))
    before = len(rec.calls)

    b = _scenario(client, target_month="2026-10")
    _get(client, b, _candidate_key(client, b))
    assert len(rec.calls) == before


def test_only_one_backfill_batch_per_symbol_per_day(db):
    """同一天多開幾個同 ticker 劇本不該各自再燒一批額度。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)

    _get(client, sid, key)
    after_first = len(rec.calls)
    for _ in range(3):
        _get(client, sid, key)
    assert len(rec.calls) == after_first


def test_each_batch_is_bounded_so_the_first_day_does_not_drain_quota(db):
    """progressive backfill：第一次用一個新 ticker 不是一口氣抓滿。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    _get(client, sid, _candidate_key(client, sid))
    assert 0 < len(rec.calls) <= 25


def test_the_newest_gaps_are_filled_first(db):
    """額度中途用完時，留下的該是比較有用的那一段。"""
    rec = Recorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    _get(client, sid, _candidate_key(client, sid))
    schedule = sampling_schedule("XYZ", ny_today())
    assert set(rec.dates) == set(sorted(schedule, reverse=True)[:len(rec.dates)])


# ---------- 五種狀態 ----------

def test_quota_exhaustion_is_reported_as_its_own_state(db):
    rec = Recorder(fail=QuotaExhausted("Market Data App 今日額度已用完"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "quota"
    assert "額度" in body["note"]


def test_a_transient_vendor_failure_is_a_different_state_from_quota(db):
    """「今天別再試了」跟「這次剛好失敗」對使用者是兩件事。"""
    rec = Recorder(fail=FetchError("連線逾時"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "vendor"


def test_quota_exhaustion_stops_further_vendor_calls_that_day(db):
    """額度用完還一直去撞，只是把明天的額度也浪費在錯誤訊息上。"""
    rec = Recorder(fail=QuotaExhausted("額度用完"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _get(client, sid, key)
    after_first = len(rec.calls)
    _get(client, sid, key)
    assert len(rec.calls) == after_first == 1


def test_zero_cached_observations_yields_no_percentile(db):
    """唯一容許「不給 percentile」的情況：literally 一筆觀測都沒有
    （backfill 從第一次嘗試就失敗，快取是空的）——這跟舊的 coverage
    門檻不同，這裡是真的沒有資料可比，不是資料「不夠多」。"""
    rec = Recorder(fail=FetchError("vendor 掛了"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["observations"] == 0
    assert body["metrics"]["normalized_skew"] == \
        {"value": None, "percentile": None, "count": 0,
         "trend_4w": None, "trend_base_count": 0}


def test_trend_4w_reflects_a_real_change_across_the_cached_series(db):
    """端到端：不是全年同一張網格（那種情況下 Δ4w 剛好是 0），而是隨
    日期真的變化的序列，證明 Δ4w 真的從快取的每日觀測算出來、不是常數
    佔位。網格 delta 軸的斜率隨日期加大——買賣兩腿的 delta 通常不同，
    Normalized Skew（兩腿之差）因此隨斜率變化而跟著變，不是常數
    （HIVT-04：`metrics` 只剩 `normalized_skew` 一項，不再驗 buy_iv；
    不預設變化方向——只證明「真的有變化」，不是常數佔位）。"""
    schedule = sampling_schedule("XYZ", ny_today())

    def _shifted_grid(offset: float) -> dict:
        pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + (0.1 + offset) * d)
              for dte in (1, 30, 90, 365, 1200)
              for d in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95)]
        return {"call": pts, "put": pts}

    from api_app.main import _surface_to_rows

    for i, day in enumerate(schedule):
        # 越晚的日子斜率越陡——delta 軸上不同位置的兩腿因此隨時間分歧。
        db.save_iv_observation(IvObservation(
            symbol="XYZ", observed_on=day,
            surface=_surface_to_rows(_shifted_grid(i * 0.01)),
            fetched_at="2026-08-12T00:00:00+00:00"))

    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    m = body["metrics"]["normalized_skew"]
    assert m["trend_4w"] is not None
    assert m["trend_4w"] != 0, "序列真的隨日期變化，Δ4w 不該剛好是常數 0"
    assert m["trend_base_count"] > 0


def test_a_first_day_run_with_partial_data_still_shows_a_percentile(db):
    """需求方 2026-08-12 二次修正：progressive backfill 第一天只補了一部
    分，但只要有觀測就給 percentile——不因為還沒補齊就隱藏。舊行為
    （status 判定 insufficient、percentile 清空）已被推翻。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "ok"
    assert 0 < body["observations"] < 66     # 真的只補了一部分
    metrics = body["metrics"]["normalized_skew"]
    assert metrics["percentile"] is not None
    assert 0 < metrics["count"] < 66


def test_a_healthy_run_reports_ok_with_metrics_for_every_field(db):
    """HIVT-04：`metrics` 只剩 `normalized_skew`（buy_iv／sell_iv／
    atm_iv 已隨舊次要顯示欄位一起移除）。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    _prefill(db)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "ok"
    assert body["observations"] >= 20
    assert set(body["metrics"]) == {"normalized_skew"}
    m = body["metrics"]["normalized_skew"]
    assert m["percentile"] is not None
    assert m["count"] > 0
    assert m["value"] is not None
    # #138：純加法欄位——整份排程都用同一張網格灌值，每天的重錨定
    # 結果都相同，Δ4w 因此該是 0（有基準可減，減出來剛好沒變化），
    # 不是 None（那會是「沒有基準」，跟這裡的情境不同）。
    assert m["trend_4w"] == pytest.approx(0.0)
    assert m["trend_base_count"] > 0


def test_the_old_top_level_points_key_and_leg_metrics_are_gone(db):
    """HIVT-04（#155）AC 明文：舊的 `points`／`metrics.buy_iv`／
    `metrics.sell_iv`／`metrics.atm_iv` 從回應移除。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert "points" not in body
    for removed in ("buy_iv", "sell_iv", "atm_iv"):
        assert removed not in body["metrics"]


def test_normalized_skew_is_bit_identical_to_an_independent_reanchored_computation(db):
    """HIVT-04（#155）AC 明文要求的前後比對：`metrics.normalized_skew`
    不是這次裁切信封時順手改出來的新計算——它逐位元等於直接呼叫
    `ivhistory.reanchor_spread()`／`field_metrics()`（本票完全沒碰的
    既有函式）在同一份快取觀測與同一組候選座標上算出的結果。這證明
    HIVT-04 只動了回應信封，沒有動內部計算本身。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _prefill(db)
    body = _get(client, sid, key).json()

    from api_app.main import _rows_to_surface
    from option_chaser import store

    rec = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    cand = store.find_candidate(rec, key)
    coords = ivhistory.spread_coordinates(cand, spot=rec["meta"]["spot"])
    independent_points = []
    for obs in db.iv_observations("XYZ"):
        surface = _rows_to_surface(obs.surface)
        reanchored = ivhistory.reanchor_spread(surface, coords)
        independent_points.append({"date": obs.observed_on, **reanchored})
    independent_metrics = ivhistory.field_metrics(independent_points, today=ny_today())

    assert body["metrics"]["normalized_skew"] == independent_metrics["normalized_skew"]


# ---------- 長天期候選的到期日鎖定（#134）----------

def _candidate_key_from_farthest_expiry(client, sid):
    """挑分析結果裡到期日最遠的那個候選——這是「vendor 預設下一個月選
    覆蓋不到」的那一類，正是需求方回報的 bug 重現條件。"""
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    best = None
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for c in g["candidates"]:
                if best is None or c["days_to_expiry"] > best["days_to_expiry"]:
                    best = c
    if best is None:
        raise AssertionError("樣本裡沒有候選可用")
    return best["candidate_key"]


def test_a_long_dated_candidate_actually_receives_non_default_expirations(db):
    """#134 修正核心：長天期候選要帶 `expiration` 篩選去打 vendor，不能
    只靠預設的下一個月選——那個預設永遠罩不到 LEAPS，這正是需求方回報
    『連線成功但無資料』的 root cause。"""
    class ExpirationRecorder:
        def __init__(self):
            self.expirations: list[str | None] = []

        def __call__(self, provider, symbol, on_date, token, expiration=None,
                     observer=None):
            self.expirations.append(expiration)
            return _grid()

    rec = ExpirationRecorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key_from_farthest_expiry(client, sid)

    _get(client, sid, key)
    assert any(e is not None for e in rec.expirations), \
        "長天期候選一次 expiration 篩選都沒帶，會撲空 vendor 的預設下一個月選"


def test_a_short_dated_candidate_keeps_using_the_cheap_vendor_default(db):
    """短天期候選不必多花 vendor 請求——這是 credit-conscious 那一半的
    紅線：預設本來就夠，不該為了修長天期的 bug 讓短天期也變貴。"""
    class ExpirationRecorder:
        def __init__(self):
            self.expirations: list[str | None] = []

        def __call__(self, provider, symbol, on_date, token, expiration=None,
                     observer=None):
            self.expirations.append(expiration)
            return _grid()

    rec = ExpirationRecorder()
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)   # 樣本裡第一個候選＝最近到期日那組

    _get(client, sid, key)
    assert all(e is None for e in rec.expirations)


def test_a_quota_failure_today_does_not_hide_yesterdays_cached_percentiles(db):
    """核心紅線：backfill 狀態（今天補不補得動）與資料能不能看是兩件事
    ——已經快取的觀測算出的 percentile 不因為今天撞額度就被藏起來。"""
    working = _client(db, surface=_rich_surface)
    _unlock(working)
    sid = _scenario(working)
    key = _candidate_key(working, sid)

    schedule = sampling_schedule("XYZ", ny_today())
    # 手動只灌一部分——模擬「先前幾天已經補到這裡」，留下缺口讓「今天」
    # 的 backfill 真的有事要做（尚未跑過，`get_iv_backfill_run` 是 None）。
    from api_app.main import _surface_to_rows

    for day in schedule[:10]:
        db.save_iv_observation(IvObservation(
            symbol="XYZ", observed_on=day, surface=_surface_to_rows(_grid()),
            fetched_at="2026-08-11T00:00:00+00:00"))

    failing = _client(db, surface=Recorder(fail=QuotaExhausted("額度用完")))
    _unlock(failing)
    body = _get(failing, sid, key).json()

    assert body["status"] == "quota"
    assert "額度" in body["note"]
    metrics = body["metrics"]["normalized_skew"]
    assert metrics["count"] == 10       # 先前補好的那 10 筆還在
    assert metrics["percentile"] is not None


def test_a_vendor_failure_today_does_not_hide_cached_percentiles_either(db):
    working = _client(db, surface=_rich_surface)
    _unlock(working)
    sid = _scenario(working)
    key = _candidate_key(working, sid)

    schedule = sampling_schedule("XYZ", ny_today())
    from api_app.main import _surface_to_rows

    for day in schedule[:5]:
        db.save_iv_observation(IvObservation(
            symbol="XYZ", observed_on=day, surface=_surface_to_rows(_grid()),
            fetched_at="2026-08-11T00:00:00+00:00"))

    failing = _client(db, surface=Recorder(fail=FetchError("連線逾時")))
    _unlock(failing)
    body = _get(failing, sid, key).json()

    assert body["status"] == "vendor"
    assert body["metrics"]["normalized_skew"]["count"] == 5
    assert body["metrics"]["normalized_skew"]["percentile"] is not None


# ---------- Historical IV 診斷接線（DG-03／#146） ----------
#
# 這裡的 surface 直接餵 observer 指定的 telemetry，不依賴
# `marketdata.py` 內部怎麼算出這份 telemetry（那是 DG-01／
# `test_data_marketdata.py` 的範圍）——本節只測 main.py 怎麼把
# telemetry 轉成診斷事件。

def _telemetry_surface(telemetry, *, points=None, call_counter=None):
    """observer 每次被呼叫都拿到同一份 `telemetry`（可自訂），可選
    `call_counter`（list）記錄實際被呼叫幾次——用來確認 no_data 不會
    中止整個 backfill 批次。"""
    def call(provider, symbol, on_date, token, expiration=None, observer=None):
        if call_counter is not None:
            call_counter.append(on_date)
        if observer is not None:
            observer(telemetry)
        return points or {"call": [], "put": []}
    return call


def _events_for(body, stage):
    return [e for e in body["diagnostics"]["events"] if e["stage"] == stage]


def _prefill_all_but_one(db, symbol="XYZ"):
    """把排程灌到只剩一天缺口——讓 backfill 迴圈只真的跑一次，事件數遠
    低於 per-request 上限（#146），不必連帶測到排放量控制那條路徑
    （那個有自己專屬的測試）。"""
    from api_app.main import _surface_to_rows
    from api_app.storage import IvObservation

    schedule = sorted(sampling_schedule(symbol, ny_today()))
    for day in schedule[:-1]:
        db.save_iv_observation(IvObservation(
            symbol=symbol, observed_on=day, surface=_surface_to_rows(_grid()),
            fetched_at="2026-08-12T00:00:00+00:00"))


def test_candidate_lookup_event_marks_found_true(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    got = _events_for(body, "candidate_lookup")
    assert len(got) == 1
    assert got[0]["severity"] == "info"
    assert got[0]["context"]["found"] is True
    assert got[0]["context"]["candidate_key"]


def test_candidate_lookup_event_marks_an_unknown_key_as_error_and_still_persists(db):
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    resp = _get(client, sid, "no-such-candidate")
    assert resp.status_code == 404
    # 404 沒有 diagnostics 欄位可讀（純字串 detail），但事件仍要落盤——
    # 使用者事後翻 Settings／Diagnostics 找得到這次失敗。
    stored = client.get("/api/diagnostics").json()
    lookups = [e for e in stored if e["stage"] == "candidate_lookup"]
    assert lookups[0]["severity"] == "error"
    assert lookups[0]["context"]["found"] is False


def test_raw_rows_positive_but_parsed_zero_is_a_warning_on_payload_parse(db):
    """「vendor 回 N 筆，卻在哪一站變成 0 筆」——這裡就是可以直接指認
    出來的地方：payload_parse 事件自己講清楚 raw 對 parsed 的落差。"""
    telemetry = {"http_status": 200, "vendor_status": "ok",
                "vendor_errmsg": None, "raw_rows": 5,
                "parsed_call_rows": 0, "parsed_put_rows": 0}
    client = _client(db, surface=_telemetry_surface(telemetry))
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _prefill_all_but_one(db)
    body = _get(client, sid, key).json()

    parse_events = _events_for(body, "payload_parse")
    assert parse_events, "至少要有一筆 payload_parse 事件"
    assert parse_events[0]["severity"] == "warning"
    assert parse_events[0]["context"]["raw_rows"] == 5
    assert parse_events[0]["context"]["parsed_call_rows"] == 0
    assert parse_events[0]["context"]["parsed_put_rows"] == 0

    fetch_events = _events_for(body, "vendor_fetch")
    assert fetch_events[0]["context"]["raw_rows"] == 5
    assert fetch_events[0]["severity"] == "info"   # vendor 本身回 s=ok，沒有失敗


def test_no_data_is_a_warning_and_does_not_abort_the_batch(db):
    """s="no_data" 是帶 expiration 篩選後的正常撲空（#134 既有語意）——
    不該讓批次中止在第一天。"""
    telemetry = {"http_status": 200, "vendor_status": "no_data",
                "vendor_errmsg": None, "raw_rows": 0,
                "parsed_call_rows": 0, "parsed_put_rows": 0}
    calls: list[str] = []
    client = _client(db, surface=_telemetry_surface(telemetry, call_counter=calls))
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    fetch_events = _events_for(body, "vendor_fetch")
    assert fetch_events and all(e["severity"] == "warning" for e in fetch_events)
    assert len(calls) > 1, "no_data 不該讓 backfill 在第一天就中止"

    backfill_summary = _events_for(body, "backfill")
    assert backfill_summary[0]["context"]["outcome"] == "ok"
    assert "aborted_on" not in backfill_summary[0]["context"]


def test_backfill_abort_is_visible_in_the_summary_event(db):
    """既有行為（第一次失敗就中止整批）本輪不修，只要求它現在看得見。"""
    rec = Recorder(fail=QuotaExhausted("額度用完"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    summary = _events_for(body, "backfill")
    assert len(summary) == 1
    assert summary[0]["severity"] == "warning"
    assert summary[0]["context"]["outcome"] == "quota"
    assert summary[0]["context"]["aborted_on"]
    assert summary[0]["context"]["abort_reason"] == "quota"
    assert summary[0]["context"]["attempted_days"] == 1
    assert summary[0]["context"]["saved_days"] == 0


def test_vendor_fetch_event_carries_http_status_and_rate_limit_fields(db):
    telemetry = {"http_status": 429, "vendor_status": None,
                "vendor_errmsg": None, "raw_rows": 0,
                "parsed_call_rows": 0, "parsed_put_rows": 0,
                "X-Api-Ratelimit-Remaining": "0",
                "X-Api-Ratelimit-Limit": "100"}
    client = _client(db, surface=_telemetry_surface(telemetry))
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    fetch_events = _events_for(body, "vendor_fetch")
    assert fetch_events[0]["severity"] == "error"
    assert fetch_events[0]["context"]["http_status"] == 429
    assert fetch_events[0]["context"]["X-Api-Ratelimit-Remaining"] == "0"
    assert fetch_events[0]["context"]["X-Api-Ratelimit-Limit"] == "100"
    # vendor_status 是 None（連 payload 都沒有）——依 sanitize_context
    # 的規則，None 值不進 context，這裡確認畫面上不會出現一個空欄位。
    assert "vendor_status" not in fetch_events[0]["context"]


def test_response_correlation_id_matches_the_header(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    resp = _get(client, sid, _candidate_key(client, sid))
    body = resp.json()
    assert body["diagnostics"]["correlation_id"] == resp.headers["X-Correlation-Id"]


def test_events_shown_in_the_response_also_land_in_the_diagnostics_store(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    shown_ids = {e["event_id"] for e in body["diagnostics"]["events"]}
    # HIVR-03（#162）：exact-contract 與 legacy 兩個 subsystem 各自享有
    # 一份完整的 per-request 保留名額，一次 request 因此可能寫進去超過
    # `/api/diagnostics` 預設的 `limit=50`——這裡明確拉高查詢上限到
    # `RETENTION_LIMIT`，只是為了讓比較涵蓋到這次 request 實際寫進去的
    # 全部事件，斷言本身（`shown_ids <= stored_ids`）不變、不放鬆。
    stored_ids = {e["event_id"]
                 for e in client.get("/api/diagnostics?limit=200").json()}
    assert shown_ids <= stored_ids


def test_a_known_token_never_appears_in_diagnostics(db):
    """紅線：vendor 把 token 夾在 errmsg 裡回來，一樣不得逐字出現在
    任何 diagnostic event 或 API 回應裡。"""
    telemetry = {"http_status": 200, "vendor_status": "error",
                "vendor_errmsg": f"invalid key {TOKEN}",
                "raw_rows": 0, "parsed_call_rows": 0, "parsed_put_rows": 0}
    client = _client(db, surface=_telemetry_surface(telemetry))
    _unlock(client)
    sid = _scenario(client)
    resp = _get(client, sid, _candidate_key(client, sid))
    assert TOKEN not in resp.text
    stored = client.get("/api/diagnostics").json()
    assert all(TOKEN not in str(e) for e in stored)


def test_full_vendor_response_body_never_reaches_any_diagnostic_event(db):
    """`_emit_surface_telemetry()` 用具名關鍵字組 event context——即使
    observer 給的 telemetry dict 意外多帶一個完整回應內容的欄位（例如
    未來 `marketdata.py` 不小心多回傳一個 `raw_body`），main.py 這一層
    因為不是 `**telemetry` 全展開，那個欄位天生就進不了任何診斷事件。"""
    huge_marker = "RAW_VENDOR_BODY_" + ("z" * 2000)
    telemetry = {"http_status": 200, "vendor_status": "ok",
                "vendor_errmsg": None, "raw_rows": 1,
                "parsed_call_rows": 1, "parsed_put_rows": 0,
                # 模擬「不小心多帶了完整回應內容」——main.py 不該把它
                # 轉發進任何 emit() 呼叫。
                "raw_body": huge_marker}
    client = _client(db, surface=_telemetry_surface(
        telemetry, points={"call": [SurfacePoint(dte=30, delta=0.4, iv=0.2)],
                           "put": []}))
    _unlock(client)
    sid = _scenario(client)
    resp = _get(client, sid, _candidate_key(client, sid))
    assert huge_marker not in resp.text
    assert huge_marker not in client.get("/api/diagnostics").text


def test_diagnostics_storage_failure_does_not_break_the_response():
    """診斷絕不能成為新的故障源——storage 的 `append_diagnostic` 掛了，
    iv-history 端點照樣回它原本該回的東西。"""
    from api_app.storage.memory import MemoryStorage

    class _Wrapped(MemoryStorage):
        def append_diagnostic(self, event):
            raise RuntimeError("db 掛了")

    wrapped = _Wrapped()
    client = _client(wrapped, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    resp = _get(client, sid, _candidate_key(client, sid))
    assert resp.status_code == 200
    assert resp.json()["normalized_skew_points"]


# ---------- per-request 排放量控制（#146） ----------

def test_error_and_warning_events_survive_the_per_request_cap():
    from api_app.diagnostics import DiagnosticEvent
    from api_app.main import (_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST,
                              _select_for_persistence)

    def ev(event_id, severity="info", stage="vendor_fetch"):
        return DiagnosticEvent(event_id=event_id, correlation_id="c",
                               ts=event_id, subsystem="historical_iv",
                               stage=stage, severity=severity, message="m")

    # 事件數要真的超過 cap 才測到取捨——HIVT-03 起 cap 已提高
    # （容納新家族每腿 5 筆統計量事件），數量要跟著這個常數走，不能寫死
    # 舊的 20，否則 cap 一旦再調整這條測試就會安靜地失去意義。
    total = _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST + 5
    events = [ev(f"info{i}") for i in range(total - 5)]
    events += [ev(f"err{i}", severity="error") for i in range(5)]
    kept = _select_for_persistence(events)
    assert len(kept) <= _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST
    kept_ids = {e.event_id for e in kept}
    assert all(f"err{i}" in kept_ids for i in range(5))


def test_the_batch_summary_event_survives_the_cap_even_when_priority_events_alone_overflow_it():
    """摘要不是跟其他 priority 事件搶名額——即使 error/warning 本身就
    塞滿整個 cap，摘要仍然保留（見 `_select_for_persistence` 三層優先序
    的第一層）。"""
    from api_app.diagnostics import DiagnosticEvent
    from api_app.main import (_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST,
                              _select_for_persistence)

    def ev(event_id, severity="info", stage="vendor_fetch"):
        return DiagnosticEvent(event_id=event_id, correlation_id="c",
                               ts=event_id, subsystem="historical_iv",
                               stage=stage, severity=severity, message="m")

    events = [ev(f"err{i}", severity="error")
             for i in range(_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST + 10)]
    events += [ev("summary", stage="backfill")]
    kept = _select_for_persistence(events)
    assert "summary" in {e.event_id for e in kept}
    assert len(kept) <= _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST


def test_under_the_cap_nothing_is_dropped():
    from api_app.diagnostics import DiagnosticEvent
    from api_app.main import _select_for_persistence

    events = [DiagnosticEvent(event_id=f"e{i}", correlation_id="c", ts=f"t{i}",
                              subsystem="historical_iv", stage="cache",
                              severity="info", message="m") for i in range(5)]
    assert _select_for_persistence(events) == events


def test_metrics_events_also_survive_the_cap_alongside_backfill():
    """兩個彙總 stage（`backfill`／`metrics`）都不跟高流量的逐日事件
    搶名額——這是 DG-04 在既有 DG-03 排放量控制上追加的保留規則。"""
    from api_app.diagnostics import DiagnosticEvent
    from api_app.main import _select_for_persistence

    def ev(event_id, stage="reanchor"):
        return DiagnosticEvent(event_id=event_id, correlation_id="c",
                               ts=event_id, subsystem="historical_iv",
                               stage=stage, severity="info", message="m")

    events = [ev(f"r{i}") for i in range(70)]
    events += [ev("m1", stage="metrics"), ev("m2", stage="metrics"),
              ev("bf", stage="backfill")]
    kept_ids = {e.event_id for e in _select_for_persistence(events)}
    assert {"m1", "m2", "bf"} <= kept_ids


# ---------- Diagnostics subsystem 拆分（HIVR-03／#162） ----------

def test_a_flood_of_legacy_events_does_not_starve_exact_contract_events():
    """load-bearing 保證：exact-contract 與 legacy 重錨定各自有獨立的
    保留預算——單一 request 裡塞進大量 legacy 事件，不得把為數不多的
    exact-contract 事件擠出保留名額（本票存在的理由，spec #159 AC）。"""
    from api_app.diagnostics import (SUBSYSTEM_EXACT_CONTRACT,
                                     SUBSYSTEM_LEGACY_REANCHOR, DiagnosticEvent)
    from api_app.main import (_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST,
                              _select_for_persistence)

    def ev(event_id, subsystem, severity="info"):
        return DiagnosticEvent(event_id=event_id, correlation_id="c",
                               ts=event_id, subsystem=subsystem,
                               stage="vendor_fetch", severity=severity,
                               message="m")

    exact_events = [ev(f"exact{i}", SUBSYSTEM_EXACT_CONTRACT) for i in range(6)]
    # legacy 家族的事件量遠超過共用上限本身——這正是 legacy 會結構性
    # 隨快照數持續成長、單一共用上限遲早再度被淹沒的那個問題。
    legacy_events = [ev(f"legacy{i}", SUBSYSTEM_LEGACY_REANCHOR)
                     for i in range(_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST * 3)]

    kept_ids = {e.event_id for e in _select_for_persistence(
        exact_events + legacy_events)}

    assert {e.event_id for e in exact_events} <= kept_ids, (
        "大量 legacy 事件擠掉了 exact-contract 事件——保留預算沒有真的獨立")


def test_each_subsystem_independently_respects_the_same_cap():
    """兩個 subsystem 各自的保留名額都是完整一份 `cap`（不是均分），
    但**各自**仍然受同一個 cap 限制——不是「拆開後上限形同虛設」。"""
    from api_app.diagnostics import (SUBSYSTEM_EXACT_CONTRACT,
                                     SUBSYSTEM_LEGACY_REANCHOR, DiagnosticEvent)
    from api_app.main import (_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST,
                              _select_for_persistence)

    def ev(event_id, subsystem):
        return DiagnosticEvent(event_id=event_id, correlation_id="c",
                               ts=event_id, subsystem=subsystem,
                               stage="vendor_fetch", severity="info",
                               message="m")

    over = _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST + 10
    exact_events = [ev(f"exact{i}", SUBSYSTEM_EXACT_CONTRACT) for i in range(over)]
    legacy_events = [ev(f"legacy{i}", SUBSYSTEM_LEGACY_REANCHOR) for i in range(over)]

    kept = _select_for_persistence(exact_events + legacy_events)
    kept_exact = [e for e in kept if e.subsystem == SUBSYSTEM_EXACT_CONTRACT]
    kept_legacy = [e for e in kept if e.subsystem == SUBSYSTEM_LEGACY_REANCHOR]

    assert len(kept_exact) <= _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST
    assert len(kept_legacy) <= _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST
    # 兩個家族各自都真的被單獨的洪水塞滿了自己的名額——不是意外地兩邊
    # 都留了個位數，掩蓋了本該測到的「各自獨立」這件事。
    assert len(kept_exact) == _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST
    assert len(kept_legacy) == _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST


def test_the_shared_cap_constant_itself_is_not_raised_by_the_split():
    """AC 明文：這次改動不得把共用上限本身調高——結構性解法是拆
    subsystem，不是繼續調高同一個數字（20→40 已經做過一次）。"""
    from api_app.main import _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST
    assert _DIAGNOSTICS_STORAGE_CAP_PER_REQUEST == 40


def test_exact_contract_and_legacy_reanchor_are_distinct_named_subsystems():
    from api_app.diagnostics import (SUBSYSTEM_EXACT_CONTRACT,
                                     SUBSYSTEM_LEGACY_REANCHOR, SUBSYSTEMS)
    assert SUBSYSTEM_EXACT_CONTRACT != SUBSYSTEM_LEGACY_REANCHOR
    assert SUBSYSTEM_EXACT_CONTRACT in SUBSYSTEMS
    assert SUBSYSTEM_LEGACY_REANCHOR in SUBSYSTEMS


def test_a_heavy_backfill_still_leaves_exact_contract_events_in_the_live_response(db):
    """端到端版本（走真的 endpoint，不是直接呼叫 `_select_for_persistence`）：
    一次請求觸發滿載的 legacy backfill（`_IV_BACKFILL_PER_RUN` 天，每天
    vendor_fetch／payload_parse／database_write／reanchor 多筆，遠超過
    共用上限），exact-contract 家族的 `candidate_lookup`／`metrics` 事件
    仍然要完整出現在這次 response 的 diagnostics 裡——不是只有純函式層
    測得到，使用者實際看到的回應也要保得住。`_telemetry_surface`（不是
    `_rich_surface`）才會真的呼叫 observer、把 telemetry 轉成事件，藉此
    讓 backfill 迴圈跑滿整批，重現過去會把 exact-contract 事件擠出保留
    名額的那個量級。"""
    from api_app.diagnostics import (SUBSYSTEM_EXACT_CONTRACT,
                                     SUBSYSTEM_LEGACY_REANCHOR)

    telemetry = {"http_status": 200, "vendor_status": "ok",
                "vendor_errmsg": None, "raw_rows": 3,
                "parsed_call_rows": 1, "parsed_put_rows": 1}
    client = _client(db, surface=_telemetry_surface(telemetry))
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    events = body["diagnostics"]["events"]
    exact = [e for e in events if e["subsystem"] == SUBSYSTEM_EXACT_CONTRACT]
    legacy = [e for e in events if e["subsystem"] == SUBSYSTEM_LEGACY_REANCHOR]

    # legacy backfill 這次確實跑滿（沒有預先灌好資料），觸發大量事件——
    # 驗證測試場景本身真的踩到過去會擠掉 exact-contract 事件的那個量級。
    assert len(legacy) >= 20
    # exact-contract 家族的關鍵事件完整保留，不受 legacy 洪水影響。
    assert any(e["stage"] == "candidate_lookup" for e in exact)
    assert any(e["stage"] == "metrics" for e in exact)


# ---------- Historical IV 投影路徑觀測（DG-04／#147） ----------
#
# `reanchor`／`metrics` 兩站——「資料明明有、畫面卻空白」唯一看得見的
# 地方。用 `_mark_backfill_done_today` 讓 backfill 短路（不碰 vendor），
# 直接手灌少量觀測到快取，讓每個測試只驗一件事，不被高流量的 backfill
# 迴圈本身淹沒。

def _mark_backfill_done_today(db, symbol="XYZ"):
    from api_app.storage import IvBackfillRun
    db.save_iv_backfill_run(
        IvBackfillRun(symbol=symbol, ran_on=ny_today().isoformat(), outcome="ok"))


def _seed_days(db, days_and_points, symbol="XYZ"):
    from api_app.main import _surface_to_rows
    from api_app.storage import IvObservation

    for day, pts in days_and_points:
        db.save_iv_observation(IvObservation(
            symbol=symbol, observed_on=day,
            surface=_surface_to_rows({"call": pts, "put": pts}),
            fetched_at="2026-08-12T00:00:00+00:00"))


_NARROW_GRID = [SurfacePoint(dte=d, delta=x, iv=0.2)
               for d in (1, 5) for x in (0.4, 0.5, 0.6)]


def test_reanchor_event_marks_an_out_of_grid_day_as_warning(db):
    """曲面有資料，但候選要查的座標不在網格範圍內——這正是「連線成功
    但沒資料」那一類失敗，本函式讓它變成看得見的事實。"""
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _NARROW_GRID)])

    body = _get(client, sid, key).json()
    got = _events_for(body, "reanchor")
    assert len(got) == 1
    assert got[0]["severity"] == "warning"
    assert got[0]["context"]["observed_on"] == "2026-05-01"
    assert got[0]["context"]["surface_dte_min"] == 1
    assert got[0]["context"]["surface_dte_max"] == 5
    assert got[0]["context"]["buy_iv_null"] is True


def test_reanchor_event_is_info_when_the_grid_covers_the_candidate(db):
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _grid()["call"])])

    body = _get(client, sid, key).json()
    got = _events_for(body, "reanchor")
    assert len(got) == 1
    assert got[0]["severity"] == "info"
    assert got[0]["context"]["buy_iv_null"] is False


def test_single_leg_reanchor_is_not_penalized_for_the_missing_sell_leg(db):
    """Long Call 結構上沒有賣腿——`sell_iv`／`normalized_skew` 恆為 None
    不是資料品質問題，不該讓每一個單腳候選永遠亮 warning。"""
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _grid()["call"])])

    body = _get(client, sid, key).json()
    got = _events_for(body, "reanchor")
    assert len(got) == 1
    assert got[0]["severity"] == "info"
    assert got[0]["context"]["sell_iv_null"] is True
    assert got[0]["context"]["normalized_skew_null"] is True
    assert "sell_delta" not in got[0]["context"]


_REANCHORED_METRIC_FIELDS = {"normalized_skew", "buy_iv", "sell_iv", "atm_iv"}


def _reanchored_metrics_by_field(body):
    """`metrics` stage 現在被舊 (tenor,delta) 家族與新 exact-contract
    家族（HIVT-03／#154，每腿再加 5 筆統計量事件）共用——只挑舊家族
    自己的欄位名稱，兩個家族的事件才不會混在一起斷言。"""
    return {e["context"]["field"]: e for e in _events_for(body, "metrics")
            if e["context"]["field"] in _REANCHORED_METRIC_FIELDS}


def test_metrics_events_are_info_when_data_is_available(db):
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _grid()["call"])])

    body = _get(client, sid, key).json()
    by_field = _reanchored_metrics_by_field(body)
    assert set(by_field) == {"normalized_skew", "buy_iv", "sell_iv", "atm_iv"}
    assert all(e["severity"] == "info" for e in by_field.values())
    assert all(e["context"]["count"] > 0 for e in by_field.values())


def test_metrics_events_flag_zero_count_fields_as_warning(db):
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _NARROW_GRID)])

    body = _get(client, sid, key).json()
    by_field = {e["context"]["field"]: e for e in _events_for(body, "metrics")}
    assert all(e["severity"] == "warning" for e in by_field.values())
    assert all(e["context"]["count"] == 0 for e in by_field.values())


def test_single_leg_metrics_do_not_flag_the_structurally_absent_fields(db):
    client = _client(db, surface=_surface_never_called)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)
    _mark_backfill_done_today(db)
    _seed_days(db, [("2026-05-01", _grid()["call"])])

    body = _get(client, sid, key).json()
    fields = set(_reanchored_metrics_by_field(body))
    assert fields == {"buy_iv", "atm_iv"}


def test_the_full_ledger_covers_every_stage_and_shares_one_correlation_id(db):
    """DG-04 的核心交付：同一個 correlation_id 的 events 依序讀完，八站
    的進與出都在——這就是「vendor 回 N 筆，究竟在哪一站變成 0 筆」的
    完整帳本，不需要讀程式碼。"""
    telemetry = {"http_status": 200, "vendor_status": "ok",
                "vendor_errmsg": None, "raw_rows": 5,
                "parsed_call_rows": 0, "parsed_put_rows": 0}
    client = _client(db, surface=_telemetry_surface(telemetry))
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    _prefill_all_but_one(db)
    body = _get(client, sid, key).json()

    stages_seen = {e["stage"] for e in body["diagnostics"]["events"]}
    assert stages_seen == {"candidate_lookup", "cache", "vendor_fetch",
                           "payload_parse", "database_write", "backfill",
                           "reanchor", "metrics"}
    cids = {e["correlation_id"] for e in body["diagnostics"]["events"]}
    assert cids == {body["diagnostics"]["correlation_id"]}

    # 帳本本身：vendor 回 5 筆原始資料，payload_parse 站砍成 0 筆——
    # 光看這一筆事件就回答得出「哪一站」，不需要讀程式碼。
    parse = _events_for(body, "payload_parse")[0]
    assert parse["context"]["raw_rows"] == 5
    assert parse["context"]["parsed_call_rows"] == 0
    assert parse["context"]["parsed_put_rows"] == 0


# ---------- Exact-contract 逐腿歷史 IV（HIVT-02／#153） ----------
#
# 跟上面整份檔案的 (tenor, delta) 重錨定家族完全獨立：這裡只測
# `legs` 這個新增欄位，既有 `points`／`metrics`／`status` 家族的行為
# 由上面既有測試覆蓋、本節不重複。

class ContractHistoryRecorder:
    """記錄每一次呼叫的 (occ_symbol, from_date, to_date)——跟舊 `Recorder`
    對 `_backfill_iv` 的角色對應，只是這裡一次呼叫代表一段區間，不是
    一天。"""

    def __init__(self, points_by_symbol=None, fail=None):
        self.calls: list[tuple[str, str, str]] = []
        self._points_by_symbol = points_by_symbol or {}
        self._fail = fail

    def __call__(self, provider, occ_symbol, from_date, to_date, token,
                observer=None):
        self.calls.append((occ_symbol, from_date, to_date))
        if observer is not None:
            observer({"vendor_status": "ok", "vendor_errmsg": None,
                      "http_status": 203, "raw_rows": 0, "parsed_rows": 0,
                      "null_iv_count": 0, "dropped_missing_date": 0})
        if self._fail is not None:
            raise self._fail
        return self._points_by_symbol.get(occ_symbol, [])


def _leg_symbols(client, sid, key):
    """借用 `_candidate_key` 同樣的走訪路徑，換成回傳這個候選兩條腿
    （或單腳只有一條）的 OCC contract symbol。"""
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for c in g["candidates"]:
                if c["candidate_key"] == key:
                    return [leg["contract_symbol"] for leg in c["legs"]]
    raise AssertionError("找不到這個候選")


def test_legs_field_carries_buy_and_sell_for_a_two_leg_spread(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    body = _get(client, sid, key).json()

    assert set(body["legs"]) == {"buy", "sell"}
    for leg_key in ("buy", "sell"):
        leg = body["legs"][leg_key]
        assert leg["contract"]["contract_symbol"]
        assert leg["contract"]["underlying"] == "XYZ"
        assert leg["status"] == "ok"
        assert leg["points"] == []


def test_legs_field_omits_the_sell_key_entirely_for_a_single_leg_candidate(db):
    """單腳候選只有買腿——`sell` 這個 key 整個不存在，不是設成 None
    （跟舊家族 `sell_iv`／`normalized_skew` 恆 None 的呈現方式刻意不同：
    這裡沒有賣腿是結構性的事實，不該讓前端多寫一個「存在但是 None」的
    分支）。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)

    body = _get(client, sid, key).json()
    assert set(body["legs"]) == {"buy"}


def test_exact_contract_isolation_different_strikes_never_cross_contaminate(db):
    """紅線：不同履約價是不同的歷史序列，即使 vendor 假體對哪個 symbol
    給哪組資料完全不重疊，兩條腿也各自拿到自己的那組、不會互相污染。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, sell_symbol = _leg_symbols(client, sid, key)
    assert buy_symbol != sell_symbol

    rec = ContractHistoryRecorder(points_by_symbol={
        buy_symbol: [("2026-07-01", 0.30)],
        sell_symbol: [("2026-07-01", 0.55)],
    })
    client2 = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client2)
    body = _get(client2, sid, key).json()

    assert body["legs"]["buy"]["points"] == [{"date": "2026-07-01", "iv": 0.30}]
    assert body["legs"]["sell"]["points"] == [{"date": "2026-07-01", "iv": 0.55}]


def test_variable_length_history_under_a_year_is_reported_as_is_not_padded(db):
    """合約只上市三天，回應就是三天——不補到一年份的空白點。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    rec._points_by_symbol[buy_symbol] = [
        ("2026-08-10", 0.20), ("2026-08-11", 0.21), ("2026-08-12", 0.22)]

    body = _get(client, sid, key).json()
    assert len(body["legs"]["buy"]["points"]) == 3
    assert body["legs"]["buy"]["observation_count"] == 3
    assert body["legs"]["buy"]["history_span_days"] == 2


def test_history_older_than_365_days_is_trimmed_out_of_the_response(db):
    today = ny_today()
    old_date = (today - timedelta(days=400)).isoformat()
    recent_date = (today - timedelta(days=1)).isoformat()

    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    rec._points_by_symbol[buy_symbol] = [(old_date, 0.5), (recent_date, 0.25)]

    body = _get(client, sid, key).json()
    dates = [p["date"] for p in body["legs"]["buy"]["points"]]
    assert old_date not in dates
    assert recent_date in dates


def test_null_iv_points_are_preserved_in_the_response_never_dropped_or_zeroed(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    rec._points_by_symbol[buy_symbol] = [
        ("2026-08-10", None), ("2026-08-11", None), ("2026-08-12", 0.22)]

    body = _get(client, sid, key).json()
    points = {p["date"]: p["iv"] for p in body["legs"]["buy"]["points"]}
    assert points["2026-08-10"] is None
    assert points["2026-08-11"] is None
    assert points["2026-08-12"] == 0.22
    # observation_count 只算非 None——null 是缺席觀測，不是「值是 0」。
    assert body["legs"]["buy"]["observation_count"] == 1


def test_missing_calendar_days_are_not_interpolated(db):
    """vendor 只回真實交易日——中間跳過的日子不補值，序列本身就是
    那幾個離散的日期，不是逐日連續。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    rec._points_by_symbol[buy_symbol] = [("2026-08-03", 0.20), ("2026-08-07", 0.24)]

    body = _get(client, sid, key).json()
    dates = [p["date"] for p in body["legs"]["buy"]["points"]]
    assert dates == ["2026-08-03", "2026-08-07"]


def test_a_vendor_error_on_the_exact_contract_path_still_returns_cached_points(db):
    """今天這次嘗試失敗，不代表先前快取的觀測就消失——跟舊家族
    `_backfill_iv` 的既有紅線（#133）是同一條原則，搬到 exact-contract
    家族。"""
    seed = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=seed)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    seed._points_by_symbol[buy_symbol] = [("2026-08-01", 0.20)]
    first = _get(client, sid, key).json()
    assert first["legs"]["buy"]["points"] == [{"date": "2026-08-01", "iv": 0.20}]

    # 清掉「今天已嘗試過」，讓下一次真的再打一次 vendor、這次失敗。
    cached = db.get_contract_history(buy_symbol)
    db.save_contract_history(ContractHistory(
        contract_symbol=cached.contract_symbol, points=cached.points,
        fetched_through=cached.fetched_through, last_attempt_on="1900-01-01",
        last_status=cached.last_status, last_note=cached.last_note))

    failing = ContractHistoryRecorder(fail=FetchError("連線逾時"))
    client2 = _client(db, surface=_rich_surface, contract_history=failing)
    _unlock(client2)
    second = _get(client2, sid, key).json()

    assert second["legs"]["buy"]["status"] == "vendor"
    assert second["legs"]["buy"]["points"] == [{"date": "2026-08-01", "iv": 0.20}]


def test_repeating_the_same_day_request_costs_zero_vendor_calls(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)

    _get(client, sid, key)
    after_first = len(rec.calls)
    assert after_first > 0
    _get(client, sid, key)
    _get(client, sid, key)
    assert len(rec.calls) == after_first


def test_incremental_refresh_only_requests_the_gap_since_fetched_through(db):
    """第二天再打，`from` 該是上次 `fetched_through` 的隔天，不是又從
    365 天前整年重抓。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)

    _get(client, sid, key)
    first_call = next(c for c in rec.calls if c[0] == buy_symbol)
    today = ny_today()
    assert first_call[1] == \
        (today - timedelta(days=ivtrend.IV_TREND_MAX_HISTORY_DAYS)).isoformat()

    # 讓「今天已嘗試過」的閘打開，模擬隔天再打一次。
    cached = db.get_contract_history(buy_symbol)
    db.save_contract_history(ContractHistory(
        contract_symbol=cached.contract_symbol, points=cached.points,
        fetched_through=cached.fetched_through, last_attempt_on="1900-01-01",
        last_status=cached.last_status, last_note=cached.last_note))
    rec.calls.clear()

    _get(client, sid, key)
    second_call = next(c for c in rec.calls if c[0] == buy_symbol)
    expected_from = (date.fromisoformat(cached.fetched_through) +
                     timedelta(days=1)).isoformat()
    assert second_call[1] == expected_from


def test_exact_contract_diagnostics_never_leak_the_token(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    resp = _get(client, sid, key)
    assert TOKEN not in resp.text
    stored = client.get("/api/diagnostics").json()
    assert all(TOKEN not in str(e) for e in stored)


def test_exact_contract_cache_events_carry_the_new_whitelisted_context_fields(db):
    """issue #153 明文要求每一站都 emit「帶有 exact contract identity」
    的事件——不能只有可以反解的 `contract_symbol`（OCC symbol），
    underlying／expiration／strike／option_type 四項本身也要在場，
    不必反解字串就看得懂這是哪張合約。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    body = _get(client, sid, key).json()

    # `cache`／`vendor_fetch`／`database_write` 三站都被舊 (tenor,delta)
    # 家族與新 exact-contract 家族共用同一個 stage 名稱（spec #151 §5
    # 刻意如此設計）——只挑帶 `contract_symbol` 的那些，這是新家族的
    # 事件才有的欄位。
    cache_events = [e for e in _events_for(body, "cache")
                    if "contract_symbol" in e["context"]]
    assert cache_events
    for e in cache_events:
        assert set(e["context"]) >= {"contract_symbol", "underlying",
                                     "expiration", "strike", "option_type"}
    assert any("requested_from" in e["context"] and "requested_to" in e["context"]
              for e in cache_events)

    vendor_fetch_events = [e for e in _events_for(body, "vendor_fetch")
                           if "contract_symbol" in e["context"]]
    assert vendor_fetch_events
    for e in vendor_fetch_events:
        assert set(e["context"]) >= {"contract_symbol", "underlying",
                                     "expiration", "strike", "option_type"}

    database_write_events = [e for e in body["diagnostics"]["events"]
                             if e["stage"] == "database_write"
                             and "contract_symbol" in e["context"]]
    assert database_write_events
    for e in database_write_events:
        assert set(e["context"]) >= {"contract_symbol", "underlying",
                                     "expiration", "strike", "option_type"}


# ---------- 統計量套組（HIVT-03／#154） ----------
#
# `points_by_symbol` 用連續日曆天灌值，方便手算對照——跟
# `test_ivtrend.py` 的策略相同，這裡額外驗證的是「main.py 有沒有正確把
# ivtrend.py 的輸出接進 `legs` 回應」，不重覆測純函式本身的邊界案例
# （那是 test_ivtrend.py 的範圍）。

def _consecutive_days(end, n, ivs):
    from datetime import timedelta as _td
    start = end - _td(days=n - 1)
    return [((start + _td(days=i)).isoformat(), iv) for i, iv in enumerate(ivs)]


def test_leg_response_carries_the_full_hivt03_stat_shape(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    today = ny_today()
    rec._points_by_symbol[buy_symbol] = _consecutive_days(
        today, 6, [0.10, 0.11, 0.12, 0.13, 0.14, 0.15])

    body = _get(client, sid, key).json()
    buy = body["legs"]["buy"]
    assert set(buy) >= {"contract", "points", "moving_average",
                        "bollinger_upper", "bollinger_lower",
                        "current_percentile", "current_zscore", "delta_4w",
                        "observation_count", "history_span_days",
                        "lookback_days_config", "status", "note"}
    assert buy["lookback_days_config"] == ivtrend.IV_TREND_LOOKBACK_DAYS


def test_stats_are_unavailable_below_the_minimum_observation_count(db):
    """低於 `IV_TREND_MIN_OBSERVATIONS_FOR_BANDS`（5）：moving_average／
    bollinger／current_zscore 各自回報 unavailable，percentile／
    Δ4w／原始走勢圖照常渲染——不是整張卡片一起消失。"""
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    today = ny_today()
    rec._points_by_symbol[buy_symbol] = _consecutive_days(
        today, 3, [0.10, 0.11, 0.12])

    body = _get(client, sid, key).json()
    buy = body["legs"]["buy"]
    assert buy["moving_average"][-1]["value"] is None
    assert buy["bollinger_upper"][-1]["value"] is None
    assert buy["bollinger_lower"][-1]["value"] is None
    assert buy["current_zscore"] is None
    # 原始走勢圖與百分位不受最低觀測門檻影響
    assert len(buy["points"]) == 3
    assert buy["current_percentile"] is not None


def test_stats_become_available_once_enough_observations_exist(db):
    from statistics import mean, stdev

    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    today = ny_today()
    ivs = [0.10, 0.12, 0.14, 0.16, 0.18]
    rec._points_by_symbol[buy_symbol] = _consecutive_days(today, 5, ivs)

    body = _get(client, sid, key).json()
    buy = body["legs"]["buy"]
    m, s = mean(ivs), stdev(ivs)
    assert buy["moving_average"][-1]["value"] == pytest.approx(m)
    assert buy["bollinger_upper"][-1]["value"] == pytest.approx(m + 2 * s)
    assert buy["bollinger_lower"][-1]["value"] == pytest.approx(m - 2 * s)
    assert buy["current_zscore"] == pytest.approx((ivs[-1] - m) / s)


def test_percentile_has_no_minimum_gate_at_the_endpoint_level(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    today = ny_today()
    rec._points_by_symbol[buy_symbol] = [(today.isoformat(), 0.20)]

    body = _get(client, sid, key).json()
    assert body["legs"]["buy"]["current_percentile"] == 1.0


def test_delta_4w_is_none_without_a_baseline_window_observation(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    buy_symbol, _sell = _leg_symbols(client, sid, key)
    today = ny_today()
    # 全部落在 [today-42, today-21] 窗口之外（只有最近幾天）
    rec._points_by_symbol[buy_symbol] = _consecutive_days(
        today, 5, [0.10, 0.12, 0.14, 0.16, 0.18])

    body = _get(client, sid, key).json()
    assert body["legs"]["buy"]["delta_4w"] is None


def test_metrics_stage_emits_one_event_per_statistic_for_each_leg(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    body = _get(client, sid, key).json()

    stat_fields = {"moving_average", "bollinger_bands", "current_zscore",
                   "historical_percentile", "delta_4w"}
    seen = {e["context"]["field"] for e in _events_for(body, "metrics")
            if e["context"]["field"] in stat_fields}
    assert seen == stat_fields


def test_moving_average_and_bollinger_are_the_only_new_events_carrying_lookback_days(db):
    rec = ContractHistoryRecorder()
    client = _client(db, surface=_rich_surface, contract_history=rec)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)
    body = _get(client, sid, key).json()

    for e in _events_for(body, "metrics"):
        if e["context"]["field"] in ("moving_average", "bollinger_bands",
                                     "current_zscore"):
            assert e["context"]["lookback_days"] == ivtrend.IV_TREND_LOOKBACK_DAYS
        elif e["context"]["field"] in ("historical_percentile", "delta_4w"):
            assert "lookback_days" not in e["context"]
