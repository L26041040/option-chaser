# OPTION-STORAGE-PROTOTYPE-004 — Scaling Storage Prototype Validation

**日期**：2026-09-06　**基準**：`claude/implement-tfm9oa` @ `24650f2`
**性質**：丟棄式 prototype。**未改 production architecture、未 migration、未拆票、未開 PR、未 merge。**

**驗收結果**：**PASS_WITH_CHANGES**　**實測 storage 改善 58.70×**（audit 預測 62×，差 5.3%）
**functional regressions：0**　**backfill 逐位元 parity：成立（4,626 次比對、0 mismatch、六個 subtype 全覆蓋）**

> ⚠ **skill 分支偏離的誠實說明**：`/prototype` 的 LOGIC 分支要求產出「非開發者可點按鈕的單檔 HTML demo」。
> 本輪的問題是 **A/B 量測與逐位元 parity 證明**，那不是點按鈕能回答的。因此採用 skill 的**核心規則**
> （丟棄式、明確標記、一鍵可跑、scratch DB 標 `WIPE_ME`、不寫測試、不抽象、可完整移除、收尾進 throwaway branch），
> 但把「可被抽回正式模組的純邏輯」做成 `cost_from_snapshot()` 而非 HTML 頁面。

---

## 1. Prototype architecture

| 檔案 | 角色 | 去向 |
|---|---|---|
| `PROTOTYPE_storage_foundation.py` | A/B 量測台：100 次刷新、雙軌寫入、parity 檢查、儲存與延遲量測 | **丟棄**（見 §12） |
| `PROTOTYPE_followup.py` | 後續量測：VACUUM 後真實尺寸、`/results` 回歸根因與修法、全 subtype backfill | **丟棄** |
| `cost_from_snapshot()` | **唯一會被抽回正式模組的純函式**：純算術、零 I/O、零 vendor、零 credential | **保留概念，正式施工時抽出** |

**隔離**：所有寫入只進 scratch 資料庫 `octest_proto_WIPE_ME`；零 production 模組改動
（`git diff HEAD` 對 `option_chaser/`／`api_app/`／`src/`／`tests/` 零差異）。

**Workload（A 與 B 完全相同）**：同一份 production-scale fixture
（`xyz_v8_production_scale.json`，600 合約／5 到期日／60 履約價/側）、同一組 scenario 參數
（`target_price=110`／`target_month=2026-09`）、同一個 seed（**20260906**）、
**六個 subtype 全開**（long-call／long-put／bull-call-spread／bear-put-spread／call-fly／put-fly，
即 single-leg ＋ vertical ＋ butterfly 三個 family）、**100 次刷新**。

每次刷新以固定 seed 對 fixture 施加合成隨機漫步（spot 漂移 ＋ 逐合約報價 jitter ＋
moneyness 相關項），目的是讓 cost 隨時間變、**讓排名 churn 從而產生 narrow history 缺格**。
⚠ 這是合成模型，不宣稱是真實市場。

**每次刷新的實際規模**：`all_candidates` **105,869 筆**，visible 集合 **120 筆**（比例 0.11%）。

---

## 2. Baseline A vs Prototype B

| | Baseline A（今天的 canonical 行為） | Prototype B（新 storage shape） |
|---|---|---|
| `results.view` | 每次刷新寫一列**完整 view**（含 `all_candidates`），永久累積 | **只保留最新一列**（且已移除 `all_candidates`），舊列不累積 |
| `snapshots` | 每次刷新一列 | **不變**（OD-06） |
| narrow history | 不存在 | **新增**：`(scenario_id, analyzed_at, candidate_key, cost)`，**只存 visible 集合** |
| 歷史 cost 來源 | `all_candidates` | narrow 表（熱）＋ **raw snapshot 重算（冷，補缺格）** |

**假設 1～5 對應**：① 移除 `all_candidates` ✅　② visible-only narrow ✅
③ 缺格由 snapshot deterministic backfill ✅　④ 歷史 full view 停止累積 ✅　⑤ current detail 完整 ✅

**未順手施工**（依指示）：snapshot dedup／IV retention／object storage／chain shared cache／
Redis-KV／ownership／Treasury／429 resilience——全部不在本 prototype 內。

