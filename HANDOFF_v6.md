# Option Chaser v6 交接文件（給 codex 接手）

撰寫日期：2026-07-23。撰寫者：Claude Code（本輪 SDD 控制者）。
本文件是唯一交接入口；讀完本檔後再按需要打開引用的其他檔案。

---

## 0. 一句話現況

v6「Artifact Parity」13 個任務全部實作完成、逐任務審查通過、全套件 319 綠，
**但卡在最後的硬性關卡：使用者視覺核可未通過**——使用者看了實機截圖後認為
與原始 Artifact 長相差距過大。已定位出具體落差（見 §5），使用者說「我自己先挖，
你先停」，目前等待使用者指示修哪些。**在使用者明確核可前，禁止合併到 master。**

---

## 1. 權威文件（依優先序）

1. `Brief_v4.md`（repo 根）——使用者親自口述的需求原文，最高權威。
2. `docs/superpowers/specs/2026-07-22-option-chaser-v6-design.md`——設計 spec，
   已 codex-peer-review APPROVED（檔尾有 marker）。
3. `docs/superpowers/plans/2026-07-22-option-chaser-v6.md`——13 任務實作計畫，
   內含每個檔案的完整程式碼，已 codex-peer-review APPROVED（4 輪）。
4. `.superpowers/sdd/progress.md`——SDD 執行 ledger，每個任務的 commit 範圍、
   審查結論、Minor findings 都在裡面。**信 ledger 與 git log，不要信記憶。**
5. `ui_reference/index.html`——視覺 Source of Truth 的原樣匯出（見 §4）。

## 2. Git 狀態（2026-07-23 當下）

- 分支：`feature/v6-artifact-parity`
- 分支起點（merge-base 對 master）：`43079ea`
- HEAD：`bfea927`（fix: $ 雙重跳脫 bug，見 §5.1）
- 未追蹤、未 commit：`ui_reference/`（兩個檔案，使用者已看過，尚未指示 commit）
- 工作樹除 `ui_reference/` 外乾淨。
- master 上是 v5 完成態（v5 已合併、已通過 codex-audit 三閘）。

主要 commit 序列（底→頂）：Task 1..13 各自成 commit（見 ledger），之後
`97336e3`（BAT 啟動器）→ `ef96f2b`(BAT 編碼警告) → `bfea927`（$ 跳脫修復）。

## 3. 測試與環境

- **跑測試唯一正確指令**：`rtk proxy python -m pytest -q` → 目前 **319 passed**。
  ⚠ 已知怪癖：裸 `python -m pytest` 在這台機器會 collect 到 0 顆——不是壞掉，
  一律走 `rtk proxy`。
- Python 3.11.9（`py -3`），streamlit 1.59.2，`pip install -e ".[gui]"` 已裝在
  repo 根的 `.venv`（BAT 建的）與系統環境皆可。
- 啟動 app：`OC_WORKSPACE=workspace/v6demo python -m streamlit run webapp/app.py
  --server.port 8601 --server.headless true`（PowerShell 語法：
  `$env:OC_WORKSPACE='workspace\v6demo'; ...`）。
- 頁面直連 URL（`st.navigation` 的 url_path）：`/`＝戰情總覽、`/workspace`、
  `/quick`、`/help`、`/detail?sid=<scenario_id>`（detail 是 hidden page，可路由
  不入導覽列）。

### 3.1 Demo workspace（截圖用，git-ignored）

`workspace/v6demo/` 現有 4 個劇本（由 `.audit-scratch/make_v6_demo_ws.py` 與
兩個後補腳本建立，全部用 offline fixture
`tests/fixtures/xyz_v4_six_expiries.json`，spot=$100）：

| scenario id | 用途 | 狀態 |
|---|---|---|
| `XYZ-110-202608` | Reached 示範、G-XYZ 群組成員 | 預設候選 Long Call |
| `XYZ-120-202609` | Active 示範、G-XYZ 群組成員 | 預設候選 Long Call |
| `XYZ-118-202608` | **封頂區示範**（只分析 bull-call-spread） | 預設候選 BCS，詳頁可見「收益封頂」「最大獲利區」欄與分隔線 |
| `XYZ-85-202608` | BPS 鏡像示範（失敗） | **無候選**——fixture 完全沒有 put 合約，BPS/long-put 永遠空手。BPS 封頂邏輯只有單元測試 `tests/test_render_cap.py::test_bps_caps_at_and_below_cap_price` 覆蓋，沒有實機截圖 |

⚠ fixture 無 put 合約是資料限制：若要實機驗 BPS，需手刻含 put 的 fixture。

### 3.2 截圖工具（重要教訓）

