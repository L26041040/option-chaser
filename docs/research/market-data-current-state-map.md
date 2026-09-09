# Market Data 現況地圖（Current-State Map）

研究日期：2026-09-03。對應 **OPTION-MARKET-DATA-RESEARCH-001**。
基準：`origin/master` HEAD `864dd5c`（工作樹 `b41ad1c`，已核對與 master
production code 逐位元相同）。

本檔只畫「現在實際長什麼樣」，**不含任何建議**——建議與風險分級見
`market-data-lifecycle-scaling.md`。每個框都可回推到具體檔案與行號。

---

## 1. 全景圖

```mermaid
flowchart TB
    subgraph BROWSER["瀏覽器（單一使用者，無登入、無 user id）"]
        A1["開站 / 按刷新鈕"]
        A2["建立劇本"]
        A3["詳細頁"]
        RB["runBatch()<br/>src/App.tsx:188"]
        RO["refreshOne()<br/>src/App.tsx:152"]
        A1 --> RB
        A2 --> RB
        A3 --> RO
    end

    subgraph EDGE["Vercel Edge（vercel.json：/api/(.*) → api/index.py）"]
        MW["correlation + storage scope middleware<br/>api_app/main.py:533"]
    end

    subgraph FN["Vercel Python Function（iad1，maxDuration 60s 自設）"]
        RR["POST /api/scenarios/refresh-run<br/>main.py:1011<br/>GROUP_LIMIT=1 → 一次回應只做一個 symbol 分組"]
        RS["POST /api/scenarios/{id}/refresh<br/>main.py:989"]
        FC["_fetch_chain(symbol)<br/>main.py:574"]
        AN["_analyze() → service.run_with_snapshot<br/>main.py:615 / service.py:1393"]
        IV["GET /iv-history · POST /iv-history/backfill<br/>main.py:1341 / 1398"]
        RR --> FC
        RS --> FC
        FC --> AN
        RR --> AN
        RS --> AN
    end

    subgraph LOADERS["估值輸入 loader（每次 analysis 各呼叫一次）"]
        RL["_rate_curve_loader()<br/>rate_cache.cached_loader"]
        DL["_dividend_loader()<br/>dividend_cache.cached_loader"]
        TR["_cached_rate_curve_rows()<br/>treasury_cache（PIT，只給 IV history）"]
    end

    subgraph NEON["Neon Postgres（全站單一資料集，無 user 欄位）"]
        C1[("rate_cache<br/>單列 id=1<br/>market-day")]
        C2[("dividend_cache<br/>PK symbol<br/>market-day / 90d stale")]
        C3[("treasury_year_cache<br/>PK year<br/>過去年份永久")]
        C4[("contract_iv_history<br/>PK contract_symbol")]
        C5[("iv_observations / iv_backfill_runs<br/>PK symbol")]
        D1[("results.view JSONB<br/>每次刷新一列，無 retention")]
        D2[("snapshots<br/>每次刷新一列，無 retention")]
    end

    subgraph EXT["外部資料源（Vercel 出口，動態 IP）"]
        X1{{"cdn.cboe.com<br/>整鏈 JSON，1–5.6 MB<br/>⚠ 無文件、會 429"}}
        X2{{"home.treasury.gov<br/>CSV → XML → 前一年 CSV"}}
        X3{{"query2.finance.yahoo.com<br/>→ FMP → api.nasdaq.com"}}
        X4{{"api.marketdata.app<br/>需使用者 token"}}
    end

    A1 -.-> MW
    MW --> RR
    MW --> RS
    MW --> IV
    AN --> RL
    AN --> DL
    IV --> TR
    IV --> DL

    FC ==>|"❗每次呼叫都真的抓一次<br/>無任何跨 invocation 快取"| X1
    FC -. "使用者選自訂時" .-> X4
    RL --> C1
    DL --> C2
    TR --> C3
    IV --> C4
    IV --> C5

    C1 -. "market-day miss（每市場日約一次）" .-> X2
    C2 -. "(symbol, market-day) miss" .-> X3
    C3 -. "年份 miss" .-> X2
    C4 -. "(contract, day) miss" .-> X4
    C5 -. "(symbol, day) miss，一批最多 25 天 × 4 到期日" .-> X4

    AN ==>|"每次刷新寫入<br/>12.18 MiB（3 families，實測）"| D1
    AN ==>|"每次刷新寫入<br/>0.48–2.55 MiB（實測）"| D2
```

