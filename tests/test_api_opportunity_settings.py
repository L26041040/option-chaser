"""Settings 的選填鍵 `opportunity_search`（OS-02／#391，母票 #389 §6／C10）。

沿用既有 `GET`／`PUT /api/settings`，不加 DDL、不加端點。釘住四件事：

1. 未設定時 GET 回預設（20／10／全部家族／return／S&P 500 成分股）；
2. 兩道門檻各自存取、互不影響（PUT 只送其中一個欄位時，其餘欄位不動）；
3. 範圍與型別驗證沿用既有 settings 的 422 格式；
4. 既有鍵（market_data／historical_iv）行為不變——而且**只送既有兩鍵的
   舊版請求不會抹掉 `opportunity_search`**（舊前端照常存資料來源時不能
   順手把機會搜尋設定清空）。
"""
import pytest
from fastapi.testclient import TestClient

from api_app import sp500_constituents
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from tests._role_session import superuser_cookies

_DEFAULT = {"mode": "default", "provider": None}
_BASE = {"market_data": _DEFAULT, "historical_iv": _DEFAULT}

EXPECTED_DEFAULTS = {
    "universe_id": "sp500",
    "custom_symbols": [],
    "percentile_max": 20,
    "dispersion_max": 10,
    "strategies": ["single-leg", "vertical-spread", "butterfly"],
    "sort": "return",
}


@pytest.fixture
def db():
    return MemoryStorage()


@pytest.fixture
def client(db):
    return TestClient(create_app(identity_resolver=lambda: "solo", storage=db),
                      cookies=superuser_cookies(db, owner_id="solo"))


def _put(client, opportunity_search=None, **base):
    body = {**_BASE, **base}
    if opportunity_search is not None:
        body["opportunity_search"] = opportunity_search
    return client.put("/api/settings", json=body)


def _opp(client):
    return client.get("/api/settings").json()["opportunity_search"]


# ---------- 預設值 ----------

def test_unset_opportunity_search_reads_back_as_the_defaults(client):
    assert _opp(client) == EXPECTED_DEFAULTS


def test_view_carries_the_options_the_settings_block_needs(client):
    """母體文案、家族、排序、上限與預設值都由後端給，前端不自己寫一份。"""
    options = client.get("/api/settings").json()["opportunity_search_options"]
    universes = {u["id"]: u for u in options["universes"]}
    assert list(universes) == ["sp500", "custom"]
    assert universes["sp500"]["label"] == "S&P 500 成分股"
    assert universes["sp500"]["provisional"] is False
    assert universes["sp500"]["symbol_count"] == len(sp500_constituents.CONSTITUENTS)
    assert universes["sp500"]["version_date"] == sp500_constituents.VERSION
    assert universes["custom"]["label"] == "自訂清單"
    assert options["strategies"] == ["single-leg", "vertical-spread", "butterfly"]
    assert options["sorts"] == [
        {"id": "return", "label": "目標價情境報酬（高→低）"},
        {"id": "cost", "label": "投入成本（低→高）"},
        {"id": "max_loss", "label": "最大損失（低→高）"}]
    assert options["custom_symbols_max"] == 50
    assert options["defaults"] == EXPECTED_DEFAULTS


# ---------- 儲存與讀回 ----------

def test_full_opportunity_search_survives_a_reload(client):
    wanted = {"universe_id": "custom", "custom_symbols": ["TSLA", "AAPL"],
              "percentile_max": 35, "dispersion_max": 7.5,
              "strategies": ["butterfly"], "sort": "max_loss"}
    resp = _put(client, wanted)
    assert resp.status_code == 200, resp.text
    assert resp.json()["opportunity_search"] == wanted
    assert _opp(client) == wanted


def test_saving_the_first_threshold_leaves_the_second_alone(client):
    _put(client, {"dispersion_max": 6})
    _put(client, {"percentile_max": 15})
    got = _opp(client)
    assert got["percentile_max"] == 15
    assert got["dispersion_max"] == 6


def test_saving_the_second_threshold_leaves_the_first_alone(client):
    _put(client, {"percentile_max": 33})
    _put(client, {"dispersion_max": 4})
    got = _opp(client)
    assert got["percentile_max"] == 33
    assert got["dispersion_max"] == 4


def test_threshold_bounds_are_inclusive(client):
    assert _put(client, {"percentile_max": 0, "dispersion_max": 100}).status_code == 200
    got = _opp(client)
    assert (got["percentile_max"], got["dispersion_max"]) == (0, 100)


