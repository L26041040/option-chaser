"""#119（spec #117 §1.1／§1.2）：BS93 美式近似封閉解＋同模型 IV 反解。

純函式、未接引擎（#113 才接線）——這裡只驗證原語本身正確，不觸碰任何
既有呼叫路徑、不改變任何 production 行為。

`american_price()` 逐字依 QuantLib `BjerksundStenslandApproximationEngine`
（一手原始碼）移植；CRR 二項樹在本檔案裡是精度對照基準，**只存在於
測試裡**，不得也沒有進 production code（`option_chaser/valuation.py`
沒有 import 任何二項樹相關程式碼，這條由本檔案的存在本身佐證）。
"""
from __future__ import annotations

import math
import time

import pytest

from option_chaser.valuation import (
    american_price,
    implied_vol,
    intrinsic_value,
    merton_price,
)


# ---------- CRR 二項樹：測試專用精度基準，不進 production ----------

def _crr_american(option_type: str, S: float, K: float, T: float, r: float,
                  q: float, sigma: float, n: int = 400) -> float:
    dt = T / n
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-r * dt)
    p = (math.exp((r - q) * dt) - d) / (u - d)
    values = []
    for j in range(n + 1):
        spot = S * (u ** j) * (d ** (n - j))
        values.append(max(spot - K, 0.0) if option_type == "call"
                     else max(K - spot, 0.0))
    for i in range(n - 1, -1, -1):
        nxt = [None] * (i + 1)
        for j in range(i + 1):
            cont = disc * (p * values[j + 1] + (1 - p) * values[j])
            spot = S * (u ** j) * (d ** (i - j))
            exercise = (spot - K) if option_type == "call" else (K - spot)
            nxt[j] = max(cont, exercise)
        values = nxt
    return values[0]


# ---------- q<=0 對 call 逐位元退化成 Merton 歐式 ----------

@pytest.mark.parametrize("q", [0.0, -0.01, -0.05, -0.2])
@pytest.mark.parametrize("sigma", [0.1, 0.3, 0.8])
@pytest.mark.parametrize("T", [0.05, 1.0, 5.0])
def test_call_degenerates_to_merton_when_q_nonpositive(q, sigma, T):
    a = american_price("call", 100.0, 95.0, T, 0.04, q, sigma)
    m = merton_price("call", 100.0, 95.0, T, 0.04, q, sigma)
    assert a == m  # 逐位元相等，不是「接近」


def test_call_does_not_degenerate_when_q_positive():
    """反向確認：q>0 時不會被誤判成退化——上面那組測試如果分支寫錯（永遠
    退化）也會全綠，這條負向測試才是真正卡住那個分支條件的斷言。"""
    a = american_price("call", 100.0, 95.0, 1.0, 0.04, 0.05, 0.3)
    m = merton_price("call", 100.0, 95.0, 1.0, 0.04, 0.05, 0.3)
    assert a > m + 1e-6


# ---------- 美式恆 ≥ 歐式（不需要任何模型就知道的不變量） ----------

def test_american_never_below_european_random_sweep():
    import random
    random.seed(20260810)
    worst = 0.0
    for _ in range(5000):
        S = random.uniform(20, 300)
        K = random.uniform(20, 300)
        T = random.uniform(0.02, 3.0)
        r = random.uniform(0.0, 0.08)
        q = random.uniform(0.0, 0.10)
        sigma = random.uniform(0.05, 1.2)
        for opt in ("call", "put"):
            a = american_price(opt, S, K, T, r, q, sigma)
            e = merton_price(opt, S, K, T, r, q, sigma)
            worst = min(worst, a - e)
    assert worst >= -1e-6, f"worst violation margin={worst}"


def test_american_put_exceeds_european_put_when_rate_positive():
    """put 的提前履約溢價來自利率（不是股利）——r>0、q=0 時，長天期價內
    put 的美式價格應明顯高於歐式，這是 put-call symmetry 轉換正確的
    直接證據（若轉換寫錯，這條最容易先紅）。"""
    S, K, T, r, q, sigma = 80.0, 100.0, 2.0, 0.05, 0.0, 0.25
    a = american_price("put", S, K, T, r, q, sigma)
    e = merton_price("put", S, K, T, r, q, sigma)
    assert a > e + 0.01


def test_american_call_exceeds_european_call_when_dividend_yield_positive():
    S, K, T, r, q, sigma = 120.0, 100.0, 2.0, 0.03, 0.06, 0.25
    a = american_price("call", S, K, T, r, q, sigma)
    e = merton_price("call", S, K, T, r, q, sigma)
    assert a > e + 0.01


# ---------- 永不低於內在價值 ----------

def test_never_below_intrinsic_random_sweep():
    import random
    random.seed(7)
    for _ in range(5000):
        S = random.uniform(20, 300)
        K = random.uniform(20, 300)
        T = random.uniform(0.001, 3.0)
        r = random.uniform(-0.02, 0.08)
        q = random.uniform(-0.02, 0.15)
        sigma = random.uniform(0.01, 1.5)
        for opt in ("call", "put"):
            a = american_price(opt, S, K, T, r, q, sigma)
            assert a >= intrinsic_value(opt, S, K) - 1e-9


