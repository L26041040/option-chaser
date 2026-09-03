"""v5 spec §4: service 抽出 fetch_and_save 供 workspace.analyze_group 共用。"""
import json
from pathlib import Path

from option_chaser import service
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _yf_must_not_be_reached(symbol):
    raise AssertionError("主源已 stub 成功，不該退到 yfinance 備援")


def test_fetch_and_save_returns_snap_and_path(tmp_path, monkeypatch):
    """Hermetic（#236）：**兩個**資料源都要 stub。

    `service.fetch_chain()` 是「先試 Cboe、失敗才退 yfinance」
    （FB3-01／#44 把主源換成 Cboe）。這條測試原本只 stub 了 yfinance
    ——也就是**備援**那一層——所以在連得到外網的環境裡，Cboe 那一步會
    直接成功，回傳一份帶著「現在」時間戳的真實快照，`got_snap == snap`
    因此失敗（而在擋外網的沙箱裡 Cboe 會拋 FetchError、退到備援，測試
    就綠——同一份程式碼隨環境紅綠不定）。

    主源改回傳 fixture（＝production 實際會走的那條路），備援則放一顆
    地雷：真的被呼叫到就代表主源沒攔住，那是要知道的事，不是可以安靜
    降級的事。兩者合起來保證這條測試在任何網路狀態下都走不到真網路，
    `fetched_at` 一律是 fixture 自己的固定時間。
    """
    snap = load_snapshot(FIX)
    import option_chaser.data.cboe as cboe
    import option_chaser.data.yf as yf
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: snap)
    monkeypatch.setattr(yf, "fetch_chain", _yf_must_not_be_reached)
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
                                   target_month="2026-08"),
        strategies=("long-call",)))
    assert calls == ["XYZ"]
    assert result.meta.snapshot_path == FIX
