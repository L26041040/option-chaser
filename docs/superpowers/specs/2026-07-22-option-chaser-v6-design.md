# Option Chaser v6 Design Spec — Artifact Parity、正式產品化與一鍵啟動

日期：2026-07-22
狀態：已審（codex peer review APPROVED，2 rounds）
上游文件：`Brief_v4.md`（Artifact Parity 與 Windows 一鍵啟動）、v5 spec `2026-07-21-option-chaser-v5-design.md`（已實作；audit DC/AC PASS，SL 使用者中止）
本 spec 為 v5 之增量修訂；未提及處沿用既有 spec；衝突處以本文為準。

---

## 0. 目標與決議紀錄

### 0.1 目標

把視覺基準 Artifact（`https://claude.ai/code/artifact/bca2c75f-453c-40f0-9c56-d726b17b3d69`，其外殼 CSS 源碼存於本 repo 開發紀錄，見 §2）真正落地為使用者雙擊即用的正式產品。**引擎、store、workspace 層不動**（除 §4.3 序列化加欄）；改動集中於 GUI 層、打包與啟動體驗。

### 0.2 已拍板決議（brainstorm 定案，審核時不再翻案）

1. **視覺方向＝照 Artifact 原樣（淺色）**：使用者確認其看到的 Artifact 為淺色呈現——淺灰頁面底（`#eef0f3`）＋白色卡片視窗＋膠囊；資料視窗（heatmap、表格、縮圖）**零改色**。不做深色主題、不做雙主題（Brief §3「深色專業交易介面」一詞依使用者本輪澄清，修正為此淺色基準）。
2. **技術路線＝Streamlit 深度定製**＋ dict 視圖介面正式文件化（未來換前端的接縫）；不換 React、不加 API 層。
3. **BAT＝單一自癒啟動檔**：首次雙擊自動建 `.venv` 並安裝依賴（中文進度），之後直接啟動。不做獨立安裝檔。
4. **停止方式＝關窗即停**：同視窗執行 streamlit，關閉視窗或 Ctrl+C 即停止。不做停止.bat、不獵殺程序。
5. **資料目錄＝維持現位**：`workspace/`、`snapshots/` 留在專案根；新增 `logs/`；桌面放捷徑。零遷移。
6. Artifact 是視覺 Source of Truth；還原度驗收以「逐頁差異表＋使用者核可」為準（§12）。
7. 機率紅線、GUI 零金融公式紅線全面沿用 v4/v5；禁詞掃描範圍隨新檔案擴充。

---

## 1. 資訊架構與導覽

### 1.1 導覽重構（`st.navigation`）

`webapp/app.py` 改為路由入口（router），以 `st.navigation` 宣告頁面；`webapp/pages/` 檔案機制廢除（檔案移至 `webapp/views/`）。導覽顯示名稱與順序：

```
戰情總覽    webapp/views/overview.py     ← 預設首頁
劇本工作區  webapp/views/workspace.py
快速試算    webapp/views/quick.py
使用說明    webapp/views/help.py
（詳頁）    webapp/views/detail.py       ← 不入導覽列；由工作區/總覽跳轉，URL 帶 ?sid=<scenario_id>
```

- **紅線：導覽任何位置不得出現 `app` 字樣**（brief §4.2）。
- **Streamlit 版本地板**：`st.navigation`/`st.Page`（1.36+）、`st.popover`（1.32+）、`st.Page(visibility="hidden")`（1.55+）為本 spec 依賴；`pyproject.toml` 的 gui extra 升為 **`streamlit>=1.57`**（開發環境現裝 1.59.x）。
- 詳頁為獨立頁面：以 `st.Page(..., visibility="hidden")` 註冊（可路由、不入導覽列）；`st.query_params["sid"]` 指定劇本；sid 不存在→顯示錯誤卡＋返回工作區連結。
- 頁面圖示（st.Page icon）：總覽 📊、工作區 🗂、試算 ⚡、說明 📖——具體以實作視覺協調為準，非驗收項。

