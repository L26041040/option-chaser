"""Snapshot persistence + snapshot-derived 'today'. Stdlib only."""
from __future__ import annotations

import json
from dataclasses import asdict
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
    if data.get("schema_version") != SCHEMA_VERSION:
        raise SnapshotSchemaError(
            f"snapshot schema_version={data.get('schema_version')} incompatible "
            f"with {SCHEMA_VERSION}; re-fetch the chain"
        )
    contracts = tuple(OptionContract(**c) for c in data["contracts"])
    return ChainSnapshot(
        schema_version=data["schema_version"], symbol=data["symbol"],
        fetched_at=data["fetched_at"], spot=data["spot"],
        source=data["source"], contracts=contracts,
    )


def snapshot_today(fetched_at: str) -> date:
    """Spec §8: 'today' = fetched_at converted to US/Eastern, date part."""
    return datetime.fromisoformat(fetched_at).astimezone(_EASTERN).date()
