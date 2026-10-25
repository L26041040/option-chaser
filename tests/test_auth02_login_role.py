"""AUTH-02（#309，spec #307）：三層角色模型（`normal < superuser <
superadmin`）的登入／狀態查詢。OPTION-CHASER-CROSS-DEVICE-ACCOUNT-001 起：
登入＝這台裝置登入唯一的主帳號（發一顆新憑證，權限依這次輸入的密碼掛在
**這顆憑證**上）；「重設權限」＝這台裝置登出主帳號；不再有 role
session／role cookie。跨裝置的完整驗證在 `tests/test_cross_device_account.py`。

沿用第 1 個接縫（HTTP API）。`base_url="https://testserver"` 比照
`test_pb02_cookie_identity.py`／`test_pb09_superuser.py` 既有慣例，
讓 `Secure` cookie 在同一個 client 的多次請求之間正確 round-trip；
「重開瀏覽器」用捨棄舊 client、把 cookie 值移植進一個全新
`TestClient` 模擬（同一個 `app` 物件，代表 server 沒有重啟，只是
client 端的瀏覽器行程重開了）。

`resolve_credential`／`set_owner_role` 的儲存層契約在
`tests/test_storage_contract.py`，這裡不重複驗證。
"""
import inspect

from fastapi.testclient import TestClient

from api_app import superuser
from api_app.main import _OWNER_COOKIE_NAME, create_app
from api_app.storage import RoleSession
from api_app.storage.memory import MemoryStorage

SU_PASSWORD = "the-real-superuser-password"
SA_PASSWORD = "the-real-superadmin-password"


def _client(*, superuser_password=SU_PASSWORD, superadmin_password=SA_PASSWORD,
           storage=None):
    return TestClient(
        create_app(storage=storage or MemoryStorage(),
                  superuser_password=superuser_password,
                  superadmin_password=superadmin_password),
        base_url="https://testserver")




# ---------- 1. 登入 ----------