- **一律用 gstack 隔離 headless Chromium**：`~/.claude/skills/gstack/browse/dist/browse`
  （bash 環境需 `export PATH="/c/Program Files/nodejs:$PATH"`）。
  **絕對不要碰使用者的真實 Chrome**——Task 13 實測時曾誤殺使用者整個 Chrome
  （所有分頁遺失，已向使用者道歉，使用者未回覆是否有損失）。
- browse daemon 會不定時自己重啟（session 歸零、viewport 重設、`@eN` ref 全部
  失效）。對策：**別依賴 snapshot ref 導航，直接 `goto` 上面的直連 URL**；每次
  截圖前重新 `viewport`。
- 檔案存取白名單只有 repo 目錄與 `C:\Users\Rice\AppData\Local\Temp`，開本機
  HTML 要先複製到 scratchpad。

## 4. `ui_reference/`——視覺基準的原樣匯出

使用者指定的視覺基準 Artifact：
`https://claude.ai/code/artifact/bca2c75f-453c-40f0-9c56-d726b17b3d69`
（「Option Chaser v5 — 即時資料驗證快照」，使用者親口確認「這份啊」）。

- `ui_reference/index.html`：其完整原始 HTML，逐位元組複製（sha256
  `f7c696c70a3a499d77d630eea790f3085b9ee4b693179853e189f04642082f77`），未編輯。
- `ui_reference/README.md`：來源、驗證、啟動方式。
- **技術真相**：這份 Artifact 是單一自包含靜態 HTML——無外部資源、無框架、無
  package.json/lockfile/components（已 grep 全文證實）。開頭那段 minified
  `<script>` 是 claude.ai 平台注入的 iframe 沙盒橋接碼，不是 mockup 本身的程式。
  已實測 `file://` 獨立開啟正常渲染、console 零錯誤。
- **未整合**：使用者明示暫不與 Streamlit 整合，只作對照 ground truth。

⚠ **陷阱警告**：使用者帳號還有另一份 Artifact（`e30c61ff...`，「v4 — 結果頁
Mockup」，深藍綠主色 `#2f6b5e`、單欄無側欄版面）。**那份不是基準**。我曾誤把
它當基準改了一輪 theme token 又全部 revert（未留 commit，工作樹已還原）。
現行 `webapp/theme.py` 的 token（bg `#eef0f3`、chrome `#f3f4f6`、accent
`#ff4b4b`、pos `#1a7f37`、neg `#b22222`…）與正確基準 `bca2c75f` 的 `:root`
**逐值相符**，不要再動 token 值，除非使用者指示。

## 5. 視覺核可回合：已修的與待決的

### 5.1 已修：`$` 雙重跳脫 bug（commit `bfea927`）

實機截圖抓到所有金額顯示成字面 `\$110.00`。根因：`components.py` 卡片函式與
`render.py` 的 `heatmap_html`/`comparison_table_html` 回傳的是**完整 HTML block**
（`<div>` 開頭），經 `st.markdown(..., unsafe_allow_html=True)` 輸出時依
CommonMark 規則不再做行內 markdown 解析，所以 `esc()`（`$`→`\$`，防 LaTeX
誤判）在這些路徑沒有任何東西把它還原，反斜線原樣上屏。修法：這些 HTML-block
路徑移除 `esc()`；`render.py` 其餘**純 markdown 文字路徑**（render_summary 的
chips、greeks 行等）的 `esc()` 保留且必要。相應測試斷言已同步更新
（`tests/test_render_cap.py` 改斷言未跳脫字面）。

**慣例（後續改動必守）**：回傳值是完整 HTML block → 不 esc()；會被當 markdown
行內解析的字串 → 必須 esc()。`components.py` 與 `render.py::heatmap_html` 檔頭
docstring 有完整說明。

### 5.2 已確認、待使用者拍板的三個落差（對照 `ui_reference/index.html`）

1. **詳頁缺 Step 3 縮圖比較（最明確的功能遺漏）**：
   `webapp/views/detail.py:14` import 了 `render_step3` 但**從未呼叫**（77 行
   `render_step2` 之後直接跳 79 行 `comparison_table_html`）。mockup 詳頁的
   Step 3——每候選一列：🚀🛡️⚠ badge＋4×5 彩色縮圖＋四個帶下劃線標籤的指標欄＋
   「選看」按鈕切換上方主圖——整套不存在於實際頁面。`render_step3` 函式本身
   完好（quick.py 有用），理論上加一行 `render_step3(view, key)` 加上 selected
   key 的 session_state 接線即可，但**先別動**：使用者說要自己先研究。
   注意：若補回，需決定 13 欄 `comparison_table_html` 與 Step 3 是否並存
   （mockup 兩者皆有：Step 3 在 app 視窗內、13 欄明細表在「外部驗證表」視窗）。
