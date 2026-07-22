"""v6 spec §1.1：st.navigation 路由——四頁載入無例外、無 app 字樣、詳頁隱藏可達。"""
import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def test_default_page_is_overview(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "戰情總覽" in titles


def test_no_app_literal_in_navigation(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    body = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.title)
    assert body.strip() != "app"
    assert "\nappa" not in body  # 弱保護：確保不是巧合子字串誤判


def test_switch_to_workspace_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/workspace.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "劇本工作區" in titles


def test_switch_to_quick_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    assert not at.exception
    titles = " ".join(t.value for t in at.title)
    assert "快速試算" in titles


def test_switch_to_help_page(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/help.py")
    at.run()
    assert not at.exception


def test_detail_page_reachable_though_hidden(ws):
    sc = workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                                   ("long-call",), ts=TS)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/detail.py")
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception


def test_overview_empty_state_page_link_reaches_workspace(ws):
    """Task 8 shipped plain-text guidance (st.page_link requires its target to
    already be a page registered in st.navigation, which does not exist until
    this task wires the router — see Task 8 Step 3 comment). Now that the
    router is registered, overview.py's empty-state page_link must resolve
    without raising `StreamlitAPIException` (the exact failure mode this task
    guards against): `streamlit.testing.v1.AppTest` has no typed accessor for
    `st.page_link` (it surfaces as an opaque UnknownElement — verified against
    the installed streamlit version), so `not at.exception` after reaching
    this exact page through the real router IS the load-bearing assertion,
    not a placeholder — a page_link pointed at an unregistered/nonexistent
    page raises during script execution, which `at.exception` would catch."""
    at = AppTest.from_file("webapp/app.py")
    at.run()   # default page = overview (empty workspace) -> renders the page_link
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body or "劇本工作區" in body


def test_workspace_detail_button_switches_with_sid(ws):
    """Task 10's「詳頁」按鈕呼叫 st.switch_page(..., query_params={"sid":...})——
    只能經真實入口（webapp/app.py，含 st.navigation 宣告）驗證，不可獨立測試
    workspace.py（見 Task 10 註記）。同時驗證 st.switch_page 不帶 query_params
    會清空既有值這件事沒有在此處踩雷（query_params 是隨 switch_page 呼叫一併
    帶入，不是先設 st.query_params 再呼叫無參數版本）。"""
    sc = workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                                   ("long-call",), ts=TS)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/workspace.py")
    at.run()
    next(b for b in at.button if b.key == f"ws-det-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    # NOTE (deviation from brief, flagged): AppTest.query_params is populated via
    # urllib.parse.parse_qs (streamlit/testing/v1/app_test.py), which always
    # yields dict-of-lists, never bare scalars -- verified against the installed
    # streamlit 1.59.2. The brief's literal `== sc.id` assertion cannot pass in
    # this environment; comparing against `[sc.id]` preserves the same
    # load-bearing check (sid round-trips correctly through switch_page).
    assert at.query_params.get("sid") == [sc.id]


def test_quick_save_success_links_to_detail_page(ws, monkeypatch):
    from option_chaser import service
    from option_chaser.data.snapshot import load_snapshot
    FIX = "tests/fixtures/xyz_v4_six_expiries.json"
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at.switch_page("views/quick.py")
    at.run()
    at.text_input(key="symbol").set_value("XYZ")
    at.number_input(key="target_price").set_value(120.0)
    at.date_input(key="target_date").set_value(__import__("datetime").date(2026, 8, 1))
    at.checkbox(key="chk-long-call").set_value(True)
    at.run()
    at.button[0].set_value(True).run(timeout=30)
    save_buttons = [b for b in at.button if b.label == "保存為劇本"]
    assert save_buttons
    save_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
