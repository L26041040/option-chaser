# Historical IV Reconstruction — Calibration Prototype 結果

`/prototype` 執行紀錄（2026-08-18），對應
`docs/research/historical-iv-reconstruction.md` §8 的 calibration
experiment 設計。**這是一次性驗證結果，不是決策**——是否採用 §10
recipe、要不要先補 LEAPS 樣本，留給需求方裁決（見文末）。

## 0. 執行方式

- 腳本：`scripts/prototype_historical_iv_calibration.py`（丟棄式研究
  工具，直接 import production 的 `implied_vol()`／`fetch_chain()`／
  `load_rate_curve()`／`load_dividend_history()`，不複製任何定價公式）。
- 因為本地沙箱的 outbound proxy 擋住 `api.marketdata.app`／
  `home.treasury.gov`／Yahoo（與既有 `docs/research/dividend-yield-
  source-selection.md` 記錄的沙箱限制一致），比照既有 `tmp-*` 一次性
  CI probe 慣例，透過 GitHub Actions（真實 `MARKETDATA_APP_TOKEN`）
  執行，跑完即刪工作流檔案。
- 標的：TLT、ORCL（呼應需求方原本回報 vendor null-iv 現象的兩個真實
  標的）。

## 1. 樣本組成（與原始設計的落差，誠實記錄）

**原始設計**（研究文件 §2）要求樣本涵蓋 call/put、ITM/ATM/OTM、
short/medium/LEAPS、equity/ETF。實際執行拿到的樣本：

- **N = 328** 筆 vendor iv 非 null 的觀測（TLT 124 張合約、ORCL 204
  張合約的完整 chain，call/put 皆有，履約價範圍廣）。
- **DTE 只有一種**：兩個標的的預設 `fetch_chain()`（不帶
  `expiration=` 參數）回傳的都是最近一個到期日——2026-08-21，執行當天
  （2026-08-18）算起是 **3 天到期**。這是 vendor 官方文件記載的行為
  （本 repo 既有 `fetch_surface()` docstring 已經記錄過這個坑，
  `option_chaser/data/marketdata.py:367-368`，#134），不是抓取錯誤。
- **補抓 medium／LEAPS 到期日的嘗試沒有成功**：第一次補抓因腳本自己
  的 bug（忘記 `import json`）靜默降級失敗（try/except 接住、不影響
  主樣本，但也沒拿到新資料）；修好 bug 後重跑兩次，皆收到 Market Data
  App **HTTP 403**——前兩次（近月選主樣本）用同一把 token 都成功，
  短短數分鐘內連續補抓才開始 403，讀起來像是這把 token 方案的
  rate limit／額度上限，不是 auth 或程式問題。依專案規則
  （vendor／external dependency 無法自行解決時停止，不硬幹）沒有
  再重試——**本次結果只涵蓋 3-DTE 這一種到期日，完全沒有 medium／
  LEAPS 樣本**，這是一個真實、未補上的樣本缺口，不是可以忽略的細節：
  Historical IV Trend 的實際產品場景是 LEAPS 尺度（月～年），3-DTE
  是目前產品完全不會遇到的極端案例。

## 2. A. 數字結果

### 整體

| 指標 | 值 |
|---|---|
| N | 328 |
| ok（成功反解） | 183 |
| failures | 145（44.2%） |
| ├─ no_valid_mid（bid/ask 缺席或倒掛） | 94 |
| └─ implied_vol_no_solution（目標價落在模型可行區間外） | 51 |
| MAE | 0.3816（38.2 vol points） |
| median AE | 0.2907 |
| p90 AE | 0.7228 |
| bias | +0.3816（**幾乎等於 MAE——誤差幾乎全部同號，系統性高估**） |
| Pearson | 0.9991 |
| Spearman | 0.9970 |
| percentile rank diff | median 0.005／p90 0.016 |

### 分群：moneyness

| | n | ok | MAE | Pearson | Spearman |
|---|---|---|---|---|---|
| ATM | 47 | 47 | 0.1545 | 0.9998 | 0.9978 |
| ITM | 139 | 88（51 反解失敗） | 0.5050 | 0.9989 | 0.9976 |
| OTM | 48 | 48 | 0.3777 | 1.0000 | 0.9998 |

### 分群：option_type

| | n | ok | MAE | Pearson | Spearman |
|---|---|---|---|---|---|
| call | 164 | 69（95 失敗，58 no_valid_mid＋37 no_solution） | 0.2627 | 0.9890 | 0.9905 |
| put | 164 | 114（50 失敗，36 no_valid_mid＋14 no_solution） | 0.4536 | 1.0000 | 0.9994 |

