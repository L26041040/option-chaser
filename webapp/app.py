# webapp/app.py
"""Option Chaser 單一主畫面（Streamlit 入口，`streamlit run webapp/app.py`）。

QA1-01（#28）：拿掉「app／劇本工作區／說明」三分頁疊床架屋——開站直接
落地劇本工作區，不存在與它平行的快速分析入口，「說明」頁一併刪除
（2026-08-02 需求方裁示：不併入、不降為次要入口）。本檔即原本的
`webapp/pages/0_劇本工作區.py`，搬到入口位置後不再有 `pages/` 目錄。

v5 spec §5 ＋ T5（#19）: 桌面兩欄工作區雛形（`st.columns([0.2, 0.8])`，
已由下述 QA1-02 換成 `st.sidebar`）。＋ T7（#21）: 自動／手動刷新。
＋ T8（#22）: 左側清單依 `workspace.sort_cards()` 依最新收益率重排。
＋ T10（#24）: 詳細頁兩層結構——第一層沿用既有 `render_expiry_comparison`
（各期第 1 名＋Heatmap 縮圖，QA1-05 前名為 `render_step3`），第二層新增
`render_expiry_top10`（單期 Top 10，預設 baseline 期，見附錄A8.5）。
切換到期日／點選候選皆純 UI 互動，不觸發 API。
＋ T11（#25）: 選中 Spread 後，Step 4 進階區新增「Spread 歷史」——依身份鍵
跨該劇本全部歷史快照聚合（`workspace.spread_history`），唯讀查詢。

QA1-02（#29）：`st.columns([0.2, 0.8])` 在窄螢幕會自然堆疊、清單壓在
主畫面上方，劇本卡片清單因此改放 `st.sidebar`。Streamlit 的 sidebar
桌面上是常駐左欄、窄螢幕（手機）上自動收合成漢堡選單拉出的側欄——同一份
程式碼即涵蓋兩種螢幕寬度下的行為，不需要應用層另外判斷視窗寬度。主畫面
（設定、建立表單、被選中劇本的詳細頁）永遠是唯一主角。

QA1-04（#31）：建立表單三欄全部留白，不預填任何值；目標價位改用純文字
輸入（`_parse_target_price`）以支援真正的空白，取代原本的
`st.number_input(value=100.0)`。目標年月除了既有的自由格式文字輸入，
新增年／月輔助下拉，兩者並存；選好兩個下拉即自動把 `YYYY/M` 填進文字框
（見 `_sync_month_dropdown_to_text`）——Streamlit 只在 widget 提交時重跑，
沒有逐鍵盤事件，因此連動僅單向（下拉→文字），無法做到打字時即時反向連動。

QA1-05（#32）：`_render_detail` 呼叫順序改為 Step2 → 到期日選擇
（`render_expiry_top10`）→ 到期日分組比較（`render_expiry_comparison`，
原名 `render_step3`）→ Step4——到期日選擇緊接主圖之後，不再壓在冗長比較
表下方。兩函式的候選卡片皆改窄版展開列（拿掉 thumbnail 與多指標欄，
只留徽章、策略／履約、劇本報酬），問題陳述明確點名「每個候選都是一整條
寬列」正是 `render_expiry_comparison`；細節見 render.py 兩函式各自的
docstring。

QA1-06（#33）：候選展開列不再是會改寫 Step 2 主圖的「選看」按鈕——改用
`st.expander` 就地展開該候選的 Heatmap（`render.py` 的
`_render_candidate_expander`）。`st.expander` 展開／收合是純前端互動，
不觸發重跑，因此不寫入 `ws-selected-key`、不影響 Step 2。`ws-selected-key`
自此固定為 baseline 期預設候選（見上方 `_render_detail` 的
`baseline_key` 初始化邏輯），Step 2／Step 4／「佔本金」／Spread 歷史皆
沿用這個固定值，不再跟著候選展開互動改變。

群組區自首頁移除（附錄 A8.6）——`store.rebuild_groups`／
`workspace.analyze_group` 等底層邏輯原封不動，只是不再於此頁曝露。
GUI 零金融公式：所有數字來自 result dict（store 預算）或 scenario 欄位。

T7：開站首次載入自動刷新所有未過期劇本（同一 session 只此一次，靠
`AUTO_REFRESH_KEY` 旗標把關）。建立劇本立即觸發該劇本首次刷新。同標的
多劇本各自獨立呼叫 `workspace.analyze_scenario`（各自 fetch，不共用
snapshot——附錄 A8.9），單一劇本失敗不擋其他。原子性由
`workspace.analyze_scenario`／`store.save_result` 既有次序保證（失敗即
提前 return，成功才落盤＋補事件），本頁不需另外處理。

效能觀察（issue #21 AC，僅記錄不設門檻）：3 個劇本、離線重放同一份
snapshot fixture、序列刷新，總耗時約 29ms（本機量測，計算部分；不含
真實網路延遲——沙箱環境無法連外抓真實報價）。多劇本序列刷新目前無並行化，
劇本數量顯著增加時應重新量測。

QA1-07（#34）：刷新時機收斂為嚴格三種——開站首次載入、新增劇本當下、
頁面**最上方**的刷新鈕（原本放在側欄清單旁，移到主畫面頂部）。詳細頁
原本每張劇本各自的「分析」重刷按鈕**移除**（2026-08-02 需求方裁示：
嚴格照三種情況解讀，不屬於任何一種，拿掉而非保留成第四種管道）；
`_analyze_with_status` 因此失去唯一有意義的呼叫端（建立流程原本呼叫它，
但無論成敗都接著 `st.rerun()`，其 `st.error` 分支其實從未真的被使用者
看到），一併刪除、改走 `_refresh_all`，統一成單一刷新路徑。「到期日
選擇」橫向按鈕原本「按鈕觸發重跑後又手動 `st.rerun()` 一次」＝多刷一輪
（見 `render.py` 的 `render_expiry_top10`），改用 `on_click` 回呼，回呼
在重跑前執行，同一輪重跑即讀到新值，不需要第二輪。
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from option_chaser.models import FetchError, ParamError
from option_chaser.timeframe import parse_target_month
from webapp.render import (baseline_key, esc, find_row, money, pct,
                           render_expiry_comparison, render_expiry_top10,
                           return_md, render_step2, render_step4,
                           render_summary)

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

# QA1-07（#34）：手動刷新鈕移到頁面最上方——需求七三種刷新時機之一
# （開站／新增劇本按分析／頂部刷新鈕），其他操作一律不得觸發資料重抓。
if st.button("🔄 刷新", key="ws-refresh-all"):
    _refresh_all(refreshable, label="刷新未過期劇本……")
    st.rerun()

views = {sc.id: workspace.latest_result(WS_ROOT, sc.id) for sc in scenarios}
failure_flags = st.session_state.setdefault(_FAILURE_KEY, {})
cards = workspace.sort_cards(
    [workspace.card_of(sc, views[sc.id],
                       critical_failure=failure_flags.get(sc.id, False))
     for sc in scenarios])

# 選中的劇本：預設第一張卡，主畫面因此一載入就有東西可看。
selected = st.session_state.get("ws-detail")
if selected not in by_id:
    selected = scenarios[0].id if scenarios else None
    st.session_state["ws-detail"] = selected


def _render_card(card) -> None:
    """恰五項：標的／目標價／目標年月／最高收益率／一個燈號（需求五）。

    整張卡片就是進詳細頁的按鈕；腿別、成本、佔本金等技術數字一律留給主畫面。
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
    """QA1-07（#34）：詳細頁不再有單一劇本專屬的「分析」重刷按鈕——需求七
    只認三種刷新時機（開站／新增劇本／頁面頂部刷新鈕），不含「進了某個
    劇本的詳細頁後再點一次分析」這個第四種管道。要重刷這張劇本，走最上方
    的刷新鈕（會刷新全部未過期劇本，含這張）。

    QA1-08（#35）：原本這裡還有「原因」輸入欄＋「標記達成」／「標記失效」
    兩顆按鈕——當初是預留給持倉紀錄工具的操作入口，目前沒有用處，依需求方
    裁示整組拿掉。`workspace.set_status()` 與其資料模型／事件紀錄／燈號
    邏輯不在本票範圍，原封不動（`test_workspace.py` 仍在測），只移除這裡
    的操作入口；`Scenario.status`／`STATUS_BADGE` 生命週期徽章維持顯示。
    """
    st.subheader(esc(f"{sc.symbol}　${money(sc.target_price)}　"
                     f"{sc.target_month}　{STATUS_BADGE[sc.status]}"))

    view = views[sc.id]
    if view is None:
        st.info("尚無分析結果。使用頁面最上方的「🔄 刷新」按鈕取得目前報價與候選。")
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
    # QA1-05（#32）：到期日選擇緊接主圖之後，長列比較表退居其後（見
    # render.py 兩函式各自的 docstring）。
    render_expiry_top10(view, key, state_key="ws-selected-key")
    render_expiry_comparison(view, key)
    # T11（#25）：唯讀跨快照聚合，只在選中候選時才查——避免無謂重複掃描
    # results/<sid>/*.json（劇本刷新次數多時，這個目錄可能不小）。
    history = (workspace.spread_history(WS_ROOT, sc.id, key)
              if key is not None else None)
    render_step4(view, key, history=history)


