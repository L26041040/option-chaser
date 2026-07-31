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

> 2026-07-30 Grill 更新②：紅燈判定日確認＝目標月份最後一天過完
> （§2六）；Heatmap 舊 target-date * 錨點欄改列「可移除的舊實作細節／
> 日後另行確認的非阻塞顯示項目」（§2四、§3），不得反向製造產品需求；
> §6 對應兩項待定據此解消。

> 2026-07-30 Grill 更新③（資料模型定案，取代先前多項結論）：
> 需求方確認刷新／燈號／原子更新單位全部是「劇本」，且**每次刷新都必須
> 重新計算該劇本全部有效候選**（系統無 Spread API，Spread 由 Option 基礎
> 資料即時算出）。據此本路線圖移除兩項錯誤假設：
> (1) **「跨到期日全域 Top 10」不再是主要詳細頁模型**——改為「每個到期日
>     各自 Top 10、摘要層每期只顯示第 1 名、詳細層預設 baseline 的 Top 10」；
>     原 Step 6「跨到期日 Top10 聚合」據此改寫。
> (2) **不得只刷新曾入榜／曾顯示／曾被追蹤的 Spread**——歷史保存範圍與
>     刷新計算範圍必須分離（§2八、Step 7）。
> 另新增：原子快照更新（§2七/八）、燈號劇本級粒度與「個別 Option 無報價
> ≠ 劇本失敗」（§2六）、session 級自動刷新一次＋手動刷新鈕（§2七）、
> 左側依各劇本最高收益率排序（§2五）。

> 2026-07-30 Grill 更新④（Step 1 排序缺陷修正）：原 Step 1「改 UI 但
> 本步不動 `AnalysisParams`」是**不可施工的約束**——`create_scenario()`
> 簽章要求 `target_date: str`（`workspace.py:36`），UI 改年月後只剩
> 「無法建立劇本」或「偷把月份轉成某一天塞回去」兩條路，後者正是附錄A2
> 明令禁止的。需求方裁示：`Scenario.target_month`（YYYY-MM）直接取代
> `target_date`（附錄A5），**原 Step 1 與 Step 1-1 合併為一個縱切步驟**。
> 本次核對另發現三項原文未提及、同樣阻塞施工的事實：
> (a) `filters.py:22` `e >= target` 會硬砍所有早於目標日的到期日，
>     使六點規則的「baseline 前方最近兩檔」無法實作——Step 1-1 原檔案
>     清單漏列 `filters.py`；
> (b) `webapp/app.py:49,128` 是**第二個** `st.date_input` 入口，
>     原 Step 1/2/3 完全未提及；
> (c) `service.py:520`／`cli.py:144` 的 `target_date <= today` 驗證在
>     月語意下無定義（「本月」是部分已過去的）。
> 另確認一項有利事實：`store.py:57-61` `scenario_id()` 本來就只取
> `target_date[:4]+[5:7]`，ID 格式（`TLT-105-202801`）已是月粒度，
> 改為 target_month 後 ID 格式不變。

> 2026-07-30 Grill 更新⑤：需求方裁示三項——(1) 紅燈劇本左側排序一律
> 沉底，並新增左側清單編輯工具供手動移除劇本（附錄A6，Step 3/5）；
> (2) 歷史保存範圍＝每次成功刷新保存**該次全部有效候選**的歷史欄位，
> 不只入榜者（附錄A7，Step 6/7 據此更新——`serialize_result()` 需序列化
> 全部有效候選，歷史斷點問題僅剩「候選當次失效」一種）；(3) 兩處文件
> 衛生修正（§三殘留重複句刪除、§八「五個到期日」改「至多五個」）。
> 其餘尚未定案事項統一列於 §6 待決清單，不再逐題散問。

> 2026-07-30 Grill 更新⑥（收尾定案）：§6A 全部待決項經需求方「全按建議」
> 一次批准，定案於附錄A8（A-F 六項＋三項預設）與 A9（舊表面 anchor
> 例外）。A9 同時解掉本文件 §3 保留清單的內部矛盾——原「`scenarios.py`
> 全部不動」「`ranking.py` 全部不動」與 Step 1 移除單日目標欄位不相容
> （該二檔仍有多處消費 `p.target_date`）；現改為「曲線／排名邏輯不動，
> 消費單日目標欄位之處改吃 anchor，屬 Step 1 範圍」。Step 1 spec 據此
> 發佈至 GitHub Issues（ready-for-agent）。

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
- 缺口集中在呈現層聚合（每到期日 Top 10、資料狀態燈號、Spread 獨立歷史查詢）、
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
  見附錄A2 日期語意分離原則。**兩個** UI 入口都要改：
  `0_劇本工作區.py:94,111` 與 `app.py:49,128`。持久化欄位改為
  `Scenario.target_month`，見附錄A5 與 Step 1。）
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
  另有一項**阻塞事實**（2026-07-30 新查得）：`filters.py:22` 的
  `e >= target`（target 即 `p.target_date`）會硬砍掉所有早於目標日的
  到期日，而六點規則明確要求選取 baseline **前方**最近兩檔——那些到期日
  可能早於目標月。不解耦這道下限，六點規則無法實作。已納入 Step 1
  第 5 小段。
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
- 每個到期日各自 Top 10 — 缺少（2026-07-30 改寫：原「跨到期日總排名
  Top10」模型已被需求方作廢，見更新③）。`rank_spreads()`
  （`ranking.py:120-122`）在回傳前就截斷至 `p.top`（預設 3，
  `models.py:51`），且 `store.serialize_result()` 沒有序列化
  `StrategyResult.ranked_spreads`——結果 JSON 中不存在任何一個到期日的
  完整前十名。正確做法是在 `_spread_result()` 內**依到期日分組**後各自
  取前 10（既有區域變數 `all_ranked`，`service.py:455-456`，是全域排序，
  需先分組再切片，不是直接取前十），並在 `serialize_result()` 新增
  per-expiry Top 10 的序列化。`p.top=3` 是舊參數，不構成「只顯示 3 筆」
  的產品理由。
- 各到期日第 1 名（摘要層） — 已完成。`_spread_result()` 內
  `best_by_expiry` 迴圈（`service.py:453-468`）+ `_build_groups()`
  （`service.py:296-383`）已產出，語意與需求「每個到期日摘要只顯示
  該期第 1 名」相符。
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
- （2026-07-30 補註）`date_axis()` 的 target_date 參數與 * 目標欄
  （`matrix.py:46-57`）為舊實作細節，非需求文件必要功能。需求對日期軸
  的要求只有「今天 → 該 Spread 自身到期日」。* 欄列為可移除、或日後
  另行確認的非阻塞顯示項目；施工時不得為了餵它一個日期而把
  target month 映射成單日。

**五、劇本卡片**
- 緊湊卡片（標的/目標價/年月/最高目標達成收益率/單一燈號） — 實作錯誤。現況
  `0_劇本工作區.py:127-161` 是多欄位表格列（標的/方向/目標價/目標日/生命週期
  badge/佔本金%/含完整 Spread 腳資訊與情境最壞數字的摘要行，見 L156-159），
  牴觸文件「卡片不應塞入完整 Spread 腿資訊/長篇說明/大量技術數字」的要求。
- 收益正綠負紅 — 缺少。收益數字（`0_劇本工作區.py:159`）以純文字 markdown
  顯示，`render.py`/`0_劇本工作區.py` 都沒有依正負值上色的卡片級邏輯
  （`cell_color()` 是 Heatmap 專用函式）。
- 點卡片進詳細頁 — 已完成。「詳頁」按鈕（L168-170）+ 詳頁區塊（L257-275）。

**六、資料狀態燈號（綠/黃/紅，紅優先）** — 缺少。（2026-07-30 已確認：
紅燈判定＝目標月份最後一天過完，純日曆、離線可判；燈號為**劇本級**狀態，
不存在「部分到期日綠、部分黃」；黃燈＝關鍵資料失敗→丟棄本次全部部分結果、
完整保留上一份成功快照並顯示其時間；個別 Option 無有效報價僅是候選過濾，
不影響燈號，只有整個到期日 chain／標的價格等關鍵資料失敗才是劇本級失敗。
需注意現況 `filters.py` 的個別合約過濾與「劇本級失敗」目前沒有分層區分，
新燈號函式必須明確劃開這兩類。）現況只有生命週期 badge
（`STATUS_BADGE`, `0_劇本工作區.py:20-21`：🟢Active/🏁Reached/⌛Expired/
❌Invalidated），語意是使用者手動或到期判定的生命週期，不是文件定義的
「綠=成功取得最新報價並完成重新分析／黃=報價 API 連不上、顯示上次成功結果／
紅=劇本年月已過期，優先於報價連線狀態」。Repo-wide grep 除此 badge 外找不到
其他相符實作。

**七、動態更新** — 缺少。
`workspace.analyze_scenario`/`analyze_group`（`workspace.py:163-198`）都是
「使用者按下『分析』/『群組分析』按鈕」觸發（`0_劇本工作區.py:163-167,
250-253`），頁面載入的 top-level 程式碼沒有任何自動迴圈呼叫。「單一失敗不擋
其他」的例外隔離語意已存在於 `_analyze_with_status()`
（`0_劇本工作區.py:43-53` 的 try/except），只是還沒被包進「開站對所有未過期
劇本迴圈呼叫」的邏輯。

（2026-07-30 補充需求，均為缺少）
- 刷新單位是劇本，每次刷新重算全部有效候選 — 現況 `_analyze()` 主流程本來
  就是「每次呼叫從 chain 重新窮舉」，語意相符；需確保新增 Top 10／歷史功能
  時不得退化成「只重算曾入榜候選」。
- Session 級自動刷新一次 — 缺少。需以 `st.session_state` 旗標控制，避免
  Streamlit 每次 rerun（切頁/點卡片/切到期日/展開）都打 API。
- 手動刷新圖示按鈕（左側清單旁） — 缺少。
- 原子快照替換 — 部分完成。`store.save_result()`（`store.py:378-383`）本來
  就是「整份 view 寫成一個新 timestamp 檔案」，天然具備整組替換語意；但
  失敗路徑目前由 UI 層 try/except 處理（`0_劇本工作區.py:43-53`），需確認
  失敗時**不寫入任何部分結果**、且 latest 指標仍指向上一份成功快照。
- 左側依各劇本最高收益率排序（黃燈用上一份成功快照的值） — 缺少。
  `workspace.list_scenarios()` 固定以 `(symbol, target_date, id)` 排序
  （`workspace.py:99`）。

**八、Spread 詳細頁與歷史**
- 詳細頁兩層結構（第一層五個到期日摘要各顯示第 1 名＋縮圖；第二層預設
  baseline 的 Top 10，點其他到期日才切換） — 部分完成。
  `render_summary`/`render_step2`/`render_step3`/`render_step4` 都已存在且被
  詳頁區塊呼叫（L265-275），`render_step3` 本來就是「依到期日分組的表格」，
  結構上與第一層摘要相近；缺的是「每個到期日自己的 Top 10」資料
  （見第三節）與「預設選中 baseline＋切換」的互動。原「跨到期日 Top10」
  結論已作廢（見更新③）。
- Spread 身份（標的+到期日+買入履約價+賣出履約價） — 已完成。
  `service.py:258-263` `candidate_key()` 用 strategy（隱含標的方向）+
  `long_leg.strike` + `short_leg.strike` + `long_leg.expiry` 組成穩定 id。
- 同一 Spread 排名升降/掉出/重進（該到期日自己的）Top 10 都延續同一份歷史
  — 缺少。`store.save_result()`（`store.py:378-383`）每次分析把整份 view 存成
  新的 timestamp 檔案；`candidate_key` 雖穩定，但沒有函式依 `candidate_key`
  跨多個歷史快照檔案抽取單一 Spread 的時間序列。若某次分析該 Spread 掉出
  保存範圍，該次快照不含它的資料點，歷史會出現斷點。現有 `events.jsonl` +
  `results/<id>/<ts>.json` 檔案配置本身可支撐（欄位都在，只是缺查詢函式），
  不需改資料格式。
- 每次成功更新至少保存更新時間/標的價格/建倉淨成本/收益率/當時排名 — 部分
  完成。`store._candidate()`（L256-307）已存 `mid_cost`/`baseline_return`/
  `candidate_key`，快照檔名即 `fetched_at`（`store.py:380`），`meta.spot`
  （L360-363）即標的價格；但「當時排名」沒有獨立欄位。新模型下「當時排名」
  ＝該 Spread 在**其所屬到期日** Top 10 中的名次（不是全域名次）。
- 歷史保存範圍與刷新計算範圍分離（2026-07-30 新增） — 施工約束，非現況缺口。
  歷史最終保存每期第 1 名／每期 Top 10／或特定曾入榜結果，都不得回過頭限縮
  每次刷新的計算範圍；每次刷新一律重算該劇本全部有效候選。

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
- `option_chaser/scenarios.py` 的曲線邏輯 — 本輪未要求變更 7 情境向量/
  completion curve。（2026-07-30 修訂：其消費單日目標欄位之處改吃
  anchor——附錄A9，屬 Step 1 範圍；曲線演算法本身不動。）
- `option_chaser/store.py` 的事件溯源機制（`append_event`/`read_events`/
  `reconcile_status`/`rebuild_groups`）— 架構已達標。
- `option_chaser/ranking.py` 的排名與指引邏輯。（2026-07-30 修訂：單腳
  指引消費單日目標欄位之處改吃 anchor——附錄A9，屬 Step 1 範圍；
  排名公式不動。）
- `option_chaser/service.py` 的 `_analyze`/`_single_leg_result`/
  `_spread_result` 主流程。

**修改（局部）**
- ~~`option_chaser/matrix.py:23` — overshoot 倍率 1.10→至少 1.15~~ 已完成
  （commit `5e6b1bb`，含測試與 golden fixtures）。
- `option_chaser/store.py` `Scenario`（L26-38）— `target_date` 改為
  `target_month`（YYYY-MM），`schema_version` 升版＋既有資料遷移；
  `scenario_id()`（L57-61）輸入改 (年, 月)，**輸出格式不變**。
- `option_chaser/models.py` `AnalysisParams`（L46-52）— 承載年月/錨點語意，
  移除可被填入任意單日的 `target_date`。
- `option_chaser/filters.py`（L17,22）— 解除 `e >= target_date` 到期日
  硬性下限（阻塞六點規則，見 §2三）；保留報價/IV/OI 等合約品質過濾。
- `option_chaser/workspace.py` — `create_scenario()` 簽章（L35-46）、
  過期判定（L86-94）改月級。
- `option_chaser/service.py`（L520）／`cli.py`（L144）— `target_date <=
  today` 驗證改月級語意。
- `webapp/app.py`（L49,128）— 第二個 `st.date_input` 入口，同步改年月。
- `webapp/pages/0_劇本工作區.py` 建立表單（L69-114） — 移除方向/策略勾選欄位，
  改為 3 欄輸入 + 年月合併框。
- `webapp/pages/0_劇本工作區.py` 清單區（L122-202） — 表格列改為緊湊卡片，
  加入正負色與單一燈號。
- `webapp/pages/0_劇本工作區.py` 版面配置 — 加入 `st.columns([0.2, 0.8])`
  左右分割（桌面）。
- `option_chaser/service.py` `_build_groups`/`_sample_expiries`
  （L278-383） — `_sample_expiries` 的「先窮舉後取樣」須改為六點規則的
  「先選 5 檔再窮舉」；另新增 per-expiry Top 10 聚合（2026-07-30 修訂：
  非跨到期日全域 Top 10）。
- `option_chaser/store.py` `_candidate()`（L256-307） — 新增「當時排名」
  欄位（該 Spread 在其所屬到期日 Top 10 中的名次）。

