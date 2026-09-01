"""Black-Scholes valuation, Greeks, scenario/stress/guidance. Stdlib math only."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .models import AnalysisParams, OptionContract

DAYS_PER_YEAR = 365.0


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call. Spec §5.1: T <= 0 -> intrinsic (BS undefined at T=0)."""
    if T <= 0.0:
        return max(S - K, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float


def call_greeks(S: float, K: float, T: float, r: float, sigma: float,
                q: float = 0.0) -> Greeks:
    """Spec §5.5，#113（spec #117 §1.4）擴充 q（連續股利殖利率）。

    Caller guarantees T > 0 (filters ensure expiry > today)。

    `q=0.0`（預設）時逐位元退化成擴充前的既有公式——`math.exp(-0.0*T)`
    恆為 `1.0`（IEEE754 精確值，非近似），乘 1.0／減 0.0 不引入任何
    捨入誤差，`tests/test_greeks_q.py` 直接斷言差為 0.0。
    """
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    disc_q = math.exp(-q * T)
    theta_year = (
        -(S * disc_q * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm_cdf(d2)
        + q * S * disc_q * norm_cdf(d1)
    )
    return Greeks(
        delta=disc_q * norm_cdf(d1),
        gamma=disc_q * norm_pdf(d1) / (S * st),
        theta_per_day=theta_year / DAYS_PER_YEAR,
        vega_per_pct=S * disc_q * norm_pdf(d1) * math.sqrt(T) / 100.0,
    )


def days_between(d1: date, d2: date) -> int:
    return (d2 - d1).days


def leg_rate(p: AnalysisParams, expiry: str) -> float:
    """T12（附錄 A14.1）：每腿以**自身到期日**查表取期限對齊利率。

    表由 service 以「分析日→到期日」年期自 Treasury 曲線預先解出；同一腿在
    Heatmap 全格共用同一個 r（與恆定 IV 假設一致），因此以到期日查表而非逐格
    重算年期。無表（`--rate` 明示、離線路徑、曲線 fallback）時用常數 `p.rate`。
    """
    for exp, r in p.rate_by_expiry:
        if exp == expiry:
            return r
    return p.rate


@dataclass(frozen=True)
class LegCarry:
    """#113（spec #117 §1）：一條腿的 carry 校準結果，每腿只算一次

    （架構要求：矩陣迴圈維持 `(S, t)` 純函式，不隨格數重算 IV 反解）。
    由 `calibrate_leg()` 產生，掛在 `ContractValuation.carry`／
    `SpreadValuation.long_carry`／`short_carry` 上，之後所有 `scenario_
    leg_value()` 呼叫（Heatmap 矩陣、七情境、保本掃描、CLI 報告……全部
    共用同一個原語）都直接傳這個現成的 `(q, sigma)`，不重新反解。
    """
    q: float
    sigma: float
    # False＝退回今天的完整行為（q=0、直接採用 vendor IV）——不管是因為
    # q 管線尚未接上（`p.q_by_symbol is None`，#123 之前恆為此狀態），
    # 還是這條腿的 IV 反解本身失敗（目標價落在模型可行區間外，例如
    # 報價陳舊或錯價）。兩種原因收斂成同一個 fallback 形狀，呼叫端不必
    # 分辨「為什麼沒校準」，只需要知道「有沒有校準」。
    carry_calibrated: bool


def calibrate_leg(c: OptionContract, spot: float, today: date,
                  p: AnalysisParams,
                  cache: dict[tuple, "LegCarry"] | None = None) -> LegCarry:
    """對一條腿做一次 carry 校準（每腿一次，見 `LegCarry` docstring）。

    `p.q_by_symbol is None`（q 管線未接、或該次快照校準不出來，#123
    的範圍）→ 直接退回今天的行為，**不呼叫** IV 反解——q=0 時很多真實
    LEAPS call 的目標價落在模型 sigma→0 下限之下，反解在數學上無解
    （研究文件 `heatmap-valuation-method-selection.md` §4.2 已證實），
    這條路必須是直接失敗而不是嘗試後失敗。

    有 `q_by_symbol` → 用同一份快照的**中價**、在同一個 BS93+q 模型下
    反解 σ（價格錨定：t=0 時模型值依定義回到市價）。反解失敗（同樣的
    「目標價落在可行區間外」情況，但這次是嘗試過的）→ 該腿一樣退回
    今天的行為並標記，**不外插、不亂猜**（沿用「缺席就如實缺席」的
    既有原則）。

    REPAIR-03（#240，FIX-02，#052 audit）：`cache` 選填——單次
    `_spread_result()`／`_butterfly_result()` 呼叫內，`generate_
    spread_pairs()`／`generate_butterfly_triples()` 窮舉出的候選組合
    會讓同一條腿（同一張合約）在大量不同組合裡重複出現，`evaluate_
    spread()`／`evaluate_butterfly()` 因此對同一條腿重複呼叫這個函式
    ——production-scale 規模下（171,100 組 Butterfly 候選對應約 300
    條相異腿）這是 60 秒 timeout 的主因，佔整體 wall time 約 95%。
    比照既有 `scenarios.resilience_metrics()` 的 `cache` 參數慣例：
    呼叫端（`_single_leg_result`／`_spread_result`／`_butterfly_
    result`）建立、貫穿單次分析呼叫傳下去的字典，鍵為
    `(contract_symbol, spot, today, q_by_symbol)`——這四項在單次分析
    呼叫內皆為常數，只有 `contract_symbol` 真正會變，寫全四項是為了
    誠實表達「這個結果依賴什麼」，不是暗示這幾項在單次呼叫內真的會變。
    ⚠ 快取正確性還隱性依賴 `p`（`AnalysisParams`，經 `leg_rate(p, ...)`
    影響利率查表）在快取字典的存活期間不變——這一項**沒有**寫進 key，
    因為呼叫端（`_single_leg_result`／`_spread_result`／`_butterfly_
    result`）建立 `carry_cache` 後只在同一個 `p` 底下的單一迴圈使用，
    `AnalysisParams` 本身是 frozen dataclass、迴圈內不會被替換；若未來
    呼叫端改成同一個快取字典跨不同 `p` 重用，這個假設就會失效，屆時
    需要把 `p`（或至少它影響 `calibrate_leg` 結果的那些欄位）一併
    納入 key。不傳（`None`，預設）就是每次都重算，行為與這個快取機制
    存在之前完全一樣——沒有快取的既有呼叫端（測試直接呼叫本函式）
    不受影響。
    範圍侷限在單次分析呼叫內，**不是**跨 HTTP request 的快取層（那是
    完全不同風險等級的改動，不在本票範圍）。
    """
    key = (c.contract_symbol, spot, today, p.q_by_symbol)
    if cache is not None and key in cache:
        return cache[key]

    if p.q_by_symbol is None:
        result = LegCarry(q=0.0, sigma=c.implied_volatility, carry_calibrated=False)
    else:
        expiry = date.fromisoformat(c.expiry)
        T = days_between(today, expiry) / DAYS_PER_YEAR
        if T <= 0.0:
            result = LegCarry(q=0.0, sigma=c.implied_volatility, carry_calibrated=False)
        else:
            mid = (c.bid + c.ask) / 2.0
            sigma_hat = implied_vol(c.option_type, mid, spot, c.strike, T,
                                    leg_rate(p, c.expiry), p.q_by_symbol)
            if sigma_hat is None:
                result = LegCarry(q=0.0, sigma=c.implied_volatility,
                                  carry_calibrated=False)
            else:
                result = LegCarry(q=p.q_by_symbol, sigma=sigma_hat,
                                  carry_calibrated=True)

    if cache is not None:
        cache[key] = result
    return result


@dataclass(frozen=True)
class ContractValuation:
    contract: OptionContract
    mid: float
    spread: float
    delta: float
    # #122（spec #117 §1.4 核心紅線）：legacy 單腿分級（`ranking.classify`／
    # `p.delta_bands`）只讀這一份，不讀上面的 `delta`。目前兩者算法完全
    # 相同（本票是零行為變化的 prefactor），差異只在「誰讀誰」——
    # `delta` 供估值與畫面顯示，未來換估值模型（#113）只會改 `delta`，
    # `classification_delta` 保持原口徑不動，legacy 分級因此不會被新模型
    # 污染。這欄位存在的唯一理由就是切斷這條路徑，不是為了任何其他目的。
    classification_delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float
    breakeven: float
    breakeven_vs_spot: float
    breakeven_vs_target: float
    effective_leverage: float
    floor_value: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l1: float
    l2: float
    l3: float
    # #113：這條腿的 carry 校準結果，算一次、掛在這裡供所有下游呼叫
    # （Heatmap 矩陣、七情境、CLI 報告……）共用，不重新反解。
    carry: LegCarry


def scenario_leg_value(
    c: OptionContract, S: float, at: date, p: AnalysisParams, shift: float = 0.0,
    carry: LegCarry | None = None,
) -> float:
    """Spec §3 valuation primitive: value of one leg at date `at` with spot S.

    #113：`carry=None`（預設）與 `carry.carry_calibrated=False` 都走
    **今天逐位元不變**的路徑——`clamped_price` ＋ vendor IV，q=0。只有
    `carry.carry_calibrated=True` 才走 BS93＋校準後的 `(q, sigma)`。
    `at >= expiry` 的到期內在價值分支在 carry 檢查**之前**，不受影響
    ——這正是 T3／#17「Spread 排名用自身到期日的內在價值，與定價模型
    無關」這條既有不變量在程式碼層級成立的原因，不需要另外特case。
    """
    expiry = date.fromisoformat(c.expiry)
    if at >= expiry:
        return intrinsic_value(c.option_type, S, c.strike)
    T = days_between(at, expiry) / DAYS_PER_YEAR
    if carry is not None and carry.carry_calibrated:
        return american_price(c.option_type, S, c.strike, T,
                              leg_rate(p, c.expiry), carry.q,
                              carry.sigma * (1.0 + shift))
    return clamped_price(c.option_type, S, c.strike, T, leg_rate(p, c.expiry),
                         c.implied_volatility * (1.0 + shift))


def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams,
    carry_cache: dict[tuple, LegCarry] | None = None,
) -> ContractValuation:
    """`carry_cache`：REPAIR-03（#240）——傳給 `calibrate_leg()` 的選填
    快取，單腿路徑本身沒有同一條腿重複出現的問題（`qualified` 逐一
    對應一次呼叫），這裡接受它只是為了讓三個估值函式共用同一套
    memoization 機制、呼叫慣例一致；不傳（預設）行為不變。"""
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    expiry = date.fromisoformat(c.expiry)
    # REPAIR-09（#246，spec #237 OD-02，FIX-05）：排名基準估值日改為
    # 候選**自身到期日**（直接用 `expiry`，不再另立 `target` 別名——
    # `evaluate_spread()` 本來就是這樣寫，這裡對齊同一種寫法），與
    # Vertical／Butterfly（T3／#17，`evaluate_spread`／
    # `evaluate_butterfly` 既有裁示）對齊——三個 family 從此用同一套
    # 「候選自身到期日」比較語意，不再是單腿殘留時間價值、Spread／
    # Butterfly 卻已經是純內在價值這種不對稱比較。附錄 A9 的
    # `p.anchor`（固定日曆錨點）仍是舊表面的合法例外（CLI 報告、單腳
    # 買價指引文字、情境曲線、`ranking.return_at_price` 的 V7 三價位
    # 顯示——`ranking.py` 依票面明文不動），只是不再是**排名**基準
    # 估值日。
    carry = calibrate_leg(c, spot, today, p, carry_cache)   # #113：每腿一次
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    # #122 核心紅線：分級用的 delta **恆** q=0／vendor IV，不讀 carry——
    # 即使這條腿已校準，legacy 分級路徑也看不到新模型。
    g_classification = leg_greeks(c.option_type, spot, c.strike, t_now,
                                  leg_rate(p, c.expiry), c.implied_volatility)
    # 顯示／估值用的 Greeks：未校準時 carry.sigma=vendor IV、carry.q=0.0，
    # 與 g_classification 精確同值（不是巧合，是 calibrate_leg 的 fallback
    # 設計）；校準成功時才真的用上新的 (q, sigma)。
    g = leg_greeks(c.option_type, spot, c.strike, t_now,
                   leg_rate(p, c.expiry), carry.sigma, carry.q)
    scenario_values = tuple(
        (shift, scenario_leg_value(c, p.target_price, expiry, p, shift, carry))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]
    floor_value = intrinsic_value(c.option_type, p.target_price, c.strike)
    # T12（附錄 A14.2）：主數字成本口徑＝最差成交假設（單腿＝Ask）。
    # breakeven／槓桿等成本衍生數字同口徑；mid 保留為次要顯示。breakeven
    # 純粹是市場報價（strike ± ask）的算術，不經任何估值模型，因此不受
    # carry 影響——這與研究文件 §8 對 Spread 排名的觀察是同一件事。
    if c.option_type == "call":
        breakeven = c.strike + c.ask
        be_vs_spot = (breakeven - spot) / spot
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = c.strike - c.ask
        be_vs_spot = (spot - breakeven) / spot
        be_vs_target = (breakeven - p.target_price) / p.target_price
    l2 = scenario_leg_value(c, p.target_price, expiry, p, min(p.iv_shifts), carry)
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, classification_delta=g_classification.delta,
        gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven, breakeven_vs_spot=be_vs_spot,
        breakeven_vs_target=be_vs_target,
        effective_leverage=abs(g.delta) * spot / c.ask,
        floor_value=floor_value, scenario_values=scenario_values,
        baseline_value=baseline_value,
        l1=floor_value, l2=l2, l3=baseline_value / (1.0 + p.min_return),
        carry=carry,
    )


