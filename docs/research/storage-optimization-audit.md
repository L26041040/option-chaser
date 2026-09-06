# OPTION-STORAGE-AUDIT-003 — Exhaustive Storage Optimization Audit

**日期**：2026-09-06　**基準**：`claude/implement-tfm9oa` @ `190475a`
**性質**：audit／research／architecture reconciliation。**未改 production code、未 migration、未拆票、未開 PR。**

**量測環境**：本機 PostgreSQL 16.13（`default_toast_compression = pglz`，與 stock PG 相同），
repo 自己的 `PostgresStorage`／真實 schema／真實 `service.run_offline()`。
**量測 fixture**：`tests/fixtures/xyz_v8_production_scale.json`（600 合約、5 到期日、60 履約價/側），
三個 family 六個 subtype 全開、真實非零 q——即 repo 自己定義的 production-scale 基準
（`tests/_production_scale_fixtures.py`）。

> **所有標【實測】的數字都是本輪在這台機器上跑出來的**；標【引用】的來自既有研究文件、本輪未重跑；
> 標【推估】的是由實測值外推。

---

## 0. 執行摘要：五個最重要的發現

1. **`all_candidates` 佔 view 的 97.82%【實測】**，而移除它**同時改善效能**：
   寫入 981 ms → 41 ms（**24×**）、單列讀取 380 ms → 10.4 ms（**36.5×**）。
   這不是「拿效能換空間」，是兩者同向。
2. **今天的真實落盤是 3.04 MiB／次，不是 12–20 MiB。**【實測】TOAST（pglz）已經在壓，
   view 邏輯 21.1 MB → 落盤 **3.17 MB**（6.66×）。**既有研究與 spec #251 引用的
   12.18 MiB 是邏輯大小，不是落盤大小**——撞牆時間因此被低估了約 6.7 倍。
3. **RD-1 的「安全選項」是假優化，而且是災難級的。** 把全部合格候選存進 narrow 關聯表：
   **26.0 MB／次【實測】**，比今天的 3.17 MB **糟 8.2 倍**，走勢圖查詢 285 ms（visible-only 是 0.396 ms）。
   原因：關聯表逐列有 header／索引開銷且**吃不到 TOAST 壓縮**，JSONB blob 有。
4. **snapshot 逐位元相同性成立【實測】**（md5 相同、`distinct payloads=1 / rows=3`），
   K=5 去重實測省 **80.0%** payload，而讀取延遲 1.83 ms → 1.79 ms（**無代價**）。
5. **H3（snapshot 欄位瘦身）必須 REJECT**：Raw Data 面板逐欄渲染 `last`／`volume`／
   `open_interest`／`implied_volatility`（`src/RawData.tsx:115-121`），且 CSV 匯出用
   `fields(OptionContract)` **結構性輸出全部欄位**（`data/snapshot.py:60`）。刪任一欄都是功能退化。

---

## 1. H1 — `all_candidates`

### 1.1 Consumer 稽核（實證，非推論）

在獨立 git worktree 把 `store.py:680` 的 `all_candidates` stub 成 `[]`，跑**全套後端測試**
（記憶體＋真實 Postgres 雙後端）。**只有 9 條失敗**【實測】：

| 失敗測試 | 性質 |
|---|---|
| `test_api_analyze.py` × 4（contract sample drift） | 契約樣本需重產。`POST /api/analyze` 回傳**未投影**的 view，是唯一仍把它送上 wire 的端點——但它**零前端呼叫端** |
| `test_api_history.py::test_history_is_one_continuous_series_across_refreshes_with_a_gap` | **唯一真正的產品消費端**（SpreadHistory 走勢圖） |
| `test_detail_projection.py::test_storage_stays_full_fidelity_...` | 設計斷言（「儲存保持全保真」），需有意識重新定基 |
| `test_expiry_top10.py` ×1、`test_single_leg_expiry_grouping.py` ×2 | 直接測這個欄位本身，隨欄位一起退場 |

**未失敗、因此確認不依賴它的**：CLI golden fixtures（5 份）、`test_selection_regression.py`
全部、`test_ivpipeline_parity.py`、全部前端契約以外的後端測試。

