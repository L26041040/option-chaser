"""PROTOTYPE — throwaway calibration check for Historical IV reconstruction
recipe（見 `docs/research/historical-iv-reconstruction.md` §8）。

**目的只有一個**：驗證「Option Chaser 自己用固定 recipe 重算 IV」跟
Market Data App 已知（vendor 已給、非 null）的 IV 是否足夠一致，尤其是
高低排序／percentile 是否穩定——Historical IV Trend 是相對高低指標，
排序穩不穩定比絕對誤差更重要。

**這是丟棄式研究工具，不是 production 程式碼**：`option_chaser/`／
`api_app/` 完全不 import 這個檔案，跟既有 `scripts/research_valuation_
methods.py` 同一種角色分工。核心 pricing 邏輯**直接 import 現有
production 的 `option_chaser.valuation.implied_vol()`**，不複製任何
定價公式；資料抓取同樣直接 import 現有 production 的
`option_chaser.data.marketdata.fetch_chain()`／
`option_chaser.data.treasury.load_rate_curve()`／
`option_chaser.data.dividends.load_dividend_history()`——recipe 完全比照
`docs/research/historical-iv-reconstruction.md` §10 的建議：mid 價格、
既有 BS93 `implied_vol()`、同筆 market data 的 underlying price、
`days_between()/365` 的既有 day-count、既有 Treasury 曲線與既有 q 計算。

樣本刻意用「今日／近期快照」（vendor `iv` 非 null 的觀測），不是真的歷史
資料——這是因為 vendor 的歷史單一合約端點目前 `iv` 幾乎全部是 null
（研究文件 §2），沒有一個「已知答案」可以拿來比對；今日快照剛好相反，
vendor `iv` 通常非 null，因此可以拿來當 benchmark。用今日快照驗證「這套
recipe 反解出來的 IV 有多接近 vendor 自己的 IV」，跟「這套 recipe 套用在
歷史資料上是否一樣可信」是兩個不同但高度相關的問題——後者的可信度建立
在前者成立的基礎上（如果連今天都對不準，套到歷史上不會更準）。

Run（需要真實 `MARKETDATA_APP_TOKEN`；本地沙箱 outbound 被 proxy 擋住，
無法在這裡直接跑，需要在有網路的環境——例如既有 `tmp-*` 一次性 CI
probe 慣例——執行）：

    PYTHONPATH=. MARKETDATA_APP_TOKEN=xxx python3 \\
        scripts/prototype_historical_iv_calibration.py [SYMBOL ...]

不帶參數預設跑 TLT、ORCL（呼應需求方原本測試 vendor null-iv 現象的
兩個真實標的，且分別代表 ETF／equity、call/put 皆有機會出現）。
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import date

from option_chaser import dividends as div_module
from option_chaser import ratecurve
from option_chaser.data import dividends as data_dividends
from option_chaser.data import marketdata
from option_chaser.data import treasury
from option_chaser.valuation import DAYS_PER_YEAR, days_between, implied_vol

DEFAULT_SYMBOLS = ("TLT", "ORCL")

# relative spread 高於這個值算「寬價差」樣本，供 §5 sanity check 分組。
# 這不是一個要驗證的 gate，只是分組標準——沿用 `option-liquidity-
# filtering.md` 既有研究「業界慣例沒有統一數字」的結論，這裡取一個
# 足以把「明顯比其他樣本寬」的觀測分出來的粗略門檻。
WIDE_SPREAD_THRESHOLD = 0.15


# ---------- 資料蒐集：直接呼叫既有 production 模組，不複製任何邏輯 ----------

def _mid(bid: float | None, ask: float | None) -> float | None:
    """§10 recipe：mid 優先；bid/ask 任一缺席或倒掛則整筆跳過（不用
    last，理由見研究文件 §4.1／§3.2）。"""
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def _moneyness_bucket(option_type: str, spot: float, strike: float) -> str:
    ratio = spot / strike if option_type == "call" else strike / spot
    if ratio >= 1.05:
        return "ITM"
    if ratio <= 0.95:
        return "OTM"
    return "ATM"


def _dte_bucket(dte_days: int) -> str:
    if dte_days <= 45:
        return "short"
    if dte_days <= 180:
        return "medium"
    return "LEAPS"


# Market Data App 的 `/options/chain/{symbol}/` **不帶** `expiration=`
# 參數時，vendor 官方文件記載的預設行為是「只回下一個月選」（本 repo
# 既有 `fetch_surface()` docstring，`marketdata.py:367-368`，#134 已經
# 踩過這個坑）——這裡把同一個已知行為當成需要自己額外處理的事，不是
# 假設它會自動給我們 short/medium/LEAPS 的分佈。呼叫端額外指定
# `expiration=` 抓幾個更遠的到期日，直接沿用同一個 query 參數慣例
# （`marketdata.py:381-382` 已經在別的呼叫路徑這樣用），解析仍然
# 100% 重用 production 的 `map_chain_payload()`，不重造。
_EXPIRATIONS_URL = marketdata._BASE + "/options/expirations/{symbol}/"


def fetch_expirations(symbol: str, token: str) -> list[str]:
    raw = marketdata._http_get(_EXPIRATIONS_URL.format(symbol=symbol.upper()), token)
    payload = json.loads(raw)
    if payload.get("s") != "ok":
        return []
    return list(payload.get("expirations") or [])


def fetch_chain_for_expiration(symbol: str, token: str, expiration: str):
    fetched_at = marketdata.datetime.now(marketdata.timezone.utc).isoformat(timespec="seconds")
    url = marketdata._CHAIN_URL.format(symbol=symbol.upper()) + f"?expiration={expiration}"
    payload = json.loads(marketdata._http_get(url, token))
    return marketdata.map_chain_payload(symbol, payload, fetched_at)


def pick_diverse_expirations(expirations: list[str], today: date) -> list[str]:
    """從全部可得到期日裡各挑一個落在「medium」（90–180 天）與
    「LEAPS」（>300 天）區間的，湊出 §2 要求的 DTE 多樣性——預設
    （不帶 `expiration=`）只會拿到最近月選，見上方常數註解。挑不到
    就略過，不硬湊。"""
    picked = []
    for lo, hi in ((90, 180), (300, 3650)):
        candidates = [e for e in expirations
                     if lo <= days_between(today, date.fromisoformat(e)) <= hi]
        if candidates:
            # 落在區間內取最接近區間中點的一個，避免每次都選到邊界值。
            mid_target = (lo + hi) / 2
            best = min(candidates,
                      key=lambda e: abs(days_between(today, date.fromisoformat(e)) - mid_target))
            picked.append(best)
    return picked


def _process_contract(c, symbol: str, spot: float, today: date, curve, q: float | None) -> dict:
    """單一合約 → 一筆觀測 row（反解成功或 failure_reason）。純函式，
    給 `collect_observations()` 跟額外到期日的補抓路徑共用。"""
    mid = _mid(c.bid, c.ask)
    row = {
        "symbol": symbol, "occ": c.contract_symbol, "option_type": c.option_type,
        "strike": c.strike, "expiry": c.expiry, "bid": c.bid, "ask": c.ask,
        "mid": mid, "vendor_iv": c.implied_volatility,
        "relative_spread": ((c.ask - c.bid) / mid)
                           if (mid and c.bid is not None and c.ask is not None) else None,
    }
    if mid is None:
        row.update(our_iv=None, error=None, abs_error=None, failure=True,
                   failure_reason="no_valid_mid", dte_days=None, moneyness="?")
        return row

    expiry_date = date.fromisoformat(c.expiry)
    dte_days = days_between(today, expiry_date)
    row["dte_days"] = dte_days
    row["moneyness"] = _moneyness_bucket(c.option_type, spot, c.strike)

    if dte_days <= 0:
        row.update(our_iv=None, error=None, abs_error=None, failure=True,
                   failure_reason="expired_or_today")
        return row
    if curve is None or q is None:
        row.update(our_iv=None, error=None, abs_error=None, failure=True,
                   failure_reason="missing_rate_or_dividend_input")
        return row

    T = dte_days / DAYS_PER_YEAR
    r = ratecurve.rate_for_tenor(curve, T)
    our_iv = implied_vol(c.option_type, mid, spot, c.strike, T, r, q)
    row["T"] = T
    row["r"] = r
    row["q"] = q
    if our_iv is None:
        row.update(our_iv=None, error=None, abs_error=None, failure=True,
                   failure_reason="implied_vol_no_solution")
    else:
        err = our_iv - c.implied_volatility
        row.update(our_iv=our_iv, error=err, abs_error=abs(err), failure=False,
                   failure_reason=None)
    return row


def collect_observations(symbol: str, token: str, today: date) -> list[dict]:
    """一個標的的完整觀測清單——每筆是一個 vendor iv 非 null 的合約，
    帶 our_iv（反解成功）或 failure_reason（反解失敗／輸入缺席）。
    抓最近月選（預設行為）＋額外 1–2 個較遠到期日（DTE 多樣性，見
    `pick_diverse_expirations()`）。"""
    snapshot = marketdata.fetch_chain(symbol, token)
    curve, curve_note = treasury.load_rate_curve(today)
    hist, div_note = data_dividends.load_dividend_history(symbol, today)
    q = div_module.compute_q(hist, snapshot.spot, today) if hist is not None else None
    print(f"[{symbol}] spot={snapshot.spot} contracts={len(snapshot.contracts)} "
          f"rate_curve=({curve_note}) dividend=({div_note}) q={q}", file=sys.stderr)

    all_contracts = list(snapshot.contracts)
    try:
        expirations = fetch_expirations(symbol, token)
        extra = pick_diverse_expirations(expirations, today)
        for exp in extra:
            extra_snap = fetch_chain_for_expiration(symbol, token, exp)
            all_contracts.extend(extra_snap.contracts)
            print(f"[{symbol}] 額外抓到期日 {exp}：+{len(extra_snap.contracts)} 筆合約",
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — prototype：額外多樣性抓取失敗
        # 不影響主樣本（近月選）已經拿到的結果，記錄下來就好。
        print(f"[{symbol}] 額外到期日抓取失敗（不影響主樣本）：{e!r}", file=sys.stderr)

    rows: list[dict] = []
    for c in all_contracts:
        if c.implied_volatility is None:
            continue  # 不在 benchmark 池裡——沒有已知答案可以比對
        rows.append(_process_contract(c, symbol, snapshot.spot, today, curve, q))
    return rows


# ---------- 統計 ----------

def _percentile(values: list[float], p: float) -> float:
    """線性內插百分位（0<=p<=1）。stdlib-only，不依賴 numpy（沿用引擎
    既有「刻意排除 numpy」慣例，`heatmap-valuation-method-selection.md`
    §5.3 已記錄理由）。"""
    if not values:
        raise ValueError("empty")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = p * (len(s) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    frac = idx - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _ranks(values: list[float]) -> list[float]:
    """平均排名（處理並列值）——1 為最小。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    return _pearson(_ranks(xs), _ranks(ys))


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["failure"]]
    failures = [r for r in rows if r["failure"]]
    n = len(rows)
    summary: dict = {
        "n": n, "n_ok": len(ok), "n_failures": len(failures),
        "failure_rate": (len(failures) / n) if n else None,
        "failure_reasons": {},
    }
    for r in failures:
        reason = r["failure_reason"]
        summary["failure_reasons"][reason] = summary["failure_reasons"].get(reason, 0) + 1

    if not ok:
        return summary

    abs_errors = [r["abs_error"] for r in ok]
    errors = [r["error"] for r in ok]
    vendor_ivs = [r["vendor_iv"] for r in ok]
    our_ivs = [r["our_iv"] for r in ok]

    summary.update(
        mae=sum(abs_errors) / len(abs_errors),
        median_ae=_percentile(abs_errors, 0.5),
        p90_ae=_percentile(abs_errors, 0.9),
        bias=sum(errors) / len(errors),
        pearson=_pearson(vendor_ivs, our_ivs),
        spearman=_spearman(vendor_ivs, our_ivs),
    )

    # Percentile rank difference：把 vendor_iv／our_iv 各自換成「在這批
    # 樣本裡的百分位排名」，看兩邊排出來的百分位差多少——這是 ranking
    # stability 的另一種讀法，直接對應「歷史 IV Trend 的 percentile
    # 讀數會不會因為用 reconstruction 而跳掉」這個產品問題。
    n_ok = len(ok)
    if n_ok >= 2:
        vendor_ranks = _ranks(vendor_ivs)
        our_ranks = _ranks(our_ivs)
        vendor_pctl = [(rk - 1) / (n_ok - 1) for rk in vendor_ranks]
        our_pctl = [(rk - 1) / (n_ok - 1) for rk in our_ranks]
        pctl_diffs = [abs(a - b) for a, b in zip(vendor_pctl, our_pctl)]
        summary["percentile_rank_diff_median"] = _percentile(pctl_diffs, 0.5)
        summary["percentile_rank_diff_p90"] = _percentile(pctl_diffs, 0.9)

    return summary


