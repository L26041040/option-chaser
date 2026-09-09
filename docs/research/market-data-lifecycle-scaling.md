# Market Data Lifecycle & Scaling

研究日期：2026-09-03。對應 **OPTION-MARKET-DATA-RESEARCH-001**。

**基準**：`origin/master` HEAD `864dd5c`（工作樹 `b41ad1c`，已用
`git diff --stat` 核對兩者 production code 逐位元相同，差異只有
`CLAUDE.md` 與 session-history）。

**本輪範圍**：只做盤點、量測與 pattern 研究。**不設計最終架構、不寫
spec、不開票、不改任何 production code。** 文中任何「應該」都只是把
選項與代價攤開，決策一律留給後續 `/wayfinder`。

**證據分級**：本文標示 **【一手實測】**（我在本輪對真實端點／真實
程式碼實際跑出來的數字）、**【官方文件】**（vendor／平台官方文件，附
存取日期）、**【repo 紀錄】**（本 repo 既有文件或 commit 訊息宣稱的
事實，我未獨立重驗）、**【推估】**（模型推算，非量測）。

---

## 1. Executive Summary

### 1.1 十個必須先知道的事實

1. **Treasury、Dividend、Historical IV 三條線今天已經是 shared-data
   架構。** 它們各自有 Neon 為底、per-key、跨 invocation、跨使用者的
   快取（`rate_cache` 全站單列／`dividend_cache` per-symbol／
   `treasury_year_cache` per-year／`contract_iv_history` per-contract／
   `iv_backfill_runs` per-symbol），全部是 market-day 或永久語意。
   **這三條不是本輪的問題。**

2. **Option Chain 是唯一沒有任何共用機制的資料流。** ADR-0001 明文
   刪除了跨 invocation 的 chain 快取，去重範圍只剩「單一 invocation
   內同 symbol 的多個劇本」。100 個使用者同時看 TLT ＝ **100 次**
   `cdn.cboe.com` 抓取。

3. **`cdn.cboe.com` 會 rate limit，而且我在本輪真的撞到了。**
   【一手實測】HTTP **429**，`retry-after: 34`，`server: cloudflare`。
   這是本 repo 從未記錄過的事實。

4. **而 Cboe adapter 完全沒有處理 429。** `data/cboe.py:102` 一律
   `except Exception → FetchError`，不看 status、不讀 `retry-after`、
   無 backoff、無 circuit breaker。唯一的備援 `data/yf.py` 在
   production **結構上不可達**（`yfinance` 不在 Vercel 會裝的
   `[project] dependencies` 裡）。**Cboe 一被限流 ＝ 核心功能全站立即
   中斷，且沒有任何自動復原機制。**

5. **真正會先撞牆的不是 vendor quota，是 Neon 儲存。**【一手實測】用
   真實 TLT 鏈跑完整三 family 分析，`results.view` JSONB 單列
   **12.18 MiB**（V1 只有 vertical-spread 時是 0.92 MiB，**13.5 倍**），
   其中 **96.4%** 是 `results[call-fly].all_candidates`（74,011 筆，
   11.78 MiB）。`results`／`snapshots` **完全沒有 retention 機制**。
   Neon Free 每 project **0.5 GB**【官方文件】→ **約 42 次（未壓縮）
   到 402 次（zlib-6 上界）刷新就把免費額度寫滿**；Postgres TOAST 的
   預設壓縮（pglz／lz4）弱於 zlib-6，實際值會更靠近低端。

6. **沒有任何 user 隔離（issue #59 仍 open）**，`api_app/main.py` 全檔
   零 `Depends`／零 auth。因此「開站刷新」＝`list_scenarios()` 回傳
   **資料庫裡全部劇本** → 前端把**全部** id 送進 `runBatch`。任何一個
   使用者開站，就刷新全站所有人的劇本。這讓所有負載公式變成 **O(U²)**。

7. **`REFRESH_RUN_GROUP_LIMIT = 1`（`main.py:80`）讓一輪刷新的
   serverless invocation 數等於 distinct symbol 數。** 這是 2026-08-26
   為了「逐張解鎖」的產品需求刻意加的，不是 bug，但它使得
   「Refresh Run 把一輪收進一次 invocation」這件事在實務上不再成立。

8. **本 repo 對 Vercel 60 秒上限的認知已經過時。** CONTEXT.md 與
   CLAUDE.md 多處寫「60 秒函式硬性上限」；Vercel 官方文件（存取
   2026-09-03）指出啟用 fluid compute（2025-04-23 起新專案預設開啟）
   後 **Hobby 的 default 與 maximum 都是 300s**。60 秒是本專案自己在
   `vercel.json` 設的 `maxDuration: 60`。

9. **ADR-0001 的一項前提已被平台改變推翻。** ADR 寫「跨 invocation
   **沒有共享記憶體**」；Vercel fluid compute 官方文件明文：「multiple
   invocations can share the same physical instance (a global state/
   process) concurrently」。行程內快取現在是**可能有效但無保證**的，
   而不是「結構上不可能」。（ADR 的**結論**——不要把 chain 寫進
   Postgres——是否仍然正確是另一個問題，見 §8.3。）

10. **請求量今天跟著「使用者數 × 系統內 symbol 數」成長，而成熟系統
    讓它跟著「unique active symbols × refresh frequency」成長。** 這正
    是本輪委託問題的答案，詳見 §7。

### 1.2 最短路徑的結論

| 資料流 | 今天是不是 shared？ | 最大問題 | 分級 |
|---|---|---|---|
| Treasury | ✅ 是（market-day，全站一筆） | 每市場日第一批並發請求會 stampede（無 single-flight）；抓取在使用者關鍵路徑上，最壞 3×15s | P1 |
| Dividend | ✅ 是（per-symbol，market-day） | 同上的 stampede；primary source 的 `robots.txt` 是 `Disallow: /` | P1 |
| **Option Chain** | ❌ **否** | 零快取 × 上游會 429 × 429 未處理 × 備援不存在 | **P0** |
| （非 vendor，但更早撞牆）Neon 儲存 | — | 12.18 MiB/刷新 × 無 retention × Free 0.5 GB | **P0** |
| （非 vendor，但更早撞牆）無 user 隔離 | — | 開站 ＝ 刷新全站，負載 O(U²) | **P0** |

---

## 2. Current-State Data Flow

完整圖見 `market-data-current-state-map.md`。這裡只列與 scaling 直接
相關的骨架。

### 2.1 三個 Refresh Trigger 各自產生什麼

| Trigger | 前端動作 | 送出的範圍 | HTTP 請求數 | Chain 抓取數 |
|---|---|---|---|---|
| 開站 | `reloadAndRefresh()`（`src/App.tsx:266`） | `listScenarios()` 的**全部**未過期劇本（無 user 過濾） | D（distinct symbol 數） | D |
| 頂部刷新鈕 | 同上 | 同上 | D | D |
| 建立新劇本 | `runBatch([created.id])`（`src/App.tsx:348`） | 只有新劇本 | 1 | 1 |
| （非 Trigger）卡片重試／詳細頁刷新／編輯後 | `refreshOne(id)` | 單一劇本 | 1 | 1 |

`D` 之所以等於 HTTP 請求數：`refresh_run` 每次回應最多完成一個 symbol
分組（`main.py:1083`，`REFRESH_RUN_GROUP_LIMIT = 1`），其餘進
`remaining`，前端 Continuation 迴圈（`src/App.tsx:196-253`）再打一次。

### 2.2 一次 scenario 分析的外部呼叫帳本

`service._analyze()` 每次分析各呼叫 **一次** `_resolve_rates`
（`service.py:1170`）與 **一次** `_resolve_q`（`service.py:1202`），
兩者都在 subtype 迴圈**之前**（`service.py:1259-1261`），因此不會隨
family 數量增加。

| 輸入 | 快取命中時的外部呼叫 | 快取未命中時 |
|---|---|---|
| Option chain | **不存在快取，恆為 1 次** | 1 次（1–5.6 MB） |
| 無風險利率 | 0 | 1–3 次 HTTP（CSV→XML→前一年 CSV），每次 timeout 15s |
| 股利 q | 0 | 1–4 次 HTTP（Yahoo→[FMP]→Nasdaq stocks→Nasdaq etf） |

因此**在快取全熱的穩態下，一次 scenario 刷新的外部請求數恰好是 1，
而那 1 次就是 Cboe chain。**

### 2.3 每次刷新寫進 Neon 的東西

`_refresh_and_save()`（`main.py:914-987`）每個劇本各寫：

- `save_result(ResultRecord(view=...))` — 完整 view JSONB
- `save_snapshot(...)` — 完整 chain snapshot dict
- `append_event(ANALYSIS_COMPLETED)`

`analyzed_at` 來自快照的 `fetched_at`（秒級 UTC 時間戳），每次抓取都
不同，因此每次刷新都是**新的一列**，不是覆寫。

---

## 3. Treasury

### 3.1 來源與端點

| 項目 | 內容 | 依據 |
|---|---|---|
| 主源 | `home.treasury.gov` Daily Treasury Par Yield Curve Rates，當年 CSV | `data/treasury.py:34-37` |
| 備援 1 | 同站當年 XML | `data/treasury.py:38-40` |
| 備援 2 | 前一年 CSV（年初空檔） | `data/treasury.py:82-84` |
| 備援 3 | 本地檔案快取（7 天窗） | `data/treasury.py:155-180` — **production 死碼**，見 §3.5 |
| 最終 fallback | 引擎固定 4%，報告參數行標示 | `service.py:1191` |
| timeout | 15.0s / 次 | `data/treasury.py:45` |

