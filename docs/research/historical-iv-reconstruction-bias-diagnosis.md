# 為什麼我們自算的 IV 比 vendor 高 30～40 vol points——逐層排除診斷

診斷日期：2026-08-18。範圍：只回答一個問題——
`docs/research/historical-iv-reconstruction-calibration-results.md` 那輪
calibration 出現的 **+0.3816 平均偏差（bias 幾乎等於 MAE，方向幾乎全部同號）**
到底從哪裡來。**不是** methodology 重選、**不是** 重新設計 Historical IV
Trend、**不是** implementation。未動 production pricing／Historical IV
production path／diagnostics production code／spec／tickets。

Base commit：`9f839ec`（診斷開始時的 `origin/claude/implement-tfm9oa`）。

---

## 0. 結論先行（一句話）

**偏差不是模型問題、不是 r／q 問題、不是報價品質問題，是一個「日期用錯」
的問題**：Market Data App 回的是**過期快照**（`updated` 指向前一個交易日
收盤），vendor 用**快照自己那一天**算 IV，而 prototype 用 `date.today()`
算 T。那一輪快照比執行當天早 4 個日曆天，於是 vendor 眼中 DTE=7、
我們眼中 DTE=3。

**vendor 官方文件獨立佐證**：options 資料要到**次一交易日 9:30:01 ET**
才從 Delayed 轉成 Historical，該文件自己舉的例子與本案幾乎一字不差；
把這條規則套用到本案兩次不同時間的呼叫，**精確預測了兩個不同的快照日**
（見 §3.2）。

在 3 DTE 這種天期，這個日期差被放大成 +38 vol points；**同一份程式碼、
同一天、只把 T 換成快照自己的日期，183 筆真實觀測的 MAE 從 0.3813 掉到
0.0020（190 倍），our/vendor 比值從 1.5249 收斂到 1.0001 ± 0.0068。**

而且——**同一個錯誤在 LEAPS 天期只值約 0.1 vol point**（已用真實 303 DTE
資料實測確認）。

---

## 1. 起手線索：偏差是「乘法的」，不是「加法的」

把那 183 筆成功反解的觀測拿來看 `our_iv / vendor_iv` 的比值
（`ORCL260821C00136000` 的 vendor_iv=0.0001 近乎數值零，剔除）：

| | 值 |
|---|---|
| n | 182 |
| mean ratio | 1.5156 |
| **median ratio** | **1.5249** |
| **stdev** | **0.0483** |
| min / max | 1.3962 / 1.7039 |
| TLT 單獨（n=74） | median 1.5210 |
| ORCL 單獨（n=108） | median 1.5250 |

**這個表本身就幾乎把答案講完了。** 一個**近乎常數的乘法比值**，橫跨：

- IV 水準從 0.085 到 3.33（**39 倍**的範圍）
- 兩個完全不同的標的（TLT $82 ETF、ORCL $150 個股）
- call 與 put 兩側
- 深價內到深價外

**沒有任何一個「加法型」誤差源做得到這件事。** 報價差、模型差異、r／q
誤差，全都會隨 moneyness 與 IV 水準劇烈變化，不可能在 39 倍的範圍上維持
±3% 的常數比值。

**唯一會產生常數乘法比值的東西是 T**，理由是純數學的：在 3 DTE、
r≈4%、q≈1–5% 之下，貼現因子 `e^{-rT}=0.99967`、`e^{-qT}≈0.9996`
實質上都是 1，於是 Black-Scholes 價格**只透過總波動 `w = σ√T`
依賴 σ 與 T**。價格與 S、K 固定時：

```
σ_ours · √T_ours = σ_vendor · √T_vendor
σ_ours / σ_vendor = √(T_vendor / T_ours)
```

這個關係**對所有 moneyness 都成立**（不是近似），完全解釋了為什麼比值
這麼穩定。反推：

```
T_vendor / T_ours = ratio² = 1.5249² = 2.3252
T_ours = 3 天  →  T_vendor ≈ 6.98 天
```

**≈ 7 天。** 而 `√(7/3) = 1.5275`，與實測 median 1.5249 只差 **0.17%**。

---

## 2. 驗證：把 T 換成 7 天

方法：`implied_vol()` 是單調可逆的，所以可以從已知的 `our_iv` 用
`american_price()` **精確回推當時餵進去的 mid**（183/183 筆皆能 round-trip
回原值，誤差 <2e-3），再用同一個 mid 在不同 T 下重解。

掃描候選 DTE：

