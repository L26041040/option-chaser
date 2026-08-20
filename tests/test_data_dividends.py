"""#123（spec #117 §2）取得與快取層：Yahoo→FMP→Nasdaq 備援、per-symbol
本地檔案快取（90 日曆日陳舊窗）、三層 fallback。全部離線（假抓取器）。

真實 Yahoo 回應形狀取自 #120 production 實測（GitHub Actions run
31408756757，見 `docs/research/dividend-yield-source-selection.md`
§12.4）——`events.dividends` 鍵為 unix timestamp 字串、值含 `amount`。
"""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import date

import pytest

from option_chaser.data import dividends
from option_chaser.data.dividends import (CACHE_MAX_AGE_DAYS, FMP_URL, NASDAQ_URL,
                                          YAHOO_URL, fetch_dividends,
                                          load_dividend_history)
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.models import FetchError

TODAY = date(2026, 8, 10)

# 形狀比照 #120 §12.4 實測回應（timestamp→{"amount": float} 對映）。
_YAHOO_BODY = json.dumps({
    "chart": {"result": [{
        "meta": {"symbol": "TLT"},
        "events": {"dividends": {
            "1785816600": {"amount": 0.330, "date": 1785816600},
            "1783224600": {"amount": 0.318, "date": 1783224600},
        }}}]}})

_YAHOO_NO_DIVIDENDS_BODY = json.dumps({
    "chart": {"result": [{"meta": {"symbol": "YETI"}, "events": {}}]}})

_NASDAQ_BODY = json.dumps({
    "data": {"annualizedDividend": "3.965448",
            "dividends": {"rows": [
                {"exOrEffDate": "08/03/2026", "amount": "$0.330000", "type": "CASH"},
                {"exOrEffDate": "07/01/2026", "amount": "$0.318000", "type": "CASH"},
            ]}}})

_FMP_BODY = json.dumps([
    {"date": "2026-08-03", "dividend": 0.330, "adjDividend": 0.330},
    {"date": "2026-07-01", "dividend": 0.318, "adjDividend": 0.318},
])


def _history(source="yahoo") -> DividendHistory:
    return DividendHistory(
        symbol="TLT", as_of=TODAY.isoformat(), source=source,
        distributions=(DividendRecord("2026-08-03", 0.330),
                       DividendRecord("2026-07-01", 0.318)))


# ---------- fetch_dividends 備援次序 ----------

def test_fetch_dividends_yahoo_first():
    calls = []

    def http_get(url, headers=None):
        calls.append(url)
        return _YAHOO_BODY

    history = fetch_dividends("TLT", TODAY, http_get=http_get)
    assert history.source == "yahoo"
    assert len(history.distributions) == 2
    assert calls == [YAHOO_URL.format(symbol="TLT")]


def test_yahoo_success_with_zero_dividends_is_not_a_failure():
    """研究 §8 第 2 層：確定無配息（YETI 這種）是成功，不是要備援的失敗
    ——`distributions` 為空 tuple，`source` 仍是 yahoo，不落到 FMP/Nasdaq。"""
    calls = []

    def http_get(url, headers=None):
        calls.append(url)
        return _YAHOO_NO_DIVIDENDS_BODY

    history = fetch_dividends("YETI", TODAY, http_get=http_get)
    assert history.source == "yahoo"
    assert history.distributions == ()
    assert calls == [YAHOO_URL.format(symbol="YETI")]   # 沒有再打 FMP/Nasdaq


def test_fetch_dividends_falls_back_to_nasdaq_when_yahoo_fails_and_no_fmp_key(
    monkeypatch,
):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    calls = []

    def http_get(url, headers=None):
        calls.append(url)
        if url == YAHOO_URL.format(symbol="TLT"):
            raise OSError("boom")
        if url == NASDAQ_URL.format(symbol="TLT", cls="stocks"):
            raise FetchError("狀態碼 400")
        return _NASDAQ_BODY

    history = fetch_dividends("TLT", TODAY, http_get=http_get)
    assert history.source == "nasdaq"
    assert len(history.distributions) == 2
    assert calls == [YAHOO_URL.format(symbol="TLT"),
                     NASDAQ_URL.format(symbol="TLT", cls="stocks"),
                     NASDAQ_URL.format(symbol="TLT", cls="etf")]


