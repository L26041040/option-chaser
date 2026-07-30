# Option Chaser 重構路線圖 v1

需求來源：`docs/modifyRequestV1.md`（本輪唯一產品需求來源，內容未重新整理或擴寫）。
本文件為定向程式碼勘查結果，非全 repository 掃描；追蹤路徑：`webapp/app.py` /
`webapp/pages/0_劇本工作區.py`（入口）→ `option_chaser/{service,store,workspace,
models,ranking,valuation,scenarios,matrix}.py`（被前述檔案實際 import 到才追）→
`webapp/render.py`（被 app.py / 0_劇本工作區.py import）。未修改任何程式碼。

> 2026-07-30 獨立覆核更新：Step 0 已由 commit `5e6b1bb` 完成；修正一處
> `ranked_spreads` 證據錯誤（影響 Step 6 施工方式）；補上需求七.8
> 「依收益率重排卡片」的遺漏（併入 Step 5）。詳見
> `docs/modify-route-map-v1-review.md`。

> 2026-07-30 Grill 更新①：需求方確認到期日探索規則（六點，見
> `modifyRequestV1.md` §三與附錄A）與日期語意分離原則（附錄A2）。
> 據此：(1) §2（三）第一項改判「實作錯誤」——選取必須發生在窮舉之前；
> (2) §2（三）排名情境改判「實作錯誤」——估值日應為各 Spread 自身到期日，
> 非 `p.target_date`；(3) Step 1 改為解析年月＋計算日曆錨點，不映射單日；
> (4) 新增 Step 1-1／1-2。覆核報告中「建議月底映射」之建議作廢。

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
  計算（Long Call 追平比較）。原列的具體數值錯誤（Heatmap 超標僅 +10%，文件要求
  ≥15%）已由 commit `5e6b1bb` 修正（`matrix.py:23` 現為 1.15/0.85，
  `tests/test_matrix.py` 四處斷言與 golden fixtures 已同步）。其餘缺口都是在
  既有模組邊界內新增/局部修改函式與呼叫點，不需更動 valuation/matrix/store
  的資料結構或演算法本體。

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
  grep 找不到對應正規化函式。（2026-07-30 補註：解析目標是 (年, 月) 二元組
  ＋據此計算日曆錨點（第三個星期五），不是映射成單一 target_date；
  見附錄A2 日期語意分離原則。）
- 不需輸入到期日／買入履約價／賣出履約價／Spread 寬度 — 已完成。這三項在
  `_spread_result()`（`service.py:432-475`）由系統窮舉決定，UI 與
  `AnalysisRequest` 都不含這些欄位。

**三、到期日探索與 Spread 排名**
- 探索目標月份附近約 5 個代表到期日 — 實作錯誤（2026-07-30 改判，原
  「部分完成」的豁免依據「列為後續研究事項」已被需求方六點規則取代）。
  現況 `service._sample_expiries()`（`service.py:278-293`）是「先窮舉全部
  未來到期日→事後取樣最多 4 個供分組*顯示*」；規則要求「日曆錨點（目標月
  第三個星期五）→ baseline＝距錨點最近的實際到期日（同距取較晚）→
  baseline 前2後2共至多5檔（一側不足由另一側補）→ 只對這5檔窮舉，
  各自產生排名」。選取必須發生在窮舉之前，且窮舉範圍限縮至選取的5檔。
- 窮舉這些到期日中符合條件的 Call Debit Spread — 已完成。`bull-call-spread`
  即文件所稱 Call Debit Spread（`models.py:79` `SPREAD_STRATEGIES`），
  `_spread_result()` 對同到期日內所有多空腳配對呼叫 `evaluate_spread()`。
