<!-- 正式發布於 GitHub issue #251（label: ready-for-agent）。本檔案是同一份 spec 的 repo 內副本，供離線閱讀與後續 /to-tickets 引用；兩者內容一致，issue 為權威版本。 -->

# 第 0 部：OPTION-SCALING-SPEC-RECONCILE-002 — Remove Superseded Historical Storage Assumptions

**對象**：spec `OPTION-SCALING-SPEC-001`（GitHub issue #251，repo 副本 `docs/spec/scaling-foundation.md`）。
**性質**：canonical architecture 的 reconciliation。**不改 production code、不拆票、不開 PR、不做 migration。**
**證據等級**：本輪以 23 個並行 agent 做 consumer audit ＋ 三路對抗驗證（hidden-consumer／replacement-completeness／
user-visible-breakage），其中一路**實際啟動應用程式呼叫兩支端點**、一路**用 repo 自己的引擎跑 30 次模擬刷新×4 seeds**。
全部主張皆有 `file:line`。工作目錄已核對與 HEAD 逐位元相同（audit 期間出現的暫時性實驗改動已還原）。

---

## R0. 本輪最重要的一句話

> **Owner 的「該退役」判斷成立；但委託中指定的替代來源不成立，而真正的替代來源是我們自己已經在存的 raw snapshot。**

這一句同時是好消息與壞消息：
- **壞消息**：`exact OCC contract historical quotes → 取代 SpreadHistory 的保存需求` 這條**在證據上不成立**（R1）。
- **好消息**：不需要它。`cost` 是 raw snapshot 上的 1–3 個加減，**同一 vendor、同一瞬間、同一最差成交口徑、免 credential、任何腿數**——
  逐位元可重算（R2）。因此 **OD-06（snapshot 永久保存）不是成本負擔，而是整個瘦身方案的地基**。

---

## R1. 委託前提的更正（含反證）

委託原文：「Spread / Butterfly 的歷史 net cost 可由各腿 historical quotes deterministic 計算 ⇒ 為 Spread History
永久保存 result / snapshot 已是 superseded legacy design」。

**這條有三個獨立、各自即足以推翻它的反證**：

| # | 反證 | 證據 |
|---|---|---|
| **R1-a** | **預設組態下替代路徑完全不存在。** `GET /history` 只過 `_require(scenario_id)`，無任何 credential gate；`GET /iv-history` 在 `_historical_iv_enabled` 為假時回 **403**，而該旗標要求 `mode==MODE_CUSTOM` ＋ provider ＋ credential `status=="ok"`，出廠預設是 `DEFAULT_LABELS[HISTORICAL_IV] = "無"`。**實測**：一個刷新 3 次的新劇本，`/history` → **200 帶完整 cost 序列**，`/iv-history` → **403**。 | `api_app/main.py:1136-1146`（無 gate）／`:1275-1278`（403）／`:1502-1511`（判準）／`:1457-1462`（預設）；`api_app/providers.py:31`。取得該 credential 正是 repo 自己記載**至今未解**的 blocker #111 |
| **R1-b** | **兩個功能的閘門是「不相交」而非「包含」——Butterfly 完全落在替代路徑之外。** SpreadHistory 渲染條件是 `legs.length >= 2`（**含三腿**）；IvHistory 是 `legs.length <= 2`（**排除三腿**）。交集只有兩腿 Vertical。後端更是結構性的：`leg_names = ("buy","sell")` 再 `zip` 掉第三腿，且中腿的 `quantity=2` 權重無處表達，而 butterfly 的 `natural_cost = low.ask − 2.0×mid.bid + high.ask` 需要全部三腿與那個 2 倍權重。**且 SpreadHistory 只畫跨 family 冠軍，而 repo 自己的凍結多 family 基準冠軍正是 `call-fly`。** | `src/SpreadHistory.tsx:184`；`src/IvHistory.tsx:586`；`option_chaser/ivpipeline.py:835,837`；`option_chaser/scenarios.py:141-142`；`src/family.ts:97-109` → `src/ScenarioDetail.tsx:245,273`；`tests/test_selection_regression.py:676-679`；`e2e/smoke.spec.ts:2924-2931`（Butterfly 圖表可見的既有 e2e） |
| **R1-c** | **即使在兩腿交集內，那也不是同一條序列。** 不同 vendor（Cboe 延遲 CDN vs `api.marketdata.app`）、不同時刻（盤中任意秒 vs 前一交易日收盤）、粒度塌縮（`merged = {q["date"]: q}` 每日至多一點 vs 每次刷新一點、秒級）、深度上限 365 天且只能向前補、`_num()` 把真實的 `0.0` bid 映成缺值。**且今天圖表最新一點與同頁「Net Worst（保守進場成本）」逐位元相同（實測 0.49 == 0.49），換來源會打破這個一致性。** | `option_chaser/ivpipeline.py:598-600`／`:574-578`；`option_chaser/store.py:758`；`option_chaser/data/cboe.py:96`；`option_chaser/data/marketdata.py:93-106`；`src/AnalysisReport.tsx:286` |

**另外兩項一併更正**：
- 替代路徑**今天沒有任何程式碼**：`natural_cost` 在 `ivpipeline.py`／`ivreconstruct.py`／`ivspread.py` 零命中，
  且價格根本不上 wire（`points` 只序列化 `{date, iv, low_confidence}`）。那是**新增後端工作**，不是接線。
  （`option_chaser/ivpipeline.py:716-721`）
- `contract_iv_history` **只在使用者開過 IV 卡片的合約上才有資料**（`_ensure_contract_history` 只從 iv-history
  端點觸發，`service.py` 零引用），不是刷新時自動累積。刷新路徑從未寫入它。

---

## R2. 更正後的替代來源：raw snapshot（本輪的關鍵發現）

**`cost` 的定義是純算術**：

```
natural_cost(候選) =  Spread    : long.ask − short.bid
                      Butterfly : low.ask − 2.0×mid.bid + high.ask
                      Single-leg: contract.ask          （option_chaser/scenarios.py:138-143）
```

**而 raw snapshot 存的正是這些數字**：`ChainSnapshot.contracts` 是**未經裁切的完整鏈**，每筆 `OptionContract`
帶 `bid`／`ask`（`option_chaser/models.py:39-40, 48-54`；未裁切這點見 Wayfinder F6）。
`candidate_key` 完整編碼 strategy ＋ 全部履約價 ＋ 到期日（`option_chaser/service.py:623-635`），
而 `find_contract(snap, option_type, strike, expiry)` 已存在（`option_chaser/data/snapshot.py:66-75`）。

> ⇒ **`cost(candidate_key, snapshot)` 是一個完全決定的純函式，逐位元重現今天存下來的那個數字。**
> 同一個 vendor、同一個瞬間、同一套最差成交口徑、**免 credential、任何腿數、任何 family**。

**這推翻了 spec #251 §3.4 的 L2 例外論證**。原論證說「重建要 96 秒以上、放不進 read path」——那是「**重跑整份分析**」
的成本（研究 M8 的 3.21s 快路徑／REPAIR-03 的 7.543s 完整校準路徑）。但走勢圖只要 `cost`，而 `cost` 不需要引擎、
不需要 r／q、不需要 IV 反解、不需要校準。**原前提本身就錯了。**

L2 materialization 仍然值得做，但**理由必須改寫**：不是「重算太慢」，而是「**重算要載入 N 份 snapshot**」——
30 次刷新 × 0.48 MiB（TLT）≈ 14 MiB／2.55 MiB（SPY）≈ 76 MiB 的 Neon 讀取與反序列化。
（對照：今天讀 30 份完整 view ＝ **365 MiB**，所以就算完全不 materialize、改為即時從 snapshot 重算，
**也已經比今天好 25 倍**。）

### R2.1 由此得到的分層架構（本輪的核心修正）

```
L0  raw snapshot（OD-06，永久）
      └─ 完整、免 credential、任何腿數、與當時逐位元相同的 cost 唯一冷來源
           ↓ 純函式 natural_cost∘find_contract，無引擎、無 vendor
L2  narrow (scenario_id, analyzed_at, candidate_key, cost)（OD-07）
      └─ 純粹的 read-path 熱快取；缺格可隨時從 L0 回填
           ↓
L3  歷史 results.view 完整內容 → 整份退役
```

**這一層關係解決了本輪對抗驗證最嚴重的那個發現**：OD-07 的「只 materialize 可見候選」被實測為
**Butterfly 30 點只剩 2–9 點（損失 67–93%）、Vertical 在 spot 跌 17% 那個 seed 20 點只剩 2 點**
（用 repo 自己的引擎、4 個 seed 跑出來的）。原本這是「無法挽回的可見退化」；
**但 L0 仍在（OD-06），那些缺格是可回填的**——narrow 表是快取不是真相，真相在 snapshot。
因此 OD-07 的窄化從「不可逆的資訊損失」降級為「**可回補的快取覆蓋率選擇**」。

⚠ **誠實揭露**：從 snapshot 重算 cost 的程式碼**今天不存在**，是新增工作（純函式層＋一條回填路徑）。
本輪只定架構，不施工。

---

## R3. Consumer Audit 結果（每一項的今日真實消費端）

| 資料 | 今日 production 消費端 | 替代來源 | 分類 |
|---|---|---|---|
| **歷史 `results.view`（非最新列的完整內容）** | **僅一處**：`GET /history` → `spread_cost_history()`，而它只讀 `analyzed_at`／`meta.spot`／`all_candidates` 內單一 key 的 entry | narrow 表（熱）＋ raw snapshot（冷） | **superseded legacy** |
| `results[].all_candidates` | **僅一處**：同上（`store.py:278`）。前端型別從未宣告它；detail wire 早已剝除（`store.py:871`） | 同上 | **superseded legacy（形狀），canonical（其中兩腿以上的 `cost` 事實）** |
| ↳ 其中 **single-leg** 的 entries | **零**——SpreadHistory 在 `legs.length < 2` 直接 `return null` | n/a（無消費端） | **superseded legacy（純寫入死重）** |
| ↳ 其中 `baseline_return`／`rank_in_expiry`／回應的 `spot` | **零**——`src/` 只讀 `cost` 與 `analyzed_at` | n/a | **superseded legacy（wire 死重）** |
| ↳ 其中 **Butterfly** 的 `(analyzed_at, candidate_key, cost)` | **有，且有 e2e 釘住**；且是 repo 凍結基準的冠軍 family | **只有 in-house**（vendor 路徑結構上做不到） | **canonical（事實本身，非陣列形狀）** |
| **歷史 raw snapshots（非最新列）** | **零。而且比「未被使用」更強——結構上不可定址**：Storage port 沒有任何列舉方法，Postgres 只有單列點查詢，唯一讀取端硬綁 `latest_result(...).analyzed_at`，25 條路由沒有一條接受 `analyzed_at` | **無**（Cboe 無歷史端點，#111 已窮舉免 key 路線） | **canonical（L0 seed）——維持 OD-06** |
| **最新 raw snapshot** | `/raw-data`／`/raw-data.csv` 面板 | n/a | **current-only（兼 L0 seed）** |
| `results[].candidates`（扁平 key 清單） | `find_candidate()` 的 fallback 分支，**只在最新列上** | n/a | **current-only** |
| **最新 `results.view`** | detail 頁 ＋ iv-history gate | n/a | **current-only（明確不在本輪範圍）** |
| `GET /api/scenarios/{id}/results`（analyzed_at 索引） | **零前端呼叫端**（`src/api.ts` 全部 URL 字面量中不存在），只有測試呼叫。**且它是實質成本**：`result_history()` 無條件 `SELECT` 含 `view` 的整列，只為投影出一串時間戳 | n/a | **superseded legacy** |
| `GET /api/scenarios/{id}/events` | **零前端呼叫端** | n/a | **未使用（保留：每次刷新僅約 177 bytes，佔比 0.0014%，是列數問題不是位元組問題）** |
| `contract_iv_history` | 只從兩支 iv-history 端點；`service.py` 零引用（**不在刷新路徑上**） | 可向 vendor 重抓（需 credential，且只能向前補） | **cache（但無界，見 RD-2）** |
| `iv_observations` | 同上（legacy 重錨定家族） | 同上 | **cache（但無界、無 retention、`delete_scenario` 不 cascade，見 RD-2）** |
| `iv_backfill_runs`／`diagnostics`／`rate_cache`／`dividend_cache`／`treasury_year_cache` | 各自既有消費端 | 各自可重抓／重生 | **cache（皆已有界，不動）** |
| `data_source_settings`／`provider_credentials`／`provider_verifications` | Settings ＋ 來源選擇 ＋ IV gate | n/a（使用者 token 無法重導出） | **canonical（零成長）** |
| **CLI 檔案系統 snapshots**（`snapshots/{symbol}_{fetched_at}.json`） | `option_chaser/cli.py:163` → `run_offline` → `load_snapshot`，**真的重播任意歷史快照**，且是 `pyproject.toml` 的 console entry point | n/a | **canonical（但是另一個 store：本機磁碟、無 scenario_id、部署函式不可達）** |

> ⚠ **最後一列必須寫進 spec**：任何「退役歷史 snapshots」的敘述**必須指明是哪一個 store**，
> 否則字面上是錯的——DB 表與 CLI 檔案是兩個不同的東西。

---

## R4. 修正後的 Owner Decisions

### OD-06（修正）— Raw option-chain snapshot

**維持永久保存，但理由升級。** 原理由是「不可重新取得的市場事實／未來 re-analysis 的 canonical seed」。
本輪新增一條**更強的、當下就成立的**理由：

> **它是歷史 net cost 唯一的完整、免 credential、任何腿數、與當時逐位元相同的來源。**
> 一旦刪除，Butterfly 與未持有付費 token 的使用者將永久失去補回歷史走勢的能力。

Foundation 階段仍維持現有 storage location、不新增 object-storage dependency。

**新增一條實作紅線（RL-28）**：refresh-run 對共用同一個 symbol 的 K 個劇本，會寫入 **K 份逐位元相同的
snapshot**（一列一個 `scenario_id`）。這是**去重的機會，不是刪除的理由**——內容定址／共享是零刪除的節省，
應在 spec 中登記為可選最佳化（不在本輪施工）。

### OD-07（修正）— Historical candidate trend

**維持「只 materialize 使用者實際點得到的 candidate」與最小四欄，但語意重新定性**：

> narrow 表是 **L2 熱快取，不是真相來源**。真相是 L0 snapshot。
> 因此覆蓋率不足產生的斷格 **可從 L0 回填**，不是不可逆的資訊損失。

**修正「永久保存暫不設 retention」的措辭**：narrow 表**可以**永久保存（它極小），但它的永久性**不是**
產品保證的來源——產品保證來自 L0。這個區分很重要：它讓未來若要調整 narrow 表覆蓋率或欄位，
不必再走一次不可逆決策。

