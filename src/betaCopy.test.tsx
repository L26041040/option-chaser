/**
 * PB-12（#302，Anonymous Public Beta）：設定頁免責聲明（SW-10／#340
 * 起取代原本常駐首頁的 `BetaNotice`）／頁尾／隱私頁的禁詞掃描——票面
 * §7 明文「不得出現『推薦』『建議』『應該』或任何投資建議暗示」。
 *
 * 仿 `src/percentileCopy.test.ts` 的既有慣例獨立成一個檔案，但這裡的
 * 禁詞規則比那份更細——不能對「建議」整個字串一律禁止：本站既有的
 * 免責聲明（`option_chaser/report.py::disclaimer_text()`／
 * `_DISCLAIMER_LINE`）本身就寫著「不構成投資建議」「不提供個人化投資
 * 建議」，這正是 §7 要求的那句話本身，硬性禁止這個子字串會連
 * production 既有、必要的免責聲明都通不過。真正要擋的是**正面推薦
 * 語句**（例如「建議您」「我們建議」「值得投資」），不是「不是投資
 * 建議」這種否定句——這與 `disclaimer_text()` 的既有做法一致，不是
 * 這裡另外發明的例外。
 *
 * 「推薦」「應該」兩個詞本身在本票新增的文案裡完全用不到（不像
 * 「建議」有一句必要的否定用法），因此維持整字串禁止，不需要同一種
 * 例外處理。
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DisclaimerSection from "./DisclaimerSection";
import Footer from "./Footer";
import PrivacyPage from "./PrivacyPage";

/** 整字串禁止——本票新增文案完全不需要用到這兩個詞。 */
const STRICTLY_BANNED = ["推薦", "應該", "recommend", "should"];

/** 「建議」只允許出現在否定句型裡——涵蓋既有 `disclaimer_text()`
 *  的措辭（「不構成……投資建議」「不應被視為……投資建議」）與本票
 *  自己新增文案用的另外兩種說法（「不是投資建議」「非投資建議」，
 *  後者是頁尾的精簡版）。任何其他出現方式（例如「建議您」「我們
 *  建議」）都是真正的投資建議暗示，禁止。 */
const ALLOWED_SUGGESTION_PATTERN = /(不(是|構成|應被視為|提供)|非).{0,10}投資建議/;

const COMPONENTS: [string, () => JSX.Element][] = [
  ["設定頁免責聲明（SW-10／#340 起取代首頁常駐 Beta 說明）", () => <DisclaimerSection />],
  ["全站頁尾", () => <Footer />],
  ["隱私頁", () => <PrivacyPage />],
];

describe("Beta 首頁說明／頁尾／隱私頁：投資建議暗示禁詞掃描（PB-12／#302）", () => {
  for (const [name, factory] of COMPONENTS) {
    it(`${name}：不含「推薦」「應該」等正面推薦詞`, () => {
      const text = render(factory()).container.textContent ?? "";
      for (const banned of STRICTLY_BANNED) {
        expect(text).not.toContain(banned);
      }
    });

    it(`${name}：出現「建議」時，每一次都落在既有免責聲明的否定句型裡`, () => {
      const text = render(factory()).container.textContent ?? "";
      const occurrences = text.split("建議").length - 1;
      if (occurrences === 0) return; // 這個元件根本沒用到這個詞，直接過
      const matches = text.match(new RegExp(ALLOWED_SUGGESTION_PATTERN, "g")) ?? [];
      expect(matches.length).toBe(occurrences);
    });
  }

  it("三個元件合起來至少講過一次『不是投資建議』這件事（AC9 硬性要求）", () => {
    const combined = COMPONENTS
      .map(([, factory]) => render(factory()).container.textContent ?? "")
      .join("\n");
    expect(combined).toMatch(ALLOWED_SUGGESTION_PATTERN);
  });
});
