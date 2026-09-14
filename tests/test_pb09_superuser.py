"""PB-09（#298，Anonymous Public Beta）：User Level（軸二）端到端硬性
需求驗證。

`api_app/superuser.py` 本身的純函式行為（`is_superuser()`／
`require_superuser()` 的 fail-closed、常數時間比對）與軸一完全獨立
（無 `owner_id` 參數）已由該模組自己的 docstring 記錄設計；本檔案要
證明的是 spec §6 對**接線後**的整體行為要求，逐條在 HTTP seam 上
用真實 `TestClient` 驗證，而非只靠零散散落在各張票各自測試檔裡的
間接佐證：

1. 全站只有一把 `ADMIN_SECRET`——同一把密鑰同時解鎖 `/api/ops/
   metrics` 與 `owner_credentials` 三個寫入端點，不必為不同功能
   各自申請不同密鑰。
2. Super User capability 只能由伺服器自行驗證 `Authorization` 標頭
   判定——任何 client 端可操縱的欄位（cookie、query string、自訂
   標頭）都不能讓伺服器誤判成 Super User。
3. 軸一（owner_id）不受軸二影響——帶不帶、對不對 `ADMIN_SECRET`
   都不改變同一個 cookie 解析出的 owner_id 是誰。
4. `CRON_SECRET` 與 `ADMIN_SECRET` 互相隔離——兩把服務不同信任邊界
   的 service credential，一把打不開另一把守的端點。
5. Normal User 無法自行升級——沒有任何 API 路徑能讓一般請求，在
   沒有正確 `ADMIN_SECRET` 的情況下取得 Super User 能力。

沿用既有第 1 個接縫（HTTP API）。`base_url="https://testserver"`
比照 `test_pb02_cookie_identity.py` 既有慣例，讓 Secure cookie 在
同一個 client 的多次請求之間正確 round-trip。
"""
import ast
import inspect

from fastapi.testclient import TestClient

from api_app import superuser
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage

ADMIN_SECRET = "the-real-admin-secret"
CRON_SECRET = "the-real-cron-secret"


def _client(*, admin_secret=ADMIN_SECRET, cron_secret=CRON_SECRET,
           headers=None, storage=None):
    return TestClient(
        create_app(storage=storage or MemoryStorage(),
                  admin_secret=admin_secret, cron_secret=cron_secret),
        base_url="https://testserver", headers=headers or {})


ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN_SECRET}"}
CRON_AUTH = {"Authorization": f"Bearer {CRON_SECRET}"}

# 四個受 Super User 保護的端點（AC 逐一列舉，供「單一驗證機制」與
# 「Normal User 無法自行升級」兩組測試共用）。
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


def test_the_same_admin_secret_unlocks_every_protected_endpoint():
    """同一把 `ADMIN_SECRET`，不必為 metrics 與 credential 兩種完全
    不同性質的功能各自另外申請一把——這是 spec §6 第 1 點的字面
    要求，不是巧合成立。"""
    c = _client(headers=ADMIN_AUTH)
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code != 401, f"{method} {path}: {r.status_code} {r.text}"


def test_a_bare_client_with_no_authorization_header_is_rejected_everywhere():
    c = _client()
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_a_wrong_secret_is_rejected_everywhere_not_just_missing():
    """401 不是只有「沒帶」才會發生——帶了但帶錯，一樣是 401，兩者
    對外行為一致（`superuser.require_superuser()` docstring 明文
    要求，這裡從 HTTP 層驗證）。"""
    c = _client(headers={"Authorization": "Bearer definitely-not-it"})
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_admin_secret_not_configured_fails_closed_on_every_endpoint():
    """全站沒設定 `ADMIN_SECRET`（`None`）時，即使呼叫端剛好帶對了
    字面值，也一律 401——不存在「祕密沒設定就等於誰都是 Super User」
    這種退化狀態。"""
    c = _client(admin_secret=None, headers=ADMIN_AUTH)
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


# ---------- 2. Super User capability 只能由伺服器驗證 ----------


def test_status_endpoint_never_trusts_client_supplied_hints():
    """query string／自訂標頭這類 client 完全可操縱的欄位一律被
    忽略——只有真正的 `Authorization` 標頭內容決定答案。"""
    c = _client()
    r = c.get("/api/superuser/status?is_superuser=true",
              headers={"X-Superuser": "true", "X-Is-Admin": "1"})
    assert r.status_code == 200
    assert r.json() == {"is_superuser": False}