def test_fetch_dividends_tries_fmp_before_nasdaq_when_key_is_set(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test-key")
    calls = []

    def http_get(url, headers=None):
        calls.append(url)
        if url == YAHOO_URL.format(symbol="TLT"):
            raise OSError("boom")
        return _FMP_BODY

    history = fetch_dividends("TLT", TODAY, http_get=http_get)
    assert history.source == "fmp"
    assert calls == [YAHOO_URL.format(symbol="TLT"),
                     FMP_URL.format(symbol="TLT", key="test-key")]


def test_fetch_dividends_skips_fmp_without_a_key_configured(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    calls = []

    def http_get(url, headers=None):
        calls.append(url)
        raise OSError("all fail")

    with pytest.raises(FetchError) as exc_info:
        fetch_dividends("TLT", TODAY, http_get=http_get)
    # FMP 完全沒有被打（沒金鑰組不出可呼叫的請求）
    assert not any("financialmodelingprep" in c for c in calls)
    assert "FMP_API_KEY 未設定" in str(exc_info.value)


def test_fetch_dividends_all_fail_raises_fetch_error_naming_each_source(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def http_get(url, headers=None):
        raise OSError("offline")

    with pytest.raises(FetchError) as exc_info:
        fetch_dividends("TLT", TODAY, http_get=http_get)
    message = str(exc_info.value)
    assert "Yahoo" in message and "Nasdaq" in message


def test_yahoo_malformed_json_is_a_fetch_error_not_a_crash():
    def http_get(url, headers=None):
        if url == YAHOO_URL.format(symbol="TLT"):
            return "<html>maintenance</html>"
        raise OSError("no backup either")

    with pytest.raises(FetchError):
        fetch_dividends("TLT", TODAY, http_get=http_get)


# ---------- load_dividend_history 三層 fallback ----------

def test_fresh_fetch_writes_cache_and_notes_the_source(tmp_path):
    history, note = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path, fetch=lambda s, t: _history())
    assert history == _history()
    assert "yahoo" in note and "快取" not in note
    cache_file = tmp_path / "dividend_cache_TLT.json"
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert data["fetched_on"] == TODAY.isoformat()


def test_fetch_failure_uses_cache_within_the_90_day_window(tmp_path):
    fetched_on = date(2026, 5, 15)   # 87 天前，窗內（CACHE_MAX_AGE_DAYS=90）
    assert (TODAY - fetched_on).days <= CACHE_MAX_AGE_DAYS
    load_dividend_history("TLT", fetched_on, cache_dir=tmp_path,
                          fetch=lambda s, t: _history())

    def boom(symbol, today):
        raise FetchError("offline")

    history, note = load_dividend_history("TLT", TODAY, cache_dir=tmp_path,
                                          fetch=boom)
    assert history == dataclasses.replace(_history(), stale=True)
    assert history.stale is True
    assert "快取" in note and fetched_on.isoformat() in note


def test_cache_at_the_90_day_boundary_is_still_used(tmp_path):
    fetched_on = date(2026, 5, 12)
    assert (TODAY - fetched_on).days == CACHE_MAX_AGE_DAYS
    load_dividend_history("TLT", fetched_on, cache_dir=tmp_path,
                          fetch=lambda s, t: _history())
    history, _ = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    assert history.stale is True


def test_cache_past_the_90_day_window_is_not_used(tmp_path):
    fetched_on = date(2026, 5, 11)   # 91 天前，超窗
    assert (TODAY - fetched_on).days == CACHE_MAX_AGE_DAYS + 1
    load_dividend_history("TLT", fetched_on, cache_dir=tmp_path,
                          fetch=lambda s, t: _history())
    history, note = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    assert history is None
    assert "配息資料不可得" in note


def test_no_cache_returns_none(tmp_path):
    history, note = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    assert history is None
    assert "配息資料不可得" in note


def test_corrupt_cache_returns_none_not_crash(tmp_path):
    cache = tmp_path / "dividend_cache_TLT.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{not json", encoding="utf-8")
    history, note = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    assert history is None and "配息資料不可得" in note


def test_cache_is_keyed_per_symbol(tmp_path):
    """研究 §11：配息快取是 per-symbol，跟利率單一全站曲線不同。"""
    load_dividend_history("TLT", TODAY, cache_dir=tmp_path,
                          fetch=lambda s, t: _history("yahoo"))
    load_dividend_history(
        "YETI", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: DividendHistory(symbol="YETI", as_of=TODAY.isoformat(),
                                           source="yahoo", distributions=()))

    tlt_history, _ = load_dividend_history(
        "TLT", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    yeti_history, _ = load_dividend_history(
        "YETI", TODAY, cache_dir=tmp_path,
        fetch=lambda s, t: (_ for _ in ()).throw(FetchError("x")))
    # 兩個都超窗？不——同一天抓的，這裡改用「今天再抓一次都失敗」驗證
    # 各自讀回各自的快取內容，不會互相污染。
    assert tlt_history.symbol == "TLT" and len(tlt_history.distributions) == 2
    assert yeti_history.symbol == "YETI" and yeti_history.distributions == ()


def test_successful_fetch_overwrites_stale_cache(tmp_path):
    load_dividend_history("TLT", date(2026, 1, 2), cache_dir=tmp_path,
                          fetch=lambda s, t: _history())
    fresh = DividendHistory(symbol="TLT", as_of=TODAY.isoformat(), source="nasdaq",
                            distributions=(DividendRecord("2026-08-03", 0.5),))
    history, _ = load_dividend_history("TLT", TODAY, cache_dir=tmp_path,
                                       fetch=lambda s, t: fresh)
    assert history == fresh
    data = json.loads((tmp_path / "dividend_cache_TLT.json").read_text())
    assert data["fetched_on"] == TODAY.isoformat()
    assert data["history"]["source"] == "nasdaq"
