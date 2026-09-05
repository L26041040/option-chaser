# Wayfinder Map：Scaling Foundation

原始版本對應 **OPTION-SCALING-WAYFINDER-001**（2026-09-03）。

**本版對應 OPTION-SCALING-WAYFINDER-002 — Scaling Foundation
Reconciliation（2026-09-05）。這是同一張地圖的更新，不是新地圖。**

**基準**：`origin/master` HEAD `864dd5c`（Initial V2 已 merge 上線）。

**輸入**：
- `docs/research/market-data-lifecycle-scaling.md`（2026-09-03）
- `docs/research/market-data-current-state-map.md`（2026-09-03）
- `docs/research/runtime-targeted-scaling.md`（2026-09-04）
- 本輪（002）對上述結論所依賴的 production code 逐項覆核。

**本輪性質**：Reconciliation。**只更新地圖**——不改 production code、
不寫 spec、不開票、不做 migration、不開 PR、不碰 Cross-Scenario／
Position。**不因 storage 節省而犧牲既有 performance 或 behavior。**

**Destination**：收斂出 Option Chaser 從今天的單人產品走到可安全支撐
至少 1,000 active users 之前，**最小必要**的 Scaling Foundation——
以及同樣重要的，**哪些看起來該做、其實可以不做**。

**證據標示**：**【研究】**＝三份研究文件已建立的事實（本輪抽查覆核，
有出入會標明）；**【本輪覆核】**＝本輪（002）自己讀 production code
確認或新推導出來的；**【推估】**＝模型推算，非量測；**【OD】**＝
Owner 已裁示、視為定案，不再討論；**【未決】**＝仍需 Owner 裁示。

---

## 0. Owner Decisions（已定案，本地圖全文據此對齊）

這五條是 002 的輸入，**不是本輪的推導結果**。地圖全文若與它們衝突，
一律以它們為準；本輪已逐處修正（衝突清單見 §14）。

| # | 裁示 | 影響的章節 |
|---|---|---|
| **OD-01** | **Treasury**：每日自動排程更新 → 存共享 DB cache → 全體共用。正常分析原則上只讀 DB，不讓第一個使用者承擔 cold fetch。每日更新失敗 → 用上一個有效市場日資料 ＋ 明確標示 stale／effective date ＋ 後續排程再補。**不依賴 Python background `waitUntil`。** | §6、§10 Stage 4 |
| **OD-02** | **Storage 核心原則**：**保存不可確定性重建的事實；不必永久保存可由種子資料＋固定演算法確定性重建的衍生結果。** 但**必須先證明** `seed + version → deterministic reconstruction`，不能因「理論上能重算」就先刪資料。 | §3 全節（本輪主體） |
| **OD-03** | **Storage Migration Safety**：**Performance／behavior preservation > storage savings。** 任何瘦身必經六步：① coexist／dual-write ② parity proof ③ 切換 read path ④ production validation ⑤ 停止舊寫入 ⑥ 不可逆 cleanup／retention 永遠最後。**禁止直接刪除 production 依賴的 payload。** current analysis 的 ranking／candidate identity／return／champion／heatmap／UI behavior **不得因 storage optimization 改變**。 | §3.6、§10 Stage 1 |
| **OD-04** | **Ownership**：先建立 ownership／data boundary；既有 Scenario／Result／Snapshot 預設歸現有 Owner；ownership schema 與 login/auth 可分階段；**但不得再宣稱「只有 owner_id 就已經完成 privacy」**——真正 multi-user 開放前仍需 authentication／identity binding。**Ownership 與 Storage lifecycle 彼此獨立**，不得寫成 retention 擋住 ownership。 | §4、§10 Stage 3／7 |
| **OD-05** | **Chain freshness／429**：shared freshness window **30 秒**；使用者手動 Refresh **也不繞過**此窗；顯示 quote fetched time；429 時優先顯示上一份成功資料＋stale 標示；honor `Retry-After`；`Retry-After` 期間禁止立即重打 vendor；持續失敗時明確顯示資料源異常。**但不因此立即推翻 ADR-0001**——chain 跨 request／shared cache 是否施工，仍走 evidence gate。 | §5、§10 Stage 2／5／6 |

**Runtime 結論（同為定案）**：

- **Fluid Compute**：**不得當 correctness dependency**；即使存在也只能
  視為 optional L1 optimization。
- **Python background continuation**：官方未支援，**不得以
  fire-and-forget SWR 為設計基礎**。

---

## 1. 三句話版本

1. **今天最貴的兩個問題，都不需要任何快取、任何 lock、任何排程就能
   解決**——`results.view` 的 storage lifecycle（U=1 就會撞牆）與
   user ownership boundary（把負載從 O(U²) 變成 O(U)）。這兩件是
   Scaling Foundation 的**主體**。
2. **OD-02 讓 storage 這一塊從「留多少」變成「留什麼」**：本輪證明了
   重建鏈的 seed 幾乎齊備（§3.2），但也證明了**兩個 seed 本身正處於
   被瘦身的候選名單上**（`snapshots`、以及寄生在 view 裡的
   `params`／`engine_version`）——**seed 與 derived 不能同時砍**，
   這是本輪修正的最大一處內部矛盾。
3. **Chain 這條線被 OD-05 一分為二**：使用者可見的 429／stale／
   fetched-time 語意**已經裁示完畢、可以施工**（原本卡在 §9-Q4）；
   而「30 秒共用窗」的跨 request 實作**仍在 evidence gate 後面**——
   參數已定，機制未定。

---

## 2. Current State（引用研究，本輪覆核）

### 2.1 已經做對、本輪不動的

| 項目 | 現況 | 本輪態度 |
|---|---|---|
| Treasury 快取 | Neon 單列、market-day 語意、7 天陳舊備援 | **不動**（OD-01 在它之上加排程，不重做它） |
| Dividend 快取 | Neon per-symbol、market-day、90 天陳舊備援 | **不動** |
| Treasury PIT（歷史）快取 | per-year，過去年份永久，PIT 安全靠鍵設計鎖死 | **不動** |
| Historical IV 快取 | per-contract／per-symbol | **不動** |
| 快取鍵設計 | 全部以「公開市場事實」為鍵（symbol／year／contract／market-day），**沒有一個以 user 為鍵** | **不動，而且這正是後面 user 隔離時的正確方向** |
| Run 內 chain 去重 | ADR-0001，純記憶體 dict | **不動** |
| 資料來源揭露 | `market_day`／`as_of`／`stale`／`rate_note`／`q_note` | **不動，而且它是 OD-01／OD-05 的 stale 標示現成基礎** |

> **這一節的重點是「不要因為本階段叫 Scaling Foundation 就重做已經
> 正確的東西」。** 研究的結論很明確：本專案在慢變資料上的快取設計
> 相當成熟，缺口高度集中。

### 2.2 五個已確認的缺口（研究 P0 分級，逐項覆核）

| # | 缺口 | 覆核結果 |
|---|---|---|
| G1 | `results.view` 單列 12.18 MiB、96.4% 是 `all_candidates`、**零 retention** | ✅ 成立。另見 §3 全節 |
| G2 | 無 user ownership（#59 仍 open）→ 開站刷新全站劇本 → O(U²) | ✅ 成立。`main.py:838-848` 無過濾、`main.py:1065-1067` 直接吃 `list_scenarios()` |
| G3 | Cboe 會 429（實測 `retry-after: 34`），adapter 一律 `except Exception → FetchError`，唯一備援 yfinance production 不可達 | ✅ 成立。`data/cboe.py:96-105` 逐行確認 |
| G4 | `result_history()` 把該劇本**全部**歷史 view 完整讀出，而 `/results` 只要時間戳 | ✅ 成立。`postgres.py:550-556` `SELECT {_RESULT_COLS}`（含 `view`）、`main.py:1127-1133` |
| G5 | 三條線都沒有 single-flight | ✅ 成立。`rate_cache.py:86+` 是裸 read-fetch-write |

### 2.3 覆核發現（F1–F3 為 001 輪，F4–F6 為本輪新增）

**F1｜`all_candidates` 的資訊價值遠低於它的體積——UI 只讀其中一個
欄位。**【001 覆核，本輪重驗成立】

`store._history_entry()` 每筆存 5 個欄位（`candidate_key`／`expiry`／
`cost`／`baseline_return`／`rank_in_expiry`）。前端實際消費路徑：

```
src/SpreadHistory.tsx  → 只畫 cost（第 64、123、158 行）
src/spreadHistory.ts   → 只讀 e.cost 與 e.analyzed_at（第 46、58、86、87 行）
```

`rank_in_expiry` 在整個 `src/` 只出現在 `api.ts:920` 的**型別宣告**，
**沒有任何一處讀取**；`baseline_return` 同樣只在型別與註解裡；
`spot` 也不進圖表。

> **74,011 筆 × 5 欄位，最後只有「一條曲線的 y 值」會被使用者看到。**

**F2｜「歷史斷點」的產品語意已經存在。**【001 覆核】

`store.spread_cost_history()` docstring 明文：某次快照找不到這個
candidate_key 時「該筆仍然入列，但 cost／baseline_return／
rank_in_expiry 皆為 None：**如實呈現斷點，不插值、不跳過、不報錯**」。

> 這是既有、刻意的設計：**只保存一部分候選的歷史，畫面上會自然呈現
> 成斷線，而不是壞掉。**

**F3｜`provider_credentials` 是全站一把 token，且沒有 user 欄位。**
【001 覆核，`postgres.py:176`】隱私（A 的 token 被 B 用）＋成本
（A 的 Market Data credits 被 B 燒掉）＋它會反過來限制 chain 共用的
設計（見 §5.5）。

---

**F4｜`today` 完全由 snapshot 決定，不吃 wall clock——這是
deterministic reconstruction 最重要的一塊拼圖，而且它已經成立。**
【本輪覆核，`option_chaser/service.py:1252`】

```python
today = snapshot_today(snap.fetched_at)
```

`_analyze()` 的第一行就把「今天」釘死在**快照自己的抓取時間**上，
不呼叫 `date.today()`／`ny_today()`。整條分析鏈往下（到期日選取
`_scoped_to_selected_expiries`、期限對齊利率的年期、DTE、估值）用的
都是這個 `today`。

> **後果：同一份 snapshot 在任何一天重放，`today` 都是同一個值。**
> 這消滅了「重放時間點會污染結果」這個最典型的 determinism 殺手，
> 而且它不是本輪要新增的設計——它今天就已經是這樣。

**F5｜重建所需的估值輸入（r／q）已經被解析並回寫進 view——但它們
`寄生`在那個要被瘦身的 payload 裡面。**【本輪覆核】

`service._analyze()` 解出利率與股利之後回寫 request：

```python
base = _resolve_rates(base, snap, today, rate_curve_loader)   # → rate_by_expiry
base = _resolve_q(base, snap, today, dividend_loader)         # → q_by_symbol
request = dataclasses.replace(request, base_params=base)      # service.py:1264
```

而 `store.serialize_result()` 把**解析後**的 params 整包序列化：

```python
"params": {**dataclasses.asdict(base), ...}   # store.py:766
"engine_version": __version__                 # store.py:764
"schema_version": 9
```

因此 `view["params"]` 已含 `rate_by_expiry`（逐到期日期限對齊利率）、
`q_by_symbol`、`rate_curve_date`／`rate_curve_stale`／`q_source`／
`q_as_of`／`q_stale`（全部 provenance）、`iv_shifts`／`delta_bands`
等全部估值輸入。

