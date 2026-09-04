# Wayfinder Map：Scaling Foundation

對應 **OPTION-SCALING-WAYFINDER-001**。日期 2026-09-03。

**基準**：`origin/master` HEAD `864dd5c`（Initial V2 已 merge 上線）。

**輸入**：`docs/research/market-data-lifecycle-scaling.md`、
`docs/research/market-data-current-state-map.md`（同日完成），以及本輪對
兩份研究引用結論直接相關的 production code／ADR／issue 的逐項覆核。

**本輪性質**：Wayfinder。**只畫地圖**——不改 production code、不寫
spec、不開票、不做 migration、不開 PR、不自行回答 Owner Decision。

**Destination**：收斂出 Option Chaser 從今天的單人產品走到可安全支撐
至少 1,000 active users 之前，**最小必要**的 Scaling Foundation——
以及同樣重要的，**哪些看起來該做、其實可以不做**。

**證據標示**：**【研究】**＝上述兩份研究文件已建立的事實（本輪抽查
覆核過，覆核結果如有出入會標明）；**【本輪覆核】**＝本輪自己讀
production code 確認或新推導出來的；**【推估】**＝模型推算，非量測；
**【未決】**＝需要 Owner 裁示，本文不作答。

---

## 0. 三句話版本

1. **今天最貴的兩個問題，都不需要任何快取、任何 lock、任何排程就能
   解決**——`results.view` 的 retention（U=1 就會撞牆）與 user
   ownership（把負載從 O(U²) 變成 O(U)）。這兩件是 Scaling Foundation
   的**主體**。
2. **Option chain 共用（大家最直覺會想先做的那一個）本輪明確建議
   「先不要做」**——不是因為不重要，是因為 ADR-0001 自己設下的重開
   門檻要求 production 量測，而我們今天連「昨天對 Cboe 發了幾次請求」
   都答不出來。**先裝計數器，再談要不要蓋快取。**
3. **但 chain 這條線有一件事現在就要做，而且與快取無關**：Cboe 會
   429、程式碼完全不處理、唯一備援結構上不可達。這是「全站中斷且
   無自動復原」，不是效能問題。

---

## 1. Current State（引用研究，本輪覆核）

### 1.1 已經做對、本輪不動的

| 項目 | 現況 | 本輪態度 |
|---|---|---|
| Treasury 快取 | Neon 單列、market-day 語意、7 天陳舊備援 | **不動** |
| Dividend 快取 | Neon per-symbol、market-day、90 天陳舊備援 | **不動** |
| Treasury PIT（歷史）快取 | per-year，過去年份永久，PIT 安全靠鍵設計鎖死 | **不動** |
| Historical IV 快取 | per-contract／per-symbol | **不動** |
| 快取鍵設計 | 全部以「公開市場事實」為鍵（symbol／year／contract／market-day），**沒有一個以 user 為鍵** | **不動，而且這正是後面 user 隔離時的正確方向** |
| Run 內 chain 去重 | ADR-0001，純記憶體 dict | **不動** |
| 資料來源揭露 | `market_day`／`as_of`／`stale`／`rate_note`／`q_note` | **不動** |

> **這一節的重點是「不要因為本階段叫 Scaling Foundation 就重做已經
> 正確的東西」。** 研究的結論很明確：本專案在慢變資料上的快取設計
> 相當成熟，缺口高度集中。

### 1.2 五個已確認的缺口（研究 P0 分級，本輪逐項覆核）

| # | 缺口 | 本輪覆核結果 |
|---|---|---|
| G1 | `results.view` 單列 12.18 MiB、96.4% 是 `all_candidates`、**零 retention** | ✅ 成立。另**新增發現**見 §3.2 |
| G2 | 無 user ownership（#59 仍 open）→ 開站刷新全站劇本 → O(U²) | ✅ 成立。`main.py:838-848` 無過濾、`main.py:1065-1067` 直接吃 `list_scenarios()` |
| G3 | Cboe 會 429（實測 `retry-after: 34`），adapter 一律 `except Exception → FetchError`，唯一備援 yfinance production 不可達 | ✅ 成立。`data/cboe.py:96-105` 逐行確認 |
| G4 | `result_history()` 把該劇本**全部**歷史 view 完整讀出，而 `/results` 只要時間戳 | ✅ 成立。`postgres.py:550-556` `SELECT {_RESULT_COLS}`（含 `view`）、`main.py:1127-1133` |
| G5 | 三條線都沒有 single-flight | ✅ 成立。`rate_cache.py:86+` 是裸 read-fetch-write |

### 1.3 本輪新增的三項覆核發現

**F1｜`all_candidates` 的資訊價值遠低於它的體積——UI 只讀其中一個
欄位。**【本輪覆核】

`store._history_entry()` 每筆存 5 個欄位（`candidate_key`／`expiry`／
`cost`／`baseline_return`／`rank_in_expiry`）。但前端實際消費路徑：

```
src/SpreadHistory.tsx  → 只畫 cost（第 64、123、158 行）
src/spreadHistory.ts   → 只讀 e.cost 與 e.analyzed_at（第 46、58、86、87 行）
```

`rank_in_expiry` 在整個 `src/` 只出現在 `api.ts:920` 的**型別宣告**，
**沒有任何一處讀取**；`baseline_return` 同樣只在型別與註解裡；
`spot` 也不進圖表。

> **也就是說：74,011 筆 × 5 欄位，最後只有「一條曲線的 y 值」會被
> 使用者看到。**

**F2｜「歷史斷點」的產品語意已經存在，這降低了縮減保存範圍的風險。**
【本輪覆核】

`store.spread_cost_history()` docstring 明文：某次快照找不到這個
candidate_key 時「該筆仍然入列，但 cost／baseline_return／
rank_in_expiry 皆為 None：**如實呈現斷點，不插值、不跳過、不報錯**」。

> 這是既有、刻意的設計。它的意思是：**如果未來只保存一部分候選的
> 歷史，畫面上會自然呈現成斷線，而不是壞掉。** 這件事讓 §3 的
> 選項空間比它看起來大。

**F3｜`provider_credentials` 是全站一把 token，且沒有 user 欄位。**
【本輪覆核，`postgres.py:176`】

這在 multi-user 下同時是三個問題：隱私（A 的 token 被 B 用）、成本
（A 的 Market Data credits 被 B 燒掉——研究 §6.5 顯示自訂 chain 來源
一次要 2,414–12,534 credits）、以及**它會反過來限制 chain 共用的設計**
（見 §4.4）。

---

## 2. Destination Criteria

Foundation 完成時，下面每一條都應該可以用一個測試或一個查詢回答
「是」：

