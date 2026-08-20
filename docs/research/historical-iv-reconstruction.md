# Historical IV Reconstruction Methodology：exact-contract 歷史 IV 為 null 時該怎麼辦

研究日期：2026-08-18。範圍：spec #151（Historical IV Trend）系列（HIVT-01–07，
issues #152–158，已全數完成，見 `CLAUDE.md` 專案紀錄區）之後，需求方 /
ChatGPT 透過真實 GitHub Actions probe 確認 Market Data App 的 exact-contract
歷史報價端點對 `TLT`／`ORCL` 兩個真實標的回傳的 `iv` 欄位大量／全部為
`null`。本文只研究、驗證、提出推薦方案——**不 `/to-spec`、不 `/to-tickets`、
不 implementation、不修改 production code**。

## 0. 資料品質聲明（每一條主張都標證據等級）

沿用本 repo `docs/research/` 既有四級標記慣例：

- **【一手來源】** 直接開啟／讀到的官方文件、原始碼、或本 repo 自身程式碼。
- **【實測】** 本地／CI 上真實可重跑的量化結果（含需求方／ChatGPT 已跑過的
  真實 GitHub Actions probe——那是外部真實 vendor 呼叫，不是模擬）。
- **【索引轉述】** WebSearch 回傳的搜尋索引摘錄，非一手，且明確標註若有
  網域歸屬存疑之處。
- **【本文推導】** 本文自己的推理或設計建議，沒有外部背書。
- **【未能查證】** 查過但找不到，如實記錄，不用猜測填空。

本文大量重用（而非重做）本 repo 既有研究成果——尤其是 pricing model 選型
（`heatmap-valuation-method-selection.md`）、無風險利率（`risk-free-rate-for-bs.md`）、
股利殖利率（`dividend-yield-source-selection.md`）、報價品質（`option-liquidity-
filtering.md`）、歷史選擇權資料源（`historical-options-iv-data-sources.md`）
五份文件。這是刻意的：這些文件已經用【實測】／【一手原始碼】等級的證據
回答了本題一半以上的子問題，本文的增量價值集中在「把這些既有結論套用到
**歷史、逐日、point-in-time** 這個新場景時，哪裡站得住、哪裡會露餡（look-ahead
bias、資料源缺口）」。每處重用都會標明出處章節，不逐字複製整段論述。

## 目錄

1. 摘要（結論先行）
2. 已確認的真實問題：exact-contract acquisition 已成功，缺的是 reconstruction
3. 業界怎麼由 option market data 產生 IV
4. Input definitions 逐項確認
5. Pricing model 比較與選型
6. Repo 現有能力可重用性評估
7. Historical information integrity（防止 look-ahead bias）
8. Calibration experiment 設計
9. Decision Matrix：三個候選方案
10. Recommended v1 recipe
11. Diagnostics 降噪分析（僅分析，不施工）
12. 需要需求方裁決的問題
13. 引用清單

---

## 1. 摘要（結論先行）

- **exact-contract 歷史報價取得本身沒有問題**——TLT／ORCL 兩個真實標的、
  三張真實合約，皆 HTTP 203／`s="ok"`／每張 ~250–34 筆歷史觀測，
  `bid`／`ask`／`mid`／`last`／`underlyingPrice`／`dte` 全部正常，只有
  `iv` 大量／全部為 `null`（§2，需求方【實測】）。
- **這不會自己好**：本次新查（【索引轉述】，見 §3.2）發現 Market Data
  App 自家網站文案提到「歷史 EOD Greeks/IV 目前不提供，正在準備加入
  （coming soon）」——若這個讀法成立，null 是這個端點對任何合約、任何
  時候的現行行為（vendor 承認的產品缺口），不是本 repo 資料路徑或這兩
  張合約特有的異常。這代表 reconstruction 不是「等 vendor 修好前的
  過渡方案」，而是目前唯一能讓 Historical IV Trend 對真實標的有內容
  可顯示的路。
- **業界／本 repo 自己既有研究已經回答「IV 怎麼由 option market data 產生」**：
  用同一個定價模型、由該合約**自己的市價**反解 IV（「同模型價格錨定」），
  不是抄 vendor 給的成品欄位。這正是本 repo 現有 `option_chaser/valuation.py::
  implied_vol()` 已經在做的事——它是 **Bjerksund-Stensland (1993) 美式近似**
  （含連續股利殖利率 q）的二分法反解，逐字從 QuantLib 原始碼移植，已經
  被 `heatmap-valuation-method-selection.md` 用真實 TLT 報價量化驗證過
  （§3、§5）。**這件事不需要重新研究模型選型，只需要延伸成「歷史、
  point-in-time」版本**。
- **歷史版本真正缺的三塊輸入，逐一盤點皆非空白**：
  - **r（利率）**：`ratecurve.py` 現有解析器**已支援**指定年／月抓歷史
    Treasury 曲線，但目前的「取最新一列」邏輯是為「今天」設計的，需要
    改成「取 ≤ 目標日期的最近一列」（§6）。
  - **q（股利殖利率）**：`dividends.py` 現有抓取**已經拿到帶 ex-date 的
    完整配息清單**（Yahoo 2 年窗），不是只算好一個數字就丟掉原始資料——
    point-in-time 版本只需要改成「只用 ex_date ≤ 目標日期的配息」＋
    「除以目標日期當時的標的價，不是今天的 spot」（§6）。
  - **S（標的價）**：**完全不需要新資料源**——exact-contract 歷史報價
    回應本身就帶 `underlyingPrice`，逐日、與該筆報價同時點，現有解析器
    `_parse_contract_history()` 目前**直接丟棄**這個欄位（只留
    `(date, iv)`），是個很小的擴充，不是缺口（§6）。
- **不能重用的一塊**：本 repo 現行 q 校準的「Method E」（同到期日、同側
  多筆真實報價擬合出讓跨履約價 IV 最一致的 q）需要**當天的整條 chain**。
  exact-contract 歷史路徑刻意只查單一合約（1 credit／次，這正是 HIVT
  系列選擇單合約端點而非整鏈的理由），沒有歷史整鏈可用——`historical-
  options-iv-data-sources.md` 已經把「按需查歷史整鏈」的資料源選項盤點過
  一輪，全部候選不是要另一台常駐 VM（Theta Data）就是 bulk 檔案（與
  「不自建資料庫」硬約束衝突）。**v1 建議退回較粗的「trailing distribution
  ÷ 當時 spot」單一 q**（見上一點），不做逐日 cross-strike 校準。
- **價格輸入建議用 mid，不用 last**：exact-contract 歷史列同時有
  `bid`／`ask`／`mid`／`last`，「用同一個模型反解、再用同一個模型估值」
  這條既有原則本身沒有規定用哪個價格，但業界慣例（詳見 §3、§4.1）與
  「last 可能是盤中很久以前的一筆過期成交，mid 才是那一刻的市場共識」
  的一般理由都指向 mid；vendor 若同一列已經給出 `mid` 就直接用，不用
  自己算 `(bid+ask)/2` 重複造輪子。

## 2. 已確認的真實問題：exact-contract acquisition 已成功，缺的是 reconstruction

**canonical methodology 不變**：同一張 exact OCC option contract，跟它自己
過去的 IV 比（spec #151 §2，HIVT 系列全數已完成的既有紅線）。

**需求方 / ChatGPT 已完成的真實驗證**【實測，經 GitHub Actions + 真實
`MARKETDATA_APP_TOKEN`，commits `4ec23f1`／`410f927`（工作流跑完即刪，
比照既有 `tmp-*` 慣例，本 repo 已有的一次性 probe 紀律）】：

| 標的 | 合約 | HTTP | `s` | rows | 價格欄位 | `iv` | credit |
|---|---|---|---|---|---|---|---|
| TLT | LEAPS（HIVT-01／#152 既有驗證） | 203 | ok | 34 | 正常 | 部分 `null` | 1 |
| ORCL | `ORCL270115C00220000` | 203 | ok | 250 | 正常（bid/ask/mid/last/underlyingPrice/dte） | **250/250 null** | 1 |
| ORCL | `ORCL270115C00250000` | 203 | ok | 250 | 正常 | **250/250 null** | 1 |

