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

    option-chaser NVDA --target-price 220 --target-date 2026-09-30

## Re-run offline from a snapshot

    option-chaser NVDA --target-price 220 --target-date 2026-09-30 \
        --snapshot snapshots/NVDA_xxxx.json

## Strategies

    --strategy long-call          (default) bullish single leg
    --strategy long-put           bearish single leg
    --strategy bull-call-spread   bullish debit vertical (exhaustive same-expiry pairs)
    --strategy bear-put-spread    bearish debit vertical

Direction guard: bullish strategies need target > spot, bearish need target < spot
(override with --force). Band-first candidates include a price×date P/L matrix
(11 price rows × up to 7 date columns; add --matrix-all for every candidate).

## Removed in v2

    --min-days-after / --delay-days and the stress-test section are gone —
    the matrix supersedes them. Manage your own expiry buffer via --min-expiry.

## Key flags

    --min-expiry DATE     absolute expiry floor (expiry >= target-date is always enforced)
    --iv-shifts CSV       IV scenarios, default -0.2,0,0.2 (0 always included)
    --min-return X        L3 price ceiling = baseline value / (1+X)
    --max-spread-pct / --spread-floor / --min-oi / --min-volume   tradeability gates
    --delta-bands A,B     |Delta| banding thresholds, default 0.35,0.65
    --matrix-all          matrix on every candidate
    --md PATH             also write the report to a file

Snapshots are schema v2 (calls + puts). v1 snapshots must be re-fetched.

## Tests (all offline)

    python -m pytest

Specs: docs/superpowers/specs/2026-07-15-option-chaser-mvp-design.md (v1),
docs/superpowers/specs/2026-07-19-option-chaser-v2-design.md (v2)

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
    option-chaser TLT --target-price 110 --target-date 2027-12-31

    # 看漲垂直價差（同到期日全配對窮舉，降低成本、獲利封頂）
    option-chaser TLT --strategy bull-call-spread --target-price 110 --target-date 2027-12-31

    # 看跌單腿：TLT 在 2027-06-30 前跌到 70
    option-chaser TLT --strategy long-put --target-price 70 --target-date 2027-06-30

    # 看跌垂直價差
    option-chaser TLT --strategy bear-put-spread --target-price 70 --target-date 2027-06-30

方向守衛：看漲策略要求目標價 > 現價、看跌策略要求目標價 < 現價，
方向相反時會擋下並提示加 --force 才放行。

## 怎麼讀報告

- 過濾統計：整條鏈刷掉多少、為什麼刷（到期日/報價/IV/流動性/價差過寬）
- 單腿分三級距（依 |Delta|）：保守型（深價內，容錯大）、平衡型、
  積極型（價外，高槓桿）；價差為單一排名清單
- 每候選：Bid/Mid/Ask（含每張金額）、Breakeven、IV 三情境估值
  （估值+損益+報酬率）、買價指引天花板（超過就警示）
- P/L 矩陣：列 = 股價（<現價>/<目標> 有標記）、欄 = 日期（* 為劇本日、
  末欄為到期日 payoff）、格值 = 以 Mid 進場的報酬率%。
  「如果只漲一半」「如果晚三個月才到」都直接查表，不用重跑。

## 離線重跑（可覆核性）

每次線上執行會把市場快照存進 snapshots/。之後用 --snapshot 指定該檔
即可完全離線重現同一份報告（逐位元相同）：

    option-chaser TLT --target-price 110 --target-date 2027-12-31 \
        --snapshot snapshots/TLT_xxxx.json

## 常用參數（中文對照）

    --min-expiry 日期      到期日下限（到期日 >= 劇本日 恆強制）
    --iv-shifts CSV        IV 情境，預設 -0.2,0,0.2（0 必含）
    --min-return X         要求報酬上限 L3 = 基準估值/(1+X)
    --min-oi / --min-volume / --max-spread-pct / --spread-floor   可交易性門檻
    --delta-bands A,B      |Delta| 分級門檻，預設 0.35,0.65
    --top N                每級距/清單候選數，預設 3
    --matrix-all           每個候選都附矩陣（預設只有各級首選）
    --md 路徑              報告另存檔案
    --force                允許方向相反的劇本

## 已知模型限制（讀數字前必知）

- 無股利調整（q=0）：高殖利率標的（如 TLT 約 4%）的 call 殘值會
  「系統性偏樂觀」、put 偏保守。深價內長天期偏差最大，
  「保守底線」行是對這個偏誤的天然防線。
- IV 假設恆定到劇本日；實際 IV 會變，三情境（±20%）是覆蓋手段。
- 報價為 yfinance 延遲資料（約15分鐘），volume=0 的合約會加註
  「報價新鮮度存疑」。
- 模型估計非保證成交價格；本工具不構成投資建議。

## Web GUI

    pip install -e ".[gui]"
    streamlit run webapp/app.py        # http://localhost:8501

或 Docker：

    docker compose up -d               # http://localhost:8501（PORT 環境變數可改）

網頁只需四項輸入（標的／目標價／到達日期／策略勾選，預設 Long Call
+ Bull Call Spread），一次抓取市場資料後同一快照分析所有勾選策略，
輸出跨策略比較表、各策略前三名候選與價格×日期 P/L Heatmap。
進階參數一律採用 CLI 預設值；方向不合的策略會被跳過並提示，
GUI 不提供 --force。所有計算皆由與 CLI 相同的引擎完成。