| # | 判準 | 對應 Decision Cluster |
|---|---|---|
| D1 | 一個 user 的任何動作，不會刷新、不會讀到、不會寫入另一個 user 的劇本 | A |
| D2 | 一輪刷新的 chain 抓取數，是「這個 user 自己的 distinct symbol 數」，不是「全站劇本的 distinct symbol 數」 | A |
| D3 | `results`／`snapshots` 有明確的 lifecycle，資料庫成長速率是可預測、有上界的 | B |
| D4 | 開一次歷史走勢圖，不會從 Neon 讀出整個劇本的全部完整 view | B |
| D5 | Cboe 回 429 時，系統不會形成 retry storm；使用者看到的是明確、可理解的狀態，不是無差別的「抓不到報價」 | C |
| D6 | Treasury／Dividend 的當日第一次 cold miss，不會讓使用者那一輪刷新逾時 | D |
| D7 | 任一 vendor 掛掉時，讀取既有結果的路徑仍然可用；哪些功能降級、降到什麼程度，是**寫下來的**而不是碰運氣 | Cross-cutting |
| D8 | 可以回答「昨天對 Cboe 發了幾次請求」「chain 命中率多少」「`results` 表多大」 | Cross-cutting |

**刻意不列入 Destination 的**：
- 「同 symbol 同 freshness window 只打一次 vendor」——**這是 §4 的
  未決議題，不是既定目標**。把它寫進 Destination 等於在 Owner 裁示
  之前先替他決定了。
- 任何延遲數字（p50/p99）目標——今天沒有基準線，訂了也無從驗證。

---

## 3. Decision Cluster B：Result / Snapshot Storage Lifecycle

> **本文把 B 放在 A 之前，因為它是唯一一個「就算永遠只有 Owner 一個
> 人用，也一定會撞牆」的問題。** 研究：Neon Free 0.5 GB ÷ 12.18 MiB
> ＝ **42 次刷新**（壓縮後上界 402 次）。

### 3.1 三個層次的問題，不要混在一起

| 層次 | 問題 | 今天 |
|---|---|---|
| **B-1 Current result** | 使用者「現在」看的那份結果需要什麼 | 存完整 view（12.18 MiB），但送到前端的投影只有 **0.46 MiB**【研究 M3】 |
| **B-2 Historical facts** | 「回頭看歷史」真正需要什麼 | 每次刷新完整存一份 view |
| **B-3 Heavy artifacts** | `all_candidates`／matrices／raw chain snapshot | 全部永久存 |

### 3.2 B-1：存的東西比送出去的大 26 倍

【研究 M1/M3 ＋ 本輪覆核】

```
stored view        12.18 MiB   ← 寫進 results.view
project_for_detail  0.46 MiB   ← 前端實際收到的（T13/#231 的投影）
                    ────────
                    約 26 倍
```

投影是在**讀取時**做的，所以體積差全部沉在資料庫裡。

**選項（不裁定）**：

| 選項 | 做法 | 得到 | 失去 |
|---|---|---|---|
| B1-a | 維持現狀 | 完整重放能力、debug 方便 | 26× 儲存 |
| B1-b | 存投影後的形狀，另存重放所需的最小輸入 | 大幅縮減 | 無法對舊結果重跑新版引擎 |
| B1-c | 存完整 view 但壓縮（`bytea` + zlib） | 8–9.6×【研究 M4】，改動小 | 仍是 O(每次刷新)；查詢要先解壓 |

⚠ **一個必須明說的取捨**：「為了之後能 debug 所以永久保存完整
production payload」是一個**代價明確、但收益從未被量化**的決定。
本 repo 至今沒有任何一次除錯是靠讀回歷史 `results.view` 完成的
（研究與 CLAUDE.md 全文皆無此紀錄）。

### 3.3 B-2：歷史上真正被使用的，是 4 個欄位

這是本輪最強的單一發現（§1.3 F1）。今天為了服務**一條只畫 `cost`
的折線圖**，每次刷新保存 74,011 筆 × 5 欄位。

**canonical historical fact 的最小集合**：

```
(scenario_id, analyzed_at, candidate_key, cost)
```

**選項（不裁定）**——差別在「哪些候選的歷史值得留」：

| 選項 | 保存範圍 | 量級【推估】 | 後果 |
|---|---|---|---|
| B2-a | 全部候選（現狀） | ~79,000 筆/刷新 | 任何候選都有完整歷史 |
| B2-b | **UI 可觸及的候選**（`expiry_top10` ∪ `expiry_best` ∪ representative） | ≤5 期 × 10 × 3 family ≈ **150 筆/刷新**（約 500×↓） | 使用者點得到的每個候選都有歷史；某次跌出前十的候選那一格顯示斷點（F2 已支援） |
| B2-c | 只有代表候選（champion） | 1–3 筆/刷新 | 只有頭條候選有歷史；點開其他候選看不到走勢圖 |
| B2-d | 只保存使用者「追蹤」的候選 | 最小 | **需要新增「追蹤」這個產品概念**——這已經超出 scaling foundation |

⚠ B2-d 明確標記為 **新產品概念**，本文不建議在 foundation 階段引入。

**另一個獨立維度：留多久？**

| 選項 | 說明 |
|---|---|
| 全部保留 | 現狀 |
| 保留最近 N 次 | 簡單、上界明確 |
| 保留最近 N 天 | 與「走勢圖要看多長」直接對齊 |
| 降採樣（每天保留一筆） | 前端已有 day/week/month 降採樣（`spreadHistory.ts`），但那是**顯示層**降採樣；儲存層降採樣是另一回事 |

**【未決 Owner Decision】** 見 §9-Q2。

### 3.4 B-3：raw chain snapshot 是第二大的東西

`snapshots` 表每次刷新寫 0.48（TLT）–2.55（SPY）MiB，同樣無 retention。

它的唯一消費者是 `/raw-data`（「原始資料（當次快照）」展開區）。

**選項（不裁定）**：

| 選項 | 後果 |
|---|---|
| 只保留每個劇本**最新一次**快照 | `/raw-data` 語意本來就是「當次快照」，功能不變；歷史稽核能力消失 |
| 保留 N 天 | 折衷 |
| 移出 Postgres（object storage） | 便宜，但新增一個 vendor 依賴——**本文標記為 AT_1K 之後才值得評估**，foundation 階段不建議 |
| 維持現狀 | 與 `results` 一起吃掉 Neon |

### 3.5 B-4：讀取路徑（G4）——與上面獨立、且是純 bug 等級

```python
# postgres.py:550-556
SELECT {_RESULT_COLS} FROM results WHERE scenario_id = %s   # _RESULT_COLS 含 view
```

兩個消費端：
- `/results`（`main.py:1127-1133`）——**只要 `analyzed_at`**
- `/history`（`main.py:1135-1146`）——只要每份 view 裡的**一筆** entry

> 一個刷新過 30 次的劇本，開一次歷史走勢圖 ＝ 從 Neon 讀出約
> **365 MiB** 並反序列化【研究 P0-4】。Neon Free egress 每月只有 5 GB。

**這一項沒有選項，只有做法差異**：`/results` 改成
`SELECT analyzed_at`；`/history` 的最小改動是新增一個窄查詢。
若 B-2 選了拆窄表，這一項**自動消失**。

