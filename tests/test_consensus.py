"""OS-01 共識計算核心（#390；規格 #389 §2–§4＋留言 A1–A4）。

只測公開介面：`compute_snapshot`、`evaluate_gate`、`target_month`、
`dispersion_percentile`。期望值一律來自規格的計算範例或手算，不用模組自己的
算法重算。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext

import pytest

from option_chaser.consensus import (
    AnalystTargetRecord,
    ConsensusCrossCheck,
    ConsensusRules,
    SplitEvent,
    compute_snapshot,
    dispersion_percentile,
    evaluate_gate,
    target_month,
)

AS_OF = date(2026, 11, 18)
RETRIEVED = datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc)


def rec(key: str, price, published_on: date, *, symbol: str = "XYZ",
        retrieved_at: datetime = RETRIEVED,
        split_adjusted_through: date | None = None) -> AnalystTargetRecord:
    return AnalystTargetRecord(
        symbol=symbol,
        analyst_key=key,
        firm=key,
        target_price=Decimal(str(price)),
        published_on=published_on,
        source="fixture",
        retrieved_at=retrieved_at,
        split_adjusted_through=split_adjusted_through,
    )


def five(prices=(110, 115, 120, 125, 130), published_on=date(2026, 11, 1)):
    return [rec(f"Firm {i}", p, published_on) for i, p in enumerate(prices)]


# --- §4.5 例 1：當日數值 ---------------------------------------------------

def test_example_1_sample_stdev_dispersion():
    snap = compute_snapshot(five(), [], AS_OF, ConsensusRules())
    assert snap.n_analysts == 5
    assert snap.mean == Decimal(120)
    assert round(snap.stdev, 3) == Decimal("7.906")
    assert round(snap.dispersion, 4) == Decimal("0.0659")
    assert (snap.high, snap.low) == (Decimal(130), Decimal(110))


def test_example_1_population_stdev_dispersion():
    snap = compute_snapshot(five(), [], AS_OF,
                            ConsensusRules(stdev_kind="population"))
    assert round(snap.stdev, 3) == Decimal("7.071")
    assert round(snap.dispersion, 4) == Decimal("0.0589")


# --- §4.1 有效集合 S(t) ----------------------------------------------------

def test_only_latest_record_per_analyst_counts():
    records = five() + [rec("Firm 0", 999, date(2026, 6, 1))]   # 較舊，被取代
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.n_analysts == 5
    assert snap.mean == Decimal(120)


def test_example_7_target_older_than_validity_is_dropped():
    # Firm 5 最新一筆是 13 個月前 → 不計入；剛好 12 個月前的 Firm 6 仍有效
    records = five() + [rec("Firm 5", 500, date(2025, 10, 18)),
                        rec("Firm 6", 120, date(2025, 11, 18))]
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.n_analysts == 6
    assert snap.mean == Decimal(120)


def test_an_expired_latest_does_not_fall_back_to_an_older_record():
    records = five() + [rec("Firm 5", 500, date(2025, 9, 1)),
                        rec("Firm 5", 400, date(2025, 8, 1))]
    assert compute_snapshot(records, [], AS_OF).n_analysts == 5


def test_records_published_after_as_of_are_invisible():
    base = compute_snapshot(five(), [], AS_OF)
    future = five() + [rec("Firm 0", 999, date(2026, 11, 19)),
                       rec("Late Firm", 1, date(2027, 1, 5))]
    snap = compute_snapshot(future, [], AS_OF)
    assert (snap.n_analysts, snap.mean, snap.dispersion) == (
        base.n_analysts, base.mean, base.dispersion)


def test_rating_only_records_are_discarded():
    records = five() + [rec("Ratings Only", 1, date(2026, 11, 2))]
    records[-1] = AnalystTargetRecord(
        symbol="XYZ", analyst_key="Ratings Only", firm="Ratings Only",
        target_price=None, published_on=date(2026, 11, 2))
    assert compute_snapshot(records, [], AS_OF).n_analysts == 5


# --- A3 正規化與去重 -------------------------------------------------------

def test_key_case_and_whitespace_variants_are_one_analyst():
    records = five() + [rec("  firm   0 ", 130, date(2026, 11, 10))]
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.n_analysts == 5
    assert snap.mean == Decimal(124)        # Firm 0 改為 130：(130+115+120+125+130)/5


def test_alias_table_merges_a_renamed_firm():
    records = five() + [rec("Cowen & Co.", 100, date(2026, 3, 1)),
                        rec("TD Cowen", 140, date(2026, 10, 1))]
    rules = ConsensusRules(aliases={"cowen & co.": "TD Cowen"})
    snap = compute_snapshot(records, [], AS_OF, rules)
    assert snap.n_analysts == 6
    assert snap.high == Decimal(140)
    # 別名表本身的 key 也正規化
    loose = ConsensusRules(aliases={"  COWEN  &  Co. ": " td  cowen"})
    assert compute_snapshot(records, [], AS_OF, loose).n_analysts == 6


def test_same_day_duplicates_pick_latest_retrieval_then_highest_price():
    day = date(2026, 11, 10)
    early = datetime(2026, 11, 10, 14, tzinfo=timezone.utc)
    late = datetime(2026, 11, 10, 20, tzinfo=timezone.utc)
    by_retrieval = five() + [rec("Firm 0", 200, day, retrieved_at=early),
                             rec("Firm 0", 150, day, retrieved_at=late)]
    assert compute_snapshot(by_retrieval, [], AS_OF).high == Decimal(150)
    by_price = five() + [rec("Firm 0", 150, day), rec("Firm 0", 160, day)]
    assert compute_snapshot(by_price, [], AS_OF).high == Decimal(160)


def test_input_order_does_not_change_the_snapshot():
    day = date(2026, 11, 10)
    records = five() + [rec("Firm 0", 150, day), rec("firm 0", 160, day),
                        rec("FIRM 0", 140, day), rec("Firm 9", 118, date(2026, 9, 9))]
    forward = compute_snapshot(records, [], AS_OF)
    assert compute_snapshot(list(reversed(records)), [], AS_OF) == forward
    shuffled = records[3:] + records[:3]
    assert compute_snapshot(shuffled, [], AS_OF) == forward


# --- §4.1 步驟 2／A2 分割調整 ----------------------------------------------

SPLIT_DAY = date(2026, 8, 3)
SPLIT_4_1 = SplitEvent(symbol="XYZ", effective_on=SPLIT_DAY, ratio=Decimal(4))


def split_records(**pre_kwargs):
    # 例 5：4:1 分割前發布 600、分割後 160、155；另補兩家讓 n ≥ N_min
    return [rec("Pre Split", 600, date(2026, 7, 1), **pre_kwargs),
            rec("Post A", 160, date(2026, 9, 1)),
            rec("Post B", 155, date(2026, 9, 2)),
            rec("Post C", 150, date(2026, 10, 1)),
            rec("Post D", 160, date(2026, 10, 2))]


def test_example_5_pre_split_target_is_divided_by_ratio():
    snap = compute_snapshot(split_records(), [SPLIT_4_1], AS_OF)
    assert snap.high == Decimal(160)
    assert snap.low == Decimal(150)               # 600 / 4，而不是 600
    assert snap.mean == Decimal(155)


def test_a2_record_already_adjusted_through_the_split_is_not_adjusted_again():
    records = split_records(split_adjusted_through=date(2026, 8, 10))
    records[0] = rec("Pre Split", 150, date(2026, 7, 1),
                     split_adjusted_through=date(2026, 8, 10))
    snap = compute_snapshot(records, [SPLIT_4_1], AS_OF)
    assert snap.low == Decimal(150)               # 不會變成 37.5


def test_a2_adjustment_is_recomputed_from_raw_and_never_written_back():
    records = split_records()
    first = compute_snapshot(records, [SPLIT_4_1], AS_OF)
    second = compute_snapshot(records, [SPLIT_4_1], AS_OF)
    assert first == second
    assert records[0].target_price == Decimal(600)


def test_a4_split_effective_after_as_of_is_not_applied():
    early = date(2026, 7, 31)
    records = [rec(f"Firm {i}", p, date(2026, 7, 1))
               for i, p in enumerate((600, 620, 640, 600, 610))]
    later_split = SplitEvent(symbol="XYZ", effective_on=date(2026, 8, 3),
                             ratio=Decimal(4))
    snap = compute_snapshot(records, [later_split], early)
    assert snap.mean == Decimal(614)


# --- §4.3 百分位：midrank（PR-REVIEW-001 取代 A1 的嚴格小於），容許 1e-9 ------

E8 = Decimal("0.08")


@pytest.mark.parametrize("history, today, expected", [
    ([E8] * 30, E8, Decimal("0.5")),                    # 1. 全 8%、今天 8% → 50%
    ([E8] * 30, Decimal("0.05"), Decimal(0)),           # 2. 今天 5% → 0%
    ([E8] * 30, Decimal("0.12"), Decimal(1)),           # 3. 今天 12% → 100%
    ([0] * 30, 0, Decimal("0.5")),                      # 5. 全 0、今天 0 → 50%（不特例放行）
    ([Decimal("0.01")] * 20, 0, Decimal(0)),            # 6. 今天 0、歷史全 > 0 → 0%
    ([0.1 + 0.2] * 10, 0.3, Decimal("0.5")),            # 浮點誤差視為相等
    ([0.3] * 10, 0.1 + 0.2, Decimal("0.5")),
])
def test_percentile_uses_midrank_for_ties(history, today, expected):
    assert dispersion_percentile(history, today) == expected


def test_partial_ties_get_the_middle_rank():
    # 4. 部分同值：10 點中 2 點較低、4 點相等、4 點較高 → (2 + 0.5×4) / 10 = 40%
    history = ([Decimal("0.03")] * 2 + [Decimal("0.05")] * 4
               + [Decimal("0.09")] * 4)
    assert dispersion_percentile(history, Decimal("0.05")) == Decimal("0.4")


@pytest.mark.parametrize("today, expected", [
    (E8, False),                # 50% > 20%
    (Decimal("0.05"), True),    # 0% ≤ 20%
    (Decimal("0.12"), False),   # 100%
])
def test_flat_history_first_gate_outcomes(today, expected):
    p = dispersion_percentile([E8] * 30, today)
    assert (p <= Decimal("0.20")) is expected


def test_example_2_nine_of_sixty_lower_is_15_percent():
    history = [Decimal("0.01")] * 9 + [Decimal("0.09")] * 51
    assert dispersion_percentile(history, Decimal("0.05")) == Decimal("0.15")


def test_percentile_with_no_ties_matches_the_original_definition():
    history = [Decimal(i) / 100 for i in range(1, 11)]      # 0.01 … 0.10
    assert dispersion_percentile(history, Decimal("0.035")) == Decimal("0.3")


def test_percentile_needs_at_least_one_history_point():
    with pytest.raises(ValueError):
        dispersion_percentile([], Decimal("0.05"))


# --- §4.3 自身歷史序列 ------------------------------------------------------

def spread_targets(spread):
    """D 與 spread 成正比（樣本 stdev = spread × √2.5）；只要排序關係。"""
    return [100 - 2 * spread, 100 - spread, 100, 100 + spread, 100 + 2 * spread]


def monthly(spreads, *, last_month=(2026, 10), firms=5):
    """每月 1 日，5 家各發布一次；spreads 由舊到新，最後一個落在 last_month。"""
    y, m = last_month
    out = []
    for back, spread in enumerate(reversed(spreads)):
        idx = y * 12 + m - 1 - back
        day = date(idx // 12, idx % 12 + 1, 1)
        out += [rec(f"Firm {i}", p, day)
                for i, p in enumerate(spread_targets(spread)[:firms])]
    return out


def today_records(spread=5, day=date(2026, 11, 2)):
    return [rec(f"Firm {i}", p, day) for i, p in enumerate(spread_targets(spread))]


def test_example_2_through_compute_snapshot():
    records = monthly([1] * 9 + [9] * 51) + today_records(5)
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.history_points == 60
    assert snap.percentile == Decimal("0.15")
    assert snap.status == "ok"
    assert snap.reasons == ()


def test_history_samples_last_weekday_of_each_month_strictly_before_as_of():
    snap = compute_snapshot(monthly([3] * 60), [], date(2026, 10, 30))
    dates = [d for d, _ in snap.history]
    assert date(2026, 10, 30) not in dates          # 評估日本身不計入（A4）
    assert dates[-1] == date(2026, 9, 30)
    assert date(2026, 2, 27) in dates               # 2/28 是星期六
    assert date(2025, 8, 29) in dates               # 8/31 是星期日
    assert dates == sorted(dates)


def test_history_is_capped_at_lookback_points():
    snap = compute_snapshot(monthly([3] * 70) + today_records(), [], AS_OF)
    assert snap.history_points == 60
    assert snap.history[0][0] == date(2021, 11, 30)


def test_sample_points_below_n_min_are_not_counted():
    thin = monthly([3] * 10, last_month=(2024, 10), firms=4)   # 只有 4 家
    full = monthly([3] * 24)
    snap = compute_snapshot(thin + full + today_records(), [], AS_OF)
    assert snap.history_points == 24


def test_short_history_is_insufficient_history():
    snap = compute_snapshot(monthly([3] * 23) + today_records(), [], AS_OF)
    assert snap.history_points == 23
    assert snap.status == "insufficient_history"
    assert any(r.startswith("insufficient_history") for r in snap.reasons)


def test_a4_record_published_after_as_of_changes_neither_today_nor_history():
    records = monthly([1] * 9 + [9] * 51) + today_records(5)
    base = compute_snapshot(records, [], AS_OF)
    later = records + [rec("Firm 0", 300, date(2026, 11, 19)),
                       rec("New Firm", 80, date(2026, 12, 1))]
    snap = compute_snapshot(later, [], AS_OF)
    assert (snap.dispersion, snap.history, snap.percentile) == (
        base.dispersion, base.history, base.percentile)


# --- 資料不足與資料品質 status ---------------------------------------------

def good_history():
    return monthly([3] * 30)


def statuses(snap):
    return [r.split(":", 1)[0] for r in snap.reasons]


def test_example_4_four_analysts_is_insufficient_analysts_even_with_low_dispersion():
    four = [rec(f"Firm {i}", p, date(2026, 11, 2))
            for i, p in enumerate((98, 100, 102, 100))]
    # Firm 4 只出現在歷史裡；拿掉它，今天才是真的 4 家
    records = [r for r in good_history() if r.analyst_key != "Firm 4"] + four
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.n_analysts == 4
    assert round(snap.dispersion, 4) == Decimal("0.0163")    # 1.63%，很集中
    assert snap.status == "insufficient_analysts"


def test_stale_when_too_few_targets_updated_within_freshness_window():
    july_history = monthly([3] * 30, last_month=(2026, 7))
    old = date(2026, 8, 1)                       # 109 天前
    fresh_day = date(2026, 8, 20)                # 剛好 90 天前：算新鮮
    current = [rec("Firm 0", 110, fresh_day), rec("Firm 1", 115, date(2026, 11, 2)),
               rec("Firm 2", 120, old), rec("Firm 3", 125, old), rec("Firm 4", 130, old)]
    snap = compute_snapshot(july_history + current, [], AS_OF)
    assert snap.freshness_share == Decimal("0.4")
    assert snap.status == "stale"
    current[2] = rec("Firm 2", 120, date(2026, 11, 3))
    snap = compute_snapshot(july_history + current, [], AS_OF)
    assert snap.freshness_share == Decimal("0.6")
    assert snap.status == "ok"


def test_freshness_is_measured_from_as_of_not_from_the_latest_record():
    records = good_history()                     # 最後一批發布於 10/1
    assert compute_snapshot(records, [], date(2026, 10, 20)).status == "ok"
    assert compute_snapshot(records, [], date(2027, 1, 15)).status == "stale"


def test_no_records_is_no_data():
    snap = compute_snapshot([], [], AS_OF, symbol="xyz")
    assert (snap.symbol, snap.status, snap.n_analysts, snap.mean) == (
        "XYZ", "no_data", 0, None)


def test_consensus_only_input_never_produces_ok_and_never_feeds_stdev():
    """L9：只有共識平均／人數的來源 → no_data；cross_check 只供稽核。"""
    xc = ConsensusCrossCheck(consensus_mean_from_source=Decimal(120), n_from_source=30)
    snap = compute_snapshot([], [], AS_OF, symbol="XYZ", cross_check=xc)
    assert snap.status == "no_data"
    assert "共識" in snap.reasons[0]
    assert (snap.mean, snap.stdev, snap.dispersion) == (None, None, None)
    records = good_history() + today_records()
    with_xc = compute_snapshot(records, [], AS_OF, cross_check=xc)
    without = compute_snapshot(records, [], AS_OF)
    assert with_xc.cross_check == xc
    assert (with_xc.mean, with_xc.stdev, with_xc.n_analysts) == (
        without.mean, without.stdev, without.n_analysts)


def unresolved_split_records():
    return split_records() + [rec("Pre Split", 152, date(2026, 9, 5))]


def test_suspected_split_without_split_info_is_split_unresolved():
    snap = compute_snapshot(unresolved_split_records(), [], AS_OF)
    assert snap.status == "split_unresolved"
    assert "Pre Split" in snap.reasons[0]


def test_known_split_or_ordinary_target_cut_is_not_flagged():
    known = compute_snapshot(unresolved_split_records(),
                             [SPLIT_4_1], AS_OF)
    assert "split_unresolved" not in statuses(known)
    cut = good_history() + [rec("Firm 0", 70, date(2026, 11, 2))]   # 100 → 70
    assert "split_unresolved" not in statuses(compute_snapshot(cut, [], AS_OF))


def jump_years_ago():
    """同一家多年前 200 → 100（剛好 2:1），沒有任何分割資訊；其後早已過期。"""
    return [rec("Jumper", 200, date(2022, 1, 3)), rec("Jumper", 100, date(2022, 2, 1))]


def test_old_target_halving_outside_the_validity_window_does_not_flag_today():
    records = monthly([3] * 60) + jump_years_ago() + today_records()
    snap = compute_snapshot(records, [], AS_OF)
    assert "split_unresolved" not in statuses(snap)


def test_history_point_whose_window_holds_an_unexplained_jump_is_dropped():
    # 兩筆都落在 [t − 12 個月, t] 的取樣日：2022-02 … 2022-12 的月底（11 點）；
    # 60 個取樣點（2021-11 … 2026-10）剩 49 點。
    records = monthly([3] * 60) + jump_years_ago() + today_records()
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.history_points == 49
    dropped = {(2022, m) for m in range(2, 13)}
    assert not [d for d, _ in snap.history if (d.year, d.month) in dropped]
    assert (2022, 1) in {(d.year, d.month) for d, _ in snap.history}


def test_jump_whose_earlier_record_already_expired_is_not_a_suspect():
    # 前一筆在 V 之外（已過期）、後一筆在 V 之內：不能拿過期的值去比。
    records = (good_history() + today_records()
               + [rec("Jumper", 200, date(2025, 10, 1)),
                  rec("Jumper", 100, date(2026, 11, 3))])
    assert "split_unresolved" not in statuses(compute_snapshot(records, [], AS_OF))


def test_jump_within_the_validity_window_without_split_info_is_a_suspect():
    records = (good_history() + today_records()
               + [rec("Jumper", 200, date(2026, 3, 2)),
                  rec("Jumper", 100, date(2026, 11, 3))])
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.status == "split_unresolved"
    assert "Jumper" in snap.reasons[0]


def test_every_failed_rule_is_reported_and_status_is_the_most_basic_one():
    four = [rec(f"Firm {i}", 100 + i, date(2026, 6, 1)) for i in range(4)]
    snap = compute_snapshot(four, [], AS_OF)
    assert snap.status == "insufficient_analysts"
    assert statuses(snap) == ["insufficient_analysts", "stale", "insufficient_history"]


def test_snapshot_carries_audit_fields_through():
    records = good_history() + today_records()
    snap = compute_snapshot(records, [], AS_OF, coverage="partial",
                            source="fixture:v1",
                            rules=ConsensusRules(version="r-test"))
    assert (snap.coverage, snap.source, snap.rules_version) == (
        "partial", "fixture:v1", "r-test")
    assert compute_snapshot(records, [], AS_OF).coverage == "unknown"


def test_median_published_on_is_the_lower_middle_of_effective_dates():
    days = [date(2026, 9, 1), date(2026, 9, 10), date(2026, 10, 1),
            date(2026, 10, 15), date(2026, 11, 1), date(2026, 11, 2)]
    records = [rec(f"Firm {i}", 100 + i, d) for i, d in enumerate(days)]
    assert compute_snapshot(records, [], AS_OF).median_published_on == date(2026, 10, 1)


def test_records_for_another_symbol_are_rejected():
    with pytest.raises(ValueError):
        compute_snapshot(five() + [rec("Other", 1, date(2026, 11, 1), symbol="ABC")],
                         [], AS_OF)
    with pytest.raises(ValueError):
        compute_snapshot([], [], AS_OF)          # 沒有紀錄也沒指定 symbol


# --- §4.4 Consensus Gate ---------------------------------------------------

def ok_snapshot():
    """例 2：60 點中 9 點更低 → percentile 0.15；今天 D ≈ 0.079。"""
    snap = compute_snapshot(monthly([1] * 9 + [9] * 51) + today_records(5), [], AS_OF)
    assert snap.status == "ok"
    return snap


def test_example_2_both_gates_pass_at_defaults_then_first_fails_at_p_10():
    snap = ok_snapshot()
    g = evaluate_gate(snap, Decimal("0.20"), Decimal("0.10"))
    assert (g.first, g.second, g.selected, g.reasons) == (True, True, True, ())
    g = evaluate_gate(snap, Decimal("0.10"), Decimal("0.10"))
    assert (g.first, g.second, g.selected) == (False, True, False)
    assert len(g.reasons) == 1 and g.reasons[0].startswith("percentile")


def test_example_3_exactly_at_threshold_passes():
    snap = replace(ok_snapshot(), percentile=Decimal("0.2000"),
                   dispersion=Decimal("0.1000"))
    g = evaluate_gate(snap, Decimal("0.20"), Decimal("0.10"))
    assert (g.first, g.second) == (True, True)
    assert evaluate_gate(snap, 0.2, 0.1).selected          # 浮點門檻同樣成立
    near = replace(snap, dispersion=Decimal("0.1") + Decimal("1e-12"))
    assert evaluate_gate(near, 0.2, 0.1).second            # 1e-9 內視為相等
    over = replace(snap, dispersion=Decimal("0.1001"))
    assert not evaluate_gate(over, 0.2, 0.1).second


def test_example_4_status_not_ok_fails_both_gates_even_with_tiny_dispersion():
    snap = replace(ok_snapshot(), status="insufficient_analysts",
                   dispersion=Decimal("0.02"), percentile=Decimal(0),
                   reasons=("insufficient_analysts: 有效分析師 4 < N_min 5",))
    g = evaluate_gate(snap, Decimal(1), Decimal(1))
    assert (g.first, g.second, g.selected) == (False, False, False)
    assert any("insufficient_analysts" in r for r in g.reasons)


def test_example_6_identical_targets_have_zero_dispersion_and_pass_second_gate():
    history = monthly([0] * 30)                 # 歷史一直全員一致
    snap = compute_snapshot(history + today_records(0), [], AS_OF)
    assert (snap.stdev, snap.dispersion) == (Decimal(0), Decimal(0))
    assert snap.percentile == Decimal("0.5")    # midrank：與歷史全同值 → 50%
    g = evaluate_gate(snap, Decimal("0.20"), Decimal("0.10"))
    assert (g.first, g.second) == (False, True)  # 不特例放行第一關


@pytest.mark.parametrize("p_max", ["0", "0.10", "0.15", "0.5", "1"])
def test_first_gate_result_does_not_depend_on_dispersion_max(p_max):
    snap = ok_snapshot()
    firsts = {evaluate_gate(snap, Decimal(p_max), Decimal(d)).first
              for d in ("0", "0.05", "0.10", "1")}
    assert len(firsts) == 1


@pytest.mark.parametrize("d_max", ["0", "0.05", "0.079", "0.08", "1"])
def test_second_gate_result_does_not_depend_on_percentile_max(d_max):
    snap = ok_snapshot()
    seconds = {evaluate_gate(snap, Decimal(p), Decimal(d_max)).second
               for p in ("0", "0.10", "0.20", "1")}
    assert len(seconds) == 1


@pytest.mark.parametrize("p_max, d_max", [(-0.01, 0.1), (1.01, 0.1),
                                          (0.2, -0.1), (0.2, 20)])
def test_thresholds_are_ratios_between_0_and_1(p_max, d_max):
    with pytest.raises(ValueError):
        evaluate_gate(ok_snapshot(), p_max, d_max)


# --- §5.1 target_month（#381 未決：先實作兩條規則）--------------------------

TODAY = date(2026, 11, 19)


def with_median(d):
    return replace(ok_snapshot(), median_published_on=d)


def test_fixed_12m_is_the_default_rule():
    snap = with_median(date(2026, 3, 10))
    assert target_month(snap, TODAY, "fixed_12m") == "2027-11"
    assert target_month(snap, TODAY) == "2027-11"
    assert target_month(snap, date(2026, 1, 31)) == "2027-01"


@pytest.mark.parametrize("median, expected", [
    (date(2026, 3, 10), "2027-03"),
    (date(2025, 12, 31), "2026-12"),     # 剛好落在下個月
    (date(2025, 11, 30), "2026-12"),     # +12 = 本月 → 不早於下個月
    (date(2025, 6, 1), "2026-12"),
])
def test_median_published_plus_12m_is_never_before_next_month(median, expected):
    assert target_month(with_median(median), TODAY,
                        "median_published_plus_12m") == expected


def test_target_month_rejects_missing_median_and_unknown_rule():
    with pytest.raises(ValueError):
        target_month(with_median(None), TODAY, "median_published_plus_12m")
    with pytest.raises(ValueError):
        target_month(ok_snapshot(), TODAY, "user_6m")


# --- 其他資料品質／決定性 ---------------------------------------------------

def test_expired_target_can_push_a_stock_below_n_min():
    """例 7 的後果：13 個月前的那家不算 → 只剩 4 家 → insufficient_analysts。"""
    records = [r for r in good_history() if r.analyst_key != "Firm 4"]
    records += [rec(f"Firm {i}", 100 + i, date(2026, 11, 2)) for i in range(4)]
    records += [rec("Firm 4", 100, date(2025, 10, 17))]
    snap = compute_snapshot(records, [], AS_OF)
    assert snap.n_analysts == 4
    assert snap.status == "insufficient_analysts"
    assert snap.reasons[0] == "insufficient_analysts: 有效分析師 4 < N_min 5"


def test_result_does_not_depend_on_the_callers_decimal_context():
    records = monthly([1] * 9 + [9] * 51) + today_records(5)
    base = compute_snapshot(records, [], AS_OF)
    with localcontext() as ctx:
        ctx.prec = 4
        assert compute_snapshot(records, [], AS_OF) == base
        near = replace(base, dispersion=Decimal("0.1000000000001"))
        assert evaluate_gate(near, Decimal("0.2"), Decimal("0.1")).second
        assert not evaluate_gate(replace(base, dispersion=Decimal("0.10001")),
                                 Decimal("0.2"), Decimal("0.1")).second


def test_integer_split_ratio_is_accepted():
    split = SplitEvent(symbol="XYZ", effective_on=SPLIT_DAY, ratio=4)
    assert compute_snapshot(split_records(), [split], AS_OF).low == Decimal(150)


@pytest.mark.parametrize("kwargs", [
    {"n_min": 1},                                  # 樣本標準差至少 2 筆
    {"stdev_kind": "robust"},
    {"h_min": 0},
    {"freshness_min_share": Decimal("1.5")},
])
def test_invalid_rules_are_rejected(kwargs):
    with pytest.raises(ValueError):
        ConsensusRules(**kwargs)