### 1.2 快速試算與工作區的定位區隔（brief §4.3）

- 快速試算頁標題下固定副標：「**一次性分析，結果不會自動保存。**」
- 分析完成後結果區頂部提供「**保存為劇本**」按鈕：呼叫**新增的編排函數 `workspace.adopt_result(ws_root, result, notes="", ts=None) -> (Scenario, Path)`**——內部：`create_scenario`（direction 依現價 vs 目標價推得；strategies 取自 request）→ `store.serialize_result`（capital 取當下 constraints）→ `save_result` → append `ANALYSIS_COMPLETED`（§2.5 次序：result 檔先、事件後）。**重用當次分析結果，不重新分析**；snapshot 已由 `service.run` 落盤，`snapshot_ref` 直接引用。成功後顯示連結跳轉至該劇本詳頁。view 層不得繞過 workspace 直呼 store 寫入。
- **撞名預檢**：按鈕渲染前先以 base id（`store.scenario_id(symbol, price, date, set())` 之無撞名結果）檢查 `scenarios/<base_id>.json` 是否已存在——存在→按鈕改為「已有同名劇本，前往查看」（連結至該劇本詳頁），**不得**落入 `create_scenario` 的 `-2` 撞名追加機制產生重複劇本。`adopt_result` 內亦做同一預檢（存在→拋 `ValueError`，防繞過 UI 直呼）。
- 快速試算頁**不寫任何 workspace 檔案**除非按下保存（測試鎖定：分析後 workspace 目錄無新檔）。

---

## 2. 視覺系統

### 2.1 Token 來源與落地

Artifact 外殼 CSS 是本版視覺規格的權威。其 token 全文收錄為新檔 **`webapp/theme.py`**（唯一來源；`THEME_CSS` 常數＋`inject()` 函數，各 view 開頭呼叫）。核心 token（自 Artifact 淺色呈現原樣移植——即其 `:root` 預設值，正式值如下；Artifact 源碼中的 dark 變體棄用）：

```
--bg: #eef0f3          頁面底（淺灰）
--chrome: #f3f4f6      chrome/膠囊底
--chrome-ink: #374151  chrome 文字
--surface: #ffffff     卡片/資料視窗底（白）
--ink: #1c1f26         主文字
--dim: #6b7280         次要文字
--line: #e3e6ea        邊線
--accent: #ff4b4b      主色（Streamlit 紅，延續品牌）
--pos: #1a7f37  --neg: #b22222
字體：Segoe UI / Microsoft JhengHei / system-ui；數字 tabular-nums
卡片：圓角 10px、邊 1px --line、陰影 0 8px 28px rgba(15,18,25,.10)
膠囊（pill）：999px 圓角、1px 邊；狀態色 Active 綠框淺綠底、Reached 金框淺黃底
```

- `.streamlit/config.toml` 設定 light base theme（`base="light"`、primaryColor=`#ff4b4b`、backgroundColor=`#eef0f3`、secondaryBackgroundColor=`#f3f4f6`、textColor=`#1c1f26`）——原生元件（按鈕、輸入框、下拉）吃主題色。
- 資料視窗（heatmap、mini 表、縮圖）置於白色卡片容器內；**heatmap 色階函數 `cell_color` 與所有渲染輸出零修改**。
- 側欄（st.navigation 產生）以 CSS 調為 `--chrome` 淺灰風格＋選中項 accent 淺紅底（Artifact 側欄樣式）。

### 2.2 卡片元件庫（新檔 `webapp/components.py`）

純函數，輸出 HTML 字串（吃 dict，禁公式），與 `render.py` 同紅線：

- `scenario_card(sc_dict, view_summary) -> str`：工作區劇本卡（§3.2）。
- `candidate_card(cand, strategy) -> str`：候選卡，單腿/Spread 兩版式（§4.1/§4.2）。
- `metric_tile(label, value, tone) -> str`：總覽指標卡。
- `status_pill(status) -> str`、`quality_badge(dq) -> str`（§6）。
- `milestone_rail(group, scenarios, views) -> str`：群組里程碑（§3.5）。