探測用的端點與參數（【一手來源】，本 repo 自己的 probe 腳本，commit
`4ec23f1`）：

```
GET https://api.marketdata.app/v1/options/quotes/{occSymbol}/?from={365天前}&to={今天}
Authorization: Bearer {MARKETDATA_APP_TOKEN}
```

回應是**欄狀**（column-oriented）JSON——`iv`／`updated`／`bid`／`ask`／`mid`／
`last`／`underlyingPrice`／`dte` 皆為與 `optionSymbol` 等長的陣列，第 i 個
元素對應同一筆觀測（【一手來源】，本 repo 現有 `option_chaser/data/
marketdata.py` 的 `_parse_contract_history()` 已經在解析同一種形狀，
見該檔案 429–488 行）。

**結論**：這不是 vendor connectivity 失敗，也不是 exact-contract
methodology 選錯——兩者都成功了。缺的是**當 vendor 沒給 IV 時，我們自己
從已經拿到手的價格資料反解出 IV** 這一步，也就是 reconstruction。

## 3. 業界怎麼由 option market data 產生 IV

本節大量重用 `docs/research/heatmap-valuation-method-selection.md` §3／§4.3
的既有結論（該文已經用【一手原始碼】＋【實測】等級證據回答了「業界／
成熟公開程式庫怎麼做」），只補本次新查的部分。

### 3.1 既有結論（重用，不重做）

| | 定價模型 | IV | q | 美式 |
|---|---|---|---|---|
| OptionsProfitCalculator | Black-Scholes【索引轉述】 | **由該合約自己市價反解、期間內恆定**【索引轉述】 | 未能確認 | 未能確認 |
| `rgaveiga/optionlab`（開源） | Merton BSM 含 q【一手原始碼】 | 呼叫端提供 | 一級輸入參數【一手原始碼】 | 無美式樹【一手原始碼】 |
| QuantLib | BS93／Barone-Adesi-Whaley／CRR 二項樹並列【一手原始碼】 | — | — | 三種都有【一手原始碼】 |
| Cboe 報價 feed 自家 `theo`／`iv` | **美式**【實測，該文 §4.3：直接用 Cboe 自家欄位反推】 | 美式反解 | 效果已含在 theo 裡 | 是 |
| **本 repo 現行（今日快照路徑）** | Bjerksund-Stensland (1993) 美式近似含連續股利 q，逐字自 QuantLib 原始碼移植 | **同模型、由該合約自己市價反解**（`implied_vol()`） | 有（`dividends.py`） | 是 |

**這張表最重要的一列是「IV」那一欄**：唯一講清楚自己怎麼算 IV 的公開工具
（OPC）用的是**自反解**，不是抄外部欄位。本 repo 現行的「今日快照」路徑
已經是這個做法（`option_chaser/valuation.py::implied_vol()`，見 §5）。
**本文的問題因此收斂成一句話：能不能把這套已經在用的「同模型、自反解」
方法，原封不動地套用在歷史、逐日的資料點上？**——答案在 §6：可以，
只是三個輸入（r／q／S）要從「今天」改成「point-in-time」。

### 3.2 vendor 端 IV 為何在歷史列上大量為 null（本次新查）

**沙箱出口限制（先講清楚，避免誤讀證據等級）**：本次檢索環境的出口
proxy 對 `marketdata.app` 全部子網域（含 `www.`／`docs.`／`api.`）
一律回 `CONNECT tunnel failed, response 403`——不是這個站台特有，
控制組（`example.com`／`en.wikipedia.org`／`web.archive.org` 等）
同樣全部被擋，確認是環境級的出口政策，不是「這個站台不存在或連不到」。
能連到的只有 `raw.githubusercontent.com`（可以直接讀到 Market Data App
官方開源 **Python SDK** 原始碼，屬一手來源）與 `WebSearch`（伺服器端
執行、不經本地 proxy，但回傳的是搜尋索引摘錄，不是一手頁面內容）。

**一手來源：Market Data App 官方 Python SDK**（`github.com/MarketDataApp/
sdk-py`，直接讀取 `input_types/options.py`／`output_types/options_
quotes.py`／`resources/options/quotes.py`／`CHANGELOG.md`）【一手來源】：

- SDK 的 `OptionsQuotesInput` 確認了本 repo 已經在用的 `date`／`from`／
  `to` 三個歷史查詢參數形狀，與 `option_chaser/data/marketdata.py` 現有
  的 `_QUOTES_URL` 樣式一致。
- `OptionsQuotes` 回應型別把 `iv: list[float]` 跟 `bid`／`ask`／`mid`／
  `last`／`underlyingPrice`／`delta`／`gamma`／`theta`／`vega` 放在**同一個
  型別**裡——**schema 層級沒有區分「即時」與「歷史」兩種變體**，也**沒有
  任何 docstring／註解／validator 提到 IV／Greeks 的缺值行為、計算模型、
  股利處理、或價格輸入基準**。SDK 本身只是薄的型別轉發層，不記載欄位
  語意。
- `CHANGELOG.md` 對 `from`/`to`/`date` 參數的曝光只是一次型別暴露的
  修正（1.3.0：「`options.quotes()` now exposes date, from, and to
  params」），**全篇 changelog 沒有任何一筆提到 Greeks／IV 的歷史回補、
  限制、或路線圖項目**。

**net：一手 SDK 原始碼本身對「為何歷史 IV 為 null」保持沉默**——它證實
了端點形狀，但不解釋原因。

**索引轉述：Market Data App 自家網站文案**（`WebSearch` 摘錄，未能一手
開啟，跨多次獨立查詢反覆命中同一段落）【索引轉述】：

> 「MarketData.app does not currently offer greeks or IV for historical
> end-of-day data, but they're working on adding that soon.」
> （對照同一頁族的即時／整鏈產品文案：「a full level 1 quote including:
> bid, ask, ..., implied volatility, full greeks...」）

換句話說，**這很可能是一個 vendor 自己承認、且列在路線圖上的產品缺口
（"coming soon"），不是本 repo 兩張真實合約特有的異常**——若這個讀法
成立，ORCL／TLT 觀測到的 250/250 null 是這個端點對**任何**合約、
**任何**時候的現行行為，不是資料品質問題。**但**另一次搜尋回傳的摘要
顯得矛盾（暗示歷史資料確實含 Greeks），本文**明確標註這個矛盾、不替
vendor 擅自下結論**——最可能的解釋是搜尋摘要把「歷史**價格**回溯到
2005/2010 年」與「歷史 **Greeks**」這兩句話混在一起，但**未能一手
查證**哪一句才對。

**旁證（索引轉述，Market Data App 自家 PHP SDK 文件摘錄）**：「if the IV
is not set (nil), the method returns the string 'nil'」——說明「IV 為
null」在 vendor 自己的客戶端函式庫裡是一個**已知、有明確處理路徑**的
狀態，不是會弄壞自己工具的未預期邊界案例。這只佐證「null 是被預期的
狀態」，不能證明「為什麼歷史列特別容易 null」。

**本文推導（標明是推理，非文件證據）**：把上面兩點索引摘錄合起來看
（vendor 明確講過「stock and options exchanges do not calculate or
provide Greeks and IV...every...data provider must undertake the
calculation of these values independently」——見 §4.1 已引用），一個
合理、但未經 vendor 明文證實的技術猜測是：**IV／Greeks 是掛在即時
運算層上算出來的，只在請求當下對著即時 surface 現算，歷史封存的是原始
報價（bid/ask/last/underlyingPrice），IV/Greeks 從未被回溯性地補算並
存進歷史封存**——這是選擇權資料 vendor 常見的架構模式（本文一般領域
知識，非 vendor 專屬證據），但**沒有任何 vendor 自己的陳述明講這個
機制**，仍須標為推論。

**與本 repo 既有觀察一致（repo 內部佐證，非 vendor 文件）**：
`option_chaser/data/marketdata.py:429-433` 既有註解已經記錄過同一個
經驗現象（「近期資料常見前幾筆 `null`，bid/ask 仍有值——這是『這天沒有
可信的 IV 報價』，不是『這天沒有資料』」），這是工程團隊自己先前的
判讀，與本次「coming soon」的索引摘錄方向一致，但是獨立觀察，不是
互相引用。