---

## 2. 邊界標註

### 2.1 Request boundary（一次 HTTP request 的範圍）

| 邊界 | 內容 | 依據 |
|---|---|---|
| 一次 `refresh-run` HTTP request | **恰好一個 symbol 分組**（`REFRESH_RUN_GROUP_LIMIT = 1`），其餘進 `remaining`，由前端 Continuation 迴圈再打一次 | `main.py:80`、`main.py:1083`、`src/App.tsx:196-253` |
| 一次 `refresh` HTTP request | 恰好一個劇本、一次抓鏈 | `main.py:989-1009` |
| Storage 連線 | 一個 request 共用一條 Neon 連線（`contextvars`，惰性開啟） | `main.py:533`、`storage/postgres.py:356` |
| Diagnostics | per-request 緩衝，結束時才依優先序落盤，且只有 `warning`／`error` 寫庫 | `main.py:1215-1233` |
| Chain 記憶體去重 | **只在這一次 invocation 內**，且因 GROUP_LIMIT=1 實際等同「同一 symbol 的多個劇本」 | `docs/adr/0001`、`main.py:1073-1096` |

### 2.2 Cache boundary（快取住在哪、鍵是什麼、活多久）

| 快取 | 位置 | 鍵 | 新鮮度 | 跨 invocation | 跨使用者 |
|---|---|---|---|---|---|
| `rate_cache` | Neon 單列 | 無（全站一筆） | `market_day == today`；失敗 5 分鐘窗；7 天 stale fallback | ✅ | ✅（今天無 user 概念） |
| `dividend_cache` | Neon | `symbol` | 同上，但 stale fallback 90 天 | ✅ | ✅ |
| `treasury_year_cache` | Neon | `year` | 過去年份**永久**；當年 market-day | ✅ | ✅ |
| `contract_iv_history` | Neon | `contract_symbol`（OCC） | `last_attempt_on == today` 就不再打 vendor | ✅ | ✅ |
| `iv_backfill_runs` | Neon | `symbol` | `ran_on == today` 就不再跑 | ✅ | ✅ |
| **Option chain** | **不存在** | — | — | ❌ | ❌ |
| Treasury 本地檔案快取 | `snapshots/*.json` | — | 7 天 | ❌ **production 死碼**（Vercel FS 唯讀，`_write_cache` 吞 `OSError`） | ❌ |
| 配息本地檔案快取 | `snapshots/*.json` | `symbol` | 90 天 | ❌ **production 死碼**（同上） | ❌ |
| 前端 `fetchCache` | 瀏覽器記憶體 | `(id, analyzed_at)` 等 | 參照計數，掛載期間 | ❌ | ❌（per-tab） |

### 2.3 Shared / non-shared

```
全站共用（今天就是 system-wide，因為沒有 user 隔離）
  ├── rate_cache            ← 天生就是 shared-data 架構
  ├── treasury_year_cache   ← 天生就是 shared-data 架構
  ├── dividend_cache        ← per-symbol，天生可跨使用者共用
  ├── contract_iv_history   ← per-contract，天生可跨使用者共用
  ├── iv_observations       ← per-symbol，天生可跨使用者共用
  ├── provider_credentials  ← ⚠ 全站一把 token（無 user 欄位）
  └── scenarios / results / snapshots  ← ⚠ 全站一份清單（無 user 欄位）

完全不共用
  └── option chain          ← 每一次「劇本 × 刷新」各抓一次全鏈
```

### 2.4 External call points（真正對外發出請求的唯四處）

| # | 位置 | 目的地 | 觸發頻率（現況） |
|---|---|---|---|
| 1 | `main.py:574 _fetch_chain` → `service.fetch_chain` → `data/cboe.py:95` | `cdn.cboe.com` | **每個 (symbol 分組 × refresh-run 請求)**，零快取 |
| 2 | `service.py:56 default_rate_curve_loader` → `data/treasury.py:80` | `home.treasury.gov` | 每市場日約 1 次（全站） |
| 3 | `service.py:61 default_dividend_loader` → `data/dividends.py:67` | `query2.finance.yahoo.com` → FMP → `api.nasdaq.com` | 每 (symbol, 市場日) 1 次（全站） |
| 4 | `ivpipeline.py` → `providers.py:107/131` → `data/marketdata.py` | `api.marketdata.app` | 每 (contract, 日) 1 次；backfill 每 (symbol, 日) 一批 ≤ 25 天 × ≤ 4 到期日 |

