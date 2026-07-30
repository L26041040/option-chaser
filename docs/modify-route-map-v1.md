# Option Chaser 重構路線圖 v1

需求來源：`docs/modifyRequestV1.md`（本輪唯一產品需求來源，內容未重新整理或擴寫）。
本文件為定向程式碼勘查結果，非全 repository 掃描；追蹤路徑：`webapp/app.py` /
`webapp/pages/0_劇本工作區.py`（入口）→ `option_chaser/{service,store,workspace,
models,ranking,valuation,scenarios,matrix}.py`（被前述檔案實際 import 到才追）→
`webapp/render.py`（被 app.py / 0_劇本工作區.py import）。未修改任何程式碼。

---

## 1. 總結判斷：TARGETED_REFACTOR（針對性重構）

證據：

- 核心估值引擎已經正確處理到期前時間價值：`option_chaser/valuation.py:81-89`
  `scenario_leg_value()` 對 `at < expiry` 呼叫 `clamped_price()`（Black-Scholes +
  美式下限），只有 `at >= expiry` 才退回 `intrinsic_value()`；`spread_scenario_value()`
  （`valuation.py:195-202`）組合兩腳並鉗制在 `[0, width]`。這正是文件第四節要求的
  「不可把到期 payoff 公式套用到所有 Heatmap 日期」，且已經是這樣做。
- `option_chaser/matrix.py:60-68` `matrix_grid()` 對每一個 (price, date) 格子各自呼叫
  `value_fn`，不是整張表套一條到期公式。
- `option_chaser/store.py` + `option_chaser/workspace.py` 的事件溯源設計
  （`events.jsonl` 唯一事實來源、`scenarios/<id>.json` 投影快取、`groups.json`
  全量可重建、`results/<id>/<ts>.json` 逐次快照）已是成熟架構，足以承載文件第八、
  第十節的保存需求。
- 缺口集中在呈現層聚合（跨到期日 Top10、資料狀態燈號、Spread 獨立歷史查詢）、
  輸入層欄位（年月合併輸入、桌面 20/80 版面、卡片精簡）、一項全新但高度可重用的
  計算（Long Call 追平比較）、以及一個具體數值錯誤（Heatmap 超標僅 +10%，文件要求
  ≥15%）。這些都是在既有模組邊界內新增/局部修改函式與呼叫點，不需更動
  valuation/matrix/store 的資料結構或演算法本體。

→ 不構成 PARTIAL_REWRITE 或 FULL_REBUILD 的條件（見第 8 節停止條件供對照）。

---

## 2. 需求覆蓋矩陣（逐節對照 `docs/modifyRequestV1.md`）

**一、產品目的** — 已完成。`AnalysisRequest`/`AnalysisParams`
（`option_chaser/models.py:46-61`）只吃 target_price/target_date，全 repo 找不到
價格預測邏輯。

**二、首頁與輸入方式**
- 左 20%／右 80% 桌面版面 — 缺少。`webapp/pages/0_劇本工作區.py` 全部用
  `st.subheader` 由上到下排列（設定區 L58 → 建立表單 L69 → 清單區 L122 →
  群組區 L205 → 詳頁 L257），沒有 `st.columns([0.2, 0.8])`。
- 免登入直接進首頁 — 已完成。`app.py`/`0_劇本工作區.py` 皆無 auth 相關程式碼。
- 新增劇本只問 3 欄 — 實作錯誤。`0_劇本工作區.py:69-114` 建立表單多要求
  「方向」（`ws-new-direction`, L81）與「策略勾選」（`ws-new-chk-*`, L92-93），
  且「預計年月」用 `st.date_input`（L94，精確到日）而非年月合併輸入。
- 年月合併輸入＋格式正規化（2028/1、2028/01、28/1、28/01） — 缺少。全 repo
  grep 找不到對應正規化函式。
- 不需輸入到期日／買入履約價／賣出履約價／Spread 寬度 — 已完成。這三項在
  `_spread_result()`（`service.py:432-475`）由系統窮舉決定，UI 與
  `AnalysisRequest` 都不含這些欄位。

