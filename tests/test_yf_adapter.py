import json
from pathlib import Path
from option_chaser.data.yf import map_rows

FIXTURE = Path(__file__).parent / "fixtures" / "yf_rows.json"


def test_mapping_and_cleaning():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snap = map_rows("XYZ", 100.0, "2026-07-15T21:30:00-04:00", rows)
    assert snap.symbol == "XYZ" and snap.spot == 100.0 and snap.source == "yfinance"
    c0, c1, c2 = snap.contracts
    # clean row maps verbatim
    assert c0.bid == 3.0 and c0.volume == 152 and c0.implied_volatility == 0.38
    # NaN bid -> None; NaN volume/openInterest -> 0; NaN lastPrice -> None
    assert c1.bid is None and c1.last is None
    assert c1.volume == 0 and c1.open_interest == 0
    assert c1.implied_volatility is None
    # missing lastPrice key -> None
    assert c2.last is None and c2.bid == 1.0
