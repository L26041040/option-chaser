import io, contextlib
from datetime import date
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.valuation import evaluate_spread
from option_chaser.ranking import rank_spreads, spread_baseline_return, build_spread_reasons

TODAY = date(2026, 7, 15)
P = AnalysisParams(target_price=120.0, target_date="2026-08-28",
                   strategy="bull-call-spread")


def make(sym, strike, bid, ask, iv=0.30):
    return OptionContract(contract_symbol=sym, option_type="call", strike=strike,
                          expiry="2026-10-16", bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=iv)


def build(lo, hi):
    return evaluate_spread(lo, hi, spot=100.0, today=TODAY, p=P)


def test_rank_spreads_orders_by_baseline_return():
    a = build(make("A", 105.0, 5.3, 5.5, 0.36), make("B", 130.0, 0.05, 0.15, 0.45))
    b = build(make("C", 110.0, 3.0, 3.25, 0.30), make("B2", 130.0, 0.05, 0.15, 0.45))
    ranked = rank_spreads([a, b], P)
    rets = [spread_baseline_return(s) for s in ranked]
    assert rets == sorted(rets, reverse=True)


def test_reasons_mention_rank_and_cap():
    sv = build(make("A", 110.0, 3.0, 3.25), make("B", 130.0, 0.05, 0.15, 0.45))
    pros, cons = build_spread_reasons(sv, idx=0, n_pairs=4, p=P)
    assert any("合格 4 組中第 1" in s for s in pros)
    assert any("獲利上限" in s for s in cons)


def test_cli_spread_end_to_end(tmp_path):
    # snapshot with two call legs -> one qualified pair -> report renders
    import json
    from option_chaser.cli import main
    snap = {
        "schema_version": 2, "symbol": "XYZ",
        "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
        "source": "yfinance", "contracts": [
            {"contract_symbol": "A", "option_type": "call", "strike": 105.0,
             "expiry": "2026-10-16", "bid": 5.3, "ask": 5.5, "last": None,
             "volume": 80, "open_interest": 300, "implied_volatility": 0.36},
            {"contract_symbol": "B", "option_type": "call", "strike": 110.0,
             "expiry": "2026-10-16", "bid": 3.0, "ask": 3.25, "last": None,
             "volume": 90, "open_interest": 400, "implied_volatility": 0.30},
        ],
    }
    f = tmp_path / "s.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--strategy", "bull-call-spread", "--target-price", "120",
                   "--target-date", "2026-08-28", "--snapshot", str(f)])
    out = buf.getvalue()
    assert rc == 0
    assert "配對總數" in out and "Bull Call Spread" in out
    assert "獲利上限" in out