2. **工作區劇本卡樣式**：mockup 是緊湊單行 row（`.scen`/`.scenrow`：細分隔線、
   一行排 symbol/方向/價格/日期/狀態膠囊/group/佔本金%/最佳候選摘要，行內小
   按鈕「分析/詳頁」），現實作是大張 `.oc-card` 白卡＋卡下獨立一排 st.columns
   按鈕，垂直空間耗費大、觀感差異最直觀。重排屬純樣式工作，但按鈕行內化受
   Streamlit 元件模型限制（st.button 無法塞進自訂 HTML row），需要設計取捨。
3. **側欄**：mockup 窄（176px）純文字、選中項粉紅底紅字；現為 Streamlit 原生
   側欄（寬、有 emoji icon、選中灰底）。完全比照需覆寫 Streamlit 內部 DOM，
   **牴觸紅線**（見 §6），只能有限貼近或請使用者豁免紅線。

已與基準相符、不要動的：heatmap 色階（`cell_color` 的 `#228b22`/`#b22222`
連續色階與 mockup 逐格一致）、theme token 值、頁面/卡片底色、膠囊樣式、
封頂區標示（BCS 實機驗證通過）。

### 5.3 視覺核可流程要求（硬性）

spec §12.7／brief §14.7：交付「Artifact vs 實際 App 逐頁差異表（每項標
已還原/合理調整/尚未完成）＋桌機 1280px 與手機 390px 實機截圖」→
**使用者明確核可後才可合併**。第一輪差異表已交付過（使用者不滿意），修完後
需重新交付完整一輪。

## 6. 紅線（違反任一條 = 審查直接打回）

1. 引擎（`option_chaser/service.py` 及以下）零修改；`store.py` 僅 v6 已加的
   serialize v2 欄位；`workspace.py` 僅已加的 `adopt_result`/`scenario_exists`。
2. GUI 零金融公式：所有顯示數字取自 `serialize_result` 預算好的 dict 欄位，
   views/components/render 只做格式化與展示層比較。
3. 自訂 CSS 只准 `.oc-` 前綴類別（`.st-key-` 例外），**不得選取 Streamlit 內部
   DOM**（`.stButton`、`[data-testid=...]`）——`tests/test_theme.py` 有自動化
   守門。若使用者為了側欄樣式決定放寬此線，必須同步改該測試並在 spec 記錄。
4. 機率禁詞（獲利機率/POP/期望值/Sharpe/勝率…）全域禁止，`tests/test_redlines.py`
   的 TARGETS 掃描所有 webapp 檔案。
5. 使用者輸入（symbol/notes/group_id）注入 HTML 前必過 `html.escape`（
   components.py 的 `_h()`）。
6. v1 舊 result 檔（schema_version 1）缺 v2 新欄：一律 `.get()` 降級顯示 `—` 與
   `LEGACY_RESULT_MESSAGE`，不得 KeyError。
7. `啟動 Option Chaser.bat`／`建立桌面捷徑.bat` 是 **cp950 (Big5) + CRLF**，
   **絕不可重存成 UTF-8**（檔內與 `.superpowers/sdd/task-13-report.md` 有完整
   bisection 證據：這台 cp950 機器上 UTF-8＋chcp 65001 會被 cmd.exe 解析爛）。
   git blob 存 LF 是 `core.autocrlf=true` 正常行為，checkout 會還原 CRLF，已驗證。

## 7. 接手後的建議路徑

1. 先等/先問使用者：他們正在自己研究落差（§5.2），可能回來指定修哪幾項。
2. 若使用者指示修 §5.2：逐項小 commit、每項改動跑全套件、改視覺後用 §3.2 的
   隔離瀏覽器重截 desktop+mobile。
3. 修完 → 重建 §5.3 的完整差異表＋截圖包 → 交使用者核可。
4. 核可後：merge 到 master（沿用 v5 模式：merge commit＋master 上全套件複跑）。
5. merge 後使用者慣例會要求 codex-audit（DC→AC→SL 三閘；spec §11A 有凍結的
   覆蓋契約，SL 需要 BAT 冷啟動＋真實 TLT/ORCL 劇本＋Chromium 截圖）。

## 8. 其他未結事項

- `ui_reference/` 未 commit——等使用者指示。
- 使用者尚未回覆「Chrome 被誤關有沒有損失」。
- `workspace/v6demo` 與 `.audit-scratch/` 都是 git-ignored 暫存，截圖完可清，
  但目前留著（使用者可能還要看）。
- 現在沒有任何 streamlit/瀏覽器背景程序在跑（port 8601 已釋放）。
