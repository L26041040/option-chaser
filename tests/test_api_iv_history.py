"""Historical IV 端點與模組閘門（#126）。

最重要的一條不是「算得對」，而是**鎖著的時候一個請求都不發**——
`historical_surface` 注入一個會 assert 失敗的假體，任何偷跑都會紅燈。
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage import IvBackfillRun, IvObservation
from api_app.storage.memory import MemoryStorage
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

    def __call__(self, provider, symbol, on_date, token, expiration=None):
        self.calls.append((symbol, on_date))
        if self._fail is not None:
            raise self._fail
        return _grid()

    @property
    def dates(self):
        return [d for _, d in self.calls]


def _client(db, *, surface=_surface_never_called):
    return TestClient(create_app(
        storage=db, fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=surface))


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
    """序列的每一點對應快取裡的一天觀測，在候選自己的座標上重新插值。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    cached = db.iv_observation_dates("XYZ")
    assert [p["date"] for p in body["points"]] == cached
    assert body["metrics"]["normalized_skew"]["value"] is not None


def test_series_carries_both_legs_and_the_atm_level(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    point = _get(client, sid, _candidate_key(client, sid)).json()["points"][0]
    assert set(point) >= {"date", "buy_iv", "sell_iv", "atm_iv",
                          "normalized_skew"}


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
    for field in ("normalized_skew", "buy_iv", "sell_iv"):
        assert metrics[field]["percentile"] is not None
        assert metrics[field]["count"] > 0


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


def test_a_long_call_candidate_has_buy_and_atm_but_no_sell_or_skew(db):
    """買腿 IV／ATM IV 有值；賣腿 IV／Normalized Skew 誠實回沒有這個量
    （`count == 0`），不是新的錯誤狀態。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key, view = _long_call_candidate_key_and_view(client)
    _attach_result(db, sid, view)
    _prefill(db)

    body = _get(client, sid, key).json()
    assert body["metrics"]["buy_iv"]["count"] > 0
    assert body["metrics"]["buy_iv"]["value"] is not None
    assert body["metrics"]["atm_iv"]["count"] > 0

    assert body["metrics"]["sell_iv"] == \
        {"value": None, "percentile": None, "count": 0,
         "trend_4w": None, "trend_base_count": 0}
    assert body["metrics"]["normalized_skew"] == \
        {"value": None, "percentile": None, "count": 0,
         "trend_4w": None, "trend_base_count": 0}
    assert all(p["sell_iv"] is None and p["normalized_skew"] is None
              for p in body["points"])


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
    bull-call-spread 候選）行為與數值完全不因這次修改而變。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    key = _candidate_key(client, sid)   # Scenario 流程目前只有 spread 候選
    _prefill(db)
    body = _get(client, sid, key).json()
    for field in ("normalized_skew", "buy_iv", "sell_iv", "atm_iv"):
        m = body["metrics"][field]
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
    assert body["points"], "應該有觀測，只是每一點都插不出值"
    assert all(p["normalized_skew"] is None for p in body["points"])
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
    assert body["points"] == []
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
    佔位。網格整體往上平移──IV 越晚的日子越高，最新一筆理應比四週前
    的水準高，Δ4w 應為正。"""
    schedule = sampling_schedule("XYZ", ny_today())

    def _shifted_grid(offset: float) -> dict:
        pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d + offset)
              for dte in (1, 30, 90, 365, 1200)
              for d in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95)]
        return {"call": pts, "put": pts}

    from api_app.main import _surface_to_rows

    for i, day in enumerate(schedule):
        # 越晚的日子 offset 越大——一條單調上升的序列。
        db.save_iv_observation(IvObservation(
            symbol="XYZ", observed_on=day,
            surface=_surface_to_rows(_shifted_grid(i * 0.001)),
            fetched_at="2026-08-12T00:00:00+00:00"))

    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()

    m = body["metrics"]["buy_iv"]
    assert m["trend_4w"] is not None
    assert m["trend_4w"] > 0, "序列單調上升，最新一筆該高於四週前的水準"
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
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    _prefill(db)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "ok"
    assert body["observations"] >= 20
    for field in ("normalized_skew", "buy_iv", "sell_iv", "atm_iv"):
        m = body["metrics"][field]
        assert m["percentile"] is not None
        assert m["count"] > 0
        assert m["value"] is not None
        # #138：純加法欄位——整份排程都用同一張網格灌值，每天的重錨定
        # 結果都相同，Δ4w 因此該是 0（有基準可減，減出來剛好沒變化），
        # 不是 None（那會是「沒有基準」，跟這裡的情境不同）。
        assert m["trend_4w"] == pytest.approx(0.0)
        assert m["trend_base_count"] > 0


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

        def __call__(self, provider, symbol, on_date, token, expiration=None):
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

        def __call__(self, provider, symbol, on_date, token, expiration=None):
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