### 3.6 B 的收斂建議（供 spec 參考，非裁示）

- **B-1／B-3 可以先不動**（維持完整保存），只要 **B-2 拆出去 ＋ 加上
  retention**，成長率就已經從「每次 12.18 MiB」降到「每次約 0.4 MiB
  ＋ 少量窄列」【推估】。
- **B-4 應與 B-2 同一批做**（拆窄表後它自然解決）。
- 這一整塊**不依賴任何其他 cluster**，可以今天就開工。

---

## 4. Decision Cluster A：User Isolation Boundary

### 4.1 為什麼它是「其他一切的前置」，但**不是**每件事的前置

研究說「user 隔離是任何 scaling 討論的前置條件」。本輪覆核後要把這句
話講得更精確：

| 說法 | 是否成立 |
|---|---|
| 「沒有 user 隔離，所有負載數字都是 O(U²)、因此無意義」 | ✅ 成立【研究 §7.2】 |
| 「因此所有 scaling 工作都要等它」 | ❌ **不成立**。B（retention）在 U=1 就該做、與 owner 無關；C 的 429 韌性也與 owner 無關 |
| 「chain 快取設計要等它」 | ⚠ **部分成立**——快取本身是 user-agnostic 的，但**是否值得做**取決於 U，而 U 取決於它 |

> **正確的說法：A 是「開放多使用者」的前置，不是「所有 scaling 工作」
> 的前置。**

### 4.2 兩階段拆分——本文建議的分法

| 階段 | 內容 | 為什麼可以分開 |
|---|---|---|
| **A-1 Ownership / data boundary** | 每個 per-user 資料表加 owner 維度；storage port 的每個查詢帶身分；API 每個端點解析身分。今天的身分解析器**固定回傳同一個「solo owner」id** | 這一層解掉的是**correctness 與 privacy**：refresh scope、資料可見性。它不需要任何登入 UI |
| **A-2 Authentication product layer** | 真正的登入／憑證／session／帳號生命週期 | 這一層解的是「怎麼證明你是誰」，是**產品功能**，可以晚一步 |

**A-1 的關鍵性質**：它是**backward-compatible** 的——今天所有既有
資料 backfill 成 solo owner id，行為與現在**逐位元相同**；之後換上
真的身分解析器時，**只有那一個函式改變**。

**【未決】** 既有資料的 transition：全部歸給 solo owner（自然選擇），
還是別的處理？見 §9-Q1。

### 4.3 哪些資料 per-user、哪些必須維持 system-wide

【本輪覆核 `postgres.py` 全表】

```
必須 user-scoped（使用者自己的東西）
  ├── scenarios              ← 劇本本體
  ├── results                ← 該劇本的分析結果
  ├── snapshots              ← 該劇本的原始快照
  ├── events                 ← 該劇本的事件
  ├── provider_credentials   ← ⚠ 今天是全站一把（§1.3 F3）
  ├── data_source_settings   ← 今天是全站一份
  └── provider_verifications ← 跟著 credential 走

必須維持 system-wide shared（公開市場事實，按 user 切分會破壞共用）
  ├── rate_cache             ← 全站當日一條曲線
  ├── treasury_year_cache    ← per-year
  ├── dividend_cache         ← per-symbol
  ├── contract_iv_history    ← per-contract
  └── iv_observations / iv_backfill_runs  ← per-symbol

不屬於任何一邊
  └── diagnostics            ← 營運資料。⚠ 但 context 白名單裡若含
                                 使用者輸入的 symbol，multi-user 下
                                 需要重新檢視（見 §9-Q1 附註）
```

> **這條線非常乾淨，而且今天的鍵設計已經站在對的一邊。** 五張快取表
> 沒有一張需要加 owner 欄位——這不是巧合，是研究 §8.1 指出的「本專案
> 快取鍵設計相當成熟」的直接後果。

### 4.4 A 對 C 的一個硬約束（本輪推導）

**`provider_credentials` 全站共用（F3）＋ chain 共用快取，如果同時
存在，會產生一個新的隱私／成本問題**：

> 使用者 A 設了自己的 Market Data token，A 的一次刷新用 A 的 token
> 抓了 TLT 全鏈（燒掉 2,414 credits）。如果這份資料進了共用快取，
> B 就用到了 A 花錢買的資料。

**推導出的設計約束**（不是裁示，是限制）：

- 共用快取的鍵必須含**來源**，不只 symbol：`(symbol, source)`。
- **自訂來源（使用者自備 token）抓來的資料，不應該進共用快取**——
  否則就是把一個人的付費配額變成公共財。
- 反過來說：**預設來源（Cboe，公開 CDN）沒有這個問題**，它天生適合
  共用。

> 這條約束的實際效果是：**chain 共用只需要涵蓋預設來源那條路徑**，
> 設計範圍因此比想像中小。

### 4.5 明確不做

- ❌ enterprise RBAC、org／team、角色權限矩陣
- ❌ 多租戶資料庫分片
- ❌ 因為「未來可能多租戶」而預留的抽象層

> 需要的是**一個 owner 欄位＋一條身分解析縫**，不是一套權限系統。

---

## 5. Decision Cluster C：Option Chain Shared Lifecycle

> **本 cluster 是全圖唯一一個「本文建議刻意先不做主體」的地方。**
> 理由不是它不重要，是**做它的前提還沒到位**。

### 5.1 先拆成兩件互不相干的事

| | C-1 韌性（429 / 降級） | C-2 共用（快取 / single-flight） |
|---|---|---|
| 解什麼 | 上游限流時**不要全站中斷、不要 retry storm** | 減少上游請求數 |
| 需要 Owner 先裁示嗎 | 只需要「使用者看到什麼」的產品決策 | **需要 freshness 契約**，否則 TTL 是憑空挑的 |
| 需要 production 量測嗎 | **不需要**——後果已知 | **需要**（ADR-0001 自己的重開門檻） |
| 何時做 | **NOW** | **等證據** |

**這個拆分是本 cluster 最重要的結論。** 研究把它們都放在「Option
Chain」底下，容易讓人以為要一起做。

### 5.2 C-1：429 韌性（建議 NOW）

【研究 §5.5 ＋ 本輪逐行覆核 `data/cboe.py:96-105`】

```python
except Exception as e:            # ← HTTP 429 走這條
    raise FetchError(...)         # 不看 status、不讀 retry-after、無 backoff
```

後果鏈（每一環都已覆核）：

```
429 → FetchError → service.fetch_chain 退到 yf
   → import yfinance → ImportError（不在 [project] dependencies）
   → FetchError → 使用者看到 stage:"fetch"「抓不到報價」
   → 使用者按重試 → 又 429 → retry storm → 限流窗被自己續命
```

**要決定的是「使用者看到什麼」，不是工程細節**——見 §9-Q4。工程面
的可選項（backoff／circuit breaker／honor `retry-after`／禁止立即重打／
顯示上次成功結果）彼此不互斥，但**產品語意必須先定**。

