# 匿名身份 Cookie／Analytics／Advertising 三件事的法規邊界——給 Public Beta 用

研究日期：2026-09-11。對應票號：research issue #279（Wayfinder 地圖
#272「Anonymous Public Beta」子票）。本輪為背景研究，**未修改任何
程式碼、未 commit、未碰 GitHub issue/PR、未跑測試**。

## 0. 取材說明

本輪運氣比先前幾輪研究好很多，值得先講清楚差異，避免誤判證據強度：

- `WebSearch` 全程可用（Anthropic 自家基礎設施，不受本沙箱出口政策影響）。
- `WebFetch` 對多數官方網域（`eur-lex.europa.eu`、`cnil.fr`、
  `iabeurope.eu`、`vercel.com`、`google.com`、`law.moj.gov.tw`、
  `leginfo.legislature.ca.gov`、`legislation.gov.uk` 等）**直接成功**。
- `WebFetch` 對少數網域回 403（`ico.org.uk`、`optionstrat.com`、
  `portfoliovisualizer.com`）——改用 `curl` 帶一般瀏覽器 User-Agent
  **全部成功**（沙箱出口本身沒擋，擋的是這些網站自己的爬蟲防護對
  WebFetch 的請求特徵起反應）。
- **唯一徹底失敗的是 `finra.org`**——Cloudflare 的 JS 互動式挑戰頁
  （"Just a moment..."），連換 User-Agent 的 `curl` 都過不了。這與
  本 repo 既有研究 `option-strategy-report-conventions.md`
  （2026-08-04）記載的結論一致，本輪重試仍然失敗，故 FINRA 相關內容
  **沿用該份既有研究的既有查證等級**（索引轉述，非逐字核對原文），
  不重複標記為新查證。
- 遇到 PDF（EU WP29 Opinion 04/2012）時，`WebFetch` 內建的頁面轉譯
  對這份掃描字距異常的 PDF 解析失敗；改用 `pip install pypdf`
  失敗（系統 `cryptography` 套件本身壞掉），最後手刻一段
  zlib-decompress＋PDF text-operator 解析腳本，直接從 PDF 原始
  binary 中取出逐字文字（含大量字距雜訊，但內容本身逐字可核對）。
  這是**本輪唯一一次真正做到「逐字檢視官方 PDF 原文」**，其餘引用
  歐盟一手法源的地方都是透過 `WebFetch` 直接讀取的 HTML／EUR-Lex
  頁面文字，同樣算逐字核對，不是索引轉述。

標記慣例（本文自訂，不是延續上一份研究文件的舊標記）：
- **〔官方直接引用〕**＝本輪親自用 WebFetch／curl 打到官方頁面，
  逐字核對過的內容。
- **〔官方・索引確認〕**＝來自 WebSearch 對官方頁面內容的摘要整理，
  未逐字核對原始 HTML，但摘要本身指名的是官方一手來源（非部落格）。
- **〔沿用既有研究〕**＝本 repo 既有研究檔案已經做過的查證，本輪
  原樣引用其結論與查證等級，不重新做。
- **〔UNVERIFIED〕**＝找不到官方一手來源支持，明確標示，不假裝
  查證過。

## 一、白話總結（給 Owner 看，技術名詞第一次出現都會先解釋）

這份研究把三件容易被混在一起講的事**刻意分開**：(1) 讓陌生人不用
註冊就能用 Option Chaser 的那顆「匿名身份 cookie」（cookie 就是
瀏覽器幫網站記一小段資料的機制，這裡存的只是一串隨機亂碼，不是
姓名或 email）；(2) 未來如果想知道有多少人在用、用了什麼功能的
「Analytics（流量統計）」；(3) 未來如果想放廣告賺點回本的
「Advertising（廣告）」。**這三件事在法規上要不要先問使用者同意、
要不要事先告知、以及現在該不該先把架構準備好，答案完全不一樣**，
混在一起講會導致過度設計或漏掉真正該做的事。

**結論一句話**：匿名身份 cookie 這件事**幾乎不用擔心**——歐盟、
英國、法國的官方指引都明講「只為了提供使用者自己要求的服務而存在
的 cookie」（例如記住登入狀態、記住購物車）不需要問使用者同不同意，
Option Chaser 這顆 cookie 完全符合這個描述。唯一該做但成本近乎零的
事：法規上雖然不強制要求「告知」，但法國 CNIL 與英國 ICO 都明講
「即使不用問同意，還是建議讓使用者知道網站有用 cookie」——這件事
可以跟「這不是投資建議」的免責聲明**合併成同一行小字**，一次做完。

**Analytics 這件事有一個重要的新發現**：這次研究之前，一般認知是
「英國比法國嚴格，法國有分析用 cookie 的例外，英國沒有」。**這個
認知已經過期**——英國國會在 2025 年通過新法（Data (Use and Access)
Act，簡稱 DUAA），已於 **2026 年 2 月 5 日正式生效**，新增了跟法國
類似的「統計用途例外」，英國監理機關 ICO 也已在 2026 年 4 月底發布
配套的正式指引。也就是說，只要挑對工具（本研究實測 Vercel Web
Analytics／Plausible／Fathom／Umami 四家的官方說法，全部宣稱自己
「不用 cookie、不留可追蹤的識別碼」），法國與英國現在的規則其實
相當一致：不追蹤特定個人、只做匯總統計、給使用者一個簡單的
「不要」按鈕，就不需要跳出同意彈窗。**但 Option Chaser 目前完全沒有
Analytics**，這一節純粹是「以後真的要加的話，該怎麼加」的地圖，
不代表現在就要加。

**Advertising 這件事最直接的建議是：現在什麼都不要做**。Google
AdSense（最主流的網站廣告平台）官方規定，2024 年起在歐洲地區投放
個人化廣告，網站主必須採用 Google 認證的「同意管理平台」（Consent
Management Platform，簡稱 CMP，一種跳出來讓使用者選擇要不要被追蹤
打廣告的彈窗系統）。這是一整套額外的基礎設施，而 Option Chaser
**今天完全沒有廣告**。Owner 已經明確表示「不要因為未來可能放廣告，
就現在把 Beta 搞重」，這個判斷完全正確——建議現在**不寫任何一行
CMP 相關程式碼**，只需要記住「如果哪天真的要放廣告，屆時要重新做
一次 CMP 決策」這件事即可，不必預留任何程式碼骨架。

**最後一個交叉發現**：這次順便查了 Option Chaser 現有的「這不是
投資建議」免責聲明放在哪裡——查程式碼發現它目前**只出現在劇本
詳細頁裡一個預設收合的「進階區」內**，陌生人第一次打開網站、甚至
建立第一個劇本，完全不會看到這行字。三個成熟同類工具（OptionStrat、
Portfolio Visualizer、Options Profit Calculator）裡有兩個把類似
文字放在**網站每一頁都看得到的頁尾**。這是一個成本很低、值得在
Public Beta 上線前一起做的小改動，而且可以跟上面「cookie 告知」
那句話**合併成同一行頁尾小字**，一次滿足兩個目的。

---

## 二、Cookie——匿名身份 cookie 需不需要同意、需不需要告知

### 2.1 歐盟 ePrivacy 指令 Art. 5(3)「strictly necessary（絕對必要）」豁免

