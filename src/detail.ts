/**
 * 詳細頁的純函式（V5／#53）：追平價格的三態、策略名稱、漲幅格式。
 *
 * 零金融計算——追平價格 S* 由引擎算好放在 `candidate.catchup_price`
 * （`option_chaser.valuation.catchup_price`），目標漲幅在 `meta.target_move`。
 * 這裡只負責「怎麼寫成一句人看得懂的話」。
 */
import type { Candidate, Leg } from "./api";
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
 * 追平價格的比較對象怎麼寫：`28/1 110 Long Call`（v3 #9 指定格式）。
 *
 * 名字裡有 `catchup` 是刻意的——它**恆為 Long Call**，不看 `leg.option_type`：
 * 追平比較的對象就是「同履約價、同到期的 Long Call」（D1／#14 的定義），
 * 買腿本身是 put 時後端也是去快照裡找同履約價的 call。叫
 * `contractLabel` 會讓人以為它會照著腿的權別走。
 */
export function catchupContractLabel(leg: Leg): string {
  const [year, month] = leg.expiry.split("-");
  // `String(110)` ＝ "110"、`String(122.5)` ＝ "122.5"：整數不拖 `.0`，
  // 半檔履約價原樣保留，不必自己判斷。
  return `${year.slice(2)}/${Number(month)} ${leg.strike} Long Call`;
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

/**
 * 追平價格的三態。
 *
 * - `null`：這個候選沒有「與 Long Call 比較」的意義（單腳策略），整塊不顯示
 * - `price === null`：同履約價 Call 報價缺失＝無法計算，如實說，不拋錯
 * - 其餘：S* 與它離目標價多遠；`beatsTarget` ＝ S* ≤ 目標價，
 *   代表「Long Call 在本劇本內就已經勝過這組 Spread」
 */
export interface CatchupView {
  contract: string;
  price: string | null;
  gap: string | null;
  beatsTarget: boolean;
}

export function catchupView(
  candidate: Candidate,
  targetPrice: number,
): CatchupView | null {
  const buy = candidate.legs[0];
  // 兩腿才有賣腿封頂可言；單腳候選跟 Long Call 比較是跟自己比。
  if (!buy || candidate.legs.length < 2) return null;

  const contract = catchupContractLabel(buy);
  const star = candidate.catchup_price;
  if (star === null) return { contract, price: null, gap: null, beatsTarget: false };

  const ratio = (star - targetPrice) / targetPrice;
  // 小數一位而非票上示例的整數：整數會把「超出 0.4%」寫成「超出 0%」，
  // 而且全站其他百分比都是一位小數。
  const gap = `${ratio >= 0 ? "超出" : "低於"}目標價 ${magnitude(ratio)}`;
  return {
    contract,
    price: money(star),
    gap,
    beatsTarget: star <= targetPrice,
  };
}

const LADDER_LABELS: Record<string, string> = {
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
): { label: string; price: string; ret: number }[] | null {
  const ladder = candidate.price_ladder ?? [];
  if (ladder.length < 2) return null;
  return ladder.map((p) => ({
    label: `${LADDER_LABELS[p.label] ?? p.label} ${money(p.price)}`,
    price: money(p.price),
    ret: p.return,
  }));
}
