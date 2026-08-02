"""v5 spec §5.1：四步渲染純函數，dict 介面，零金融公式。

所有函數皆消費 `option_chaser.store.serialize_result` 產出的 view dict
（及其中的 candidate dict），僅做格式化與座標幾何（顏色色階、Pareto 邊界、
SVG 座標映射），不執行任何金融估值——每個顯示數字都取自已由 service 預算好的
dict 欄位。此模組刻意與 Streamlit 以外的計算解耦，供 webapp/app.py（劇本
工作區單一主畫面）共用。
"""
from __future__ import annotations

import streamlit as st

from option_chaser.data.snapshot import load_snapshot, snapshot_to_csv
from option_chaser.glossary import GLOSSARY
from option_chaser.models import SnapshotSchemaError
from option_chaser.report import STRATEGY_LABELS

STRATEGY_COLOR = {
    "long-call": "#1f77b4", "bull-call-spread": "#2ca02c",
    "long-put": "#d62728", "bear-put-spread": "#9467bd",
}


def esc(text: str) -> str:
    """v3.1/v4 spec §4.7: escape '$' so st.markdown never triggers LaTeX."""
    return text.replace("$", "\\$")


def abbr(term: str) -> str:
    """Wrap a glossary term in an <abbr> hover tooltip (spec §4.6)."""
    return f'<abbr title="{GLOSSARY[term]}">{term}</abbr>'


def cell_color(ret: float) -> str:
    """0% 為中心之紅綠雙向色階；顯示範圍鉗制 ±100%；|ret|<5% 中性。純函數。"""
    if abs(ret) < 0.05:
        return "#ededed"
    t = min(abs(ret), 1.0)
    target = (34, 139, 34) if ret > 0 else (178, 34, 34)
    r = round(255 - t * (255 - target[0]))
    g = round(255 - t * (255 - target[1]))
    b = round(255 - t * (255 - target[2]))
    return f"#{r:02x}{g:02x}{b:02x}"


_LABEL_TEXT = {"<現價>": "現價", "<目標>": "目標", "<超標>": "超標", "<深跌>": "深跌"}


def _price_tag(label: str) -> str:
    tag = label
    for k, v in _LABEL_TEXT.items():
        tag = tag.replace(k, f" {v}")
    return tag


def heatmap_html(matrix: dict) -> str:
    """v4 spec §4.2/§4.3: bold rows are exactly those whose price_axis label is
    non-empty (spot/target/overshoot/adverse) — GUI reads the label, it never
    recomputes the anchor prices itself."""
    dates = matrix["dates"]
    prices = matrix["prices"]
    cells = matrix["cells"]
    n = len(dates)
    head_cells = []
    for j, (iso, _lbl) in enumerate(dates):
        # A2.3：日期軸已無「*」目標欄，末欄仍標到期
        suffix = "（到期）" if j == n - 1 else ""
        head_cells.append(
            f'<th style="padding:4px 8px;white-space:nowrap">{iso[5:7]}/{iso[8:10]}{suffix}</th>')
    rows = []
    for i in range(len(prices) - 1, -1, -1):
        price, plabel = prices[i]
        cells_html = "".join(
            f'<td style="background:{cell_color(v)};color:#111;text-align:right;'
            f'padding:4px 8px">{v * 100:+.0f}%</td>'
            for v in cells[i])
        price_text = f"{price:.2f}{_price_tag(plabel)}"
        if plabel:
            price_text = f"<b>{price_text}</b>"
        rows.append(
            f'<tr><td style="padding:4px 8px;white-space:nowrap">'
            f'{price_text}</td>{cells_html}</tr>')
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;'
            'font-family:monospace;font-size:13px">'
            f'<tr><th style="padding:4px 8px">價格</th>{"".join(head_cells)}</tr>'
            + "".join(rows) + "</table></div>"
            '<p style="font-size:12px;color:#666">此圖顯示在不同標的價格與日期下，'
            '以最差進場成本（買付 Ask、賣收 Bid）進場的模型報酬率。'
            '<b>粗體</b>價格列為錨點（現價／目標／超標／深跌），其餘為等距內插價。</p>')


