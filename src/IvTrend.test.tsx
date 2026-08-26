/**
 * Historical IV Trend——逐腿 exact-contract 卡片（HIVT-05／#156，
 * spec #151 §6）。
 *
 * 跟 `./IvHistory` 分屬兩個檔案，邊界跟著元件邊界走：這裡只測
 * `IvTrend` 元件本身（同步渲染，不必像 `IvHistory.test.tsx` 那樣繞過
 * 閘門／fetch 生命週期）——買賣腿各自獨立、資訊順序、統計量各自
 * graceful degradation、固定文案、facts-only 守門。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ContractIdentity, IvHistoryLegs, IvTrendStatPoint,
             LegHistoricalIv } from "./api";
import { PAD_LEFT, PAD_RIGHT } from "./IvHistory";
import IvTrend, { LEG_CHART_HEIGHT_DESKTOP, LEG_CHART_HEIGHT_MOBILE,
                 zscoreCaption } from "./IvTrend";
import { fakeMediaQueryList } from "./test-setup";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** 見 `IvHistory.test.tsx` 同名工具的說明：jsdom 沒有真正的 layout、
 *  也沒有原生 `PointerEvent` 建構子，這裡假裝渲染寬度跟 viewBox 寬度
 *  一樣（1:1），並用 `MouseEvent` 但指定 pointer 事件名稱來夾帶
 *  `clientX`（`fireEvent.pointerMove(el, {clientX})` 這種便利寫法在
 *  這個 jsdom 版本會悄悄弄丟 `clientX`）。 */
function stubChartWidth(svg: Element, width = 300) {
  vi.spyOn(svg, "getBoundingClientRect").mockReturnValue({
    left: 0, width, top: 0, height: 0, right: width, bottom: 0, x: 0, y: 0,
    toJSON() { return {}; },
  } as DOMRect);
}

function clientXForPoint(index: number, count: number, width = 300) {
  const plotWidth = width - PAD_LEFT - PAD_RIGHT;
  const frac = count <= 1 ? 0.5 : index / (count - 1);
  return PAD_LEFT + frac * plotWidth;
}

function firePointerEvent(svg: Element, type: string, clientX: number) {
  fireEvent(svg, new MouseEvent(type, { clientX, bubbles: true }));
}

function firePointerMove(svg: Element, clientX: number) {
  firePointerEvent(svg, "pointermove", clientX);
}

function contract(overrides: Partial<ContractIdentity> = {}): ContractIdentity {
  return { underlying: "XYZ", expiration: "2026-09-18", strike: 118,
          option_type: "call", contract_symbol: "XYZ260918C00118000",
          ...overrides };
}

function ivPoints(n: number, f: (i: number) => number | null) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    iv: f(i),
    low_confidence: false,
  }));
}

function statPoints(n: number, f: (i: number) => number | null): IvTrendStatPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    date: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    value: f(i),
  }));
}

function legHistoricalIv(overrides: Partial<LegHistoricalIv> = {}): LegHistoricalIv {
  return {
    contract: contract(),
    points: ivPoints(60, (i) => 0.20 + (i % 20) * 0.001),
    moving_average: statPoints(60, () => 0.21),
    bollinger_upper: statPoints(60, () => 0.25),
    bollinger_lower: statPoints(60, () => 0.17),
    current_percentile: 0.5,
    current_zscore: 0.3,
    delta_4w: 0.01,
    observation_count: 60,
    history_span_days: 365,
    lookback_days_config: 30,
    status: "ok",
    note: null,
    ...overrides,
  };
}

describe("單腳（Long Call／Put）：正好一張卡", () => {
  it("只渲染一張卡片，沒有買／賣標籤", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.querySelectorAll(".iv-trend-card")).toHaveLength(1);
    expect(screen.queryByText("買腿")).not.toBeInTheDocument();
    expect(screen.queryByText("賣腿")).not.toBeInTheDocument();
  });
});

describe("Vertical Spread：正好兩張卡，買賣腿各自獨立正確", () => {
  it("渲染買腿與賣腿兩張卡，各自標籤正確", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv({ contract: contract({ strike: 118 }) }),
      sell: legHistoricalIv({ contract: contract({ strike: 125 }) }),
    };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.querySelectorAll(".iv-trend-card")).toHaveLength(2);
    expect(screen.getByText("買腿")).toBeInTheDocument();
    expect(screen.getByText("賣腿")).toBeInTheDocument();
  });

  it("兩腿的現值各自獨立，不是合成或取平均出來的數字——這是 spec AC 明文\
     要求的「絕不互相污染」在前端的呈現", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv({ points: ivPoints(5, () => 0.20) }),
      sell: legHistoricalIv({ points: ivPoints(5, () => 0.35) }),
    };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getByText("35.0%")).toBeInTheDocument();
    // 兩者的平均值（27.5%）不該出現在畫面上——證明沒有被合成一條序列。
    expect(screen.queryByText("27.5%")).not.toBeInTheDocument();
  });
});

describe("資訊順序（桌面）：現值 → 走勢圖 → percentile → Δ4w → 涵蓋時間（SIG-02／#173 瘦身後，" +
        "手機再瘦身一輪不影響桌面這套順序）", () => {
  it("依瘦身後順序渲染，z-score 不在主要區塊裡", () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    const card = container.querySelector(".iv-trend-card")!;
    // `.className` 在 SVG 元素上是 SVGAnimatedString，不是字串——一律用
    // `getAttribute("class")` 取得跨 HTML／SVG 一致的類別字串。
    const classes = Array.from(card.children)
      .map((el) => el.getAttribute("class"));
    // PC-01（#199）新增一句常駐的百分位說明，緊接在 percentileCaption
    // 之後——多一個 "caption"，其餘既有順序不變。
    expect(classes).toEqual([
      "iv-value-primary", "iv-trend-chart",
      "caption", "caption", "caption", "caption",
    ]);
  });

  it("Spread 模式：買腿卡片標籤在現值之前", () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv(), sell: legHistoricalIv(),
    };
    const { container } = render(<IvTrend legs={legs} />);
    const buyCard = container.querySelectorAll(".iv-trend-card")[0];
    const classes = Array.from(buyCard.children)
      .map((el) => el.getAttribute("class"));
    expect(classes[0]).toContain("iv-trend-card-label");
    expect(classes[1]).toBe("iv-value-primary");
  });
});

describe("資訊順序（手機再瘦身一輪，需求方 2026-08-22 反饋）：標籤＋現值合併一行 → " +
        "百分位＋Δ4w 合併一行 → 走勢圖 → 涵蓋時間，desktop 以外的斷點都走這套", () => {
  it("依手機瘦身後順序渲染（預設 matchMedia 假體＝手機）", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    const card = container.querySelector(".iv-trend-card")!;
    const classes = Array.from(card.children)
      .map((el) => el.getAttribute("class"));
    // PC-01（#199）新增一句常駐的百分位說明，緊接在合併後的
    // 百分位＋Δ4w 那一行之後、走勢圖之前。
    expect(classes).toEqual([
      "iv-compact-head", "caption iv-compact-stats", "caption",
      "iv-trend-chart", "caption",
    ]);
  });

  it("合併行內同時看得到百分位與 Δ4w 兩個事實，是同一個文字節點而不是分開的兩段", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      current_percentile: 0.7, delta_4w: 0.02,
    }) };
    render(<IvTrend legs={legs} />);
    const stats = screen.getByText(/第 70 百分位/);
    expect(stats.textContent).toMatch(/4週 \+2\.0 pts/);
  });

  it("Spread 模式：買腿卡片標籤與現值合併在同一個 .iv-compact-head", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv(), sell: legHistoricalIv(),
    };
    const { container } = render(<IvTrend legs={legs} />);
    const buyCard = container.querySelectorAll(".iv-trend-card")[0];
    const head = buyCard.querySelector(".iv-compact-head")!;
    expect(head).toBeInTheDocument();
    expect(head.textContent).toContain("買腿");
    expect(head.querySelector(".iv-value-primary")).toBeInTheDocument();
  });
});

describe("百分位說明文字（PC-01／#199，常駐可見，不必展開才看得到）", () => {
  it("手機（預設 matchMedia 假體＝手機）買賣腿卡片都看得到說明", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv(), sell: legHistoricalIv(),
    };
    render(<IvTrend legs={legs} />);
    expect(screen.getAllByText(/百分位：目前 IV 高於近一年內/).length).toBe(2);
  });

  it("桌面斷點下同樣看得到說明，緊接在百分位數字之後", () => {
    vi.stubGlobal("matchMedia", (q: string) => fakeMediaQueryList(true, q));
    const legs: IvHistoryLegs = { buy: legHistoricalIv({ current_percentile: 0.7 }) };
    const { container } = render(<IvTrend legs={legs} />);
    const card = container.querySelector(".iv-trend-card")!;
    const captions = Array.from(card.querySelectorAll(".caption"))
      .map((el) => el.textContent);
    const percentileIdx = captions.findIndex((t) => t?.includes("第 70 百分位"));
    expect(percentileIdx).toBeGreaterThanOrEqual(0);
    expect(captions[percentileIdx + 1]).toMatch(/百分位：目前 IV 高於近一年內/);
  });
});

