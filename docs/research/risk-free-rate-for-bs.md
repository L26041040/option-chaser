# Black-Scholes 無風險利率 r 的正確口徑與 V1 取得設計

研究日期：2026-08-01。
取材限制聲明：本沙箱出口 proxy 對 `home.treasury.gov`、`fred.stlouisfed.org`、
`markets.newyorkfed.org`、`query1.finance.yahoo.com` 的直接抓取一律回 CONNECT 403
（WebFetch 與 curl 皆實測失敗）。凡標「經搜尋索引摘錄」者，內容來自搜尋引擎索引的
官方頁面節錄，未能在本環境逐位元驗證；無法確認的細節一律標「未能確認」。

## 1. 摘要（結論先行）

- **推薦方案（V1）**：以 **美國財政部 Daily Treasury Par Yield Curve（CMT）** 為唯一
  資料源（免 API key 的公開 CSV/XML），取 1M–3Y 節點，**每個 tenor 先以
  `r_cc = 2·ln(1 + y/2)` 轉為連續複利 zero rate，再對選擇權剩餘年期 T 做零利率線性
  插值**；快取上一次成功抓到的曲線（7 日陳舊窗），全部失敗時退回現行硬編碼 0.04。
- **為什麼概念上站得住**：BS 的 r 定義就是「與到期日同年期的連續複利無風險零息利率」
  （§2）；財政部曲線是美國官方、免鑰、含 1M–30Y 完整期限結構的一手來源（§4.1）。
  選擇權市場自身隱含的資金利率（box rate）約高於 Treasury 40bp（§3.3），但本工具
  已接受固定 IV 近似，40bp 級別的曲線選擇差異遠小於 IV 誤差（§7），不值得為此引入
  收費或授權受限的 SOFR 期限曲線。
- **工程成本**：一次 HTTP GET＋一個 ~30 行純函式模組（解析、轉換、插值、快取、
  fallback），無新相依套件。
- **利害有多大（T3 之後）**：r 完全不碰排名（排名基準＝到期內在價值，
  `option_chaser/valuation.py:237-242`）。只影響 heatmap 到期前格值、Greeks 與指引
  曲線。量化：TLT 型 2 年 ATM call（S=K=90、σ=0.15），r 每動 100bp，進場日理論價
  動約 **$1.01**（≈權利金的 9%）；heatmap 中欄（剩 1 年）單腿格值動 $0.51–0.71，
  **90/100 spread 只動 $0.15–0.20**（§7，數字由 repo 自身程式算得）。
  把 r 從「固定 4%」修到「期限對齊的市場值」（2026-07 中旬 2Y ≈ 4.26%，第三方
  鏡像轉述）修正量約 26bp → spread 格值差 ~$0.04，單腿 ~$0.13-0.26。
  結論：**值得做對口徑（期限對齊），不值得做細（bootstrap、日內、box 溢價）**。

## 2. BS 對 r 的嚴格定義

- BS 公式中 `e^{-rT}` 的 r 是**連續複利**（continuously compounded）的**無風險零息
  利率（zero rate）**，**年期須等於選擇權剩餘存續期 T**。出處：Hull, *Options,
  Futures, and Other Derivatives*——連續複利與 zero rate 的定義在第 4 章
  （Interest Rates），BSM 模型與其輸入在第 15 章（The Black-Scholes-Merton Model；
  9e/10e 章節編制，見目錄來源 https://catdir.loc.gov/catdir/toc/ecip0814/2008010842.html
  與 Pearson 產品頁）。**逐字原句未能在本環境核對**（教科書全文抓取受限），章節
  對應與語意為 Hull 各版一致的標準內容。
- 兩個直接推論：(a) 拿 13 週 T-bill 利率（^IRX）套 2 年 LEAPS 是**期限錯配**——
  正是產品負責人否決「換成 ^IRX」的理由，且在殖利率曲線斜率 50–100bp 的年份，
  錯配量級與本文其他所有誤差源同級或更大；(b) 市場報價（半年複利、貼現率）都
  **不是**連續複利，須經 §5 轉換。

## 3. 實務上用哪條曲線

### 3.1 抵押衍生品折現：LIBOR → OIS → SOFR（已驗證）

