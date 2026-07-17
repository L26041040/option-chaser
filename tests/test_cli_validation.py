from datetime import date
import pytest
from option_chaser.models import ParamError
from option_chaser.cli import build_parser, resolve_params, validate_scenario, effective_buffer


def parse(*extra):
    argv = ["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
            "--snapshot", "dummy.json"] + list(extra)
    return build_parser().parse_args(argv)


def test_effective_buffer_paths():
    assert effective_buffer(45, None, "2026-08-28") == 45
    assert effective_buffer(0, "2026-10-12", "2026-08-28") == 45
    assert effective_buffer(10, "2026-10-12", "2026-08-28") == 45  # max of both
    assert effective_buffer(50, "2026-10-12", "2026-08-28") == 50
    assert effective_buffer(0, "2026-08-01", "2026-08-28") == 0    # earlier than target -> 0


def test_delay_default_from_effective_buffer():
    p = resolve_params(parse("--min-days-after", "45"))
    assert p.delay_days == 23  # ceil(45/2)
    p2 = resolve_params(parse("--min-expiry", "2026-10-12"))
    assert p2.delay_days == 23  # min-expiry path also enables delay stress


def test_delay_exceeding_buffer_rejected():
    with pytest.raises(ParamError):
        resolve_params(parse("--min-days-after", "10", "--delay-days", "11"))


def test_iv_shifts_normalized():
    p = resolve_params(parse("--iv-shifts", "0.2,-0.2"))
    assert p.iv_shifts == (-0.2, 0.0, 0.2)  # 0 injected, sorted


def test_iv_shift_multiplier_must_be_positive():
    with pytest.raises(ParamError):
        resolve_params(parse("--iv-shifts", "-1.0,0"))


def test_delta_bands_validation():
    with pytest.raises(ParamError):
        resolve_params(parse("--delta-bands", "0.65,0.35"))
    with pytest.raises(ParamError):
        resolve_params(parse("--delta-bands", "0,0.5"))


def test_min_return_negative_rejected():
    with pytest.raises(ParamError):
        resolve_params(parse("--min-return", "-0.1"))


def test_scenario_target_below_spot_needs_force():
    p = resolve_params(parse())
    with pytest.raises(ParamError):
        validate_scenario(p, spot=130.0, today=date(2026, 7, 15))
    pf = resolve_params(parse("--force"))
    validate_scenario(pf, spot=130.0, today=date(2026, 7, 15))  # no raise


def test_scenario_target_date_must_be_future():
    p = resolve_params(parse())
    with pytest.raises(ParamError):
        validate_scenario(p, spot=100.0, today=date(2026, 8, 28))


def test_negative_iv_shifts_parse():
    """Test that negative IV shifts are parsed correctly via preprocessing."""
    p = resolve_params(parse("--iv-shifts", "-0.3,0,0.3"))
    assert p.iv_shifts == (-0.3, 0.0, 0.3)


def test_force_flag_not_swallowed_by_preprocessing():
    """Test that --force flag is not treated as a value-taking flag by preprocessing."""
    p = resolve_params(parse("--force", "--iv-shifts", "-0.2,0"))
    assert p.force is True
    assert p.iv_shifts == (-0.2, 0.0)
