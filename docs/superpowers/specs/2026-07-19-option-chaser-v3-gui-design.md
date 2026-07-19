# Option Chaser v3 Design Spec — Web GUI（Streamlit + 共用 Application Service）

日期：2026-07-19
狀態：待審
上游文件：`Brief_v3.md`（權威產品需求）、v2 spec `2026-07-19-option-chaser-v2-design.md`（引擎現狀，已實作並通過 codex-audit）
本 spec 定義 GUI 層與服務層；核心引擎（valuation/filters/ranking/matrix 計算語意）**零行為變更**。

---

## 1. 目標與範圍

### 1.1 目標

把 v2 CLI 引擎包成極簡網頁工具：輸入標的/目標價/目標日期/策略勾選 → 一次抓取市場資料 → 同一快照分析所有勾選策略 → 跨策略比較表 + 各策略 top 3 候選 + P/L Heatmap。體驗對標 OptionsProfitCalculator，加上它缺的自動掃鏈/自動排名/同場比較。

### 1.2 使用者輸入（首頁全部內容，不再增加）

1. 標的：文字框；送出前 strip + upper + 非空檢查。
2. 目標價：正數數字框。
3. 預計到達時間：日期選擇器；必須晚於市場資料日。
4. 策略勾選（checkbox × 4）：預設 ✅Long Call ✅Bull Call Spread，☐Long Put ☐Bear Put Spread；至少勾一項。
5. 「開始分析」按鈕；分析中 disabled 防重複提交。

進階參數（iv-shifts/rate/min-oi/min-volume/spread門檻/delta-bands/min-return/top/force/snapshot/md）一律不顯示，全吃引擎預設值。第一版無進階設定面板。

### 1.3 非目標

`Brief_v3.md` §9 全清單原樣生效（無帳號/多使用者/資料庫/回測/預測/機率/AI建議/多標的/手動履約價/credit spread/裸賣/付費）。另明確：GUI 不提供 `--force`——方向不合的策略直接跳過並提示，不阻擋其他策略。

---

## 2. 架構

### 2.1 模組（新增/修改）

```
option-chaser/
├── option_chaser/
│   ├── service.py     # 新：Application Service（GUI/CLI 唯一共用入口）
│   ├── matrix.py      # 改：新增 matrix_grid()（結構化格值）；
│   │                  #     matrix_lines() 重構為「matrix_grid + 排版」，輸出逐位元不變
│   └── cli.py         # 改：main() 編排段改為呼叫 service；CLI 行為與四份 golden 逐位元不變
├── webapp/
│   └── app.py         # 新：Streamlit 單檔應用（表單/進度/結果/heatmap/錯誤對映）
├── Dockerfile         # 新
└── compose.yaml       # 新
```

依賴新增：僅 `streamlit`。Heatmap 以自產 HTML 表格呈現（`st.markdown(unsafe_allow_html=True)`），不引入 plotly/matplotlib。

硬性技術原則（Brief §7）：GUI 不得以 subprocess 呼叫 CLI、不得解析 CLI 文字輸出、不得存在任何 GUI 側重寫的金融公式；估值/過濾/配對/排名/矩陣一律經 service 呼叫既有引擎函數。

### 2.2 Application Service 契約（`service.py`，frozen dataclasses）

