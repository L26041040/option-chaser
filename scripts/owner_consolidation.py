"""OPTION-CHASER-OWNER-CONSOLIDATION-001：Owner 合併的狀態查詢與回滾。

合併本身由 Production cold-start hook 執行一次（見
`api_app/oneshot_owner_consolidation.py`）。這支腳本給 Owner 在本機用
Neon 連線字串操作：

    # 預設：唯讀，印出合併狀態（未開始時附預檢結果）
    DATABASE_URL=postgresql://... python scripts/owner_consolidation.py

    # 回滾：用備份 schema 把 owner、browser identity、設定／憑證與每一列的
    # owner_id 還原回合併前（合併後新增的資料保留）
    DATABASE_URL=postgresql://... python scripts/owner_consolidation.py \\
        --rollback --confirm

輸出只有計數與狀態，絕不輸出 owner_id／token／credential。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app import owner_consolidation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rollback", action="store_true",
                        help="把合併還原回合併前（需同時帶 --confirm）。")
    parser.add_argument("--confirm", action="store_true",
                        help="真的執行回滾。省略時只印狀態，不寫入任何資料。")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("需要 DATABASE_URL 環境變數才能連線到正式資料庫")
    import psycopg
    with psycopg.connect(dsn, autocommit=True) as conn:
        if args.rollback and args.confirm:
            try:
                with conn.transaction():
                    out = owner_consolidation.rollback(
                        conn, now=datetime.now(timezone.utc))
            except owner_consolidation.ConsolidationError as e:
                raise SystemExit(f"✗ {e}")
            print(json.dumps({"rolled_back": out}, ensure_ascii=False, indent=2))
        print(json.dumps(owner_consolidation.status(conn), ensure_ascii=False,
                         indent=2, sort_keys=True))
        if args.rollback and not args.confirm:
            print("未帶 --confirm，本次沒有寫入任何資料。")


if __name__ == "__main__":
    main()
