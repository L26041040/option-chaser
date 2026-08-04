# Option Chaser

Long Call scenario optimizer. Given YOUR scenario (target price + target date),
it scans the current option chain, filters for tradeability, valuates every
qualifying Long Call with Black-Scholes under your scenario, bands candidates
by Delta (conservative / balanced / aggressive), and prints a deterministic
plain-text report with price-ceiling guidance.

It does NOT predict stocks, judge your scenario, estimate probabilities, or
give investment advice. Same snapshot + same params = byte-identical output.

## Install

    pip install -e .

## Run (online; saves a snapshot under snapshots/)

    option-chaser NVDA --target-price 220 --target-month 2026/9

## Re-run offline from a snapshot

    option-chaser NVDA --target-price 220 --target-month 2026/9 \
        --snapshot snapshots/NVDA_xxxx.json

## Strategies

    --strategy long-call          (default) bullish single leg
    --strategy long-put           bearish single leg
    --strategy bull-call-spread   bullish debit vertical (exhaustive same-expiry pairs)
    --strategy bear-put-spread    bearish debit vertical

Direction guard: bullish strategies need target > spot, bearish need target < spot
(override with --force). Band-first candidates include a price×date P/L matrix
(11 price rows spanning 4 bold anchor prices — spot, target, overshoot
(target ±10%), adverse (spot ∓10%) — plus evenly-interpolated rows in between;
× up to 7 date columns; add --matrix-all for every candidate).

## Removed in v2

    --min-days-after / --delay-days and the stress-test section are gone —
    the matrix supersedes them.

## Key flags

    --target-month YYYY/M the scenario's target month; 2028/1, 2028/01, 28/1 and
                          28/01 all mean the same month. Expiries are chosen from
                          the chain around that month's third Friday (see below).
    --iv-shifts CSV       IV scenarios, default -0.2,0,0.2 (0 always included)
    --min-return X        L3 price ceiling = baseline value / (1+X)
    --max-spread-pct / --spread-floor   quality-flag threshold, not a hard
                          gate — open interest, volume, and spread width no
                          longer exclude candidates, they set the ⚠ flag
                          shown on each candidate — spec #61
    --delta-bands A,B     |Delta| banding thresholds, default 0.35,0.65
    --matrix-all          matrix on every candidate
    --md PATH             also write the report to a file

Snapshots are schema v2 (calls + puts). v1 snapshots must be re-fetched.

## Reading the report