**新增（本輪實測結果，必須寫進 spec）**：visible-only 窄化在 repo 自己的引擎上實測，
Butterfly 30 點只剩 **2–9** 點、Vertical 在大幅方向性移動的 seed 20 點只剩 **2** 點；
production 的比例比該 fixture **更差**（可見候選佔比 0.07% vs fixture 的 12%）。
**⇒ 若不實作 L0 回填，OD-07 的窄化會讓 Butterfly 走勢圖失去大多數歷史點。回填路徑因此是 OD-07 的必要配套，不是可選項。**

### OD-08（不變）— Diagnostics ownership

不變。另補一項：`iv_observations` 依 OD-08 同屬 user-scoped operational data，
且它**沒有任何 retention、`delete_scenario` 也不 cascade** 它——列入 RD-2。

---

## R5. 修正後的 Canonical Storage Principle

原則本文維持，並**新增 Owner 本輪的措辭為第二句**：

> 保存不可確定性重建的 seed ＋ provenance ＋ version；deterministic derived output 原則上不永久保存，
> 除非它位於高成本 read path、必須 materialize。
>
> **並且：不要因為「以前已經存了」就把它升格成永久需求。**
> 判準永遠是「今天真的有誰在讀它」與「刪掉之後還能不能拿回來」，不是「它一直都在」。

**四層分類不變，但 L2 的判準措辭更正**：
「可由 seed 重建，但**重建成本結構上不能放進 read path**」——本輪確認對 `cost` 而言，
那個成本**不是 CPU（引擎），是 I/O（載入 N 份 snapshot）**。原 spec 的 96 秒論證作廢。

---

## R6. 對 spec #251 的具體修改清單

### 刪除／作廢

| 項目 | 處置 | 理由 |
|---|---|---|
| §3.4 全節「L2 必要例外」的 96 秒論證 | **改寫** | 前提錯誤：`cost` 不需要跑引擎（R2） |
| §3.5 L-2「重建成本結構上放不進 read path ⇒ L2 例外」 | **改寫**為 I/O 論證 | 同上 |
| §6.2「必須誠實揭露的行為差異」段落中「這不是 blocker，是知情事項」 | **升級為必要配套** | 本輪實測顯示損失是多數而非偶發（R4／OD-07） |
| §19-EG-2 | **關閉** | OD-06／OD-07 已定；且本輪確認 L0 是回填來源，「歷史 view 完整內容保留多久」不再需要 Owner 裁示——**答案是可以全退役，因為 L0 在** |

### 新增

| 項目 | 內容 |
|---|---|
| **§3.3 分類表** | 新增 5 列：single-leg `all_candidates`（superseded）／`baseline_return`＋`rank_in_expiry`＋`spot`（wire 死重）／`GET /results` 端點（superseded）／CLI 檔案系統 snapshots（另一個 store）／`iv_observations`＋`contract_iv_history`（無界 cache） |
| **新 Stage S1-0b「L0 回填路徑」** | 純函式 `cost_from_snapshot(snapshot, candidate_key)` ＋ 一條回填入口。**排在 S1-1 dual-write 之前**——它是 OD-07 窄化的安全網 |
| **RL-28** | snapshot 的 K 份重複是去重機會、不是刪除理由 |
| **RL-29** | 任何「退役歷史 snapshots」敘述必須指明 store（DB 表 vs CLI 檔案） |
| **RL-30** | 不得以 exact-contract vendor 路徑作為任何退役的理由（R1 三條反證） |
| **RL-31** | 退役實作不得把 `results.view` 設為 NULL／`{}`：`spread_cost_history()` 硬下標 `view["results"]`／`["analyzed_at"]`／`["meta"]["spot"]`，且 `ResultRecord.view` 型別非可選、以位置參數建構 |
| **RL-32** | 「每次刷新都永久留下完整分析世界」**不再是 canonical requirement**（Owner 本輪明文） |
| **AC 新增** | (a) 對任一歷史 `analyzed_at` 與任一 `candidate_key`，可從 L0 重算出與當時 `all_candidates` 記錄**逐位元相同**的 `cost`；(b) Butterfly 與 single-leg 皆涵蓋；(c) 全程零 vendor 呼叫、零 credential |

### 改寫

| 項目 | 改法 |
|---|---|
| §6 狀態機 | 插入 **1-0b（L0 回填路徑）**於 1-0 與 1-1 之間；**1-6 的範圍擴大**——原本只清「歷史 view 完整內容」，現在確認整份歷史 view 可退役（narrow ＋ L0 已覆蓋全部消費端） |
| §6.2 parity proof | parity 的定義擴充：除既有比對外，**必須額外證明 L0 重算與 `all_candidates` 記錄逐位元相同**（這是新的、更強的 parity，且它同時證明 OD-07 窄化是安全的） |
| §17 AC-2 | 「曾掉出 visible 集合」的 case 從「分類計數並報告」升級為「**必須由 L0 回填路徑覆蓋，並驗證回填值逐位元正確**」 |
| §13.1 測試接縫 | 不變（沿用既有七個、零新增）。L0 重算純函式落在接縫 2；回填端點落在接縫 1；逐位元 parity 落在接縫 5 的既有慣例 |

### 保留不動

- 測試接縫沿用既有七個、零新增（Owner 已裁示）
- `chain_backoff` 持久化進 Storage port ＋ RL-19 零 payload 紅線（Owner 已裁示）
- Treasury Cron ＋ 同步保底（OD-01）
- Ownership A-1 ＋「不等於 privacy」（OD-04／RL-21）
- Cboe 429 全節（OD-05）
- Observability 七項封頂
- 全部既有 RL-01～RL-08 產品行為保存紅線

---

## R7. 修正後的 DB Growth Model

**今日（每次刷新、每個劇本，三 family 全開）**

| 項目 | 大小 | 依據 |
|---|---|---|
| `results.view` | **~12.18 MiB**，其中 `all_candidates` 佔 **96.4%**（74,011 筆 / 11.78 MiB） | 【研究文件一手實測 2026-09-03】 |
| `snapshots` | **0.48 MiB**（TLT，2,414 合約）／**2.55 MiB**（SPY，12,534 合約） | 【研究文件一手實測】 |
| `events` | ~177 bytes（佔 0.0014%） | 【本輪由酬載形狀計算】 |
| diagnostics／全部 IV 表／三個市場事實 cache | **0 列** | 【本輪由呼叫圖確認：刷新路徑結構上不觸及】 |
| **合計** | **~12.66 MiB／次／劇本** | 【兩個實測項相加】 |

⚠ **放大器（本輪新發現，結構性）**：refresh-run 對共用同一 symbol 的 K 個劇本寫入 **K 份逐位元相同的 snapshot**。

**退役後（本輪架構）**

| 階段 | 每次刷新永久成長 | 性質 |
|---|---|---|
| 今天 | ~12.66 MiB | — |
| 退役歷史 view，narrow 保留**全部合格候選** | snapshot ＋ **~3.97 MiB** | 【推估，56 B/entry 實測 × 74,011】逐位元不變，但仍無界 |
| 退役歷史 view，narrow 只保留 **visible**（OD-07） | snapshot ＋ **~2.7 KiB** | 【推估】**約 4,500 倍差距**；缺格由 L0 回填 |
| **本輪建議態** | **≈ snapshot（0.48–2.55 MiB）＋ KiB 量級** | 成長從 O(derived) 降為 O(seed) |

**誠實的殘餘（不變，但要重講一次）**：OD-06 之下 seed 本身仍是每次刷新 0.48／2.55 MiB 的硬成長。
Neon Free 0.5 GB ⇒ TLT 約 **1,000 次**／SPY 約 **200 次**刷新後仍會滿。
**退役把撞牆時間往後推約一個數量級，沒有消滅它。** 屆時的解法依 OD-06 是搬 archival／object storage、
不是刪 seed；而那明文屬 Out of Scope。
**snapshot 去重（RL-28）是本輪新發現的、零刪除的節省來源**，值得在那之前先做。

⚠ **成長模型的兩個既有盲點（本輪新發現，原研究文件從未分析）**：
`contract_iv_history`（每個開過 IV 卡片的 OCC 合約一列，`points` 陣列 append-only、只在**讀取時**裁到 365 天、
合約到期後也不 GC）與 `iv_observations`（每 symbol 每年約 66 列、無 retention、`delete_scenario` 不 cascade）。
兩者都**不在刷新路徑上**（不進每次刷新的數字），但都在長期總量裡，且都**無界**。→ RD-2。

---

## R8. 仍然存在的 Owner Decisions（只有兩題）

本輪把 spec #251 原本的 EG-2 關閉，並把對抗驗證浮現的 RD-2／RD-3／RD-5 **全部解掉**——
因為它們都建立在「替代來源是 vendor」這個被推翻的前提上；改用 L0 之後，
credential 不需要、Butterfly 有解、序列逐位元相同。**剩下真正需要大哥拍板的只有兩題**：

### RD-1｜narrow 表的覆蓋率要選哪一檔？

**這是唯一會影響使用者體感的一題，但已經不是不可逆的了**（缺格可從 L0 回填）。
差別在於「打開走勢圖時有多少點是立刻就有的、多少點要等回填」：

- **(a) 只存 visible top-N（OD-07 現行）**：~2.7 KiB／次。Butterfly 立即可見點實測只剩 2–9/30，其餘靠回填。
- **(b) 存全部合格候選的窄欄位**：~3.97 MiB／次。逐位元不變、零回填需求，但仍是無界成長。
- **(c) 中間帶（例如每到期日前 50）**：兩者之間。
- **老弟的建議**：**(a) ＋ 必做 L0 回填**——因為回填是純函式、免 vendor、逐位元正確，
  而 (b) 保留了成長類別本身（本輪要消滅的正是這個）。

### RD-2｜`contract_iv_history` 與 `iv_observations` 的 retention／GC 政策？

本輪新發現的兩個無界 store，**沒有任何決策紀錄涵蓋它們**，且原研究文件完全沒分析過。
它們不在刷新路徑上（不影響每次刷新的數字），但在長期總量裡會累積。

- (a) 維持現狀（只在使用者開 IV 卡片時成長）
- (b) `contract_iv_history` 的 `points` 改為**寫入時**裁到 365 天渲染窗；到期合約的列做 GC
- (c) `iv_observations` 加進 `delete_scenario` cascade 與／或保留窗
- (d) 併入未來 ownership boundary 一起處理（依 OD-08 它們是 user-scoped）

> ⚠ 這兩題**都不擋 spec、不擋拆票、不擋前面任何一步**。RD-1 只擋 S1-1 的欄位定案，RD-2 完全不擋。

---

## R9. 誠實揭露（本輪無法確立的事）

1. **本輪未取得 production 部署的實際組態**。所有「預設 403」的結論是**出廠預設**，不是大哥實際部署的狀態
   ——credential 存在資料庫裡，不在 repo 裡。**若大哥的 production 其實已設定並驗證過 Market Data App token，
   R1-a 這條反證消失**（但 R1-b Butterfly 與 R1-c 序列不同一這兩條仍然成立，結論不變）。
2. **L0 重算的程式碼今天不存在**，是新增工作。本輪只證明它在數學與資料上完全可行（R2），未實作、未量測。
3. **走勢圖點數損失是模擬值**：用 repo 自己的引擎跑 30 次模擬刷新 × 4 seeds，spot 走 ~25% 年化隨機漫步，
   fixture 是 22 履約價/到期日的合成鏈。方向在 4 個 seed 上穩健，且 production 比例更差，
   但「真實使用者會掉幾點」**沒有 production 遙測**。視為嚴重度下界，不是預測。
4. **`results.view` 12.18 MiB 與 snapshot 0.48／2.55 MiB 引用自既有研究文件的一手實測，本輪未重跑**。
   本輪自己量的是 checked-in fixture 上的 per-entry 位元組數（148 B 完整／56 B 窄），交叉核對誤差約 13%。
5. **completeness critic 這一路 agent 因 session limit 未跑完**——本輪的「還缺什麼」自查不完整。
   已知未涵蓋：`docs/adr/` 是否有本輪會抵觸的既有 ADR（老弟人工核對過 ADR-0001 與本輪無交集，
   但未逐份檢視全部 ADR）。
6. **audit 期間工作目錄曾出現一次暫時性的 production code 實驗改動**（`store.py:680` 被 stub 成 `[]`），
   已還原；本輪結束時 `git status` 乾淨、`git diff HEAD` 對 `option_chaser/`／`api_app/`／`src/` 零差異。

---

## R10. 判定

| 問題 | 答案 |
|---|---|
| 委託的「superseded」判斷成立嗎？ | **成立，但替代來源要換人**——不是 vendor 的 exact-contract quotes，是我們自己的 raw snapshot |
| 歷史 `results.view` 可否整份退役？ | **可以**（narrow 熱快取 ＋ L0 冷來源已覆蓋唯一消費端） |
| 歷史 raw snapshots 可否退役？ | **不可以，而且理由比 OD-06 原本寫的更強**——它現在是整個方案的地基 |
| 是否需要發明 narrow-history table？ | **需要**，且符合 Owner 第 7 條的但書：存在獨立、仍有效的 product requirement（Butterfly ＋ 免 credential 使用者的走勢圖）。但它的定位從「真相」降為「快取」 |
| 是否仍有 Owner Decision？ | **有兩題**（RD-1 覆蓋率檔位、RD-2 IV cache retention），皆不擋 spec 與拆票 |
| 是否 READY_FOR_SCALING_TICKETS？ | **是** |

READY_FOR_SCALING_TICKETS


---

# 第 0.5 部：OPTION-STORAGE-AUDIT-003 對第 0／1 部的量測修正（2026-09-06）

> 全文見 `docs/research/storage-optimization-audit.md`。本節只記**推翻或修正**先前文字之處。
> 量測環境：本機 PostgreSQL 16.13（`default_toast_compression=pglz`）、repo 自身 schema 與引擎、
> `tests/fixtures/xyz_v8_production_scale.json`（600 合約／6 subtype／真實非零 q）。

## A1｜growth model 的單位錯了：12.18 MiB 是「邏輯」不是「落盤」

**實測**：`results.view` 邏輯 21,112,857 B → `pg_column_size` **3,171,586 B**（TOAST pglz **6.66×**）；
snapshot 邏輯 126,279 B → 落盤 **18,498 B**（6.83×）。

⇒ 第 0 部 §R7 與第 1 部全部以 12.18 MiB／0.48 MiB 推算的「Neon Free 能撐幾次」**低估約 6.7 倍**。
**每次刷新的真實落盤合計 ＝ 3,190,261 B ＝ 3.04 MiB**（view 99.41%／snapshot 0.58%／events 0.006%／
其餘 11 張表 0）。Neon Free 0.5 GB ⇒ **168 次**（不是 42 次）。

⚠ 6.66× 是**合成 fixture 上的上界**（`volume`／`open_interest` 值單一，壓縮偏樂觀），
真實資料會低於此值。

## A2｜RD-1 已由量測解決——選項 (b) 是假優化，改列 REJECT