### Ranked table（節錄，完整表見 CI log／可重跑腳本輸出）

按 vendor_iv 排序後，`rank_v`／`rank_o` 兩欄幾乎逐行貼齊（例如
vendor_iv 從 0.085 排到 3.33，our_iv 排名與 vendor 排名的落差絕大多數
在 ±1～2 名以內），這正是 percentile_rank_diff median=0.005 的直接
體現。唯一的明顯離群：`ORCL260821C00136000`（vendor_iv=0.0001，
幾乎是數值上的零，our_iv=0.4399，rank 從第 1 名跳到第 35 名）——這張
合約本身的 vendor IV 讀數在近乎歸零的水準，本身就是深度 ITM/OTM
3-DTE 合約在數值上不穩定的訊號，不是我們的反解方法特別失準。

### Spread-quality sanity check

最寬 8 筆 relative spread 全部是 ORCL、都在 1.2–1.9（也就是 ask 是
mid 的 2 倍以上）——這種量級的價差本身就是市場品質很差的訊號。但：

**窄價差（<15%，n=136）MAE=0.3968；寬價差（>=15%，n=47）MAE=0.3375**
——寬價差那組的 MAE **反而比較低**，跟「價差越寬、誤差越大」的直覺
假設相反。這代表本次樣本裡，abs_error 的主要驅動因子不是 bid-ask
價差寬窄，而是別的東西——見下面分群觀察的解讀。

## 3. B. 分群觀察

**ITM 誤差遠大於 ATM／OTM**（MAE 0.505 vs 0.155 vs 0.378），且 ITM
是唯一出現大量 `implied_vol_no_solution` 失敗（51 筆）的群組——這與
「價差寬窄」無關（上面已排除），指向另一個更根本的原因：

**這批樣本清一色是 3 天到期的合約，vega 在這個天數已經接近零**——
implied vol 反解的敏感度（∂price/∂σ）隨 T→0 塌縮，代表：(a) mid
價格裡任何幾分錢等級的雜訊（bid-ask 離散化、報價機制固有的 tick
size），换算成 IV 誤差會被放大到數十個 vol points 等級；(b) 深度
ITM／OTM 合約在這個天數下，extrinsic value 本身只剩幾分錢，mid 稍微
偏離 fair value 就可能落在模型可行區間外（這正是
`implied_vol_no_solution` 集中在 ITM 群組的原因）。**這是選擇權市場
眾所周知的現象——近到期日的 IV 讀數天生噪音大**（【本文推導】：
一般選擇權市場實務常識，非本次新查證的一手資料），不是本次
recipe 特有的缺陷；但也正因如此，**本次樣本剛好是對這套 recipe
最不友善的極端情境**，離 Historical IV Trend 真正的產品場景（LEAPS，
vega 遠大於此、反解天生穩定得多）很遠。

**Call 的失敗率高於 put**（57.9% vs 30.5%，主要差在 `no_valid_mid`：
58 vs 36）——ORCL／TLT 這批 3-DTE call 的報價品質看起來整體比 put
差，但這更可能是這兩個標的、這個到期日當下的市場特性，不是
call/put 兩種 payoff 结构本身的系統性差異。

**系統性正偏差（our_iv 幾乎全部高於 vendor_iv，bias≈MAE）**：這是
本次結果裡最需要進一步診斷、但本次無法完全確認成因的一點。已排除
的候選解釋：q 誤差（若 q 系統性偏高，calls／puts 的 iv 反解偏差方向
理論上應該相反，但實測兩者同號，故 q 誤差不是唯一或主要原因）；r
誤差（T=3 天下 `e^{-rT}` 貼現效應趨近於 1，量級太小不足以解釋 50%
級別的系統偏差）。

> ## ⚠ 更正（2026-08-18，見 `historical-iv-reconstruction-bias-diagnosis.md`）
>
> **本節原本推測「最可能的解釋是 3-DTE 下 vega 塌縮造成的數值不穩定」
> ——這個歸因是錯的，已被後續診斷推翻。**
>
> 真因是**參照日錯配**：Market Data App 回的是延遲快照（HTTP 203，
> `updated` 指向前一個交易日收盤），vendor 用**快照自己那一天**算 IV，
> 而本腳本用 `date.today()` 算 T。那一輪快照比執行日早 4 個日曆天，
> 於是 vendor 眼中 DTE=7、我們眼中 DTE=3。
>
> 證據：只把 T 換成 7 天，同樣這 183 筆的 MAE 從 0.3813 掉到 **0.0020**
> （190 倍），our/vendor 比值從 1.5249 收斂到 **1.0001 ± 0.0068**。
> 另有直接觀測（讀出 `updated` 與 vendor 自己的 `dte` 欄位）佐證。
>
> **原推測站不住的理由**：噪音不可能產生 stdev 只有 3% 的常數乘法比值。
> 觀測到的比值 1.5249 恰好等於 √(7/3) = 1.5275——那是一個**時間比**，
> 不是隨機誤差。vega 塌縮確實存在，但它解釋的是**殘留離散度與失敗率**
> （修正 T 後：時間價值 <$0.10 組中位殘差 0.28 vol pts vs ≥$0.10 組
> 0.02 vol pts），不是這個 38 vol points 的系統性偏差。
>
> 下面第 4 節的 `PASS_WITH_GUARDRAILS` 判定與第 5 節的已知限制，
> 請一併以診斷文件的結論為準（該文判定為 `YES_WITH_GUARDRAILS`，
> 且已補上真實 LEAPS benchmark）。

