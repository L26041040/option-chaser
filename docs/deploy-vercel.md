# Vercel 部署（新前端輪，V1／#48；V10／#58 Cutover 後為唯一前端）

新前端是 **Vercel 整包**：靜態前端（Vite＋React＋TypeScript）＋Python
serverless API（FastAPI，直接 import 既有 `option_chaser/` 引擎）。舊
Streamlit 前端（`webapp/`）已於 V10（#58）移除，本文件描述的架構是
唯一的正式前端。

## 一次性設定（需求方操作）

1. 到 <https://vercel.com/new> 匯入 GitHub repo `L26041040/option-chaser`
2. Framework Preset 應自動偵測為 **Vite**；Root Directory 保持 repo 根目錄
3. 按 Deploy

Vercel 會自動：

- `npm install` → `npm run build` → 靜態檔輸出到 `dist/`
- 依 `pyproject.toml` 安裝 Python 依賴，把 `api/index.py` 部署成
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

### 路由：單一函式＋catch-all rewrite

`vercel.json` 把 `/api/(.*)` 全部 rewrite 到唯一的函式 `api/index.py`，
由 FastAPI 依**原始路徑**自己路由。這點是實測確認的（2026-08-03）：
對 `/api/probe/scenarios/abc/archive` 打進來時，app 回的是 FastAPI 自己
的 404 而不是 rewrite 目的地的 200，證明 ASGI 收到的是原始路徑。因此
動態路徑（`/api/scenarios/{id}/archive`）可以正常運作，不需要為每條
路由各開一個檔案。

## 接上 Neon Postgres（V2／#50，需求方操作一次）

劇本資料要跨裝置、跨重新部署存活，需要一個雲端資料庫。用 Vercel
Marketplace 的 Neon 免費層，全程在 Vercel 後台點：

1. 打開專案 → 上方 **Storage** 分頁
2. **Create Database** → 選 **Neon**（Serverless Postgres）
3. 方案選 **Free**，Region 選離 Function 近的（本專案函式在 `iad1`
   ＝ US East，資料庫也挑 US East 可省往返時間）
4. 建立時會要你授權 Neon 存取這個 Vercel 專案——按同意
5. 建好後在 **Connect Project** 把它連到 `option-chaser` 專案，
   Environment 三個（Production／Preview／Development）都勾

連好之後 Vercel 會自動把連線字串注入成環境變數（`DATABASE_URL`、
`POSTGRES_URL`、`POSTGRES_PRISMA_URL` 等數個別名），**不需要手動貼**。
程式會依序找這些變數（見 `api_app/storage/factory.py`），優先用連線池
端點——serverless 每次請求開新連線，走 pooler 才不會把連線數用光。

### 確認接上了沒

打 `/api/health`，看 `storage` 欄位：

- **`postgres`** ＝ 接上了，資料會存活
- **`memory`** ＝ 環境變數沒讀到，資料**存在函式記憶體裡、隨時消失**。
  這是刻意讓它「看得見」而不是靜默丟資料——看到這個就回去檢查
  Connect Project 有沒有把三個 Environment 都勾到。

⚠ 注入環境變數後要**重新部署一次**才會生效（環境變數是建置時綁定的）。

### 跨重啟存活驗證

1. `POST /api/scenarios`（body：`{"symbol":"TLT","target_price":120,
   "target_month":"2028-05"}`）建立一筆
2. 在 Vercel 後台 **Redeploy**
3. `GET /api/scenarios` ——那筆還在＝驗證通過

## Treasury Cron 預熱（SCALE-07／#257，需求方操作一次，選用）

`vercel.json` 已設一個每個交易日 UTC 11:00（約美東早上 6-7 點，視
夏令時）的 Cron，打 `GET /api/cron/warm-rate-cache`，把當天的利率
曲線快取先填新——目的是讓當天第一個真正的使用者不必自己承擔一次
Treasury 冷抓取；**這只是預熱，不是必要條件**——不設定
`CRON_SECRET`、或整個停用 Cron，既有的同步 refresh-on-miss（第一次
真正分析時自己觸發抓取）完全不受影響。

要讓這個端點真的驗證授權（**強烈建議**，否則任何人都能觸發它）：

1. 專案 → **Settings** → **Environment Variables**
2. 新增 `CRON_SECRET`，值設一個隨機字串，三個 Environment 都勾
3. 重新部署一次（環境變數是建置時綁定的）

Vercel 排程觸發 Cron 時會自動帶上
`Authorization: Bearer <CRON_SECRET>`——不需要另外設定 header。
`CRON_SECRET` 沒設時這個端點對任何請求一律回 401（fail-closed），
不會變成一個誰都打得通的公開端點。