def test_correct_superuser_password_logs_in_as_superuser():
    r = _client().post("/api/auth/login", json={"password": SU_PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"role": "superuser"}


def test_correct_superadmin_password_logs_in_as_superadmin():
    r = _client().post("/api/auth/login", json={"password": SA_PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"role": "superadmin"}


def test_wrong_password_is_rejected():
    r = _client().post("/api/auth/login", json={"password": "not-either-password"})
    assert r.status_code == 401


def test_empty_password_is_rejected():
    r = _client().post("/api/auth/login", json={"password": ""})
    assert r.status_code == 401


def test_missing_password_field_is_rejected_by_request_validation():
    """缺欄位在 FastAPI／pydantic 層級就被擋下（422），根本走不到
    密碼比對邏輯——這本身就是不洩漏任何密碼相關資訊的失敗（連
    `_effective_superuser_password` 有沒有設定都碰不到）。"""
    r = _client().post("/api/auth/login", json={})
    assert r.status_code in (400, 422)


def test_missing_env_vars_fail_closed_regardless_of_password_sent():
    """兩把密碼皆未設定（`None`）時，任何送進來的密碼字串——包含
    剛好等於某個假想值的字串——一律 401，不存在「祕密沒設定就等於
    誰都能登入」的退化狀態。"""
    c = TestClient(create_app(storage=MemoryStorage()),
                  base_url="https://testserver")
    for payload in ({"password": "anything"}, {"password": ""}):
        r = c.post("/api/auth/login", json=payload)
        assert r.status_code == 401


def test_login_response_never_leaks_which_step_failed():
    """錯誤密碼／空密碼兩種情況的回應內容逐位元相同——不透露是哪個
    環節錯。"""
    c = _client()
    r1 = c.post("/api/auth/login", json={"password": "wrong"})
    r2 = c.post("/api/auth/login", json={"password": ""})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_successful_login_response_never_contains_the_token_or_a_password():
    c = _client()
    r = c.post("/api/auth/login", json={"password": SU_PASSWORD})
    assert r.json() == {"role": "superuser"}
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    assert token not in r.text
    assert SU_PASSWORD not in r.text
    assert SA_PASSWORD not in r.text


def test_a_trailing_newline_on_the_submitted_password_still_logs_in():
    """SW-10（#340，Owner 真機驗收）：真機回報 Super User／Super Admin
    密碼皆顯示 unauthorized——程式碼審閱（不觸碰任何真實密碼明文，
    CLAUDE.md 規則 5）找到的其中一個可能成因：使用者從密碼管理工具
    複製貼上時，剪貼簿內容經常帶著看不見的頭尾空白或換行，
    `secrets.compare_digest()` 逐位元組精確比對，多一個字元就整把
    失敗。這裡驗證登入表單這一側送出的密碼即使多帶換行／空白，也
    不會被這個原因誤擋。"""
    r = _client().post("/api/auth/login", json={"password": f"  {SU_PASSWORD}\n"})
    assert r.status_code == 200
    assert r.json() == {"role": "superuser"}


def test_a_trailing_newline_on_the_configured_password_still_logs_in():
    """同一個成因的另一半：部署平台的環境變數設定介面（透過 CLI／CI
    腳本寫入，或從別處複製貼上）也很容易在值的尾端多帶一個換行字元
    ——這裡用 DI 模擬「設定值本身帶換行」，驗證使用者送出乾淨密碼時
    仍然登入得進去，不會因為平台那一側的隱形字元被誤擋。"""
    r = _client(superuser_password=f"{SU_PASSWORD}\n",
               superadmin_password=f"{SA_PASSWORD}\n").post(
        "/api/auth/login", json={"password": SU_PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"role": "superuser"}


def test_stripping_does_not_let_a_merely_similar_password_through():
    """`.strip()` 只處理頭尾空白，不是模糊比對——中間多一個空格、或
    整串密碼只是恰好共用前綴／後綴，仍然必須整串精確相符才能登入，
    不能因為新增了 `.strip()` 就意外放寬成部分比對。"""
    r = _client().post("/api/auth/login",
                       json={"password": SU_PASSWORD.replace("-", " ", 1)})
    assert r.status_code == 401


# AUTH-P1-FIX-001（PR #344 Codex review P1）：SW-10 為了容忍部署平台在
# 環境變數尾端多帶的換行而加了 `.strip()`，但 truthy 檢查當時做在 strip
# 之前——設定值若整串只有空白（例如不小心存成一個換行字元），檢查會
# 通過、strip 後卻是空字串，再配上同樣 strip 成空字串的空密碼提交，
# `compare_digest("", "")` 為真，直接拿到該角色。
_WHITESPACE_ONLY_SECRETS = ("   ", "\n", "\t\r\n ")
_BLANKISH_SUBMISSIONS = ("", " ", "\n", "  \t\n")


def test_whitespace_only_superadmin_secret_cannot_be_matched_by_a_blank_password():
    for configured in _WHITESPACE_ONLY_SECRETS:
        c = _client(superuser_password=SU_PASSWORD, superadmin_password=configured)
        for submitted in _BLANKISH_SUBMISSIONS:
            r = c.post("/api/auth/login", json={"password": submitted})
            assert r.status_code == 401, (repr(configured), repr(submitted))
            assert c.cookies.get(_OWNER_COOKIE_NAME) is None


def test_whitespace_only_superuser_secret_cannot_be_matched_by_a_blank_password():
    for configured in _WHITESPACE_ONLY_SECRETS:
        c = _client(superuser_password=configured, superadmin_password=SA_PASSWORD)
        for submitted in _BLANKISH_SUBMISSIONS:
            r = c.post("/api/auth/login", json={"password": submitted})
            assert r.status_code == 401, (repr(configured), repr(submitted))
            assert c.cookies.get(_OWNER_COOKIE_NAME) is None


def test_both_secrets_whitespace_only_fail_closed_like_unset():
    """兩把都只有空白＝兩把都沒設定：任何提交（含空白）一律 401，跟
    `test_missing_env_vars_fail_closed_regardless_of_password_sent` 同一個
    保證。"""
    c = _client(superuser_password=" \n", superadmin_password="\t")
    for submitted in (*_BLANKISH_SUBMISSIONS, "anything", SU_PASSWORD):
        assert c.post("/api/auth/login",
                      json={"password": submitted}).status_code == 401


def test_a_whitespace_only_secret_disables_only_its_own_role():
    """其中一把只有空白時，另一把正常設定的角色照常可以登入——修正只
    讓「空白設定」視同未設定，不影響另一個角色。"""
    r = _client(superuser_password=SU_PASSWORD, superadmin_password="  \n").post(
        "/api/auth/login", json={"password": SU_PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"role": "superuser"}

    r = _client(superuser_password="\n", superadmin_password=SA_PASSWORD).post(
        "/api/auth/login", json={"password": SA_PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"role": "superadmin"}


def test_normalization_still_works_with_padding_on_both_sides():
    """頭尾空白 normalization 的既有預期（SW-10）在修正後仍成立：設定值與
    提交值兩側都帶頭尾空白時，照樣登入成功。"""
    r = _client(superuser_password=f"  {SU_PASSWORD}\n",
               superadmin_password=f"\t{SA_PASSWORD} ").post(
        "/api/auth/login", json={"password": f"\n{SA_PASSWORD}  "})
    assert r.status_code == 200
    assert r.json() == {"role": "superadmin"}


# ---------- 2. 權限掛在 user 記錄上（UNIFIED-IDENTITY-001） ----------

CRED = "x-oc-credential"


def _status(c, **kw) -> str:
    return c.get("/api/auth/status", **kw).json()["role"]


def _owner_set_cookies(r) -> list[str]:
    return [v for k, v in r.headers.multi_items()
            if k.lower() == "set-cookie" and v.startswith(_OWNER_COOKIE_NAME + "=")]


def test_no_user_is_normal_and_asking_creates_nobody():
    storage = MemoryStorage()
    c = _client(storage=storage)
    assert _status(c) == "normal"
    assert storage.list_owners() == []


def test_login_creates_exactly_one_user_and_writes_the_role_on_it():
    storage = MemoryStorage()
    c = _client(storage=storage)
    r = c.post("/api/auth/login", json={"password": SU_PASSWORD})
    assert r.json() == {"role": "superuser"}
    [owner] = storage.list_owners()
    assert owner.role == "superuser"
    # 憑證就是 owner cookie——沒有第二顆 role cookie。
    assert len(_owner_set_cookies(r)) == 1
    assert "__Host-oc_role" not in r.headers.get("set-cookie", "")
    assert storage.resolve_owner_by_token(c.cookies.get(_OWNER_COOKIE_NAME)) == owner.owner_id
    assert _status(c) == "superuser"


def test_first_login_makes_this_device_the_main_account_and_keeps_its_scenarios():
    """還沒有主帳號（全新部署）：第一台登入的裝置，它的 owner 就是主帳號。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sid = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
        "strategies": ["vertical-spread"]}).json()["id"]
    owner_id = storage.list_owners()[0].owner_id
    c.post("/api/auth/login", json={"password": SA_PASSWORD})
    assert [o.owner_id for o in storage.list_owners()] == [owner_id]
    assert storage.get_main_account() == owner_id
    assert _status(c) == "superadmin"
    assert [row["id"] for row in c.get("/api/scenarios").json()] == [sid]


def test_each_login_sets_this_devices_role_from_the_password_it_used():
    """權限看這次登入用的是哪一把密碼，不是「只升不降」——同一台裝置先用 SA
    再用 SU 登入，這台裝置就是 SU（另一台 SA 裝置不受影響，見
    `test_cross_device_account.py`）。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SA_PASSWORD})
    r = c.post("/api/auth/login", json={"password": SU_PASSWORD})
    assert r.json() == {"role": "superuser"}
    assert _status(c) == "superuser"


def test_wrong_password_neither_creates_a_user_nor_changes_a_role():
    storage = MemoryStorage()
    c = _client(storage=storage)
    assert c.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert storage.list_owners() == []


def test_role_survives_reload_a_new_tab_and_a_redeploy():
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    # 重新整理／新分頁：只帶瀏覽器存著的 cookie
    tab = TestClient(c.app, base_url="https://testserver",
                     cookies={_OWNER_COOKIE_NAME: token})
    assert _status(tab) == "superuser"
    # 重新部署：全新的 app instance，同一個資料庫
    redeployed = TestClient(
        create_app(storage=storage, superuser_password=SU_PASSWORD,
                   superadmin_password=SA_PASSWORD),
        base_url="https://testserver", cookies={_OWNER_COOKIE_NAME: token})
    assert _status(redeployed) == "superuser"
    assert len(storage.list_owners()) == 1


def test_role_survives_losing_the_cookie_through_the_local_credential():
    """cookie 不見了、本機那份還在：同一個 user、同一個權限，cookie 補發回來。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SA_PASSWORD})
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    no_cookie = _client(storage=storage)
    r = no_cookie.get("/api/auth/status", headers={CRED: token})
    assert r.json() == {"role": "superadmin"}
    [reissued] = _owner_set_cookies(r)
    assert reissued.startswith(f"{_OWNER_COOKIE_NAME}={token};")
    assert len(storage.list_owners()) == 1


def test_reset_role_logs_this_device_out_of_the_main_account_and_keeps_it():
    """重設＝這台裝置登出主帳號：憑證作廢、換一顆還沒綁定的新憑證，這台
    裝置回到全新的匿名 Normal User；主帳號與它的劇本原封不動。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2027-01",
        "strategies": ["vertical-spread"]})
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    main = storage.get_main_account()
    assert c.post("/api/auth/reset-role").json() == {"role": "normal"}
    assert _status(c) == "normal"
    assert c.cookies.get(_OWNER_COOKIE_NAME) != token
    assert storage.resolve_owner_by_token(token) is None
    assert [o.owner_id for o in storage.list_owners()] == [main]
    assert len(storage.list_scenarios(owner=main)) == 1
    assert c.get("/api/scenarios").json() == []
    assert c.post("/api/auth/reset-role").json() == {"role": "normal"}  # 重複也優雅


def test_reset_role_without_a_user_is_graceful_and_creates_nobody():
    storage = MemoryStorage()
    r = _client(storage=storage).post("/api/auth/reset-role")
    assert r.status_code == 200 and r.json() == {"role": "normal"}
    assert storage.list_owners() == []


def test_a_legacy_role_cookie_grants_nothing_and_is_cleared():
    """AUTH-02 留下的 role session 與 `__Host-oc_role` cookie 已退役：就算
    舊列還在資料庫、舊 cookie 還在瀏覽器，也什麼權限都不給，回應順手清掉它。"""
    storage = MemoryStorage()
    storage.create_role_session(RoleSession(
        token="legacy-" + "x" * 30, role="superadmin",
        issued_at="2026-09-20T00:00:00+00:00"))
    c = _client(storage=storage)
    r = c.get("/api/auth/status",
              cookies={superuser.LEGACY_ROLE_COOKIE_NAME: "legacy-" + "x" * 30})
    assert r.json() == {"role": "normal"}
    assert f"{superuser.LEGACY_ROLE_COOKIE_NAME}=\"\"" in r.headers["set-cookie"]
    assert c.get("/api/superuser/owners").status_code == 401


# ---------- 3. 權限判斷本身 ----------

def test_current_role_does_no_password_comparison():
    """`current_role()`／`require_role()` 只讀 user 記錄上的權限——原始碼
    裡不出現任何密碼相關識別字，比對密碼只發生在登入端點。"""
    for fn in (superuser.current_role, superuser.require_role):
        source = inspect.getsource(fn).lower()
        assert "password" not in source and "secret" not in source


def test_changing_the_configured_passwords_does_not_downgrade_an_existing_user():
    """權限永久保留：換掉環境變數裡的密碼重新部署，已經升權的 user 不受影響
    （只影響之後的登入）。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(_OWNER_COOKIE_NAME)
    rotated = TestClient(
        create_app(storage=storage, superuser_password="rotated-su",
                   superadmin_password="rotated-sa"),
        base_url="https://testserver", cookies={_OWNER_COOKIE_NAME: token})
    assert _status(rotated) == "superuser"
    assert rotated.post("/api/auth/login",
                        json={"password": SU_PASSWORD}).status_code == 401
