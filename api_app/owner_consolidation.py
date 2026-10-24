"""OPTION-CHASER-OWNER-CONSOLIDATION-001：Production 舊 Owner 資料統一合併。

把唯一 Super User 以外所有 owner 名下的資料歸入那個 Super User（target），
**整件事在呼叫端開的單一 Postgres transaction 裡完成**：

1. 唯讀預檢：重新確認唯一 Super User 與資料數量。期望值寫死在 `EXPECTED`
   （Owner 已確認的 Production 形狀），任一不符就零寫入停手。
2. 備份：在獨立 schema `BACKUP_SCHEMA` 建立可恢復的備份。
   - 身分／設定／憑證等小表（`COPY_TABLES`）整張複製；
   - 內容表（`LEDGER_TABLES`：劇本、結果、快照、事件……）合併時只會改
     `owner_id`，所以只記「主鍵 → 原本的 owner_id」帳本，不複製 MB 級
     payload（Neon 免費層容量有限）。
3. 合併：內容表依帳本把 owner_id 改成 target；設定／憑證衝突時 target
   優先，沒被採用的那份只留在備份 schema——不覆蓋 target、也不遺失。
4. 驗證完整性；通過才刪多餘的 owner、它們的 browser identity 與 owner
   quota 計數列。舊 browser identity **不**改綁到 target：舊瀏覽器下次
   來就是全新的匿名訪客，不會因為一顆舊 cookie 拿到 Super User 權限。
5. 再驗證一次。任何一步失敗都拋 `ConsolidationError`，呼叫端的
   transaction 整段 rollback（包含備份本身——沒有合併就不需要備份）。

target 的登入憑證（它自己的 browser identity）與權限（`owners.role`）
全程不動。`rollback()` 用同一份備份把 owner、identity、設定與每一列的
owner_id 還原回合併前。

輸出（`execute()`／`status()` 的回傳值）只有計數與檢查名稱；owner_id、
token、credential 只存在資料庫內的備份 schema，從不出現在回傳值裡。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from .identity import PENDING_OWNER_PREFIX
from .storage import OWNER_RATE_LIMIT_SCOPE

BACKUP_SCHEMA = "oc_backup_owner_consolidation_001"

TARGET_ROLE = "superuser"
TARGET_PREFIX = "Tcf2_BUR"


@dataclass(frozen=True)
class Expected:
    owners: int
    scenarios: int
    target_scenarios: int
    source_scenarios: int


# Owner 在 2026-10-25（台灣）確認的 Production 形狀。
EXPECTED = Expected(owners=9, scenarios=20, target_scenarios=1,
                    source_scenarios=19)

# 合併時只改 owner_id 的內容表：(表名, 主鍵欄位)。
LEDGER_TABLES = (
    ("results", ("scenario_id", "analyzed_at")),
    ("current_results", ("scenario_id",)),
    ("snapshots", ("scenario_id", "analyzed_at")),
    ("events", ("seq",)),
    ("scenarios", ("id",)),
    ("diagnostics", ("seq",)),
    ("feedback", ("seq",)),
)
# 子表：除了 source owner 的列，所屬劇本會歸 target、自己 owner_id 卻是
# NULL 的列也一起補上 target，合併後血緣才一致。
_SCENARIO_CHILDREN = ("results", "current_results", "snapshots", "events")
# 整張複製的小表（合併會刪列或換掉內容的表）。
COPY_TABLES = ("owners", "browser_identities", "owner_settings",
               "owner_credentials", "owner_verifications", "rate_limits")
_SETTINGS_TABLES = ("owner_settings", "owner_credentials",
                    "owner_verifications")
# owner_id 欄位存在的全部表（合併後非 NULL 的值只能是 target）。
_OWNER_COLUMN_TABLES = (
    "scenarios", "results", "current_results", "snapshots", "events",
    "diagnostics", "owner_settings", "owner_credentials",
    "owner_verifications", "browser_identities", "feedback")
# 合併期間擋住並行寫入（讀照常）；固定順序上鎖。
_LOCK_TABLES = ("owners", "browser_identities", "owner_settings",
                "owner_credentials", "owner_verifications", "scenarios",
                "results", "current_results", "snapshots", "events",
                "diagnostics", "rate_limits", "feedback")
# 合併前後回報筆數的表（`superuser_audit_log` 刻意不動，見 `execute()`）。
REPORT_TABLES = ("owners", "browser_identities", "scenarios", "results",
                 "current_results", "snapshots", "events", "diagnostics",
                 "owner_settings", "owner_credentials", "owner_verifications",
                 "feedback", "rate_limits", "superuser_audit_log")


class ConsolidationError(Exception):
    """任何一步不能安全繼續。訊息只有檢查名稱與計數，不含任何 id 或值。"""


class PreconditionMismatch(ConsolidationError):
    def __init__(self, mismatches: list[str], observed: dict):
        super().__init__("precondition: " + ", ".join(mismatches))
        self.mismatches = mismatches
        self.observed = observed


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _scalar(conn, sql: str, params=()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def _q(table: str) -> str:
    return f"{BACKUP_SCHEMA}.{table}"


def backup_exists(conn) -> bool:
    return bool(_scalar(conn, "SELECT count(*) FROM information_schema.schemata "
                              "WHERE schema_name = %s", (BACKUP_SCHEMA,)))


def _meta(conn) -> dict:
    return {k: v for k, v in conn.execute(
        f"SELECT key, value FROM {_q('meta')}").fetchall()}


def _set_meta(conn, key: str, value) -> None:
    conn.execute(
        f"INSERT INTO {_q('meta')} (key, value) VALUES (%s, %s::jsonb) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, json.dumps(value)))


# ---------- 唯讀觀察 ----------

def _table_counts(conn, target: str | None) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for table in REPORT_TABLES:
        row = {"total": _scalar(conn, f"SELECT count(*) FROM {table}")}
        if table in _OWNER_COLUMN_TABLES or table == "owners":
            row["target"] = _scalar(
                conn, f"SELECT count(*) FROM {table} WHERE owner_id = %s",
                (target,)) if target else 0
        out[table] = row
    return out


def observe(conn) -> dict:
    """預檢用的唯讀事實。回傳值含 owner_id（只在模組內部使用），對外一律
    走 `sanitized_observation()`。"""
    owners = conn.execute(
        "SELECT owner_id, role, protected, is_synthetic FROM owners").fetchall()
    superusers = [r[0] for r in owners if r[1] == TARGET_ROLE]
    target = superusers[0] if len(superusers) == 1 else None
    ids = {r[0] for r in owners}
    for table in _OWNER_COLUMN_TABLES:
        ids |= {r[0] for r in conn.execute(
            f"SELECT DISTINCT owner_id FROM {table} WHERE owner_id IS NOT NULL")}
    # 讀取端點用的每請求佔位值（`pending:…`）從來不是 owner，不當成 source。
    pending = {i for i in ids if i.startswith(PENDING_OWNER_PREFIX)}
    sources = sorted(ids - pending - ({target} if target else set()))
    by_owner = dict(conn.execute(
        "SELECT owner_id, count(*) FROM scenarios GROUP BY owner_id").fetchall())
    last_active = dict(conn.execute(_LAST_ACTIVE_SQL, ([r[0] for r in owners],)))
    registered = {r[0] for r in owners}
    return {
        "target": target,
        "sources": sources,
        "owners_total": len(owners),
        "superuser_count": len(superusers),
        "superadmin_count": sum(1 for r in owners if r[1] == "superadmin"),
        "protected_count": sum(1 for r in owners if r[2]),
        "synthetic_count": sum(1 for r in owners if r[3]),
        "target_prefix_match": bool(target and target.startswith(TARGET_PREFIX)),
        "target_protected": next((r[2] for r in owners if r[0] == target), None),
        # 只回報、不擋：Owner 說最近登入的就是主帳號（剛用過 Super User）。
        "target_most_recently_active": bool(target) and (
            last_active.get(target) or "") >= max(
            (v or "" for v in last_active.values()), default=""),
        "unregistered_source_ids": len(set(sources) - registered),
        "pending_placeholder_ids": len(pending),
        "scenarios_total": sum(by_owner.values()),
        "scenarios_null_owner": by_owner.get(None, 0),
        "target_scenarios": by_owner.get(target, 0) if target else 0,
        "source_scenarios": sum(by_owner.get(s, 0) for s in sources),
        "backup_exists": backup_exists(conn),
    }


def precondition_mismatches(obs: dict) -> list[str]:
    checks = {
        "superuser_count": obs["superuser_count"] == 1,
        "target_prefix": obs["target_prefix_match"],
        "owners_total": obs["owners_total"] == EXPECTED.owners,
        "scenarios_total": obs["scenarios_total"] == EXPECTED.scenarios,
        "target_scenarios": obs["target_scenarios"] == EXPECTED.target_scenarios,
        "source_scenarios": obs["source_scenarios"] == EXPECTED.source_scenarios,
        "backup_absent": not obs["backup_exists"],
    }
    return [name for name, ok in checks.items() if not ok]


def sanitized_observation(obs: dict) -> dict:
    return {k: (len(v) if k == "sources" else v) for k, v in obs.items()
            if k != "target"}


# ---------- 設定／憑證的取捨（target 優先） ----------

_LAST_ACTIVE_SQL = (
    "SELECT o.owner_id, GREATEST(o.last_activity_at, max(bi.last_seen_at)) "
    "FROM owners o LEFT JOIN browser_identities bi ON bi.owner_id = o.owner_id "
    "WHERE o.owner_id = ANY(%s) GROUP BY o.owner_id, o.last_activity_at")


def _pick(rows: list[tuple[str, str]], last_active: dict[str, str]) -> str | None:
    """rows = [(owner_id, updated_at)]；回傳要採用的那個 source owner。
    Owner 裁示（2026-10-25）：這些 owner 全是 Owner 本人，以最近登入（最近
    一次帶著 cookie 來）的那個為準；其次最近更新，最後以 owner_id 排序讓
    結果可重現。"""
    return max(rows, key=lambda r: (last_active.get(r[0]) or "", r[1] or "",
                                    r[0]))[0] if rows else None


def settings_decisions(conn, target: str, sources: list[str]) -> dict:
    """每張設定表要採用哪一列。target 有的一律保留 target 的；target 沒有
    的才從 source 裡挑一份（見 `_pick()`）。verification 跟著被採用的
    credential 走（它描述的是那一把 token 能不能用）。"""
    owners = [target, *sources]
    last_active = dict(conn.execute(_LAST_ACTIVE_SQL, (sources,)).fetchall())
    settings = conn.execute(
        "SELECT owner_id, updated_at FROM owner_settings "
        "WHERE owner_id = ANY(%s)", (owners,)).fetchall()
    has_target_settings = any(r[0] == target for r in settings)
    adopt_settings = None if has_target_settings else _pick(
        [r for r in settings if r[0] != target], last_active)

    creds: dict[str, list[tuple[str, str]]] = {}
    for owner, provider, updated in conn.execute(
            "SELECT owner_id, provider, updated_at FROM owner_credentials "
            "WHERE owner_id = ANY(%s)", (owners,)).fetchall():
        creds.setdefault(provider, []).append((owner, updated))
    adopt_creds = {}
    for provider, rows in creds.items():
        if not any(r[0] == target for r in rows):
            adopt_creds[provider] = _pick(rows, last_active)

    vers: dict[str, set[str]] = {}
    for owner, provider in conn.execute(
            "SELECT owner_id, provider FROM owner_verifications "
            "WHERE owner_id = ANY(%s)", (owners,)).fetchall():
        vers.setdefault(provider, set()).add(owner)
    adopt_vers = {p: adopt_creds[p] for p, holders in vers.items()
                  if target not in holders and adopt_creds.get(p) in holders}
    return {"owner_settings": adopt_settings,
            "owner_credentials": adopt_creds,
            "owner_verifications": adopt_vers}


# ---------- 合併 ----------

def _lock(conn) -> None:
    conn.execute("SET LOCAL lock_timeout = '15s'")
    conn.execute("LOCK TABLE " + ", ".join(_LOCK_TABLES)
                 + " IN SHARE ROW EXCLUSIVE MODE")


def _ledger_predicate(table: str) -> str:
    pred = "owner_id = ANY(%(sources)s)"
    if table in _SCENARIO_CHILDREN:
        pred += (" OR (owner_id IS NULL AND scenario_id IN ("
                 "SELECT id FROM scenarios WHERE owner_id = ANY(%(all)s)))")
    return pred


def _pk_join(pk: tuple[str, ...], a: str, b: str) -> str:
    return " AND ".join(f"{a}.{c} = {b}.{c}" for c in pk)


def _create_backup(conn, *, target: str, sources: list[str], now: datetime,
                   before: dict) -> dict[str, int]:
    conn.execute(f"CREATE SCHEMA {BACKUP_SCHEMA}")
    conn.execute(f"CREATE TABLE {_q('meta')} (key TEXT PRIMARY KEY, "
                 "value JSONB NOT NULL)")
    for table in COPY_TABLES:
        conn.execute(f"CREATE TABLE {_q('copy_' + table)} AS "
                     f"SELECT * FROM {table}")
    params = {"sources": sources, "all": [target, *sources]}
    ledger: dict[str, int] = {}
    for table, pk in LEDGER_TABLES:
        # DDL 不能帶 bind parameter：先建空表，再用 INSERT … SELECT 填。
        conn.execute(f"CREATE TABLE {_q('ledger_' + table)} AS "
                     f"SELECT {', '.join(pk)}, owner_id FROM {table} WITH NO DATA")
        conn.execute(
            f"INSERT INTO {_q('ledger_' + table)} "
            f"SELECT {', '.join(pk)}, owner_id FROM {table} "
            f"WHERE {_ledger_predicate(table)}", params)
        ledger[table] = _scalar(conn, f"SELECT count(*) FROM {_q('ledger_' + table)}")
    for key, value in (("target_owner_id", target),
                       ("source_owner_ids", sources),
                       ("created_at", _iso(now)),
                       ("before_counts", before),
                       ("ledger_counts", ledger),
                       ("status", "in_progress")):
        _set_meta(conn, key, value)
    for table in COPY_TABLES:
        copied = _scalar(conn, f"SELECT count(*) FROM {_q('copy_' + table)}")
        if copied != before["copy_totals"][table]:
            raise ConsolidationError(f"verification: backup_copy_{table}")
    return ledger


def _merge_content(conn, *, target: str, ledger: dict[str, int]) -> dict[str, int]:
    moved: dict[str, int] = {}
    for table, pk in LEDGER_TABLES:
        cur = conn.execute(
            f"UPDATE {table} t SET owner_id = %s FROM {_q('ledger_' + table)} l "
            f"WHERE {_pk_join(pk, 't', 'l')}", (target,))
        if cur.rowcount != ledger[table]:
            raise ConsolidationError(f"verification: ledger_{table}")
        moved[table] = cur.rowcount
    return moved


def _merge_settings(conn, *, target: str, sources: list[str],
                    decisions: dict) -> dict[str, dict[str, int]]:
    """被採用的 source 列改掛 target；其餘 source 列從線上表移除（內容已
    在 `copy_*` 備份表裡，可還原，不遺失）。target 自己的列一律不動。"""
    out: dict[str, dict[str, int]] = {}
    adopt = decisions["owner_settings"]
    if adopt:
        conn.execute("UPDATE owner_settings SET owner_id = %s "
                     "WHERE owner_id = %s", (target, adopt))
    archived = conn.execute("DELETE FROM owner_settings WHERE owner_id = ANY(%s)",
                            (sources,)).rowcount
    out["owner_settings"] = {"adopted": int(adopt is not None),
                             "archived_only": archived}
    for table in ("owner_credentials", "owner_verifications"):
        picks = decisions[table]
        for provider, owner in picks.items():
            conn.execute(f"UPDATE {table} SET owner_id = %s "
                         "WHERE owner_id = %s AND provider = %s",
                         (target, owner, provider))
        archived = conn.execute(f"DELETE FROM {table} WHERE owner_id = ANY(%s)",
                                (sources,)).rowcount
        out[table] = {"adopted": len(picks), "archived_only": archived}
    return out


def _verify_merge(conn, *, target: str, sources: list[str], before: dict,
                  expected_settings: dict) -> None:
    def fail(check: str) -> None:
        raise ConsolidationError(f"verification: {check}")

    for table, _ in LEDGER_TABLES:
        if _scalar(conn, f"SELECT count(*) FROM {table}") != before["tables"][table]["total"]:
            fail(f"row_count_{table}")
        if _scalar(conn, f"SELECT count(*) FROM {table} WHERE owner_id = ANY(%s)",
                   (sources,)):
            fail(f"source_rows_left_{table}")
    if _scalar(conn, "SELECT count(*) FROM scenarios WHERE owner_id = %s",
               (target,)) != before["tables"]["scenarios"]["total"]:
        fail("target_owns_all_scenarios")
    for table in _SCENARIO_CHILDREN:
        if _scalar(conn,
                   f"SELECT count(*) FROM {table} c JOIN scenarios s "
                   "ON s.id = c.scenario_id WHERE s.owner_id = %s "
                   "AND c.owner_id IS DISTINCT FROM %s", (target, target)):
            fail(f"lineage_{table}")
    if child_orphans(conn) != before["child_orphans"]:
        fail("child_orphans_changed")
    for table in _SETTINGS_TABLES:
        if _scalar(conn, f"SELECT count(*) FROM {table} WHERE owner_id = ANY(%s)",
                   (sources,)):
            fail(f"source_rows_left_{table}")
    has_settings = bool(_scalar(
        conn, "SELECT count(*) FROM owner_settings WHERE owner_id = %s", (target,)))
    if has_settings != expected_settings["settings"]:
        fail("target_settings")
    providers = {r[0] for r in conn.execute(
        "SELECT provider FROM owner_credentials WHERE owner_id = %s", (target,))}
    if providers != set(expected_settings["credential_providers"]):
        fail("target_credential_providers")


def _verify_cleanup(conn, *, target: str, target_role: str) -> None:
    def fail(check: str) -> None:
        raise ConsolidationError(f"verification: {check}")

    owners = conn.execute("SELECT owner_id, role FROM owners").fetchall()
    if owners != [(target, target_role)]:
        fail("only_target_owner_left")
    for table in _OWNER_COLUMN_TABLES:
        if _scalar(conn,
                   f"SELECT count(*) FROM {table} WHERE owner_id IS NOT NULL "
                   "AND owner_id <> %s AND owner_id NOT LIKE %s",
                   (target, PENDING_OWNER_PREFIX + "%")):
            fail(f"ownerless_rows_{table}")
    # target 的登入憑證：合併前後同一組 browser identity，一列不多、一列不少。
    if _scalar(conn,
               "SELECT count(*) FROM ("
               f"(SELECT token, issued_at FROM {_q('copy_browser_identities')} "
               " WHERE owner_id = %(t)s "
               " EXCEPT SELECT token, issued_at FROM browser_identities "
               " WHERE owner_id = %(t)s) UNION ALL "
               "(SELECT token, issued_at FROM browser_identities "
               " WHERE owner_id = %(t)s "
               f" EXCEPT SELECT token, issued_at FROM {_q('copy_browser_identities')} "
               " WHERE owner_id = %(t)s)) d", {"t": target}):
        fail("target_browser_identities_changed")
    if _scalar(conn, "SELECT count(*) FROM rate_limits WHERE scope = %s "
                     "AND NOT (key = %s)", (OWNER_RATE_LIMIT_SCOPE, target)):
        fail("source_quota_rows_left")


def child_orphans(conn) -> dict[str, int]:
    """指向不存在劇本的子列數（合併前就存在的也照實回報；合併不得改變它）。"""
    return {table: _scalar(
        conn, f"SELECT count(*) FROM {table} c WHERE c.scenario_id IS NOT NULL "
              "AND NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = c.scenario_id)")
        for table in _SCENARIO_CHILDREN}


def execute(conn, *, now: datetime) -> dict:
    """在呼叫端已經開好的 transaction 裡執行整個合併。任何不能安全繼續的
    情況都拋 `ConsolidationError`（呼叫端 rollback，零殘留）。回傳 sanitized
    摘要：合併前後各表筆數、設定取捨計數、剩餘 owner 數。

    刻意不動的表：`superuser_audit_log`（歷史稽核紀錄，本來就設計成在
    owner 被刪之後仍保留當時的 target_owner_id）、`role_sessions`（legacy，
    沒有 owner 欄位）、所有 shared market cache。"""
    _lock(conn)
    obs = observe(conn)
    mismatches = precondition_mismatches(obs)
    if mismatches:
        raise PreconditionMismatch(mismatches, sanitized_observation(obs))
    target, sources = obs["target"], obs["sources"]
    target_role = TARGET_ROLE
    before = {
        "tables": _table_counts(conn, target),
        "copy_totals": {t: _scalar(conn, f"SELECT count(*) FROM {t}")
                        for t in COPY_TABLES},
        "child_orphans": child_orphans(conn),
    }
    decisions = settings_decisions(conn, target, sources)
    expected_settings = {
        "settings": bool(_scalar(conn, "SELECT count(*) FROM owner_settings "
                                       "WHERE owner_id = ANY(%s)",
                                 ([target, *sources],))),
        "credential_providers": sorted({r[0] for r in conn.execute(
            "SELECT provider FROM owner_credentials WHERE owner_id = ANY(%s)",
            ([target, *sources],))}),
    }

    ledger = _create_backup(conn, target=target, sources=sources, now=now,
                            before=before)
    _set_meta(conn, "settings_decisions", decisions)
    moved = _merge_content(conn, target=target, ledger=ledger)
    settings = _merge_settings(conn, target=target, sources=sources,
                               decisions=decisions)
    _verify_merge(conn, target=target, sources=sources, before=before,
                  expected_settings=expected_settings)

    # 驗證通過才清理多餘 owner。舊 browser identity 刪除、不改綁。
    protected_propagated = bool(
        not obs["target_protected"] and _scalar(
            conn, "SELECT count(*) FROM owners WHERE owner_id = ANY(%s) "
                  "AND protected", (sources,)))
    if protected_propagated:
        # source 裡有受保護的 owner（例如 AUTH-07 救回的 Owner 舊身份）：
        # 它的劇本歸入 target 後仍要受同樣的保護，不被匿名清理帶走。
        conn.execute("UPDATE owners SET protected = TRUE WHERE owner_id = %s",
                     (target,))
    cleanup = {
        # 跟 `delete_owner()` 一樣只清 per-owner vendor quota 的計數列
        # （其餘 scope 是短時間窗的濫用計數，視窗結束一小時後自動清掉）。
        "rate_limits": conn.execute(
            "DELETE FROM rate_limits WHERE scope = %s AND key <> %s",
            (OWNER_RATE_LIMIT_SCOPE, target)).rowcount,
        "browser_identities": conn.execute(
            "DELETE FROM browser_identities WHERE owner_id = ANY(%s)",
            (sources,)).rowcount,
        "owners": conn.execute(
            "DELETE FROM owners WHERE owner_id = ANY(%s)", (sources,)).rowcount,
    }
    _verify_cleanup(conn, target=target, target_role=target_role)

    after = _table_counts(conn, target)
    summary = {
        "sources": len(sources),
        "before": before["tables"],
        "after": after,
        "moved": moved,
        "settings": settings,
        "cleanup": cleanup,
        "protected_propagated": protected_propagated,
        "child_orphans": before["child_orphans"],
        "remaining_owners": after["owners"]["total"],
    }
    _set_meta(conn, "summary", summary)
    _set_meta(conn, "completed_at", _iso(now))
    _set_meta(conn, "status", "completed")
    return summary


# ---------- 狀態（唯讀） ----------

def status(conn) -> dict:
    """唯讀：備份 schema 不存在 → `not_started`（附預檢結果）；存在 → 讀
    meta 的狀態與摘要，並附上目前的 owner 數與無主列數。"""
    if not backup_exists(conn):
        obs = observe(conn)
        return {"state": "not_started",
                "mismatches": precondition_mismatches(obs),
                "observed": sanitized_observation(obs)}
    meta = _meta(conn)
    target = meta.get("target_owner_id")
    # 合併之後新來的訪客是正常的新 owner；這裡只數「指向不存在 owner」的列。
    ownerless = {table: _scalar(
        conn, f"SELECT count(*) FROM {table} t WHERE t.owner_id IS NOT NULL "
              "AND t.owner_id NOT LIKE %s AND NOT EXISTS ("
              "SELECT 1 FROM owners o WHERE o.owner_id = t.owner_id)",
        (PENDING_OWNER_PREFIX + "%",)) for table in _OWNER_COLUMN_TABLES}
    return {"state": meta.get("status"),
            "summary": meta.get("summary"),
            "owners_now": _scalar(conn, "SELECT count(*) FROM owners"),
            "target_role_now": (conn.execute(
                "SELECT role FROM owners WHERE owner_id = %s", (target,))
                .fetchone() or [None])[0],
            "target_scenarios_now": _scalar(
                conn, "SELECT count(*) FROM scenarios WHERE owner_id = %s",
                (target,)),
            "ownerless_rows_now": ownerless}


# ---------- 回滾 ----------

def _columns(conn, table: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (BACKUP_SCHEMA, "copy_" + table))]


def rollback(conn, *, now: datetime) -> dict:
    """在呼叫端的 transaction 裡把合併還原回合併前：owner 與它們的
    browser identity、owner quota 計數、三張設定表回到備份內容，每一列
    內容表的 owner_id 依帳本改回原值。合併之後才新增的列（例如 target
    新建的劇本）保持原樣；被覆蓋前的 target 設定先另存在
    `rollback_archive_*`，同樣不遺失。只能從 `completed` 狀態回滾一次。"""
    if not backup_exists(conn):
        raise ConsolidationError("rollback: no_backup")
    _lock(conn)
    meta = _meta(conn)
    if meta.get("status") != "completed":
        raise ConsolidationError("rollback: not_completed")
    target, sources = meta["target_owner_id"], meta["source_owner_ids"]
    everyone = [target, *sources]
    out: dict[str, int] = {}

    cols = _columns(conn, "owners")
    out["owners"] = conn.execute(
        f"INSERT INTO owners ({', '.join(cols)}) SELECT {', '.join(cols)} "
        f"FROM {_q('copy_owners')} WHERE owner_id = ANY(%s) "
        "ON CONFLICT (owner_id) DO NOTHING", (sources,)).rowcount
    conn.execute(f"UPDATE owners o SET protected = c.protected "
                 f"FROM {_q('copy_owners')} c "
                 "WHERE o.owner_id = c.owner_id AND o.owner_id = %s", (target,))
    cols = _columns(conn, "browser_identities")
    restored = conn.execute(
        f"INSERT INTO browser_identities ({', '.join(cols)}) "
        f"SELECT {', '.join(cols)} FROM {_q('copy_browser_identities')} "
        "WHERE owner_id = ANY(%s) ON CONFLICT (token) DO NOTHING",
        (sources,)).rowcount
    out["browser_identities"] = restored
    # 舊 token 在合併後被同一個瀏覽器重新綁成新的匿名 owner：保留新的那一列
    # （不刪別人的資料），只回報數量。
    out["browser_identities_token_reused"] = _scalar(
        conn, f"SELECT count(*) FROM {_q('copy_browser_identities')} "
              "WHERE owner_id = ANY(%s)", (sources,)) - restored
    cols = _columns(conn, "rate_limits")
    out["rate_limits"] = conn.execute(
        f"INSERT INTO rate_limits ({', '.join(cols)}) "
        f"SELECT {', '.join(cols)} FROM {_q('copy_rate_limits')} "
        "WHERE scope = %s AND key <> %s ON CONFLICT DO NOTHING",
        (OWNER_RATE_LIMIT_SCOPE, target)).rowcount

    for table in _SETTINGS_TABLES:
        conn.execute(f"CREATE TABLE {_q('rollback_archive_' + table)} AS "
                     f"SELECT * FROM {table} WITH NO DATA")
        conn.execute(f"INSERT INTO {_q('rollback_archive_' + table)} "
                     f"SELECT * FROM {table} WHERE owner_id = ANY(%s)",
                     (everyone,))
        conn.execute(f"DELETE FROM {table} WHERE owner_id = ANY(%s)", (everyone,))
        cols = _columns(conn, table)
        out[table] = conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} "
            f"FROM {_q('copy_' + table)} WHERE owner_id = ANY(%s)",
            (everyone,)).rowcount

    for table, pk in LEDGER_TABLES:
        out[table] = conn.execute(
            f"UPDATE {table} t SET owner_id = l.owner_id "
            f"FROM {_q('ledger_' + table)} l WHERE {_pk_join(pk, 't', 'l')}"
            ).rowcount

    _set_meta(conn, "rollback_summary", out)
    _set_meta(conn, "rolled_back_at", _iso(now))
    _set_meta(conn, "status", "rolled_back")
    return out