def _badge_str(row: dict, selected_key: str | None) -> str:
    """QA1-05（#32）：候選卡片全面改窄版可點列後，`st.button` 標籤不支援
    unsafe_allow_html，原本與此函式並存的 `<abbr>` HTML 版本已無呼叫端，
    直接刪除（不是留著沒用）。

    QA1-09（#36）：不再顯示 🚀「最高報酬」／🛡️「最強韌性」——這兩個徽章
    在需求方眼中是會誤導判斷的評語式標記，已下令刪除。`row["badges"]`
    後端仍可能含 `top_return`／`top_resilience`（`service._build_groups()`
    計算，本票不動），這裡只是不再讀取、不再顯示這兩種；⚠ 警示（資料
    品質旗標，非評語）維持。
    """
    badges = row["badges"]
    parts = []
    if "warning" in badges:
        parts.append("⚠")
    if selected_key is not None and row["candidate"]["candidate_key"] == selected_key:
        parts.append("◀")
    return "".join(parts)


def money(x: float) -> str:
    return f"{x:.2f}"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def return_md(value: float | None) -> str:
    """劇本卡片的收益率寫法（需求五）：正數綠、負數紅、無快照「—」。

    純字串函式：色彩用 Streamlit 的 `:green[]`／`:red[]` 指令而非 HTML，
    卡片因此在深淺色主題下都讀得到。恰好 0 不著色——它既不是盈也不是虧。
    """
    if value is None:
        return "—"
    text = f"{value * 100:+.1f}%"
    if value > 0:
        return f":green[{text}]"
    if value < 0:
        return f":red[{text}]"
    return text


def _candidate_label(cand: dict) -> str:
    legs = cand["legs"]
    if len(legs) == 2:
        return f"買 {legs[0]['strike']:g} / 賣 {legs[1]['strike']:g}"
    return f"K={legs[0]['strike']:g}"


_STRATEGY_ABBR_TERM = {"bull-call-spread": "BCS", "bear-put-spread": "BPS"}


def _strategy_title(strategy: str) -> str:
    term = _STRATEGY_ABBR_TERM.get(strategy)
    if term:
        return abbr(term)
    return STRATEGY_LABELS[strategy]


def _candidate_title(strategy: str, cand: dict) -> str:
    return f"{_strategy_title(strategy)} {_candidate_label(cand)}"


def _candidate_title_plain(strategy: str, cand: dict) -> str:
    """同 `_candidate_title`，但策略縮寫不含 `abbr()` 的 `<abbr>` HTML——
    `st.button` 的標籤不支援 unsafe_allow_html，QA1-05（#32）窄版可點列
    需要純文字版本。"""
    term = _STRATEGY_ABBR_TERM.get(strategy, STRATEGY_LABELS[strategy])
    return f"{term} {_candidate_label(cand)}"


def all_rows(view: dict) -> list[dict]:
    return [row for g in view["expiry_groups"] for row in g["rows"]]


def _expiry_top10_rows(view: dict) -> list[dict]:
    """T10（#24）：把 `expiry_top10`（T9 新增，各期自己的前十名）攤平成
    跟 `all_rows()` 一樣的 {strategy, candidate} 形狀，供 `find_row()` 共用
    ——第二層 Top10 清單選中的 Spread（不只是各期第 1 名）也要能被
    `render_step2`（Step 2 主圖）找到、畫出它專屬的 Heatmap。"""
    return [{"strategy": r["strategy"], "candidate": cand}
            for r in view["results"] for g in r.get("expiry_top10", [])
            for cand in g["candidates"]]


def find_row(view: dict, key: str | None) -> dict | None:
    if key is None:
        return None
    for row in all_rows(view):
        if row["candidate"]["candidate_key"] == key:
            return row
    for row in _expiry_top10_rows(view):
        if row["candidate"]["candidate_key"] == key:
            return row
    return None


def baseline_key(view: dict) -> str | None:
    """T10（附錄A8.5）：詳細頁進頁預設選中——baseline 期自己的第 1 名。
    與全域最高報酬語意（`view["default_selection"]`，QA1-01 隨快速分析頁
    一併移除）刻意分開，見 `service.AnalysisResult` 的欄位註解。"""
    sel = view.get("baseline_selection")
    return sel[1] if sel else None


