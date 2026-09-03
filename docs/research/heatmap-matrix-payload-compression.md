# Candidate Heatmap Matrix 傳輸成本壓縮方案

研究日期：2026-08-28。對應 issue #216（`wayfinder:research`，parent #209）。
承接 #211 已裁定的決策：wire 採投影＋top-N（每 family ≤5 到期日 ×10
候選），儲存層全保真不動——本文只研究 **matrix 這一塊在 wire 上怎麼傳
最省**，不重新討論 candidate 數量該截多少。

**Owner 硬需求**：每個候選展開就能看到 heatmap，不可犧牲。

**紅線**：前端零金融計算（`CONTEXT.md`）——前端不得重算 BS93／定價
格值；解碼緊湊格式（reshape flat array、base64 decode）不算計算，是
純資料結構轉換，本文逐案評估時會明確標出哪一步是「解碼」、哪一步若
做了就會踩線。

**本文性質聲明**：純研究，未修改 `option_chaser/`、`api_app/`、
`src/`、`contracts/` 任何檔案。全部量測皆可用 repo 現成 fixture 與
`option_chaser.matrix` 的既有純函式重跑（見各段落附的計算方式）。

---

## 0. 證據等級聲明

沿用本 repo 既有研究文件慣例，每條主張標明等級：

- **【實測】** 本地真實計算得出的數字，任何人都能用本文附的方法重跑。
  本文全部量化數字（除非另有標注）皆屬此類：直接讀 repo 內
  `contracts/analysis_sample.json`／`contracts/analysis_sample_
  bear_put.json`，或用 `option_chaser.matrix` 的既有純函式
  （`price_axis`／`date_axis`／`matrix_grid`）產生的合成資料，逐一
  用 Python 內建 `json`／`gzip`／`zlib` 與外部 `brotli`（1.2.0，
  `pip install brotli` 裝進本沙箱，MIT 授權的官方 Python binding）
  量測位元組數。
- **【官方文件】** 直接讀到的官方文件原文。本文**沒有**這一等級的
  證據——`vercel.com` 全域在本沙箱被 egress proxy 擋下
  （`WebFetch` 回傳 `EGRESS_BLOCKED`），無法直接開頁面核對原文字句。
- **【二手轉述】** `WebSearch` 回傳的搜尋索引摘要，內容聲稱轉述自
  `vercel.com/docs/compression.md` 與 `vercel.com/docs/how-vercel-
  cdn-works/compression`，但摘要本身經過搜尋引擎整理，不是逐字讀到
  的原文。本文第 3-c 節的 Vercel 壓縮行為全部屬此等級。
- **【自行推論】** 沒有外部或實測背書的工程判斷（例如某方案對既有
  程式碼的改動範圍估計）。

**沙箱出口狀態**（本次實測，2026-08-28）：`vercel.com` 直接 `WebFetch`
回 `EGRESS_BLOCKED`；`WebSearch`（走搜尋引擎索引，非直接連到目的網域）
可用，取得兩則與 Vercel 壓縮相關的搜尋摘要，內容見第 3-c 節。這與過去
研究文件記錄的沙箱出口政策一致（多數目的網域 403／被擋，`WebSearch`
不受此限）。`pypi.org`（`pip install brotli`）在本次連線正常，故第
3-c 節的**壓縮率**數字（多少 bytes 壓成多少 bytes）本身是【實測】，
只有「Vercel 是否對這個 endpoint 自動套用該壓縮」這件事是【二手轉述】。

---

## 目錄

1. 問題陳述
2. 現況實測數字
3. 逐案評估（a–e）
4. 推薦組合與首屏估算
5. 供 `/to-spec` 直接採用的建議條目

---

## 1. 問題陳述

詳細頁 view JSON（`store.serialize_result()`）裡，每個 `candidate_pool`
候選內嵌自己完整的 price×date heatmap matrix
（`store._matrix_to_dict`，`option_chaser/store.py:184-190`）：

```python
def _matrix_to_dict(mv) -> dict:
    return {"prices": [list(pt) for pt in mv.prices],
           "dates": [list(d) for d in mv.dates],
           "cells": [list(r) for r in mv.cells]}
```

