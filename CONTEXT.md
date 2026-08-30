# Option Chaser — 領域詞彙（ubiquitous language）

這份檔案給接手的人與 AI 一份**共用的名字**。規則：程式碼、issue、
commit、對話裡指同一件事時，用同一個詞；這裡沒有的概念要新增時，
先加進這裡再開始寫程式。

架構詞彙（module／interface／depth／seam／adapter／leverage／
locality）依 `/codebase-design` skill 的定義，不在這裡重複。

---

## 核心領域名詞

**Scenario（劇本）** — 使用者的一個主張：某個標的、某個目標年月、
某個目標價位（可選最好／最壞價位）。時間語意是**月級**的
（`target_month`，YYYY-MM），刻意不存在可填單一日期的欄位。

**Chain Snapshot（快照）** — 某一時刻抓下來的整條選擇權鏈。是所有
計算的輸入；一經抓取即為不可變事實。

**Candidate（候選）** — 一組具體可下單的部位（Spread 的買腿＋賣腿，
或單腿），連同它的估值與排名資訊。

**Analysis（分析）** — 拿一份 Chain Snapshot 對一個 Scenario 跑完
引擎，產出 View（見下）。同一份快照重跑必得同一結果。

**View（檢視）** — 一次 Analysis 的完整序列化結果，前後端之間的契約
本體（`store.serialize_result`）。前端零金融計算：每個顯示的數字都
已由引擎算好。

**Baseline Expiry／Baseline Selection（基準到期日／基準候選）** —
主圖與劇本卡片頭條數字所採用的那一組。清單的「最高收益率」與 Step 2
主圖必須同一口徑。

---

## 策略與方向（Initial V2，spec #217）

**Strategy Family（策略家族）** — 使用者在建立／編輯劇本時勾選的層級，
也是 `Scenario.strategies` 實際持久化的詞彙。首版三個：Call / Put、
Vertical Spread、Butterfly。使用者永遠只選到這一層，不接觸下面的
Subtype。

**Subtype（子型）** — Family 底下的具體結構（`long-call`、`long-put`、
`bull-call-spread`、`bear-put-spread`、call／put butterfly）。**由
backend 在分析當下展開**（family × Direction × 啟用集合），不落盤、
不進畫面選項；新增 subtype 不得讓前端多一個 tab 或 checkbox。既有
資料裡的 subtype 字串由**全站唯一一張靜態對照表**映射回 Family，
不做資料遷移。每個候選帶著它實際的 subtype 代碼。

**Scenario Bet Ranking（劇本下注排名）** — 本產品的定位：回答「如果
我的價格劇本成立，哪一個 Candidate 的成功情境報酬最好」。**不是**
risk-adjusted return、return on risk capital、max-loss efficiency、
portfolio optimization 或 suitability engine。報酬分母是今天實際投入
的成本（worst executable entry 的 net debit）；失敗情境不是排名維度。
推論：**不存在 unbounded max-profit 概念**——包絡量一律在既有的
scenario／到期日搜尋區間內導出，不掃描整個 underlying price domain
取教科書式的理論極值。

**Direction（方向，衍生三態）** — 看漲／看跌／持平，由 `target_price`
相對 spot 於**分析當下**算出。**永不落盤、不進事件**（它會隨 spot
改變，不是使用者存下來的偏好）。沒有容忍帶：極接近但不等於現價的
方向性劇本本來就合法。

**Eligibility（可選／不可選）** — 某個 Family 在某個劇本下能不能用。
在 backend 以 **subtype 為單位**判定，Family 層是「旗下任一啟用
subtype eligible」的 OR 投影。不可選的 Family 在畫面上要看得到並
說明原因；**frontend 只渲染 verdict，永不自行計算 eligibility**。
這是事實陳述，不是推薦、不是評語（見「名詞紀律」）。

**Profit Region（獲利區間）** — 非單調結構（Butterfly）兩個損益兩平
點所夾的區間。既有的保本 suffix 掃描只對**單調** payoff 成立，對
Butterfly 會誤報「永遠不損益兩平」，因此非單調家族改報這個區間；
單調家族的掃描邏輯逐位元不變。

**Per-family Representative（家族代表候選）** — 每個 Family 各自的
代表候選與其劇本報酬，落盤成 `family → {representative, best_return}`
的 map（additive 加欄位）。既有的 scalar `best_return` 與
`representative_candidate` **保留**，語意＝**跨 family 冠軍**——劇本
卡片頭條數字與詳細頁預設打開的主圖永遠是它，兩邊同一口徑。

---

## Refresh（刷新）語意

