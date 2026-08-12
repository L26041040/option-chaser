/**
 * Historical IV Position（#114，資料層見 #126／#130，呈現規則見 #133）。
 *
 * 頭條是 **Normalized Skew**（賣腿 IV 減買腿 IV，除以當日 ATM 水準），
 * 兩腿各自的 IV 是明顯次一層。每一項都是「現值＋百分位＋觀測筆數＋
 * compact sparkline」——只要那一項有至少一筆有效觀測就顯示，**不因
 * coverage 低或樣本數少而隱藏**（需求方 2026-08-12 二次修正裁示）；
 * 觀測筆數同時揭露，讓使用者自己判斷這個百分位站不站得住腳，產品不替
 * 他下「樣本不足所以不值得看」的判斷。唯一顯示「沒有歷史資料」的情況
 * 是那一項完全沒有可比較的觀測。
 *
 * **閘門（#126 AC）**：Historical IV 沒解鎖時，這支元件不輸出任何 DOM
 * 節點，也**不發任何 IV 請求**——不是空卡片、不是「尚未啟用」提示。
 * 解不解鎖讀後端算好的 `historical_iv_enabled`，前端不自己重推規則。
 *
 * **backfill 狀態只是附加說明，不取代資料**：今天補不補得動（quota／
 * vendor）跟資料能不能看是兩件事——已經算出來的 percentile 不因為今天
 * 撞額度就被藏起來，只是額外多一行「今日額度已用完」之類的說明。
 *
 * **只陳述事實**：現值、百分位、觀測筆數、歷史形狀。不寫「便宜」「貴」
 * 「好進場點」「推薦」「樣本不足」——那些都是替使用者做判斷，而這個
 * 模組只提供他判斷所需的相對位置與資料量。有測試守門，不是靠自律。
 *
 * **enrich-only**：這塊拿掉，每個候選的命運與順序一模一樣（#118 守門）。
 * 它不參與排序、不參與過濾、不影響 baseline 或 Top 10。
 */
import { useEffect, useState } from "react";

import {
  getSettings,
  ivHistory,
  type Candidate,
  type IvFieldMetric,
  type IvHistoryStatus,
  type IvHistoryView,
} from "./api";

/**
 * 今天的 backfill 遇到什麼——一行附加說明，**不取代**下面的 percentile。
 * `unset`／`invalid` 不在這張表：那兩種在閘門就擋掉了，整個模組不渲染。
 */
const BACKFILL_NOTES: Record<Exclude<IvHistoryStatus, "ok">, string> = {
  quota: "今日 API 額度已用完，將於後續使用時繼續補齊",
  vendor: "資料源暫時無法連線，將於後續使用時繼續補齊",
};

/**
 * 百分位＋觀測筆數的複合標籤——這是需求方要求的「揭露 percentile 建立
 * 在多少筆觀測上」的具體呈現，跟著現值一起讀，不必另外點開什麼。
 * `count === 0`（唯一容許沒有百分位的情況）時誠實說沒有歷史資料，
 * **不是**判斷「資料不夠可信」——那個判斷留給使用者自己做。
 */
function metricCaption(m: IvFieldMetric): string {
  if (m.count === 0 || m.percentile === null) return "沒有歷史資料";
  return `第 ${Math.round(m.percentile * 100)} 百分位・${m.count} 筆觀測`;
}

function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/**
 * Compact sparkline。缺值（超出網格或 vendor 沒資料）**斷線**，不插值
 * ——把斷點連起來會讓一段其實沒有可比基準的區間看起來跟其他日子一樣
 * 可信（沿用 #57 Spread 走勢圖的既有處置）。
 *
 * 高度刻意壓到 18px（#135）：這是掛在數值旁邊的形狀提示，不是獨立一張
 * 走勢圖——扁平化是需求方對整區「壓到合理最低」的明文要求之一。
 */
function Sparkline({ series }: { series: (number | null)[] }) {
  const known = series.filter((v): v is number => v !== null);
  if (known.length < 2) return null;

  const lo = Math.min(...known);
  const hi = Math.max(...known);
  const span = hi - lo || 1;
  const w = 96;
  const h = 18;

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

/**
 * 兩行版型（#135 壓平）：標籤＋百分位同一行，數值自己一行——比原本
 * label／value／百分位各佔一行的三行堆疊少一行，sparkline 佔右側整欄
 * 不額外加高整塊高度。
 */
function Metric({ label, metric, series, primary = false }: {
  label: string;
  metric: IvFieldMetric;
  series: (number | null)[];
  primary?: boolean;
}) {
  return (
    <div className={primary ? "iv-metric iv-primary" : "iv-metric"}>
      <div className="iv-metric-head">
        <span className="row-label">{label}</span>
        <span className="caption">{metricCaption(metric)}</span>
      </div>
      <span className={primary ? "iv-value-primary" : "iv-value"}>
        {num(metric.value)}
      </span>
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

  const points = data.points;

  return (
    <section className="card iv-history" aria-label="IV 相對位置">
      <h2 className="section-title">IV 相對位置</h2>

      {/* backfill 今天遇到的狀況——只是額外一行說明，**不取代**下面的
          percentile：狀態與資料能不能看是兩件事（需求方 2026-08-12
          二次修正）。status 為 ok 時完全不出現這一行。 */}
      {data.status !== "ok" && (
        <p className="caption">{BACKFILL_NOTES[data.status]}</p>
      )}

      {/* 頭條：Normalized Skew。兩腿 IV 在下面一層，字級與權重都低一階。
          每一項各自依自己的 count 決定顯示數字還是「沒有歷史資料」，
          不受 status 或彼此影響——這正是拿掉整段門檻之後的樣子。 */}
      <Metric
        primary
        label="Normalized Skew"
        metric={data.metrics.normalized_skew}
        series={points.map((p) => p.normalized_skew)}
      />

      <div className="iv-legs">
        <Metric label="買腿 IV" metric={data.metrics.buy_iv}
               series={points.map((p) => p.buy_iv)} />
        <Metric label="賣腿 IV" metric={data.metrics.sell_iv}
               series={points.map((p) => p.sell_iv)} />
      </div>

      <p className="caption">
        近 1 年 {data.observations} 個觀測，依候選的到期天數與 delta 座標
        逐日重錨定
      </p>
    </section>
  );
}