describe("統計量各自 graceful degradation（HIVT-03／#154 的前端呈現）", () => {
  it("current_percentile 為 null 時顯示沒有歷史資料，不隱藏整張卡", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({ current_percentile: null }) };
    const { container } = render(<IvTrend legs={legs} />);
    expect(screen.getByText(/沒有歷史資料/)).toBeInTheDocument();
    expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument();
  });

  it("z-score 已搬進 Advanced（見 IvHistory.test.tsx），不影響 percentile／Δ4w",
     () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      current_zscore: null, current_percentile: 0.7, delta_4w: 0.02,
    }) };
    render(<IvTrend legs={legs} />);
    expect(screen.queryByText(/觀測數不足/)).not.toBeInTheDocument();
    expect(screen.getByText(/第 70 百分位/)).toBeInTheDocument();
    expect(screen.getByText(/4週 \+2\.0 pts/)).toBeInTheDocument();
  });

  it("delta_4w 為 null 時顯示「4週 —」，不是捏造的數字", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({ delta_4w: null }) };
    render(<IvTrend legs={legs} />);
    // 手機瘦身後跟百分位合併同一行，用 regex 比對子字串。
    expect(screen.getByText(/4週 —/)).toBeInTheDocument();
  });

  it("moving average／Bollinger 帶整段都不可用時，圖仍然渲染（raw 線照常）",
     () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      moving_average: statPoints(60, () => null),
      bollinger_upper: statPoints(60, () => null),
      bollinger_lower: statPoints(60, () => null),
    }) };
    const { container } = render(<IvTrend legs={legs} />);
    const chart = container.querySelector(".iv-trend-chart");
    expect(chart).toBeInTheDocument();
    expect(container.querySelectorAll(".iv-trend-ma-line")).toHaveLength(0);
    expect(container.querySelectorAll(".iv-trend-band")).toHaveLength(0);
    // raw 線本身（折線）照常畫出來——整張圖是單一 scrubber 介面之後
    // （需求方 2026-08-22 反饋），互動熱區不再是逐點圓點，這裡改成
    // 確認主線的 polyline 確實存在。
    expect(chart!.querySelector("polyline")).toBeInTheDocument();
  });

  it("moving average／Bollinger 帶有值時，圖上畫出對應的線段與區域", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.querySelectorAll(".iv-trend-ma-line").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".iv-trend-band").length).toBeGreaterThan(0);
  });
});

describe("SIG-02（#173）：z-score／Bollinger 數值不以文字形式出現在主要區塊", () => {
  it("z-score 文字（無論值是否為 null）都不在卡片主要區塊裡", () => {
    const okLegs: IvHistoryLegs = { buy: legHistoricalIv({ current_zscore: 0.42 }) };
    const { container: okContainer } = render(<IvTrend legs={okLegs} />);
    expect(okContainer.textContent).not.toMatch(/Z-score/);

    const nullLegs: IvHistoryLegs = { buy: legHistoricalIv({ current_zscore: null }) };
    const { container: nullContainer } = render(<IvTrend legs={nullLegs} />);
    expect(nullContainer.textContent).not.toMatch(/Z-score|觀測數不足/);
  });

  it("Bollinger 上下界數值不以任何文字形式出現，只有走勢圖上的視覺帶狀區域", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      bollinger_upper: statPoints(60, () => 0.999),
      bollinger_lower: statPoints(60, () => 0.111),
    }) };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.textContent).not.toMatch(/99\.9%|11\.1%/);
    expect(container.querySelectorAll(".iv-trend-band").length).toBeGreaterThan(0);
  });
});

describe("zscoreCaption（純函式，SIG-02／#173 起 export 給 Advanced 使用）", () => {
  it("有值時格式化成帶正負號的 Z-score", () => {
    expect(zscoreCaption(legHistoricalIv({ current_zscore: 0.42 })))
      .toBe("Z-score +0.42");
    expect(zscoreCaption(legHistoricalIv({ current_zscore: -1.1 })))
      .toBe("Z-score -1.10");
  });

  it("為 null 時說明觀測數不足", () => {
    expect(zscoreCaption(legHistoricalIv({ current_zscore: null })))
      .toBe("Z-score：觀測數不足");
  });
});