`data/yf.py`（yfinance 備援）**在 production 結構上不可達**：`yfinance`
不在 `pyproject.toml` 的 `[project] dependencies` 裡，只在 `yf` extra
（`pyproject.toml:30`），而 Vercel 只裝 `dependencies`——`import yfinance`
必 `ImportError`，被 `data/yf.py:63` 收斂成 `FetchError`。

---

## 3. 一次「開站刷新」的完整時序（現況，D 個 distinct symbol）

```mermaid
sequenceDiagram
    autonumber
    participant B as 瀏覽器
    participant F as Vercel Function
    participant N as Neon
    participant C as cdn.cboe.com
    participant T as treasury.gov
    participant Y as Yahoo/Nasdaq

    B->>F: GET /api/scenarios
    F->>N: list_scenarios() + latest_summaries()
    Note over F,N: ⚠ 無 user 過濾：回傳資料庫裡「全部」劇本
    N-->>B: 全部劇本列

    loop 每個 distinct symbol（共 D 輪，各是一次獨立 invocation）
        B->>F: POST /api/scenarios/refresh-run {remaining ids}
        F->>C: GET delayed_quotes/options/{sym}.json（1–5.6 MB）
        Note over F,C: ❗ 無快取、無 single-flight、無 429 backoff
        C-->>F: 整鏈 JSON
        loop 該 symbol 底下每個劇本
            F->>N: get_rate_cache()
            alt 今天還沒抓過（全站第一次）
                F->>T: CSV → (失敗才) XML → (失敗才) 前一年 CSV
                F->>N: save_rate_cache()
            end
            F->>N: get_dividend_cache(symbol)
            alt 這個 symbol 今天還沒抓過
                F->>Y: chart?events=div → (失敗才) FMP → (失敗才) Nasdaq
                F->>N: save_dividend_cache()
            end
            Note over F: 引擎：6 個 subtype 展開、枚舉、估值
            F->>N: save_result（view JSONB 12.18 MiB @3 families）
            F->>N: save_snapshot（0.48–2.55 MiB）
            F->>N: append_event
        end
        F-->>B: {results:[...], remaining:[...]}
    end
```

---

## 4. 詳細頁（Historical IV）的額外外部呼叫

```mermaid
flowchart LR
    P["詳細頁掛載"] --> S["GET /api/settings"]
    P --> G["GET /api/scenarios/{id}<br/>（project_for_detail，0.46 MiB）"]
    P --> H["GET .../iv-history"]
    H -->|"每條腿（1–3 條）"| EC["ensure_contract_history<br/>ivpipeline.py:547"]
    EC -->|"(contract, today) miss"| MD1["api.marketdata.app<br/>options/quotes（1 credit / 1000 quotes）"]
    EC -->|"hit"| CH[("contract_iv_history")]
    H --> RCR["_fetch_rate_curve_rows<br/>→ treasury_year_cache"]
    H --> DIV["dividend_loader<br/>→ dividend_cache"]
    H -->|"backfill_pending: true 時"| BF["POST .../iv-history/backfill"]
    BF -->|"(symbol, today) miss"| MD2["api.marketdata.app<br/>options/chain?date=<br/>≤ 25 天 × ≤ 4 到期日 = ≤ 100 次"]
    BF -->|"hit"| IR[("iv_backfill_runs")]
```

閘門：Historical IV 未解鎖（未選自訂 provider 或 token 未驗證通過）時，
`_iv_history_gate()` 直接 403，**一個 vendor 請求都不發**
（`main.py:1258-1278`）。

---

## 5. 一句話總結

> **Treasury、Dividend、Historical IV 這三條線今天已經是 shared-data
> 架構**（Neon 為底、per-key、跨 invocation、跨使用者共用）；
> **Option Chain 這條線完全沒有共用機制**——它是唯一「使用者數量直接
> 乘上 vendor request 數量」的資料流，而且它同時是量體最大（1–5.6 MB）、
> 頻率最高、且上游會 429 的那一條。
