"""SCALE-09（#261，Scaling Foundation Stage 1-1）Part B：candidate-
specific historical resolver。

## AC 對照

- AC-3：本檔案逐一涵蓋——valid candidate（`test_valid_candidate_
  resolves_to_the_canonical_cost`）、valid bid/ask 但 invalid IV
  （`test_invalid_iv_is_a_genuine_gap`）、strategy disabled
  （`test_strategy_not_requested_is_a_genuine_gap`）、expiry
  unselected（`test_expiry_outside_the_canonical_selection_is_a_
  genuine_gap`）、缺腿/invalid quote（`test_missing_leg_is_a_genuine_
  gap`／`test_crossed_quote_is_a_genuine_gap`）、可構造的
  structural/B-layer invalid（`test_structural_invalid_pair_is_a_
  genuine_gap`；B 層安全網本身的邏輯正確性另由
  `test_derived_invalid_branch_is_reachable_via_a_stubbed_cost_lookup`
  證明——已用真實報價數學證明「結構通過但 cost≤0」在合法報價下不可能
  構造，見 `history_resolver.py` docstring）。
- AC-4：以上每個 invalid case 都刻意保留「其餘腿報價正常、
  `cost_from_snapshot()` 單獨呼叫可以算出一個數字」，證明 resolver
  沒有偷懶地把「算不出來」與「不該算」混為一談。
- AC-5：`test_resolver_never_imports_enumeration_or_ranking` 結構性
  鎖住不 import `filters.apply_filters`／`generate_spread_pairs`／
  `generate_butterfly_triples`／`service.py` 任何一個逐 subtype
  跑整條鏈的函式——resolve 只對指名的那幾條腿做事。
- AC-6：`test_version_mismatch_never_guesses`（history_replay_version
  不匹配時一律 gap，不嘗試用新規則重解）；
  `test_history_replay_version_matches_store_constant`（結構性測試
  鎖住 `history_resolver.HISTORY_REPLAY_VERSION` 與
  `store.HISTORY_REPLAY_VERSION` 永遠同步，不是各自一個字面量）。
- 整合驗證：`test_resolver_agrees_with_a_real_engine_run_on_a_genuinely_
  eligible_candidate`——真的跑一次分析，對它產生的 `expiry_ranked`
  抽出的真實候選，resolver 算出的成本必須與引擎 `natural_cost()`
  逐位元相同。
"""
from __future__ import annotations

from option_chaser import service, store
from option_chaser.history_resolver import (HISTORY_REPLAY_VERSION,
                                             resolve_historical_cost)
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract
from option_chaser.scenarios import natural_cost
from option_chaser.snapshot_replay import cost_from_snapshot

FETCHED_AT = "2026-08-04T09:30:00+00:00"   # today = 2026-08-04
SELECTED_EXPIRY = "2026-09-18"             # 落在 target_month=2026-09 的六點選取範圍內
UNSELECTED_EXPIRY = "2026-12-18"           # 同一份鏈上存在，但被六點規則排除
TARGET_MONTH = "2026-09"

BASE_FACT = {
    "history_replay_version": HISTORY_REPLAY_VERSION,
    "requested_strategies": ("bull-call-spread",),
    # spot=100.0（`snapshot()` 固定值）——target_price=120.0 讓
    # `derive_direction()` 判成 bullish，`bull-call-spread` 因此保持
    # eligible，既有測試案例的預期行為不受新增的 direction 檢查影響。
    "resolved_params": {"target_month": TARGET_MONTH, "target_price": 120.0},
}


def leg(strike, bid, ask, iv=0.30, expiry=SELECTED_EXPIRY, option_type="call"):
    return OptionContract(contract_symbol=f"C{strike:g}{expiry}", option_type=option_type,
                          strike=strike, expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=10, implied_volatility=iv)


def snapshot(contracts) -> ChainSnapshot:
    return ChainSnapshot(schema_version=1, symbol="XYZ", fetched_at=FETCHED_AT,
                         spot=100.0, source="test", contracts=tuple(contracts))


# 有效的 vertical spread：買 100／賣 110，A 層與結構檢查皆通過。
VALID_LONG = leg(100.0, bid=5.0, ask=5.2)
VALID_SHORT = leg(110.0, bid=1.0, ask=1.2)
VALID_KEY = f"bull-call-spread|100|110|{SELECTED_EXPIRY}"