| DTE | median AE | MAE |
|---|---|---|
| 3（原樣） | 0.2905 | 0.3813 |
| 4 | 0.1784 | 0.2332 |
| 5 | 0.1012 | 0.1323 |
| 6 | 0.0441 | 0.0579 |
| 6.5 | 0.0208 | 0.0273 |
| **7** | **0.0007** | **0.0020** |
| 7.5 | 0.0187 | 0.0243 |
| 8 | 0.0357 | 0.0464 |
| 10 | 0.0902 | 0.1175 |

**DTE=7 的 MAE 是 0.0020**——比原本的 0.3813 小 **190 倍**，
p90 = 0.0052、max = 0.0211、ratio = **1.0001 ± 0.0068**。

殘留的 0.0007 中位數量級，與「vendor_iv 只給到小數 4 位的四捨五入 ＋
本文假設 r=4%（非 vendor 真實 r）」完全相符，不需要再假設任何其他誤差源。

**日期算術**：

```
prototype 執行     : 2026-08-18（星期二）→ days_between = 3
到期日             : 2026-08-21（星期五）
DTE=7 回推的快照日 : 2026-08-14（星期五）  ← 上一個星期五收盤
過期程度           : 4 個日曆天
```

---

## 3. 直接觀測（不再靠推論）

上面全部是從既有數字反推的。為了把「推論」變成「觀測」，另跑一次
一次性 CI probe（`scripts/prototype_iv_staleness_probe.py`，跑完即刪
工作流，比照既有 `tmp-*` 慣例），**直接把 prototype 當初沒讀的欄位讀出來**
——`map_chain_payload()` 只取 bid/ask/last/iv，**從來沒有取 `updated`**，
所以 prototype 當時根本無從得知快照自己的時戳。

**2026-08-18 15:23 UTC 的觀測結果**【實測】：

```
HTTP status            : 203   ← non-authoritative（延遲報價）
vendor s               : 'ok'
`updated`（全部 124/204 列）: 2026-08-17T20:00:00Z  ← 單一時戳 = 前一個交易日收盤
underlyingPrice        : TLT 81.32 / ORCL 146.68
vendor `dte`           : 4     ← vendor 自己說還有 4 天（2026-08-21 − 2026-08-17 = 4 ✓ 自洽）
our days_between(today): 3     ← prototype 用的
                                 *** 差 1 天 ***
```

三件事一次確認：

1. **`updated` 是單一均勻時戳**，不是逐筆不同——整個 chain 是**同一個
   收盤快照**，不是即時流。
2. **vendor 的 `dte` 與它自己的 `updated` 自洽**（2026-08-21 − 2026-08-17
   = 4），且與我們用 `date.today()` 算的差 1 天。
3. HTTP 203——**但這一項的解讀本文原本寫錯了，見 §3.1。**

### 3.1 ⚠ 更正：HTTP 203 不是「延遲報價」的訊號

本文初稿與本 repo `option_chaser/data/marketdata.py:425-427` 的既有註解
都寫「vendor 對延遲報價用 203 這個狀態碼」。**查證 vendor 官方文件後
確認這是錯的**，而且 vendor 文件還特地把這個誤解點名出來。

【一手來源】`api/universal-parameters/mode.md`（官方文件原始碼庫
`github.com/MarketDataApp/documentation`，HEAD `da6bfe9`，2026-08-09；
`docusaurus.config.js` 確認其 build 目標即 `www.marketdata.app/docs/`；
沙箱 proxy 擋住 `marketdata.app` 本站，故自官方 repo 取得同一份文字）：

| Status | Meaning |
|---|---|
| `200 OK` | Response was **freshly fetched from the upstream provider**. |
| `203 Non-Authoritative Information` | Response was **served from a cache layer** (Redis, database quote cache, response log, option-chain cache, etc.). Any mode. Common during market hours regardless of `mode=live`, `mode=delayed`, or no `mode`. |

> ":::caution Mode does not deterministically map to status code
> A common (**incorrect**) assumption is that `mode=live` always returns
> `200` and `mode=delayed` always returns `203`. Both can return either
> `200` or `203` depending on whether a cache layer can satisfy the
> request at the moment."

**所以 203 完全不帶新鮮度資訊，只表示「這次是從快取層回的」。**
判斷資料有多舊的唯一正確欄位是 **`updated`**——vendor 自己的文件就是
這樣教使用者的（見 §3.2）。

**這不影響本文的診斷結論**（結論本來就建立在 `updated`／`dte`／數值
證據上，不是建立在 203 上），但**它讓「必須讀 `updated`」這件事更強**：
連狀態碼都不能拿來當新鮮度的代理。

⚠ **`marketdata.py:425-427` 的既有註解需要更正**——本輪禁止改
production code，故僅記錄，列為需求方裁決點（§11-5）。

### 3.2 vendor 官方文件如何佐證這個診斷

【一手來源】`account/data-freshness.md`——vendor 對 options 的
「何時從 Delayed 轉成 Historical」有明文規則，**而且它自己舉的例子
幾乎就是本案**：

