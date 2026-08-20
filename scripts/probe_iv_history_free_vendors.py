#!/usr/bin/env python
"""#111 補充：免 credential（不需申請金鑰／帳號）候選 vendor 的探測腳本。

**這支腳本本身不能在本 repo 的 agent 沙箱跑**——沙箱出口政策封鎖
`query1.finance.yahoo.com`／`api.nasdaq.com`／`cdn.cboe.com`／
`www.cboe.com` 這幾個網域（已用 curl 直接驗證：CONNECT 403），這是
沙箱代理層的政策，不代表 GitHub Actions runner 或 Vercel production
打不到，兩件事不可混為一談（本 repo 一貫的誠實揭露紀律，見
`docs/research/interest-rate-source-selection.md` §0）。

**背景**：`docs/research/historical-options-iv-data-sources.md` 的既有
研究已判定 Market Data App／Alpha Vantage／ORATS 三家「能」的候選皆
credential-blocked（見該文件 §5.1 追記）。本腳本補測**完全不需要
申請任何金鑰／帳號**的候選：

    ① Yahoo（`query1.finance.yahoo.com`）——既有研究 §4.3 已從文件面／
      社群回報判定「不能」（無 as-of 參數、單一合約只有成交 OHLC 沒有
      歷史 bid/ask/IV）。本腳本用真實請求覆核這個結論，而不是只信
      文件——包括覆測社群爭論過的「date 參數是否真的能回放歷史」。
    ② Nasdaq（`api.nasdaq.com`）——既有研究只確認過**配息**免鑰端點
      （`dividend-yield-source-selection.md` §5.3），選擇權史料從未
      實測過；Nasdaq Data Link 的選擇權資料庫（NGVUS）是付費的，但
      `api.nasdaq.com` 網站本身背後的當前選擇權鏈 JSON 端點免鑰可打，
      這裡測它有沒有任何歷史／日期參數。
    ③ Cboe（`cdn.cboe.com`／`www.cboe.com`）——本專案現行主源
      （`option_chaser/data/cboe.py`）的延遲報價端點本身只回當下快照，
      這裡測加上日期參數是否被接受、以及 cboe.com 網站上是否存在任何
      免鑰的歷史 IV／historical volatility JSON（VIX 之類的指數史料是
      免費的，但那是市場層級指數，不是逐 (tenor, delta) 的個股/ETF
      IV 網格，即使可達也不滿足 #114 AC，仍會如實記錄）。

**用法**：

    python3 scripts/probe_iv_history_free_vendors.py

輸出所有探測結果的 JSON 到 stdout，人類可讀摘要到 stderr。跑完把
結果貼回 `docs/research/historical-options-iv-data-sources.md`。

純 stdlib（`urllib.request`），比照 `probe_dividend_sources.py`／
`probe_iv_history_vendors.py` 既有慣例：不吞例外、記錄原始回應，
不是只記「成功/失敗」。
"""
from __future__ import annotations

import json
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_TIMEOUT_SECONDS = 20.0
_SYMBOL = "TLT"
# 一般瀏覽器等級 UA——Yahoo／Nasdaq 這類端點常對明顯的腳本 UA 更嚴格
# （既有 `probe_dividend_sources.py` 對 Nasdaq 已有這個經驗）。
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _get(url: str, headers: dict | None = None) -> dict:
    req = Request(url, headers={"User-Agent": _BROWSER_UA,
                                "Accept": "application/json, text/plain, */*",
                                **(headers or {})})
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = resp.read(4000)
            return {"url": url, "status": resp.status,
                    "content_type": resp.headers.get("Content-Type"),
                    "body_preview": body[:2000].decode("utf-8", errors="replace"),
                    "error": None}
    except HTTPError as e:
        body = e.read(500) if e.fp else b""
        return {"url": url, "status": e.code,
                "content_type": e.headers.get("Content-Type") if e.headers else None,
                "body_preview": body.decode("utf-8", errors="replace"),
                "error": f"HTTPError {e.code}"}
    except URLError as e:
        return {"url": url, "status": None, "content_type": None, "body_preview": "",
                "error": f"URLError: {e.reason}"}


# ---------- ① Yahoo ----------

