from option_chaser.valuation import call_greeks


def test_hull_greeks():
    # S=42,K=40,T=0.5,r=0.10,sigma=0.20 (Hull): d1=0.7693
    g = call_greeks(42, 40, 0.5, 0.10, 0.20)
    assert abs(g.delta - 0.7791) < 1e-3
    assert abs(g.gamma - 0.0500) < 1e-3
    assert abs(g.theta_per_day - (-4.305 / 365.0)) < 1e-3
    assert abs(g.vega_per_pct - 0.0882) < 1e-3


def test_delta_bounds():
    for k in (20, 40, 60, 100):
        g = call_greeks(50, k, 0.3, 0.04, 0.4)
        assert 0.0 < g.delta < 1.0
