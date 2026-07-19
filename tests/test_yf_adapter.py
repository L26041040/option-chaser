import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

from option_chaser.data.yf import fetch_chain, map_rows
from option_chaser.models import FetchError

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


class _FakeCalls:
    """Stand-in for the pandas DataFrame returned by yfinance's option_chain().calls."""
    def __init__(self, records):
        self._records = records

    def to_dict(self, orient):
        assert orient == "records"
        return [dict(r) for r in self._records]


class _FakeChain:
    def __init__(self, records):
        self.calls = _FakeCalls(records)
        self.puts = _FakeCalls([])


class _FakeTicker:
    def __init__(self, symbol, spot=100.0, options=(), records=None):
        self.symbol = symbol
        self.fast_info = {"last_price": spot}
        self.options = options
        self._records = records or []

    def option_chain(self, expiry):
        return _FakeChain(self._records)


def _install_fake_yfinance(monkeypatch, ticker_factory):
    fake = types.ModuleType("yfinance")
    fake.Ticker = ticker_factory
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_fetch_chain_maps_via_fake_yfinance(monkeypatch):
    record = {
        "contractSymbol": "XYZ261016C00110000", "strike": 110.0,
        "bid": 3.0, "ask": 3.25, "lastPrice": 3.1, "volume": 152,
        "openInterest": 830, "impliedVolatility": 0.38,
    }
    _install_fake_yfinance(
        monkeypatch,
        lambda symbol: _FakeTicker(symbol, spot=100.0, options=("2026-10-16",), records=[record]),
    )

    snap = fetch_chain("XYZ")

    assert snap.spot == 100.0
    assert snap.source == "yfinance"
    assert len(snap.contracts) == 1
    c = snap.contracts[0]
    assert c.expiry == "2026-10-16"
    assert c.contract_symbol == "XYZ261016C00110000"
    assert c.strike == 110.0
    assert c.bid == 3.0 and c.ask == 3.25 and c.last == 3.1
    assert c.volume == 152 and c.open_interest == 830
    assert c.implied_volatility == 0.38
    datetime.fromisoformat(snap.fetched_at)  # fetched_at must parse as ISO datetime


def test_fetch_chain_raises_fetcherror_on_yf_exception(monkeypatch):
    def _raising_ticker(symbol):
        raise RuntimeError("boom")

    _install_fake_yfinance(monkeypatch, _raising_ticker)

    with pytest.raises(FetchError):
        fetch_chain("XYZ")


def test_fetch_chain_raises_fetcherror_on_empty_chain(monkeypatch):
    _install_fake_yfinance(
        monkeypatch,
        lambda symbol: _FakeTicker(symbol, spot=100.0, options=(), records=[]),
    )

    with pytest.raises(FetchError):
        fetch_chain("XYZ")


def test_option_type_mapped():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snap = map_rows("XYZ", 100.0, "2026-07-15T21:30:00-04:00", rows)
    assert snap.contracts[0].option_type == "call"
    assert snap.contracts[2].option_type == "put"


def test_fetch_chain_maps_both_sides(monkeypatch):
    fake = types.ModuleType("yfinance")

    class FakeCalls:
        def __init__(self, records): self._r = records
        def to_dict(self, kind): return self._r

    class FakeChain:
        def __init__(self):
            self.calls = FakeCalls([{"contractSymbol": "C1", "strike": 110.0,
                "bid": 3.0, "ask": 3.25, "lastPrice": 3.1, "volume": 152,
                "openInterest": 830, "impliedVolatility": 0.38}])
            self.puts = FakeCalls([{"contractSymbol": "P1", "strike": 90.0,
                "bid": 2.8, "ask": 3.0, "lastPrice": 2.9, "volume": 100,
                "openInterest": 400, "impliedVolatility": 0.40}])

    class FakeTicker:
        def __init__(self, symbol):
            self.fast_info = {"last_price": 100.0}
            self.options = ("2026-10-16",)
        def option_chain(self, expiry): return FakeChain()

    fake.Ticker = FakeTicker
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    snap = fetch_chain("XYZ")
    types_seen = {c.option_type for c in snap.contracts}
    assert types_seen == {"call", "put"} and len(snap.contracts) == 2