> **這是好消息也是壞消息。** 好消息：重建**不需要**回頭重抓 Treasury
> 或 Yahoo——那天用的 r 與 q 是已知的、被記下來的。壞消息：**這些
> seed 今天的物理位置就在 `results.view` 內部**，而 view 正是要被
> 瘦身的那個東西。**先砍 view 再說「反正能重建」，會把重建能力本身
> 一起砍掉。** 見 §3.2-S3 與 §10 Stage 1-0。

**F6｜`snapshots` 存的是未經裁切的完整鏈，且是不可重新取得的市場
事實。**【本輪覆核】

`api_app/main.py::_analyze()` 回傳的第二個值是
`dataclasses.asdict(snap)`——那是**傳進去的原始 snapshot**，不是
`service._analyze()` 內部 `_scoped_to_selected_expiries()` 裁切後的
local rebind。因此 `snapshots` 表保存的是當次抓到的**全部**到期日與
合約，不是只有入選那幾期。`snapshot_from_dict()`（`data/snapshot.py:24`）
可無損還原成 `ChainSnapshot` 物件。

而 Cboe 端點只回「當下」全鏈、沒有歷史查詢參數【研究 §5.1】；免
credential 的歷史 chain 路線已在 #111 第二輪窮舉確認**不存在**
（Yahoo／Nasdaq／Cboe 三家皆不可）。

> **後果：`snapshots` 是 OD-02 定義下的第一類資料——「外部 vendor
> 當時取得、未來不保證可重新取得」。一旦刪除，那一刻的市場狀態就
> 永遠回不來了。**

---

## 3. Decision Cluster B：Storage Lifecycle（本輪主體，全節依 OD-02／OD-03 重寫）

> **B 排在 A 之前，因為它是唯一一個「就算永遠只有 Owner 一個人用，
> 也一定會撞牆」的問題。** 研究：Neon Free 0.5 GB ÷ 12.18 MiB
> ＝ **42 次刷新**（壓縮後上界 402 次）。

### 3.1 OD-02 的落地翻譯：四層，不是兩層

OD-02 的二分（「不可重建的事實」vs「可重建的衍生結果」）在落地時
必須拆成**四層**——因為本輪證明了有一類資料**理論上可重建、但重建
成本無法放進 read path**（§3.3-L2）。硬把它塞進任何一邊都會出事。

| 層 | 名稱 | 判準 | OD-02 對應 |
|---|---|---|---|
| **L0** | **Seed** | 刪掉就永遠回不來 | 「優先保存」 |
| **L1** | **Provenance & Version** | 沒有它，seed 無法被正確解讀或重放 | 「必要的 algorithm／schema／valuation version」 |
| **L2** | **Materialized derived（必要例外）** | 可由 seed 重建，**但重建成本結構上不能放進 read path** | ⚠ **OD-02 的明文例外**，見 §3.3-L2 |
| **L3** | **Pure derived** | 可由 seed 重建，且重建只發生在離線／除錯／稽核情境 | 「原則上可不永久保存完整內容」 |

### 3.2 Seed 完整性稽核（OD-02 要求的「必須先證明」）

**重建一份 `results.view` 需要的每一個輸入，逐項追到它今天的物理
位置：**

| # | 輸入 | 今天在哪 | 層 | 狀態 |
|---|---|---|---|---|
| S1 | 使用者輸入：`symbol`／`target_price`／`target_month`／`best_price`／`worst_price`／`strategies` | `scenarios` 表 | L0 | ✅ 已永久保存 |
| S2 | Chain snapshot：逐筆合約報價、`spot`、`source`、`fetched_at`（未裁切完整鏈） | `snapshots` 表（F6） | L0 | ⚠ **無 retention，且被 001 版列為瘦身候選——本輪推翻，見 §3.4** |
| S3 | 估值輸入：`rate_by_expiry`／`q_by_symbol`／`iv_shifts`／`delta_bands`／`rate_explicit` 等全部 `AnalysisParams` 欄位 | **`results.view["params"]`（F5）** | L0 | ⚠ **寄生在要瘦身的 payload 裡——這是 Stage 1 的第 0 步必須先解決的** |
| S4 | Provenance：`rate_curve_date`／`rate_curve_stale`／`rate_note`／`q_source`／`q_as_of`／`q_stale`／`q_note` | 同 S3（`params` 內） | L1 | ⚠ 同 S3 |
| S5 | `engine_version`／`schema_version` | `results.view` 頂層（`store.py:763-764`） | L1 | ⚠ 同 S3 |
| S6 | `today`（分析基準日） | **不需保存**——由 `snapshot_today(snap.fetched_at)` 結構性導出（F4） | — | ✅ 結構性成立 |
| S7 | `analyzed_at` | `results.analyzed_at`（欄位，非 JSONB 內部） | L1 | ✅ 已是獨立欄位 |
| S8 | 引擎本身（`ranking.py`／`filters.py`／`valuation.py`／`store.py` 的當時版本） | **不在資料庫裡**，只有一個版本字串標籤（S5） | — | ❌ **見 §3.3-L1，這是 determinism 的真實邊界** |

**結論**：`seed + version → deterministic reconstruction` 這條命題
**在 S8 的限制內成立**，且今天所需的資料**幾乎全部已經存在**——
缺的不是資料，是**它們的物理位置**（S3／S4／S5 寄生在 view 內）。

> **這就是為什麼 Stage 1 的第一個動作不是「砍」，而是「拆」**：
> 先把 `params`／`engine_version`／provenance 拆成不隨 view 一起消失
> 的獨立欄位，之後才有資格談要不要瘦身 view。**先砍後拆是不可逆的
> 錯誤。**

### 3.3 Deterministic reconstruction 的三個真實限制

> 委託明文要求：「若發現『只存 seed 無法可靠重建某個目前功能』，
> 必須明確列出原因，不可硬套 OD-02。」以下三項就是。

**L1｜`engine_version` 是標籤，不是時光機——重建的是「今天的引擎對
當時資料的看法」，不是「當時使用者看到的數字」。**

`engine_version` 只是一個寫進 view 的字串；**舊版引擎的程式碼不在
資料庫裡**。用今天的 `option_chaser` 重放三個月前的 seed，得到的是
今天的估值語意套在當時的報價上。

**這不是理論風險，本 repo 的歷史直接證明它會發生**：T01（#218）建立
的數值基準到目前為止已有 **9 次合法重產事件**（T02／T04／T09／T12／
T14／T15／REPAIR-09 等），每一次都代表估值或序列化語意改變過。其中
REPAIR-09（#246）把 single-leg 的估值日從日曆錨點改成自身到期日，
同一個候選的 `baseline_return` 從 `1.1926288317629354` 變成
`0.9569471624266144`——**舊 view 存的是前者，seed 重建會得到後者。**

因此「重建」必須分成兩種語意，spec 階段不得混用：

| 語意 | 需要什麼 | 今天可行嗎 |
|---|---|---|
| **Re-analysis**（用今天的引擎重新評價當時的市場資料） | seed 就夠 | ✅ 可行，而且**這正是有價值的那一種**——REPAIR-09 之後，重建出來的數字比當時存下來的更正確 |
| **Reproduction**（逐位元重現當時使用者看到的畫面） | seed ＋ 當時的引擎行為 | ❌ **不可行**，除非保留 derived 或引入引擎版本可回溯機制（後者遠超 foundation 範圍） |

> **給 spec 的紅線**：任何宣稱「刪掉 derived 也能重現歷史」的說法
> 都必須指明是哪一種語意。**Re-analysis 可以，Reproduction 不行。**

**L2｜重建成本結構上放不進 read path——這是 OD-02 的必要例外。**

SpreadHistory 淨成本走勢圖（`store.spread_cost_history()`）要的是
**N 個歷史時點**的 `cost`。若不保存、改為即時重建：

```
單次三 family 引擎時間            3.21s   【研究 M8，真實 TLT 2,414 合約】
一個刷新過 30 次的劇本            × 30
                                 ────────
重建整條走勢圖                    ≈ 96 秒   ← 這是「下界」，理由見下
外加：從 Neon 讀 30 份 snapshot   ≈ 14 MiB（TLT 0.48 MiB × 30）
```

⚠ **96 秒是嚴重低估，必須說清楚**：研究 M8 的 3.21s 是
`loaders=None` 的 **q=0 快路徑**——那條路徑不做逐腿 IV 反解校準。
而重建**必須**用當時的 r／q（否則就不是重建那次分析），會走完整的
`calibrate_leg` 校準路徑；本 repo 對這條路徑的既有量測是
**7.543 秒**（REPAIR-03／#240，production-scale 三 family 全開，
memoization 之後；之前是 154 秒）。真實重建時間介於兩者之間並偏
高端，再加上 Neon 讀取與反序列化。

> **結論不因這個修正而改變，只是變得更強**：連最樂觀的 96 秒都
> 已經不可行了。

Vercel 函式上限 300s（fluid）／本專案 `vercel.json` 自設 60s，
`REFRESH_RUN_BUDGET` 45s——**96 秒的純 CPU 重建放進一個開圖表的 GET
request 是結構上不可行的**，SPY（12,534 合約，butterfly 是 `C(n,3)`）
只會更糟。

> **結論：歷史走勢圖需要的那幾個數字必須 materialize（L2），不能
> 只存 seed。** 這是 OD-02 明文允許的「先證明」之後的誠實結果，
> 不是偷懶。
>
> **好消息是這個例外極小**：canonical 最小集合是
> `(scenario_id, analyzed_at, candidate_key, cost)` 四欄，而 F1 已
> 證明前端只讀 `cost`。

**L3｜Seed 本身不可重建——所以 OD-02 沒有讓 retention 消失，只是把
它從 derived 轉移到 seed 上，而後者的刪除是不可逆的能力損失。**

`snapshots` 是 F6 確認的第一類資料（vendor 當時取得、無歷史端點可
重新取得）。OD-02 之下它從「可瘦身的大 payload」升級成「必須優先
保存的 seed」。

但 seed 也不是零成長：TLT 0.48 MiB／SPY **2.55 MiB** 每次刷新
【研究 M6】。Neon Free 0.5 GB ÷ 0.48 MiB ≈ **1,000 次**（TLT）／
÷ 2.55 MiB ≈ **200 次**（SPY）【推估，未計 TOAST 壓縮】。

> **給 Owner 的誠實話**：OD-02 把「要不要留歷史 derived」這個**可逆**
> 的決定，換成了「要不要留歷史 seed」這個**不可逆**的決定。前者刪錯
> 了可以重算回來，後者刪錯了就是永久失去那一刻的市場資料。這不是
> 反對 OD-02——換來的是一個數量級的空間，而且方向正確——但它讓
> **seed retention 成為本輪唯一真正不可逆的 Owner Decision**（§9-Q1）。

### 3.4 分層結論：哪些必須永久保存、哪些可重建、哪些只需短期 retention

