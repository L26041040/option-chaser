# Option Chaser

## 規則

**每做完一張 ticket，就更新下面的「專案紀錄區」**——把該票移到已完成、標出下一張。

**全部 ticket 做完才開 PR、merge 回 master**，中途不要主動開。

**除非使用者主動要求，否則不准執行截圖或把截圖貼上對話**（跑 Streamlit／Playwright
截圖驗證 UI 極度耗費 token）。窄 viewport／版面等視覺驗收，一律留給需求方自己用
瀏覽器確認，或等使用者明確要求才做。

**任何回報給需求方的實質內容（總整理、提案、拆票清單等），一律整份放進單一
code block**，不要零散貼成一般文字——需求方要能一次性複製貼上。

**Session 做完一整段工作後的回報，一律用中文＋英文專有名詞（英文專有名詞
不要翻譯，例如 ticket、commit、PR、issue、API 等維持英文），且整份回報
放進單一 code block**——跟上一條是同一份規則的延伸，不要忘記。

**這個 code block 是一整段、不能拆開**：回報內容全部放在同一個 code
block 裡，不能切成好幾個 code block、也不能中間插普通文字把它打斷成
兩截。code block 前後可以有一句話帶過，但實質內容本身必須是單一、
完整、不中斷的一塊，讓需求方一次選取、一次複製貼上。

**每份回報 code block 最上面一行加編號**，格式固定
`［回報#NNN］標題`（NNN 三位數、從 001 起算，例如
`［回報#001］spec #137 拆票完成`）。編號是**累計總數**，不因換
session、換分支、換主題而歸零——目前最新編號記在這裡：

> 目前次序：012（下一份回報用 013）

每發一份回報就把上面這個數字改成剛剛用掉的那個，跟著那次改動一起
commit（沒有其他改動要 commit 時，單獨為這一行開一個小 commit 也
可以）。新開的 session 找不到對話記憶時，编號一律以這裡記的數字為準，
不要自己另起爐灶。