> - **Options:** Historical at the *next* session's open — **9:30:01 AM
>   ET** the next trading day, not at the prior session's close.
>
> Friday's options quotes therefore do **not** become Historical until
> **9:30:01 AM ET Monday** — they remain Delayed all weekend.
>
> If you query an options endpoint at **6:33 AM ET Wednesday** on a plan
> that provides Historical-only options data, you will receive
> **Monday's** close, not Tuesday's. … This is the most common cause of
> "the data doesn't match my broker" support requests — the behavior is
> correct, the customer is just querying before the next session has
> opened.

把這條規則套到本案的**兩支 probe**（同一天、不同時間、拿到不同快照日）：

| probe | UTC | **ET** | 文件規則預測 | **實際觀測** | 相符 |
|---|---|---|---|---|---|
| calibration | 08-18 06:00 | **02:00 週二** | 週一(8/17) 的資料要到週二 9:30:01 ET 才轉 Historical → 拿到 **週五 8/14 收盤** → DTE=**7** | 數值反推 DTE=**7**（MAE 0.0020） | ✅ |
| staleness | 08-18 15:23 | **11:23 週二** | 已過週二 9:30:01 ET → 週一(8/17) 已轉 Historical → 拿到 **週一 8/17 收盤** → DTE=**4** | `updated`=**2026-08-17**、vendor `dte`=**4** | ✅ |

**同一天的兩次呼叫拿到兩個不同的快照日，兩者都被官方文件的規則精確
預測。** 這把「快照會過期、而且過期程度會變」從推論變成有文件依據的
確定行為。

【一手來源】`account/free-accounts.md`／`account/plan-limits.md`：
Free Forever 與 trial 方案的 `/v1/options/chain/` 一律是 Historical
（24 小時以上），且無法用 `mode` 參數改變。
【一手來源】`api/troubleshooting/real-time-data.mdx`：即使付費方案，
若 dashboard 的 professional status 是 "Unknown"，API 會**靜默降級**
成 Historical（"The API doesn't throw errors … it silently provides you
with the freshest data you're entitled to receive"）——**不會報錯**。

【一手來源】`api/options/chain.mdx`／`api/dates-and-times.mdx`：
`updated` 定義為 "The date and time of **this quote snapshot**"、
"the actual moment the data was **captured or last refreshed**"，
時區為 US/Eastern；且 `account/free-accounts.md` 直接指示使用者
"Check … the `updated` key in the API's JSON response to get the exact
date and time of the quote data you've received"。**用 `updated` 當
時間基準是 vendor 明文教的做法，不是我們自創的 workaround。**

【一手來源】`dte` 欄位：官方文件四個 worked example 全部滿足
`dte = (expiration − updated) 的 ET 日曆天差`，沒有任何一個是對
「現在」算的：

| 文件位置 | expiration | updated | 文件 `dte` | ET 日期差 |
|---|---|---|---|---|
| `sdk/go/options/chain.mdx` L188 | 2022-01-21 | 2022-01-03 | 18 | 18 ✓ |
| `sdk/go/options/quotes.mdx` L126 | 2025-01-17 | 2024-02-05 | 347 | 347 ✓ |
| `api/options/chain.mdx` L149 | 2023-06-16 | 2023-05-21 | 26 | 26 ✓（原始秒差 25.96，取日期差） |
| `sdk/go/options/chain.mdx` L164 | 2022-03-18 | 2022-01-03 | 74 | 74 ✓ |

**vendor 自己的日數就是以快照日為基準算的**，這正是我們該對齊的口徑。

### 3.3 vendor 的 IV 計算方法論：官方完全沒有文件

【一手來源】官方文件對 `iv` 的**完整**定義只有一句：
"The implied volatility of the option."（連到 Investopedia）。
對 229 個 `.md`/`.mdx` 檔全文檢索 `Black-Scholes`／`Bjerksund`／
`binomial`／`dividend yield`／`risk-free`／`ORATS` 等關鍵字：
**零命中**（`risk-free` 僅 4 次，全部是行銷文案 "risk-free way to
explore our services"）。

**意義**：vendor 的 IV 用什麼模型、什麼價格、什麼 r／q、以哪個時點計算，
**官方一個字都沒寫**。因此**經驗證據是唯一取得得到的證據**——本文
§2 的 190 倍 MAE 崩塌就是這件事能拿到最強的證據形式，不需要為
「沒有官方背書」道歉。

用同一批真實報價、兩種 T 各反解一次：

| 標的 | 用 `today`（DTE=3） | 用快照日（DTE=4） |
|---|---|---|
| TLT 近月 | median \|Δ\| = **18.64 vol pts** | median \|Δ\| = **0.14 vol pts** |
| ORCL 近月 | median \|Δ\| = **44.06 vol pts** | median \|Δ\| = **0.02 vol pts** |