def test_custom_symbols_are_deduplicated_keeping_first_order(client):
    resp = _put(client, {"universe_id": "custom",
                         "custom_symbols": ["MSFT", "AAPL", "MSFT", "BRK.B"]})
    assert resp.status_code == 200, resp.text
    assert _opp(client)["custom_symbols"] == ["MSFT", "AAPL", "BRK.B"]


def test_fifty_unique_symbols_after_dedupe_are_accepted(client):
    symbols = [f"T{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(50)]
    resp = _put(client, {"universe_id": "custom",
                         "custom_symbols": symbols + [symbols[0]]})
    assert resp.status_code == 200, resp.text
    assert len(_opp(client)["custom_symbols"]) == 50


def test_strategies_follow_canonical_family_order_without_duplicates(client):
    _put(client, {"strategies": ["butterfly", "single-leg", "butterfly"]})
    assert _opp(client)["strategies"] == ["single-leg", "butterfly"]


def test_switching_back_to_sp500_keeps_the_custom_list(client):
    _put(client, {"universe_id": "custom", "custom_symbols": ["TSLA"]})
    _put(client, {"universe_id": "sp500"})
    got = _opp(client)
    assert got["universe_id"] == "sp500"
    assert got["custom_symbols"] == ["TSLA"]


# ---------- V2-01（#404）：舊設定遷移、股權類別 ----------

def test_legacy_sample_value_from_an_old_frontend_is_saved_as_sp500(client):
    """舊前端送 `sample-large-cap`（大型股樣本已退役）不報錯，存成 `sp500`。"""
    assert _put(client, {"universe_id": "sample-large-cap"}).status_code == 200
    assert _opp(client)["universe_id"] == "sp500"


def test_stored_legacy_sample_setting_reads_back_as_sp500_and_still_saves(client, db):
    """V2-01 之前存下的 SU/SA 設定（`sample-large-cap`＋自己的門檻）讀出來是
    S&P 500，門檻不動；之後只改一個欄位也照常存得進去。"""
    from api_app.storage import DataSourceSettings, UsageSetting
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="default"), historical_iv=UsageSetting(mode="default"),
        updated_at="2026-11-01T00:00:00+00:00", owner_id="solo",
        opportunity_search={"universe_id": "sample-large-cap", "custom_symbols": ["TSLA"],
                            "percentile_max": 30, "dispersion_max": 12,
                            "strategies": ["single-leg"], "sort": "cost"}))
    got = _opp(client)
    assert got == {**EXPECTED_DEFAULTS, "universe_id": "sp500", "custom_symbols": ["TSLA"],
                   "percentile_max": 30, "dispersion_max": 12,
                   "strategies": ["single-leg"], "sort": "cost"}
    assert _put(client, {"dispersion_max": 15}).status_code == 200
    assert _opp(client) == {**got, "dispersion_max": 15}


def test_custom_share_class_symbols_are_saved_in_canonical_dot_form(client):
    resp = _put(client, {"universe_id": "custom",
                         "custom_symbols": ["BRK-B", "GOOGL", "GOOG", "BRK.B", "BF-B"]})
    assert resp.status_code == 200, resp.text
    assert _opp(client)["custom_symbols"] == ["BRK.B", "GOOGL", "GOOG", "BF.B"]


# ---------- 驗證（沿用既有 settings 的 422 格式） ----------

@pytest.mark.parametrize("field", ["percentile_max", "dispersion_max"])
@pytest.mark.parametrize("bad", [-1, 101, "abc", None, True, "20"])
def test_thresholds_reject_out_of_range_and_non_numbers(client, field, bad):
    resp = _put(client, {field: bad})
    assert resp.status_code == 422, resp.text
    assert isinstance(resp.json()["detail"], list)
    assert _opp(client) == EXPECTED_DEFAULTS


def test_rejected_threshold_carries_a_readable_message(client):
    detail = _put(client, {"percentile_max": 101}).json()["detail"]
    assert detail[0]["msg"] == "Value error, 分歧度歷史百分位門檻必須介於 0 到 100"


def test_empty_strategies_are_rejected(client):
    resp = _put(client, {"strategies": []})
    assert resp.status_code == 422
    assert "至少要選一個策略家族" in resp.json()["detail"][0]["msg"]


def test_unknown_strategy_family_is_rejected(client):
    assert _put(client, {"strategies": ["iron-condor"]}).status_code == 422


