"""Historical IV 端點與模組閘門（#126）。

最重要的一條不是「算得對」，而是**鎖著的時候一個請求都不發**——
`historical_surface` 注入一個會 assert 失敗的假體，任何偷跑都會紅燈。
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ivhistory import SurfacePoint
from option_chaser.models import FetchError
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


def _rich_surface(*_args, **_kwargs):
    """一個蓋得夠寬的網格，任何合理座標都插得出來。"""
    pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d)
           for dte in (1, 30, 90, 365, 1200)
           for d in (0.05, 0.25, 0.5, 0.75, 0.95)]
    return {"call": pts, "put": pts}


def _client(db, *, surface=_surface_never_called):
    return TestClient(create_app(
        storage=db, fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=surface))


@pytest.fixture
def db():
    return MemoryStorage()


def _scenario(client):
    """建立**並跑一次分析**——建立本身不分析，沒有結果就沒有候選可查。"""
    sid = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0,
        "target_month": "2026-09"}).json()["id"]
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

def test_unlocked_series_is_daily_and_re_anchored(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["window_days"] == 365
    assert len(body["points"]) > 200        # 一年扣掉週末
    assert all("date" in p for p in body["points"])
    assert body["current"] is not None


def test_series_carries_both_legs_and_the_atm_level(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    point = _get(client, sid, _candidate_key(client, sid)).json()["points"][0]
    assert set(point) >= {"date", "buy_iv", "sell_iv", "atm_iv",
                          "normalized_skew"}


def test_percentiles_are_reported_for_the_latest_value(db):
    client = _client(db, surface=_rich_surface)
    _unlock(client)
    sid = _scenario(client)
    pct = _get(client, sid, _candidate_key(client, sid)).json()["percentiles"]
    assert set(pct) >= {"normalized_skew", "buy_iv", "sell_iv"}


def test_a_coordinate_outside_the_grid_is_labelled_not_faked(db):
    """網格只蓋短天期時，長天期候選要說「超出可比網格」，不是拿最長那格
    頂替（#114 AC 明文）。"""
    narrow = [SurfacePoint(dte=d, delta=x, iv=0.2)
              for d in (1, 5) for x in (0.4, 0.5, 0.6)]
    client = _client(db, surface=lambda *a, **k: {"call": narrow, "put": narrow})
    _unlock(client)
    sid = _scenario(client)
    body = _get(client, sid, _candidate_key(client, sid)).json()
    assert body["out_of_grid"] is True
    assert all(p["normalized_skew"] is None for p in body["points"])


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