def summarize_group(rows: list[dict], key_fn) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(key_fn(r), []).append(r)
    return {k: summarize(v) for k, v in groups.items()}


# ---------- 報表輸出 ----------

def print_ranked_table(rows: list[dict]) -> None:
    ok = [r for r in rows if not r["failure"]]
    ok_sorted = sorted(ok, key=lambda r: r["vendor_iv"])
    vendor_ranks = _ranks([r["vendor_iv"] for r in ok_sorted])
    our_ranks = _ranks([r["our_iv"] for r in ok_sorted])
    print(f"\n{'occ':<24}{'vendor_iv':>10}{'our_iv':>10}{'rank_v':>8}{'rank_o':>8}{'abs_err':>10}")
    for r, rv, ro in zip(ok_sorted, vendor_ranks, our_ranks):
        print(f"{r['occ']:<24}{r['vendor_iv']:>10.4f}{r['our_iv']:>10.4f}"
              f"{rv:>8.1f}{ro:>8.1f}{r['abs_error']:>10.4f}")


def print_spread_quality_check(rows: list[dict], top_n: int = 8) -> None:
    ok = [r for r in rows if not r["failure"] and r["relative_spread"] is not None]
    widest = sorted(ok, key=lambda r: r["relative_spread"], reverse=True)[:top_n]
    print(f"\n最寬 {len(widest)} 筆 relative spread（(ask-bid)/mid）："
          f"{'occ':<24}{'rel_spread':>12}{'abs_err':>10}")
    for r in widest:
        print(f"{r['occ']:<24}{r['relative_spread']:>12.3f}{r['abs_error']:>10.4f}")

    narrow = [r for r in ok if r["relative_spread"] < WIDE_SPREAD_THRESHOLD]
    wide = [r for r in ok if r["relative_spread"] >= WIDE_SPREAD_THRESHOLD]
    if narrow and wide:
        mae_narrow = sum(r["abs_error"] for r in narrow) / len(narrow)
        mae_wide = sum(r["abs_error"] for r in wide) / len(wide)
        print(f"\n窄價差（<{WIDE_SPREAD_THRESHOLD:.0%}，n={len(narrow)}）MAE="
              f"{mae_narrow:.4f}；寬價差（>={WIDE_SPREAD_THRESHOLD:.0%}，"
              f"n={len(wide)}）MAE={mae_wide:.4f}")
    else:
        print("\n（樣本在寬/窄價差兩側分佈不足，略過窄 vs 寬 MAE 對照）")


