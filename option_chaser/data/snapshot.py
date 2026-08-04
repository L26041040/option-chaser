"""Snapshot persistence + snapshot-derived 'today'. Stdlib only."""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, astuple, fields
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..models import SCHEMA_VERSION, ChainSnapshot, OptionContract, SnapshotSchemaError

_EASTERN = ZoneInfo("America/New_York")


def save_snapshot(snap: ChainSnapshot, path: str | Path) -> None:
    data = asdict(snap)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )


def snapshot_from_dict(data: dict) -> ChainSnapshot:
    """V8（#56）：把 `dataclasses.asdict(ChainSnapshot)` 的 dict 形式還原成
    物件——`load_snapshot`（讀檔）與 API 層的 `Storage.get_snapshot`（讀
    儲存層，serverless 沒有檔案系統）現在共用同一段還原邏輯，不各自重
    寫一次 `OptionContract(**c) for c in data["contracts"]`。不做 schema
    版本檢查（呼叫端＝自己剛存過的資料，不是使用者上傳的檔案，版本
    不合的情境不存在）。"""
    contracts = tuple(OptionContract(**c) for c in data["contracts"])
    return ChainSnapshot(
        schema_version=data["schema_version"], symbol=data["symbol"],
        fetched_at=data["fetched_at"], spot=data["spot"],
        source=data["source"], contracts=contracts,
    )


def load_snapshot(path: str | Path) -> ChainSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("schema_version")
    if version == 1:
        raise SnapshotSchemaError(
            "快照為 v1 格式（僅含 call），請重新抓取（schema_version=1，需要 2）"
        )
    if version != SCHEMA_VERSION:
        raise SnapshotSchemaError(
            f"snapshot schema_version={version} incompatible with {SCHEMA_VERSION}; re-fetch the chain"
        )
    return snapshot_from_dict(data)


def snapshot_to_csv(snap: ChainSnapshot) -> str:
    """QA1-10（#37）：整份原始選擇權鏈快照轉 CSV，供需求方查證畫面數字
    （原話「免得你亂掰我卻查不到證據」）。純轉換函式——不碰檔案 I/O 或
    UI，取得（`load_snapshot`）／轉換（本函式）／輸出（呼叫端）三層
    清楚分離，換儲存後端時只需替換取得層。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(f.name for f in fields(OptionContract))
    for c in snap.contracts:
        writer.writerow(astuple(c))
    return buf.getvalue()


def find_contract(
    snap: ChainSnapshot, option_type: str, strike: float, expiry: str
) -> OptionContract | None:
    """D1（#14）：依 option_type／strike／expiry 精確比對，從快照裡找出單一
    合約——用於「同履約價、不同 option_type」的查找（Spread 買腿是 put 時，
    找同履約價的 call 來算 Long Call 追平價格）。找不到回傳 None，不拋錯。"""
    for c in snap.contracts:
        if c.option_type == option_type and c.strike == strike and c.expiry == expiry:
            return c
    return None


def snapshot_today(fetched_at: str) -> date:
    """Spec §8: 'today' = fetched_at converted to US/Eastern, date part."""
    return datetime.fromisoformat(fetched_at).astimezone(_EASTERN).date()
