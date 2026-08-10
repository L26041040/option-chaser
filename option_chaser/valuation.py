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


def call_greeks(S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §5.5. Caller guarantees T > 0 (filters ensure expiry > today)."""
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        - r * K * math.exp(-r * T) * norm_cdf(d2)
    )
    return Greeks(
        delta=norm_cdf(d1),
        gamma=norm_pdf(d1) / (S * st),
        theta_per_day=theta_year / DAYS_PER_YEAR,
        vega_per_pct=S * norm_pdf(d1) * math.sqrt(T) / 100.0,
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
class ContractValuation:
    contract: OptionContract
    mid: float
    spread: float
    delta: float
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


def scenario_leg_value(
    c: OptionContract, S: float, at: date, p: AnalysisParams, shift: float = 0.0
) -> float:
    """Spec §3 valuation primitive: value of one leg at date `at` with spot S."""
    expiry = date.fromisoformat(c.expiry)
    if at >= expiry:
        return intrinsic_value(c.option_type, S, c.strike)
    T = days_between(at, expiry) / DAYS_PER_YEAR
    return clamped_price(c.option_type, S, c.strike, T, leg_rate(p, c.expiry),
                         c.implied_volatility * (1.0 + shift))


def evaluate_contract(
    c: OptionContract, spot: float, today: date, p: AnalysisParams
) -> ContractValuation:
    assert c.bid is not None and c.ask is not None and c.implied_volatility is not None
    mid = (c.bid + c.ask) / 2.0
    spread = c.ask - c.bid
    expiry = date.fromisoformat(c.expiry)
    target = p.anchor          # 附錄 A9 錨點：估值參考日
    g = leg_greeks(c.option_type, spot, c.strike,
                   days_between(today, expiry) / DAYS_PER_YEAR,
                   leg_rate(p, c.expiry), c.implied_volatility)
    scenario_values = tuple(
        (shift, scenario_leg_value(c, p.target_price, target, p, shift))
        for shift in p.iv_shifts
    )
    baseline_value = dict(scenario_values)[0.0]
    floor_value = intrinsic_value(c.option_type, p.target_price, c.strike)
    # T12（附錄 A14.2）：主數字成本口徑＝最差成交假設（單腿＝Ask）。
    # breakeven／槓桿等成本衍生數字同口徑；mid 保留為次要顯示。
    if c.option_type == "call":
        breakeven = c.strike + c.ask
        be_vs_spot = (breakeven - spot) / spot
        be_vs_target = (p.target_price - breakeven) / p.target_price
    else:
        breakeven = c.strike - c.ask
        be_vs_spot = (spot - breakeven) / spot
        be_vs_target = (breakeven - p.target_price) / p.target_price
    l2 = scenario_leg_value(c, p.target_price, target, p, min(p.iv_shifts))
    return ContractValuation(
        contract=c, mid=mid, spread=spread,
        delta=g.delta, gamma=g.gamma, theta_per_day=g.theta_per_day,
        vega_per_pct=g.vega_per_pct,
        breakeven=breakeven, breakeven_vs_spot=be_vs_spot,
        breakeven_vs_target=be_vs_target,
        effective_leverage=abs(g.delta) * spot / c.ask,
        floor_value=floor_value, scenario_values=scenario_values,
        baseline_value=baseline_value,
        l1=floor_value, l2=l2, l3=baseline_value / (1.0 + p.min_return),
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
    """Spec §3.2: American no-arbitrage floor applied to every valuation output."""
    return max(bs_price(option_type, S, K, T, r, sigma), intrinsic_value(option_type, S, K), 0.0)


def leg_greeks(option_type: str, S: float, K: float, T: float, r: float, sigma: float) -> Greeks:
    """Spec §3.1. Caller guarantees T > 0."""
    g = call_greeks(S, K, T, r, sigma)
    if option_type == "call":
        return g
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    theta_year_put = (
        -(S * norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
        + r * K * math.exp(-r * T) * norm_cdf(-d2)
    )
    return Greeks(
        delta=g.delta - 1.0,
        gamma=g.gamma,
        theta_per_day=theta_year_put / DAYS_PER_YEAR,
        vega_per_pct=g.vega_per_pct,
    )


def spread_scenario_value(
    long_leg: OptionContract, short_leg: OptionContract,
    S: float, at: date, p: AnalysisParams, shift: float = 0.0,
) -> float:
    width = abs(short_leg.strike - long_leg.strike)
    raw = (scenario_leg_value(long_leg, S, at, p, shift)
           - scenario_leg_value(short_leg, S, at, p, shift))
    return min(max(raw, 0.0), width)


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


def evaluate_spread(
    long_leg: OptionContract, short_leg: OptionContract,
    spot: float, today: date, p: AnalysisParams,
) -> SpreadValuation:
    width = abs(short_leg.strike - long_leg.strike)
    net_mid = (long_leg.bid + long_leg.ask) / 2.0 - (short_leg.bid + short_leg.ask) / 2.0
    net_worst = long_leg.ask - short_leg.bid
    expiry = date.fromisoformat(long_leg.expiry)
    t_now = days_between(today, expiry) / DAYS_PER_YEAR
    g_l = leg_greeks(long_leg.option_type, spot, long_leg.strike, t_now,
                     leg_rate(p, long_leg.expiry), long_leg.implied_volatility)
    g_s = leg_greeks(short_leg.option_type, spot, short_leg.strike, t_now,
                     leg_rate(p, short_leg.expiry), short_leg.implied_volatility)
    net_delta = g_l.delta - g_s.delta
    # 需求 §三：排名情境＝標的在該 Spread **自身到期日**等於目標價、持有至到期。
    # 估值日即 expiry → 內在價值；IV shift 到期時無作用，情境向量同值屬必然。
    scenario_values = tuple(
        (shift, spread_scenario_value(long_leg, short_leg, p.target_price, expiry, p, shift))
        for shift in p.iv_shifts
    )
    baseline = dict(scenario_values)[0.0]
    # T12（附錄 A14.2）：主數字成本口徑＝net_worst（買腿 Ask − 賣腿 Bid），
    # 定位「保守成交假設收益」。breakeven／最大獲利／槓桿同口徑；net_mid
    # 保留為次要顯示。
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
