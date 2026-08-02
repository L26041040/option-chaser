"""D1（#14）：詳細頁選中 Spread 後，主圖旁顯示 Long Call 追平價格
（AppTest）。數學正確性由 tests/test_valuation.py（純函式）與
tests/test_service_catchup.py（服務層接線）覆蓋，這裡只驗證整頁串接：
選中 Spread 才顯示、選中單腳不顯示。"""
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


def _leg(sym, option_type, strike, bid, ask):
    return {"contract_symbol": sym, "option_type": option_type, "strike": strike,
            "expiry": EXP, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _write_snapshot(tmp_path) -> str:
    snap = {"schema_version": 2, "symbol": "XYZ", "fetched_at": TS,
           "spot": 100.0, "source": "yfinance",
           "contracts": [_leg("A", "call", 100, 4.95, 5.05),
                        _leg("B", "call", 110, 0.95, 1.05)]}
    f = Path(tmp_path) / "snap.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    fix = _write_snapshot(tmp_path / "fixture")
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path / "workspace"))
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, fix, progress))
    from option_chaser.data.snapshot import load_snapshot
    monkeypatch.setattr(service, "fetch_and_save",
                        lambda symbol: (load_snapshot(fix), fix))
    return str(tmp_path / "workspace"), fix


def _run_page():
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True
    at.run()
    return at


def test_catchup_price_shown_next_to_selected_spread(ws):
    ws_root, fix = ws
    sc = workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-08", notes="", strategies=("bull-call-spread",),
        ts=TS, observed=date(2026, 7, 15))
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=fix, ts=TS)
    at = _run_page()
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert any("Long Call 追平價格" in c for c in captions)


def test_no_catchup_price_for_single_leg_selection(ws):
    ws_root, fix = ws
    sc = workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-08", notes="", strategies=("long-call",),
        ts=TS, observed=date(2026, 7, 15))
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=fix, ts=TS)
    at = _run_page()
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert not any("Long Call 追平價格" in c for c in captions)
