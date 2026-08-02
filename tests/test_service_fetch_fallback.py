"""FB3-01（#44）：`service.fetch_and_save` 改為 Cboe 優先、yfinance 備援。
快照 `source` 欄位如實記錄實際用了哪個源。"""
from datetime import datetime, timezone

import pytest

from option_chaser import service
from option_chaser.models import (ChainSnapshot, FetchError, OptionContract,
                                  SCHEMA_VERSION)


def _snap(source):
    c = OptionContract(
        contract_symbol="TLT260731C00065000", option_type="call", strike=65.0,
        expiry="2026-07-31", bid=17.15, ask=17.3, last=21.55, volume=0,
        open_interest=0, implied_volatility=None)
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol="TLT",
        fetched_at=datetime(2026, 8, 2, 14, 30, tzinfo=timezone.utc)
        .isoformat(timespec="seconds"),
        spot=86.11, source=source, contracts=(c,))


@pytest.fixture
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # fetch_and_save 落盤到 cwd 下的 snapshots/
    return tmp_path


def test_cboe_success_is_primary(in_tmp_cwd, monkeypatch):
    import option_chaser.data.cboe as cboe
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: _snap("cboe"))
    snap, path = service.fetch_and_save("TLT")
    assert snap.source == "cboe"
    assert "snapshots" in path


def test_cboe_failure_falls_back_to_yfinance(in_tmp_cwd, monkeypatch):
    import option_chaser.data.cboe as cboe
    import option_chaser.data.yf as yf

    def cboe_fail(symbol):
        raise FetchError("cboe down")

    monkeypatch.setattr(cboe, "fetch_chain", cboe_fail)
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: _snap("yfinance"))
    snap, path = service.fetch_and_save("TLT")
    assert snap.source == "yfinance"


def test_both_sources_failing_raises_fetch_error(in_tmp_cwd, monkeypatch):
    import option_chaser.data.cboe as cboe
    import option_chaser.data.yf as yf

    def fail(symbol):
        raise FetchError("down")

    monkeypatch.setattr(cboe, "fetch_chain", fail)
    monkeypatch.setattr(yf, "fetch_chain", fail)
    with pytest.raises(FetchError):
        service.fetch_and_save("TLT")