---

## 3. A/B Functional Parity

**100 次刷新、逐次比對，0 失敗。**

| 檢查項 | 方法 | 結果 |
|---|---|---|
| current detail wire（含 **heatmap／candidate detail／candidate identity／family ranking**） | `json.dumps(project_for_detail(view), sort_keys=True)` 逐位元比對 | **0 mismatch／100** |
| champion（跨 family 冠軍） | `store.representative_candidate()` A vs B | **0 mismatch／100** |
| baseline return | `store.best_return()` A vs B | **0 mismatch／100** |
| Raw Data | 兩邊 `snapshots` 列逐位元比對 | **0 mismatch／100** |
| CSV 匯出 | `snapshot_to_csv(snapshot_from_dict(...))` 字串比對 | **0 mismatch／100** |
| per-expiry ordering | 見 §3.1 | **0 mismatch／100** |
| Spread Cost History | 見 §4 | **逐位元一致** |

> `project_for_detail` 的輸出涵蓋 heatmap（`candidate_pool` 內的 matrix／`axis_sets`）、
> 候選詳情、family eligibility、expiry 分組——因此「wire 逐位元相同」一次涵蓋多個檢查項。

### 3.1 Regression Guard Repair（RL-33）——已證明有非空的 canonical source

**問題**：`test_selection_regression.py:78-80` 的 `per_expiry_order` 軸由 `all_candidates` 構造，
比對是同一次執行內 before vs after（`:175`）；欄位變空時兩邊都是 `{}`，**斷言恆真、假綠燈**。

**驗證的替代來源**：引擎的 `result.results[i].expiry_ranked`——`all_candidates` 本來就只是它的序列化副本。

| 指標 | 結果（100 輪） |
|---|---|
| 引擎來源**非空**（每個到期日都有排序清單） | **100／100** |
| 與 `all_candidates` 構造的結果**完全相同** | **100／100** |

⇒ **`expiry_ranked` 是有效、非空、逐位元等價的 canonical regression source。不需要用空集合讓測試假通過。**

⚠ **正式施工必須改的一處**：`test_selection_regression.py` 的 `_view()`（`:55-57`）**丟棄了引擎
`result`**，只回傳 view。要用 `expiry_ranked` 必須讓該 helper 同時回傳 result（小 refactor）。
若不願改 helper，退而求其次可改基於序列化的 `expiry_top10`——**非空、不假綠燈，但只涵蓋每期前十**，
覆蓋率低於今天。**建議走前者。**

---

## 4. Snapshot Backfill Proof（本輪最重要的 correctness proof）

**純函式**：`cost_from_snapshot(snapshot, candidate_key) -> float | None`

- `candidate_key` 由 `service.valuation_key()` 產生，已完整編碼 strategy ＋ 全部履約價 ＋ 到期日 ⇒ 不需任何額外中繼資料
- 運算式順序**逐字複製** `option_chaser/scenarios.py:138-143`（浮點加減不可交換，順序一變就拿不到逐位元一致）
- **零 vendor 呼叫、零 credential、不跑 ranking／valuation 引擎**

| 驗證 | checked | bitwise exact | mismatch |
|---|---|---|---|
| 主驗證（追蹤最新 visible 集合跨全部 100 次刷新） | **2,826** | **2,826** | **0** |
| 全 subtype 擴大驗證（10 份快照 × 每 subtype 抽樣 60） | **1,800** | **1,800** | **0** |
| **合計** | **4,626** | **4,626** | **0** |

**六個 subtype 全數涵蓋**（逐位元一致筆數）：
`bull-call-spread` 480／`call-fly` 480／`long-call` 480／`bear-put-spread` 120／`long-put` 120／`put-fly` 120

- **Vertical**：`long.ask − short.bid` ✅
- **Butterfly**：`low.ask − 2.0 × mid.bid + high.ask` ✅（含中腿 2 倍權重）
- **Single-leg**：`contract.ask` ✅

**缺格處理已實測**：主驗證中有 **1,179 個 (analyzed_at, candidate_key) 組合不在 narrow 表裡**
（該候選當時不在 visible 集合），全部由 snapshot 重算補上且**逐位元一致**。