| 資料 | 今天 | 層 | 本輪結論 | 依據 |
|---|---|---|---|---|
| `scenarios`（使用者輸入） | 永久 | **L0** | **永久保存**。量體極小 | OD-02「使用者輸入」 |
| `snapshots`（raw chain） | 永久、無 retention | **L0** | **必須保存**（不是「可以砍」）。retention window 是 §9-Q1，且是唯一不可逆的一題 | F6、§3.3-L3 |
| `results.view["params"]`（含 r／q／provenance） | 寄生在 view 內 | **L0＋L1** | **必須先拆成獨立欄位**，才有資格談瘦身 view | F5、§3.2-S3 |
| `engine_version`／`schema_version` | 寄生在 view 內 | **L1** | 同上，一併拆出 | §3.2-S5 |
| `results.analyzed_at`／`best_return`／`representative_candidate`／`per_family`／`spot`／`family_eligibility` | 已是獨立欄位 | **L1／L2** | **維持**——清單卡片直接讀它們，不撈 view（既有正確設計，T07／#224） | `postgres.py` `_RESULT_COLS` |
| 歷史 `(candidate_key, cost)` 時間序列 | 埋在 `all_candidates`（74,011 筆／次） | **L2** | **必須 materialize，但只需最小集合**——範圍見 §9-Q2 | §3.3-L2、F1 |
| `all_candidates` 其餘欄位（`expiry`／`baseline_return`／`rank_in_expiry`） | 永久 | **L3** | **可不永久保存**——`src/` 全站零讀取端 | F1 |
| **current** `results.view` 完整內容（heatmap／payoff／ranking／max P/L／profit region／candidate_pool／axis_sets） | 永久 | **L3，但 current 那一份必須在** | **不得為了瘦身而動 current 的內容或行為**（OD-03 紅線）。可縮的是「歷史的那幾十份」，不是「使用者現在看的這一份」 | OD-03 |
| **歷史** `results.view` 完整內容 | 永久 | **L3** | **可短期 retention**——除 L2 的窄事實外，其餘可由 seed re-analysis 取得 | OD-02、§3.3-L1 |
| `events`（ANALYSIS_COMPLETED 等） | 永久 | **L0** | **永久保存**。它記錄「發生過什麼」，不可由 seed 導出；量體極小（一列一個時間戳＋ref） | OD-02「不可重建的事實」 |
| `diagnostics` | trim 至最新 200 筆 | **L3** | **不動**（已有 retention） | 既有設計 |
| 五張市場事實快取表（`rate_cache`／`treasury_year_cache`／`dividend_cache`／`contract_iv_history`／`iv_observations`） | 各自有語意化新鮮度 | **L0（歷史部分）／L3（當日部分）** | **不動**。`treasury_year_cache` 的過去年份、`iv_observations` 是 PIT 不可重建事實；`rate_cache` 當日值可重抓 | §2.1 |

**一句話版本**：

> **永久：使用者輸入、raw snapshot、估值輸入＋provenance＋version、
> events、歷史走勢圖的四欄窄事實。
> 短期：歷史 view 的完整內容。
> 不動：current view 的一切。**

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
**若 L2 窄表落地，這一項自動消失。**

⚠ 注意 OD-03：這一項是**純讀取路徑改善**，不刪任何資料、不改任何
使用者可見數字——它落在六步遷移的第 ③ 步之內，但**不需要**等 ①②，
因為它沒有新舊資料格式的問題。

### 3.6 OD-03 六步遷移的落地形狀

| 步 | 動作 | 對本專案的具體意義 | 可 rollback？ |
|---|---|---|---|
| **0**（前置，本輪新增） | **拆 seed** | 把 `params`／`engine_version`／provenance 從 view 內部複製到 `results` 的獨立欄位（純加法，view 原樣不動） | ✅ 純加法 |
| **①** | coexist／dual-write | L2 窄表與既有 `all_candidates` **同時寫**，兩邊都在 | ✅ 停寫新表即可 |
| **②** | parity proof | 對同一批歷史資料，`spread_cost_history()`（讀 view）與新窄表查詢，**逐位元比對** `cost` 序列。比照本專案既有 bitwise 凍結慣例（T01 數值基準、`test_selection_regression.py`） | — |
| **③** | 切換 read path | `/history` 改讀窄表；`/results` 改窄查詢 | ✅ 切回讀 view |
| **④** | production validation | 在真實 production 資料上確認走勢圖、卡片、詳細頁行為與切換前相同 | ✅ 同③ |
| **⑤** | 停止舊寫入 | `serialize_result()` 不再產生 `all_candidates`（或 `save_result` 前投影掉） | ⚠ 半可逆——停寫之後的新列沒有舊格式，但舊列還在 |
| **⑥** | 不可逆 cleanup／retention | 刪除歷史 view 的重量欄位／設定 snapshot retention | ❌ **不可逆。且需 §9-Q1／Q2 裁示後才能執行** |

**OD-03 的三條紅線在本專案的具體檢查點**：

1. **Performance preservation**：③④ 之後 `/history` 的 Neon 讀取量
   必須**下降**（365 MiB → 窄列），不得上升。若上升就是做錯了。
2. **Behavior preservation**：current analysis 的 ranking／candidate
   identity／return／champion／heatmap／UI 全部不動——本專案已有現成
   守門（`test_selection_regression.py` 身份＋數值雙軸、四份 CLI
   golden fixtures、契約樣本 drift 測試），**這些既有測試就是 OD-03
   的執行機制，不需要發明新的**。
3. **禁止直接刪除 production 依賴的 payload**：`all_candidates`
   今天**確實**被 `spread_cost_history()` 依賴（`store.py:277-279`
   直接讀 `r.get("all_candidates", [])`）——所以它落在①～⑤全部走完
   之前不得移除。

### 3.7 量化帳

| 方案 | 每次刷新永久成長（TLT） | Neon Free 0.5 GB 容得下 | 備註 |
|---|---|---|---|
| **今天** | view 12.18 MiB ＋ snapshot 0.48 MiB ＝ **12.66 MiB** | **≈ 40 次** | 【研究 M1／M5／M6】 |
| **OD-02 目標態** | snapshot 0.48 MiB ＋ L2 窄事實（約 150 筆／次，KB 量級）＋ L0/L1 欄位 ＝ **≈ 0.5 MiB** | **≈ 1,000 次** | 【推估】約 **25×** 改善 |
| SPY 的同一筆帳 | snapshot **2.55 MiB** | ≈ 200 次 | 【推估】seed 本身就是大宗 |

⚠ **兩項誠實揭露**：
1. 上表的「目標態」**不含 current view**（每個劇本最新一份必須完整
   保留，OD-03）。以每劇本一份 12.18 MiB 計，10 個劇本就是 122 MiB
   ——**這是常數而非成長項**，但在 0.5 GB 的額度下不可忽略。若這一項
   成為瓶頸，選項是壓縮 current view（zlib-6 實測 9.6×【研究 M4】），
   而**不是**縮減它的內容。
2. snapshot 也可壓縮（逐筆報價 JSON、欄位名高度重複，壓縮率**推估**
   不低於 view 的 9.6×），但本輪**未實測**，不列為既定收益。

---

## 4. Destination Criteria

Foundation 完成時，下面每一條都應該可以用一個測試或一個查詢回答
「是」：

| # | 判準 | Cluster |
|---|---|---|
| D1 | 一個 user 的任何動作，不會刷新、不會讀到、不會寫入另一個 user 的劇本 | A |
| D2 | 一輪刷新的 chain 抓取數，是「這個 user 自己的 distinct symbol 數」，不是「全站劇本的 distinct symbol 數」 | A |
| **D3**（本輪重寫） | **每次刷新的永久儲存成長，等於 seed（snapshot）＋常數量級的窄事實，而不是完整 derived payload。** 歷史 view 的完整內容有明確、有上界的 retention | B |
| D4 | 開一次歷史走勢圖，不會從 Neon 讀出整個劇本的全部完整 view | B |
| **D9**（本輪新增） | **對任何一份歷史結果，都能從獨立欄位讀出它當時的 `params`（含 r／q）、provenance 與 `engine_version`，不必解析 `view` JSONB** | B |
| D5 | Cboe 回 429 時，系統不會形成 retry storm；使用者看到的是明確、可理解的狀態＋資料時間，不是無差別的「抓不到報價」 | C |
| D6 | Treasury 的當日更新由排程完成；使用者的分析路徑正常情況下只讀 DB，不承擔 cold fetch | D |
| D7 | 任一 vendor 掛掉時，讀取既有結果的路徑仍然可用；哪些功能降級、降到什麼程度，是**寫下來的**而不是碰運氣 | Cross-cutting |
| D8 | 可以回答「昨天對 Cboe 發了幾次請求」「chain 命中率多少」「`results`／`snapshots` 表多大」 | Cross-cutting |

**刻意不列入 Destination 的**：
- 「同 symbol 同 freshness window 只打一次 vendor」——OD-05 已定
  **30 秒**這個產品參數，但**是否施工跨 request 共用仍在 evidence
  gate 後面**（OD-05 明文「不要因此立即推翻 ADR-0001」）。把它寫進
  Destination 等於跳過那個 gate。
- 任何延遲數字（p50/p99）目標——今天沒有基準線，訂了也無從驗證。

---

## 5. Decision Cluster A：User Isolation Boundary（依 OD-04 對齊）

### 5.1 為什麼它是「其他一切的前置」，但**不是**每件事的前置

| 說法 | 是否成立 |
|---|---|
| 「沒有 user 隔離，所有負載數字都是 O(U²)、因此無意義」 | ✅ 成立【研究 §7.2】 |
| 「因此所有 scaling 工作都要等它」 | ❌ **不成立**。B（storage lifecycle）在 U=1 就該做、與 owner 無關；C-1 的 429 韌性也與 owner 無關 |
| 「storage retention 會擋住 ownership」 | ❌ **不成立，且 OD-04 明文禁止這樣寫。** 兩者互不依賴——ownership 是加一個維度，storage 是改保存範圍，沒有共同的資料結構前提 |
| 「chain 快取設計要等它」 | ⚠ **部分成立**——快取本身是 user-agnostic 的，但**是否值得做**取決於 U，而 U 取決於它；另有 §5.5 的 credential 約束 |

> **正確的說法：A 是「開放多使用者」的前置，不是「所有 scaling 工作」
> 的前置。**

### 5.2 兩階段拆分（OD-04 已核准分階段）

| 階段 | 內容 | 解決什麼 |
|---|---|---|
| **A-1 Ownership / data boundary** | 每個 per-user 資料表加 owner 維度；storage port 的每個查詢帶身分；API 每個端點解析身分。今天的身分解析器**固定回傳同一個「solo owner」id** | **資料邊界正確性**：refresh scope 收斂（O(U²)→O(U)）、查詢不再跨 owner。**不需要任何登入 UI** |
| **A-2 Authentication / identity binding** | 真正的登入／憑證／session／帳號生命週期 | **「你是誰」的證明**。⚠ **在它完成之前，系統不具備 privacy 保證** |

**A-1 的關鍵性質**：**backward-compatible**——依 OD-04，既有 Scenario／
Result／Snapshot 全部 backfill 成現有 Owner 的 id，行為與現在**逐位元
相同**；之後換上真的身分解析器時，**只有那一個函式改變**。

### 5.3 ⚠ OD-04 明令修正的一處措辭（本輪已改）

001 版寫「A-1 這一層解掉的是 **correctness 與 privacy**」。

**這句話依 OD-04 作廢。** 正確表述是：

> **A-1 建立的是 data boundary，不是 privacy。**
> 一個固定回傳 solo owner 的身分解析器，沒有任何機制阻止第三方冒充
> 那個 owner——它讓資料**有主**，但沒有讓資料**受保護**。
> **`owner_id` 欄位存在 ≠ privacy 已完成。**
> **真正開放多使用者之前，A-2（authentication／identity binding）
> 是不可跳過的。**