⚠ **一個必須記錄的沉默陷阱【實測】**：`test_selection_regression.py` **沒有失敗，但它的
`per_expiry_order` 軸悄悄變成空斷言**。該軸由 `res["all_candidates"]` 構造（`:78-80`），
比對方式是**同一次執行內 before vs after**（`:175`）——欄位變空時兩邊都是 `{}`，`{} == {}` 恆真。
**⇒ 若移除 `all_candidates`，必須把該軸重新定基到 `expiry_ranked` 或 narrow 表，
否則真正的排序回歸會無聲通過。**

### 1.2 Current UI 是否仍完整？——**是**

`store.project_for_detail()` 早已在 wire 層剝除 `all_candidates` 與 `candidates`
（`store.py:871`），前端 TypeScript 從未宣告過它們。**實測**：detail 端點的投影輸出
**431,675 B**，而儲存的 view 是 **19,784,314 B**——**wire 只有儲存的 2.18%**。
`candidate_pool`（150 項、413,318 B）與 `expiry_top10` 已足夠支撐 detail 頁全部既有功能。

### 1.3 量體【實測】

| 項目 | 值 |
|---|---|
| FULL view（邏輯 JSON） | 19,784,314 B |
| ↳ `all_candidates` | 19,352,142 B（**97.82%**），128,668 筆，**150.4 B/筆** |
| ↳ `candidate_pool` | 413,318 B（2.09%） |
| ↳ 其餘全部鍵 | < 0.1% |
| FULL view 落盤（`pg_column_size`） | **3,171,586 B**（TOAST 6.66×） |
| 去 `all_candidates` 後落盤 | **203,010 B**（省 **93.6%**） |

### 1.4 效能影響——**改善，非惡化**【實測】

| 操作 | 現況 | 去 `all_candidates` | 變化 |
|---|---|---|---|
| `save_result`（寫入） | 981.2 ms | 40.7 ms | **24.1× 更快** |
| 單列 `SELECT view`（讀取） | 380.1 ms | 10.4 ms | **36.5× 更快** |
| `serialize_result`（CPU） | 0.605 s（含產生 128,668 筆） | — | 一併省下 |

> 這一項同時滿足 Owner 的兩條硬約束：功能不退化（current UI 本來就沒用它）、
> 效能不惡化（**大幅改善**）。**但它有一個前置**：`/history` 需要替代來源（見 §1.5）。

### 1.5 前置條件

`spread_cost_history()` 讀**全部**歷史列，**含最新列**（`postgres.py:550-556` 無 offset）。
因此不能只針對「歷史列」移除——最新列的 `all_candidates` 也是走勢圖最新一點的來源。
移除前必須先有 RECONCILE-002 定義的 **narrow 表（L2 熱快取）＋ L0 snapshot 回填路徑**。

---

## 2. H2 — Snapshot 去重

### 2.1 逐位元相同性——**成立**【實測】

`refresh-run` 在一個 symbol group 內只抓一次鏈，`snap` 物件由該 group 全部劇本共用，
逐劇本各寫一列（`main.py:979`，鍵 `(scenario_id, analyzed_at)`）。
實測 3 個劇本共用同一 snapshot：`md5` 相同、`count(DISTINCT md5)=1 / count(*)=3`。

### 2.2 節省與代價【實測，K=5 × 30 次刷新 = 150 列】

| 指標 | 現況 | 去重（ref + blob） | 變化 |
|---|---|---|---|
| payload 落盤 | 2,774,700 B | 554,940 B | **省 80.0%**（理論上界 (K−1)/K = 80%） |
| relation 總量 | 3,203,072 B | 753,664 B | 省 76.5% |
| 點查詢讀取延遲 | 1.83 ms | 1.79 ms | **0.98×（無代價）** |

> JOIN **沒有**增加延遲——因為兩邊都是主鍵點查詢，多一次索引查找的成本遠小於 deTOAST 本身。

### 2.3 正確性風險（本輪未解，屬複雜度成本）

- **刪除語意**：`delete_scenario` 今天直接 `DELETE FROM snapshots WHERE scenario_id=%s`。
  去重後必須改為 refcount 或 GC，否則會刪掉別的劇本還在用的 blob，或永久遺留孤兒 blob。