**結論**：Market Data App 為何歷史列 `iv` 為 null，最接近可信的解釋是
**vendor 自己承認的產品缺口（尚未支援歷史 Greeks/IV）**，而非本 repo
資料抓取路徑或合約選擇上的問題——這與 §2 的「exact-contract acquisition
已成功，缺的是 reconstruction」結論完全吻合，也代表**這個缺口不會自己
消失**：等 vendor 真的把它做出來之前，reconstruction 是唯一能讓
Historical IV Trend 對真實標的有內容可顯示的路。

### 3.3 早行使（early exercise）對 call／put 的不同影響（重用既有結論）

`option_chaser/valuation.py:451-517` 的既有註解已經把這點講清楚，直接
重用（【一手來源】，本 repo 自身程式碼＋docstring）：

- **Call 的提前履約誘因來自股利**：q>0 時，提早履約拿到標的、在除息日前
  收下股利可能比繼續持有選擇權更划算；q≤0 時提前履約永不最優，美式 call
  退化成歐式（`_bs93_call_core` 的 `bT >= rT` 分支，逐位元等於 Merton 解）。
- **Put 的提前履約誘因來自時間價值**：把履約價的現金提早拿去生息，
  誘因來自 r，不是 q；因此 put 走 put-call symmetry（`S↔K`、`r↔q`）代入
  同一個 call 核心函式，「何時退化成歐式」的判準對稱地變成 `r<=0`。

這與 Cox-Ross-Rubinstein (1979)、Barone-Adesi & Whaley (1987)、
Bjerksund & Stensland (1993) 三篇經典論文處理美式選擇權提前履約邊界的
標準框架一致（QuantLib 把三者並列在同一個 pricing engine 工具箱裡，
`heatmap-valuation-method-selection.md` §3.3 已【一手原始碼】確認）。
本文不重複這三篇論文的數學推導。

## 4. Input definitions 逐項確認

### 4.1 Option price：last / bid / ask / mid / NBBO mid

**Pricing 函式庫本身刻意不管這題**（【一手來源】，直接讀原始碼）：
QuantLib（`ql/instruments/impliedvolatility.cpp`、
`Examples/EquityOption/EquityOption.cpp`，皆為 `master` 分支）與
py_vollib（`vollib/black_scholes/implied_volatility.py`、
`vollib/black_scholes_merton/implied_volatility.py`，`vollib/vollib`
commit `11f2058`）都只接受一個抽象的 `price`／`targetValue` 參數，
docstring 逐字只寫「the Black-Scholes option price」，**全文沒有一處
提到 bid/ask/mid/last**——這兩個業界標準函式庫把「該用哪個價格」的
決定權完全交給呼叫端，不在函式庫層面規定。

**真正計算出一份可回溯歷史 IV 序列的三個系統，一致收斂在 NBBO mid**
（【索引轉述】，皆為 WebSearch 摘錄、未能一手開啟原頁）：

- **Cboe VIX 方法論**：`Q(Kᵢ)` 定義為該筆選擇權 bid/ask 報價的
  **中價**。
- **OptionMetrics IvyDB**（學術界最常用的歷史選擇權＋IV 資料集）：
  「computes option mid prices by averaging the bid and ask prices,
  which are used as reference prices for calculating implied
  volatility」。
- **ORATS**（Tradier 的 Greeks/IV 資料供應商，Tradier 官方文件本身
  對此沉默，往上一層追到 ORATS 自己的方法論）：於「current NBBO bid
  and ask prices」的中點反解 IV，再擬合無套利平滑曲線。

**IBKR 是唯一的例外，且例外的方式本身也是有用的訊號**（【索引轉述】，
多次獨立查詢一致命中同一批 IBKR 官方網域，網域歸屬信心較高，但**未能
一手開啟原頁逐字核對**）：IBKR TWS API 對同一張合約**同時**提供四種
獨立的即時 Greeks/IV tick type，各自錨定不同價格——bid（tick 10）、
ask（tick 11）、last（tick 12）、IBKR 自己的 model/theoretical price
（tick 13）——**不收斂成單一「這就是這張合約的 IV」**。這對本文的
啟示是：「唯一正確的價格輸入」本身就不是業界鐵律，是一個工程／產品
判斷；本文選 mid 是因為 mid 最接近「vendor 已經幫我們算好、不需要
自己決定要不要用 last 這種可能過期很久的成交價」的最低爭議選項，不是
因為業界只有一種做法。

**額外佐證（附帶發現，非本題原本要問的）**：Schwab thinkorswim 官方
研究文件（【索引轉述】，`toslc.thinkorswim.com` 的 study library 頁）
指出其「Implied Volatility」study 是「an approximation method based
on the Bjerksund-Stensland model」——這與本 repo `heatmap-valuation-
method-selection.md` 已經選定的模型**獨立吻合**（該文原本比較的
OptionsProfitCalculator／optionlab 都不是用 BS93），值得在該文件之後
的維護中補一筆這個新佐證，但不影響本文任何結論。

**本 repo 手上實際可用的欄位**：exact-contract 歷史列同時含
`bid`／`ask`／`mid`／`last`（§2 已【實測】確認四者皆非空），**不需要
自己算 `(bid+ask)/2`**——vendor 已經提供算好的 `mid`。

**crossed／stale／wide spread 如何處理**：`docs/research/option-liquidity-
filtering.md` 已經是一份專門的報價品質研究（§6.2【索引轉述】：業界偵測
陳舊報價的方式是**無套利一致性檢查**，不是時戳——Cboe 自家 delayed
quote feed 本身就沒有逐筆時戳）。該文的四道既有關卡（`quote_ok`／
`iv_ok`／`oi_volume_ok`／`spread_ok`）是為**今日快照、揀選候選**設計的，
不能原樣套用在「歷史單一觀測、只是要不要納入反解」這個不同的場景——
但無套利一致性檢查本身（例如 `bid <= mid <= ask`、`bid>0` 且未倒掛）
是通用原則，可以直接借來當「這筆歷史觀測值不值得拿去反解」的最低品質
關卡（詳見 §10 recipe）。

### 4.2 Underlying price：spot / historical close / contemporaneous quote / forward

**已解決，不是空白**：exact-contract 歷史報價回應本身就帶
`underlyingPrice`（§2 已【實測】確認），與該筆選擇權報價**同一列、
同一個 `updated` 時戳**——這正是「contemporaneous underlying quote」，
是四個候選裡理論上最正確的一個（不需要再去對一個獨立的歷史標的收盤價
資料源，也不會有「選擇權報價是盤中、標的價是收盤」的時點錯配問題）。
唯一的工程動作是**別再丟掉這個欄位**（見 §6.4）。

### 4.3 Time to expiration

**沿用既有慣例，不引入新的口徑**：`option_chaser/valuation.py:10,66`
（`DAYS_PER_YEAR = 365.0`、`days_between()` 純日曆天差）是全引擎唯一的
day-count 慣例，T3 之後的排名與 T12 之後的估值全部靠這一個常數。
歷史 reconstruction 若引入不同的 day-count（例如 ACT/365.25 或交易日），
會讓「今天算出來的 IV」與「用歷史 recipe 算出來的 IV」在**同一張合約
同一天**的邊界上對不齊，直接違反「同一份走勢圖，前後一致」的產品直覺。
**建議**：歷史 reconstruction 的 T 用同一個 `days_between(觀測日,
到期日) / 365.0`。

exact-contract 歷史列裡的 `dte` 欄位（§2 已確認存在）理論上可以直接拿來
用，但**建議仍以 `days_between()` 自己算**，不要信任 vendor 給的
`dte`——理由：(a) 不確定 vendor 的 `dte` 是用交易日還是日曆天，兩者在
LEAPS 尺度上的差異足以造成 IV 反解誤差；(b) 自己算能保證跟「今天快照」
路徑用同一個函式、同一個口徑，vendor 換算法不會悄悄污染歷史序列。
到期時刻（市場收盤 vs 午夜）本文**未能查證**業界標準做法比 ACT/365
細到這個精度是否值得——`heatmap-valuation-method-selection.md` §7 已
量化過類似精度取捨（r 曲線選擇差異 <某個量級即不值得做細），同一精神
適用於這裡：這是 NICE TO HAVE，不是 v1 必要項（見 §10）。

