# Vercel 部署（新前端輪，V1／#48）

新前端是 **Vercel 整包**：靜態前端（Vite＋React＋TypeScript）＋Python
serverless API（FastAPI，直接 import 既有 `option_chaser/` 引擎）。

## 一次性設定（需求方操作）

1. 到 <https://vercel.com/new> 匯入 GitHub repo `L26041040/option-chaser`
2. Framework Preset 應自動偵測為 **Vite**；Root Directory 保持 repo 根目錄
3. 按 Deploy

Vercel 會自動：

- `npm install` → `npm run build` → 靜態檔輸出到 `dist/`
- 以 `requirements.txt` 安裝 Python 依賴，把 `api/*.py` 各自部署成
  serverless function（`vercel.json` 設 `maxDuration: 60`，一次分析的
  抓鏈＋計算要在這個時限內完成）

之後每次 push 到 master 就自動重新部署。

### ⚠ 專案模式必須是 Vite，不能是「Python 後端框架」

`vercel.json` 的 `"framework": "vite"` 是必要的，且 `pyproject.toml`
**不可以**有 `[tool.vercel]` 區段。實測過的坑（2026-08-02）：加上
`[tool.vercel] entrypoint` 之後，Vercel 把整個專案判定成 Python 後端
框架——build log 只剩 `Installing required dependencies from
pyproject.toml`，完全不跑 npm/vite build（前端根本沒被建置），而且
依賴改從 `pyproject.toml` 裝（那裡沒有 fastapi），函式啟動即
`FUNCTION_INVOCATION_FAILED`。

路由靠檔名對齊、不靠 rewrite：`api/analyze.py` ＝ `/api/analyze`、
`api/health.py` ＝ `/api/health`，與 FastAPI 內部的路由路徑一致。
（rewrite 送給函式的究竟是原始路徑還是改寫後路徑，在不同專案模式下
行為不同，靠檔名對齊可完全避開這個不確定性。）

## 部署後的第一件事：確認 Cboe 可達性

開部署網址 → 按「跑一次分析」→ 看卡片最下面那行「資料來源」：

- **`cboe`** ＝ Vercel 出口打得到 `cdn.cboe.com`，主資料源生效
  （盤外報價凍結不歸零，FB3-01／#44 的修正在雲端也成立）
- **`yfinance`** ＝ 打不到 Cboe，走了備援
- **502「Cboe 抓取失敗且備援不可用」** ＝ 打不到 Cboe，而 serverless
  上刻意沒裝 yfinance（見下），此時需要改走別的資料源方案

這一行就是 V1 驗收清單裡「Cboe 可達性已實測」的驗證方式。

## 為什麼 serverless 上沒有 yfinance

`requirements.txt` 刻意只裝 `fastapi`：yfinance 帶 pandas/numpy，塞進
函式體積不划算，而主資料源 Cboe adapter 是 stdlib-only。Cboe 不可用時
`service.fetch_chain` 會如實回報「兩層都不可用」（HTTP 502），不會崩成
500。本機開發與舊 Streamlit 版仍由 `pyproject.toml` 安裝完整降級鏈。

## 本機開發

```bash
npm install
npm run dev          # 前端 http://localhost:5173
```

前端測試與型別：

```bash
npm run typecheck    # tsc --noEmit
npm test             # Vitest 元件測試
npm run e2e          # Playwright E2E（手機 viewport）
```

後端（API 契約測試走 pytest，與引擎測試同一套）：

```bash
PYTHONPATH=. .venv/bin/python -m pytest
```

> 沙箱／CI 若已預先安裝 Chromium，用
> `PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium npm run e2e`
> 指定執行檔，避免 Playwright 另外下載。

## 契約樣本

`contracts/analysis_sample.json` 是**前端 mock 與後端 fixture 共用的
同一份** API 樣本。契約變動時：

```bash
PYTHONPATH=. .venv/bin/python scripts/gen_contract_sample.py
```

後端 `tests/test_api_analyze.py` 會斷言 API 實際回應等於這份樣本——
忘記重產就會紅燈，前後端因此不會各說各話。
