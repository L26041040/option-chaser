# Anonymous Public Beta — Final Owner Decision Packet（回報#078）

> 狀態：**2026-09-12 產出，全部 OD 尚未由 Owner 回答。** 本文件是問題包，
> 不是決策紀錄——任何未來 session 不得把下方「Fable 建議」誤記為 Owner
> Decision。Owner 回覆後，答案應逐票貼進 #282～#289 的 resolution
> comment、地圖 #272 的 Decisions so far，並把詞條寫進 CONTEXT.md。
>
> 產出指令：`OPTION-PUBLIC-BETA-GRILL-004`（`/grill-with-docs`）。該 skill
> 標 `disable-model-invocation`，本輪改直接載入它指向的 `/grilling`＋
> `/domain-modeling`；Owner 明文要求「一次整理成完整問題包」，因此不採
> grilling 預設的一次一題。研究依據：地圖 #272、#273～#280、#290 與對應
> `docs/research/*.md`；Ownership A-1／Scaling Foundation canonical docs；
> production 公開端點與 Vercel MCP 實查（見第 1 節）。

---

## 1. 已確定、不需再問 Owner 的硬事實

### 1a. #281 七題——本輪自行查證完畢，Task 票可直接 close

| # | 題目 | 結果 | 依據 |
|---|---|---|---|
| 1 | Vercel 方案 | **Hobby** | Vercel MCP `list_teams` 實讀 `plan: "hobby"`（專案層級 `get_project`／`list_deployments` 仍 404／403，帳號層級這次讀得到） |
| 2 | Fluid Compute 開關 | UNVERIFIED，**且作廢**——Scaling Foundation runtime 結論已裁「不得當 correctness dependency」，不影響任何決策 | 專案層級 404 |
| 3 | Vercel 用量 %／Cron | 用量 UNVERIFIED 但差好幾個數量級（1 使用者、4 劇本、19 份結果 vs Hobby 100 萬 invocations／100 GB 頻寬）。Cron：`/api/health` 顯示 rate `fetched_at 2026-09-11T14:37Z`，晚於排程 11:00Z，外部無法分辨是 cron 沒跑、`CRON_SECRET` 未設、或當時 Treasury 抓失敗後由同步 refresh-on-miss 補救；既有保底本來就會補，**不擋決策**，Owner 有空看一眼 Vercel Cron 頁即可 | production `GET /api/health` |
| 4 | Neon 方案／storage | **Free**（經 Vercel Marketplace 建，`docs/deploy-vercel.md`）；storage 用量 UNVERIFIED，上界可推：19 份快照 × TOAST 後每份約 0.1–0.5 MB ≈ 個位數 MB，遠低於 0.5 GB | repo 文件＋推估 |
| 5 | `pg_cron` | **作廢**——Free 方案 autosuspend 不可關，`pg_cron` 靜默不觸發；清理一律走 Vercel Cron 打 HTTP 端點（既有 `warm-rate-cache` 先例） | #273／#276 |
| 6 | 正式站劇本／快照數 | 4 個 active（TLT 2028-12／ORCL 2028-01／TSLA 2028-12／NVDA 2028-12）、0 個垃圾桶；結果列 7＋2＋6＋4＝**19**（≈快照數） | production `GET /api/scenarios`、`/results` |
| 7 | `owner_credentials` 有沒有 token | **有**——Market Data App 一把（masked `••••2TT0`，status ok，2026-08-12 存入），Historical IV `mode=custom` 已啟用 | production `GET /api/settings` |

→ #283／#284／#285 的唯一 blocker（#281）因此解除；全部 8 張 grilling 票技術上都可由本包一次回答。

### 1b. 現況暴露（本輪不帶任何身份實測，地圖已知事實 #1 的活證據）

- `GET /api/scenarios`：回 Owner 的 4 個劇本。
- `GET /api/settings`：回 token 已設定、遮罩尾碼、驗證狀態、更新時間。
- `GET /api/diagnostics`：回 44 筆診斷事件。
- `DELETE /api/diagnostics`、`DELETE /api/settings/credentials/{provider}`、`DELETE /api/scenarios/{id}`（封存後）：**全部不驗身份**。
- 結論：任何知道網址的人今天就能讀走／清掉 Owner 的診斷與第三方 token 紀錄。這是 I2（匿名身份 cookie）必須排在 Release line 第一項的直接理由，不是未來風險。

