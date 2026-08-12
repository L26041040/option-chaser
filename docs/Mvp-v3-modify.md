請完成 Option Chaser 的 Settings / Market Data API Token 功能，並以以下 UI 方向施工。

UI 草圖

MOBILE
┌─────────────────────────────┐
│ Option Chaser             ⚙ │
├─────────────────────────────┤
│                             │
│          工作區             │
│                             │
└─────────────────────────────┘
點擊 ⚙：
┌─────────────────────────────┐
│ ← 設定                      │
├─────────────────────────────┤
│ Data / API                  │
│                             │
│ Market Data                 │
│ Historical IV              │
│                             │
│ API Token                   │
│ ┌─────────────────────────┐ │
│ │ •••••••••••••••••••••   │ │
│ └─────────────────────────┘ │
│                             │
│ [ 測試連線 ]      [ 儲存 ] │
│                             │
│ ● 已連線                    │
└─────────────────────────────┘
DESKTOP
┌───────────────┬──────────────────────────────┐
│ Option Chaser │                              │
│               │                              │
│ 劇本          │                              │
│ 垃圾桶        │           工作區             │
│               │                              │
│               │                              │
│               │                              │
│               │                              │
│ ⚙ 設定        │                              │
└───────────────┴──────────────────────────────┘

位置

Mobile：

* 齒輪放主要工作區右上角。
* 左上保留返回／導航用途。

Desktop：

* 「⚙ 設定」固定放 sidebar 最下方。

Settings 第一版

只需要：

Data / API
→ Market Data
→ Historical IV

提供：

* API Token 輸入
* masked 顯示
* 儲存
* 測試連線
* 未設定／已連線／驗證失敗狀態

行為

沒有有效 Market Data Token：

* Historical IV 整個模組不要出現在正常分析頁。
* 不發 Historical IV request。
* 不影響其他功能。

有有效 Token：

* Historical IV 自動解鎖。
* #111、#114 共用這條 credential path。

Security

Token：

* 不得 commit
* 不得寫進 CLAUDE.md / issue / fixture
* 不得出現在 logs
* UI 不得重新顯示完整已儲存 token

請依 repo 現有架構選擇合理的安全儲存方式，不要為此大改架構。

完成 Settings 後，直接用此 credential path 完成 #111 Market Data 真實驗證；若符合 AC，關閉 #111，接著施工 #114。

Historical IV 永遠只做 enrichment，不得影響 ranking / filtering / candidate selection / expiry_best / expiry_top10 / representative candidate。

完成後跑相關 regression、desktop/mobile E2E、commit + push。
不要開 PR。