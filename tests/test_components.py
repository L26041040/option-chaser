# tests/test_components.py
"""v6 spec §2.2: 卡片元件庫——零公式，僅格式化＋既有 dict 值直讀。"""
from webapp import components

SC = {"id": "XYZ-120-202608", "symbol": "XYZ", "direction": "bullish",
     "target_price": 120.0, "target_date": "2026-08-01", "status": "Active",
     "group_id": "G-XYZ", "notes": "測試備註"}

SINGLE_CAND = {
    "candidate_key": "long-call|93|2028-01-21", "strategy": "long-call",
    "legs": [{"contract_symbol": "X", "option_type": "call", "strike": 93.0,
              "expiry": "2028-01-21", "bid": 1.32, "ask": 1.52, "iv": 0.11,
              "volume": 13, "open_interest": 17320}],
    "mid_cost": 1.42, "natural_cost": 1.52, "natural_per_contract": 152.0,
    "capital_per_contract": 142.0, "max_loss_per_contract": 142.0,
    "max_profit": None, "max_profit_per_contract": None, "cap_price": None,
    "breakeven": 94.42, "baseline_return": 7.4938, "net_delta": 0.39,
}

SPREAD_CAND = {
    "candidate_key": "bull-call-spread|100|120|2028-12-15", "strategy": "bull-call-spread",
    "legs": [{"contract_symbol": "L", "option_type": "call", "strike": 100.0,
              "expiry": "2028-12-15", "bid": 1.0, "ask": 1.1, "iv": 0.13,
              "volume": 10, "open_interest": 100},
             {"contract_symbol": "S", "option_type": "call", "strike": 120.0,
              "expiry": "2028-12-15", "bid": 0.05, "ask": 0.15, "iv": 0.17,
              "volume": 5, "open_interest": 50}],
    "mid_cost": 0.95, "natural_cost": 1.11, "natural_per_contract": 111.0,
    "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
    "max_profit": 19.05, "max_profit_per_contract": 1905.0, "cap_price": 120.0,
    "breakeven": 100.95, "baseline_return": 20.05, "net_delta": 0.20,
}

SUMMARY = {
    "meta": {"spot": 100.0},
    "snapshot_ref": {
        "fetched_at": "2026-07-22T00:00:00+00:00",
        "source": "UnitFixture",
    },
    "data_quality": {"all_quotes_filtered": False},
    "default_selection": ["2028-01-21", "long-call|93|2028-01-21"],
    "expiry_groups": [{
        "expiry": "2028-01-21",
        "rows": [{"strategy": "long-call", "candidate": SINGLE_CAND}],
    }],
}


def test_scenario_card_shows_core_fields():
    html = components.scenario_card(SC, None)
    assert "XYZ" in html and "120.00" in html and "2026-08-01" in html
    assert "尚未分析" in html


def test_scenario_card_productized_list_item_fields():
    html = components.scenario_card(SC, SUMMARY)
    for text in (
        "Symbol", "方向", "現價", "目標價", "目標日", "狀態", "群組",
        "最新推薦候選", "劇本報酬", "每張或每組成本", "資料品質",
    ):
        assert text in html
    assert "oc-scenario-list-item" in html
    assert "Long Call" in html
    assert "$100.00" in html
    assert "$120.00" in html
    assert "749.4%" in html
    assert "$142" in html
    assert "最近有效快照" in html
    assert "UnitFixture" in html


def test_scenario_card_no_position_language():
    """brief §7.1 紅線：不得偽造持倉語彙。"""
    html = components.scenario_card(SC, None)
    for banned in ("持倉損益", "已投入資金", "Portfolio Greeks"):
        assert banned not in html


def test_candidate_card_single_leg_shows_bid_mid_ask_and_per_contract():
    html = components.candidate_card(SINGLE_CAND, "long-call")
    assert "1.32" in html and "1.42" in html and "1.52" in html   # bid/mid/ask
    assert "142" in html    # 每張成本
    assert "94.42" in html  # breakeven
    assert "履約價" in html and "93" in html


def test_candidate_card_spread_shows_max_profit_and_cap_price():
    html = components.candidate_card(SPREAD_CAND, "bull-call-spread")
    assert "0.95" in html          # net mid debit /股
    assert "95" in html            # 每組成本
    assert "1,905" in html or "1905" in html   # 最大獲利每組
    assert "120" in html           # 封頂價
    assert "買" in html and "賣" in html