### 1c. 硬限制（安全／法規／平台已有唯一合理答案，列為施工前提，不當選擇題）

- **H1 匿名身份形狀**：隨機不透明 id 的 cookie＋伺服器查表；`HttpOnly`＋`Secure`＋`SameSite=Strict`＋`__Host-` 前綴；每次成功請求續命（瀏覽器 400 天上限）；owner id 設計成日後升級帳號時**不變、只多一個綁定**。JWT／簽章 token 在同源 SPA 零優勢、被偷不能單方作廢。（#275）
- **H2 `SOLO_OWNER` 退場**：不得恢復全站共用 solo（Owner 已裁）。
- **H3 Admin 身份**：獨立專屬 secret（第三把，比照 `CRON_SECRET`／`OPS_SECRET`「不同信任邊界不共用一把」）＋單一集中判斷點＋deny-by-default；Admin 自己的劇本仍走一般 owner cookie（Owner 已裁「Admin 資料歸 Admin 自己」）；不把 role 塞進 `owner_id` 字串或 cookie。若 Owner 堅持「同一顆 cookie 多一個 role」，請在回覆時明講。（#275）
- **H4 Admin 與壓測不繞過限流**：Admin 走獨立、較寬但有限的額度桶；controlled beta 壓測**預設走既有 DI 注入點（`fetch=`／`rate_loader=`／`dividend_loader=`）mock vendor**，不打真實 Cboe——`chain_backoff` 是 provider-global，真打必連坐同時段真人；synthetic owner 開跑前先加標記欄位。若要真打 Cboe 只能在明確小視窗、且知道會連坐。（#277／#276）
- **H5 owner 級刪除原語必須先存在**：含 `narrow_history` 孤兒修正、`owner_settings`／`owner_credentials`／`owner_verifications`／`diagnostics` 四張表的清理路徑——這是工程前提不是價值題；`owner_credentials` 的 token 清理節奏獨立、先於一般 retention 天數。（#276）
- **H6 清理排程載體**：Vercel Cron 打 HTTP 端點（`CRON_SECRET` 慣例），先用手動腳本跑幾輪驗證判定邏輯再自動化；不用 `pg_cron`；不用 `ctid` 做批次刪除。（#273／#276）
- **H7 頁尾一行**：網站全域、常駐、非阻斷：必要 cookie 告知＋「非投資建議」免責（既有 `disclaimer_text()` 目前埋在收合區）；不做 consent banner。（#279）
- **H8 Beta 不做 Analytics、不做廣告／CMP**（Owner 已裁；研究確認）。若日後要 Analytics，Vercel Web Analytics 等 cookieless 方案在英法新規則下免同意。
- **H9 CI 形狀**：GitHub Actions 跑既有四套測試＋GitHub branch protection required status checks（公開 repo 免費）；deploy 後 `/api/health` smoke；Sentry 免費層＋email 通知；LINE Notify 已於 2025-03-31 終止。Vercel 無官方機制等外部 CI，把關點在合併鈕。（#280）
- **H10 `/security-review` 位置**：碰身份／cookie／credential／限流／清理的每張票 pre-PR 一次；controlled beta 前、public beta 前各一次整體 pre-release；骨架 OWASP ASVS 5.0 Level 1＋憑證儲存相關少數 Level 2 條。（#280）
- **H11 市場資料（語意修正版）**：現行 Cboe／Yahoo 自動抓取**今天就違反雙方條款**（Cboe 明文封 IP）。OPRA 對延遲 ≥15 分鐘資料**不收即時 subscriber 類逐人費**，但把資料展示給外部使用者**仍需 vendor／redistribution licensing**——Intrinio Silver 的優勢來自它自己的 Business Display licensing arrangement，不是「延遲資料可以免費隨便公開」。Alpha Vantage／Polygon／MarketData.app 現有方案／Finnhub／Twelve Data 個人層全部明文禁止多使用者應用。換源工程輕量（`providers.py` 白名單＋一個 adapter）。（#290）
- **H12 平台**：現在不搬平台（Owner 已裁）；Vercel Hobby 非商業限制在無廣告無收費下不適用；Hobby 超額是暫停 30 天非扣款；Neon Free 滿了是寫入失敗非刪資料；production protection 不開（已裁）；`maxDuration:60` 可調到 300；WAF Rate Limiting Hobby 可開 1 條（edge 粗篩，零程式碼）。（#273）
- **H13 既有裁示不動**：Cboe backoff provider-global（SCALE-04）；Refresh Trigger 三個時機不新增（開站節流是既有時機的閘門，見 OD-5 請點頭）。
- **H14 封印／暫停**：SCALE-18／#269、Cross-Scenario／Holdings、RD-2。

