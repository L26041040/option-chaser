"""測試連線三態＋Market Data 自訂來源與 fallback（Settings／#125）。

全程離線：`verify_provider` 與 `custom_fetch` 都由 `create_app` 注入，
沒有任何一條路徑會打到真的 Market Data App。
"""
import dataclasses
import logging

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.models import FetchError
from option_chaser.ratecurve import RateCurve

# 沿用 `test_api_analyze.py` 的既有快照與假 loader：本檔案要驗的是抓鏈
# **路徑的選擇**，不是引擎算得對不對，因此利率／配息一律注入固定值，
# 不讓測試依賴本機當下連不連得到外部來源。
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
_RATE_CURVE = RateCurve(curve_date="2026-07-31",
                        nodes=((0.5, 0.041), (1.0, 0.042), (2.0, 0.043),
                               (3.0, 0.044)))
_DIVIDENDS = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                             distributions=(DividendRecord("2026-06-01", 1.2),))


def _rate_loader(today):
    return _RATE_CURVE, "假曲線"


def _dividend_loader(symbol, today):
    return _DIVIDENDS, "假配息"


def chain_snapshot(*, source):
    """固定快照，只換 `source`——用來證明「實際走了哪條路徑」。"""
    return dataclasses.replace(load_snapshot(FIX), source=source)

TOKEN = "mdapp_live_SECRET1234abcd"
PROVIDER = providers.MARKETDATA_APP.id


def _ok(_provider, _token):
    return providers.VerifyOutcome(True)


def _rejected(_provider, _token):
    return providers.VerifyOutcome(False, "認證被拒——請確認 token 是否正確、是否已失效")


@pytest.fixture
def db():
    return MemoryStorage()


def _client(db, *, verify=_ok, custom_fetch=None, fetch=None):
    kwargs = {"storage": db, "verify_provider": verify,
              "rate_loader": _rate_loader, "dividend_loader": _dividend_loader}
    if custom_fetch is not None:
        kwargs["custom_fetch"] = custom_fetch
    if fetch is not None:
        kwargs["fetch"] = fetch
    return TestClient(create_app(**kwargs))


def _configure(client, *, market="custom", iv="default"):
    def usage(mode):
        return {"mode": mode, "provider": PROVIDER if mode == "custom" else None}
    client.put("/api/settings", json={"market_data": usage(market),
                                      "historical_iv": usage(iv)})


def _save_token(client):
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})


# ---------- 三態 ----------

def test_status_is_unset_before_a_token_exists(db):
    client = _client(db)
    assert client.get("/api/settings").json()["credentials"][PROVIDER]["status"] \
        == "unset"


def test_status_is_unverified_after_saving_a_token_but_before_testing(db):
    """存了 token 不等於「已連線」——那是還沒驗證過的宣稱。"""
    client = _client(db)
    _save_token(client)
    assert client.get("/api/settings").json()["credentials"][PROVIDER]["status"] \
        == "unverified"


def test_successful_test_reports_connected(db):
    client = _client(db)
    _save_token(client)
    cred = client.post(f"/api/settings/credentials/{PROVIDER}/test") \
                 .json()["credentials"][PROVIDER]
    assert cred["status"] == "ok"
    assert cred["reason"] is None
    assert cred["checked_at"]


def test_failed_test_reports_a_readable_reason(db):
    client = _client(db, verify=_rejected)
    _save_token(client)
    cred = client.post(f"/api/settings/credentials/{PROVIDER}/test") \
                 .json()["credentials"][PROVIDER]
    assert cred["status"] == "failed"
    assert "認證被拒" in cred["reason"]


def test_a_failed_verification_is_not_an_http_error(db):
    """「這把 token 不能用」是這個端點的正常答案之一，不是請求失敗。"""
    client = _client(db, verify=_rejected)
    _save_token(client)
    assert client.post(f"/api/settings/credentials/{PROVIDER}/test").status_code \
        == 200


def test_testing_without_a_token_is_refused(db):
    client = _client(db)
    assert client.post(f"/api/settings/credentials/{PROVIDER}/test").status_code \
        == 400


def test_testing_an_unknown_provider_is_refused(db):
    assert _client(db).post("/api/settings/credentials/nope/test").status_code == 400


def test_verification_result_survives_a_reload(db):
    """重新載入設定頁不必重測就看得到上次結果與時間。"""
    client = _client(db, verify=_rejected)
    _save_token(client)
    first = client.post(f"/api/settings/credentials/{PROVIDER}/test") \
                  .json()["credentials"][PROVIDER]
    again = client.get("/api/settings").json()["credentials"][PROVIDER]
    assert again["status"] == "failed"
    assert again["checked_at"] == first["checked_at"]


def test_clearing_the_token_also_clears_its_verification(db):
    """沒有 credential 卻還顯示「已連線」是最糟的一種騙人。"""
    client = _client(db)
    _save_token(client)
    client.post(f"/api/settings/credentials/{PROVIDER}/test")
    cred = client.delete(f"/api/settings/credentials/{PROVIDER}") \
                 .json()["credentials"][PROVIDER]
    assert cred["status"] == "unset"
    assert cred["checked_at"] is None


