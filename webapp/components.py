# webapp/components.py
"""v6 spec §2.2/§4: 卡片元件庫——純函數，輸出 HTML 字串，吃 dict，零金融公式。
與 render.py 同紅線：每個顯示數字皆直接取自已由 store.serialize_result 預算好的
dict 欄位；本模組僅格式化、條件分支（單腿 vs Spread）與既有 status/render 工具函數
的組合呼叫。

安全紅線：使用者輸入（scenario symbol／notes）一律先經 `html.escape()` 才可注入
HTML 樣板；本模組所有回傳字串在 return 前一律經 `esc()`（$ 轉義，見 render.py）
處理，呼叫端不需重複跳脫。v1 舊 result 檔缺 v2 新欄時以 `.get()` 降級讀取，顯示
`—` 與 `status.LEGACY_RESULT_MESSAGE`，不得 KeyError。
"""
from __future__ import annotations

import html as html_lib

from option_chaser.report import STRATEGY_LABELS
from webapp.render import esc, money, pct
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
    return esc(f'<span class="oc-pill {cls}">{emoji} {scenario_status}</span>')


def quality_badge(tone: str) -> str:
    cls = _QUALITY_CLASS[tone]
    emoji = _QUALITY_EMOJI[tone]
    return esc(f'<span class="{cls}">{emoji} {tone}</span>')


def metric_tile(label: str, value: str) -> str:
    return esc(f'<div class="oc-metric-tile"><div class="oc-metric-label">{_h(label)}</div>'
              f'<div class="oc-metric-value oc-num">{_h(value)}</div></div>')


def scenario_card(sc: dict, summary: dict | None) -> str:
    result_status = derive_result_status(summary)
    parts = [f'<div class="oc-card"><b>{_h(sc["symbol"])}</b> '
            f'{"看漲" if sc["direction"] == "bullish" else "看跌"} '
            f'{status_pill(sc["status"])}<br>'
            f'目標 ${money(sc["target_price"])} ｜ {sc["target_date"]} ｜ {_h(sc["group_id"])}<br>']
    if summary is None:
        parts.append(f'<span class="oc-badge-stale">{result_status}</span>')
    else:
        cand = None
        if summary["default_selection"]:
            key = summary["default_selection"][1]
            for g in summary["expiry_groups"]:
                for row in g["rows"]:
                    if row["candidate"]["candidate_key"] == key:
                        cand = row["candidate"]
                        break
        if cand is not None:
            parts.append(f'{STRATEGY_LABELS[cand["strategy"]]}｜每張/組 ≈ '
                        f'${cand["capital_per_contract"]:.0f}｜劇本報酬 {pct(cand["baseline_return"])}')
        else:
            parts.append(f'<span class="oc-badge-warn">{result_status}</span>')
    if sc["notes"]:
        parts.append(f'<div style="font-size:12px;color:#6b7280">{_h(sc["notes"])}</div>')
    parts.append('</div>')
    return esc("".join(parts))


def candidate_card(cand: dict, strategy: str) -> str:
    legs = cand["legs"]
    label = STRATEGY_LABELS[strategy]
    legacy = is_legacy_schema({"schema_version": cand.get("schema_version", 2)}) or (
        "natural_per_contract" not in cand)
    legacy_note = f'<div style="font-size:12px;color:#b45309">{LEGACY_RESULT_MESSAGE}</div>' if legacy else ""

    def _fmt_money(key: str) -> str:
        v = cand.get(key)
        return f'${v:,.0f}' if v is not None else "—"

    if len(legs) == 1:
        leg = legs[0]
        lines = [
            f'<b>{esc(label)}</b> ｜ 履約價 {leg["strike"]:g} ｜ 到期 {leg["expiry"]}',
            f'Bid ${money(leg["bid"])} ｜ Mid ${money(cand["mid_cost"])} ｜ Ask ${money(leg["ask"])}',
            f'Mid 每張 ≈ ${cand["capital_per_contract"]:.0f} ｜ '
            f'Natural 每張 ≈ {_fmt_money("natural_per_contract")}',
            f'最大損失 ≈ ${cand["max_loss_per_contract"]:.0f} ｜ '
            f'Breakeven ${money(cand["breakeven"])} ｜ 劇本報酬 {pct(cand["baseline_return"])}',
        ]
    else:
        long_leg, short_leg = legs
        max_profit_v = cand.get("max_profit_per_contract")
        max_profit_txt = (f'${max_profit_v:,.0f}' if max_profit_v is not None
                         else ("無上限" if "max_profit_per_contract" in cand else "—"))
        cap_price = cand.get("cap_price")
        cap_txt = f'{cap_price:g}' if cap_price is not None else "—"
        # BCS 兩腿皆 call、BPS 兩腿皆 put——讀 leg 實際 option_type，不得硬編 "Call"
        # （spec brief §5.2 明確要求 Bear Put Spread 顯示 Put，先前草稿誤植兩者皆
        # 顯示 Call）。
        opt_label = long_leg["option_type"].capitalize()
        lines = [
            f'<b>{esc(label)}</b> ｜ 買 {long_leg["strike"]:g} {opt_label} ／ '
            f'賣 {short_leg["strike"]:g} {opt_label} ｜ 到期 {short_leg["expiry"]}',
            f'Net Mid Debit ${money(cand["mid_cost"])}／股 ｜ 每組 ≈ ${cand["capital_per_contract"]:.0f}',
            f'Natural Debit ${money(cand["natural_cost"])}／股 ｜ '
            f'Natural 每組 ≈ {_fmt_money("natural_per_contract")}',
            f'最大損失 ≈ ${cand["max_loss_per_contract"]:.0f} ｜ 最大獲利 ≈ {max_profit_txt} ｜ '
            f'Breakeven ${money(cand["breakeven"])} ｜ 獲利封頂價 {cap_txt}',
        ]
    return esc('<div class="oc-card">' + "<br>".join(lines) + legacy_note + '</div>')


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
    return esc("".join(parts))
