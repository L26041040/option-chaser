# Seed Warm（SW-01～SW-09）全站驗收清單

給 Owner 用真機走一遍的清單。依專案規則，視覺驗收本身不貼截圖進對話
——這份清單只負責告訴你「每一條該去哪裡看、看什麼」，以及哪些已經有
自動化測試守住、哪些需要你親自在真機上確認。

Mother issue：**#330**（SEED-WARM-SPEC-001）
Working branch：`ui-redesign/seed-warm`（尚未開 PR，依專案規則等 Owner
真機驗收後 cue）。
Canonical 視覺 artifact（Direction A · Seed Warm evolved）：
`https://claude.ai/artifact/TS2KZEjtYPkzGuYDTFd4HA`

**圖例**：✅ 已完成，自動化測試覆蓋 ｜ ⚠ 已完成但需要你親自確認（多半是
「好不好看」這類主觀判斷，或環境相關狀態）｜ 📝 已知的 artifact 與現行
實作差異，已記錄、留給你裁示是否要另開票補上，本輪不自行改設計。

Scope 提醒：本系列**只做淺色**（`prefers-color-scheme` 分支整段移除，
`:root` 恆為淺色 Seed Warm token），dark mode 明確排除在 #330 之外，
不是遺漏。

---

## 1. Foundations（SW-01 #331）

**1.1 Seed Warm token／字體全站生效** ✅
`src/seedWarm.test.ts`：`--paper`／`--card`／`--ink`／`--acc` 等新
canonical token 逐一比對 hex 值；Plus Jakarta Sans＋Noto Sans TC 真的
`<link>` 載入，不再載入 Geist；`color-scheme: light`；`prefers-color-
scheme` 字面零命中。`src/contrast.test.ts` 守住 WCAG AA 對比（含
Heatmap 最深色格的 worst-case alpha 混色）。

**1.2 StockLogo 契約：真 Logo 或什麼都不留** ✅
`src/StockLogo.tsx` 靜態掃描：全站唯一一處 `<img>`，唯一一處組
Logo.dev URL（`img.logo.dev/ticker/{SYM}?...&fallback=404`），沒有任何
首字母／通用圖示／favicon 猜測的替代邏輯（SW-09 本輪重新掃描一次
`grep -rn '<img\b'`，全站只有這一處）。`StockLogo.test.tsx` 覆蓋三態。

**1.3 `.pXXX` primitives：ARIA 契約與實際採用率** ⚠ 見下方 1.4
`SeedWarmPrimitives.test.tsx` 驗證每個曾經計畫要用的 primitive 該有的
ARIA 模式（`role=group`＋`aria-current`、原生 `disabled`、
`role=progressbar`＋`aria-valuenow`）。

**1.4 📝 已知落差：11 個 SW-01 primitives 裡有 6 個到 SW-08 為止從未被
任何真實畫面採用**
SW-01 檔頭原本設想 `.pbtn`／`.pnav`／`.pseg`／`.pchip`／`.ptag`／
`.pcard`／`.pstat`／`.pinp`／`.pdot`／`.pbar`／`.pinfo` 這批新
primitives 會在 SW-02～SW-08 各自落地。SW-09 盤點結果：
- 確實被採用：`.pbtn`（全站按鈕）、`.pnav`（`TopBar.tsx`）、`.pcard`
  （`CompactScenarioList.tsx`）、`.pstat`（`MobileStatsStrip.tsx`／
  `SuperUserAdmin.tsx` 的 `OpsStats()`）、`.pinfo`（`InfoTooltip.tsx`）。
- **從未被採用、SW-09 已把 CSS 宣告當死程式碼整段刪除**：`.pseg`／
  `.pchip`／`.ptag`／`.pdot`／`.pbar`——方向 segment／到期月份 chip／
  狀態徽章／表格狀態欄／比例條這五個位置，SW-02～SW-08 全部沿用
  「既有 primitives 對照表」指名的既有 `.seg`／`.chip`／`.tag.up`／
  `.down`／`.flat` 家族，不是這裡新造的五個 class。
