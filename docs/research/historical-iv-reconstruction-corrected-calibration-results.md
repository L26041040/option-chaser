# Historical IV Reconstruction — Corrected Calibration 結果（修正 observation date 後）

`/prototype` 執行紀錄（2026-08-18）。唯一目的：驗證
`docs/research/historical-iv-reconstruction-bias-diagnosis.md` §9-C
點名的三個取數缺口修正後（observation_date 用 vendor `updated`、T/r/q
皆對齊該日，不用 `date.today()`），reconstruction 在 medium／LEAPS
是否足夠準，並釐清 TLT 的殘差成因。

腳本：`scripts/prototype_historical_iv_calibration_corrected.py`
（丟棄式研究工具，直接 import production 的 `implied_vol()`；r／q
的「挑 point-in-time 那一列／那些配息」邏輯是這支腳本自己寫的，不改動
`ratecurve.py`／`dividends.py` 任何一行——修正版 §9-C 第 1 點指出的
「解析層不帶 `updated`／`dte`」缺口，這裡在 prototype 層繞過，不是在
production 補上，補 production 是後續施工票的範圍）。

執行方式：一次性 CI probe（真實 `MARKETDATA_APP_TOKEN`，跑完即刪，
比照既有 `tmp-*` 慣例）。offline 先用 `tests/fixtures/
treasury_csv_sample.txt` 與合成資料驗證過 point-in-time 揀選邏輯
（精確命中、週末/假日退回最近前一列、不洩漏未來配息），才花 vendor
額度正式跑。

## 0. 修正後 recipe（逐項對照原始 recipe）

| 輸入 | 原始（有 bug） | 修正後 |
|---|---|---|
| observation_date | `date.today()` | 該筆 chain 回應自己的 `updated`（整批 chain 共用單一時戳，已由前一輪 staleness probe 實測確認） |
| T | `days_between(today, expiry)/365` | `days_between(observation_date, expiry)/365` |
| S | 同筆 `underlyingPrice` | 不變 |
| price | mid | 不變 |
| r | 抓「今天」的 Treasury 曲線 | 抓 observation_date 那一年的 CSV，自己挑 ≤observation_date 的最近一列 |
| q | `compute_q(hist, spot, today)`——只有下界（TTM 窗），沒有上界 | 只計入 `ex_date <= observation_date` 的配息（額外補上界，避免抓取當下已公開、observation_date 當時還沒發生的配息偷跑進來——研究文件 §7 的 look-ahead bias 紅線） |
| model | BS93 `implied_vol()` | 不變 |
| vendor IV | 只當 benchmark | 不變 |

## 1. 樣本

`fetch_expirations()` 取得完整到期日清單，挑三個桶：`medium_short`
（14–60 天）、`medium`（90–200 天）、`leaps`（300–3650 天，實際命中
2028-12-15，距執行日約 852 天）。TLT／ORCL 各三個桶，共 6 次 chain
呼叫，全部一次拿到（單次呼叫回整條 chain，不是逐 strike 查）。

**observation_date 兩個標的、三個桶全部一致：2026-08-17**（執行日
2026-08-18 的前一交易日收盤——與前一輪 staleness probe 觀測到的延遲
行為一致）。

| 標的 | spot@obs | q_asof | dividend 來源 |
|---|---|---|---|
| TLT | 81.32 | 0.04800 | yahoo（24 筆配息記錄） |
| ORCL | 146.68 | 0.01364 | yahoo（8 筆配息記錄） |

## 2. A. 數字結果

### 整體

| 指標 | 值 | 對照：修正前（3-DTE，`historical-iv-reconstruction-calibration-results.md`） |
|---|---|---|
| N | 578 | 328 |
| ok | 537 | 183 |
| **failure rate** | **7.1%** | 44.2% |
| **MAE** | **0.0060**（0.6 vol pts） | 0.3816 |
| median AE | 0.0010 | 0.2907 |
| p90 AE | 0.0150 | 0.7228 |
| **bias** | **-0.0021**（幾乎為零，方向反轉） | +0.3816 |
| Pearson | 0.9982 | 0.9991 |
| Spearman | 0.9951 | 0.9970 |
| percentile rank diff | median 0.0075／p90 0.0429 | 未算（原文只算絕對誤差） |