第 0 部 §R8-RD-1 把「narrow 表存全部合格候選」描述為「逐位元不變但仍無界」的保守選項。
**實測推翻**（30 次刷新、含主鍵索引）：

| 方案 | 每次刷新落盤 | 走勢圖查詢（單一候選 30 點） |
|---|---|---|
| narrow **visible-only**（150 列/次） | **32,495 B** | **0.396 ms** |
| narrow **all-qualified**（128,668 列/次） | **26,030,626 B** | 285 ms |
| （對照）今天的完整 view | 3,171,586 B | 380 ms／列 × 30 ≈ 11,400 ms |

⇒ all-qualified **比今天糟 8.2 倍**、查詢慢 **720 倍**。
根因：**關聯表逐列有 header／索引開銷且吃不到 TOAST 壓縮，JSONB blob 吃得到。**

**RD-1 因此收斂**：**(a) visible-only ＋ L0 回填**為唯一合理解；(b) 與 (c) 改列 **REJECT**。
這一題不再需要 Owner 裁示——它已被量測回答。

## A3｜`all_candidates` 的移除同時「改善」效能（非取捨）

**實測**：`save_result` 981.2 ms → **40.7 ms**（24.1×）；單列 `SELECT view` 380.1 ms → **10.4 ms**（36.5×）；
落盤 3,171,586 B → **203,010 B**（−93.6%）。**功能面**：`project_for_detail` 早已在 wire 剝除它
（detail 投影 431,675 B ＝ 儲存的 2.18%），current UI 結構上不依賴它。

**實證消費端邊界**：獨立 worktree 把它 stub 成 `[]` 跑全套後端測試，**只有 9 條失敗**——
4 條契約樣本 drift、1 條 `/history`（唯一真產品消費端）、1 條「儲存全保真」設計斷言、
3 條直接測該欄位本身。**CLI golden fixtures 與 `test_selection_regression.py` 全數通過。**

## A4｜新增兩條紅線（總數 32 → **34**）

| # | 紅線 |
|---|---|
| **RL-33** | **不得把 `all_candidates` 就地清空而不重新定基 `test_selection_regression.py` 的 `per_expiry_order` 軸。** 該軸由 `res["all_candidates"]` 構造（`:78-80`），比對方式是**同一次執行內 before vs after**（`:175`）——欄位變空時兩邊都是 `{}`，斷言**恆真而非紅燈**。實測已確認：stub 成 `[]` 時該檔案全數通過。移除前必須把該軸改基於 `expiry_ranked` 或 narrow 表 |
| **RL-34** | **`snapshots` 的任何欄位都不得移除。** `/raw-data` 面板逐欄渲染全部欄位（`src/RawData.tsx:115-121`，含引擎零消費的 `last`），且 CSV 匯出用 `fields(OptionContract)` **結構性輸出全部欄位**（`data/snapshot.py:60`）——刪欄位會靜默改變 CSV 表頭。H3「minimal replay seed」因此整案 **REJECT** |

## A5｜新增一個第 0／1 部未涵蓋的候選：snapshot 去重

`refresh-run` 對共用同一 symbol 的 K 個劇本寫入 **K 份逐位元相同** 的 snapshot
（實測 `count(DISTINCT md5)=1 / count(*)=3`）。**實測（K=5×30 次）**：payload 落盤省 **80.0%**
（理論上界 (K−1)/K），點查詢延遲 1.83 ms → **1.79 ms（無代價）**。

**但列 `VALIDATE_MORE` 而非 `DO_NOW`**：`delete_scenario` 的 cascade、archive／restore 語意、
blob refcount／GC 都需重寫，且**收益完全取決於 production 的真實 K（本輪無遙測，K=1 時零收益）**。

## A6｜以下方案經量測後明確 REJECT

| 方案 | 量測結果 |
|---|---|
| TOAST 改用 `lz4` | 落盤 3,171,586 → 3,665,657 B，**變大 15.6%**（pglz 在本負載上較優） |
| `bytea` + 應用層 zlib 取代 JSONB | H1 之前省 33.1%；**H1 之後只剩 113 KiB／次**，卻永久失去 JSONB 運算子 |
| snapshot 欄位瘦身（含只刪 `last`） | 見 RL-34——功能退化 |
| 退役 `events` | 177 B／次 ＝ **0.006%**，量測上等於零 |

## A7｜修正後的理論下限

| 情境 | 每次刷新永久成長 | Neon Free 0.5 GB |
|---|---|---|
| 今天 | 3,190,261 B | 168 次 |
| 移除 `all_candidates` ＋ narrow(visible) | 254,180 B | 2,113 次（12.5×） |
| **＋ 歷史 view 整份退役** | **51,170 B** | **10,494 次（62.3×）** |
| ＋ snapshot 去重（K=5） | 36,372 B | 14,764 次（87.7×） |

**理論下限 ＝ narrow 32,495 B ＋ snapshot 18,498 B ＋ events 177 B ≈ 51 KiB／次**——
OD-06 之下 snapshot 是不可壓縮的地板。

## A8｜全 schema 窮舉結論（14 張表）

**具成長性的只有四張**：`results`（canonical history，accidentally unbounded）、
`snapshots`（L0 seed，OD-06 永久）、`events`（append-only，零前端消費端，量體可忽略）、
以及**不在刷新路徑上但無界**的 `contract_iv_history` 與 `iv_observations`。
其餘九張皆 bounded（單列 CHECK／per-symbol／per-year／per-provider upsert）或
已有 retention（`diagnostics`，全域最新 200 筆 trim-on-write）。


---

# 第 1 部：OPTION-SCALING-SPEC-001（原文）

> ⚠ **以下為 SPEC-001 原文，逐字保留供追溯。**
> 凡與上方第 0 部（RECONCILE-002）衝突之處，**一律以第 0 部為準**。
> 被取代的段落已就地插入標記；未標記者仍然有效。

# OPTION-SCALING-SPEC-001 — Scaling Foundation Spec

**基準**：`origin/master` HEAD `864dd5c`（Initial V2 已 merge 上線）；工作分支 `claude/implement-tfm9oa`。

**上游輸入（Source of Truth，本 spec 不重新辯論已定案結論）**：
- `docs/wayfinder/scaling-foundation.md`（OPTION-SCALING-WAYFINDER-002 reconciliation，2026-09-05，標記 `READY_FOR_SCALING_SPEC`）— **最高優先級**
- `docs/research/market-data-lifecycle-scaling.md`（2026-09-03）
- `docs/research/runtime-targeted-scaling.md`（2026-09-04）

**本 spec 的性質**：把 Wayfinder reconciliation 的 NOW／BLOCKED_ON_OWNER 分級，加上 Owner 新裁示的 **OD-06／OD-07／OD-08**，固化成可拆票施工的規格。**不重做 Wayfinder、不重新辯論 OD-01～OD-08。**

---

## 1. Problem Statement

Option Chaser 今天是一個單人產品，功能面（Initial V2 三個 Strategy Family）已經上線並通過真機驗收。但從使用者的角度，有四件事在「還沒有第二個使用者」的今天就已經是問題，或者在第一次真的有第二個使用者時會立刻變成問題：

**（一）資料庫會在大約 40 次刷新之後寫滿，然後整個產品停止運作。**

每按一次刷新，系統會把當次算出來的**全部候選**完整存進資料庫。實測（真實 TLT 鏈，三個 family 全開）單列 `results.view` JSONB 是 **12.18 MiB**，其中 **96.4%**（74,011 筆、11.78 MiB）是 `all_candidates`。`results` 與 `snapshots` **完全沒有 retention 機制**。Neon Free 每個 project 只有 **0.5 GB** ⇒ **約 42 次刷新（未壓縮）到 402 次（zlib-6 壓縮上界）就寫滿**。

這件事**不需要第二個使用者就會發生**。它是本輪唯一一個「就算永遠只有 Owner 一個人用，也一定會撞牆」的問題。

而 74,011 筆存進去之後，畫面上真正被讀到的**只有一條折線的 y 值**（淨成本）——`rank_in_expiry`／`baseline_return`／`spot` 在整個 `src/` 生產碼**零讀取端**。

**（二）打開一次歷史走勢圖，會從資料庫讀出整個劇本的全部完整結果。**

`Storage.result_history()` 一律 `SELECT` 含 `view` 的全部欄位。兩個消費端——`GET /api/scenarios/{id}/results` **只要 `analyzed_at`**、`GET /api/scenarios/{id}/history` 只要每份 view 裡的**一筆** entry。一個刷新過 30 次的劇本，開一次走勢圖 ＝ 從 Neon 讀出約 **365 MiB** 並反序列化。Neon Free 每月 egress 只有 5 GB。

**（三）上游報價來源會限流，而系統完全沒有處理，也沒有任何自動復原路徑。**

`cdn.cboe.com` 實測會回 **HTTP 429**（`retry-after: 34`，`server: cloudflare`）。而 `option_chaser/data/cboe.py` 一律 `except Exception → FetchError`：不看 status、不讀 `retry-after`、無 backoff、無 circuit breaker。唯一備援 `data/yf.py` 在 production **結構上不可達**（`yfinance` 不在 Vercel 會安裝的 `[project] dependencies` 裡）。

使用者看到的是無差別的「抓不到報價」，於是按重試 → 又 429 → **retry storm**，自己把限流窗口一直續下去。**這是全站核心功能中斷，不是效能問題**，而且與使用者數量無關——今天就會發生。

**（四）每個市場日的第一批使用者，可能把整輪刷新的時間預算耗在等 Treasury 上。**

Treasury cold miss 最壞 ＝ 3 × 15s ＝ **45 秒**（CSV → XML → 前一年 CSV），而 `REFRESH_RUN_BUDGET` 就是 45 秒、`vercel.json` 的 `maxDuration` 是 60 秒。這是 latency／timeout 的正確性問題，不是容量問題。

**（五）以及一個今天就存在、但要等到第二個使用者才會被看見的問題**：`api_app/main.py` 全檔零身分解析、零 owner 過濾。任何人開站 ＝ `list_scenarios()` 回傳**資料庫裡全部劇本** → 前端把**全部** id 送進 `runBatch` ⇒ 任何一個使用者開站，就刷新全站所有人的劇本，負載變成 **O(U²)**。

---

## 2. Goals / Non-goals

### 2.1 Goals

| # | 目標 | 對應 Destination Criteria |
|---|---|---|
| G1 | 每次刷新的永久儲存成長，等於 **seed ＋ 常數量級的窄事實**，而不是完整 derived payload | D3 |
| G2 | 開一次歷史走勢圖，不會從 Neon 讀出整個劇本的全部完整 view | D4 |
| G3 | 對任何一份歷史結果，都能從**獨立欄位**讀出當時的 `params`（含 r／q）、provenance 與 `engine_version`，不必解析 `view` JSONB | D9 |
| G4 | Cboe 回 429 時系統不形成 retry storm；使用者看到明確、可理解的狀態 ＋ 資料時間，而不是無差別的「抓不到報價」 | D5 |
| G5 | Treasury 的當日更新由排程完成；使用者的分析路徑正常情況下只讀 DB，不承擔 cold fetch | D6 |
| G6 | 一個 user 的任何動作，不會刷新、不會讀到、不會寫入另一個 user 的劇本 | D1 |
| G7 | 一輪刷新的 chain 抓取數，是「這個 user 自己的 distinct symbol 數」，不是「全站劇本的 distinct symbol 數」 | D2 |
| G8 | 可以回答「昨天對 Cboe 發了幾次請求」「429 幾次」「`results`／`snapshots` 表多大」 | D8 |

### 2.2 Non-goals（本 spec 明確不追求）

- **不追求任何延遲數字目標（p50／p99）**——今天沒有基準線，訂了也無從驗證。
- **不追求「同 symbol 同 freshness window 只打一次 vendor」**——OD-05 已定 30 秒這個**產品參數**，但是否施工跨 request 共用仍在 ADR-0001 的 evidence gate 後面（見 §19）。
- **不追求 privacy**——A-1 建立的是 data boundary，privacy 只能來自 A-2（authentication），而 A-2 不在本 spec 施工範圍。
- **不追求把撞牆問題永久消滅**——OD-06 讓 raw snapshot 永久保存，Neon Free 在 TLT 約 1,000 次／SPY 約 200 次刷新後仍會滿。本 spec 把成長率降一個數量級並讓它變得可觀測、可預測，不宣稱消滅它。

### 2.3 硬紅線（貫穿全 spec，優先於一切最佳化）

> **Performance / product behavior preservation > storage savings.**

不得因 storage 優化改變：candidate identity／ranking／return／champion／heatmap／family behavior／scenario card behavior／current detail payload semantics。詳見 §14。

---

## 3. Canonical Data Classification

### 3.1 Canonical Storage Principle（本 spec 的儲存憲法）

> **保存不可確定性重建的 seed + provenance + version；deterministic derived output 原則上不永久保存，除非它位於高成本 read path、必須 materialize。**

這條原則有一個**不可跳過的前置條件**（OD-02 明文）：**必須先證明 `seed + version → deterministic reconstruction`**，不能因「理論上能重算」就先刪資料。該證明已在 Wayfinder §3.2 完成，結論與其三個真實限制記錄在 §3.3。

### 3.2 四層分類（不是兩層）

| 層 | 名稱 | 判準 | 保存政策 |
|---|---|---|---|
| **L0** | **Seed** | 刪掉就永遠回不來 | **永久保存** |
| **L1** | **Provenance & Version** | 沒有它，seed 無法被正確解讀或重放 | **永久保存** |
| **L2** | **Materialized derived（必要例外）** | 可由 seed 重建，**但重建成本結構上不能放進 read path** | **永久保存最小集合** |
| **L3** | **Pure derived** | 可由 seed 重建，且重建只發生在離線／除錯／稽核情境 | **不永久保存完整內容**（current 那一份除外） |

### 3.3 各資料類型歸屬（逐項）

