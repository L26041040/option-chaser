"""REPAIR-08（#245，FIX-04，#052 audit）：per-subtype／per-family soft
deadline——safety net 專用，處理異常輸入（例如某個 symbol 的鏈異常
龐大、vendor 回應異常慢）下的優雅降級。**不是**效能修復的替代方案：
正常 production-scale 規模的效能已由 #240（`calibrate_leg`
memoization）解決，本票的 soft deadline 在正常情況下**必須**維持
完全不生效（見下方 `test_...normal_production_scale_never_times_out`）。

用假時鐘（`monkeypatch.setattr(service.time, "monotonic", ...)`）
決定性地控制「deadline 在第幾次檢查點被撞到」，不依賴真實 wall-clock
——真實計時在不同機器上跑起來會有落在哪個候選才超時的差異，假時鐘
讓「第 N 次檢查點超時」變成可重現的既定事實，這是本專案一貫的既有
原則（`refresh_run` 的 Continuation 測試、`PERF-05` 的併發測試皆同
一套手法：模擬時間流逝，不真的等待）。
"""
from datetime import date

from option_chaser import service
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"


def _fake_monotonic(step: float = 1.0):
    """每次呼叫時間前進 `step`，從 0 開始——`_absolute_deadline()` 的
    第一次呼叫視為「現在」，後續每次檢查點呼叫各自前進一步。"""
    state = {"t": 0.0}

    def tick():
        state["t"] += step
        return state["t"]
    return tick


def test_a_deadline_that_is_already_past_marks_every_subtype_timed_out(monkeypatch):
    """最單純的案例：deadline 在分析開始前就已經過期（`deadline_
    seconds` 給負值），`_analyze()` 逐 subtype 迴圈裡的第一個檢查點
    就會撞到——每個原本會真的計算的 subtype 都改標記
    `status="timed_out"`，不再啟動任何昂貴計算，也不會讓整個 request
    掛掉（正常回傳、不拋例外）。"""
    p = AnalysisParams(target_price=108.0, target_month="2026-10",
                       strategy="long-call")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("long-call", "long-put", "bull-call-spread",
                   "bear-put-spread", "call-fly", "put-fly"))

    result = service.run_offline(req, FIX, deadline_seconds=-1.0)

    by_strategy = {r.strategy: r for r in result.results}
    # skipped_direction 的三個 subtype 在觸及 soft deadline 檢查點**之
    # 前**就已經被方向閘門擋掉（`_analyze()` 的既有邏輯順序：方向閘門
    # 先於 soft deadline 檢查），這條既有行為不受本票影響。
    assert by_strategy["long-put"].status == "skipped_direction"
    assert by_strategy["bear-put-spread"].status == "skipped_direction"
    assert by_strategy["put-fly"].status == "skipped_direction"
    # 真正會被 soft deadline 攔下的三個：deadline 已過期，一個都不會
    # 真的跑完整估值。
    for strategy in ("long-call", "bull-call-spread", "call-fly"):
        assert by_strategy[strategy].status == "timed_out", strategy
        assert by_strategy[strategy].candidates == ()
        assert "安全上限" in by_strategy[strategy].message


def test_the_deadline_check_inside_butterfly_enumeration_aborts_mid_loop(monkeypatch):
    """AC「帶一個刻意極慢的劇本（模擬異常輸入），斷言 soft deadline／
    優雅降級真的生效」的核心案例：用假時鐘讓 deadline 撐過進入
    `_butterfly_result()` 的那一刻（`_analyze()` 逐 subtype 的前置
    檢查通過），但在窮舉候選、逐一估值的迴圈**中途**才被撞到——證明
    `_butterfly_result()` 內部真的有自己的檢查點，不是只靠
    `_analyze()` 那一層（那一層只能擋「下一個」subtype，擋不住「這個」
    subtype 自己異常龐大）。"""
    monkeypatch.setattr(service.time, "monotonic", _fake_monotonic(step=1.0))
    p = AnalysisParams(target_price=108.0, target_month="2026-10",
                       strategy="call-fly")
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("call-fly",))

    # deadline_seconds=5：第一次 time.monotonic() 呼叫（`_absolute_
    # deadline` 內）視為 t=1，deadline=6。`_analyze()` 的方向閘門與
    # 前置檢查、`apply_filters`／`generate_butterfly_triples`（皆不
    # 呼叫 time.monotonic）不消耗假時鐘，因此 `_butterfly_result()`
    # 迴圈內第 5 次檢查點呼叫（t=6）就會撞到 deadline——確認撞在
    # 迴圈中途而非第一次呼叫，需要窮舉出的候選數遠大於 5（本 fixture
    # call-fly 三個到期日合計遠超過 5 組，下方直接斷言 idx 落在
    # 合理範圍內而非等於 0 或等於總數，避免依賴精確次數這種脆弱假設）。
    result = service.run_offline(req, FIX, deadline_seconds=5.0)

    res = result.results[0]
    assert res.status == "timed_out"
    assert res.candidates == ()
    assert "已估值" in res.message
    # 解析訊息裡的「已估值 N／M 組候選」，證明真的是中途中止
    # （0 < N < M），不是一開始就直接放棄、也不是意外跑完全部才回報。
    import re
    match = re.search(r"已估值 (\d+)／(\d+) 組候選", res.message)
    assert match is not None, res.message
    n_done, n_total = int(match.group(1)), int(match.group(2))
    assert 0 < n_done < n_total, (n_done, n_total)