停用／回退：把 `vercel.json` 的 `crons` 區塊整段刪掉即可，行為退回
純 cache-aside（既有同步路徑），零風險。

## S0 最小可觀測性 ＋ 三層角色模型（SCALE-08／#258、spec #307，
需求方操作一次，選用但強烈建議）

`GET /api/ops/metrics` 回答最小運維指標（chain 抓取次數／429
次數／利率股利陳舊備援次數／Treasury 與股利冷抓取次數／刷新耗時／
`results`／`snapshots` 兩表大小與列數／`/history` 讀取量／PB-08
匿名擁有者清理量體＋PB-11 匿名擁有者分佈與 alert 判準），供
rollout 前後比較與未來 chain 共用決策（EG-1）取證用，**不對一般
使用者開放**。這個端點與 Settings 頁的自訂 provider token 設定
（PUT／測試連線／清除，見下方）由同一組**軸二（User Level）**
機制把關——三層角色模型（Normal ＜ Super User ＜ Super Admin，
spec #307），本站唯一的登入入口是 `POST /api/auth/login`。要讓這一層
真的生效：

1. 專案 → **Settings** → **Environment Variables**
2. 新增 `SUPERADMIN_PASSWORD`，值設一個 Owner 自己記得住的字串
   （跟 `CRON_SECRET` 用不同的值——兩者是不同的信任邊界，一個是
   Vercel 排程系統，一個是人類 Owner，輪替其中一把不該連帶影響
   另一把），三個 Environment 都勾
3. 選用：新增 `SUPERUSER_PASSWORD`（較窄的日常角色，能用 Historical
   IV、不受 Scenario 額度／刷新節流限制，但看不到 `/api/ops/metrics`
   與跨 owner 管理面板）——不設定就沒有人能以這一層登入，不影響
   Super Admin
4. 重新部署一次

登入方式：`curl -c cookies.txt -X POST -H 'Content-Type:
application/json' -d '{"password":"<SUPERADMIN_PASSWORD>"}'
https://<部署網址>/api/auth/login`，回應 `{"role":"superadmin"}`
並在 `cookies.txt` 存下持久的角色 session cookie；接著
`curl -b cookies.txt https://<部署網址>/api/ops/metrics` 即可查詢。
兩把密碼皆未設定，或帶錯密碼，`/api/auth/login` 一律回 401，
`/api/ops/metrics` 對任何沒有有效角色 session 的請求也一律回 401
（fail-closed）。

⚠ **`OPS_SECRET`（PB-09／#298）與後來取代它的 `ADMIN_SECRET`（同票）
皆已於 AUTH-03（#310，Anonymous Public Beta 三層角色模型）正式
退役**，由上面的 `SUPERADMIN_PASSWORD` 取代——若專案上還留著這兩個
舊環境變數，可以直接刪除，它們已經沒有任何程式碼在讀取，留著不會
造成安全問題，純粹是死配置。`SUPERUSER_PASSWORD`／
`SUPERADMIN_PASSWORD` 兩把密碼皆無輪替偵測機制：換掉環境變數重新
部署後，既有、尚未登出的角色 session 依然有效（Owner 明確裁示）。

停用／回退：把 `enable_metrics=False` 傳進 `create_app()`（`api/
index.py`）即可，整組觀測記錄變成 no-op；已經寫進 `operational_
metrics` 表的資料不影響任何產品資料，可保留或清空。這個開關與
`SUPERADMIN_PASSWORD` 是否設定無關——即使停用觀測記錄，Super Admin
角色仍然守著自訂 provider token 的讀寫路徑。

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
500。本機開發（CLI／pytest）仍由 `pyproject.toml` 的 `yf` extra 安裝
完整降級鏈。

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

儲存層的 Postgres adapter 要對**真的資料庫**驗證才算數（記憶體假體
綠燈不能代表正式環境成立）。本機起一個 PG 再跑：

```bash
PGBIN=/usr/lib/postgresql/16/bin        # 依實際版本調整
PGDATA=/var/lib/postgresql/ocdata
mkdir -p $PGDATA && chown postgres:postgres $PGDATA && chmod 700 $PGDATA
su -s /bin/sh postgres -c "$PGBIN/initdb -U postgres -A trust -D $PGDATA"
su -s /bin/sh postgres -c "$PGBIN/pg_ctl -D $PGDATA -o '-p 55432 -k /tmp' -l /tmp/pg.log start"

OC_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/postgres \
  PYTHONPATH=. .venv/bin/python -m pytest tests/test_storage_contract.py
```

沒設 `OC_TEST_DATABASE_URL` 時 Postgres 那組會跳過（測試輸出會寫明
跳過原因）——記憶體那組仍會跑，但**Postgres adapter 等於沒被驗證**。

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
