# webapp/views/workspace.py
"""v6 spec §3.2/§3.5：劇本工作區——Artifact 風卡片牆＋⋯管理彈出層＋群組里程碑軌。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from webapp.components import candidate_card, quality_badge, scenario_card, status_pill
from webapp.status import quality_tone
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
RELATION_LABELS = {"milestone-path": "里程碑路徑", "independent": "獨立",
                   "exclusive": "互斥", "undefined": "暫不定義"}
PROPOSED_LABELS = {"milestone-path": "里程碑路徑", "review-needed": "需檢視",
                   "exclusive-candidate": "互斥候選"}

inject()
st.title("劇本工作區")


def _summary_of(sid: str):
    return workspace.latest_result(WS_ROOT, sid)


def _analyze_with_status(fn, *args, **kw):
    try:
        with st.status("分析中……", expanded=True) as status:
            out = fn(*args, progress=status.write, **kw)
            status.update(label="分析完成", state="complete")
        return out
    except (FetchError, ParamError) as e:
        st.error(str(e))
    except Exception:
        st.error("分析過程發生錯誤，請稍後再試。")
    return None


# ---------- 設定 ----------
constraints = store.load_constraints(WS_ROOT)
with st.popover("⚙ 設定"):
    cur = constraints["total_capital"]
    cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                             value=float(cur or 0.0), step=1000.0, key="ws-capital")
    if st.button("儲存設定", key="ws-save-capital"):
        store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
        st.rerun()

# ---------- 建立劇本 ----------
with st.popover("＋ 建立劇本"):
    st.text_input("標的", key="ws-new-symbol", placeholder="TLT")
    st.number_input("目標價位", key="ws-new-price", min_value=0.01, value=100.0, step=1.0)
    sym = (st.session_state.get("ws-new-symbol") or "").strip().upper()
    inferred = (workspace.default_direction(sym, float(st.session_state.get("ws-new-price", 100.0)))
               if sym else None)
    options = ("bullish", "bearish") if inferred else ("", "bullish", "bearish")
    dir_labels = {"": "（請選擇）", "bullish": "看漲", "bearish": "看跌"}
    idx = options.index(inferred) if inferred else 0
    direction = st.selectbox("方向", options, index=idx, format_func=lambda d: dir_labels[d],
                             key="ws-new-direction")
    if direction and st.session_state.get("ws-new-dir-prev") != direction:
        st.session_state["ws-new-dir-prev"] = direction
        defaults = ({"long-call", "bull-call-spread"} if direction == "bullish"
                    else {"long-put", "bear-put-spread"})
        for s in STRATEGY_ORDER:
            st.session_state[f"ws-new-chk-{s}"] = s in defaults
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"ws-new-chk-{s}")
    st.date_input("目標日", key="ws-new-date", value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    st.text_input("備註", key="ws-new-notes")
    if st.button("建立", key="ws-new-create"):
        strategies = tuple(s for s in STRATEGY_ORDER if st.session_state.get(f"ws-new-chk-{s}"))
        if not sym:
            st.error("請輸入標的代號。")
        elif not direction:
            st.error("請選擇方向（此標的尚無 snapshot，無法自動推測）。")
        elif not strategies:
            st.error("請至少勾選一種策略。")
        else:
            workspace.create_scenario(
                WS_ROOT, symbol=sym, direction=direction,
                target_price=float(st.session_state["ws-new-price"]),
                target_date=st.session_state["ws-new-date"].isoformat(),
                notes=st.session_state["ws-new-notes"], strategies=strategies)
            st.rerun()

# ---------- 載入 ----------
scenarios = workspace.list_scenarios(WS_ROOT)
by_id = {sc.id: sc for sc in scenarios}
groups = workspace.load_groups(WS_ROOT)

# ---------- 卡片牆 ----------
st.subheader("劇本清單")
if len(scenarios) > 6:
    st.warning(f"目前有 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
if not scenarios:
    st.markdown("尚無劇本。用上方「＋ 建立劇本」開始。")
for sc in scenarios:
    summary = _summary_of(sc.id)
    st.markdown(scenario_card(
        {"id": sc.id, "symbol": sc.symbol, "direction": sc.direction,
         "target_price": sc.target_price, "target_date": sc.target_date,
         "status": sc.status, "group_id": sc.group_id, "notes": sc.notes},
        summary), unsafe_allow_html=True)
    cols = st.columns([1, 1, 1])
    with cols[0]:
        if st.button("分析", key=f"ws-an-{sc.id}"):
            if _analyze_with_status(workspace.analyze_scenario, WS_ROOT, sc.id) is not None:
                st.rerun()
    with cols[1]:
        if summary is not None and st.button("詳頁", key=f"ws-det-{sc.id}"):
            # st.switch_page 若不帶 query_params 會清空既有 query params
            # （官方文件："Query parameters to apply when navigating"——不傳即不帶），
            # 不可先 st.query_params["sid"]=... 再呼叫無參數版本，sid 會遺失。
            st.switch_page("views/detail.py", query_params={"sid": sc.id})
    with cols[2]:
        with st.popover("⋯ 管理"):
            if sc.status == "Active":
                st.text_input("原因", key=f"ws-reason-{sc.id}", placeholder="標記原因（必填）")
                reason = (st.session_state.get(f"ws-reason-{sc.id}") or "").strip()
                if st.button("標記達成", key=f"ws-reach-{sc.id}"):
                    if reason:
                        workspace.set_status(WS_ROOT, sc.id, "Reached", reason)
                        st.rerun()
                    else:
                        st.error("請填原因。")
                if st.button("標記失效", key=f"ws-inv-{sc.id}"):
                    if reason:
                        workspace.set_status(WS_ROOT, sc.id, "Invalidated", reason)
                        st.rerun()
                    else:
                        st.error("請填原因。")
            st.checkbox("確認刪除", key=f"ws-delok-{sc.id}")
            if st.button("刪除", key=f"ws-del-{sc.id}"):
                if st.session_state.get(f"ws-delok-{sc.id}"):
                    workspace.delete_scenario(WS_ROOT, sc.id)
                    st.rerun()
                else:
                    st.error("請先勾選「確認刪除」。")

# ---------- 群組里程碑軌 ----------
st.subheader("劇本群組")
for g in groups["groups"]:
    members = [by_id[m] for m in g["members"] if m in by_id]
    if not members:
        continue
    views_by_id = {m: _summary_of(m) for m in g["members"] if _summary_of(m) is not None}
    from webapp.components import milestone_rail
    st.markdown(milestone_rail(g, by_id, views_by_id), unsafe_allow_html=True)
    for i, rel in enumerate(g["relations"]):
        a_id, b_id = rel["pair"]
        st.markdown(
            f"{a_id} ↔ {b_id}｜提案：{PROPOSED_LABELS[rel['proposed']]}｜"
            f"已確認：{RELATION_LABELS[rel['confirmed']]}")
        ccols = st.columns([2, 1, 6])
        with ccols[0]:
            choice = st.selectbox("確認關係", ("milestone-path", "independent", "exclusive", "undefined"),
                                  format_func=lambda c: RELATION_LABELS[c], key=f"ws-rel-{g['id']}-{i}")
        with ccols[1]:
            if st.button("確認", key=f"ws-rel-btn-{g['id']}-{i}"):
                workspace.confirm_relation(WS_ROOT, g["id"], (a_id, b_id), choice)
                st.rerun()
        prev, nxt = by_id.get(a_id), by_id.get(b_id)
        if (prev is not None and nxt is not None and prev.status == "Reached"
                and rel["confirmed"] == "milestone-path"):
            if st.button(f"重新分析 {nxt.id}", key=f"ws-rean-{nxt.id}"):
                if _analyze_with_status(workspace.analyze_scenario, WS_ROOT, nxt.id) is not None:
                    st.rerun()
    if st.button("群組分析", key=f"ws-gan-{g['id']}"):
        if _analyze_with_status(workspace.analyze_group, WS_ROOT, g["id"]) is not None:
            st.rerun()
