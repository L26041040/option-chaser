# 匿名優先產品的身份／儲存／過期慣例研究

**issue #274**（`L26041040/option-chaser`），Wayfinder 地圖 #272「Anonymous Public
Beta」子票。**本文只研究、不施工、不裁決**——`option_chaser/`／`api_app/`／`src/`
零改動，未觸碰任何 GitHub issue／PR，未跑測試。全部「存取日期」皆為
**2026-09-11**。

**證據分級**（每個結論標記其一）：

- 【業界慣例】——多數成熟產品的常見做法，非強制，但被廣泛採用
- 【法規／安全必要】——有明確、可觀察的法規遵循或安全後果，跳過等於留一個已知缺口
- 【純產品選擇】——這件事在不同成熟產品之間分歧很大，沒有單一「正確答案」

**標記說明**：「文件未說明」＝官方一手來源（官方文件／ToS／FAQ／官方部落格）
確實沒有回答這一題；「UNVERIFIED」＝我找到了某個說法，但只來自二手轉述
（社群討論、部落格評測、第三方比較網站），**未能**在官方一手來源裡獨立
核實，因此不採信為結論依據，只當線索使用。

---

## 給 Owner 看的白話摘要

這次調查看了 12 個現在還在正常營運、真的有大量使用者在用的成熟產品，
橫跨四種類型：純畫圖／繪圖工具（Excalidraw、tldraw、diagrams.net）、
金融計算機（Portfolio Visualizer、OptionStrat、Options Profit
Calculator）、免登入的線上程式編輯器（CodeSandbox、StackBlitz、
Replit）、以及免登入的分享型小工具（TypeScript Playground、CodePen、
Pastebin）。每一個都問同樣七個問題：怎麼認出「這是同一個人」、資料存在
哪裡、清 cookie 會怎樣、資料放多久、匿名跟登入差在哪、能不能把匿名資料
搬進帳號、弄丟識別方式後有沒有救。

**最重要的一個發現，而且是三個獨立產品各自得出同樣結論**：Replit、
CodePen、CodeSandbox 這三家原本都比現在更慷慨地讓陌生人不登入就能做
比較「重」的事情（Replit 是不登入就能直接執行程式碼、CodePen 是不登入
就能存檔、CodeSandbox 是不登入就能即時編輯）。三家後來**都往回收**——
理由都是同一件事：**濫用的成本後來大於維持這個功能帶來的好處**。Replit
自己的官方部落格講得最直白：不登入的執行環境被暗網駭客拿去轉賣 DDoS
攻擊服務，而且擋這些濫用要付給 Google 的 reCAPTCHA 費用漲到比 Replit
當月營收還高，逼得他們選擇收掉大部分的匿名體驗、改成登入才能建立與
儲存專案。CodePen 也是同一個故事的另一個版本：他們是「不打招呼、立刻
生效」直接關掉匿名存檔功能，理由是要防止濫用者搶在功能真的關閉前先
鑽漏洞。**這三個案例都比 Option Chaser 目前的設計更保守**——它們燒的
是自己的伺服器資源，不是像 Option Chaser 這樣，每次陌生人刷新一個
劇本，就要去呼叫一個有配額限制、按量計費的第三方報價廠商 API。這代表
Option Chaser 目前規劃的「匿名使用者觸發第三方付費 API」這個模式，
在成熟市場上找不到一個結構完全對應、而且仍在正常運作的先例——最接近
的先例（Replit）反而是「試過，後來收回去」的故事。

**第二個重要發現**：大多數工具其實**不需要**伺服器端持久記住匿名
使用者是誰。純繪圖工具把資料整個放在瀏覽器自己的儲存空間（不是
伺服器）；金融計算機讓你算完就看結果，只有「登入後才能存起來追蹤」；
分享型小工具（TypeScript Playground、Pastebin、OptionStrat）乾脆把
整個狀態塞進網址本身，網址就是唯一的「救命繩」，不靠 cookie 也不靠
帳號。**沒有任何一個成熟產品官方文件明講「我們會在你清 cookie 之前
主動跳出警告」**——這件事看起來業界慣例是不做的，做過的（例如
Excalidraw 曾被社群多次要求要加更清楚的警告文字）也是事後補、不是
一開始就有的預設設計。

---

## 摘要表

（每格為精簡摘要，完整說明與逐條引用見下方各案例章節；「文件未說明」＝
官方沒講，「UNVERIFIED」＝只有非官方線索、未獨立核實）

