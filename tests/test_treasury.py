# tests/test_treasury.py
"""T12(A) 取得與快取層：CSV→XML→前一年備援、快取 7 日曆日陳舊窗、
三層 fallback（新鮮抓取／快取／退 0.04 由上層決定）。全部離線（假抓取器）。"""
import dataclasses
import json
from datetime import date

import pytest

from option_chaser.data import treasury
from option_chaser.models import FetchError
from option_chaser.data.treasury import (CACHE_MAX_AGE_DAYS, CSV_URL, XML_URL,
                                         fetch_curve, fetch_curve_range,
                                         fetch_curve_rows_for_year,
                                         load_rate_curve)
from option_chaser.ratecurve import RateCurve, par_to_continuous

TODAY = date(2026, 7, 31)

CSV_TEXT = ('Date,"1 Mo","1 Yr","2 Yr"\n'
            "07/31/2026,4.30,4.00,4.20\n")
XML_TEXT = ('<feed xmlns:d="urn:x"><entry>'
            "<d:NEW_DATE>2026-07-30T00:00:00</d:NEW_DATE>"
            "<d:BC_1MONTH>4.31</d:BC_1MONTH><d:BC_2YEAR>4.19</d:BC_2YEAR>"
            "</entry></feed>")


def _curve() -> RateCurve:
    return RateCurve(curve_date="2026-07-31",
                     nodes=((1 / 12, par_to_continuous(0.0430)),
                            (2.0, par_to_continuous(0.0420))))


# ---------- fetch_curve 端點備援次序 ----------

def test_fetch_curve_csv_first():
    calls = []

    def http_get(url):
        calls.append(url)
        return CSV_TEXT

    curve = fetch_curve(TODAY, http_get=http_get)
    assert curve.curve_date == "2026-07-31"
    assert calls == [CSV_URL.format(year=2026)]


def test_fetch_curve_falls_back_to_xml_then_prior_year():
    calls = []

    def http_get(url):
        calls.append(url)
        if url == CSV_URL.format(year=2026):
            raise OSError("boom")
        if url == XML_URL.format(year=2026):
            return "<html>maintenance</html>"      # 解析失敗也要繼續備援
        return CSV_TEXT

    curve = fetch_curve(TODAY, http_get=http_get)
    assert curve.curve_date == "2026-07-31"
    assert calls == [CSV_URL.format(year=2026), XML_URL.format(year=2026),
                     CSV_URL.format(year=2025)]


def test_fetch_curve_xml_used_when_csv_unparseable():
    def http_get(url):
        if url == CSV_URL.format(year=2026):
            return "<html>err</html>"
        return XML_TEXT

    assert fetch_curve(TODAY, http_get=http_get).curve_date == "2026-07-30"


def test_fetch_curve_all_fail_raises_fetch_error():
    def http_get(url):
        raise OSError("offline")

    with pytest.raises(FetchError):
        fetch_curve(TODAY, http_get=http_get)


def test_fetch_curve_failure_message_names_the_source_and_stage():
    """#74：失敗訊息要看得出是哪個來源、哪一段失敗，不是一句籠統的
    「抓取失敗」。"""
    def http_get(url):
        raise OSError("connection refused")

    with pytest.raises(FetchError) as exc_info:
        fetch_curve(TODAY, http_get=http_get)

    message = str(exc_info.value)
    assert "Treasury" in message
    assert "CSV" in message and "XML" in message   # 兩種格式都試過
    assert "connection refused" in message


# ---------- fetch_curve_rows_for_year／fetch_curve_range（issue #160 前置件） ----------

def test_fetch_curve_rows_for_year_returns_every_row_via_csv():
    calls = []

    def http_get(url):
        calls.append(url)
        return CSV_TEXT

    rows = fetch_curve_rows_for_year(2026, http_get=http_get)
    assert [d for d, _ in rows] == ["2026-07-31"]
    assert calls == [CSV_URL.format(year=2026)]


def test_fetch_curve_rows_for_year_falls_back_to_xml_when_csv_fails():
    def http_get(url):
        if url == CSV_URL.format(year=2026):
            raise OSError("boom")
        return XML_TEXT

    rows = fetch_curve_rows_for_year(2026, http_get=http_get)
    assert [d for d, _ in rows] == ["2026-07-30"]


def test_fetch_curve_rows_for_year_raises_when_both_sources_fail():
    def http_get(url):
        raise OSError("offline")

    with pytest.raises(FetchError):
        fetch_curve_rows_for_year(2026, http_get=http_get)


def test_fetch_curve_range_concatenates_rows_across_years():
    csv_2025 = ('Date,"1 Mo","1 Yr"\n' "12/31/2025,4.10,3.90\n")
    csv_2026 = ('Date,"1 Mo","1 Yr"\n' "01/02/2026,4.11,3.91\n")

    def http_get(url):
        if url == CSV_URL.format(year=2025):
            return csv_2025
        if url == CSV_URL.format(year=2026):
            return csv_2026
        raise OSError("unexpected url")

    rows = fetch_curve_range(date(2025, 12, 31), date(2026, 1, 2),
                             http_get=http_get)
    assert [d for d, _ in rows] == ["2025-12-31", "2026-01-02"]


def test_fetch_curve_range_skips_a_year_that_fails_entirely_instead_of_raising():
    """單一年份 CSV／XML 兩者皆失敗，不讓整段跨年查詢報廢——其他年份
    抓到的資料照樣回傳，缺口留給 `curve_asof` 對落在缺口裡的觀察日
    自然回傳 None。"""
    def http_get(url):
        if url == CSV_URL.format(year=2026) or url == XML_URL.format(year=2026):
            raise OSError("offline for 2026")
        return CSV_TEXT

    rows = fetch_curve_range(date(2025, 1, 1), date(2026, 12, 31),
                             http_get=http_get)
    assert [d for d, _ in rows] == ["2026-07-31"]   # 只剩 2025 那年成功