| 資料 | 層 | 保存政策 | 依據 |
|---|---|---|---|
| `scenarios`（使用者輸入：symbol／target_price／target_month／best_price／worst_price／strategies） | **L0** | 永久 | Canonical Principle |
| `snapshots`（raw option-chain snapshot，未裁切完整鏈） | **L0** | **永久保存，暫不設 retention** | **OD-06** |
| 估值輸入：`rate_by_expiry`／`q_by_symbol`／`iv_shifts`／`delta_bands`／`rate_explicit` 等全部已解析 `AnalysisParams` 欄位 | **L0** | 永久（**必須先從 view 內部拆出成獨立欄位**） | Wayfinder F5、Stage 1-0 |
| Provenance：`rate_curve_used`／`rate_curve_date`／`rate_curve_stale`／`rate_note`／`q_source`／`q_as_of`／`q_stale`／`q_note`／snapshot `source`／`fetched_at` | **L1** | 永久（同上，拆出成獨立欄位） | Wayfinder F5、D9 |
| `engine_version`／view `schema_version` | **L1** | 永久（同上） | Wayfinder §3.2-S5 |
| `results.analyzed_at`／`best_return`／`representative_candidate`／`per_family`／`spot`／`family_eligibility` | **L1／L2** | 維持（**已經是獨立欄位，既有正確設計，不動**） | T07／#224 |
| `events`（SCENARIO_CREATED／ANALYSIS_COMPLETED 等） | **L0** | 永久（記錄「發生過什麼」，不可由 seed 導出；量體極小） | Canonical Principle |
| **Visible-candidate 歷史窄事實**：`(scenario_id, analyzed_at, candidate_key, cost)` | **L2** | **永久保存，暫不設 retention** | **OD-07**、§3.4 |
| `all_candidates` 的其餘欄位（`expiry`／`baseline_return`／`rank_in_expiry`） | **L3** | 可不永久保存（`src/` 生產碼零讀取端） | Wayfinder F1 |
| **current** `results.view` 完整內容（heatmap／payoff／ranking／max P/L／profit region／candidate_pool／axis_sets／expiry_groups） | **L3，但 current 那一份必須在** | **不得為了瘦身而動它的內容或行為** | **OD-03 紅線** |
| **歷史** `results.view` 完整內容（除 L2 窄事實外） | **L3** | 可停止寫入、可 retention（**僅限 Stage 1-6，且需 Owner 對 §19-EG-2 有答案**） | Canonical Principle |
| `diagnostics` | **L3** | 不動既有 trim（最新 200 筆），但**必須加 owner 維度** | 既有設計 ＋ **OD-08** |
| `rate_cache`（當日曲線） | **L3（當日）** | 不動——可重抓 | Wayfinder §2.1 |
| `treasury_year_cache`（過去年份）／`iv_observations`／`contract_iv_history` | **L0（歷史部分）** | 不動——PIT 不可重建事實 | Wayfinder §2.1 |
| `dividend_cache` | **L3** | 不動 | Wayfinder §2.1 |
| `chain_backoff`（本 spec 新增，見 §8） | **控制狀態，不屬 L0–L3** | 短期、可隨時丟棄、**零市場資料** | §8.4 |

> 🛑 **本節論證已被 RECONCILE-002 §R2 推翻。** 96 秒是「重跑整份分析」的成本；
> 走勢圖只要 `cost`，而 `cost` 是 raw snapshot 上的 1–3 個加減（`natural_cost`），
> 不需要引擎、r／q、IV 反解或校準。L2 materialization 仍然值得做，但**理由改為 I/O**
> （重算要載入 N 份 snapshot），不是 CPU。以 §R2 為準。

### 3.4 L2 的「必要例外」為什麼成立（OD-02 要求的證明）

歷史走勢圖需要的 `cost` 序列**理論上可從 seed 重建、實務上不行**：

```
單次三 family 引擎時間（q=0 快路徑，研究 M8 實測）    3.21s
一個刷新過 30 次的劇本                              × 30
                                                   ────────
重建整條走勢圖（下界）                              ≈ 96 秒
```

⚠ **96 秒是下界不是上界**：M8 的 3.21s 是 `loaders=None` 的 q=0 快路徑，不做逐腿 IV 反解校準；而真正的重建**必須**用當時的 r／q（否則就不是重建那次分析），會走完整校準路徑——本 repo 對該路徑的既有量測是 **7.543 秒**（REPAIR-03／#240，production-scale 三 family 全開、memoization 之後）。再加上從 Neon 讀 30 份 snapshot（TLT 0.48 MiB × 30 ≈ 14 MiB）與反序列化。

`vercel.json` 的 `maxDuration` 是 60 秒、`REFRESH_RUN_BUDGET` 是 45 秒。**把 96 秒以上的純 CPU 重建放進一個開圖表的 GET request 是結構上不可行的**，SPY（12,534 合約、butterfly 是 `C(n,3)`）只會更糟。

> **結論：這幾個數字必須 materialize，不能只存 seed。** 這是 Canonical Principle 明文允許的例外，不是偷懶。**而且這個例外極小**——canonical 最小集合只有四欄，且前端只讀 `cost`。

### 3.5 Deterministic reconstruction 的三個真實限制（spec 階段不得混用語意）

**L-1｜`engine_version` 是標籤，不是時光機。** 舊版引擎的程式碼不在資料庫裡。用今天的 `option_chaser` 重放三個月前的 seed，得到的是**今天的估值語意套在當時的報價上**。

這不是理論風險：T01（#218）建立的數值基準至今已有 **9 次合法重產事件**（T02／T04／T09／T12／T14／T15／REPAIR-09 等），每一次都代表估值或序列化語意改變過。REPAIR-09（#246）把 single-leg 估值日從日曆錨點改成自身到期日，同一個候選的 `baseline_return` 從 `1.1926288317629354` 變成 `0.9569471624266144`——**舊 view 存的是前者，seed 重建會得到後者**。

因此「重建」有兩種語意，**本 spec 全文與後續票務不得混用**：

| 語意 | 需要什麼 | 是否可行 |
|---|---|---|
| **Re-analysis**（用今天的引擎重新評價當時的市場資料） | seed 就夠 | ✅ **可行**，而且這正是有價值的那一種 |
| **Reproduction**（逐位元重現當時使用者看到的畫面） | seed ＋ 當時的引擎行為 | ❌ **不可行** |

> **紅線**：任何宣稱「刪掉 derived 也能重現歷史」的說法都必須指明是哪一種。**Re-analysis 可以，Reproduction 不行。**

> 🛑 **本項已被 RECONCILE-002 §R2 更正**：對 `cost` 而言那個成本是 I/O 不是 CPU。

**L-2｜重建成本結構上放不進 read path** ⇒ L2 例外（§3.4）。

**L-3｜Seed 本身不可重建。** Cboe 端點只回「當下」全鏈、無歷史查詢參數；免 credential 的歷史 chain 路線已在 #111 第二輪窮舉確認**不存在**（Yahoo／Nasdaq／Cboe 三家皆不可）。**OD-06 因此把 snapshot 定為永久保存**——它一旦刪除，那一刻的市場狀態永遠回不來，而且其他一切「可重建」的宣稱都建立在它之上。

---

## 4. User Stories

### 4.1 儲存生命週期（Storage Lifecycle）

1. 作為 Owner，我希望每按一次刷新只增加 seed ＋ 少量窄事實，而不是十幾 MB 的完整結果，這樣資料庫不會在四十幾次刷新後寫滿。
2. 作為 Owner，我希望原始的選擇權鏈快照永遠不被刪掉，因為 Cboe 沒有歷史端點，那一刻的市場資料刪了就永遠回不來。
3. 作為 Owner，我希望歷史走勢圖上「我在畫面上點得到的每一個候選」都留得住，因為那正是我會回頭去看的東西。
4. 作為 Owner，我希望我不會為了看一條折線，就讓系統從資料庫讀出整個劇本的全部歷史結果。
5. 作為 Owner，我希望對任何一份歷史結果，都能直接查出它當時用的利率、股利與引擎版本，不必去解析一大包 JSON。
6. 作為 Owner，我希望儲存瘦身的每一步都可以退回去，只有最後一步是不可逆的，而且那一步要等我親自點頭。
7. 作為 Owner，我希望在真正停止寫入舊格式之前，系統已經先用真實資料證明過新格式足夠支撐現有畫面。
8. 作為使用者，我希望儲存瘦身之後，我現在看到的分析結果——名次、報酬率、冠軍候選、熱力圖——一個數字都不會變。
9. 作為使用者，我希望歷史走勢圖上某個候選在某次刷新沒有入選時，圖上如實斷開一格，而不是被插值、也不是整張圖壞掉。
10. 作為 Owner，我希望知道資料庫現在有多大、成長多快，而不是等它滿了才發現。

### 4.2 Treasury Lifecycle

11. 作為使用者，我不希望因為我剛好是今天第一個按刷新的人，就得多等 45 秒等系統去抓國債殖利率曲線。
12. 作為 Owner，我希望每個市場日的利率曲線由排程自動更新好，正常情況下使用者的分析只是從資料庫讀出來。
13. 作為使用者，我希望就算排程那天沒跑成功，我的分析仍然能完成——系統會自己去抓，只是我多等一下。
14. 作為使用者，我希望在系統用的是舊日期的曲線時，畫面上明確告訴我曲線的有效日期與它是舊的，而不是假裝那是今天的數字。
15. 作為 Owner，我希望這件事不依賴任何「回應送出後還會繼續跑」的平台承諾，因為官方文件確認 Python runtime 沒有那個機制。

### 4.3 Cboe 429 韌性

16. 作為使用者，當報價來源在限流我時，我希望畫面明確告訴我「資料來源暫時限流」，而不是一句看不出原因的「抓不到報價」。
17. 作為使用者，當報價抓不到時，我希望還能看到我上一次成功的分析結果，並且清楚知道那份資料是什麼時候抓的、它是舊的。
18. 作為使用者，我希望系統在上游叫我等 34 秒的時候真的等，而不是我一按重試它就立刻再打一次、把限流窗口一直續下去。
19. 作為使用者，我希望在限流期間，重試按鈕清楚告訴我還要等多久，而不是讓我一直按。
20. 作為使用者，當同一個資料來源持續失敗很久時，我希望畫面明確顯示這是資料來源異常，而不是讓我以為是自己的劇本設定有問題。
21. 作為 Owner，我希望知道昨天對 Cboe 發了幾次請求、被限流幾次，這樣我才有依據判斷要不要做共用快取。
22. 作為 Owner，我希望這個 backoff 機制只記「上游現在讓不讓我打」，不存任何市場資料，這樣它不會變成偷偷做進來的 chain 共用快取。

### 4.4 Ownership Boundary

23. 作為使用者，我希望我開站時只刷新我自己的劇本，不會去動別人的資料。
24. 作為使用者，我希望我在劇本清單看到的只有我自己的劇本。
25. 作為使用者，我希望我設定的 API token 只有我自己會用到，不會被別人拿去燒掉我的付費額度。
26. 作為使用者，我希望我的診斷紀錄裡不會出現別人查過哪些標的。
27. 作為 Owner，我希望在只有我一個人使用的今天，加上 owner 維度之後，我看到的每一個畫面、每一個數字都跟改動前完全一樣。
28. 作為 Owner，我希望文件與程式碼誠實說明「加了 owner 欄位」不等於「隱私已完成」，真正開放註冊前還需要登入機制。
29. 作為 Owner，我希望市場公開事實（利率曲線、股利、歷史 IV）仍然全站共用，不會因為加了 owner 維度就每個人各抓一份。

### 4.5 Observability

30. 作為 Owner，我希望能回答「昨天對 Cboe 發了幾次請求」。
31. 作為 Owner，我希望能回答「昨天被限流幾次」。
32. 作為 Owner，我希望能回答「有幾次是拿舊資料給使用者看的」。
33. 作為 Owner，我希望能回答「Treasury／Dividend 昨天有幾次冷啟動抓取」。
34. 作為 Owner，我希望能回答「一輪刷新現在要多久」。
35. 作為 Owner，我希望能回答「`results`／`snapshots` 表現在多大、單列多大」。
36. 作為 Owner，我希望能證明「切換讀取路徑之後，看歷史走勢圖的資料庫讀取量真的下降了」。
37. 作為 Owner，我希望這些量測只是加上去的計數，不會改變產品任何行為，而且隨時可以關掉。
38. 作為 Owner，我不希望為了這幾個數字就蓋一整套 observability 平台。

---

## 5. Functional Requirements

### FR-1 Storage — Seed 抽取（Stage 1-0）

- **FR-1.1** `results` 資料表新增獨立欄位，承載目前寄生在 `view` 內部的重建 seed 與 provenance：已解析的 `AnalysisParams`（含 `rate_by_expiry`／`q_by_symbol`／`iv_shifts`／`delta_bands`／`rate_explicit` 與全部 provenance 欄位）、`engine_version`、view 的 `schema_version`、snapshot `source`。
- **FR-1.2** 新增欄位為**純加法**：`view` 內容逐位元不變，既有讀取端零改動。
- **FR-1.3** 既有列必須 backfill（從各自的 `view` 讀出、寫入新欄位）。Backfill 必須**冪等且可續跑**（中斷後重跑不會產生錯誤或重複副作用）。
- **FR-1.4** 讀取端在 backfill 完成前必須容忍新欄位為 `NULL`。
- **FR-1.5** 在 FR-1.1～FR-1.3 全部完成之前，**禁止**移除或停止寫入 `view` 內的任何 historical 內容（RL-16）。

### FR-2 Storage — Narrow visible-candidate history（Stage 1-1～1-5）

- **FR-2.1** 新增 narrow history 表，欄位為 OD-07 明訂的最小集合：`scenario_id`、`analyzed_at`、`candidate_key`、`cost`。**不得把完整 candidate object 塞回去。**
- **FR-2.2** 「visible candidate」的定義（施工時不必重新推導）＝以下三者的聯集，逐 family、逐到期日：
  - 各到期日的 `expiry_top10`（使用者在到期日結構區點得到的前十名）
  - 各到期日的 `expiry_best`
  - 跨 family champion（`representative_candidate`）與 per-family 代表（`per_family`）
- **FR-2.3** 這份 narrow history **永久保存，暫不設 retention**（OD-07）。
- **FR-2.4** **斷點語意必須逐位元保留**：某次刷新該 candidate 不在 visible 集合內時，歷史查詢對那個 `analyzed_at` 必須回傳一筆 `cost = None` 的 entry（**如實呈現斷點，不插值、不跳過、不報錯**）。實作上這意味著讀取路徑必須以該劇本的 `results.analyzed_at` 清單為左側基準做 LEFT JOIN，**不能只回傳 narrow 表裡真的有的列**。
- **FR-2.5** 走勢圖回應中的 `spot` 取自 `results.spot` 既有獨立欄位，不再解析 view。`baseline_return`／`rank_in_expiry` 兩欄在契約中保留但恆為 `None`（前端零讀取端，Wayfinder F1）。
- **FR-2.6** Dual-write 期間，narrow 表與既有 `all_candidates` **同時寫入**，兩邊都在。

### FR-3 Storage — 讀取路徑（Stage 1-3）

- **FR-3.1** `GET /api/scenarios/{id}/results` 改為窄查詢，只取 `analyzed_at`，不再 `SELECT` 含 `view` 的整列。
- **FR-3.2** `GET /api/scenarios/{id}/history` 改讀 narrow history 表（含 FR-2.4 的 LEFT JOIN 語意），不再讀取全部歷史 view。
- **FR-3.3** 切換後兩個端點的回應**逐位元不變**（除 FR-2.5 明列的既有恆 `None` 欄位維持恆 `None`）。
- **FR-3.4** 切換後 Neon 讀取量**必須下降**，latency **不得惡化**（RL-24）。

### FR-4 Treasury Lifecycle

