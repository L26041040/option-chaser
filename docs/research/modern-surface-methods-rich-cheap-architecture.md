# 近代 fair-vol-surface 方法與 Rich/Cheap Engine 架構——承接 R2 之後的缺口研究

研究日期：2026-08-14。本文是本 repo 第五輪選擇權貴賤判斷研究，**不是重寫**，是
`spread-surface-residual-rv.md`（R2/#97）、`candidate-iv-relative-value.md`、
`iv-relative-history-methodology.md`、`option-richness-assessment-methods.md`、
`directional-option-fair-value-workflow.md`、`spread-implied-probability-readout.md`、
`spread-price-percentile-vs-vol-space.md` 七份既有研究之後的**缺口填補**：
(1) 1999 年 GS SAS 框架近年業界怎麼改進；(2) SSVI（跨期一致性）是否推翻 R2
「本用途不需要跨期一致性」的判定；(3) surface 的統計／PCA／因子模型（本 repo
完全未覆蓋的主題）；(4) 機器學習 surface fitting／relative value（同樣完全未
覆蓋）；(5) deviation/residual/z-score 詞彙——橫斷面殘差與時間序列統計兩軸
是否、如何合併；(6) 最終交付——把以上六份既有研究＋本文新材料收攏成一套
具體的 Rich/Cheap Engine 架構答案。**本文不施工、不替需求方拍板。**

## 取材限制聲明

- **開工前 checkout 核對**（依委託指示執行）：`git log --oneline -3` 顯示
  HEAD 為 `bead845`（「docs(research): 物理分布如何橋接到選擇權公平值」），
  `git status` 乾淨，`docs/research/` 目錄下確認七份既有研究檔案全部存在。
  **checkout 為新鮮狀態，非本專案歷史上出現過三次的回退陷阱**——本文的
  【repo 實證】可信。
- **沙箱網路限制與前七輪完全同型，本輪逐一新測仍全部被擋**：
  `arxiv.org`（WebFetch 直接 403 `EGRESS_BLOCKED`）、個人學術頁面
  `rama.cont.perso.math.cnrs.fr`（Rama Cont 本人掛的 PDF，非常見金融網域，
  仍被擋）、GitHub Pages 靜態網誌 `volsurf-rs.github.io`（前輪能連的是
  `github.com` 的 git clone 協定，**GitHub Pages 網域本身不在白名單內**，
  本輪新確認）、CDN 檔案託管 `assets.ctfassets.net`（FactSet 白皮書掛載處，
  同樣被擋）。**結論與前七輪一致且更廣**：沙箱白名單目前已知只有
  `raw.githubusercontent.com`（單檔）與 `git clone` 對 `github.com`
  （完整 repo）兩條通路，其餘幾乎所有網域無論是金融業、學術個人頁、或
  純內容 CDN 一律 403。不再逐一列舉更多網域，此型態已由本輪與前七輪共
  逾三十次獨立測試充分確認。
- **本輪 git clone 複查了前輪已取得的一手鏡像**
  `github.com/s0ap/gs-quantitative-strategies-research-notes`
  （23 份 PDF 全部列出，見 §9 來源清單），**確認其中沒有任何一份晚於
  1999 年**——這個鏡像本身就是「1990 年代 GS QSRN」的封閉集合，
  對「近年業界改進」（§1 的核心問題）**不可能**提供答案；本輪因此把
  §1 的檢索完全轉向搜尋索引，此為方法論上的必然，非偷懶。
- **本輪【原文實證】掛零**：多次嘗試取得一手 PDF（Cont–da Fonseca 原文、
  Zeliade／FactSet 白皮書、`volsurf-rs` 工程網誌）全部被擋，與
  `spread-implied-probability-readout.md`（該輪同樣零一手來源）同型
  現狀，如實聲明。**本文除 §6 的 repo 現況核對外，所有外部事實主張
  均為【搜尋索引轉述】**——本文使用的是搜尋引擎回傳的摘要／標題／
  片段，未逐字讀過任何一份新引用的原始文件全文。
- **分級標記**：依委託指示，採用本 repo 最近兩輪
  （`option-richness-assessment-methods.md`／`directional-option-fair-value-workflow.md`）
  已建立的三級體系：**【原文實證】**（逐頁讀過原文）、
  **【搜尋索引轉述】**（只讀到搜尋引擎摘要）、**【repo 實證】**（本
  repo 程式碼，逐行覆核）。凡引用既有六份研究「已經確立」的結論，
  一律標「（既有研究已證，見 X 文 §Y，本文不重複）」，不重貼推導、
  不重新分級——那是那些文件自己的證據責任，本文只負責正確轉引。
- **本輪唯一的【repo 實證】新增項**：為確認 §6 最終架構的地基是否
  仍然成立，本輪直接讀了 `option_chaser/valuation.py` 與
  `option_chaser/dividends.py`／`option_chaser/data/dividends.py`
  的函式簽名（見 §6.1），發現一項**既有研究文件用語不夠精確、需要
  訂正的小細節**：`directional-option-fair-value-workflow.md` 稱
  「`bs_call`／`leg_greeks` 等函式均帶 `q` 參數」——**逐行核對後，
  `bs_call`（第 21 行）本身其實沒有 `q` 參數，帶 `q` 的是
  `call_greeks`／`leg_greeks`（Greeks 專用）與另外兩個該文件未點名的
  函式：`merton_price`（純定價，Merton 1973 含股利歐式解）與
  `american_price`（Bjerksund–Stensland 1993 美式近似，含連續股利
  殖利率）**。這不影響那份文件的核心論點（引擎確實已有股利殖利率
  機制），但精確歸屬见 §6.1。

## 結論摘要

**核心問題（§6）的直接答案先講**：Option Chaser 現在若要做一套可信的
Rich/Cheap Engine，最接近現代做法的架構是**四層、非五層**——(1) 資料層
（已在手，本輪 repo 覆核確認）；(2) 橫斷面 fit 層＝R2 已判定的
per-expiry、log-moneyness、OTM-only、加權二次式（或零成本起點 `theo`
欄位）；(3) 兩腿封裝層＝R2 已判定的 $ 空間相加、vol pts 空間並排明細；
(4) 時間層（本文新增，**選配、非 MVP**）＝把 (2)/(3) 的殘差用**既有
V9/T11 快照累積機制**存成序列，累積足量後取**百分位**（理由：對離群值
穩健，本文延伸 `iv-relative-history-methodology.md` §2.1 既有的
Rank-vs-Percentile 論證到殘差這個新量上，見 §5.3）。**SVI／SSVI／
SABR／PCA／ML 全部不進這套架構**——但**不是同一個理由**：SVI／SABR
是 R2 已證的「殺雞用牛刀＋SABR 主動出錯」；SSVI 是本文新證的
「买的是跨期一致性，本產品只做單一到期日的 vertical spread，用不上，
且犧牲同期擬合精度換這個買不到的東西」；PCA 是本文新證的「業界真的
用它描述 surface 動態＋做避險歸因，但沒有找到它被當成**獨立於平滑
殘差之外**的 rich/cheap 訊號在用，缺的是這一步的證據不是缺 PCA 本身
的證據」；ML 是四者中**證據最薄**的一個，理由收斂到四條而不是一條
（§4.4）。

**逐問簡答**：

1. **1999 年 GS SAS 框架近年業界怎麼改進**——**沒有找到一個直接的
   「SAS 2.0」**。真正發生的是業界**繞過**了 SAS 最重的部分（用標的
   歷史報酬分佈＋相對熵最小化推「歷史公平 smile」），改用便宜十倍
   的做法：直接對**今天自己這條鏈**做 SVI／SSVI 平滑，殘差當 edge
   （ORATS S%、SpiderRock、Vola Dynamics——R2 §2.3／§7.4 已覆蓋，
   本文不重複）。SAS 想解決的問題被**簡化**掉了，不是被**升級**掉了
   （§1）。P→Q 橋接的唯一學術後續（Duan 1995 GARCH-LRNVR 及其修正）
   已由 `directional-option-fair-value-workflow.md` §5 深挖過、且該文
   已證「沒有找到真的用它給散戶方向性 spread 定價的證據」，本文不
   重複（§1.3）。
2. **SSVI 是否推翻「跨期一致性不需要」的判定**——**不推翻，且本文找到
   更精確的理由**：SSVI 買的是**calendar-spread 無套利一致性**，這是
   Option Chaser 目前**唯一沒有的產品線**（本產品只做同到期日的
   vertical spread，不做跨到期日的 calendar spread）；而且找到明確的
   權衡證據——**維持相關係數在跨到期日常數，會犧牲逐期擬合品質**
   （§2.2）。換句話說：SSVI 為本產品用不上的東西，付本產品用得上的
   東西的代價。若未來 Option Chaser 真的加了 calendar spread 候選，
   這個判定要重新做（§2.3 的但書）。
