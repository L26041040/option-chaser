"""一次性 backfill 腳本（SCALE-01／#252）：對正式資料庫既有 `results`
列補齊 Stage 1-0 新增的歷史 fact context 欄位。

冪等、可重跑，**不是部署前置條件**——`api_app/main.py` 的寫入路徑
（`_refresh_and_save()`）已經在每次刷新時自動補上這幾個欄位；不執行
本腳本也不影響任何既有功能，只是那些既有歷史列在被下一次刷新之前，
`resolved_params` 等欄位維持 `NULL`（讀取端已設計成容忍這個狀態）。

用法：

    DATABASE_URL=postgresql://... python scripts/backfill_result_fact_context.py

中斷後直接重跑即可續跑（見 `api_app/storage/backfill.py` docstring）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app.storage.backfill import backfill_result_fact_context  # noqa: E402
from api_app.storage.postgres import PostgresStorage  # noqa: E402


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("需要 DATABASE_URL 環境變數才能連線到正式資料庫")
    db = PostgresStorage(dsn)
    summary = backfill_result_fact_context(db)
    print(f"backfill 完成：{summary['scenarios']} 個劇本、"
          f"{summary['rows']} 筆歷史結果已重新寫入 fact context。")


if __name__ == "__main__":
    main()