def render_summary(view: dict) -> None:
    """Step 1 chips (spec §4.1): summary line + any per-strategy skip/empty
    notices. The edit form itself is rendered separately by the main script
    (inside the '✎ 修改劇本' expander) so its submit button is visible to the
    submit-dispatch logic on the SAME rerun it is clicked."""
    m = view["meta"]
    base = view["params"]
    strategies_used = "、".join(
        STRATEGY_LABELS[r["strategy"]] for r in view["results"] if r["status"] == "ok")
    move_pct = m["target_move"] * 100
    chips = (f"**{m['symbol']}** 劇本 ｜ 現價 ${money(m['spot'])} ｜ "
             f"目標 ${money(base['target_price'])}（{move_pct:+.1f}%）｜ "
             f"{base['target_month']} ｜ {strategies_used or '（無已完成策略）'}")
    st.markdown(esc(chips))
    for r in view["results"]:
        if r["status"] != "ok":
            st.info(f"{STRATEGY_LABELS[r['strategy']]}：{r['message']}")


def render_step2(view: dict, key: str | None) -> None:
    st.subheader("Step 2　劇本主圖")
    row = find_row(view, key)
    if row is None:
        st.info("目前沒有可顯示的候選（所有策略皆未產生合格合約）。")
        return
    cand = row["candidate"]
    st.markdown(esc(f"**{_candidate_title(row['strategy'], cand)}**"),
                unsafe_allow_html=True)
    st.markdown(heatmap_html(cand["matrix"]), unsafe_allow_html=True)


def _render_candidate_expander(strategy: str, cand: dict, *, mark: str = "",
                               rank: int | None = None) -> None:
    """QA1-06（#33）共用窄版展開列：收起時只顯示一行摘要（徽章／排名／
    策略／履約／劇本報酬）；展開才就地顯示該候選專屬的 Heatmap。標籤
    本身也在這裡組裝（`mark`／`rank` 是呼叫端僅有的兩個差異點），避免
    `render_expiry_comparison`／`render_expiry_top10` 各自重複組字串。

    `st.expander` 展開／收合是純前端互動，不觸發任何重跑，因此不寫入
    `session_state`、不影響 Step 2 主圖——正是本票要的「不跳動頁面位置、
    不改寫主圖」：先前「選看」按鈕會把候選寫進共用的選中狀態、觸發
    `st.rerun()`，導致整頁重繪並跳回最上方的 Step 2；使用者在下面比較
    候選時，主圖被迫跟著每次點擊改寫、視角也被拋回上面。`render_step2`
    如今固定顯示 baseline 期的預設候選，只在初次進頁或找不到候選時才會
    更新，不再跟著這裡的展開互動改變。"""
    parts = [p for p in (mark, f"#{rank}" if rank is not None else "",
                        _candidate_title_plain(strategy, cand)) if p]
    label = "🔽 " + "　".join(parts) + f"　{pct(cand['baseline_return'])}"
    with st.expander(label, expanded=False):
        st.markdown(esc(f"**{_candidate_title(strategy, cand)}**"),
                    unsafe_allow_html=True)
        st.markdown(heatmap_html(cand["matrix"]), unsafe_allow_html=True)


def render_expiry_comparison(view: dict, key: str | None) -> None:
    """到期日分組比較表（QA1-05／#32：原「Step 3」，編號已讓給
    `render_expiry_top10`——現在緊接 Step 2 主圖之後——本函式退居次要
    參考，標題不再帶編號，函式名稱也一併改掉以免與新的 Step 3 混淆）。

    候選卡片改窄版展開列（問題陳述明確點名的「每個候選都是一整條寬列，
    卡片太長」正是本函式——原本的 8 欄 thumbnail＋多指標列＋獨立「選看」鈕
    拿掉，只留徽章、策略／履約、劇本報酬一行，仿 `render_expiry_top10` 的
    TradingView 手機版標的列風格；QA1-06（#33）：改為 `st.expander` 就地
    展開 Heatmap，不再是會改寫 Step 2 主圖的「選看」按鈕，見
    `_render_candidate_expander` 說明）。情境最壞／不漲保留率／Bid-Ask
    Spread 不在這張快速比較表顯示：資料品質異常已透過 ⚠ 徽章標示，數字
    細節留給 Step 4 進階區（`_render_resilience_expander`／
    `_render_greeks_expander`），與 T5／需求五「劇本卡片恰五項」的精簡
    先例一致，不在快速比較列重複鋪陳。

    QA1-09（#36）：不再顯示 🚀「最高報酬」／🛡️「最強韌性」徽章與圖例
    ——需求方判定為會誤導判斷的評語式標記，一併從圖例拿掉。

    `key` 僅用於標示「目前 Step 2 主圖顯示的是哪一個」（◀ 徽章），本函式
    不再有寫入任何選中狀態的機制（不需要 `state_key` 參數）。"""
    st.subheader("到期日分組比較")
    if not view["expiry_groups"]:
        st.info("目前沒有可比較的候選。")
        return
    st.markdown('<p style="font-size:12px;color:#666">⚠ 警示（零成交腿／'
                'Bid-Ask Spread 超標）｜◀ Step 2 主圖顯示中</p>',
                unsafe_allow_html=True)
    for g in view["expiry_groups"]:
        header = f"{g['expiry']} 到期（緩衝 +{g['buffer_days']} 天）"
        st.markdown(f"**{esc(header)}**")
        for row in g["rows"]:
            cand = row["candidate"]
            _render_candidate_expander(row["strategy"], cand,
                                       mark=_badge_str(row, key))
        if g["hidden_count"] > 0:
            st.caption(f"＋此到期日其他 {g['hidden_count']} 個候選")
    if view["hidden_expiries"]:
        st.caption(f"另有 {len(view['hidden_expiries'])} 個到期日未展示。")