> ⇒ **Backfill proof 成立。** narrow 表是熱快取、snapshot 是完整冷來源，這個分層在資料上站得住。

---

## 5. Storage Growth（1／30／100 次刷新）

⚠ 下表為**執行當下**的量測，`b_results_latest` 因 100 次覆寫而含 MVCC 膨脹；
**權威數字見 §6（VACUUM FULL 後）**。

| 刷新次數 | A 總量 | B 總量 | 比值 | narrow 列數 |
|---|---|---|---|---|
| 1 | 2,998,272 B | 425,984 B | 7.04× | 120 |
| 30 | 85,426,176 B | 3,203,072 B | **26.67×** | 3,600 |
| 100 | 266,526,720 B | 7,118,848 B | **37.44×** | 12,000 |

> 1 次刷新時比值只有 7.04×，是因為 B 的三張表各自有 8 KB 頁面與 16 KB 索引的**固定配置成本**——
> 那是常數項，隨刷新次數攤薄。**這正是為什麼必須量到 100 次才看得到真實斜率。**

---

## 6. PostgreSQL Physical-Size Breakdown（VACUUM FULL 後，權威數字）

| 表 | VACUUM 前 total | VACUUM 後 total | heap | index | TOAST |
|---|---|---|---|---|---|
| `a_results` | 264,355,840 | **264,282,112** | 16,384 | 16,384 | 264,249,344 |
| `a_snapshots` | 2,170,880 | **2,121,728** | 16,384 | 16,384 | 2,088,960 |
| `b_results_latest` | 1,351,680 | **237,568** | 8,192 | 16,384 | 212,992 |
| `b_snapshots` | 2,170,880 | **2,121,728** | 16,384 | 16,384 | 2,088,960 |
| `b_narrow` | 3,006,464 | **2,416,640** | 1,277,952 | 1,130,496 | 8,192 |

**核心數字（100 次刷新）**：

| | 值 |
|---|---|
| A 總量 | 266,403,840 B ⇒ **2,664,038 B／次** |
| B **成長部分**（snapshots ＋ narrow） | 4,538,368 B ⇒ **45,384 B／次** |
| B **current 固定成本**（latest view） | **237,568 B**（常數項，非成長項） |
| **總量比** | **55.78×** |
| **邊際成長比（決定何時撞牆）** | **58.70×** |

**與 audit 預測對照**：audit 預測 3.19 MB → ~51 KB／次 ＝ **62×**；
本輪實測 2.66 MB → **45.4 KB／次 ＝ 58.70×**。**差距 5.3%——強證據等級的吻合。**

⚠ **兩項必須誠實指出的量測細節**：
1. `b_results_latest` VACUUM 前 1.35 MB、VACUUM 後 **237,568 B**——差的 82% 是 100 次覆寫的
   MVCC 死列。**production 的 autovacuum 會處理，但施工時不能拿 VACUUM 前的數字說嘴。**
2. `b_narrow` 的**索引佔 46.8%**（1,130,496 / 2,416,640）——主鍵 `(scenario_id, analyzed_at,
   candidate_key)` 三個 TEXT 欄位很寬。這是 narrow 方案的真實成本，不是可忽略項（見 §11）。

---

## 7. Performance Benchmark

### 7.1 寫入路徑（median / p95）

| 項目 | Baseline A | Prototype B | 比值 |
|---|---|---|---|
| serialize CPU | 240.9 / 266.1 ms | 同左（兩邊共用同一次序列化） | 1.00× |
| `save_result` | **722.7 / 829.9 ms** | **30.6 / 34.2 ms** | **23.60× 更快** |
| snapshot write | 7.5 / 8.8 ms | 7.2 / 8.1 ms | 1.05×（持平） |
| narrow write（B 新增成本） | — | **3.5 / 4.4 ms** | 新增 |

> **B 的寫入路徑淨改善約 696 ms／次**（省下 692 ms 的 view 寫入，付出 3.5 ms 的 narrow 寫入）。

### 7.2 讀取路徑（median / p95）

