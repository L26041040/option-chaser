#!/usr/bin/env python
"""重產既有四策略的數值 bitwise 基準（T01／#218，spec #217 §Q-A）。

`tests/fixtures/valuation_numeric_baseline.json` 凍結 `long-call`／
`long-put`／`bull-call-spread`／`bear-put-spread` 四個既有策略在固定
fixture（`tests/fixtures/xyz_v2_snapshot.json`）上的**估值輸出**：
劇本報酬、包絡量、情境向量、heatmap 格值、完成度、Greeks 比率、
Crossover comparator 等（完整欄位清單見
`tests/test_selection_regression.py::NUMERIC_BASELINE_FIELDS`）。

Initial V2 的 T02（逐腿 payoff 直算）與 T03（包絡量由 payoff 導出）
要換掉估值核心，唯一的驗收判準是**畫面零變化**——這份基準就是那個
「零變化」的可執行證明。

**什麼時候可以重跑這支腳本**：只有在數字**確定是刻意改變**的時候，
而且要跟需求方確認過。已知的合法時機目前有兩個：

1. **T02（#219，2026-08-30 Owner 核准）**——`spread_scenario_value` 的
   `[0, width]` clamp 廢除後，兩腿 vendor IV 不同（真實市場 skew）時，
   逐腿直算值可能微幅超出 width；舊 clamp 會無聲地夾掉這個張力，新版
   如實顯示。實測影響：XYZ bull-call-spread 105/110 候選的 3 個
   Heatmap 格點（`matrix.cells[9][0]`／`[10][0]`／`[10][1]`）。範圍
   極窄——僅此一組候選、僅這 3 格，其餘 1999 格與其餘三個策略逐位元
   不變，已用「監控每一種輸出、不是只看測試綠燈」的方式核對過
   （CLI golden fixtures、契約樣本皆零漂移）。
2. **T04（#220）**把 friction 自 canonical model 移除（#217 決策 D）。
3. **T09（#222，2026-08-31）**——單腿策略補齊 `expiry_top10`／
   `expiry_ranked` 到期日分組欄位後，`candidate_pool` 隨之收進過去
   從未序列化過的候選（單腿 MVP 範圍當初只做到 `expiry_best`，附錄
   A13）。這是**純新增**：`long-call` 4 筆、`long-put` 5 筆候選加入
   基準，既有候選逐一核對零修改零刪除，`bull-call-spread`／
   `bear-put-spread` 兩個策略（T09 AC 明文要求「Spread 路徑逐位元
   不變」）100% 零差異——已用腳本逐鍵比對過（不是只看測試綠燈），見
   T09 commit 訊息。

4. **T12（#228，2026-08-31）**——候選契約每一腿新增顯式 `side`／
   `quantity` 欄位（取代「陣列位置＝方向」的隱性慣例），候選新增
   `breakeven_points`（損益兩平點集合的傳輸格式，值＝`[breakeven]`）。
   兩者皆**純加法**：逐一核對過整個基準檔案——四個既有策略每一腿的
   原有欄位值一字不變，新增的 `side`／`quantity` 值正確（既有兩腿
   策略恆為 `buy`／`sell`、口數恆為 1），`breakeven_points` 恆等於
   `[既有 breakeven 值]`；除了這兩處新增，其餘任何欄位、任何候選的
   數值零變化（含新增／刪除候選集合本身也不變）。

除了以上四個已知、已記錄的例外，其餘期間跑出差異＝有 bug，不是基準
過期。

    PYTHONPATH=. .venv/bin/python scripts/gen_numeric_baseline.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 快照與比對邏輯的單一來源就是守門測試本身——這裡刻意不複製一份，
# 否則基準與守門會各自漂移。
sys.path.insert(0, str(ROOT / "tests"))

from test_selection_regression import (  # noqa: E402
    SCENARIOS, SNAP, _NUMERIC_BASELINE_PATH, snapshot_numbers,
)

OUT = ROOT / _NUMERIC_BASELINE_PATH


def main() -> None:
    payload = {
        "_about": (
            "既有四策略的數值 bitwise 基準（T01／#218）。由 "
            "scripts/gen_numeric_baseline.py 產生，勿手改。"
            "重產條件見該腳本 docstring。"),
        "fixture": SNAP,
        "strategies": {s: snapshot_numbers(s) for s in sorted(SCENARIOS)},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    n = sum(len(v["candidates"]) for v in payload["strategies"].values())
    print(f"寫入 {OUT}（{len(payload['strategies'])} 個策略、{n} 個候選、"
          f"{OUT.stat().st_size / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