這條紅線同時修正 §12 的分類（見該節）。

### 5.4 哪些資料 per-user、哪些必須維持 system-wide

【覆核 `postgres.py` 全表】

```
必須 user-scoped（使用者自己的東西）
  ├── scenarios              ← 劇本本體
  ├── results                ← 該劇本的分析結果
  ├── snapshots              ← 該劇本的原始快照（L0 seed）
  ├── events                 ← 該劇本的事件（L0）
  ├── provider_credentials   ← ⚠ 今天是全站一把（F3）
  ├── data_source_settings   ← 今天是全站一份
  └── provider_verifications ← 跟著 credential 走

必須維持 system-wide shared（公開市場事實，按 user 切分會破壞共用）
  ├── rate_cache             ← 全站當日一條曲線（OD-01 排程填的就是它）
  ├── treasury_year_cache    ← per-year
  ├── dividend_cache         ← per-symbol
  ├── contract_iv_history    ← per-contract
  └── iv_observations / iv_backfill_runs  ← per-symbol

不屬於任何一邊
  └── diagnostics            ← 營運資料。⚠ context 白名單裡若含使用者
                                 輸入的 symbol，multi-user 下需要重新
                                 檢視（§9-Q3）
```

> **這條線非常乾淨，而且今天的鍵設計已經站在對的一邊。** 五張快取表
> 沒有一張需要加 owner 欄位——這不是巧合，是研究 §8.1 指出的「本專案
> 快取鍵設計相當成熟」的直接後果。

### 5.5 A 對 C 的一個硬約束

**`provider_credentials` 全站共用（F3）＋ chain 共用快取，如果同時
存在，會產生一個新的隱私／成本問題**：

> 使用者 A 設了自己的 Market Data token，A 的一次刷新用 A 的 token
> 抓了 TLT 全鏈（燒掉 2,414 credits）。如果這份資料進了共用快取，
> B 就用到了 A 花錢買的資料。

**推導出的設計約束**（不是裁示，是限制）：

- 共用快取的鍵必須含**來源**，不只 symbol：`(symbol, source)`。
- **自訂來源（使用者自備 token）抓來的資料，不應該進共用快取。**
- **預設來源（Cboe，公開 CDN）沒有這個問題**，它天生適合共用。

> 這條約束的實際效果是：**OD-05 的 30 秒共用窗只需要涵蓋預設來源
> 那條路徑**，設計範圍因此比想像中小。

### 5.6 明確不做

- ❌ enterprise RBAC、org／team、角色權限矩陣
- ❌ 多租戶資料庫分片
- ❌ 因為「未來可能多租戶」而預留的抽象層

> 需要的是**一個 owner 欄位＋一條身分解析縫**，不是一套權限系統。

---

## 6. Decision Cluster C：Option Chain（依 OD-05 對齊）

> **OD-05 把這個 cluster 一分為二，而且兩半的狀態完全不同**：
> 使用者可見語意**已裁示、可施工**；跨 request 共用機制**仍在
> evidence gate 後面**。001 版把它們寫在一起，是本輪修正的第二處
> 內部矛盾。

### 6.1 OD-05 的七條，逐條歸位

| # | OD-05 條文 | 需要跨 request 共用機制嗎 | 歸屬 | 狀態 |
|---|---|---|---|---|
| 1 | shared freshness window **30 秒** | ✅ **需要**（要讓 B 用到 A 剛抓的那份） | **C-2** | ⏸ evidence gate |
| 2 | 手動 Refresh **也不繞過**此窗 | ✅ 需要（同上，這是窗的語意的一部分） | **C-2** | ⏸ evidence gate |
| 3 | 顯示 quote fetched time | ❌ 不需要 | **C-1** | ✅ **可施工** |
| 4 | 429 時優先顯示上一份成功資料＋stale 標示 | ❌ 不需要 | **C-1** | ✅ **可施工** |
| 5 | honor `Retry-After` | ❌ 不需要 | **C-1** | ✅ **可施工** |
| 6 | `Retry-After` 期間禁止立即重打 vendor | ❌ 不需要 | **C-1** | ✅ **可施工** |
| 7 | 持續失敗時明確顯示資料源異常 | ❌ 不需要 | **C-1** | ✅ **可施工** |

> **七條裡有五條不需要任何快取。** 這是本輪最有操作價值的一個拆解
> ——**Stage 2 原本的 blocker（001 版 §9-Q4「使用者看到什麼」）已由
> OD-05 第 3～7 條回答完畢，Stage 2 因此解除阻擋、可直接進 spec。**

### 6.2 C-1｜429 韌性與資料時間揭露（**NOW，已解除阻擋**）

【研究 §5.5 ＋ 逐行覆核 `data/cboe.py:96-105`】

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

**OD-05 定下的目標行為**（第 3～7 條）對應到本專案的既有機制：

| OD-05 要求 | 落地位置 | 現況 |
|---|---|---|
| 顯示 quote fetched time | `view["meta"]["fetched_at"]`／`data_quality.fetched_at` | ✅ **資料已經在契約裡**，缺的是前端呈現 |
| 429 顯示上一份成功資料＋stale | 卡片失敗兩態（REPAIR-05／#242 已落地「曾成功過 → 反灰＋顯示上一次成功結果」） | ⚠ **一半已有**，缺的是把 429 與一般失敗區分開、並標 stale |
| honor `Retry-After` | `data/cboe.py` adapter：讀 status、讀標頭 | ❌ 完全沒有 |
| 禁止立即重打 | 前端重試閘門 ＋ 後端拒絕視窗 | ❌ 完全沒有 |
| 持續失敗顯示資料源異常 | 既有 `{stage, message}` 失敗分層 | ⚠ 分層在，但訊息無差別，看不出是限流 |

⚠ **`data/cboe.py` 的 docstring 目前只寫「無官方文件、無 SLA」，
沒有記載它會 429**——這本身是一個應該一併修正的事實記載。

### 6.3 C-2｜30 秒共用窗（**仍在 evidence gate 後面**）

**OD-05 給的是參數，不是施工授權**——它明文「不要因此立即推翻
ADR-0001，chain 跨 request／shared cache 是否施工，仍走 evidence
gate」。

ADR-0001 明文：**不要重新提案，除非「流量形狀本身改變，且有同時
計入新增往返成本的量測」。**

| ADR 的理由 | 今天 |
|---|---|
| 「miss 路徑純增加成本：多一次 Neon SELECT ＋ 把整條 chain 當 JSONB 寫回，而同一份 payload 本來就寫進 `snapshots`」 | **仍然完全成立，而且更強**——SPY snapshot 實測 2.55 MiB。**這是反對『把 chain 放進 Postgres』最強的論證，本輪同樣沒有推翻它。** |
| 「hit 路徑沒有證據比一次 Cboe GET 便宜」 | Cboe TLT GET 實測 0.23–0.60s；1 MiB JSONB 從 Neon 讀出＋重建 dataclass **很可能不會更快** |
| 「跨 invocation 沒有共享記憶體」 | ⚠ 已被平台改變推翻（fluid compute）——但依 Runtime 結論，**這只開啟一個不能當 correctness layer 的選項**，見 §8.1 |

**gate 的輸入是 Stage 0 的量測**，不是本輪的推論。

**登記在案、供 gate 時評估的第三選項**：ADR 只比較了「Postgres 快取
vs 不快取」，**從未評估 Vercel Edge CDN**。如果「取得某 symbol 的鏈」
存在為一個 **GET 端點**，`s-maxage` + `stale-while-revalidate` 可以在
**平台層**做共用：零 Neon 往返、零額外寫入，正好繞開 ADR 最強的那個
反對理由。⚠ 這**不是提案**——它會改變 API 形狀（POST `refresh-run`
天生不可快取），而且沒有量測。

⚠ **一個 30 秒窗特有的、必須在 gate 時一併評估的取捨**：OD-05 第 2 條
（手動 Refresh 也不繞過）意味著使用者按下刷新鈕、看到的可能是最多
30 秒前的報價。這是刻意的產品選擇（Cboe 本身就是 `delayed_quotes`，
相對新鮮度損失是二階的），但它**必須配合第 3 條（顯示 fetched
time）才誠實**——兩條是一組，不能只做一條。

### 6.4 Sharing scope / cache location / stampede — 留給 gate 後

在 Stage 0 的量測出來之前，任何收斂都是猜測。本文只記錄兩條已定的
約束：

1. **共用只涵蓋預設來源（Cboe），鍵必須含 source**（§5.5）。
2. **窗長 = 30 秒**（OD-05，已定，不必再挑數字）。

---

## 7. Decision Cluster D：Treasury / Dividend（依 OD-01 對齊）

> **除了 OD-01 指定的排程之外，本 cluster 的正確態度仍是「幾乎什麼
> 都不要做」。**

### 7.1 請求量從來不是問題——OD-01 解的是延遲，不是負載

Treasury 全站每市場日約 1 次；Dividend 每 (symbol, 市場日) 1 次。
即使 U=1,000，Treasury 的期望上界也只有 2–3 次【研究 §3.7 推估】。

真正的踩點是延遲【研究 P0-5】：

```
Treasury cold miss 最壞 = 3 × 15s = 45s（CSV → XML → 前一年 CSV）
REFRESH_RUN_BUDGET      = 45s
vercel.json maxDuration = 60s（本專案自設）
```

> 每個市場日的**第一批**使用者，可能在一次刷新裡就把整個時間預算耗在
> 等 Treasury 上。**這是 latency／timeout 的 correctness 問題，不是
> capacity 問題**——而 OD-01 正是為它而下的。

### 7.2 OD-01 的落地形狀：Cron 主動填 ＋ 同步 refresh-on-miss 保底

**這不是兩個備選方案，是一個方案的兩半。** 依 Runtime 結論
（Python 無 `waitUntil`），fire-and-forget 背景更新這條路不存在；
`runtime-targeted-scaling.md` §2.3(d) 給的可行形狀正是這個疊加：

| 元件 | 角色 | 依據 |
|---|---|---|
| **Vercel Cron → 專屬 refresh endpoint** | **主路徑**。每市場日主動把 `rate_cache` 填新，使用者永遠不 cold miss | OD-01「每日自動排程更新」；`runtime-targeted-scaling.md` §2.3(d) 選項 2 |
| **既有同步 refresh-on-miss** | **保底**。Cron 沒跑到／跑失敗時，當天第一個請求自己救回來 | OD-01「原則上只讀 DB」的「原則上」；今天 `rate_cache.py` 本來就是這個形狀，**不必新寫** |
| **既有 7 天 stale fallback ＋ `rate_note`／`stale`** | **降級揭露**。用上一個有效市場日的資料，明確標示 | OD-01「使用上一個有效市場日資料 ＋ 明確標示 stale／effective date」；**今天已經完全具備**（§2.1） |

> **給 spec 的紅線**：**不得**因為「有 Cron 了」就拿掉同步
> refresh-on-miss。OD-01 說的是「原則上只讀 DB」，不是「只能讀 DB」
> ——拿掉保底路徑會讓 Cron 的任何一次失敗直接變成當天全站沒有真實
> 利率曲線。

**⚠ 平台限制必須寫進 spec，否則會誤解 OD-01 的「後續排程再補」**
【研究 §6.3，官方文件】：