def test_fetch_curve_range_within_a_single_year():
    def http_get(url):
        assert url == CSV_URL.format(year=2026)
        return CSV_TEXT

    rows = fetch_curve_range(date(2026, 1, 1), date(2026, 12, 31),
                             http_get=http_get)
    assert [d for d, _ in rows] == ["2026-07-31"]


# ---------- `_http_get`：#74 硬化（真實標頭、明確檢查狀態碼） ----------

class _FakeHttpResponse:
    def __init__(self, status: int, body: bytes = b""):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_get_sends_browser_like_headers(monkeypatch):
    """只帶一個非常規 User-Agent（舊版是裸字串 "option-chaser"）前置
    CDN／WAF 常直接擋——#74 硬化成一般瀏覽器等級標頭。"""
    captured = {}

    def fake_urlopen(req, timeout):
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        return _FakeHttpResponse(200, b"ok")

    monkeypatch.setattr(treasury, "urlopen", fake_urlopen)

    treasury._http_get("https://example.test/x")

    ua = captured["headers"].get("user-agent", "")
    assert "Mozilla" in ua and "Chrome" in ua
    assert "accept" in captured["headers"]
    assert "accept-language" in captured["headers"]


def test_http_get_rejects_a_non_200_status_without_reaching_the_caller(monkeypatch):
    """明確檢查狀態碼（#74）——`urlopen` 對 4xx/5xx 本來就會拋
    `HTTPError`，這裡額外擋 2xx 但非 200 的情況（例如 204），讓
    「這個來源這次失敗了」不必等到後面解析階段才發現。"""
    monkeypatch.setattr(treasury, "urlopen",
                        lambda req, timeout: _FakeHttpResponse(204, b""))

    with pytest.raises(FetchError, match="204"):
        treasury._http_get("https://example.test/x")


def test_http_get_wraps_an_http_error_with_the_status_code(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(req, timeout):
        raise HTTPError("https://example.test/x", 403, "Forbidden", {}, None)

    monkeypatch.setattr(treasury, "urlopen", fake_urlopen)

    with pytest.raises(FetchError, match="403"):
        treasury._http_get("https://example.test/x")


# ---------- load_rate_curve 三層 fallback ----------

def test_fresh_fetch_writes_cache_and_notes_curve_date(tmp_path):
    cache = tmp_path / "cache.json"
    curve, note = load_rate_curve(TODAY, cache_path=cache,
                                  fetch=lambda today: _curve())
    assert curve == _curve()
    assert "2026-07-31" in note and "快取" not in note
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["fetched_on"] == TODAY.isoformat()


def test_fetch_failure_uses_cache_within_window(tmp_path):
    cache = tmp_path / "cache.json"
    fetched_on = date(2026, 7, 25)                      # 6 天前，窗內
    load_rate_curve(fetched_on, cache_path=cache, fetch=lambda t: _curve())

    def boom(today):
        raise FetchError("offline")

    curve, note = load_rate_curve(TODAY, cache_path=cache, fetch=boom)
    # RC1（#87）：沿用陳舊本地快取——曲線內容一致，但要標成 stale，
    # 不能跟新鮮抓取顯示成同一態。
    assert curve == dataclasses.replace(_curve(), stale=True)
    assert curve.stale is True
    assert "快取" in note and fetched_on.isoformat() in note


def test_cache_at_window_boundary_still_used(tmp_path):
    cache = tmp_path / "cache.json"
    fetched_on = date(2026, 7, 24)                      # 剛好 7 日曆日
    assert (TODAY - fetched_on).days == CACHE_MAX_AGE_DAYS
    load_rate_curve(fetched_on, cache_path=cache, fetch=lambda t: _curve())
    curve, _ = load_rate_curve(TODAY, cache_path=cache,
                               fetch=lambda t: (_ for _ in ()).throw(OSError()))
    assert curve == dataclasses.replace(_curve(), stale=True)
    assert curve.stale is True


def test_stale_cache_returns_none(tmp_path):
    cache = tmp_path / "cache.json"
    fetched_on = date(2026, 7, 23)                      # 8 天前，超窗
    load_rate_curve(fetched_on, cache_path=cache, fetch=lambda t: _curve())
    curve, note = load_rate_curve(
        TODAY, cache_path=cache,
        fetch=lambda t: (_ for _ in ()).throw(OSError()))
    assert curve is None
    assert "曲線不可得" in note


def test_no_cache_returns_none(tmp_path):
    curve, note = load_rate_curve(
        TODAY, cache_path=tmp_path / "missing.json",
        fetch=lambda t: (_ for _ in ()).throw(FetchError("x")))
    assert curve is None
    assert "曲線不可得" in note


def test_corrupt_cache_returns_none_not_crash(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text("{not json", encoding="utf-8")
    curve, note = load_rate_curve(
        TODAY, cache_path=cache,
        fetch=lambda t: (_ for _ in ()).throw(OSError()))
    assert curve is None and "曲線不可得" in note


def test_successful_fetch_overwrites_stale_cache(tmp_path):
    cache = tmp_path / "cache.json"
    load_rate_curve(date(2026, 1, 2), cache_path=cache, fetch=lambda t: _curve())
    fresh = RateCurve(curve_date="2026-07-31", nodes=((1.0, 0.041),))
    curve, _ = load_rate_curve(TODAY, cache_path=cache, fetch=lambda t: fresh)
    assert curve == fresh
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["fetched_on"] == TODAY.isoformat()
    assert data["curve"]["nodes"] == [[1.0, 0.041]]
