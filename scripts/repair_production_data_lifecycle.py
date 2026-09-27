"""Production 資料生命週期一次性修復（CLAUDE-DB-HYGIENE-002，含 AUTH-07）。

唯一的 canonical 入口——取代舊的 `migrate_solo_to_owner.py`（現在只是
轉呼叫這裡的薄殼）、`backfill_owner_ids.py`、`backfill_settings_to_owner.py`、
`backfill_result_fact_context.py`。

一個指令完成：legacy singleton 設定收進 solo → solo 搬到 Owner 的真正
owner → NULL-owner 舊劇本血緣救援 → 重建舊劇本的 current_results →
標記 protected → 補 SCALE-01 fact context → 清掉 legacy `results.view`
→ snapshot／events／role session／audit log retention → DROP 已退役的表
→ 驗證所有 invariant。搬遷段是原子的：任何衝突或驗證失敗都整段
rollback，不會留下半狀態；重跑是安全的 no-op。

用法：

    # 預設是 dry-run：零寫入，只印列數／大小／衝突預檢／預計動作
    DATABASE_URL=postgresql://... python scripts/repair_production_data_lifecycle.py \\
        --target-owner-id <REAL_OWNER_ID>

    # 真的執行
    DATABASE_URL=postgresql://... python scripts/repair_production_data_lifecycle.py \\
        --target-owner-id <REAL_OWNER_ID> --confirm

**前置（Owner HITL）**：target owner 必須已經存在。用自己的瀏覽器在正式站
**建立一個劇本**（SECURITY-FIX-01 起只有寫入才會建立 owner；**不要**用
「存設定」來建立——那會讓 target 已經有設定，跟 solo 的設定不同時會被
預檢擋下），再用 Super Admin 的 owner 清單找到自己的 `owner_id`。
**故意不提供任何猜測預設值**：`--target-owner-id` 必填。

輸出只有列數、大小、表名、provider 名稱與描述——絕不輸出 credential／
token／cookie／role-session token／IP。任何 invariant 失敗都以非零 exit
code 結束。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app import data_lifecycle  # noqa: E402
from api_app.storage.postgres import PostgresStorage  # noqa: E402


def _print(title: str, payload: dict) -> None:
    print(f"== {title} ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def run(db, *, target_owner_id: str, confirm: bool,
        now: datetime | None = None) -> int:
    """回傳 exit code（0＝成功／dry-run 完成且可以執行；非 0＝不能安全執行或
    驗證失敗）。拆出來讓測試可以直接用記憶體／測試用 Postgres 呼叫。"""
    now = now or datetime.now(timezone.utc)
    plan = data_lifecycle.plan(db, target_owner_id=target_owner_id, now=now)
    _print("dry-run plan（零寫入）", plan)
    if not plan["target_owner"]["exists"]:
        print(f"✗ target owner 不存在：{target_owner_id!r}——請先依本腳本檔頭"
              "的前置步驟建立（用自己的瀏覽器建立一個劇本）")
        return 2
    if plan["conflicts"]:
        print("✗ 預檢發現衝突（需要 Owner 先決定保留哪一份，本腳本不替你挑）："
              + ", ".join(plan["conflicts"]))
        return 3
    if not confirm:
        print("未帶 --confirm，本次沒有寫入任何資料。核對上面的數字與 target "
              "owner 後，加上 --confirm 重新執行。")
        return 0
    try:
        summary = data_lifecycle.execute(db, target_owner_id=target_owner_id,
                                         now=now)
    except data_lifecycle.MaintenanceError as e:
        print(f"✗ {e}")
        return 4
    _print("完成（before／after）", summary)
    print("✓ 所有 invariant 驗證通過。重跑本指令是安全的 no-op。")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-owner-id", required=True,
                        help="Owner 自己的真正 owner_id（見檔頭前置步驟）——必填，"
                             "不提供任何猜測預設值。")
    parser.add_argument("--confirm", action="store_true",
                        help="真的執行。省略時只做 dry-run，不寫入任何資料。")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("需要 DATABASE_URL 環境變數才能連線到正式資料庫")
    sys.exit(run(PostgresStorage(dsn), target_owner_id=args.target_owner_id,
                 confirm=args.confirm))


if __name__ == "__main__":
    main()