- **FR-4.1** 新增一個**只做刷新、不服務使用者請求**的 cron endpoint，由 Vercel Cron 於每市場日觸發，主動把 shared `rate_cache` 填新。
- **FR-4.2** 該 endpoint 必須驗證 Vercel Cron 的授權標頭（`CRON_SECRET`），未授權請求一律拒絕。
- **FR-4.3** **既有同步 refresh-on-miss 保底路徑不得移除**（RL-17）。Cron 沒跑到或跑失敗時，當天第一個請求仍能自己救回來。
- **FR-4.4** 既有 7 天陳舊備援與 `rate_curve_date`／`rate_curve_stale`／`rate_note` 揭露維持不變。
- **FR-4.5** 不得依賴 Python background continuation（官方確認 NOT_SUPPORTED），不得依賴 Fluid Compute 的 correctness（官方原文是 "can share"，非保證；且本專案開關狀態 NOT_CONFIRMED）。
- **FR-4.6** Cron 可單獨停用；停用後行為退回今天的純 cache-aside，零風險。

### FR-5 Cboe 429 Failure Semantics

- **FR-5.1** Cboe adapter 必須取得並判讀 HTTP status 與 rate-limit 相關標頭，將 **429 與一般抓取失敗區分開**。
- **FR-5.2** 必須讀取並 honor `Retry-After`。
- **FR-5.3** 新增持久化的 **backoff 控制狀態**（見 §8.4）；在 `Retry-After` 標示的期間內，**禁止對該來源立即重打 upstream**——此時直接以「限流中」語意失敗，**不發出 vendor 請求**。
- **FR-5.4** 失敗分層新增一個與既有 `fetch` 區分的 stage，前後端詞彙必須同步（既有 `test_frontend_contract.py` drift guard 涵蓋）。
- **FR-5.5** 前端在限流期間必須抑制重試（重試按鈕停用或顯示尚需等待時間），防止 client retry storm。
- **FR-5.6** 使用者優先看到**上一份成功結果**，並明確標示 stale 與 quote fetched time。
- **FR-5.7** 同一來源連續失敗超過門檻時，明確顯示 **data-source incident**（資料來源異常），與「這個劇本設定有問題」區分開。
- **FR-5.8** `option_chaser/data/cboe.py` 的 docstring 必須補記「此端點會主動限流並回 429」這個事實（今天只寫「無官方文件、無 SLA」）。
- **FR-5.9** **不得因本 spec 直接啟用 cross-request chain cache**（RL-19／RL-20）。

### FR-6 Observability

- **FR-6.1** 提供以下**最小指標集**（封頂，不得擴張）：
  1. chain fetch count
  2. chain 429 count
  3. stale serve count
  4. Treasury／dividend cold miss count
  5. refresh duration
  6. result row size / DB growth（`results`／`snapshots` 表大小、列數、單列 view 大小分布）
  7. narrow-history read volume 或等效證明（用以證明 FR-3.4）
- **FR-6.2** 觀測必須是**純加法**、可關閉，且**不改變 production 任何行為**（RL-25）。
- **FR-6.3** 不得建立大型 observability platform（無 dashboard 框架、無 metrics vendor、無 tracing 系統）。

### FR-7 Ownership Boundary（A-1）

- **FR-7.1** 新增 owner 維度到以下 per-user 資料：`scenarios`、`results`、`snapshots`、`events`、`provider_credentials`、`data_source_settings`、`provider_verifications`、`diagnostics`（**OD-08**）。
- **FR-7.2** 既有資料一律 backfill 成目前的 solo owner。
- **FR-7.3** Storage port 的每個 per-user 查詢帶身分；API 每個端點解析身分。身分解析器為可注入的相依（沿用 `create_app()` 既有 DI 慣例），**預設固定回傳 solo owner id**。
- **FR-7.4** Refresh scope 只包含 owner 自己的 scenarios。
- **FR-7.5** 以下 **system-wide market facts 維持 shared，不得加 owner 維度**（RL-22）：`rate_cache`、`treasury_year_cache`、`dividend_cache`、`contract_iv_history`、`iv_observations`、`iv_backfill_runs`，以及本 spec 新增的 `chain_backoff`（它是「上游對我們的限流狀態」，不是任何使用者的資料）。
- **FR-7.6** **單人模式下所有可見行為必須逐位元一致**（RL-23）。
- **FR-7.7** 文件、commit 訊息、issue、程式碼註解**一律不得**把 A-1 描述成「privacy 已完成」或「多使用者隔離已完成」（RL-21）。正確措辭是「已建立 data boundary，authentication 尚未實作」。

---

## 6. Storage Migration State Machine

**這是一台狀態機，不得跳步。** 每一步都有明確的進入條件、退出條件與 rollback 手段。

```
   ┌─────────┐
   │  S0     │ 今天：view 全保真、all_candidates 全寫、無 seed 欄位
   └────┬────┘
        │  Stage 1-0：拆 seed（純加法 + backfill）
        ▼
   ┌─────────┐
   │  S1     │ seed 欄位已存在且已 backfill；view 仍全保真
   └────┬────┘
        │  Stage 1-1：narrow 表建立 + dual-write
        ▼
   ┌─────────┐
   │  S2     │ 兩種表徵並存，兩邊都在寫
   └────┬────┘
        │  Stage 1-2：parity proof（不改任何寫入或讀取）
        ▼
   ┌─────────┐
   │  S3     │ 已證明 narrow 足以支撐既有 historical UI 與 re-analysis 契約
   └────┬────┘
        │  Stage 1-3：切換 read path
        ▼
   ┌─────────┐
   │  S4     │ /history 與 /results 讀 narrow；舊寫入仍在
   └────┬────┘
        │  Stage 1-4：production validation
        ▼
   ┌─────────┐
   │  S5     │ 已在真實 production 資料上驗證通過
   └────┬────┘
        │  Stage 1-5：停止寫入 obsolete historical derived payload
        ▼
   ┌─────────┐
   │  S6     │ 新結果不再產生 all_candidates；舊列仍在
   └────┬────┘
        │  Stage 1-6：不可逆 cleanup ★需 Owner 對 EG-2 有答案
        ▼
   ┌─────────┐
   │  S7     │ 歷史 derived payload 已清理
   └─────────┘
```

### 6.1 逐步定義

| Stage | 動作 | 進入條件 | 退出條件（＝驗收） | 改 schema | 影響使用者可見行為 | Rollback |
|---|---|---|---|---|---|---|
| **1-0** | **Extract reconstruction seed** — 把 rate inputs／dividend inputs／provenance／source／fetched & effective dates／stale state／`engine_version`／`schema_version` 抽成獨立、持久化欄位 | 無 | 新欄位存在；既有列全部 backfill 完成；`view` 逐位元未變；D9 可用一個查詢回答 | ✅ 純加法 | ❌ 無 | ✅ 停用讀取新欄位即可 |
| **1-1** | **Dual-write** — narrow 表建立，與既有 `all_candidates` 同時寫 | 1-0 完成 | 新刷新同時產生兩種表徵；既有讀取路徑未動 | ✅ 新表 | ❌ 無 | ✅ 停寫新表 |
| **1-2** | **Parity proof** — 對同一批歷史資料，新窄表查詢 vs 既有 `spread_cost_history()`，**逐位元比對** | 1-1 已累積可比對的資料 | 見 §6.2 的 parity 範圍與例外 | ❌ | ❌ 無 | — |
| **1-3** | **Switch read path** — `/history` 讀窄表；`/results` 改窄查詢 | 1-2 通過 | 回應逐位元不變；Neon 讀取量下降；latency 不惡化 | ❌ | ⚠ 僅效能改善，數字不變 | ✅ 切回讀 view |
| **1-4** | **Production validation** | 1-3 部署 | UI 無退化；history 正確；current analysis bitwise／contract behavior 不變；DB read volume 明顯下降；latency 不惡化 | ❌ | ❌ 無 | ✅ 同 1-3 |
| **1-5** | **Stop obsolete writes** — 新結果不再產生 `all_candidates` | 1-4 通過且 production 已穩定運行一段時間 | 新列不含 obsolete payload；讀取端全綠 | ❌ | ❌ 無 | ⚠ **半可逆**——停寫之後的新列沒有舊格式，舊列仍在 |
| **1-6** | **Cleanup（不可逆）** | 1-5 完成 **且** Owner 對 §19-EG-2 有答案 | 見 §6.3 的三條禁令 | ❌ | ⚠ 歷史可見範圍改變 | ❌ **不可逆** |

> 🛑 **本節的「這不是 blocker，是知情事項」已被 RECONCILE-002 §R4／OD-07 升級。**
> 本輪以 repo 自身引擎實測（30 次模擬刷新×4 seeds）：visible-only 窄化下 Butterfly
> 30 點只剩 2–9 點、Vertical 在大幅方向性移動的 seed 20 點只剩 2 點。
> ⇒ **L0 回填路徑（新增 Stage S1-0b）是 OD-07 的必要配套，不是可選項。**
> parity proof 的定義同步擴充：必須額外證明 L0 重算與 `all_candidates` 逐位元相同。

### 6.2 Stage 1-2 Parity proof 的範圍與一項必須誠實揭露的例外

**parity 的定義**：對任一 `(scenario_id, candidate_key)`，新窄表查詢與既有 `spread_cost_history()` 回傳的 `analyzed_at` 序列與 `cost` 序列**逐位元相同**——**條件是**：該 candidate 在該次刷新當時落在 visible 集合（FR-2.2）內。

⚠ **必須寫進 spec、不得靜默吸收的行為差異**：今天 `all_candidates` 收錄的是**全部**有效候選（含當時排在第 15 名的）。改成只 materialize visible top candidates 之後，一個**今天**在前十名、但**過去某次刷新**曾掉出前十名的候選，那一格會從「有值」變成「斷點」。

- 這**在 OD-07 的字面之內**（只 materialize 使用者實際可點到的 candidate）。
- 既有的斷點語意（FR-2.4，`store.spread_cost_history()` docstring 明文「如實呈現斷點，不插值、不跳過、不報錯」）已經**優雅地**處理這件事：圖上自然斷開一格，不會壞掉。
- 但它**確實是歷史圖表的一個可見行為變化**，因此：
  - Stage 1-2 的 parity proof 必須把這類 case **明確分類、計數、報告**，不得混進「不 parity」而被誤判成 bug，也不得混進「parity」而被掩蓋。
  - Stage 1-4 的 production validation 必須用真實資料回報這個比例，供 Owner 知情。
  - **這不是 blocker，是知情事項。**
- 若 Owner 事後想補回那些空格：seed 仍在（OD-06），可用離線 **re-analysis**（非 reproduction，§3.5 L-1）填補。

### 6.3 Stage 1-6 的三條禁令（不可逆步驟的護欄）

即使進到 1-6，以下三項**永遠不得執行**：

1. **raw snapshots 不得刪**（OD-06）。
2. **narrow visible-candidate history 不得刪**（OD-07）。
3. **current result view 不得瘦身**（OD-03）——可清理的只有「歷史的那幾十份」，不是「使用者現在看的這一份」。

---

## 7. Treasury Lifecycle

### 7.1 形狀：Cron 主動填 ＋ 同步 refresh-on-miss 保底

**這不是兩個備選方案，是一個方案的兩半。**

| 元件 | 角色 | 狀態 |
|---|---|---|
| **Vercel Cron → 專屬 refresh endpoint** | **主路徑**——每市場日主動把 shared `rate_cache` 填新，使用者正常不 cold miss | 本 spec 新增 |
| **既有同步 refresh-on-miss** | **保底**——Cron 沒跑到／跑失敗時，當天第一個請求自己救回來 | **既有，不得移除** |
| **既有 7 天 stale fallback ＋ `rate_curve_date`／`rate_curve_stale`／`rate_note` 揭露** | **降級揭露** | **既有，不動** |

### 7.2 平台限制（Deployment constraint，不是設計缺陷）

| 限制 | Hobby | 意義 |
|---|---|---|
| Cron 最小間隔 | **一天一次** | 「後續排程再補」在 Hobby 上是**明天再補**，不是一小時後 |
| Cron 精度 | **±59 分鐘** | 排在 UTC 21:00（＝ET 17:00）時，最晚 21:59 UTC 仍在 Treasury 當日 15:30 ET 發布之後、隔日開盤之前——這個時窗吸收得了抖動 |
| 一天只有一次機會 | — | 那一次若失敗，**當天靠的就是同步保底路徑** |

> **明文結論**：在 Hobby 上，OD-01 的「後續排程再補」實際上是由「當天第一個使用者的同步 refresh-on-miss」完成的，不是由排程。**這不違反 OD-01**（使用者仍拿得到當天資料、stale 有標示），但它正是「保底路徑不可移除」的直接理由。
>
> **Hobby 的一天一次限制應視為 deployment constraint，不得因此破壞 fallback**——不得把它當成「所以要升級 Pro」的架構前置條件（Foundation 每一塊都必須 plan-independent）。

### 7.3 不得依賴的兩件事

- **Python background continuation**：官方文件四份一致確認 `waitUntil`／`after()` 只在 Node.js／Edge runtime，Python SDK 零命中 ⇒ **NOT_SUPPORTED**。fire-and-forget SWR 這條路不存在。
- **Fluid Compute correctness**：官方原文是 "multiple invocations **can** share the same physical instance"——關鍵字是 "can" 不是 "will"；且本專案是否啟用為 **NOT_CONFIRMED**（六種 MCP 查詢路徑對真實 production 專案全數 404／零可見度）。

---

## 8. Cboe 429 Failure Semantics

### 8.1 今天的行為（要被取代的）

```python
# option_chaser/data/cboe.py
except Exception as e:            # ← HTTP 429 走這條
    raise FetchError(...)         # 不看 status、不讀 retry-after、無 backoff
```

後果鏈（逐環已覆核）：`429 → FetchError → 退到 yfinance → ImportError（production 結構上不可達）→ FetchError → 使用者看到 stage:"fetch"「抓不到報價」→ 使用者按重試 → 又 429 → retry storm`。

### 8.2 目標語意（逐條對應 OD-05 第 3～7 條）

