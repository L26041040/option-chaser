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

describe("SW-01→SW-09：Seed Warm token 值（Direction A artifact，#330）", () => {
  // SW-09（#339）contract 階段：`:root` 已經把「新名字 alias 回舊名字」
  // 的雙層結構收成單層——這裡直接檢查新名稱本身宣告的色值，不再檢查
  // 一個指向另一個的 alias 關係（舊名稱已經整段從 `:root` 移除，見下面
  // 「SW-09：contract 階段」那組測試）。
  const expected: Record<string, string> = {
    "--paper": "#fbf7f0",
    "--card": "#ffffff",
    "--card-hover": "#fdfbf7",
    "--soft": "#f1e9dc",
    "--line": "#ebe3d6",
    "--line-2": "#e0d6c6",
    "--ink": "#231f1b",
    "--ink-2": "#5c554e",
    "--mute": "#766e66",
    "--acc": "#c9501f",
    "--acc-hover": "#a8420f",
    "--acc-text": "#be4c1d",
    "--on-acc": "#ffffff",
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
});

describe("SW-09（#339）：contract 階段——OG 時代舊 token 名整段移除", () => {
  const OLD_NAMES = [
    "--bg", "--panel", "--panel-2", "--panel-3", "--panel-4",
    "--text", "--text-2", "--text-3",
    "--accent", "--accent-hover", "--accent-text", "--on-accent", "--accent-soft",
    "--card-shadow", "--bg-elevated", "--separator",
    "--label", "--label-secondary", "--label-tertiary",
    "--tint", "--green", "--red", "--orange", "--yellow",
  ];

  for (const name of OLD_NAMES) {
    it(`styles.css 不再宣告 ${name}`, () => {
      expect(CSS).not.toMatch(new RegExp(`^\\s*${name}:`, "m"));
    });

    it(`styles.css 不再有任何 var(${name}) 消費端`, () => {
      expect(CSS).not.toContain(`var(${name})`);
    });
  }
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