`prices`／`dates` 是**座標軸**（各自帶標籤字串），`cells` 是報酬率
格點（`float`，完整 float64 精度）。這個字典被 `_candidate()` 塞進
`candidate["matrix"]`，Crossover 對照（#115/#116）的
`candidate["comparator"]["matrix"]` 也是同一個函式序列化出來的獨立
一份。

#211 已量測：`candidate_pool` 佔每策略 view payload 的 64%（該量測
基於投影＋top-N 裁定**之前**、每策略 1125 rows 的舊規模）；本文
進一步確認 matrix 在 `candidate_pool` 內部本身也占大頭（見第 2 節），
且**在合理的 top-N 規模下，同一 Scenario 的多個候選之間，matrix 的
座標軸有結構性保證的高度重複**——這是本文找到的核心槓桿，第 3-a 節
展開。

---

## 2. 現況實測數字

### 2.1 真實契約樣本（小規模，4 candidates）

【實測】對 repo 既有兩份契約樣本做整份量測：

| 檔案 | on-disk（pretty） | compact JSON | candidate_pool | candidate_pool 佔比 | matrix 總量 | matrix 佔整份比 |
|---|---:|---:|---:|---:|---:|---:|
| `analysis_sample.json` | 55,022 B | 27,068 B | 22,498 B | 83.1% | 14,669 B | 54.2% |
| `analysis_sample_bear_put.json` | 55,466 B | 27,512 B | 23,016 B | 83.7% | 15,299 B | 55.6% |

（`candidate_pool` 佔比在這裡比 #211 量到的 64% 更高，因為這兩份樣本
本身候選數少、每個 candidate 的非-matrix 欄位相對固定成本占比較低；
兩次量測的候選數量級不同，但**matrix 是 candidate_pool 裡最大的單一
欄位**這個結構性結論一致。）

單一候選的 matrix 平均約 1,826–1,906 bytes（11 個價格列 × 7 個日期
欄，短天期候選的 `date_axis` 欄數）。

**軸重複程度**：兩份樣本各自只有 4 個候選，而且**每個候選剛好各自
一個不同到期日**（`expiry_best`：每個到期日的代表候選）：

```
distinct price-axis tuples across pool: 1   # 全池只有一種價格軸
distinct date-axis tuples across pool: 4    # 4 個到期日、4 種日期軸
```

這印證了 `option_chaser/matrix.py` 兩個軸函式的簽章本身就決定了誰會
重複：

```python
def price_axis(spot, target, bullish, best_price=None, worst_price=None): ...
def date_axis(today, expiry, max_gap_days=None): ...
```

`price_axis` 只吃 `(spot, target, bullish, best_price, worst_price)`
——除了 `bullish`（=`is_bullish(strategy)`，只有兩種值）之外全部是
Scenario／`AnalysisParams` 層級的常數，在整份 view 裡逐候選相同。
`date_axis` 只吃 `(today, expiry, max_gap_days)`——`today` 與
`max_gap_days`（GUI 固定 `GUI_MAX_GAP_DAYS=31`）是文件層級常數，唯一
會變的輸入是 `expiry`。呼叫端 `service._matrix_view()`
（`option_chaser/service.py:278-292`）逐字證實這一點：

```python
prices = price_axis(spot, p.target_price, is_bullish(p.strategy),
                    best_price=p.best_price, worst_price=p.worst_price)
dates = date_axis(today, date.fromisoformat(expiry_iso),
                  max_gap_days=GUI_MAX_GAP_DAYS)
```

**推論（非猜測，是函式簽章的直接結果）**：同一份 view 裡，distinct
price-axis 數 ≤ 2（bullish／bearish 各一組，目前 MVP 策略集合下最多
兩種方向），distinct date-axis 數 = distinct expiry 數。#211 裁定的
「每 family ≤5 到期日」代表**整份 view 的 distinct 軸對最多約
`2 × 5 = 10` 組**，與 candidate 總數（可達 `3 family × 5 expiry × 10
candidate = 150`）完全脫鉤——candidate 數量往上加不會增加 distinct
軸的數量，只要 family／expiry 數不變。

