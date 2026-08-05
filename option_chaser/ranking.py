"""Delta banding and in-band ranking (spec §6). No custom weights."""
from __future__ import annotations

from datetime import date

from .models import AnalysisParams
from .valuation import (
    ContractValuation,
    SpreadValuation,
    guidance_judgments,
    intrinsic_value,
    scenario_leg_value,
    spread_guidance_judgments,
    spread_scenario_value,
)

BAND_CONSERVATIVE = "conservative"
BAND_BALANCED = "balanced"
BAND_AGGRESSIVE = "aggressive"
BAND_ORDER = (BAND_CONSERVATIVE, BAND_BALANCED, BAND_AGGRESSIVE)
BAND_LABELS = {
    BAND_CONSERVATIVE: "保守型",
    BAND_BALANCED: "平衡型",
    BAND_AGGRESSIVE: "積極型",
}


def classify(delta: float, bands: tuple[float, float]) -> str:
    delta = abs(delta)
    a, b = bands
    if delta > b:
        return BAND_CONSERVATIVE
    if delta < a:
        return BAND_AGGRESSIVE
    return BAND_BALANCED


def baseline_return(v: ContractValuation) -> float:
    """主排名數字。成本口徑＝最差成交假設（單腿＝Ask，附錄 A14.2）。"""
    return (v.baseline_value - v.contract.ask) / v.contract.ask


def return_at_price(
    val: ContractValuation | SpreadValuation, S: float, p: AnalysisParams
) -> float:
    """任意標的價位下的劇本報酬（V7／#55，三價位對照用）。

    口徑與主排名數字**完全相同**——基準 IV、最差成交成本（單腿＝Ask；
    價差＝買腿 Ask − 賣腿 Bid，附錄 A14.2），只有標的價換成 `S`。這是
    刻意的：三價位要能與頭條那個數字並排讀，就不能是另一套算法。
    `return_at_price(v, p.target_price, p) == baseline_return(v)` 由測試釘住，
    且**必須在 expiry != anchor 的候選上驗證**——兩者相等時這條斷言是空的。

    估值日**兩條路徑不同，各自沿用既有裁示**，不可統一：
    - 價差＝該組**自身的到期日**（T3／#17：排名估值改為各 Spread 自身到期日
      的內在價值，見 `valuation.evaluate_spread`）
    - 單腿＝日曆錨點（附錄 A9，見 `valuation.evaluate_contract`）

    不改排名（spec #47 明文：仍以目標價排名）——本函式只供呈現。
    """
    if isinstance(val, SpreadValuation):
        at = date.fromisoformat(val.long_leg.expiry)
        value = spread_scenario_value(val.long_leg, val.short_leg, S, at, p)
        cost = val.net_worst
    else:
        value = scenario_leg_value(val.contract, S, p.anchor, p)
        cost = val.contract.ask
    return (value - cost) / cost


def _tie_break_key(v: ContractValuation) -> tuple:
    return (v.spread / v.contract.ask, v.contract.strike, v.contract.expiry,
            v.contract.contract_symbol)


def rank(
    valuations: list[ContractValuation], p: AnalysisParams
) -> dict[str, list[ContractValuation]]:
    bands: dict[str, list[ContractValuation]] = {name: [] for name in BAND_ORDER}
    for v in valuations:
        bands[classify(v.delta, p.delta_bands)].append(v)
    for name in BAND_ORDER:
        bands[name].sort(key=lambda v: (-baseline_return(v), *_tie_break_key(v)))
        bands[name] = bands[name][: p.top]
    return bands


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_reasons(
    v: ContractValuation,
    band: str,
    ranked: dict[str, list[ContractValuation]],
    spot: float,
    n_qualified: int,
    p: AnalysisParams,
) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []

    all_ranked = [x for lst in ranked.values() for x in lst]
    max_ret = max(baseline_return(x) for x in all_ranked) if all_ranked else 0.0

    if band == BAND_CONSERVATIVE:
        word = "高於" if v.contract.option_type == "call" else "低於"
        s = f"breakeven 僅{word}現價 {_pct(v.breakeven_vs_spot)}"
        half_price = spot + 0.5 * (p.target_price - spot)
        if scenario_leg_value(v.contract, half_price, p.anchor, p) > v.contract.ask:
            s += "，劇本半對仍獲利"
        pros.append(s)
    elif band == BAND_BALANCED:
        intrinsic_now = intrinsic_value(v.contract.option_type, spot, v.contract.strike)
        pros.append(
            f"內在價值佔權利金 {_pct(intrinsic_now / v.contract.ask)}，時間價值負擔適中"
        )
    else:  # aggressive
        if baseline_return(v) == max_ret:
            pros.append(f"{n_qualified} 張合格合約中基準情境報酬率最高")
        else:
            pros.append(
                f"基準情境報酬率 {_pct(baseline_return(v))}，同級距中排名靠前"
            )

    if abs(v.delta) < 0.5:
        cons.append(
            f"若完全不漲權利金可能全損（最大虧損 ${v.contract.ask * 100:.2f}/張）"
        )
    first_picks = [lst[0] for lst in ranked.values() if lst]
    if first_picks and v is max(first_picks, key=lambda x: x.contract.ask):
        cons.append(f"本金需求最大（${v.contract.ask * 100:.2f}/張）")
    # spread warning: same structure as the §4 hard filter, relative part scaled 2/3
    if v.spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * v.mid):
        cons.append("買賣價差偏大")
    cons.extend(guidance_judgments(v, p))
    return pros, cons


def spread_baseline_return(sv: SpreadValuation) -> float:
    """主排名數字。成本口徑＝net_worst（買腿 Ask − 賣腿 Bid，附錄 A14.2）：
    bid/ask 寬、難成交在 mid 的 Spread 由口徑自然懲罰。公式形狀
    (基準值−成本)/成本 不變，僅成本口徑改變。"""
    return (sv.baseline_value - sv.net_worst) / sv.net_worst


def _spread_tie_key(sv: SpreadValuation) -> tuple:
    legs_spread = (sv.long_leg.ask - sv.long_leg.bid) + (sv.short_leg.ask - sv.short_leg.bid)
    return (legs_spread / sv.net_worst, sv.long_leg.strike, sv.long_leg.expiry,
            sv.long_leg.contract_symbol)


def rank_spreads(spreads: list[SpreadValuation], p: AnalysisParams) -> list[SpreadValuation]:
    ordered = sorted(spreads, key=lambda s: (-spread_baseline_return(s), *_spread_tie_key(s)))
    return ordered[: p.top]


def build_spread_reasons(
    sv: SpreadValuation, idx: int, n_pairs: int, p: AnalysisParams
) -> tuple[list[str], list[str]]:
    pros = [f"劇本成立時報酬率 {_pct(spread_baseline_return(sv))}（合格 {n_pairs} 組中第 {idx + 1}）"]
    cons = [f"獲利上限 = 寬度 − 淨成本 = ${sv.max_profit:.2f}（目標價以上的漲幅不參與）"]
    legs_spread = (sv.long_leg.ask - sv.long_leg.bid) + (sv.short_leg.ask - sv.short_leg.bid)
    if legs_spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * sv.net_mid):
        cons.append("買賣價差偏大（兩腿合計）")
    cons.extend(spread_guidance_judgments(sv, p))
    return pros, cons
