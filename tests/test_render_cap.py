"""v6 spec §5: Spread heatmap 封頂標示（BCS/BPS 鏡像）；§4.4 候選比較表。"""
from webapp.render import comparison_table_html, heatmap_html

MATRIX = {
    "prices": [[130.0, ""], [120.0, "<目標>"], [100.0, "<現價>"], [80.0, ""]],
    "dates": [["2026-08-01", ""], ["2026-09-01", "*"]],
    "cells": [[0.9, 0.9], [0.8, 0.8], [-0.3, -0.3], [-1.0, -1.0]],
}

BCS_CAND = {"strategy": "bull-call-spread",
           "legs": [{"strike": 100.0}, {"strike": 120.0}],
           "cap_price": 120.0, "max_profit_per_contract": 1905.0}
BPS_CAND = {"strategy": "bear-put-spread",
           "legs": [{"strike": 100.0}, {"strike": 80.0}],
           "cap_price": 80.0, "max_profit_per_contract": 1500.0}
SINGLE_CAND = {"strategy": "long-call", "legs": [{"strike": 100.0}],
              "cap_price": None, "max_profit_per_contract": None}


def test_single_leg_heatmap_unchanged_no_cap_marker():
    html_old = heatmap_html(MATRIX)                 # 既有呼叫形式（無 cand）仍合法
    html_new = heatmap_html(MATRIX, SINGLE_CAND)
    assert html_old == html_new
    assert "收益封頂" not in html_new
    assert "最大獲利區" not in html_new


def test_bcs_caps_at_and_above_cap_price():
    html = heatmap_html(MATRIX, BCS_CAND)
    assert "收益封頂" in html
    # 回傳字串整體經 esc() 處理（$ -> \$，見 render.py 既有慣例，v6 新增 cap_note
    # 含 $ 金額必須跳脫），故斷言比對跳脫後的實際輸出，而非原始未跳脫字面。
    assert "股價 ≥ \\$120" in html
    assert "1,905" in html or "1905" in html


def test_bps_caps_at_and_below_cap_price():
    html = heatmap_html(MATRIX, BPS_CAND)
    assert "收益封頂" in html
    assert "股價 ≤ \\$80" in html


def test_bcs_v1_legacy_no_cap_price_degrades_silently():
    """v1 舊 result 檔缺 cap_price/max_profit_per_contract——不得 KeyError，
    降級為無封頂標示（等同 cand=None 的行為）。"""
    legacy = {"strategy": "bull-call-spread", "legs": [{"strike": 100.0}, {"strike": 120.0}]}
    html = heatmap_html(MATRIX, legacy)
    assert "收益封頂" not in html


def test_comparison_table_contains_required_columns():
    view = {
        "expiry_groups": [{
            "expiry": "2026-09-01", "buffer_days": 30, "hidden_count": 0,
            "rows": [{"strategy": "long-call", "badges": ["top_return"],
                     "candidate": {**SINGLE_CAND, "candidate_key": "k1",
                                  "mid_cost": 1.5, "natural_cost": 1.6,
                                  "capital_per_contract": 150.0,
                                  "natural_per_contract": 160.0,
                                  "max_loss_per_contract": 150.0,
                                  "breakeven": 101.5, "baseline_return": 0.5,
                                  "scenario_vector": {"worst_return": -1.0, "worst_code": "S1",
                                                      "entries": []},
                                  "retention": 0.1, "friction": 0.05,
                                  "quote_warning": False,
                                  "legs": [{"strike": 100.0, "bid": 1.4, "ask": 1.6,
                                           "option_type": "call", "expiry": "2026-09-01"}]}}]
        }],
        "hidden_expiries": [],
    }
    html = comparison_table_html(view)
    for token in ("策略", "Breakeven", "最大損失", "劇本報酬", "情境最壞",
                 "成交摩擦", "overflow-x:auto"):
        assert token in html


def test_comparison_table_v1_legacy_spread_no_crash():
    """v1 舊 result 檔的 Spread 候選缺 max_profit_per_contract——不得 KeyError。"""
    legacy_cand = {"strategy": "bull-call-spread", "candidate_key": "k2",
                   "mid_cost": 0.95, "natural_cost": 1.11,
                   "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
                   "breakeven": 100.95, "baseline_return": 0.2,
                   "scenario_vector": {"worst_return": -1.0, "worst_code": "S1", "entries": []},
                   "retention": 0.3, "friction": 0.1, "quote_warning": False,
                   "legs": [{"strike": 100.0, "expiry": "2026-09-01"},
                           {"strike": 120.0, "expiry": "2026-09-01"}]}
    view = {"expiry_groups": [{"expiry": "2026-09-01", "buffer_days": 30, "hidden_count": 0,
                               "rows": [{"strategy": "bull-call-spread", "badges": [],
                                        "candidate": legacy_cand}]}],
            "hidden_expiries": []}
    html = comparison_table_html(view)   # must not raise KeyError
    assert "—" in html
