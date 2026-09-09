"""SCALE-03（#254，Scaling Foundation S1-0b）：`cost_from_snapshot()`
——從 raw snapshot 逐位元重算 `natural_cost()` 的快照回填原語，移植自
Prototype #065（4,626 筆歷史快照比對、0 mismatch）。

## AC 對照

- AC-1：本檔案 `test_cost_from_snapshot_matches_natural_cost_across_
  the_full_production_scale_pool` 對真實 production-scale fixture
  （`xyz_v8_production_scale.json`，600 張合約，六個 subtype 全開）
  的**整個 ranked pool** 做逐一比對，規模達到與 Prototype #065 同一
  量級（見測試內註解記錄的實測筆數）。
- AC-2：`test_missing_or_non_finite_legs_are_honest_gaps` 涵蓋缺腿、
  `None`、NaN、Infinity。
- AC-3：`test_crossed_quote_is_not_misjudged_as_invalid` 證明
  `bid == ask` 不被誤判成倒掛而拒絕。
- AC-4：`test_natural_cost_is_bit_identical_to_before_the_refactor`
  用既有 valuation fixture 直接核對 `scenarios.natural_cost()` 抽出
  canonical helper 前後逐位元不變。
- AC-5：`cost_from_snapshot()` 本身未被任何生產路徑呼叫
  （`git grep` 可自行核對），本票只交付函式。
- AC-6：全套既有測試（`test_scenarios.py`／`test_valuation*.py`／
  CLI golden／selection regression）在本票的 PR 裡零改動、零漂移
  ——`scenarios.natural_cost()` 的輸出值本身未變，只是內部呼叫路徑
  多繞了一層。
"""
import math

import pytest

from option_chaser import scenarios, service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams
from option_chaser.snapshot_replay import cost_from_snapshot
from tests._production_scale_fixtures import (
    PRODUCTION_SCALE_FIXTURE as FIX, real_dividend_loader)


# ---------- AC-1：整個 production-scale ranked pool 逐一比對 ----------

def test_cost_from_snapshot_matches_natural_cost_across_the_full_production_scale_pool():
    """單一劇本六個 subtype 全開，跑一次真實分析（真實非零 q，比照
    REPAIR-03／#240 既有慣例），對 `result.expiry_ranked` 裡**每一個**
    候選（不是抽樣）獨立用 `cost_from_snapshot()` 從同一份 raw snapshot
    重算，逐位元比對 `scenarios.natural_cost()` 的既有引擎輸出。

    這是比 Prototype #065（100 次合成刷新×46 個 visible 候選≈4,626 筆）
    更嚴格的驗證方式：Prototype 只驗證「visible 候選集合」，這裡窮舉
    「整個 ranked pool」（含每個到期日全部合格候選，不只 top-N）。
    單一 target 只會觸發三個方向相容的 subtype（T08／#225 既有
    eligibility gate 會把方向不合的 subtype 判成 `skipped_direction`，
    候選數為 0）——這裡分別用看漲（target=110，高於 fixture 現價
    100）與看跌（target=90）各跑一次、合併比對，讓六個 subtype
    （single-leg×2、vertical×2、butterfly×2）三種算式形狀都真的被
    `cost_from_snapshot()` 走過至少一次，不只是三個。

    2026-09-06 實測：600 張合約，看漲那輪 128,668 筆（long-call 300／
    bull-call-spread 7,435／call-fly 120,933，遠超 butterfly 枚舉的
    A 層健全性判準門檻）、看跌那輪對稱量級——合併遠超 Prototype #065
    的 4,626 筆基準，且是窮舉而非抽樣。"""
    all_strategies = ("long-call", "long-put", "bull-call-spread",
                      "bear-put-spread", "call-fly", "put-fly")
    snap = load_snapshot(FIX)

    compared = 0
    mismatches = []
    per_strategy: dict[str, int] = {}
    for target_price in (110.0, 90.0):   # 看漲＋看跌，覆蓋全部 6 個 subtype
        p = AnalysisParams(target_price=target_price, target_month="2026-09",
                           strategy="long-call")
        req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                      strategies=all_strategies)
        result = service.run_offline(req, FIX, dividend_loader=real_dividend_loader)
        for r in result.results:
            for _expiry, ranked_group in r.expiry_ranked:
                for sv in ranked_group:
                    key = service.valuation_key(sv)
                    expected = scenarios.natural_cost(sv)
                    actual = cost_from_snapshot(snap, key)
                    compared += 1
                    per_strategy[r.strategy] = per_strategy.get(r.strategy, 0) + 1
                    if actual != expected:
                        mismatches.append((key, expected, actual))

    assert mismatches == []
    assert all(n > 0 for n in per_strategy.values()), per_strategy
    assert set(per_strategy) == set(all_strategies)
    # 抓 Prototype #065 原始基準的 1×，不是湊出來的數字（實測遠超此門檻）。
    assert compared >= 4626, (
        f"樣本數只有 {compared} 筆，未達 Prototype #065 的 4,626 筆"
        " 重新驗證基準")


