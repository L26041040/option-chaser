# webapp/pages/0_劇本工作區.py
"""v5 spec §5: 多劇本工作區（清單/建立/群組/詳頁/設定）。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from option_chaser.timeframe import parse_target_month
from webapp.render import (esc, money, pct, render_step2, render_step3,
                           render_step4, render_summary)

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STATUS_BADGE = {"Active": "🟢 Active", "Reached": "🏁 Reached",
                "Expired": "⌛ Expired", "Invalidated": "❌ Invalidated"}
RELATION_LABELS = {"milestone-path": "里程碑路徑", "independent": "獨立",
                   "exclusive": "互斥", "undefined": "暫不定義"}
PROPOSED_LABELS = {"milestone-path": "里程碑路徑", "review-needed": "需檢視",
                   "exclusive-candidate": "互斥候選"}

st.set_page_config(page_title="劇本工作區", layout="wide")
st.title("劇本工作區")


def _summary_of(sid: str):
    view = workspace.latest_result(WS_ROOT, sid)
    if view is None or not view["default_selection"]:
        return None
    key = view["default_selection"][1]
    for g in view["expiry_groups"]:
        for row in g["rows"]:
            if row["candidate"]["candidate_key"] == key:
                return view, row
    return None


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


# ---------- 設定區 ----------
constraints = store.load_constraints(WS_ROOT)
with st.expander("⚙ 設定", expanded=False):
    cur = constraints["total_capital"]
    cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                             value=float(cur or 0.0), step=1000.0,
                             key="ws-capital")
    if st.button("儲存設定", key="ws-save-capital"):
        store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
        st.rerun()

# ---------- 建立表單 ----------
# T4（#18）：只問標的／目標價／目標年月三欄。方向與策略不曝露於 UI，
# 帶入 MVP 預設（bullish + bull-call-spread）；create 簽章保留全部參數。
with st.expander("＋ 建立劇本", expanded=False):
    st.text_input("標的", key="ws-new-symbol", placeholder="TLT")
    st.number_input("目標價位", key="ws-new-price", min_value=0.01,
                    value=100.0, step=1.0)
    st.text_input("目標年月", key="ws-new-month", placeholder="2028/1")
    if st.button("建立", key="ws-new-create"):
        sym = (st.session_state.get("ws-new-symbol") or "").strip().upper()
        if not sym:
            st.error("請輸入標的代號。")
        else:
            # 格式錯誤與「已過完的月份」都由 ParamError 表達（後者在 create 裡把關）
            try:
                month = parse_target_month(
                    st.session_state.get("ws-new-month") or "")
                workspace.create_scenario(
                    WS_ROOT, symbol=sym, direction="bullish",
                    target_price=float(st.session_state["ws-new-price"]),
                    target_month=month.key(),
                    notes="",
                    strategies=("bull-call-spread",))
            except ParamError as e:
                st.error(str(e))
            else:
                st.rerun()

# ---------- 載入（含對帳） ----------
scenarios = workspace.list_scenarios(WS_ROOT)
by_id = {sc.id: sc for sc in scenarios}
groups = workspace.load_groups(WS_ROOT)

# ---------- 清單區 ----------
st.subheader("劇本清單")
if len(scenarios) > 6:
    st.warning(f"目前有 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
if not scenarios:
    st.info("尚無劇本。用上方「＋ 建立劇本」開始。")
for sc in scenarios:
    cols = st.columns([1.0, 0.7, 0.8, 0.9, 1.0, 0.8, 0.9, 2.2, 1.8])
    with cols[0]:
        st.markdown(f"**{sc.symbol}**")
    with cols[1]:
        st.markdown("看漲" if sc.direction == "bullish" else "看跌")
    with cols[2]:
        st.markdown(esc(f"${money(sc.target_price)}"))
    with cols[3]:
        st.markdown(sc.target_month)
    with cols[4]:
        st.markdown(STATUS_BADGE[sc.status])
    with cols[5]:
        st.markdown(sc.group_id)
    summary = _summary_of(sc.id)
    with cols[6]:
        if summary is not None:
            p = summary[1]["candidate"]["pct_of_capital"]
            st.markdown(f"佔本金 {pct(p)}" if p is not None else "—")
        else:
            st.markdown("—")
    with cols[7]:
        if summary is not None:
            row = summary[1]
            cand = row["candidate"]
            label = (f"買 {cand['legs'][0]['strike']:g} / "
                     f"賣 {cand['legs'][1]['strike']:g}"
                     if len(cand["legs"]) == 2
                     else f"K={cand['legs'][0]['strike']:g}")
            st.markdown(esc(
                f"{STRATEGY_LABELS[row['strategy']]} {label}｜"
                f"劇本報酬 {pct(cand['baseline_return'])}｜"
                f"情境最壞 {pct(cand['scenario_vector']['worst_return'])}"))
        else:
            st.markdown("尚未分析")
    with cols[8]:
        if st.button("分析", key=f"ws-an-{sc.id}"):
            # 僅成功才 rerun——失敗時 st.error 留在本次渲染，不被沖掉
            if _analyze_with_status(workspace.analyze_scenario, WS_ROOT,
                                    sc.id) is not None:
                st.rerun()
        if summary is not None and st.button("詳頁", key=f"ws-det-{sc.id}"):
            st.session_state["ws-detail"] = sc.id
            st.rerun()
    if sc.status == "Active":
        rcols = st.columns([3.0, 1.2, 1.2, 4.0])
        with rcols[0]:
            st.text_input("原因", key=f"ws-reason-{sc.id}",
                          placeholder="標記原因（必填）")
        reason = (st.session_state.get(f"ws-reason-{sc.id}") or "").strip()
        with rcols[1]:
            if st.button("標記達成", key=f"ws-reach-{sc.id}"):
                if reason:
                    workspace.set_status(WS_ROOT, sc.id, "Reached", reason)
                    st.rerun()
                else:
                    st.error("請填原因。")
        with rcols[2]:
            if st.button("標記失效", key=f"ws-inv-{sc.id}"):
                if reason:
                    workspace.set_status(WS_ROOT, sc.id, "Invalidated", reason)
                    st.rerun()
                else:
                    st.error("請填原因。")
    dcols = st.columns([1.6, 1.0, 7.0])
    with dcols[0]:
        st.checkbox("確認刪除", key=f"ws-delok-{sc.id}")
    with dcols[1]:
        if st.button("刪除", key=f"ws-del-{sc.id}"):
            if st.session_state.get(f"ws-delok-{sc.id}"):
                workspace.delete_scenario(WS_ROOT, sc.id)
                st.session_state.pop("ws-detail", None)
                st.rerun()
            else:
                st.error("請先勾選「確認刪除」。")
    st.divider()

# ---------- 群組區 ----------
st.subheader("劇本群組")
for g in groups["groups"]:
    members = [by_id[m] for m in g["members"] if m in by_id]
    if not members:
        continue
    st.markdown(f"**{g['id']}**（{len(members)} 個里程碑）")
    for sc in members:
        summary = _summary_of(sc.id)
        if summary is not None:
            cand = summary[1]["candidate"]
            line = (f"{sc.target_month} ${money(sc.target_price)}｜"
                    f"{STATUS_BADGE[sc.status]}｜"
                    f"劇本報酬 {pct(cand['baseline_return'])}｜"
                    f"情境最壞 {pct(cand['scenario_vector']['worst_return'])}｜"
                    f"緩衝 +{cand['buffer_days']} 天")
        else:
            line = (f"{sc.target_month} ${money(sc.target_price)}｜"
                    f"{STATUS_BADGE[sc.status]}｜尚未分析")
        st.markdown(esc(line))
    for i, rel in enumerate(g["relations"]):
        a_id, b_id = rel["pair"]
        st.markdown(esc(
            f"{a_id} ↔ {b_id}｜提案：{PROPOSED_LABELS[rel['proposed']]}｜"
            f"已確認：{RELATION_LABELS[rel['confirmed']]}"))
        ccols = st.columns([2.4, 1.0, 6.0])
        with ccols[0]:
            choice = st.selectbox(
                "確認關係", ("milestone-path", "independent", "exclusive",
                             "undefined"),
                format_func=lambda c: RELATION_LABELS[c],
                key=f"ws-rel-{g['id']}-{i}")
        with ccols[1]:
            if st.button("確認", key=f"ws-rel-btn-{g['id']}-{i}"):
                workspace.confirm_relation(WS_ROOT, g["id"], (a_id, b_id),
                                           choice)
                st.rerun()
        # spec §5.1 兩條件：前一里程碑 Reached 且 confirmed==milestone-path
        prev, nxt = by_id.get(a_id), by_id.get(b_id)
        if (prev is not None and nxt is not None
                and prev.status == "Reached"
                and rel["confirmed"] == "milestone-path"):
            if st.button(f"重新分析 {nxt.id}", key=f"ws-rean-{nxt.id}"):
                if _analyze_with_status(workspace.analyze_scenario, WS_ROOT,
                                        nxt.id) is not None:
                    st.rerun()
    if st.button("群組分析", key=f"ws-gan-{g['id']}"):
        if _analyze_with_status(workspace.analyze_group, WS_ROOT,
                                g["id"]) is not None:
            st.rerun()
    st.divider()

# ---------- 詳頁 ----------
detail_id = st.session_state.get("ws-detail")
if detail_id and detail_id in by_id:
    view = workspace.latest_result(WS_ROOT, detail_id)
    if view is not None:
        st.subheader(f"詳頁：{detail_id}")
        if st.button("關閉詳頁", key="ws-close-detail"):
            st.session_state.pop("ws-detail", None)
            st.rerun()
        render_summary(view)
        key = st.session_state.get("ws-selected-key")
        if key is None or all(
                row["candidate"]["candidate_key"] != key
                for gg in view["expiry_groups"] for row in gg["rows"]):
            key = (view["default_selection"][1]
                   if view["default_selection"] else None)
            st.session_state["ws-selected-key"] = key
        render_step2(view, key)
        render_step3(view, key, state_key="ws-selected-key")
        render_step4(view, key)