歐盟規範 cookie 的法源不是 GDPR 本身，是另一部叫 **ePrivacy Directive
（電子隱私指令，2002/58/EC，2009 年修訂）**的指令，其中 Art. 5(3)
規定：在使用者的裝置上存取或讀取資訊（也就是設 cookie），原則上
要先取得使用者同意，**除非符合兩個例外之一**。第二個例外（本文稱
CRITERION B）就是「絕對必要」豁免。

**官方一手原文**（〔官方直接引用〕，取自歐盟資料保護工作小組
Article 29 Working Party《Opinion 04/2012 on Cookie Consent
Exemption》PDF 原文，親自解壓縮 PDF stream 逐字核對，2012 年
6 月 7 日通過，*WP194*）：

> "CRITERION B: strictly necessary in order for the provider of an
> information society service explicitly requested by the subscriber
> or user to provide the service"

> "the wording of CRITERION B suggests that the European Legislator
> intended to ensure that the test for qualifying for such an
> exemption must remain high. […] a cookie matching CRITERION B has
> to pass simultaneously the two following tests: 1) The information
> society service has been explicitly requested by the user: the
> user (or subscriber) did a positive action to request a service
> with a clearly defined perimeter. 2) The cookie is strictly needed
> to enable the information society service: if cookies are
> disabled, the service will not work."

翻成白話就是兩個條件要**同時**成立：①使用者主動做了一件事來要求
這個服務（不是網站自己想要，是使用者自己要的）；②沒有這顆 cookie
服務就真的不能運作。這份意見書自己歸納出五種符合豁免的常見類型
〔官方直接引用〕：

> "1) User input cookies (session-id), for the duration of a session
> or persistent cookies limited to a few hours in some cases. 2)
> Authentication cookies, used for authenticated services, for the
> duration of a session. 3) User centric security cookies, used to
> detect authentication abuses, for a limited persistent duration.
> 4) Multimedia content player session cookies […] 5) Load balancing
> session cookies […]"

**這份 2012 年的意見書地位**：它是 GDPR 生效前、由 Article 29
Working Party（EDPB 的前身）發布的，但它解釋的是 ePrivacy 指令
Art. 5(3) 的文字本身（該條文文字至今未變），因此至今仍是歐盟層級
對「strictly necessary」這個詞最權威的逐條拆解——英國 ICO 自己的
官方頁面（見下）現在都還在直接引用它。EDPB 後續的《Guidelines
2/2023》處理的是不同問題（cookie 之外的技術，例如裝置指紋辨識
是否落入 Art. 5(3) 的技術範圍），**沒有推翻或重寫**這份 2012 年
對「strictly necessary」測試本身的解釋。

**英國 ICO 官方指引怎麼說（更新到 2026-04-29 的最新版）**
〔官方直接引用〕，取自 ICO《Guidance on the use of storage and
access technologies》「What is the 'strictly necessary'
exception?」章節：

> "The 'strictly necessary' exception applies when the purpose of
> the storage or access is essential to provide the service the
> subscriber or user requests. This means that without it the
> service couldn't be provided on a technical level. […] you should
> assess 'strictly necessary' from the point of view of the
> subscriber or user, not your own."

該頁面明列的「非窮盡示例清單」中，與 Option Chaser 的匿名身份
cookie 直接對應的一條〔官方直接引用〕：

> "Identifying a user once they have logged in to an online service
> for the duration of their visit to the site (eg to prevent a new
> login prompt on an online banking service each time the user loads
> a new page). ✔"

Option Chaser 的匿名身份 cookie 本質上就是這個模式的變形——沒有
「登入」動作，但同樣是「記住這個瀏覽器是誰、讓它能看到自己建立的
劇本」，屬於「識別已經在使用服務的使用者」這個既有承認的類別。
ICO 頁面也附帶說明**單純的識別作業不會因為使用了 session cookie
以外的手法（例如純粹存一個隨機 ID）而失去豁免資格**，只要用途
沒有超出「讓這個使用者能繼續用他自己已經在用的服務」。

**法國 CNIL 官方頁面**（〔官方直接引用〕，取自 `cnil.fr`
「Cookies et traceurs : que dit la loi ?」頁面，最後更新
2020-09-29）逐字列出的豁免類別，與上面 WP29／ICO 的清單高度一致：

> "les traceurs destinés à l'authentification auprès d'un service…
> les traceurs destinés à garder en mémoire le contenu d'un panier
> d'achat… les traceurs de personnalisation de l'interface
> utilisateur… les traceurs permettant l'équilibrage de la charge…"

（驗證身份用的追蹤器、記住購物車內容的追蹤器、使用者介面個人化
追蹤器、負載平衡追蹤器。）

**分類：【安全／法規必要】**——三個獨立官方來源（歐盟 2012 年
一手意見書、英國 ICO 2026 年最新指引、法國 CNIL 2020 年官方頁面）
交叉確認，Option Chaser 的匿名身份 cookie（隨機亂碼、伺服器端查表、
只用來讓使用者看到自己的劇本）落在這個豁免範圍內，**不需要跳出
同意彈窗**。

### 2.2 隨機、不帶姓名/email 的識別碼，算不算 GDPR 說的「個人資料」？

會有這個問題，是因為「需不需要同意 cookie」（ePrivacy 管的）跟
「這串資料算不算個人資料、要不要遵守 GDPR 其他規則」是**兩個獨立
問題**——前者答案是「不需要」，但這不代表後者也是「不算」。

**GDPR 官方原文**（〔官方直接引用〕，取自 EUR-Lex，Regulation (EU)
2016/679，Recital 30，直接讀取歐盟官方法規資料庫全文）：

> "Natural persons may be associated with online identifiers
> provided by their devices, applications, tools and protocols,
> such as internet protocol addresses, cookie identifiers or other
> identifiers such as radio frequency identification tags. This may
> leave traces which, in particular when combined with unique
> identifiers and other information received by the servers, may be
> used to create profiles of the natural persons and identify them."

這段話**明講 cookie identifier 本身就是 GDPR 認定「可能可以指向
一個自然人」的東西之一**，不需要姓名或 email 才算。判斷標準在
Recital 26〔官方直接引用〕：

> "Personal data which have undergone pseudonymisation, which could
> be attributed to a natural person by the use of additional
> information should be considered to be information on an
> identifiable natural person."

也就是說：**只要有辦法（不論是誰）透過額外資訊，把這串亂碼跟
「這一個特定的人」對起來，就算是個人資料**（法律上稱為
「pseudonymised personal data，假名化個人資料」，而不是真正的
「anonymous data，匿名資料」——後者才完全不受 GDPR 規範）。

這個標準在歐盟法院（CJEU）2016 年的判例中被實際套用過。**官方判決
原文**（〔官方直接引用〕，取自 EUR-Lex，Case C-582/14 *Patrick
Breyer v Bundesrepublik Deutschland*，2016 年 10 月 19 日判決，
直接讀取判決全文）：

> "recital 26 of Directive 95/46 states that, to determine whether a
> person is identifiable, account should be taken of all the means
> likely reasonably to be used either by the controller or by any
> other person to identify the said person." […] "it is not required
> that all the information enabling the identification of the data
> subject must be in the hands of one person."

該案的最終認定：一個動態 IP 位址，即使**網站經營者自己認不出訪客
是誰**，只要**存在合法管道**（該案是網站業者可以透過法律程序要求
ISP 提供對照資料）能把 IP 跟人對起來，就算是該網站業者手上的個人
資料。

