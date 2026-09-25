"""AUTH-02（#309，spec #307，Anonymous Public Beta）：三層角色模型
（`normal < superuser < superadmin`）的單一判斷點＋登入／登出／狀態
查詢端點＋持久 role-session cookie。

沿用第 1 個接縫（HTTP API）。`base_url="https://testserver"` 比照
`test_pb02_cookie_identity.py`／`test_pb09_superuser.py` 既有慣例，
讓 `Secure` cookie 在同一個 client 的多次請求之間正確 round-trip；
「重開瀏覽器」用捨棄舊 client、把 cookie 值移植進一個全新
`TestClient` 模擬（同一個 `app` 物件，代表 server 沒有重啟，只是
client 端的瀏覽器行程重開了）。

本檔案只驗證 AUTH-02 新增的行為——AUTH-01（#308）的 Storage 契約
（`create_role_session`／`resolve_role_session`／`revoke_role_
session` 本身）已在 `tests/test_storage_contract.py` 驗證過，這裡
不重複驗證儲存層。
"""
import ast
import inspect

from fastapi.testclient import TestClient

from api_app import superuser
from api_app.main import create_app
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


ROLE_COOKIE = superuser.ROLE_COOKIE_NAME


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
    token = c.cookies.get(ROLE_COOKIE)
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
            assert c.cookies.get(ROLE_COOKIE) is None


def test_whitespace_only_superuser_secret_cannot_be_matched_by_a_blank_password():
    for configured in _WHITESPACE_ONLY_SECRETS:
        c = _client(superuser_password=configured, superadmin_password=SA_PASSWORD)
        for submitted in _BLANKISH_SUBMISSIONS:
            r = c.post("/api/auth/login", json={"password": submitted})
            assert r.status_code == 401, (repr(configured), repr(submitted))
            assert c.cookies.get(ROLE_COOKIE) is None


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


# ---------- 2. 角色解析 ----------


def test_no_cookie_resolves_to_normal():
    r = _client().get("/api/auth/status")
    assert r.status_code == 200
    assert r.json() == {"role": "normal"}


def test_valid_superuser_cookie_resolves_to_superuser():
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    r = c.get("/api/auth/status")
    assert r.json() == {"role": "superuser"}


def test_valid_superadmin_cookie_resolves_to_superadmin():
    c = _client()
    c.post("/api/auth/login", json={"password": SA_PASSWORD})
    r = c.get("/api/auth/status")
    assert r.json() == {"role": "superadmin"}


def test_unknown_token_resolves_to_normal():
    c = _client()
    c.cookies.set(ROLE_COOKIE, "this-token-was-never-issued-by-anyone")
    r = c.get("/api/auth/status")
    assert r.json() == {"role": "normal"}


def test_revoked_token_resolves_to_normal():
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    c.post("/api/auth/logout")
    r = c.get("/api/auth/status")
    assert r.json() == {"role": "normal"}


# ---------- 3. 持久 cookie ----------


