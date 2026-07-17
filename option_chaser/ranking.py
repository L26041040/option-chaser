"""Delta banding and in-band ranking (spec §6). No custom weights."""
from __future__ import annotations

from .models import AnalysisParams
from .valuation import ContractValuation, guidance_judgments

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
    a, b = bands
    if delta > b:
        return BAND_CONSERVATIVE
    if delta < a:
        return BAND_AGGRESSIVE
    return BAND_BALANCED


def baseline_return(v: ContractValuation) -> float:
    return (v.baseline_value - v.mid) / v.mid


def _tie_break_key(v: ContractValuation) -> tuple:
    return (v.spread / v.mid, v.contract.strike, v.contract.expiry,
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
        s = f"breakeven 僅高於現價 {_pct(v.breakeven_vs_spot)}"
        if v.stress_half > v.mid:
            s += "，劇本半對仍獲利"
        pros.append(s)
    elif band == BAND_BALANCED:
        intrinsic_now = max(spot - v.contract.strike, 0.0)
        pros.append(
            f"內在價值佔權利金 {_pct(intrinsic_now / v.mid)}，時間價值負擔適中"
        )
    else:  # aggressive
        if baseline_return(v) == max_ret:
            pros.append(f"{n_qualified} 張合格合約中基準情境報酬率最高")
        else:
            pros.append(
                f"基準情境報酬率 {_pct(baseline_return(v))}，同級距中排名靠前"
            )

    if v.delta < 0.5:
        cons.append(
            f"若完全不漲權利金可能全損（最大虧損 ${v.mid * 100:.2f}/張）"
        )
    first_picks = [lst[0] for lst in ranked.values() if lst]
    if first_picks and v is max(first_picks, key=lambda x: x.mid):
        cons.append(f"本金需求最大（${v.mid * 100:.2f}/張）")
    # spread warning: same structure as the §4 hard filter, relative part scaled 2/3
    if v.spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * v.mid):
        cons.append("買賣價差偏大")
    cons.extend(guidance_judgments(v, p))
    return pros, cons
