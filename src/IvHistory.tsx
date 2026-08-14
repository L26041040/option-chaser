/**
 * Historical IV Position（#114，資料層見 #126／#130，呈現規則見 #133；
 * 一年走勢圖為主體＋Δ4w：#140／spec #137）。
 *
 * Spread 模式：頭條 Normalized Skew，兩腿 IV 次層——次層不是簡化成只剩
 * 數字，而是各自擁有跟頭條同等資訊完整度的走勢圖／百分位／筆數／Δ4w
 * （spec #137 Gate 1 的落地處：Ĝ 只描述結構形狀，不含整體水位——「skew
 * 好看但 vol level 很高、debit 其實比歷史貴」確實可能發生，解法不是換
 * 掉 Ĝ，是讓水位跟結構形狀在同一區塊並列可讀）。
 *
 * Long Call 模式（單腳候選，資料層見 #139）：沒有賣腿就沒有 skew 可言，
 * 頭條改買腿 IV（level 語言），次層是 ATM IV。
 *
 * 每一項都是「現值＋百分位・筆數・Δ4w＋一年走勢圖」——只要那一項有至少
 * 一筆有效觀測就顯示，**不因 coverage 低或樣本數少而隱藏**（需求方
 * 2026-08-12 二次修正裁示；Δ4w 延伸適用同一原則：基準窗只要有一筆就
 * 給，`trend_base_count` 讓使用者自己判斷站不站得住腳）。
 *
 * **#135 的部分覆蓋**：#135 曾要求這一區「壓到合理最低」，sparkline 因此
 * 壓到 18px；本輪（spec #137）需求方改裁示「走勢圖為主」——percentile
 * 給位置、圖給路徑、Δ4w 給最近速度，三者互補，不需要任何預測模型。
 * 本檔案在 Historical IV 這個區塊覆蓋 #135 的壓平要求，這是新裁示，
 * 不是遺漏舊裁示。
 *
 * **閘門（#126 AC）**：Historical IV 沒解鎖時，這支元件不輸出任何 DOM
 * 節點，也**不發任何 IV 請求**——不是空卡片、不是「尚未啟用」提示。
 * 解不解鎖讀後端算好的 `historical_iv_enabled`，前端不自己重推規則。
 *
 * **backfill 狀態只是附加說明，不取代資料**：今天補不補得動（quota／
 * vendor）跟資料能不能看是兩件事——已經算出來的 percentile／Δ4w 不因為
 * 今天撞額度就被藏起來，只是額外多一行「今日額度已用完」之類的說明。
 *
 * **只陳述事實**：現值、百分位、觀測筆數、Δ4w、一年走勢圖。不寫「便宜」
 * 「貴」「好進場點」「推薦」——那些都是替使用者做判斷；**也不寫任何
 * 預測語句**（「預期還會再跌」「可能觸底」之類）——facts-only 紅線延伸
 * 涵蓋 forecast，是比評價字眼更嚴格的一種越界。方法論註記只陳述 Δ4w
 * 的定義與「等待另有已知的 theta 成本與標的價格風險」這句事實，不下
 * 判斷、不預測。有測試守門，不是靠自律。
 *
 * **enrich-only**：這塊拿掉，每個候選的命運與順序一模一樣（#118 守門）。
 * 它不參與排序、不參與過濾、不影響 baseline 或 Top 10。
 *
 * 零金融計算：`value`／`percentile`／`trend_4w`／`points` 全部是後端
 * 算好的，這裡只做座標換算與呈現（`./ivHistoryChart` 的純函式，沿用
 * Spread 淨成本走勢圖已驗證的手刻 SVG 作法，不引入圖表函式庫）。
 */
import { useEffect, useState } from "react";

import {
  getSettings,
  ivHistory,
  type Candidate,
  type IvFieldMetric,
  type IvHistoryPoint,
  type IvHistoryStatus,
  type IvHistoryView,
} from "./api";
import { contiguousRuns, ivChartPoints, ivYAxisDomain, xAxisTicks,
        type ChartPoint } from "./ivHistoryChart";

/**
 * 今天的 backfill 遇到什麼——一行附加說明，**不取代**下面的 percentile。
 * `unset`／`invalid` 不在這張表：那兩種在閘門就擋掉了，整個模組不渲染。
 */
const BACKFILL_NOTES: Record<Exclude<IvHistoryStatus, "ok">, string> = {
  quota: "今日 API 額度已用完，將於後續使用時繼續補齊",
  vendor: "資料源暫時無法連線，將於後續使用時繼續補齊",
};

