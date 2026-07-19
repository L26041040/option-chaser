# option_chaser/report.py
"""Deterministic plain-text report (spec §7). No box-drawing characters."""
from __future__ import annotations

from datetime import date
from datetime import date as _date

from .matrix import date_axis, matrix_lines, price_axis
from .models import AnalysisParams, ChainSnapshot, FilterReport, leg_option_type
from .ranking import BAND_LABELS, BAND_ORDER, build_reasons
from .valuation import ContractValuation, guidance_judgments, scenario_leg_value, spread_scenario_value

STRATEGY_LABELS = {
    "long-call": "Long Call",
    "long-put": "Long Put",
    "bull-call-spread": "Bull Call Spread",
    "bear-put-spread": "Bear Put Spread",
}


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _shift_name(shift: float) -> str:
    return "IV 不變" if shift == 0.0 else f"IV {shift * 100:+g}%"


def _val_line(name: str, val: float, cost: float) -> str:
    """spec §7: each scenario line = 估值 + 損益 + 報酬率 (per-share and per-contract)."""
    pnl = val - cost
    return (
        f"- {name}: ${_money(val)}（${val * 100:.0f}/張）"
        f"損益 {pnl:+.2f}（{pnl * 100:+.0f}/張）-> {_pct(pnl / cost)}"
    )


def _header_lines(snap: ChainSnapshot, p: AnalysisParams, today: date) -> list[str]:
    bands = p.delta_bands
    return [
        "OPTION CHASER 報告",
        "",
        "[使用者假設]",
        f"- 策略: {STRATEGY_LABELS[p.strategy]}",
        f"- 劇本: {p.target_date} 到達 ${_money(p.target_price)}",
        f"- 限制: 到期日 >= 劇本日"
        + (f"; 到期日 >= {p.min_expiry}" if p.min_expiry else ""),
        f"- 最低要求報酬率: {_pct(p.min_return)}",
        "",
        "[市場資料]",
        f"- 資料時間: {snap.fetched_at}（來源 {snap.source}，可能延遲）",
        f"- {snap.symbol} 現價: ${_money(snap.spot)}（分析基準日 {today.isoformat()}）",
        "",
        "[模型假設]",
        f"- 無風險利率 {_pct(p.rate)}、無股利調整、Black-Scholes 歐式近似",
        f"- IV 情境: {', '.join(_shift_name(s) for s in p.iv_shifts)}",
        f"- Delta 分級門檻: {bands[0]:g} / {bands[1]:g}（實務慣例級距）",
    ]


def _filter_lines(freport: FilterReport, p: AnalysisParams) -> list[str]:
    side = "Call 側" if leg_option_type(p.strategy) == "call" else "Put 側"
    lines = ["", "[過濾統計]", f"- 掃描合約（{side}）: {freport.total} 張"]
    for s in freport.stages:
        lines.append(f"- {s.label}刷掉: {s.removed}")
    lines.append(f"- 合格: {freport.passed} 張")
    return lines