- `.pinp` 是唯一一個「有明確理由不用」的例外（`CreateForm.tsx`／
  `RoleLogin.tsx` 檔內註解說明：16px 字級是 iOS Safari 防止整頁縮放的
  既有可及性保護，換成 `.pinp` 會撤掉這個保護，兩者顏色／圓角本來就
  同源 Seed Warm token，純粹是同一件事的兩種寫法）——CSS 予以保留，
  供未來非全寬欄位使用，不算死程式碼。

本輪已同步移除 `SeedWarmPrimitives.test.tsx` 裡對應 `.pseg`／`.ptag`／
`.pbar` 的三個示範測試（class 本身已刪，繼續留著會誤導成「這個
primitive 還在用」），只保留確實被採用的 `.pnav`／`.pbtn` 兩組契約
測試。

---

## 2. 桌面版（SW-02／SW-03／SW-05）

**2.1 常駐頂欄導覽，64px→68px（SW-02 #332）** ✅
`e2e/desktop.spec.ts`：`TopBar` 用 `.pnav`／`.pbtn`，目前頁靠
`aria-current="page"` 標示（不是 class）；68px 高＋暖米色；三處依賴
舊 64px 高度的 sticky/fixed 偏移量同步更新；Settings 子導覽
（`.settings-subnav`）局部 pill 化，不動全站共用 `.chip`。

**2.2 桌面劇本庫（SW-03 #334）** ✅
`e2e/desktop.spec.ts`／`src/ScenarioList.test.tsx`：標題 32px/800＋
副標（劇本數＋最後批次更新時間）；刷新鈕 `.pbtn`；表格 11 欄→9 欄
（現價／目標價合併、更新時間合併為狀態格＋可讀文字）；過期列變暗
（`.compact-card.expired`，跟 `.locked`／`.failed` 互斥）；Vendor
每日預算／429 事故兩格搬到 `SuperUserAdmin.tsx`，一般劇本庫頁面零
`/api/ops/metrics` 請求。

**2.3 桌面詳細頁（SW-05 #337）** ✅
`e2e/desktop.spec.ts`：身分列新增劇本報酬列（正負色＋family 標籤），
5 格 meta 收斂成 4 格；`DesktopDetail.tsx` 補上跟手機同款的冠軍徽章
（`FamilyTabs.tsx`／`DesktopDetail.tsx` 各自獨立渲染 family tabs，
SW-06 當時漏補桌面這份，`/code-review` Spec 軸抓到後補齊）；
`.chip` pill 圓角從 SW-06 的 scoped 版擴大成全站無條件套用。

**2.4 1100px 斷點與四寬度不溢出** ✅
`e2e/desktop.spec.ts`：1099px↔1100px 兩側 chrome 乾淨互斥；1150px
（1100–1280px 中間寬度）劇本庫表格／詳細頁三欄外殼／垃圾桶／設定／
隱私皆不觸發整頁水平捲動；1440px 劇本庫／詳細頁／垃圾桶／設定／
隱私同樣不溢出（SW-09 本輪補齊垃圾桶在三個桌面寬度下、設定／隱私在
1100px／1150px 下原本沒測過的缺口）。

---

## 3. 手機版（SW-04／SW-06）

**3.1 手機劇本庫（SW-04 #333）** ✅
`e2e/smoke.spec.ts`：單一「＋ 建立劇本」入口併入標題列
（`.mobile-home-head`），`Dashboard.tsx`／`CreateEntry.tsx` 兩個檔案
刪除；`BottomNav` 3 個分頁（無 `create`）；`BetaNotice` 持續可見
（PB-12／#302 AC9 硬性要求）；新 `MobileStatsStrip`（3 個真實
`usage-summary` 欄位）；`.mnav` 52px→60px。