def print_summary(label: str, summary: dict) -> None:
    print(f"\n=== {label} ===")
    print(f"n={summary['n']} ok={summary['n_ok']} failures={summary['n_failures']} "
          f"failure_rate={summary['failure_rate']:.1%}"
          if summary.get("failure_rate") is not None else
          f"n={summary['n']} ok={summary['n_ok']} failures={summary['n_failures']}")
    if summary["failure_reasons"]:
        print(f"  failure reasons: {summary['failure_reasons']}")
    if "mae" in summary:
        print(f"  MAE={summary['mae']:.4f}  median_AE={summary['median_ae']:.4f}  "
              f"p90_AE={summary['p90_ae']:.4f}  bias={summary['bias']:+.4f}")
        pearson = summary.get("pearson")
        spearman = summary.get("spearman")
        print(f"  Pearson={pearson:.4f}" if pearson is not None else "  Pearson=N/A(n<2)")
        print(f"  Spearman={spearman:.4f}" if spearman is not None else "  Spearman=N/A(n<2)")
        if "percentile_rank_diff_median" in summary:
            print(f"  percentile_rank_diff: median={summary['percentile_rank_diff_median']:.3f} "
                  f"p90={summary['percentile_rank_diff_p90']:.3f}")
    else:
        print("  （沒有任何成功反解的觀測，無法算精度指標）")


