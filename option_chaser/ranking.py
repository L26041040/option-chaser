"""Delta banding and in-band ranking (spec §6). No custom weights."""
from __future__ import annotations

from datetime import date

from .models import AnalysisParams
from .valuation import (
    ButterflyProfitRegion,
    ButterflyValuation,
    ContractValuation,
    SpreadValuation,
    butterfly_guidance_judgments,
    butterfly_scenario_value,
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
    val: ContractValuation | SpreadValuation | ButterflyValuation, S: float,
    p: AnalysisParams,
) -> float:
    """任意標的價位下的劇本報酬（V7／#55，三價位對照用）。

    口徑與主排名數字**完全相同**——基準 IV、最差成交成本（單腿＝Ask；
    價差＝買腿 Ask − 賣腿 Bid，附錄 A14.2；Butterfly＝買腿 Ask 合計 −
    2×中腿 Bid，T15／#230），只有標的價換成 `S`。這是刻意的：三價位要
    能與頭條那個數字並排讀，就不能是另一套算法。
    `return_at_price(v, p.target_price, p) == baseline_return(v)` 由測試釘住，
    且**必須在 expiry != anchor 的候選上驗證**——兩者相等時這條斷言是空的。

    估值日**三個 family 一律是該候選自身的到期日**：
    - 價差／Butterfly＝T3／#17 既有裁示（見 `valuation.evaluate_spread`／
      `evaluate_butterfly`）
    - 單腿＝REPAIR-09（#246，spec #237 OD-02）把排名基準估值日從固定
      日曆錨點（附錄 A9）改成候選自身到期日之後，這裡跟著對齊（見
      `valuation.evaluate_contract`）

    OPTION-CHASER-CLOSEOUT-003：這一行原本停在 `p.anchor`——REPAIR-09
    依票面明文「`ranking.py` 零改動」未動它，於是上面那條「口徑完全
    相同」的不變量對**到期日晚於錨點的單腿候選**變成假的（實測
    strike 110／ask 3.2／target 120／anchor 2026-10-16／expiry
    2026-12-18：`baseline_return` 2.125 vs 這裡 2.942，差的正是
    REPAIR-09 要消滅的殘留時間價值）。守門測試
    `test_single_leg_at_target_price_equals_baseline_return` 的 fixture
    到期日恰好等於錨點，正是它姊妹測試 docstring 早就點名的那種空
    斷言，因此沒有紅燈。本輪 merge gate review 抓到並修正，單腿分支
    改用候選自身到期日；價差／Butterfly 兩個分支本來就是自身到期日，
    一個字沒動，V1 Vertical 凍結數值逐位元不變。

    不改排名（spec #47 明文：仍以目標價排名）——本函式只供呈現。
    """
    if isinstance(val, SpreadValuation):
        at = date.fromisoformat(val.long_leg.expiry)
        value = spread_scenario_value(val.long_leg, val.short_leg, S, at, p,
                                      long_carry=val.long_carry,
                                      short_carry=val.short_carry)
        cost = val.net_worst
    elif isinstance(val, ButterflyValuation):
        at = date.fromisoformat(val.low_leg.expiry)
        value = butterfly_scenario_value(
            val.low_leg, val.mid_leg, val.high_leg, S, at, p,
            low_carry=val.low_carry, mid_carry=val.mid_carry,
            high_carry=val.high_carry)
        cost = val.net_worst
    else:
        at = date.fromisoformat(val.contract.expiry)
        value = scenario_leg_value(val.contract, S, at, p, carry=val.carry)
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
        # #122（spec #117 §1.4 核心紅線）：分級只讀 `classification_delta`，
        # 不讀 `delta`——見 `ContractValuation.classification_delta` 欄位
        # 註解。這是本專案唯一的單腿分級選取路徑，未來換估值模型不得
        # 讓這一行改讀 `v.delta`。
        bands[classify(v.classification_delta, p.delta_bands)].append(v)
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
        # OPTION-CHASER-CLOSEOUT-003：估值日與 `baseline_return`／
        # `return_at_price` 同為候選**自身到期日**。原本停在固定日曆
        # 錨點（附錄 A9），對到期日晚於錨點的候選會說出與到期真相相反
        # 的話——實測 K110／ask 3.2／anchor 2026-10-16／expiry
        # 2026-12-18，半價位（110.0）在錨點日值 5.83 > ask，於是印出
        # 「劇本半對仍獲利」；但那天它自己還沒到期，真正到期時內在
        # 價值是 0.00，權利金全損。這句話是講給使用者聽的事實陳述，
        # 不能用一個該候選根本還沒到期的日期去判定。
        at = date.fromisoformat(v.contract.expiry)
        if scenario_leg_value(v.contract, half_price, at, p,
                              carry=v.carry) > v.contract.ask:
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


