"""REPAIR-03（#240，FIX-02，#052 audit）：強制 production-equivalent
re-profile＋FIX-03 決策閘門。

AC 明文要求：修完 `calibrate_leg()` memoization 之後，**必須**用
production-equivalent 規模（≥5 到期日×≥60 履約價/側）＋真實非零 q
（真實 `dividend_loader`，不是直接手設 `q_by_symbol`）重新量測單一
劇本三個 family 全開的完整分析時間，對照 #237 的 20 秒 acceptance
threshold 明確判定 FIX-03（Butterfly 枚舉重新設計）是否需要施工，
且判定必須有實測數字佐證。

`tests/fixtures/xyz_v8_production_scale.json`（`scripts/gen_butterfly_
fixture.py` 新增）：5 到期日×60 履約價/側＝600 張合約，call-fly 在
這份 fixture 上枚舉出 120,933 組候選——與 #052 audit 引用的
production-scale 量級（171,100 組，60 履約價×5 到期日的理論組合數）
同一個數量級，差異來自 `generate_butterfly_triples()` 既有的 A 層
`net_mid<=0` 健全性判準會篩掉一部分組合，不是本次刻意湊出來的數字。

**修法前後實測（2026-09-01，本機容器，一次性量測，記錄於此供追溯，
不是每次 CI 都重新量測「修法前」——那個版本已經不存在於工作樹，且
單次要價 154 秒，不該是常態 CI 負擔）**：

用 `git worktree` 拉出修法前的乾淨版本（commit `18b58e8`）與目前
工作樹分別跑同一支腳本（`/tmp` 一次性腳本，未進 repo），真實
`dividend_loader`（q≈0.035，非直接手設 `AnalysisParams.q_by_symbol`）：

| 情境 | 修法前 | 修法後 | 加速比 |
|---|---|---|---|
| 3 family 全開（single-leg／vertical-spread／butterfly，bullish 劇本） | 154.236s | 7.543s | 20.4x |
| Legacy vertical-only（bull-call-spread／bear-put-spread） | 6.992s | 1.120s | 6.2x |

修法前 154.236 秒**超過 Vercel serverless 60 秒硬上限**，與
production 觀察到的 timeout 症狀直接對應；修法後 7.543 秒遠低於
#237 訂出的 20 秒 acceptance threshold。

**FIX-03 決策閘門判定：`FIX-03: NOT_NEEDED / NOT_PLANNED`**
（實測 7.543s ≤ 20s，`calibrate_leg()` memoization 本身已經足夠，
不需要再重新設計 Butterfly 枚舉演算法）。

下面的 `test_production_scale_three_family_analysis_stays_under_the_
twenty_second_threshold` 是這個判定的永久 CI 回歸鎖：往後任何改動
（memoization 邏輯被意外移除、枚舉演算法複雜度上升等）只要讓
production-scale 場景重新超過 20 秒，這條測試就會紅，不必等下一次
使用者回報 timeout 才發現。"""
import time
from datetime import date

from option_chaser import service
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v8_production_scale.json"

# 20 秒 acceptance threshold（#237 訂定），測試門檻抓threshold 本身、
# 不另外加安全餘裕——這條測試的目的就是「有沒有超過這個門檻」，加餘裕
# 反而會讓真正貼近門檻的回歸被誤判為通過。
ACCEPTANCE_THRESHOLD_SECONDS = 20.0


def _real_dividend_loader(symbol, today):
    """比照 `tests/test_q_wiring.py` 既有慣例——真實 `dividend_loader`
    介面（不是直接手設 `AnalysisParams.q_by_symbol`），算出的 q 是
    非零值，真的會讓 `calibrate_leg()` 走 IV 反解分支，不是退回
    fallback 短路。"""
    history = DividendHistory(
        symbol=symbol, as_of="2026-07-14", source="yahoo", stale=False,
        distributions=(DividendRecord("2026-06-01", 3.5),))
    return history, "配息資料 yahoo（2026-07-14，1 筆，profiling 用固定值）"


def test_production_scale_three_family_analysis_stays_under_the_twenty_second_threshold():
    """FIX-03 決策閘門本體：單一劇本三個 family 全開，production-scale
    規模（600 張合約），真實非零 q，完整分析時間必須 ≤ 20 秒——本票
    修法前這個場景實測 154.236 秒（`git worktree` 對照修法前的
    commit `18b58e8` 量測，見檔頭紀錄），本票修法後降到 7.543 秒。"""
    p = AnalysisParams(target_price=110.0, target_month="2026-09",
                       strategy="long-call")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("long-call", "long-put", "bull-call-spread",
                   "bear-put-spread", "call-fly", "put-fly"))

    t0 = time.perf_counter()
    result = service.run_offline(req, FIX, dividend_loader=_real_dividend_loader)
    elapsed = time.perf_counter() - t0

    by_strategy = {r.strategy: r for r in result.results}
    assert by_strategy["long-call"].status == "ok"
    assert by_strategy["bull-call-spread"].status == "ok"
    assert by_strategy["call-fly"].status == "ok"
    # 確認真的走了 IV 反解分支（q 非零、有候選校準成功），不是意外
    # fallback 短路讓這條測試表面通過、實際沒測到重點。
    assert result.request.base_params.q_by_symbol is not None
    assert result.request.base_params.q_by_symbol > 0.0
    assert any(cv.carry_calibrated for cv in by_strategy["long-call"].candidates)

    print(f"\n[REPAIR-03 production-scale] 3 family 全開耗時 {elapsed:.3f}s "
         f"（門檻 {ACCEPTANCE_THRESHOLD_SECONDS}s）")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS, (
        f"production-scale 三 family 全開耗時 {elapsed:.3f}s 超過 20 秒"
        f"acceptance threshold——FIX-03（Butterfly 枚舉重新設計）需要"
        f"重新評估是否施工")


def test_production_scale_legacy_vertical_only_analysis_also_benefits():
    """AC「Legacy vertical-only 路徑的效能改善一併量測記錄，確認
    memoization 對它也生效」——不要求它原本就慢（修法前 6.992s 本來
    就在可接受範圍），只確認同一個修法確實覆蓋到它，且門檻同樣守住。"""
    p = AnalysisParams(target_price=110.0, target_month="2026-09",
                       strategy="bull-call-spread")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("bull-call-spread", "bear-put-spread"))

    t0 = time.perf_counter()
    result = service.run_offline(req, FIX, dividend_loader=_real_dividend_loader)
    elapsed = time.perf_counter() - t0

    by_strategy = {r.strategy: r for r in result.results}
    assert by_strategy["bull-call-spread"].status == "ok"
    assert any(cv.carry_calibrated for cv in by_strategy["bull-call-spread"].candidates)

    print(f"\n[REPAIR-03 production-scale] legacy vertical-only 耗時 "
         f"{elapsed:.3f}s（修法前實測 6.992s）")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS
