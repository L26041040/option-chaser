"""T6（#20）／需求六: 劇本級狀態燈號（純函式，窮盡三色規則＋紅燈優先）。"""
from datetime import date

from option_chaser import workspace
from option_chaser.timeframe import TargetMonth

MONTH = TargetMonth(2028, 1)   # 最後一天 2028-01-31
NOT_OVER = date(2028, 1, 31)   # 最後一天當天——尚未過完
OVER = date(2028, 2, 1)        # 翌日——過完


def test_success_is_green():
    assert workspace.scenario_signal(
        MONTH, NOT_OVER, workspace.REFRESH_OK) == workspace.SIGNAL_GREEN


def test_critical_failure_is_yellow():
    assert workspace.scenario_signal(
        MONTH, NOT_OVER, workspace.REFRESH_CRITICAL_FAILURE
    ) == workspace.SIGNAL_YELLOW


def test_never_refreshed_is_unknown():
    assert workspace.scenario_signal(
        MONTH, NOT_OVER, workspace.REFRESH_NEVER) == workspace.SIGNAL_UNKNOWN


def test_month_over_is_red_even_on_success():
    assert workspace.scenario_signal(
        MONTH, OVER, workspace.REFRESH_OK) == workspace.SIGNAL_RED


def test_red_takes_priority_over_critical_failure():
    """紅燈優先於黃燈：失效劇本不會偽裝成「只是刷新失敗」。"""
    assert workspace.scenario_signal(
        MONTH, OVER, workspace.REFRESH_CRITICAL_FAILURE
    ) == workspace.SIGNAL_RED


def test_red_takes_priority_over_never_refreshed():
    assert workspace.scenario_signal(
        MONTH, OVER, workspace.REFRESH_NEVER) == workspace.SIGNAL_RED


def test_last_day_of_month_is_not_yet_over():
    """紅燈判定邊界：目標月最後一天當天尚未算過完（need month_is_over 語意）。"""
    assert workspace.scenario_signal(
        MONTH, date(2028, 1, 31), workspace.REFRESH_OK) == workspace.SIGNAL_GREEN


def test_day_after_last_day_is_over():
    assert workspace.scenario_signal(
        MONTH, date(2028, 2, 1), workspace.REFRESH_OK) == workspace.SIGNAL_RED
