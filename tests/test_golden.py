# tests/test_golden.py
import io
import contextlib
from pathlib import Path
from option_chaser.cli import main

FIX = Path(__file__).parent / "fixtures"
ARGS = ["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
        "--min-days-after", "45", "--snapshot", str(FIX / "xyz_snapshot.json")]


def run_capture():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(ARGS)
    return rc, buf.getvalue()


def test_golden_report_byte_identical():
    rc, out = run_capture()
    assert rc == 0
    assert out == (FIX / "golden_report.txt").read_text(encoding="utf-8")


def test_repeat_run_is_deterministic():
    _, a = run_capture()
    _, b = run_capture()
    assert a == b


def test_no_box_drawing_characters():
    _, out = run_capture()
    assert not any(0x2500 <= ord(ch) <= 0x257F for ch in out)


def test_report_shows_bid_pnl_and_per_contract_amounts():
    # spec §7: bid/ask/mid visible; scenario lines carry 估值+損益+報酬率;
    # per-share and per-contract (x100) side by side
    _, out = run_capture()
    assert "Bid $" in out
    assert "/張）" in out
    assert "損益 " in out


def test_zero_qualified_exit_code(tmp_path):
    rc, out = None, None
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["XYZ", "--target-price", "120", "--target-date", "2026-08-28",
                   "--min-days-after", "3650",
                   "--snapshot", str(FIX / "xyz_snapshot.json")])
    assert rc == 1
    assert "無合格合約" in buf.getvalue()


def test_md_output(tmp_path):
    md = tmp_path / "r.md"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(ARGS + ["--md", str(md)])
    assert rc == 0
    assert md.read_text(encoding="utf-8") == buf.getvalue()