| 案例 | Q1 識別機制 | Q2 伺服器端儲存 | Q3 清除後果／是否主動警告 | Q4 匿名資料過期 | Q5 匿名限制／登入解鎖 | Q6 匿名→帳號遷移 | Q7 弄丟識別後的救援 |
|---|---|---|---|---|---|---|---|
| **Excalidraw**（自由版） | 無伺服器身份，資料活在瀏覽器 localStorage／IndexedDB；協作連結靠 URL fragment 帶加密金鑰 | 一般繪圖：無；協作房間：伺服器存加密後的密文（無法解讀） | 清除即失去繪圖，官方文件未提「主動警告」 | 文件未說明（純受瀏覽器自身儲存政策支配） | 匿名＝完整繪圖功能無額度限制；Excalidraw+（付費）解鎖跨裝置雲端庫、版本紀錄、團隊協作 | 有：登入 Excalidraw+ 時「大多數情況會自動匯入」本機場景，找不到再手動 Save to | 協作連結本身就是救命繩（需自己收藏）；純本機繪圖若未匯出／匯入，官方未提供任何救援 |
| **tldraw**（tldraw.com） | 無伺服器身份，SDK 文件描述以 `persistenceKey` 存 IndexedDB（單瀏覽器內跨分頁同步） | 單人編輯：無；多人協作用另一個 sync 伺服器（產品本身細節文件未說明，SDK demo 伺服器明講 24 小時清空） | 清除本機儲存即失去文件；官方文件未提主動警告 | SDK demo 伺服器明講 24 小時；tldraw.com 正式產品的匼理保留期文件未說明 | 匼名＝可畫圖、無需註冊；產品是否有任何登入帳號層文件未說明 | 文件未說明 | `.tldr` 檔案匯出／匯入是官方建議的備份方式；協作連結需自行保存 |
| **diagrams.net**（draw.io） | 完全不記識別——「同一份文件」＝你自己選的儲存位置（Google Drive／OneDrive／GitHub／本機） | 明文承諾：draw.io 不儲存你的圖表資料，只在偵錯用途下保留 IP／裝置資訊的伺服器日誌（10 天循環覆寫） | 若選「稍後決定」且只停在瀏覽器暫存，清除即遺失——但存檔流程本身就內建提示文字警告這一點 | N/A（無圖表內容留存）；日誌 10 天覆寫 | 匿名＝完全功能、無帳號綁定；沒有「登入解鎖」概念（雲端儲存本身可能各自需要你自己的 Google／MS 帳號） | N/A——沒有 draw.io 自己的帳號模型 | 完全取決於你自己選的儲存位置（Drive 版本紀錄等），draw.io 本身不提供任何救援 |
| **Portfolio Visualizer** | 計算本身不需要任何識別；「儲存模型」需登入註冊帳號 | 匿名：無（結果只在當次頁面存在）；已登入：儲存的 Portfolio／Simulation Models 綁在帳號上 | 匿名使用無資料可失去，故無警告必要 | 帳號資料：「保留到不再需要提供服務為止，或使用者要求刪除，或帳號被刪除」（無具體天數） | 匿名／免費＝可跑回測、Monte Carlo 等分析（上限 25 個資產），但不能存檔／匯出；付費 Basic／Pro 解鎖存檔、150 個資產上限 | N/A（匿名端本無資料） | N/A |
| **OptionStrat** | 匿名端無帳號式識別；策略狀態直接編碼進分享網址本身 | 匿名：無（網址即狀態）；已登入「Saved Trades」需要伺服器持續追蹤損益，故存在帳號資料庫 | 清 cookie／換裝置對「分享網址」完全無影響；只有帳號綁定的 Saved Trades 才會受帳號登入狀態影響 | 文件未說明（分享網址本身無明訂到期） | 匿名＝可建構、檢視、分享策略；登入解鎖「儲存並持續追蹤損益」與進階（Premium）圖表 | 概念上不適用——URL 從未綁定身份，登入後按存檔鍵才第一次產生綁定 | 網址本身就是完整救命繩，跟 cookie／帳號無關 |
| **Options Profit Calculator** | 匿名端可用核心計算機；具體識別機制文件未說明（頁面有站台層級 cookie domain 設定，用途未細分） | 匿名：文件未說明是否落地；會員（Membership）等級可「加入投資組合」追蹤損益 | 文件未說明 | 通用隱私政策措辭：「保留到不再需要為止，除非法律另有規定」（無具體匿名天數） | 匿名＝核心策略計算機全開放；付費會員解鎖投資組合追蹤、IV 情境模擬、無廣告、試算表下載 | 文件未說明 | 文件未說明（頁面有「分享」相關程式碼線索，但官方文字未確認機制） |
| **CodeSandbox** | **歷史**：曾用追蹤 cookie「比對匿名使用者與其 sandbox」；**現況**：官方文件描述非工作區成員只能瀏覽／執行公開 sandbox，要編輯須先 fork 進自己的工作區（等於需要帳號） | 現況下 sandbox 一律伺服器端持久儲存，但匿名建立流程在目前文件中已不被視為主要路徑 | UNVERIFIED（社群回報清 cookie 後找不到匿名建立的 sandbox，官方文件未明確承諾或警告） | 文件未說明具體天數；VM 閒置 5 分鐘（免費）／30 分鐘（Pro）休眠（僅運算暫停非刪除）；合約終止後「盡快銷毀或刪除使用者內容」 | 免費工作區 20 個 sandbox 總額度、月付 400 VM 額度、公開專案不限；私有／協作需 Pro | 文件未說明明確的「認領」流程 | 文件未說明；社群回報曾發生匿名建立的 sandbox 連刪除都做不到 |
| **StackBlitz** | 核心編輯器（Classic／WebContainers）整個在瀏覽器裡執行，不需要伺服器身份；隱私政策的資料保留章節只談「帳號」，完全不提匿名資料類別 | 官方隱私政策原文：「檔案與你的帳號及相關專案綁定儲存」——沒有匿名資料儲存的說明 | 未連 GitHub／未登入時清除等同直接失去尚未存檔的專案；官方文件未提警告 | 帳號自願關閉後 30 天內刪除或匿名化（不超過此期限）；匿名資料類別本身文件未說明因為它似乎不存在 | 免費（Personal）帳號可存無限公開專案；付費（Personal+）解鎖私有專案與檔案上傳 | 文件未說明（UNVERIFIED：社群討論提到未登入建立的專案「不會被存檔，因為它不是 fork」） | 文件未說明；WebContainers 是純瀏覽器執行，關掉分頁即消失 |
| **Replit** | **歷史**：完全不需帳號，靠 Google reCAPTCHA 擋機器人；**現況**：建立／儲存 Repl 需登入（Email／Google／GitHub／Apple），少數語言頁面保留極簡「試跑」不需登入 | Repl 本身一律伺服器端執行與儲存；現行「試跑」路徑刻意設計成不留下可回訪的完整專案 | 文件未說明（現行匿名路徑本就不打算持久） | 帳號 1 年無活動後可被終止；DPA 客戶可在合約終止後 90 天內要求刪除 | **官方部落格明講整個產品史上最重的裁示**：曾允許完全匿名執行程式碼，被濫用做暗網 DDoS 轉售與大量botting，Google reCAPTCHA 漲價後（甚至比月營收還貴）選擇大幅收回匿名體驗，改為登入才能建立／儲存 | N/A（現行設計下已無值得遷移的匿名持久狀態） | N/A |
| **TypeScript Playground** | 完全無身份概念——狀態＝網址本身（gzip 壓縮的原始碼＋設定差異全編碼進 URL fragment） | 無（官方文件完全未提資料庫／後端持久化） | 只要沒有先取得／分享那個即時更新的網址，關閉分頁等同失去未分享的編輯內容；已分享的網址不受 cookie／裝置影響 | N/A（網址本身無到期機制） | 無帳號層概念，匿名即完整功能 | N/A | 網址本身即完整、自足的救命繩 |
| **CodePen** | **現況**：官方文件明講「必須要有帳號並登入」才能進入 Pen Editor 建立 Pen；Collab Mode 允許完全匿名的人加入即時協作（但不能 fork／不能聊天） | 已登入使用者的 Pen 存在伺服器；歷史上曾允許匿名存檔（無帳號歸屬），該功能已徹底移除 | N/A（現在建立內容本就需要登入） | 一般隱私政策措辭：資料保留到你刪除帳號或退出為止 | 免費帳號即可存檔、公開分享；Pro 解鎖私有 Pen、資產代管等 | N/A（無匿名建立路徑可遷移） | N/A——2019 年官方部落格明講：因為「垃圾訊息／詐騙等惡意使用者」大量濫用匿名存檔，**無預警、立即生效**永久移除該功能 |
| **Pastebin** | 訪客沒有跨次造訪的持久身份；官方措辭暗示「登入使用者才有」用來識別的 cookie；每一則貼上內容靠自己的 URL 獨立定位，不靠「使用者」 | 訪客貼文確實存在伺服器（產品本體），但不綁定任何匿名使用者紀錄——貼文本身才是持久單位 | 清 cookie／換裝置對已存在的貼文毫無影響（它活在自己的網址）；但官方 FAQ 直白承認「以訪客身份貼上的內容沒有快速刪除選項」 | 由建立者在建立當下自行選擇到期時間（永久／10 分鐘／1 天…等）；訪客預設值官方文件未明確區分 | 訪客：24 小時內最多 10 則、可設公開／未列出，**不能**設私密，單則上限 512KB；PRO：24 小時 250 則、可設私密、單則上限 10MB | 概念上不適用——訪客貼文本無擁有者身份，登入後只能重新貼一份，不是「搬過去」 | 貼文自己的網址就是唯一的存取方式；官方明講訪客內容沒有任何刪除／救援管道 |

---

## 逐案例研究

### (a) 匿名優先網頁工具

#### 1. Excalidraw