⚠ **`data/cboe.py` 的 docstring 目前只寫「無官方文件、無 SLA」，
沒有記載它會 429**——這本身是一個應該修正的事實記載。

### 5.3 C-2：共用——為什麼建議「先量測，再決定」

ADR-0001 明文：**不要重新提案，除非「流量形狀本身改變，且有同時
計入新增往返成本的量測」。**

研究誠實揭露：**沒有 production 量測**，達不到這個門檻。本輪覆核
同意這個判斷，並補充三點：

| ADR 的理由 | 今天 |
|---|---|
| 「miss 路徑純增加成本：多一次 Neon SELECT ＋ 把整條 chain 當 JSONB 寫回，而同一份 payload 本來就寫進 `snapshots`」 | **仍然完全成立，而且更強**——SPY snapshot 實測 2.55 MiB。**這是反對『把 chain 放進 Postgres』最強的論證，本輪同樣沒有推翻它。** |
| 「hit 路徑沒有證據比一次 Cboe GET 便宜」 | Cboe TLT GET 實測 0.23–0.60s；1 MiB JSONB 從 Neon 讀出＋重建 dataclass **很可能不會更快** |
| 「跨 invocation 沒有共享記憶體」 | ⚠ **已被平台改變推翻**（fluid compute）——但見 §7.1，這開啟的是一個**不能當 correctness layer** 的選項 |

**本輪新增的觀察**：ADR 只比較了「Postgres 快取 vs 不快取」。它從未
評估過第三個選項——**Vercel Edge CDN**。如果「取得某 symbol 的鏈」
存在為一個 **GET 端點**，`s-maxage` + `stale-while-revalidate` 可以在
**平台層**做共用：零 Neon 往返、零額外寫入、正好繞開 ADR 最強的那個
反對理由。

> ⚠ 但這**不是提案**——它會改變 API 形狀（POST refresh-run 天生不可
> 快取），而且我沒有量測。**登記在案，供 Owner 決定要不要納入重開
> ADR-0001 時的評估範圍。**

### 5.4 Freshness Contract——必須從產品語意推導，不能憑直覺挑數字

**這是 C-2 的真正前置。** ADR-0001 當初的 15 秒就是憑直覺挑的。

**從產品語意可以推導出的邊界**（不是答案，是約束）：

| 事實 | 推導出的約束 |
|---|---|
| Cboe 端點路徑本身叫 `delayed_quotes`——**它本來就已經是延遲報價**【研究 §5.7】 | 在一份已經延遲的資料上再加一個共用窗，**相對新鮮度損失是二階的** |
| 刷新只有三個時機（開站／手動鈕／建立劇本），**不是連續輪詢**【研究 §2.1】 | 使用者不會期待秒級即時；他期待的是「我按下去的時候是新的」 |
| 產品定位是 **Scenario Bet Ranking**（劇本下注排名），不是即時交易執行 | 候選排名對數十秒級的報價變動不敏感 |
| 使用者「按下刷新鈕」是一個**明確的意圖表達** | 手動刷新是否應該繞過快取，是獨立於 TTL 的另一個決策 |

**【未決 Owner Decision】** 見 §9-Q3。

### 5.5 Sharing scope / cache location / stampede — 留給裁示後

這三題（研究已列出完整選項矩陣）**在 §9-Q3 的 freshness 契約與
§9-Q5 的量測結果出來之前，任何收斂都是猜測**。本文因此不預先收斂，
只記錄 §4.4 推導出的硬約束：**共用只涵蓋預設來源（Cboe），鍵必須
含 source。**

---

## 6. Decision Cluster D：Treasury / Dividend Lifecycle

> **本 cluster 的正確態度是「幾乎什麼都不要做」。**

### 6.1 研究已證明：這兩條線的**請求量不是 scaling 問題**

Treasury 全站每市場日約 1 次；Dividend 每 (symbol, 市場日) 1 次。
即使 U=1,000，Treasury 的期望上界也只有 2–3 次【研究 §3.7 推估】。

### 6.2 真正的問題是延遲，不是負載——而且它有一個具體的踩點

【研究 P0-5 ＋ 本輪推導】

```
Treasury cold miss 最壞 = 3 × 15s = 45s（CSV → XML → 前一年 CSV）
REFRESH_RUN_BUDGET      = 45s
vercel.json maxDuration = 60s（本專案自設）
```

> 每個市場日的**第一批**使用者，可能在一次刷新裡就把整個時間預算耗在
> 等 Treasury 上；再加上 chain 抓取與分析，有機會直接撞到 60 秒被平台
> hard kill。

**這是 latency／timeout 的 correctness 問題，不是 capacity 問題。**
可選的解法互不互斥：

| 解法 | 解到什麼 | 代價 |
|---|---|---|
| Single-flight | 只有第一個人等，其餘等它 | 需要跨 instance 協調（見 §7.2） |
| Stale-while-revalidate | **沒有人要等**——先回昨天的，背景更新 | 需要背景執行機制（⚠ Python runtime 是否有 `waitUntil` 等價物，研究**未查證**） |
| 縮短 timeout | 最壞情況變短 | 弱網路下失敗率上升 |
| 排程 warm（cron） | 使用者永遠不會 cold miss | 見 §7.3 |

> **本文的判斷**：Treasury 只有一條曲線、每天只變一次、陳舊 7 天內
> 幾乎無成本——**stale-while-revalidate 的收益/風險比最好**。但
> 「Python runtime 有沒有背景執行機制」是一個**未查證的事實**，
> 它會直接決定可行性 → 見 §9-Q6（targeted research need）。

### 6.3 Dividend：single-flight 的價值比 Treasury 更低

per-symbol 的 stampede 只會發生在「同一個 symbol、同一個市場日、
同一個 0.7 秒視窗內、有多個並發冷請求」——這需要多個使用者同時第一次
看同一個標的。**在 1,000 users 的量級下，這是低機率事件，且後果只是
多打幾次 Yahoo。**

### 6.4 明確劃出去：Yahoo 替換 ≠ Scaling Foundation

研究實測：`query2.finance.yahoo.com/robots.txt` ＝ `Disallow: /`，
且無公開 API、無 SLA。

**本文明確判斷：這不屬於 Scaling Foundation。**

理由：
1. 它是**合規／治理決策**，不是容量決策——換不換、換去哪，是 Owner
   的商業判斷。
2. 它需要**自己的 vendor 研究**（候選、成本、資料品質驗證），與本
   foundation 的依賴鏈完全不相交。
3. 它的**風險曲線與 U 無關**——1 個使用者和 1,000 個使用者面對的是
   同一個「這條依賴隨時可能被單方面斷掉」的風險。

> **建議另開 data-provider migration 這條獨立線**，不要塞進
> foundation。列為 §9-Q7 給 Owner 知情，但不要求現在決定。

### 6.5 D 的收斂建議

