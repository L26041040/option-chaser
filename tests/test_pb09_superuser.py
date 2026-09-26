"""PB-09（#298，Anonymous Public Beta）：User Level（軸二）端到端硬性
需求驗證。**AUTH-03（#310）機制置換**：舊 `ADMIN_SECRET`／
`is_superuser()`／`require_superuser()`（單一 Super User 層級）已整組
退役，這四個受保護端點改成 AUTH-02（#309）三層角色模型的
`require_role(minimum=Role.SUPERADMIN)`——本檔案逐條把舊斷言換成新
機制（角色由持久 role session cookie 決定，不再是每次請求比對一次
`Authorization` 標頭），**斷言意圖不變**，並新增一條 AUTH-03 才有意義
的新斷言（中間那一層 Super User 仍然進不去，證明門檻真的升級到
Super Admin 而非只是換了密碼名字）。

`api_app/superuser.py` 本身的純函式行為（`resolve_role()`／
`require_role()` 的 fail-closed、與軸一完全獨立無 `owner_id` 參數）
已由該模組自己的 docstring 記錄設計；本檔案要證明的是 spec §6 對
**接線後**的整體行為要求，逐條在 HTTP seam 上用真實 `TestClient`
驗證，而非只靠零散散落在各張票各自測試檔裡的間接佐證：

1. 全站只有一把 `SUPERADMIN_PASSWORD`（透過 `POST /api/auth/login`
   換成 role session）——同一顆 cookie 同時解鎖 `/api/ops/metrics`
   與 `owner_credentials` 三個寫入端點，不必為不同功能各自重新登入。
2. 角色只能由伺服器端 session 查表決定——任何 client 端可操縱的
   欄位（query string、自訂標頭）都不能讓伺服器誤判成任何角色。
3. 軸一（owner_id）不受軸二影響——帶不帶、對不對 role session cookie
   都不改變同一個 owner cookie 解析出的 owner_id 是誰。
4. `CRON_SECRET` 與角色 session 互相隔離——兩種服務不同信任邊界的
   機制，一個打不開另一個守的端點。
5. Normal User 無法自行升級——沒有任何 API 路徑能讓一般請求，在
   沒有正確角色 session 的情況下取得 Super User／Super Admin 能力。

沿用既有第 1 個接縫（HTTP API）。`base_url="https://testserver"`
比照 `test_pb02_cookie_identity.py` 既有慣例，讓 Secure cookie 在
同一個 client 的多次請求之間正確 round-trip；本檔案另外用「直接寫入
storage、取回 cookie 字典」的手法（`tests/_role_session.py`）建立
role session 前提狀態，不必真的打一次 `/api/auth/login`（那條路徑
本身的正確性由 `tests/test_auth02_login_role.py` 完整覆蓋）。
"""
import ast
import inspect

from fastapi.testclient import TestClient

from api_app import superuser
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from api_app.superuser import ROLE_COOKIE_NAME
from tests._role_session import role_cookies, superadmin_cookies

CRON_SECRET = "the-real-cron-secret"
SUPERUSER_PASSWORD = "the-real-superuser-password"
SUPERADMIN_PASSWORD = "the-real-superadmin-password"
CRON_AUTH = {"Authorization": f"Bearer {CRON_SECRET}"}


def _client(*, storage=None, cron_secret=CRON_SECRET, cookies=None, headers=None):
    return TestClient(
        create_app(storage=storage or MemoryStorage(), cron_secret=cron_secret,
                  superuser_password=SUPERUSER_PASSWORD,
                  superadmin_password=SUPERADMIN_PASSWORD),
        base_url="https://testserver", cookies=cookies or {}, headers=headers or {})


# 四個受 Super Admin 保護的端點（AC 逐一列舉，供「單一驗證機制」與
# 「Normal User 無法自行升級」兩組測試共用）——PB-10 新增的 7 個
# `/api/superuser/*` 跨 owner 管理端點由 `test_pb10_superuser_admin.py`
# 自己的 `_CROSS_OWNER_ROUTES` 專責覆蓋，不在這裡重複。
_PROTECTED_ROUTES = [
    ("GET", "/api/ops/metrics"),
    ("PUT", "/api/settings/credentials/marketdata-app"),
    ("POST", "/api/settings/credentials/marketdata-app/test"),
    ("DELETE", "/api/settings/credentials/marketdata-app"),
]