3. **PCA／統計因子模型**——本 repo 完全空白的主題，本文找到扎實材料：
   Cont–da Fonseca (2002) 與本 repo 既有的 Kamal–Derman（GS 內部）
   **兩條獨立血統**都得出「3–4 個因子解釋 90–95% surface 日變異，
   可讀成 level／skew／curvature」的一致結論（§3.1），且 Cont–da
   Fonseca 進一步提議把每個因子當 Ornstein-Uhlenbeck（均值回歸）過程
   建模。**但「PCA 殘差當獨立於平滑殘差之外的 rich/cheap 訊號」這個
   具體應用，本輪沒有找到 vol surface 專用的實證**——均值回歸殘差
   當交易訊號這個技法本身在**鄰接領域**（Avellaneda–Lee 的股票報酬
   統計套利）有紮實的回測證據，但那是對股票報酬的橫斷面，不是對
   vol surface；本輪找到的 vol-surface-PCA 實際用途集中在**避險歸因
   與 delta 正規化座標的理論背書**，不是獨立訊號（§3.2–3.3）。
4. **機器學習**——學界極活躍（2024–2026 仍持續發表），但本文專門
   檢索「桌上真的在用」的證據，找到的是**反向證據**：連提出
   SABR-informed Gaussian Process 的研究者自己都聲明「不是要取代
   SABR 避險或 OTC 估值」；搜尋「業界生產部署證據」直接得出「主要
   是學術工具，沒有廣泛避險基金生產採用的明確跡象」的結論；銀行
   拒用的結構性理由（Basel／Fed／ECB 對可解釋風險驅動因子的要求）
   有多來源交叉佐證；甚至 2025 年最新一批論文自己的方向都是
   **ML 疊加在 SABR／SVI 骨架上做插值**，不是取代整個參數化骨架
   （§4）。四項理由疊加，是本文五個技術裡「不需要」判定證據最厚的
   一個。
5. **Deviation/Residual/Z-score 詞彙**——業界的基本單位是**原始 vol
   點差**（SAS、ORATS S%、殘差本身皆是）；縱軸統計則**percentile／
   rank／z-score 三種都真實在用**，但用在**不同量**上：ORATS 把
   skew slope（橫斷面擬合的衍生量）做成 percentile 對照自身歷史
   （`slope 在九十百分位` 這類語言，直接回答本題「縱橫是否合併」——
   答案是**合併，且已是產品功能**）；VRP 這個量則用 z-score
   （`z-score 1.5＝VRP 高於均值 1.5 個標準差`）。**本輪明確沒有
   找到的是：把「平滑殘差本身」（S%／edge，而非 slope／VRP 這類
   衍生統計量）拿去做時間序列 percentile／z-score 的公開產品實例**
   ——這是本文最重要的單一查證缺口，直接影響 §6 Layer 4 的定位
   （選配、非 MVP）（§5）。

## 目錄

- §1　「近年業界如何改進 1999 GS SAS」——實際發生的是簡化＋productize，不是升級
- §2　SSVI 專論：跨期一致性買什麼、付什麼代價、與本產品的距離
- §3　Surface 的 PCA／統計因子模型：動態描述的扎實證據 vs. 訊號應用的缺席
- §4　機器學習：學界活躍、桌上證據缺席，四條收斂理由
- §5　Deviation/Residual/Z-score 詞彙：縱橫合併的真實案例與缺口
- §6　最終架構：Option Chaser 的 Rich/Cheap Engine（核心交付）
- §7　未能查證的事項
- §8　引用清單

## 1.「近年業界如何改進 1999 GS SAS」——實際發生的是簡化＋productize，不是升級

### 1.1 檢索方法與最直接的負向結果

本輪針對「post-2010 vol surface 相對價值方法」「1999 年後 SAS 後繼框架」
「systematic volatility relative value cross-sectional mispricing」
等多種措辭反覆檢索，並複查了前輪已取得的 GS 一手 PDF 鏡像
（`github.com/s0ap/gs-quantitative-strategies-research-notes`，
23 份 PDF，見 §0）——**該鏡像本身封頂在 1999 年，不含任何後續材料**
【repo 實證，本輪直接 `git clone` 列目錄確認】。搜尋端同樣沒有找到
一篇明確自稱「延續／取代 Zou–Derman SAS」的後續論文或業界白皮書
【搜尋索引轉述，檢索性結論，見 §7 第 1 項的 absence-of-evidence
留保】。ResearchGate 索引顯示該論文累計約 **915 次引用**
【搜尋索引轉述，數字未核對原始資料庫，僅供影響力量級參考，見 §7】，
代表學界知道這篇文章、常引用它，但「常被引用」不等於「有人接著把
它的方法做大」——這正是本節要交代清楚的落差。

### 1.2 真正發生的事：業界繞過了 SAS 最重的那一步

把 SAS 的四步驟（§0 已引 `directional-option-fair-value-workflow.md`
§2.2 的完整推導，不重複）簡化為一句話：**用標的的歷史報酬分佈，經
相對熵最小化，推出一條「歷史公平 smile」，再拿今天的市場 smile 去減
它**。這一步的工程與模型風險，遠高於「直接對今天這條鏈本身做平滑、
拿殘差」——而**業界／vendor 端過去二十多年實際走的正是後面這條輕
量路徑**，已由 R2（`spread-surface-residual-rv.md` §2.3／§7.4）與
`candidate-iv-relative-value.md` §7.4 詳盡覆蓋（ORATS SMV／S%、
SpiderRock、Vola Dynamics、Cboe `theo`），本文不重複其內容，只指出
一個此輪才看清楚的**定位**：

> 這些 vendor 產品**不是** SAS 的「升級版」——它們解決的是同一個
> 表面問題（「給我一條可以拿來算殘差的公平 smile」），但**放棄了
> SAS 最有野心的部分**（把歷史報酬分佈餵進 P→Q 橋接，得出真正
> 「相對歷史」的公平值）。它們的公平 smile 是**純橫斷面**的——
> 今天這條鏈自己的形狀，經平滑得到今天的參照面。SAS 想回答「相對
> 歷史，這是不是公平的」；ORATS S% 一類回答的是「相對今天的鄰居，
> 這是不是公平的」。這不是後者比前者高明，是**業界用腳投票選了
> 更便宜、更少模型風險的那一題**，而 R2 已經證明對本產品用途而言
> 這一題（橫斷面）已經足夠（見 R2 §7 結論），本文只是把這個選擇
> 放到「產業史」的脈絡裡講清楚：**這是刻意的簡化，不是能力不足
> 的妥協**。

### 1.3 唯一稱得上「後續」的學術路線，本 repo 已經深挖過且判了負面結果

SAS 的 P→Q 橋接（相對熵最小化）在數學上與 **Duan (1995) 的 GARCH
option pricing／LRNVR** 同構——`directional-option-fair-value-workflow.md`
§2.3／§5 已經把這條線的一手／索引材料整理得非常完整：Duan 1995 的
LRNVR、Christoffersen–Jacobs (2004) 對 LRNVR 字面限制下模型表現不佳
的負面實證、Barone-Adesi et al. (2008) 提出的 modified-LRNVR 修正，
以及**該文自己下的判定**——「沒有找到任何來源指出一般方向性選擇權
交易台，會用完整參數化 GARCH-Q 模型去給單一標的的 vertical spread
定價」（該文 §5.2）。**本文不重複這條線的證據，只確認一件事**：
本輪的新檢索（「post-2010 systematic volatility relative value
methodology」等）沒有找到任何**推翻**這個負面判定的新材料——
即沒有找到「GARCH-Q 定價後來被證明真的在桌上用」的反例。

### 1.4 有一件事是真的變了：「vol relative value」變成了一個真實的機構資產類別

本輪新找到、前七輪未觸及的材料：**Capstone Investment Advisors** 與
**Parallax Volatility Advisers** 是兩家真實存在、規模可觀的機構基金，
公開自我定位為「relative value trading with a volatility bias」
（Capstone）與「global relative value volatility trading strategy」
（Parallax）【搜尋索引轉述，兩家公司官網】。這證明「vol surface
relative value」作為一個**機構投資紀律**，不但沒有隨 SAS 論文淡出，
反而長成了獨立的對沖基金策略類別；**但兩家的具體方法論屬商業機密，
公開材料只到行銷語言層級（「proprietary tools to price derivatives
and volatility efficiently, filter opportunities」），本輪無法取得
任何可逐字引用的方法細節**——這是誠實的邊界，列入 §7。此外，一份
2020 年代的 vendor／部落格級材料（FlashAlpha，「Complete Guide to
Volatility Relative-Value Trading」）把「vol RV」的現代交易分類
整理成四類：**calendar trades**（跨到期日相對貴賤）、**skew
trades**（同到期日內兩翼相對貴賤）、**dispersion trades**（指數
implied correlation 對單一成分股 vol 的偏離）、**VRP trades**
（市場定價的未來變異數 vs 已實現變異數）【搜尋索引轉述，vendor
部落格層級，與 R2 §9 已引用的同一站台同一信任等級，非新提升】。
對本產品最直接的映射：Option Chaser 目前只做**同到期日**的 vertical
spread，落在這四類裡的 **skew trades**——這與 R2、
`option-richness-assessment-methods.md` M5、
`candidate-iv-relative-value.md` 三份文件已經反覆確立的「vertical
spread 的定價由局部 skew 斜率一階決定」完全一致，只是本文找到了
一個現代（雖然是 vendor 層級）材料把這個分類講得更明確。

### 1.5 小結：gap 1 的答案

