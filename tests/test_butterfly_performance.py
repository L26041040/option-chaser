"""T15（#230，Initial V2 spec #217）：枚舉／估值效能量測——AC「枚舉成本
在可接受範圍，並記錄實測數字」。

`tests/fixtures/xyz_v6_butterfly_ladder.json`（`scripts/gen_butterfly_
fixture.py` 產生）是刻意密集的合成快照：26 個履約價 × 5 個到期日，
單一到期日 `C(26,3)=2600` 組合、五個到期日合計 13,000 組——量級對齊
wayfinder 地圖 #216 對真實 Cboe 全鏈的估計（11,966 組 ~230ms，該數字
量的是純枚舉，見下方分項量測）。

本測試分兩段量測、各自記錄：純枚舉（`generate_butterfly_triples`）與
含完整估值（`evaluate_butterfly` 逐組計算 carry／Greeks／七情境）——
後者比前者貴了兩個數量級，這是誠實的分項記錄，不是把兩件不同的事
混報成同一個數字。斷言只設寬鬆的回歸上界（真的變慢一個數量級才會
紅），不是精確比對某個時間點量到的數字（機器效能本身就會浮動）。

⚠ **這份測試不是 production-scale 效能基準**——`dividend_loader`
從未接上（q 停用，`calibrate_leg()` 的 IV 反解分支完全不會被觸發），
fixture 規模也只有 production 尺度的 1/17（26 履約價 vs 60）。真正
量測「production-scale＋真實非零 q」的是
`tests/test_repair03_performance.py`（引擎層 `run_offline()`）與
`tests/test_api_performance_guard.py`（HTTP 層完整刷新路徑）——
REPAIR-03／REPAIR-10（#240／#247，#052 audit）刻意保留本檔案不動，
理由與判斷詳見那兩個檔案自己的檔頭說明。
"""
import time
from datetime import date

from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.filters import apply_filters, generate_butterfly_triples
from option_chaser.models import AnalysisParams
from option_chaser.valuation import evaluate_butterfly

FIX = "tests/fixtures/xyz_v6_butterfly_ladder.json"


def test_pure_enumeration_is_fast_even_at_thirteen_thousand_combinations():
    snap = load_snapshot(FIX)
    p = AnalysisParams(strategy="call-fly", target_price=108.0, target_month="2026-10")
    qualified, _ = apply_filters(snap.contracts, p)
    t0 = time.perf_counter()
    triples, pair_report = generate_butterfly_triples(qualified, p)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"\n[枚舉量測] {pair_report.total_pairs} 組合，{elapsed_ms:.1f} ms "
         f"（{len(qualified)} 張合格合約，5 個到期日）")
    assert pair_report.total_pairs > 10000
    # 寬鬆上界：純枚舉本地實測落在個位數毫秒，給 50x 安全餘裕。
    assert elapsed_ms < 500


def test_full_valuation_of_all_combinations_completes_within_a_few_seconds():
    """含完整估值（carry 校準、Greeks、七情境、獲利區間求根）——這是
    真正代表使用者體感延遲的數字，比純枚舉貴一到兩個數量級是預期中的
    事（重計算量在估值本身，不在窮舉演算法）。"""
    snap = load_snapshot(FIX)
    p = AnalysisParams(strategy="call-fly", target_price=108.0, target_month="2026-10")
    qualified, _ = apply_filters(snap.contracts, p)
    triples, pair_report = generate_butterfly_triples(qualified, p)
    today = date(2026, 7, 15)
    t0 = time.perf_counter()
    vals = [evaluate_butterfly(lo, mid, hi, snap.spot, today, p)
           for lo, mid, hi in triples]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    per_combo_us = elapsed_ms * 1000.0 / len(vals)
    print(f"\n[完整估值量測] {len(vals)} 組合，{elapsed_ms:.1f} ms"
         f"（每組合 {per_combo_us:.1f} µs）")
    assert len(vals) > 5000
    # 寬鬆上界：本地實測約 350-500ms，給充分餘裕（單一 HTTP request，
    # 非批次 Refresh Run 的 60 秒硬上限路徑）。
    assert elapsed_ms < 5000


def test_end_to_end_analysis_with_the_dense_fixture_completes_promptly():
    """完整 `_analyze()`（含過濾、枚舉、估值、排名、Heatmap 矩陣、
    韌性計算、文字報告渲染）在這份密集 fixture 上的總耗時——記錄真實
    使用者體感延遲的上界，不是分項數字的加總（有共用計算的重疊）。"""
    request = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="call-fly", target_price=108.0,
                                   target_month="2026-10"),
        strategies=("call-fly",))
    t0 = time.perf_counter()
    result = service.run_offline(request, FIX)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"\n[端到端量測] 完整 _analyze() 耗時 {elapsed_ms:.1f} ms")
    assert result.results[0].status == "ok"
    assert elapsed_ms < 5000