**額外一個免費的重複**：Crossover 對照（`_spread_comparator()`，
`option_chaser/service.py:451-474`）建 `comparator.matrix` 時，傳給
`_matrix_view()` 的是同一個 `spot`／`p`／`today`／`leg.expiry`
（`leg.expiry` 就是這組 Spread 自己的到期日）——因此**一個候選自己的
`matrix` 與它的 `comparator.matrix` 永遠是同一組軸**，目前卻各自
完整存一份座標軸。

### 2.2 大規模模擬（150 candidates，貼近 #211 裁定後的規模）

真實契約樣本只有 4 個候選、彼此到期日互異，看不出「同一到期日內
10 個候選共用一組軸」這件事的實際壓縮效果。本文用
`option_chaser.matrix` 的既有純函式，依 #211 裁定的規模（3 個
family × 5 個到期日 × 10 個候選＝150 個候選）產生一份合成
candidate_pool（非-matrix 欄位取自真實樣本的既有候選當模板，只有
`cells` 數值換成合成的、`prices`／`dates` 走真正的引擎函式產生）：

- 到期日跨度：49／103／270／490／880 天（涵蓋短天期到 LEAPS，
  `date_axis` 在 `GUI_MAX_GAP_DAYS=31` 下分別產出 7／7／10／17／30 欄）
- 3 個 family：2 個 bullish（`bull-call-spread` 方向）＋1 個 bearish
  （`bear-put-spread` 方向）
- 每個 (family, expiry) 組合 10 個候選

【實測】結果：

```
total candidates: 150
distinct axis pairs: 10   # 精確等於 2 個方向 × 5 個到期日，與 §2.1 推論一致
```

| | raw（compact JSON） | gzip -6 | gzip -9 | brotli -11 |
|---|---:|---:|---:|---:|
| **整份 candidate_pool（現行格式）** | 725,850 B | 106,593 B | 105,618 B | 49,830 B |

（gzip level 6 vs 9 只差 0.9%——對這種內容，級別本身不是關鍵變數，
真正的差距在演算法：brotli 11 比 gzip 9 再省 52.8%。）

matrix 資料本身（不含候選其餘欄位）：raw 465,300 B，gzip -9
96,742 B，brotli -11 47,932 B——占了整份 candidate_pool 現行格式
64.1%（raw）／91.6%（brotli 後，因為候選其餘欄位裡有更多可壓縮的
重複結構文字，matrix 的隨機浮點數字反而在壓縮後占比更高）。這與
#211 量到的「64%」量級一致，補上了本文自己的可重現版本。

---

## 3. 逐案評估

### 3-a. Shared axes dedup

**做法**：把 `prices`／`dates` 從逐候選欄位提升到 view 層一次性的
`axes: {axis_id: {prices, dates}}` 字典，每個候選（含
`comparator.matrix`）只留一個 `axis_id` 引用＋自己的 `cells`。
`axis_id` 產生方式建議＝穩定雜湊 `(bullish, expiry_iso)`（或直接用
`f"{expiry_iso}-{'up' if bullish else 'down'}"` 這種可讀字串，不必是
密碼學雜湊——碰撞的唯一風險是不同 family 的方向剛好相同、到期日剛好
相同，這正是我們**想要**共用的情況）。

**單獨效果**（§2.2 的 150-candidate 模擬，只做 dedup、cells 仍是巢狀
完整 float64）：

```
Option A (shared axes dedup only):
  raw = 394,240 B（84.7% of matrix-only baseline）
  gzip9 = 94,183 B（97.4% of baseline gzip9）
```

**單獨做這件事效益有限**：raw 只省 15.3%，gzip 後幾乎沒有差異
（97.4%）——因為 gzip／brotli 本來就很擅長吃掉「同一份軸字串重複
出現 10 次」這種模式，壓縮演算法已經免費做掉大半的 dedup 效果。
**shared axes dedup 真正的價值不在壓縮後的 bytes，而在**：

1. **未壓縮（raw）的下載量**——如果傳輸路徑上壓縮沒有生效（見
   3-c 的不確定性），這 15% 是唯一保證拿到的。
2. **前端記憶體**：150 個候選各自持有一份重複的 `prices`／`dates`
   陣列物件，dedup 後只有 10 份，GC 壓力與記憶體佔用同比例下降
   （這件事 bytes 量測看不到，但屬於 payload 優化的合理延伸目標）。