**3.2 手機詳細頁（SW-06 #335）** ✅
`e2e/smoke.spec.ts`：新 `MobileHero`（Logo＋代號＋方向 pill、劇本
報酬、目標價、4 格統計）；新 60px `.detail-bar` 取代手機版 `.toolbar`；
`FamilyTabs.tsx` 新增冠軍徽章（`aria-hidden`）。

**3.3 手機 375px 不橫捲** ✅
`e2e/smoke.spec.ts`：劇本庫／詳細頁／設定／隱私／垃圾桶（SW-09 本輪
補齊垃圾桶這一項，之前四個一般畫面裡唯一沒測過的）在 375px 下整頁都
不出現水平捲軸。

---

## 4. 表單／設定／隱私／登入／Super Admin（SW-07 #336）

**4.1 全部完成** ✅
`CreateForm.tsx`／`Settings.tsx`／`RoleLogin.tsx` 按鈕換 `.pbtn`；
`DeleteMyData.tsx` 新 `.danger-zone`；`SuperUserAdmin.tsx` 的
`OpsStats` 換 `.pstat`/`.pstat-grid`。

**4.2 📝 已知落差：`.pinp` 未套用到全寬輸入框**
見 1.4——iOS Safari 16px 防縮放保護與 `.pinp` 衝突，兩者顏色/圓角本來
就同源 token，是視覺上的等價替代，不是漏改。

---

## 5. 圖表換色（SW-08 #338）

**5.1 全部完成** ✅
`heatmap.ts` 的 GAIN／LOSS 顏色與 alpha 換成 Seed Warm `--up`／
`--down`；`Heatmap.tsx` 新增目標列／現價列的差異化高亮
（`anchor-target`／`anchor-spot`）；`PriceLadder.tsx` 目標列強調；
`SpreadHistory.tsx`／`IvTrend.tsx` 換 `--acc-text`；SVG 圖表 `<text>`
補上 `tabular-nums`（跟既有 `<table>` 版 Heatmap 一致）。

**5.2 📝 已知落差：手機版沒有淨成本走勢縮圖**
`CostSparkline.tsx` 只掛在桌面劇本庫（`CompactScenarioList.tsx` 手機列
本來就沒有這一欄，artifact Mobile 劇本庫板本來就沒有這格）——不是
漏補手機版，是這個資料點在手機劇本庫上結構上不存在，沒有意義的假
覆蓋。

**5.3 📝 已知落差：`PriceLadder` 沒有獨立「現價」錨點列**
`PriceLadder.tsx` 只有目標價列可以強調，現價本身不是這個元件的資料
點（現價已經在身分列／Heatmap 錨點列顯示過），維持原本的三價位階梯
定位。

---

## 6. 語意零漂移證明（AC 明文要求，附驗證方式）

**6.1 後端／引擎／API／契約零漂移** ✅
```
git diff af2163d..HEAD --stat -- api api_app option_chaser tests contracts
```
（`af2163d` 為 SW-01 第一個 commit `8c7547d` 的父 commit）——**零命中**，
全系列（SW-01～SW-09）沒有任何 commit 碰過後端／引擎／API／契約樣本，
純前端視覺重構。

**6.2 Logo 政策靜態掃描** ✅（見 1.2）

**6.3 舊 Obsidian Gold token／CSS 整段移除** ✅
`grep -nE "^\s*--(bg|panel|panel-2|panel-3|panel-4|text|text-2|text-3
|accent|accent-hover|accent-text|on-accent|accent-soft|card-shadow
|bg-elevated|separator|label|label-secondary|label-tertiary|tint
|green|red|orange|yellow):" src/styles.css` 與對應的
`grep -o "var(--<name>)"` 掃描：23 個舊名稱在 `:root` 宣告與消費端
（`var()`）皆零命中，`src/seedWarm.test.ts` 的「SW-09：contract 階段」
區塊逐一斷言鎖定。`src/obsidianGold.test.ts`（本來就標記「待 SW-09
刪除」的占位檔案）已整份移除。

