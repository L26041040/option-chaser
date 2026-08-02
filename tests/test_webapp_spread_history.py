"""T11（#25）：詳細頁選中 Spread 後顯示其歷史區塊（AppTest）。"""
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


def _write_snapshot(tmp_path, fetched_at) -> str:
    snap = {"schema_version": 2, "symbol": "XYZ", "fetched_at": fetched_at,
           "spot": 100.0, "source": "yfinance",
           "contracts": [_leg("A", 100, 4.95, 5.05), _leg("B", 110, 0.95, 1.05)]}
    f = Path(tmp_path) / "snap.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    fix = _write_snapshot(tmp_path / "fixture", TS)
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
    return ws_root, sc.id


def _run_page():
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True
    at.run()
    return at


def test_history_expander_shows_the_selected_candidates_own_series(ws):
    ws_root, sid = ws
    at = _run_page()
    assert not at.exception
    expander = next(e for e in at.expander if e.label == "Spread 歷史")
    table = expander.markdown[0].value

    key = at.session_state["ws-selected-key"]
    expected = workspace.spread_history(ws_root, sid, key)
    assert len(expected) == 1
    assert f"{expected[0]['rank_in_expiry']}" in table.splitlines()[-1]
    assert TS in table


def test_history_reflects_a_second_refresh_as_one_growing_series(ws, monkeypatch):
    ws_root, sid = ws
    fix2 = _write_snapshot(Path(ws_root).parent / "fixture2",
                           "2026-07-22T21:30:00-04:00")
    from option_chaser.data.snapshot import load_snapshot
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, fix2, progress))
    monkeypatch.setattr(service, "fetch_and_save",
                        lambda symbol: (load_snapshot(fix2), fix2))
    workspace.analyze_scenario(ws_root, sid, snapshot_path=fix2,
                               ts="2026-07-22T21:30:00-04:00")

    at = _run_page()
    key = at.session_state["ws-selected-key"]
    expected = workspace.spread_history(ws_root, sid, key)
    assert len(expected) == 2   # 兩次刷新，同一 Spread 身份的連續序列

    expander = next(e for e in at.expander if e.label == "Spread 歷史")
    table = expander.markdown[0].value
    assert TS in table and "2026-07-22T21:30:00-04:00" in table