3. **與 3-b 疊加時效果不同**：3-b 若同時把 cells 換成不含軸資訊的
   純數字陣列，dedup 的 15% 就疊加在 3-b 已經壓到很小的基礎上，
   相對占比會放大（見 3-b 尾段的 A+B 組合數字）。

**成本**：前端需要一個小的「查表」步驟——候選拿到 `axis_id` 後去
`axes` 字典找回 `prices`／`dates`，再與自己的 `cells` 組成畫圖需要
的形狀。這是純查找＋reshape，不觸碰數值本身，不踩零金融計算紅線。
`Heatmap.tsx` 目前直接解構 `matrix.prices`／`matrix.dates`／
`matrix.cells`（`src/Heatmap.tsx:115`）；改動點是在渲染前先做一次
`resolveMatrix(view, candidate)` 查找，元件內部邏輯不必變。

### 3-b. Compact 編碼

三個子選項，遞進：

**b1. Flat array + 四捨五入到 basis point（1e-4）**：`cells` 從
`float[][]`（巢狀）攤平成 `float[]`（一維，長度＝`nRows × nCols`，
row-major），且四捨五入到小數點後 4 位（0.01 個百分點精度）。

精度是否安全：前端顯示只到整數百分比
（`Math.round(ret * 100)`，`src/heatmap.ts:44`）與一位小數的
±%（`toFixed(1)`，`src/heatmap.ts:62`），4 位小數精度遠超過顯示需要。
Crossover 邊界偵測（`crossoverEdges`，`src/heatmap.ts:124`）用的是
`sign(spreadCells[i][j] - comparatorCells[i][j])`——四捨五入後兩個
矩陣各自的誤差各 ±5×10⁻⁵，diff 的誤差上界 ±1×10⁻⁴，只有在真實 diff
落在這個窄帶內（相當於 0.01 個百分點差距）才可能翻轉符號，而這種
情況下畫在圖上的線本來就是「兩個報酬率幾乎相等」，使用者看不出差異
——四捨五入到 basis point 對這個既有 UI 是安全的。

【實測】（§2.2 的 150-candidate 模擬，只看 cells 本身、不含 axes，
用來單獨量測「攤平＋四捨五入」這一步的效果）：

```
Option B (flat + round4, cells only, no axes):
  raw = 166,989 B（35.9% of matrix-only baseline 465,300 B）
  gzip9 = 59,680 B
```

**A + B 疊加**（axes 只存一次＋cells 攤平四捨五入，這是本文最終
推薦的核心組合）套用到整份 `candidate_pool`：

```
raw   = 436,630 B（60.2% of baseline 725,850 B，-39.8%）
gzip6 = 69,645 B
gzip9 = 69,357 B（65.7% of baseline gzip9 105,618 B）
brotli11 = 27,952 B（56.1% of baseline brotli11 49,830 B）
```

**b2. 更激進：四捨五入到整數百分比（1e-2）**，即後端直接存
`round(ret * 100)` 這個整數，等於把前端 `formatCell()` 本來就會做的
四捨五入提前搬到後端做。這與現行顯示邏輯**逐位元等價**（顯示永遠是
同一個整數），但會讓 crossover 邊界的容忍帶放大到 0.5 個百分點——
仍在「兩者幾乎相等、使用者看不出差異」的範圍內，但比 b1 更接近臨界。
【實測】A+B2（axes dedup ＋ 整數百分比）：

```
raw = 381,241 B（52.5% of baseline）
gzip9 = 43,131 B（40.8% of baseline gzip9）
brotli11 = 16,804 B（33.7% of baseline brotli11）
```

b2 比 b1 再省一截，但代價是把「顯示精度」與「資料精度」綁死——未來
若想在 UI 加更細的 tooltip（例如 hover 顯示到小數點後一位），資料層
已經不夠用了。**本文建議 b1（4 位小數）為預設，b2 留作次輪若仍需要
進一步壓縮的追加選項**，不在本輪一次做到底。

**b3. base64(Float32Array)**：把攤平後的 `cells` 編碼成
`ArrayBuffer` → base64 字串，前端用 `atob()` + `DataView` /
`Float32Array` 解回數字陣列（標準瀏覽器 API，純解碼，不算計算）。

【實測】A + C（axes dedup ＋ base64 f32，cells 未四捨五入，float32
本身已有精度損失但遠高於顯示需要）：

