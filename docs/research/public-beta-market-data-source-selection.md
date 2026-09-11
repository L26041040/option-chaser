# Public Beta 選擇權鏈資料源選型：有沒有一家 vendor 明文允許我們現在的用法

> 本文件回答 issue #290（wayfinder 地圖 #272 子票）：`public-beta-platform-facts.md`
> （#273）已經確認 Cboe 與 Yahoo 的官方條款明文禁止本產品現行的自動抓取
> 方式，且已經有實際執法動作（IP 封鎖威脅）。**這張票的任務不是「更小心地
> 繼續刮 Cboe／Yahoo」（換 User-Agent、放慢速度躲偵測）——那明確排除在
> 範圍外**。任務是找出：**有沒有一家 vendor，官方條款白紙黑字允許「把
> 美股選擇權鏈資料，透過自動化程式，餵給一個公開、多使用者的網站」這件事**，
> 而且成本是這個 Beta 階段產品負擔得起的。**這張票只研究、排優先序，不做
> 最終決定**——決定留給後續的人工票。
>
> 查閱日期：全部 2026-09-11。

---

## 給 Owner 的白話摘要

**有。而且不只一家，最少三個等級的方案都有官方白紙黑字允許。** 但沒有一個
是「免費、什麼都不用簽、今天申請明天就能用」的——這件事的本質是：期權
即時報價的著作權與轉散布權，法律上屬於交易所（OPRA，十幾家交易所共同
成立的官方報價機構）而不是任何一家資料 vendor，任何人想把這種資料公開
展示給陌生訪客看，繞不開跟 OPRA 有關的某種正式授權關係，差別只在於「這個
授權關係是自己直接跟 OPRA 簽」還是「透過一家已經幫你簽好的 vendor 轉包」。

**本輪最重要的發現，直接決定了整個成本結構**：官方 OPRA 費用政策明文只對
**即時**（15 分鐘內）資料收「每個訂閱者每月」的展示費；只要資料**延遲滿
15 分鐘**，OPRA **完全不收**這筆逐訂閱者的費用——而 Option Chaser 現在
本來就已經是延遲報價產品（現行 Cboe 端點就是 15 分鐘延遲），不是即時交易
工具。這代表：只要換到一家「合法登記為 OPRA vendor、且明確授權你把延遲
資料秀給自己的使用者看」的資料源，理論上完全不必因為使用者變多而多付
一毛錢的逐人授權費——真正要付的是那家 vendor 自己的固定月費。

依這個邏輯，本輪排出的**最推薦方案是 Intrinio 的 Silver Options 方案**：
官方頁面白紙黑字寫著「15 分鐘延遲的 OPRA 選擇權報價，企業可以把它顯示給
自己應用程式的使用者看，不另外收費、沒有逐使用者費用、不需要額外的
交易所手續」——這句話幾乎是為 Option Chaser 這種產品量身打的。**唯一
沒查到的數字是它實際月費多少**（官方頁面把價格藏在要填表單才看得到的
「產品頁」後面），且這個方案**限制是只能「顯示」（畫成圖表、算成報表），
不能讓使用者自己下載原始逐筆合約資料**——這點會影響本產品現有的「原始
資料下載（CSV）」這個既有小功能，需要調整或另外處理，不影響核心的候選
分析與熱力圖顯示。**次推薦方案是 Databento**：走真正的官方自助簽約流程
（回答問卷、自動產生合約），且因為它會誠實地把「你到底要不要付即時資料
逐人費」這件事算清楚並且不加價轉嫁，若我們鎖定只要延遲資料，理論上成本
結構會比 Intrinio 更透明、更可能壓得比較低，但需要實際跑一次真實簽約
流程才能拿到精確數字，本輪只查到文件層級的流程說明。

**明確不建議的路**：繼續用現在的 Cboe 免費端點或 Yahoo Finance——兩家
官方條款都白紙黑字寫著禁止自動抓取，Cboe 甚至寫明「違者封鎖 IP」；以及
Alpha Vantage／Polygon 免費層／MarketData.app 現有方案／Finnhub／
Twelve Data 這幾家的**個人／免費方案**——全部都明文寫著「不得用來建立
給別人用的應用程式」，要用在 Option Chaser 上都得先聯絡業務簽一份我們
沒看過內容的客製合約，價格與條款本輪查不到。

---

## 目錄

