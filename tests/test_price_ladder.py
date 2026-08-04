"""V7（#55）：任意價位的劇本報酬——三價位對照的引擎原語。

這一組測試釘住的核心性質是**口徑一致**：`return_at_price` 在目標價上必須
等於既有的主排名數字（`baseline_return`／`spread_baseline_return`）。三價位
要能與頭條數字並排比較，唯一的辦法就是它們是同一條公式、同一個估值日、
同一個 IV、同一個成本口徑（最差成交，附錄 A14.2）。
"""
from datetime import date

import pytest

from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.ranking import (baseline_return, return_at_price,
                                   spread_baseline_return)
from option_chaser.valuation import evaluate_contract, evaluate_spread

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_month="2026-10")


def _leg(sym, strike, bid, ask, iv=0.30, expiry="2026-10-16"):
    return OptionContract(contract_symbol=sym, option_type="call", strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None, volume=10,
                          open_interest=100, implied_volatility=iv)


def _val(strike, bid, ask):
    return evaluate_contract(_leg("c", strike, bid, ask), spot=100.0, today=TODAY, p=P)


def _spread(k_long, k_short):
    return evaluate_spread(_leg("lng", k_long, 3.0, 3.2), _leg("sht", k_short, 1.0, 1.2),
                           spot=100.0, today=TODAY, p=P)


# --- 口徑一致：目標價上必須與主排名數字完全相同 -------------------------

def test_single_leg_at_target_price_equals_baseline_return():
    v = _val(110.0, 3.0, 3.2)
    assert return_at_price(v, P.target_price, P) == pytest.approx(baseline_return(v))


def test_spread_at_target_price_equals_spread_baseline_return():
    sv = _spread(110.0, 120.0)
    assert return_at_price(sv, P.target_price, P) == pytest.approx(
        spread_baseline_return(sv))


# --- 任意價位的行為 -----------------------------------------------------

def test_higher_price_gives_higher_return_for_bullish_leg():
    """看漲部位：標的價越高、報酬越高。三價位對照要有意義的前提。"""
    v = _val(110.0, 3.0, 3.2)
    assert (return_at_price(v, 100.0, P)
            < return_at_price(v, 120.0, P)
            < return_at_price(v, 140.0, P))


def test_spread_return_is_capped_by_width():
    """價差的報酬有上限：估值最多到寬度，成本固定，報酬因此有天花板。
    標的價漲到天上去也不會超過 (寬度 − 成本)/成本。"""
    sv = _spread(110.0, 120.0)
    ceiling = (sv.width - sv.net_worst) / sv.net_worst
    assert return_at_price(sv, 10_000.0, P) == pytest.approx(ceiling)


def test_worthless_at_low_price_is_total_loss():
    """標的價遠低於履約價：到錨點日估值趨近 0，報酬趨近 −100%。"""
    sv = _spread(110.0, 120.0)
    assert return_at_price(sv, 1.0, P) == pytest.approx(-1.0, abs=1e-6)
