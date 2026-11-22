"""LIVE-T2（#399）：以**錄下的真實 Yahoo 回應**重建每月共識序列與個股明細。

輸入是 `tests/fixtures/yahoo/` 的真實樣本（AAPL／NVDA／BABA 2026-11-22、
AMZN／GOOGL 2026-11-23 錄製，不含任何秘密），經 `YahooAnalystSource` 轉成
`AnalystTargetRecord`，再交給既有共識引擎；規則與部署環境相同
（`ConsensusRules(aliases=FIRM_ALIASES)`，見 `api/index.py`）。測試不連外。

期望值是直接讀 fixture 得出的字面常數（券商、日期、目標價），不是拿引擎
自己算；只有 point-in-time 那條用「把未來紀錄拿掉重算」這條獨立路徑對照。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from option_chaser.consensus import ConsensusRules, compute_snapshot
from option_chaser.data.yahoo_analyst import FIRM_ALIASES
from tests.test_yahoo_analyst_source import _fetch

RULES = ConsensusRules(aliases=FIRM_ALIASES)
NVDA_DAY = date(2026, 11, 21)          # #397 實測時被誤判 split_unresolved 的那天


def _source(symbol):
    result, _ = _fetch(symbol)
    assert result.error is None
    return result


def _snapshot(symbol, as_of, *, records=None, splits=None, rules=RULES):
    result = _source(symbol)
    return compute_snapshot(result.records if records is None else records,
                            result.splits if splits is None else splits,
                            as_of, rules, coverage=result.coverage)


# --- 疑似分割誤判（#399 留言：NVDA Bernstein 400 → 200） --------------------

def test_nvda_target_cuts_stated_by_the_firms_are_not_a_suspected_split():
    snap = _snapshot("NVDA", NVDA_DAY)
    assert snap.status == "ok"
    assert not any(r.startswith("split_unresolved") for r in snap.reasons)
    # Bernstein 2026-11-12 寫 200（prior 400、Lowers）照常進有效集合
    [bernstein] = [e for e in snap.effective if e.firm == "Bernstein"]
    assert (bernstein.target_price, bernstein.published_on) == (Decimal(200), date(2026, 11, 12))
    assert bernstein.prior_target == Decimal(400) and bernstein.action == "Lowers"
    # 過去 12 個月內 Raymond James 165 →（漏記）→ 323（prior 291）等也不再剔除歷史點
    assert snap.history_points == 60
    assert all(p.qualified for p in snap.series)


def test_the_same_real_jump_without_a_stated_prior_is_still_flagged():
    result = _source("NVDA")
    unexplained = [replace(r, prior_target=None) for r in result.records]
    snap = _snapshot("NVDA", NVDA_DAY, records=unexplained)
    assert snap.status == "split_unresolved"
    assert any("Bernstein" in r for r in snap.reasons)


def test_rebasing_records_across_a_missing_split_calendar_are_still_caught():
    # AMZN 2022-06-06 20:1：分割後各家發的「Adjusts」紀錄（prior＝分割前原值）
    # 不能把缺漏的分割日曆蓋掉——拿掉分割日曆時 2022 年中的取樣點必須被剔除。
    snap = _snapshot("AMZN", date(2026, 11, 21), splits=[])
    mid_2022 = [p for p in snap.series if date(2022, 6, 30) <= p.on <= date(2022, 11, 30)]
    assert mid_2022 and all(p.reason == "split_unresolved" for p in mid_2022)


# --- 每月序列：point-in-time ------------------------------------------------

def test_each_monthly_point_uses_only_records_published_by_that_month_end():
    result = _source("AAPL")
    snap = _snapshot("AAPL", date(2026, 11, 20))
    assert [p.on for p in snap.series][:2] == [date(2021, 11, 30), date(2021, 12, 31)]
    one_point = replace(RULES, lookback_points=1)
    for point in snap.series[::6]:
        past_only = [r for r in result.records if r.published_on <= point.on]
        ref = compute_snapshot(past_only, result.splits, point.on, one_point)
        assert (point.n_analysts, point.mean, point.dispersion) == (
            ref.n_analysts, ref.mean, ref.dispersion), point.on


def test_history_is_exactly_the_qualified_points_of_the_monthly_series():
    snap = _snapshot("BABA", date(2026, 11, 20))
    assert snap.history == tuple((p.on, p.dispersion) for p in snap.series if p.qualified)
    assert snap.history_points == sum(p.qualified for p in snap.series)


# --- 跨分割月份：D 不爆量（AMZN／GOOGL 2022 20:1） ----------------------------

@pytest.mark.parametrize("symbol", ["AMZN", "GOOGL"])
def test_dispersion_does_not_blow_up_across_the_2022_split(symbol):
    snap = _snapshot(symbol, date(2026, 11, 21))
    around = [p for p in snap.series if date(2022, 3, 31) <= p.on <= date(2022, 11, 30)]
    assert len(around) == 9
    assert all(p.qualified for p in around)
    # 換算正確時 2022 年各月 D 都在 0.08–0.21；沒換算會到 1.3–2.4
    assert all(Decimal("0.05") < p.dispersion < Decimal("0.25") for p in around)
    unadjusted = _snapshot(symbol, date(2026, 11, 21), splits=[])
    assert max(p.dispersion for p in unadjusted.series
               if date(2022, 7, 29) <= p.on <= date(2022, 11, 30)) > Decimal(1)


def test_effective_set_reports_both_the_raw_and_the_split_adjusted_target():
    # AAPL 2020-08-31 4:1 分割前一個交易日：富國 121.25 已是分割後基準 → 換回 485
    snap = _snapshot("AAPL", date(2020, 8, 28), rules=replace(RULES, h_min=1))
    [wells] = [e for e in snap.effective if e.firm == "Wells Fargo"]
    assert wells.target_price == Decimal("121.25")
    assert wells.adjusted_price == Decimal("485.00")
    [bofa] = [e for e in snap.effective if e.firm == "B of A Securities"]
    assert bofa.target_price == bofa.adjusted_price == Decimal(470)


# --- 同券商多筆只取最新一筆；過期剔除 ----------------------------------------

def test_only_the_latest_target_per_firm_is_in_the_effective_set():
    snap = _snapshot("NVDA", NVDA_DAY)
    # Morgan Stanley：11-11 300、11-16 267、11-18 260 → 只留 260
    [ms] = [e for e in snap.effective if e.firm == "Morgan Stanley"]
    assert (ms.target_price, ms.published_on) == (Decimal(260), date(2026, 11, 18))
    keys = [e.analyst_key for e in snap.effective]
    assert len(keys) == len(set(keys)) == snap.n_analysts == 35


def test_targets_older_than_the_validity_window_are_dropped():
    # Deutsche Bank／Susquehanna 最後一筆都在 2025-11-20：12 個月有效期內
    # 2026-11-20 還算、2026-11-21 剔除；Loop Capital（2025-11-03）兩天都剔除。
    firms = lambda day: {e.firm for e in _snapshot("NVDA", day).effective}
    on_edge, past_edge = firms(date(2026, 11, 20)), firms(NVDA_DAY)
    assert {"Deutsche Bank", "Susquehanna"} <= on_edge
    assert not {"Deutsche Bank", "Susquehanna", "Loop Capital"} & past_edge
    assert "Loop Capital" not in on_edge
