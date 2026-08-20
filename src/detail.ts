/**
 * 詳細頁的純函式（V5／#53）：策略名稱、漲幅格式、候選標題。
 *
 * 零金融計算——每個數字都是引擎算好放在契約裡的，這裡只負責「怎麼寫成
 * 一句人看得懂的話」。
 */
import type { Candidate } from "./api";

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
};

export function strategyLabel(strategy: string): string {
  return STRATEGY_LABELS[strategy] ?? strategy;
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
 */
export function candidateTitle(candidate: Candidate): string {
  const [buy, sell] = candidate.legs;
  if (!buy) return "—";
  return sell ? `買 ${buy.strike} / 賣 ${sell.strike}` : `買 ${buy.strike}`;
}