- 2008 危機後，主要交易商與清算所把抵押品衍生品折現由 LIBOR 改為 OIS；2020-10-16
  收盤起，LCH 與 CME 進一步把美元利率衍生品的折現與 PAI 由 Fed Funds 改為
  **SOFR**。一手來源：LCH 官方新聞稿（轉換 >100 萬口、名目 $120T，
  https://www.lseg.com/en/media-centre/press-releases/lch/2020/lch-successfully-completes-transition-sofr-discounting ）、
  ISDA 2020 報告（https://www.isda.org/a/WhXTE/Adoption-of-Risk-Free-Rates-Major-Developments-in-2020.pdf ）。
  學理討論：Hull & White, "LIBOR vs. OIS: The Derivatives Discounting Dilemma"
  (*J. Investment Management*, 2013)。
- 但這是**有抵押機構市場**的口徑。SOFR 是隔夜利率；要得到 2 年期 r 需要 SOFR OIS
  swap 曲線或 CME Term SOFR——後者**再散布與「用於估值/定價」皆須向 CME 簽授權**
  （CME Term SOFR Data License FAQ,
  https://www.cmegroup.com/market-data/files/term-sofr-data-license-faq.pdf ；
  Use License/ILA 之要求見
  https://www.cmegroup.com/articles/faqs/cme-term-sofr-reference-rates.html ）。
  對免費小工具而言 SOFR 期限曲線**不可行**。

### 3.2 選擇權市場自身的利率：box-implied（已驗證）

- van Binsbergen, Diamond & Grotteria, "Risk-Free Interest Rates"（*J. Financial
  Economics* 143(1), 2022；NBER WP 26138,
  https://www.nber.org/system/files/working_papers/w26138/w26138.pdf ；SSRN 3242836）
  用 box spread 從選擇權價格反推無風險利率：**box rate 顯著高於國債、OIS 與 GC repo**，
  對國債的利差（convenience yield）平均約 **40bp**，3 個月以下更大、危機時可放大
  數倍。含意：若要讓 BS 理論價貼合選擇權市場實際內嵌的資金成本，Treasury 曲線
  **系統性偏低約幾十 bp**——方向已知、量級有界，可視需要加常數 spread 校正。

### 3.3 零售計算器與交易所公開文件

- Cboe Options Calculator 要求使用者**自行輸入** risk-free rate，介面提供帶入
  T-bill／LIBOR 現值的選項（Cboe Options Institute 工具頁
  https://www.cboe.com/education/tools/options-calculator/ ；細節敘述屬經搜尋索引
  摘錄）。OCC／CME 對「保證金或理論價用哪條利率曲線」的公開規格：**未能確認**
  （搜尋未見一手文件）。optionsprofitcalculator.com 的利率同樣未公開（見同目錄
  `opc-heatmap-comparison.md` 第 51 行）。
- 結論：**沒有任何零售層級的「標準答案」曲線**；學理正解（期限對齊 zero rate）
  搭配最可得的官方曲線（Treasury）即是同類工具的合理上限。

## 4. 公開資料源盤點（含可及性實測）

| 來源 | 內容 | 授權/金鑰 | 本沙箱可及性 |
|---|---|---|---|
| Treasury Daily Par Yield Curve | 1M,1.5M(部分年份),2M,3M,4M,6M,1Y,2Y,3Y,5Y,7Y,10Y,20Y,30Y | 美國政府著作，公有領域；免鑰 | **403（proxy 封鎖）** |
| FRED（DGS1MO…DGS30、SOFR） | 同上逐 tenor 日頻鏡像 | 網頁/fredgraph.csv 免鑰；正式 API 需免費 API key | **403** |
| NY Fed Markets API | SOFR 隔夜與平均值 JSON | 免鑰 | **403** |
| Yahoo/yfinance ^IRX/^FVX/^TNX/^TYX | Cboe 殖利率指數 4 點 | 免鑰（非官方管道） | **403** |

- **Treasury（推薦）**：資料頁
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value={YYYY 或 YYYYMM}`，
  頁面提供 Download CSV / XML feed。官方 XML 端點（Treasury 自家開發者頁轉述）：
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={YYYY}`
  （https://home.treasury.gov/treasury-daily-interest-rate-xml-feed ，經搜尋索引摘錄）。
  CSV 直鏈樣式 `…/daily-treasury-rates.csv/{YYYY}/all?type=daily_treasury_yield_curve&field_tdr_date_value={YYYY}&_format=csv`
  見於第三方套件轉述（PyPI `dailytreasuryrates`、GitHub `epogrebnyak/data-ust`）——
  **確切參數未能直接實測（403），實作時以實際回應為準**。tenor 欄位
  1 Mo–30 Yr 由 `dailytreasuryrates` 文件轉述證實。