def probe_yahoo() -> dict:
    out: dict = {}

    # 1) 當下選擇權鏈：拿真實到期日清單與一個真實 OCC 合約代號，供
    #    後續測試使用（也順便看回應形狀本身有沒有任何歷史欄位）。
    current = _get(f"https://query1.finance.yahoo.com/v7/finance/options/{_SYMBOL}")
    out["1_current_chain"] = current

    occ_symbol = None
    expirations: list[int] = []
    if current.get("status") == 200:
        try:
            body = json.loads(current["body_preview"]
                              if len(current["body_preview"]) < 2000 else "{}")
        except json.JSONDecodeError:
            body = {}
        # body 可能被截斷成不完整 JSON（只取前 2000 bytes）；抓不到就算了，
        # 下面用 regex 從 preview 裡硬撈一個 contractSymbol 當備援。
        try:
            result = body.get("optionChain", {}).get("result", [{}])[0]
            expirations = result.get("expirationDates", [])
            calls = result.get("options", [{}])[0].get("calls", [])
            if calls:
                occ_symbol = calls[0].get("contractSymbol")
        except (KeyError, IndexError, AttributeError):
            pass
    if occ_symbol is None:
        m = re.search(r'"contractSymbol":"([A-Z0-9]+)"', current.get("body_preview", ""))
        if m:
            occ_symbol = m.group(1)

    out["_extracted_occ_symbol"] = occ_symbol
    out["_extracted_expiration_count"] = len(expirations)

    # 2) 社群爭論過的「as-of」workaround：加 date= 參數（過去的 unix
    #    timestamp）看回應是否真的回放到那個時間點，還是照樣回當下。
    #    90 天前與 1 年前各測一次。
    now = int(time.time())
    for label, days_ago in (("90d_ago", 90), ("1y_ago", 365)):
        ts = now - days_ago * 86400
        out[f"2_date_param_{label}"] = _get(
            f"https://query1.finance.yahoo.com/v7/finance/options/{_SYMBOL}?date={ts}")

    # 3) 單一合約的 chart 端點：這是 Yahoo 對「歷史」唯一有資料的路徑
    #    （既有研究：只有成交 OHLC，沒有 bid/ask/IV）。用真的抓到的合約
    #    代號測，親眼確認欄位形狀。抓不到就退回用一個合理猜測的代號
    #    （測試本身仍然有意義：至少驗證端點是否存在、格式要求）。
    probe_symbol = occ_symbol or f"{_SYMBOL}260117C00090000"
    out["3_contract_chart"] = _get(
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{probe_symbol}?range=1y&interval=1d")

    return out


# ---------- ② Nasdaq ----------

def probe_nasdaq() -> dict:
    out: dict = {}
    headers = {"Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}

    # 1) 當下選擇權鏈——確認端點免鑰可達＋看回應形狀有沒有任何歷史／
    #    日期相關欄位或 metadata。
    out["1_current_chain"] = _get(
        f"https://api.nasdaq.com/api/quote/{_SYMBOL}/option-chain"
        "?assetclass=etf&limit=40", headers)

    # 2) 硬塞歷史日期參數，看是被忽略、報錯，還是真的接受。Nasdaq 的
    #    股價歷史端點確實吃 fromdate/todate（`dividend-yield-source-
    #    selection.md` 已確認股價／配息兩種端點都吃），這裡測選擇權
    #    鏈端點是否也吃同一組參數名。
    out["2_chain_with_date_params"] = _get(
        f"https://api.nasdaq.com/api/quote/{_SYMBOL}/option-chain"
        "?assetclass=etf&limit=10&fromdate=2025-08-01&todate=2025-08-01", headers)

    # 3) 猜測性測試：是否存在獨立的「選擇權歷史」端點（仿照股價歷史
    #    端點命名慣例）。404／400 也是有意義的結果——確認不存在，
    #    不是探測腳本失敗。
    for label, url in (
        ("historical_subpath",
         f"https://api.nasdaq.com/api/quote/{_SYMBOL}/option-chain/historical"
         "?assetclass=etf&fromdate=2025-08-01&todate=2025-08-01"),
        ("options_historical",
         f"https://api.nasdaq.com/api/quote/{_SYMBOL}/options-historical"
         "?assetclass=etf&fromdate=2025-08-01&todate=2025-08-01"),
    ):
        out[f"3_guess_{label}"] = _get(url, headers)

    return out


# ---------- ③ Cboe ----------

def probe_cboe() -> dict:
    out: dict = {}

    # 1) 現行 production 端點原樣再測一次（`option_chaser/data/cboe.py`
    #    既有 URL）——確認它就是純快照，沒有任何歷史查詢方式。
    base = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{_SYMBOL}.json"
    out["1_current_snapshot"] = _get(base)

    # 2) 硬塞常見的日期查詢參數名，看是否被接受（預期：被忽略，回應
    #    跟不加參數時一樣；若真的不同，就是重大新發現）。
    for label, param in (("date", "date=2025-08-01"), ("asof", "asof=2025-08-01"),
                        ("historical", "historical=true")):
        out[f"2_param_{label}"] = _get(f"{base}?{param}")

    # 3) cboe.com 網站上是否存在任何免鑰的歷史 IV／historical volatility
    #    JSON（即使可達，市場層級指數如 VIX 也不滿足 #114 的
    #    (tenor,delta) 逐候選網格需求——這裡如實記錄可達性與資料層級，
    #    不代表可達就符合 AC）。
    for label, url in (
        ("symbol_hv_guess",
         f"https://cdn.cboe.com/api/global/delayed_quotes/historical/{_SYMBOL}.json"),
        ("us_indices_history_pattern",
         f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{_SYMBOL}_History.csv"),
    ):
        out[f"3_guess_{label}"] = _get(url)

    return out


def main() -> None:
    probes = [("① Yahoo", probe_yahoo), ("② Nasdaq", probe_nasdaq),
              ("③ Cboe", probe_cboe)]
    results = {}
    for name, fn in probes:
        results[name] = fn()
    print(json.dumps(results, indent=2, ensure_ascii=False))

    print("\n--- 摘要 ---\n", file=sys.stderr)
    for name, group in results.items():
        print(f"{name}:", file=sys.stderr)
        for key, r in group.items():
            if key.startswith("_"):
                print(f"    {key}: {r}", file=sys.stderr)
                continue
            status = r.get("error") or f"HTTP {r.get('status')}"
            print(f"  {key}: {status}  [{r.get('url')}]", file=sys.stderr)


if __name__ == "__main__":
    main()
