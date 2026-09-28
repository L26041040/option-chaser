"""【臨時】CLAUDE-DB-HYGIENE-008：Production cold-start 一次性資料修復 hook。

Production 的 DB 連線只存在於 Vercel runtime，所以把已核對過 dry-run 的
canonical 修復（`data_lifecycle.plan()`／`execute()`）掛在 serverless
進入點（`api/index.py`）的 cold start 上跑一次。**不重寫任何 migration
SQL**，也不新增任何 route。migration 完成後由 cleanup PR 整個移除本檔、
`api/index.py` 的那一行呼叫、`/api/health` 的 `db_rescue` 欄位與對應測試。

安全條件：
- 只在 `VERCEL_ENV == "production"` 時動作，其餘環境直接 return。
- 跨 process：先在一條獨立連線上開 transaction 取
  `pg_try_advisory_xact_lock(固定 key)`——拿不到代表別的 instance 正在跑，
  直接跳過、不等待、不並行施工。用 transaction-level lock 是因為
  Production 走 Neon 的 pooled（transaction pooling）端點，session-level
  advisory lock 在那種連線池上不可靠。
- 拿到 lock 先跑 `plan()`：已經是完成狀態就 no-op；有衝突或 target 不存在
  就停手不施工；還有工作才呼叫 `execute()`（兩個原子段，失敗會 rollback）。
- 任何例外都吞掉、只記 sanitized 訊息，不影響 app 啟動；process 內一次性，
  下一次 cold start 自然重試。
- 記錄與 `/api/health` 只出現計數與狀態，絕不出現 DATABASE_URL、token、
  credential、cookie、owner_id 或例外原文。
"""
from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Iterator
from datetime import datetime, timezone

from . import data_lifecycle

TARGET_OWNER_ID = "qcPzOu1c8bMaicVX2dqk67ETDHmk_MZ6oA9dN1Hizlg"

# 固定、可重現的 advisory lock key（"OCDB" + 0x0008，落在 signed bigint 內）。
ADVISORY_LOCK_KEY = 0x4F434442_0008

_logger = logging.getLogger(__name__)

# `/api/health` 讀這份（只含計數與狀態）；cleanup PR 一併移除。
STATUS: dict = {}


@contextlib.contextmanager
def _postgres_advisory_lock(dsn: str) -> Iterator[bool]:
    """在獨立連線的 transaction 裡嘗試取 xact advisory lock；yield 是否拿到。
    離開時 rollback，lock 隨 transaction 結束釋放。"""
    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        try:
            row = conn.execute("SELECT pg_try_advisory_xact_lock(%s)",
                               (ADVISORY_LOCK_KEY,)).fetchone()
            yield bool(row and row[0])
        finally:
            conn.rollback()


def _pending_work(plan: dict) -> list[str]:
    """plan 裡還沒完成的項目（空清單＝已完成）。retention 是每日 cron 本來
    就在做的滑動視窗清理，不算「修復未完成」。"""
    planned = plan["planned"]
    pending = []
    if plan["null_owner_legacy"]["scenarios"]:
        pending.append("null_owner_scenarios")
    if any(plan["solo"]["rows"].values()):
        pending.append("solo_rows")
    if plan["legacy_singleton_tables"].get("present"):
        pending.append("legacy_singleton_tables")
    if any(planned["null_lineage_rows_claimed"].values()):
        pending.append("null_lineage")
    if planned["current_results_reconstructed"]:
        pending.append("current_results")
    if planned["fact_context_backfilled"]:
        pending.append("fact_context")
    if planned["legacy_result_views_cleared"]:
        pending.append("legacy_views")
    if planned["retired_tables_dropped"]:
        pending.append("retired_tables")
    if not plan["target_owner"]["protected"]:
        pending.append("target_protected")
    return pending


def _state(plan: dict) -> dict:
    """plan 的 sanitized 摘要：只有計數與表名。"""
    planned = plan["planned"]
    return {
        "target_exists": plan["target_owner"]["exists"],
        "target_protected": plan["target_owner"]["protected"],
        "target_total_scenarios": plan["target_owner"]["total_scenarios"],
        "target_active_scenarios": plan["target_owner"]["active_scenarios"],
        "null_owner_scenarios": plan["null_owner_legacy"]["scenarios"],
        "solo_rows": sum(plan["solo"]["rows"].values()),
        "conflicts": len(plan["conflicts"]),
        "current_results_to_reconstruct": planned["current_results_reconstructed"],
        "current_results_unrecoverable": len(planned["current_results_unrecoverable"]),
        "fact_context_to_backfill": planned["fact_context_backfilled"],
        "fact_context_impossible": planned["fact_context_impossible"],
        "legacy_views_to_clear": planned["legacy_result_views_cleared"],
        "retired_tables_present": list(planned["retired_tables_dropped"]),
    }


