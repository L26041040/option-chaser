/**
 * V2-04（#406）：機會搜尋「容易誤會的指標」的 ⓘ 說明文字——**唯一來源**。
 *
 * 每則固定三段：定義、方向（越高越好還是越低越好）、計算口徑。名稱照 #405
 * 定稿（`metricHelp.test.ts` 鎖住名稱、禁用字眼，並用真實 helper 抽查範例
 * 數字：PR 用 `dispersionRank.ts`、分歧率用 `ratioPct()`、金額用 `money()`、
 * 目標漲跌幅用 `targetUpside.ts` 的 `targetUpsidePct()`／`formatUpside()`——
 * 前端唯一一套公式與小數位規則，與後端讀同一份案例，V2-06／#408）。
 *
 * 口徑對照後端（只是說明，不是演算法；改後端規則時要一起改這裡）：
 * - `option_chaser/consensus.py` `ConsensusRules`：`n_min=5`、`validity_months=12`、
 *   `h_min=24`、`lookback_points=60`、`stdev_kind="sample"`；月度點取每月最後
 *   一個平日（`_last_weekday`），嚴格早於資料日期；百分位用 midrank
 *   （`dispersion_percentile`）。
 * - `api_app/consensus_cache.py` `RefreshPolicy` 預設：重試 3 次、冷卻 15 分、
 *   429 沒給 Retry-After 時暫停 30 分、每日上游呼叫上限（一次＝一檔）。
 * - 結果表：`entry_cost` 每股、`max_loss_per_contract` 每口（100 股）；
 *   單位換算只在 `contractUnits.ts`。
 * - 目標漲跌幅：`api_app/price_quote.py::target_upside_pct`（小數一位、一半遠離零）。
 */

export interface MetricHelpEntry {
  /** 指標名稱（#405 定稿）。 */
  name: string;
  /** 定義：這個數字是什麼。 */
  definition: string;
  /** 方向：越高越好、越低越好，或沒有好壞方向。 */
  direction: string;
  /** 計算口徑：怎麼算、用哪些資料、單位。 */
  basis: string;
}

