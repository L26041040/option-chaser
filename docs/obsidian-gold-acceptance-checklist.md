# Obsidian Gold（OG-01～OG-12）全站驗收清單

給 Owner 用真機走一遍的清單。依專案規則，視覺驗收本身不貼截圖進對話
——這份清單只負責告訴你「每一條該去哪裡看、看什麼」，以及哪些已經有
自動化測試守住、哪些需要你親自在真機上確認。

Working branch：`ui-redesign/graphite-amber`（尚未開 PR，依專案規則等
Owner 真機驗收後 cue）。

**圖例**：✅ 已完成，自動化測試覆蓋 ｜ ⚠ 已完成但需要你親自確認（多半是
「好不好看」這類主觀判斷，或環境相關狀態）｜ 📝 已知的 artifact 與現行
實作差異，已記錄、留給你裁示是否要另開票補上，本輪不自行改設計。

---

## 0. Artifact 10 張板逐張截圖對照——處理狀態

本輪用真實 headless Chromium 對 8 張板截圖，用相同的路由 mock（真實
契約樣本／`analysis_sample_call_fly.json`）跑出對應頁面後肉眼核對，逐張
記錄差異（見下方各節 📝 項目）；另外 2 張說明如下，並非遺漏：

| # | Artifact 板 | 處理方式 |
|---|---|---|
| 1 | Desktop-Library | 截圖對照，見 §2.3 |
| 2 | Desktop-Library-Light | 截圖對照（淺色），見 §1.3／§2.3 |
| 3 | Desktop-Detail | 截圖對照，見 §2.4 |
| 4 | Desktop-LongCall-IV | 已在 OG-08（#326）實作階段逐字比對過版位並有專屬 e2e 鎖定（`e2e/desktop.spec.ts` 「OG-08」兩條測試），本輪不重複截圖 |
| 5 | Desktop-Settings-Admin | 截圖對照，見 §2.6 |
| 6 | Main | **設計 token／字級／間距參考板，不是一個實際頁面**（`<title>Foundations · Obsidian Gold</title>`），沒有對應的單一 app 畫面可以截圖比對；改由 OG-01 落地時的 `contrast.test.ts`／`foundations.spec.ts` 逐項驗證同一批 token 數值 |
| 7 | Mobile-Detail | 已在 OG-10（#327）實作階段逐字比對過版位並有專屬 e2e 鎖定，本輪不重複截圖 |
| 8 | Mobile-Library | 截圖對照，見 §3.1 |
| 9 | Mobile-Library-Light | 截圖對照（淺色），見 §1.3／§3.1 |
| 10 | Mobile-Settings | 截圖對照，見 §3.3 |

---

## 1. Foundations（OG-01 #317）

**1.1 Obsidian Gold token 全站生效（字體、底色、金色強調色）** ✅
`e2e/foundations.spec.ts`：Geist／Noto Sans TC 真的 loaded、`body` 背景色
是新 token（深色 `#0B0E11`／淺色 `#F5F5F5`，本輪新增淺色斷言）。

**1.2 StockLogo 契約：真 Logo 或什麼都不留** ✅
`src/StockLogo.tsx` 靜態掃描：全站只有這一處組 Logo.dev URL（`fallback=
404`），沒有任何首字母／通用圖示／favicon 猜測的替代邏輯（本輪掃描
`grep -rniE "monogram|initials|favicon|generic.*stock.*icon"` 全站零命中）。
`StockLogo.test.tsx` 覆蓋三態。

**1.3 淺色模式：對照 artifact 兩張淺色板** ⚠ 需你親自看
`src/contrast.test.ts` 守住 WCAG AA 對比（含已知裁示：`--text-3` 深色
tertiary 既有低對比狀態如實記錄、非本輪缺陷，見該檔案檔頭說明）；
`e2e/foundations.spec.ts` 新增的淺色 token 斷言只驗證顏色數值套用，實際
「好不好看」「跟 artifact 排版是否一致」仍需要你在瀏覽器切換系統深/淺
色模式親自看一次劇本庫（桌面＋手機）。

**1.4 📝 已知差異：沒有站內手動深/淺色切換按鈕**
Desktop-Library／Desktop-Library-Light 兩張 artifact 板的桌面頂欄都畫了
一顆「切換深淺色」icon button；現行實作全站只跟隨作業系統
`prefers-color-scheme`，沒有站內手動切換 UI。這不是任何一張 OG 子票的
明確要求（OG-01～OG-12 沒有一張票的 AC 提過手動切換開關），本輪不新增
這個功能，記錄供你裁示是否要另開票。