**6.4 全站文案掃描：vendor／候選池／口徑／限流事故／規劃中／
placeholder 零殘留** ✅
新增 `src/bannedCopy.ts` 共用清單，取代 SW-06／SW-07 各自複製的小
清單；覆蓋範圍：`CreateForm`／`Settings`（Normal User 視角）／
`PrivacyPage`／`DeleteMyData`／`RoleLogin`（新增測試檔）／
`ScenarioDetail`（手機）／`DesktopDetail`／`CandidatePool`／
`FamilyTabs`／`ScenarioList`（桌面劇本庫）／`CompactScenarioList`
（手機劇本庫）／`TrashView`。**刻意排除**：`SuperUserAdmin.tsx`
（Super Admin 專用內部維運面板，不是一般使用者畫面）、
`RawData.tsx`／`Diagnostics.tsx`（逐字顯示後端原始欄位名稱是這兩個
元件存在的目的本身）、`AnalysisReport.tsx` 的「Model & Assumptions」
技術揭露區塊（`q_source` 等欄位值本來就是逐字顯示的模型參數來源）。

**6.5 死 CSS 清理** ✅
SW-09 本輪額外刪除的死 class（皆已用 word-boundary grep 逐一確認全站
零 `.tsx` 消費端）：整組 OG-01 落地但從未被消費的 `.btn` 家族
（`.btn`／`.secondary`／`.danger`／`.ghost`／`.sm`／`.xs`／`.dis`）與
`.iconbtn`；`.card-tap`／`.metric-group`／`.chevron`；`.pill-trash`／
`.compact-archive`（兩處）；`.button.subtle`；`.screen-section`；
`.tag.gold`／`.tag.info`／`.tag.fam`（`.tag.flat` 保留，移除跟它合併
宣告的 `.fam`）；整組 `.sym`／`.legs`／`.inp`／`label.lb`；
`.tbl tr.hov`／`.tbl tr.dim`；以及 1.4 節列出的 `.pseg`／`.pchip`／
`.ptag`／`.pdot`／`.pbar`／`.pstat .pstat-d`。

---

## 7. 全套回歸數字

**前端**（本輪最後一次執行）：
- `npm run typecheck`：0 錯誤。
- `npx vitest run`：**49 個檔案、1326 條全綠**。
- `npm run build`：成功，`tsc --noEmit && vite build` 無警告；CSS
  bundle 因本輪死程式碼清理而縮小。
- `PLAYWRIGHT_CHROMIUM_PATH=... npm run e2e`（iPhone＋Desktop 兩個
  viewport 專案）：連續執行兩輪，150/150 條全綠（含本輪
  新增的垃圾桶四寬度／設定與隱私 1100px／1150px 缺口共 4 條新測試）。

**後端**（真實 Postgres，非記憶體 fallback）：
```
OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest" \
PYTHONPATH=. .venv/bin/python -m pytest
```
全綠：**2400 條測試，exit code 0**，無 F／E（連續兩次獨立執行同一份
指令核對，數字一致）。僅第三方套件的既有 deprecation warning
（`httpx`／`starlette` 相關，跟本輪改動無關）。

---

## 8. 尚待你確認的項目

- 1.4／4.2 節「`.pinp` 未套用」與 5.2／5.3 節兩項圖表資料點落差，是否
  需要另開後續票調整（本輪判斷都是結構上的合理限制，不是實作疏漏）。
- 真機（非模擬器）上手機 Safari／Chrome 的觸控手勢與淺色配色觀感，
  本清單只能證明自動化幾何與對比度斷言通過，實際手感仍需你在真機上
  確認一次（尤其是 terracotta 強調色在戶外強光下的可讀性）。
- 未開 PR——確認上述項目後請告知，再依你的指示開 PR 或繼續調整。
