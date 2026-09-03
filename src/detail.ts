/**
 * 詳細頁的純函式（V5／#53）：策略名稱、漲幅格式、候選標題。
 *
 * 零金融計算——每個數字都是引擎算好放在契約裡的，這裡只負責「怎麼寫成
 * 一句人看得懂的話」。
 */
import { legQuantityPrefix, legSide, type Candidate } from "./api";

/**
 * 策略顯示名。與後端 `option_chaser/report.py` 的 `STRATEGY_LABELS`
 * 同一份字彙（QA1-09 已裁示用標準英文術語，不自創中文譯名）；後端加了
 * 新策略而這裡沒跟上，`tests/test_api_refresh.py` 的字彙漂移測試會紅。
 * 真的漏了也不會壞畫面——退回顯示原始代號，不假裝。
 */
const STRATEGY_LABELS: Record<string, string> = {
  "long-call": "Long Call",
  "long-put": "Long Put",
  "bull-call-spread": "Bull Call Spread",
  "bear-put-spread": "Bear Put Spread",
  "call-fly": "Call Butterfly",
  "put-fly": "Put Butterfly",
};

export function strategyLabel(strategy: string): string {
  return STRATEGY_LABELS[strategy] ?? strategy;
}

/**
 * 衍生方向顯示名（OPTION-CHASER-CLOSEOUT-001，Scenario Detail 補劇本
 * 摘要）。與後端 `option_chaser/models.py::DIRECTION_LABELS` 同一份
 * 字彙（`tests/test_frontend_contract.py` 的漂移測試把關）——後端加了
 * 新方向而這裡沒跟上，該測試會紅。`undefined`（舊存 View，
 * schema_version 尚未帶這個欄位）與未知代碼都誠實顯示「—」／原始代號，
 * 不假裝算得出方向。
 */
const DIRECTION_LABELS: Record<string, string> = {
  bullish: "看漲",
  bearish: "看跌",
  flat: "持平",
};

export function directionLabel(direction: string | undefined): string {
  if (direction === undefined) return "—";
  return DIRECTION_LABELS[direction] ?? direction;
}

/** 百分比的大小（不含方向）。方向由呼叫端自己說：有的地方用正負號，
 *  有的地方用「超出／低於」。 */
function magnitude(ratio: number): string {
  return `${Math.abs(ratio * 100).toFixed(1)}%`;
}

/** 帶正負號的百分比（目標漲幅）。 */
export function formatMove(ratio: number): string {
  return `${ratio >= 0 ? "+" : "-"}${magnitude(ratio)}`;
}

/**
 * 候選的一句話身分：`買 118 / 賣 122`。單腳候選只有一隻腿，寫成
 * `買 118`——硬要寫成價差的樣子會憑空生出一隻不存在的腿。
 *
 * T12（#228，Initial V2）：改成逐腿迭代（讀 `side` 判斷買賣），不再
 * 解構固定兩個變數——三腿以上的候選（Butterfly，T15／#232）不會被
 * 靜默丟腿，例如 `買 100 / 賣 105 / 買 110`。既有兩腿／單腿候選的
 * 輸出逐字不變。
 *
 * T16（#232，Initial V2）：口數 > 1 的腿（Butterfly 中腿賣 2 口）額外
 * 標出 `2×`——單純列出履約價會讓「中腿其實是兩口」這個結構性事實對
 * 使用者不可見（AC 明文：「中腿口數 2 要看得出來」）。既有兩腿／單腿
 * 候選 `quantity` 恆為 1，不觸發這個分支，輸出逐字不變。標示語法沿用
 * 後端 `service._comparison()` 既有的 `f"2×{mid_leg.strike:g}"` 慣例，
 * 前後端同一套寫法；`legSide()`／`legQuantityPrefix()`（`./api`）與
 * `expiry.ts::legPriceEntries()` 共用同一套「怎麼標示方向與口數」規則
 * （`/code-review` Standards 軸抓到兩處各自重複同一句三元運算式）。
 */
export function candidateTitle(candidate: Candidate): string {
  // `CandidateLegs` 的型別本身保證至少一隻腿（canonical boundary
  // 1<=len<=4），這裡不需要再防禦性檢查空陣列。
  return candidate.legs
    .map((leg) => `${legSide(leg)} ${legQuantityPrefix(leg)}${leg.strike}`)
    .join(" / ");
}