**三、到期日探索與 Spread 排名**
- 探索目標月份附近約 5 個代表到期日 — 部分完成。`service._sample_expiries()`
  （`service.py:278-293`）是「先窮舉全部未來到期日→事後取樣最多 4 個供分組
  *顯示*」，數量上限是 4 非 5，且順序與文件描述（先選 5 個代表到期日→只窮舉
  這 5 個）相反。文件本身允許「具體挑選方式列為後續研究事項」，故不判定為錯誤。
- 窮舉這些到期日中符合條件的 Call Debit Spread — 已完成。`bull-call-spread`
  即文件所稱 Call Debit Spread（`models.py:79` `SPREAD_STRATEGIES`），
  `_spread_result()` 對同到期日內所有多空腳配對呼叫 `evaluate_spread()`。
- 排名情境（目標價、持有至到期、相對淨支出 %） — 已完成。
  `ranking.py:110-111` `spread_baseline_return = (baseline_value - net_mid) /
  net_mid`，`baseline_value` 即 shift=0 情境下 `spread_scenario_value(...,
  target_date, ...)`。
- 跨到期日總排名 Top10 — 缺少。`rank_spreads()`（`ranking.py:120-122`）排序後
  只取 `p.top`（預設 3，`models.py:51`）筆建成 `CandidateView`；`ranked_spreads`
  本身雖是全域排序（`service.py:445`），但沒有任何 UI 把它攤平成 Top10 榜單
  （`render.py:206-250` `render_step3` 是依到期日分組的表格）。
- 各到期日最佳結果 — 已完成。`_spread_result()` 內 `best_by_expiry` 迴圈
  （`service.py:453-468`）+ `_build_groups()`（`service.py:296-383`）已產出。
- 各到期日最佳結果需附 Heatmap 縮圖 — 已完成。`render.py:90-103`
  `_thumb_html()` 用 `matrix.thumbnail_cells()`，`render_step3` 每列呼叫。

**四、Heatmap**
- 每個排名結果有自己的 Heatmap — 已完成。`_spread_view()` 呼叫 `_matrix_view()`
  （`service.py:149-157`）為每個 `CandidateView` 各自建表。
- 點擊查看詳細 Heatmap — 已完成。`render_step2` + `st.session_state` 選中機制
  （`app.py:35-42`、`0_劇本工作區.py:266-274`）。
- 正確呈現到期前時間價值，不可套用到期 payoff 公式 — 已完成（核心正確，見
  第 1 節證據）。`tests/test_matrix.py`、`tests/test_spread_valuation.py` 有
  覆蓋。
- 價格範圍需延伸至目標價以上至少 15% — 實作錯誤。`matrix.py:23`
  `overshoot = target * (1.10 if bullish else 0.90)`，只有 +10%。
  `tests/test_matrix.py:36,47,68,76` 把 1.10/0.90 寫死斷言，證實是目前設計值
  而非筆誤，修改需連測試一起改。
- 修正不得改變排名公式 — 現況未違反：排名用 `spread_baseline_return`，與
  `matrix.py` 的價格軸無耦合。

**五、劇本卡片**
- 緊湊卡片（標的/目標價/年月/最高目標達成收益率/單一燈號） — 實作錯誤。現況
  `0_劇本工作區.py:127-161` 是多欄位表格列（標的/方向/目標價/目標日/生命週期
  badge/佔本金%/含完整 Spread 腳資訊與情境最壞數字的摘要行，見 L156-159），
  牴觸文件「卡片不應塞入完整 Spread 腿資訊/長篇說明/大量技術數字」的要求。
- 收益正綠負紅 — 缺少。收益數字（`0_劇本工作區.py:159`）以純文字 markdown
  顯示，`render.py`/`0_劇本工作區.py` 都沒有依正負值上色的卡片級邏輯
  （`cell_color()` 是 Heatmap 專用函式）。
- 點卡片進詳細頁 — 已完成。「詳頁」按鈕（L168-170）+ 詳頁區塊（L257-275）。