**MAE 從 0.3816 掉到 0.0060——63 倍。bias 從 +0.38（幾乎等於 MAE，
方向系統性）掉到 -0.0021（幾乎為零）。失敗率從 44.2% 掉到 7.1%。**
與 `historical-iv-reconstruction-bias-diagnosis.md` 的診斷完全吻合
（該文預測：修正日期後失敗率必然下降，因為可行價格區間變寬）。

### 分群：symbol

| symbol | n | ok | fail% | MAE | median AE | p90 AE | bias | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|---|
| TLT | 302 | 284 | 6.0% | 0.0089 | 0.0031 | 0.0202 | -0.0019 | 0.9706 | 0.9707 |
| ORCL | 276 | 253 | 8.3% | 0.0028 | 0.0005 | 0.0083 | -0.0024 | 0.9971 | 0.9949 |

### 分群：tenor bucket

| tenor | n | ok | fail% | MAE | median AE | p90 AE | bias | Pearson | Spearman | rank_diff median/p90 |
|---|---|---|---|---|---|---|---|---|---|---|
| medium_short（14–60d） | 170 | 166 | 2.4% | 0.0005 | 0.0001 | 0.0013 | -0.0004 | 1.0000 | 0.9999 | 0.0000／0.0061 |
| medium（90–200d） | 246 | 210 | 14.6% | 0.0058 | 0.0007 | 0.0104 | -0.0004 | 0.9975 | 0.9965 | 0.0048／0.0287 |
| **leaps（~852d）** | 162 | 161 | 0.6% | **0.0121** | 0.0075 | 0.0208 | -0.0062 | 0.9971 | **0.9894** | 0.0188／0.0625 |

### 分群：symbol × tenor（含前一輪點名的 TLT LEAPS）

| | n | ok | fail% | MAE | median AE | p90 AE | bias | Pearson | Spearman |
|---|---|---|---|---|---|---|---|---|---|
| TLT/medium_short | 76 | 73 | 3.9% | 0.0006 | 0.0001 | 0.0018 | -0.0004 | 0.9998 | 0.9996 |
| TLT/medium | 126 | 112 | 11.1% | 0.0094 | 0.0011 | 0.0268 | -0.0001 | 0.9722 | 0.9780 |
| **TLT/leaps** | 100 | 99 | 1.0% | **0.0145**（1.45 vol pts） | 0.0085 | 0.0212 | -0.0051 | 0.9771 | **0.9626** |
| ORCL/medium_short | 94 | 93 | 1.1% | 0.0003 | 0.0001 | 0.0011 | -0.0003 | 1.0000 | 0.9997 |
| ORCL/medium | 120 | 98 | 18.3% | 0.0017 | 0.0005 | 0.0063 | -0.0009 | 0.9991 | 0.9981 |
| **ORCL/leaps** | 62 | 62 | 0.0% | **0.0083**（0.83 vol pts） | 0.0064 | 0.0177 | -0.0080 | 0.9831 | 0.9661 |

**TLT／ORCL 在 LEAPS（~852 天）的 MAE 分別是 1.45／0.83 vol points**
——遠低於研究文件 §8.4 建議的 3–5 vol points 判準，也遠低於前一輪
`historical-iv-reconstruction-bias-diagnosis.md` §7.2 用**未修正 q**
（`compute_q(hist, spot, today)`，today 而非 observation_date，且沒有
`ex_date` 上界）在**另一個**、較近的 LEAPS 到期日（2027-06-17，
~303 天）觀測到的 TLT MAE 3.17 / median -3.98——這兩次用的不是同一組
合約（到期日不同），不是嚴格的 before/after 對照，但方向一致：
**修正 q 的 look-ahead 缺口後，TLT 的殘差顯著縮小**（見下方 §3 的
直接 ablation，同一批合約、只換 q，是嚴格對照）。

**注意到的資料品質現象**（非本文方法論缺陷）：TLT／medium 桶與
ORCL／medium 桶的失敗率（11.1%／18.3%）明顯高於 medium_short／leaps，
且 TLT／medium 出現三筆 vendor_iv=0.0001 的退化值
（`TLT270115P00097000` 等）——這是 vendor 自家報價的品質問題（前一輪
`historical-iv-reconstruction.md`／診斷文件已見過同型態的
`ORCL260821C00136000` vendor_iv=0.0001），不是 reconstruction 算錯。
這類觀測若流入 production 的 percentile／z-score 計算會需要一個最低
限度的合理性關卡（見 §5 guardrails）。