**沒有「2010 年後的 SAS 升級版」這種東西**——業界的真實演化路徑是
「放棄 SAS 最貴的那一步（歷史報酬→entropy→公平值），改用純橫斷面
平滑＋vendor productize（R2 已覆蓋），並讓『vol relative value』
長成一個獨立的機構資產類別（本文新增，但方法論不可得）」。這個
結論**加固**而非**推翻**了 R2 原本的判定：R2 選擇「per-expiry 二次式
平滑」而非「SAS 全套」，本文找到的產業史證據顯示——**整個業界都做了
同一個選擇**，不只是本產品因資源限制而退而求其次。

## 2. SSVI 專論：跨期一致性買什麼、付什麼代價、與本產品的距離

R2（`spread-surface-residual-rv.md` §2.1）已把 SVI 定位為「殘差標示
用途的過度工具」、一句話帶過 SSVI（表格備註「Gatheral–Jacquier 2014
無套利版」）；`option-richness-assessment-methods.md` M4 也只在一句
話帶過「SSVI／eSSVI 變體再跨切片施加一致性以避免 calendar spread
套利」。兩處都**沒有深入**——這正是委託要求本文補的缺口。

### 2.1 SSVI 精確買的是什麼：calendar-spread 無套利，不是逐期擬合品質

SSVI（Gatheral & Jacquier, 2014；已由前兩輪索引引用，本文不重複其
公式，R2 §2.3 已列出參考連結）的機制：**把每個到期日切片限制成一個
共用形狀族的子集**（幾個全域參數如相關性 ρ 跨所有到期日共用，只有
每期的 ATM total variance θ_t 各自變動），目的是**解析式保證**
calendar-spread 無套利——「total variance 在固定 log-moneyness 上
對到期日單調不遞減」這個條件在 SSVI 的參數限制下自動成立
【搜尋索引轉述，多個來源交叉一致：SSVI 對「skew 以 total variance
計對交易時間單調遞增、以 implied variance 計對交易時間單調遞減」
這兩個條件的滿足，是其「immune to calendar arbitrage」的機制】。

而**逐期各自獨立 fit SVI（R2 已判定的路線之一，雖然 R2 最終選了更
簡單的二次式）天生會犯的錯，恰好就是 calendar-spread 套利**：
「Calendar arbitrage between slices can occur when each expiry is
calibrated independently, which can produce total variance that
decreases with time at the same moneyness」【搜尋索引轉述】——這是
SSVI 存在的**唯一理由**，不是「擬合品質更好」，而是「跨期比較時
不會產生自相矛盾的訊號」。

### 2.2 找到的權衡證據：跨期一致性是用逐期擬合精度換來的

本輪新找到一則直接回答委託「這是否推翻 R2 判定」的證據
【搜尋索引轉述，索引摘要交叉多篇 SSVI 相關文獻（含 Baruch MFE
課程講義索引與 SSVI robust calibration 文獻索引）】：

> SSVI 的校準比逐期 SVI 容易，但**把相關性 (ρ) 限制成跨到期日
> 常數，會犧牲擬合品質**——原文摘要用詞是「depreciates the fit
> quality」。

這與 eSSVI（Hendriks & Martini 的延伸版——見 §2.3）存在的理由完全
吻合：eSSVI 把 ρ 改成**依到期日變化**（不再是全域常數），目的正是
**找回**SSVI 犧牲掉的那塊擬合精度，代價是重新引入一部分跨期不一致
的風險，只是用「顯式的無套利條件」重新守住（見 §2.3）。**這證明
「跨期一致性」與「逐期擬合精度」在 SSVI 的參數設計裡是真實的
翹翹板，不是免費午餐**。

### 2.3 對 R2 判定的檢驗：不推翻，且找到更精確的理由

R2 §2.4 原文已把「跨期比較或 constant-maturity 輸出」列為二次式
「不夠用」的反例之一，並註明「三者都不在本票用途內」——這句話當時
是**直覺性的範圍界定**，本文找到的證據把它**變成有機制支撐的判定**：

| | 逐期擬合精度 | 跨期（calendar）一致性 |
|---|---|---|
| **SSVI 買到的** | 較差（§2.2 的權衡證據） | 保證無套利 |
| **本產品用得上的** | **是**（候選兩腿都落在同一到期日內，殘差讀數只消費該期切片的擬合品質） | **否**（本產品目前只做 vertical spread，兩腿恆為同一到期日；沒有 calendar spread 候選，不存在「比較不同到期日之間誰比較貴」這個產品問題） |

**結論**：SSVI 把本產品用不到的東西（跨期一致性）當賣點，而且是用
本產品確實用得到的東西（逐期擬合精度）去換的——若真的採用 SSVI，
對 Option Chaser 現有候選（vertical spread，單一到期日）而言是
**淨損**，不是「用不到但至少無害」。這比 R2 原本「三者都不在本票
用途內」的界定更進一步：**不只是不需要，採用了反而變差**。

**但書（範圍限定，不是否定）**：CLAUDE.md 記載的 spec #47／
V1–V10 拆票中沒有 calendar spread 候選類型；`option-richness-
assessment-methods.md` M6（期限結構）也明確指出 Option Chaser
目前的「橫向到期日選單」比較的是「哪一期的 vertical spread較划算」
而非「同一組 legs 跨到期日比較」——這與 calendar spread（買近月賣
遠月或反之，同履約價）是不同的產品形態。**若未來 Option Chaser
真的加了 calendar spread 這條產品線，本節的判定要重新評估**——
那時候，SSVI／eSSVI 買的東西（跨期一致性）就會直接對上那個新產品
問題的核心需求，屆時 R2「跨期比較不在本票用途內」的前提本身會
改變。這是一個**條件式**的但書，本文不擴大解讀成「應該加 calendar
spread」——那是完全獨立的產品範圍決策，不在本文授權範圍內。

### 2.4 eSSVI：同一場翹翹板的延伸，也是本輪唯一找到的真實 vendor 落地證據

**Hendriks & Martini 的 eSSVI**（extended SSVI，Journal of
Computational Finance）把 SSVI 的相關性參數 ρ 改成依到期日變化的
函數 ρ(θ_t)，同時給出保持 calendar 無套利的充要條件
【搜尋索引轉述】。找到的量化說法：「eSSVI 對長天期的擬合品質增益
很小，但短天期的擬合品質幾乎加倍」【搜尋索引轉述】——這再次確認
§2.2 的翹翹板：SSVI 犧牲的擬合精度主要集中在**短天期**，eSSVI 是
針對這個弱點的局部修補，對本產品的 LEAPS 主戰場（長天期）**增益
本來就小**，進一步削弱了它對 Option Chaser 的相關性。

本輪唯一一項具體指向「有真實 vendor 用 eSSVI」的線索：一份標題
《eSSVI Implied Volatility》的白皮書，經搜尋確認發布方是
**FactSet Research Systems**（主要金融資料／分析平台商，與
Bloomberg 同級）【搜尋索引轉述，僅取得標題與發布方歸屬，PDF 本體
被沙箱擋下，未讀到任何內文，見 §7】。這是本文唯一具體指向「主流
vendor 採用 eSSVI」的證據，但**因為無法讀到內文，不能引用任何
FactSet 對 eSSVI 用途／效能／部署方式的具體陳述**——只能確認
「FactSet 這個等級的 vendor 確實對 eSSVI 發過方法論白皮書」這件事
本身，不能確認更多。

### 2.5 小結：gap 2 的答案

**SSVI 不推翻 R2「跨期一致性不需要」的判定，且本文把這個判定從
「直覺範圍界定」升級成「有機制與權衡證據支撐的判定」**：SSVI 的
存在理由是 calendar-spread 一致性，這是本產品目前唯一沒有的產品線
（vertical-spread-only，同到期日）；SSVI 买這個一致性的代價是逐期
擬合精度，而逐期擬合精度正是本產品**唯一**用得到的東西。eSSVI 的
局部修補（§2.4）進一步顯示它想解決的問題主要在短天期，與本產品
LEAPS 主戰場錯位。**若產品線擴張到 calendar spread，此判定需要
重新評估**——但這是條件句，不是本文的建議。

## 3. Surface 的 PCA／統計因子模型：動態描述的扎實證據 vs. 訊號應用的缺席

本 repo 目前完全沒有專門處理過這個主題——`option-richness-
assessment-methods.md` 只在轉述 Kamal–Derman（GS 內部一手文獻）的
PCA 結果時提及一次（用途是佐證「M7 delta 正規化座標」與「M4 曲面
是低維物件」兩個既有論點，見該文 §4-M4 第 4 點與 §4-M7 第 4 點），
**沒有把 PCA 當成獨立的方法去問「殘差本身能不能當訊號」**。這正是
本節要填的缺口。

### 3.1 兩條獨立血統，同一個結論：surface 動態是低維的

| 血統 | 因子數與解釋力 | 因子解讀 | 證據等級 |
|---|---|---|---|
| **GS 內部（Kamal & Derman，1990s）**——既有研究已引用 | SPX 前 3 個模態解釋 90.7%（81.6／5.0／4.1）；Nikkei 95.9%（85.6／7.9／2.4） | 水位／期限結構／skew | 【原文實證，本 repo `option-richness-assessment-methods.md` 已逐頁讀過原文並引用，本文不重複】 |
| **學界（Cont & da Fonseca, 2002, *Dynamics of implied volatility surfaces*）**——本文新增 | 前 3 個主成分解釋約 95% 的日變異 | level／orientation（skew：正衝擊使 OTM call vol 上升同時 OTM put vol 下降）／convexity | 【搜尋索引轉述，多個索引來源交叉一致（SSRN 摘要、ResearchGate、及作者本人學術頁面的索引片段），PDF 本體被沙箱擋下未讀到原文】 |

