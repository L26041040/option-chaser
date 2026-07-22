"""v6 spec §1.2/§3.4：快速試算——一次性分析，結果不會自動保存。
輸入表單、渲染邏輯與 v5 app.py 完全沿用；新增副標與「保存為劇本」。"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from option_chaser import service, store, workspace
from option_chaser.models import AnalysisParams, FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from webapp.render import (cell_color, default_key, find_row, heatmap_html,
                           render_step2, render_step3, render_step4,
                           render_summary)
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
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
    st.date_input("預計到達時間", key="target_date",
                  value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}", value=(s in DEFAULT_CHECKED))


inject()
st.title("快速試算")
st.caption("一次性分析，結果不會自動保存。")

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


if submitted and not st.session_state.get("running", False):
    sym = (st.session_state.get("symbol") or "").strip().upper()
    strategies = tuple(s for s in STRATEGY_ORDER if st.session_state.get(f"chk-{s}"))
    if not sym:
        st.error("請輸入標的代號。")
    elif not strategies:
        st.error("請至少勾選一種策略。")
    else:
        base = AnalysisParams(target_price=float(st.session_state["target_price"]),
                              target_date=st.session_state["target_date"].isoformat())
        st.session_state["pending_request"] = service.AnalysisRequest(
            symbol=sym, base_params=base, strategies=strategies)
        st.session_state["running"] = True
        st.rerun()

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])

if "result" in st.session_state:
    _final_result = st.session_state["result"]
    _view = store.serialize_result(_final_result, "", None)
    _key = _selected_key(_view)
    render_step2(_view, _key)
    render_step3(_view, _key)
    render_step4(_view, _key)

    # v6 spec §1.2: 保存為劇本
    _base = _final_result.request.base_params
    _existing = workspace.scenario_exists(
        WS_ROOT, _final_result.request.symbol, _base.target_price, _base.target_date)
    if _existing is not None:
        st.markdown(f"已有同名劇本：`{_existing}`，前往劇本工作區查看。")
    else:
        if st.button("保存為劇本", key="save-as-scenario"):
            sc, _ = workspace.adopt_result(WS_ROOT, _final_result)
            st.success(f"已保存為劇本 `{sc.id}`，前往劇本工作區查看。")