---

## 3. 頁面規格

### 3.1 戰情總覽（首頁）

- 六個指標卡（`metric_tile` 橫排 wrap）：Active 劇本數／尚未分析數／資料異常數（最新 result `all_quotes_filtered=True` 或無合格候選）／已完成數（Reached）／待確認關係數（relations 中 `confirmed=="undefined"` 且 proposed 非空）／最近分析時間（全工作區最新 result 的 `analyzed_at`）。全部由 `workspace.list_scenarios`＋`latest_result` 聚合，**計數與時間取值屬彙總非估值**，在 view 層完成。
- 指標卡下方：劇本速覽列表（每列＝狀態膠囊＋symbol＋目標＋最新推薦一行摘要，點擊跳詳頁）。
- **不得出現**：持倉損益、已投入資金、Portfolio Greeks（brief §7.1；無 Position 不偽造）。
- 空工作區→引導卡「建立第一個劇本」跳工作區。

### 3.2 劇本工作區

- **劇本卡片牆**（每劇本一張 `scenario_card`）。卡面：Symbol＋方向膠囊／現價→目標價與漲跌幅（現價取最新 result 的 `snapshot_ref.spot`；無 result 則不顯示現價）／目標日／狀態膠囊／資料品質標章／最新分析時間（`analyzed_at`）／最新推薦候選（策略＋結構＋**每張/每組成本**）／劇本報酬／情境最壞／緩衝天數。
- 卡片主操作（僅三鍵）：`查看分析`（詳頁）｜`重新分析`｜`選擇候選`（跳詳頁 Step 3 錨點）。
- **`⋯ 管理` 彈出層**（`st.popover`）：標記達成／標記失效（含 reason 輸入）／關係設定／刪除（含確認）。原因欄、刪除 checkbox、狀態按鈕**不得**長駐主畫面（brief §7.2）。備註顯示於卡面小字；「修改備註」不在 v6（劇本唯讀原則沿用 v5，brief 該行以 v5 既有決議為準，管理層不提供）。
- 建立劇本表單收進頁頂「＋ 建立劇本」`st.popover`（欄位與 v5 相同；方向推測邏輯沿用）。
- 群組區：見 §3.5。>6 劇本軟提示沿用。

### 3.3 劇本詳頁（獨立頁）

結構（brief §7.4）：

1. **Header 卡**：Symbol／現價／目標價（漲跌幅）／目標日／snapshot 時間＋資料品質標章／`重新分析` 按鈕／狀態膠囊。
2. **推薦候選卡**：default_selection 的 `candidate_card`（完整價格，§4）。
3. **Heatmap**（v4 主圖；Spread 加封頂標示，§5）。
4. **候選比較**：v5 Step 3 的到期日分組列表升級為比較表（§4.4），選看切換沿用 session state。
5. **進階區**：7 情境向量／完成度曲線／Greeks 與流動性／成交摩擦／原始報告（`report_text`）——v5 內容原樣，容器改深框淺窗卡片。

### 3.4 快速試算

- 現 `app.py` 四步流程整體移入 `views/quick.py`；輸入表單、渲染全部沿用 `render.py`；視覺容器套新卡片系統。
- 副標與「保存為劇本」見 §1.2。

### 3.5 同標的群組（brief §8）

`milestone_rail`：垂直時間軸——每里程碑一節點（狀態膠囊＋日期＋目標價＋最新推薦一行），節點間連線標注關係（已確認＝實線＋關係名；僅提案＝虛線＋「提案：×××，待確認」＋確認按鈕）。附註「群組分析共用同一份 snapshot」；成員最新 result 若引用同一 snapshot 檔則顯示「✓ 同一資料快照」標章（路徑相等判斷，展示層）。重新分析按鈕兩條件規則沿用 v5。

---

## 4. 候選價格全面顯示（brief §5）

### 4.1 單腿候選卡

