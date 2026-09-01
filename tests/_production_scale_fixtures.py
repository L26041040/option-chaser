"""REPAIR-03／REPAIR-10（#240／#247，#052 audit）共用的 production-
scale 效能量測基礎設施——`/code-review` Spec 軸抓到的真發現：
`tests/test_repair03_performance.py`（引擎層 `run_offline()`）與
`tests/test_api_performance_guard.py`（HTTP 層 `_refresh_and_save()`）
各自獨立複製了同一份真實 `dividend_loader`／fixture 路徑／20 秒門檻，
兩邊分頭維護容易漂移（例如其中一邊改了 q 的數值，另一邊沒跟著改，
兩份「production-scale 基準」就悄悄不再測同一件事）。收斂成單一
定義來源，不用 leading underscore 檔名（`_` 前綴讓 pytest 不會把
它當測試檔收集）以外的方式取巧。

不叫 `conftest.py`——這兩個常數／函式不是 fixture，是普通的 import，
用 `conftest.py` 的自動注入機制反而會讓「這個值從哪裡來」變得不透明；
本檔案刻意保持「顯式 import、顯式呼叫」。"""
from datetime import date

from option_chaser.dividends import DividendHistory, DividendRecord

# 5 到期日×60 履約價/側＝600 張合約，滿足 AC「≥5 到期日×≥60 履約價/側」
# 的強制 re-profile 規模要求（`scripts/gen_butterfly_fixture.py` 產生）。
PRODUCTION_SCALE_FIXTURE = "tests/fixtures/xyz_v8_production_scale.json"

# 20 秒 acceptance threshold（#237 訂定）。測試門檻抓 threshold 本身、
# 不另外加安全餘裕——這幾條測試的目的就是「有沒有超過這個門檻」，加
# 餘裕反而會讓真正貼近門檻的回歸被誤判為通過。
ACCEPTANCE_THRESHOLD_SECONDS = 20.0


def real_dividend_loader(symbol: str, today: date):
    """真實 `dividend_loader` 介面（不是直接手設
    `AnalysisParams.q_by_symbol`）——算出的 q 是非零值，真的會讓
    `calibrate_leg()` 走 IV 反解分支，不是退回 fallback 短路。比照
    `tests/test_q_wiring.py` 既有慣例的形狀。"""
    history = DividendHistory(
        symbol=symbol, as_of="2026-07-14", source="yahoo", stale=False,
        distributions=(DividendRecord("2026-06-01", 3.5),))
    return history, "配息資料 yahoo（2026-07-14，1 筆，效能量測用固定值）"


def offline_rate_loader(today: date):
    """利率不是這些測試要驗證的變因，維持既有 fallback 常數利率，
    決定性、零網路。"""
    return None, "test：離線重放，未啟用利率曲線"