- **FRED**：series 頁如 https://fred.stlouisfed.org/series/DGS2 （DGS1MO 起自
  2001-07，DGS3MO 起自 1981-09）。`https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2`
  免鑰可下載，但它是網站便利端點、**非文件承諾的穩定 API**（未能確認其穩定性
  承諾）；正式 REST API 需免費 API key。DGS 系列即 Treasury CMT 之鏡像，落後
  來源一個發布週期。CME Term SOFR 在 FRED 上**不可再散布**（見 §3.1 授權）。
- **NY Fed**：SOFR 資料頁 https://www.newyorkfed.org/markets/reference-rates/sofr ，
  Markets Data API（規格 https://apps.newyorkfed.org/~/media/XML/Schemas/api_spec ，
  JSON，如 `/api/rates/secured/sofr/last/N.json`——路徑樣式經搜尋索引摘錄）。
  只有隔夜與回溯平均，**無期限結構**，V1 不採。
- **yfinance ^IRX/^FVX/^TNX/^TYX**：Cboe 殖利率指數，分別對應 13 週 T-bill、
  5Y、10Y、30Y（Yahoo 商品頁自述，https://finance.yahoo.com/quote/%5ETNX/ ）。
  **3M 與 5Y 之間完全沒有節點**——2 年 LEAPS 恰落在洞裡，單用它們無法期限對齊。
  Cboe 指數值為殖利率 ×10（如 4.5% → 45.00）；Yahoo 端顯示口徑在第三方教學間
  說法不一（÷10 與否），**未能實測確認**；^IRX 的報價基礎（貼現率 vs 債券等值）
  **未能確認**。加上 yfinance 為非官方爬取管道、本 repo 已知其 IV 欄位品質問題，
  不宜再讓它多承擔一條利率輸入。

## 5. 報價 → 連續複利 zero rate 的轉換公式（含數值例）

以下數值例皆由 `/tmp/...scratchpad/r_sensitivity.py` 以 repo 的 `valuation.py` 函式
與 stdlib math 算出，可重跑覆核。

1. **Treasury par yield（CMT，半年複利 bond-equivalent，官方口徑見
   https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology ，
   經搜尋索引摘錄）**：
   `r_cc = 2 · ln(1 + y/2)`。例：y = 4.20% → r_cc = **4.1565%**。
   注意 CMT 曲線上短端（bills）已由財政部換算成 bond-equivalent，因此**全曲線可用
   同一條公式**，不必對 1M–6M 另設貼現率轉換。
2. **T-bill 貼現率 d（ACT/360，^IRX 一類報價若採此基礎）**：
   價格 `P = 100·(1 − d·n/360)`；`r_cc = −(365/n)·ln(P/100)`。
   例：d = 4.30%、n = 91 天 → P = 98.9131 → BEY = 4.4076%、r_cc = **4.3836%**。
3. **par → zero bootstrap 在 3Y 以下可忽略**：par 曲線 0.5–2Y 為
   3.9/4.0/4.1/4.2% 時，逐期 bootstrap 出的 2Y 連續複利 zero 與直接
   `2ln(1+y/2)` 之差僅 **0.52bp**（票息效應與曲線斜率成正比；斜率 ±30bp/年內
   都在個位數 bp）。**V1 不做 bootstrap，理由即此量化**。
4. **SOFR（單利 ACT/360 隔夜）**：無期限結構，不適用，僅列存參。

## 6. 期限插值（1M–3Y）

- 曲線構建文獻的兩個常見基礎：對 zero rate 線性、對 log-discount factor（= t·z）
  線性（後者等價於分段常數 forward）。系統比較見 Hagan & West, "Interpolation
  Methods for Curve Construction", *Applied Mathematical Finance* 13(2), 2006
  （其結論：linear-on-yield 簡單但 forward 不連續；生產級曲線用 monotone convex——
  財政部官方曲線 2021-12-06 起亦採 monotone convex，出處同 §5 方法論頁）。
- 本案量化：在 1Y(4.00%)–3Y(4.30%) 之間取 2Y，linear-zero 得 4.150%、
  linear-logDF 得 4.225%，差 **7.5bp**——已是刻意放大的斜率情境，仍遠小於 §3.2
  的 40bp 曲線口徑差與 §7 的 IV 誤差。且 Treasury 在 1M–3Y 給了 8 個節點，相鄰
  節點間插值誤差再縮一個量級。
