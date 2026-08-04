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
- **R1** [#49] — Research：專業報告版型慣例（無阻擋；只擋 V8，可在 V8 之前任意時點插入）
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
  ⚠ 兩份程式碼檢視（標準面／規格面）在提交時尚未回報，若有發現待補
- **V4** [#52] — 刷新與分析：進度／失敗指引／新鮮度 ←**下一張**
  （#51 已完成、已解鎖；功能列的刷新鈕目前是 disabled 佔位，由這張接上）
- **V5** [#53] — 詳細頁核心：Heatmap＋摘要＋追平標示（被 #52 擋）
- **V6** [#54] — 到期日結構：橫向按鈕＋Top 10 含腿價（被 #53 擋）
- **V7** [#55] — 最好／最差價位三價位對照（被 #51、#53 擋）
- **V8** [#56] — 分析報告新版型＋原始資料（被 #53、#49 擋）
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
