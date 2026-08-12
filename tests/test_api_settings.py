"""設定：資料源模式與 Provider credential（Settings／#124）。

這份測試的重心是**兩條硬性紅線**，其餘才是一般 CRUD 行為：

1. 完整 token 絕不離開後端——回應、事件紀錄、log 三處都明文斷言。
2. 自訂資料源只能是白名單裡已內建 adapter 的那幾家，不接受任意 id。
"""
import logging

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage

TOKEN = "mdapp_live_SECRET1234abcd"
PROVIDER = providers.MARKETDATA_APP.id


@pytest.fixture
def db():
    return MemoryStorage()


@pytest.fixture
def client(db):
    return TestClient(create_app(storage=db))


def _custom(provider=PROVIDER):
    return {"mode": "custom", "provider": provider}


_DEFAULT = {"mode": "default", "provider": None}


# ---------- 預設值 ----------

def test_defaults_are_cboe_and_none_before_anything_is_saved(client):
    """兩列的預設值不同，而且都不需要使用者先做任何事。"""
    body = client.get("/api/settings").json()
    assert body["market_data"]["mode"] == "default"
    assert body["market_data"]["default_label"] == "Cboe"
    assert body["historical_iv"]["mode"] == "default"
    assert body["historical_iv"]["default_label"] == "無"


def test_supported_providers_is_the_whitelist(client):
    body = client.get("/api/settings").json()
    assert body["supported_providers"] == [
        {"id": PROVIDER, "label": "Market Data App"}]


# ---------- 模式儲存 ----------

def test_saved_modes_survive_a_reload(client):
    client.put("/api/settings", json={"market_data": _custom(),
                                      "historical_iv": _DEFAULT})
    body = client.get("/api/settings").json()
    assert body["market_data"] == {"mode": "custom", "provider": PROVIDER,
                                   "default_label": "Cboe"}
    assert body["historical_iv"]["mode"] == "default"


def test_default_mode_clears_any_provider_that_was_sent_with_it(client):
    """模式與 provider 不一致的狀態不該存得進去——讀回來時無從判斷該信
    哪一邊。"""
    resp = client.put("/api/settings",
                      json={"market_data": {"mode": "default",
                                            "provider": PROVIDER},
                            "historical_iv": _DEFAULT})
    assert resp.json()["market_data"]["provider"] is None


# ---------- 白名單：自訂 ≠ 任意 API ----------

def test_custom_mode_requires_a_provider(client):
    resp = client.put("/api/settings", json={"market_data":
                                             {"mode": "custom", "provider": None},
                                             "historical_iv": _DEFAULT})
    assert resp.status_code == 422


def test_arbitrary_provider_id_is_rejected(client):
    resp = client.put("/api/settings",
                      json={"market_data": _custom("https://evil.example/api"),
                            "historical_iv": _DEFAULT})
    assert resp.status_code == 422


def test_credential_for_an_unknown_provider_is_rejected(client, db):
    resp = client.put("/api/settings/credentials/some-other-vendor",
                      json={"token": TOKEN})
    assert resp.status_code == 400
    assert db.get_credential("some-other-vendor") is None


# ---------- token 的邊界 ----------

def test_stored_token_is_never_returned_in_any_response(client):
    """最重要的一條：存進去之後，完整 token 不得再出現在任何回應裡。

    斷言整份回應的原始文字，而不是逐欄位挑——新加欄位若不小心帶上
    token，這條會直接紅燈。
    """
    save = client.put(f"/api/settings/credentials/{PROVIDER}",
                      json={"token": TOKEN})
    assert TOKEN not in save.text
    assert TOKEN not in client.get("/api/settings").text


def test_saved_token_shows_as_masked_with_only_a_short_tail(client):
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    cred = client.get("/api/settings").json()["credentials"][PROVIDER]
    assert cred["configured"] is True
    assert cred["masked"] == "••••••••abcd"
    assert cred["updated_at"]


def test_mask_hides_length_and_reveals_nothing_for_short_tokens():
    """遮罩長度固定：跟著 token 長短變化的話，遮罩本身就洩漏了長度。"""
    assert providers.mask_token("a" * 8) == providers.mask_token("a" * 200)[:8] + "aaaa"
    assert providers.mask_token("abc") == "••••••••"


def test_token_is_stored_in_full_behind_the_api(client, db):
    """遮罩是**回應層**的事，後端自己仍握有完整 token（#125 要拿它去
    驗證連線）——否則遮罩就成了資料損毀。"""
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    assert db.get_credential(PROVIDER).token == TOKEN


def test_token_never_reaches_the_event_log(client, db):
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    client.put("/api/settings", json={"market_data": _custom(),
                                      "historical_iv": _custom()})
    assert TOKEN not in repr(db.list_events())


def test_token_never_reaches_the_application_log(client, caplog):
    with caplog.at_level(logging.DEBUG):
        client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
        client.get("/api/settings")
    assert TOKEN not in caplog.text


def test_blank_token_is_rejected(client):
    assert client.put(f"/api/settings/credentials/{PROVIDER}",
                      json={"token": "   "}).status_code == 422


def test_surrounding_whitespace_is_stripped(client, db):
    """貼上時多帶的空白不是 token 的一部分，留著只會讓驗證莫名失敗。"""
    client.put(f"/api/settings/credentials/{PROVIDER}",
               json={"token": f"  {TOKEN}\n"})
    assert db.get_credential(PROVIDER).token == TOKEN


# ---------- 一個 Provider 一把 credential（共用） ----------

def test_both_usages_on_one_provider_share_a_single_credential(client, db):
    """需求方裁示：不要求使用者把同一把 token 輸入兩次。

    credential 以 provider 為 key，所以「共用」不是前端的體貼，而是資料
    模型本身就只有一份。
    """
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    body = client.put("/api/settings", json={"market_data": _custom(),
                                             "historical_iv": _custom()}).json()
    assert body["market_data"]["provider"] == body["historical_iv"]["provider"]
    assert list(body["credentials"]) == [PROVIDER]
    assert body["credentials"][PROVIDER]["configured"] is True


def test_replacing_a_token_overwrites_rather_than_accumulates(client, db):
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": "second-9999"})
    assert db.get_credential(PROVIDER).token == "second-9999"


# ---------- 清除 ----------

def test_clearing_a_credential_returns_to_unconfigured(client):
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    body = client.delete(f"/api/settings/credentials/{PROVIDER}").json()
    assert body["credentials"][PROVIDER] == {"configured": False, "masked": None,
                                             "updated_at": None}


def test_clearing_a_credential_leaves_the_mode_choice_alone(client):
    """清 token 不等於改設定——使用者可能只是要換一把。"""
    client.put("/api/settings", json={"market_data": _custom(),
                                      "historical_iv": _DEFAULT})
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    body = client.delete(f"/api/settings/credentials/{PROVIDER}").json()
    assert body["market_data"]["mode"] == "custom"


def test_clearing_something_that_was_never_set_is_not_an_error(client):
    assert client.delete(f"/api/settings/credentials/{PROVIDER}").status_code == 200


# ---------- 不影響其他功能 ----------

def test_settings_do_not_disturb_the_scenario_endpoints(client):
    client.put("/api/settings", json={"market_data": _custom(),
                                      "historical_iv": _custom()})
    assert client.get("/api/scenarios").json() == []