def test_normal_production_scale_never_times_out_with_the_default_deadline():
    """AC「正常 production-scale 規模下的既有行為與效能特性（#240／
    #244 已確立的數字）不受本票影響——新增測試證明 soft deadline 在
    正常規模下不會被觸發」。用預設的 `service.ANALYSIS_SOFT_DEADLINE`
    （45 秒，本票新增常數本身，不是另外挑一個寬鬆值）＋真實非零 q，
    在 production-scale fixture 上跑三個 family 全開，斷言沒有任何
    一個 subtype 的 status 是 `timed_out`——soft deadline 機制存在，
    但在正常負載下維持完全不生效，這是 safety net 而非效能修復替代
    方案的直接證明。"""
    from tests._production_scale_fixtures import (
        PRODUCTION_SCALE_FIXTURE, real_dividend_loader)

    p = AnalysisParams(target_price=110.0, target_month="2026-09",
                       strategy="long-call")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("long-call", "long-put", "bull-call-spread",
                   "bear-put-spread", "call-fly", "put-fly"))

    result = service.run_offline(
        req, PRODUCTION_SCALE_FIXTURE, dividend_loader=real_dividend_loader,
        deadline_seconds=service.ANALYSIS_SOFT_DEADLINE.total_seconds())

    statuses = {r.strategy: r.status for r in result.results}
    assert statuses == {
        "long-call": "ok", "bull-call-spread": "ok", "call-fly": "ok",
        "long-put": "skipped_direction", "bear-put-spread": "skipped_direction",
        "put-fly": "skipped_direction"}
    assert "timed_out" not in statuses.values()


def _code_identifiers(module) -> set[str]:
    """模組**程式碼**裡出現的識別字（函式／類別／參數／變數／屬性／
    匯入名），刻意不含註解與 docstring——那是散文，不是機制。"""
    import ast
    import inspect
    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Import):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            names.update(a.asname or a.name for a in node.names)
    return names


def test_ranking_and_filters_do_not_import_the_soft_deadline_mechanism():
    """結構性守門，比照全站既有慣例（`test_selection_regression.py`
    同一種手法）：`ranking.py`／`filters.py` 不得認識 soft deadline
    機制——它是 `service.py` 內部的流程控制，不該滲透進排名／過濾這
    兩個核心模組。

    CLOSEOUT-004（PR #250 review Finding 3）：改掃**程式碼識別字**
    （AST）而不是整份原始碼文字。原版連註解與 docstring 都掃，於是
    「解釋為什麼這裡刻意不認識 deadline」這種散文本身就會讓它紅——
    那不是它想擋的東西。同時把守門**加嚴**：除了識別字不含
    `deadline`，另外明確斷言兩個模組都沒有匯入 `time`（沒有時鐘＝
    結構上不可能自己判斷逾時），這比原本的字串掃描更貼近真正的
    不變量。Finding 3 的修法因此走依賴反轉——`generate_butterfly_
    triples()` 只收一個不帶語意的 `should_stop` 謂詞，政策留在
    `service.py`。"""
    from option_chaser import filters, ranking
    for module in (ranking, filters):
        names = _code_identifiers(module)
        assert not [n for n in names if "deadline" in n.lower()], module.__name__
        assert "time" not in names, f"{module.__name__} 匯入了時鐘"


# ---------- CLOSEOUT-004（PR #250 review Finding 3）：deadline 必須
# 涵蓋枚舉階段本身 ------------------------------------------------------