def main(argv: list[str]) -> int:
    symbols = tuple(argv) if argv else DEFAULT_SYMBOLS
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    if not token:
        print("MARKETDATA_APP_TOKEN 未設定——這個 prototype 需要真實 vendor "
              "credential 才能拿到 benchmark 樣本（vendor iv 非 null 的今日"
              "快照），本地沙箱通常連不到 vendor，需要在有網路的環境跑"
              "（例如既有 tmp-* 一次性 CI probe 慣例）。", file=sys.stderr)
        return 1

    today = date.today()
    all_rows: list[dict] = []
    for symbol in symbols:
        try:
            all_rows.extend(collect_observations(symbol, token, today))
        except Exception as e:  # noqa: BLE001 — prototype：單一標的失敗不擋住其他標的
            print(f"[{symbol}] 抓取失敗：{e!r}", file=sys.stderr)

    if not all_rows:
        print("沒有任何觀測——所有標的都抓取失敗，或整批都沒有 vendor iv。",
              file=sys.stderr)
        return 1

    print(f"\n總觀測數（vendor iv 非 null）：{len(all_rows)}")

    print_summary("整體", summarize(all_rows))

    print("\n--- 分群：moneyness ---")
    for k, s in sorted(summarize_group(all_rows, lambda r: r["moneyness"]).items()):
        print_summary(f"moneyness={k}", s)

    print("\n--- 分群：DTE bucket ---")
    dte_groups = summarize_group(
        all_rows, lambda r: _dte_bucket(r["dte_days"]) if r.get("dte_days") else "unknown")
    for k in ("short", "medium", "LEAPS", "unknown"):
        if k in dte_groups:
            print_summary(f"dte={k}", dte_groups[k])

    print("\n--- 分群：option_type ---")
    for k, s in sorted(summarize_group(all_rows, lambda r: r["option_type"]).items()):
        print_summary(f"option_type={k}", s)

    print_ranked_table(all_rows)
    print_spread_quality_check(all_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