- 排名情境（目標價、持有至到期、相對淨支出 %） — 實作錯誤（2026-07-30
  改判，原「已完成」判定經定向核對推翻）。公式形狀正確
  （`ranking.py:110-111` `spread_baseline_return = (baseline_value -
  net_mid) / net_mid`），但估值時點錯誤：`evaluate_spread()`
  （`valuation.py:230,238-242`）把 baseline 定在 `p.target_date` 當天——
  對到期日晚於該日的 Spread，`scenario_leg_value()`（`valuation.py:86-89`）
  走 `at < expiry` 分支，帶入 BS 剩餘時間價值。需求 §三/§四明定
  「標的在該 Spread 到期時＝目標價、持有至到期」＝各 Spread 自身到期日
  的內在價值（附錄A2 第2點已確認此語意不使用共用日期）。到期日早於或
  等於估值日的 Spread 兩種算法重合，晚於者數字與名次都會不同。
- 跨到期日總排名 Top10 — 缺少。`rank_spreads()`（`ranking.py:120-122`）在
  回傳前就截斷至 `p.top`（預設 3，`models.py:51`），因此
  `StrategyResult.ranked_spreads` 只含 3 筆，且 `store.serialize_result()`
  完全沒有序列化此欄位——結果 JSON 中不存在可直接取 Top10 的資料。真正的
  全域完整排序是 `_spread_result()` 內的區域變數 `all_ranked`
  （`service.py:455-456`，已為 `expiry_best` 而存在），Top10 應從此處切片
  外露，不能只靠 UI 攤平既有資料（`render.py:206` `render_step3` 是依到期日
  分組的表格）。
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
- 價格範圍需延伸至目標價以上至少 15% — 已完成（覆核時確認由 commit
  `5e6b1bb` 修正）。`matrix.py:23` 現為
  `overshoot = target * (1.15 if bullish else 0.85)`；
  `tests/test_matrix.py:36,47,68,76` 斷言與 golden fixtures 已同步更新，
  `pytest tests/test_matrix.py` 為綠。
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
- `option_chaser/valuation.py` 的估值原語（`scenario_leg_value`/
  `spread_scenario_value`/BS/greeks）— 已正確，是 Heatmap 的地基。
  （2026-07-30 修訂：`evaluate_spread` 的 baseline 估值時點除外，
  改列 Step 1-2 修改範圍。）
- `option_chaser/scenarios.py` 全部 — 本輪未要求變更 7 情境向量/completion curve。
- `option_chaser/store.py` 的事件溯源機制（`append_event`/`read_events`/
  `reconcile_status`/`rebuild_groups`）— 架構已達標。
- `option_chaser/ranking.py` 全部。
- `option_chaser/service.py` 的 `_analyze`/`_single_leg_result`/
  `_spread_result` 主流程。

**修改（局部）**
- ~~`option_chaser/matrix.py:23` — overshoot 倍率 1.10→至少 1.15~~ 已完成
  （commit `5e6b1bb`，含測試與 golden fixtures）。
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

**Step 0 — Heatmap 價格範圍修正 ✅ 已完成**（commit `5e6b1bb`）
- 完成證據：`matrix.py:23` 為 1.15/0.85；`tests/test_matrix.py:36,47,68,76`
  斷言同步；golden fixtures（`tests/fixtures/golden_*.txt`）重新產生；
  排名公式（`ranking.py`）、`date_axis`、`matrix_grid` 未被改動。

**Step 1 — 年月合併輸入與正規化**（輸入層，阻塞後續首頁改版）
- 目標：新增年月解析函式，支援 4 種格式，輸出 (年, 月) 二元組；另提供
  日曆錨點函式（該月第三個星期五，純日曆計算）。不得把年月映射成單一
  「目標日」供全流程共用（附錄A2；原「映射慣例待確認」問題已解消——
  答案是不映射）
- 檔案：新增解析函式（`option_chaser/models.py` 或新檔），
  `webapp/pages/0_劇本工作區.py` 建立表單欄位替換
- 驗證：新增單元測試（4 種格式→相同 (年, 月)；第三個星期五計算含
  跨年/閏年案例）；確認 `tests/test_workspace.py`/`tests/test_scenarios.py`
  不受影響
- 不得順便改動：`service.py` 分析主流程。`AnalysisParams` 若需增欄位
  以承載年月/錨點語意，屬 Step 1-1 範圍，本步不動

