/**
 * WCAG AA 文字對比的自動驗收（QA-FIX-2／QA-01 第 3 項既有硬性要求）。
 *
 * SW-01（#331，Seed Warm）：`:root` 從「深色優先＋
 * `prefers-color-scheme: light` 覆寫」收斂成單一淺色 `:root`——
 * 本輪只做淺色（SEED-WARM-SPEC-001／#330 Out of Scope），不再需要
 * 依媒體查詢字串分區讀兩份 token，直接讀同一個 `:root`。
 *
 * 同時把 Direction A 的「填色 token」（`--accent`／`--up`／`--warn`）
 * 與「文字安全 token」（`--accent-text`／`--up-text`／`--warn-text`）
 * 分開驗證——填色 token 在小字上量不到 4.5:1 是已知、有意的取捨（見
 * `styles.css` 檔頭說明），只對真的拿來當小字文字色用的那一組
 * token 套用 AA normal text 門檻。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

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

function readHexToken(name: string): RGB {
  const hit = new RegExp(`${name}:\\s*#([0-9a-fA-F]{6})`).exec(CSS);
  if (!hit) throw new Error(`styles.css 找不到 token ${name}`);
  const v = hit[1];
  return [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16)) as RGB;
}

/** WCAG AA，normal text（<18pt 且非 14pt bold）。 */
const AA_NORMAL = 4.5;

describe("Seed Warm 淺色模式文字對比", () => {
  const backgrounds: [string, RGB][] = [
    ["--panel（卡片底）", readHexToken("--panel")],
    ["--bg（頁面底）", readHexToken("--bg")],
  ];

  for (const token of ["--text-2", "--text-3"]) {
    for (const [bgName, bg] of backgrounds) {
      it(`${token} 疊在 ${bgName} 上達到 WCAG AA normal text`, () => {
        const fg = readHexToken(token);
        const ratio = contrast(fg, bg);
        expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
      });
    }
  }

  // 「文字安全」變體——這三個在小字（badge 文字、inline 百分比）上
  // 使用，必須達 AA normal text；對應的填色 token（--accent／--up／
  // --warn）本身不在此列，那組是給按鈕背景、大報酬數字、sparkline
  // 這類「填色或大字」場景，只需要 3:1（WCAG large text），不是本測
  // 試的斷言範圍。
  for (const token of ["--accent-text", "--up-text", "--warn-text", "--down"]) {
    for (const [bgName, bg] of backgrounds) {
      it(`${token}（文字安全變體）疊在 ${bgName} 上達到 WCAG AA normal text`, () => {
        const fg = readHexToken(token);
        const ratio = contrast(fg, bg);
        expect(ratio).toBeGreaterThanOrEqual(AA_NORMAL);
      });
    }
  }

  it("三階文字層次仍然存在——text-2 比 text-3 明顯更重，不是為了過門檻把兩者壓成同一個顏色", () => {
    const sec = readHexToken("--text-2");
    const ter = readHexToken("--text-3");
    const lSec = luminance(sec);
    const lTer = luminance(ter);

    // 淺色：文字比背景暗，text-2 應該比 text-3 更暗（更接近主文字）。
    expect(lSec).toBeLessThan(lTer);
    expect(Math.abs(lSec - lTer)).toBeGreaterThan(0.03); // 差得看得出來
  });
});