| 項目 | 建議 |
|---|---|
| Treasury／Dividend 快取本體 | **不動** |
| Treasury cold-miss 延遲 | 進 foundation（見 §8 Stage 4），做法待 §9-Q6 |
| Dividend single-flight | **不進 foundation**——收益低於複雜度 |
| Hot-symbol warming | **不進 foundation**（Hobby cron 一天一次，且是延遲優化） |
| Yahoo 替換 | **另開獨立線** |

---

## 7. Decision Cluster E：Runtime / Deployment / Scheduler

### 7.1 Process-local cache：只能是 L1 optimization，**絕不能是
correctness layer**

【研究 §6.3 官方文件 ＋ 本輪推導】

Vercel fluid compute 官方文件：「multiple invocations **can** share the
same physical instance」。

**關鍵字是 "can"，不是 "will"。**

Vercel 不承諾任何一件事：實例數量、實例生命週期、哪個請求落在哪個
實例、冷啟動頻率。因此：

> **任何「正確性」依賴行程內快取的設計都是不安全的。**
> 例如「我們保證同一個 freshness 窗只打 Cboe 一次」——這句話在
> process-local 快取上**無法成立**，因為你不知道有幾個 process。

**它能做什麼**：純粹的 hit-rate 優化。命中就省一次請求，沒命中就
照常走。**它的價值無法事先預測，也不該被寫進任何契約。**

> ⚠ 研究還揭露一個未查證項：**部署專案實際是否啟用 fluid compute
> 未經確認**（只能依「2025-04-23 後建立的新專案預設啟用」推定）。
> 這是一個廉價、應該先查清楚的事實 → §9-Q6。
>
> **2026-09-04 查證結果**：NOT_CONFIRMED——嘗試過六種 Vercel MCP
> 直接查詢路徑，對 `option-chaser` 專案全數 404／零可見度，非未查。
> 上面「"can" 不是 "will"」的論證不受影響、原樣成立。詳見
> `docs/research/runtime-targeted-scaling.md`。

### 7.2 是否需要 distributed cache / lock？

**本文判斷：foundation 階段不需要，而且不建議。**

| 選項 | 評估 |
|---|---|
| Redis / KV | 新增一個 vendor 依賴、新增一個 failure domain、新增成本。**在還沒證明 Postgres 不夠之前，這是 overengineering** |
| Postgres advisory lock | Neon 支援、零新 vendor。**如果真的需要 single-flight，這是第一選擇** |
| 不做 | 對 Treasury／Dividend 而言（§6.3）完全可接受 |

> **判準**：先把 §9-Q5 的計數器裝上去，看到真實的並發冷請求數之後，
> 再決定要不要 lock。

### 7.3 Scheduler：只有一個地方真的合理

| 資料 | 排程是否合理 | 理由 |
|---|---|---|
| **Treasury** | ✅ **合理，而且 Hobby 就做得到** | 每營業日 15:30 ET 更新一次；Hobby cron 一天一次剛好夠。**±59 分鐘抖動可以被排程時間吸收**——例如排在 UTC 21:00（＝ET 17:00），最晚 21:59 UTC 也還在當日發布之後、隔日開盤之前【本輪推導自研究 §6.3】 |
| **Dividend** | ❌ 不合理（全 universe） | universe 不封閉——`symbol` 只受 `^[A-Za-z.\-]{1,10}$` 約束，使用者可建立任何代號【研究 §4.5】 |
| **Chain** | ❌❌ 絕對不合理（全 universe） | 同上，且量體 1–5.6 MB／symbol |
| Hot-symbol warming | ⚠ 需要 Pro（一天一次不夠密），且是**延遲優化** | 延後 |

### 7.4 Hobby vs Pro：**不應該是架構的前置條件**

> **「升級付費方案」不是架構修復。**

本文的立場：

- **Foundation 的每一塊都應該 plan-independent**——在 Hobby 上就要
  正確運作。
- 唯一會被 plan 影響的是**可選的 warming 層**（需要比一天一次更密的
  cron），而 warming 本來就被本文排在 foundation 之外。
- ⚠ 但有一個**與架構無關、卻真實存在**的問題：研究未查證 **Hobby 的
  商業使用條款**是否適用於本專案。這是產品／合規問題，不是工程問題
  → §9-Q7。

### 7.5 順帶：一個應該修正的過時事實

研究發現本 repo 有 **7 處**寫著「60 秒函式硬性上限」（`CONTEXT.md:123`、
`api_app/main.py:62/72/1033/1053`、`option_chaser/service.py:71/1287`、
`docs/adr/0001:10`）。

本輪覆核 `vercel.json`：**`maxDuration: 60` 是本專案自己設的**，
fluid compute 下 Hobby 的 default 與 maximum 都是 300s。

> 這不是 scaling 問題，但**它是一個會讓後續設計沿用錯誤前提的過時
> 事實**。應該在 foundation 的某個階段順手更正（含 ADR-0001 的
> 「沒有共享記憶體」那句）。

---

## 8. Dependency Graph 與 Stage Map

### 8.1 依賴推導（不預設順序，逐條推出來）

**先問「誰真的擋住誰」：**

```
B（retention）        ← 不依賴任何人。U=1 就會撞牆。
C-1（429 韌性）        ← 不依賴任何人。後果已知，不需要量測。
Obs（最小量測）        ← 不依賴任何人。而且它是 C-2 的證據來源。
A-1（ownership 邊界）  ← 不依賴任何人。但它擋住「開放多使用者」。
─────────────────────────────────────────────
A-2（auth 產品層）     ← 依賴 A-1（要先有 owner 維度才有東西可綁）
D-latency             ← 不依賴任何人，但價值在 multi-user 後才顯著
C-2（chain 共用）      ← 依賴 Obs（證據）＋ Owner 的 freshness 契約
                        ＋ 依賴 A-1（§4.4 的 source 約束）
```

**推導出的關鍵洞察三則：**

1. **前四項彼此完全獨立**，可以任意順序、甚至平行。這是好消息——
   foundation 的主體沒有長鏈依賴。
2. **Obs 必須早於 C-2**，這是一條**非顯而易見**的依賴：ADR-0001
   自己設定的重開門檻要求量測，而我們今天沒有任何計數器。
   **不先裝計數器，C-2 的討論就只能繼續停在猜測。**
3. **A-1 對 C-2 有設計約束**（§4.4：共用不得涵蓋自訂來源），所以
   即使 C-2 先做，也必須先知道 A-1 會長什麼樣。

### 8.2 Stage Map

> 每個 stage 只說：解哪個風險、前置依賴、是否改 schema、是否影響
> production 行為、rollout / rollback 要點。**不開票。**

---

#### Stage 0｜最小可觀測性

- **解哪個風險**：D8。今天無法回答「昨天對 Cboe 發了幾次請求」，
  因此 C-2 的討論**結構上無法收斂**。
