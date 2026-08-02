"""CLI entry point: arg parsing, validation, orchestration (spec §3, §8)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .models import AnalysisParams, ParamError, STRATEGIES, is_bullish
from .timeframe import TargetMonth, ensure_month_open, parse_target_month


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
    ap.add_argument("--target-month", required=True,
                    help="目標年月：2028/1、2028/01、28/1、28/01 皆可")
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="long-call")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--iv-shifts", default="-0.2,0,0.2")
    # default=None 以分辨「使用者明示」與「未指定」：明示 → 跳過利率曲線管線
    # （保留現有語意）；未指定 → 網路路徑走期限對齊曲線，fallback 0.04。
    ap.add_argument("--rate", type=float, default=None)
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


def resolve_params(args: argparse.Namespace) -> AnalysisParams:
    if not args.symbol or not args.symbol.strip():
        raise ParamError("symbol 必須為非空字串")
    if args.target_price <= 0:
        raise ParamError("--target-price 必須 > 0")
    target_month = parse_target_month(args.target_month).key()
    if not 1 <= args.top <= 10:
        raise ParamError("--top 必須在 1–10")
    if args.rate is not None and args.rate < 0:
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
        target_price=args.target_price, target_month=target_month,
        strategy=args.strategy,
        top=args.top, iv_shifts=iv_shifts,
        rate=args.rate if args.rate is not None else 0.04,
        rate_explicit=args.rate is not None,
        min_oi=args.min_oi, min_volume=args.min_volume,
        max_spread_pct=args.max_spread_pct, spread_floor=args.spread_floor,
        delta_bands=(a, b), min_return=args.min_return,
        force=args.force, matrix_all=args.matrix_all,
    )


def validate_scenario(p: AnalysisParams, spot: float, today: date) -> None:
    ensure_month_open(TargetMonth.from_key(p.target_month), today)
    if is_bullish(p.strategy):
        if p.target_price <= spot and not p.force:
            raise ParamError(
                f"看漲策略目標價 {p.target_price} 低於現價 {spot}；確定要跑請加 --force")
    else:
        if p.target_price >= spot and not p.force:
            raise ParamError(
                f"看跌策略目標價 {p.target_price} 高於現價 {spot}；確定要跑請加 --force")


from .models import FetchError, SnapshotSchemaError, SPREAD_STRATEGIES
from . import service

USAGE_HINT = "用法示例: option-chaser XYZ --target-price 120 --target-month 2026/8 --strategy long-call"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        p = resolve_params(args)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        print(USAGE_HINT)
        return 2

    request = service.AnalysisRequest(symbol=args.symbol, base_params=p,
                                      strategies=(p.strategy,))
    try:
        if args.snapshot:
            result = service.run_offline(request, args.snapshot)
        else:
            result = service.run(request)
    except ParamError as e:
        print(f"參數錯誤: {e}")
        return 2
    except (FetchError, SnapshotSchemaError, OSError) as e:
        print(f"資料錯誤: {e}")
        return 1

    res = result.results[0]
    if res.status == "skipped_direction":
        try:
            validate_scenario(p, result.snapshot.spot, result.today)
        except ParamError as e:
            print(f"參數錯誤: {e}")
        return 2

    text = res.report_text
    if res.status == "empty":
        if p.strategy in SPREAD_STRATEGIES:
            print(text, end="")
        else:
            print(text)
        return 1
    print(text, end="")
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    return 0
