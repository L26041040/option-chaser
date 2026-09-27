"""AUTH-07（PB-03／#295）的舊入口——現在只是
`scripts/repair_production_data_lifecycle.py` 的薄殼（CLAUDE-DB-HYGIENE-002）。

solo 搬遷不再有自己的一份實作：原本這支腳本直接呼叫一個不原子、不處理
衝突的 `migrate_owner()`，也不救 NULL-owner 的舊劇本。現在所有步驟（含
NULL-owner 救援、current_results 重建、protected 標記與驗證）都在 canonical
腳本裡，這裡只轉呼叫，參數與行為完全相同（預設 dry-run，`--confirm` 才寫入）。

    DATABASE_URL=postgresql://... python scripts/migrate_solo_to_owner.py \\
        --target-owner-id <REAL_OWNER_ID> [--confirm]
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_production_data_lifecycle import main  # noqa: E402

if __name__ == "__main__":
    main()