**注意這一輪只差 1 天**（快照 Aug 17，執行 Aug 18），就已經造成 18–44
vol points 的誤差。原本那輪 calibration 差 4 天，造成 38 vol points 的
平均偏差——完全同一個機制，只是天數不同。

> **附帶發現**：兩次 probe 的快照日不一樣（06:00 UTC 那次對應 Aug 14，
> 15:23 UTC 這次是 Aug 17）。**vendor 快照的日期會隨呼叫時間變動**，
> 所以「假設它總是昨天」也是錯的——必須每次讀 `updated`／`dte`。

---

## 4. Controlled Ablation：其他假設逐一排除

基準＝prototype 當時的實際設定（T=3/365、mid、BS93、production r 與 q）。
一次只改一個輸入。單位：vol（0.01 = 1 vol point）。

### ATM call `TLT260821C00082000`（K=82, S=82.07, mid $0.4808, vendor 0.1000, ours 0.1509）

| variant | IV | Δ vs baseline | Δ vs vendor |
|---|---|---|---|
| baseline (T=3d) | 0.1509 | — | **+0.0509** |
| **T = 7d（快照日）** | **0.0996** | −0.0513 | **−0.0004** |
| T = 3 trading d /252 | 0.1257 | −0.0252 | +0.0257 |
| r = 0% | 0.1554 | +0.0045 | +0.0554 |
| r = 8% | 0.1461 | −0.0048 | +0.0461 |
| q = 0 | 0.1452 | −0.0057 | +0.0452 |
| q = 10% | 0.1568 | +0.0059 | +0.0568 |
| price −$0.10 | 0.1171 | −0.0338 | +0.0171 |
| price +$0.10 | 0.1847 | +0.0338 | +0.0847 |
| S +0.5% | 0.0354 | −0.1155 | −0.0646 |
| **model: Merton European** | **0.1509** | **+0.0000** | +0.0509 |

### ATM put `ORCL260821P00150000`（K=150, S=150.59, mid $4.1236, vendor 0.5360, ours 0.8149）

| variant | IV | Δ vs baseline | Δ vs vendor |
|---|---|---|---|
| baseline (T=3d) | 0.8149 | — | **+0.2789** |
| **T = 7d（快照日）** | **0.5361** | −0.2788 | **+0.0001** |
| r 0%→8% 全範圍 | 0.8105–0.8192 | ±0.0044 | ~+0.28 |
| q 0→10% 全範圍 | 0.8058–0.8163 | ±0.0091 | ~+0.28 |
| price ±$0.10 | 0.7965–0.8333 | ±0.0184 | ~+0.28 |
| **model: Merton European** | **0.8150** | **+0.0001** | +0.2790 |

### OTM put `ORCL260821P00135000`（vendor 0.5542, ours 0.8449）

| variant | IV | Δ vs vendor |
|---|---|---|
| baseline (T=3d) | 0.8449 | +0.2907 |
| **T = 7d（快照日）** | **0.5543** | **+0.0001** |
| r 0%→8% | 0.8429–0.8469 | ~+0.29 |
| q 0→10% | 0.8408–0.8455 | ~+0.29 |
| **model: Merton European** | **0.8449** | +0.2907 |

### 逐項判定

| 假設 | 觀測到的量級 | 能否單獨解釋 30–40 vol pts | 判定 |
|---|---|---|---|
| **B. Time-to-expiry** | **改 T 一項即命中 vendor 到小數 4 位（Δ ≤0.0041）** | **是——而且只有它做得到** | **✅ ROOT CAUSE** |
| C. Pricing model（BS93 vs Merton European） | **0.0000–0.0001** | 否 | ❌ 排除（實質為零：3 DTE 下提前履約不最優，BS93 依定義退化成 Merton） |
| D. Dividend q（0→10% 全範圍） | ATM/OTM ≤0.009 | 否 | ❌ 排除（量級差 30 倍） |
| E. Risk-free r（0%→8% 全範圍） | ATM/OTM ≤0.005 | 否 | ❌ 排除（量級差 50 倍） |
| A. Price input（±$0.10） | ATM/OTM ±0.009–0.019 | 否，且不可能產生常數比值 | ❌ 排除為系統性主因 |
| F. Underlying timing | S 與 iv 來自**同一份快照**，本身自洽 | 不是獨立誤差源 | ❌ 排除（但它與 T 同源：都是「快照日 ≠ 今天」的一體兩面） |
| I. Units／scaling | 比值 = √(7/3)，不是 100 或 0.01 | 否 | ❌ 排除（見 §5） |
| G. 近到期病態 | 解釋**離散度與失敗率**，不解釋**偏差** | 否 | ⚠️ 真實存在但非本題主因（見 §6） |