- **前置依賴**：無。
- **改 schema**：可能不需要——`diagnostics` 已有 `emit()` 與 structured
  JSON log 機制，但目前只有 `warning`／`error` 落盤（`main.py:1215-1233`）。
  可選：純 log（零 schema）／新增輕量計數表。
- **影響 production 行為**：不應該有。純觀測。
- **rollout / rollback**：純加法，可隨時關閉。
- **最小指標集**（不要建 observability platform）：
  `chain fetch count`、`chain 429 count`、`stale serve count`、
  `treasury/dividend cold miss count`、`results 表大小 / 列數`、
  `單列 view 大小分布`、`refresh 端到端延遲`。

#### Stage 1｜Storage lifecycle

- **解哪個風險**：D3、D4。**唯一在 U=1 就會撞牆的問題。**
- **前置依賴**：無。（若同時要做 A-1，兩者共用一次 migration 窗較省，
  但**不是依賴**。）
- **改 schema**：**是**（拆窄表 ＋ retention）。
- **影響 production 行為**：歷史走勢圖的可見範圍可能改變（取決於
  §9-Q2 選哪個）。**這是使用者看得到的變化，必須明說。**
- **rollout / rollback**：
  - 新窄表可以**先雙寫**（舊 `all_candidates` 保留、新表同步寫），
    確認資料一致後才切讀取端，再才停止舊寫入——三步都可獨立 rollback。
  - retention 的刪除是**不可逆**的：建議先只對「新資料」套用，舊資料
    的清理另外一次有意識的操作。

#### Stage 2｜Chain vendor 韌性（C-1）

- **解哪個風險**：D5。全站中斷且無自動復原。
- **前置依賴**：**Owner 對「使用者看到什麼」的裁示**（§9-Q4）。
- **改 schema**：否（除非降級狀態要落盤）。
- **影響 production 行為**：**是**——使用者在 vendor 限流時看到的東西
  會不同。這正是要做的事。
- **rollout / rollback**：backoff／circuit breaker 的參數應可調；
  circuit breaker 誤開會讓功能在 vendor 其實健康時仍不可用，因此
  **必須有手動 reset 或短的 half-open 週期**。

#### Stage 3｜Ownership boundary（A-1）

- **解哪個風險**：D1、D2。privacy ＋ O(U²)→O(U)。
- **前置依賴**：**Owner 對既有資料 transition 的裁示**（§9-Q1）。
- **改 schema**：**是**（per-user 表加 owner 維度 ＋ backfill）。
- **影響 production 行為**：**在單人情境下應為零**——身分解析器固定
  回傳 solo owner，所有查詢結果與今天相同。這是這個階段的驗收判準。
- **rollout / rollback**：
  - 欄位先加成 nullable ＋ backfill ＋ 再設 NOT NULL，三步可分開。
  - 查詢帶身分這一步是**行為改變點**，應該有「單人情境下回傳集合
    與改動前逐位元相同」的回歸測試（比照本專案既有的 bitwise 凍結
    慣例）。

#### Stage 4｜Treasury cold-miss 延遲

- **解哪個風險**：D6。每市場日第一批使用者可能整輪逾時。
- **前置依賴**：§9-Q6 的 targeted research（Python runtime 背景執行
  機制是否存在）——它決定 stale-while-revalidate 可不可行。
- **改 schema**：否。
- **影響 production 行為**：使用者可能拿到「昨天的曲線 ＋ 明確標示」
  而不是等 45 秒。**揭露機制已經存在**（`rate_note`／`stale`）。
- **rollout / rollback**：純快取行為，可用旗標關閉。

#### Stage 5｜〔決策閘門〕Chain 共用要不要做

- **不是施工 stage，是一個明確的停等點。**
- **輸入**：Stage 0 的量測數字 ＋ §9-Q3 的 freshness 契約 ＋ §9-Q5 的
  ADR-0001 重開裁示。
- **輸出**：`C-2: NEEDED`（附數字依據）或 `C-2: NOT_NEEDED / DEFERRED`。
- **這個閘門必須有數字**，不接受「感覺應該要做」。

#### Stage 6｜Chain 共用（條件式，僅當 Stage 5 判定 NEEDED）

- **前置依賴**：Stage 0（證據）、Stage 3（§4.4 的 source 約束）、
  Stage 5（閘門）。
- **改 schema**：視選型（Edge CDN ＝ 否；Postgres ＝ 是）。
- **影響 production 行為**：**是**——使用者可能看到最多 τ 秒前的報價。
- **rollout / rollback**：TTL 應可調到 0（＝停用共用），作為即時
  rollback 手段。

#### Stage 7｜Authentication product layer（A-2）

- **解哪個風險**：真正開放註冊之前的最後一塊。
- **前置依賴**：Stage 3。
- **本文不展開設計**——它是產品功能，不是 scaling foundation。

---

### 8.3 Minimum Foundation vs Deferred

| 分級 | 項目 | 理由 |
|---|---|---|
| **NOW** | Stage 0 最小量測 | 沒有它，C-2 永遠只能猜 |
| **NOW** | Stage 1 storage lifecycle（B-2 ＋ B-4 ＋ retention） | **U=1 就會撞牆**（42–402 次刷新） |
| **NOW** | Stage 2 Cboe 429 韌性 | 後果是全站中斷且無自動復原，與 U 無關 |
| **NOW** | 更正 7 處過時的「60 秒硬上限」與 ADR-0001「無共享記憶體」 | 廉價；不更正會讓後續設計沿用錯誤前提 |
| **BEFORE_MULTIUSER** | Stage 3 ownership boundary（A-1） | privacy ＋ O(U²)。**開放多使用者的絕對前置** |
| **BEFORE_MULTIUSER** | `provider_credentials` 的 per-user 化（§1.3 F3） | 一個人的 token／配額被所有人用 |
| **BEFORE_MULTIUSER** | Stage 4 Treasury cold-miss | 單人時每天最多痛一次；多人時每天第一批都痛 |
| **BEFORE_MULTIUSER** | Stage 7 auth 產品層（A-2） | 定義上 |
| **AT_1K** | Stage 5／6 chain 共用（若閘門判定 NEEDED） | 研究 §7.5：高重疊情境下約 **U≈430** 才是絕對請求數的交叉點 |
| **AT_1K** | Dividend／chain 的 single-flight | 在此之前 stampede 是低機率、低後果事件 |
| **LATER** | Hot-symbol cron warming | 需要 Pro；且是延遲優化不是容量修復 |
| **LATER** | Redis／KV／distributed lock | 在證明 Postgres 不夠之前是 overengineering |
| **LATER** | snapshot 移出 Postgres 到 object storage | 新增 vendor 與 failure domain |
| **LATER** | 多 region | 上游都在美東，單 region 是對的 |
| **獨立線** | Yahoo → 其他 dividend provider | 合規／治理決策，需要自己的 vendor 研究 |
| **獨立線** | Market Data App 自訂 chain 成本揭露（研究 P1-5） | 產品揭露問題，非 scaling |

