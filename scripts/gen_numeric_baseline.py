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

5. **T14（#233，Initial V2）**——熱力圖 matrix 傳輸壓縮（座標軸去重
   ＋格值捨入，研究 #216 定案）。這是**破壞性**改變 `matrix`／
   `comparator.matrix` 的既有形狀：`{prices, dates, cells}`（`cells`
   為二維陣列）→ `{axis_index, cells}`（`cells` 攤平成一維陣列，並
   捨入到 `store.MATRIX_CELL_DECIMALS`＝4 位小數——遠細於畫面顯示
   精度，不造成任何看得到的格值差異）；`prices`／`dates` 移到頂層新增
   的 `axis_sets` 陣列，本快照函式（`snapshot_numbers()`）同步新增
   `"axis_sets"` 欄位捕捉它，否則座標軸內容本身被動過但索引剛好沒變
   時會偵測不到。四個既有策略的**估值本身**（`baseline_return`／
   Greeks／情境向量等其餘全部欄位）逐位元不變，只有 `matrix` 這一項
   的傳輸形狀改變，已用腳本逐鍵比對過（不是只看測試綠燈）。
6. **T15（#230，Initial V2）**——Butterfly（`call-fly`／`put-fly`）
   落地，候選契約新增 `profit_region`（非單調結構的獲利區間，只有
   Butterfly 用得到）。既有四策略這個欄位恆為 `None`——純加法，逐鍵
   核對過既有四個策略的其餘全部欄位（含新增的 `call-fly`／`put-fly`
   各自候選集合本身）零修改零刪除，只有這一個新增鍵。
7. **REPAIR-09（#246，OPTION-CHASER-REPAIR-001，2026-09-01）**——單腿
   （`long-call`／`long-put`）排名基準估值日從固定日曆錨點（附錄
   A9）改為候選**自身到期日**，與 Vertical／Butterfly（T3／#17）既有
   語意對齊，修掉 #052 audit 找到的跨 family champion 系統性灌水
   （Root Cause C：到期日晚於錨點的單腿候選會殘留時間價值，Vertical／
   Butterfly 卻已經是純內在價值，兩者混進同一個排行榜）。四步驟
   collateral-drift 驗證：(1) 修法前對此基準跑 `bitwise_frozen` 四條
   測試，逐一綠燈，確認 diff 工具本身在真的沒有差異時如實回報零差異；
   (2) 修法後重跑，只有 `long-call` 一個策略紅燈、且只有唯一一個候選
   `long-call|90|2026-11-20`（到期日 2026-11-20，晚於這份 fixture 的
   `target_month="2026-10"` 錨點 2026-10-16，人工核對過）的
   `baseline_pnl`／`baseline_return`／`l2`／`l3` 四個欄位改變，
   `long-put`／`bull-call-spread`／`bear-put-spread` 三個策略逐位元
   零差異（`bull-call-spread`／`bear-put-spread` 為 AC 硬約束）；
   (3) 已納入本次重產；(4) 另以三 family 全開的真實劇本
   （`tests/fixtures/xyz_v7_butterfly_moderate.json`）對照修法前後的
   跨 family champion——`test_cross_family_champion_identity_is_
   recorded_as_a_baseline`（`target_month="2026-09"`，baseline 到期日
   恰好等於錨點）證明身份不變，但這個 target_month 下 champion 的
   **數值**結構上不可能被本票影響（baseline==anchor 時單腿的排名
   基準估值日修法前後是同一天）；真正證明「數值合法改變、且改變只
   來自單腿修正」的是另一條測試
   `test_cross_family_champion_baseline_return_is_corrected_when_
   baseline_expiry_is_after_anchor`（`target_month="2026-08"`，
   baseline 到期日 2026-09-18 晚於錨點 2026-08-21 28 天）——已用
   `git stash` 對照修法前後真實數字：single-leg champion 從
   1.1926288317629354（灌水）修正到 0.9569471624266144，
   vertical-spread／butterfly 兩個 family 逐位元不變，champion 身份
   （butterfly）不受影響（這條測試在對修法前的程式碼跑時會真的紅燈，
   已驗證過，不是恆真的裝飾性斷言）。`test_q_no_longer_moves_single_
   leg_ranking_at_any_expiry_after_the_fix` 證明的是另一件事——q 這個
   輸入本身對 baseline_return 的影響在修法後消失，不是修法前後的
   before/after 數值比對。`ranking.py`／`filters.py`／
   `evaluate_spread()`／`evaluate_butterfly()` 內部估值邏輯零改動——
   修法侷限在 `valuation.py::evaluate_contract()` 的單一行（原本
   `target = p.anchor`，後改為直接沿用既有變數 `expiry`，不再另立
   `target` 別名）。