def _set_session_key(session_key: str, value: str) -> None:
    """`st.button(on_click=...)` 回呼：純寫入，不觸發額外 `st.rerun()`
    （QA1-07／#34）——回呼在 Streamlit 自身的重跑*之前*執行，因此接下來
    這一輪重跑一開始讀 `session_state` 就已經是新值，不需要第二輪重跑。"""
    st.session_state[session_key] = value


def render_expiry_top10(view: dict, key: str | None, state_key: str) -> None:
    """QA1-05（#32）：到期日選擇緊接 Step 2 主圖之後——原本壓在冗長的
    到期日分組比較表（`render_expiry_comparison`）下方要捲很久才到，
    現在編號讓給這裡。
    到期日橫向並排（`10/1`／`11/1`……），每個日期選項下方附該期最高收益，
    一眼可橫向比較；候選卡片改窄版展開列（TradingView 手機版標的列風格：
    只留排名、策略／履約、劇本報酬），取代原本的 thumbnail＋多欄位＋
    獨立「選看」鈕。到期日連同前十名並排、可橫向滑動對比的大表格本票
    明確不做（需求方裁示：先做本票範圍，之後再評估是否需要）。

    預設顯示 baseline 期，點其他到期日切換——這裡的 `state_key` 只用來
    命名切換到期日的 `viewing_key`（`f"{state_key}-viewing-expiry"`），
    純粹是這個橫向選單自己的局部狀態，與「哪個候選在 Step 2 主圖顯示」
    無關。QA1-06（#33）：點入榜 Spread 已不再改寫 `state_key`／觸發
    `st.rerun()`——就地展開該候選的 Heatmap（`_render_candidate_expander`），
    Step 2 主圖不受影響、頁面位置不跳動。切換到期日、展開候選都是純 UI
    互動，不呼叫任何 `workspace`／`service` 函式，因此不觸發 API（需求七、
    T10 AC 沿用）。第一層（各期摘要）沿用既有的
    `render_expiry_comparison`／`expiry_groups`，本函式不重複那份資料，
    只負責「深入單期」這一層。

    QA1-07（#34）：切換到期日改用 `on_click` 回呼寫入 `session_state`，
    不再額外呼叫 `st.rerun()`。原本「按鈕觸發的自動重跑」之後又手動再
    `st.rerun()` 一次＝重跑兩輪，是多餘的整頁重載（閃爍／捲動跳位）；
    `on_click` 回呼在 Streamlit 重跑*之前*執行，`viewing` 在這次重跑一開始
    就讀到新值，同一輪就能畫對，不需要第二輪。
    """
    st.subheader("Step 3　到期日選擇")
    strat = next((r for r in view["results"] if r.get("expiry_top10")), None)
    if strat is None or not strat["expiry_top10"]:
        st.info("目前沒有可顯示的到期日排名。")
        return

    groups = strat["expiry_top10"]
    expiries = [g["expiry"] for g in groups]
    viewing_key = f"{state_key}-viewing-expiry"
    if st.session_state.get(viewing_key) not in expiries:
        baseline = view.get("baseline_expiry")
        st.session_state[viewing_key] = baseline if baseline in expiries \
            else expiries[0]
    viewing = st.session_state[viewing_key]

    cols = st.columns(len(groups))
    for col, g in zip(cols, groups):
        with col:
            label = f"{int(g['expiry'][5:7])}/{int(g['expiry'][8:10])}"
            if g["expiry"] == viewing:
                label = f"▸{label}"
            st.button(label, key=f"{viewing_key}-{g['expiry']}",
                     use_container_width=True, on_click=_set_session_key,
                     args=(viewing_key, g["expiry"]))
            top = (max(c["baseline_return"] for c in g["candidates"])
                  if g["candidates"] else None)
            st.caption(return_md(top))

    group = next(g for g in groups if g["expiry"] == viewing)
    for i, cand in enumerate(group["candidates"], start=1):
        mark = "▸" if cand["candidate_key"] == key else ""
        _render_candidate_expander(strat["strategy"], cand, mark=mark, rank=i)