```python
@dataclass(frozen=True)
class AnalysisRequest:
    symbol: str                     # 已 strip+upper
    base_params: AnalysisParams     # 完整引擎參數物件（strategy 欄位在此被忽略）
    strategies: tuple[str, ...]     # 非空，元素 ∈ models.STRATEGIES；逐策略以
                                    # dataclasses.replace(base_params, strategy=s) 衍生
    # target_price/target_date 一律取自 base_params——單一事實來源，
    # GUI 以預設值建構 base_params（僅填三項輸入），CLI 把 resolve_params
    # 的完整結果原樣傳入 → CLI 全部旗標（min_expiry/top/iv_shifts/rate/
    # 流動性門檻/min_return/matrix_all/force）零回歸。
    # --snapshot 對應 run_offline()；--md 為 CLI 呈現層自理，不進 service。

@dataclass(frozen=True)
class MatrixView:
    prices: tuple[tuple[float, str], ...]   # (價格, 標記) 升冪；標記 ∈ {"","<現價>","<目標>","<現價><目標>"}
    dates: tuple[tuple[str, str], ...]      # (ISO日期, 標記) ；標記 ∈ {"","*"}；末欄=到期日
    cells: tuple[tuple[float, ...], ...]    # cells[i][j] = 報酬率（小數），列序與 prices 相同（升冪）

@dataclass(frozen=True)
class CandidateView:
    valuation: ContractValuation | SpreadValuation   # 引擎原物件，不轉譯
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    matrix: MatrixView
    baseline_pnl: float        # 估值 − 成本（Mid 口徑，每股）
    baseline_return: float     # ranking.baseline_return / spread_baseline_return
    worst_return: float        # (估值 − 最差成本) / 最差成本
    # 報酬率於 service 內以引擎函數預算，GUI 僅格式化（紅線落實）

@dataclass(frozen=True)
class StrategyResult:
    strategy: str
    status: str                     # "ok" | "skipped_direction" | "empty"
    candidates: tuple[CandidateView, ...]     # GUI 便利檢視（§3.3 定義取法）
    ranked_bands: dict[str, list[ContractValuation]] | None   # 單腿：引擎 rank() 原輸出
    ranked_spreads: tuple[SpreadValuation, ...] | None        # 價差：rank_spreads() 原輸出
    n_qualified: int                # 單腿合格數 / 價差合格組數
    filter_report: FilterReport | None
    pair_report: PairReport | None  # 價差策略才有
    report_text: str | None         # ok：service 內呼叫 report.render/render_spreads 產生；
                                    # empty：單腿 = render_filter_only 輸出、價差 =
                                    # render_spreads(空清單) 輸出（沿用 v2 空結果報告）；
                                    # skipped_direction：None。
                                    # 引擎原物件直渲染，GUI「原始文字報告」與 CLI 輸出
                                    # 共用同一來源——golden 與空結果行為保真由此結構性成立
    message: str                    # skipped/empty 時的使用者可讀說明

@dataclass(frozen=True)
class ComparisonRow:
    strategy: str
    label: str                      # 單腿: "K=110.00"; 價差: "買 110 / 賣 130"
    expiry: str
    cost: float                     # Mid 口徑每股
    baseline_return: float
    worst_return: float             # Ask/最差口徑基準報酬率
    breakeven: float
    max_profit: float | None       # 逐策略定義：long-call → None（無上限，顯示「無上限」）；
                                   # long-put → strike − Mid（每股，標的跌到 0 的上限）；
                                   # 價差 → 寬度 − 淨Mid

@dataclass(frozen=True)
class SnapshotMeta:
    symbol: str
    spot: float
    fetched_at: str
    source: str
    snapshot_path: str              # 落地檔路徑

@dataclass(frozen=True)
class AnalysisResult:
    request: AnalysisRequest                  # 原始請求（GUI 摘要需顯示劇本目標價/日期，
                                              # 結果物件自足、不依賴 session 外部狀態）
    meta: SnapshotMeta
    snapshot: ChainSnapshot                   # 引擎原物件（渲染/重算所需）
    today: date                               # snapshot_today() 結果
    results: tuple[StrategyResult, ...]       # 依 request.strategies 順序
    comparison: tuple[ComparisonRow, ...]     # 僅 status=="ok" 且有候選的策略各一列
    best_strategy: str | None                 # comparison 中 baseline_return 最高者（同分取 request 順序靠前）
```

**「最佳候選」的確定性定義（Brief §5.2）**：comparison 每列代表該策略「全體合格候選中基準情境報酬率最高者」——單腿為跨三級距的全域最大（同分沿用 v2 四層 tie-break），**不是**保守級距的第一張；價差為 rank_spreads 榜首（本身即全域降冪）。

**策略 Tab 的「前三名候選」定義（Brief §5.3）**：單腿 = 三級距各自的 #1（保守/平衡/積極首選各一張，維持 v2 風險級距語意，恰為三張；某級距空則缺位並註明）；價差 = 清單前三。CandidateView 即按此取法組裝。

```python
```

`service.run(request, progress=None) -> AnalysisResult`：

0. **請求驗證**：`strategies` 為空或含非 `models.STRATEGIES` 元素 → raise `ParamError`（不得靜默接受）。
1. `fetch_chain(symbol)` **一次**，`save_snapshot` 落地（沿用 CLI 的 snapshots/ 命名）。
2. `today = snapshot_today(fetched_at)`；驗證 `target_date > today`（否則 raise ParamError）。
3. 逐策略：方向不合（`is_bullish` 與目標價/現價關係矛盾）**且 `base_params.force` 為假** → `skipped_direction` + 說明文字，**不中斷其他策略**；`force` 為真 → 照常執行（保留 CLI `--force` 語意；GUI 永不設 force）。合格 → 既有管線（apply_filters → [generate_spread_pairs] → evaluate → rank/rank_spreads → build_reasons/build_spread_reasons）；0 合格/0 配對 → `empty` + 說明。
   **CLI 對映（行為保真）**：CLI 為單一策略 request——結果為 `skipped_direction` 時，印出既有 ParamError 格式的方向錯誤訊息並 exit 2；`empty` 時印出 `report_text` 並 exit 1；`ok` 印 `report_text` exit 0。與 v2 行為逐一對應。
