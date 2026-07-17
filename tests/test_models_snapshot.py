from datetime import date
from option_chaser.models import (
    OptionContract, ChainSnapshot, SCHEMA_VERSION, SnapshotSchemaError,
)
from option_chaser.data.snapshot import save_snapshot, load_snapshot, snapshot_today
import pytest


def make_snap():
    c = OptionContract(
        contract_symbol="XYZ261016C00110000", strike=110.0, expiry="2026-10-16",
        bid=3.0, ask=3.25, last=3.1, volume=152, open_interest=830,
        implied_volatility=0.38,
    )
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol="XYZ",
        fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
        source="yfinance", contracts=(c,),
    )


def test_roundtrip(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    assert load_snapshot(p) == snap


def test_schema_mismatch(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 99')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError):
        load_snapshot(p)


def test_snapshot_today_eastern():
    # 21:30 EDT on 7/15 is still 7/15 in New York
    assert snapshot_today("2026-07-15T21:30:00-04:00") == date(2026, 7, 15)
    # 03:00 UTC on 7/16 is 23:00 EDT on 7/15 -> "today" is 7/15
    assert snapshot_today("2026-07-16T03:00:00+00:00") == date(2026, 7, 15)