**六、資料狀態燈號（綠/黃/紅，紅優先）** — 缺少。現況只有生命週期 badge
（`STATUS_BADGE`, `0_劇本工作區.py:20-21`：🟢Active/🏁Reached/⌛Expired/
❌Invalidated），語意是使用者手動或到期判定的生命週期，不是文件定義的
「綠=成功取得最新報價並完成重新分析／黃=報價 API 連不上、顯示上次成功結果／
紅=劇本年月已過期，優先於報價連線狀態」。Repo-wide grep 除此 badge 外找不到
其他相符實作。

**七、動態更新（開站自動更新所有未過期劇本，單一失敗不擋其他）** — 缺少。
`workspace.analyze_scenario`/`analyze_group`（`workspace.py:163-198`）都是
「使用者按下『分析』/『群組分析』按鈕」觸發（`0_劇本工作區.py:163-167,
250-253`），頁面載入的 top-level 程式碼沒有任何自動迴圈呼叫。「單一失敗不擋
其他」的例外隔離語意已存在於 `_analyze_with_status()`
（`0_劇本工作區.py:43-53` 的 try/except），只是還沒被包進「開站對所有 Active
劇本迴圈呼叫」的邏輯。

**八、Spread 詳細頁與歷史**
- 詳細頁顯示劇本摘要/各到期日最佳/被選 Spread 的詳細 Heatmap — 部分完成。
  `render_summary`/`render_step2`/`render_step3`/`render_step4` 都已存在且被
  詳頁區塊呼叫（L265-275），但「跨到期日 Top10」如第三節所述不存在。
- Spread 身份（標的+到期日+買入履約價+賣出履約價） — 已完成。
  `service.py:258-263` `candidate_key()` 用 strategy（隱含標的方向）+
  `long_leg.strike` + `short_leg.strike` + `long_leg.expiry` 組成穩定 id。
- 同一 Spread 排名升降/掉出/重進 Top10 都延續同一份歷史 — 缺少。
  `store.save_result()`（`store.py:378-383`）每次分析把整份 view 存成新的
  timestamp 檔案；`candidate_key` 雖穩定，但沒有函式依 `candidate_key` 跨多個
  歷史快照檔案抽取單一 Spread 的時間序列。若某次分析該 Spread 掉出 top-3 且
  不是任何到期日最佳，該次快照甚至不含它的資料點，歷史會出現斷點。現有
  `events.jsonl` + `results/<id>/<ts>.json` 檔案配置本身可支撐（欄位都在，只
  是缺查詢函式），不需改資料格式。
- 每次成功更新至少保存更新時間/標的價格/建倉淨成本/收益率/當時排名 — 部分
  完成。`store._candidate()`（L256-307）已存 `mid_cost`/`baseline_return`/
  `candidate_key`，快照檔名即 `fetched_at`（`store.py:380`），`meta.spot`
  （L360-363）即標的價格；但「當時排名」沒有獨立欄位——只能靠 candidate 在
  `candidates` 陣列的 index 間接推得，而該陣列只留 top-3，不在 top-3 但在
  `expiry_best` 的候選無法得知全域排名。與第三節 Top10 缺口直接相關。

**九、Long Call 比較** — 缺少，但有高度可重用基礎。Repo-wide grep 找不到「Long
Call 需用多少價格買入才能追上 Spread 報酬」的計算或 UI。但
`valuation.py:127` `l3 = baseline_value / (1.0 + p.min_return)` 這行公式，
形狀與文件要求完全相同（用「目標情境估值 / (1+目標報酬率)」反推成本上限）；
只要把 `p.min_return` 換成「所選 Spread 的 `baseline_return`」、
`baseline_value` 換成同到期日 Long Call 的 `baseline_value`，就是文件要的
比較數字。CLI 既有 `guidance_judgments()`（`valuation.py:137-149`）已在用
同一族公式做「買價天花板」提示。故此為新增一個小函式 + 一個 UI 區塊，不是
新建估值引擎。