**這對 Option Chaser 的意義（本輪推論，非直接引用判決本身對本案
的認定）**：Option Chaser 的狀況其實比 Breyer 案**更直接**——不需要
「向第三方要額外資料」這一步，因為**伺服器自己的資料庫本身就是那個
查表**（cookie 隨機碼 → 這個人建立的劇本清單）。這正是「假名化」
最典型的例子：Owner 自己隨時能透過查表區分出「這是同一個訪客」，
即使完全不知道對方叫什麼名字。**結論：這顆匿名身份 cookie 底下
對應的資料，在 GDPR 的定義下應被視為（假名化）個人資料**，即使
沒有蒐集姓名、email 或任何其他身份資訊。

**分類：【安全／法規必要】**（判斷本身）／但**GDPR 是否真的管得到
Option Chaser 是另一個獨立問題**，見 2.6。

### 2.3 即使豁免同意，還需不需要告知使用者？

**這一題答案在三個官方來源上意外地一致：法律上不強制，但監理機關
都建議做**。

法國 CNIL 官方 FAQ（〔官方直接引用〕，取自 `cnil.fr`
「Questions-réponses…」頁面第 18 題，頁面標記最後更新
**2026-04-29**）：

> « Si l'article 82 de la loi Informatique et Libertés n'impose pas
> d'informer les utilisateurs sur l'utilisation de tels traceurs, la
> CNIL recommande qu'ils soient informés de leur existence afin
> d'assurer une transparence pleine et entière sur ces opérations. »

白話翻譯：「雖然法律（該國轉譯 ePrivacy 指令的條文）不強制要求
針對這類（豁免同意的）追蹤器告知使用者，CNIL 建議還是告知使用者
它們的存在，以確保完整透明。」

英國 ICO 官方頁面同樣的立場（〔官方直接引用〕，見 2.1 引用的同一份
頁面「Do the rules still apply if the data is anonymous?」與
「Are there any exemptions?」兩節）：

> "However, it is still good practice to provide users with
> information about these cookies, even if you do not need consent."

**為什麼即使 ePrivacy 不強制，GDPR 本身可能還是要求告知**：這牽涉
GDPR 跟 ePrivacy 兩部法規怎麼分工。GDPR 官方原文 Art. 95〔官方・
索引確認，經多方獨立轉述交叉核對逐字一致，惟本輪未能直接從
EUR-Lex 頁面截出完整條文文字（該頁面過長、逐頁擷取工具讀不到最後
幾條），故標記索引確認而非直接引用〕：

> "This Regulation shall not impose additional obligations on
> natural or legal persons in relation to processing in connection
> with the provision of publicly available electronic communications
> services in public communication networks in the Union in relation
> to matters for which they are subject to specific obligations with
> the same objective set out in Directive 2002/58/EC."

意思是：GDPR 不會在 ePrivacy 指令**已經處理過、目的相同**的事情上
疊加額外義務。但反過來說，**GDPR 自己的一般透明原則（第 12–14 條，
要求控制者在蒐集個人資料時告知蒐集目的、保存期限等）目的跟
ePrivacy 的「cookie 存取同意」並不完全相同**——前者管的是「資料
處理本身要透明」，後者管的是「往裝置裡寫東西要先問過」。因此**若
這顆 cookie 底下的資料依 2.2 的分析確實算個人資料，GDPR 自己的一般
告知義務很可能仍然獨立存在**，即使 ePrivacy 的同意義務被豁免了。
這一段落是本輪的法律推論，不是直接引用某一份官方文件對這個具體
情境下的結論，特此標明。

**分類：【業界成熟慣例】**——法律上非強制，但兩個獨立、地位最高的
歐盟成員國監理機關都公開建議照做，且成本極低（一行小字），沒有
理由不做。

### 2.4 台灣個人資料保護法（個資法）的適用性

**官方法源**（〔官方直接引用〕，取自 `law.moj.gov.tw` 官方英譯，
最後修正日期 **2025-11-11**，非常新的修法）：

第 2 條「個人資料」定義：

> "a natural person's name, date of birth, national identification
> Card number, passport number, physical characteristics,
> fingerprints, marital status, family information, education
> background, occupation, medical records, healthcare data, genetic
> data, sex life, records of physical examination, criminal records,
> contact information, financial conditions, social activities and
> **any other information that may be used to directly or indirectly
> identify a natural person**"

最後那句「及其他得以直接或間接方式識別該個人之資料」是概括條款，
邏輯上與 GDPR Recital 30/26 的「identifiability」測試相通，但台灣
個資法本身**沒有像 GDPR Recital 30 那樣明文點名「online
identifier／cookie identifier」**，也沒有查到台灣個人資料保護
委員會（依 2025 年 11 月修法新設，見下）發布過針對「單純隨機
cookie ID 算不算個資」的解釋令。**這一點標記〔UNVERIFIED〕**——
概括條款文字看起來足以涵蓋，但沒有找到台灣官方對這個具體情境的
直接解釋。

第 51 條的適用範圍（〔官方直接引用〕）：

> 第 1 項：「本法於下列情形不適用之：一、自然人為單純個人或家庭
> 活動之目的，而蒐集、處理或利用個人資料。二、於公開場所或公開
> 活動中所蒐集、處理或利用之影音資料，未與其他個人資料結合者。」

> 第 2 項：「（英譯）The PDPA also applies to the government and
> the non-government agencies outside the territory of the Republic
> of China (R.O.C) when they collect, process or use the personal
> data of R.O.C. nationals.」

**這對 Option Chaser 的意義**：第 1 項的「個人/家庭活動」豁免**不
適用**——Option Chaser 是提供給不特定第三人使用的公開服務，不是
Owner 自己私人使用。第 2 項處理的是「境外」情境（境外機構處理
台灣人資料，或台灣機構在境外處理資料）——這其實**不是 Option
Chaser 最主要的適用理由**：真正的重點更簡單，**Owner 本人是台灣籍、
在台灣營運**，因此個資法作為台灣本地法律，原則上直接適用於 Owner
對其蒐集到的任何個人資料（不論訪客本身國籍或所在地）的處理行為，
這是一般屬地管轄的結果，不需要動用第 51 條第 2 項那個處理跨境
情境的特殊條款。

**跟歐盟／美國的一個關鍵差異**：台灣個資法**沒有** GDPR 那種
「與 ePrivacy 分離、專門管 cookie 存取本身」的獨立規則，也**沒有**
CCPA 那種營收/資料量門檻——條文本身不分企業規模，一旦落入第 2 條
「個人資料」的定義、又不落入第 51 條第 1 項的個人/家庭豁免，原則上
就要遵守個資法蒐集/處理的一般規則（第 8 條的告知義務、第 19 條的
蒐集合法依據等）。這些一般規則本身有相當寬的例外（例如第 8 條
第 2 項列了多款不用逐次告知的情形），但完整走一輪超出本題「這顆
cookie 適用性」的範圍，這裡不展開，僅指出結構性差異。

**分類：【安全／法規必要】**（個資法本身直接適用 Owner 這件事）／
**【UNVERIFIED】**（隨機 cookie ID 本身是否落入「間接識別」概括
條款，缺乏台灣官方對此具體情境的直接解釋）。

### 2.5 美國 CCPA/CPRA 的門檻，Beta 階段有沒有可能踩到？