兩條**完全獨立**（一條是 1990 年代 GS 交易台內部研究、一條是 2002
年學界公開論文，作者與資料處理管線互不相干）的血統得出**幾乎相同**
的答案（3–4 個因子、90%+ 解釋力、level/skew/curvature 或 term-
structure 的相同讀法）——這是本文找到最強的跨來源一致證據，**強化
了 surface 確實是低維物件這個既有論點**，但這件事本身在 repo 裡
已經被 Kamal–Derman 用過（服務 M7 的正規化論證與 M4 的「殘差不是
雜訊」論證），本文的增量是**確認這不是 GS 一家的孤例，是學界獨立
複現的結果**。

**Cont–da Fonseca 進一步提議的建模選擇**（本 repo 之前完全沒有的
材料）：把每個主成分**當 Ornstein-Uhlenbeck（均值回歸）過程**建模
【搜尋索引轉述】——即認為 surface 的因子在動態上是**穩態、會拉回
均值**的，而非隨機漫步。這一步是本節後續討論的關鍵前提。

### 3.2 均值回歸殘差當交易訊號：鄰接領域（股票統計套利）有紮實回測證據

**Avellaneda & Lee (2008/2010), "Statistical Arbitrage in the U.S.
Equities Market"**（*Quantitative Finance* 10(7)）——這是本文找到
與「PCA 因子殘差當交易訊號」最直接相關的紮實材料【搜尋索引轉述，
多個索引來源（SSRN、Bocconi Students Investment Club 教學文章、
研究論文摘要）交叉一致】：對**股票報酬**的橫斷面做 PCA（前 20 個
主成分），主成分解釋系統性報酬，**殘差（idiosyncratic 部分）是
穩態的、適合建模成均值回歸的 Ornstein-Uhlenbeck 過程**，據此產生
逆勢（contrarian）交易訊號；回測（1997–2007）年化 Sharpe ratio
約 **1.44**，但**2003 年後表現明顯轉弱**【搜尋索引轉述，數字未
核對原始論文，見 §7；「2003 後轉弱」本身是該策略族系文獻裡常見的
「alpha 隨已知因子普及而衰減」現象，方向性可信但本輪未取得衰減的
精確幅度】。

**這條證據回答的是「均值回歸殘差當訊號」這個技法本身是否紮實**
——答案是肯定的，**但是在股票報酬的橫斷面上**，不是在 vol
surface 上。

### 3.3 缺口所在：「vol surface 的 PCA 殘差」本身沒有找到同等級的訊號證據

本輪專門檢索「PCA residual volatility surface trading signal」
「factor residual vs smile fit residual comparison」等措辭，
**結果明確**：找到的是 §3.1（surface 動態的低維描述）與 §3.2
（股票報酬 PCA 殘差的訊號證據），**兩者中間缺一塊直接的橋——沒有
找到一份材料具體描述「有人把 vol surface 的 PCA 殘差（而非股票報酬
的 PCA 殘差）當成獨立於平滑殘差之外的 rich/cheap 訊號在用，並附有
實際效能或部署證據」**【搜尋索引轉述，檢索性結論，absence of
evidence，見 §7】。

本輪找到的 vol-surface-PCA **實際確認用途**只有兩類，**都不是
獨立訊號**：

1. **投組績效歸因與避險**：「PCA 因子可用於把投組績效歸因到 surface
   的系統性移動，供部位配置與風險管理參考」【搜尋索引轉述】——這是
   風控／歸因用途，回答的是「我的整批部位對 level／skew／curvature
   各暴露多少」，不是「這一組候選貴不貴」。
2. **正規化座標的理論背書**：本 repo 既有的 Kamal–Derman 引用（M7）
   已經是這個用途——PCA 證明 surface 低維，所以拿 delta／期限座標
   正規化是合理的，這是**支持 R2 選擇的座標系**，不是一個競爭方案。

### 3.4 判定：技法有先例（鄰接領域），前提有證據（surface 確實低維且
均值回歸），但「vol surface PCA 殘差當獨立訊號」的具體應用未見實證

用委託原文的措辭直接回答：**這是「學術上優雅、目前找不到桌上真的
在把它當 vol surface 專用 rich/cheap 訊號在用的實證」的情況**，
但精確程度要分層講清楚，不能一竿子打成「純學術幻想」：

- 均值回歸殘差當訊號這個**技法**：有紮實先例（Avellaneda–Lee，
  股票報酬）；
- vol surface 因子確實均值回歸這個**前提**：有兩條獨立血統的
  描述性證據（Kamal–Derman、Cont–da Fonseca），但這兩篇本身**沒有
  報告把它拿去做成交易策略、回測、或效能數字**——它們停在「這樣
  建模是合理的」，沒有走到「這樣做真的賺錢／被用」；
- 把兩者**接起來**（vol surface PCA 殘差 = 獨立可交易訊號）：
  **本輪沒有找到任何一份材料做過這件事並提供證據**——這是一個
  合理的類比延伸，結構上站得住，但目前是**未被證實的推論**，
  不是**已確認的業界做法**。

對 Option Chaser 的意義：PCA 因子模型**不該被當成 R2 平滑殘差
的替代方案**引入——它解決的是不同的問題（surface **怎麼動**，而非
**這一筆報價**離今天的曲線多遠），證據集中在描述性／歸因用途，
不在獨立訊號用途。若 Option Chaser 未來想做「整批候選對 vol
環境的系統性暴露」這種**投組層級**的功能（而非本文一直在討論的
**單一候選**層級 rich/cheap 讀數），PCA 因子模型會是那個不同問題
的合理起點——但那是另一個產品問題，見 §6.5。

## 4. 機器學習：學界活躍、桌上證據缺席，四條收斂理由

同 §3，本主題本 repo 完全空白。委託明確要求保持懷疑——本節的檢索
策略刻意分兩路：先找「有什麼方法」，再**專門**找「有沒有真的被
用在生產環境／交易台」的證據，兩路分開報告。

### 4.1 有什麼方法：學界持續活躍，2024–2026 仍有新論文

找到的方法族系（全部【搜尋索引轉述】，全部是學術論文，年份橫跨
2019 至 2026）：

- **帶先驗知識的神經網路**：把「無套利」「邊界條件」「漸近斜率」
  等金融約束直接編碼進 loss function 或網路架構，據稱在標普 500
  二十年期權資料上，樣本內與樣本外的 MAPE 都**優於 SSVI**
  【搜尋索引轉述，具體論文與數字未核對原文，見 §7】。
- **Gaussian Process 方法**：2025 年的「SABR-informed multitask
  Gaussian Process」——用 SABR 生成的合成資料做結構性正則化，
  結合任務嵌入處理稀疏報價；同年另有「Meta-Learning Neural Process
  with SABR-induced Priors」。兩者**都不是純資料驅動**，而是把
  SABR（R2 已判定「產生負機率密度、本用途不需要」的模型）當**先驗／
  正則化來源**注入 ML 架構【搜尋索引轉述】。
- **Physics-Informed Neural Networks（PINN）**：把 PDE 約束與金融
  邊界條件整合進即時校準【搜尋索引轉述】。
- **eSSVI ＋強化學習**：2025 年一篇「Risk-Sensitive Option Market
  Making with Arbitrage-Free eSSVI Surfaces」把 eSSVI（§2.4）的
  無套利參數化骨架與約束式強化學習、隨機控制結合，做市商情境
  【搜尋索引轉述】。

**這四類方法有一個共同、值得單獨標出的形態**：**沒有一個是「純
黑箱 ML 取代整個參數化模型」**——全部是「把 SABR／SVI／eSSVI 的
參數化骨架當先驗、正則化來源、或約束條件，ML 負責在骨架允許的空間
內做插值或決策」。這代表**即使是 2025–2026 年最新的研究方向，
研究社群自己也還沒有走向「拋棄無套利參數化骨架、全交給 ML」**這條
路——這個事實本身就是對「ML 已經取代傳統方法」這種印象的一個
反證，不需要額外去找「ML 失敗」的證據，方法論的選型本身就說明了
研究者的判斷。

### 4.2 專門檢索生產部署證據：明確的負向結果

針對「機器學習 volatility surface 生產部署」「hedge fund production
adoption evidence」等措辭的專門檢索，得到的結果本身就承認證據
缺席【搜尋索引轉述，來自對多篇 2025–2026 GP／NN 論文的索引摘要
綜合】：

> 「搜尋結果主要是學術論文（2025–2026 年的 arXiv 與學術出版物），
> 展示對真實市場資料（SPX 選擇權、股票指數期權）的理論應用。然而，
> 結果中沒有明確證據顯示避險基金廣泛生產採用，或有真實世界的
> 交易實作……這暗示 Gaussian Process 用於 vol surface 目前主要
> 仍是學術工具，而非標準避險基金生產系統。」

