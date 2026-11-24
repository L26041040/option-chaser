"""V2-05（#407）：目前股價、報價日期、目標漲跌幅的純邏輯。

期望值都是手算的字面常數（例：平均目標價 120、股價 100 → +20.0%），不是拿
被測函式自己的算式再算一次。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from api_app.analyst_source import FixtureAnalystSource
from api_app.price_quote import (STALE_AFTER_TRADING_DAYS, PriceQuote,
                                 positive_price, quote_record, target_upside_pct,
                                 trading_days_after, upside_fields)
from option_chaser.consensus import SplitEvent

# 2026-11-20（週五）16:00:01 美東 = 21:00:01 UTC：收盤後的 regularMarketTime。
FRI_CLOSE = datetime(2026, 11, 20, 21, 0, 1, tzinfo=timezone.utc)
MON = date(2026, 11, 23)


# ---------- 公式與小數位 ----------

# V2-06（#408）：案例與前端 `src/targetUpside.test.ts` 共用同一份
# （`contracts/target_upside_rounding_cases.json`），公式與小數位規則只有一套。
_ROUNDING_CASES = json.loads(
    Path("contracts/target_upside_rounding_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("mean, price, expected", [
    (c["mean"], c["price"], Decimal(c["expected"])) for c in _ROUNDING_CASES
], ids=[c["note"] for c in _ROUNDING_CASES])
def test_target_upside_pct_formula_and_rounding(mean, price, expected):
    got = target_upside_pct(Decimal(mean), Decimal(price))
    assert got == expected
    assert str(got) == str(expected)          # 一位小數，沒有 "-0.0"


# ---------- 交易日距離（週末不算；不維護假日曆） ----------

@pytest.mark.parametrize("earlier, later, expected", [
    (date(2026, 11, 20), date(2026, 11, 20), 0),   # 同一天
    (date(2026, 11, 20), date(2026, 11, 21), 0),   # 週五 → 週六
    (date(2026, 11, 20), date(2026, 11, 23), 1),   # 週五 → 週一
    (date(2026, 11, 20), date(2026, 11, 25), 3),   # 週五 → 週三
    (date(2026, 11, 20), date(2026, 11, 26), 4),   # 週五 → 週四
    (date(2026, 11, 13), date(2026, 11, 23), 6),
])
def test_trading_days_after(earlier, later, expected):
    assert trading_days_after(earlier, later) == expected


def test_stale_threshold_is_three_trading_days():
    assert STALE_AFTER_TRADING_DAYS == 3


def test_stale_threshold_matches_the_shared_contract():
    """前後端同一份門檻（`contracts/price_stale_threshold.json`，前端
    `src/targetUpside.test.ts` 讀同一份）。"""
    doc = json.loads(Path("contracts/price_stale_threshold.json").read_text(encoding="utf-8"))
    assert STALE_AFTER_TRADING_DAYS == doc["stale_after_trading_days"]


# ---------- 存進快照的報價紀錄 ----------

def test_quote_record_after_close_is_labelled_close_with_new_york_date():
    rec = quote_record(PriceQuote(Decimal("125.53"), FRI_CLOSE), (), MON)
    assert rec == {"price": "125.53", "at": "2026-11-20T21:00:01+00:00",
                   "date": "2026-11-20", "kind": "close",
                   "split_basis_mismatch": False}


def test_quote_record_during_session_is_intraday():
    at = datetime(2026, 11, 23, 15, 30, tzinfo=timezone.utc)   # 10:30 美東
    rec = quote_record(PriceQuote(Decimal("10"), at), (), MON)
    assert rec["date"] == "2026-11-23" and rec["kind"] == "intraday"


def test_quote_record_from_an_earlier_day_is_a_close_even_if_early_session_end():
    # 提早收盤日（13:00 美東）的最後成交，隔天抓到 → 那一天的收盤。
    at = datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc)
    rec = quote_record(PriceQuote(Decimal("10"), at), (), date(2026, 11, 30))
    assert rec["date"] == "2026-11-27" and rec["kind"] == "close"


def test_quote_record_flags_a_split_between_price_date_and_as_of():
    split = SplitEvent(symbol="X", effective_on=MON, ratio=Decimal(10))
    rec = quote_record(PriceQuote(Decimal("1200"), FRI_CLOSE), (split,), MON)
    assert rec["split_basis_mismatch"] is True


def test_quote_record_split_on_or_before_price_date_is_consistent():
    split = SplitEvent(symbol="X", effective_on=date(2026, 11, 20), ratio=Decimal(10))
    rec = quote_record(PriceQuote(Decimal("120"), FRI_CLOSE), (split,), MON)
    assert rec["split_basis_mismatch"] is False


def test_quote_record_none_without_quote():
    assert quote_record(None, (), MON) is None


@pytest.mark.parametrize("price", ["0", "-1.5", "NaN", "Infinity"])
def test_quote_record_drops_a_non_positive_or_non_finite_price(price):
    assert quote_record(PriceQuote(Decimal(price), FRI_CLOSE), (), MON) is None


@pytest.mark.parametrize("raw, expected", [
    ("12.5", Decimal("12.5")), (3, Decimal("3")), ("0", None), (-2, None),
    ("NaN", None), ("abc", None), (None, None), (True, None),
])
def test_positive_price(raw, expected):
    assert positive_price(raw) == expected


# ---------- 畫面欄位與缺資料原因 ----------

def _rec(**over):
    rec = {"price": "100", "at": "2026-11-20T21:00:01+00:00", "date": "2026-11-20",
           "kind": "close", "split_basis_mismatch": False}
    rec.update(over)
    return rec


def test_upside_fields_when_everything_is_available():
    assert upside_fields(_rec(), Decimal("120"), MON) == {
        "price": 100.0, "price_date": "2026-11-20",
        "price_at": "2026-11-20T21:00:01+00:00", "price_kind": "close",
        "target_upside_pct": 20.0, "target_upside_reason": None}


def test_no_price_yet():
    out = upside_fields(None, Decimal("120"), MON)
    assert out["price"] is None and out["price_date"] is None
    assert out["target_upside_pct"] is None
    assert out["target_upside_reason"] == "no_price"


@pytest.mark.parametrize("price", ["0", "-3", "0.00"])
def test_stored_non_positive_price_reads_as_no_price_instead_of_dividing(price):
    """快取裡已經存了 0 或負的股價（舊資料、來源異常）：不除、不 500，照
    「尚未取得股價」處理。"""
    out = upside_fields(_rec(price=price), Decimal("120"), MON)
    assert out["price"] is None and out["target_upside_pct"] is None
    assert out["target_upside_reason"] == "no_price"


@pytest.mark.parametrize("price", ["0", "-10"])
def test_fixture_source_rejects_a_non_positive_price(tmp_path, price):
    """測試資料來源與 Yahoo（`_positive_decimal`）同一條規則：股價 ≤ 0 不算
    取得股價。"""
    path = tmp_path / "fixture.json"
    at = "2026-11-20T21:00:01+00:00"
    path.write_text(json.dumps({"name": "fx", "symbols": {
        "AAA": {"records": [], "quote": {"price": price, "at": at}},
        "BBB": {"records": [], "quote": {"price": "101.5", "at": at}}}}),
        encoding="utf-8")
    src = FixtureAnalystSource(path)
    assert src.fetch("AAA", MON).quote is None
    assert src.fetch("BBB", MON).quote == PriceQuote(Decimal("101.5"), FRI_CLOSE)


def test_price_too_old():
    # 週五收盤，到下週四已過 4 個交易日（> 3）
    out = upside_fields(_rec(), Decimal("120"), date(2026, 11, 26))
    assert out["price"] == 100.0 and out["price_date"] == "2026-11-20"
    assert out["target_upside_pct"] is None
    assert out["target_upside_reason"] == "price_stale"


def test_price_exactly_three_trading_days_old_is_still_used():
    out = upside_fields(_rec(), Decimal("120"), date(2026, 11, 25))
    assert out["target_upside_pct"] == 20.0


def test_no_mean_target():
    out = upside_fields(_rec(), None, MON)
    assert out["price"] == 100.0
    assert out["target_upside_pct"] is None
    assert out["target_upside_reason"] == "no_mean"


def test_split_basis_mismatch_never_divides():
    out = upside_fields(_rec(price="1200", split_basis_mismatch=True),
                        Decimal("130"), MON)
    assert out["price"] == 1200.0
    assert out["target_upside_pct"] is None
    assert out["target_upside_reason"] == "split_mismatch"