---

## 2. 桌面版（OG-02／OG-03／OG-06／OG-07／OG-08／OG-11）

**2.1 常駐頂欄導覽，全站單一全寬頁面（OG-02 #318）** ✅
`e2e/desktop.spec.ts` 多條既有測試覆蓋：建立劇本／垃圾桶／設定入口在
頂欄、瀏覽器上一頁/下一頁正常、`.library-pane`／`.detail-pane`／
`.workspace` 三個舊 class 結構性移除。

**2.2 劇本庫 Markets 風格表格（OG-03 #320）** ✅
方向／狀態篩選 chip 純前端過濾、垃圾桶頁同一套表格換皮、批次選取／
還原／刪除。

**2.3 📝 已知差異：劇本庫頂部沒有 artifact 畫的 5 格業務指標＋Family 篩選
＋搜尋框**
Desktop-Library.dc.html 畫的劇本庫上方是「追蹤中的劇本／最佳劇本報酬／
今日刷新＋節流／資料來源／Vendor 每日預算」五格 stat＋一個 Family
segmented control＋一個搜尋輸入框；OG-03／OG-04／OG-05 三張票各自的
issue body 明確只要求「方向與狀態篩選 chip」與「唯讀使用量摘要 stats
strip（進行中劇本／最近活動／刷新節流間隔，Super Admin 才多看到
Vendor 預算／429 事故兩格）」——這是三張票**各自 issue body 明訂的範圍**
，不是本輪疏漏。目前沒有 Family 篩選、沒有搜尋框、stats 內容與 artifact
不完全相同。記錄供你裁示是否要另開票對齊。

**2.4 桌面詳細頁三欄外殼（OG-06／OG-07 #321／#325）** ✅
`e2e/desktop.spec.ts`「OG-06／OG-07」「T16」「T17」「T18」等既有測試：
左欄 family tabs／到期日 chip／排名表、中央常駐 Heatmap＋三價位階梯、
右欄候選面板（進場／Payoff／Greeks／報告）、底部四個收合 tab。

**2.5 桌面 Historical IV 右欄換皮（OG-08 #326）** ✅
`e2e/desktop.spec.ts`「OG-08」兩條測試：單腿＋Super User 以上時右欄整個
換成 `<IvHistory>`，Normal User／兩腿以上候選右欄仍是既有候選面板、
零 IV 請求。

**2.6 設定頁 subnav／Super Admin 後台（OG-11 #322）** ✅
`e2e/desktop.spec.ts` 既有角色可見度矩陣測試：Normal 看不到管理面板，
Super Admin 登入後「管理後台」分頁可見 ops-metrics stats／owner 篩選／
type-to-confirm 刪除。

**2.7 1100px 斷點與中間寬度不溢出** ✅（本輪新增）
`e2e/desktop.spec.ts`「OG-12」兩條新測試：1099px↔1100px 兩側 chrome
乾淨互斥；1150px 中間寬度下劇本庫表格與詳細頁三欄外殼皆不觸發整頁
水平捲動。**本輪順帶修正一個真實幾何缺陷**：`.toolbar` 的滿版負邊距
沿用 `var(--gap)`（16px），但 `.detail-page .screen` 的 padding 早在
QA-FIX-3 就已經改成 12px，兩個數字對不上，1100–1280px 這段中間寬度
會讓詳細頁頂欄溢出視窗 8px（新測試寫出來後才發現，不是刻意留著的舊
問題）；已在 `src/styles.css` 補上 `.detail-page .toolbar` 的對應覆寫，
純幾何修正、無任何內容或語意改變。

**2.8 手機 375px 不橫捲** ✅（本輪新增，一般性 page-level 守門）
`e2e/smoke.spec.ts`「OG-12」新測試：viewport 明確設成 375px（比既有
iPhone 專案預設的 390px 更窄），劇本庫與詳細頁（Butterfly 三腿，版面
最寬的情境）整頁 `document.documentElement.scrollWidth` 都不超過
`window.innerWidth`。既有 Heatmap／到期日 chip 橫向捲動測試各自只驗
自己那個功能容器本身的橫捲行為，這是本輪新增、獨立於任何單一功能的
整頁級守門。

---

## 3. 手機版（OG-09／OG-10）

**3.1 手機劇本庫＋底部導覽（OG-09 #319）** ✅
既有 iPhone e2e：52px 頂欄、密度、底部四個分頁常駐。