【一手實測 2026-09-03】該 CSV 端點 `HTTP 200`、13,799 bytes、169 行
（含表頭，即 2026 年至今 168 個交易日）、0.66s、`cache-control:
private, no-cache, must-revalidate`、`server: nginx` / `x-generator:
Drupal 10`。

### 3.2 兩條完全不同的 lifecycle

本 repo 對 Treasury 有**兩條互不相干**的取數路徑，這是本節最容易被
搞混的地方：

| | **Live 估值路徑** | **Point-in-Time 路徑** |
|---|---|---|
| 用途 | 今天這次分析的期限對齊利率 | Historical IV reconstruction 逐日回算 |
| 入口 | `service.default_rate_curve_loader` | `treasury_data.fetch_curve_range` |
| 取什麼 | **只要最新那一列** | 一段區間**全部**資料列 |
| 快取層 | `api_app/rate_cache.py` | `api_app/treasury_cache.py` |
| Neon 表 | `rate_cache`（單列 `id INTEGER PRIMARY KEY DEFAULT 1`） | `treasury_year_cache`（`PK year`） |
| 新鮮度 | `market_day == today` | 過去年份**永久**；當年 market-day |
| 誰觸發 | 每次 scenario 分析 | 只有 `/iv-history` |

`treasury_year_cache` 的 PIT 安全性是靠**鍵設計**鎖死的，不是靠呼叫端
小心：對歷史日期 D 的查詢結構上只可能被 D 所在年份的區塊滿足
（`treasury_cache.py:60-68`）。這個設計是正確的，本輪無異議。

### 3.3 Request 粒度

- **呼叫粒度**：每次 scenario 分析一次（不是 per symbol、不是 per
  HTTP request）。
- **實際外部請求粒度**：**每市場日全站約 1 次**——`_success_is_fresh`
  只比對 `market_day == today.isoformat()`（`rate_cache.py:59-64`），
  與時間差無關。
- **失敗**：5 分鐘去重窗（`_FAILURE_MAX_AGE`）＋ 7 天 stale fallback
  （`_STALE_FALLBACK_MAX_AGE`）。`market_day` 只在真正「新鮮直抓成功」
  時前進（`rate_cache.py:121`），因此暫時性失敗不會把當天鎖死。

### 3.4 Cold start / restart

快取在 Neon，**不受 serverless cold start 影響**。這一點與下面的檔案
快取形成對比。

【一手實測 2026-09-03】production `GET /api/health` 回傳：

```json
{"storage":"postgres",
 "rate":{"fetched_at":"2026-09-03T05:00:52+00:00","ok":true,
         "note":"Treasury 曲線 2026-09-02",
         "last_success_at":"2026-09-03T05:00:52+00:00"}}
```

當日只有一筆成功抓取紀錄——market-day 快取確實在 production 生效。

### 3.5 一個已經死掉、但沒有人記錄的層

`data/treasury.py` 的本地檔案快取（`snapshots/treasury_curve_cache.json`）
在 Vercel 上**完全無效**：serverless 檔案系統唯讀，`_write_cache` 的
`except OSError: pass`（`data/treasury.py:142-143`）把失敗吞掉，於是
「(b) 抓取失敗 → 快取在 7 日曆日內 → 用快取」這條 fallback 在
production 永遠走不到。`.vercelignore` 也明確排除了 `snapshots`。

**這不是 bug**（Neon 那層做了同樣的事，而且做得更好），但它是誤導：
`load_rate_curve` 的 docstring 宣稱三層 fallback，實際在 production
只有兩層。同樣的狀況也存在於 `data/dividends.py`。

### 3.6 同一天會不會重抓？historical 與 current 是不是不同 lifecycle？

- 同一天重抓：**穩態下不會**。例外有二：(a) 抓取失敗後過了 5 分鐘的
  去重窗；(b) **stampede**（見下）。
- historical vs current：**是兩條不同的 lifecycle**，見 §3.2。它們甚至
  打不同的解析函式（`parse_treasury_csv` vs `parse_treasury_csv_rows`）。

### 3.7 委託問題：同一天 1,000 個使用者，會對 Treasury 發多少 request？

**下界 = 1**（全站每市場日一次）。

**上界**：`cached_loader`（`rate_cache.py:86-153`）是 **read → fetch →
write** 的 cache-aside，**沒有任何 single-flight／lock**。在「今天第一
次有人來」的那個瞬間，所有在第一筆 `save_rate_cache()` 落地之前抵達的
並發請求，**每一個都會各自打一次 Treasury**。

因此上界 = **該時刻的並發冷請求數 C**。C 取決於：

- 使用者是否集中在開盤前後同時開站（真實產品裡：會）
- Neon 寫入延遲（幾十 ms 量級）＋ Treasury 回應時間（實測 0.66s）——
  **視窗大約是 0.7 秒**，這段時間內抵達的請求全部 miss

**無法給出精確值的原因**：C 是使用者到達過程的函數，不是程式碼常數。
合理的估計方式是：若 1,000 個使用者的開站時刻在早上 9:25–9:35 的
600 秒內大致均勻分布，則 0.7 秒視窗內期望有 `1000 × 0.7/600 ≈ 1.2` 個
並發冷請求 → 期望上界約 **2–3 次**【推估】。若使用者集中在同一分鐘
（例如推播通知後），視窗內可能有 10–20 個 → 上界 **10–20 次**【推估】。

**結論：Treasury 的請求量不是 scaling 問題**（絕對量太小，Treasury 是
政府公開靜態檔案 CDN）。真正的問題是 §9 列的兩件事：stampede 期間
每個 miss 都要在**使用者的關鍵路徑上**等最壞 3×15s＝45s，而
`REFRESH_RUN_BUDGET` 只有 45s。

### 3.8 官方限制

【官方文件，存取 2026-09-03】
`https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics`：

> "The par yields are derived from input market prices, which are
> indicative quotations obtained by the Federal Reserve Bank of New York
> at approximately 3:30 PM each business day."

→ **資料每個營業日只更新一次，約 15:30 ET。** 這在數學上就把「正確的
刷新頻率」上限釘死在**每營業日一次**，本 repo 的 market-day 語意與它
完全吻合。

該頁面**未公布**任何 rate limit、quota 或 API 使用條款。我在本輪未
觸發任何限流。

---

## 4. Dividend

### 4.1 抓的到底是什麼

**抓的是原始現金分配歷史（金額＋除息日），不是算好的殖利率。**

- `parse_yahoo_dividends` 讀 `events.dividends`，**刻意不讀**
  `events.capitalGains`（只計經常性現金分配，`data/dividends.py:13-17`）。
- 回傳型別 `DividendHistory`（`distributions` 清單＋`as_of`＋`source`＋
  `stale`）。

**valuation 真正需要的 canonical input 是 `q`（連續股利殖利率）**，由
`_resolve_q` 在分析當下用**這次快照自己的 spot** 現算
（`service.py:1235`，`dividends.compute_q`）。

**刻意不快取算好的 q**（`service.py:49-52` 引研究 §7.5：快取比例會凍結
一個過期的價格基準）。這是正確的設計，本輪無異議——它也正好讓
per-symbol 快取可以安全地跨使用者、跨劇本共用：快取的是「這個標的過去
配了多少錢」這個客觀事實，不是任何人的估值中間值。

### 4.2 來源鏈

| 順位 | 來源 | 需金鑰 | 依據 |
|---|---|---|---|
| 1 | `query2.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&...&events=div,splits,capitalGains` | 否 | `data/dividends.py:39-40` |
| 2 | `financialmodelingprep.com/stable/dividends` | **是**（`FMP_API_KEY`），未設定即跳過 | `data/dividends.py:41-42, 85-93` |
| 3 | `api.nasdaq.com/api/quote/{sym}/dividends?assetclass=stocks` 然後 `etf` | 否 | `data/dividends.py:43, 95-101` |

【一手實測 2026-09-03】Yahoo 端點 `HTTP 200`、28,194 bytes、
`cache-control: public, max-age=10, stale-while-revalidate=20`、
`server: ATS`。Nasdaq 端點 `HTTP 200`、32,990 bytes、
`cache-control: max-age=0, no-cache, no-store`、`server: Kestrel`。

### 4.3 Refresh trigger 與 scope

- **Trigger**：每次 scenario 分析（`_resolve_q`）。
- **Scope**：per-symbol。
- **同 symbol 會不會重抓**：不會——`dividend_cache` 以 `symbol` 為
  primary key，`market_day == today` 就命中（`dividend_cache.py:42-43`）。
- **不同 scenario 同 symbol**：天生共用（鍵裡沒有 scenario）。
- **不同 user 同 symbol**：**今天天生共用**（表裡沒有 user 欄位）。
  若日後加入 user 隔離，**這張表不應該加 user 欄位**——它快取的是
  公開市場事實，不是任何人的私有資料。

### 4.4 Stale 的實際影響

| 狀態 | 對估值的影響 | 依據 |
|---|---|---|
| 有 fresh history | 正確 q | — |
| 有 stale history（≤ 90 天） | 幾乎無影響——分配是月頻事件，90 天窗內漏掉的最多是一次配息 | `dividend_cache.py:27-31` |
| 完全沒有（`q_by_symbol=None`） | 退回 **q=0**，`calibrate_leg` 第 4 層 | `service.py:1208-1213` |

**q=0 的代價是巨大的**【repo 紀錄】：
`docs/research/heatmap-valuation-method-selection.md` 記載 q=0 歐式在
「今天 × 現價」那格印出 **+81.9%**，誠實答案是 **−11.5%**；
`historical-iv-reconstruction-corrected-calibration-results.md` 的 TLT
q ablation：q=0 讓 MAE 從 0.0089 惡化到 0.0493（**+4.05 vol pts**）。

→ **90 天 stale window 是被實證支持的正確取捨**，遠好過 7 天。

### 4.5 委託問題：Dividend 適不適合「全 universe 每日 preload」？