**新增**
- 年月輸入解析/正規化函式（建議 `option_chaser/models.py` 或新檔） — 處理
  2028/1、2028/01、28/1、28/01，輸出 (年, 月)。
- 日曆錨點函式（該月第三個星期五，純日曆計算）與「目標月是否已過完」判定。
- 到期日選取六點規則函式（`service.py`；取代 `_sample_expiries`）。
- `Scenario` schema 遷移函式（`target_date` → `target_month`）。
- 資料狀態燈號計算函式（建議加入 `workspace.py`，依賴既有
  `analyze_scenario` 成功/失敗與 `list_scenarios` 的 Expired 判定）。
- Long Call 追平比較函式（建議加入 `option_chaser/scenarios.py` 或新模組，
  重用 `valuation.py` 的 `l3` 公式形狀）。
- Spread 歷史查詢函式（依 `candidate_key` 跨 `results/<id>/*.json` 聚合時間
  序列，建議加入 `workspace.py`）。
- 開站自動更新迴圈（建議加入 `0_劇本工作區.py` 頁面載入區塊），含
  session 級「只自動刷新一次」旗標與手動刷新圖示按鈕。
- 每到期日 Top 10 的 UI 渲染＋詳細頁兩層結構（摘要層各期第 1 名／詳細層
  預設 baseline）（建議加入 `webapp/render.py`）。
- 劇本最高收益率取值與左側排序函式（黃燈用上一份成功快照的值）。

**移除/隱藏（不刪除底層邏輯）**
- Heatmap 日期軸的 target-date * 目標欄（`matrix.date_axis`）— 可移除
  的舊實作細節；若日後要保留顯示，錨定語意另行確認（非阻塞）。
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

**Step 1 — 年月資料模型縱切**（2026-07-30 合併原 Step 1＋Step 1-1；
阻塞後續所有首頁改版）

本步是**縱切**：UI、資料模型、持久化、過濾器必須同批落地。理由見更新④
——`create_scenario()` 的簽章是硬邊界，中間沒有可運行的半成品狀態。

- 目標（建議依此內部順序施工，每一小段都不破壞既有測試）：
  1. 純函式先行：年月解析（4 格式 → (年, 月)）＋日曆錨點（該月第三個
     星期五，純日曆計算）＋「目標月是否已過完」判定
  2. 資料模型：`Scenario.target_date` → `target_month: str  # YYYY-MM`，
     `schema_version` 升版並提供既有資料遷移；`AnalysisParams` 相應調整
     （承載年月/錨點語意，不得保留可被填入任意單日的 target_date）
  3. 持久化與查詢：`workspace.create_scenario()` 簽章改吃 target_month；
     `store.scenario_id()` 輸入改為 (年, 月)——**ID 格式不變**
     （`{symbol}-{price}-{yyyymm}`，本來就是月粒度，見更新④）
  4. 過期判定：`workspace.py:90` `observed > target_date` 改為
     「目標月最後一天過完」；`service.py:520`／`cli.py:144` 的
     `target_date <= today` 驗證同步改為月級語意
  5. **`filters.py:22` 到期日下限解耦**：現行 `e >= target` 會砍掉所有
     早於目標日的到期日，使六點規則的「baseline 前方最近兩檔」無法實作。
     到期日的取捨改由 Step 1 的選取規則負責，filters 只保留報價/IV/OI
     等合約品質過濾
  6. 到期日選取六點規則（原 Step 1-1）：日曆錨點 → baseline（距錨點最近
     的實際到期日，同距取較晚）→ baseline 前2後2共至多5檔（一側不足由
     另一側依距離補足）→ **窮舉範圍限縮至選取的5檔**，取代
     `_sample_expiries()` 的「先窮舉後取樣」
  7. UI：**兩個**入口的 `st.date_input` 一併改為年月輸入框——
     `webapp/pages/0_劇本工作區.py:94,111` 與
     `webapp/app.py:49,128`（後者原路線圖從未提及，見更新④b）
  8. 舊表面 anchor 例外（附錄A9）：CLI 報告、單腳指引、情境曲線、
     `days_to_target` 等消費 `p.target_date` 的舊路徑，一律改吃日曆
     錨點（欄位名 `anchor`，僅顯示/指引參考）；Heatmap 日期軸的
     target-date * 標記依 A2.3 移除，不得為其映射日期
