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
    contracts = tuple(OptionContract(**c) for c in data["contracts"])
    return ChainSnapshot(
        schema_version=data["schema_version"], symbol=data["symbol"],
        fetched_at=data["fetched_at"], spot=data["spot"],
        source=data["source"], contracts=contracts,
    )


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


def snapshot_today(fetched_at: str) -> date:
    """Spec §8: 'today' = fetched_at converted to US/Eastern, date part."""
    return datetime.fromisoformat(fetched_at).astimezone(_EASTERN).date()