def _resolve(candidate_key, snap, **overrides):
    fact = {**BASE_FACT, **overrides}
    return resolve_historical_cost(
        candidate_key, history_replay_version=fact["history_replay_version"],
        requested_strategies=fact["requested_strategies"],
        resolved_params=fact["resolved_params"], snapshot=snap)


# ---------- AC-3／AC-4：逐一涵蓋每個案例 ----------

def test_valid_candidate_resolves_to_the_canonical_cost():
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap)
    assert result.reason == "ok"
    assert result.cost == cost_from_snapshot(snap, VALID_KEY)
    assert result.cost is not None and result.cost > 0


def test_invalid_iv_is_a_genuine_gap():
    """AC-4：bid/ask 正常、`cost_from_snapshot()` 單獨呼叫算得出價格，
    但其中一腿 IV 落在可解區間外——仍必須是 gap。"""
    bad_iv_short = leg(110.0, bid=1.0, ask=1.2, iv=0.001)
    snap = snapshot([VALID_LONG, bad_iv_short])
    assert cost_from_snapshot(snap, VALID_KEY) is not None   # 佐證 AC-4 前提成立
    result = _resolve(VALID_KEY, snap)
    assert result == (None, "invalid_iv") or result.reason == "invalid_iv"
    assert result.cost is None


def test_strategy_not_requested_is_a_genuine_gap():
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap, requested_strategies=("long-call",))
    assert result.reason == "strategy_disabled"
    assert result.cost is None


def test_direction_ineligible_subtype_is_a_genuine_gap():
    """AC-3／AC-4（/code-review 抓到的真缺口，見 history_resolver.py
    的說明註解）：`bull-call-spread` 只在 bullish 方向才 eligible
    （`SUBTYPE_DIRECTIONS`）。這裡把 `target_price` 設成低於 spot
    （bearish），即使 `requested_strategies` 仍列著這個 subtype、且
    兩腿報價本身完全健全、`cost_from_snapshot()` 單獨呼叫算得出一個
    數字——那天分析當下這個 subtype 因方向不合根本沒有產生任何候選
    （`status="skipped_direction"`，`view["results"]` 那筆的
    `candidates` 是空的），resolver 必須誠實回 gap，不能因為報價本身
    合法就冒充「這個 candidate 當時是 all_candidates 的成員」。"""
    snap = snapshot([VALID_LONG, VALID_SHORT])
    assert cost_from_snapshot(snap, VALID_KEY) is not None   # 佐證 AC-4 前提成立
    result = _resolve(VALID_KEY, snap,
                      resolved_params={"target_month": TARGET_MONTH,
                                       "target_price": 80.0})  # < spot=100 → bearish
    assert result.reason == "skipped_direction"
    assert result.cost is None


def test_flat_target_keeps_only_butterfly_eligible():
    """方向三態的 `flat` 分支：`target_price == spot` 時
    `bull-call-spread` 不 eligible（僅 Butterfly 收 flat），驗證不是
    只測了 bullish/bearish 兩態就當作涵蓋整個 `derive_direction()`。"""
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap,
                      resolved_params={"target_month": TARGET_MONTH,
                                       "target_price": snap.spot})
    assert result.reason == "skipped_direction"
    assert result.cost is None


def test_missing_target_price_is_a_genuine_gap():
    """`resolved_params` 裡完全沒有 `target_price` 這個 key（比照既有
    `target_month` 讀不懂就視同缺 context 的既有處理方式）——資料
    不完整時誠實回 gap，不猜一個方向。"""
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap,
                      resolved_params={"target_month": TARGET_MONTH})
    assert result.reason == "missing_fact_context"
    assert result.cost is None