**不適合，三個獨立理由：**

1. **Universe 不封閉。** `symbol` 的唯一約束是
   `^[A-Za-z.\-]{1,10}$`（`main.py:99`）——使用者可以建立任何代號的
   劇本。沒有一份「全 universe」清單可以 preload。要 preload 就得先
   定義 universe，而定義 universe 本身是一個產品決策（要不要限制使用者
   只能選某個清單裡的標的？）。
2. **Vercel Hobby 的 cron 一天只能跑一次**【官方文件】，且觸發時間
   有 ±59 分鐘誤差（見 §6.3）。這對「每日 preload」勉強夠用，但沒有
   任何補救餘裕。
3. **價值不對稱。** 實際被使用的 symbol 是**極度長尾**的：一個標的
   一天只需要抓一次，而 cache-aside 的成本只有「每個活躍 symbol 每天
   第一個使用者多等一次 HTTP」。Preload 全 universe 是為了消除這一次
   等待而付出「抓幾千個沒人看的標的」的代價。

**成熟替代模式**（本節只研究、不裁定，評估見 §8）：

| Pattern | 解決什麼 | 對 Dividend 的適用性 |
|---|---|---|
| Global per-symbol cache-aside | 同 symbol 不重抓 | **已經做到了**（`dividend_cache`） |
| TTL + freshness metadata | 知道資料多舊 | **已經做到了**（`market_day`／`stale`／`as_of`／`q_note`） |
| Single-flight / request coalescing | 冷啟動 stampede | **缺**——這是 Dividend 唯一真正缺的東西 |
| Stale-while-revalidate | 使用者不必等 | 缺；但因為 stale 窗是 90 天、資料是月頻，SWR 的收益很高、風險極低 |
| Hot-symbol warming | 熱門標的永不 cold miss | 有價值，但受 Hobby cron 一天一次限制 |
| Negative cache | 不存在／無配息的標的不要每天重試 | **語意上已經有**——`compute_q` 對空 `distributions` 自然回 0.0 且標 fresh（`service.py:1217-1219`），這是正確答案不是降級 |

### 4.6 官方限制 / 治理風險

**Yahoo（primary）**：這是驅動 finance.yahoo.com 網頁的**內部端點**，
沒有公開 API 文件、沒有 SLA、沒有公布的 quota。

【一手實測 2026-09-03】`https://query2.finance.yahoo.com/robots.txt`：

```
User-agent: *
Disallow: /
```

**整個 host 對自動化存取是 disallow 的。** 這是可驗證的一手事實，也是
本 repo 從未記錄過的治理風險。它不代表「會被封鎖」，但它代表：
(a) 這條依賴隨時可能被單方面斷掉，(b) 若產品要走向商業化，這是需求方
必須自己裁決的合規問題。**本輪不裁定，列入 §10。**

**FMP**：需要金鑰。【存取 2026-09-03】
`https://site.financialmodelingprep.com/developer/docs/pricing` 對本
沙箱回 **HTTP 403**，我**沒有**取得官方限額數字。本 repo 現況是
`FMP_API_KEY` 未設定 → 這一棒直接跳過，因此**目前不影響任何行為**。

**Nasdaq**：`api.nasdaq.com` 同樣是網站內部端點，無公開文件、無 SLA。

---

## 5. Option Chain

**這是本輪最重要的一節。**

### 5.1 現況

| 項目 | 內容 | 依據 |
|---|---|---|
| 主源 | `https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json` | `data/cboe.py:21` |
| 粒度 | **整個 symbol 的全鏈**，一次 GET 回全部到期日（含 LEAPS），**無法只要某個到期日** | `data/cboe.py:21, 95-105` |
| 延遲 | 延遲報價（Cboe 官方 "delayed_quotes"），非即時 | 端點路徑本身 |
| 備援 | yfinance | **production 不可達**，見 §5.5 |
| 自訂 | Market Data App `options/chain`（無篩選＝全鏈） | `data/marketdata.py:34, 185-195` |
| timeout | 15.0s | `data/cboe.py:22` |
| **快取** | **無** | ADR-0001 |

### 5.2 量體（【一手實測 2026-09-03】，用 repo 自己的 adapter 解析）

| Symbol | vendor payload | 合約數 | 到期日數 | 存進 `snapshots` 的 JSON |
|---|---|---|---|---|
| TLT | 1,072,425 B (1.02 MiB) | 2,414 | 29 | 507,552 B (0.48 MiB) |
| SPY | 5,592,700 B (5.33 MiB) | 12,534 | 34 | 2,668,703 B (2.55 MiB) |

12 檔流動性佳的 ETF／大型股一次抓完共 **24,996,146 B**，平均每檔
**2.08 MB**【一手實測】。以下模型用 **B̄ ≈ 2 MB** 作為「活躍 symbol 的
平均鏈大小」，並註明這是流動性偏高的樣本、長尾小型股會更小。

### 5.3 同 symbol 的多 scenario 會不會重抓？

**Run 內不會，Run 外一定會。**

`refresh_run` 先依 symbol 分組，每個 distinct symbol 只呼叫一次
`_fetch_chain()`（`main.py:1073-1096`），純記憶體 dict。這是
ADR-0001 定義的唯一去重範圍。

但因為 `REFRESH_RUN_GROUP_LIMIT = 1`（`main.py:80`），**一次 invocation
就只處理一個分組**——所以「Run 內去重」在實務上精確地等同於「同一個
symbol 底下的多個劇本共用一次抓取」，不多也不少。

### 5.4 多使用者同時刷新同 symbol 會發生什麼？

**各抓各的。** 沒有快取、沒有 single-flight、沒有任何跨 request 的協調
機制。

100 個使用者同時刷新 TLT：
- **100 次** `cdn.cboe.com` GET
- **≈ 107 MB** 從 Cboe 拉進 Vercel（100 × 1.02 MiB）
- **100 次** 各自獨立的 Vercel function invocation
- 全部落在同一個 region（`iad1`，`vercel.json` 未設 `regions`，預設
  單一 region）

### 5.5 ⚠ P0：Cboe 會 429，而程式碼完全沒有處理

**【一手實測 2026-09-03】** 在本輪早期的探測中，對
`cdn.cboe.com/api/global/delayed_quotes/options/{TLT,SPY,AAPL,NVDA}.json`
連續快速發出請求後收到：

```
HTTP/2 429
retry-after: 34
content-type: text/plain; charset=UTF-8
content-length: 17
server: cloudflare
cf-ray: a356e2fe39d5e647-IAD
```

**這是本 repo 從未記錄過的事實。** `data/cboe.py` 的 docstring 只寫
「此端點無官方 API 文件、無 SLA」，沒有提到它**會主動限流**。

**我沒能精確定出門檻**（誠實揭露）：後續控制實驗中，20 次 Range 請求
（1 秒間隔）、10 次全量請求（1 秒間隔，共 18.9 MB）、4／8 並發、
12 並發全量（3.16 秒內 25.0 MB）**都沒有再觸發 429**。所以這是一個
**滑動視窗式、未公布門檻**的 Cloudflare 限流，我只能確定「它存在、
會回 `retry-after: 34`、而且在很低的請求量下就被我撞到了」。

**為什麼這是 P0——不是因為機率，是因為後果：**

```python
# option_chaser/data/cboe.py:95-105
def fetch_chain(symbol: str, http_get=_http_get) -> ChainSnapshot:
    try:
        payload = json.loads(http_get(_URL.format(symbol=symbol.upper())))
        return map_payload(symbol, payload, fetched_at)
    except FetchError:
        raise
    except Exception as e:  # ← 429 走這條
        raise FetchError(f"Cboe 抓取失敗（{symbol}）: {e}") from e
```

1. `urlopen` 對 429 拋 `HTTPError` → 被 `except Exception` 吞成一個
   **無差別的 `FetchError`**。
2. **不讀 `retry-after`**、**不 backoff**、**不 circuit break**。
3. `service.fetch_chain`（`service.py:1329-1350`）接到 `FetchError` →
   `from .data import yf` → `yf.fetch_chain` → `import yfinance`
   （`data/yf.py:51`）→ **`ImportError`**（`yfinance` 只在
   `pyproject.toml:30` 的 `yf` extra；`[project] dependencies`
   ＝`pyproject.toml:12-15` 只有 `fastapi`／`psycopg[binary]`／
   `tzdata; platform_system == 'Windows'`，而 Vercel 只裝
   `dependencies`——這一點是 repo 自己在 `pyproject.toml:6-10` 與
   `requirements.txt:1-8` 明文記錄的實測結論）→ 被 `data/yf.py:63`
   的 `except Exception` 收斂成另一個 `FetchError`。
4. 使用者看到 `stage: "fetch"` 的「抓不到 {symbol} 的報價」。
5. **前端會怎麼反應？** 使用者按「重試」→ 再打一次 → 又 429 →
   多個使用者同時重試 → **retry storm**，把限流窗口一直續下去。

**對照 §5.4：在有共用機制之前，使用者一多，觸發 429 的機率會隨
`U × r × D` 線性上升，而觸發之後系統沒有任何自動復原路徑。**

### 5.6 Market Data App 作為自訂 chain 來源的成本

【官方文件，存取 2026-09-03】`https://www.marketdata.app/docs/api/options/chain`：

> 即時／15 分鐘延遲資料："1 credit" — "Per option symbol."
>
> 帶 `date` 參數的歷史查詢："1 credit per 1000 option symbols returned
> in the response."

`data/marketdata.py:34` 的 `_CHAIN_URL` **不帶任何篩選參數**，回的是
全鏈。因此：

