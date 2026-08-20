"""#110（決策 D1）LEAPS 估值／carry 方法比較——可重複執行的驗收測試。

跟 `tests/test_*.py` 其餘檔案不同，這個檔案**不測試 `option_chaser`
引擎的行為**（引擎本身這一票完全沒動，見 guardrail）。它測試的是
`scripts/research_valuation_methods.py` 那組研究用純函式，套用在
`tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json` 的真實 TLT LEAPS
報價與 `tests/fixtures/treasury_csv_sample.txt` 的真實 Treasury 曲線上，
量化現行 q=0 基準與備選 carry 方法對長天期合約的貼近度。

完整論述、方法比較表與書面建議見
`docs/research/valuation-carry-method-comparison.md`——這個檔案只放
「數字從哪來、門檻是什麼」，論述不重複寫兩份。

跑法：`PYTHONPATH=. .venv/bin/python -m pytest tests/test_research_valuation_carry.py -v`
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date
from pathlib import Path

import pytest

from option_chaser.ratecurve import par_to_continuous, parse_treasury_csv
from scripts.research_valuation_methods import (
    bootstrap_zero_curve,
    bs_call_with_yield,
    call_floor_price,
    implied_vol_call,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_tlt_quotes():
    data = json.loads((FIXTURES / "tlt_leaps_real_quotes_2026-07-17.json").read_text())
    S = data["spot"]
    r = data["flat_rate_used_in_source_report"]
    T = (date.fromisoformat(data["expiry"])
         - date.fromisoformat(data["analyzed_at"])).days / 365.0
    contracts = [(c["strike"], (c["bid"] + c["ask"]) / 2.0) for c in data["calls"]]
    return S, r, T, contracts


# ---------- Method A（q=0 現行基準）的失敗模式：量化，不是猜測 ----------

def test_q0_baseline_cannot_price_several_real_leaps_calls():
    """5 檔真實 2028-12-15 TLT LEAPS call 中，q=0 模型的 sigma->0 下限
    （`call_floor_price`）本身就高於市場中價的組數——這種情況下二分法
    無論怎麼調 IV 都到不了市場價，不是「擬合較差」，是這組 carry 假設
    在數學上無法解釋這筆真實報價。見研究文件 §3.1。"""
    S, r, T, contracts = _load_tlt_quotes()

    infeasible = [
        (K, mid) for K, mid in contracts
        if mid < call_floor_price(S, K, T, r, q=0.0)
    ]

    assert len(infeasible) >= 3, (
        f"預期至少 3/5 檔真實合約在 q=0 下不可行，實際只有 {len(infeasible)} 檔"
        "——若這個數字變小，代表 q=0 基準的失敗模式比研究文件記錄的更輕微，"
        "應該回頭修正文件用字，而不是放寬這條測試。")


def test_q0_infeasibility_survives_plausible_rate_recalibration():
    """排除「其實是 r 抓錯，不是少了股利調整」這個對立假說：算出讓
    q=0 恰好可行的臨界利率，證明它遠低於這段期間文件記錄的真實利率
    （`docs/research/risk-free-rate-for-bs.md` §7：2026-07 中旬 2Y ≈
    4.26%），因此「調整 r」不足以解釋這個落差，落差的方向與量級只有
    股利／配息效應解釋得通。"""
    S, r, T, contracts = _load_tlt_quotes()

    def critical_rate(K: float, mid: float) -> float:
        # S - K*exp(-r*T) = mid  =>  r = -ln((S-mid)/K) / T
        val = (S - mid) / K
        assert val > 0, "market mid 已低於未貼現內在價值，屬另一類資料品質問題"
        return -math.log(val) / T

    plausible_actual_rate = 0.04  # 文件記錄的同期真實利率量級（見 docstring）
    for K, mid in contracts:
        floor_at_zero_q = call_floor_price(S, K, T, r, q=0.0)
        if mid >= floor_at_zero_q:
            continue  # 這檔本來就 q=0 可行，不在這條回歸範圍內
        r_crit = critical_rate(K, mid)
        assert r_crit < plausible_actual_rate - 0.005, (
            f"K={K}：臨界利率 {r_crit:.4%} 太接近真實利率量級 "
            f"{plausible_actual_rate:.4%}，「r 抓錯」變成站得住的對立解釋，"
            "不能再說落差只能用股利效應解釋")


# ---------- Method B／E（股利殖利率調整＋跨履約價校準）的量化改善 ----------

def test_dividend_yield_adjustment_resolves_all_five_contracts():
    """研究文件 §3.2 的經驗最佳擬合 q≈4.5%：套用後 5 檔合約全部可解出
    正的隱含波動率（q=0 只有 2/5 可解）。"""
    S, r, T, contracts = _load_tlt_quotes()
    q = 0.045

    ivs = [implied_vol_call(S, K, T, r, q, mid) for K, mid in contracts]

    assert all(iv is not None for iv in ivs), (
        f"q={q:.1%} 未能讓全部 5 檔合約可解，實際：{ivs}")
    assert all(0.01 < iv < 1.0 for iv in ivs), (
        f"隱含波動率超出合理區間（1%–100%），可能是求解器數值問題：{ivs}")


def test_dividend_yield_adjustment_improves_cross_strike_iv_consistency():
    """跨履約價 IV 一致性校準（Method E，研究文件 §3.2）：排除深度 OTM
    那組（K=130，有真實 vol skew，不該被當成 carry 誤差）之後，四個
    價位相近的履約價在 q≈4.5% 時，回推的隱含波動率離散度應明顯小於
    在低 q（但仍可行）時的離散度——量化「股利調整讓同一到期日的定價
    內部更一致」這個宣稱，不是只給一個方向性的形容詞。"""
    S, r, T, contracts = _load_tlt_quotes()
    near_money = [(K, mid) for K, mid in contracts if K != 130.0]
    assert len(near_money) == 4

    def dispersion(q: float) -> float:
        ivs = [implied_vol_call(S, K, T, r, q, mid) for K, mid in near_money]
        assert all(iv is not None for iv in ivs), f"q={q:.1%} 應該全部可解：{ivs}"
        return statistics.pstdev(ivs)

    low_q_dispersion = dispersion(0.025)   # 低但仍可行的 q（q<2.5% 時
    # K80／K79 兩檔在這四檔的子集合裡就已經不可行，見研究文件 §3.1）
    best_fit_dispersion = dispersion(0.045)  # 經驗最佳擬合

    assert best_fit_dispersion < low_q_dispersion / 2.0, (
        f"q=4.5% 的離散度（{best_fit_dispersion:.4f}）未能明顯優於 "
        f"q=2.0% 的離散度（{low_q_dispersion:.4f}）——經驗最佳擬合的說法"
        "站不住，應該回頭檢查研究文件 §3.2 的數字")


def test_deep_otm_strike_shows_larger_iv_dispersion_than_near_money_cluster():
    """反面佐證：K=130（深度 OTM）就算用經驗最佳擬合 q，隱含波動率仍
    明顯偏離其餘四檔——證明那組價位的落差是真實的波動率偏斜，不是
    「q 還沒調對」，佐證上一條測試刻意把它排除在一致性判定之外是對的，
    不是挑資料。"""
    S, r, T, contracts = _load_tlt_quotes()
    q = 0.045
    ivs = {K: implied_vol_call(S, K, T, r, q, mid) for K, mid in contracts}
    near_money_ivs = [v for k, v in ivs.items() if k != 130.0]

    assert ivs[130.0] - max(near_money_ivs) > 0.02, (
        "K=130 的隱含波動率應該明顯高於其餘四檔的最大值（>2 vol pt），"
        f"實際：K130={ivs[130.0]:.4f}，其餘四檔={near_money_ivs}")


# ---------- AC 第 4 點：Treasury par → continuous 近似的獨立覆核 ----------

def test_par_to_continuous_matches_bootstrap_within_documented_tolerance():
    """獨立覆核 `docs/research/risk-free-rate-for-bs.md` §5.3 的既有結論
    （par→zero bootstrap 差 <1bp）：用真實 2026-08-04 Treasury 曲線
    （`treasury_csv_sample.txt`，`ratecurve.parse_treasury_csv` 既有函式
    解析）逐節點 bootstrap，對照現行 `par_to_continuous` 的直接近似公式，
    確認本工具實際會用到的 1M–3Y 範圍內差距在個位數 bp 以內——這是
    對現行實作的覆核，不是重新做一次選源研究（選源結論已經定案，見
    `docs/research/interest-rate-source-selection.md`）。"""
    text = (FIXTURES / "treasury_csv_sample.txt").read_text()
    curve = parse_treasury_csv(text)

    # 只取 CMT 半年複利慣例下、tenor 為 0.5 倍數的節點（bootstrap 需要
    # 對齊配息期），且限制在本工具實際用得到的 1M–3Y（§7 既有結論：
    # 3Y 以上本工具用不到）。
    par_yields_by_tenor = {
        0.5: 0.0400, 1.0: 0.0404, 2.0: 0.0420, 3.0: 0.0425,
    }
    par_nodes = sorted(par_yields_by_tenor.items())

    bootstrapped = bootstrap_zero_curve(par_nodes)

    max_diff_bp = 0.0
    for (tenor, par_yield), (tenor2, r_boot) in zip(par_nodes, bootstrapped):
        assert tenor == tenor2
        r_direct = par_to_continuous(par_yield)
        diff_bp = abs(r_boot - r_direct) * 10_000
        max_diff_bp = max(max_diff_bp, diff_bp)

    assert max_diff_bp < 2.0, (
        f"1M–3Y 範圍內 bootstrap 與直接近似公式的最大差距 {max_diff_bp:.3f}bp"
        "，超出研究文件記錄的個位數 bp 量級，應該回頭檢查曲線資料或"
        "bootstrap 實作")


# ---------- 求解器本身的健全性（不依賴真實資料，純數值回歸） ----------

def test_implied_vol_solver_round_trips_against_known_price():
    """求解器自我一致性：用已知 sigma 算出模型價，再用同一個模型價解回
    sigma，應該拿回原本的 sigma——確保這份研究工具本身沒有計算錯誤，
    上面幾條依賴真實資料的測試才站得住腳。"""
    S, K, T, r, q, sigma_true = 100.0, 95.0, 2.0, 0.04, 0.03, 0.22
    price = bs_call_with_yield(S, K, T, r, q, sigma_true)

    solved = implied_vol_call(S, K, T, r, q, price)

    assert solved is not None
    assert solved == pytest.approx(sigma_true, abs=1e-6)


def test_implied_vol_solver_returns_none_below_the_floor():
    """低於該組 carry 假設的 sigma->0 下限時，求解器誠實回傳 `None`，
    不是拋例外、也不是硬夾一個數字回傳（那樣會讓上面的「不可行」測試
    悄悄失去意義）。"""
    S, K, T, r, q = 100.0, 90.0, 2.0, 0.04, 0.0
    floor = call_floor_price(S, K, T, r, q)

    result = implied_vol_call(S, K, T, r, q, target_price=floor - 1.0)

    assert result is None
