"""v4 spec §3.2: expiry grouping, badges；選取取代事後抽樣。"""
from datetime import date

from option_chaser import service
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def _run(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=strategies), SNAP)


def test_groups_ascending_and_rows_sorted():
    r = _run()
    assert r.expiry_groups
    expiries = [g.expiry for g in r.expiry_groups]
    assert expiries == sorted(expiries)
    for g in r.expiry_groups:
        rets = [row.candidate.baseline_return for row in g.rows]
        assert rets == sorted(rets, reverse=True)
        strategies = [row.strategy for row in g.rows]
        assert len(strategies) == len(set(strategies))  # per-strategy best only


def test_badges_global():
    r = _run()
    rows = [row for g in r.expiry_groups for row in g.rows]
    tops = [row for row in rows if "top_return" in row.badges]
    shields = [row for row in rows if "top_resilience" in row.badges]
    assert len(tops) == 1 and len(shields) == 1
    best = max(rows, key=lambda x: x.candidate.baseline_return)
    assert "top_return" in best.badges
    hard = max(rows, key=lambda x: x.candidate.scenario.worst_return)
    assert "top_resilience" in hard.badges


def test_default_selection_no_warning_and_visible():
    r = _run()
    assert r.default_selection is not None
    expiry, key = r.default_selection
    match = [row for g in r.expiry_groups if g.expiry == expiry
             for row in g.rows if service.candidate_key(row.candidate) == key]
    assert len(match) == 1
    all_rows = [row for g in r.expiry_groups for row in g.rows]
    if any(not row.candidate.quote_warning for row in all_rows):
        assert not match[0].candidate.quote_warning


# --- 六到期日鏈：選取取代抽樣 + all-warning fallback ---

SIX_EXPIRY_SNAP = "tests/fixtures/xyz_v4_six_expiries.json"
ALL_WARNING_SNAP = "tests/fixtures/xyz_v4_all_warning.json"

SIX_EXPIRIES = ("2026-08-07", "2026-08-21", "2026-09-18", "2026-10-16",
                "2026-11-20", "2026-12-18")


def _run_six_expiry():
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call",)), SIX_EXPIRY_SNAP)


def test_selection_replaces_sampling_no_hidden_expiries():
    """六檔鏈、目標月 2026-08（錨點 2026-08-21，恰好命中實際到期日）：
    baseline 前 1（鏈上只有一檔）＋ 後 3（缺額由另一側補足）＝ 五檔。
    每一檔選中的到期日都是一組，事後抽樣層已整個消失。"""
    r = _run_six_expiry()
    group_expiries = [g.expiry for g in r.expiry_groups]
    assert group_expiries == ["2026-08-07", "2026-08-21", "2026-09-18",
                              "2026-10-16", "2026-11-20"]
    assert r.hidden_expiries == ()
    assert "2026-12-18" not in group_expiries      # 超出五檔窗，未被窮舉

    res = r.results[0]
    qualified_counts = dict(res.expiry_counts)
    assert set(qualified_counts) == set(group_expiries)
    for g in r.expiry_groups:
        assert g.hidden_count == qualified_counts[g.expiry] - len(g.rows)


def test_all_badged_rows_visible():
    """全域徽章（最高報酬／最強韌性）恆在可見分組內——不再需要注入補救。"""
    r = _run_six_expiry()
    rows = [row for g in r.expiry_groups for row in g.rows]
    for badge in ("top_return", "top_resilience"):
        assert len([row for row in rows if badge in row.badges]) == 1


def test_buffer_days_measured_from_calendar_anchor():
    r = _run_six_expiry()
    anchor = r.request.base_params.anchor
    for g in r.expiry_groups:
        assert g.buffer_days == (date.fromisoformat(g.expiry) - anchor).days


def test_all_warning_fallback():
    """(c) When every candidate has quote_warning, default_selection falls
    back to the global top_return candidate (and it is still visible)."""
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call",)), ALL_WARNING_SNAP)

    rows = [row for g in r.expiry_groups for row in g.rows]
    assert rows
    assert all("warning" in row.badges for row in rows)

    top_return_rows = [row for row in rows if "top_return" in row.badges]
    assert len(top_return_rows) == 1
    top_return_row = top_return_rows[0]
    expected = (service._expiry_of(top_return_row.candidate),
                service.candidate_key(top_return_row.candidate))

    assert r.default_selection == expected
    match = [row for g in r.expiry_groups if g.expiry == expected[0]
             for row in g.rows if service.candidate_key(row.candidate) == expected[1]]
    assert len(match) == 1  # visible


# --- MVP V3（#104，spec #102 決策 F）：顯示旗標與選取閘門分家後的回歸鎖
# ---
#
# AC 原文：「以既有真實 fixture 斷言 default_pair／預設候選選取結果與
# 本票改動前逐位元相同」。`quote_warning` 的計算式（見 service.py
# `_v4_fields`）與 `_build_groups` 的選取邏輯本票完全沒有觸碰——這裡把
# 改動前用同一份 fixture 實際跑出來的 `default_selection` 精確值釘死，
# 任何未來不小心動到選取邏輯（包含 quote_warning 公式本身）都會在這裡
# 紅燈，而不必等到發現使用者看到的預設候選變了才知道。

def test_default_selection_unchanged_by_wide_spread_warning_split():
    """六到期日鏈、雙策略：改動前後 default_selection 必須逐位元相同。"""
    r = _run_six_expiry_two_strategies()
    assert r.default_selection == (
        "2026-08-07", "bull-call-spread|118|122|2026-08-07")


def test_all_warning_fallback_default_selection_unchanged():
    """all-warning fixture：連 fallback 分支選出來的候選也必須逐位元相同。

    REPAIR-09（#246）之後這個釘死值合法改變——`_build_groups` 的選取
    邏輯本身（`_return_key` 排序式）一個字沒動，變的是它排序所依賴的
    `baseline_return` 數值本身：`2026-09-18|122` 這個到期日晚於這份
    fixture 的錨點（2026-08-21），修法前殘留時間價值讓它的報酬率**灌水
    成 +177.3%**（`1.7733143398959357`）、蓋過 `2026-08-07|118`（到期日
    早於錨點，數值本就不受本票影響，維持 0.818 不變）——這正是 #052
    audit 描述的灌水症狀本身在這份 fixture 上的具體案例，而且是最極端
    的一種：修法後這張合約其實是 strike 122 > target 120 的價外 call，
    到期內在價值為 0，正確報酬率是**全損 -100%**（`-1.0`），不是
    +177%。錯的候選贏了、而且贏得離譜。已用 `git stash` 對照過修法前後
    的完整候選清單（`2026-08-07|118` 全程 0.818 不變、`2026-08-07|122`
    全程 -1.0 不變——兩者到期日皆早於錨點；`2026-09-18|118` 從 +150.0%
    降至 -16.7%、`2026-09-18|122` 從 +177.3% 降至 -100.0%——兩者到期日
    皆晚於錨點且皆改變），確認是排序輸入合法改變、不是選取邏輯被動到。"""
    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call",)), ALL_WARNING_SNAP)
    assert r.default_selection == ("2026-08-07", "long-call|118|2026-08-07")


def _run_six_expiry_two_strategies():
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call", "bull-call-spread")), SIX_EXPIRY_SNAP)