def _oversized_chain(n_strikes: int):
    """異常龐大的鏈：單一到期日 `n_strikes` 個履約價，`C(n,3)` 組合數
    在 n=300 時是 445 萬——遠超任何正常 production-scale 規模（#240 的
    效能守門 fixture 是 26 個履約價 × 5 個到期日）。刻意用合成報價而不
    是既有 fixture：既有 fixture 沒有一個大到能在枚舉階段本身耗掉時間
    預算，而這正是本 finding 要重現的情境。"""
    from option_chaser.models import ChainSnapshot, OptionContract
    contracts = []
    for i in range(n_strikes):
        strike = 50.0 + i * 0.5
        # 報價維持自洽（bid<ask、IV 在可解區間），確保 A/B 兩層過濾都
        # 放行——否則枚舉會因為候選被濾光而提早結束，測到的就不是
        # 「枚舉本身太久」這件事。
        price = max(120.0 - strike, 0.5)
        contracts.append(OptionContract(
            contract_symbol=f"XYZ20261016C{i:05d}", option_type="call",
            strike=strike, expiry="2026-10-16", bid=round(price - 0.05, 2),
            ask=round(price + 0.05, 2), last=price, volume=10,
            open_interest=100, implied_volatility=0.30))
    return ChainSnapshot(schema_version=1, symbol="XYZ", spot=110.0,
                         fetched_at="2026-07-15T00:00:00+00:00",
                         source="test", contracts=tuple(contracts))


def test_the_soft_deadline_takes_effect_during_butterfly_enumeration_itself(
        monkeypatch):
    """Review Finding 3 的核心：deadline 必須在**枚舉階段**就生效。

    修正前 `generate_butterfly_triples()` 會先把整份 `C(n,3)` 走完、
    把通過的組合全部建成一個 list，`_butterfly_result()` 的 deadline
    檢查點在那之後才第一次執行——異常龐大的鏈因此可能在任何檢查點
    生效之前就耗掉整個時間預算或撐爆記憶體，最後仍被 Vercel hard
    kill。

    非空斷言的關鍵在 `pair_report.total_pairs`：它記的是**真的走訪過**
    的組合數。deadline 已經過期的情況下，修好之後它必須遠小於完整的
    `C(n,3)`；修正前它恆等於完整組合數（枚舉一定跑完）。
    """
    from math import comb

    n_strikes = 300
    snap = _oversized_chain(n_strikes)
    full = comb(n_strikes, 3)          # 4,455,100 組
    p = AnalysisParams(target_price=130.0, target_month="2026-10",
                       strategy="call-fly")
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("call-fly",))

    # 假時鐘（沿用本檔案既有手法）讓 deadline 精準落在枚舉階段：
    # t=1 `_absolute_deadline()`→deadline=1+2=3；t=2 `_analyze()` 逐
    # subtype 的前置檢查（2>=3 為假，通過，所以真的有進到
    # `_butterfly_result()`）；t=3 枚舉的第一個徵詢點（3>=3 為真，停）。
    # 直接用 deadline_seconds=-1 是不行的——那會在 `_analyze()` 那層就
    # 先被擋下，根本走不到枚舉，測不到本 finding 要測的東西。
    monkeypatch.setattr(service.time, "monotonic", _fake_monotonic(step=1.0))
    result = service.run_with_snapshot(req, snap, deadline_seconds=2.0)

    res = result.results[0]
    assert res.status == "timed_out"
    assert res.candidates == ()
    assert "已枚舉" in res.message, res.message
    # 真的在枚舉中途停下：走訪過的組合數必須遠小於完整 C(n,3)。
    walked = res.pair_report.total_pairs
    assert 0 < walked < full / 100, (walked, full)
    # 前提斷言：這條鏈真的大到值得測（否則上面的比例是巧合）。
    assert full > 4_000_000, full


def test_enumeration_stays_bitwise_identical_when_no_deadline_is_given():
    """`should_stop=None`（預設，也是全部既有呼叫端的用法）時，枚舉
    行為與這個參數加入前逐位元相同——正常 production-scale workload
    的結果不得改變。直接對照「傳謂詞但永遠回 False」與「完全不傳」
    兩種呼叫，兩者輸出必須完全一致。"""
    from option_chaser.data.snapshot import load_snapshot
    from option_chaser.filters import apply_filters, generate_butterfly_triples

    snap = load_snapshot(FIX)
    p = AnalysisParams(target_price=108.0, target_month="2026-10",
                       strategy="call-fly")
    qualified, _ = apply_filters(snap.contracts, p)

    plain, plain_report = generate_butterfly_triples(qualified, p)
    hooked, hooked_report = generate_butterfly_triples(
        qualified, p, should_stop=lambda: False)

    assert plain == hooked
    assert plain_report == hooked_report
    assert plain, "這份 fixture 沒有候選，比較不出東西"