- **封存語意**：archive 是軟刪除、`restore_scenario` 不動 snapshots——GC 必須排除封存中的劇本。
- **交易語意**：目前逐劇本各自 autocommit 寫入；去重需要「blob upsert + ref insert」兩步的原子性考量。
- **K 值未知**：節省幅度完全取決於「幾個劇本共用同一 symbol」。K=1 時**零節省、純增加複雜度**。
  本輪無 production 遙測可知大哥的實際 K。

---

## 3. H3 — Minimal Replay Seed（逐欄稽核）

### 3.1 逐欄位元組【實測】（snapshot 總計 114,269 B / 600 合約 = 190.4 B/合約）

| 欄位 | 位元組 | 佔比 | 引擎／API consumer | Raw Data 面板 | 可否推導 |
|---|---|---|---|---|---|
| `contract_symbol` | 21,600 | 18.90% | `report.py` 逐腿報價行；**`contract_iv_history` 的 primary key**；vendor 歷史查詢身分 | ✅ 顯示 | ❌ **不可**——`cboe.py:78` 是 `str(o["option"])`，**vendor 原字串**，非本站推導 |
| `implied_volatility` | 16,130 | 14.12% | `report.py` 逐腿 IV；`service.py` IV 過濾關卡 | ✅ 顯示 | ❌ 不可（市場觀測） |
| `expiry` | 13,200 | 11.55% | 全鏈路（估值／分組／`candidate_key`） | ✅ 顯示 | ❌ identity |
| `option_type` | 12,300 | 10.76% | 全鏈路 | ✅ 顯示 | ❌ identity |
| `open_interest` | 12,300 | 10.76% | 序列化進候選腿（`store.py:238`），FB5-01 後**不再是硬門檻** | ✅ 顯示 | ❌ 不可（市場觀測） |
| `strike` | 8,700 | 7.61% | 全鏈路 | ✅ 顯示 | ❌ identity |
| `volume` | 7,710 | 6.75% | `service.py:460/469/481` 零成交量品質標示；`report.py:234` | ✅ 顯示 | ❌ 不可 |
| `last` | 7,341 | 6.42% | **引擎與 API 層零命中** | ✅ **顯示** | ❌ 不可 |
| `ask` | 6,828 | 5.98% | `natural_cost` 核心 | ✅ 顯示 | ❌ 不可 |
| `bid` | 6,818 | 5.97% | `natural_cost` 核心 | ✅ 顯示 | ❌ 不可 |

### 3.2 結論：**REJECT**

**沒有任何一欄可以在不退化功能的前提下移除。** 兩個結構性理由：

1. **`/raw-data` 面板逐欄渲染全部欄位**（`src/RawData.tsx:115-121`，含 `last`）。
2. **CSV 匯出結構性輸出全部欄位**：`snapshot_to_csv` 用 `fields(OptionContract)`
   （`data/snapshot.py:60`）——刪欄位會**靜默改變 CSV 表頭**，而該功能的存在理由正是
   「免得你亂掰我卻查不到證據」（QA1-10／#37 原話）。

`last` 是唯一引擎零消費的欄位（省 6.42%），但它仍在畫面上。**省 6% 換一個可見欄位消失，不划算。**

⚠ **fixture 誠實揭露**：本 fixture 是合成的，`volume` 恆為 10、`open_interest` 恆為 100，
壓縮率因此**樂觀**；真實資料這兩欄變異大、佔比會更高。逐欄佔比視為指示性，非 production 值。

---

## 4. H4 — 壓縮

### 4.1 現況：TOAST 已在壓，且已是較好的演算法【實測】

| 對象 | 邏輯 | 落盤 | ratio |
|---|---|---|---|
| FULL view（pglz，現況） | 21,112,857 | **3,171,586** | **6.66×** |
| FULL view（lz4 對照） | 21,112,857 | 3,665,657 | 5.76× |
| snapshot（pglz） | 126,279 | 18,498 | 6.83× |

> **`pglz`（現行預設）在本負載上優於 `lz4`。改用 lz4 會讓落盤變大 15.6%。不建議更動。**

### 4.2 應用層壓縮對照【實測】

| 方案 | view 落盤 | 讀取 | partial-query | 複雜度 |
|---|---|---|---|---|
| JSONB + pglz（現況） | 3,171,586 | 358.4 ms | ✅ JSONB 運算子可用 | 零 |
| bytea + zlib-6 | 2,122,255（省 33.1%） | 217.7 ms（0.61×，較快） | ❌ 完全失去 | 高 |

