from datetime import date
import pytest
from option_chaser.models import ParamError
from option_chaser.cli import build_parser, resolve_params, validate_scenario


def parse(*extra):
    argv = ["XYZ", "--target-price", "120", "--target-month", "2026/8",
            "--snapshot", "dummy.json"] + list(extra)
    return build_parser().parse_args(argv)


def parse_with_month(text):
    return build_parser().parse_args(
        ["XYZ", "--target-price", "120", "--target-month", text,
         "--snapshot", "dummy.json"])


def test_removed_buffer_flags_error(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["XYZ", "--target-price", "120", "--target-month", "2026/8",
             "--snapshot", "d.json", "--min-days-after", "45"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_strategy_choices_and_default():
    p = resolve_params(parse())
    assert p.strategy == "long-call" and p.matrix_all is False
    p2 = resolve_params(parse("--strategy", "bear-put-spread", "--matrix-all"))
    assert p2.strategy == "bear-put-spread" and p2.matrix_all is True


def test_direction_matrix():
    from datetime import date
    today = date(2026, 7, 15)
    for strat, target, spot, needs_force in [
        ("long-call", 120.0, 100.0, False), ("long-call", 90.0, 100.0, True),
        ("bull-call-spread", 120.0, 100.0, False), ("bull-call-spread", 90.0, 100.0, True),
        ("long-put", 80.0, 100.0, False), ("long-put", 110.0, 100.0, True),
        ("bear-put-spread", 80.0, 100.0, False), ("bear-put-spread", 110.0, 100.0, True),
    ]:
        p = resolve_params(parse("--strategy", strat, "--target-price", str(target)))
        if needs_force:
            with pytest.raises(ParamError):
                validate_scenario(p, spot=spot, today=today)
            validate_scenario(
                resolve_params(parse("--strategy", strat, "--target-price", str(target), "--force")),
                spot=spot, today=today)
        else:
            validate_scenario(p, spot=spot, today=today)


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


def test_four_input_formats_normalize_to_same_month():
    for text in ("2026/8", "2026/08", "26/8", "26/08"):
        assert resolve_params(
            parse_with_month(text)).target_month == "2026-08"


def test_unparseable_month_rejected():
    for text in ("2026-08", "August 2026", "2026/13", ""):
        with pytest.raises(ParamError):
            resolve_params(parse_with_month(text))


def test_scenario_month_must_not_be_over():
    """目標月最後一天當天不算過完，翌日才算（月級語意）。"""
    p = resolve_params(parse())          # 2026-08
    validate_scenario(p, spot=100.0, today=date(2026, 8, 31))   # 當月末日仍可
    with pytest.raises(ParamError):
        validate_scenario(p, spot=100.0, today=date(2026, 9, 1))


def test_negative_iv_shifts_parse():
    """Test that negative IV shifts are parsed correctly via preprocessing."""
    p = resolve_params(parse("--iv-shifts", "-0.3,0,0.3"))
    assert p.iv_shifts == (-0.3, 0.0, 0.3)


def test_force_followed_by_negative_token_errors(capsys):
    # post-fix: --force never merges with a following negative token;
    # argparse rejects it as an unrecognized argument (pre-fix error differed)
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["XYZ", "--target-price", "120", "--target-month", "2026/8",
             "--snapshot", "dummy.json", "--force", "-5"]
        )
    err = capsys.readouterr().err
    assert "unrecognized arguments" in err


def test_dot_leading_negative_shift_parses():
    p = resolve_params(parse("--iv-shifts", "-.3,0"))
    assert p.iv_shifts == (-0.3, 0.0)


def test_empty_symbol_rejected():
    # spec §3: symbol must be a non-empty string
    for sym in ("", "   "):
        argv = [sym, "--target-price", "120", "--target-month", "2026/8",
                "--snapshot", "dummy.json"]
        with pytest.raises(ParamError):
            resolve_params(build_parser().parse_args(argv))


def test_cli_uses_service_and_goldens_unchanged():
    # golden byte-identity is asserted by tests/test_golden_v2.py; here assert
    # the service wiring exists (no subprocess, single entry)
    import option_chaser.cli as cli
    import inspect
    src = inspect.getsource(cli.main)
    assert "service.run" in src or "run_offline" in src
    assert "subprocess" not in src


def test_cli_skipped_direction_exits_2(capsys, tmp_path):
    import json, io, contextlib
    from option_chaser.cli import main
    snap = json.loads(open("tests/fixtures/xyz_v2_snapshot.json", encoding="utf-8").read())
    f = tmp_path / "s.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--target-price", "80", "--target-month", "2026/8",
                   "--snapshot", str(f)])
    assert rc == 2 and "看漲策略目標價" in buf.getvalue()
