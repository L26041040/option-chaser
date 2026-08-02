"""V1（#48）prefactor：`service.fetch_chain`（純抓取降級鏈，不落盤）與
`service.run_with_snapshot`（分析記憶體中的快照）兩個公開接縫。

理由：serverless 檔案系統唯讀，API 層不能走會 `mkdir("snapshots")` 的
`fetch_and_save`；也不該伸手進私有的 `_analyze`。這兩個接縫都只是把
既有能力公開出來，不含任何新的計算邏輯——引擎行為不變（`fetch_and_save`
改為呼叫 `fetch_chain` 後落盤，其既有測試原樣通過）。"""
from datetime import date

import pytest

from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams, FetchError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _request():
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0, target_month="2026-08",
                                   min_return=0.0),
        strategies=("bull-call-spread",))


def test_fetch_chain_prefers_cboe(monkeypatch):
    import option_chaser.data.cboe as cboe
    snap = load_snapshot(FIX)
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    assert service.fetch_chain("XYZ") is snap


def test_fetch_chain_falls_back_to_yfinance(monkeypatch):
    import option_chaser.data.cboe as cboe
    import option_chaser.data.yf as yf
    snap = load_snapshot(FIX)

    def boom(symbol):
        raise FetchError("cboe down")

    monkeypatch.setattr(cboe, "fetch_chain", boom)
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: snap)
    assert service.fetch_chain("XYZ") is snap


def test_fetch_chain_does_not_touch_the_filesystem(tmp_path, monkeypatch):
    """唯讀檔案系統前提：純抓取不得落盤（`fetch_and_save` 才落盤）。"""
    import option_chaser.data.cboe as cboe
    snap = load_snapshot(FIX)          # chdir 前先載入：FIX 是相對路徑
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    monkeypatch.chdir(tmp_path)
    service.fetch_chain("XYZ")
    assert list(tmp_path.iterdir()) == []


def test_run_with_snapshot_matches_run_offline():
    """分析記憶體快照的結果，與既有離線重放路徑等價（同一份快照）。"""
    snap = load_snapshot(FIX)
    from_memory = service.run_with_snapshot(_request(), snap, snapshot_ref=FIX)
    from_disk = service.run_offline(_request(), FIX)
    assert from_memory.meta == from_disk.meta
    assert from_memory.baseline_expiry == from_disk.baseline_expiry
    assert from_memory.baseline_selection == from_disk.baseline_selection
    assert from_memory.today == from_disk.today == date(2026, 7, 15)


def test_run_with_snapshot_validates_the_request():
    snap = load_snapshot(FIX)
    bad = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0, target_month="2026-08"),
        strategies=())
    with pytest.raises(Exception):
        service.run_with_snapshot(bad, snap)