**十、劇本保存** — 結構層面已完成，功能完整度受限於第六、八節缺口。
`workspace.py`+`store.py` 的 event-sourcing 設計完整支援劇本輸入
（`store.Scenario` dataclass）、最近一次有效結果（`workspace.latest_result`）、
Spread 身份（`candidate_key`）。但「狀態燈號」（第六節）與「Spread 收益率
歷史查詢」（第八節）缺的不是保存層（`store.py`），是聚合/查詢層
（`workspace.py`）還沒補上對應函式。

**十一、手機版與 UI 實作原則** — 證據不足，列入第 6 節待調查。`app.py:56-68`
有 mobile CSS 近似處理的註解與 `.oc-thumb`/`.oc-num` class，顯示已有窄螢幕
最小調整意圖，但未經實機或 viewport 模擬驗證是否真的完整可操作；
`0_劇本工作區.py` 的多欄 `st.columns([1.0, 0.7, ..., 2.2, 1.8])` 在窄螢幕如何
reflow 也未驗證。依文件「不要只因外觀不理想就判定整個前端重寫」的原則，現況
初步評估為「可簡化/局部替換」，但最終結論需要下一階段實機驗證。

**十二、未來 Agent API 邊界** — 已完成（邊界本身已存在）。`app.py:1-12`
docstring 與 `service.py` 開頭註解明確聲明「GUI computes NO financial
formulas — every displayed number comes from service」；`render.py`/
`app.py`/`0_劇本工作區.py` 都只消費 `store.serialize_result()` 產出的 dict，
唯一例外是 `render.py:288-299` `_pareto_frontier()` 與 SVG 座標映射，屬幾何
呈現非金融計算（程式碼註解本身點名此例外）。`service.run()` /
`service.AnalysisRequest` 已是乾淨、可版本化的計算層 API 雛形。

**十三、本輪不包含** — 現況檢查：既有程式碼已支援 `long-put`/
`bear-put-spread`（`models.py:77-79`）與 Delta 分級（`ranking.py`）等超出
MVP 範圍的功能；不需移除，只需在新首頁流程中不曝露/不強制使用者選擇即可
（保留程式碼，新流程預設帶入 bullish + bull-call-spread）。

---

## 3. Keep / Modify / Remove / Add

**保留（不動）**
- `option_chaser/valuation.py` 全部 — 已正確，是 Heatmap/排名的地基。
- `option_chaser/scenarios.py` 全部 — 本輪未要求變更 7 情境向量/completion curve。
- `option_chaser/store.py` 的事件溯源機制（`append_event`/`read_events`/
  `reconcile_status`/`rebuild_groups`）— 架構已達標。
- `option_chaser/ranking.py` 全部。
- `option_chaser/service.py` 的 `_analyze`/`_single_leg_result`/
  `_spread_result` 主流程。

**修改（局部）**
- `option_chaser/matrix.py:23` — overshoot 倍率 1.10→至少 1.15（連動
  `tests/test_matrix.py:36,47,68,76`）。
- `webapp/pages/0_劇本工作區.py` 建立表單（L69-114） — 移除方向/策略勾選欄位，
  改為 3 欄輸入 + 年月合併框。
- `webapp/pages/0_劇本工作區.py` 清單區（L122-202） — 表格列改為緊湊卡片，
  加入正負色與單一燈號。
- `webapp/pages/0_劇本工作區.py` 版面配置 — 加入 `st.columns([0.2, 0.8])`
  左右分割（桌面）。
- `option_chaser/service.py` `_build_groups`/`_sample_expiries`
  （L278-383） — 新增跨到期日 Top10 聚合（可新增獨立函式與既有分組邏輯並存，
  不必互斥）。
- `option_chaser/store.py` `_candidate()`（L256-307） — 新增「當時排名」欄位。

**新增**
- 年月輸入解析/正規化函式（建議 `option_chaser/models.py` 或新檔） — 處理
  2028/1、2028/01、28/1、28/01。