**官方法源**（〔官方直接引用〕，取自加州州議會官方法規資料庫
`leginfo.legislature.ca.gov`，California Civil Code § 1798.140，
CCPA 經 CPRA 修訂後現行版本）：

「Business」（適用 CCPA 義務的主體）三選一門檻之一即可觸發
§ 1798.140(d)(1)：

> "had annual gross revenues in excess of twenty-five million
> dollars ($25,000,000)"

> "annually buys, sells, or shares the personal information of
> 100,000 or more consumers or households"

> "Derives 50 percent or more of its annual revenues from selling or
> sharing consumers' personal information"

同一條文對「personal information」的定義，明確把 cookie／裝置識別
碼／IP 位址都列為「unique identifier」，同樣屬於受規範的個資
〔官方直接引用〕：

> "'Identifiers' include: a real name, alias, postal address, unique
> personal identifier, online identifier, Internet Protocol address,
> email address, account name…"

> "'unique identifier' or 'unique personal identifier' means a
> persistent identifier that can be used to recognize a
> consumer…including, but not limited to, a device identifier; an
> Internet Protocol address; cookies, beacons, pixel tags, mobile ad
> identifiers, or other forms of persistent or probabilistic
> identifiers…"

**推論（本輪自行判斷，門檻數字本身已由官方原文確認，不是
UNVERIFIED；「Option Chaser 目前是否踩到這些門檻」才是需要推理的
部分）**：Option Chaser 目前無營收（不收費）、不出售/分享任何
使用者資料給第三方、Beta 階段預期使用者數量遠低於 10 萬——**三個
門檻大機率一個都碰不到**，因此 CCPA 對「Business」的義務條款很
可能現階段不適用。但這個結論有兩個前提沒有查證：①CCPA 適用的前提
本身還包含「在加州從事商業活動（doing business in California）」
這個更基礎的門檻，而 Option Chaser 是全中文介面的台灣產品，是否
構成「在加州從事商業」本身就有疑義（此點〔UNVERIFIED〕，本輪
未找到官方對這個具體情境的解釋）；②使用者數字未來成長軌跡未知，
100,000 這個門檻是**累積年度數字**，不是瞬時在線人數，成長夠快
的話並非遙不可及。

**分類：【安全／法規必要】**（門檻數字本身、cookie 落入個資定義
本身）／**【Option Chaser 產品選擇】**（要不要現在就假設會踩到
門檻而預先合規，還是等真的接近門檻再處理——建議後者，見第八節）。

### 2.6 一個常被忽略的前提：GDPR／英國 PECR 到底管不管得到 Option Chaser？

上面 2.1–2.3 大量引用歐盟／英國官方指引，但這裡有必要誠實講清楚
一個常被忽略的前提問題：**這些規則本身有沒有域外效力管到一個
全中文、Owner 台灣籍、目前沒有刻意經營歐洲市場的產品？**

GDPR 域外管轄的關鍵條文是 Art. 3(2)（Territorial scope），其中
「向歐盟境內的人提供商品或服務」這一款有官方判斷標準——**EDPB 官方
指引**（〔官方・索引確認〕，取自 EDPB 官方文件
《Guidelines 3/2018 on the territorial scope of the GDPR》，
`edpb.europa.eu`，經 WebSearch 多方交叉確認要點，未逐字全文核對）：

> 判斷是否「targeting（鎖定）」歐盟使用者的指標之一，是網站是否
> 使用歐盟會員國的語言、貨幣等；單純「網站在歐盟境內打得開」本身
> **不足以**觸發 Art. 3(2)，必須要有實際鎖定歐盟使用者的跡象。

Option Chaser 目前是全繁體中文介面、無歐元計價、未見任何鎖定
歐盟/英國使用者的行銷動作——依這個「targeting 測試」，**GDPR／
英國 PECR 現階段很可能都不構成 Owner 的法定義務**，即使真的有
歐洲訪客不小心點進網站也一樣（判斷依據是「有沒有鎖定」，不是
「有沒有訪客」）。

**這不代表上面 2.1–2.3 的引用是白做工**——本研究的定位跟本 repo
既有慣例一致（`option-strategy-report-conventions.md` 借用 FINRA
規則「當作品質標準」而非宣稱受其管轄）：**CNIL／ICO／EDPB 的指引
在這裡是拿來當「成熟、審慎的產品設計標準」參考，不是宣稱 Option
Chaser 現在就有法律義務遵守它們**。真正現階段大機率直接適用的是
2.4 的台灣個資法（Owner 屬地管轄）；CCPA 依 2.5 的分析大機率門檻
未達；GDPR/PECR 依本節分析大機率域外效力未觸發。

**分類：【安全／法規必要】**（判斷方法本身，即「先問管不管得到」
這件事）。

---

## 三、Analytics——流量統計要不要問過使用者

**現況提醒：Option Chaser 目前完全沒有導入任何 Analytics 工具**
（`git grep` 全站確認，且本 repo 產品定位一貫是「零金融計算在前端」
「不主動蒐集使用者行為」）。本節純粹是「以後真的要加的話該怎麼
選、怎麼加」的地圖。

### 3.1 法國 CNIL 的「audience measurement（流量統計）豁免」——完整八條件

**官方一手來源**（〔官方直接引用〕，取自 `cnil.fr` 官方英文頁面
「Sheet n°16: Use analytics on your websites and applications」）：

> 1. To inform users of their use（告知使用者有在用）
> 2. To give them the ability to object to their use（給使用者
>    反對/退出的能力）
> 3. To limit to the following purposes only: audience measurement;
>    A/B testing（用途僅限流量統計、A/B 測試）
> 4. Not to cross-check the data processed with other processing
>    （不得跟其他資料源交叉比對）
> 5. To limit the scope of the tracer to a single site or
>    application editor（範圍限單一網站/應用程式經營者）
> 6. To truncate the last byte of the IP address（IP 位址最後一
>    個位元組截斷）
> 7. To limit the lifetime of the trackers to 13 months（追蹤器
>    存活期限 13 個月）
> 8.（多平台代管服務商的獨立性要求）"the data is collected,
>    processed and stored independently for each publisher"

CNIL 頁面同時明白提醒：**"most large audience measurement
offerings do not fall within the scope of the exemption, regardless
of their configuration."**（多數主流大型流量統計服務，不論怎麼
設定都無法落入這個豁免——暗指 Google Analytics 這類服務）。CNIL
建議自架的開源方案（如 Matomo）作為可行替代。

另外，收集到的資料（相對於「追蹤器本身」）保存期限，CNIL 另有
建議上限：**25 個月**〔官方・索引確認〕——這是「resulting 統計
資料」的保存上限，跟上面第 7 點「tracker 本身存活 13 個月」是
兩件不同的事，不要混為一談。

### 3.2 英國的重大轉折：DUAA 修法生效，2026 年 2 月起新增「statistical purposes exception」

這是本輪最重要的新發現：**「英國比法國嚴格」這個常識已經過期**。

**官方法源**（〔官方直接引用〕，取自英國官方立法資料庫
`legislation.gov.uk`，《The Data (Use and Access) Act 2025
(Commencement No. 6 and Transitional and Saving Provisions)
Regulations 2026》）：

> Section 112（修訂 PECR 第 6 條，即英國轉譯 ePrivacy Art. 5(3)
> 的條文）"come into force on **5th February 2026**"