- 檔案：`option_chaser/models.py`（或新檔，解析/錨點函式）、
  `option_chaser/store.py`、`option_chaser/workspace.py`、
  `option_chaser/filters.py`、`option_chaser/service.py`、
  `option_chaser/cli.py`、`option_chaser/ranking.py`、
  `option_chaser/scenarios.py`、`option_chaser/report.py`、
  `webapp/pages/0_劇本工作區.py`、`webapp/app.py`
- 驗證：新增單元測試（4 種格式→相同 (年, 月)；第三個星期五含跨年/閏年；
  目標月最後一天前後的過期判定邊界；錨點命中/未命中實際到期日；同距
  tie-break 取較晚；一側不足由另一側補足；鏈上到期日少於 5 檔；
  **baseline 前方到期日早於目標月時不被 filters 濾掉**）；
  `tests/test_workspace.py`／`test_scenarios.py`／`test_service*.py`／
  `test_filters.py`／`test_store_*.py` 同步更新；全套 pytest 綠
- 不得順便改動：排名公式本體與估值時點（屬 Step 1-2）；Heatmap 估值路徑；
  卡片/版面（屬 Step 2-3）。**特別禁止**：為了餵任何既有 API 一個
  `date`，而把 target_month 補成某一天（附錄A2/A5）

**Step 1-1 — 已併入 Step 1**（原「到期日選取規則」，見上）

**Step 1-2 — 排名估值時點修正**（可與 Step 1 平行；建議同一輪完成）
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

**Step 3 — 桌面 20/80 版面 + 劇本卡片重製 + 清單編輯工具**（依賴 Step 2）
- 目標：`st.columns` 左右分割、緊湊卡片（5 欄位+單一燈號位置）、收益正負色；
  左側清單編輯工具（手動移除劇本，附錄A6；儲存語意已定＝事件溯源軟
  刪除，歷史保留，附錄A8.2）；群組區自新版首頁隱藏（附錄A8.6，底層
  邏輯保留）
- 檔案：`webapp/pages/0_劇本工作區.py` 版面與清單區
- 驗證：`tests/test_webapp_workspace.py`；手動截圖確認版面
- 不得順便改動：群組區/詳頁邏輯（L204-275 暫不動）

**Step 4 — 劇本級狀態燈號＋失敗分層**（依賴 Step 3 有燈號 UI 位置）
- 目標：(a) 新增**劇本級**燈號計算函式（綠/黃/紅，紅優先；紅＝目標月最後
  一天過完，純日曆判定，不依賴市場資料）；(b) 明確劃開兩類失敗——個別
  Option 無有效報價＝候選過濾（不影響燈號），整個到期日 chain／標的價格等
  關鍵資料失敗＝劇本級失敗（黃燈）；(c) 黃燈時顯示上次成功更新時間
- 檔案：`option_chaser/workspace.py`（新函式），
  `webapp/pages/0_劇本工作區.py`（消費）
- 驗證：新增單元測試（關鍵資料 `FetchError`→黃燈、目標月已過完→紅燈、
  成功→綠燈、紅燈優先於黃燈、**個別合約缺報價但 chain 成功→仍綠燈**）
- 不得順便改動：`analyze_scenario` 本身的分析邏輯，只讀取其成功/失敗結果；
  `filters.py` 既有個別合約過濾規則