def test_expiry_outside_the_canonical_selection_is_a_genuine_gap():
    """AC-4：同一份鏈上這個到期日的報價完全正常、算得出價格，只是這個
    到期日當時不屬於六點規則選中的範圍。

    六點規則「前 2 後 2、至多五檔」在候選到期日太少時會用鄰側補滿，
    這裡刻意鋪滿 8 個到期日（與 `docs` 施工紀錄實測過的同一組日期），
    讓 `UNSELECTED_EXPIRY` 真的落在選取窗之外，而不是恰好因為鏈上
    到期日不夠多而被順手選進去。"""
    padding_expiries = ("2026-08-21", "2026-08-28", "2026-09-04",
                        "2026-09-11", "2026-09-25", "2026-10-02")
    padding = [leg(100.0, bid=5.0, ask=5.2, expiry=e) for e in padding_expiries]
    long_far = leg(100.0, bid=5.0, ask=5.2, expiry=UNSELECTED_EXPIRY)
    short_far = leg(110.0, bid=1.0, ask=1.2, expiry=UNSELECTED_EXPIRY)
    far_key = f"bull-call-spread|100|110|{UNSELECTED_EXPIRY}"
    snap = snapshot([VALID_LONG, VALID_SHORT, long_far, short_far, *padding])
    assert cost_from_snapshot(snap, far_key) is not None   # 佐證 AC-4 前提成立
    result = _resolve(far_key, snap)
    assert result.reason == "expiry_unselected"
    assert result.cost is None


def test_missing_leg_is_a_genuine_gap():
    snap = snapshot([VALID_LONG])   # 賣腿整個不存在於快照
    result = _resolve(VALID_KEY, snap)
    assert result.reason == "missing_leg"
    assert result.cost is None


def test_crossed_quote_is_a_genuine_gap():
    """AC-4：賣腿 bid>ask（倒掛）——`cost_from_snapshot()` 本身不做
    A 層判斷，單獨呼叫仍會算出一個（沒有意義的）數字。"""
    crossed_short = leg(110.0, bid=5.0, ask=1.0)
    snap = snapshot([VALID_LONG, crossed_short])
    assert cost_from_snapshot(snap, VALID_KEY) is not None   # 佐證 AC-4 前提成立
    result = _resolve(VALID_KEY, snap)
    assert result.reason == "invalid_quote"
    assert result.cost is None


def test_structural_invalid_pair_is_a_genuine_gap():
    """AC-4：兩腿各自的報價完全健全（quote_ok／iv_ok 皆通過），
    `cost_from_snapshot()` 算得出一個數字，但用中價算的配對結構
    （`net_mid`）不成立——這組履約價湊不出一個有意義的 vertical
    spread，是配對層級、不是單腿層級的問題。"""
    long_c = leg(100.0, bid=1.0, ask=1.1)     # mid = 1.05
    short_c = leg(110.0, bid=1.10, ask=1.20)  # mid = 1.15 > 1.05 → net_mid < 0
    snap = snapshot([long_c, short_c])
    assert cost_from_snapshot(snap, VALID_KEY) is not None   # 佐證 AC-4 前提成立
    result = _resolve(VALID_KEY, snap)
    assert result.reason == "structural_invalid"
    assert result.cost is None


def test_derived_invalid_branch_is_reachable_via_a_stubbed_cost_lookup(monkeypatch):
    """B 層安全網（`cost is None or cost <= 0` → `derived_invalid`）。

    **可證明的數學事實**（見 `history_resolver.py` docstring）：對
    vertical／butterfly 兩個家族，只要兩腿報價本身合法（`bid<=ask`，
    即 A 層 `quote_ok` 已通過），`cost_from_snapshot()` 算出非正值
    這件事**必然蘊含**結構檢查（`spread_structural_ok`／
    `butterfly_structural_ok`，皆只看中價）也會判定 invalid——因為
    `mid <= ask` 且 `bid <= mid` 對任一條腿恆成立，逐步代入可推出
    「結構通過」與「cost<=0」在合法報價下互斥。因此**用真實報價無法
    構造出「結構通過但 cost<=0」的案例**（已嘗試多組數值，見 git
    history 的施工記錄）——這正是 T05／#226 當年「premium > width
    這類案例結構上不可能觸發」同一個既有事實的延伸。

    這裡改用 `monkeypatch` 直接讓 `cost_from_snapshot()` 回傳一個
    非正值，證明 resolver 這一段安全網程式碼本身邏輯正確、不是死碼
    （若真的發生——例如 SCALE-03 的算式未來被改動而不再與結構檢查
    同步——這裡仍然擋得住），而不是假裝能用合法資料構造出一個其實
    數學上不存在的情境。"""
    import option_chaser.history_resolver as hr

    monkeypatch.setattr(hr, "cost_from_snapshot", lambda snap, key: -1.0)
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap)
    assert result.reason == "derived_invalid"
    assert result.cost is None


