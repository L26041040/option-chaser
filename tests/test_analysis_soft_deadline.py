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


def test_ranking_and_filters_do_not_import_the_soft_deadline_mechanism():
    """結構性守門，比照全站既有慣例（`test_selection_regression.py`
    同一種手法）：`ranking.py`／`filters.py` 原始碼不含 `deadline`
    字樣——soft deadline 是 `service.py` 內部的流程控制，不該滲透進
    排名／過濾這兩個核心模組。"""
    import inspect
    from option_chaser import filters, ranking
    assert "deadline" not in inspect.getsource(ranking)
    assert "deadline" not in inspect.getsource(filters)