**Step 5 — 自動／手動刷新＋原子快照＋卡片依最高收益率重排**（依賴 Step 4）
- 目標：
  (a) 開站自動刷新所有**未過期**劇本；**同一 Streamlit session 只在首次
      載入時自動刷新一次**，一般切頁／點卡片／切到期日／展開內容不得再次
      呼叫 API（以 `st.session_state` 旗標控制）
  (b) 左側清單旁新增常見的網頁刷新圖示按鈕，點擊時重新刷新所有未過期劇本
  (c) 單一劇本失敗不擋其他
  (d) **原子快照**：本次刷新失敗時丟棄所有部分結果、完整保留上一份成功
      快照；嚴禁混合今天的標的價格／今天部分到期日資料／上次其他到期日資料，
      也不得用部分成功結果重新排名
  (e) 左側依**各劇本此次分析結果中的最高收益率**由高至低排序；黃燈劇本用
      上一份完整成功快照的最高收益率參與排序；**紅燈劇本一律沉底**
      （附錄A6；紅燈組內排序沿用同一收益率規則，附錄A8.7）
  (f) 建立劇本當下立即觸發該劇本首次刷新；無快照劇本收益率顯示「—」、
      排序在綠／黃之後紅燈之前（附錄A8.1）；MVP 刷新不計算 Long Call
      （附錄A8.3）
- 檔案：`webapp/pages/0_劇本工作區.py`（頁面頂部、刷新鈕、清單排序）；
  若原子性需在儲存層加固，`option_chaser/workspace.py`
- 驗證：多劇本其中一個關鍵資料失敗→其餘完成且該劇本保留舊快照＋黃燈；
  session 內多次 rerun 只打一次 API；點刷新鈕會再打一次；排序測試
  （兩劇本最高收益率互換後順序反轉）；失敗路徑不得留下部分寫入的快照檔
- 不得順便改動：`list_scenarios` 的既有回傳排序（其順序被對帳/群組邏輯依賴
  的風險未查證，排序改在 UI 層／新聚合函式較安全）；每次刷新的**計算範圍**
  （一律重算全部有效候選，不得因歷史保存範圍而限縮）

**Step 6 — 每到期日 Top 10＋詳細頁兩層結構**（2026-07-30 依更新③改寫，
原「跨到期日全域 Top10 聚合」已作廢；可與 Step 4/5 平行，建議在卡片穩定
後做以降低 UI 變動衝突）
- 目標：
  (a) `service.py`：把既有完整排序 `all_ranked`（`service.py:455-456`）
      **依到期日分組後各自取前 10**，外露為新欄位（建 `CandidateView`
      含 Heatmap）。不可從 `StrategyResult.ranked_spreads` 切片——它已被
      `rank_spreads()` 截斷至 `p.top`（預設 3）且未被序列化；也不可只取
      全域前十
  (b) `store.serialize_result()` 依附錄A7 改為序列化**該次全部有效候選**
      的歷史欄位（更新時間/標的價/淨成本/收益率/所屬到期日內名次），
      per-expiry Top 10 為其上的標記或視圖，不是保存範圍的上限；
      注意全量序列化的檔案體積會明顯成長（5 檔 × 全部配對），屬已接受
      的取捨，後續依需求縮減
  (c) `render.py`＋詳頁：第一層被選中到期日（至多五個）摘要各顯示第 1 名
      ＋Heatmap 縮圖；第二層預設顯示 **baseline 到期日**的 Top 10，點其他
      到期日才切換（切換屬 UI 互動，不得觸發新的 API 呼叫，見 Step 5(a)）；
      進入詳頁預設選中 baseline 第 1 名 Spread（附錄A8.5）
- 檔案：`option_chaser/service.py`、`option_chaser/store.py`、
  `webapp/render.py`、`webapp/pages/0_劇本工作區.py` 詳頁
- 驗證：新增測試（合成多到期日 spread 資料，驗證**每個到期日各自**前 10
  正確、baseline 預設選中、切換到期日顯示對應 Top 10）；確認
  `tests/test_spread_ranking.py` 無回歸
- 不得順便改動：既有依到期日分組的 `render_step3` 顯示（可作為第一層摘要
  的基礎，不砍掉重練）；每次刷新的計算範圍

**Step 7 — Spread 獨立歷史查詢**（依賴 Step 6 的 per-expiry 名次欄位）
- 目標：新增依 `candidate_key` 跨 `results/<id>/*.json` 聚合時間序列的函式
- 檔案：`option_chaser/workspace.py`，`webapp/pages/0_劇本工作區.py` 詳頁
- 驗證：新增測試（合成 3 次刷新產生 3 份快照，同一 `candidate_key` 在其中
  1 份因當次缺報價而缺席，驗證查詢函式正確回傳含斷點的時間序列而非報錯）
