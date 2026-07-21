# Option Chaser v5 — Codex Independent Audit

日期：2026-07-21
Spec（權威）：`docs/superpowers/specs/2026-07-21-option-chaser-v5-design.md`（codex peer review APPROVED, 5 rounds）
Plan：`docs/superpowers/plans/2026-07-21-option-chaser-v5.md`（codex peer review APPROVED, 2 rounds）
受審版本：master merge commit `5f2c22b`（feature/v5-workspace, 11 commits）
內部狀態：246 tests green（177 v4 回歸 + 69 新）；final whole-branch review READY TO MERGE

## 覆蓋契約（spec §7A，設計期凍結）

- **DC**：乾淨安裝；store/workspace/vocabulary/render import；工作區目錄自動建立；3.11/3.13 corner；JSON schema 檔案 parse。
- **AC**：全套件 codex 親自跑；result 序列化獨立驗證（codex 載入 result JSON，抽 ≥3 個數值欄位以引擎原語重算比對，另驗 capital/pct/days 手算）；事件投影獨立重放（codex 以 events.jsonl 重建狀態比對快取）；群組提案規則矩陣重現（含 bearish 鏡像）；id 撞名決定性；決定性雙跑逐位元；紅線掃描（擴充範圍）；v4 回歸全綠。
- **SL**：真實多劇本流程——live 建立 TLT 105/2028-01 與 TLT 115/2028-12 兩劇本 → 自動歸組＋milestone-path 提案 → 設定 capital → 群組分析（驗證兩 result 檔引用同一 snapshot 檔、pct 非 null）→ 清單/群組摘要渲染 → 確認 relation milestone-path → 標記第一個 Reached → 「重新分析」按鈕出現 → live 重跑第二劇本；result 檔重載一致；Docker 容器內載入主機工作區（經 `./workspace` 掛載）重算 parity（結構同一＋使用者可見精度，跨 libm 漂移依 v4 判例 <1e-12 接受）。無法執行處依 skill 處方模式，不得豁免。

## 審計紀錄

- **Round 1**：codex sandbox 無可執行 Python → DC 環境阻斷（非實作發現）。
- **Round 2**：Option A（embedded CPython 下載）被 sandbox 網路阻斷 → 切處方腳本模式（降低獨立性，記錄在案）；controller 代抓 python-3.13.13-embed-amd64.zip（sha256 8766a877…，codex 對 python.org 發佈頁核驗通過）。
- **Round 3**：DC 首跑失敗於 `import webapp.render` → codex 裁定為探針工件（script-dir sys.path 語意；webapp 非安裝套件屬設計）→ 修正探針。
- **Round 4**：**DC PASS**——host 3.11.9 venv 乾淨安裝＋embedded 3.13.13 乾淨安裝（get-pip bootstrap）雙 corner；import/compile/工作區自動建立/19 個 JSON parse 全過。codex 同輪依 spec §2.5 第 3 列自行反轉其 `latest_result` 檢查（容忍無事件 result 檔＝spec 明文設計）。
- **Round 5**：AC 卡在 embedded 發行版 `._pth` 隔離（test_heatmap_colors 子行程 import）→ codex 裁定審計工件，修 `._pth` 加 repo 根。
- **Round 6**：pytest 全綠但 summary 行被 Tee-Object 吞掉 → codex 改用 junitxml 機器可讀計數。
- **Round 7**：**AC PASS**——junit tests=246 failures=0 errors=0 skipped=0（embedded 3.13 執行）；獨立探針全過：寫入次序（事件先行）、提案矩陣 5 案含 bearish 鏡像、id 撞名決定性（-2/-3、92.5→92p5）、事件投影獨立重放==快取、觀察日邊界（==不過期、+1 過期）、刪除補完、latest_result 容忍語意、序列化引擎原語重算相符（mid_cost 0.5、baseline_return 2.7236…）＋手算 capital 50.0/pct 0.0005/days 17/23、capital None/0 → pct null、決定性雙跑 sha256 逐位元同（b913acec…）、紅線掃描零命中、targeted 回歸 exit 0。
- **Round 7 SL 首跑**：處方腳本逐字執行——live 建立 TLT-105-202801/TLT-115-202812、自動歸組、milestone-path 提案、live yfinance 群組分析皆執行；盤前 LEAPS 報價全過濾 → 腳本自身守衛 exit 77（`SL_MARKET_HOURS_REQUIRED`），依 codex 政策延至 NYSE 盤中（台北 21:30–04:00）重跑。與 v4 審計判例一致。

<!-- codex-audit: status=FAIL gates=DC:PASS,AC:PASS,SL:PENDING date=2026-07-21T07:40:00Z rounds=7 appeals=0 arbitrations=0 -->