**但**——H1 之後再比：JSONB 203,010 B vs bytea+zlib **87,530 B**，
差距僅 **113 KiB／次**。**用「失去 JSONB 運算子＋新增壓縮/解壓層」換 113 KiB，不划算。**

zlib-9（10.37×）／lzma（15.46×）壓縮 CPU 分別是 798 ms／9,703 ms——**遠超任何可接受的寫入路徑成本**。

### 4.3 結論：**REJECT**（現況已最佳；H1 之後絕對收益過小）

---

## 5. H5 — 全 schema 分類（14 張表，窮舉）

| # | 表 | 鍵 | 每次刷新成長 | 分類 |
|---|---|---|---|---|
| 1 | `scenarios` | `id` | 0（僅建立時） | **current-state only**（bounded by 劇本數） |
| 2 | `results` | `(scenario_id, analyzed_at)` | **+1 列，3.17 MB 落盤** | **canonical history（accidentally unbounded）** |
| 3 | `snapshots` | `(scenario_id, analyzed_at)` | **+K 列，18.5 KB/列** | **canonical history（L0 seed，OD-06 永久）** |
| 4 | `events` | `seq` | +1 列 ≈ 177 B | **append-only，永不修剪（零前端消費端）** |
| 5 | `diagnostics` | `seq` | **0 列**（健康刷新只留 warning/error，且刷新路徑結構上不觸及） | **cache（唯一有 retention：全域最新 200 筆 trim-on-write）** |
| 6 | `rate_cache` | `id=1`（CHECK） | 0（單列 upsert） | **bounded（1 列）** |
| 7 | `dividend_cache` | `symbol` | 0（per-symbol upsert） | **bounded by symbol 數** |
| 8 | `treasury_year_cache` | `year` | 0（per-year upsert） | **bounded by 年份數** |
| 9 | `data_source_settings` | `id=1`（CHECK） | 0 | **bounded（1 列）** |
| 10 | `provider_credentials` | `provider` | 0 | **bounded（`SUPPORTED_PROVIDERS` 目前 1 元組）** |
| 11 | `provider_verifications` | `provider` | 0 | **bounded** |
| 12 | `iv_observations` | `(symbol, observed_on)` | **0（不在刷新路徑）** | ⚠ **accidentally unbounded**——無 retention、`delete_scenario` **不 cascade**、約 66 列/symbol/年 |
| 13 | `iv_backfill_runs` | `symbol` | 0 | **bounded（per-symbol upsert）** |
| 14 | `contract_iv_history` | `contract_symbol` | **0（不在刷新路徑）** | ⚠ **accidentally unbounded**——每個開過 IV 卡片的 OCC 合約一列，`points` **append-only**、只在**讀取時**裁 365 天、合約到期後**不 GC** |

**大型 JSONB 欄位窮舉**：`results.view`（3.17 MB）／`snapshots.snapshot`（18.5 KB）／
`iv_observations.surface`／`contract_iv_history.points`／`dividend_cache.history`／
`treasury_year_cache.rows`／`rate_cache.curve`／`events.payload`／`diagnostics.context`／
`scenarios.strategies`／`results.{representative_candidate,per_family,family_eligibility}`。
**只有前四個具成長性**，其餘皆 bounded 或單列。

---

## 6. Storage Optimization Matrix