- 不得順便改動：**每次刷新的計算範圍**。（2026-07-30 更新：附錄A7 定案
  全量保存後，快照本身即含全部有效候選，本步縮小為純查詢函式；斷點僅剩
  「候選當次失效」一種情況）

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

## 6A. 待決產品決策清單 — ✅ 已全數定案（2026-07-30「全按建議」批准）

全部決議收錄於 `modifyRequestV1.md` 附錄A8/A9，摘要：

- **A** 建立劇本即觸發首次刷新；無快照劇本收益率顯示「—」，排序在
  綠／黃之後、紅燈之前（→ Step 5）
- **B** 手動移除＝事件溯源軟刪除，歷史保留（→ Step 3）
- **C** MVP 刷新不計算 Long Call，§七流程第 6 步隨 D1 生效（→ Step 5/D1）
- **D** 「符合條件」沿用現行 filters 合約品質參數作預設（→ Step 1/6）
- **E** 詳頁預設選中 baseline 到期日第 1 名（→ Step 6）
- **F** 群組區自新版首頁隱藏，底層保留（→ Step 3）
- **G** 舊表面（CLI 報告/單腳指引/情境曲線/days_to_target）改吃日曆
  錨點 `anchor`，A2 原則唯一授權例外（→ Step 1，附錄A9）
- 三項預設一併確認：紅燈組內依最後已知收益率排序；已過完月份拒絕建立、
  當月允許；同標的多劇本各自獨立原子刷新

**仍屬驗證／後續活動（非決策，不阻塞）：**

- Heatmap 與 optionsprofitcalculator.com 的數值比對（列為驗收項）。
- 手機版完整可操作性實測（§十一）。
- 全量歷史保存的檔案體積成長觀察（附錄A7 已接受的取捨）。

---

## 6. 尚未取得足夠證據、下一階段才需要深入調查的項目

- 手機版 UI 是否真的完整可操作（需瀏覽器/viewport 實測，非讀程式碼可判斷）—
  對應文件十一節。
- ~~年月合併輸入正規化後「代表哪一天」的映射慣例~~ — 已解消
  （2026-07-30，附錄A2：不映射單日；探索中心＝日曆錨點，排名估值日＝
  各 Spread 自身到期日）。後續 Grill 亦已解消：紅燈判定日＝目標月
  最後一天過完；Heatmap * 目標欄改列非產品需求之舊實作細節
  （可移除／後議，見 §2四補註）。
- Heatmap 的 IV 假設（逐腳固定 IV，不隨日期變動）是否需要對照
  optionsprofitcalculator.com 做進一步比對——README 已知揭露此為模型限制，
  但文件第四節明確要求「需要研究及比對」，本輪未實際跑該網站比對數據，只能
  確認「非到期 payoff 硬套」這個大方向是對的。
- `candidate_key` 在測試中的實際覆蓋範圍（`tests/test_service.py`、
  `tests/test_store_serialize.py` 等是否已驗證 Spread 身份跨快照穩定）——
  本輪只讀了原始碼定義，未逐一開啟這些測試檔案核對斷言內容。
- ~~目前「全鏈窮舉 vs 先選 5 檔」需效能量測佐證~~ — 已由產品決策解消
  （2026-07-30）：需求方確認「先依六點規則選出最多 5 檔實際到期日，再對
  這 5 檔各自完整窮舉」，見 Step 1。仍待觀察的是每次刷新重算全部有效
  候選（5 檔 × 全部配對）在多劇本自動刷新下的頁面載入耗時，屬 Step 5
  的效能量測項，不影響規則本身。
- `tests/test_webapp_workspace.py`/`tests/test_webapp_v4.py` 的 AppTest
  涵蓋範圍，決定 Step 2-3 改動 UI 時有多少既有測試需同步更新——本輪只確認
  檔案存在，未讀取內容。