def _render_resilience_expander(view: dict, key: str | None) -> None:
    row = find_row(view, key)
    if row is None:
        st.info("無選中候選。")
        return
    cand = row["candidate"]
    from option_chaser.scenarios import SCENARIO_NAMES
    st.markdown(f"**{esc(_candidate_title(row['strategy'], cand))}** 的 7 情境向量")
    lines = ["|情境|報酬|", "|---|---|"]
    for code, ret in cand["scenario_vector"]["entries"]:
        is_worst = code == cand["scenario_vector"]["worst_code"]
        mark = " ◀ 情境最壞" if is_worst else ""
        cell = f"{pct(ret)}{mark}"
        if is_worst:
            cell = f'<span style="background:#f8d7da">{cell}</span>'
        lines.append(f"|{code} {SCENARIO_NAMES[code]}|{cell}|")
    st.markdown("\n".join(lines), unsafe_allow_html=True)

    # Prices are precomputed in service._v4_fields (cand["completion_prices"]) —
    # GUI performs zero financial arithmetic, only zips the two lists.
    curve_lines = ["", "**完成度報酬曲線**", "|完成度|對應價位|報酬|", "|---|---|---|"]
    for (k, ret), price_at_k in zip(cand["completion_curve"], cand["completion_prices"]):
        curve_lines.append(f"|{int(k * 100)}%|${money(price_at_k)}|{pct(ret)}|")
    st.markdown(esc("\n".join(curve_lines)))

    if cand["completion_threshold"] is None:
        thr = "— ⚠劇本全成仍不保本"
    elif cand["completion_threshold"] <= 0:
        thr = "0%（已保本）"
    else:
        thr = (f"完成 {pct(cand['completion_threshold'])}"
               f"（{abbr('保本價')} ${money(cand['breakeven_at_target'])}，基準IV）")
    st.markdown(esc(f"**完成度門檻**：{thr}"), unsafe_allow_html=True)