def _candidate_lines(
    v: ContractValuation, idx: int, band: str,
    ranked: dict[str, list[ContractValuation]],
    snap: ChainSnapshot, n_qualified: int, p: AnalysisParams,
) -> list[str]:
    c = v.contract
    word = "高於" if c.option_type == "call" else "低於"
    lines = [
        "",
        f"{idx}) {BAND_LABELS[band]}: Strike ${_money(c.strike)} / {c.expiry} 到期",
        f"- 現在買入: Bid ${_money(c.bid)}（${c.bid * 100:.0f}/張）"
        f" / Mid ${_money(v.mid)}（${v.mid * 100:.0f}/張）"
        f" / Ask ${_money(c.ask)}（${c.ask * 100:.0f}/張）IV {_pct_iv(c.implied_volatility)}",
        f"- Delta {v.delta:.2f} / Theta {v.theta_per_day:.3f}每天 / Vega {v.vega_per_pct:.2f}",
        f"- Breakeven: ${_money(v.breakeven)}（{word}現價 {_pct(v.breakeven_vs_spot)}；"
        f"對目標價緩衝 {_pct(v.breakeven_vs_target)}）",
        f"- Lambda 有效槓桿: {v.effective_leverage:.1f}x",
    ]
    if c.volume == 0:
        lines.append("- 警示: 今日無成交，報價新鮮度存疑")
    lines.append("")
    lines.append("劇本成立時:")
    lines.append(_val_line("保守底線", v.floor_value, v.mid))
    for shift, val in v.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, v.mid))
    lines.append(
        f"- 最差進場（Ask）基準報酬率: {_pct((v.baseline_value - c.ask) / c.ask)}"
    )
    lines.append("")
    lines.append("買價指引:")
    lines.append(f"- L1 硬上限（劇本內在價值）: ${_money(v.l1)}（${v.l1 * 100:.0f}/張）")
    lines.append(f"- L2 保守上限（最保守 IV 情境）: ${_money(v.l2)}（${v.l2 * 100:.0f}/張）")
    lines.append(
        f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: "
        f"${_money(v.l3)}（${v.l3 * 100:.0f}/張）"
    )
    judgments = guidance_judgments(v, p)
    if judgments:
        for m in judgments:
            lines.append(f"- 警示: {m}")
    else:
        lines.append("- 目前 Ask 低於全部三層天花板")
    pros, cons = build_reasons(v, band, ranked, snap.spot, n_qualified, p)
    lines.append("")
    lines.append("評語:")
    for s in pros:
        lines.append(f"- 優點: {s}")
    for s in cons:
        lines.append(f"- 代價: {s}")
    return lines


def _pct_iv(iv: float) -> str:
    return f"{iv * 100:.0f}%"


def _matrix_block(value_fn, cost, spot, p, today, expiry) -> list[str]:
    prices = price_axis(spot, p.target_price)
    dates = date_axis(today, _date.fromisoformat(p.target_date), expiry)
    return ["", "P/L 矩陣（報酬率，Mid 進場）:"] + matrix_lines(value_fn, cost, prices, dates)


def _footer_lines(p: AnalysisParams) -> list[str]:
    return [
        "",
        "[尾註]",
        "- 估值: Black-Scholes 歐式 call，N(x) = 0.5*(1+erf(x/sqrt(2)))，T = 日曆日/365",
        "- Put: P = K·e^(-rT)·N(-d2) - S·N(-d1)；估值鉗制 value = max(BS, 內在價值, 0)",
        "- T <= 0 時以內在價值 max(S-K, 0) 取代 BS",
        "- 保守底線 = max(目標價 - Strike, 0)（無套利下限）",
        "- IV 情境: sigma' = sigma * (1 + shift)",
        "- 買價天花板: L1 = max(目標價-Strike, 0); L2 = BS(最保守 IV 情境); L3 = 基準估值/(1+min-return)",
        "- 價差: V = 長腿 − 短腿，鉗制至 [0, 寬度]；價差無 L1，L2 = 全部 IV 情境最小值（情境包絡，非無套利下限）",
        "- Breakeven = Strike + Mid（到期持有觀點，提前平倉不適用）",
        "- Lambda = Delta * 現價 / Mid（低權利金合約會放大，僅供量級參考）",
        "- 矩陣: 11 價格 × ≤7 日期；IV 按快照值恆定；末欄為到期 payoff；估值含美式內在價值鉗制",
        f"- 過濾: 到期日 / 報價 / IV(0.01-5.0) / OI>={p.min_oi} 且 Vol>={p.min_volume} / "
        f"Spread <= max({p.spread_floor:g}, {p.max_spread_pct:g}*Mid)",
        "- 排名: Delta 分級（實務慣例），級內以基準情境報酬率（Mid 進場）排序",
        "- 模型限制: 無股利調整（q=0）、歐式近似、IV 乘法情境",
        "- 免責: 模型估計非保證價格，不構成投資建議",
    ]


def render_filter_only(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport, today: date
) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport, p)
    lines += ["", "過濾後無合格合約，不產生推薦。", ""]
    return "\n".join(lines)