| Candidate | Current bytes（落盤／次） | Potential savings | Functional risk | Performance impact | Replay impact | Complexity | Recommendation |
|---|---|---|---|---|---|---|---|
| **C1 移除 `all_candidates`（配 narrow 表＋L0 回填）** | 3,171,586 → 203,010 | **−2.97 MB／次（−93.6%）** | 低（current UI 已不用；`/history` 需先有替代） | **改善**：寫 24×、讀 36.5× | 無（L0 snapshot 不動） | 中（需 narrow 表＋回填路徑＋重新定基 `per_expiry_order` 軸） | **DO_NOW**（在 narrow＋回填就緒後） |
| **C2 `/results` 改窄查詢** | 讀 419.5 ms（2 列） | 讀取 **419.5 → 0.1 ms（4,195×）** | 零（回應逐位元不變） | **改善** | 無 | 極低 | **DO_NOW** |
| **C3 narrow 表用 visible-only** | — | 32,495 B／次 | 中（缺格需 L0 回填，見 RECONCILE-002） | 走勢圖查詢 **0.396 ms** | 缺格可從 L0 回填 | 中 | **DO_NOW**（優於 C4） |
| **C4 narrow 表用 all-qualified** | — | **26,030,626 B／次** | 零 | 走勢圖查詢 285 ms | 無 | 中 | **REJECT — 假優化**：比今天糟 **8.2×**、查詢慢 **720×** |
| **C5 snapshot 去重** | 18,498 × K | **−80%（K=5 實測）** | 中（刪除／封存／GC 語意） | **無代價**（1.83→1.79 ms） | 無（內容不變） | **高**（refcount／GC／cascade 重寫） | **VALIDATE_MORE**（先量 production 的真實 K） |
| **C6 snapshot 欄位瘦身** | 114,269（邏輯） | 最多 −38% | **高——功能退化** | 中性 | **降低**（L0 不再完整） | 中 | **REJECT** |
| **C7 移除 `last` 單欄** | 7,341（6.42%） | −6.4% | **高**（Raw Data 面板欄位消失、CSV 表頭變動） | 中性 | 略降 | 低 | **REJECT** |
| **C8 bytea + zlib 取代 JSONB** | 3,171,586 → 2,122,255 | −33%（H1 前）／−113 KiB（H1 後） | 中（失去 JSONB 運算子） | 讀取 0.61×（較快） | 無 | 高 | **REJECT**（H1 之後絕對收益過小） |
| **C9 TOAST 改 lz4** | 3,171,586 → 3,665,657 | **−15.6%（變大）** | 零 | 中性 | 無 | 低 | **REJECT — 反向** |
| **C10 歷史 `results.view` 整份退役** | 203,010／次（C1 後的殘值） | **−203,010 B／次** | 低（RECONCILE-002 已證唯一消費端可由 narrow＋L0 覆蓋） | **改善** | 無 | 中 | **DO_NOW**（C1／C3 之後） |
| **C11 `contract_iv_history` 寫入時裁窗＋到期 GC** | 不在刷新路徑 | 未量測（無 production 遙測） | 低—中（裁掉的點只能向前補、不可回溯） | 中性 | 降低（IV 歷史深度） | 中 | **VALIDATE_MORE** |
| **C12 `iv_observations` 加 retention／cascade** | 不在刷新路徑 | 未量測 | 低 | 中性 | 降低 | 低 | **VALIDATE_MORE** |
| **C13 `events` 退役** | 177 B／次（0.006%） | 可忽略 | 低（零前端消費端） | 中性 | **降低**（審計軌跡消失） | 低 | **DEFER**（是列數問題不是位元組問題） |

---

## 7. 儲存分解與理論下限

### 7.1 今天的真實分解【實測，每次刷新／每劇本】

| 項目 | 落盤 | 佔比 |
|---|---|---|
| `results.view` | 3,171,586 B | 99.41% |
| `snapshots.snapshot` | 18,498 B | 0.58% |
| `events` | 177 B | 0.006% |
| 其餘 11 張表 | 0 B | 0% |
| **合計** | **3,190,261 B ＝ 3.04 MiB** | |

> ⚠ **對既有文件的更正**：研究文件與 spec #251 引用的「12.18 MiB／列」是**邏輯**大小。
> 本輪實測的**落盤**大小是邏輯值的 1/6.66。撞牆時間因此被低估約 6.7 倍。

### 7.2 Current-state 固定成本（不隨刷新成長）

每個劇本一份：最新 view（C1 後 203,010 B）＋最新 snapshot（18,498 B）＋劇本列
≈ **221,508 B／劇本**。10 個劇本 ≈ 2.11 MiB——**常數項，不是成長項**。

### 7.3 Growth cost 與理論下限

| 情境 | 每次刷新永久成長 | Neon Free 0.5 GB 可容 | 相對今天 |
|---|---|---|---|
| **今天** | 3,190,261 B | **168 次** | 1× |
| C1＋C3（保留歷史 view 殘值） | 254,180 B | 2,113 次 | **12.5×** |
| **C1＋C3＋C10（歷史 view 整份退役）** | **51,170 B** | **10,494 次** | **62.3×** |
| ＋C5 去重（K=5） | **36,372 B** | **14,764 次** | **87.7×** |
| C4（假優化對照） | 26,030,626 B | 20 次 | **0.12×（更糟）** |

