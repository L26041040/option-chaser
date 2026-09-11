# 匿名濫用防護與限流模式研究

研究日期：2026-09-11。對應 GitHub issue **#277**，另含 Owner 於
2026-09-11 追加的 admin／controlled-beta 範圍。

**本輪範圍**：只研究業界成熟做法與代價，**不替 Owner 決定任何具體
數字**（例如「每個 owner 幾張劇本」）。文中所有「建議」只建議
**形狀**（要不要有這層機制、哪一層先做、哪個方向比較安全），不建議
數值。真正的數字留給 issue #277 底下的 grilling 票，由 Owner 親自
裁示。

**未施工**：本輪未改動任何 production code、config、infra，未碰
`option_chaser/`／`api_app/`／`src/`，未碰 #269，未開票、未裁決任何
事項。

**查證日期**：以下全部外部連結之存取日期均為 **2026-09-11**（下同，
不逐條重複標註）。無法查證的地方一律標記 **UNVERIFIED**，不猜測、
不杜撰。

**證據分級**（本文專用三類，非本 repo 其他研究文件慣用的四級）：
- **【業界慣例】**——多家獨立廠商／專案的官方文件或工程部落格一致
  採用的做法。
- **【法規／安全必要】**——IETF RFC、OWASP 官方標準等具規範性質的
  文件所明訂或建議的事。
- **【Option Chaser 產品選擇】**——把上述業界事實對照到這個 repo
  現有架構後，屬於「這個產品該怎麼選」的判斷（仍不含具體數字）。

---

## 0. 給 Owner 看的白話摘要

現況：Option Chaser 今天**完全沒有**任何形式的濫用防護——沒有
per-owner（每個匿名身份）的劇本數上限、沒有刷新最短間隔、沒有
每日分析量上限、也沒有全站每日對 vendor（第三方資料源，這裡指
Cboe）呼叫次數的預算。唯一存在的節流機制是 `chain_backoff.py` 那張
**provider-global**（不分使用者、不分 symbol，整個 Cboe 這個
provider 共用一個封鎖窗）的 429 circuit breaker（斷路器，見 §3），
但它是**被動**的——要先被 Cboe 真的擋了才會啟動，不是主動預防。

三個核心問題的答案先講重點：

1. **只靠 cookie 辨識匿名身份「不夠」，但這不代表它「沒用」。**
   業界（Vercel、Cloudflare、AWS）三家的限流工具都把「cookie／自訂
   header 值」列為可用的計數鍵之一，但沒有一家把它當作**唯一**的
   防線——全部都建議跟 IP 疊加使用。原因很簡單：清 cookie 是零成本
   的動作，任何人隨手就能重置身份。但 cookie／owner id 仍然是**唯一
   能對應到「這個帳號有幾張劇本」這種帳號形狀問題的鍵**——IP 或
   裝置指紋都做不到這件事，因為一個 IP 底下可能有很多真實使用者、
   一個裝置指紋也可能對應很多人（見 §1）。

2. **限流放哪一層不是二選一，業界標準做法是疊加。** Vercel 自己的
   Firewall／WAF 就內建 edge 層限流（免費方案就有），app 層可以在
   FastAPI 裡自己寫（配 Postgres），這個 repo 已經在生產環境跑著
   兩個「用一張 Postgres 表當共用計數器」的機制了（`chain_backoff`／
   `operational_metrics`）——加一張 per-owner 額度表是同一個模式的
   第三次應用，不是引入新技術（見 §2）。

3. **circuit breaker 已經有了，但只有「被動」那一半。** 現有的
   Cboe 429 backoff 是撞到牆才啟動；業界（Google SRE Book、Stripe）
   同時建議**主動**設一個「還沒撞牆但已經接近時就先降級」的全站每日
   預算——這個 repo 已經在記錄需要的原始數據（`chain_fetch_count`），
   只是還沒有任何程式碼真的去讀這個數字並據此提前降級（見 §3）。

4. **前端已經有一套「怎麼跟使用者說『請等一下再試』」的現成元件**——
   Cboe 429 的倒數計時鎖定重試鈕（`useCountdownSeconds()`）如果換一組
   相同形狀的資料（`retry_after_seconds`／`blocked_until`），大概可以
   直接重用在「你這個身份被限流了」這個新情境上，不必從零刻一套
   （見 §4）。

5. **Admin／superuser 身份不建議做成「完全不受限」**，理由不是理論上
   的謹慎，是有實際案例可循：Stripe 自己維護獨立的 test mode，卻
   明確告誡「不要拿 test mode 去做真的壓力測試，因為它的限制反而比
   live mode **更嚴**」，並建議測試該用 mock（假造）掉真正的外部呼叫，
   而不是真的打下游服務。Option Chaser 這個 repo 剛好已經有現成的
   mock 注入點（測試套件用的 `fetch=`／`rate_loader=`／
   `dividend_loader=` DI 參數）可以直接借來做 controlled beta 的
   壓測，不必真的打 Cboe（見「Admin 身份」一節）。

6. **admin 端點如果真的去打 Cboe，一定會算進同一個全站配額**——這不是
   政策選擇，是物理限制：Cboe 的 429 不知道、也不在乎是誰在 Option
   Chaser 內部發起這次請求；而且現有的 backoff 設計本來就是
   **provider-global**（刻意不分 symbol，見 SCALE-04 的既有裁示），
   所以只要 admin 走的是真實 vendor 呼叫路徑，就一定會跟一般使用者
   共用同一個封鎖窗——這是本輪查證後最確定的一條結論（見「Admin 身份」
   一節第 3 小題）。

其餘細節、每一條結論的證據來源、以及最後那份「要問 Owner 的選項清單」
都在下面各節。

---

## 1. 三種限制單位的優缺點

限流（rate limiting，限制單位時間內能做多少次某件事）第一步永遠是
決定「用什麼身份來算次數」。三種候選：**匿名 owner（用 cookie 存的
一個隨機身份）**、**IP 位址**、**裝置指紋（browser fingerprinting，
從瀏覽器／裝置的一堆特徵組合出一個近似唯一的識別碼，不需要 cookie）**。

### 1.1 按匿名 owner（cookie）

**機制**：第一次造訪時由伺服器發一個隨機 owner id、寫進 cookie；
之後每次請求都帶著同一個 cookie，伺服器據此認出「這是同一個身份」。
這剛好對應這個 repo 現有的 `IdentityResolver` 概念（`api_app/
identity.py`）——今天它是寫死的 `SOLO_OWNER`，若要支援多個匿名使用者，
自然的做法就是把這個固定值換成「從 cookie 讀出來的值，讀不到就發一個
新的」。

**擋得住什麼**：能表達「這個帳號有幾張劇本」「這個帳號上次刷新是
什麼時候」這類**帳號形狀**的問題——IP 或裝置指紋都做不到，因為它們
不是「一個帳號」的概念，是「一台機器／一條網路連線」的概念。這個 repo
既有的 ownership boundary（SCALE-06／SCALE-11，`owner_id` 欄位已經
存在於 `scenarios`／`results`／`snapshots` 等表）天生就是為「一個
owner」設計的，cookie-owner 是唯一能直接掛上去用的鍵。

**擋不住什麼／誰會被誤傷**：清 cookie、開無痕視窗、換一個瀏覽器都是
**零成本**的動作，任何人隨手就能重置身份、拿到一組全新的額度。

**業界怎麼看待「只靠 cookie」**：

- Vercel 官方 WAF Rate Limiting 文件列出的「計數鍵」包含
  IP、JA4 Digest（見 §1.3），付費方案再加 header／cookie 值——但
  **從未把 cookie 列為唯一鍵**，永遠是跟 IP 或其他鍵並列的選項
  （[Vercel WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)）。【業界慣例】
