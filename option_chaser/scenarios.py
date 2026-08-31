"""v4 spec §2: seven-scenario resilience engine. Pure, deterministic.

Every valuation goes through the existing primitives scenario_leg_value /
spread_scenario_value. T02（#219）：後者的 `[0, width]` clamp 已廢除，
現在是純逐腿加總（`valuation.payoff_value`）——American clamp（`clamped_
price`／`american_price` 的內在價值下限）仍在單腿層級生效，不受影響。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .models import AnalysisParams
from .valuation import (ButterflyValuation, ContractValuation, SpreadValuation,
                        butterfly_scenario_value, scenario_leg_value,
                        spread_scenario_value)

SCENARIO_NAMES = {
    "S1": "不漲", "S2": "半程", "S3": "大半程", "S4": "晚30天",
    "S5": "晚90天", "S6": "IV最保守", "S7": "Natural成交",
}


@dataclass(frozen=True)
class ScenarioVector:
    entries: tuple[tuple[str, float], ...]   # (("S1", ret) ... ("S7", ret)) fixed order
    worst_code: str                          # first minimum in S1..S7 order
    worst_return: float


def _value_fn(val):
    """Uniform (S, at, shift) -> value callable for single legs, spreads, and
    (T15／#230) butterflies.

    #113：帶上 `val.carry`／`val.long_carry`+`val.short_carry`（每腿只算
    一次，見 `valuation.LegCarry` docstring）——七情境、保本掃描等全部
    共用同一個 closure，不重新反解 IV。

    T15：Butterfly 分支重用既有、已核准的 `butterfly_scenario_value()`
    （逐腿加總，T02／#219 原語的具體呼叫），這裡只是把它包成跟另外
    兩型別同一種 `(fn, mid, natural, expiry)` 四元組——`scenario_
    vector()`／`completion_curve()` 兩者都是逐點評價，對任何結構皆
    正常運作（AC 明文）；`completion_scan()`（非單調結構下算法本身
    不適用）在它自己的函式內用 isinstance 短路，不靠這裡的分派擋。"""
    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        lc, sc = val.long_carry, val.short_carry
        return (lambda S, at, p, shift=0.0:
                spread_scenario_value(lng, sht, S, at, p, shift, lc, sc)), \
               val.net_mid, (lng.ask - sht.bid), lng.expiry
    if isinstance(val, ButterflyValuation):
        lo, mid, hi = val.low_leg, val.mid_leg, val.high_leg
        lc, mc, hc = val.low_carry, val.mid_carry, val.high_carry
        natural = lo.ask - 2.0 * mid.bid + hi.ask
        return (lambda S, at, p, shift=0.0:
                butterfly_scenario_value(lo, mid, hi, S, at, p, shift, lc, mc, hc)), \
               val.net_mid, natural, lo.expiry
    c = val.contract
    carry = val.carry
    return (lambda S, at, p, shift=0.0:
            scenario_leg_value(c, S, at, p, shift, carry)), val.mid, c.ask, c.expiry


def _effective_target(spot: float, target: float) -> float:
    """T17（#234，Initial V2 spec #217 §F／§P.5）：持平劇本
    （`target_price == spot`）時，「從 spot 走到 target」這條既有插值
    路徑的長度是零——`_grid_price()`／`scenario_vector()` 的
    S2/S3/S4/S5／`completion_curve()`／`completion_scan()`（後者今天
    只有 CLI `--force` 才可能對非 Butterfly 候選觸發，見下方
    `completion_scan()` docstring）全部依賴這條路徑取樣，字面上路徑
    長度為零會讓全部取樣點塌成同一個價格（spec 明文點名的既有地雷：
    「價格網格產生器在該情況下會把五個 k 塌成同一個價格」）。

    這裡只在真正持平時換一個非零的合成終點，讓依賴這條路徑的既有函式
    的既有插值公式原封不動繼續運作、不必逐一改寫每個呼叫端。合成終點
    取 `spot * 1.15`——15% 這個比例沿用 `matrix.price_axis()` 無最高／
    最低價位時既有預設路徑已經在用、且已通過需求方核准的係數（該處是
    `target * 1.15`，看漲情境的預設上限；這裡因為 `target == spot`
    才需要合成終點，兩者在這個分支下數值相同，只是基底名字不同），
    不是為本票另外發明一個新比例。

    **只影響這裡列出的內部取樣座標，不改變 `AnalysisParams.
    target_price` 本身**——S1（不漲＝spot 本身）、S6／S7（劇本成立時
    的真實 target_price 評價點，target==spot 時該點就是 spot，這是
    正確答案不是退化）、以及排名／估值／breakeven-vs-target 等其餘
    一切真正讀取使用者目標價的地方完全不受影響，也不會被這裡改到。

    `target != spot` 時原樣回傳 `target`——既有看漲／看跌劇本用到這條
    路徑的函式因此逐位元不變（T01 基準；AC 明文要求）。"""
    if target != spot:
        return target
    return spot * 1.15


def _delay_value(fn, spot: float, today: date, p: AnalysisParams,
                 expiry: date, delta_days: int) -> float:
    """Spec §2.2: linear path spot->target over [today, anchor+delta]."""
    arrive = p.anchor + timedelta(days=delta_days)
    d = min(arrive, expiry)
    frac = (d - today).days / (arrive - today).days
    target = _effective_target(spot, p.target_price)
    s_at_d = spot + (target - spot) * frac
    return fn(s_at_d, d, p)


def scenario_vector(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams) -> ScenarioVector:
    fn, mid, natural, expiry_iso = _value_fn(val)
    expiry = date.fromisoformat(expiry_iso)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日

    def ret(value: float, cost: float) -> float:
        return (value - cost) / cost

    # T17（#234）：S2／S3 是「走到半程／大半程」的路徑插值點，target==
    # spot 時改用 `_effective_target()` 的合成終點，不再塌成 spot 本身
    # 的重複值；S1（原地不漲）／S6／S7（真實 target_price 評價）不經過
    # 這條路徑，維持讀取真正的 `p.target_price`。
    target = _effective_target(spot, p.target_price)
    s_half = spot + 0.5 * (target - spot)
    s_most = spot + 0.75 * (target - spot)
    values = [
        ("S1", ret(fn(spot, tgt, p), mid)),
        ("S2", ret(fn(s_half, tgt, p), mid)),
        ("S3", ret(fn(s_most, tgt, p), mid)),
        ("S4", ret(_delay_value(fn, spot, today, p, expiry, 30), mid)),
        ("S5", ret(_delay_value(fn, spot, today, p, expiry, 90), mid)),
        ("S6", ret(min(fn(p.target_price, tgt, p, sh) for sh in p.iv_shifts),
                   mid)),
        ("S7", ret(fn(p.target_price, tgt, p), natural)),
    ]
    worst = min(r for _, r in values)
    code = next(c for c, r in values if r == worst)
    return ScenarioVector(entries=tuple(values), worst_code=code,
                          worst_return=worst)


def natural_cost(val: ContractValuation | SpreadValuation | ButterflyValuation) -> float:
    if isinstance(val, SpreadValuation):
        return val.long_leg.ask - val.short_leg.bid
    if isinstance(val, ButterflyValuation):
        return val.low_leg.ask - 2.0 * val.mid_leg.bid + val.high_leg.ask
    return val.contract.ask


def _grid_price(spot: float, target: float, k: float) -> float:
    """Spec §2.3: positive floor min(0.01*spot, target) keeps k=1 == target.

    T17（#234）：`target` 先過 `_effective_target()`——`target==spot`
    （持平劇本）時換成非零的合成終點，否則每個 k 都算出同一個 `spot`
    （既有地雷，見 `_effective_target()` docstring）。`target != spot`
    時原樣不變，既有呼叫端（`completion_scan()`／`completion_curve()`）
    逐位元不變。"""
    target = _effective_target(spot, target)
    return max(spot + k * (target - spot), min(0.01 * spot, target))


def completion_scan(val: ContractValuation | SpreadValuation, spot: float,
                    today: date, p: AnalysisParams
                    ) -> tuple[float | None, float | None]:
    """Suffix-condition grid scan (spec §2.3): k* = smallest k such that
    value >= Mid cost at EVERY grid point in [k, 1.0]. Walk down from 1.0.

    T15（#230）：這個「從 k=1.0 反向掃描、遇第一個失敗就停」的演算法
    假設 payoff 沿掃描路徑單調——這個假設對既有四個 debit 策略成立
    （T3／#17：Spread 排名用自身到期日的內在價值，其掃描路徑本來就是
    單調的），但 Butterfly 的 payoff 是分段線性、非單調（兩翼歸零、
    中間有峰值），對它硬套這個演算法會誤報「劇本全成仍不保本」（AC
    明文的錯誤案例）。ButterflyValuation 因此在這裡短路直接回
    `(None, None)`，不進入下面的掃描迴圈——這不是「Butterfly 沒有這個
    概念」，而是這個特定演算法對它結構性地給不出正確答案，正確答案是
    `valuation.evaluate_butterfly()` 已經用這個結構自己的分段線性性質
    算出的 `profit_region`（見 `service._v4_fields()` 如何把它接進
    `CandidateView`）。既有四策略的掃描邏輯完全不受影響——它們從不會
    走到這個分支，`isinstance` 判斷本身就是逐位元不變的保證。

    T17（#234）：Butterfly 的持平劇本走上面的 `isinstance` 短路，本來
    就不會碰到下面的網格掃描——「保本掃描對它正常」的意思就是誠實回
    `(None, None)`（既有 spec 裁示：Butterfly 的保本概念改由
    `profit_region` 承接，不是這個 suffix 掃描）。下面的網格仍然可能
    以 `target_price == spot` 被呼叫到（單腿／Spread 候選在 CLI
    `--force` 繞過方向閘門時）——`_grid_price()` 已經在函式內部處理
    這個退化情況（見其 docstring），這裡不需要另外判斷。"""
    if isinstance(val, ButterflyValuation):
        return None, None
    fn, mid, _, _ = _value_fn(val)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日
    k_star = None
    for i in range(1000, -201, -1):          # k = 1.000 down to -0.200
        k = i / 1000.0
        s = _grid_price(spot, p.target_price, k)
        if fn(s, tgt, p) < mid:
            break
        k_star = k
    if k_star is None:                        # value(S_1.0) < cost
        return None, None
    return k_star, _grid_price(spot, p.target_price, k_star)


def completion_curve(val: ContractValuation | SpreadValuation, spot: float,
                     today: date, p: AnalysisParams
                     ) -> tuple[tuple[float, float], ...]:
    fn, mid, _, _ = _value_fn(val)
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日
    out = []
    for k in (0.0, 0.25, 0.5, 0.75, 1.0):
        s = _grid_price(spot, p.target_price, k)
        out.append((k, (fn(s, tgt, p) - mid) / mid))
    return tuple(out)


@dataclass(frozen=True)
class ResilienceMetrics:
    """T09（#191）：`scenario_vector()`／`completion_curve()`／
    `completion_scan()` 三個純函式常見的組合輸出，供 `resilience_metrics()`
    的呼叫端一次拿齊，不必各自呼叫三次。"""
    scenario: ScenarioVector
    curve: tuple[tuple[float, float], ...]
    threshold: float | None
    breakeven: float | None


def resilience_metrics(val: ContractValuation | SpreadValuation, spot: float,
                       today: date, p: AnalysisParams,
                       cache: dict[int, "ResilienceMetrics"] | None = None,
                       ) -> ResilienceMetrics:
    """韌性向量／完成度曲線／保本掃描——供文字報告（`report._resilience_
    lines`）與 View（`service._v4_fields`）兩條路徑共用同一次計算
    （T09／#191）。`completion_scan()` 是三者中最貴的一個（1200 步線性
    掃描），同一個候選在一輪分析裡最多會被兩條路徑各呼叫一次；沒有這層
    快取就是白算一次。

    `cache`：呼叫端（單次 `_single_leg_result`／`_spread_result`）建立、
    貫穿整輪分析傳下去的字典，鍵是 `id(val)`——同一輪分析裡，同一個
    候選的估值物件在報告文字與 View 兩條路徑用的是同一個 Python 物件
    （`rank_spreads`／`rank` 只排序、不複製元素，`sorted()`／切片沿用
    既有 object identity），object identity 因此是安全、不需要額外身分
    鍵計算的快取鍵；不同輪分析各自建立新字典，不會跨輪誤命中。不傳
    （`None`，預設）就是每次都重算，行為與這個函式存在之前完全一樣——
    沒有快取機制的呼叫端（例如既有測試直接呼叫 `scenario_vector` 等
    個別函式）不受影響，本函式本身也可以在沒有 cache 時單獨呼叫。"""
    key = id(val)
    if cache is not None and key in cache:
        return cache[key]
    threshold, breakeven = completion_scan(val, spot, today, p)
    result = ResilienceMetrics(
        scenario=scenario_vector(val, spot, today, p),
        curve=completion_curve(val, spot, today, p),
        threshold=threshold, breakeven=breakeven)
    if cache is not None:
        cache[key] = result
    return result
