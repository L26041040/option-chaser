# webapp/components.py
"""v6 spec §2.2/§4: 卡片元件庫——純函數，輸出 HTML 字串，吃 dict，零金融公式。
與 render.py 同紅線：每個顯示數字皆直接取自已由 store.serialize_result 預算好的
dict 欄位；本模組僅格式化、條件分支（單腿 vs Spread）與既有 status/render 工具函數
的組合呼叫。

安全紅線：使用者輸入（scenario symbol／notes）一律先經 `html.escape()` 才可注入
HTML 樣板。本模組每個函式回傳完整一段以區塊層級標籤（`<div>`/`<span>`...）開頭
的 HTML 字串，經呼叫端 `st.markdown(..., unsafe_allow_html=True)` 整段輸出——
依 CommonMark HTML block 規則，這整段內容不會再被當作行內 markdown 解析，故其中
的裸 `$` 不會被誤判為 LaTeX 定界符，也不需要（也不可以）套用 `render.esc()`；
套用只會讓字面上的反斜線「\\$」原樣顯示，而非還原成 `$`（render.esc() 僅適用於
純 markdown 文字路徑，見 render.py 內其餘呼叫點）。v1 舊 result 檔缺 v2 新欄時
以 `.get()` 降級讀取，顯示 `—` 與 `status.LEGACY_RESULT_MESSAGE`，不得 KeyError。
"""
from __future__ import annotations

import html as html_lib

from option_chaser.report import STRATEGY_LABELS
from webapp.render import money, pct
from webapp.status import (EMPTY_CANDIDATE_MESSAGE,  # noqa: F401 (re-export for views)
                           LEGACY_RESULT_MESSAGE, derive_result_status,
                           is_legacy_schema)

_STATUS_PILL_CLASS = {
    "Active": "oc-pill-active", "Reached": "oc-pill-reached",
    "Expired": "oc-pill-expired", "Invalidated": "oc-pill-invalidated",
}
_STATUS_EMOJI = {"Active": "🟢", "Reached": "🏁", "Expired": "⌛", "Invalidated": "❌"}
_QUALITY_CLASS = {"正常": "oc-badge-ok", "報價不足": "oc-badge-warn", "歷史資料": "oc-badge-stale"}
_QUALITY_EMOJI = {"正常": "✓", "報價不足": "⚠", "歷史資料": "🕒"}


def _h(text: str) -> str:
    """HTML-escape user-controlled text before interpolating into a template
    (symbol/notes) — distinct from esc(), which only guards '$' against LaTeX."""
    return html_lib.escape(text, quote=True)


def status_pill(scenario_status: str) -> str:
    cls = _STATUS_PILL_CLASS[scenario_status]
    emoji = _STATUS_EMOJI[scenario_status]
    return f'<span class="oc-pill {cls}">{emoji} {scenario_status}</span>'


def quality_badge(tone: str) -> str:
    cls = _QUALITY_CLASS[tone]
    emoji = _QUALITY_EMOJI[tone]
    return f'<span class="{cls}">{emoji} {tone}</span>'


def metric_tile(label: str, value: str) -> str:
    return (f'<div class="oc-metric-tile"><div class="oc-metric-label">{_h(label)}</div>'
           f'<div class="oc-metric-value oc-num">{_h(value)}</div></div>')


def _default_candidate(summary: dict | None) -> dict | None:
    if not summary or not summary["default_selection"]:
        return None
    key = summary["default_selection"][1]
    return next(
        (
            row["candidate"]
            for group in summary["expiry_groups"]
            for row in group["rows"]
            if row["candidate"]["candidate_key"] == key
        ),
        None,
    )


def _data_quality_label(summary: dict | None) -> str:
    if summary is None:
        return "尚未分析"
    if summary["data_quality"]["all_quotes_filtered"]:
        return "報價不足"
    return "正常"


def _data_source_label(summary: dict | None) -> str:
    if summary is None:
        return "—"
    snapshot = summary["snapshot_ref"]
    fetched_date = str(snapshot["fetched_at"]).split("T", 1)[0]
    source = snapshot.get("source") or summary.get("meta", {}).get("source") or "來源未標示"
    return f"最近有效快照 · {source} · {fetched_date}"


