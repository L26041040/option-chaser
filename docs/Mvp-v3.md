Option Chaser — MVP V3 Spread Analysis Spec

1. MVP V3 定位

MVP V3 先專注把目前的 Spread 分析頁完整化。

本輪主要處理三件事：

* Spread 詳細頁的 UI / Information Hierarchy 進化
* Candidate 的 Historical IV Position
* Heatmap 加入 Spread 與對應裸買腿的 Crossover Boundary

本輪不要同時擴張其他策略頁面。

核心原則：

先把目前 Spread 的分析體驗做成完整母版。

⸻

2. Spread 詳細頁 UI 進化

目前 Spread 頁已經有：

* Candidate ranking
* Buy / Sell Strike
* Buy Ask
* Sell Bid
* Net Cost
* Return
* Expiry
* Heatmap
* Price Ladder
* Expiry Structure
* Candidate Pool
* Spread History
* Analysis Report
* Quote-quality warning

MVP V3 不要推翻這些功能。

主要工作是重新整理：

* 哪些資訊最重要
* 哪些資訊應該先看到
* 哪些資訊屬於第二層
* 如何加入 IV History 又不讓 Candidate Card 過度膨脹

目標不是「增加更多卡片」。

目標是：

讓同一組 Candidate 的價格、IV、報酬與時間風險可以在一個自然的閱讀流程裡理解。

⸻

3. Candidate Card 資訊階層

Spread Candidate 的主要閱讀順序建議為：

1. Candidate Identity
2. Return
3. Entry Cost
4. Historical IV Position
5. Heatmap
6. 其他進階資訊

例如：

* #1
* B105 / S110 Call Spread
* +238%
* Buy Ask 15.2
* Sell Bid 8.4
* Net Cost 6.8
* IV History
* Heatmap

不要因為加入新功能，把同一份資訊在不同 Card 重複顯示。

⸻

4. Historical IV Position 的目的

Historical IV Position 主要回答：

「如果我本來就準備在這附近建立這組 Spread，現在的 volatility 結構相對歷史在哪裡？」

典型使用場景：

標的正在盤整。

例如：

TLT 長時間在 90～95 附近。

使用者已經有未來價格劇本，因此「標的現在多少錢」的差異可能不大。

真正影響進場時點的其中一個重要因素，反而是：

現在買到的 IV 結構是不是處於不同的歷史位置。

Historical IV Position 是決策資訊。

不是自動交易訊號。

⸻

5. Normalized Skew 是主要 IV 資訊

Spread 有兩條腿，因此只看 Buy Leg IV 不完整。

例如：

情況 A：

* Buy IV = 12%
* Sell IV = 18%

情況 B：

* Buy IV = 12%
* Sell IV = 13%

雖然 Buy Leg IV 完全相同，但兩組 Spread 的 volatility structure 並不相同。

因此 MVP V3 必須顯示 Normalized Skew。

Normalized Skew 在 IV 區塊中是最重要資訊，視覺順位必須高於 Buy / Sell Leg 各自 IV。

例如：

Normalized Skew 0.50 · 1Y Percentile 78

並搭配歷史線。

⸻

6. Buy / Sell Leg IV

Normalized Skew 下方再顯示兩條腿本身。

至少包含：

Buy Leg

* Current IV
* Historical Percentile
* Historical Line

例如：

Buy IV 12.0% · 1Y Percentile 24

Sell Leg

* Current IV
* Historical Percentile
* Historical Line

例如：

Sell IV 18.0% · 1Y Percentile 61

目的不是用其中某一條取代 Normalized Skew。

而是讓使用者知道：

整體 skew 為什麼會落在現在的位置。

⸻

7. 三條 IV Historical Lines

每組 Candidate 顯示三條歷史線：

1. Normalized Skew
2. Buy Leg IV
3. Sell Leg IV

資訊權重不是三條完全相同。

應該是：

Normalized Skew = Primary

Buy / Sell IV = Supporting Detail

為避免畫面過度膨脹：

* Historical chart 應保持 compact
* 可以使用 sparkline 類型
* Buy / Sell IV 可以考慮左右並排
* 不需要把公式與完整 methodology 常駐在 Candidate Card

MVP V3 的重點是讓使用者快速讀值，不是把研究報告塞進 UI。

⸻

8. IV History 必須屬於 Candidate

IV History 不能掛在整個 Scenario 上。

例如同一個 TLT 2028/12 劇本裡：

* B95 / S105
* B100 / S110
* B105 / S115

三組 Spread 的 volatility structure 可能不同。

因此 Historical IV Position 必須跟著目前正在看的 Candidate。

不能把某一組 Candidate 的 IV 數字冒充成整個 Scenario 的 IV。

⸻

9. IV 呈現保持客觀

UI 可以顯示：

* Current IV
* Percentile
* Normalized Skew
* Historical Line

例如：

Normalized Skew 0.50 · P78

Buy IV 12.0% · P24

Sell IV 18.0% · P61

不要自動寫：

* 很便宜
* 很貴
* 好買點
* 建議進場
* 有利
* 不利

Option Chaser 提供事實。

交易判斷由使用者自己完成。

⸻

10. Heatmap 加入 Crossover Boundary

目前 Heatmap 已經回答：

這組 Spread 在不同未來時間與標的價格下，報酬如何？

MVP V3 要增加第二層資訊：

在不同「日期 × 標的價格」下，這組 Spread 與對應裸買腿的報酬誰比較高？