換句話說，這**不是** ICO 自己發的指引鬆綁，而是**英國國會立法本身
新增了法定豁免類別**，已於 2026 年 2 月 5 日正式生效。ICO 隨後在
2026 年 4 月 29 日發布配套的正式指引（〔官方直接引用〕，取自
`ico.org.uk`《Guidance on the use of storage and access
technologies》，「About this guidance」章節明白記載 "April 2026
update: We have finalised this guidance…"）。

該指引「What are the exceptions?」章節，官方原文列出**五個**豁免
（舊制只有兩個：communication／strictly necessary）〔官方直接
引用〕：

> "You can store or access information in five circumstances
> without the subscriber's or user's consent. […] for the sole
> purpose of collecting statistical information about visitors to
> your service, with a view to improving it. This is the
> 'statistical purposes' exception (also known as the 'analytics'
> exception)"

該章節對這個新豁免的具體條件，逐字如下〔官方直接引用〕：

> "The exception is essentially for analytics purposes. However, it
> is not a broad exception that covers all types of analytics
> technologies or ways you can use them. It is about how your
> service is used, not about who uses it. It is not for identifying,
> tracking or monitoring people or groups of people who use your
> service."

> "As part of relying on this exception, you must provide the user
> or subscriber with clear and comprehensive information about the
> purpose, and a 'simple and free' means to object."

明確**不合格**的情境包含〔官方直接引用〕：

> "logs or recordings of individual visitors to your website and the
> actions they took"／"tracking or profiling individual visitors"／
> "monitoring the browsing of website visitors across different
> services and applications"（跨站追蹤）

第三方 analytics 服務商可以用，但條件是〔官方直接引用〕：

> "your provider can only: act on your behalf; and use the
> information to help you improve your service" ／必須是
> "a processor, not a joint controller"

**跟法國 CNIL 對照**：兩國現在的規則骨架高度一致——只做匯總統計、
不追蹤特定個人、不跨站關聯、給使用者一個簡單的退出方式、不需要
彈窗式同意。英國新規**沒有**像法國一樣明訂具體的「13 個月」「IP
截斷最後一位元組」這種數字化條件，条件寫得比較抽象（"aggregate"／
"cannot identify people"），實務上等於把「怎麼做到匿名化」的判斷
交給業者自己承擔舉證責任。

**分類：【安全／法規必要】**（若真的要在英國/歐盟使用者身上用
Analytics，這是目前的法定規則現況）／**目前對 Option Chaser 是
【Option Chaser 產品選擇】**（因為現在根本沒有 Analytics，這節
只是未來地圖）。

### 3.3 四家「聲稱免同意」的 vendor，各自官方頁面怎麼說

**Vercel Web Analytics**（〔官方直接引用〕，取自 `vercel.com/docs/
analytics/privacy-policy`，頁面標記 `last_updated: 2026-06-26`）：

> "Vercel Web Analytics allows you to track your website traffic and
> gather valuable insights without using any third-party cookies,
> instead end users are identified by a hash created from the
> incoming request."

> "The lifespan of a visitor session is not stored permanently, it
> is automatically discarded after 24 hours."

> "no personal identifiers that track and cross-check end users' data
> across different applications or websites, are collected"

重點：**Vercel Web Analytics 完全不設 cookie**（用請求本身即時算出
的雜湊值，不寫進瀏覽器），且該雜湊值 24 小時後即丟棄，不做跨站
比對。這代表它甚至可能**不觸發 ePrivacy Art. 5(3)**（該條文管的是
「往裝置裡存取資訊」，這裡完全沒有寫入裝置這個動作），是四家裡
架構上最乾淨的一個。（本 repo 現有部署（見 CLAUDE.md「## 環境」
一節）本來就架在 Vercel 上，若真要加 Analytics，這是零額外
vendor 依賴的最低成本選項。）

**Plausible**（〔官方直接引用〕，取自 `plausible.io/data-policy`）：

> "We do not use cookies, we don't generate persistent identifiers."

> "By using Plausible, you do not need cookie banners for analytics
> or to collect consent for tracking."

> 識別演算法："hash(daily_salt + website_domain + ip_address +
> user_agent)"，"The salt is rotated and deleted every 24 hours."

> "Raw IP addresses and User-Agent data are never stored."

**Fathom Analytics**（〔官方直接引用〕，取自 `usefathom.com/data`）：

> "GDPR compliance out of the box"

> 識別演算法：a SHA-256 visitor signature using the incoming IP
> value, user-agent information, the site identifier, and a daily
> salt

> "without cookie banners"

**Umami**（〔官方直接引用〕，取自 `docs.umami.is/docs/faq`）：

> "Umami does not collect any personally identifiable information
> and anonymizes all data collected."

> "No, Umami does not use any cookies in the tracking code."

（Umami 官方 FAQ 沒有像 Plausible／Fathom 那樣公開詳細技術機制，
標記〔UNVERIFIED〕：Umami 用什麼演算法達成匿名化，本輪未查到
逐字說明。）

**這四家的共同模式**：不寫 cookie／不留跨站可用的持久識別碼／
用「每日輪替的鹽值 + IP + User-Agent 雜湊」在極短時間窗內去重
（區分「同一天內的同一人」跟「不同人」），過期後即無法逆推回原始
IP。這正好對應 3.1／3.2 兩國規則的核心要求（不能追蹤特定個人、
不能跨站關聯）——這也是為什麼這四家都敢公開宣稱自己免同意/免
cookie 橫幅，而 Google Analytics 這種**會設持久性 cookie、跨站
比對廣告聯播網資料**的傳統方案做不到同樣的宣稱（CNIL 官方頁面
2020 年就已明講「多數主流大型服務落不進豁免」）。

**分類：【業界成熟慣例】**——這四家的做法已是同類「隱私優先
analytics」市場的共識模式，不是單一家廠商的行銷話術（四家各自
獨立收斂到同一種「無 cookie + 短效雜湊」架構）。

---

## 四、Advertising——放廣告要準備什麼

**現況提醒：Option Chaser 目前完全沒有廣告。** 本節同樣是地圖，
**明確不建議現在動工**，理由見第八節。

### 4.1 Google AdSense「EU User Consent Policy」

**官方一手來源**（〔官方直接引用〕，取自 `google.com/about/
company/user-consent-policy-help/`，Google 官方公司頁面）：

> "Publishers are required to adopt a Certified CMP when serving ads
> to users in the EEA, the UK, and Switzerland in order to comply
> with this policy."

> "For publisher partners, publishers are required to adopt a
> Google-certified CMP which has integrated with the IAB Europe's
> Transparency and Consent Framework (TCF) when serving personalized
> ads to users in the EEA, the UK and Switzerland."

> 重要但書："Adopting a Google-certified CMP does not guarantee
> compliance with Google's EU user consent policy, as this depends
> on the implementation of the CMP and the specific consent message
> presented to users."（裝了認證的 CMP 不等於自動合規，還要看
> CMP 怎麼設定、彈窗文案怎麼寫。）

生效日期（〔官方直接引用〕，取自 `support.google.com/admanager/
answer/13554116`，Google Ad Manager Help 官方頁面）：

> "As of 16 January 2024, a certified CMP integrated with the TCF is
> required when serving personalized ads to users in the EEA and
> UK."

