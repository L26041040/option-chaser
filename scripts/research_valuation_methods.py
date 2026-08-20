"""#110（決策 D1）研究用純函式：LEAPS 估值／carry 方法比較的計算原語。

**這個檔案不是引擎的一部分，`option_chaser/` 不 import 它**——#110 的
guardrail 明講不修改引擎既有行為，這裡的每個函式都是「另外一套，供
比較用」，即使將來某個方法被需求方核准鎖定，也是另開票把邏輯搬進
`option_chaser/valuation.py`，不是直接改這裡。

只依賴 stdlib + 直接重用 `option_chaser.valuation.norm_cdf`（純數學
primitive，重用它不等於修改引擎行為）。

對應的可重跑驗收測試在 `tests/test_research_valuation_carry.py`；完整
論述與引用見 `docs/research/valuation-carry-method-comparison.md`。
"""
from __future__ import annotations

import math

from option_chaser.valuation import norm_cdf


def bs_call_with_yield(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """Merton (1973) 股利殖利率調整版歐式 call。q=0 時退化成
    `option_chaser.valuation.bs_call`（同一條公式，只是多一項 q）。"""
    if T <= 0.0:
        return max(S - K, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def bs_put_with_yield(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """Merton 股利殖利率調整版歐式 put，與 `bs_call_with_yield` 同組公式。"""
    if T <= 0.0:
        return max(K - S, 0.0)
    st = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / st
    d2 = d1 - st
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * math.exp(-q * T) * norm_cdf(-d1)


def implied_vol_call(
    S: float, K: float, T: float, r: float, q: float, target_price: float,
    lo: float = 1e-4, hi: float = 5.0, tol: float = 1e-9, max_iter: int = 200,
) -> float | None:
    """對 `bs_call_with_yield` 二分法解隱含波動率，使模型價等於 `target_price`。

    `None` 表示 `target_price` 落在這組 (S,K,T,r,q) 參數下、任何非負波動率
    都到不了的區間——不是求解失敗，是**這組 carry 假設本身無法解釋這個
    市場價**（q=0 baseline 對本票 5 檔真實 TLT LEAPS 中 3 檔就是這個
    情況，見研究文件 §3.1）。呼叫端必須把 `None` 當成一個有意義的結果，
    不能當成例外吞掉。
    """
    f_lo = bs_call_with_yield(S, K, T, r, q, lo) - target_price
    f_hi = bs_call_with_yield(S, K, T, r, q, hi) - target_price
    if f_lo > 0.0 or f_hi < 0.0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = bs_call_with_yield(S, K, T, r, q, mid) - target_price
        if abs(f_mid) < tol:
            return mid
        if f_mid > 0.0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def call_floor_price(S: float, K: float, T: float, r: float, q: float = 0.0) -> float:
    """`bs_call_with_yield` 在 sigma→0 時的極限（該組 carry 假設下，這個
    履約價理論上能到的最低價）。用來判定「市場中價是否落在這個 carry
    假設的可行區間之外」，比逐一呼叫二分法更直接、也是二分法回傳 `None`
    的根本原因。"""
    return max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)


def implied_forward_from_parity(call_price: float, put_price: float, K: float, r: float, T: float) -> float:
    """Method D（put-call parity 隱含 forward）：F = K + (C-P)·e^{rT}。

    只提供公式本身供文件與可能的未來檢驗使用——**研究文件 §4 已用本 repo
    既有的真實全鏈 parity 分析（`docs/research/spread-synthetic-parity-check.md`）
    論證這個公式直接套用在美式 ETF options 上會被提前履約溢價汙染，本票
    因此不用這個函式去產生「推薦的」股利估計，只用它示範公式與失敗模式。
    """
    return K + (call_price - put_price) * math.exp(r * T)


def bootstrap_zero_curve(par_nodes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """半年配息公債序貫 bootstrap，求逐期連續複利 zero rate——用來獨立
    覆核 `option_chaser.ratecurve.par_to_continuous` 的直接近似公式
    （`r_cc = 2·ln(1+y/2)`，不 bootstrap）誤差有多大（研究文件 §5／AC
    第 4 點）。

    `par_nodes`：`(年期, par 殖利率小數)`，年期嚴格遞增、且皆為 0.5 的
    倍數（Treasury CMT 的半年複利慣例；本 repo 實際只用得到 1M–3Y，
    這裡驗到 10Y 純粹是量化「近似公式在超出本工具使用範圍後才開始
    明顯偏離」，不代表本工具需要那個範圍）。

    第一個節點（或任何 T<=0.5 的節點）視為零息單期，直接用
    `par_to_continuous` 同一條公式；之後每個節點用前面已 bootstrap
    出的 zero curve（相鄰節點線性插值）折現該公債的中間配息，解出
    讓公司債定價為面額 100 的最後一期 zero rate——教科書標準作法
    （見研究文件引用）。
    """
    zero_nodes: list[tuple[float, float]] = []

    def zero_at(t: float) -> float:
        if t <= zero_nodes[0][0]:
            return zero_nodes[0][1]
        if t >= zero_nodes[-1][0]:
            return zero_nodes[-1][1]
        for (t0, r0), (t1, r1) in zip(zero_nodes, zero_nodes[1:]):
            if t0 <= t <= t1:
                return r0 + (t - t0) * (r1 - r0) / (t1 - t0)
        raise AssertionError("unreachable：節點嚴格遞增且已夾住兩端")

    for tenor, par_yield in par_nodes:
        if tenor <= 0.5 or not zero_nodes:
            r_cc = 2.0 * math.log(1.0 + par_yield / 2.0)
            zero_nodes.append((tenor, r_cc))
            continue
        n_periods = round(tenor / 0.5)
        coupon = 100.0 * par_yield / 2.0
        pv_coupons = sum(
            coupon * math.exp(-zero_at(i * 0.5) * (i * 0.5))
            for i in range(1, n_periods)
        )
        remaining = 100.0 - pv_coupons
        r_cc = -math.log(remaining / (coupon + 100.0)) / tenor
        zero_nodes.append((tenor, r_cc))
    return zero_nodes