```
raw = 138,591 B（19.1% of baseline，raw 體積最小的方案）
gzip9 = 75,556 B（71.5% of baseline gzip9——比 A+B1 差！）
brotli11 = 44,375 B（89.1% of baseline brotli11——也比 A+B1 差）
```

**關鍵發現**：base64 二進位在**未壓縮**時體積最小，但**壓縮後反而
比 A+B（文字型 flat + round4）差**——base64 把二進位的 4-byte
float32 攤成可列印字元，這些字元對 gzip／brotli 的字典壓縮不友善
（浮點數的位元組模式沒有 JSON 數字文字那種「同一組數字重複出現」的
規律性）。**若傳輸路徑上壓縮確實生效（3-c 的證據顯示大機率生效），
base64 float32 是反效果選項；只有在壓縮確定不生效的環境下，它的
raw 體積優勢才有意義。**

### 3-c. HTTP 壓縮實況

【實測，本地】gzip／brotli 對這種「大量重複結構、內容是隨機浮點數」
的 JSON 壓縮率：baseline candidate_pool（725,850 B）用 gzip -9 可壓到
14.6%（105,618 B），brotli -11 可壓到 6.9%（49,830 B）。brotli 明顯
優於 gzip（再省 52.8%），這與
【二手轉述】的行業共識（brotli 對文字型內容一般比 gzip 再省
15–25%，此處差距更大是因為 JSON 數字文字本身的重複結構對 brotli
的字典視窗更有利）方向一致。

【二手轉述】（`WebSearch` 索引摘要，聲稱轉述自 `vercel.com/docs/
compression.md` 與 `vercel.com/docs/how-vercel-cdn-works/
compression`，本文無法直接開頁核對逐字原文）：

- Vercel 的 CDN 層會在請求帶 `Accept-Encoding` 標頭時自動壓縮回應
  （瀏覽器的 `fetch()` 預設會帶這個標頭，本專案前端走 `fetch()`
  ——`src/api.ts`，因此請求端這一步不需要額外處理）。
- 支援 brotli 的客戶端會優先拿到 brotli（優先於 gzip）。
- 這個自動壓縮是**白名單制**、只對特定 MIME type 生效，摘要列出的
  白名單包含 `application/json`（連同 `application/javascript`／
  `text/css`／多種 `+xml`／`+json` 變體等）——本專案 API 回應是
  `application/json`，在白名單內。
- 另一則摘要提到：這個壓縮發生在 **CDN 層**，對後面接的是哪種
  serverless function runtime（含本專案用的 Python/FastAPI）透明，
  不需要在函式內手動設定 `Content-Encoding`；同時提醒**若用非瀏覽器
  客戶端手動發請求且沒有帶 `Accept-Encoding` 標頭，就不會觸發**——
  這對本專案不構成風險，因為消費端就是瀏覽器 `fetch()`。

**證據強度的誠實評估**：以上四點全部只有搜尋引擎摘要背書，沒有一手
原文可核對逐字條款（例如「白名單是否包含所有 `application/json`
還是有大小上限」「CDN 壓縮是否對 Vercel Python runtime 的動態回應
一視同仁，或只對可快取的靜態/ISR 內容生效」這類細節摘要沒有觸及）。
**本文不能替代 production 實測**：建議 `/to-spec` 落地後，用瀏覽器
DevTools Network 面板直接看一次真實 `/api/scenarios/{id}` 回應的
`Content-Encoding` 回應標頭，一次性確認即可（成本極低，不需要另開
研究票）。

**保守結論**：即使壓縮沒有生效（最壞情況），A+B 方案本身的 raw
體積已經比現行格式省 39.8%；若壓縮生效（大機率，依二手證據），
再疊加 gzip 約 34%／brotli 約 44% 的額外壓縮率提升（相對現行格式各自
的壓縮結果）。**不應該因為壓縮的證據等級不夠高就放棄 wire 層面的
compact 編碼**——compact 編碼在兩種情境下都有效，壓縮只是錦上添花。

### 3-d. Progressive prefetch