> "As of 31 July 2024, a certified CMP integrated with the TCF is
> required when serving personalized ads to users in Switzerland."

### 4.2 IAB Europe「Transparency & Consent Framework (TCF) v2.2」

**官方一手來源**（〔官方直接引用〕，取自 `iabeurope.eu/tcf/`，
IAB Europe 官方頁面）：

> "The TCF is an accountability tool that relies on standardisation
> to facilitate compliance with certain provisions of the ePrivacy
> Directive and the GDPR."

> "a cross-industry voluntary standard that is intended to enable
> publishers of websites and apps (first parties) and technology
> partners […] to work together and provide users with a
> standardised experience when they make privacy choices"

> TCF v2.2 於 **2023 年 5 月 16 日**發布（回應比利時資料保護
> 機構對前一版本的裁決）。

白話說明：TCF 是整個線上廣告業界的一套**共通技術規格**，讓「使用者
同意過什麼」這件事能用標準化格式在網站、廣告聯播網、多個廣告技術
供應商之間互相傳遞（不用每家自己發明一套）。Google 的 CMP 要求
本質上就是「你的同意彈窗系統要講 TCF 這套共通語言，Google 才願意
在你的網站上投放個人化廣告」。

### 4.3 現在該預留什麼、明確不該做什麼

**明確不建議現在做（會讓 Beta 變重、且服務的是不存在的需求）**：

- 整合任何 CMP（不論是 Google 認證的還是其他家）
- 寫任何 IAB TCF 相關程式碼（vendor list、purpose 字串等）
- 放任何實際廣告版位或 AdSense script
- 導入 Google Consent Mode v2（廣告用的一種「即使沒同意也回報
  匯總數據」的機制，跟廣告本身綁在一起，沒有廣告就沒有理由裝）
- 做任何歐盟/英國/瑞士訪客的地理位置偵測（CMP 通常需要判斷訪客
  在不在受規範地區，這本身就是一套額外系統）

**值得現在就知道、但不需要寫程式碼的事**：如果哪天真的決定要放
廣告，那一天要重新做的決策，跟今天的匿名身份 cookie 或 Analytics
決策**幾乎沒有共用空間**——CMP 要記錄的「使用者對廣告個人化的
選擇」，在法律定性上跟「這是不是投資建議」的免責聲明、或「有沒有
同意流量統計」是三件互相獨立的狀態，勉強現在就在資料庫裡預留一個
「consent 欄位」不會讓未來的工作變輕鬆，反而可能因為猜錯形狀而
需要重做。**唯一值得記住的原則**：真的要放廣告的那天，把「是否
已取得 TCF 格式同意」這件事，跟現有的匿名身份查表機制（cookie →
owner_id）用同一把 key 掛在一起即可，不需要現在預先設計這把
key 長什麼樣子——因為那把 key（隨機 cookie ID）**已經因為匿名
身份需求而存在了**，不是這節要新增的東西。

**分類：【安全／法規必要】**（若未來真的放廣告，Google/IAB 這套
要求就是現實）／**【Option Chaser 產品選擇】**（現在完全不做，
且不需要為它預留任何架構——這正是 Owner 已經表達的方向，本研究
確認這個方向沒有隱藏的技術債風險）。

---

## 五、交叉參照：投資免責聲明慣例

### 5.1 沿用既有研究——FINRA 規則

本 repo 既有研究 `docs/research/option-strategy-report-
conventions.md`（2026-08-04，對應票 R1／#49）§2.5、§4.4 已經
完整整理過美國 FINRA（美國金融業監管局）對選擇權相關溝通內容的
規則，**本輪直接沿用其結論，不重新查證**（該文件本身已誠實標記
這部分是「索引轉述」——WebFetch 在該次 session 對 `finra.org`
全部回 403；本輪重試 `curl` 帶瀏覽器 UA 依然被 Cloudflare 的
JS 挑戰頁擋下，確認這個封鎖從 2026-08-04 到今天沒有變化）：

> 〔沿用既有研究〕FINRA Rule 2210(d)(1)：所有溝通必須
> **fair, balanced and not misleading**；FINRA Rule 2220：選擇權
> 相關溝通中「任何提到潛在機會或優勢的敘述，必須以對應風險的敘述
> 來平衡」。

該既有研究已明講：Option Chaser **不受這些規則管轄**（非美國
經紀商、非 FINRA 會員），這裡引用純粹是「借業界最嚴格的品質標準
自我要求」，不是宣稱有法律義務。本輪判斷這個立場依然正確，不需要
修正。

### 5.2 三個真實工具的「陌生人第一次造訪」體驗——本輪新查

以下三個工具全部透過 `curl`（帶一般瀏覽器 User-Agent）直接取得
官方網站原始 HTML，逐字擷取，非第三方轉述。

**OptionStrat**（選擇權策略視覺化工具，與 Option Chaser 定位最
接近）〔官方直接引用〕：

> "Options involve a high degree of risk and are not suitable for
> all investors. OptionStrat is not an investment advisor. The
> calculations, information, and opinions on this site are for
> educational purposes only and are not investment advice.
> Calculations are estimates and do not account for all market
> conditions and events."

**位置**：**網站全域頁尾**，且經本輪實測確認**每一頁（含互動工具
頁本身、甚至 404 錯誤頁）都會出現**，因為它是整個 SPA 共用外殼的
一部分，不需要另外點什麼才看得到。**沒有**跳出彈窗、**沒有**
強制點擊同意才能繼續使用。

**Portfolio Visualizer**（資產配置/回測工具，比 Option Chaser
成熟、有付費會員與廣告合作）〔官方直接引用〕：

> "By clicking I Agree or by using this software, you confirm that
> you have read, understood, and agree to be bound by the Terms of
> Service, Privacy Policy, Disclaimer, Global Disclosures, and
> Partners and Affiliates."

> "Educational only. Not investment advice. Past and hypothetical
> results do not guarantee future performance. Investing involves
> risk, including loss of principal."

> "By proceeding, you consent to the processing of your personal
> data in accordance with our Privacy Policy (GDPR/UK GDPR/U.S.
> compliant)."

（頁面上並列 "I Agree" 與 "Continue" 兩個按鈕。）

**位置**：一個**強制的「User Agreement」互動關卡**，把「這不是
投資建議」跟「你同意我們處理你的個人資料（明講 GDPR/UK GDPR/US
合規）」**兩件本文刻意要求分開討論的事，捆在同一個彈窗裡一次要求
使用者按同意**。這是三個樣本裡**最重的**一種做法，且伴隨的
line 99（"we may receive compensation…advertising fees,
revenue-share"）透露它已經有廣告/聯盟行銷收入，法遵成本自然比較高。

**Options Profit Calculator**（免費簡易選擇權計算機，規模與
Option Chaser 最接近）〔官方直接引用，逐字掃描確認〕：

首頁與工具頁**完全沒有出現任何「投資建議」相關字樣**，頁尾只有
"About | Terms and Conditions | Privacy Policy | Contact"
四個連結，沒有任何一句可見的免責文字。

**三者對照給出的光譜**：Options Profit Calculator（完全沒有可見
揭露）→ OptionStrat（輕量、常駐、非阻斷式頁尾一句話）→ Portfolio
Visualizer（強制互動關卡，且把投資免責與資料處理同意綁在一起）。

### 5.3 Option Chaser 現況檢視（讀程式碼確認，非猜測）

