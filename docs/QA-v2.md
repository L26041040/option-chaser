# Option Chaser — QA-v2 後續維修需求

以下為目前需求方已確認的維修需求與已知問題。
此文件只記錄需求，不預先指定實作方式或施工順序。

## A. 已確認功能問題

### 1. 排除已過期選擇權合約
目前分析流程仍可能把已經過期的合約納入處理。

需求：
- 已過期合約不應進入有效候選分析。
- 不應浪費計算資源分析已經無法交易的合約。
- 需確認所有相關分析、排序與顯示流程皆一致排除。

### 2. 刷新時 Long Call 也必須重新計算
目前刷新可以重新計算 Bull Call Spread，但 Long Call comparison 沒有同步刷新。

需求：
- 刷新市場資料／重新分析劇本時，Long Call comparison 也必須使用最新資料重新計算。
- 不應出現 Spread 已更新、Long Call 仍停留在舊 snapshot 的狀態。

### 3. Analysis refresh 後進階資料可能殘留舊 cache
PR #66 review 發現：

- Scenario analysis 更新後，Spread History / Raw Data 可能仍保留上一輪 analysis 的內部 cache。
- 若使用者在刷新前已打開這些區塊，刷新後可能繼續看到舊 candidate / 舊 snapshot 資料。

需求：
- 新 analysis 完成後，所有與該 analysis 綁定的進階資料必須同步失效或更新。
- UI 不可混用新 analysis 與舊 cache。


## B. UI / UX 尚未符合原始需求

### 4. Desktop 20/80 版面尚未真正完成
原始需求為 Desktop 約 20/80：

- 左側：劇本庫 sidebar
- 右側：主要工作區

目前劇本庫仍主要位於上方，沒有形成真正的左側劇本庫工作流。

需求：
- Desktop 回到明確的左側劇本庫＋右側主要工作區架構。
- Mobile 可使用不同 responsive layout，不要求硬套 20/80。

### 5. 主要操作按鈕位置
原始需求希望主要操作按鈕集中在工作區正上方，形成固定、容易理解的操作入口。

需重新檢查目前：
- 建立劇本
- 刷新
- 劇本庫
- 其他主要操作

是否符合此操作邏輯。

### 6. 目標年月輸入體驗
目前年月選擇方式仍不符合需求。

需求：
- 年份預設為 `20xx` 邏輯，使用者主要只需輸入年份後兩碼。
- 日期／年月 selector 在按下日期區域時應一次直接下方展開，不該由使用者去旁邊按日曆📅圖案。
- 減少手機與桌面輸入年月所需操作次數。


## C. 外部資料問題

### 7. 市場利率仍無法正常取得
目前實際使用時利率仍經常顯示離線／fallback，代表 Treasury rate pipeline 尚未真正完成 production 驗證。

需求：
- 查明目前抓取失敗原因。
- 驗證 Treasury endpoint、response format、parser 與部署環境。
- 若目前資料源不適合 production，評估替代的可靠公開利率資料來源。
- 最終應讓期限對齊利率曲線在正常連網環境下真正取得市場資料，而不是長期依賴 4% fallback。