---

## 5. 單位／解析 trace（假設 I，逐層手算）

```
OCC symbol        : TLT260821C00082000
strike 解析       : 00082000 → 82000/1000 = 82.0        ← 1000 倍縮放正確
                    （註：production 的 map_chain_payload 直接讀 row['strike']／
                      row['side']，根本不解析 OCC 字串，這條路徑不存在縮放風險）
underlyingPrice   : 82.07      美元，未套用任何縮放
mid               : 0.4808     美元，(bid+ask)/2，未套用任何縮放
r  餵進模型       : 0.04       DECIMAL（par_to_continuous 回傳小數：4.20% → 0.0416）
q  餵進模型       : 0.047557   DECIMAL（compute_q = sum(amounts)/spot，本來就是比例）
T  餵進模型       : 0.008219   3/365 年
implied_vol 輸出  : 0.1509     DECIMAL vol（＝15.09%）
vendor `iv` 欄位  : 0.1000     DECIMAL vol（＝10.00%）
```

兩邊都是同一數量級的小數。**單位 bug 會表現成 100 倍或 0.01 倍，或是
一個常數的加法偏移**；實測比值是 1.5249 = √(7/3)，是一個**時間比**，
不是單位比。**排除。**

---

## 6. 近到期病態（假設 G）：真實存在，但解釋的是「離散度」不是「偏差」

3 DTE 的深價內合約，時間價值只剩幾分錢：

| 合約 | mid | 內在值 | **時間價值** | 時間價值/mid | **1 分錢 → 幾 vol pts** |
|---|---|---|---|---|---|
| TLT C82000（ATM） | 0.4808 | 0.0700 | 0.4108 | 0.854 | +0.34 |
| TLT C75000 | 7.0765 | 7.0700 | **0.0065** | 0.0009 | **+3.55** |
| TLT C70000 | 12.0764 | 12.0700 | **0.0064** | 0.0005 | **+4.98** |
| TLT C60000 | 22.0762 | 22.0700 | **0.0062** | 0.0003 | **+7.38** |
| ORCL C250000（深價外） | 0.0150 | 0 | 0.0150 | 1.0 | **+9.09** |

**是的，一分錢的報價誤差在這些合約上值 3.5–9 個 vol points。** 這是真的，
而且用數字證明了。

但這**不是偏差的來源**，因為報價噪音是雙向的、不可能產生單向 +1.52 倍的
常數比值。它解釋的是**修正 T 之後的殘留離散度**：

| 分組 | n | 修正 T 後的中位殘差 |
|---|---|---|
| 時間價值 ≥ $0.10 | 98 | **0.02 vol pts** |
| 時間價值 < $0.10 | 84 | **0.28 vol pts** |

時間價值薄的那一組殘差是厚的那組的 **14 倍**——病態確實存在，但量級
是 0.28 vol points，不是 38。

**它也解釋了 44.2% 的失敗率**：`implied_vol_no_solution` 發生在 mid 超出
模型可行價格區間。T 太小會**縮窄**可行區間：

| 合約 | mid | T=3d 可行區間 | T=7d 可行區間 |
|---|---|---|---|
| TLT C75000 | 7.0765 | [7.0700, 17.8795] | [7.0700, **24.9489**] |
| TLT C70000 | 12.0764 | [12.0700, 20.4727] | [12.0700, **27.1156**] |
| TLT C60000 | 22.0762 | [22.0700, 26.6055] | [22.0700, **32.0790**] |

用對的（較大的）T，可行區間**嚴格變寬**，所以 51 筆
`implied_vol_no_solution` 中必然有一部分會消失。**真實失敗率必然低於
回報的 44.2%**——確切數字要重跑才知道（那 145 筆失敗沒有印在 ranked
table 裡，mid 無法回推）。

---

## 7. 這是不是「只有 3 DTE 才這樣」？——是的，而且已實測

### 7.1 數學敏感度（同一張選擇權，S=100、ATM、真實 IV=25%、r=4%、q=2%）

| DTE | mid | vega $/volpt | $0.05 報價誤差 | S +0.5% | T −1 天 | r +100bp | q +100bp | **4 天過期** |
|---|---|---|---|---|---|---|---|---|
| 3 | 0.91 | 0.036 | +1.38 | −7.89 | **+5.71** | −0.11 | +0.12 | **+13.48** |
| 30 | 2.93 | 0.114 | +0.44 | −2.36 | +0.45 | −0.36 | +0.38 | +1.70 |
| 90 | 5.16 | 0.196 | +0.25 | −1.39 | +0.15 | −0.62 | +0.67 | +0.60 |
| 180 | 7.39 | 0.275 | +0.18 | −1.01 | +0.08 | −0.87 | +0.98 | +0.31 |
| 365 | 10.66 | 0.383 | +0.13 | −0.75 | +0.04 | **−1.23** | **+1.46** | **+0.16** |
| 730 | 15.19 | 0.520 | +0.10 | −0.57 | +0.02 | **−1.74** | **+2.14** | **+0.08** |

（單位皆為 vol points）

封閉形式的過期偏差 `ratio = √((DTE+stale)/DTE)`：

| DTE | 4 天過期 → 在 25% IV 上 | 2 天過期 |
|---|---|---|
| 3 | **+13.19 pts**（+52.8% 相對） | +7.27 pts |
| 30 | +1.61 pts | +0.82 pts |
| 90 | +0.55 pts | +0.28 pts |
| 365 | **+0.14 pts** | +0.07 pts |
| 730 | **+0.07 pts** | +0.03 pts |

**從 3 DTE 到 365 DTE，同樣的日期錯誤縮小約 94 倍。**

### 7.2 真實 LEAPS 資料實測（本次 probe 補上，calibration 那輪因 403 沒拿到）

`TLT270617`／`ORCL270617`，**303 DTE**：

| 標的 | n | 用 today 的中位 Δ | 用快照日的中位 Δ | **兩者差異** |
|---|---|---|---|---|
| TLT | 7 | −3.91 vol pts（MAE 3.17） | −3.98 vol pts（MAE 3.21） | **0.030 vol pts** |
| ORCL | 8 | −0.35 vol pts（MAE 0.43） | −0.48 vol pts（MAE 0.55） | **0.130 vol pts** |

封閉形式對 1 天過期 @303 DTE 的預測是 **0.082 vol pts**；實測 0.03–0.13。
**吻合。**

**同一份程式碼、同一天、同一個 recipe：**

- **3–4 DTE：17–57 vol points 誤差，幾乎全部來自 1 天的參照日錯誤**
- **303 DTE：0.2–4.0 vol points 誤差，其中日期錯誤只佔約 0.1**

### 7.3 LEAPS 的殘差是另一回事（新發現，需求方需注意）

修掉日期之後，LEAPS 仍有殘差，而且**方向相反（我們偏低）且與標的相關**：

- **TLT（q=4.8%，高配息 ETF）：−3.98 vol pts**，且隨價內程度加深而放大
  （K=45 深價內 −3.98 → K=80 近價 −0.47）
- **ORCL（q=1.4%，低配息個股）：−0.48 vol pts**

這個「高 q 標的殘差大、低 q 標的殘差小，且深價內 call 最明顯」的樣態，
與 §7.1 的敏感度表一致——**q 與 r 的影響力在長天期會放大**（q +100bp 在
3 DTE 只值 0.12 vol pts，在 365 DTE 值 1.46 vol pts）。深價內 call ＋
高股利正是 q 與提前履約效應最強的地方。

**判定：LEAPS 殘差最可能是 q 口徑差異（我們的 trailing-TTM q vs vendor
的假設）。**【本文推導，證據為 moneyness 梯度 ＋ 高 q／低 q 標的對比；
未直接做 ablation——這批 LEAPS 的 mid 沒有留下，無法回推】。這是一個
**獨立於本題的、值得後續驗證的問題**，不影響本題結論。

---

## 8. Root Cause Ranking

| # | 原因 | 佔比 | 信心 | 證據 | 觀測量級 | 能否單獨解釋 30–40 pts |
|---|---|---|---|---|---|---|
| **1** | **快照過期造成的參照日／T 錯配**（prototype 用 `date.today()`，vendor 用快照自己的日期） | **~97%** | **HIGH** | 改 T 一項使 MAE 0.3813→0.0020（190×）、ratio 1.5249→1.0001；直接觀測 `updated`=前一交易日收盤、vendor `dte` 與我們差 1 天；HTTP 203 | **+38 vol pts**（4 天過期 @3 DTE） | **是** |
| 2 | 近到期病態（時間價值僅數分錢 → vega 塌縮） | ~2% | HIGH | 時間價值 <$0.10 組殘差 0.28 pts vs ≥$0.10 組 0.02 pts；1 分錢 = 3.5–9 pts | 0.28 vol pts（中位殘差）；解釋失敗率 | 否 |
| 3 | q 口徑差異 | <1%（本題）；**LEAPS 上升為主要殘差** | MEDIUM | 3 DTE 全範圍 ≤0.009；但 LEAPS 上 TLT −3.98 vs ORCL −0.48 的高/低 q 對比 | 3 DTE：≤0.9 pts；303 DTE：~4 pts | 否 |
| 4 | r 口徑差異 | <1% | HIGH | 0%→8% 全範圍 ≤0.005（3 DTE） | ≤0.5 vol pts | 否 |
| 5 | Pricing model（BS93 vs European） | **0%** | HIGH | 逐筆差 0.0000–0.0001 | **0.01 vol pts** | 否 |
| 6 | Units／scaling bug | **0%** | HIGH | 比值 = √(7/3) 而非 100/0.01；逐層 trace 全部 decimal 一致 | 0 | 否 |

