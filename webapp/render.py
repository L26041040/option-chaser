"""v5 spec §5.1：四步渲染純函數，dict 介面，零金融公式。

所有函數皆消費 `option_chaser.store.serialize_result` 產出的 view dict
（及其中的 candidate dict），僅做格式化與座標幾何（顏色色階、Pareto 邊界、
SVG 座標映射），不執行任何金融估值——每個顯示數字都取自已由 service 預算好的
dict 欄位。此模組刻意與 Streamlit 以外的計算解耦，供 quick-analysis GUI 與
工作區詳頁共用。
"""
from __future__ import annotations

import streamlit as st

from option_chaser.glossary import GLOSSARY
from option_chaser.matrix import thumbnail_cells
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
    for j, (iso, lbl) in enumerate(dates):
        suffix = ("*" if lbl == "*" else "") + ("（到期）" if j == n - 1 else "")
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
            '以目前 Mid 價進場的模型報酬率。'
            '<b>粗體</b>價格列為錨點（現價／目標／超標／深跌），其餘為等距內插價。</p>')


def _thumb_html(cand: dict) -> str:
    """4x<=5 colour-block thumbnail, no numbers (spec §4.4). Fixed pixel
    width (`oc-thumb`, see the global <style> block) so the thumbnail column
    doesn't reflow/jump between rows on narrow (mobile) viewports — a CSS-only
    approximation of the mockup's fixed-width thumbnail column."""
    grid = thumbnail_cells(cand["matrix"]["cells"])
    rows = []
    for r in grid:
        cells = "".join(
            f'<span style="display:inline-block;width:9px;height:9px;'
            f'background:{cell_color(v)}"></span>'
            for v in r)
        rows.append(f'<div style="line-height:0">{cells}</div>')
    return f'<div class="oc-thumb">{"".join(rows)}</div>'


def _badge_str(row: dict, selected_key: str | None) -> str:
    parts = []
    badges = row["badges"]
    if "top_return" in badges:
        parts.append('<abbr title="全體合格候選中劇本報酬最高">🚀</abbr>')
    if "top_resilience" in badges:
        parts.append('<abbr title="全體合格候選中情境最壞報酬最高（最強韌性）">🛡️</abbr>')
    if "warning" in badges:
        parts.append('<abbr title="零成交腿／摩擦超標">⚠</abbr>')
    if selected_key is not None and row["candidate"]["candidate_key"] == selected_key:
        parts.append("◀")
    return "".join(parts)


def money(x: float) -> str:
    return f"{x:.2f}"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


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


def all_rows(view: dict) -> list[dict]:
    return [row for g in view["expiry_groups"] for row in g["rows"]]


def find_row(view: dict, key: str | None) -> dict | None:
    if key is None:
        return None
    for row in all_rows(view):
        if row["candidate"]["candidate_key"] == key:
            return row
    return None


def default_key(view: dict) -> str | None:
    return view["default_selection"][1] if view["default_selection"] else None


def _buffer_note(buffer_days: int) -> str:
    """Display-tier copy only (spec §4.4), not a financial computation."""
    if buffer_days < 45:
        return "收斂完全、容錯最低"
    if buffer_days <= 180:
        return "中庸帶"
    return "收斂不完全、容錯最高"


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
             f"{base['target_date']} ｜ {strategies_used or '（無已完成策略）'}")
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