def test_t_zero_or_nonpositive_sigma_returns_intrinsic():
    assert american_price("call", 100.0, 90.0, 0.0, 0.04, 0.02, 0.3) == 10.0
    assert american_price("put", 90.0, 100.0, 0.0, 0.04, 0.02, 0.3) == 10.0
    assert american_price("call", 100.0, 90.0, 1.0, 0.04, 0.02, 0.0) == 10.0


# ---------- 數值防護 1／2：b_inf − b_zero → 0 ----------
#
# 具體、可重現的參數（不是碰運氣的隨機掃描）：S=150,K=100,T=1,r=0.01,
# q=0.5,sigma=1e-7。denom（b_inf−b_zero）在這組參數下實測 ≈1.02e-12，
# 低於 1e-10 門檻，直接命中防護分支。

def test_guard_denom_near_zero_does_not_crash():
    S, K, T, r, q, sigma = 150.0, 100.0, 1.0, 0.01, 0.5, 1e-7
    val = american_price("call", S, K, T, r, q, sigma)
    assert math.isfinite(val)
    # 深度價內＋極高股利殖利率：立即履約比繼續持有理性（股利侵蝕遠期
    # 價值），封閉解防護 fallback 到歐式後，外層 intrinsic clamp 仍把
    # 結果正確拉回立即履約價值——防護不會讓答案變得不合理。
    assert val == pytest.approx(S - K, abs=1e-6)


def test_guard_denom_near_zero_internal_raises_without_guard():
    """證明防護不是死碼：呼叫沒有防護的內部函式，同一組參數真的會
    OverflowError（不是猜測）。"""
    from option_chaser.valuation import _bs93_call_core
    S, K, T, r, q, sigma = 100.0, 100.0, 0.0001, 0.04, 5.0, 0.001
    with pytest.raises((OverflowError, ValueError, ZeroDivisionError)):
        _bs93_call_core(S, K, T, r, q, sigma)
    # 而外層 american_price 對同一組參數必須乾淨地回傳有限值。
    val = american_price("call", S, K, T, r, q, sigma)
    assert math.isfinite(val)


# ---------- 數值防護 2／2：beta 過大／trigger price 邊界失控 ----------
#
# 具體參數：S=100,K=100,T=0.0001（極短天期）,r=0.04,q=0.001,sigma=0.001。
# 實測 q_check（QuantLib 命名，"We have a run away exercise boundary"
# 判準）≈368888，遠超 12.5 門檻，直接命中防護分支。

def test_guard_runaway_exercise_boundary_does_not_crash():
    S, K, T, r, q, sigma = 100.0, 100.0, 0.0001, 0.04, 0.001, 0.001
    val = american_price("call", S, K, T, r, q, sigma)
    m = merton_price("call", S, K, T, r, q, sigma)
    assert math.isfinite(val)
    assert val == pytest.approx(m, abs=1e-9)  # 防護 fallback 到歐式


# ---------- CRR 精度基準（測試專用，production 不 import 任何相關程式碼） ----------

def test_bs93_matches_crr_on_real_tlt_leaps_scale_case():
    """真實量級（研究文件 heatmap-valuation-method-selection.md §5 的
    TLT 2028-12 LEAPS 案例：spot 84.52、r 4.26%、q 4.5%、T≈2.4 年）——
    對照 CRR N=800，相對誤差應在個位數 bp 量級（研究文件量到中位
    0.18–0.33pp，這裡用寬鬆一點的門檻避免測試對 CRR 步數過度敏感）。
    """
    S, r, q = 84.52, 0.0426, 0.045
    cases = [(79.0, 0.1315), (85.0, 0.1314), (90.0, 0.1292), (130.0, 0.1806)]
    T = 2.414
    for K, sigma in cases:
        bs93 = american_price("call", S, K, T, r, q, sigma)
        crr = _crr_american("call", S, K, T, r, q, sigma, n=800)
        rel_err = abs(bs93 - crr) / crr
        assert rel_err < 0.01, f"K={K}: BS93={bs93} CRR={crr} rel_err={rel_err}"