def _call(client, method, path):
    if method == "GET":
        return client.get(path)
    if method == "PUT":
        return client.put(path, json={"token": "whatever"})
    if method == "POST":
        return client.post(path)
    if method == "DELETE":
        return client.delete(path)
    raise AssertionError(method)


# ---------- 1. 單一驗證機制 ----------


def test_the_same_superadmin_session_unlocks_every_protected_endpoint():
    """同一顆 Super Admin role session cookie，不必為 metrics 與
    credential 兩種完全不同性質的功能各自重新登入一次——這是 spec
    §6 第 1 點的字面要求，不是巧合成立。"""
    storage = MemoryStorage()
    c = _client(storage=storage, cookies=superadmin_cookies(storage))
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code != 401, f"{method} {path}: {r.status_code} {r.text}"


def test_a_bare_client_with_no_role_cookie_is_rejected_everywhere():
    c = _client()
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_an_unresolvable_cookie_value_is_rejected_everywhere_not_just_missing():
    """401 不是只有「沒帶」才會發生——帶了一個查不到任何 session 的
    token，一樣是 401，兩者對外行為一致（`require_role()` docstring
    明文要求，這裡從 HTTP 層驗證）。"""
    c = _client(cookies={ROLE_COOKIE_NAME: "definitely-not-a-real-token"})
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_a_superuser_session_is_rejected_everywhere_these_routes_require_superadmin():
    """AUTH-03 的核心變化：這四個端點的門檻從舊機制唯一一層的
    『Super User』升級成三層角色模型的『Super Admin』——這裡直接證明
    中間那一層（Super User）依然進不去，不是只驗證兩端（無 session／
    Super Admin），否則升級可能只是換了密碼名字、門檻其實沒變嚴。"""
    storage = MemoryStorage()
    c = _client(storage=storage, cookies=role_cookies(storage, "superuser"))
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


# ---------- 2. 角色只能由伺服器端 session 決定 ----------


def test_no_client_supplied_hint_can_forge_a_role():
    """query string／自訂標頭這類 client 完全可操縱的欄位一律被
    忽略——只有真正解析得出來的 role session cookie 內容決定答案。"""
    c = _client()
    r = c.get("/api/auth/status?role=superadmin",
              headers={"X-Superuser": "true", "X-Role": "superadmin"})
    assert r.status_code == 200
    assert r.json() == {"role": "normal"}


def test_auth_status_reports_the_correct_role_for_each_session_and_none():
    storage = MemoryStorage()
    c_admin = _client(storage=storage, cookies=superadmin_cookies(storage))
    assert c_admin.get("/api/auth/status").json() == {"role": "superadmin"}

    c_su = _client(storage=storage, cookies=role_cookies(storage, "superuser"))
    assert c_su.get("/api/auth/status").json() == {"role": "superuser"}

    c_wrong = _client(cookies={ROLE_COOKIE_NAME: "nope"})
    assert c_wrong.get("/api/auth/status").json() == {"role": "normal"}

    c_none = _client()
    assert c_none.get("/api/auth/status").json() == {"role": "normal"}


def test_auth_status_is_always_200_regardless_of_the_cookies_validity():
    """查『自己現在算哪一層角色』不該需要先證明自己是誰才查得到答案
    （雞生蛋問題）——不論帶什麼 cookie 都是 200，差別只在角色本身。"""
    for cookies in ({ROLE_COOKIE_NAME: "whatever"}, {}):
        r = _client(cookies=cookies).get("/api/auth/status")
        assert r.status_code == 200


# ---------- 3. 軸一（owner_id）不受軸二影響 ----------