| 限制 | Hobby | 對 OD-01 的意義 |
|---|---|---|
| Cron 最小間隔 | **一天一次** | 「後續排程再補」在 Hobby 上是**明天再補**，不是一小時後 |
| Cron 精度 | **±59 分鐘** | 排在 UTC 21:00（＝ET 17:00），最晚 21:59 UTC 仍在 Treasury 當日 15:30 ET 發布之後、隔日開盤之前——**這個時窗吸收得了抖動** |
| 一天只有一次機會 | — | 那一次若失敗，**當天靠的就是同步保底路徑**（所以它不能被拿掉） |

> 換句話說：**在 Hobby 上，OD-01 的「後續排程再補」實際上是由
> 「當天第一個使用者的同步 refresh-on-miss」完成的，不是由排程。**
> 這不違反 OD-01（使用者仍然拿得到當天資料、stale 有標示），但它是
> 一個 Owner 應該知道的落地差異。若要「當天內由排程重試」，需要 Pro
> ——列入 §9-Q4 知情項，不要求現在決定。

### 7.3 Dividend：不進 foundation

- **不做全 universe preload**：universe 不封閉——`symbol` 只受
  `^[A-Za-z.\-]{1,10}$` 約束，使用者可建立任何代號【研究 §4.5】。
- **不做 single-flight**：per-symbol 的 stampede 只會發生在「同一個
  symbol、同一個市場日、同一個 0.7 秒視窗內、多個並發冷請求」。在
  1,000 users 量級下是低機率事件，後果只是多打幾次 Yahoo。
- **OD-01 明文只涵蓋 Treasury**，本輪不擅自把排程擴張到 Dividend
  （而且 universe 不封閉讓它結構上也做不到）。

### 7.4 明確劃出去：Yahoo 替換 ≠ Scaling Foundation

研究實測：`query2.finance.yahoo.com/robots.txt` ＝ `Disallow: /`，
且無公開 API、無 SLA。

**這不屬於 Scaling Foundation。** 理由：
1. 它是**合規／治理決策**，不是容量決策。
2. 它需要**自己的 vendor 研究**，與本 foundation 的依賴鏈不相交。
3. 它的**風險曲線與 U 無關**——1 個和 1,000 個使用者面對的是同一個
   「這條依賴隨時可能被單方面斷掉」的風險。

> **建議另開 data-provider migration 獨立線。** 列為 §9-Q4 知情項。

---

## 8. Decision Cluster E：Runtime / Deployment / Scheduler（結論已定案）

### 8.1 Process-local cache：只能是 L1 optimization，**絕不能是 correctness layer**

【研究 §6.3 ＋ `runtime-targeted-scaling.md` §1.3 逐字覆核】

Vercel fluid compute 官方文件：「multiple invocations **can** share the
same physical instance (a global state/process) concurrently.」

**關鍵字是 "can"，不是 "will"。** Vercel 不承諾實例數量、實例生命
週期、哪個請求落在哪個實例、冷啟動頻率。因此：

> **任何「正確性」依賴行程內快取的設計都是不安全的。**
> 例如「我們保證同一個 30 秒窗只打 Cboe 一次」——這句話在
> process-local 快取上**無法成立**，因為你不知道有幾個 process。

**⚠ 而且本專案連「有沒有開」都無法確認**：`runtime-targeted-scaling.md`
§1 記錄六種 Vercel MCP 查詢路徑對 `option-chaser` production 專案全數
404／零可見度，判定 **NOT_CONFIRMED**（是「查過查不到」，不是「沒查」）；
`vercel.json` 也沒有顯式 `fluid` key，狀態完全取決於 dashboard 設定。

> **這讓「不能依賴它」這條結論比原本更強，不是更弱**——連開關狀態都
> 不確定時，更沒有理由把任何正確性建立在它上面。
>
> **Owner 一分鐘可自行確認**：Vercel dashboard → `option-chaser` →
> Settings → Functions → Fluid Compute 開關（官方文件給的標準路徑）。
> 但**確認結果不會改變上面的結論**（"can" 不是 "will" 是機制本身的
> 性質，與開關無關）。列入 §9-Q4 知情項。

### 8.2 Python background execution：官方未支援，SWR 必須換觸發形狀

【`runtime-targeted-scaling.md` §2，四份官方文件一致】

`waitUntil()`／`after()` 定義在 npm 套件 `@vercel/functions`，該頁
`<title>` 本身寫死 `"(Node.js)"`；官方 Python SDK 參考頁六個章節窮舉
列出、`waitUntil` 零命中；Python runtime 主文件頁零命中；2024-05-10
官方 changelog 原文明講首發範圍是 "Node.js and Edge runtimes"。

**判定：NOT_SUPPORTED（as officially documented）。**

> **對本地圖的影響**：SWR 這個**目標**不必放棄，但**形狀**必須換——
> 見 §7.2，改由「Cron 主動填 ＋ 同步 refresh-on-miss 保底」達成，
> 而不是 fire-and-forget 背景更新。這正是 OD-01 的形狀。

⚠ 一則 dev.to 部落格聲稱 Python 也支援，與四份官方文件矛盾，
`runtime-targeted-scaling.md` §5 已列為**未仲裁的殘留疑點、不採信為
結論**。本地圖沿用該判斷。

### 8.3 是否需要 distributed cache / lock？

**foundation 階段不需要，而且不建議。**

| 選項 | 評估 |
|---|---|
| Redis / KV | 新增一個 vendor 依賴、新增一個 failure domain、新增成本。**在還沒證明 Postgres 不夠之前，這是 overengineering** |
| Postgres advisory lock | Neon 支援、零新 vendor。**如果真的需要 single-flight，這是第一選擇** |
| 不做 | 對 Treasury（OD-01 之後由 Cron 主動填，stampede 窗本身就大幅縮小）／Dividend（§7.3）而言完全可接受 |

> **判準**：先把 Stage 0 的計數器裝上去，看到真實的並發冷請求數
> 之後，再決定要不要 lock。
>
> ⚠ 注意 OD-01 **順帶削弱了 Treasury single-flight 的價值**：排程
> 主動填之後，「當天第一批並發冷請求」這個 stampede 情境的觸發條件
> 從「每個市場日必然發生」變成「只有排程失敗那天才發生」。

### 8.4 Scheduler：只有一個地方真的合理（而 OD-01 正是那一個）

| 資料 | 排程是否合理 | 理由 |
|---|---|---|
| **Treasury** | ✅ **合理，Hobby 就做得到**——**這正是 OD-01** | 每營業日 15:30 ET 更新一次；Hobby cron 一天一次剛好夠，±59 分抖動可被排程時間吸收（§7.2） |
| **Dividend** | ❌ 不合理（全 universe） | universe 不封閉【研究 §4.5】 |
| **Chain** | ❌❌ 絕對不合理（全 universe） | 同上，且量體 1–5.6 MB／symbol |
| Hot-symbol warming | ⚠ 需要 Pro（一天一次不夠密），且是**延遲優化** | 延後 |

### 8.5 Hobby vs Pro：**不應該是架構的前置條件**

> **「升級付費方案」不是架構修復。**

- **Foundation 的每一塊都應該 plan-independent**——在 Hobby 上就要
  正確運作。OD-01 的 Cron 在 Hobby 上可行（§7.2），這是刻意確認過的。
- 唯一會被 plan 影響的是**可選的 warming 層**，而 warming 本來就被
  排在 foundation 之外。
- ⚠ **Hobby 的商業使用條款**是否適用於本專案，研究未查證。這是產品／
  合規問題，不是工程問題 → §9-Q4。

### 8.6 一個應該順手更正的過時事實

研究發現本 repo 有 **7 處**寫著「60 秒函式硬性上限」（`CONTEXT.md:123`、
`api_app/main.py:62/72/1033/1053`、`option_chaser/service.py:71/1287`、
`docs/adr/0001:10`）。

覆核 `vercel.json`：**`maxDuration: 60` 是本專案自己設的**，fluid
compute 下 Hobby 的 default 與 maximum 都是 300s。

⚠ **但依 §8.1，「fluid 是否啟用」是 NOT_CONFIRMED**——所以正確的
更正措辭不是「上限其實是 300s」，而是：

> **「60 秒是本專案在 `vercel.json` 自設的 `maxDuration`，不是平台
> 硬性上限；平台上限取決於 fluid compute 是否啟用（本專案狀態未
> 確認），非 fluid 為 60s、fluid 為 300s。」**

同一次順手更正 ADR-0001 的「沒有共享記憶體」那句（改為「可能共享、
但不保證，不得依賴」）。

---

## 9. Owner Decisions（**只剩真正未決的**）

### 9.0 已解除的題目（可追溯，不再討論）

| 001 版的題目 | 由誰解 | 結果 |
|---|---|---|
| Q1「『我的劇本』要做到什麼程度」第 1 問（現在是否就做 ownership） | **OD-04** | ✅ **要做**。先建立 ownership／data boundary |
| Q1 第 2 問（既有資料歸誰） | **OD-04** | ✅ **全部歸現有 Owner** |
| Q1 第 3 問（登入是否分開做） | **OD-04** | ✅ **可分階段**，但 A-2 是開放多使用者的必要條件 |
| Q2 第 3 問（raw snapshot 要不要保留歷史） | **OD-02 ＋ 本輪 §3.3-L3** | ✅ **要保留**——它是不可重建的 seed。001 版的「只保留最新一次」選項**已作廢** |
| Q3「報價可以多舊」全部三問 | **OD-05** | ✅ **30 秒**；**手動 Refresh 不繞過**；**429 時顯示稍舊資料＋標示**（不讓使用者乾等） |
| Q4「抓不到時使用者看到什麼」全部三問 | **OD-05** | ✅ 三問皆定（顯示上次成功＋stale／禁止立即重打／持續失敗明確揭露）。**Stage 2 的阻擋因此解除** |
| Q5「ADR-0001 要不要重開」第 1、2 問 | **OD-05** | ✅ **不立即推翻，先走 evidence gate**（＝先量測）。降級為 Stage 5 gate 的輸入，不再是 blocking decision |
| Q6「兩個未查證事實」 | **runtime-targeted-scaling.md（2026-09-04）** | ✅ 已查證：fluid **NOT_CONFIRMED**；Python background **NOT_SUPPORTED** |

### 9.1 Q1｜**歷史的原始市場快照，你願意保留多久？**（唯一不可逆的一題）

**具體情況**：每按一次刷新，系統會把當時從 Cboe 抓到的**整條選擇權
鏈**原封不動存一份（TLT 每次 0.48 MB、SPY 每次 **2.55 MB**）。

**為什麼這一題和其他題不一樣**：這份資料**刪掉就永遠拿不回來**。
Cboe 的端點只回「現在」的報價，沒有任何方式查詢「2026 年 9 月 5 日
下午三點的 TLT 全鏈長什麼樣」；免費的替代來源本專案已經窮舉查過
（issue #111），也沒有。

而你剛定下的原則（OD-02）正好把它的地位提高了：**其他東西之所以可以
不永久保存，理由正是「反正可以從這份原始資料重算回來」。所以這份
一旦刪掉，可重算的那些東西也一起沒了。**

**要決定的是**：