---

## 9. Owner Decisions

> 每一題都先用**白話與具體案例**問，技術後果放在後面。
> **本文不代答任何一題。**

### Q1｜「我的劇本」這件事，現在要做到什麼程度？

**具體情況**：今天任何人打開網址，都會看到**你所有的劇本**，也可以
編輯、封存、刪除它們；而且他一開站，系統就會把你的劇本全部重新
刷新一次。

**要決定的是**：

1. 現在是否就要把「資料是誰的」這件事做進去（**即使還沒有登入畫面**）？
2. 既有的劇本／結果／快照，全部歸給你一個人（最自然），還是有別的
   想法？
3. 「登入」這個產品功能，跟上面那件事**可以分開做**——你希望分開，
   還是一起？

**技術後果**：第 1 點是資料庫欄位＋查詢帶身分，在單人情境下行為與
今天**完全相同**（可用逐位元回歸測試證明）。它同時解決隱私與
「一個人開站刷新全站」這兩件事。第 3 點分開做的話，之後換上真的
登入只需要改一個函式。

> ⚠ 附註：診斷紀錄（`diagnostics`）的 context 裡可能含使用者輸入的
> symbol。multi-user 下這算不算需要隔離，一併請你裁示。

### Q2｜歷史走勢圖，你真正想看到多少？

**具體情況**：現在每按一次刷新，系統會把**當次算出來的全部候選**
（TLT 實測 **74,011 筆**）完整存進資料庫，每次約 **12.18 MB**。
Neon 免費額度是 0.5 GB——**大約 42 次刷新就滿了**。

而這 74,011 筆存進去之後，畫面上真正用到的**只有一條線的高度**
（淨成本）。其餘欄位在整個前端**一個字都沒有被讀過**。

**要決定的是**：

1. 你打開歷史走勢圖時，希望能看**哪些候選**的歷史？
   - (a) 只有卡片頭條那一個
   - (b) **你在畫面上點得到的每一個**（各到期日前十名）← 約 150 筆/次
   - (c) 全部（現狀）← 約 79,000 筆/次
2. 歷史要留多久？（全部／最近 N 次／最近 N 天）
3. 「原始資料」那一區的快照（每次 0.5–2.5 MB），需要保留歷史每一次
   嗎？還是只要最新一次？

**技術後果**：選 (b) 大約是 **500 倍**的縮減，而且既有的「找不到就
顯示斷點、不插值」機制已經支援——某個候選某次跌出前十，畫面上會
自然斷一格，不會壞掉。

⚠ 另外請一併考慮：**「為了以後好 debug 所以全部留著」這個理由，
代價是明確的（26 倍儲存），但收益從來沒被驗證過**——本專案至今
沒有任何一次除錯是靠讀回歷史完整結果完成的。

### Q3｜報價可以多舊？

**具體情況**：100 個人同時按「更新」看 TLT，今天系統會對 Cboe 發
**100 次**請求、拉進約 107 MB，而這 100 份資料**逐位元完全相同**。

**要決定的是**：

> 你希望其中 99 個人最多看到 **30 秒前**的資料，換取只打一次
> Cboe；還是每個人都一定要重新抓？

以及：

1. 這個「最多多舊」的容忍度，你覺得是幾秒？（5／15／30／60 秒／更長）
2. **使用者自己按下刷新鈕**時，是否應該無視這個窗、強制重抓？
3. 如果強制重抓會撞到 vendor 限流，你寧可讓他**等**、還是讓他看到
   **稍舊的資料＋明確標示**？

**技術後果**：Cboe 這個端點本身就叫 `delayed_quotes`（已經是延遲
報價），所以再加一個共用窗的**相對**新鮮度損失是二階的。但這個
數字必須由你定——沒有它，任何 TTL 都是憑空挑的（ADR-0001 當初的
15 秒就是這樣挑的）。

### Q4｜資料抓不到的時候，使用者該看到什麼？

**具體情況**：Cboe **會**限流（本輪實測撞到過，它要求等 34 秒）。
今天撞到之後：使用者看到「抓不到報價」，他按重試 → 又撞 → 更多人
一起重試 → 把限流窗一直續下去。**而且沒有任何自動復原機制。**

**要決定的是**：

1. 限流期間，使用者應該看到什麼？
   - (a) 「暫時抓不到，X 秒後自動重試」
   - (b) 「顯示上次成功的結果」＋明確標示資料時間
   - (c) 其他
2. 限流期間，**要不要禁止**使用者按重試立刻再打 vendor？
3. 如果 Cboe 持續不可用（例如 10 分鐘），系統應該安靜地一直重試，
   還是明確告訴使用者「這個資料源目前有問題」？

### Q5｜ADR-0001（chain 不做跨請求快取）要不要重開？

**具體情況**：這是 2026-08-24 的一個明文決策，而且它自己寫了
「不要重新提案，除非流量形狀改變**且有量測**」。

本輪找到三項它當時不存在的證據（上游會 429、平台可能允許行程共用、
Vercel Edge CDN 從未被評估），**但沒有 production 量測**——達不到
它自己設的門檻。

**要決定的是**：

1. 要不要重開這個題目？
2. 如果要，是否同意**先裝計數器量一個月**，用真實數字再談？
3. 重開時，是否要把 **Vercel Edge CDN** 這個 ADR 從未評估過的選項
   納入比較？

**技術後果**：ADR 反對「把 chain 寫進 Postgres」的核心論證（miss 是
純增加成本、同一份 payload 本來就已經寫進 `snapshots`）**本輪並沒有
被推翻**，而且更強了。所以重開不等於推翻——可能的結論是「換一個
ADR 沒評估過的做法」。

### Q6｜〔targeted research need〕兩個廉價、但會改變設計的未查證事實

**這兩件不是要你決定，是請你同意花很少的力氣先查清楚**：

1. **本專案的 Vercel 部署，實際上有沒有啟用 fluid compute？**
   研究只能依「2025-04-23 後的新專案預設啟用」推定。它決定
   §7.1「行程內快取能不能當 L1」的可行性。
2. **Python runtime 有沒有背景執行機制（`waitUntil` 的等價物）？**
   它直接決定 §6.2 的 stale-while-revalidate 可不可行。

> 這是 targeted research，**不是另一輪大型研究**。

> **2026-09-04 兩項均已查證完成**（1. NOT_CONFIRMED／2.
> NOT_SUPPORTED——官方文件確認無 Python 版 `waitUntil`/`after()`，
> SWR 需改用同步 refresh-on-miss 或 Cron 觸發，非 fire-and-forget）。
> 詳見 `docs/research/runtime-targeted-scaling.md`。

### Q7｜三件與 scaling 無關、但你應該知道的事

**不要求現在決定，只要求知情**：

1. **Dividend 主要來源 Yahoo 的 `robots.txt` 是 `Disallow: /`**——
   整個 host 對自動化存取是不允許的。這條依賴隨時可能被單方面斷掉，
   而且若產品要商業化，這是合規問題。**建議另開獨立線處理。**