8. **OPTION-CHASER-CLOSEOUT-003（2026-09-03，PR #250 merge gate
   review）**——`ranking.return_at_price()` 的**單腿**分支估值日補上
   REPAIR-09（#246）的修正。REPAIR-09 依票面明文「`ranking.py` 零
   改動」只改了 `valuation.evaluate_contract()`，`return_at_price()`
   還停在固定日曆錨點（附錄 A9），於是該函式 docstring 自己宣告的
   不變量（`return_at_price(v, p.target_price, p) == baseline_
   return(v)`，「口徑與主排名數字完全相同」）對**到期日晚於錨點的
   單腿候選**變成假的；守門測試
   `test_single_leg_at_target_price_equals_baseline_return` 的 fixture
   到期日恰好等於錨點，正是它姊妹測試（spread 版）docstring 早就
   點名的**空斷言**，因此沒有紅燈。本輪 merge gate 的兩軸
   `/code-review` 獨立收斂到同一個缺陷後修正。
   影響範圍：**只有一行**——`long-call|90|2026-11-20`（唯一到期日
   晚於這份 fixture 錨點的單腿候選）的 `price_ladder[0].return`
   `1.2652057829186634` → `1.2388059701492538`，新值正好等於該候選
   在 REPAIR-09 已經修正過的 `baseline_return`，也就是不變量恢復
   本身。`long-put`／`bull-call-spread`／`bear-put-spread` 三個策略
   逐位元零差異（實測 `bitwise_frozen` 四條測試：1 failed／3 passed，
   只有 long-call 紅），V1 Vertical 凍結硬約束成立。守門測試同時
   補上 `test_single_leg_equality_holds_when_expiry_is_not_the_anchor`
   （比照 spread 版 parametrize 錨點前／上／後三種到期日），已驗證
   對修法前的程式碼會紅燈。

9. **OPTION-CHASER-CLOSEOUT-004（2026-09-03，PR #250 review Finding
   2）**——heatmap crossover 的傳輸捨入漂移。候選 matrix 與 comparator
   matrix 原本各自獨立捨入到 `store.MATRIX_CELL_DECIMALS`（1e-4），
   前端 `crossoverEdges()`／`crossoverFavoredSide()`／`crossoverSides()`
   再對捨入後的值做**精確的正負號**判斷——真差小於捨入誤差的格子會被
   捨成同一個數字（`sign()` 變 0），憑空生出或抹掉 crossover 邊界。
   實測兩份 fixture **6/6 有 comparator 的候選 edge 集合都改變**
   （bull-call-spread 精確 17 條 vs 捨入後 20 條）。修法在
   `store._comparator_matrix_to_dict()`：符號被捨錯的 comparator 格值
   推到候選值的正負一格，保住逐格
   `sign(候選 − comparator)`；comparator 的格值結構上不顯示在畫面上
   （`Heatmap.tsx` 只顯示候選自己的 matrix 與 comparator 的標籤／
   成本），偏離真值上界 1.5e-4，比顯示精度（整數百分點）細兩個數量級。
   影響範圍：**只有 6 格**，全部在 `comparator.matrix.cells` 內、每格
   恰好變動一個捨入網格（±1e-4）——已用腳本逐鍵比對四個策略的全部
   欄位，`changed=6 added=0 removed=0`，候選自己的 matrix 與全部金融
   數值（`baseline_return`／`max_profit`／`max_loss`／`breakeven`／
   Greeks／`price_ladder` 等）逐位元不變。Butterfly 的 Finding 1
   修正不影響本基準（`call-fly`／`put-fly` 不在這四個既有策略裡）。

除了以上九個已知、已記錄的例外，其餘期間跑出差異＝有 bug，不是基準
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
