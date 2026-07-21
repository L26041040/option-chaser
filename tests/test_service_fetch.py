"""v5 spec §4: service 抽出 fetch_and_save 供 workspace.analyze_group 共用。"""
import json
from pathlib import Path

from option_chaser import service
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def test_fetch_and_save_returns_snap_and_path(tmp_path, monkeypatch):
    snap = load_snapshot(FIX)
    import option_chaser.data.yf as yf
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: snap)
    monkeypatch.chdir(tmp_path)   # snapshots/ 寫在 cwd
    got_snap, path = service.fetch_and_save("XYZ")
    assert got_snap == snap
    p = Path(path)
    assert p.exists() and p.parent.name == "snapshots"
    assert ":" not in p.name
    assert json.loads(p.read_text(encoding="utf-8"))["symbol"] == "XYZ"


def test_run_delegates_to_fetch_and_save(monkeypatch):
    """run 只是 fetch_and_save + _analyze 的組合（行為不變的結構性證據）。"""
    snap = load_snapshot(FIX)
    calls = []

    def fake_fetch_and_save(symbol):
        calls.append(symbol)
        return snap, FIX

    monkeypatch.setattr(service, "fetch_and_save", fake_fetch_and_save)
    from option_chaser.models import AnalysisParams
    result = service.run(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_date="2026-08-01"),
        strategies=("long-call",)))
    assert calls == ["XYZ"]
    assert result.meta.snapshot_path == FIX
