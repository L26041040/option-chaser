# tests/test_views_workspace.py
"""v6 spec §3.2/§3.5：劇本工作區卡片牆——沿用 v5 test_webapp_workspace.py 全部
語意斷言，改為卡片/popover 呈現形式；新增 candidate_card 價格顯示斷言。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/views/workspace.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    import option_chaser.service as svc
    real_offline = svc.run_offline
    monkeypatch.setattr(svc, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))
    from option_chaser.data.snapshot import load_snapshot
    monkeypatch.setattr(svc, "fetch_and_save",
                        lambda symbol: (load_snapshot(FIX), FIX))
    return tmp_path


def _mk(ws_root, price=120.0, tdate="2026-08-01"):
    return workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=price,
        target_date=tdate, notes="", strategies=("long-call",), ts=TS)


def _body(at):
    return " ".join(m.value for m in at.markdown)


def test_scenario_card_shows_symbol_and_status(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert "XYZ" in _body(at)


def test_scenario_card_price_after_analysis(ws):
    sc = _mk(ws)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    assert "每張/組" in body or "每張" in body   # candidate_card 摘要含成本


def test_manage_popover_contains_status_actions(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    popover_labels = [p.proto.popover.label for p in at.get("popover")]
    assert "⋯ 管理" in body or any("管理" in lbl for lbl in popover_labels)
    # popover 內容須存在標記達成/標記失效/刪除按鈕（按鍵 key 前綴檢查）
    assert any(b.key and b.key.startswith("ws-reach-") for b in at.button)
    assert any(b.key and b.key.startswith("ws-inv-") for b in at.button)
    assert any(b.key and b.key.startswith("ws-del-") for b in at.button)


def test_status_change_requires_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert any("請填原因" in e.value for e in at.error)


def test_reanalyze_button_requires_both_conditions(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")

    def has_rean(at):
        return any(bt.key == f"ws-rean-{b.id}" for bt in at.button)

    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)
    workspace.set_status(ws, a.id, "Reached", reason="到價", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)
    workspace.confirm_relation(ws, "G-XYZ", (a.id, b.id), "milestone-path", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert has_rean(at)


def test_group_analyze_shares_snapshot(ws):
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")
    at = AppTest.from_file(PAGE)
    at.run()
    next(bt for bt in at.button if bt.key == "ws-gan-G-XYZ").set_value(True).run(timeout=60)
    assert not at.exception
    va = workspace.latest_result(ws, a.id)
    vb = workspace.latest_result(ws, b.id)
    assert va["snapshot_ref"]["path"] == vb["snapshot_ref"]["path"]


def test_no_position_language(ws):
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body