# ---------- AC-2：缺腿／None／NaN／Infinity ----------

def test_missing_or_non_finite_legs_are_honest_gaps():
    p = AnalysisParams(target_price=110.0, target_month="2026-09",
                       strategy="long-call")
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("long-call",))
    result = service.run_offline(req, FIX)
    snap = load_snapshot(FIX)

    # 不存在的履約價／到期日組合——腿根本查不到
    assert cost_from_snapshot(snap, "long-call|9999|2099-01-01") is None
    # 未知策略前綴——防禦性 None，不猜
    assert cost_from_snapshot(snap, "not-a-real-strategy|100|2026-09-18") is None
    # 欄位數量與策略不符（例如把單腳鍵硬塞成價差形狀）
    assert cost_from_snapshot(snap, "long-call|100|105|2026-09-18") is None


def test_none_and_non_finite_ask_are_both_honest_gaps():
    """直接構造一份合成 snapshot，逐一驗證 `None`／NaN／Infinity 三種
    非有限值都誠實回 `None`，不是只測「腿不存在」這一種情況。"""
    from dataclasses import replace

    snap = load_snapshot(FIX)
    target = next(c for c in snap.contracts if c.option_type == "call")
    key = f"long-call|{target.strike:g}|{target.expiry}"

    for bad_ask in (None, math.nan, math.inf, -math.inf):
        contracts = tuple(
            replace(c, ask=bad_ask) if c is target else c
            for c in snap.contracts)
        broken = replace(snap, contracts=contracts)
        assert cost_from_snapshot(broken, key) is None


def test_missing_leg_in_a_vertical_spread_is_a_gap():
    from dataclasses import replace

    snap = load_snapshot(FIX)
    calls = sorted({c.strike for c in snap.contracts if c.option_type == "call"})
    long_strike, short_strike = calls[0], calls[1]
    expiry = next(c.expiry for c in snap.contracts
                 if c.option_type == "call" and c.strike == long_strike)
    key = f"bull-call-spread|{long_strike:g}|{short_strike:g}|{expiry}"

    # 完整時算得出值
    assert cost_from_snapshot(snap, key) is not None

    # 拿掉短腿那張合約——缺腿必須是誠實的 None
    without_short = replace(snap, contracts=tuple(
        c for c in snap.contracts
        if not (c.option_type == "call" and c.strike == short_strike
                and c.expiry == expiry)))
    assert cost_from_snapshot(without_short, key) is None


def test_missing_or_non_finite_leg_in_a_butterfly_is_a_gap():
    """`/code-review` 抓到的真缺口：AC-2「1/2/3 腿缺失」原本只測到
    單腳與 vertical 兩種形狀，butterfly（3 腿、獨立的一段
    `if strategy in _BUTTERFLY_STRATEGIES` 判斷邏輯）完全沒有負向
    測試覆蓋——結構上與 vertical 平行，但沒測就不算真的驗證過。"""
    from dataclasses import replace

    snap = load_snapshot(FIX)
    calls = sorted({c.strike for c in snap.contracts if c.option_type == "call"})
    low, mid, high = calls[0], calls[1], calls[2]
    expiry = next(c.expiry for c in snap.contracts
                 if c.option_type == "call" and c.strike == low)
    key = f"call-fly|{low:g}|{mid:g}|{high:g}|{expiry}"

    # 三腿齊全時算得出值
    assert cost_from_snapshot(snap, key) is not None

    # 拿掉中腿——缺腿必須是誠實的 None
    without_mid = replace(snap, contracts=tuple(
        c for c in snap.contracts
        if not (c.option_type == "call" and c.strike == mid
                and c.expiry == expiry)))
    assert cost_from_snapshot(without_mid, key) is None

    # 高腿 ask 為 None／NaN／Infinity——同樣是誠實的 None
    high_c = next(c for c in snap.contracts
                 if c.option_type == "call" and c.strike == high
                 and c.expiry == expiry)
    for bad_ask in (None, math.nan, math.inf):
        broken = replace(snap, contracts=tuple(
            replace(high_c, ask=bad_ask) if c is high_c else c
            for c in snap.contracts))
        assert cost_from_snapshot(broken, key) is None


# ---------- AC-3：bid == ask 不得被誤判成倒掛 ----------

