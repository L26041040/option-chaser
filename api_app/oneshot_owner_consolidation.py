"""【臨時】OPTION-CHASER-OWNER-CONSOLIDATION-001：Production cold-start
一次性 Owner 合併 hook。

Production 的 DB 連線只存在於 Vercel runtime（與 CLAUDE-DB-HYGIENE-008
同一個理由），所以把 `owner_consolidation.execute()` 掛在 serverless
進入點（`api/index.py`）的 cold start 上跑一次。合併完成並驗收後，cleanup
commit 整個移除本檔、`api/index.py` 的那一行呼叫、`/api/health` 的
`owner_consolidation` 欄位與對應測試；`owner_consolidation` 模組本身
（含 `rollback()`）保留。

安全條件：
- 只在 `VERCEL_ENV == "production"` 時動作，其餘環境直接 return。
- 跨 process：同一條連線、同一個 transaction 先取
  `pg_try_advisory_xact_lock(固定 key)`——拿不到就跳過、不等待、不並行
  施工（Neon transaction pooling 下 session-level lock 不可靠）。
- 合併本身與 lock 在**同一個 transaction**：預檢不符、驗證失敗或任何例外
  都整段 rollback（含備份 schema），資料零變動，下一次 cold start 重試。
- 備份 schema 已存在＝已經做過（或已回滾）：只讀狀態回報，絕不重跑。
- 記錄與 `/api/health` 只有計數、檢查名稱與狀態，絕不出現 DATABASE_URL、
  token、credential、owner_id 或例外原文。
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone

from . import owner_consolidation

# 固定、可重現的 advisory lock key（"OCDB" + 0x0009，HYGIENE-008 用過 0x0008）。
ADVISORY_LOCK_KEY = 0x4F434442_0009
# 搶輸 lock 的 instance 隔多久才回頭讀一次共享狀態（只讀）。
RECHECK_SECONDS = 30

_logger = logging.getLogger(__name__)

# `/api/health` 讀這份（只含計數與狀態）；cleanup commit 一併移除。
STATUS: dict = {}
_last_attempt = [0.0]


def _connect(dsn: str):
    import psycopg
    return psycopg.connect(dsn, connect_timeout=10, autocommit=True)


def _record(status: str, **fields) -> None:
    STATUS.clear()
    STATUS.update({"status": status, **fields,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _logger.warning("OWNER-CONSOLIDATION-001 %s %s", status, fields)


def _record_shared_state(conn) -> None:
    state = owner_consolidation.status(conn)
    if state["state"] == "not_started":
        _record("pending", mismatches=state["mismatches"],
                observed=state["observed"])
    else:
        _record(f"noop_{state['state']}", state=state)


def run(env: dict[str, str] | None = None, *,
        connect: Callable | None = None,
        prepare_schema: Callable[[str], None] | None = None,
        now: Callable[[], datetime] | None = None) -> None:
    """cold start 呼叫一次。永不拋例外。參數只供測試注入假體。"""
    env = os.environ if env is None else env
    if env.get("VERCEL_ENV") != "production":
        return
    _last_attempt[0] = time.monotonic()
    try:
        from .storage.factory import database_url
        dsn = database_url(env)
        if not dsn:
            _record("skipped_no_database")
            return
        if prepare_schema is None:
            from .storage.postgres import PostgresStorage
            PostgresStorage(dsn)._ensure_schema()
        else:
            prepare_schema(dsn)
        clock = now or (lambda: datetime.now(timezone.utc))
        with (connect or _connect)(dsn) as conn:
            with conn.transaction():
                acquired = conn.execute("SELECT pg_try_advisory_xact_lock(%s)",
                                        (ADVISORY_LOCK_KEY,)).fetchone()[0]
                if not acquired:
                    _record("skipped_lock_held")
                    return
                if owner_consolidation.backup_exists(conn):
                    _record_shared_state(conn)
                    return
                summary = owner_consolidation.execute(conn, now=clock())
            # 走到這裡＝transaction 已 commit。
            _record("completed", summary=summary)
    except owner_consolidation.PreconditionMismatch as e:
        _record("blocked_precondition", mismatches=e.mismatches,
                observed=e.observed)
    except owner_consolidation.ConsolidationError as e:
        # 訊息本來就只有檢查名稱（見 ConsolidationError docstring）。
        _record("failed_check", reason=str(e)[:120])
    except Exception as e:  # noqa: BLE001 — 絕不讓合併拖垮 app 啟動
        # 例外原文可能帶連線細節，只記類別名。
        _record("failed_exception", error_type=type(e).__name__)


def recheck_if_lock_was_held(env: dict[str, str] | None = None, *,
                             connect: Callable | None = None) -> None:
    """`/api/health` 每次呼叫：只有這個 instance 當初搶輸 lock 時，才在
    `RECHECK_SECONDS` 之後回頭**只讀**一次共享狀態——request path 上
    絕不執行合併。"""
    if STATUS.get("status") != "skipped_lock_held":
        return
    if time.monotonic() - _last_attempt[0] < RECHECK_SECONDS:
        return
    env = os.environ if env is None else env
    _last_attempt[0] = time.monotonic()
    try:
        from .storage.factory import database_url
        dsn = database_url(env)
        if not dsn:
            return
        with (connect or _connect)(dsn) as conn:
            _record_shared_state(conn)
    except Exception as e:  # noqa: BLE001
        _record("skipped_lock_held", recheck_error_type=type(e).__name__)
