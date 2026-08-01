# tests/test_treasury.py
"""T12(A) 取得與快取層：CSV→XML→前一年備援、快取 7 日曆日陳舊窗、
三層 fallback（新鮮抓取／快取／退 0.04 由上層決定）。全部離線（假抓取器）。"""
import json
from datetime import date

import pytest

from option_chaser.models import FetchError
from option_chaser.data.treasury import (CACHE_MAX_AGE_DAYS, CSV_URL, XML_URL,
                                         fetch_curve, load_rate_curve)
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
    assert curve == _curve()
    assert "快取" in note and fetched_on.isoformat() in note


def test_cache_at_window_boundary_still_used(tmp_path):
    cache = tmp_path / "cache.json"
    fetched_on = date(2026, 7, 24)                      # 剛好 7 日曆日
    assert (TODAY - fetched_on).days == CACHE_MAX_AGE_DAYS
    load_rate_curve(fetched_on, cache_path=cache, fetch=lambda t: _curve())
    curve, _ = load_rate_curve(TODAY, cache_path=cache,
                               fetch=lambda t: (_ for _ in ()).throw(OSError()))
    assert curve == _curve()


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