```
Long Call ｜ 履約價 93 ｜ 到期 2028-01-21
Bid $1.32 ｜ Mid $1.42 ｜ Ask $1.52
Mid 每張 ≈ $142 ｜ Natural 每張 ≈ $152
最大損失 ≈ $142 ｜ Breakeven $94.42 ｜ 劇本報酬 749.4%
```

每股價與每張金額並列明示（brief §5.1）。

### 4.2 Spread 候選卡

```
Bull Call Spread ｜ 買 100 Call ／ 賣 120 Call ｜ 到期 2028-12-15
Net Mid Debit $0.95／股 ｜ 每組 ≈ $95
Natural Debit $1.11／股 ｜ Natural 每組 ≈ $111
最大損失 ≈ $95 ｜ 最大獲利 ≈ $1,905 ｜ Breakeven $100.95 ｜ 獲利封頂價 $120
```

買賣腿、Net Debit、每組成本、最大損失、最大獲利、封頂價全顯（brief §5.2）。

### 4.3 序列化加欄（`store.serialize_result`，result `schema_version: 2`）

candidate dict 新增（乘法與取值，非估值邏輯——v5 §3 慣例）：

- `natural_per_contract` = `natural_cost × 100`
- `max_profit_per_contract` = `max_profit × 100`（max_profit 為 null 則 null）
- `cap_price` = Spread 時 `legs[1].strike`；單腿 null

規則：

- `schema_version` 1→2；**僅加欄**，既有欄位、決定性（sort_keys 逐位元）與既有測試語意不變（determinism 測試以 v2 重錄）。
- 舊 result 檔（v1）照常載入；GUI 對缺欄顯示「—」＋卡面提示「舊版分析結果，重新分析以顯示完整價格」。不回填、不遷移。
- engine_version 隨 §8 升 `0.6.0`。

### 4.4 候選比較表（詳頁；brief §5.3）

到期日分組保留，每組內候選以表格呈現，欄位：策略／結構（K=93 或 買100/賣120）／到期日／Bid/Mid/Ask（單腿）或 Net Mid＋Natural Debit（Spread）／每張・每組成本／最大損失／最大獲利（單腿 long-call 顯示「無上限」，long-put 與 Spread 顯示金額）／Breakeven／劇本報酬／情境最壞／不漲保留率／成交摩擦（獨立欄，>25% 標 ⚠）／資料品質。徽章（🚀🛡️⚠◀）與選看沿用。表格外層 `overflow-x:auto`，手機橫向捲動。

---

## 5. Spread Heatmap 封頂標示（brief §6）

`render.py` 的 heatmap 渲染對 Spread 候選（`len(legs)==2`）增加：

1. **封頂區方向依策略**：BCS（call spread）→ 價格 **≥** `cap_price` 的資料列為封頂區；BPS（put spread）→ 價格 **≤** `cap_price` 的資料列為封頂區（賣腿在下方，最大獲利平台在賣腿 strike 之下）。方向由候選的 `strategy` 判定（`bull-call-spread`/`bear-put-spread`），非硬編 ≥。
2. 封頂區資料列：列首價格標注「**收益封頂**」，區塊與非封頂區交界畫分隔線＋右側直欄標「最大獲利區」。
3. 圖下說明行（同樣依方向措辭）：BCS「股價 ≥ $\{cap_price\} 後，收益固定於最大獲利 ≈ $\{max_profit_per_contract\}／每組。」；BPS「股價 ≤ $\{cap_price\} 後，收益固定於最大獲利 ≈ $\{max_profit_per_contract\}／每組。」
4. 封頂價本身若不在價格軸上，於最接近的兩列間標注封頂線（展示層插行標記，不改引擎價格軸）。

判斷僅為「價格 vs cap_price 比較＋讀 max_profit＋策略字串分支」——展示層邏輯（v4 粗體錨點同類）。單腿主圖零變化 → 兩策略主圖一眼可辨（brief §6 要求 1-5 全數滿足）。測試須含 BCS 與 BPS 鏡像案例。

---

## 6. 狀態文案（brief §9）