**Step 1-1 — 到期日選取規則**（依賴 Step 1 的日曆錨點函式）
- 目標：實作 `modifyRequestV1.md` §三六點規則：日曆錨點 → baseline
  （距錨點最近的實際到期日，同距取較晚）→ baseline 前2後2共至多5檔
  （一側不足由另一側依距離補足）→ 窮舉範圍限縮至選取的5檔
- 檔案：`option_chaser/service.py`（取代/改寫 `_sample_expiries` 的
  「先窮舉後取樣」流程）
- 驗證：新增單元測試（錨點命中/未命中實際到期日、同距 tie-break 取較晚、
  一側不足補足、鏈上到期日少於5檔）；確認 `tests/test_service*.py` 回歸
- 不得順便改動：排名公式本體（估值時點修正屬 Step 1-2）、Heatmap

**Step 1-2 — 排名估值時點修正**（可與 Step 1-1 平行；建議同一輪完成）
- 目標：baseline 估值日由 `p.target_date` 改為各 Spread 自身到期日
  （＝內在價值 payoff），對齊需求 §三「持有至到期」（附錄A2 第2點）
- 檔案：`option_chaser/valuation.py`（`evaluate_spread`；單腳
  `evaluate_contract` 是否同步修改，隨 Long Call 比較功能屬可延後項目，
  本步不強制）
- 驗證：新增測試（到期日晚於/早於/等於舊估值日三情境的 baseline 值）；
  `tests/test_spread_valuation.py`/`tests/test_spread_ranking.py` 斷言
  同步更新；golden fixtures 重產
- 不得順便改動：Heatmap 估值路徑（`matrix_grid`/`scenario_leg_value`
  本體——Heatmap 必須維持到期前時間價值，這正是兩者語意分離的原因）

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

**Step 5 — 開站自動更新迴圈＋卡片依收益率重排**（依賴 Step 4 燈號需要更新
時機）
- 目標：(a) 頁面載入時對所有 Active 劇本呼叫 `analyze_scenario`，單一失敗
  不擋其他；(b) 需求七.8：更新後劇本卡片依最新收益率重新排序——現況
  `list_scenarios` 固定以 `(symbol, target_date, id)` 排序
  （`workspace.py:99`），需在 UI 層（或新聚合函式）改以最新
  `baseline_return` 排序，`list_scenarios` 本身的回傳順序可不動
- 檔案：`webapp/pages/0_劇本工作區.py` 頁面頂部與清單區排序
- 驗證：新增測試模擬多劇本其中一個 `FetchError`，確認其餘仍完成；卡片排序
  測試（兩劇本收益率互換後順序反轉）；建議先量測目前手動分析耗時，評估多
  劇本情境下頁面載入時間是否可接受
- 不得順便改動：`workspace.analyze_scenario`/`analyze_group` 函式本身、
  `list_scenarios` 的排序（其順序被對帳/群組邏輯依賴的風險未查證，改 UI 層
  較安全）

**Step 6 — 跨到期日 Top10 聚合**（可與 Step 4/5 平行，建議在卡片穩定後做以
降低 UI 變動衝突）
- 目標：新增跨到期日聚合函式（`service.py`），`render_top10`（`render.py`），
  詳細頁串接；`store.py` 補「當時排名」欄位。注意：不能從
  `StrategyResult.ranked_spreads` 切片——它已被 `rank_spreads()` 截斷至
  `p.top`（預設 3）且未被 `serialize_result()` 序列化。正確做法是在
  `_spread_result()` 把既有完整排序 `all_ranked`（`service.py:455-456`）的
  前 10 名外露為新欄位（建 `CandidateView` 含 Heatmap），並在
  `store.serialize_result()` 新增對應序列化，結果 JSON 才能供 UI 與歷史
  查詢使用
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
- ~~年月合併輸入正規化後「代表哪一天」的映射慣例~~ — 已解消
  （2026-07-30，附錄A2：不映射單日；探索中心＝日曆錨點，排名估值日＝
  各 Spread 自身到期日）。仍待定：Heatmap 目標時間錨點欄用哪個日期、
  紅燈「年月已過期」判定日（Grill 進行中）。
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
