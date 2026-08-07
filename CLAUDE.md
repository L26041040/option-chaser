# Option Chaser

## 規則

**每做完一張 ticket，就更新下面的「專案紀錄區」**——把該票移到已完成、標出下一張。

**全部 ticket 做完才開 PR、merge 回 master**，中途不要主動開。

**除非使用者主動要求，否則不准執行截圖或把截圖貼上對話**（跑 Streamlit／Playwright
截圖驗證 UI 極度耗費 token）。窄 viewport／版面等視覺驗收，一律留給需求方自己用
瀏覽器確認，或等使用者明確要求才做。

只有這三條。

## 專案紀錄區

> **現況總覽（2026-08-07，寫給接手的新 session 看）**：T1–T12、QA1
> 系列、D1、FB3、FB5、V1–V10、QA-v2（#67–#75）、**MVP V2 手機版劇本庫
> （M1a–M6，#78–#84）全數完結，已 merge 回 master**（PR #85，squash
> merge commit `8b52f41`，需求方真機驗收通過後 2026-08-07 merge）。
> production 網址 `option-chaser.vercel.app` 現在對應代表候選＋燈號＋
> Compact Row＋捲動還原全部到位的手機版劇本庫。緊接著同一天開始
> **Trash 語意＋利率顯示修正**這一輪（見下方「Trash 語意＋利率顯示
> 修正」小節）：需求方三點反饋（Archive 改真正 Trash、利率 fallback
> 顯示語意）、`/to-tickets` 拆成 RC1＋TR1–TR6（#87–#93）。**RC1、
> TR1、TR2、TR3、TR6 已完成**，剩 TR4／TR5（垃圾桶畫面的還原與永久
> 刪除操作）施工中。中間穿插的
> 「目前狀態（2026-08-02）」等舊日期標頭是歷史留存，**以此段與下面
> 對應小節末尾的紀錄為準，不要被舊標頭誤導**。下一階段候選：
> **多使用者隔離** [#59]（未標 `ready-for-agent`，需求方裁示後才開工）、
> 外觀優化（QA-v2 需求方已明確裁示延後，待主動重啟）、Dashboard 佔位區
> 實際內容（跨劇本比較功能確定後另開票，spec #77 Out of Scope）。
> 環境操作細節（venv／本地 Postgres／容器倒退修法／部署網址）見檔案
> 最底下「## 環境」一節，已同步更新。

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
- **V7** [#55] — 最好／最差價位三價位對照 ✅（commit 待補）：劇本可選填
  最好／最差價位，詳細頁對主圖那組候選並列三個價位的報酬。引擎新增
  `ranking.return_at_price()` 為唯一計算點；`AnalysisParams`／`Scenario`
  各加兩個選填欄位（預設 None，既有劇本與既有行為不受影響）；Postgres
  遷移與建表分兩批送（沿用 V3 教訓）。排名口徑不變，由測試把關。
  方向合理性（看漲時 最差 <= 目標 <= 最好）擋在 API 邊界，前端同一套
  規則先擋一次省往返、後端仍是權威。
  ⚠ **檢視抓到一個真 bug 並已修**：`return_at_price` 原本對價差用日曆
  錨點估值，但 T3（#17）的既有裁示是**各 Spread 用自身到期日**
  （`valuation.evaluate_spread`）——只有 baseline 那一期兩者重合，其餘
  到期日的三價位全錯（實測 2026-11-20 那期：0.874 vs 正確的 1.857）。
  原測試剛好只挑到 `expiry == anchor` 的案例，**是空斷言**。已改為
  參數化涵蓋錨點前／上／後三種到期日，並讓 API 測試掃全部到期日的
  全部候選；已驗證新測試對舊實作會紅燈。契約樣本重產
  ⚠ **票上「建立／編輯表單」的編輯路徑不存在**（全站無 scenario 更新
  端點與編輯 UI），本票不新增——編輯功能未被任何 spec 要求過，要做
  應另開票
- **V8** [#56] — 分析報告新版型＋原始資料查看/下載 ✅
  （commits `8faf76f`／`a3ec3fd`）：後端序列化補齊 R1 §4.2 A2 明列的
  四項（值早算好、只是沒吐）——`store._candidate()` 新增 `l2`／`l3`
  （買價指引天花板）、`cons`（評語代價，pros 依 §4.2 C 裁示不補）、
  `guidance_warnings`（`valuation.guidance_judgments`／
  `spread_guidance_judgments`）；`serialize_result()` 每策略新增
  `methodology_text`（`report.methodology_lines()`，與 CLI 報告尾註
  同一事實來源，免責從中段移到尾端）、`disclaimer_text`（R1 §4.4.4
  擴充版，CLI 精簡版維持不變）。新增 `store.raw_snapshot_json()`／
  `data.snapshot.snapshot_from_dict()`（還原 `Storage.get_snapshot()`
  的 dict 形式，與 `load_snapshot` 共用同一段還原邏輯）與兩個 API
  端點 `GET /api/scenarios/{id}/raw-data`（JSON 查看）／`/raw-data.csv`
  （下載，內容走既有 `snapshot_to_csv`）——兩者皆跟著劇本「最新一次
  結果」的 `analyzed_at` 走，不接受指定歷史版本。
  前端新增兩個進階區元件（詳細頁預設收合）：`AnalysisReport.tsx`
  對齊 R1 §4.1 章節骨架（結論先行、方法論墊底、最大獲利與最大損失
  同框、情境最壞與劇本報酬並排），刻意不重複頁面上方已無條件顯示的
  數字（目標/追平價格/策略/P·L矩陣）；`RawData.tsx` 展開才打
  `/raw-data`，逐筆合約表＋CSV 下載連結（純 `<a href download>`）。
  新增純函式（`detail.ts`）：`reportConclusion`／`maxPayoutRatioText`／
  `costPctOfSpot`／`breakevenDistancePct`／`completionThresholdText`／
  `SCENARIO_NAMES`（新增字彙漂移防線測試）。

  **兩份檢視均已處理**（commit `a3ec3fd`）。Spec 檢視抓到三個真缺口：
  (1) ⑥ 方法與假設漏掉 R1「[模型假設]→⑥」重排——利率／IV 情境／
  Delta 門檻／最低要求報酬率從沒進新版型，`AnalysisParams` TS 型別
  補上這些早就在契約裡的欄位；(2) ⑤ 進場執行原本每隻腿只印「最差
  成交會用到的那一邊」（買腿只印 Ask、賣腿只印 Bid），R1 §4.2 A
  明講逐腿報價要雙邊都給，新增 `LegRow` 印完整 Bid/Ask/IV；
  (3) 剩餘天數（`days_to_expiry`，R1 §4.2 B 明列的新增顯示項）完全
  漏掉，`Candidate` 型別漏了這個早就序列化的欄位。Standards 判斷後
  採納兩項：`store.py` 生成式借用 `p` 當迴圈變數跟函式自己的
  `p: AnalysisParams` 參數同名，改名 `pt`；`cons`／`guidance_warnings`
  原本攤成同一堆看不出差別的警示列表，改用 CLI 既有的「代價:」／
  「警示:」文字區分並拆成兩個獨立區塊
- **V9** [#57] — Spread 淨成本走勢：日粒度＋日/週/月切換＋固定 y 軸 ✅
  （commit `dbfa8be`）：把 T11（#25，Streamlit 版）既有的
  `workspace.spread_history()` 聚合邏輯（依 Spread 身份鍵跨快照聚合、
  缺席快照如實呈現為斷點、不插值）抽成 `store.spread_cost_history
  (views, candidate_key)`——新架構 `Storage.result_history()` 回傳
  `ResultRecord`（`.view` 已是完整 view dict），沒有檔案路徑可讀，
  `workspace.spread_history()` 改為委派本函式，兩邊共用同一份邏輯。
  新增 `GET /api/scenarios/{id}/history?candidate_key=...`，唯讀。
  前端新增第三個進階區元件 `SpreadHistory.tsx`（詳細頁預設收合），
  跟隨主圖那組候選（`baselineTopCandidate`，QA1-06 既有裁示），單腳
  候選沒有 Spread 身份鍵，整塊不顯示（T9 附錄A13 既有 MVP 範圍）。
  純函式（`spreadHistory.ts`）：`downsampleHistory`（日／週／月降
  採樣，同組取最後一筆——票上明列的簡化口徑）、`yAxisDomain`（固定
  [最低×0.85, 最高×1.15]）、`chartPoints`／`contiguousRuns`（斷點切段，
  段間不連線）。手刻 SVG 折線圖——本專案沒有裝圖表函式庫，沒有縮放／
  平移手勢。新增 `.segmented`／`.segmented-option` CSS（iOS 風格分段
  控制項，跟到期日 chip 形狀不同，不重用 `.chip`）。

  **兩份檢視均已處理，皆無真 bug**（Standards：extraction 確實消滅重複、
  非搬移；手刻 SVG 與新 CSS 皆為合理判斷，非過度工程；Spec：AC 全數
  達成，聚合邏輯的「同一天取最後一筆」確認是依時間而非陣列位置，斷點
  切段在 render 層與 E2E 都驗證過真的不連線）。**兩份檢視各標記一項
  「非缺陷、供確認」的既有判斷，本輪判斷維持不改**：
  (1) 完全沒有縮放／平移手勢——票上原文「y 軸固定...不隨互動滑動」
  是對「若有互動」的約束，不是「必須要有互動」的要求；本專案沒有圖表
  函式庫，從零手刻手勢操作是遠超出票面範圍的工程量，日／週／月切換
  才是票上明列的互動需求，已達成；
  (2) y 軸範圍依「目前顯示的降採樣序列」算，不是「原始日粒度序列」——
  切換粒度時範圍可能跟著變。這是多數行情圖表（含 TradingView 等）換
  時間尺度時的常態行為，非本票造成的缺陷
- **V10** [#58] — Cutover：移除 Streamlit 前端、文件更新、全站驗收 ✅
  （commits `9115452`／`d899682`）：移除 `webapp/`（Streamlit 前端）及
  其 10 個專屬測試檔案（`test_webapp_*.py`、走 `webapp.render` 的
  `test_render_*.py`／`test_card_render.py`／`test_heatmap_colors.py`）；
  `tests/test_redlines.py` 的禁詞掃描與年月守則測試收斂回只掃
  `option_chaser/`（範圍不變，只是拿掉已刪除的 webapp 路徑）；引擎與
  其測試不受影響，全套維持全綠。`pyproject.toml` 移除 `gui`
  （Streamlit）extra；`scripts/dev_env.sh`／`.devcontainer/
  devcontainer.json` 跟著更新（後者原本還停在 `streamlit run
  webapp/app.py`，改成 `.venv`＋`npm run dev`）。README（英文＋中文）
  的「Web GUI」「多劇本工作區」兩節改寫成新架構（Neon Postgres 取代
  Streamlit 檔案式 workspace），`docs/deploy-vercel.md` 修正一處過期
  陳述。新增 `docs/v10-acceptance-checklist.md`：逐條對照 spec #47 的
  30 條 user stories，24 條 ✅ 自動化覆蓋、4 條 ⚠ 需求方需在真機／環境
  上覆核（#11 刷新變快主觀感受、#15 橫向並排視覺印象、#27 y 軸切換
  粒度時的範圍變動、#28 Neon 連線狀態）、2 條 ❌ 明確未完成但皆為需求方
  本人已裁示的延後項（#2 年月選擇器、#29 iOS 外觀優化），不是本票疏漏。

  **兩份檢視均已處理**（commit `d899682`）。真遺漏一個（Standards）：
  `Dockerfile`／`compose.yaml` 這次提交完全沒碰到，但兩者都在建置／
  執行舊 Streamlit（`COPY webapp`、`pip install ".[gui]"`、
  `streamlit run webapp/app.py`），`webapp/`／`gui` extra 都已刪除，
  建置會直接失敗——新架構部署路徑只有 Vercel，沒有 Docker 這條路，
  直接移除兩個檔案而非修復。另修正 `.devcontainer/devcontainer.json`
  裝到系統 Python、跟全專案 `.venv` 工作流不一致的問題，以及 CLAUDE.md
  本身（雖不在 AC 明列的 README／deploy 範圍內，但檢視判斷它也算
  「目前具權威性文件」）殘留的 `gui` extra 指令與指向已刪除測試檔案的
  已知偶發備註。

**全部票（T1–T12、QA1 系列、D1、FB3、FB5、V1–V10）已完結。** 依既有
規則，這輪不主動開 PR——`docs/v10-acceptance-checklist.md` 已備妥，
等需求方以手機實機走一遍、給出 go-ahead 後才開 PR、準備合併回 master。

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

### 過濾器修正輪（spec #61，2026-08-04 發布，票已開）

**起因**：需求方回報「某些到期日的收益率正常、某些不是，很明顯就是
篩選器在作怪」。判斷正確——實測逐到期日淘汰率差異極大（DTE 49 從
28 筆砍到剩 **1** 筆，DTE 525 卻是 21→19）。一個到期日只剩 1 組候選時，
該期「最高收益」在定義上就是唯一倖存者，不是比較結果。

**核心裁示（需求方，2026-08-04）**：把「品質門檻」改成「品質標示」。
原話——

> 「如果根本不篩，那我們還要篩什麼？反正回傳的都是有人出過的價不就好了？」

> 「我們能做的，就是如實且保守的計算當下的最低保守收益，而不是硬要先
> 刪掉這些資料。因為你不可能把交易市場的 corner/edge 全刪掉，交易市場，
> 特別是期權市場，本質上是非凸的！」

架構支持：主數字採**最差成交口徑**（T12／附錄 A14.2），實測 `net_worst`
是 Cboe 理論價的 1.15–2.10 倍——價差爛的候選成本已被誠實算高、報酬率
已被誠實壓低，再用硬門檻刪掉是同一件事罰兩次。

**明確否決的四個方向（附理由，除非有新證據不再重啟）**：
1. `bid_size`／`ask_size` 取代 OI——實測 934 筆 `bid_size=0` 恰好僅在
   `bid=0` 時發生，與現有 `bid>0` 是**同一個條件**（套套邏輯）；且 Cboe
   規定造市商最低報 10 口，size 量的是報價義務非真實深度
2. 成本下限（$0.30／$0.50）——需求方指出近月價外合約單價本就低，會整批
   誤殺；且最差口徑已是保守下緣，再加敏感度上緣反而往樂觀加料
3. 凸性檢查——實測 50/305 違反，訊噪比太差；期權市場本質非凸
4. 報價新鮮度過濾——Cboe **不提供逐合約報價時間戳**（原始欄位與 OpenBB
   匯出兩路確認）；`last_trade_time` 是成交非報價時間，600 筆雙邊報價中
   244 筆從未成交，當代理會誤殺正常掛單

**⚠ 我先前轉述研究時的錯誤，已更正**：「逐一移除四道關卡榜首都不變」
量的是**全鏈全域第一名**，而畫面呈現的是**各到期日各自的 Top 10**。
一期從 28 筆砍到 1 筆時該期冠軍必然改變。指標選錯，需求方的判斷比我
當時的轉述準確。

**⚠ 研究母體與實際情境有落差**：研究以全鏈（DTE 0–525）為母體，但
`timeframe.select_expiries` 只取錨點前後至多五檔——需求方指出「近月
樂透票」在遠月劇本裡結構上不會出現，故研究舉的 DTE=7 / 1900% 例子不
代表實際使用情境。

**仍未證實**：盤後遠月價外合約大量 `bid=0` 是否另外造成一波餓死。手上
逐期樣本皆為盤中。取得方式＝收盤後在部署版跑一次，看候選池區塊數字。
本輪變更不依賴該答案。

**研究文件**：`docs/research/option-liquidity-filtering.md`（本輪新增）、
`docs/research/cboe-field-semantics.md`（逐到期日淘汰實測）。

**票（依序）**：
- **FB5-01** [#62] — 移除 OI 硬門檻與恆真的成交量條件 ✅
  （commits `b93b4b1`／`ce16204`）：`filters.py`
  的 `oi_volume_ok` 整關移除，只剩報價／IV／Spread 三關；`AnalysisParams`
  移除 `min_oi`／`min_volume` 兩欄，CLI 對應的 `--min-oi`／`--min-volume`
  一併移除（不留「看起來在做事、其實沒有」的死旗標）；未平倉量仍隨
  候選序列化（`OptionContract.open_interest`／`store._leg`），只是不再
  有生殺大權。分析報告尾註同步改寫。README 兩處 CLI 說明同步更新。
  Golden fixtures（4 份）與契約樣本重產——`xyz_v2_snapshot.json` 原本
  被 OI=5／OI=3 卡住的兩筆合約（call strike 100.5、put strike 90）現在
  進榜，可在 `golden_long_call.txt`／`golden_long_put.txt` 的 diff 直接
  看到候選數 6→7。測試：引擎層（`test_filters.py`，含 spec #61 明列的
  回歸防護——9 組「報價正常但 OI 個位數」的合約全數留在池子裡，不再
  塌縮成唯一倖存者）＋HTTP API 層（新增 `test_api_filters.py`，同一份
  fixture 走 `/api/analyze` 端到端驗證，pin 住 `filter_report`
  `{total:10, passed:7}`）。`test_service.py` 原本靠 `min_oi=10**9`
  製造「全數落空」的測試改用依然是硬門檻的 `spread_floor=0` 達成同效果。
  ⚠ **檢視回饋補了兩項規格斷言**：(1) 票上寫的是「各到期日的候選池
  數量」，原測試只驗整批合約數（6→7），改讀 `expiry_counts` 直接證明
  只有真正被 OI 卡住的 2026-10-16 那期漲了（4→5），另兩個到期日各只有
  1 張合約、數字原封不動；(2) 「排名公式不變由測試把關」原本只驗成本
  口徑，排名公式只是「ranking.py 沒被動過」的默示假設。新增測試利用
  平衡型級距修法後恰好有 4 組候選競爭的事實——新留下來的 100.5
  （報酬率 2.841）確實比 100.0／105.0／95.0 都高，若排名公式或排序
  方向壞了，中選的不會是它
- **FB5-02** [#63] — 買賣價差寬度降級為品質標示 ✅
  （commits `c3caf7e`／`e31891c`）：`filters.py` 移除 `spread_ok` 硬關卡
  （只剩報價／IV 兩關），公式原封不動搬進新公開函式 `is_spread_wide()`；
  `service._v4_fields` 用它多加一個 OR 項到既有的 `CandidateView.
  quote_warning`（沿用既有機制，不新造一套）。「標示內容說得出寬到
  什麼程度」不新增序列化欄位——既有的 `friction`／`friction_amount`
  已是量級資訊，`report.py` 另補逐候選文字警示（單腿與價差兩路徑，
  比照既有「今日無成交」警示寫法）。前端零變更（`CandidatePool` 對
  `filter_stages` 泛型渲染）。Golden fixtures 與契約樣本重產，README
  兩處 CLI 說明同步更新
  ⚠ **檢視抓到一個真的會錯的舊斷言**：`test_service_v4.py::
  test_quote_warning_friction_over_25pct` 原本斷言只含兩個 OR 項，
  少了新加的 `wide_spread`；全套測試仍綠純粹是這份 fixture 的候選剛好
  沒踩到「價差寬但 friction 不到 25%」的交集，不代表公式沒變。已補上
  `_any_wide_spread` helper 與正確的三項 OR。另外票上「以既有 fixture
  斷言……且帶標示」原本「進得了榜」與「帶標示」兩半分別證明在不同資料
  上（前者用真 fixture、後者用合成 fixture），已改為直接從真 fixture
  撈出那張合約的原始 bid/ask、用 `is_spread_wide` 在**同一張合約**上
  驗證兩半
  ⚠ **判斷為不修的既有觀察**（兩者皆非本票引入，屬既有狀態）：
  `ranking.py` 的 `build_reasons`／`build_spread_reasons` 早就獨立算了
  一個相似的「買賣價差偏大」cons 訊息，用的是不同門檻（`2/3 *
  max_spread_pct`，而非 `is_spread_wide` 的完整 `max_spread_pct`）——
  同一個關注點現在有兩個獨立公式，未來若要統一屬另開票的範圍
- **FB5-03** [#64] — 單調性違反偵測，只標不刪 ✅
  （commits `063a48e`／`b07709a`）：`filters.py` 新增
  `monotonicity_violations(contracts)`——依 (到期日, 類型) 分組、依履約價
  排序、只比對相鄰配對，用 ask 欄位（call 非遞增／put 非遞減），違反
  時兩邊都標記（配對關係違反，無法從單一報價判斷是哪邊陳舊）。**不被
  `apply_filters` 呼叫**，純查詢用。走**獨立欄位**
  `CandidateView.monotonicity_warning`（不併入 `quote_warning`——成因
  與嚴重性都不同，混在一起會讓使用者分不出「疑似陳舊報價」跟「這組
  候選價差比較寬」是同一等級的事），前端徽章也分開（🚩 紅色 vs ⚠
  橙色，`ExpiryStructure.tsx`）。方法論依據
  `docs/research/option-liquidity-filtering.md` §6.3（307 組相鄰配對僅
  3 組違反，訊噪比極佳）；明確不做凸性檢查（同份研究 50/305 誤判過高，
  且期權市場本質非凸）。契約樣本重產
  ⚠ **檢視面補了一項**：票上（#64）跟兩張姊妹票不同，AC 清單沒明列
  「分析報告尾註同步更新」，一開始沒動 `report.py`；檢視判斷這是漏寫
  不是刻意排除（`filters.py` 自己的 docstring 把三個 C 類標示並列成
  同一套哲學，FB5-02 已替價差寬度開了 CLI 先例），已比照補上
  `_monotonicity_warning_line()`，`violations` 集合原本就已經算好，
  這次只是多傳一手給 `render()`／`render_spreads()`。golden fixtures
  一併重產
- **FB5-04** [#65] — 三分類定位＋品質標示的畫面揭露 ✅
  （commits `be7e293`／`f9c7969`）：`FilterStageResult` 新增
  `filter_class` 欄位（"A"＝資料健全性、"B"＝數學前提，隨
  `apply_filters` 逐關寫入），新增 `filters.FILTER_CLASS_LABELS` 三類
  人話對照表。C 類三個既有判準（零成交量／`is_spread_wide`／
  `monotonicity_violations`）透過新的 `filters.quality_flag_counts()`
  攤開成整個合格池（腿級，單腿與價差共用同一份 `apply_filters` 輸出的
  `qualified`，刻意不依賴 `expiry_top10` 那個只填 spread 策略的既有
  MVP 範圍限制，附錄A13）裡的計數，回傳具名型別
  `models.QualityFlagCount`（不用裸 tuple，跟 `FilterStageResult` 同
  一種模式）；未平倉量刻意不在這三項裡——FB5-01 只把它從硬門檻移除、
  原樣顯示，沒定義「多低算有疑慮」的新門檻，這裡跟著不發明一個。
  CLI `[過濾統計]` 每關標出 `[A類排除]`／`[B類排除]`，新增
  `[C類標示，不影響入選]` 小節列出三項計數；尾註「過濾」條目拆成
  A／B／C 三行分別說明。前端 `CandidatePool` 新增「品質標示（不影響
  入選）」小節，橙色計數（`.flagged`，`--orange`）跟排除的紅色「−」
  （`.negative`，`--red`）視覺分開，全零時整節不顯示；每一關的 A/B
  類別也標在畫面上（`.row-note`）。品質標示徽章（⚠／🚩）本已在候選
  列上（FB5-02／FB5-03 既有機制，`ExpiryStructure.tsx`），本票依票上
  「沿用既有機制不重造」的裁示未新增新徽章。後端 HTTP 層
  （`test_api_filters.py`）、前端元件層（`CandidatePool.test.tsx`）、
  E2E（`smoke.spec.ts` 新增「品質標示（不影響入選）」與「買賣價差
  偏大」斷言，走真實契約樣本）各補測試。契約樣本／CLI 黃金 fixture
  隨之重產。

  **兩份檢視均已處理**（commit `f9c7969`）。真 bug 一個（Spec，對照
  AC3「尾註與實際行為完全一致」）：尾註原文聲稱未平倉量／成交量／
  買賣價差寬度／無套利一致性四項都在 `[過濾統計]` 逐項計數，但
  `quality_flag_counts()` 只算後三項——讀者照著尾註回頭找「未平倉量」
  那一列會撲空。已改寫措辭，把未平倉量獨立說清楚：原樣顯示、不設
  門檻、不在該區計數。Standards 判斷後採納兩項（皆為 judgement call，
  非硬性違規）：`FilterStageResult.cls` 更名 `filter_class`（`cls` 是
  Python classmethod 慣用參數名，容易誤讀，全鏈路含 JSON 欄位與 TS
  型別一併對齊）；`quality_flags` 改回傳 `QualityFlagCount` 具名型別
  取代裸 tuple（Primitive Obsession／Data Clumps，跟 A／B 兩類已有的
  具名模式一致）。**判斷維持不改**：`filters.py` 的零成交量判準與
  `service._v4_fields` 裡同一個比較式（`volume == 0`）各自寫一次，
  未抽共用 helper——單一比較式的重複不足以立一個新符號，Standards
  review 本身也只列為 judgement call，非違規。

**過濾器修正輪（spec #61，FB5-01～04／#62–#65）全數完結。V8（#56）／
V9（#57）／V10（#58）亦已完結——全部票做完。** 下一步不是新票，是等
需求方以 `docs/v10-acceptance-checklist.md` 實機驗收；驗收通過才輪到
年月選擇器（第 1 項）與外觀（第 3 項，已延後）另開新一輪。

### QA-v2 維修輪（`docs/QA-v2.md`，2026-08-05 拆票完成，票已開）

需求方測試部署版後回報 7 點（`docs/QA-v2.md`），已逐點查證並取得裁示，
拆成 9 張票 **#67–#75**（全數 `ready-for-agent`）。

**三個查證結論改變了票面範圍，記在這裡免得重蹈**：

1. **§A.1「排除已過期合約」的單位搞錯了。** 已過期合約在 `_analyze`
   的**第一步** `_scoped_to_selected_expiries`（`expiry > today`，嚴格
   大於，當日到期也砍）就被切掉，過濾／配對／排名／估值全跑在切完之後
   ——`valuation` 的 `T > 0` 假設正是靠這關成立，**沒有浪費任何估值計算**。
   需求方澄清原話：「要壓的不是過期合約，是**過期劇本**。合約不是我們的
   單位，劇本才是。」故 #68 重新定義為「目標年月已過的**劇本**不再進入
   批次刷新」。原始 chain 要不要剔除過期合約**明確不擴 scope**
2. **§A.2「Long Call 沒跟著刷新」在程式碼上不可能發生。** 追平價格只有
   一個計算點（`service._spread_catchup_price`），與 Spread 同一次分析、
   同一份快照算完，序列化進同一份 view，前端 `Catchup` 是純 props
   （無 state／effect／獨立端點），結構上無法單獨變舊。需求方接受，
   **不為不存在的問題開修復票**。查證中發現的真缺口是「詳細頁一個操作
   都沒有」→ #70
3. **§C.7 利率的真因比預期單純：部署的分析路徑從來沒接上利率載入器。**
   `api_app` 全包 grep 不到 `rate_curve_loader`，`run_with_snapshot` 預設
   `None` → `_resolve_rates` 短路成固定 4%。畫面那行是「離線重放，未啟用
   利率曲線」而**不是**「曲線不可得」——這兩個字串是分開的，正好證明
   **線上從來沒有發出過任何一次利率請求**，不是抓取失敗

**需求方 2026-08-05 的其他裁示**：

- 年月選擇器**確認推翻 V3 的「不自刻」裁示**（原生元件做不到「點欄位就
  展開」與 `20xx` 遮罩，桌面 Safari／Firefox 還會退化成純文字框）。要照
  成熟 Month Picker 的互動模式：關閉態有 `20xx` 概念、點日期區域就地
  展開、展開預設今年、當月有清楚 current state、年份**不限**今年～+N
- 桌面**做真正的 master/detail**（左庫常駐＋右工作區），主要操作收攏到
  工作區上方。**手機版面需求方稍後另行定義，本輪不做**
- 利率**接線與選源解耦**：不綁死 `home.treasury.gov`（需求方指出 Yahoo 的
  API 連得上，代表不是部署環境在擋，可能是國債網站本身不給 API）。
  Treasury／FRED／Yahoo 等比較後再定主備援；一輪刷新全部劇本共用同一條
  曲線；快取放 Neon（serverless 檔案系統唯讀，現有檔案快取那層是死的）。
  **先前已研究過 Treasury 不構成必須採用 Treasury 的理由**——要解的是
  「可靠取得期限對齊的市場無風險利率」
- 進階區舊 cache 以資料正確性優先，**刷新後收合重取可接受**

**票與依賴**：QA-v2 這一輪（#67–#75）全數完成，**全部票做完才開 PR**
的門檻已達成。

**2026-08-06 已 merge 回 master（PR #76，merge commit `5ff95c5`）**：
需求方明確要求直接 merge（非等全套 `docs/v10-acceptance-checklist.md`
實機驗收後才開）。merge 前跑過的把關：後端全套 654 條測試（記憶體
假體＋本機真實 PostgreSQL 16 雙軌）全綠、前端型別檢查與 254 條
Vitest 單元測試全綠、`npm run build` 生產建置成功；PR body 附完整
test plan。merge 後 production 網址（`option-chaser.vercel.app`，
對應 master 分支）會自動觸發重新部署，套用本輪全部改動（React／
FastAPI／Neon 新架構取代 Streamlit）。桌面 20/80 版面（#72）
先前的「驗收失敗」是需求方誤在 production 網址（當時仍是舊版 master）
測試、非工作分支 preview——已排除，非真缺陷。

**已完成**：

- **需求方直接裁示（2026-08-06，不開票，四項合併一次執行）**：
  1. 確認並清除 Streamlit 遺留——`git ls-files webapp/` 確認零追蹤
     檔案，只剩未追蹤的 `__pycache__` 殘留（連同全站 stale `.pyc` 一併
     刪除），pytest collection 乾淨，webapp/ 空目錄一併移除。查明
     反覆出現的環境詭異狀態是這個 sandbox 容器本身在對話輪次之間會
     把本地 checkout 重置回舊 commit（`git status` 誤報「已是最新」，
     實際上落後 origin 幾十個 commit）——不是資料真的遺失，`git fetch`
     ＋`git reset --hard origin/<branch>` 即可修正，遇到就重做一次。
  2. 同步最新 master 進工作分支（commit `5a801fe`）：只落後一個
     `Create Mvp-v2.md`，QA-v2 這一輪既有成果原封不動保留。
  3. 利率快取改市場日語意（commit `1045880`）：同一市場日成功抓過
     一次就所有劇本、所有 refresh 共用，不再是 12 小時滾動新鮮度窗；
     下一個市場日第一次需要時才重新 fetch。`RateCacheEntry` 新增
     `market_day`（只在真正成功直接抓到時前進，判準是呼叫端傳入的
     `today`——紐約曆日，不是 `fetched_at` 的 UTC 日期部分，兩者在
     午夜前後對不起來）與 `attempted_day`（不論成敗、每次寫入都蓋成
     當次 `today`，供既有短窗 anti-hammering 判斷改用「是否同一市場日
     的嘗試」而非單看時間差——單看時間差在市場日剛跨過午夜的那幾
     分鐘會誤沿用「昨天的紀錄」）。失敗窗與 7 天緊急備援窗兩條既有
     fallback 邏輯不變。Postgres schema／migration／SQL 同步加欄位。
  4. **#74** 完成：利率 production probe＋Treasury 硬化（commit
     `d505bc8`）。用需求方的 Vercel 帳號部署一個用完即丟的臨時專案
     （跟正式 `option-chaser` 分開，`option-chaser-rate-probe`，
     ⚠ 本輪工具沒有刪除專案的操作，需求方之後可手動清掉），對候選
     利率來源打真連線探測（探測程序見研究文件 §6，結果見 §6.4）：
     Treasury CSV／XML 皆可達，維持主源；FRED 免鑰 `fredgraph.csv`
     兩次測試皆逢時，但官方 keyed API（不同子網域）連線正常、只是
     缺 key——證明問題在那個便利端點本身，不是整個網域被擋，**探測
     結果推翻研究 §5 原排序「FRED 免鑰路徑為第一備援」**；Financial
     Modeling Prep 連線正常、缺 key；需求方另外提議的 Yahoo Finance
     四檔免鑰指數連得到，但用同一天真實 Treasury 資料回頭算過，
     1–3 年期插值誤差約 18–25bp（本 repo 既有可接受門檻 7.5bp 的
     3 倍），維持研究 §3.5 不採用的結論，這次是拿實測資料驗證而非
     紙上推論。FRED／FMP 皆確認網路可達但沒有金鑰（本輪不申請，
     需求方裁示先接受 fallback 鏈只有 Treasury 這一層），落地版本＝
     Treasury（CSV→XML→前一年 CSV）→ 陳舊窗快取 → 固定 4%。
     `option_chaser/data/treasury.py` 硬化：一般瀏覽器等級標頭（原本
     裸字串 `User-Agent`）、明確檢查狀態碼（非 200 不進解析）、失敗
     訊息分來源分階段（Treasury／CSV 或 XML／哪一年／原因）；新增
     `tests/fixtures/treasury_{csv,xml}_sample.txt` 兩份探測時實際
     拿到的真實回應當回歸樣本（不是手刻夾具）。只動接縫後面的
     provider，未改動 #67 的分析路徑／快取層核心邏輯（第 3 項的市場日
     修正是需求方另外裁示、與 #74 分開一個 commit）。**未驗證項**：
     正式部署版（不是探針用的臨時專案）拿到真實期限對齊曲線這件事，
     仍待需求方之後實機部署驗證（`docs/deploy-vercel.md` 記錄的既有
     部署缺口尚未解決）。
- **#75** 主要操作入口收攏到工作區上方（commits `589014d`／`9ec0971`）：
  建立劇本從「掛在全部劇本卡片下面、永遠展開的表單」改成工具列上的
  頂部入口——跟刷新同一個固定操作列（`Toolbar` 新增 `createOpen`／
  `onToggleCreate`／`createPanelId`，並排兩顆膠囊鈕），預設收合，
  按下去才展開。`Toolbar` 既有的 `position: sticky` 天生蓋到新按鈕，
  不必另外實作「捲動時常駐可見且可點」。code review 跟進：面板原本
  用條件渲染整個卸載重掛，收合＝使用者打到一半的字被悄悄清掉——
  改用原生 `hidden` 屬性切換可見度，面板一律掛著、`DOCUMENT_POSITION_
  FOLLOWING` 的結構保證因此在開／關兩態都成立；順帶補上展開鈕的
  `aria-controls`（`CreateForm.tsx` 裡 `MonthPicker` 展開鈕既有的
  `aria-expanded`＋`aria-controls` 寫法，這裡原本只抄了一半）。
  建立表單本身（`CreateForm.tsx`）未改動，既有的「必填留白、無
  預設值」規則不受影響；建立成功後表單不自動收合（方便連續建立），
  票上沒有硬性規定，屬工程判斷。Playwright 對按鈕名稱是子字串比對
  （不同於 `@testing-library` 預設的精確比對），"收合建立表單" 含
  「建立」兩字會撞到表單送出鈕，e2e 改用 `exact: true` 消歧。
- **#72** 桌面版真正的 master/detail（commits `7d5f68b`／`8523f71`）：
  桌面寬度（`window.matchMedia`／`useIsDesktop`，`App.tsx`）改成左側
  劇本庫常駐、右側工作區顯示選中劇本，約 20/80；選中劇本不必先返回
  即可切換到另一個。手機寬度沿用既有整頁替換，程式碼路徑原封不動
  （`!isDesktop` 才會走進那個既有分支），既有測試不必為此改動就繼續
  通過。`ScenarioList` 新增 `selectedId`：目前選中的劇本卡片標
  `selected` class（左側強調色條＋淡色底，非 `.chip.selected` 那種
  整片實色——卡片內文字要維持可讀）與 `aria-current="page"`。斷點與
  版面下限刻意對齊（1100px／220px，220 恰好是 1100 的 20%）：code
  review 抓到原始寫法（900px／280px）在 900～1400px 這段常見桌面寬度
  會被下限卡死到超過 30%，與「約 20/80」的驗收不符，改成對齊值後
  下限在斷點邊界形同虛設，往寬處走比例自然貼著 20%。新增 Playwright
  `Desktop` 專案（1280×800）＋`e2e/desktop.spec.ts`（含左右比例量測、
  瀏覽器上一頁／下一頁兩項 code review 補的覆蓋率缺口），與既有
  `iPhone` 專案用 `testMatch`／`testIgnore` 互不重疊，手機案例不會被
  拿去跑桌面版的行為假設。jsdom 沒有實作 `window.matchMedia`，
  `test-setup.ts` 新增 `fakeMediaQueryList()` 工廠（預設 `matches:
  false`＝手機，既有測試不必改動；桌面情境測試用
  `vi.stubGlobal("matchMedia", ...)` 覆寫），與 `App.test.tsx` 共用
  同一份假體形狀。
- **#68** 過期劇本不再進入批次刷新——新增 `_timing_json` 的 `expired`
  欄位（`timeframe.month_is_over`，與既有 `days_to_anchor` 是不同判準，
  前者才是擋刷新的那個）；唯一擋點設在 `refresh_scenario` 端點本身
  （不是前端篩選），過期劇本呼叫這支端點會短路成無害讀取（不抓鏈、不
  跑引擎、不入庫、不留事件），回傳既有卡片列——批次流程另外在前端
  `App.tsx` 的 enqueue 前先篩掉，純粹省一趟網路往返，真正的保證來自
  後端。清單卡片新增「已過期，不再刷新」標記，且比照舊 Streamlit
  `workspace.card_of` 的既有優先序判斷（紅燈優先於黃燈）：已過期時
  蓋掉刷新失敗的提示與重試鈕，避免同一張卡同時出現兩種互相矛盾的
  狀態。契約樣本 `contracts/scenario_row_sample.json` 隨之重產。
  code-review 跟進：`api_app/main.py` 三處重複的「取最新結果摘要」
  收斂成 `_summary_of()`
- **#70** 詳細頁補上刷新入口——查證 §A.2「Long Call 沒跟著刷新」在
  程式碼上不可能發生（同一次分析、同一份快照、純 props），不開修復票；
  真缺口是詳細頁一個操作都沒有。`ScenarioDetail` 新增刷新入口，三個
  props（`busy`／`failure`／`onRefresh`）全部由 `App` 傳入、直接對接
  既有的那條單一佇列與 `failures` map——`busy` 沿用 `Toolbar` 同一個
  「任何刷新進行中」判準（不是新開一個「只有這個劇本」的追蹤），
  `onRefresh` 就是 `enqueue([這個劇本])`，`ScenarioDetail` 自己不發起
  任何網路請求。視覺語言與既有兩處一致：標題列右側膠囊鈕仿
  `Toolbar`，失敗提示＋重試鈕仿 `ScenarioList` 的卡片失敗區塊。
  code-review 跟進：Spec 面抓到詳細頁沒有比照 #68 排除過期劇本——
  刷新鈕與失敗重試都補上 `detail?.expired` 判斷，已過期時鈕文案改
  「已過期，不再刷新」並停用、失敗提示整塊不顯示，與清單卡片同一套
  優先序判斷一致
- **#69** 進階區資料隨新分析失效，不得混用新舊 cache——`SpreadHistory`／
  `RawData` 是純 `<details onToggle>` 一次性取得、無任何 dependency
  array，父層 `DetailBody` 用 `key={"spread-history-"+analyzedAt}`／
  `key={"raw-data-"+analyzedAt}` 綁定分析身分，新分析一到就整個卸載
  重掛，內部 state（已抓到的資料、`<details open>`）連同歸零，刷新後
  收合、下次展開重新取得（需求方裁示接受，資料正確性優先）。原始資料
  CSV 下載連結另外補上快取破壞參數（`rawDataCsvUrl` 新增選填
  `analyzedAt` 附成 `?t=...`）——那是靜態 `<a href>`，不受 React
  remount 保護，瀏覽器 HTTP 快取才是它真正的敵人。
  ⚠ **TDD 抓到一個真的 React bug**：兩個元件一開始給了同一個 key 字串
  （`analyzedAt` 本身，未加前綴）——手足元素共用同一個 key 是未定義
  行為，React 會噴「key 重複」警告，且第一次紅燈測試在這個 bug 下呈現
  出詭異的間歇性失敗（remount 有時發生、有時沒有）。查出來是 key 碰撞
  後，兩個元件各自加上元件名前綴才穩定。這正是先寫測試、看紅燈長什麼
  樣的價值——如果只是先寫實作再補測試，這個 bug 很可能被漏掉
  code-review 跟進：Spec 面抓到 AC2「主圖候選因新分析換掉時，歷史走勢
  跟著換成新候選的序列」雖然程式碼上已經正確（`candidate`／`analyzedAt`
  恆出自同一次 `getScenario` 回應，不可能單獨變），但沒有測試真的換過
  候選身份鍵去驗證，補上一條用 `withTopCandidate({candidate_key:...})`
  的回歸測試
- **#71** 自製年月選擇器——推翻 V3「用原生 `<input type="month">`」的
  裁示（需求方 2026-08-05 明確裁示）。`MonthPicker`／`YearInput` 兩個
  子元件比照專案既有慣例（`ScenarioDetail.tsx` 的 `Catchup`／
  `PriceLadder` 等）直接定義在唯一呼叫端 `CreateForm.tsx` 內，不拆
  獨立檔案。切換鈕是 `<button>`，點下去在文件流裡就地展開面板（不是
  浮層），Tab 順序天然是切換鈕→上一年→年份→下一年→1 月…12 月→
  下一個表單欄位，不必用 `useEffect` 搬焦點；選定後把焦點還給切換鈕，
  鍵盤使用者才不會在月份鈕被卸載後掉到 `<body>`。年份輸入三條路徑
  殊途同歸：`‹`／`›` 箭頭無上下限步進、聚焦時只框住後兩碼（打兩碼就
  換另一個 20xx 年，不必先刪「20」）、或全選後直接打四碼跳到任意年份。
  當月 `aria-current="date"`、已選定月份 `aria-pressed`，兩者可同時
  成立、CSS 分開處理（外框 vs 填色）。ARIA 只宣稱完整實作的部分——
  `aria-expanded`＋`aria-controls` 的揭露元件模式（button 控制面板
  顯／隱，就這麼多）完整成立，沿用到期日 chip 那條「不宣稱 tablist」
  的既有裁示，不發明一個沒做完整方向鍵導覽的假 widget role。
  `validateDraft` 的年月格式檢查原封不動保留——UI 現在雖然只會產生
  合法格式，但那條規則是獨立測試、公開匯出的純函式契約，不是只服務
  這個 UI。App.tsx／e2e 兩處既有的「打字進年月欄位」測試改成點選互動。
  code-review 跟進三項：(1) Standards 面抓到 `today` 沒有接上 App 既有
  的單一時鐘（`ScenarioList` 的 `now`），一律各自 `new Date()`——`App.tsx`
  補上 `today={now}`；(2) `.month-cell.selected` 與既有 `.chip.selected`
  逐字重複，合併成同一組選擇器；(3) Spec 面抓到 `MonthPicker` 包在
  `<label>` 裡是無效巢狀（`<label>` 內容模型只收 phrasing content，
  `<div>` 根節點不合格）——改用 `aria-labelledby` 指向獨立的
  `<span id=...>`，且當月的 `aria-current` 視覺提示原本只有 0.5px
  外框改色太淡，加粗到 1.5px＋粗體字
- **#73** Research：公開利率資料源評選——比較 Treasury／FRED／
  Fed H.15／NY Fed SOFR／Yahoo／Alpha Vantage／Financial Modeling
  Prep／Massive-Polygon／CME Term SOFR 九個候選，逐項套用票上明列的
  八個維度。**結論不是蕭規曹隨**：主源仍是 Treasury（期限覆蓋全場
  最完整、免鑰、零金融語意風險），但備援順序改成 FRED 官方 API
  （DGS 系列與 Treasury CMT 同一報價口徑，換源不用動 `ratecurve.py`
  消費端一行）→ Financial Modeling Prep（單次 GET 全曲線，商業聚合站
  故排最後一層）→ 現行固定 4%。明確剔除 NY Fed SOFR（回顧性平均、
  非期限結構）、Yahoo 四指數（3M–5Y 之間整段無節點，恰好蓋住本 app
  1M–3Y 主戰場）、Alpha Vantage（缺 1M／1Y 節點，且與既有選擇權鏈
  備援共用同一組 25 次/日全站配額）、CME Term SOFR（授權不可行）、
  Fed H.15（官方公告正在退役其 Data Download Program，導引改用
  FRED）。沙箱對全部候選網域一律 403，明確標記為 sandbox validation
  limitation（`$HTTPS_PROXY/__agentproxy/status` 顯示是本沙箱出口
  政策擋下，不是目的站或 production 的結論），文件中沒有出現「沙箱
  連不到＝production 連不到」這類推論。產出給 #74 的 production
  connectivity probe 程序（逐來源 URL、檢查項目、pass/fail 標準、
  平日／假日各測一次的執行紀律）。研究文件：
  `docs/research/interest-rate-source-selection.md`。
  ⚠ 查核時抓到一處引註錯誤（非本票程式碼——文件本身的一個引用）：
  「Vercel serverless 唯讀檔案系統」這件事被錯誤歸給
  `docs/deploy-vercel.md` 一個不存在的「serverless 唯讀」小節，已改
  正引到真正的出處（`api_app/main.py` 檔頭與
  `option_chaser/service.py` 的 `run_with_snapshot` docstring）——
  事實本身沒錯，只是來源引用貼錯地方，在一份以「逐一引註」為賣點的
  文件裡值得修正
- **#67** 利率：接線、fallback 與狀態語意（provider 無關）——
  production 的分析路徑第一次真正接上利率載入器；`create_app()` 新增
  `rate_loader`（預設仍是既有 `service.default_rate_curve_loader`＝
  Treasury，**只是接縫後面的暫時填充物，不是選型**，選型是 #73／#74）。
  新增 `api_app/rate_cache.py::cached_loader()`：包在任何
  `RateCurveLoader` 外面的持久快取，本身完全不認識 provider 是誰——
  `test_provider_is_swappable_without_touching_the_caching_layer` 用一個
  假 provider 走完整條路徑直接證明這點。快取放新的 `Storage.
  get_rate_cache()`／`save_rate_cache()`（`api_app/storage/`，port/
  adapter 兩邊都實作，Postgres 用 `CHECK(id=1)` 單列表——單一狀態、
  不是歷史序列，跟 `results`／`snapshots` 的複合鍵是不同的資料形狀，
  刻意不同套）。成功快取 12 小時、失敗只快取 5 分鐘——資料源短暫斷線
  恢復後不該讓使用者卡在舊的失敗訊息裡到 12 小時後才有機會重試，同時
  仍吸收得住同一輪刷新裡 N 個劇本的重複請求（這正是「N 個劇本共用
  同一條」的落地機制：每個 `/refresh` 是各自獨立的 serverless 呼叫，
  只能靠跨呼叫的持久層達成，不是行程內批次）。快取讀寫失敗一律視同
  沒有快取／不影響本次分析（比照 `option_chaser/data/treasury.py`
  既有「快取寫不進去不影響本次分析」的哲學，套用在這個新的持久層
  上）。`/api/health` 新增 `rate` 欄位（`fetched_at`／`ok`／`note`／
  `last_success_at`）供運維診斷。契約樣本因為利率從固定 4% 換成真實
  期限對齊而全面重產（Greeks／情境報酬等下游數字隨之變動，非結構性
  變更）；`scripts/gen_contract_sample.py` 與 `tests/test_api_analyze.py`
  的契約比對測試都改注入固定假曲線，不再依賴當下網路能不能連到
  Treasury。開發環境用沙箱內建的 PostgreSQL 16 對真資料庫（不只
  記憶體假體）驗證過 Postgres adapter。
  code-review 跟進（commit `428f210`）：(1) 抓取失敗時原本直接蓋成
  `None`（退回引擎固定 4%），未沿用快取內還沒過期的舊曲線，與
  `treasury.py` 既定行為不一致——新增 `_STALE_FALLBACK_MAX_AGE`（7 天，
  同 `treasury.py` 既有窗口），失敗時優先沿用還沒過期的舊曲線並在
  `note` 誠實標出「沿用快取」；(2) `RateCacheEntry` 單列覆蓋式儲存，
  一旦抓取失敗就答不出「最後一次成功是什麼時候」——新增
  `last_success_at`，只在真正成功時前進，失敗（含沿用舊曲線分支）
  一律沿用前一次的值，Postgres schema／SQL 同步更新（新欄位走
  `_MIGRATIONS` 而非只加進 `_SCHEMA`——本機真實 Postgres 已建過舊表，
  重現了「表已存在、需要 ALTER」的正式環境情境）；(3) `underlying(today)`
  原本沒有 try/except，未來 #74 換源後 provider 若直接拋例外會讓整條
  分析路徑炸成 500——收斂成跟 provider 自報失敗同一種形狀。新增 8 條
  TDD 測試涵蓋以上三點。

> 我原本把 #73 設計成「被 #67 擋，要靠部署版探針才能開始研究」，
> **需求方 2026-08-05 否決，理由成立**：沙箱閘道擋掉某些網域，不等於
> Vercel 不能對外聯網——production 本來就穩定抓得到 Yahoo／Cboe，
> outbound 能力早已證實。403 更可能是該站限制自動化請求、endpoint
> 用法不對、User-Agent／API policy，或那個 provider 本身不適合當
> production source。**紙上比較（#73）不需要探針就能做**；真正的
> production connectivity probe 排在候選選出之後、由 #74 執行，
> 且**探針結果可以推翻研究的排序**。

### MVP V2 手機版劇本庫（spec #77，2026-08-06 完結，PR #85 已 merge）

**背景**：QA-v2（#72）完成桌面 20/80 master/detail 時，需求方明確裁示
「手機版面稍後另行定義，本輪不做」。`docs/Mvp-v2.md` 就是那份定義，
`/to-spec` 據此發佈 spec #77，`/to-tickets` 拆成 M1a–M6（#78–#84）。

**兩條硬紅線**（需求方 2026-08-06 裁示，全程遵守，每張票都有對應回歸
測試）：
1. 桌面版（#72／#75）已經是對的，本輪不准弄壞——每張票都在真的
   Postgres＋Desktop／iPhone 兩個 Playwright 專案全綠後才收工，Desktop
   案例一條都沒被放寬。
2. 代表候選不得藉本輪擴張 ranking universe——`representative_candidate`
   只讀 baseline 期 `expiry_groups` 的 rows（與 `best_return` 同一次
   走訪），不讀 `comparison`；`test_representative_candidate_ignores_
   comparison_and_stays_baseline_scoped` 專門釘住這點，
   `test_representative_candidate_baseline_return_always_matches_
   best_return` 釘住兩者數值恆等。

**已完成**：

- **M1a**（#78，commit `1f63d4a`）— 代表候選：引擎純函式＋儲存落盤＋
  API 序列化。新增 `store.representative_candidate(view)`，
  `best_return()` 改由它導出而非各走各的一次走訪；`ResultRecord`／
  `ResultSummary` 與 `results` 表新增同名欄位（建表與遷移分兩批送，
  沿用 V3 當年 `best_return` 欄位的教訓）；`latest_summaries()` 加選
  新欄位、仍不撈 view。純前端不動，這張票的可驗證交付在 HTTP 層。
- **M1b**（#79，commit `8237a6f`）— 前端型別與卡片顯示（沿用現有大
  卡片版式）。`ScenarioSummary` 新增 `representative_candidate` 欄位，
  現有卡片補上策略／買賣履約價／實際到期日兩列，不做密度改造。
- **M2**（#80，commit `21aa346`）— 劇本級燈號＋紅燈沉底。純前端
  `scenarioSignal()`（紅＝過期、黃＝本次刷新失敗、綠＝其餘，紅＞黃＞
  綠）與 `sortScenarios()` 新增紅燈沉底鍵，沿用附錄 A12 語意、舊
  Streamlit 版早有這條排序規則，React 版直到這票才補上。
- **M4**（#81，commit `7d85592`）— 手機首頁三段版面：Dashboard 佔位
  （低調可見、不放任何數字）＋就地展開的新增劇本入口（`CreateEntry`，
  沿用 #75「面板一律掛著只切換可見度」的教訓）。桌面工具列
  （`Toolbar`）新增 `showCreateButton` 判別聯合型別，手機傳 `false`
  不重複顯示建立入口，桌面維持 #75 現狀。
- **M3**（#82，commit `8366a24`）— Compact Scenario Row：三層版式與
  密度改造。新增 `CompactScenarioList.tsx`，手機版專屬的高密度三層
  compact row（標的/目標/年月/燈號、報酬率/策略/履約價、到期日/距
  到期/更新時間），取代大卡片；封存鈕疊在右下角不佔行高。桌面版
  `ScenarioList.tsx` 完全不動、兩者是獨立元件不共用渲染路徑。
- **M5**（#83，commit `e13d402`）— 返回還原捲動位置與劇本庫狀態。
  `App.tsx` 新增 `scroll` 監聽（記錄）＋`useLayoutEffect`（還原）兩個
  手機專屬 effect；新增表單開合狀態本就因為 App 元件不會因導覽重新
  掛載而自然維持，本票補上回歸測試釘住這個既有前提。
- **M6**（#84，本節）— Regression、真機驗收清單、PR gate。全套測試
  （後端 667 條、前端 288 條 Vitest、Desktop＋iPhone 22 條 Playwright、
  typecheck、build）全綠；兩條硬紅線的回歸測試逐條確認存在且通過
  （見上）；真機驗收清單見下；PR 待需求方核准後開。

**真機驗收清單**（比照既有 A10.5 窄 viewport 驗收慣例，本輪 CI 只能
驗結構與數值，視覺／觸感留給需求方在真機上確認）：

1. 手機首頁由上而下：Dashboard 佔位區（只有標題與一句規劃中說明，
   沒有任何數字）→「＋ 新增劇本」收合列 → 高密度劇本清單。
2. 點「＋ 新增劇本」在原位置向下展開表單，不跳頁、不彈出 modal；
   打一半誤觸收合鈕，內容不會被清空。
3. 每個劇本列一眼看得出：標的、目標價、目標年月、燈號（紅／黃／
   綠）、報酬率、策略、買賣履約價、實際到期日、距到期天數、最後
   更新時間——一個手機螢幕能掃過至少 4 個劇本，不必先往下捲。
4. 報酬率旁邊的策略與履約價，跟改版前卡片上顯示的數字對得起來
   （同一個劇本、同一次刷新，兩邊看到的百分比應該一致）。
5. 目標月已過完的劇本排在清單最後、亮紅燈；本次刷新失敗但仍有舊
   結果的劇本亮黃燈、標「舊資料」；其餘綠燈。
6. 點任一劇本進詳細頁，用返回鍵或返回連結回到劇本庫，畫面停在原本
   捲動的位置，不必重新往下找剛剛那一列；若展開過建立表單，返回後
   仍是展開的。
7. 封存入口在 compact row 上找得到（角落的小字），點下去仍能封存。
8. 桌面寬度（≥1100px）行為與 QA-v2 完全一致：左側劇本庫常駐＋右側
   詳細頁、建立入口仍在工具列頂部，肉眼看不出這輪改動的痕跡。

> 沿用規則：反饋要先逐點跟需求方確認打算怎麼改、為什麼，確認完才
> 開票施工；`/implement` 進行中沒遇到需人類裁示的事就不停。

### Trash 語意＋利率顯示修正（tracking #86，施工中）

**背景**：需求方 2026-08-07 三點確定事項——Archive 正式改為 Trash 語意
（硬擋垃圾桶劇本的背景動作、單筆／批量還原、單筆／批量永久刪除皆需
二次確認）、修正利率顯示語意（fallback 不掛市場資料日期、真曲線標示
curve date／stale）。垃圾桶版面先出手繪 HTML 預覽給需求方核准（三輪
修正：桌面版工具列順序、手刻 SVG 圖示取代 emoji、每張卡片單筆刪除
圖示化），核准後 `/to-tickets` 拆成 RC1＋TR1–TR6（#87–#93），依賴順序：
RC1／TR1／TR2／TR3／TR6 可平行開工，TR4 被 TR2＋TR3 擋，TR5 被 TR4 擋。

**已完成**：

- **RC1**（#87）— 利率顯示語意修正：`AnalysisParams` 新增
  `rate_curve_used`／`rate_curve_date`／`rate_curve_stale` 三個結構化
  欄位，獨立於 `rate_by_expiry` 是否非空（後者在曲線成功但鏈上零合約
  時仍會是空表，兩者脫鉤才不會誤判成 fallback）。`RateCurve`
  （`ratecurve.py`）新增 `stale: bool = False` 欄位並隨 `curve_to_dict`／
  `curve_from_dict` 序列化——staleness 搭著曲線物件本身走，
  `RateCurveLoader` 呼叫介面簽章不變（仍是 2-tuple），blast radius
  因此侷限在標記 stale 的兩個分支：`data/treasury.py` 的本地檔案
  快取備援、`api_app/rate_cache.py` 的 Neon 緊急備援窗。前端
  `AnalysisReport.tsx` 新增 `RateRow` 三態分流：真 fallback 只顯示
  「{rate}% · FALLBACK／Treasury curve unavailable」不掛日期；真曲線
  顯示 curve date，陳舊備援額外標 STALE。`report.py::_rate_line` 純
  文字報告同步套用（同一段文字會出現在網頁「分析報告」展開區），
  golden fixture 四份與契約樣本重產。後端＋5 條新測試、前端＋3 條，
  全套 672 條（後端）／291 條（前端 Vitest）全綠
- **TR1**（#88）— 後端硬擋垃圾桶劇本的 refresh：`refresh_scenario`
  在 `_require` 之後、任何抓鏈／分析動作之前新增 `archived_at is not
  None` 檢查，回 409＋`stage="archived"`（比照既有 `_fail()` 分層
  格式），不抓鏈、不跑引擎、不入庫、不留事件——跟過期劇本（#68）的
  靜默短路（200，回既有卡片列）刻意不同，垃圾桶是使用者主動丟掉的，
  要讓前端分辨得出「這是因為在垃圾桶」。`FailureStage`／`STAGES`／
  `failureLabel` 三處同步加 `"archived"`（`test_frontend_contract.py`
  的漂移防線抓到才補的，不是主動想到）。`/api/analyze`（一次性分析、
  無 scenario 概念）不受影響。後端＋3 條、前端＋1 條，全套 675 條
  （後端）／291 條（前端）全綠

- **TR2**（#89）— 後端還原：`Storage` port 新增 `restore_scenario`
  （`Scenario.restored()` 清空 `archived_at`，`memory`／`postgres`
  皆實作，契約測試 parametrize 兩者），API 新增
  `POST /api/scenarios/{id}/restore`，成功寫 `SCENARIO_RESTORED`
  事件；重複呼叫（本來就不在垃圾桶）冪等成功、不留事件，比照既有
  `archive` 對重複封存的處理。批量不新增後端端點——沿用既有序列
  佇列模式，前端 TR4／TR5 對選中的每個劇本各打一次這個端點。前端
  `api.ts` 新增 `restoreScenario()` 供 TR4 消費。後端＋9 條，全套
  686 條（後端）／292 條（前端）全綠

- **TR3**（#90）— 後端永久刪除：`Storage` port 新增 `delete_scenario`，
  安全閘門只允許刪除已封存的劇本（未封存或不存在皆回 `False`、資料
  原封不動）；真的刪除時 cascade 清 results／snapshots／events（不
  依賴 FK，`postgres.py` 三張表各自一次 `DELETE`，沿用專案既有「不用
  FK 約束」慣例）。API 新增 `DELETE /api/scenarios/{id}`：未封存回
  409（純字串 `detail`，不是 `_fail()` 的分層形狀——這不是刷新／分析
  失敗分層概念）、成功回 204、不留刪除事件（劇本連同它的 events 一起
  沒了）。前端 `api.ts` 新增 `deleteScenario()`；`request<T>()` 補上
  204 No Content 分支（不呼叫 `.json()`，回 `undefined`）。批量同
  TR2，前端序列佇列逐一呼叫。後端＋8 條，全套 698 條（後端）／292 條
  （前端）全綠

- **TR6**（#91）— 前端：主清單批次移入垃圾桶＋單筆刪除圖示化＋垃圾桶
  入口。手刻 SVG 圖示（`src/icons.tsx`：`TrashIcon`／`CheckIcon`，
  outline 風格，核准版面唯一採用款）取代 `ScenarioList.tsx`／
  `CompactScenarioList.tsx` 既有文字「封存」鈕；桌面工具列新增
  「🗑 垃圾桶」膠囊鈕，順序＝＋建立劇本→垃圾桶→重新整理（需求方核准
  版面）。批次選取：清單「收益率口徑」說明旁新增圖示入口，進入選取
  模式後 checkbox 取代單筆刪除鈕（不同時出現）、整卡／整列點擊改為
  切換選取（`<a>` 的 `onClick` 攔截＋`preventDefault`，不換成
  `<button>`）、底部 `batch-action-bar` 顯示已選數量＋「移入垃圾桶」；
  沿用既有序列佇列模式依序呼叫既有 `/archive` 端點，個別失敗不中斷
  其餘筆、失敗原因列在錯誤提示裡、成功者立即從清單消失。`route.ts`
  新增 `trashHash()`／`isTrashHash()`（跟詳細頁同一套 hash 慣例）；
  新增 `TrashView.tsx`（讀 `GET /api/scenarios?include_archived=true`
  篩出已封存者，`api.ts` 新增 `listArchivedScenarios()`）作為垃圾桶
  畫面骨架——手機整頁替換、桌面替換左側 `library-pane`（右側
  `detail-pane` 沿用既有「有無選中劇本」邏輯，不特別接管；開垃圾桶
  會清空網址上的劇本 id，右側因此落回既有空狀態，這是核准版面「右側
  邏輯不動」的自然結果，不是另外接管）；TR6 階段是唯讀清單，TR4／
  TR5 補上還原／永久刪除操作。前端＋新增 21 條 Vitest（含
  `route.test.ts`／`ScenarioList.test.tsx`／`CompactScenarioList.test.tsx`／
  `App.test.tsx` 四處）、＋4 條 Playwright（Desktop＋iPhone 各兩條：
  批次移入垃圾桶端到端、垃圾桶入口導覽），全套 313 條 Vitest／
  27 條 Playwright 全綠

**待辦**：

- TR4（#92）— 前端：垃圾桶畫面單筆操作（被 TR2／TR3 擋，已解除，
  可施工）
- TR5（#93）— 前端：垃圾桶畫面批次操作（被 TR4 擋）

> 沿用規則：全部票做完才開 PR、merge 回 master，中途不主動開。

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

- **⚠ 容器會不定時倒退回較早的提交**（多次發生，連 `.venv` 套件與本地
  Postgres 資料目錄一起消失，且 `git status` 會誤報「已是最新」）。
  發現 `git log` 對不上 `git log origin/<branch>` 時，**不要用
  `git merge --ff-only`**（本地 HEAD 是壞掉的舊提交，不是落後的乾淨
  祖先，`--ff-only` 常常直接失敗）——正確作法：
  `git fetch origin claude/implement-tfm9oa` →
  `git reset --hard origin/claude/implement-tfm9oa`（safe：這個 bug
  模式下本地從來沒有真正未提交的工作，只有 HEAD 指錯）。
  **所有工作都推到 origin，倒退不會掉東西**。接著重建環境（見下方
  venv／Postgres 兩條）——不重建的後果是**靜默**的：儲存契約測試的
  Postgres 那一半會被跳過，全套仍是綠的卻少驗一個實作（正常全套是
  **667 條**，MVP-v2／M1a 起的數字；掉到 6xx 前段或更少，且明顯變快，
  就是 Postgres 那組沒跑）
- 跑測試：`OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest"
  PYTHONPATH=. .venv/bin/python -m pytest`
  （`pyproject.toml` 的 `packages.find` 只收 `option_chaser*`，`api_app`
  不在裡面，靠 PYTHONPATH 匯入。沒有 `OC_TEST_DATABASE_URL`
  就只跑記憶體假體那一半）
- 建 venv：`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e ".[api,yf]" pytest`
  （**`api` extra 必裝**：HTTP API 是後端唯一測試接縫，缺 httpx 會讓
  契約測試整組紅燈——這是刻意的，不要改成靜默跳過。**`yf` extra**＝
  備援資料源 yfinance，已移出核心依賴以免 pandas/numpy 進 serverless
  函式——pyproject 的核心依賴就是 lambda 實際安裝的清單。**`gui` extra
  已隨 V10 cutover 移除**（Streamlit 已刪除），裝 `.[gui,api]` 只會
  跳警告、不是錯誤，但代表指令抄到舊版，改用 `.[api,yf]`）
- **本地 Postgres 起不來時**（`initdb`／`pg_ctl` 直接以 root 執行會報
  `cannot be run as root`）：容器內建 Postgres 16（`/usr/lib/postgresql/16/bin/`）
  要用內建的 `postgres` 系統使用者跑，完整流程：
  ```
  mkdir -p /tmp/oc_pgdata /tmp/oc_pgrun
  chown -R postgres:postgres /tmp/oc_pgdata /tmp/oc_pgrun
  su postgres -c "/usr/lib/postgresql/16/bin/initdb -D /tmp/oc_pgdata --auth=trust"
  su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /tmp/oc_pgdata -o '-k /tmp/oc_pgrun -p 55432' -l /tmp/pg.log start"
  /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -p 55432 -U postgres -c "CREATE DATABASE octest"
  ```
  （`scripts/dev_env.sh` 應該已經包了這套邏輯——上面是它失敗時的手動
  備援步驟）
- 前端（V1／#48 起）：`npm install`；`npm run typecheck`／`npm test`
  （Vitest 元件測試）／`npm run e2e`（Playwright，手機 viewport）／
  `npm run build`。沙箱有預裝 Chromium 時用
  `PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium npm run e2e`
- 部署與契約樣本：見 `docs/deploy-vercel.md`
- **部署網址（2026-08-06 起，PR #76 merge 後）**：
  - **production**：`https://option-chaser.vercel.app`（對應 master，
    push 到 master 會自動重新部署）——V10 merge 前這裡必定是 ERROR
    的舊限制**已解除**，現在應該是正常運作的新架構
  - **工作分支 preview**：`https://option-chaser-git-claude-imp-aef368-ofriedoriceo-5352s-projects.vercel.app`
    ——分支別名，永遠指向 `claude/implement-tfm9oa` 最新一次部署。
    每次 push 也會另外產生一次性 preview 網址，那些不用收藏
  - 兩者預設都開了 Vercel Authentication（SSO）保護 preview 部署；
    2026-08-06 曾在自動化驗證過程中被意外關閉又重新開啟過一次
    （已確認復原為 `prod_deployment_urls_and_all_previews`），日後若
    需要調整以 Vercel 後台 Project Settings → Deployment Protection
    為準
  - **待清理**：`option-chaser-rate-probe`（#74 探測用的獨立臨時
    Vercel 專案，跟正式 `option-chaser` 專案分開）已無用途，目前沒有
    工具可以刪除 Vercel 專案，需求方之後可自行在後台刪除
- 全套測試現為全綠（後端 667 條、前端 288 條 Vitest、Desktop＋iPhone
  共 22 條 Playwright；舊紀錄提到的 5 個 streamlit 版本漂移失敗已隨
  T2 改寫消失）。MVP-v2（M1a–M6）起的最新數字。