**做法**：首屏（初次載入詳細頁）只在 `candidate_pool` 裡對每個
family 的 representative candidate（即 baseline expiry 的代表候選，
`baseline_selection` 已經指出是哪一個）附上完整 `matrix`；其餘
top-N 候選只回非-matrix 欄位（供清單／候選卡片渲染），`matrix`
留空或整個省略該欄位。前端在首屏渲染完成後，立刻背景發一個批次
請求把「其餘候選的 matrix」一次拿回來（不是逐候選各發一次——逐候選
會產生 N-1 個 round trip，在本專案「N 個 request 串行」曾經是
`App.tsx` 舊架構被 Refresh Run 重構掉的同一種反模式，見 CONTEXT.md
Refresh Run 段落，不該在這裡重蹈覆轍）。使用者實際點開某個候選的
`<details>` 展開 heatmap 時，多半這個背景請求已經完成（展開這個互動
本身需要使用者先捲動／閱讀候選列，天然給了背景請求執行時間），畫面
是直接從快取讀，體感即時。

**首屏估算**（§2.2 的 150-candidate 模擬，3 個 family 各自的
representative candidate 帶完整 matrix，其餘 147 個候選只有摘要
欄位無 matrix）：

```
raw = 264,473 B（36.4% of baseline 725,850 B）
gzip9 = 3,881 B（3.7% of baseline gzip9——候選摘要欄位本身高度重複，
                 壓縮率極佳）
brotli11 = 1,624 B（3.3% of baseline brotli11）
```

這是四個方案裡首屏 payload 壓得最小的一個，但**它壓縮的是「首屏要
不要在第一時間拿到全部 matrix」這個時間維度，不是總傳輸量**——
147 個候選的 matrix 終究要傳（背景請求），總 bytes 數與 A+B 方案相近
（甚至因為多一次請求的 HTTP overhead／header 略高一點）。它解決的是
**體感延遲**，不是**總流量**，這兩者是不同的優化目標，需求文件裡
應該分開寫驗收條件。

**與既有 `fetchCache.ts` 的相容性**：`src/fetchCache.ts` 既有的
`cachedFetch(key, fetcher)` 模式（in-flight 去重＋reference-counted
abort）可以直接承接這個需求——比照既有 `getIvHistoryCached()`
（`src/fetchCache.ts:158-167`）的寫法，新增
`getCandidateMatricesCached(scenarioId, analyzedAt)`，鍵含
`analyzedAt`（新分析一到，matrix 也要重抓，語意與既有 iv-history
快取一致，不是與「容忍舊 hint」的 scenario detail 快取同一套邏輯）。
展開候選的元件（`Heatmap` 目前的呼叫端）改成：先查這個快取，快取未
命中時顯示 skeleton（本專案已有 `IvHistorySkeleton` 這類前例，見
CLAUDE.md「Historical IV 固定版位」段落），命中後渲染。

**成本／風險**：
1. 新增一個批次端點（例如 `GET /api/scenarios/{id}/candidate-
   matrices?keys=...` 或直接把 `analyzedAt` 當快取鍵、無條件回全部
   候選的 matrix——後者更簡單，且與「同一次分析結果的 matrix 集合
   本來就是不可變的」這個事實一致，不需要前端傳一串 candidate_key）。
2. 需要一個 loading 狀態（skeleton 或 spinner）覆蓋「使用者展開得比
   背景請求完成得快」這個邊界情況——機率低但必須處理，否則會是一個
   使用者能感知到的 regression（現行版本展開永遠有資料，因為資料
   已經跟首屏一起下載完了）。
3. 這是本文五個方案裡**唯一**需要新增 API 端點與前端狀態機的方案，
   改動面比 3-a／3-b 大一截（3-a／3-b 只改既有序列化函式的輸出形狀，
   不新增端點、不新增前端請求邏輯）。

### 3-e. Owner 提議「傳種子、前端渲染」

Owner 原話（issue 原文）以「傳種子」稱呼一種可能的省流量做法。這句話
有兩種可能的意思，必須分開誠實評估：

