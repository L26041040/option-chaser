"""OPTION-CHASER-PRODUCTION-DELIVERY-001：Yahoo 直連選擇權鏈 adapter。

fixture（`tests/fixtures/yahoo/AAPL.options*.json`）是**錄下的真實 Yahoo v7
options 回應**（2026-11-23 美東錄製，AAPL，週五收盤後的報價）。為了控制大小
只留 3 個到期日（2026-11-23 第一頁＋2026-12-18、2027-01-15 兩頁），
`expirationDates`／`strikes`／`quote` 跟著裁成這 3 頁的範圍；合約列一字未改。
不含 cookie、crumb 或任何秘密。HTTP 層由假 transport 回放，測試本身不連外。
期望值是直接數原始 JSON 得出的字面常數，不是拿 adapter 自己算。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from option_chaser import service
from option_chaser.data import yahoo_options
from option_chaser.data.yahoo_analyst import HttpResponse, UrllibTransport
from option_chaser.data.yahoo_options import YahooOptionsClient, parse_options_page
from option_chaser.models import AnalysisParams, FetchError, RateLimitedError

FIXTURES = Path(__file__).parent / "fixtures" / "yahoo"
RECORDED_AT = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)
EXPIRY_EPOCHS = (1795392000, 1797552000, 1799971200)


class OptionsReplayTransport:
    """依 URL 回放錄下的 options 回應，記錄每次請求。`page_status` 可指定某個
    `date=`（第一頁用 None）回非 200。"""

    def __init__(self, *, symbol_dir: Path = FIXTURES, page_status=None,
                 crumb_status: int = 200, first_401: bool = False):
        self.calls: list[str] = []
        self.dir = symbol_dir
        self.page_status = dict(page_status or {})
        self.crumb_status = crumb_status
        self.first_401 = first_401

    @property
    def option_calls(self) -> list[str]:
        return [u for u in self.calls if "/v7/finance/options/" in u]

    def get(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if "getcrumb" in url:
            return HttpResponse(self.crumb_status, "crumbXYZ", {})
        if "fc.yahoo.com" in url:
            return HttpResponse(404, "", {})
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        assert query.get("crumb") == ["crumbXYZ"], url
        if self.first_401:
            self.first_401 = False
            return HttpResponse(401, '{"finance":{"error":{"code":"Unauthorized"}}}', {})
        symbol = parts.path.rstrip("/").split("/")[-1]
        date = query.get("date", [None])[0]
        if date in self.page_status:
            status, headers = self.page_status[date]
            return HttpResponse(status, '{"finance":{"error":{}}}', headers)
        name = f"{symbol}.options.json" if date is None else f"{symbol}.options.{date}.json"
        path = self.dir / name
        if not path.exists():
            return HttpResponse(404, '{"finance":{"result":null}}', {})
        return HttpResponse(200, path.read_text(encoding="utf-8"), {})


def _fetch(symbol="AAPL", **kw):
    transport = OptionsReplayTransport(**kw)
    snap = YahooOptionsClient(transport).fetch_chain(symbol, now=lambda: RECORDED_AT)
    return snap, transport


def _page(*, quote=None, dates=(1797552000,), options=None) -> str:
    return json.dumps({"optionChain": {"result": [{
        "underlyingSymbol": "XYZ", "expirationDates": list(dates),
        "quote": {"regularMarketPrice": 100.0} if quote is None else quote,
        "options": [{"expirationDate": dates[0], "calls": [], "puts": []}]
        if options is None else options}], "error": None}})


# ---------- 真實 fixture → ChainSnapshot ----------

def test_real_fixture_maps_every_contract_of_every_expiry():
    snap, _ = _fetch()
    # 原始 JSON：43+46（11-23）、102+88（12-18）、98+86（01-15）
    assert len(snap.contracts) == 463
    assert snap.source == "yahoo"
    assert snap.symbol == "AAPL"
    assert snap.spot == 342.56                     # quote.regularMarketPrice
    assert snap.fetched_at == "2026-11-23T05:00:00+00:00"
    assert sorted({c.expiry for c in snap.contracts}) == [
        "2026-11-23", "2026-12-18", "2027-01-15"]
    assert sum(c.option_type == "call" for c in snap.contracts) == 43 + 102 + 98
    assert sum(c.option_type == "put" for c in snap.contracts) == 46 + 88 + 86


def test_real_contract_fields_match_the_raw_row():
    snap, _ = _fetch()
    by_symbol = {c.contract_symbol: c for c in snap.contracts}
    c = by_symbol["AAPL261123C00270000"]
    assert (c.option_type, c.strike, c.expiry) == ("call", 270.0, "2026-11-23")
    assert (c.bid, c.ask, c.last) == (71.75, 74.65, 73.41)
    assert (c.volume, c.open_interest) == (2, 2)
    assert c.implied_volatility == 1.8232430712890624
    leap = by_symbol["AAPL270115C00350000"]
    assert (leap.bid, leap.ask, leap.volume, leap.open_interest) == (11.65, 13.0, 1919, 58263)


def test_missing_fields_follow_the_yfinance_mapping():
    """真實列 AAPL261218P00425000 沒有 `volume`：比照 `yf.map_rows` 記 0；
    其餘欄位照實。"""
    snap, _ = _fetch()
    c = {c.contract_symbol: c for c in snap.contracts}["AAPL261218P00425000"]
    assert c.volume == 0 and c.open_interest == 0
    assert (c.bid, c.ask, c.last) == (80.55, 83.3, 67.7)


def test_one_request_per_expiry_and_crumb_only_once():
    snap, transport = _fetch()
    # cookie＋crumb＋3 個到期日頁（第一頁已含最近的到期日，其餘各一次）
    assert len(transport.calls) == 2 + 3
    requested = [parse_qs(urlsplit(u).query).get("date", [None])[0]
                 for u in transport.option_calls]
    assert requested == [None, "1797552000", "1799971200"]
    # 同一個 client 再抓一次：crumb 沿用，只多 3 個到期日頁
    client = YahooOptionsClient(transport)
    client._client._crumb = "crumbXYZ"
    before = len(transport.calls)
    client.fetch_chain("AAPL", now=lambda: RECORDED_AT)
    assert len(transport.calls) - before == 3


def test_expiry_string_is_the_utc_date_like_yfinance():
    # 2026-12-18 00:00 UTC 在紐約仍是 12-17 晚上——yfinance 取 UTC 日期
    assert yahoo_options.expiry_string(1797552000) == "2026-12-18"
    assert yahoo_options.expiry_string(1797552000 + 3600 * 20) == "2026-12-18"


def test_expired_crumb_is_refreshed_once():
    snap, transport = _fetch(first_401=True)
    assert len(snap.contracts) == 463
    assert sum("getcrumb" in u for u in transport.calls) == 2


# ---------- 壞資料 ----------

def test_malformed_rows_are_skipped_and_nan_becomes_none():
    body = _page(options=[{"expirationDate": 1797552000, "calls": [
        {"contractSymbol": "XYZ261218C00100000", "strike": 100, "bid": "NaN",
         "ask": float("nan"), "lastPrice": None, "impliedVolatility": "x"},
        {"strike": 105},                                     # 沒有代號
        {"contractSymbol": "XYZ261218C00110000", "strike": "abc"},
        {"contractSymbol": "XYZ261218C00120000", "strike": -5},
        "not-a-row",
    ], "puts": [{"contractSymbol": "XYZ261218P00090000", "strike": 90.0,
                 "bid": 1.2, "ask": 1.4, "volume": 3, "openInterest": 7}]}])
    page = parse_options_page(body)
    rows = page.rows[1797552000]
    assert [r["contractSymbol"] for r in rows] == ["XYZ261218C00100000", "XYZ261218P00090000"]

    class One:
        def get(self, url):
            if "getcrumb" in url:
                return HttpResponse(200, "c", {})
            return HttpResponse(200, body if "options" in url else "", {})

    snap = YahooOptionsClient(One()).fetch_chain("XYZ", now=lambda: RECORDED_AT)
    call, put = snap.contracts
    assert (call.bid, call.ask, call.last, call.implied_volatility) == (None, None, None, None)
    assert (call.volume, call.open_interest) == (0, 0)
    assert (put.bid, put.ask, put.volume, put.open_interest) == (1.2, 1.4, 3, 7)


class _Static:
    def __init__(self, body: str, status: int = 200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}

    def get(self, url):
        if "getcrumb" in url:
            return HttpResponse(200, "c", {})
        if "fc.yahoo.com" in url:
            return HttpResponse(404, "", {})
        return HttpResponse(self.status, self.body, self.headers)


@pytest.mark.parametrize("body", [
    _page(quote={}),                                         # 沒有現價
    _page(quote={"regularMarketPrice": "NaN"}),
    _page(),                                                 # 有現價、沒有合約
    json.dumps({"optionChain": {"result": [], "error": None}}),
    "<html>not json</html>",
])
def test_no_spot_or_no_contracts_or_garbage_is_a_fetch_error(body):
    with pytest.raises(FetchError):
        YahooOptionsClient(_Static(body)).fetch_chain("XYZ")


def test_unknown_symbol_404_is_a_fetch_error():
    with pytest.raises(FetchError, match="選擇權"):
        _fetch("NOPE")


def test_429_is_a_rate_limited_error_with_retry_after():
    with pytest.raises(RateLimitedError) as ei:
        YahooOptionsClient(_Static("{}", 429, {"Retry-After": "30"})).fetch_chain("XYZ")
    assert ei.value.retry_after_seconds == 30


def test_a_failing_expiry_page_fails_the_whole_fetch():
    """不交出缺到期日的殘缺 chain：降級鏈改試下一個來源。"""
    with pytest.raises(FetchError, match="狀態碼 500"):
        _fetch(page_status={"1799971200": (500, {})})


def test_connection_errors_are_sanitized_fetch_errors():
    class Down:
        def get(self, url):
            raise OSError("connect to internal-host.example:443 refused")

    with pytest.raises(FetchError) as ei:
        YahooOptionsClient(Down()).fetch_chain("XYZ")
    assert "internal-host" not in str(ei.value)


def test_the_test_suite_cannot_reach_the_real_network():
    """`tests/conftest.py` 把共用的 `UrllibTransport.get` 換成丟 OSError：
    預設入口（共用 client）在測試裡只會得到 `FetchError`，不會連外。"""
    with pytest.raises(OSError, match="network disabled"):
        UrllibTransport().get("https://query2.finance.yahoo.com/")
    with pytest.raises(FetchError):
        yahoo_options.fetch_chain("AAPL")


def test_fixtures_carry_no_cookie_or_crumb():
    for path in FIXTURES.glob("AAPL.options*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert "crumb" not in text and "cookie" not in text and "set-cookie" not in text


# ---------- 真實 snapshot 跑得過引擎 ----------

def test_real_snapshot_runs_through_the_engine():
    snap, _ = _fetch()
    req = service.AnalysisRequest(
        symbol="AAPL",
        base_params=AnalysisParams(strategy="long-call", target_price=370.0,
                                   target_month="2027-01"),
        strategies=("long-call", "bull-call-spread", "call-fly"))
    result = service.run_with_snapshot(req, snap)
    assert result.snapshot.source == "yahoo"
    statuses = {r.strategy: r.status for r in result.results}
    assert statuses == {"long-call": "ok", "bull-call-spread": "ok", "call-fly": "ok"}
    assert all(r.candidates for r in result.results)
    assert result.best_strategy is not None


# ---------- V2-01（#404）：股權類別代號對照 ----------

def test_share_class_chain_is_requested_as_brk_hyphen_b_and_labelled_brk_dot_b():
    """`BRK-B.options.json`：2026-11-24 錄下的真實 Yahoo 第一頁（只留第一個
    到期日 1795737600＝2026-11-27，`expirationDates`／`strikes` 跟著裁；合約列一字未改：
    57 call＋53 put，現價 572.36）。Yahoo 對 `BRK.B` 回 404，所以 URL 必須用
    連字號；快照掛回 canonical `BRK.B`，劇本與搜尋結果都用這個鍵。"""
    transport = OptionsReplayTransport()
    snap = YahooOptionsClient(transport).fetch_chain("BRK.B", now=lambda: RECORDED_AT)
    assert transport.option_calls
    assert all("/v7/finance/options/BRK-B?" in u for u in transport.option_calls)
    assert snap.symbol == "BRK.B"
    assert snap.spot == 572.36
    assert len(snap.contracts) == 110
    assert {c.expiry for c in snap.contracts} == {"2026-11-27"}