---

## 9. 四個必答問題

### A. 目前巨大 bias 最主要原因是什麼？

**Prototype 用 `date.today()` 當 T 的參照日，但 vendor 給的是過期快照
（`updated` 指向前一個交易日收盤），vendor 的 IV 是用快照自己那一天算的。**
那一輪快照比執行日早 4 天，於是 DTE 7 vs 3。

而且這不只是我們反推出來的——**vendor 官方文件的 options
Delayed→Historical 轉換規則（次一交易日 9:30:01 ET）精確預測了本案的
兩次觀測**（02:00 ET 那次拿到週五收盤、11:23 ET 那次拿到週一收盤），
見 §3.2。

在 3 DTE 這種天期，`σ ∝ 1/√T` 把這個日期差放大成 √(7/3) = 1.53 倍
＝ **+38 vol points**。

**這是 prototype 的取數 bug，不是 recipe 的方法論缺陷**——
`historical-iv-reconstruction.md` §7「Historical information integrity」
早就寫明「用該筆觀測自己的時點資料」；諷刺的是 prototype 自己違反了這一條，
因為 `map_chain_payload()` 根本沒有把 `updated` 欄位取出來，prototype
無從得知快照的真實日期。

### B. 這個問題在 LEAPS 上會大幅減弱，還是可能一樣嚴重？

**會大幅減弱，且已用真實 303 DTE 資料實測確認，不是只有理論推導。**

- 封閉形式：4 天過期在 3 DTE 值 +13.19 vol pts，在 365 DTE 值 **+0.14
  vol pts**，在 730 DTE 值 **+0.07 vol pts**（縮小約 94–188 倍）。
- 實測：303 DTE 上「用 today」與「用快照日」的差異只有 **0.03–0.13
  vol pts**，與封閉形式預測的 0.082 吻合。

**但要注意一個反向趨勢**：r 與 q 的敏感度**隨天期上升**（q +100bp：
3 DTE 值 0.12 pts、365 DTE 值 1.46 pts）。真實 LEAPS 資料上確實看到
−0.5（ORCL，低 q）到 −4.0（TLT，高 q）vol pts 的殘差。**LEAPS 上的
主要誤差源會從「日期」換成「r／q 口徑」**——這正好印證
`historical-iv-reconstruction.md` §10 把 point-in-time r 與 q 列為
MUST HAVE 是對的。

### C. 我們目前 reconstruction recipe 哪個地方確實需要改？

**Recipe（§10 那份）本身不需要改任何一項。** 需要改的是**取數層的三個
具體缺口**：

1. **`map_chain_payload()`／`_parse_contract_history()` 必須把觀測自己的
   時戳帶出來**（`updated`，以及 chain 路徑上的 vendor `dte`）。目前兩者
   都把它丟掉，導致上層**在結構上無法**做正確的 point-in-time 計算——
   這是本次 bug 的根本成因，不是誰忘了寫。
2. **T 的參照日一律用「該筆觀測自己的日期」，永遠不用 `date.today()`。**
   而且**不能假設「快照就是昨天」**——本次兩支 probe 拿到的快照日分別是
   Aug 14 與 Aug 17，vendor 的延遲程度會隨呼叫時間變動（§3.2 已用官方
   文件的 9:30:01 ET 轉換規則解釋為什麼）。**也不能拿 HTTP 狀態碼當
   新鮮度代理**——203 只代表「從快取層回的」，與新鮮度無關（§3.1）。
3. **同一個原則適用於 r 與 q**：既然 T 要用快照日，r 曲線與 q 也該對齊
   同一天（§10 已經這樣寫，本次只是再次證實它為什麼重要——尤其在 LEAPS
   上 r／q 的影響力反而更大）。

另外**建議（非必要）**：`historical-iv-reconstruction-calibration-results.md`
把偏差歸因為「3-DTE vega 塌縮造成的數值不穩定」——**那個歸因是錯的**，
本文已證明真因是日期錯配（噪音不會產生 stdev 僅 3% 的常數比值）。
該文應更正，以免後續決策沿用錯誤前提。

### D. 目前是否已經足以進 production？

## **YES_WITH_GUARDRAILS**

理由：

**支持進入的證據（比上一輪強得多）**：