/** 這個欄位的量該用什麼單位呈報——腿 IV／ATM IV 是 vol 點（百分比），
 *  Normalized Skew 無因次，現值與 Δ4w 都印小數（spec #137 §7.5 逐字
 *  範例：`Normalized Skew 0.50 ... 4週 +0.06`，不是 `50% ... +6.0%`）。 */
type TrendUnit = "vol-pts" | "unitless";

function num(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 現值的呈現——單位隨欄位而定（見 `TrendUnit`）。Normalized Skew 改用
 *  無因次小數而不是既有 `num()` 的百分比格式：跟同一欄位新增的 Δ4w
 *  用同一種語言，避免「現值 8.0% 但變化量 +0.06」這種同一個量卻兩套
 *  單位並列的困惑——這個混淆是新增 Δ4w 才會出現的，不是延續既有行為。 */
function valueLabel(value: number | null, unit: TrendUnit): string {
  if (value === null) return "—";
  return unit === "vol-pts" ? num(value) : value.toFixed(2);
}

/** 帶正負號的 Δ4w，量自身單位——不是預測，只是「最新減基準」這件事實
 *  的呈報。`trend_4w` 為 `null`（基準窗內無觀測）時印 em dash，不外推、
 *  不假裝沒有變化（那會把「沒有基準可比」跟「比較完發現剛好沒變」
 *  混為一談，兩者是不同的事實）。 */
function trendLabel(m: IvFieldMetric, unit: TrendUnit): string {
  if (m.trend_4w === null) return "4週 —";
  const sign = m.trend_4w >= 0 ? "+" : "-";
  const magnitude = unit === "vol-pts"
    ? `${Math.abs(m.trend_4w * 100).toFixed(1)} pts`
    : Math.abs(m.trend_4w).toFixed(2);
  return `4週 ${sign}${magnitude}`;
}

/**
 * 百分位＋觀測筆數＋Δ4w 的複合標籤——這是需求方要求的「揭露 percentile
 * 建立在多少筆觀測上」的具體呈現，跟著現值一起讀，不必另外點開什麼。
 * `count === 0`（唯一容許沒有百分位的情況）時誠實說沒有歷史資料，
 * **不是**判斷「資料不夠可信」——那個判斷留給使用者自己做。
 */
function metricCaption(m: IvFieldMetric, unit: TrendUnit): string {
  if (m.count === 0 || m.percentile === null) return "沒有歷史資料";
  return `第 ${Math.round(m.percentile * 100)} 百分位・${m.count} 筆觀測・${
    trendLabel(m, unit)}`;
}

const PAD_TOP = 12;
const PAD_RIGHT = 6;
const PAD_BOTTOM = 16;
const PAD_LEFT = 34;

/** `y` 容許 `null`（X 軸刻度只需要 `px`，那個呼叫端不保證 `y` 非空）
 *  ——呼叫端若真的需要 `py` 一定是從 `runs`（已篩掉 `null` 的片段）
 *  取來的點，`y` 屆時已經是 `number`。 */
function toPixel(p: { x: number; y: number | null }, width: number,
                 height: number) {
  const plotWidth = width - PAD_LEFT - PAD_RIGHT;
  const plotHeight = height - PAD_TOP - PAD_BOTTOM;
  return { px: PAD_LEFT + p.x * plotWidth,
          py: PAD_TOP + (p.y ?? 0) * plotHeight };
}

/** 這個欄位一年走勢圖的 y 軸刻度怎麼寫成文字——沿用現值同一套單位，
 *  刻度與現值講同一種語言，不會讓人在同一張圖裡看到兩套不一致的數字。 */
function tickLabel(value: number, unit: TrendUnit): string {
  return unit === "vol-pts" ? num(value) : value.toFixed(2);
}

/**
 * 一年走勢圖——取代原本 18px 的 sparkline，成為這一區塊的主要視覺
 * （#140／spec #137：percentile 給位置、圖給路徑、Δ4w 給最近速度，
 * 三者互補）。y 軸固定域不隨互動改變；x 軸日期刻度均勻取樣涵蓋頭尾；
 * 缺值斷線不插值；tooltip 桌面 hover／手機 tap 共用同一套狀態（沿用
 * Spread 淨成本走勢圖 #106 已驗證的手刻 SVG 作法，不引入圖表函式庫，
 * 不加 zoom／pan——y 軸固定的驗收標準因此無從被互動破壞）。
 *
 * `points` 全 `null`（`ivYAxisDomain` 回 `null`）時不畫任何東西——呼叫
 * 端的「沒有歷史資料」文案已經交代過這個狀態，不需要一個空白的圖表
 * 外框重複說一次同一件事。
 */
function TrendChart({ label, unit, points, width, height }: {
  label: string;
  unit: TrendUnit;
  points: { date: string; value: number | null }[];
  width: number;
  height: number;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const values = points.map((p) => p.value);
  const domain = ivYAxisDomain(values);
  if (domain === null) return null;

  const dates = points.map((p) => p.date);
  const chartPts = ivChartPoints(dates, values, domain);
  const runs = contiguousRuns(chartPts);
  const indexOf = new Map(chartPts.map((p, i) => [p, i]));
  const [lo, hi] = domain;
  const yTicks: [number, number][] = [[0, hi], [0.5, (lo + hi) / 2], [1, lo]];
  const xTicks = xAxisTicks(chartPts);
  const active = activeIndex === null ? null : chartPts[activeIndex];
  const activeValue = activeIndex === null ? null : values[activeIndex];

  return (
    <svg
      className="iv-trend-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${label}走勢，近 1 年`}
    >
      {/* Y 軸：三個刻度（低／中／高，固定範圍，不隨互動變動），單位隨
          欄位而定，與現值同一套語言。 */}
      {yTicks.map(([frac, value]) => {
        const py = PAD_TOP + frac * (height - PAD_TOP - PAD_BOTTOM);
        return (
          <g key={frac}>
            <line x1={PAD_LEFT - 3} y1={py} x2={PAD_LEFT} y2={py}
                 className="chart-tick-mark" />
            <text x={PAD_LEFT - 5} y={py + 3} textAnchor="end"
                 className="chart-tick-label">
              {tickLabel(value, unit)}
            </text>
          </g>
        );
      })}

      {/* X 軸：日期刻度，均勻取樣（含首尾），不是每個資料點都印一個。 */}
      {xTicks.map(({ index, label: dateLabel }) => {
        const { px } = toPixel(chartPts[index], width, height);
        const bottom = height - PAD_BOTTOM;
        return (
          <g key={index}>
            <line x1={px} y1={bottom} x2={px} y2={bottom + 3}
                 className="chart-tick-mark" />
            <text x={px} y={height - 3} textAnchor="middle"
                 className="chart-tick-label">
              {dateLabel}
            </text>
          </g>
        );
      })}

      {runs.map((run, i) => (
        <g key={i}>
          {/* 每段各自一條折線——段與段之間刻意不連線，斷點如實顯示，
              不畫成連續、也不畫成 0。 */}
          <polyline
            fill="none"
            stroke="var(--tint)"
            strokeWidth={1.5}
            points={run.map((p) => {
              const { px, py } = toPixel(p, width, height);
              return `${px},${py}`;
            }).join(" ")}
          />
          {run.map((p) => {
            const { px, py } = toPixel(p, width, height);
            const idx = indexOf.get(p)!;
            return (
              <circle
                // 用序列位置而非日期字串當 key：真實資料每個 symbol 每天
                // 只有一筆觀測、日期天然唯一，但 key 的穩定性不該依賴這
                // 個外部假設——位置在同一次渲染裡本來就唯一。
                key={idx}
                cx={px} cy={py} r={4}
                className="chart-point"
                tabIndex={0}
                role="button"
                aria-label={`${p.label}，${label} ${
                  valueLabel(values[idx], unit)}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseLeave={() => setActiveIndex(null)}
                onFocus={() => setActiveIndex(idx)}
                onBlur={() => setActiveIndex(null)}
                // 手機 tap 沒有 hover 狀態，click 是唯一訊號——直接設定
                // 而不是切換：真實觸控會先合成一輪 hover 事件再送出
                // click，切換邏輯在那個當下會誤判成「已經開著、這次點擊
                // 是要關掉」，點了等於沒點。
                onClick={() => setActiveIndex(idx)}
              />
            );
          })}
        </g>
      ))}

      {active && activeValue !== null && (
        <ChartTooltip point={active} value={activeValue} unit={unit}
                     width={width} height={height} />
      )}
    </svg>
  );
}

/** 桌面 hover／手機 tap 共用的同一個 tooltip——固定含日期與這一項的值。
 *  位置貼著資料點，靠左右邊緣時往內收，不出界（沿用 Spread 淨成本走勢
 *  圖既有作法）。 */
function ChartTooltip({ point, value, unit, width, height }: {
  point: ChartPoint;
  value: number;
  unit: TrendUnit;
  width: number;
  height: number;
}) {
  const { px, py } = toPixel(point, width, height);
  const boxWidth = 84;
  const boxHeight = 30;
  const x = Math.min(Math.max(px - boxWidth / 2, PAD_LEFT),
                     width - PAD_RIGHT - boxWidth);
  const y = Math.max(py - boxHeight - 8, 0);
  return (
    <g className="chart-tooltip">
      <rect x={x} y={y} width={boxWidth} height={boxHeight} rx={5} />
      <text x={x + boxWidth / 2} y={y + 12} textAnchor="middle">
        {point.label}
      </text>
      <text x={x + boxWidth / 2} y={y + 24} textAnchor="middle">
        {valueLabel(value, unit)}
      </text>
    </g>
  );
}

function seriesFor(
  points: IvHistoryPoint[], field: keyof Omit<IvHistoryPoint, "date">,
): { date: string; value: number | null }[] {
  return points.map((p) => ({ date: p.date, value: p[field] }));
}

/**
 * 一項指標的完整呈現：標籤＋現值＋百分位／筆數／Δ4w 複合標籤＋一年
 * 走勢圖。主位（`primary`）圖較大；次層圖較小，但資訊完整——不是把
 * 次層簡化成只剩數字（Gate 1：買賣腿的水位要跟頭條的結構形狀一樣
 * 讀得到，見檔頭說明）。
 */
function Metric({ label, metric, points, unit, primary = false }: {
  label: string;
  metric: IvFieldMetric;
  points: { date: string; value: number | null }[];
  unit: TrendUnit;
  primary?: boolean;
}) {
  const width = primary ? 300 : 200;
  const height = primary ? 104 : 60;
  return (
    <div className={primary ? "iv-metric iv-primary" : "iv-metric"}>
      <div className="iv-metric-head">
        <span className="row-label">{label}</span>
        <span className="caption">{metricCaption(metric, unit)}</span>
      </div>
      <span className={primary ? "iv-value-primary" : "iv-value"}>
        {valueLabel(metric.value, unit)}
      </span>
      <TrendChart label={label} unit={unit} points={points}
                 width={width} height={height} />
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
  // `!candidate` 這條分支實務上不會單獨發生（`key` 已經蘊含 `candidate`
  // 存在），寫出來純粹是讓 TS 把下面的 `candidate.legs` 收窄成非 null。
  if (enabled !== true || !key || !candidate) return null;

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
  // Long Call（單腳候選）沒有賣腿——頭條改買腿 IV，次層是 ATM IV
  // （#139 資料層對單腳誠實回 sell_iv／normalized_skew 為 None）。用
  // `candidate.legs.length` 判斷跟 `SpreadHistory` 判斷單腳的既有慣例
  // 同一種手法，不另創一套規則。
  const isSingleLeg = candidate.legs.length < 2;

  return (
    <section className="card iv-history" aria-label="IV 相對位置">
      <h2 className="section-title">IV 相對位置</h2>

      {/* backfill 今天遇到的狀況——只是額外一行說明，**不取代**下面的
          percentile／Δ4w：狀態與資料能不能看是兩件事（需求方 2026-08-12
          二次修正）。status 為 ok 時完全不出現這一行。 */}
      {data.status !== "ok" && (
        <p className="caption">{BACKFILL_NOTES[data.status]}</p>
      )}

      {isSingleLeg ? (
        <>
          <Metric
            primary
            label="買腿 IV"
            unit="vol-pts"
            metric={data.metrics.buy_iv}
            points={seriesFor(points, "buy_iv")}
          />
          <div className="iv-legs single">
            <Metric label="ATM IV" unit="vol-pts" metric={data.metrics.atm_iv}
                   points={seriesFor(points, "atm_iv")} />
          </div>
        </>
      ) : (
        <>
          <Metric
            primary
            label="Normalized Skew"
            unit="unitless"
            metric={data.metrics.normalized_skew}
            points={seriesFor(points, "normalized_skew")}
          />
          <div className="iv-legs">
            <Metric label="買腿 IV" unit="vol-pts" metric={data.metrics.buy_iv}
                   points={seriesFor(points, "buy_iv")} />
            <Metric label="賣腿 IV" unit="vol-pts" metric={data.metrics.sell_iv}
                   points={seriesFor(points, "sell_iv")} />
          </div>
        </>
      )}

      <p className="caption">
        近 1 年 {data.observations} 個觀測，依候選的到期天數與 delta 座標
        逐日重錨定
      </p>
      {/* 方法論註記（#140／spec #137 §7.5）：Δ4w 的定義＋等待進場的
          誠實帳本，兩句事實，不下判斷、不預測。 */}
      <p className="caption">
        4週變化＝與約四週前（21–42 天窗內觀測中位數）之差；等待進場另有
        已知的 theta 成本與標的價格風險，本區塊僅描述 volatility 結構。
      </p>
    </section>
  );
}