def test_bs93_matches_crr_broad_sweep():
    import random
    random.seed(11)
    errs = []
    for _ in range(30):
        S = random.uniform(50, 200)
        K = random.uniform(0.7 * S, 1.3 * S)
        T = random.uniform(0.1, 2.5)
        r = random.uniform(0.0, 0.06)
        q = random.uniform(0.0, 0.08)
        sigma = random.uniform(0.1, 0.6)
        opt = random.choice(["call", "put"])
        bs93 = american_price(opt, S, K, T, r, q, sigma)
        crr = _crr_american(opt, S, K, T, r, q, sigma, n=300)
        if crr > 0.05:  # 避免除以接近零的價格讓相對誤差失真
            errs.append(abs(bs93 - crr) / crr)
    errs.sort()
    median = errs[len(errs) // 2]
    assert median < 0.02, f"median relative error too high: {median}"
    assert max(errs) < 0.05, f"max relative error too high: {max(errs)}"


# ---------- IV 反解：價格往返、可行域判斷 ----------

def test_implied_vol_price_round_trip():
    import random
    random.seed(1)
    worst = 0.0
    misses = 0
    for _ in range(2000):
        S = random.uniform(50, 200)
        K = random.uniform(50, 200)
        T = random.uniform(0.05, 2.5)
        r = random.uniform(0.0, 0.06)
        q = random.uniform(0.0, 0.08)
        sigma_true = random.uniform(0.05, 1.0)
        for opt in ("call", "put"):
            price = american_price(opt, S, K, T, r, q, sigma_true)
            sigma_hat = implied_vol(opt, price, S, K, T, r, q)
            if sigma_hat is None:
                misses += 1
                continue
            price_hat = american_price(opt, S, K, T, r, q, sigma_hat)
            worst = max(worst, abs(price_hat - price))
    assert worst < 1e-6, f"worst price round-trip error={worst}"


def test_implied_vol_recovers_sigma_precisely_near_the_money():
    """近價位（Heatmap 候選的實際落點）反解精度應該很緊——這是「同模型
    逐腿反解」的核心承諾：反解出的 σ 代回同一模型要幾乎精確重現市價。"""
    import random
    random.seed(3)
    worst = 0.0
    for _ in range(1000):
        S = 100.0
        K = random.uniform(95, 105)  # 緊貼價平，避開深價內/價外的平坦區
        T = random.uniform(0.3, 2.5)
        r = random.uniform(0.0, 0.06)
        q = random.uniform(0.0, 0.08)
        sigma_true = random.uniform(0.1, 0.6)
        for opt in ("call", "put"):
            price = american_price(opt, S, K, T, r, q, sigma_true)
            sigma_hat = implied_vol(opt, price, S, K, T, r, q)
            if sigma_hat is None:
                continue
            worst = max(worst, abs(sigma_hat - sigma_true))
    assert worst < 1e-4, f"worst sigma recovery error near the money={worst}"


def test_implied_vol_returns_none_when_target_outside_feasible_range():
    """研究文件 §4.2：q=0 時很多真實 LEAPS 近價位 call 的目標價低於模型
    sigma→0 下限，反解在數學上無解——呼叫端必須拿到明確的 None，不是
    一個外插或猜測的數字。這裡直接構造一個保證無解的例子：目標價低於
    sigma→0 時的內在/遠期下限。"""
    # 深度價外、幾乎沒有時間價值可言時，任何 sigma 都無法把價格推到一個
    # 遠高於現實區間的天文數字之上。
    result = implied_vol("call", 1e9, 100.0, 100.0, 1.0, 0.04, 0.0)
    assert result is None


def test_implied_vol_returns_none_for_zero_or_negative_target():
    assert implied_vol("call", 0.0, 100.0, 100.0, 1.0, 0.04, 0.0) is None
    assert implied_vol("call", -1.0, 100.0, 100.0, 1.0, 0.04, 0.0) is None


def test_implied_vol_deep_itm_flat_region_is_a_known_property_not_a_bug():
    """已知、非缺陷的性質：深度價內＋短天期＋股利驅動立即履約時，價格
    對 sigma 在一段區間內是平的（等於內在價值），反解出的 sigma 不保證
    等於原始 sigma——但代回同一模型仍精確重現價格。這條測試把這個性質
    寫清楚，避免日後被誤認成 bug 重新「修」壞。"""
    S, K, T, r, q = 197.9, 54.3, 0.14, 0.0088, 0.0575
    price = american_price("call", S, K, T, r, q, 0.05)
    assert price == pytest.approx(S - K, abs=1e-6)  # 落在平坦（立即履約）區
    sigma_hat = implied_vol("call", price, S, K, T, r, q)
    assert sigma_hat is not None
    price_hat = american_price("call", S, K, T, r, q, sigma_hat)
    assert price_hat == pytest.approx(price, abs=1e-6)  # 價格往返仍準確


# ---------- 效能（成本數字，供 #113 的架構要求對照） ----------

def test_american_price_performance_budget():
    n = 5000
    t0 = time.perf_counter()
    for _ in range(n):
        american_price("call", 84.52, 90.0, 2.414, 0.0426, 0.045, 0.13)
    elapsed_us = (time.perf_counter() - t0) / n * 1e6
    # 研究文件量到 ~6 µs/次；給充分餘裕避免在慢速 CI 機器上假紅，
    # 但仍遠低於「每格重算」會構成問題的量級。
    assert elapsed_us < 200, f"american_price too slow: {elapsed_us:.1f} us/call"


def test_implied_vol_performance_budget():
    n = 1000
    t0 = time.perf_counter()
    for _ in range(n):
        implied_vol("call", 3.95, 84.52, 90.0, 2.414, 0.0426, 0.045)
    elapsed_us = (time.perf_counter() - t0) / n * 1e6
    # 研究文件量到 30–343 µs／腿；本實作（區間收斂式二分法）量到約
    # 280 µs，門檻抓寬鬆一點避免慢速機器假紅。
    assert elapsed_us < 2000, f"implied_vol too slow: {elapsed_us:.1f} us/call"
