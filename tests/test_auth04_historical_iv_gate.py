"""AUTH-04（#311，Anonymous Public Beta，三層角色模型 spec #307）：
Historical IV 角色閘門 ＋ 唯一 protected owner credential 借用。

四個核心情境，逐一對應票面 Acceptance Criteria：

1. **Normal User**——閘門前後行為不變（沿用既有 403 訊息），且角色
   檢查本身必須排在觸碰 `list_owners()` 之前——票面 Security
   considerations 明文要求：不得讓 Normal User 的請求洩漏「有沒有
   protected owner 存在」這個存在性資訊。
2. **尚未有 protected owner**（PB-03 遷移前）——Super User／Super
   Admin 一樣拿到同一句 403，不是 500，不猜、不挑第一個。
3. **遷移完成後——借用**：Super User／Super Admin 借用 protected
   owner 已驗證的 credential，即使發請求的是完全不同的一個 owner；
   這個劇本／候選本身仍歸屬發請求者自己的 owner（`identity_
   resolver()`），只有 credential 來源改變。
4. **邊界情況**——0 個或多於 1 個 protected owner 一律 fail-closed。

另外直接對 `_the_protected_owner_id()` 做純函式單元測試，不必透過
HTTP 就能驗證判準本身。

**範圍確認**：本檔案只測 `api_app/main.py` 的閘門與 credential 來源
層。五個 Historical IV 引擎模組（`option_chaser/ivpipeline.py`／
`ivreconstruct.py`／`ivhistory.py`／`ivspread.py`／`ivtrend.py`）與
`ContractHistory`／`IvBackfillRun` 兩張儲存表本輪零改動——`git diff`
已在對應 commit 核對過範圍。
"""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app import providers
from api_app.clock import now_utc_iso
from api_app.main import _the_protected_owner_id, create_app
from api_app.storage import (DataSourceSettings, Owner, ProviderCredential,
                             ProviderVerification, UsageSetting)
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory
from option_chaser.ratecurve import RateCurve
from tests._protected_owner import ensure_owner, ensure_protected_owner
from tests._role_session import role_cookies

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
PROVIDER = providers.MARKETDATA_APP.id
TOKEN = "mdapp_live_PROTECTED0001"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
      "strategies": ["vertical-spread"]}

_HISTORICAL_IV_DISABLED_DETAIL = (
    "Historical IV 未啟用——請在設定頁選擇自訂資料源並通過測試連線")

_RATE = RateCurve(curve_date="2026-07-31",
                  nodes=((0.5, 0.041), (1.0, 0.042), (2.0, 0.043)))
_DIV = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                       distributions=())
_RATE_CURVE_ROWS = (("2020-01-01", ((0.1, 0.04), (30.0, 0.04))),)


def _rate_loader(today):
    return _RATE, "假曲線"


def _dividend_loader(symbol, today):
    return _DIV, "假配息"


def _rate_curve_rows(from_date, to_date):
    return _RATE_CURVE_ROWS


def _snap():
    # `fetched_at` 用真正的「現在」（而不是 fixture 內建的固定日期）
    # ——避免需要像 `test_api_iv_history.py` 那樣凍結系統時鐘；本檔案
    # 的斷言只關心「借用了誰的 token」，不關心 percentile／Δ4w 這類
    # 對日期敏感的計算細節。
    return dataclasses.replace(load_snapshot(FIX), source="cboe",
                               fetched_at=now_utc_iso())


def _never_called_contract_history(*args, **kwargs):
    raise AssertionError(
        "閘門未通過時不得對 vendor 發任何 exact-contract 歷史請求")