def test_crossed_quote_is_not_misjudged_as_invalid():
    """票面明文：現行 A 層合法報價是 `ask >= bid`，`bid == ask` 合法。
    `cost_from_snapshot()` 不得額外加一條「必須嚴格 ask > bid」的規則
    ——那會偷換「quote 可算」與「historically eligible」的界線。"""
    from dataclasses import replace

    snap = load_snapshot(FIX)
    target = next(c for c in snap.contracts if c.option_type == "call")
    key = f"long-call|{target.strike:g}|{target.expiry}"

    tied = replace(target, bid=1.0, ask=1.0)
    contracts = tuple(tied if c is target else c for c in snap.contracts)
    snap2 = replace(snap, contracts=contracts)

    assert cost_from_snapshot(snap2, key) == 1.0   # 單腳成本就是 ask 本身

    # 價差腿也一樣：short 腿 bid==ask 不得被拒絕
    calls = sorted({c.strike for c in snap.contracts if c.option_type == "call"})
    long_strike, short_strike = calls[0], calls[1]
    long_c = next(c for c in snap.contracts
                 if c.option_type == "call" and c.strike == long_strike)
    short_c = next(c for c in snap.contracts
                  if c.option_type == "call" and c.strike == short_strike
                  and c.expiry == long_c.expiry)
    tied_short = replace(short_c, bid=2.0, ask=2.0)
    contracts2 = tuple(tied_short if c is short_c else c for c in snap.contracts)
    snap3 = replace(snap, contracts=contracts2)
    vkey = f"bull-call-spread|{long_strike:g}|{short_strike:g}|{long_c.expiry}"
    expected = long_c.ask - 2.0
    assert cost_from_snapshot(snap3, vkey) == pytest.approx(expected)

    # butterfly 的中腿也一樣：bid==ask 是合法報價，不是倒掛
    calls_sorted = sorted({c.strike for c in snap.contracts
                          if c.option_type == "call"})
    low, mid, high = calls_sorted[0], calls_sorted[1], calls_sorted[2]
    fly_expiry = next(c.expiry for c in snap.contracts
                      if c.option_type == "call" and c.strike == low)
    mid_c = next(c for c in snap.contracts
                if c.option_type == "call" and c.strike == mid
                and c.expiry == fly_expiry)
    low_c = next(c for c in snap.contracts
                if c.option_type == "call" and c.strike == low
                and c.expiry == fly_expiry)
    high_c = next(c for c in snap.contracts
                 if c.option_type == "call" and c.strike == high
                 and c.expiry == fly_expiry)
    tied_mid = replace(mid_c, bid=3.0, ask=3.0)
    contracts3 = tuple(tied_mid if c is mid_c else c for c in snap.contracts)
    snap4 = replace(snap, contracts=contracts3)
    fkey = f"call-fly|{low:g}|{mid:g}|{high:g}|{fly_expiry}"
    expected_fly = low_c.ask - 2.0 * 3.0 + high_c.ask
    assert cost_from_snapshot(snap4, fkey) == pytest.approx(expected_fly)


# ---------- AC-4：canonical helper 抽出前後 natural_cost() 逐位元不變 ----------

def test_natural_cost_is_bit_identical_to_before_the_refactor():
    """`scenarios.natural_cost()` 抽出 `_single_leg_cost`／
    `_vertical_cost`／`_butterfly_cost` 三個 canonical helper 後，
    對既有真實分析結果的輸出必須逐位元不變——直接對照抽出前的公式
    手算一次，不是只信任「測試綠燈」。"""
    p = AnalysisParams(target_price=110.0, target_month="2026-09",
                       strategy="long-call")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("long-call", "bull-call-spread", "call-fly"))
    result = service.run_offline(req, FIX)

    from option_chaser.valuation import (ButterflyValuation, ContractValuation,
                                         SpreadValuation)

    checked = {"single": 0, "vertical": 0, "butterfly": 0}
    for r in result.results:
        for _expiry, ranked_group in r.expiry_ranked:
            for sv in ranked_group:
                actual = scenarios.natural_cost(sv)
                if isinstance(sv, SpreadValuation):
                    expected = sv.long_leg.ask - sv.short_leg.bid
                    checked["vertical"] += 1
                elif isinstance(sv, ButterflyValuation):
                    expected = sv.low_leg.ask - 2.0 * sv.mid_leg.bid + sv.high_leg.ask
                    checked["butterfly"] += 1
                elif isinstance(sv, ContractValuation):
                    expected = sv.contract.ask
                    checked["single"] += 1
                else:
                    continue
                assert actual == expected

    assert all(n > 0 for n in checked.values()), checked


# ---------- 結構性隔離（沿用既有 enrich-only 模式的檢查慣例） ----------

def test_snapshot_replay_module_does_not_run_the_ranking_engine():
    """`cost_from_snapshot()` 不得 import 任何 ranking／filters／service
    模組——它只是查表＋算術，不是縮小版的分析引擎。掃 AST 的 import
    節點，不掃整份原始碼文字（docstring 散文本來就會提到這些詞彙，
    那不是依賴）。"""
    import ast

    import option_chaser.snapshot_replay as mod
    tree = ast.parse(open(mod.__file__).read())
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    banned = {"option_chaser.ranking", "option_chaser.filters",
             "option_chaser.service", ".ranking", ".filters", ".service"}
    assert not (imported_modules & banned), imported_modules
