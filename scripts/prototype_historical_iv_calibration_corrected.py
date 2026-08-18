"""PROTOTYPE — corrected calibration: 用觀測自己的日期算 T／r／q，不用
`date.today()`。見 `docs/research/historical-iv-reconstruction-bias-
diagnosis.md`（診斷出上一輪 +38 vol points 偏差的真因＝參照日錯配）。

**丟棄式研究工具，不是 production 程式碼**：跟既有
`scripts/prototype_historical_iv_calibration.py`／
`scripts/prototype_iv_staleness_probe.py` 同一種角色。核心定價邏輯
直接 import production 的 `implied_vol()`；資料抓取直接 import
production 的 `marketdata.fetch_chain_for_expiration` 等價邏輯（沿用
上一版 prototype 已經寫好的 `fetch_chain_for_expiration()`／
`pick_diverse_expirations()`）。

**跟上一版的關鍵差異**（修正診斷文件點名的三個取數缺口）：

1. `observation_date` 來自 vendor 這批報價自己的 `updated` 欄位（整個
   chain 回應是單一均勻時戳，已由 staleness probe 實測確認），不是
   `date.today()`。
2. T 用 `days_between(observation_date, expiration)`。
3. r：抓 Treasury CSV 全年資料後，自己挑「≤ observation_date 的最近
   一列」（production 的 `ratecurve.parse_treasury_csv()` 永遠只挑
   全檔最大日期那列，是為「今天」場景設計的——這裡重用它的底層 CSV
   解析 primitive，只是換一個「挑哪一列」的邏輯，不改 production
   檔案）。
4. q：只用 `ex_date <= observation_date` 的配息記錄（production 的
   `compute_q()` 只有下界 cutoff，沒有上界——直接沿用會讓「抓取當下已
   公開、但 observation_date 當時還沒發生」的配息偷跑進來，是研究文件
   §7 點名的 look-ahead bias），除以 observation_date 當天的
   `underlyingPrice`。

Run（需要真實 `MARKETDATA_APP_TOKEN`；本地沙箱擋 vendor，需在 CI 跑）：

    PYTHONPATH=. MARKETDATA_APP_TOKEN=xxx python3 \\
        scripts/prototype_historical_iv_calibration_corrected.py [SYMBOL ...]
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


# ---------- 到期日多樣性（沿用上一版 prototype 已驗證過的邏輯） ----------

_EXPIRATIONS_URL = marketdata._BASE + "/options/expirations/{symbol}/"


def fetch_expirations(symbol: str, token: str) -> list[str]:
    raw = marketdata._http_get(_EXPIRATIONS_URL.format(symbol=symbol.upper()), token)
    payload = json.loads(raw)
    if payload.get("s") != "ok":
        return []
    return list(payload.get("expirations") or [])


def fetch_chain_for_expiration(symbol: str, token: str, expiration: str):
    """跟上一版一樣，但回傳原始 payload（不是 `map_chain_payload()` 已經
    轉好的 `ChainSnapshot`）——這裡需要原始 `updated` 欄位，
    `map_chain_payload()` 不保留它。"""
    url = marketdata._CHAIN_URL.format(symbol=symbol.upper()) + f"?expiration={expiration}"
    return json.loads(marketdata._http_get(url, token))


def pick_diverse_expirations(expirations: list[str], today: date) -> dict[str, str]:
    """跟上一版邏輯相同，但回傳 {bucket_name: expiration} 方便分群列印。"""
    picked: dict[str, str] = {}
    for lo, hi, name in ((14, 60, "medium_short"), (90, 200, "medium"), (300, 3650, "leaps")):
        candidates = [e for e in expirations
                     if lo <= days_between(today, date.fromisoformat(e)) <= hi]
        if candidates:
            mid_target = (lo + hi) / 2
            best = min(candidates,
                      key=lambda e: abs(days_between(today, date.fromisoformat(e)) - mid_target))
            picked[name] = best
    return picked


# ---------- observation_date（vendor `updated`，非 today） ----------

def snapshot_date(payload: dict) -> date | None:
    """整個 chain 回應共用一個 `updated` 時戳（已由 staleness probe 實測
    確認），取第一筆非空值即可代表整批。"""
    for u in (payload.get("updated") or []):
        if isinstance(u, (int, float)):
            return marketdata.datetime.fromtimestamp(
                int(u), tz=marketdata.timezone.utc).date()
    return None


# ---------- Point-in-time r：重用 ratecurve 的 CSV 底層 primitive ----------

def fetch_curve_asof(observation_date: date) -> ratecurve.RateCurve | None:
    """抓 observation_date 那一年的 Treasury CSV 全年資料，自己挑
    「<= observation_date 的最近一列」——production 的
    `parse_treasury_csv()` 永遠挑全檔最大日期，是為今天場景設計的，
    這裡不改那個函式，只是不呼叫它，改呼叫它用的同一批底層 primitive
    （`ratecurve._CSV_TENOR_RE` 等）自己做「挑哪一列」。"""
    try:
        text = treasury._http_get(treasury.CSV_URL.format(year=observation_date.year))
    except Exception:  # noqa: BLE001 — 抓不到就讓呼叫端退回「今天的曲線」
        return None
    import csv as csv_module
    import io
    rows = list(csv_module.reader(io.StringIO(text)))
    if not rows:
        return None
    header = [h.strip() for h in rows[0]]
    if not header or header[0].lower() != "date":
        return None
    tenor_cols = {}
    for i, name in enumerate(header[1:], start=1):
        m = ratecurve._CSV_TENOR_RE.match(name)
        if m:
            tenor_cols[i] = ratecurve._tenor_years(m.group(1), m.group(2))
    if not tenor_cols:
        return None
    best: tuple[str, tuple[tuple[float, float], ...]] | None = None
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        try:
            curve_date = ratecurve._parse_curve_date(row[0])
        except ratecurve.CurveParseError:
            continue
        if date.fromisoformat(curve_date) > observation_date:
            continue  # 只要 <= observation_date 的列，避免抓到未來的曲線
        pairs = tuple((tenor, y) for i, tenor in tenor_cols.items()
                      if i < len(row) and (y := ratecurve._parse_percent(row[i])) is not None)
        if not pairs:
            continue
        if best is None or curve_date > best[0]:
            best = (curve_date, pairs)
    if best is None:
        return None
    return ratecurve.curve_from_par_yields(*best)


# ---------- Point-in-time q：只用 observation_date 當時已知的配息 ----------

def compute_q_asof(history, spot: float, observation_date: date,
                   *, ex_date_cutoff: date | None = None) -> float:
    """跟 production 的 `dividends.compute_q()` 同一個定義（TTM 經常性
    現金分配 / spot），但額外加一個上界：`ex_date <= observation_date`
    ——`compute_q()` 只有下界（TTM 窗），這裡補上界避免「抓取當下已公開、
    observation_date 當時還沒發生」的配息偷跑進來（研究文件 §7 的
    look-ahead bias 紅線）。異常值防護沿用 production 的
    `_dampen_outliers()`，不重寫。"""
    if spot <= 0:
        return 0.0
    cutoff = ex_date_cutoff or date(observation_date.year - 1, observation_date.month,
                                    observation_date.day)
    amounts = tuple(
        r.amount for r in history.distributions
        if cutoff < date.fromisoformat(r.ex_date) <= observation_date)
    if not amounts:
        return 0.0
    return sum(div_module._dampen_outliers(amounts)) / spot


# ---------- 每筆合約 → 一筆觀測 ----------

def _mid(bid, ask):
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def _moneyness_bucket(option_type, spot, strike):
    ratio = spot / strike if option_type == "call" else strike / spot
    if ratio >= 1.05:
        return "ITM"
    if ratio <= 0.95:
        return "OTM"
    return "ATM"


def process_chain(symbol: str, payload: dict, curve, q_history, tenor_bucket: str) -> list[dict]:
    obs_date = snapshot_date(payload)
    rows: list[dict] = []
    if obs_date is None:
        print(f"  [{symbol}/{tenor_bucket}] 沒有 `updated` 欄位，整批跳過", file=sys.stderr)
        return rows

    spot = next((marketdata._num(r.get("underlyingPrice"))
                 for r in marketdata._rows(payload)
                 if marketdata._num(r.get("underlyingPrice")) is not None), None)
    if spot is None:
        print(f"  [{symbol}/{tenor_bucket}] 沒有 underlyingPrice，整批跳過", file=sys.stderr)
        return rows

    q = compute_q_asof(q_history, spot, obs_date) if q_history is not None else None
    r_curve = curve  # 已經是 point-in-time（fetch_curve_asof 的結果）或 None
    print(f"  [{symbol}/{tenor_bucket}] observation_date={obs_date}  spot={spot}  "
          f"q_asof={q}  r_curve={'ok' if r_curve else 'MISSING'}", file=sys.stderr)

    for row in marketdata._rows(payload):
        occ = row.get("optionSymbol")
        iv_v = marketdata._num(row.get("iv"))
        side = str(row.get("side") or "").lower()
        if not occ or iv_v is None or side not in ("call", "put"):
            continue
        bid = marketdata._num(row.get("bid")); ask = marketdata._num(row.get("ask"))
        mid = _mid(bid, ask)
        exp_iso = marketdata._expiry(row.get("expiration"))
        expd = date.fromisoformat(exp_iso)
        dte_days = days_between(obs_date, expd)
        out = dict(symbol=symbol, tenor_bucket=tenor_bucket, occ=occ, option_type=side,
                  strike=float(row["strike"]), expiry=exp_iso, obs_date=obs_date.isoformat(),
                  bid=bid, ask=ask, mid=mid, vendor_iv=iv_v, dte_days=dte_days,
                  moneyness=_moneyness_bucket(side, spot, float(row["strike"])) if mid else "?")
        if mid is None:
            out.update(our_iv=None, error=None, abs_error=None, failure=True,
                       failure_reason="no_valid_mid")
            rows.append(out); continue
        if dte_days <= 0:
            out.update(our_iv=None, error=None, abs_error=None, failure=True,
                       failure_reason="expired_or_today")
            rows.append(out); continue
        if r_curve is None or q is None:
            out.update(our_iv=None, error=None, abs_error=None, failure=True,
                       failure_reason="missing_rate_or_dividend_input")
            rows.append(out); continue
        T = dte_days / DAYS_PER_YEAR
        r = ratecurve.rate_for_tenor(r_curve, T)
        our_iv = implied_vol(side, mid, spot, float(row["strike"]), T, r, q)
        out["T"] = T; out["r"] = r; out["q"] = q
        if our_iv is None:
            out.update(our_iv=None, error=None, abs_error=None, failure=True,
                       failure_reason="implied_vol_no_solution")
        else:
            err = our_iv - iv_v
            out.update(our_iv=our_iv, error=err, abs_error=abs(err), failure=False,
                       failure_reason=None)
        rows.append(out)
    return rows


# ---------- 統計（跟上一版一致，複製過來避免又去 import 上一版腳本） ----------

def _percentile(values, p):
    s = sorted(values)
    if len(s) == 1: return s[0]
    idx = p * (len(s) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi: return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _ranks(values):
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


def _pearson(xs, ys):
    n = len(xs)
    if n < 2: return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs); vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0: return None
    return cov / math.sqrt(vx * vy)


def _spearman(xs, ys):
    return _pearson(_ranks(xs), _ranks(ys))


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["failure"]]
    failures = [r for r in rows if r["failure"]]
    n = len(rows)
    s = {"n": n, "n_ok": len(ok), "n_failures": len(failures),
        "failure_rate": (len(failures) / n) if n else None, "failure_reasons": {}}
    for r in failures:
        s["failure_reasons"][r["failure_reason"]] = s["failure_reasons"].get(r["failure_reason"], 0) + 1
    if not ok:
        return s
    abs_errors = [r["abs_error"] for r in ok]; errors = [r["error"] for r in ok]
    vendor_ivs = [r["vendor_iv"] for r in ok]; our_ivs = [r["our_iv"] for r in ok]
    s.update(mae=sum(abs_errors) / len(abs_errors), median_ae=_percentile(abs_errors, 0.5),
            p90_ae=_percentile(abs_errors, 0.9), bias=sum(errors) / len(errors),
            pearson=_pearson(vendor_ivs, our_ivs), spearman=_spearman(vendor_ivs, our_ivs))
    n_ok = len(ok)
    if n_ok >= 2:
        vr = _ranks(vendor_ivs); orr = _ranks(our_ivs)
        vp = [(x - 1) / (n_ok - 1) for x in vr]; op = [(x - 1) / (n_ok - 1) for x in orr]
        diffs = [abs(a - b) for a, b in zip(vp, op)]
        s["percentile_rank_diff_median"] = _percentile(diffs, 0.5)
        s["percentile_rank_diff_p90"] = _percentile(diffs, 0.9)
    return s


def print_summary(label: str, s: dict) -> None:
    print(f"\n=== {label} ===")
    fr = f" failure_rate={s['failure_rate']:.1%}" if s.get("failure_rate") is not None else ""
    print(f"n={s['n']} ok={s['n_ok']} failures={s['n_failures']}{fr}")
    if s["failure_reasons"]:
        print(f"  failure reasons: {s['failure_reasons']}")
    if "mae" in s:
        print(f"  MAE={s['mae']:.4f}  median_AE={s['median_ae']:.4f}  p90_AE={s['p90_ae']:.4f}  "
              f"bias={s['bias']:+.4f}")
        p = s.get("pearson"); sp = s.get("spearman")
        print(f"  Pearson={p:.4f}" if p is not None else "  Pearson=N/A")
        print(f"  Spearman={sp:.4f}" if sp is not None else "  Spearman=N/A")
        if "percentile_rank_diff_median" in s:
            print(f"  percentile_rank_diff: median={s['percentile_rank_diff_median']:.4f} "
                  f"p90={s['percentile_rank_diff_p90']:.4f}")
    else:
        print("  （沒有任何成功反解的觀測）")


# ---------- TLT q ablation ----------

def q_ablation(rows: list[dict], spot_by_symbol: dict) -> None:
    """對同一批已經成功用 production q 反解的觀測，換 q 重新反解一次，
    量化 q 對殘差的貢獻——不展開新模型，只換這一個輸入。"""
    ok = [r for r in rows if not r["failure"] and r["symbol"] == "TLT"]
    if not ok:
        print("\n  （TLT 沒有成功反解的觀測，略過 q ablation）")
        return
    spot = spot_by_symbol.get("TLT")
    print(f"\n  TLT q ablation（n={len(ok)}）  spot={spot}")
    print(f"  {'occ':<22}{'vendor_iv':>10}{'q_prod':>9}{'Δ@q_prod':>10}{'Δ@q=0':>9}"
          f"{'Δ@q-50%':>10}{'Δ@q+50%':>10}")
    maes = {"q_prod": [], "q0": [], "qlo": [], "qhi": []}
    for r in ok:
        q_prod = r["q"]
        for name, qq in (("q_prod", q_prod), ("q0", 0.0), ("qlo", q_prod * 0.5), ("qhi", q_prod * 1.5)):
            iv = implied_vol(r["option_type"], r["mid"], spot, r["strike"], r["T"], r["r"], qq)
            if iv is not None:
                maes[name].append(abs(iv - r["vendor_iv"]))
        d_prod = r["our_iv"] - r["vendor_iv"]
        iv0 = implied_vol(r["option_type"], r["mid"], spot, r["strike"], r["T"], r["r"], 0.0)
        ivlo = implied_vol(r["option_type"], r["mid"], spot, r["strike"], r["T"], r["r"], q_prod * 0.5)
        ivhi = implied_vol(r["option_type"], r["mid"], spot, r["strike"], r["T"], r["r"], q_prod * 1.5)
        f = lambda x: "  n/a" if x is None else f"{x - r['vendor_iv']:+.4f}"
        print(f"  {r['occ']:<22}{r['vendor_iv']:>10.4f}{q_prod:>9.4f}{d_prod:>+10.4f}"
              f"{f(iv0):>9}{f(ivlo):>10}{f(ivhi):>10}")
    print(f"\n  MAE by q variant: " +
         "  ".join(f"{k}={sum(v)/len(v):.4f}(n={len(v)})" for k, v in maes.items() if v))
    if maes["q_prod"] and maes["q0"]:
        drop = sum(maes["q0"]) / len(maes["q0"]) - sum(maes["q_prod"]) / len(maes["q_prod"])
        print(f"  q=0 對照組 MAE 比 production q 高 {drop:+.4f} vol pts"
             f"（{'q 是主要成因' if abs(drop) > 0.02 else 'q 不是主要成因，殘差另有來源'}）")


# ---------- main ----------

def main(argv: list[str]) -> int:
    symbols = tuple(argv) if argv else DEFAULT_SYMBOLS
    token = os.environ.get("MARKETDATA_APP_TOKEN")
    if not token:
        print("MARKETDATA_APP_TOKEN 未設定", file=sys.stderr)
        return 1

    today = date.today()
    all_rows: list[dict] = []
    spot_by_symbol: dict[str, float] = {}

    for symbol in symbols:
        try:
            expirations = fetch_expirations(symbol, token)
        except Exception as e:  # noqa: BLE001
            print(f"[{symbol}] 到期日清單抓取失敗：{e!r}", file=sys.stderr)
            continue
        buckets = pick_diverse_expirations(expirations, today)
        if not buckets:
            print(f"[{symbol}] 沒有找到 medium/LEAPS 到期日", file=sys.stderr)
            continue
        print(f"[{symbol}] 到期日分群：{buckets}", file=sys.stderr)

        try:
            hist, div_note = data_dividends.load_dividend_history(symbol, today)
        except Exception as e:  # noqa: BLE001
            hist, div_note = None, f"失敗：{e!r}"
        print(f"[{symbol}] dividend history: {div_note}  "
              f"(distributions n={len(hist.distributions) if hist else 0})", file=sys.stderr)

        for bucket_name, expiration in buckets.items():
            try:
                payload = fetch_chain_for_expiration(symbol, token, expiration)
            except Exception as e:  # noqa: BLE001
                print(f"[{symbol}/{bucket_name}] chain 抓取失敗：{e!r}", file=sys.stderr)
                continue
            obs_date = snapshot_date(payload)
            if obs_date is None:
                print(f"[{symbol}/{bucket_name}] 沒有 updated 欄位，跳過", file=sys.stderr)
                continue
            curve = fetch_curve_asof(obs_date)
            if curve is None:
                print(f"[{symbol}/{bucket_name}] point-in-time curve 抓取失敗，"
                      f"退回 today 的曲線", file=sys.stderr)
                curve, _ = treasury.load_rate_curve(today)
            rows = process_chain(symbol, payload, curve, hist, bucket_name)
            all_rows.extend(rows)
            spot = next((marketdata._num(r.get("underlyingPrice"))
                        for r in marketdata._rows(payload)
                        if marketdata._num(r.get("underlyingPrice")) is not None), None)
            if spot is not None:
                spot_by_symbol[symbol] = spot

    if not all_rows:
        print("沒有任何觀測", file=sys.stderr)
        return 1

    print(f"\n總觀測數（vendor iv 非 null）：{len(all_rows)}")
    print_summary("整體（修正後：observation_date/r/q 皆對齊快照日）", summarize(all_rows))

    print("\n--- 分群：symbol ---")
    for sym in symbols:
        rs = [r for r in all_rows if r["symbol"] == sym]
        if rs: print_summary(f"symbol={sym}", summarize(rs))

    print("\n--- 分群：tenor bucket ---")
    for bucket in ("medium_short", "medium", "leaps"):
        rs = [r for r in all_rows if r["tenor_bucket"] == bucket]
        if rs: print_summary(f"tenor={bucket}", summarize(rs))

    print("\n--- 分群：symbol x tenor ---")
    for sym in symbols:
        for bucket in ("medium_short", "medium", "leaps"):
            rs = [r for r in all_rows if r["symbol"] == sym and r["tenor_bucket"] == bucket]
            if rs: print_summary(f"{sym}/{bucket}", summarize(rs))

    print("\n" + "=" * 70)
    print("TLT q ABLATION")
    print("=" * 70)
    q_ablation(all_rows, spot_by_symbol)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
