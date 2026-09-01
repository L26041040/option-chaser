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

> 目前次序：053（下一份回報用 054）

每發一份回報就把上面這個數字改成剛剛用掉的那個，跟著那次改動一起
commit（沒有其他改動要 commit 時，單獨為這一行開一個小 commit 也
可以）。新開的 session 找不到對話記憶時，编號一律以這裡記的數字為準，
不要自己另起爐灶。

只有這七條。

## 專案紀錄區

> **現況總覽（2026-08-26，寫給接手的新 session 看，取代下面所有更舊的
> 「現況總覽」／「目前狀態」標頭——那些是歷史留存，內文本身依然正確，
> 但「現在該做什麼」一律以這段為準）**：
>
> **master 現況**：截至今天，本檔案記錄過的每一輪工作——T1–T12、QA1
> 系列、D1、FB3、FB5、V1–V10、QA-v2、MVP V2 手機版劇本庫、Trash 語意
> 修正、過濾器修正輪、MVP V3（spec #102 主線＋spec #117 Continuation）、
> Historical IV Trend／Reconstruction／資訊架構重整（spec #151／#159／
> #171）、Application Diagnostics（spec #143）、Performance 修正輪
> （spec #176）、Architecture Review 輪（spec #184）、V1 Product
> Correctness + Historical IV UX Cleanup（spec #198）、以及 2026-08-26
> 真機驗收直接施工的兩項修正（Refresh Run 逐張解鎖＋percentile 白話
> 文案）——**全部已 merge 回 master**（PR #207，merge commit
> `459fb4f`，需求方 2026-08-26 核准後 merge）。工作分支
> `claude/implement-tfm9oa` 與 master 目前同步；production 網址
> `option-chaser.vercel.app` 對應 master，下次部署會拿到這裡列的
> 全部成果。
>
> **GitHub issue 現況**：藉這次 merge 順手清點，補關了一批早就做完
> 但忘記關閉的舊票（spec #124–143、#151、#159、#171、#176 各自的
> parent／子票，共 25 張；#136 是被 Refresh Run 架構取代的舊票，
> 標 `not_planned`）。**目前只剩 4 張 open**：
> - **#111**（`needs-human-validation`）——IV 歷史 vendor 三步驗證，
>   credential-blocked，需要需求方申請一組 Market Data App／Alpha
>   Vantage／ORATS 任一家的免費金鑰後才能繼續（免 key 路線已窮盡，
>   見「MVP V3 Continuation」小節內的查證紀錄）
> - **#114**（`ready-for-agent`，但被 #111 擋）——Historical IV
>   Position 模組，等 #111 解除才動工（⚠ 需注意：Historical IV Trend
>   後來以 spec #151／#159／#171 另外一條路線做出來並已上線，#114
>   當初設想的模組是否還有必要、或該視為被取代，下次要動這張票前
>   建議先跟需求方確認範圍是否仍然成立，不要照舊字面直接施工）
> - **#102**（`ready-for-agent`）——MVP V3 spec 母票，因為 #111／#114
>   兩張子票未解而維持 open，其餘全部子票已完成
> - **#59**（未標 `ready-for-agent`）——多使用者隔離，需求方尚未裁示
>   要不要開工，`/implement` 不會取到
>
> **下一步**：等需求方指示新一輪方向。若要繼續 MVP V3 剩餘範圍，
> 起點是 #111 的免費金鑰申請（不受 agent 沙箱環境限制，需人工執行）；
> 若是全新方向，比照慣例先 `/qa` 或 `/research` 或直接發 spec。
> 環境操作細節（venv／本地 Postgres／**容器倒退修法**／部署網址）見
> 檔案最底下「## 環境」一節；**本 session 兩度遇到容器倒退**（HEAD
> 憑空跳回舊 commit、工作目錄留下與任何單一 commit 都對不上的雜訊
> 檔案），皆用 `git stash push -u` 存證後 `git fetch`＋
> `git reset --hard origin/<branch>` 安全復原，過程詳見「## 環境」
> 一節的既有說明，這是已知、有標準流程的環境限制，不是新狀況。

> **以下「現況總覽（2026-08-07）」原文照舊保留，與更舊的各段落標頭
> 一樣皆為歷史留存**：

> 現況總覽（2026-08-07，寫給接手的新 session 看）：T1–T12、QA1
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

### Architecture Review 輪（2026-08-24，`/improve-codebase-architecture`，回報#025）

需求方授權完全自主跑 skill 原生流程（自選 candidate、自選優先序、
可裁定既有 PERF-01~06 保留／修改／回退；紅線＝不得刪使用者功能、
不得開新功能）。四路 Explore（API 請求生命週期／engine 模組深度／
前端請求模式／PERF 輪 vs serverless forensics）已完成，HTML 報告
已交付需求方（tmp 檔，依 skill 裁示不進 repo）。

**核心診斷**：「局部 benchmark 變快、production 體感變慢」兩者同時
為真——慢在執行結構不在單一 endpoint。(1) 前端一輪刷新＝N 個串行
serverless invocation（`App.tsx:187` 逐一 await），每次各付 Neon TLS
握手＋vendor 抓取＋兩份大 JSONB 寫入；(2) 四個「cache」全是 Neon 表，
命中＝數百 KB JSONB 網路 SELECT＋dataclass 重建，PERF 輪 benchmark
只數「省掉的 upstream 抓取」從未計入「新增的 Neon 往返」；(3) 詳細頁
deep-link 有 refetch cascade（3 次 ~100KB 全量下載＋2 次 iv-history）；
(4) `api_app/main.py` 2,121 行中約 1,000 行是 domain 邏輯（IV 編排
680 行只能靠 2,970 行的 `test_api_iv_history.py` 從 HTTP 測）。

**六個 candidates**（詳見 HTML 報告；C1 為自選 top）：
- **C1 Refresh Run（Strong，top）**：一輪刷新收進一個深模組——單一
  interface 收整批劇本，一次 invocation 內按 symbol 去重抓 chain
  （純 in-process dict）、逐劇本分析、批次寫回；`chain_cache` 模組
  ＋資料表＋15s TTL 整個刪除（deletion test 通過：複雜度集中進 run
  module）；前端佇列塌縮成一個請求。
- **C2 IV History Pipeline（Strong）**：`main.py:1279–1959` 下沉為
  engine 深模組（ports：vendor history／surface／storage／clock），
  HTTP handler 縮回 glue；補 iv-history contract fixture（全站最大
  payload、目前唯一沒有 fixture）。
- **C3 View 契約瘦身（Worth exploring）**：4 candidates → 15 份序列化
  收斂為一處＋key 引用；`report_text`／`methodology_text`（前端不
  渲染）移出 view；schema_version 升版＋樣本重產。
- **C4 前端取數紀律（Strong）**：以 `(id, analyzed_at)` 為 key 的
  fetch module，消滅 cascade／settings 重抓／無 AbortController。
- **C5 死重清除（Strong）**：`workspace.py`（348/354 行 prod 不可達，
  僅 2 個 clock helper 存活）、`store.py` 檔案系統半邊（~350 行零
  caller）、`data/base.py` 零實作 Protocol、data 層 on-disk cache
  死碼、`main.py:2121` 冷啟建第二個 app——deletion test 全過。
- **C6 Storage lifecycle 對 serverless 誠實（Worth exploring，隨
  C1/C2 施工）**：PERF-01 共用連線語意保留但改 lazy、合併兩層
  BaseHTTPMiddleware、schema DDL 移出請求路徑、PERF-05 pool 提出
  迴圈；memory adapter 補 `request_scope` 讓測試走到 production 路徑。

**舊決策裁定**：保留 PERF-02（serverless-correct）、PERF-03（方向
正確，註明命中非免費）、PERF-04（純 CPU）、Neon pooled DSN 優先序、
「刷新只有三個觸發時機」產品規則（C1 只改執行結構不改觸發語意）。
推翻／修形：PERF-06 chain_cache（miss 純加成本、hit 無證據比 Cboe
CDN 便宜、15s TTL 被串行佇列擊敗——由 C1 取代後刪除）、PERF-01 形狀
（eager connect＋第二層 middleware → lazy＋合併）、PERF-05 形狀
（每天新建 ThreadPoolExecutor ×25 → 提出迴圈；50ms sleep mock 的
3.9x 在 fractional vCPU＋GIL 下存疑）、前端串行單劇本刷新設計（由
C1 批次取代）。

**下一步（skill 原生流程）**：needs 需求方——對 C1 進 grilling loop
（60s 上限的分批策略、進度回饋形狀、`refresh-run` interface 細節），
grilling 中依裁決 lazily 建立 `CONTEXT.md`／ADR，再 `/to-spec`／
拆票施工。C5 無爭議可隨時先行。

**Grilling 結果（2026-08-24，回報#026）**——需求方授權：工程選擇
直接拍板、產品決策彙整一次提問。

已拍板（工程，E1–E8）：
- **E1** Refresh Run interface：`POST /api/refresh-run`（body 可選
  scenario ids，預設全部未過期），一次 invocation 內 symbol 去重
  （in-process dict）→ 逐劇本 `run_with_snapshot` → 批次寫回；回應
  含 server 端時間預算的 continuation——逾時回傳「已完成 rows＋
  remaining ids」，前端自動再呼叫直到清空（單次請求為常態，分段是
  安全閥）。實測支持：引擎 CPU 7ms/劇本（11-contract fixture）、
  瓶頸在網路，realistic 一輪 <15s。
- **E2** `chain_cache` 模組＋資料表＋15s TTL 刪除（被 E1 取代）。
- **E3** PERF-01 修形：連線 lazy（首次用到才開）、兩層
  BaseHTTPMiddleware 合併為一、schema DDL 移出請求路徑；memory
  adapter 補 `request_scope` 讓 1,504 條測試走到 production 路徑。
- **E4** PERF-05 修形：ThreadPoolExecutor 提出迴圈建一次；
  concurrency=4 維持，留待 production 量測。
- **E5** C2 下沉：`main.py:1279–1959` → engine 深模組（ports：
  vendor history／surface／storage／clock）；補 iv-history contract
  fixture。
- **E6** C3 瘦身：candidates 單一容器＋key 引用；`report_text`／
  `methodology_text` 移出 view payload（src/ 零引用已驗證；CLI 照
  舊自 render）；schema_version 升版＋樣本重產＋TS types 同步。
  舊已存 view 不遷移（讀取端相容）。
- **E7** C4 前端：fetch module 以 `(id, analyzed_at)` 為 cache key
  ＋in-flight 去重＋settings 共享＋AbortController；不引外部套件。
- **E8** C5 死重清除全部執行（workspace.py／store.py 檔案系統半邊
  ／data/base.py／data 層 on-disk cache 死碼／main.py:2121 第二個
  app／殘骸檔案），對應舊測試依 replace-don't-layer 一併刪。

**產品決策已裁示（2026-08-24，需求方回覆回報#026）**：
- **P1-b** 刷新進行中，卡片顯示上一輪舊資料＋「更新中」徽章，
  全程可瀏覽、可進詳細頁，結果回來逐批換新（取代整段灰化鎖定）。
- **P2-a** 部分成功：成功劇本照常落地，失敗劇本保留舊資料＋亮既有
  失敗燈號＋可單卡重試，頂部顯示「N 成功／M 失敗」。
- **P3-a** IV 冷 backfill 兩段式：先立即回既有歷史畫圖，backfill 由
  第二個請求觸發，完成後自動補全，期間卡片標「歷史資料補建中」。
- **P4-b（改動既有規則）** 建立新劇本時**只刷新該新劇本**；開站與
  使用者主動全量 Refresh 才刷新全部未過期劇本。這修改了 QA1-07
  時期「建立劇本＝全量刷新」的產品規則，三個刷新時機本身不變。

裁示落地：`docs/adr/0001-chain-sharing-within-run-only.md`（chain
共用只在 run 內，不跨 invocation）＋根目錄 `CONTEXT.md`（領域詞彙，
含 Refresh Run／Continuation／Partial Success／Updating Badge／
Two-Phase Backfill 等新詞）。

**Spec 已發佈＝issue #184**（2026-08-24，`ready-for-agent`，回報#027）：
涵蓋 E1–E8＋P1–P4 全部裁定，66 條 user stories。**測試接縫定案**
（4 條，唯一新增是第 3 條）：(1) HTTP API＝既有主接縫（Refresh Run
批次／去重／Continuation／Partial Success／P4 範圍／契約形狀）；
(2) Storage port＝既有，E3 補記憶體 adapter 的 request scope 後，
既有契約測試組首次真正涵蓋 production 連線路徑（補既有覆蓋缺口，
非新接縫）；(3) **IV history pipeline 模組 interface＝唯一新增**，
兩個 adapter（marketdata＋記憶體假體）證成真 seam，2,970 行 HTTP
測試檔的編排斷言**搬過去**而非兩層都留；(4) 前端＝既有
`global.fetch` mock＋Playwright，新增「每畫面請求數上限」斷言防
cascade 回歸。建議施工順序：E8→E3→E1+E2→E7→E6→E5→P3→E4。

**拆票完成（2026-08-24，`/to-tickets`，回報#028）**——依「不求快、
求正確性」裁示，granularity 比原建議更細：Refresh Run 拆三張
（核心／Continuation／前端整合，隔離三個獨立正確性風險）、IV
pipeline 拆兩張（隔離建置／上線切換，先在零風險環境驗完全等價
再做可逐位元驗證的小切換）、View 契約瘦身拆兩張（死欄位移出／
Candidate 去重，避免瑣碎刪除跟結構改動混在同一份 diff）。全數
13 張、依拓撲順序（blocker 先發佈）發佈完成、皆標 `ready-for-agent`：

**已完成**：