### 6.1 劇本顯示狀態（展示層推導，非新狀態機）

| 顯示狀態 | 判定（既有資料） |
|---|---|
| 尚未分析 | `latest_result` 為 None |
| 有可用候選 | result 存在且 `default_selection` 非 null |
| 無合格候選 | result 存在、所有策略完成、無候選、`all_quotes_filtered=False` |
| 報價資料不足 | result 存在且 `data_quality.all_quotes_filtered=True` |
| 抓取市場資料失敗 | 本次操作拋 `FetchError`（即時顯示，不落盤） |
| 分析執行失敗 | 本次操作拋其他例外（即時顯示） |
| 歷史 Snapshot | result 存在且 `fetched_at` 非今日（顯示資料時間＋「歷史資料」標章） |

- 「報價資料不足」卡顯示文案：「已完成分析，但目前報價資料不足，沒有可用候選。」＋操作：`稍後重試`（重新分析）｜`查看過濾原因`（展開 filter_stages 表）。
- **誠實聲明**：引擎不存在 Last-Trade/Synthetic fallback，v6 不新增；「使用測試 fallback」狀態標籤於本 spec 定義保留（文案：`Synthetic Test／不可作為成交依據`）但無觸發路徑，GUI 無此分支（測試鎖定：程式內無 synthetic 資料路徑）。
- 「最近有效 Snapshot」重試屬順手項（§13），非必做。

### 6.2 資料品質標章（`quality_badge`）

`正常`（綠）／`報價不足`（橙，all_quotes_filtered）／`歷史資料`（灰，非今日）。標章出現於：劇本卡、詳頁 Header、總覽速覽列。

---

## 7. 視圖契約文件化（遷移接縫）

新檔 `docs/view-contract.md`：正式記錄 `store.serialize_result` 輸出 dict 的完整 schema（v2，含 §4.3 新欄）、`render.py`/`components.py` 的消費介面、以及「未來前端只需讀 result JSON＋workspace 檔案即可完整重建 UI」的邊界聲明。文件與 `test_store_serialize.py` 的欄位斷言互為印證（文件列的鍵必須是測試鎖定的鍵——審計可核）。

---

## 8. 打包修復與版本統一（brief §11）

- `pyproject.toml`：`packages.find` include 加 `webapp*`；確保 `webapp/`、`webapp/views/` 均有 `__init__.py`。驗收：乾淨 venv `pip install -e ".[gui]"` 後，任意 cwd `python -c "import webapp.render"` 成功；`streamlit run webapp/app.py` 於專案根正常；Docker build/run 正常；**全程無 PYTHONPATH 設定**。
- 版本統一 **0.6.0**：`option_chaser/__init__.__version__` 與 pyproject `version` 同值（測試鎖定兩者相等——讀 pyproject 比對）。
- `webapp/pages/` 舊檔（`0_劇本工作區.py`、`1_說明.py`）刪除（內容遷入 views）；`egg-info` 重生。
- Dockerfile 增 COPY `.streamlit/`（現 Dockerfile 僅複製 pyproject/README/option_chaser/webapp——config.toml 必須進容器，否則容器內主題錯誤）。
- gui extra 版本地板同步 §1.1：`streamlit>=1.57`。

---

## 9. Windows 一鍵啟動（brief §10）

### 9.1 `啟動 Option Chaser.bat`（專案根；UTF-8 `chcp 65001`）

流程：

