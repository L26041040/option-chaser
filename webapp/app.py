# webapp/app.py
"""Option Chaser 單一主畫面（Streamlit 入口，`streamlit run webapp/app.py`）。

QA1-01（#28）：拿掉「app／劇本工作區／說明」三分頁疊床架屋——開站直接
落地劇本工作區，不存在與它平行的快速分析入口，「說明」頁一併刪除
（2026-08-02 需求方裁示：不併入、不降為次要入口）。本檔即原本的
`webapp/pages/0_劇本工作區.py`，搬到入口位置後不再有 `pages/` 目錄。

v5 spec §5 ＋ T5（#19）: 桌面 20/80 兩欄工作區。＋ T7（#21）: 自動／手動刷新。
＋ T8（#22）: 左側清單依 `workspace.sort_cards()` 依最新收益率重排。
＋ T10（#24）: 詳細頁兩層結構——第一層沿用既有 `render_step3`（各期第 1
名＋Heatmap 縮圖），第二層新增 `render_expiry_top10`（單期 Top 10，預設
baseline 期，見附錄A8.5）。切換到期日／點選候選皆純 UI 互動，不觸發 API。
＋ T11（#25）: 選中 Spread 後，Step 4 進階區新增「Spread 歷史」——依身份鍵
跨該劇本全部歷史快照聚合（`workspace.spread_history`），唯讀查詢。

左 20%：劇本卡片清單（每張卡恰五項＋一個燈號位置）與清單編輯工具；
右 80%：設定、建立表單、被選中劇本的詳細頁。
窄螢幕由 Streamlit 自然堆疊成上下兩段，三件核心事（瀏覽／建立／進詳頁）
在窄 viewport 下都還在（附錄 A10.5）。

群組區自首頁移除（附錄 A8.6）——`store.rebuild_groups`／
`workspace.analyze_group` 等底層邏輯原封不動，只是不再於此頁曝露。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。

T7：開站首次載入自動刷新所有未過期劇本（同一 session 只此一次，靠
`AUTO_REFRESH_KEY` 旗標把關）；左側清單旁的刷新鈕不受此限制，隨時可再打。
建立劇本立即觸發該劇本首次刷新。同標的多劇本各自獨立呼叫
`workspace.analyze_scenario`（各自 fetch，不共用 snapshot——附錄 A8.9），
單一劇本失敗不擋其他。原子性由 `workspace.analyze_scenario`／
`store.save_result` 既有次序保證（失敗即提前 return，成功才落盤＋補事件），
本頁不需另外處理。

效能觀察（issue #21 AC，僅記錄不設門檻）：3 個劇本、離線重放同一份
snapshot fixture、序列刷新，總耗時約 29ms（本機量測，計算部分；不含
真實網路延遲——沙箱環境無法連外抓真實報價）。多劇本序列刷新目前無並行化，
劇本數量顯著增加時應重新量測。
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.timeframe import parse_target_month
from webapp.render import (baseline_key, esc, find_row, money, pct,
                           render_expiry_top10, return_md, render_step2,
                           render_step3, render_step4, render_summary)

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))
STATUS_BADGE = {"Active": "🟢 Active", "Reached": "🏁 Reached",
                "Expired": "⌛ Expired", "Invalidated": "❌ Invalidated"}
# 卡片上的單一燈號位置（需求六／T6）。
SIGNAL_ICON = {workspace.SIGNAL_GREEN: "🟢", workspace.SIGNAL_YELLOW: "🟡",
              workspace.SIGNAL_RED: "🔴", workspace.SIGNAL_UNKNOWN: "⚪"}
# session 內「這張劇本最近一次刷新是否為關鍵資料失敗」——只有 FetchError
# （標的價格／到期日 option chain 取得失敗）才算；ParamError 等其他例外
# 不代表關鍵資料失敗（附錄 A12），不動這個旗標。
# 已知限制：這個旗標只活在 st.session_state，跨瀏覽器分頁／應用重啟不會
# 保留——重開一份全新 session 時，剛發生過的關鍵資料失敗會被忘記，卡片
# 改顯示綠燈。T7 評估後維持現狀：新 session 本來就會自動刷新一次，屆時
# 若關鍵資料仍取不到，旗標會在那次刷新中重新被設起來。
_FAILURE_KEY = "ws-critical-failure"
# T7（需求七）：同一 session 只在首次載入時自動刷新一次；之後的一般互動
# （切頁、點卡片、切到期日、展開）一律不得再次觸發 API。
AUTO_REFRESH_KEY = "ws-auto-refreshed"

st.set_page_config(page_title="Option Chaser", layout="wide")
st.title("Option Chaser")


def _mark_refresh(sid: str, *, critical_failure: bool) -> None:
    st.session_state.setdefault(_FAILURE_KEY, {})[sid] = critical_failure


def _classify_refresh_error(exc: Exception) -> tuple[bool, str]:
    """統一例外分類（附錄 A12），供單一分析與批次刷新共用。

    `FetchError`＝關鍵資料（標的價格／到期日 option chain）取得失敗，
    是唯一會標記劇本級失敗（黃燈）的例外；`ParamError` 與其他例外只是
    帶出訊息，不影響燈號。
    """
    if isinstance(exc, FetchError):
        return True, str(exc)
    if isinstance(exc, ParamError):
        return False, str(exc)
    return False, "分析過程發生錯誤，請稍後再試。"


def _analyze_with_status(sid: str, fn, *args, **kw):
    try:
        with st.status("分析中……", expanded=True) as status:
            out = fn(*args, progress=status.write, **kw)
            status.update(label="分析完成", state="complete")
        _mark_refresh(sid, critical_failure=False)
        return out
    except Exception as e:
        critical, message = _classify_refresh_error(e)
        _mark_refresh(sid, critical_failure=critical)
        st.error(message)
        return None


def _refresh_all(sids: list[str], *, label: str) -> None:
    """依序刷新每個劇本；單一失敗不擋其他（需求七：刷新單位是劇本）。

    每個 sid 各自呼叫一次 `analyze_scenario`（各自 fetch，附錄 A8.9），
    例外經 `_classify_refresh_error` 分類後就地記錄，繼續下一個，不中斷
    整個批次；批次結束後由呼叫端決定是否 rerun 以反映最新結果。
    """
    if not sids:
        return
    with st.status(label, expanded=False) as status:
        for sid in sids:
            try:
                workspace.analyze_scenario(WS_ROOT, sid, progress=status.write)
                _mark_refresh(sid, critical_failure=False)
            except Exception as e:
                critical, message = _classify_refresh_error(e)
                _mark_refresh(sid, critical_failure=critical)
                status.write(f"{sid}：{message}")
        status.update(label="刷新完成", state="complete")


# ---------- 載入（含對帳） ----------
scenarios = workspace.list_scenarios(WS_ROOT)
by_id = {sc.id: sc for sc in scenarios}
refreshable = [sc.id for sc in scenarios if sc.status != "Expired"]

if not st.session_state.get(AUTO_REFRESH_KEY):
    st.session_state[AUTO_REFRESH_KEY] = True
    _refresh_all(refreshable, label="自動刷新未過期劇本……")

views = {sc.id: workspace.latest_result(WS_ROOT, sc.id) for sc in scenarios}
failure_flags = st.session_state.setdefault(_FAILURE_KEY, {})
cards = workspace.sort_cards(
    [workspace.card_of(sc, views[sc.id],
                       critical_failure=failure_flags.get(sc.id, False))
     for sc in scenarios])

# 選中的劇本：預設第一張卡，右欄因此一載入就有東西可看。
selected = st.session_state.get("ws-detail")
if selected not in by_id:
    selected = scenarios[0].id if scenarios else None
    st.session_state["ws-detail"] = selected


def _render_card(card) -> None:
    """恰五項：標的／目標價／目標年月／最高收益率／一個燈號（需求五）。

    整張卡片就是進詳細頁的按鈕；腿別、成本、佔本金等技術數字一律留給右欄。
    """
    with st.container(border=True):
        # 選中以「▸」標示，不用 primary 按鈕——那是紅色的，會和「負數＝紅」
        # 的收益率色碼在同一張卡上打架（按鈕標籤的粗體則看不出來）。
        title = f"{card.symbol}　${money(card.target_price)}　{card.target_month}"
        label = esc(f"▸ {title}" if card.id == selected else title)
        if st.button(label, key=f"ws-card-{card.id}",
                     use_container_width=True):
            st.session_state["ws-detail"] = card.id
            st.rerun()
        st.markdown(f"{SIGNAL_ICON[card.signal]}　{return_md(card.best_return)}")
        if card.signal == workspace.SIGNAL_YELLOW:
            prev = views[card.id]
            if prev is not None:
                st.caption(f"關鍵資料刷新失敗，顯示上次成功更新："
                          f"{prev['analyzed_at']}")
            else:
                st.caption("關鍵資料刷新失敗，尚無任何成功快照可顯示。")
        if st.session_state.get("ws-edit"):
            _render_remove_tool(card.id)


def _render_remove_tool(sid: str) -> None:
    """手動移除＝軟刪除（附錄 A8.2）：二次確認後只寫事件，歷史全留。"""
    if st.session_state.get("ws-remove-ask") != sid:
        if st.button("🗑 移除", key=f"ws-rm-{sid}", use_container_width=True):
            st.session_state["ws-remove-ask"] = sid
            st.rerun()
        return
    st.caption("移除後不再出現於清單，歷史保留。")
    yes, no = st.columns(2)
    with yes:
        if st.button("確定", key=f"ws-rm-yes-{sid}", use_container_width=True):
            workspace.remove_scenario(WS_ROOT, sid)
            st.session_state.pop("ws-remove-ask", None)
            if st.session_state.get("ws-detail") == sid:
                st.session_state.pop("ws-detail", None)
            st.rerun()
    with no:
        if st.button("取消", key=f"ws-rm-no-{sid}", use_container_width=True):
            st.session_state.pop("ws-remove-ask", None)
            st.rerun()


def _render_detail(sc) -> None:
    st.subheader(esc(f"{sc.symbol}　${money(sc.target_price)}　"
                     f"{sc.target_month}　{STATUS_BADGE[sc.status]}"))
    if st.button("分析", key=f"ws-an-{sc.id}"):
        # 僅成功才 rerun——失敗時 st.error 留在本次渲染，不被沖掉
        if _analyze_with_status(sc.id, workspace.analyze_scenario, WS_ROOT,
                                sc.id) is not None:
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

    view = views[sc.id]
    if view is None:
        st.info("尚無分析結果。按上方「分析」取得目前報價與候選。")
        return
    render_summary(view)
    key = st.session_state.get("ws-selected-key")
    if find_row(view, key) is None:
        # T10（附錄A8.5）：詳細頁預設選中 baseline 期第 1 名，不是舊有
        # 全域最高報酬語意（QA1-01 後已隨快速分析頁一併移除）。
        key = baseline_key(view)
        st.session_state["ws-selected-key"] = key
    row = find_row(view, key)
    if row is not None and row["candidate"]["pct_of_capital"] is not None:
        st.caption(f"佔本金 {pct(row['candidate']['pct_of_capital'])}")
    render_step2(view, key)
    render_step3(view, key, state_key="ws-selected-key")
    render_expiry_top10(view, key, state_key="ws-selected-key")
    # T11（#25）：唯讀跨快照聚合，只在選中候選時才查——避免無謂重複掃描
    # results/<sid>/*.json（劇本刷新次數多時，這個目錄可能不小）。
    history = (workspace.spread_history(WS_ROOT, sc.id, key)
              if key is not None else None)
    render_step4(view, key, history=history)


left, right = st.columns([0.2, 0.8], gap="medium")

# ---------- 左：劇本卡片清單 ----------
with left:
    st.subheader("劇本清單")
    st.toggle("✎ 編輯清單", key="ws-edit")
    if st.button("🔄 刷新", key="ws-refresh-all", use_container_width=True):
        _refresh_all(refreshable, label="刷新未過期劇本……")
        st.rerun()
    if not scenarios:
        st.info("尚無劇本。用右側「＋ 建立劇本」開始。")
    elif len(scenarios) > 6:
        st.warning(f"目前 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
    for card in cards:
        _render_card(card)

# ---------- 右：設定、建立、詳細頁 ----------
with right:
    constraints = store.load_constraints(WS_ROOT)
    with st.expander("⚙ 設定", expanded=False):
        cur = constraints["total_capital"]
        cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                                 value=float(cur or 0.0), step=1000.0,
                                 key="ws-capital")
        if st.button("儲存設定", key="ws-save-capital"):
            store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
            st.rerun()

    # T4（#18）：只問標的／目標價／目標年月三欄。方向與策略不曝露於 UI，
    # 帶入 MVP 預設（bullish + bull-call-spread）；create 簽章保留全部參數。
    with st.expander("＋ 建立劇本", expanded=not scenarios):
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
                    created = workspace.create_scenario(
                        WS_ROOT, symbol=sym, direction="bullish",
                        target_price=float(st.session_state["ws-new-price"]),
                        target_month=month.key(),
                        notes="",
                        strategies=("bull-call-spread",))
                except ParamError as e:
                    st.error(str(e))
                else:
                    # 需求七：建立劇本當下立即觸發首次刷新，完成後卡片即有數字。
                    # 無論成敗都 rerun——失敗時卡片自身的黃燈＋說明文字
                    # （見 `_render_card`）已是持續可見的失敗指示，不需要
                    # 額外保留一次性 st.error。
                    _analyze_with_status(created.id, workspace.analyze_scenario,
                                         WS_ROOT, created.id)
                    st.session_state["ws-detail"] = created.id
                    st.rerun()

    if selected is None:
        st.info("尚無劇本可顯示。")
    else:
        _render_detail(by_id[selected])