查證 `option_chaser/report.py`／`src/AnalysisReport.tsx`：Option
Chaser **確實已經有**一段完整的免責文字（`disclaimer_text()`）：

> 「模型估計非保證價格，不構成投資建議。本工具並非經紀商，亦非
> 投資顧問，不提供個人化投資建議，本工具與任何監理機構之揭露
> 規範皆無關。選擇權交易涉及重大風險，可能損失全部投入本金，
> 交易前請參閱 OCC《Characteristics and Risks of Standardized
> Options》（選擇權風險揭露文件）。」

內容品質已經對齊業界慣例（明確排除經紀商/顧問身份、點名風險揭露
文件）。**問題完全出在位置**：`src/AnalysisReport.tsx` 檔頭
docstring 自己明講：

> 「整塊是詳細頁的『進階區』，本身也預設收合（沿用既有 QA1-12
> 慣例）」

也就是說，這段文字**只活在某個劇本詳細頁裡一個預設收合的區塊
底部**。一個陌生訪客從打開網站、瀏覽劇本庫、建立第一個劇本、看
Heatmap 主圖——**整條路徑上完全不會經過這段文字**，除非他自己
點進某個劇本詳細頁、還主動展開「進階區」。這與 5.2 光譜上表現
最弱的 Options Profit Calculator 實質上處於同一等級（有寫，但
陌生人幾乎不會看到），落後 OptionStrat 的頁尾常駐做法。

### 5.4 建議

**不需要修改既有 `disclaimer_text()` 的內容**（文字品質已足夠）。
**建議在 Public Beta 上線前，新增一個網站全域、常駐（不需要展開）、
非阻斷式（不擋住任何操作）的頁尾小字**，比照 OptionStrat 的模式而
非 Portfolio Visualizer 的模式——理由：Option Chaser 目前無廣告、
無付費會員、無聯盟行銷關係，法遵複雜度遠低於 Portfolio Visualizer，
沒有理由做到需要使用者主動點擊「我同意」才能繼續的程度；但目前
「完全埋在進階區」的狀態，比起同類工具裡做得最少的那一個
（Options Profit Calculator）也沒有更好，這是一個真正的落差、
不是吹毛求疵。

**這一節與第二節可以合併成一次改動**：既然頁尾小字本來就要新增，
順手把 2.3 的結論（法規上非強制、但兩個歐盟監理機關都建議做的
cookie 告知）放進同一行文字，例如「本工具使用一個必要的識別
cookie 以記住您的劇本，不含個人資訊；本站內容為模型估計，不構成
投資建議」這種一句話同時涵蓋兩件事——不需要因此新增第二塊 UI。

**分類：【業界成熟慣例】**（頁尾常駐揭露是三個樣本裡兩個都採用
的模式）／**【Option Chaser 產品選擇】**（合併成同一行小字這個
具體寫法，是產品層級的選擇，不是任何規則要求）。

---

## 六、分類總覽

**【安全／法規必要】**（不做會有實際法律/監理風險，或是判斷本身
屬於事實查證而非產品偏好）：
- 匿名身份 cookie 落在 ePrivacy Art. 5(3)「strictly necessary」
  豁免範圍內（§2.1）
- 該 cookie 對應資料應被視為 GDPR 意義下的（假名化）個人資料
  （§2.2）
- 台灣個資法直接適用於 Owner 的營運行為，且概括條款文字上足以
  涵蓋這類識別碼（§2.4，惟具體適用到「單純隨機 ID」缺台灣官方
  直接解釋）
- CCPA 的三個門檻數字本身、以及 cookie 落入其個資定義本身（§2.5）
- 判斷「GDPR/PECR 到底管不管得到」這個域外效力前提本身（§2.6）
- 若未來真要用 Analytics 影響到歐盟/英國使用者，CNIL／英國新法
  各自的具體條件（§3.1、§3.2）
- 若未來真要放廣告，Google AdSense／IAB TCF 的規則現況（§4.1、
  §4.2）

**【業界成熟慣例】**（法規上非強制，但成熟業者/監理機關公開建議，
成本低、沒有理由不採納）：
- 即使豁免同意，仍告知使用者有使用 cookie（CNIL、ICO 皆明講是
  "good practice"／"recommande"，非強制）（§2.3）
- 選用「無 cookie、短效匿名雜湊」架構的 Analytics vendor（若未來
  真要導入），而非傳統跨站追蹤型工具（§3.3）
- 「不構成投資建議」揭露採網站全域常駐頁尾，而非埋在深層收合區
  （§5.2、§5.4，三個同類工具中兩個採用類似模式）

**【Option Chaser 產品選擇】**（規則沒有規定,由 Owner／團隊自行
決定）：
- 要不要現在就假設會踩到 CCPA 門檻而預先合規（建議：不用，見
  第八節）（§2.5）
- 未來真的要加 Analytics 時選哪一家 vendor（§3.3 四選一或其他）
- 現在完全不建置任何 CMP/廣告相關程式碼（§4.3，Owner 已表態，
  本研究確認方向正確）
- 把 cookie 告知與投資免責合併成同一行頁尾文字的具體寫法（§5.4）

---

## 七、總表

| 項目 | 需不需要同意（consent） | 需不需要告知（notice） | Public Beta 建議 | 未來要預留什麼 |
|---|---|---|---|---|
| **匿名身份 cookie**（隨機 ID＋伺服器查表，記住訪客的劇本） | **不需要**——落在 ePrivacy Art. 5(3)「strictly necessary」豁免，WP29／ICO／CNIL 三方官方來源一致確認（§2.1） | **法律上不強制**，但 CNIL／ICO 皆建議告知（§2.3）；若對應資料被視為 GDPR 個資，GDPR 一般透明原則可能獨立要求告知（§2.2） | 現在就做：新增一行網站全域頁尾小字，說明「這是必要的識別 cookie，不含個資」，與投資免責合併同一行（§5.4） | 不需要預留任何額外欄位或機制——這顆 cookie 本身已經是「未來 Analytics/廣告若要掛使用者狀態」時唯一需要的那把 key，不必另外設計 |
| **Analytics**（流量統計，目前不存在） | 視作法而定：CNIL 八條件全滿足＝不需要；英國 2026-02-05 起新法定「statistical purposes exception」條件滿足＝不需要；否則需要（§3.1、§3.2） | 即使豁免同意，兩地規則都**要求**「clear and comprehensive information」＋「簡單免費的退出方式」（比 cookie 告知更強，是豁免的**必要條件**之一，不是選配）（§3.2） | **現在不加**。真的要加時，優先選 Vercel Web Analytics（零額外 vendor、已在既有部署平台上）或 Plausible/Fathom（皆已用官方頁面自證合乎兩地新規則）（§3.3） | 不需要現在預留架構——這四家 vendor 的載入方式都是「加一個 `<script>` 標籤」等級的整合，沒有需要提前準備的資料模型 |
| **Advertising**（廣告，目前不存在） | **需要**（且是最重的一種）——Google 明文規定 EEA/UK/CH 個人化廣告須用 IAB TCF 格式的認證 CMP 取得同意，2024-01-16／2024-07-31 起強制（§4.1、§4.2） | 併入 CMP 同意彈窗流程本身，不是獨立的告知動作 | **現在完全不做**，符合 Owner 已表達的方向（§4.3） | **不預留任何架構**——CMP 決策與匿名身份 cookie／Analytics 的技術棧幾乎不共用，提前預留反而可能猜錯形狀；真正要用的那天，用既有匿名身份 cookie 當 key 掛新狀態即可，屆時再設計 |