**Refresh Run（一輪刷新）** — 一次使用者動作所涵蓋的整批劇本刷新，
是一個**深模組**，也是一次 serverless invocation 的工作單位。Run 內
同 symbol 的 Chain 只抓一次（純記憶體去重，見 ADR-0001）。

**Refresh Trigger（刷新時機）** — 只有三種，不新增第四種管道：
1. 開站
2. 使用者按頂部刷新鈕
3. 建立新劇本

前兩者的 Run 範圍是「全部未過期劇本」；**建立新劇本的 Run 範圍只有
新建立的那一個劇本**（2026-08-24 需求方裁示 P4-b，取代 QA1-07 時期
的全量刷新）。

**Continuation（續跑）** — 一個 Refresh Run 若在 server 端時間預算內
沒跑完，回傳「已完成的 rows ＋ remaining ids」，由前端自動再發一次
請求接續。分段是 60 秒函式上限的安全閥，不是常態路徑。

**Partial Success（部分成功）** — 一個 Refresh Run 裡，成功的劇本
照常落地更新，失敗的劇本保留舊資料並亮既有失敗燈號、可單卡重試
（2026-08-24 裁示 P2-a）。一顆壞掉的 symbol 不拖累整輪。

**Updating Badge（更新中徽章）** — 刷新進行中，卡片顯示**上一輪的
舊資料**並標記「更新中」，全程可瀏覽、可進詳細頁；結果回來逐批換新
（2026-08-24 裁示 P1-b，取代先前整段灰化鎖定）。

**Freshness（新鮮度）** — 每張卡片的資料時間戳。使用者辨識「我現在
看到的數字是哪一刻的」唯一依據，因此 Updating Badge 期間必須仍然
可見。

---

## Historical IV 子系統

**Exact-Contract Series（確切合約數列）** — 以 OCC 身份鎖定同一張
合約，回溯它自己的歷史報價再重解 IV。是 canonical 的那一條。

**Legacy Re-anchor Series（舊重錨定數列）** — 以 (tenor, delta) 座標
在歷史 surface 上重新錨定。與上者是兩條**平行獨立**的 pipeline，
最終在回應裡合併。

**Backfill（歷史補建）** — 把某 symbol 的歷史 IV 觀測值逐日補齊。
配額規則限制單次請求最多補 25 天，每個 symbol 每天只跑一批。

**Progressive Backfill（漸進補建）** — 補建不會一次到位，需跨數天
的使用者造訪才達到目標涵蓋率。這是刻意的取捨，不是缺陷。

**Two-Phase Backfill（兩段式補建）** — 冷 backfill 不再同步夾在
iv-history 請求裡：先立即回傳既有歷史把圖畫出來，補建由第二個請求
觸發，完成後圖表自動補全，卡片期間標「歷史資料補建中」
（2026-08-24 裁示 P3-a）。

**Normalized Skew（標準化偏斜）** — 買賣腿 IV 相對關係的主資訊。

**Spread IV Gap（價差 IV 落差）** — 兩腿 IV 數列對齊後的差值數列。
對齊與裁切的順序（align-then-trim）是正確性關鍵。

**Point-in-Time（PIT，時點）** — 回算歷史某一天時，利率 r 與股利
率 q 必須取**那一天**的值，不能用今天的。違反此原則曾造成一次真實
的偏誤事故。

---

## 資料源

**Cboe** — 延遲報價，chain 的主資料源。盤外報價凍結而非歸零。

**yfinance** — 備援資料源，已移出核心依賴（避免 pandas/numpy 進
serverless bundle），故雲端環境實際上不可用。

**Market Data App** — 歷史合約報價與歷史 surface 的資料源，需要
使用者自備 token。

---

## 名詞紀律（不要用的說法）

- 不要說「成交摩擦」——用 **Bid-Ask Spread**。
- 不要對候選下人工評語（「收斂完全」「中庸帶」之類自創詞）。
- 不要用「目標日期」——時間語意是月級的，只有 **target_month**。
- **Friction 已自 canonical model 退場**（spec #217 決策 D）：收益與
  排名一律從 worst executable entry 起算，execution spread 已內生於
  進場價格，不該二次處理——不額外扣除、不做排名 penalty、不建 score、
  不作為估值輸入，也不為診斷保留一個可能被後續誤用的 canonical
  metric。**不得新增任何 friction 指標。** 既有的 `friction`／
  `friction_amount` 欄位屬 legacy 清理／隔離對象（T04／#220）；在它
  真正退場之前，T01 的數值基準仍然凍結它們的現況值。