def test_more_than_fifty_symbols_are_rejected(client):
    symbols = [f"T{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(51)]
    resp = _put(client, {"universe_id": "custom", "custom_symbols": symbols})
    assert resp.status_code == 422
    assert "最多 50 檔" in resp.json()["detail"][0]["msg"]


@pytest.mark.parametrize("bad", ["aapl", "AA PL", "1ABC", "", "TOOLONGTICKER",
                                 "../X", 7])
def test_illegal_tickers_are_rejected(client, bad):
    resp = _put(client, {"universe_id": "custom", "custom_symbols": ["AAPL", bad]})
    assert resp.status_code == 422, resp.text


def test_custom_universe_needs_at_least_one_symbol(client):
    resp = _put(client, {"universe_id": "custom", "custom_symbols": []})
    assert resp.status_code == 422
    assert "自訂清單至少要有一檔" in resp.json()["detail"][0]["msg"]


def test_custom_universe_check_sees_the_already_saved_list(client):
    """欄位是分開存的：先存清單、再只切母體也要過（反之，從沒存過清單
    就只切到 custom 要擋）。"""
    _put(client, {"custom_symbols": ["NVDA"]})
    assert _put(client, {"universe_id": "custom"}).status_code == 200
    assert _opp(client)["universe_id"] == "custom"


@pytest.mark.parametrize("payload", [{"universe_id": "nasdaq100"}, {"sort": "probability"},
                                     {"sort": None}, {"bogus": 1}])
def test_unknown_values_and_keys_are_rejected(client, payload):
    assert _put(client, payload).status_code == 422


# ---------- 既有鍵不受影響 ----------

def test_legacy_put_without_opportunity_search_keeps_the_stored_value(client):
    _put(client, {"percentile_max": 12, "sort": "cost"})
    resp = client.put("/api/settings", json=_BASE)   # 舊前端：只送既有兩鍵
    assert resp.status_code == 200
    got = _opp(client)
    assert got["percentile_max"] == 12
    assert got["sort"] == "cost"


def test_opportunity_search_does_not_disturb_existing_keys(client):
    custom_md = {"mode": "custom", "provider": "marketdata-app"}
    _put(client, market_data=custom_md)
    _put(client, {"percentile_max": 5}, market_data=custom_md)
    body = client.get("/api/settings").json()
    assert body["market_data"]["mode"] == "custom"
    assert body["market_data"]["provider"] == "marketdata-app"
    assert body["historical_iv"]["mode"] == "default"


def test_old_stored_settings_without_the_key_read_back_unchanged(client, db):
    """`opportunity_search` 出現之前存的設定，讀回來時既有鍵照舊，新鍵是預設。"""
    from api_app.storage import DataSourceSettings, UsageSetting
    db.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode="custom", provider="marketdata-app"),
        historical_iv=UsageSetting(mode="default"),
        updated_at="2026-01-01T00:00:00+00:00", owner_id="solo"))
    body = client.get("/api/settings").json()
    assert body["market_data"]["provider"] == "marketdata-app"
    assert body["updated_at"] == "2026-01-01T00:00:00+00:00"
    assert body["opportunity_search"] == EXPECTED_DEFAULTS


# ---------- 權限：只有 SU／SA 能寫 opportunity_search ----------

@pytest.fixture
def normal_client(db):
    return TestClient(create_app(identity_resolver=lambda: "solo", storage=db))


def test_normal_user_cannot_write_opportunity_search(normal_client, db):
    resp = _put(normal_client, {"universe_id": "custom", "custom_symbols": ["AAPL"]})
    assert resp.status_code == 403
    assert db.get_settings(owner="solo") is None          # 什麼都沒寫
    assert _opp(normal_client) == EXPECTED_DEFAULTS


def test_normal_user_still_saves_the_existing_keys(normal_client):
    custom_md = {"mode": "custom", "provider": "marketdata-app"}
    resp = _put(normal_client, market_data=custom_md)
    assert resp.status_code == 200
    assert resp.json()["market_data"]["provider"] == "marketdata-app"
    assert resp.json()["opportunity_search"] == EXPECTED_DEFAULTS


def test_anonymous_cookie_identity_cannot_write_opportunity_search():
    db = MemoryStorage()
    client = TestClient(create_app(storage=db), base_url="https://testserver")
    resp = _put(client, {"percentile_max": 5})
    assert resp.status_code == 403
    assert client.get("/api/settings").json()["opportunity_search"] == EXPECTED_DEFAULTS


@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_superuser_and_superadmin_can_write_opportunity_search(db, role):
    from tests._role_session import role_cookies
    client = TestClient(create_app(storage=db), base_url="https://testserver",
                        cookies=role_cookies(db, role))
    assert _put(client, {"percentile_max": 5}).status_code == 200
    assert _opp(client)["percentile_max"] == 5