**理論下限 = narrow 表 32,495 B ＋ snapshot 18,498 B ＋ events 177 B ≈ 51 KiB／次**
（OD-06 之下 snapshot 是不可壓縮的地板；去重後可再降到 ≈ 36 KiB／次）。

### 7.4 哪些 savings 最大

1. **C1 移除 `all_candidates`：−93.6%**（單獨一項就吃掉幾乎全部收益）
2. **C10 歷史 view 整份退役：再 −80%**（C1 之後的殘值）
3. **C5 snapshot 去重：−80% 的 snapshot 部分**（僅在 K>1 時）

### 7.5 哪些其實是假優化

- **C4（narrow 全部合格候選）**：比今天**糟 8.2×**、查詢慢 **720×**。
  「保守、逐位元不變」的直覺完全錯誤——**關聯表吃不到 TOAST，JSONB blob 吃得到。**
- **C9（TOAST 改 lz4）**：反而變大 15.6%。
- **C8（bytea+zlib）**：H1 之後只剩 113 KiB／次，卻要付出失去 JSONB 運算子的永久代價。
- **C13（退役 events）**：0.006%，量測上等於零。

### 7.6 明確 REJECT（會犧牲功能或效能）

- **C6／C7 snapshot 欄位瘦身**：Raw Data 面板與 CSV 匯出結構性消費全部欄位 ⇒ 功能退化。
- **C4**：效能與空間**雙輸**。
- **C9**：空間單輸。
- **C8**：複雜度／可查詢性代價遠大於收益。

---

## 8. 是否需要修正 spec #251？——**需要，四處**

| # | 修正 |
|---|---|
| **A1** | **growth model 的單位錯了**：12.18 MiB 是邏輯大小，落盤是 1/6.66。全部「Neon Free 能撐幾次」的推算需以落盤值重算 |
| **A2** | **RD-1 已由量測解決**：選項 (b)（全部合格候選）不是「保守但無界」，而是**比今天糟 8.2 倍的假優化**，應直接改列 REJECT；建議值確定為 (a) visible-only ＋ L0 回填 |
| **A3** | **新增紅線 RL-33**：不得把 `all_candidates` 就地清空而不重新定基 `test_selection_regression.py` 的 `per_expiry_order` 軸——該軸是同一次執行內 before/after 比對，欄位變空會**恆真**而非紅燈 |
| **A4** | **新增紅線 RL-34**：`snapshots` 的**任何欄位**都不得移除——`/raw-data` 面板逐欄渲染、CSV 匯出用 `fields(OptionContract)` 結構性輸出全部欄位 |

另**新增一個 spec #251 未涵蓋的候選**：**C5 snapshot 去重**（VALIDATE_MORE，需先量 production 的真實 K）。

---

## 9. 誠實揭露

1. **fixture 是合成的**：`xyz_v8_production_scale.json` 的 `volume`／`open_interest` 值單一，
   壓縮率樂觀；真實 TLT／SPY 資料的 TOAST ratio 會低於 6.66×，逐欄佔比也會不同。
   **6.66× 應視為上界，不是 production 值。**
2. **本輪未在真實 Neon 上量測**——本機 PG 16 與 Neon 的 TOAST 行為理論相同（皆 stock PG），
   但網路延遲、pooler、實際 `default_toast_compression` 設定未驗證。
3. **K 值未知**：C5 的收益完全取決於 production 上「幾個劇本共用同一 symbol」，本輪無遙測。
4. **既有文件的 12.18 MiB／0.48 MiB／2.55 MiB 引用自研究文件的一手實測，本輪未重跑**；
   本輪的數字來自不同 fixture，兩者不可直接相減比較，只可比較**比例**。
5. **narrow 表的 32,495 B／次是在 30 次刷新、單一劇本下攤提的**；索引開銷在更大規模下會攤得更薄。
6. **C1 的測試實證是在 stub 成 `[]` 的情況下跑的**，不等於「真正移除欄位」的完整改動範圍
   （型別、序列化、契約樣本、前端型別皆需跟著動）。它證明的是**消費端邊界**，不是施工完整性。