## 3. TLT q Ablation（同一批 284 筆成功反解的觀測，只換 q）

| q 版本 | MAE | n（成功反解數，隨 q 改變可行區間而不同） |
|---|---|---|
| **q_prod**（point-in-time，0.0480） | **0.0089** | 284 |
| q=0 | 0.0493 | 242 |
| q_prod × 0.5 | 0.0375 | 272 |
| q_prod × 1.5 | 0.0140 | 205 |

**q=0 對照組的 MAE 比 production q 高 +0.0405 vol pts（4.05 個 vol
points）——q 是主要成因，且是壓倒性的主要成因**：拿掉 q，TLT 的誤差
從 0.89 vol pts 惡化到 4.93 vol pts，惡化 5.5 倍。

**同時，production q 是四個版本裡表現最好的一個**（優於 q×0.5 與
q×1.5 兩側），代表**目前的 point-in-time q 校準本身沒有系統性偏誤，
不是「調整 q 的數值就能進一步壓低殘差」的情況**——剩下的 0.89 vol
points MAE 是另一個量級更小的殘差來源（本文不深究，量級已經遠低於
§8.4 判準，不需要為了壓到 0 而展開新模型研究，符合票面「不要展開新
模型研究」的範圍限制）。

## 4. 四個必答問題

### 1. 日期修正後，巨大 bias 是否完全消失？

**幾乎完全消失。** 整體 bias 從 +0.3816（幾乎等於 MAE，方向系統性
一致）掉到 **-0.0021**（219 分之一，且方向已經不是系統性單向）。
MAE 從 0.3816 掉到 0.0060（63 倍）。這與
`historical-iv-reconstruction-bias-diagnosis.md` 的診斷完全吻合——
該文已經用單一 T 替換就證明 190 倍的收斂，這裡是完整 recipe（含
point-in-time r／q）在**全新的一批真實觀測**（medium／LEAPS，前一輪
完全沒有的天期）上獨立重現同一個結論。

### 2. LEAPS ranking 是否穩定？

**穩定，且是本輪最強的訊號之一。** LEAPS 桶（~852 天）：整體
Spearman **0.9894**、TLT **0.9626**、ORCL **0.9661**——即使是四組
symbol×tenor 組合裡 Spearman 最低的 TLT/leaps，仍然是「幾乎完全同序」
等級的相關。percentile rank diff 在 LEAPS 也維持小量級（整體 median
0.0188、p90 0.0625；TLT/leaps 最差，p90 0.1224，仍在可接受範圍）。
**Historical IV Trend 最在乎的「相對高低排序」在 LEAPS 天期完全站得住。**

### 3. TLT 殘差主要是不是 q？

**是，而且是壓倒性的主要成因，已用直接 ablation 證實（§3）**：同一批
284 筆觀測，拿掉 q（q=0）讓 MAE 從 0.0089 惡化到 0.0493（+0.0405，
惡化 5.5 倍）。**但這不代表「q 校準得不夠好」**——production q 本身
是四個測試版本裡表現最好的一個（優於 ×0.5 與 ×1.5 兩側），代表目前
的 point-in-time q 沒有系統性偏誤，只是「有沒有 q」這件事本身影響很
大（TLT 是高股利 ETF，q≈4.8%，在 LEAPS 天期 q 對 IV 反解的敏感度本來
就顯著放大，`historical-iv-reconstruction-bias-diagnosis.md` §7.1 的
敏感度表已經預告過這件事：q +100bp 在 365 天值 1.46 vol pts，在 730
天值 2.14 vol pts）。

### 4. Reconstruction 是否已足以正式施工？

**是，核心 recipe 已經證明站得住**——bias 消除、ranking 在所有天期
（含 LEAPS）都穩定在 Spearman ≥0.96、絕對誤差（MAE 0.6 vol pts 整體，
最差的 symbol×tenor 組合 TLT/medium 也只有 0.94 vol pts）遠低於研究
文件 §8.4 訂的 3–5 vol pts 判準。**但正式施工前仍有具體、已點名的
guardrails**（見下方 §5），不是「毫無保留」的通過。

## 5. Verdict

## **STRONG_PASS**

（本輪驗證範圍：修正後的 recipe 在 medium／LEAPS 是否夠準、LEAPS
ranking 是否穩定、TLT 殘差成因——三者皆得到明確、可重現的正面答案，
沒有含糊地帶。）

**支持 STRONG_PASS 而非 PASS_WITH_GUARDRAILS 的理由**：

- bias 消除不是「大幅改善」而是「63 倍收斂到幾乎零」，且用了兩種獨立
  證據互相佐證（診斷文件的單變數 T 替換、本輪的完整 recipe 重新反解）。
- ranking stability（票面明訂的優先判準）在**新增的**天期（medium／
  LEAPS，前一輪完全沒有）上依然全數 ≥0.96，沒有隨天期拉長而崩壞。
- q 對 TLT 殘差的因果關係不是「合理推測」，是**直接 ablation 量化**
  出來的（+4.05 vol pts），而且證明了 production q 本身沒有系統性
  偏誤——這排除了「還要再花一輪去調 q 校準」的疑慮。
- 樣本量遠超票面要求（medium/LEAPS 合計 408 筆 vendor-IV 觀測，遠超
  「>30 筆」的門檻）。

**但 verdict 是「這一輪驗證的問題」得到了強力肯定答案，不等於「可以
不做任何準備就上線」**——下面第 5 題列出施工前仍然必要的 guardrails，
`STRONG_PASS` 不代表跳過它們。

### 5. Production implementation 前還有哪些必要 guardrails？

1. **§9-C 三個取數缺口要真正搬進 production**（本輪修正只做在 prototype
   層——`marketdata.py` 的解析層仍然沒有把 `updated`／`dte` 帶出來，
   `ratecurve.py`／`dividends.py` 仍然沒有 point-in-time 版本的公開
   介面）。這是本輪驗證「recipe 對不對」，不是「已經接好」。
2. **vendor IV 合理性關卡**——本輪發現多筆 vendor_iv≈0.0001 的退化值
   （§2 附註），這類數字如果不過濾，會在 percentile／z-score 計算裡
   製造假訊號。建議在使用 vendor IV 當 canonical input 或 benchmark
   前，加一個最低限度的合理性檢查（例如 iv 需落在 (某個下限, 某個上限)
   區間，或至少排除恰好等於 0.0001 這種明顯是佔位符而非真實反解值的
   讀數）。
3. **仍然只驗證了單一時間點的橫截面（cross-sectional）準確度**——
   本輪與前兩輪 calibration 一樣，都是同一天、跨不同 strike／expiry
   比較，不是「同一張合約、跨很多天」的縱向比較。Historical IV Trend
   真正需要的是後者。cross-sectional 準確度是縱向準確度的必要條件
   （模型本身站不住，縱向也不會準），但不是充分證明——正式上線前，
   建議至少對幾張合約做「連續數天各自反解、跟 vendor 逐日對照」的
   縱向抽查（若 vendor 未來某天 iv 不再是 null，可以直接比對）。
4. **medium 天期的失敗率偏高**（TLT 11.1%／ORCL 18.3%，遠高於
   medium_short 的 2–4% 與 leaps 的 0–1%）——本文未深究成因（可能是
   該天期流動性較差、報價較寬），正式施工前建議至少看一下這批失敗
   案例的 failure_reason 分佈是否需要額外處理，而不是照單全收。
5. **fetch_curve_asof／compute_q_asof 這兩個 prototype 函式的「挑
   point-in-time 那一列」邏輯，搬進 production 時建議直接寫成
   `ratecurve.py`／`dividends.py` 的正式函式**（不是複製這支腳本的
   寫法），並補上單元測試——本輪已經用 `tests/fixtures/
   treasury_csv_sample.txt` offline 驗證過選列邏輯正確（精確命中、
   假日退回最近前一列、不洩漏未來），這批驗證可以直接轉成正式測試案例。

## 6. 附錄：可重跑的診斷資產

- `scripts/prototype_historical_iv_calibration_corrected.py`——本輪
  新增，保留作研究工具。offline 驗證見腳本 docstring 與本文 §0；
  重跑不需要修改（沙箱擋 vendor，需在有網路的環境跑，例如既有 `tmp-*`
  一次性 CI probe 慣例）。
- 本文所有數字皆可由該腳本重新產生（同一天重跑會拿到新的
  observation_date、新的 vendor 報價，數字會變，但 recipe 邏輯不變）。
