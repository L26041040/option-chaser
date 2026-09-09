"""一次性 backfill 腳本（SCALE-06／#256，Ownership A-1 Expand）：對正式
資料庫既有 5 張 row-scoped 表（`scenarios`／`results`／`snapshots`／
`events`／`diagnostics`）補上固定的 solo-owner `owner_id`。

冪等、可重跑，**不是部署前置條件**——`api_app/main.py` 的寫入路徑已經
在每次新寫入時自動帶上 `identity_resolver()` 解析出的值；不執行本腳本
也不影響任何既有功能，只是那些既有歷史列在跑過本腳本之前，`owner_id`
維持 `NULL`（本票不加任何查詢過濾，讀取端不需要這個值就能正常運作）。

用法：

    DATABASE_URL=postgresql://... python scripts/backfill_owner_ids.py

中斷後直接重跑即可續跑——`Storage.backfill_missing_owner_ids()` 本身
是 `WHERE owner_id IS NULL` 的條件式批次更新，重跑對已補過的列是
0-effect no-op。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app.identity import SOLO_OWNER  # noqa: E402
from api_app.storage.postgres import PostgresStorage  # noqa: E402


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("需要 DATABASE_URL 環境變數才能連線到正式資料庫")
    db = PostgresStorage(dsn)
    counts = db.backfill_missing_owner_ids(SOLO_OWNER)
    total = sum(counts.values())
    print(f"backfill 完成，補齊 {total} 筆：{counts}")


if __name__ == "__main__":
    main()