- 資料狀態燈號計算函式（建議加入 `workspace.py`，依賴既有
  `analyze_scenario` 成功/失敗與 `list_scenarios` 的 Expired 判定）。
- Long Call 追平比較函式（建議加入 `option_chaser/scenarios.py` 或新模組，
  重用 `valuation.py` 的 `l3` 公式形狀）。
- Spread 歷史查詢函式（依 `candidate_key` 跨 `results/<id>/*.json` 聚合時間
  序列，建議加入 `workspace.py`）。
- 開站自動更新迴圈（建議加入 `0_劇本工作區.py` 頁面載入區塊）。
- 跨到期日 Top10 的 UI 渲染（建議加入 `webapp/render.py`）。

**移除/隱藏（不刪除底層邏輯）**
- 首頁不應曝露的 UI 輸入：方向選擇（L81）、策略勾選（L92-93） — 隱藏/
  預設化，底層 `strategies` 參數保留供未來使用。
- 不因底層已支援 Put/Bear-Put-Spread 而在首頁新增對應 UI（維持現狀，不算
  移除，只是不擴大）。

---

## 4-5. 最短安全施工路線圖

**Step 0 — Heatmap 價格範圍修正**（獨立、風險最低、無依賴）
- 檔案：`option_chaser/matrix.py`（`price_axis`），`tests/test_matrix.py`
- 驗證：`pytest tests/test_matrix.py tests/test_spread_valuation.py
  tests/test_matrix_grid.py`
- 不得順便改動：排名公式（`ranking.py`）、`date_axis`、`matrix_grid` 估值邏輯本身

**Step 1 — 年月合併輸入與正規化**（輸入層，阻塞後續首頁改版）
- 目標：新增年月解析函式，支援 4 種格式；需先確認「年月代表哪一天」的映射
  慣例（文件未指定，見第 6 節）
- 檔案：新增解析函式（`option_chaser/models.py` 或新檔），
  `webapp/pages/0_劇本工作區.py` 建立表單欄位替換
- 驗證：新增單元測試（4 種格式→相同標準化年月）；確認
  `tests/test_workspace.py`/`tests/test_scenarios.py` 不受影響
- 不得順便改動：`AnalysisParams` 資料結構（仍為 YYYY-MM-DD 字串）、
  `service.py` 分析主流程

**Step 2 — 首頁建立表單簡化**（依賴 Step 1）
- 目標：移除方向/策略勾選 UI，預設帶入 bullish + bull-call-spread
- 檔案：`webapp/pages/0_劇本工作區.py`（L69-114）
- 驗證：`tests/test_webapp_workspace.py` 既有測試更新對應 fixture；跑一次
  建立劇本流程
- 不得順便改動：`workspace.create_scenario()` 函式簽章與底層 `strategies`
  參數（保留不刪）

**Step 3 — 桌面 20/80 版面 + 劇本卡片重製**（依賴 Step 2）
- 目標：`st.columns` 左右分割、緊湊卡片（5 欄位+單一燈號位置）、收益正負色
- 檔案：`webapp/pages/0_劇本工作區.py` 版面與清單區
- 驗證：`tests/test_webapp_workspace.py`；手動截圖確認版面
- 不得順便改動：群組區/詳頁邏輯（L204-275 暫不動）

**Step 4 — 資料狀態燈號計算**（依賴 Step 3 有燈號 UI 位置）
- 目標：新增燈號計算函式（綠/黃/紅，紅優先），接上卡片
- 檔案：`option_chaser/workspace.py`（新函式），
  `webapp/pages/0_劇本工作區.py`（消費）
- 驗證：新增單元測試（模擬 `FetchError`→黃燈、Expired→紅燈、成功→綠燈、
  紅燈優先於黃燈情境）
- 不得順便改動：`analyze_scenario` 本身的分析邏輯，只讀取其成功/失敗結果

**Step 5 — 開站自動更新迴圈**（依賴 Step 4 燈號需要更新時機）
- 目標：頁面載入時對所有 Active 劇本呼叫 `analyze_scenario`，單一失敗不擋
  其他