def _verification(db) -> dict:
    """canonical 的唯讀驗證（execute 內部用的同一組檢查），只回問題數量。"""
    settings = db.owner_settings_bundle(TARGET_OWNER_ID)
    return {
        "migration_problems": len(data_lifecycle._verify_migration(
            db, TARGET_OWNER_ID, db.legacy_settings_bundle())),
        "cleanup_problems": len(data_lifecycle._verify_cleanup(
            db, TARGET_OWNER_ID)),
        "result_views": db.result_view_stats(),
        "target_settings": settings.settings is not None,
        "target_credential_providers": len(settings.credentials),
        "target_verification_providers": len(settings.verifications),
    }


def _summary(result: dict) -> dict:
    """execute() 回傳值的 sanitized 版本（拿掉 owner_id 與劇本 id）。"""
    return {
        "legacy_adopted_into_solo": result.get("legacy_adopted_into_solo"),
        "solo_migrated": result.get("solo_migrated"),
        "null_lineage_claimed": result.get("null_lineage_claimed"),
        "current_results_reconstructed": result.get("current_results_reconstructed"),
        "current_results_unrecoverable": len(
            result.get("current_results_unrecoverable") or []),
        "fact_context_backfilled": result.get("fact_context_backfilled"),
        "fact_context_impossible": result.get("fact_context_impossible"),
        "legacy_result_views_cleared": result.get("legacy_result_views_cleared"),
        "retention": result.get("retention"),
        "rate_limit_rows_purged": result.get("rate_limit_rows_purged"),
        "retired_tables_dropped": result.get("retired_tables_dropped"),
        "target_active_before": result.get("before", {}).get("target_active_scenarios"),
        "target_active_after": result.get("after", {}).get("target_active_scenarios"),
    }


def _record(status: str, **fields) -> None:
    STATUS.clear()
    STATUS.update({"status": status, **fields,
                   "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _logger.warning("DB-HYGIENE-008 %s %s", status, fields)


def run(env: dict[str, str] | None = None, *,
        storage_factory: Callable | None = None,
        lock: Callable | None = None,
        now: Callable[[], datetime] | None = None) -> None:
    """cold start 呼叫一次。永不拋例外。參數只供測試注入假體。"""
    env = os.environ if env is None else env
    if env.get("VERCEL_ENV") != "production":
        return
    try:
        from .storage.factory import database_url, storage_from_env
        dsn = database_url(env)
        if not dsn:
            _record("skipped_no_database")
            return
        lock = lock or _postgres_advisory_lock
        with lock(dsn) as acquired:
            if not acquired:
                _record("skipped_lock_held")
                return
            db = (storage_factory or storage_from_env)(env)
            clock = now or (lambda: datetime.now(timezone.utc))
            plan = data_lifecycle.plan(db, target_owner_id=TARGET_OWNER_ID,
                                       now=clock())
            state = _state(plan)
            if not plan["target_owner"]["exists"]:
                _record("blocked_target_missing", plan=state)
                return
            if plan["conflicts"]:
                _record("blocked_conflicts", plan=state)
                return
            pending = _pending_work(plan)
            if not pending:
                _record("noop_already_complete", plan=state,
                        verification=_verification(db))
                return
            result = data_lifecycle.execute(
                db, target_owner_id=TARGET_OWNER_ID, now=clock())
            after = _state(data_lifecycle.plan(
                db, target_owner_id=TARGET_OWNER_ID, now=clock()))
            _record("completed", pending_before=pending, summary=_summary(result),
                    plan_after=after, verification=_verification(db))
    except data_lifecycle.MaintenanceError as e:
        # canonical 已整段 rollback；訊息冒號後面可能帶劇本 id，只留前綴類別
        # （例如「搬遷驗證失敗，已整段 rollback」）。
        _record("failed_maintenance_error", reason=str(e).split("：")[0][:80])
    except Exception as e:  # noqa: BLE001 — 絕不讓修復拖垮 app 啟動
        # 例外原文可能帶連線細節，只記類別名。
        _record("failed_exception", error_type=type(e).__name__)