更值得注意的是：**連提出這些方法的研究者自己都主動聲明限制**——
一篇 SABR-informed GP 論文的作者明確寫道，該方法「不是要取代
SABR-based 動態避險或 OTC 衍生品估值」，若要延伸到避險與 OTC 估值
「需要與市場一致的動態與 Greeks 驗證」【搜尋索引轉述】——即研究者
自己都把它定位在「介面／插值工具」，不是「生產定價／風控引擎的
替代品」。**這比外部懷疑更有力**：不是外人質疑這些方法不成熟，是
提出方法的人自己在論文裡就先劃清了「這還不能取代生產系統」的界線。

### 4.3 找到的結構性障礙：不是「還沒做」，是有明確理由「難做」

專門檢索「為什麼銀行不用神經網路做生產定價」，得到多方交叉一致的
結構性理由【搜尋索引轉述，來自對衍生品定價神經網路應用綜述類材料
的索引摘要】：

1. **可解釋性／監理要求**：Basel 委員會、Fed、ECB 等監理機關要求
   風險估計必須能**拆解成非技術背景的監理人員可以質問、挑戰、
   核准的風險驅動因子**——傳統的無套利參數化模型（SVI／SSVI）
   天生可拆解（幾個參數各自對應水位／斜率／曲率），神經網路的
   內部表示天生不是。
2. **資料品質與外推能力**：神經網路的表現高度依賴訓練資料，訓練
   資料的微小誤差可能讓策略非常不穩定；且「即使訓練良好的模型
   也無法對訓練資料之外的情況做外推，市場結構一有變化就要重新
   訓練」——這與選擇權市場的 regime 變化（升息週期、危機期）
   頻繁發生的現實直接衝突。
3. **模型風險治理的一般張力**：「傳統原則驅動模型立基於經濟理論與
   無套利論證，具可解釋性與可審計性；現代機器學習模型能高度擬合
   市場資料，卻通常是黑箱、可能違反基本金融原則，對模型風險管理、
   驗證與監理合規構成核心挑戰」。

這三條理由**不是本文自己的推論**，是多方索引來源交叉重複出現的
說法，本文只是把它們收攏列出——但它們的**邏輯**與這個較窄、
但更直接的產品事實完全吻合：**Option Chaser 本身就明文宣告
`valuation.py` 是「Stdlib math only」**（`option-richness-
assessment-methods.md` §3 已【repo 實證】確認），任何 numpy／
scipy／PyTorch 依賴都需要先推翻這個既有工程決策——而這正是 R2
評估 SVI（更輕量的非線性最佳化）時就已經考慮過並選擇繞開的同一類
成本，ML 的依賴更重，同一個理由的效力只會更強不會更弱。

### 4.4 判定：四條理由收斂，是五個技術裡「不需要」證據最厚的一個

把 §4.1–4.3 收攏成四條**各自獨立**（缺一都不影響其他三條成立）的
理由，逐條列出是為了讓讀者看清楚這不是單一薄弱理由的重複包裝：

1. **證據面**：專門檢索生產部署證據，得到的是明確的「主要是學術
   工具」結論，且是研究者自己承認的限制，不是外部批評（§4.2）；
2. **方向面**：連 2025–2026 年最前沿的研究，自己選擇的路線都是
   「ML 疊加在 SABR／SVI 骨架上」而非「純 ML 取代骨架」，研究
   社群自己還沒有走向「不需要無套利參數化骨架」這個方向（§4.1
   末段）；
3. **結構面**：可解釋性／監理要求／訓練資料外推能力三項，是比
   本產品規模大得多的機構仍然面對的真實障礙，不是「小公司做不起」
   這種資源問題（§4.3）；
4. **工程面**：本產品明文的 stdlib-only 工程決策，是比 R2 拒絕
   SVI（僅需自寫非線性最佳化）更嚴格的一道門檻——ML 需要的依賴
   （訓練框架、模型檔案、推論執行環境）比 SVI 的非線性最佳化重
   一個量級（§4.3 末段，本文推論，非引用來源直接陳述）。

**這四條理由中沒有一條依賴另一條才成立**——即使假設監理障礙未來
放鬆、即使假設某天生產部署證據出現，第一條與第四條（本產品自身
的工程決策）依然獨立成立。這是本文對五個技術（SVI/SABR/SSVI/PCA/
ML）逐一檢驗後，「不需要」判定證據最厚的一個。

## 5. Deviation/Residual/Z-score 詞彙：縱橫合併的真實案例與缺口

R2 已經完整定義了橫斷面殘差（本產品用途：今天這條鏈上，這兩張報價
偏離同期鄰居多少）；`iv-relative-history-methodology.md` §2.1 已經
完整定義了 Rank 與 Percentile 兩種時間序列統計量的差異（對極值的
敏感度）；`candidate-iv-relative-value.md` §6.2 也已經提到 FX Risk
Reversal 圈子對「兩點差」序列取 z-score 的成文實務。**本文要接上的
是委託明確點名的空隙**：橫斷面殘差（R2 那一軸）與時間序列統計
（`iv-relative-history-methodology.md` 那一軸）**是否、如何**
實際被業界合併使用。

### 5.1 找到的正面案例：ORATS 把「橫斷面擬合的衍生量」拿去做時間序列
percentile

這是本文對這個問題找到的**最直接**證據【搜尋索引轉述，ORATS 官方
university／blog 頁面索引】：

> ORATS 用一條平滑曲線畫過各履約價的 IV 之後，把 skew **總結成
> slope、derivative、fixed-day points 幾個量**——slope 衡量「每
> 增加 10 個 call delta 點，IV 改變多少」，即整條 skew 的陡峭程度；
> 這個 **slope**（本身是橫斷面平滑的衍生統計量，需要當天全鏈擬合
> 才算得出來）**再被拿去對照自身歷史算 percentile**——「若一檔
> 股票的 slope 落在第九十百分位，代表其下檔保護的定價比九成的
> 歷史觀察值都貴」。

這**精確**回答了委託問題：**橫斷面（今天的擬合）與縱軸（相對自身
歷史的統計位置）確實被合併使用，而且是 ORATS 這種主流 vendor 的
現行產品功能，不是概念驗證**。這條證據的量（slope）與 R2 討論的量
（fit residual）**相關但不同**——slope 是擬合曲線本身的一階導數
（描述**整條曲線的形狀**），R2 的殘差是**單一報價點偏離擬合曲線
多遠**（描述**一筆報價的定價品質**）。這個區別很重要，見 §5.2。

### 5.2 第二個案例：VRP 的 z-score，同一個合併模式、不同統計量

另一個獨立找到的案例【搜尋索引轉述】：Volatility Risk Premium
（`option-richness-assessment-methods.md` M3 已完整覆蓋 VRP 本身
的定義與證據，本文不重複）——「VRP z-score 把當前 VRP 對照自身
歷史分佈正規化，通常用滾動窗；z-score 1.5 代表 VRP 高於均值 1.5
個標準差，暗示選擇權市場異常昂貴」。VRP 本身的計算需要**當天完整
OTM 鏈**（VIX 式 variance swap strip，見 M3），是不折不扣的橫斷面
量；縱軸統計選的是 **z-score**，不是 percentile。

**兩個案例合起來的觀察**：業界確實會把「需要當天橫斷面計算才得到
的量」拿去做時間序列統計，這個**合併模式本身**是真實、多處可查的
實務——但**選 percentile 還是 z-score，看起來取決於量本身的統計
性質與 vendor 慣例，不是有一條寫死的規則**。ORATS 對 slope（及
其整個指標家族，含 ATM IV 本身）統一用 percentile／rank；VRP 這個
不同的量、不同的來源，用的是 z-score。

### 5.3 找不到的：殘差本身（而非其衍生統計量）的時間序列化

本輪**專門**檢索「smile fit residual percentile」「ORATS S%
historical percentile」「IV residual z-score history」等措辭，
得到的結果明確承認查無所得【搜尋索引轉述，檢索性結論】：

> 「搜尋結果不包含 S% 歷史百分位追蹤或 SpiderRock edge 歷史資料的
> 具體資訊」

即：**ORATS 自己的 S%（平滑殘差，R2 §3.3 已用作零成本起點）有沒有
被 ORATS 自己拿去做歷史 percentile，本輪找不到證據**——這與 §5.1
的 slope percentile **不是同一件事**：slope 是擬合曲線的形狀
參數，S% 是報價偏離擬合曲線的殘差本身。兩者都是「橫斷面擬合的
產物」，但 §5.1 證明前者被時間序列化了，本輪沒能證明後者也被
時間序列化了。**這是絕對缺乏證據（absence of evidence），不是
證明它不存在**——ORATS 的完整指標家族極大（官方稱追蹤超過 100 個
指標／檔標的），本輪的搜尋深度不足以窮舉；不能排除某個未被搜尋到
的欄位就是這個東西。此為本文最重要的單一查證缺口，直接影響 §6.4
的定位。

### 5.4 詞彙小結：業界怎麼命名這件事

| 量的性質 | 找到的縱軸統計量 | 案例 |
|---|---|---|
| 原始 vol 點差（無時間維度） | 不適用（無時間軸） | SAS、ORATS S%（R2 已覆蓋）——這是「橫」軸本身 |
| ATM IV 水位 | Rank／Percentile 兩者皆有，vendor 常見兩者並陳 | tastytrade IVR／IVP、ORATS `ivRank`／`ivPct`（`iv-relative-history-methodology.md` §3.4 已完整覆蓋，本文不重複） |
| Skew slope（橫斷面擬合的衍生量） | **Percentile** | ORATS slope percentile（本文新增，§5.1） |
| VRP（橫斷面計算的衍生量） | **Z-score** | 業界部落格慣用語（本文新增，§5.2） |
| FX Risk Reversal（兩點差） | **Z-score**（1M／6M lookback） | `candidate-iv-relative-value.md` §6.1 已引用（Spectra Markets 教材），本文不重複 |
| **平滑殘差本身（S%／edge）** | **未查得** | 本文專門檢索無所得，§5.3 |