describe("涵蓋時間與觀測筆數（story #5／#6：掛牌不滿一年就顯示實際長度）", () => {
  it("顯示觀測筆數", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({ observation_count: 42 }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/42 個觀測/)).toBeInTheDocument();
  });

  it("掛牌不滿一年時顯示實際涵蓋的月數，不是永遠講「近 1 年」", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      history_span_days: 90, observation_count: 20,
    }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/近 3 個月・20 個觀測/)).toBeInTheDocument();
  });

  it("掛牌不滿一個月時顯示週數", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      history_span_days: 14, observation_count: 8,
    }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/近 2 週・8 個觀測/)).toBeInTheDocument();
  });

  // HIVT-07（#158）E2E 撈出的既有 bug 回歸鎖：15–29 天這段原本會被
  // `Math.round(days / 30)` 誤湊成「近 1 個月」（21/30=0.7 四捨五入成
  // 1），不是掛牌 3 週的合約使用者看到的真實長度。
  it("掛牌約 3 週（21 天）時顯示週數，不會被誤湊成「近 1 個月」", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      history_span_days: 21, observation_count: 12,
    }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/近 3 週・12 個觀測/)).toBeInTheDocument();
    expect(screen.queryByText(/近 1 個月/)).not.toBeInTheDocument();
  });

  // 同一個 bug 的另一面：固定 300 天門檻會把「11 個月」（約 330 天，
  // 仍在 `IV_TREND_MAX_HISTORY_DAYS=365` 之內）錯報成「近 1 年」。
  it("掛牌約 11 個月（330 天）時顯示月數，不會被誤湊成「近 1 年」", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      history_span_days: 330, observation_count: 48,
    }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/近 11 個月・48 個觀測/)).toBeInTheDocument();
    expect(screen.queryByText(/近 1 年/)).not.toBeInTheDocument();
  });

  it("走勢圖的 aria-label 跟著實際涵蓋時間走，不是永遠寫死「近 1 年」", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      history_span_days: 330, observation_count: 48,
    }) };
    const { container } = render(<IvTrend legs={legs} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("aria-label")).toContain("近 11 個月");
    expect(chart.getAttribute("aria-label")).not.toContain("近 1 年");
  });
});

describe("固定文案（spec #151 §6 逐字原文）", () => {
  it("顯示歷史位置參考的固定 caption", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(
      "比較同一張 option 自己的歷史 IV；僅供歷史位置參考，不代表未來 IV 方向。",
    )).toBeInTheDocument();
  });
});

describe("backfill 狀態各自獨立（每隻腳自己的 status／note）", () => {
  it("其中一腿 vendor 失敗時，只有那一腿顯示附加說明", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv({ status: "ok" }),
      sell: legHistoricalIv({ status: "vendor" }),
    };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/資料源暫時無法連線/)).toBeInTheDocument();
  });

  it("兩腿都正常時不顯示任何附加說明", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv({ status: "ok" }),
      sell: legHistoricalIv({ status: "ok" }),
    };
    render(<IvTrend legs={legs} />);
    expect(screen.queryByText(/資料源暫時無法連線/)).not.toBeInTheDocument();
    expect(screen.queryByText(/今日 API 額度已用完/)).not.toBeInTheDocument();
  });

  it("額度用完時顯示對應說明", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({ status: "quota" }) };
    render(<IvTrend legs={legs} />);
    expect(screen.getByText(/今日 API 額度已用完/)).toBeInTheDocument();
  });
});

/**
 * Firstrade 風格整張圖 scrubber（需求方 2026-08-22 反饋）：整張 SVG 是
 * 單一 pointer／touch／keyboard 互動介面，依游標／觸點的 X 座標找最近
 * 的 observation，不再靠每個 observation 各自一顆透明命中圓點。座標
 * 換算是 `./ivHistoryChart` 的純函式 `nearestIndexForClientX`（已有
 * 獨立單元測試），這裡驗證接線：真的把游標位置轉成正確的 active
 * marker／tooltip，而且拖曳／鍵盤都能用。
 */