def test_login_sets_a_correctly_flagged_persistent_cookie():
    c = _client()
    r = c.post("/api/auth/login", json={"password": SU_PASSWORD})
    set_cookie = r.headers.get("set-cookie")
    assert set_cookie is not None
    assert set_cookie.startswith(f"{ROLE_COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Domain=" not in set_cookie  # __Host- 前綴要求不得設 Domain
    assert "Max-Age=" in set_cookie  # 不是 session-only cookie
    max_age = int(set_cookie.split("Max-Age=")[1].split(";")[0])
    assert max_age > 300 * 24 * 60 * 60  # 遠超過一個典型 session 的量級


def test_cookie_value_is_neither_the_password_nor_the_role_name():
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(ROLE_COOKIE)
    assert token not in (SU_PASSWORD, SA_PASSWORD, "superuser", "superadmin")
    assert len(token) >= 32  # 密碼學安全隨機來源產生的不透明字串


def test_cookie_survives_a_simulated_browser_restart():
    """重開「瀏覽器」：捨棄整個 client（含它的 cookie jar），只把
    cookie 的值移植進一顆全新的 `TestClient`——伺服器（`app` 物件與
    底下的 storage）完全沒變，模擬的是瀏覽器行程重啟，不是伺服器
    重啟。"""
    storage = MemoryStorage()
    c1 = _client(storage=storage)
    c1.post("/api/auth/login", json={"password": SA_PASSWORD})
    token = c1.cookies.get(ROLE_COOKIE)

    c2 = TestClient(
        create_app(storage=storage, superuser_password=SU_PASSWORD,
                  superadmin_password=SA_PASSWORD),
        base_url="https://testserver")
    c2.cookies.set(ROLE_COOKIE, token)
    r = c2.get("/api/auth/status")
    assert r.json() == {"role": "superadmin"}


# ---------- 4. 登出 ----------


def test_logout_revokes_the_session_server_side():
    """不是只在瀏覽器端清掉了事——伺服器自己的 `RoleSession` 記錄也
    真的被標記撤銷（透過 AUTH-01 的 `resolve_role_session()` 之後回
    `None` 間接驗證，不直接碰 storage 內部欄位）。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(ROLE_COOKIE)
    assert storage.resolve_role_session(token) is not None

    c.post("/api/auth/logout")
    assert storage.resolve_role_session(token) is None


def test_logout_clears_the_cookie_on_the_client():
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    r = c.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"role": "normal"}
    # httpx cookie jar 會依 Set-Cookie 的清除指示自行移除這個 key。
    assert c.cookies.get(ROLE_COOKIE) is None


def test_replaying_the_old_cookie_after_logout_resolves_to_normal():
    """即使呼叫端硬是重放登出前那顆舊 cookie（例如攔截到舊值、繞過
    瀏覽器自己清除的行為），`resolve_role()` 依然回 `normal`——這是
    伺服器端撤銷的直接後果，不依賴瀏覽器乖乖清除 cookie。"""
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    token = c.cookies.get(ROLE_COOKIE)
    c.post("/api/auth/logout")

    c2 = _client()
    c2.cookies.set(ROLE_COOKIE, token)
    r = c2.get("/api/auth/status")
    assert r.json() == {"role": "normal"}


def test_logout_without_any_cookie_is_graceful_not_an_error():
    r = _client().post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"role": "normal"}


def test_repeated_logout_is_graceful():
    c = _client()
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    r1 = c.post("/api/auth/logout")
    r2 = c.post("/api/auth/logout")
    assert r1.status_code == r2.status_code == 200
    assert r2.json() == {"role": "normal"}


# ---------- 5. 正交性（軸一／軸二互不干擾） ----------


def test_login_does_not_create_or_touch_any_owner():
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    assert storage.list_owners() == []


def test_status_does_not_create_any_owner():
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.get("/api/auth/status")
    assert storage.list_owners() == []


def test_logout_does_not_delete_or_change_any_owner():
    storage = MemoryStorage()
    c = _client(storage=storage)
    # SECURITY-FIX-01：讀取不再建立 owner，建一個劇本才會。
    c.post("/api/scenarios", json={"symbol": "XYZ", "target_price": 130.0,
                                   "target_month": "2027-01",
                                   "strategies": ["vertical-spread"]}).raise_for_status()
    assert len(storage.list_owners()) == 1
    owner_id = storage.list_owners()[0]

    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    c.post("/api/auth/logout")
    assert storage.list_owners() == [owner_id]


def test_the_owner_cookie_never_changes_across_login_and_logout():
    """同一個瀏覽器（同一個 cookie jar）先建立 owner，登入／登出
    Super User 角色的整個過程中，owner cookie 的值必須逐位元不變
    ——兩顆 cookie 完全獨立，不得合併也不得互相牽動。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.get("/api/scenarios")
    owner_cookie_before = c.cookies.get("__Host-oc_owner")
    assert owner_cookie_before is not None

    c.post("/api/auth/login", json={"password": SA_PASSWORD})
    c.get("/api/scenarios")
    assert c.cookies.get("__Host-oc_owner") == owner_cookie_before

    c.post("/api/auth/logout")
    c.get("/api/scenarios")
    assert c.cookies.get("__Host-oc_owner") == owner_cookie_before


def test_scenario_ownership_is_identical_before_and_after_login():
    """同一瀏覽器登入前建立的劇本，登入 Super User／Super Admin 之後
    走一般使用者路徑（`identity_resolver()`，非 `/api/superuser/*`）
    仍然看得到、仍然是同一份——登入這個動作不改變 `owner_id` 本身。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    r = c.post("/api/scenarios", json={
        "symbol": "TLT", "target_price": 100.0, "target_month": "2028-05",
        "strategies": ["vertical-spread"]})
    assert r.status_code == 201
    scenario_id = r.json()["id"]

    c.post("/api/auth/login", json={"password": SU_PASSWORD})
    r = c.get(f"/api/scenarios/{scenario_id}")
    assert r.status_code == 200
    assert r.json()["id"] == scenario_id


def _code_identifiers(module) -> set[str]:
    """模組程式碼裡出現的識別字，比照 `test_pb09_superuser.py` 既有
    手法。"""
    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Import):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(a.asname or a.name for a in node.names)
    return names


def test_superuser_module_still_never_references_owner_identity_machinery():
    """延伸既有 `test_pb09_superuser.py` 的同一條斷言——AUTH-02 的
    新增內容（`Role`／`resolve_role`／`require_role`）與既有內容都在
    同一個檔案（`api_app/superuser.py`），這條測試涵蓋整個檔案，
    AUTH-02 新增的部分自動包含在內。"""
    names = _code_identifiers(superuser)
    for forbidden in ("identity", "owner_id", "identity_resolver",
                      "resolved_owner_scope", "owner_scope"):
        assert forbidden not in names, forbidden


def test_resolve_role_signature_has_no_owner_parameter():
    params = set(inspect.signature(superuser.resolve_role).parameters)
    assert "owner_id" not in params
    assert "owner" not in params


def test_require_role_signature_has_no_owner_parameter():
    params = set(inspect.signature(superuser.require_role).parameters)
    assert "owner_id" not in params
    assert "owner" not in params


def test_superuser_module_does_not_import_the_identity_module():
    import api_app.identity as identity_module
    import api_app.superuser as superuser_module
    assert identity_module not in vars(superuser_module).values()


# ---------- 6. 沒有密碼變更偵測／指紋機制 ----------


def test_role_session_dataclass_has_no_fingerprint_or_version_fields():
    """程式碼審查的可執行版本——AUTH-01 定義的 `RoleSession` 只有
    `token`／`role`／`issued_at`／`revoked_at` 四個欄位，沒有任何
    密碼雜湊、指紋、或 session version 欄位。"""
    fields = {f.name for f in RoleSession.__dataclass_fields__.values()}
    assert fields == {"token", "role", "issued_at", "revoked_at"}


def test_resolve_role_source_does_no_password_comparison():
    """`resolve_role()` 的原始碼裡不出現任何密碼相關識別字——它只
    查 session 記錄本身，不重新驗證密碼。"""
    source = inspect.getsource(superuser.resolve_role)
    for forbidden in ("password", "compare_digest", "secret"):
        assert forbidden not in source.lower()


def test_changing_the_configured_passwords_does_not_invalidate_an_existing_session():
    """AC 明文要求的正面驗證（非驗證失效）：換掉環境變數重新部署後，
    既有、尚未登出的 session 依然有效。用同一個 storage、換一組
    密碼重新 `create_app()` 模擬「改環境變數重新部署」。"""
    storage = MemoryStorage()
    c1 = _client(storage=storage, superuser_password="old-su-password",
                superadmin_password="old-sa-password")
    c1.post("/api/auth/login", json={"password": "old-su-password"})
    token = c1.cookies.get(ROLE_COOKIE)

    # 「重新部署」：新的密碼設定，同一個 storage（同一批既有 session）。
    c2 = TestClient(
        create_app(storage=storage, superuser_password="BRAND-NEW-su-password",
                  superadmin_password="BRAND-NEW-sa-password"),
        base_url="https://testserver")
    c2.cookies.set(ROLE_COOKIE, token)
    r = c2.get("/api/auth/status")
    assert r.json() == {"role": "superuser"}, (
        "換密碼不該讓既有 session 失效——這是 Owner 明確接受的取捨"
        "（見 #307 Further Notes、#309 2026-09-17 修正），不是漏洞")

    # 舊密碼登入新的 app 應該失敗（密碼真的換了）；新密碼應該成功。
    r = c2.post("/api/auth/login", json={"password": "old-su-password"})
    assert r.status_code == 401
    r = c2.post("/api/auth/login", json={"password": "BRAND-NEW-su-password"})
    assert r.status_code == 200
