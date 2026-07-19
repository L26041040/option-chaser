Option Chaser Web GUI — Product Brief

1. 產品定位

將目前的 Option Chaser CLI 包裝成一個簡單、直覺的網頁工具。

使用者只需要輸入：

1. 股票或 ETF 標的
2. 預期目標價
3. 預計到達日期
4. 想比較的選擇權策略

系統便自動抓取目前市場上的選擇權鏈，掃描並比較符合條件的合約與價差組合，提供：

* 最佳候選
* 條件式報酬率比較
* 進場成本與損益資訊
* 價格 × 日期 P/L Heatmap

產品體驗應接近 OptionsProfitCalculator，但增加它缺少的：

* 自動掃描整條選擇權鏈
* 自動尋找最佳單腿與價差組合
* 不同策略的同場比較
* 自動排名候選，而不是要求使用者手動選履約價

⸻

2. 核心使用流程

使用者打開網站後，只看到一個簡單表單。

必要輸入

1. 標的

文字輸入框。

範例：

TLT

送出前自動：

* 去除前後空白
* 轉成大寫
* 檢查標的不為空白

2. 目標價位

正數數字輸入框。

範例：

105

3. 預計到達時間

日期選擇器。

範例：

2028-01-01

日期必須晚於目前市場資料日期。

4. 報告清單

以 Checkbox 顯示：

☑ Long Call
☑ Bull Call Spread
☐ Long Put
☐ Bear Put Spread

預設勾選：

* Long Call
* Bull Call Spread

使用者至少需要勾選一種策略。

執行按鈕

開始分析

按下後：

1. 抓取一次完整市場資料。
2. 建立一份共用 Snapshot。
3. 所有勾選策略都使用相同 Snapshot 分析。
4. 不得為每個策略分別重新抓取資料。
5. 完成後顯示結果頁。

⸻

3. 首頁設計原則

首頁必須極度簡單。

畫面只保留：

* 產品名稱
* 一句產品說明
* 四項輸入
* 開始分析按鈕

建議說明文字：

輸入你的價格劇本，Option Chaser 會自動掃描目前的選擇權鏈，
比較單腿與價差策略，找出條件式報酬率最高的候選。

第一版不顯示以下進階參數：

* IV shifts
* Risk-free rate
* Minimum OI
* Minimum volume
* Spread threshold
* Delta bands
* Minimum return
* Top N
* Force
* Snapshot path
* Output path

這些全部沿用 Option Chaser 核心引擎目前的預設值。

第一版也不需要「進階設定」面板。除非實際使用後證明有需求，再於後續版本加入。

⸻

4. 分析中狀態

按下「開始分析」後，顯示清楚但簡單的進度狀態：

正在抓取 TLT 市場資料……
正在過濾合約……
正在比較 Long Call……
正在窮舉 Bull Call Spread……
正在建立 Heatmap……

分析期間停用重複提交按鈕。

不得讓使用者看到 Python traceback 或內部例外。

⸻

5. 結果頁結構

結果頁由上至下分為五區。

5.1 劇本摘要

顯示：

* 標的
* 目前股價
* 目標價
* 目標日期
* 市場資料時間
* 資料來源
* 已分析策略

範例：

TLT 現價 $84.52
劇本：2028-01-01 前到達 $105.00
資料時間：2026-07-19 09:51 UTC
已比較：Long Call、Bull Call Spread

⸻

5.2 跨策略比較摘要

這是 GUI 相較 CLI 最重要的新功能。

將每個已勾選策略的最佳候選放在同一張比較表中。

至少顯示：

策略	候選	到期日	進場成本	劇本報酬率	最差進場報酬率	Breakeven	最大獲利

其中：

* Long Call 顯示履約價。
* Spread 顯示買入履約價／賣出履約價。
* 最大獲利對 Long Call 顯示「無上限」。
* Spread 顯示固定最大獲利。

劇本報酬率最高者標記：

最高報酬

但不得將「最高報酬」描述成「最佳投資」或「最推薦」，因為系統沒有判斷劇本發生機率。

⸻

5.3 策略結果區

每個勾選策略各有一個 Tab：

Long Call
Bull Call Spread
Long Put
Bear Put Spread

只顯示本次有勾選的策略。

每個策略預設顯示核心引擎排名前三名的候選。

候選以卡片或簡潔表格呈現。

Long Call／Long Put 候選資訊

* 履約價
* 到期日
* Bid／Mid／Ask
* 每張成本
* IV
* Delta
* Breakeven
* 劇本日估值
* 劇本損益
* 劇本報酬率
* 最差進場報酬率
* 流動性或價差警示

Spread 候選資訊

* 買入腿
* 賣出腿
* 到期日
* 寬度
* Net Mid Debit
* Natural Debit
* 每組成本
* Breakeven
* 最大虧損
* 最大獲利
* 劇本日估值
* 劇本損益
* 劇本報酬率
* 最差進場報酬率
* 流動性或價差警示

候選卡片提供：

查看 Heatmap

第一名候選的 Heatmap 預設展開，其餘收合。

⸻

5.4 P/L Heatmap

Heatmap 是本 GUI 的核心視覺功能。

軸

* Y 軸：標的價格
* X 軸：日期
* 格值：以 Mid 進場計算的報酬率百分比

沿用 Option Chaser 現有矩陣引擎：