def render(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport,
    ranked: dict[str, list[ContractValuation]], n_qualified: int, today: date,
) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport, p)
    idx = 0
    for band in BAND_ORDER:
        lines.append("")
        lines.append(f"=== {BAND_LABELS[band]}（{_band_range(band, p)}） ===")
        if not ranked[band]:
            lines.append("- 此級距無合格合約")
            continue
        for j, v in enumerate(ranked[band]):
            idx += 1
            lines += _candidate_lines(v, idx, band, ranked, snap, n_qualified, p)
            if j == 0 or p.matrix_all:
                c = v.contract
                lines += _matrix_block(
                    lambda S, d, c=c: scenario_leg_value(c, S, d, p),
                    v.mid, snap.spot, p, today, _date.fromisoformat(c.expiry),
                )
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)


def _band_range(band: str, p: AnalysisParams) -> str:
    a, b = p.delta_bands
    if band == "conservative":
        return f"Delta > {b:g}"
    if band == "aggressive":
        return f"Delta < {a:g}"
    return f"Delta {a:g}-{b:g}"


def _pair_lines(pr) -> list[str]:
    return ["", "[配對統計]", f"- 配對總數: {pr.total_pairs}",
            f"- 健全性淘汰: {pr.removed_sanity}", f"- 合格組數: {pr.passed}"]


def _spread_candidate_lines(sv, idx, n_pairs, p) -> list[str]:
    from .ranking import build_spread_reasons
    from .valuation import spread_guidance_judgments
    ll, sl = sv.long_leg, sv.short_leg
    lines = [
        "",
        f"{idx + 1}) 買 K={_money(ll.strike)} / 賣 K={_money(sl.strike)} / {ll.expiry} 到期（寬度 ${_money(sv.width)}）",
        f"- 買腿 {ll.contract_symbol}: Bid ${_money(ll.bid)} / Ask ${_money(ll.ask)} IV {_pct_iv(ll.implied_volatility)}",
        f"- 賣腿 {sl.contract_symbol}: Bid ${_money(sl.bid)} / Ask ${_money(sl.ask)} IV {_pct_iv(sl.implied_volatility)}",
        f"- 淨成本: Mid ${_money(sv.net_mid)}（${sv.net_mid * 100:.0f}/張） / 最差 ${_money(sv.net_worst)}（${sv.net_worst * 100:.0f}/張）",
        f"- 最大獲利: ${_money(sv.max_profit)}（${sv.max_profit * 100:.0f}/張） / 淨Delta {sv.net_delta:.2f} / Lambda {sv.effective_leverage:.1f}x",
        f"- Breakeven: ${_money(sv.breakeven)}（對目標價緩衝 {_pct(sv.breakeven_vs_target)}）",
        "",
        "劇本成立時:",
    ]
    for shift, val in sv.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, sv.net_mid))
    lines.append(_val_line("IV 情境最低值", sv.l2, sv.net_mid))
    lines += ["", "買價指引:",
              f"- L2 保守上限（IV 情境最低值）: ${_money(sv.l2)}（${sv.l2 * 100:.0f}/張）",
              f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: ${_money(sv.l3)}（${sv.l3 * 100:.0f}/張）"]
    judgments = spread_guidance_judgments(sv, p)
    if judgments:
        lines += [f"- 警示: {m}" for m in judgments]
    else:
        lines.append("- 目前最差進場成本低於全部天花板")
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    lines += ["", "評語:"] + [f"- 優點: {s}" for s in pros] + [f"- 代價: {s}" for s in cons]
    return lines


def render_spreads(snap, p, freport, pair_report, ranked, n_pairs, today) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport, p) + _pair_lines(pair_report)
    if not ranked:
        lines += ["", "無合格價差組合，不產生推薦。", ""]
        return "\n".join(lines)
    for i, sv in enumerate(ranked):
        lines += _spread_candidate_lines(sv, i, n_pairs, p)
        if i == 0 or p.matrix_all:
            lng, sht = sv.long_leg, sv.short_leg
            lines += _matrix_block(
                lambda S, d, lng=lng, sht=sht: spread_scenario_value(lng, sht, S, d, p),
                sv.net_mid, snap.spot, p, today, _date.fromisoformat(lng.expiry),
            )
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)