---

## 2. 完整 OD 套件（9 題）

### OD-1｜清 cookie／換瀏覽器／無痕＝劇本不見——Beta 期間接不接受？要不要給救命碼？

你其實在決定：匿名產品最大的體驗缺口要不要在第一版就補、以及要不要為此收 email。12 個成熟產品沒有一個主動警告資料將遺失，也沒有一個提供救命碼——做了是超越業界，不做是業界常態。

A｜接受：Beta 期間明講「劇本只活在這個瀏覽器；清掉就沒了」，不做找回機制（owner id 依 H1 設計成日後可疊）。
B｜Mullvad 式救命碼：發一串碼讓使用者自己保管，換裝置輸入即認領；零個資、零寄信基礎設施，但使用者弄丟就真的沒了。
C｜Email magic link：最順暢，但要收 email、寄信、多一類個資與隱私義務。

Fable 建議：A（controlled beta），B 排在 public beta 後第一個看反饋再決定的項目。理由：不擋上線、不動資料結構、Beta 目標是驗證機制不是留客。
如果選錯會怎樣：A 錯＝有人辛苦建了劇本清 cookie 後抱怨；B／C 錯＝多做一套沒人用的機制。
以後好不好改：好改——A→B 純加法；A→C 要多收 email，但 owner id 不動。

### OD-2｜Owner 自己正式站上那 4 個 solo 劇本怎麼處理？

你其實在決定：舊資料是「認領進 Owner 自己的匿名 owner」還是「放掉重建」，也決定 I3 做不做。

A｜認領：一次性腳本（比照 `scripts/backfill_owner_ids.py`，Admin secret 保護）把 `owner_id="solo"` 的列改成 Owner 瀏覽器拿到的新 owner id；19 份快照的歷史走勢保留。
B｜放掉：上線後 Owner 用新 cookie 重建 4 個劇本；solo 資料整批刪（含 token）。省一支腳本，失去歷史。
C｜凍結：solo 列保留但沒人對得到（等於孤兒），日後再說。

Fable 建議：A。工程量一支用一次的腳本、既有慣例現成；它同時是「owner 級搬移／刪除原語」（H5）的第一個真實用例。
如果選錯會怎樣：B 錯＝TLT 自 2026-08 起的 19 份快照歷史沒了，不可逆；A 錯＝多寫一支腳本；C 違反「不得恢復 solo」精神且留孤兒。
以後好不好改：A 做完隨時可刪；B 不可逆。

### OD-3｜匿名陌生人可不可以存第三方 token／用 Historical IV？Settings 對陌生人開到哪？

你其實在決定：cookie 被偷的傷害半徑（只有劇本 vs 劇本＋別人的 API token）、`owner_credentials` 清理壓力、以及 MarketData.app 條款灰帶（伺服器代打、只回本人——條款未明寫，需客服確認）要不要在 Beta 就承擔。

A｜Beta 不開放：匿名者看不到自訂 provider／token 輸入；Historical IV 只對 Admin 身份；Settings 對匿名者只剩資料源顯示；Diagnostics 頁保留（cookie 上線後自然 owner-scoped）。
B｜開放但警示：可存 token，畫面明講「Beta 期間 token 存在我們資料庫、清 cookie 即失聯、N 天不用即清除」，並套 H5 較短清理節奏。
C｜照常：與今天相同，不加提示。

Fable 建議：A（first slice）。少掉 I8、少掉 ASVS 憑證條款在匿名者身上的驗收、少掉 MarketData.app 灰帶；Historical IV 本來只有自帶 token 的人用得到，陌生人幾乎不會有。
如果選錯會怎樣：A 錯＝少數有 token 的進階使用者用不到 Historical IV；C 錯＝陌生人的第三方 token 躺在 DB、被偷是別人的錢。
以後好不好改：A→B 純加法（拿掉隱藏＋加文案＋清理節奏）。