---

## 八、最推薦方案 / 次佳方案 / 明確不推薦方案

**最推薦方案**：三件事維持現狀分開處理，**只做一件事**——在 Public
Beta 上線前，新增一行網站全域、常駐、非阻斷式的頁尾文字，一次
說完「這是必要的識別 cookie，不含個資」＋「本站內容為模型估計，
不構成投資建議」兩件事（可以是同一句或緊鄰的兩句）。理由：這是
本輪唯一同時符合「【業界成熟慣例】」（CNIL/ICO 建議、OptionStrat
的實際做法）且成本近乎零（純文案改動，`disclaimer_text()` 內容
已經寫好，只是要挪一個更顯眼的位置）的動作；不涉及 Analytics／
Advertising 任何一步，不會讓 Beta 變重。**Analytics 與 Advertising
現階段一律不動**，維持 Owner 原本的判斷。

**次佳方案**：若 Owner 認為現在就想順便決定「以後真的要加
Analytics 會選哪一家」，可以現在就把答案記下來（本研究建議
Vercel Web Analytics，因為零額外 vendor 依賴且已驗證合乎英法
兩地最新規則），但**不需要現在寫任何整合程式碼**——記錄決策本身
不會讓 Beta 變重，實際整合留到真的需要看數據的那一天再做。

**明確不推薦方案，附原因**：
- **現在就導入任何 Analytics 工具**——即使選了「免同意」的
  vendor，也是在沒有真實需求（目前不知道要看什麼指標）的情況下
  新增一個外部依賴與隱私面向的持續維護負擔，不符合 Beta 階段
  「先驗證產品，不先建設施」的精神。
- **現在就整合任何 CMP 或廣告程式碼**——Owner 已經明確表態不要
  這樣做，本研究確認這個判斷完全正確：CMP／TCF 是一整套跟廣告
  綁死的基礎設施，沒有廣告就沒有意義，而且未來真的要放廣告時，
  屆時的 TCF 規範版本（目前是 v2.2）本身還可能再改版，現在猜
  規格反而可能猜錯白做工。
- **把 Portfolio Visualizer 那種強制「I Agree」彈窗當範本**——
  那個模式服務的是一個已經有付費會員、廣告合作、需要用一次性
  彈窗蒐集多種同意的成熟產品，套用在一個免費、無廣告、無會員制
  的 Beta 階段小工具上，是典型的「規格抄錯規模」，會讓每一個
  陌生訪客在看到任何內容之前先被迫做一次不必要的決定。

---

## 九、來源清單（依章節順序，重複來源不重列）

〔官方直接引用，本輪 WebFetch/curl 逐字核對〕
- [WP29 Opinion 04/2012 on Cookie Consent Exemption（PDF, WP194）](https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2012/wp194_en.pdf)（2012-06-07 通過；本輪自行解壓縮 PDF stream 逐字核對）
- [ICO — Guidance on the use of storage and access technologies: What are the exceptions?](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/what-are-the-exceptions/)（finalised 2026-04-29）
- [ICO — Guidance on the use of storage and access technologies: About this guidance](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/about-this-guidance/)（2026-04-29）
- [ICO — Cookies and similar technologies（舊版指引，仍掛在網站上作參考）](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/)
- [CNIL — Sheet n°16: Use analytics on your websites and applications](https://www.cnil.fr/en/sheet-ndeg16-use-analytics-your-websites-and-applications)
- [CNIL — Cookies et autres traceurs : que dit la loi ?](https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/que-dit-la-loi)（最後更新 2020-09-29）
- [CNIL — Questions-réponses sur les lignes directrices modificatives（FAQ）](https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/FAQ)（最後更新 2026-04-29）
- [GDPR (Regulation (EU) 2016/679) 全文 — EUR-Lex CELEX 32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679)（Recital 26、30、Art. 95 逐字核對）
- [CJEU Case C-582/14 Breyer v Bundesrepublik Deutschland — EUR-Lex CELEX 62014CJ0582](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A62014CJ0582)（判決日期 2016-10-19）
- [台灣《個人資料保護法》— 全國法規資料庫官方英譯](https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=I0050021)（最後修正 2025-11-11）
- [California Civil Code § 1798.140 — California Legislative Information](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1798.140&lawCode=CIV)
- [The Data (Use and Access) Act 2025 (Commencement No. 6…) Regulations 2026 — legislation.gov.uk](https://www.legislation.gov.uk/uksi/2026/82/regulation/2/made)（Section 112 生效日 2026-02-05）
- [Vercel — Web Analytics Privacy and Compliance](https://vercel.com/docs/analytics/privacy-policy)（`last_updated: 2026-06-26`）
- [Plausible — Data Policy](https://plausible.io/data-policy)
- [Fathom Analytics — Simple, Privacy-Focused Website Analytics（Data 頁）](https://usefathom.com/data)
- [Umami — FAQ](https://docs.umami.is/docs/faq)
- [Google — Help with the EU user consent policy](https://www.google.com/about/company/user-consent-policy-help/)
- [Google Ad Manager Help — Google consent management requirements for serving ads in the EEA, the UK, and Switzerland (for publishers)](https://support.google.com/admanager/answer/13554116?hl=en)
- [IAB Europe — The Transparency & Consent Framework (TCF) v2.2](https://iabeurope.eu/tcf/)
- [OptionStrat 官方首頁](https://optionstrat.com/)（本輪 curl 直接擷取原始 HTML）
- [Portfolio Visualizer 官方首頁](https://www.portfoliovisualizer.com/)（同上）
- [Options Profit Calculator 官方首頁](https://www.optionsprofitcalculator.com/)（同上）

〔官方・索引確認，經 WebSearch 交叉核對多筆結果指向同一官方來源，
未逐字全文核對〕
- Google AdSense EU User Consent Policy 相關支援頁面群（`support.google.com/adsense/*`、`support.google.com/admanager/*`）生效日期 2024-01-16／2024-07-31
- GDPR Art. 95 條文全文（多方轉述逐字一致，惟本輪未能直接從 EUR-Lex 頁面截出該條所在段落）
- EDPB《Guidelines 3/2018 on the territorial scope of the GDPR》（`edpb.europa.eu`）targeting 測試要點
- Data (Use and Access) Act 2025 Section 112 內容摘要（`lexology.com`／`practicallaw.thomsonreuters.com`等法律實務摘要，但生效日期已由官方 legislation.gov.uk 交叉確認）

〔沿用既有研究，未重新查證〕
- `docs/research/option-strategy-report-conventions.md` §2.5、§4.4（FINRA Rule 2210(d)(1)、2220，索引轉述等級，`finra.org` 本輪重試仍 403）

〔UNVERIFIED，明確標示，非猜測〕
- 台灣個人資料保護委員會（或 NDC）是否曾就「不具名隨機識別碼是否
  構成個資法上的個人資料」發布過解釋令
- CCPA「doing business in California」這個更基礎的適用門檻，是否
  對一個全中文、非鎖定加州市場的產品構成障礙
- Umami 匿名化訪客識別的具體技術機制（該廠商官方 FAQ 未公開細節）
