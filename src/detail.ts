/**
 * 詳細頁的純函式（V5／#53）：策略名稱、漲幅格式、候選標題。
 *
 * 零金融計算——每個數字都是引擎算好放在契約裡的，這裡只負責「怎麼寫成
 * 一句人看得懂的話」。
 */
import type { Candidate, PricePoint } from "./api";
import { money } from "./scenarios";

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

/**
 * V8（#56）：韌性 7 情境的顯示名，與 `option_chaser/scenarios.py` 的
 * `SCENARIO_NAMES` 同一份字彙（`tests/test_frontend_contract.py` 把關）。
 */
export const SCENARIO_NAMES: Record<string, string> = {
  S1: "不漲", S2: "半程", S3: "大半程", S4: "晚30天",
  S5: "晚90天", S6: "IV最保守", S7: "Natural成交",
};

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

const LADDER_LABELS: Record<PricePoint["label"], string> = {
  worst: "最差", target: "目標", best: "最好",
};

/**
 * 劇本區間三價位對照（V7／#55）。
 *
 * 回傳 null ＝ 這一區不該出現：使用者兩端都沒設定時，`price_ladder` 只有
 * 目標價一項，畫一張「只有一格的對照表」對不上「對照」二字，什麼也沒比較到。
 * V7 之前落盤的結果沒有這個欄位，一併當作沒設定。
 *
 * 報酬不在這裡算——`return` 是引擎給的，口徑與頭條數字相同。
 */
export function priceLadderView(
  candidate: Candidate,
): { label: string; ret: number }[] | null {
  const ladder = candidate.price_ladder ?? [];
  if (ladder.length < 2) return null;
  return ladder.map((p) => ({
    label: `${LADDER_LABELS[p.label]} ${money(p.price)}`,
    ret: p.return,
  }));
}

/**
 * V8（#56，spec R1 §2.3／§4.2）：分析報告新版型①「交易摘要」的一句話
 * 結論，格式固定——`動作 + 到期 + 履約組合 + 結構名稱 + 成本 → 損益兩平
 * → 最大獲利`（家族 C 實際發行 trade idea 的標準句型）。全部由既有欄位
 * 拼接，零金融計算；Long Call 的 `max_profit` 依定義為 `null`（無上限），
 * 必須顯示「無上限」，不可留白或顯示 0（R1 §1 第 3 點例外）。
 */
export function reportConclusion(candidate: Candidate, strategy: string): string {
  const expiry = candidate.legs[0]?.expiry ?? "—";
  const maxProfit = candidate.max_profit === null
    ? "無上限"
    : money(candidate.max_profit);
  return `${candidateTitle(candidate)} ${expiry} 到期 ${strategyLabel(strategy)}，` +
    `成本 ${money(candidate.natural_cost)} → 損益兩平 ${money(candidate.breakeven)} → ` +
    `最大獲利 ${maxProfit}`;
}

/**
 * max payout ratio（R1 §2.3 GS 慣例，機構愛用的壓縮指標：最大獲利／成本，
 * 如「大於 8 倍」）——`max_profit / natural_cost`，純除法。Long Call
 * 無上限時回傳「無上限」，不是硬湊一個假倍數。
 */
export function maxPayoutRatioText(candidate: Candidate): string {
  if (candidate.max_profit === null) return "無上限";
  return `${(candidate.max_profit / candidate.natural_cost).toFixed(1)}x`;
}

/** 成本佔現價的比例（R1 §3.2，純除法）。 */
export function costPctOfSpot(candidate: Candidate, spot: number): number {
  return candidate.natural_cost / spot;
}

/** 損益兩平距現價的比例，帶正負號（R1 §3.2，純除法）。 */
export function breakevenDistancePct(candidate: Candidate, spot: number): number {
  return (candidate.breakeven - spot) / spot;
}

/**
 * 保本門檻的三態文字——對照 `option_chaser/report.py::_resilience_lines`
 * 的既有三態邏輯（`k is None`／`k <= 0`／其餘），純格式化、不重算門檻
 * 本身（`completion_threshold` 是引擎 `scenarios.completion_scan` 算好的）。
 */
export function completionThresholdText(k: number | null): string {
  if (k === null) return "劇本全成仍不保本";
  if (k <= 0) return "0%（已保本）";
  return `完成 ${(k * 100).toFixed(1)}%`;
}