### OD-4｜匿名 owner 多久算沒人要、怎麼刪、快照跟不跟著走、要不要「立刻刪光」鈕？

你其實在決定：清理機制的形狀＋第一組數字，以及 OD-06「原始快照永久保留」在匿名者身上要不要維持（#283 明文要求重新確認，不能默默沿用）。30 天是業界最常見單一值（Firebase／Supabase／StackBlitz 各自獨立），完整範圍從幾小時到 14 個月。

A｜「明確使用者動作」（建立／編輯／手動刷新）算活動、sliding 續命、兩段式（軟過期後內部緩衝再硬刪，不做使用者救回 UI）；匿名 owner 的快照隨 owner 一起刪，Admin 自己的資料維持 OD-06 永久；Settings 加一顆「立刻刪光我的資料」鈕（同一個原語多一個入口）。
B｜固定時鐘（建立或最後分析起算 N 天、不續命）、一段式直接刪；其餘同 A。最能保證真的會清，但可能誤殺低頻使用者。
C｜三段式含使用者可見「即將清除、點此保留」的救回 UI；其餘同 A。體驗最好、工程最多、緩衝期照付 storage。

Fable 建議：A；起手數字建議 30 天無明確動作→軟過期、再 7 天→硬刪（Owner 改數字即可）；「開站自動刷新」不算活動（否則開著的分頁永遠續命）。
如果選錯會怎樣：A 太寬＝清不到人、Neon 慢慢滿（有 I6 告警兜底）；B 太嚴＝低頻真人被清。
以後好不好改：天數是設定值隨時改；A↔B 改判定函式即可；C 是純加法。

### OD-5｜額度起手數字：每個匿名 owner 幾個劇本、同一劇本多久內不重刷、全站每日 vendor 預算多少？

你其實在決定：機制存在是硬限制（H4），數字是 Owner 的風險承受度。業界找不到「匿名代打付費 API」的存活先例（#274），該偏保守。同時請點頭一句：「開站自動刷新加最短間隔」是既有時機的節流，不是第四個 Refresh Trigger。

A｜寬鬆起手：每 owner 20 個劇本（垃圾桶不計）、同一劇本 15 分鐘內不重刷、全站每日 chain fetch 預算 ≈ 現況日均 20 倍（用 `operational_metrics` 既有數字算；超過即降級成沿用舊資料＋既有 429 倒數 UI）。
B｜保守起手：10 個劇本、30 分鐘、預算 10 倍；超過即降級。
C｜只做機制先不設限（＝現況無限），等 controlled beta 數據再填。

Fable 建議：B 進 controlled beta（讓 synthetic 流量真的撞到限制、驗證降級 UI），public beta 前依數據放寬到 A 量級；edge 層 WAF 1 條 IP 規則（例如每 IP 每分鐘 120 次）Owner 在 dashboard 自己開、零程式碼；app 層第一天只按 cookie owner，不做 IP／指紋。
如果選錯會怎樣：太嚴＝正常人被擋（有降級 UI，不是 500）；太鬆＝Cboe 429 全站連坐、Neon 幾天滿；C＝機制沒被測到。
以後好不好改：全是設定值，隨時改。

### OD-6｜Admin 第一版能看什麼、能做什麼？告警通知到哪？

你其實在決定：Admin secret 被偷的最壞後果（資訊揭露 vs 破壞性操作），以及要不要現在投資稽核；順帶決定通知管道。

A｜只讀彙總：受保護 JSON endpoint（延伸 `/api/ops/metrics`：owners 數、劇本數、refresh 次數、vendor 呼叫／429、DB 大小趨勢、清理量）＋每日 email 摘要；不能點進任何匿名 owner 的內容；不做 HTML 儀表板。
B｜A ＋「查看指定 owner 的劇本」：每次查看留一筆稽核事件、token 等敏感欄位遮罩。
C｜完整管理：可看可刪任何人的資料。
通知管道：(i) email（Sentry 內建＋GitHub workflow 失敗通知＋每日摘要，零新基礎設施）；(ii) Slack incoming webhook（需先開 workspace）；(iii) 兩者。

Fable 建議：A ＋ (i)。B 留到真的有使用者回報問題需要除錯時再加；C 風險級別等同 SCALE-18。
如果選錯會怎樣：C 錯＝一把 secret 洩漏就能刪全站；A 錯＝除錯時看不到內容（可用 B 補）。
以後好不好改：A→B 純加法；通知管道隨時換。

