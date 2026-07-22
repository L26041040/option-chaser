"""v4 spec §4/§7.7: four-step GUI (glossary, grouped comparison, thumbnails,
badges, advanced expanders). Follows the existing tests/test_webapp.py
AppTest bootstrap pattern (subprocess-isolated streamlit runtime)."""
from datetime import date
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import service
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
SYMBOL = "XYZ"
TARGET_PRICE = 120.0
TARGET_DATE = date(2026, 8, 1)


def _patched(monkeypatch):
    real_offline = service.run_offline
    monkeypatch.setattr(
        service, "run",
        lambda req, progress=None: real_offline(req, FIX, progress))


def _fill_and_submit(at, checks=("long-call",)):
    at.text_input(key="symbol").set_value(SYMBOL)
    at.number_input(key="target_price").set_value(TARGET_PRICE)
    at.date_input(key="target_date").set_value(TARGET_DATE)
    for s in ("long-call", "bull-call-spread", "long-put", "bear-put-spread"):
        at.checkbox(key=f"chk-{s}").set_value(s in checks)
    at.run()
    at.button[0].set_value(True).run(timeout=30)
    return at


def _expected_result():
    return service.run_offline(
        service.AnalysisRequest(
            symbol=SYMBOL,
            base_params=AnalysisParams(strategy="long-call",
                                       target_price=TARGET_PRICE,
                                       target_date=TARGET_DATE.isoformat(),
                                       min_return=0.0),
            strategies=("long-call",)),
        FIX)


def test_grouped_table_renders(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert not at.exception
    # nearest expiry is always kept by the sampler (spec §3.2)
    assert "2026-08-07 到期" in body
    assert "緩衝" in body


def test_default_selection_matches_service_and_has_no_warning(monkeypatch):
    _patched(monkeypatch)
    expected = _expected_result()
    assert expected.default_selection is not None
    expected_key = expected.default_selection[1]
    expected_row = next(
        row for g in expected.expiry_groups for row in g.rows
        if service.candidate_key(row.candidate) == expected_key)
    assert not expected_row.candidate.quote_warning

    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    assert at.session_state["selected_key"] == expected_key


def test_row_button_switches_selected_key(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    before = at.session_state["selected_key"]

    other = None
    for b in at.button:
        if b.key and b.key.startswith("sel-") and b.key != f"sel-{before}":
            other = b
            break
    assert other is not None, "expected at least two selectable candidate rows"

    other.set_value(True).run(timeout=30)
    after = at.session_state["selected_key"]
    assert after != before
    assert other.key == f"sel-{after}"


def test_three_advanced_expanders_present(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    labels = {e.label for e in at.expander}
    assert "韌性與壓力情境" in labels
    assert "報酬×韌性散點" in labels
    assert "Greeks 與流動性" in labels
    assert "✎ 修改劇本" in labels


def test_dollar_amounts_are_escaped(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert "\\$" in body
    assert not at.exception


def test_abbr_titles_come_from_glossary(monkeypatch):
    from option_chaser.glossary import GLOSSARY
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    for term in ("劇本報酬", "情境最壞", "不漲保留率"):
        assert f'title="{GLOSSARY[term]}"' in body


def test_edit_form_resubmit_triggers_new_analysis(monkeypatch):
    """Regression test for the ordering bug (fixed in this branch): the
    collapsed '✎ 修改劇本' form's submit must be dispatched on the SAME rerun
    it is clicked, even after a result already exists (i.e. the form/button
    live inside the `else` branch + `st.expander`, not some later-rendered
    path the dispatch-check block runs before)."""
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    assert at.session_state["result"].request.base_params.target_price == (
        TARGET_PRICE)

    new_target = 125.0
    at.number_input(key="target_price").set_value(new_target)
    # The edit-form submit button is `st.form_submit_button("開始分析", ...)`
    # inside the "✎ 修改劇本" expander — it carries no explicit `key`, so it
    # is located by label via `at.button` (which lists both `st.button` and
    # `st.form_submit_button` widgets per streamlit.testing.v1 docs).
    submit_buttons = [b for b in at.button if b.label == "開始分析"]
    assert submit_buttons, (
        "expected the edit-form's submit button to still be reachable "
        "after a result exists")
    submit_buttons[0].set_value(True).run(timeout=30)

    assert not at.exception
    result = at.session_state["result"]
    assert result.request.base_params.target_price == new_target


def test_glossary_importable_without_streamlit():
    src = Path("option_chaser/glossary.py").read_text(encoding="utf-8")
    assert "streamlit" not in src

    import option_chaser.glossary as g
    assert len(g.GLOSSARY) >= 16
    required = ["劇本報酬", "情境最壞", "Natural 成交報酬", "成交摩擦",
                "完成度門檻", "不漲保留率", "到期緩衝", "保本價", "Mid",
                "Natural", "BCS", "BPS", "Delta", "Theta", "Vega", "IV"]
    for term in required:
        assert term in g.GLOSSARY
