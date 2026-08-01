from datetime import date

import pytest

from option_chaser.models import ParamError
from option_chaser.timeframe import (
    TargetMonth,
    calendar_anchor,
    month_is_over,
    parse_target_month,
    select_expiries,
)


# --- 年月解析 -------------------------------------------------------------

def test_four_written_forms_normalize_to_the_same_month():
    forms = ["2028/1", "2028/01", "28/1", "28/01"]
    assert {parse_target_month(f) for f in forms} == {TargetMonth(2028, 1)}


def test_surrounding_whitespace_is_tolerated():
    assert parse_target_month("  2028/01 ") == TargetMonth(2028, 1)


@pytest.mark.parametrize("bad", [
    "", "   ", "2028", "2028/", "/1", "2028/1/1", "2028-01",
    "abc/1", "2028/abc", "202/1", "2028//1",
])
def test_unparseable_input_raises_with_the_offending_text(bad):
    with pytest.raises(ParamError) as excinfo:
        parse_target_month(bad)
    assert repr(bad) in str(excinfo.value)


@pytest.mark.parametrize("bad", ["2028/13", "2028/0", "2028/99"])
def test_month_outside_1_to_12_is_named_as_such(bad):
    with pytest.raises(ParamError, match="1-12"):
        parse_target_month(bad)


def test_two_digit_year_is_this_century():
    assert parse_target_month("05/3") == TargetMonth(2005, 3)


def test_key_round_trips_the_persisted_form():
    assert TargetMonth(2028, 1).key() == "2028-01"
    assert TargetMonth.from_key("2028-01") == TargetMonth(2028, 1)


@pytest.mark.parametrize("bad", ["2028-1", "202801", "2028/01", "2028-13"])
def test_from_key_rejects_anything_but_yyyy_dash_mm(bad):
    with pytest.raises(ParamError):
        TargetMonth.from_key(bad)


# --- 日曆錨點（該月第三個星期五）------------------------------------------

@pytest.mark.parametrize("year,month,expected", [
    (2028, 1, date(2028, 1, 21)),   # 1 號是星期六 → 最晚的第三個星期五
    (2026, 5, date(2026, 5, 15)),   # 1 號是星期五 → 最早的第三個星期五
    (2026, 9, date(2026, 9, 18)),
    (2027, 12, date(2027, 12, 17)),  # 跨年邊界（前一個月）
    (2028, 2, date(2028, 2, 18)),   # 閏年二月
    (2024, 2, date(2024, 2, 16)),   # 閏年二月（1 號為星期四）
])
def test_calendar_anchor_is_the_third_friday(year, month, expected):
    anchor = calendar_anchor(TargetMonth(year, month))
    assert anchor == expected
    assert anchor.weekday() == 4


def test_anchor_never_leaves_its_own_month():
    for month in range(1, 13):
        anchor = calendar_anchor(TargetMonth(2027, month))
        assert (anchor.year, anchor.month) == (2027, month)
        assert 15 <= anchor.day <= 21


# --- 目標月是否已過完 -----------------------------------------------------

def test_month_is_not_over_on_its_last_day():
    assert month_is_over(TargetMonth(2026, 8), date(2026, 8, 31)) is False


def test_month_is_over_the_day_after_its_last_day():
    assert month_is_over(TargetMonth(2026, 8), date(2026, 9, 1)) is True


def test_current_month_is_not_over_partway_through():
    assert month_is_over(TargetMonth(2026, 8), date(2026, 8, 1)) is False


def test_leap_february_runs_to_the_29th():
    assert month_is_over(TargetMonth(2028, 2), date(2028, 2, 29)) is False
    assert month_is_over(TargetMonth(2028, 2), date(2028, 3, 1)) is True


def test_future_and_past_months():
    assert month_is_over(TargetMonth(2028, 1), date(2026, 8, 1)) is False
    assert month_is_over(TargetMonth(2025, 12), date(2026, 8, 1)) is True


# --- 六點到期日選取 -------------------------------------------------------

ANCHOR = date(2028, 1, 21)


def test_baseline_is_the_expiry_nearest_the_anchor():
    chain = ["2027-11-19", "2027-12-17", "2028-01-14", "2028-02-18", "2028-03-17"]
    assert select_expiries(chain, ANCHOR).baseline == "2028-01-14"