class _RecordingContractHistory:
    """記錄每一次呼叫實際帶著哪個 token／symbol——直接證明「借用了誰
    的 credential」，比只看回應形狀更硬。回傳空序列，reconstruction
    因此不會產生任何觀測，測試只關心「呼叫本身有沒有發生、帶著哪個
    token」，不關心序列本身的統計量。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, provider, occ_symbol, from_date, to_date, token,
                observer=None):
        self.calls.append({"provider": provider, "occ_symbol": occ_symbol,
                           "token": token})
        return []


def _client(*, storage, identity_resolver, cookies=None,
           contract_history=_never_called_contract_history):
    return TestClient(create_app(
        identity_resolver=identity_resolver, storage=storage,
        fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=lambda *a, **k: {"call": [], "put": []},
        contract_history=contract_history,
        rate_curve_rows=_rate_curve_rows),
        cookies=cookies)


def _configure_owner_historical_iv(storage, owner_id: str, *,
                                   token: str = TOKEN) -> None:
    """直接寫 storage——既有 `test_api_iv_history.py::_unlock()` 那條
    HTTP helper 只能設定「這次請求自己身份」的設定，而 AUTH-04 的核心
    情境恰好需要設定**另一個**（protected）owner 的設定，發請求的是
    完全不同的一個 owner，因此不能走那條 HTTP 路徑；比照
    `test_pb06_global_vendor_fuse.py` 既有「直接寫 storage 建立前提
    狀態」的手法。"""
    now = now_utc_iso()
    storage.save_settings(DataSourceSettings(
        market_data=UsageSetting(mode=providers.MODE_DEFAULT),
        historical_iv=UsageSetting(mode=providers.MODE_CUSTOM,
                                   provider=PROVIDER),
        updated_at=now, owner_id=owner_id))
    storage.save_credential(ProviderCredential(
        provider=PROVIDER, token=token, updated_at=now, owner_id=owner_id))
    storage.save_verification(ProviderVerification(
        provider=PROVIDER, ok=True, reason=None, checked_at=now,
        owner_id=owner_id))


def _create_and_refresh(client, *, target_price: float = 130.0) -> str:
    sid = client.post("/api/scenarios",
                      json={**NEW, "target_price": target_price}).json()["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    return sid


def _first_two_leg_candidate_key(client, sid: str) -> str:
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for key in g["candidate_keys"]:
                return key
    raise AssertionError("fixture 應該至少有一個合格候選")


@pytest.fixture
def storage():
    return MemoryStorage()


# ---------- 純函式：`_the_protected_owner_id()` 本身 ----------

def test_zero_owners_has_no_protected_owner():
    assert _the_protected_owner_id([]) is None


def test_exactly_one_protected_owner_among_several_is_found():
    owners = [
        Owner(owner_id="a", created_at="2026-01-01T00:00:00+00:00",
             protected=False),
        Owner(owner_id="b", created_at="2026-01-01T00:00:00+00:00",
             protected=True),
        Owner(owner_id="c", created_at="2026-01-01T00:00:00+00:00",
             protected=False),
    ]
    assert _the_protected_owner_id(owners) == "b"


def test_zero_protected_among_several_unprotected_is_none():
    owners = [
        Owner(owner_id="a", created_at="2026-01-01T00:00:00+00:00",
             protected=False),
        Owner(owner_id="b", created_at="2026-01-01T00:00:00+00:00",
             protected=False),
    ]
    assert _the_protected_owner_id(owners) is None


def test_more_than_one_protected_owner_is_ambiguous_and_fails_closed():
    owners = [
        Owner(owner_id="a", created_at="2026-01-01T00:00:00+00:00",
             protected=True),
        Owner(owner_id="b", created_at="2026-01-01T00:00:00+00:00",
             protected=True),
    ]
    assert _the_protected_owner_id(owners) is None


# ---------- 情境 1：Normal User ----------

def test_normal_user_gets_the_same_403_even_with_a_fully_configured_protected_owner(
        storage):
    """Normal User 沒有帶任何角色 cookie——即使 protected owner 已經
    完整設定好（settings／credential／verification 三者皆備），
    Historical IV 對他依然是同一句既有 403，一個 vendor 請求都不發。"""
    ensure_protected_owner(storage, "the-protected-owner")
    _configure_owner_historical_iv(storage, "the-protected-owner")

    client = _client(storage=storage, identity_resolver=lambda: "a-normal-user")
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    get_resp = client.get(f"/api/scenarios/{sid}/iv-history",
                          params={"candidate_key": key})
    assert get_resp.status_code == 403
    assert get_resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL

    post_resp = client.post(f"/api/scenarios/{sid}/iv-history/backfill",
                            params={"candidate_key": key})
    assert post_resp.status_code == 403
    assert post_resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL


def test_normal_user_request_never_even_queries_for_a_protected_owner(
        storage, monkeypatch):
    """票面 Security considerations 的直接落地：角色檢查沒過之前，
    連「有沒有 protected owner 存在」這個查詢都不該發生——不只是
    「不洩漏借用了誰的 credential」，是連查都不查。"""
    calls: list[None] = []
    original = MemoryStorage.list_owners

    def _recording_list_owners(self):
        calls.append(None)
        return original(self)

    monkeypatch.setattr(MemoryStorage, "list_owners", _recording_list_owners)

    client = _client(storage=storage, identity_resolver=lambda: "a-normal-user")
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    calls.clear()  # `_create_and_refresh`／建立候選過程本身可能觸發其他呼叫
    resp = client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})
    assert resp.status_code == 403
    assert calls == []


# ---------- 情境 2：尚未有 protected owner（PB-03 遷移前） ----------

@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_no_protected_owner_yet_reports_not_enabled_not_500(storage, role):
    """PB-03 遷移前，`owners` 表裡可能已經有幾個匿名 owner，但沒有一個
    標記 `protected`——Super User／Super Admin 一樣拿到同一句 403、
    不是 500，也不會被誤判成別的原因。"""
    ensure_owner(storage, "unrelated-anonymous-1", protected=False)
    ensure_owner(storage, "unrelated-anonymous-2", protected=False)

    client = _client(storage=storage, identity_resolver=lambda: "a-requester",
                     cookies=role_cookies(storage, role))
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    get_resp = client.get(f"/api/scenarios/{sid}/iv-history",
                          params={"candidate_key": key})
    assert get_resp.status_code == 403
    assert get_resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL

    post_resp = client.post(f"/api/scenarios/{sid}/iv-history/backfill",
                            params={"candidate_key": key})
    assert post_resp.status_code == 403
    assert post_resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL


# ---------- 情境 3：遷移完成後——借用 protected owner 的 credential ----------

@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_borrows_the_protected_owners_credential_across_a_different_requesting_owner(
        storage, role):
    """核心情境：protected owner（PB-03 遷移後的 Owner 本人）已經設定
    好一把 credential；發請求的是**完全不同**的另一個 owner（結構上
    甚至不在 `owners` 表裡註冊過）。角色 >= Super User 時，Historical
    IV 200，且 vendor 呼叫實際帶著的是 protected owner 的 token——不是
    發請求者自己的（他根本沒有設定過）。"""
    protected_owner_id = "the-protected-owner"
    ensure_protected_owner(storage, protected_owner_id)
    _configure_owner_historical_iv(storage, protected_owner_id, token=TOKEN)

    recorder = _RecordingContractHistory()
    client = _client(storage=storage,
                     identity_resolver=lambda: "a-different-anonymous-owner",
                     cookies=role_cookies(storage, role),
                     contract_history=recorder)
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    resp = client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})
    assert resp.status_code == 200
    assert recorder.calls, "應該至少對 vendor 發過一次 exact-contract 歷史請求"
    assert all(call["token"] == TOKEN for call in recorder.calls)


def test_the_requesting_owner_never_gets_its_own_settings_used_when_it_has_none(
        storage):
    """反向證明：發請求的 owner 自己完全沒有設定過任何 credential
    （`/api/settings` 誠實回報鎖著），但 Historical IV 呼叫依然成功
    ——credential 來源真的是借來的，不是發請求者自己悄悄也被判定成
    可用。"""
    protected_owner_id = "the-protected-owner"
    ensure_protected_owner(storage, protected_owner_id)
    _configure_owner_historical_iv(storage, protected_owner_id, token=TOKEN)

    recorder = _RecordingContractHistory()
    client = _client(storage=storage,
                     identity_resolver=lambda: "a-different-anonymous-owner",
                     cookies=role_cookies(storage, "superuser"),
                     contract_history=recorder)
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    assert client.get("/api/settings").json()["historical_iv_enabled"] is False

    resp = client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})
    assert resp.status_code == 200


def test_the_scenario_itself_still_belongs_to_the_requesting_owner_not_the_protected_owner(
        storage):
    """只有 credential 來源被借用——這個劇本本身仍歸屬發請求者自己的
    owner。另一個完全不相干的 owner（甚至是 protected owner 自己）
    看不到它（既有 SCALE-11 Ownership Enforce 不變量，本票不改）。"""
    protected_owner_id = "the-protected-owner"
    ensure_protected_owner(storage, protected_owner_id)
    _configure_owner_historical_iv(storage, protected_owner_id, token=TOKEN)

    requester = _client(storage=storage,
                        identity_resolver=lambda: "a-different-anonymous-owner",
                        cookies=role_cookies(storage, "superuser"),
                        contract_history=_RecordingContractHistory())
    sid = _create_and_refresh(requester)

    as_protected_owner = _client(
        storage=storage, identity_resolver=lambda: protected_owner_id,
        cookies=role_cookies(storage, "superuser"))
    assert as_protected_owner.get(f"/api/scenarios/{sid}").status_code == 404


# ---------- 情境 4：邊界情況——0 個或多於 1 個 protected owner ----------

def test_more_than_one_protected_owner_fails_closed_not_guessed(storage):
    """兩個 owner 都被標記 `protected`（不論怎麼發生的）——不得挑
    「第一個」將就，一律視為 Historical IV 不可用，零 vendor 呼叫。"""
    ensure_protected_owner(storage, "protected-one")
    _configure_owner_historical_iv(storage, "protected-one", token="token-one")
    ensure_protected_owner(storage, "protected-two")
    _configure_owner_historical_iv(storage, "protected-two", token="token-two")

    client = _client(storage=storage, identity_resolver=lambda: "a-requester",
                     cookies=role_cookies(storage, "superadmin"))
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    resp = client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})
    assert resp.status_code == 403
    assert resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL


def test_zero_protected_owner_among_several_unprotected_owners_fails_closed(
        storage):
    ensure_owner(storage, "unrelated-1", protected=False)
    ensure_owner(storage, "unrelated-2", protected=False)

    client = _client(storage=storage, identity_resolver=lambda: "a-requester",
                     cookies=role_cookies(storage, "superadmin"))
    sid = _create_and_refresh(client)
    key = _first_two_leg_candidate_key(client, sid)

    resp = client.get(f"/api/scenarios/{sid}/iv-history",
                      params={"candidate_key": key})
    assert resp.status_code == 403
    assert resp.json()["detail"] == _HISTORICAL_IV_DISABLED_DETAIL