### 4.4 Risk-free rate：2025-10-01 的選擇權，用哪一天的 r？

**答案（本文推導，直接應用 no-look-ahead 原則，不是新研究）**：用
**2025-10-01 當時可取得的利率曲線**，不是今天的曲線。

**業界文件對這題明講的程度**（本次新查，【未能查證】+ 循環佐證）：
沒有找到任何一手或索引來源明文寫「歷史選擇權要用觀測當天的利率曲線，
不能用今天的」——這符合預期，這種等級的方法論細節通常不會出現在 vendor
FAQ 裡。唯二的間接佐證（皆【索引轉述】）：OptionMetrics IvyDB 的利率
輸入是「與到期日同年期的零息利率，由當天 zero curve 上最近兩個節點
線性插值」，而 IvyDB 本質上是一個逐日建置的歷史 panel dataset，「當天
的 zero curve」這個結構本身就隱含逐日對齊；Cboe VIX 方法論的利率輸入
同樣是「每日用當天 curve 插值」，且 VIX 有數十年的每日發布歷史，
每一天的印出值都必然只用了那天自己的曲線（不然無法逐日重算同一個
公式）。兩者都是**從『這套方法本來就是逐日跑』反推出『歷史上每一天
用的是那天的曲線』，不是一句明文的「不得使用未來利率」聲明**——本文
的 no-look-ahead 建議因此仍然主要站在「這是金融時間序列分析的基本
常識」這個立場上，業界文件提供的是循環佐證，不是正面證據。BS/BS93 的 r 定義
是「與到期日同年期的連續複利無風險零息利率」（`risk-free-rate-for-bs.md`
§2，已【一手來源】確認 Hull 教科書章節框架），這是一個**在該時點觀測到
的市場量**，跟該時點的股價、報價一樣，都是「當時已知」的資訊；拿今天
的曲線去定價一張 2025-10-01 的歷史觀測，等於把 2026-08 才知道的利率
資訊偷渡進 2025-10-01 的 IV 裡，是教科書等級的 look-ahead bias（§7 有
專門一節展開）。

**這在技術上可不可行**：可行，且成本很低。Treasury Daily Par Yield
Curve 的既有端點本身就支援指定歷史年／月抓整批曲線
（`field_tdr_date_value={YYYY}` 或 `{YYYYMM}`，`risk-free-rate-for-bs.md`
§4.1 已列出這個 URL 樣式）——`option_chaser/ratecurve.py` 現有的
`parse_treasury_csv()`／`parse_treasury_xml()` 解析器**已經在處理「一整批
日期、逐列都是一天的曲線」這種形狀**，只是目前呼叫端邏輯（`best is None
or curve_date > best[0]`，`ratecurve.py:152`）永遠只取全檔案裡日期最大的
那一列——這是為「今天」場景寫的，不是解析器本身的限制。改成「取 ≤ 目標
日期的最近一列」是**同一個解析器加一個參數**，不是重寫（詳見 §6.1）。

### 4.5 Dividend：ORCL（equity）vs TLT（ETF）要不要不同處理

`dividend-yield-source-selection.md` 已經是一份專門研究（§4：ETF 發行商
官方配息資料；§5：Yahoo/FMP/Nasdaq 等公開市場 API），現有 `dividends.py`
的抓取鏈（Yahoo → FMP → Nasdaq）**不分 equity/ETF**，統一走同一套
`events.dividends`／`dividends` 端點格式。這是刻意的：q 的定義
（trailing 365 天經常性現金分配 ÷ spot）在數學上對 equity 跟 ETF
一視同仁，差異只在**資料品質**——ETF（如 TLT）配息頻率高、金額規律，
equity（如 ORCL）配息較稀疏、偶有特別股利（`dividends.py` 已有的
「單期超過近 12 期中位數 3 倍視為異常」防護正是為了處理這種情形，
`dividends.py:32-38`）。**沒有查到需要為 equity/ETF 分岔出兩套處理邏輯
的依據**——現有的「trailing distribution ÷ spot」＋異常值防護對兩者
都適用，只是 ORCL 這種配息稀疏標的的 q 估計噪音天生比 TLT 大，這是
資料品質問題，不是方法論分岔的理由。

**歷史 point-in-time 版本的唯一必要修改**（本文推導，直接應用 §7 no-
look-ahead 原則）：q(t) = （ex_date ≤ t 的 trailing 365 天分配總額）
÷（t 當時的標的價）。`dividends.py` 現有的 `DividendHistory.distributions`
本來就是完整的 `(ex_date, amount)` 清單而非算好丟棄原始資料的單一數字
（`dividends.py:57-63` 的既有 docstring 已經明講這是刻意設計：「q 是
比例，分母會隨行情變動，快取算好的 q 會把過期價格基準凍結進去」）——
這個既有設計選擇對歷史重建剛好是對的形狀，只是「除以哪個 spot」要從
「本次快照 spot（今天）」改成「目標歷史日期的 spot」（來源見 §4.2：
剛好就是 exact-contract 歷史列自帶的 `underlyingPrice`，不需要另一個
資料源）。

## 5. Pricing model 比較與選型

**結論（重用 `heatmap-valuation-method-selection.md` §10-1/10-2，不重新
研究）**：**Bjerksund-Stensland (1993)**，含連續股利殖利率 q，`q<=0` 時
逐位元退化成 Merton 歐式解。該文已經用真實 TLT 報價量化比較過
Black-Scholes／Merton／CRR 二項樹／Barone-Adesi-Whaley／BS93 五者的
精度與成本（§5），結論是 BS93 在成本（3.83ms／矩陣 vs CRR300 的
9.85 秒）與精度（QuantLib 同源）之間是唯一同時滿足「純 stdlib、無新
依賴、成熟公開」三個硬約束的選項；CRR 明確**不建議當 production
估值器，但建議留在測試裡當精度對照基準**（該文既有建議，本文不重複
理由，見該文 §10-1 逐字）。

**本 repo 現行 `option_chaser/valuation.py::american_price()` 與
`implied_vol()` 已經是這個模型的完整實作**（§6 詳述可重用範圍）。
**本文不需要為「歷史 reconstruction」重新選型**——這是同一個反解問題，
差別只在輸入的 S／r／q／T 從「今天」換成「某個歷史日期」，模型本身
（一個純函式 `american_price(option_type, S, K, T, r, q, sigma)`）
對「今天算」還是「历史某天算」沒有任何區別，這正是純函式最有價值的
地方：**同一個引擎原語，餵不同的（S,K,T,r,q）就能同時服務兩種場景**。

## 6. Repo 現有能力可重用性評估

### 6.1 `option_chaser/valuation.py::implied_vol()` 用什麼模型？適合直接重用嗎？

**用什麼模型**：Bjerksund-Stensland (1993) 美式近似（`american_price()`），
含連續股利殖利率 q，二分法反解 σ（`implied_vol()`，60 次迭代收斂到
`hi-lo < 1e-12`，找不到解時誠實回 `None`，不外插不亂猜——`valuation.py:
553-586`，見本文開頭已引用的完整原始碼）。

**適合直接重用**：**適合，且不需要修改這個函式本身**——它已經是純函式
（`option_type, target_price, S, K, T, r, q`），對呼叫端來說「今天的
target_price/S/r/q」跟「某個歷史日期的 target_price/S/r/q」沒有任何
介面差異。歷史 reconstruction 需要新增的是**呼叫端**：一個新的、獨立於
現有 `service.py`/`calibrate_leg()` 的路徑，把 exact-contract 歷史列的
`(mid, underlyingPrice, dte-derived T)` 加上 point-in-time 的 `(r, q)`
餵給同一個 `implied_vol()`——不改動函式本身，是新增一個呼叫路徑，符合
spec #151 既有的「新 feature 不改既有引擎行為」紅線精神（HIVT 系列全程
遵守的同一條紅線）。

### 6.2 歷史 rate 是否真的可取得？