* 11 個價格
* 最多 7 個日期
* 精確包含目前股價
* 精確包含目標價
* 精確包含目標日期
* 最後一欄為到期日 payoff

視覺規則

* 正報酬：綠色
* 負報酬：紅色
* 接近損益兩平：中性色
* 每格直接顯示報酬率，例如 +943%、-51%
* 目前股價所在列明確標記「現價」
* 目標價所在列明確標記「目標」
* 目標日期所在欄明確標記
* 到期日欄明確標記「到期」

色階應以 0% 為中心，而不是以矩陣中的最小值與最大值平均分色。

極端報酬率不應讓其他格子的顏色失去辨識度。可對色彩顯示範圍設定合理上限，但格內仍顯示真實數字。

Heatmap 下方顯示一句說明：

此圖顯示在不同標的價格與日期下，以目前 Mid 價進場的模型報酬率。

⸻

5.5 計算細節

為避免首頁與主要結果過度複雜，以下資訊放在可展開區：

查看完整計算細節

內容包括：

* 過濾統計
* IV 情境結果
* Greeks
* Lambda
* 買價指引
* 模型公式
* 模型限制
* 原始文字報告

普通使用者不展開也能完成主要決策比較。

⸻

6. 錯誤與空結果

GUI 必須處理：

無法取得市場資料

目前無法取得 TLT 的市場資料，請稍後再試。

標的不存在

找不到此標的，請確認代號是否正確。

沒有合格合約

目前沒有符合流動性與報價條件的合約。

日期或方向錯誤

若看漲策略的目標價低於或等於現價，或看跌策略的目標價高於或等於現價：

* 不提供 --force 給一般 GUI 使用者。
* 顯示方向不一致的提示。
* 只阻擋方向不一致的策略，不必阻擋其他合理策略。

例如：

目標價低於目前股價，因此未執行 Long Call 與 Bull Call Spread。
可改選 Long Put 或 Bear Put Spread。

⸻

7. 技術原則

共用核心

GUI 不得透過 subprocess 呼叫 CLI，也不得解析 CLI 文字輸出。

應抽出一個共用 Application Service：

GUI ─┐
     ├→ Application Service → Option Chaser 核心引擎
CLI ─┘

Application Service 回傳結構化結果，至少包含：

* Snapshot metadata
* Strategy results
* Ranked candidates
* Comparison summary
* Matrix data
* Filter report
* Warnings

CLI 與 GUI 共用相同的估值、過濾、配對與排名邏輯，禁止另寫一套 GUI 計算公式。

資料一致性

一次分析只能抓取一次市場資料。

所有被勾選的策略必須使用完全相同的 Snapshot，確保跨策略比較公平且可重現。

Heatmap

Heatmap 使用現有 matrix.py 的結構化輸出，不得重新實作另一套價格軸、日期軸或估值引擎。

建議 GUI 技術

第一版優先採用 Streamlit：

* Python 原生
* 可快速建立表單、Tabs、卡片、表格與 Heatmap
* 容易與現有 Python 核心共用
* 可直接 Docker 化
* 適合目前單一使用者與私人服務情境

⸻

8. Docker 與部署

本輪可同時提供：

* Dockerfile
* compose.yaml
* Health check
* Snapshot 與報告的持久化 volume
* 環境變數設定 Port

目標啟動方式：

docker compose up -d

預設服務：

http://localhost:8501

Docker 化不得改變核心計算結果。

同一 Snapshot 與同一組輸入，在 CLI、裸機 GUI、Docker GUI 中必須得到相同的候選排序與數值。

⸻

9. 第一版明確不做

* 帳號與登入
* 多使用者
* 資料庫
* 雲端同步
* 投資組合追蹤
* 自動下單
* 價格提醒
* 歷史回測
* 股價預測
* 機率計算
* AI 投資建議
* 多標的同場比較
* 自訂策略組合器
* 複雜進階設定
* 手動指定履約價
* Credit Spread
* 裸賣策略
* 付費系統

⸻

10. MVP 驗收標準

1. 使用者只需填寫標的、目標價、目標日期並勾選策略。
2. 預設勾選 Long Call 與 Bull Call Spread。
3. 一次抓取市場資料後，共用同一 Snapshot 分析所有策略。
4. 顯示跨策略最佳候選比較表。
5. 每個策略至少顯示前三名候選。
6. 每個策略第一名候選自動顯示 P/L Heatmap。
7. Heatmap 正確標示現價、目標價、目標日期與到期日。
8. Heatmap 數值與現有 CLI 矩陣逐格一致。
9. GUI 不包含任何獨立重寫的金融計算公式。
10. 錯誤與空結果均以使用者可理解的文字顯示，不暴露 traceback。
11. 真實 TLT 測試可同時產生 Long Call 與 Bull Call Spread 結果。
12. 同 Snapshot、同輸入的 GUI 與 CLI 候選排名及數值一致。
13. Docker 啟動後可正常完成相同分析。
14. 手機瀏覽器可完成輸入、查看比較表及水平捲動 Heatmap。

⸻

11. 產品核心原則

Option Chaser Web GUI 的價值不在於提供更多欄位，而在於：

輸入一個價格劇本
→ 自動掃描整條選擇權鏈
→ 找出最適合的單腿與價差
→ 同場比較報酬
→ 用 Heatmap 看時間與價格風險

任何不能直接服務這條流程的功能，都不應加入第一版。
