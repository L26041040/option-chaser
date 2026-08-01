"""Option Chaser Web GUI（Streamlit）。所有金融計算一律經 option_chaser.service。

v4 spec §4: four-step flow (chips -> single heatmap -> grouped comparison ->
advanced expanders). GUI computes NO financial formulas — every displayed
number comes from service-produced CandidateView/ScenarioVector fields
(including the completion-curve price column, `cv.completion_prices`,
precomputed by `service._v4_fields` via `scenarios._grid_price`); the few
remaining exceptions (bold-anchor detection, buffer-day copy tier, Pareto
frontier selection, SVG coordinate scaling) are pure presentation/geometry
over already-computed values, allowed per spec §4.2/§4.4/§4.5, and are called
out inline.
"""
from __future__ import annotations

import logging
from datetime import date

import streamlit as st

from option_chaser import service, store
from option_chaser.models import AnalysisParams, FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from option_chaser.timeframe import month_is_over, parse_target_month
from webapp.render import (cell_color, default_key, find_row, heatmap_html,
                           render_step2, render_step3, render_step4,
                           render_summary)

STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
DEFAULT_CHECKED = {"long-call", "bull-call-spread"}


def run_analysis(request, progress):
    return service.run(request, progress)


def _selected_key(view) -> str | None:
    if "selected_key" not in st.session_state:
        st.session_state["selected_key"] = default_key(view)
    key = st.session_state["selected_key"]
    if find_row(view, key) is None and view["default_selection"]:
        key = view["default_selection"][1]
        st.session_state["selected_key"] = key
    return key


def _scenario_form_fields():
    st.text_input("標的", key="symbol", placeholder="TLT")
    st.number_input("目標價位", key="target_price",
                    min_value=0.01, value=100.0, step=1.0)
    st.text_input("預計到達年月", key="target_month", placeholder="2028/1")
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}", value=(s in DEFAULT_CHECKED))


st.set_page_config(page_title="Option Chaser", layout="wide")
# Mobile CSS approximation (spec §4.4 visual intent, minimal deviation — see
# task-7 fix-round report for the accepted gap: rows use st.columns/buttons
# instead of one outer-overflow-x HTML table): fixed thumbnail width so the
# Step-3 thumbnail column doesn't reflow on narrow viewports, and tabular
# (monospace-width) digits on the comparison table's numeric columns so
# stacked percentage values stay vertically aligned.
st.markdown(
    "<style>"
    ".oc-thumb{display:inline-block;width:46px;overflow:hidden}"
    ".oc-num{font-variant-numeric:tabular-nums}"
    "</style>",
    unsafe_allow_html=True)
st.title("Option Chaser")
st.caption("輸入你的價格劇本，Option Chaser 會自動掃描目前的選擇權鏈，"
           "比較單腿與價差策略，找出條件式報酬率最高的候選。")

# Step 1 (spec §4.1): once a result exists, the input form collapses behind
# a chips summary line + a "✎ 修改劇本" expander. The form (and its submit
# button) MUST be instantiated before the submit-dispatch block below runs,
# so a click inside the collapsed expander is seen on the same rerun.
_result = st.session_state.get("result")
if _result is None:
    with st.form("scenario"):
        _scenario_form_fields()
        submitted = st.form_submit_button(
            "開始分析", disabled=st.session_state.get("running", False))
else:
    render_summary(store.serialize_result(_result, "", None))
    with st.expander("✎ 修改劇本", expanded=False):
        with st.form("scenario"):
            _scenario_form_fields()
            submitted = st.form_submit_button(
                "開始分析", disabled=st.session_state.get("running", False))


def _do_analysis() -> None:
    """Runs on the rerun AFTER running=True, so the form above is already
    rendered disabled while this executes (two-phase rerun pattern)."""
    request = st.session_state.pop("pending_request")
    try:
        with st.status("分析中……", expanded=True) as status:
            result = run_analysis(request, status.write)
            status.update(label="分析完成", state="complete")
        st.session_state["result"] = result
        st.session_state.pop("selected_key", None)
        st.session_state.pop("error_msg", None)
    except FetchError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = (
            "找不到此標的，請確認代號是否正確。" if "資料不足" in str(e)
            else f"目前無法取得 {request.symbol} 的市場資料，請稍後再試。")
    except ParamError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = str(e)
    except Exception:
        logging.exception("analysis failed")
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = "分析過程發生錯誤，請稍後再試。"
    finally:
        st.session_state["running"] = False


def _resolve_target_month() -> str:
    """年月輸入 → YYYY-MM。格式錯誤與「已過完的月份」都是明確錯誤，不猜測。"""
    month = parse_target_month(st.session_state.get("target_month") or "")
    if month_is_over(month, date.today()):
        raise ParamError(f"目標年月 {month.key()} 已經過完，請改填未來的年月。")
    return month.key()


if submitted and not st.session_state.get("running", False):
    sym = (st.session_state.get("symbol") or "").strip().upper()
    strategies = tuple(s for s in STRATEGY_ORDER if st.session_state.get(f"chk-{s}"))
    if not sym:
        st.error("請輸入標的代號。")
    elif not strategies:
        st.error("請至少勾選一種策略。")
    else:
        try:
            target_month = _resolve_target_month()
        except ParamError as e:
            st.error(str(e))
        else:
            base = AnalysisParams(
                target_price=float(st.session_state["target_price"]),
                target_month=target_month)
            st.session_state["pending_request"] = service.AnalysisRequest(
                symbol=sym, base_params=base, strategies=strategies)
            st.session_state["running"] = True
            st.rerun()   # next run renders the form disabled, THEN analyzes

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()       # re-enable the button and show results/errors

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])

# Step 2/3/4 (spec §4.2-4.5): render against the LATEST result in session
# state (a fresh analysis may have just replaced it above).
if "result" in st.session_state:
    _final_result = st.session_state["result"]
    _view = store.serialize_result(_final_result, "", None)
    _key = _selected_key(_view)
    render_step2(_view, _key)
    render_step3(_view, _key)
    render_step4(_view, _key)