**可取得**。Treasury Daily Par Yield Curve 端點支援用
`field_tdr_date_value={YYYY}`／`{YYYYMM}` 抓一整年／一整月的歷史曲線
（`risk-free-rate-for-bs.md` §4.1 已列出樣式）。`ratecurve.py` 現有的
`parse_treasury_csv()`／`parse_treasury_xml()` 已經能解析「多列、每列
一天」的完整表格（`parse_treasury_csv()` 的迴圈本來就走訪 `rows[1:]`
全部列，只是目前的比較邏輯 `curve_date > best[0]` 永遠選最大值，
`ratecurve.py:141-156`）。**需要的擴充**：一個新函式或參數，語意從
「這批資料裡最新的一列」改成「這批資料裡 ≤ 目標日期的最近一列」——
純函式層級的小改動，抓取層（`data/treasury.py`）需要改成能對指定歷史
年份發請求（現有大概率是抓「今年」）。**這是 MUST HAVE 的工程缺口，
不是資料源缺口**（詳見 §10）。

### 6.3 歷史 dividend 是否真的可取得？

**可取得**。`dividends.py` 的 `DividendHistory.distributions` 是完整的
`(ex_date, amount)` 清單（Yahoo `range=2y` 窗口，`data/dividends.py:40`），
不是只算好丟棄原始資料的單一 q 值。對 1 年歷史窗（`IV_TREND_MAX_
HISTORY_DAYS=365`）而言，2 年抓取窗**綽綽有餘**——最早的歷史觀測日
（今天−365 天）往前再抓 365 天的配息記錄（q 定義需要的 trailing 窗），
仍落在 Yahoo 2 年窗之內。**需要的擴充**：呼叫端把「除以今天 spot」
改成「除以目標日期的 spot（來自 §4.2 的 `underlyingPrice`）」＋
「只納入 `ex_date <= 目標日期` 的配息」——同樣是純函式層級的小改動，
不是新資料源。

### 6.4 若缺少，最小必要資料源是什麼？

**沒有缺少任何資料源**——這是本文最重要的一個結論。三項輸入（S／r／q）
的原始資料全部已經在手上（S 直接來自 exact-contract 歷史列本身；r／q
的原始資料在既有的 `ratecurve.py`／`dividends.py` 抓取鏈裡），缺的是
**三處呼叫端邏輯的 point-in-time 化**（r／q 各自從「取今天」改成「取
歷史某天」；S 從「被丟棄」改成「被保留」）。這與 §5 的結論相呼應：
模型與資料源選型都不是空白，本文真正的增量價值是把這些既有積木拼成
「歷史逐日」的形狀，並誠實標出拼接處的 look-ahead 陷阱（§7）。

### 6.5 哪些資料 Market Data App 歷史端點已經直接提供，不需要再抓？

`bid`／`ask`／`mid`／`last`／`underlyingPrice`／`dte`／`updated`（觀測
時戳）——全部已經在同一次 API 呼叫、同一筆歷史列裡（§2 已【實測】
確認）。**不需要**：獨立的歷史標的收盤價資料源（§4.2）、獨立的歷史
NBBO 報價源（§4.1，vendor 已給 bid/ask/mid）。

### 6.6 `_parse_contract_history()` 目前實際上做了什麼（現有程式碼的落差）

【一手來源】`option_chaser/data/marketdata.py:453-488`：目前的解析器
**只萃取 `(date, iv)` 兩個欄位**，`bid`／`ask`／`mid`／`last`／
`underlyingPrice`／`dte` 全部在解析當下就被丟棄，即使原始 payload
裡都有（HIVT-02/03/HIVT-07 至今這個路徑只被拿來服務「vendor 有給
IV 就顯示」這個 v1 範圍，尚未有需要保留價格欄位的呼叫端）。**這是本文
建議的 v1 recipe 唯一需要碰的既有檔案**：擴充回傳形狀，不是重寫解析
邏輯本身（現有的 `updated`→日期轉換、`_num()` 缺值口徑、
`dropped_missing_date` telemetry 全部原封不動沿用）。

## 7. Historical information integrity（防止 look-ahead bias）

**核心原則（本文推導，套用金融時間序列分析的標準常識，非新研究）**：
2025-10-01 的歷史 IV，只能用「2025-10-01 當時、市場參與者實際能觀測到」
的資訊算出來。任何在那之後才確定、才公布、或才存在的資訊，即使今天
已知，都不得用來算那一天的 IV。

逐項分類：

| 輸入 | Contemporaneous（當時可知，✅ 可用） | Look-ahead（事後才知，❌ 不可用） |
|---|---|---|
| 選擇權價格（bid/ask/mid/last） | 該筆歷史觀測本身的 `bid`/`ask`/`mid`/`last`（vendor 已給，時戳同步） | 用「今天」重新查一次同一張合約的當前報價 |
| 標的價 | 該筆歷史觀測的 `underlyingPrice`（同列、同時戳） | 用今天的標的收盤價／即時價 |
| 到期日／履約價／型別 | 合約身份本身不隨時間變（OCC symbol 定義即不變） | （不適用——這三者本來就不隨時間變） |
| 利率 | **抓取日期對齊到目標觀測日**的 Treasury 曲線（§6.2） | 用今天最新的 Treasury 曲線 |
| 股利 | 只納入 **ex_date ≤ 目標觀測日** 的配息記錄（§6.3） | 納入目標觀測日之後才除息的配息、或事後才公告的特別股利 |
| Time to expiration | `days_between(該筆觀測日, 到期日)`（永遠是「從那天看還剩幾天」，天生無 look-ahead 風險） | （不適用） |

**已知、不可避免的近似（誠實記錄，不假裝解決）**：

1. **股利公告時點 vs ex-date**：本文用 `ex_date` 當「該筆配息何時變成
   公開已知資訊」的代理——多數常規配息在 ex-date 前數週就已公告，
   這個代理保守（傾向晚納入，不會提前納入），方向正確；但特別股利
   偶有極短前置期的案例，本文【未能查證】是否所有特別股利都在 ex-date
   前充分公告。這是 v1 可接受的近似，不是被忽略的風險——`dividends.py`
   既有的異常值防護（單期超過中位數 3 倍即用中位數取代）本來就是為了
   壓住這類離群值對 q 的影響，同一防護對歷史版本同樣適用。
2. **利率曲線的抓取日 vs 公布日**：Treasury 曲線通常在收盤後公布當天
   的曲線，本文假設「目標觀測日當天的曲線」在該日已經是最終值——這是
   標準假設（Treasury 公布的是官方定盤價，不是需要事後修正的初值），
   風險極低。
3. **無法完全排除的近似**：exact-contract 歷史報價本身的 `updated`
   時戳解析度（`_observation_date()` 目前只到日，不到分鐘/秒，
   `marketdata.py:438-445`）意味著同一天內标的价格若有明显日内波動，
   我們只能用 vendor 給的那個時點快照，不能重建「那一天任何時刻」的
   IV——這是 vendor 資料本身的顆粒度限制，不是本文方法論的缺陷。

## 8. Calibration experiment 設計

**目的重申**：不是要猜中 Market Data App 專有原始碼，而是找一個公開、
可重現、誤差穩定、足以支撐我們自己歷史 IV 序列的 recipe——用「vendor
IV 已知」的真實觀測反過來驗證我們自己重建出來的 IV 夠不夠準。

### 8.1 資料池

**用 vendor IV 非 null 的真實觀測**——這些存在於**今日／近期**快照
（本 repo 現行的「今日快照」路徑，vendor 的即時 chain 端點本來就給
非 null 的 iv／greeks，這是 §2 已確認的「即時 vs 歷史」落差的另一面：
即時有、歷史沒有）。已有精確前例：`tests/fixtures/tlt_leaps_real_
quotes_2026-07-17.json`（#110 研究用的真實 TLT LEAPS 報價，含
vendor-reported iv／greeks），以及既有的 `scripts/research_valuation_
methods.py` 研究用純函式（不進引擎，`option_chaser/` 不 import 它，
專門服務這類「比較用」腳本）——**沿用同一套既有基礎設施抓新的樣本，
不是另起爐灶**。

**抽樣維度**（依票面要求）：call/put、ITM/ATM/OTM、short/medium/LEAPS、
equity/ETF、low/high dividend——建議至少各維度 2–3 個真實觀測，總樣本
數落在 30–60 筆量級（足夠算出穩定的 MAE/median/p90，又不會把 vendor
credit 燒在單一實驗上；1 credit／單合約查詢，30–60 筆歷史序列可能只需
個位數到十位數次單合約呼叫，因為單次呼叫回整段區間）。

