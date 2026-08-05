Option Chaser — MVP V2 Mobile UX Spec

1. Mobile 首頁定位

手機版的預設首頁就是「劇本庫」。

不要把 Desktop 的 20/80 master/detail 硬縮成手機版。

Mobile UX 主要參考成熟券商 App，例如：

* Firstrade
* eToro

重點是高資訊密度、操作直接、金融資訊容易掃描，而不是把每個劇本做成很高的大卡片。

⸻

2. 首頁上方 Dashboard 區域

首頁最上方先保留一塊 Dashboard / Summary 區域。

目前 MVP V2 尚未決定這裡要放哪些報表或跨劇本指標，因此：

* 先保留版面位置。
* 不要為了填滿空間自行發明 KPI。
* 後續跨劇本比較功能確定後，再決定這裡的內容。

⸻

3. 新增劇本

Dashboard 下方提供明確的「新增劇本」入口。

平常新增劇本區域保持縮合狀態，例如：

＋ 新增劇本

點擊後：

* 原位置向下展開／放大成完整建立劇本表單。
* 不使用傳統 modal popup。
* 不切換到另一個頁面。
* 建立完成後可以自然收合回原本的 compact 狀態。

概念是 inline expandable composer，而不是獨立頁面。

⸻

4. 劇本庫呈現方式

所有 Scenario 以 Firstrade 持倉／Watchlist 類似的 compact row 方式，由上往下排列。

目的：

壓縮高度，不是刪除資訊。

每個劇本不要使用目前過高的大型 Card。

⸻

5. 每個 Scenario Row 必要資訊

每一列至少必須清楚顯示：

* Ticker
* Target Price
* Target Month
* 該劇本目前代表／最高到期報酬
* 產生這個報酬的 Strategy Type
* Buy Strike
* Sell Strike（若為 Spread）
* Actual Expiry
* Scenario Status / Traffic Light
* Last Updated Time

例如：

TLT   Target 105 · 2028/05        🟢

+238%   Call Spread B100 / S105

Exp 2028/05/19 · Updated 10:32

不能只顯示：

+238%

因為使用者必須立刻知道：

這個收益是哪一個 option combination 產生的。

未來若代表策略是 Long Call，也應能自然顯示：

Long Call B100

而不是需要重新設計 Scenario Row。

⸻

6. Scenario Navigation

點擊任一 Scenario Row：

→ 進入該 Scenario 的詳細分析頁。

手機不需要同時顯示 Scenario Library 與 Detail。

返回後回到原本劇本庫位置與狀態，不應讓使用者重新從首頁頂端開始找。

⸻

7. Mobile 資訊密度原則

Mobile 版應參考 Firstrade / eToro：

* 壓縮垂直 padding
* 減少不必要的大標題
* 減少大型 Card 留白
* 關鍵金融數字優先
* 次要 metadata 使用較小 typography
* 一眼能掃描多個 Scenario

但不得因為追求 compact 而刪除投資決策所需資訊。

核心原則：

壓縮的是留白、裝飾與重複標籤，不是金融資訊。

⸻

8. Desktop 與 Mobile 是兩套 Responsive Layout

Desktop：

左側約 20% Scenario Library | 右側約 80% Main Workspace

Mobile：

Dashboard
↓
Expandable Create Scenario
↓
Compact Scenario Library
↓
Scenario Detail

兩者共用相同資料與產品語意，但 navigation / layout 不要求完全一致。

⸻

9. Visual Reference

MVP V2 的 Mobile UI / UX 可以明確參考：

* Firstrade mobile app
* eToro mobile app

參考的是：

* Information hierarchy
* Portfolio / Watchlist row density
* Typography hierarchy
* Financial-number presentation
* Navigation interaction
* Spacing
* Button / control treatment

不是要求逐像素複製品牌視覺。

目標是讓 Option Chaser 看起來像成熟的投資工具，而不是一般 CRUD Web App。