"""Sentry 錯誤上報接線（PB-13／#293，Anonymous Public Beta）。

**未設定 `SENTRY_DSN` 環境變數時 `init_sentry()` 直接回傳 `False`、
不 import `sentry_sdk`、不改變任何既有行為**（PB-13 Non-goals：
「不得順手改動既有邏輯」——這是一條新增的觀測接線，不是對既有請求
路徑的修改）。

PII scrubbing：`before_send` hook 在事件真的要送出前，對 request
headers（`Cookie`／`Authorization`）整個丟棄，並對事件裡的訊息／例外
文字套用既有 `diagnostics.sanitize_string()` 同一套「已知祕密值逐字
比對 → 樣式遮蔽」規則——匿名身份 cookie token 與第三方 provider
token（`owner_credentials`）都不該隨錯誤堆疊上傳到 Sentry。

**`include_local_variables=False`（release-level `/security-review`
發現並修正，PB-14／#305）**：Sentry Python SDK 預設會把每一層
stack frame 的區域變數整個 `repr()` 後上傳。`_fetch_chain()`／
`put_credential()`／`test_credential()`（`api_app/main.py`）在成功
拿到第三方 provider token 明文（`cred.token`／`req.token`）之後，
還有後續呼叫（`db.save_verification()` 等）可能拋出無關的例外
（例如 Neon 連線瞬斷）——那個當下 token 仍是活著的區域變數，若
Sentry 照預設把它連同 stack frame 一起送出，`_scrub_event()` 目前
只清 `event["exception"]["values"][].value`（例外訊息字串）與
`request` 區塊，並不會走到 `stacktrace.frames[].vars` 這一層，
token 因此會明文外洩到 Sentry 帳號。停用整個 local-variable 擷取
功能是最直接的封堵——本站的 error triage 從一開始就只依賴例外
型別／訊息與既有 Diagnostics／`/api/ops/metrics` 這條完全獨立的
自建帳本，不依賴 Sentry 顯示區域變數值，關掉它零損失。
"""
from __future__ import annotations

import os

from .diagnostics import sanitize_string, secret_forms
from .storage.factory import database_url_candidates

_STRIPPED_HEADERS = frozenset({"cookie", "authorization"})

# 已知固定 secret 的環境變數名稱——與 `main.py::_known_secrets()`
# （診斷用途，含目前設定的 provider token，request-scoped）刻意分開：
# 這裡沒有 request 可讀，只掃得到 process 環境變數層級的固定值。
# `OPS_SECRET`／`ADMIN_SECRET` 已隨舊機制退役（PB-09→AUTH-03），不再
# 被任何程式碼讀取，但仍留在這裡當防禦性冗餘——Owner 若還沒清掉這兩個
# 環境變數，一旦它們的值意外出現在例外文字裡照樣會被遮蔽（讀不到就是
# 空字串，被下面的 `if v` 濾掉，不影響行為）。`SUPERUSER_PASSWORD`／
# `SUPERADMIN_PASSWORD`（AUTH-02／#309）才是現行真正在用的軸二密碼。
_SECRET_ENV_VARS = ("CRON_SECRET", "OPS_SECRET", "ADMIN_SECRET",
                   "SUPERUSER_PASSWORD", "SUPERADMIN_PASSWORD",
                   # SECURITY-FIX-02：source key 的 HMAC secret。
                   "SOURCE_HMAC_SECRET")


def known_env_secrets() -> tuple[str, ...]:
    # #345 B-7：原值與 `.strip()` 後的形式都遮（登入比對用的是後者）。
    values = secret_forms(*(os.environ.get(n) for n in _SECRET_ENV_VARS))
    return values + database_url_candidates()


def _scrub_event(event: dict, secrets: tuple[str, ...]) -> dict:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in list(headers):
                if key.lower() in _STRIPPED_HEADERS:
                    headers[key] = "[redacted]"
        request.pop("cookies", None)
        # SECURITY-FIX-01：request body 一律不送 Sentry。登入密碼
        # （`/api/auth/login`）與 provider credential（`PUT /api/settings/
        # credentials/*`）都在 JSON body 裡——Sentry 的 FastAPI／Starlette
        # 整合會把 body 放進 `request.data`，這裡整塊拿掉，不靠逐欄位
        # 遮蔽（漏遮一個欄位名就是明文外洩）。
        request.pop("data", None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?")[0]
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = sanitize_string(message, secrets=secrets)
    exc = event.get("exception")
    if isinstance(exc, dict):
        for value in exc.get("values") or []:
            if isinstance(value.get("value"), str):
                value["value"] = sanitize_string(value["value"], secrets=secrets)
    return event


def init_sentry() -> bool:
    """回傳是否真的初始化了。缺 `SENTRY_DSN` 時回 `False`，此時**不**
    `import sentry_sdk`——本票不得讓未設定 Sentry 的部署多付任何
    import 成本或行為差異。"""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False

    import sentry_sdk

    secrets = known_env_secrets()

    def before_send(event, hint):  # noqa: ARG001 — sentry_sdk 契約要求的簽章
        return _scrub_event(event, secrets)

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("VERCEL_ENV", "development"),
        release=os.environ.get("VERCEL_GIT_COMMIT_SHA"),
        # FREE-FIRST（spec §13）：免費層 5,000 events/月，不開
        # performance tracing——那會用掉遠更多配額且本票不需要。
        traces_sample_rate=0.0,
        send_default_pii=False,
        include_local_variables=False,
        before_send=before_send,
    )
    return True