1. 這些原始快照要保留多久？
   - (a) 全部永久保留（最安全，但 Neon Free 0.5 GB 大約 **1,000 次**
     刷新就滿；若常看 SPY 這類大標的，約 **200 次**）
   - (b) 保留最近 N 次／N 天，更舊的刪除（＝**有意識地放棄**那段期間
     的重算能力）
   - (c) 只保留「每個交易日最後一次」（同一天刷新五次，只留最後那份）
2. 如果選 (b) 或 (c)，你能接受「超過保留期的歷史，將來想重新分析時
   完全沒有資料可用」嗎？

**技術後果**：這是本輪唯一**不可逆**的決定。其他所有瘦身（歷史結果、
走勢圖範圍）刪錯了都能從快照重算回來，只有這一項不行。

> ⚠ **依 OD-03 第 ⑥ 步，這一題在整個遷移的最後才需要執行**——所以
> 它**不擋 spec 撰寫、不擋前五步施工**。但它必須在按下刪除鍵之前有
> 答案。

### 9.2 Q2｜**歷史走勢圖，你真正想看到多少？**

**具體情況**：現在每按一次刷新，系統會把當次算出來的**全部候選**
（TLT 實測 **74,011 筆**）完整存進資料庫，每次約 **12.18 MB**。
而這 74,011 筆存進去之後，畫面上真正用到的**只有一條線的高度**
（淨成本）——其餘欄位在整個前端**一個字都沒有被讀過**。

**本輪查證後的補充**：這一條線的數字，理論上可以從原始快照重算，
但實測要 **3.21 秒／次**——一個刷新過 30 次的劇本，重算整條走勢圖
要 **96 秒**。使用者開個圖表不可能等 96 秒。**所以這幾個數字必須
實際存下來，不能只靠重算。**（這是 OD-02 之下一個誠實的例外，
理由見 §3.3-L2。）

**要決定的是**：

1. 你打開歷史走勢圖時，希望能看**哪些候選**的歷史？
   - (a) 只有卡片頭條那一個 ← 約 1–3 筆／次
   - (b) **你在畫面上點得到的每一個**（各到期日前十名）← 約 **150 筆
     ／次**（比現狀縮減約 500 倍）
   - (c) 全部（現狀）← 約 74,000 筆／次
2. 這條走勢線要留多久？（全部／最近 N 次／最近 N 天）

**本輪的建議值（不是裁示）**：**(b)**。理由是它可以直接從 OD-02 推導
出來——OD-02 說「保存不可重建的事實」，而這幾個數字之所以必須保存
純粹是因為 read-path 成本，那麼保存範圍就該取「讓功能不退化的最小
集合」＝使用者點得到的那些。且既有的「找不到就顯示斷點、不插值」
機制（F2）已經支援：某個候選某次跌出前十，畫面上會自然斷一格，
不會壞掉。

**第 2 問（留多久）無法從 OD-02 推導**——那是產品決策（走勢圖要看
多長），只有你能回答。

> ⚠ 同 Q1：依 OD-03，這一題也在第 ⑥ 步才需要執行，**不擋 spec**。

### 9.3 Q3｜診斷紀錄裡的標的代號，算不算需要隔離的資料？

**具體情況**：系統的錯誤診斷紀錄（Settings 頁的「Diagnostics／
報錯紀錄」）在記錄一次失敗時，context 裡可能含使用者輸入的標的代號
（例如 `TLT`）。這張表今天不屬於任何使用者，是全站營運資料。

**要決定的是**：多使用者情境下，A 在診斷頁看到 B 查過 `NVDA` 這件
事，算不算問題？

- (a) 不算——標的代號是公開市場資訊，不是隱私
- (b) 算——診斷紀錄應該跟著 owner 走
- (c) 折衷：診斷紀錄維持全站，但把可能含使用者輸入的欄位遮蔽

**技術後果**：(a) 零改動；(b) 要給 `diagnostics` 加 owner 維度；
(c) 動既有的 redaction 白名單。三者都不大，但方向必須先定。

> OD-04 涵蓋了 Scenario／Result／Snapshot，**沒有涵蓋這一張表**，
> 所以它是 001 版 Q1 附註留下來、目前唯一還沒有答案的 ownership 問題。

### 9.4 Q4｜四件與 scaling 無關、但你應該知道的事（**不要求現在決定**）

1. **Dividend 主要來源 Yahoo 的 `robots.txt` 是 `Disallow: /`**——
   整個 host 對自動化存取是不允許的。這條依賴隨時可能被單方面斷掉，
   若產品要商業化，這是合規問題。**建議另開獨立線處理。**
2. **Market Data App 自訂 chain 來源，一次刷新要 2,414（TLT）–12,534
   （SPY）credits**，而 Free 一天只有 100。產品目前**完全沒有揭露
   這個成本**。
3. **Vercel Hobby 的商業使用條款**是否適用於本專案，研究未查證。
   另外 Hobby 的 cron 一天只能跑一次、精度 ±59 分鐘——這讓 OD-01 的
   「後續排程再補」在 Hobby 上實際是由「當天第一個使用者的同步
   保底路徑」完成的（§7.2）。若要「當天內由排程重試」需要 Pro。
4. **Fluid Compute 開關狀態你可以一分鐘查完**：Vercel dashboard →
   `option-chaser` → Settings → Functions → Fluid Compute。
   ⚠ **但查出來是開或關，都不會改變本地圖任何結論**（§8.1）——它只
   影響「順手更正 60 秒那句話」時的措辭精確度。

---

## 10. Dependency Graph 與 Stage Map

### 10.1 依賴推導（不預設順序，逐條推出來）

```
Obs（最小量測）          ← 不依賴任何人。而且它是 C-2 gate 的唯一證據來源。
B-0（拆 seed）           ← 不依賴任何人。純加法。★本輪新增，且是 B 的第一步
C-1（429 韌性＋資料時間） ← 不依賴任何人。★OD-05 已解除它原本的裁示阻擋
A-1（ownership 邊界）    ← 不依賴任何人。★OD-04 已解除它原本的裁示阻擋
D（Treasury 排程）        ← 不依賴任何人。★OD-01 已定形狀，且不需要背景執行 API
───────────────────────────────────────────────────────
B-1..B-5（storage 遷移前五步） ← 依賴 B-0（seed 必須先拆出來）
B-6（不可逆 cleanup）     ← 依賴 B-1..B-5 全部 ＋ Owner 的 Q1／Q2
A-2（auth 產品層）        ← 依賴 A-1
C-2（chain 30 秒共用窗）  ← 依賴 Obs（證據）＋ Stage 5 gate ＋ A-1（§5.5 source 約束）
```

**推導出的關鍵洞察四則：**

1. **可立即開工的項目從 001 版的四項增加到五項**（Obs／B-0／C-1／
   A-1／D）——因為 OD-01、OD-04、OD-05 各自解除了一個原本卡在
   「等 Owner 裁示」的阻擋。**foundation 的主體沒有長鏈依賴。**
2. **B-0（拆 seed）是本輪新推導出來的第一步，而且它必須在任何瘦身
   動作之前**。理由不是流程潔癖，是 F5 的物理事實：重建所需的
   `params`／`engine_version` 今天就住在要被瘦身的那個 payload 裡。
   **先砍後拆是不可逆的錯誤。**
3. **Obs 必須早於 C-2**，這是一條**非顯而易見**的依賴：ADR-0001 自己
   設定的重開門檻要求量測，而我們今天沒有任何計數器。OD-05 給了
   30 秒這個**參數**，但明文保留 evidence gate——**參數已定不等於
   可以施工。**
4. **B-6 是唯一被 Owner 未決事項擋住的施工步驟**（Q1／Q2）。其餘
   全部可進 spec。這是「READY_FOR_SCALING_SPEC」成立的關鍵理由
   （§14.2）。

### 10.2 Stage Map

> 每個 stage 只說：解哪個風險、前置依賴、是否改 schema、是否影響
> production 行為、rollout／rollback 要點。**不開票。**

#### Stage 0｜最小可觀測性

- **解哪個風險**：D8。今天無法回答「昨天對 Cboe 發了幾次請求」，
  因此 C-2 的 gate **結構上無法收斂**。
- **前置依賴**：無。
- **改 schema**：可能不需要——`diagnostics` 已有 `emit()` 與 structured
  JSON log 機制，但目前只有 `warning`／`error` 落盤（`main.py:1215-1233`）。
  可選：純 log（零 schema）／新增輕量計數表。
- **影響 production 行為**：不應該有。純觀測。
- **rollout／rollback**：純加法，可隨時關閉。
- **最小指標集**（不要建 observability platform）：
  `chain fetch count`、`chain 429 count`、`stale serve count`、
  `treasury/dividend cold miss count`、**`results`／`snapshots` 表大小
  與列數**、`單列 view 大小分布`、`refresh 端到端延遲`。

#### Stage 1｜Storage lifecycle（依 OD-02／OD-03，本輪重寫）

**這一個 stage 內部有六個子步驟，順序由 OD-03 固定，不得跳步。**

| 子步 | 動作 | 改 schema | 影響使用者可見行為 | 可 rollback |
|---|---|---|---|---|
| **1-0** | **拆 seed**：`params`／`engine_version`／provenance 從 view 內部複製到 `results` 獨立欄位（★本輪新增，見 F5／§3.2） | ✅ 純加法 | ❌ 無 | ✅ |
| **1-1** | L2 窄表建立 ＋ **dual-write**（與 `all_candidates` 並存） | ✅ 新表 | ❌ 無 | ✅ |
| **1-2** | **parity proof**：新窄表查詢 vs `spread_cost_history()` 逐位元比對 | ❌ | ❌ 無 | — |
| **1-3** | 切換 read path（`/history` 讀窄表；`/results` 改窄查詢＝順帶解掉 G4） | ❌ | ⚠ **效能改善**，數字不變 | ✅ |
| **1-4** | **production validation**：真實資料上確認走勢圖／卡片／詳細頁行為不變 | ❌ | ❌ 無 | ✅ |
| **1-5** | 停止舊寫入（新結果不再產生 `all_candidates`） | ❌ | ❌ 無（讀取端已切換） | ⚠ 半可逆 |
| **1-6** | **不可逆 cleanup／retention** | ❌ | ⚠ **歷史可見範圍改變** | ❌ **不可逆** |

- **解哪個風險**：D3、D4、D9。**唯一在 U=1 就會撞牆的問題。**
- **前置依賴**：1-0～1-5 無外部依賴；**1-6 需要 §9-Q1（seed
  retention）與 §9-Q2（走勢圖範圍與時間窗）的裁示**。
- **OD-03 檢查點**（每一步都要過）：
  - current analysis 的 ranking／candidate identity／return／champion／
    heatmap／UI **逐位元不變**——用既有守門（`test_selection_
    regression.py` 身份＋數值雙軸、四份 CLI golden fixtures、契約樣本
    drift 測試），**不需要發明新機制**。
  - **效能不得退步**：1-3 之後 `/history` 的 Neon 讀取量必須下降
    （365 MiB → 窄列）。若上升就是做錯了。
- **⚠ 明確禁止**：在 1-1～1-5 走完之前移除 `all_candidates`——
  `spread_cost_history()`（`store.py:277-279`）今天**真的**在讀它，
  這是 OD-03 明文禁止的「直接刪除 production 依賴的 payload」。

#### Stage 2｜Chain vendor 韌性與資料時間揭露（C-1）

- **解哪個風險**：D5。全站中斷且無自動復原。
- **前置依賴**：**無**——★OD-05 第 3～7 條已把「使用者看到什麼」
  定完，001 版的裁示阻擋解除。
