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
                   "--target-month", "2026/8",
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


# ---------- T15（#230，Initial V2）：Butterfly golden fixture ----------
#
# 獨立的 run 函式而非塞進上面的 `CASES`／`run()`——Butterfly 需要專屬
# 的中密度履約價梯子快照（`xyz_v7_butterfly_moderate.json`，稀疏的
# `xyz_v2_snapshot.json` 排不出正的 max_profit）與不同的 target-month，
# 硬要共用既有 `run()` 只會讓那個函式多出一堆條件參數，服務兩種不同
# 的東西。

def _run_call_fly():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--strategy", "call-fly", "--target-price", "106",
                   "--target-month", "2026/10",
                   "--snapshot", str(FIX / "xyz_v7_butterfly_moderate.json")])
    return rc, buf.getvalue()


def test_call_fly_golden_byte_identical():
    rc, out = _run_call_fly()
    assert rc == 0
    assert out == (FIX / "golden_call_fly.txt").read_text(encoding="utf-8")


def test_call_fly_deterministic_rerun():
    assert _run_call_fly()[1] == _run_call_fly()[1]


def test_call_fly_no_box_drawing():
    _, out = _run_call_fly()
    assert not any(0x2500 <= ord(ch) <= 0x257F for ch in out)


def test_call_fly_names_all_three_legs_and_the_profit_region():
    _, out = _run_call_fly()
    assert "低履約腿" in out and "中履約腿（賣 2 口）" in out and "高履約腿" in out
    assert "獲利區間（到期）" in out