| 項目 | Baseline A | Prototype B | 比值 |
|---|---|---|---|
| current detail read | **275.9 / 359.1 ms** | **9.2 / 10.4 ms** | **30.00× 更快** |
| `/history` 常見情況（narrow 全命中） | 51,875 / 59,162 ms | **1.17 / 1.60 ms** | **44,261× 更快** |
| `/history` 最壞情況（99/100 缺格全回填） | 51,875 / 59,162 ms | **192.4 / 212.7 ms** | **270× 更快** |
| `/results`（**天真實作**：`DISTINCT` over narrow） | **0.167 / 0.515 ms** | **2.110 / 2.352 ms** | ⚠ **12.6× 更慢** |
| `/results`（**修正後**：讀 `snapshots` 的 PK 索引） | 0.167 / 0.515 ms | **0.106 / 0.180 ms** | **1.58× 更快** |

### 7.3 唯一的效能回歸：`/results`（已找到根因、已驗證修法）

**不用 storage 收益掩蓋它。** 天真實作 `SELECT DISTINCT analyzed_at FROM b_narrow` 要掃 12,000 列
才去重出 100 個時間戳，因此比 A 的主鍵索引掃描慢 12.6×。

**根因**：把 narrow 表當成 analyzed_at 索引用，但它是 **per-candidate 粒度**，不是 per-refresh 粒度。

**修法（已實測，非假設）**：`snapshots` 表天生就是 per-refresh 一列、且有
`(scenario_id, analyzed_at)` 主鍵——直接讀它。實測 **0.106 ms，比 Baseline 還快 1.58×**。

> ⇒ **修正後：主要使用者路徑零回歸，全部改善。**

---

## 8. Failed Assumptions

| # | 假設 | 實測結果 |
|---|---|---|
| 1 | 「narrow 表可以同時當 analyzed_at 索引用」 | ❌ **證偽**。per-candidate 粒度做 `DISTINCT` 慢 12.6×。必須改用 `snapshots` 的 PK（§7.3） |
| 2 | 「B 的 latest view 就是一列，很小」 | ⚠ **部分證偽**。不 VACUUM 的話 100 次覆寫累積 1.35 MB 死列，是真實尺寸的 5.7 倍 |
| 3 | 「narrow 表很窄所以索引可忽略」 | ❌ **證偽**。三個 TEXT 欄位的 PK 佔全表 **46.8%** |
| 4 | 「1 次刷新就能看出改善幅度」 | ❌ **證偽**。N=1 時只有 7.04×（固定頁面配置主導），N=100 才收斂到 58.70× |
| 5 | 「A/B 的 view 可以直接用 Python 物件比對」 | ❌ **證偽（harness 自身的 bug）**。`json` round-trip 把 tuple 變 list，產生假陽性。必須比 JSON 文字（＝真正的 wire 等價） |

**未被證偽的核心假設**：backfill 逐位元一致（4,626/4,626）、功能零退化（0/100）、
`expiry_ranked` 是有效 guard source（100/100）、儲存改善達一個數量級以上（58.70×）。

---

## 9. Unexpected Costs

1. **`/history` 最壞情況 192 ms**——一個「剛剛才進入 visible 集合」的候選，100 個點裡 99 個要回填。
   比 A 的 51.9 秒快 270×，但**不是免費的**，且**隨歷史長度線性成長**。
   ⇒ 施工建議：回填後**寫回 narrow 表**（write-through），第二次開圖就是 1.17 ms。
2. **narrow 表索引 46.8%**——比預期高。
3. **MVCC 膨脹**——latest-only 的覆寫模式對 autovacuum 有依賴，冷門劇本可能長期帶著死列。
4. **narrow 寫入 3.5 ms／次**——絕對值小，但它是 B 相對 A **新增**的成本，不是零。

---

## 10. 是否支持 audit 的 C1 / C2 / C3 / C10？

| 候選 | 支持？ | 實測依據 |
|---|---|---|
| **C1** 移除 `all_candidates` | ✅ **強力支持** | 寫入 23.60× 更快、current detail 讀取 30.00× 更快、落盤 −93%；功能 0 退化 |
| **C2** `/results` 改窄查詢 | ✅ **支持，但索引來源要改** | 必須讀 `snapshots` 的 PK（0.106 ms），**不可** `DISTINCT` over narrow（2.110 ms） |
| **C3** narrow 用 visible-only | ✅ **支持** | 45,384 B／次；缺格 1,179 個全部由 snapshot 逐位元補回 |
| **C10** 歷史 view 整份退役 | ✅ **強力支持** | 唯一消費端（`/history`）已由 narrow ＋ backfill 完全覆蓋，逐位元一致 |