2. **Market Data App 自訂 chain 來源，一次刷新要 2,414（TLT）–12,534
   （SPY）credits**，而 Free 一天只有 100。產品目前**完全沒有揭露
   這個成本**。
3. **Vercel Hobby 的商業使用條款**是否適用於本專案，研究未查證。

---

## 10. Correctness vs Optimization 分類

> 依委託明確區分。**這張表決定了「什麼可以延後」。**

| 項目 | 分類 | 說明 |
|---|---|---|
| user ownership（查詢帶身分） | **correctness ＋ privacy** | 今天 B 能改 A 的劇本 |
| 開站不刷新別人的劇本 | **correctness** | 不只是浪費——它在改別人的資料 |
| `provider_credentials` per-user | **privacy ＋ 成本正確性** | 一個人的付費配額被所有人用 |
| `results` retention | **capacity**（硬牆） | 42 次刷新就滿 |
| `/results` 不讀整份 view | **capacity ＋ latency** | 讀 365 MiB 只為了拿時間戳 |
| Cboe 429 不 retry storm | **correctness** | 自己把中斷延長 |
| Cboe 429 有降級路徑 | **capacity（可用性）** | 有沒有替代顯示 |
| chain 共用快取 | **capacity optimization** | **不是 correctness**——今天每次抓新的，語意上是對的 |
| Treasury single-flight | **capacity optimization**（收益極小） | 期望值 2–3 次/日 |
| Treasury cold-miss 延遲 | **latency，但會升級成 correctness** | 45s 預算 vs 45s 最壞，可能整輪逾時 |
| Dividend q=0 降級 | ⚠ **correctness 疑慮** | 研究實測 q=0 讓某格從 −11.5% 變成 +81.9%。今天有揭露（`q_note`），但這是**降級到一個已知很錯的值** |
| snapshot 移到 object storage | **cost optimization** | 延後 |
| Redis／distributed lock | **capacity optimization** | 延後 |

---

## 11. Failure Domains

【本輪覆核程式碼推導】

| 壞掉的東西 | 讀舊資料 | 重新計算 | 使用者看到 | 缺口 |
|---|---|---|---|---|
| **Cboe（429／down）** | ✅ 可以（結果在 Neon） | ❌ 禁止——沒有報價 | 「抓不到報價」＋卡片保留舊結果（REPAIR-05 兩態） | ⚠ **沒有 backoff → retry storm**；訊息無差別，看不出是限流 |
| **Treasury down** | ✅ | ✅ 可以——7 天陳舊備援 → 固定 4% ＋ 揭露 | 分析照常完成，參數行標示來源 | ✅ 設計良好 |
| **Dividend down** | ✅ | ⚠ 可以，但降級到 **q=0** | 分析照常完成，`q_note` 標示 | ⚠ q=0 是**已知錯很多**的值（見 §10）。「照常完成」是否正確？ |
| **Market Data（自訂）down** | ✅ | ✅ 自動退回預設來源，並記一次驗證失敗 | 設定頁自己變成「驗證失敗」＋原因 | ✅ 設計良好，無靜默退回 |
| **Neon down** | ❌ **完全不可用** | ❌ | 全站失敗 | ⚠ **無任何降級**。foundation 階段是否要處理？本文判斷：**不要**——資料庫是 single point of truth，為它做降級的複雜度遠超收益 |
| **快取層自己壞掉**（讀寫失敗） | — | ✅ 視同無快取，直接打上游 | 無感 | ✅ 三個快取層都已經這樣做 |

**推導出的兩個 foundation 要求**：

1. **必須寫下來**：哪些功能在哪個 vendor 掛掉時降級到什麼程度。
   今天這些行為是「程式碼裡碰巧是這樣」，不是「我們決定要這樣」。
2. **Dividend 的 q=0 降級需要一次有意識的裁決**——是繼續照常完成
   （現狀，有揭露），還是應該拒絕給出可能錯很多的數字？
   ⚠ 這一題本文**不列入 Owner Decisions**，因為它是 valuation 語意
   問題、不是 scaling 問題，應該另外處理。這裡只負責指出它存在。

---

## 12. 一頁總結

```
        ┌──────────────── NOW（不依賴任何人，可平行）─────────────────┐
        │  Stage 0  最小量測      ← 沒有它，chain 那題永遠在猜         │
        │  Stage 1  storage       ← 唯一 U=1 就撞牆的問題              │
        │  Stage 2  429 韌性      ← 全站中斷且無自動復原               │
        │  （順手）更正 7 處過時的「60 秒硬上限」                       │
        └──────────────────────────┬───────────────────────────────────┘
                                   │
        ┌──────────── BEFORE_MULTIUSER ────────────────────────────────┐
        │  Stage 3  ownership boundary（A-1）                          │
        │           └→ provider_credentials per-user                   │
        │           └→ refresh scope 自然收斂 O(U²) → O(U)             │
        │  Stage 4  Treasury cold-miss 延遲                            │
        │  Stage 7  auth 產品層（A-2）                                 │
        └──────────────────────────┬───────────────────────────────────┘
                                   │
        ┌──────────── AT_1K（條件式）──────────────────────────────────┐
        │  Stage 5  〔閘門〕chain 共用要不要做  ← 需要 Stage 0 的數字   │
        │  Stage 6  chain 共用（僅當閘門 NEEDED）                       │
        │           約束：只涵蓋預設來源；鍵含 source（§4.4）            │
        └───────────────────────────────────────────────────────────────┘

        LATER：cron warming、Redis／lock、object storage、多 region
        獨立線：Yahoo 替換（合規）、Market Data 成本揭露（產品）
```

---

## 13. 本輪的限制（誠實揭露）

1. **沒有新增任何量測。** 本輪是 Wayfinder，依委託不做第二輪研究。
   所有數字都引用自兩份研究文件或本輪對程式碼的靜態覆核。
2. **§8.3 的分級含判斷成分。** 「NOW／BEFORE_MULTIUSER／AT_1K」的
   界線是我依「風險在哪個 U 開始咬人」推導的，不是量測出來的。
   Owner 可以推翻任何一格。
3. **§9-Q6 的兩個事實未查證**，而它們會影響 §6.2 與 §7.1 的可行性。
4. **本文沒有替 ADR-0001 做決定。** 它的核心反對論證本輪沒有被推翻，
   新證據也不足以達到它自己設的重開門檻——這個張力是真實的，留給
   Owner。
5. **`docs/research/*` 的 P0/P1/P2 分級與本文的 NOW/BEFORE_MULTIUSER/
   AT_1K 分級不是同一套坐標**。研究依「多嚴重」分，本文依「什麼時候
   會咬人 ＋ 誰擋住誰」分。兩者對同一個項目可能落在不同格子，這是
   刻意的。

---

READY_FOR_SCALING_OWNER_DECISIONS
