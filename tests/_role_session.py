"""AUTH-03（#310，Anonymous Public Beta，三層角色模型 spec #307）共用
小工具：直接把一筆有效的 `RoleSession`（AUTH-01／#308）寫進 storage，
回傳可以塞給 `TestClient(..., cookies=...)`（構造時）或
`client.get(path, cookies=...)`（單次請求）的 cookie 字典。

不必真的打一次 `POST /api/auth/login`——那條路徑本身的正確性（密碼
比對、fail-closed、cookie 屬性、`SUPERADMIN_PASSWORD`／
`SUPERUSER_PASSWORD` 的優先序）已由 `tests/test_auth02_login_role.py`
33 條測試完整覆蓋；本站既有慣例本來就是測試直接寫入 storage 建立
前提狀態（例如 `storage.save_credential(...)` 直接寫入而非透過 HTTP
PUT），這裡延伸同一種手法到 role session。

已用最小重現腳本驗證：透過 `TestClient(..., cookies={...})` 構造時或
`client.get(path, cookies={...})` 單次請求時注入的 cookie，httpx 內部
一律標記為非 Secure（不是解析 `Set-Cookie` 標頭產生的），因此不論
`base_url` 是 `http://` 或 `https://` 都會正常送出——不受
`docs/pb02-cookie-testing-notes.md` 記載的「Secure cookie 只在
https scheme 下才會被送出」那個限制影響（那個限制只發生在真的透過
`Set-Cookie` 回應標頭簽發、下一次請求要不要回送的情境）。
"""
from __future__ import annotations

import secrets

from api_app.storage import RoleSession
from api_app.superuser import ROLE_COOKIE_NAME


def seed_role_session(storage, role: str, *,
                      issued_at: str = "2026-01-01T00:00:00+00:00") -> str:
    """在 `storage` 裡建立一筆有效（未撤銷）的 role session，回傳它的
    token。`role` 必須是 `"superuser"` 或 `"superadmin"`。"""
    token = secrets.token_urlsafe(16)
    storage.create_role_session(
        RoleSession(token=token, role=role, issued_at=issued_at))
    return token


def role_cookies(storage, role: str) -> dict[str, str]:
    """`seed_role_session()` 的薄殼——直接回傳可塞給
    `TestClient(..., cookies=...)` 或單次請求 `cookies=` 參數的字典。"""
    return {ROLE_COOKIE_NAME: seed_role_session(storage, role)}


def superuser_cookies(storage) -> dict[str, str]:
    return role_cookies(storage, "superuser")


def superadmin_cookies(storage) -> dict[str, str]:
    return role_cookies(storage, "superadmin")