**若指「前端拿到最少量輸入（spot／strike／IV／r／q／到期日……），
自己重算 BS93 或其他定價公式得出每一格的報酬率」**——這**直接違反
「前端零金融計算」紅線**（`CONTEXT.md`）。本專案的既有架構原則是
「View 是一次 Analysis 的完整序列化結果……前端零金融計算：每個顯示
的數字都已由引擎算好」（`CONTEXT.md` View 定義）。讓前端重新實作一份
BS93／IV 反解／carry 校準邏輯，不只是工程重複（`option_chaser/
matrix.py`、`ivreconstruct.py` 等既有純函式會被前端重新發明一份），
更會製造「前後端各自一套定價邏輯、隨時可能算出不同數字」的正確性
風險——這正是本專案過去多輪修正（HIVR 系列、valuation carry 系列）
花費大量工程去消滅的那種風險。**本文明確否決這個解讀**，不建議
`/to-spec` 採用。

**若指「後端只傳一組緊湊的座標（軸）＋壓縮過的格點數值，前端只是
解碼、重新排列成表格形狀」**——這件事本身沒有計算，等同本文 3-a
＋3-b 已經評估的 compact 編碼方案。**若 Owner 的原意是這個，本文的
建議組合（第 4 節）就是這個提議的具體落地方式**，不需要另外設計。

**建議**：`/to-spec` 前先跟 Owner 確認「種子」具體所指——若答案是
後者（多數情況下業界說「傳種子」確實常指「傳最小可還原的資料」而非
「傳輸入去讓對方重算」），直接採用第 4 節的組合即可；若確實是前者，
需要 Owner 明確承擔「front-end 零金融計算」紅線鬆動的產品決策，
本文不代為決定。

---

## 4. 推薦組合與首屏估算

### 組合一（建議作為本輪必做項，風險最低）：3-a + 3-b1（+ 3-c 免費疊加）

**內容**：`candidate_pool`／`comparator` 序列化改為 view 層一次性的
`matrix_axes: {axis_id: {prices, dates}}` ＋ 每個候選只留
`{matrix_axis: axis_id, matrix_cells: number[]}`（攤平、四捨五入到
4 位小數）。壓縮交給 Vercel CDN 既有的自動 gzip/brotli（第 3-c 節，
不需要後端額外程式碼）。

**首屏估算**（3 family × 5 到期日 × 10 候選＝150 候選，`GUI_MAX_
GAP_DAYS=31` 下日期軸 7～30 欄、價格軸固定 11 列）：

| | raw | gzip -9 | brotli -11 |
|---|---:|---:|---:|
| 現行格式（baseline） | 725,850 B | 105,618 B | 49,830 B |
| 組合一 | 436,630 B | 69,357 B | 27,952 B |
| 降幅 | −39.8% | −34.3% | −43.9% |

**取捨**：改動面侷限在 `option_chaser/store.py` 的序列化函式（新增
軸 dedup 邏輯＋改 `_matrix_to_dict` 為攤平＋四捨五入）、`src/api.ts`
的 `Matrix`／`View` 型別、`src/Heatmap.tsx` 前面加一個 reshape 步驟、
`contracts/*.json` 與 `scripts/gen_contract_sample.py` 重產、
`schema_version` 建議 3→4（比照 T04／T09 先例，契約形狀變了就升版）。
**不需要新增任何 API 端點，不改變資料何時送達**——這是與現行架構
差異最小、最容易一次做完並回歸驗證的選項。

### 組合二（次輪追加，若組合一之後首屏延遲仍是問題）：組合一 + 3-d

**內容**：組合一的 wire 格式 ＋ 首屏只讓每個 family 的 representative
candidate 帶 `matrix_cells`，其餘候選延後由一個背景批次請求取得。

**首屏估算**（同一份 150 候選模擬，只有 3 個 representative 候選帶
matrix）：

| | raw | gzip -9 | brotli -11 |
|---|---:|---:|---:|
| 首屏（組合二） | 264,473 B | 3,881 B | 1,624 B |
| 背景批次（其餘 147 候選，組合一格式） | ≈ 組合一總量 −（3 個代表候選的
matrix 份額，約 8.7 KB raw）≈ 428 KB raw | ≈ 66 KB | ≈ 26 KB |

**取捨**：需要新增一個批次端點與前端 loading 狀態機（3-d 節已詳列
成本），總傳輸量與組合一相近（甚至因多一次請求略高），換來的是
「使用者第一眼看到畫面」的時間點提前、且與展開候選這個互動天然對齊
的體感即時性。**建議先出組合一、量測 production 首屏延遲是否真的
是問題，再決定要不要加組合二**——不建議在沒有 production 延遲數字
的情況下一次把兩者都做（過度工程風險，且組合二的改動面明顯更大）。