describe("走勢圖互動：整張圖是單一 scrubber 介面（不再靠逐點命中，" +
        "需求方 2026-08-22 反饋）", () => {
  function threePointLegs(): IvHistoryLegs {
    return { buy: legHistoricalIv({
      points: ivPoints(3, (i) => 0.20 + i * 0.01),
      moving_average: statPoints(3, () => null),
      bollinger_upper: statPoints(3, () => null),
      bollinger_lower: statPoints(3, () => null),
    }) };
  }

  it("預設狀態下沒有任何 active marker，也不需要", () => {
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(0);
    expect(container.querySelectorAll(".chart-tooltip")).toHaveLength(0);
  });

  it("桌面滑鼠在圖上移動時，依 X 座標找到最近的資料點並顯示 tooltip， " +
     "移出圖表後消失", () => {
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    stubChartWidth(chart);

    // 中間那個資料點（index 1 of 3）的畫布座標。
    firePointerMove(chart, clientXForPoint(1, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);
    expect(chart.querySelectorAll(".chart-tooltip").length).toBeGreaterThan(0);

    fireEvent.pointerLeave(chart);
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(0);
    expect(chart.querySelectorAll(".chart-tooltip")).toHaveLength(0);
  });

  it("marker 隨游標移動而換到最近的資料點，不是釘住第一次命中的點", () => {
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    stubChartWidth(chart);

    firePointerMove(chart, clientXForPoint(0, 3));
    expect(chart.querySelectorAll(".chart-tooltip")[0].textContent)
      .toContain("2026-01-01");

    firePointerMove(chart, clientXForPoint(2, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);
    expect(chart.querySelectorAll(".chart-tooltip")[0].textContent)
      .toContain("2026-01-03");
  });

  it("手機觸控：pointerdown 起手即顯示 marker，貼合手指落點，" +
     "單純點一下（pointerup）不會立刻把剛顯示的 marker 擦掉", () => {
    // 這是刻意的：touch 沒有「移出」這個中間狀態，鬆開手指是唯一訊號，
    // 若鬆開就清掉，單純點一下（down→up 幾乎同時發生）會讓使用者根本
    // 來不及看到剛顯示的 tooltip，等於 tap-to-view 整個失效——沿用舊版
    // 「tap 直接設定、維持到下一次互動」的既有行為。
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    stubChartWidth(chart);

    firePointerEvent(chart, "pointerdown", clientXForPoint(0, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);

    firePointerEvent(chart, "pointerup", clientXForPoint(0, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);
  });

  it("互動被系統手勢中斷（pointercancel）時清除 active 狀態", () => {
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    stubChartWidth(chart);

    firePointerEvent(chart, "pointerdown", clientXForPoint(0, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);

    firePointerEvent(chart, "pointercancel", clientXForPoint(0, 3));
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(0);
  });

  it("鍵盤：SVG 本身可 focus，方向鍵左右移動 active 資料點——一個容器" +
     "一個 tab stop，取代原本每個資料點各自一個 tabIndex", () => {
    const { container } = render(<IvTrend legs={threePointLegs()} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("tabindex")).toBe("0");

    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    // 已經在最後一個資料點，再往右不會超出範圍或報錯。
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(1);

    fireEvent.keyDown(chart, { key: "Escape" });
    expect(container.querySelectorAll(".chart-point-active")).toHaveLength(0);
  });

  it("不再依賴任何 tabIndex=0／role=button 的隱形逐點命中圓點", () => {
    const manyPointLegs: IvHistoryLegs = { buy: legHistoricalIv({
      points: ivPoints(250, (i) => 0.20 + (i % 20) * 0.001),
    }) };
    const { container } = render(<IvTrend legs={manyPointLegs} />);
    expect(container.querySelectorAll("[role='button']")).toHaveLength(0);
    // 唯一的 tab stop 是 SVG 本身，不是逐點命中圓點。
    expect(container.querySelectorAll("[tabindex='0']"))
      .toHaveLength(container.querySelectorAll(".iv-trend-chart").length);
  });
});

describe("手機版圖高度明顯縮小（Historical IV 圖表改版）：桌面維持原高度", () => {
  it("手機（預設 matchMedia 假體＝手機）走勢圖用較矮的高度", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("viewBox"))
      .toBe(`0 0 300 ${LEG_CHART_HEIGHT_MOBILE}`);
  });

  it("桌面斷點下走勢圖維持既有（較高的）高度，不受手機瘦身影響", () => {
    vi.stubGlobal("matchMedia",
      (q: string) => fakeMediaQueryList(true, q));
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    expect(chart.getAttribute("viewBox"))
      .toBe(`0 0 300 ${LEG_CHART_HEIGHT_DESKTOP}`);
  });
});

describe("只陳述事實（紅線，由測試守門而非自律）", () => {
  it("不出現任何評價字眼", () => {
    const legs: IvHistoryLegs = {
      buy: legHistoricalIv(), sell: legHistoricalIv(),
    };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.textContent).not.toMatch(
      /便宜|貴|划算|超值|好進場|進場點|推薦|建議|值得|機會|偏低|偏高|過高|過低|fair value|mispriced/i);
  });

  it("不出現任何預測語句", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.textContent).not.toMatch(
      /預期|預測|將會|可能觸底|即將|會再|會繼續|會回升|會下跌|趨勢將|一定會反彈/);
  });
});