---

## 11. 正式施工必須調整的 implementation details

1. **`/results` 的 analyzed_at 索引必須來自 `snapshots`（或另建 per-refresh 索引表），不得用
   `DISTINCT` over narrow。** 這是本輪唯一的效能回歸，已驗證修法。
2. **回填必須 write-through**：從 snapshot 算出的缺格值應寫回 narrow 表，否則每次開圖都重付
   最壞情況 192 ms。
3. **`test_selection_regression.py::_view()` 需要同時回傳引擎 `result`**，才能讓
   `per_expiry_order` 改基於 `expiry_ranked`（RL-33 修復）。不改的話只能退到 `expiry_top10`，
   覆蓋率會低於今天。
4. **narrow 表的主鍵設計要複審**——三個 TEXT 欄位的 PK 佔 46.8%。可考慮 `candidate_key` 的
   數值化編碼或 `scenario_id` 的 surrogate key。**這不影響本輪結論（58.70× 已含此成本）**，
   但是可再拿的收益。
5. **latest-only 覆寫要確認 autovacuum 覆蓋**，否則冷門劇本會長期帶 MVCC 死列。
6. **A/B parity 測試一律比 JSON 文字，不比 Python 物件**（tuple/list 假陽性）。
7. `cost_from_snapshot()` 抽進正式模組時，**運算式順序必須逐字保留**——浮點加減不可交換，
   改順序就失去逐位元一致。建議直接與 `scenarios.natural_cost` 共用同一段算術而非各寫一份。

---

## 12. Prototype 的處置

- ⚠ **與 `/prototype` skill 的一處偏離，需 Owner 裁示**：skill 規定量測台程式碼應存進
  **throwaway branch**、不留在工作分支。但本 session 的硬性規則是「**未經明確許可不得 push 到
  指定分支以外的任何分支**」。兩者衝突時老弟選擇遵守後者——量測台因此**留在指定分支的
  `docs/prototypes/`**，以 `PROTOTYPE_` 前綴明確標記、與 production 樹完全隔離
  （`option_chaser/`／`api_app/`／`src/`／`tests/` 零改動）。
  **Owner 一句話即可改為 throwaway branch**；或直接 `git rm docs/prototypes/PROTOTYPE_*.py`
  一行移除，不影響任何 production 行為。
- scratch 資料庫 `octest_proto_WIPE_ME` 已可刪除；本機 PG 實例非 production。
- **本文件（結論）留在工作分支**，因為它是 Owner 明文要求的交付物。
- 正式施工時真正被抽回的只有 `cost_from_snapshot()` 這個純函式的概念與運算式順序。

---

## 13. 驗收判定

| Gate | 門檻 | 實測 | 結果 |
|---|---|---|---|
| **Functional** | 零產品功能退化 | 0 mismatch／100 輪（detail wire／champion／baseline return／Raw Data／CSV／per-expiry ordering） | ✅ |
| **Correctness** | ranking／return／heatmap／identity／historical cost parity | 4,626 次 backfill 比對全數逐位元一致；guard 修復 100/100 | ✅ |
| **Performance** | 主要 current-path 不得惡化 | 修正後全部改善（寫 23.6×／detail 讀 30×／history 44,261×／`/results` 1.58×）；**天真實作的 `/results` 回歸已找到根因並驗證修法** | ⚠→✅ |
| **Storage** | 至少一個數量級 | **58.70×**（audit 預測 62×，差 5.3%） | ✅ **強證據** |

**判定：PASS_WITH_CHANGES**

「WITH_CHANGES」的原因是 §11 的 7 項——尤其第 1 項（`/results` 索引來源）在天真實作下是**真實回歸**，
必須在正式施工時改掉。其餘 gate 全數通過。

**READY_FOR_SCALING_TICKETS**
