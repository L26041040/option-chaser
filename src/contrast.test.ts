/**
 * WCAG AA 文字對比的自動驗收（QA-FIX-2／QA-01 第 3 項既有硬性要求，
 * UI-IMPL-002／#092＋#094 起隨 Graphite & Amber 改成驗深色優先預設）。
 *
 * 本輪把 `:root` 從「淺色預設、深色媒體查詢覆寫」整個倒過來——`:root`
 * 現在是深色（Foundations 板「深色優先」原文），淺色改成
 * `@media (prefers-color-scheme: light)` 覆寫。這支測試原本硬編碼
 * 「第一個 `:root` 讀成 light、`dark` 媒體查詢讀成 dark」，結構上必須
 * 跟著換——改成明確依媒體查詢字串分區，不再依賴「誰在檔案前面」這個
 * 已經不成立的假設。
 *
 * token 值本身也從 rgba 半透明疊色改成設計系統給的純色 hex（Foundations
 * 板 `--text`／`--text-2`／`--text-3`），因此改用直接比較兩個純色的
 * 對比，不再需要 alpha over-background 的混色運算。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// jsdom 環境下 `import.meta.url` 不是 file: URL，`fileURLToPath` 會炸；
// Vitest 由專案根目錄啟動，直接用相對根目錄的路徑最穩。
const CSS = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");

type RGB = [number, number, number];

/** WCAG relative luminance（sRGB）。 */
function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * 從 `styles.css` 取出某個 token 的純色 hex 值。
 * `scope` = "dark" 讀 `:root`（檔案最上方的深色預設）、
 * "light" 讀 `@media (prefers-color-scheme: light)` 區塊裡那一份。
 */
function readHexToken(name: string, scope: "light" | "dark"): RGB {
  // 精確比對到 `{`：檔案上方的說明文字裡也出現過同一段媒體查詢字串
  // （寫在反引號註解裡），不帶大括號的話會先撞到註解、把整個 `:root`
  // 深色區塊誤判成落在「light」範圍之外。
  const lightAt = CSS.indexOf("@media (prefers-color-scheme: light) {");
  expect(lightAt).toBeGreaterThan(0);
  const region = scope === "dark" ? CSS.slice(0, lightAt) : CSS.slice(lightAt);
  const hit = new RegExp(`${name}:\\s*#([0-9a-fA-F]{6})`).exec(region);
  if (!hit) throw new Error(`在 ${scope} 區塊找不到 token ${name}`);
  const v = hit[1];
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)) as RGB;
}

/** WCAG AA，normal text（<18pt 且非 14pt bold）。 */
const AA_NORMAL = 4.5;

for (const scope of ["dark", "light"] as const) {
  describe(`${scope === "dark" ? "深色（預設）" : "淺色"}模式文字對比`, () => {
    // 這兩個底色是實際會出現在文字後面的：卡片底（panel）與頁面底
    // （bg）。兩個都要過——哪個對比較嚴苛因模式而異，不假設方向。
    const backgrounds: [string, RGB][] = [
      ["--panel（卡片底）", readHexToken("--panel", scope)],
      ["--bg（頁面底）", readHexToken("--bg", scope)],
    ];

    for (const token of ["--text-2", "--text-3"]) {
      for (const [bgName, bg] of backgrounds) {
        it(`${token} 疊在 ${bgName} 上達到 WCAG AA normal text`, () => {
          const fg = readHexToken(token, scope);
          const ratio = contrast(fg, bg);
          expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
        });
      }
    }

    it("三階文字層次仍然存在——text-2 比 text-3 明顯更重，" +
       "不是為了過門檻把兩者壓成同一個顏色", () => {
      const sec = readHexToken("--text-2", scope);
      const ter = readHexToken("--text-3", scope);
      const lSec = luminance(sec);
      const lTer = luminance(ter);

      if (scope === "dark") {
        // 深色模式：文字比背景亮，text-2 應該比 text-3 更亮（更接近
        // 主文字）。
        expect(lSec).toBeGreaterThan(lTer);
      } else {
        // 淺色模式：文字比背景暗，text-2 應該比 text-3 更暗（更接近
        // 主文字）。
        expect(lSec).toBeLessThan(lTer);
      }
      expect(Math.abs(lSec - lTer)).toBeGreaterThan(0.03); // 差得看得出來
    });
  });
}