- **V1 建議：對連續複利 zero rate 做相鄰節點線性插值**（實作最短、單調、誤差
  已量化為個位數 bp）；不採樣條、不外插（T > 30Y 不存在；T < 1M 取 1M 值即可）。

## 7. 本 repo 利害範圍量化（T3 之後）

r（`AnalysisParams.rate`，預設 0.04，`option_chaser/models.py:60`；CLI `--rate`，
`option_chaser/cli.py:74`）的全部觸點：

- **排名：零影響**。T3 後 spread 排名情境＝自身到期日的內在價值
  （`option_chaser/valuation.py:237-242`），r 不出現。
- **heatmap 到期前格值**：`scenario_leg_value` → `clamped_price`
  （`valuation.py:89,170-172`；矩陣接線 `option_chaser/service.py:151-158`）。
  到期欄恆為內在價值，r 影響歸零。
- **Greeks**：delta/gamma/theta/vega 經 `call_greeks`／`leg_greeks`
  （`valuation.py:39-53,175-192`）；**rho 根本沒算**（`Greeks` 欄位
  `valuation.py:31-36`），r 只進 d1/d2 與 theta 的 `−rKe^{−rT}N(d2)` 項
  （`valuation.py:44-47`）。
- **單腿指引/情境曲線、30 日衰減**：同一條 `scenario_leg_value` 路徑
  （`valuation.py:103-117`、`service.py:191-196`）。

數值（TLT 型 2 年 LEAPS：S=K=90、σ=0.15、repo 自身程式計算）：

| 量 | r=3% | r=4% | r=5% | Δ/100bp |
|---|---|---|---|---|
| 進場日 ATM 2y call 理論價 | 10.29 | 11.28 | 12.31 | **≈ $1.01**（解析 rho=K·T·e^{−rT}·N(d2)=100.8/單位 r） |
| heatmap 中欄（剩 1y）單腿 K=90，S=90/95/100 | 6.74/10.11/14.06 | 7.23/10.72/14.76 | 7.73/11.34/15.47 | **$0.51/0.62/0.71** |
| 同格 90/100 bull call spread | 3.98/5.34/6.57 | 4.18/5.53/6.73 | 4.39/5.72/6.88 | **$0.20/0.19/0.15**（兩腿 rho 對消） |
| theta/day（2y ATM） | — | −0.0102 | −0.0116 | ~14% |

對照誤差預算：固定 4% vs 2026-07 中旬實際 2Y ≈ 4.26%（第三方鏡像
https://convextrade.com/metrics/dgs2 轉述 FRED DGS2，**當日精確值未能直接驗證**）
→ 誤差 26bp → spread 中欄格值差 ~$0.04、單腿 ~$0.13；而 IV 誤差 2–5 vol-pt 對同
一單腿是 $0.8–2（vega≈0.4/vol-pt，見 `opc-heatmap-comparison.md:96`）。
**r 的口徑錯配（短率 vs 2 年）最壞可差 100–200bp＝$0.5–2，與 IV 誤差同級，值得修；
修對期限後殘餘的 ±40bp 曲線選擇差（$0.1–0.4）低於 IV 噪音，不值得再買精度。**

## 8. 推薦方案與備選

### V1 推薦（最小而概念正確）

1. **資料源**：Treasury Daily Par Yield Curve 當年 CSV（免鑰單一 GET；XML 端點為
   備援）。取最新一列的 1M,2M,3M,4M,6M,1Y,2Y,3Y 節點（3Y 以上本工具用不到，
   多留 5Y 亦無妨）。
2. **轉換**：每節點 `r_cc = 2·ln(1 + y/2)`。不做 par→zero bootstrap（§5 量化
   <1bp）。
3. **插值**：對 r_cc 相鄰節點線性插值到該腿剩餘年期 T（`days_between/365`，沿用
   repo 現行 ACT/365，`valuation.py:10`）；T < 1M 取 1M 節點。
   介面上這自然是一個純函式 `rate_for_tenor(curve, T) -> float`，
   與 `timeframe.py` 同風格的無 I/O 模組，測試用固定曲線夾具。
4. **Fallback（三層）**：
   (a) 抓取成功 → 曲線連同 `fetched_at` 寫入 workspace 快取（JSON）；
   (b) 抓取失敗 → 用快取曲線，**陳舊窗 7 個日曆日**（利率日常波動 ~數 bp/日，
   一週漂移 <<26bp 的現存誤差；報告註明快取日期）；
   (c) 無快取或超窗 → 退回常數 `0.04`（現行預設），並在報告參數行
   （`option_chaser/report.py:58`）標示「r=固定 0.04（曲線不可得）」。
   `--rate` 明示指定時跳過整條管線（保留現有 CLI 語意）。
