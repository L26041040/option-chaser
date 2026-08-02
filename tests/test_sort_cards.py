"""T8（#22）／需求五: 左側清單排序（純函式，零 Streamlit）。

聚合函式，只重排 `ScenarioCard` 視圖；不碰 `list_scenarios()` 既有回傳順序
（該不變式由 `tests/test_workspace.py` 另行覆蓋）。
"""
from option_chaser import workspace


def _card(id, best_return, signal=workspace.SIGNAL_GREEN):
    return workspace.ScenarioCard(id=id, symbol="XYZ", target_price=120.0,
                                  target_month="2028-01",
                                  best_return=best_return, signal=signal)


def test_higher_return_sorts_first():
    a = _card("A", 3.1)
    b = _card("B", 5.2)
    assert [c.id for c in workspace.sort_cards([a, b])] == ["B", "A"]


def test_swapping_returns_reverses_the_order():
    """驗收：兩劇本收益率互換後，清單順序反轉。"""
    a = _card("A", 5.2)
    b = _card("B", 3.1)
    assert [c.id for c in workspace.sort_cards([a, b])] == ["A", "B"]
    a2 = _card("A", 3.1)
    b2 = _card("B", 5.2)
    assert [c.id for c in workspace.sort_cards([a2, b2])] == ["B", "A"]


def test_yellow_card_participates_using_its_own_best_return():
    """黃燈卡片的 best_return 已是上一份成功快照的值（見 `card_of`）——
    排序函式本身只認 best_return，不管燈號是綠是黃。"""
    green = _card("G", 2.0, signal=workspace.SIGNAL_GREEN)
    yellow = _card("Y", 4.0, signal=workspace.SIGNAL_YELLOW)
    assert [c.id for c in workspace.sort_cards([green, yellow])] == ["Y", "G"]


def test_red_cards_always_sort_after_non_red_regardless_of_return():
    red = _card("R", 99.0, signal=workspace.SIGNAL_RED)
    green = _card("G", 0.01, signal=workspace.SIGNAL_GREEN)
    assert [c.id for c in workspace.sort_cards([red, green])] == ["G", "R"]


def test_red_group_sorts_internally_by_last_known_return():
    r_high = _card("RH", 5.0, signal=workspace.SIGNAL_RED)
    r_low = _card("RL", 1.0, signal=workspace.SIGNAL_RED)
    green = _card("G", 0.5, signal=workspace.SIGNAL_GREEN)
    got = [c.id for c in workspace.sort_cards([r_low, green, r_high])]
    assert got == ["G", "RH", "RL"]


def test_no_snapshot_card_sorts_after_valued_cards_and_before_red():
    unknown = _card("U", None, signal=workspace.SIGNAL_UNKNOWN)
    green = _card("G", 0.1, signal=workspace.SIGNAL_GREEN)
    red = _card("R", 9.0, signal=workspace.SIGNAL_RED)
    got = [c.id for c in workspace.sort_cards([red, unknown, green])]
    assert got == ["G", "U", "R"]


def test_red_card_with_no_known_return_sorts_last_within_red_group():
    """從未成功刷新過就已月過期：仍是紅燈，但沒有「最後已知值」可用。"""
    r_valued = _card("RV", 2.0, signal=workspace.SIGNAL_RED)
    r_unknown = _card("RU", None, signal=workspace.SIGNAL_RED)
    got = [c.id for c in workspace.sort_cards([r_unknown, r_valued])]
    assert got == ["RV", "RU"]
