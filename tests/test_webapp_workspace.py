# tests/test_webapp_workspace.py
"""v5 spec §7.7: 工作區 GUI（AppTest）。OC_WORKSPACE 隔離＋service seam 注入。"""
from datetime import date
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/pages/0_劇本工作區.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"
OBSERVED = date(2026, 7, 21)   # 與 TS 同日：建立驗證不吃真實時鐘


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


def _mk(ws_root, price=120.0, tmonth="2028-01"):
    return workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=price,
        target_month=tmonth, notes="", strategies=("long-call",), ts=TS,
        observed=OBSERVED)


def _body(at):
    return " ".join(m.value for m in at.markdown)


def test_create_via_form_appears_in_list(ws):
    """T4：三欄填寫即可建立；方向／策略由系統帶入 MVP 預設。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.number_input(key="ws-new-price").set_value(120.0)
    at.text_input(key="ws-new-month").set_value("2028/1")   # 四種寫法之一
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert not at.exception
    assert "XYZ" in _body(at)
    sc = workspace.list_scenarios(ws)[0]
    assert sc.id == "XYZ-120-202801"
    assert sc.target_month == "2028-01"
    assert sc.direction == "bullish"                 # 預設帶入,不經 UI
    assert sc.strategies == ("bull-call-spread",)    # MVP 預設策略
    assert sc.notes == ""                            # 備註欄已移除


def test_create_form_exposes_only_three_inputs(ws):
    """T4：方向／策略／備註不出現在建立表單。"""
    at = AppTest.from_file(PAGE)
    at.run()
    form_text_keys = {t.key for t in at.text_input}
    assert "ws-new-symbol" in form_text_keys
    assert "ws-new-month" in form_text_keys
    assert "ws-new-notes" not in form_text_keys
    assert not any(sb.key == "ws-new-direction" for sb in at.selectbox)
    assert not any((cb.key or "").startswith("ws-new-chk-")
                   for cb in at.checkbox)


def test_create_rejects_unparseable_month(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.text_input(key="ws-new-month").set_value("明年一月")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("目標年月" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []


def test_analysis_error_stays_visible(ws, monkeypatch):
    """失敗不 rerun：st.error 留在畫面上（durable feedback）。"""
    sc = _mk(ws)
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-an-{sc.id}").set_value(True).run(timeout=30)
    assert any("boom" in e.value for e in at.error)
    assert not at.exception


def test_status_buttons_with_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key=f"ws-reason-{sc.id}").set_value("到價")
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Reached"


def test_status_button_requires_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert any("請填原因" in e.value for e in at.error)
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Active"


def test_group_card_and_relation_confirm(ws):
    a = _mk(ws, price=110.0, tmonth="2028-01")
    b = _mk(ws, price=120.0, tmonth="2028-12")
    at = AppTest.from_file(PAGE)
    at.run()
    body = _body(at)
    assert "G-XYZ" in body and "里程碑路徑" in body     # proposed 顯示
    next(bt for bt in at.button
         if bt.key == "ws-rel-btn-G-XYZ-0").set_value(True).run(timeout=30)
    assert not at.exception
    groups = workspace.load_groups(ws)
    assert groups["groups"][0]["relations"][0]["confirmed"] == "milestone-path"


def test_reanalyze_button_requires_both_conditions(ws):
    """負例×2＋正例：單一條件成立不出現（spec §7.7）。"""
    a = _mk(ws, price=110.0, tmonth="2028-01")
    b = _mk(ws, price=120.0, tmonth="2028-12")

    def has_rean(at):
        return any(bt.key == f"ws-rean-{b.id}" for bt in at.button)

    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 皆不成立
    workspace.set_status(ws, a.id, "Reached", reason="到價", ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)                       # 僅 Reached，未確認
    workspace.confirm_relation(ws, "G-XYZ", (a.id, b.id), "milestone-path",
                               ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert has_rean(at)                           # 兩條件成立
    # 反向單一條件：只確認、未 Reached
    workspace.delete_scenario(ws, a.id, ts=TS)
    c = _mk(ws, price=110.0, tmonth="2028-01")
    workspace.confirm_relation(ws, "G-XYZ", (c.id, b.id), "milestone-path",
                               ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not has_rean(at)


def test_capital_pct_shown_after_analysis(ws):
    sc = _mk(ws)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert "佔本金" in _body(at)


def test_detail_page_renders_four_steps(ws):
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-det-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    subheaders = " ".join(s.value for s in at.subheader)
    assert "Step 2" in subheaders and "Step 3" in subheaders \
        and "Step 4" in subheaders


def test_delete_button_full_chain(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.checkbox(key=f"ws-delok-{sc.id}").set_value(True)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-del-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert workspace.list_scenarios(ws) == []


def test_group_analyze_button_shares_snapshot(ws):
    a = _mk(ws, price=110.0, tmonth="2028-01")
    b = _mk(ws, price=120.0, tmonth="2028-12")
    at = AppTest.from_file(PAGE)
    at.run()
    next(bt for bt in at.button
         if bt.key == "ws-gan-G-XYZ").set_value(True).run(timeout=60)
    assert not at.exception
    va = workspace.latest_result(ws, a.id)
    vb = workspace.latest_result(ws, b.id)
    assert va["snapshot_ref"]["path"] == vb["snapshot_ref"]["path"]