- Cloudflare 的進階限流（Advanced Rate Limiting，Enterprise 方案）
  同樣把 Cookie 列為可用鍵，但官方範例展示的是**組合鍵**（例如
  「IP 位址與 HTTP 方法」「兩個不同 cookie 的值」），不是單獨用一個
  cookie（[Cloudflare Rate Limiting Rules](https://developers.cloudflare.com/waf/rate-limiting-rules/)）。【業界慣例】
- AWS WAF 的 rate-based rule 同樣支援 Cookie 當自訂 aggregation key
  （聚合鍵），但官方文件把它跟 Header／Query argument 並列成「可以
  跟 IP 位址組合使用」的選項之一，不是取代 IP
  （[AWS WAF aggregation options](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html)）。【業界慣例】
- Vercel 自己在程式碼裡做限流用的 `@vercel/firewall` SDK
  （`checkRateLimit()`）預設鍵是 client IP；文件明確警告：如果你把
  `rateLimitKey` 換成一個**所有請求都相同的固定字串**，這條規則會
  「變成全域規則」——換句話說，官方直接點名「單一、可預測、容易重複
  使用的鍵會讓限流形同虛設」，這正是純 cookie（使用者可以自己清掉、
  拿到新的一份）最根本的弱點
  （[Vercel Rate Limiting SDK](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting-sdk)）。【業界慣例】

⚠ **本輪要點名的一個常見誤解**：「只靠 cookie 限流」本身**不是**
一個被業界普遍認可為足夠的方案——上面四個獨立來源沒有一個把
client-supplied identifier（客戶端自己帶的、可以自己清除或偽造的
識別值，cookie 正是其中一種）當作單一防線用；全部都是拿它跟 IP 或
其他鍵組合。但這不等於「cookie 沒用」——它仍是**唯一**能對應到
「帳號形狀」問題的鍵，只是「防止有人一直重開新帳號」這件事，cookie
本身做不到，需要 IP 或其他訊號來補。

### 1.2 按 IP

**機制**：以請求的來源 IP 位址為鍵。

**擋得住什麼**：這是三者中**唯一**「換一個新身份要付出實際成本」的
鍵——一般使用者不會為了多刷幾次劇本去換網路。而且在 Vercel 上，
`x-forwarded-for`（記錄請求經過的代理鏈路上各站 IP 的標頭）**不能被
使用者偽造**：Vercel 官方文件明確寫著「若你想在 Vercel 前面再放一層
代理，我們目前會覆寫 `X-Forwarded-For` 標頭、不轉發外部 IP，這是為了
防止 IP 偽造」，只有 Enterprise 方案付費開通「trusted proxy」才能自訂
（[Vercel Request headers — x-forwarded-for](https://vercel.com/docs/headers/request-headers)）。【業界慣例，且直接適用於這個 repo 的實際部署平台】
也就是說：在目前的 Hobby／Pro 方案下，Option Chaser 應用層看到的
`x-forwarded-for` 就是真實的來源 IP，不必額外擔心使用者自己塞假標頭
進來繞過。

**擋不住什麼／誰會被誤傷**：IP 位址從來不等於一個人。

- **CGNAT（Carrier-Grade NAT，電信商把大量用戶包在同一個對外公開
  IP 後面的技術）是 IETF 官方正式承認、專門保留了一塊位址空間
  （`100.64.0.0/10`）來支援的架構**——RFC 6598 摘要直接寫：「本文件
  請求分配一塊 IPv4 /10 位址區塊，作為 Shared Address Space（共享
  位址空間），以滿足 Carrier-Grade NAT（CGN）裝置的需求」
  （[RFC 6598](https://www.rfc-editor.org/rfc/rfc6598.html)）。【法規／安全必要，IETF 標準】
  換句話說，「同一個 IP 後面有一大群互不相關的真實使用者」不是邊緣
  案例，是整個網際網路早就正式規劃進去的常態——行動網路用戶、公司
  NAT 出口、家用寬頻在某些地區都可能落在同一個 CGNAT 出口 IP 後面。
- AWS WAF 官方文件自己也承認這個限制：「來源 IP 位址可能不包含真正
  發出請求的客戶端位址。如果一個 Web 請求經過一或多個代理或負載
  平衡器，這裡記錄的會是最後一個代理的位址」
  （[AWS WAF rate-based rule statements](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html)）。【業界慣例，官方自己記載的已知限制】
- 反過來，IP 對「同一個真實使用者」也不穩定——切換 Wi-Fi／行動網路、
  重新連線就可能拿到新 IP，所以 IP 既不是使用者的穩定身份，也不是
  攻擊者無法繞過的邊界，只是「三者裡成本相對較高、但不是絕對」的
  一個訊號。

**業界慣例定位**：IP 是幾乎所有限流產品的**預設**鍵——Cloudflare
Free／Pro 方案的限流鍵就只有 IP（[Cloudflare 限流規則](https://developers.cloudflare.com/waf/rate-limiting-rules/)），AWS WAF
rate-based rule 的預設聚合方式就是來源 IP
（[AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html)）。【業界慣例】
「IP 是最常見的第一層防線」跟「IP 會誤傷 NAT／代理背後的真實使用者」
這兩件事同時為真，且兩者都被主要廠商官方文件明文承認。

### 1.3 按裝置指紋（browser fingerprinting）

**機制**：不靠 cookie，改用瀏覽器／裝置本身的一堆特徵（畫面尺寸、
字型清單、時區、User-Agent、WebGL 參數、TLS 握手細節等）組合出一個
近似唯一的識別碼。

**擋得住什麼**：清 cookie、開無痕視窗都清不掉——指紋不是存在
瀏覽器的儲存空間裡，是從瀏覽器「現在長什麼樣子」即時算出來的。
EFF（Electronic Frontier Foundation）自己維護的 Cover Your Tracks
專案（前身 Panopticlick）明講：「如果你的瀏覽器是唯一的，那麼追蹤者
即使不設 cookie 也可能認出你」「清 cookie 沒有用，因為被分析的是你
瀏覽器設定本身的特徵」
（[Cover Your Tracks](https://coveryourtracks.eff.org/about)）。【業界慣例，且是原始研究專案本身】

**擋不住什麼／誰會被誤傷、以及一個矯正性的重要事實**：

- 指紋的鏡像問題——**多個真實使用者共用同一台裝置**（家人共用電腦、
  學校／公司共用的公用電腦）在指紋辨識下會被判成同一個身份，這是
  跟 NAT 對稱、但成因不同的誤傷。
- **更根本的問題：主流瀏覽器廠商正在主動、長期地降低指紋的可辨識度，
  而這正是這項技術「可靠」與否的核心矛盾。** W3C（全球資訊網標準
  組織）自己發佈的 fingerprinting-guidance 官方文件講得很直接：
  「瀏覽器指紋可以被用作一種安全機制（例如驗證使用者身份的手段）……
  然而指紋識別同時也是使用者隱私的一種威脅」，並提到「有些實作者與
  使用者可能願意接受功能或效能上的降級，以求降低瀏覽器可被指紋
  辨識的程度」——也就是說，瀏覽器廠商正在**主動**讓指紋變得更不
  穩定、更不獨特，這跟拿它當防濫用訊號的目的正好互相拉扯
  （[W3C Fingerprinting Guidance](https://w3c.github.io/fingerprinting-guidance/)）。【法規／安全必要，W3C 官方文件；同時也是業界廠商行為的既定事實】
  同一份文件也指出「瀏覽器指紋通常無法被清除或重設」——這對防濫用是
  好消息（攻擊者不能像清 cookie 一樣輕鬆重置），但對**被誤判**的
  無辜使用者是壞消息：他們沒有一個簡單動作可以「換一個新指紋」重新
  開始，除非真的換裝置或瀏覽器。
- **這個 repo 部署在 Vercel 上，恰好有一個現成、免費、不需要額外
  廠商整合的「輕量指紋」可用**：Vercel Firewall 內建 JA3／JA4 TLS
  fingerprint（對 TLS 交握過程本身的特徵做雜湊，不是完整的瀏覽器
  JS 環境指紋，粒度較粗），且 Vercel 官方 WAF Rate Limiting 文件
  的方案對照表明確寫著：**Hobby 與 Pro 方案「內含的計數鍵」就是
  「IP、JA4 Digest」**，不需要升級到 Enterprise
  （[Vercel WAF Rate Limiting 方案表](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)；[Vercel Firewall Concepts — JA3/JA4](https://vercel.com/docs/vercel-firewall/firewall-concepts)）。【Option Chaser 產品選擇：這是一個現有平台已經免費附贈、值得列入考慮的選項，不必額外整合第三方指紋服務】
  但要注意粒度：JA4 指紋只反映用戶端 TLS／HTTP 函式庫版本，同一個
  瀏覽器版本＋同一個作業系統的所有使用者可能共用同一組 JA4，因此比
  完整瀏覽器指紋粗得多、也比它穩定（因為只在瀏覽器更新版本時才變）。

**業界定位**：指紋辨識在主流廠商產品裡，較常見的用途是**輔助偵測
機器人／異常流量**（Vercel 用 JA3/JA4 判斷「同一個攻擊工具是不是
換著 IP／User-Agent 打」），而不是單獨拿來當限流的主鍵。【業界慣例】

### 1.4 小結對照表

| 維度 | 匿名 owner（cookie） | IP | 裝置指紋 |
|---|---|---|---|
| 擋得住 | 「帳號形狀」問題（劇本數、上次刷新時間）——只有這個鍵做得到 | 換身份要付出實際成本（換網路） | 清 cookie／開無痕視窗都繞不過 |
| 擋不住 | 清 cookie／換瀏覽器＝零成本重置 | 沒防住任何「同一人多個帳號」的行為 | 主流瀏覽器正主動讓它變得不穩定；粗粒度版本（JA4）覆蓋面窄 |
| 誰被誤傷 | 沒有誤傷（身份本身就是這個鍵定義出來的） | CGNAT／公司 NAT／行動網路背後的多個真實使用者互相牽連 | 共用裝置（家人／公用電腦）背後的多個真實使用者互相牽連 |
| 換身份成本 | 零 | 中（換網路） | 高（換裝置／瀏覽器），但也因此誤判後很難自行「洗白」 |
| 這個 repo 現成的鉤子 | `IdentityResolver`／`owner_id` 欄位（SCALE-06/11 已存在） | `x-forwarded-for`（Vercel 邊緣層已驗證過，不可偽造） | Vercel JA4 Digest（Hobby/Pro 方案免費內含） |

**結論（回答任務給的關鍵問題）**：只靠 cookie **不是**業界認可的
充分方案——四個獨立來源一致把它當作「要跟其他鍵組合」的訊號，而不是
單獨防線。但它也不是「沒用」，而是三個鍵各自解決不同問題：cookie
解決「這是誰的帳號」，IP 解決「換身份有沒有代價」，指紋解決「清
cookie 繞不繞得過」。業界標準做法是疊加，不是三選一。

---

## 2. 限流演算法與放在哪一層

### 2.1 演算法白話對照

**固定視窗計數器（Fixed Window Counter）**：把時間切成固定長度的
格子（例如「這一分鐘」），格子裡的請求數超過門檻就擋，換到下一個
格子計數器歸零重來。Vercel 官方 WAF Rate Limiting 的方案表把它列為
**所有方案都內含**的演算法（"Fixed Window (all plans)"），對照
**Token Bucket（Enterprise）**——也就是說，最簡單的固定視窗在
Vercel 上完全免費，但如果想要更平滑的 token bucket，目前得升級到
Enterprise 方案
（[Vercel WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)）。【業界慣例，且直接標出這個 repo 目前方案能拿到什麼】
固定視窗最大的已知缺點是「邊界突刺」——Cloudflare 自己的工程部落格
講得很直白：純固定視窗「會讓流量尖峰有機會穿過限流器」（因為在
兩個格子交界處，攻擊者可以在上一格結尾＋下一格開頭各打滿一次額度，
短時間內等於拿到兩倍額度）
（[Cloudflare — Counting things, a lot of different things](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/)）。【業界慣例】

**滑動視窗（近似版，Sliding Window Counter）**：Cloudflare 自己的
工程部落格公開了他們的做法——不是精確記錄每一筆請求的時間戳，而是
只存**前一格與這一格**兩個數字，用一個加權公式估算「現在往回數
一個視窗長度」的請求數。他們給的實際範例公式：

> `rate = 42 * ((60-15)/60) + 18 = 42 * 0.75 + 18 = 49.5 requests`

（意思是：上一分鐘打了 42 次，這一分鐘目前打了 18 次，現在時間點
落在這一分鐘的第 15 秒，所以上一分鐘的量按「還剩多少比例落在視窗內」
打折後跟這一分鐘的量相加，估算出目前這個滑動視窗內大約有 49.5 次
請求。）他們選這個做法的理由很直接：純固定視窗會讓尖峰穿過去，
但完整、逐筆記錄時間戳的精確滑動視窗（sliding window log）「需要
巨大的處理與記憶體開銷」；折衷方案只需要「每個計數器存兩個數字」，
可以用一次 `INCR`（原子遞增）指令更新，實測 4 億筆請求裡只有
0.003% 被誤判（誤放或誤擋），準確度「夠用」但複雜度低很多
（[同上](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/)）。【業界慣例】
⚠ 這篇部落格發表於 2017 年，描述的是 Cloudflare 當時那一代限流產品
的內部實作；**Cloudflare 現在的 Rate Limiting Rules（本文 §1／§2
其他段落引用的官方文件）沒有在公開文件裡明確點名目前用的是不是完全
同一套演算法**——本文只把這篇部落格當作「業界一個真實、可查證、
說明清楚的滑動視窗近似實作範例」引用，不代表 Cloudflare 現行產品
逐字如此。標記 **UNVERIFIED**：Cloudflare 現行 Rate Limiting Rules
產品的確切演算法名稱。

**代幣桶（Token Bucket）**：想像一個桶子，裡面的代幣以固定速率
慢慢注入，滿了就不再加；每次請求消耗一個代幣，桶空了就拒絕。這個
設計天生允許「短時間內爆量」（桶子還有存量），同時長期平均速率被
桶子的注入速率鎖住。Stripe 自己的工程部落格明講他們用的就是這個
演算法：「有一個集中式的 bucket host，每次請求拿一個代幣，代幣會
慢慢地被滴進桶子裡」，「每個 Stripe 使用者都有自己的桶子，每次請求
就從那個桶子拿掉一個代幣」，用 Redis 叢集實作
（[Stripe — Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)）。【業界慣例】
Stripe 官方限流文件也建議客戶端自己實作 token bucket 演算法來平滑
自己送出的流量（[Stripe Rate Limits](https://docs.stripe.com/rate-limits)）。【業界慣例】

**GCRA（Generic Cell Rate Algorithm）**：數學上等價於 token bucket，
但只需要存**一個時間戳**（下一次「理論上允許的到達時間」），不需要
存桶子容量或代幣數，是一種更省儲存空間的實作技巧，常見於高效能限流
函式庫。本文只把這個當作「業界常見的高效實作手法」提及，**沒有找到
可以直接引用的一手官方來源確認 Cloudflare 或其他大廠現行產品逐字
使用這個名稱的演算法**——標記 **UNVERIFIED**。

**併發數限制（Concurrency Limiter，跟速率型限流是不同概念）**：
限制「同時有幾個請求在處理中」，而不是「單位時間內能送幾次請求」。
Stripe 官方文件明確把這個跟一般限流分開講：「併發限制跟速率限制
不同，速率限制通常一秒後就重置，併發限制是即時計算『現在有多少個
請求正在進行中』」，並指出「長時間執行的請求（例如列表查詢或帶展開
參數的請求）比較容易踩到這個限制」（[Stripe Rate Limits — Concurrency limits](https://docs.stripe.com/rate-limits)）。【業界慣例】
這個概念跟 Option Chaser 的架構特別相關——見 §2.3。

**依重要性分級卸載（Criticality-based load shedding）**：當系統整體
過載時，優先犧牲不重要的流量、保留重要的流量，而不是一視同仁地全部
拒絕。Google SRE Book《處理過載》一章定義了四個等級：`CRITICAL_
PLUS`（最不能失敗）、`CRITICAL`（一般 production 預設）、
`SHEDDABLE_PLUS`（批次工作，允許部分不可用）、`SHEDDABLE`（可以
經常不可用）；書中原文：「當一個客戶用完全站配額時，後端只有在已經
拒絕了所有更低重要性等級的請求之後，才會拒絕某個特定重要性等級的
請求」（[Google SRE Book — Handling Overload](https://sre.google/sre-book/handling-overload/)）。【業界慣例】
Stripe 自己也有類似設計，稱為「Worker Utilization Load Shedder」：
過載時依序犧牲「test mode 流量 → GET 請求 → POST 請求 → 關鍵請求」
（[Stripe — Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)）。【業界慣例】

### 2.2 放在哪一層

**Edge／WAF 層（Vercel Firewall、Cloudflare——請求連你的程式碼都
還沒跑到就先被擋掉）**：

- 優點：擋掉的流量完全不會消耗你自己的運算或資料庫資源——這是成本
  最低的防線。Vercel 的 Attack Mode（自動判斷是否遭受攻擊並要求
  訪客過關驗證）「在所有方案上都免費，被 Attack Mode 擋下的請求
  不計入用量」（[Vercel Attack Mode](https://vercel.com/docs/vercel-firewall/attack-mode)）。【業界慣例】
  更重要的是，**Vercel WAF Rate Limiting 今天就能直接開，不需要
  改一行程式碼**——Hobby 方案內含 1 條規則、100 萬次「被允許的
  請求」額度，鍵可以選 IP 或 JA4 Digest（[Vercel WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)）。【Option Chaser 產品選擇：這是零程式碼改動、現有平台已內建、可以現在就打開的選項】
- 缺點：edge 層天生看不到你自己 App 的資料模型——它不知道「這個
  owner 已經有幾張劇本」這種只有你的資料庫才知道的事。Cloudflare／
  AWS 都支援把一個自訂 header／cookie 的值當鍵用，但那個值本身還是
  得由你的程式碼算出來、寫進 header／cookie，帳號形狀的邏輯（「這個
  owner 有沒有超過上限」）終究得留在 App 層。另外，WAF Rate Limiting
  在超出方案內含額度後是按用量計費的（[Vercel WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)），不是無限免費，只是對一個小規模的
  controlled beta 而言，這個量級大概離收費門檻還很遠。

**App 層（FastAPI middleware，這個 repo 自己的程式碼）**：

- 優點：能表達完整的商業邏輯——「這個 owner 已經有 N 張未過期劇本」
  「距離上次刷新不到 X 秒」這種判斷只有這裡做得到。Vercel 自己的
  `@vercel/firewall` SDK 就是設計成讓你在程式碼裡呼叫
  `checkRateLimit()`，並傳入你自己算出來的 `rateLimitKey`（例如
  已驗證使用者的 `userId`）
  （[Vercel Rate Limiting SDK](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting-sdk)）——這正是「app 層決定鍵、edge 層執行限流」這種混合設計的官方範例。
  **但要注意**：這個 SDK 是 Node.js／TypeScript 套件（本 repo
  `package.json` 內沒有 `@vercel/firewall` 依賴，本輪也查無 Python
  Vercel Functions 的官方對應套件）——標記 **UNVERIFIED**：是否
  存在給 Python serverless function 直接呼叫的等價 API。對這個
  repo 實際的 Python／FastAPI 架構而言，最直接可行的路仍是自己在
  FastAPI middleware 裡讀 Postgres 判斷（見下）。
- 缺點：即使決定要擋掉這次請求，這個判斷本身仍要消耗一次應用層
  ＋資料庫往返（雖然遠比真的去打 Cboe、跑一次完整分析便宜）。
  **更關鍵的一個陷阱，且這個 repo 自己已經踩過、記錄下來過**：
  serverless 架構下，行程內記憶體（例如一個 Python 的 `dict`
  計數器）**不會**跨 invocation（每次呼叫可能是全新的容器）穩定
  存活。這正是這個 repo 的 ADR-0001 明確記載過的教訓——舊版
  `chain_cache` 曾經想靠行程內記憶體做跨呼叫的快取，最後被拿掉、
  改成只在單一 invocation 內去重（見 `docs/adr/0001-chain-sharing-
  within-run-only.md`，本 repo 內部文件）。【Option Chaser 產品選擇：這個 repo 自己的既有架構決策已經證明「行程內記憶體計數器」在這個平台上不可靠，任何 app 層計數器都必須落在 Postgres，不能只放記憶體】

**資料層（只有 Postgres，沒有 Redis）——任務特別問到的情境**：

這正是 Option Chaser 目前的真實處境：`pyproject.toml` 沒有任何
Redis／Upstash 依賴，全站唯一的持久層是 Neon（雲端 Postgres）。
好消息是：**這個 repo 已經在生產環境跑著這個模式兩次了**：

- `api_app/chain_backoff.py`——一張只有一列（依 `source`）的表，
  記錄 Cboe 目前是否處於 429 封鎖窗，讀寫失敗一律 fail-open（視同
  沒有限流問題，不阻斷主流程）。
- `api_app/metrics.py`——`operational_metrics` 表，依「日期桶」
  （day bucket）聚合計數（`chain_fetch_count`／`chain_429_count`
  等），每次寫入時順手清掉超過 30 天的舊桶（`RETENTION_DAYS`）。

加一張「per-owner 額度」表，是同一個「用一張 Postgres 表當共用
計數器、讀寫失敗 fail-open」模式的**第三次應用**，不是引入新技術。

業界對「只有 Postgres、沒有 Redis」該怎麼做限流也有現成答案，而且
恰好是**這個 repo 實際使用的 Postgres 供應商 Neon 自己寫的官方
指南**：用「固定視窗計數器＋advisory lock（諮詢鎖，PostgreSQL 提供
的一種應用程式自訂用途的鎖，系統不會替你檢查怎麼用，正確與否全靠
你自己的程式邏輯）＋UPSERT（insert 或 update 二選一的原子操作）」
組合而成——「如果現在的時間已經超出既有視窗（`window_start +
window_length <= now`），就把計數重置為 1、開新視窗；否則就遞增計數、
維持現有視窗」，用 advisory lock 避免併發時計數被搶跑掉
（[Neon — Rate Limiting in Postgres](https://neon.com/guides/rate-limiting)）。【業界慣例，且是這個 repo 實際 Postgres 供應商的官方文件】
PostgreSQL 官方文件對 advisory lock 本身的定義：「PostgreSQL 提供
一種能建立應用程式自訂意義的鎖的機制，這些鎖被稱為 advisory lock，
因為系統不會強制檢查它們的使用方式——是否正確使用完全由應用程式
自己負責」，並指出這類鎖「常見用途是模擬傳統『flat file』資料管理
系統中典型的悲觀鎖策略……advisory lock 比在資料表裡存一個旗標欄位
更快、不會造成資料表膨脹（table bloat），且伺服器會在連線結束時
自動清理」
（[PostgreSQL 官方文件 — Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html)）。【法規／安全必要層級的官方技術文件（PostgreSQL 專案自己的手冊）】

Neon 的官方指南本身**沒有**明確給出這個模式的效能上限或什�么時候
會不夠用（標記為指南本身未涵蓋的部分）；本輪另外查到一篇第三方
（非官方）部落格宣稱 advisory lock 這種模式單節點大約能撐到每秒
1.5 萬次請求量級——**這是二手來源，非官方確認，僅列為線索、不作為
事實引用**（[MVP Factory 部落格](https://mvpfactory.io/blog/postgresql-advisory-locks-for-distributed-rate-limiting-replacing-redis-in-your/)，二手，標記 UNVERIFIED）。
以 Option Chaser 目前與可預見的 controlled/public beta 規模而言，
真正的瓶頸幾乎肯定會先落在 Cboe 自己的 429 門檻與 Neon 的連線／
運算資源上（這個 repo 的 PERF-01 那一輪工程已經處理過 Postgres
連線生命週期的問題），而不會是 Postgres 計數器本身的吞吐量。

### 2.3 建議層級搭配（形狀，非數字）

業界的常態是**疊加**，不是三選一：
- Edge 層做便宜的粗篩（IP 為主，成本幾乎是零、現在就能開）；
- App＋Postgres 層做只有你的資料模型才懂的帳號形狀判斷（劇本數、
  刷新間隔）；
- 併發限制是速率限制之外**獨立的一個維度**——這點特別值得對照
  Option Chaser 自己的架構：現有的 `REFRESH_RUN_GROUP_LIMIT`／
  `REFRESH_RUN_BUDGET`／`IV_BACKFILL_DAY_CONCURRENCY=4` 全部都是
  **單一 invocation 內部**的併發／時間預算控制，管的是「這一次
  呼叫別跑太久」，但**沒有任何機制限制「同時有幾個不同的 owner／
  invocation 一起在打 Cboe」**——這是一個獨立於速率限制之外的
  真實缺口，Stripe 把它獨立列成第二種限流器正是因為這兩種問題
  （太頻繁 vs 太多同時進行）需要不同的機制去解決。

至於「這三層裡先做哪個、要不要三層都做」，留給 §6 的 grilling
選項清單，不在這裡替 Owner 決定。

---

## 3. 額度的形狀

任務點名四種額度：per-owner 劇本數上限、刷新最短間隔、每日分析量、
全站每日 vendor 呼叫預算（含 circuit breaker）。逐一對照這個 repo
現有的機制講清楚「這個額度在防什麼」。

### 3.1 per-owner 劇本數上限

**防的是什麼**：Refresh Trigger（見 CONTEXT.md 定義，開站／使用者
手動點刷新／建立新劇本三種既有時機之一）目前的邏輯是「刷新這個
owner 名下**全部**未過期劇本」（`refresh_run` 端點，見
`api_app/main.py`），**沒有**任何「最近剛刷過就跳過」的判斷。這代表
一個 owner 的劇本數，直接、線性地乘上每次 Refresh Trigger 要打幾次
Cboe、寫幾次 Postgres。這個 repo 自己過去為了完全不同的理由
（Neon 免費層儲存空間）就已經計算過「劇本數×刷新次數」如何直接
撞牆——CLAUDE.md 的 Scaling Foundation 章節記錄過 `results.view`
單列一度量到 12.18 MiB、推算「42 到 402 次刷新就會把 Neon Free
0.5 GB 寫滿」。**劇本數上限同時是防濫用的鍵，也是防儲存爆量的鍵**，
兩者是同一件事的兩面。

### 3.2 刷新最短間隔

**防的是什麼**：同一張劇本被連續、快速重複刷新，每次都是一次真的
Cboe 呼叫＋一次分析運算＋一次 Postgres 寫入。這是**現有事實清單裡
明確點名的缺口**——開站＝自動刷新全部未過期劇本，完全沒有「距離
上次刷新才過了幾秒，先跳過」的檢查。

業界的形狀參考（不是要照抄數字）：Stripe 對「同一個物件」設有獨立
於全域速率限制之外的專屬限制，例如「同一個 PaymentIntent 物件每小時
最多 1000 次更新請求」（[Stripe Rate Limits](https://docs.stripe.com/rate-limits)）——這個形狀剛好對應
Option Chaser「同一張劇本」這個單位，跟 §3.1 的「per-owner 全域」
是不同維度、可以並存的兩種額度。

### 3.3 每日分析量

**防的是什麼**：即使有劇本數上限＋刷新最短間隔，一個 owner 仍然
可以在一天內用「刪除舊劇本、建立新劇本」的方式反覆製造新的
Refresh Trigger（建立新劇本本身就是既有三個 Refresh Trigger 之一）。
每日分析量是防這種繞過模式的額外一層。

GitHub 官方文件示範的形狀值得參考（不是要照抄數字）：未驗證身份
的請求跟已驗證身份的請求，額度差了將近 100 倍（「未驗證請求的
主要限流是每小時 60 次」對比「你個人的限流是每小時 5,000 次」，
[GitHub REST API 限流文件](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)）。【業界慣例】
這給出一個形狀上的教訓：**匿名層的額度，通常比「已驗證身份」層
低很多，不是打對折，是差一個數量級**——如果 Option Chaser 未來加上
真正的帳號驗證（A-2，這個 repo 既有文件已經點名是 out of scope 的
未來工作），匿名 cookie 層的額度形狀上應該明顯低於未來驗證身份層，
不是兩者相等。

### 3.4 全站每日 vendor 呼叫預算與 circuit breaker

**現況已有的部分（被動）**：`chain_backoff.py` 是一個貨真價實的
circuit breaker（斷路器模式）——它的行為完全符合這個模式的經典
定義：「你把受保護的呼叫包在一個監控失敗次數的物件裡；一旦失敗次數
達到門檻，斷路器就會『跳開』，之後所有呼叫都直接回錯誤，連真正的
呼叫都不會發出去」，這個模式由 Michael Nygard 在《Release It!》
一書中提出、經 Martin Fowler 整理成三態模型（closed 正常／open
跳開拒絕／half-open 嘗試恢復）
（[Martin Fowler — CircuitBreaker](https://martinfowler.com/bliki/CircuitBreaker.html)）。【業界慣例，經典架構模式】
`chain_backoff.py` 的設計刻意是 **provider-global**（整個 Cboe
共用一個封鎖窗，不分 symbol）——這是 SCALE-04 既有裁示的結果，理由
是「沒有證據顯示 429 是 per-symbol，如果做成 per-symbol，使用者換個
symbol 就能繞過封鎖窗」。這個設計選擇很重要，會在「Admin 身份」
一節再次出現。

**現況缺的部分（主動）**：`metrics.py` 的 `METRIC_CATALOGUE` 已經
在記錄 `chain_fetch_count`／`chain_429_count` 這些數字（透過
`GET /api/ops/metrics` 這個 operator 專用端點可以查），但**這些數字
目前只用來給人看，沒有任何程式碼路徑會去讀這些數字、據此提前降級**。
今天唯一會觸發降級的時機是「Cboe 真的已經回了 429」——這是純粹被動
的斷路器；業界建議的做法是同時要有**主動**的一層：

- Google SRE Book 的 client-side throttling（客戶端自我節流）演算法：
  客戶端在過去兩分鐘的視窗內追蹤「應用層嘗試發出的請求數」與「後端
  真的接受的請求數」兩個數字，一旦前者超過後者的 K 倍（書中舉例
  K=2），客戶端就**在請求連網路都還沒發出去之前**、依照計算出的
  機率主動在本地拒絕：「超過上限的請求根本不會碰到網路就直接失敗」
  （[Google SRE Book — Handling Overload](https://sre.google/sre-book/handling-overload/)）。【業界慣例】
  這正是「主動」而非「被動」的示範——不是等對方說不行才停，是自己
  先估算「照這個速度下去大概快不行了」就先減速。
- Stripe 的 Fleet Usage Load Shedder：「為關鍵操作保留基礎設施容量，
  超出保留額度時拒絕非關鍵請求」——也是在真正資源耗盡**之前**先開始
  分級丟棄（[Stripe — Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)）。【業界慣例】

**「降級成只給舊資料」不是新概念，這個 repo 已經有兩個先例**：
1. UI 層面：既有的失敗卡片兩態設計（PC-05 等既有工作記錄）——曾經
   成功過的劇本，刷新失敗時顯示「更新失敗，目前顯示上一次成功結果」
   而非清空畫面，這在使用者體感上就是「服務過載時退回舊資料」的
   落地版本。
2. 資料層面：既有的 `rate_cache`／`dividend_cache`／
   `treasury_year_cache` 全部都有「陳舊備援窗」（過期還沒抓到新的，
   先沿用舊值並標記為陳舊，而非直接失敗），是同一個「寧可給舊的，
   別給不到」的哲學，套用在不同的資源上。

**因此**：全站每日 vendor 預算若要做，形狀上不必發明新哲學——只是
把「主動監看 `chain_fetch_count` 這個已經在記錄的數字、在還沒真的
撞到 429 之前就先切換成既有的『只給舊資料』模式」這件事實際寫成
程式碼，是既有 pattern 的第三次延伸，不是新架構。

---

## 4. 回應方式

### 4.1 HTTP 429 與 Retry-After 的正確用法

429 這個狀態碼由 IETF RFC 6585 定義，第 4 節原文：「429 狀態碼表示
使用者在一段時間內發送了太多請求（『限流』）」，並給出一個範例
回應：

```
HTTP/1.1 429 Too Many Requests
Content-Type: text/html
Retry-After: 3600

<html>
   <head><title>Too Many Requests</title></head>
   <body>
      <h1>Too Many Requests</h1>
      <p>I only allow 50 requests per hour to this Web site per
         logged in user.  Try again soon.</p>
   </body>
</html>
```

RFC 原文也提到「回應的內容表示應該包含說明這個狀況的細節，並可以
包含 `Retry-After` 標頭指出使用者該等多久再送新的請求」，且明確要求
「429 的回應不可以被快取存下來」（[RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html)）。【法規／安全必要，IETF 標準】

`Retry-After` 標頭本身的正式定義在現行 HTTP 語意規範 RFC 9110（第
10.2.3 節）：這個欄位「指出使用者代理應該在送出後續請求之前等待多久」，
允許兩種格式——一種是 HTTP 日期格式（時間戳），一種是 delay-seconds
（純數字，等待秒數）
（[RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html)）。【法規／安全必要，IETF 標準】

**這個 repo 已經有一半的正確實作**：`option_chaser/data/cboe.py`
的 `parse_retry_after()` 已經支援兩種合法格式（delta-seconds／
HTTP-date），根據其自己的 docstring 是照著 RFC 9110 寫的——這是
**vendor 面**的正確處理（解析 Cboe 回給我們的 Retry-After）。**缺的
是使用者面**：今天 Option Chaser 自己的 API 對前端從來不會回 429
（因為根本沒有任何限流機制），一旦加上 per-owner／per-IP 限流，
自己的 API 回應也應該遵循同一套 RFC 定義的形狀（429 狀態碼＋
`Retry-After` 標頭），這樣前端才能用同一套解析邏輯處理，不必為
「vendor 給我們的 429」跟「我們給使用者的 429」寫兩套不同的解析器。

### 4.2 前端 backoff＋jitter：避免 retry storm

**指數退避（exponential backoff）**：每次重試失敗就把等待時間乘上
一個固定倍數，直到某個上限。AWS 官方架構部落格《Exponential Backoff
And Jitter》一文（作者 Marc Brooker）指出：純粹的指數退避（沒有
隨機性）仍然會造成客戶端「叢聚」——原文：「仍然存在成批的呼叫叢集。
我們沒有減少每一輪裡競爭的客戶端數量，只是換成了有時候沒有客戶端
在競爭的空檔」（[AWS — Exponential Backoff And Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)）。【業界慣例】
換句話說：即使每個客戶端各自都在「退避」，只要大家都是同時失敗、
同時按照同一套固定公式退避，仍然會同步地一起重試，只是重試的間隔
被拉長而已，沒有真正打散。

**Jitter（抖動，在退避時間裡加入隨機性）**：AWS 這篇文章給出的
「Full Jitter」公式：

> `sleep = random(0, min(cap, base * 2 ^ attempt))`

（意思是：先照標準指數退避算出一個理論上限值，再從 0 到那個上限值
之間**隨機**取一個實際等待時間，而不是每次都固定照那個上限值等待。
`cap` 是設好的等待時間上限，避免無限拉長。）
這樣一來，即使所有客戶端在同一時刻失敗，各自算出來的真正等待時間
會被打散到整個範圍內，而不是全部集中在同一個值上，避免同步重試
造成的二次尖峰（[同上](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)）。【業界慣例】

**Google SRE Book 的 retry storm（重試風暴）防護**：書中列出三道
防線——(1) 每個請求最多重試 3 次；(2) 每個客戶端的重試量最多佔它
總流量的 10%；(3) 後端會在請求的中繼資料裡檢查「這個請求鏈路上已經
重試過幾次」，如果 histogram（統計分布）顯示大量請求已經被重試過，
代表整個系統正在過載，後端會直接回「不要再重試了」的錯誤，防止跨
多層服務的「組合爆炸式重試」（[Google SRE Book — Handling Overload](https://sre.google/sre-book/handling-overload/)）。【業界慣例】

**這個 repo 已經有的前端先例**：Cboe 429 倒數計時＋鎖定重試鈕
（`useCountdownSeconds()`／`isRetryDisabledByRateLimit()`，見
SCALE-05 既有工作記錄）——它讀的是一個**絕對時間點**
（`blocked_until`），畫面重新渲染不會讓倒數重置，並在封鎖窗內
直接鎖住重試鈕，不讓使用者手動連續重試造成 retry storm。這個
機制的資料形狀（`retry_after_seconds`／`blocked_until`／
`remaining_seconds`，見 `chain_backoff.status()`）跟一個
「per-owner 429」需要回給前端的資料形狀幾乎一樣——**如果新的
per-owner 429 用同一組欄位名稱，這個既有元件很可能可以幾乎原樣
重用**，不必重刻一套新的倒數 UI。

**⚠ 一個值得在實作時注意的風險，本輪只提出、不裁決**：現有的
Refresh Run Continuation（前端自動追著 `remaining` 欄位、只要非空
就立刻打下一次請求）是為「還有工作沒做完」設計的迴圈。如果未來某次
迴圈中途卡住的原因變成「這個 owner 被限流了」而不是「還有 symbol
分組沒處理完」，這個迴圈如果原封不動重用，可能會在完全沒有 backoff
的情況下對自己剛觸發的 429 迅速連續重試——這正是 retry storm 的
定義。落地時需要明確判斷「是限流回應」還是「還有工作」，兩者不能
共用同一個「非空就立刻重打」的邏輯，否則就是自己做出一個小型
retry storm 產生器。這是一個實作提醒，不是本輪要決定的事。

---

## 5. 惡意 vs 正常的區分

### 5.1 漸進式處置：業界一致收斂到「先觀察、後動手」

至少三個獨立廠商的官方文件都把「先用 Log／Count（只記錄不擋）觀察，
再升級成 Challenge／Deny（挑戰或直接擋）」當作標準建議路徑：

- Vercel WAF 規則的 Log 動作官方說明：「Log 動作不會執行任何封鎖。
  你可以用它在套用限流或封鎖動作之前，先觀察效果」
  （[Vercel WAF Rate Limiting](https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting)）。
- Cloudflare 的限流規則同樣把「符合規則」（matching）與「動作」
  （action）分開設計，可以先只匹配不動作觀察一段時間
  （[Cloudflare Rate Limiting Rules](https://developers.cloudflare.com/waf/rate-limiting-rules/)）。
- AWS WAF 的 rate-based rule 動作可以設成「Count」（只計數，不擋）
  觀察一段時間再改成真的封鎖（[AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html)）。

【業界慣例，三家獨立廠商官方文件一致收斂】

### 5.2 Vercel Attack Challenge Mode

**機制**：訪客必須通過一個 JavaScript 挑戰（證明自己是真的、有 JS
能力的瀏覽器，不是腳本或爬蟲）才能存取網站，已知的合法機器人（搜尋
引擎爬蟲、webhook 供應商）自動放行。**在所有方案上免費，被 Attack
Mode 擋下的流量不計入用量、完全免費不設上限**
（[Vercel Attack Mode](https://vercel.com/docs/vercel-firewall/attack-mode)）。【業界慣例，且是這個 repo 部署平台的免費現成功能】
過關後的 session（會話）有效期是 1 小時，這段時間內同一瀏覽器的
後續請求都自動放行。**已知限制**：官方文件明講「獨立的 API、其他
後端框架、未被辨識的自動化服務可能無法通過挑戰而被擋下」，且提到
一個具體的相容例子——「一個 Next.js 前端呼叫同一個專案裡的 Next.js
API 可以正常運作」（[同上](https://vercel.com/docs/vercel-firewall/attack-mode)）。Option Chaser 是「同網域的 React SPA 呼叫
同專案的 FastAPI」，架構形狀上跟這個例子類似，但**不是**逐字相同的
Next.js 設定——標記 **UNVERIFIED**：Vite＋FastAPI-on-Vercel 這種
組合是否享有完全相同的保證，建議實際啟用前先在測試環境驗證一次。

### 5.3 Vercel Bot Management 與已驗證機器人

Vercel 的官方說明把 bot management 拆成幾種手法：「signature-based
detection（比對已知機器人特徵）」「rate limiting」「JavaScript
challenge」「behavioral analysis（行為模式分析）」，並維護一份持續
更新的「已驗證機器人」名單，用三種方式證明機器人身份：**IP 位址範圍
驗證**、**反向 DNS 查詢**（確認 IP 真的能反解回宣稱的網域）、**加密
簽章驗證**（透過 Web Bot Auth，一種基於 HTTP 訊息簽章 RFC 9421 的
機制）（[Vercel Bot Management](https://vercel.com/docs/bot-management)）。【業界慣例】
這個「已知、可驗證的身份放行清單」概念，會在「Admin 身份」一節
被拿來類比 admin／controlled-beta 測試身份該怎麼設計。

### 5.4 CAPTCHA 成本：Turnstile 與 hCaptcha

**Cloudflare Turnstile**：2023 年正式發佈時官方部落格明講：
「Turnstile 的『Managed』模式現在對所有人完全免費、無限次使用」，
且明確定位為對抗「自動化帳號註冊，這類行為可能包含『新帳號詐騙』」
——官方數據：單月封鎖超過 100 萬次自動化註冊嘗試
（[Cloudflare — Turnstile is free for everyone](https://blog.cloudflare.com/turnstile-ga/)）。【業界慣例】
它與傳統 CAPTCHA 的差異：不需要視覺解謎（對低視力／視障使用者較
友善），不依賴追蹤使用者曾造訪過哪些其他網站來判斷是否為人類，改用
瀏覽器背景特徵檢測與輕量的 proof-of-work（一種需要付出一點計算成本
才能通過的測試）（[同上](https://blog.cloudflare.com/turnstile-ga/)）。
這個定位——「對抗自動化帳號註冊」——跟這張票要防的「有人一直開新
匿名 cookie 身份」高度吻合，值得列入考慮。

**hCaptcha**：Basic（免費）方案「$0，無明確使用上限」；Pro 方案
每月 99–139 美元（依年繳／月繳），內含每月 10 萬次驗證，超額
每千次 0.99 美元（[hCaptcha Pricing](https://www.hcaptcha.com/pricing)）。【業界慣例】

兩者的免費層在 controlled／public beta 這種規模下實際上都近似
「無限」，付費層的成本只有在真正達到生產規模時才會變成需要認真
考慮的議題——CAPTCHA 本身的**金錢成本**在這個階段基本不是問題，
真正該權衡的是**使用者體感摩擦力**（要不要為了防濫用讓每個人多按
一次驗證），這屬於產品決策，留給 §6。

### 5.5 OWASP 官方防護清單

OWASP（開放網路軟體安全計畫）API Security Top 10 2023 版
API4:2023「不受限資源消耗」（Unrestricted Resource Consumption）
的官方「How to Prevent」清單全文：

1. 「使用能輕鬆限制記憶體、CPU、重啟次數、檔案描述符與行程數量的
   方案，例如容器／serverless code（如 Lambda）」
2. 「對所有傳入的參數與 payload 定義並強制執行最大資料大小，例如
   字串最大長度、陣列最大元素數、上傳檔案最大大小（不論存放在本地
   或雲端儲存空間）」
3. 「實作限制客戶端在一段固定時間內能與 API 互動的頻率（rate
   limiting）」
4. 「rate limiting 應該依商業需求微調，某些 API 端點可能需要更嚴格
   的政策」
5. 「限制／節流單一 API 客戶端／使用者能執行同一個操作的次數或頻率
   （例如驗證一次性密碼，或在沒有造訪一次性連結的情況下重複要求
   密碼重設）」
6. 「對查詢字串與請求主體參數加上適當的伺服器端驗證，特別是控制
   回應中要回傳幾筆紀錄的那個參數」
7. 「為所有服務供應商／API 整合設定支出上限；如果無法設定支出上限，
   應該設定帳單警示」

（[OWASP API Security Top 10 2023 — API4:2023](https://raw.githubusercontent.com/OWASP/API-Security/master/editions/2023/en/0xa4-unrestricted-resource-consumption.md)，官方原始碼庫版本）【法規／安全必要，OWASP 官方標準】

這份清單裡的第 7 條——「為服務供應商整合設定支出上限」——直接對應
這張票要問的「全站每日 vendor 呼叫預算」這個項目，等於是 OWASP 官方
標準把它列為標準防護項目之一，不是這個 repo 自己發明的額外要求。

### 5.6 一個值得特別點名的既有設計張力

Stripe 的官方文件把限流講成不只是防濫用，也是**公平性**問題：
一個使用者的流量尖峰不應該拖累其他所有人的服務品質——這正是他們
把 rate limiter（使用者可以自己分散流量）跟 load shedder（系統
狀態判斷，跟使用者行為無關）分開設計的原因
（[Stripe — Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)）。

這個原則直接照出 Option Chaser 現有設計的一個真實張力：`chain_
backoff` 刻意做成 **provider-global**（不分使用者），這個設計的
好處是防住了「換個 symbol 就繞過封鎖窗」，但代價是——**一個 owner
的重度使用（大量劇本、頻繁刷新）如果真的把 Cboe 打到 429，封鎖窗
會讓當下所有其他匿名 owner 一起被鎖住**，不分是誰造成的。這不是
bug，是這個設計選擇當年（SCALE-04／#255）就接受的代價，但它也
正好說明為什麼 §3 的 per-owner／per-IP 額度需要存在——**限流的
真正目的，除了防惡意，也是保護「provider-global 斷路器不要那麼容易
被任何一個帳號單獨觸發」**，兩件事互相支撐。

---

## 6. Admin 身份與 controlled-beta 壓測流量在限流體系裡的位置

Owner 追加範圍的三個小題，逐一回答。

### 6.1 Admin／superuser 要不要完全繞過限流

**業界怎麼處理「管理者自己測試系統」跟「一般使用者被限流」的關係**：

三個真實廠商產品都有正式的「trusted bypass」概念，但**沒有一個
把它做成「這個身份完全等於不受限」的單一開關**，而是「範圍明確界定
的例外路徑」：

- Vercel Firewall 官方對 **Bypass** 動作的定義：「Bypass 動作允許
  特定流量跳過後續的防火牆規則……這對信任的流量來源、內部工具、或
  不該被擋下的關鍵服務很有用」，並在 Challenge 動作的說明裡直接
  建議：「對於合法的自動化需求，使用 Bypass 讓特定信任來源通過」
  （[Vercel Firewall Concepts — Bypass](https://vercel.com/docs/vercel-firewall/firewall-concepts)）。【業界慣例】
- Vercel Attack Mode 對「Internal Requests」（自家帳號內的
  Functions／Cron Jobs）自動放行，但**範圍嚴格限制在帳號邊界內**：
  「只有你自己帳號外部的請求才會被挑戰……其他 Vercel 帳號無法繞過
  你專案上的 Attack Mode，安全邊界嚴格以帳號為單位」
  （[Vercel Attack Mode — Internal requests](https://vercel.com/docs/vercel-firewall/attack-mode)）。【業界慣例】——這代表「管理者的內部呼叫自動放行」這個概念是真實存在的業界模式，但它的邊界是明確、可稽核、無法被外部冒用的（帳號本身的邊界，不是一個可以被偷走的通用旗標）。
- **一個更值得注意的反例**：Stripe 自己維護獨立的 test mode
  （沙盒環境），但這個「管理者／測試身份」拿到的限制**不是更寬鬆，
  反而更嚴格**——官方文件明講：「如果你的測試環境請求回 429 錯誤，
  請降低請求頻率。測試環境的限流比 live mode 更嚴格」，並且明確
  勸阻：「不要拿測試環境去做整合的壓力測試，因為你可能會撞到限流」，
  建議改用「可設定的 mock 系統，把對 Stripe API 的請求假造掉，
  在壓力測試時啟用」（[Stripe Testing — Rate limits](https://docs.stripe.com/testing)；[Stripe Rate Limits — Load testing](https://docs.stripe.com/rate-limits)）。【業界慣例，且是特別具啟發性的一個反例】

**風險**：如果 admin 身份做成「完全不受限」，一旦這個身份的憑證
（credential）被冒用或誤用，等於一次性繞過系統裡**所有**其他保護
機制——這是把系統裡最大單一風險點集中到一個地方。OWASP API2:2023
（Broken Authentication，認證機制被破解）官方文件的其中一條防護
建議直接點名：「API 金鑰不應該用於使用者認證，只應該用於 API
客戶端認證」（[OWASP API2:2023](https://raw.githubusercontent.com/OWASP/API-Security/master/editions/2023/en/0xa2-broken-authentication.md)，官方原始碼庫版本）——這雖然不是逐字討論
「admin 繞過限流」這個場景，但延伸的邏輯是一致的：任何一個憑證能
授予的權力範圍越大、越接近「無限」，這個憑證洩漏或被誤用時造成的
損害就越大，應該傾向讓憑證的授權範圍盡量窄。

**這個 repo 自己已經有現成、符合上述業界模式的範本**：`main.py`
裡的 `CRON_SECRET`／`OPS_SECRET`——兩個**各自獨立**的 Bearer token
（HTTP 驗證標頭裡帶的一段密鑰字串），CLAUDE.md 記錄的既有裁示原文
是「兩種不同信任邊界不共用一把」。這正是「範圍明確界定、各司其職的
信任邊界」而非「一個萬能開關」的設計哲學。Admin／controlled-beta
身份延續這個既有慣例是最一致的做法——**它應該是自己專屬的一把
secret，不是借用 `CRON_SECRET` 或 `OPS_SECRET`**，且授予的額度
應該是「明顯高於一般匿名 owner，但仍然有限」的獨立額度桶，而不是
完全不受任何額度約束（形狀建議，非數字）。

### 6.2 controlled beta 的 synthetic 流量怎麼跟真實濫用流量區分

**業界對「這是自己在做負載測試」與「這是有人在攻擊」的辨別方式**：

真正的一手業界做法幾乎都依賴**獨立的 staging／測試環境**——這正是
Owner 本輪明確點出的現實限制（Option Chaser 只有單一 production
環境，沒有獨立 staging）。在這個限制下，兩條可行的替代路：

1. **已知測試身份白名單，比照 Vercel 已驗證機器人名單的做法**：
   Vercel 用 IP 範圍驗證、反向 DNS、加密簽章三種方式證明「這個流量
   真的是它宣稱的那個已知服務」（見 §5.3）。同一個原理可以類比套用
   到 controlled beta——用一個**簽署過的、只有 admin 能發出的**
   身份憑證（延續 §6.1 建議的獨立 secret 模式），讓限流 middleware
   認得「這是已知的測試身份」，但這個識別**不等於「不限」**，而是
   對應到一個獨立、時效內的額度桶，跟一般匿名 owner 的額度桶分開
   計算——這樣測試流量不會污染真實使用者的額度統計，也不會變成
   一個無上限的後門。
2. **限時放寬，只在 controlled beta 期間生效**（Owner 原話）：
   架構上這就是「一個額度覆寫規則，鍵是身份＋可選的到期時間」，
   本質跟 AWS WAF／Cloudflare 讓一條規則透過 scope-down statement
   （縮小規則適用範圍的條件式陳述）／counting expression（自訂
   計數條件）只套用在特定已知子集流量上是同一種機制形狀——這些
   廠商的工具本來就是為「讓某條規則對已知的特定流量表現不同」
   設計的，不是要發明新東西。

**Stripe 測試模式的教訓再次適用**：Stripe 自己有真正獨立的 test
mode，卻仍然告誡不要拿它做壓測，理由是 test mode 本身的下游行為
（例如信用卡收款）跟 live mode 不完全一樣，用測試環境的量體去外推
生產環境的真實行為本身就不準——「用 sandbox 建立一筆收款會送一個
請求給付款閘道，這個請求在 sandbox 裡是被 mock 掉的，導致延遲曲線
差異很大」（[Stripe Rate Limits — Load testing](https://docs.stripe.com/rate-limits)）。**這句話反過來也支持
Owner 的做法是對的**：Owner 要求的不是「假造一個獨立環境」，而是
「synthetic 使用者真的打同一套 production 程式碼路徑」，這比 Stripe
描述的那種會失真的假環境測試方式更貼近真實——**但代價是這批
synthetic 流量若真的走到底層 vendor 呼叫，就會消耗真實、有限的
Cboe 配額**，這正是 §6.3 要處理的問題。

**這個 repo 剛好已經有現成的解法**：整套後端測試（`tests/`）大量
使用 `create_app(fetch=..., rate_loader=..., dividend_loader=...)`
這種依賴注入（dependency injection，讓呼叫端決定要用真的還是假的
實作）介面，讓測試可以走完整條 request→response 的程式碼路徑，
但底層真正打 Cboe／Treasury／Dividend 的那一步被換成假體
（fake）。controlled-beta 的壓測 harness（測試用的驅動框架）如果
用同一組現成的注入點，就能達到「真的打同一套限流／middleware
程式碼路徑」＋「不真的消耗 Cboe 配額」兩個目標同時成立——這正是
Stripe 建議的「可設定的 mock 系統」的精神，且不需要另外發明，
接口早就存在於這個 repo 的測試套件裡。

### 6.3 Admin 端點要不要算進全站 vendor 呼叫預算

**答案是：如果 admin 呼叫真的走到 vendor（Cboe），沒有技術手段可以
讓它不算進同一個配額。** 理由是純粹的物理限制：

- Cboe 的 429 限流是 Cboe 自己伺服器端判斷的，它不知道、也不會去
  區分「這次請求是 Option Chaser 內部哪個角色發起的」——它看到的
  只是打進來的 HTTP 請求。
- 這個 repo 現有的 `chain_backoff` 設計又是刻意的 **provider-global**
  （不分 symbol、更不分使用者身份，見 §3.4／§5.6）——這個封鎖窗的
  定義範圍就是「整個 Cboe 這個 provider」，admin 呼叫如果走這條路徑，
  結構上就一定共用同一個封鎖窗狀態，沒有「admin 專屬旁道」這種選項
  存在於現有架構裡（除非另外設計一套完全獨立的 backoff 狀態鍵，
  但那會違背 SCALE-04 當年「provider-global 才安全，per-key 會被
  繞過」的既有裁示邏輯——一旦有第二套鍵存在，理論上就有繞過封鎖窗
  的路可走，即使那個路是「你是 admin」而非「換個 symbol」）。

**因此**：如果 controlled-beta 的壓測沒有走 §6.2 建議的 mock 路徑，
而是真的打了 production 的 Cboe 呼叫，那它確實有可能觸發同一個
provider-global 429 封鎖窗，進而讓**同一時段真實的一般使用者**跟著
被鎖住——這是一個真實、可預期、由這個 repo 現有架構直接決定的
交互作用，不是理論上的謹慎。這也是本輪查證後最確定的一條結論，直接
回答了 Owner 提出的疑問。

**這個交互作用要不要在額度設計裡特別處理，是一個真正的設計問題，
本輪不代替 Owner 決定**，但可以指出一個既有的相關張力：`metrics.py`
的 `METRIC_CATALOGUE` 目前只允許 `source`／`symbol` 兩個維度，
**明確不允許 `owner_id`**——模組自己的 docstring 寫著「不存
`scenario_id`、`owner_id`、任何報價／合約／chain payload」，理由是
這套系統是刻意做成 system-wide（不分 owner）、跟 owner-scoped 的
`diagnostics` 系統分開。如果未來想在 `/api/ops/metrics` 儀表板上
分清楚「今天的 vendor 預算有多少是被 controlled-beta 測試吃掉、
多少是真實使用者吃掉」，這會需要一個新的維度（例如「是否為已知測試
身份」），而這件事跟現有「不存 owner_id」的隱私範圍規則之間的關係
需要重新考慮——這是一個值得放進 grilling 票的具體問題（見 §7 的
OD-12），不在這裡預先決定。

---

## 7. 這對 Option Chaser 意味著什麼

把上面所有研究收斂成幾條跟這個 repo 現有程式碼直接對得上的觀察：

1. **最高槙桿、成本最低的單一改動**：Refresh Trigger 加一個「距離
   上次刷新未滿最短間隔就跳過」的 Postgres 時間戳檢查——這既是防
   濫用（§3.2），也是這個 repo 自己過去因為儲存空間理由就已經在
   意的同一個問題的另一面。
2. **現有的 circuit breaker 只有被動那一半**：`chain_backoff` 要
   等 Cboe 真的 429 才啟動；`metrics.py` 已經在記錄需要的原始數字
   （`chain_fetch_count`），但沒有任何程式碼路徑主動讀它、據此提前
   降級。補上這一段是既有模式的延伸，不是新架構（§3.4）。
3. **前端已經有可重用的 429 UI 元件**：如果新的 per-owner／
   per-IP 429 回應用同一組欄位形狀（`retry_after_seconds`／
   `blocked_until`），既有的倒數計時＋鎖定重試鈕元件很可能可以
   幾乎原樣重用（§4.2）。
4. **這個平台（Vercel）已經免費附贈了一層可以現在就開的防護**：
   WAF Rate Limiting（IP／JA4 為鍵）＋Attack Mode，兩者在 Hobby／
   Pro 方案上都不需要另外付費就能用，且不需要改一行程式碼（§2.2、
   §5.2）。
5. **只有 Postgres、沒有 Redis 這件事不是新挑戰**：這個 repo 已經
   用「一張表當共用計數器、fail-open」的模式跑了兩次（`chain_
   backoff`／`metrics`），且這個模式恰好是 Neon（這個 repo 實際的
   Postgres 供應商）自己官方推薦的做法（§2.2）。
6. **Admin／controlled-beta 身份的兩個既有範本直接可用**：獨立
   Bearer secret（比照 `CRON_SECRET`／`OPS_SECRET`）、以及測試
   套件既有的 `fetch=`／`rate_loader=` 依賴注入介面（可以讓
   controlled-beta 壓測完全不消耗真實 Cboe 配額）（§6.1、§6.2）。
7. **一個必須誠實面對、無法用架構繞過的物理限制**：只要 admin
   走真實 vendor 路徑，就一定共用同一個 provider-global 429 封鎖窗，
   會影響到當下真實使用者——這不是可以「設計」掉的問題，只能靠
   §6.2 建議的 mock 路徑從源頭避免（§6.3）。
8. **一個尚待解決的觀測維度問題**：`metrics.py` 現有的隱私範圍規則
   （不存 `owner_id`）跟「想要分清楚 vendor 預算被誰吃掉」的需求
   之間有真實的張力，需要另外決定（§6.3、§7 OD-12）。

---

## 8. 額度與濫用防護 grilling 票應該問 Owner 的選項

以下全部選項只列**形狀**與**代價**，不建議任何具體數字。分成
「第一天就該有」（缺了會讓 controlled/public beta 直接暴露在已知
風險裡）與「看到 abuse 再做」（可以先上線觀察、之後再補）兩欄。

### 第一天就該有

```
OD-1：要不要有「per-owner 劇本數上限」這個機制本身（不是幾張，是
要不要有上限）
這題其實在決定什麼：Refresh Trigger 目前會刷新一個 owner 名下全部
未過期劇本，沒有上限代表劇本數可以無限成長，每一次刷新的成本
（Cboe 呼叫次數、Postgres 寫入量）會跟著無限放大——這不是理論
風險，是這個 repo 自己過去就已經因為 Neon 免費層儲存空間算過同一
筆帳（12.18 MiB／列、42–402 次刷新填滿 0.5 GB）。
A：不設上限，先觀察 controlled beta 有沒有人真的濫用再決定。
B：設一個上限機制，但先給一個「肉眼看起來很寬鬆」的初始值（業界
常見的免費層額度形狀差異很大，從個位數到幾十都有先例，取決於產品
定位），之後看真實使用數據再調。
C：分兩層——一般匿名 owner 一個較低上限，未來若有驗證身份機制
（A-2）則另一層較高上限（比照 GitHub 未驗證 60/hr vs 已驗證
5,000/hr 那種數量級差距的形狀，而非照抄數字）。
你的建議：B——上限機制的「存在」本身比「數字多少」更急迫，先有
開關，數字可以隨時調，沒有開關的話現在就是無限。
不現在決定會卡住什麼：controlled beta 的 synthetic bot 流量本身
就可能無限建立劇本，若沒有上限，這個測試流量本身就會製造出跟
真實濫用一樣的資源消耗模式，測試會提早撞到 Cboe／Neon 的真實極限。
```

```
OD-2：Refresh Trigger 要不要加「距離上次刷新太近就跳過」的判斷
這題其實在決定什麼：這是現有事實清單裡明確點名的缺口——開站就是
全部未過期劇本一起刷新，完全沒有「最近剛刷過」的判斷。這是成本
最低、槙桿最高的一個改動：一個 Postgres 時間戳比對就能實作。
A：不加，維持現狀，靠 §3.1 的劇本數上限間接限制總量。
B：加一個判斷，形狀是「劇本層級」（同一張劇本多久內不重複刷新）
還是「owner 層級」（同一個 owner 多久內不能觸發整批刷新）兩者
可以並存，也可以只做一種先看效果。
C：不是硬擋，是軟性提示——距離上次刷新太近時前端直接不送這次
Refresh Trigger（使用者體感等同 B，但不需要後端回 429，純前端
判斷即可，只是防不了直接打 API 的情況）。
你的建議：B（劇本層級優先）——這正好對應到會員最直接的成本
（Cboe 呼叫次數×Postgres 寫入量），且跟劇本數上限是互補、不是
取代關係。
不現在決定會卡住什麼：這是所有防濫用機制裡投入產出比最高的一項，
延後等於白白放著一個已知、成本最低的缺口不補。
```

```
OD-3：要不要在真的撞到 Cboe 429 之前，先有一個主動的「全站每日
vendor 呼叫預算」降級開關
這題其實在決定什麼：現有的 chain_backoff 是被動斷路器（要先被
Cboe 擋才啟動）；業界（Google SRE、Stripe）都建議同時要有主動的
一層，在真的耗盡之前先自己降速／降級。這個 repo 已經在記錄需要的
原始數字（chain_fetch_count），只差讀它並據此動作的程式碼。
A：不做，維持現有的被動斷路器就好，反正它已經能兜底。
B：做一個簡單的每日計數門檻，超過門檻就把「還沒抓到今天資料的
劇本」自動降級成沿用舊資料（比照既有 rate_cache／dividend_cache
的陳舊備援窗設計），不擋新請求，只是不再嘗試抓新資料。
C：跟 B 類似，但門檻依 controlled-beta 與 public-beta 兩個階段
各自獨立設定（因為兩階段的預期流量型態不同）。
你的建議：B——先有這個開關存在，比精確調對門檻更重要；且落地
方式可以完全沿用既有的「陳舊備援」既有模式，不必發明新的降級行為。
不現在決定會卡住什麼：controlled beta 的 synthetic 壓測若走真實
vendor 路徑（見 OD-6），本身就有很高機率成為第一個把 Cboe 打到
429 的流量來源，屆時只有被動斷路器會讓「發現極限」跟「真實使用者
被連坐」變成同一個時刻發生。
```

```
OD-4：IP 限流要放在 edge（Vercel WAF dashboard 規則）、app 層
（自己寫），還是兩者都要
這題其實在決定什麼：edge 層今天就能免費開（Vercel Hobby 方案內含
1 條規則、100 萬次額度，鍵可選 IP／JA4 Digest），零程式碼改動；
app 層才能表達帳號形狀的判斷（劇本數、刷新間隔）。這不是互斥選項，
是「先做哪個」與「要不要兩個都做」的問題。
A：只做 edge 層——最低成本，但擋不住「同一個 IP 底下的合法使用者
被誤傷」這個既有已知的 CGNAT／NAT 問題（見 §1.2），也表達不了
帳號形狀。
B：只做 app 層——能精確表達帳號邏輯，但每個惡意請求都要真的進到
App、消耗一次 Postgres 查詢才會被擋，比 edge 層貴。
C：兩層都做——edge 層當粗篩（擋掉最明顯的流量洪水），app 層做
精確的帳號額度判斷；這是業界最常見的疊加形狀（§2.3）。
你的建議：C，但可以分兩步上線——edge 層（純 dashboard 設定，
零程式碼）可以在 OD-2／OD-1 的程式碼還沒寫完前就先開，因為它完全
不需要等其他任何票完工。
不現在決定會卡住什麼：edge 層不上不會立刻造成資源耗盡（有 app 層
兜底），純粹是放著一個免費、現成、零成本的選項不用；但如果完全
不開，某些單純的流量洪水（例如單一 IP 短時間內狂發請求）會一路
打到 App 層才被擋下，比在 edge 層擋掉貴得多。
```

```
OD-5：Admin／superuser 身份要用哪種模式——完全繞過限流、獨立但
有限額度、還是走獨立測試端點
這題其實在決定什麼：Owner 已裁示 admin 是正式、獨立於一般匿名
owner 的身份，但這個身份「不受限的程度」直接決定了它一旦被冒用
的最大損害範圍。這是本輪查證後判斷最應該優先定案的一題，因為它
決定了「其他額度的數字設多少」在 admin 身上是否有意義。
A：完全繞過——admin 身份完全不受任何限流／額度檢查。實作最簡單，
但正是本輪引用的業界反例（Stripe test mode 反而更嚴、不是更寬）
與 OWASP API2:2023（API 金鑰不該當使用者認證用）共同指出風險最高
的選項。
B：獨立但有限的額度桶——admin 走同一套限流機制，但套用一組明顯
更寬鬆、獨立計算的額度（不跟一般匿名 owner 共用同一個計數器）。
跟這個 repo 既有的 CRON_SECRET／OPS_SECRET「各自獨立信任邊界」
慣例一致。
C：走獨立的測試專用端點——admin 的壓測完全不經過一般使用者會走
的 API 路徑，而是另一組專門給測試用的端點（例如直接注入假資料，
完全不碰真實 vendor／一般業務邏輯）。隔離最徹底，但需要額外維護
一組平行端點。
你的建議：B——沿用既有的獨立 secret 慣例，風險與工程成本都最
平衡；C 可以是 B 之外「壓測 vendor 呼叫本身」那部分的補充做法
（見 OD-6），不必取代 B。
不現在決定會卡住什麼：如果先用 A（完全繞過）上線、之後才想收緊，
會變成「拿掉一個已經在用的權限」，比一開始就選 B 更容易引發抱怨
或誤判成故障；先定案能避免這種回頭收緊的摩擦。
```

```
OD-6：controlled-beta 的壓測流量，要不要強制走 mock vendor 的
路徑，不准打真實 Cboe
這題其實在決定什麼：這是本輪查證後最明確的一條結論——admin／
synthetic 流量如果真的打到 Cboe，一定會跟真實使用者共用同一個
provider-global 429 封鎖窗（chain_backoff 的既有設計就是這樣，
無法繞過）。這題決定的是「controlled beta 的壓力測試會不會誤傷
同一時段的真實使用者」。
A：不強制——synthetic 流量走完整真實路徑，包含真的打 Cboe。最
貼近「production 下的真實行為」，但有實測會觸發 429、連坐真實
使用者的風險。
B：強制 mock——synthetic 流量必須用這個 repo 測試套件既有的
fetch=／rate_loader=／dividend_loader= 這類依賴注入接口，走完整
限流／middleware 程式碼路徑，但底層 vendor 呼叫被替換成假資料。
C：分兩階段——初期（驗證限流機制本身）用 B，後期（想驗證真實
vendor 互動下的整體行為）用 A，但限制在流量很小的窗口內。
你的建議：B 為主，C 為輔——這是 Stripe 自己對「不要拿測試環境
真的去打下游服務」給出的具體建議在這個架構下的落地方式，且這個
repo 已經有現成的注入點可以直接借用，工程成本很低。
不現在決定會卡住什麼：如果沒有明確要求 B，執行 controlled beta
壓測的人很容易「圖方便」直接打 production 的 Cboe，這件事一旦
發生、觸發封鎖窗，會直接影響同一時段的真實使用者體感，且發生後
才發現會比事先規定困難得多去追查原因。
```

### 看到 abuse 再做

```
OD-7：三種身份鍵（cookie／IP／裝置指紋）要不要疊加成組合鍵，疊
幾層
這題其實在決定什麼：業界標準是疊加不是三選一（§1），但「現在就
把三層全部疊上去」跟「先上一層，等看到單層被繞過的證據再加下
一層」是不同的工程與體驗成本。
A：只上 cookie＋IP 兩層（app 層帳號邏輯＋edge 層粗篩），暫不引入
裝置指紋。
B：三層全上，包含裝置指紋（可以先用 Vercel 免費附贈的 JA4
Digest，不必額外整合第三方指紋服務）。
C：先上一層（例如只有 IP），觀察 abuse 樣態後再決定要不要加
cookie／指紋。
你的建議：A 作為 day-1（見上一欄），指紋（B 的延伸）等到觀察到
「同一批行為明顯在清 cookie／換 IP 規避」的具體樣態才加——這正是
「疊加訊號」該在什麼時候疊加的自然時機，不必預先猜。
不現在決定會卡住什麼：不會卡住任何東西——A 已經是可用的基礎
防線，指紋是精進而非必要條件。
```

```
OD-8：CAPTCHA／人類驗證機制（Turnstile 等）要不要接，接在哪個
動作上
這題其實在決定什麼：Turnstile／hCaptcha 免費層在 beta 規模下
金錢成本近乎零，真正的成本是使用者體感摩擦力——業界慣例是先用
Log／軟性限流觀察，CAPTCHA 通常是升級路徑裡比較後面的一階
（§5.1）。
A：不接，先靠 §3／§4 的額度與 429 機制。
B：接在「建立新劇本」這個動作上（對應這張票點名的「一直開新
cookie、一直建劇本」情境，摩擦最小、只影響低頻動作）。
C：接在所有寫入型操作上（建立劇本＋觸發刷新），防護面更廣但
使用者體感摩擦也更大。
你的建議：先不接（A），等額度機制上線後觀察是否仍有繞過——如果
觀察到大量「一直清 cookie 重開帳號」的樣態，B 是成本最低、最
精準對應這個樣態的下一步。
不現在決定會卡住什麼：不會卡住任何東西——Turnstile／hCaptcha
接入成本低，隨時可以在觀察到需求後再加，不需要提前準備。
```

```
OD-9：漸進式處置（軟上限→挑戰→暫時封鎖）的階梯要幾階、每階觸發
條件與持續時間
這題其實在決定什麼：業界普遍採用多階（Log→Challenge→Deny 這種
形狀在 Vercel／Cloudflare／AWS 三家都能看到），但具體幾階、每階
維持多久，是需要真實 abuse 樣態才能校準的參數，不是可以憑空猜對
的數字。
A：先做兩階（軟上限→封鎖），不做中間的 Challenge 階段。
B：完整三階（軟上限→Challenge→暫時封鎖）。
C：階梯數視觸發的動作類型而不同（例如「建立劇本」跟「觸發刷新」
可以有不同的階梯設計）。
你的建議：A 開始（跟 §3／§4 的基本額度機制一起上線），B／C 留給
真正觀察到 abuse 之後，因為 Challenge 階段的加入時機本身也適合
放進 OD-8 一起考慮。
不現在決定會卡住什麼：不會，A 已經是一個完整可運作的最小版本，
B／C 是精進。
```

```
OD-10：要不要引入裝置指紋（JA3/JA4 或第三方指紋服務）當第三個
訊號
這題其實在決定什麼：跟 OD-7 是同一個決策的不同角度——裝置指紋
主要用來抓「清 cookie＋換 IP 一起繞過」這種更費力的規避行為，
在 controlled/public beta 這種規模，這類規避者出現的機率與造成
的損害都還是未知數。
A：完全不引入，維持 cookie＋IP。
B：先用 Vercel 免費附贈的 JA4 Digest（零額外整合成本），不接
第三方指紋服務。
C：接第三方指紋服務（例如 FingerprintJS 這類商業產品），準確度
較高但需要額外整合與（超過免費額度後的）成本。
你的建議：等看到具體規避樣態才選——如果真的要加，B 是成本最低
的第一步，C 只在 B 明顯不夠用時才考慮。
不現在決定會卡住什麼：不會，這是純粹的精進項目。
```

```
OD-11：全域 vendor 預算耗盡後的「降級」要降到什麼程度
這題其實在決定什麼：OD-3 決定的是「要不要有這個主動降級開關」，
這題決定的是「開關觸發之後，畫面上／行為上具體變成什麼樣子」——
可以先粗糙、之後再精修，不影響機制本身能不能上線。
A：最粗糙版本——直接回一個明確的錯誤／提示訊息，不嘗試抓新資料，
但也不特別美化 UX。
B：比照既有 rate_cache／dividend_cache 的陳舊備援窗設計，沿用
舊資料並在畫面上標示「資料可能不是最新」。
C：更進一步，依重要性分級（比照 Google SRE Book 的 criticality
概念）——例如「開站自動刷新」先被降級，「使用者手動點的單一劇本
刷新」維持較高優先序最後才降級。
你的建議：先做 A 或 B 其中一個最簡單能動的版本（B 因為沿用既有
模式，工程成本更低），C 這種分級降級留到真的觀察到「主動降級
開關頻繁觸發」之後才需要精修。
不現在決定會卡住什麼：不會，OD-3 的開關本身不需要等這題定案就能
先用最簡單的行為（例如 A）上線。
```

```
OD-12：admin／synthetic 流量要不要在 metrics 系統裡有獨立可見的
維度，即使這代表要為既有的「不存 owner_id」隱私範圍規則開一個例外
這題其實在決定什麼：這是 §6.3 指出的真實設計張力——現有
metrics.py 明確設計成不記錄 owner_id（system-wide、隱私範圍
考量），但如果想在 /api/ops/metrics 儀表板上分清楚「今天的 vendor
預算被 controlled-beta 測試吃掉多少、被真實使用者吃掉多少」，
需要某種形式的新維度。
A：不加，維持現有規則不動——反正 OD-6 如果落實（壓測強制走 mock
路徑），admin 流量本來就不會產生真實 vendor 呼叫，這個問題自然
不存在。
B：加一個粗粒度的布林維度（例如「是否為已知測試身份」，不是完整
owner_id），在不洩漏個別 owner 身份的前提下，至少能區分「測試」
與「真實」兩個大類。
C：完全不在 metrics 系統動手，改成在 admin 身份自己的獨立額度桶
（OD-5／B）那邊直接看消耗量，不需要碰 metrics.py 既有的隱私範圍
規則。
你的建議：如果 OD-6 選 B（強制 mock），這題基本可以維持 A（不用
改動）；只有在 OD-6 選 A 或 C（允許 synthetic 流量真的打 vendor）
時，這題才變得有意義，屆時 C 是風險最低的做法（完全不去動既有
metrics.py 的隱私範圍規則）。
不現在決定會卡住什麼：不會，這是純粹的觀測性精進，且很大程度上
依賴 OD-6 的答案，適合排在 OD-6 定案之後才討論。
```

---

## 9. 引用清單

以下全部連結存取日期均為 2026-09-11。

**IETF／標準規範**：
- https://www.rfc-editor.org/rfc/rfc6585.html —— 429 Too Many
  Requests 狀態碼定義
- https://www.rfc-editor.org/rfc/rfc9110.html —— HTTP 語意規範，
  Retry-After 標頭定義（第 10.2.3 節）
- https://www.rfc-editor.org/rfc/rfc6598.html —— Carrier-Grade
  NAT 共享位址空間（100.64.0.0/10）

**OWASP 官方**：
- https://raw.githubusercontent.com/OWASP/API-Security/master/editions/2023/en/0xa4-unrestricted-resource-consumption.md
  —— API4:2023 不受限資源消耗，官方防護清單
- https://raw.githubusercontent.com/OWASP/API-Security/master/editions/2023/en/0xa2-broken-authentication.md
  —— API2:2023 認證機制被破解，API 金鑰使用建議
- https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
  —— OWASP Denial of Service Cheat Sheet

**AWS**：
- https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
  —— Exponential Backoff And Jitter，Full Jitter 公式原始出處
- https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html
  —— AWS WAF rate-based rule 總覽與已知限制
- https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html
  —— AWS WAF 聚合鍵完整清單（IP／Header／Cookie／JA3/JA4 等）
- https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-caveats.html
  —— AWS WAF rate-based rule 精確度與延遲已知限制

**Google**：
- https://sre.google/sre-book/handling-overload/ —— Google SRE
  Book《處理過載》一章：adaptive throttling、criticality 分級、
  retry storm 防護三道防線

**Cloudflare**：
- https://developers.cloudflare.com/waf/rate-limiting-rules/ ——
  Rate Limiting Rules 總覽、方案對照表
- https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
  —— 限流規則參數（評估視窗、mitigation timeout）
- https://blog.cloudflare.com/counting-things-a-lot-of-different-things/
  —— 2017 年工程部落格，滑動視窗近似演算法與公式
- https://blog.cloudflare.com/turnstile-ga/ —— Turnstile 正式發佈：
  免費無限使用、對抗自動化帳號註冊

**Vercel**（此 repo 實際部署平台）：
- https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
  —— WAF Rate Limiting：演算法（Fixed Window／Token Bucket）、
  方案對照表
- https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting-sdk
  —— `@vercel/firewall` 程式碼內限流 SDK，自訂 `rateLimitKey`
- https://vercel.com/docs/vercel-firewall/attack-mode —— Attack
  Challenge Mode：免費、內部流量自動放行、已知限制
- https://vercel.com/docs/bot-management —— Bot Management：
  已驗證機器人三種驗證方式
- https://vercel.com/docs/vercel-firewall/firewall-concepts ——
  Firewall 動作定義（Log／Deny／Challenge／Bypass）、JA3/JA4
  TLS fingerprint
- https://vercel.com/docs/headers/request-headers —— `x-forwarded-
  for` 標頭：Vercel 邊緣層覆寫防偽造機制

**Stripe**：
- https://docs.stripe.com/rate-limits —— 官方限流文件：全域／
  端點／併發三種限制、退避建議、load testing 建議
- https://stripe.com/blog/rate-limiters —— 工程部落格：token
  bucket、四種限流器分層、公平性哲學
- https://docs.stripe.com/testing —— Testing／sandbox 文件：
  test mode 限流反而更嚴、不建議拿 sandbox 做壓測

**GitHub**：
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  —— REST API 限流：未驗證 60/hr vs 已驗證 5,000/hr、Retry-After
  處理建議

**PostgreSQL／Neon**：
- https://www.postgresql.org/docs/current/explicit-locking.html
  —— PostgreSQL 官方文件：Advisory Locks 定義與用途
- https://neon.com/guides/rate-limiting —— Neon（此 repo 實際
  Postgres 供應商）官方指南：固定視窗＋UPSERT＋advisory lock
  限流模式

**裝置指紋與隱私**：
- https://coveryourtracks.eff.org/about —— EFF Cover Your Tracks：
  指紋唯一性與追蹤風險
- https://w3c.github.io/fingerprinting-guidance/ —— W3C
  Fingerprinting Guidance 官方文件：指紋穩定性與隱私張力

**CAPTCHA／人類驗證**：
- https://www.hcaptcha.com/pricing —— hCaptcha 官方定價（Basic
  免費、Pro 定價與額度）

**架構模式（經典參考，非廠商官方文件）**：
- https://martinfowler.com/bliki/CircuitBreaker.html —— Circuit
  Breaker 模式定義與三態模型，Michael Nygard《Release It!》
  溯源

**二手來源（僅列為線索，未作為事實依據引用）**：
- https://mvpfactory.io/blog/postgresql-advisory-locks-for-distributed-rate-limiting-replacing-redis-in-your/
  —— advisory lock 限流模式效能量級的非官方宣稱，標記 UNVERIFIED

**本 repo 內部檔案**（作為既有架構事實的第一方依據）：
- `api_app/chain_backoff.py` —— provider-global Cboe 429
  circuit breaker 現有實作
- `api_app/identity.py` —— `IdentityResolver`／`SOLO_OWNER`
  固定身份現況
- `api_app/metrics.py` —— `METRIC_CATALOGUE`、`operational_
  metrics` 表設計、明確排除 `owner_id` 的隱私範圍規則
- `api_app/main.py`（`REFRESH_RUN_BUDGET`／
  `REFRESH_RUN_GROUP_LIMIT`／`CRON_SECRET`／`OPS_SECRET`／
  `refresh_run()`）—— 既有 Refresh Trigger 邏輯、既有獨立信任
  邊界 secret 慣例
- `option_chaser/ivpipeline.py`（`IV_BACKFILL_DAY_CONCURRENCY`）
  —— 既有 bounded concurrency 併發控制先例
- `option_chaser/data/cboe.py`（`parse_retry_after()`）——
  既有 RFC 9110 相容的 Retry-After 解析實作
- `vercel.json`（`maxDuration: 60`）—— serverless 函式硬性時間
  上限
- `pyproject.toml`／`package.json` —— 確認全站無 Redis／Upstash／
  `@vercel/firewall` 依賴，唯一持久層為 Neon Postgres
- `CLAUDE.md`（Scaling Foundation 章節、SCALE-04／SCALE-05／
  SCALE-06／SCALE-11 既有裁示記錄）—— provider-global backoff
  設計理由、既有儲存空間撞牆推算、既有 ownership boundary
