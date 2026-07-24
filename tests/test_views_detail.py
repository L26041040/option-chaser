"""v6 spec §3.3：獨立劇本詳頁——四步結構＋sid 不存在保護。取代 test_webapp_v4.py
剩餘的分組表格/badge/scatter/greeks 相關斷言（原針對 v5 workspace 詳頁）。"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace

PAGE = "webapp/views/detail.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-22T00:00:00+00:00"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    return tmp_path


def _mk_analyzed(ws_root, price=120.0, tdate="2026-08-01"):
    sc = workspace.create_scenario(ws_root, "XYZ", "bullish", price, tdate, "",
                                   ("long-call", "bull-call-spread"), ts=TS)
    store.save_constraints(ws_root, 100000.0)
    workspace.analyze_scenario(ws_root, sc.id, snapshot_path=FIX, ts=TS)
    return sc


def test_missing_sid_shows_error_card(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert any("找不到" in e.value or "尚未指定" in e.value for e in at.error)


def test_unknown_sid_shows_error_card(ws):
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = "NOPE-1-202601"
    at.run()
    assert not at.exception
    assert any("找不到" in e.value for e in at.error)


def test_four_step_structure_renders(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception
    subheaders = " ".join(s.value for s in at.subheader)
    body = " ".join(m.value for m in at.markdown)
    assert "Header" not in subheaders  # header 是卡片非 subheader，不強制字面比對
    assert "Step 2" in subheaders or "劇本主圖" in body
    # NOTE (brief deviation, flagged in task-11-report.md): brief's original
    # assertion was `"Step 3" in subheaders or "比較" in body` — but detail.py
    # (verbatim from the brief's own Step 3 code) renders this section via
    # `st.subheader("候選比較")`, a *subheader* element, not markdown. "比較"
    # therefore only ever lands in `subheaders`, never in `body` (which only
    # joins at.markdown). The literal brief assertion can never pass against
    # the brief's own given implementation. Checking `subheaders` (where the
    # text actually is) instead of `body` is the minimal faithful fix.
    assert "Step 3" in subheaders or "比較" in subheaders or "比較" in body
    assert "Step 4" in subheaders or "進階" in body


def test_productized_candidate_sections_do_not_repeat_step_or_comparison_headings(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception
    subheaders = [s.value for s in at.subheader]
    body = " ".join(m.value for m in at.markdown)
    assert not any("Step 2" in text for text in subheaders)
    assert "候選比較" not in subheaders
    assert "報酬情境矩陣" in body
    assert "候選比較" in body


def test_candidate_card_price_visible(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    body = " ".join(m.value for m in at.markdown)
    source = workspace.latest_result(ws, sc.id)["snapshot_ref"]["source"]
    assert "資料來源：最近有效快照" in body
    assert source in body
    assert "Breakeven" in body or "保本" in body


def test_reanalyze_button_present(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert any(b.key == "detail-reanalyze" for b in at.button)


def test_scatter_expander_and_greeks_present(ws):
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    labels = {e.label for e in at.expander}
    assert "韌性與壓力情境" in labels
    assert "報酬×韌性散點" in labels
    assert "Greeks 與流動性" in labels


def test_header_escapes_symbol_html_injection(ws):
    """detail.py 的 Header 卡直接組字串後 unsafe_allow_html=True 呈現——sc.symbol
    是使用者輸入，必須 html.escape() 才可注入，否則破壞版面或執行注入內容。

    注意：`<`/`>` 是 Windows 檔名非法字元，若經 workspace.create_scenario 產生
    （id 由 symbol 直接組成），會在 store.save_scenario 寫檔階段就先炸掉，測不到
    render 層的跳脫邏輯。改直接建構 Scenario 物件、以固定安全 id 存檔，僅讓
    symbol 欄位（JSON 內容字串，無檔名限制）帶惡意字串，單純驗證 detail.py 的
    HTML 跳脫，不糾纏 id 產生規則。"""
    from option_chaser.store import Scenario
    sc = Scenario(schema_version=1, id="INJECT-TEST-1", symbol="<script>alert(1)</script>",
                 direction="bullish", target_price=120.0, target_date="2026-08-01",
                 created_at=TS, notes="", group_id="G-INJECT", status="Active",
                 strategies=("long-call",))
    store.save_scenario(ws, sc)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = "INJECT-TEST-1"
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_v1_legacy_result_renders_without_crash(ws):
    """End-to-end proof of Task 6/7's .get()-based v1 fallback: a real result
    file written with v2 fields stripped and schema_version rolled back to 1
    must still render the full detail page (degraded, not KeyError)."""
    sc = _mk_analyzed(ws)
    path = store.latest_result_path(ws, sc.id)
    view = store.load_result(path)
    for r in view["results"]:
        for c in r["candidates"] + r["expiry_best"]:
            c.pop("natural_per_contract", None)
            c.pop("max_profit_per_contract", None)
            c.pop("cap_price", None)
    for g in view["expiry_groups"]:
        for row in g["rows"]:
            cc = row["candidate"]
            cc.pop("natural_per_contract", None)
            cc.pop("max_profit_per_contract", None)
            cc.pop("cap_price", None)
    view["schema_version"] = 1
    store.atomic_write_json(path, view)

    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert "舊版分析結果" in body


# ---------------------------------------------------------------------------
# Migrated from tests/test_webapp_v4.py (v5 workspace-detail assertions).
# See task-11-report.md ("Fix round 1") for the full per-test disposition
# rationale — summary:
#   - grouped/badge/選看 (test_grouped_table_renders,
#     test_default_selection_matches_service_and_has_no_warning,
#     test_row_button_switches_selected_key) targeted render_step3's
#     interactive session_state-based selection table. detail.py (per this
#     task's brief) deliberately replaces that with the static
#     comparison_table_html — there is no "選看" button or `selected_key`
#     session-state on this page, so those three tests have no structural
#     analog here. That interactive-selection behavior still lives on
#     webapp/views/quick.py (out of scope for this task).
#   - test_three_advanced_expanders_present's core assertions (three advanced
#     expander labels) are already covered above by
#     test_scatter_expander_and_greeks_present; its 4th label ("✎ 修改劇本")
#     is quick.py's edit-form expander, not applicable to detail.py.
#   - test_edit_form_resubmit_triggers_new_analysis is quick.py's edit-form
#     resubmit behavior; detail.py has no form, only the "重新分析" button
#     already covered by test_reanalyze_button_present.
#   - test_dollar_amounts_are_escaped and test_glossary_importable_without_streamlit
#     were removed here in fix round 1: both are now restored, page-agnostic,
#     in tests/test_render_v4_regression.py (pointed at quick.py per the plan),
#     and duplicating them here added no detail.py-specific signal — the
#     `$`-escaping of comparison_table_html itself already has a precise,
#     non-AppTest unit test in tests/test_render_cap.py (asserts "\\$120"/
#     "\\$80" directly against comparison_table_html()'s output).
#   - test_abbr_titles_come_from_glossary is KEPT (adapted): unlike the
#     restored test_render_v4_regression.py version (which asserts
#     render_step3's grouped-table terms 劇本報酬/情境最壞/不漲保留率 — a
#     function detail.py never calls), this version asserts render_step4's
#     Greeks/liquidity-expander terms (Delta/Vega/成交摩擦). render_step4 is
#     used verbatim by both quick.py and detail.py, but no other test file
#     asserts its glossary-abbr wiring, so this is genuinely independent
#     coverage, not a duplicate.
# ---------------------------------------------------------------------------

def test_abbr_titles_come_from_glossary(ws):
    r"""Migrated from test_webapp_v4.py::test_abbr_titles_come_from_glossary,
    adapted to the terms detail.py actually renders via render.abbr(): the
    original terms (劇本報酬/情境最壞/不漲保留率) are only abbr()-wrapped inside
    render_step3's grouped table (not used by detail.py — see note above).
    detail.py calls render_step4 verbatim, whose Greeks/liquidity expander
    unconditionally abbr()-wraps Delta/Vega/成交摩擦, so those are the
    detail-page-relevant glossary-tooltip terms to assert on.

    Delta's glossary text contains a literal '$1' — the Greeks expander's
    whole markdown string passes through render.esc() before rendering
    (render.py's `$` -> `\$` LaTeX-guard convention), so the rendered
    abbr title is the *escaped* text, not the raw GLOSSARY value. Compare
    against esc(GLOSSARY[term]) to match what's actually on the page."""
    from option_chaser.glossary import GLOSSARY
    from webapp.render import esc
    sc = _mk_analyzed(ws)
    at = AppTest.from_file(PAGE)
    at.query_params["sid"] = sc.id
    at.run()
    body = " ".join(m.value for m in at.markdown)
    for term in ("Delta", "Vega", "成交摩擦"):
        assert f'title="{esc(GLOSSARY[term])}"' in body
