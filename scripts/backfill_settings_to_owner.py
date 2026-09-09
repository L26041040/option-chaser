"""一次性 backfill 腳本（SCALE-13／#264，Ownership A-1 Contract）：把
正式資料庫既有 3 張 singleton／provider-key 表（`data_source_settings`
／`provider_credentials`／`provider_verifications`）的資料，複製進
本票新增的 per-owner 表（`owner_settings`／`owner_credentials`／
`owner_verifications`）。

冪等、可重跑、可中斷續跑——**不是部署前置條件**：`api_app/main.py` 的
`get_settings()`／`get_credential()`／`get_verification()` 三個讀取
路徑已經自帶 read-through-with-write-through-on-hit（見
`api_app/storage/postgres.py` 對應方法），solo owner 第一次真正讀取
就會自動把舊資料搬過來；不執行本腳本也不影響任何既有功能，只是要等到
有人真的讀過才會搬。本腳本讓 Owner 可以主動、一次把全部搬完，不必依賴
「剛好有請求觸發」。

只搬「新表這個 owner 還沒有」的那幾筆——絕不覆蓋新表已經存在的資料
（不論那份資料是先前跑過本腳本留下的，還是使用者在這之間透過設定頁
自己存過的新值），重跑對「已經搬過」的部分全部回 0。

用法：

    DATABASE_URL=postgresql://... python scripts/backfill_settings_to_owner.py

舊表（`data_source_settings`／`provider_credentials`／
`provider_verifications`）本身不受影響、不被清空——additive-first
遷移的一部分，不是單向搬家（Rollback Point：在確認穩定前保留舊
shape／資料）。
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
    counts = db.backfill_settings_to_owner(SOLO_OWNER)
    total = sum(counts.values())
    print(f"backfill 完成，補齊 {total} 筆：{counts}")

    null_counts = db.owner_id_null_counts()
    remaining = sum(null_counts.values())
    if remaining:
        print(f"⚠ 8 張 user tables 仍有 {remaining} 筆 owner_id 為 NULL："
             f"{null_counts}（settings/credential/verification 三張本身"
             f"structurally 不可能為 NULL，若看到非零數字，代表其餘 5 張"
             f"row-scoped 表尚未跑過 scripts/backfill_owner_ids.py）")
    else:
        print("AC-5 核對：8 張 user tables 均無 NULL owner。")


if __name__ == "__main__":
    main()
