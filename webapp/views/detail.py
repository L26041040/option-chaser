"""v6 spec §3.3：劇本詳頁——獨立路由（st.Page visibility="hidden"），
以 st.query_params["sid"] 指定劇本。"""
from __future__ import annotations

import html
import os
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from webapp.components import candidate_card, quality_badge
from webapp.render import comparison_table_html, esc, render_step2, render_step3, render_step4
from webapp.status import derive_result_status, quality_tone
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))

inject()

sid = st.query_params.get("sid")
if not sid:
    st.error("尚未指定劇本，請從劇本工作區點擊「詳頁」進入。")
    st.stop()

try:
    sc = store.load_scenario(store.scenario_path(WS_ROOT, sid))
except FileNotFoundError:
    st.error(f"找不到劇本 `{sid}`。")
    st.stop()

view = workspace.latest_result(WS_ROOT, sid)
st.title(f"詳頁：{sc.symbol}")

# ---------- Header ----------
# sc.symbol 為使用者輸入，經 unsafe_allow_html=True 呈現前必須 html.escape()；
# 含 $ 金額的整段組字串在 return/呼叫前統一經 render.esc() 處理（既有紅線，見
# components.py／comparison_table_html 同一慣例）。
_safe_symbol = html.escape(sc.symbol, quote=True)
header_lines = [f"**{_safe_symbol}** ｜ 目標 ${sc.target_price:g} ｜ {sc.target_date}"]
if view is not None:
    header_lines.append(f"現價 ${view['meta']['spot']:.2f} ｜ 資料時間 {view['snapshot_ref']['fetched_at']} "
                        + quality_badge(quality_tone(view, workspace.ny_today())))
    header_lines.append(
        "資料來源：最近有效快照"
        f"（{html.escape(str(view['snapshot_ref']['source']), quote=True)}，"
        f"{html.escape(str(view['snapshot_ref']['fetched_at']).split('T', 1)[0], quote=True)}）"
    )
st.markdown(esc("<br>".join(header_lines)), unsafe_allow_html=True)
if st.button("重新分析", key="detail-reanalyze"):
    try:
        with st.status("分析中……", expanded=True) as status:
            workspace.analyze_scenario(WS_ROOT, sid, progress=status.write)
            status.update(label="分析完成", state="complete")
        st.rerun()
    except (FetchError, ParamError) as e:
        st.error(str(e))
    except Exception:
        st.error("分析過程發生錯誤，請稍後再試。")

if view is None:
    st.markdown(derive_result_status(view))
    st.stop()

if view["data_quality"]["all_quotes_filtered"]:
    from webapp.status import INSUFFICIENT_QUOTE_MESSAGE
    st.warning(INSUFFICIENT_QUOTE_MESSAGE)
    with st.expander("查看過濾原因"):
        for r in view["results"]:
            for stage in r["filter_stages"]:
                st.markdown(f"{r['strategy']}／{stage['label']}：移除 {stage['removed']}")

key = view["default_selection"][1] if view["default_selection"] else None
if key is not None:
    cand = next(row["candidate"] for g in view["expiry_groups"] for row in g["rows"]
               if row["candidate"]["candidate_key"] == key)
    strategy = next(row["strategy"] for g in view["expiry_groups"] for row in g["rows"]
                    if row["candidate"]["candidate_key"] == key)
    st.markdown(candidate_card(cand, strategy), unsafe_allow_html=True)

render_step2(view, key)
st.markdown(comparison_table_html(view), unsafe_allow_html=True)
render_step4(view, key)