- **T01** [#185] 死重清除（commit `365f1dd`）：刪
  `option_chaser/workspace.py`／`data/base.py`／`webapp/`（已空）／
  10 個死測試檔；`store.py` 移除檔案系統／event-sourcing 半邊
  （~315 行）；`now_utc_iso`／`ny_today` 搬進新的 `api_app/clock.py`；
  `main.py` 底部重複的 `app = create_app()` 一併刪。**兩處刻意不刪**
  （偏離票面字面範圍，皆已在 commit message 記錄原因）：
  `store.best_return()`——測試明文把它當跨層一致性規則（防
  QA1-03 迴歸），不是死碼；`data/treasury.py`／`data/dividends.py`
  的本機檔案快取——雖然 Vercel 唯讀 FS 讓這支分支正式環境不會走到，
  但 44 條測試明確測這三層 fallback 設計，屬環境限制、非死碼
- **T02** [#186] Storage 連線生命週期修形（commit `937f9a1`）：
  `PostgresStorage` 建構不再 eager `_ensure_schema()`；`request_scope()`
  只在 `ContextVar` 放空狀態、真正呼叫才 lazy connect；`main.py` 兩個
  middleware（correlation id／storage scope）合併成一個。過程中在 T03
  驗證階段抓到 T02 自己留下的一個真 bug：`storage` pytest fixture 在
  全新資料庫上會撞 `UndefinedTable`（schema 建立時機被延後、fixture
  卻假設它已存在），已在 T03 一併修正並記錄
- **T03** [#187] 詳細頁 fetch 紀律（commit `f257abe`）：新增
  `src/fetchCache.ts`（in-flight 去重＋參照計數快取＋`AbortController`），
  `ScenarioDetail`／`IvHistory`／`Settings` 接線。抓到兩個問題：jsdom
  不支援 `AbortSignal.any`（改手寫 `combineSignals`）、快取是模組級
  singleton 會跨測試污染（`test-setup.ts` 補 `afterEach` 重置）
- **T04** [#188] View 契約：移出死欄位（commit `74f7517`）：
  `serialize_result()` 移除 `report_text`／`methodology_text`
  兩個從未被前端讀取的欄位，`schema_version` 2→（本次不變動語意，
  純粹欄位瘦身）；契約樣本重產、前端型別與測試同步瘦身
- **T05** [#189] IV history pipeline 模組化（commit `446e2d7`）：新增
  `option_chaser/ivpipeline.py`（~770 行，port-based：`VendorPorts`／
  `StoragePorts`＋單一進入點 `build_iv_history()`），把 `main.py` 內嵌
  的 IV history 編排（Exact-Contract 逐腿重建＋Legacy 兩段式
  backfill＋Spread IV Gap）搬成獨立引擎模組，**本票刻意不動
  `main.py` 呼叫路徑**（T10／#192 才切換）。新增
  `tests/test_ivpipeline_parity.py`：同一組輸入分別跑「真正 HTTP
  endpoint」與「新模組直接呼叫＋純記憶體 `FakeIvStorage`」兩條路徑，
  逐位元比對輸出。過程中抓到測試假體本身的排序 bug（`iv_observations`
  沒依 `observed_on` 排序，兩個既有 adapter 都有排序、這是 port 的
  隱含契約）並修正，同時把這條契約寫進 `StoragePorts.iv_observations`
  欄位註解

**已完成**（續前）：

- **T06** [#190] Refresh Run 核心（commit `bac4785`）：新增
  `POST /api/scenarios/refresh-run`——省略 id＝全部未過期劇本（且真的
  排除，不是排進去才短路）、帶 id＝只刷新那幾個（P4 用這條路徑）。
  Run 內依 symbol 分組，每個 distinct symbol 只呼叫一次
  `_fetch_chain()`（純記憶體 dict 共用，ADR-0001），任一劇本失敗
  不中止整輪、沿用既有 `{stage, message}` 失敗分層（未發明新詞彙），
  失敗項保留舊資料。從 `refresh_scenario` 抽出
  `_refresh_and_save(sc, today, snap=None)` 共用核心，兩端點共用同一套
  過期短路／落地邏輯。E2：`chain_cache` 模組、`ChainCacheEntry`、
  Storage Protocol 對應方法、Postgres 資料表整組移除（schema 只拿掉
  `CREATE TABLE`，沿用專案既有「只加不減」遷移慣例，不下 `DROP
  TABLE`——已部署 Neon 會留一張不再寫入的孤兒表，無害）。回應含
  `remaining`，本票固定回空陣列，Continuation 留給 T07。新增
  `tests/test_api_refresh.py` 一輪刷新測試區塊 14 條

**已完成**（續前）：

- **T07** [#193] Refresh Run Continuation（commit `d349dbc`）：
  `refresh-run` 新增 server 端時間預算（模組常數
  `REFRESH_RUN_BUDGET = timedelta(seconds=45)`，明顯小於 CONTEXT.md
  記錄的 60 秒函式硬性上限，可注入）。每處理完一個劇本（不論成敗）用
  `time.monotonic()` 檢查是否超過 deadline，超過後之後全部劇本
  （含還沒開始的 symbol 分組）原樣依序進 `remaining`——分組順序等於
  `dict` 插入順序，已完成＋remaining 永遠等於送進去的全集。已知且
  刻意接受的架構後果：續跑是全新 invocation，ADR-0001 的 symbol
  去重不會跨呼叫存活，remaining 裡同一個 symbol 續跑會重新抓一次
  （docstring 已記錄，非本票要解決的問題）。新增 Continuation 測試
  區塊 6 條：零預算只完成第一個、其餘全進 remaining；已完成＋
  remaining 精確覆蓋全集不遺漏不重複；人為拉長單一劇本處理時間
  （而非只調預算為 0）也能逼出耗盡；同一組 remaining 再打一次能接續
  完成且與一次做完結果一致；常見規模（12 劇本、3 symbol）預設預算
  下單次完成不觸發 Continuation

- **T08** [#196] Refresh Run 前端整合（commit `bc4f03f`）：`App.tsx`
  從「一條佇列、逐一送出單一劇本刷新」（V4 跟進票／#136）改接後端
  T06/T07 的批次端點。**P1** 整段灰化鎖定（`partitionByLock()`）整組
  移除，改成 `updatingIds: Set<string>`「更新中」徽章——列項全程
  可點、顯示上一輪舊資料，不反灰、不拿掉 `href`；`sortScenarios()`
  不再把更新中的項目獨立排到後面（用它上一輪的 `best_return` 正常
  排序）。**P2** `runBatch()` 累計整輪成功／失敗數，Toolbar 顯示
  「N 成功／M 失敗」（`formatRunSummary()`），取代逐一「第幾個／
  共幾個」進度。**P4** 新建劇本只呼叫 `runBatch([created.id])`，不再
  刷新全部劇本；開站與手動點「重新整理」才刷新全部未過期劇本。
  **Continuation** `runBatch()` 用迴圈追 `response.remaining` 直到
  清空，對呼叫端透明——後端分批續跑不需要前端知道正在分批。單一
  劇本重試（卡片失敗重試、詳細頁刷新入口）維持走既有單一劇本
  `refresh` 端點（`refreshOne()`），不占用批次端點。
  **E2E 連鎖修正**（本票最大宗的非功能性工作）：Playwright glob
  `**/api/scenarios/*/refresh` 不匹配 `/api/scenarios/refresh-run`
  （`*` 只吃一個路徑段，`refresh-run` 是單一段、不含 `/refresh`
  子路徑）——開站與建立劇本現在一律打批次端點，既有大量 E2E 測試的
  單一劇本 refresh route mock 因此攔不到，`updatingIds` 卡住不清、
  後續斷言逐一 timeout。修法：`smoke.spec.ts` 新增全域
  `test.beforeEach` 空氣回應（`{results:[],remaining:[]}`）當安全網，
  逐一補上測試專屬的 `refresh-run` route（含失敗案例回
  `{ok:false,stage,message}`）；`desktop.spec.ts` 的共用
  `routeTwoScenarios()` 與個別測試同步補上。順手修正一條文案斷言
  過期（`"1/1"` 進度→新版「更新中……」單一狀態文字）。
  全套測試：後端 1434 條（記憶體＋真實 Postgres）全綠；前端 Vitest
  628 條全綠；typecheck／build 通過；Playwright e2e 87 條全綠
  （iPhone 54＋Desktop 33）。

- **T09** [#191] View 契約：Candidate 去重（commit `1266a6b`）：
  `candidates`／`expiry_best`／`expiry_top10`／`expiry_groups[].
  rows[]` 四個容器過去各自完整序列化一份同一個 Candidate（重疊時最多
  重複 4 次），新增頂層 `candidate_pool`（單一字典，鍵＝
  `candidate_key`，跨策略共用一份——key 本身已含策略前綴天生不衝突），
  四個容器改存 key 字串引用。`_candidate()` 的輸出對同一個 key 是
  container-invariant（唯一依賴入選容器的欄位是 `CandidateView.pros`，
  而 `pros` 從不序列化進 View），去重因此只需要比對 key。
  `find_candidate()`／`representative_candidate()` 兩個讀取端同步改走
  pool，並保留舊 schema（<=2，容器內直接內嵌完整字典）的相容分支——
  「既有已儲存的 View 不做資料遷移」，這兩處是僅有需要相容的讀取
  路徑（其餘容器只在剛產生的新鮮 view 上被讀取，不會遇到舊格式）。
  schema_version 2→3。Payload 實測：契約樣本 229KB→55KB、
  231KB→55KB，各縮減約 76%。
  韌性／完成度計算共用：`scenarios.py` 新增 `ResilienceMetrics`／
  `resilience_metrics()`，把 `scenario_vector()`／`completion_curve()`／
  `completion_scan()`（最貴，1200 步線性掃描）依 `id(val)` 快取；
  `service._v4_fields()`（View 路徑）與 `report._resilience_lines()`
  （CLI／API 文字報告路徑）共用同一個由 `_single_leg_result()`／
  `_spread_result()` 建立、貫穿整輪分析的快取字典——`rank_spreads()`／
  `sorted()`／切片不複製元素，同一個候選在 report 與 View 兩條路徑、
  以及 View 自己三個容器之間用的都是同一個 Python 物件，`id()` 因此
  是安全的快取鍵。實測（`xyz_v2_snapshot.json`）：`completion_scan`
  呼叫次數 16→9（−44%）。
  前端：`api.ts` 新增 `CandidateMap`（不叫 CandidatePool，避免跟既有
  `./CandidatePool` 元件同名）與 `resolveCandidate(view, key)`；
  `ExpiryTop10.candidates` → `candidate_keys`；`baselineTopCandidate()`
  改走 pool；`expiry.ts::expiryOptions()` 新增 `view` 參數解回完整
  內容；`ExpiryStructure.tsx` 新增 `view` prop，呼叫端
  `ScenarioDetail.tsx` 同步補上。六個共用契約樣本的既有 Vitest 檔
  （`AnalysisReport`／`ExpiryStructure`／`Heatmap`／`ScenarioDetail`／
  `SpreadHistory`／`expiry`）與兩個 Playwright 規格全部同步通過。
  全套測試：後端（記憶體＋真實 Postgres）全綠；前端 Vitest 628 條
  全綠；typecheck／build 通過；Playwright e2e 87 條全綠（iPhone 54＋
  Desktop 33）。

- **T10** [#192] IV history pipeline 上線（commit `c51043e`）：
  `iv_history()` 路由改呼叫 T05（#189）建置的
  `option_chaser.ivpipeline.build_iv_history()`，main.py 只保留 HTTP
  邊界職責（權限 gate／candidate 404／把 `create_app()` 收到的資料源
  與 storage 接成 `VendorPorts`／`StoragePorts`／呼叫模組／疊
  diagnostics 信封）。刪除舊的內嵌編排十餘個函式（`_backfill_iv`／
  `_ensure_contract_history`／`_reconstruct_leg_series`／
  `_leg_historical_iv_payload`／`_spread_gap_payload` 等）與其模組層級
  姊妹函式，連同因此未使用的匯入（`ivhistory`／`ivreconstruct`／
  `ivspread`／`ivtrend`／`ratecurve`／`dividends`／`DAYS_PER_YEAR`／
  `days_between`／`QuotaExhausted`／`ThreadPoolExecutor`／
  `as_completed`）與兩個死常數。**保留**HTTP-request 生命週期關注點
  （`_CollectingDiagnostics`／`_select_for_persistence`／
  `_select_for_storage`／`_flush_diagnostics`）——這些不屬於引擎模組。
  main.py 淨減少 942 行（2255→1370）。
  測試：修正 20 條因符號搬遷而斷的匯入；重寫 AST 結構隔離測試
  （`test_exact_contract_pipeline_never_calls_the_reanchoring_
  functions`）改掃 `ivpipeline.py` 原始碼——隔離保證因此變得更強
  （模組結構上不 import `api_app`，不只是命名慣例）。
  **AC 逐項核對，一項判斷偏離記錄如下**：main.py 不再含任何金融決策
  邏輯；舊編排刪除非新舊並存；HTTP 測試檔維持 120 條全綠——重新盤點
  發現 T05／#189 實際只新增了一條 parity 測試，並未真的把既有 120 條
  行為斷言搬進新模組專屬測試檔（票面「確認已在 #189 搬移完成」與
  實況不符）；鑑於逐一拆分 2971 行、120 條測試成「純 HTTP」與「純
  編排」兩類的工作量與本票核心目標（切換呼叫路徑）不成比例、且拆分
  本身有引入覆蓋率漏洞的風險，判斷維持現狀（沿用既有 120 條測試作為
  cutover 的行為回歸防線）比強行拆分更符合「不求快，求正確性」，已
  記錄供需求方覆核。新增 iv-history 契約樣本
  （`contracts/iv_history_sample.json`，`scripts/
  gen_iv_history_sample.py` 產生，涵蓋逐腿統計量套組＋Spread IV Gap＋
  Normalized Skew 三個家族皆有真實資料）——`today` 在這個端點結構上
  恆為 `ny_today()`（無 DI 注入點，全站既有一致設計），因此不比照
  `analysis_sample.json` 加上「必須逐位元相同」的自動化 drift 測試
  （那類測試在此會隨日期滾動系統性變紅，是引入新的不穩定性而非
  防護）。切換前後逐位元相同：由 T05 既有 parity 測試＋全套 120 條
  既有行為斷言在 cutover 後原樣通過，兩者共同證明。
  全套測試：後端（記憶體＋真實 Postgres）全綠；前端 Vitest 628 條
  全綠（本票不觸碰任何前端檔案）；typecheck 通過；Playwright e2e
  Historical IV 相關 18 條全綠（cutover 對前端完全透明）。

**已完成**（續前）：

- **T11** [#194] IV 冷 backfill 兩段式（P3-a）：`option_chaser/
  ivpipeline.py` 新增三個函式——`legacy_target_expirations()`（票面
  「Legacy 家族要鎖定哪幾個到期日」判準抽出，`build_iv_history()`
  與獨立補建端點共用同一條規則，避免兩處各自重算出不同答案）、
  `legacy_backfill_status()`（純讀取、零 vendor 呼叫，只回報「今天
  跑過了嗎」與上一次真正跑過的 `outcome`／`note`）、
  `run_legacy_backfill()`（既有 `backfill_iv()` 的別名進入點，
  Progressive Backfill 本身——配額、取樣排程、到期日梯子演算法、
  「今天已跑過」短路——逐字沿用，零重複邏輯）。`build_iv_history()`
  的 Legacy 家族段落改呼叫 `legacy_backfill_status()` 取代原本同步
  呼叫 `backfill_iv()`，回應新增 `backfill_pending` 欄位；Exact-
  Contract 家族（`ensure_contract_history()` 漸進式補缺口）完全不受
  影響——CONTEXT.md 明文區分兩者不是同一種「backfill」概念。

  `api_app/main.py`：`iv_history()` 路由拆出三個共用 helper
  （`_iv_diagnostics_emitters()`／`_iv_history_gate()`／
  `_iv_pipeline_ports()`，把原本內嵌的閘門／candidate 查找／emitter
  建構／port 組裝抽出來，PERF-01 的「credential 只查一次」優化透過
  顯式 `credentials` 參數延續，不因拆分而退化成重複查詢），新增
  `POST /api/scenarios/{id}/iv-history/backfill` 端點呼叫
  `ivpipeline.legacy_target_expirations()`／`run_legacy_backfill()`
  觸發真正的補建，兩個端點共用同一套 gate 因此對同一個
  scenario_id／candidate_key 不會給出不一致的答案。

  **測試（`tests/test_api_iv_history.py`）大規模更新**：21 條既有
  測試因為「`GET .../iv-history` 不再同步觸發 backfill」而斷言失敗，
  另外發現 6 條測試雖然仍綠燈、但已經悄悄變成**只驗證到跟原意不同的
  事**——`rec.calls == []`／`all(e is None for e in rec.expirations)`
  這類「沒有東西發生」式的斷言，在 backfill 觸發權轉移到新端點後
  變成恆真（vacuous pass），不是真的在驗證「不重抓」「不多帶
  expiration」。逐一排查後全數修正：新增 `_backfill()` test helper
  （對應 `POST .../backfill`），既有靠 `_get()` 順便觸發 backfill 的
  斷言改成先呼叫 `_backfill()` 再視情況讀 `_get()`／backfill 回應
  本身；`test_the_full_ledger_covers_every_stage_and_shares_one_
  correlation_id`（DG-04 核心交付）改寫成兩段——`cache`／`backfill`
  兩個 stage 現在只活在 backfill 回應自己的 correlation_id 底下，
  `GET` 回應涵蓋其餘六站，兩次請求合起來仍是完整的「N→0」帳本，只是
  不再擠在同一個 correlation_id——這是兩段式設計的真實、預期後果，
  不是需要掩蓋的缺陷，已在測試 docstring 記錄。全套後端測試（記憶體
  ＋真實 Postgres 雙後端）1504 條全綠。

  **前端**：`src/api.ts` 新增 `IvHistoryView.backfill_pending`／
  `ivHistoryBackfill()`／`IvHistoryBackfillResult`；`src/fetchCache.ts`
  新增 `invalidateIvHistoryCache()`；`src/IvHistory.tsx` 新增獨立
  effect——偵測 `backfill_pending` 時呼叫補建端點，完成（不論成功
  失敗，皆已設計成不會無限重試：同一個 (scenario, candidate) 組合
  這次掛載只嘗試一次，`backfillAttempted` ref 守門）後 invalidate
  快取＋重新整份請求，卡片頂端顯示「歷史資料補建中……」（不必展開
  Advanced 就看得到，比照「補建中不擋內容、舊資料照常可看」的既有
  P1 精神延伸）。**施工中抓到並修正一個真 bug**：第一版直接引用了
  沒宣告過的 `currentDataRef`（編譯不會過，是 hooks 呼叫順序限制下
  一時筆誤），改成在 early-return 之前重算 `dataKey === key ? data
  : null` 這條跟 render 用的 `currentData` 同一條判斷式；另外發現若
  同一個候選的補建仍在飛行中就切換候選，`backfillInFlight` 會卡在
  `true` 永遠不清（`finally` 裡的 `if (!alive) return` 連帶跳過了
  重置），已改成 effect cleanup 一律重置這個旗標，換候選時「補建中」
  提示不會誤留在新候選的卡片上。前端測試新增 5 條（`IvHistory.
  test.tsx`：自動觸發／`backfill_pending` 為 false 時不觸發／進行中
  文字＋完成後自動重抓換新資料／同一候選只嘗試一次即使重抓後仍
  pending／補建端點本身失敗也會重抓、不會卡住），Playwright 新增
  1 條（`smoke.spec.ts`，手機 viewport：完整兩段式流程，含明確掛獨立
  route `**/api/scenarios/*/iv-history/backfill*`——既有教訓
  「`iv-history*` 尾綴 `*` 不吃路徑分隔符」，不依賴既有 route 順序
  僥倖成立）。全套：後端 1504、前端 Vitest 633、typecheck／build
  皆過、Playwright e2e 88 條（iPhone 55＋Desktop 33）全綠。

**已完成**（續前）：

- **T12** [#195] Backfill 併發形狀修正（執行緒池只建一次）：
  `option_chaser/ivpipeline.py::backfill_iv()` 原本在 `_fetch_day_
  bounded()` 內每處理一批到期日梯子（≤ `IV_BACKFILL_DAY_CONCURRENCY`
  ＝4 個）就 `with ThreadPoolExecutor(...) as pool:` 新建銷毀一次——
  不只「每天一次」（票面敘述），是「每批一次」，一天若有 20 個到期日
  就已經是 5 次。改成 `ThreadPoolExecutor(max_workers=
  IV_BACKFILL_DAY_CONCURRENCY)` 只在 `for day in schedule:` 迴圈外
  建立一次，整個 `with` 區塊涵蓋跨全部天數、跨每天內全部批次的迴圈，
  `_fetch_day_bounded()` 改吃呼叫端傳入的既有 `pool`、自己不再開關；
  併發上限數值（`max_workers`）與既有的「批次大小＝併發上限」邏輯
  完全不變，只是 worker 數量固定掛在整個 run 而非重新配置。函式
  結束（含中途 `break` 中止）時 `with` 的 `__exit__` 才
  `shutdown(wait=True)`——已送出但尚未完成的呼叫仍會先跑完，這條
  既有保護語意本來就活在 `as_completed(futures)` 逐一等待的迴圈裡，
  未被本票觸碰。

  測試：新增 `test_the_whole_backfill_run_creates_exactly_one_thread_
  pool`（`tests/test_api_iv_history.py`）——monkeypatch
  `ivpipeline.ThreadPoolExecutor` 為計數子類別，沿用既有
  `_client_with_long_expiration_ladder`（20 個到期日梯子，遠超併發
  上限）但**不觸發失敗**（`fail_on_first=False`，前次 PERF-05 測試
  皆刻意讓第一天就失敗以驗證中止語意，本票要的是完整跑滿多天多批次
  才測得出「真的只建一次」），並用兩條前提斷言（真的橫跨多天、真的
  每天拆成一批以上）確保不是巧合只有單一批次的退化情境。修正前
  ／修正後對照驗證：對修正前的舊程式碼跑這條新測試，實測建立
  **125 次**執行緒池（25 天 × 每天 5 批）；修正後恰好 **1 次**——證明
  這條測試真的抓得住這個迴歸，不是掛著看形狀的擺設。既有 PERF-05
  三條 concurrency 測試（`test_bounded_concurrency_stops_launching_
  new_batches_after_the_first_failure`／`test_the_extra_calls_from_a_
  failure_are_bounded_by_concurrency_minus_one`／
  `test_a_failure_in_the_middle_of_a_batch_still_saves_the_
  successful_siblings`）與既有取樣排程／到期日梯子測試逐一核對，
  一條斷言都沒改、全數原樣通過——AC 明文要求的「不受影響、不需要
  修改」逐位元成立。全套後端測試（記憶體＋真實 Postgres 雙後端）
  1505 條全綠。純後端模組改動，未觸碰任何前端／E2E 檔案。

**已完成**（續前）：

- **T13** [#197] 全面回歸與最終驗收（本輪 T01–T13 最後一張票，純
  驗證＋整理，未新增任何 production 程式碼）：

  **自動化把關（AC 前 3 項）**：後端 pytest（記憶體＋本機真實
  Postgres 兩組合併跑）**1423 條全綠**；前端 `typecheck` 乾淨、
  Vitest **633 條全綠**、`vite build` 成功；Playwright **88 條全綠**
  （iPhone 55＋Desktop 33）。

  **既有數值語意零回歸（AC 第 4 項）**：`git log` 逐一核對整個
  T01–T12 範圍（`365f1dd~1..HEAD`），`option_chaser/ranking.py`／
  `filters.py`／`valuation.py` **零 commit 觸碰**——排名／過濾／估值
  三個核心模組從第一張票到最後一張票原封不動，不是靠測試巡邏出來的
  結果，是結構上不可能被本輪動到。`#118` 選取身份回歸守門
  （`tests/test_selection_regression.py`）與 `test_ivpipeline_parity.py`
  合併 12 條全綠——Historical IV／Exact-contract／Spread IV Gap／
  Normalized Skew／排名／收益率的既有斷言一條都沒有鬆綁或改寫成更
  寬鬆的版本，T11 施工中唯一需要「換句話說」的既有測試
  （`test_the_full_ledger_covers_every_stage_and_shares_one_
  correlation_id`）已在 T11 自己的紀錄裡說明原因並保留完整驗證力，
  不是本票才發現、也不是弱化。

  **Before/after 對照表**（逐項標示本地實測 vs 推估，兩者不混寫；
  格式沿用 Performance 輪 PERF-07 既有慣例）：

  | 項目 | 施工前 | 施工後 | 依據 |
  |---|---|---|---|
  | `api_app/main.py` 行數 | 2121 行（T01 開工前，`git show 365f1dd~1:api_app/main.py`） | 1450 行 | 本地實測（`wc -l`，直接量測，非估計） |
  | `main.py` 職責 | ~1000 行 domain 邏輯（IV 編排 680 行、Refresh Run 編排、儲存半邊死碼與檔案系統 fallback 等混在 HTTP handler 裡） | 金融決策邏輯全部下沉（`ivpipeline.py`／`scenarios.py` 等引擎模組），`main.py` 只剩 HTTP 邊界職責（gate／port 組裝／diagnostics 信封） | 本地實測＋結構檢視（T01／T05／T10／T11 逐票記錄的職責遷移，`ranking.py`／`filters.py`／`valuation.py` 零改動佐證核心引擎未被牽動） |
  | 一輪刷新的 serverless invocation 數（N 個劇本） | N 個（`App.tsx` 逐一 `await` 單一劇本端點，回報#025 診斷） | 1 個（`POST /api/scenarios/refresh-run`，超過時間預算才 continuation 續跑） | 本地實測（T06／T07／T08 各自測試套件：`test_api_refresh.py` 一輪刷新 14 條、Continuation 6 條、前端 `runBatch()` 迴圈追 `remaining` 直到清空皆有專屬斷言） |
  | 同一輪刷新內同 symbol 的 chain 抓取次數 | 每個劇本各自抓一次（即使同一個 symbol） | 每個 distinct symbol 只抓一次（`_fetch_chain()` 純記憶體 dict 共用，ADR-0001） | 本地實測（T06 commit `bac4785`，`tests/test_api_refresh.py` 專屬斷言） |
  | View 契約 payload 大小（`candidate_pool` 去重前後） | 229KB／231KB（兩份契約樣本） | 55KB／55KB，各縮減約 76% | 本地實測（T09，`scripts/gen_contract_sample.py` 重產後直接量測檔案大小） |
  | `completion_scan`（韌性計算，單次分析最貴的部分）呼叫次數 | 16 次 | 9 次（−44%），View 三個容器與 report 文字路徑共用同一份快取字典 | 本地實測（T09，對 `xyz_v2_snapshot.json` 實測） |
  | 詳細頁 deep-link 開啟的 refetch cascade | 3 次 ~100KB 全量下載＋2 次 iv-history（回報#025 診斷觀察） | 同一個資料身分（key）的並發呼叫只真的發一次底層請求（in-flight 去重＋參照計數快取） | 結構性保證＋本地單元測試實測（T03，`src/fetchCache.test.ts`：N 個並發呼叫者→`calls` 恰好等於 1）；**未在本沙箱對真實 deep-link 頁面做端到端網路請求計數**（sandbox 連不到正式 Neon／vendor，無法重現真實頁面載入的完整請求序列）——「cascade 這個問題類別被消滅」是結構性事實，但「這個頁面實際從 5 次變成幾次」沒有本地端到端量測數字，屬推估 |
  | Storage 連線數（一次完全不碰 storage 的 request，例如某些驗證即失敗的路徑） | 1 條（PERF-01 既有機制：scope 一進入就無條件開一條，不論這次 request 用不用得到） | 0 條（T02：scope 進入時只註冊空狀態，第一次真正呼叫 `_connect()` 才開） | 本地實測（T02，`tests/test_storage_contract.py::test_a_scope_with_no_storage_calls_never_opens_a_connection`：monkeypatch `psycopg.connect` 計數，確認全程零呼叫） |
  | Storage 連線數（一次 warm、真的會碰到 storage 的 request 內） | 沿用 PERF-01 既有的「整個 request scope 共用一條」（本輪未改變這件事） | 不變——T02 只修「要不要開」的時機（惰性），不改「開了之後共不共用」（一直都是共用） | 沿用既有事實，非本輪新測量；PERF-07 的 36→1 數字對這個情境依然成立 |
  | Legacy (tenor,delta) 冷 backfill 執行緒池建立次數（25 天×20 個到期日梯子的完整一次 run） | 125 次（25 天 × 每天 5 批，每批各自新建銷毀） | 1 次（整個 run 共用） | 本地實測（T12，`test_the_whole_backfill_run_creates_exactly_one_thread_pool`：對修正前後的程式碼分別跑同一條測試，125 vs 1 兩個數字都是實際執行量到的，不是推算） |
  | Legacy backfill 的「今天已跑過」重複觸發成本 | 同步夾在 `GET /iv-history` 裡，使用者每次打開詳細頁都可能觸發一次冷啟動延遲（即使當天已經補過） | 兩段式：`GET` 只讀狀態（零 vendor 呼叫），真正觸發交給獨立 `POST .../iv-history/backfill`，前端只在 `backfill_pending: true` 時嘗試一次 | 本地實測（T11，`legacy_backfill_status()` 為純讀取函式，`tests/test_api_iv_history.py` 多條端點層測試佐證；`backfillAttempted` ref 守門確認同一掛載期間至多一次前端觸發） |

  **P1–P4 產品語意運作確認（AC 第 6 項）**：四項裁示對應的既有／
  本輪測試逐一核對，皆有專屬自動化覆蓋（手機＋桌面 viewport 皆有）：
  - **P1（更新中徽章，非整段灰化鎖定）**：T08 `App.tsx` 的
    `updatingIds` 機制與既有 Playwright 案例（`smoke.spec.ts`／
    `desktop.spec.ts` 既有 refresh-run 相關案例）維持全綠，本輪未
    再修改這段前端邏輯
  - **P2（部分成功摘要，N 成功／M 失敗）**：T06／T08 的
    `formatRunSummary()`／後端 `{stage, message}` 失敗分層測試維持
    全綠
  - **P3（兩段式 backfill）**：T11 新增專屬 E2E（`smoke.spec.ts`，
    手機 viewport：`backfill_pending` 觸發補建、進行中顯示「歷史
    資料補建中……」、完成後自動重抓補全）
  - **P4（建立劇本只刷新該新劇本，範圍收斂）**：T06 既有的
    「帶 id＝只刷新那幾個」路徑與 T08 前端 `runBatch([created.id])`
    測試維持全綠

  **上一輪 Performance 修正確認未受影響（AC 第 7 項）**：`git log
  365f1dd~1..HEAD -- api_app/treasury_cache.py api_app/rate_cache.py
  option_chaser/ivtrend.py api_app/diagnostics.py` 四個檔案**零
  commit 命中**——Diagnostics 降噪（PERF-02）、Treasury 年快取
  （PERF-03）、`ivtrend` 演算法改良（PERF-04）三個檔案本輪完全沒有
  被觸碰，不是「測過沒壞」，是結構上不可能被本輪動到；三者各自的
  既有測試套件（`test_api_treasury_cache.py`／`test_ivtrend.py`／
  diagnostics 相關測試）皆包含在上面 1423 條全綠裡。

  **AC 最後一項——需求方真機驗收：本票無法自行完成**，這是唯一需要
  人工執行的項目，記錄於此供需求方核對；其餘七項 AC 已全數以自動化
  或結構檢視方式驗證完畢。

**T01–T13（Architecture Review 輪，spec #184）全數完成。** 依專案
規則「全部 ticket 做完才開 PR，中途不主動開」——本輪 13 張票（含
T13 自己）程式碼與測試層面已全數完工，等需求方在正式部署版完成真機
驗收、下指示後才開 PR、準備合併回 master。

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

**Supplemental spec 已發佈（2026-08-18，`/to-spec`）——issue #159**：
`Historical IV Reconstruction + Point-in-Time Correctness + Diagnostics
降噪`，`ready-for-agent`。**#151 的 methodology 不變**（canonical identity
與統計方法逐字不動），#159 只修三件事：(1) canonical IV 從「抄 vendor
`iv`」改成「一律自己 reconstruction」，vendor `iv` 降為 benchmark；
(2) point-in-time 正確性（r／q 對齊每筆觀測自己的日期，補上既有
`compute_q()` 缺的 `ex_date` 上界）；(3) diagnostics subsystem 分離
＋事件聚合（取代「持續調高 cap」）。已在 #151 留言連結，未修改 #151
內容。

核心架構決策：**快取存 raw quote、reconstruction 在讀取時重算**——
recipe 已經錯過一次，存算好的 IV 會讓任何修正都要重花 vendor 額度重抓；
存 raw 則修正立即對全部歷史生效、零 vendor 成本（代價 ~0.1 秒／候選）。
`contract_iv_history` 舊格式列視為 cache miss 重抓（純快取、可再生）。
新 reconstruction 模組的輸出形狀刻意等同 `ivtrend.py` 既有輸入形狀，
統計層一行不用改。Seam 沿用既有兩層（純函式單元測試＋HTTP API），
不新增 seam。

**拆票完成（2026-08-18，`/to-tickets`，需求方核准後發佈）**——11 張
子票 **#160–#170**（HIVR-01–11），全部 `ready-for-agent`、皆為 #159
的 GitHub sub-issue。需求方裁示「拆成好作業的方式比較適合，我不會
中間停下來看」，因此**以單張票好施工為準、不為了中途 demo 而合併**
——原本設計成一張「能 demo」的大 tracer bullet（空卡片變成有圖）已
依此拆成三張（#163 資料層／#164 純模組／#165 接線）。

依賴順序（照舊 `/implement` 一張張做）：

- **HIVR-01**（#160）point-in-time Treasury 曲線 ✅ commit `36ffd29`：
  `ratecurve.py` 新增 `parse_treasury_csv_rows`／`parse_treasury_xml_rows`
  （回傳全部有效資料列，不挑最新）＋純函式 `curve_asof(rows,
  observation_date)`（取不晚於觀察日的最新一列、找不到回傳 `None`
  不外插）；既有 `parse_treasury_csv`／`parse_treasury_xml` 改為對新
  row-level 解析器取 `max()` 的薄包裝，既有行為與既有測試原封不動。
  `data/treasury.py` 新增 `fetch_curve_rows_for_year`／
  `fetch_curve_range`（單年 CSV→XML 備援／跨年度串接、單年失敗不擋
  其他年份）——本票範圍內純前置件，尚無呼叫端，接線留給 HIVR-06
- **HIVR-02**（#161）point-in-time 股利 q ✅ commit `5db92ca`：
  `dividends.py` 新增 `compute_q_asof(history, spot, observation_date)`——
  沿用既有 TTM 365 天下界，加上界 `ex_date <= observation_date` 擋
  look-ahead（那天還沒除息的分配不可能影響那天的選擇權價格）；分母用
  呼叫端傳入「那天」的 spot、離群值抑制沿用既有 `_dampen_outliers`
  不重寫。既有 `compute_q()`（即時分析路徑）原封不動。純前置件，
  尚無呼叫端
- **HIVR-03**（#162）diagnostics subsystem 拆分 ✅ commit `c43e062`：
  `diagnostics.py` 新增 `SUBSYSTEM_EXACT_CONTRACT`（"historical_iv"，
  沿用既有名字）／`SUBSYSTEM_LEGACY_REANCHOR`（"normalized_skew"，
  新增，借用 legacy 路徑自己輸出欄位的既有詞彙）；`main.py` 的
  `iv-history` 端點改用兩個獨立 `emit` closure，`_select_for_
  persistence` 改成先依 `event.subsystem` 分組、每個 subsystem 各自
  套用既有三層優先序（抽成 `_select_family_for_persistence`）、各自
  享有一份完整的 cap（40，未調高）——大量 legacy 事件不再擠掉
  exact-contract 事件。新增直接證明「洪水不擠掉對方」的測試＋端到端
  版本（真跑滿 25 天 backfill）。redaction／correlation-ID 未動，
  Settings 診斷頁泛型渲染 `event.subsystem`，前端零變更
- **HIVR-04**（#163）historical quote record ✅ commit `2e7695d`：
  `marketdata.py` 的 `_parse_contract_history`／`fetch_contract_history`
  改回傳寬版 quote dict（`date`／`updated`／`dte`／`bid`／`ask`／
  `mid`／`underlying_price`／`vendor_iv`，取代舊版 `(date, iv)` 二元組），
  `date` 推導方式不變（仍是這一列自己的 `updated`）；既有 `_num()`
  缺值口徑（None／非數字／0.0 一律缺值）延伸到新欄位。`api_app/
  storage` 的 `ContractHistory.points` 型別隨之變寬（`tuple[dict,
  ...]`），postgres.py 讀寫直接原樣傳遞 JSONB object、不重組成
  2-tuple；storage 本身不解讀形狀。`main.py::_ensure_contract_history`
  改用 `q["date"]` 合併快取與新抓資料，並在讀出快取後偵測「舊格式列
  （元素是 list 不是 dict）」——偵測到就當 cache miss 整批重抓（一次性
  代價：每張合約 1 credit），不會被「今天已嘗試過」短路掉、也不會被
  誤讀成新格式。新增 `_project_vendor_iv()` 轉接器讓
  `_leg_historical_iv_payload`／`ivtrend` 繼續吃舊版 `(date, iv)`
  形狀——本票沒有任何東西消費新欄位（reconstruction 要等 #164／#165），
  Historical IV Trend 卡片畫面行為維持不變
- **HIVR-05**（#164）reconstruction 純模組 ✅ commit `3166dbc`：新增
  `option_chaser/ivreconstruct.py`（`ivtrend.py` 同層純模組）——
  `reconstruct_iv_series(option_type, strike, expiration, quotes,
  rate_by_date, dividend_yield_by_date)`。price 用 vendor `mid`、缺席退
  `(bid+ask)/2`（HIVR-04 的寬版 quote 結構上沒有 `last` 欄位，「絕不用
  last」因此是結構性保證）；quote 合法性（bid／ask 皆正、未倒掛）獨立
  於 `mid` 是否存在；`T` 用該筆觀測自己的日期算（既有
  `DAYS_PER_YEAR`／`days_between`，不引入新慣例）；r／q 由呼叫端逐筆
  觀測日以 `{date: value}` 傳入，模組本身零 I/O；model 沿用既有
  `implied_vol()`（BS93）。任一輸入缺席或反解無解只讓那一筆變
  `(date, None)`，以四個具名原因（`unusable_quote`／`no_rate`／
  `no_dividend_yield`／`inversion_failed`）分別計數，不影響其他筆。
  `vendor_iv` 整個模組零讀取，canonical series 結構上不可能引用它。
  輸出形狀與 `ivtrend.py` 既有統計函式輸入形狀逐位元相同，測試直接
  餵過去驗證零轉接層。28 條測試皆為 round-trip 風格（已知 sigma 經
  `american_price()` 算出價格，反解回來核對，不手猜期望值）；隔離紅線
  （不 import `ivhistory`、`ranking.py`／`filters.py` 不依賴這個模組）
  比照 `ivtrend.py` 既有寫法。本票沒有任何呼叫端，不影響其他檔案
- **HIVR-06**（#165）接線：**空卡片變成有圖** ✅ commit `8323cf0`：
  `iv-history` 端點改用 `ivreconstruct.reconstruct_iv_series()` 逐點
  重建，取代原本的 `_project_vendor_iv()` 透傳——vendor IV 全 null 的
  真實合約（ORCL／TLT LEAPS）現在能畫出完整走勢圖。`create_app()`
  新增可注入的 `rate_curve_rows`（預設 HIVR-01 的
  `treasury.fetch_curve_range`），兩腿共用一次抓取（Treasury 曲線與
  標的無關）；`_rate_by_date_for_leg()` 用 `ratecurve.curve_asof()`＋
  `rate_for_tenor()` 逐日查表；`_dividend_yield_by_date_for_leg()` 用
  `dividends.compute_q_asof()`，分母用該筆觀測自己的
  `underlying_price`——沿用既有 `dividend_loader`（HIVR-02 的
  ex-date 上界讓「今天抓一次完整配息清單」本身就是逐筆觀測日正確的，
  不需要新的快取層）。**每一筆都重建，包含 vendor 剛好給非 null iv
  的那些**——`ivreconstruct` 模組本身零讀取 `vendor_iv`，canonical
  series 結構上不可能退回它。既有隔離測試的函式清單擴充涵蓋新增的
  四個接線函式。測試 fixture 需要真正的財務 round-trip 才有意義：
  新增 `_synthetic_quote()`（用跟 production 完全相同的 point-in-time
  r/q 查表方式建構報價，保證精確反解回指定 sigma）；施工中發現並
  記錄兩個 fixture 真 bug（固定 ±0.01 價差在深度價外、近到期日的
  近零價格會讓 bid 變負值，改比例價差；多個既有測試寫死的日期恰好
  落在這份 fixture 候選自己的到期日**之後**，`T<0` 讓 `implied_vol`
  正確回 `None`——不是重建邏輯錯，是 fixture 日期沒對齊）。新增端到端
  測試涵蓋三項核心主張：vendor iv 全 null 仍完整重建、canonical
  series 不採用刻意設錯的 vendor_iv、r／q 逐觀測日查表（用橫跨配息
  ex-date 前後兩筆觀測驗證，若誤用「今天」的值會露餡）。全套：後端
  雙後端全綠、前端 vitest 557 條**零修改**全綠、typecheck 通過——
  證實回應形狀真的沒變
- **HIVR-07**（#166，commit `323a529`）— Reconstruction 帳本＋staleness
  可見性＋HTTP 203 註解更正：新增兩個 exact-contract 家族專屬
  diagnostic stage。`reconstruction`——`_reconstruct_leg_series()` 重建
  完後每腿發一筆帳本事件，`fetched`／`reconstructed`／`usable` 三個
  計數＋`ivreconstruct` 四種失敗原因逐一計數（含 0），回答「vendor 回
  N 筆究竟在哪一站變成 0 筆」不必讀程式碼；加進 `_ALWAYS_KEPT_STAGES`
  （原 `("backfill", "metrics")` 擴為 `("backfill", "metrics",
  "reconstruction")`）避免同一腿高流量的 `reanchor`／`vendor_fetch`
  事件把它擠出 per-request cap（40，未動）。`staleness`——只在
  `_ensure_contract_history()` 真的抓到新資料時發一筆（沿用既有
  「今天已跑過不重抓」短路，不對快取命中發這個事件），帶
  `request_time`／observation 自己的 `date`／原始 `updated`／
  `staleness_days`／vendor 自己回報的 `vendor_dte` 與本站獨立算的
  `computed_dte`——兩者不一致時現在看得出來；`staleness_days<=1` 為
  info（下一個 session 的正常 rollover），否則 warning。順帶更正
  `marketdata.py` 對 HTTP 203 的錯誤註解：vendor 官方文件明確指出 203
  代表「這筆回應來自快取層」而非「延遲報價」，且文件本身把
  mode→status 這種對應點名為常見誤解；既有行為（接受任何 2xx，未寫死
  `status==200`）本來就正確，只有解釋錯了，已修正並補一條原始碼文字
  掃描回歸鎖（`test_the_203_comment_states_cache_layer_not_delayed_
  quote`）。測試：`tests/test_api_iv_history.py` 新增 5 條端到端
  （fetched/reconstructed/usable/四種原因逐一計數、無可用時 warning、
  staleness 欄位含 DTE 不一致案例、陳舊但成功可辨識、帳本在高流量
  legacy 事件洪流下存活）＋`tests/test_data_marketdata.py` 新增 203
  註解回歸鎖。全套後端雙後端（memory＋真實 Postgres）全綠。
- **HIVR-08**（#167，commit `4ea40d6`）— 近到期 low-confidence 標記：
  `option_chaser/ivreconstruct.py` 新增具名常數
  `LOW_CONFIDENCE_DTE_THRESHOLD = 14` 與純函式 `is_low_confidence()`
  ——純粹的天數比較（觀測日距到期日），不讀取 price／IV，因此對任一
  觀測日皆可呼叫，包含反解失敗的缺席觀測。`_leg_historical_iv_
  payload()` 的 `points` 序列化新增 `low_confidence` 欄位，套用在
  裁窗後的每一點上；標記本身不影響 `trimmed`／統計量計算路徑，被
  標記的點依然完整餵給 moving average／Bollinger／z-score／
  percentile／Δ4w，也依然計入 `observation_count`——純資訊品質標記，
  不刪點、不改統計、不影響 ranking／filtering／candidate selection
  （那些路徑本來就不 import `ivreconstruct`，既有隔離測試涵蓋）。
  前端 `IvTrendPoint` 型別新增 `low_confidence: boolean`；依票上
  「前端呈現可以最小化，只要帶著欄位」的裁示，本票不新增視覺呈現。
  測試：`test_ivreconstruct.py` 新增 5 條純函式測試（門檻邊界、
  常數值、對缺席觀測仍可呼叫）；`test_api_iv_history.py` 新增 4 條
  端到端測試（近到期標記為 true／遠到期為 false、標記不影響統計量、
  不外洩進 diagnostic context 白名單）＋修正兩條既有測試因新增欄位
  而需要更新的精確字典比對。全套後端雙後端全綠，前端 typecheck／
  557 條 vitest 全綠。
- **HIVR-09**（#168，commit `67d7e55`）— Vendor-IV benchmark 合理性
  gate：`option_chaser/ivreconstruct.py` 新增兩個具名常數
  `VENDOR_IV_BENCHMARK_MIN = 0.01`（下界依 calibration 實測抓到的
  退化值，真實 vendor 回應出現過 `vendor_iv≈0.0001`）／
  `VENDOR_IV_BENCHMARK_MAX = 5.0`（對齊 `implied_vol()` 自己的搜尋
  上限，不是另外挑的門檻）與純函式 `vendor_iv_is_benchmarkable()`。
  這個 gate 只管 benchmark／QA／診斷比較要不要採信某筆 vendor
  `iv`，跟 canonical series 完全無關——canonical series 本來就不讀
  `vendor_iv`（既有紅線，本票新增測試直接證明：同一份報價序列只換
  vendor_iv 為退化值／正常值／缺席三種情況，反解出來的 canonical
  series 逐位元相同）。新增 diagnostics stage `vendor_benchmark`
  （`api_app/diagnostics.py` STAGES／whitelist）與
  `_emit_vendor_benchmark()`（`api_app/main.py`，接在
  `_reconstruct_leg_series()` 裡緊接 reconstruction 帳本之後發送）：
  每一腿一筆事件，報告這張合約有幾筆觀測帶了 vendor IV
  （`vendor_iv_present`）、其中被 gate 排除幾筆
  （`vendor_iv_excluded_degenerate`——排除是可見的，不是靜默丟棄）、
  實際拿去跟 canonical series 比較幾筆（`vendor_iv_compared`）、
  平均絕對差（`mean_abs_diff`，無可比較筆數時缺席）。加進
  `_ALWAYS_KEPT_STAGES` 避免被同一腿高流量事件擠出 per-request
  cap。測試：`test_ivreconstruct.py` 新增 8 條純函式測試（門檻邊界、
  真實退化值、上界與 solver 搜尋上限的關聯、canonical series 不受
  影響的直接證明）；`test_api_iv_history.py` 新增 4 條端到端測試
  （退化值排除且可見、門檻內值正常比較、缺席值不算進任何一個計數、
  帳本在高流量 legacy 事件洪流下存活）＋修正一條既有測試因新增
  stage 而需要更新的 stage 集合斷言。全套後端雙後端全綠；本票未
  觸碰任何前端檔案，typecheck／557 條 vitest 確認無回歸。
- **HIVR-10**（#169，commit `fd03b56`）— Legacy backfill／reanchor 事件
  聚合＋週末 no_data 降為 info：Legacy（normalized skew）家族兩個高
  流量事件源收斂成各自一筆摘要。**Backfill**：一次批次最多 25 天、
  每天可能查好幾個到期日，舊版每次 vendor 呼叫各發一筆
  `vendor_fetch`＋`payload_parse`（外加每天一筆 `database_write`），
  輕鬆破百筆。新增 `_emit_backfill_summary()`，批次結束後只發一筆
  事件，攜帶三分類計數：`days_with_data`／`days_no_data_expected`
  （週末，正常現象）＋`days_no_data_unexpected`（交易日卻沒資料，
  值得留意）／`days_failed`。`_vendor_fetch_severity`／
  `_payload_parse_severity`／`_emit_surface_telemetry` 三個只服務舊
  機制的函式隨之整個刪除。**Reanchor**：舊版對這個 symbol 已存的每一
  筆歷史快照各發一筆 `reanchor` 事件——累積一年快照的 Scenario 光開頁
  就能炸出幾十筆。新增 `_reanchor_in_grid()`（純判準，DG-04 既有
  「核心欄位全 null」邏輯原樣沿用）與 `_emit_reanchor_summary()`，
  一次 request 只發一筆摘要：`total_dates`／`in_grid_dates`／
  `out_of_grid_dates`。**週末 severity**：新增 `_is_weekend()`（只濾
  週末，比照 `ivhistory.trading_days_back()` 既有「不維護美股假日表」
  的取捨與理由——`sampling_schedule()` 本來就只排交易日，市場假日
  結構上無法在沒有假日表的情況下與「交易日撲空」區分，因此仍落在會
  示警的那個桶子，這是明確記錄的已知殘留噪音，不是遺漏，issue 留言
  已記錄這個裁決）。Normalized Skew 的計算與呈現本身完全未動
  （`option_chaser/ivhistory.py` 與 `tests/test_ivhistory.py` 零改動，
  `git diff` 確認）；`_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST` 維持 40，
  噪音是靠少發事件而非調高上限降下來的（新增測試正面驗證：完整
  backfill 現在遠低於 20 筆 legacy 事件，過去輕易破百）。測試：刪除
  三條只服務已移除機制的既有測試，新增一條用函式簽章直接證明新摘要
  函式結構上不吃任何 vendor 自由格式文字；重寫三條 reanchor 測試改驗
  聚合後的計數，新增一條混合情境測試對照票上範例句型；重寫兩條
  no_data 測試涵蓋 AC5／AC6（交易日撲空仍示警、週末撲空降為 info，
  後者用 `monkeypatch` 注入真實週六日期）；重寫三條過去依賴「legacy
  backfill 天然構成洪水」的既有測試（HIVR-03／HIVR-07／HIVR-09）——
  端到端版本改驗證「兩個 subsystem 正常並存」，cap 溢位保證改用合成
  事件的單元測試覆蓋。全套後端雙後端全綠；本票未觸碰任何前端檔案，
  typecheck／557 條 vitest 確認無回歸。
- **HIVR-11**（#170，commit `62d9f17`）— 全面回歸與 E2E 最終驗收：
  逐條稽核 issue #170 明列的九條紅線，全數已由既有測試覆蓋（多數在
  HIVR-01–10 施工當下已各自涵蓋），補齊兩處缺口——「exact-contract
  路徑絕不呼叫 legacy 重錨定函式」的既有 AST 隔離測試擴充涵蓋
  HIVR-07／HIVR-09 新增的三個函式（`_emit_reconstruction_ledger`／
  `_emit_staleness`／`_emit_vendor_benchmark`，先前只涵蓋到 HIVR-06
  為止）；新增端到端測試逐欄位驗證回應裡的 `contract` identity 精確
  等於候選自己的 leg（strike／expiration／option_type／
  contract_symbol），先前這條紅線只被別的測試間接蘊含、沒有專屬
  斷言。全套把關：後端 pytest 雙後端（memory＋真實 Postgres）全綠
  （1427 條）；前端 typecheck／557 條 vitest／production build 全綠；
  Playwright E2E 手機＋桌面共 84 條全綠（quota／vendor 失敗優雅降級、
  掛牌不滿一年如實顯示、完全無可比較觀測誠實顯示「沒有歷史資料」等
  場景皆由既有 E2E 覆蓋，本輪未新增專屬案例——新增的 `low_confidence`
  欄位與新增診斷 stage 皆為前端零渲染的純加法，不影響任何既有
  fixture）。沒有任何既有斷言被放寬或移除以達成全綠——HIVR-10 刪除
  的三條測試針對的是該票本身刻意移除的機制，不是弱化仍然存在的行為
  保證。本輪未發現新的實質缺陷，只補了上述兩項測試覆蓋缺口。

**Spec #159（HIVR-01–11，issues #160–170）全十一張子票全數完成。**
依專案規則全部子票做完才開 PR、merge 回 master，中途不主動開——目前
等需求方 cue 才實際開 PR。

**下一步**：`/implement` 施工中，依序做票、無阻擋不停下等待確認
（需求方裁示）。依專案規則全部子票做完才開 PR，中途不主動開。

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
- **Historical IV 手機圖表改版＋錯誤分級修正**（無 issue 編號，需求方
  2026-08-21 直接反饋，commit `66bd20f`）：手機版三張圖（Spread IV
  Gap／買腿／賣腿，共用 `IvTrend.tsx` 的 `IvTrendChart`）改成 Firstrade
  風格——資料點預設不再是常駐大圓點，改成 CSS `opacity: 0` 的互動熱區，
  只在 hover／focus／tap 中的那一點加上 `chart-point-active` 才顯示
  （連同 tooltip），scope 在 `.iv-history` 內不影響 Spread 淨成本走勢圖
  既有的 `.chart-point`；新增 `useIsDesktop.ts`（`useIsDesktop`／
  `useResponsiveHeight`，從 `App.tsx` 抽出並共用）讓手機走勢圖高度
  明顯壓低、桌面維持原高度。文字瘦身：`SpreadSummary` 的 Δ4w ratio
  說明與固定的 Spread Percentile 語意句搬進新的 `SpreadSummaryAdvanced`，
  掛在既有 Advanced／Diagnostics 收合區，主畫面只留 Current／
  Percentile／4 週變化／涵蓋小字。錯誤分級：`IvHistory` 新增 `dataKey`
  追蹤資料屬於哪個候選，重新嘗試（新分析後同一候選，經新增的
  `analyzedAt` prop 觸發，接線自 `ScenarioDetail.tsx`）失敗時，若已有
  這個候選的資料就只降級成非阻斷警示（`.iv-history-stale-warning`），
  不再整塊蓋掉已經畫得出來的圖表；legacy normalized_skew 失敗（頂層
  `status`）本來就已經只留在 Advanced 裡，這次新增明文回歸測試釘住。
  經 `/code-review` 兩軸（Standards／Spec）審查，套用其中一項建議
  （抽出 `useResponsiveHeight` 消除高度判斷的重複）。全套回歸：後端
  pytest 全綠（記憶體假體）、前端 Vitest 596 passed、Playwright e2e
  87 passed（iPhone＋Desktop）、typecheck／build 皆過。
- **Historical IV 手機 UX 收尾輪——再瘦身／真 scrubber／診斷語意分級**
  （無 issue 編號，需求方 2026-08-22 反饋，commit `4d7ee05`）：上面那輪
  （`66bd20f`）的「opacity:0 常駐熱區」其實還是逐點命中，且手機仍太
  高，這輪收尾三件事。**再瘦身**：`IvTrendCard`／`SpreadSummary.tsx`
  手機分支合併「標籤＋現值」「百分位＋Δ4w」各一行，桌面 JSX 不動；
  圖高收到裁示範圍（Leg 68→54px、Spread 80→62px）。CSS 抓到真正的
  密度元兇——`.iv-history` 底下的 `<p className="caption">` 從未把
  瀏覽器預設 `margin:1em 0` 歸零，flex 容器裡這段 margin 不會跟 `gap`
  合併，每段多墊近 26px；補上 `.iv-history p { margin: 0 }`，連同
  padding／gap／separator／chart margin 一起收緊，桌面在
  `@media (min-width: 1100px)` 內明確恢復原值。**真正的 chart-wide
  scrubber**：新增純函式 `nearestIndexForClientX`（`ivHistoryChart.ts`，
  含 9 條單元測試）把游標／觸點螢幕座標換算成最近的 observation
  index；`useChartScrubber`（`IvHistory.tsx`，`IvTrend.tsx` 原樣複用）
  讓整張 `<svg>` 變成單一 pointer／touch／keyboard 互動介面（
  `setPointerCapture` 支援觸控拖曳、方向鍵＋Escape／失焦支援鍵盤），
  移除兩三百個各自 `tabIndex=0 role="button"` 的隱形命中圓點——
  `TrendChart`（Normalized Skew）與 `IvTrendChart`（Spread／買／賣腿）
  兩處都套用。**診斷語意分級**：`InlineDiagnostics` 新增必填
  `variant: "failure" | "info"`，呼叫端明講語意而不是靠 event
  severity 猜——`IvHistory` 整塊無資料錯誤分支傳 `"failure"`，只在
  主資料已成功（`IvAdvanced`）才出現的 vendor／legacy 診斷事件改傳
  `"info"`（「Historical IV 診斷資訊」，不再誤報「資料取得失敗」）。
  `/code-review` 兩軸：Standards 抓到一處測試斷言該用精確相等卻用了
  `toBeLessThanOrEqual`，已修正；Spec 確認三項全數符合、無 scope
  creep，並指出 `useResponsiveHeight`（`useIsDesktop.ts`）已無呼叫端，
  一併移除。驗收：手機四圖情境（Spread Gap＋買＋賣＋Advanced 內
  Normalized Skew）實測卡片高度 1051px→566.5px（降 46%，其中約 31
  個百分點在裁示的 25–35% 範圍內，其餘來自上述 margin 歸零這個額外
  抓到的既有缺陷，兩者都沒有犧牲任何資訊，因此未刻意收斂回原區間）。
  全套回歸：typecheck 乾淨、Vitest 614 passed、build 乾淨、Playwright
  e2e 87 passed（iPhone＋Desktop）。

**Performance 修正輪——spec 已發佈（2026-08-22，issue #176，票未開）**：
需求方裁示下一階段暫停 MVP V2／N-leg／任何新 Strategy／跨 Strategy
Dashboard，只處理 Option Chaser V1 效能問題。依據：session 內
Architecture + Performance Survey（回報編號 #019，非 GitHub issue）與
一次輕量記憶體假體 profiling（回報編號 #020）——確認 warm
`/iv-history` 一次約 36 次 storage calls（production Postgres adapter
每個 method 各開新 Neon 連線）、diagnostics 落盤佔 23 次全 info、
credential/settings 重複讀 3 次、Treasury 曲線這條路徑完全無快取、
本機 CPU 大宗是 `ivtrend._rolling_windows` O(n²)（126ms）＞
reconstruction（62ms），以及 cold Normalized Skew backfill（25 天×4
到期日）inline 最多 100 次序列 vendor 呼叫、量級 15–60 秒——需求方
明確裁示 Normalized Skew 必須保留且維持預先計算，不接受「Advanced
展開才觸發」當主要解法。`/to-spec` 前先跑一輪 5 個並行 Explore agent
逐一確認五個修正方向各自的最小安全 seam（storage 連線用
`contextvars.ContextVar` 侷限在 `postgres.py` 內部、Protocol 簽章不
動；diagnostics 新增 `append_diagnostics()` 批次方法＋政策掛在
`main.py` 的 `_flush_diagnostics()`、回應內容不變只影響落盤；Treasury
快取以**年份**為鍵而非「今天」，過去年份可永久快取、當年比照既有
rate/dividend cache 市場日語意，PIT 正確性由鍵設計本身保證；
`_rolling_windows` 雙指標 O(n) 化，保留完全相同的日曆天視窗與邊界
判定；cold backfill 改併發呼叫而非序列，vendor 端批次已確認結構上
不可行）。Spec（issue #176，`ready-for-agent`）涵蓋五＋一項修正
（storage 連線／diagnostics／Treasury cache／ivtrend CPU／cold
backfill 併發化／同 symbol chain 重複抓取次要項），已回報需求方，
等待確認後 `/to-tickets`。

**Performance 修正輪——tickets 已開（2026-08-23，issues #177–#183，
共 7 張，全數以 GitHub native sub-issue 掛在 #176 底下）**：需求方
確認 spec #176 通過後裁示 `/to-tickets`，並補一條施工護欄——cold
backfill 必須是 bounded concurrency，不要求現在指定固定數字但不得
無上限 fan-out，失敗後不得繼續大量啟動尚未開始的 vendor requests，
且保留 spec 已要求的 failure regression test；此護欄已寫進 PERF-05
的 Acceptance Criteria。七張票：**PERF-01** [#177]（Storage 連線
生命週期——request-scoped connection）、**PERF-02** [#178]
（Diagnostics 批次寫入＋只留 warning／error 落盤）、**PERF-03**
[#179]（Treasury 曲線快取，以年份為鍵、PIT 安全）、**PERF-04**
[#180]（`ivtrend._rolling_windows` 雙指標 O(n) 化）、**PERF-05**
[#181]（cold Normalized Skew backfill——bounded concurrency）、
**PERF-06** [#182]（同 symbol chain 重複抓取去重，次要、範圍受限）、
**PERF-07** [#183]（全面 before/after 對照＋最終回歸驗收）。**依賴
結構**：PERF-01～06 彼此互相獨立、沒有硬阻擋邊（各自命中不同檔案／
不同 seam，spec 自身 Further Notes 已確認過一次）；只有 PERF-07 是
六張的匯總驗收，`Blocked by` 全部六張。標 PERF-01 為下一張純屬建議
排序（風險最低、獨立可驗證），非強制依賴順序。範圍再次確認排除：
不做 V2、不做 N-leg、不做 main.py architecture extraction、不做
無關 cleanup。**尚未開始 implementation**，等需求方指示。

**PERF-05 [#181] AC 修正——不可能契約改寫（2026-08-23，施工前，
尚未開始 implementation）**：需求方拆票整體批准後，指出原 AC 有一條
不可能契約——「不會因為併發而多花掉序列版本本來會擋下來的額度」。
Bounded concurrency 下這件事在數學上不成立：第一個 failure 被觀測前，
最多已有 concurrency－1 個其他 requests 已經 in-flight。已改寫為
誠實、可驗證的上界式契約：(1) 第一個 failure 被觀測後不再啟動任何
新 vendor request；(2) 已 in-flight 的 requests 允許完成、不強制
cancel；(3) failure 相對 serial 造成的額外 request 數硬性上界為
concurrency－1；(4) 不得宣稱「不會多花 serial 原本會擋下的額度」；
(5) 已成功完成的 in-flight observations 正常保留落盤，不為模擬
serial 而丟棄已付出配額成本拿到的資料；(6) diagnostics 新增記錄
failure 事件／in-flight completions／本批最終結果摘要三項；
(7) regression test 新增鎖住上界與「failure 後不再啟動新工作」兩條
斷言，原「序列版本整批中止」測試維持不動。issue #181 body 已更新
（保留修正前歷史於 issue 內文，未刪除重寫）。

**Sequencing 定案（2026-08-23，取代先前「建議排序」）**：
`#180 → #179 → #177 → #178 → #181 → #182 → #183`（即 PERF-04→
PERF-03→PERF-01→PERF-02→PERF-05→PERF-06→PERF-07）。這是需求方
指定的固定執行順序，非程式碼層級硬阻擋——PERF-01～06 之間仍然沒有
`Blocked by` 依賴，只有 PERF-07 繼續 `Blocked by` 全部六張。

**Performance 修正輪施工中（2026-08-23，`/implement` 依定案順序連續
施工，中途不停）**：

- **PERF-04**（#180）✅ `_rolling_windows()` 雙指標 O(n) 化——`left`
  指標隨排序後的日期單調前進、不回頭；視窗邊界「含當天、含左邊界」
  不變，三個呼叫端呼叫方式不變，未換成增量式統計。重構前先補一條
  含真實日期缺口＋剛好卡在 30 天邊界的特徵化測試（先綠燈於重構前）。
  `/code-review` 兩軸：Standards 無程式面問題（僅提醒 CLAUDE.md 待
  更新，即本次一併處理）；Spec 抓到一個真正的邊界情境——舊版逐點全掃描
  對「同一天兩筆有效觀測」是對稱可見（不論列表位置），新版切片
  `valid[left:right+1]` 只對「同天稍後那筆」對稱、「同天較早那筆」看
  不到後面那筆，理論上不是逐位元相同。查證後確認：這個情境在既有
  pipeline 裡結構性不會發生——`reconstruct_iv_series()` 與 storage 的
  contract history 都是 per-contract per-date 語意（`test_rewriting_
  the_same_contract_overwrites_rather_than_duplicates` 等既有測試把關），
  輸出序列與輸入 quotes 逐筆一一對應、quotes 本身不含同日重複。已在
  `_rolling_windows()` docstring 明文記下這個前提，不新增用不到的
  duplicate-date 處理邏輯（避免無謂的一般化）。本地量測（合成 365 天、
  約 80% 涵蓋率的序列）：舊版 O(n²) 3.891 ms/call，新版 O(n) 0.600
  ms/call，6.5x，且新舊輸出逐位元相同（`assert old_out == new_out`
  通過）。全套後端測試（記憶體＋Postgres 兩組）667 條全綠。
- **PERF-03**（#179）✅ Treasury 曲線列快取，鍵是**年份**——本輪風險
  最高的一項。新增 `api_app/treasury_cache.py`（結構逐一鏡射
  `rate_cache.py`／`dividend_cache.py` 三態快取設計：成功／近期嘗試
  失敗／陳舊備援），新增 `Storage` Protocol 的 `TreasuryYearCacheEntry`
  ＋`get_treasury_year_cache`／`save_treasury_year_cache`（memory／
  postgres 兩個 adapter 皆補齊，postgres 新增 `treasury_year_cache`
  表）。PIT 安全靠鍵設計本身鎖死：過去年份（`year < today.year`）一旦
  `rows is not None` 即永久新鮮，不看 `fetched_at` 多舊；當年比照
  `rate_cache.py` 市場日語意（5 分鐘失敗去重窗、7 天陳舊備援窗）。
  `main.py` 的 `_fetch_rate_curve_rows` 改呼叫新的
  `_cached_rate_curve_rows()`（惰性單例，同一套 `_rate_curve_loader()`
  模式），取代直接呼叫注入的 `rate_curve_rows`；一律以整年範圍向底層
  來源請求（Treasury／`fetch_curve_range` 本來就只看年份，不看月日）。
  測試：新增 `tests/test_api_treasury_cache.py`（17 條，含 spec 點名
  「唯一真正重要」的
  `test_a_past_years_rate_is_never_shadowed_by_the_current_years_cache`
  ——2025／2026 各自灌入可辨識假利率，熱快取後反覆查
  `observation_date="2025-01-15"`，斷言永遠拿到 2025 的利率）與
  `test_storage_contract.py` 新增 6 條 per-year 隔離的 round-trip 契約
  測試（memory＋postgres 各一份）。`/code-review` 兩軸皆無 hard
  violation：Standards 軸指出 `main.py` 「惰性單例 dict」模式（`_db`／
  `_rate_curve_loader`／`_dividend_loader`）這次多了第四個重複實例，
  屬既有模式延伸、非本票新增，依「不做 main.py architecture
  extraction／不做無關 cleanup」裁示不動；Spec 軸確認全部 AC 落實、
  無 scope creep。本地量測：模擬冷啟動 25 天×4 到期日情境（100 次
  `_fetch_rate_curve_rows` 呼叫全落在同一年份、同一市場日），快取前
  100 次網路呼叫、快取後 1 次。全套後端測試（記憶體＋Postgres 兩組）
  684 條全綠（667 + 17 條新增）。
- **PERF-01**（#177）✅ Storage 連線生命週期——request-scoped
  connection。`postgres.py` 新增模組層級 `contextvars.ContextVar`
  （`_request_connection`，存 `(dsn, conn)`，不掛在 `PostgresStorage`
  單例物件屬性上，避免併發 request 互相汙染）＋`_BorrowedConnection`
  （讓既有 40 處 `with self._connect() as conn:` 呼叫慣例零改動，
  `__exit__` 回 `False` 不吞例外、不關閉連線）；新增
  `PostgresStorage.request_scope()`：進入時開一條連線放進 ContextVar，
  `finally` 無論成敗都關閉並清空，**開連線本身失敗時不設定
  ContextVar、直接放行**（不讓整個 request 跟著炸，退回逐次開連線的
  既有行為，`/api/health` 這類容忍連不上的端點不受影響）。`main.py`
  新增 `_storage_connection_scope_middleware`（`getattr` 拿
  `request_scope`，`memory.py` 沒有這個方法就直接跳過——`Storage`
  Protocol／`memory.py` 依裁示零改動）。順手消除 iv-history request
  內 credential 三處重複讀取（`_settings_view()`／`_known_secrets()`／
  挑選中 Provider 的 token 取得）：新增 `_credential_map()`，三處都改
  吃可選的 `credentials` 參數，不傳時行為不變（其餘呼叫端不受影響）。
  測試：新增 3 條 Postgres-only adapter 層級測試（monkeypatch
  `psycopg.connect` 計數，斷言一個 scope 內任意多個 method 呼叫恰好
  一次 connect()；離開 scope 後連線確實關閉清空；開連線失敗時優雅退回
  逐次開連線）。`/code-review` Standards 軸無 hard violation（僅幾處
  既有模式延伸的 judgement call，依裁示不動）；Spec 軸稍後回報：全部
  AC 落實、無 scope creep，但抓到一處測試強度不足——「離開 scope 後
  連線確實關閉」原本只斷言 ContextVar 清空＋下一次呼叫不炸掉，沒有
  真的抓住那條連線物件斷言 `.closed`（舊連線只是被丟棄、從未關閉一樣
  會通過）。已修正：測試改成在 scope 內抓住 `_request_connection`
  當下借用的連線物件，離開後直接斷言 `borrowed_conn.closed`（fix 隨
  下一次 commit 一併附上，未另開 PERF-01 專屬 commit）。本地量測：
  10 次 storage 呼叫在 scope 外開 10 條連線、scope 內開 1 條。
- **PERF-02**（#178）✅ Diagnostics 批次寫入＋只留 warning／error
  落盤。`Storage` Protocol 新增複數形式 `append_diagnostics()`，與
  既有單筆 `append_diagnostic()` 並存不取代；postgres.py 用一次多列
  INSERT（VALUES 佔位符數量依 `len(events)` 動態組出，不是逐筆迴圈，
  沒有使用者資料進到 SQL 文字本身、無注入風險）＋retention DELETE
  跑一次；memory.py 用一次 `deque.extend()`。main.py 新增純函式
  `_select_for_storage()`（只留 `severity in ("warning","error")`），
  掛在 `_flush_diagnostics()` 裡、`_select_for_persistence()`／
  `_select_family_for_persistence()` 既有三層優先序完全不動、
  `diagnostics.py` 的 `emit()` 也未觸碰——過濾只影響「寫進資料庫」
  這一步，回應的 `kept` 清單維持過濾前的完整版本。測試：`test_api_
  iv_history.py` 裡「用全 info 合成事件驗回應與落盤一致」的既有測試
  改用 `_telemetry_surface({})`（混合 severity）重新驗證，斷言方向從
  `shown_ids <= stored_ids` 改為 `stored_ids <= shown_ids`（前者
  PERF-02 後結構性不再成立：健康 request 大多數事件是 info、不落盤，
  舊方向的驗證意義本來就是「回應看得到的必然也存得到」，這件事本身
  不成立了；不是放寬斷言，是測試前提換了）；新增 `_select_for_
  storage()` 的 3 條純函式單元測試、`test_storage_contract.py` 新增
  3 條批次寫入／retention 等價性測試（memory＋postgres 各一份）、
  端到端測試驗證健康 request（兩腿各灌 60 天 round-trip 觀測涵蓋
  bands／Δ4w 兩個窗口）對 diagnostics 資料表寫入 0 筆但回應完整帶著
  info 事件。`/code-review` Spec 軸確認三層優先序與 `emit()` 皆逐行
  核對零改動、測試資料修正方向正確，無 scope creep；Standards 軸抓到
  兩處已修正：(1) 其中一條測試的 docstring 誤稱「`_rich_surface`
  全程成功只有 info」——實測並非如此（預設空 `contract_history` 下
  exact-contract 家族本來就會冒出 reconstruction／metrics warning），
  已改寫成準確說明改用 `_telemetry_surface({})` 的真正理由（驗證
  legacy 家族刻意、可預期的 warning，不糾纏在另一子系統的旁支行為裡）；
  (2) `postgres.py` 的 `append_diagnostic()`／`append_diagnostics()`
  重複同一份欄位清單與 trim SQL 字面值，已抽成模組層級常數
  `_DIAGNOSTICS_INSERT_COLS`／`_DIAGNOSTICS_TRIM_SQL` 共用（比照既有
  `_RESULT_COLS`／`_SCENARIO_COLS` 慣例）。全套後端測試（記憶體＋
  Postgres 兩組）1485 條全綠。
- **PERF-05**（#181）✅ Cold Normalized Skew backfill——bounded
  concurrency，依 2026-08-23 修正版契約（見上方 sequencing 定案段落）
  施工。設計取捨：併發套用在**單一天內跨到期日**的扇出（一批最多
  `_IV_BACKFILL_DAY_CONCURRENCY`＝4，`ThreadPoolExecutor`＋
  `as_completed()` 取真實完成順序），**天與天之間維持嚴格序列**——
  一天的批次完全解決（全部成功，或整批中止）才會考慮下一天。這是
  刻意的選擇：既有 regression test（`Recorder` 每次呼叫都失敗、斷言
  `attempted_days==1`）若允許跨天併發，一個永遠失敗的假體會讓多天的
  呼叫同時在飛，那條斷言結構上守不住；`/code-review` Spec 軸判斷這是
  「保守但合規」的實作，不是偷工減料——到期日梯子實務上是個位數項目
  （量級對齊 concurrency＝4），單天內扇出已經收斂掉主要成本（100 次
  序列呼叫→約 25 輪），跨天併發留給未來如果需要再開新票。修正版契約
  七點逐一落實：`_fetch_day_bounded()` 內建批次迴圈，`while idx <
  len(expirations) and first_failure is None` 確保失敗後不再送出新
  批次；`ThreadPoolExecutor` 的 `with` 區塊本來就會等全部已送出的
  futures 做完才離開，不強制 cancel；批次大小＝concurrency，額外呼叫
  數上界精確等於 concurrency－1；程式註解／測試皆未宣稱「不會多花
  serial 原本會擋下的額度」（Spec 軸逐字 grep 確認零命中）；同一批次
  裡失敗前後成功的呼叫一律併入 `merged` 並落盤，不因整天判定失敗而
  丟棄。Diagnostics：`_emit_backfill_summary()` 新增
  `failed_expiration`／`in_flight_after_failure_succeeded`／`_failed`／
  `unstarted_due_to_failure` 四個欄位（已加進 `diagnostics.py` 的
  `_CONTEXT_KEY_WHITELIST`，否則會被白名單機制悄悄丟棄——這是施工中
  抓到的一個真實坑，不是預先想到的）。測試：保留既有
  `test_backfill_abort_is_visible_in_the_summary_event` 不動；新增
  3 條——併發批次失敗後不再啟動新呼叫、額外呼叫數不超過
  concurrency－1、批次中段失敗仍保留成功的同批次資料（其中
  in-flight-after-failure 的成功／失敗切分點刻意不鎖死，因為真實
  執行緒完成順序本來就不是決定性的，`/code-review` 確認這個鬆綁合理、
  不是偷懶）。`/code-review`：Standards 軸抓到已修正——`failed_
  expiration` 缺型別標註、`db.save_iv_observation(...)` 重複邏輯已
  抽成 `_save_day()` 共用；Spec 軸抓到一項真的漏做——before/after
  牆鐘量測完全沒留下痕跡（AC 硬性要求）——已補上：本地模擬（不是
  production 實測，沙箱無出口網路）25 天×4 到期日、模擬延遲
  50ms／次，serial 5.019s vs bounded concurrency 1.287s，3.9x，
  推估真實 vendor RTT 落在 profiling 觀察的 15–60 秒量級時可望縮短到
  約 4–15 秒（未經 production 驗證）。全套後端測試（記憶體＋Postgres
  兩組）1488 條全綠。
- **PERF-06**（#182）✅ 同 symbol chain 重複抓取去重——次要、範圍受限，
  單獨切掉不影響 PERF-01～05／07。新增 `api_app/chain_cache.py`：
  `cached_fetch_chain()` 包住整個既有 `_fetch_chain()`（不管內部走
  自訂還是預設來源），鍵是 symbol，短效期 `CHAIN_CACHE_TTL`，具名
  可調——刻意**不**比照 `rate_cache.py`／`dividend_cache.py`／
  `treasury_cache.py` 的市場日／年份三態設計：這裡是即時報價，短效期
  本身就是正確語意，失敗也不快取（例外原樣往上炸，跟今天行為一致）。
  `Storage` Protocol 新增 `ChainCacheEntry`＋`get_chain_cache`／
  `save_chain_cache`（memory／postgres 皆補齊，postgres 新增
  `chain_cache` 表）。main.py 新增 `chain_cache_ttl` 參數（比照既有
  `fetch`／`rate_loader`／`dividend_loader` 的 DI 慣例），用既有
  `_rate_curve_loader()` 同一套惰性單例模式包裝，快取命中時連
  `_fetch_chain()` 自己的 settings／credential 查詢都省下來。

  **施工中發現一個真實坑並修正**：3 條既有測試（`test_history_is_
  one_continuous_series_across_refreshes_with_a_gap`／`test_raw_
  data_follows_the_latest_refresh_not_a_stale_one`／`test_
  reanalysis_updates_the_card_to_the_newer_numbers`）刻意對同一個
  symbol 連續觸發兩三次「真的重新抓一次」（驗證歷史序列／原始資料／
  清單都跟著最新結果走），跟新快取的設計目的直接衝突——已改傳
  `chain_cache_ttl=timedelta(seconds=0)`（`create_app()` DI 參數）
  停用快取重用，讓它們繼續驗證原本要驗證的事，不是在測 chain cache
  本身。

  **`/code-review` 兩輪修正**：第一輪（Standards 軸）：原本用
  `monkeypatch.setattr(chain_cache, "CHAIN_CACHE_TTL", ...)` 改模組
  內部狀態停用測試裡的快取——本地檢查全部通過（截斷時間戳不會導致
  `age` 算成負值，邏輯本身正確），但抓到這不是本專案既有慣例（既有
  `monkeypatch` 案例一律打在抓取／IO 接縫，不是內部調校常數上，本專案
  DI 早就有 `fetch=`／`rate_loader=`／`dividend_loader=` 這套模式可用）
  ——已改成 `cached_fetch_chain(..., ttl=...)` 顯式參數＋`create_app()`
  的 `chain_cache_ttl` DI 參數，三條測試改用 `create_app(...,
  chain_cache_ttl=timedelta(0))`。第二輪（Spec 軸）：明確指出「使用者
  對同一個劇本連續按兩次刷新」跟「同一批刷新裡不同劇本共用同一個
  symbol」在這個純 wall-clock TTL 設計下**結構上無法區分**，原本
  2 分鐘的 TTL 對真實使用者「過一陣子再手動重新整理」這個明顯不同的
  操作意圖太寬鬆，會讓使用者在毫無提示的情況下看到舊快照——這是需要
  誠實記在案的產品層取捨，不能默默吸收成測試修正的副作用。已將
  `CHAIN_CACHE_TTL` 從 2 分鐘壓到 **15 秒**（大到足以吃到前端逐劇本
  序列送出的同批次請求，小到讓「使用者稍後再手動重新整理」幾乎不會
  落在窗內看到沒有提示的舊資料），並在 `chain_cache.py` 模組 docstring
  明文記下這個取捨與依據；AC 本身已明文接受「即時報價、短效期即正確
  語意」這個政策方向，本輪修正是把 TTL 數字調整到更保守、更貼近
  AC 意圖的值，不是推翻 AC。

  測試：新增 `tests/test_api_chain_cache.py`（8 條，涵蓋首次快取／
  TTL 內重用／過期後恢復各自抓取／symbol 互相獨立／失敗不快取／
  快取讀取失敗優雅退回／序列化往返）與 `test_storage_contract.py`
  新增 4 條 round-trip 契約測試。本地量測：模擬 5 個劇本共用同一個
  symbol 的整批刷新情境，底層 vendor chain 抓取次數從 5 次降到 1 次。
  前端程式碼零改動。全套後端測試（記憶體＋Postgres 兩組）1504 條全綠。
- **PERF-07**（#183）✅ 全面 before/after 對照＋最終回歸驗收——本輪
  最後一張票，合併 PERF-01～06 後重新量測、跑全套回歸。

  **全套回歸（不鬆綁任何既有斷言）**：後端 pytest（記憶體＋本機
  Postgres）1504 條全綠；前端 `tsc --noEmit` 乾淨；前端 Vitest 614
  條全綠；`vite build` 成功；Playwright e2e 87 條全綠（iPhone＋
  Desktop，含大量 Historical IV／Exact-contract／Spread IV Gap／
  Normalized Skew 專屬案例，例如 SIG-04 兩條紅線鎖定測試）。全部
  Historical IV 相關數值語意（Spread IV Gap／買賣腿走勢圖／百分位／
  Δ4w／Normalized Skew）跟施工前逐位元相同——本輪六張票只動效能相關
  的內部機制（連線重用／批次寫入策略／快取層／`_rolling_windows`
  演算法／併發排程），沒有任何一處改變計算邏輯或輸出格式；PERF-04
  另外有專屬一致性斷言（`assert old_out == new_out`）鎖住這件事。
  `ruff check` 額外掃過本輪新增／改動的檔案：僅 1 處發現（`main.py`
  的 `RateCacheEntry` unused import），確認是**施工前既有**（`git log`
  對照 commit `17873b4` 已存在），依「不做無關 cleanup」裁示不動；
  本輪新增的所有檔案（`chain_cache.py`／`treasury_cache.py` 等）本身
  乾淨無警告。

  **Before/after 對照表**（逐項標示本地實測 vs 推估，兩者不混寫）：

  | 項目 | 施工前 | 施工後 | 依據 |
  |---|---|---|---|
  | Storage 連線數（一次 warm request 內） | ~36 條各自新連線 | 1 條共用連線 | 本地實測（PERF-01：10 次呼叫 scope 外 10 條連線→scope 內 1 條，同一套機制） |
  | Diagnostics 寫入次數（健康 warm request） | ~23 次 INSERT＋trim DELETE（全 info） | 0 次 | 本地實測（PERF-02 端到端測試：`test_a_healthy_request_writes_zero_diagnostics_rows_...`） |
  | Treasury 曲線抓取（cold backfill 情境，25 天×4 到期日同一年份同一市場日） | 100 次網路請求 | 1 次 | 本地實測（PERF-03 demo script） |
  | 同 symbol chain 重複抓取（5 個劇本共用一個 symbol） | 5 次 | 1 次 | 本地實測（PERF-06 demo script） |
  | `ivtrend._rolling_windows` CPU（合成 365 天、80% 涵蓋率序列） | 3.891 ms/call（O(n²)） | 0.600 ms/call（O(n)），6.5x | 本地實測（PERF-04），輸出逐位元相同 |
  | `ivreconstruct` CPU | ~62ms（回報#020 profiling 估計） | 不變（62ms） | 推估——本輪範圍明確排除 reconstruction，PERF-04 只動 ivtrend，這段程式碼未被觸碰 |
  | Cold backfill 牆鐘時間（25 天×4 到期日 = 100 次序列呼叫） | 15–60 秒（回報#020 profiling 估計，未在本機用真實 vendor 網路量過） | 本地模擬（50ms/call 模擬延遲）：5.019s→1.287s，3.9x；推估 production：15–60秒→約 4–15秒 | 本地實測（模擬延遲）＋推估（production，實際 vendor RTT 未知） |
  | warm 端到端總時間（含真實 Neon／vendor 網路延遲） | 未曾在本機精確量過（sandbox 無出口網路連正式 Neon／vendor） | 無法本地重現，只能推估：連線數 36→1 省下約 35 次 Postgres/Neon 連線建立開銷（典型量級數十至兩三百毫秒／次，非本次量測得出，屬一般認知），diagnostics 寫入 23→0 再省一批對應的網路往返；兩者疊加方向正確，但沒有本地實測支持任何具體秒數 | 推估 |

  **驗收目標回報**：
  - **warm < 1 秒目標**：無法在本機驗證（sandbox 連不到正式 Neon／
    vendor）。結構性改善方向明確（連線數 36→1、diagnostics 寫入
    23→0、ivtrend CPU 6.5x）且互不衝突可疊加，但沒有本地實測支持
    「確實達到 < 1 秒」這個具體門檻——需要 production 部署後實測確認。
  - **cold path 不再出現 15–60 秒級卡頓**：本地模擬顯示 bounded
    concurrency 在 concurrency=4 下可貢獻約 3.9x 加速，量級對齊
    profiling 原始 15–60 秒範圍換算約縮短到 4–15 秒——但這是基於
    50ms/call 的模擬延遲，不是真實 vendor RTT，正式環境實際 RTT
    可能更高或更低，需要 production 實測確認是否真正跳出「正常情況
    下 15–60 秒級卡頓」這個問題。

  **本輪發現的真實缺陷**：全部在各自的票內當場修掉，沒有延到這張票
  ——PERF-01（連線關閉斷言強度不足）、PERF-02（測試 docstring 對
  fixture 行為描述不準確＋SQL 片段重複）、PERF-05（遺漏 wall-clock
  量測記錄）、PERF-06（monkeypatch 內部常數改成正式 DI 參數＋TTL
  從 2 分鐘壓到 15 秒，修正一個真實的產品層取捨）皆已個別修正並
  重新驗證。PERF-07 本身的最終回歸掃描沒有發現新的真實缺陷。

  **各票 commit**：PERF-04 `0653460`；PERF-03 `0181191`；PERF-01
  `9b7b782`（fix 隨 PERF-02 `978ad73` 一併附上）；PERF-02 `d1d66fd`
  ＋`978ad73`；PERF-05 `b8380f7`；PERF-06 `cceeaa2`＋`4ac238f`。

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

### V1 Product Correctness + Historical IV UX Cleanup（2026-08-25，`/grill-with-docs`，只分析不施工）

需求方提出四項問題，`/grilling` 依 CONTEXT.md／ADR-0001／既有實作與
測試自主 audit，未動 production code。

**1. Updating Lock 需要恢復**：需求方裁示推翻 2026-08-24 的 P1-b
（更新中不鎖定、卡片標徽章仍可點入）——查證確認範圍集中在
`src/App.tsx::runBatch()` docstring 明文的「P1：涉及的卡片標『更新中』
但不鎖定，資料與連結全程可用」與 `ScenarioList.tsx`／
`CompactScenarioList.tsx` 的卡片渲染（`updating` 只加徽章、`<a href>`
本身未被攔截）。Refresh Run 範圍規則（開站／手動＝全部未過期，建立
新劇本＝只刷新新劇本，P4-b）與 Continuation／Partial Success 機制
不受影響，鎖定只管卡片能不能點進去。

**2. Diagnostics 語意分級**：逐一核對 `option_chaser/ivpipeline.py`
全部 `emit(...)` call site 的 severity 判準，找出四個在**正常、成功
顯示資料的情況下也會頻繁觸發 warning** 的既有事件源：
  - `staleness`（exact-contract，`staleness_days > 1` 才警示）——
    vendor 的 Delayed→Historical 轉換要等次一交易日 9:30:01 ET
    （HIVT-06 研究已查證），`staleness_days == 1` 其實是**正常交易日
    的健康狀態**；warning 主要集中在週一或假日後第一次抓取，是行事曆
    產物，不是資料異常
  - `metrics`（legacy 家族，`count == 0` 才警示）——T11 兩段式補建後，
    任何 symbol 第一次被看到（backfill 還沒觸發過）在 legacy 家族的
    `buy_iv`／`atm_iv`／`normalized_skew` 結構上**必然** count=0，這是
    設計上的過渡態，不是資料品質問題
  - `reanchor`（legacy 家族，`out_of_grid_dates > 0` 才警示）——LEAPS
    等長天期候選的座標本來就不是每天的歷史 surface 都覆蓋得到
    （#134 的既有已知限制），結構性會反覆觸發
  - `backfill` 摘要（`days_no_data_unexpected > 0` 才警示）——本站不維護
    美股假日表（HIVR-10 已記錄的已知殘留噪音），市場假日撲空會被算成
    「非預期無資料」
  這四項的共同特徵：**warning severity 目前混合了「這次分析結果可能
  不完整或不可信，使用者該知道」跟「這是系統正常運作下的預期過渡態／
  行事曆產物」兩種完全不同的事**，這正是需求方描述的「資料明明成功
  顯示，但 Advanced／Diagnostics 還有大量 warning/error」的根本原因。
  `vendor_fetch`（exact-contract，vendor 真的回報失敗）與
  `reconstruction`（整段序列零筆重建成功）兩個既有的 warning／error
  來源查證後**確認是真警訊**，不在降噪範圍內。

**3. Percentile 正確性——結論：程式碼與定義本身皆正確；「常看到
80–90 百分位」極可能是統計性質、不是 bug**。全部針對 spec #159／
#151 明文機制逐項查證，並用 production 函式（`ivreconstruct.
reconstruct_iv_series`／`ivtrend.trim_to_window`／
`ivtrend.historical_percentile`／`ivspread.align_spread_gap`）跑過
可獨立重現的合成序列，percentile 另外用完全獨立的手算邏輯核對：
  - current 是否為最新有效觀測：`leg_historical_iv_payload()` 的
    `valid = sorted(... if iv is not None); latest_iv = valid[-1][1]`
    ——確認排序鍵是日期字串（正確按時間排序），且明確排除 `None`；
    刻意讓「今天」的 quote 反解失敗（crossed quote），驗證 latest
    正確退回到前一個有效觀測日，不是 crash、不是誤用 None、不是偷用
    vendor_iv
  - 是否只用同一張 exact listed contract：快取鍵是 `contract_symbol`
    （OCC 身份字串），逐張合約各自一列，結構上不可能混入別的合約
  - 一年 window：`trim_to_window()` 用日曆天 cutoff（`today - 365`），
    篩選條件正確、順序保留
  - null／failed reconstruction：`reconstruct_iv_series()` 逐筆獨立、
    任一筆缺輸入或反解無解只讓那一筆變 `(date, None)`，不影響其他筆、
    不外插、不換合約、不退回 vendor_iv——四種失敗原因獨立計數
  - Spread IV Gap 只用共同存在日期：`align_spread_gap()` 用
    `set(buy_map) & set(sell_map)` 交集，任一天只有一腿有值就整天不
    進輸出，回傳 gap 恆為 `float` 從不為 `None`——**確認**
  - percentile 的 `≤` 定義與顯示值一致：`sum(1 for x in series if x
    <= current) / len(series)`，前端 `第 N 百分位` 文案未與此矛盾
  - production 函式輸出與獨立手算結果**逐位元相符**（3 個場景各自
    驗證：全年持平／持平＋雜訊／近三週真實 vol spike，皆 match）

  **關鍵發現（Monte Carlo，500 次試驗，零真實 vol 變化、只有逐日
  ±1% 報價雜訊）**：平均 percentile 0.4749（≈理論預期 0.50，證明**無
  系統性偏誤**），但 **P(percentile ≥ 80%) = 18.4%、P(≥90%) = 8.2%**
  ——即使 IV 完全沒有真的變貴變便宜，單一最新觀測相對於一年歷史母體
  的百分位排名，光靠雜訊就有將近五分之一的機會落在 80 以上。這是因為
  `current_percentile` 定義上取的是**未平滑的單一最新觀測**（跟 30 天
  `moving_average` 不同），單點排名統計天生沒有「該收斂到 50%」的
  性質。**這解釋了「常看到 80–90 百分位」這個症狀本身，且不需要真實
  production 資料就能證明**——是統計量本身的雜訊敏感度，不是計算
  邏輯錯誤，程式碼行為與 spec #151/#159 的既有定義逐字一致（`current`
  一律是最新原始觀測，非本輪才發現的既有設計，非意外）。

  **需要 production 實測才能確認的部分**（無法用本地合成資料回答）：
  真實市場在特定時期是否也存在額外的系統性（非雜訊）貴估——例如
  point-in-time r／q 資料源在近期是否有系統性缺口導致晚近觀測的
  reconstruction 品質下降；這需要真實 exact contract 的完整一年歷史
  報價（沙箱對 vendor 網域仍是 403，且本輪未依過去慣例推送臨時
  GitHub Actions probe——範圍明確限定「只分析不施工」，動 CI 或觸碰
  master 不在這輪授權內）。

**4. Historical IV UI hierarchy**：查證 `IvHistory.tsx`／
`SpreadSummary.tsx`／`IvTrend.tsx` 目前結構後發現，**page 層級順序
已經符合需求方要的階層**（SIG-02／SIG-03 上一輪已經做到）：
`SpreadSummary`（Spread IV Gap，Current／Percentile／Δ4w／Chart／
涵蓋小字）→ `IvTrend`（買／賣腿次要資訊）→ `IvAdvanced`（預設收合，
Normalized Skew／z-score／diagnostics 三級資訊）。唯一的落差在
**卡片內部**：`SpreadSummary`／`IvTrendCard` 的桌面版把 Chart 排在
Percentile／Δ4w**之前**，跟需求方要的 Current→Percentile→Δ4w→Chart
順序不符；手機版（`iv-compact-head`＋`iv-compact-stats`）已經是
Current→Percentile→Δ4w→Chart 的正確順序。建議：桌面版對齊手機版
既有順序（純 JSX 元素重排，不改資料流、不改元件介面）。

**建議下一步**：percentile 與 diagnostics 兩項核心正確性疑慮已收斂，
無殘留邏輯 bug；updating lock 與 UI hierarchy 範圍明確、風險低。
**尚有兩個需要需求方裁決的「產品行為」問題**（詳見本輪回報），其餘
（diagnostics 語意分級的實際分類表、UI 排序調整方式）待裁示後即可
`/to-spec`。本輪未開票、未動 production code。

**需求方裁示（2026-08-25，回覆回報#030）**：percentile 採 A(a)——
維持現行演算法完全不變，只加一句說明文字，不得使用「異常」「離群」
「貴」等字眼；~~額外要求 spec 必須把「production 真資料 cross-check」
獨立列為驗收項~~（**⚠ 這半條已於同日稍後被需求方推翻、整個工作流
砍掉，見下方「Owner Decision — Percentile Validation Scope」；
percentile 採 A(a) 那半仍然有效**）。Diagnostics 裁示採「engineering
observability != user-
facing error state」——四個候選事件（staleness=1 日、backfill 進行中
的 metrics count=0、市場假日 no-data、reanchor out-of-grid 但功能
正常）不得再讓一般使用者誤認故障，但不得刪除或吞掉底層診斷能力。
Updating lock 明確要求恢復灰化＋不可點入，不改 Refresh Run 觸發規則
／Continuation／Partial Success。Desktop hierarchy 維持 #030 建議
（對齊手機版 Current→Percentile→Δ4w→Chart）。

**`/to-spec` 已發佈——issue #198**（`ready-for-agent`）：五項工程
決策逐一寫成明確 Implementation Decisions／Acceptance Criteria：
- Percentile：`ivtrend.py`／`ivreconstruct.py`／`ivspread.py` 零改動；
  新增純格式化說明文字＋banned-word 檢查
- ~~Production cross-check：獨立驗收項……~~ **⚠ 這一條已於 2026-08-25
  被需求方裁示整個砍掉、不再有效**——spec #198 本文與對應票務皆已
  更新，理由見下方「Owner Decision — Percentile Validation Scope」。
  這行保留只為說明本紀錄區的演進，**不是待辦、不得據此重開票**
- Diagnostics：新增獨立於既有 `severity` 的 `user_facing` 布林欄位
  （`DiagnosticEvent` 新欄位），`severity` 本身連同 `/api/diagnostics`
  ／Settings 頁完全不受影響、繼續完整顯示；四個覆寫點各自用該站既有
  就拿得到的資料計算（staleness 改成交易日感知，非單純日曆天；
  legacy metrics count=0 綁 `backfill_pending`；backfill 假日 no-data
  維持既有「不維護假日表」限制下唯一可行的處理；reanchor 只在真的
  導致 Normalized Skew count=0 時才算 user-facing）；預設值＝鏡射既有
  `severity`，只有這四個明確覆寫點例外，避免任何未來新事件源意外被
  靜默降噪
- Updating lock：復用既有 `compact-card-tap` 攔截點擊的既有機制
  （原本只服務批次選取模式），沿用 `styles.css` 註解裡記載的
  pre-P1-b 視覺樣式（`opacity`／`pointer-events`）
- Desktop hierarchy：`SpreadSummary.tsx`／`IvTrend.tsx` 桌面分支純
  JSX 元素重排，不改 props／資料流／圖表幾何

四項工作流彼此獨立、無相依關係，可任意順序或平行施工。本輪 `/to-spec`
到此為止，未 implementation、未開 PR、未 merge master。

**`/to-tickets` 完成（2026-08-25，需求方核准拆票方案後發佈）——8 張
子票 #199–#206，全部為 #198 的 GitHub native sub-issue**：

- **PC-01** [#199] Percentile 說明文字（演算法零改動）——無依賴
- **PC-03** [#201] Diagnostics `user_facing` 軸（expand，行為零變更）——無依賴
- **PC-05** [#202] Updating card 恢復鎖定（灰化＋不可點入）——無依賴
- **PC-06** [#203] Desktop Historical IV 卡片資訊順序對齊手機版——無依賴
- **PC-04** [#204] Diagnostics 四項 user-facing 分類覆寫——被 #201 擋
- **PC-07** [#205] 全面回歸與最終驗收——被 #199／#204／#202／#203 擋
- ~~**PC-02** [#200] Production cross-check 腳本~~ ／
  ~~**PC-08** [#206] Production cross-check 實跑~~——**2026-08-25
  需求方裁示整個工作流砍掉，兩張皆已 `not_planned` 關閉**（見下方
  「Owner Decision」）

**兩個拆票決策（需求方核准，仍然有效）**：
1. **PC-03／PC-04 刻意拆開**：PC-03 是零行為變更的「加軸」（預設值鏡射
   既有 `severity`，驗收就是全套既有測試原樣通過），PC-04 才是全部
   判斷所在。拆開把「加欄位有沒有弄壞既有東西」跟「這四條分類對不對」
   兩種風險隔離——沿用 T01–T13 一路的既有慣例（Refresh Run 拆三張、
   IV pipeline 拆兩張同一個理由）。
2. **PC-04 的四條覆寫不再細拆**：四條都在同一個模組、同一個測試檔、
   每條只有幾行加兩三個測試，拆成四張只會製造四張互碰同一個檔案的
   票，隔離不到東西。

（原第 2 條「PC-08 的 blocking edge 只掛 PC-02」隨該工作流一併作廢。）

### Owner Decision — Percentile Validation Scope（2026-08-25）

**需求方裁示：Production Percentile Cross-check 整個工作流砍掉。**
#200、#206 皆以 `not_planned` 關閉（#200 的 `ready-for-agent` 標籤
一併移除，避免被誤認為還可以抓來做）；#205 移除 #200 blocker 與
「production cross-check 尚未完成」那條 AC；spec #198 本文已重寫，
移除全部相關 Solution／User Stories／Implementation Decisions／
Testing Decisions 段落，並新增同名章節存證。

需求方已接受目前 Historical IV percentile 的計算契約與回報#030
correctness audit 的結論。本輪真正要解決的產品問題**不是**「重新
證明 percentile 整條 production data pipeline 正確」，而是「目前
percentile 數字對一般使用者不夠直覺，需要更好的文字解釋與資訊呈現」
——那由 #199 負責。

因此：**不**建立額外 production percentile validation CLI、**不**建立
獨立 cross-check subsystem、**不**要求抽查 5–10 張 production
contracts 作為交付條件、**不**保留成 deferred ticket／future
blocker、**不**因為 #200／#206 被砍而建立替代票完成同一件事。

**這不是因為「驗證做不到」或「先延後」。** 這是明確的產品／工程
取捨：**該驗證對目前需求的邊際價值不足，會造成不必要的 validation
infrastructure 與測試複雜度，屬於 over-engineering。**

已審查完畢並經需求方接受：公式、exact-contract identity、一年
window、valid observation handling、Spread Gap common-date
alignment、independent arithmetic check。需求方接受這個 confidence
level。

**除非未來出現具體 evidence 指向 percentile correctness bug——API 與
UI 數字不一致、明確可重現的 contract rank 錯誤、historical series
混入錯誤 contract、使用者提供可證明錯算的實例——否則不要再次主動
建立 production percentile cross-check 工作流。**

**本輪剩餘正式施工範圍與建議順序**：
`#199 → #201 → #204 → #202 → #203 → #205`

**施工前查證到的三個關鍵細節**（寫在這裡避免施工時重查）：
- `DiagnosticEvent` 是單純 dataclass；`emit()` 用 `**context` 收其餘
  關鍵字，**`user_facing` 必須當具名參數加**，否則會被吸進走欄位
  白名單的 `context`、被靜默丟棄
- `backfill_pending` 與 `_emit_metrics`／`_emit_reanchor_summary` 在
  `build_iv_history()` 同一個 scope 內，四個覆寫點需要的資料**都已經
  在手邊**，不需要新增任何抓取或狀態
- pre-P1-b 的卡片鎖定樣式（`pointer-events: none; opacity: 0.45`）在
  `styles.css` 註解裡有記載，原始 commit `098b3b9`（#136）可查

**施工開始（2026-08-26 `/implement`，依核准順序連續施工、不中途停）**：

- **PC-01**（#199）— Percentile 說明文字：三個家族（買／賣腿 IV、
  Spread IV Gap、Normalized Skew）的百分位數字旁各自新增一句常駐可見
  的說明——`IV_PERCENTILE_EXPLANATION`（`IvTrend.tsx`）／
  `GAP_PERCENTILE_EXPLANATION`（`SpreadSummary.tsx`）／
  `SKEW_PERCENTILE_EXPLANATION`（`IvHistory.tsx`），皆為 export 的
  純字串常數，緊接在各自的 percentileCaption 之後（桌面／手機兩種
  版面皆插入，不影響既有合併行為）。Normalized Skew 沿用「偏斜」語彙
  不套「IV」字樣（AC 明文要求）；Spread IV Gap 措辭刻意用「共同歷史
  期間」而非「近一年」——這個家族的視窗是兩張合約共同存在的歷史期間，
  可能短於一年（`shared_history_span_days` 既有語意），照實講比套用
  統一樣板更誠實。Normalized Skew 的百分位本來就位於預設收合的
  Advanced／Diagnostics 區塊（SIG-02／#173 既有裁示），這裡不擴大
  範圍把它搬回主畫面——AC「常駐可見」的落地方式是「展開 Advanced 後
  不必再多點一次」，不是推翻既有的資訊階層決策。演算法／裁窗／
  exact-contract 身份規則／有效觀測篩選／Spread IV Gap 共同日期對齊
  規則全部零改動（`git status` 確認零 Python 檔案變動）。
  新增 `src/percentileCopy.test.ts`（仿 `tests/test_redlines.py`
  禁詞掃描慣例）：三個常數各自驗證不含 {異常, 離群, 貴, 便宜, 昂貴,
  推薦, 建議} 及直接英文對應、講清楚定義、提到單日讀數會隨市場報價
  波動。既有 `IvTrend.test.tsx` 兩條資訊順序測試（桌面／手機的
  class 陣列斷言）因新增一個 caption 節點而更新，其餘既有 facts-only
  紅線測試（`IvHistory.test.tsx` 的評價字眼／預測語句掃描）原樣通過、
  未鬆綁。前端 typecheck／648 條 Vitest／build 全綠；Playwright
  Historical IV／Spread IV Gap 相關 26 條（iPhone＋Desktop）全綠。
  **後端全套回歸確認**：4 條既有測試失敗（`test_api_filters.py` 三條、
  `test_service_fetch.py` 一條）——經 `git stash` 比對在完全未施工的
  基準點上同樣失敗（symbol「XYZ」的 `fetch_and_save` 沒有 mock 住
  `cboe.fetch_chain`，本輪 sandbox session 對 Cboe 的網路連線恰好
  connect 成功、回傳當下真實時間戳，跟寫死的 fixture 時間戳對不上；
  另外三條與此連動），確認為施工前既有、與本輪任何一張票皆無關的
  環境依賴性 flake，非本票造成的回歸，未嘗試修正（不在 spec #198
  範圍內）。

- **PC-03**（#201）— Diagnostics `user_facing` 軸：`DiagnosticEvent`
  新增必填欄位 `user_facing: bool`（刻意不給 class-level 預設值——
  真正的預設規則只活在 `emit()` 一個地方，避免兩處邏輯漂移；直接
  建構 `DiagnosticEvent` 的既有測試因此逐一補上顯式值，鏡射各自的
  `severity`，斷言本身一行未動）。`diagnostics.emit()` 新增具名參數
  `user_facing: bool | None = None`，省略時套預設規則（`severity` 為
  warning／error 視為 true，info 視為 false）——具名參數確保它不會被
  `**context` 收集吸走、被欄位白名單靜默丟棄（AC 明文擔心的那個坑）。
  `main.py` 的 `_emit` closure 與 `ivpipeline.EmitFn` 的呼叫慣例文件
  同步補上這個參數（純文件／簽章澄清，PC-03 本身沒有任何呼叫端傳入
  覆寫值，PC-04 才會用到）。`postgres.py`：`diagnostics` 表新增
  nullable 欄位 `user_facing`（走 `_MIGRATIONS`，不改 `_SCHEMA`——沿用
  既有「建表與遷移分開送」慣例）、insert／select 兩條路徑同步接上，
  讀回時對舊列（遷移前寫入、欄位為 NULL）套用跟 `emit()` 相同的規則
  補值，新舊列讀回行為一致。`memory.py` 不需改動（dataclass 物件本身
  攜帶這個欄位）。前端：`DiagnosticEvent` 型別新增 `user_facing:
  boolean`；`IvHistory.tsx` 的 `notableEvents` 過濾條件從
  `severity==="warning"||"error"` 改為 `user_facing===true`——PC-03
  的預設規則與舊過濾條件逐一等價，這一行改動因此是零行為變更；
  `/api/diagnostics` 端點（`dataclasses.asdict()` 直接吐全部欄位）與
  Settings／Diagnostics 頁（`Diagnostics.tsx`／`DiagnosticDetail.tsx`
  只讀 `severity`）完全不受影響、未改一行。契約樣本
  `contracts/iv_history_sample.json` 重產（事件數 28→26 為既有已知的
  跨日期非決定性，同一天內重複執行两次皆為 26，已驗證非本票造成）。
  新增測試：`test_diagnostics.py` 三條（預設鏡射三種 severity、顯式
  覆蓋、`user_facing` 不落入 `context`）；`test_storage_contract.py`
  一條 round-trip（true／false 兩個方向都要能存活過 Postgres）；
  frontend `Diagnostics.test.tsx`／`IvHistory.test.tsx` 的既有假體
  工廠函式（`event()`／`diagEvent()`）改為動態鏡射 `severity`（而非
  寫死常數），沿用同一套「省略時鏡射」哲學，既有呼叫端（含
  `severity: "info"` 覆寫）因此零修改就自動得到正確值；e2e
  （`smoke.spec.ts`／`desktop.spec.ts`）三處手造的 diagnostics 假體
  補上 `user_facing`——這些不受 TypeScript 檢查（純 JSON 假體），漏補
  會讓依賴 iv-history 診斷面板觸發的既有 e2e 案例失去觸發條件而非
  型別錯誤，已逐一核對三處足夠。全套回歸：後端 pytest 無新增失敗
  （與 PC-01 記錄的同一組 4 條既有環境依賴性 flake 完全相同）；前端
  typecheck／648 條 Vitest／build 全綠；Playwright Historical
  IV／Diagnostics／Copy 相關 29 條（iPhone＋Desktop）全綠。

- **PC-04**（#204）— Diagnostics 四項 user-facing 分類覆寫：只動
  `option_chaser/ivpipeline.py` 四個 emit 函式，每處都只加
  `user_facing=` 這一個具名參數、`severity` 計算式逐字未動（測試
  逐一鎖住兩者同時成立）。**staleness**：新增
  `_most_recent_trading_day_before(day)`（只處理週末，沿用既有
  `_is_weekend`，不新增假日表）；`obs_date >= 那個交易日` 視為預期
  中的正常過渡態（含跨週末），`user_facing = not benign`。**Legacy
  metrics count=0**：`_emit_metrics()` 新增參數 `backfill_pending:
  bool = False`（`build_iv_history()` 既有的 `legacy_backfill_status()`
  結果直接傳入，不新增任何抓取），`user_facing = count==0 and not
  backfill_pending`——只影響 Legacy 家族自己的 metrics，`_emit_leg_
  stat_metrics()`（Exact-Contract 家族逐腿統計量）完全未觸碰。
  **backfill 批次摘要**：`user_facing = bool(aborted_on)`——warning
  唯一成因是交易日撲空且未中止時為 False（本站不維護美股假日表的
  既有已接受限制，跟 `days_no_data_expected`／`_is_weekend` 同一個
  取捨），中止（額度用盡／vendor 失敗）時無論是否同時有撲空一律
  True。**reanchor 覆蓋率**：`user_facing = total > 0 and in_grid ==
  0`——只有整段快取歷史全部落在網格外才顯示，部分覆蓋不顯示；真的
  顯示時 Normalized Skew 的中性文案（`metricCaption()` 既有的「沒有
  歷史資料」）與 `InlineDiagnostics` 的 `variant="info"`（非紅色阻斷
  樣式，`.iv-diagnostics-summary-info` 既有 CSS 早已是中性語氣）兩者
  都是既有架構、不需要任何新程式碼即滿足這條 AC，純檢視確認。
  `_emit_contract_history_telemetry`／`_emit_reconstruction_ledger`／
  `_emit_vendor_benchmark`／`_emit_leg_stat_metrics` 四個函式完全未
  觸碰（維持預設規則，reconstruction 全零成功與 vendor 真失敗依然
  對使用者可見）；施工中未發現其他行為類似、需要另行裁決的診斷事件源。
  測試：`test_api_iv_history.py` 對 reanchor／metrics／backfill 三組
  既有測試逐一補上 `user_facing` 斷言（與既有 `severity` 斷言並列，
  證明兩者互相獨立）；新增 `test_metrics_zero_count_is_not_user_
  facing_while_backfill_is_still_pending`（pending 情境專屬）；新增
  三條直接呼叫 `_emit_staleness()`／`_most_recent_trading_day_before()`
  的純函式測試（HTTP 端點層級的 `today` 是真實系統時鐘、無法穩定
  構造「今天是星期幾」，比照既有 `test_the_backfill_and_reanchor_
  summaries_take_no_free_text_vendor_params` 直接匯入私有函式的既有
  慣例）——正常跨週末不可見、真的跳過交易日則可見、新鮮觀測不可見。
  前端 `IvHistory.test.tsx` 新增兩條：`severity=warning`＋
  `user_facing=false`（PC-04 良性覆寫的形狀）不觸發面板；
  `severity=info`＋`user_facing=true` 觸發面板——雙向證明過濾條件是
  獨立軸，不是 severity 的別名。契約樣本重產，4 筆 metrics 事件（該
  fixture 的 Legacy 家族 backfill_pending 為 true）`user_facing`
  正確從 true 翻成 false，親眼核對非本票造成的意外行為。全套回歸：
  後端 pytest 無新增失敗（同一組 4 條既有 flake）；前端 typecheck／
  650 條 Vitest／build 全綠；Playwright Historical IV／Diagnostics
  相關 29 條（iPhone＋Desktop）全綠。


- **PC-05**（#202）— Updating card 恢復鎖定（灰化＋不可點入）：
  `ScenarioList.tsx`（桌面）／`CompactScenarioList.tsx`（手機）的卡片
  `updating` 為真時新增 `locked` class（`.compact-card.locked { opacity:
  0.45; }`＋`cursor: not-allowed`，`src/styles.css`）；`href` 仍保留
  （長按複製／螢幕閱讀器／可及性語意不變），實際擋點擊靠 `<a>` 的
  `onClick`——`updating` 時 `e.preventDefault()`，比照既有 `selectMode`
  攔截手法。**優先序**：`selectMode` 判斷在前（AC：既有批次選取互動
  不受影響，鎖著的卡片一樣勾得起來），`updating` 判斷在後（僅在不是
  選取模式時才擋導航）。刻意不用 `pointer-events: none`——那會讓
  Playwright 一般 `.click()` 判定元素不可互動而失敗／需要 `force:
  true`，改用純 `opacity` 讓點擊事件正常發生、由 `preventDefault()`
  擋下導航，E2E 因此驗證得出「按下去真的沒有導航」而非「按不下去」。
  詳細頁（`ScenarioDetail.tsx`）本身的「本輪刷新排隊中或進行中」提示
  維持原樣不動——這張票的鎖定只針對清單卡片，不影響使用者已經打開的
  detail pane（AC 明文的跨劇本隔離：清單上其他劇本鎖定中不影響目前
  詳細頁）。

  測試：Vitest 兩個元件測試檔重寫「更新中徽章」describe block——鎖定
  class、`window.location.hash` 點擊前後不變（jsdom 對帶 `href` 的
  `<a>` 真的會做同頁 hash 導覽，除非 `preventDefault()`，這給了一個
  可靠、不依賴瀏覽器特有行為的斷言）、對照組（非更新中卡片點擊正常
  導航，證明攔截確實生效而非 jsdom 本來就不會跳轉）、批次選取模式下
  鎖定卡片仍可勾選。`App.test.tsx` 既有兩條測試更新斷言（`locked`
  class 而非「全程可點」），新增桌面 master/detail 情境的跨劇本隔離
  測試（s2 鎖定中不影響正在看的 s1 詳細頁內容或提示）。E2E 各平台新增
  一條「鎖定卡片點下去路由不變」（先驗證鎖定時點擊不導航，再驗證解鎖
  後同一顆連結點得進去，排除「這個候選結構上到不了詳細頁」的干擾）。

  **施工中發現並修正兩個真實 e2e 回歸**（皆為既有測試的路由假設在
  「更新中卡片全程可點」的舊行為下才成立，PC-05 恢復鎖定後現形，
  不是本票新引入的邏輯錯誤）：(1) `smoke.spec.ts` 「返回劇本庫時停在
  原本捲動的位置」測試沒有覆寫 `refresh-run` 路由、吃 `test.
  beforeEach` 的預設空氣回應（`results: []`），10 個劇本因此永遠拿不到
  自己的結果、永遠卡在「更新中」＋鎖定，點不進要測的詳細頁——補上正確
  的 `refresh-run` 路由（讓全部 10 個劇本各自成功落地）；(2) 「久未
  刷新的資料標成舊資料」測試用 `getByText("舊資料")` 廣泛比對，撞上
  更新中列項既有的 sr-only 文字（「更新中；查看…顯示上一輪的舊資料」，
  這段文字本身早於 PC-05 存在，不是本票新增）在開站刷新進行中的短暫
  窗口裡恰好也含「舊資料」子字串，屬既有、非本票引入的潛在 race——
  改用更精確的 `.tag.warn` 選擇器 scope 回真正的舊資料徽章本身，不受
  巧合的字串重疊影響。兩處都已用多次重跑確認修正後穩定（PC-05 施工
  前的基準點以 `git stash` 核對過，兩個問題在基準點原本就會被舊行為
  掩蓋、不會被觸發，證實是本票恢復鎖定後才現形的既有缺口，不是新
  程式碼寫錯）。全套回歸：後端 pytest 無新增失敗（同一組 4 條既有
  flake，本票零 Python 檔案變動）；前端 typecheck／657 條 Vitest／
  build 全綠；Playwright 全套 90 條（iPhone 56＋Desktop 34）連續兩輪
  穩定全綠。

- **PC-06**（#203）— Desktop Historical IV 卡片資訊順序對齊手機版：
  `IvTrend.tsx`（`IvTrendCard` 桌面分支）／`SpreadSummary.tsx`
  （`SpreadSummary` 桌面分支）純 JSX 元素重排——現值 → 百分位 → Δ4w
  → 走勢圖（AC 逐字列出的四項），PC-01（#199）新增的百分位說明句排在
  Δ4w 之後、走勢圖之前（跟手機版「percentile+Δ4w 合併行 → 說明句 →
  走勢圖」同一個相對位置，手機版分支完全未動）；涵蓋時間／backfill
  說明維持在走勢圖之後。頁面層級順序（Spread Summary → 買／賣腿卡片
  → Advanced／Diagnostics 收合區）、圖表資料／scrubber 互動／
  responsive 高度切換／任何 Historical IV 計算或元件 props 完全不變
  ——純粹重排既有 JSX 元素，零新增邏輯。
  測試：兩個檔案的「資訊順序（桌面）」describe block 改用
  `compareDocumentPosition`（沿用 `IvHistory.test.tsx`／`App.test.tsx`
  既有手法，AC 明文要求）鎖住新順序——現值早於百分位、百分位早於
  Δ4w、Δ4w 早於走勢圖，另外一條鎖住說明句夾在 Δ4w 與走勢圖之間；
  `SpreadSummary.test.tsx` 新增手機版對照組（合併行 → 說明句 → 走勢圖
  順序不變）。PC-01 起兩個檔案各自一條斷言「說明緊接在百分位數字之後」
  的既有測試因為 Δ4w 現在插進中間而失真，改成只驗證看得到（不必展開）
  ——真正的順序保證交給新的 DOM 順序測試。全套回歸：本票零 Python
  檔案異動，後端不重跑；前端 typecheck／661 條 Vitest／build 全綠；
  Playwright 全套 90 條（iPhone 56＋Desktop 34）全綠，含既有 SIG-04
  桌面／手機紅線（頁面層級順序）與 PC-05 新增的鎖定卡片測試皆未受
  影響。
- **PC-07**（#205）— 全面回歸與最終驗收（本輪最後一張票，純驗證、
  無新功能程式碼）：逐項核對 spec #198 全文（Problem Statement／Owner
  Decision／Solution／23 條 User Stories／四節 Implementation
  Decisions／Testing Decisions／Out of Scope），全數落實、無缺口、
  無 scope creep：
  - **紅線核對**：`git diff` 確認 `ranking.py`／`filters.py`／
    `valuation.py`／`ivtrend.py`／`ivreconstruct.py`／`ivspread.py`／
    `ivhistory.py` 全部逐位元未動；`option_chaser/` 本輪唯一改動檔案
    是 `ivpipeline.py`，逐行核對只有 `user_facing=` 新增與註解，零
    `severity` 數值改動、零計算邏輯改動；`test_redlines.py`／
    `test_selection_regression.py` 零改動；全專案 `tests/`／
    `src/*.test.*` 掃過每一處被移除的既有斷言（後端 0 條、前端 5 條）
    ——後者逐條核對皆為「原地重構＋等價或更強斷言」而非鬆綁覆蓋率。
  - **PC-07 施工中發現並補上的一個真測試缺口**：spec Testing
    Decisions 明列「a genuine vendor failure and a total reconstruction
    failure both still `user_facing=True`」——vendor failure 那半（Legacy
    家族 quota abort）已由既有
    `test_backfill_abort_is_visible_in_the_summary_event` 覆蓋，但
    Exact-Contract 家族「整段序列零可用點」那半
    （`test_reconstruction_ledger_is_a_warning_when_nothing_is_usable`）
    先前只驗證 `severity`，沒有直接斷言 `user_facing`——已補上一行
    `assert events[0]["user_facing"] is True`。DG-04 風格的「單一
    全帳本測試同時涵蓋四項覆寫、集中證明 severity 不受影響」則判斷
    維持現狀不強行合併：severity 不受影響這件事已經在四項覆寫各自的
    既有測試裡逐一斷言（`test_reanchor_summary_*`／
    `test_metrics_*`／`test_backfill_abort_*`／`test_staleness_*`
    皆同時斷言 `severity` 與 `user_facing`），而 staleness 覆寫在
    HTTP 層無法控制「今天」（既有限制，走純函式層級測試），backfill
    覆寫又需要獨立的 `IvBackfillRun` 狀態（同一個 `db` fixture 內
    兩種 backfill_pending 狀態無法在同一個 request 並存），勉強拼成
    一個物理上的單一測試函式只會犧牲既有測試檔案「一個場景一個函式」
    的既有可讀性慣例，換不到新的保證。
  - **User Stories 1–23 逐條核對**：1–4（percentile 說明文字三家族＋
    演算法零改動）由 PC-01 落實；5–12（四項覆寫＋兩個「維持原樣」的
    對照組）由 PC-04 落實，其中 #9／#10 的「部分覆蓋不示警／全覆蓋
    失效時沿用既有『沒有歷史資料』中性文案、不新增視覺嚴重度」由
    `_emit_reanchor_summary` 覆寫＋既有（#133）`metricCaption()` 呈現
    層共同滿足，本輪未新增任何新視覺樣式；13–14（`severity` 完整保留
    ＋覆寫條件明確可測）由 PC-03／PC-04 的 explicit named parameter
    設計滿足；15–19（鎖定／自動解鎖／三個觸發規則不變／Partial
    Success 不受影響）由 PC-05 落實，#17／#19 由既有（P1-b 時期）
    `updatingIds` 狀態管理機制原樣保留佐證（PC-05 只加 CSS class 與
    onClick 攔截，未觸碰 `runBatch()` 的完成偵測與摘要計算）；20–22
    （桌面卡片順序對齊＋頁面層級順序不變）由 PC-06 落實；23（範圍
    嚴格限定四項決策，不夾帶 V2／N-leg／架構重構）由本輪 `git diff`
    範圍核對確認。
  - **Out of Scope 核對**：無 production percentile cross-check 相關
    任何檔案／CLI／ticket（依 Owner Decision，#200／#206 維持
    `not_planned`）；percentile 公式／一年窗／exact-contract identity／
    valid-observation filtering／Spread Gap 對齊規則零改動；未新增
    平滑化或 outlier 指標；未新增美股假日曆；未觸碰 ScenarioDetail
    自身在背景刷新時的既有行為；未新增新的視覺嚴重度分級；無 V2／
    N-leg／Refresh Run 架構／`main.py`／`service.py` 重構。
  - **全套回歸**（三次獨立驗證，非單次僥倖綠燈）：後端 pytest（記憶體
    ＋本機真實 Postgres 16 雙後端）——與本輪其餘六票完全相同的既有
    4 條失敗（`test_api_filters.py` 三條、`test_service_fetch.py` 一條，
    皆為此 sandbox 網路環境對虛構 symbol「XYZ」意外允許真實連線所致的
    既有環境依賴性 flake，經多次 `git stash` 比對確認在本輪施工前的
    基準 commit 上就已存在，與本輪任何一張票的改動無關），PC-07
    新補的一行斷言通過、零新增失敗；前端 `tsc --noEmit` 乾淨、
    `vite build` 成功；Playwright 全套 90 條（iPhone 56＋Desktop 34）
    全綠。
  - **交付**：commit＋push 到 `claude/implement-tfm9oa`，依專案規則
    不開 PR、不 merge master。

**spec #198（PC-01、PC-03～PC-07，issues #199、#201～#205）全數完成，
PC-07 驗收通過。** #200／#206（production percentile cross-check）
依需求方 2026-08-25 Owner Decision 以 `not_planned` 關閉，不重啟、
不建替代票。下一步：等需求方以真機／production 檢視本輪四項成果
（percentile 說明文字、Diagnostics 靜音化、Refresh Run 鎖定復原、
桌面卡片順序）；依專案規則全部子票做完才開 PR，中途不主動開。

### 真機驗收直接施工（2026-08-26，無 GitHub issue，直接下工單處理）

需求方對 spec #198 的成果真機驗收後，發現兩個要在開 PR 前修正的小
問題，明確指示直接施工修正、不重新 `/grill`／`/to-spec`／拆新一輪
tickets，本輪只處理下列兩項、禁止 scope creep。

**問題 1：Refresh Run 恢復「逐張完成、逐張可用」（commit `ca75b5f`）**
——PC-05（#202）復原的鎖定機制與 C1 Refresh Run 批次架構（T06／#190）
疊在一起後，真機上出現需求方不要的行為：backend 雖然批次處理，但
前端要等整輪全部完成才一次把所有卡片解鎖／更新。

**診斷**：前端 `runBatch()`（`App.tsx`）其實**早就**逐批套用回應
（每次 Continuation 迴圈拿到一次 HTTP 回應，就立刻更新那批的
`rows`／解除那批的 `updatingIds`，不等迴圈跑完），這件事本身沒有
bug。真正的成因在後端：`refresh_run` 端點過去只有一個提前返回條件
——45 秒的 `REFRESH_RUN_BUDGET`（T07／#193），對常見規模（十幾個
劇本、少數幾個 distinct symbol）而言遠遠不會觸發，所以典型情況下
**整批一次就在單一 HTTP 回應裡做完**，前端就算逐批套用，也只有
「一批」可套用，看起來自然是「整輪跑完才一次全部解鎖」。

**修法**：新增 `REFRESH_RUN_GROUP_LIMIT`（預設 1，`create_app()` DI
注入方式與既有 `refresh_run_budget` 完全同構），單次回應最多完成
一個 symbol 分組（ADR-0001 既有的去重單位）就回傳，其餘分組原樣進
`remaining`——前端既有、不必改動的 Continuation 迴圈因此會逐組拿到
結果並立即解鎖。分組本身不會被這個限流從中間切開（檢查點在分組開始
前，不是分組內部），同一個 symbol 的多個劇本仍共用一次抓取、一起
送達（這是分享同一次抓取結果的誠實後果，不是退步）；不同 symbol
天生各自獨立分組，逐一送達。三個既有的 Refresh Run 優點原封不動：
未退回 N 個獨立 serverless invocation、symbol chain 去重範圍不變
（仍是單一 invocation 內）、request-scoped connection（PERF-01）與
Continuation／Partial Success 機制都沒有被觸碰。

測試：`tests/test_api_refresh.py` 新增
`test_refresh_run_three_distinct_symbols_unlock_one_group_at_a_time`
（A／B／C 三個不同 symbol，逐組完成，C 那組刻意安插一個抓取失敗，
證明失敗不擋 A／B 已經落地的結果）；三個既有測試因新預設值改變
假設（原本斷言「多 symbol 一次做完」）而改用新增的
`_run_to_completion()` 輔助函式（循環呼叫到 `remaining` 清空，只驗
最終結果不依賴幾次往返）——`test_refresh_run_deduplicates_chain_
fetch_within_the_same_symbol`／`test_refresh_run_partial_success_
one_symbol_failing_does_not_block_another`／
`test_refresh_run_continuation_resumes_and_matches_a_single_pass`
（後者的「一次做完」比較基準改顯式注入
`refresh_run_group_limit=10`，代表「真的不分組限流」的對照組，不再
是預設值自然产生的副作用）。`test_refresh_run_a_realistic_batch_
completes_in_a_single_call` 整條重新命名為
`..._now_completes_progressively_not_in_one_call`，斷言方向反過來：
第一次回應只完成 4 個（第一個 symbol 分組），`remaining` 有 8 個；
`_run_to_completion` 後仍然 12 個全部成功——這正是本票要修的那個
行為，舊斷言就是舊 bug 本身的證明。

前端：`App.test.tsx` 新增 A／B／C 三劇本逐張解鎖測試（B 刻意失敗，
驗證失敗只影響它自己、不擋 C）；Playwright 手機（`smoke.spec.ts`）
與桌面（`desktop.spec.ts`）各新增一條同款三階段驗收測試，用
`scenario_ids` 長度判斷第幾輪、各自延遲讓中間鎖定狀態真的看得到，
對齊需求方逐字列出的驗收情境（A 先完成解鎖、B/C 仍鎖定；B 完成
不必等 C；partial failure 只影響該 Scenario；手機與桌面皆成立）。

**問題 2：Percentile 說明文字改寫為白話句（commits `bc8b792`／
`f6be5bd`）**——PC-01（#199）新增的三句常駐說明文字雖然技術上正確，
需求方真機閱讀後仍覺得不像一般使用者能快速理解。三個家族
（`IvTrend.tsx::ivPercentileExplanation`／`SpreadSummary.tsx::
gapPercentileExplanation`／`IvHistory.tsx::skewPercentileExplanation`）
從靜態字串常數升級為函式，直接把「第 N 百分位」翻譯成一句話、把
N 帶進句子裡——例如「現在的 IV 比過去一年大約 87% 的有效歷史觀測
都高。單日數字可能隨市場報價波動。」——不再要求使用者自己把
「百分位」這個統計學名詞在腦中換算成「比例」。數字沿用旁邊既有
`percentileCaption`／`metricCaption`（本輪不動）完全相同的
`Math.round(percentile*100)`，兩處讀到的數字保證一致；三個新函式
之間的這份重複由 code review 抓到後收斂成共用的
`IvHistory.tsx::roundPercentile()`（只給這輪新增的三個函式共用，
刻意不回頭改既有 caption 函式——那屬於「不動任何 percentile 計算」
的既有程式碼）。Spread IV Gap 維持「共同歷史期間」措辭（視窗可能
短於一年，非「近一年」樣板）、Normalized Skew 沿用「偏斜」語彙、
不套「IV」字樣——皆延伸既有裁示，非本次新裁決。沒有歷史觀測時
誠實說「目前沒有足夠的歷史觀測可以比較」，不硬套假數字。只改文字：
percentile 演算法／裁窗／exact-contract 身份規則、圖表、scrubber、
手機／桌面 layout、diagnostics 全部不動。

測試：`percentileCopy.test.ts` 改為呼叫函式（不再讀靜態字串），
涵蓋禁詞掃描、數字內嵌、「都高」句型且不再出現「百分位」字樣、單日
波動提醒、簡短（兩句話之內）、null 情況誠實留白、三家族視窗措辭
差異、與既有顯示數字的四捨五入一致性；`IvTrend.test.tsx`／
`SpreadSummary.test.tsx`／`IvHistory.test.tsx` 既有的 DOM 定位斷言
同步改用新文案的正則（用 `\d+%` 一般化，不逐一硬編每條測試各自的
百分位數字）。

**`/code-review` 已執行（Standards＋Spec 兩軸平行）**：Standards 軸
零 hard violation；抓到三個新函式的 `Math.round(percentile*100)`
重複（已如上收斂成 `roundPercentile()`）、以及建議把兩個不相關的
修正拆成獨立 commit（已照做，兩個修正各自獨立 commit，未合併）。
Spec 軸零缺漏、零 scope creep；逐項核對 group-limit 分組不會被切開
（檢查點在分組前）、失敗隔離（`fetch_error` 只標記那一組）、三個
說明函式數字換算與旁邊既有顯示逐位元一致；唯一提到的「未測到的
情境」（同一次回應內有多個分組時，其中一組失敗是否擋住下一組）
判斷為既有、本輪未改動的邏輯（`fetch_error` 是 per-group 局部變數，
外層迴圈本來就會繼續），非本輪缺陷。

**全套回歸**（不鬆綁任何既有斷言）：後端 pytest（記憶體＋本機真實
Postgres 16 雙後端）——與 PC-01～PC-07 完全相同的既有 4 條環境依賴性
flake（`test_api_filters.py` 三條、`test_service_fetch.py` 一條，
與本輪改動無關）；前端 `tsc --noEmit`／`vite build` 乾淨、Vitest
670 條全綠（多次全套重跑時，`IvHistory.test.tsx` 一條與本輪完全
無關的既有測試——補建端點失敗後重抓的 `waitFor()`——出現約 2 成
機率的間歇性失敗；用 `git worktree` 拉出本輪施工前的基準 commit
（`69994ba`）反覆對照跑過近 20 次，確認**同一條測試在施工前的基準
上同樣會間歇性失敗、且永遠只在全套平行跑、單獨跑該檔案永遠 100%
通過**——是這個 sandbox 既有的 CPU 資源競爭導致 `waitFor()` 逾時，
不是本輪任何一個修正引入的迴歸，本輪新增的測試沒有一次牽涉在內）；
Playwright 連續兩輪 92 條全綠（iPhone 58＋Desktop 34，含本輪新增
兩條逐張解鎖驗收）。

**交付**：兩個修正各自獨立 commit（`ca75b5f`／`bc8b792`）＋一個
code-review 跟進 commit（`f6be5bd`），已 push 到
`claude/implement-tfm9oa`。依需求方明確指示不開 PR、不 merge
master，等需求方最後一次真機驗收。

**2026-08-26 需求方真機驗收通過，指示「可以了，先 merge 回去吧」**：
開 PR #207（涵蓋自上次 merge master 以來累積的全部工作——Architecture
Review 輪、spec #198、以及本節兩項直接施工修正），merge commit
`459fb4f`。順手清點 GitHub issues：補關 25 張早就做完但忘記關閉的
舊票（spec #124–143、#151、#159、#171、#176 的 parent／子票；#136
標 `not_planned`，已被 Refresh Run 架構取代），確認只剩 #111／#114／
#102／#59 四張因真實 blocker 或需求方尚未裁示而維持 open。詳見檔案
最上方 2026-08-26 版「現況總覽」。

### Strategy-specific valuation metric 研究輪（2026-08-26，`/research`，只研究不施工）

需求方裁示核心產品原則：**不同 strategy 不需要、也不應強迫共用同一套
valuation metric**；跨 strategy 唯一的共同座標是「該 strategy 自己的
metric 目前落在自己歷史分布的第幾百分位」。本輪唯一任務＝逐 strategy
找出那個底層 metric。產出
`docs/research/strategy-valuation-metric-percentile.md`。**未寫
production code、未開 ticket、未設計 UI、未改 percentile 演算法。**

**Step 0 Prior Research Ledger**：既有 27 份研究、17,258 行全數盤點，
26 個問題分級 **ANSWERED 15／PARTIAL 5／OPEN 6**，ANSWERED 一律不重研究。
⚠ 需求方點名的 `candidate-iv-history-proxy.md` **在 repo 不存在**，
最可能是指 `candidate-iv-relative-value.md`。

**三條核心裁定**：

1. **現行出貨的 `Spread IV Gap = Sell IV − Buy IV` percentile 必須停用。**
   引擎實算（真實 TLT LEAPS fixture）：vol level 12%→22% 而 skew 不動時，
   gap 讀數 **0.0% 完全失明**、Ĝ **−44.9% 反向**，而使用者實付 debit
   **+59.9%**；skew 變陡時兩個指標往「更貴」走、價格卻往便宜走。四個純
   vol 衝擊的符號吻合 **0/4**、量級吻合 **0/4**。**根因**：業界「vertical
   ＝純 skew 玩法」預設兩腿履約價相鄰，而本產品實際產生 **W=40（47% of
   spot）**、net vega 是買腿的 **92.3%**，level 分量權重是 skew 的 12 倍
   ——既有研究沒錯，錯在被套用到不適用的幾何上。⚠ **gap 當走勢圖仍有
   價值**，要拿掉的只是 percentile 與「歷史位置」語意。⚠ 這件事 repo
   自己的 `candidate-iv-relative-value.md` §4.3 與
   `historical-rich-cheap-canonical-methodology.md` §11.3 早已明文寫過
   ——**出貨與既有裁決不一致**。
2. **三個 bounded 結構（butterfly／iron butterfly／iron condor）在數學上
   是同一個工具**：`butterfly/(DF·h) = E^Q[tent]`（驗到 5.6e-10）、
   `condor/(DF·W) + credit/(DF·W) = 1`（驗到 1.78e-14）。共用一個公式
   **不違反「不得為整齊硬湊」紅線——no-arbitrage 說它們本來就是同一個
   東西**。統一形式 `M = price/(DF × max_payoff)`，值域 [0,1]，且
   **Cboe BFLY／CNDR 官方 methodology 就是這樣錨定的**【官方文件】。
3. **Straddle 價格 percentile ≡ ATM IV percentile 逐筆等價**
   （`straddle/(DF·F) = 2(2N(σ√T/2)−1)`，嚴格遞增雙射）——**不必反解
   IV**，直接繞開本 repo 已知的 `implied_vol()` 在 LEAPS 與退化 vendor
   IV 上的脆弱性。本輪最強的單一結果。

**核心前提的誠實答案**：跨 strategy percentile 是**「同一種語句」可比，
不是「同一種經濟後果」可比**。Cboe 官方 `VIX_History.csv`（9,258 筆）
實測：**VIX=18 在樣本裡同時當過最便宜與最貴的讀數，509 次**；同一個
VIX 用 126/252/504/756 天窗口算出 10.2/15.4/18.2/35.4，**3.5 倍擺動來自
使用者看不見的參數**。兩條必要條件：全部 strategy 共用同一個回看窗口
且對使用者可見；percentile 必須與原始值並陳。

**三個待需求方裁示點**：(a) bounded structures 用 `M`（有 Cboe 官方先例、
但留 r/q 汙染）還是統一版 `M_VORD`（汙染結構性為零、但無業界先例）；
(b) 回看窗口選多長（本輪找不到可辯護的預設值）；(c) strangle 報一個數字
還是拆 `σ_ATM`／`BF` 兩個。

**誠實缺口**：vertical spread／VORD 那條線**本輪一手原文 0 筆、官方文件
0 筆**，說服力全來自數字可重跑與交叉驗證；**VORD 是本輪自創、無具名業界
先例**（若「符合機構實務」從嚴解釋，目前只有 `M` 滿足）；#111 仍 blocked
故**所有歷史 percentile 的行為主張都未用真實序列驗證過**。

**順帶查證到、與本輪主題正交但需求方應知**：現行排行榜排的是「賠率」不是
「價值」——`ranking.py:151` 的 `spread_baseline_return` 本質是
`width/debit − 1 ≈ 1/p̂ − 1`，由高到低排等於照風險中性機率由低到高排。
**這不是 bug**（「劇本必定成立」前提下選賠率最高是對的），但它結構上不看
劇本成立的機率，與本輪要建的軸互相獨立，文案上必須分清楚。另
`api_app/main.py:84` 的 `_MVP_STRATEGIES = ("bull-call-spread",)`——
委託點名的九個 strategy **今天只有一個有 candidate generator**，其餘八個
的裁定全部是前瞻性的。

**下一步**：等需求方審閱與三個裁示點的方向，**本輪不進 `/to-spec`**。

### Wayfinder：方向性策略擴充（2026-08-27，`/wayfinder`，只畫地圖不施工）

需求方 `/wayfinder` 指示規劃「方向性策略擴充」：使用者面對 4 個
Strategy Family（Call/Put、Vertical Spread、Butterfly、Iron Condor），
backend 可自由增加 subtype 而不使 frontend 膨脹。**本輪只 Wayfind**
——未施工、未開 PR、未進 `/to-spec`。

**地圖＝issue #209**（label `wayfinder:map`），六張子票 #210–#215。
Frontier（可立即開工）：#210／#211／#212；#213／#214 被 #210 擋；
#215 被全部擋。六張**全是 grilling 票**，需需求方親自裁示，
本 session 依 skill 規範不自問自答、不代答。

**Prior Decision / Research Ledger（九條已 ANSWERED，不重新研究）**
最關鍵的三條：

1. **`strategies` 不是新概念，是既有已持久化欄位**——
   `Scenario.strategies: tuple[str,...]`（`api_app/storage/__init__.py:26`、
   `postgres.py:85` `strategies JSONB NOT NULL`），建立與編輯都寫、分析
   路徑都讀，`_MVP_STRATEGIES` 全 repo **只有一個 production 寫入點**
   （`main.py:703`）。**若該行寫入不同 tuple，backend 今天就能跑
   multi-strategy。** 需求方原本的第 4 題（strategy selection 怎麼存）
   因此不需要開票。
2. **Long Call／Long Put 已端到端可跑**，四策略皆有 byte-locked golden
   fixtures。唯一缺口是 `_single_leg_result` 未填 `expiry_top10`
   （刻意 MVP scoping，`service.py:194-200`），導致詳細頁空白。
   **是兩個欄位，不是架構。**
3. **多 family 成本：CPU ~1.5×、network 1×**（實測 372 合約鏈
   218ms→334ms；chain fetch 已提到 per-strategy 迴圈外，且 ADR-0001
   保證 Run 內同 symbol 只抓一次）。**真正 scale 的是 payload：每多
   一個 active spread 策略 +495KB→1001KB，且目前無任何機制 bound 它。**

**五顆已埋好的地雷（現在就存在，非理論風險）**

- **C1 單邊 chain 過濾**（`filters.py:104-105`）：一行讓 Iron Condor／
  Iron Butterfly **結構上不可能**（對面半條鏈在枚舉前就被丟棄），
  且 `FilterReport.total` 變單邊分母、診斷數字也會錯。
- **C2 `[0,width]` clamp**（`valuation.py:326-334`，**最危險因為靜默**）：
  是 long debit vertical 的 payoff 包絡被寫成算術。對任何 credit 結構
  short leg 恆較值錢 ⇒ `raw ≤ 0` ⇒ **baseline_value 在每個價格恆等於
  0**。實測真實 bull put spread：`baseline_return` 恆為 −1.0（每個
  credit spread 都一樣）、`max_profit` 算出 7.25 > width 5.0、leverage
  與 friction 符號翻轉、`completion_scan` 宣稱任何價格都損益兩平——
  **全部不拋例外**。目前靠 `filters.py:104`／`:162`／`:176` 三道閘門
  擋著，而**擴充策略時要拆的正是這三道閘門**，bug 會在拆的當下醒來。
- **C3 前端寫死兩腿**：`formatRepresentativeLegs`／`candidateTitle` 皆
  destructure `[buy, sell]`，遇第一個 butterfly 靜默丟棄第 3 腿以後。
- **C4 單腿詳細頁靜默空白**（見上第 2 條）。
- **C5 `is_bullish` 硬編碼兩名字表**（`models.py:180-181`）：加
  `"bull-put-spread"` 會回 `False`，direction gate 於是拒絕所有
  bullish target。

**枚舉量實測**（真實鏈 per-expiry 合格數，5 個到期日總和）：
vertical `C(n,2)`＝1,463（28ms）／butterfly `C(n,3)`＝11,966（~230ms）／
iron condor 有序 `C(n,4)`＝73,100（~1.4–3s）／**無序 `C(n,2)²`＝
511,859（~20s）**。Butterfly 舒服，Iron Condor 需要收斂規則。

**本輪最重要的領域洞察（#210 的核心）**：同一個 `target_price` 對三類
結構語意根本不同——Call/Put 是**門檻**（越遠越好）、Vertical 是
**上界**（漲到這裡封頂）、Butterfly/Condor 是**中心**（pin 在這裡最賺、
漲過頭反而虧）。把後者接進現有 Scenario **會改變既有欄位的意義**，
且 `target == spot` 目前被 direction gate 直接拒絕、`_grid_price` 會把
五個 k 塌成同一價格——**純中性的 Iron Condor 現行模型無法表達**。

**Out of scope（需求方已裁示）**：Straddle／Strangle 等純 volatility
strategies、Calendar／Diagonal 跨 expiration 結構、Covered Call／
Protective Put／Collar（需 stock-position context）、Dashboard、
Recommended／Not Recommended ranking semantics。

**順帶更正 tracker 狀態**：#111／#114 是**過期 blocker**——#111 最後
更新停在 2026-08-12，但 HIVT-01（#152）之後已用真實 probe 驗證
Market Data App 單合約歷史端點可用，HIVR-01～11（#160–170）已把
reconstruction pipeline 出貨，**歷史 IV 今天實際拿得到**。兩張應重新
評估而非續當 blocker。

**下一步**：需求方逐張處理 frontier 三票（#210／#211／#212），
`/wayfinder <map>` 一次一張。六張走完才進 `/to-spec`。

**#210 已 resolve（2026-08-27 第二場，`/wayfinder 209` 單票 grilling，
回報#039）**——`target_price` 語意 Owner Decision 全數定案：

1. **全 family 統一為「點預測」**：`target_price`＝使用者預測
   target_date 當天標的所在的單一價位；所有 family 的劇本報酬回答
   同一個問題「如果剛好是這個價，我賺多少」（把既有引擎行為升格為
   正式產品語言）。Butterfly 的 body ≈ target 由排名自然湧現，
   不新增欄位。
2. **Iron Condor 自 Initial V2 defer**（地圖 Destination 從 4 family
   改 3 family）：Condor 實質主張是「區間寬度」，單點給不出；照點
   排名必退化成照權利金排名（短腿貼 target 的最高風險 Condor 恆
   第一）。劃界寫死：**點預測＝價格主張；區間寬度＝波動率主張**
   （與已排除的 volatility scenario 同類）。#214（Condor 枚舉收斂）
   隨之以 not_planned 關閉、入地圖 Out of scope；未來要做需以
   range-scenario 另起新地圖。
3. **`target == spot` 開放**：方向升為衍生三態（漲／跌／持平），
   分析當下由 target vs spot 算出、永不落盤；持平時僅 Butterfly
   可選。不發明容忍帶。direction gate（`service.py:915`）與
   `_grid_price` 塌陷的修法屬實作，交下游。
4. **漲過頭不是失敗**：`best_return`／卡片燈號語意不隨 family 變
   （燈號維持資料層語意；與 QA1-08 移除「標記達成／失效」一致），
   Butterfly 的 tent 下行由 heatmap＋三價位照既有機制如實揭露。
5. **可選／不可選矩陣定案**（純衍生規則）：看漲 Call✓ Vertical✓
   Butterfly✓ Put✗；看跌對稱；持平僅 Butterfly✓。判準＝該 payoff
   能否誠實表達該方向的點主張；沿用 `skipped_direction` 先例。
   subtype 層歸 #212／#213。

**Frontier 現況**：#210 closed（completed）、#214 closed
（not_planned）→ **#213 解鎖**（`baseline_value`＝劇本成真時的價值、
非路徑最差值，已由 #210 給定輸入）；frontier＝#211／#212／#213；
#215 剩 #211／#212／#213 三個 blocker。地圖 #209 的 Destination／
Decisions so far／Not yet specified／Out of scope 均已同步更新。

**#212 已 resolve（2026-08-28，`/wayfinder 209` 單票 grilling，
回報#040）**——Family ↔ subtype domain model 邊界 Owner Decision 定案：

1. **(a) 存 family**：`Scenario.strategies` 詞彙從 subtype 代碼改存
   family 代碼（`single-leg`／`vertical-spread`／`butterfly`），
   legacy subtype 字串讀取端靜態映射、不做資料遷移；backend 日後
   新增 subtype 時既有劇本下次 refresh 自動吃到，零遷移。
   SCENARIO_CREATED 只記 family（stored preference，合法）。
2. **subtype 於分析時間由 backend 展開**（family × 衍生三態方向 ×
   啟用集合），使用者永遠不接觸 subtype 選擇。
3. **首版 roster debit 先行 6 個**：long-call／long-put／
   bull-call-spread／bear-put-spread（＝今天引擎原樣）／call-fly／
   put-fly。credit 三兀（bull-put／bear-call／iron-fly）名字進
   詞彙表、**啟用 gate 掛在 #213**（C2 clamp 讓 credit 每個數字
   靜默錯誤，修對前不啟用）。
4. **同 family 多 subtype 同一池競爭**：subtype 是候選屬性（如同
   履約價）、不是分組維度，不設 subtype 分區／tab。
5. **eligibility 在 backend、以 subtype 為單位**（skipped_direction
   先例）；family 的可選／不可選＝旗下任一啟用 subtype eligible
   （OR 投影逐格重現 #210 矩陣）；frontend 只渲染 verdict。
6. 候選攜帶具體 subtype 代碼（沿用既有引擎 strategy 字串不改名）；
   `subtype→family` 全站唯一靜態對照表。反過度抽象護欄確認：無
   registry／plugin／策略類別階層／per-family config，詞彙固定
   3 family × 9 subtype（6 啟用）。

**Frontier 現況**：#212 closed（completed）；frontier＝#211／#213
（#215 剩這兩個 blocker）。fog「family tab 空狀態與 eligibility
揭露文案」隨 #210＋#212 定案降級為 /to-spec 文案細節，自地圖移除。

**#213 已 resolve（2026-08-28，`/wayfinder 209` 單票 grilling，
回報#041）**——非單調／credit payoff 估值與排名語意 Owner Decision
定案（canonical payoff semantics）：

1. **payoff 一律逐腿直算**：`V(S)＝Σ 方向符號×口數×單腿價值`；
   `[0,width]` clamp（C2 地雷，`valuation.py:326-334`）廢除，
   max profit／max loss／breakeven 由 piecewise-linear 導出，不寫
   per-subtype 封套公式（C2 正是那條路線的產物）。
2. **return 分母＝max loss（最大可損資本，worst 口徑）**——T12／
   附錄 A14.2 成本口徑的修訂，需求方明示核准：worst execution
   原則不動，分母語意從「debit 成本」升級為「最大可損資本」，
   debit 下兩者恆等（全家族逐位元不變為硬條件）；credit＝W−C；
   「−100%＝全損」成為全 family 不變量（否決「收到的 credit 當
   分母」——崩盤 −122% 穿破不變量；否決券商保證金公式——非市場
   事實）。驗算真實 bull put K85/K90：達標 +81.8%、崩盤 −100%，
   現行病態（恆 −1.0／max_profit 7.25＞width／符號翻轉）全消失。
3. **ranking 維持 point evaluation**（V(target) 於自身 expiry，
   #210 給定）；breakeven 泛化為導出根集合（單調 1 點、fly 2 點）；
   completion 單調家族逐位元不變、非單調改報獲利區間（兩邊界，
   含 target 上方側）；七情境／resilience／heatmap 全 family 沿用。
4. **衍生指標分母同步**：leverage＝|net_delta|×spot/max loss、
   friction＝(net_worst−net_mid)/|net_mid|、`_spread_tie_key` 同步
   ——debit 全部恆等不變。filters 三道閘門（單邊過濾／
   long_is_lower／net_mid≤0）改 per-subtype 結構合法性規則。
5. **Butterfly spec-ready**（語意齊備，剩 #211 payload）；**credit
   三兀「語意未定」gate 解除**，轉為可驗證工程＋驗證 AC（逐腿
   估值取代 C2＋回歸斷言含「credit baseline_return 不得為常數」、
   per-subtype 合法性、真實資料驗證、「收到 credit＋最大風險」
   兩欄顯示），是否進 V2 首發歸 #215。

**Frontier 現況**：#213 closed（completed）；frontier＝**#211**
（最後一張 grilling 票；#215 只剩它一個 blocker）。

**#213 Addendum＋#211＋#216 已完成（2026-08-28，回報#042）**——
需求方兩段式指示：先補 #213 clarification、再 resolve #211。

**#213 Addendum（Owner clarification，不重開票）**：①詞彙分離
**Scenario Value**（ranking 評估量＝「underlying 在 target_date
當天剛好等於 target_price 時 position 在那一刻值多少」；expiration
晚於 target_date 的候選**含剩餘時間價值**、早於等於者＝Expiration
Payoff at target；target 前後多個 expiration 共同參與 ranking）vs
**Expiration Payoff**（max profit／max loss／breakeven／profit
region 唯一來源），不得混用——原 resolution「於自身 expiry」表述
被取代；②defined-risk candidate 導出 max_loss 必須 > 0，否則
invalid（不進 ranking、不計 ROI、只記 diagnostic，不得產生
Infinity／宇宙級 ROI）；③**friction 自 canonical model 移除**
（worst executable entry 已內生 execution spread，不二次處理；
原 friction 公式撤回、credit AC 的 friction 項移除；既有
friction 欄位／函式標記 spec 階段 legacy 清理對象）。

**#211 已 resolve（`/wayfinder 209` 單票 grilling）**：
1. 代表候選＝**「B 儲存＋A 顯示」**（需求方原話）：卡片頭條＝
   跨 family 冠軍（#213 統一分母後同一把尺；口徑升級明文入
   spec／CONTEXT.md 非靜默），儲存 scalar 冠軍保留（排序零改動）
   ＋新增 per-family 代表 map（additive JSONB）——資料不在儲存面
   抹殺，日後改 per-family 顯示零遷移。詳細頁預設 tab＝冠軍
   family。
2. payload＝**儲存全保真、wire 投影＋top-N**：detail 回應每啟用
   family 只帶 expiry_top10（≤5 期×10）＋expiry_best＋
   representative＋pool 只留被引用 key；all_candidates（歷史
   連續性用）永不上 wire。
3. **matrix 全候選照帶不 lazy**（需求方硬需求：每候選展開即見
   熱力圖），採 #216 研究組合一壓縮。
4. candidate wire＝共用骨架＋`legs[]`（任意腿數；C3 地雷修形
   定案），subtype 代碼＋靜態標籤表。
5. lazy 名單不動；detail 單一 fetch per (id, analyzed_at) 含全部
   family；tab 首屏最小集＝verdict＋representative＋top-N 列；
   Refresh Run 語意不動；新增優化僅限使用者觸發或有上限預取。

**#216 已 resolve（research，Sonnet subagent）**：Candidate
heatmap matrix 傳輸壓縮——組合一（shared axes dedup＋cells flat
array／round4，交 Vercel gzip／brotli）：150 候選模擬
candidate_pool raw 726KB→437KB（−39.8%）、brotli 50KB→28KB；
軸數與候選數結構性脫鉤（實測 10 組軸）。base64 Float32 壓縮後
反而更差、否決；「傳種子前端重算」違反零金融計算紅線、否決。
組合二（progressive prefetch）defer 至 production 數字（入 map
fog）。文件 `docs/research/heatmap-matrix-payload-compression.md`。

**Frontier 現況**：#211／#216 closed；**#215 正式解鎖**（blockers
#210–#214 全 closed）＝地圖最後一張票，走完即可安全進 /to-spec。

**#213 Correction＋#215 已完成——地圖 #209 Destination 達成
（2026-08-29，回報#043）**：

**#213 Correction（Owner canonical product model 訂正，superseding
comment 落 #213／#211，不重開票）**：①產品＝**Scenario Bet
Ranking**（「劇本成立時哪個 candidate 成功情境報酬最好」），不是
risk-adjusted return optimizer；②**「全 family 統一 max_loss 當
return 分母」撤回 canonical 地位**——debit 維持既有語意（劇本成立
時相對**實際投入成本**的報酬；數值不變、T12/A14.2 不視為被修訂），
失敗情境不是 ranking 維度；③**credit return semantics＝unresolved
scope**（要啟用 credit 必須先有符合 Scenario Bet 哲學的獨立分母
定義，不自行決定 max_loss／credit／margin）；④Scenario Value／
Expiration Payoff 降級為 implementation-level 計算區分（不進產品
概念、不改 UI、不要求使用者理解）；⑤**expiration 分組是產品結構
必須保留**（多 expiration 共同分析、依 expiration 分區呈現）；
⑥#211 的跨 family 可比理據同步訂正（首發全 debit＝同為「相對
實際投入成本」同一把尺，非 risk-capital 尺）。仍 canonical：逐腿
直算、worst execution entry、point ranking、BE 導出根、獲利區間、
max_loss>0 validity、friction 移除、#210／#212 全部裁定。

**#215 已 resolve（`/wayfinder 209` 收尾票，grilling）**：
1. **Initial V2 封板**：3 family × 6 debit subtype（long-call／
   long-put／bull-call／bear-put／call-fly／put-fly）；**持平劇本
   （target==spot）首發就上**（Owner：「就當作停在原地」，僅
   Butterfly 可選，照畫該到期日熱力圖，不多發明設計）；credit
   vertical 與 iron-fly **deferred**（return semantics 未
   canonical）；首發全 debit ⇒ C1 單邊過濾本輪不需拆。
2. Vertical／Butterfly 的「貴不貴」區塊**整塊不顯示**（不留空
   狀態文字）；Butterfly M percentile 緩發（3 腿涵蓋率未量測）；
   兩腿 IV 走勢與 IV Gap 走勢（descriptive）照常。
3. 舊劇本：讀成 vertical-spread family、升版當天逐位元不變、
   不自動開新 family（編輯可加勾）。
4. 硬回歸紅線六條：#118 沿用＋debit bitwise parity（估值改逐腿
   直算後）＋到期日分組結構不變＋四策略 golden fixtures
   byte-locked＋stored view 讀取相容不遷移＋既有功能零回歸；
   另 fly 歷史身份列 day-1 落盤＋fly 淨成本走勢圖首發即支援。
5. 施工六段式（風險遞減、每段獨立可驗）：**A 護欄**（#118 擴充
   ＋debit bitwise 基準）→**B 估值核心**（逐腿直算取代 clamp，
   畫面零變化下 bitwise 驗證）→**C 儲存/domain**（family 詞彙＋
   legacy 映射＋per-family map）→**D Call/Put 端到端**（C4 兩
   欄位修＋family tab 首例）→**E Butterfly 端到端**（枚舉＋
   validity＋legs[]/C3＋獲利區間＋持平三態/_grid_price＋payload
   投影/matrix 壓縮/schema 升版）→**F 收尾**（全面回歸＋E2E＋
   真機驗收清單）。
6. Out of scope 封板：credit 三兀／Condor／Straddle-Strangle／
   Calendar-Diagonal／Covered-Collar／Dashboard／Recommended／
   兩 family package percentile／prefetch／多使用者／N-leg／
   新 friction 指標／順手 cleanup，施工不得順手加入。

**地圖 #209 全部收尾**：#210–#216 七張全 closed（#214
not_planned），Destination 標記達成、Notes 補 Scenario Bet 紅線、
credit 三兀入 Out of scope。**下一步＝/to-spec，等需求方 cue，
本 session 依規停止。**

### Initial V2 spec 已發布＝issue #217（2026-08-29，`/to-spec`，回報#044）

地圖 #209 的七張票決策收斂成單一份 spec：**issue #217「Initial V2：
方向性策略擴充（Call / Put、Vertical Spread、Butterfly）」**，標
`ready-for-agent`，63 條 user stories。

**施工前先讀 spec §A**（產品定位）與 **§Q**（六段式順序）。重點：

- **測試接縫：沿用既有七個、零新增**（需求方核准）——① HTTP API
  ② 引擎純函式 ③ Storage port 契約（memory＋真 Postgres 雙跑）
  ④ 契約樣本 drift（需新增一份 Butterfly 樣本）⑤ 選取身份守門
  （#118，本輪**擴充**加上 debit 數值 bitwise parity）⑥ CLI golden
  fixtures ⑦ 前端 Vitest＋Playwright 兩 project。
- **12 條硬回歸紅線**寫進 spec Testing Decisions，含「既有
  bull-call／bear-put 逐位元不變」「到期日分組結構不變」「fly
  legs[] 長度 3」「熱力圖展開零額外請求」等。
- **施工中一個必須避開的陷阱**（已在 #213 留防呆註記）：#213
  Addendum A 的字面文字會讓人以為要把後錨點到期日的候選改成
  「在錨點當天含時間價值估值」——**不可以**。需求方澄清「劇本只是
  設定，以某個到期日來看，最佳收益如何」，ranking 維持 T3／#17
  的「各候選用自身到期日」既有語意，Scenario Value／Expiration
  Payoff 的區分只是 implementation-level，且在既有熱力圖裡本來就
  存在，本次不新增、不改任何 ranking 數字。
- **詞彙對齊**：地圖討論用 `target_date`，但產品既有時間語意是
  月級 `target_month`（CONTEXT.md 明文「不要用目標日期」），spec
  一律用 `target_month`，`target_date` 不進產品詞彙。
- **施工前先更新 CONTEXT.md**（該檔自身規則）：新增 Strategy
  Family／Subtype／Scenario Bet Ranking／Direction（衍生三態）／
  Eligibility／Profit Region／Per-family Representative 七個詞條，
  並記錄 friction 已自 canonical model 退場。

**下一步＝/to-tickets**（依 spec §Q 六段切票），等需求方 cue。

### Initial V2 拆票完成＝#218–#235（2026-08-29，`/to-tickets`，回報#045）

spec #217 拆成 **18 張票（#218–#235）**，全數為 #217 的 GitHub
sub-issue、全數標 `ready-for-agent`。依賴邊寫在各票 body 的
「Blocked by」（本 repo 的 MCP 工具沒有 native blocking 寫入能力，
沿用 body 慣例）。

**四張無依賴、可立即開工**：#219（T02 逐腿 payoff）／#220（T04
friction 退場）／#221（T06 family 詞彙）／#222（T09 單腿補欄位）
——皆只被 #218（T01 護欄與詞彙）擋。

**施工順序**（spec §Q 六段的落地，粒度比六段更細，沿用專案
「不求快、求正確性」的拆票先例）：

- **A 護欄**：T01 #218（凍結四策略數值 bitwise 基準＋CONTEXT.md
  七個新詞條，零產品行為改動）
- **B 估值核心**：T02 #219（逐腿 payoff 取代 debit-only 包絡）→
  T03 #223（包絡量改由 payoff 導出）→ T05 #226（max loss ≤ 0
  直接淘汰）。**T04 #220（friction 退場）刻意與 T02/T03 分開**：
  後者是 bitwise-identical 的改動、前者會動 golden fixtures，
  兩種混在同一份 diff 就分不出是誰讓 fixture 移動的
- **C 儲存／domain**：T06 #221 → T07 #224（per-family 代表 map）
  ／T08 #225（衍生三態方向＋per-subtype eligibility）
- **D Call/Put 端到端**：T09 #222 → T10 #227（表單 family 勾選）
  → T11 #229（詳細頁 family tab，Call/Put 到此端到端可用）
- **E Butterfly 端到端**：T12 #228（共用骨架 legs[]，**刻意排在
  Butterfly 之前**——先用既有兩腿資料把任意腿數的骨架驗好，
  Butterfly 只是多一個產生器，「make the change easy, then make
  the easy change」）→ T15 #230（Butterfly 後端）→ T16 #232
  （前端三腿／獲利區間）→ T13 #231（payload 投影）→ T14 #233
  （matrix 壓縮）→ T17 #234（持平劇本）
- **F 收尾**：T18 #235（12 條硬紅線逐條對照＋全套回歸＋真機
  驗收清單）

**T04 friction 的範圍已釐清**（需求方：「摩擦力不需要考慮，因為
我們的模型早已按最差價格計算了」）：friction 今天其實**已經不進
ranking**（排名用 worst 口徑成本），只活在候選契約欄位、CLI 報告
一行、詳細頁分析報告一列——三處一併移除，並加結構性測試讓它回
不來。**golden fixtures 會因此重產一次**（只含那一行的移除），
之後繼續 byte-locked；這是 T04 唯一預期中的 fixture 變動。

**測試接縫沿用既有七個、零新增**（需求方核准，見 spec #217
Testing Decisions）。

**下一步＝`/implement`**，從 #218 開始，等需求方 cue。

### Initial V2 票面澄清＋T01 施工（2026-08-30，回報#046）

**票面澄清（需求方三點指正，未重跑 `/to-tickets`，票號與依賴全數保留）**：

- **#223（T03）** — 原文「極值只可能出現在各履約價與**兩端**——掃描
  這些點」會被讀成「掃描全價格域取理論極值」，進而生出「Long Call
  max profit = ∞」這種不屬於本產品的語意。已改寫為「分段折點與**所
  評價區間**的端點」，新增「範圍界定」一節：只導出既有產品真正需要的
  payoff envelope／extrema、遵守既有 target／expiration scenario 搜尋
  範圍、**不新增 unbounded max-profit product concept**、評價端點取自
  既有搜尋區間邊界而非 `0` 與 `+∞`。Owner semantics 未動，四策略
  bitwise parity 仍為硬條件。
- **#226（T05）** — 原 AC 把「debit spread 權利金大於價差寬度」列為
  `max_loss <= 0` 的驗證 fixture，但 width=5／debit=6 的 max loss 是
  **+6**，結構上不可能觸發該規則。已移除，改為真正的壞報價／不自洽
  報價（單腿倒掛、兩腿矛盾致 net debit ≤ 0、跨時點凍結報價）。同時
  明文加註**不新增 `max_profit <= 0` 過濾規則**、不新增任何新產品
  判斷——成功劇本仍為負報酬的候選由既有 ranking 自然沉底即可。
- **#228（T12）** — `legs[]` 陣列保留，但撤掉「任意腿數／任意長度」
  scope（與 spec #217 Out of Scope 明文排除的「四腿以上結構與 N-leg
  泛化」衝突）。Canonical boundary 改為 **`1 <= len(legs) <= 4`**：
  1 腿 Long Call/Put、2 腿 Vertical、3 腿 Butterfly 為本輪實際啟用，
  4 腿只保留 contract／data-shape 容量、**不啟用任何四腿 strategy**、
  不建立 arbitrary N-leg strategy framework，`len(legs) > 4` 應
  validation fail。標題同步修正。

**已完成**：

- **T01** [#218] 護欄與詞彙（commit `ffab545`）——**零 production
  code 改動**，只新增測試、fixture、產生用 dev script 與文件。
  - `tests/test_selection_regression.py` **擴充**出數值那一半：新增
    `snapshot_numbers()`／`assert_numbers_unchanged()`，與既有的
    `snapshot_identity()`／`assert_identity_unchanged()` **兩個獨立
    入口並存、刻意不合併**（#118 把「誰／第幾個」與「值多少」分開的
    設計原封不動）。11 → 24 條測試。
  - 現況凍結成磁碟 golden `tests/fixtures/valuation_numeric_baseline.
    json`（4 策略、26 候選、227KB），由 `scripts/gen_numeric_baseline.
    py` 產生——腳本直接 import 守門測試本身取得 `snapshot_numbers()`，
    不複製一份快照邏輯，基準與守門因此不會各自漂移。`indent=1` 是
    刻意的：每個數字獨佔一行，git diff 能直接指到變動的那一格。
  - 決定性：`run_offline` 預設不接利率／股利 loader，`today` 由快照
    自己的 `fetched_at` 推出（`snapshot_today`）——離線、零網路、不讀
    系統時鐘。另有一條測試釘住「JSON 往返後逐位元相同」。
  - 凍結 **37 個欄位**（劇本報酬、包絡量、情境向量、heatmap 格值、
    完成度、Greeks 比率、利率輸入、價格階梯、Crossover comparator
    含其 matrix、逐腿報價），明確排除 **4 個**並各記理由
    （`candidate_key`／`strategy` 歸身份守門；`cons`／
    `guidance_warnings` 是文字、已由 CLI golden byte-lock）。另加一條
    **completeness 測試**斷言「候選的每個欄位非凍結即明文排除」——
    新增欄位時紅燈，逼出一次有意識的決定。
  - **紅燈實測**：臨時把 `valuation.py` 的 `max_profit` 加 `1e-9`，
    守門立刻紅並逐筆列出「策略／候選鍵／欄位／舊值→新值」；驗完
    `git checkout` 還原。另兩條測試分別鎖住「訊息要指得出候選與
    欄位」與「改一格 heatmap 也要指到 `matrix.cells[2][3]`」。
  - 順手釘住一顆 #223 的引信：`test_long_call_max_profit_is_absent_
    not_infinite`——Long Call 今天的 `max_profit` 是 **None（不適用）**
    而非無限大；T03 若誤引入全價格域理論極值，這條會紅。
  - `CONTEXT.md` 新增七個詞條（Strategy Family／Subtype／Scenario
    Bet Ranking／Direction 衍生三態／Eligibility／Profit Region／
    Per-family Representative），獨立成「策略與方向」一節；「名詞
    紀律」記錄 **Friction 已自 canonical model 退場**（#217 決策 D，
    施工在 T04／#220）。數值基準**仍然凍結** `friction`／
    `friction_amount` 的現況值——T04 移除它們時這條會紅，那是本基準
    唯一預期內、需有意識重產 golden 的一處。

> **⚠ 分支上有 5 條先前就存在的紅燈，與 T01 無關**（已用「stash 掉
> T01 改動後在乾淨 HEAD 重跑」與「乾淨 HEAD worktree 對照」兩種方式
> 各確認一次，五條逐字相同）：`test_api_filters.py` 三條、
> `test_api_iv_history.py` 一條、`test_service_fetch.py` 一條。
>
> **共同病因是測試非 hermetic，不是引擎回歸。** 三條 filters 的機制
> 已鎖定：這些 `/api/analyze` 測試用假 symbol `"XYZ"`，卻走
> `create_app()` 的**預設 dividend loader**——而 `XYZ` 是真實上市代號
> （Block Inc.），在**連得到外網**的環境裡會抓到真實配息、算出非零
> q、`carry_calibrated` 變 True，估值與級距排名跟著位移，strike 100.5
> 因此掉出榜。實測：把 `dividend_loader` 換成回傳 `None` 的假體，三條
> 立刻全綠。`test_service_fetch` 同一家族——`fetch_and_save` 實際打到
> 真 vendor，回傳 `fetched_at` 是「現在」而非 fixture 的時間（會隨
> 沙箱 egress 通不通而間歇紅／綠）。第 5 條（iv-history 的
> `delta_4w 回報 unavailable`）走 `ny_today()`、疑似日曆漂移，成因
> **未完全鎖定**。
>
> 先前紀錄的「全套全綠」是在沙箱擋外網（q 退回 0、vendor 抓不到）的
> 條件下量到的——**環境變了，測試就變了**，這本身就是缺陷。三者皆不
> 在 #218 範圍（該票明令不動 production code），未修，**建議另開一張
> hermetic-test 修正票**。T01 自己的基準不受影響——它走 `run_offline`，
> loader 預設 `None`。

> **⚠ 容器倒退再度發生（本 session）**：本地 checkout 落後 origin
> **29 個 commit**（停在 `945977c`，遠端已到 `22b9d4b`），且 working
> tree 帶著一份**已經推上去的** T11（#194）改動的殘影，看起來像未提交
> 工作。依 CLAUDE.md 既有處置：`git fetch` → `git reset --hard
> origin/claude/implement-tfm9oa`，零內容遺失。**本輪的實際教訓**：
> T01 的基準第一次是在 stale base 上產生的，reset 後重新產生一份逐位元
> 比對——**兩份完全相同**（那 29 個 commit 沒有動到估值），但這個核對
> 是必要的，不是多餘的。回報編號也因此差了一大截（stale 版寫 028，
> 真值是 045）。**動筆前先 `git fetch` 該分支本身、核對 `git log
> origin/<branch>`。**

**待辦（← 為下一張）**：

- **T02** [#219] 逐腿 payoff 直算（取代 debit-only 包絡）——被 #218
  擋，**已解除** ←
- 同時解鎖：**T04** [#220] friction 退場、**T06** [#221] family 詞彙、
  **T09** [#222] 單腿補欄位（三者亦只被 #218 擋）
- 其餘依 spec #217 §Q 六段順序推進

### #226 兩層化＋Hermetic test repair #236（2026-08-30，回報#047）

**#226（T05）票面第二次修訂——Candidate validity 明確拆成兩層**：
原文把 `bid > ask` 等報價層問題描述成「導致 `max_loss <= 0`」的成因，
等於讓報價層的剔除**依賴**導出層的結果——那是錯的：倒掛報價有時不會
讓 max loss 變號，但它本來就該被剔除。現改為——

- **A. Quote-level invalidity**：原始報價本身不可信即 invalid
  （`bid > ask`、缺失／非有限值、同候選腿位間互相矛盾、已被**既有**
  資料品質規則判定失效的 stale／frozen quote）。**不需要先證明它一定
  導致 `max_loss <= 0`**；程式碼與測試中不得出現「`bid > ask` ⇒
  `max_loss <= 0`」這種因果敘述。
- **B. Derived mathematical safety net**：即使通過 A 層，只要導出結果
  出現 `max_loss <= 0` 或 `Infinity`／`NaN` 等不可能值，仍直接
  invalid＋diagnostic。**獨立於 A 層成立**，是最後一道網不是 A 的推論。

診斷要看得出**是哪一層**剔除的、各層各幾筆。仍**不新增**
`max_profit <= 0` 或任何新的產品 ranking 規則——負報酬但自洽的候選由
既有 ranking 沉底。標題同步改為「兩層——報價層不可信、導出層數學安全網」。

**Hermetic test repair ＝ issue #236（新開，非 #217 的 18 張施工票之
一），已完成並關閉**（commit `ad783ab`）。修掉 T01 收尾時發現、擋住
#218 「全套測試綠燈」AC 的那 5 條紅燈。**只動 3 個測試檔，production
code 零改動**，既有斷言一條都沒放寬。

- **`test_api_filters.py`（3 條）** — `_client()` 只注入 `fetch=`，
  其餘走 `create_app()` 的**預設 loader**（真管線）。而 fixture 用的
  假 symbol **`"XYZ"` 是真實上市代號**，連得到外網時會抓到那家公司的
  真實配息 → 非零 q → `carry_calibrated` True → 估值與級距排名位移 →
  `strike 100.5` 掉出榜；`rate_used` 也在 `0.0390…`／`0.04` 之間跳。
  改為明確注入固定假利率曲線＋「合成標的不配息」的假 dividend loader
  （q=0）——那正是 FB5-01（#62）期望值成立的條件。
  ⚠ 同一個坑 `scripts/gen_contract_sample.py` 檔頭**早就寫過**，只是
  這個測試檔沒跟上。
- **`test_service_fetch.py`（1 條）** — 只 monkeypatch 了
  `data.yf.fetch_chain`，也就是**備援**那層；但 FB3-01（#44）之後主源
  已是 Cboe。連得到外網時 Cboe 直接成功、回傳帶「現在」時間戳的真實
  快照 → `got_snap == snap` 失敗；擋外網時 Cboe 拋 FetchError 退到
  備援就綠——**同一份程式碼隨環境紅綠不定**。改為主源回傳 fixture、
  備援放地雷（被呼叫到就 AssertionError）。
- **`test_api_iv_history.py`（1 條）** — 該檔 `_client()` 早就注入了
  rate／dividend／vendor 三個假體，唯一非 hermetic 的是 **`ny_today()`**。
  fixture `fetched_at` 是 2026-07-15、候選兩腿到期日 2026-08-07；真實
  日曆走到 2026-08-30 時該合約已到期 23 天。測試以 `ny_today()` 為終點
  造 60 天合成觀測，落在到期日當天或之後的被 `implied_vol()` 正確判為
  無解（T ≤ 0）：買腿剩 22 筆、賣腿剩 15 筆且全在 2026-07-16 之前，而
  Δ4w 基準窗是 `[today-42, today-21]`＝07-19～08-09——**窗還沒開資料就
  沒了**。新增 module 層 autouse fixture 把時鐘釘在
  **`FROZEN_TODAY = 2026-07-15`**（＝fixture 自己的 `fetched_at`），
  只換 `api_app.main` 與測試模組各自綁定的名字，`api_app/clock.py`
  本身不動、**production 日期語意零變更**；14 處既有 `ny_today()` 呼叫
  點自動跟著凍結，不必逐一改寫。
  連帶修正 `test_delta_4w_is_none_without_a_baseline_window_observation`
  ——它把觀測錨在「到期日前 50 天」，但 Δ4w 的窗是相對 **today** 的，
  原本只是碰巧落在窗外。改成從 today 往回數 43 天（窗口起點 today-42），
  斷言一字未動，這條測試從「碰巧通過」變成「真的在測窗口」。

**驗證**：全套後端（記憶體＋真實 Postgres）**1449 passed / 0 failed**；
同一套在 **socket 層封鎖所有對外連線**下重跑**同樣 1449 passed**
（一次性驗證插件，未入 repo）——「可上網與不可上網結果一致」是實測，
不是推論。前端 typecheck 乾淨、vitest 670 條全綠（本輪未觸碰前端）。

> **教訓（值得記住）**：先前多次紀錄的「全套全綠」都是在沙箱**擋外網**
> 的條件下量到的。環境一變（本 session 的沙箱恰好連得到 Treasury／
> Cboe／Yahoo），同一份程式碼就紅——這不是引擎回歸，是測試把「環境
> 剛好連不到外網」當成了隱含前提。**判斷一條紅燈是不是回歸之前，先問
> 它會不會打真網路、會不會讀系統時鐘。**

**#218（T01）全部 AC 通過，已 close。** 阻擋它的唯一一條
（「全套測試綠燈」）由 #236 解除。

**下一張＝T02 #219**（逐腿 payoff 直算），無 blocker；同時解鎖的還有
T04 #220、T06 #221、T09 #222。

### T02（#219）完成（2026-08-30，回報#048）

`spread_scenario_value` 的 `min(max(long-short,0), width)` 封套公式已
廢除，改為逐腿直算 `V(S) = Σ 方向符號 × 口數 × 單腿價值`。新增原語
`WeightedLeg`／`payoff_value`（`option_chaser/valuation.py`）——不假設
腿數為 2、不假設買賣方向組合，供 T12（#228）／T15（#230）的任意腿數
結構直接複用。`spread_scenario_value` 縮成薄殼，簽章不變，既有呼叫點
（`ranking.py`／`report.py`／`scenarios.py`／`service.py`）零改動沿用。

**施工中攤開一個真實衝突並取得 Owner 裁示**：「拿掉 clamp 後四策略
bitwise 不變」在有**買賣腿 vendor IV 不同（真實市場 skew）**時不成立
——BS 定價的 monotone-in-strike 保證只在兩腿共用同一 sigma 時才有效。
實測反例：XYZ bull-call-spread 105/110（買腿 IV 0.36、賣腿 IV 0.30）
在 Heatmap 格點 S=133.2／2026-07-15，逐腿直算 `5.017486628026035`
微幅超出 `width=5.0`（+0.35%）——不是浮點雜訊，是既有模型（未經 carry
校準的預設路徑）在有 skew 時的真實性質，舊 clamp 把它無聲夾掉。
**Owner 裁示：拿掉 clamp，更新 T01 基準**（AskUserQuestion，三選一中
選推薦項）。範圍已核對到最嚴格：全部 4 策略、2002 個 heatmap 格值
逐格掃過，只有這一組候選的 **3 格**不同，CLI golden fixtures 與契約
樣本零漂移。決策記錄三處：`valuation.py` docstring、
`scripts/gen_numeric_baseline.py`（新增第二個已知合法重產時機）、
新回歸測試鎖住這個發現本身。

`/code-review`（Standards＋Spec 兩軸）均無 hard violation。全套後端
1455 passed；前端零改動、typecheck 乾淨。commit `71f837c`，issue #219
已附完整驗收留言並關閉。

> **⚠ 容器倒退再度發生（本 session 第二次）**：這次連當下未 commit 的
> T02 進度一起消失（本地 HEAD 掉回 `945977c`，落後真 HEAD `f5df5ec`
> 3 個 commit；working tree 也回到帶著 T11 舊殘影的狀態）。標準處置：
> `git fetch` + `git reset --hard origin/claude/implement-tfm9oa`
> 復原（T01／hermetic repair 皆已推上遠端，零損失），T02 全部改動
> 重做一次（已完整記得先前做過什麼，重做無額外損耗）。**教訓更新**：
> 這個 bug 不只在 commit 之間發生，**同一票施工過程中**（尚未 commit）
> 也可能發生——每完成一張票的全部改動就立刻 commit＋push，不要在單票
> 內累積過多未提交進度。

**下一張＝T03 #223**（包絡量由 payoff 導出），被 #219 擋、現已解除。
同時已解鎖（原本只被 #218 擋，現在也可開工）：T04 #220、T06 #221、
T09 #222。

### T03（#223）正式收斂為 not planned＋下游票修正（2026-08-30，回報#049）

T03 兩次嘗試皆被 Owner 判定方向錯誤，**正式收斂、不再嘗試第三套演算法**：

- **第一次**（commit `5691fdc`，已 revert 於 `c6b6e0b`，保留在分支歷史作
  audit trail）——自建 payoff continuous-function／slope／tail 分析
  （`payoff_envelope()` 用「在履約價之外任選一點求斜率」判斷是否封頂）。
  雖對真實 fixture 19/19 逐位元核對通過，但機制本身偏離 Option Chaser
  從頭到尾「窮舉既有價格網格逐點計算」的產品模型（heatmap／情境向量／
  完成度掃描皆是如此），Owner 判定方向錯誤。
- **第二次**（未進 commit，本地驗證後即捨棄）——改用既有 `price_axis()`
  網格逐點窮舉。實測 19 個既有候選中 **17 個數值改變**（Long Call
  max_profit 從 `None` 變成有限數字、Long Put max_profit 遠小於真實值、
  部分 Spread breakeven 出現線性內插誤差）。根因**不是取樣太粗**，是
  `price_axis()` 本來服務 **Scenario Bet**（圍繞使用者填的
  spot／target／best/worst），不服務**結構本身的數學極值**（不受劇本
  範圍限制的真實 max/min）——這兩者只在 Vertical Spread 上巧合重疊。

**Canonical 結論**：Initial V2 不需要先建立一套跨所有 strategy 的
generic payoff-envelope／extrema engine。新 family 只實作自己真正需要、
且既有模型沒有的語意，不為「架構漂亮」提前泛化。既有 Long Call／
Long Put／Bull Call Spread／Bear Put Spread 的 `max_profit`／
`max_loss`／`breakeven` **維持 T02／#219 完成時的既有公式**
（`width-net_worst`、`strike±ask`、`None if strategy=="long-call"`），
不受本輪探索影響。

**#223 已 close（state_reason=not_planned）**，收尾 comment 記錄兩次
否決的完整證據與原因區分。

**下游三張票已修正**（各自 comment＋本文皆已更新）：

- **T05 #226** — 解除 Blocked by #223，**無 blocker，可立即開工**。
  B 層安全網改為只檢查**既有**成本／報酬欄位（`net_worst`／
  `natural_cost`／報酬率），明文禁止為了本票重建 generic max-loss
  推導引擎。A/B 兩層架構、範圍紅線本身未變。
- **T12 #228** — 解除 Blocked by #223，**無 blocker，可立即開工**。
  新增「schema 裡的數值欄位是透傳，不是本票要建的引擎」一節：
  `max_profit`／`max_loss`／`breakeven` 數值沿用既有四策略既有公式，
  本票只動 `legs[]` 傳輸形狀；損益兩平兩點容量純粹是預留給 T15 的
  空間，本票不實作產生兩點的邏輯。
- **T15 #230（Butterfly）** — Blocked by 維持 #225／#226／#228（本來
  就沒有 #223）。移除「兩個損益兩平點由 T03 的導出機制自然得到」這句
  已失效引用，改為 Butterfly 真正需要的三腿 payoff／兩個損益兩平點／
  獲利區間**收回本票自己獨立完成**，只服務 Butterfly 這個結構，明文
  禁止趁機重建跨 family 的 generic extrema framework。

**#217 已留 scope/dependency clarification comment** 彙整索引以上
異動，未重寫 spec 本文。

**下一張＝T04 #220**（friction 自 canonical model 退場），無 blocker。

### T04（#220）完成——friction 自 canonical model 整個退場（2026-08-30，回報#050）

friction 概念從 `option_chaser/scenarios.py`（`friction()` 函式）、
`CandidateView.friction`／`friction_amount` 兩欄位（`service.py`）、
契約序列化（`store.py`）、CLI 報告一行（`report.py`）、前端型別
（`api.ts`）與 Analysis Report「Execution Friction」列（`AnalysisReport.
tsx`）**全部一併移除**，不新增任何替代的 friction／滑價／執行成本
指標。新增兩條結構性測試防止它悄悄回來（契約裡不得出現這兩個 key；
`scenarios.py`／`service.py`／`store.py`／`report.py` 原始碼不含
`friction` 字樣）。

**既有 `quote_warning` 選取閘門的複合公式**（FB5-02／#63，
`zero_vol or wide_spread or fr>0.25`）拿掉第三個條件，改為
`zero_vol or wide_spread`——**`/code-review` Spec 軸抓到一個真的不
準確的宣稱並已修正**：commit `09a224e` 原本聲稱「沒有任何候選單獨
依賴這個條件，選取身份因此逐位元不變」，實測用契約樣本逐位元核對
後推翻——`contracts/analysis_sample.json`／`analysis_sample_bear_
put.json` 各有一個候選真的翻轉了（`ExpiryGroup.rows[].badges` 從
`['warning']` 變 `[]`）。真正站得住的理由是：`quote_warning` 唯一的
消費端 `_build_groups()`／`default_selection`／`badges` 是 v4 舊
「到期日分組比較」遺留結構，`src/` 全站零消費者（#104 施工時已
grep 確認的既有死碼，非本票新產生）——這個翻轉因此沒有使用者可見
影響，但這是「消費端剛好是死碼」的巧合，不是「公式改動不影響任何
候選」。已在 `service.py` 欄位註解與對應測試 docstring 更正
（follow-up commit `65f1ec5`，純註解修正）。

**golden fixtures／契約樣本重產，逐一核對 diff 範圍**：四份 CLI
golden 各自只少一句 `| Bid-Ask Spread: X%（$Y/股）` 後綴；兩份契約
樣本只刪除每個候選的 `friction`／`friction_amount` 兩個 key；T01
（#218）數值基準把這兩個欄位從凍結名單移到完全不存在（本基準腳本
文件裡記錄的唯一第二個合法重產時機）。

**全套測試**：後端 1453 passed（記憶體＋真實 Postgres，含 T01 基準與
選取身份守門）；前端 typecheck 乾淨、vitest 671 passed、production
build 成功；Playwright e2e 92 passed（iPhone＋Desktop）。`/code-
review`（Standards＋Spec 兩軸）：Standards 軸零 hard violation；Spec
軸抓到上述一處真發現並已修正跟進。

**#220 已 close。** commit `09a224e`＋follow-up `65f1ec5`。

### Initial V2 自主執行輪（2026-08-31 起，Owner 授權全自主施工至全部完成才一次回報）

Owner 明確裁示：不再逐票停下等待，依 #217／#218–#235 dependency graph
自主完成 Initial V2 剩餘全部 tickets，只在六種情況才停下（新的 Owner
裁示題、無法在既有 scope 內修正的硬回歸紅線、ticket/spec 互相矛盾、
必須突破 out-of-scope、需要非票面明文允許的 baseline 更新、真正無法
判斷方案）。全部完成前不主動回報（不占用「回報#0NN」編號，下面 4 條
規則本身仍照舊遵守，只是回報時機挪到全部票做完那一刻）。逐票仍維持
既有紀律：TDD、`/code-review` 兩軸、AC 全過才 close、獨立 commit、
CLAUDE.md 隨手更新。

- **T06**（#221，commit `5c13469`）✅ Strategy Family 詞彙、legacy 映射、
  分析時 subtype 展開：`option_chaser/models.py` 新增 `FAMILIES`（
  single-leg／vertical-spread／butterfly）、唯一一張 `STRATEGY_FAMILY`
  對照表、`FAMILY_SUBTYPES`、`normalize_families()`／`subtypes_of()`
  兩個純函式；`api_app/main.py` 的 `_MVP_STRATEGIES` 改存 family 代碼
  （`"vertical-spread"`），`_refresh_and_save()` 是唯一展開點。改動
  完全侷限在 HTTP 層（`option_chaser/service.py`／`AnalysisRequest`
  介面一行未動）——T01（#218）的引擎層基準結構上摸不到這次改動，因此
  另外寫了 API 層級的逐位元比對測試（`tests/test_strategy_family.py`
  的 `test_refreshing_a_scenario_expands_the_family_and_keeps_today_
  bitwise_identical`：展開後 `bull-call-spread` 的 candidates／
  expiry_best／expiry_top10／candidate_pool 與直接呼叫引擎逐項相同；
  `bear-put-spread` 如預期被既有方向閘門擋成 `skipped_direction`）與
  舊資料相容測試（裸存 subtype 字串的劇本刷新行為不變）。`direction`
  欄位確認只在建立時寫入、`_scenario_json` 純顯示回顯，結構性測試
  逐行掃描鎖定它從未進入任何判斷邏輯。全套測試（記憶體＋真實 Postgres
  雙後端）綠燈；`/code-review` 兩軸皆無 hard violation。**#221 已 close**。

- **T09**（#222，commit `35868f2`；另有獨立 commit `abb0c23` 修正 T06
  遺留的 `scenario_row_sample.json` strategies 值）✅ 單腿策略補齊到期日
  分組欄位：`_single_leg_result()` 補齊 `expiry_top10`／`expiry_ranked`，
  照既有 `_spread_result()` 寫法補齊、重用同一輪已排序的 `vals_sorted`。
  `store._history_entry()` 過去只服務過 Spread，改為依型別分派
  （`isinstance(sv, SpreadValuation)`）正確處理 `ContractValuation`。
  `find_candidate()`／`representative_candidate()` 兩條既有讀取路徑不必
  改邏輯即可正確解出單腿候選——前者原有的「`expiry_top10` 空才退回扁平
  清單」fallback（#139）自然接手，後者本來就讀早已填入的 `expiry_best`。
  驗證：T01 數值基準逐鍵比對，`bull-call-spread`／`bear-put-spread` 0
  modified/0 removed，`long-call`／`long-put` 純新增（4／5 筆候選）——
  記錄為基準第三個合法重產事件（`scripts/gen_numeric_baseline.py`
  docstring 已更新）。新增獨立契約樣本 `analysis_sample_long_call.json`
  ＋drift 測試（不硬湊進主樣本，理由同既有 bear-put 獨立樣本）。全套
  測試（記憶體＋真實 Postgres 雙後端）綠燈；`/code-review` 兩軸完成，
  findings 已修正（`service.py` 補一句 `n_qualified` 全域 vs 本期組內
  大小的不對稱說明；`store.py` 更新 `find_candidate()` 過期 docstring；
  補齊三條鏡射 `test_expiry_top10.py` 的既有測試）。前端零改動——
  `_MVP_STRATEGIES` 仍只啟用 vertical-spread family，single-leg 尚未
  被任何 Scenario/API 路徑觸發。**#222 已 close**。

- **T12**（#228，commit `e7b82e8`）✅ Candidate 共用骨架——`legs[]`
  陣列，1-4 腿容量上限：`_leg()` 新增顯式 `side`／`quantity`，取代
  「陣列位置＝方向」的隱性慣例；新增 `_validate_leg_count()`（
  `1<=len(legs)<=4`，獨立可測試純函式，接在 `_candidate()` 建構
  路徑上）；新增 `breakeven_points`（純加法，值 `[既有 breakeven]`，
  容量預留給 T15 Butterfly，本票不實作產生兩點的邏輯）；
  `representative_candidate()` 投影補上 `side`（舊 View 位置回推
  備援）；`schema_version` 3→4。「每個候選帶著它實際的 subtype
  代碼」確認既有 `strategy` 欄位本來就是，不新增冗餘欄位。T01 基準
  第四個合法重產事件：逐鍵程式化 diff 驗證四個既有策略除新增
  `side`／`quantity`／`breakeven_points` 外零財務數值變化。前端
  新增 `CandidateLegs`（1-4 腿容量的 tuple union，型別本身即容量
  邊界）；修掉 `expiry.ts`／`scenarios.ts`／`detail.ts`／
  `AnalysisReport.tsx` 四處把腿位解構成固定兩個變數的寫法（三腿以上
  候選過去會被靜默丟腿），既有兩腿／單腿候選輸出逐字不變；新增合成
  3 腿候選的元件測試證明不丟腿。`/code-review` 兩軸完成，Standards
  軸抓到的 leg 查找重複已抽成 `api.ts::findLeg()` 共用。全套測試
  （後端記憶體＋真實 Postgres 雙後端、前端 typecheck／675 Vitest／
  build、Playwright e2e 92 條）綠燈。**#228 已 close**。

- **T05**（#226，commit `8594b51`＋跟進 commit `005f20f`）✅ Candidate
  validity 兩層——A. Quote-level invalidity（報價層：`apply_filters()`
  的 `quote_ok`／`iv_ok` 強化為明確 `math.isfinite()` 檢查，判定不以
  「是否導致某導出量變成不可能值」為前提）＋B. Derived mathematical
  safety net（新函式 `validate_derived_values()`，接在既有計算路徑
  之後、排名之前，獨立於 A 層成立，只檢查既有 `cost_fn`／`return_fn`
  ——`natural_cost`／`baseline_return`／`spread_baseline_return`——
  的輸出，零讀取候選欄位，用編譯後 bytecode 名稱檢查證明不含
  `max_profit`／`max_loss`／`payoff_envelope`／`extrema`）。單腳
  `n_qualified` 隨 B 層之後的數量改口徑，Spread 記在
  `pair_report.b_layer_removed`（配對單位，與腿級 `freport` 分開）。
  明確不做：不新增 `max_profit<=0` 規則（劇本成立時報酬為負但報價
  自洽的候選照常留在排名裡自然沉底）、不用「權利金大於價差寬度」當
  驗證案例（該情境兩層皆不觸發）、未重啟 #223 已收斂為 not planned
  的 generic payoff-envelope engine。

  **`/code-review` 兩軸各抓到一個真缺口，已在跟進 commit `005f20f`
  修正**：Standards 軸——`validate_derived_values()` 對泛型
  `cost_fn`／`return_fn` 缺 `None`-safety（`math.isfinite(None)` 會
  拋 `TypeError`），已加 `_finite()` 內部輔助函式。Spec 軸——AC「每一
  筆被剔除的候選留下一筆診斷事件，內容足以指認是哪一組合約」與「剔除
  可見……各層各幾筆」對 Spread UI 不成立：`FilterStageResult`／
  `PairReport` 先前只有聚合計數，`CandidatePool.tsx` 只渲染
  `removed_sanity`、從未渲染 `b_layer_removed`。修法：`FilterStage
  Result` 新增 `removed_examples`、`PairReport` 新增
  `b_layer_removed_examples`（皆純加法，預設空 tuple）；
  `apply_filters()` 兩個 A 層 stage 記下被剔除合約的 `contract_
  symbol`（上限 5 筆範例）；`validate_derived_values()` 新增選填
  `identity_fn` 參數，單腳傳合約代碼、Spread 傳買賣兩腿代碼組合；
  CLI 報告與 API 序列化跟進；`CandidatePool.tsx` 補上 Spread 路徑的
  「成本或報酬為不可能值（B 層）」列（單腳早已透過 `filter_stages.
  map()` 通用渲染），並用瀏覽器原生 `title` tooltip 呈現範例。

  新增 22 條後端測試（`tests/test_candidate_validity.py`）＋3 條前端
  測試（`CandidatePool.test.tsx`）。契約樣本三份（含 T09 新增的
  long-call 樣本）重產：純加法，只多兩個 key，其餘逐位元不變。CLI
  golden fixtures 四份重產：各自只在既有兩行後面附加「（例：
  XYZxxxB／XYZxxxC）」，其餘逐位元不變。T01（#218）數值基準未受
  影響——`ranking.py`／`valuation.py` 零改動。全套後端測試綠燈
  （記憶體＋真實 Postgres 雙後端）；前端 typecheck／678 條 Vitest／
  build 皆過；Playwright e2e 92 條（iPhone＋Desktop）全綠。**#226
  已 close**。

- **T07**（#224，commit `1bc4153`＋跟進 `f993884`）✅ per-family 代表
  候選與最高報酬落盤（additive）——Owner 裁示「B 儲存＋A 顯示」：
  顯示面本輪維持單一個跨 family 冠軍，儲存面額外把每個 family 各自
  的代表候選與最高報酬也落盤。`option_chaser/store.py` 新增
  `representative_candidates_by_family(view)`：與既有
  `representative_candidate()` 同一次走訪、同一個候選池（抽出共用
  `_baseline_group()`／`_project_representative_row()` 兩個私有函式，
  既有函式行為逐位元不變），只是依 family（`STRATEGY_FAMILY` 對照表）
  分組各自取最大值。一致性保證（AC 要求：per-family map 取 max 後
  等於 scalar 冠軍）是代數性質、非巧合。`api_app/storage/__init__.py`
  的 `ResultRecord`／`ResultSummary` 新增 `per_family: dict | None =
  None`（純加法，落盤層 `None` 語意與既有 `representative_candidate`
  一致）；`postgres.py` 的 `results` 表新增 `per_family JSONB`，沿用
  既有「建表與遷移分兩批送」教訓；`memory.py` 補上轉遞。
  `main.py::_refresh_and_save()` 接上——卡片列（`_row_json`／
  `_summary_of`）刻意未觸碰，AC 明文「清單排序與卡片讀取端零改動」。
  `/code-review` 兩軸：Spec 軸零缺漏、零 scope creep；Standards 軸
  抓到一個真重複（`_refresh_and_save()` 原本各自獨立呼叫兩個函式、
  各自重掃一次候選池），已在跟進 commit 修正為只呼叫 per-family
  版本一次、scalar 冠軍改用 `max()` 從中導出（與既有 `best_return()`
  由 `representative_candidate()` 導出、`main.py` 內聯避免重複走訪
  同一種既有作法）。新增 10 條測試（純函式 5 條、儲存契約 4 條、
  端到端 wiring 1 條），全套後端測試綠燈（記憶體＋真實 Postgres
  雙後端）。純後端／儲存層改動，未觸碰任何前端檔案與 API 契約序列化。
  **#224 已 close**。

- **T08**（#225，commit `58ed4df`＋跟進 `3db3198`）✅ 衍生三態方向與
  per-subtype eligibility（family verdict＝OR）——把方向判斷從硬編碼
  的兩個策略名字表換成 per-subtype 的方向適用性資料，方向本身成為
  衍生的三態（看漲／看跌／持平），由目標價位相對現價在分析當下算出、
  永不落盤、永不進事件。`option_chaser/models.py` 新增
  `DIRECTIONS`／`SUBTYPE_DIRECTIONS`（每個 subtype 適用哪些方向的
  靜態資料表，新增 subtype 只需加資料不需改判斷邏輯）／
  `derive_direction()`（無容忍帶）／`subtype_eligible()`（純查表）／
  `FamilyEligibility` dataclass＋`family_eligibility()`（OR 投影，
  不可選附帶原因文字，兩種成因分開表達）。`is_bullish()` 改為資料
  驅動但保留簽章與行為（服務 Heatmap／CLI 報告價格軸走向這類與
  eligibility gate 無關的既有用途，明確標註為本票範圍外、留言註記
  T15 的 flat-only subtype 出現後需重新檢視）。`service.py::_analyze()`
  的閘門改為方向算一次、逐 subtype 查 `subtype_eligible()`；
  `_skip_message()` 改用資料反查產生訊息，沿用既有 `skipped_direction`
  機制。`store.py::serialize_result()` 新增頂層 `family_eligibility`
  （涵蓋全部 `FAMILIES`，`schema_version` 5→6，純加法）。`src/api.ts`
  新增對應型別。`/code-review` 兩軸：Spec 軸零缺漏零 scope creep（手動
  逐一核對新舊閘門在全部方向×subtype 組合下判定相同，含 `target==
  spot` 邊界）；Standards 軸三項 judgement call 已於跟進 commit 處理
  （`is_bullish` 二元本質留言註記、`_family_eligibility_map` 跨模組
  隱性前提補說明、`_skip_message` 迴圈重複消除）。新增 24 條測試
  （純函式三態／per-subtype／OR 投影／bytecode 結構驗證／閘門端到端／
  契約覆蓋）。全套後端測試綠燈（記憶體＋真實 Postgres 雙後端），T01
  數值基準未受影響。前端 typecheck／678 條 Vitest／build 皆過。
  **#225 已 close**。

- **T10**（#227，commit `9fa6c6c`＋跟進 `a617d1c`）✅ 建立／編輯表單的
  Strategy Family 勾選與 eligibility 呈現——使用者第一次可以自己決定
  這個劇本要看哪幾類策略。`CreateScenarioRequest`／
  `EditScenarioRequest` 新增必填 `strategies: list[Literal[FAMILIES]]`
  （`Field(min_length=1)`，白名單本身就是型別，沿用既有
  `AnalyzeRequest.strategies` 同一種寫法）。`create_scenario()` 移除
  寫死的 `_MVP_STRATEGIES`；`edit_scenario()` 編輯表單永遠送出目前
  完整勾選集合，`thesis_changed` 新增 family 比較（改變視同 thesis
  改變、清掉舊結果），兩邊比較前正規化成 family 避免 legacy subtype
  字串誤判。`ResultRecord`／`ResultSummary` 新增 `family_eligibility`
  （與 T07 `per_family` 同一個模式，額外落盤供編輯表單讀取不必打
  detail 端點），Postgres schema 沿用「建表＋遷移分兩批送」教訓；
  `_refresh_and_save()` 直接讀 T08 已算好的 `view["family_
  eligibility"]`。前端 `CreateForm.tsx` 新增 Strategy Family
  checkbox 群組（`role="group"`＋`aria-labelledby`，比照
  `MonthPicker` 既有寫法）；`validateDraft()` 新增「至少勾選一個」
  驗證；不可選的 family 顯示後端 verdict 的原因文字（前端零計算），
  checkbox 本身仍可勾選，只有事實陳述、不做推薦。`/code-review`
  兩軸：Spec 軸零缺漏零 scope creep；Standards 軸一項 judgement call
  （`thesis_changed` 兩側正規化不對稱缺行內註記）已於跟進 commit
  處理。新增後端 24 條測試、既有 10 個測試檔補上必填 `strategies`
  欄位、前端新增 13 條元件測試、E2E 新增 6 條（手機＋桌面各 3 條）。
  全套測試綠燈：後端（記憶體＋真實 Postgres 雙後端）、前端
  typecheck／692 條 Vitest／build、Playwright e2e 98 條。詳細頁的
  多 family 呈現留給 T11（票上明文範圍，未觸碰）。**#227 已 close**。

- **T11**（#229，commits `d19dfa9`＋跟進 `2cbf3d9`）✅ 詳細頁 family
  tab——多 family 並存呈現，Call / Put 端到端可用。每個啟用的 family
  一個分頁（新增 `src/FamilyTabs.tsx`），分頁內部維持既有「依到期日
  分組」結構與版面完全不變（`ExpiryStructure` 零改動複用）；同一
  family 底下不同 subtype 的候選合併進同一個排名池（新增
  `family.ts::mergedExpiryTop10()`，依 `baseline_return` 重排、逐
  到期日各取前十，跟後端 `expiry_top10` 自己「排序取前 N」是同一種
  選取操作，不是新的財務推導），畫面上不依 subtype 分區；每個候選在
  `ExpiryStructure` 的候選列標示它實際的 subtype（後端 `strategy`
  欄位早就序列化，前端補上型別宣告即可讀取）。不可選的 family 一樣
  有分頁、點得進去看得到 eligibility 給的原因（facts-only）。單一
  family 時完全不畫分頁列，既有單一 family 劇本畫面逐位元不變。

  頭條數字＝跨 family 冠軍（新增 `family.ts::championCandidate()`），
  與主圖／摘要卡固定顯示同一組候選，不隨分頁切換而改變——沿用
  QA1-06「主圖就是主圖，不跟著別處的互動改變」既有原則，延伸到
  family 這個新維度。這是 AC 明文要求的「口徑升級」，已在
  `CONTEXT.md` 新增「Family Tab」一節明文記錄，不是靜默發生。

  **施工中發現並修正一個真實 bug**（Initial V2 尚未發布，不影響
  production master）：T06（#221）家族展開後，`view.results` 的順序
  固定跟隨 `subtypes_of()` 展開順序、不看方向——`bull-call-spread`
  固定排在 `bear-put-spread` 之前，於是**方向不合被擋掉的那個
  subtype 反而可能排在陣列前面**（bearish 劇本裡 `bull-call-spread`
  是 `skipped_direction`、`bear-put-spread` 才是真正有候選的那個，
  卻排在它後面）。用真實 HTTP 路徑（`create_app()` + `xyz_v5_put_
  ladder.json` fixture）重現過這個排列，舊版 `primaryResult(view) =
  results[0]`／`baselineTopCandidate()` 因此會挑到 `skipped_
  direction` 那筆、顯示「無合格候選」——`championCandidate()` 改為
  逐一掃過 `view.results` 找 `status==="ok"` 的再比大小，天然修正
  此問題；已記錄在 `CONTEXT.md`「Family Tab」一節與 `family.test.ts`
  的專屬回歸測試裡。

  其餘結構性改動：`CandidatePool` 改由呼叫端明確傳入 `result`（不再
  自己用 `primaryResult(view)` 猜，多 family 並存後這個假設不成立）；
  `ExpiryStructure`／`expiry.ts` 的 `result` 參數窄化為新型別
  `ExpiryBearing`（`Pick<StrategyResult, "expiry_top10"|"expiry_
  counts">`），讓合併後的排名池不需要假造一份其餘欄位無意義的完整
  `StrategyResult` 即可直接餵入；`Candidate` 型別新增 `strategy`
  欄位（後端早已序列化，純加法宣告）。

  `/code-review` 兩軸：Spec 軸 11 條 AC 全數 done、零 scope creep，
  唯一前瞻性提醒（`CandidatePool`／`AnalysisReport` 今天只吃
  `okResults[0]`，等 T15／#230 真的出現雙 subtype 同時 ok 才需要
  重新檢視）已寫進 `family.ts` 檔頭，不在本票範圍處理；Standards
  軸三項判斷已於跟進 commit 處理（兩份測試檔逐字重複的假體建構式
  抽成共用 `src/family.fixtures.ts`；`e2e/smoke.spec.ts` 補型別消除
  一處 `as any`；`FamilyTabs.tsx` 分頁按鈕改用語意正確的
  `.chip-label`，不再借用專屬到期日文字的 `.chip-date`）。

  全套測試：前端 typecheck／724 條 Vitest（新增 `family.test.ts`
  20 條、`FamilyTabs.test.tsx` 9 條、`ScenarioDetail.test.tsx` 新增
  3 條多 family 端到端案例）／build 皆過；Playwright e2e 101 條
  （iPhone 63＋Desktop 38）全綠；後端全套 1590 條維持通過（本票零
  Python 檔案變動）。

- **T13**（#231，commits `9a97b13`＋跟進 `049a025`）✅ 詳細頁 payload
  投影與 top-N 上限——完整候選序列不上 wire。新增純函式
  `store.project_for_detail(view: dict) -> dict`，只在
  `api_app/main.py::get_scenario()`（`GET /api/scenarios/{id}`）這
  一個 HTTP 端點套用，`serialize_result()`／落盤的 `ResultRecord.view`
  本身逐字未動。

  **真正的體積來源已鎖定並移除**：`results[].candidates`——引擎全量
  候選 key 清單，未經任何上限裁切，會把每一筆通過過濾的候選都拉進
  `candidate_pool`，遠遠超出 `expiry_top10` 每期前十名的既有上限，
  這才是「每多啟用一個 spread 策略就多約 495KB」的真正成因；
  `results[].all_candidates`（V9 Spread 淨成本走勢的歷史序列）同樣
  移除——前端 `src/api.ts` 的 `StrategyResult`／`Candidate` 型別從
  未宣告過這兩個容器欄位，移除對前端零影響。候選池只保留還被
  `expiry_best`／`expiry_top10`／`expiry_groups`／`default_selection`／
  `baseline_selection` 引用到的鍵（`serialize_result()` 裡全部四個
  `cand_key(` 呼叫點都涵蓋），這些容器加總起來已被引擎既有規則限制
  在「到期日數 × 10」量級，移除那兩個無界欄位後上限是結構上自動
  成立的，不需要另外寫檢查邏輯。

  `expiry_groups`（v4 舊「到期日分組比較」結構）**刻意保留**：本身
  很小（每個到期日×策略只有一列，不是候選序列），且
  `representative_candidate()`／`best_return()` 需要它才能對任何
  view dict 正常運作——`test_api_scenarios.py` 既有測試就是這樣呼叫
  的，移除會直接弄壞它們。

  修正一條既有測試（`test_strategy_family.py`）：原本透過 HTTP 回應
  驗證 family 展開後的位元組相同性，現在改讀 `storage.latest_result
  (sc_id).view`（落盤那份，未經投影）——這正是 AC「儲存的內容維持
  全保真」該用的驗證方式，比先前透過 HTTP 回應間接驗證更貼近實際
  保證的對象。

  新增 `tests/test_detail_projection.py`（12 條）：HTTP 層驗證回應
  不含完整候選序列、候選池無孤兒項目、候選數上限、`representative_
  candidate()`／`best_return()` 對投影後的 view 仍正確運作、V9／V8
  兩個既有端點（`/history`／`/raw-data`）走 storage 直接讀取不受
  影響；純函式層驗證不修改輸入、`default_selection`／`baseline_
  selection` 引用的候選仍可解析、空 view 邊界情況。真實量測
  （`xyz_v4_six_expiries.json`，single-leg ＋ vertical-spread 兩個
  family 皆啟用）：66,495 → 64,271 bytes（縮減 3.3%）——這份測試
  fixture 刻意精簡（跑得快），縮減幅度遠低於票上引用的 production
  觀察值，測試斷言只鎖「結構性修法確實生效」，不編一個這個 fixture
  量不出來的百分比門檻。

  `/code-review` 兩軸：Spec 軸 8 條 AC 全數 done、零 scope creep、
  零 concern；Standards 軸兩項判斷已於跟進 commit 處理（一條測試
  多餘的本地 import 別名改回一致寫法；docstring 補一句說明
  `expiry_groups` 的防禦性引用收集不是依賴子集關係才可省略）。

  全套測試：後端全套 1602 條通過（記憶體＋真實 Postgres 雙後端，
  1590 + 12 條新增）；前端本票零檔案變動，typecheck／724 條
  Vitest／build／Playwright e2e 101 條（iPhone 63＋Desktop 38）全數
  重跑確認無回歸（移除的三個欄位前端從未宣告型別、從未讀取，投影對
  前端結構上不可見）。

- **T14**（#233，commits `048e4e1`＋跟進 `739d1d5`）✅ 熱力圖 matrix
  傳輸壓縮——座標軸去重＋格值緊湊編碼（研究 #216 定案的「組合一」）。
  `option_chaser/store.py` 新增 `axis_pool`／`axis_sets`／`axis_of()`
  closure（比照既有 `cand_key()`／`pool` 候選去重手法），把候選
  `matrix`／`comparator.matrix` 從 `{prices, dates, cells}`（二維）
  換成 `{axis_index, cells}`（`cells` 攤平成一維＋捨入到
  `MATRIX_CELL_DECIMALS`＝4 位小數，遠細於畫面顯示精度）；`prices`／
  `dates` 只在第一次遇到某組座標時序列化進頂層新增的 `axis_sets`，
  其餘候選（含候選自己的 Crossover comparator）改存索引引用。
  `schema_version` 6→7。

  真實去重效果（`tests/test_matrix_compression.py` 新增 5 條測試，
  皆用真實 fixture 而非合成小物件證明）：同一到期日 9 組候選共用 1
  組軸；跨到期日的軸數與到期日數同量級，不隨候選數線性成長；候選
  自己的 Crossover comparator 與候選本身的 matrix 共用同一個
  `axis_index`（不是各自序列化一份）；捨入誤差上界（0.5×10⁻⁴）逐格
  核對小於畫面一位小數百分比顯示精度的半格（0.0005）。契約樣本三份
  實測（本地量測，非推估）：`analysis_sample.json` 55,808→38,612
  bytes（−30.8%）、`analysis_sample_bear_put.json` 56,248→38,749
  bytes（−31.1%）、`analysis_sample_long_call.json` 71,881→54,183
  bytes（−24.6%）。

  前端：`src/heatmap.ts` 新增純解碼函式 `resolveMatrix()`／
  `resolveComparator()`（查 `AnalysisView.axis_sets` 把攤平的
  `cells` 依日期數切回二維；`"axis_index" in wm` 為假時原樣透傳——
  T09（#191）既有「舊存 View 不做資料遷移」裁示的延伸，讀取端維持
  相容，新舊形狀共用 `WireMatrix` 聯集型別）；`Heatmap.tsx` 本身
  維持只吃已解碼的完整 `Matrix`／新型別 `ResolvedComparator`，解碼
  動作收斂在 `ExpiryStructure.tsx`（候選展開清單）與
  `ScenarioDetail.tsx`（主圖）兩個既有呼叫點——前端零金融計算，只做
  解碼與格式化。

  `/code-review` 兩軸：Standards 軸抓到上述兩個呼叫端原本各自重複
  同一段「解碼＋單腿候選不傳 comparator」判斷（Duplicated Code），
  已收斂成 `heatmap.ts::heatmapProps(view, candidate)`，兩處呼叫點
  改為 `<Heatmap {...heatmapProps(view, candidate)} />`——「只有兩腿
  候選才有 Crossover comparator 概念」這條規則現在只寫在一個地方，
  未來出現第三個呼叫端（例如 Butterfly 三腿展示，T16／#232）時也
  只需要呼叫這裡；同軸另抓到一條測試命名與斷言不符（宣稱「量測並
  記錄」，實際斷言只驗證去重比例的結構性前提），已更名為
  `test_contract_samples_also_exhibit_axis_dedup`。Spec 軸確認核心
  機制忠實、零 scope creep（無 base64 Float32、前端未從任何「種子」
  重算格值），唯一提到的「記錄」缺口（AC 要求記錄壓縮前後大小，
  commit 訊息當時已記但 CLAUDE.md 尚未更新）已隨本節一併補上。

  T01（#218）數值基準第五個合法重產事件：只有 `matrix`／
  `comparator.matrix`／新增 `axis_sets` 欄位改變，其餘估值全數欄位
  逐位元不變（已用腳本逐鍵比對，非只看測試綠燈）。全套測試：後端
  （記憶體＋真實 Postgres 雙後端）綠燈；前端 typecheck／732 條
  Vitest（新增 3 條）／build 皆過；Playwright e2e 101 條（iPhone＋
  Desktop）綠燈，含既有熱力圖既有呈現（價格軸／日期軸／±% 右欄／
  橫向捲動／Crossover 邊界疊色）逐一確認不受影響、候選展開零額外
  網路請求。

- **T15**（#230，commits `008ae99`＋跟進 `72e25c5`）✅ Butterfly
  後端：枚舉、獲利區間、兩個損益兩平點——地圖 #209 收斂的三個 debit
  family 中最後一個尚未接線的結構，端到端可用。

  `option_chaser/valuation.py` 新增 `ButterflyValuation`／
  `ButterflyProfitRegion`／`butterfly_expiry_payoff()`（到期 payoff
  純算術）／`butterfly_breakeven_and_profit_region()`（封閉式代數
  直接求兩個損益兩平點與獲利區間，**不透過任何通用求根／extrema
  引擎**——沿用 #223 已收斂的裁示：「買一賣二買一」結構的分段線性
  斜率恆為 ±1 是這個特定權重組合才有的不變量，不是任意 N 腿的
  一般化性質，因此可以用封閉式代數求解，不需要 #223 兩次被否決的
  那種 payoff-envelope／slope／tail 分析）／`butterfly_scenario_value()`
  （複用 T02／#219 已核准的 `payoff_value()`／`WeightedLeg` 逐腿加總
  原語，非新引擎）／`evaluate_butterfly()`（`evaluate_spread()` 的
  三腿版本，worst 成交口徑、排名情境＝自身到期日等於目標價）。

  `option_chaser/filters.py` 新增 `generate_butterfly_triples()`
  （依到期日分組、`itertools.combinations(group, 3)`，A 層
  `net_mid<=0` 檢查）；`validate_derived_values()` 新增選填
  `max_loss_fn` 參數（#213 Addendum：defined-risk candidate 的
  max_loss 必須 > 0，向下相容不影響既有四策略）。

  `option_chaser/ranking.py`／`scenarios.py` 三分支擴充（`_value_fn`／
  `natural_cost`／`valuation_key`／`_strategy_of`／`_expiry_of` 等既有
  isinstance-dispatch 慣例延伸為三路）；`completion_scan()` 對
  `ButterflyValuation` **短路直接回 `(None, None)`**——既有「從
  k=1.0 反向掃描」演算法假設 payoff 沿掃描路徑單調，對 Butterfly
  硬套會誤報「劇本全成仍不保本」，Owner Decision 已明訂用
  `profit_region` 取代，兩者互斥出現（單調家族恆 `completion_
  threshold`／`breakeven_at_target` 有值＋`profit_region` 為 None，
  Butterfly 恆相反）。

  `option_chaser/service.py` 新增 `_butterfly_result()`（`_spread_
  result()` 的三腿鏡射：枚舉→估值→A/B 層驗證→排名→序列化，
  `expiry_top10`／`expiry_best`／`expiry_ranked` 從第一天就落盤，
  不是留給未來的空殼）與 `_butterfly_view()`／`_butterfly_leg_
  greeks()`；`CandidateView` 新增 `profit_region` 欄位（純加法）；
  `_comparison()` 新增 Butterfly 分支。

  `option_chaser/store.py::_candidate()` 三分支擴充：`legs[]` 三腿
  （`side`／`quantity`，T12／#228 打的底）、`breakeven_points` 兩點、
  **`max_loss_per_contract` 獨立於 `capital_per_contract`**——AC
  明文性質：broken-wing（兩翼不等寬）到期時某一翼可能為負值，讓
  最大損失超過已付權利金本身，既有四策略「max_loss 恆等於成本」
  這條不變量在 Butterfly 上不成立，契約層如實反映不假裝相等；新增
  `profit_region` 頂層候選欄位（純加法，頂層 `schema_version` 未變，
  只加候選層欄位）。

  `option_chaser/report.py`／`cli.py`：`render_butterflies()`（列
  三腿、獲利區間或誠實文案「無——到期時任何標的價都無法獲利」）；
  `STRATEGY_LABELS` 補 call-fly／put-fly；新增 byte-locked golden
  fixture `golden_call_fly.txt`。`src/detail.ts` 補兩個新 subtype
  的前端顯示標籤（本票唯一前端改動）。

  **`/code-review` 兩軸結果與修正**（跟進 commit `72e25c5`）：Spec
  軸零缺漏零 scope creep；Standards 軸兩項發現皆已修正——(1)
  `evaluate_butterfly()` 與 `butterfly_breakeven_and_profit_region()`
  原本各自獨立算 K1/K2/K3 到期 payoff 節點（v1/v2/v3）共兩遍，抽出
  `_butterfly_knots()`（算一次節點）與 `_butterfly_region_from_
  knots()`（吃現成節點的核心判斷邏輯），後者維持公開簽章不變的
  `butterfly_breakeven_and_profit_region()` 內部委派使用，
  `evaluate_butterfly()` 改直接呼叫 `_butterfly_region_from_knots()`
  複用同一組節點——`butterfly_expiry_payoff()` 呼叫次數從每次
  `evaluate_butterfly()` 6 次降到 3 次；(2) `_comparison()` 的
  Butterfly 分支在沒有損益兩平點時（到期時連峰值都賺不到）用
  `bv.low_leg.strike` 當 `ComparisonRow.breakeven` 這個既有 scalar
  欄位的佔位值，抽成具名變數並加註解澄清這不是真正的損益兩平點，
  避免讀者誤讀。

  新增 45 條專屬測試（`test_butterfly_valuation.py` 20、
  `test_butterfly_triples.py` 4、`test_butterfly_service.py` 12、
  `test_butterfly_store.py` 6、`test_butterfly_performance.py` 3），
  新增獨立中密度契約樣本 `contracts/analysis_sample_call_fly.json`
  （241KB——密集效能測試 fixture 若拿來產樣本會撐到 2.5MB，改用
  `scripts/gen_butterfly_fixture.py` 額外產生的中密度版本）。效能
  量測（密集 fixture，26 履約價×5 到期日）：枚舉 3.7ms/13000 組合、
  完整估值 373.2ms/9998 組合、端到端 435.7ms。T01（#218）數值基準
  第六個合法重產事件：只新增 `profit_region: null` 欄位本身（既有
  四策略永遠是 `None`），其餘既有四策略估值全數欄位逐位元不變。

  全套後端測試（記憶體＋真實 Postgres 雙後端）1660 條全數通過；
  前端 typecheck 乾淨、732 條 Vitest／build／Playwright e2e 101 條
  （iPhone＋Desktop）皆過（本票除 `src/detail.ts` 標籤新增外未觸碰
  任何前端檔案）。

- **T16**（#232，commits `c8e49b3`＋跟進 `dec724b`）✅ Butterfly
  前端呈現：三腿完整顯示、兩個損益兩平點、獲利區間、淨成本走勢圖，
  端到端可用——純前端票，**零 Python 檔案異動**（T15／#230 後端已
  就緒，`git diff` 確認）。

  施工中查證到三個真缺口，皆修正（非 AC 字面新增）：(1)
  `family.ts::SUBTYPE_FAMILY` 漏掉 `call-fly`／`put-fly`（T15 是純
  後端票，依票面範圍未動這個檔案，檔頭本就留有「新增 subtype 時記得
  同步」的提醒；不修的話 Butterfly 候選會被歸進錯誤 family、預設分頁
  選不對）——已補上兩筆映射，新增回歸測試（含「冠軍是 Butterfly 時
  預設打開 Butterfly 分頁」的端到端場景）；(2) `AnalysisReport.tsx`
  的 Max Loss 列原本讀 `natural_cost`（既有四策略「max_loss 恆等於
  成本」不變量的既有假設），Butterfly broken-wing 組合的真實最大
  損失可能超過已付權利金（T15 AC 明文性質）——改讀
  `max_loss_per_contract / 100`：對既有四策略逐位元相同（已驗證），
  對 Butterfly 才是誠實數字，這是跨全部策略的共用元件改動、非只影響
  Butterfly，已在測試中明確驗證等價性；(3) `IvHistory.tsx` 的兩個
  既有家族（Normalized Skew／逐腿 Historical IV Trend）結構上只認得
  單腿與兩腿——後端 `ivpipeline.build_iv_history()` 的 `leg_names =
  ("buy","sell") if len(legs)>=2 else ("buy",)` 對三腿候選會靜默丟掉
  第三隻腿、把中腿誤標成「賣腿」，新增 `supportsIvHistory` 閘門讓
  Butterfly 候選一個 IV 請求都不發、不輸出任何 DOM 節點——這是 #215
  Owner Decision「Vertical／Butterfly 的『貴不貴』區塊整塊不顯示」的
  字面落地（該裁示指的是尚未建置、本輪也不建置的 package percentile，
  不是要藏起既有描述性功能，但既有功能本身只認得 ≤2 腿，因此必須在
  請求層擋下 Butterfly）；修正管線本身讓它認得三腿是另一張票的範圍。

  正式新增：`api.ts` 的 `Candidate.breakeven` 拓寬為 `number | null`
  （Butterfly 到期時連峰值都賺不到時如實回傳 null）＋新增
  `profit_region: [number, number] | null`＋共用的 `legSide()`／
  `legQuantityPrefix()`；`detail.ts::candidateTitle()` 口數 > 1 的腿
  標出倍數（`賣 2×106`，沿用後端 `service._comparison()` 既有的
  `2×{strike:g}` 語法）；`expiry.ts::legPriceEntries()` 逐腿最差成交
  價，三腿以上不會有任何一隻腿被靜默丟棄，既有 `legPrices()`（兩腿／
  單腿摘要）原封不動；`ExpiryStructure.tsx` 候選窄列收合狀態的價格
  摘要三腿以上改逐腿列出；`AnalysisReport.tsx::BreakevenRow` 0 點
  誠實顯示「無（到期時任何價位都無法獲利）」、1 點沿用既有格式、
  2 點顯示兩個損益兩平點＋獨立的「獲利區間」列。

  `/code-review` 兩軸結果與修正（跟進 commit `dec724b`）：Spec 軸零
  缺漏零 scope creep（未觸碰 T17／T18 範圍：無 flat-scenario
  eligibility gating、無 final regression 程式碼；唯一標記的「Max
  Loss 讀法是跨全部策略的共用元件改動」已確認安全並記錄）；Standards
  軸零 hard violation，四項 judgement call 中三項已修正——(1)
  `candidateTitle()`／`legPriceEntries()` 重複的方向／口數標示邏輯
  抽到 `api.ts` 共用（比照既有 `findLeg()` 同一次 Standards 軸抓到、
  同一個檔案收斂的先例）；(2) `ExpiryStructure.tsx` 的
  `legs.length > 2` 命名為 `isMultiLeg`（刻意不與 `IvHistory.tsx` 的
  `supportsIvHistory` 共用常數——兩者今天數值相同但語意不同，一個是
  「收合摘要版式該用哪一種」的 UI 呈現決定，一個是「IV pipeline
  結構上支援哪些腿數」的後端能力邊界，強行共用會製造不存在的耦合，
  已記錄判斷）；(3) `candidate-prices` 重複兩次的「淨成本」span 收斂
  為一次。第四項（`breakeven` 型別拓寬後前端無直接讀取端）判斷維持
  現狀——那是契約型別的誠實反映，不是投機性彈性。

  新增 16 條 Vitest（`detail.test.ts`／`expiry.test.ts`／
  `AnalysisReport.test.tsx`／`IvHistory.test.tsx`／
  `ExpiryStructure.test.tsx`／`family.test.ts`／`FamilyTabs.test.tsx`）
  ＋6 條 Playwright（iPhone 5＋Desktop 1，涵蓋三腿渲染、兩個損益兩平
  點、獲利區間、展開零額外請求、IV History 不出現、淨成本走勢圖
  支援）。全套：後端零改動（1660 條測試不受影響，`git diff` 確認）；
  前端 typecheck 乾淨、747 條 Vitest、build 通過、Playwright e2e
  107 條（iPhone 67＋Desktop 40）全綠，桌面與手機兩個 viewport 皆
  驗過。

- **T17**（#234，commits `c775735`＋跟進 `1d17f5d`）✅ 持平劇本
  （`target_price == spot`）：方向閘門這半**零程式碼改動**——T08
  （#225）既有的 `derive_direction()`／`SUBTYPE_DIRECTIONS`／
  `subtype_eligible()`／`family_eligibility()` 早已是完全資料驅動的
  三態設計（`bullish`/`bearish`/`flat`），`call-fly`／`put-fly` 在
  T15（#230）就標好 `{bullish,flat}`／`{bearish,flat}`，
  `service.py::_analyze()` 呼叫這些函式時本就正確處理 flat 情境。
  真正要修的是 spec #217 §F／§P.5 點名的既有地雷——**價格網格塌陷**：
  `option_chaser/scenarios.py` 的 `_grid_price()`／`scenario_vector()`
  的 S2–S5／`_delay_value()`／`completion_scan()` 全部依賴「spot 走到
  target」這條線性插值路徑取樣，`target == spot` 時路徑長度為零，
  全部取樣點塌成同一個價格（spot 本身），韌性指標因此退化失真。

  修法：新增 `_effective_target(spot, target)`——`target != spot` 時
  原樣回傳 `target`（既有看漲／看跌劇本這條路徑逐位元不變，T01
  基準）；只有 `target == spot` 才換成合成終點 `spot * 1.15`（沿用
  `matrix.price_axis()` 無最高／最低價位時既有預設路徑已核准的同一個
  15% 係數，該處算的是 `target * 1.15`，兩者只在 `target==spot` 這個
  分支下數值相同，基底名字不同）。`_grid_price()`／`scenario_vector()`
  ／`_delay_value()` 內部改呼叫這個函式；S1（不漲＝spot 本身）與
  S6/S7（劇本成立時的真實 target_price 評價點，flat 時就是 spot）
  完全不受影響——這三點的既有語意本來就不是退化。`completion_scan()`
  既有的 Butterfly 短路（`isinstance(val, ButterflyValuation): return
  None, None`）未受影響，那是非單調 payoff 的既有正確行為（由
  `profit_region` 取代），不是本票要修的東西；CLI `--force` 讓非
  Butterfly 候選觸發這條路徑的邊界情況，因為修法在 `_grid_price()`
  內部，透明涵蓋、不需另外處理。

  測試：`tests/test_scenarios.py` 新增 7 條單元測試（`_effective_
  target` 只在退化情境生效、`_grid_price` 不再塌縮、flat Butterfly
  的 `scenario_vector`／`completion_curve` 產生非退化多值、
  `completion_scan` 對 flat Butterfly 仍正確短路、對 CLI-forced flat
  單腿仍滿足 suffix property）；`tests/test_family_selection.py` 新增
  一條端到端整合測試（真的建立 `target_price==spot` 的劇本跑分析——
  4 個非 Butterfly subtype 全部 `skipped_direction`，Butterfly 至少
  一個 `ok` 且候選非退化，二次 refresh 同樣成功）；`e2e/smoke.spec.ts`
  ／`e2e/desktop.spec.ts` 各新增一條端到端案例，真的走 CreateForm UI
  建立 flat 劇本，全程不被拒絕、看得到 Butterfly 候選、Call/Put 與
  Vertical Spread 分頁顯示「持平」原因且不可選。

  施工中順手修正一個真實、與 T17 無關的既有 e2e flake：T16 的「展開
  Butterfly 候選零額外請求」測試在全套跑時偶發失敗（React StrictMode
  在 Vite dev server 下把 `IvHistory.tsx` 的 settings-fetch effect
  重複觸發一次，Playwright `webServer` 跑的是 `npm run dev` 非
  production build），兩個 spec 檔皆補上
  `page.waitForLoadState("networkidle")` 讓 StrictMode 重複觸發的
  請求先落定再歸零計數器，重跑 5 次穩定通過。

  `/code-review` 兩軸：Standards 軸零 hard violation，三項 judgement
  call（15% 常數說明精確度已修正、`_effective_target` 三處獨立呼叫、
  函式命名自我說明性）；Spec 軸抓到一個真問題——編輯
  `tests/test_scenarios.py` 尾端追加新測試時，意外刪除一條既有、與
  T17 無關但仍有效的斷言（`test_completion_scan_suffix_semantics_
  synthetic` 的 `be == pytest.approx(...)`），直接牴觸本票自己「T01
  基準逐位元不變」的宣稱——已用 `git log -p` 核對基準版本確認該行
  原本存在且數學上依然成立，已補回。兩項修正皆在跟進 commit
  `1d17f5d` 完成。

  全套（跟進 commit 之後重新驗證）：後端 pytest（記憶體＋真實
  Postgres 雙後端）全綠；前端 typecheck 乾淨、747 條 Vitest 全綠、
  build 成功；Playwright e2e 109 條（iPhone 58＋Desktop 34）全綠。

- **T18**（#235，commits `3125611`＋`822d165`）✅ 全面回歸與最終
  驗收——Initial V2 最後一張票，純驗證＋補測試缺口，未新增任何
  production 程式碼。

  用兩個背景 agent 分工稽核 spec #217 Testing Decisions 章節列出的
  12 條硬回歸紅線（每條要求列出守它的測試），逐條對照結果：10 條
  完全有測試把關（含逐一核對「沒有斷言被弱化」——`git diff`
  自 T01 開工前的 `22b9d4b` 至今，後端 17 行、前端 24 行被刪除的
  `assert`/`expect()`，全數對照為 spec 明文要求的結構性變更如
  friction 退場、`Scenario.strategies` 改存 family、`schema_version`
  升版等，無一為單純放寬）；**2 條發現缺口並補齊**：

  - **紅線 8**（導出 max_loss≤0 的候選不出現在排名中，且留下
    diagnostic）：Butterfly 路徑此前只有機制層測試，未經真實
    `service.run_offline()` wiring 驗證。深入查證發現一個數學事實
    ——`evaluate_butterfly()` 的 `max_loss = net_worst - min(v1,v3)`，
    call-fly 到期時 K1 那一點三腿恆為 OTM/ATM（`v1` 恆為 0），配合
    A 層 `bid<=ask` 前提與既有配對層 `net_mid<=0` 門檻，可證明任何
    撐過既有門檻的三腿組合 `max_loss>0` 在數學上已經保證成立——無法
    用任何真實報價構造出反例。新增兩條測試：一條證明性測試（惡意
    構造三組報價含逼近邊界案例試圖找反例，全數失敗，其中一組近零
    價差案例 `max_loss=0.002` 逼近邊界但從未跨界）；一條 wiring
    測試（monkeypatch `service.evaluate_butterfly()` 對真實候選注入
    `max_loss=-1.0`，證明排除機制與 diagnostic 身份揭露確實接上）。
  - **紅線 12**（任一前十名候選展開熱力圖零額外請求）：既有測試
    （T16／#232）只用 Butterfly 候選驗證過，字面「任一」未涵蓋。
    新增手機＋桌面各一條，改用一般 Vertical Spread 候選重複同一套
    斷言。

  `/code-review` 兩軸：Spec 軸零缺口（獨立重新驗算紅線 8 的數學論證
  通過、確認 wiring 測試兩半都驗到、確認 e2e 用的是非 Butterfly
  樣本、零 scope creep）；Standards 軸三項 judgement call 已修正
  （desktop.spec.ts 補回原本只在 smoke.spec.ts 出現的完整說明文字、
  改掉會隨編輯漂移的行號交叉引用、`poisoned()` 內聯組出的身份字串
  改呼叫共用的 `triple_key()` 消除重複定義來源）。

  Out of Scope 逐項 grep 確認：credit 三兀／Iron Condor／straddle／
  calendar／covered call／推薦評語／package percentile／prefetch／
  多使用者隔離／N-leg（`legs[]` 有結構性 `1<=len<=4` 上限強制）／
  新 friction 指標，皆無違反。

  新增 `docs/initial-v2-acceptance-checklist.md`（比照既有
  `docs/v10-acceptance-checklist.md` 慣例），逐條列出三個 family
  建立與瀏覽、持平劇本、Butterfly 三腿與獲利區間、熱力圖展開、舊
  劇本相容、桌面與手機版面，標明哪些已由自動化覆蓋、哪些需要需求方
  親自用真機確認。

  全套：後端 pytest（記憶體＋真實 Postgres 雙後端）全綠；前端
  typecheck 乾淨、747 條 Vitest 全綠、build 成功；Playwright e2e
  111 條（iPhone 59＋Desktop 34＋T18 新增 2 條）全綠，連續兩輪穩定
  無 flake。

  **AC9（需求方真機驗收通過才算完成）為唯一未完成項目**——已在
  issue #235 留言完整回報，issue 保留 open、不強行關閉（這是它自己
  AC 明文的完成條件，不是 agent 能代勞的動作）。

**Initial V2（spec #217，T01–T18，issues #218–#235）工程與自動化
驗證面全數完成。** 依專案規則不主動開 PR，等需求方走過
`docs/initial-v2-acceptance-checklist.md` 給出 go-ahead 後才開 PR、
準備合併回 master。

### Production Regression Audit（2026-08-31，回報#052）＋ Repair Spec
（issue #237，2026-08-31）

需求方在 Vercel preview deployment 真機驗收（T18 AC9）時發現四組
production regression（P1 舊劇本編輯 422、P2 失敗卡片沒反灰、P3
刷新失敗比例升高＋部分數字異常、P4 新建劇本刷新必敗）。需求方以
`/code-review`＋額外 Production Regression Audit 指令下工單，另一個
平行 session（本機 JSONL `a2a2958d-...`，同一帳號、同一時段）完成
audit 並交付**回報#052**（fixed point `22b9d4b`→HEAD `a6ba02b`，
Standards／Spec／P1-P2 追蹤／60 秒 profiling／financial drift 五路
並行 sub-agent，關鍵結論逐條獨立覆核過）。**該份完整原文已存
`session-history/2026-08-31_225102+0800_a2a2958d.md`**（本輪順手
補存，原本只存在本機暫存、未進 repo）。

**Audit 核心結論**：三個獨立根因（不是四個）——(A) `_scenario_json()`
唯一沒呼叫 `normalize_families()` 的讀取路徑，T06／#221 commit
`5c13469` 引入，T10／#227 引爆；(B) `calibrate_leg` 在單次
Butterfly 分析內完全沒有跨候選 memoize，171,100 組候選×3 腿＝
513,300 次 solver 呼叫但只有約 300 條相異腿，19.8× 差距、約 95%
wall time，正是 Vercel `Task timed out after 60 seconds` 的成因；
外加獨立發現的失敗放大器 `REFRESH_RUN_GROUP_LIMIT=1` 讓任一劇本
504 就連坐標記整批 `pendingIds`；(C) 單腿用固定日曆錨點估值、
Vertical／Butterfly 用自身到期日估值，兩者在 select_expiries「錨點
前 2 後 2」下必然相遇，`_refresh_and_save()` 跨 family champion
把兩者混進同一排行榜，單腿系統性灌水（實測最高 +166.1 pp）——V1
兩把尺從未碰過面（`_MVP_STRATEGIES` 只有 bull-call-spread），
Initial V2 才是讓它們相遇的那一輪，不是寫錯數字的那一輪。六次既有
T01 基準重產事件（T02／T04／T09／T12／T14／T15）全數 VERIFIED，
無隱藏漂移。`/code-review` 抓到一項 hard violation（即 A 根因）與
三項判斷為刻意反泛化取捨的 judgement call。

**Owner 裁示 OD-01–OD-04**（FROZEN，完整內容見 issue #237）：
legacy 相容不遷移、只修讀取端正規化；跨 family 估值日統一為
own-expiration payoff（單腿改，Vertical／Butterfly 既有數值凍結
不動）；失敗卡片分「曾成功過」／「從未成功過」兩態、皆反灰皆保留
Retry；Strategy Family 新增全選（create＋edit，toggle，無獨立全
不選鈕）。

**`/to-spec` 已發佈——issue #237「OPTION-CHASER-REPAIR-001」**
（`ready-for-agent`）：涵蓋 FIX-01（legacy 相容）、FIX-02
（memoization）、FIX-09（refresh 失敗隔離）、FIX-03（條件式，
Butterfly 枚舉重新設計，明確不預設施工，由 FIX-02 後的
production-equivalent＋q≠0 re-profile 結果對照 **20 秒 acceptance
threshold** 決定 NEEDED／NOT_NEEDED）、FIX-04（timeout safety net，
非效能替代方案）、FIX-05（own-expiration 修正，第 7 次合法基準
重產事件，四項 collateral-drift 驗證步驟明訂）、FIX-08（守門擴充：
多 family 數值凍結＋production-scale 效能守門）、FIX-06（failure
卡片兩態）、FIX-07（Select All）。新增 5 條本輪專屬回歸紅線
（13–17，含既有 12 條紅線的例外註記：紅線 1 不再涵蓋 long-call／
long-put 到期日晚於錨點的候選數值）。九段 staged order（A 守門
擴充→B FIX-01→C FIX-02＋強制 re-profile→〔決策閘門〕→D FIX-09
（與 C 並行）→E FIX-03（條件式）→F FIX-04→G FIX-05＋FIX-08→H
FIX-06＋FIX-07→I 最終驗證）。測試接縫沿用既有七個、零新增。Spec
Self-Review 逐項核對 OD-01–OD-04 與 audit 結論無矛盾，標記
**READY_FOR_TICKETING**。

**`/to-tickets` 完成（2026-08-31，需求方裁示 Q1=A／Q2=A／Q3=B 後
發佈）——12 張票，issues #238–#249，全數為 #237 的 GitHub native
sub-issue、皆標 `ready-for-agent`**：

- **REPAIR-01**［#238］✅ 多 family baseline 守門擴充（Stage A，
  prefactor，零 production 改動，commit `42fd838`）——無 blocker
- **REPAIR-02**［#239］✅ FIX-01：Legacy Scenario 編輯相容（commits
  `87ba2b0`＋跟進 `7042438`）——無 blocker
- **REPAIR-03**［#240］✅ FIX-02：`calibrate_leg` memoization＋強制
  production-equivalent re-profile＋FIX-03 決策閘門（commits
  `e28bb0a`＋`9d5e742`＋跟進 `cda0089`）——無 blocker
- **REPAIR-04**［#241］✅ FIX-09：refresh-run 失敗隔離（消除
  `pendingIds` 連坐，commits `fd6be81`＋跟進 `73e96c6`）——無 blocker，
  可與 #240 並行
- **REPAIR-05**［#242］✅ FIX-06：刷新失敗卡片兩態 UX（commits
  `35b17f8`＋跟進 `7651c25`）——無 blocker
- **REPAIR-06**［#243］FIX-07：Strategy Family 全選——無 blocker
- **REPAIR-07**［#244］✅ FIX-03：Butterfly 枚舉 lazy calibration
  （條件式，依 #240 決策閘門判定是否施工）——**判定
  `NOT_NEEDED / NOT_PLANNED`**（#240 實測 7.543s ≤ 20s），依票面
  裁示直接關閉、零程式碼改動——blocked by #240（已解除）
- **REPAIR-08**［#245］✅ FIX-04：Timeout safety net（per-scenario
  soft deadline，僅限異常輸入，commits `cf66f27`＋跟進 `c347ae1`／
  `3a22318`）——blocked by #240（已解除）；#244 NOT_NEEDED 未施工，
  不必等
- **REPAIR-09**［#246］FIX-05：跨 family 估值日修正（單腿改
  own-expiration payoff，T01 基準第 7 次合法重產＋四步驟
  collateral-drift 證明）——blocked by #238
- **REPAIR-10**［#247］✅ FIX-08a：Performance Guard（production-scale
  效能守門，20 秒門檻永久 CI 斷言，commits `1e14b31`＋跟進 `a7e8540`）
  ——blocked by #240（已解除）；#244 NOT_NEEDED 未施工，不必等
  （需求方 Q3=B 裁示：FIX-08 拆成 Performance／Financial 兩張獨立票）
- **REPAIR-11**［#248］FIX-08b：Financial Guard（多 family
  champion 數值凍結，E2E-5 完整版）——blocked by #246
- **REPAIR-12**［#249］最終 production-equivalent regression
  validation（Stage I 收尾，17 條紅線逐條核對＋真機驗收清單
  更新）——blocked by #238–#248 全部（#244 需已解決，施工完成或
  關閉 NOT_PLANNED 皆可）

**Frontier（立即可開工、彼此互不依賴）＝ 6 張**：#238、#239、
#240、#241、#242、#243。

**`/implement` 施工開始（2026-08-31 起，需求方裁示全自主執行至全部
完成才一次回報，比照 Initial V2 自主執行輪同一套授權範圍與紀律）**：

- **REPAIR-01**［#238］✅ 已完成（commit `42fd838`）。詳見上方
  「Frontier」條目。
- **REPAIR-02**［#239］✅ 已完成（commits `87ba2b0`＋`7042438`）。
  修法為 `_scenario_json()`（全站唯一序列化 `strategies` 的地方）
  正規化。`/code-review` 抓到兩點並修正：(1) 修法範圍其實連帶修好
  `refresh`／`refresh-run` 對 legacy 劇本的回應，不是只有兩個 GET
  端點，原措辭已更正並補測試；(2) 新增前端測試補上真正餵 raw legacy
  字串的案例，把「正規化只在後端做一次」的架構邊界寫成可執行斷言。
  詳見上方「Frontier」條目。

- **REPAIR-03**［#240］✅ 已完成（commits `e28bb0a`＋`9d5e742`＋
  `cda0089`）。詳見上方「Frontier」條目——修法後 production-scale
  3 family 全開 7.543 秒（修法前 154.236 秒，20.4x），FIX-03 判定
  NOT_NEEDED。
- **REPAIR-07**［#244］✅ 已完成——FIX-03 判定 NOT_NEEDED，直接關閉
  不施工。詳見上方「Frontier」條目。

`#240` 解除後，`#245`（REPAIR-08，被 #240 擋、原本「若 #244 施工才
一併等」）與 `#247`（REPAIR-10，同上）**均已解鎖**——#244 已關閉且
未施工，兩張票的條件式 blocker 因此不再成立。

- **REPAIR-10**［#247］✅ 已完成（commits `1e14b31`＋`a7e8540`）。
  新增 `tests/_production_scale_fixtures.py` 收斂 #240／#247 兩份
  效能測試共用的 dividend_loader／fixture／門檻常數；`/code-review`
  抓到並修正一個真缺陷（`representative_candidate is not None` 不足
  以證明三個 family 都成功、也沒驗證 IV 反解真的觸發，已改用
  `results[].status`＋`candidate_pool[...].carry_calibrated`，並
  用 q=None 假 loader 驗證新斷言非恆真）。詳見上方「Frontier」條目。

- **REPAIR-08**［#245］✅ 已完成（commits `cf66f27`＋`c347ae1`＋
  `3a22318`）。`/code-review` 抓到兩項真發現並修正：(1) 新 DI 參數
  只在引擎層測過，補上 HTTP 層測試；(2) 更關鍵——deadline 計時點
  原本擺在抓鏈之後才啟動，票面自己點名的「vendor 回應異常慢」情境
  完全不受保護，已修正為抓鏈之前就起算，並用真實 `time.sleep`
  ＋`TestClient` warm-up（校準時發現並修掉一個會讓極短 deadline
  無論有無 bug 都在首次請求誤觸發的偽陽性測試設計）證明修法生效。
  詳見上方「Frontier」條目。

- **REPAIR-04**［#241］✅ 已完成（commits `fd6be81`＋跟進
  `73e96c6`）。真因：`runBatch()` 的 Continuation 迴圈裡，
  `refreshRun(pendingIds)` 這次 HTTP 呼叫本身整個失敗（504／
  timeout／transport failure，非個別劇本在 `results[]` 裡各自回
  `ok:false`）時，舊邏輯把 `pendingIds`（這一輪還沒處理到的全部
  劇本）一起標記失敗——單一批次呼叫的問題連坐整批，正是「V2 之後
  刷新失敗比例明顯比 V1 高」的直接機制。修法：改逐一走既有單一
  劇本刷新端點（`refreshOne()`，經 `Promise.allSettled` 各自獨立
  呼叫），每個劇本各自判定成敗；`refreshOne` 回傳型別
  `Promise<void>`→`Promise<boolean>` 供統計 N 成功／M 失敗，既有
  四個呼叫端沿用 `void refreshOne(id)` 寫法不受影響。新增三條端到
  端測試（`src/App.test.tsx`＋`e2e/smoke.spec.ts`＋
  `e2e/desktop.spec.ts`），已用臨時還原舊邏輯的方式驗證新測試在
  bug 存在時確實紅燈。`/code-review` 兩軸：Standards 軸無 hard
  violation，`catch (e) { void e; ... }` 改回本站既有的
  `catch { ... }` 裸接寫法（比照 `IvHistory.tsx`／
  `DiagnosticDetail.tsx`），`refreshOne` 疊了兩段的 JSDoc 合併成
  一段；Spec 軸無缺漏無 scope creep，兩點記錄於程式碼註解（fallback
  是脫離 Continuation 迴圈的一次性平行嘗試而非迴圈內重試，隔離保證
  本身仍成立；逐一呼叫刻意不設併發上限，因這個時間點的 pendingIds
  量體天生小）。純前端改動，`option_chaser/`／`api_app/` 零改動；
  typecheck／750 條 Vitest／114 條 Playwright／build 全綠。

- **REPAIR-05**［#242］✅ 已完成（commits `35b17f8`＋跟進
  `7651c25`）。依 OD-03 落地兩態：A（曾成功過）卡片反灰＋「更新失敗，
  目前顯示上一次成功結果」＋可點入看最後一次成功結果；B（從未成功過）
  卡片反灰＋「尚無可用分析結果」＋可點入（落到 `ScenarioDetail.tsx`
  既有的「尚未分析」空狀態，本票未改該檔案）。新增純函式
  `cardFailureVariant(row, failure, updating)` 集中三個互斥判準
  （`updating`／無 `failure`／`row.expired`＝#68 既有規則，皆回
  `null`）；新增 CSS `.compact-card.failed`（opacity 0.6，與
  `.locked` 的 0.45 刻意不同——failed 卡片仍完全可點）。順手補上
  `ScenarioList.tsx`／`CompactScenarioList.tsx` 原本沒有的
  `!updating` 互斥判斷（對齊 `ScenarioDetail.tsx` 既有寫法，避免更新
  中同時看到「更新中」徽章與過時的失敗提示）——這是票面「updating
  與 failure 不得混用」明文要求的延伸，已在 GitHub 結案留言向需求方
  說明。新增測試：`scenarios.test.ts` 6 條、`ScenarioList.test.tsx`／
  `CompactScenarioList.test.tsx` 各 4 條、`e2e/smoke.spec.ts`／
  `e2e/desktop.spec.ts` 各 2 條（A／B 兩情境）。`/code-review`
  Standards 軸一個 judgement call（`failure!` 非空斷言四處，已改用
  `failureVariant && failure` 讓型別系統自己窄化）已修正；Spec 軸無
  缺漏無 scope creep。純前端改動，typecheck／Vitest 764／Playwright
  118／build 全綠。

**下一張＝REPAIR-06（#243，FIX-07：Strategy Family 全選）**，無
blocker——原始 frontier（#238–#243）至此全數完成。

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

- **⚠ 沙箱外部網路現況（2026-08-26 實測更新，推翻本檔案更早的記載）**：
  過去幾輪記載「`raw.githubusercontent.com` 是唯一一手通道」——**該記載
  已過期**。本輪實測：
  - `raw.githubusercontent.com`：**已失效**（前輪 papers 鏡像路徑回 404）
  - `WebFetch`：**被擋**
  - **`curl` 沒有被閘道攔截，`WebFetch` 有**——這是關鍵區別
  - `curl` 可通：**`cdn.cboe.com`**（官方 methodology、完整即時全鏈、
    數十年指數歷史 CSV）、`arxiv.org`、`federalreserve.gov`、
    `nber.org`、`bis.org`
  - 各 vendor／交易所／監管網域（`api.marketdata.app` 等）：CONNECT 403
    或 DNS 失敗（不變）

  做研究輪要取一手文獻時，**先試 `curl`，不要先試 `WebFetch`**。
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
