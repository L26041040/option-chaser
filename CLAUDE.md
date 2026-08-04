# Option Chaser

## 規則

**每做完一張 ticket，就更新下面的「專案紀錄區」**——把該票移到已完成、標出下一張。

**全部 ticket 做完才開 PR、merge 回 master**，中途不要主動開。

**除非使用者主動要求，否則不准執行截圖或把截圖貼上對話**（跑 Streamlit／Playwright
截圖驗證 UI 極度耗費 token）。窄 viewport／版面等視覺驗收，一律留給需求方自己用
瀏覽器確認，或等使用者明確要求才做。

只有這三條。

## 專案紀錄區

### 已完成

- **Step 0** — Heatmap 價格範圍 1.10 → 1.15/0.85（commit `5e6b1bb`）
- **T1** [#15] — 年月與到期日選取純函式模組 `option_chaser/timeframe.py`（commit `4aaf0a0`）
- **T2** [#16] — target_month 全線縱切（輸入、持久化、選取、過濾解耦）
- **T3** [#17] — 排名估值改為各 Spread 自身到期日的內在價值（commit `8d52acf`）
- **T12** [#26] — 估值輸入層：期限對齊利率曲線＋worst 成本口徑
  （commits `c2f7ec2`/`8be24b9`/`d1881fc`；parity 測試點腳本
  `scripts/opc_parity_points.py`，OPC 人工驗證 A13.5 待需求方執行）
- **T4** [#18] — 建立表單簡化為三欄輸入（commits `cd8e0cc`/`a524f1d`）
- **T5** [#19] — 桌面 20/80 版面、緊湊劇本卡片、清單移除工具（commit `1dc010f`；
  A10.5 窄 viewport 驗收待需求方執行）
- **T6** [#20] — 劇本級狀態燈號與失敗分層（commit `26306ab`；附錄 A12「零」
  分層判讀一併納入。已知限制：關鍵失敗旗標只活在 `st.session_state`，
  跨分頁／重啟不保留，留給 T7 一併評估是否需要落地事件）
- **T7** [#21] — 自動／手動刷新與原子快照（commit `b639930`；原子性／全量重算／
  不計算 Long Call 三項驗收皆由既有架構保證，本票只加頁面層觸發；
  關鍵失敗旗標的已知限制沿用 T6 現狀，評估後維持不落地事件）
- **T8** [#22] — 劇本清單依最新收益率排序（commit `cb49c96`；新增
  `workspace.sort_cards()` 聚合函式，`list_scenarios()` 既有回傳順序未動）
- **T9** [#23] — 每到期日 Top 10 與全候選快照序列化（commit `4285215`；
  `StrategyResult.expiry_top10`／`expiry_ranked` 新增，`serialize_result()`
  新增 `expiry_top10`／`all_candidates` 兩欄位；範圍限定 Spread 路徑，
  single-leg 依 MVP 範圍不動）
- **T10** [#24] — 詳細頁兩層結構：各期摘要（沿用既有 `render_step3`）→
  單期 Top 10（新增 `render_expiry_top10`，commit `cc93053`）。新增
  `AnalysisResult.baseline_expiry`／`baseline_selection`（附錄A8.5），
  與 app.py 快速分析頁仍在用的 `default_selection` 並存不衝突。
  A10.5 窄 viewport 驗收待需求方執行
- **T11** [#25] — Spread 歷史時間序列查詢（commits `5474742`/`5565906`；
  新增 `workspace.spread_history()`，依身份鍵跨劇本全部歷史快照唯讀聚合，
  缺席即斷點不插值；`store.list_result_paths()` 一併抽出供
  `latest_result_path()` 共用）
- **QA1-01** [#28] — 移除疊床架屋的多頁結構（App／劇本工作區／說明，
  commit `68f896f`）：`webapp/app.py` 直接就是劇本工作區（原
  `webapp/pages/0_劇本工作區.py` 內容搬到入口位置），`webapp/pages/1_
  說明.py` 直接刪除、`pages/` 目錄隨之移除；兩頁專屬測試一併刪除，
  劇本工作區既有測試只改路徑常數，斷言未鬆綁
- **QA1-02** [#29] — 20/80 版面在部署版看不到（commit `e61ed1b`）：
  劇本卡片清單改放 `st.sidebar`（原 `st.columns([0.2, 0.8])` 窄螢幕
  會自然堆疊、清單壓在主畫面上方）；桌面常駐左欄、窄螢幕自動收合成
  漢堡側欄由 Streamlit 框架本身保證，不需應用層判斷視窗寬度。窄
  viewport 最終驗收仍待需求方以實機確認
- **QA1-03** [#30] — 劇本清單「最高收益率」抓錯到期日（commit
  `ba0438e`）：`workspace._best_return()` 原本掃全部到期日取全域最大值，
  改為只在 `view["baseline_expiry"]` 那組候選裡取最大值，與 Step 2
  主圖同一口徑；`sort_cards()` 排序本就直接吃 `card.best_return`，同一次
  修正自動涵蓋排序不脫鉤的要求，不需另外改動
- **QA1-04** [#31] — 建立表單不留預設值＋年月輔助下拉（commit
  `1db93ed`）：目標價位改純文字輸入（`_parse_target_price`），三欄全部
  留白；新增年／月輔助下拉（`index=None` 不預選），與既有自由格式文字
  輸入並存。連動僅做到下拉→文字單向（`_sync_month_dropdown_to_text`
  掛 `on_change`）——Streamlit 無逐鍵盤事件，打字時即時反向連動下拉不可行，
  依票上裁示記錄可行範圍
- **QA1-05** [#32] — Step3／Step4 對調＋到期日橫向選單（commits
  `4eafbbb`/`65cc215`/`a453eee`）：到期日選擇（原「到期日 Top 10」）緊接
  Step 2 主圖之後，橫向並排、每個日期選項下方附該期最高收益；候選卡片
  （到期日選擇＋到期日分組比較兩處，後者即問題陳述點名的舊「Step 3」）
  皆改窄版整列可點（TradingView 手機版標的列風格：徽章＋策略／履約＋
  劇本報酬），情境最壞／不漲保留率／成交摩擦不進這張快速比較列，數字
  細節留給 Step 4 進階區。`render_step3` 更名為 `render_expiry_comparison`
  避免與新 Step 3 混淆。「每到期日連同前十名並排可橫向滑動對比的大表格」
  依需求方裁示明確不做
- **QA1-06** [#33] — 「選看」改為就地展開（🔽），不拋回主圖（commits
  `84f4417`/`e4a00ca`）：`st.expander` 就地展開候選 Heatmap，純前端互動
  不觸發 rerun；`ws-selected-key` 從此固定為 baseline 期預設候選，
  不再跟著展開互動改變（「主圖就是主圖」）
- **QA1-07** [#34] — 刷新時機只有三種；刷新按鈕移頁面頂部（commit
  `90d8f96`）：`_refresh_all` 只從開站／建立劇本／頂部刷新鈕三處觸發；
  詳細頁單一劇本「分析」重刷鈕依需求方裁示移除（不當第四種管道），
  `_analyze_with_status` 隨之刪除、建立流程改走 `_refresh_all`；到期日
  橫向選單改用 `on_click` 回呼，消除「按鈕重跑後又手動 rerun 一次」
  的多餘整頁重載
- **QA1-08** [#35] — 移除「標記達成／標記失效」操作（commit `3a9857e`）：
  刪除詳細頁「原因」輸入欄與兩顆標記按鈕；`workspace.set_status()`／
  `Scenario.status`／事件紀錄／`STATUS_BADGE` 生命週期徽章不在本票範圍，
  原封不動，`set_status()` 測試覆蓋續留 `test_workspace.py`
- **QA1-09** [#36] — 刪除人工評語與自創名詞（收斂完全／成交摩擦等，
  commit `d5ce918`）：`_buffer_note()`（收斂完全／收斂不完全／中庸帶）
  與 🚀最高報酬／🛡️最強韌性徽章＋圖例三處一併刪除；自創詞「成交摩擦」
  改標準用語「Bid-Ask Spread」，glossary／CLI 報告／README 一致改名，
  golden fixtures 隨之重產。⚠ 警示徽號與後端 badges 計算不在本票範圍，
  維持不動
- **QA1-10** [#37] — 進階區分析報告＋歷史紀錄表單（raw data 可下載，
  commit `0c9364d`）：純文字報告搬出「Greeks 與流動性」展開區底部，
  獨立成「📄 Option Chaser 分析報告」；新增「原始資料（當次快照）」
  展開區（`st.dataframe` 查看＋CSV 下載），新增純函式 `snapshot_to_csv()`
  （`option_chaser/data/snapshot.py`）取得／轉換／輸出三層分離。範圍
  依裁示只做當下快照，不接外部持久化儲存
- **QA1-11** [#38] — Spread 歷史改為淨成本折線圖（commit `5c2c46a`）：
  原表格版本重做成跟 Yahoo Finance 單張選擇權價格走勢一樣的折線圖，
  x 軸更新時間、y 軸淨成本；`render_spread_history()` 改呼叫
  `st.line_chart`。缺席快照（`cost=None`）原封不動傳入，交由 Vega-Lite
  預設的 null 斷點行為維持「不插值」既有需求，不需額外處理（已驗證
  該版本 Vega-Lite 對 null 值預設是斷線而非略過連接）。整合測試改用
  `expander.get("vega_lite_chart")` 驗證圖表確實渲染（AppTest 對
  `line_chart` 無專屬存取器），精確資料對應留給純函式層測試。範圍內
  的取捨：新圖只畫淨成本單一序列，原表格的標的價／收益率／期內名次
  不再顯示於此區塊——這是「畫成跟 Yahoo Finance 單張價格走勢一樣」
  的直接結果，非遺漏
- **QA1-12** [#39] — 進階區「韌性」「散點」「Greeks」移入封存區
  （commit `4a95065`）：`render_step4()` 拔掉這三個展開區與主程式的
  連結，進階區只剩分析報告＋原始資料（#37）與 Spread 歷史走勢圖
  （#38）；三個渲染函式本身保留（票上裁示：程式碼保留與否屬工程
  判斷），只是不再被呼叫，目前無測試覆蓋（已知、非意外）
- **D1** [#14] — Long Call 追平價格 S*=K+C×(1+R)（commit `f89d27f`）：
  所選 Spread 旁顯示標的要漲到哪個價格，同履約價 Long Call 到期報酬率
  才追得上這組 Spread；S*≤目標價時醒目提示。分層維持 `webapp/render.py`
  「零金融公式」原則——`option_chaser/valuation.py` 新增純算術
  `catchup_price()`，`option_chaser/data/snapshot.py` 新增
  `find_contract()`（依 option_type/strike/expiry 查找，找不到回傳 None
  不拋錯），`option_chaser/service.py` 的 `CandidateView` 新增
  `catchup_price` 欄位（`_spread_view()` 多吃 `snap` 參數、新增
  `_spread_catchup_price()`：買腿是 call 直接用自己 Ask，是 put 則從
  快照找同履約價 call），`store._candidate()` 序列化該欄位（單腳恆
  None），`render_catchup_price()` 純格式化顯示，接在 `render_step2`
  之後。唯一取捨：目標價差距（gap）計算留在 render 層（與既有
  `render_summary` 的 `move_pct` 同類手法一致，非新模式），未額外
  搬進服務層——標準面審查列為非阻塞建議，判斷維持現狀

### 目前狀態（2026-08-02，PR #43、#46 已 merge）

**第二輪 MVP 已完結**：T1–T12、QA1-01–QA1-12、D1 全數完成（PR #43）；
**FB3 修正輪已完結**：FB3-01/02（feedback-v3 第 4 點）已隨 PR #46
merge 回 master，部署版待需求方驗證（`source` 是否 `cboe`＋TLT 2028/5
重驗）。工作分支 `claude/implement-tfm9oa` 已從最新 master 重開，
後續工作屬新一輪（前端重練）、將開新 PR。

**下一階段（spec 已發佈 [#47]，票未開）**——前端砍掉重練：

- **Spec：issue #47**（2026-08-02 發佈，涵蓋 2026-08-02 全部裁示）：
  Vercel 整包（前端＋Python serverless API，`option_chaser/` 引擎
  不動）、Neon Postgres 免費層持久化（建立時需求方在 Vercel 後台
  授權一次）、iOS 風格手機優先
- **測試裁示**：後端唯一接縫＝HTTP API（測試客戶端直測、儲存層
  記憶體假體）；**前端完整測試**（元件層 mock API＋Playwright E2E，
  需求方明示不只煙霧測試）；前端 mock 與後端 fixture 共用同一份
  契約樣本
- **範圍裁示**：QA1-13 [#40]、QA1-14 [#41]、QA1-15 [#42] 六項
  **全數併入** spec；feedback-v3 前端各點（2/3/6/7/7'/8/9/10）併入；
  舊「到期日分組比較」不搬遷（v3 #7' 與新層重複）；Streamlit
  `webapp/` 凍結至 cutover 後整目錄移除
- **拆票完成（2026-08-02，需求方核准後發佈）**，依賴順序如下、
  照舊 `/implement` 一張張做：

### 待辦（依序，← 為下一張；標注「被誰擋」）

- **V1** [#48] — 走通骨架 ✅ **雲端實測通過**（commits `7330ddb`
  → `4d3cea3` → `4225da4` → `2ab1a16`）：Vite＋React＋TS 手機優先前端／
  FastAPI serverless（`api_app/`，進入點 `api/index.py`，`/api/(.*)`
  全部 rewrite 到它、由 FastAPI 依原始路徑自行路由）／既有引擎。引擎只做 prefactor 不動計算：新增 `service.fetch_chain()`
  （只抓不落盤，serverless 唯讀）與 `run_with_snapshot()`（分析記憶體
  快照，不碰私有 `_analyze`）。契約＝既有 view dict，前端零金融計算。
  測試 24 條四層分工，契約樣本 `contracts/analysis_sample.json`
  前後端共用、漂移必紅燈。

  **部署踩過的三個坑**（全記在 `docs/deploy-vercel.md`，別再踩）：
  (1) 進入點偵測認不出「匯入再轉出」→ 改直接 `app = create_app()`；
  (2) `[tool.vercel]` 會讓整包被判成「Python 後端框架」、前端完全不被
  建置 → 撤掉，改用 `vercel.json` 的 `framework: "vite"`；
  (3) **pyproject.toml 存在時 Vercel 認它、不認 requirements.txt**
  → fastapi 移進 `[project] dependencies`，yfinance 移出改為 `yf`
  extra（免得 pandas/numpy 進 lambda）。路由靠檔名對齊、不靠 rewrite。

  **雲端驗收結果（2026-08-03）**：`資料來源 cboe` ← Vercel 出口打得到
  `cdn.cboe.com`，主資料源在雲端生效。且同一組輸入（TLT／2028-05／120）
  對照 feedback-v3 第 4 點的原始抱怨，**確認 FB3-01 的修正在雲端成立**：
  第 1 名從「買75/賣80、41%」（深度 ITM，候選池被盤外歸零報價餓死的
  產物）變成「買100/賣120、2566.7%」（淨成本 $0.75，數字自洽）。
- **V2** [#50] — 儲存層 port/adapter＋Neon 接通（commit `b08830c`，
  **Neon 授權待需求方執行**）：`api_app/storage/` port（Protocol＋
  `Scenario`／`ResultRecord`）＋記憶體假體＋Postgres adapter＋依環境
  變數挑後端的 factory（連線池端點優先）。API 新增劇本 CRUD／封存／
  分析／結果歷史／事件端點，`main.py` 零 SQL（有結構性測試把關）。
  原始快照與結果分開存（快照數百 KB，V9 歷史查詢不該拖著它；但 V8
  的原始資料 CSV 需要逐筆合約報價，分析當下不存就補不回來）。
  儲存層改延遲建構——放 import 期會讓資料庫連不上時整個 lambda 起不
  來，連負責回報狀態的 `/api/health` 都會 500。
  **測試亮點**：儲存契約 22 條同時跑記憶體與**真 Postgres**兩個實作
  （沙箱可起 PG，指令見 `docs/deploy-vercel.md`）——假體綠燈才代表
  正式環境也成立。全套 567 條綠。
  ✅ 需求方已於 2026-08-04 接上 Neon 並重新部署；最終確認方式：
  `/api/health` 的 `storage` 要顯示 `postgres`（顯示 `memory` ＝環境
  變數沒讀到、資料不會存活）
- **FB4-01** [#60] — 候選池診斷可見（commits `80af90a`／`84cb9f7`，
  **部署後待需求方按一次按鈕回報真實數字**）：新元件
  `src/CandidatePool.tsx` 顯示「選定到期日的合約 N 筆 → 四道關卡各砍
  −N → 通過品質過濾 N 筆 → 配對 N 組／合理性不通過 −N／有效 N 組 →
  該期有效組數」，組數 < 3 出 `role="status"` 警示（沿用 FB3-02／#45
  門檻）。**本票不動任何過濾門檻**——拿到真實數字才討論怎麼修。
  ⚠ **對票上「純顯示層、API 契約不動」的已知偏離**：票的前提
  「資料已存在於 view dict」與事實不符——dict 只有各關 `removed`，
  從來沒有合約層級的 total／passed，而 spread 路徑的 `n_qualified`
  是**配對數**（`service._spread_result` 取 `pair_report.passed`）。
  照票施工會顯示 4 筆／3 筆，真實是 9 筆／8 筆（契約樣本實測），
  正好是這張票要消滅的無聲誤導。因此 `store.serialize_result` 新增
  `filter_report`（`total`／`passed`）純新增欄位、契約樣本重產；
  引擎、`filters.py`、任何門檻皆未動（檢視已逐一核對）
- **R1** [#49] — Research：專業機構選擇權策略報告的版型慣例 ✅
  （產出 `docs/research/option-strategy-report-conventions.md`）。四個獨立
  來源家族（賣方寫作指引／課綱與教育機構／實際發行的 trade idea／專業
  平台策略單），外加法規面的語氣與免責約束（FINRA 2210(d)(1)、2220、
  OCC ODD——**本產品不受管轄，僅借為品質標準**）。核心結論：專業版型
  一律「結論先行、方法論墊底」，本產品 `report.py` 目前**正好相反**
  （30 行前言，第一組候選淨成本在第 34 行）；「最大獲利／最大損失／
  損益兩平」是不可拆的三件套，而純文字報告只印最大獲利；Greeks 屬
  第二層明細不進頭條列；報酬數字不得單獨出現、須與情境最壞並排。
  §4 給 V8 的欄位對照表分 A（重排）／A2（需補序列化）／B（呈現層
  算術）／C（刪除降級）四類。
  ⚠ **V8 施工前必讀 §4.2 A2**：買價指引 L2/L3、評語 cons、方法論尾註、
  免責這四項**只以散文活在 `report_text` 字串裡，沒有結構化欄位**
  （值已由 `CandidateView.pros/cons` 與 `valuation.l2/l3` 算好，只是
  `store._candidate()` 沒吐），V8 需順手補序列化——屬序列化層加欄位、
  非新增金融計算，仍在「引擎 report 內容來源不變」界線內。另 Greeks
  序列化的是**正規化比率**（`theta_day_rate`／`vega_per_pt` 分母為 Mid
  成本），非原始美元 Greeks，標籤不可寫成「Theta」了事。
  ⚠ 取材限制：本沙箱 WebFetch 對**所有**網域回 403（連 Wikipedia 亦然），
  全文一手資料皆為搜尋索引轉述，逐字法規措辭與機構報告原件無法查證，
  已逐項列於 §6；要寫進產品免責的法規措辭建議由需求方覆核原文後定稿
- **V3** [#51] — 劇本庫＋建立表單＋釘選功能列（commits `8e3b3be`／
  `868c86d`）：主畫面從「一顆分析按鈕」變成劇本庫（`Toolbar` sticky ／
  `ScenarioList` ／ `CreateForm`）。三個關鍵決定：
  (1) `workspace._best_return` 提升為公開 `store.best_return()`，API 與
  Streamlit 共用同一條規則——前端照抄一份等於給 QA1-03（#30）修好的
  「卡片數字對不上主圖」留後路；
  (2) `ResultRecord.best_return` 落盤＋`Storage.latest_summaries()`
  （Postgres 走 DISTINCT ON），清單不撈 view——一份 view 十萬字元等級，
  十個劇本就是 MB 級回應；
  (3) 「距到期天數」由後端算（錨點＝該月第三個星期五、今天＝紐約日曆），
  但**不進** `_scenario_json`——那個結構會原樣寫進 SCENARIO_CREATED 事件，
  事件是不可變的事實，不能塞隨時間改變的值。
  V1 的一次性分析搬到 `DemoAnalysis` 留在頁面下方（詳細頁是 V5，在它
  落地前那是唯一看得到候選池診斷的地方），V5 接手後整塊移除。
  兩份檢視均已處理（commits `7a3d620`／`5d02d08`）：規格面 8 項驗收
  7 項通過；標準面抓到一個真 bug——`_ensure_schema` 把建表與遷移同批
  送出，Postgres 會包成一個 implicit transaction，冷啟動撞上
  DuplicateTable 時遷移會跟著 rollback 但仍標記 ready，該 lambda 從此
  每次寫入都炸 UndefinedColumn。已拆成兩批各送各的。
  ⚠ **驗收第 1 項「功能列往下捲仍常駐可點」只完成一半**：釘選已驗證
  （E2E 量 `<header>` 的 y），但「可點」做不到——功能列上唯一的控制項
  是 V4 的 disabled 佔位鈕。**這條留給 V4（#52）一併關掉**
  ⚠ **已知、判斷為非阻擋**：既有 results 列的 `best_return` 是 NULL，
  卡片會顯示「—」（該符號在本專案語意是「該期零合格候選」，見附錄
  A10.2）。理由：V3 之前的部署版沒有任何 UI 路徑能建立劇本或呼叫劇本
  分析端點（只有不落盤的 `/api/analyze`），Neon 的 results 表應為空。
  若需求方看到已分析的劇本顯示「—」，就是這件事，重跑一次分析即修復
- **V4** [#52] — 刷新與分析：進度／失敗指引／新鮮度（commits `067983c`／`1aa60ea`）：
  後端 `POST /api/scenarios/{id}/analyze` 改名 `…/refresh` 並改回傳
  **卡片列**（與清單同形狀，`_row_json` 三處共用）——回整份 view 的話
  逐一刷新 N 個劇本等於在手機上拖 N 份十萬字元級回應；要看完整 view
  走 detail 端點。失敗分層落在錯誤主體：`_fail()` 讓 detail 變成
  `{stage, message}`，抓鏈與分析各自 try（原本包在同一個 try 裡，
  事後只能靠例外型別猜是哪一段），前端 `ApiError.stage` 據此給出
  「抓不到報價（可稍後重試）／分析沒跑完（重試多半無效）」兩種不同
  的話與就地重試鈕。前端刷新編排是「一條佇列、一個跑者」
  （`App.enqueue`）：三種時機（開站／建立劇本／功能列鈕）與卡片重試
  全走同一條，進行中追加的劇本會一起跑完、分母跟著變大——用「進行中
  就不理」的話，開站那輪還沒跑完就建立的劇本會靜靜停在「尚未分析」。
  新鮮度門檻 `STALE_AFTER_HOURS = 12`（一個交易時段 6.5 小時，12 小時
  ＝「這份報價已是上一個時段的」），讀不懂的時間戳當舊、尚未分析不算舊。
  三處已知取捨：(1) 開站 effect 加了 `started` ref 一次性閘——StrictMode
  在 dev 會把 effect 跑兩遍，等於每個劇本開站被分析兩次；(2) 卡片列
  **不帶** `source` 欄位（要 `latest_summaries()` 多一個欄位，屬儲存層
  schema 變動），資料來源留在 detail 的 view meta，V5 詳細頁顯示；
  (3) V3 驗收第 1 項「功能列可點」在本票補完（E2E 捲到底後真的按下去、
  斷言清單請求數增加）。

  **兩份檢視均已處理**（commit `1aa60ea`）。真 bug 一個：`create()` 用
  送出前的 `rows` 閉包蓋回整份陣列，建立期間刷新好的卡片會被打回未分析
  ——與 V3 檢視替 `archive()` 修掉的是同一類，已改函式式更新＋`rowsRef`，
  並補上會咬人的回歸測試（先手動把 bug 放回去確認測試會紅）。另修：
  抓鏈那段的 `except Exception` 縮回只認 `FetchError`（不然我們自己的
  bug 會被貼上「抓不到報價、可稍後重試」，正是本票要消滅的誤導，
  非 FetchError 照樣 500 且不編造 stage）；進度改 1-based（「第幾個」而
  非「跑完幾個」）；`request()` 加 90 秒逾時（serverless 上限 60 秒＋
  網路餘裕）——沒有它，一個永不回來的請求會讓佇列與按鈕永久卡死；
  新鮮度的「現在」改成每 5 分鐘走一次（原本只在渲染時取一次，頁面開著
  放隔天永遠不會長出「舊資料」）；`finally` 不再清空佇列；API 降級態
  測試改走**真的** Cboe→yfinance 降級鏈（原本注入一個 source=yfinance
  的假快照，等於自己驗自己）；新增分層字彙漂移測試（後端 `_fail` 的
  stage 必須同時被 `api.ts` 的 `STAGES` 與 `scenarios.ts` 的
  `failureLabel` 認得，否則靜默退化成「刷新失敗」）。
  **判斷維持現狀的兩點**：分析失敗訊息仍帶引擎例外原文（部署後需求方
  只能靠畫面診斷，這是唯一管道；本專案無多使用者、無機密）；`failures`
  不在封存時清除（封存失敗會回滾，清掉的話卡片回來時會看起來一切正常）
- **V5** [#53] — 詳細頁核心：Heatmap＋摘要＋追平標示（commit `496dac0`）：
  新增 hash 路由（`src/route.ts`，`#/s/{id}`）——不引套件也不用純狀態，
  hash 進瀏覽歷史，手機返回手勢／返回鍵、貼網址重整都自然可用。
  詳細頁 `ScenarioDetail.tsx`：摘要（現價／目標價＋所需漲幅／目標年月／
  策略／資料時間／**資料來源**）→ 主圖 `Heatmap.tsx`（baseline 期第 1 名
  候選）→ Long Call 追平價格三態 → 候選池診斷。純函式在 `heatmap.ts`
  （配色／格式）與 `detail.ts`（追平三態／策略名／候選標題），前端零
  金融計算不變。Heatmap 手機處理：價格欄 `position: sticky` 釘左，表格
  自己橫向捲（不縮字級硬塞），E2E 實測 `scrollWidth > clientWidth` 且
  頁面本身不橫捲。格子配色改**半透明**疊色——原 Streamlit 版往白色混，
  深色模式會變成刺眼亮塊。
  **一併移除 V1 遺留的一次性分析畫面**（`DemoAnalysis.tsx`，其 docstring
  本就寫明「V5 接手後整塊移除」）：候選池診斷搬進詳細頁（本來就是
  「這個劇本這次分析」的事）、資料來源改由詳細頁摘要顯示（雲端 Cboe
  可達性的驗證管道不中斷），`api.ts` 的 `analyze()` 隨之刪除；後端
  `/api/analyze` 端點留到 V10 cutover。
  **iOS 觀感補強**（需求方回報「畫面開始降級、沒原本驚艷」）：Large
  Title 32px、卡片加圓角 16＋淡投影、整張卡變成可點連結（`<a>` 而非
  onClick div，長按可複製、返回手勢可用）＋右側 chevron ＋按下
  highlight、功能列動作改導覽列膠囊鈕（原本自成一列的整寬按鈕吃掉一列
  卡片）、封存／重試改 tint 色文字動作（一張卡三個帶框按鈕會把視線從
  數字上拉走）、新增 `--fill`／`--card-shadow` token。
  新增 `tests/test_frontend_contract.py` 收攏前後端**字串值**的漂移防線
  （失敗分層 stage ＋策略代號顯示名），V4 那條 stage 測試一併移過去。

  **兩份檢視均已處理**（commit `a07ef28`）。最實的一條：直接開
  `#/s/{id}` 會永遠停在開站刷新**之前**的那份快照——詳細頁沒有功能列、
  也沒有第四種刷新管道可按。修法是把該劇本在清單上的 `latest_analyzed_at`
  當作 `refreshedAt` 傳進詳細頁並列入 effect 相依，刷新輪一跑完詳細頁
  就重取（換劇本才清空畫面，刷新重取不清空，免得閃一下）。其餘：
  詳細頁三個子區塊改吃 `view`／`candidate`（拿掉三處 `!`，baseline 第 1
  名只取一次）、主圖補上區塊標題、`contractLabel` 更名
  `catchupContractLabel`（它恆為 Long Call、不看腿的權別，舊名會誤導）、
  百分比大小抽成共用 `magnitude()`。可及性三項：卡片連結拿掉
  `aria-label`（那會**取代**內容當可及名稱，收益率等全被吃掉）改用
  `.sr-only` 補述、Heatmap 表格補 `<caption>`、`role="status"` 只留給
  真正會變的候選池警示。CSS 三項：刪掉一條其實沒作用的
  `.card-tap .row + .row`、sticky 價格欄用特異性取代 `!important`、
  `.caption.progress` 與 `.card .notice.error/.warn` 不再靠寫在後面決勝。
  測試品質兩項：刪掉「查得到 `.heatmap-scroll` 就算過」這種拿掉
  `overflow-x` 也不會紅的裝飾性斷言（真正守門的是 E2E 實測
  `scrollWidth > clientWidth`）、字彙漂移測試補 `re.S` 與抓不到時的說明。
  **判斷維持現狀**：S* ≤ 目標價的醒目提示用警示橘而非舊 Streamlit 的
  成功綠——「你這組價差被更簡單的 Long Call 比下去」對使用者不是好消息
  （已在 CSS 註解寫明理由，若需求方偏好綠色再改）；追平價差距
  （gap）的除法仍留在前端，與 D1 已記錄的取捨一致；`/api/analyze`
  端點無呼叫端但留到 V10 cutover 一併掃
- **V6** [#54] — 到期日結構：橫向按鈕＋Top 10 含腿價（commit `782c52f`）：
  詳細頁主圖之下的**唯一**到期日結構（舊「到期日分組比較」不搬遷，
  v3 #7' 裁示）。`ExpiryStructure.tsx`：到期日 chip 真正橫向並排可滑動
  （`overflow-x` ＋ `scroll-snap`，不是換行的按鈕堆），每顆下方是該期
  最高收益；點選只換下面的清單，**主圖不動**（QA1-06 既有裁示）。
  Top 10 窄列：名次＋⚠ 徽章＋買賣履約＋劇本報酬，第二行直接列出買腿
  買入價（Ask）／賣腿賣出價（Bid）／淨成本（引擎 `natural_cost`，最差
  成交口徑）——三個價格在**收合狀態**就看得到，要比較幾組候選時不必
  逐一展開。展開用原生 `<details>`：純瀏覽器行為，不重繪、不跳動頁面
  位置（E2E 實測 `window.scrollY` 不變、主圖內容不變）。純函式在
  `expiry.ts`（`expiryOptions`／`legPrices`／`resolveExpiry`），按鈕上的
  數字與清單第 1 名取自同一個陣列、不可能對不上。
  **一併處理的重複**：`CandidatePool` 的「該期組數過少」警示移到本層
  （原本固定講 baseline 那期，現在跟著使用者切換的到期日走），CandidatePool
  只留「該期有效組數」那一列數字——同一句話在一頁上出現兩次，第二次
  只是噪音；兩條相關測試隨之搬家，另外兩條變成恆真的斷言（警示已不在
  該元件）已刪除或改寫。

  **檢視回饋已處理**（commit `3f4e8d7`）。檢視抓到上面那個搬遷**漏了一個
  情況**：主圖固定是 baseline 期第 1 名，警示改成跟著使用者切換的到期日
  之後，一旦切到別期，baseline 池只有 1 組這件事全頁沒人再提——頭條數字
  失去它的但書。修法是主圖區自己帶一句（措辭與清單那句不同、各自指向
  自己描述的東西），`CandidatePool` 那一列同時正名為「主圖到期日有效
  組數」，消除「該期」在同一頁上有兩個意思。其餘：`role="tab"` 改回
  `aria-pressed` 按鈕（沒有 tabpanel／aria-controls／方向鍵巡覽就不該
  宣稱自己是 tab widget）、`role="status"` 改常駐容器（插入時就有內容的
  live region 不一定會被唸）、`validPairsForExpiry` 從 `api.ts` 移進
  `expiry.ts` 與 `expiryOptions` 共用一份查找、補上候選列的展開角括號
  （原本完全沒有「可展開」的線索，而註解還寫著一個不存在的 `::after`）
  並刪掉 `display:flex` 下本來就不會生效的 `::marker` 規則。測試四項：
  「前十名最多十列」名稱與 `toHaveLength(12)` 的斷言互相矛盾已正名、
  「展開一列不影響其他列」只驗到瀏覽器原生行為（本專案任何改動都弄不
  紅它）改成驗「展開的是那一列自己的候選矩陣」、到期日 chip 的橫向捲動
  補 E2E（複製成十二期逼出真捲動，並確認整條高度＝一顆按鈕高＝沒換行）、
  「不跳動頁面」原本在 Playwright 自動捲動之後才取值必然相等，改成先
  `scrollIntoViewIfNeeded` 再量。另刪掉兩條手捏的狀態（引擎不可能送出
  某一期 0 組／空候選，`expiry_counts` 與 `expiry_top10` 出自同一個迴圈）。

  ⚠ **一併修正專案紀錄自己的錯**：V4／V5／V6 四筆 commit SHA 記的都是
  `--amend` **之前**那顆（先 `rev-parse` 再 amend），其中三顆已不在分支
  歷史上。全部改正並加驗：`git merge-base --is-ancestor <sha> HEAD`
- **V7** [#55] — 最好／最差價位三價位對照 ←**下一張**（被 #51、#53 擋，
  兩者皆已完成）
- **V8** [#56] — 分析報告新版型＋原始資料（被 #53 擋，已完成；#49 亦已
  完成——施工依據＝`docs/research/option-strategy-report-conventions.md`
  §4，**含 §4.2 A2 的補序列化清單**）
- **V9** [#57] — Spread 歷史走勢圖：日粒度＋固定 y 軸（被 #53 擋）
- **V10** [#58] — Cutover：移除 Streamlit、文件、全站驗收（被 #54–#57 擋）

> 全部票做完＋需求方實機驗收通過才開 PR（V10 驗收清單）。

### ⚠ 未決事項：盤後候選池仍會被餓死（2026-08-04 發現，票未開）

**症狀**：TLT／2028-05／120，**盤中**跑得到「買100/賣120、2567%」（合理），
**盤後**跑變成「買77/賣85」（近價位、報酬低）——與 feedback-v3 第 4 點
同一個病徵。

**診斷（待需求方以 Cboe 原始資料確認）**：FB3-01 換 Cboe 只治好一半。
先前「Cboe 盤外凍結報價不歸零」的結論是**過度推論**——當時的實測樣本
幾乎都是近月價內合約（那些確實有 bid），但遠月價外合約盤後根本沒有
掛單、bid 就是 0，仍會被 `filters.quote_ok` 的 `bid > 0` 濾掉，候選池
於是只剩近價位的。現價 82 時，77（價內）與 85（貼現價）活著，
100/120（遠月價外）被殺。

**待確認**：請需求方開 `https://cdn.cboe.com/api/global/delayed_quotes/options/TLT.json`
查 `TLT280616C00100000` 的 `bid` 是否為 0。

**2026-08-04 研究結論（`docs/research/cboe-field-semantics.md`，以 GitHub 上
一份真實 758 筆 Cboe 全鏈為樣本、經買賣權平價自我驗證）——推翻了先前
三個猜測，修法方向以此為準**：

1. **主要殺手實測是 `OI ≥ 10` 硬門檻，不是 IV、也不是 spread。** 同一份
   全鏈跑本 app 四道過濾：DTE 49 從 26 筆剩 1 筆全死在 OI；DTE 525
   （LEAPS）21 → 19，IV 與 spread 幾乎沒殺人。OI 是 OCC 收盤後結算、
   隔天早上才發布的 **T+1 落後數字**，回答「昨天收盤有多少未平倉」而
   非「現在有沒有人掛單」；樣本裡每個天期都有 `OI=0 但 volume>0`。
   Cboe 其實有給 `bid_size`／`ask_size`，adapter 目前沒取用——那才是
   「現在有沒有人掛單」的直接證據
2. **`max(0.10, 0.15 × mid)` 對 LEAPS 是寬鬆的，不是元凶**：相對價差
   中位數 ≤30 天 6.6%、>365 天僅 3.9%。長天期絕對價差寬但單價高，
   相對反而最窄（先前「15% 對 LEAPS 太嚴」的算例，單看成立、當診斷錯）
3. **`iv=0.0 → None` 的映射正確、應保留**（先前說它是 FB3-01 引入的
   迴歸，不準確）。iv=0 是「解不出來」的哨兵值（零時間價值、vega≈0），
   映射成缺值沒錯，錯的是讓這種腿還得過 IV 這一關。32 筆兩側有報價的
   iv=0 call 有 30 筆數學上無解，自己反推只救得回 6%——該做的是讓無
   時間價值的腿**旁路** IV，不是寫 solver
4. last-price 降級口徑（`docs/research/option-chain-data-sources.md`
   §4.3）依然是選項之一，但依上述已非首選

**下一步**：FB4-01（#60）已把真實過濾數字攤在畫面上。**拿到那組真實
數字之後**，才開票修過濾器——這會動到 T12 已定案的成本／品質口徑
（附錄 A14.2），**需要需求方裁示，勿自行施工**。

**⚠ agent 自行抓真實鏈這條路走不通（2026-08-04 查證結論）**：
容器的出口閘道擋掉 `cdn.cboe.com`、`*.vercel.app`、`home.treasury.gov`
（CONNECT 403；`curl "$HTTPS_PROXY/__agentproxy/status"` 的
`recentRelayFailures` 可見 `connect_rejected`）。

**不要再嘗試繞或重試**，也不要再叫需求方去「環境設定」找開關：
- 需求方實測找不到可點的網路政策設定——該政策多半只能在**建立環境時**
  選定，不能事後改
- 需求方找到的 permission 設定管的是「agent 可以用哪些工具／網域」，
  但 403 發生在更上游的閘道，請求根本走不到權限判斷這一層
- WebFetch 與 curl 兩條路都實測過，同樣 403，且不會跳出任何授權提示

**因此拿數字只有一條路：需求方按一次按鈕。** 部署版頁面下方的
「一次性分析」跑的正好是 TLT／2028-05／120（＝回報的那個案例本身），
按下去下面就會出現「候選池」區塊的逐關數字。拿到數字才開票修過濾器。

### 第四輪反饋（2026-08-04，需求方看 Vercel 部署版後回報，票未開）

需求方回報四項。**已逐項比對 spec #47 與剩餘票 V7–V10：四項全部
沒有被涵蓋，都要另外開票**，不會隨後續票自動解決。

1. **年月選擇器不好用**（前端，小）
   - 1-1：要按右邊日曆圖示才展開；需求方要的是**點欄位本身**就從下方
     彈出選擇器
   - 1-2：年份要預設 `20__`，不要每次重打「20」
   - **現況**：`src/CreateForm.tsx` 用原生 `<input type="month">`
     （V3／#51 的裁示：「自己刻一個彈窗只會比系統的更難用」）。桌面
     Chrome 的原生行為就是要按圖示，且**原生元件無法做 `20__` 遮罩**。
     要滿足這兩點只能自刻年月選擇器，等於推翻 V3 當時的裁示
   - spec #47 story 2（「點擊彈出只有年月的選擇器」）意圖有涵蓋，但
     實作票 V3 已完成並結案，剩餘票無人再碰 `CreateForm`
     （V7／#55 會加最好／最差價位欄位，是唯一會再動到這個檔案的票）

2. **過濾器誤殺一狗票，很多日期出現不合理收益率**（引擎，嚴重）
   - **spec #47 明文列為 Out of Scope**（「引擎（估值、排名、過濾、
     資料源）邏輯變更——本輪只消費」），剩餘票一張都不會碰
   - 診斷早已完成，見下方「⚠ 未決事項：盤後候選池仍會被餓死」與
     `docs/research/cboe-field-semantics.md`：**主要殺手是 `OI ≥ 10`
     硬門檻**（T+1 落後數字），Cboe 給的 `bid_size`／`ask_size` 才是
     「現在有沒有人掛單」的直接證據，adapter 目前沒取用
   - 原本卡在「等需求方按按鈕拿真實數字」——**該前提已由 758 筆真實
     全鏈研究解除**。剩下的阻擋只有「會動到 T12 的成本／品質口徑
     （附錄 A14.2），需要需求方裁示修法方向」

3. **外觀**（前端）
   - 3-1：首頁要**桌面 20/80**（左劇本庫、右主畫面）。**spec #47 是
     手機優先**，30 條 story 裡沒有任何桌面版面要求；需求方記憶中的
     20/80 是舊 Streamlit 版的 QA1-02（#29），沒有被帶進新 spec
   - 3-2：劇本庫要可收放（預設展開、可縮到最左）。spec 完全沒提
   - 3-3：整體美觀度再加強。需求方要參考網站連結自己挑方向——連結已
     於 2026-08-04 提供（Mobbin／Land-book／Godly／Dribbble 等）
   - **⚠ 2026-08-04 需求方裁示：整個第 3 項（3-1／3-2／3-3）延後。**
     原話「目前我們的長相還可以，先把功能拼出來吧，要做好看後面再來
     研究」「我看你貼的網站，其實也沒有多好看」。**不開票、不施工**，
     優先做完功能票（V7–V9）。外觀待需求方日後主動提起才重啟

**優先序（2026-08-04 需求方裁示）**：過濾器（第 2 項）插隊最優先 →
功能票 V7–V9 → 年月選擇器（第 1 項）→ 外觀（第 3 項，已延後）。
過濾器修法方向需求方裁示為「**先跑 research 再決定**」，研究進行中。

### 下一版 MVP（本輪明確不施工，已立案）

- **多使用者隔離** [#59]（2026-08-04 需求方裁示）：現在 API 有可寫入的
  共用儲存但無任何保護，正式部署會是公開的。需求方要的是「自己只看得到
  自己的」——讀使用者 id 或發憑證皆可，屆時再裁示。該票**未標**
  `ready-for-agent`，`/implement` 不會取到

**第三輪反饋**：`docs/user-feedback-v3.md`（2026-08-02，需求方測試
部署版後由 GitHub 直接 commit 進 master）。共 10 點：

- **第 4 點（嚴重 bug）已診斷完畢並拆票**（2026-08-02，需求方同意
  方案）：排名公式沒壞，真因是 Yahoo 盤外把 LEAPS bid/ask 歸零、
  品質過濾把遠期候選池殺光只剩 deep ITM（重現：2028/6 期只剩 75/80
  一組、40.8%，與回報的 41% 一致）。修法＝FB3-01 [#44] 換 Cboe 主源
  ＋FB3-02 [#45] 候選池過少警示（見下方待辦）。資料源調查全文：
  `docs/research/option-chain-data-sources.md`；需求方已實測 Cboe
  端點盤外報價凍結不歸零。「刷新等 3 分鐘」預期隨 #44 一併改善
  （Cboe 一個 GET 回全鏈 vs yfinance ~20 次請求）
- 其餘各點尚未逐點確認，多與下一階段前端重練重疊（第 5 點 iOS
  風格＝已裁示方向、第 7 點釘選功能列＝QA1-14 範圍），待 `/to-spec`
  時合併考量，避免在舊 Streamlit 前端上做白工

#### FB3 修正輪（已完結，PR #46 已 merge；保留供追溯）

- **FB3-01** [#44] — Cboe 延遲報價換主源（commit `69dd99d`）：新增
  `option_chaser/data/cboe.py`（OCC 解析＋欄位映射＋stdlib urllib，
  iv=0.0/last=0.0 映射 None 為缺值口徑統一、不改過濾結果；任何失敗
  收斂成 FetchError），`service.fetch_and_save` 改 Cboe 優先、失敗退
  yfinance、快照 `source` 如實記錄。測試 fixture 取自需求方實測回傳。
  ⚠ 部署後待確認：Streamlit Cloud／未來 Vercel 的出口 IP 能否連
  `cdn.cboe.com`（沙箱 proxy 擋住無法代測，備援鏈已就位）
- **FB3-02** [#45] — 到期日候選池過少警示（commit `2ead43e`）：該期
  有效組數 < 3 時 `render_expiry_top10` 顯示「⚠ 該期僅 N 組候選通過
  品質過濾」；讀 T9 既有 `expiry_counts`，純顯示層

> 沿用規則：反饋要先逐點跟需求方確認打算怎麼改、為什麼，確認完才
> 開票施工；`/implement` 進行中沒遇到需人類裁示的事就不停。

### 施工依據

- 需求與決策紀錄：`docs/modifyRequestV1.md`（附錄 A1–A12）
- 路線圖與依賴地圖：`docs/modify-route-map-v1.md`
- 每張票的施工細節以 GitHub issue 為準（`L26041040/option-chaser`）
- **產品使用反饋：`docs/QA-v1.md`** — 第一次討論產品使用反饋的紀錄
  （2026-08-02，需求方手機實機操作 Streamlit 部署版後回報）。
  已於 2026-08-02 分析拆票完成：tracking #27、子票 #28–#39、
  下一版 #40/#41、待裁示 #42（見上方待辦清單）。
  §3-1 主動刷新為正面回饋、數據與 OPC 出入可接受，均不開票。

## 環境

- **⚠ 容器會不定時倒退回較早的提交**（2026-08-04 已發生兩次，連 `.venv`
  套件與本地 Postgres 資料目錄一起消失）。發現 `git log` 對不上時：
  `git stash -u`（若有未提交的工作）→
  `git fetch origin claude/implement-tfm9oa` →
  `git merge --ff-only origin/claude/implement-tfm9oa` → `git stash pop`。
  **所有工作都推到 origin，倒退不會掉東西**。接著跑
  `sh scripts/dev_env.sh` 重建測試環境——不重建的後果是**靜默**的：
  儲存契約測試的 Postgres 那一半會被跳過，全套仍是綠的卻少驗一個實作
  （正常全套是 582 條；掉到 5xx 出頭就是 Postgres 那組沒跑）
- 跑測試：`OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest"
  PYTHONPATH=. .venv/bin/python -m pytest`
  （`pyproject.toml` 的 `packages.find` 只收 `option_chaser*`，`webapp`／
  `api_app` 不在裡面，靠 PYTHONPATH 匯入。沒有 `OC_TEST_DATABASE_URL`
  就只跑記憶體假體那一半）
- 已知偶發：`test_render_spread_history.py::test_chart_does_not_crash...`
  是 Streamlit AppTest 的逾時 flake，單獨重跑會過
- 建 venv：`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e ".[gui,api,yf]" pytest`
  （**`api` extra 必裝**：HTTP API 是後端唯一測試接縫，缺 httpx 會讓
  契約測試整組紅燈——這是刻意的，不要改成靜默跳過。**`yf` extra**＝
  備援資料源 yfinance，已移出核心依賴以免 pandas/numpy 進 serverless
  函式——pyproject 的核心依賴就是 lambda 實際安裝的清單）
- 前端（V1／#48 起）：`npm install`；`npm run typecheck`／`npm test`
  （Vitest 元件測試）／`npm run e2e`（Playwright，手機 viewport）／
  `npm run build`。沙箱有預裝 Chromium 時用
  `PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium npm run e2e`
- 部署與契約樣本：見 `docs/deploy-vercel.md`
- **部署網址只認這一個**（每次 push 都會自動產生一個一次性 preview
  網址，那些不要收藏）：
  `https://option-chaser-git-claude-imp-aef368-ofriedoriceo-5352s-projects.vercel.app`
  ——分支別名，永遠指向工作分支的最新一次部署。
  master 的 production 網址在 V10 merge 前必定是 ERROR（master 還沒有
  前端程式碼），屬預期，不必理會
- 全套測試現為全綠（舊紀錄提到的 5 個 streamlit 版本漂移失敗已隨 T2 改寫消失）。
