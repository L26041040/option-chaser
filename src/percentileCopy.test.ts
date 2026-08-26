/**
 * PC-01（#199，spec #198）：三個家族（買／賣腿 IV、Spread IV Gap、
 * Normalized Skew）的百分位說明文字——禁詞掃描＋兩項事實齊全的守門。
 *
 * 2026-08-26 真機驗收後改寫：三個常數升級為函式（`ivPercentileExplanation`／
 * `gapPercentileExplanation`／`skewPercentileExplanation`），直接把
 * 「第 N 百分位」翻譯成白話句、把 N 帶進句子裡（「現在的 IV 比過去一年
 * 大約 87% 的有效歷史觀測都高」），不再要求使用者自己把「百分位」這個
 * 統計學名詞換算成「比例」——這份測試同步改成呼叫函式而非讀靜態字串。
 *
 * 仿 `tests/test_redlines.py` 的禁詞掃描慣例，搬進前端獨立成一個檔案：
 * 那份 Python 測試的掃描範圍是 `option_chaser/`（引擎），本就不會碰到
 * `src/` 底下的 React／TypeScript 說明文字，這裡是它在前端的對應。
 *
 * 三個函式各自定義在自己家族的元件檔案裡（`./IvTrend`／`./SpreadSummary`／
 * `./IvHistory`），這裡只呼叫函式做內容檢查，不重新渲染元件——「這句話
 * 常駐可見」由各自的元件測試把關，這裡只管「這句話寫了什麼」。
 */
import { describe, expect, it } from "vitest";

import { skewPercentileExplanation } from "./IvHistory";
import { gapPercentileExplanation } from "./SpreadSummary";
import { ivPercentileExplanation } from "./IvTrend";

/** #199 AC 逐字列出的中文禁詞＋各自直接的英文對應。「貴」單獨列出時
 *  刻意不用詞邊界比對整個中文子字串偵測就足夠精準——三句說明文字都是
 *  我們自己寫的固定文案，不會意外出現「昂貴」以外語意不相關但包含
 *  「貴」字的詞（例如人名、專有名詞），所以不需要更複雜的邊界處理。 */
const BANNED = [
  "異常", "離群", "貴", "便宜", "昂貴", "推薦", "建議",
  "anomaly", "anomalous", "outlier", "expensive", "cheap", "recommend", "suggest",
];

/** 對照需求方原文例句「第 87 百分位」→「現在的 IV 比過去一年大約 87%
 *  的有效歷史資料都高」——用同一個數字，方便直接肉眼核對句子讀起來
 *  是不是那句話。 */
const SAMPLE_PERCENTILE = 0.87;

const FAMILIES: Record<string, (p: number | null) => string> = {
  "買／賣腿 IV": ivPercentileExplanation,
  "Spread IV Gap": gapPercentileExplanation,
  "Normalized Skew": skewPercentileExplanation,
};

describe("percentile 說明文字（PC-01／#199，2026-08-26 真機驗收後改寫為白話句）",
  () => {
  for (const [family, explain] of Object.entries(FAMILIES)) {
    describe(family, () => {
      const text = explain(SAMPLE_PERCENTILE);

      it("不含禁詞", () => {
        for (const term of BANNED) {
          expect(text.toLowerCase()).not.toContain(term.toLowerCase());
        }
      });

      it("直接把數字帶進句子——不是丟一句抽象定義要使用者自己換算", () => {
        // 需求方原文例句：「現在的 IV 比過去一年大約 87% 的有效歷史
        // 資料都高。」——同一個百分位（0.87）要能在句子裡看到 87 這個
        // 數字，且用「都高」這種直接比較句型，不再出現「百分位」這種
        // 需要額外解釋的統計學名詞（旁邊既有的 `percentileCaption`／
        // `metricCaption` 仍然顯示「第 87 百分位」，這句話負責把它
        // 翻成白話，不是取代它）。
        expect(text).toContain("87%");
        expect(text).toMatch(/都高/);
        expect(text).not.toMatch(/百分位/);
      });

      it("提到單日數字可能隨市場報價波動，不是把數字講成異常或昂貴", () => {
        expect(text).toMatch(/單日/);
        expect(text).toMatch(/波動/);
        expect(text).toMatch(/市場報價/);
      });

      it("短——不重複一堆 methodology，兩句話之內講完", () => {
        const sentences = text.split("。").filter((s) => s.length > 0);
        expect(sentences.length).toBeLessThanOrEqual(2);
      });

      it("沒有歷史觀測可比較時，誠實說沒有資料，不硬套一個假數字", () => {
        const empty = explain(null);
        expect(empty).not.toContain("%");
        expect(empty).toMatch(/沒有足夠/);
        for (const term of BANNED) {
          expect(empty.toLowerCase()).not.toContain(term.toLowerCase());
        }
      });
    });
  }

  it("買／賣腿 IV 與 Normalized Skew 用「過去一年」，Spread IV Gap 用" +
     "「共同歷史期間」——兩者視窗定義不同（Gap 的比較窗是兩張合約共同" +
     "存在的歷史，可能短於一年），措辭要如實反映各自真實的視窗", () => {
    expect(ivPercentileExplanation(SAMPLE_PERCENTILE)).toMatch(/過去一年/);
    expect(skewPercentileExplanation(SAMPLE_PERCENTILE)).toMatch(/過去一年/);
    expect(gapPercentileExplanation(SAMPLE_PERCENTILE)).toMatch(/共同歷史期間/);
  });

  it("Normalized Skew 沿用「偏斜」語彙，不硬套「IV」字樣", () => {
    const text = skewPercentileExplanation(SAMPLE_PERCENTILE);
    expect(text).toMatch(/偏斜/);
    expect(text).not.toMatch(/IV/);
  });

  it("數字換算跟旁邊既有 percentileCaption／metricCaption 顯示的百分位" +
     "一致——同樣用 Math.round(percentile*100)，不會出現兩個數字對不上" +
     "的情況（0.5 的邊界四捨五入方向也一致）", () => {
    expect(ivPercentileExplanation(0.874)).toContain("87%");
    expect(ivPercentileExplanation(0.875)).toContain("88%");
  });
});
