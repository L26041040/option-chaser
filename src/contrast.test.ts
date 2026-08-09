/**
 * QA-FIX-2（QA-01）：文字色對比的自動驗收。
 *
 * QA-01 第 3 項的驗收標準是「WCAG AA normal text（4.5:1）」——那是一個
 * 客觀門檻，不該只在修正當下用計算機算一次就算數。這支測試直接讀
 * `styles.css` 裡的 token 值，把對比算出來，任何人日後調淡它都會紅燈。
 *
 * 只驗淺色模式（QA-01 第 3 項的範圍）。深色模式的同名 token 本次刻意
 * 不動（要求是「不因本修正退化」，不是「一併改到 AA」）——它目前
 * tertiary 仍低於 AA，這個已知狀態記在最後一條測試裡，明確標成
 * 「已知、待需求方裁示」，不讓它靜靜消失。
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

/** 半透明前景疊在不透明底色上的實際顏色。 */
function over(fg: RGB, alpha: number, bg: RGB): RGB {
  return [0, 1, 2].map((i) => alpha * fg[i] + (1 - alpha) * bg[i]) as RGB;
}

function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * 從 `styles.css` 取出某個 token 的 `rgba(r, g, b, a)` 值。
 * `scope` = "light" 讀第一個 `:root`（檔案最上方的淺色預設）、
 * "dark" 讀 `@media (prefers-color-scheme: dark)` 區塊裡那一份。
 */
function readRgbaToken(name: string, scope: "light" | "dark"):
    { rgb: RGB; alpha: number } {
  const darkAt = CSS.indexOf("@media (prefers-color-scheme: dark)");
  expect(darkAt).toBeGreaterThan(0);
  const region = scope === "light" ? CSS.slice(0, darkAt) : CSS.slice(darkAt);
  const hit = new RegExp(
    `${name}:\\s*rgba\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*([\\d.]+)\\s*\\)`,
  ).exec(region);
  if (!hit) throw new Error(`在 ${scope} 區塊找不到 token ${name}`);
  return {
    rgb: [Number(hit[1]), Number(hit[2]), Number(hit[3])],
    alpha: Number(hit[4]),
  };
}

function readHexToken(name: string, scope: "light" | "dark"): RGB {
  const darkAt = CSS.indexOf("@media (prefers-color-scheme: dark)");
  const region = scope === "light" ? CSS.slice(0, darkAt) : CSS.slice(darkAt);
  const hit = new RegExp(`${name}:\\s*#([0-9a-fA-F]{6})`).exec(region);
  if (!hit) throw new Error(`在 ${scope} 區塊找不到 token ${name}`);
  const v = hit[1];
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)) as RGB;
}

/** WCAG AA，normal text（<18pt 且非 14pt bold）。 */
const AA_NORMAL = 4.5;

describe("淺色模式文字對比（QA-FIX-2／QA-01 第 3 項）", () => {
  // 這兩個底色是實際會出現在文字後面的：卡片底與頁面底。頁面底
  // （#f2f2f7）比卡片底更暗，是比較嚴苛的那一個，兩個都要過。
  const backgrounds: [string, RGB][] = [
    ["--bg-elevated（卡片底）", readHexToken("--bg-elevated", "light")],
    ["--bg（頁面底）", readHexToken("--bg", "light")],
  ];

  for (const token of ["--label-secondary", "--label-tertiary"]) {
    for (const [bgName, bg] of backgrounds) {
      it(`${token} 疊在 ${bgName} 上達到 WCAG AA normal text`, () => {
        const { rgb, alpha } = readRgbaToken(token, "light");
        const ratio = contrast(over(rgb, alpha, bg), bg);
        expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
      });
    }
  }

  it("三階文字層次仍然存在——secondary 比 tertiary 明顯更重，" +
     "不是為了過門檻把兩者壓成同一個顏色", () => {
    const bg = readHexToken("--bg-elevated", "light");
    const sec = readRgbaToken("--label-secondary", "light");
    const ter = readRgbaToken("--label-tertiary", "light");
    const lSec = luminance(over(sec.rgb, sec.alpha, bg));
    const lTer = luminance(over(ter.rgb, ter.alpha, bg));

    expect(lSec).toBeLessThan(lTer);          // secondary 更深
    expect(lTer - lSec).toBeGreaterThan(0.03); // 而且差得看得出來
  });
});

describe("深色模式：本次不修正，但要證明沒有退化", () => {
  it("--label-secondary 在深色卡片底上仍達 AA（原本就過，維持）", () => {
    const bg = readHexToken("--bg-elevated", "dark");
    const { rgb, alpha } = readRgbaToken("--label-secondary", "dark");
    expect(contrast(over(rgb, alpha, bg), bg)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it("⚠ 已知未解：--label-tertiary 在深色模式仍低於 AA。" +
     "QA-01 第 3 項範圍是淺色模式，深色只要求不退化——這條測試把" +
     "現狀釘住，日後要修時會因為『比預期更好』而紅燈，屆時一併更新", () => {
    const bg = readHexToken("--bg-elevated", "dark");
    const { rgb, alpha } = readRgbaToken("--label-tertiary", "dark");
    const ratio = contrast(over(rgb, alpha, bg), bg);
    // 不退化：至少不比修正前（2.48:1）更差
    expect(ratio).toBeGreaterThanOrEqual(2.4);
    // 現狀誠實記錄：還沒到 AA
    expect(ratio).toBeLessThan(AA_NORMAL);
  });
});