def scenario_card(sc: dict, summary: dict | None) -> str:
    result_status = derive_result_status(summary)
    cand = _default_candidate(summary)
    direction = "看漲" if sc["direction"] == "bullish" else "看跌"
    spot = f'${money(summary["meta"]["spot"])}' if summary is not None else "—"
    candidate = STRATEGY_LABELS[cand["strategy"]] if cand is not None else result_status
    scenario_return = pct(cand["baseline_return"]) if cand is not None else "—"
    cost = f'${cand["capital_per_contract"]:,.0f}' if cand is not None else "—"
    quality = _data_quality_label(summary)
    quality_cls = _QUALITY_CLASS.get(quality, "oc-badge-stale")

    parts = [
        '<div class="oc-card oc-scenario-list-item">',
        '<div class="oc-scenario-main">',
        f'<div class="oc-scenario-symbol"><span class="oc-field-label">Symbol</span>'
        f'<strong>{_h(sc["symbol"])}</strong></div>',
        f'<div class="oc-scenario-direction">{_h(direction)}</div>',
        f'{status_pill(sc["status"])}',
        '</div>',
        '<div class="oc-scenario-grid">',
        f'<div class="oc-scenario-field"><span>方向</span><strong>{_h(direction)}</strong></div>',
        f'<div class="oc-scenario-field"><span>現價</span><strong class="oc-num">{spot}</strong></div>',
        f'<div class="oc-scenario-field"><span>目標價</span><strong class="oc-num">${money(sc["target_price"])}</strong></div>',
        f'<div class="oc-scenario-field"><span>目標日</span><strong>{_h(str(sc["target_date"]))}</strong></div>',
        f'<div class="oc-scenario-field"><span>狀態</span><strong>{_h(sc["status"])}</strong></div>',
        f'<div class="oc-scenario-field"><span>群組</span><strong>{_h(sc["group_id"])}</strong></div>',
        f'<div class="oc-scenario-field oc-scenario-wide"><span>最新推薦候選</span>'
        f'<strong>{_h(candidate)}</strong></div>',
        f'<div class="oc-scenario-field"><span>劇本報酬</span><strong class="oc-num">{scenario_return}</strong></div>',
        f'<div class="oc-scenario-field"><span>每張或每組成本</span><strong class="oc-num">{cost}</strong></div>',
        f'<div class="oc-scenario-field"><span>資料品質</span><strong class="{quality_cls}">{_h(quality)}</strong></div>',
        f'<div class="oc-scenario-field oc-scenario-wide"><span>資料來源</span>'
        f'<strong>{_h(_data_source_label(summary))}</strong></div>',
        '</div>',
    ]
    if sc["notes"]:
        parts.append(f'<div class="oc-scenario-notes">{_h(sc["notes"])}</div>')
    parts.append('</div>')
    return "".join(parts)


