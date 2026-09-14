"""User Level（軸二，PB-09／#298，Anonymous Public Beta）：Super User
capability——與軸一（Owner Identity／owner_id，`api_app/identity.py`）
完全獨立的第二段判斷。

```
軸一（所有人共用，含 Owner 自己）：
  Browser Identity（cookie）→ owner_id → product data

軸二（獨立於軸一）：
  Authenticated context → User Level（normal | superuser）→ capability
```

這個模組**只回答「這次請求的呼叫端有沒有證明自己是 Super User」**，
從不讀取、不參與、不影響 owner_id 的解析——`is_superuser()` 的唯一
輸入是 `Request` 本身的 `Authorization` 標頭與已解析好的
`admin_secret` 設定值，不接觸 `identity.py` 的任何函式、ContextVar
或中間結果。反過來，`identity.py`／cookie middleware 也完全不 import
這個模組。兩段程式碼各自獨立，呼叫端（`api_app/main.py` 的 HTTP
handler）分別呼叫兩者各自取得答案，這是 spec §19 明文要求的結構
（不得共用同一個函式或同一個中間結果）。

**單一驗證機制**（spec §6 第 1 點）：全站只有一把 `ADMIN_SECRET`，
用它就能使用全部 Super User 介面與操作——不像 `CRON_SECRET`／
`OPS_SECRET` 那樣依信任邊界各自獨立（那兩把是 machine-to-machine
service credential，服務不同的呼叫者，本來就該各自獨立；這裡服務的
是同一個人類 Owner，要求他為不同後台功能重新輸入不同 secret 是
明確禁止的體驗）。

沿用本站既有的 `CRON_SECRET`／`OPS_SECRET`「`Authorization: Bearer
<secret>`、逐字比對、fail-closed 401」慣例（`main.py` 的
`cron_warm_rate_cache()`／舊版 `ops_metrics()`），但改用
`secrets.compare_digest()` 做常數時間比對——這是全輪授權面第二寬的
邊界（僅次於軸一 cookie 本身），值得比既有兩把 service credential
多一分防護。

**「知道某個 owner_id」不等於「取得 Super User」**——這件事在這個
模組裡是結構性成立的，不是靠約定：`is_superuser()` 的簽章裡根本
沒有 `owner_id` 這個參數，它完全無法讀取呼叫端的 owner_id 是什麼，
自然也就無從「根據 owner_id 判斷」。
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request


def is_superuser(request: Request, *, admin_secret: str | None) -> bool:
    """單一 Super User 判斷點。`admin_secret` 未設定（`None`／空字串）
    時**一律回 `False`**——fail-closed，不存在「祕密沒設定就等於誰都
    是 Super User」這種退化狀態。"""
    if not admin_secret:
        return False
    provided = request.headers.get("authorization")
    if not provided:
        return False
    return secrets.compare_digest(provided, f"Bearer {admin_secret}")


def require_superuser(request: Request, *, admin_secret: str | None) -> None:
    """HTTP handler 用的 fail-closed 守門——比照既有 `cron_secret`／
    `ops_secret` 端點「驗證失敗一律 401」的既有慣例，不區分「沒帶
    憑證」與「帶錯憑證」（兩者對外都應該看起來一樣，不洩漏哪一種
    情況成立）。"""
    if not is_superuser(request, admin_secret=admin_secret):
        raise HTTPException(status_code=401, detail="unauthorized")