### 明確不建議的組合

- **3-a + 3-c（base64 float32）**：raw 體積確實最小，但在【二手轉述】
  顯示壓縮大機率生效的前提下，壓縮後反而比組合一差（第 3-b 節 b3
  小節的實測數字）。除非 production 實測證實 Vercel 對這個 endpoint
  沒有自動壓縮，否則不建議採用。
- **只做 3-a（不做 3-b）**：疊加 HTTP 壓縮後幾乎沒有額外效益（第
  3-a 節：gzip 後只剩 97.4% of baseline），效益/改動比太差。
- **3-b2（整數百分比精度）當預設**：把「顯示精度」與「資料精度」
  綁死，為未來 UI 想加更細緻的 tooltip 埋雷；建議留作組合一之後
  若仍需要進一步壓縮的第二輪選項，不在本輪預設採用。

---

## 5. 供 `/to-spec` 直接採用的建議條目

1. `option_chaser/store.py::serialize_result()` 新增頂層
   `matrix_axes: dict[str, {prices, dates}]`；`axis_id` 建議格式
   `f"{expiry_iso}-{'up' if bullish else 'down'}"`（可讀、天生按
   family 方向與到期日去重，不需要密碼學雜湊）。
2. `_matrix_to_dict()` 改為回傳
   `{"matrix_axis": axis_id, "matrix_cells": [round(c, 4) for row
   in cells for c in row]}`（row-major 攤平，四捨五入到 4 位小數＝
   basis point 精度）；`comparator.matrix` 沿用同一個
   `_matrix_to_dict()`，且**與所屬候選共用同一個 `axis_id`**（第
   2.1 節已證明兩者結構上必然同軸，不需要各自查一次）。
3. `schema_version` 由 3 升為 4；`contracts/analysis_sample.json`／
   `contracts/analysis_sample_bear_put.json`／
   `contracts/iv_history_sample.json`（若牽涉 matrix 形狀）與
   `scripts/gen_contract_sample.py` 同步重產。
4. `src/api.ts` 新增 `MatrixAxis`／調整 `Matrix`（或改名反映新形狀）
   型別；`src/heatmap.ts` 新增純函式 `resolveMatrix(axes, axisId,
   flatCells, nCols): Matrix`（reshape，零金融計算，供 `Heatmap.tsx`
   在渲染前呼叫一次）。
5. 前端既有 `crossoverEdges()`／`cellColor()`／`formatCell()` 等
   純函式的輸入型別不變（它們吃的是 reshape 後的 `number[][]`），
   本輪改動不動這些函式本身，只動 `Matrix` 資料怎麼從 wire 組出來。
6. 驗收條件建議寫兩條，分開驗收「總傳輸量」與「首屏延遲」兩個不同
   目標（本文第 4 節已說明兩者是不同優化維度）：
   - 總傳輸量：150-candidate 規模下，`candidate_pool` compact JSON
     體積相對現行格式降幅 ≥35%（本文組合一實測 39.8%，留安全餘裕）。
   - 首屏延遲：production 部署後用瀏覽器 DevTools 確認
     `Content-Encoding` 回應標頭確實是 `br` 或 `gzip`（第 3-c 節
     標注為【二手轉述】，需要這一步補成【實測】）；若確認生效，
     本條目視為達標，不需要另外量測毫秒數。
7. 組合二（progressive prefetch，3-d）**建議另開一張獨立 ticket**，
   不與組合一混在同一張票——理由：組合一是純序列化格式改動（低風險、
   單一 PR 可回歸驗證完畢），組合二牽涉新端點＋前端狀態機（改動面
   明顯更大），混在一起會讓一張票的回歸驗證範圍過寬。是否需要組合
   二，建議先看組合一上線後的 production 首屏延遲數字再裁示。
8. Owner「傳種子」提議：`/to-spec` 前建議先向 Owner 確認具體所指
   （本文第 3-e 節）——若指「解碼緊湊格式」，組合一即是落地方式，
   不需要另外設計；若指「前端重算格值」，需要 Owner 明確承擔對
   「前端零金融計算」紅線的鬆動決策，不建議在本票範圍內默認採用。