def butterfly_baseline_return(bv: ButterflyValuation) -> float:
    """主排名數字。成本口徑＝net_worst（買腿 Ask 合計 − 2×中腿 Bid，
    附錄 A14.2 的延伸——debit 維持既有語意：劇本成立時相對**實際投入
    成本**的報酬，#213 Correction，非 risk-capital 分母）。公式形狀
    (基準值−成本)/成本 逐字沿用既有兩個 debit 家族。"""
    return (bv.baseline_value - bv.net_worst) / bv.net_worst


def _butterfly_tie_key(bv: ButterflyValuation) -> tuple:
    legs_spread = ((bv.low_leg.ask - bv.low_leg.bid)
                  + (bv.mid_leg.ask - bv.mid_leg.bid)
                  + (bv.high_leg.ask - bv.high_leg.bid))
    return (legs_spread / bv.net_worst, bv.low_leg.strike, bv.low_leg.expiry,
           bv.low_leg.contract_symbol)


def rank_butterflies(
    butterflies: list[ButterflyValuation], p: AnalysisParams
) -> list[ButterflyValuation]:
    """Owner 2026-08-30 明確裁示（#230）：body 的位置不寫死，由「在目標
    價位那一點的報酬最大化」的排名自然湧現——這裡跟既有 `rank_spreads()`
    是同一套排序邏輯，不特別偏好任何履約價組合。"""
    ordered = sorted(
        butterflies,
        key=lambda b: (-butterfly_baseline_return(b), *_butterfly_tie_key(b)))
    return ordered[: p.top]


def butterfly_profit_region_text(region: ButterflyProfitRegion | None) -> str:
    """獲利區間的人話描述——CLI 純文字報告（`report._butterfly_lines`）與
    候選評語（`build_butterfly_reasons`）共用同一份措辭決策，兩處不各自
    判斷四種情況，否則哪天只改一邊就會出現兩種說法。

    CLOSEOUT-004（PR #250 review Finding 1）：`lower`／`upper` 各自可為
    `None`＝那一側沒有界（broken-wing 的翼外平台本身就高於進場成本，
    見 `valuation.ButterflyProfitRegion`）。文案**不得**在那種情況下說
    「區間外到期時無法獲利」——那是對使用者的假話：往那個方向走多遠都
    還是獲利。"""
    if region is None:
        return "無——到期時任何標的價都無法獲利"
    lo, hi = region.lower, region.upper
    if lo is not None and hi is not None:
        return f"${lo:.2f} ~ ${hi:.2f}（區間外到期時無法獲利）"
    if lo is not None:
        return f"${lo:.2f} 以上（沒有上界，更高的標的價到期時一樣獲利）"
    if hi is not None:
        return f"${hi:.2f} 以下（沒有下界，更低的標的價到期時一樣獲利）"
    return "任何標的價到期時都獲利（兩側都沒有界）"


def build_butterfly_reasons(
    bv: ButterflyValuation, idx: int, n_triples: int, p: AnalysisParams
) -> tuple[list[str], list[str]]:
    pros = [f"劇本成立時報酬率 {_pct(butterfly_baseline_return(bv))}"
           f"（合格 {n_triples} 組中第 {idx + 1}）"]
    if bv.profit_region is not None:
        cons = [f"獲利區間 {butterfly_profit_region_text(bv.profit_region)}"]
    else:
        cons = ["到期時任何標的價都無法獲利（峰值仍低於進場成本）"]
    legs_spread = ((bv.low_leg.ask - bv.low_leg.bid)
                  + (bv.mid_leg.ask - bv.mid_leg.bid)
                  + (bv.high_leg.ask - bv.high_leg.bid))
    if legs_spread > max(p.spread_floor, (2.0 / 3.0) * p.max_spread_pct * bv.net_mid):
        cons.append("買賣價差偏大（三腿合計）")
    cons.extend(butterfly_guidance_judgments(bv, p))
    return pros, cons