5. **不做**：SOFR/Term SOFR（授權不可行，§3.1）、box 溢價校正（+40bp 常數可日後
   一行加上，§3.2）、日內/交易日慣例、per-cell 折現曲線以外的任何期限模型。

### 備選

- **B1（更少工程）**：FRED `fredgraph.csv?id=DGS1MO,...,DGS3` 一次拉多序列，轉換
  插值同上。代價：非承諾性端點、資料落後一個發布週期、多一層鏡像。適合當
  Treasury 端點解析失敗時的第二資料源，而非首選。
- **B2（零網路）**：維持手動 `--rate`，但把預設值文件化為「應填與劇本年期相配的
  Treasury 殖利率」。零成本、概念口徑靠使用者自律；作為 V1 被否決時的底線。
- **B3（拒絕）**：^IRX 單點（期限錯配，即產品負責人否決案）；yfinance 四指數拼
  曲線（3M–5Y 斷層蓋不住 LEAPS 主戰場，且報價口徑未能確認，§4）。

## 9. 引用清單

一手/官方（標註者為經搜尋索引摘錄，直接抓取被 proxy 403）：
- https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026 —— par 曲線資料頁、CSV/XML 下載（摘錄）
- https://home.treasury.gov/treasury-daily-interest-rate-xml-feed —— XML 端點樣式（摘錄）
- https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology —— monotone convex 方法、bond-equivalent 半年複利口徑（摘錄）
- https://www.lseg.com/en/media-centre/press-releases/lch/2020/lch-successfully-completes-transition-sofr-discounting —— 2020-10 SOFR 折現切換
- https://www.isda.org/a/WhXTE/Adoption-of-Risk-Free-Rates-Major-Developments-in-2020.pdf —— OIS→SOFR 脈絡
- https://www.cmegroup.com/market-data/files/term-sofr-data-license-faq.pdf 、https://www.cmegroup.com/articles/faqs/cme-term-sofr-reference-rates.html —— Term SOFR 授權限制
- https://fred.stlouisfed.org/series/DGS2 、https://fred.stlouisfed.org/series/DGS1MO 、https://fred.stlouisfed.org/series/DGS3MO —— DGS 系列（摘錄）
- https://www.newyorkfed.org/markets/reference-rates/sofr 、https://apps.newyorkfed.org/~/media/XML/Schemas/api_spec —— NY Fed SOFR 與 API（摘錄）
- https://www.cboe.com/education/tools/options-calculator/ —— Cboe 計算器利率輸入（摘錄）
- https://finance.yahoo.com/quote/%5ETNX/ 等 —— ^IRX/^FVX/^TNX/^TYX 定義（摘錄）

學術/教科書：
- van Binsbergen, Diamond & Grotteria, "Risk-Free Interest Rates", *JFE* 143(1) 2022；NBER WP 26138（https://www.nber.org/system/files/working_papers/w26138/w26138.pdf ）
- Hull, *Options, Futures, and Other Derivatives*（Ch.4 利率、Ch.15 BSM；逐字未核對）
- Hull & White, "LIBOR vs. OIS: The Derivatives Discounting Dilemma", *JOIM* 2013
- Hagan & West, "Interpolation Methods for Curve Construction", *AMF* 13(2) 2006

第三方轉述（僅用於 URL 樣式/現值，均已標示）：
- https://pypi.org/project/dailytreasuryrates 、https://github.com/epogrebnyak/data-ust —— Treasury CSV/XML 抓取樣式與 tenor 欄位
- https://convextrade.com/metrics/dgs2 —— 2026-07-13 DGS2 ≈ 4.26%

本 repo：
- `option_chaser/valuation.py:10,31-53,44-47,81-89,101,170-172,175-192,237-242`
- `option_chaser/models.py:60`、`option_chaser/cli.py:74,96-97`
- `option_chaser/service.py:151-158,165-196`、`option_chaser/report.py:58`
- `docs/research/opc-heatmap-comparison.md:51,95-96`
- 敏感度數值：以 repo 自身 `valuation.py` 的 `bs_call`／`call_greeks`／
  `spread_scenario_value` 帶入表列參數（S=K=90、σ=0.15、T=2y/1y、r∈{3%,4%,5%}）
  即可重算覆核，無外部相依。