- **改 schema**：否（除非降級狀態要落盤）。
- **影響 production 行為**：**是**——使用者在 vendor 限流時看到的
  東西會不同（顯示上次成功結果＋資料時間＋stale 標示，而不是無差別
  的「抓不到報價」）。**這正是要做的事。**
- **範圍**（OD-05 逐條）：讀 HTTP status／honor `Retry-After`／
  `Retry-After` 期間拒絕重打／429 與一般失敗分層區分／前端顯示
  quote fetched time 與 stale／持續失敗顯示資料源異常。
  **順手**：更正 `data/cboe.py` docstring（補記它會 429）。
- **rollout／rollback**：backoff／circuit breaker 的參數應可調；
  circuit breaker 誤開會讓功能在 vendor 其實健康時仍不可用，因此
  **必須有手動 reset 或短的 half-open 週期**。

#### Stage 3｜Ownership boundary（A-1）

- **解哪個風險**：D1、D2。資料邊界 ＋ O(U²)→O(U)。
- **前置依賴**：**無**——★OD-04 已定「既有資料全歸現有 Owner」。
- **改 schema**：**是**（per-user 表加 owner 維度 ＋ backfill）。
- **影響 production 行為**：**在單人情境下應為零**——身分解析器固定
  回傳 solo owner，所有查詢結果與今天相同。這是這個階段的驗收判準。
- **⚠ OD-04 紅線**：完成 Stage 3 **不等於**取得 privacy。文件、
  commit 訊息、issue 一律不得寫成「已完成多使用者隔離／privacy」——
  正確措辭是「已建立 data boundary，authentication 尚未實作」。
- **rollout／rollback**：欄位先加成 nullable ＋ backfill ＋ 再設
  NOT NULL，三步可分開。查詢帶身分那一步是**行為改變點**，應有
  「單人情境下回傳集合與改動前逐位元相同」的回歸測試（比照本專案
  既有的 bitwise 凍結慣例）。
- **一併處理**：`provider_credentials` 的 per-user 化（F3）。

#### Stage 4｜Treasury 排程（OD-01）

- **解哪個風險**：D6。每市場日第一批使用者可能整輪逾時。
- **前置依賴**：**無**——★OD-01 已定形狀，且 Runtime 結論
  （無 Python background API）已確認 Cron 是可行路徑（§7.2／§8.2）。
- **改 schema**：否（填的是既有 `rate_cache`）。
- **形狀**：Vercel Cron → 專屬 refresh endpoint（主路徑）
  ＋ **保留**既有同步 refresh-on-miss（保底）
  ＋ 既有 7 天 stale fallback 與 `rate_note`／`stale` 揭露（降級）。
- **⚠ 明確禁止**：拿掉同步 refresh-on-miss。Hobby cron 一天只有一次
  機會、精度 ±59 分鐘，那一次失敗時保底路徑是唯一的救援（§7.2）。
- **影響 production 行為**：正常情況下使用者不再承擔 cold fetch；
  排程失敗時使用者拿到「上一個有效市場日 ＋ 明確標示」。
- **rollout／rollback**：Cron 可單獨停用，停用後退回今天的純
  cache-aside 行為，零風險。

#### Stage 5｜〔決策閘門〕Chain 跨 request 共用要不要做

- **不是施工 stage，是一個明確的停等點。**
- **輸入**：Stage 0 的量測數字（chain fetch count／429 count／
  同 symbol 重複率）＋ ADR-0001 要求的「同時計入新增往返成本」的比較。
- **已經不需要再問 Owner 的**：freshness 窗長（OD-05 已定 **30 秒**）、
  手動 Refresh 是否繞過（OD-05 已定 **不繞過**）。
- **輸出**：`C-2: NEEDED`（附數字依據）或 `C-2: NOT_NEEDED / DEFERRED`。
- **gate 時應一併評估、ADR-0001 從未評估過的第三選項**：Vercel Edge
  CDN（§6.3）。
- **這個閘門必須有數字**，不接受「感覺應該要做」。

#### Stage 6｜Chain 30 秒共用窗（條件式，僅當 Stage 5 判定 NEEDED）

- **前置依賴**：Stage 0（證據）、Stage 3（§5.5 的 source 約束）、
  Stage 5（閘門）。
- **改 schema**：視選型（Edge CDN ＝ 否；Postgres ＝ 是）。
- **約束**：只涵蓋預設來源（Cboe）；鍵含 `(symbol, source)`；
  窗長 30 秒；**必須同時顯示 quote fetched time**（OD-05 第 3 條，
  與第 1、2 條是一組）。
- **rollout／rollback**：窗長應可調到 0（＝停用共用），作為即時
  rollback 手段。

#### Stage 7｜Authentication / identity binding（A-2）

- **解哪個風險**：**真正開放註冊之前的最後一塊——也是 privacy 唯一
  的來源**（OD-04）。
- **前置依賴**：Stage 3。
- **本文不展開設計**——它是產品功能，不是 scaling foundation。

---

### 10.3 Minimum Foundation vs Deferred

| 分級 | 項目 | 理由 |
|---|---|---|
| **NOW** | Stage 0 最小量測 | 沒有它，chain gate 永遠只能猜 |
| **NOW** | **Stage 1-0 拆 seed** | ★本輪新增。**任何 storage 瘦身的不可跳過前置**（F5） |
| **NOW** | Stage 1-1～1-5 storage 遷移 | **U=1 就會撞牆**（約 40 次刷新） |
| **NOW** | Stage 2 Cboe 429 韌性＋資料時間揭露 | 後果是全站中斷且無自動復原，與 U 無關。★OD-05 已解除阻擋 |
| **NOW** | Stage 4 Treasury 排程 | ★OD-01 已定形狀；且 Hobby 就做得到 |
| **NOW** | 順手更正 7 處過時的「60 秒硬上限」與 ADR-0001「無共享記憶體」 | 廉價；不更正會讓後續設計沿用錯誤前提（措辭見 §8.6） |
| **BLOCKED_ON_OWNER** | Stage 1-6 不可逆 cleanup／retention | 需要 §9-Q1（seed retention）與 §9-Q2（走勢圖範圍／時間窗） |
| **BEFORE_MULTIUSER** | Stage 3 ownership boundary（A-1） | 資料邊界 ＋ O(U²)。**開放多使用者的絕對前置** |
| **BEFORE_MULTIUSER** | `provider_credentials` 的 per-user 化（F3） | 一個人的 token／配額被所有人用 |
| **BEFORE_MULTIUSER** | **Stage 7 auth（A-2）** | **★OD-04：沒有它就沒有 privacy**，不是可選的產品加分項 |
| **AT_1K** | Stage 5／6 chain 30 秒共用窗（若閘門判定 NEEDED） | 研究 §7.5：高重疊情境下約 **U≈430** 才是絕對請求數的交叉點 |
| **AT_1K** | Dividend／chain 的 single-flight | 在此之前 stampede 是低機率、低後果事件；OD-01 之後 Treasury 這一側的價值又更低（§8.3） |
| **LATER** | Hot-symbol cron warming | 需要 Pro；且是延遲優化不是容量修復 |
| **LATER** | Redis／KV／distributed lock | 在證明 Postgres 不夠之前是 overengineering |
| **LATER** | snapshot 移出 Postgres 到 object storage | 新增 vendor 與 failure domain。⚠ 但 OD-02 把 snapshot 升級成必須長期保存的 seed 之後，這一項的價值上升——**若 §9-Q1 選「全部永久保留」，它會提早變成真問題** |
| **LATER** | 多 region | 上游都在美東，單 region 是對的 |
| **獨立線** | Yahoo → 其他 dividend provider | 合規／治理決策，需要自己的 vendor 研究 |
| **獨立線** | Market Data App 自訂 chain 成本揭露（研究 P1-5） | 產品揭露問題，非 scaling |

---

## 11. Failure Domains

【覆核程式碼推導；OD-01／OD-05 已改變其中兩列的目標狀態】

| 壞掉的東西 | 讀舊資料 | 重新計算 | 使用者看到（今天） | 缺口／目標態 |
|---|---|---|---|---|
| **Cboe（429／down）** | ✅ 可以（結果在 Neon） | ❌ 禁止——沒有報價 | 「抓不到報價」＋卡片保留舊結果（REPAIR-05 兩態） | ⚠ **沒有 backoff → retry storm**；訊息無差別，看不出是限流。**目標態由 OD-05 第 3～7 條定義**（Stage 2） |
| **Treasury down** | ✅ | ✅ 可以——7 天陳舊備援 → 固定 4% ＋ 揭露 | 分析照常完成，參數行標示來源 | ✅ 設計良好。**OD-01 之後再加一層**：排程主動填，使用者正常不碰上 cold fetch |
| **Treasury 排程失敗（OD-01 之後的新 domain）** | ✅ | ✅ 由同步 refresh-on-miss 保底 | 當天第一個使用者多等一次；或用上一個市場日＋stale 標示 | ⚠ **Hobby 一天只有一次排程機會**——保底路徑因此不可移除（§7.2） |
| **Dividend down** | ✅ | ⚠ 可以，但降級到 **q=0** | 分析照常完成，`q_note` 標示 | ⚠ q=0 是**已知錯很多**的值（見 §12）。「照常完成」是否正確？ |
| **Market Data（自訂）down** | ✅ | ✅ 自動退回預設來源，並記一次驗證失敗 | 設定頁自己變成「驗證失敗」＋原因 | ✅ 設計良好，無靜默退回 |
| **Neon down** | ❌ **完全不可用** | ❌ | 全站失敗 | ⚠ **無任何降級**。foundation 階段是否要處理？判斷：**不要**——資料庫是 single point of truth，為它做降級的複雜度遠超收益 |
| **快取層自己壞掉**（讀寫失敗） | — | ✅ 視同無快取，直接打上游 | 無感 | ✅ 三個快取層都已經這樣做 |

**推導出的兩個 foundation 要求**：

1. **必須寫下來**：哪些功能在哪個 vendor 掛掉時降級到什麼程度。
   今天這些行為是「程式碼裡碰巧是這樣」，不是「我們決定要這樣」。
   **OD-05 已經替 Cboe 這一列寫下來了**；其餘各列仍是隱性的。
2. **Dividend 的 q=0 降級需要一次有意識的裁決**——是繼續照常完成
   （現狀，有揭露），還是應該拒絕給出可能錯很多的數字？
   ⚠ 這一題本文**不列入 Owner Decisions**，因為它是 valuation 語意
   問題、不是 scaling 問題，應該另外處理。這裡只負責指出它存在。

---

## 12. Correctness vs Optimization 分類

> **這張表決定了「什麼可以延後」。** ⚠ 依 OD-04，ownership 那兩列的
> 分類已修正——它們是 **data-boundary correctness**，**不是** privacy。