def test_unrecognized_key_is_a_genuine_gap():
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve("not-a-real-strategy|100|110|" + SELECTED_EXPIRY, snap)
    assert result.reason == "unrecognized_key"
    assert result.cost is None


# ---------- AC-6：version dispatch，唯一 canonical 判準 ----------

def test_version_mismatch_never_guesses():
    snap = snapshot([VALID_LONG, VALID_SHORT])
    result = _resolve(VALID_KEY, snap, history_replay_version=HISTORY_REPLAY_VERSION + 1)
    assert result.reason == "version_mismatch"
    assert result.cost is None


def test_missing_fact_context_fields_are_a_genuine_gap():
    """SCALE-01 FR-1.4：backfill 完成前，既有列的這幾個欄位是
    `NULL`——resolver 必須誠實回 gap，不得臆測。"""
    snap = snapshot([VALID_LONG, VALID_SHORT])
    for override in ({"history_replay_version": None},
                     {"requested_strategies": None},
                     {"resolved_params": None}):
        result = _resolve(VALID_KEY, snap, **override)
        assert result.reason == "missing_fact_context"
        assert result.cost is None


def test_history_replay_version_matches_store_constant():
    """AC-6：`history_resolver` 自己的版本常數與 `store.
    HISTORY_REPLAY_VERSION`（SCALE-01 落盤時寫入的那個數字）必須
    永遠同步——engine 層不 import `store`（避免不必要的模組耦合），
    這條結構性測試是兩者不會悄悄分岔的唯一保證。"""
    assert HISTORY_REPLAY_VERSION == store.HISTORY_REPLAY_VERSION


# ---------- AC-5：結構性隔離——不重新枚舉候選全池 ----------

def test_resolver_never_imports_enumeration_or_ranking():
    import ast
    import inspect

    from option_chaser import history_resolver

    src = inspect.getsource(history_resolver)
    tree = ast.parse(src)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)

    forbidden = {"apply_filters", "generate_spread_pairs",
                "generate_butterfly_triples", "rank", "rank_spreads",
                "rank_butterflies", "evaluate_contract", "evaluate_spread",
                "evaluate_butterfly", "service"}
    assert not (imported_names & forbidden), (
        f"resolver 匯入了會枚舉整條鏈／重跑排名的符號：{imported_names & forbidden}")


# ---------- 整合驗證：與真實引擎在一個真實 eligible 候選上一致 ----------

def test_resolver_agrees_with_a_real_engine_run_on_a_genuinely_eligible_candidate():
    # 真實 call 鏈：履約價越高、call 越便宜（現貨 100）——`leg()` 若用
    # `bid=strike*0.05` 這種隨履約價遞增的公式，等於做出一條假的、
    # 越價外越貴的鏈，任何 vertical pair 都會在結構檢查（`net_mid`）
    # 直接判 invalid，這裡改用遞減、貼近真實現貨附近報價的數值。
    prices = {95.0: (20.0, 20.2), 100.0: (15.0, 15.2), 105.0: (10.0, 10.2),
             110.0: (5.0, 5.2), 115.0: (1.0, 1.2)}
    contracts = [leg(strike, bid=b, ask=a) for strike, (b, a) in prices.items()]
    snap = snapshot(contracts)
    p = AnalysisParams(target_price=115.0, target_month=TARGET_MONTH,
                       strategy="bull-call-spread")
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("bull-call-spread",))
    result = service.run_with_snapshot(req, snap)
    r = result.results[0]
    assert r.status == "ok", r.message
    _, ranked_group = r.expiry_ranked[0]
    sv = ranked_group[0]
    real_key = service.valuation_key(sv)
    real_cost = natural_cost(sv)

    resolved = resolve_historical_cost(
        real_key, history_replay_version=HISTORY_REPLAY_VERSION,
        requested_strategies=("bull-call-spread",),
        resolved_params={"target_month": TARGET_MONTH, "target_price": 115.0},
        snapshot=snap)

    assert resolved.reason == "ok"
    assert resolved.cost == real_cost