1. `cd /d %~dp0`（專案根定位）。
2. 找 Python：依序試 `py -3` → `python`；版本 <3.11 或不存在→中文訊息（「找不到 Python。請先安裝 Python 3.11 以上版本。」）＋`pause`。
3. `.venv\` 不存在→顯示「首次啟動，正在安裝必要元件（約 2-3 分鐘，僅此一次）……」→ `python -m venv .venv` ＋ `.venv\Scripts\python -m pip install -e ".[gui]"`；失敗→錯誤訊息＋log 路徑＋`pause`。
4. 依賴健檢：`.venv\Scripts\python -c "import streamlit, option_chaser, webapp"`；失敗視同步驟 3 失敗。
5. Port 8501 檢查（含**身分驗證**，防開到別人的 Streamlit）：
   - `logs\running.lock` 記錄本 app 上次啟動的 PID（步驟 6 寫入、正常結束刪除）。
   - `/_stcore/health` 有回應 **且** lock 檔存在且其 PID 對應之程序仍存活→「Option Chaser 已在執行，為你開啟瀏覽器。」→ `start http://localhost:8501` → 結束。
   - `/_stcore/health` 有回應但無有效 lock→「連接埠 8501 上有其他 Streamlit 程式，請關閉後重試。」＋`pause`。
   - port 被占但健檢無回應→「連接埠 8501 被其他程式占用，請關閉該程式後重試。」＋`pause`。
6. 前景執行 `.venv\Scripts\python -m streamlit run webapp/app.py`（**非 headless——瀏覽器由 Streamlit 於伺服器就緒後原生自動開啟**，消除先開瀏覽器的連線失敗競態；BAT 不手動 `start` URL，「已在執行」路徑除外）。啟動前寫入 `logs\running.lock`（PID）。視窗保留＝服務執行中；**關窗/Ctrl+C 即停**（殘留 lock 由下次啟動的存活檢查自然失效）。
7. 全程輸出併寫 `logs\launch-YYYYMMDD-HHMMSS.log`；任何錯誤路徑以 `pause` 結尾（brief §10.2）。

### 9.2 `建立桌面捷徑.bat`（一次性，可選）

以 PowerShell WScript.Shell 在桌面建「啟動 Option Chaser」捷徑指向 §9.1 BAT（工作目錄＝專案根）。使用者桌面此後只需要這個捷徑（brief §10.4）。

### 9.3 驗收（brief §15）

Windows 實機：刪除 `.venv` 從零雙擊→自動安裝→瀏覽器開啟→四頁正常；二次啟動秒開；已執行時再雙擊→直接開瀏覽器不重複起服務；錯誤路徑（改壞依賴）視窗不消失且 log 可尋。

---

## 10. 紅線（沿用＋擴充）

1. 引擎（service 及以下）**零修改**；store 僅 §4.3 加欄；workspace 僅新增 `adopt_result`（§1.2），既有函數零修改。
2. GUI 零金融公式：新欄位一律 serialize 預算；components/views 僅格式化與展示層比較（價格 vs cap_price、路徑相等、日期比對、計數）。
3. 機率禁詞掃描 TARGETS 擴充：`webapp/theme.py`、`webapp/components.py`、`webapp/views/*.py`（bare 機率同步擴充；舊 pages 檔自清單移除）。
4. 無分數、無 POP/期望值/Sharpe；Group 不進計算路徑；LLM 零介入。
5. Artifact 視覺方向不得擅改（§0.2.6）；Streamlit 無法還原處必須在差異表誠實列為「合理調整」或「尚未完成」，不得隱藏（brief §14.6）。

---

## 11. 測試

1. **serialize v2**：新欄三組值 fixture 手算鎖定（natural×100、max_profit×100、cap_price=賣腿 strike；單腿 null）；決定性雙跑逐位元（v2 基準）；v1 舊檔載入相容（缺欄不炸）。
2. **快速試算不落盤**：分析後 workspace 無新檔；按「保存為劇本」→ scenario＋result＋事件齊備且 `snapshot_ref` 引用當次 snapshot；同 id 再存→不覆寫。
3. **狀態推導**：§6.1 表逐列單元測試（構造七種 result/例外情境）。
4. **封頂標示**：Spread heatmap HTML 含「收益封頂」與說明行、cap_price 正確；單腿 HTML 不含封頂字樣。
5. **導覽**：AppTest 四頁載入無例外；渲染輸出不含「app」頁名；詳頁 sid 存在/不存在兩態。
6. **components**：卡片函數對 fixture dict 的輸出包含必要欄位字串（成本、最大損失、Breakeven 等），無公式計算（程式碼審查＋禁詞掃描）。
7. **既有測試策略**：`test_webapp*.py` 因頁面重構**允許修改**——保留全部語意斷言（按鈕條件、狀態轉移、保存語意），更新頁面路徑與 key；`test_render`/`test_store_serialize` 等非 GUI 測試除 v2 基準重錄外不動；引擎測試（177 顆 v4 基準）零修改零紅。
8. **打包**：子行程（無 cwd 加持）`import webapp.render` 成功；版本一致性測試。
9. BAT 屬 §9.3 實機驗收，不寫自動化測試（Windows batch 不納入 pytest）。

