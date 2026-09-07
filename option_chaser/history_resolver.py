"""SCALE-09（#261，Scaling Foundation Stage 1-1）：candidate-specific
historical resolver——internal helper only，**不接任何 HTTP 端點**
（Stage boundary：本票不得切換 `/history` production read path，
SCALE-14 才正式接線）。

**這個模組要回答的問題，逐字對照票面**：narrow table 是熱快取、不是
真相——「這份快照上算得出這個 candidate 的成本」（SCALE-03／
`snapshot_replay.cost_from_snapshot()`）與「這個 candidate 當時真的
出現在 `expiry_ranked`／`all_candidates`（歷史 eligible）」是兩件
不同的事，前者不能拿來冒充後者。舊 `all_candidates` 的「有沒有這個
點」代表 candidate 當時真的通過完整 eligibility/validity；IV 無效、
strategy 當時未啟用、expiry 未被選、pair/B-layer invalid 時，raw
quote 可能仍存在，但正確答案是 gap（`cost=None`），不是把算得出來的
價格硬塞進去。

**刻意不 import 任何 `api_app` 的型別**（比照既有 `ivpipeline.py`
docstring 記載的同一個既有原則）——呼叫端（`api_app`）自己決定怎麼
把 `ResultFactContext` 拆成這裡吃的原生參數，engine 不依賴 storage
層的物件形狀。

**AC-5（不得退化成重跑整個 candidate universe/ranking）如何成立**：
本模組完全不呼叫 `filters.apply_filters()`／`generate_spread_pairs()`
／`generate_butterfly_triples()`（那些會枚舉整條鏈）——只對
`candidate_key` 指名的那幾條腿呼叫 `filters.quote_ok()`／`iv_ok()`／
`spread_structural_ok()`／`butterfly_structural_ok()`（皆為 O(1) 的
單一候選判準，SCALE-09 抽成公開函式供這裡重用，不重複維護一份會漂移
的複本）。也完全不呼叫 `evaluate_contract()`／`evaluate_spread()`／
`evaluate_butterfly()`（那些牽動 IV 反解／carry 校準等貴重計算）——
canonical cost 的算術本身已經由 SCALE-03 的 `cost_from_snapshot()`
單獨負責，不需要完整估值物件。

**`history_replay_version`（AC-6）**：唯一的 canonical 版本判準——
與 `store.HISTORY_REPLAY_VERSION` 比對，不匹配時**不得猜測**，直接
回傳 `version_mismatch` 這個 genuine gap。未來 filter／eligibility
改動若語意不相容於既有存量歷史資料，靠調高這個常數讓舊資料的 resolve
請求誠實停手，而不是用新規則悄悄重解舊歷史。
"""
from __future__ import annotations

from dataclasses import dataclass

from .data.snapshot import find_contract, snapshot_today
from .filters import (butterfly_structural_ok, iv_ok, quote_ok,
                      spread_structural_ok)
from .models import ChainSnapshot, derive_direction, subtype_eligible
from .snapshot_replay import cost_from_snapshot, parse_candidate_key
from .timeframe import (TargetMonth, calendar_anchor, select_expiries,
                        tradable_expiries)

# 與 `store.HISTORY_REPLAY_VERSION` 同一個數字——不 import `store`
# 本身（那會把這個模組跟一個遠比它重的、序列化用的模組綁在一起），
# 兩邊各自持有這個常數，靠 `tests/test_history_resolver.py` 的結構性
# 測試鎖住兩者必須一致（AC-6：唯一 canonical 版本判準，不是「唯一
# 定義處」——定義處可以有兩個字面量副本，只要有測試保證它們同步）。
HISTORY_REPLAY_VERSION = 1

# 三個家族各自的腿數，供 `resolve_historical_cost()` 判斷要跑哪一段
# 結構檢查——與 `parse_candidate_key()` 回傳的 `strikes` 長度一一對應，
# 不重新窮舉一次策略名稱清單。
_SINGLE_LEG_STRIKE_COUNT = 1
_VERTICAL_STRIKE_COUNT = 2
_BUTTERFLY_STRIKE_COUNT = 3


@dataclass(frozen=True)
class ResolvedHistoricalCost:
    """resolve 的結果——`cost=None` 一律代表 genuine gap，`reason`
    是給診斷／測試看的人話原因，不是給任何判斷邏輯用的（呼叫端只該
    讀 `cost`，不該對 `reason` 字串做分支決策）。"""
    cost: float | None
    reason: str


def _gap(reason: str) -> ResolvedHistoricalCost:
    return ResolvedHistoricalCost(cost=None, reason=reason)


