"""PROTOTYPE DIAGNOSTIC — 直接讀 vendor 的 `updated` 時戳，驗證
「+30～40 vol points 系統性偏差 ＝ 快照過期造成的 T 錯配」這個診斷。

見 `docs/research/historical-iv-reconstruction-bias-diagnosis.md`。

本地數值分析（不需要 vendor）已經證明：把 T 從 3 天改成 7 天，183 筆
真實觀測的 MAE 從 0.3813 掉到 0.0020（190 倍），ratio 從 1.5249 收斂到
1.0001。7 天回推的快照日 ＝ 2026-08-14（星期五），而 prototype 是
2026-08-18（星期二）跑的——推論是 vendor 給的是**上一個交易日收盤的
延遲報價**（HTTP 203 ＝ non-authoritative，本 repo `marketdata.py`
既有註解已記錄 vendor 用這個狀態碼表示延遲報價）。

這支腳本把「推論」變成「直接觀測」：`map_chain_payload()` 只取
bid/ask/last/iv 等欄位，**不取 `updated`**，所以 prototype 當時無從得知
快照自己的時戳。這裡直接打同一個端點、印出原始 `updated`，並且用
「今天」與「快照自己的日期」兩種 T 各反解一次做對照。

順便抓一個 medium／LEAPS 到期日（calibration 那輪因 vendor 403 沒拿到），
補上 §4 sensitivity 分析預測「同樣的 4 天過期在長天期只值 0.1 vol pt」
的實證。

Run（需要真實 `MARKETDATA_APP_TOKEN`；沙箱 proxy 擋住 vendor，需在 CI 跑）：

    PYTHONPATH=. MARKETDATA_APP_TOKEN=xxx python3 \\
        scripts/prototype_iv_staleness_probe.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone

from option_chaser import dividends as div_module
from option_chaser import ratecurve
from option_chaser.data import dividends as data_dividends
from option_chaser.data import marketdata
from option_chaser.data import treasury
from option_chaser.valuation import DAYS_PER_YEAR, days_between, implied_vol

SYMBOLS = ("TLT", "ORCL")


def raw_chain(symbol: str, token: str, expiration: str | None = None) -> tuple[int, dict]:
    """打 chain 端點，回 (http_status, payload)。用 `_http_request`（不是
    `_http_get`）才拿得到狀態碼——203 vs 200 正是「延遲 vs 即時」的訊號。"""
    url = marketdata._CHAIN_URL.format(symbol=symbol.upper())
    if expiration:
        url += f"?expiration={expiration}"
    resp = marketdata._http_request(url, token)
    return resp.status, json.loads(resp.body)


def summarize_updated(payload: dict) -> dict:
    """`updated` 欄位（Unix 秒）→ 這批報價實際上是哪一天的。"""
    updated = payload.get("updated") or []
    stamps = [u for u in updated if isinstance(u, (int, float))]
    if not stamps:
        return {"n": 0}
    dts = [datetime.fromtimestamp(int(u), tz=timezone.utc) for u in stamps]
    dates = sorted({d.date().isoformat() for d in dts})
    return {"n": len(stamps), "distinct_dates": dates,
            "min": min(dts).isoformat(), "max": max(dts).isoformat()}


def main() -> int:
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    if not token:
        print("MARKETDATA_APP_TOKEN 未設定", file=sys.stderr)
        return 1

    today = date.today()
    print(f"### wall-clock today (UTC) = {today} ({today.strftime('%A')})")
    curve, curve_note = treasury.load_rate_curve(today)
    print(f"### rate curve: {curve_note}")

    for symbol in SYMBOLS:
        print("\n" + "=" * 78)
        print(f"## {symbol}")
        print("=" * 78)
        try:
            status, payload = raw_chain(symbol, token)
        except Exception as e:  # noqa: BLE001 — 診斷腳本，失敗就如實印出
            print(f"  chain 抓取失敗：{e!r}")
            continue

        print(f"  HTTP status = {status}   (203 = non-authoritative = vendor 延遲報價)")
        print(f"  vendor s    = {payload.get('s')!r}")
        upd = summarize_updated(payload)
        print(f"  `updated` 欄位：{upd}")

        spot = next((marketdata._num(r.get("underlyingPrice"))
                     for r in marketdata._rows(payload)
                     if marketdata._num(r.get("underlyingPrice")) is not None), None)
        print(f"  underlyingPrice = {spot}")

        # vendor 自己的 dte 欄位 vs 我們自己算的
        rows = marketdata._rows(payload)
        sample = next((r for r in rows if r.get("optionSymbol")), None)
        if sample is not None:
            exp_iso = marketdata._expiry(sample.get("expiration"))
            vendor_dte = sample.get("dte")
            our_dte = days_between(today, date.fromisoformat(exp_iso))
            print(f"  sample contract  : {sample.get('optionSymbol')}")
            print(f"    expiration     : {exp_iso}")
            print(f"    vendor `dte`   : {vendor_dte}      <-- vendor 自己說還有幾天")
            print(f"    our days_between(today, expiry) : {our_dte}   <-- prototype 用的")
            if isinstance(vendor_dte, (int, float)) and vendor_dte != our_dte:
                print(f"    *** 不一致：差 {vendor_dte - our_dte} 天 ***")

        hist, div_note = data_dividends.load_dividend_history(symbol, today)
        q = div_module.compute_q(hist, spot, today) if (hist and spot) else None
        print(f"  dividend: {div_note}  q={q}")

        # 兩種 T 各反解一次做對照
        if curve is None or q is None or spot is None:
            print("  （缺 r/q/spot，跳過反解對照）")
            continue
        snap_dates = upd.get("distinct_dates") or []
        snap_date = date.fromisoformat(snap_dates[-1]) if snap_dates else None
        print(f"\n  {'occ':<24}{'vendor_iv':>10}{'iv@today':>10}{'iv@snapshot':>13}{'Δtoday':>9}{'Δsnap':>9}")
        shown = 0
        for r in rows:
            occ = r.get("optionSymbol")
            iv_v = marketdata._num(r.get("iv"))
            bid = marketdata._num(r.get("bid")); ask = marketdata._num(r.get("ask"))
            side = str(r.get("side") or "").lower()
            if not occ or iv_v is None or bid is None or ask is None or side not in ("call", "put"):
                continue
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            mid = (bid + ask) / 2.0
            K = float(r["strike"]); exp_iso = marketdata._expiry(r.get("expiration"))
            expd = date.fromisoformat(exp_iso)
            d_today = days_between(today, expd)
            if d_today <= 0:
                continue
            iv_today = implied_vol(side, mid, spot, K, d_today / DAYS_PER_YEAR,
                                   ratecurve.rate_for_tenor(curve, d_today / DAYS_PER_YEAR), q)
            iv_snap = None
            if snap_date is not None:
                d_snap = days_between(snap_date, expd)
                if d_snap > 0:
                    iv_snap = implied_vol(side, mid, spot, K, d_snap / DAYS_PER_YEAR,
                                          ratecurve.rate_for_tenor(curve, d_snap / DAYS_PER_YEAR), q)
            f = lambda x: "   n/a" if x is None else f"{x:.4f}"
            dt_ = "   n/a" if iv_today is None else f"{iv_today - iv_v:+.4f}"
            ds_ = "   n/a" if iv_snap is None else f"{iv_snap - iv_v:+.4f}"
            print(f"  {occ:<24}{iv_v:>10.4f}{f(iv_today):>10}{f(iv_snap):>13}{dt_:>9}{ds_:>9}")
            shown += 1
            if shown >= 6:
                break

        # medium / LEAPS：calibration 那輪沒拿到，補一個
        try:
            exp_raw = marketdata._http_get(
                marketdata._BASE + f"/options/expirations/{symbol.upper()}/", token)
            exps = json.loads(exp_raw).get("expirations") or []
            far = [e for e in exps if days_between(today, date.fromisoformat(e)) >= 300]
            if far:
                pick = far[0]
                print(f"\n  --- LEAPS 到期日 {pick}"
                      f"（{days_between(today, date.fromisoformat(pick))} 天）---")
                st2, pay2 = raw_chain(symbol, token, pick)
                print(f"  HTTP status = {st2}  s = {pay2.get('s')!r}  "
                      f"updated: {summarize_updated(pay2)}")
                shown = 0
                print(f"  {'occ':<24}{'vendor_iv':>10}{'iv@today':>10}{'iv@snapshot':>13}{'Δtoday':>9}{'Δsnap':>9}")
                for r in marketdata._rows(pay2):
                    occ = r.get("optionSymbol"); iv_v = marketdata._num(r.get("iv"))
                    bid = marketdata._num(r.get("bid")); ask = marketdata._num(r.get("ask"))
                    side = str(r.get("side") or "").lower()
                    if not occ or iv_v is None or bid is None or ask is None: continue
                    if side not in ("call", "put") or bid <= 0 or ask <= 0 or ask < bid: continue
                    mid = (bid + ask) / 2.0; K = float(r["strike"])
                    expd = date.fromisoformat(marketdata._expiry(r.get("expiration")))
                    d_today = days_between(today, expd)
                    if d_today <= 0: continue
                    iv_today = implied_vol(side, mid, spot, K, d_today / DAYS_PER_YEAR,
                                           ratecurve.rate_for_tenor(curve, d_today / DAYS_PER_YEAR), q)
                    iv_snap = None
                    if snap_date is not None:
                        d_snap = days_between(snap_date, expd)
                        if d_snap > 0:
                            iv_snap = implied_vol(side, mid, spot, K, d_snap / DAYS_PER_YEAR,
                                                  ratecurve.rate_for_tenor(curve, d_snap / DAYS_PER_YEAR), q)
                    f = lambda x: "   n/a" if x is None else f"{x:.4f}"
                    dt_ = "   n/a" if iv_today is None else f"{iv_today - iv_v:+.4f}"
                    ds_ = "   n/a" if iv_snap is None else f"{iv_snap - iv_v:+.4f}"
                    print(f"  {occ:<24}{iv_v:>10.4f}{f(iv_today):>10}{f(iv_snap):>13}{dt_:>9}{ds_:>9}")
                    shown += 1
                    if shown >= 8: break
        except Exception as e:  # noqa: BLE001
            print(f"  LEAPS 抓取失敗（不影響上面的結論）：{e!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