- Filter stats: how many contracts got cut from the full chain, and why
  (quote validity / IV solvable). Liquidity and spread width no longer cut
  candidates — they show up as a per-candidate ⚠ warning instead (spec #61).
  Which expiries get analysed is decided beforehand by the selection rule,
  not by a filter.
- Single-leg candidates come in three Delta bands (conservative / balanced /
  aggressive); spreads are a single ranked list.
- Each candidate: Bid/Mid/Ask (with per-contract dollar amounts), Breakeven,
  three IV-scenario valuations (value + P/L + return), and a buy-price
  ceiling guide (flagged if the current Ask exceeds it).
- Resilience vector (new): 7 fixed stress scenarios — no-move, half-way,
  mostly-there, arrives 30 days late, arrives 90 days late, most-conservative
  IV, and a natural-fill (Ask/Bid) entry — all priced on a Mid cost basis
  except S7 (natural fill, taker price).
  The reported worst-case return is simply the lowest of those 7 numbers: a
  transparent worst-of-a-fixed-scenario-set value, not a statistical
  inference. Also reported: a scenario-completion curve (return at 0/25/
  50/75/100% of the way from spot to target), a breakeven threshold (a
  *suffix* condition — once completion clears this threshold, any higher
  completion also doesn't lose money), a no-move retention ratio (leftover
  value / entry cost if the underlying never moves), and execution friction
  (as a percentage, plus the absolute dollar amount per share).
- P/L matrix: rows = underlying price (the 4 bold anchor rows above, plus
  interpolated rows), columns = date (* = target date, last column = expiry
  payoff), cell = Mid-entry return %.

## Known model limitations (read before trusting the numbers)

- No dividend adjustment (q=0): high-yield underlyings make call values look
  systematically optimistic and put values look conservative; deep-ITM,
  long-dated contracts are hit hardest — the "floor" line is the built-in
  guard against this.
- IV is held constant through the target date; realized IV will differ — the
  ±20% IV scenarios are the hedge for that.
- Quotes are yfinance-delayed data (~15 min); zero-volume contracts get a
  "stale quote" flag.
- The delayed-arrival scenarios (arrives 30/90 days late) assume a *linear*
  price path from spot to target between now and the delayed arrival date —
  a modeling assumption, not a market forecast.
- Estimates are not guaranteed fills; nothing here is investment advice.

## Web app

The interactive web app is a separate Vite + React (TypeScript) frontend
backed by a Python serverless API (FastAPI, imports this same
`option_chaser` engine directly) — see `docs/deploy-vercel.md` for the
full architecture, Vercel deployment steps, and connecting Neon Postgres
for persistence.

    npm install
    npm run dev                # frontend dev server, http://localhost:5173
    PYTHONPATH=. .venv/bin/python -m pytest    # backend/API tests

The web app opens on the scenario library (create/list/archive scenarios,
refresh at the top level) and its detail view: summary -> main Heatmap for
the baseline expiry's top candidate -> Long Call catch-up price -> expiry
picker with a per-expiry Top 10 list -> candidate-pool diagnostics -> a
collapsed "advanced" area (redesigned analysis report, Spread cost history
chart, raw snapshot data with CSV download). The web app performs no
financial arithmetic of its own — every number on screen comes from this
same engine via the HTTP API (`store.serialize_result`), exactly like the
CLI. Scenario data persists to Postgres (Neon, via Vercel Storage) in
production; a scenario created without a connected database is kept only
in the serverless function's memory and does not survive a redeploy — see
`docs/deploy-vercel.md` to confirm persistence is actually connected
(`GET /api/health`'s `storage` field).

(A Streamlit-based prototype frontend, `webapp/`, existed during the
rewrite and has been removed — this Vite/React app is now the only
frontend.)

## Tests (all offline)

    python -m pytest

Specs: docs/superpowers/specs/2026-07-15-option-chaser-mvp-design.md (v1),
docs/superpowers/specs/2026-07-19-option-chaser-v2-design.md (v2),
docs/superpowers/specs/2026-07-19-option-chaser-v3-gui-design.md (v3),
docs/superpowers/specs/2026-07-20-option-chaser-v4-design.md (v4)

---

# 使用說明（中文）

## 這是什麼

你提供「劇本」（某檔美股會在某天到達某個價位），本工具掃描目前市場上
整條選擇權鏈，過濾掉不可交易的合約，用 Black-Scholes 在「劇本成立」的
假設下估算每個候選的損益，排名後輸出報告——每個級距首選附一張
「價格 × 日期」P/L 矩陣（同 optionsprofitcalculator.com 的矩陣體驗，
外加它做不到的自動掃鏈與多組合同場比較）。

本工具不預測股價、不判斷你的劇本對不對、不算機率、不構成投資建議。
同一份快照 + 同參數 = 逐位元相同的報告（可覆核、可重現）。

## 安裝

    pip install -e .

## 四種策略與範例

    # 看漲單腿（預設）：TLT 在 2027-12-31 前到 110
    option-chaser TLT --target-price 110 --target-month 2027/12

    # 看漲垂直價差（同到期日全配對窮舉，降低成本、獲利封頂）
    option-chaser TLT --strategy bull-call-spread --target-price 110 --target-month 2027/12

    # 看跌單腿：TLT 在 2027-06-30 前跌到 70
    option-chaser TLT --strategy long-put --target-price 70 --target-month 2027/6

    # 看跌垂直價差
    option-chaser TLT --strategy bear-put-spread --target-price 70 --target-month 2027/6

方向守衛：看漲策略要求目標價 > 現價、看跌策略要求目標價 < 現價，
方向相反時會擋下並提示加 --force 才放行。

## 怎麼讀報告

- 過濾統計：三分類（spec #61）——A 類「報價異常」、B 類「IV 異常」是
  硬門檻，刷掉多少候選就列多少；C 類（未平倉量／成交量／價差寬度／
  無套利一致性）從不刷掉候選，改成合格池裡「標示」了幾筆，逐項列在
  同一區塊、跟 A/B 的排除數分開；每個候選上另有對應的 ⚠／🚩 標示。
  到期日本身的取捨在過濾之前，由選取規則負責
- 單腿分三級距（依 |Delta|）：保守型（深價內，容錯大）、平衡型、
  積極型（價外，高槓桿）；價差為單一排名清單
- 每候選：Bid/Mid/Ask（含每張金額）、Breakeven、IV 三情境估值
  （估值+損益+報酬率）、買價指引天花板（超過就警示）
- 韌性向量（CLI 新增）：7 個固定壓力情境（不漲／半程／大半程／晚30天／
  晚90天／IV最保守／Natural成交），除 S7（Natural 成交，以吃單價計）外皆以 Mid 進場計；「情境最壞」即這
  7 個情境報酬率中的最低值——是透明情境集合下的最壞值，非統計推論。
  另外會列出「劇本完成度」曲線（完成 0/25/50/75/100% 對應的報酬率）、
  「保本門檻」（後綴條件：一旦完成度達到門檻，之後任何更高完成度也不會
  虧）、「不漲保留率」（股價完全不動時剩餘價值佔進場成本的比例），以及
  「Bid-Ask Spread」（百分比之外同時換算列出絕對金額）。
- P/L 矩陣：列 = 股價（11 列，其中 4 個錨點價格粗體標記：現價／目標／
  超標(目標±10%)／深跌(現價∓10%)，其餘為等距內插價）、欄 = 日期
  （末欄為該合約自身的到期日 payoff）、格值 = 以 Mid 進場的報酬率%。
  「如果只漲一半」「如果晚三個月才到」都直接查表，不用重跑。

## 離線重跑（可覆核性）

每次線上執行會把市場快照存進 snapshots/。之後用 --snapshot 指定該檔
即可完全離線重現同一份報告（逐位元相同）：

    option-chaser TLT --target-price 110 --target-month 2027/12 \
        --snapshot snapshots/TLT_xxxx.json

## 常用參數（中文對照）

    --target-month 年月    目標年月，2028/1、2028/01、28/1、28/01 皆可
    --iv-shifts CSV        IV 情境，預設 -0.2,0,0.2（0 必含）
    --min-return X         要求報酬上限 L3 = 基準估值/(1+X)
    --max-spread-pct / --spread-floor   品質標示門檻，不是硬過濾——未平
                          倉量、成交量、買賣價差寬度皆不影響候選是否
                          入選，只決定每個候選上的 ⚠ 標示，spec #61
    --delta-bands A,B      |Delta| 分級門檻，預設 0.35,0.65
    --top N                每級距/清單候選數，預設 3
    --matrix-all           每個候選都附矩陣（預設只有各級首選）
    --md 路徑              報告另存檔案
    --force                允許方向相反的劇本

## 已知模型限制（讀數字前必知）

- 無股利調整（q=0）：高殖利率標的（如 TLT 約 4%）的 call 殘值會
  「系統性偏樂觀」、put 偏保守。深價內長天期偏差最大，
  「保守底線」行是對這個偏誤的天然防線。
- IV 假設恆定到日曆錨點日；實際 IV 會變，三情境（±20%）是覆蓋手段。
- 報價為 yfinance 延遲資料（約15分鐘），volume=0 的合約會加註
  「報價新鮮度存疑」。
- 延遲到達情境（韌性向量 S4 晚30天／S5 晚90天）假設股價沿現價到目標價
  「線性內插」到達，屬模型假設，不是市場預測。
- 模型估計非保證成交價格；本工具不構成投資建議。

## Web 前端

互動網頁版是獨立的 Vite＋React（TypeScript）前端，後端走 Python
serverless API（FastAPI，直接呼叫本 `option_chaser` 引擎）——完整架構、
Vercel 部署步驟、接上 Neon Postgres 持久化的方式見 `docs/deploy-vercel.md`。

    npm install
    npm run dev                 # 前端開發伺服器，http://localhost:5173
    PYTHONPATH=. .venv/bin/python -m pytest    # 後端／API 測試

網頁版開啟即是劇本庫（建立／列出／封存劇本，最上層可一鍵全部刷新），
詳細頁流程：摘要 → baseline 到期日第 1 名候選的主 Heatmap → Long Call
追平價格 → 到期日選單＋單期 Top 10 → 候選池診斷 → 收合的「進階區」
（重排版的分析報告、Spread 淨成本走勢圖、原始快照資料＋CSV 下載）。
網頁版本身不做任何金融公式運算——畫面上每個數字都經 HTTP API
（`store.serialize_result`）取自與 CLI 相同的引擎。劇本資料正式環境
存在 Neon（透過 Vercel Storage 掛的 Postgres）；沒接資料庫時，新建的
劇本只存在 serverless 函式的記憶體裡，重新部署就消失——確認資料庫是
否真的接上，見 `docs/deploy-vercel.md`（`GET /api/health` 的 `storage`
欄位）。

（重寫期間曾有一版 Streamlit 前端雛型 `webapp/`，已於 Cutover 移除；
現在這個 Vite／React 前端是唯一的正式前端。）