## 4. C. Verdict

## **PASS_WITH_GUARDRAILS**

**Ranking stability**（票上明訂的優先判準）**表現極強**：Pearson
0.9991、Spearman 0.9970、percentile rank diff median 僅 0.005——即使
是在 3-DTE 這個對任何 IV 反解方法都最不友善的極端情境下，這套
recipe 仍然把 vendor IV 的相對高低排序保留得非常完整。這件事本身是
一個正面訊號：Historical IV Trend 的核心用途（現在比過去貴還是便宜）
依賴的正是這個相對排序，而不是絕對數字。

**但不給 STRONG_PASS**，理由：

1. **完全沒有驗證到 LEAPS／medium DTE**——這是產品真正的使用場景，
   本次因為 vendor rate limit 沒能補上，是個真實、未解決的證據缺口，
   不是可以略過的細節。
2. **絕對誤差量級大（MAE 38 vol points）且系統性方向一致**——雖然對
   percentile／z-score 這類 scale-較不敏感的統計量影響有限，但如果
   直接把 our_iv 顯示成「目前 IV」這個絕對數字，落差達到這個量級會
   誤導使用者；系統性偏差的根本原因本次只做到「排除部分候選解釋、
   推論出最可能成因」，未完全鎖定，仍需要更多樣本（尤其是 LEAPS）
   才能確認。
3. **失敗率偏高（44.2%）**——雖然兩種失敗模式（`no_valid_mid`／
   `implied_vol_no_solution`）都是 recipe 刻意設計的「誠實缺值，不
   硬猜」行為（見研究文件 §10 failure behavior），而不是程式錯誤，
   但如果這個失敗率在 LEAPS 天期依然這麼高，會讓 Historical IV Trend
   的可用觀測數大幅縮水。

**建議的 guardrails**（本文推導，供需求方裁示要不要落地）：

- 正式採用前，至少要在 medium／LEAPS 天期補一輪同樣的 calibration
  （vendor rate limit 解除後重跑本腳本即可，程式邏輯已經就緒，只是
  這次沒拿到資料）。
- 若最終要顯示 reconstruction 出來的絕對 IV 數字（不只是 percentile／
  z-score），近到期日（例如 <14 或 <30 天）的重建值應該標記為低信賴
  度，而不是跟遠期合約一視同仁地顯示——這與研究文件 §10 recipe 的
  `failure behavior`（反解失敗就誠實缺值）是同一個精神的延伸：反解
  「成功」但落在天生噪音很大的區間，也該讓使用者知道。

## 5. 已知限制（誠實記錄）

- 樣本完全集中在一個到期日（2026-08-21），是 vendor 預設行為造成的
  副作用，不是刻意的抽樣設計；medium／LEAPS 樣本因 vendor rate limit
  未能補上（詳見第 1 節）。
- Rate curve／dividend q 都是**今天**（2026-08-18）算出來的（因為
  這是「今日快照 vs vendor 今日 iv」的驗證，本來就該用今天的值，
  不是歷史 point-in-time——這與 `historical-iv-reconstruction.md` §7
  防 look-ahead bias 的原則並不衝突，那一節管的是真正歷史觀測的重建，
  這裡是驗證 recipe 本身在「當下」是否站得住）。
- 只測了 TLT（ETF）／ORCL（equity）兩個標的，樣本廣度有限。

## 6. 產出物

- `scripts/prototype_historical_iv_calibration.py`——保留作研究工具，
  可在 vendor rate limit 解除後直接重跑取得 medium／LEAPS 樣本，
  不需要修改。
- 本檔案（結果紀錄）。

---
_研究性質——非最終決策，等需求方裁決是否核准 §10 recipe、是否要求
先補 LEAPS 樣本再決定。_
