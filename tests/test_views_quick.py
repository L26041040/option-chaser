"""v6 spec §1.2/§3.4：快速試算頁——沿用 v5 app.py 全部語意斷言（併入自
test_webapp.py + test_webapp_v4.py），新增副標與保存為劇本斷言。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams, FetchError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
PAGE = "webapp/views/quick.py"


def _patched(monkeypatch):
    real_offline = service.run_offline
    monkeypatch.setattr(service, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))


def _fill_and_submit(at, symbol="XYZ", price=120.0, checks=("long-call",)):
    at.text_input(key="symbol").set_value(symbol)
    at.number_input(key="target_price").set_value(price)
    at.date_input(key="target_date").set_value(date(2026, 8, 1))
    for s in ("long-call", "bull-call-spread", "long-put", "bear-put-spread"):
        at.checkbox(key=f"chk-{s}").set_value(s in checks)
    at.run()
    at.button[0].set_value(True).run(timeout=30)
    return at


def test_subtitle_present(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    body = " ".join(m.value for m in at.markdown) + " ".join(getattr(x, "value", "") for x in at.caption)
    assert "不會自動保存" in body


def test_happy_path_renders_four_steps(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    subheaders = " ".join(s.value for s in at.subheader)
    assert "Step 2" in subheaders and "Step 3" in subheaders and "Step 4" in subheaders
    assert not at.exception


def test_empty_symbol_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at, symbol="   ")
    assert any("請輸入標的代號" in e.value for e in at.error)


def test_fetch_error_mapping(monkeypatch):
    import option_chaser.service as svc
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 抓取失敗（XX）: boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at, symbol="XX")
    assert any("請稍後再試" in e.value for e in at.error)


def test_analysis_does_not_write_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    assert workspace.list_scenarios(tmp_path) == []   # 零新檔（測試鎖定）


def test_save_as_scenario_button_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    save_buttons = [b for b in at.button if b.label == "保存為劇本"]
    assert save_buttons, "expected a 保存為劇本 button after analysis"
    save_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
    scenarios = workspace.list_scenarios(tmp_path)
    assert len(scenarios) == 1
    assert scenarios[0].id == "XYZ-120-202608"


def test_save_as_scenario_duplicate_shows_link(monkeypatch, tmp_path):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    _patched(monkeypatch)
    workspace.create_scenario(tmp_path, "XYZ", "bullish", 120.0, "2026-08-01", "",
                              ("long-call",), ts="2026-07-22T00:00:00+00:00")
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert "已有同名劇本" in body
    assert not any(b.label == "保存為劇本" for b in at.button)


def test_edit_form_resubmit_triggers_new_analysis(monkeypatch):
    """Migrated from tests/test_webapp_v4.py (Task 11 Step 5): regression test
    for the ordering bug where the collapsed '✎ 修改劇本' form's submit must be
    dispatched on the SAME rerun it is clicked, even after a result already
    exists."""
    _patched(monkeypatch)
    at = AppTest.from_file(PAGE)
    at.run()
    at = _fill_and_submit(at)
    assert at.session_state["result"].request.base_params.target_price == 120.0
    new_target = 125.0
    at.number_input(key="target_price").set_value(new_target)
    submit_buttons = [b for b in at.button if b.label == "開始分析"]
    assert submit_buttons
    submit_buttons[0].set_value(True).run(timeout=30)
    assert not at.exception
    assert at.session_state["result"].request.base_params.target_price == new_target
