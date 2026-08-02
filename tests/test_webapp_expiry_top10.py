"""T10（#24）：劇本詳細頁兩層結構（AppTest）。

第一層（各期摘要，`render_step3`）沿用既有測試覆蓋；本檔專注第二層
（單期 Top 10 切換）與 baseline 預設選中——這是本票新增的行為。

自建三檔到期日的合成快照（不重用既有 fixture）：`xyz_v4_six_expiries.json`
的 Spread 路徑在 baseline 期（2026-08-21）恰好因單一履約價買賣價差超標
被過濾光（見 apply_filters 對 122 履約價那筆合約的判定），零合格候選，
不適合用來驗證「進頁預設選中 baseline 第 1 名」；自建快照確保 baseline
期本身也有乾淨的合格候選，測試才不會被無關的報價品質巧合影響。
"""
import json
from datetime import date
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import service, workspace
from option_chaser.models import AnalysisParams

PAGE = "webapp/app.py"
TS = "2026-07-15T21:30:00-04:00"
AUTO_REFRESH_KEY = "ws-auto-refreshed"
E1, E2, E3 = "2026-08-21", "2026-09-18", "2026-10-16"   # E1＝baseline


def _leg(sym, strike, expiry, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": expiry, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _write_snapshot(tmp_path) -> str:
    contracts = []
    for i, exp in enumerate((E1, E2, E3)):
        contracts.append(_leg(f"A{i}", 100, exp, 4.95 - i * 0.3, 5.05 - i * 0.3))
        contracts.append(_leg(f"B{i}", 110, exp, 0.95 - i * 0.1, 1.05 - i * 0.1))
    snap = {"schema_version": 2, "symbol": "XYZ", "fetched_at": TS,
           "spot": 100.0, "source": "yfinance", "contracts": contracts}
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
    ws_root = str(tmp_path / "workspace")
    sc = workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-08", notes="", strategies=("bull-call-spread",),
        ts=TS, observed=date(2026, 7, 15))
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=fix, ts=TS)
    return ws_root, fix


def _run_page():
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True   # 已有快照，不需要再自動刷新
    at.run()
    return at


def test_detail_page_defaults_to_baseline_top1(ws):
    _, fix = ws
    at = _run_page()
    assert not at.exception
    expected = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0, target_month="2026-08",
                                   min_return=0.0),
        strategies=("bull-call-spread",)), fix)
    assert expected.baseline_expiry == E1
    assert expected.baseline_selection is not None
    assert at.session_state["ws-selected-key"] == expected.baseline_selection[1]


def test_expiry_tab_defaults_to_baseline_and_lists_its_candidates(ws):
    at = _run_page()
    radio = next(r for r in at.radio if r.key == "ws-selected-key-viewing-expiry")
    assert set(radio.options) == {E1, E2, E3}
    assert radio.value == E1
    assert any(b.key == f"sel-top10-{E1}-bull-call-spread|100|110|{E1}"
              for b in at.button)


def test_switching_tab_shows_that_periods_top10_without_new_api_call(ws, monkeypatch):
    calls = {"n": 0}
    real_run = service.run

    def counting_run(req, progress=None):
        calls["n"] += 1
        return real_run(req, progress)
    monkeypatch.setattr(service, "run", counting_run)

    at = _run_page()
    before = calls["n"]
    radio = next(r for r in at.radio if r.key == "ws-selected-key-viewing-expiry")
    radio.set_value(E2).run(timeout=30)
    assert not at.exception
    assert calls["n"] == before   # 切換到期日純 UI 互動，不呼叫 service.run

    radio2 = next(r for r in at.radio if r.key == "ws-selected-key-viewing-expiry")
    assert radio2.value == E2
    assert any(b.key == f"sel-top10-{E2}-bull-call-spread|100|110|{E2}"
              for b in at.button)
    assert not any(b.key == f"sel-top10-{E1}-bull-call-spread|100|110|{E1}"
                  for b in at.button)   # E1 不再顯示——已切到 E2 的 Top10


def test_selecting_a_non_baseline_candidate_shows_its_own_heatmap_without_api_call(ws, monkeypatch):
    calls = {"n": 0}
    real_run = service.run

    def counting_run(req, progress=None):
        calls["n"] += 1
        return real_run(req, progress)
    monkeypatch.setattr(service, "run", counting_run)

    at = _run_page()
    before = calls["n"]
    radio = next(r for r in at.radio if r.key == "ws-selected-key-viewing-expiry")
    radio.set_value(E2).run(timeout=30)
    btn = next(b for b in at.button
              if b.key == f"sel-top10-{E2}-bull-call-spread|100|110|{E2}")
    btn.set_value(True).run(timeout=30)

    assert not at.exception
    assert calls["n"] == before   # 點選候選純 UI 互動，同樣不觸發 API
    assert at.session_state["ws-selected-key"] == f"bull-call-spread|100|110|{E2}"
    # Step 2 主圖標題含該候選的履約價（同履約價跨期都是 100/110，但
    # selected_key 已證明選中的正是 E2 那一份，Heatmap 隨之重繪不報錯即可）。
    assert any("100" in m.value and "110" in m.value for m in at.markdown)