1. [比較總表](#1-比較總表)
2. [OPRA 的角色：為什麼這件事不是單純比較 vendor](#2-opra-的角色為什麼這件事不是單純比較-vendor)
3. [逐 vendor 詳細條款與引用](#3-逐-vendor-詳細條款與引用)
4. [分類：安全必要 vs 業界慣例 vs 產品選擇](#4-分類安全必要-vs-業界慣例-vs-產品選擇)
5. [工程難度：現有 `providers.py` 抽象撐不撐得住](#5-工程難度現有-providerspy-抽象撐不撐得住)
6. [規模成本推算（100／1,000／10,000 使用者量級）](#6-規模成本推算1001000010000-使用者量級)
7. [最推薦方案／次佳方案／明確不推薦方案](#7-最推薦方案次佳方案明確不推薦方案)
8. [誠實揭露：本輪沒查到／查不到的事](#8-誠實揭露本輪沒查到查不到的事)

---

## 1. 比較總表

> 「公開多使用者 App 是否允許」是本輪查證重點欄位，逐字引用見第 3 節。
> `UNVERIFIED` 表示官方頁面本輪查不到明確答案或查到互相矛盾的二手轉述。

| Vendor | 公開多使用者 App 是否允許（官方原話方向） | 免費層 | 低價付費層 | 延遲/即時 | 選擇權鏈完整度（含 LEAPS） | bid/ask/last/vol/OI | IV/Greeks | Public Beta 起步成本 | 100/1k/10k 使用者成本走向 | 工程難度（接進現有 adapter 抽象） |
|---|---|---|---|---|---|---|---|---|---|---|
| **現行：Cboe 刮取端點**（`cdn.cboe.com` 免文件端點） | ❌ **明文禁止＋威脅封 IP**（見 `public-beta-platform-facts.md` 已確認逐字引用） | 免費（但違規） | — | 15 分延遲（未經授權） | 全鏈含 LEAPS | 有 | 有（vendor 給的 IV，本產品不用） | $0（但隨時可能被封鎖全站） | 使用者越多，被偵測到、觸發全站封鎖的機率越高，不是錢的問題 | 已整合 |
| **現行：Yahoo Finance**（股利資料，非選擇權鏈本身） | ❌ **明文禁止自動化擷取＋禁止「建立競品資料源」** | 免費（但違規） | — | — | 不適用（非鏈資料） | — | — | $0（同上風險） | 同上 | 已整合 |
| **Cboe DataShop／LiveVol All Access API**（官方授權產品，同一家交易所） | ✅ **官方「redistribution license」明文涵蓋「client-facing applications, websites」** | 500 points/day（`UNVERIFIED` 是否含轉散布權） | Tier 1 基本 $599/月 | 官方文件宣稱同時提供即時／延遲／歷史 | 全鏈（官方一手來源，應含 LEAPS，`UNVERIFIED` 逐項覆蓋） | 有 | 有 | **Tier 1 含轉散布授權 $1,499/月**（`UNVERIFIED` 二手轉述，見 §3.6） | 各 Tier 以「points/月」計量，超額另計，UNVERIFIED 精確換算 | 低——REST＋API key，同一家交易所欄位語意最接近現行 adapter |
| **Databento（OPRA.PILLAR）** | 🟡 **看資料新鮮度而定**：即時資料的轉散布需另外取得 OPRA vendor 授權（Databento 代辦、不加價轉嫁）；官方部落格證實「若使用者已有 market 的轉散布授權，Databento 不額外限制轉散布」 | 無獨立免費層（歷史資料另計量計費） | **Standard $199/月**（含即時＋10 年歷史，但這是「你自己用」的授權，轉散布資格需另外經 OPRA 問卷審核） | 即時＋延遲＋歷史皆有 | 全 18 家交易所 OPRA 官方資料，理論上完整含 LEAPS | 有（原始逐筆） | 官方不主動算 Greeks／IV（本產品原本就自己算） | **$199/月起，另加 OPRA vendor 資格審核**（若鎖定延遲資料，OPRA 官方政策對延遲資料不收逐訂閱者費，實際加價未知，`UNVERIFIED`） | 自助問卷流程理論上可隨用量調整方案，具體門檻 UNVERIFIED | 低——自助簽約產生「合約」，REST API，與現有 adapter 形狀相容 |
| **Intrinio（Silver Options）** | ✅ **官方原話：「企業可將 Silver Options 授權用於顯示，不另外收費、無逐使用者費用、無交易所額外要求」，明文涵蓋「顯示給企業的終端使用者」** | 無獨立免費層（有兩週試用） | **確切月費 `UNVERIFIED`**（官方把價格藏在需要留資料的「Options Product Page」後面，一般範圍報導為 Intrinio 全站方案落在約 $250/月至數千/年） | 15 分鐘延遲（Silver＝延遲層，Gold 才是即時） | `UNVERIFIED`（官方僅稱「options contract prices」，未逐項確認 LEAPS／全履約價覆蓋） | 有 | `UNVERIFIED`（官方頁面未列出是否含 IV／Greeks） | **官方明文月費不對外公開，需留資料索取報價** | `UNVERIFIED`，但因是「顯示授權」非逐使用者計費，理論上使用者數增加不直接推高成本 | 中——**Business Use-Display 授權明文禁止「透過 API 之類方式做原始資料的散裝下載或轉散布」**，本產品既有 CSV 原始資料下載功能需要調整或走更高階（未知價格的）授權層才相容 |
| **EODHD（US Options，B2B 方案）** | ✅ **需要商業授權，官方文件明文「建立產品、顯示資料給終端使用者、或在商業應用中使用資料，就需要商業授權，商業授權含所需的交易所轉散布權」** | 個人層（`Non-Professional`）明文禁止轉售/轉散布/展示給他人 | B2B 方案起價 **$399/月**（依二手轉述，官方確切 SKU 名稱與涵蓋範圍 `UNVERIFIED`） | **只有 EOD（每日一次）**，非即時、非盤中延遲快照 | 6,600+ 檔美股、42+ 欄位（含五個 Greeks／IV／bid-ask/size/volume/OI），回溯僅至 2023 Q4 | 有 | **有，官方直接提供五個 Greeks 與 IV**（比其餘 vendor 更完整） | **$399/月起（B2B，`UNVERIFIED` 確切門檻）** | `UNVERIFIED`，B2B 合約通常依用量另議 | 低——REST＋API key；**但資料只到每日收盤、不是盤中快照**，與現行「每次刷新抓一次當下鏈」的產品模型不同，需評估「一天只更新一次」對 Refresh Run 語意的影響 |
| **ORATS** | 🟡 **預設個人使用、明文「資料不得轉散布」，但官方指出「若打算做應用程式或資料 API，主動聯絡他們，會協商需要做什麼」——不是預設禁止，是預設要客製協商** | 無 | Delayed API $199/月、Live API $299/月（個人使用授權，未含轉散布） | 兩層皆有，另有 <10 秒延遲的 Live Intraday | `UNVERIFIED`（官方以「選擇權分析與 Greeks」為賣點，逐項欄位覆蓋度未核實） | 有 | **有，官方主打逐日計算的 Greeks／IV，是這幾家中對 Greeks 最看重的** | **官方定價僅涵蓋個人用途；轉散布走客製報價，`UNVERIFIED`** | `UNVERIFIED`，客製報價 | 中——需先完成「live data agreement」簽署流程，另外**轉散布 OPRA 資料本身仍需與 OPRA 直接簽約**（ORATS 官方原話） |
| **Polygon.io（Massive）** | ❌（免費／Starter／個人方案）**官方原話極其明確：「不得使用市場資料建立供你以外的終端使用者使用的應用程式」**；商業轉散布需獨立走 "Business" 合約（本輪未查到公開報價） | Options Basic 免費層 EOD-only、5 req/min | Starter $29/月、Developer $99/月、Advanced $199/月、All-Access $399/月——**全數屬「個人非商業」授權，皆不得用於本產品情境** | Starter 起提供 15 分鐘延遲快照 | 官方稱有全鏈 snapshot 端點 | 有 | 官方即時快照含 Greeks（`UNVERIFIED` 各層覆蓋差異） | 上列付費層對 Option Chaser 這種用途在條款上一律不合格；合格的 Business 方案報價 `UNVERIFIED` | 不適用（未取得合格授權前無法評估） | 低（同一套 API，形狀單純），但**授權門檻本身是不合格的**，工程難度不是問題所在 |
| **Alpha Vantage** | ❌（免費層）**官方原話「你打算把透過本平台取得的資訊，用在任何形式的商業活動，讓 User 以外的個人或實體可以直接或間接取得該資訊」即落入禁止的商業使用，需另外聯絡 `premium@alphavantage.co`** | `HISTORICAL_OPTIONS` 25 req/day（僅 EOD） | 商業使用價格未公開，須聯絡業務 | 免費層僅 EOD | 指定日期全鏈 | 有 | 官方附 Greeks | 條款上不合格，須客製報價 `UNVERIFIED` | 不適用 | 低，但授權不合格 |
| **MarketData.app**（本產品現有整合） | ❌（現有一般方案）**官方原話：「未取得補充商業使用附加條款前，不得販售、轉售、轉發或以任何方式讓我方資料或第三方資料供他人取得」「不得以資料 feed、API 或匯出檔的形式對外散布資料」**——另有一份「新聞／教育用途」豁免條款，官方明講該條款**不涵蓋**「供第三方消費的軟體、平台或程式庫」 | 無真正免費層（cached mode 免費層不可用） | Starter US$12–30/月起（依方案，個人使用授權） | 依方案 | 官方稱可整鏈查詢 | 有 | 有 | 條款上不合格，需信箱洽談商業授權，價格 `UNVERIFIED` | 不適用 | 極低——**本產品今天已經有完整的 `fetch_chain`／驗證整合**（`option_chaser/data/marketdata.py`），若拿到商業授權，切換成本幾乎是零（只是把它設成預設來源而非自訂來源） |
| **Twelve Data** | `UNVERIFIED`——官方文件確認有「Venture／Enterprise（商業）」方案存在且是使用公開資料（如 ASX）就需要轉散布授權的先例，但**本輪查無證據顯示 Twelve Data 的公開文件裡有一個完整的美股選擇權鏈端點**（其官方 API 文件搜尋結果只泛稱「option chain API」，未見具體 endpoint／欄位規格） | Basic 免費層（額度極小） | Grow $29/月起（個人） | `UNVERIFIED` | `UNVERIFIED`——**未確認是否真的涵蓋美股選擇權**，本輪最大的資料缺口之一 | `UNVERIFIED` | `UNVERIFIED` | 不建議在確認產品是否真的有完整美股選擇權鏈之前列入考慮 | — | — |
| **Finnhub** | ❌ **二手轉述：「免費金鑰的非商業授權——你的 app 一旦開始營利或轉散布資料，就需要付費方案」**，商業授權建議直接聯絡 `sales@finnhub.io` | 60 req/min，個人非商業 | 商業授權價格未公開 | `UNVERIFIED` | 既有研究（`option-chain-data-sources.md`）已記錄過對 `/stock/option-chain` 有多起品質問題的公開 issue | `UNVERIFIED`，已知品質疑慮 | `UNVERIFIED` | 條款不合格＋既有品質疑慮，本輪判斷優先度低、未深入 | — | — |
| **dxFeed（Retail Services Platform）** | ✅ **官方產品定位本身就是「B2B2C：讓合作夥伴把市場資料訂閱直接整合進自己的產品」**——理論上是本輪唯一一家把「你想做的正是我們的產品」寫進行銷文案的 vendor | 無 | `UNVERIFIED`（二手資料顯示 dxFeed 一般訂閱年費約落在中低四位數美元量級，但那是零售單一資料 feed 報價，非 Retail Services Platform 這個 B2B2C 產品線本身的報價） | `UNVERIFIED` | `UNVERIFIED` | `UNVERIFIED` | `UNVERIFIED` | **`UNVERIFIED`，需求接洽業務，本輪查無公開自助報價**，型態上聽起來偏向中大型合作規模，未必貼合 Beta 階段量級 | — | 中——需另外接入 dxFeed 專屬的帳號管理／訂閱 API，不是單純換一個 `fetch_chain` 端點那麼簡單 |
| **Charles Schwab Trader API**（Broker-based redistributor） | 🟡 **個人開發者用自己帳戶存取免費；官方文件明講「商業使用、市場資料轉散布、大型整合，需要 Schwab 審核與交易所資料協議」**——非預設允許，需要走 Schwab 內部審核流程，且過程與結果本輪查不到公開先例 | 個人帳戶免費（需開立並維持 Schwab 帳戶） | 商業／轉散布報價未公開，須走審核 | `UNVERIFIED` | 官方分「Market Data Production」，涵蓋報價／歷史價格等 | `UNVERIFIED`，官方文件未逐項列出選擇權鏈欄位 | `UNVERIFIED` | 需先走商業審核，本輪判斷流程與時程皆不可控，優先度較低 | — | 中——OAuth 2.0 流程與現有 Bearer-token adapter 形狀不同，需要額外的授權碼交換與 token 更新機制 |

---

## 2. OPRA 的角色：為什麼這件事不是單純比較 vendor

在讀逐一 vendor 的條款之前，先講清楚一個貫穿全部候選、決定成本結構的
共同背景：**美股選擇權的即時／延遲報價，著作權與轉散布權屬於
Options Price Reporting Authority, LLC（OPRA）**——十幾家美股選擇權
交易所共同成立的官方報價機構，不是任何一家資料 vendor 自己擁有的資料。
不管你透過 Cboe、Databento、Intrinio 還是 Polygon 拿到這份資料，
你事實上都是在消費「OPRA Data」，只是透過不同的中間商（vendor）取得。

這件事對本輪研究有兩個直接影響：

1. **任何 vendor 若允許你把資料轉散布給自己的終端使用者，這件事本身
   最終都要回溯到 OPRA 的授權架構**——vendor 自己的條款只是第一層，
   vendor 條款允許之後，通常還隱含一份與 OPRA 相關的「Subscriber
   Agreement」或「Vendor Agreement」（見 §3.2 Polygon 附件的 OPRA
   Non-Professional Subscriber Agreement 完整逐字條文，是本輪唯一
   一份完整讀到全文的 OPRA 附屬合約）。
2. **OPRA 官方費用政策本身，對「即時」與「延遲 15 分鐘以上」資料的
   收費邏輯完全不同**（二手轉述，來源見 §3.9，本輪未直接讀取 OPRA
   官方 PDF 費用表逐字原文，列為 UNVERIFIED 但多方來源一致）：
   - **即時資料**：vendor 通常要依「Non-Professional Subscriber」
     人數，逐月付給 OPRA 一筆「每人每月」的費用（2018 年生效的費率
     表二手轉述約 $0.60–$1.25／人／月，隨累計人數遞減，**本輪查到
     的是 2018 年生效版本，2026 年是否調整過未查證**）；另外可能有
     一筆與人數無關的「redistributor」固定月費（二手來源估計約
     $1,500/月量級，**這個數字本輪只從單一二手來源（MarketData.app
     自己的教育部落格）取得，未在 OPRA 官方 PDF 原文中逐字核對，
     列為 UNVERIFIED、且該來源本身有推銷自家產品的動機，需要謹慎
     看待**）。
   - **延遲 15 分鐘以上的資料**：多方二手來源一致認為 **OPRA 不收
     這筆逐訂閱者的展示費**——這正是 Intrinio Silver Options 官方
     頁面能夠寫出「no additional charge, no per-user fees, no
     exchange requirements」的制度性原因。
   - **歷史資料**（滿一個完整交易日以上）：多方來源皆稱完全免 OPRA
     授權費用。

**這代表什麼**：Option Chaser 現有的產品定位——延遲報價、非即時交易
工具——如果换到一家「已經幫你把 OPRA vendor 資格辦好」的合法資料源，
理論上不必因為使用者變多而付出隨人數增加的授權費，真正要付的只是
vendor 自己的固定月費（依方案而非依人數）。這正是本輪把 Intrinio
Silver Options 排在最推薦的核心理由。

---

## 3. 逐 vendor 詳細條款與引用

### 3.1 Cboe 現行刮取端點——不建議繼續使用（複查既有結論，未重新引用全文）

`public-beta-platform-facts.md`（本輪 issue #273）已於 2026-09-11
直接抓取 <https://www.cboe.com/delayed_quotes/API/quote_table/> 原始
HTML，逐字確認：

> "IT IS STRICTLY PROHIBITED TO DOWNLOAD DELAYED QUOTE TABLE DATA FROM
> THIS WEB SITE BY USING AUTO-EXTRACTION PROGRAMS/QUERIES AND/OR
> SOFTWARE. CBOE WILL BLOCK IP ADDRESSES OF ALL PARTIES WHO ATTEMPT
> TO DO SO."

本輪未重複抓取（同一份查證今天稍早已完成、逐字存在），直接引用其結論。
Yahoo Finance 條款（`legal.yahoo.com`）同一份文件也已逐字引用禁止自動化
擷取與「建立競品資料源」的條款，本輪同樣不重複引用。

### 3.2 Polygon.io（Massive）——免費／個人方案明文禁止本產品用法

直接抓取官方 PDF <https://massive.com/terms/market_data_terms.pdf>
（"POLYGON.IO, INC. MARKET DATA TERMS OF SERVICE", Last Updated:
October 9, 2024，2026-09-11 查閱，完整全文，非摘要）：

> "Polygon hereby grants you a nonexclusive, nontransferable,
> non-sublicensable, revocable, limited license to use Market Data
> exclusively for your personal, non-business, and non-commercial
> purposes. For the avoidance of doubt, you may not use the Market
> Data for any business or commercial purpose, and **you may not use
> the Market Data to build an application intended for use by end
> users other than you**."

這是本輪所有 vendor 裡措辭最直接、最沒有模糊空間的一句禁止語言——
逐字點名「不得拿這份資料建立供你以外的終端使用者使用的應用程式」，
Option Chaser 這個 Public Beta 產品正是這句話描述的行為。文件同時附上
完整的 **OPRA Non-Professional Subscriber Agreement**（Schedule 1）與
**NYSE Market Data Agreement**（Schedule 2）逐字全文，兩份都重申「僅供
個人非商業使用、不得轉發給任何其他人或實體」。文件本身未提及付費的
"Business" 轉散布方案報價，僅暗示存在（"Business contracts for
redistribution and exchange-licensed data" 語出二手轉述的公司簡介，
非官方條款原文，故該報價本身列為 `UNVERIFIED`）。

### 3.3 Alpha Vantage——免費層明文排除本產品用法

直接抓取官方 ToS PDF <https://www.alphavantage.co/terms_of_service/>
（該頁面本身直接回傳 PDF 而非 HTML，2026-09-11 查閱，完整全文）：

> "Usage falls under 'commercial use' if any of the following criteria
> apply to you: ... You plan to use or provide information accessed
> through the Alpha Vantage Platform **as part of any type of
> commercial activity that allows individuals or entities other than
> User to access information directly or indirectly** even if the
> scope of such activity falls outside of the securities industry."
>
> "If you are interested in using the Alpha Vantage Platform for
> commercial purposes, please contact us at: premium@alphavantage.co"

同樣明確排除「讓 User 以外的人取得資訊」這種用法，且沒有公開列出商業
授權的價格或條款，必須寄信洽談——本輪無法進一步查證條款內容或價格。

### 3.4 MarketData.app——現有整合，商業使用需另簽附加條款

<https://www.marketdata.app/terms/>（2026-09-11 WebFetch 直接讀取）：

> "You may not sell, resell, retransmit, or **redistribute or make our
> data or any third-party data available to anyone** without a
> supplemental commercial use addendum to this agreement."
>
> "You may not **distribute the data programmatically as a data feed,
> an API, or an export file**."

這與本輪先前批次研究（`public-beta-platform-facts.md` §4.5）的既有
發現一致，本輪額外查到一份專屬的「新聞／教育用途」豁免條款頁
（<https://www.marketdata.app/terms/public-use/>，2026-09-11
WebFetch）：

> 允許「incorporate insubstantial excerpts of Historical Data into
> Permitted Work solely to illustrate analysis or commentary」，
> 上限「no more than one hundred fifty individual data points... per
> Permitted Work」，且明文排除「incorporation of Historical Data into
> software, platforms, or repositories intended for third-party
> consumption」——**這條路本身就聲明不適用於任何供第三方使用的軟體／
> 平台**，不是本產品可以援引的豁免。因此 MarketData.app 現有整合若要
> 用於 Public Beta，仍然需要走「supplemental commercial use
> addendum」這條路，價格與具體條款本輪查不到、需要信箱洽談。

### 3.5 ORATS——預設個人使用，轉散布走客製協商而非制式方案

<https://orats.com/data-api>／WebSearch 摘要（2026-09-11 查閱，未能
完整讀取官方 ToS 原文全文，本節引用皆為搜尋引擎轉述二手資訊，列為
`UNVERIFIED` 但多次獨立搜尋結果一致）：

> 「Data is not to be used for redistribution. However, if you intend
> on making an application or data API and are using this data, you
> should let them know and they can work out what you need to do.」

> 「If you want to redistribute OPRA data through an API, mobile app,
> trading dashboard, or browser plugin, this requires a direct
> agreement between your company and OPRA.」

與 Polygon／Alpha Vantage 那種「條款白紙黑字禁止」不同，ORATS 的立場
更接近「預設不行，但主動找我們談，可能有路」——這是一種需要人工協商、
結果不可預測的路徑，且即使 ORATS 本身同意，轉散布 OPRA 資料本身仍
需要另外直接跟 OPRA 簽約（見第 2 節的制度性背景），不是 ORATS 一家
說了算。定價方面，ORATS 公開列出的方案（Delayed API $199/月、Live
API $299/月，見 §1 比較表）明確只涵蓋個人使用，未涵蓋轉散布。

### 3.6 Cboe DataShop／LiveVol All Access API——同一家交易所的官方授權版本

搜尋引擎轉述（<https://datashopcert.livevol.com/all-access-apis-pricing>
本輪 WebFetch 直接讀取遭 403 拒絕，本節數字為 WebSearch 摘要索引結果，
**列為 `UNVERIFIED`，強烈建議在正式決策前直接以真實瀏覽器登入確認**）：

> 「A monthly base price with the All Access API redistribution
> license applies if you intend to redistribute the data to any
> external individual or parties. The redistribution license allows
> for retransmission of real-time, delayed, and historical non-SIP
> data into client facing applications, websites, and/or data
> feeds.」

轉述的分層報價（`UNVERIFIED`）：

| Tier | 額度 | 基本價（不含轉散布） | 含轉散布授權 |
|---|---|---|---|
| Free | 500 points/day | $0 | `UNVERIFIED` 是否可轉散布 |
| Tier 1 | 150,000 points/月 | $599/月 | $1,499/月 |
| Tier 2 | 250,000 points/月 | $799/月 | $1,999/月 |
| Tier 3 | 1,250,000 points/月 | $2,499/月 | $3,699/月 |
| Tier 4 | 4,000,000 points/月 | $4,599/月 | $5,999/月 |

**「Redistribution rights for SIP data must be obtained directly from
the appropriate SIP data provider」**——這句話（同一份二手轉述）暗示
非 SIP（即 Cboe 自家撮合的選擇權，本產品主要標的多數屬此類）走這個
授權即可，但若牽涉到跨交易所 SIP 彙總報價，可能還要另外處理，本輪
未進一步查證這條界線對本產品實際標的清單的影響。**這是本輪唯一一家
「跟現行資料源同一個交易所、明確把『client-facing applications』
寫進官方轉散布授權說明」的候選**——概念上最乾淨（不必換資料語意、
欄位定義與現行 `cboe.py` adapter 幾乎一致），但價格是本輪查到最貴
的合法路徑之一（$1,499/月起）。

### 3.7 Databento（OPRA.PILLAR）——自助簽約流程，成本結構最透明

<https://databento.com/blog/introducing-new-opra-pricing-plans>／
<https://databento.com/blog/subscriber-status>（WebSearch 摘要，
2026-09-11 查閱，`databento.com/legal` 本輪 WebFetch 讀取失敗、僅取得
導覽頁殘缺內容，未能引用完整 ToS 原文，列為部分 `UNVERIFIED`）：

> 「Databento US Equities Mini supports commercial applications—such
> as external redistribution and non-display trading—without
> licensing restrictions.」（**這句話講的是股票 Mini 產品，非選擇權
> OPRA 資料，兩者授權規則不同，不可直接套用**）

> 「For live data (24 hours or newer), markets generally require a
> redistribution license, and Databento facilitates the process for
> users to obtain the redistribution license from the market operator
> and pass through those fees. If a user has a redistribution license
> from the market, Databento doesn't impose any limitations on them
> redistributing the data.」

> 「After users answer a short questionnaire, Databento determines
> their subscriber status and auto-generates contracts to meet venue
> licensing requirements.」

這代表 Databento 本身**不是**那個會禁止你轉散布的角色——它扮演「幫你
辦好與 OPRA／交易所之間手續」的中間人，真正的授權關卡（與費用）來自
OPRA／交易所本身，而不是 Databento 額外加碼。**若鎖定只用延遲 15 分鐘
以上的資料**（依第 2 節的制度背景，OPRA 對這類資料不收逐訂閱者費），
理論上走 Databento 自助流程的邊際轉散布成本會非常低，但**本輪沒有
真的跑過這個問卷流程，無法確認「延遲資料」這個選項在 Databento 的
自助問卷裡是否真的存在、以及审核通過後具體月費多少**——Standard 方案
$199/月官方寫明是「即時＋10 年歷史」的整體訂閱費，這是「你自己用」
的授權費，不必然涵蓋「轉散布給你的終端使用者看」這件事本身的額外
授權，需要實際走一次流程才能確認總成本。

### 3.8 Intrinio（Silver Options）——本輪找到措辭最直接對應本產品需求的方案

<https://intrinio.com/guides/options-silver>（WebFetch 直接讀取，
2026-09-11 查閱，完整頁面文字）：

> 「15-min delayed options contract prices from OPRA. **Businesses may
> license Silver Options for display at no additional charge with no
> per-user fees or exchange requirements.**」

> 「The data included in the plan may be displayed to **business' end
> users** in an application, report, or analysis」（Business
> Use-Display 授權條款）

> 「**Bulk downloads or raw distribution of the underlying data
> through methods such as an API are not allowed.**」

三句合起來的意思：**這個授權明確允許把資料「畫成圖表／算成分析結果」
顯示給企業自己的終端使用者，且不會因為使用者變多而逐人收費，也不需要
額外跟交易所打交道**——這正是 Option Chaser 現在的用法（引擎算完
candidate／heatmap／greeks 之後才顯示，使用者看不到未加工的逐筆報價）。
**但明文排除「讓使用者透過類似 API 的方式下載散裝原始資料」**——本產品
既有的 V8／#56「原始資料（當次快照）」CSV 下載功能（`GET
/api/scenarios/{id}/raw-data.csv`）如果照現行設計原封不動保留，很可能
落在這條禁止範圍內，需要移除該功能、改成「顯示不可下載」，或另外
洽談涵蓋範圍更廣（且價格更高）的授權層——這是採用此方案時需要處理的
產品面調整，非本文件範圍內解決，留給後續施工票裁示。

**價格是本輪最大的查證缺口**：官方頁面把實際月費藏在需要留資料的
「Options Product Page」表單後面，本輪多次嘗試搜尋具體數字未果，只
查到 Intrinio 全站方案的概略區間（$250/月至約 $200/月等值的年繳方案）
供參考，**不能確定 Silver Options 這個特定方案的價格落在這個區間內**，
列為 `UNVERIFIED`，需要 Owner 或後續施工者實際填表索取報價。

### 3.9 EODHD——選擇權資料完整但只有 EOD 頻率

<https://eodhd.com/financial-apis/commercial-vs-personal-license-use>
（WebSearch 摘要，2026-09-11 查閱）：

> 「Non-Professional Users are prohibited from selling, reselling,
> retransmitting, redistributing, displaying, or granting access to
> the Information or Services... If you're building a product,
> displaying data to end users, or using data within a business
> application, you need a commercial license, which includes all
> necessary exchange redistribution rights.」

EODHD 的美股選擇權資料本身欄位完整度是本輪查到最高的（42+ 欄位，含
完整五個 Greeks、bid/ask 含 size、volume、OI），且官方 B2B 商業方案
文字明講「含所需的交易所轉散布權」——制度上是合格的。**但這份資料是
End-of-Day（每日收盤後更新一次），不是盤中即時或近即時快照**——與
Option Chaser 現行「每次刷新即時抓一次當下的鏈」這個核心產品行為
（Refresh Run／Continuation 機制）語意不同，若採用需要接受「一天只有
一份新資料」這件事，可能影響到「盤中刷新看到不同數字」這個既有使用者
預期，屬於需要 Owner 裁示是否可接受的產品面取捨，非純技術問題。

### 3.10 dxFeed（Retail Services Platform）——產品定位最貼合，價格最不透明

<https://kb.dxfeed.com/en/dxfeed-retail-products/retail-services-platform.html>
（WebSearch 摘要，2026-09-11 查閱）：

> 「The dxFeed Retail Services Platform is a B2B2C solution that keeps
> an end-user within a partner's ecosystem without additional sign-up
> on the dxFeed portal and makes it possible for partners to create
> user accounts, grant access to market data, and manage subscriptions
> via developed API methods.」

這是本輪唯一一家把「幫你的終端使用者管理市場資料訂閱」寫成整個產品
主軸的 vendor——概念上完全對應 Option Chaser 想做的事。**但本輪完全
查不到這個特定產品線的自助報價**，二手資料顯示的價格（Vendr 平均約
$4,200／年）來自的是零售單一資料 feed 訂閱（如 CME Market Depth），
不是 Retail Services Platform 這個 B2B2C 整合方案本身，兩者定價邏輯
可能完全不同（後者聽起來更像是要走業務洽談、依合作規模報價）。列為
`UNVERIFIED`，且從產品调性判斷，這個方案可能是為已有一定使用者規模、
願意簽長期合作合約的公司設計，不確定貼不貼合一個還在 Beta 驗證階段、
使用者量未知的專案。

### 3.11 Twelve Data／Finnhub／Schwab——本輪判斷優先度較低的候選

- **Twelve Data**：本輪查不到證據顯示它有一個文件完整的美股選擇權鏈
  端點（搜尋結果只泛稱「option chain API」而未見具體 schema），在確認
  這個基本能力存在之前，條款與定價的查證意義不大，本輪未深入。
- **Finnhub**：既有研究（`option-chain-data-sources.md` §3.7，
  2026-08-02）已記錄過 `/stock/option-chain` 端點本身有多起公開品質
  問題（GitHub issue，官方 repo 與 finnhub-python repo 皆有），本輪
  二手轉述確認免費層是「非商業」授權、一旦營利或轉散布需要付費方案，
  但鑑於既有品質疑慮尚未解除，本輪判斷優先度低、未進一步深入 ToS。
- **Charles Schwab Trader API**：作為「透過真實券商帳戶取得資料、
  再自己轉散布」這條路的代表性樣本，查證結果是「個人開發者免費，但
  商業使用與資料轉散布需要 Schwab 審核與交易所資料協議」——這是一個
  需要人工審核、時程與結果都不可控的路徑，且要求維持一個真實 Schwab
  券商帳戶（可能涉及帳戶維護要求），與 Option Chaser 現行「adapter
  只需要一把 API token」的架構假設不同，本輪判斷不是這個階段的
  優先候選，僅記錄供未來若需要「broker-based 選項」時參考起點。

---

## 4. 分類：安全必要 vs 業界慣例 vs 產品選擇

**【安全／法規必要】**（vendor 條款白紙黑字要求的事，不是本產品能自行
決定要不要遵守）：

- 繼續使用現行 Cboe 免文件端點與 Yahoo Finance 抓取方式，在條款上已經
  是違規狀態——這件事**不因為換不換 vendor 而改變**，是本文件存在的
  前提，必須另外處理（換源，或 Owner 自行承擔風險維持現狀，見既有
  `public-beta-platform-facts.md` 的裁示）。
- 任何選定的替代 vendor，若要把資料顯示給多個匿名終端使用者看（而非
  只給自己看），一律需要走該 vendor 明文要求的「商業使用」或「轉散布」
  授權路徑，沒有一家的免費／個人層允許本產品現行的用法（見比較表逐一
  的 ❌／🟡 標記）。
- 若最終選擇的 vendor 涉及真正的即時（<15 分鐘）OPRA 資料轉散布，
  依制度背景（第 2 節）**必然**牽涉到某種與 OPRA 相關的逐訂閱者費用
  或固定轉散布費，這不是任何一家 vendor 自己能豁免的規則，是 OPRA
  這個機構本身的收費政策。

**【業界成熟慣例】**（多家 vendor 共通、可預期、非本產品獨有的模式）：

- 「免費／個人層」與「商業／轉散布層」分成兩套完全不同的授權文字，
  幾乎是選擇權資料這個產業的標準結構（Polygon／Alpha Vantage／
  MarketData.app／EODHD／Twelve Data 皆同一套邏輯），不是某一家
  vendor 特別嚴格。
- 「延遲 15 分鐘以上的資料，OPRA 不收逐訂閱者展示費」這件事本身
  也是業界共同的制度背景，不是任一家 vendor 的優惠——任何 vendor
  只要老實遵守 OPRA 規則，理論上都能對「只轉散布延遲資料」的客戶
  提供類似 Intrinio Silver Options 那種「no per-user fee」的條件，
  只是不是每家都把這個選項做成清楚標示、可自助購買的方案。
- 精確定價普遍要「留資料索取報價」而非公開列在網頁上，是這個產業
  在「商業／轉散布」這個層級的共同做法（Intrinio／EODHD B2B／
  dxFeed／ORATS 轉散布皆如此），不是刻意對本產品不透明。

**【Option Chaser 產品選擇】**（本產品既有裁示或需要 Owner 判斷的
取捨，非 vendor 條款強制）：

- 現行產品定位「延遲報價、非即時交易工具」這個既有事實（V1 起就是
  15 分鐘延遲 Cboe 資料），恰好讓本產品能夠合法落在「OPRA 對延遲資料
  免收逐訂閱者費」這個制度優惠帶內——**這不是這輪研究才決定的事**，
  是既有產品定位的自然結果，選源時應該主動善用這個既有優勢（鎖定
  vendor 的「delayed」方案而非「real-time」方案），而不是為了追求
  更即時的資料而放棄這個成本優勢。
- 若採用 Intrinio Silver Options 這類「Display-only、禁止散裝下載」
  的授權，本產品既有的「原始資料（當次快照）CSV 下載」功能（V8／#56）
  是否要移除、限縮，或另外爭取更高授權層——這是純粹的產品取捨，
  需要 Owner 裁示，本文件不代為決定。
- 若採用 EODHD 這類「只有 EOD 頻率」的資料源，是否接受「一天只更新
  一次」這件事改變既有 Refresh Run／盤中刷新的使用者體感——同樣是
  需要 Owner 裁示的產品取捨，非技術問題。
- 「先付費升級到合法資料源」與「先接受現有 Cboe／Yahoo 違規風險、
  等被真的封鎖再處理」兩條路本身是一個風險承受度的商業判斷，
  `public-beta-platform-facts.md` 已經明講「本文件不建議任何特定
  做法」，這條原則本輪延續不變。

---

## 5. 工程難度：現有 `providers.py` 抽象撐不撐得住

讀過 `api_app/providers.py`、`option_chaser/data/cboe.py`、
`option_chaser/data/marketdata.py`、`option_chaser/data/yf.py` 全文後
的結論：**現有抽象對本輪絕大多數候選都撐得住，不需要改介面形狀**。

- **白名單機制**（`SUPPORTED_PROVIDERS: tuple[Provider, ...]`）本身就是
  為了「多一家就多一列」設計的（`providers.py` 檔頭註解原話：「多一家
  就在這裡多一列，UI 與驗證都不必改」）。新增 Databento、Intrinio、
  Cboe DataShop、EODHD 這類單純「Bearer token／API key ＋ REST JSON」
  的 vendor，只需要：(1) 在 `option_chaser/data/` 新增一個同名模組，
  仿照 `marketdata.py` 已經示範過的完整模式（`fetch_chain(symbol,
  token)`、`verify(token)`、統一的 `_num()`／`_clean_float()` 缺值口徑、
  收斂成 `FetchError`）；(2) 在 `providers.py` 的 `SUPPORTED_PROVIDERS`
  加一個 `Provider(id=..., label=...)`；(3) 在 `default_verify()`／
  `default_fetch_chain()` 各加一個 `if provider_id == ...` 分支。這正是
  `marketdata.py` 當初（#125）從零整合進來時走過的路徑，模式已驗證過
  一次。
- **既有的欄位對映慣例也通用**：`cboe.py`／`marketdata.py` 兩個既有
  adapter 都刻意**不映射 vendor 提供的 Greeks／delta／gamma／theta／
  vega**（即使原始 payload 可能有），因為本產品的估值引擎（`calibrate_
  leg()`／`implied_vol()`，BS93 逐腿自行反解校準）本來就不信任 vendor
  算的 IV／Greeks，只消費 bid/ask/last/volume/open_interest 這幾個
  最基本的報價欄位。這代表**選 vendor 時「有沒有原生 Greeks」不是
  決定性因素**——本輪查到 EODHD／ORATS 這兩家格外強調自己的 Greeks
  計算，但那份能力本產品其實用不太到；真正該看的是 bid/ask/OI/volume
  這幾個基本欄位夠不夠完整、準不準（此四項全部候選皆宣稱具備，見
  比較表）。
- **唯一形狀不同的候選是 Charles Schwab（OAuth 2.0 授權碼流程）**——
  現有 adapter 全部是靜態 token（`Authorization: Bearer {token}`）
  一次性帶入即可，OAuth 需要授權碼交換與定期換發 access token 的
  額外狀態管理，`providers.py` 目前的 `verify(token)`／`fetch_chain
  (symbol, token)` 簽章假設 token 是長效、可重複使用的單一字串，
  若真的要接 Schwab，`option_chaser/data/schwab.py` 內部需要自己
  處理 token refresh 邏輯（可以做到不影響 `providers.py` 對外介面），
  但這件事本身讓 Schwab 的整合工作量比其餘候選明顯高一截，這也是
  本輪把它排在優先度較低的理由之一。
- **`api_app/main.py` 的 Historical IV pipeline 完全獨立**（走
  `default_historical_surface()`／`default_contract_history()`），
  換掉「即時鏈」資料源不會牽動這一塊——兩件事在 `providers.py` 裡
  本來就是分開的兩支 usage（`MARKET_DATA` vs `HISTORICAL_IV`），選
  live-chain vendor 時不需要連帶考慮 Historical IV 那條線是否受影響。

**結論**：換 vendor 這件事本身，在本產品既有架構下**是一件工程上輕量
的事**（新增一個 adapter 模組＋一行白名單），真正的門檻與不確定性
全部集中在**條款與價格**，不在程式碼——這也是本文件把絕大多數篇幅
放在 ToS／定價查證而非架構設計的原因。

---

## 6. 規模成本推算（100／1,000／10,000 使用者量級）

> 本節刻意用量級推理而非假裝有精確數字——多數候選的商業方案本身就是
> 「依用量客製報價」，沒有公開的量級對照表可套用。

- **若選 Intrinio Silver Options（或任何「delayed data, display-only,
  no per-user fee」性質的方案）**：因為官方明講不逐使用者收費，
  100／1,000／10,000 位使用者理論上**面對同一個固定月費**——真正
  會隨使用者數上升的是本產品自己既有的基礎設施成本（Vercel
  Function Invocations／Neon 儲存，`public-beta-platform-facts.md`
  第 5 節已經分析過這部分），不是資料授權費本身。這是這類方案的
  核心吸引力：**授權費用與使用者規模脫鉤**。
- **若選 Databento（走真正的即時 OPRA 授權，而非鎖定延遲資料）**：
  依第 2 節的制度背景，即時資料很可能牽涉逐 Non-Professional
  Subscriber 計費（二手轉述費率約每人每月 $0.60–$1.25，隨累計人數
  遞減），10,000 位使用者量級下這筆費用理論上落在**每月數千至一萬
  美元量級**（未經精確驗證，且費率表是否為 2026 年最新版本本輪
  未查證）——這正是為什麼本文件建議**鎖定延遲資料**而非追求即時性。
- **若選 Cboe DataShop All Access API**：其分層報價本身是依
  「points/月」的用量計費（見 §3.6 表格），使用者數增加若直接帶動
  API 呼叫量增加（每個使用者觸發自己的 refresh），有可能需要從
  Tier 1（$1,499/月含轉散布）逐步升級到 Tier 2／3／4，**是本輪唯一
  一家把「用量隨使用者數成長」直接寫進定價分層的候選**，量級推算
  相對最容易但基礎月費也最高。
- **若選 EODHD B2B**：因為資料是 EOD（每日一次），**理論上使用者數
  完全不影響向 vendor 抓取的次數**（本產品可以只在每天固定時間抓
  一次、快取一整天供全部使用者共用），是本輪所有候選裡「使用者規模
  與 vendor 端成本關聯度最低」的一個，但代價是資料新鮮度的產品面
  取捨（見 §3.9／第 4 節）。

**一個所有候選都適用的既有事實**：現行 Refresh Run 架構（ADR-0001）
本來就已經把「同一次批次刷新內，同一個 symbol 只抓一次」這件事做好了
——多個使用者若剛好在追蹤同一個標的、同一輪刷新視窗內，本來就不會
對外部 vendor 重複發出請求。這代表「10,000 位使用者」不必然等於
「10,000 次獨立的 vendor API 呼叫」，實際呼叫量取決於「有多少個
distinct symbol 正在被追蹤」而非「有多少個使用者」——這件事在估算
任何一家 vendor 的用量費時都應該納入考量，但本輪未進一步建立
量化模型（屬於後續施工票該做的容量規劃工作，非本輪研究範圍）。

---

## 7. 最推薦方案／次佳方案／明確不推薦方案

### 最推薦方案：Intrinio Silver Options

**理由**：官方頁面白話文字精確對應本產品的用法（「顯示給企業的終端
使用者，不逐人收費，不需要額外交易所手續」），且鎖定的正是本產品
既有的延遲資料定位，制度上（OPRA 對延遲資料免逐訂閱者費）與 vendor
自己的條款（display-only 授權免加價）兩層都對齊。**唯二保留**：
(1) 確切月費本輪查不到，需要 Owner 或後續施工者實際留資料索取報價
才能確認這是不是一個 Beta 階段真的負擔得起的數字；(2) 「禁止散裝
下載原始資料」這條限制，需要處理既有的 CSV 原始資料下載功能。

### 次佳方案：Databento（鎖定延遲資料的自助簽約路徑）

**理由**：真正的官方自助流程（問卷→自動產生合約），且它扮演的角色
是「幫你辦好與 OPRA 的手續、不加價轉嫁」而非自己設限——若能在問卷
流程裡明確選擇「只要延遲資料」，理論上會拿到本輪所有候選中最貼近
「真實成本、不含中間商加價」的報價。**保留**：本輪未實際跑過這個
問卷流程，無法確認延遲資料選項是否真的存在、以及最終月費，需要
實際嘗試申請才能驗證。

### 第三順位：Cboe DataShop／LiveVol All Access API

**理由**：概念最乾淨——同一家交易所，官方明確把「client-facing
applications」寫進轉散布授權說明，欄位語意與現行 `cboe.py` adapter
幾乎一致，換源時的資料模型改動最小。**代價**：目前查到的價格
（Tier 1 含轉散布 $1,499/月）是本輪合法路徑中偏高的一個，且官方
頁面本輪多次嘗試直接讀取遭拒（HTTP 403），確切條款與是否有更便宜
的「僅延遲資料」子方案未能查證，建議若考慮這條路，先直接聯繫 Cboe
DataShop 業務索取延遲資料專屬報價。

### 明確不推薦方案

1. **維持現行 Cboe 刮取端點與 Yahoo Finance 抓取方式**——這正是本
   ticket 存在的理由：`public-beta-platform-facts.md` 已直接抓取
   官方頁面逐字確認 Cboe「嚴格禁止自動抓取程式，違者將封鎖 IP」，
   Yahoo 官方條款同樣明文禁止自動化擷取與「建立競品資料源」。這不是
   「用量大了才會踩到」的門檻，是現在這一刻就已經在條款容許範圍
   之外的既有狀態，Public Beta 只會提高被偵測、被封鎖、影響全站
   的機率。
2. **Alpha Vantage／Polygon 免費或個人付費層／MarketData.app 現有
   一般方案／Finnhub 免費層／Twelve Data 個人層**——全部條款白紙
   黑字禁止「建立供其他終端使用者使用的應用程式」，若不先取得這幾
   家各自獨立、價格未公開的商業授權，套用在 Public Beta 上就是明文
   違約，與繼續刮 Cboe 本質是同一種風險，只是換了一家公司。
3. **Twelve Data**——在本輪查證範圍內找不到證據顯示它真的有一個
   文件完整的美股選擇權鏈端點，基本能力存在與否都未確認，不建議
   在確認這件事之前投入條款與定價的進一步查證。
4. **Finnhub**——除了條款上的商業使用限制外，既有研究已記錄過其
   選擇權鏈端點本身的公開品質疑慮（見 `option-chain-data-sources.md`
   §3.7 引用的兩則 GitHub issue），本輪判斷不值得優先投入。

---

## 8. 誠實揭露：本輪沒查到／查不到的事

- **Intrinio Silver Options 的確切月費／年費**——官方把價格藏在需要
  留資料的表單頁面後面，本輪多次嘗試搜尋具體數字皆未果，只能引用
  Intrinio 全站籠統區間（$250/月起）作為粗略參考，不能確定這個特定
  方案落在此區間內。這是本文件「最推薦方案」底下最大的一個未知數，
  若這個數字實際上遠高於預期，排序結論可能需要重新評估。
- **Cboe DataShop All Access API 的完整定價頁面原文**——`WebFetch`
  直接讀取遭 HTTP 403 拒絕，本輪引用的分層報價數字全部來自搜尋引擎
  索引轉述，未能核對官方頁面逐字原文，其中「Free 層是否含轉散布權」
  「各 Tier 的『points』確切定義與換算方式」皆未查證。
- **Databento 走完整自助問卷流程後、鎖定延遲資料選項的實際總月費**
  ——本輪只讀到流程說明（文件層級），未實際模擬走過這個問卷，無法
  確認延遲資料在這個流程裡是否是一個明確可選的分支、以及選了之後
  最終報價會落在哪個數字。
- **OPRA 官方費用表本身的 2026 年最新版本逐字原文**——本輪搜尋結果
  一致指向 2018 年生效的費率（每位 Non-Professional Subscriber
  $0.60–$1.25／月，隨累計人數遞減），以及「延遲資料免收逐訂閱者費」
  「約 $1,500/月的 redistributor 固定費」這兩項政策方向，但**未能
  直接讀取 <https://cdn.opraplan.com/documents/OPRA_Fee_Schedule.pdf>
  本身逐字核對這些數字在 2026 年是否仍然準確**——這些搜尋到的 URL
  本輪僅列出、未實際成功抓取內容。「$1,500/月 redistributor 固定費」
  這個數字更是只從單一二手來源（MarketData.app 自己的教育部落格，
  該公司對外銷售自己的資料方案，存在推銷自身產品、貶低 DIY 路線的
  潛在動機）取得，未經任何官方文件交叉核對，是本文件裡信心等級
  最低的一個具體數字，任何後續決策若牽涉到「自己直接向 OPRA 註冊
  vendor 身份」這條路，務必在動用真實預算前重新獨立查證這個數字。
- **各家 vendor 對本產品實際會用到的完整履約價／到期日梯度（尤其
  LEAPS，本產品既有紀錄顯示這是歷史上多次踩雷的角落）的真實覆蓋度**
  ——本輪僅依官方行銷文案「全鏈」「全部到期日」等泛稱推斷，沒有一家
  candidate 真正申請試用帳號、實際打過 API 驗證過長天期合約是否
  確實涵蓋在內，這件事的驗證需要真正取得試用權限才能做，超出本輪
  純文件查證的範圍。
- **Polygon／MarketData.app／EODHD／dxFeed／ORATS 的「Business」／
  轉散布方案實際報價**——全部需要聯絡業務才能取得，本輪未進行任何
  人工接洽（任務範圍明確排除代表 Owner 進行商業談判），因此除了
  Cboe DataShop（透過二手搜尋轉述取得部分數字）之外，其餘幾家的
  合格方案價格幾乎全部是 `UNVERIFIED`。
- **本輪未嘗試申請任何一家的試用帳號、也未實際發出任何 API 請求**
  ——全部查證皆基於官方公開頁面（ToS／pricing／docs）的文字內容，
  沒有一項是透過實際呼叫 API 驗證欄位真的存在、格式是否與文件相符。
  這與既有的 `option-chain-data-sources.md`（2026-08-02）用同一套
  「文件查證優先於實測」的方法論，風險與侷限也相同：若正式決定採用
  某一家，強烈建議先申請免費試用或最低付費層，實際打一次 API 驗證
  過欄位形狀，再投入正式整合工程。