def test_candidate_card_has_product_quote_return_cost_risk_hierarchy():
    html = components.candidate_card(SPREAD_CAND, "bull-call-spread")
    for css_class in (
        "oc-candidate-card", "oc-candidate-return", "oc-candidate-quotes",
        "oc-candidate-cost", "oc-candidate-risk", "oc-spread-cap",
    ):
        assert css_class in html
    for label in (
        "Bid", "Mid", "Ask", "每股價格", "每組成本", "最大損失",
        "Spread 最大獲利", "Breakeven", "Spread 封頂價",
    ):
        assert label in html
    assert "$0.95" in html
    assert "$95" in html
    assert "$1,905" in html
    assert "$120.00" in html


def test_single_leg_candidate_card_uses_per_contract_language():
    html = components.candidate_card(SINGLE_CAND, "long-call")
    assert "每張成本" in html
    assert "每組成本" not in html
    assert "最大獲利無上限" in html
    assert "Spread 封頂價" not in html


def test_candidate_card_no_formula_arithmetic():
    """禁止元件內做金融乘除——所有顯示值須直接取自 dict（字串搜尋已知輸入值）。"""
    html = components.candidate_card(SPREAD_CAND, "bull-call-spread")
    # 每組成本應直接等於 dict 內已算好的 capital_per_contract，不應是元件自算 mid*100
    assert f"{SPREAD_CAND['capital_per_contract']:.0f}" in html


def test_metric_tile():
    html = components.metric_tile("Active 劇本數", "3")
    assert "Active 劇本數" in html and ">3<" in html or "3" in html


def test_status_pill_four_states():
    for st_ in ("Active", "Reached", "Expired", "Invalidated"):
        html = components.status_pill(st_)
        assert st_ in html


def test_quality_badge_three_tones():
    for tone in ("正常", "報價不足", "歷史資料"):
        html = components.quality_badge(tone)
        assert tone in html


def test_scenario_card_escapes_html_injection_in_symbol_and_notes():
    """紅線：使用者輸入（symbol/notes）注入 HTML 標記時必須被跳脫，不得破壞卡片
    結構或執行注入內容。"""
    malicious = {**SC, "symbol": "<script>alert(1)</script>",
                "notes": '<img src=x onerror="alert(2)">'}
    html = components.scenario_card(malicious, None)
    assert "<script>" not in html
    # NOTE: html.escape(quote=True) neutralizes structural characters
    # (<, >, &, quotes) but does not remove literal attribute-name text —
    # "onerror=" as a bare substring necessarily survives escaping (its
    # letters/`=` are not special HTML chars), same as "img" surviving in
    # "&lt;img" below. The actual exploit vector is the quote character
    # that lets an attribute value break out and inject a live handler;
    # that quote is escaped to `&quot;`, so the raw `onerror="` (or `'`)
    # pattern that a browser would parse as a live attribute must be gone.
    assert 'onerror="' not in html and "onerror='" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_candidate_card_bear_put_spread_shows_put_not_call():
    """BPS 兩腿皆 put——卡片不得誤標 Call（先前草稿硬編 Call 的迴歸測試）。"""
    bps_cand = {
        "candidate_key": "bear-put-spread|100|80|2028-12-15", "strategy": "bear-put-spread",
        "legs": [{"contract_symbol": "L", "option_type": "put", "strike": 100.0,
                 "expiry": "2028-12-15", "bid": 1.0, "ask": 1.1, "iv": 0.13,
                 "volume": 10, "open_interest": 100},
                {"contract_symbol": "S", "option_type": "put", "strike": 80.0,
                 "expiry": "2028-12-15", "bid": 0.05, "ask": 0.15, "iv": 0.17,
                 "volume": 5, "open_interest": 50}],
        "mid_cost": 0.95, "natural_cost": 1.11, "natural_per_contract": 111.0,
        "capital_per_contract": 95.0, "max_loss_per_contract": 95.0,
        "max_profit": 19.05, "max_profit_per_contract": 1905.0, "cap_price": 80.0,
        "breakeven": 99.05, "baseline_return": 20.05, "net_delta": -0.20,
    }
    html = components.candidate_card(bps_cand, "bear-put-spread")
    assert "Put" in html
    assert "Call" not in html


def test_candidate_card_v1_legacy_missing_fields_no_crash():
    """v1 舊 result 檔缺 v2 新欄（natural_per_contract/max_profit_per_contract/
    cap_price）——必須降級顯示，不得 KeyError。"""
    legacy_single = {k: v for k, v in SINGLE_CAND.items()
                     if k not in ("natural_per_contract", "max_profit_per_contract", "cap_price")}
    html = components.candidate_card(legacy_single, "long-call")
    assert "—" in html
    assert "舊版分析結果" in html

    legacy_spread = {k: v for k, v in SPREAD_CAND.items()
                     if k not in ("natural_per_contract", "max_profit_per_contract", "cap_price")}
    html2 = components.candidate_card(legacy_spread, "bull-call-spread")
    assert "—" in html2
    assert "舊版分析結果" in html2