| 動作 | Credit 成本【推估，基於官方計價 × 實測合約數】 |
|---|---|
| 抓一次 TLT 全鏈（即時路徑） | **≈ 2,414 credits** |
| 抓一次 SPY 全鏈（即時路徑） | **≈ 12,534 credits** |
| 抓一天份 TLT 歷史 surface（backfill 路徑，帶 `date`） | ≈ 1–3 credits |

【官方文件】`https://www.marketdata.app/docs/api/rate-limits`：
Free Forever **100 credits/day**；Starter 10,000/day；Trader
100,000/day；Quant 10,000/**minute**；Prime 100,000/minute。
"Only status 200/203 responses consume credits."

→ **使用者若在 Settings 把 Market Data 設成自訂＝Market Data App，
一次刷新就會燒掉 Free 全天額度的 24 倍（TLT）到 125 倍（SPY）。**
這條路徑在 Free 與 Starter 上實務不可用。本 repo 從未記錄過這個成本
模型。（Historical IV 那條路徑不同——它走 `date` 參數與
`options/quotes`，成本合理，見 §6.5。）

### 5.7 委託問題：1,000 個使用者裡 100 人關注 TLT，理想 request 數是多少？

**理想值接近「1 次，或每個 freshness 窗一次」，不是 100 次。**

理由是資料本身的性質，不是效率偏好：

1. **這份資料對所有人完全相同。** `cdn.cboe.com/.../TLT.json` 是一個
   無參數、無 per-user 內容的公開 CDN 物件。100 個使用者拿到的是
   **逐位元相同**的 bytes。
2. **它本來就是延遲報價。** 端點路徑就叫 `delayed_quotes`。在一份
   已經延遲了的資料上，再多一個 30–60 秒的共用窗，**相對新鮮度損失
   是二階的**。
3. **成熟系統的通則**：可快取性由「資料的識別性」決定，不由「請求者
   的數量」決定。同一個 `(symbol)` key、同一個時間桶 → 一份資料。

成熟系統通常怎麼做（研究，不裁定）：

| 做法 | 誰在用 | 對應到本專案 |
|---|---|---|
| **Shared read-through cache with short TTL** | 幾乎所有 market data 中介層 | per-symbol chain cache，TTL 以秒計 |
| **Single-flight / request coalescing** | Go `singleflight`、Guava `LoadingCache`、Rails `race_condition_ttl` | 同一個 (symbol, 時間桶) 同時只有一個 upstream fetch，其餘等它 |
| **Stale-while-revalidate** | HTTP `Cache-Control: stale-while-revalidate`（Yahoo 自己就在用，見 §4.2 實測） | 過期後先回舊的，背景更新 |
| **Hot/cold split** | 熱門標的排程 warm，冷門標的 on-demand | 熱門 ETF cron warm，長尾 cache-aside |
| **Fan-out at the edge, not at the origin** | CDN | Vercel 的 CDN 只快取回應，不快取我們對 Cboe 的請求 |

**但這一步在本專案有一個既有的、明文的反對意見（ADR-0001），而且它
的理由並非全部過時。** 見 §8.3——那裡是本輪最需要 Owner 裁決的地方。

---

## 6. Vendor / Platform Constraints

所有會隨時間變動的限制都附 source 與存取日期。**Primary =
vendor／平台官方文件或端點本身；Secondary = 第三方轉述。本節沒有使用
任何 secondary source。**

### 6.1 Treasury（primary）

| 限制 | 值 | Source | 存取日 |
|---|---|---|---|
| 更新頻率 | 每營業日一次，約 **15:30 ET**（NY Fed indicative quotations） | `https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics` | 2026-09-03 |
| Rate limit | **未公布** | 同上（頁面無此章節） | 2026-09-03 |
| 實測回應 | HTTP 200、13,799 B、0.66s、169 行 | 端點本身【一手實測】 | 2026-09-03 |

### 6.2 Cboe（primary，但無文件）

| 限制 | 值 | Source | 存取日 |
|---|---|---|---|
| 官方 API 文件 | **不存在**（該端點未出現在任何 Cboe 開發者文件中） | — | 2026-09-03 |
| Rate limit | **存在但未公布**：實測 `HTTP 429` + `retry-after: 34`，`server: cloudflare` | 端點本身【一手實測】 | 2026-09-03 |
| 門檻 | **未能測定**——20 次/1s 間隔、12 並發全量（25 MB/3.16s）皆未再觸發 | 【一手實測】 | 2026-09-03 |
| Payload | TLT 1.02 MiB / SPY 5.33 MiB（見 §5.2） | 【一手實測】 | 2026-09-03 |
| Cache header（429 回應） | `private, max-age=0, no-store, no-cache, must-revalidate` | 【一手實測】 | 2026-09-03 |

⚠ **無文件 ＝ 沒有承諾，也沒有預警。** 門檻可以在任何一天被 Cboe
單方面調整，而本專案沒有任何偵測或降級機制。

### 6.3 Vercel（primary）

【官方文件，存取 2026-09-03】

**Cron jobs**（`https://vercel.com/docs/cron-jobs/usage-and-pricing`，
頁面 `last_updated: 2026-07-15`）：

| | Hobby | Pro | Enterprise |
|---|---|---|---|
| Cron jobs per project | 100 | 100 | 100 |
| **Minimum interval** | **Once per day** | Once per minute | Once per minute |
| **Scheduling precision** | **Per-hour (±59 min)** | Per-minute | Per-minute |

> "Hobby accounts are limited to cron jobs that run **once per day**.
> Cron expressions that would run more frequently will fail during
> deployment."
>
> "Vercel cannot assure a timely cron job invocation. For example, a
> cron job configured as `0 1 * * *` (every day at 1 am) will trigger
> anywhere between 1:00 am and 1:59 am."

→ **任何「系統每天自己抓一次、全站共享」的 Treasury 排程，在 Hobby
上是可行的（一天一次剛好夠），但 ±59 分鐘的抖動代表它不能保證在
Treasury 15:30 ET 發布後、使用者開盤前那個窗口內跑完。任何比一天一次
更密的排程（例如熱門 symbol warming）需要 Pro。**

**Function limits**（`https://vercel.com/docs/functions/limitations`，
`last_updated: 2026-08-24`）：

| 項目 | Hobby | Pro |
|---|---|---|
| Max duration（**fluid compute**） | **300s default 與 maximum** | 300s default / 800s max / 1800s extended（beta） |
| Max duration（**非** fluid，2025-04-23 前建立的專案） | 10s default / **60s max** | 15s / 300s |
| Memory | 2 GB / 1 vCPU | 2 GB / 1 vCPU（可設到 4 GB / 2 vCPU） |
| **Request/response body** | **4.5 MB**（超過回 `413 FUNCTION_PAYLOAD_TOO_LARGE`） | 同左 |
| Concurrency | auto-scale 到 30,000 | 30,000 |
| Bundle size（Python） | 500 MB | 500 MB |
| File descriptors | 1,024（跨並發共用） | 1,024 |
| Regions | 預設單一 region（`iad1`） | 可設多 region |

**Fluid compute**（`https://vercel.com/docs/fluid-compute`,
`last_updated: 2026-08-24`）：

> "As of April 23, 2025, fluid compute is enabled by default for new
> projects."
>
> "Fluid compute uses a different approach to isolation. Instead of
> using a microVM for each function invocation, **multiple invocations
> can share the same physical instance (a global state/process)
> concurrently.**"
>
> "Vercel Functions prioritize existing idle resources before
> allocating new ones."

**Limits**（`https://vercel.com/docs/limits`, `last_updated: 2026-08-25`）：
Proxied request timeout 120s；Hobby 每日 100 deployments。
（Hobby 的 included Active CPU / Invocations / Fast Data Transfer 具體
數字在該頁的 Markdown 呈現中被渲染成空白，**我沒有取得可引用的
數值**——誠實揭露，見 §10。）

### 6.4 Neon（primary）

【官方文件，存取 2026-09-03】`https://neon.com/docs/introduction/plans`：

| 項目 | Free | Launch（下一階） |
|---|---|---|
| **Storage** | **0.5 GB / project** | $0.35/GB-month，無硬性上限 |
| Compute | 100 CU-hours/project/月 | $0.106/CU-hour |
| **Data transfer（egress）** | **5 GB / project / 月** | 500 GB 內含，之後 $0.10/GB |
| Autosuspend | 5 分鐘後，**不可停用** | 5 分鐘後，可停用 |
| Branches | 10/project | 10/project |

⚠ **Autosuspend 不可停用**在 Free 上直接影響冷啟動延遲：閒置 5 分鐘後
第一個請求要等 Neon compute 醒來。

### 6.5 Market Data App（primary）

【官方文件，存取 2026-09-03】

`https://www.marketdata.app/docs/api/rate-limits`：

| Plan | 限額 |
|---|---|
| Free Forever | **100 credits / day** |
| Starter | 10,000 credits / day |
| Trader | 100,000 credits / day |
| Quant | 10,000 credits / **minute** |
| Prime | 100,000 credits / minute |

> "Normally each successful response consumes 1 credit. However, if you
> request multiple symbols in a single API call using `stocks/quotes`,
> `stocks/prices`, `stocks/bulkcandles`, or `options/chain`, credits are
> consumed per symbol included in the response."
>
> "Only status 200/203 responses consume credits. NULL responses are not
> counted. Error responses are not counted."

`https://www.marketdata.app/docs/api/options/chain`：即時／延遲 **1
credit per option symbol**；帶 `date` 的歷史查詢 **1 credit per 1000
option symbols returned**。

`https://www.marketdata.app/docs/api/options/quotes`：歷史資料
**"Per 1000 quotes | 1 credit"**。

**對本專案的直接後果：**

| 本專案路徑 | 端點 | Credit 成本 | 評價 |
|---|---|---|---|
| Historical IV — exact contract（`ensure_contract_history`） | `options/quotes?from&to` | 一張合約一年 ≈ 250 quotes ＝ **1 credit** | ✅ 非常便宜 |
| Historical IV — legacy backfill（`backfill_iv`） | `options/chain?date=` | 每次呼叫 1–3 credits；一批最多 25 天 × 4 到期日 ＝ **≤ 100 次呼叫 ≈ 100–300 credits** | ⚠ 一個 symbol 的一批 backfill 就超過 Free 全天額度 |
| 自訂 Market Data 來源（`_fetch_chain`） | `options/chain`（即時，無篩選） | **2,414（TLT）～12,534（SPY）credits／次** | ❌ 見 §5.6 |

⚠ 這是**使用者自備 token**的模型（`provider_credentials` 表），因此
成本落在使用者身上而不是本專案——但 §5.6 那個量級的消耗，使用者不會
預期，產品也沒有任何揭露。

### 6.6 Yahoo / Nasdaq / FMP

| 來源 | Rate limit | Source | 存取日 |
|---|---|---|---|
| `query2.finance.yahoo.com` | **未公布**（無公開 API 文件）。`robots.txt` = `User-agent: * / Disallow: /`【一手實測】 | 端點本身 | 2026-09-03 |
| `api.nasdaq.com` | **未公布**（網站內部端點） | 端點本身 | 2026-09-03 |
| FMP | **未取得**——`site.financialmodelingprep.com/developer/docs/pricing` 對本沙箱回 **HTTP 403** | — | 2026-09-03 |

---

## 7. Scaling Model

### 7.1 符號

| 符號 | 意義 | 範例值（下面的算式一律用這組） |
|---|---|---|
| `U` | 每日活躍使用者數 | 100 / 1,000 / 10,000 |
| `s` | 每個使用者的劇本數 | 5 |
| `r` | 每個使用者每天觸發的**完整** refresh run 次數（開站＋手動刷新） | 3 |
| `d_u` | 單一使用者劇本涵蓋的 distinct symbol 數 | 3 |
| `D` | **全系統** distinct 活躍 symbol 數 | 見兩個情境 |
| `B̄` | 一個 symbol 的平均 chain payload | **2 MB**【一手實測，12 檔流動性佳標的的平均】 |
| `V` | 一次分析寫進 `results.view` 的大小 | **12.18 MiB**（3 families）／0.92 MiB（僅 vertical）【一手實測】 |
| `f` | shared 架構下每個 symbol 每天真正抓幾次 | 由 TTL 決定 |

**兩個 symbol 重疊情境**（因為真實的重疊率無從得知，用上下界夾住）：

- **情境 H（高重疊）**：使用者集中在少數熱門 ETF／大型股 → `D = 50`，
  與 U 無關。
- **情境 L（低重疊）**：長尾 → `D = 0.5 × U × s`。

### 7.2 Model 0：今天實際部署的樣子（**無 user 隔離**）

這是必須先講的，因為它讓後面所有數字失去意義。

`GET /api/scenarios` 沒有任何 user 過濾（`main.py:838-848`），
`refresh_run` 的 `scenario_ids is None` 分支直接吃
`_db().list_scenarios()`（`main.py:1065-1067`），前端 `reloadAndRefresh`
把回傳的全部 id 丟進 `runBatch`（`src/App.tsx:266-269`）。

> **一個使用者開站 ＝ 刷新資料庫裡「所有人」的劇本。**

因此一輪完整 refresh run 涵蓋 `S_total = U × s` 個劇本、`D` 個分組：

```
每日 chain 抓取數 = U × r × D
每日寫入 results 列數 = U × r × (U × s)      ← O(U²)
```

| U | 情境 | chain 抓取/日 | results 列/日 | Neon 寫入/日（3 families，未壓縮） |
|---|---|---|---|---|
| 100 | H (D=50) | 15,000 | 150,000 | **1.7 TB** |
| 1,000 | H (D=50) | 150,000 | 15,000,000 | **174 TB** |
| 100 | L (D=250) | 75,000 | 150,000 | 1.7 TB |
| 1,000 | L (D=2,500) | 7,500,000 | 15,000,000 | 174 TB |

**這個架構在 U ≈ 5–10 就已經無法運作**，而且問題不是 vendor quota，
是自己的資料庫。**結論：user 隔離不是「未來要做的功能」，它是任何
scaling 討論的前置條件。**

### 7.3 Model 1：只加 user 隔離，其他什麼都不改

一輪完整 refresh run 只涵蓋該使用者自己的 `s` 個劇本、`d_u` 個分組：

```
每日 chain 抓取數        = U × r × d_u                    = U × 9
每日 chain 下載量        = U × r × d_u × B̄               = U × 18 MB
每日 refresh invocation  = U × r × d_u  (GROUP_LIMIT=1)   = U × 9
每日 Treasury 上游       ≈ 1                              （已 shared）
每日 Dividend 上游       ≈ D                              （已 shared）
每日 results 列          = U × r × s                      = U × 15
每日 Neon 寫入           = U × r × s × V
```

| U | chain 抓取/日 | chain 下載量/日 | results 列/日 | Neon 寫入/日（未壓縮 ~ zlib-6） |
|---|---|---|---|---|
| 100 | 900 | 1.8 GB | 1,500 | **17.8 GB ~ 1.9 GB** |
| 1,000 | 9,000 | 18 GB | 15,000 | **178 GB ~ 19 GB** |
| 10,000 | 90,000 | 180 GB | 150,000 | **1.78 TB ~ 190 GB** |

**注意 Neon Free 的 storage 是 0.5 GB、egress 是 5 GB/月。**
即使在 U = 100 的最樂觀（zlib-6）估計下，**一天就寫進 1.9 GB**，是
Free storage 的 3.8 倍。

**這一列才是「什麼會先壞」的答案，而且它跟 vendor 一點關係都沒有。**

### 7.4 Model 2：Shared-data 架構

- Treasury：system-wide scheduled ＋ 全站共用 → **每日 1 次**（已達成）
- Dividend：global per-symbol cache-aside ＋ TTL ＋ single-flight →
  **每日 D 次**（已達成，缺 single-flight）
- Option chain：per-symbol shared cache，TTL = τ，single-flight →
  **每日 D × f 次**，其中 `f = min(需求次數, 交易時段秒數 / τ)`

以 6.5 小時交易時段（23,400 秒）計：

| τ | f（上界） |
|---|---|
| 30s | 780 |
| 60s | 390 |
| 300s (5 min) | 78 |
| 900s (15 min，對齊 Cboe 延遲量級) | 26 |

```
每日 chain 抓取數 = D × f          ← 完全不含 U
每日 chain 下載量 = D × f × B̄
```

| 情境 | D | τ=300s → 抓取/日 | 下載量/日 |
|---|---|---|---|
| H | 50 | 3,900 | 7.8 GB |
| L, U=1,000 | 2,500 | 195,000 | 390 GB |
| L, U=10,000 | 25,000 | 1,950,000 | 3.9 TB |

**注意 f 的上界只有在「每個 symbol 每個時間桶都真的有人看」時才會
達到。實務上冷門 symbol 的實際 f 遠低於上界**（cache-aside 只在有人
要的時候才抓），所以上表的 L 情境是嚴重的上界高估。

### 7.5 交叉比較與委託問題的直接答案

**Model 1 vs Model 2 的交叉點**：`U × r × d_u` vs `D × f`

以 H 情境（D=50, τ=300s → D×f = 3,900）：
- U × 9 = 3,900 → **U ≈ 433**
- 也就是說：**在高重疊情境下，超過約 430 個使用者之後，shared cache
  的絕對請求數就比今天少**；在那之前，shared cache 的價值不在總量而在
  **突發保護**（single-flight 消除同時抓取）。

**委託問題：request load 應該跟「users」成長，還是跟「unique active
symbols × refresh frequency」成長？**

> **應該跟後者成長，而且這不是效率偏好，是資料語意的必然結果。**
>
> `cdn.cboe.com/.../TLT.json` 是一個**無參數、無 per-user 內容**的公開
> CDN 物件——100 個使用者拿到的是逐位元相同的 bytes。當同一份資料被
> 重複抓 N 次時，N 這個數字沒有攜帶任何資訊：它不是需求的度量，是
> 缺少共用機制的度量。
>
> 資料的**識別性**（identity）是 `(symbol, 時間桶)`；正確的請求量因此
> 是 `|distinct (symbol, 時間桶)|`，也就是 `D × f`。使用者數只應該
> 影響 **cache hit 的次數**，不應該影響 **upstream fetch 的次數**。
>
> Treasury 與 Dividend 這兩條線本專案**已經做對了**（key 是 market-day
> 與 symbol，不是 user）。Option chain 是唯一一條沒做的。

---

## 8. Architecture Patterns Considered

每個 pattern 只回答四題：(1) 解本專案哪個具體問題？(2) 真的需要嗎？
(3) complexity cost？(4) 在 100 / 1,000 / 10,000 users 下價值是否不同？

### 8.1 已經在用、且用對了的（不要動）

| Pattern | 解什麼 | 現況 |
|---|---|---|
| **Cache-aside** | Treasury／Dividend／Treasury-year／contract history 全部是 | ✅ 已達成 |
| **Per-symbol cache key design** | 同 symbol 跨 scenario／跨 user 共用 | ✅ `dividend_cache`／`iv_observations` |
| **Immutable historical data caching** | 過去年份的 Treasury 曲線永久有效、不設 TTL | ✅ `treasury_cache.py:60-68`，PIT 安全靠鍵設計鎖死 |
| **Data provenance (fetched_at / effective_at)** | 使用者看得到資料多舊、來源是誰 | ✅ `market_day`／`attempted_day`／`last_success_at`／`as_of`／`stale`／`q_note`／`rate_note` |
| **TTL + freshness metadata** | market-day 語意比 wall-clock TTL 更貼近資料本身 | ✅ 這是本專案做得特別好的一點 |
| **Vendor fallback** | Treasury CSV→XML→前一年；Dividend Yahoo→FMP→Nasdaq | ✅ 對這兩條線有效 |
| **Negative caching** | 「這個標的確定沒有配息」是正確答案不是失敗 | ✅ `compute_q` 對空 distributions 回 0.0 且標 fresh |

**觀察**：本專案在 slow-moving 資料上的快取設計相當成熟。缺口高度
集中在**一條線（chain）＋一個機制（single-flight）**。

### 8.2 缺、且明確有價值的

#### Single-flight / request coalescing

- **解什麼**：每市場日第一批並發請求同時打 Treasury／Dividend；以及
  chain 的同時抓取。這是三條線**共同**缺的唯一機制。
- **真的需要嗎**：在 U=1 時完全不需要（永遠只有一個請求）。在 U≥50
  且使用者到達時間集中（開盤前）時，是**唯一**能把上游突發壓下來的
  機制。
- **Complexity cost**：在 serverless 上比在常駐 server 上**貴得多**。
  行程內 `singleflight` 只能覆蓋同一個 fluid instance 上的並發
  （fluid compute 讓這變成可能，但無保證）；跨 instance 需要
  **distributed lock**（Postgres advisory lock 可行，Neon 支援），
  而 distributed lock 要處理持有者崩潰、租約過期、驚群喚醒。
- **U 敏感度**：100 → 低；1,000 → 中；10,000 → 高。

#### Stale-while-revalidate

- **解什麼**：「每個活躍 symbol 每天第一個使用者要多等一次 HTTP」。
- **真的需要嗎**：對 Dividend **很划算**（stale 窗 90 天、資料月頻、
  §4.4 已證明 stale 幾乎無成本）。對 Treasury 划算（每日一變）。
  對 chain **要看產品對 freshness 的定義**——這是 Owner 決策。
- **Complexity cost**：需要「背景更新」機制。Vercel 有 `waitUntil`
  （fluid compute 的 background processing），但那是 Node.js SDK；
  Python runtime 的等價物**我未查證**（列入 §10）。
- **U 敏感度**：與 U 無關，是延遲問題不是負載問題。

#### DB retention strategy

- **解什麼**：§7.3 顯示的第一個硬牆。
- **真的需要嗎**：**是，而且最急。** 這是唯一在 U < 10 就會發生的問題。
- **Complexity cost**：低到中。可選項（不裁定）：只保留最近 N 次
  結果、把 `all_candidates` 從 view 移出改存窄表、對 `snapshots`
  設 TTL、或把大 payload 移出 Postgres。
- **U 敏感度**：U=1 就會發生（幾十次刷新）。

### 8.3 ⚠ 需要 Owner 裁決、本輪明確不裁定：per-symbol chain cache

**ADR-0001 明文禁止重新提案**，除非「流量形狀本身改變，且有同時計入
新增往返成本的量測」。本輪確實找到三項 ADR 當時不存在的證據，**因此
把它們攤開，但不做決定：**

**ADR-0001 的三個理由，逐一對照今天：**

| ADR 的理由 | 今天是否仍成立 |
|---|---|
| 「前端一輪刷新是嚴格串行的（`App.tsx:187` 逐一 `await refreshOne()`），批次尾端的請求很容易在 15 秒之後才開始，於是 miss」 | **這段程式碼已不存在**（T08／#196 換成 `runBatch`）。但 `GROUP_LIMIT=1` 讓實際形狀變回「每個 distinct symbol 一次 invocation」。**時間軸被壓縮了**（一輪 D 個請求是連續 pipeline，不是逐劇本序列），15 秒 TTL 的 miss 率因此與當時**不同**——但我**沒有** production 量測，不能宣稱它現在會 hit。 |
| 「miss 路徑是純增加成本：多一次 Neon SELECT，再把整條 chain 當 JSONB 寫回——而同一份 payload 本來就已經寫進 `snapshots` 表」 | **完全成立，而且更嚴重。** 我實測 SPY snapshot ＝ 2.55 MiB。把 chain 再寫一份進另一張表，等於一次刷新兩次 MB 級寫入。**這是反對「把 chain 放進 Postgres」最強的論證，本輪沒有推翻它。** |
| 「hit 路徑是拿 Neon 讀數百 KB JSONB＋重建千級 dataclass 去換一次 Cboe CDN 的 GET，沒有證據前者比較便宜」 | **在 U 小時成立。** 我實測 Cboe TLT GET 只要 **0.23–0.60s**，而 1 MiB JSONB 從 Neon 讀出＋`snapshot_from_dict` 重建**很可能不會更快**。但 ADR 沒有考慮的是：**Cboe 那一端有 429**（§5.5）。當上游會限流時，「哪一邊比較快」不再是唯一的比較維度。 |

**ADR 當時不存在的三項新證據：**

1. **上游會 429**（§5.5，一手實測）。ADR 假設 Cboe GET 是無限量供應的
   免費操作。它不是。
2. **Fluid compute 讓行程內快取變成可能**。ADR 的前提「跨 invocation
   沒有共享記憶體，實例可能每次請求都冷啟動」已被官方文件推翻（§6.3）。
   **這開啟了一個 ADR 從未評估過的第三選項：行程內 per-symbol
   memoization，零 Neon 往返、零額外寫入**——正好繞開 ADR 最強的那個
   反對理由。代價是 hit rate 不確定（instance 數量、生命週期不可控），
   因此它只能當**盡力而為的優化**，不能當保證。
3. **Vercel 自身的 CDN 從未被評估過。** `/api/scenarios/refresh-run`
   是 POST，天生不可快取；但「取得某 symbol 的鏈」如果存在為一個
   **GET 端點**，Vercel Edge Network 可以用 `s-maxage` +
   `stale-while-revalidate` 在**平台層**做共用，完全不碰 Postgres、
   不碰行程記憶體。ADR 只比較了「Postgres 快取」vs「不快取」兩個選項。

**必須誠實說的**：我**沒有** production 量測，無法滿足 ADR 要求的
「同時計入新增往返成本的量測」。因此本文**不提案**任何 chain 快取，
只把新證據登記在案，供 Owner 決定要不要重開這個題目（§10 Q3）。

### 8.4 缺、但價值視 U 而定

| Pattern | 解什麼 | 100 users | 1,000 | 10,000 |
|---|---|---|---|---|
| **Exponential backoff + circuit breaker** | Cboe 429 之後不要 retry storm | **已經需要**（§5.5，後果是全站中斷） | 需要 | 必要 |
| **Scheduled refresh（cron warming）** | 熱門 symbol 永不 cold miss | 低（Hobby 一天一次不夠密） | 中（需 Pro） | 高 |
| **Hot / cold symbol distinction** | 只 warm 值得 warm 的 | 低 | 中 | 高 |
| **Distributed lock** | 跨 instance single-flight | 不需要 | 視 §8.2 而定 | 需要 |
| **Read-through cache**（相對 cache-aside） | 把「誰負責填快取」收進一個地方 | 純結構收益 | 同左 | 同左 |
| **Shared system-wide cache（Redis/KV）** | 比 Postgres 便宜的共用層 | 不需要（多一個 vendor） | 需評估 | 可能需要 |
| **Deduplication（同一輪內）** | 同 symbol 多劇本 | ✅ **已達成**（ADR-0001） | 同左 | 同左 |

### 8.5 研究到但判斷「本專案不需要」的

| Pattern | 為什麼不需要 |
|---|---|
| **Whole-universe preload** | Universe 不封閉（§4.5）；Hobby cron 一天一次 |
| **Per-user cache partitioning** | 這三份資料都是公開市場事實，按 user 分割會**破壞**共用，方向相反 |
| **Write-through cache** | 我們不寫入 vendor，沒有 write path |
| **Event-driven invalidation** | vendor 不提供 webhook／push；只能靠時間 |

---

## 9. P0 / P1 / P2 Risk Matrix

**分級定義**（依委託）：**P0** ＝ 在讓更多使用者上線之前必須解決；
**P1** ＝ 1,000 users 之前應解決；**P2** ＝ 可以之後再做。

### P0

| # | 問題 | 證據 | 為什麼是 P0 |
|---|---|---|---|
| **P0-1** | **`results.view` 12.18 MiB/刷新 × 無 retention**。96.4% 是 `results[call-fly].all_candidates`（74,011 筆，11.78 MiB），而它唯一的消費者 `spread_cost_history` 每次只查**一個** candidate_key | 【一手實測】真實 TLT 鏈跑三 family；`store.py:680`、`store.py:257-287`；`postgres.py` 無 retention SQL | Neon Free 0.5 GB【官方文件】÷ 12.18 MiB ＝ **42 次刷新**（zlib-1 後 335 次、zlib-6 後 402 次；Postgres TOAST 預設壓縮弱於 zlib-6，實際更靠近低端）。**U=1 就會撞到。** 且 V1→V2 是 0.92 MiB → 12.18 MiB 的 13.5 倍躍升，剛在 2026-09-03 merge 上線 |
| **P0-2** | **無 user 隔離（#59）＋「開站刷新全部」** → 任何使用者開站就刷新全站所有人的劇本，負載 **O(U²)**；且全站共用一把 provider token、一份劇本清單 | `main.py:838-848`（無 user 過濾）、`main.py:1065-1067`、`src/App.tsx:266-269`；`main.py` 全檔零 `Depends`／零 auth | 在 U≈5–10 就讓 §7.2 的數字失控。**它是所有其他 scaling 數字的前置條件**；同時是隱私問題（B 看得到 A 的劇本） |
| **P0-3** | **Cboe 會 429，而 adapter 完全不處理**：不讀 `retry-after`、無 backoff、無 circuit breaker；唯一備援 yfinance 在 production 結構上不可達 | 【一手實測】`HTTP 429` + `retry-after: 34` + `server: cloudflare`；`data/cboe.py:102`；`pyproject.toml:12-15`（`[project] dependencies` 三項，無 yfinance）vs `:30`（`yf` extra）；`data/yf.py:51, 63` | 觸發後**核心功能全站中斷且無自動復原**，使用者重試會形成 retry storm 延長中斷。機率隨 `U × r × D` 線性上升 |
| **P0-4** | **`result_history()` 把該劇本**全部**歷史 view 完整讀出**——`/results` 只需要 `analyzed_at`，`/history` 只需要每份裡的一筆 | `postgres.py:550-556`（`SELECT {_RESULT_COLS}` 含 `view`）；`main.py:1127-1133`、`main.py:1135-1146` | 與 P0-1 相乘：一個刷新過 30 次的劇本，開一次歷史走勢圖 ＝ 從 Neon 讀 **365 MiB** 並反序列化。Neon Free egress 只有 5 GB/月 |
| **P0-5** | **三條線都沒有 single-flight** — 每市場日第一批並發請求各自打上游 | `rate_cache.py:86-153`／`dividend_cache.py:53-97` 皆為裸 read-fetch-write | Treasury 的 miss 最壞要 3×15s ＝ 45s，而 `REFRESH_RUN_BUDGET` 就是 45s（`main.py:66`）→ 每市場日第一批使用者可能整輪逾時 |

### P1

| # | 問題 | 證據 |
|---|---|---|
| **P1-1** | **Option chain 零共用** ＝ 唯一「使用者數直接乘上 vendor request 數」的資料流。100 人看 TLT ＝ 100 次抓取 ＝ 107 MB | §5.4；ADR-0001 |
| **P1-2** | **`REFRESH_RUN_GROUP_LIMIT = 1`** 讓一輪刷新的 invocation 數 ＝ distinct symbol 數，Refresh Run「一次 invocation 收一輪」的原始設計目標在實務上不成立 | `main.py:80, 1083` |
| **P1-3** | **Treasury／Dividend 抓取在使用者關鍵路徑上**（最壞 45s／60s），沒有排程 warm | `data/treasury.py:45, 82-84`；`data/dividends.py:34, 67-103` |
| **P1-4** | **`snapshots` 表每次刷新寫 0.48–2.55 MiB，無 retention** | 【一手實測】；`main.py:979` |
| **P1-5** | **Market Data App 自訂 chain 來源 ＝ 2,414–12,534 credits／次**，Free 全天只有 100，產品完全未揭露 | 【官方文件】§6.5；`data/marketdata.py:34, 185` |
| **P1-6** | **Dividend primary source 的 `robots.txt` 是 `Disallow: /`**，且無公開 API／SLA | 【一手實測】§4.6 |
| **P1-7** | **本 repo 對平台限制的認知過時**（60s vs 300s；「無共享記憶體」vs fluid compute），會讓後續設計沿用錯誤前提 | §6.3；`CONTEXT.md:123`、`api_app/main.py:62, 72, 1033, 1053`、`option_chaser/service.py:71, 1287`；`docs/adr/0001:10` |

### P2

| # | 問題 |
|---|---|
| **P2-1** | 本地檔案快取層（`snapshots/*.json`）在 production 是死碼，docstring 宣稱的三層 fallback 實際只有兩層 |
| **P2-2** | `refresh_run` 帶顯式 ids 時對每個 id 各發一次 `get_scenario()`（`main.py:1069-1071`），N 個 id ＝ N 次 SELECT |
| **P2-3** | Neon Free autosuspend 5 分鐘**不可停用** → 低流量時每次冷啟動都要等 compute 醒來 |
| **P2-4** | 沒有任何 cache hit-rate／upstream request-count 的可觀測性；今天無法回答「昨天對 Cboe 發了幾次請求」 |
| **P2-5** | 單一 region（`iad1`），未設 `regions`；Cboe/Treasury 都在美東，這其實是對的，但未經有意識的決定 |
| **P2-6** | SPY 的 `/raw-data` 回應 2.55 MiB，距 Vercel 4.5 MB 上限只剩 1.8 倍餘裕（更大的鏈可能撞上 `413`） |

---

## 10. Open Questions for Wayfinder

**以下每一題我都刻意沒有決定。**

**Q1（前置）｜多使用者隔離模型（#59）。** 在它定案之前，所有 scaling
數字都是 O(U²)（§7.2），任何快取設計也無法定案——因為「哪些資料
per-user、哪些 system-wide」正是隔離模型要回答的。我的觀察僅止於：
`rate_cache`／`dividend_cache`／`treasury_year_cache`／
`contract_iv_history`／`iv_observations` 快取的都是**公開市場事實**，
按 user 切分會破壞共用；`scenarios`／`results`／`snapshots`／
`provider_credentials` 才是 per-user 的。

**Q2（最急）｜Retention 與 `all_candidates`。** 三個子問題：
(a) `results`／`snapshots` 要保留多久／幾次？
(b) `all_candidates`（74,011 筆／11.78 MiB）只為了服務
`spread_cost_history` 對**單一** candidate_key 的查詢——是否該改成
窄表、或只對使用者實際追蹤的候選保存？
(c) SpreadHistory 走勢圖產品上真的需要多長的歷史？
**這一題不解，其他都不用談。**

**Q3｜要不要重開 ADR-0001？** 本輪帶來三項它當時不存在的證據
（上游會 429、fluid compute 讓行程內快取可能、Vercel Edge CDN 從未
被評估）。但我**沒有** production 量測，達不到 ADR 自己設定的重開門檻。
**要不要重開、以及重開時是否要求先做 production 量測，是 Owner 的決定。**

**Q4｜Chain 的 freshness 契約是什麼？** 目前沒有任何地方寫下「使用者
看到的報價最舊可以是幾秒前」。Cboe 本身已是延遲報價，Refresh Run 的
三個 Trigger 也不是連續輪詢。**沒有這個契約，任何 TTL 數字都是憑空
挑的**——ADR-0001 的 15 秒當初就是這樣挑的。

**Q5｜Hobby 還是 Pro？** 影響三件具體的事：cron 最小間隔（一天一次
vs 一分鐘一次）、cron 精度（±59 分鐘 vs 準時）、maxDuration（300s vs
800s）。**如果決策方向包含「系統自己排程抓取」，Hobby 的一天一次
＋±59 分鐘可能不夠。** 另外我**未查證** Hobby 的商業使用條款是否適用
於本專案（§10-限制）。

**Q6｜Market Data App 自備 token 模型還要不要留？** §6.5 顯示自訂
chain 來源一次要 2,414–12,534 credits，Free 只有 100/day。要嘛揭露
成本、要嘛限制該路徑、要嘛移除。（Historical IV 那條路徑成本合理，
不受影響。）

**Q7｜Yahoo `Disallow: /` 怎麼處理？** 合規／治理決策，不是工程決策。

**Q8｜Cboe 429 的降級策略要長什麼樣？** 我只確認了「必須有」。要
backoff＋重試？circuit breaker＋顯示舊資料？換備援來源？
——**是產品決策**（使用者看到什麼），不只是工程決策。

### 本輪明確的取材與量測限制（誠實揭露）

1. **Cboe 429 的門檻未能測定。** 我觸發了一次，但後續 20 次/1s、
   12 並發全量（25 MB/3.16s）都沒能重現。只能斷言「存在且未公布」。
2. **所有量測都在這個沙箱、從單一 IP 做的**，不是從 Vercel `iad1`
   的出口。Vercel 使用動態 IP，實際的限流表現可能不同（可能更好——
   請求分散在多個出口 IP；也可能更差——與其他 Vercel 使用者共用）。
3. **沒有任何 production 遙測。** 所有 U>1 的數字都是模型推算。
   本專案目前沒有 cache hit-rate 或 upstream request-count 的計數器
   （P2-4），因此連「今天實際對 Cboe 發了幾次」都無從得知。
4. **未取得**：FMP 官方限額（403）、Vercel Hobby 的 included
   Active CPU／Invocations／Fast Data Transfer 具體數值（官方頁面的
   該表格在 Markdown 呈現中為空白）、Vercel Hobby 商業使用條款、
   Python runtime 是否有 `waitUntil` 等價物、部署專案實際是否啟用
   fluid compute（僅能依「2025-04-23 後建立的新專案預設啟用」推定）。
   （2026-09-04 已於 `docs/research/runtime-targeted-scaling.md` 查證
   完成，見該文件——結論：Python 無官方 `waitUntil` 等價物；production
   專案是否啟用 fluid compute 因 MCP 工具對該專案零可見度而未能直接
   確認，仍為推定）
5. **`V = 12.18 MiB` 是 TLT（2,414 合約）的數字。** 更大的鏈
   （SPY 12,534 合約）butterfly 是 `C(n,3)`，量體會**更大**——
   我沒有實測，因為那已足以說明問題。
6. 本輪**未**驗證 `refresh_run` 在真實 production 併發下的行為，
   也未部署任何探針。

---

## 11. Sources / Evidence

### 11.1 Primary sources — 官方文件（全部在 2026-09-03 存取）

| # | Source | 取得的確切限制 |
|---|---|---|
| S1 | `https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics` | "indicative quotations obtained by the Federal Reserve Bank of New York at approximately 3:30 PM each business day" → 每營業日更新一次。無公布 rate limit |
| S2 | `https://vercel.com/docs/cron-jobs/usage-and-pricing`（頁面 `last_updated: 2026-07-15`） | Hobby: 100 crons/project, **minimum interval "Once per day"**, precision "Per-hour (±59 min)"；Pro/Ent: once per minute, per-minute。"Hobby accounts are limited to cron jobs that run once per day. Cron expressions that would run more frequently will fail during deployment." |
| S3 | `https://vercel.com/docs/functions/limitations`（`last_updated: 2026-08-24`） | Fluid: Hobby 300s default **and maximum**；Pro 300s/800s/1800s(beta)。非 fluid 且 2025-04-23 前建立：Hobby 10s/60s。Memory Hobby 2GB/1vCPU。**Request/response body 4.5 MB**（`413 FUNCTION_PAYLOAD_TOO_LARGE`）。Concurrency auto-scale 30,000。Python bundle 500 MB。FD 1,024 |
| S4 | `https://vercel.com/docs/fluid-compute`（`last_updated: 2026-08-24`） | "As of April 23, 2025, fluid compute is enabled by default for new projects."／"multiple invocations can share the same physical instance (a global state/process) concurrently" |
| S5 | `https://vercel.com/docs/limits`（`last_updated: 2026-08-25`） | Proxied request timeout 120s；Hobby 100 deployments/day。⚠ Hobby 的 Active CPU／Invocations／Fast Data Transfer 數值在該頁 Markdown 呈現中為空白，**未取得** |
| S6 | `https://neon.com/docs/introduction/plans` | Free: **storage 0.5 GB/project**、compute 100 CU-hours/project/月、**data transfer 5 GB/project/月**、autosuspend "After 5 min" 且 "cannot be disabled"。Launch: $0.35/GB-month、$0.106/CU-hour、500 GB 內含 |
| S7 | `https://www.marketdata.app/docs/api/rate-limits` | Free Forever **100 credits/day**；Starter 10,000/day；Trader 100,000/day；Quant 10,000/min；Prime 100,000/min。"Normally each successful response consumes 1 credit... if you request multiple symbols in a single API call using ... `options/chain`, credits are consumed per symbol included in the response."／"Only status 200/203 responses consume credits." |
| S8 | `https://www.marketdata.app/docs/api/options/chain` | 即時/延遲："1 credit" "Per option symbol"；帶 `date`："1 credit per 1000 option symbols returned in the response" |
| S9 | `https://www.marketdata.app/docs/api/options/quotes` | "Historical Data \| Per 1000 quotes \| 1 credit" |

### 11.2 Primary sources — 對端點本身的一手實測（2026-09-03）

| # | 觀測 | 值 |
|---|---|---|
| E1 | `cdn.cboe.com/.../TLT.json` 限流 | **`HTTP/2 429`, `retry-after: 34`, `server: cloudflare`, `cf-ray: a356e2fe39d5e647-IAD`** |
| E2 | Cboe payload | TLT 1,072,425 B / 2,414 合約 / 29 到期日；SPY 5,592,700 B / 12,534 合約 / 34 到期日 |
| E3 | Cboe 12 檔並發全量 | 12 並發、3.16s、24,996,146 B、0 個 429 → 平均 2.08 MB/symbol |
| E4 | Cboe 序列全量 | 10 檔 1s 間隔、18,869,345 B、0 個 429 |
| E5 | Treasury CSV | `HTTP 200`, 13,799 B, 0.66s, 169 行, `server: nginx`, `x-generator: Drupal 10` |
| E6 | Yahoo dividend 端點 | `HTTP 200`, 28,194 B, `cache-control: public, max-age=10, stale-while-revalidate=20`, `server: ATS` |
| E7 | **`query2.finance.yahoo.com/robots.txt`** | **`User-agent: *` / `Disallow: /`** |
| E8 | Nasdaq dividends 端點 | `HTTP 200`, 32,990 B, `cache-control: max-age=0, no-cache, no-store`, `server: Kestrel` |
| E9 | production `GET /api/health` | `{"storage":"postgres","rate":{"fetched_at":"2026-09-03T05:00:52+00:00","ok":true,"note":"Treasury 曲線 2026-09-02"}}`；`x-vercel-id: iad1::iad1::...` |

### 11.3 Primary sources — 對本 repo 程式碼的一手量測（2026-09-03）

用 `sys.path` 掛載 repo、直接 import 本專案自己的 `data.cboe`、
`service`、`store` 執行；**未修改任何 repo 檔案**。

| # | 量測 | 值 |
|---|---|---|
| M1 | `serialize_result` 大小（真實 TLT 鏈，`target_month=2027-01`，`loaders=None`） | 僅 vertical-spread：**969,702 B (0.92 MiB)**；+single-leg：1,138,453 B；**三 family：13,068,821 B (12.46 MiB)**（另一次跑 12,774,445 B / 12.18 MiB，隨當時報價浮動） |
| M2 | 三 family view 的組成 | `results` 12,598,295 B (96.4%)，其中 `results[call-fly]` 11,775,334 B（`all_candidates` 74,011 筆）；`candidate_pool` 463,376 B；`axis_sets` 3,000 B |
| M3 | `project_for_detail` 後的 wire 大小 | 480,252 B (0.46 MiB) — T13/#231 確實有效 |
| M4 | view 壓縮率 | zlib-1 → 1,601,430 B (8.0×)；zlib-6 → 1,335,450 B (9.6×) |
| M5 | Neon Free 0.5 GB 可容納的 `results` 列數 | **42（未壓縮）／335（zlib-1）／402（zlib-6）**。⚠ 這是 JSON 文字的壓縮率，非 Postgres TOAST 實測——TOAST 預設 pglz／lz4 弱於 zlib-6，實際值介於 42 與 402 之間並偏低端 |
| M6 | `snapshots` 列大小 | TLT 507,552 B；SPY 2,668,703 B |
| M7 | `GET /raw-data` 回應大小 | TLT 507,565 B；SPY 2,668,717 B（**均低於 Vercel 4.5 MB 上限**） |
| M8 | 三 family 引擎時間（`loaders=None`，q=0 快路徑） | 3.21s（TLT 2,414 合約） |
| M9 | 候選數（真實 TLT） | long-call 242；bull-call-spread 4,894；**call-fly 74,011** |

### 11.4 本 repo 既有紀錄（【repo 紀錄】，我未獨立重驗）

| # | 來源 | 內容 |
|---|---|---|
| R1 | `docs/adr/0001-chain-sharing-within-run-only.md` | chain 只在單一 Refresh Run 記憶體內去重；不做跨 invocation 快取；「不要重新提案」條款 |
| R2 | `CLAUDE.md`（REPAIR-03／#240） | production-scale 三 family 全開：memoization 前 154.236s → 後 **7.543s** |
| R3 | `docs/research/heatmap-valuation-method-selection.md` | q=0 讓「今天×現價」那格印 +81.9%，誠實答案 −11.5% |
| R4 | `docs/research/historical-iv-reconstruction-corrected-calibration-results.md` | TLT q ablation：q=0 使 MAE 0.0089 → 0.0493（+4.05 vol pts） |
| R5 | `CLAUDE.md`（PERF-07 對照表） | 「同 symbol chain 重複抓取 5 次 → 1 次」——⚠ 那是 PERF-06 的 `chain_cache`，**已於 T06／E2 隨 ADR-0001 整組刪除**，該表述已不反映現況 |
| R6 | `CONTEXT.md:123`、`api_app/main.py:62, 72, 1033, 1053`、`option_chaser/service.py:71, 1287` | 「60 秒函式（硬性）上限」共 7 處——⚠ 與 S3／S4 衝突，見 §1.1-8 |

### 11.5 Secondary sources

**本文未使用任何 secondary source。** 所有外部主張都來自 §11.1（官方
文件）或 §11.2（對端點本身的一手觀測）。

### 11.6 與既有 repo 紀錄衝突之處（供後續 session 注意）

| # | repo 說法 | 本輪發現 | 依據 |
|---|---|---|---|
| C1 | CONTEXT.md／CLAUDE.md 多處：「60 秒函式硬性上限」 | Fluid compute 下 Hobby default 與 max 皆 **300s**；60s 是 `vercel.json` 自設的 `maxDuration` | S3, S4 |
| C2 | ADR-0001：「跨 invocation **沒有共享記憶體**，實例可能每次請求都冷啟動」 | "multiple invocations can share the same physical instance (a global state/process) concurrently" | S4 |
| C3 | ADR-0001 背景：「前端一輪刷新是嚴格串行的（`App.tsx:187` 逐一 `await refreshOne()`）」 | 該程式碼已被 T08／#196 的 `runBatch` 取代；但 `GROUP_LIMIT=1` 讓實際形狀部分回退 | `src/App.tsx:188-257`, `main.py:80` |
| C4 | CLAUDE.md PERF-06 段落描述 `api_app/chain_cache.py` 為已出貨 | **該檔案不存在**（T06／E2 已刪除，符合 ADR-0001）。PERF-07 對照表仍留著「5 次→1 次」的數字 | 檔案系統；ADR-0001 |
| C5 | `data/cboe.py` docstring：「此端點無官方 API 文件、無 SLA」 | 正確，但**漏了最重要的一項：它會 429** | E1 |
| C6 | CLAUDE.md「## 環境」：`raw.githubusercontent.com` 是唯一一手通道、WebFetch 被擋、vendor 網域 CONNECT 403 | **本輪全部推翻**：WebFetch 可用；treasury.gov／vercel.com／neon.com／marketdata.app／query2.finance.yahoo.com／api.nasdaq.com／cdn.cboe.com 一律 curl 可達 | §11.2 全部 |
| C7 | `data/treasury.py`／`data/dividends.py` docstring 宣稱三層 fallback | production 只有兩層——本地檔案快取那層因 Vercel FS 唯讀而永遠走不到 | `data/treasury.py:142-143`；`.vercelignore` |

---

READY_FOR_MARKET_DATA_WAYFINDER