### OD-7｜陌生人第一次進站看到什麼、隱私頁怎麼寫、回報問題往哪去？

你其實在決定：「使用者基本無法理解產品」這條 Release Gate 硬類別要做到什麼程度，以及隱私文件要不要顧到歐盟／英國。

A｜最小：首頁常駐一段 Beta 說明（存在這個瀏覽器的 cookie／清掉就沒了／N 天不用會清／非投資建議／Beta 中）＋H7 頁尾一行＋一頁極簡中文隱私說明（存了什麼、留多久、怎麼刪）＋「回報問題」連到 GitHub issue；空狀態只給一段文字、不自動建示範劇本。
B｜A ＋ 英文版與歐盟／英國措辭（面向全球）。
C｜只做 H7 頁尾一行，其餘不做。

Fable 建議：A。介面本來就只有中文，先面向中文圈；cookie 本身已是 strictly necessary，隱私頁是 good practice 非義務。
如果選錯會怎樣：C 錯＝陌生人不知道資料會消失、會被清；B 錯＝多寫沒人看的英文頁。
以後好不好改：純文案，隨時改。

### OD-8｜Release line 怎麼畫：controlled beta 找誰、public beta 怎麼公開、CI 硬閘要不要接受改習慣？

你其實在決定：兩階段各自的參與者與結束條件，以及 Owner 要不要從此不直接 push master。

A｜Controlled beta＝synthetic 流量（mock vendor）＋ 3–5 位熟人真人 UX validation，觀察 I6 數字兩週、零 sustained incident 且 Neon 成長符合預期才進 public；public beta＝只把連結給人、不主動張貼社群；CI 硬閘：branch protection required checks，Owner 改「開 PR → CI 綠 → 自己按合併」。
B｜同 A 但 public beta 直接公開張貼（社群／論壇）——此時 edge WAF 規則與 OD-5 數字必須先驗證過，並考慮把 CAPTCHA 排進 public 前。
C｜Controlled beta 只跑 synthetic 不找真人；CI 只跑不擋（靠自律）。

Fable 建議：A。「只給連結」讓 public beta 的流量形狀可控，張貼社群等看過一輪真實數字再說；CI 不設硬閘等於今天手動貼回報一樣沒擋住任何事。
如果選錯會怎樣：B 錯＝第一天就被流量洪水打到 429 連坐；C 錯＝真人 UX 問題到 public 才發現、CI 形同虛設。
以後好不好改：A→B 隨時；硬閘可隨時關（但不建議）。

### OD-9｜市場資料源換不換、何時換、每月預算上限多少、CSV 匯出怎麼辦？

你其實在決定：要不要在 Beta 前解掉「今天就在違約」的既有風險，以及願意為合法資料源＋基礎設施每月付多少。Intrinio Silver 月費 UNVERIFIED（全站區間 $250/月起，該方案未必落在此區間）、Databento 需實跑問卷、Cboe DataShop Tier 1 約 $1,499/月（單一二手來源）。Neon 付費層 $0.35/GB-月、Vercel Pro $20/月（目前都不需要；升級觸發值見 #273 §5.5）。

A｜不換：Beta 繼續刮 Cboe／Yahoo，Owner 自承被封 IP＝全站中斷的風險；預算 $0；CSV 照舊。
B｜Public beta 前換：controlled beta 期間平行做——向 Intrinio 索取 Silver Options 報價、跑一次 Databento 自助問卷（鎖定 delayed）、兩家申請試用實打 API 驗證 LEAPS 覆蓋；拿到數字再由 Owner 拍板哪一家；CSV 原始資料下載在 display-only 授權下移除或限縮為畫面顯示；預算上限先給一個數（建議 ≤ US$300/月含資料源，超過回來重議）。
C｜Controlled beta 用現狀、public beta 前必換（＝B，但把「換源完成」正式寫進 public beta gate）。

Fable 建議：C。Controlled beta 以 mock vendor 為主、不放大真實抓取量；公開給陌生人前把違約狀態解掉。
如果選錯會怎樣：A 錯＝某天 Cboe 封 IP，全站每個人同時失去資料源且無備援（yfinance 在雲端結構上不可用）；B 錯＝報價超出預算、上線延後。
以後好不好改：換源工程輕量（一個 adapter＋一行白名單），資料源可再換；CSV 功能移除可回復。