def test_status_endpoint_reports_true_only_with_the_correct_secret():
    c = _client(headers=ADMIN_AUTH)
    assert c.get("/api/superuser/status").json() == {"is_superuser": True}

    c_wrong = _client(headers={"Authorization": "Bearer nope"})
    assert c_wrong.get("/api/superuser/status").json() == {"is_superuser": False}

    c_none = _client()
    assert c_none.get("/api/superuser/status").json() == {"is_superuser": False}


def test_status_endpoint_is_always_200_regardless_of_secret_correctness():
    """查『自己現在算不算 Super User』不該需要先證明自己是 Super
    User 才查得到答案（雞生蛋問題）——三種情況都是 200，差別只在
    布林值本身。"""
    for headers in (ADMIN_AUTH, {"Authorization": "Bearer wrong"}, {}):
        r = _client(headers=headers).get("/api/superuser/status")
        assert r.status_code == 200


# ---------- 3. 軸一（owner_id）不受軸二影響 ----------


def test_admin_secret_presence_does_not_change_which_owner_a_cookie_resolves_to():
    """同一個 cookie，不論這次請求有沒有附帶（或附帶對不對）
    `ADMIN_SECRET`，解析出來的 owner 必須是同一個——`is_superuser()`
    的簽章裡根本沒有 `owner_id` 參數，這裡從 HTTP 層驗證這件事真的
    落地成一致的可觀察行為。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    c.get("/api/scenarios")  # lazy creation：建立一個 owner，拿到 cookie
    assert len(storage.list_owners()) == 1
    owner_id = storage.list_owners()[0]

    # 同一個 cookie jar，這次再附上有效的 Authorization 標頭。
    c.headers.update(ADMIN_AUTH)
    c.get("/api/scenarios")
    assert storage.list_owners() == [owner_id]  # 沒有多生出第二個 owner

    # 反過來，帶錯的 Authorization 也不該讓它變成別的 owner。
    c.headers.update({"Authorization": "Bearer wrong"})
    c.get("/api/scenarios")
    assert storage.list_owners() == [owner_id]


def test_superuser_status_endpoint_does_not_create_or_touch_any_owner():
    """`/api/superuser/*` 前綴整段排除在 lazy owner creation 之外
    （PB-02 既有機制），這裡從軸二自己的端點角度重新驗證一次，
    確保兩軸真的各自獨立、互不牽動對方的副作用。"""
    storage = MemoryStorage()
    c = _client(storage=storage, headers=ADMIN_AUTH)
    c.get("/api/superuser/status")
    assert storage.list_owners() == []


# ---------- 4. 兩把 service credential 互相隔離 ----------


def test_the_cron_secret_does_not_unlock_any_superuser_endpoint():
    c = _client(headers=CRON_AUTH)
    for method, path in _PROTECTED_ROUTES:
        r = _call(c, method, path)
        assert r.status_code == 401, f"{method} {path}: {r.status_code}"


def test_the_admin_secret_does_not_unlock_the_cron_endpoint():
    c = _client(headers=ADMIN_AUTH)
    r = c.get("/api/cron/warm-rate-cache")
    assert r.status_code == 401


def test_the_correct_cron_secret_still_works_on_its_own_endpoint():
    """隔離不是「兩把都失效」——各自對自己的端點依然正常運作，
    只是不能跨過去解鎖對方。"""
    c = _client(headers=CRON_AUTH)
    r = c.get("/api/cron/warm-rate-cache")
    assert r.status_code != 401


# ---------- 5. Normal User 無法自行升級 ----------


def test_no_request_without_the_correct_secret_can_ever_reach_a_protected_handler():
    """窮舉：完全沒有標頭／隨便亂帶標頭／帶對但值錯／帶另一把合法
    但不對題的 service secret——四種「不是那把 ADMIN_SECRET 本身」
    的情況，沒有一種能碰到受保護端點背後的邏輯（一律在
    `require_superuser()` 就被攔下、回應內容不含任何端點自身的
    資料）。"""
    attempts = [
        {},
        {"Authorization": "not-even-bearer-shaped"},
        {"Authorization": "Bearer "},
        CRON_AUTH,
    ]
    for headers in attempts:
        c = _client(headers=headers)
        r = c.get("/api/ops/metrics")
        assert r.status_code == 401, f"{headers}: {r.status_code} {r.text}"
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


def test_is_superuser_signature_has_no_owner_parameter():
    """比對 signature 而非只信任 docstring 的宣稱——`is_superuser()`
    物理上就沒有能力讀取任何 owner_id，不是「寫了但沒用到」。"""
    params = set(inspect.signature(superuser.is_superuser).parameters)
    assert "owner_id" not in params
    assert "owner" not in params
