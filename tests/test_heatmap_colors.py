from webapp.render import cell_color


def test_neutral_band():
    assert cell_color(0.0) == "#ededed" == cell_color(0.049) == cell_color(-0.049)


def test_zero_centered_signs():
    assert cell_color(0.5) != cell_color(-0.5)


def test_clamp_saturation():
    assert cell_color(1.0) == cell_color(9.43)      # +943% same as +100%
    assert cell_color(-1.0) == cell_color(-5.1)


def test_deterministic():
    assert cell_color(0.37) == cell_color(0.37)
