/**
 * SW-01（#331）Seed Warm Foundations 驗收——手法沿用既有
 * `obsidianGold.test.ts`：直接讀 `styles.css` 原始碼文字，不依賴
 * jsdom 真的套用 CSS（jsdom 不下載 web font、也不會真的計算 computed
 * style 的 CSS 變數解析鏈，這類斷言只有讀原始碼才可靠）。
 *
 * 淺色唯一是本輪最關鍵的結構性斷言：整份 `styles.css` 不應該再出現
 * `prefers-color-scheme` 字樣（SEED-WARM-SPEC-001／#330 Out of
 * Scope：dark mode 另開後續 spec）。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");

function readHexToken(name: string): string {
  const hit = new RegExp(`${name}:\\s*#([0-9a-fA-F]{6})`).exec(CSS);
  if (!hit) throw new Error(`styles.css 找不到 token ${name}`);
  return `#${hit[1].toLowerCase()}`;
}

describe("SW-01：Seed Warm 淺色唯一", () => {
  it("styles.css 不含任何 @media (prefers-color-scheme …) 分支", () => {
    // 只驗證真的 CSS at-rule，不是隨口出現在註解裡的字——本檔案自己
    // 的檔頭說明就會提到這個詞（記錄「已經移除」這件事）。
    expect(CSS).not.toMatch(/@media\s*\(\s*prefers-color-scheme/);
  });

  it(":root 宣告 color-scheme: light", () => {
    expect(CSS).toMatch(/:root\s*{[^}]*color-scheme:\s*light/);
  });
});

describe("SW-01：Seed Warm token 值（Direction A artifact，#330）", () => {
  const expected: Record<string, string> = {
    "--bg": "#fbf7f0",
    "--panel": "#ffffff",
    "--panel-2": "#fdfbf7",
    "--panel-3": "#f1e9dc",
    "--panel-4": "#e0d6c6",
    "--line": "#ebe3d6",
    "--line-2": "#e0d6c6",
    "--text": "#231f1b",
    "--text-2": "#5c554e",
    "--text-3": "#766e66",
    "--accent": "#c9501f",
    "--accent-hover": "#a8420f",
    "--accent-text": "#be4c1d",
    "--on-accent": "#ffffff",
    "--up": "#1e8a5a",
    "--up-text": "#1b7c51",
    "--down": "#c93b4a",
    "--warn": "#b7791f",
    "--warn-text": "#9b661a",
  };

  for (const [name, hex] of Object.entries(expected)) {
    it(`${name} = ${hex}`, () => {
      expect(readHexToken(name)).toBe(hex);
    });
  }

  it("Seed Warm 詞彙別名（--paper／--card／--ink／--mute／--acc）都指回同一組 var()，不是第二套顏色", () => {
    for (const [alias, target] of [
      ["--paper", "var(--bg)"],
      ["--card", "var(--panel)"],
      ["--ink", "var(--text)"],
      ["--mute", "var(--text-3)"],
      ["--acc", "var(--accent)"],
    ]) {
      const hit = new RegExp(`${alias}:\\s*${target.replace(/[()]/g, "\\$&")}`).exec(CSS);
      expect(hit, `${alias} 應該是 ${target} 的別名`).not.toBeNull();
    }
  });
});

describe("SW-01：字體換血（Plus Jakarta Sans + Noto Sans TC）", () => {
  it("--font 以 Plus Jakarta Sans 開頭，不含 Geist", () => {
    const hit = /--font:\s*([^;]+);/.exec(CSS);
    expect(hit).not.toBeNull();
    const value = hit![1];
    expect(value).toContain("Plus Jakarta Sans");
    expect(value).toContain("Noto Sans TC");
    expect(value).not.toContain("Geist");
  });

  it("--mono 不再引用 Geist Mono", () => {
    const hit = /--mono:\s*([^;]+);/.exec(CSS);
    expect(hit).not.toBeNull();
    expect(hit![1]).not.toContain("Geist");
  });

  it("index.html 載入 Plus Jakarta Sans 與 Noto Sans TC，不再載入 Geist", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf-8");
    expect(html).toContain("Plus+Jakarta+Sans");
    expect(html).toContain("Noto+Sans+TC");
    expect(html).not.toContain("family=Geist");
  });
});