def _pareto_frontier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Geometry-only selection over already-computed (x, y) pairs (spec §4.5:
    'GUI 僅座標映射'). No financial value is computed here."""
    pts_sorted = sorted(points, key=lambda pt: (-pt[0], -pt[1]))
    frontier = []
    best_y = float("-inf")
    for pt in pts_sorted:
        if pt[1] > best_y:
            frontier.append(pt)
            best_y = pt[1]
    frontier.sort(key=lambda pt: pt[0])
    return frontier


def _scatter_svg(all_pairs) -> str:
    W, H, PAD = 600, 360, 44
    points = [(cand["scenario_vector"]["worst_return"], cand["baseline_return"], s, cand)
              for s, cand in all_pairs]
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    costs = [cand["mid_cost"] for s, cand in all_pairs]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    x_span = (x_hi - x_lo) or 1.0
    y_span = (y_hi - y_lo) or 1.0
    c_lo, c_hi = min(costs), max(costs)
    c_span = (c_hi - c_lo) or 1.0

    def px(x: float) -> float:
        return PAD + (x - x_lo) / x_span * (W - 2 * PAD)

    def py(y: float) -> float:
        return H - PAD - (y - y_lo) / y_span * (H - 2 * PAD)

    def radius(c: float) -> float:
        return 4 + (c - c_lo) / c_span * 10

    frontier = _pareto_frontier([(pt[0], pt[1]) for pt in points])
    frontier_set = set(frontier)
    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'style="width:100%;max-width:{W}px;font-family:monospace;font-size:10px">']
    svg.append(f'<line x1="{PAD}" y1="{H - PAD}" x2="{W - PAD}" y2="{H - PAD}" stroke="#999"/>')
    svg.append(f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H - PAD}" stroke="#999"/>')
    svg.append(f'<text x="{W / 2}" y="{H - 10}" text-anchor="middle">情境最壞（越右越韌）</text>')
    svg.append(f'<text x="14" y="{H / 2}" text-anchor="middle" '
               f'transform="rotate(-90 14 {H / 2})">劇本報酬（越上越高）</text>')
    if len(frontier) > 1:
        poly = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in frontier)
        svg.append(f'<polyline points="{poly}" fill="none" stroke="#333" '
                    f'stroke-width="1.5" stroke-dasharray="4 2"/>')
    for x, y, s, cand in points:
        dominated = (x, y) not in frontier_set
        color = STRATEGY_COLOR.get(s, "#888888")
        opacity = 0.35 if dominated else 0.9
        r = radius(cand["mid_cost"])
        svg.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r:.1f}" '
                    f'fill="{color}" fill-opacity="{opacity}" stroke="#333" stroke-width="0.5">'
                    f'<title>{STRATEGY_LABELS[s]} {pct(x)}/{pct(y)}</title></circle>')
    svg.append("</svg>")
    return "".join(svg)


def _render_scatter_expander(view: dict) -> None:
    """QA1-09（#36）：散點原本會疊 🚀「最高報酬」／🛡️「最強韌性」文字標記
    （由 `top_return`／`top_resilience` 徽章驅動），需求方判定為評語式
    標記一併刪除；`_scatter_svg` 因此不再需要 `badge_of` 回呼參數。"""
    all_pairs = [(r["strategy"], cand) for r in view["results"] if r["status"] == "ok"
                 for cand in r["expiry_best"]]
    if not all_pairs:
        st.info("目前沒有可比較的候選。")
        return
    st.markdown('<div style="overflow-x:auto">' +
                _scatter_svg(all_pairs) +
                "</div>", unsafe_allow_html=True)
    legend = "｜".join(f'<span style="color:{c}">●</span> {STRATEGY_LABELS[s]}'
                       for s, c in STRATEGY_COLOR.items())
    st.markdown(legend + "　點大小 ~ Mid 成本；淡色點為 Pareto 被支配點。",
                unsafe_allow_html=True)


def _render_greeks_expander(view: dict, key: str | None) -> None:
    row = find_row(view, key)
    if row is None:
        st.info("無選中候選。")
        return
    cand = row["candidate"]
    legs = cand["legs"]
    is_spread = len(legs) == 2
    lines = [f"**Net {abbr('Delta')}**：{cand['net_delta']:.2f}"]
    if is_spread:
        lines[-1] += "（價差：兩腿相減，方向語意較弱，僅供參考）"
    lines.append(f"**Θ日耗率**：{pct(cand['theta_day_rate'])}"
                 "（隨到期接近會加速流失，此為目前速率）")
    lines.append(f"**{abbr('Vega')}/1pt**：{pct(cand['vega_per_pt'])}")
    if is_spread:
        lines.append(f"買腿 OI/Volume：{legs[0]['open_interest']}/{legs[0]['volume']}")
        lines.append(f"賣腿 OI/Volume：{legs[1]['open_interest']}/{legs[1]['volume']}")
    else:
        lines.append(f"OI/Volume：{legs[0]['open_interest']}/{legs[0]['volume']}")
    lines.append(f"**{abbr('Bid-Ask Spread')}**："
                 f"{pct(min(cand['friction'], 9.99))}（${cand['friction_amount']:.2f}/股）")
    lines.append(f"**30天純時間衰減**：{pct(cand['decay_30d_return'])}"
                 "（S=現價、IV 不變、今日+30天估值）")
    st.markdown(esc("\n\n".join(lines)), unsafe_allow_html=True)


def _render_report_expander(view: dict, key: str | None) -> None:
    """QA1-10（#37）：純文字報告獨立成明確標示的展開區——原本埋在
    「Greeks 與流動性」展開區最底部，沒有標題、不易發現（問題陳述原話）。
    內容不變，只是搬家：`res["report_text"]` 本來就存在，這裡不重算。"""
    row = find_row(view, key)
    if row is None:
        st.info("無選中候選。")
        return
    res = next((r for r in view["results"] if r["strategy"] == row["strategy"]), None)
    if res is None or not res["report_text"]:
        st.info("尚無分析報告。")
        return
    st.code(res["report_text"], language=None)


def _render_raw_data_expander(view: dict) -> None:
    """QA1-10（#37）：原始資料查看＋下載——需求方原話「免得你亂掰我卻查不到
    證據」。範圍依裁示只做「當下快照」：不接外部持久化儲存（Streamlit
    Community Cloud 會自動重啟清空磁碟，只是測試環境，非上線後的去處）。

    取得（`load_snapshot`）／轉換（`snapshot_to_csv`）／輸出（本函式）
    三層清楚分離——換儲存後端時只需替換取得層，這裡與 CSV 轉換邏輯不動。
    不吃 `key`：快照跟哪個候選被選中無關，一次分析只有一份快照。
    """
    ref = view["snapshot_ref"]
    try:
        snap = load_snapshot(ref["path"])
    except OSError:
        st.warning(f"原始快照檔案已不在（{ref['path']}）——不是資料錯誤，"
                  "是部署環境的磁碟在重啟後被清空（已知限制）。")
        return
    except SnapshotSchemaError as e:
        st.warning(f"原始快照檔案格式不相容：{e}")
        return
    st.caption(f"標的 {snap.symbol}｜現價 ${money(snap.spot)}｜"
              f"資料時間 {snap.fetched_at}｜來源 {snap.source}｜"
              f"{len(snap.contracts)} 筆合約")
    st.dataframe(
        [{"contract_symbol": c.contract_symbol, "option_type": c.option_type,
          "strike": c.strike, "expiry": c.expiry, "bid": c.bid, "ask": c.ask,
          "last": c.last, "volume": c.volume, "open_interest": c.open_interest,
          "implied_volatility": c.implied_volatility}
         for c in snap.contracts],
        width="stretch", height=240)
    st.download_button(
        "⬇ 下載原始資料（CSV）", snapshot_to_csv(snap),
        file_name=f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.csv",
        mime="text/csv")


def render_spread_history(history: list[dict]) -> None:
    """T11（#25）：選中 Spread 的專屬歷史時間序列——純表格呈現，數字直接來自
    `workspace.spread_history()` 的聚合結果，本函式不做任何金融計算。
    缺席快照（斷點）顯示「—」：如實呈現，不插值、不平滑掉（需求）。"""
    if not history:
        st.info("尚無歷史紀錄。")
        return
    lines = ["|更新時間|標的價|淨成本|收益率|期內名次|", "|---|---|---|---|---|"]
    for e in history:
        cost = f"${money(e['cost'])}" if e["cost"] is not None else "—"
        ret = pct(e["baseline_return"]) if e["baseline_return"] is not None else "—"
        rank = str(e["rank_in_expiry"]) if e["rank_in_expiry"] is not None else "—"
        lines.append(f"|{e['analyzed_at']}|${money(e['spot'])}|{cost}|{ret}|{rank}|")
    st.markdown(esc("\n".join(lines)))


def render_step4(view: dict, key: str | None,
                 history: list[dict] | None = None) -> None:
    st.subheader("Step 4　進階區")
    with st.expander("韌性與壓力情境", expanded=False):
        _render_resilience_expander(view, key)
    with st.expander("報酬×韌性散點", expanded=False):
        _render_scatter_expander(view)
    with st.expander("Greeks 與流動性", expanded=False):
        _render_greeks_expander(view, key)
    with st.expander("📄 Option Chaser 分析報告", expanded=False):
        _render_report_expander(view, key)
    with st.expander("原始資料（當次快照）", expanded=False):
        _render_raw_data_expander(view)
    # T11（#25）：只有真的選中 Spread、且呼叫端有提供歷史資料才顯示——沒
    # 選中候選、或呼叫端不傳 history（不適用持久化劇本的場景）時不顯示這
    # 個區塊，不是「尚無歷史」，是「不適用」。
    if key is not None and history is not None:
        with st.expander("Spread 歷史", expanded=False):
            render_spread_history(history)
