# Option Chaser Repository Instructions

## 專案目標

Option Chaser 是選擇權劇本分析工具。產品應把劇本、候選策略、交易成本、風險與情境結果整理成清楚、可信、可操作的分析介面。

## 架構與金融計算邊界

- `option_chaser/` 內的金融計算引擎是已驗證的核心，不得任意修改、重寫或搬移公式。
- GUI 不得自行實作金融公式、估值、排名或衍生數值。
- `webapp/` 只能顯示與格式化 service/store 已產生的資料，尤其應以 `option_chaser.service` 的結果及 `option_chaser.store.serialize_result()` 產生的 view dict 為資料來源。
- 若畫面需要新數值，先確認 service/store 是否已提供；不得為了方便直接在 view、component 或 render 層重算金融結果。

## UI 與產品品質

- `ui_reference/index.html` 是視覺與資訊層級參考，不是可直接複製的 App 外殼。
- 不得複製 Claude 網站外框、Artifact 外框、假瀏覽器視窗、假網址列或平台注入腳本。
- 實際 App 必須比目前的 Streamlit 工程後台感更接近正式產品，包含清楚的資訊架構、視覺層級、間距、卡片、狀態與操作流程。
- UI 施工完成後，必須以真實瀏覽器開啟實際 App 驗收並保存截圖；測試全綠只是必要條件，不足以代表 UI 完成。
- 視覺驗收至少應涵蓋實際桌機與手機 viewport；不得以靜態 mockup、AppTest 或文字斷言代替真實瀏覽器截圖。

## Windows BAT 檔案

- `啟動 Option Chaser.bat` 與 `建立桌面捷徑.bat` 是 Windows 使用者入口。
- 這兩個 BAT 檔案必須保留既有編碼與 CRLF；目前為 cp950（Big5）加 CRLF，不得任意轉成 UTF-8、LF 或用會改寫編碼的工具重存。
- 除非任務明確要求且能在 Windows 實機驗證，否則不要修改 BAT 檔案。

## Git 限制

- 不得合併 `master`，也不得把目前工作合併到 `master`。
- 除非使用者另有明確指示，不執行任何涉及 `master` 的 merge。

## 里程碑回報

每個里程碑完成後都必須先回報：

1. 改了哪些檔案，以及各檔案的改動目的。
2. 使用哪些指令、測試、資料與操作流程驗證。
3. 真實瀏覽器截圖存放在哪裡；提供可定位的檔案路徑，並註明桌機或手機畫面。

若里程碑尚未產生適用的 UI 截圖，必須明確寫出「本里程碑無 UI 截圖」及原因，不得省略此項。