例如：

Spread：

2028/12 B105 / S110 Call Spread

比較對象：

2028/12 105 Long Call

如果標的很早就到 110，例如 2027/12：

Long Call 可能因為仍保有大量時間價值而具有較高報酬。

但如果 110 是接近 2028/12 才到：

Spread 因為初始成本較低，可能逐漸反超。

因此兩者不是只有一個固定的「誰比較好」。

⸻

11. Crossover 不是一個點

原本的「追平價格」只是一維答案。

MVP V3 要把它提升成：

Time × Price 的勝負邊界。

也就是找出所有：

Spread Return = Comparator Return

的位置。

這些位置連起來形成：

Crossover Boundary

它可能是：

* 斜線
* 曲線
* 不規則邊界

不要預設它一定是直線。

⸻

12. Crossover 直接疊在原本 Heatmap

不要為 Crossover 再建立第二張重複 Heatmap。

應直接在原本 Spread Heatmap 上 overlay Crossover Boundary。

概念上：

一側代表：

Comparator Return > Spread Return

另一側代表：

Spread Return > Comparator Return

中間：

Crossover Boundary

如此使用者仍然是在看同一張熟悉的 Spread Heatmap，只是多了一層非常有用的比較資訊。

⸻

13. Crossover 的閱讀目的

Crossover 主要回答：

「如果我的價格劇本提早發生，和比較晚才發生，Spread 的相對優勢會如何改變？」

例如：

目標價都是 110。

但：

* 2027/12 到 110
* 2028/06 到 110
* 2028/12 到 110

可能得到完全不同的相對報酬結果。

所以使用者不只知道：

「我的目標價是多少。」

還可以知道：

「我的劇本如果提早實現，會不會其實另一種 payoff exposure 更有優勢？」

⸻

14. Crossover 視覺原則

Crossover Boundary 必須：

* 容易辨認
* 不遮住 Heatmap 數字
* 不破壞原本 Heatmap 閱讀

可以使用：

* 細線
* 虛線
* 輕量區域標示
* 簡短文字標籤

不要每個 Heatmap cell 都額外寫：

* WIN
* LOSE
* CALL WIN
* SPREAD WIN

否則資訊會過度擁擠。

詳細位置與版面後續由獨立 .txt wireframe 定義。

⸻

15. 現有 Long Call 追平價格

目前系統已經存在「Long Call 追平價格」。

MVP V3 的 Crossover Boundary 本質上是這個概念的二維擴充。

因此 /to-spec 時需要確認：

* 舊的一維追平價格是否仍有獨立閱讀價值
* 或已被新的 Crossover Boundary 完整取代

不要在沒有需求的情況下，同時留下兩套重複資訊造成 UI 膨脹。

⸻

16. Mobile 資訊密度原則

沿用 MVP V2 已確立原則：

壓縮的是留白、裝飾與重複標籤，不是金融資訊。

加入 IV History 與 Crossover 後尤其需要注意：

* 不要產生大量新的大型 Card
* 不要使用過高 vertical padding
* Normalized Skew 優先
* Buy / Sell IV 為第二層
* Historical lines 保持 compact
* Crossover 使用原 Heatmap overlay，而不是新增第二張圖

目標仍然是成熟投資工具的資訊密度。

⸻

17. Desktop 原則

Desktop 保留既有 Scenario Library / Main Workspace 架構。

MVP V3 主要改善右側 Spread Detail Workspace。

不要因為 V3 重做整個 Scenario Library。

不要破壞 MVP V2 已完成且已驗收的 Desktop / Mobile navigation。

⸻

18. Historical Data 原則

Historical IV 不能採用：

每天自行保存完整 option chain。

歷史資料應優先使用可按需取得的 historical options / IV data source。

目標：

* DB 負擔最低
* 不維護龐大的 options history
* 需要時才取得 candidate 所需歷史資料

具體 vendor 與 API 使用方式由後續 spec / validation 決定。

⸻

19. Valuation Correctness

目前研究已發現現有 valuation engine 對 TLT 類配息標的存在 q=0 問題。

這會影響：

* Long-dated option theoretical value
* 提前時間點估值
* Crossover Boundary

因此 Crossover 正式施工前必須確認：

配息／distribution treatment 不會讓比較結果被錯誤估值污染。

這是 correctness requirement，不是新增產品功能。

⸻

20. MVP V3 成功狀態

MVP V3 完成後，使用者打開一組 Spread Candidate，應能很快回答：

1. 這是哪一組 Spread？
2. 我要付多少成本？
3. 目標情境報酬多少？
4. 目前 Normalized Skew 在歷史哪裡？
5. Buy Leg IV 在歷史哪裡？
6. Sell Leg IV 在歷史哪裡？
7. 三者過去一段時間怎麼變化？
8. 不同未來日期與標的價格下，Spread 報酬如何？
9. 哪些 Time × Price 區域 Spread 開始反超比較對象？
10. Crossover Boundary 大致如何移動？

整體體驗應仍然是一個完整的 Spread Analysis Workspace。

不是把很多新功能堆在一起。

⸻

21. 下一步

本文件確認後：

1. 另外建立完整 Scenario Detail .txt Wireframe
2. 另外建立 Crossover Heatmap .txt Wireframe
3. /clear
4. /to-spec
5. 人工 Review
6. 有真正未裁示問題才局部 Grill
7. /to-tickets
8. 再開始施工

本階段只定義 MVP V3 需求，不直接進 implementation。