**回答委託的具體問法**（「業界怎麼定義／表達一個 relative-value
訊號一旦有了殘差之後——是原始 vol 點差、對某個歷史分布的
z-score、百分位，還是別的」）：**三種都是真實存在的業界詞彙，
但落在不同的量上，沒有一條規則說「殘差就該用哪一種」**。本文
能給的最誠實答案是：**如果 Option Chaser 真要把 R2 的殘差接上
時間軸，percentile 與 z-score 兩者都有業界precedent 可援引
（分別援引 §5.1 slope 案例與 §5.2 VRP 案例），選擇應該基於這個
特定量（殘差）的統計性質，而不是盲從某個外部慣例**——這個判斷
本身，見 §6.4。

## 6. 最終架構：Option Chaser 的 Rich/Cheap Engine（核心交付）

本節是委託最明確要求的交付物：把七份既有研究＋本文 §1–§5 的新材料，
收攏成一個具體的架構答案。**先聲明範圍**：本節是研究結論的架構化
呈現，**不是實作計畫、不是票、不施工**——沿用本 repo 所有研究文件
的既有紀律。

### 6.1 地基：資料層現況核對（【repo 實證】，本輪新覆核）

`option-richness-assessment-methods.md` §3 與
`directional-option-fair-value-workflow.md` §6.1 已經【repo 實證】
過一次「引擎有什麼」，本輪為了確保 §6 的架構建議站在正確的地基上，
重新核對了與「fair value 需要股利口徑」這個關鍵前提直接相關的
函式簽名，發現**地基比兩輪之前更穩固**：

```
option_chaser/valuation.py：
  bs_call(S, K, T, r, sigma)                       # 原始、無 q，q=0 隱含
  call_greeks(S, K, T, r, sigma, q: float = 0.0)    # 帶 q，Greeks 專用
  leg_greeks(option_type, S, K, T, r, sigma, q=0.0) # 帶 q，call_greeks 的 put 延伸
  merton_price(option_type, S, K, T, r, q, sigma)   # 帶 q，Merton 1973 純定價
  american_price(option_type, S, K, T, r, q, sigma) # 帶 q，Bjerksund–Stensland 1993 美式近似

option_chaser/dividends.py + option_chaser/data/dividends.py：
  parse_yahoo_dividends() / parse_fmp_dividends() / parse_nasdaq_dividends()
  # 三個獨立來源的股利資料解析器，非僅函式簽名的空殼
```

**這件事對本文架構的意義**：R2（2026-08-08）與
`candidate-iv-relative-value.md`（同日）當時反覆警告「本 repo 引擎
是 q=0 的 BS，任何用它當 fair value 模型都是股利假象」——這句話在
**當時是完全正確的封鎖性判定**，也是 R2 選擇「直接 fit 市場 IV，
不碰模型價格」這條路的關鍵理由之一。**本輪核對顯示，這個封鎖已經
被後續票（#113／spec #117 §1.4）解除**——`merton_price`／
`american_price` 現在都是含股利口徑的真定價函式，且有三個真實資料
來源餵股利率，不是只有函式簽名。**這不改變 R2 的核心建議**（R2
選的「直接 fit 市場 `iv` 欄位」本來就不需要模型定價，見 R2 §3.2 的
論證——它本來就是為了繞開 q=0 問題而選的路），**但這打開了一條 R2
寫作當時明確關閉的門**：若未來想要一個「模型理論價 vs 市場價」的
獨立殘差路徑（作為 R2 §3.3 `theo` 路徑的自建驗證器的驗證器），
現在的引擎已經有能力算出一個不含股利假象的版本。這是一個**可用性
的提升**，不是本文架構的必要條件——§6.2 的設計完全不依賴這件事。

### 6.2 Layer 1（橫斷面 fit 層）：R2 判定原樣採用，本文不重新論證

**per-expiry、x＝log-moneyness、y＝Cboe `iv`、OTM-only、1/相對價差²
加權、OLS 二次式**——R2 §2.4 已經給出完整判定與 §6 的真實 Cboe 全鏈
實測（LEAPS 期殘差中位數 0.12 vol pts，41/41 落在半價差內），
**本文原樣採用，不重新推導、不重新實測**。零成本起點是 Cboe
`theo` 欄位（R2 §3.3，與自建二次式相關係數 +0.94~+0.98）。

**本文對這一層唯一的新增**：§1–§4 的檢索結果**沒有一項推翻**這個
選擇——SVI／SABR（R2 已判定過度）、SSVI（§2 新判定：買不需要的
東西、付需要的代價）、PCA（§3 新判定：解決不同問題）、ML（§4 新
判定：五個技術裡證據最薄）全部經過本輪的獨立檢索，**沒有一個技術
的新證據強到值得推翻 R2 原本用『per-expiry 二次式對真實鏈實測、
殘差已落在雜訊底噪之下』得到的判定**。用一句話總結這一層的地位：
**R2 的判定不但沒有被本文動搖，反而在五個候選替代方案逐一被檢驗
後，證據上更加穩固**。

### 6.3 Layer 2（兩腿封裝層）：R2 判定原樣採用

**$ 空間相加（spread 整體殘差佔 debit 的 %，主讀數）＋vol pts 空間
並排（每腿明細，不合成）**——R2 §4.2 已完整論證（兩腿 vega 不同、
SAS 腳注 3 的單調性紅線禁止湊單一 vol 數字給 spread；$ 空間天然可加
且同號相消是正確反映淨多付成本，不是 bug）。本文核對：
`option-richness-assessment-methods.md` §4-M8-B 用鏈式法則展開
`∂C/∂K`，獨立得到「決定包裹貴賤的是 [K1,K2] 這一段的局部 skew 斜率，
ATM IV 水位在兩腿間大幅相消」的結論——**這與 R2 用完全不同的推導
路徑（殘差直接相減）殊途同歸**，兩份文件互相印證，本文不重複兩者
的推導，只指出這個交叉驗證本身值得記錄：**兩種獨立方法論路徑（R2
的橫斷面殘差框架、M8 的 Breeden-Litzenberger／鏈式法則框架）在
「spread 定價由局部 skew 斜率主導」這一點上完全會師**。

### 6.4 Layer 3（時間層，選配、非 MVP）：本文新增，基於 §5 的證據謹慎提出

這是本文對既有六份研究**唯一**新增的架構層——之前沒有任何一份
文件明確回答「R2 的橫斷面殘差，要不要疊一層時間序列統計」。

**設計**：

1. **資料機制不是新問題**：R2 的殘差計算是**零成本**的（每次刷新
   時，既有全鏈資料 + 一次 3×3 封閉解 OLS，見 R2 §2.4 第 2 點）；
   要把它時間序列化，唯一要做的新事情是**存下來**——這正是 V9
   （`store.spread_cost_history()`）／T11
   （`workspace.spread_history()`）已經在為 spread 成本走勢做的事
   （依身份鍵跨快照累積、缺席即斷點不插值）。**不需要新的資料管線
   類別，是既有累積機制的一個新消費者**。
2. **統計量選擇：percentile，理由是本文自己的推論，明確標注**
   ——`iv-relative-history-methodology.md` §2.1 已經完整論證 Rank
   （min-max 正規化）對單一極端值高度敏感（一次尖峰壓低其後一整年
   讀數），Percentile（經驗 CDF）則遠不敏感。**本文把這個既有論證
   延伸到 z-score**（該文原本沒有討論 z-score，因為當時的候選量是
   IV 本身，z-score 尚不在候選之列）：z-score 依賴均值與標準差，
   **同樣對極端值高度敏感**——一次極端離群殘差（例如冷門履約價
   的殘留爛報價，R2 §5.3 已經指出這正是本產品殘差讀數最容易出現
   假訊號的情境）會同時拉高分子（離均值的距離）與標準差本身，
   效果比 Rank 更難預期。**本文的推論結論**：若 Option Chaser
   真的建 Layer 3，**percentile 優於 z-score 與 Rank**——這不是
   外部引用，是本文自己延伸既有論證得到的建議，標注為【本文推論】
   而非【搜尋索引轉述】。§5.2 找到的 VRP z-score 先例證明 z-score
   在業界不是不能用，只是本文認為對「殘差」這個特定量、在本產品
   「使用者觸發式刷新、快照密度不規律」（QA1-07 已裁定的三種刷新
   時機）的資料現實下，percentile 的離群穩健性更重要。
3. **繼承既有的冷啟動警告，不是新問題**：`iv-relative-history-
   methodology.md`（方案 A-E 全部）與 `candidate-iv-relative-
   value.md`（方案二 Ĝ）已經反覆處理過「累積歷史需要時間，視窗未滿
   前只能顯示『以現有 N 天計』」的問題——Layer 3 繼承同一個警告，
   不是新問題，**且很可能比既有的 IV／skew 歷史累積得更慢**：R2
   的殘差計算雖然零成本，但它是本文（連同 R2）才第一次被提出的
   全新量，目前沒有任何一天的歷史被存過，累積必須從零開始，冷啟動
   期會比已經在跑（哪怕跑得不規律）的其他量更長。