def _shift_label(shift: float) -> str:
    if shift == 0.0:
        return "shift=0，即基準"
    return f"shift={shift * 100:+g}%"


def guidance_judgments(v: ContractValuation, p: AnalysisParams) -> list[str]:
    """Spec §5.7: independent per-ceiling judgments against current Ask."""
    ask = v.contract.ask
    msgs: list[str] = []
    if ask > v.l1:
        msgs.append("超過劇本內在價值，獲利需時間價值/IV 配合")
    if ask > v.l2:
        msgs.append(
            f"劇本成立但最保守 IV 情境（{_shift_label(min(p.iv_shifts))}）下仍虧損"
        )
    if ask > v.l3:
        msgs.append("以 Ask 進場達不到你設定的最低報酬（min-return）")
    return msgs


def bs_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put. T <= 0 -> intrinsic (spec §3.1)."""
    if T <= 0.0:
        return max(K - S, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def bs_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    return bs_call(S, K, T, r, sigma) if option_type == "call" else bs_put(S, K, T, r, sigma)


def intrinsic_value(option_type: str, S: float, K: float) -> float:
    return max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)


def clamped_price(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    """把歐式 BS 值鉗到內在價值之上（未校準／今天行為路徑專用，見
    `scenario_leg_value`）。

    #113（spec #117 §1.6）更正 docstring：這**不是**「American
    no-arbitrage floor」——它防的是「模型值低於內在價值」這種荒謬
    結果，不是提前履約權利的價值。實測（真實 758 筆 Cboe 全鏈）它對
    美式溢價的回收率中位數是 0.0%（229 筆有溢價的 put，箝制真正生效
    只有 46 筆），見 `docs/research/heatmap-valuation-method-selection.md`
    §4.4。真正的美式提前履約價值由 `american_price`（BS93 近似）處理，
    只在該腿 carry 校準成功時才會被用到；本函式維持給未校準（今天）
    路徑用，行為不變。
    """
    return max(bs_price(option_type, S, K, T, r, sigma), intrinsic_value(option_type, S, K), 0.0)


def leg_greeks(option_type: str, S: float, K: float, T: float, r: float,
               sigma: float, q: float = 0.0) -> Greeks:
    """Spec §3.1，#113（spec #117 §1.4）擴充 q。Caller guarantees T > 0.

    put 的 delta 用一般化的 put-call parity 微分關係
    `put_delta = call_delta − e^{-qT}`（q=0 時精確退化成既有的
    `call_delta − 1.0`，`math.exp(-0.0*T)` 恆為 1.0）；theta 的
    `q*S*e^{-qT}*N(-d1)` 修正項同理在 q=0 時精確歸零，不是近似。
    """
    g = call_greeks(S, K, T, r, sigma, q)
    if option_type == "call":
        return g
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    disc_q = math.exp(-q * T)
    theta_year_put = (
        -(S * disc_q * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm_cdf(-d2)
        - q * S * disc_q * norm_cdf(-d1)
    )
    return Greeks(
        delta=g.delta - disc_q,
        gamma=g.gamma,
        theta_per_day=theta_year_put / DAYS_PER_YEAR,
        vega_per_pct=g.vega_per_pct,
    )


@dataclass(frozen=True)
class WeightedLeg:
    """T02（#219，#217 決策 B）：一條腿在某個 payoff 加總裡的角色——
    符號（多／空）、口數、以及（可選的）carry 校準結果。這是本票引入的
    逐腿加總原語，**不假設腿數、不假設買賣方向組合**——供 T12（#228，
    共用骨架 legs[]）與 T15（#230，Butterfly 枚舉）之後的任意腿數結構
    直接複用；本票本身不新增任何新結構，只用它取代既有兩腿 Spread 的
    封套公式。"""
    contract: OptionContract
    sign: float          # +1.0＝方向與買方一致（long），-1.0＝short
    quantity: int = 1
    carry: LegCarry | None = None


def payoff_value(legs: tuple[WeightedLeg, ...], S: float, at: date,
                 p: AnalysisParams, shift: float = 0.0) -> float:
    """#217 決策 B：payoff 一律逐腿直算——`V(S) = Σ 方向符號 × 口數 ×
    單腿價值`。到期＝內在價值、到期前＝既有逐腿模型估值（BS93＋carry），
    這兩件事都已經是 `scenario_leg_value` 自己的既有行為，本函式只負責
    加總，**不對加總結果做任何額外的 clamp／floor／cap**。

    不假設 `legs` 的長度或裡面符號的組合方式——空集合回傳 0.0（純加總
    的自然結果，不需要特殊分支）。
    """
    return sum(leg.sign * leg.quantity * scenario_leg_value(
        leg.contract, S, at, p, shift, leg.carry) for leg in legs)


def spread_scenario_value(
    long_leg: OptionContract, short_leg: OptionContract,
    S: float, at: date, p: AnalysisParams, shift: float = 0.0,
    long_carry: LegCarry | None = None, short_carry: LegCarry | None = None,
) -> float:
    """T02（#219）：逐腿直算，取代舊有的 `min(max(long-short,0), width)`
    封套公式——那是「long debit vertical 的 payoff 包絡寫成算術」的
    地雷之一（#217 決策 B 明令廢除）。

    移除前已用 T01（#218）數值基準核對：在**到期日**（`scenario_
    values`／`baseline_value`／排名所用的口徑，T3／#17 既有裁示）以及
    絕大多數 Heatmap 格點上，這個 clamp 從未真正生效——到期時兩腿內在
    價值差恆在 `[0, width]`（`intrinsic(K1)-intrinsic(K2)` 對 K1<K2 的
    call 必然如此）；到期前，若兩腿共用**同一個** sigma，BS 定價的
    monotone-in-strike 性質保證 `C(K1)-C(K2) <= (K2-K1)e^{-rT} < width`。

    **但兩腿的 vendor IV 通常不同**（真實市場 skew）——這個保證只在
    「同一 sigma」的前提下成立。核對中實測抓到一個真實反例：XYZ 的
    105/110 call（買腿 IV 0.36、賣腿 IV 0.30）在 2026-07-15、S=133.2
    這個 Heatmap 格點，逐腿直算 `5.017486628026035` 微幅超出
    `width=5.0`（超出 0.35%）——這不是浮點雜訊，是「各腿各自反解自己
    的 IV、分開定價」這個既有模型（未經 carry 校準時的既有行為，非
    T02 引入）在有 skew 時的真實性質。舊 clamp 會把這種情況無聲地夾回
    `width`，讓使用者看不出這裡其實有模型張力；移除後如實顯示逐腿加總
    的結果——這正是 #217 決策 B 要的「不再有結構專屬封套公式」。

    Owner 2026-08-30 核准：拿掉 clamp、更新 T01 基準反映這 3 格的新值
    （XYZ bull-call-spread 105/110 候選，`matrix.cells[9][0]`／
    `[10][0]`／`[10][1]`），此後繼續 byte-locked。CLI golden fixtures
    與契約樣本核對後零漂移（未踩到這個特定 skew 組合）。

    這裡仍是一個薄殼——只是把兩腿包成 `WeightedLeg` 交給 `payoff_
    value()`，簽章（`long_leg`／`short_leg`／`long_carry`／
    `short_carry`）維持既有兩腿呼叫慣例不變，供 `ranking.py`／
    `report.py`／`scenarios.py`／`service.py` 現有呼叫點零改動沿用；
    共用骨架的任意腿數版本留給 T12（#228）處理。
    """
    legs = (WeightedLeg(contract=long_leg, sign=1.0, quantity=1, carry=long_carry),
           WeightedLeg(contract=short_leg, sign=-1.0, quantity=1, carry=short_carry))
    return payoff_value(legs, S, at, p, shift)


@dataclass(frozen=True)
class SpreadValuation:
    long_leg: OptionContract
    short_leg: OptionContract
    width: float
    net_mid: float
    net_worst: float
    net_delta: float
    breakeven: float
    breakeven_vs_target: float
    effective_leverage: float
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l2: float
    l3: float
    max_profit: float
    # #113：兩條腿各自的 carry 校準結果，算一次、供所有下游共用
    # （見 `LegCarry` docstring）。
    long_carry: LegCarry
    short_carry: LegCarry


def evaluate_spread(
    long_leg: OptionContract, short_leg: OptionContract,
    spot: float, today: date, p: AnalysisParams,
    carry_cache: dict[tuple, LegCarry] | None = None,
) -> SpreadValuation:
    """`carry_cache`：REPAIR-03（#240，#052 audit）——`generate_spread_
    pairs()` 窮舉出的候選裡，同一條腿會在多個配對裡重複出現
    （`C(n,2)` 組合，每條腿平均出現 n-1 次），未加 memoize 時
    `calibrate_leg()` 對同一條腿被重複反解。傳入呼叫端貫穿單次
    `_spread_result()` 的字典即可對同一條腿只反解一次；不傳
    （預設）行為不變，見 `calibrate_leg()` docstring。"""
    width = abs(short_leg.strike - long_leg.strike)
    net_mid = (long_leg.bid + long_leg.ask) / 2.0 - (short_leg.bid + short_leg.ask) / 2.0
    net_worst = long_leg.ask - short_leg.bid
    expiry = date.fromisoformat(long_leg.expiry)
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    long_carry = calibrate_leg(long_leg, spot, today, p, carry_cache)  # #113
    short_carry = calibrate_leg(short_leg, spot, today, p, carry_cache)
    g_l = leg_greeks(long_leg.option_type, spot, long_leg.strike, t_now,
                     leg_rate(p, long_leg.expiry), long_carry.sigma, long_carry.q)
    g_s = leg_greeks(short_leg.option_type, spot, short_leg.strike, t_now,
                     leg_rate(p, short_leg.expiry), short_carry.sigma, short_carry.q)
    net_delta = g_l.delta - g_s.delta
    # 需求 §三：排名情境＝標的在該 Spread **自身到期日**等於目標價、持有至到期。
    # 估值日即 expiry → 內在價值；IV shift 到期時無作用，情境向量同值屬必然。
    # 這也是 Spread 排名與定價模型無關（研究文件 §8／T3／#17 既有裁示）
    # 在程式碼層級成立的原因：`scenario_leg_value` 的 `at >= expiry` 分支
    # 在讀 carry 之前就回傳了，這裡即使傳了 carry 也不影響數值——傳入是
    # 為了與其他呼叫點一致，不是因為這裡真的用得到。
    scenario_values = tuple(
        (shift, spread_scenario_value(long_leg, short_leg, p.target_price, expiry,
                                      p, shift, long_carry, short_carry))
        for shift in p.iv_shifts
    )
    baseline = dict(scenario_values)[0.0]
    # T12（附錄 A14.2）：主數字成本口徑＝net_worst（買腿 Ask − 賣腿 Bid），
    # 定位「保守成交假設收益」。breakeven／最大獲利／槓桿同口徑；net_mid
    # 保留為次要顯示。breakeven 是市場報價算術，不經模型，不受 carry 影響。
    if long_leg.option_type == "call":
        breakeven = long_leg.strike + net_worst
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = long_leg.strike - net_worst
        be_vs_target = (breakeven - p.target_price) / p.target_price
    return SpreadValuation(
        long_leg=long_leg, short_leg=short_leg, width=width,
        net_mid=net_mid, net_worst=net_worst, net_delta=net_delta,
        breakeven=breakeven, breakeven_vs_target=be_vs_target,
        effective_leverage=abs(net_delta) * spot / net_worst,
        scenario_values=scenario_values, baseline_value=baseline,
        l2=min(v for _, v in scenario_values),
        l3=baseline / (1.0 + p.min_return),
        max_profit=width - net_worst,
        long_carry=long_carry, short_carry=short_carry,
    )


# ---------- #119（spec #117 §1）：BS93 美式近似＋同模型 IV 反解 ----------
#
# 這一段是 spec #117 鎖定的估值原語，純函式、純 stdlib，逐字依
# QuantLib `BjerksundStenslandApproximationEngine`（一手原始碼，
# https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/
# vanilla/bjerksundstenslandengine.cpp）移植，未改動任何既有函式、
# 未被任何既有呼叫路徑引用——接進引擎是 #113 的範圍，本檔只交付
# 「原語本身正確」。變數命名沿用原始碼的 rT/bT/variance（皆已乘上 T
# 的「T-scaled」量，不是年化值），方便對照原始碼逐行核對。


def merton_price(option_type: str, S: float, K: float, T: float, r: float,
                 q: float, sigma: float) -> float:
    """Black-Scholes-Merton 歐式解，含連續股利殖利率 q（Merton 1973）。

    q=0 時就是既有 `bs_price`；這裡獨立一份是因為 BS93 需要它當
    q<=0 的精確退化目標與數值防護的 fallback，兩邊呼叫的參數形狀
    （含 q）不同，不透過既有 `bs_price` 包一層。T<=0／sigma<=0 回內在
    價值（時間價值歸零的極限，不是特例分支）。
    """
    if T <= 0.0 or sigma <= 0.0:
        return intrinsic_value(option_type, S, K)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    if option_type == "call":
        return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * math.exp(-q * T) * norm_cdf(-d1)


def _bs93_phi(S: float, gamma: float, H: float, I: float,
             rT: float, bT: float, variance: float) -> float:
    """QuantLib `phi()` 逐行移植。`variance`＝sigma²T（已含 T），
    `rT`＝rT、`bT`＝bT（皆已含 T）——呼叫端負責換算，這裡不重複。"""
    lam = -rT + gamma * bT + 0.5 * gamma * (gamma - 1.0) * variance
    sv = math.sqrt(variance)
    d = -(math.log(S / H) + (bT + (gamma - 0.5) * variance)) / sv
    kappa = 2.0 * bT / variance + (2.0 * gamma - 1.0)
    d2 = d - 2.0 * math.log(I / S) / sv
    return math.exp(lam) * (norm_cdf(d) - (I / S) ** kappa * norm_cdf(d2))


def _bs93_call_core(S: float, K: float, T: float, r: float, q: float,
                    sigma: float) -> float:
    """美式 call 封閉解本體（cost of carry b=r-q）。呼叫端負責 put 的
    put-call symmetry 轉換（`S↔K`、`r↔q`）——BS93 對美式 put 的標準
    處理方式，逐字對照 QuantLib `calculate()` 的 swap 邏輯。"""
    variance = sigma * sigma * T
    rfD = math.exp(-r * T)
    dD = math.exp(-q * T)
    bT = math.log(dD / rfD)      # = (r-q)*T
    rT = math.log(1.0 / rfD)     # = r*T

    # q<=0（b>=r）時提前履約永不最優，退化為歐式——這一支同時是「唯一
    # 兩個數值防護」的第一層 fallback 目標，寫在最前面。QuantLib 原始碼
    # 在 calculate() 用 dividendDiscount>=1 && dividendDiscount>=
    # riskFreeDiscount 判斷；代入 rT/bT 後對 r>=0（本專案唯一會出現的
    # 情況：Treasury 期限利率恆為正）與這個 bT>=rT 判準完全等價，
    # 唯一分歧點（r<q<0 的雙邊界病態情形）QuantLib 選擇直接拋錯，
    # 本函式選擇同樣退回歐式——純函式不拋錯是本專案既有慣例。
    if bT >= rT:
        return merton_price("call", S, K, T, r, q, sigma)

    european = merton_price("call", S, K, T, r, q, sigma)

    beta = (0.5 - bT / variance) + math.sqrt(
        (bT / variance - 0.5) ** 2 + 2.0 * rT / variance)
    b_inf = beta / (beta - 1.0) * K
    b_zero = K if bT == rT else max(K, rT / (rT - bT) * K)

    # 數值防護 1／2：b_inf − b_zero → 0（trigger price 的邊界收斂到單點，
    # h(T) 除以幾乎是 0 的分母）。實測會直接 OverflowError／發散，
    # 退回歐式（有定義、且是 beta→∞ 時的極限值）。
    denom = b_inf - b_zero
    if abs(denom) < 1e-10:
        return european

    ht = -(bT + 2.0 * math.sqrt(variance)) * b_zero / denom
    trigger = b_zero + (b_inf - b_zero) * (1.0 - math.exp(ht))

    if S >= trigger:
        value = S - K  # 立即履約價值
    else:
        fwd = S * dD / rfD
        # 數值防護 2／2：beta 過大／trigger price 邊界失控（QuantLib
        # 原始碼註解原文："We have a run away exercise boundary. It is
        # numerically more accurate to use the Greeks of the European
        # engine."）——同一判準、同一處理方式，退回歐式而不是讓後面的
        # (I/S)**kappa 溢位。
        q_check = math.log(trigger / fwd) / math.sqrt(variance)
        if q_check > 12.5:
            value = european
        else:
            value = (
                (trigger - K) * (S / trigger) ** beta
                * (1.0 - _bs93_phi(S, beta, trigger, trigger, rT, bT, variance))
                + S * _bs93_phi(S, 1.0, trigger, trigger, rT, bT, variance)
                - S * _bs93_phi(S, 1.0, K, trigger, rT, bT, variance)
                - K * _bs93_phi(S, 0.0, trigger, trigger, rT, bT, variance)
                + K * _bs93_phi(S, 0.0, K, trigger, rT, bT, variance)
            )
    # QuantLib 原始碼收尾一致：這個「取歐式與較大值」的收尾對**三個分支
    # 全部**適用，不只 phi 公式那一支——深度價內＋高波動的短天期組合下，
    # 立即履約分支算出的 trigger price 有時會落在真正最適履約邊界之內，
    # 讓 S-K 反而低於歐式連續持有的價值；沒有這一步時 American < European
    # 會直接違反「美式恆 ≥ 歐式」這個不需要任何模型就知道的不變量
    # （原始移植時漏放在 if/else 外層，已用隨機參數掃描抓出並修正）。
    return max(value, european)


def american_price(option_type: str, S: float, K: float, T: float, r: float,
                   q: float, sigma: float) -> float:
    """美式選擇權封閉解近似（Bjerksund–Stensland 1993），含連續股利殖利率
    q。純函式、純 stdlib，無新依賴。

    q<=0 時對 call **逐位元**退化成 `merton_price("call", ...)`——見
    `_bs93_call_core` 最前面那個分支，這是研究文件（`docs/research/
    heatmap-valuation-method-selection.md` §10-1）明文要求的不變量，
    由 `test_american_pricing.py` 直接斷言差為 0.0。

    Put 走 put-call symmetry（`S↔K`、`r↔q`，同一個 call 核心函式），
    這是 BS93 對美式 put 的標準處理方式，不是另外一套公式——因此 put
    的「何時退化成歐式」判準是 r<=0（不是 q<=0，兩者互為對偶：call
    的提前履約誘因來自股利，put 的提前履約誘因來自把履約價現金提早
    拿去生息，見 valuation-method-selection.md §10-2 第 4 點的討論）。

    任何數值溢位（beta 溢位、trigger price 邊界失控等，兩個防護已在
    `_bs93_call_core` 內攔截，這裡的 try/except 是最後一道保險）一律
    收斂成歐式解——純函式不拋錯，是本專案既有慣例（`data/cboe.py`
    的 FetchError 收斂同一精神）。最終結果永遠 clamp 到內在價值之上
    （不會低於立即履約可拿到的價值，也不會是負值）。
    """
    if T <= 0.0 or sigma <= 0.0:
        return intrinsic_value(option_type, S, K)
    try:
        if option_type == "put":
            raw = _bs93_call_core(K, S, T, q, r, sigma)
        else:
            raw = _bs93_call_core(S, K, T, r, q, sigma)
    except (OverflowError, ValueError, ZeroDivisionError):
        raw = merton_price(option_type, S, K, T, r, q, sigma)
    return max(raw, intrinsic_value(option_type, S, K), 0.0)


def implied_vol(option_type: str, target_price: float, S: float, K: float,
                T: float, r: float, q: float,
                lo: float = 1e-6, hi: float = 5.0) -> float | None:
    """從市場中價反解 σ，使 `american_price(...)` 重現 `target_price`
    （同模型逐腿反解＋價格錨定，見研究文件 §10-1／§10-3）。

    二分法：`american_price` 對 sigma 單調遞增（標準性質，call／put
    皆成立），不需要導數、不需要初始猜值。找不到解時回傳 `None`——
    「目標價落在模型可行區間外」是真實會發生的情況（研究文件 §4.2：
    q=0 時多數近價位 LEAPS call 的 IV 反解在數學上無解），呼叫端必須
    把 `None` 當成「這條腿反解失敗」處理、不得外插或亂猜一個數字
    （沿用本專案「缺席就如實缺席、不偽造數值」的既有原則）。
    """
    if T <= 0.0 or target_price <= 0.0:
        return None
    price_lo = american_price(option_type, S, K, T, r, q, lo)
    price_hi = american_price(option_type, S, K, T, r, q, hi)
    if not (price_lo <= target_price <= price_hi):
        return None
    # 只在 sigma 區間本身收斂到極小才提早退出，不靠價格容忍度提早退出：
    # 深價內／深價外附近價格對 sigma 的敏感度（vega）可能很小，只看
    # 「價格夠近了」會在區間還很寬時就停手，讓反解出的 sigma 不準確
    # （曾實測近價位候選最大誤差達 0.0625 vol pt，遠高於預期）。改成
    # 純粹依區間寬度收斂，48 次已把寬度壓到 ~2e-11（(5-1e-6)/2^48）。
    for _ in range(60):
        if hi - lo < 1e-12:
            break
        mid = (lo + hi) / 2.0
        price_mid = american_price(option_type, S, K, T, r, q, mid)
        if price_mid < target_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def catchup_price(strike: float, call_cost: float, baseline_return: float) -> float:
    """D1（#14）：所選 Spread 的 Long Call 追平價格 S*＝K＋C×(1+R)——標的要
    漲到哪個價格，同履約價 K 的 Long Call 持有至到期的報酬率才追得上這組
    Spread 的目標情境到期報酬率 R。K＝買腿履約價，C＝同快照中該 Call 的
    實際成本（Ask，worst 成本口徑，見 T12／附錄A14.2），R＝該 Spread 的
    baseline_return。封閉式算術，不需估值引擎。"""
    return strike + call_cost * (1 + baseline_return)


def spread_guidance_judgments(sv: SpreadValuation, p: AnalysisParams) -> list[str]:
    """Spec §3.4: spreads have NO L1; L2 is the scenario envelope minimum."""
    msgs: list[str] = []
    if sv.net_worst > sv.l2:
        msgs.append(f"劇本成立但最保守 IV 情境下仍虧損（IV 情境最低值 ${sv.l2:.2f}）")
    if sv.net_worst > sv.l3:
        msgs.append("以最差進場成本達不到你設定的最低報酬（min-return）")
    return msgs


# ---------- T15（#230，Initial V2 spec #217）：Butterfly——只服務這個
# 結構自己的邏輯，不透過任何通用跨 strategy 的 payoff-envelope／extrema
# 引擎（#223 已判定 Initial V2 不需要，正式收斂為 not planned）。買一口
# 低履約價（K1）、賣兩口中間履約價（K2）、買一口高履約價（K3），
# call／put 兩個 subtype 共用同一套結構與算式（`intrinsic_value()` 已
# 吸收兩者差異）。 ----------


@dataclass(frozen=True)
class ButterflyProfitRegion:
    """到期時 payoff 高於進場成本（`net_worst`）的標的價範圍，左右邊界
    各自是這個結構自己的分段線性交叉點（見
    `butterfly_breakeven_and_profit_region()` docstring）。"""
    lower: float
    upper: float


def butterfly_expiry_payoff(option_type: str, k1: float, k2: float, k3: float,
                            S: float) -> float:
    """到期時的獲利（1 口買 K1、2 口賣 K2、1 口買 K3），純算術。

    `intrinsic_value()` 已經處理了 call／put 的差異，這個公式本身對
    兩種權別通用；k1<k2<k3 是呼叫端的既有前提（`generate_butterfly_
    triples()` 依履約價排序後才組成三元組），這裡不重複驗證。"""
    return (intrinsic_value(option_type, S, k1)
           - 2.0 * intrinsic_value(option_type, S, k2)
           + intrinsic_value(option_type, S, k3))


def _butterfly_knots(option_type: str, k1: float, k2: float,
                     k3: float) -> tuple[float, float, float]:
    """三個履約價各自的到期 payoff（`v1`＝K1、`v2`＝K2 峰值、`v3`＝K3），
    只算一次——`butterfly_breakeven_and_profit_region()` 與
    `evaluate_butterfly()` 都需要這三個數字，抽出來避免兩處各自呼叫
    `butterfly_expiry_payoff()` 三次（`/code-review` Standards 軸抓到
    的重複）。"""
    return (butterfly_expiry_payoff(option_type, k1, k2, k3, k1),
           butterfly_expiry_payoff(option_type, k1, k2, k3, k2),
           butterfly_expiry_payoff(option_type, k1, k2, k3, k3))


def _butterfly_region_from_knots(
    k1: float, k2: float, k3: float, v1: float, v2: float, v3: float,
    net_cost: float,
) -> tuple[tuple[float, ...], ButterflyProfitRegion | None]:
    """`butterfly_breakeven_and_profit_region()` 的核心邏輯，改吃已經
    算好的三個到期 payoff 節點（`v1`／`v2`／`v3`）而非自己重算——供
    `evaluate_butterfly()` 在已經算過一次 `_butterfly_knots()` 之後
    直接複用，不必為了呼叫這個公開函式再算第二次（`/code-review`
    Standards 軸抓到的重複，此為完整消除，非表面上少寫幾行）。

    Butterfly 專屬（不透過任何通用求根／extrema 引擎）：到期時的
    payoff 是分段線性、非單調的「帳篷」形狀——不論 call 或 put、不論
    兩翼是否等寬，[K1,K2] 段斜率恆為 +1、[K2,K3] 段斜率恆為 -1（可由
    「買一賣二買一」的權重組合直接推導：兩段各自只有一條腿的斜率係數
    尚未被抵銷，且係數恰為 ±1），K1 之外與 K3 之外則各自恆定——這是
    這個特定權重結構（不是任意 N 腿組合）才有的不變量，因此兩個損益
    兩平點可以用封閉式代數直接求出，不需要迭代逼近或通用求根機制。

    峰值必然落在 K2（`v2 = v1 + (K2-K1)` 恆 > v1、`v2 = v3 + (K3-K2)`
    恆 > v3，因為 K1<K2<K3），若峰值扣掉成本仍 <= 0，代表**連峰值都
    賺不到**，到期時任何價位都無法獲利——回傳空的損益兩平點與 `None`
    （不硬擠成一個假的區間）。

    峰值有獲利空間時，左／右兩個交叉點各自落在峰值左側／右側的線性
    段上；若某一側的翼端本身已經獲利（該側翼端的成本方是負值，即
    `v1 - net_cost >= 0` 或 `v3 - net_cost >= 0`——這只在履約價明顯
    不對稱、俗稱「broken wing」的組合上才可能發生），該側就沒有落在
    對應線性段內的真交叉點，這裡用該側翼端履約價（K1／K3）本身當
    邊界——這是這個已知邊界情況的合理近似（獲利region 實際上延伸到
    該翼端之外的恆定平台，見函式頂端的段落分析），不是憑空發明的
    容忍值。"""
    peak_profit = v2 - net_cost
    if peak_profit <= 0.0:
        return (), None
    left_tail_profit = v1 - net_cost
    right_tail_profit = v3 - net_cost
    # [K1,K2] 斜率恆 +1：f(S) = left_tail_profit + (S-K1)，根 = K1 - left_tail_profit
    lower = k1 if left_tail_profit >= 0.0 else k1 - left_tail_profit
    # [K2,K3] 斜率恆 -1：f(S) = peak_profit - (S-K2)，根 = K2 + peak_profit
    upper = k3 if right_tail_profit >= 0.0 else k2 + peak_profit
    return (lower, upper), ButterflyProfitRegion(lower=lower, upper=upper)


def butterfly_breakeven_and_profit_region(
    option_type: str, k1: float, k2: float, k3: float, net_cost: float,
) -> tuple[tuple[float, ...], ButterflyProfitRegion | None]:
    """公開進入點：算一次 `_butterfly_knots()`，交給
    `_butterfly_region_from_knots()` 做核心判斷。簽章維持不變（不吃
    現成節點），供只有履約價、沒有算過節點的呼叫端直接使用；已經算過
    節點的呼叫端（`evaluate_butterfly()`）改直接呼叫
    `_butterfly_region_from_knots()` 避免重算。"""
    v1, v2, v3 = _butterfly_knots(option_type, k1, k2, k3)
    return _butterfly_region_from_knots(k1, k2, k3, v1, v2, v3, net_cost)


@dataclass(frozen=True)
class ButterflyValuation:
    option_type: str
    low_leg: OptionContract     # K1，買 1 口
    mid_leg: OptionContract     # K2，賣 2 口
    high_leg: OptionContract    # K3，買 1 口
    net_mid: float
    net_worst: float
    net_delta: float
    effective_leverage: float
    breakeven_points: tuple[float, ...]
    profit_region: ButterflyProfitRegion | None
    scenario_values: tuple[tuple[float, float], ...]
    baseline_value: float
    l2: float
    l3: float
    max_profit: float
    # 到期時最壞可能損失（`net_worst - min(兩翼到期值)`）——**不假設**
    # 恆等於 `net_worst`：兩翼等寬（對稱蝶式）時兩者確實相等，但不對稱
    # 履約價組合（broken wing）可能讓某一翼到期時價值為負，使最壞損失
    # 超過已付權利金本身。這是這個結構的真實性質，不是既有四策略
    # 「max_loss 恆等於成本」這條不變量的例外或錯誤，只是 Butterfly
    # 結構性地不保證這條不變量成立。
    max_loss: float
    low_carry: LegCarry
    mid_carry: LegCarry
    high_carry: LegCarry


def butterfly_scenario_value(
    low_leg: OptionContract, mid_leg: OptionContract, high_leg: OptionContract,
    S: float, at: date, p: AnalysisParams, shift: float = 0.0,
    low_carry: LegCarry | None = None, mid_carry: LegCarry | None = None,
    high_carry: LegCarry | None = None,
) -> float:
    """薄殼：把三腿包成 `WeightedLeg` 交給既有的、已核准的逐腿加總原語
    `payoff_value()`（T02／#219）——這不是新的通用引擎，`payoff_value`
    本身早已支援任意腿數，這裡只是 Butterfly 這個具體結構的呼叫慣例。"""
    legs = (
        WeightedLeg(contract=low_leg, sign=1.0, quantity=1, carry=low_carry),
        WeightedLeg(contract=mid_leg, sign=-1.0, quantity=2, carry=mid_carry),
        WeightedLeg(contract=high_leg, sign=1.0, quantity=1, carry=high_carry),
    )
    return payoff_value(legs, S, at, p, shift)


def evaluate_butterfly(
    low_leg: OptionContract, mid_leg: OptionContract, high_leg: OptionContract,
    spot: float, today: date, p: AnalysisParams,
    carry_cache: dict[tuple, LegCarry] | None = None,
) -> ButterflyValuation:
    """`evaluate_spread()` 的三腿版本——同一套既有裁示逐條延伸：
    worst 成交口徑（附錄 A14.2：買腿 Ask、賣腿 Bid，中腿口數 2）、
    排名情境＝標的在**自身到期日**等於目標價（T3／#17），breakeven／
    max_profit／max_loss 由這個結構自己的分段線性性質直接算（見
    `butterfly_breakeven_and_profit_region()`），不透過任何通用機制。

    `carry_cache`：REPAIR-03（#240，#052 audit）——`generate_butterfly_
    triples()` 窮舉出的 `C(n,3)` 組合讓同一條腿平均出現 `C(n-1,2)` 次，
    是三個估值函式裡重複度最高的一個（production-scale 規模下這是
    60 秒 timeout 的主因）。傳入呼叫端貫穿單次 `_butterfly_result()`
    的字典即可對同一條腿只反解一次；不傳（預設）行為不變，見
    `calibrate_leg()` docstring。
    """
    net_mid = ((low_leg.bid + low_leg.ask) / 2.0
              - 2.0 * (mid_leg.bid + mid_leg.ask) / 2.0
              + (high_leg.bid + high_leg.ask) / 2.0)
    net_worst = low_leg.ask - 2.0 * mid_leg.bid + high_leg.ask
    expiry = date.fromisoformat(low_leg.expiry)
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    low_carry = calibrate_leg(low_leg, spot, today, p, carry_cache)
    mid_carry = calibrate_leg(mid_leg, spot, today, p, carry_cache)
    high_carry = calibrate_leg(high_leg, spot, today, p, carry_cache)
    g_lo = leg_greeks(low_leg.option_type, spot, low_leg.strike, t_now,
                      leg_rate(p, low_leg.expiry), low_carry.sigma, low_carry.q)
    g_mid = leg_greeks(mid_leg.option_type, spot, mid_leg.strike, t_now,
                       leg_rate(p, mid_leg.expiry), mid_carry.sigma, mid_carry.q)
    g_hi = leg_greeks(high_leg.option_type, spot, high_leg.strike, t_now,
                      leg_rate(p, high_leg.expiry), high_carry.sigma, high_carry.q)
    net_delta = g_lo.delta - 2.0 * g_mid.delta + g_hi.delta
    # 需求 §三／T3／#17 既有裁示：排名情境＝標的在自身到期日等於目標價。
    scenario_values = tuple(
        (shift, butterfly_scenario_value(low_leg, mid_leg, high_leg,
                                         p.target_price, expiry, p, shift,
                                         low_carry, mid_carry, high_carry))
        for shift in p.iv_shifts)
    baseline_value = dict(scenario_values)[0.0]
    # 三個履約價各自的到期 payoff 只算一次（`_butterfly_knots()`），供
    # breakeven／profit region 與 max_profit／max_loss 共用——原本
    # `butterfly_breakeven_and_profit_region()` 內部會重算一次、這裡
    # 又為了 max_profit／max_loss 各自呼叫 `butterfly_expiry_payoff()`
    # 三次，是 `/code-review` Standards 軸抓到的重複，改直接呼叫
    # `_butterfly_region_from_knots()` 複用同一組節點。
    v1, v2, v3 = _butterfly_knots(
        low_leg.option_type, low_leg.strike, mid_leg.strike, high_leg.strike)
    breakeven_points, profit_region = _butterfly_region_from_knots(
        low_leg.strike, mid_leg.strike, high_leg.strike, v1, v2, v3, net_worst)
    max_profit = v2 - net_worst   # 峰值必然在 K2，見上方 docstring
    max_loss = net_worst - min(v1, v3)
    return ButterflyValuation(
        option_type=low_leg.option_type,
        low_leg=low_leg, mid_leg=mid_leg, high_leg=high_leg,
        net_mid=net_mid, net_worst=net_worst, net_delta=net_delta,
        effective_leverage=abs(net_delta) * spot / net_worst,
        breakeven_points=breakeven_points, profit_region=profit_region,
        scenario_values=scenario_values, baseline_value=baseline_value,
        l2=min(v for _, v in scenario_values),
        l3=baseline_value / (1.0 + p.min_return),
        max_profit=max_profit, max_loss=max_loss,
        low_carry=low_carry, mid_carry=mid_carry, high_carry=high_carry,
    )


def butterfly_guidance_judgments(bv: ButterflyValuation, p: AnalysisParams) -> list[str]:
    """比照 `spread_guidance_judgments()` 同一套判準（無 L1，L2＝情境
    包絡最小值）。"""
    msgs: list[str] = []
    if bv.net_worst > bv.l2:
        msgs.append(f"劇本成立但最保守 IV 情境下仍虧損（IV 情境最低值 ${bv.l2:.2f}）")
    if bv.net_worst > bv.l3:
        msgs.append("以最差進場成本達不到你設定的最低報酬（min-return）")
    return msgs