export const METRIC_HELP = {
  dispersionRank: {
    name: "分歧度歷史排序（PR）",
    definition:
      "今天的分析師分歧率，放進這檔股票自己過去的每月紀錄裡排第幾。",
    direction:
      "PR 越高，代表現在的共識比過去更集中。PR88＝比過去 88% 的月份更集中（前 12%）。",
    basis:
      "回看 60 個月，每月取月底（當月最後一個平日）的分歧率，只用早於資料日期的月份，至少 24 個有效月份才計算。用 midrank 算出原百分位，PR＝100 − 原百分位。畫面上的 PR 向下取整（原百分位 20.4% → PR79），篩選看的是未取整的原值，所以畫面顯示達標就一定通過。",
  },
  dispersionRate: {
    name: "分析師分歧率",
    definition: "有效券商目標價的標準差 ÷ 平均，看券商之間的看法差多少。",
    direction: "越低，券商看法越一致。",
    basis:
      "每家有效券商只取有效期 12 個月內最新的一筆目標價；股票分割前後發布的目標價先換算到同一個分割基準，再算樣本標準差與平均。例：平均 $200.00、標準差 $18.00 → 分歧率 9.0%。",
  },
  validBrokerCount: {
    name: "有效券商數",
    definition: "有效期 12 個月內、有最新目標價的券商（或分析師）數。",
    direction: "越多，平均目標價越有代表性。",
    basis:
      "同一家券商（或分析師）只算最新一筆；超過 12 個月的目標價不算。至少 5 家才計算平均目標價、分析師分歧率與 PR，不足 5 家列為資料不足。",
  },
  meanTarget: {
    name: "平均目標價",
    definition: "有效券商最新目標價的平均。",
    direction: "本身沒有好壞方向；和目前股價比，才看得出分析師認為的漲跌空間。",
    basis:
      "只用有效期 12 個月內各券商最新的目標價；股票分割前發布的目標價已換算成目前的分割基準（例：1 拆 4 之前的 $400.00 → $100.00）。",
  },
  currentPrice: {
    name: "目前股價",
    definition: "計算目標漲跌幅時用的股價。",
    direction: "沒有好壞方向，是目標漲跌幅的比較基準。",
    basis:
      "不是即時成交價：畫面會一併標示股價日期，股價日期可能和分析師資料日期不同。",
  },
  targetUpside: {
    name: "目標漲跌幅",
    definition: "平均目標價比目前股價高（或低）多少。",
    direction:
      "正值代表平均目標價高於目前股價，數字越大，分析師認為的上漲空間越大；負值代表平均目標價低於目前股價。",
    basis:
      "(平均目標價 ÷ 目前股價 − 1) × 100%，結果四捨五入到小數第一位（整好一半時遠離零）；股價用畫面標示的股價日期那天的價格。例：平均目標價 $120.00、目前股價 $100.00 → +20.0%。",
  },
  scenarioReturn: {
    name: "股價達標時的策略報酬",
    definition:
      "假設股價在目標月份剛好到達分析師平均目標價，這個策略的報酬率。",
    direction: "越高，在這個情境下賺得越多。",
    basis:
      "這是條件式的情境報酬，只回答「如果股價達標會怎樣」：它不代表股價達標的機率，也不是把各種可能結果平均起來的數字。沿用既有劇本的報酬算法（以最差成交價進場）。",
  },
  costAndMaxLoss: {
    name: "成本、最大損失",
    definition:
      "成本＝建立這個策略要付的淨權利金；最大損失＝到期時最壞情況會虧掉的金額。",
    direction: "越低，投入的錢與最壞情況的虧損越小。",
    basis:
      "有每股與每口兩種單位：1 口 = 100 股，每口＝每股 × 100。例：每股 $1.25 → 每口 $125.00。成本以最差成交價（買付 Ask、賣收 Bid）計算。",
  },
  scanUniverse: {
    name: "掃描股票範圍",
    definition: "機會搜尋要檢查分析師共識的股票清單（內建清單或自訂清單）。",
    direction: "沒有好壞方向；範圍越大，可能符合條件的股票越多，每天要抓的資料也越多。",
    basis:
      "只有每日更新範圍內的股票會建立與更新分析師資料；超出範圍的股票不會更新，畫面會列出檔數。",
  },
  dataDate: {
    name: "資料日期",
    definition: "這份分析師共識是用哪一天（美東日期）的資料算出來的。",
    direction: "越接近今天，資料越新。",
    basis:
      "每檔股票各自記錄最近一次成功更新的日期；更新失敗時沿用上一份資料，日期不會往前推。",
  },
  dailyCap: {
    name: "每日上限",
    definition: "每天最多向分析師資料來源抓幾次資料（一次＝一檔股票）。",
    direction: "沒有好壞方向；達到上限只是今天暫停更新，已建立的資料照常可以搜尋。",
    basis:
      "成功、失敗與重試都算進當天次數；達到上限後當天不再更新或重試，下一個平日自動更新。",
  },
  rateLimitPause: {
    name: "限流暫停",
    definition: "資料來源回覆「請求太頻繁」（429）時，全部更新暫停一段時間。",
    direction: "沒有好壞方向；暫停期間已建立的資料照常可以搜尋。",
    basis:
      "暫停時間照資料來源指定的等待時間；來源沒指定時預設暫停 30 分鐘，時間到了才會再更新或重試。",
  },
  rotatingUpdate: {
    name: "輪替更新",
    definition: "平日排程逐檔更新掃描範圍內的股票，不是一次全部重抓。",
    direction: "沒有好壞方向；只影響資料多快更新完。",
    basis:
      "當天已成功的股票不重抓；失敗的冷卻 15 分鐘後重試，預設最多 3 次；當天沒更新完的，下一個平日接著更新。",
  },
} as const satisfies Record<string, MetricHelpEntry>;

export type MetricHelpKey = keyof typeof METRIC_HELP;

/** ⓘ 圖示的 aria-label：「分析師分歧率說明」。 */
export function metricHelpLabel(key: MetricHelpKey): string {
  return `${METRIC_HELP[key].name}說明`;
}