def resolve_historical_cost(
    candidate_key: str,
    *,
    history_replay_version: int | None,
    requested_strategies: tuple[str, ...] | None,
    resolved_params: dict | None,
    snapshot: ChainSnapshot,
) -> ResolvedHistoricalCost:
    """單一 candidate 的歷史 membership／validity 判定＋（valid 時）
    canonical cost 查詢。

    四個輸入分別對應票面「輸入：candidate_key + 該 analyzed_at 的
    SCALE-01 historical fact/context + raw DB snapshot」：
    - `history_replay_version`／`requested_strategies`／
      `resolved_params` 三者即 SCALE-01 的 `ResultFactContext`
      （`api_app/storage/__init__.py`）拆開後的原生欄位，呼叫端自行
      從該物件取出、不需要在這裡認得那個型別。
    - `snapshot`：那次 `analyzed_at`的原始快照（`ChainSnapshot`）。

    任一項為 `None`（既有資料尚未 backfill，見 SCALE-01 FR-1.4：讀取
    端在 backfill 完成前必須容忍新欄位為 `NULL`）一律誠實回傳 gap，
    不臆測——這與「resolver 拒絕對它看不懂的版本亂猜」是同一種保守
    原則的兩個面向。
    """
    if (history_replay_version is None or requested_strategies is None
            or resolved_params is None):
        return _gap("missing_fact_context")
    if history_replay_version != HISTORY_REPLAY_VERSION:
        return _gap("version_mismatch")

    parsed = parse_candidate_key(candidate_key)
    if parsed is None:
        return _gap("unrecognized_key")
    strategy, option_type, strikes, expiry = parsed

    if strategy not in requested_strategies:
        return _gap("strategy_disabled")

    # `requested_strategies`（SCALE-01／`historical_fact_context()`）是
    # 這個 scenario **設定上**啟用的全部 subtype，不分那天 status 是否
    # 為 `skipped_direction`——T08（#225）的方向 eligibility 是逐次
    # analysis、依那天 target_price 相對 spot 算出的衍生事實，跟
    # `requested_strategies` 是不同層次的問題（前者「這個 subtype 這次
    # 有沒有跑」，後者「這個 subtype 這個 scenario 有沒有勾選」）。一個
    # subtype 若那天因方向不合被跳過，`view["results"]` 裡那筆的
    # `candidates` 是空的、根本沒有產生任何候選——即使這裡指名的
    # candidate_key 湊巧能從原始報價重新算出合法成本，它當時也不曾是
    # `all_candidates` 的成員，必須誠實回 gap，不能因為報價本身合法就
    # 冒充「有效」（SCALE-09／#261 code review 抓到的缺口）。
    target_price = resolved_params.get("target_price")
    if not isinstance(target_price, (int, float)):
        return _gap("missing_fact_context")
    direction = derive_direction(float(target_price), snapshot.spot)
    if not subtype_eligible(strategy, direction):
        return _gap("skipped_direction")

    target_month = resolved_params.get("target_month")
    if not isinstance(target_month, str):
        return _gap("missing_fact_context")
    try:
        anchor = calendar_anchor(TargetMonth.from_key(target_month))
    except Exception:  # noqa: BLE001 — 讀不懂的月份格式視同缺 context，不猜
        return _gap("missing_fact_context")

    today = snapshot_today(snapshot.fetched_at)
    tradable = tradable_expiries((c.expiry for c in snapshot.contracts), today)
    if not tradable or expiry not in select_expiries(tradable, anchor).expiries:
        return _gap("expiry_unselected")

    legs = [find_contract(snapshot, option_type, strike, expiry)
           for strike in strikes]
    if any(leg is None for leg in legs):
        return _gap("missing_leg")
    if not all(quote_ok(leg) for leg in legs):
        return _gap("invalid_quote")
    if not all(iv_ok(leg) for leg in legs):
        return _gap("invalid_iv")

    if len(legs) == _VERTICAL_STRIKE_COUNT:
        long_leg, short_leg = legs
        if not spread_structural_ok(long_leg, short_leg):
            return _gap("structural_invalid")
    elif len(legs) == _BUTTERFLY_STRIKE_COUNT:
        low_leg, mid_leg, high_leg = legs
        if not butterfly_structural_ok(low_leg, mid_leg, high_leg):
            return _gap("structural_invalid")
    # 單腿（_SINGLE_LEG_STRIKE_COUNT）沒有配對／結構層級的概念可檢查。

    cost = cost_from_snapshot(snapshot, candidate_key)
    # B 層安全網（`filters.validate_derived_values()` 對 `cost_fn` 的
    # 判準逐字沿用：`_finite(cost) and cost > 0`）。**誠實記錄一個
    # 已證明的數學事實**：對 vertical／butterfly，只要兩腿報價本身
    # 合法（`bid<=ask`，即上面的 A 層檢查已通過），`mid<=ask` 且
    # `bid<=mid` 對任一條腿恆成立，逐步代入可推出「結構檢查通過」與
    # 「這裡算出的 cost<=0」在合法報價下互斥——也就是說，給定上面的
    # A 層＋結構檢查都已經跑過，這個分支在真實資料上應為不可觸發
    # （`tests/test_history_resolver.py` 已用 `monkeypatch` 直接證明
    # 這段程式碼本身邏輯正確，而非用真實資料構造，因為構造不出來）。
    # 保留這道檢查是防禦性寫法：SCALE-03 的成本算式與這裡的結構檢查
    # 各自獨立維護，未來任一邊改動而不同步時，這裡仍然攔得住，不會
    # 把一個算出非正值的「候選」誤標成有效。單腿沒有結構檢查可比較，
    # 但 `cost = ask` 本身在通過 `quote_ok()`（`ask>=bid>0`）後恆正，
    # 這個分支對單腿同樣結構上不可觸發，理由同上。
    if cost is None or cost <= 0:
        return _gap("derived_invalid")

    return ResolvedHistoricalCost(cost=cost, reason="ok")