4. 每候選附 `MatrixView`（§2.3）。
5. `progress: Callable[[str], None] | None`——每階段呼叫一次（抓取/過濾/各策略/heatmap），GUI 接 st.status，CLI 傳 None。
6. 另提供 `service.run_offline(request, snapshot_path, ...)` 供測試與 CLI parity（同快照重現）。

CLI 重構：`cli.main` 的資料抓取＋管線段改為呼叫 service（單一策略 request，完整 AnalysisParams 原樣傳入），輸出直接印 `StrategyResult.report_text`（service 內以 report.py 渲染——CLI 與 GUI 同一渲染來源）。**回歸鐵則：四份 v2 golden 逐位元不變；CLI 全部旗標行為不變。**

### 2.3 `matrix_grid()`（matrix.py 新函數，單一資料源）

```python
def matrix_grid(value_fn, cost, prices, dates) -> tuple[tuple[float, ...], ...]
    # cells[i][j] = (value_fn(prices[i], dates[j]) − cost) / cost   （i 依 prices 升冪）
```

`matrix_lines()` 重構為呼叫 `matrix_grid` 後純排版（reversed 顯示、`{:+.0f}%`、欄寬），輸出逐位元不變（golden 鎖定）。GUI 的 MatrixView.cells 直接取 `matrix_grid` 原始浮點值——**CLI 與 GUI 逐格同源**（Brief 驗收 #8 由此結構性成立）。

---

## 3. GUI 頁面（`webapp/app.py`，繁體中文介面）

### 3.1 首頁

產品名稱 + 一句說明（Brief §3 文案）+ 四項輸入 + 按鈕，無其他元素。輸入驗證失敗以行內錯誤顯示（不進分析）。

### 3.2 進度

`st.status` 逐步顯示（文案同 Brief §4：正在抓取…/過濾…/比較 X…/建立 Heatmap…）。按鈕於執行期間 disabled。任何內部例外 → §5 錯誤對映，永不顯示 traceback。

### 3.3 結果頁五區（Brief §5 落地）

1. **劇本摘要**：標的/現價/目標價/目標日期/資料時間（UTC標示）/來源/已比較策略清單；被跳過或空結果的策略在此列出原因一句話。
2. **跨策略比較表**：`AnalysisResult.comparison` 渲染；欄位＝策略/候選/到期日/進場成本/劇本報酬率/最差進場報酬率/Breakeven/最大獲利（一律依 `ComparisonRow.max_profit` 語意渲染：long-call 顯示「無上限」、long-put 顯示 `strike − Mid` 金額、價差顯示 `寬度 − 淨Mid` 金額——Long Put 有界，不得顯示「無上限」）；`best_strategy` 列標「最高報酬」badge；表下註明「最高報酬≠最佳投資，本系統不判斷劇本機率」。
3. **策略 Tabs**：僅顯示本次勾選者；每 Tab 依 status 呈現——ok：top 3 候選卡片（欄位清單照 Brief §5.3，單腿含 K/到期/Bid/Mid/Ask/每張成本/IV/Delta/BE/劇本估值/損益/報酬率/最差報酬率/警示；價差含兩腿/寬度/Net Mid/Natural(最差) Debit/每組成本/BE/最大虧損/最大獲利/劇本估值/損益/報酬率/最差報酬率/警示）；skipped_direction/empty：顯示 message。
4. **Heatmap**：每候選卡片附「查看 Heatmap」expander，各 Tab 第 1 名預設展開，其餘收合（§4）。
5. **計算細節 expander**：過濾統計（+價差配對統計）/IV 情境/Greeks/Lambda/買價指引/公式與模型限制/原始文字報告（直接呼叫 `report.render`／`render_spreads` 產生，`st.code` 顯示）。

### 3.4 方向不合的處理（Brief §6）

以 `is_bullish(strategy)` 對照 target vs spot：不合者 status=skipped_direction，message 例：「目標價低於目前股價，因此未執行 Long Call 與 Bull Call Spread。可改選 Long Put 或 Bear Put Spread。」其他策略照常執行。GUI 無 force。

---

## 4. Heatmap 視覺規格

- 呈現：自產 HTML `<table>`，外層 `<div style="overflow-x:auto">`（手機橫捲，Brief 驗收 #14）。
- 軸：Y=價格（由高至低顯示，即 MatrixView.prices 反轉）、X=日期；列標記「現價」「目標」、欄標記目標日期「*」與末欄「到期」。
- 格值：顯示真實報酬率 `{:+.0f}%`（與 CLI 同格式）。
- 色階：以 0% 為中心之紅（負）綠（正）雙向漸層；**顯示色彩範圍鉗制於 ±100%**（|ret|≥100% 顏色飽和，數字仍顯示真值如 +943%）；|ret| < 5% 使用中性灰。色彩函數為純函數（同格值同色，決定性）。
- 圖下說明一句（Brief §5.4 文案）。

