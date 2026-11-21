"""PRODUCTION-TEST-DATA-CLEANUP-001：清掉回報#141 事故留在 Production 的測試資料。

2026-10-27 08:05–08:15 (台灣) 驗證腳本誤連 Production，在別名網址上種了 14 個
測試 Normal Owner，各自一個 XYZ 劇本（target_price=130、target_month=2027-01、
vertical-spread）與少量分析結果。這支腳本只清**那 14 個**，其他一律不碰。

設計原則（Owner 指示）：

- 預設 dry-run：零寫入，只印完整盤點。條件**任何一項**不符、候選數不是 14、出現
  任何歧義，一律以非零 exit code 停止，不做部分刪除。
- `--confirm` 才真的刪，而且要 `--backup-path`（不存在的新檔）：刪除前先把候選
  Owner 名下全部列存成 JSON（browser identity 的 token 只存 SHA-256，不含明文
  憑證），權限 0600。
- 刪除沿用既有生命週期原語 `PostgresStorage.delete_owner()`（含墓碑、quota 計數列、
  browser identity），外面包一層 `transaction()`：14 個 Owner＋任何殘餘子列是**同一個
  交易**，任一步驟或交易內的事後核對失敗就整批 rollback。
- 交易內重新盤點一次（防 dry-run 與執行之間資料變動），並用固定鎖序鎖住相關表。
- 事後核對：Owner／劇本數、候選殘留、非候選資料（Owner 與劇本整列內容、各表非候選
  列數與 key 的雜湊、主帳號列）刪前刪後完全相同、沒有孤兒資料、墓碑數只增加被刪
  identity 的數量。交易 commit 後再用全新連線核對一次。
- 輸出只有 id、列數、雜湊與描述：**不含任何 token、cookie、密碼**。

用法（`DATABASE_URL` 只從環境變數讀，不放在參數裡）：

    DATABASE_URL=postgresql://... python scripts/cleanup_production_test_owners.py
    DATABASE_URL=postgresql://... python scripts/cleanup_production_test_owners.py \\
        --confirm --backup-path ./test-owner-cleanup-backup.json

Exit code：0＝dry-run 全部符合／已清理並核對通過；2＝前置條件不符，**零寫入**；
3＝交易內核對失敗，已 rollback。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

from api_app.storage import OWNER_RATE_LIMIT_SCOPE, identity_token_hash  # noqa: E402
from api_app.storage.postgres import PostgresStorage, _lock_order  # noqa: E402

EXPECTED_CANDIDATES = 14
# 事故時間窗（UTC）：2026-10-27 08:05–08:20 (台灣)。比 Owner 回報的 08:11–08:14 寬一點，
# 真正的界線是下面的「形狀」條件，不是時間。
DEFAULT_WINDOW_START = "2026-10-27T00:05:00+00:00"
DEFAULT_WINDOW_END = "2026-10-27T00:20:00+00:00"
# Owner 在施工令裡給的 Production 現況。
DEFAULT_EXPECT_OWNERS = 15
DEFAULT_EXPECT_SCENARIOS = 24

TEST_SYMBOL = "XYZ"
TEST_TARGET_PRICE = 130.0
TEST_TARGET_MONTH = "2027-01"
TEST_STRATEGIES = ["vertical-spread"]

_SCENARIO_CHILDREN = ("results", "current_results", "snapshots", "events")
_OWNER_ONLY_ZERO_TABLES = ("owner_settings", "owner_credentials",
                           "owner_verifications", "feedback")
_LOCK_TABLES = _lock_order((
    "owners", "browser_identities", "identity_tombstones", "owner_settings",
    "owner_credentials", "owner_verifications", "owner_merge_archive",
    "scenarios", "results", "current_results", "snapshots", "events",
    "diagnostics", "feedback", "rate_limits"))


class Refused(Exception):
    """前置條件或事後核對不符——呼叫端據此停止（交易內則 rollback）。"""


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _digest(rows) -> str:
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _all(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchall()


def _count(conn, sql: str, params=()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


# ---------- 孤兒檢查 ----------

def orphans(conn) -> dict[str, int]:
    """每一類「指向不存在的父列」的數量。全部為 0 才算乾淨。"""
    q = {
        "scenarios_without_owner":
            "SELECT count(*) FROM scenarios s WHERE s.owner_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = s.owner_id)",
        "browser_identities_without_owner":
            "SELECT count(*) FROM browser_identities b WHERE NOT EXISTS "
            "(SELECT 1 FROM owners o WHERE o.owner_id = b.owner_id)",
        "owner_settings_without_owner":
            "SELECT count(*) FROM owner_settings t WHERE NOT EXISTS "
            "(SELECT 1 FROM owners o WHERE o.owner_id = t.owner_id)",
        "owner_credentials_without_owner":
            "SELECT count(*) FROM owner_credentials t WHERE NOT EXISTS "
            "(SELECT 1 FROM owners o WHERE o.owner_id = t.owner_id)",
        "owner_verifications_without_owner":
            "SELECT count(*) FROM owner_verifications t WHERE NOT EXISTS "
            "(SELECT 1 FROM owners o WHERE o.owner_id = t.owner_id)",
        "diagnostics_without_owner":
            "SELECT count(*) FROM diagnostics t WHERE t.owner_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.owner_id = t.owner_id)",
        "owner_quota_rows_without_owner":
            "SELECT count(*) FROM rate_limits r WHERE r.scope = %s AND NOT EXISTS "
            "(SELECT 1 FROM owners o WHERE o.owner_id = r.key)",
    }
    for table in _SCENARIO_CHILDREN:
        q[f"{table}_without_scenario"] = (
            f"SELECT count(*) FROM {table} t WHERE t.scenario_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM scenarios s WHERE s.id = t.scenario_id)")
    out = {}
    for name, sql in q.items():
        out[name] = _count(conn, sql, (OWNER_RATE_LIMIT_SCOPE,)
                           if "%s" in sql else ())
    return out


# ---------- 盤點 ----------

def inspect(conn, *, window_start: str, window_end: str, expect_owners: int,
            expect_scenarios: int) -> dict:
    """唯讀盤點。回傳的 `problems` 非空＝不能安全執行。"""
    problems: list[str] = []
    start, end = _ts(window_start), _ts(window_end)

    owners = {r[0]: {"created_at": r[1], "protected": r[2], "role": r[3],
                     "is_synthetic": r[4]}
              for r in _all(conn, "SELECT owner_id, created_at, protected, role, "
                                  "is_synthetic FROM owners")}
    scen_rows = _all(conn, "SELECT id, owner_id, symbol, target_price, target_month, "
                           "strategies, created_at, archived_at FROM scenarios")
    scenarios = [{"id": r[0], "owner_id": r[1], "symbol": r[2],
                  "target_price": float(r[3]), "target_month": r[4],
                  "strategies": r[5], "created_at": r[6], "archived_at": r[7]}
                 for r in scen_rows]
    main_row = conn.execute("SELECT main_owner_id FROM main_account WHERE id = 1").fetchone()
    main = main_row[0] if main_row else None

    totals = {"owners": len(owners), "scenarios": len(scenarios)}
    if totals["owners"] != expect_owners:
        problems.append(f"Owner 總數 {totals['owners']}，預期 {expect_owners}")
    if totals["scenarios"] != expect_scenarios:
        problems.append(f"劇本總數 {totals['scenarios']}，預期 {expect_scenarios}")
    if main is None:
        problems.append("main_account 沒有主帳號列")
    elif main not in owners:
        problems.append("主帳號不在 owners 裡")

    by_owner: dict[str, list[dict]] = {}
    for s in scenarios:
        by_owner.setdefault(s["owner_id"], []).append(s)

    def in_window(value) -> bool:
        return start <= _ts(value) <= end

    def matches_test_shape(s: dict) -> bool:
        return (s["symbol"] == TEST_SYMBOL and s["target_price"] == TEST_TARGET_PRICE
                and s["target_month"] == TEST_TARGET_MONTH
                and list(s["strategies"]) == TEST_STRATEGIES
                and s["archived_at"] is None and in_window(s["created_at"]))

    candidates: list[str] = []
    for oid, meta in sorted(owners.items()):
        if oid == main or not in_window(meta["created_at"]):
            continue
        # 時間窗內建立的非主帳號 Owner：要嘛完全符合測試形狀，要嘛是歧義→停止。
        mine = by_owner.get(oid, [])
        shape_ok = (meta["role"] == "normal" and not meta["protected"]
                    and not meta["is_synthetic"] and len(mine) == 1
                    and matches_test_shape(mine[0]))
        if shape_ok:
            candidates.append(oid)
        else:
            problems.append(f"時間窗內的 Owner {oid} 不符合測試形狀"
                            f"（role={meta['role']}, protected={meta['protected']}, "
                            f"劇本數={len(mine)}）——歧義，停止")
    cand_set = set(candidates)
    cand_scenarios = [by_owner[o][0]["id"] for o in candidates]

    if len(candidates) != EXPECTED_CANDIDATES:
        problems.append(f"候選 Owner {len(candidates)} 個，預期 {EXPECTED_CANDIDATES}")
    if main in cand_set:
        problems.append("主帳號出現在候選裡")
    if any(owners[o]["protected"] or owners[o]["role"] != "normal" for o in candidates):
        problems.append("候選裡有 protected 或非 Normal 的 Owner")
    if totals["scenarios"] - len(cand_scenarios) != expect_scenarios - EXPECTED_CANDIDATES:
        problems.append("扣掉候選後的劇本數不是預期的原有劇本數")

    # 候選名下不得有設定／credential／verification／意見回饋／併入封存。
    zero = {}
    for table in _OWNER_ONLY_ZERO_TABLES:
        zero[table] = _count(conn, f"SELECT count(*) FROM {table} WHERE owner_id = ANY(%s::text[])",
                             (candidates,))
    zero["owner_merge_archive"] = _count(
        conn, "SELECT count(*) FROM owner_merge_archive WHERE source_owner_id = ANY(%s::text[]) "
              "OR target_owner_id = ANY(%s::text[])", (candidates, candidates))
    for table, n in zero.items():
        if n:
            problems.append(f"候選名下有 {n} 列 {table}（預期 0）——歧義，停止")

    # 子列：每一列都必須屬於候選劇本；owner_id 不是候選本人就是 NULL。
    children = {}
    null_owner_children = {}
    sid_owner = {by_owner[o][0]["id"]: o for o in candidates}
    for table in _SCENARIO_CHILDREN:
        rows = _all(conn, f"SELECT scenario_id, owner_id, count(*) FROM {table} "
                          "WHERE scenario_id = ANY(%s::text[]) OR owner_id = ANY(%s::text[]) "
                          "GROUP BY scenario_id, owner_id", (cand_scenarios, candidates))
        total = nulls = 0
        for sid, oid, n in rows:
            total += n
            if sid not in sid_owner:
                problems.append(f"{table} 有 {n} 列掛在候選 Owner {oid} 但劇本 {sid} "
                                "不是候選劇本——歧義，停止")
            elif oid is None:
                nulls += n
            elif oid != sid_owner[sid]:
                problems.append(f"{table} 有 {n} 列 owner_id={oid} 卻屬於 {sid_owner[sid]} "
                                "的劇本——歧義，停止")
        children[table] = total
        null_owner_children[table] = nulls
    children["diagnostics"] = _count(
        conn, "SELECT count(*) FROM diagnostics WHERE owner_id = ANY(%s::text[])", (candidates,))

    identities = {o: _count(conn, "SELECT count(*) FROM browser_identities "
                                  "WHERE owner_id = %s", (o,)) for o in candidates}
    quota_rows = _count(conn, "SELECT count(*) FROM rate_limits WHERE scope = %s "
                              "AND key = ANY(%s::text[])", (OWNER_RATE_LIMIT_SCOPE, candidates))

    pre_orphans = orphans(conn)
    if any(pre_orphans.values()):
        problems.append(f"刪除前就已有孤兒資料 {pre_orphans}——不在本次授權範圍，停止")

    return {
        "totals": totals, "main_account": main, "candidates": candidates,
        "candidate_scenarios": cand_scenarios, "owner_only_zero_tables": zero,
        "children": children, "null_owner_children": null_owner_children,
        "identities_per_candidate": identities, "quota_rows": quota_rows,
        "orphans": pre_orphans, "baseline": baseline(conn, candidates, cand_scenarios),
        "tombstones": _count(conn, "SELECT count(*) FROM identity_tombstones"),
        "problems": problems,
    }


def baseline(conn, candidates: list[str], cand_scenarios: list[str]) -> dict:
    """候選**以外**的資料指紋——刪除前後必須完全相同。"""
    owners = _all(conn, "SELECT * FROM owners WHERE owner_id <> ALL(%s::text[]) ORDER BY owner_id",
                  (candidates,))
    scenarios = _all(conn, "SELECT * FROM scenarios WHERE id <> ALL(%s::text[]) ORDER BY id",
                     (cand_scenarios,))
    out = {"owners_digest": _digest(owners), "scenarios_digest": _digest(scenarios),
           "owners": len(owners), "scenarios": len(scenarios)}
    keys = {"results": "scenario_id, analyzed_at", "current_results": "scenario_id",
            "snapshots": "scenario_id, analyzed_at", "events": "seq"}
    for table, key in keys.items():
        rows = _all(conn, f"SELECT {key} FROM {table} WHERE scenario_id IS NULL "
                          "OR scenario_id <> ALL(%s::text[]) ORDER BY " + key,
                    (cand_scenarios,))
        out[table] = {"rows": len(rows), "keys_digest": _digest(rows)}
    out["diagnostics"] = _count(conn, "SELECT count(*) FROM diagnostics WHERE owner_id IS NULL "
                                      "OR owner_id <> ALL(%s::text[])", (candidates,))
    out["browser_identities"] = _digest(_all(
        conn, "SELECT owner_id, issued_at, last_seen_at FROM browser_identities "
              "WHERE owner_id <> ALL(%s::text[]) ORDER BY owner_id, issued_at", (candidates,)))
    for table in _OWNER_ONLY_ZERO_TABLES + ("owner_merge_archive",):
        out[table] = _count(conn, f"SELECT count(*) FROM {table}")
    out["quota_rows"] = _count(
        conn, "SELECT count(*) FROM rate_limits WHERE NOT (scope = %s AND key = ANY(%s::text[]))",
        (OWNER_RATE_LIMIT_SCOPE, candidates))
    out["main_account_row"] = _digest(_all(conn, "SELECT * FROM main_account ORDER BY id"))
    return out


# ---------- 備份 ----------

def _table_rows(conn, sql: str, params=()) -> list[dict]:
    cur = conn.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def write_backup(conn, report: dict, path: str) -> str:
    """刪除前把候選名下全部列存成 JSON（不含明文憑證）。回傳檔案 SHA-256。"""
    owners, sids = report["candidates"], report["candidate_scenarios"]
    identities = _table_rows(conn, "SELECT * FROM browser_identities WHERE owner_id = ANY(%s::text[])",
                             (owners,))
    for row in identities:
        row["token_sha256"] = identity_token_hash(row.pop("token"))
    body = {
        "purpose": "PRODUCTION-TEST-DATA-CLEANUP-001 刪除前備份（回報#141 事故的測試資料）",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "browser_identities 的明文 token 已換成 SHA-256；沒有任何密碼或 cookie。",
        "owners": _table_rows(conn, "SELECT * FROM owners WHERE owner_id = ANY(%s::text[])", (owners,)),
        "browser_identities": identities,
        "scenarios": _table_rows(conn, "SELECT * FROM scenarios WHERE id = ANY(%s::text[])", (sids,)),
        "rate_limits": _table_rows(
            conn, "SELECT * FROM rate_limits WHERE scope = %s AND key = ANY(%s::text[])",
            (OWNER_RATE_LIMIT_SCOPE, owners)),
        "diagnostics": _table_rows(conn, "SELECT * FROM diagnostics WHERE owner_id = ANY(%s::text[])",
                                   (owners,)),
    }
    for table in _SCENARIO_CHILDREN:
        body[table] = _table_rows(
            conn, f"SELECT * FROM {table} WHERE scenario_id = ANY(%s::text[]) OR owner_id = ANY(%s::text[])",
            (sids, owners))
    blob = json.dumps(body, ensure_ascii=False, indent=1, default=str).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    return hashlib.sha256(blob).hexdigest()


# ---------- 核對 ----------

def verify_after(conn, before: dict, args) -> dict:
    """刪除後的完整核對；任何一項不符丟 Refused。"""
    cands, sids = before["candidates"], before["candidate_scenarios"]
    n = len(cands)
    after = {
        "owners": _count(conn, "SELECT count(*) FROM owners"),
        "scenarios": _count(conn, "SELECT count(*) FROM scenarios"),
        "candidate_owners_left": _count(conn, "SELECT count(*) FROM owners "
                                              "WHERE owner_id = ANY(%s::text[])", (cands,)),
        "candidate_scenarios_left": _count(conn, "SELECT count(*) FROM scenarios "
                                                 "WHERE id = ANY(%s::text[])", (sids,)),
        "xyz_test_scenarios": sum(
            1 for created_at in (r[0] for r in _all(
                conn, "SELECT created_at FROM scenarios WHERE symbol = %s "
                      "AND target_price = %s AND target_month = %s",
                (TEST_SYMBOL, TEST_TARGET_PRICE, TEST_TARGET_MONTH)))
            if _ts(args.window_start) <= _ts(created_at) <= _ts(args.window_end)),
        "candidate_identities_left": _count(
            conn, "SELECT count(*) FROM browser_identities WHERE owner_id = ANY(%s::text[])", (cands,)),
        "orphans": orphans(conn),
        "tombstones": _count(conn, "SELECT count(*) FROM identity_tombstones"),
        "baseline": baseline(conn, cands, sids),
    }
    for table in _SCENARIO_CHILDREN:
        after[f"{table}_left"] = _count(
            conn, f"SELECT count(*) FROM {table} WHERE scenario_id = ANY(%s::text[]) "
                  "OR owner_id = ANY(%s::text[])", (sids, cands))
    failures = []
    if after["owners"] != before["totals"]["owners"] - n:
        failures.append("Owner 總數不是 刪前 − 候選")
    if after["scenarios"] != before["totals"]["scenarios"] - len(sids):
        failures.append("劇本總數不是 刪前 − 候選劇本")
    for key in ("candidate_owners_left", "candidate_scenarios_left",
                "candidate_identities_left", "xyz_test_scenarios",
                *(f"{t}_left" for t in _SCENARIO_CHILDREN)):
        if after[key]:
            failures.append(f"{key} = {after[key]}（預期 0）")
    if any(after["orphans"].values()):
        failures.append(f"出現孤兒資料 {after['orphans']}")
    if after["baseline"] != before["baseline"]:
        failures.append("候選以外的資料指紋與刪除前不同")
    expected_tombstones = before["tombstones"] + sum(before["identities_per_candidate"].values())
    if after["tombstones"] != expected_tombstones:
        failures.append(f"墓碑數 {after['tombstones']}，預期 {expected_tombstones}")
    if failures:
        raise Refused("; ".join(failures))
    return after


# ---------- 執行 ----------

def execute(dsn: str, report: dict, args) -> dict:
    db = PostgresStorage(dsn)
    with db.transaction():
        with db._connect() as conn:
            conn.execute("LOCK TABLE " + ", ".join(_LOCK_TABLES)
                         + " IN SHARE ROW EXCLUSIVE MODE")
            again = inspect(conn, window_start=args.window_start, window_end=args.window_end,
                            expect_owners=args.expect_owners,
                            expect_scenarios=args.expect_scenarios)
            if again["problems"]:
                raise Refused("交易內重新盤點不符：" + "; ".join(again["problems"]))
            if (again["candidates"] != report["candidates"]
                    or again["baseline"] != report["baseline"]):
                raise Refused("dry-run 與執行之間資料變動了——停止")
            # 掛在候選劇本、但自己 owner_id 是 NULL 的子列：delete_owner 只認 owner_id，
            # 不先清會變孤兒。
            for table in _SCENARIO_CHILDREN:
                conn.execute(f"DELETE FROM {table} WHERE scenario_id = ANY(%s::text[]) "
                             "AND owner_id IS NULL", (report["candidate_scenarios"],))
            deleted = {oid: db.delete_owner(oid, reason="deleted")
                       for oid in report["candidates"]}
            after = verify_after(conn, report, args)
    return {"deleted": deleted, "after_in_transaction": after}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--confirm", action="store_true", help="真的刪除（預設 dry-run）")
    parser.add_argument("--backup-path", help="--confirm 時必填：刪除前備份的新檔路徑")
    parser.add_argument("--expect-owners", type=int, default=DEFAULT_EXPECT_OWNERS)
    parser.add_argument("--expect-scenarios", type=int, default=DEFAULT_EXPECT_SCENARIOS)
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("需要環境變數 DATABASE_URL", file=sys.stderr)
        return 2
    if args.confirm and not args.backup_path:
        print("--confirm 需要 --backup-path", file=sys.stderr)
        return 2
    if args.confirm and os.path.exists(args.backup_path):
        print(f"{args.backup_path} 已存在——不覆蓋既有備份，請換一個新檔名", file=sys.stderr)
        return 2

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = on")
        report = inspect(conn, window_start=args.window_start, window_end=args.window_end,
                         expect_owners=args.expect_owners,
                         expect_scenarios=args.expect_scenarios)
        print("== 刪除前盤點（唯讀）==")
        print(json.dumps({k: v for k, v in report.items() if k != "baseline"},
                         ensure_ascii=False, indent=2, sort_keys=True, default=str))
        if report["problems"]:
            print("\n不符合，零寫入，停止：", file=sys.stderr)
            for p in report["problems"]:
                print(f" - {p}", file=sys.stderr)
            return 2
        if not args.confirm:
            print("\ndry-run 完成：全部條件符合，14 個候選可以清理。加 --confirm "
                  "--backup-path <新檔> 執行。")
            return 0
        backup_sha = write_backup(conn, report, args.backup_path)
        print(f"\n備份已寫入 {args.backup_path}（sha256 {backup_sha}，0600，無明文憑證）")

    try:
        result = execute(dsn, report, args)
    except Refused as e:
        print(f"\n交易內核對失敗，已 rollback，沒有任何刪除：{e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 — 交易內任何失敗都整批 rollback，回報後停止
        print(f"\n交易失敗，已 rollback，沒有任何刪除：{type(e).__name__}: {e}", file=sys.stderr)
        return 3

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = on")
        try:
            final = verify_after(conn, report, args)
        except Refused as e:
            print(f"\ncommit 後的獨立核對失敗：{e}", file=sys.stderr)
            return 3
    record = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "backup": {"path": args.backup_path, "sha256": backup_sha},
        "before": {k: v for k, v in report.items() if k != "problems"},
        "deleted_rows_per_owner": result["deleted"],
        "after": final,
    }
    record_path = args.backup_path + ".verification.json"
    with open(record_path, "x", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1, sort_keys=True, default=str)
    print("\n== 刪除後核對（commit 後、全新連線）==")
    print(json.dumps(final, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    print(f"\n完成。驗證紀錄：{record_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