**3.2 手機詳細頁整頁重排（OG-10 #327）** ✅
`e2e/smoke.spec.ts`「OG-10」新測試：Family tabs／排名表在劇本主圖之前，
三價位階梯／進場面板（本輪新增，之前手機版完全沒有）緊接在主圖之後，
Historical IV 在進場面板之後；進場面板固定顯示冠軍、切換 family 分頁
零額外請求。既有「候選展開零請求」「Heatmap 橫捲」「vs 現價 短格式」
等既有斷言全數保留（見 issue #327 收尾留言的完整說明）。

**3.3 📝 已知差異：手機設定頁版面跟 Mobile-Settings 板不完全一致**
Mobile-Settings.dc.html 畫的是「帳戶與角色」（單一密碼輸入登入）＋
「資料來源」（唯讀 kv 摘要）＋「我的資料」三張精簡卡片；現行實作是
Settings／#124、#125 既有票留下的功能性頁面（Market Data／Historical
IV 各自獨立、有互動式的預設/自訂切換與儲存按鈕），資訊更完整但版面
密度與分卡方式跟這張 artifact 板不同。OG-01～OG-12 沒有一張票的 AC
要求重做手機設定頁版面（OG-11 只做桌面 subnav／後台），本輪不新增
這項工作，記錄供你裁示。

---

## 4. 語意零漂移證明（AC 明文要求，附驗證方式）

**4.1 後端／引擎零漂移** ✅
```
git diff ead06cb...HEAD --stat -- option_chaser/ api_app/
```
只命中 5 個檔案：`api_app/main.py`、`api_app/storage/__init__.py`、
`api_app/storage/memory.py`、`api_app/storage/postgres.py`、
`option_chaser/store.py`——全部是 OG-04（#323）／OG-05（#324）兩張已核准
純加法票的內容（`cost_sparklines()` 批次查詢、`candidate_key` 投影、
`/api/me/usage-summary` 端點、`vendor_fuse` 欄位）。valuation／ranking／
filters／ivpipeline／superuser／quota／vendor_fuse 核心邏輯、`storage`
既有讀寫路徑本身，零命中。

**4.2 契約樣本只多兩個核准 key** ✅
```
git diff ead06cb...HEAD -- contracts/scenario_row_sample.json
```
只新增 `cost_sparkline`（頂層）與 `representative_candidate.candidate_key`
（巢狀）兩個 key，逐字對應 OG-04 的核准範圍。

**4.3 Logo 政策靜態掃描** ✅（見 1.2）

---

## 5. 全套回歸數字

**前端**（本輪最後一次執行）：
- `npm run typecheck`：0 錯誤。
- `npx vitest run`：**44 個檔案、1041 條全綠**。
- `npm run build`：成功，`tsc --noEmit && vite build` 無警告。
- `PLAYWRIGHT_CHROMIUM_PATH=... npm run e2e`（iPhone＋Desktop 兩個
  viewport 專案）：**143 條全綠**（連續執行兩輪皆 143/143，含本輪新增
  的 1100px 斷點／中間寬度／375px 不橫捲／淺色 token 四條）。

**後端**（真實 Postgres，非記憶體 fallback）：
```
OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest" \
PYTHONPATH=. .venv/bin/python -m pytest
```
全綠（exit code 0），無 F／E，僅第三方套件的既有 deprecation warning
（`httpx`／`anyio` 相關，跟本輪改動無關）。

**斷言完整性**：本輪（OG-08／OG-10／OG-12）觸及的測試檔案 diff 裡，
唯二兩處「刪除既有斷言行」都是同一句話的**逐字等值或更嚴格**取代——
`.card` 總數斷言從舊順序的 8 張改成新順序的 9 張（新增進場面板卡片後
的必然結果，不是弱化）；一處未縮小範圍的 `getByText` 改成 `within(...)`
scoped 查詢（新增內容造成的文字重複衝突，斷言的期望值本身逐字不變）。
兩處皆已通過兩軸 `/code-review` 的 Spec 軸獨立確認。全系列（OG-01～
OG-12）診斷用 `git diff` 沒有找到任何新增的 `.skip(`／`test.skip`／
`describe.skip`。

---

## 6. 尚待你確認的項目

- 1.3／2.3／3.3 三項「📝 已知差異」是否要另開後續票調整（劇本庫指標
  Family 篩選／搜尋框、手機設定頁精簡化、站內深淺色切換按鈕）。
- 真機（非模擬器）上手機 Safari／Chrome 的觸控手勢（橫向捲動、tap
  scrubber）與淺色模式觀感，本清單只能證明自動化幾何斷言通過，實際
  手感仍需你在真機上確認。
- 未開 PR——確認上述項目後請告知，再依你的指示開 PR 或繼續調整。
