"""SCALE-03（#254，Scaling Foundation S1-0b）：從 raw snapshot 逐位元
重算 `natural_cost()` 的快照回填原語——Prototype #065 已證明可行
（4,626 筆歷史快照比對，0 mismatch），本模組是它移植進 production 的
版本。

**明確的責任邊界（票面「明確不做」）**：`cost_from_snapshot()` 只回答
「這個 candidate_key 在這份快照上算得出多少成本」，**不判定歷史
membership／eligibility**——candidate 當時是否真的通過完整過濾
（IV 有效性、strategy 是否啟用、expiry 是否被選中、pair/B 層合法性）
是更高層 resolver（SCALE-09）的職責。尤其：`bid == ask` 在現行 A 層
是合法報價（既有 filter 是 `ask >= bid`），本函式**不得**額外把它當
成倒掛拒絕——那會偷換「quote 可算」與「historically eligible」的
界線。

零 vendor 呼叫、零 credential、不跑 ranking／valuation 引擎——純粹是
`option_chaser.data.snapshot.find_contract()` 查表 ＋
`option_chaser.scenarios` 的三個 canonical 算式。
"""
from __future__ import annotations

import math

from .data.snapshot import find_contract
from .models import ChainSnapshot
from .scenarios import _butterfly_cost, _single_leg_cost, _vertical_cost

_SINGLE_LEG_STRATEGIES = {"long-call": "call", "long-put": "put"}
_VERTICAL_STRATEGIES = {"bull-call-spread": "call", "bear-put-spread": "put"}
_BUTTERFLY_STRATEGIES = {"call-fly": "call", "put-fly": "put"}


def _finite(x: float | None) -> bool:
    """`None`（缺失）或非有限值（NaN／±Infinity）都不是可用的報價。"""
    return x is not None and math.isfinite(x)


def parse_candidate_key(
    candidate_key: str,
) -> tuple[str, str, tuple[float, ...], str] | None:
    """把 `candidate_key`（`service.valuation_key()` 的輸出格式）拆成
    `(strategy, option_type, strikes, expiry)`——`strikes` 依身份鍵
    既有順序（單腿一個；vertical＝買腿在前賣腿在後；butterfly＝低中高）。
    格式不合法或 strategy 未知一律回傳 `None`，不拋例外。

    SCALE-09（#261）：抽成獨立公開函式——candidate-specific historical
    resolver 需要在呼叫 `cost_from_snapshot()`（本模組）之前，先自己
    找出各腿合約做 A 層／結構合法性檢查，若各自維護一份 `candidate_key`
    拆解規則，未來格式改動只改到其中一處就會悄悄失準（AC-6 的精神：
    唯一 canonical 判準）。`cost_from_snapshot()` 本身改為呼叫這個
    函式，不再各自重複一份拆解邏輯。"""
    parts = candidate_key.split("|")
    strategy = parts[0]

    if strategy in _SINGLE_LEG_STRATEGIES:
        if len(parts) != 3:
            return None
        return (strategy, _SINGLE_LEG_STRATEGIES[strategy],
                (float(parts[1]),), parts[2])

    if strategy in _VERTICAL_STRATEGIES:
        if len(parts) != 4:
            return None
        return (strategy, _VERTICAL_STRATEGIES[strategy],
                (float(parts[1]), float(parts[2])), parts[3])

    if strategy in _BUTTERFLY_STRATEGIES:
        if len(parts) != 5:
            return None
        return (strategy, _BUTTERFLY_STRATEGIES[strategy],
                (float(parts[1]), float(parts[2]), float(parts[3])), parts[4])

    return None


def cost_from_snapshot(snapshot: ChainSnapshot, candidate_key: str) -> float | None:
    """依 `candidate_key`（`service.valuation_key()` 的輸出格式）解析
    出這個 candidate 的策略與各腿履約價／到期日，從 `snapshot` 逐一
    查出對應合約，算出與 `option_chaser.scenarios.natural_cost()`
    逐位元相同的成本。

    任一腿在快照裡不存在、或計算所需的那個報價（見下方三種形狀各自
    用到哪一邊）缺失／非有限值，一律誠實回傳 `None`，不猜、不外插、
    不拋例外。無法辨識的 `candidate_key` 前綴（未知 strategy）同樣回
    `None`——這是防禦性寫法，不是預期會發生的情況（`candidate_key`
    的合法前綴集合由 `service._strategy_of()` 窮舉，三個 dict 的鍵
    集合與它逐字一致）。
    """
    parsed = parse_candidate_key(candidate_key)
    if parsed is None:
        return None
    strategy, option_type, strikes, expiry = parsed

    if strategy in _SINGLE_LEG_STRATEGIES:
        (strike,) = strikes
        contract = find_contract(snapshot, option_type, strike, expiry)
        if contract is None or not _finite(contract.ask):
            return None
        return _single_leg_cost(contract.ask)

    if strategy in _VERTICAL_STRATEGIES:
        long_strike, short_strike = strikes
        long_c = find_contract(snapshot, option_type, long_strike, expiry)
        short_c = find_contract(snapshot, option_type, short_strike, expiry)
        if long_c is None or short_c is None:
            return None
        if not (_finite(long_c.ask) and _finite(short_c.bid)):
            return None
        return _vertical_cost(long_c.ask, short_c.bid)

    if strategy in _BUTTERFLY_STRATEGIES:
        low_strike, mid_strike, high_strike = strikes
        low_c = find_contract(snapshot, option_type, low_strike, expiry)
        mid_c = find_contract(snapshot, option_type, mid_strike, expiry)
        high_c = find_contract(snapshot, option_type, high_strike, expiry)
        if low_c is None or mid_c is None or high_c is None:
            return None
        if not (_finite(low_c.ask) and _finite(mid_c.bid) and _finite(high_c.ask)):
            return None
        return _butterfly_cost(low_c.ask, mid_c.bid, high_c.ask)

    return None