4. **與既有兩條時間軸並列，靠標籤紀律區分**：`iv-relative-history-
   methodology.md` 方案 A（ATM IV 水位歷史）、`candidate-iv-
   relative-value.md` 方案二（skew gap Ĝ 歷史）、與本文 Layer 3
   （殘差歷史）三者**全部正交**——分別回答「現在的 vol 環境貴嗎」
   「這組結構的 skew 相對歷史在哪」「這筆報價的定價品質相對它自己
   的歷史穩不穩定」三個不同問題。R2 §5.1 已經對「橫斷面殘差 vs
   歷史位置」的正交性明文警告過一次（不得在 UI 上混排），本文的
   Layer 3 若真的實作，這個警告的對象要**再增加一條線**——三條
   時間軸都掛「相對歷史」的標籤，但相對的是三個不同的「歷史」，
   必須分區、分標題，不得暗示彼此可以互相替代或加總。

**明確定位：選配、後期**。理由收攏：(a) §5.3 找到的查證缺口——
「殘差本身的時間序列化」沒有找到業界現成先例，只有相鄰量（slope、
VRP）的先例可類比，這是一個**合理延伸但未被證實的產品假設**，
不應該用 MVP 的優先級去賭一個未被驗證的假設；(b) 冷啟動期預期
比既有其他時間軸更長（見上第 3 點）；(c) R2 自己的誠實侷限
（§5.2）已經指出「健康鏈上殘差多數時間落在雜訊底噪之下」——一個
「多數時間在說沒事」的量，拿去做歷史百分位，产出的訊號密度會更低，
值不值得為它建一整套累積與展示機制，是一個需要需求方看過 Layer
1-2 實際上線效果之後才能做的判斷，不是本文能替代的決定。

### 6.5 明確排除，逐項理由一句話（可複查表）

| 技術 | 排除理由（一句話） | 判定依據 |
|---|---|---|
| **SVI（逐期 5 參數）** | 二次式已達到同等真實鏈精度，非線性最佳化的工程成本換不到對應的殘差品質提升 | R2 §2.4／§6（既有研究，本文不重複） |
| **SABR** | 在本產品 LEAPS／遠翼主戰場已知會產生負機率密度，是唯一「不只是過度、還會主動出錯」的選項 | R2 §2.1（既有研究） |
| **SSVI／eSSVI** | 買的是跨期一致性，本產品只做同到期日 vertical spread 用不上；且犧牲逐期擬合精度換這個買不到的東西 | 本文 §2（新判定） |
| **PCA／因子模型當獨立訊號** | 兩條獨立血統證實 surface 動態低維（支持既有 M7 正規化與 M4「殘差非雜訊」論證），但沒有找到「PCA 殘差當獨立於平滑殘差之外的訊號」的實證；已確認用途是投組歸因與避險，不是單一候選的 rich/cheap 讀數 | 本文 §3（新判定） |
| **ML（NN／GP）surface fitting** | 五個技術裡「不需要」證據最厚：生產部署證據専門檢索得負面結果、2025 年最新研究自己選擇 ML+參數化骨架混合而非純 ML、監理／可解釋性有多方交叉佐證的結構性障礙、本產品既有 stdlib-only 工程決策比 R2 拒絕 SVI 的門檻更嚴格 | 本文 §4（新判定） |
| **RNHD／SAS 全套自建** | 需要歷史報酬分佈＋entropy 最小化＋全鏈定價，成本比橫斷面簡化版差一個量級；業界自己也走了簡化路線，不是本產品因資源限制而妥協 | `candidate-iv-relative-value.md` §7.3、本文 §1（既有研究＋本文新證據互相印證） |
| **GARCH-Q 定價（Duan LRNVR）** | 學術文獻量大，但沒有找到用於單一標的方向性 spread 定價的桌上證據 | `directional-option-fair-value-workflow.md` §5（既有研究，本文不重複） |

### 6.6 架構總覽（四層示意）

```
┌─ Layer 0：資料層（已在手，本輪覆核）───────────────────────────┐
│ 全鏈＋每合約 iv／theo／vega（cboe.py）                          │
│ 期限對齊無風險利率（ratecurve.py／T12）                          │
│ 股利殖利率：merton_price／american_price 已含 q，              │
│   三個真實來源解析器（dividends.py）                            │
│ 每腿 Greeks 含 delta（leg_greeks）                              │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌─ Layer 1：橫斷面 fit（R2 判定，本文原樣採用）──────────────────┐
│ v0：殘差 = market_iv − theo（零建置成本）                       │
│ v1：per-expiry OTM-only log-moneyness 加權二次式（v0 驗證器／    │
│      斷供備援，3×3 封閉解，stdlib）                             │
│ 輸出：每腿 vol pts 殘差 ＋ 並列 bid-ask 半寬底噪                 │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌─ Layer 2：兩腿封裝（R2 判定，本文原樣採用）────────────────────┐
│ vol pts 空間：並排明細，不合成（單調性紅線）                     │
│ $ 空間：殘差×vega 相加＝spread 整體殘差，同號相消如實反映淨成本   │
│ 主讀數：spread 整體殘差 佔 debit 的 %                            │
└──────────────────────────────────────────────────────────────┘
                              ↓（選配、後期、需求方裁示後才進票）
┌─ Layer 3：時間層（本文新增，未被業界直接證實，謹慎提出）────────┐
│ 沿用 V9／T11 既有快照累積機制，存 Layer 1/2 的殘差序列            │
│ 累積足量後：percentile（理由：對離群值穩健，延伸既有 Rank vs      │
│   Percentile 論證，本文推論）                                    │
│ 與既有 ATM IV 歷史（方案 A）、skew gap Ĝ 歷史（方案二）並列，     │
│   三條時間軸正交，標籤紀律不可少                                 │
└──────────────────────────────────────────────────────────────┘

明確不進：SVI／SABR／SSVI／eSSVI／PCA 因子殘差／ML surface fitting
（§6.5 逐項理由）
```

### 6.7 一句話總結整套架構的定位

這套架構**不是"最先進"的架構**——它刻意不用 SVI、不用 SSVI、不用
PCA、不用 ML，這些技術每一個在其他更高階的用途（做市、跨資產一致
定價、投組風控）都是真實、有證據支撐的業界工具。這套架構是
**"最貼合 Option Chaser 這個特定產品問題"的架構**：單一候選、
單一到期日、vertical spread、零售使用者、stdlib-only serverless
budget。本文逐一檢驗了委託點名的五個候選升級方向後，得到的結論
與 R2 十天前對 SVI／SABR 下的判斷同構——**"更高用途的工具"對這個
特定問題是過度配備，不是能力不足的妥協，而業界自己在同一個問題上
的實際選擇（§1 的 SAS→橫斷面簡化演化史）也印證了這一點**。

## 7. 未能查證的事項

1. **本輪【原文實證】掛零**（§0）：Cont–da Fonseca 原文、Zeliade／
   FactSet 白皮書、`volsurf-rs` 工程網誌全部被沙箱擋下，本文所有
   外部事實主張（除 §6.1 的 repo 覆核）均為搜尋索引轉述，未逐字
   核對任何一份新引用文件的完整原文。
2. **本文最重要的單一查證缺口**（§5.3，直接影響 §6.4 的架構定位）：
   「平滑殘差本身（S%／edge）是否被任何 vendor 拿去做時間序列
   percentile／z-score」——本輪專門檢索得到明確的查無所得，但這是
   absence of evidence，不是證明不存在；ORATS 官方指標家族號稱
   逾百個，本輪搜尋深度遠不足以窮舉，需要一個能直接讀 ORATS／
   SpiderRock／Vola Dynamics 官方文件全文的環境才能徹底排除。
3. **FactSet eSSVI 白皮書內文**（§2.4）：僅取得標題與發布方歸屬，
   PDF 本體被擋，無法引用其對 eSSVI 用途、效能、或部署方式的任何
   具體陳述。
4. **SAS 論文「約 915 次引用」的數字**（§1.1）：來自 ResearchGate
   索引頁的引用計數，未核對原始資料庫（Google Scholar／Web of
   Science 等可能給出不同數字），且不清楚該計數是否混入
   Zou／Derman 其他論文的引用。
5. **Capstone／Parallax 的實際方法論**（§1.4）：兩家真實機構基金
   的存在與定位已確認，但具體技術方法完全屬商業機密，本輪只能
   取得行銷語言層級的官網描述，無法核實其與本文討論的任何方法
   （SAS 系、SVI 系、PCA 系）的實際關聯。
6. **Citadel Securities「Machine Learning Researcher, Options」
   職缺的具體工作內容**（§4，未在正文展開引用，因證據太弱不足以
   支撐任何具體主張）：僅見職缺標題本身，未讀取職缺全文，無法
   確認該職位是否涉及 surface fitting／relative value，或是市場
   微結構／訂單流／執行優化等其他「選擇權 + ML」應用；本文因此
   刻意不把它當證據使用，僅在此列為「檢索過程中看到但未採信」
   的項目。