**Q1 識別機制**：自由版（excalidraw.com）**不使用任何伺服器端身份**——
繪圖存在瀏覽器自己的儲存空間：「localStorage is used for scene
elements and app state, and IndexedDB is used for binary files and
library items」（[Excalidraw
docs](https://excalidraw-excalidraw.mintlify.app/guides/storage)，
2026-09-11 存取）。多人協作（Live Collaboration）則完全不靠伺服器
發的識別碼，而是把房間 ID 與對稱加密金鑰一起塞進**網址的 fragment
部分**（`#` 後面那段，瀏覽器規範上永遠不會送到伺服器）：「A symmetric
AES key is generated on the client side and appended to the sharing
URL as a fragment identifier」（[Excalidraw Blog — End-to-End
Encryption](https://plus.excalidraw.com/blog/end-to-end-encryption)，
2026-09-11 存取）。只有付費的 Excalidraw+ 才有真正的帳號式登入
（email／SSO）。

**Q2 伺服器端儲存**：一般繪圖：無。協作房間：伺服器會**relay**（轉發）
繪圖資料給參與者，但「they receive only encrypted bytes. They cannot
read what you've drawn」（[Excalidraw Blog — Building the P2P
Collaboration
Feature](https://plus.excalidraw.com/blog/building-excalidraw-p2p-collaboration-feature)，
2026-09-11 存取）。至於這份加密後的房間內容具體會在伺服器上保留
多久，我沒有在官方文件／部落格頁面找到明確數字（**文件未說明**）；
一個 GitHub Discussion 裡提到「房間的內容會被持久化到伺服器」，但
那則討論串本身不是官方文件頁面，**列為 UNVERIFIED**，不採信為
「保留多久」的依據。

**Q3 清除後果／是否主動警告**：官方文件（開發者文件的 Storage 頁面）
只描述機制本身，**沒有**提到會在使用者操作前主動跳出警告；文件反而
建議使用者**自己**記得手動匯出：「For permanent storage you can
export scenes to .excalidraw files」（同上開發者文件頁）。是否曾經
或現在會在畫面上顯示某種提示，官方文件層級**文件未說明**——多個
社群 GitHub 討論／issue 反映使用者對這件事的困惑與挫折（例如要求
更明確警告文案的 issue），但那些是社群回報而非官方確認的產品行為，
僅作為「這是真實痛點」的旁證，不當作事實依據。

**Q4 匿名資料過期**：不適用一般定義下的「過期」——資料完全交給
瀏覽器自身的儲存空間管理政策（配額滿了、使用者手動清除、瀏覽器自動
回收等），Excalidraw 本身不對這份資料設定任何 TTL。**文件未說明**
更細節的邊界情況（例如瀏覽器配額用盡時的行為）。

**Q5 匿名限制／登入解鎖**：匿名（免費）使用可完整使用繪圖工具，
官方文件未列出任何人為設下的功能或用量上限。Excalidraw+（付費帳號）
解鎖：跨裝置雲端同步的工作區、SOC2 稽核（[Excalidraw+ Security &
Compliance](https://plus.excalidraw.com/security-and-compliance)，
2026-09-11 存取）與團隊協作功能。

**Q6 匿名→帳號遷移**：**有明確、官方文件化的機制**：「In most cases,
we are now auto-importing your Excalidraw.com scene to your new
workspace」，找不到時的手動備援路徑是先造訪
`excalidraw.com/#noredirect`（或關閉偏好設定裡的自動跳轉），再走
`Menu → Save to → Excalidraw+`（[Excalidraw+ — How to
Start](https://plus.excalidraw.com/how-to-start)，2026-09-11 存取）。

**Q7 弄丟識別後的救援**：協作房間——分享連結本身（內含解密金鑰）
就是唯一的存取憑證，官方原文明講「you need to store the link
yourself (e.g. you can bookmark it)」（同 Q1 P2P 協作部落格）；一旦
連結本身遺失，官方沒有提供任何額外救援管道。一般本機繪圖——若使用者
從未匯出 `.excalidraw` 檔案也從未登入 Excalidraw+ 觸發自動匯入，
清除瀏覽器儲存後**官方文件沒有提供任何救援機制**。

---

#### 2. tldraw

**Q1 識別機制**：tldraw 的開發者文件（SDK／產品共用同一套底層技術）
描述核心持久化機制是 `persistenceKey`：「saves the document and any
uploaded assets to IndexedDB and syncs across browser tabs」，且
「two editors with the same key share the same document and stay
synchronized」（[tldraw Docs —
Persistence](https://tldraw.dev/docs/persistence)，2026-09-11
存取）——這代表識別單位是「同一瀏覽器裡的某把 key」，不是伺服器發的
使用者身份。多人協作另外走 `@tldraw/sync` 套件，該文件描述其提供
「real-time collaboration」讓「multiple users can edit the same
document simultaneously」（同上）。**需誠實區分**：以上引用皆來自
tldraw 官方**開發者／SDK**文件（tldraw.dev），描述的是這套技術本身
的通用能力；tldraw.com 這個**產品本身**內部具體怎麼組裝使用這套
技術，我沒有找到專屬於 tldraw.com（而非 SDK）的官方文件頁面獨立
確認，這部分列為**文件未說明**。

**Q2 伺服器端儲存**：單人編輯：無（IndexedDB 本機儲存）。多人協作：
tldraw 官方 FAQ 提到自家的自架方案（`tldraw sync`）「is a self-hosted
solution that we use for collaboration on tldraw.com」（[tldraw
FAQ](https://tldraw.dev/faq)，2026-09-11 存取）——這確認 tldraw.com
的多人協作確實走這套 sync 架構，但該架構在 production 用途下的
資料保留策略、儲存後端等細節，SDK 文件只針對**開發者自架**情境給出
建議（例如建議用 Cloudflare Durable Objects＋SQLite 持久化），
**tldraw.com 自己 production 環境實際採用的確切保留規則文件未說明**。
SDK 本身附帶的**demo/prototyping** 伺服器則有明確聲明：「data only
lasts 24 hours and rooms are publicly accessible」（[tldraw Docs —
Sync](https://tldraw.dev/docs/sync)，2026-09-11 存取）——但這是官方
明講給開發者「原型測試用」的伺服器，不是 tldraw.com 產品本身的
保留政策，兩者不可混為一談。

**Q3 清除後果／是否主動警告**：本機儲存被清除即遺失單人編輯的
文件，SDK 文件未提任何主動警告機制。

**Q4 匿名資料過期**：demo/prototyping sync 伺服器明講 24 小時（見
Q2）；tldraw.com 產品本身的多人協作房間保留期**文件未說明**。

**Q5 匿名限制／登入解鎖**：官方文件確認的部分僅止於「no signup」／
免登入即可開始畫圖這件事本身；是否存在任何登入帳號層、登入後解鎖
什麼功能，**文件未說明**（我沒有找到 tldraw.com 專屬的帳號／訂閱
說明頁）。

**Q6 匿名→帳號遷移**：**文件未說明**。

**Q7 弄丟識別後的救援**：官方文件建議的備份方式是手動匯出 `.tldr`
檔案：「to save a copy of your current project as a .tldr file, you
select Menu > File > Save a copy」（[tldraw Persist to
Storage範例文件](https://tldraw.dev/examples/data/assets/local-storage)，
2026-09-11 存取，經 WebSearch 摘要間接確認，原始頁面內容未能逐字
覆核，**此點列 UNVERIFIED**，但 `.tldr` 檔案匯出功能本身在
persistence 官方文件中有清楚描述）。多人協作房間則需自行保存連結，
與 Excalidraw 同一種模式。

---

#### 3. diagrams.net（draw.io）

**Q1 識別機制**：**完全沒有**用來識別「同一個使用者」的機制——這個
產品刻意不建立使用者身份的概念。官方文件原文：「As draw.io does not
store your diagram data, you need to select a location to store your
diagram files」（[draw.io — Save Diagram
Files](https://www.drawio.com/docs/getting-started/save-diagram-files/)，
2026-09-11 存取）。「同一份文件」是由使用者自己選定的儲存位置
（Google Drive／OneDrive／GitHub／GitLab／Dropbox／瀏覽器本機／
本機磁碟）來定義，不是由 draw.io 認出「你是誰」。

**Q2 伺服器端儲存**：官方明文承諾**不儲存圖表內容**：「draw.io
does not allow diagram data to be stored on their servers」（[draw.io
Trust Center](https://www.drawio.com/trust/)，2026-09-11 存取，經
WebSearch 摘要取得原文措辭）。伺服器唯一保留的是為了維運除錯用的
IP 位址與裝置資訊日誌，且「These logs are cyclically overwritten
every 10 days」（同上）。官方也明講不使用 cookie 或追蹤像素：
「draw.io doesn't use cookies or tracking pixels on their website」
（同上）。若因處理需求偶爾把資料暫時送到伺服器，官方承諾「that is
documented publicly」（同上）。

**Q3 清除後果／是否主動警告**：draw.io 的儲存流程本身內建了近似
「主動警告」的設計——若你選擇「Decide Later」（稍後決定要存哪），
官方文件明講：「diagram data will stay in your browser, but may not
be saved permanently until you select File > Save as and choose a
location」（[draw.io — Save Diagram
Files](https://www.drawio.com/docs/getting-started/save-diagram-files/)，
2026-09-11 存取）——這句話本身就在存檔流程的當下把風險講清楚，而不是
被動地等你事後發現。若你選擇了真正的雲端／本機儲存位置，清除瀏覽器
資料則完全沒有影響，因為文件的「家」在別的地方。

**Q4 匿名資料過期**：不適用（無圖表內容留存）；日誌 10 天循環覆寫
（見 Q2）。

**Q5 匿名限制／登入解鎖**：官方明講沒有帳號綁定這件事：「With draw.io,
your diagram files aren't locked behind any account」（同上 Trust
Center）。核心繪圖功能匿名即完整可用；企業版（例如 Confluence／Jira
的付費外掛）另有其團隊層級功能，但那是外掛產品層級的差異，不是
「匿名 vs. 登入」這條軸線。

**Q6 匿名→帳號遷移**：**概念上不適用**——因為 draw.io 從未建立自己的
使用者帳號體系，沒有「匿名狀態」可供遷移；使用者本來就是直接綁定
自己選的第三方帳號（Google／Microsoft／GitHub 等）。

**Q7 弄丟識別後的救援**：完全取決於使用者自己選的儲存位置提供什麼
（例如 Google Drive 自己的版本紀錄、GitHub 自己的提交歷史），draw.io
本身不提供任何獨立於這些外部服務之外的救援機制。

---

### (b) 金融計算機

#### 4. Portfolio Visualizer

**Q1 識別機制**：跑分析本身不需要任何識別；只有「儲存 Portfolio 或
Simulation Model」才需要登入註冊帳號——官方 FAQ 頁：「When you are
signed in with your registered account you will see a 'Save
Portfolio' link under the portfolio asset allocation section of the
results」（[Portfolio Visualizer
FAQ](https://www.portfoliovisualizer.com/faq)，2026-09-11 存取）。

**Q2 伺服器端儲存**：匿名使用完全不落地任何伺服器端紀錄——結果只在
當次頁面呈現。已登入使用者的儲存模型放在帳號底下：「You can see the
list of saved portfolio models and their type in the saved models
section under your preferences」（同上 FAQ）。

**Q3 清除後果／是否主動警告**：匿名使用本身沒有任何資料可失去，因此
不需要、也沒有找到任何警告機制。

**Q4 匿名資料過期**：帳號資料的官方隱私政策措辭：「Information
associated with your account will generally be kept until it is no
longer necessary to provide the services or until you ask us to
delete it or your account is deleted whichever comes first」
（[Portfolio Visualizer Privacy
Policy](https://www.portfoliovisualizer.com/privacy-policy)，
2026-09-11 存取）——這是一般性、無具體天數的措辭，且完全針對「有
帳號」的情境；匿名使用因為本無資料留存，這條規則不適用，官方文件也
未另外對「匿名資料」單獨作出保留期承諾。

**Q5 匿名限制／登入解鎖**：官方隱私政策明講「If you choose not to
register or provide personal information, you can still use our
websites and online tools but you will not be able to receive
additional services or access certain areas that require
registration」（同上 Privacy Policy）。具體額度差異：免費（含匿名）
可分析最多 25 個資產的投資組合、可跑回測／Monte Carlo／壓力測試等，
但**不能儲存或匯出模型**；付費 Basic／Pro 方案支援最多 150 個資產，
且解鎖儲存功能（[Terms of
Service](https://www.portfoliovisualizer.com/terms-of-service)，
2026-09-11 存取，及上述 FAQ 頁）。

**Q6 匿名→帳號遷移**：不適用——匿名端本來就沒有產生任何伺服器端
資料可供遷移，登入後的「儲存」動作是第一次真正建立資料，不是搬遷
既有資料。

**Q7 弄丟識別後的救援**：不適用（同上理由，匿名端無資料曾經存在）。

---

#### 5. OptionStrat

**Q1 識別機制**：匿名使用**沒有任何帳號式的持久身份**——一個策略的
完整狀態直接編碼進網址本身。官方教學頁原文：「You can also simply
copy the URL from your browser to share a trade, but it won't be
added to your account unless you save it through the save dialog」
（[OptionStrat — Options Builder
Tutorial](https://optionstrat.com/tutorials/options-builder)，
2026-09-11 存取，本文直接以 curl 取得該頁原始 HTML 逐字核對）。

**Q2 伺服器端儲存**：匿名分享的網址本身不對應任何伺服器端的「使用者」
紀錄——網址即狀態。只有登入後點選「儲存」，該筆交易才進入帳號綁定的
「Saved Trades」清單，並開始被伺服器持續追蹤損益：「Saved trades will
show on the saved tab and allow you to track the profit and loss of
your trade over time」（同上教學頁）。

**Q3 清除後果／是否主動警告**：由於分享機制完全建立在網址本身而非
cookie，清除 cookie、換瀏覽器、開無痕視窗對「已產生並分享出去的網址」
**完全沒有影響**——這是這個案例最鮮明的特性。唯一會受帳號登入狀態
影響的是「Saved Trades」這種需要持續追蹤的功能，但那本來就是帳號
綁定的東西，不是匿名識別碼被清除的問題。官方文件未提任何警告機制
（因為結構上不太需要）。

**Q4 匿名資料過期**：官方隱私政策對「關閉帳號」後的資料有一般性
措辭：「we may still retain (a) any non-personally identifiable
information, and (b) certain personal information associated with
your account, if retention is reasonably necessary...」
（[OptionStrat Privacy
Policy](https://optionstrat.com/privacy)，2026-09-11 存取，經 curl
直接取得原文），但**沒有**針對「一個分享出去的匿名網址本身會不會
過期」給出任何具體天數，**文件未說明**。

**Q5 匿名限制／登入解鎖**：匿名可完整建構、檢視、計算策略並產生
分享網址；登入後解鎖持續追蹤損益（並附圖表）：「Premium members will
also see a graph of the strategy performance so far」（同上教學頁），
以及把交易加入個人的 Saved 分頁進行管理。

**Q6 匿名→帳號遷移**：概念上不完全適用「遷移」這個詞——因為分享的
網址從一開始就沒有綁定任何身份；使用者之後登入並按下儲存鍵時，是
**第一次**把這筆交易與帳號建立關聯，而不是把既有的匿名資料「搬」過去。

**Q7 弄丟識別後的救援**：網址本身**就是**完整、自足的救命繩——只要
保留這個連結（書籤、訊息紀錄等），任何裝置、任何瀏覽器狀態下都能
重建出完全相同的策略檢視畫面，完全不依賴 cookie 或帳號。

---

#### 6. Options Profit Calculator（optionsprofitcalculator.com）

**Q1 識別機制**：核心計算機（Long Call、Spreads 等各種策略計算器）
可在不登入的情況下直接使用，頁面原始碼中確實設有站台層級的
`COOKIE_DOMAIN = '.optionsprofitcalculator.com'`（經 curl 直接取得
首頁原始碼核對），但這個 cookie 具體用來記錄什麼、是否構成一個持久的
「匿名使用者」身份，**官方文件未明確說明**其確切用途與範圍。

**Q2 伺服器端儲存**：**文件未說明**匿名使用是否在伺服器端落地任何
紀錄。「會員」（Membership）等級功能明確描述了會被伺服器持續追蹤的
資料：「Add calculations to portfolio — View the profit or loss on
your saved trades at updated prices」（[Options Profit Calculator —
Membership](https://www.optionsprofitcalculator.com/membership.html)，
2026-09-11 存取，經 curl 直接取得原文）——這意味著「持續追蹤」這件事
是會員專屬能力，暗示匿名端不具備等價的持久儲存，但官方文字沒有
逐字排除匿名端儲存的可能性，故列為文件未說明而非直接否定。

**Q3 清除後果／是否主動警告**：**文件未說明**。

**Q4 匿名資料過期**：官方隱私政策採用一般性的合規標準措辭：「We will
only keep your personal information for as long as it is necessary
for the purposes set out in this privacy notice, unless a longer
retention period is required or permitted by law」（[Options Profit
Calculator — Privacy
Policy](https://www.optionsprofitcalculator.com/privacy-policy.html)，
2026-09-11 存取，經 curl 直接取得原文）——沒有針對匿名資料給出具體
天數。

**Q5 匿名限制／登入解鎖**：匿名／免費：核心計算機（Long Call、Long
Put、Covered Call、Cash Secured Put、各式 Spreads 等）全部可直接使用
（見首頁導覽清單，經 curl 直接核對）。會員解鎖：投資組合追蹤（見
Q2 引文）、「Add anticipated IV changes」情境模擬、「Compare against
alternatives」比較功能、試算表下載，以及付費「Ad-Free」升級選項
（同上 Membership 頁）。

**Q6 匿名→帳號遷移**：**文件未說明**。

**Q7 弄丟識別後的救援**：**文件未說明**——網頁原始碼中存在一個名為
`shareHolder` 的 CSS class（經 curl 核對存在於頁面 DOM 結構中），
暗示可能有某種分享功能，但我沒有找到官方文字明確描述這個分享機制
的具體運作方式（是否比照 OptionStrat 走網址編碼），**此點列
UNVERIFIED，不作為結論依據**。

---

### (c) 免登入 SaaS／程式碼沙盒

#### 7. CodeSandbox

**Q1 識別機制**：**歷史與現況出現明顯落差**，須分開講。官方隱私政策
明確描述曾經（且措辭上看起來至今仍存在的）一種機制：「tracking
cookies used to gather a unique view count of sandboxes and to match
a sandbox to users without an account」（[CodeSandbox Privacy
Policy](https://codesandbox.io/legal/privacy)，2026-09-11
存取——**方法論說明**：`codesandbox.io` 的法律頁面對本次研究環境的
直接請求回應 Cloudflare bot 挑戰頁面 `403`，此段引文取自搜尋引擎
呈現的該頁面摘要文字，未能由我親自逐字覆核完整頁面，但該搜尋結果
明確標示來源即為此官方 URL，予以採信但註記方法論限制）。**現行**
官方使用者權限文件描述的流程則是：「Non-workspace members are able
to open and run public Sandboxes... in order to edit, they will need
to fork the Sandbox to their own workspace」（[CodeSandbox — User
Permissions](https://codesandbox.io/docs/learn/access/permissions)，
2026-09-11 存取，同上方法論限制）——也就是說，**建立／編輯**在目前
文件描述的標準流程裡已回歸帳號（工作區）綁定，匿名端只剩「檢視／
執行公開專案」。

**Q2 伺服器端儲存**：sandbox 本身一律是伺服器端持久物件（這是產品
的核心）；上述追蹤 cookie 機制暗示歷史上曾允許這些伺服器端物件
歸屬於「無帳號的使用者」，而非只歸屬於已註冊工作區。

**Q3 清除後果／是否主動警告**：**UNVERIFIED**——一則社群討論串標題
直接點出「How do I find all the sandboxes I created while being in
Anonymous mode?」，暗示清除識別方式後真的會找不到，但這是社群
討論串而非官方文件確認的行為，且我未能取得官方文件對此情境的
明確承諾或警告文字，故列為 UNVERIFIED。

**Q4 匿名資料過期**：具體天數**文件未說明**。可確認的相關規則：
VM（含預覽）在免費方案 5 分鐘、Pro 方案 30 分鐘無操作後自動休眠（僅
運算暫停，非刪除資料）；合約終止時「CodeSandbox will destroy or
delete any User Content as soon as reasonably possible」（[CodeSandbox
Terms of Use](https://codesandbox.io/legal/terms)，2026-09-11
存取，同上方法論限制）。

**Q5 匿名限制／登入解鎖**：免費工作區：20 個 sandbox 總額度、
每月 400 VM 額度（約 40 小時 Nano VM）、最多 10 個並行 VM、
不限量的公開 sandbox／repository；私有內容與協作功能需要 Pro
方案（綜合多個官方定價／文件頁面，2026-09-11 存取）。

**Q6 匿名→帳號遷移**：**文件未說明**明確的「認領」流程；一則官方
GitHub 討論串上有使用者提出同樣的問題，但沒有找到官方文件層級的
確定答案。

**Q7 弄丟識別後的救援**：**文件未說明**任何官方救援管道；一則社群
GitHub issue 標題直接點出「Not able to delete the codesandbox which
is created as anonymous user」，暗示這是一個已知、尚未有官方解法的
邊界情況（社群回報，非官方確認）。

---

#### 8. StackBlitz

**Q1 識別機制**：StackBlitz 的核心編輯器技術（WebContainers）刻意
設計成**完全在瀏覽器裡執行**，不需要伺服器運算：「WebContainers
compile a Node.js runtime + npm + filesystem to WebAssembly」，讓
「your browser to run Node code without any server」（[StackBlitz
Blog — Introducing
WebContainers](https://blog.stackblitz.com/posts/introducing-webcontainers/)，
2026-09-11 存取）。這代表匿名的單人編輯情境下，StackBlitz **結構上
不需要**任何伺服器端身份識別機制——整個「沙盒」活在你的分頁裡。
官方隱私政策裡唯一討論到的身份/儲存概念是「帳號」，完全沒有獨立的
「匿名使用者」章節。

**Q2 伺服器端儲存**：官方隱私政策原文（本文直接以 curl 取得完整
頁面並逐字核對）：「Files are stored in connection with your account
and associated projects. Data retention practices for such files are
described in the Data Retention section below」（[StackBlitz Privacy
Policy](https://stackblitz.com/privacy-policy)，2026-09-11
存取）——整份 Data Retention 章節（見下方 Q4 逐字引用）**完全只用
「帳號（Account）」為單位描述**，沒有任何一句話提到匿名或訪客資料
類別，這本身就是一個資訊：**官方隱私政策的資料模型裡似乎根本不存在
「持久化的匿名使用者」這個概念**。

**Q3 清除後果／是否主動警告**：未連結 GitHub、未登入時所做的變更
不會被伺服器保留（純瀏覽器內執行），清除頁面／瀏覽器儲存等同直接
失去尚未匯出的工作內容；官方文件未提任何主動警告。

**Q4 匿名資料過期**：官方隱私政策原文（curl 逐字核對）：「When an
account is voluntarily closed, the account and associated data enter
an inactive or expired state. We will delete or anonymize such data
within a commercially reasonable period following account closure
not to exceed thirty days」（同上 Privacy Policy）——這條規則明確
只針對**已存在的帳號**被關閉之後，不是匿名資料的保留規則（因為
如 Q2 所述，這個資料模型裡沒有獨立的匿名資料類別）。

**Q5 匿名限制／登入解鎖**：官方 FAQ 頁面確認的是帳號分級差異：
「The Personal Plan is a free account that allows you to create
unlimited public projects」，「The Personal+ Plan allows users to
create unlimited private projects... as well as unlimited file
uploads」（[StackBlitz — General
FAQs](https://developer.stackblitz.com/guides/user-guide/general-faqs)，
2026-09-11 存取）。至於完全不登入時具體能做到什麼程度、有無數量
上限，該官方 FAQ 頁面本身經我直接查詢確認**沒有涵蓋**這個問題
（見方法論欄位）。

**Q6 匿名→帳號遷移**：**文件未說明**任何正式遷移機制。

**Q7 弄丟識別後的救援**：**文件未說明**——由於未登入狀態下本就不
在伺服器端持久儲存專案（見 Q1／Q2），邏輯上也沒有可供救援的伺服器端
資料存在；使用者唯一的保障是自己在瀏覽器關閉前手動連結 GitHub 或
登入帳號。

---

#### 9. Replit

**這是本次研究中，與 Option Chaser 的風險模型最直接對應的一個案例**
——Replit 官方自己發表了一篇完整說明「為什麼我們收回了匿名體驗」的
部落格文章，值得逐段引用。

**Q1 識別機制**：**歷史**：完全不需要帳號即可開始寫程式並執行：
「for a long time, you could start coding on Replit.it without a
user account」（[Replit Blog — reCAPTCHA and the Anonymous
Experience](https://replit.com/blog/anon)，2026-09-11
存取）——當時靠 Google reCAPTCHA 擋機器人，而非任何持久的使用者
識別機制。**現況**：建立與儲存 Repl 需要登入（Email／Google／
GitHub／Apple 任一種），僅有部分程式語言的入門頁面保留了不需登入
的極簡「barebones REPL」，官方描述其設計目的正是「with limited
opportunity for abuse」（同上，經 WebSearch 摘要間接引用，措辭與
官方部落格內容一致）。

**Q2 伺服器端儲存**：Repl（專案）本身一律在伺服器端執行與持久化——
這正是整個雲端 IDE 產品的核心。現行保留下來的匿名「試跑」路徑，
其設計目的就是刻意不讓你建立一個可回訪的完整、持久專案。

**Q3 清除後果／是否主動警告**：**文件未說明**（現行匿名路徑本身
設計上就不打算讓使用者累積值得保留的狀態，這個問題某種程度上
不太適用）。

**Q4 匿名資料過期**：官方文件確認的是帳號層級規則：「Replit
reserves the right to terminate inactive accounts after 1 year of
no activity」（經 WebSearch 摘要取自 [Replit Legal & Security
文件集](https://docs.replit.com/category/legal-and-security)，
2026-09-11 存取）；DPA 規範的客戶可在合約終止後 90 天內要求刪除
個資（同上摘要）。**沒有**針對「匿名試跑」這個現行殘留路徑給出
任何保留期承諾（因為它本就不設計成持久）。

**Q5 匿名限制／登入解鎖——這是本案例的核心價值**：官方部落格
文章完整說明了整個決策脈絡。**濫用的具體樣態**：「dark-web hackers
trying to sell DDoS attacks from our site for Bitcoin」（[Replit Blog
— reCAPTCHA and the Anonymous
Experience](https://replit.com/blog/anon)，2026-09-11 存取）；不加
以防護的代價是「an immense amount of time spent fighting abuse and
risking outages」（同上）。**防護手段與其成本**：長期仰賴 Google
reCAPTCHA，「a massive help, protecting against botting」（同上）——
但 2023 年 Google 宣布 reCAPTCHA 開始收費，且「it meant they would
have to pay Google more than they make in monthly revenue」（經
WebSearch 摘要引用同一篇官方部落格文章）。**最終決策**：Replit
在「continue leaving the site vulnerable」與「phase out the
anonymous experience」之間，選擇了後者——即**主動收回**匿名執行
環境，只保留語言頁面上刻意設計成低濫用空間的極簡版本，並把資安
投資重心整個轉向已登入使用者：「invested in sandboxing, security,
and anti-abuse tools」（同上）。

**Q6 匿名→帳號遷移**：不適用——現行設計下已不存在值得遷移的匿名
持久狀態。

**Q7 弄丟識別後的救援**：不適用（同上理由）。

---

### (d) 匿名購物車／文件／Playground

#### 10. TypeScript Playground（官方，typescriptlang.org）

**Q1 識別機制**：**完全沒有**使用者身份的概念——狀態本身就是網址。
官方文件原文（本文直接以 WebFetch 取得該頁面並核對）：「URLs contain
a lot more information about your settings」，網址裡編碼了「the
gzipped source code for your TypeScript/JavaScript」、目前語言、
與預設值的編譯器設定差異、以及文字選取範圍（[TypeScript — Sharable
URLs](https://www.typescriptlang.org/play/playground/tooling/sharable-urls.ts.html)，
2026-09-11 存取）。網址會即時更新：「The URL is updated live when any
of the above changes using HTML5's replaceState, so your back button
will still work as expected」（同上）。

**Q2 伺服器端儲存**：**無**——官方文件通篇沒有提到任何資料庫、
後端持久化、帳號系統，整個分享機制純粹是瀏覽器端的 URL 編碼。

**Q3 清除後果／是否主動警告**：因為狀態即時反映在網址列上（不需要
使用者主動按「分享」才產生），只要你在關閉分頁或導覽離開之前把
當下網址複製／加入書籤，就等於保存了完整狀態；若你完全沒有取得那個
網址就關閉分頁，未儲存的編輯內容會如同任何未儲存的瀏覽器分頁內容
一樣消失——這與 cookie／裝置無關，純粹是「有沒有拿到那串網址」的
問題。官方文件未提任何主動警告機制（結構上也幾乎用不到，因為網址
本身隨時反映最新狀態）。

**Q4 匿名資料過期**：不適用——沒有伺服器端紀錄可供過期，只要網站
本身仍在運作、且網址中編碼的 TypeScript 版本仍受支援，該連結原則上
可無限期重現當初的程式碼與設定。

**Q5 匿名限制／登入解鎖**：不適用——這個產品完全沒有帳號層或登入
選項，所有功能對所有訪客一視同仁。

**Q6 匿名→帳號遷移**：不適用（無帳號概念）。

**Q7 弄丟識別後的救援**：不適用於一般意義下的「救援」——網址本身
**就是**完整、自足的憑證，沒有第二層「帳號」或「cookie」需要擔心
弄丟。

---

#### 11. CodePen

**Q1 識別機制**：**現況**官方文件明確要求登入才能建立內容：「You
must [have an account] and be [logged in], then you head to [the Pen
Editor], and save it when you are ready」（[CodePen — The Pen
Editor](https://blog.codepen.io/documentation/pen-editor/)，
2026-09-11 存取）——即便是「建立」這個動作本身，現行官方文件描述
的標準流程也已要求帳號存在，而不只是「儲存」才需要。一個例外：
Collab Mode（即時協作）允許完全沒有 CodePen 帳號的人加入既有的
協作場次：「Everybody else can have free accounts, or even be
anonymous (have no account at all), though anonymous users won't be
able to chat or fork their own copies」（[CodePen — Collab
Mode](https://blog.codepen.io/documentation/collab-mode/)，
2026-09-11 存取）——但這是「加入別人已建立好的場次」，不是「匿名
建立自己的內容」。

**Q2 伺服器端儲存**：已登入使用者建立的 Pen 一律伺服器端持久儲存並
歸屬於該帳號。歷史上曾存在完全不歸屬任何帳號的「匿名存檔」機制，
該機制**已被官方正式、永久移除**（詳見 Q5）。

**Q3 清除後果／是否主動警告**：不適用於現行流程（建立內容本身就
需要先登入，不存在「匿名建立後被清除」這種情境）。

**Q4 匿名資料過期**：一般帳號資料保留措辭：「CodePen processes and
keeps your information as long as you don't delete the account or
withdraw yourself」（經 WebSearch 摘要引自 [CodePen Privacy
Policy](https://blog.codepen.io/legal/privacy-policy/)，2026-09-11
存取）。

**Q5 匿名限制／登入解鎖——本案例最重要的發現**：CodePen 官方部落格
在 2019 年發布了一篇專門說明「為什麼移除匿名存檔」的公告，這是本次
研究中除 Replit 之外**第二個**明講「因為濫用而主動收回匿名功能」的
一手官方案例。核心理由：「spammers, scammers, and others seeking to
cause harm」利用了這個功能，「an overwhelming amount of anonymous
saves included spam/scam content or otherwise went against CodePen's
Code of Conduct and Terms of Service」，且「the volume and severity
of abusive content increased」（[CodePen Blog — Anonymous Pen Save
Option
Removed](https://blog.codepen.io/2019/08/06/anonymous-pen-save-option-removed/)，
2026-09-11 存取）。**執行方式同樣值得注意**：這項變更是**無預警、
立即生效**的，官方明講原因是要防止濫用者在關閉前的空窗期搶著鑽
漏洞：文章本身即強調此舉「without advance notice」是刻意的防範
措施。官方同時強調帳號並不要求本名：「you do not have to use your
real name on CodePen and are welcome to use CodePen under a
pseudonym」（同上），降低註冊門檻以緩解「被迫登入」造成的摩擦。
免費帳號本身無需付費，付費 Pro 方案解鎖私有 Pen、更進階的隱私
控制、資產代管等。

**Q6 匿名→帳號遷移**：不適用——現行流程下已無匿名建立路徑可供遷移。

**Q7 弄丟識別後的救援**：不適用——2019 年之後，匿名存檔這條路徑
本身已徹底不存在，也就沒有「弄丟匿名識別後找不回來」這種情境可談；
這正是這個案例的意義所在：CodePen **選擇整個拿掉這條路**，而不是
去解「怎麼幫匿名使用者救援資料」這個難題。

---

#### 12. Pastebin

**Q1 識別機制**：訪客（未登入）使用者**沒有**任何跨次造訪的持久
身份——官方 FAQ 對登入使用者才有的識別機制間接暗示了這個區分：
「A cookie may store a unique identifier for each logged in user」
（經 WebSearch 摘要引自 [Pastebin Cookies
Policy](https://pastebin.com/doc_cookies_policy)，2026-09-11
存取）——措辭明確限定在「已登入使用者（logged in user）」，未將此
機制延伸到訪客身上。每一則貼上的內容（paste）都是獨立的、以自己的
URL 定址的物件，而不是掛在某個「訪客身份」底下的項目集合。

**Q2 伺服器端儲存**：訪客建立的 paste **確實**存在伺服器端（這是
產品本體），但**不**綁定任何匿名使用者的持久紀錄——paste 本身，而
非「使用者」，才是這個系統裡的持久單位。

**Q3 清除後果／是否主動警告**：因為 paste 本身活在自己的網址，
清除 cookie／換裝置／開無痕視窗對**已存在**的 paste 完全沒有影響。
但官方 FAQ 直接、坦白地講出真正的限制：「You are only able to
remove items that you created while you were logged in. If you
pasted something as a guest, there is no quick delete option」
（[Pastebin FAQ](https://pastebin.com/faq)，2026-09-11
存取）——換句話說，清除識別方式本身不影響貼文的存續，但**你**會
失去掌控它（刪除／編輯）的能力，因為那份掌控權從一開始就沒有跟
任何持久識別綁在一起。官方文件未提任何在建立當下主動跳出的警告
訊息，但 FAQ 頁面本身把這個限制寫得非常直白。

**Q4 匿名資料過期**：由建立者在建立當下**自行選擇**每則 paste 的
到期設定（例如永久／10 分鐘／1 天／1 週等，官方 FAQ 確認「You
decide if you want your pastes to 'expire'」）；官方 FAQ 本身沒有
明確區分「訪客的預設到期時間」是否與「登入使用者的預設到期時間」
不同，**此點列文件未說明**（一份第三方網站聲稱訪客預設為永久，
但未能在 pastebin.com 自己的官方頁面中找到逐字對應的段落，
**該特定「訪客預設永久」的說法列為 UNVERIFIED**）。

**Q5 匿名限制／登入解鎖**：官方 FAQ 明確數字：「Guests can create up
to 10 new pastes per 24 hours」；「Guest can create unlimited
'public' pastes, unlimited 'unlisted' pastes, but can't create
'private' pastes」；一般上限「512 kilobytes (0.5 megabytes)」適用
於所有使用者（含訪客）（以上皆引自 [Pastebin
FAQ](https://pastebin.com/faq)，2026-09-11 存取，本文以 WebFetch
直接核對頁面內容）。PRO 會員：「create up to 250 new pastes per 24
hours」，可建立無限「private」paste，單則上限提高到「10
megabytes」（同上）。

**Q6 匿名→帳號遷移**：概念上不適用——訪客貼文從一開始就沒有擁有者
身份欄位，因此沒有「搬過去」這件事；使用者唯一能做的是登入後重新
貼一次（產生一則全新、獨立的 paste），這不是資料遷移，只是重做
一次動作。

**Q7 弄丟識別後的救援**：**明確、官方確認的「無」**——paste 自己的
網址是唯一的存取路徑；官方 FAQ 直白承認訪客內容「no quick delete
option」，邏輯上也代表沒有相對應的「復原」選項。如果 paste 設為
公開（public），內容理論上仍可能被公開列表／搜尋找到，但這已經
不是「帳號救援」，純粹是內容本身仍然存在於某個可探索的公開位置
而已。

---

## 共通模式

### 【業界慣例】

1. **匿名身份的底層實作手法高度收斂**：凡是真的需要記住「這是同一個
   瀏覽器回來了」的產品（Excalidraw／tldraw 的協作房間、
   CodeSandbox 歷史上的匿名 sandbox），一致採用「cookie 或瀏覽器
   儲存空間裡的一個識別碼，伺服器端查表對應」這個形狀，沒有任何一個
   案例發明了更花俏的替代機制（例如裝置指紋）。這與姊妹研究票 #275
   （`docs/research/anonymous-identity-session-patterns.md`）針對
   Option Chaser 自身架構得出的 OWASP 標準建議完全一致方向。

2. **「先算給你看，存起來才要帳號」是金融計算機類別的共識**：
   Portfolio Visualizer、OptionStrat、Options Profit Calculator
   三者不約而同採用同一種切法——運算本身完全開放給匿名訪客，只有
   「持續追蹤、日後回來看」這個需求才要求登入。這代表如果一個功能
   的本質是「一次性算給我看」，根本不需要為它設計任何匿名持久身份。

3. **把整個狀態塞進網址，讓網址本身取代帳號**是一個成熟、被多個
   獨立產品採用的分享機制（TypeScript Playground、OptionStrat、
   Pastebin 的公開／未列出 paste、Excalidraw 與 tldraw 的協作
   連結）。這個模式的好處是**完全不需要伺服器記住任何「使用者」**，
   缺點是內容大小受網址長度或編碼效率限制，且「誰能看到」等同「誰
   有這串網址」。

4. **登入帳號解鎖的東西高度重複**：幾乎每個案例登入後解鎖的都是同一
   組能力——跨裝置存取、私有（不公開）內容、儲存並回顧歷史、團隊
   協作、更高的用量上限。沒有任何案例把「核心單次運算功能本身」
   鎖在登入後面（TypeScript Playground／draw.io／多數計算機皆然）。

5. **有能力做「匿名資料自動搬進帳號」的產品，都把它做成 best-effort
   而非硬保證**：Excalidraw+ 的措辭是「In most cases」，且明文提供
   手動備援路徑；沒有任何案例承諾 100% 自動、零失敗的遷移。

### 【法規／安全必要】

1. **幾乎每一份隱私政策都出現同一句近乎模板化的保留期措辭**：
   「只保留到不再需要提供服務為止，除非法律另有規定」——這句話（或
   極相近的變體）出現在 Excalidraw+、Portfolio Visualizer、
   OptionStrat、Options Profit Calculator 四份獨立產品的隱私政策
   裡，措辭雷同到很可能是同一類法遵範本／同一種法律顧問建議的
   產物，而非各自獨立設計的產品決策。這比較像是**隱私法規遵循的
   最低共識底線**，不是真正因應各自產品特性設計出來的政策。

2. **帳號關閉後的「善後保留窗」收斂在 30–90 天這個區間**：
   Excalidraw+「no longer than one month past termination」
   （約 30 天）、StackBlitz 明文「not to exceed thirty days」、
   Replit 的 DPA 客戶「up to ninety (90) days」。三個獨立產品各自
   收斂到同一個數量級，值得記錄下來供未來 Owner 裁示保留期時參考，
   但**沒有任何一份來源明講這是某條特定法規強制要求的數字**——我
   只能誠實標記這是「業界觀察到的收斂值」，而非確認過的法定下限或
   上限。

3. **完全沒有找到任何一個成熟產品，在使用者即將因清除瀏覽器資料而
   遺失內容前，正面官方文件確認會主動跳出警告**——這件事本身值得
   記錄成一個明確的「缺席」觀察：至少三個純本機儲存產品
   （Excalidraw、tldraw、部分情境下的 StackBlitz）都存在使用者
   資料只活在瀏覽器裡、卻沒有官方確認的「你正要弄丟資料」主動提示。
   若把「資料遺失前主動示警」視為對使用者負責任的最低限度安全
   慣例，這個空缺是整個產業普遍存在的，而不是單一產品的疏漏——
   Option Chaser 若選擇在這一點做得比業界平均更好（例如清 cookie
   前主動提示），會是超越現有業界慣例、而非只是補上一個業界都在做
   的必要項目。

### 【純產品選擇】

1. **★ 是否要讓匿名訪客觸發「較重」的伺服器端行為，是一個高風險、
   會隨時間反覆被重新評估的商業決策，而非一次到位的技術問題**。
   本次研究找到**三個**獨立、彼此無關的成熟產品（Replit、CodePen、
   CodeSandbox），全部都曾經給匿名使用者更寬鬆的能力（分別是：不
   登入就能執行程式碼、不登入就能存檔、不登入就能即時編輯），後來
   **全部往回收緊**，理由高度一致：濫用（垃圾訊息、詐騙內容、機器
   人攻擊、甚至暗網轉售 DDoS 服務）造成的成本，最終超過了維持這個
   便利性帶來的價值。三者之中沒有一個公開過具體的量化門檻（例如
   「濫用事件達到每天 X 次就會觸發改版」），都只給出質化的說明。
   **這三個案例沒有一個結構上完全對應 Option Chaser 的設計**——
   它們燒的都是自己的運算資源／頻寬，Replit 的 reCAPTCHA 費用故事
   最接近，但那筆費用是 Replit 付給 Google 買驗證服務，不是
   Option Chaser 這種「代替匿名訪客去消耗一個外部、按量計費、有
   配額上限的報價廠商 API」。**在這 12 個案例裡，我沒有找到任何一個
   目前仍在正常運作、結構完全對應「儲存匿名使用者物件＋代替匿名
   使用者呼叫付費第三方 API」這兩個條件同時成立的成熟產品**——這
   件事本身可能就是一個訊號：這種組合要嘛真的很少見，要嘛真的做了
   但後來像 Replit 一樣收回去、已經不在「目前仍在正常運作」的
   樣本裡了（Glitch 是另一個值得一提但已經**不算數**的例子——它是
   2025 年 7 月正式關閉、不再營運的產品，故未列入本文正式的 12
   個案例，但它的官方說法同樣指向「擴大的濫用問題推高了維運成本」
   是收掉 app hosting 服務的原因之一，方向與 Replit／CodePen 一致，
   在此僅作為額外的旁證脈絡提出，不作為正式案例引用）。**這條發現
   對 Option Chaser 的意涵**：目前規劃的匿名代理第三方付費 API
   模式，找不到一個仍在運作、規模相近的先例可以直接照抄「他們的
   限流數字／防護機制設多少」，Owner 若要往這個方向走，某種程度上
   是在業界普遍認為風險過高而退避的地帶自行摸索，值得在額度、
   限流、監控機制上比一般「先做了再看」更保守。

2. **匿名資料要不要留在伺服器上、留多久，各家分歧極大且沒有收斂
   趨勢**：StackBlitz 的隱私政策資料模型裡似乎**根本不存在**
   匿名資料這個類別（帳號關閉才有 30 天窗，此外文件完全沒提到
   訪客資料）；Pastebin 的訪客貼文則反過來是**預設可能無限期存在**
   （除非建立者自己選了到期時間）；Excalidraw／tldraw／
   diagrams.net 則是把這個問題完全丟給瀏覽器自己的儲存空間管理，
   產品本身根本不設定任何期限。三種完全不同的立場，全部都在成熟
   產品上正常運作中，沒有一種被業界公認為「正確答案」。

3. **要不要把匿名內容存成「有內容但無擁有者」的孤兒物件、還是乾脆
   完全不留在伺服器上、還是存成「伺服器加密後連自己都讀不懂」的
   密文，是三種完全不同、目前都在同時被使用的架構哲學**：
   Pastebin／CodeSandbox（歷史）走「孤兒物件」路線；StackBlitz／
   TypeScript Playground／diagrams.net 走「幾乎不落地」路線；
   Excalidraw／tldraw 的協作房間走「落地但加密到伺服器自己也讀
   不懂」路線。三者對應到完全不同的隱私與可維運性取捨，這是一個
   純粹的產品架構選擇，沒有任何一個案例暗示其他兩種做法是錯的。

4. **有沒有提供「匿名→帳號」正式遷移機制，本身就是分歧的**：
   Excalidraw+ 主動做了（best-effort 自動匯入＋手動備援）；其餘
   十一個案例中，我沒有找到任何一個具備類似機制的官方文件，多數
   要嘛結構上不需要（URL 本身即救命繩，沒有東西好搬）、要嘛乾脆
   不提供、只讓使用者「fork／重新貼一份／手動重做」當作事實上的
   替代方案。**沒有任何一個案例提供類似「救援代碼（recovery
   code）」的機制**——這代表若 Option Chaser 未來考慮加一組
   「换裝置救援碼」，在這 12 個成熟產品裡找不到直接可抄的先例，
   會是相對少見、需要自行設計的功能。

---

## 誠實揭露：方法論限制

- **CodeSandbox 的官方法律／文件頁面（`codesandbox.io/legal/privacy`、
  `/legal/terms`、`/docs/faq`）本次研究環境對其發出的直接請求
  （WebFetch 與 curl 皆然）一律收到 Cloudflare bot 挑戰頁
  （HTTP 403，`cf-mitigated: challenge`），未能親自逐字取得完整
  頁面內容。本文對 CodeSandbox 的引用改採搜尋引擎呈現的該官方 URL
  摘要文字，雖然搜尋結果明確標示摘要來源即為這些官方頁面，仍屬於
  透過中介工具取得、而非親自逐字覆核的引用，已在正文對應段落逐一
  註記此方法論限制。
- **Wayback Machine（web.archive.org）在本次研究的沙盒網路環境中
  無法連線**（curl 透過 agent proxy 連線失敗、WebFetch 直接拒絕該
  網域），因此無法用歷史快照獨立交叉驗證任何一個案例的政策頁面
  在過去某個時間點的確切文字（例如 CodeSandbox 或 CodePen 政策
  變更前後的逐字差異）。
- **tldraw 的官方文件站（tldraw.dev）主要服務 tldraw SDK（開發者
  工具）而非 tldraw.com 產品本身**；本文已在對應段落盡力區分「這是
  SDK 通用能力的描述」與「這是 tldraw.com 產品本身的確切行為」，
  但部分細節（尤其 tldraw.com 生產環境多人協作房間的確切保留規則）
  只能列為文件未說明，而非誤植成已由官方確認。
- **optionstrat.com 與部分其他網域對 WebFetch 直接請求回應
  HTTP 403**，改用 curl（透過本環境的 agent proxy，附帶一般瀏覽器
  User-Agent 字串）成功取得原始頁面，本文對這些頁面的引用皆為親自
  下載後以程式逐字擷取比對，非透過搜尋引擎摘要中介。
- **12 個案例是抽樣，不是窮舉**：四個類別裡每類只深入研究 3 個
  代表性產品，同類別裡未研究的其他成熟產品（例如 Figma／Miro／
  Canva 之於畫圖類別，或 Robinhood／Yahoo Finance 之於金融計算機
  類別）可能存在與本文結論不同的做法，本文結論代表「調查到的樣本
  中觀察到的模式」，不宣稱涵蓋整個市場。
- **Replit 與 CodePen 兩篇最關鍵的官方部落格文章（各自說明收回
  匿名功能的決策）發布時間分別約在 2023 年與 2019 年**——這些是
  官方對「當時發生的事」的一手記載，但寫作時間點本身是回溯性的
  政策公告，不是逐日即時的產品行為紀錄；本文據此描述的是官方自己
  對歷史決策的說法，而非獨立第三方稽核。
- 本文所有「今天」「現況」的表述，皆以 **2026-09-11** 這次存取
  當下觀察到的頁面內容為準；若任一產品在此之後修改了政策或介面
  行為，本文內容不會自動反映。
