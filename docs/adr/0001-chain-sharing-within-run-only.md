# ADR-0001：Chain 共用只存在於一個 Refresh Run 之內，不跨 invocation

- 狀態：Accepted
- 日期：2026-08-24
- 來源：`/improve-codebase-architecture` Architecture Review 輪（回報#025／#026）

## 背景

Option Chaser 的後端是 Vercel 上的單一 Python serverless function。
跨 invocation **沒有共享記憶體**，實例可能每次請求都冷啟動。

PERF-06（issue #182）為了讓「同一 symbol 的多個劇本不要各抓一次
option chain」，把整份 chain snapshot 寫進 Neon 的 `chain_cache` 表，
以 symbol 為鍵、15 秒 wall-clock TTL。

Architecture Review 的證據顯示這個補償機制被它要補償的流量形狀擊敗：

- 前端一輪刷新是**嚴格串行**的（`src/App.tsx:187` 逐一 `await
  refreshOne()`），每個劇本一次獨立 invocation。批次尾端的請求很容易
  在第一次抓取的 15 秒之後才開始，於是 miss。
- miss 路徑是**純增加成本**：多一次 Neon SELECT，再把整條 chain 當
  JSONB 寫回——而同一份 payload 本來就已經寫進 `snapshots` 表
  （`main.py:1181`），變成一次刷新兩次大寫入。
- hit 路徑是拿「Neon 讀取數百 KB JSONB ＋ 重建千級 dataclass」去換掉
  「一次 Cboe CDN 的 GET」，沒有任何證據顯示前者比較便宜。
- 原始 benchmark 量的是「省掉幾次 upstream 抓取」，從未計入「新增
  幾次 Neon 往返」，所以這筆替換成本在所有記錄的數字裡都不可見。

## 決策

**Chain 的重複抓取，只在單一 Refresh Run 的記憶體內去重。**

- Refresh Run module 在一次 invocation 內，用普通 `dict[symbol,
  ChainSnapshot]` 讓同 symbol 的劇本共用同一次抓取。
- **不做**任何跨 invocation 的 chain 快取：`api_app/chain_cache.py`
  模組、`chain_cache` 資料表、`chain_cache_ttl` DI 參數全部刪除。
- 「同一份資料在 process 記憶體裡共用」與「把資料寫進資料庫再讀回來」
  是兩件不同的事，後者不是前者的替代品。

## 理由

去重的正確作用域是**一個使用者動作**（一輪刷新），不是一段時間窗。
把作用域改成「一次 invocation 內」之後，共用是確定性的（不靠時間
猜測）、免費的（純記憶體）、且不需要任何快取失效策略。

## 後果

- 使用者在 15 秒內連按兩次刷新，會抓兩次 chain。接受：這是罕見動作，
  且第二次刷新本來就應該拿到新報價。
- `snapshots` 表仍然保留每輪的快照（原始資料區與稽核需要它），但一輪
  刷新不再重複寫入同一份 chain。
- 其餘三個以 Storage 為底的快取（`rate_cache`／`dividend_cache`／
  `treasury_cache`）**不受本 ADR 影響**：它們快取的是「當天／當年
  只會有一個值」的低頻慢變資料，跨 invocation 共用有實質意義，且
  payload 遠小於 option chain。

## 不要重新提案的事

- 「把 chain 快取進 Postgres／KV／Redis 以跨請求共用」——除非流量形狀
  本身改變（例如改成常駐 server 或前端改成大量並行小請求），且有
  同時計入新增往返成本的量測。
