"""T11（#25）：`render_spread_history`（純字串／markdown 組裝，零金融計算）。"""
import pytest

pytest.importorskip("streamlit")

import streamlit as st

from webapp.render import render_spread_history


def test_empty_history_does_not_render_a_table(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "markdown", lambda *a, **kw: calls.append(a))
    render_spread_history([])
    assert calls == []   # 走 st.info 分支，不組表格


def test_gap_entries_render_as_dashes_not_zero_or_blank(monkeypatch):
    history = [
        {"analyzed_at": "2026-07-01T21:30:00-04:00", "spot": 100.0,
         "cost": 0.55, "baseline_return": 17.18, "rank_in_expiry": 1},
        {"analyzed_at": "2026-07-08T21:30:00-04:00", "spot": 101.0,
         "cost": None, "baseline_return": None, "rank_in_expiry": None},
    ]
    captured = {}
    monkeypatch.setattr(st, "markdown",
                        lambda text, **kw: captured.setdefault("text", text))
    render_spread_history(history)

    lines = captured["text"].splitlines()
    normal_row, gap_row = lines[2], lines[3]
    assert "$0.55" in normal_row and "1" in normal_row.split("|")[-2]
    # 斷點列：淨成本／收益率／名次三欄皆「—」，不是 0 或空字串。
    cells = gap_row.strip("|").split("|")
    assert cells[2:5] == ["—", "—", "—"]
