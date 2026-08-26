/**
 * PC-01（#199，spec #198）：三個家族（買／賣腿 IV、Spread IV Gap、
 * Normalized Skew）的百分位說明文字——禁詞掃描＋兩項事實齊全的守門。
 *
 * 仿 `tests/test_redlines.py` 的禁詞掃描慣例，搬進前端獨立成一個檔案：
 * 那份 Python 測試的掃描範圍是 `option_chaser/`（引擎），本就不會碰到
 * `src/` 底下的 React／TypeScript 說明文字，這裡是它在前端的對應。
 *
 * 三個常數各自定義在自己家族的元件檔案裡（`./IvTrend`／`./SpreadSummary`／
 * `./IvHistory`），這裡只 import 字串本身做內容檢查，不重新渲染元件——
 * 「這句話常駐可見」由各自的元件測試把關，這裡只管「這句話寫了什麼」。
 */
import { describe, expect, it } from "vitest";

import { SKEW_PERCENTILE_EXPLANATION } from "./IvHistory";
import { GAP_PERCENTILE_EXPLANATION } from "./SpreadSummary";
import { IV_PERCENTILE_EXPLANATION } from "./IvTrend";

/** #199 AC 逐字列出的中文禁詞＋各自直接的英文對應。「貴」單獨列出時
 *  刻意不用詞邊界比對整個中文子字串偵測就足夠精準——三句說明文字都是
 *  我們自己寫的固定文案，不會意外出現「昂貴」以外語意不相關但包含
 *  「貴」字的詞（例如人名、專有名詞），所以不需要更複雜的邊界處理。 */
const BANNED = [
  "異常", "離群", "貴", "便宜", "昂貴", "推薦", "建議",
  "anomaly", "anomalous", "outlier", "expensive", "cheap", "recommend", "suggest",
];

const FAMILIES: Record<string, string> = {
  "買／賣腿 IV": IV_PERCENTILE_EXPLANATION,
  "Spread IV Gap": GAP_PERCENTILE_EXPLANATION,
  "Normalized Skew": SKEW_PERCENTILE_EXPLANATION,
};

describe("percentile 說明文字禁詞掃描（PC-01／#199）", () => {
  for (const [family, text] of Object.entries(FAMILIES)) {
    describe(family, () => {
      it("不含禁詞", () => {
        for (const term of BANNED) {
          expect(text.toLowerCase()).not.toContain(term.toLowerCase());
        }
      });

      it("講清楚定義：目前值在有效歷史觀測中的相對位置", () => {
        // Spread IV Gap 的視窗是兩張合約「共同存在」的歷史期間，可能
        // 短於一年（`shared_history_span_days` 語意），措辭因此誠實地
        // 講「共同歷史期間」而非套用「近一年」樣板——買／賣腿 IV 與
        // Normalized Skew 兩個家族的視窗才真的是近一年，各自的文案
        // 反映各自真實的視窗定義。
        expect(text).toMatch(/近一年|歷史期間/);
        expect(text).toMatch(/歷史觀測|有效觀測/);
        expect(text).toMatch(/比例|百分位/);
      });

      it("提到單日讀數可能隨市場報價波動，不是把高百分位講成異常或昂貴", () => {
        expect(text).toMatch(/單日/);
        expect(text).toMatch(/波動/);
        expect(text).toMatch(/市場報價/);
      });
    });
  }

  it("Normalized Skew 沿用「偏斜」語彙，不硬套「IV」字樣", () => {
    expect(SKEW_PERCENTILE_EXPLANATION).toMatch(/偏斜/);
    expect(SKEW_PERCENTILE_EXPLANATION).not.toMatch(/IV/);
  });
});