# ---------- 側欄：劇本卡片清單（QA1-02／#29：桌面常駐、窄螢幕收合漢堡） ----------
# QA1-07（#34）：刷新鈕移到頁面最上方，此處不再重複。
with st.sidebar:
    st.subheader("劇本清單")
    st.toggle("✎ 編輯清單", key="ws-edit")
    if not scenarios:
        st.info("尚無劇本。用主畫面「＋ 建立劇本」開始。")
    elif len(scenarios) > 6:
        st.warning(f"目前 {len(scenarios)} 個劇本（建議上限 6，僅提示不限制）。")
    for card in cards:
        _render_card(card)

# ---------- 主畫面：設定、建立、詳細頁 ----------
constraints = store.load_constraints(WS_ROOT)
with st.expander("⚙ 設定", expanded=False):
    cur = constraints["total_capital"]
    cap_in = st.number_input("資金總額（0＝未設定）", min_value=0.0,
                             value=float(cur or 0.0), step=1000.0,
                             key="ws-capital")
    if st.button("儲存設定", key="ws-save-capital"):
        store.save_constraints(WS_ROOT, cap_in if cap_in > 0 else None)
        st.rerun()


def _parse_target_price(text: str | None) -> float:
    """目標價位改用純文字輸入以支援真正留白（QA1-04／#31：不留預設值），
    在此手動解析與驗證，用 ParamError 表達錯誤，與年月解析同一套機制。"""
    text = (text or "").strip()
    if not text:
        raise ParamError("請輸入目標價位。")
    try:
        price = float(text)
    except ValueError:
        raise ParamError(f"目標價位請輸入數字：{text!r}")
    if price <= 0:
        raise ParamError(f"目標價位必須為正數：{text!r}")
    return price