- 檔案：`webapp/pages/0_劇本工作區.py` 頁面頂部
- 驗證：新增測試模擬多劇本其中一個 `FetchError`，確認其餘仍完成；建議先
  量測目前手動分析耗時，評估多劇本情境下頁面載入時間是否可接受
- 不得順便改動：`workspace.analyze_scenario`/`analyze_group` 函式本身

**Step 6 — 跨到期日 Top10 聚合**（可與 Step 4/5 平行，建議在卡片穩定後做以
降低 UI 變動衝突）
- 目標：新增跨到期日聚合函式（`service.py`），`render_top10`（`render.py`），
  詳細頁串接；`store.py` 補「當時排名」欄位
- 檔案：`option_chaser/service.py`、`option_chaser/store.py`、
  `webapp/render.py`、`webapp/pages/0_劇本工作區.py` 詳頁
- 驗證：新增測試（合成多到期日 spread 資料，驗證 Top10 正確合併排序）；確認
  `tests/test_spread_ranking.py` 無回歸
- 不得順便改動：既有依到期日分組的 `render_step3` 顯示（並存，不砍掉重練）

**Step 7 — Spread 獨立歷史查詢**（依賴 Step 6 的候選當時排名欄位）
- 目標：新增依 `candidate_key` 跨 `results/<id>/*.json` 聚合時間序列的函式
- 檔案：`option_chaser/workspace.py`，`webapp/pages/0_劇本工作區.py` 詳頁
- 驗證：新增測試（合成 3 次 `analyze_scenario` 產生 3 份快照，同一
  `candidate_key` 在其中 1 份缺席，驗證查詢函式正確回傳含斷點的時間序列而非
  報錯）
- 不得順便改動：`save_result` 的檔案格式

**可延後項目（依文件第九節，獨立於核心 MVP，不得混入 Step 0-7）**

**Step D1 — Long Call 追平比較**
- 目標：新增比較函式（重用 `valuation.py` 的 `l3` 公式形狀）+ 一個 UI 顯示
  區塊
- 檔案：建議 `option_chaser/scenarios.py` 新函式，`webapp/render.py` 新增
  顯示
- 驗證：新增單元測試（構造已知 Spread 報酬率，反推 Long Call 價格，驗證數學
  一致性）
- 明確不得因此延遲或擴大 Step 0-7 範圍

---

## 6. 尚未取得足夠證據、下一階段才需要深入調查的項目

- 手機版 UI 是否真的完整可操作（需瀏覽器/viewport 實測，非讀程式碼可判斷）—
  對應文件十一節。
- 年月合併輸入正規化後「代表哪一天」的映射慣例文件未指定（15 日？月底？
  到期日附近？），需與需求提出者確認，否則 Step 1 會卡在設計決策而非程式
  問題。
- Heatmap 的 IV 假設（逐腳固定 IV，不隨日期變動）是否需要對照
  optionsprofitcalculator.com 做進一步比對——README 已知揭露此為模型限制，
  但文件第四節明確要求「需要研究及比對」，本輪未實際跑該網站比對數據，只能
  確認「非到期 payoff 硬套」這個大方向是對的。
- `candidate_key` 在測試中的實際覆蓋範圍（`tests/test_service.py`、
  `tests/test_store_serialize.py` 等是否已驗證 Spread 身份跨快照穩定）——
  本輪只讀了原始碼定義，未逐一開啟這些測試檔案核對斷言內容。
- 目前「跨到期日全窮舉」（`_spread_result` 對整條 chain 窮舉所有未來到期日，
  而非文件建議的「先選 5 個代表到期日」）在真實市場資料（數十個到期日）下的
  效能與雜訊——是否需要在窮舉前先做到期日篩選而非只在顯示時取樣，需要效能
  量測佐證。
- `tests/test_webapp_workspace.py`/`tests/test_webapp_v4.py` 的 AppTest
  涵蓋範圍，決定 Step 2-3 改動 UI 時有多少既有測試需同步更新——本輪只確認
  檔案存在，未讀取內容。