### 8.2 Recipe 組合（Model × Price input × Rate source × Dividend treatment × Time convention）

由於 §5 已經把 pricing model 收斂到 BS93（唯一符合 repo 硬約束的選項），
**本實驗的 model 軸不需要真的展開比較**——CRR 已經在既有研究裡被列為
「留著當精度對照基準」而非候選；本實驗應該把維度集中在真正還有分歧的
三個軸：

- **Price input**：`mid` vs `last`（`bid`/`ask` 單獨不建議當反解輸入，
  §4.1 已說明理由）
- **Rate source**：point-in-time 曲線（§6.2 建議）vs 今天的曲線（
  作為「不做對」的對照組，量化 look-ahead 到底貴不貴——呼應
  `risk-free-rate-for-bs.md` §7 已經做過的「r 敏感度」量化手法，這裡
  是同一手法套在歷史場景）
  vs 一個「單一固定值」的極簡對照組（例如整段歷史用同一個 r，量化
  「連期限對齊都不做」要付多少代價）
- **Dividend treatment**：point-in-time trailing q（§6.3 建議）vs
  q=0 對照組（量化「完全不處理股利」的代價，呼應
  `heatmap-valuation-method-selection.md` §4 已經量化過的「q=0 在今日
  快照上讓 IV 反解無解」現象，這裡驗證同一現象在歷史序列上是否一樣
  嚴重）

Time convention 軸**不建議展開比較**——§4.3 已經論證只有一個站得住的
選擇（沿用引擎既有的 `days/365`），展開比較只是在驗證一個已經沒有
分歧的變數，浪費樣本。

### 8.3 指標與判準

- **MAE**、**median absolute error**、**p90 error**（vol points，例如
  IV=32.5% 記為 0.325）——沿用票面要求。
- **Bias**（signed mean error）：用來抓「系統性偏高/偏低」而非只看
  離散度——例如 q=0 對照組預期會出現系統性偏低的 bias（賣方少算了
  股利，call 的理論價偏低，反解出的 IV 會偏高去補償），這個方向性
  本身就是有用的診斷訊號。
- **Failure rate**：`implied_vol()` 回傳 `None` 的比例（目標價落在
  模型可行區間外）——`heatmap-valuation-method-selection.md` §4.2
  已經証實 q=0 對真實近價位 LEAPS 而言在數學上**經常無解**，這個
  指標預期會是「q=0 對照組」與「真實 q」版本之間差距最大的一項。

### 8.4 判準：多好才算「夠好」

**建議判準（本文推導）**：v1 recipe（point-in-time r／q／mid）相對
vendor 真實 IV 的 median absolute error 應落在**個位數 vol points
以內**（例如 <3–5 vol pts），且 failure rate 應顯著低於 q=0 對照組。
這不是一個精確到小數點的工程指標，而是「這組重建出來的歷史序列，
拿來畫『現在比過去貴還是便宜』的相對走勢圖，方向與量級判斷不會被
反解誤差本身帶偏」這個產品目標的合理下限——呼應 spec #151 全系列
「Historical IV Trend 供歷史位置參考，不代表未來方向」的既有定位
（`IvTrend.tsx` 既有 caption 文案）。**具體數字最終仍待需求方核准**
（§12）。

### 8.5 本文不做、留給後續實作票的事

本節只是**設計**，不執行。要真的跑這個實驗，需要：(a) 一個新的
`scripts/research_historical_iv_reconstruction.py`（比照既有
`research_valuation_methods.py` 的「純函式、不進引擎」慣例）；
(b) 一批真實觀測樣本（需要用真實 `MARKETDATA_APP_TOKEN` 抓，比照
既有 `tmp-*` 一次性 CI probe 慣例）；(c) 一份對應的
`docs/research/historical-iv-reconstruction-calibration-results.md`
記錄實測數字。這些是下一輪 `/to-tickets` 的範圍，不在本文。

## 9. Decision Matrix：三個候選方案

| | **A. Vendor IV only** | **B. Simple reconstruction** | **C. Production-grade reconstruction** |
|---|---|---|---|
| 定義 | 有 vendor `iv` 就用，`null` 就誠實缺值（現行 HIVT-01–07 行為，不改） | mid 價格輸入 ＋ BS93（不是純 BSM）＋ point-in-time r／q ＋ 既有 day-count | American 模型（同 B）＋ 更精細的歷史曲線（如逐日 bootstrap）＋ 更嚴謹股利處理（如逐日 cross-strike Method E 校準，需要歷史整鏈）＋ 逐筆報價品質過濾（無套利一致性檢查、非只看是否非空） |
| accuracy | **對真實 ORCL/TLT 幾乎等於「沒有歷史 IV 這個功能」**（250/250 null） | 待 §8 實測驗證，預期個位數 vol pts 誤差量級（依 §8.4 判準） | 理論上略優於 B，但 §6.1 已說明本 repo 沒有「當天整條歷史鏈」資料源可支撐逐日 Method E 校準——這一項的邊際精度提升目前**無法兌現**，除非另外採購歷史整鏈資料源 |
| engineering complexity | 零（已完成） | 中——三處呼叫端擴充（r／q point-in-time 化、S 欄位保留），全部重用既有純函式，不改動 `implied_vol()`/`american_price()` 本身 | 高——需要新資料源（歷史整鏈）、新的逐日校準管線、新的報價品質過濾器 |
| data dependencies | 現有（無新增） | 現有（Treasury 歷史曲線端點、Yahoo 配息歷史、exact-contract 歷史列本身），無新增外部資料源 | 需要新增：歷史整條 option chain 資料源（`historical-options-iv-data-sources.md` 已盤點過候選，全部與「不自建資料庫」或「REST 按需查詢」硬約束有衝突或代價顯著更高） |
| compute cost | 零 | 低——BS93 單次估值 3.83ms 量級（`heatmap-valuation-method-selection.md` §5.3 已實測），二分法反解 60 次迭代／點，全歷史序列（≤365 點）仍是毫秒級 | 中～高，取決於逐日校準的展開方式 |
| vendor credits | 已花（單合約查詢已經在付） | 不變——沿用同一次歷史查詢拿到的欄位，不多打任何 vendor 呼叫 | 增加——歷史整鏈查詢比單合約貴得多（且需要逐日查，不是一次查整段區間） |
| failure modes | 「功能幾乎空白」對真實資料是常態，不是邊緣案例 | `implied_vol()` 既有的「目標價落在模型可行區間外回 `None`」機制直接沿用，缺值行為與現行「vendor null」在使用者眼中觀感一致（同一種「誠實缺值」UX，不需要新的錯誤處理形狀） | 同 B，但多了「歷史整鏈這天抓不到」這個新的失敗模式，且失敗頻率與盤中／盤後資料完整度強相關（`historical-options-iv-data-sources.md` 已記錄類似問題） |
| reproducibility | 完全可重現（沒有計算，只是轉述 vendor） | 完全可重現——純函式、固定輸入即固定輸出，可寫成標準單元測試 fixture（比照現有 `implied_vol()` 測試手法） | 較低——逐日校準結果依賴當天能不能抓到足夠品質的整鏈報價，同一天重跑可能因為 vendor 端資料變動而得到不同的校準 q |
| resume / portfolio 可信度 | 低——功能形同虛設，難以在履歷/作品集脈絡中展示「解決了什麼問題」 | 高——完整故事線清楚：發現 vendor 缺陷 → 業界方法論調查 → 重用既有引擎原語 → 加上 look-ahead bias 防護 → 實測校準驗證，是一個完整、可講的工程判斷案例 | 中——理論上更完整，但若 accuracy 提升無法兌現（見上）、只是徒增複雜度，反而是「過度工程」的反面案例 |

## 10. Recommended v1 recipe

- **price input =** `mid`（vendor 已給，不用 `(bid+ask)/2` 自算；歷史觀測
  若 `mid` 缺值則退回 `(bid+ask)/2` 自算，兩者都缺則該筆觀測跳過，不用
  `last`——理由見 §4.1／§3.2）