def test_both_usages_share_one_verification_result(db):
    """credential 是 per-Provider 的一把，驗證結果自然也只有一份——
    不要求使用者為同一把 token 測兩次。"""
    client = _client(db)
    _configure(client, market="custom", iv="custom")
    _save_token(client)
    body = client.post(f"/api/settings/credentials/{PROVIDER}/test").json()
    assert list(body["credentials"]) == [PROVIDER]
    assert body["credentials"][PROVIDER]["status"] == "ok"


def test_token_never_reaches_the_log_during_verification(db, caplog):
    client = _client(db, verify=_rejected)
    _save_token(client)
    with caplog.at_level(logging.DEBUG):
        client.post(f"/api/settings/credentials/{PROVIDER}/test")
    assert TOKEN not in caplog.text


def test_token_never_appears_in_the_verification_response(db):
    client = _client(db, verify=_rejected)
    _save_token(client)
    assert TOKEN not in client.post(
        f"/api/settings/credentials/{PROVIDER}/test").text


# ---------- 生效來源與 fallback ----------

def _analyze(client):
    return client.post("/api/analyze", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["bull-call-spread"]})


def test_default_mode_reports_cboe_and_no_fallback(db):
    client = _client(db)
    assert client.get("/api/settings").json()["market_data_effective"] == {
        "source": "Cboe", "fallback": False, "reason": None}


def test_custom_without_a_token_says_it_is_falling_back(db):
    client = _client(db)
    _configure(client)
    eff = client.get("/api/settings").json()["market_data_effective"]
    assert eff["fallback"] is True
    assert "尚未設定 token" in eff["reason"]
    assert eff["source"] == "Cboe"


def test_custom_saved_but_untested_says_it_is_falling_back(db):
    client = _client(db)
    _configure(client)
    _save_token(client)
    eff = client.get("/api/settings").json()["market_data_effective"]
    assert eff["fallback"] is True
    assert "尚未測試連線" in eff["reason"]


def test_custom_verified_reports_the_custom_source(db):
    client = _client(db)
    _configure(client)
    _save_token(client)
    client.post(f"/api/settings/credentials/{PROVIDER}/test")
    assert client.get("/api/settings").json()["market_data_effective"] == {
        "source": "Market Data App", "fallback": False, "reason": None}


def test_a_working_custom_source_is_actually_used_for_analysis(db):
    """設定說要用自訂，分析就真的走自訂——快照 `source` 如實記錄。"""
    calls = []

    def custom(provider, symbol, token):
        calls.append((provider, symbol, token))
        return chain_snapshot(source="marketdata-app")

    def default_fetch(symbol):
        raise AssertionError("自訂可用時不該退回預設來源")

    client = _client(db, custom_fetch=custom, fetch=default_fetch)
    _configure(client)
    _save_token(client)

    body = _analyze(client).json()
    assert body["meta"]["source"] == "marketdata-app"
    assert calls == [(PROVIDER, "XYZ", TOKEN)]


def test_a_broken_custom_source_falls_back_to_the_default_chain(db):
    """自訂掛掉時分析照常完成，走的是既有 Cboe → yfinance 降級鏈。"""
    def custom(provider, symbol, token):
        raise FetchError("Market Data App 抓取失敗（XYZ）: 額度用盡")

    client = _client(db, custom_fetch=custom,
                     fetch=lambda s: chain_snapshot(source="cboe"))
    _configure(client)
    _save_token(client)

    body = _analyze(client).json()
    assert body["meta"]["source"] == "cboe"


def test_the_fallback_is_reported_honestly_not_silently(db):
    """退回之後設定頁要說得出「為什麼現在用的不是你選的那家」。"""
    def custom(provider, symbol, token):
        raise FetchError("Market Data App 抓取失敗（XYZ）: 額度用盡")

    client = _client(db, custom_fetch=custom,
                     fetch=lambda s: chain_snapshot(source="cboe"))
    _configure(client)
    _save_token(client)
    _analyze(client)

    body = client.get("/api/settings").json()
    assert body["credentials"][PROVIDER]["status"] == "failed"
    assert "額度用盡" in body["credentials"][PROVIDER]["reason"]
    eff = body["market_data_effective"]
    assert eff["fallback"] is True and eff["source"] == "Cboe"


def test_a_successful_custom_fetch_records_that_it_worked(db):
    """真的抓成功了，是比任何測試連線都硬的證據——狀態要跟著變好。"""
    client = _client(db, custom_fetch=lambda p, s, t: chain_snapshot(
        source="marketdata-app"))
    _configure(client)
    _save_token(client)
    _analyze(client)
    assert client.get("/api/settings").json()["credentials"][PROVIDER]["status"] \
        == "ok"


def test_default_mode_never_touches_the_custom_provider(db):
    def custom(provider, symbol, token):
        raise AssertionError("預設模式不該碰自訂資料源")

    client = _client(db, custom_fetch=custom,
                     fetch=lambda s: chain_snapshot(source="cboe"))
    assert _analyze(client).status_code == 200