def candidate_card(cand: dict, strategy: str) -> str:
    legs = cand["legs"]
    label = STRATEGY_LABELS[strategy]
    legacy = is_legacy_schema({"schema_version": cand.get("schema_version", 2)}) or (
        "natural_per_contract" not in cand)
    legacy_note = (
        f'<div class="oc-candidate-legacy">{LEGACY_RESULT_MESSAGE}</div>'
        if legacy else ""
    )

    def _fmt_money(key: str) -> str:
        v = cand.get(key)
        return f'${v:,.0f}' if v is not None else "—"

    is_spread = len(legs) == 2
    unit_label = "每組成本" if is_spread else "每張成本"
    natural_unit_label = "Natural 每組" if is_spread else "Natural 每張"
    structure = ""
    quotes = []

    if len(legs) == 1:
        leg = legs[0]
        structure = f'{leg["option_type"].capitalize()} · 履約價 {leg["strike"]:g}'
        quotes = [
            ("Bid", f'${money(leg["bid"])}'),
            ("Mid", f'${money(cand["mid_cost"])}'),
            ("Ask", f'${money(leg["ask"])}'),
        ]
        max_profit_label = "最大獲利無上限" if strategy == "long-call" else "最大獲利"
        max_profit_value = "無上限" if strategy == "long-call" else "—"
        cap_panel = ""
    else:
        long_leg, short_leg = legs
        max_profit_v = cand.get("max_profit_per_contract")
        max_profit_value = f'${max_profit_v:,.0f}' if max_profit_v is not None else "—"
        max_profit_label = "Spread 最大獲利"
        cap_price = cand.get("cap_price")
        # BCS 兩腿皆 call、BPS 兩腿皆 put——讀 leg 實際 option_type，不得硬編 "Call"
        # （spec brief §5.2 明確要求 Bear Put Spread 顯示 Put，先前草稿誤植兩者皆
        # 顯示 Call）。
        opt_label = long_leg["option_type"].capitalize()
        structure = (
            f'買 {long_leg["strike"]:g} {opt_label} · '
            f'賣 {short_leg["strike"]:g} {opt_label}'
        )
        quotes = [
            ("買腿 Bid", f'${money(long_leg["bid"])}'),
            ("買腿 Ask", f'${money(long_leg["ask"])}'),
            ("Net Mid", f'${money(cand["mid_cost"])}'),
            ("賣腿 Bid", f'${money(short_leg["bid"])}'),
            ("賣腿 Ask", f'${money(short_leg["ask"])}'),
        ]
        cap_value = f'${money(cap_price)}' if cap_price is not None else "—"
        cap_panel = (
            '<div class="oc-spread-cap">'
            '<span>Spread 封頂價</span>'
            f'<strong class="oc-num">{cap_value}</strong>'
            '<small>到達此價位後進入最大獲利區</small>'
            '</div>'
        )

    quote_items = "".join(
        '<div class="oc-quote-item">'
        f'<span>{quote_label}</span><strong class="oc-num">{quote_value}</strong>'
        '</div>'
        for quote_label, quote_value in quotes
    )
    expiry = legs[-1]["expiry"]
    return (
        '<article class="oc-card oc-candidate-card">'
        '<header class="oc-candidate-header">'
        '<div><span class="oc-eyebrow">最新推薦候選</span>'
        f'<h3>{label}</h3><p>{structure} · 到期 {expiry}</p></div>'
        '<div class="oc-candidate-return">'
        '<span>劇本報酬</span>'
        f'<strong class="oc-num">{pct(cand["baseline_return"])}</strong>'
        '</div>'
        '</header>'
        '<section class="oc-candidate-quotes">'
        '<div class="oc-section-label">Bid / Mid / Ask <small>每股價格</small></div>'
        f'<div class="oc-quote-grid">{quote_items}</div>'
        '</section>'
        '<div class="oc-candidate-fundamentals">'
        '<section class="oc-candidate-cost">'
        '<div class="oc-section-label">成本</div>'
        '<div class="oc-value-pair">'
        f'<span>{unit_label}</span><strong class="oc-num">${cand["capital_per_contract"]:,.0f}</strong>'
        '</div>'
        '<div class="oc-value-pair oc-value-pair-secondary">'
        f'<span>{natural_unit_label}</span><strong class="oc-num">{_fmt_money("natural_per_contract")}</strong>'
        '</div>'
        '</section>'
        '<section class="oc-candidate-risk">'
        '<div class="oc-section-label">風險與損益邊界</div>'
        '<div class="oc-risk-grid">'
        '<div class="oc-value-pair"><span>最大損失</span>'
        f'<strong class="oc-num">${cand["max_loss_per_contract"]:,.0f}</strong></div>'
        f'<div class="oc-value-pair"><span>{max_profit_label}</span>'
        f'<strong class="oc-num">{max_profit_value}</strong></div>'
        '<div class="oc-value-pair"><span>Breakeven</span>'
        f'<strong class="oc-num">${money(cand["breakeven"])}</strong></div>'
        '</div>'
        '</section>'
        f'{cap_panel}'
        '</div>'
        f'{legacy_note}'
        '</article>'
    )


def milestone_rail(group: dict, scenarios_by_id: dict, views_by_id: dict) -> str:
    """v6 spec §3.5：垂直里程碑軌。group 為 store.rebuild_groups 產出的單一群組 dict；
    scenarios_by_id/views_by_id 為呼叫端預先聚合的 {scenario_id: Scenario|view dict}。"""
    parts = [f'<div class="oc-card"><b>{_h(group["id"])}</b>（{len(group["members"])} 個里程碑）']
    for mid in group["members"]:
        sc = scenarios_by_id[mid]
        view = views_by_id.get(mid)
        cls = "oc-rail-node"
        line = (f'{status_pill(sc.status)} {sc.target_date} ${money(sc.target_price)}')
        if view is not None and view["default_selection"]:
            key = view["default_selection"][1]
            cand = next((row["candidate"] for g in view["expiry_groups"]
                        for row in g["rows"] if row["candidate"]["candidate_key"] == key), None)
            if cand is not None:
                line += f' ｜ {STRATEGY_LABELS[cand["strategy"]]} ｜ 劇本報酬 {pct(cand["baseline_return"])}'
        parts.append(f'<div class="{cls}">{line}</div>')
    same_snapshot = len({views_by_id[m]["snapshot_ref"]["path"] for m in group["members"]
                         if m in views_by_id}) == 1 and len(views_by_id) >= 2
    if same_snapshot:
        parts.append('<div class="oc-badge-ok">✓ 同一資料快照</div>')
    parts.append('</div>')
    return "".join(parts)
