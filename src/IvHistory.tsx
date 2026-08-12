/**
 * Historical IV Position（#114，資料層見 #126）。
 *
 * 頭條是 **Normalized Skew**（賣腿 IV 減買腿 IV，除以當日 ATM 水準），
 * 兩腿各自的 IV 是明顯次一層。每一項都是「現值＋1 年百分位＋compact
 * sparkline」三件套，整塊維持 compact，手機上不長出一張大卡片。
 *
 * **閘門（#126 AC）**：Historical IV 沒解鎖時，這支元件不輸出任何 DOM
 * 節點，也**不發任何 IV 請求**——不是空卡片、不是「尚未啟用」提示。
 * 解不解鎖讀後端算好的 `historical_iv_enabled`，前端不自己重推規則。
 *
 * **只陳述事實**：現值、百分位、歷史形狀。不寫「便宜」「貴」「好進場
 * 點」「推薦」——那是替使用者做判斷，而這個模組只提供他判斷所需的
 * 相對位置。有測試守門，不是靠自律。
 *
 * **enrich-only**：這塊拿掉，每個候選的命運與順序一模一樣（#118 守門）。
 * 它不參與排序、不參與過濾、不影響 baseline 或 Top 10。
 */
import { useEffect, useState } from "react";

import {
  getSettings,
  ivHistory,
  type Candidate,
  type IvHistoryPoint,
  type IvHistoryStatus,
  type IvHistoryView,
} from "./api";

/**
 * 資料不完整時的說明。刻意**極短**——需求方明示不要大卡片、不要長篇。
 *
 * 五種情況裡的 `unset`（provider 未設定）與 `invalid`（驗證失敗）不在
 * 這張表：那兩種在閘門就擋掉了，整個模組不渲染，連訊息都不該出現。
 */
const STATUS_NOTES: Record<Exclude<IvHistoryStatus, "ok">, string[]> = {
  insufficient: ["歷史資料尚未完整", "將在後續使用時繼續補齊"],
  quota: ["歷史資料尚未完整", "今日 API 額度已用完", "將在後續使用時繼續補齊"],
  vendor: ["歷史資料尚未完整", "資料源暫時無法連線", "將在後續使用時繼續補齊"],
};

/** 百分位顯示成整數百分比；沒有百分位就明說超出可比網格，不留白讓人猜。 */
/** 單一項目算不出百分位時留空並說明——**留空不是留白**：什麼都不寫會
 *  讓人以為那個數字還沒載入完。文案維持極短。 */
function pctLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "無可比基準";
  return `第 ${Math.round(value * 100)} 百分位`;
}

function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/**
 * Compact sparkline。缺值（超出網格或 vendor 沒資料）**斷線**，不插值
 * ——把斷點連起來會讓一段其實沒有可比基準的區間看起來跟其他日子一樣
 * 可信（沿用 #57 Spread 走勢圖的既有處置）。
 */
function Sparkline({ series }: { series: (number | null)[] }) {
  const known = series.filter((v): v is number => v !== null);
  if (known.length < 2) return null;

  const lo = Math.min(...known);
  const hi = Math.max(...known);
  const span = hi - lo || 1;
  const w = 96;
  const h = 24;

  // 連續的非空區段各自成一條 polyline —— 中間的缺口就是斷線。
  const runs: string[] = [];
  let current: string[] = [];
  series.forEach((v, i) => {
    if (v === null) {
      if (current.length > 1) runs.push(current.join(" "));
      current = [];
      return;
    }
    const x = (i / Math.max(series.length - 1, 1)) * w;
    const y = h - ((v - lo) / span) * h;
    current.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  });
  if (current.length > 1) runs.push(current.join(" "));

  return (
    <svg className="iv-spark" viewBox={`0 0 ${w} ${h}`} width={w} height={h}
        aria-hidden="true" preserveAspectRatio="none">
      {runs.map((points, i) => (
        <polyline key={i} points={points} fill="none" stroke="currentColor"
                 strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      ))}
    </svg>
  );
}

function Metric({ label, value, percentile, series, primary = false }: {
  label: string;
  value: number | null;
  percentile: number | null | undefined;
  series: (number | null)[];
  primary?: boolean;
}) {
  return (
    <div className={primary ? "iv-metric iv-primary" : "iv-metric"}>
      <span className="row-label">{label}</span>
      <span className={primary ? "iv-value-primary" : "iv-value"}>
        {num(value)}
      </span>
      <span className="caption">{pctLabel(percentile)}</span>
      <Sparkline series={series} />
    </div>
  );
}

export default function IvHistory({ scenarioId, candidate }: {
  scenarioId: string;
  candidate: Candidate | null;
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [data, setData] = useState<IvHistoryView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const key = candidate?.candidate_key ?? null;

  // 先問解不解鎖。鎖著就到此為止——**不發 IV 請求**。
  useEffect(() => {
    let alive = true;
    getSettings()
      .then((s) => alive && setEnabled(s.historical_iv_enabled))
      // 設定讀不到時當成鎖著：寧可少顯示一塊 enrichment，也不要在狀態
      // 不明時對 vendor 發請求。
      .catch(() => alive && setEnabled(false));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (enabled !== true || !key) return;
    let alive = true;
    ivHistory(scenarioId, key)
      .then((v) => alive && setData(v))
      .catch((e) => alive
        && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [enabled, key, scenarioId]);

  // 鎖著、還沒問完、或這個候選根本沒有身份鍵 → 不輸出任何節點。
  if (enabled !== true || !key) return null;

  // vendor 失敗只影響這一塊，頁面其餘部分照常（#126 AC）。
  if (error) {
    return (
      <section className="card iv-history" aria-label="IV 相對位置">
        <h2 className="section-title">IV 相對位置</h2>
        <p className="caption">取不到歷史 IV：{error}</p>
      </section>
    );
  }

  if (!data) return null;

  // 資料不完整：只出短訊息，**不畫 percentile、不畫 sparkline**。硬畫
  // 一條線等於為了湊圖而假造資料（需求方紅線）。
  if (data.status !== "ok") {
    return (
      <section className="card iv-history" aria-label="IV 相對位置">
        <h2 className="section-title">IV 相對位置</h2>
        {STATUS_NOTES[data.status].map((line) => (
          <p className="caption" key={line}>{line}</p>
        ))}
      </section>
    );
  }

  const points: IvHistoryPoint[] = data.points;
  const cur = data.current;

  return (
    <section className="card iv-history" aria-label="IV 相對位置">
      <h2 className="section-title">IV 相對位置</h2>

      {/* 頭條：Normalized Skew。兩腿 IV 在下面一層，字級與權重都低一階。 */}
      <Metric
        primary
        label="Normalized Skew"
        value={cur?.normalized_skew ?? null}
        percentile={data.percentiles.normalized_skew}
        series={points.map((p) => p.normalized_skew)}
      />

      <div className="iv-legs">
        <Metric label="買腿 IV" value={cur?.buy_iv ?? null}
               percentile={data.percentiles.buy_iv}
               series={points.map((p) => p.buy_iv)} />
        <Metric label="賣腿 IV" value={cur?.sell_iv ?? null}
               percentile={data.percentiles.sell_iv}
               series={points.map((p) => p.sell_iv)} />
      </div>

      <p className="caption">
        近 1 年 {data.observations} 個觀測，依候選的到期天數與 delta 座標
        逐日重錨定
      </p>
    </section>
  );
}