- **pricing model =** Bjerksund-Stensland (1993) 美式近似，含連續股利
  殖利率 q（`option_chaser/valuation.py::american_price()`，**原封不動
  重用，不新增模型**）
- **underlying input =** exact-contract 歷史列自帶的 `underlyingPrice`
  （同列、同時戳，**不新增資料源**）
- **rate =** point-in-time Treasury 曲線，取 ≤ 觀測日的最近一列
  （`ratecurve.py` 既有解析器擴充「取最近一列」邏輯，**不新增資料源**）
- **dividend =** trailing 365 天配息（`ex_date <= 觀測日`）÷ 觀測日當時
  `underlyingPrice`（`dividends.py` 既有 `DividendHistory.distributions`
  擴充成 point-in-time 篩選，**不新增資料源**；equity／ETF 不分岔處理，
  理由見 §4.5）
- **time convention =** `days_between(觀測日, 到期日) / 365.0`（沿用引擎
  既有唯一慣例，**不引入新 day-count**）
- **quote-quality filter =** 無套利一致性最低關卡（`bid>0`、
  `bid<=mid<=ask` 未倒掛）；不套用今日快照專用的四道候選揀選關卡
  （`oi_volume_ok` 等，那些是為「今天挑候選」設計的，歷史單點反解
  不需要，見 §4.1）
- **inversion solver =** `option_chaser/valuation.py::implied_vol()`
  （**原封不動重用**，二分法、找不到解回 `None`）
- **failure behavior =** 任何一步輸入缺失（r 曲線抓不到、q 校準不出來、
  `mid`/`(bid,ask)` 都缺、`implied_vol()` 回 `None`）→ 該筆歷史觀測點
  誠實缺值（沿用 spec #151 全系列「缺席就如實缺席、不外插不偽造」
  的既有原則，`ivtrend.py` 既有的 `(date, None)` 形狀原封不動接得住）
- **vendor IV present 時怎麼辦 =** **直接用 vendor 給的值，不跑
  reconstruction**——vendor 有給就是最直接的一手資料，沒有理由用自己
  的近似模型去覆蓋它；reconstruction 只在 vendor `iv` 為 `null` 時
  才啟動（per-observation 判斷，不是 per-request 整批切換）
- **vendor IV null 時怎麼辦 =** 依上述 recipe 嘗試反解；反解失敗（見
  failure behavior）則該點缺值，不影響其他點

### MUST HAVE（不做就會讓 IV 明顯失真）

1. Point-in-time 利率曲線（不能用今天的曲線算歷史 IV——§7 已量化這是
   教科書等級的 look-ahead bias，且 `heatmap-valuation-method-selection.md`
   §4.2 已證實 q/r 選錯會讓反解直接無解，不是「差一點」的問題）
2. Point-in-time 股利（`ex_date <= 觀測日` 篩選——同一理由）
3. 使用 exact-contract 歷史列自帶的 `underlyingPrice`（同時點標的價，
   不是事後才知道的收盤價）
4. 沿用引擎既有的美式模型與 day-count 慣例，不為歷史路徑另開一套
   （否則同一張合約「今天」與「歷史」兩條路徑會算出不一致的 IV，
   使用者會覺得走勢圖在接點處有一個沒有解釋的跳動）
5. `mid` 優先於 `last` 當價格輸入（§4.1／§3.2；last 可能是舊到失真的
   一筆過期成交）

### NICE TO HAVE（可以之後升級）

1. 更精細的到期時刻／交易日 day-count（§4.3 已論證這是精度數量級遠小於
   其他誤差源的優化，非必要）
2. §8 的 calibration experiment 實際執行、量化出真實誤差數字，讓 v1
   recipe 的參數（例如異常值防護門檻）有實測依據，而不只是既有研究
   類比套用
3. 報價品質更細緻的分級（例如寬價差時降級信心而非只是二元收/不收）

### OVERENGINEERING FOR V1（現在不要做）

1. 逐日 cross-strike q 校準（Method E 的歷史版本）——需要歷史整鏈資料源，
   本 repo 目前的硬約束（不自建資料庫、REST 按需查詢、成本可控）下沒有
   合格候選（§6、`historical-options-iv-data-sources.md` 已盤點）
2. 為 equity／ETF 分別設計不同的股利處理管線（§4.5 已論證數學上沒有
   分岔的必要，只有資料品質差異，且既有異常值防護已經覆蓋）
3. 交易日曆微調（假日／半日市場的精確 T 計算）——`heatmap-valuation-
   method-selection.md` 已多次示範這個量級的精度優化不值得（§4.3）
4. 用二項樹（CRR）或其他更複雜的美式模型取代 BS93——`heatmap-valuation-
   method-selection.md` §10-1 已明確結論不建議，BS93 已經是同源
   QuantLib 工具箱裡的封閉解選項

## 11. Diagnostics 降噪分析（僅分析，不施工）

**現況**（【一手來源】，`api_app/main.py:1314-1414` 的 `/api/scenarios/
{id}/iv-history` 端點）：exact-contract 家族的 legs 迴圈跑完之後
（1372–1381 行），端點**無條件**繼續往下跑 (tenor,delta) 重錨定家族的
整段既有流程：

```
_backfill_iv(...)                              # 最多 25 天 × N 個到期日
                                                #   × 2 事件（vendor_fetch/
                                                #   payload_parse）
for obs in _db().iv_observations(sc.symbol):   # 這個 symbol 目前存了
    reanchor_spread(surface, coords)           #   多少天快照，就重跑
    _emit_reanchor(...)                        #   多少次 reanchor＋
                                                #   emit 一次
_emit_metrics(...)
```

**噪音的兩個真正來源**（不是「vendor 不穩定」，是架構本身的重複計算）：

1. **`_backfill_iv` 的逐日缺口補齊**（1392 行）：註解自己承認「一次
   backfill 最多 25 天 × 數個到期日，每次 vendor 呼叫又拆成
   `vendor_fetch`／`payload_parse` 兩筆」（`main.py:264-266`）——單次
   request 理論上限可以到 25 × N expirations × 2 ≈ 上百筆原始事件。
   週末／假日「這天沒資料」屬於 `vendor_status="no_data"` →
   severity `warning`（`_vendor_fetch_severity`，`main.py:324-332`），
   這是**正常、預期會發生的日常噪音**（每週兩天），不是異常，但目前
   跟真正的異常訊號混在同一個 severity 桶裡搶 `_select_for_persistence`
   的保留名額（`main.py:287-316`）。
2. **`reanchor` 對整段歷史的重複重放**（1402–1408 行）：這一段迴圈
   **每一次 API 呼叫**都會對這個 symbol 目前資料庫裡**已經存在的每一筆
   歷史快照**重新跑一次 `reanchor_spread()` 並各自 `emit` 一次——不是
   只對「這次新抓到的」資料，而是全部重放。一個累積了數十筆快照的
   scenario，單純**打開一次詳細頁**就會產生數十筆 `reanchor` 事件，
   跟 exact-contract 家族「這次到底發生了什麼」完全無關，卻佔用同一個
   `_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST=40` 額度池。

**現有的部分緩解，但沒有解決根因**：`_ALWAYS_KEPT_STAGES=("backfill",
"metrics")`（HIVT-03／#154 為了不讓新家族的 metrics 事件被舊家族擠掉
而新增，`main.py:284`）保證兩個家族各自的「彙總結論」都留得住，但
`vendor_fetch`／`payload_parse`／`reanchor` 這些**逐次、高流量**的事件
仍然共用同一個非保留名額池，仍然可能互相擠壓。

### 建議分類（分析，非施工建議的程式碼）

- **應保留（提高訊噪比的關鍵）**：exact-contract 家族自己的
  `vendor_fetch`／`payload_parse`（每個 leg 各一組，數量少、資訊密度高，
  且是本次使用者最關心的新功能）；两个家族的 `metrics`／`backfill`
  彙總結論（現狀已保留）。
- **應 aggregate（本文推導，具體聚合形狀留給施工票決定）**：
  `_backfill_iv` 的逐日 `vendor_fetch`／`payload_parse`——25 天的
  嘗試理論上可以摘要成**一筆**「本次 backfill：X 天有資料、Y 天
  no_data（多半是週末）、Z 天失敗」的彙總事件，而不是 50 筆逐日
  事件；`reanchor` 同理，可以摘要成「N 天 in-grid、M 天 out-of-grid」
  一筆彙總，而不是逐天重放。
