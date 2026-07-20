"""Option Chaser Web GUI（Streamlit）。所有金融計算一律經 option_chaser.service。

v4 spec §4: four-step flow (chips -> single heatmap -> grouped comparison ->
advanced expanders). GUI computes NO financial formulas — every displayed
number comes from service-produced CandidateView/ScenarioVector fields; the
few exceptions (bold-anchor detection, buffer-day copy tier, Pareto frontier
selection, SVG coordinate scaling, completion-curve price labels as a plain
linear read-out of already-known spot/target) are presentation-only per spec
§4.2/§4.4/§4.5 and are called out inline.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import streamlit as st

from option_chaser import service
from option_chaser.glossary import GLOSSARY
from option_chaser.matrix import thumbnail_cells
from option_chaser.models import AnalysisParams, FetchError, ParamError
from option_chaser.report import STRATEGY_LABELS
from option_chaser.valuation import SpreadValuation

STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
DEFAULT_CHECKED = {"long-call", "bull-call-spread"}
STRATEGY_COLOR = {
    "long-call": "#1f77b4", "bull-call-spread": "#2ca02c",
    "long-put": "#d62728", "bear-put-spread": "#9467bd",
}


def _esc(text: str) -> str:
    """v3.1/v4 spec §4.7: escape '$' so st.markdown never triggers LaTeX."""
    return text.replace("$", "\\$")


def _abbr(term: str) -> str:
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


def heatmap_html(mv: service.MatrixView) -> str:
    """v4 spec §4.2/§4.3: bold rows are exactly those whose price_axis label is
    non-empty (spot/target/overshoot/adverse) — GUI reads the label, it never
    recomputes the anchor prices itself."""
    n = len(mv.dates)
    head_cells = []
    for j, (iso, lbl) in enumerate(mv.dates):
        suffix = ("*" if lbl == "*" else "") + ("（到期）" if j == n - 1 else "")
        head_cells.append(
            f'<th style="padding:4px 8px;white-space:nowrap">{iso[5:7]}/{iso[8:10]}{suffix}</th>')
    rows = []
    for i in range(len(mv.prices) - 1, -1, -1):
        price, plabel = mv.prices[i]
        cells = "".join(
            f'<td style="background:{cell_color(v)};color:#111;text-align:right;'
            f'padding:4px 8px">{v * 100:+.0f}%</td>'
            for v in mv.cells[i])
        price_text = f"{price:.2f}{_price_tag(plabel)}"
        if plabel:
            price_text = f"<b>{price_text}</b>"
        rows.append(
            f'<tr><td style="padding:4px 8px;white-space:nowrap">'
            f'{price_text}</td>{cells}</tr>')
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;'
            'font-family:monospace;font-size:13px">'
            f'<tr><th style="padding:4px 8px">價格</th>{"".join(head_cells)}</tr>'
            + "".join(rows) + "</table></div>"
            '<p style="font-size:12px;color:#666">此圖顯示在不同標的價格與日期下，'
            '以目前 Mid 價進場的模型報酬率。'
            '<b>粗體</b>價格列為錨點（現價／目標／超標／深跌），其餘為等距內插價。</p>')


def _thumb_html(cv) -> str:
    """4x<=5 colour-block thumbnail, no numbers (spec §4.4)."""
    grid = thumbnail_cells(cv.matrix.cells)
    rows = []
    for r in grid:
        cells = "".join(
            f'<span style="display:inline-block;width:9px;height:9px;'
            f'background:{cell_color(v)}"></span>'
            for v in r)
        rows.append(f'<div style="line-height:0">{cells}</div>')
    return f'<div style="display:inline-block">{"".join(rows)}</div>'


def _badge_str(row, selected_key: str | None) -> str:
    parts = []
    if "top_return" in row.badges:
        parts.append('<abbr title="全體合格候選中劇本報酬最高">🚀</abbr>')
    if "top_resilience" in row.badges:
        parts.append('<abbr title="全體合格候選中情境最壞報酬最高（最強韌性）">🛡️</abbr>')
    if "warning" in row.badges:
        parts.append('<abbr title="零成交腿／摩擦超標">⚠</abbr>')
    if selected_key is not None and service.candidate_key(row.candidate) == selected_key:
        parts.append("◀")
    return "".join(parts)


def run_analysis(request, progress):
    return service.run(request, progress)


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _mid_cost(strategy: str, cv) -> float:
    v = cv.valuation
    return v.net_mid if isinstance(v, SpreadValuation) else v.mid


def _net_delta(cv) -> float:
    v = cv.valuation
    return v.net_delta if isinstance(v, SpreadValuation) else v.delta


def _candidate_label(strategy: str, cv) -> str:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        return f"買 {v.long_leg.strike:g} / 賣 {v.short_leg.strike:g}"
    return f"K={v.contract.strike:g}"


_STRATEGY_ABBR_TERM = {"bull-call-spread": "BCS", "bear-put-spread": "BPS"}


def _strategy_title(strategy: str) -> str:
    term = _STRATEGY_ABBR_TERM.get(strategy)
    if term:
        return _abbr(term)
    return STRATEGY_LABELS[strategy]


def _candidate_title(strategy: str, cv) -> str:
    return f"{_strategy_title(strategy)} {_candidate_label(strategy, cv)}"


def _all_rows(result):
    return [row for g in result.expiry_groups for row in g.rows]


def _find_row(result, key: str | None):
    if key is None:
        return None
    for row in _all_rows(result):
        if service.candidate_key(row.candidate) == key:
            return row
    return None


def _buffer_note(buffer_days: int) -> str:
    """Display-tier copy only (spec §4.4), not a financial computation."""
    if buffer_days < 45:
        return "收斂完全、容錯最低"
    if buffer_days <= 180:
        return "中庸帶"
    return "收斂不完全、容錯最高"


def _selected_key(result) -> str | None:
    if "selected_key" not in st.session_state:
        st.session_state["selected_key"] = (
            result.default_selection[1] if result.default_selection else None)
    key = st.session_state["selected_key"]
    if _find_row(result, key) is None and result.default_selection:
        key = result.default_selection[1]
        st.session_state["selected_key"] = key
    return key


def _render_summary(result) -> None:
    """Step 1 chips (spec §4.1): summary line + any per-strategy skip/empty
    notices. The edit form itself is rendered separately by the main script
    (inside the '✎ 修改劇本' expander) so its submit button is visible to the
    submit-dispatch logic on the SAME rerun it is clicked."""
    m = result.meta
    base = result.request.base_params
    strategies_used = "、".join(
        STRATEGY_LABELS[r.strategy] for r in result.results if r.status == "ok")
    pct = (base.target_price - m.spot) / m.spot * 100
    chips = (f"**{m.symbol}** 劇本 ｜ 現價 ${_money(m.spot)} ｜ "
             f"目標 ${_money(base.target_price)}（{pct:+.1f}%）｜ "
             f"{base.target_date} ｜ {strategies_used or '（無已完成策略）'}")
    st.markdown(_esc(chips))
    for r in result.results:
        if r.status != "ok":
            st.info(f"{STRATEGY_LABELS[r.strategy]}：{r.message}")


def _scenario_form_fields():
    st.text_input("標的", key="symbol", placeholder="TLT")
    st.number_input("目標價位", key="target_price",
                    min_value=0.01, value=100.0, step=1.0)
    st.date_input("預計到達時間", key="target_date",
                  value=date.today() + timedelta(days=180),
                  min_value=date.today() + timedelta(days=1))
    for s in STRATEGY_ORDER:
        st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}", value=(s in DEFAULT_CHECKED))


def _render_step2(result, key: str | None) -> None:
    st.subheader("Step 2　劇本主圖")
    row = _find_row(result, key)
    if row is None:
        st.info("目前沒有可顯示的候選（所有策略皆未產生合格合約）。")
        return
    st.markdown(_esc(f"**{_candidate_title(row.strategy, row.candidate)}**"),
                unsafe_allow_html=True)
    st.markdown(heatmap_html(row.candidate.matrix), unsafe_allow_html=True)


def _render_step3(result, key: str | None) -> None:
    st.subheader("Step 3　到期日分組比較")
    if not result.expiry_groups:
        st.info("目前沒有可比較的候選。")
        return
    st.markdown('<p style="font-size:12px;color:#666">🚀 最高報酬｜🛡️ 最強韌性｜'
                '⚠ 警示（零成交腿／摩擦超標）｜◀ 目前選中</p>', unsafe_allow_html=True)
    for g in result.expiry_groups:
        header = f"{g.expiry} 到期（緩衝 +{g.buffer_days} 天）— {_buffer_note(g.buffer_days)}"
        st.markdown(f"**{_esc(header)}**")
        for row in g.rows:
            cv = row.candidate
            cols = st.columns([0.6, 2.2, 1.6, 1.1, 1.1, 1.1, 1.1, 0.7])
            with cols[0]:
                st.markdown(_badge_str(row, key), unsafe_allow_html=True)
            with cols[1]:
                st.markdown(_esc(_candidate_title(row.strategy, cv)),
                            unsafe_allow_html=True)
            with cols[2]:
                st.markdown(_thumb_html(cv), unsafe_allow_html=True)
            with cols[3]:
                st.markdown(_abbr("劇本報酬") + f"<br>{_pct(cv.baseline_return)}",
                            unsafe_allow_html=True)
            with cols[4]:
                st.markdown(_abbr("情境最壞") + f"<br>{_pct(cv.scenario.worst_return)}",
                            unsafe_allow_html=True)
            with cols[5]:
                st.markdown(_abbr("不漲保留率") + f"<br>{_pct(cv.retention)}",
                            unsafe_allow_html=True)
            with cols[6]:
                fr_mark = " ⚠" if cv.friction > 0.25 else ""
                st.markdown(_abbr("成交摩擦") + f"<br>{_pct(min(cv.friction, 9.99))}{fr_mark}",
                            unsafe_allow_html=True)
            with cols[7]:
                if st.button("選看", key=f"sel-{service.candidate_key(cv)}"):
                    st.session_state["selected_key"] = service.candidate_key(cv)
                    st.rerun()
        if g.hidden_count > 0:
            st.caption(f"＋此到期日其他 {g.hidden_count} 個候選")
    if result.hidden_expiries:
        st.caption(f"另有 {len(result.hidden_expiries)} 個到期日未展示。")


def _render_resilience_expander(result, key: str | None) -> None:
    row = _find_row(result, key)
    if row is None:
        st.info("無選中候選。")
        return
    cv = row.candidate
    from option_chaser.scenarios import SCENARIO_NAMES
    st.markdown(f"**{_esc(_candidate_title(row.strategy, cv))}** 的 7 情境向量")
    lines = ["|情境|報酬|", "|---|---|"]
    for code, ret in cv.scenario.entries:
        is_worst = code == cv.scenario.worst_code
        mark = " ◀ 情境最壞" if is_worst else ""
        cell = f"{_pct(ret)}{mark}"
        if is_worst:
            cell = f'<span style="background:#f8d7da">{cell}</span>'
        lines.append(f"|{code} {SCENARIO_NAMES[code]}|{cell}|")
    st.markdown("\n".join(lines), unsafe_allow_html=True)

    # Presentation-only linear read-out: for k in {0,.25,.5,.75,1} the price is
    # exactly spot + k*(target-spot) (no clamping ever applies on this range,
    # since it stays between two already-known, already-displayed numbers).
    # This mirrors the k=1==target identity already guaranteed by service.
    spot = result.meta.spot
    target = result.request.base_params.target_price
    curve_lines = ["", "**完成度報酬曲線**", "|完成度|對應價位|報酬|", "|---|---|---|"]
    for k, ret in cv.completion_curve:
        price_at_k = spot + k * (target - spot)
        curve_lines.append(f"|{int(k * 100)}%|${_money(price_at_k)}|{_pct(ret)}|")
    st.markdown(_esc("\n".join(curve_lines)))

    if cv.completion_threshold is None:
        thr = "— ⚠劇本全成仍不保本"
    elif cv.completion_threshold <= 0:
        thr = "0%（已保本）"
    else:
        thr = (f"完成 {_pct(cv.completion_threshold)}"
               f"（{_abbr('保本價')} ${_money(cv.breakeven_at_target)}，基準IV）")
    st.markdown(_esc(f"**完成度門檻**：{thr}"), unsafe_allow_html=True)


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
    points = [(cv.scenario.worst_return, cv.baseline_return, s, cv) for s, cv in all_pairs]
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    costs = [_mid_cost(s, cv) for s, cv in all_pairs]
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
    for x, y, s, cv in points:
        dominated = (x, y) not in frontier_set
        color = STRATEGY_COLOR.get(s, "#888888")
        opacity = 0.35 if dominated else 0.9
        r = radius(_mid_cost(s, cv))
        mark = badge_of(service.candidate_key(cv))
        svg.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="{r:.1f}" '
                    f'fill="{color}" fill-opacity="{opacity}" stroke="#333" stroke-width="0.5">'
                    f'<title>{STRATEGY_LABELS[s]} {_pct(x)}/{_pct(y)}</title></circle>')
        if mark:
            svg.append(f'<text x="{px(x):.1f}" y="{py(y) - 7:.1f}" '
                       f'text-anchor="middle">{mark}</text>')
    svg.append("</svg>")
    return "".join(svg)


def _render_scatter_expander(result) -> None:
    all_pairs = [(res.strategy, cv) for res in result.results if res.status == "ok"
                 for cv in res.expiry_best]
    if not all_pairs:
        st.info("目前沒有可比較的候選。")
        return
    badge_map: dict[str, str] = {}
    for row in _all_rows(result):
        marks = ""
        if "top_return" in row.badges:
            marks += "🚀"
        if "top_resilience" in row.badges:
            marks += "🛡️"
        if marks:
            badge_map[service.candidate_key(row.candidate)] = marks
    st.markdown('<div style="overflow-x:auto">' +
                _scatter_svg(all_pairs, lambda k: badge_map.get(k, "")) +
                "</div>", unsafe_allow_html=True)
    legend = "｜".join(f'<span style="color:{c}">●</span> {STRATEGY_LABELS[s]}'
                       for s, c in STRATEGY_COLOR.items())
    st.markdown(legend + "　點大小 ~ Mid 成本；淡色點為 Pareto 被支配點。",
                unsafe_allow_html=True)


def _render_greeks_expander(result, key: str | None) -> None:
    row = _find_row(result, key)
    if row is None:
        st.info("無選中候選。")
        return
    cv = row.candidate
    v = cv.valuation
    lines = [f"**Net {_abbr('Delta')}**：{_net_delta(cv):.2f}"]
    if isinstance(v, SpreadValuation):
        lines[-1] += "（價差：兩腿相減，方向語意較弱，僅供參考）"
    lines.append(f"**Θ日耗率**：{_pct(cv.theta_day_rate)}"
                 "（隨到期接近會加速流失，此為目前速率）")
    lines.append(f"**{_abbr('Vega')}/1pt**：{_pct(cv.vega_per_pt)}")
    if isinstance(v, SpreadValuation):
        lines.append(f"買腿 OI/Volume：{v.long_leg.open_interest}/{v.long_leg.volume}")
        lines.append(f"賣腿 OI/Volume：{v.short_leg.open_interest}/{v.short_leg.volume}")
    else:
        lines.append(f"OI/Volume：{v.contract.open_interest}/{v.contract.volume}")
    lines.append(f"**{_abbr('成交摩擦')}**：{_pct(min(cv.friction, 9.99))}")
    lines.append(f"**30天純時間衰減**：{_pct(cv.decay_30d_return)}"
                 "（S=現價、IV 不變、今日+30天估值）")
    st.markdown(_esc("\n\n".join(lines)), unsafe_allow_html=True)

    res = next((r for r in result.results if r.strategy == row.strategy), None)
    if res is not None and res.report_text:
        st.code(res.report_text, language=None)


def _render_step4(result, key: str | None) -> None:
    st.subheader("Step 4　進階區")
    with st.expander("韌性與壓力情境", expanded=False):
        _render_resilience_expander(result, key)
    with st.expander("報酬×韌性散點", expanded=False):
        _render_scatter_expander(result)
    with st.expander("Greeks 與流動性", expanded=False):
        _render_greeks_expander(result, key)


st.set_page_config(page_title="Option Chaser", layout="wide")
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
    _render_summary(_result)
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
        st.rerun()   # next run renders the form with disabled=True, THEN analyzes

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()       # re-enable the button and show results/errors

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])

# Step 2/3/4 (spec §4.2-4.5): render against the LATEST result in session
# state (a fresh analysis may have just replaced it above).
if "result" in st.session_state:
    _final_result = st.session_state["result"]
    _key = _selected_key(_final_result)
    _render_step2(_final_result, _key)
    _render_step3(_final_result, _key)
    _render_step4(_final_result, _key)