---

## 5. 錯誤與空結果對映（GUI 全域）

| 內部例外/狀態 | 使用者訊息 |
|---|---|
| FetchError（網路/源故障） | 「目前無法取得 {symbol} 的市場資料，請稍後再試。」 |
| FetchError（無現價/無合約，視同標的不存在） | 「找不到此標的，請確認代號是否正確。」 |
| 過濾後 0 合格 / 0 配對 | 「目前沒有符合流動性與報價條件的合約。」（該策略 Tab 內顯示） |
| ParamError（日期不合法等） | 行內表單錯誤 |
| 其他未預期例外 | 「分析過程發生錯誤，請稍後再試。」（logging 記錄，畫面不露 traceback） |

FetchError 二分規則：`fetch_chain` 現有兩種訊息（抓取失敗 vs 回傳資料不足）以例外訊息內容區分對映；此為顯示層邏輯，不改引擎。

---

## 6. Docker 與部署（Brief §8）

- `Dockerfile`：`python:3.11-slim` → `pip install .`（含 streamlit）→ `streamlit run webapp/app.py`。
- `compose.yaml`：port 由環境變數 `PORT`（預設 8501）映射；volume `./snapshots:/app/snapshots`；healthcheck `GET /_stcore/health`。
- `docker compose up -d` → `http://localhost:8501`。
- 決定性要求：同 snapshot 同輸入，CLI/裸機 GUI/Docker GUI 候選排序與數值一致（Brief 驗收 #12/#13）。

---

## 7. 測試

1. **service parity（核心回歸）**：以 v2 fixture 快照 `run_offline` 四策略，候選（symbol/strike/expiry 序列）與數值（mid/baseline/return）逐一等於既有引擎直呼結果；CLI 四份 golden 逐位元不變（cli 重構回歸鎖）。
2. **matrix_grid parity**：`matrix_grid` 數值經 `{:+.0f}%` 格式化後 == `matrix_lines` 對應格文字（逐格解析比對）；`matrix_lines` 輸出與重構前逐位元相同（由 golden 覆蓋）。
3. **service 行為**：方向不合 → skipped_direction 且其他策略照跑；0 合格 → empty；strategies 空/非法 → ParamError；comparison/best_strategy 正確（含同分取序規則）。
4. **GUI（Streamlit 官方 AppTest，離線）**：表單驗證（空標的/非正數/過去日期）；以 monkeypatch 將 service.run 導向 `run_offline`+fixture → 結果頁五區元素存在（比較表/Tabs/heatmap HTML/細節 expander）；錯誤對映四類各一測；至少勾一策略的約束。
5. **Heatmap 色彩函數**：0% 中心、±100% 鉗制、|ret|<5% 中性、決定性（同值同色）。
6. **Docker**：build 成功 + healthcheck 通過（本機驗證步驟，寫入 plan 的手動段）。

## 7A. 審計覆蓋契約（codex-audit §9A 格式，設計期凍結）

- **DC**：乾淨環境 `pip install .` 含 streamlit；`webapp/app.py` 與 `option_chaser.service` import；compose.yaml/Dockerfile 語法有效；3.11/3.13 corner（既有慣例）。
- **AC**：全套件測試 codex 親自跑；service parity 與 golden 不變性驗證；matrix_grid 逐格 parity；GUI AppTest smoke；錯誤對映；方向 skip 行為；紅線掃描（無 subprocess 呼叫 CLI、無 GUI 側金融公式、無機率/LLM、網路仍僅 data/yf.py）。
- **SL**：真實 TLT 於 GUI 路徑（AppTest 或 headless 驅動）勾 Long Call+BCS 一次分析成功 → 取其落地 snapshot 以 CLI `--snapshot` 重跑 → 候選排名與數值一致（Brief 驗收 #11/#12）；`docker compose up -d` → healthcheck 綠 → 容器內完成同分析且結果一致（#13）。無法連網/無 Docker 時依 skill 處方腳本模式，不得豁免。

---

## 8. 驗收標準

`Brief_v3.md` §10 全部 14 條原樣生效，為本版驗收之唯一清單。

---

## 9. 已討論並否決／延後

- plotly/matplotlib heatmap：多依賴、樣式控制反而繞遠，HTML 表格勝出（可逆決策，後續要互動性再議）。
- 進階設定面板、`--force` in GUI、多標的比較：Brief §9/§3 明文排除。
- FastAPI+前端框架：單一使用者私人服務，Streamlit 成本低一個量級（Brief §7 已定）。

<!-- codex-peer-reviewed: 2026-07-19T11:20:31Z rounds=3 verdict=approved -->
