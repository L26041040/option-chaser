/**
 * Historical IV Trend——逐腿 exact-contract 卡片（HIVT-05／#156，
 * spec #151 §6）。
 *
 * 跟 `./IvHistory` 分屬兩個檔案，邊界跟著元件邊界走：這裡只測
 * `IvTrend` 元件本身（同步渲染，不必像 `IvHistory.test.tsx` 那樣繞過
 * 閘門／fetch 生命週期）——買賣腿各自獨立、資訊順序、統計量各自
 * graceful degradation、固定文案、facts-only 守門。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ContractIdentity, IvHistoryLegs, IvTrendStatPoint,
             LegHistoricalIv } from "./api";
import IvTrend, { zscoreCaption } from "./IvTrend";

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

describe("資訊順序：現值 → 走勢圖 → percentile → Δ4w → 涵蓋時間（SIG-02／#173 瘦身後）", () => {
  it("依瘦身後順序渲染，z-score 不在主要區塊裡", () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv() };
    const { container } = render(<IvTrend legs={legs} />);
    const card = container.querySelector(".iv-trend-card")!;
    // `.className` 在 SVG 元素上是 SVGAnimatedString，不是字串——一律用
    // `getAttribute("class")` 取得跨 HTML／SVG 一致的類別字串。
    const classes = Array.from(card.children)
      .map((el) => el.getAttribute("class"));
    expect(classes).toEqual([
      "iv-value-primary", "iv-trend-chart",
      "caption", "caption", "caption",
    ]);
  });

  it("Spread 模式：買腿卡片標籤在現值之前", () => {
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
    expect(screen.getByText("4週 —")).toBeInTheDocument();
  });

  it("moving average／Bollinger 帶整段都不可用時，圖仍然渲染（raw 線照常）",
     () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      moving_average: statPoints(60, () => null),
      bollinger_upper: statPoints(60, () => null),
      bollinger_lower: statPoints(60, () => null),
    }) };
    const { container } = render(<IvTrend legs={legs} />);
    expect(container.querySelector(".iv-trend-chart")).toBeInTheDocument();
    expect(container.querySelectorAll(".iv-trend-ma-line")).toHaveLength(0);
    expect(container.querySelectorAll(".iv-trend-band")).toHaveLength(0);
    // raw 線的互動點照常在。
    expect(container.querySelectorAll(".chart-point").length).toBeGreaterThan(0);
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

describe("走勢圖互動（沿用 Normalized Skew 走勢圖已驗證的手刻 SVG 作法）", () => {
  it("桌面 hover 資料點顯示 tooltip", async () => {
    const legs: IvHistoryLegs = { buy: legHistoricalIv({
      points: ivPoints(3, (i) => 0.20 + i * 0.01),
      moving_average: statPoints(3, () => null),
      bollinger_upper: statPoints(3, () => null),
      bollinger_lower: statPoints(3, () => null),
    }) };
    const { container } = render(<IvTrend legs={legs} />);
    const chart = container.querySelector(".iv-trend-chart")!;
    const point = chart.querySelectorAll<HTMLElement>("[role='button']")[0];

    await userEvent.hover(point);
    expect(chart.querySelectorAll(".chart-tooltip").length).toBeGreaterThan(0);

    await userEvent.unhover(point);
    expect(chart.querySelectorAll(".chart-tooltip")).toHaveLength(0);
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