def render_step3(view: dict, key: str | None, state_key: str = "selected_key") -> None:
    st.subheader("Step 3　到期日分組比較")
    if not view["expiry_groups"]:
        st.info("目前沒有可比較的候選。")
        return
    st.markdown('<p style="font-size:12px;color:#666">🚀 最高報酬｜🛡️ 最強韌性｜'
                '⚠ 警示（零成交腿／摩擦超標）｜◀ 目前選中</p>', unsafe_allow_html=True)
    for g in view["expiry_groups"]:
        header = f"{g['expiry']} 到期（緩衝 +{g['buffer_days']} 天）— {_buffer_note(g['buffer_days'])}"
        st.markdown(f"**{esc(header)}**")
        for row in g["rows"]:
            cand = row["candidate"]
            cols = st.columns([0.6, 2.2, 1.6, 1.1, 1.1, 1.1, 1.1, 0.7])
            with cols[0]:
                st.markdown(_badge_str(row, key), unsafe_allow_html=True)
            with cols[1]:
                st.markdown(esc(_candidate_title(row["strategy"], cand)),
                            unsafe_allow_html=True)
            with cols[2]:
                st.markdown(_thumb_html(cand), unsafe_allow_html=True)
            with cols[3]:
                st.markdown(abbr("劇本報酬")
                            + f'<br><span class="oc-num">{pct(cand["baseline_return"])}</span>',
                            unsafe_allow_html=True)
            with cols[4]:
                st.markdown(abbr("情境最壞")
                            + f'<br><span class="oc-num">{pct(cand["scenario_vector"]["worst_return"])}</span>',
                            unsafe_allow_html=True)
            with cols[5]:
                st.markdown(abbr("不漲保留率")
                            + f'<br><span class="oc-num">{pct(cand["retention"])}</span>',
                            unsafe_allow_html=True)
            with cols[6]:
                fr_mark = " ⚠" if cand["friction"] > 0.25 else ""
                st.markdown(abbr("成交摩擦")
                            + f'<br><span class="oc-num">{pct(min(cand["friction"], 9.99))}</span>{fr_mark}',
                            unsafe_allow_html=True)
            with cols[7]:
                if st.button("選看", key=f"sel-{cand['candidate_key']}"):
                    st.session_state[state_key] = cand["candidate_key"]
                    st.rerun()
        if g["hidden_count"] > 0:
            st.caption(f"＋此到期日其他 {g['hidden_count']} 個候選")
    if view["hidden_expiries"]:
        st.caption(f"另有 {len(view['hidden_expiries'])} 個到期日未展示。")


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


def _scatter_svg(all_pairs, badge_of) -> str:
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
        mark = badge_of(cand["candidate_key"])
        svg.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r:.1f}" '
                    f'fill="{color}" fill-opacity="{opacity}" stroke="#333" stroke-width="0.5">'
                    f'<title>{STRATEGY_LABELS[s]} {pct(x)}/{pct(y)}</title></circle>')
        if mark:
            svg.append(f'<text x="{px(x):.1f}" y="{py(y) - 7:.1f}" '
                       f'text-anchor="middle">{mark}</text>')
    svg.append("</svg>")
    return "".join(svg)


def _render_scatter_expander(view: dict) -> None:
    all_pairs = [(r["strategy"], cand) for r in view["results"] if r["status"] == "ok"
                 for cand in r["expiry_best"]]
    if not all_pairs:
        st.info("目前沒有可比較的候選。")
        return
    badge_map: dict[str, str] = {}
    for row in all_rows(view):
        marks = ""
        if "top_return" in row["badges"]:
            marks += "🚀"
        if "top_resilience" in row["badges"]:
            marks += "🛡️"
        if marks:
            badge_map[row["candidate"]["candidate_key"]] = marks
    st.markdown('<div style="overflow-x:auto">' +
                _scatter_svg(all_pairs, lambda k: badge_map.get(k, "")) +
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
    lines.append(f"**{abbr('成交摩擦')}**："
                 f"{pct(min(cand['friction'], 9.99))}（${cand['friction_amount']:.2f}/股）")
    lines.append(f"**30天純時間衰減**：{pct(cand['decay_30d_return'])}"
                 "（S=現價、IV 不變、今日+30天估值）")
    st.markdown(esc("\n\n".join(lines)), unsafe_allow_html=True)

    res = next((r for r in view["results"] if r["strategy"] == row["strategy"]), None)
    if res is not None and res["report_text"]:
        st.code(res["report_text"], language=None)


def render_step4(view: dict, key: str | None) -> None:
    st.subheader("Step 4　進階區")
    with st.expander("韌性與壓力情境", expanded=False):
        _render_resilience_expander(view, key)
    with st.expander("報酬×韌性散點", expanded=False):
        _render_scatter_expander(view)
    with st.expander("Greeks 與流動性", expanded=False):
        _render_greeks_expander(view, key)
