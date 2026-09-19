/**
 * 真實品牌 Logo（UI-IMPL-002／#092，Identity 板「真 Logo，或者什麼都不
 * 放」）：資料源＝Logo.dev 官方 ticker endpoint
 * （`img.logo.dev/ticker/{SYM}?...&fallback=404`）。
 *
 * 三種狀態，逐字對照設計稿：
 * - **狀態 A**（找到真實品牌 Logo）：方形 symbol，白底方塊維持深色
 *   介面下的可辨識度（黑色 Logo 如 Apple／Tesla 尤其需要）。
 * - **狀態 B**（只有橫式字標，例如 ETF 發行商）：不硬塞進正方形——
 *   `onLoad` 讀圖片真實寬高比，比例夠寬（>1.6）才加 `wide` 修飾
 *   class，讓方塊自動加寬到最多 96px（依尺寸級距）。這是自動判斷，
 *   不是為特定代號寫死的清單。
 * - **狀態 C**（`fallback=404`，資料源找不到真實 Logo）：`fallback=404`
 *   讓伺服器端直接回 404，不再收到任何形式的佔位圖——不畫首字母、
 *   不畫通用圖示、不畫 AI 生成替代品。`onError` 切到 `.tile.none`
 *   （透明、無邊框，只留代號本身），載入中同樣不顯示任何方塊內容
 *   （避免先閃一個空框再消失）。
 *
 * `VITE_LOGO_DEV_TOKEN`：Logo.dev 的 publishable key，可安全放前端
 * （官方文件明文允許）。未設定時退回 Logo.dev 官方公開文件裡示範用的
 * demo key——讓這個功能在沒有自行申請金鑰的環境下也能運作，但那把
 * demo key 是共用、有限流的，正式環境建議大哥申請一把免費帳號自己的
 * publishable key、設定這個環境變數（免費層 500k 次/月，見
 * `docs/research/public-beta-market-data-source-selection.md` 同一輪
 * 附帶查過的 Logo.dev 條款）。Logo API 本身不可用（額度用盡、逾時、
 * 網路問題）時一律走 `onError` 同一條路徑退化成「只有代號」，不會
 * 讓整個 UI 掛住或報錯。
 */
import { useEffect, useState } from "react";

const DEMO_TOKEN = "pk_X-1ZO13GSgeOoUrIuJ6GMQ";

/** 尺寸級距對照 OG-01（#317）Foundations 板：24 表格／清單列
 *  （`ScenarioList.tsx`／`CompactScenarioList.tsx` 皆傳 `size="s"`）
 *  · 32 建立表單預覽（`CreateForm.tsx` 不傳 `size`，吃這個預設值）
 *  · 40 詳細頁標頭（`ScenarioDetail.tsx` 傳 `size="l"`）· 56 保留給
 *  未來 Holdings 卡片，目前無消費端。 */
const SIZE_CLASS: Record<StockLogoSize, string> = {
  s: "tile s",
  m: "tile",
  l: "tile l",
  xl: "tile xl",
};

const SIZE_PX: Record<StockLogoSize, number> = { s: 24, m: 32, l: 40, xl: 56 };

export type StockLogoSize = "s" | "m" | "l" | "xl";

function logoUrl(symbol: string, px: number): string {
  const token =
    (import.meta.env.VITE_LOGO_DEV_TOKEN as string | undefined) || DEMO_TOKEN;
  const params = new URLSearchParams({
    token,
    fallback: "404",
    // 兩倍取樣供高密度螢幕，Logo.dev 依請求尺寸回傳裁切好的圖。
    size: String(px * 2),
  });
  return `https://img.logo.dev/ticker/${encodeURIComponent(symbol)}?${params}`;
}

/** 標的識別方塊——只顯示真 Logo，找不到就整個消失（只留呼叫端自己
 *  渲染的代號文字），不畫任何佔位圖形。 */
export default function StockLogo({
  symbol,
  size = "m",
}: {
  symbol: string;
  size?: StockLogoSize;
}) {
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [wide, setWide] = useState(false);

  // 換標的（不同劇本／候選）要重新嘗試——舊符號的失敗狀態不該沿用到
  // 新符號上。
  useEffect(() => {
    setStatus("loading");
    setWide(false);
  }, [symbol]);

  if (!symbol) return null;

  const px = SIZE_PX[size];
  const classes = [
    SIZE_CLASS[size],
    wide && "wide",
    status !== "ok" && "none",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes}>
      {status !== "error" && (
        <img
          src={logoUrl(symbol, px)}
          alt=""
          // 純裝飾——標的代號永遠緊接在呼叫端自己的文字裡，不需要
          // 螢幕閱讀器重複唸一次「NVDA logo」。
          aria-hidden="true"
          onLoad={(ev) => {
            const img = ev.currentTarget;
            if (img.naturalWidth > 0 && img.naturalHeight > 0) {
              setWide(img.naturalWidth / img.naturalHeight > 1.6);
            }
            setStatus("ok");
          }}
          onError={() => setStatus("error")}
        />
      )}
    </span>
  );
}
