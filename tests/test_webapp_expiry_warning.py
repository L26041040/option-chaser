"""FB3-02（#45）：到期日候選池過少警示（AppTest）。

品質過濾把某期候選殺到 < 3 組時，該期 Top 10 區塊要明示「僅 N 組」，
不再無聲端出唯一倖存者當「該期最高收益」——41% 誤導事件（
`docs/user-feedback-v3.md` 第 4 點）的產品層修正；引擎層病因由 #44 處理。"""
import json
from datetime import date
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import service, workspace

PAGE = "webapp/app.py"
TS = "2026-07-15T21:30:00-04:00"
AUTO_REFRESH_KEY = "ws-auto-refreshed"
EXP = "2026-08-21"


def _leg(sym, strike, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": EXP, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _write_snapshot(tmp_path, contracts) -> str:
    snap = {"schema_version": 2, "symbol": "XYZ", "fetched_at": TS,
           "spot": 100.0, "source": "yfinance",
           "contracts": contracts}
    f = Path(tmp_path) / "snap.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


def _setup(tmp_path, monkeypatch, contracts):
    fix = _write_snapshot(tmp_path / "fixture", contracts)
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path / "workspace"))
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, fix, progress))
    from option_chaser.data.snapshot import load_snapshot
    monkeypatch.setattr(service, "fetch_and_save",
                        lambda symbol: (load_snapshot(fix), fix))
    ws_root = str(tmp_path / "workspace")
    sc = workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-08", notes="", strategies=("bull-call-spread",),
        ts=TS, observed=date(2026, 7, 15))
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=fix, ts=TS)


def _run_page():
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True
    at.run()
    return at


def test_starved_expiry_shows_survivor_count_warning(tmp_path, monkeypatch):
    """兩檔履約價＝該期只有 1 組有效 pair（< 3）→ 警示出現且含實際組數。"""
    _setup(tmp_path, monkeypatch,
           [_leg("A", 100, 4.95, 5.05), _leg("B", 110, 0.95, 1.05)])
    at = _run_page()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert any("僅 1 組" in w for w in warnings), warnings


def test_healthy_expiry_has_no_survivor_warning(tmp_path, monkeypatch):
    """四檔履約價＝該期 6 組 pair（≥ 3）→ 不出現候選池警示。"""
    _setup(tmp_path, monkeypatch,
           [_leg("A", 100, 4.95, 5.05), _leg("B", 105, 2.45, 2.55),
            _leg("C", 110, 0.95, 1.05), _leg("D", 115, 0.45, 0.55)])
    at = _run_page()
    assert not at.exception
    warnings = [w.value for w in at.warning]
    assert not any("組候選通過品質過濾" in w for w in warnings), warnings
