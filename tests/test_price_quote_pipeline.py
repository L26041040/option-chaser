"""V2-05（#407）：目前股價在**股票掃描階段**（分析師共識更新）取得，跟共識
快照一起存；清單與詳細資料讀取時算目標漲跌幅。

全部用 `tests/fixtures/yahoo/` 錄下的真實 Yahoo 回應回放，不連外。分割案例用
NVDA 2024-06-10 的 10:1 分割與 AVGO 2024-07-15 的 10:1 分割：分割前一個交易日
的實際收盤價（NVDA 2024-06-07 收 1,208.88；AVGO 2024-07-12 收 1,700.67）
是公開的歷史數字，fixture 的週線（已調整分割）對應 120.888／170.067，測試裡
有核對。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from api_app import consensus_cache
from api_app.analyst_source import YahooAnalystSource
from api_app.opportunity_settings import effective
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import ConsensusRules
from option_chaser.data.yahoo_analyst import HttpResponse, parse_chart_quote

FIXTURES = Path(__file__).parent / "fixtures" / "yahoo"


class Replay:
    """依 URL 回放錄下的回應；`chart_meta` 可改寫 chart 的 meta（模擬在另一天
    抓到的報價）。記錄每次請求。"""

    def __init__(self, chart_meta: dict | None = None):
        self.calls: list[str] = []
        self.chart_meta = chart_meta

    def get(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if "getcrumb" in url:
            return HttpResponse(200, "crumbXYZ", {})
        if "fc.yahoo.com" in url:
            return HttpResponse(404, "", {})
        symbol = url.split("?")[0].rstrip("/").split("/")[-1]
        if "quoteSummary" in url:
            return HttpResponse(200, (FIXTURES / f"{symbol}.quote_summary.json")
                                .read_text(encoding="utf-8"), {})
        doc = json.loads((FIXTURES / f"{symbol}.chart.json").read_text(encoding="utf-8"))
        if self.chart_meta is not None:
            doc["chart"]["result"][0]["meta"].update(self.chart_meta)
        return HttpResponse(200, json.dumps(doc), {})


def _epoch(y, m, d, hh, mm=0, ss=0) -> int:
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).timestamp())


# ---------- chart meta → 報價 ----------

def test_chart_meta_regular_market_price_and_time_are_the_quote():
    body = (FIXTURES / "NVDA.chart.json").read_text(encoding="utf-8")
    quote = parse_chart_quote(body)
    # fixture 原值：regularMarketPrice 125.53、regularMarketTime 1795208401
    assert quote.price == Decimal("125.53")
    assert quote.at == datetime(2026, 11, 20, 21, 0, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("meta", [
    {},                                                    # 沒有 meta 欄位
    {"regularMarketPrice": None, "regularMarketTime": 1795208401},
    {"regularMarketPrice": 0, "regularMarketTime": 1795208401},
    {"regularMarketPrice": 12.3},                          # 沒有時間
    {"regularMarketPrice": 12.3, "regularMarketTime": "x"},
])
def test_missing_or_broken_meta_means_no_quote(meta):
    body = json.dumps({"chart": {"result": [{"meta": meta, "timestamp": [],
                                             "indicators": {"quote": [{}]}}]}})
    assert parse_chart_quote(body) is None


def test_source_carries_the_quote_from_the_same_chart_call():
    transport = Replay()
    result = YahooAnalystSource(transport=transport).fetch("NVDA", date(2026, 11, 23))
    assert result.error is None
    assert result.quote.price == Decimal("125.53")
    assert result.quote.at == datetime(2026, 11, 20, 21, 0, 1, tzinfo=timezone.utc)


def test_upstream_calls_per_symbol_are_unchanged():
    """每檔仍是 cookie、crumb、quoteSummary、chart 四個請求，chart 只打一次
    （報價沿用同一個 chart 回應，沒有新增任何端點）。"""
    transport = Replay()
    YahooAnalystSource(transport=transport).fetch("AAPL", date(2026, 11, 23))
    kinds = ["cookie" if "fc.yahoo.com" in u else "crumb" if "getcrumb" in u
             else "summary" if "quoteSummary" in u else "chart" if "/chart/" in u
             else u for u in transport.calls]
    assert kinds == ["cookie", "crumb", "summary", "chart"]


# ---------- 更新流程 → 清單 ----------

def _refresh_and_view(symbols, today, transport, rules=None):
    storage = MemoryStorage()
    source = YahooAnalystSource(transport=transport)
    rules = rules or ConsensusRules()
    out = consensus_cache.refresh_symbols(
        storage, source, symbols, today, budget_exhausted=lambda: False,
        rules=rules, sleep=lambda _s: None)
    opportunity = effective({"universe_id": "custom", "custom_symbols": list(symbols)})
    view = consensus_cache.consensus_view(storage, source, opportunity, today, rules=rules)
    return {i["symbol"]: i for i in view["items"]}, out, storage


def test_refresh_stores_the_quote_and_list_shows_price_date_and_upside():
    items, out, _ = _refresh_and_view(["NVDA"], date(2026, 11, 23), Replay())
    item = items["NVDA"]
    assert item["price"] == 125.53
    assert item["price_date"] == "2026-11-20" and item["price_kind"] == "close"
    assert item["price_at"] == "2026-11-20T21:00:01+00:00"
    expected = (Decimal(str(item["mean"])) / Decimal("125.53") - 1) * 100
    assert item["target_upside_pct"] == pytest.approx(float(expected), abs=0.05)
    assert item["target_upside_reason"] is None


def test_refresh_uses_one_upstream_call_per_symbol_on_the_daily_cap():
    """每日上游呼叫計數（`rate_limits` 的 consensus_upstream）每檔仍只扣 1。"""
    _, out, _ = _refresh_and_view(["NVDA", "AVGO", "AAPL"], date(2026, 11, 23), Replay())
    assert out["upstream_calls_today"] == 3


def test_old_snapshots_without_a_quote_say_no_price_yet():
    items, _, storage = _refresh_and_view(["NVDA"], date(2026, 11, 23), Replay())
    [rec] = storage.latest_consensus_snapshots(["NVDA"], source="yahoo-udh").values()
    rec.snapshot.pop("quote")                     # 舊版（#407 之前）存的快照
    storage.save_consensus_snapshot(rec)
    source = YahooAnalystSource(transport=Replay())
    opportunity = effective({"universe_id": "custom", "custom_symbols": ["NVDA"]})
    [item] = consensus_cache.consensus_view(storage, source, opportunity,
                                            date(2026, 11, 23))["items"]
    assert item["mean"] is not None
    assert item["price"] is None and item["target_upside_pct"] is None
    assert item["target_upside_reason"] == "no_price"


def test_quote_older_than_three_trading_days_is_reported_stale():
    items, _, storage = _refresh_and_view(["NVDA"], date(2026, 11, 23), Replay())
    source = YahooAnalystSource(transport=Replay())
    opportunity = effective({"universe_id": "custom", "custom_symbols": ["NVDA"]})
    # 隔週週四再看（快照沒更新）：週五收盤之後已過 4 個交易日
    [item] = consensus_cache.consensus_view(storage, source, opportunity,
                                            date(2026, 11, 26))["items"]
    assert item["price"] == 125.53 and item["price_date"] == "2026-11-20"
    assert item["target_upside_pct"] is None
    assert item["target_upside_reason"] == "price_stale"


# ---------- 真實分割 ----------

def _weekly_adjusted(symbol: str, monday: date) -> float:
    doc = json.loads((FIXTURES / f"{symbol}.chart.json").read_text(encoding="utf-8"))
    r = doc["chart"]["result"][0]
    for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
        if datetime.fromtimestamp(t, timezone.utc).date() == monday:
            return c
    raise AssertionError(monday)


@pytest.mark.parametrize("symbol, pre_close, pre_close_at, split_day, monday", [
    # NVDA 2024-06-07（週五）收 1,208.88；10:1 分割 2024-06-10 生效
    ("NVDA", 1208.88, _epoch(2024, 6, 7, 20, 0, 1), date(2024, 6, 10), date(2024, 6, 3)),
    # AVGO 2024-07-12（週五）收 1,700.67；10:1 分割 2024-07-15 生效
    ("AVGO", 1700.67, _epoch(2024, 7, 12, 20, 0, 1), date(2024, 7, 15), date(2024, 7, 8)),
])
def test_real_split_between_quote_and_as_of_is_not_divided(
        symbol, pre_close, pre_close_at, split_day, monday):
    # fixture 週線已調整分割：那一週收盤 × 10 ＝ 分割前的實際收盤（獨立核對）
    assert _weekly_adjusted(symbol, monday) * 10 == pytest.approx(pre_close, abs=0.01)
    rules = ConsensusRules(h_min=1)
    # 分割生效日當天盤前更新：報價是前一個交易日（分割前基準）的收盤，
    # 平均目標價已在分割後基準 → 不得相除
    meta = {"regularMarketPrice": pre_close, "regularMarketTime": pre_close_at}
    items, _, _ = _refresh_and_view([symbol], split_day, Replay(meta), rules)
    item = items[symbol]
    assert item["mean"] is not None
    assert item["price"] == pre_close
    assert item["target_upside_pct"] is None
    assert item["target_upside_reason"] == "split_mismatch"


@pytest.mark.parametrize("symbol, pre_close, pre_close_at, pre_day, post_close, post_close_at, post_day", [
    # NVDA：分割前 2024-06-07 收 1,208.88；分割後第一個交易日 2024-06-10 收 121.79
    ("NVDA", 1208.88, _epoch(2024, 6, 7, 20, 0, 1), date(2024, 6, 7),
     121.79, _epoch(2024, 6, 10, 20, 0, 1), date(2024, 6, 10)),
    # AVGO：分割前 2024-07-12 收 1,700.67；分割後 2024-07-15 收 171.42
    ("AVGO", 1700.67, _epoch(2024, 7, 12, 20, 0, 1), date(2024, 7, 12),
     171.42, _epoch(2024, 7, 15, 20, 0, 1), date(2024, 7, 15)),
])
def test_same_basis_on_each_side_of_a_real_split_gives_comparable_upsides(
        symbol, pre_close, pre_close_at, pre_day, post_close, post_close_at, post_day):
    """分割前一天（價格、目標價都是分割前基準）與分割後當天（都是分割後
    基準）各算一次：兩個漲跌幅都落在合理範圍，而且彼此接近——跨分割沒有
    差十倍的錯算。"""
    rules = ConsensusRules(h_min=1)
    before, _, _ = _refresh_and_view(
        [symbol], pre_day,
        Replay({"regularMarketPrice": pre_close, "regularMarketTime": pre_close_at}), rules)
    after, _, _ = _refresh_and_view(
        [symbol], post_day,
        Replay({"regularMarketPrice": post_close, "regularMarketTime": post_close_at}),
        rules)
    b, a = before[symbol], after[symbol]
    assert b["target_upside_reason"] is None and a["target_upside_reason"] is None
    assert b["mean"] > 500 and a["mean"] < 500            # 兩邊的平均目標價基準不同
    for up in (b["target_upside_pct"], a["target_upside_pct"]):
        assert -50 < up < 100, up                         # 錯基準會是 −90% 或 +900%
    assert abs(b["target_upside_pct"] - a["target_upside_pct"]) < 15


def test_detail_item_and_search_summary_carry_the_same_price_fields():
    from api_app.opportunity_search import consensus_summary
    storage = MemoryStorage()
    source = YahooAnalystSource(transport=Replay())
    today = date(2026, 11, 23)
    consensus_cache.refresh_symbols(storage, source, ["NVDA"], today,
                                    budget_exhausted=lambda: False,
                                    sleep=lambda _s: None)
    opportunity = effective({"universe_id": "custom", "custom_symbols": ["NVDA"]})
    [listed] = consensus_cache.consensus_view(storage, source, opportunity, today)["items"]
    detail = consensus_cache.detail_view(storage, source, "NVDA", opportunity, today)
    fields = ("price", "price_date", "price_at", "price_kind",
              "target_upside_pct", "target_upside_reason")
    assert {k: detail["item"][k] for k in fields} == {k: listed[k] for k in fields}
    summary = consensus_summary(listed)
    assert {k: summary[k] for k in fields} == {k: listed[k] for k in fields}


def test_list_item_requires_today_so_staleness_is_never_skipped():
    """`consensus_cache._item()` 一定要拿到「今天」：有報價時要靠它判斷股價過舊，
    沒有預設值可以讓呼叫端漏傳（漏傳在有報價時會 500）。"""
    import inspect

    for fn in (consensus_cache._item, consensus_cache._empty_item):
        param = inspect.signature(fn).parameters["today"]
        assert param.default is inspect.Parameter.empty, fn.__name__
    quote = {"price": "100", "at": "2026-11-20T21:00:01+00:00", "date": "2026-11-20",
             "kind": "close", "split_basis_mismatch": False}
    gate = {"first": False, "second": False, "selected": False, "reasons": []}
    with pytest.raises(TypeError):
        consensus_cache._item("AAA", "no_data", reasons=[], gate=gate, quote=quote)
    empty = consensus_cache._empty_item("AAA", "no_data", "no_data: 尚未更新",
                                        today=date(2026, 11, 23))
    assert empty["target_upside_reason"] == "no_price"
