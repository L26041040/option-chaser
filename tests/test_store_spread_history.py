"""V9（#57）：`store.spread_cost_history()`——T11（#25）既有聚合邏輯搬出
`workspace.spread_history()`後的獨立單元測試，直接餵手刻的 view dict
（不必經過完整引擎管線／檔案 I/O），驗證聚合本身的行為。

`workspace.spread_history()` 改為委派本函式後，`tests/test_spread_history.py`
（走完整檔案＋引擎管線）仍然全綠——那條測試現在同時覆蓋「檔案層委派
正確」與「聚合邏輯正確」，這裡只補「聚合邏輯」本身更細的手刻案例。
"""
from option_chaser import store

KEY = "bull-call-spread|100|110|2026-08-21"


def _view(analyzed_at, spot, all_candidates=(), strategy="bull-call-spread"):
    return {"analyzed_at": analyzed_at, "meta": {"spot": spot},
           "results": [{"strategy": strategy, "all_candidates": list(all_candidates)}]}


def _entry(cost, baseline_return, rank, key=KEY):
    return {"candidate_key": key, "cost": cost, "baseline_return": baseline_return,
           "rank_in_expiry": rank}


def test_matching_key_carries_cost_return_and_rank():
    views = [_view("2026-07-01T21:30:00-04:00", 100.0,
                   [_entry(5.2, 0.4, 2)])]
    hist = store.spread_cost_history(views, KEY)
    assert hist == [{"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
                     "cost": 5.2, "baseline_return": 0.4, "rank_in_expiry": 2}]


def test_absent_key_is_a_gap_not_a_skip():
    """該次快照沒有這個候選（被過濾／不存在）——這一筆仍然入列，只是
    三欄皆為 None，`analyzed_at`／`spot` 仍取自那次成功更新本身。"""
    views = [_view("2026-07-08T21:30:00-04:00", 101.5, [])]
    hist = store.spread_cost_history(views, KEY)
    assert hist == [{"analyzed_at": "2026-07-08T21:30:00-04:00", "spot": 101.5,
                     "cost": None, "baseline_return": None, "rank_in_expiry": None}]


def test_multiple_snapshots_form_one_continuous_series_with_gaps():
    views = [
        _view("2026-07-01T21:30:00-04:00", 100.0, [_entry(5.2, 0.4, 2)]),
        _view("2026-07-08T21:30:00-04:00", 101.0, []),   # 缺席＝斷點
        _view("2026-07-15T21:30:00-04:00", 99.0, [_entry(4.8, 0.6, 1)]),
    ]
    hist = store.spread_cost_history(views, KEY)
    assert [e["cost"] for e in hist] == [5.2, None, 4.8]
    assert [e["rank_in_expiry"] for e in hist] == [2, None, 1]
    # 順序原樣保留（呼叫端負責排序，這裡不重排）
    assert [e["analyzed_at"] for e in hist] == [
        "2026-07-01T21:30:00-04:00", "2026-07-08T21:30:00-04:00",
        "2026-07-15T21:30:00-04:00"]


def test_only_the_matching_key_is_picked_when_multiple_candidates_present():
    views = [_view("2026-07-01T21:30:00-04:00", 100.0, [
        _entry(3.0, 0.1, 1, key="bull-call-spread|95|105|2026-08-21"),
        _entry(5.2, 0.4, 2, key=KEY),
        _entry(1.0, -0.2, 3, key="bull-call-spread|105|115|2026-08-21"),
    ])]
    hist = store.spread_cost_history(views, KEY)
    assert hist[0]["cost"] == 5.2 and hist[0]["rank_in_expiry"] == 2


def test_searches_across_all_strategies_in_a_view_not_just_the_first():
    """`view["results"]` 可能有多個策略（多策略分析）——搜尋要涵蓋全部，
    不能只看第一個 result。"""
    views = [{
        "analyzed_at": "2026-07-01T21:30:00-04:00", "meta": {"spot": 100.0},
        "results": [
            {"strategy": "long-call", "all_candidates": []},
            {"strategy": "bull-call-spread", "all_candidates": [_entry(5.2, 0.4, 2)]},
        ],
    }]
    hist = store.spread_cost_history(views, KEY)
    assert hist[0]["cost"] == 5.2


def test_empty_view_list_is_an_empty_history():
    assert store.spread_cost_history([], KEY) == []


def test_result_without_all_candidates_field_does_not_crash():
    """單腳策略的 result 沒有 `all_candidates` 欄位（T9 附錄A13 既有 MVP
    範圍：只有 spread 策略填入）——`.get(..., [])` 要擋得住，不拋
    KeyError。"""
    views = [{"analyzed_at": "2026-07-01T21:30:00-04:00", "meta": {"spot": 100.0},
             "results": [{"strategy": "long-call"}]}]
    hist = store.spread_cost_history(views, KEY)
    assert hist == [{"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
                     "cost": None, "baseline_return": None, "rank_in_expiry": None}]
