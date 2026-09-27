"""資料生命週期：retention 政策與一次性的 Production 資料修復
（CLAUDE-DB-HYGIENE-002）。

兩個呼叫端共用這一份：

- 每日 cron（`/api/cron/cleanup-abandoned-owners`）呼叫 `run_retention()`，
  讓 snapshots／role sessions／audit log／events 保持有界；
- `scripts/repair_production_data_lifecycle.py` 呼叫 `plan()`（dry-run，
  零寫入）與 `execute()`（`--confirm`）——Production 只需要這一個指令，
  不需要手動 SQL。

`execute()` 分兩個原子段落（`Storage.transaction()`）：

A. 搬遷段：legacy singleton 收進 `solo` → `solo` 搬到 target（預檢衝突、
   fail closed）→ NULL-owner 劇本血緣救援 → 重建舊劇本的
   `current_results` → 標記 target 為 protected → 驗證。任何一步失敗，
   A 整段 rollback，不會留下半搬遷狀態。
B. 清理段：補 SCALE-01 fact context → 清掉已補齊列的 legacy
   `results.view` → retention → DROP 已退役的表 → 驗證。

全部步驟都是條件式的，重跑是安全的 no-op。整份模組**從不**輸出
credential／token／cookie／IP 的值，只輸出列數與描述。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from option_chaser import store

from . import abuse_control, superuser
from .identity import SOLO_OWNER
from .storage import (LEGACY_SINGLETON_TABLES, RETIRED_TABLES,
                      OwnerMigrationConflict, OwnerSettingsBundle, ResultRecord,
                      Storage, settings_bundle_merge_plan)
from .storage.backfill import FACT_FIELDS, derive_fact_context

# ---------- Retention 政策（Owner 裁示，CLAUDE-DB-HYGIENE-002） ----------

# Snapshot：每個劇本最新一份永遠保留；歷史份最多 30 天、且最多 10 份
# （兩者取較緊者）。
SNAPSHOT_HISTORY_DAYS = 30
SNAPSHOT_HISTORY_MAX = 10
# 撤銷超過 30 天的 role session 刪掉；超過 role cookie Max-Age 的也刪
# （瀏覽器已經不可能再送出那顆 token）。
ROLE_SESSION_REVOKED_RETENTION_DAYS = 30
ROLE_SESSION_MAX_AGE_SECONDS = superuser.ROLE_COOKIE_MAX_AGE_SECONDS
# Super User audit log 與 scenario events 都保留 180 天。
AUDIT_LOG_RETENTION_DAYS = 180
EVENT_RETENTION_DAYS = 180


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def run_retention(db: Storage, *, now: datetime, dry_run: bool = False) -> dict:
    """snapshots／role sessions／audit log／events 的保留期清理。回傳各項
    刪掉（`dry_run` 時：會刪）的列數。`diagnostics`／`operational_metrics`／
    `rate_limits` 維持各自既有的 retention，不在這裡。"""
    return {
        "snapshots": db.purge_snapshots(
            historical_since=_iso(now - timedelta(days=SNAPSHOT_HISTORY_DAYS)),
            max_historical=SNAPSHOT_HISTORY_MAX, dry_run=dry_run),
        "role_sessions": db.purge_role_sessions(
            revoked_before=_iso(
                now - timedelta(days=ROLE_SESSION_REVOKED_RETENTION_DAYS)),
            issued_before=_iso(
                now - timedelta(seconds=ROLE_SESSION_MAX_AGE_SECONDS)),
            dry_run=dry_run),
        "audit_log": db.purge_audit_events(
            before=_iso(now - timedelta(days=AUDIT_LOG_RETENTION_DAYS)),
            dry_run=dry_run),
        "events": db.purge_events(
            before=_iso(now - timedelta(days=EVENT_RETENTION_DAYS)),
            dry_run=dry_run),
    }


# ---------- 舊劇本的 current_results 重建（SCALE-16 之前的劇本） ----------


def _usable_legacy_view(view) -> bool:
    return isinstance(view, dict) and isinstance(view.get("results"), list)


def _current_record_from_legacy(rec: ResultRecord) -> ResultRecord:
    """用 SCALE-16 之前的 ledger 列（帶完整 `view`）組出一筆 current
    materialization：套用今天寫入路徑同一套持久化剝除規則
    （`store.strip_persisted_all_candidates()`），summary 欄位優先沿用那一列
    自己存的值；只有那一列沒存、而同一份 view 可以確定推導出來時才推導
    （跟 `_refresh_and_save()` 用同一組純函式），絕不捏造。"""
    view = rec.view
    per_family = rec.per_family
    if per_family is None:
        try:
            per_family = store.representative_candidates_by_family(view) or None
        except Exception:  # noqa: BLE001 — 舊 view 形狀推導不出來就維持缺值，不捏造
            per_family = None
    representative = rec.representative_candidate
    best_return = rec.best_return
    if representative is None and per_family:
        representative = max(per_family.values(),
                             key=lambda v: v["baseline_return"])
    if best_return is None and representative is not None:
        best_return = representative.get("baseline_return")
    spot = rec.spot if rec.spot is not None else store.spot(view)
    family_eligibility = (rec.family_eligibility
                          if rec.family_eligibility is not None
                          else view.get("family_eligibility"))
    fact = derive_fact_context(view) or {}
    return dataclasses.replace(
        rec, view=store.strip_persisted_all_candidates(view),
        best_return=best_return, representative_candidate=representative,
        spot=spot, per_family=per_family, family_eligibility=family_eligibility,
        **{k: getattr(rec, k) if getattr(rec, k) is not None else fact.get(k)
           for k in FACT_FIELDS})


@dataclass
class ReconstructReport:
    reconstructed: list[str] = field(default_factory=list)
    unrecoverable: list[str] = field(default_factory=list)


def reconstruct_current_results(db: Storage, *, owner: str,
                                dry_run: bool = False) -> ReconstructReport:
    """`owner` 名下（含已封存）還沒有 `current_results` 的劇本：用它最新
    一筆帶有可用 `view` 的歷史結果重建。**不打任何 vendor**。有歷史結果、
    卻沒有任何一筆可用 view 的劇本保留、列進 `unrecoverable`，不捏造數值；
    從來沒分析過的劇本本來就沒有東西可重建，直接略過。"""
    report = ReconstructReport()
    for sc in db.list_scenarios(owner=owner, include_archived=True):
        if db.latest_result(sc.id, owner=owner) is not None:
            continue
        history = db.result_history(sc.id, owner=owner)
        if not history:
            continue            # 從來沒分析過：沒有東西可以重建，也不算失敗
        rows = [r for r in history if _usable_legacy_view(r.view)]
        if not rows:
            report.unrecoverable.append(sc.id)
            continue
        if not dry_run:
            db.save_current_result(_current_record_from_legacy(rows[-1]))
        report.reconstructed.append(sc.id)
    return report


def _plan_reconstruction(db: Storage, scenario_ids: list[str]) -> ReconstructReport:
    """dry-run 版：`owner=None` 讀（搬遷前這些劇本還不屬於 target）。"""
    report = ReconstructReport()
    for sid in scenario_ids:
        history = db.result_history(sid, owner=None)
        if not history:
            continue
        usable = any(_usable_legacy_view(r.view) for r in history)
        (report.reconstructed if usable else report.unrecoverable).append(sid)
    return report


# ---------- SCALE-01 fact context backfill ----------


@dataclass
class BackfillReport:
    backfilled: int = 0
    impossible: int = 0


def backfill_missing_fact_context(db: Storage, *,
                                  dry_run: bool = False) -> BackfillReport:
    """對仍帶著 legacy `view`、但 6 個 SCALE-01 fact 欄位不齊的 ledger 列，
    從那份 view 確定推導出 fact context 補上；推導不出來（view 形狀太舊）
    的列只計數，不捏造。只補缺的欄位，已經有值的欄位原樣保留。"""
    report = BackfillReport()
    for sc in db.list_scenarios(owner=None, include_archived=True):
        for rec in db.result_history(sc.id, owner=None):
            if rec.view is None or all(getattr(rec, f) is not None
                                       for f in FACT_FIELDS):
                continue
            fact = derive_fact_context(rec.view)
            if fact is None:
                report.impossible += 1
                continue
            report.backfilled += 1
            if not dry_run:
                db.save_result(dataclasses.replace(rec, **{
                    k: getattr(rec, k) if getattr(rec, k) is not None else v
                    for k, v in fact.items()}))
    return report


# ---------- 一次性 Production 修復 ----------


class MaintenanceError(Exception):
    """修復不能安全進行或驗證沒過。訊息只含描述與列數，不含任何秘密值。"""


def _effective_solo_bundle(db: Storage) -> OwnerSettingsBundle:
    """dry-run 用：`solo` 在「legacy 收進來之後」會長什麼樣子（legacy 只補
    solo 沒有的那幾列，跟 `adopt_legacy_settings()` 同一套規則）。"""
    solo = db.owner_settings_bundle(SOLO_OWNER)
    legacy = db.legacy_settings_bundle()
    if legacy is None:
        return solo
    return OwnerSettingsBundle(
        settings=solo.settings or legacy.settings,
        credentials={**legacy.credentials, **solo.credentials},
        verifications={**legacy.verifications, **solo.verifications})


def _null_owner_scenarios(db: Storage):
    return [sc for sc in db.list_scenarios(owner=None, include_archived=True)
            if sc.owner_id is None]


def _active(scenarios) -> int:
    return sum(1 for sc in scenarios if sc.archived_at is None)


def plan(db: Storage, *, target_owner_id: str, now: datetime) -> dict:
    """Dry-run：**零寫入**，回傳執行 `execute()` 之前要核對的全部數字。"""
    target = db.get_owner(target_owner_id)
    null_scenarios = _null_owner_scenarios(db)
    solo_scenarios = db.list_scenarios(owner=SOLO_OWNER, include_archived=True)
    target_scenarios = (db.list_scenarios(owner=target_owner_id,
                                          include_archived=True)
                        if target is not None else [])
    legacy = db.legacy_settings_bundle()
    conflicts, redundant = settings_bundle_merge_plan(
        _effective_solo_bundle(db),
        db.owner_settings_bundle(target_owner_id))
    lineage_conflicts: list[str] = []
    try:
        lineage_counts = db.claim_null_owner_lineage(
            to_owner=target_owner_id, legacy_owners=(SOLO_OWNER,), dry_run=True)
    except OwnerMigrationConflict as e:
        lineage_conflicts = list(e.conflicts)
        lineage_counts = {}
    rescue_ids = [sc.id for sc in (*null_scenarios, *solo_scenarios,
                                   *target_scenarios)]
    missing_current = [sid for sid in rescue_ids
                       if _has_no_current(db, sid, null_scenarios,
                                          solo_scenarios, target_owner_id)]
    reconstruction = _plan_reconstruction(db, missing_current)
    backfill = backfill_missing_fact_context(db, dry_run=True)
    views = db.result_view_stats()
    return {
        "target_owner": {"owner_id": target_owner_id,
                         "exists": target is not None,
                         "protected": bool(target and target.protected),
                         "active_scenarios": _active(target_scenarios),
                         "total_scenarios": len(target_scenarios)},
        "tables": db.table_row_counts(),
        "null_owner_legacy": {"scenarios": len(null_scenarios),
                              "active_scenarios": _active(null_scenarios),
                              "rows": db.owner_row_counts(None)},
        "solo": {"scenarios": len(solo_scenarios),
                 "active_scenarios": _active(solo_scenarios),
                 "rows": db.owner_row_counts(SOLO_OWNER)},
        "legacy_singleton_tables": _legacy_summary(legacy),
        "conflicts": conflicts + lineage_conflicts,
        "already_equivalent": redundant,
        "planned": {
            "null_lineage_rows_claimed": lineage_counts,
            "current_results_reconstructed": len(reconstruction.reconstructed),
            "current_results_unrecoverable": reconstruction.unrecoverable,
            "fact_context_backfilled": backfill.backfilled,
            "fact_context_impossible": backfill.impossible,
            "legacy_result_views_cleared": views["clearable"] + backfill.backfilled,
            "legacy_result_views_kept": backfill.impossible,
            "retention": run_retention(db, now=now, dry_run=True),
            "retired_tables_dropped": db.retired_tables_present(),
        },
        "expected_active_scenarios_after": (
            _active(target_scenarios) + _active(solo_scenarios)
            + _active(null_scenarios)),
    }


def _has_no_current(db: Storage, sid: str, null_scenarios, solo_scenarios,
                    target_owner_id: str) -> bool:
    """`latest_result()` 需要 owner——搬遷前每個劇本各自用它現在的 owner
    查；NULL-owner 劇本在 SCALE-16 之前建立，天生沒有 current_results。"""
    if any(sc.id == sid for sc in null_scenarios):
        return True
    owner = (SOLO_OWNER if any(sc.id == sid for sc in solo_scenarios)
             else target_owner_id)
    return db.latest_result(sid, owner=owner) is None


def _legacy_summary(legacy: OwnerSettingsBundle | None) -> dict:
    if legacy is None:
        return {"present": False}
    return {"present": True,
            "settings": legacy.settings is not None,
            "credential_providers": sorted(legacy.credentials),
            "verification_providers": sorted(legacy.verifications)}


def _verify_migration(db: Storage, target_owner_id: str,
                      legacy: OwnerSettingsBundle | None) -> list[str]:
    problems: list[str] = []
    leftover = {t: n for t, n in db.owner_row_counts(SOLO_OWNER).items() if n}
    if leftover:
        problems.append(f"solo 仍有資料：{leftover}")
    if _null_owner_scenarios(db):
        problems.append("仍有 owner_id 為 NULL 的劇本")
    lineage = db.lineage_report(target_owner_id)
    if not lineage.ok:
        problems.append(f"target 劇本血緣不一致：mismatch="
                        f"{lineage.child_owner_mismatch} orphans="
                        f"{lineage.child_orphans}")
    owner = db.get_owner(target_owner_id)
    if owner is None or not owner.protected:
        problems.append("target owner 沒有被標記為 protected")
    problems += _missing_legacy_copies(db, target_owner_id, legacy)
    return problems


def _missing_legacy_copies(db: Storage, target_owner_id: str,
                           legacy: OwnerSettingsBundle | None) -> list[str]:
    """DROP legacy 表之前的 fail-closed 檢查：legacy 的每一列在 target 的
    owner-scoped 表裡都必須有 canonical 副本。"""
    if legacy is None:
        return []
    have = db.owner_settings_bundle(target_owner_id)
    missing: list[str] = []
    if legacy.settings is not None and have.settings is None:
        missing.append("owner_settings")
    missing += [f"owner_credentials:{p}" for p in sorted(legacy.credentials)
                if p not in have.credentials]
    missing += [f"owner_verifications:{p}" for p in sorted(legacy.verifications)
                if p not in have.verifications]
    return [f"legacy 資料在 target 沒有 canonical 副本：{m}" for m in missing]


def execute(db: Storage, *, target_owner_id: str, now: datetime) -> dict:
    """`--confirm`：跑完整修復，回傳 before／after 摘要。任何不安全的狀況或
    驗證沒過都拋 `MaintenanceError`（搬遷段整段 rollback）。"""
    target = db.get_owner(target_owner_id)
    if target is None:
        raise MaintenanceError(
            f"target owner 不存在：{target_owner_id!r}——請先依 runbook 用"
            "自己的瀏覽器做一次寫入（例如建立一個劇本）讓 owner 建立")
    before = {"tables": db.table_row_counts(),
              "target_active_scenarios": _active(
                  db.list_scenarios(owner=target_owner_id))}
    summary: dict = {"target_owner_id": target_owner_id, "before": before}

    # A. 搬遷段（原子）
    try:
        with db.transaction():
            legacy = db.legacy_settings_bundle()
            summary["legacy_adopted_into_solo"] = db.adopt_legacy_settings(
                SOLO_OWNER)
            summary["solo_migrated"] = db.migrate_owner(
                from_owner=SOLO_OWNER, to_owner=target_owner_id)
            summary["null_lineage_claimed"] = db.claim_null_owner_lineage(
                to_owner=target_owner_id, legacy_owners=(SOLO_OWNER,))
            recon = reconstruct_current_results(db, owner=target_owner_id)
            summary["current_results_reconstructed"] = len(recon.reconstructed)
            summary["current_results_unrecoverable"] = recon.unrecoverable
            db.set_owner_protected(target_owner_id, True)
            problems = _verify_migration(db, target_owner_id, legacy)
            if problems:
                raise MaintenanceError("搬遷驗證失敗，已整段 rollback：" +
                                       "；".join(problems))
    except OwnerMigrationConflict as e:
        raise MaintenanceError(
            "預檢發現衝突，沒有寫入任何資料：" + ", ".join(e.conflicts)) from e

    # B. 清理段（原子）
    with db.transaction():
        backfill = backfill_missing_fact_context(db)
        summary["fact_context_backfilled"] = backfill.backfilled
        summary["fact_context_impossible"] = backfill.impossible
        summary["legacy_result_views_cleared"] = \
            db.clear_historical_result_views()
        summary["retention"] = run_retention(db, now=now)
        summary["rate_limit_rows_purged"] = db.purge_rate_limits(
            before_epoch=int(now.timestamp())
            - abuse_control.RATE_LIMIT_RETENTION_SECONDS)
        present = db.retired_tables_present()
        if any(t in LEGACY_SINGLETON_TABLES for t in present):
            missing = _missing_legacy_copies(db, target_owner_id,
                                             db.legacy_settings_bundle())
            if missing:
                raise MaintenanceError("拒絕 DROP legacy 表：" + "；".join(missing))
        summary["retired_tables_dropped"] = db.drop_retired_tables(
            [t for t in RETIRED_TABLES if t in present])
        problems = _verify_cleanup(db, target_owner_id)
        if problems:
            raise MaintenanceError("清理驗證失敗，已整段 rollback：" +
                                   "；".join(problems))

    summary["after"] = {"tables": db.table_row_counts(),
                        "target_active_scenarios": _active(
                            db.list_scenarios(owner=target_owner_id)),
                        "result_views": db.result_view_stats()}
    return summary


def _verify_cleanup(db: Storage, target_owner_id: str) -> list[str]:
    problems: list[str] = []
    if db.result_view_stats()["clearable"]:
        problems.append("仍有 fact 已補齊、卻還帶著 legacy view 的 results 列")
    if db.retired_tables_present():
        problems.append(f"已退役的表仍存在：{db.retired_tables_present()}")
    lineage = db.lineage_report(target_owner_id)
    if not lineage.ok:
        problems.append("target 劇本血緣不一致")
    # raw-data 的錨點：每個有 current result 的劇本，那個時間點的快照都必須
    # 還在——快照一份都沒有（空清單）也算違反，不能讓驗證靜默通過。
    for sc in db.list_scenarios(owner=target_owner_id, include_archived=True):
        current = db.latest_result(sc.id, owner=target_owner_id)
        if current is None:
            continue
        if current.analyzed_at not in db.snapshot_timestamps(
                sc.id, owner=target_owner_id):
            problems.append(f"劇本 {sc.id} 的最新結果沒有對應快照")
    return problems