## 11A. 審計覆蓋契約（codex-audit，設計期凍結）

- **DC**：乾淨 venv `pip install -e ".[gui]"`；任意 cwd import webapp/webapp.views 全模組；`streamlit run` 啟動健檢（`/_stcore/health` 200）；版本 0.6.0 一致；config.toml 解析。
- **AC**：全套件 codex 親跑；serialize v2 新欄獨立重算（natural/max_profit ×100、cap_price 對照 legs）；v1 檔相容載入；狀態推導表逐列重現；封頂 HTML 斷言；快速試算不落盤＋保存鏈路事件重放；禁詞掃描擴充範圍；v4 引擎 177 測試零紅。
- **SL**：真實流程——BAT 從無 `.venv` 冷啟動（處方腳本記錄完整 transcript）→ 瀏覽器開啟 → 建立 TLT 105/2028-01、TLT 120/2028-12、ORCL 250/2027-01 → TLT 自動歸組共用 snapshot、ORCL 獨立 → 各頁 Chromium 桌機（1280px）＋手機（390px）截圖 → 候選卡價格欄位與 result JSON 逐值比對 → Spread 詳頁封頂帶可見 → 快速試算「保存為劇本」全鏈 → 關窗停止後 port 釋放。無法執行處依處方模式，不得豁免。

---

## 12. 驗收案例

1. 雙擊 BAT（乾淨 `.venv`）→ 自動安裝 → 瀏覽器開 `http://localhost:8501` → 首頁為戰情總覽，導覽無 `app`。
2. 建立三真實劇本（TLT 105/2028-01、TLT 120/2028-12、ORCL 250/2027-01）→ 工作區卡片牆呈現；TLT 群組里程碑軌顯示、共用 snapshot 標章；ORCL 獨立。
3. 任一候選卡與比較表：Bid/Mid/Ask、每張/每組成本、最大損失、Breakeven 全顯；Spread 另有最大獲利與封頂價；數值與 result JSON 一致。
4. TLT 120 Spread 詳頁主圖：≥ 封頂價區域標「收益封頂」＋說明行；Long Call 主圖無此標示。
5. 盤前抓取（報價全濾）→ 劇本卡顯示「報價資料不足」文案＋查看過濾原因，**不是**「尚未分析」。
6. 快速試算跑 AAPL → workspace 零新檔；按「保存為劇本」→ 劇本出現於工作區並可進詳頁。
7. **視覺核可硬閘**：Artifact vs 實際 App 逐頁差異表（每項標 已還原/合理調整/尚未完成）＋桌機與手機實機截圖交付使用者；**使用者明確核可後才可合併**（brief §14.7）。
8. 全輸出無機率語彙；引擎測試零紅。

---

## 13. 明確不做（v6）

深色主題、雙主題、React/API 層（僅文件化接縫）、停止.bat、資料目錄遷移、Last-Trade/Synthetic fallback 實作、韌性排名重構、Scenario Decision 持久化、持倉/追蹤面板/倉位配置、Policy Engine、自動事件、券商 API、自動下單、劇本備註編輯（唯讀原則沿用）。順手項（不擋主線、時間允許才做）：「每口成本占本金」改名、最近有效 Snapshot 重試、Top 5 顯示、候選展開。

<!-- codex-peer-reviewed: 2026-07-22T03:22:02Z rounds=2 verdict=approved -->
