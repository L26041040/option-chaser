"""v6 spec §3.1/既有 help 頁遷移：AppTest via router (webapp/app.py) + switch_page。
本測試獨立於 Task 12 的 app.py 路由重寫——先用 AppTest.from_file 直接驗證頁面腳本
本身在 stub session_state 下可執行（views 檔案本身零例外），Task 12 完成後另有
test_app_navigation.py 驗證完整路由整合。"""
import os
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def test_overview_empty_workspace_shows_guidance(ws):
    # overview.py 現含 st.page_link（空工作區分支）——st.page_link 要求入口腳本
    # 已宣告 st.navigation，故經真實路由到達本頁，而非直接載入本檔。
    at = AppTest.from_file("webapp/app.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "建立第一個劇本" in body


def test_overview_metrics_reflect_workspace(ws):
    workspace.create_scenario(ws, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts=TS)
    at = AppTest.from_file("webapp/views/overview.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert ">1<" in body or "1" in body   # Active 劇本數 = 1


def test_overview_no_position_language(ws):
    at = AppTest.from_file("webapp/app.py")
    at.run()
    body = " ".join(m.value for m in at.markdown)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in body


def test_help_page_renders():
    from option_chaser.glossary import GLOSSARY
    at = AppTest.from_file("webapp/views/help.py")
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert any(term in body for term in GLOSSARY)