---

## 3. Fable 推薦組合

OD-1 A｜OD-2 A｜OD-3 A｜OD-4 A（30＋7 天）｜OD-5 B→public 前放寬到 A｜OD-6 A＋(i) email｜OD-7 A｜OD-8 A｜OD-9 C（預算 ≤ US$300/月含資料源）。

## 4. 照推薦走時的 Public Beta Release line

**Line 1｜Controlled Beta 前必做**（做完即開合成流量＋熟人）：
1. I2 匿名 cookie（H1）→ 每瀏覽器一個 owner；`SOLO_OWNER` 退場（擋：資料外洩）
2. I9 Admin 專屬 secret＋集中判斷點（H3）；I3 認領 solo 資料（OD-2）（擋：資料外洩）
3. H5 owner 級刪除原語＋`narrow_history` 修＋「立刻刪光」鈕（OD-4）＋synthetic 標記欄位（擋：成本失控／資料外洩）
4. I4 額度三件套：劇本上限／刷新最短間隔／全站每日 vendor 預算 fuse，超過降級沿用舊資料＋既有 429 UI（OD-5 B 數字）（擋：成本失控／不可用）
5. OD-3 A：匿名者隱藏 token／Historical IV（擋：資料外洩）
6. H7 頁尾一行＋OD-7 A 首頁 Beta 說明（擋：看不懂／法規最低告知）
7. I1 CI＋branch protection＋deploy 後 `/api/health` smoke（研究說 controlled 階段可選，但壓測 harness 本身就是程式碼，建議提前）（擋：不可用）
8. Edge WAF 1 條 IP 規則（Owner dashboard 操作，零程式碼）
9. mock-vendor 壓測 harness（既有 DI 注入點）
10. `/security-review` pre-release #1（ASVS L1 骨架）

**Line 2｜Public Beta 前額外必做**（連結給人）：
11. I5 清理 cron 上線（先手動腳本跑幾輪）；`owner_credentials` 清理（OD-3 A 下只剩 Admin 的）
12. I6：Sentry 免費層、每日 email 摘要、兩條告警（Cboe sustained incident／Neon 80%）、DB 成長趨勢每日快照；UptimeRobot 可選
13. OD-7 A 隱私頁＋回報入口
14. OD-9 C 資料源切換完成＋CSV 功能處置
15. 依 controlled 數據放寬額度到 OD-5 A 量級
16. `/security-review` pre-release #2（ASVS L1＋憑證儲存 L2 子集）
17. 公開方式：只給連結（OD-8 A）

**張貼社群前另議**：CAPTCHA／app 層 IP 限流／三階處置（看到 abuse 再做）。
**測試接縫**：沿用既有七個、零新增（比照 spec #217／#237）。

## 5. 明確 defer 到 Beta 後

帳號系統（Email／Google）／跨裝置同步／救命碼（若 OD-1 選 A）；廣告與 CMP；Analytics（若要，Vercel Web Analytics）；Holdings／Cross-Scenario；進階 admin（跨 owner 查看 B、完整管理 C）；CAPTCHA／裝置指紋／app 層 IP 限流／三階處置；即時 HTML 儀表板／PostHog；ASVS Level 2／3 全套；平台搬遷；RD-2；SCALE-18；MarketData.app 條款客服確認（OD-3 A 下不急）；Slack；UptimeRobot（nice-to-have）。

## 6. 是否已足夠進 `/to-spec`

**足夠**——條件是 Owner 回完 9 題（回字母＋改數字即可）。回覆後的收尾動作：把答案逐票貼進 #282～#288 resolution comment 並 close、#289 寫 Release Gate 定稿、#281 close（本輪已自查）、地圖 #272 Destination 標記達成、CONTEXT.md 新增詞條（Anonymous Owner／Browser Identity／Admin Identity／Abandoned Owner／Grace Period／Hard Delete／Quota／Global Fuse／Controlled Beta／Public Beta／Release Gate）→ 才進 `/to-spec`。

三項 UNVERIFIED（Intrinio 月費、Databento 問卷結果、cron 是否每日生效）**不擋 spec**，只擋 OD-9 最終選哪一家 vendor——spec 可寫成「二選一待報價」。
