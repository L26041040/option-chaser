"""Yahoo 直連選擇權鏈 adapter（OPTION-CHASER-PRODUCTION-DELIVERY-001）。只用 stdlib。

為什麼需要：Cboe 延遲報價（`cboe.py`）從部分網路（含本沙箱）被 Cloudflare
擋下（307 → cdn-api.cboe.com → 403），而 yfinance 帶 pandas／numpy，Vercel
serverless 不裝（`yf.available()` 為假）——production 原本的 Cboe → yfinance
降級鏈在 Cboe 被擋時等於沒有備援。這個 adapter 直接打 yfinance 背後用的同一個
公開端點，不需要任何新依賴：

    https://query2.finance.yahoo.com/v7/finance/options/{SYMBOL}

第一次呼叫回 `expirationDates`（全部到期日）、最近一個到期日的 chain，以及
`quote.regularMarketPrice`（現價）；其餘每個到期日各打一次 `?date=<epoch>`。
一次完整抓取的請求數＝(cookie＋crumb，同一個 client 只在第一次或 crumb 過期時)
＋到期日數量。

存取方式沿用 `yahoo_analyst.YahooClient` 的 cookie＋crumb 流程（crumb 401 時
重取一次、錯誤訊息不帶底層例外原文，#345 B-3）。**不使用**代理、代理池、
反機器人繞過或付費服務；被擋就照實回報 `FetchError`，交給呼叫端的降級鏈。

欄位對應與 `yf.py` 的 `map_rows` 完全相同（直接共用它，只把 `source` 換成
`"yahoo"`）：到期日字串比照 yfinance，取 epoch 的 **UTC 日期**；缺值／NaN 一律
`None`（volume／open_interest 比照 `map_rows` 記 0）。個別壞掉的列跳過；
沒有現價或一張合約都沒有時丟 `FetchError`。任何一個到期日的頁面抓取失敗，整次
抓取就失敗（不交出缺到期日的殘缺 chain，讓降級鏈試下一個來源）。
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote

from ..models import ChainSnapshot, FetchError, RateLimitedError
from ..symbols import canonical_symbol, yahoo_symbol
from .yahoo_analyst import Transport, YahooClient, YahooError
from .yf import map_rows

SOURCE = "yahoo"
OPTIONS_URL = "https://query2.finance.yahoo.com/v7/finance/options/{symbol}"
_NOT_FOUND = "Yahoo 沒有這個 symbol 的選擇權資料"


@dataclass(frozen=True)
class OptionsPage:
    """一次 v7 options 回應解析後的結果。"""

    spot: float | None                      # quote.regularMarketPrice
    expiration_dates: tuple[int, ...]       # 全部到期日 epoch
    rows: dict[int, list[dict]]             # 到期日 epoch → yfinance 形狀的列


def expiry_string(epoch: int) -> str:
    """到期日 epoch → "YYYY-MM-DD"：與 yfinance 產生 `Ticker.options` 字串的方式
    相同（UTC 日期；Yahoo 的到期日 epoch 是當天 UTC 零時）。"""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date().isoformat()


def _finite_positive(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def _epoch(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return int(value)


def _row(raw, option_type: str, expiry: str) -> dict | None:
    """一列 → yfinance 形狀的 dict（交給 `map_rows`）；缺代號或履約價壞掉的列
    回 None（跳過，不讓整頁失敗）。"""
    if not isinstance(raw, dict):
        return None
    symbol = raw.get("contractSymbol")
    strike = _finite_positive(raw.get("strike"))
    if not isinstance(symbol, str) or not symbol.strip() or strike is None:
        return None
    return {"contractSymbol": symbol.strip(), "option_type": option_type,
            "strike": strike, "expiry": expiry,
            "bid": raw.get("bid"), "ask": raw.get("ask"),
            "lastPrice": raw.get("lastPrice"), "volume": raw.get("volume"),
            "openInterest": raw.get("openInterest"),
            "impliedVolatility": raw.get("impliedVolatility")}


def parse_options_page(body: str) -> OptionsPage:
    """v7 options 回應 → `OptionsPage`。整體結構不對時丟 `YahooError`；個別壞掉
    的列（或缺到期日的區塊）跳過。"""
    try:
        doc = json.loads(body)
        result = (doc.get("optionChain") or {}).get("result")
    except (ValueError, AttributeError) as e:
        raise YahooError("選擇權回應格式無法解析（不是預期的 JSON）") from e
    if not result or not isinstance(result[0], dict):
        raise YahooError(_NOT_FOUND)
    entry = result[0]
    quote_ = entry.get("quote") if isinstance(entry.get("quote"), dict) else {}
    dates = tuple(e for e in (_epoch(x) for x in entry.get("expirationDates") or ())
                  if e is not None)
    rows: dict[int, list[dict]] = {}
    for block in entry.get("options") or ():
        if not isinstance(block, dict):
            continue
        epoch = _epoch(block.get("expirationDate"))
        if epoch is None:
            continue
        expiry = expiry_string(epoch)
        out = rows.setdefault(epoch, [])
        for side, option_type in (("calls", "call"), ("puts", "put")):
            for raw in block.get(side) or ():
                r = _row(raw, option_type, expiry)
                if r is not None:
                    out.append(r)
    return OptionsPage(_finite_positive(quote_.get("regularMarketPrice")), dates, rows)


class YahooOptionsClient:
    """一個標的的完整 chain：第一頁＋其餘每個到期日各一頁。"""

    def __init__(self, transport: Transport | None = None, *,
                 client: YahooClient | None = None):
        self._client = client or YahooClient(transport)

    def _page(self, symbol: str, epoch: int | None) -> OptionsPage:
        # 股權類別：Yahoo 只認 `BRK-B`（`BRK.B` 回 404），見 `option_chaser.symbols`。
        url = OPTIONS_URL.format(symbol=quote(yahoo_symbol(symbol))) + (
            f"?date={epoch}" if epoch is not None else "")
        return parse_options_page(self._client.get_with_crumb(
            url, "選擇權資料", not_found=_NOT_FOUND))

    def fetch_chain(self, symbol: str, *,
                    now: Callable[[], datetime] | None = None) -> ChainSnapshot:
        symbol = canonical_symbol(symbol)   # 快照掛 canonical 代號（#404）
        try:
            first = self._page(symbol, None)
            rows = dict(first.rows)
            for epoch in first.expiration_dates:
                if epoch not in rows:
                    rows[epoch] = self._page(symbol, epoch).rows.get(epoch, [])
        except YahooError as e:
            if e.rate_limited:
                # `RateLimitedError` 讓 API 層的 `_vendor_attempt` 記到 429 指標
                raise RateLimitedError(f"Yahoo 選擇權限流（{symbol}）：{e}",
                                       retry_after_seconds=e.retry_after) from e
            raise FetchError(f"Yahoo 選擇權抓取失敗（{symbol}）：{e}") from e
        flat = [r for epoch in sorted(rows) for r in rows[epoch]]
        if first.spot is None or not flat:
            raise FetchError(f"Yahoo 選擇權回傳資料不足（{symbol}）：無現價或無合約")
        fetched_at = (now or (lambda: datetime.now(timezone.utc)))().isoformat(
            timespec="seconds")
        return map_rows(symbol, first.spot, fetched_at, flat, source=SOURCE)


# 同一個 serverless instance 內共用 cookie＋crumb（warm 呼叫省掉 2 個請求）。
_shared: YahooOptionsClient | None = None
_shared_lock = threading.Lock()


def _shared_client() -> YahooOptionsClient:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = YahooOptionsClient()
        return _shared


def fetch_chain(symbol: str) -> ChainSnapshot:
    """預設抓鏈降級鏈（`service.fetch_chain`／API `_default_fetch`）用的入口。"""
    return _shared_client().fetch_chain(symbol)
