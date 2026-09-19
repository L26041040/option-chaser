/**
 * OG-01（#317）Foundations 驗收——token／字體／primitives 的靜態
 * 驗證。手法沿用既有 `contrast.test.ts`：直接讀 `styles.css` 原始碼
 * 文字，不依賴 jsdom 真的套用 CSS（jsdom 不下載 web font、也不會真的
 * 計算 computed style 的 CSS 變數解析鏈，這類斷言只有讀原始碼才可靠）。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");

const LIGHT_AT = CSS.indexOf("@media (prefers-color-scheme: light) {");

function readHexToken(name: string, scope: "light" | "dark"): string {
  const region = scope === "dark" ? CSS.slice(0, LIGHT_AT) : CSS.slice(LIGHT_AT);
  const hit = new RegExp(`${name}:\\s*#([0-9a-fA-F]{6})`, "i").exec(region);
  if (!hit) throw new Error(`在 ${scope} 區塊找不到 token ${name}`);
  return `#${hit[1].toLowerCase()}`;
}

describe("OG-01：Obsidian Gold token 值", () => {
  it("開頭是 :root（深色為預設，不是 dark 媒體查詢）", () => {
    expect(LIGHT_AT).toBeGreaterThan(0);
    expect(CSS.indexOf(":root {")).toBeLessThan(LIGHT_AT);
  });

  const darkExpected: Record<string, string> = {
    "--bg": "#0b0e11",
    "--panel": "#181a20",
    "--panel-2": "#1e2329",
    "--panel-3": "#2b3139",
    "--panel-4": "#363d47",
    "--line": "#252b33",
    "--line-2": "#2f3640",
    "--text": "#eaecef",
    "--text-2": "#b7bdc6",
    "--text-3": "#848e9c",
    "--text-4": "#5e6673",
    "--accent": "#f2c12e",
    "--accent-hover": "#ffd75a",
    "--on-accent": "#181a20",
    "--up": "#2ebd85",
    "--down": "#f6465d",
    "--info": "#5ac8fa",
    "--warn": "#f0b90b",
  };
  for (const [name, hex] of Object.entries(darkExpected)) {
    it(`深色 ${name} = ${hex}`, () => {
      expect(readHexToken(name, "dark")).toBe(hex);
    });
  }

  const lightExpected: Record<string, string> = {
    "--bg": "#f5f5f5",
    "--panel": "#ffffff",
    "--panel-3": "#f1f2f4",
    "--panel-4": "#e6e8ea",
    "--line": "#e9ebee",
    "--line-2": "#dcdfe3",
    "--text": "#1e2329",
    "--text-2": "#474d57",
    "--text-4": "#9aa3ae",
    "--accent": "#e3b11e",
    "--accent-hover": "#f2c12e",
    "--on-accent": "#1e2329",
    "--up": "#0fa37f",
    "--down": "#e0374f",
    "--info": "#1e88e5",
    "--warn": "#f0b90b",
  };
  for (const [name, hex] of Object.entries(lightExpected)) {
    it(`淺色 ${name} = ${hex}`, () => {
      expect(readHexToken(name, "light")).toBe(hex);
    });
  }

  it("淺色 --text-3 為了 AA 從 artifact 原文加深，但仍是同一個色相家族", () => {
    // 已知偏離：artifact 原文 #707A8A 不過 AA（見 styles.css 檔頭說明），
    // 這裡鎖住實際採用值，不是隨便誰改都不會被發現。
    expect(readHexToken("--text-3", "light")).toBe("#636c7a");
  });

  it("既有的 Crossover 分界線改用新的資訊色（純色彩重新分配）", () => {
    expect(CSS).toMatch(/--crossover:\s*var\(--info\)/);
  });
});

describe("OG-01：字體堆疊", () => {
  it("--font 以 Geist 為拉丁/數字字體、Noto Sans TC 為中文字體", () => {
    const m = /--font:\s*"([^"]+)",\s*"([^"]+)"/.exec(CSS);
    expect(m).not.toBeNull();
    expect(m![1]).toBe("Geist");
    expect(m![2]).toBe("Noto Sans TC");
  });

  it("--mono 以 Geist Mono 為主", () => {
    const m = /--mono:\s*"([^"]+)"/.exec(CSS);
    expect(m).not.toBeNull();
    expect(m![1]).toBe("Geist Mono");
  });

  it("index.html 用 Google Fonts 載入 Geist／Geist Mono／Noto Sans TC 三個 web font", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf-8");
    expect(html).toMatch(/fonts\.googleapis\.com\/css2\?family=Geist:/);
    expect(html).toMatch(/family=Geist\+Mono:/);
    expect(html).toMatch(/family=Noto\+Sans\+TC:/);
    // IBM Plex 系列（上一輪 Graphite & Amber 的字體）不該再被載入——
    // 檔頭史料性質的一句提及（"取代上一輪的 IBM Plex Sans"）允許存在，
    // 這裡精確檢查的是實際會被瀏覽器拿去載入／套用的兩處：Google
    // Fonts 連結、`--font`／`--mono` 兩個 token 的值本身。
    expect(html).not.toMatch(/IBM\+Plex/);
    expect(/--font:\s*"[^"]*"/.exec(CSS)?.[0]).not.toMatch(/IBM Plex/);
    expect(/--mono:\s*"[^"]*"/.exec(CSS)?.[0]).not.toMatch(/IBM Plex/);
  });

  it("既有 tabular-nums 規則沒有被本輪動到（財務數字仍是等寬數字）", () => {
    // 基準值＝本輪施工前實際數過的既有宣告數（非猜測的整數），鎖住
    // 「至少沒有變少」，不要求剛好等於某個數字。
    const count = (CSS.match(/font-variant-numeric:\s*tabular-nums/g) ?? []).length;
    expect(count).toBeGreaterThanOrEqual(14);
  });
});

describe("OG-01：共用 primitives 存在且套用預期 token", () => {
  const mustExist = [
    ".btn {",
    ".btn.secondary {",
    ".btn.danger {",
    ".iconbtn {",
    ".panel {",
    ".panel-h {",
    ".tabs {",
    ".seg {",
    ".tbl {",
    ".sym {",
    ".legs {",
    ".inp {",
    ".mnav {",
    ".hm td {",
    ".bar {",
    ".dot {",
  ];
  for (const selector of mustExist) {
    it(`${selector.replace(" {", "")} 存在`, () => {
      expect(CSS).toContain(selector);
    });
  }

  it(".btn 預設（primary）套用 --accent／--on-accent", () => {
    const rule = /\.btn\s*\{([^}]*)\}/.exec(CSS);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/background:\s*var\(--accent\)/);
    expect(rule![1]).toMatch(/color:\s*var\(--on-accent\)/);
  });

  it(".btn.secondary 套用髮絲線框（--line-2），不是實色背景", () => {
    const rule = /\.btn\.secondary\s*\{([^}]*)\}/.exec(CSS);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/border-color:\s*var\(--line-2\)/);
    expect(rule![1]).toMatch(/background:\s*transparent/);
  });

  it(".btn.danger 套用 --down，不是實色填滿", () => {
    const rule = /\.btn\.danger\s*\{([^}]*)\}/.exec(CSS);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/color:\s*var\(--down\)/);
    expect(rule![1]).toMatch(/background:\s*transparent/);
  });

  it(".panel 用髮絲線分隔，沒有 box-shadow", () => {
    const rule = /\.panel\s*\{([^}]*)\}/.exec(CSS);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/border:\s*1px solid var\(--line\)/);
    expect(rule![1]).not.toMatch(/box-shadow/);
  });

  it(".tbl td 列高落在 40–56px 範圍內（Foundations 板規格）", () => {
    const rule = /\.tbl td\s*\{([^}]*)\}/.exec(CSS);
    expect(rule).not.toBeNull();
    const height = Number(/height:\s*(\d+)px/.exec(rule![1])?.[1]);
    expect(height).toBeGreaterThanOrEqual(40);
    expect(height).toBeLessThanOrEqual(56);
  });

  it(".tbl .r 數字欄右對齊", () => {
    expect(CSS).toMatch(/\.tbl \.r\s*\{\s*text-align:\s*right;\s*\}/);
  });
});

describe("OG-01：既有 primitives 已經滿足 Foundations 板的等價角色，未被重複定義", () => {
  // 這幾個既有 class 承接了 artifact 的「角色 chip／tag／chip／stat／
  // 頂欄 nav／手機 bottom tab／kv 列表」——確認它們還在、且沒有被本票
  // 意外新增一份撞名但語意不同的版本。
  it(".role／.tag／.chip／.stat／.topbar／.mtabs／.row 都還在", () => {
    for (const selector of [
      ".role {",
      ".tag {",
      ".chip {",
      ".stat {",
      ".topbar {",
      ".mtabs {",
      ".row {",
    ]) {
      expect(CSS).toContain(selector);
    }
  });
});

describe("OG-01：金色只用於可動作元素／冠軍標記，紅綠只用於數值方向（靜態掃描）", () => {
  /** 把一段扁平（不含巢狀 `{}`）CSS 拆成 [{selector, body}]，先去掉
   *  區塊註解（否則多行中文註解會被 `[^{}]+` 一起吃進「selector」），
   *  並把 selector 內的換行／多重空白收斂成單一空白，讓多選擇器
   *  （逗號分行）與白名單字串能對齊比對。 */
  function rules(css: string): { selector: string; body: string }[] {
    const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
    const out: { selector: string; body: string }[] = [];
    const re = /([^{}]+)\{([^{}]*)\}/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(stripped))) {
      const selector = m[1].replace(/\s+/g, " ").trim();
      if (selector) out.push({ selector, body: m[2] });
    }
    return out;
  }

  // 本輪新增的兩段 CSS：`.tag` 色彩修飾（緊接在既有 `.tag.suspect` 之後）
  // ＋檔尾的 OG-01 primitives 整段。既有三千多行沿用舊系統時期已經
  // review 過的既有色彩決定，本輪只換 token 值、不重新審查，範圍不含
  // 在這次靜態掃描裡。先把整份 CSS 的區塊註解去掉，再用「選擇器本身」
  // （而非藏在註解裡的說明文字）當邊界——邊界字串才不會因為註解被
  // 去掉而跟著消失、也不會把註解內容誤含進第一條規則的 selector。
  const STRIPPED_CSS = CSS.replace(/\/\*[\s\S]*?\*\//g, "");
  const TAG_MODIFIERS_START = STRIPPED_CSS.indexOf(".tag.up {");
  const TAG_MODIFIERS_END = STRIPPED_CSS.indexOf(".card .notice {", TAG_MODIFIERS_START);
  const OG01_SECTION_START = STRIPPED_CSS.indexOf(".btn {", TAG_MODIFIERS_END);

  it("兩段掃描範圍都真的找得到（測試本身沒有失去目標）", () => {
    expect(TAG_MODIFIERS_START).toBeGreaterThan(0);
    expect(TAG_MODIFIERS_END).toBeGreaterThan(TAG_MODIFIERS_START);
    expect(OG01_SECTION_START).toBeGreaterThan(TAG_MODIFIERS_END);
  });

  const scanned = [
    ...rules(STRIPPED_CSS.slice(TAG_MODIFIERS_START, TAG_MODIFIERS_END)),
    ...rules(STRIPPED_CSS.slice(OG01_SECTION_START)),
  ];

  const ACCENT_TOKENS = /var\(--accent(-hover|-soft|-text)?\)/;
  // 可動作元素／冠軍標記白名單：主按鈕、分頁選取指示條、輸入框
  // focus 狀態、inline 比例條的填色（相對冠軍的量級標示）、
  // 「冠軍／金牌」語意的 tag 修飾。
  const ACCENT_ALLOWED_SELECTORS = [
    ".btn",
    ".tabs a.on::after",
    ".inp.focus, .inp:focus-within",
    ".bar i",
    ".tag.gold",
  ];

  const DIRECTION_TOKENS = /var\(--(up|down)(-soft)?\)/;
  // 數值方向（含同一語意軸的買／賣腿方向、健康／異常狀態燈、危險
  // 操作按鈕——見上方 `.btn.danger` 定義處的說明：交易平台裡「危險
  // 操作」與「賣出／下跌」慣例上共用同一個紅色，不是誤用）白名單。
  const DIRECTION_ALLOWED_SELECTORS = [
    ".tag.up",
    ".tag.down",
    ".dot.g",
    ".dot.r",
    ".legs .b",
    ".legs .s",
    ".btn.danger",
  ];

  it("本輪新增 CSS 裡，套用金色 token 的規則都在白名單內", () => {
    const offenders = scanned.filter(
      (r) => ACCENT_TOKENS.test(r.body) && !ACCENT_ALLOWED_SELECTORS.includes(r.selector),
    );
    expect(offenders.map((r) => r.selector)).toEqual([]);
  });

  it("本輪新增 CSS 裡，套用紅／綠方向 token 的規則都在白名單內", () => {
    const offenders = scanned.filter(
      (r) => DIRECTION_TOKENS.test(r.body) && !DIRECTION_ALLOWED_SELECTORS.includes(r.selector),
    );
    expect(offenders.map((r) => r.selector)).toEqual([]);
  });

  it("白名單本身沒有過期條目（每一條都真的在掃描範圍內出現過）", () => {
    const selectors = new Set(scanned.map((r) => r.selector));
    for (const s of [...ACCENT_ALLOWED_SELECTORS, ...DIRECTION_ALLOWED_SELECTORS]) {
      expect(selectors.has(s)).toBe(true);
    }
  });
});
