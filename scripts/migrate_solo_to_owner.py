"""一次性遷移腳本（PB-03／#295，Anonymous Public Beta）：把 Owner 既有
的 `solo` 名下全部資料，認領到 Owner 自己透過正常 Browser Identity
（軸一，PB-02／#294）取得的 owner_id，並把該 owner_id 標記為
`protected`（結構性豁免 PB-08 的閒置清理政策）。

**前置步驟（HITL，agent 無法代勞）**：Owner 用自己的瀏覽器造訪一次
正式站任意一個會建立 owner-scoped 請求的頁面（例如首頁劇本清單），
PB-02 的 cookie middleware 會自動幫他建立一個新 owner 並簽發 cookie。
接著打開瀏覽器開發者工具 → Application／儲存空間 → Cookies，找到
`__Host-oc_owner` 這顆 cookie 的值——**這不是 owner_id 本身**（PB-01
既有不變量：cookie token 與 owner_id 是分開儲存的兩個值），要換成
owner_id 有兩種方式：

1. 呼叫 `GET /api/ops/metrics`（帶 `OPS_SECRET`）目前不回報 per-owner
   id；最直接的方式是在有資料庫連線的環境跑
   `python -c "from api_app.storage.postgres import PostgresStorage;
   import os; db = PostgresStorage(os.environ['DATABASE_URL']);
   print(db.resolve_owner_by_token('<剛剛複製的 cookie 值>'))"`。
2. 或由 PB-10（Super User 管理面）上線後，透過那個介面直接查表列出
   最近建立的 owner。本票之前只能走方式 1。

拿到 owner_id 之後才能執行這支腳本。

冪等、可安全重跑、可中斷續跑——`migrate_owner()` 本身是
`WHERE owner_id = 'solo'` 的條件式批次更新，重跑對已搬過的表全部
回 0；`set_owner_protected()` 同理，重複呼叫不會累積副作用。

用法：

    DATABASE_URL=postgresql://... python scripts/migrate_solo_to_owner.py \
        --target-owner-id <從上面步驟拿到的 owner_id> --confirm

**故意不提供任何猜測預設值**：`--target-owner-id` 必填，且必須額外
加上 `--confirm` 才會真的執行寫入——單純執行（不帶 `--confirm`）只會
印出「將會做什麼」並比對遷移前 `solo` 各表列數，供執行前核對，不動
任何資料（AC「遷移目標 owner_id 若填錯，資料會被認領到錯誤身份」的
最小防呆：先看一遍數字，再決定要不要真的按下去）。

安全考量：本腳本只印每表**列數**，不印任何 `owner_credentials` 的
token 值（比照既有 `backfill_settings_to_owner.py` 慣例）。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_app.identity import SOLO_OWNER  # noqa: E402
from api_app.storage.postgres import PostgresStorage  # noqa: E402


def _count_solo_rows(db: PostgresStorage) -> dict[str, int]:
    """遷移前的「solo 底下現在有幾筆」快照——純讀取，不寫入任何東西。
    直接複用 `migrate_owner()` 自己的表清單，避免這裡另外維護一份
    可能漂移的複本。"""
    counts: dict[str, int] = {}
    with db._connect() as conn:  # noqa: SLF001 — 一次性遷移腳本，讀計數不值得為此開一個新的 public 方法
        for table in db._MIGRATE_OWNER_TABLES:  # noqa: SLF001
            cur = conn.execute(
                f"SELECT count(*) FROM {table} WHERE owner_id = %s", (SOLO_OWNER,))
            counts[table] = cur.fetchone()[0]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-owner-id", required=True,
        help="Owner 透過正常 Browser Identity 取得的 owner_id（見本檔案"
             "檔頭 HITL 前置步驟）——必填，不提供任何猜測預設值。")
    parser.add_argument(
        "--confirm", action="store_true",
        help="真的執行寫入。省略時只印出遷移前快照，不動任何資料。")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("需要 DATABASE_URL 環境變數才能連線到正式資料庫")

    db = PostgresStorage(dsn)

    target = db.get_owner(args.target_owner_id)
    if target is None:
        raise SystemExit(
            f"owner_id={args.target_owner_id!r} 在 owners 表裡不存在——"
            "請先完成本檔案檔頭的 HITL 前置步驟（用自己的瀏覽器造訪一次"
            "正式站，讓 PB-02 的 cookie middleware 先建立這個 owner）")

    before = _count_solo_rows(db)
    total_before = sum(before.values())
    print(f"遷移前 solo（{SOLO_OWNER!r}）底下共 {total_before} 筆，"
         f"逐表：{before}")
    print(f"遷移目標：owner_id={args.target_owner_id!r}"
         f"（created_at={target.created_at}，"
         f"目前 protected={target.protected}）")

    if not args.confirm:
        print("未帶 --confirm，本次不執行任何寫入——確認上面的數字與目標"
             "owner_id 正確後，加上 --confirm 重新執行。")
        return

    counts = db.migrate_owner(from_owner=SOLO_OWNER, to_owner=args.target_owner_id)
    total = sum(counts.values())
    print(f"遷移完成，共搬動 {total} 筆：{counts}")

    db.set_owner_protected(args.target_owner_id, True)
    after_target = db.get_owner(args.target_owner_id)
    print(f"已標記 protected=True（現況：{after_target.protected}）")

    after = _count_solo_rows(db)
    remaining = sum(after.values())
    if remaining:
        print(f"⚠ solo 底下仍有 {remaining} 筆未搬動：{after}——請重新執行"
             "本腳本（冪等，安全重跑）")
    else:
        print("solo 底下 10 張表皆已清空——遷移確認完成。")


if __name__ == "__main__":
    main()
