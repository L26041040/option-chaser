"""Historical IV 端點與模組閘門（#126）。

最重要的一條不是「算得對」，而是**鎖著的時候一個請求都不發**——
`historical_surface` 注入一個會 assert 失敗的假體，任何偷跑都會紅燈。
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage import IvBackfillRun
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
    # delta 一路蓋到 0.01：真實的鏈有深價外履約價，而這份 fixture 的候選
    # 兩腿就落在 0.03–0.06。網格不夠寬時引擎會（正確地）拒絕外插，那時
    # 測到的是「拒絕外插」而不是本來要測的東西。
    pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d)
           for dte in (1, 30, 90, 365, 1200)
           for d in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95)]
    return {"call": pts, "put": pts}


def _rich_surface(*_args, **_kwargs):
    return _grid()


class Recorder:
    """記錄每一次 vendor 呼叫的 (symbol, 日期)——「已有日期不重抓」與
    「同一天不重複燒額度」都只能靠這個斷言。"""

    def __init__(self, fail=None):
        self.calls: list[tuple[str, str]] = []
        self._fail = fail

    def __call__(self, provider, symbol, on_date, token):
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
    assert body["current"] is not None


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


def test_percentiles_are_reported_once_the_cache_is_filled(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    _prefill(db)
    pct = _get(client, sid, _candidate_key(client, sid)).json()["percentiles"]
    assert set(pct) >= {"normalized_skew", "buy_iv", "sell_iv"}


def test_a_coordinate_outside_the_grid_is_left_blank_not_faked(db):
    """網格只蓋短天期時，長天期候選的每一天都插不出值——留空，不是拿最長
    那格頂替（#114 AC 明文）。整段都插不出來時也不給百分位。"""
    narrow = [SurfacePoint(dte=d, delta=x, iv=0.2)
              for d in (1, 5) for x in (0.4, 0.5, 0.6)]
    client = _client(db, surface=lambda *a, **k: {"call": narrow, "put": narrow})
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["points"], "應該有觀測，只是每一點都插不出值"
    assert all(p["normalized_skew"] is None for p in body["points"])
    assert body["percentiles"] == {}
    assert body["status"] == "insufficient"


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


def test_sparse_coverage_is_reported_as_insufficient(db):
    """觀測太少時不給百分位——硬算一個看起來很確定的數字就是造假。"""
    rec = Recorder(fail=FetchError("vendor 掛了"))
    client = _client(db, surface=rec)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["percentiles"] == {}
    assert body["observations"] == 0


def test_a_first_day_run_is_honestly_incomplete_not_ok(db):
    """progressive backfill 的第一天本來就補不滿——這時候說「資料尚未
    完整」是實話，硬給一個 1Y percentile 才是造假。"""
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "insufficient"
    assert body["percentiles"] == {}
    assert body["observations"] > 0        # 有進度，只是還不夠


def test_a_healthy_run_reports_ok_with_weighted_percentiles(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    _prefill(db)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["status"] == "ok"
    assert body["observations"] >= 20
    assert body["coverage"] >= 0.5
    assert set(body["percentiles"]) >= {"normalized_skew", "buy_iv", "sell_iv"}


def test_no_percentile_is_offered_when_the_status_is_not_ok(db):
    """需求方紅線：不得為了湊圖而端出百分位。"""
    for failure in (QuotaExhausted("額度"), FetchError("掛了")):
        fresh = MemoryStorage()
        client = _client(fresh, surface=Recorder(fail=failure))
        _unlock(client)
        sid = _scenario(client)
        body = _get(client, sid, _candidate_key(client, sid)).json()
        assert body["percentiles"] == {}, body["status"]