- **應降為 info（而非目前的 warning）**：週末／假日的 `no_data`——
  這是**預期行為**，不是需要使用者注意的異常。目前的
  `_vendor_fetch_severity()` 把 `vendor_status == "no_data"` 一律判
  `warning`（`main.py:328-329`），沒有區分「這天剛好是週末」與
  「這天應該有資料但拿不到」，後者才是真正值得 warning 的情況。
- **exact-contract 與 legacy normalized-skew 是否應分 subsystem／
  family**：**建議應該分**——目前兩者共用同一個
  `subsystem="historical_iv"`（`main.py:1346`）與同一個
  `_DIAGNOSTICS_STORAGE_CAP_PER_REQUEST` 額度池，即使 HIVT-03 已經用
  `_ALWAYS_KEPT_STAGES` 部分隔離了彙總結論，逐次事件仍然互相競爭。
  分成兩個 subsystem（例如 `historical_iv.exact_contract` 與
  `historical_iv.normalized_skew`）能讓每個家族各自有獨立的保留額度，
  從根本上解決「新功能的診斷被舊功能的例行噪音淹沒」這個問題，而不是
  持續調高共用上限（HIVT-03 已經把上限從 20 調到 40，這種調法治標
  不治本——只要 `_backfill_iv` 的迴圈規模繼續隨快照數量增長，任何固定
  上限遲早會重新被淹沒）。
- **如何讓使用者最終只看到「真正 root cause」**：本文推導出的優先序是
  「彙總優先於逐次、異常優先於預期內噪音、新功能優先於已穩定的舊功能」。
  一個具體、留給施工票決定細節的方向：`reanchor` 迴圈**不需要在每次
  API 呼叫時都重新診斷全部歷史**——只有「這次 request 有沒有新東西
  發生」（新抓到的快照、新的 backfill 嘗試）才值得產生新的診斷事件；
  對已經看過很多次、狀態沒有變化的舊快照重新跑診斷、重新 emit，
  本質上是在污染訊號而不是提供資訊。

**本節不施工**——上述都是分析與方向性建議，具體的事件 schema 變更、
聚合邏輯、subsystem 拆分需要另開票，交由需求方裁示範圍後施工。

## 12. 需要需求方裁決的問題

1. **Calibration experiment 是否核准實際執行**（§8）——需要花 vendor
   credit 抓真實樣本，且會產生一個新的一次性 CI probe（比照既有
   `tmp-*` 慣例）。本文只設計，不執行。
2. **§8.4 的「多好才算夠好」判準（<3–5 vol pts median error）**——
   本文推導的建議值，需求方可能有不同的容忍度，尤其如果 Historical
   IV Trend 未來要支撐比「相對走勢參考」更精確的用途。
3. **diagnostics subsystem 拆分**（§11）——是否核准把 exact-contract
   與 legacy normalized-skew 拆成兩個 subsystem／獨立額度池，這涉及
   既有 DG-03/04/05/06 系列既有的診斷資料格式，可能需要一併考慮既有
   前端 `InlineDiagnostics` 的呈現方式要不要跟著調整。
4. **`_backfill_iv`／`reanchor` 的聚合／降噪具體形狀**（§11）——本文
   只給方向（聚合而非逐次、no_data 週末降為 info），實際的事件 schema
   設計留給需求方核准範圍後的施工票。
5. **是否要在 v1 就實作本文的 recipe，還是先維持現行「vendor null 就
   缺值」（方案 A）多一段時間**——本文的 Decision Matrix（§9）建議方案
   B，但這是產品優先順序判斷，不是純技術判斷。

## 13. 引用清單

本 repo 既有研究（重用，不重複列出各自的原始引用清單，見各文件自己的
「引用清單」章節）：

- `docs/research/heatmap-valuation-method-selection.md` —— pricing model
  選型、美式溢價量化、OPC/optionlab/QuantLib 比較
- `docs/research/risk-free-rate-for-bs.md` —— Treasury 曲線來源、
  par→continuous 轉換、期限插值
- `docs/research/dividend-yield-source-selection.md` —— 股利資料源、
  q 計算公式、異常值防護
- `docs/research/option-liquidity-filtering.md` —— 報價品質關卡、
  陳舊報價偵測（無套利一致性）
- `docs/research/historical-options-iv-data-sources.md` —— 歷史選擇權
  資料源盤點（ORATS／Market Data App／Theta Data／Polygon 等）

本 repo 程式碼（【一手來源】）：

- `option_chaser/valuation.py:409-586`（BS93／Merton／`implied_vol()`）
- `option_chaser/ratecurve.py`（Treasury 曲線解析）
- `option_chaser/dividends.py`、`option_chaser/data/dividends.py`
  （股利抓取與 q 計算）
- `option_chaser/data/marketdata.py:429-520`（exact-contract 歷史報價
  抓取與解析）
- `option_chaser/ivtrend.py`（HIVT-02/03 統計量純函式）
- `api_app/main.py:260-475,1314-1414`（`/iv-history` 端點、診斷事件）
- `scripts/research_valuation_methods.py`、
  `tests/fixtures/tlt_leaps_real_quotes_2026-07-17.json`（既有研究用
  基礎設施）

本次真實 vendor 驗證（【實測】，需求方 / ChatGPT 執行）：

- commits `4ec23f1`／`410f927`（ORCL exact-contract IV probe，GitHub
  Actions，跑完即刪，比照既有 `tmp-*` 一次性 probe 慣例）
- HIVT-01／#152 既有的 TLT LEAPS 驗證（`3724fca`／`6b085f7`／`9175d7d`／
  `220699d`）

本次外部研究（背景 agent，2026-08-18；**沙箱出口 proxy 對幾乎所有外部
網域回 403**，含控制組 `example.com`／`en.wikipedia.org`／
`web.archive.org`——這是環境級限制，不代表這些站台不存在或連不到，
下方逐條標明實際證據等級）：

一手來源（成功直接讀取，`raw.githubusercontent.com` 可達）：
- `github.com/vollib/py_vollib`（commit `11f2058`）——
  `black_scholes/implied_volatility.py`、
  `black_scholes_merton/implied_volatility.py`
- `github.com/lballabio/QuantLib`（`master`）——
  `ql/instruments/impliedvolatility.cpp`、
  `Examples/EquityOption/EquityOption.cpp`
- `github.com/MarketDataApp/sdk-py`（`main`）——
  `input_types/options.py`、`output_types/options_quotes.py`、
  `resources/options/quotes.py`、`CHANGELOG.md`

索引轉述（WebSearch 摘錄，未能一手開啟原頁，逐條已於內文標明信心度）：
- Cboe VIX White Paper（`cdn.cboe.com`／`vixwhite.pdf`）—— Q(Kᵢ) 中價
  定義、利率插值方法
- OptionMetrics IvyDB Reference Manual（第三方鏡像，非 optionmetrics.com
  本站）—— mid price／zero curve 插值定義
- ORATS 官方部落格／文件（`orats.com`）—— NBBO mid 反解＋無套利平滑曲線
- Interactive Brokers TWS API 文件（`interactivebrokers.com`／
  `interactivebrokers.github.io`）—— tick type 10/11/12/13 四種
  Greeks／IV
- Schwab thinkorswim study library（`toslc.thinkorswim.com`）——
  Implied Volatility study 採 Bjerksund-Stensland 近似
- Market Data App 官方網站（`www.marketdata.app/data/options/`、
  `/education/options/differences-in-iv-greeks/` 等頁面）—— 歷史
  Greeks/IV「coming soon」聲稱、IV/Greeks 為 vendor 自算非交易所提供
- OCC 相關 SEC 申報文件（`sec.gov`）—— TIMS 系統美式選擇權用
  CRR 二項樹

本文推導 / 未能查證（明確標示，不強行湊出正面證據）：
- 業界文件對「歷史 IV 該用觀測當天還是今天的利率曲線」無明文聲明
- Market Data App 歷史列 `iv` 為 null 的確切技術機制無官方文件證實
  （最佳推論見 §3.2）