def test_role_session_presence_does_not_change_which_owner_a_cookie_resolves_to():
    """同一個 owner cookie，不論這次請求有沒有附帶（或附帶對不對）
    role session cookie，解析出來的 owner 必須是同一個——`resolve_
    role()`／`require_role()` 的簽章裡根本沒有 `owner_id` 參數，這裡
    從 HTTP 層驗證這件事真的落地成一致的可觀察行為。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    # SECURITY-FIX-01：讀取不再建立 owner，建一個劇本才會。
    c.post("/api/scenarios", json={"symbol": "XYZ", "target_price": 130.0,
                                   "target_month": "2027-01",
                                   "strategies": ["vertical-spread"]}).raise_for_status()
    assert len(storage.list_owners()) == 1
    owner_id = storage.list_owners()[0]

    # 同一個 owner cookie（已經在 client 的 jar 裡），這次額外附上一顆
    # 有效的 Super Admin role session cookie——per-request cookies 與
    # jar 既有內容會合併，不會取代掉 owner cookie。
    c.get("/api/scenarios", cookies=superadmin_cookies(storage))
    assert storage.list_owners() == [owner_id]  # 沒有多生出第二個 owner

    # 反過來，帶錯的 role cookie 也不該讓它變成別的 owner。
    c.get("/api/scenarios", cookies={ROLE_COOKIE_NAME: "wrong"})
    assert storage.list_owners() == [owner_id]


def test_auth_status_endpoint_does_not_create_or_touch_any_owner():
    """`/api/auth/*` 前綴整段排除在 lazy owner creation 之外
    （PB-02 既有機制），這裡從軸二自己的端點角度重新驗證一次，
    確保兩軸真的各自獨立、互不牽動對方的副作用。"""
    storage = MemoryStorage()
    c = _client(storage=storage, cookies=superadmin_cookies(storage))
    c.get("/api/auth/status")
    assert storage.list_owners() == []


# ---------- 4. 角色 session 與 service credential 互相隔離 ----------


def test_the_cron_secret_does_not_unlock_any_superadmin_endpoint():
    c = _client(headers=CRON_AUTH)
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_a_superadmin_role_session_does_not_unlock_the_cron_endpoint():
    storage = MemoryStorage()
    c = _client(storage=storage, cookies=superadmin_cookies(storage))
    r = c.get("/api/cron/warm-rate-cache")
    assert r.status_code == 401


def test_the_correct_cron_secret_still_works_on_its_own_endpoint():
    """隔離不是「兩者都失效」——各自對自己的端點依然正常運作，
    只是不能跨過去解鎖對方。"""
    c = _client(headers=CRON_AUTH)
    r = c.get("/api/cron/warm-rate-cache")
    assert r.status_code != 401


# ---------- 5. Normal User 無法自行升級 ----------


def test_no_request_without_a_valid_role_session_can_ever_reach_a_protected_handler():
    """窮舉：完全沒有 cookie／隨便亂帶 cookie／帶對格式但查不到
    session／帶另一把合法但不對題的 service secret（CRON_SECRET
    header）——四種「不是有效 Super Admin session」的情況，沒有一種
    能碰到受保護端點背後的邏輯（一律在 `require_role()` 就被攔下、
    回應內容不含任何端點自身的資料）。"""
    attempts = [
        None,
        {ROLE_COOKIE_NAME: "not-even-close"},
        {ROLE_COOKIE_NAME: ""},
    ]
    for cookies in attempts:
        c = _client(cookies=cookies)
        r = c.get("/api/ops/metrics")
        assert r.status_code == 401, f"{cookies}: {r.status_code} {r.text}"
        assert "table_size" not in r.text

    c = _client(headers=CRON_AUTH)
    r = c.get("/api/ops/metrics")
    assert r.status_code == 401
    assert "table_size" not in r.text


# ---------- 結構性守門：兩軸程式碼互不耦合 ----------


def _code_identifiers(module) -> set[str]:
    """模組程式碼裡出現的識別字（函式／類別／參數／變數／屬性／
    匯入名），比照 `test_analysis_soft_deadline.py` 既有手法。"""
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


def test_superuser_module_never_references_owner_identity_machinery():
    """`api_app/superuser.py` 結構上不 import `api_app.identity`、
    不出現 `owner_id`／`identity_resolver`／`resolved_owner_scope`
    這類軸一專屬詞彙——這不只是慣例，是 spec §19「不得共用同一個
    函式或同一個中間結果」的可執行證明。"""
    names = _code_identifiers(superuser)
    for forbidden in ("identity", "owner_id", "identity_resolver",
                      "resolved_owner_scope", "owner_scope"):
        assert forbidden not in names, forbidden


def test_require_role_signature_has_no_owner_parameter():
    """比對 signature 而非只信任 docstring 的宣稱——`resolve_role()`／
    `require_role()` 物理上就沒有能力讀取任何 owner_id，不是「寫了
    但沒用到」。"""
    for fn in (superuser.resolve_role, superuser.require_role):
        params = set(inspect.signature(fn).parameters)
        assert "owner_id" not in params
        assert "owner" not in params


def test_the_old_two_tier_mechanism_is_fully_gone():
    """AUTH-03（#310）AC：`ADMIN_SECRET`／`is_superuser()`／
    `require_superuser()` 整組移除，不是留著沒接線的死程式碼。"""
    assert not hasattr(superuser, "is_superuser")
    assert not hasattr(superuser, "require_superuser")


# ---------- PB-14（#305）§20 補測：spec §20 八項必要測試逐一核對時
# 發現的兩個真缺口，本輪一併補齊，不留給下一輪 ----------

NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def test_superadmin_credentials_can_still_do_every_normal_user_thing():
    """§20 必要測試第 3 項：『Super User 可以執行 Normal User 的所有
    功能』（AUTH-03 之後這句話對 Super Admin 依然成立——它是完整超
    集合）。既有 `test_role_session_presence_does_not_change_which_
    owner_a_cookie_resolves_to` 只驗證 owner 身份不變，沒有真的驗證
    一次完整的 Normal User 寫入操作（建立劇本）在同時帶著有效角色
    session 的情況下依然成功——這裡補上這條，用真實 201 狀態碼與
    後續讀取確認，不是只看 owner 沒有分裂。"""
    storage = MemoryStorage()
    c = _client(storage=storage, cookies=superadmin_cookies(storage))

    created = c.post("/api/scenarios", json=NEW)
    assert created.status_code == 201, created.text

    listing = c.get("/api/scenarios")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [created.json()["id"]]

    edited = c.patch(f"/api/scenarios/{created.json()['id']}", json={
        **NEW, "notes": "仍是一般 Normal User 操作"})
    assert edited.status_code == 200, edited.text

    archived = c.post(f"/api/scenarios/{created.json()['id']}/archive")
    assert archived.status_code == 200, archived.text


def test_normal_user_cannot_self_elevate_to_superadmin_through_any_product_endpoint():
    """§20 必要測試第 7 項：『Normal User 無法透過任何操作自行升級為
    Super User／Super Admin』。本站沒有任何『升級』端點，這個安全性質
    的正確測法是反面證明：即使在一般使用者可控的請求內容（body／
    query string／自訂標頭）裡塞進看起來像是要素取角色的欄位，
    `/api/auth/status` 事後查詢的結果依然是 `normal`——沒有任何一條
    Normal User 路徑會讓伺服器把這些欄位讀成角色判準（`resolve_
    role()` 的唯一輸入是 role session cookie 本身，見
    `test_no_client_supplied_hint_can_forge_a_role`；這裡從「建立
    劇本」這個具體的 Normal User 寫入端點角度重新驗證一次）。"""
    c = _client()  # 沒有角色 cookie，純粹的 Normal User

    # 嘗試在 body／query string 塞進各種看起來像是要素取權限的欄位。
    r = c.post("/api/scenarios?role=superadmin&is_superuser=true",
              json={**NEW, "is_superuser": True, "role": "superadmin"})
    assert r.status_code == 201, r.text  # 額外欄位被忽略，建立仍正常成功

    status = c.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json() == {"role": "normal"}

    # 之後這個 owner 對受保護端點依然是 Normal User，進不去。
    protected = c.get("/api/ops/metrics")
    assert protected.status_code == 401