只有這七條。

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
> TR1–TR6 全數完成並已 merge 回 master**（PR #94，merge commit
> `200b1ae`，tracking #86 與 16 張此前兩輪已出貨但忘記關閉的舊票
> #67–75／#78–84 一併於收尾時關閉）——Archive 正式改為 Trash 語意、
> 利率顯示語意修正、垃圾桶前端全部落地。中間穿插的
> 「目前狀態（2026-08-02）」等舊日期標頭是歷史留存，**以此段與下面
> 對應小節末尾的紀錄為準，不要被舊標頭誤導**。需求方已指示
> **下一輪先研究、不施工**：三份研究文件已完成（歷史 IV 資料源、
> IV 相對歷史方法論、candidate 層級深化——見「下一輪研究」小節），
> 等需求方審閱、實測資料源、裁示方案後才進 spec／拆票。
> 其他下一階段候選：
> **多使用者隔離** [#59]（未標 `ready-for-agent`，需求方裁示後才開工）、
> 外觀優化（QA-v2 需求方已明確裁示延後，待主動重啟）、Dashboard 佔位區
> 實際內容（跨劇本比較功能確定後另開票，spec #77 Out of Scope）。
> **2026-08-08 需求方 `/wayfinder` 開了「貴不貴」研究地圖**（issue
> #95）：R1–R4 四張研究票完成（四份新文件見「下一輪研究」小節末尾）。
> **2026-08-09 需求方直接發佈 MVP V3 需求文件**（`docs/Mvp-v3.md`＋
> `docs/Mvp-v3-appendix.txt`，master 直 commit）＝G1/G2 裁示（入選：
> 歷史位置 vol 空間、Normalized Skew 主資訊；呈現只給事實；追平價格
> 升級為 Crossover Boundary），地圖 #95 與 G1 #100／G2 #101 據此
> resolution 關閉。同日 `/to-spec` 完成：**MVP V3 spec＝issue #102**
> （`ready-for-agent`），並依需求方 Review 修訂三點：comparator 不得
> 寫死 Long Call（須與買腿同 option type，Bear Put Spread→Long Put；
> 既有 `_spread_catchup_price` 的 put→call 轉換為缺陷，一併取消）、
> q=0 修法不在 spec 鎖死（改獨立 correctness ticket 先驗證後鎖定，
> 仍是 Crossover 的 gate，spec 不自行發明模型）、LEAPS 超網格裁示
> 採方案 (b)（不外插、不以較短 tenor 代理，percentile 留白）。
> **R2（同日，to-tickets 前最後一輪 UX cleanup，共 7 點）**：追平價格
> 區塊正式確認移除（底層欄位只留 migration／regression 用）、報價品質
> 警示重整（顯示旗標只剩 Bid/Ask 過寬，volume==0 與 friction>25% 退出
> 警示；⚠ **選取閘門凍結不動以守「不改 ranking semantics」**，契約拆
> 顯示／選取兩旗標）、Analysis Report 瘦身成四塊、利率顯示實際數值
> （Rate used／Tenor／Source／Curve date，候選契約新增利率與年期欄位）、
> 走勢圖補軸刻度與 hover/tap tooltip、Raw Data 二層收合、Desktop 劇本庫
> 卡片瘦身。**R3（同日，to-tickets 前最後補充）**：Heatmap 右側價格變動
> 百分比軸（左軸絕對價格不動、右側為同列 annotation 非第二組 scale，
> `move_pct` 由 price-axis 契約提供、前端只格式化；主圖與展開候選圖共用
> 語意；Mobile 可短格式但不得拿掉）＋新 guardrail：**Bid/Ask 過寬門檻
> 本輪只能量測回報，未經需求方裁示不得自行修改**。
> **尚存 Open Question 僅一項：IV 歷史 vendor 選型與月費上限
> （只擋 IV History 那條線）**；q=0＋par-yield 近似歸 correctness ticket
> 驗證後裁示。**同日 `/to-tickets` 完成，拆成 14 張票（#103–#116，
> 皆為 #102 子票）**：8 張無依賴可立即開工（#103 A/E、#104 F、
> #105 G、#106 I、#107 J、#108 K、#109 M、#110 D1）；#111（B1 vendor
> 驗證）標 `needs-human-validation`（非 `ready-for-agent`，需可連網
> 環境執行，此沙箱大部分外部網域 403）；#112 H 被 #105 擋；#113 D2
> 被 #110＋需求方核准擋（人工裁示點，非純技術依賴）；#114 B2 被
> #103＋#111 擋；#115 C1 被 #113 擋；#116 C2 被 #115＋#109 擋。
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

### Spec #151（2026-08-17 發佈）——Historical IV Trend v1（Exact Contract Canonical Series）

需求方 `/to-spec` 發佈：既有 Normalized Skew 卡片的歷史數列（`ivhistory.py`
的 (tenor, delta) 逐日重錨定）從未真正追蹤「同一張合約」——每天都可能
對到不同履約價甚至不同到期日。新 spec 定義一個**新增、獨立**的
「Historical IV Trend」卡片：對候選的每一隻腳，追蹤**這張、且只有這張
exact listed option contract**（同一 underlying／到期日／履約價／
call-put）過去最長一年的市場 IV，畫走勢圖＋moving average／Bollinger／
z-score／percentile／Δ4w。與既有 Normalized Skew 功能**並存、不取代**
——後者維持原樣，繼續由 `ivhistory.py` 供應。`/to-tickets` 拆成七張
（HIVT-01–07，issues #152–158，皆為 #151 子票），依相依序單線施工，
HIVT-01 是硬性 blocker（`needs-human-validation`，非 `ready-for-agent`）。

**HIVT-01**（#152）— Vendor Capability Gate：需求方另一個 session
（ChatGPT）完成真實驗證（commits `3724fca`／`6b085f7`／`9175d7d`／
`220699d`，GitHub Actions 一次性 probe，真實 HTTP 203＋`s="ok"`）。
真實合約 `TLT281215C00094000`：單合約歷史端點一次呼叫回整段區間（34
筆觀測，1 credit），`iv` 欄位直接由 vendor 給（部分觀測為 `null`，
如實視為缺席，不補值）；超界 `from`／週末窗口皆自然截斷，不需另建
listing-date 探測。`single_contract_history_endpoint_verified=true`，
issue 已關閉。

**HIVT-02**（#153，commits `ba3211d`／`56b4c9b`）— Exact-Contract 後端
資料取得路徑：新增 `option_chaser/ivtrend.py`（純函式，本票只有
`trim_to_window`／`history_span_days`——moving average／Bollinger／
z-score／percentile／Δ4w 留給 HIVT-03，與 `ivhistory.py` 零耦合、雙向
零 import）；`option_chaser/data/marketdata.py` 新增
`fetch_contract_history()`（成功判準 2xx含203＋`s=="ok"`，不寫死
`status==200`——新增 `test_http_203_is_a_success_not_a_failure` 迴歸
測試鎖死這個 #152 抓到的 bug class；`null` IV 誠實保留為缺席）；
`api_app/storage` 新增 `ContractHistory`（memory／postgres 兩後端，
鍵是 exact OCC contract symbol，取代整條 chain／整個 symbol 的舊快取
模型）；`api_app/main.py::_ensure_contract_history()` 漸進式刷新（只補
`fetched_through` 之後到今天的缺口，同一天重複請求零 vendor 呼叫）；
`GET /api/scenarios/{id}/iv-history` 新增純加法 `legs` 欄位（單腳依
spec #151 §4 精確定義整個省略 `sell` key，不是設成 `null`），既有
`points`／`metrics`／`status`／`note` 家族逐位元未動。IV 反算路徑
（`implied_vol()`）確認不需要——vendor 直接給 `iv`，條件分支不成立。
`/code-review` 兩軸皆抓到同一個真缺口：diagnostics 白名單補了
`underlying`／`strike`／`option_type`，但沒有任何 `emit()` 呼叫真的帶
這些欄位（只有可反解的 `contract_symbol`），且遺漏 issue 原文列出的
`expiration`／`lookback_days`——已修正，新增 `_identity_context()`
輔助函式，四站 emit 全部補上四個可讀欄位，白名單補齊遺漏兩項。全套
1279 條測試通過（memory＋真實 Postgres 雙後端），既有 (tenor,delta)
家族測試逐條未動。issue 已關閉。

**HIVT-03**（#154，commits `18a2337`／`4d60e14`）— Historical IV 統計量
套組：`ivtrend.py` 新增 `moving_average`／`bollinger_bands`／
`current_zscore`／`historical_percentile`／`delta_4w` 五個純函式＋
`IV_TREND_LOOKBACK_DAYS=30`／`IV_TREND_MIN_OBSERVATIONS_FOR_BANDS=5`
兩個常數；三個「視窗型」統計量共用同一份 rolling mean／std（z-score
與 Bollinger band 保證同一個數字，不分頭算）；`percentile`／`delta_4w`
沿用 `ivhistory.percentile()`／`trend_4w()` 演算法定義但重新實作、不
import，維持雙向零耦合。`LegHistoricalIv` 回應新增六個統計欄位＋
`lookback_days_config`；低於最低觀測門檻時 SMA／bands／zscore 各自回
`null`，percentile／Δ4w／原始走勢圖不受影響。per-request 診斷保留上限
`_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST` 從 20 調高到 40——兩腿候選新增
10 筆恆保留的 metrics 事件後，舊上限會把 `vendor_fetch`／`reanchor`
擠出去，這是舊 (tenor,delta) 家族的真回歸，當票一併修正。`/code-review`
兩軸各抓到一項真問題：`bollinger_bands()` 補回 spec 明文簽章的
`mean`／`std` 兩條序列；`_emit_leg_stat_metrics()` 從五段複製貼上改成
資料驅動迴圈、六參數收斂成三個。新增結構性隔離測試（AST 逐函式檢查
exact-contract 端點函式不呼叫任何重錨定函式）。全套 1329 條測試通過。
issue 已關閉。

**HIVT-04**（#155，commit `0b4865b`）— Vertical Spread 兩腿分離＋舊
reanchored 次要欄位退場：`api_app/main.py::_iv_payload()` 從回應信封
移除 `points`／`metrics.buy_iv`／`metrics.sell_iv`／`metrics.atm_iv`
（已被 `legs.buy`／`legs.sell` 取代）。**裁決記錄**：issue 字面列出
`points` 應移除，但同票也要求 Normalized Skew 不受影響——而
Normalized Skew 卡片本來就靠 `points` 畫自己的走勢圖，兩條要求對同一
信封鍵有矛盾。解法：`points`（帶四個子欄位）確實整個消失，新增
`normalized_skew_points`（只有 `date`／`normalized_skew`）取代它，
Normalized Skew 走勢圖因此不受影響——已在 `_iv_payload()` docstring
與 issue 留言記錄這個裁決，需求方若有異議可回饋調整。新增
`test_normalized_skew_is_bit_identical_to_an_independent_reanchored_computation`
直接呼叫未觸碰的 `ivhistory.reanchor_spread()`／`field_metrics()`
重算比對，不是靠既有測試套件全綠間接推論。

**HIVT-05**（#156，commits `74fee21`／`bb4ed98`）— 前端 Historical IV
Trend 卡片：新增 `src/IvTrend.tsx`，逐腿卡片資訊順序比照 spec #151
§6（現值→走勢圖→percentile→z-score→Δ4w→涵蓋時間＋觀測筆數）；
`src/ivHistoryChart.ts` 新增 `projectOntoDomain()` 讓 raw／MA／
Bollinger 上下界四條疊加序列共用同一個 x 軸；`src/IvHistory.tsx`
只剩 Normalized Skew 頭條，`ChartTooltip`／`toPixel`／版面常數 export
供 `IvTrend.tsx` 複用幾何。`/code-review` 抓到 `CardSkeleton`／
`InlineDiagnostics` 檔頭註解誤寫成逐腿卡片直接複用（實際 import 清單
沒有這兩個名字——固定版位／診斷區塊是掛在整張卡片層級一次涵蓋兩個
家族，不是逐卡各自一份），已修正註解＋順手把只有一處呼叫點卻泛化出
不必要彈性的 `CardSkeleton` 參數簡化回單一 `isSingleLeg`。

兩票依需求方指示連續完成（避免前端讀到已消失欄位的空窗期），全套：
backend 1339 條、frontend vitest 554 條、typecheck／build、Playwright
e2e 75 條（含 `smoke.spec.ts`／`desktop.spec.ts` 既有 Historical IV
區塊改用新回應形狀重寫）全部通過。issue 已關閉。

**HIVT-06**（#157，commit `a59b4e4`）— 既有重錨定引擎隔離稽核＋回歸
測試強化：純驗證票，稽核結果全數通過、無交叉依賴，只補一個結構測試
缺口——`option_chaser/data/marketdata.py` 的 `fetch_contract_history`／
`_parse_contract_history`（HIVT-02 新增）先前沒被 AST 隔離測試涵蓋到，
本票補上（同檔案 `_parse_surface_rows` 合法引用 `SurfacePoint` 服務舊
whole-chain 家族，確認新函式沒有沾邊）。`tests/test_ivhistory.py` 經
`git log` 核對全系列 HIVT commits 從未被改過。Migration map（spec
#151 §7）逐項對照實際出貨程式碼，三處與 spec 事前預測有出入已記錄在
issue #157 留言：`valuation.py::implied_vol()` 與
`snapshot.py::find_contract()` 兩個「條件式重用」最終都沒被本 feature
呼叫過（vendor 直接給 IV／contract_symbol 一律可取得，條件分支從未
觸發）；`_ALWAYS_KEPT_STAGES`／診斷保留上限問題方向與 spec 猜測相反
（不是新家族被餓死，是新家族的量體把舊家族擠出去，HIVT-03 已修正）。
全套 1341 條測試通過。issue 已關閉。

**HIVT-07**（#158，commits `8ffb457`／`74f3398`）— 全面回歸／E2E 最終
驗收，spec #151 系列最後一張票：補齊既有 75 條 E2E 尚未逐一肉眼驗證到
的 34 項 User Stories 缺口，新增 6 條手機端測試涵蓋 exact-contract
身份真實性（買／賣腿現值與百分位讀出兩個確實不同數字，不是同一份
序列複製兩份）、涵蓋時間三個邊界（近 3 週／5 個月／11 個月）、
z-score／MA／Bollinger 帶幾何可見性、逐腿 vendor／quota 獨立狀態。
過程中在 `IvTrend.tsx::spanLabel()` 抓到兩個既有生產環境 bug（15–29
天被 `Math.round(days/30)` 誤湊成「近 1 個月」；330 天被固定 300 天
門檻誤報成「近 1 年」），修正並各補一條回歸測試鎖死；本人以邊界值
（1／21／29／30／300／330／345／364／365／0）手算獨立覆核過修正結果，
`/code-review` Standards 軸自己手算同一批邊界值也得到相同結論。

`/code-review` Spec 軸抓到真缺口：`playwright.config.ts` 顯示
`smoke.spec.ts` 只跑在 mobile（iPhone）project 下，本票新增的 6 條
檢查因此只有手機覆蓋，desktop.spec.ts 完全沒補，與 #158 明文要求的
「桌面與手機 viewport 對等」有落差——已修正，補上其中 3 條到
`desktop.spec.ts`（exact-contract 身份真實性、統計量幾何可見性、
逐腿 vendor／quota 獨立狀態；沿用該檔既有 `legHistoricalIv`／
`SELL_CONTRACT`／`fullIvResponse`／`routeTwoScenarios` 慣例）。涵蓋
時間三個邊界維持只在 mobile 跑——`spanLabel()` 是純 viewport-agnostic
邏輯，已被 `IvTrend.test.tsx` 單元測試與 mobile E2E 鎖死，desktop
重複驗證邊際價值低，已在 commit 訊息記錄這個取捨。

最終驗證：backend pytest 全綠（memory＋真實 Postgres 雙後端）、
frontend vitest 557 條全綠、typecheck／build 通過、Playwright
mobile＋desktop 共 84 條全綠（連續兩輪穩定、無 flake；HIVT-07 自己
新增的一條測試施工中曾因固定值移動平均線在圖上塌成零高度導致
geometry 斷言不穩，已改用有斜率的假資料修正並重跑兩輪確認穩定）。
issue 已關閉。

**Spec #151（HIVT-01–07）全七張子票（#152–158）全數完成。** 依專案
規則全部子票做完才開 PR，中途不主動開；**尚存 blocker：無**——
已符合開 PR 條件，等需求方 cue 才實際開 PR、merge 回 master。

**HIVT-07 完成後的追加發現＋研究（2026-08-18，`/research`，
commit `a513353`）**：需求方 / ChatGPT 真實 GitHub Actions probe
（commits `4ec23f1`／`410f927`）確認 Market Data App 的 exact-contract
歷史報價端點對 `TLT`／`ORCL` 真實合約回傳 `iv` 大量／全部為 `null`
（`bid`／`ask`／`mid`／`last`／`underlyingPrice`／`dte` 皆正常）——
exact-contract acquisition 本身沒壞，缺的是 vendor 沒給 IV 時的
reconstruction。研究文件
`docs/research/historical-iv-reconstruction.md` 已完成：pricing model
不需重選（既有 `option_chaser/valuation.py::implied_vol()` 的
Bjerksund-Stensland (1993) 可直接重用，`ThinkorSwim` 官方文件本次
新查獨立佐證同一模型選擇），三項輸入（S／r／q）原始資料本 repo
既有研究＋既有程式碼都已具備，缺的是把既有「今日快照」邏輯
point-in-time 化（`ratecurve.py`／`dividends.py` 各自的小擴充）＋
停止丟棄 exact-contract 歷史列本來就有的 `underlyingPrice`。附帶
一節純分析（不施工）的 `/iv-history` 診斷降噪建議：現行端點在
exact-contract 路徑跑完後無條件繼續跑整段舊 (tenor,delta) 重錨定
流程，`_backfill_iv` 逐日缺口補齊＋`reanchor` 對整段歷史逐次重放
是噪音根因。純研究，未 `/to-spec`、未 `/to-tickets`、未動
production code。

**Calibration prototype 已執行（2026-08-18，`/prototype`，commits
`2c48b67`～`22ad0fc`）**：`scripts/prototype_historical_iv_calibration.py`
（丟棄式，直接 import production 的 `implied_vol()`／`fetch_chain()`／
`load_rate_curve()`／`load_dividend_history()`，不複製定價公式），透過
一次性 CI probe（真實 `MARKETDATA_APP_TOKEN`，跑完即刪）拿到 TLT／ORCL
真實資料（N=328，vendor iv 非 null 的今日快照）驗證 §10 recipe。結果見
`docs/research/historical-iv-reconstruction-calibration-results.md`：
**ranking stability 極強**（Pearson 0.9991、Spearman 0.9970、percentile
rank diff median 0.005）；絕對誤差大且系統性偏高（MAE 38 vol points），
最可能成因是樣本恰好清一色落在 3 天到期（vendor `fetch_chain()` 不帶
`expiration=` 參數時只回最近月選，這是既有 `fetch_surface()` docstring
已經記錄過的 vendor 行為，#134）——3-DTE 是 vega 塌縮、IV 反解天生最
不穩定的極端情境，不是 Historical IV Trend 實際運作的 LEAPS 尺度。補抓
medium／LEAPS 到期日兩次都遇到 Market Data App HTTP 403（前兩次近月選
主樣本用同一把 token 皆成功，數分鐘內連續補抓才開始 403，讀起來像
rate limit），依規則未再重試，**LEAPS／medium DTE 至今沒有真實資料
驗證過**，是本輪最大的未解缺口。**Verdict：PASS_WITH_GUARDRAILS**
（ranking 這個票上明訂的優先判準通過，但絕對誤差成因未完全鎖定＋
沒驗證到 LEAPS 天期，需求方核准前建議先在 rate limit 解除後補一輪
LEAPS 樣本）。

**偏差診斷已完成（2026-08-18，`/research`，commits `6ad4fd7`～`b6adaf4`）**：
上面那個 +38 vol points 的系統性偏差**成因已完全鎖定**，結果見
`docs/research/historical-iv-reconstruction-bias-diagnosis.md`。

**真因不是 vega 塌縮（上一輪的推測是錯的，已在 calibration 結果文件
加註更正）**，而是**參照日錯配**：Market Data App 回的是過期快照，
vendor 用**快照自己那一天**算 IV，prototype 卻用 `date.today()` 算 T。
那輪快照早 4 個日曆天，於是 vendor 眼中 DTE=7、我們眼中 DTE=3；在 3 DTE
這種天期，`σ ∝ 1/√T` 把它放大成 √(7/3)=1.53 倍。**只把 T 換成快照日，
同樣 183 筆的 MAE 從 0.3813 掉到 0.0020（190 倍），ratio 從 1.5249
收斂到 1.0001±0.0068。** 起手線索是「偏差是乘法的」——比值在 39 倍的
IV 範圍上 stdev 只有 3%，噪音做不到這件事。

其餘假設全部用數字排除：**pricing model（BS93 vs Merton European）差
0.0001**、r（0→8%）≤0.005、q（0→10%）≤0.009、單位 trace 乾淨。近到期
病態真實存在但只解釋**殘留離散度與失敗率**（時間價值 <$0.10 組殘差
0.28 vol pts vs ≥$0.10 組 0.02），不解釋偏差。

**vendor 官方文件獨立佐證**（自官方文件原始碼庫取得，沙箱擋住本站）：
options 要到**次一交易日 9:30:01 ET** 才從 Delayed 轉 Historical，
該規則精確預測了本輪兩支 probe 在同一天不同時間拿到的**兩個不同快照日**
（02:00 ET → 週五收盤 DTE=7；11:23 ET → 週一收盤 DTE=4）。同時**更正**
一個本 repo 既有的錯誤認知：**HTTP 203 不是「延遲報價」，是「從快取層
回應」**，官方文件還特地把這個誤解點名為 "a common (incorrect)
assumption"——`option_chaser/data/marketdata.py:425-427` 的註解需更正
（本輪禁止動 production code，僅記錄為裁決點）。

**LEAPS 問題也一併解決**：本輪 probe 補上真實 303 DTE 資料，同樣的日期
錯誤在那裡只值 **0.03–0.13 vol pts**（封閉形式預測 0.082，吻合）。修正
日期後 ORCL LEAPS MAE **0.43 vol pts**、TLT **3.2 vol pts**——TLT 的殘差
與 moneyness 及該標的的高 q 相關，推測是 q 口徑差異（MEDIUM 信心，未做
直接 ablation）。**Verdict：`YES_WITH_GUARDRAILS`**（guardrails ＝ 先補
取數層三個缺口：`updated`/`dte` 要帶出解析層、T 一律用觀測日、r/q 對齊
同一天）。

**修正後 calibration 重跑完成（2026-08-18，`/prototype`，commits
`bb3d80f`～`66c1183`）**：診斷文件 §9-C 點名的三個取數缺口（observation_
date 用 vendor `updated`、T/r/q 皆對齊該日、q 額外補上界避免看到
observation_date 當時還沒發生的配息）在 prototype 層修正後，用真實
TLT／ORCL medium／LEAPS 資料（N=578，前兩輪完全沒有的天期）重新跑一輪
calibration，結果見
`docs/research/historical-iv-reconstruction-corrected-calibration-results.md`。

**bias 幾乎完全消失**：MAE 0.3816→0.0060（63 倍）、bias +0.3816→-0.0021、
失敗率 44.2%→7.1%。**LEAPS ranking 穩定**：新到期日（~852 天）整體
Spearman 0.9894，四組 symbol×tenor 組合全數 ≥0.9626。**TLT q ablation
直接證實 q 是主因**（同一批 284 筆觀測只換 q：q=0 讓 MAE 從 0.0089
惡化到 0.0493，+4.05 vol pts；且 production point-in-time q 本身是
四個測試版本裡表現最好的，沒有系統性偏誤，不是「調 q 數值就能再壓低」
的情況）。**Verdict：`STRONG_PASS`**（本輪驗證的三個具體問題——日期
修正是否解決 bias、LEAPS ranking 是否穩定、TLT 殘差是否為 q——全數
得到明確肯定答案）。

STRONG_PASS 不等於「毫無準備即可上線」，本輪列出 5 項施工前必要
guardrails：(1) 修正邏輯要真正搬進 production（本輪修正只做在
prototype 層，`marketdata.py`／`ratecurve.py`／`dividends.py` 尚未真正
補上 point-in-time 介面）(2) vendor IV 合理性關卡（本輪又發現多筆
vendor_iv≈0.0001 的退化值）(3) 目前只驗證過橫截面準確度，縱向（同一
合約跨多天）準確度仍待驗證 (4) medium 天期失敗率偏高（TLT 11.1%／
ORCL 18.3%）成因未深究 (5) prototype 的 point-in-time 揀選邏輯建議
直接寫成 `ratecurve.py`／`dividends.py` 正式函式＋補單元測試，不要
複製腳本寫法。

**下一步**：等需求方審閱兩份 calibration 結果文件＋診斷文件，裁示
§11 的六個決策點與本輪新增的 5 項 guardrails，再決定要不要把 v1
recipe 拆成正式 spec/tickets。

### Spec #143（2026-08-15 發佈）——Application Diagnostics / Error Log 系統

需求方在兩輪 Historical IV 診斷都卡在「拿不到真實 production 證據」
之後裁示：**先做一套小型但正式的 Application Diagnostics**，不是為
Historical IV 臨時插 console.log，而是後續其他資料源與功能共用的錯誤
診斷基礎。`/to-spec` 已發佈 **issue #143**（`ready-for-agent`），**票
尚未拆**。

**要解的問題**：`api_app/`／`option_chaser/` 目前**一行 logging 都沒有**
（唯一的 `print` 在 `cli.py`，是 CLI 正常輸出）；唯一持久線索是
`IvBackfillRun.outcome` 三選一，而最常見的失敗恰好是 `outcome="ok"`
但資料是空的。`fetch_surface()` 把 HTTP status／vendor `s`／errmsg／
rate-limit 標頭／raw row 數全部丟掉，`map_surface_payload()` 靜默跳過
缺欄位的列，`iv_at()` 出界回 `None`——每一站都可能把 N 筆變 0 筆，
**沒有任何一站留下自己的進出筆數**。

**spec 的核心決策**（施工時不必重新推導）：

- **新模組 `api_app/diagnostics.py`**：`DiagnosticEvent`＋單一
  `emit()` 入口，同時寫 storage 與印 structured JSON log，共用
  `event_id`／`correlation_id`；correlation id 由 middleware 產生放
  `contextvars`，**不從函式簽章往下傳**（否則引擎層模組被迫認識 HTTP）
- **Redaction 用白名單不是黑名單**：`context` 走 key 白名單（不在名單
  直接丟棄），字串值再過長度截斷＋樣式遮蔽＋已知祕密值比對；URL 只記
  sanitized 形式、headers 一概不記、完整 vendor body 永不落盤
- **Storage 新表 `diagnostics`**（不併進 `events`——後者是永不修剪的
  領域事實），retention＝**trim-on-write 全域最新 200 筆**（serverless
  無背景排程可掛、日期 TTL 擋不住單日爆量；memory 用 `deque(maxlen=)`
  取得同一條上限，契約測試才有意義）
- **排放量雙層控制**：log 全發不設限，storage 有 per-request 上限
  （20 筆）且**依 severity 取捨**（error／warning 一律優先保留）
- **契約純加法**：iv-history 回應新增 `diagnostics: {correlation_id,
  events}`（因為最常見症狀是 **200 但沒資料**，另打端點就得猜 id）；
  新增 `GET /api/diagnostics`、`DELETE /api/diagnostics`
- **vendor adapter 需暴露 HTTP metadata**（低層 primitive 改回
  status／白名單標頭／body，`fetch_surface` 加 optional observer）。
  spec 內明文界定：這**不算**需求禁止的「改 vendor」——禁的是換資料源
  ／改抓取行為，把本來就存在、只是被丟掉的 metadata 傳出來是觀測必需，
  且需求第 5 點直接點名要這些欄位。回傳值／例外型別／欄位映射不動
- **八個 observation point**（`candidate_lookup`／`cache`／
  `vendor_fetch`／`payload_parse`／`database_write`／`backfill` 摘要／
  `reanchor`／`metrics`）構成「N → 0 帳本」：同一 correlation id 的
  events 依序讀完，每站進出筆數都在
- **只觀測不修**：`_backfill_iv` 一天失敗就 break 整批、`iv_at()` 出界
  回 None——本輪一律不動，只讓它們看得見

**成功判準只有一條**：上線後不必再開一輪診斷、不必讀程式碼，就能直接
回答「vendor 回 N 筆，究竟在哪一站變成 0 筆」。

**需求方修訂（2026-08-15，spec #143 留言存證）**：spec 整體方向核准、
設計全部保留；**唯一修正是部署那一條**——不再把「Claude 端 Vercel MCP
看不到 project」當成施工或驗收 blocker。Claude 只負責完成程式、測試、
push `claude/implement-tfm9oa`；**Preview deployment 與 Vercel runtime
logs 由需求方端（ChatGPT）另行驗證**，不需要要求需求方處理 Vercel
授權，也不得因此把任何項目標成「待需求方執行」而暫停。spec 原文
「⚠ 已知風險……需要需求方在 Vercel 後台確認部署」該段作廢。

**拆票完成（2026-08-15 `/to-tickets`，七張全掛 `ready-for-agent`，
票已開、尚未施工）**：

- **DG-01** [#144] — Prefactor：vendor adapter 暴露 HTTP metadata
  （零行為變更；observer 是純 callback，adapter 不 import 診斷模組）
  ／無 blocker
- **DG-02** [#145] — 診斷骨幹：event／emit／whitelist redaction／
  structured JSON log／`diagnostics` 表＋trim-on-write 200／
  `GET`＋`DELETE /api/diagnostics`／correlation ID middleware＋
  `X-Correlation-Id`／emit 失敗絕不影響主流程／無 blocker
- **DG-03** [#146] — Historical IV 取數路徑觀測（candidate_lookup／
  cache／vendor_fetch／payload_parse／database_write／backfill 摘要）
  ＋per-request 排放量控制（20 筆、severity 優先）＋iv-history 回應
  新增 `diagnostics` 欄位／被 #144、#145 擋
- **DG-04** [#147] — Historical IV 投影路徑觀測（reanchor／metrics）
  ＋完整 N→0 帳本測試／被 #146 擋
- **DG-05** [#148] — Inline diagnostics：Historical IV 卡片就地展開
  （預設收合、只顯示存在欄位、200 但有 warning 也觸發）／被 #146 擋
- **DG-06** [#149] — Settings `Diagnostics / 報錯紀錄` 區塊（清單／
  詳情／Copy 含 fallback／Clear 二次確認）／被 #145 擋，可與
  #146–#148 並行
- **DG-07** [#150] — 最終 regression／security gate（紅線全表面、
  retention、observation-only 回歸、E2E、全套綠燈、push 不開 PR）／
  被 #144–#149 擋

> 建議施工順序（單線、不平行）：**#144 → #145 → #146 → #147 →
> #148 → #149 → #150**。

**施工開始（2026-08-15 `/implement`，依序單線、每張跑該票測試才進
下一張）**：

- **DG-01** [#144] — Prefactor：vendor adapter 暴露 HTTP metadata
  （零行為變更）：`option_chaser/data/marketdata.py` 新增
  `HttpResponse`（status／白名單 rate-limit 標頭／body）與低層
  `_http_request()`；`_http_get()` 降級為它的 body-only 薄殼，
  `fetch_chain`／`verify` 的既有 `http_get=` 注入點與測試因此完全
  不動。歷史曲面路徑新增 `_parse_surface()`（`map_surface_payload`
  與 `fetch_surface` 共用的唯一分支邏輯，不拋例外，回傳
  `(points, telemetry)`）與 `_parse_surface_rows()`（逐列筆數帳本：
  raw_rows／parsed_call_rows／parsed_put_rows／四種 dropped_* 原因，
  篩選條件逐字不變，只是現在計數而非默默 `continue`）；`fetch_surface`
  新增 `observer: Callable[[dict], None] | None` 參數，成功／
  no_data／vendor 錯誤／HTTP 429／連線失敗五條路徑都會在拋出前先
  通知一次，帶 http_status／rate-limit 三欄／vendor_status／
  vendor_errmsg／筆數帳本。**adapter 不 import 任何診斷模組**——
  observer 是純 callback。新增 16 條測試（HTTP primitive 2＋observer
  7＋既有 fetch_surface 測試改注入 `http_request=`），
  `test_data_marketdata.py` 既有斷言一條未動、全綠；全套 pytest
  無回歸（全綠）
- **DG-02** [#145] — 診斷骨幹（commit `367b8d6`）：新增 `api_app/
  diagnostics.py`——`DiagnosticEvent`＋唯一入口 `emit()`（組 event→
  sanitize→印 structured JSON log→寫 storage，任一步失敗皆吞掉、
  絕不拋出）；`SUBSYSTEMS`／`STAGES`／`SEVERITIES` 詞彙單一來源（本票
  不接任何 subsystem，`STAGES` 先把 #143 列的八個都定義好供 DG-03／
  DG-04 用）。**Redaction 白名單**：`_CONTEXT_KEY_WHITELIST` 過濾＋
  `sanitize_string()` 三層（已知現行祕密值逐字比對→樣式遮蔽
  `Bearer …`／`token=`／`postgres://`→長度截斷）；`sanitize_context()`
  同時丟棄 `None` 值（只顯示存在欄位）。**correlation ID**：
  `contextvars` 存一份，`correlation_scope()` context manager 綁定／
  還原，`emit()` 自己讀，不從函式簽章往下傳。`Storage` protocol 新增
  `append_diagnostic`／`list_diagnostics`／`clear_diagnostics`，
  `RETENTION_LIMIT=200` 定義在 `diagnostics.py` 單一處；`MemoryStorage`
  用 `deque(maxlen=RETENTION_LIMIT)` 天然 trim-on-write，`PostgresStorage`
  新增 `diagnostics` 表＋每次寫入後 `DELETE ... OFFSET RETENTION_LIMIT`
  trim（不併進既有 `events` 表——後者是 scenario-scoped 永不修剪的
  領域事實）。`main.py` 新增 correlation ID middleware（每個回應皆帶
  `X-Correlation-Id`，含錯誤回應）與 `GET`／`DELETE /api/diagnostics`
  兩端點。新增 `test_diagnostics.py`（22 條，redaction／correlation／
  emit 容錯）、`test_api_diagnostics.py`（10 條，端點＋middleware）、
  `test_storage_contract.py` 新增 diagnostics 契約區塊（含
  retention-cap 測試，memory／postgres 共用同一份行為）；全套 pytest
  無回歸（全綠）
- **DG-03** [#146] — Historical IV 取數路徑觀測＋排放量控制＋
  iv-history 回應夾帶診斷（commit `5a4da9b`）：`api_app/providers.py` 的
  `default_historical_surface` 加一個 `observer` 參數原樣轉給
  `marketdata.fetch_surface`（#144 打的底），這一層仍不解讀 telemetry
  內容。`main.py` 新增六個觀測點：`candidate_lookup`（找不找得到候選、
  掃過幾組 `expiry_top10`）、`cache`（缺口天數、今天是否已跑過）、
  `vendor_fetch`＋`payload_parse`（`_emit_surface_telemetry()` 把
  observer 給的合併 telemetry 拆成兩個事件——同一份 raw_rows 同時放
  進兩邊，即使其中一個因排放量控制被裁掉，另一邊仍完整帶著「N 筆進、
  幾筆出」）、`database_write`（每天寫入的 call／put 點數）、
  `backfill`（批次摘要：嘗試幾天／存幾天／在哪天中止／原因／
  outcome）。**這四條既有 backfill 決策規則本身逐字不動**——`emit`
  呼叫不參與任何 if／break 判斷，只是把已經在發生的事情說出來。

  **排放量控制**（`_select_for_persistence`，per-request 上限 20 筆）：
  三層優先序——① `backfill` 摘要**先保留、不跟其他事件搶名額**（施工
  中發現：若把摘要跟其他 error／warning 事件混在同一個優先池裡用
  `list[:cap]` 前截斷，事件量一大時摘要反而會被排在後面而擠出去，
  跟「使用者最想看批次結果」的初衷相反，因此改成獨立保留一個名額）；
  ② 其餘事件的 error／warning 依原順序，額滿為止；③ 剩餘名額才輪到
  info。structured log 不受此限，`emit()` 當下就全發了。

  `iv_history()` 端點新增 `_CollectingDiagnostics`（per-request 緩衝，
  `emit()` 寫這個而不是直接寫真正的 storage，log 照樣全發）與
  `_flush_diagnostics()`（request 結束時套用排放量控制、把留下的那批
  真的寫進 `_db()`，同一批也組進回應——畫面看到的跟真的存進 Settings／
  Diagnostics 的是同一批，不會兜不起來）。回應新增 `diagnostics:
  {correlation_id, events}`（純加法，既有欄位語意不變）；候選找不到
  的 404 路徑一樣先落盤再拋錯誤，只是回應本身沒有 `diagnostics` 欄位
  可讀（純字串 detail）。`_known_secrets()` 收集目前設定的 provider
  token 與 `database_url_candidates()`（`storage/factory.py` 新增，
  蒐集 DATABASE_URL 家族**全部**有值的環境變數，不只 `database_url()`
  選中的那一個）供逐字比對 redaction。

  測試：`test_api_iv_history.py` 新增 13 條端點層測試（`_telemetry_
  surface()` 直接餵 observer 指定 telemetry，不依賴 `marketdata.py`
  內部行為——那是 DG-01 的範圍；raw>0/parsed=0 可指認、no_data 不中止
  批次、backfill 中止可見、rate-limit 欄位、correlation id 對得上
  回應標頭、事件同時落盤、token redaction、診斷寫入失敗不影響回應、
  3 條排放量控制單元測試）；`test_api_iv_history.py` 三個既有
  `historical_surface` 假體（`Recorder`／兩個 `ExpirationRecorder`）
  加 `observer=None` 參數以相容新簽章，既有斷言一條未動。全套 pytest
  無回歸（全綠）
- **DG-04** [#147] — Historical IV 投影路徑觀測（reanchor／metrics）＋
  完整 N→0 帳本（commit `62e5dd4`）：新增兩個觀測點。`_emit_reanchor()`
  逐日發一筆——當天曲面（`option_type` 對應那張網格）的 dte／delta
  範圍、要查的 tenor／買賣腿 delta、四個欄位（buy_iv／sell_iv／
  atm_iv／normalized_skew）各自是否為 null；這是「資料明明有、畫面卻
  空白」唯一看得見的地方（`iv_at()` 出界回 None、不外插的既有行為
  本身不動）。`_emit_metrics()` 在 `field_metrics()` 之後每個欄位各發
  一筆（不是一筆合併事件）——比合併事件更看得出是哪一項指標沒有觀測。

  **單腳候選豁免**（兩處都有）：Long Call 結構上沒有賣腿，
  `sell_iv`／`normalized_skew` 恆為 `None`／`count=0` 不是資料品質
  問題；`_emit_reanchor` 的「全部 null 才算 warning」與 `_emit_metrics`
  的欄位清單都排除這兩項（依 `coords.get("sell") is None` 判斷），
  否則每個 Long Call 候選會永遠亮 warning，是新增訊號而非既有裁示——
  「只顯示存在欄位」原則的延伸應用。

  **`_select_for_persistence` 追加保留規則**（施工中發現，追加在
  DG-03 既有機制上）：`metrics` 跟 `backfill` 一樣獨立保留名額，不跟
  高流量的逐日事件（尤其 `reanchor`，快取滿一年時一次 request 可能
  ~65 筆）搶——常數改名 `_ALWAYS_KEPT_STAGES = ("backfill", "metrics")`，
  三層優先序的第一層從「只保留 backfill」擴大成「保留這兩個 stage」。
  若不追加這條，`reanchor` 一多就會把 `metrics` 擠出 20 筆的 cap，
  完整帳本測試因此抓到這個問題並在動工當下修正，不是留到 DG-07 才發現。

  測試：`test_api_iv_history.py` 新增 10 條——reanchor 出界／覆蓋兩種
  severity、單腳 reanchor 豁免、metrics 全零／有資料兩種 severity、
  單腳 metrics 豁免、完整帳本測試（八站都在同一個 correlation_id 下、
  payload_parse 單筆事件自己就答得出「N→0」）、`_select_for_persistence`
  新增一條驗證 `metrics` 與高流量 `reanchor` 共存時不被擠掉。全套
  pytest 無回歸（全綠）
- **DG-05** [#148] — Inline diagnostics：Historical IV 卡片就地展開
  錯誤詳情（commit `ad5924e`）：`src/api.ts` 新增 `DiagnosticEvent`／
  `IvHistoryDiagnostics` 型別＋ `IvHistoryView.diagnostics` 欄位；
  `ApiError` 新增 `correlationId`（`request()` 從 `X-Correlation-Id`
  回應標頭讀，`resp.headers?.get(...)`——既有測試大量用簡化物件字面量
  假冒 `Response` 省略 `headers`，用可選鏈避免連帶炸掉那些無關測試）。

  `IvHistory.tsx` 新增 `InlineDiagnostics`／`DiagnosticEventFields`：
  沿用 `AnalysisReport.tsx` 既有的 `<details>`／`<summary>` 收合慣例，
  不自己寫展開狀態機。觸發條件兩種——請求整個失敗（`error` 狀態，
  只帶 message／correlationId，沒有結構化 events 可顯示）；或回應帶有
  severity ≥ warning 的 events（200 但資料是空的那個最常見症狀，只看
  HTTP 狀態碼看不出來）。**只顯示實際存在的欄位**天然成立——不需要
  前端另外過濾，因為後端 `sanitize_context()` 產生時就把 `None` 拿掉了，
  `context` 裡沒有的 key 本來就不會出現。前端零解讀邏輯：`severity`／
  `stage`／`message`／`context` 全是後端字串，只做格式化與呈現。

  測試：`IvHistory.test.tsx` 新增 8 條（卡片本身仍在＋預設收合、展開／
  收合、200 但有 warning events 觸發、只有 info 不觸發、展開後看得到
  完整欄位、只顯示存在欄位、多筆 events 各自完整呈現）；`ivView()`
  fixture 補上 `diagnostics` 欄位，既有斷言一條未動。前端全套
  `typecheck`／`vitest`（515）／`build` 無回歸；後端全套 pytest 無回歸
  （全綠）
- **DG-06** [#149] — Settings：Diagnostics / 報錯紀錄 區塊（commit
  `c234f0c`）：`src/api.ts` 新增 `getDiagnostics()`／`clearDiagnostics()`。
  新元件 `src/Diagnostics.tsx` 掛在 `Settings.tsx` 既有兩列（Market
  Data／Historical IV）下方，同一個 `<section className="card
  settings-section">` 慣例——不需要另外的可見性判斷，就是 Settings
  頁多一塊。清單最新在最上（**信任後端順序，前端不重新排序**）；每列
  timestamp／subsystem／stage／severity／message；點一筆用原生
  `<button>` 展開完整 details（含 `context` 逐 key 呈現，同一套「只顯示
  存在欄位」原則）。**Copy**：`navigator.clipboard.writeText` 成功時
  按鈕文字短暫變「已複製」；clipboard 不可用或被拒時退回顯示一個唯讀、
  可全選的 `<textarea>`（`onFocus` 自動全選）——不是靜默失敗。
  **Clear**：兩段式就地確認（按鈕變「確定清除」＋「取消」），不用
  modal，確認後才真的打 `DELETE /api/diagnostics`。空清單顯示「目前
  沒有紀錄」。沒有 pagination、搜尋、圖表（票上明文範圍）。

  **既有測試連帶修正**（`Settings.tsx` 現在多掛一個會自己打
  `/api/diagnostics` 的子元件，影響既有 `Settings.test.tsx` 的假體）：
  `mockApi()` 依 URL 分流，`/api/diagnostics` 固定回空陣列，不吃掉
  原本那組 `SettingsView` 序列的計數器；「載入失敗」測試原本斷言
  `getByRole("alert")` 只有一個，現在 `<Diagnostics />` 自己的請求也會
  用同一個失敗假體產生第二個 alert，改用 `getAllByRole` 找特定內容——
  兩處都是配合新子元件調整既有測試的注入方式，斷言涵蓋的行為本身未變。

  測試：新增 `src/Diagnostics.test.tsx`（11 條：空清單文案、五欄位
  清單、依後端順序渲染不重排、展開／收合、Copy 含 fallback、Clear
  含二次確認與取消、讀取失敗說明原因、結構）。前端全套 `typecheck`／
  `vitest`（526）／`build` 無回歸；後端全套 pytest 無回歸（全綠）
- **DG-07** [#150] — 最終 regression／security gate（commit `714e9cc`）：

  **兩個真實回歸**（施工中發現、修在這張票）：
  1. `IvHistory.tsx` 存取 `data.diagnostics.events` 未做防禦——大量既有
     E2E 手造的 iv-history JSON fixture（`smoke.spec.ts`／
     `desktop.spec.ts`，DG-05 之前就存在）沒有 `diagnostics` 欄位，
     跑下去整頁炸掉。改成 `data.diagnostics?.events ?? []`，不必連帶
     改寫每一處既有 fixture。
  2. `Diagnostics.tsx` 清單列在 iPhone 13 寬度（375px）把
     timestamp／subsystem／stage／severity／message 硬擠成一行，
     message 的可用寬度被擠到 0（技術上存在、視覺上不可見，
     Playwright `toBeVisible()` 判 hidden）——這正是 QA-FIX-1／
     QA-FIX-4 那種「幾何驗證勝過文字存在性檢查」教訓的又一個真實案例，
     被 DG-06 新增的 E2E 測試當場抓到。改成 metadata／message 兩行
     （`.diagnostics-row-meta` 包住前四項，message 獨立一行）。

  **Security gate**：`test_api_diagnostics.py` 新增端點層 redaction
  全表面驗證（跟 `test_diagnostics.py` 純函式層級的既有斷言換一個
  角度、從 HTTP 回應往回驗）——已知 provider token／已知
  `DATABASE_URL`（含帳密子字串）不逐字出現在 `GET /api/diagnostics`
  回應裡；white-list 外的 key（`authorization`／`cookie`）整包被丟棄；
  超長 `errmsg` 截斷且看得出截斷過；`headers` 整個 dict 值本身不在
  白名單、原封不動被丟棄，只有 rate-limit 白名單三欄留下。
  `test_api_iv_history.py` 新增「即使 observer telemetry 意外多帶一個
  完整回應內容的欄位（模擬 `raw_body`），`_emit_surface_telemetry()`
  用具名關鍵字組 event、不是 `**telemetry` 全展開，那個欄位天生進不了
  任何診斷事件」。

  **Observation-only 回歸**：`test_selection_regression.py` 新增
  `test_ranking_and_filters_do_not_depend_on_diagnostics()`——與既有
  `ivhistory` 同名結構斷言同一種手法，`ranking.py`／`filters.py`
  原始碼不含 `diagnostics` 字樣。`_backfill_iv` 的 break 時機、
  `iv_at()` 不外插、`IvBackfillRun.outcome` 語意本輪一律未動，由
  DG-01–DG-06 全程保持既有測試綠燈佐證（未新增額外斷言，這些既有
  行為的專屬測試本來就覆蓋著）。

  **E2E**：`smoke.spec.ts` 新增 2 條（手機：Historical IV 請求失敗
  預設收合／可展開可收起／帶 correlation id；200 但帶 warning events
  同樣觸發，資料照常渲染）＋ 1 條（手機：Settings Diagnostics 區塊
  可讀可操作，含展開與 Clear 二次確認）；`desktop.spec.ts` 新增 1 條
  （桌面：同上）。新增測試踩到的 route pattern 陷阱：`**/api/diagnostics`
  沒帶尾端 `*` 匹配不到真實請求的 `?limit=50` 查詢字串（既有
  `iv-history*` 早就示範過這個慣例，這次補教訓——5 處遺漏統一補上
  尾端 `*`）。

  **全套綠燈**（一條斷言都沒放寬）：後端 pytest 全綠；前端
  `typecheck`／`vitest`（526）／`build` 全綠；E2E `playwright test`
  （iPhone＋Desktop 共 71 條）全綠。

  **交付**：push 到 `claude/implement-tfm9oa`。Preview deployment 與
  Vercel runtime logs 由需求方端（ChatGPT）另行驗證，不列為本票驗收
  項目（spec #143 2026-08-15 修訂）。**不開 PR**。

**spec #143（DG-01–DG-07，issues #144–#150）七張票全數完成。**
Application Diagnostics 基礎設施＋Historical IV 完整八站
observation chain（candidate_lookup／cache／vendor_fetch／
payload_parse／database_write／backfill／reanchor／metrics）已上線，
成功判準（「不必讀程式碼就能直接回答 vendor 回 N 筆究竟在哪一站變成
0 筆」）已由完整帳本測試（DG-04）與端點層驗證（DG-07）證實成立。
等 ChatGPT 驗證 Preview deployment；需求方尚未 cue 是否要合併回
`master`（依專案規則，PR 開不開由需求方主動要求，不主動開）。

### QA 反饋直接施工（2026-08-16）——Historical IV 固定版位＋Inline Diagnostics Copy 按鈕

需求方以 `/qa` 呼叫但直接給了施工等級的完整規格（含明確排除範圍與
「完成後 commit + push」指示），視同直接下工單處理，不走 `/qa` 平時
「只訪談、開 issue、不動手」的預設流程。範圍明文排除：Historical IV
演算法、vendor request、HTTP 402 handling、backfill、ranking/filter/
selection——本輪只動 `src/` 前端呈現層，`option_chaser/`／`api_app/`
一行未碰（已用 `git diff --stat` 核對）。

**問題 1：Historical IV 版位不固定**——原本 `IvHistory.tsx` 在
`ivHistory()` 請求 pending 期間直接 `return null`（`error` 分支與
`enabled !== true` 這條 #126 閘門是分開的兩件事，後者原封不動保留），
資料回來前卡片整塊不存在，造成頁面載入後版面「突然長出來」。改成
`enabled === true` 之後卡片外框（`<section className="card
iv-history">`）永遠掛著，內部依 `error` / `!data` / 有資料三態切換：
新增 `IvHistorySkeleton`（依候選 `isSingleLeg` 決定 1 或 2 個次層佔位
方塊，形狀跟真正的 `.iv-metric` 頭條／次層同構，資料回來前後高度
不整個跳動）在 `!data && !error` 時顯示；有資料內容抽成
`IvHistoryContent` 子元件（純粹是把「四態同一版位切換」那段 JSX
拆乾淨，不是新分層原則）。「無資料」本來就不是獨立分支——`count===0`
已由既有 `metricCaption()` 逐項顯示「沒有歷史資料」，資料物件本身
照常存在、卡片照常渲染，這次修正前就已成立，不需要額外處理。骨架
CSS（`.iv-skeleton*`）用 `aspect-ratio` 貼近真實 `Metric` 頭條/次層
比例＋線性漸層 shimmer 動畫，`prefers-reduced-motion: reduce` 時關閉
動畫。

**問題 2：Inline Diagnostics 加 Copy 按鈕**——新增共用模組
`src/DiagnosticDetail.tsx`（`SEVERITY_LABELS`／`diagnosticEventFields`／
`DiagnosticEventFieldList`／`CopyDiagnosticButton`），整套從
`Diagnostics.tsx`（DG-06／#149）既有的私有 `SEVERITY_LABELS`／
`eventFields`／`CopyButton` 抽出來，`Diagnostics.tsx` 與
`IvHistory.tsx` 兩處改成呼叫同一份，不重做第二套格式化／複製邏輯
（需求方明文要求）。抽出時**順便修掉一個既有漂移**：`IvHistory.tsx`
舊私有 `DiagnosticEventFields` 直接印 `event.severity` 原始英文字串
（`"warning"`），跟 `Diagnostics.tsx` 用中文標籤（`"警告"`）不一致——
消掉這份重複的直接結果就是兩處現在都印中文標籤，`IvHistory.test.tsx`
既有一條斷言原文字比對 `"warning"` 因此改成比對 `"警告"`（唯一因這次
重構而變的既有斷言）。`InlineDiagnostics` 版面依需求方裁示調整為
「錯誤摘要 → Copy diagnostics 按鈕 → 下方完整 diagnostic details」
（跟 Settings 那邊 `EventDetail` 「fields 在前、Copy 在後」的順序刻意
不同，兩處各自組裝、共用的只是欄位清單元件與 Copy 按鈕本身）；新增
`message` prop 讓純請求層失敗（無結構化 events 可看）的情境也能把
錯誤訊息一起放進複製內容。收合／展開行為（`<details>`／`<summary>`）
原樣保留，clipboard 不可用時沿用既有的唯讀 `<textarea>` fallback。

**測試**：`IvHistory.test.tsx` 新增 9 條（loading 中卡片已在原位顯示
骨架＋資料到位後骨架消失卡片數不變、Spread 兩個次層方塊／Long Call
一個、error 狀態沿用同一版位、無資料狀態卡片照常在、Copy 按鈕版面
順序、Copy 內容含 correlation ID 與事件清單、請求失敗時 Copy 內容
帶錯誤訊息、clipboard 不可用時 fallback、收合展開行為保留）；既有
1 條斷言改比對中文標籤（見上）。`Diagnostics.test.tsx` 11 條原樣
全綠（抽出共用模組沒有改變任何可觀察行為）。E2E 手機＋桌面各新增
2 條（固定版位骨架、Copy 按鈕版面順序＋clipboard 內容＋收合展開），
共 4 條，用 `page.context().grantPermissions(["clipboard-read",
"clipboard-write"])` 讓 headless Chromium 真的能讀寫 clipboard 驗證
複製內容，而不是只斷言按鈕存在。

**全套綠燈**：後端 pytest 全綠（本輪未觸碰後端，純確認無回歸）；
前端 `typecheck`／`vitest`（535）／`build` 全綠；E2E `playwright test`
（iPhone＋Desktop 共 75 條）全綠。

**交付**：commit＋push 到 `claude/implement-tfm9oa`，依需求方指示
不開 PR。

### 第七輪研究（2026-08-16）——Historical Rich/Cheap canonical methodology 重新確認（只研究不施工）

需求方 `/research` 指示：**重新確認** canonical methodology，明令
**不得因既有實作已經做了 fixed-(tenor, delta) 就給 sunk-cost 優勢**，
也不得預設 `IV − realized vol` 就是 fair-value residual。產出
`docs/research/historical-rich-cheap-canonical-methodology.md`
（16 節、70KB）。未改動任何 code、未開 issue。

**裁決＝C（hybrid），但是非對稱、界線寫死的 hybrid**：
- 最直接回答「這張現在貴不貴」的是 **A 家族的 fair-value residual
  本身**，不是它的歷史。SAS 定義 `SAS(K,T)=Σ_market−Σ_H`，`Σ_H` 由
  **標的報酬史**推出，**不需要這張合約的任何報價歷史**【一手原文】。
- 能掛 1Y 走勢圖／percentile／Δ4w 的 canonical 量**只能是 B 的
  fixed-(tenor, delta) 重錨定序列**——理由是與 vendor 無關的可得性
  算術：A 需 `L ≥ D+T`、B 只需 `L ≳ D`。真實 fixture 的 TLT LEAPS
  D=882 天時 A 需 L≥41 個月 > 39 個月掛牌上限，**A 在數學上不可能，
  換誰家、付多少錢都一樣**。
- **`IV − realized vol` 明確否決**：SAS 第 1 頁把它列為與 SAS 並列的
  **另一把尺**、「options replicators 的指標」、「有 skew 時就不精確」
  【一手原文】。它量的是 variance risk premium，不是這張合約的錯價。
- **結構性死路**（殺掉 full-SAS 路線）：SAS 裡唯一大得過摩擦的成分
  （level ≈ IV−RV）是 **GS 自己主動歸零**的那一半（SAS_ATM）；剩下
  可信的 skew richness 實測只有 **0.15–0.5 vol 點 vs 買賣價差半寬
  0.80–2.65 vol 點**。
- **引擎實算（新增、決定性）**：環境凍結下把 DTE 882→252，raw gap
  與 Ĝ 同步漂移 **+87%**（÷ATM 不能消除 roll-down），同座標殘差漂移
  **0.000**——這是 A 唯一真實的結構優勢，但在本產品 tenor 上用不到。
- **Spread 合成**：逐腿 residual → 各自 vega → price 空間、依部位符號
  相加；**單一「Spread IV」否決**（net-volatility 在真實 TLT 部位上
  解出 −0.74 vol 點，1% vega 擾動跳 0.41 點）。
- **必要 normalization（保留）**：固定 tenor、固定 delta、不外插、
  skew ÷ ATM、rank 統計量。**不該當訊號**：買腿 IV percentile 當
  「貴不貴」的答案、Ĝ 絕對值跨候選比較、Δ4w 當方向、觀測 <10 筆的
  percentile、貼網格邊界的 ATM 內插。

**⚠ 順帶標出一個可驗證的風險（非已確認 bug）**：`ivhistory` 的
delta 座標用引擎 `q=0`（#122 紅線），vendor 曲面網格的 delta 若帶
股利，同一張真實 TLT LEAPS 是 0.7194（q=0）vs 0.4478（q=4.5%），
查表會落在 **K=74.03 而非 K=85**、系統性偏 **−1.95 vol 點**。
vendor greeks 的 q 慣例在沙箱無法驗證（#111）。

**唯一殘留 blocker**：TLT 這類 ETF 的**實際**最長掛牌前置期 L（目前
只能界定在 [29, 39] 個月）。它只影響 18–29 個月 tenor 那一段的 A vs B
邊界，**不影響 882 天核心情境的裁決**。

⚠ **本輪沒有任何【官方文件】等級證據**：交易所／OCC／vendor 官方網域
（`docs.marketdata.app`／`cboe.com`／`theocc.com`／`sec.gov` 等）在沙箱
全數 CONNECT 403 或 DNS 解析不到，掛牌規則整節是【二手轉述】。
`raw.githubusercontent.com` 仍是唯一一手通道——本輪由此取得 **SAS 全文
PDF** 與**一份真實 Cboe 全鏈 JSON**。證據分級統計：【一手原文】35、
【官方文件】3、【二手轉述】36、【自行推論】37。

**下一步**：等需求方審閱裁決。**本輪不施工、不開票。**

### 最新狀態（2026-08-14）——「貴不貴」第六輪研究：Rich/Cheap Trend／entry timing（只研究不施工）

需求方 `/research` 指示本輪只研究、不修改程式碼：在既有「現在相對
歷史站在哪」（percentile／座標正規化／橫斷面殘差）之上補**時間軸
動態層**——這組 Call／Vertical Spread 現在便宜/正常/貴**且正在往哪
走**，回答「再等有沒有合理機會拿到更好進場價」，且必須拍板單一
方案、不開菜單。產出 `docs/research/rich-cheap-trend-entry-timing.md`。
⚠ 派工前發現本紀錄區漏了三份 2026-08-13/14 的研究文件（
`option-richness-assessment-methods.md` 第四輪——其【repo 實證】段
因 checkout 倒退已自我標注不可信、
`directional-option-fair-value-workflow.md`、
`modern-surface-methods-rich-cheap-architecture.md` 第五輪四層
Rich/Cheap Engine 架構），先前 session 未記入，以檔案本身為準；
本輪文件 §10 已與第五輪架構逐點對位（承接 Layer 0–2 不動、拍板
第五輪刻意留白的時間層、無衝突）。

**最終拍板：既有 Historical IV Position 序列上的「Percentile＋Δ4w」
趨勢層**——零新增資料源、零新增 vendor 呼叫，`field_metrics()` 對
既有四欄位各純加法新增 `{trend_4w, trend_base_date}`：Δ4w＝最新
觀測 −「[today−42, today−21] 容忍窗內距 today−28 最近的一筆」，
窗內無點誠實留白「4週 —」（沿用 `iv_at()` 不外插哲學）。Long Call
主讀數＝買腿 IV percentile＋Δ4w（level 語言）；Spread 主讀數＝
Normalized Skew Ĝ percentile＋Δ4w（skew 語言，兩腿 IV 次層）——與
MVP V3 資訊權重一致，且引擎實算背書：spread net vega 僅裸買腿
40%、gap 敏感度為 level 兩倍（1 gap pt ≈ 11.6% of debit vs 裸腿
12.3%/pt）。呈現只延伸既有 caption 一格「第 P 百分位・N 筆觀測・
4週 ±X」，帶正負號原始變化量、量自身單位，無顏色/箭頭/象限標籤/
預測句；方法論尾註補 Δ4w 定義＋「等待另有 spot 風險與 theta 成本」
誠實條款（引擎實算：等一週 spot 不確定性 ±19% of debit、一個月
±39%、LEAPS theta ~0.8%/週——指標只 scope vol 分量，不假裝能 time
spot）。4 週 lookback 落在三個獨立來源家族收斂的 IV level 因子
half-life 證據帶（GARCH α+β 0.97–0.99→23–34 交易日；Cont–da
Fonseca τ≈28/51 天；Kamal–Derman 低維結構）＋FX RR 1M lookback
成文慣例＋既有抽樣密集段（≤90 天每週 2 點）可靠支撐 Δ4w 而撐不起
Δ1w／Δ3m。

**明確否決（各附證據）**：IV Rank（第一輪原判）、z-score（離群值
敏感＋常態假設不成立）、volatility cone（Burghardt–Lane 1990——
另一題：IV vs RV 分布；其 tenor-matching 紀律已被固定 (tenor,
delta) 座標繼承）、per-symbol half-life／AR(1)／OU（66 點/年不等距
抽樣估不出，文獻 half-life 只用來校準 lookback、不做成 per-symbol
顯示）、model-based expected drift／任何 forecast（facts-only 紅線
＋Harvey–Whaley 1992：IV 變化統計可預測但扣成本無 edge）、
term-structure slope 進場訊號（Simon–Campasano 一手全文：基差不
預測 spot vol 變化、只反映可收割溢酬）、Markov regime-switching
（desk 級部署證據缺席）。本輪新增三份一手全文（GitHub 鏡像
`emintham/Papers`：Simon–Campasano 2012、Cooper 2013——momentum
活在 ETP carry 層非 spot vol 層、Carr–Wu 2005）。enrich-only 紅線
（spec #117）結構性繼承——趨勢欄位只進 iv-history 端點，
ranking/filters 不 import ivhistory 的既有測試保證原樣有效。
**已進 spec：issue #137**（2026-08-14 `/to-spec`，`ready-for-agent`）。

### Spec #137——Rich/Cheap Trend：Δ4w＋一年走勢圖＋Long Call 納入

需求方與顧問討論後裁示（對話 0014／0015）：框架採第六輪研究的
「Percentile＋Δ4w」，但 **UI 改為走勢圖為主**——不是只顯示 P22，而是
直接看一年走勢圖（percentile 給位置、圖給路徑、Δ4w 給最近速度，
三者互補）；且明示「我要的是尺，不是預言機」，不接受 ARIMA／ML／
regime model 這類「模型一換答案就變」的東西。Long Call 一併納入。

**兩道 Grill Gate 已於 spec 內查證答覆，施工時不必重查**：

- **Gate 1（Spread 主追蹤量：Ĝ vs package cost）→ 維持 Ĝ**。依據
  第三輪 `spread-price-percentile-vs-vol-space.md`：price 空間被
  dominated（引擎實算 r 3%→5% 使 TLT LEAPS spread 理論價 +26% ≈
  gap 動 4 個 vol 點，而該實例 raw gap 總共才 6 pts；另需歷史股息率、
  q=0 引擎高估近一倍；per-candidate 無業界先例）。**但顧問點出的
  「skew 漂亮但 vol level 高、debit 仍比歷史貴」是真的**——解法不是
  換掉 Ĝ，而是**買賣腿 IV 各自擁有完整走勢圖＋percentile＋Δ4w**，
  水位與結構形狀兩個軸並陳，不融合成一個數字（融合就必須進被利率／
  股息汙染的 price 空間）
- **Gate 2（四元件成熟度與假訊號）→ 全部是成熟穩定的「尺」**：重錨定
  ＝雙軸線性插值嚴格不外插（無擬合／無最佳化器）、Ĝ＝純算術對 r/q
  零敏感、percentile＝rank statistic 本質抗離群、Δ4w＝減法。
  **唯一真正新增的風險是 Δ4w 的兩點脆弱性**（percentile 在 ~66 點上
  抗得住一筆爛報價，兩點差抗不住）→ **決策：基準改取 [21,42] 天窗內
  觀測的中位數**（密集段每週 2 點、該窗典型約 6 筆），不是單一最近點；
  除既定窗口外不引入任何可調參數，仍是尺。其餘假訊號源（稀疏 LEAPS
  chain、delta 軸邊緣、插值平滑、vendor 報價、#111 blocker）逐項盤點
  於 spec

**契約為純加法**：`field_metrics()` 每欄位新增 `trend_4w`＋
`trend_base_count`；`value`／`percentile`／`count` 語意完全不動。
**Long Call 是新增能力不是改顯示**——現況 `spread_coordinates()` 對
單腳直接回 None（MVP V3 明文只做 Spread），需新增單腳座標路徑，
Ĝ 與賣腿 IV 誠實回 None。走勢圖沿用 `SpreadHistory.tsx` 既有形態
（手刻 SVG、幾何抽純函式、y 軸固定、缺值斷線、tooltip），不引入
圖表函式庫。**#135「壓到合理最低」在本區塊被「走勢圖為主」覆蓋**
（需求方新裁示，非遺漏舊裁示）。enrich-only 與 facts-only 紅線原樣
繼承，並新增「禁止任何預測語句」。

**拆票完成（2026-08-14 `/to-tickets`，五張全掛 `ready-for-agent`）**，
依 #137 一比一切五張。

**施工完成（2026-08-14 `/implement`，依序單線施工、不平行）**：

- **RCT-01** [#138] — Δ4w 引擎純函式＋API 契約純加法（commit
  `0158dc7`）：`ivhistory.trend_4w()`＋`field_metrics()` 擴充
  `trend_4w`／`trend_base_count`；中位數守門測試（離群觀測不改變基準）
  已涵蓋
- **RCT-02** [#139] — Long Call 單腳 Historical IV 資料路徑（commit
  `1864ba1`）：`spread_coordinates()`／`reanchor_spread()` 開通單腳，
  option_type 隨座標回傳供曲面查找（避免 Long Put 誤用 call 網格）。
  **施工中發現並一併修正的上層阻擋**：`store.find_candidate()` 原本
  只搜 `expiry_top10`（T9 附錄A7：single-leg 恆為空），單腳候選過去
  在這一步就找不到——修正為沒有 `expiry_top10` 分組的策略才退去搜
  扁平 `candidates` 清單，兩腿路徑零回歸
- **RCT-03** [#140] — 一年走勢圖為主體＋Percentile＋Δ4w＋雙模式版型
  （commit `0ffc84e`）：新增 `src/ivHistoryChart.ts`；`IvHistory.tsx`
  全面重寫，Spread 模式 Ĝ 主位＋買賣腿次層、Long Call 模式買腿 IV
  主位＋ATM IV 次層；Normalized Skew 現值格式一併修正為無因次小數
  （與新增 Δ4w 同語言，避免同一欄位兩套單位並列）；#135 壓平裁示在
  本區塊被覆蓋
- **RCT-04** [#141] — 桌面／手機整合＋缺資料狀態全景 E2E（commit
  `6c3537e`）：67 個 E2E 案例（41 手機＋26 桌面）全綠。**施工中發現
  並修正**：(1) 真實 App 導覽路徑（`baselineTopCandidate`＋
  `_MVP_STRATEGIES` 皆 Spread-only）結構上走不到 Long Call 模式，比
  #139 更上層，不在本輪範圍——Long Call 版型改依賴 RCT-03 的 Vitest
  元件測試驗證；(2) 既有 E2E fixture 用 250 點模擬全年歷史，遠超引擎
  `sampling_schedule` 實際約 55–75 點的密度，250 個 8px 圓圈擠在手機
  走勢圖裡嚴重重疊、連自動化都點不準——改為 66 點貼近真實密度
- **RCT-05** [#142] — 最終 regression gate（commit `a87a9c6`）：
  `test_selection_regression.py` 新增行為＋結構雙重證明——用力呼叫
  本輪全部新函式夾在兩次 identity snapshot 之間身份不變；
  `ranking.py`／`filters.py` 原始碼不含 `ivhistory` 字樣。
  pytest／typecheck／build／vitest（508）／e2e（67）全綠，未紅燈
  調整任何斷言

**spec #137 五張票全數完成，等需求方實機驗收；PR 未開，等 cue。**

> 本 session 內容器 checkout 曾五度自行倒退到 `4d3cea3`（V1 期）——每次
> 都在寫檔前 `git rev-parse HEAD` 核對抓到，用 `git fetch origin
> claude/implement-tfm9oa && git merge --ff-only origin/claude/
> implement-tfm9oa` 復原，未造成任何內容遺失。後續 session 若遇到同一
> 個 HEAD（`4d3cea3`），這是已知的容器陷阱，不是需要調查的新狀況。

### 最新狀態（2026-08-12 第四輪）——Historical IV 綁定修正＋壓平＋Refresh 漸進解鎖

需求方三段 `/to-tickets` 指示，三張票全數完成並推上
`claude/implement-tfm9oa`（未 merge master、未開 PR）：

- **#134** ✅ 長天期候選 Historical IV「連線成功但無資料」root cause
  修正（commit `81c91b5`）。**真因**：Market Data App 的
  historical chain 端點（`GET /options/chain/{symbol}/?date=...`）
  不帶 `expiration` 篩選時，官方文件明載只回「下一個月選」——對
  LEAPS 等長天期候選的曲面永遠覆蓋不到其座標，`ivhistory.iv_at()`
  依既有不外插紅線全部回 `None`，呈現成「連線成功但無資料」。修法：
  新增 `ivhistory.nearby_expirations()`，從這個 Scenario **已經分析
  過**的到期日（`view["results"][i]["expiry_counts"]`，zero 額外
  vendor 成本）裡挑出離目標 tenor 最近的幾個（預設上限 4 個，短天期
  ≤45 天刻意回空、沿用免費的 vendor 預設），`_backfill_iv()` 逐一
  帶 `expiration=` 打、合併成同一天的曲面再存一次——不用
  `expiration=all`（會扣光整條鏈額度）。`map_surface_payload` 同時
  補上 `s == "no_data"` 視為合法空結果（不是 vendor 故障），這是帶了
  單一到期日篩選後的常態撲空，原本會誤判成錯誤中止整批 backfill。
  次要修正：`leg_coordinate()` 計算 delta 原本硬編 `rate=0.0`，改讀
  候選自己的 `rate_used`（`CandidateView.rate_used`，與正式估值管線
  `leg_rate()` 同一個數字）；`q=0` 沿用既有 #122 紅線（分級用途 delta
  恆用 q=0／vendor IV）不變。Test Connection 職責完全未動
- **#135** ✅ Historical IV UI 依 `docs/Mvp-v3-appendix.txt` 壓平
  （commit `225573a`）。核對結果：資料綁定語意（每次都是當前候選的
  `candidate_key`）與資訊優先序（Normalized Skew → Buy Leg IV →
  Sell Leg IV）本來就正確，真正的落差在視覺密度。`.iv-history` 內距
  比照 `.summary-card` 密度覆寫（16px→12px）；每個指標從 label／
  value／百分位三行堆疊壓成兩行（標籤＋百分位同一行、數值自己一行，
  新增 `.iv-metric-head`）；sparkline 高度 24px→18px、兩腿寬度再收窄
  56px。只陳述事實、不加評價字眼的既有測試守門不變
- **#136** ✅ 整輪刷新逐劇本漸進解鎖與即時排序（commit `098b3b9`）。
  排進刷新佇列的當下（整輪、單一劇本重試、建立後那一批，三者共用
  同一條佇列）立刻反灰＋拿掉 `href` 禁止點入；每個劇本一完成（成功
  或失敗）立刻從 `lockedIds` 移除，不必等整條佇列跑完，並用最新
  `best_return` 立刻參與已完成區排序。新增純函式
  `scenarios.partitionByLock()` 把清單拆成「已完成」（照舊排序）與
  「還鎖著」（維持佇列順序、不參與排序）兩段，`ScenarioList`／
  `CompactScenarioList`／桌面 `ScenarioDetail`（`refreshLocked` 提示，
  搶在其他內容之前）共用同一套 `lockedIds` 狀態。失敗也會解鎖、沿用
  既有 yellow／stale 語意，不會永久反灰。未新增第二套 refresh
  pipeline、不刪除任何舊快照資料。順帶修掉 `App.test.tsx` 三個既有
  測試的隱性競態（多了一次 `setLockedIds` 的 setState 讓沒等開站那輪
  批次刷新落定就操作的舊測試現形），補上與檔案內既有測試一致的
  settle wait，不是放寬斷言

**回歸紅線全數確認未變**：Spread ranking／filtering／candidate
generation／`expiry_best`／`expiry_top10`／代表候選身份／
`best_return` 排序語意（`sortScenarios` 本身未改，只是新增
`partitionByLock` 包一層）、#118 選取身份回歸 12/12。

**測試現況**：Python 1119、前端 482、E2E 61（桌面＋手機兩個
project），#118 選取身份回歸 12/12，全綠（Postgres adapter 以本機
PG16 實跑，非 skip）。

**遺留待需求方處理**：#134 的修法依賴「這個 Scenario 已經分析過的
到期日」作為目標 tenor 的候選池——若使用者在同一 symbol 上只分析過
單一窄範圍的到期日（例如只看過近月），第一次查詢遠期 LEAPS 候選的
Historical IV 時，`nearby_expirations()` 仍會用手上有的最接近選項
嘗試（不會完全空手），但涵蓋精確度不如已分析過多個到期日的情況；
理論上限——Market Data App 官方文件是否真的支援 `?date=` 搭配
`&expiration=` 兩參數同時使用**沒有在沙箱驗證過**（沙箱對
`api.marketdata.app` 出口網域仍是 CONNECT 403，本輪修法完全依賴
WebSearch 轉述的官方文件內容），需要需求方在有真實 token 的 production
環境實測確認。

### 最新狀態（2026-08-12 第三輪）——移除 Historical IV 的 coverage 門檻

需求方裁示：Historical IV 的問題定義是「目前 IV 在實際取得的有效歷史
observations 中位於什麼位置」，只要有至少一筆可比較觀測就該顯示
percentile，不得因 coverage 低、樣本稀疏、或觀測數低於任何固定門檻而
隱藏——這推翻了第二輪 #130／#131 裡「coverage < 0.5 就不給 percentile」
「status 不是 ok 就整段換成短訊息」的設計。

- **#133** ✅ 移除門檻，percentile 一律呈現並揭露觀測筆數（`8bae985`）。
  `_IV_MIN_COVERAGE`／`coverage_ratio()` 整組刪除（那個函式的唯一用途
  就是這個門檻，門檻拆了它就是死碼）。純函式層（`weighted_percentile`）
  本來就沒有 coverage 判斷，這次修正跟 #128 的抽樣／加權演算法沒有衝突
  ，不需回頭改動。`weighted_percentiles_of()` 換成 `field_metrics()`：
  每個欄位各自回 `{value, percentile, count}`，`count` 是這個百分位
  背後有幾筆有效觀測，讓使用者自己判斷資訊強度——不是產品替他判斷
  「樣本不足不值得看」。`status`（ok／quota／vendor）語意改變：只描述
  這次 backfill 嘗試的結果，不再影響 percentile 顯示；已快取的觀測不
  因今天撞額度就被藏起來，變成疊加在指標之上的一行附加說明。前端
  `metricCaption()` 把百分位與觀測筆數合成複合標籤（「第 62 百分位・
  45 筆觀測」），是需求方「P90 · 9/10」語意示例的落地呈現。**#130／
  #131 補了留言標明哪些敘述被取代**（門檻機制本身，其餘 progressive
  backfill／enrich-only／閘門紅線不受影響，下方 bullet 內容以此為準
  ，不再逐一更正）

**測試現況**：Python 1103、前端 471、E2E 61，#118 選取身份回歸 8/8，
全綠。

### 最新狀態（2026-08-12 第二輪）——quota 架構＋編輯劇本

需求方最終產品模型（A–E 段）拆成 6 張票並全數完成，推上
`claude/implement-tfm9oa`：

- **#127** ✅ Historical IV 共用 credential（`9772733`）。規則：token
  輸入框只出現在**由上而下第一個使用該 Provider 的自訂列**，其餘列顯示
  「與上方共用 credential」。這同時解掉「兩列都自訂時輸入框該在哪」與
  「只有 Historical IV 自訂時無處可設」兩種情況
- **#128** ✅ 抽樣排程＋時間加權 percentile（`1c4f8f8`）。近 90 天每週
  約 2 點、90 天到 1 年每週約 1 點，全年約 66 點而非 250+；窗仍是完整
  1 年。挑哪天由 `crc32(symbol:week)` 決定——**不能用內建 `hash()`**，
  str 雜湊每個 process 都不同，排程會每次重啟就變、backfill 永遠追一份
  移動的目標。Voronoi 時間權重，單點代表上限 14 天（沒有上限的話一段
  長空窗會讓緊鄰的那一點吃下整段權重，那就是插值）
- **#129** ✅ per-symbol 觀測快取（`04a277d`）。鍵是 (symbol, 日期)，
  **沒有 scenario 欄位**——資料模型上就不可能因 target/scenario 不同而
  分家。刪 scenario 不清快取
- **#130** ✅ progressive backfill ＋ quota 感知端點（`7153c06`）。已有
  日期不重抓、每 symbol 每天只跑一批、每批上限 25 天（約三天補齊）。
  `QuotaExhausted` 繼承 `FetchError`（既有降級鏈行為不變，但在乎的
  呼叫端分得出「今天別再試」與「這次剛好失敗」）。status 不是 ok 就
  **不給 percentile**
- **#131** ✅ 五種狀態的簡短呈現（`dd5754b`）。資料不完整時只出三行以內
  短訊息，不畫 percentile／sparkline
- **#132** ✅ 編輯劇本（`aa106bf`）。沿用建立表單切編輯模式；標的不可改
  的防線在後端請求模型（根本沒有 symbol 欄位）；取消隨時可按；儲存走
  PATCH 同一個 id，不是刪除＋重建；thesis 變了才清舊結果

**測試現況**：Python 1098、前端 469、E2E 60，#118 選取身份回歸 8/8，
全綠（Postgres adapter 以本機 PG16 實跑，非 skip）。

**容器又倒退過一次**：HEAD 掉回 4d3cea3、origin 領先 188 個 commit，
依指示以 origin 為唯一真相 `git reset --hard` 復原後才施工。

### 最新狀態（2026-08-12 第一輪）——Settings／Historical IV

**依需求方 2026-08-12 的 Provider 裁示改票後施工，四張已完成並推上
`claude/implement-tfm9oa`；#111 卡在 credential，見下。**

- **#124** ✅ 設定頁＋預設／自訂＋Provider Token 安全儲存（`a555fde`
  → 重做為 `7841a2c`）。`Data / API` 兩列各自「預設／自訂」，預設值
  Cboe 與「無」。自訂只能挑 `api_app/providers.py` 白名單（目前只有
  Market Data App），後端 pydantic 驗證是防線、前端下拉只是方便。
  UI 文案只寫「目前支援」「需自行申請 API Token」，測試擋「推薦」／
  vendor 比較／未來規劃。**credential 以 provider 為 key**，兩列選
  同一家天然共用同一把，第二列顯示「與 X 共用」而不是再要一次。
  完整 token 永不回前端／log／事件紀錄／fixture，三處各有明文斷言
- **#125** ✅ 測試連線三態＋Market Data 自訂與 fallback（`7baf52c`）。
  狀態其實是四個值：**未設定／尚未驗證／已連線／驗證失敗**——存了
  token 不等於測過。驗證失敗回 200（那是預期內的答案，不是請求失敗）。
  自訂來源接在既有 Cboe→yfinance 降級鏈**前面**，失敗即退回並把該次
  失敗記成一次驗證失敗，設定頁因此自動顯示原因，**不可能靜默退回**
- **#126** ✅ Historical IV 端點與閘門（`ceabea4`）。新增
  `option_chaser/ivhistory.py` 純函式：(tenor, delta) 逐日重錨定、
  不外插（含「tenor 在範圍內但一端 delta 蓋不到」也算出界）、
  percentile 用「小於等於」含等於。閘門判準只寫一次，鎖著時 403 且
  **零 vendor 請求**（注入會 assert 失敗的假體守門）
- **#114** ✅ Historical IV 呈現層（`3c7a01d`）。填進 `ScenarioDetail`
  既有的 `IVPositionSlot` 佔位。Normalized Skew 頭條、兩腿次層
  （階層是結構性的，E2E 比對 computed font-size）；sparkline 缺值
  **斷線不插值**；評價字眼由測試守門

**enrich-only 紅線用結構保證而非巡邏**：`ranking.py`／`filters.py`
根本不 import `ivhistory`（有測試斷言原始碼裡沒有那個字），IV 序列走
自己的端點、不摻進 view dict；另有測試證明解鎖前後候選身份與順序逐一
相同、IV 端點掛掉不影響刷新。

**⚠ #111 仍未完成（唯一未結項）**：需要 (1) 一把 Market Data App
token（需求方免費註冊），(2) 一個打得到 `api.marketdata.app` 的環境
——agent 沙箱對該網域回 CONNECT 403（本輪 curl 複驗）。已備妥
`scripts/probe_marketdata_app.py`（四關：認證／即時全鏈＝#125 adapter
的實際路徑／**歷史整鏈含 delta**／單合約序列對照組），在可連網環境跑
完把 JSON 貼回 issue 即可結案。**Market Data App 的 wire format 因此
尚未經真實回應驗證**——`marketdata.py` 的欄位對應依官方文件撰寫，
解析失敗一律收斂成 `FetchError`，所以寫錯的後果是走備援、不是分析
炸掉。需求方裁示「照文件形狀先全做完」，之後用真實回應校正。

**一次施工事故，記著別再犯**：`claude/implement-tfm9oa` 遠端有 69 個
commit（整段 MVP V3 continuation），本機那份 ref 是舊的，我照 master
重開分支就把它們蓋掉了，#124 因此是在錯的基底上做完的。push 被
non-fast-forward 擋下才發現，改成「還原遠端分支 → merge master →
cherry-pick」重做。**動分支前先 `git fetch` 該分支本身，不要只 fetch
master 就相信本機的 remote-tracking ref。**

**環境補充**：本輪為了真的驗證 Postgres adapter（而不是讓它 skip），
在沙箱起了本機 Postgres 16（`/usr/lib/postgresql/16/bin`）跑契約測試
——`OC_TEST_DATABASE_URL` 一設，memory 與 postgres 兩組都實跑。過程中
它抓到一個 memory-only 測不到的真 bug（merge 後 `postgres.py` 少匯入
`ProviderVerification`）。venv 另補裝了 `psycopg[binary]`。

**測試現況**：Python 1015、前端 451、E2E 55，全綠。

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

### Trash 語意＋利率顯示修正（tracking #86，已完成並 merge）

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

- **TR4**（#92）— 前端：垃圾桶畫面單筆還原／永久刪除＋二次確認。
  `TrashView.tsx` 每列新增「還原」「永久刪除」文字鈕；還原呼叫既有
  `restoreScenario()`、成功後從垃圾桶清單移除，並透過新增的
  `onRestore` 回呼把那一列資料交回 `App.tsx`（`restoreFromTrash()`
  併入 `rows`，去重比照 `create()` 既有函式式更新寫法）——`TrashView`
  自己的清單狀態獨立於 `App` 的 `rows`，不會自動同步。永久刪除必經
  二次確認：`ConfirmDeleteOne` 是全站唯一的真正 modal（`.confirm-
  overlay`／`.confirm-sheet`，`CreateEntry.tsx` 那類低風險操作刻意
  原地展開不用 modal，但永久刪除是破壞性動作，風險等級不同），標題
  明確列出該劇本的 ticker＋target month（例如「永久刪除 TLT ·
  2028-05？」），確認後呼叫既有 `deleteScenario()`；失敗時確認畫面
  留著並顯示原因，不靜靜關掉讓使用者以為刪除生效了。前端＋新增
  11 條 Vitest（`TrashView.test.tsx` 9 條、`App.test.tsx` 還原回主
  清單整合測試 1 條）、＋1 條 Playwright（iPhone：還原一個＋永久刪除
  另一個，含確認畫面內容驗證），全套 323 條 Vitest／28 條 Playwright
  全綠

- **TR5**（#93）— 前端：垃圾桶畫面批次操作。這個畫面本身就是「管理
  垃圾桶」的畫面，不像主清單得先點圖示才進批次選取模式——checkbox
  與單筆「還原」「永久刪除」鈕本來就同時存在（垃圾桶列本來就沒有
  「點下去進詳細頁」這件事，不會互相搶戲），標題列加「全選」／
  「取消全選」文字鈕。批次還原沿用單筆 `restoreScenario()` 序列迴圈，
  每成功一筆立即從清單移除並交回 `onRestore`；批次永久刪除新增
  `ConfirmDeleteBatch`（跟單筆 `ConfirmDeleteOne` 刻意不同措辭：
  「永久刪除 N 個劇本？」＋逐筆 ticker／target month 清單，不是單筆
  句型的複數化），確認後依序呼叫 `deleteScenario()`。兩種批次操作
  皆個別失敗不中斷其餘筆，失敗原因彙整顯示、失敗項目留在清單上可
  重試。`.batch-pill` 拆出 `.danger` 修飾類別（原本預設紅色只服務
  「移入垃圾桶」「永久刪除」，現在「還原已選」要跟「永久刪除已選」
  並排卻是可逆動作，顏色不能混淆——`ScenarioList.tsx`／
  `CompactScenarioList.tsx` 既有的「移入垃圾桶」按鈕補上 `.danger`
  類別維持原本紅色，行為不變）。前端＋新增 8 條 Vitest
  （`TrashView.test.tsx`）、＋1 條 Playwright（iPhone：全選＋批次永久
  刪除，含確認畫面清單與數量驗證），全套 331 條 Vitest／29 條
  Playwright 全綠

**Trash 語意＋利率顯示修正這一輪全數完成**（RC1、TR1–TR6，
tracking #86）。收工前跑過一輪 `/code-review`（Standards＋Spec 兩軸
平行審查，對照 issue #87–93 逐條驗收），修回的項目：
`report.py::_rate_line` docstring 跟實際三態分流兜不起來（離線重放
其實會標 FALLBACK，docstring 誤寫成不會）；`api_app/rate_cache.py`
的 `fetched_fresh` 判準漏看 `curve.stale`（陳舊備援曲線若直接由
`underlying` 回傳，會被誤判成「今天真的新鮮抓到」，讓 `market_day`
提早推進、擋住同一天稍後理應要有的真正重試）；前端 `RateRow` 少了
`rate_explicit` 分支，跟後端三態邏輯對不齊（目前網頁路徑不可達，
純粹補齊一致性）；`App.restoreFromTrash` 沒清空還原回主清單那一列
殘留的 `archived_at`；`TrashView.tsx` 兩處內嵌 `style={{}}` 改回
`styles.css`；補一條 RC1「曲線成功但零合約」的邊界情況直接測試；
桌面版（`desktop.spec.ts`）原本缺 TR6／TR4／TR5 的端到端覆蓋，
批次還原（TR5）原本兩個平台都沒有專屬 e2e，一併補齊。全套最終回歸：
後端 699 條、前端 332 條 Vitest、Playwright 33 條（Desktop＋iPhone）
全綠。

**已開 PR #94、已 merge 回 master**（merge commit `200b1ae`，
2026-08-07，需求方直接指示收尾）。收尾一併清掉的 GitHub 票務積壓：
tracking #86 本身，加上此前兩輪（PR #76「前端重練＋QA 維修輪」涵蓋
#67–75、PR #85「MVP V2 手機版劇本庫」涵蓋 #78–84）早就出貨卻忘記
關閉的 16 張舊票，逐一核對 commit 訊息確認涵蓋後全數關閉。

**待辦**：無——這一輪已全數施工完畢並 merge。下一輪＝IV 歷史判讀
研究輪（見下一小節），需求方已於 2026-08-07 指示「先研究，不施工」。

> 沿用規則：全部票做完才開 PR、merge 回 master，中途不主動開。

### 下一輪研究：歷史 IV 資料源＋IV 相對歷史方法論（2026-08-07，只研究不施工）

需求方 2026-08-07 指示「下一輪先研究，不施工」，範圍 A＋B 兩題，
已完成、產出兩份研究文件（皆在工作分支 `claude/implement-tfm9oa`，
未開票、未施工）：

- **A. Historical Options / IV Data 資料源比較**
  （`docs/research/historical-options-iv-data-sources.md`）：17 個來源
  逐源判定能否按需重建歷史 spread debit（Buy Ask − Sell Bid）＋歷史
  IV。「不自存 chain、資料庫負擔最低」是需求方硬約束，bulk 檔案商
  全數如實比較但標明衝突。**交集候選四家**：ORATS（2007 起、選擇權
  專業血統）、Market Data App（單合約一次呼叫回整段日序列，與
  SpreadHistory 形狀天然對齊；免費層可實測）、Alpha Vantage
  `HISTORICAL_OPTIONS`（與既有備援同一家金鑰可共用；免費層資格
  懸而未決）、EODHD（欄位最齊但只回溯 2023 Q4）。**Yahoo/yfinance
  查證確認沒有歷史選擇權鏈**（僅合約成交 OHLC）；Theta Data 資料面
  最強但 REST 靠本機常駐 Java Terminal、與 Vercel serverless 衝突。
  ⚠ 價格數字全為搜尋索引轉述（沙箱 EGRESS_BLOCKED，實測三域確認），
  文件 §7 列出待原件查證清單與**三步近零成本驗證優先序**（Market
  Data App 免費層實測 → Alpha Vantage 免費金鑰 → ORATS 原件確認），
  需在可連網環境（production 或需求方本機）執行。
- **B. IV relative-history methodology**
  （`docs/research/iv-relative-history-methodology.md`）：七問七答。
  要點——同一 OCC 合約 1Y percentile 不成立（DTE 遞減＋moneyness
  漂移＋LEAPS 上市不滿一年，無主流平台採用）；業界零售端主流是
  **constant-maturity ATM IV 指數**的 Rank／Percentile（VIX／
  IVolatility IVX／IBKR V30／tastytrade IVx／ORATS 六家同款；
  IV Rank 與 IV Percentile 是不同統計量，thinkorswim 欄位名實算
  Rank 是著名命名陷阱）；**不能簡單平均兩腿 IV**——§5 自行推導＋
  引擎數值驗算：水位項權重是 net vega（差、會穿零變號）、skew 項
  權重是平均 vega（不隨對沖縮小），平均會把 skew 曝險整個抹掉，
  且「spread 單一 IV」數學上 ill-defined（debit 對 σ 非單調、一價
  兩解）。**候選方案五案 A–E 供裁示**（推薦排序 A→E→B→C，D 不作
  本題答案）：A＝標的層級 30d constant-maturity IV 指數 1Y
  Rank+Percentile（資料最輕、解釋性最高）；E＝IV/HV 比值（零歷史
  IV 需求、A 冷啟動期的保險）；B＝與劇本天期對齊的長 tenor
  percentile（修 A 的 tenor 錯配，機制與 T12 期限對齊利率同構）；
  C＝兩腿 surface 點 percentile＋skew 差（天花板、資料最重）；
  D＝既有 V9 成本歷史加 percentile（不是 IV 判讀，須守標籤紀律）。
  共同紅線：**任何 IV 環境指標都是標示層，不進排名／過濾／A14.2
  成本口徑**，要影響入選屬口徑變更、需求方另行裁示。

- **B-深化：candidate 層級 IV 相對位置**（2026-08-08，
  `docs/research/candidate-iv-relative-value.md`）：需求方看完 B 後
  追問「不要標的整體 IV，要指定 Buy/Sell legs 的 volatility 結構
  相對歷史位置」，十問十答深挖專業市場做法。取材突破：經
  raw.githubusercontent.com 鏡像取得**三份一手 PDF 逐字檢視**
  （Zou & Derman《Strike-Adjusted Spread》GS 1999 全文、Natenberg
  1994 第 10/18 章、Gatheral 2006 SVI 節），其餘外部域仍
  EGRESS_BLOCKED。要點——desk 語言是三層拆解（level／skew slope／
  surface residual），沒有人給 spread 單一 IV；**固定合約 Sell−Buy
  raw IV gap 的 1Y percentile 不成立**（skew 斜率 ~1/√T 的
  roll-down 等四混淆；引擎外推：DTE 882→252 天 gap 6.0→11.2 pts
  零環境變化）；normalize 成熟工具箱＝÷ATM vol（Mixon 2011）＋
  delta 座標（FX RR 可搬處）＋√t 加權（Natenberg 一手）；漂移解法
  ＝每天在 surface 固定 (tenor, delta) 座標重錨定取值，vendor 現成
  序列＝零自訂 bucket，**誠實缺口：LEAPS 882 DTE 超出 ORATS 365d／
  OptionMetrics 730d 網格**（三條處理路線並列）。**四方案供裁示**：
  一＝兩腿 (tenor,delta) 座標各自 1Y percentile【A 成熟】；二＝
  candidate 錨定 normalized skew `Ĝ=(σ(Δs)−σ(Δb))/σ_ATM` 序列
  percentile【B 延伸，對原始問題最直接的單一數字回答】；三＝固定
  合約 raw gap 走勢圖（自家快照零成本；percentile 不做核心）【圖
  B／percentile 化 C】；四＝橫斷面 surface 殘差（Cboe `theo` 零成本
  起點）【A，但與歷史位置正交、card 上須分區】。C 類不建議：
  vega-weighted spread IV、任何單一「Spread IV」、debit percentile
  當 IV、RNHD/SAS 全套自建、CBOE SKEW 式全 smile 指標。Long Call
  （level 語言、單點 percentile）與 Spread（skew 語言、gap）分屬
  兩種 definition、同一 card 兩模式——有 FX 市場三維分報的專業對應。
  ⚠ 側發現：引擎 q=0（無配息）在 TLT LEAPS 上 BS 明顯高估（實算
  7.68 vs 市場 3.95）——不影響方案一~三，但**堵死用現有引擎自建
  方案四殘差的捷徑**，文中已標警告。

- **Wayfinder 地圖：「這組 Spread 現在貴不貴」**（2026-08-08，
  需求方 `/wayfinder` 指示，地圖＝issue #95、子票 #96–#101）：
  把問題從「IV 相對位置」升級為「貴不貴」的完整判讀路徑地圖——
  九條路徑按參照系拆解（相對自身歷史／vol 環境／skew 歷史／鄰近
  履約價橫斷面／同 payoff 等價品／候選池／隱含機率／自建預測／
  price 空間結構價），逐條標「真正回答什麼、先例等級、去向」，
  拆解表在 #95 本文。收斂出四張研究票**全數完成並關閉**，四份
  新文件（皆已 commit 上工作分支）：
  - **R1 [#96] 隱含機率讀數**（`spread-implied-probability-readout.md`）
    ——可行且值得：`D/W = DF × 帶狀平均生存機率`（模型無關恆等式，
    引擎驗證吻合）；零額外資料十行算術；先例成熟（desk digital
    掛帳／BL／BoE·Fed implied PDF／FedWatch·Kalshi ¢ 慣例）；
    陷阱＝必除 DF、寬帶不可標點機率、N(d2) 在 q=0 下不可用、
    嚴禁標「勝率」
  - **R2 [#97] Surface residual**（`spread-surface-residual-rv.md`）
    ——可行且值得，定位「安靜的保險絲＋挑選品質客觀化」：最低可行
    fit＝per-expiry 加權 OLS 二次式（DFW 1998 先例）、OTM-only、
    ≥6 點；直接 fit Cboe `iv` 繞開 q=0；`theo` 殘差＝零成本 v0
    （與自建二次式相關 +0.94~+0.98）；健康鏈殘差普遍低於 bid-ask
    半寬底噪→輸出永遠並列底噪
  - **R3 [#98] price 空間結構價 percentile**
    （`spread-price-percentile-vs-vol-space.md`）——**負結論**：被
    方案二（vol 空間 Ĝ）dominated；先例只在指數／基金層級（buffer
    ETF cap 史等），per-candidate 無；利率主導長天期結構價（TLT
    LEAPS 利率 2pp→價 +26%）是汙染；資料需求不少於方案二還要含 q
    引擎
  - **R4 [#99] Synthetic parity 檢查**
    （`spread-synthetic-parity-check.md`）——**比價＝雜訊**（YETI
    758 筆實算：88% 配對 gap 埋在自身交易成本內；「call 側貴」是
    美式 box 未貼現定價假象）；唯一值得產品化＝`D_worst > width`
    穩賠健全性紅旗（零成本，引擎 net_worst 已算好）；put credit
    spread 當候選策略不建議本輪做

**下一步**：需求方審閱七份文件（前輪三份＋本輪四份；建議順序：
方法論 → candidate 深化 → R1 → R2 → R4 → R3 → 資料源）→
**G1 [#100] Grilling 裁示「貴」的語意**（產品採哪幾個參照系；
7b edge-vs-預測要不要進產品哲學）→ G2 [#101] 呈現與資料裁示
（若選需歷史序列的路徑才需要三步驗證實測）→ 才進 `/to-spec`／
拆票。**本輪不施工。**

**需求方另保留兩個後續獨立 Grill（本輪明確不涵蓋，勿混入）**：
- C. Long Call 如何與 Spread 正確比較／整合，不強行壓成單一 ROI
- D. 跨劇本比較 workspace 應比較哪些維度、如何排序，以及是否採
  Pareto frontier 而非總分

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

### MVP V3（spec #102，2026-08-09 拆票，第一施工批次已完結）

需求基準：`docs/Mvp-v3.md`＋`docs/Mvp-v3-appendix.txt`；spec 全文與三輪
Review 修訂見 issue #102。14 張子票 #103–#116，需求方 `/implement`
指示本批次固定順序施工 9 張——#103 → #104 → #105 → #112 → #106 →
#107 → #108 → #109 → #110，依序、每票測完即 commit＋push。**本批次
不施工**：#111（`needs-human-validation`，vendor 驗證需可連網環境，
本沙箱多數外部網域 403）、#113（被 #110＋需求方核准擋，人工裁示點）、
#114（被 #103＋#111 擋）、#115（被 #113 擋）、#116（被 #115＋#109 擋）。

**九張全數完成（2026-08-09）**，#110 是研究票、本批次終點——完整結果
見批次總回報（本次對話回覆）。等需求方 review＋#110 correctness 裁示
（是否進 #113），本批次不主動開 PR。

- **#103** [#103] — 劇本詳細頁資訊階層重整＋移除追平價格 UI
  （commit `669d653`）：`ScenarioDetail.tsx` 依決策 A 重排為 摘要 →
  基準候選（新增：名次／B-S履約／策略／到期日／目標報酬，取自舊版
  「劇本主圖」卡片拆出）→ 進場成本（新增：Buy Ask／Sell Bid／Net
  Cost，沿用既有 `expiry.ts::legPrices()`）→〔Historical IV Position
  插槽，`IVPositionSlot` 元件回傳 null，不輸出任何 DOM 節點〕→
  Payoff Heatmap（瘦身後只剩圖本身）→ Price Ladder → Expiry Structure
  → Advanced（候選池／分析報告／Spread 歷史／原始資料，四者相對順序
  不變，沿用既有各自收合狀態）。獨立的「Long Call 追平價格」卡片
  （`Catchup` 元件）整個刪除；前端純函式 `catchupContractLabel`／
  `catchupView` 因此不再被任何 UI 呼叫，屬死碼一併刪除——後端序列化
  欄位與計算函式（`catchup_price`／`_spread_catchup_price`／
  `valuation.catchup_price`）依票上要求原封不動保留，僅供未來
  migration／regression 測試使用。新增區塊順序回歸測試（鎖定 9 張
  卡片依序的 `.section-title` 文字，同時證明 IV 插槽零 DOM 輸出）。
  ⚠ **一項解讀記錄**：決策 A「基準候選」文字列了「策略」，與摘要卡
  既有「策略」列重複——核對 wireframe 骨架後判斷為刻意重複，非疏漏，
  兩處皆保留顯示。AC 檢查清單原文「Candidate Pool...僅調整順序」，
  故候選池維持既有非折疊行為，未如票面 prose 摘要暗示的「Advanced
  全部收合」擴大成把候選池也改成 `<details>`——AC checklist 優先於
  prose 摘要，避免無謂 scope 擴張。
- **#104** [#104] — 報價品質警示重整（決策 F，commit `9c47e8c`）：
  `CandidateView` 新增 `wide_spread_warning`（僅 `is_spread_wide`）；
  既有 `quote_warning`（zero_vol or wide_spread or fr>0.25）計算式與
  `_build_groups` 的 `default_pair` 選取邏輯**逐字未動**，只是
  `store._candidate()` 不再把它寫進 JSON——契約裡只剩顯示旗標。前端
  `ExpiryStructure` 的 ⚠ 徽章改接 `wide_spread_warning`，文案改「Bid/Ask
  過寬」；`filters.quality_flag_counts()` 的「報價非最新（今日無成交）」
  改「今日無成交量」（同一函式同時餵 CandidatePool 與 CLI，golden
  fixture 一併更新）。兩個舊字串加進 `test_redlines.py` BANNED 清單。
  新增引擎測試覆蓋 AC 三案例（volume==0／friction>25% 各自單獨不觸發，
  is_spread_wide 為真才觸發）；`test_grouping.py` 新增以真實 fixture
  （`xyz_v4_six_expiries.json`／`xyz_v4_all_warning.json`）鎖死
  `default_selection` 逐位元不變的回歸測試。
  ⚠ **一項解讀記錄**：`_build_groups`內部的 `_row_badges`／
  `ExpiryGroup.rows[].badges`（v4 舊「到期日分組比較」遺留結構，
  `src/` 全站無任何消費者，已 grep 確認）仍以 `quote_warning` 餵
  `"warning"` 徽章字串、維持原樣未動——AC 逐條列的「Candidate 契約」
  「ExpiryStructure/CandidateRow 徽章」「CandidatePool 文案」皆明確
  指向**現行 React UI**這一份契約，不含這個死碼結構；且動它會直接
  碰觸 `_build_groups`（guardrail 明文「不得改變既有 default candidate
  / ranking semantics」的核心函式），改動風險（`test_grouping.py`
  既有斷言）遠高於效益（沒有任何畫面會顯示它），判斷維持不動。
  **量測結果（不改動門檻參數，AC 要求）**：`xyz_v4_six_expiries.json`
  （11 筆合格池）顯示旗標觸發率 9.1%（1/11，與原複合旗標持平，本樣本
  唯一觸發者恰好就是 wide_spread）；`xyz_v2_snapshot.json`（8 筆合格池）
  觸發率從原複合旗標 37.5%（3/8：wide+zero_vol+高friction 各 1 筆）
  降至 12.5%（1/8）——兩份樣本皆未見「全頁候選全亮」，符合決策 F 的
  sparse 設計目標，無需要求需求方裁示調參的情況。
- **#105** [#105] — Analysis Report 瘦身為四區塊（決策 G，commit
  `6643675`）：`AnalysisReport.tsx` 從七段落（一句話結論、7情境韌性表、
  完成度曲線、風險與代價＋部位敏感度小節、進場執行、方法與假設＋過濾
  統計、免責聲明）改為四個 AC 逐欄列明的固定區塊——Risk / Payoff、
  Position Sensitivity、Execution、Model & Assumptions（折疊）。免責
  聲明維持獨立不折疊，判斷為「不是四區塊之一，不在裁減範圍」，非疏漏
  （AC 移除清單未列它）。底層欄位／CLI／契約樣本完全不動，純 UI
  cleanup；新增 `mid_cost`（Candidate）與 `volume`/`open_interest`
  （Leg）的 TS 型別宣告（後端早就序列化，只是先前沒型別）。
  死碼清理：`reportConclusion`／`maxPayoutRatioText`／`costPctOfSpot`／
  `breakevenDistancePct`／`completionThresholdText`／`SCENARIO_NAMES`
  隨唯一呼叫端一併移除；`test_frontend_contract.py` 守護
  `SCENARIO_NAMES` 前後端同步的測試（守護一個已不存在的 UI）一併移除；
  孤兒 CSS（`.report-conclusion`／`.report-warnings`／
  `.report-methodology-text`／`.report-table tr.worst`）一併清理。
  ⚠ **兩項解讀記錄**：(1) AC 逐區塊的內容清單視為窮舉而非舉例——
  `retention`／`completion_threshold`／`cons`／`guidance_warnings`／
  `days_to_expiry`／`l2`／`l3` 皆不在任何一區塊的明列欄位中，判斷一併
  移除（不是漏看，底層欄位仍在契約裡）；(2) Row 標籤採 AC 原文英文
  （Breakeven／Net Delta／Execution Friction 等）而非另譯中文——與
  Bull Call Spread／Bid-Ask Spread 等既有「標準英文術語」慣例一致，
  Model & Assumptions 內部參數（利率／IV情境／Delta門檻／最低要求
  報酬率）維持既有中文標籤，因 AC 未對這幾項重新指定名稱。
- **#112** [#112] — 無風險利率透明化（決策 H，commit `7846eab`）：
  `CandidateView` 新增 `rate_used`／`rate_tenor_years`，值直接取
  `leg_rate(p, expiry)`（估值管線本來就在用的同一個查表函式）與
  `_resolve_rates` 建 `rate_by_expiry` 同一條年期公式——不是另外重算。
  Model & Assumptions 的利率列從「只講用了某條曲線」拆成四項：Rate
  used（一律讀 `candidate.rate_used`，不是可能沒被用在估值上的
  `params.rate` 常數）、Tenor（前端只格式化不換算）、Source（US
  Treasury／CLI 明示／Fallback 常數，依既有三態旗標判斷字串，非新
  財務計算）、Curve date（陳舊附 STALE、非曲線來源顯示「—」）。三態
  語意沿用既有 `rate_curve_used`／`rate_curve_date`／`rate_curve_
  stale`／`rate_explicit`，未新造狀態機。引擎測試涵蓋六到期日鏈多組
  不同到期日，逐一驗證與查表結果一致。至此 #103–#105、#112 四張
  「無依賴／被 #105 擋」的資訊階層票全數完成，回到主線依序 #106。
- **#106** [#106] — Spread 淨成本走勢圖補刻度與 tooltip（決策 I，commit
  `fcc6005`）：`SpreadHistory.tsx` 手刻 SVG 補 Y 軸（`Net Cost
  ($/share)` 單位＋低/中/高三個刻度，讀既有 `yAxisDomain` 固定範圍
  不變）與 X 軸（日期刻度，新增純函式 `xAxisTicks` 均勻取樣至多 4
  個、恆含首尾）。資料點新增桌面 hover／手機 tap 共用同一套 state 的
  tooltip（日期＋淨成本）。
  ⚠ **開發過程中抓到並修掉一個真 regression**：`onClick` 原本寫成
  切換（`idx === activeIndex ? null : idx`），但 `userEvent.click`／
  真實觸控裝置會先合成一輪 hover 事件再送出 click——切換邏輯在那個
  當下讀到「已經是這個 idx」，立刻切回 null，點了等於沒點。改成
  `onClick` 直接設定（不切換）解決；已用 Vitest 的 `userEvent.click`
  逐一驗證過（不是只看 hover 分開測、掩蓋這個交互作用）。
  Day/Week/Month 切換與缺口不連線兩項既有行為皆有回歸測試覆蓋，未
  加入 zoom／pan（AC 明文排除）。e2e：桌面 hover（`desktop.spec.ts`
  新測試）＋手機 viewport 點按（`smoke.spec.ts` 既有測試擴充）皆綠。
- **#107** [#107] — 原始資料二層收合（決策 J，commit `9eba7e4`）：
  `RawData.tsx` 第一層 `<details>` 展開只留摘要＋下載 CSV 連結；逐筆
  合約表格移進巢狀第二層 `<details>`（「查看逐筆合約資料」），需再
  展開一次才渲染。抓資料時機不變（第一層展開就打 API），CSV 下載與
  逐筆表格內容完全不變。
  ⚠ **測試寫法注意**：巢狀 `<details>` 收合時內容仍在 DOM 裡，只是
  不可見——`toBeInTheDocument()`（存在性）測不出「收合了沒」，第一輪
  用它寫的兩條負向斷言直接紅燈（`getByRole("table")`／contract symbol
  文字都被判定「存在」），改用 `toBeVisible()` 才對。既有
  `ScenarioDetail.test.tsx` 的刷新快取失效案例原本就是用存在性斷言
  （`findByText`／`toBeInTheDocument`），不受收合狀態影響，維持不動
  ——不是漏改，是那組測試本來就問對了問題。
- **#108** [#108] — Desktop 劇本庫卡片瘦身（決策 K，commit `b616750`）：
  `ScenarioList.tsx` 的 `ScenarioCard` 從舊版 `.card`（六列各自一整行、
  16px padding、12px 分隔線）改直接沿用 `CompactScenarioList.tsx` 那組
  `.compact-card`／`.compact-tier1/2/3` CSS class（兩個檔案仍是各自
  獨立元件、互不共用渲染路徑，只共用 class 命名與視覺密度）：tier1
  （Ticker＋目標價／年月＋燈號）、tier2（代表報酬＋策略／履約價，
  全卡最醒目一行）、tier3（到期日／距到期／資料時間合併一行，舊資料／
  已過期標記附後）。七項決策資訊一項不少，只是不再各自佔一整列；
  桌面獨有的 `selected`／`aria-current`（#72 master-detail 高亮）保留，
  新增 `.compact-card.selected` 複製既有 `.card.selected` 視覺（左側
  強調色條＋淡色底），手機版不傳 `selected`，用不到這條規則。
  ⚠ **施工中抓到並順手修掉一個真密度 bug**：桌面左側欄（約 220px）
  比手機版視窗窄很多，`.compact-target`／`.compact-tier3` 原本沒有
  nowrap/ellipsis，文字裝不下時會直接在原地換成兩行、把卡片撐高，
  違背「三層各一行」的密度前提——這是既有 CSS 的缺口，手機版視窗較寬
  一直沒踩到，#108 把同一組 class 搬到桌面窄欄位才第一次顯現，判斷
  屬於落實本票「壓縮過大字級／空白」範圍內的修正，非另開的重構。補上
  後 e2e 實測：固定 800px 高左側欄一次看得到的卡片數從換行時的 4 張
  提升到 6 張（e2e 門檻抓 5，留一張安全餘裕）。`ul` 容器 class 一併從
  `.list` 改 `.compact-list`（gap 12px→4px），`App.tsx`／
  `CompactScenarioList.tsx`／`styles.css`／`smoke.spec.ts`／
  `App.test.tsx` 裡幾處因此變得不準確的既有註解一併修正（原本都寫
  「桌面版不用這組 class」）。Scenario Library 的資料流、排序、選取
  語意、整列可點連結行為、勾選、封存操作皆未變動，只動卡片版式。
- **#109** [#109] — Heatmap 右側價格變動百分比軸（決策 M，commit
  `d6fb58c`）：`matrix.py::price_axis()` 回傳型別加第三個元素
  `move_pct = (price - spot) / spot`，跟 cell 值同一次呼叫、同一個
  spot 算出來（`<現價>` 恆為 0），不是前端另外重算的第二份數字。
  `matrix_grid`／`MatrixView.prices` 型別跟進；`matrix_lines`（CLI 文字
  報告）刻意不印這個新欄位，golden fixtures 不因此漂移；`store.py` 的
  序列化本來就通用處理任意長度 tuple，未動。前端 `heatmap.ts` 新增
  `formatMovePct`（完整格式，如 "+13.6%"）／`formatMovePctShort`（AC
  明文允許的手機短格式，如 "+14%"），`Heatmap.tsx` 在既有 sticky
  價格欄同一個儲存格裡加這兩個 span（不是獨立欄／獨立座標軸），兩種
  格式都畫進 DOM、用 CSS 依既有 1100px 桌面斷點切換顯示（不得整段
  省略、不得靠 tooltip／長按才看得到——AC 明文）。主 Heatmap 與到期日
  結構展開候選的 Heatmap 是同一個元件，不需另外接線。
  ⚠ **施工中發現並修正一個既有 e2e 斷言的脆弱點**：契約樣本 target
  剛好在 spot 之上 30%，Heatmap「目標」列的 +30.0% 跟摘要卡「所需
  漲幅」的 +30.0% 撞了同一段文字，`page.getByText(/\+30\.0%/)` 從此
  不再唯一（每張 Heatmap 的目標列都是同一個數字）——改用 `.row-note`
  scope 回摘要那一句，不影響其口徑或既有斷言意圖，純粹是本票新增
  文字後既有選擇器不夠精確的必然後果。
- **#110** [#110] — Valuation correctness：LEAPS carry 方法比較與驗收
  測試（決策 D1，研究票，commit `866c708`）：本批次終點，只做研究、
  不修改引擎／golden fixtures／契約樣本、不鎖定方法。核心量化（真實
  資料，`tests/test_research_valuation_carry.py` 全部可重跑）：現行
  q=0 基準對真實 2026-07-17 TLT 2028-12-15 LEAPS call（取自本 repo
  既有 `tlt_report.md`）5 檔中 3 檔在數學上不可行（市場中價低於 q=0
  模型 sigma→0 下限），且排除「利率抓錯」對立假說後結論穩健（臨界
  利率 1.6–3.2% vs 同期真實利率 ~4%）；引用既有研究
  （`spread-synthetic-parity-check.md` 真實 758 筆 Cboe 全鏈實算）證明
  vanilla put-call parity 萃取股利會被美式提前履約溢價汙染、LEAPS
  尤重，AC 明文警告的風險已用真實資料坐實、不建議採用；新提出並量化
  一個零新增資料依賴、只用同側 call（天然避開上述汙染源）的跨履約價
  IV 一致性校準法，經驗最佳擬合 q≈4.5% 時 5 檔全部可解且離散度明顯
  收斂；獨立覆核（自製半年配息 bootstrap＋真實 2026-08-04 Treasury
  曲線）確認 `risk-free-rate-for-bs.md` 既有的 par→continuous 近似
  結論（1M–3Y 差距 <1bp）仍然成立，2Y 節點兩份分析幾乎完全吻合。
  書面建議（需需求方核准，非已執行變更）：方向上採股利殖利率調整 BS
  ＋同快照跨履約價校準，見 `docs/research/
  valuation-carry-method-comparison.md` §7 完整論述與已知殘留侷限。
  範圍確認：`option_chaser/`／golden fixtures／`contracts/` 全部
  git status 乾淨，四個新增檔案（研究文件、純函式模組、真實資料
  fixture、驗收測試）皆為純加法，研究模組不被引擎 import。

### QA-01 人工 QA 修正輪（2026-08-09，CLOSED / ACCEPTED，HEAD `8e57a7b`）

需求方對第一施工批次（#103–#110）做人工 QA，回報 6 項；偵查後 5 項
成立、1 項結案。修正 5 張、每張各自 commit＋push：

- **QA-FIX-1**（commit `b87080f`）— Heatmap ±% 從左側價格欄移到表格
  最右欄。#109 施工時把 ±% 塞進左側 sticky 價格欄的同一個儲存格，
  與 ticket 名稱「右側…軸」及 AC 不符（AC 那句「不是獨立座標軸／
  獨立 scale」限制的是 scale 語意，不是位置——當時解讀錯誤）。改為
  價格（sticky left）→ 日期格 → ±%（sticky right），`<thead>` 補
  對應欄標題「vs 現價」。測試改用幾何位置（boundingBox）驗欄序，
  加負向斷言「價格欄內不得再出現 ±%」——原本的文字存在性斷言正是
  讓誤置也能通過的那一種
- **QA-FIX-2**（commit `07e297d`）— 淺色模式文字對比。實測
  secondary 3.44:1、tertiary 1.73:1，皆低於 WCAG AA normal text
  的 4.5:1。照 AA 反解最小 alpha（最差底色是頁面底 `--bg` #f2f2f7
  而非卡片白底）：secondary 0.6→0.90、tertiary 0.3→0.75，三階層次
  仍在。`.compact-tier3` 11px→12px。深色模式未動（要求是不退化）。
  新增 `src/contrast.test.ts` 直接讀 styles.css 算對比，把 AA 變成
  可執行守門；其中一條把「深色 tertiary 仍未達 AA」釘成現狀，
  待需求方裁示。⚠ 字級變大讓 compact card 長高、手機一屏從 4 張掉
  到 3 張（踩到 #82 既有驗收），以 `.compact-card-tap` 內距 6→4px
  換回來
- **QA-FIX-3**（commit `8a70d1f`）— 桌面詳細頁密度。實測 2668px ÷
  800px ＝ 3.33 螢幕，純文字列卡片 37–50% 高度是 padding/gap。全部
  規則掛在 `.detail-pane`（桌面專屬 DOM，手機**結構上**拿不到），
  card padding 16→12、gap 12→8、section-title 20→17px、row 間距
  12→8；摘要卡加 `metadata-grid` 改兩欄（只有這一張，不一律兩欄化）。
  結果 2208px ＝ 2.76 螢幕（−17.2%），摘要卡 305→132px。Heatmap
  本體未壓（格子字級仍 13px，有測試釘住）。新增 Mobile 護欄 e2e：
  手機 `.detail-pane` 數量為 0、卡片內距仍 16px
- **QA-FIX-4**（commit `97a8454`）— 批次操作列改桌面與手機共用吸底。
  原本 sticky 只寫在手機斷點裡，桌面全選後批次列在 y=1696px，得再
  捲 971px 才點得到動作鈕。三條 e2e 全部用 boundingBox 對照 viewport
  ——`isVisible()` 對捲到畫面外的元素照樣回 true，正是原本沒抓到的原因
- **QA-FIX-5**（commit `874f4e1`）— GUI Heatmap 日期軸密度參數化。
  舊行為固定七欄與天期無關，2.4 年 LEAPS 平均 143 天／欄。
  `date_axis(..., max_gap_days=None)`：`None` ＝ 既有七欄（CLI 走
  這條，golden 零漂移）；GUI 傳 `GUI_MAX_GAP_DAYS = 31`，實測命中
  裁示目標 7／13／29 欄。密度參數化在引擎，不讓前端自己重新抽樣。
  payload 實測 128KB → 268.6KB、latency 26→38ms（偵查時擔心的
  ~600KB 是高估：只有 matrix cells 隨欄數成長），依裁示不預先建架構。
  決策已補記於 issue #109 留言。⚠ 測試發現既有邊界：天期 < 6 天時
  無法有 7 個相異日曆日，不變量寫成 `>= min(7, span+1)`

**QA-01 第 6 項（Rate 4.1%）已結案、未施工**：4.1% 是 Treasury 曲線
在 ~1.4–1.9 年期的正常插值輸出；固定 fallback 是 0.04＝畫面顯示
「4.0%」，數學上不可能顯示 4.1%；三態（US Treasury／STALE／Fallback）
在 UI 與 API 都可辨識；兩條陳舊分支都會標 `stale=True` 且經
`curve_to_dict`／`curve_from_dict` 往返無損，查無「抓取失敗但看起來
像正常 Treasury」的路徑。

> 本輪未施工 #111／#113／#114／#115／#116，亦未更動 #110 研究結論。

**正式收尾（2026-08-09）**：第一施工批次（#103–#110、#112 共 9 張）＋
QA-01 修正輪（QA-FIX-1–5）標記 **CLOSED / ACCEPTED**，對應 9 張 GitHub
issue 已關閉（`state_reason=completed`），驗收基準 HEAD `8e57a7b`
（branch `claude/implement-tfm9oa`，已 push、working tree clean）。

**唯一殘留**：Dark Mode 下 `--label-tertiary` 對比仍低於 WCAG AA
（QA-FIX-2 施工中發現，`src/contrast.test.ts` 已留存機器可驗證的
已知狀態斷言）。列為**低優先 UX debt，不阻擋本輪驗收**，留待下一階段
前端工作視情況處理。

> 下一階段（#111／#113／#114／#115／#116、Crossover、IV History、
> Valuation D2 model 鎖定）尚未開工，等待需求方後續指示。

### MVP V3 Continuation（spec #117，2026-08-09 起，第二波施工）

QA-01 收尾後緊接開始的下一波，承接 #102 尚未完成的部分（#111／#113／
#114／#115／#116）加兩項新增工作（q 資料管線、Heatmap compact 小修）。
**#103–#110、#112、QA-01 已 ACCEPTED 的第一施工批次不重開**。

**研究（不施工，只留文件）**：

- `docs/research/heatmap-valuation-method-selection.md`（commit
  `91e8fb9`）——Heatmap／Crossover 該用哪個估值方法。真實資料證實
  現行 q=0 歐式＋vendor IV 在「今天×現價」那格印出 +81.9%／+81.4%，
  誠實答案是 −11.5%／−4.2%；根因是模型不一致（vendor IV 是美式含
  股利模型反解的，卻代進歐式無股利公式）。四方法比較（對 CRR 美式樹
  基準）：現行格差中位 4.79–14.28pp；Bjerksund–Stensland 1993＋q
  僅 0.18–0.33pp、Crossover 判錯 0.0%，且每格 6.0µs（CRR300 要
  15.4ms，60 秒 serverless 上限下不可行）。**建議＝BS93 美式近似＋
  同快照同模型逐腿反解 IV 價格錨定**，需需求方核准。另標出副作用：
  單腿 delta 分級會位移（TLT 五檔三檔 conservative→balanced），
  Spread 排名／best_return／V9 成本走勢圖不受影響。
- `docs/research/dividend-yield-source-selection.md`（commit
  `e7df64a`）——q 從哪裡拿、怎麼算。用 TLT 真實 fixture 量化：外部
  配息資料算的 q 與市場自身隱含 carry 只差 0.024–0.078pp（Heatmap
  格差 0.15–0.48pp），對照門檻（1.5pp⇒9.26pp）達標一到兩個數量級。
  真正要付代價的只有三個決定：現金分配 vs 30 天 SEC 殖利率
  （3.59pp）、除以自己的 spot vs 抄 vendor 百分比（0.87pp）、複利
  慣例（1.01pp）。**推薦 primary＝Yahoo chart `events.dividends`**
  （見下方 #120 已實測確認）；不建配息時間表（次數數錯比相位貴
  20 倍）。快取沿用 ratecurve／rate_cache 既有 pattern，三處刻意
  偏離：per-symbol 鍵、90 天陳舊窗（非利率的 7 天）、快取金額而非
  算好的 q。
- `docs/spec/`（未落檔案，commits `399d677`／`12bb5b8`）——MVP V3
  Remaining Work / Continuation Spec：鎖定 BS93＋同模型 IV 反解、
  q 取外部配息資料（Method E 僅 diagnostic）、Crossover 2D overlay、
  不恢復舊 1D 追平價格 UI。**核心紅線（需求方更正版）**：本輪任何
  工作都不得改變既有 Spread 的 ranking／filtering／candidate
  selection／expiry_best／expiry_top10／representative candidate／
  best_return；新模型 delta 僅供估值與顯示，不得進入 legacy 分級
  路徑；Crossover 的 comparator 就是買腿本身，禁止候選搜尋；
  Historical IV 只 enrich、不得參與 ranking 或 selection。

**已完成（依序）**：

- **#118**（commit `2425ea6`）— Spread 選取身份回歸守門：施工前先把
  現行 ranking identity／各到期日順序／expiry_best／expiry_top10／
  representative candidate／best_return semantics 凍結成固定
  fixture 的離線測試，供後續每張票完成後直接呼叫比對。刻意只釘身份
  與順序、不釘數值（Heatmap cells／Greeks／baseline_return 允許在
  估值修正後改變）。不改動任何 production 行為。
- **#119**（commit `ccba9c7`）— BS93 定價原語＋同模型 IV 反解（純
  函式，未接引擎）：`american_price()`／`merton_price()`／
  `implied_vol()`，逐字依 QuantLib 一手原始碼移植。q<=0 時對 call
  逐位元退化成 Merton 歐式。實作中抓到並修正一個真正確性 bug
  （QuantLib「取歐式與較大值」的收尾漏放在條件外層，深度價內＋高波動
  組合下美式價格一度低於歐式，違反美式恆≥歐式的基本不變量；修正後
  4 萬組隨機參數掃描零違反）。未接進任何呼叫路徑，production 行為
  零變化。
- **#121**（commit `6a6060e`）— Heatmap compact：cell 去 `+`／`%`
  純數字化、水平 padding 8px→5px。右側「vs 現價」欄與日期軸密度不動
  （QA-FIX-1／#109 既有驗收範圍）。Playwright 實測固定容器寬度下
  平均欄寬 60.92px→45.65px、可見欄數 14→19，新增 e2e 永久回歸斷言。
  零金融計算、零契約變更。
- **#122**（commit `028d249`）— 分級 delta 接縫：`ContractValuation`
  新增 `classification_delta`，legacy 單腿分級改讀這一欄而非 `delta`
  ——#113 換估值模型時只會改 `delta`，`classification_delta` 保持
  原口徑，legacy 分級因此不會被新模型污染（spec #117 核心紅線的落地
  機制）。目前兩欄同值（q=0 歐式解析式，未換模型），純結構性 prefactor。
- **#113**（commit `17dc6ca`）— 引擎接線：Spread／單腿估值改走 BS93＋
  同模型 IV 反解（#119 原語），q 由 `AnalysisParams.q_by_symbol` 注入
  （`None`＝今天，#123 之前恆為此狀態）。每腿一次 `calibrate_leg()`，
  掛在 `carry`／`long_carry`+`short_carry` 上供 Heatmap／七情境／保本
  掃描／CLI 報告全部共用。Fallback：`q_by_symbol=None` 或反解失敗，
  一律收斂成 `(q=0.0, sigma=vendor_iv, carry_calibrated=False)`——
  今天的完整行為，不是「q=0＋價格錨定」（那條路對多數真實 LEAPS call
  數學上無解）。端到端用真實 TLT LEAPS fixture 驗證：q=0→0.045 讓
  K=85 顯示 delta 從 0.73 真的移到 0.46，但 `classification_delta`
  逐位元不變、候選身份與順序不變（#118 守門通過）；Spread 排名端到端
  維持模型無關（T3／#17，`scenario_leg_value` 的到期內在價值分支在
  讀 carry 前就回傳）。契約樣本純加法重產（`q_by_symbol`／
  `carry_calibrated`），CLI golden fixture 零漂移。
- **#120**（issue 已於本輪 close）— Yahoo 配息端點 production 探測：
  沙箱探測腳本先備妥（commit `af27f52`），本輪改用 GitHub Actions
  `ubuntu-latest` runner（真實網路出口，理由見下方「探測環境選擇」）
  取得**真實**結果：TLT 匿名 `GET .../v8/finance/chart/TLT?...` →
  HTTP 200，`events.dividends` 24 筆歷史配息、過去 365 天 12 筆，
  與 Nasdaq 獨立來源交叉印證誤差僅 1.6%；`events.splits` 窗內不存在
  （TLT 近 2 年無分割，預期結果）。**Yahoo chart events 正式從
  「建議」升級為「實測確認」的 primary source**（研究文件
  `dividend-yield-source-selection.md` §12.4／§13-1 同步更新，
  commits `f392014`／`6211085`／`55d80a3`）。issue 已附真實結果留言
  並 close。
- **#111**（credential-blocked，issue 維持 OPEN）— IV History vendor
  三步驗證：同一真實環境實測。① Market Data App／③ ORATS 的認證機制
  要求金鑰才能組出可呼叫的 URL，無金鑰下連請求都送不出去；② Alpha
  Vantage 用官方公開 demo 金鑰測得 HTTP 200，但回應是「請註冊真實
  金鑰」而非 `HISTORICAL_OPTIONS` 真實資料。**三家皆 credential-
  blocked，無一達成 AC「至少一次成功的真實資料呼叫」**，不得宣稱
  vendor 已確認（研究文件 `historical-options-iv-data-sources.md`
  §5.1 同步更新）。issue 已附真實結果留言，**維持 OPEN**、待需求方
  決定是否申請免費金鑰（建議優先 Alpha Vantage，號稱 20 秒申請、
  已確認端點真實可達）。**#114（Historical IV Position 模組）依既有
  blocked-by 持續卡在本票之後，本輪未動工**。
- **#123**（commits `4043106`／`a022628`）— q 管線：抓取（Yahoo→FMP
  →Nasdaq 備援鏈，純 stdlib，單一 `FetchError`）／per-symbol 快取
  （`Storage` protocol 新增 `DividendCacheEntry`，memory／postgres
  兩後端皆補齊，90 天陳舊窗）／三態揭露（`AnalysisParams` 新增
  `q_source`／`q_as_of`／`q_stale`／`q_note`，比照既有
  `rate_curve_used` 三態）／接進引擎（`service._resolve_q` 鏡射
  `_resolve_rates` 四層 fallback，接上 #113 早已就緒的消費端）。
  前端補上 `QRow`（`src/AnalysisReport.tsx`，鏡射既有 `RateRow`）與
  `src/api.ts` 型別。純函式解析（`parse_yahoo_dividends` 等）歸位到
  `option_chaser/dividends.py`，比照 `ratecurve.parse_treasury_csv`
  既有分工（純模組自己的例外型別 `DividendParseError`，不依賴 I/O
  層的 `FetchError`）。`/api/health` 刻意不比照加 `dividend` 區塊
  （per-symbol 資料沒有「那一筆」可讀，程式碼註記說明）。全套測試
  綠燈：後端 867 passed（memory＋真實 Postgres 兩後端）、前端 360
  passed、typecheck／build 皆過。**#118 選取身份回歸守門全程綠燈**。

- **#115**（commit `19b7d5d`）— Crossover comparator 矩陣計算：
  `service._spread_comparator()` 直接取 `sv.long_leg`（Spread 買腿本身
  既有報價）——無型別轉換、無查找，`test_comparator_construction_
  never_calls_find_contract`／`..._never_calls_legacy_ranking_or_
  classification` 兩條測試明確證明這條路徑不做任何選擇。Comparator
  matrix 重用既有 `_matrix_view()`（同一組 price×date grid，`sv.
  long_carry` 沿用 #123 校正過的 q pipeline）。買腿報價缺失時誠實回傳
  `None`，不假造。契約樣本新增獨立第二例
  `contracts/analysis_sample_bear_put.json`（bear put spread，配新
  fixture `xyz_v5_put_ladder.json`）與 bull call 既有例並存，call／put
  comparator 兩種都有 drift 測試覆蓋。純資料層，未觸碰任何前端渲染。
- **#116**（commit `f47eff4`）— Crossover Boundary Heatmap overlay：
  `heatmap.ts` 新增 `crossoverEdges()`／`crossoverFavoredSide()`——
  逐格掃兩軸找 Spread 與 comparator 報酬符號翻轉，純幾何比較、零財務
  計算。`Heatmap.tsx` 三態區分 comparator 是否傳入／`null`／有值
  （對應「概念不存在」／「報價缺失」／「正常顯示」），CSS `box-shadow:
  inset` 疊色不新增第二張表、不蓋掉既有格值。`ScenarioDetail.tsx`／
  `ExpiryStructure.tsx` 兩處呼叫點（主圖＋展開候選）皆接上。桌面＋
  手機 e2e 各一條新測試驗證圖例／邊界格可見且不破壞既有橫向捲動／
  ±% 欄行為。兩票皆通過 #118 選取身份回歸守門，皆已在 GitHub 關閉
  （commit 引用留言）。

**探測環境選擇（#120／#111 共同記錄）**：使用者原始指示要求建臨時
Vercel probe，但本輪 Vercel MCP 的 `deploy_to_vercel` 可成功部署，
該 session 內所有讀回工具（`get_deployment`／`list_projects`／
`web_fetch_vercel_url`／`get_runtime_logs` 等，7+ 次不同嘗試、兩個
獨立專案）全數 404/403——與沙箱網路政策無關，是另一個獨立的 MCP
工具整合缺陷。改用本 repo 既有的 `tmp-*.yml` 一次性工作流慣例（6 個
既有前例）：推臨時 workflow 到 `master`（`tmp-vendor-probe.yml`，
`ubuntu-latest` runner 真實網路出口），跑完即刪。**兩個孤兒 Vercel
專案**（`option-chaser-vendor-probe`／`option-chaser-vendor-probe-2`）
**MCP 工具無刪除操作，需求方需自行從 Vercel 後台手動清除**。

**尚存 blocker**：#111（IV History vendor，credential-blocked，
需需求方申請免費金鑰，issue 維持 OPEN）、#114（Historical IV Position
模組，依既有 blocked-by 卡在 #111 之後，未動工）。**Crossover 主線
（#115→#116）已於 #123 解鎖後完結並關閉**——本輪剩下的唯一實質
blocker 就是 #111 的 credential。#113／#115／#116／#118–#123 依既有
規則**中途不主動開 PR**，累積到 IV 線也解決或需求方指示時再開。

**#111 免 credential 候選第二輪窮舉（2026-08-11）**：需求方指示先窮盡
不需申請金鑰的路線再考慮付費三家。Yahoo／Nasdaq／Cboe 三家皆用
GitHub Actions runner 真實請求測過（
`docs/research/historical-options-iv-data-sources.md` §5.2，探測腳本
`scripts/probe_iv_history_free_vendors.py`），結論**三家皆不能**：
Nasdaq 當下鏈免鑰可達但歷史日期參數被明確拒絕、Cboe 現行端點對
`date`／`asof`／`historical` 全部忽略只回當下快照、Yahoo 當下鏈端點
新增 crumb+cookie 驗證且既有研究已確認其 chart 端點結構上無 bid/ask/
IV。免 key 路線已窮盡，**blocker 未解除**，仍需需求方申請
Alpha Vantage／Market Data App／ORATS 任一家金鑰。

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
  - `option-chaser-rate-probe`（#74 探測用的獨立臨時 Vercel 專案，跟
    正式 `option-chaser` 專案分開）**需求方已於 2026-08-07 手動刪除**
- 全套測試現為全綠（後端 667 條、前端 288 條 Vitest、Desktop＋iPhone
  共 22 條 Playwright；舊紀錄提到的 5 個 streamlit 版本漂移失敗已隨
  T2 改寫消失）。MVP-v2（M1a–M6）起的最新數字。