def _sync_month_dropdown_to_text() -> None:
    """QA1-04（#31）：年／月輔助下拉與文字輸入並存，選好兩個下拉即自動把
    `YYYY/M` 填進文字框。掛在 `on_change`——只在下拉「改變」的那次重跑觸發，
    且發生在本次重跑的其餘 widget 尚未建立之前，因此可以安全覆寫文字框的
    session_state，也不會每次重跑都覆寫使用者手動修改過的文字內容。

    Streamlit 只在 widget 提交（失焦／Enter）時重跑，沒有逐鍵盤事件，因此
    無法做到「打字時即時反向連動下拉」；本票允許依框架可行性決定連動程度，
    這是可行範圍內做到的單向（下拉→文字）連動。
    """
    y = st.session_state.get("ws-new-year")
    m = st.session_state.get("ws-new-month-dd")
    if y is not None and m is not None:
        st.session_state["ws-new-month"] = f"{y}/{m}"


# T4（#18）：只問標的／目標價／目標年月三欄。方向與策略不曝露於 UI，
# 帶入 MVP 預設（bullish + bull-call-spread）；create 簽章保留全部參數。
# QA1-04（#31）：三欄全部留白，不預填任何值。
with st.expander("＋ 建立劇本", expanded=not scenarios):
    st.text_input("標的", key="ws-new-symbol", placeholder="TLT")
    st.text_input("目標價位", key="ws-new-price", placeholder="120.00")
    year_now = workspace.ny_today().year
    ycol, mcol = st.columns(2)
    with ycol:
        st.selectbox("年（輔助選單）", list(range(year_now, year_now + 11)),
                     index=None, placeholder="年", key="ws-new-year",
                     on_change=_sync_month_dropdown_to_text)
    with mcol:
        st.selectbox("月（輔助選單）", list(range(1, 13)),
                     index=None, placeholder="月", key="ws-new-month-dd",
                     on_change=_sync_month_dropdown_to_text)
    st.text_input("目標年月", key="ws-new-month", placeholder="2028/1")
    if st.button("建立", key="ws-new-create"):
        sym = (st.session_state.get("ws-new-symbol") or "").strip().upper()
        if not sym:
            st.error("請輸入標的代號。")
        else:
            # 格式錯誤、價位非數字／非正數、與「已過完的月份」都由 ParamError
            # 表達（後兩者分別在 `_parse_target_price` 與 create 裡把關）
            try:
                price = _parse_target_price(st.session_state.get("ws-new-price"))
                month = parse_target_month(
                    st.session_state.get("ws-new-month") or "")
                created = workspace.create_scenario(
                    WS_ROOT, symbol=sym, direction="bullish",
                    target_price=price,
                    target_month=month.key(),
                    notes="",
                    strategies=("bull-call-spread",))
            except ParamError as e:
                st.error(str(e))
            else:
                # 需求七：建立劇本當下立即觸發首次刷新，完成後卡片即有數字。
                # 走 `_refresh_all`（QA1-07／#34 後單一劇本刷新管道
                # `_analyze_with_status` 已隨詳細頁「分析」按鈕一併移除）。
                # 無論成敗都 rerun——失敗時卡片自身的黃燈＋說明文字（見
                # `_render_card`）已是持續可見的失敗指示，不需要額外保留
                # 一次性 st.error。
                _refresh_all([created.id], label="分析新劇本……")
                st.session_state["ws-detail"] = created.id
                st.rerun()

if selected is None:
    st.info("尚無劇本可顯示。")
else:
    _render_detail(by_id[selected])
