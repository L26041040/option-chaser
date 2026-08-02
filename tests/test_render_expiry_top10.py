"""T10（#24）：`find_row`／`baseline_key` 對 Top10 候選的擴充（純函式，
不碰 Streamlit widget）。"""
import pytest

pytest.importorskip("streamlit")

from webapp.render import baseline_key, find_row


def _cand(key, baseline_return=0.5):
    return {"candidate_key": key, "baseline_return": baseline_return,
           "legs": [{"strike": 100}, {"strike": 110}], "matrix": {"cells": []}}


def _view(*, expiry_groups=(), expiry_top10=(), baseline_selection=None):
    return {
        "expiry_groups": [{"expiry": exp, "rows": [
            {"strategy": "bull-call-spread", "badges": [], "candidate": c}
            for c in cands]} for exp, cands in expiry_groups],
        "results": [{"strategy": "bull-call-spread", "expiry_top10": [
            {"expiry": exp, "candidates": list(cands)}
            for exp, cands in expiry_top10]}],
        "baseline_selection": baseline_selection,
    }


def test_find_row_locates_candidate_only_present_in_top10():
    """第二層 Top10 清單的候選（不只各期第 1 名）也要能被 Step 2 主圖找到。"""
    rank1 = _cand("K1")
    rank5 = _cand("K5")
    view = _view(expiry_groups=[("2026-08-21", [rank1])],
                expiry_top10=[("2026-08-21", [rank1, rank5])])
    assert find_row(view, "K1")["candidate"]["candidate_key"] == "K1"
    row = find_row(view, "K5")
    assert row is not None
    assert row["candidate"]["candidate_key"] == "K5"
    assert row["strategy"] == "bull-call-spread"


def test_find_row_returns_none_for_unknown_key():
    view = _view(expiry_groups=[("2026-08-21", [_cand("K1")])],
                expiry_top10=[("2026-08-21", [_cand("K1")])])
    assert find_row(view, "does-not-exist") is None
    assert find_row(view, None) is None


def test_baseline_key_reads_baseline_selection_not_default_selection():
    view = _view(baseline_selection=["2026-08-21", "K1"])
    assert baseline_key(view) == "K1"


def test_baseline_key_is_none_when_no_baseline_selection():
    """例如 baseline 期零合格候選（附錄A10.2）——沒有任何值可預設選中。"""
    assert baseline_key(_view(baseline_selection=None)) is None
