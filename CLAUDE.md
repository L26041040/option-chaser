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

### 待辦（依序，← 為下一張）

> **用 `/implement` 處理已開出的 ticket：沒有遇到需要人類決定的部分，
> 就照下面的順序一張接一張往下寫，不要自己停下來。**
> 只有真正需要需求方裁示時才停——例如規格互相衝突、ticket 沒寫到而
> 任一種做法都會改變產品行為、或是要動到已定案的附錄決策。
> 純工程判斷（命名、重構、測試怎麼寫、既有 lint 問題）自己決定就好。

- **QA-v1 修正輪**（tracking [#27]，來源 `docs/QA-v1.md`，2026-08-02 拆票完成）：
  - **QA1-05** [#32] — Step3／Step4 對調＋到期日橫向選單（各期附最高收益）←
  - **QA1-06** [#33] — 「選看」改為就地展開（🔽），不拋回主圖
  - **QA1-07** [#34] — 刷新時機只有三種；刷新按鈕移頁面頂部
  - **QA1-08** [#35] — 移除「標記達成／標記失效」操作
  - **QA1-09** [#36] — 刪除人工評語與自創名詞（收斂完全／成交摩擦等）
  - **QA1-10** [#37] — 進階區分析報告＋歷史紀錄表單（raw data 可下載）
  - **QA1-11** [#38] — Spread 歷史改為折線圖
  - **QA1-12** [#39] — 進階區其餘移入封存區（**被 #37 擋**；其餘皆無阻擋）
  - 下一版不施工：QA1-13 [#40] 最好／最差價位、QA1-14 [#41] 上方功能區
  - 待需求方裁示：QA1-15 [#42] 使用者角度補充建議清單（裁示前不施工）
- **D1** [#14] — Long Call 追平比較（deferred，不得混入 T2–T11）。
  順序上排在 QA-v1 之後：兩者不衝突、可以先做完 QA-v1 這輪再回頭做 D1，
  理由是 D1 獨立不碰現有畫面，而 QA-v1 會動到 Step3/4/詳細頁結構，
  先做完 QA-v1 可避免 D1 白工。**D1 不會因為開始 QA-v1 而消失，
  全部 ticket 做完才開 PR 的規則（見上）涵蓋 D1 在內。**

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

- 跑測試：`PYTHONPATH=. .venv/bin/python -m pytest`
  （`pyproject.toml` 的 `packages.find` 只收 `option_chaser*`，`webapp` 不在裡面）
- 建 venv：`uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e ".[gui]" pytest`
- 全套測試現為全綠（舊紀錄提到的 5 個 streamlit 版本漂移失敗已隨 T2 改寫消失）。