| # | 要求 | 落地 |
|---|---|---|
| 1 | **distinguish HTTP 429 from generic fetch failure** | adapter 取得 HTTP status ＋ rate-limit 標頭（沿用 `marketdata.py` 於 DG-01／#144 建立的 `HttpResponse`（status／白名單標頭／body）＋低層 `_http_request()` ＋ body-only `_http_get()` shim 既有 pattern）；抬成一個**專屬例外型別**（沿用 `QuotaExhausted(FetchError)` 於 #130 建立的既有 pattern——**繼承 `FetchError`**，既有降級鏈行為因此完全不變，但在乎的呼叫端分得出「這是限流」與「這次剛好失敗」） |
| 2 | **honor Retry-After** | 讀取 `Retry-After` 標頭；缺席或不可解析時套用一個保守預設值 |
| 3 | **Retry-After 期間禁止立即重打 upstream** | 抓取前先查 backoff 控制狀態（§8.4）；仍在封鎖窗內 ⇒ **直接以限流語意失敗，不發出 vendor 請求** |
| 4 | **防止 client retry storm** | 前端在限流期間抑制重試（按鈕停用／顯示尚需等待時間）；批次刷新遇到封鎖中的 symbol 直接回該 scenario 的限流失敗，不打 vendor |
| 5 | **使用者優先保留上一份成功結果** | 沿用 REPAIR-05／#242 既有的「曾成功過 → 反灰＋顯示上一次成功結果」兩態卡片，加上限流專屬文案 |
| 6 | **明確標示 stale / fetched time** | `view["meta"]["fetched_at"]`／`data_quality.fetched_at` **資料已在契約裡**，缺的是前端呈現 |
| 7 | **長時間不可用時明確顯示 data-source incident** | 連續失敗計數超過門檻 ⇒ 專屬的資料來源異常揭露，與「劇本設定有問題」明確區分 |

### 8.3 失敗分層詞彙

沿用既有 `{stage, message}` 分層機制，新增一個與 `fetch` 區分的 stage 代表限流。前後端詞彙**必須同步**——`api_app/main.py` 的失敗分層、`src/api.ts` 的 `STAGES`、`src/scenarios.ts` 的 `failureLabel` 三處，由既有 `tests/test_frontend_contract.py` 的漂移防線把關（該測試會在只改一邊時紅燈，這是既有機制，不需要發明新的）。

### 8.4 Backoff 控制狀態（Owner 已裁示：持久化進既有 Storage port）

**為什麼需要持久化**：`REFRESH_RUN_GROUP_LIMIT = 1` 讓每個 symbol group 各自是一次獨立的 serverless invocation。行程內記憶體依 Wayfinder §8.1 **不能當 correctness layer**（fluid compute 是 "can share" 不是保證，且本專案開關狀態 NOT_CONFIRMED）。因此跨 invocation 的「現在還不能打」必須落在 Storage。

**新增一張極小的表**，形狀沿用 `rate_cache`／`dividend_cache`／`treasury_year_cache` 既有的三態快取設計，不發明新模式：

| 欄位 | 用途 |
|---|---|
| 鍵：`source`（**2026-09-06 訂正，見下方 🛑；原文為 `(source, symbol)`，已由 SCALE-04 拆票時修正**） | 哪個來源被限流——**provider-global**，不分 symbol |
| `blocked_until` | 封鎖窗結束時間 |
| `retry_after_seconds` | 上游給的原始值（供揭露與診斷） |
| `consecutive_failures` | 供 FR-5.7 的 incident 判定 |
| `observed_at` | 最近一次觀測到限流的時間 |
| `last_success_at` | 最近一次成功抓取的時間（供 incident 判定與揭露） |

> 🛑 **2026-09-06 訂正（OPTION-SCALING-TICKETS-REVISE-006，Owner 裁示）**：
> 原文把鍵設計成 `(source, symbol)`，是照抄既有 `rate_cache`／`dividend_cache`
> 這類「本來就是 per-symbol 資料」的既有慣例，未經證據就套用。Owner 指出
> Cboe 的 429 限流語意**沒有證據顯示是 per-symbol**——若真是 provider-global
> 限流，`(source, symbol)` 這個鍵設計會讓使用者「換一個 symbol 繼續打」就
> 繞過封鎖窗，等於 retry storm 換個馬甲繼續打上游。**在沒有證據證明是
> per-symbol 限流之前，安全預設是 `source` 單獨當鍵（provider-global）**——
> 同一來源被限流時，封鎖窗涵蓋該來源底下的全部 symbol。此訂正已同步進
> SCALE-04 的驗收條件（含一條明確的跨 symbol 防護測試：用 symbol A 觸發
> backoff 後，同一 `source` 底下的 symbol B 在窗口內也必須被擋下）。

**RL-19（紅線）**：這張表**不得儲存任何 chain payload、任何市場報價、任何合約資料**。它存的是「上游現在讓不讓我打」，零市場資料。

> **這條界線為什麼重要**：ADR-0001／OD-05 evidence gate 卡住的是 **chain shared cache**——存的是**市場資料本身**。backoff 控制狀態與它是**不同的東西**。這條區分必須在程式碼註解、schema 註解與 commit 訊息裡明文寫出，避免日後被誤讀成偷渡 C-2。

**歸屬**：`chain_backoff` 是 system-wide shared（見 FR-7.5），不加 owner 維度——上游對本站的限流狀態與哪個使用者觸發無關。

### 8.5 明確不做

- **不因本 spec 直接啟用 cross-request chain cache**（RL-19／RL-20）。
- **不施工 30 秒 shared freshness window**（見 §19-EG-1）。
- backoff 的封鎖窗長度**必須可調**（含調成 0 ＝停用），作為 rollback 手段——circuit breaker 誤開會讓功能在 vendor 其實健康時仍不可用。

---

## 9. Observability

### 9.1 最小指標集（封頂七項，不得擴張）

| # | 指標 | 服務哪個決策 |
|---|---|---|
| 1 | **chain fetch count** | §19-EG-1（chain evidence gate）的唯一證據來源 |
| 2 | **chain 429 count** | FR-5 的效果驗證 ＋ EG-1 |
| 3 | **stale serve count** | FR-5.6 的效果驗證；也回答「使用者多常看到舊資料」 |
| 4 | **Treasury／dividend cold miss count** | FR-4 的效果驗證（Cron 生效後應趨近 0） |
| 5 | **refresh duration** | G5／FR-4 的 latency 驗證 |
| 6 | **result row size / DB growth**（`results`／`snapshots` 表大小、列數、單列 view 大小分布） | G1 的效果驗證；也是「什麼時候會撞牆」的唯一可回答依據 |
| 7 | **narrow-history read volume 或等效證明** | **FR-3.4／RL-24 的驗證**——證明切換讀取路徑之後 DB 讀取量真的下降 |

### 9.2 實作約束

- **純加法、可關閉、零 production 行為改變**（FR-6.2／RL-25）。
- **禁止建立大型 observability platform**（FR-6.3）：無 dashboard 框架、無外部 metrics vendor、無 tracing 系統、無新的長期基礎設施依賴。
- 計數器以「指標名稱 ＋ 市場日」為主鍵累加；#6 的表大小／列大小屬 gauge，查詢時即時算出，不落盤成時間序列。
- #1 的 chain fetch count 需要 per-symbol 粒度才能服務 EG-1（判斷同 symbol 重複率）。⚠ **這與 OD-08 的精神同類**（它會揭露「系統裡有人看過 NVDA」）：因此這些計數**僅供 operator 查詢，不得暴露給一般使用者**，並且在 A-2（authentication）落地時必須與 `diagnostics` 一起重新檢視。這一點列入 §19-EG-3。

---

## 10. Ownership Boundary

### 10.1 本 spec 只施工 A-1

| 階段 | 內容 | 本 spec |
|---|---|---|
| **A-1 Ownership / data boundary** | owner 維度 ＋ 既有資料 backfill 成 solo owner ＋ user-scoped 查詢 ＋ refresh scope 收斂 ＋ diagnostics owner-scoped ＋ provider credentials／settings／verifications owner-scoped | ✅ **施工** |
| **A-2 Authentication / identity binding** | 真正的登入／憑證／session／帳號生命週期 | ❌ **不施工**（但**是真正 multi-user 上線前的必要前置**） |

### 10.2 A-1 是 data-boundary correctness，**不等於 privacy 已完成**

> **明文紅線（RL-21）**：
>
> **A-1 建立的是 data boundary，不是 privacy。**
> 一個固定回傳 solo owner 的身分解析器，沒有任何機制阻止第三方冒充那個 owner——它讓資料**有主**，但沒有讓資料**受保護**。
> **`owner_id` 欄位存在 ≠ privacy 已完成。**
> **真正開放多使用者之前，A-2（authentication／identity binding）是不可跳過的，不是可選的產品加分項。**
>
> 文件、commit 訊息、issue、程式碼註解一律不得寫成「已完成多使用者隔離／privacy」。正確措辭是「已建立 data boundary，authentication 尚未實作」。

### 10.3 資料歸屬（逐表）

```
必須 user-scoped（加 owner 維度）
  ├── scenarios
  ├── results
  ├── snapshots
  ├── events
  ├── provider_credentials      ← 今天是全站一把 token（成本 + 未來 privacy）
  ├── data_source_settings      ← 今天是全站一份
  ├── provider_verifications    ← 跟著 credential 走
  └── diagnostics               ← ★OD-08：user-scoped operational data

必須維持 system-wide shared（公開市場事實／上游狀態，加 owner 會破壞共用）
  ├── rate_cache
  ├── treasury_year_cache
  ├── dividend_cache
  ├── contract_iv_history
  ├── iv_observations / iv_backfill_runs
  └── chain_backoff             ← ★本 spec 新增；是「上游對本站的限流狀態」
```

**OD-08 的具體要求**：diagnostics 必須能依 owner 隔離；**不允許不同 user 從 diagnostics 看見彼此的 symbol / scenario activity**。

### 10.4 單人模式的驗收判準

**單人模式下所有可見行為必須保持一致**（RL-23）——身分解析器固定回傳 solo owner，所有查詢結果、所有畫面、所有數字與改動前**逐位元相同**。這是 A-1 這個階段唯一的驗收判準。

### 10.5 明確不做

- ❌ enterprise RBAC、org／team、角色權限矩陣
- ❌ 多租戶資料庫分片
- ❌ 因為「未來可能多租戶」而預留的抽象層

> 需要的是**一個 owner 欄位 ＋ 一條身分解析縫**，不是一套權限系統。

---

## 11. Backward Compatibility

| # | 相容性要求 |
|---|---|
| BC-1 | **既有已儲存的 `view` 不做資料遷移**（沿用 T09／#191 既有裁示）。schema 升版時，讀取端保留舊格式分支。 |
| BC-2 | Stage 1-0 的新 seed 欄位在 backfill 完成前可能為 `NULL`，讀取端必須容忍。 |
| BC-3 | Stage 1-1～1-4 期間，narrow 表沒有對應列的歷史結果，讀取端必須能退回讀 `view`（否則切換讀取路徑會讓 dual-write 之前的歷史整段消失）。 |
| BC-4 | 沒有 `results.spot` 值的極舊列（該欄位是後來才加的），走勢圖回應的 `spot` 允許為 `None`，不得因此拋錯。 |
| BC-5 | 新增的失敗 stage 是**加法**——既有 `fetch`／`analyze`／`params`／`archived` 四個 stage 的語意與文案不變。 |
| BC-6 | owner 欄位先加成 nullable ＋ backfill ＋ 再設 NOT NULL，三步可分開部署。 |
| BC-7 | Cron endpoint 是新端點；既有全部端點的路徑、請求與回應契約不變。 |
| BC-8 | `chain_backoff` 表不存在或讀寫失敗時，行為必須退回「視同沒有 backoff 狀態」（比照三個既有快取層的既有哲學：快取層自己壞掉不影響主流程）。 |

---

## 12. Rollout / Rollback

### 12.1 部署順序建議（各 stage 彼此獨立，可平行，但 Stage 1 內部不得跳步）

```
可平行開工（互不依賴）：
  Stage 0（Observability）   ← 建議最先，因為它是後面幾個 stage 的驗證工具
  Stage 1-0（拆 seed）        ← Stage 1 的不可跳過前置
  Stage 2（Cboe 429）
  Stage 3（Ownership A-1）
  Stage 4（Treasury Cron）

Stage 1 內部嚴格順序：1-0 → 1-1 → 1-2 → 1-3 → 1-4 → 1-5 → 1-6
```

### 12.2 Rollback 手段（逐項）

| 項目 | Rollback |
|---|---|
| Stage 0 觀測 | 純加法，可關閉；關閉後零殘留影響 |
| Stage 1-0 | 停止讀取新欄位；欄位本身留著無害 |
| Stage 1-1 | 停寫 narrow 表 |
| Stage 1-3 | 切回讀 `view` |
| Stage 1-5 | ⚠ **半可逆**——停寫之後的新列沒有舊格式；舊列仍在。回退方式是恢復寫入，但那段期間的新列需靠 seed re-analysis 補（§3.5 L-1，注意是 re-analysis 不是 reproduction） |
| Stage 1-6 | ❌ **不可逆**——這正是它必須排在最後、且需要 Owner 對 EG-2 有答案的理由 |
| Stage 2 | backoff 封鎖窗長度可調到 0 ＝停用；429 判讀退回既有無差別 `FetchError` |
| Stage 3 | 身分解析器可切回「不過濾」；owner 欄位留著無害（因為全部是同一個 solo owner） |
| Stage 4 | Cron 可單獨停用，行為退回今天的純 cache-aside |

### 12.3 部署期的雙寫／雙讀窗

- Stage 1-1～1-4 是明確的**共存窗**，兩種表徵都在、讀取端可切換。這段期間**故意**多花一點儲存，換取隨時可退。
- Stage 1-5 之前**不得**移除 `all_candidates`——`store.spread_cost_history()` 今天**真的**在讀它（RL-12）。

---

## 13. Testing Strategy

### 13.1 測試接縫（Owner 已裁示：**沿用既有七個、零新增**）

| # | 接縫 | 本 spec 用它驗什麼 |
|---|---|---|
| **1** | **HTTP API**（`TestClient` 直測，儲存層記憶體假體／真實 Postgres 雙後端） | `/history`／`/results` 回應逐位元不變；cron endpoint 授權與行為；429 失敗分層；owner scope 過濾；refresh scope 收斂 |
| **2** | **引擎純函式** | visible-candidate 集合的推導；斷點語意；backoff 判定純函式；seed 抽取的純轉換 |
| **3** | **Storage port 契約**（memory ＋ 真實 Postgres 雙跑） | 新 seed 欄位／narrow history 表／`chain_backoff` 表的 round-trip；owner 隔離；backfill 冪等性 |
| **4** | **契約樣本 drift**（`contracts/*.json`） | current detail payload 語意不變；schema 升版時的純加法驗證 |
| **5** | **selection identity ＋ numeric guard**（`tests/test_selection_regression.py` ＋ `tests/fixtures/valuation_numeric_baseline.json`） | **RL-01～RL-04、RL-27 的主要執行機制**——candidate identity、ranking、return、champion、heatmap 逐位元凍結 |
| **6** | **CLI golden fixtures**（五份 `tests/fixtures/golden_*.txt`） | 引擎輸出 byte-locked |
| **7** | **前端 Vitest ＋ Playwright**（iPhone ＋ Desktop 兩個 project） | 走勢圖斷點呈現；429 文案與重試抑制；stale／fetched time 揭露；卡片兩態；單人模式畫面不變 |

**零新增接縫。** 唯一新增的是 `create_app()` 的一個 **identity resolver 注入參數**——沿用既有 `fetch=`／`rate_loader=`／`dividend_loader=`／`refresh_run_budget=`／`analysis_deadline_seconds=` 同一套 DI 慣例，是既有注入模式的延伸，**不是新的測試接縫**。

