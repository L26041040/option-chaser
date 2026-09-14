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
"""
from __future__ import annotations

import os

from .diagnostics import sanitize_string
from .storage.factory import database_url_candidates

_STRIPPED_HEADERS = frozenset({"cookie", "authorization"})

# 已知固定 secret 的環境變數名稱——與 `main.py::_known_secrets()`
# （診斷用途，含目前設定的 provider token，request-scoped）刻意分開：
# 這裡沒有 request 可讀，只掃得到 process 環境變數層級的固定值。
# `ADMIN_SECRET` 尚未在本輪其餘票之前存在，先列進來不影響行為（讀不到
# 就是空字串，被下面的 `if v` 濾掉）。
_SECRET_ENV_VARS = ("CRON_SECRET", "OPS_SECRET", "ADMIN_SECRET")


def known_env_secrets() -> tuple[str, ...]:
    values = tuple(v for v in (os.environ.get(n) for n in _SECRET_ENV_VARS) if v)
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
        before_send=before_send,
    )
    return True
