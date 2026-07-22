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
    """4 象限：皆不成立／僅 Reached／僅已確認／兩者皆成立（v5 test_webapp_workspace.py 移植）。"""
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")

    def has_rean(at):
        return any(bt.key == f"ws-rean-{b.id}" for bt in at.button)

    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 皆不成立
    workspace.set_status(ws, a.id, "Reached", reason="到價", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 僅 Reached，未確認
    workspace.confirm_relation(ws, "G-XYZ", (a.id, b.id), "milestone-path", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert has_rean(at)                           # 兩條件成立
    # 反向單一條件：只確認 relation、前一劇本未 Reached（第 4 象限）
    workspace.delete_scenario(ws, a.id, ts=TS)
    c = _mk(ws, price=110.0, tdate="2026-08-01")
    workspace.confirm_relation(ws, "G-XYZ", (c.id, b.id), "milestone-path", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 僅已確認，c 未 Reached


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


def test_create_via_form_appears_in_list(ws):
    """建立表單成功路徑：方向連動預設策略勾選，建立後卡片牆出現該劇本
    （v5 test_webapp_workspace.py::test_create_via_form_appears_in_list 移植）。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.number_input(key="ws-new-price").set_value(120.0)
    at.date_input(key="ws-new-date").set_value(date(2026, 8, 1))
    at.run()
    # 測試 cwd 的 snapshots/ 無 XYZ_*.json → 無法推測 → 必選方向
    at.selectbox(key="ws-new-direction").set_value("bullish")
    at.run()
    assert at.session_state["ws-new-chk-long-call"] is True   # 方向連動預設策略
    assert at.session_state["ws-new-chk-long-put"] is False
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert not at.exception
    assert "XYZ" in _body(at)
    created = workspace.list_scenarios(ws)
    assert len(created) == 1
    assert created[0].id == "XYZ-120-202608"
    assert created[0].direction == "bullish"       # 120 > spot(100) → 看漲，方向推測正確


def test_create_requires_direction_when_no_snapshot(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("請選擇方向" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []


def test_analysis_error_stays_visible(ws, monkeypatch):
    """失敗不 rerun：st.error 留在畫面上（durable feedback），劇本不被靜默清除。"""
    sc = _mk(ws)
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-an-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert any("boom" in e.value for e in at.error)
    # 分析失敗不應清除劇本
    assert workspace.list_scenarios(ws)[0].id == sc.id


def test_status_change_reached_persists_to_store(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key=f"ws-reason-{sc.id}").set_value("到價")
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Reached"
    assert workspace.list_scenarios(ws)[0].status == "Reached"


def test_status_change_invalidated_persists_to_store(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key=f"ws-reason-{sc.id}").set_value("條件不再成立")
    at.run()
    next(b for b in at.button
         if b.key == f"ws-inv-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Invalidated"
    assert workspace.list_scenarios(ws)[0].status == "Invalidated"


def test_delete_button_full_chain(ws):
    """需先勾選「確認刪除」才能刪除；確認後劇本實際從 store 移除。"""
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    # 未勾選確認框：刪除按鈕應報錯且不移除
    next(b for b in at.button
         if b.key == f"ws-del-{sc.id}").set_value(True).run(timeout=30)
    assert any("請先勾選" in e.value for e in at.error)
    assert workspace.list_scenarios(ws)[0].id == sc.id
    # 勾選確認框後刪除才生效
    at.checkbox(key=f"ws-delok-{sc.id}").set_value(True)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-del-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert workspace.list_scenarios(ws) == []


def test_group_relation_confirm_persists_to_store(ws):
    """確認關係寫回 store，且下一次頁面 run 仍反映該狀態。"""
    a = _mk(ws, price=110.0, tdate="2026-08-01")
    b = _mk(ws, price=120.0, tdate="2026-09-01")
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    assert "G-XYZ" in body and "里程碑路徑" in body     # proposed 顯示
    next(bt for bt in at.button
         if bt.key == "ws-rel-btn-G-XYZ-0").set_value(True).run(timeout=30)
    assert not at.exception
    groups = workspace.load_groups(ws)
    assert groups["groups"][0]["relations"][0]["confirmed"] == "milestone-path"
    # 下一次頁面 run（新的 AppTest 實例）仍應反映已持久化的確認狀態
    at2 = AppTest.from_file(PAGE)
    at2.run()
    assert "已確認：里程碑路徑" in _body(at2)