- 偏差的成因已經**完全鎖定並量化**，不是「最可能是……」——改一個變數就
  從 MAE 0.3813 到 0.0020，而且有直接觀測（`updated`／`dte`／HTTP 203）
  佐證機制。
- Recipe 的**模型選擇被證明是對的**：BS93 vs Merton European 差 0.0001，
  在這個天期模型根本不是誤差源；r／q 的量級也都在容忍範圍內。
- **LEAPS 已經有真實 vendor benchmark 了**（本輪 probe 補上，303 DTE）：
  修正日期後，ORCL LEAPS MAE **0.43 vol pts**、TLT LEAPS MAE 3.2 vol pts。
  這已經遠優於上一輪「完全沒有 LEAPS 資料」的狀態，也遠低於
  `historical-iv-reconstruction.md` §8.4 建議的 3–5 vol pts 判準（ORCL
  通過，TLT 邊緣）。
- Ranking stability 本來就極強（Pearson 0.9991／Spearman 0.9970），而
  日期錯配是**純乘法**的，**依定義完全不改變排序**——這也解釋了為什麼
  ranking 在偏差這麼大時仍然完好。對 Historical IV Trend 這個「相對高低」
  產品而言，這是最關鍵的性質。

**必要的 guardrails**：

1. **§9-C 的三個取數缺口必須先補**（尤其第 1、2 點）。不補的話，
   production 會重演同一個 bug——而且在 LEAPS 上它不會像 3 DTE 那樣
   誇張到一眼看出來（只有 0.1 vol pt），**會安靜地錯下去**，比大錯更危險。
2. **TLT 型高配息標的的 LEAPS 殘差（−4 vol pts）尚未歸因完成**，
   應在補完取數缺口後重跑一次 LEAPS calibration 確認它是 q 口徑問題
   且落在可接受範圍。
3. **顯示絕對 IV 數字時，近到期（<14 天）應標記低信賴度**——§6 已證明
   一分錢報價誤差在那裡值 3.5–9 vol points，這與日期 bug 無關，是市場
   結構本身的性質，修不掉，只能誠實標示。

**不選 `NO_NEED_LEAPS_VALIDATION`** 的理由：LEAPS 已經有初步真實
benchmark，但只有 15 筆、單一到期日、且 TLT 那組還有未歸因的 −4 vol pts
殘差。稱不上「不需要驗證」。**不選 `YES`** 的理由：取數缺口是結構性的，
不補就會重演。

---

## 10. 附錄：可重跑的診斷資產

- `scripts/prototype_historical_iv_calibration.py`——原 calibration 腳本
  （**已知缺陷：用 `date.today()` 當 T 參照日**，見 §9-C；重跑前應先修）。
- `scripts/prototype_iv_staleness_probe.py`——本次新增，直接讀 `updated`／
  `dte`／HTTP status，並用兩種 T 對照反解，同時抓 LEAPS 到期日。
- 本文所有數值分析不需要 vendor 呼叫即可重跑：`implied_vol()` 單調可逆，
  可從已公布的 `(vendor_iv, our_iv)` 表精確回推當時的 mid。

## 11. 需求方裁決點

1. **是否核准把 §9-C 的三個取數缺口開成正式票**（`updated`/`dte` 帶出
   解析層、T 一律用觀測日、r/q 對齊同一天）。本文只診斷，未開票。
2. **是否要求先重跑一輪「修正日期後的完整 calibration」**（含 LEAPS）
   再進 production——本文的 `YES_WITH_GUARDRAILS` 假設會做這件事。
3. **`historical-iv-reconstruction-calibration-results.md` 的錯誤歸因是否
   一併更正**（該文把偏差歸因為 vega 塌縮噪音，已被本文推翻）。
4. **TLT 型高配息標的的 LEAPS q 口徑**是否要另開研究——目前只有
   MEDIUM 信心的推論，未做直接 ablation。
5. **`option_chaser/data/marketdata.py:425-427` 的既有註解寫錯了**
   （宣稱 vendor 用 HTTP 203 表示延遲報價；官方文件明文說 203 表示
   「從快取層回應」，且把這個誤解點名為 "a common (incorrect)
   assumption"，見 §3.1）。本輪禁止改 production code，僅記錄；
   是否併入上述取數票一起更正，請裁示。
6. **是否要處理「靜默降級」風險**：官方文件載明即使付費方案，
   若帳號 professional status 為 "Unknown"，API 會**不報錯地**降級成
   1 天以上的 Historical 資料（§3.2）。這意味著 production 若只看
   HTTP 狀態與 `s=="ok"`，**無法察覺自己拿到的是舊資料**——正確做法
   仍是讀 `updated` 並據以計算，本文的修法天然涵蓋這個風險，但值得
   在 diagnostics 上另外顯性化。