def test_anchor_landing_exactly_on_an_expiry_picks_it():
    chain = ["2027-12-17", "2028-01-21", "2028-02-18"]
    assert select_expiries(chain, ANCHOR).baseline == "2028-01-21"


def test_equal_distance_breaks_toward_the_later_expiry():
    # 2028-01-14 與 2028-01-28 距錨點各 7 天
    chain = ["2028-01-14", "2028-01-28"]
    assert select_expiries(chain, ANCHOR).baseline == "2028-01-28"


def test_two_before_and_two_after_the_baseline():
    chain = ["2027-10-15", "2027-11-19", "2027-12-17", "2028-01-21",
             "2028-02-18", "2028-03-17", "2028-06-16"]
    got = select_expiries(chain, ANCHOR)
    assert got.baseline == "2028-01-21"
    assert got.expiries == ("2027-11-19", "2027-12-17", "2028-01-21",
                            "2028-02-18", "2028-03-17")


def test_short_earlier_side_is_topped_up_from_the_later_side():
    chain = ["2027-12-17", "2028-01-21", "2028-02-18", "2028-03-17", "2028-06-16"]
    got = select_expiries(chain, ANCHOR)
    assert got.expiries == ("2027-12-17", "2028-01-21", "2028-02-18",
                            "2028-03-17", "2028-06-16")


def test_short_later_side_is_topped_up_from_the_earlier_side():
    # 後方只有 1 檔 → 前方補到 3 檔
    chain = ["2027-09-17", "2027-10-15", "2027-11-19", "2027-12-17",
             "2028-01-21", "2028-02-18"]
    got = select_expiries(chain, ANCHOR)
    assert got.baseline == "2028-01-21"
    assert got.expiries == ("2027-10-15", "2027-11-19", "2027-12-17",
                            "2028-01-21", "2028-02-18")


def test_neither_side_can_make_up_the_shortfall():
    chain = ["2027-12-17", "2028-01-21", "2028-02-18", "2028-03-17"]
    got = select_expiries(chain, ANCHOR)
    assert got.expiries == ("2027-12-17", "2028-01-21", "2028-02-18",
                            "2028-03-17")


def test_no_later_expiries_at_all_still_fills_four_from_before():
    chain = ["2027-08-20", "2027-09-17", "2027-10-15", "2027-11-19",
             "2027-12-17", "2028-01-21"]
    got = select_expiries(chain, ANCHOR)
    assert got.baseline == "2028-01-21"
    assert got.expiries == ("2027-09-17", "2027-10-15", "2027-11-19",
                            "2027-12-17", "2028-01-21")


def test_never_returns_more_than_five():
    chain = [f"2028-{m:02d}-17" for m in range(1, 13)]
    assert len(select_expiries(chain, ANCHOR).expiries) == 5


def test_chain_shorter_than_five_returns_everything_it_has():
    chain = ["2027-12-17", "2028-01-21", "2028-02-18"]
    got = select_expiries(chain, ANCHOR)
    assert got.expiries == ("2027-12-17", "2028-01-21", "2028-02-18")


def test_single_expiry_chain_is_its_own_baseline():
    got = select_expiries(["2029-06-15"], ANCHOR)
    assert got.baseline == "2029-06-15"
    assert got.expiries == ("2029-06-15",)


def test_selection_is_sorted_and_deduplicated_regardless_of_input_order():
    chain = ["2028-02-18", "2027-12-17", "2028-01-21", "2027-12-17", "2028-02-18"]
    got = select_expiries(chain, ANCHOR)
    assert got.expiries == ("2027-12-17", "2028-01-21", "2028-02-18")


def test_expiries_earlier_than_the_target_month_are_selectable():
    """需求 §三：baseline 前方最近兩檔可能早於目標月，選取不得砍掉它們。"""
    chain = ["2027-11-19", "2027-12-17", "2028-01-21"]
    got = select_expiries(chain, ANCHOR)
    assert "2027-11-19" in got.expiries and "2027-12-17" in got.expiries


def test_empty_chain_is_a_parameter_error():
    with pytest.raises(ParamError):
        select_expiries([], ANCHOR)


def test_selection_does_not_consume_its_input_iterable():
    chain = ["2027-12-17", "2028-01-21"]
    select_expiries(iter(chain), ANCHOR)
    assert chain == ["2027-12-17", "2028-01-21"]
