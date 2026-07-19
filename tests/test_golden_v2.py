# tests/test_golden_v2.py
import io
import contextlib
from pathlib import Path
import pytest
from option_chaser.cli import main

FIX = Path(__file__).parent / "fixtures"
CASES = [
    ("golden_long_call.txt", "long-call", "120"),
    ("golden_long_put.txt", "long-put", "80"),
    ("golden_bull_call_spread.txt", "bull-call-spread", "120"),
    ("golden_bear_put_spread.txt", "bear-put-spread", "80"),
]


def run(strategy, target, *extra):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--strategy", strategy, "--target-price", target,
                   "--target-date", "2026-08-28",
                   "--snapshot", str(FIX / "xyz_v2_snapshot.json"), *extra])
    return rc, buf.getvalue()


@pytest.mark.parametrize("golden,strategy,target", CASES)
def test_golden_byte_identical(golden, strategy, target):
    rc, out = run(strategy, target)
    assert rc == 0
    assert out == (FIX / golden).read_text(encoding="utf-8")


@pytest.mark.parametrize("golden,strategy,target", CASES)
def test_deterministic_rerun(golden, strategy, target):
    assert run(strategy, target)[1] == run(strategy, target)[1]


def test_matrix_all_adds_matrices():
    _, base = run("long-call", "120")
    _, full = run("long-call", "120", "--matrix-all")
    assert full.count("P/L 矩陣") > base.count("P/L 矩陣")


def test_no_box_drawing_all_strategies():
    for _, strategy, target in CASES:
        _, out = run(strategy, target)
        assert not any(0x2500 <= ord(ch) <= 0x257F for ch in out)


def test_no_stress_section():
    _, out = run("long-call", "120")
    assert "壓力測試" not in out
