"""D1（#14）：`render_catchup_price`——顯示所選 Spread 的 Long Call 追平
價格 S*＝K＋C×(1+R)。S* 本身在服務層（`service._spread_catchup_price`）
已算好放進 `cand["catchup_price"]`（見 tests/test_service_catchup.py），
這裡的函式零金融計算，純格式化與顯示分支（與模組說明「不執行任何金融
估值」一致）：只對 Spread 候選顯示；`catchup_price` 為 None 顯示「無法
計算」；S* ≤ 目標價時醒目提示。"""
import pytest

pytest.importorskip("streamlit")

import streamlit as st

from webapp.render import render_catchup_price


def _view(strategy, catchup, target_price=110.0):
    cand = {"candidate_key": "k1", "catchup_price": catchup}
    return {
        "expiry_groups": [{"rows": [{"strategy": strategy, "candidate": cand}]}],
        "params": {"target_price": target_price},
    }


def _capture(monkeypatch):
    captured = {"caption": [], "success": []}
    monkeypatch.setattr(st, "caption", lambda msg: captured["caption"].append(msg))
    monkeypatch.setattr(st, "success", lambda msg: captured["success"].append(msg))
    return captured


def test_shows_catchup_price_and_gap_to_target(monkeypatch):
    """需求文件例：TLT S*=115、目標 110 -> 超出目標 +4.5%。"""
    captured = _capture(monkeypatch)
    view = _view("bull-call-spread", catchup=115.0, target_price=110.0)
    render_catchup_price(view, "k1")
    assert captured["caption"]
    msg = captured["caption"][0]
    assert "115.00" in msg
    assert "+4.5%" in msg
    assert not captured["success"]   # S* > 目標，不觸發醒目提示


def test_s_star_at_or_below_target_triggers_the_highlight(monkeypatch):
    captured = _capture(monkeypatch)
    view = _view("bull-call-spread", catchup=102.0, target_price=105.0)
    render_catchup_price(view, "k1")
    assert captured["success"]
    assert "Long Call 在本劇本內即勝過此 Spread" in captured["success"][0]


def test_s_star_exactly_at_target_also_triggers_the_highlight(monkeypatch):
    captured = _capture(monkeypatch)
    view = _view("bear-put-spread", catchup=105.0, target_price=105.0)
    render_catchup_price(view, "k1")
    assert captured["success"]


def test_missing_call_cost_shows_cannot_calculate_not_a_crash(monkeypatch):
    captured = _capture(monkeypatch)
    view = _view("bear-put-spread", catchup=None, target_price=80.0)
    render_catchup_price(view, "k1")
    assert any("無法計算" in c for c in captured["caption"])
    assert not captured["success"]


def test_no_display_for_single_leg_strategy(monkeypatch):
    """Long Call／Long Put 本身沒有「與 Long Call 比較」的意義（D1 Out of
    Scope），即使 catchup_price 欄位存在（恆為 None）也不顯示任何東西。"""
    captured = _capture(monkeypatch)
    view = _view("long-call", catchup=None, target_price=110.0)
    render_catchup_price(view, "k1")
    assert not captured["caption"] and not captured["success"]


def test_no_display_when_nothing_selected(monkeypatch):
    captured = _capture(monkeypatch)
    view = _view("bull-call-spread", catchup=115.0, target_price=110.0)
    render_catchup_price(view, None)
    assert not captured["caption"]
