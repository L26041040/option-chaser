"""CLI entry point: arg parsing, validation, orchestration (spec §3, §8)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .models import AnalysisParams, ParamError, STRATEGIES, is_bullish


# Flags that take numeric/CSV values and need preprocessing for negative numbers
_NUMERIC_VALUE_FLAGS = {
    "--iv-shifts",
    "--delta-bands",
    "--min-return",
    "--target-price",
    "--rate",
    "--max-spread-pct",
    "--spread-floor",
    "--min-oi",
    "--min-volume",
    "--top"
}


def _merge_numeric_flag_values(args: list[str]) -> list[str]:
    """Convert "--option negative_value" to "--option=negative_value" so argparse
    doesn't mistake a negative-number value (e.g. -1.0,0 as IV shifts) for a flag.
    Only applies to flags that actually take numeric/CSV values."""
    processed_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        # Check if this is a numeric-value flag and next arg looks like a negative number
        if (arg in _NUMERIC_VALUE_FLAGS and i + 1 < len(args)):
            next_arg = args[i + 1]
            # If next arg starts with - followed by digit or dot (negative/decimal number pattern)
            if next_arg.startswith('-') and len(next_arg) > 1 and (next_arg[1].isdigit() or next_arg[1] == '.'):
                # Combine them as --option=value
                processed_args.append(f"{arg}={next_arg}")
                i += 2
                continue
        processed_args.append(arg)
        i += 1
    return processed_args


class _CustomParser(argparse.ArgumentParser):
    """ArgumentParser that handles negative numbers in values (e.g., -1.0,0 as IV shifts).

    Overrides only the public, stable parse_known_args API (not the private
    _parse_known_args, whose signature changed in Python 3.13)."""
    def parse_known_args(self, args=None, namespace=None):
        if args is None:
            args = sys.argv[1:]
        args = _merge_numeric_flag_values(args)
        return super().parse_known_args(args, namespace)


def build_parser() -> argparse.ArgumentParser:
    ap = _CustomParser(
        prog="option-chaser",
        description="Long Call scenario optimizer（確定性計算，非投資建議）",
    )
    ap.add_argument("symbol")
    ap.add_argument("--target-price", type=float, required=True)
    ap.add_argument("--target-date", required=True)
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="long-call")
    ap.add_argument("--min-expiry", default=None)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--iv-shifts", default="-0.2,0,0.2")
    ap.add_argument("--rate", type=float, default=0.04)
    ap.add_argument("--min-oi", type=int, default=10)
    ap.add_argument("--min-volume", type=int, default=0)
    ap.add_argument("--max-spread-pct", type=float, default=0.15)
    ap.add_argument("--spread-floor", type=float, default=0.10)
    ap.add_argument("--delta-bands", default="0.35,0.65")
    ap.add_argument("--min-return", type=float, default=0.0)
    ap.add_argument("--matrix-all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--md", default=None)
    return ap


def _parse_iso(name: str, s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ParamError(f"{name} 必須為 YYYY-MM-DD：{s!r}") from None


def resolve_params(args: argparse.Namespace) -> AnalysisParams:
    if not args.symbol or not args.symbol.strip():
        raise ParamError("symbol 必須為非空字串")
    if args.target_price <= 0:
        raise ParamError("--target-price 必須 > 0")
    _parse_iso("--target-date", args.target_date)
    if args.min_expiry:
        _parse_iso("--min-expiry", args.min_expiry)
    if not 1 <= args.top <= 10:
        raise ParamError("--top 必須在 1–10")
    if args.rate < 0:
        raise ParamError("--rate 必須 >= 0")
    if args.min_oi < 0 or args.min_volume < 0:
        raise ParamError("--min-oi / --min-volume 必須 >= 0")
    if args.max_spread_pct <= 0:
        raise ParamError("--max-spread-pct 必須 > 0")
    if args.spread_floor < 0:
        raise ParamError("--spread-floor 必須 >= 0")
    if args.min_return < 0:
        raise ParamError("--min-return 必須 >= 0")

    try:
        shifts = [float(x) for x in args.iv_shifts.split(",") if x.strip() != ""]
    except ValueError:
        raise ParamError(f"--iv-shifts 解析失敗：{args.iv_shifts!r}") from None
    if any(1.0 + s <= 0 for s in shifts):
        raise ParamError("--iv-shifts 每個乘數 1+shift 必須 > 0")
    if 0.0 not in shifts:
        shifts.append(0.0)  # baseline scenario is mandatory (spec §3)
    iv_shifts = tuple(sorted(set(shifts)))

    try:
        a, b = (float(x) for x in args.delta_bands.split(","))
    except ValueError:
        raise ParamError(f"--delta-bands 解析失敗：{args.delta_bands!r}") from None
    if not (0.0 < a < b < 1.0):
        raise ParamError("--delta-bands 需滿足 0 < a < b < 1")

    return AnalysisParams(
        target_price=args.target_price, target_date=args.target_date,
        strategy=args.strategy, min_expiry=args.min_expiry,
        top=args.top, iv_shifts=iv_shifts, rate=args.rate,
        min_oi=args.min_oi, min_volume=args.min_volume,
        max_spread_pct=args.max_spread_pct, spread_floor=args.spread_floor,
        delta_bands=(a, b), min_return=args.min_return,
        force=args.force, matrix_all=args.matrix_all,
    )


def validate_scenario(p: AnalysisParams, spot: float, today: date) -> None:
    if date.fromisoformat(p.target_date) <= today:
        raise ParamError(f"--target-date 必須晚於資料日 {today.isoformat()}")
    if is_bullish(p.strategy):
        if p.target_price <= spot and not p.force:
            raise ParamError(
                f"看漲策略目標價 {p.target_price} 低於現價 {spot}；確定要跑請加 --force")
    else:
        if p.target_price >= spot and not p.force:
            raise ParamError(
                f"看跌策略目標價 {p.target_price} 高於現價 {spot}；確定要跑請加 --force")


from .data.snapshot import load_snapshot, save_snapshot, snapshot_today
from .filters import apply_filters
from .models import FetchError, SnapshotSchemaError, SPREAD_STRATEGIES
from .ranking import rank
from .report import render, render_filter_only
from .valuation import evaluate_contract

USAGE_HINT = "用法示例: option-chaser XYZ --target-price 120 --target-date 2026-08-28 --strategy long-call"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        p = resolve_params(args)
        if p.strategy in SPREAD_STRATEGIES:
            raise ParamError("價差策略於本版後續任務啟用")
    except ParamError as e:
        print(f"參數錯誤: {e}")
        print(USAGE_HINT)
        return 2

    try:
        if args.snapshot:
            snap = load_snapshot(args.snapshot)
        else:
            from .data.yf import fetch_chain  # lazy: offline runs never import yfinance

            snap = fetch_chain(args.symbol)
            out = Path("snapshots") / f"{snap.symbol}_{snap.fetched_at.replace(':', '')}.json"
            out.parent.mkdir(exist_ok=True)
            save_snapshot(snap, out)
    except (FetchError, SnapshotSchemaError, OSError) as e:
        print(f"資料錯誤: {e}")
        return 1

    today = snapshot_today(snap.fetched_at)
    try:
        validate_scenario(p, snap.spot, today)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        return 2

    qualified, freport = apply_filters(snap.contracts, p, today)
    if not qualified:
        print(render_filter_only(snap, p, freport, today))
        return 1

    vals = [evaluate_contract(c, snap.spot, today, p) for c in qualified]
    ranked = rank(vals, p)
    text = render(snap, p, freport, ranked, n_qualified=len(qualified), today=today)
    print(text, end="")  # render() already ends with \n; keep stdout == --md content
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    return 0
