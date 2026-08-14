"""Production 診斷探測——單一 (symbol, date, expiration) 的 Market Data
App 歷史鏈請求，逐站回報使用者要求的十個欄位。

**這支腳本不修任何 Historical IV 演算法**，只是把
`option_chaser/data/marketdata.py`／`api_app/storage/` 已有的真實函式
串起來、在每一站插入觀測點——URL 組法、payload 解析、SurfacePoint
轉換、DB 寫入全部呼叫 production 原函式，零重新實作、零 mock。

**執行環境要求（本腳本無法在這個沙箱跑出真實結果）**：
- 需要能連到 `api.marketdata.app` 的網路出口（本沙箱對該網域出站一律
  CONNECT 403，這是沙箱代理政策，與 production／Vercel 的連線能力無關）
- 需要一把真實、已驗證可用的 Market Data App token（`MARKETDATA_TOKEN`
  環境變數）——不得用測試用的假 token，那只會在站 2 就直接 401
- 步驟 9／10（DB 寫入驗證）需要 production 的 Postgres 連線字串
  （`DATABASE_URL`／`POSTGRES_URL`／`POSTGRES_PRISMA_URL` 等，
  `api_app/storage/factory.py` 認得的任一個都行）；沒有的話這兩步會
  明確標示「跳過」，不會假裝驗證過

**用法**：

    MARKETDATA_TOKEN=xxx python scripts/probe_production_iv_chain.py \\
        --symbol TLT --date 2025-09-15 --expiration 2028-06-16

    # 若要一併驗證 DB 寫入（步驟 9／10），另外提供連線字串，例如：
    MARKETDATA_TOKEN=xxx DATABASE_URL=postgres://... \\
        python scripts/probe_production_iv_chain.py \\
        --symbol TLT --date 2025-09-15 --expiration 2028-06-16

跑在哪裡都行，只要那個環境的出站網路真的到得了
`api.marketdata.app`——本機、有真實網路出口的 CI runner（本 repo
既有 `tmp-*.yml` 一次性工作流慣例）、或任何跑得了 Python 且能連網
的地方。**輸出直接複製貼回即可**，token 已在印出的 URL 裡遮蔽。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 全部從 production 模組原樣匯入——URL 組法、payload 解析、SurfacePoint
# 轉換一個字元都不重寫，避免探測腳本本身的邏輯跟正式路徑漂移，變成在
# 驗證一支別的程式。
from option_chaser.data.marketdata import (  # noqa: E402
    _HISTORICAL_CHAIN_URL, _rows, map_surface_payload)

_TIMEOUT_SECONDS = 15.0


def _redact(url: str) -> str:
    """輸出用：URL 本身不含 token（Market Data App 的認證是
    `Authorization: Bearer` header，不是 query string），所以這裡其實
    不需要遮蔽任何東西——但仍防呆一次，若未來哪個 adapter 改成 URL 帶
    金鑰，這裡會攔下來，不會不小心把它印到終端機。"""
    if "token=" in url.lower():
        import re
        return re.sub(r"(?i)token=[^&]+", "token=***REDACTED***", url)
    return url


def _header(headers, name: str) -> str | None:
    """HTTP header 大小寫不拘（RFC 7230）——`http.client.HTTPMessage`
    本身就是大小寫不敏感的，這裡直接用它的 get。"""
    return headers.get(name)


def stage(n: int, title: str) -> None:
    print(f"\n{'=' * 60}\n【站 {n}】{title}\n{'=' * 60}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD，要探測的歷史日期")
    ap.add_argument("--expiration", default=None,
                    help="YYYY-MM-DD，可留空測試不帶 expiration 篩選的預設行為")
    args = ap.parse_args()

    token = os.environ.get("MARKETDATA_TOKEN")
    if not token:
        print("FATAL：MARKETDATA_TOKEN 環境變數未設定——這支腳本需要一把"
             "真實、已在 production 驗證過的 Market Data App token 才能"
             "跑出有意義的結果，不能用假值代替。中止。", file=sys.stderr)
        sys.exit(1)

    url = _HISTORICAL_CHAIN_URL.format(symbol=args.symbol.upper(), date=args.date)
    if args.expiration:
        url += f"&expiration={args.expiration}"

    # ---------- 1. 最終送出的完整 URL ----------
    stage(1, "最終送出的完整 URL（token 遮蔽）")
    print(_redact(url))
    print("（token 不在 URL 裡，走 Authorization: Bearer header——上面這行"
         "就是完整送出的請求目標，沒有東西被藏起來）")

    req = Request(url, headers={"Authorization": f"Bearer {token}",
                                "User-Agent": "option-chaser-diagnostic-probe",
                                "Accept": "application/json"})

    status: int
    headers = None
    raw_body = ""
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            status = resp.status
            headers = resp.headers
            raw_body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        # HTTPError 本身就是一個可讀的 response——4xx/5xx 一樣要把
        # status／headers／body 全部撈出來，不能因為是錯誤狀態碼就
        # 少報一半的證據。
        status = e.code
        headers = e.headers
        raw_body = e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — 診斷腳本要看到「連不上」本身
        stage(2, "HTTP status")
        print(f"連線層失敗，連 HTTP status 都沒有——{type(e).__name__}: {e}")
        print("\n這代表第一筆資料在【站 2：對外連線本身】就從 N 筆變成 0 筆"
             "——不是 vendor 回應內容的問題，是這個執行環境連請求都送不出去"
             "（DNS／TLS／逾時／網路政策皆有可能，訊息已印在上面）。")
        sys.exit(2)

    # ---------- 2. HTTP status ----------
    stage(2, "HTTP status")
    print(status)

    # ---------- 3. response body 的 status / errmsg / row count ----------
    stage(3, "response body：status／errmsg／row count")
    try:
        payload = json.loads(raw_body)
    except Exception as e:  # noqa: BLE001
        print(f"body 不是合法 JSON——{type(e).__name__}: {e}")
        print(f"原始 body（前 500 字）：{raw_body[:500]!r}")
        print("\n第一筆資料在【站 3：JSON 解析】就從 N 筆變成 0 筆——vendor "
             "回了 HTTP 200／4xx 但 body 本身解析不出來。")
        sys.exit(3)

    body_status = payload.get("s")
    errmsg = payload.get("errmsg")
    raw_rows = _rows(payload)   # production 原函式，欄狀 JSON → 逐筆 dict
    print(f"s (status)   = {body_status!r}")
    print(f"errmsg       = {errmsg!r}")
    print(f"raw row 數   = {len(raw_rows)}   "
         "（_rows() 依 optionSymbol 陣列長度算出，production 解析用的"
         "同一個函式）")
    if raw_rows[:1]:
        print(f"第一筆 raw row 的欄位（供核對 wire format 是否符合預期）：")
        print(json.dumps(raw_rows[0], indent=2, ensure_ascii=False, default=str))

    # ---------- 4/5/6. Rate limit headers ----------
    stage(4, "Rate limit headers")
    for name in ("X-Api-Ratelimit-Limit", "X-Api-Ratelimit-Remaining",
                "X-Api-Ratelimit-Consumed"):
        print(f"{name} = {_header(headers, name)!r}")
    print("（若三個都是 None：這個 vendor／這個端點可能不回這組 header，"
         "不代表請求本身失敗——vendor 端點不一定統一都帶額度 header，"
         "以上面【站 3】的 s／errmsg 為準判斷是否真的額度用盡）")

    # ---------- 7/8. parser 前後筆數 ----------
    stage(7, "parser 前（raw row）／parser 後（SurfacePoint）筆數")
    print(f"parser 前（raw row，同站 3 的 raw row 數）＝ {len(raw_rows)}")
    try:
        surface = map_surface_payload(payload)   # production 原函式
    except Exception as e:  # noqa: BLE001
        print(f"map_surface_payload() 拋出例外——{type(e).__name__}: {e}")
        print("\n第一筆資料在【站 7：map_surface_payload()】就從 N 筆變成 "
             "0 筆——production 的 parser 本身對這份真實回應解析失敗，"
             "不是網路或額度問題。")
        sys.exit(7)
    call_n, put_n = len(surface.get("call") or []), len(surface.get("put") or [])
    print(f"parser 後（SurfacePoint，call）＝ {call_n}")
    print(f"parser 後（SurfacePoint，put） ＝ {put_n}")
    print(f"parser 後（SurfacePoint，合計）＝ {call_n + put_n}")
    if len(raw_rows) > 0 and call_n + put_n == 0:
        print("\n⚠ raw row > 0 但 SurfacePoint = 0——第一筆資料在【站 7："
             "map_surface_payload() 內部的 delta/iv/dte 缺值過濾】從 N 筆"
             "變成 0 筆。上面印出的第一筆 raw row 欄位，逐一核對 'delta'／"
             "'iv'／'dte' 三個 key 是否存在、是否為 None——production 的"
             "邏輯是這三者任一缺席就整筆跳過（不補零、不外插）。")

    # ---------- 9/10. DB 寫入驗證 ----------
    stage(9, "save_iv_observation 是否真的寫入 DB")
    try:
        from api_app.storage import IvObservation
        from api_app.storage.factory import database_url, storage_from_env
    except Exception as e:  # noqa: BLE001
        print(f"無法載入 storage 模組——{type(e).__name__}: {e}")
        sys.exit(9)

    dsn = database_url()
    if not dsn:
        print("跳過——這個執行環境沒有 DATABASE_URL／POSTGRES_URL／"
             "POSTGRES_PRISMA_URL 等任一個 production 認得的連線字串"
             "（見 api_app/storage/factory.py 的優先序）。這一步需要"
             "production 的真實 Postgres 連線字串才能驗證——沒有就是"
             "沒有，不假裝驗證過。")
        print("\n【站 10】無法定位——DB 寫入這一步沒有執行，見上。")
        return

    if call_n + put_n == 0:
        print("SurfacePoint 合計為 0——production 的 `_backfill_iv()` 在"
             "這個情況下會把這一天的合約併入 `merged`（可能是空的 "
             "{'call': [], 'put': []}），仍然呼叫一次 save_iv_observation"
             "（除非站 3 的 s 是會拋 FetchError／QuotaExhausted 的狀態，"
             "那種情況根本不會走到寫入這一步——見上面站 3／4 的結果判斷"
             "是哪一種）。這裡仍然實際呼叫一次寫入，如實回報結果。")

    storage = storage_from_env()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    surface_rows = {side: [[p.dte, p.delta, p.iv] for p in points]
                    for side, points in surface.items()}
    try:
        storage.save_iv_observation(IvObservation(
            symbol=args.symbol.upper(), observed_on=args.date,
            surface=surface_rows, fetched_at=fetched_at))
    except Exception as e:  # noqa: BLE001
        print(f"save_iv_observation() 拋出例外——{type(e).__name__}: {e}")
        print("\n第一筆資料在【站 9：save_iv_observation() 寫入 DB】"
             "就從 N 筆變成 0 筆——不是 vendor／parser 的問題，是"
             "production 的 DB 寫入本身失敗（連線、schema、權限皆有可能，"
             "例外訊息如上）。")
        sys.exit(9)

    readback = [o for o in storage.iv_observations(args.symbol.upper())
               if o.observed_on == args.date]
    if not readback:
        print("寫入呼叫沒有拋例外，但讀回時這一天完全不存在。")
        print("\n【站 10】第一筆資料在【站 9：寫入後的持久化】從 N 筆變成 "
             "0 筆——寫入呼叫『看起來』成功但資料沒有真的留下來（例如"
             "連到了錯的資料庫、交易沒有 commit、或這個 symbol/date 的"
             "鍵值跟預期不一致）。")
    else:
        got = readback[0]
        got_call = len(got.surface.get("call") or [])
        got_put = len(got.surface.get("put") or [])
        print(f"讀回成功：symbol={got.symbol}, observed_on={got.observed_on}, "
             f"call={got_call}, put={got_put}, fetched_at={got.fetched_at}")
        if got_call + got_put == call_n + put_n:
            print("\n✅ 寫入與讀回筆數一致——DB 這一站沒有斷。若這次探測的"
                 "合計 SurfacePoint 是 0，那麼第一筆資料是在【站 7 之前】"
                 "（vendor 回應本身或 parser 過濾）就已經是 0，DB 只是"
                 "如實記錄了『這天沒有可比座標』，不是 DB 弄丟資料。")
        else:
            print(f"\n⚠ 寫入時是 {call_n + put_n} 筆，讀回卻是 "
                 f"{got_call + got_put} 筆——筆數不一致，需要人工檢查"
                 "surface 序列化／反序列化（_surface_to_rows／"
                 "_rows_to_surface，api_app/main.py）是否有損耗。")


if __name__ == "__main__":
    main()