同理，Stage 1-2 的 **parity proof 是新測試、不是新接縫**——它跑在接縫 2（引擎純函式）與接縫 3（Storage port 契約）之上。

### 13.2 什麼算好測試

- **只測外部行為，不測實作細節。** 例如驗「切換讀取路徑後 `/history` 的回應逐位元相同」，而不是驗「內部呼叫了哪個函式」。
- **決定性**：不打真網路、不讀系統時鐘。既有 pattern：`run_offline`／`snapshot_today(snap.fetched_at)`／注入固定假曲線與假 dividend loader／`FROZEN_TODAY` autouse fixture（#236 hermetic repair 建立的既有慣例）。
- **先證明測試抓得住 bug**：本專案既有慣例是把舊 bug 臨時放回去、確認新測試會紅（T01 的紅燈實測、PERF-04 的 125 vs 1、REPAIR-04 的還原舊邏輯驗證）。本 spec 的每一條新增守門測試都應照做。
- **不得為了讓測試綠燈而放寬任何既有斷言**（RL-27）。

### 13.3 本 spec 特別要求的測試

| # | 測試 | 接縫 |
|---|---|---|
| T-1 | **Parity proof**：新窄表查詢 vs 既有 `spread_cost_history()`，逐位元比對 `analyzed_at`／`cost` 序列；§6.2 的「曾掉出 visible 集合」case 必須被**分類計數**而非混入 pass／fail | 2 ＋ 3 |
| T-2 | **斷點語意**：candidate 在某次刷新不在 visible 集合時，回應必須有那一筆且 `cost is None`（LEFT JOIN 語意，FR-2.4） | 1 ＋ 2 |
| T-3 | **Seed 完整性**：對任一份結果，可從獨立欄位讀出當時的 `params`（含 r／q）、provenance、`engine_version`，不解析 `view`（D9） | 1 ＋ 3 |
| T-4 | **Backfill 冪等**：重跑 backfill 不產生錯誤或重複副作用 | 3 |
| T-5 | **429 辨識**：注入回 429 ＋ `Retry-After` 的假 http 層，驗證抬成專屬例外、帶正確秒數，且**繼承 `FetchError`**（既有降級鏈行為不變） | 2 |
| T-6 | **封鎖窗內不打 vendor**：backoff 生效時注入一個「被呼叫就 assert 失敗」的假 http 層，證明零 vendor 請求（沿用 #126 既有守門手法） | 1 ＋ 2 |
| T-7 | **`chain_backoff` 零 payload**：結構性測試，證明該表／該 dataclass 不含任何市場資料欄位（RL-19） | 3 |
| T-8 | **失敗分層詞彙不漂移**：新 stage 必須同時被後端、`src/api.ts` 的 `STAGES`、`src/scenarios.ts` 的 `failureLabel` 認得（既有 `test_frontend_contract.py`） | 既有 |
| T-9 | **Cron endpoint 授權**：未帶正確 `CRON_SECRET` 的請求被拒絕 | 1 |
| T-10 | **同步 refresh-on-miss 未被移除**：Cron 未跑過的情況下，第一個請求仍能自己抓到曲線（RL-17） | 1 |
| T-11 | **Owner 隔離**：兩個 owner 的資料互不可見；refresh scope 只含自己的 scenarios | 1 ＋ 3 |
| T-12 | **單人模式逐位元一致**：加上 owner 維度前後，同一組輸入的全部端點回應逐位元相同（RL-23） | 1 ＋ 4 |
| T-13 | **Shared caches 未被 owner 化**：結構性測試，證明六張 system-wide 表 ＋ `chain_backoff` 沒有 owner 欄位（RL-22） | 3 |
| T-14 | **Diagnostics owner-scoped**：一個 owner 讀不到另一個 owner 的診斷事件（OD-08） | 1 ＋ 3 |
| T-15 | **觀測零行為改變**：觀測開啟與關閉時，全部端點回應逐位元相同（RL-25） | 1 ＋ 4 |
| T-16 | **前端**：走勢圖斷點如實斷開；限流文案與重試抑制；stale ＋ fetched time 揭露；卡片兩態；incident 揭露 | 7 |

---

## 14. Regression Red Lines

**共 34 條（RL-01～RL-27 原文，RL-28～RL-32 由 RECONCILE-002 新增，RL-33～RL-34 由 STORAGE-AUDIT-003 新增，見第 0.5 部 A4）。**
**任一條被違反即為施工失敗，不得以「storage 省得多」為由交換。**

### 14.1 產品行為保存（RL-01～RL-08）

| # | 紅線 | 守門 |
|---|---|---|
| **RL-01** | **candidate identity** 不變（current analysis） | 接縫 5（identity guard） |
| **RL-02** | **ranking** 順序不變 | 接縫 5 ＋ 6 |
| **RL-03** | **return** 數值逐位元不變（`baseline_return` 及全部衍生報酬欄位） | 接縫 5（numeric guard） |
| **RL-04** | **champion**（跨 family 冠軍與 per-family 代表）的身份與數值不變 | 接縫 5 |
| **RL-05** | **heatmap**（matrix cells／`axis_sets`／comparator／crossover 邊界）不變 | 接縫 5 ＋ 4 |
| **RL-06** | **family behavior**（eligibility verdict／family tab／subtype 展開）不變 | 接縫 1 ＋ 7 |
| **RL-07** | **scenario card behavior**（`best_return`／representative／排序／燈號／失敗兩態）不變 | 接縫 1 ＋ 7 |
| **RL-08** | **current detail payload semantics** 不變（`project_for_detail()` 的輸出契約） | 接縫 4 |

### 14.2 既有守門不得弱化（RL-09～RL-11）

| # | 紅線 |
|---|---|
| **RL-09** | 五份 CLI golden fixtures 維持 byte-locked（除非有明文記錄的合法重產事件） |
| **RL-10** | 契約樣本 drift 測試通過；schema 升版只允許純加法 |
| **RL-11** | `/history` 對 visible candidate 的既有斷點語意（缺席即 `None`、不插值、不跳過、不報錯）不變 |

### 14.3 Storage migration safety（RL-12～RL-16）

| # | 紅線 |
|---|---|
| **RL-12** | `all_candidates` 在 Stage 1-5 之前**不得停止寫入**；在 Stage 1-6 之前**不得刪除**（它今天真的被 `spread_cost_history()` 依賴） |
| **RL-13** | **raw snapshots 永不刪除**（OD-06） |
| **RL-14** | **narrow visible-candidate history 永不刪除**（OD-07） |
| **RL-15** | **current result view 不得瘦身**（OD-03） |
| **RL-16** | **Stage 1-0 未完成前，不得移除或停止寫入任何 historical view 內容**（重建所需的 seed 今天寄生在 view 裡，先砍後拆是不可逆的錯誤） |

### 14.4 Treasury（RL-17～RL-18）

| # | 紅線 |
|---|---|
| **RL-17** | **既有同步 refresh-on-miss 保底路徑不得移除**（OD-01） |
| **RL-18** | 不得依賴 Python background continuation，不得依賴 Fluid Compute correctness |

### 14.5 Chain（RL-19～RL-20）

| # | 紅線 |
|---|---|
| **RL-19** | `chain_backoff` 表**不得儲存任何 chain payload／市場報價／合約資料**——它只存「上游現在讓不讓我打」 |
| **RL-20** | **不得在本 spec 施工 30 秒 shared freshness window 或任何 cross-request chain cache**（ADR-0001 evidence gate，見 §19-EG-1） |

### 14.6 Ownership（RL-21～RL-23）

| # | 紅線 |
|---|---|
| **RL-21** | **A-1 不得被描述成 privacy 完成**（文件／commit／issue／註解一律適用） |
| **RL-22** | **system-wide market-fact caches 不得加 owner 維度**（`rate_cache`／`treasury_year_cache`／`dividend_cache`／`contract_iv_history`／`iv_observations`／`iv_backfill_runs`／`chain_backoff`） |
| **RL-23** | **單人模式下所有可見行為必須逐位元一致** |

### 14.7 效能與觀測（RL-24～RL-25）

| # | 紅線 |
|---|---|
| **RL-24** | 切換讀取路徑後，`/history`／`/results` 的 Neon 讀取量**必須下降、不得上升**；latency **不得惡化**。若上升就是做錯了 |
| **RL-25** | 觀測必須是純加法、可關閉，**不得改變 production 任何行為** |

### 14.8 範圍紀律（RL-26～RL-27）

| # | 紅線 |
|---|---|
| **RL-26** | **diagnostics 必須隨 A-1 一併 owner-scoped**（OD-08）——不得以「它只是營運資料」為由跳過 |
| **RL-27** | **不得夾帶 unrelated cleanup、stylistic 改動，或為了讓測試綠燈而放寬任何既有斷言** |


### 14.9 RECONCILE-002 新增（RL-28～RL-32）

| # | 紅線 |
|---|---|
| **RL-28** | refresh-run 對共用同一 symbol 的 K 個劇本寫入 K 份逐位元相同的 snapshot——這是**去重的機會，不是刪除的理由**。零刪除的節省應優先於任何刪除 |
| **RL-29** | 任何「退役歷史 snapshots」的敘述**必須指明是哪一個 store**：Postgres `snapshots` 表，或 `option_chaser/cli.py` 重播的本機檔案 `snapshots/{symbol}_{fetched_at}.json`。兩者是不同的東西，不指明則該敘述字面上為偽 |
| **RL-30** | **不得以 exact-contract vendor 路徑（Historical IV）作為任何退役的理由**——它預設 403、結構上排除 Butterfly、且產生的是不同的序列（§R1 三條反證） |
| **RL-31** | 退役實作**不得把 `results.view` 設為 NULL 或 `{}`**：`spread_cost_history()` 硬下標 `view["results"]`／`view["analyzed_at"]`／`view["meta"]["spot"]`，且 `ResultRecord.view` 型別非可選、以位置參數建構。必須保留成形的 stub 或改寫該函式 |
| **RL-32** | **「每次刷新都永久留下完整分析世界」不再是 canonical requirement**（Owner RECONCILE-002 明文）。任何設計不得再以「以前已經存了」推導出永久保存需求 |

---

## 15. Data Migration Safety

| # | 安全要求 |
|---|---|
| **DM-1** | 每一次 schema 變更都是**純加法**（新欄位 nullable／新表），沿用本專案既有「建表與遷移分兩批送」慣例（V3／#51 的 implicit transaction 教訓：建表與遷移同批送，冷啟動撞 `DuplicateTable` 時遷移會跟著 rollback 但仍標記 ready）。 |
| **DM-2** | 所有 backfill **冪等且可續跑**；中斷後重跑不產生錯誤或重複副作用。 |
| **DM-3** | Backfill 期間讀取端必須容忍新欄位為 `NULL`（BC-2／BC-3）。 |
| **DM-4** | **不可逆操作只有一個地方**：Stage 1-6。除它之外，本 spec 的任何一步都不刪除任何既有資料。 |
| **DM-5** | Stage 1-6 執行前，必須先在真實 production 資料上跑過 Stage 1-2 parity proof 與 Stage 1-4 validation，並且 Owner 對 §19-EG-2 有明確答案。 |
| **DM-6** | 三條永久禁令（§6.3）：raw snapshots 不刪、narrow history 不刪、current view 不瘦身。 |
| **DM-7** | owner 欄位採「先 nullable → backfill → 再設 NOT NULL」三步，可分開部署（BC-6）。 |
| **DM-8** | 本 spec **不做** object storage 遷移——OD-06 明文「Foundation 階段先維持現有 storage location，不新增 object-storage dependency」。 |
| **DM-9** | 任何 migration 若在 production 上失敗，必須能在不遺失資料的前提下停在原地（純加法保證這件事成立）。 |

---

## 16. Explicit Out of Scope

以下項目**明確不在本 spec 範圍**，施工時不得順手加入：

- Cross-Scenario（跨劇本比較）
- Position / Holdings
- Credit strategies（bull-put／bear-call／iron-fly）
- Iron Condor
- **Chain shared cache implementation**（含 30 秒 shared freshness window 的任何實作）
- Redis / KV
- Object storage migration
- Full authentication UI / product（A-2）
- Billing
- Multi-region
- Microservices
- Arbitrary N-leg work
- Dividend provider migration（Yahoo 替換——那是合規／治理決策，需要自己的 vendor 研究，另開獨立線）
- Unrelated cleanup（含 stylistic 改動）

**額外不做（由上游研究／地圖推導，一併封板）**：

- 全 universe dividend preload（universe 不封閉，`symbol` 只受 `^[A-Za-z.\-]{1,10}$` 約束）
- Treasury／dividend single-flight（OD-01 之後 stampede 觸發條件從「每個市場日必然」降為「只有排程失敗那天」，收益極小）
- Postgres advisory lock／distributed lock
- Hot-symbol cron warming（需要 Pro，且是延遲優化不是容量修復）
- Market Data App 自訂 chain 成本揭露（產品揭露問題，非 scaling，另開獨立線）
- Dividend `q=0` 降級的語意裁決（那是 valuation 語意問題，不是 scaling 問題）
- 修正「60 秒硬性上限」與 ADR-0001「無共享記憶體」這兩處過時記載**以外**的任何文件整理

> ⚠ 上一行的例外說明：Wayfinder §10.3 把「順手更正 7 處過時的『60 秒硬上限』與 ADR-0001『無共享記憶體』」列為 NOW。本 spec 保留這一項，因為不更正會讓後續設計沿用錯誤前提。正確措辭見 §20-N4。

---

## 17. Acceptance Criteria

### 17.1 Storage

- **AC-1** 可以用一個查詢回答：對任一份歷史結果，當時的 `params`（含 `rate_by_expiry`／`q_by_symbol`）、provenance（曲線日期／stale 狀態／q 來源）與 `engine_version` 各是什麼——**不必解析 `view` JSONB**。
- **AC-2** Stage 1-2 的 parity proof 通過：新窄表查詢與既有 `spread_cost_history()` 對同一批歷史資料逐位元相同（§6.2 定義的範圍內），且「曾掉出 visible 集合」的 case 被**分類計數並報告**。
- **AC-3** Stage 1-3 之後，`/history` 與 `/results` 的回應逐位元不變。
- **AC-4** Stage 1-4 之後，在真實 production 資料上確認：UI 無退化、history 正確、current analysis bitwise／contract behavior 不變、**DB read volume 明顯下降**、latency 不惡化。
- **AC-5** Stage 1-5 之後，新產生的結果不再包含 obsolete historical derived payload，且全部讀取端仍然全綠。
- **AC-6** 每次刷新的永久儲存成長 ＝ snapshot ＋ 常數量級窄事實 ＋ L0/L1 欄位（可用指標 #6 直接量到）。
- **AC-7** Stage 1-6 在 §19-EG-2 有答案之前**未被執行**。

