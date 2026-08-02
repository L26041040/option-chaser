"""T11（#25）→ QA1-11（#38，重做）：`render_spread_history` 改為折線圖
（原表格版本「變成表格很奇怪」，需求方裁示重做成跟 Yahoo Finance 單張
選擇權價格走勢一樣的折線圖）。純資料組裝，零金融計算——數字直接來自
`workspace.spread_history()` 的聚合結果。"""
from datetime import datetime

import pytest

pytest.importorskip("streamlit")

import streamlit as st

from webapp.render import render_spread_history


def test_empty_history_does_not_render_a_chart(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "line_chart", lambda *a, **kw: calls.append(a))
    render_spread_history([])
    assert calls == []   # 走 st.info 分支，不畫圖


def test_chart_plots_net_cost_against_time(monkeypatch):
    history = [
        {"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
         "cost": 0.55, "baseline_return": 17.18, "rank_in_expiry": 1},
        {"analyzed_at": "2026-07-08T21:30:00-04:00", "spot": 101.0,
         "cost": 0.62, "baseline_return": 20.0, "rank_in_expiry": 2},
    ]
    captured = {}

    def fake_line_chart(data, *, x, y):
        captured["data"] = data
        captured["x"] = x
        captured["y"] = y

    monkeypatch.setattr(st, "line_chart", fake_line_chart)
    render_spread_history(history)

    assert captured["data"][0][captured["x"]] == datetime.fromisoformat(
        "2026-07-01T21:30:00-04:00")
    assert captured["data"][0][captured["y"]] == 0.55
    assert captured["data"][1][captured["y"]] == 0.62


def test_gap_entry_keeps_none_not_zero_or_dropped(monkeypatch):
    """需求（T11 沿用、QA1-11 重申）：缺席快照維持斷點，不插值、不跳過。
    `None` 讓 Vega-Lite（`st.line_chart` 底層）在該點斷開，不連過去、
    不畫成 0——這裡只驗證資料層確實把 None 原封不動傳下去，不做任何
    替代值或跳過該筆。"""
    history = [
        {"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
         "cost": 0.55, "baseline_return": 17.18, "rank_in_expiry": 1},
        {"analyzed_at": "2026-07-08T21:30:00-04:00", "spot": 101.0,
         "cost": None, "baseline_return": None, "rank_in_expiry": None},
        {"analyzed_at": "2026-07-15T21:30:00-04:00", "spot": 102.0,
         "cost": 0.70, "baseline_return": 25.0, "rank_in_expiry": 1},
    ]
    captured = {}

    def fake_line_chart(data, *, x, y):
        captured["data"] = data
        captured["y"] = y

    monkeypatch.setattr(st, "line_chart", fake_line_chart)
    render_spread_history(history)

    assert len(captured["data"]) == 3        # 沒有跳過那一筆
    assert captured["data"][1][captured["y"]] is None   # 原封不動是 None，不是 0


def test_chart_does_not_crash_when_rendered_end_to_end():
    """`monkeypatch` 版只驗證資料層；這裡讓 `st.line_chart` 真的跑一次
    （含斷點的 None 值），確認 Streamlit／Vega-Lite 端到端不拋例外。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_render_history_with_a_gap)
    at.run()
    assert not at.exception


def _render_history_with_a_gap():
    from webapp.render import render_spread_history
    render_spread_history([
        {"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
         "cost": 0.55, "baseline_return": 17.18, "rank_in_expiry": 1},
        {"analyzed_at": "2026-07-08T21:30:00-04:00", "spot": 101.0,
         "cost": None, "baseline_return": None, "rank_in_expiry": None},
        {"analyzed_at": "2026-07-15T21:30:00-04:00", "spot": 102.0,
         "cost": 0.70, "baseline_return": 25.0, "rank_in_expiry": 1},
    ])
