from datetime import date
from option_chaser.models import (
    OptionContract, ChainSnapshot, SCHEMA_VERSION, SnapshotSchemaError,
    STRATEGIES, SINGLE_LEG_STRATEGIES, SPREAD_STRATEGIES,
    leg_option_type, is_bullish, PairReport,
)
from option_chaser.data.snapshot import save_snapshot, load_snapshot, snapshot_today
import pytest


def make_snap():
    c = OptionContract(
        contract_symbol="XYZ261016C00110000", strike=110.0, expiry="2026-10-16",
        bid=3.0, ask=3.25, last=3.1, volume=152, open_interest=830,
        implied_volatility=0.38, option_type="call",
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


def test_strategy_helpers():
    assert STRATEGIES == ("long-call", "long-put", "bull-call-spread", "bear-put-spread")
    assert set(SINGLE_LEG_STRATEGIES) == {"long-call", "long-put"}
    assert set(SPREAD_STRATEGIES) == {"bull-call-spread", "bear-put-spread"}
    assert leg_option_type("long-call") == "call"
    assert leg_option_type("bull-call-spread") == "call"
    assert leg_option_type("long-put") == "put"
    assert leg_option_type("bear-put-spread") == "put"
    assert is_bullish("long-call") and is_bullish("bull-call-spread")
    assert not is_bullish("long-put") and not is_bullish("bear-put-spread")


def test_schema_mismatch_updated_for_v2(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 99')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError):
        load_snapshot(p)


def test_schema_v1_rejected_with_refetch_message(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 1')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError) as ei:
        load_snapshot(p)
    assert "請重新抓取" in str(ei.value)


def test_pair_report_shape():
    pr = PairReport(total_pairs=6, removed_sanity=2, passed=4)
    assert pr.passed == 4


def test_snapshot_today_eastern():
    # 21:30 EDT on 7/15 is still 7/15 in New York
    assert snapshot_today("2026-07-15T21:30:00-04:00") == date(2026, 7, 15)
    # 03:00 UTC on 7/16 is 23:00 EDT on 7/15 -> "today" is 7/15
    assert snapshot_today("2026-07-16T03:00:00+00:00") == date(2026, 7, 15)
