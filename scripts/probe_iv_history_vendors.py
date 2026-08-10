#!/usr/bin/env python
"""#111（決策 B1）：IV 歷史 vendor 三步近零成本驗證——探測腳本。

**這支腳本本身不能在本 repo 的 agent 沙箱跑**——沙箱出口政策封鎖
`www.marketdata.app`／`www.alphavantage.co`／`api.orats.io` 這三個網域
（已用 curl 直接驗證，見下方「沙箱驗證紀錄」）。這是沙箱代理層的政策，
不代表 Vercel production 或需求方本機打不到，兩件事不可混為一談
（本 repo 一貫的誠實揭露紀律）。

**驗證優先序**（`docs/research/historical-options-iv-data-sources.md`
§5 已定案，本腳本按此順序探測，三者皆免費或近免費）：

    ① Market Data App 免費層（確認 credit 扣法與實際回溯年限）
    → ② Alpha Vantage 免費金鑰（HISTORICAL_OPTIONS，兩輪研究共同的
      懸案——免費層資格傳聞矛盾，需要一次真實呼叫定案）
    → ③ ORATS（token 認證，付費為主，僅在①②都不可行時才需要）

**用法**：在可連網環境，先申請好免費金鑰／帳號（見下方「前置」），
設定環境變數後執行：

    export MARKETDATA_APP_TOKEN=...   # https://www.marketdata.app/ 註冊取得
    export ALPHA_VANTAGE_API_KEY=...  # https://www.alphavantage.co/support/#api-key
    export ORATS_TOKEN=...            # https://orats.com/ （多半需付費，可留空跳過）
    python3 scripts/probe_iv_history_vendors.py

**⚠ 認證方式標為「待確認」的部分**：本研究文件對這三個 vendor 的
`EGRESS_BLOCKED`／被沙箱擋，**沒有查到官方文件逐字確認的精確認證
標頭格式**（Bearer token？query string？自訂 header？）——下面各
`_probe_*` 函式的認證寫法是依業界常見 REST 慣例的**合理猜測**，
不是查證結果。跑這支腳本的人第一步應該打開對應 vendor 的官方 API
文件頁核對一次，猜錯了直接改函式裡的認證寫法即可，不影響其餘部分。

**不得**在未成功完成至少一次真實 API 呼叫並驗證資料形狀前，宣稱
vendor 已確認（本票既有 AC，逐字沿用）。

沙箱驗證紀錄（本輪，`curl` 直接測，非本腳本）：

    $ curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://www.marketdata.app/
    curl: (56) CONNECT tunnel failed, response 403
    $ curl ... www.alphavantage.co ...   → 同樣 CONNECT 403（若曾測）
    $ curl ... api.orats.io ...          → 同樣 CONNECT 403（若曾測）

純 stdlib（`urllib.request`），比照 `option_chaser/data/cboe.py`／
`treasury.py`／`scripts/probe_dividend_sources.py`（#120，同一輪、
同一套探測紀律）既有慣例。
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "option-chaser-probe/1"

# 測試標的固定用 TLT（本專案目前的主要研究對象，也是 #110/#113 系列
# 票沿用的真實案例），日期挑一個確定已收盤、資料應該存在的近期交易日。
_SYMBOL = "TLT"
_TEST_DATE = "2026-08-04"  # 需求方之後跑的時候可自行改成任一近期交易日


def _get(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = resp.read(6000)
            return {"status": resp.status,
                    "content_type": resp.headers.get("Content-Type"),
                    "body_preview": body[:800].decode("utf-8", errors="replace"),
                    "error": None}
    except HTTPError as e:
        body = e.read(500) if e.fp else b""
        return {"status": e.code,
                "content_type": e.headers.get("Content-Type") if e.headers else None,
                "body_preview": body.decode("utf-8", errors="replace"),
                "error": f"HTTPError {e.code}"}
    except URLError as e:
        return {"status": None, "content_type": None, "body_preview": "",
                "error": f"URLError: {e.reason}"}


def probe_marketdata_app() -> dict:
    """① 優先序第一——免費層 100 credits/日，查詢形狀最適配本專案
    （單合約一次呼叫回整段日序列）。

    ⚠ 認證方式待確認：依 REST 常見慣例猜測 Bearer token；官方文件
    https://www.marketdata.app/docs/api/options/quotes 若寫的是別種
    方式（如 query string `token=`），改這裡即可。
    """
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    if not token:
        return {"skipped": "MARKETDATA_APP_TOKEN 未設定，先到 "
                "https://www.marketdata.app/ 註冊取得免費金鑰"}
    # optionSymbol 用 OCC 代號；這裡示範查一筆存在機率高的合約，具體
    # 履約價/到期日需求方跑的時候可依當時真實鏈調整。
    url = (f"https://api.marketdata.app/v1/options/quotes/"
          f"{_SYMBOL}260117C00090000/?from={_TEST_DATE}&to={_TEST_DATE}")
    return _get(url, {"Authorization": f"Bearer {token}"})


def probe_alpha_vantage() -> dict:
    """② 優先序第二——與本 repo 既有備援方案同一家（金鑰可共用），
    一次呼叫解決「免費層是否含 HISTORICAL_OPTIONS」這個兩輪研究
    共同的懸案。"""
    key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not key:
        return {"skipped": "ALPHA_VANTAGE_API_KEY 未設定，先到 "
                "https://www.alphavantage.co/support/#api-key 免費申請"}
    url = (f"https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS"
          f"&symbol={_SYMBOL}&date={_TEST_DATE}&apikey={key}")
    return _get(url)


def probe_orats() -> dict:
    """③ 優先序第三——多半需要付費訂閱，僅在①②都不可行時才需要跑。
    token 認證方式依 https://docs.orats.io/data-api-guide/data.html
    （被沙箱擋，未查證）猜測為 query string `token=`。"""
    token = os.environ.get("ORATS_TOKEN")
    if not token:
        return {"skipped": "ORATS_TOKEN 未設定（多半需付費訂閱，"
                "見 https://orats.com/data-api ；①②任一可行時可跳過此項）"}
    url = (f"https://api.orats.io/datav2/hist/strikes"
          f"?token={token}&ticker={_SYMBOL}&tradeDate={_TEST_DATE}")
    return _get(url)


def main() -> None:
    probes = [("① Market Data App", probe_marketdata_app),
              ("② Alpha Vantage", probe_alpha_vantage),
              ("③ ORATS", probe_orats)]
    results = {}
    for name, fn in probes:
        results[name] = fn()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("\n---\n", file=sys.stderr)
    for name, r in results.items():
        if "skipped" in r:
            print(f"{name}: SKIPPED（{r['skipped']}）", file=sys.stderr)
        else:
            status = r["error"] or f"HTTP {r['status']}"
            print(f"{name}: {status}", file=sys.stderr)


if __name__ == "__main__":
    main()
