"""依環境變數挑儲存後端（V2／#50）。

有連線字串就用 Postgres，沒有就退回記憶體假體。**退回是刻意可見的**
——`/api/health` 會回報 `storage: "memory"`，因為在正式部署上這等於
環境變數沒設好、資料不會存活；靜默退回才是危險的。

Vercel 的 Neon 整合會注入好幾個變數名，這裡依序找第一個有值的：
`DATABASE_URL` 是通例，`POSTGRES_URL` 是 Vercel Marketplace 的慣用名，
`*_POOLED`／`*_POOLER` 是 Neon 的連線池端點（serverless 應優先用它，
因為每次請求都開新連線）。
"""
from __future__ import annotations

import os

from . import Storage

# 順序即優先序：連線池端點排前面（serverless 短命連線的正確選擇）。
_ENV_CANDIDATES = (
    "POSTGRES_PRISMA_URL",      # Neon/Vercel 的 pooled 連線
    "DATABASE_URL_POOLED",
    "POSTGRES_URL",
    "DATABASE_URL",
    "POSTGRES_URL_NON_POOLING",
)


def database_url(env: dict[str, str] | None = None) -> str | None:
    src = os.environ if env is None else env
    for name in _ENV_CANDIDATES:
        value = src.get(name)
        if value:
            return value
    return None


def database_url_candidates(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """目前有值的 DATABASE_URL 家族環境變數之值——**全部**，不只
    `database_url()` 挑中的那一個（DG-02／#145 診斷 redaction 用：不管
    哪個變數被設，值本身都不該有機會外洩進 diagnostic event）。"""
    src = os.environ if env is None else env
    return tuple(v for name in _ENV_CANDIDATES if (v := src.get(name)))


def storage_from_env(env: dict[str, str] | None = None) -> Storage:
    url = database_url(env)
    if not url:
        from .memory import MemoryStorage
        return MemoryStorage()
    from .postgres import PostgresStorage
    return PostgresStorage(url)