| 項目 | 分類 | 說明 |
|---|---|---|
| user ownership（查詢帶身分） | **data-boundary correctness** | 今天 B 能改 A 的劇本。⚠ **本身不提供 privacy**（OD-04） |
| authentication／identity binding（A-2） | **privacy 的唯一來源** | ★OD-04：沒有它，`owner_id` 只是一個欄位 |
| 開站不刷新別人的劇本 | **correctness** | 不只是浪費——它在改別人的資料 |
| `provider_credentials` per-user | **成本正確性 ＋（A-2 之後的）privacy** | 一個人的付費配額被所有人用 |
| **拆 seed（Stage 1-0）** | **correctness 的前置** | ★本輪新增：不先拆，之後的瘦身會毀掉重建能力（F5） |
| `results` storage lifecycle | **capacity**（硬牆） | 約 40 次刷新就滿 |
| **snapshot 保存（seed）** | **capacity ＋ 不可逆的能力邊界** | ★OD-02 之後升級：它是其他一切「可重建」宣稱的基礎（§3.3-L3） |
| `/results` 不讀整份 view | **capacity ＋ latency** | 讀 365 MiB 只為了拿時間戳 |
| Cboe 429 不 retry storm | **correctness** | 自己把中斷延長 |
| Cboe 429 有降級路徑＋資料時間揭露 | **capacity（可用性）＋ 誠實性** | ★OD-05 已定目標態 |
| chain 30 秒共用窗 | **capacity optimization** | **不是 correctness**——今天每次抓新的，語意上是對的。OD-05 定了參數，不等於定了施工 |
| Treasury 排程（OD-01） | **latency，且會升級成 correctness** | 45s 預算 vs 45s 最壞，可能整輪逾時 |
| Treasury／Dividend single-flight | **capacity optimization**（收益極小，OD-01 之後更小） | 期望值 2–3 次/日 |
| Dividend q=0 降級 | ⚠ **correctness 疑慮** | 研究實測 q=0 讓某格從 −11.5% 變成 +81.9%。今天有揭露（`q_note`），但這是**降級到一個已知很錯的值** |
| snapshot 移到 object storage | **cost optimization** | 延後（但見 §10.3 的但書） |
| Redis／distributed lock | **capacity optimization** | 延後 |

---

## 13. 一頁總結

```
        ┌────────── NOW（五項，彼此獨立、可平行）──────────────────────┐
        │  Stage 0    最小量測        ← 沒有它，chain gate 永遠在猜     │
        │  Stage 1-0  拆 seed  ★新增  ← 任何瘦身的不可跳過前置（F5）    │
        │  Stage 1-1..1-5  storage 遷移（dual-write→parity→切讀→驗證   │
        │                              →停舊寫），OD-03 六步的前五步   │
        │  Stage 2    429 韌性＋資料時間  ★OD-05 已解除阻擋             │
        │  Stage 4    Treasury 排程       ★OD-01（Cron＋同步保底）      │
        │  （順手）更正 7 處「60 秒硬上限」與 ADR-0001「無共享記憶體」  │
        └───────────────────────┬───────────────────────────────────────┘
                                │
        ┌────────── BLOCKED_ON_OWNER ───────────────────────────────────┐
        │  Stage 1-6  不可逆 cleanup／retention                         │
        │             ← 需要 §9-Q1（seed 留多久，唯一不可逆的一題）      │
        │             ＋ §9-Q2（走勢圖範圍與時間窗）                    │
        └───────────────────────┬───────────────────────────────────────┘
                                │
        ┌────────── BEFORE_MULTIUSER ───────────────────────────────────┐
        │  Stage 3  ownership boundary（A-1）                           │
        │           └→ provider_credentials per-user                    │
        │           └→ refresh scope 自然收斂 O(U²) → O(U)              │
        │  Stage 7  authentication（A-2）★privacy 的唯一來源，非可選     │
        └───────────────────────┬───────────────────────────────────────┘
                                │
        ┌────────── AT_1K（條件式）─────────────────────────────────────┐
        │  Stage 5  〔閘門〕chain 共用要不要做  ← 需要 Stage 0 的數字    │
        │           窗長 30 秒已由 OD-05 定，gate 決定的是「做不做」     │
        │  Stage 6  chain 30 秒共用窗（僅當閘門 NEEDED）                 │
        │           約束：只涵蓋預設來源；鍵含 source；必須顯示資料時間  │
        └───────────────────────────────────────────────────────────────┘

        LATER：cron warming、Redis／lock、object storage、多 region
        獨立線：Yahoo 替換（合規）、Market Data 成本揭露（產品）
```

**Storage 分層一句話**：

```
永久：使用者輸入 / raw snapshot(seed) / 估值輸入+provenance+version /
      events / 走勢圖的四欄窄事實
短期：歷史 view 的完整內容（可由 seed re-analysis 取回）
不動：current view 的一切（OD-03 紅線）
```

---

## 14. 內部一致性稽核（本輪要求的交付項）

### 14.1 001 版與 Owner Decisions 衝突之處——逐處已修正

| # | 001 版的說法 | 與誰衝突 | 本輪處置 |
|---|---|---|---|
| C1 | 001 版 §4.2「A-1 這一層解掉的是 correctness 與 **privacy**」 | **OD-04**（不得宣稱只有 owner_id 就完成 privacy） | ✅ 已改寫（§5.3）：A-1 建立的是 data boundary；privacy 只能來自 A-2。§12 分類表同步修正 |
| C2 | 001 版 §3.4「只保留每個劇本**最新一次**快照」列為可選項 | **OD-02**（snapshot 是不可重建的 seed）＋ 本輪 F6 | ✅ **該選項已作廢**（§3.4、§9.0）。snapshot 改列 L0 必須保存 |
| C3 | 001 版 §3.2「B1-b：存投影後的形狀」未說明它會毀掉歷史查詢 | **OD-03**（禁止刪除 production 依賴的 payload） | ✅ 已改寫成 OD-03 六步（§3.6／Stage 1），並明列 `all_candidates` 今天真的被 `spread_cost_history()` 依賴 |
| C4 | 001 版 §6.2 建議「stale-while-revalidate 收益/風險比最好」，可行性掛在未查證的背景執行機制上 | **Runtime 結論**（Python 無 `waitUntil`）＋ **OD-01** | ✅ 已改寫（§7.2）：形狀換成 Cron 主動填 ＋ 同步 refresh-on-miss 保底 |
| C5 | 001 版 §5.2「C-1 的前置依賴＝Owner 對『使用者看到什麼』的裁示」 | **OD-05 第 3～7 條** | ✅ 阻擋解除（§6.1／Stage 2），C-1 改列 NOW |
| C6 | 001 版 §9-Q3／Q4 整題待裁示 | **OD-05** | ✅ 已從 unresolved 移除（§9.0） |
| C7 | 001 版 §7.5「fluid compute 下 Hobby default 與 maximum 都是 300s」的斷言語氣 | **Runtime 結論**（fluid 是否啟用 NOT_CONFIRMED） | ✅ 已改寫更正措辭（§8.6）：不宣稱上限是 300s，而是說明它取決於一個未確認的開關 |
| C8 | 001 版 §2 D3「`results`／`snapshots` 有明確 lifecycle，成長速率可預測、有上界」 | **OD-02**（snapshot 升級為必須保存的 seed，成長不再有自然上界） | ✅ D3 已重寫（§4）：成長 = seed ＋ 常數量級窄事實；「有上界」只對 derived 成立 |

### 14.2 剩餘的張力（誠實揭露，不是矛盾但值得知道）

1. **OD-02 與 Neon Free 額度之間有一個真實的張力**：把 derived 換成
   seed 之後成長率降到約 1/25，但 seed 本身仍是每次刷新 0.48–2.55 MiB
   的硬成長，且**不可逆**。若 §9-Q1 選「全部永久保留」，Neon Free
   在 TLT 約 1,000 次／SPY 約 200 次刷新後仍會滿——只是把撞牆時間
   往後推了一個數量級，沒有消滅它。**這不是 OD-02 的缺陷，是誠實的
   算術**，Owner 應在回答 Q1 時知道。
2. **current view 是常數項而非成長項，但在 0.5 GB 的額度下不可忽略**
   （每劇本一份 12.18 MiB，OD-03 禁止縮減其內容）。若成為瓶頸，
   正確的解是**壓縮**（zlib-6 實測 9.6×），不是縮內容（§3.7）。
3. **`engine_version` 只是標籤**——re-analysis 可行、reproduction
   不可行（§3.3-L1）。spec 階段必須逐處指明用的是哪一種語意。

### 14.3 判定

| 問題 | 答案 |
|---|---|
| 是否已無內部矛盾？ | ✅ **是**——§14.1 的八處衝突全部已修正；§14.2 的三項是誠實揭露的張力（帶數字、有處置方向），不是自相矛盾的敘述 |
| 是否 READY_FOR_SCALING_SPEC？ | ✅ **是** |

**READY_FOR_SCALING_SPEC 的理由（不是憑感覺）**：

1. **五個 NOW 項目全部沒有 blocking Owner Decision**（Obs／
   Stage 1-0／Stage 1-1..1-5／Stage 2／Stage 4）——OD-01／OD-04／
   OD-05 各解除一個原本的阻擋。
2. **唯一被未決事項擋住的是 Stage 1-6**，而 OD-03 自己把它排在
   **六步的最後一步**——所以它擋施工尾端，不擋 spec 撰寫，也不擋
   前五步。
3. **OD-02 要求的「必須先證明 deterministic reconstruction」已經
   在本輪完成**（§3.2 逐項稽核 ＋ §3.3 三個限制），而且該證明的
   結論**已經反過來改變了施工順序**（新增 Stage 1-0）——這正是委託
   要求的「不可硬套 OD-02」。

> **給 spec 階段的三條硬前置**（不得遺漏）：
> 1. Stage 1-0（拆 seed）必須排在任何 storage 瘦身之前。
> 2. Stage 1-6（不可逆 cleanup）在 §9-Q1／Q2 有答案之前不得執行。
> 3. Stage 4 不得移除同步 refresh-on-miss 保底路徑。

---

## 15. 本輪（002）的限制（誠實揭露）

1. **沒有新增任何量測。** 本輪是 reconciliation，依委託不做第三輪
   研究。所有數字皆引用自三份研究文件，或本輪對 production code 的
   靜態覆核。
2. **§3.7 的「目標態約 0.5 MiB／次」是推估**，不是實測——L2 窄事實
   的實際列大小未量測；snapshot 的壓縮率未實測。
3. **§3.3-L2 的 96 秒是由 3.21s × 30 推算**（研究 M8 的單次時間是
   一手實測，乘法是推估），而且 3.21s 本身是 **q=0 快路徑**、
   不含逐腿 IV 反解校準——真實重建走的是完整校準路徑（既有量測
   7.543s，REPAIR-03／#240），再加上 Neon 讀取與反序列化。
   **所以 96 秒是下界，不是上界**，實際只會更慢。
4. **§10.3 的 NOW／BEFORE_MULTIUSER／AT_1K 分級含判斷成分**，界線是
   依「風險在哪個 U 開始咬人 ＋ 誰擋住誰」推導的，不是量測出來的。
   Owner 可以推翻任何一格。
5. **Fluid compute 開關狀態仍是 NOT_CONFIRMED**（§8.1）。它不影響
   任何結論，只影響 §8.6 更正措辭的精確度。
6. **本輪沒有替 ADR-0001 做決定。** OD-05 明文保留 evidence gate，
   本文遵守——Stage 5 是一個真實的停等點，不是形式。
7. **`docs/research/*` 的 P0/P1/P2 分級與本文的 NOW/BEFORE_MULTIUSER/
   AT_1K 分級不是同一套坐標**。研究依「多嚴重」分，本文依「什麼時候
   會咬人 ＋ 誰擋住誰」分。兩者對同一個項目可能落在不同格子，這是
   刻意的。

---

READY_FOR_SCALING_SPEC
