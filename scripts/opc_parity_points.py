"""輸出 OPC parity 人工驗證測試點（issue #26 驗收；驗證協議見 A13.5）。

對指定 snapshot 跑一次分析，取主策略第一名候選，輸出 9 個
（估值日 × 標的價）測試點的模型每股價值，供需求方至
optionsprofitcalculator.com 以相同合約、相同日期／價位人工對照。

用法（離線快照，r 用固定值或 --rate）：
    PYTHONPATH=. python scripts/opc_parity_points.py snapshots/TLT_xxx.json \
        --target-price 105 --target-month 2028/1 [--strategy long-call]
加 --use-curve 則啟用 T12 利率曲線管線（會連網抓 Treasury 曲線）。
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from option_chaser import service
from option_chaser.cli import build_parser as cli_parser
from option_chaser.cli import resolve_params
from option_chaser.models import SPREAD_STRATEGIES, STRATEGIES
from option_chaser.valuation import (SpreadValuation, leg_rate,
                                     scenario_leg_value, spread_scenario_value)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("snapshot")
    ap.add_argument("--target-price", type=float, required=True)
    ap.add_argument("--target-month", required=True)
    ap.add_argument("--strategy", choices=list(STRATEGIES), default="long-call")
    ap.add_argument("--rate", type=float, default=None)
    ap.add_argument("--use-curve", action="store_true",
                    help="啟用 T12 利率曲線管線（連網抓 Treasury 曲線）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # 借用 CLI 的 parser 與參數歸一（含 --rate 明示語意）——預設值單一來源，
    # 不在此處手抄
    cli_argv = ["X", "--target-price", str(args.target_price),
                "--target-month", args.target_month,
                "--strategy", args.strategy]
    if args.rate is not None:
        cli_argv += ["--rate", str(args.rate)]
    p = resolve_params(cli_parser().parse_args(cli_argv))
    request = service.AnalysisRequest(symbol="X", base_params=p,
                                      strategies=(p.strategy,))
    loader = service.default_rate_curve_loader if args.use_curve else None
    result = service.run_offline(request, args.snapshot,
                                 rate_curve_loader=loader)
    res = result.results[0]
    if res.status != "ok" or not res.candidates:
        print(f"無合格候選（status={res.status}）：{res.message}")
        return 1
    p = result.request.base_params            # 含解出的 rate_by_expiry
    val = res.candidates[0].valuation
    today, spot = result.today, result.snapshot.spot

    if isinstance(val, SpreadValuation):
        lng, sht = val.long_leg, val.short_leg
        expiry = date.fromisoformat(lng.expiry)
        ident = (f"{lng.contract_symbol}(買)/{sht.contract_symbol}(賣) "
                 f"K={lng.strike:g}/{sht.strike:g} exp={lng.expiry} "
                 f"IV={lng.implied_volatility:.4f}/{sht.implied_volatility:.4f}")
        cost = val.net_worst

        def value(S: float, at: date) -> float:
            return spread_scenario_value(lng, sht, S, at, p)
    else:
        c = val.contract
        expiry = date.fromisoformat(c.expiry)
        ident = (f"{c.contract_symbol} K={c.strike:g} exp={c.expiry} "
                 f"IV={c.implied_volatility:.4f}")
        cost = c.ask

        def value(S: float, at: date) -> float:
            return scenario_leg_value(c, S, at, p)

    exp_key = lng.expiry if isinstance(val, SpreadValuation) else val.contract.expiry
    print(f"OPC parity 測試點（{res.strategy}；成本口徑=最差進場）")
    print(f"- 合約: {ident}")
    print(f"- 現價 {spot:g} / 目標價 {p.target_price:g} / 分析日 {today.isoformat()}")
    print(f"- r = {leg_rate(p, exp_key):.4%}"
          + (f"（{p.rate_note}）" if p.rate_note else "（固定）")
          + f" / 進場成本 {cost:.2f}")
    print()
    total = (expiry - today).days
    dates = [today + timedelta(days=round(total * f)) for f in (1 / 3, 2 / 3)]
    dates.append(expiry)
    prices = [spot, spot + 0.5 * (p.target_price - spot), p.target_price]
    print(f"{'估值日':<12}{'標的價':>10}{'模型每股值':>12}")
    for at in dates:
        for S in prices:
            print(f"{at.isoformat():<12}{S:>10.2f}{value(S, at):>12.4f}")
    print()
    print("OPC 對照方式：同合約、同到期日，OPC 矩陣取同日期欄／價格列的"
          "每股估值；誤差容忍帶見 docs/research/opc-heatmap-comparison.md §5。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