7. **NN-beats-SSVI 論文的作者與確切期刊**（§4.1 第一項）：搜尋
   結果只給出方法描述與「優於 SSVI」的 MAPE 主張，未取得作者姓名、
   期刊、卷期；本文因此只引用其研究方向與結論方向，不引用任何
   具體數字或聲稱逐字核對。
8. **Avellaneda–Lee 回測數字**（§3.2）：Sharpe ratio 1.44、
   1997–2007 樣本期、2003 後轉弱，均為搜尋索引轉述，未核對原始
   論文（*Quantitative Finance* 10(7)）的圖表與精確統計量。
9. **Cont–da Fonseca (2002) 的精確發表細節**（§3.1）：論文標題、
   作者、核心結論（3 個主成分解釋約 95% 變異、level/orientation/
   convexity 讀法、OU 過程建模提議）經多個索引來源交叉一致，但
   精確發表年份／期刊卷期／頁碼本輪未能核對原文確認（不同索引
   結果對此有些微出入，例如某些引述將其歸於 *Quantitative
   Finance* 2002 年卷，另一些僅稱「working paper」）。
10. **Harvey Stein《PCA for Implied Volatility Surfaces》的確切
    發表年份**：僅能從 arXiv 編號 `2002.00085` 的格式慣例（YYMM
    前綴）推斷提交於 **2020 年 2 月**，未讀取論文本身確認正式
    出版日期或期刊卷期的最終版本資訊；其 Bloomberg 從屬關係僅由
    LinkedIn 職稱「Senior VP, Labs group」的搜尋片段推斷，未見
    論文作者欄位本身的機構標註。
11. **銀行監理／可解釋性障礙的具體規範條文**（§4.3）：Basel／
    Fed／ECB 對機器學習模型可解釋性的要求，本輪只取得綜述性
    二手轉述，未核對任何一份具體的監理文件原文（如 SR 11-7 或
    BCBS 相關指引）。

## 8. 引用清單

**標記說明**：本文採委託指定的三級體系——【原文實證】（逐頁讀過
原文）、【搜尋索引轉述】（只讀到搜尋引擎摘要）、【repo 實證】
（本 repo 程式碼，逐行覆核）。本輪【原文實證】掛零（§0），除
repo 程式碼外全部為【搜尋索引轉述】。

**PCA／統計因子模型（§3，本文新增主題）**

- 【搜尋索引轉述】Cont, R. & da Fonseca, J., "Dynamics of Implied
  Volatility Surfaces"（2002；索引摘要交叉 SSRN abstract_id=295859、
  ResearchGate publication/227624113、作者個人學術頁面索引；PDF
  本體 `rama.cont.perso.math.cnrs.fr` 被沙箱擋下未讀）
- 【搜尋索引轉述】Stein, H., "PCA for Implied Volatility Surfaces"
  （*Journal of Financial Data Science*；arXiv:2002.00085；
  pm-research.com/content/iijjfds/2/2/85；LinkedIn 職稱索引顯示
  Bloomberg 從屬）
- 【搜尋索引轉述】Avellaneda, M. & Lee, J.-H., "Statistical
  Arbitrage in the U.S. Equities Market"（*Quantitative Finance*
  10(7), 2010；SSRN abstract_id=1153505；Bocconi Students
  Investment Club 教學文章 bsic.it/19167-2/ 的轉述）

**SSVI／eSSVI（§2，本文深挖）**

- 【搜尋索引轉述】Gatheral, J. & Jacquier, A., "Arbitrage-free SVI
  volatility surfaces"（2014；前輪已索引引用，本文新增其
  calendar-arbitrage 機制與 SSVI/per-slice 擬合品質權衡的補充
  索引材料，來源交叉 Baruch MFE 課程講義索引、
  De Marco/Martini 等 "Robust calibration and arbitrage-free
  interpolation of SSVI slices" arXiv:1804.04924 的索引摘要）
- 【搜尋索引轉述】Hendriks, S. & Martini, C., "The extended SSVI
  volatility surface"（eSSVI；*Journal of Computational Finance*
  索引；亦見 arXiv:2204.00312「No arbitrage global parametrization
  for the eSSVI volatility surface」索引摘要）
- 【搜尋索引轉述】De Marco, S. & Martini, C., "Quasi-Explicit
  Calibration of Gatheral's SVI model"（Zeliade Systems White
  Paper ZWP-0005, 2009；索引摘要含「used world-wide by actors who
  face the calibration challenge」的自我陳述）
- 【搜尋索引轉述】FactSet Research Systems, "eSSVI Implied
  Volatility"白皮書（僅取得標題與發布方歸屬，內文未讀，見 §7 第 3 項）

**機器學習（§4，本文新增主題）**

- 【搜尋索引轉述】"Incorporating prior financial domain knowledge
  into neural networks for implied volatility surface prediction"
  （arXiv:1904.12834；作者未確認，見 §7 第 7 項）
- 【搜尋索引轉述】"SABR-Informed Multitask Gaussian Process: A
  Synthetic-to-Real Framework for Implied Volatility Surface
  Construction"（arXiv:2506.22888, 2025）
- 【搜尋索引轉述】"Meta-Learning Neural Process for Implied
  Volatility Surfaces with SABR-induced Priors"（arXiv:2509.11928,
  2025）
- 【搜尋索引轉述】"Risk-Sensitive Option Market Making with
  Arbitrage-Free eSSVI Surfaces: A Constrained RL and Stochastic
  Control Bridge"（arXiv:2510.04569, 2025）
- 【搜尋索引轉述】銀行監理／可解釋性障礙綜述類材料（多來源交叉，
  含衍生品定價神經網路應用的綜述性索引摘要；具體規範條文未核對，
  見 §7 第 11 項）

**機構「vol relative value」資產類別（§1.4，本文新增）**

- 【搜尋索引轉述】Capstone Investment Advisors 官網
  （capstoneco.com，「relative value trading with a volatility
  bias」自我定位）
- 【搜尋索引轉述】Parallax Volatility Advisers 官網／第三方資料庫
  索引（「global relative value volatility trading strategy」）
- 【搜尋索引轉述】FlashAlpha, "Complete Guide to Volatility
  Relative-Value Trading"／"What Is a Volatility Surface? The
  Complete Guide"（vendor 部落格層級，與 R2 §9 已引用的同站台同
  信任等級，本文引用其現代 vol-RV 交易分類：calendar／skew／
  dispersion／VRP）

**Deviation/Residual/Z-score 詞彙（§5，本文新增材料）**

- 【搜尋索引轉述】ORATS, "Predictive indicators"／"Strike Skew
  Killer Metrics"（orats.com/university／blog；slope percentile
  的方法論索引，本文 §5.1 的核心來源）
- 【搜尋索引轉述】VRP z-score 慣例（多篇量化交易部落格層級材料
  交叉一致，未見單一權威原始出處）

**本 repo（既有研究與引擎，本文引用不重複其論證）**

- `docs/research/spread-surface-residual-rv.md`（R2/#97）——本文
  §2、§6 的直接地基：fit 等級判定、二次式對真實鏈實測、輸出語意、
  兩腿封裝的 $ 空間相加判定，全部原樣沿用
- `docs/research/candidate-iv-relative-value.md`——§6.1／§7.3／
  §7.4 的 SAS 一手引用（Zou-Derman 全文逐字）、q=0 引擎警告、
  FX RR z-score 先例，本文 §1／§5／§6.1 引用其結論
- `docs/research/iv-relative-history-methodology.md`——§2.1 的
  Rank vs Percentile 論證，本文 §6.4 延伸到殘差這個新量
- `docs/research/option-richness-assessment-methods.md`——M4／M7
  的 Kamal-Derman PCA 一手引用（GS 內部研究，SPX/Nikkei 模態解釋
  力）、M8 的 Breeden-Litzenberger 鏈式法則展開，本文 §3.1／§6.3
  引用其結論並提出交叉驗證觀察
- `docs/research/directional-option-fair-value-workflow.md`——
  §2／§5 的 SAS entropy／Appendix B-C 逐式一手引用、Duan 1995
  GARCH-LRNVR 負面實證，本文 §1.3 引用其判定、不重複推導
- `docs/research/spread-implied-probability-readout.md`／
  `docs/research/spread-price-percentile-vs-vol-space.md`——
  委託點名的「鄰接前期工作」，本文確認其結論（隱含機率讀數、
  price 空間 percentile 被 vol 空間 dominated）與本文 §6 架構
  不衝突，正交並存，不重複引用其論證
- `option_chaser/valuation.py`——本輪【repo 實證】：`bs_call`
  （無 q）／`call_greeks`／`leg_greeks`（帶 q）／`merton_price`
  （Merton 1973，帶 q）／`american_price`（Bjerksund-Stensland
  1993，帶 q）的精確函式簽名核對，見 §6.1（訂正
  `directional-option-fair-value-workflow.md` 一處用語不夠精確
  的小細節）
- `option_chaser/dividends.py`／`option_chaser/data/dividends.py`
  ——本輪【repo 實證】：三個獨立股利資料來源解析器（Yahoo／FMP／
  Nasdaq）存在性核對，見 §6.1
- `github.com/s0ap/gs-quantitative-strategies-research-notes`——
  本輪 `git clone` 複查，確認鏡像封頂 1999 年、不含任何後續材料
  （§0／§1.1）