### 17.2 Treasury

- **AC-8** Cron endpoint 存在、需要授權、每市場日觸發、成功後 shared `rate_cache` 為當日值。
- **AC-9** 正常使用者的分析路徑命中 DB，不承擔 cold fetch（可用指標 #4 驗證 cold miss 趨近 0）。
- **AC-10** 刻意讓 Cron 不執行時，當天第一個請求仍能自己抓到曲線並完成分析（同步保底未被移除）。
- **AC-11** 使用上一個有效市場日資料時，畫面明確標示 stale 與 effective date。
- **AC-12** 全程不依賴 Python background continuation 或 Fluid Compute correctness（結構性測試：相關模組不 import 任何背景執行 API）。

### 17.3 Cboe 429

- **AC-13** 429 與一般抓取失敗在後端與畫面上**可區分**。
- **AC-14** `Retry-After` 被讀取並被遵守；封鎖窗內**零 vendor 請求**（可用「被呼叫就 assert 失敗」的假體證明）。
- **AC-15** 限流期間前端抑制重試（按鈕停用或顯示尚需等待時間）。
- **AC-16** 使用者看得到上一份成功結果 ＋ stale 標示 ＋ quote fetched time。
- **AC-17** 連續失敗超過門檻時，畫面顯示 data-source incident，與劇本設定問題明確區分。
- **AC-18** `chain_backoff` 表**不含任何市場資料欄位**（結構性測試）。
- **AC-19** 本 spec 未啟用任何 cross-request chain cache（結構性測試 ＋ 逐字檢查）。

### 17.4 Observability

- **AC-20** 七項指標各自可以用一個查詢或一個端點回答。
- **AC-21** 觀測開啟與關閉時，全部端點回應逐位元相同。
- **AC-22** 未引入任何外部 metrics vendor、dashboard 框架或 tracing 系統。

### 17.5 Ownership

- **AC-23** 兩個不同 owner 的 scenarios／results／snapshots／events／credentials／settings／verifications／diagnostics 互不可見。
- **AC-24** 一輪刷新只涵蓋 owner 自己的 scenarios。
- **AC-25** 七張 system-wide 表（六張市場事實 ＋ `chain_backoff`）**沒有** owner 欄位（結構性測試）。
- **AC-26** **單人模式下所有端點回應與改動前逐位元相同。**
- **AC-27** 全 repo 掃描：不存在把 A-1 描述為 privacy／多使用者隔離已完成的措辭。

### 17.6 全域

- **AC-28** 27 條 Regression Red Lines 逐條對照，全數未被違反。
- **AC-29** 全套測試綠燈（後端 pytest 記憶體 ＋ 真實 Postgres 雙後端；前端 typecheck／Vitest／build；Playwright iPhone ＋ Desktop），且**沒有任何既有斷言被放寬或移除**以達成綠燈。
- **AC-30** §16 Out of Scope 清單逐項掃描，零違反。
- **AC-31** Owner 真機驗收（本項無法由 agent 完成，需 Owner 親自執行）。

---

## 18. Implementation Stages

> 🛑 **RECONCILE-002 對本節的兩處修改（以 §R6 為準）**：
> 1. **新增 S1-0b「L0 回填路徑」**，排在 S1-0 之後、S1-1 之前——純函式
>    `cost_from_snapshot(snapshot, candidate_key)`（`natural_cost` ∘ `find_contract`，零 vendor、
>    零 credential、任何腿數）＋一條回填入口。它是 OD-07 窄化的安全網，**不是可選項**。
> 2. **S1-6 的範圍擴大**：原本只清「歷史 view 完整內容」的一部分，現在確認**整份歷史 view
>    可退役**（narrow 熱快取 ＋ L0 冷來源已覆蓋其唯一消費端）；三條永久禁令（§6.3）不變。


> 拆票時以此為骨架。**Stage 內部順序是硬性的；Stage 之間可平行。**

| Stage | 名稱 | 前置依賴 | 改 schema | 影響可見行為 | 分級 |
|---|---|---|---|---|---|
| **S0** | **Minimal Observability** | 無 | 可能（輕量計數表） | ❌ 無 | **NOW**（建議最先——它是後面幾個 stage 的驗證工具，也是 EG-1 的唯一證據來源） |
| **S1-0** | **Extract reconstruction seed** | 無 | ✅ 純加法 ＋ backfill | ❌ 無 | **NOW**（Stage 1 的不可跳過前置） |
| **S1-1** | **Narrow history 表 ＋ dual-write** | S1-0 | ✅ 新表 | ❌ 無 | **NOW** |
| **S1-2** | **Parity proof** | S1-1 | ❌ | ❌ 無 | **NOW** |
| **S1-3** | **Switch read path**（`/history` ＋ `/results`，順帶解掉「讀 365 MiB 只為拿時間戳」） | S1-2 | ❌ | ⚠ 僅效能 | **NOW** |
| **S1-4** | **Production validation** | S1-3 已部署 | ❌ | ❌ 無 | **NOW** |
| **S1-5** | **Stop obsolete writes** | S1-4 且 production 穩定 | ❌ | ❌ 無 | **NOW** |
| **S1-6** | **Cleanup（不可逆）** | S1-5 **＋ Owner 對 EG-2 有答案** | ❌ | ⚠ 歷史可見範圍改變 | **BLOCKED_ON_OWNER** |
| **S2** | **Cboe 429 韌性 ＋ 資料時間揭露** | 無 | ✅ `chain_backoff` 小表 | ✅ **是**（這正是要做的事） | **NOW** |
| **S3** | **Ownership boundary（A-1）** | 無 | ✅ owner 維度 ＋ backfill | ❌ 單人模式下應為零 | **NOW** |
| **S4** | **Treasury 排程** | 無 | ❌ | ✅ 正常不再 cold fetch | **NOW** |
| **S5** | **〔決策閘門〕chain 跨 request 共用要不要做** | S0 的量測 | — | — | **GATE**（見 §19-EG-1） |
| **S6** | **Chain 30 秒共用窗** | S5 判定 NEEDED ＋ S0 ＋ S3 | 視選型 | ✅ | **條件式，不在本 spec** |
| **S7** | **Authentication（A-2）** | S3 | ✅ | ✅ | **不在本 spec** |

### 18.1 三條硬前置（Wayfinder §14.3，不得遺漏）

1. **S1-0（拆 seed）必須排在任何 storage 瘦身之前。**
2. **S1-6（不可逆 cleanup）在 §19-EG-2 有答案之前不得執行。**
3. **S4 不得移除同步 refresh-on-miss 保底路徑。**

---

## 19. Remaining Evidence Gates

### EG-1｜Chain 跨 request 共用（30 秒 shared freshness window）

**狀態**：**參數已定，機制未定。** OD-05 給的是產品參數（30 秒、手動 Refresh 也不繞過），**不是施工授權**——它明文保留 ADR-0001 的 evidence gate。

**ADR-0001 自己訂的重開條件**：不要重新提案，除非「流量形狀本身改變，**且有同時計入新增往返成本的量測**」。

**gate 的輸入**：Stage 0 的量測（chain fetch count／429 count／同 symbol 重複率）＋ 一份**同時計入新增 Neon 往返成本**的比較。

**已經不必再問 Owner 的**：窗長（30 秒，OD-05 已定）、手動 Refresh 是否繞過（不繞過，OD-05 已定）。

**gate 的輸出**：`C-2: NEEDED`（附數字依據）或 `C-2: NOT_NEEDED / DEFERRED`。

**gate 時應一併評估、ADR-0001 從未評估過的第三選項**：Vercel Edge CDN（`s-maxage` ＋ `stale-while-revalidate`）——它在**平台層**共用，零 Neon 往返、零額外寫入，正好繞開 ADR 最強的反對理由（「miss 路徑純增加成本」）。⚠ 但它會改變 API 形狀（POST `refresh-run` 天生不可快取），且沒有量測。

**本 spec 保留但不施工**：freshness contract（30 秒）／future acceptance semantics（若施工，只涵蓋預設來源 Cboe、鍵含 `(symbol, source)`、必須同時顯示 quote fetched time）／Stage 5 evidence gate／Stage 6 conditional implementation。

> **RL-20 明文禁止把它偷偷做進 NOW scope。**

**已知的一項施工前必須確認的約束**（不影響本 spec，但 gate 時必須帶入）：`provider_credentials` 全站共用 ＋ chain 共用快取若同時存在，會產生「A 用自己 token 花 credits 抓的資料被 B 用到」的問題。因此共用快取的鍵必須含 source，且**自訂來源（使用者自備 token）抓來的資料不得進共用快取**。A-1 完成 credential per-user 化之後，這條約束的落地方式會更清楚。

> ✅ **本 gate 已由 RECONCILE-002 關閉。** L0（raw snapshot，OD-06 永久保存）是歷史 cost 的
> 完整冷來源，因此「歷史 view 完整內容保留多久」不再需要 Owner 裁示——**答案是可以全退役**。
> 取代它的是 §R8 的 RD-1（narrow 覆蓋率檔位）與 RD-2（IV cache retention）。

### EG-2｜Seed retention 與 narrow history 時間窗（擋住 S1-6，不擋 spec、不擋前五步）

OD-06 與 OD-07 已把方向定死（**raw snapshot 永久保存**、**narrow history 永久保存暫不設 retention**），因此**這一題目前沒有 blocker**。

留在此處的是一個**需要 Owner 在按下不可逆刪除鍵之前確認的具體問題**：

> **S1-6 要清理的「歷史 view 完整內容」，保留多久？**

- 這一項**不是** raw snapshot（OD-06 已定永久），**不是** narrow history（OD-07 已定永久），**不是** current view（OD-03 禁止動）。
- 它是「歷史那幾十份完整 view 的其餘內容」——刪掉之後，該時點的 **reproduction**（逐位元重現當時畫面）不再可能，但 **re-analysis**（用今天的引擎重新評價當時資料）仍然可行，因為 seed 全在。
- **技術後果**：這是本 spec 唯一不可逆的一步。

**同時必須讓 Owner 知情的算術（誠實揭露，不是反對 OD-06）**：OD-06 把 snapshot 定為永久保存之後，成長率降到約 1/25，但 seed 本身仍是每次刷新 **0.48 MiB（TLT）／2.55 MiB（SPY）** 的硬成長。Neon Free 0.5 GB ⇒ TLT 約 **1,000 次**／SPY 約 **200 次**刷新後仍會滿。**這把撞牆時間往後推了一個數量級，沒有消滅它。** 屆時的解法依 OD-06 是「搬到較便宜的 archival／object storage，不是刪除 seed」——那屬於本 spec 明文 Out of Scope，需要另開一線。

### EG-3｜Per-symbol 觀測計數在 A-2 時的處置

Stage 0 的 chain fetch count 需要 per-symbol 粒度才能服務 EG-1，而這與 OD-08 的精神同類（會揭露「系統裡有人看過 NVDA」）。

**本 spec 的處置**：這些計數僅供 operator 查詢、不暴露給一般使用者；在 A-2（authentication）落地時，必須與 `diagnostics` 一起重新檢視。**這不擋本 spec 任何一步**，只是登記在案。

---

## 20. Further Notes

**N1｜本 spec 沿用既有守門機制，不發明新的。** OD-03 的「behavior preservation」在本專案已有現成的執行機制——`tests/test_selection_regression.py`（身份 ＋ 數值雙軸）、五份 CLI golden fixtures、契約樣本 drift 測試、前端 Vitest ＋ Playwright。**這些既有測試就是 OD-03 的執行機制。** 只有在既有 guard 真的不足時才補必要 guard，**不改產品**。

**N2｜本專案既有的兩個 adapter pattern 正好是 Stage 2 需要的。** `option_chaser/data/marketdata.py` 在 DG-01（#144）建立的 `HttpResponse`（status／白名單標頭／body）＋ 低層 `_http_request()` ＋ body-only `_http_get()` shim，是「暴露 HTTP metadata 而不改變回傳值語意」的現成前例；`QuotaExhausted(FetchError)`（#130）是「新增專屬例外但繼承既有型別，讓既有降級鏈行為完全不變」的現成前例。Stage 2 應直接沿用這兩個 pattern，不發明第三種。

**N3｜本專案既有的 DI 慣例正好是 Stage 3 需要的。** `create_app()` 已有 `fetch=`／`storage=`／`rate_loader=`／`dividend_loader=`／`rate_curve_rows=`／`refresh_run_budget=`／`refresh_run_group_limit=`／`analysis_deadline_seconds=` 八個注入點。identity resolver 是第九個，沿用同一套慣例，**不是新的測試接縫**。

**N4｜順手更正兩處過時記載（措辭必須精確）。** 本 repo 有 7 處寫著「60 秒函式硬性上限」（`CONTEXT.md`、`api_app/main.py` 四處、`option_chaser/service.py` 兩處、`docs/adr/0001`）。正確措辭**不是**「上限其實是 300s」，而是：

> 「60 秒是本專案在 `vercel.json` 自設的 `maxDuration`，不是平台硬性上限；平台上限取決於 fluid compute 是否啟用（本專案狀態未確認），非 fluid 為 60s、fluid 為 300s。」

同一次一併更正 ADR-0001 的「跨 invocation 沒有共享記憶體」（改為「可能共享、但不保證，**不得依賴**」）。

**N5｜`REFRESH_RUN_GROUP_LIMIT = 1` 是刻意的產品決策，不是 bug。** 它是 2026-08-26 為了「逐張解鎖」的產品需求加的。本 spec 不改它——但它正是 §8.4 backoff 狀態必須持久化的直接原因（每個 symbol group 各自是一次獨立 invocation）。

**N6｜本 spec 未新增任何量測。** 全部數字引用自三份上游文件或對 production code 的靜態覆核。§3.4 的 96 秒是 `3.21s × 30` 推算的**下界**（3.21s 是 q=0 快路徑實測，真實重建走完整校準路徑，既有量測 7.543s）；「目標態約 0.5 MiB／次」是推估，L2 窄事實的實際列大小未量測，snapshot 壓縮率未實測。

**N7｜Stage 1-4 的 production validation 需要真實部署環境。** 本沙箱連不到正式 Neon／vendor，該步驟的驗證需要在 Vercel preview／production 上執行，可能需要 Owner 協助。拆票時應把這一點寫進該張票的驗收方式，不要在沙箱裡假裝驗證過。

**N8｜`chain_backoff` 的界線必須寫在程式碼裡，不只寫在 spec 裡。** schema 註解、dataclass docstring 與 commit 訊息都要明文寫出「這張表存的是上游限流狀態，零市場資料；它不是 ADR-0001／OD-05 evidence gate 卡住的 chain shared cache」。理由：未來的 session 讀到「一張以 (source, symbol) 為鍵、跟 chain 抓取有關的表」時，很容易誤讀成偷渡的 chain cache。

---

READY_FOR_SCALING_TICKETS
