"""共識計算核心（純函式，無 I/O、無時鐘、無全域狀態）。

需求來源：#390（OS-01）、規格 #389 §2–§4，並以 #389 留言「規格修正 A1–A4」為準。

數值型別：**一律 `Decimal`**（目標價、平均、標準差、分歧度、百分位、門檻）。
所有運算在固定精度（28 位）的 local context 內進行，結果與呼叫端的全域
Decimal context 無關，同一輸入永遠得到同一輸出。浮點輸入（例如門檻）以
`Decimal(str(x))` 轉換。比較「相等」時容許 `EPSILON = 1e-9`。

比例一律以 0–1 表示（10% = 0.1）。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Context, Decimal, localcontext
from typing import Iterable, Literal, Mapping

EPSILON = Decimal("1e-9")
_CTX = Context(prec=28)


@dataclass(frozen=True)
class AnalystTargetRecord:
    """一筆個別分析師目標價（#389 §2）。`target_price` 是原始（未分割調整）值；
    `None` 代表只有評級沒有目標價，計算時丟棄。"""

    symbol: str
    analyst_key: str
    firm: str
    target_price: Decimal | None
    published_on: date
    source: str = ""
    retrieved_at: datetime | None = None
    action: str | None = None
    prior_target: Decimal | None = None          # 只作稽核，不參與計算
    split_adjusted_through: date | None = None   # A2：來源已反映到哪一天的分割


@dataclass(frozen=True)
class SplitEvent:
    symbol: str
    effective_on: date
    ratio: Decimal                               # 4:1 → 4；反向分割 1:10 → 0.1


@dataclass(frozen=True)
class ConsensusRules:
    """資料品質規則 R（#389 §4）。預設值 = 規格暫定值，待 #385 定案；全部可覆寫。"""

    n_min: int = 5
    validity_months: int = 12                    # V
    freshness_days: int = 90                     # F
    freshness_min_share: Decimal = Decimal("0.5")  # φ
    h_min: int = 24
    stdev_kind: Literal["sample", "population"] = "sample"
    lookback_points: int = 60                    # L：5 年月度點
    aliases: Mapping[str, str] = field(default_factory=dict)
    # 疑似分割偵測：同一 analyst_key 前後兩筆的比值落在常見分割比例 ±tolerance
    split_ratios: tuple[Decimal, ...] = tuple(
        Decimal(r) for r in (2, 3, 4, 5, 8, 10, 15, 20))
    split_ratio_tolerance: Decimal = Decimal("0.03")
    version: str = "provisional-389"

    def __post_init__(self) -> None:
        # 允許呼叫端傳 float／int；內部一律 Decimal
        for name in ("freshness_min_share", "split_ratio_tolerance"):
            object.__setattr__(self, name, _dec(getattr(self, name)))
        object.__setattr__(self, "split_ratios",
                           tuple(_dec(r) for r in self.split_ratios))
        if self.stdev_kind not in ("sample", "population"):
            raise ValueError(f"stdev_kind 必須是 sample 或 population：{self.stdev_kind!r}")
        if self.n_min < (2 if self.stdev_kind == "sample" else 1):
            raise ValueError("n_min 太小：樣本標準差至少要 2 筆")
        if self.h_min < 1 or self.lookback_points < 1:
            raise ValueError("h_min 與 lookback_points 必須 ≥ 1")
        if self.validity_months < 1 or self.freshness_days < 0:
            raise ValueError("validity_months 必須 ≥ 1、freshness_days 必須 ≥ 0")
        if not Decimal(0) <= self.freshness_min_share <= Decimal(1):
            raise ValueError("freshness_min_share 必須介於 0–1")


@dataclass(frozen=True)
class ConsensusCrossCheck:
    """來源公布的共識值。只供稽核，**永遠不參與**任何計算（L9）。"""

    consensus_mean_from_source: Decimal | None = None
    n_from_source: int | None = None


STATUSES = ("ok", "insufficient_analysts", "insufficient_history", "stale",
            "no_data", "source_error", "split_unresolved")
# 多條規則同時不過時，status 取最基本的那一條；reasons 全部列出、同此順序。
# source_error 由 provider 層（#392）產生，本模組不會輸出。
_PRIORITY = ("no_data", "split_unresolved", "insufficient_analysts", "stale",
             "insufficient_history")


@dataclass(frozen=True)
class ConsensusSnapshot:
    """#389 §3。數值欄位在 status != ok 時仍可能有值，但門檻一律不通過。
    reasons 每條以 status 代碼開頭（例如 `"stale: …"`）。"""

    symbol: str
    as_of: date
    status: str
    n_analysts: int
    mean: Decimal | None
    stdev: Decimal | None
    dispersion: Decimal | None
    high: Decimal | None
    low: Decimal | None
    history_points: int
    percentile: Decimal | None
    history: tuple[tuple[date, Decimal], ...]   # 合格取樣點 (tᵢ, D(tᵢ))，供稽核
    reasons: tuple[str, ...]
    freshness_share: Decimal | None = None
    median_published_on: date | None = None
    coverage: str = "unknown"
    source: str = ""
    rules_version: str = ""
    cross_check: ConsensusCrossCheck | None = None
    computed_at: datetime | None = None


def _dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def dispersion_percentile(history: Iterable, today) -> Decimal:
    """A1：歷史中**嚴格小於**今天分歧度的比例（差距 ≤ 1e-9 視為相等）。
    意義：歷史上有多少比例的時間比今天更有共識；今天等於歷史最低值 → 0。"""
    values = [_dec(h) for h in history]
    if not values:
        raise ValueError("dispersion_percentile 需要至少一個歷史點")
    with localcontext(_CTX):
        cut = _dec(today) - EPSILON
        return Decimal(sum(1 for v in values if v < cut)) / len(values)


def _add_months(d: date, months: int) -> date:
    """日曆加減月；月底不存在的日子夾到該月最後一天（3/31 − 1 月 → 2/28）。"""
    idx = d.year * 12 + d.month - 1 + months
    y, m = divmod(idx, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _normalize_key(key: str) -> str:
    return " ".join(key.split()).casefold()


Keyed = list[tuple[str, AnalystTargetRecord]]   # (正規化後 analyst_key, 紀錄)


def _keyed(records: list[AnalystTargetRecord], aliases: Mapping[str, str]) -> Keyed:
    """A3：casefold＋去頭尾空白＋壓縮空白，再套別名表（別名表兩側也正規化）。"""
    table = {_normalize_key(a): _normalize_key(b) for a, b in aliases.items()}
    out = []
    for r in records:
        k = _normalize_key(r.analyst_key)
        out.append((table.get(k, k), r))
    return out


def _recency(r: AnalystTargetRecord) -> tuple:
    """「最新一筆」的全序：(published_on, retrieved_at, target_price) 最大者勝。
    retrieved_at 缺漏視為最早；一律換成 UTC timestamp 以免 naive/aware 混比。"""
    ts = r.retrieved_at.timestamp() if r.retrieved_at is not None else float("-inf")
    return (r.published_on, ts, _dec(r.target_price))


def _adjusted_price(r: AnalystTargetRecord, splits: list[SplitEvent],
                    t: date) -> Decimal:
    """以 t 為基準的分割調整價（§4.1 步驟 2＋A2＋A4）。分割 s 只在
    published_on < s.effective_on ≤ t 且 s.effective_on > split_adjusted_through
    時套用。每次都從原始值重算，不回寫。"""
    price = _dec(r.target_price)
    for s in splits:
        if not r.published_on < s.effective_on <= t:
            continue
        if (r.split_adjusted_through is not None
                and s.effective_on <= r.split_adjusted_through):
            continue
        price = price / _dec(s.ratio)
    return price


def _effective_set(records: Keyed, t: date,
                   rules: ConsensusRules) -> list[AnalystTargetRecord]:
    """S(t)：只看 published_on ≤ t（A4）；每個 analyst_key 取最新一筆；過期剔除。
    回傳依 key 排序，讓加總順序也與輸入順序無關。"""
    latest: dict[str, AnalystTargetRecord] = {}
    for key, r in records:
        if r.published_on > t:
            continue
        cur = latest.get(key)
        if cur is None or _recency(r) > _recency(cur):
            latest[key] = r
    oldest_valid = _add_months(t, -rules.validity_months)
    return [latest[k] for k in sorted(latest)
            if latest[k].published_on >= oldest_valid]


@dataclass(frozen=True)
class _DayStats:
    n: int
    effective: tuple[AnalystTargetRecord, ...] = ()
    mean: Decimal | None = None
    stdev: Decimal | None = None
    dispersion: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


def _day_stats(records: Keyed, splits: list[SplitEvent],
               t: date, rules: ConsensusRules) -> _DayStats:
    """§4.2：以 t 為基準的當日數值；n < 2（樣本）或 n == 0 時不算統計量。"""
    effective = tuple(_effective_set(records, t, rules))
    prices = [_adjusted_price(r, splits, t) for r in effective]
    n = len(prices)
    min_n = 2 if rules.stdev_kind == "sample" else 1
    if n < min_n:
        return _DayStats(n=n, effective=effective)
    mean = sum(prices, Decimal(0)) / n
    ss = sum(((p - mean) ** 2 for p in prices), Decimal(0))
    stdev = (ss / (n - 1 if rules.stdev_kind == "sample" else n)).sqrt()
    return _DayStats(n=n, effective=effective, mean=mean, stdev=stdev,
                     dispersion=stdev / mean, high=max(prices), low=min(prices))


def _last_weekday(year: int, month: int) -> date:
    """月底最後一個平日。不查假日表：取樣點若剛好是假日，D 與前一個交易日
    相同（沒有人在假日發布），不影響 point-in-time 語意。"""
    d = date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() >= 5:
        d = date.fromordinal(d.toordinal() - 1)
    return d


def _sample_dates(as_of: date, count: int) -> list[date]:
    """嚴格早於 as_of 的最近 count 個月底取樣日（A4），由舊到新。"""
    out: list[date] = []
    y, m = as_of.year, as_of.month
    while len(out) < count:
        d = _last_weekday(y, m)
        if d < as_of:
            out.append(d)
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def _split_suspects(records: Keyed, splits: list[SplitEvent],
                    as_of: date, since: date, rules: ConsensusRules) -> list[str]:
    """同一 analyst_key 相鄰兩筆（已套用已知分割）的比值接近常見分割比例
    → 疑似有分割但缺分割資訊。只看後一筆發布於 [since, as_of] 的配對。"""
    by_key: dict[str, list[AnalystTargetRecord]] = {}
    for key, r in records:
        if r.published_on <= as_of:
            by_key.setdefault(key, []).append(r)
    found = []
    for key in sorted(by_key):
        seq = sorted(by_key[key], key=_recency)
        for prev, nxt in zip(seq, seq[1:]):
            if nxt.published_on < since or prev.published_on == nxt.published_on:
                continue
            q = _adjusted_price(prev, splits, as_of) / _adjusted_price(nxt, splits, as_of)
            for ratio in rules.split_ratios:
                if any(abs(x - ratio) <= ratio * rules.split_ratio_tolerance
                       for x in (q, 1 / q)):
                    found.append(
                        f"split_unresolved: {nxt.firm or key} 目標價 "
                        f"{prev.target_price} → {nxt.target_price}"
                        f"（{prev.published_on}→{nxt.published_on}）接近"
                        f" {ratio}:1 分割比例，但缺分割資訊")
                    break
    return found


def _resolve_symbol(records: list[AnalystTargetRecord], splits: list[SplitEvent],
                    symbol: str | None) -> str:
    names = {x.symbol.strip().upper() for x in [*records, *splits]}
    if symbol is not None:
        names.add(symbol.strip().upper())
    if len(names) != 1:
        raise ValueError(f"compute_snapshot 一次只算一檔 symbol：{sorted(names) or '未指定'}")
    return names.pop()


def compute_snapshot(records: Iterable[AnalystTargetRecord],
                     splits: Iterable[SplitEvent],
                     as_of: date,
                     rules: ConsensusRules | None = None,
                     *,
                     symbol: str | None = None,
                     coverage: str = "unknown",
                     source: str = "",
                     cross_check: ConsensusCrossCheck | None = None,
                     computed_at: datetime | None = None) -> ConsensusSnapshot:
    """§4.1–4.3：一檔股票在評估日 as_of 的 Consensus Snapshot。

    只用 published_on ≤ as_of 的紀錄、effective_on ≤ as_of 的分割（A4）。
    `cross_check` 只原樣帶進 Snapshot，不參與計算（L9）。純函式：不讀時鐘，
    `computed_at` 由呼叫端提供。
    """
    rules = rules or ConsensusRules()
    records = list(records)
    splits = sorted(splits, key=lambda s: (s.effective_on, s.ratio))
    sym = _resolve_symbol(records, splits, symbol)
    # 只有評級、沒有目標價的紀錄一律丟棄（§2）
    records = _keyed([r for r in records
                      if r.target_price is not None and r.target_price > 0],
                     rules.aliases)
    sample_dates = _sample_dates(as_of, rules.lookback_points)
    with localcontext(_CTX):
        today = _day_stats(records, splits, as_of, rules)
        history = []
        for t in sample_dates:
            past = _day_stats(records, splits, t, rules)
            if past.n >= rules.n_min and past.dispersion is not None:
                history.append((t, past.dispersion))
        percentile = None
        if history and today.dispersion is not None:
            percentile = dispersion_percentile([d for _, d in history],
                                               today.dispersion)
        freshness = None
        if today.n:
            fresh = sum(1 for r in today.effective
                        if (as_of - r.published_on).days <= rules.freshness_days)
            freshness = Decimal(fresh) / today.n
        since = _add_months(sample_dates[0], -rules.validity_months)
        suspects = _split_suspects(records, splits, as_of, since, rules)

    found: dict[str, list[str]] = {k: [] for k in _PRIORITY}
    if not any(r.published_on <= as_of for _, r in records):
        found["no_data"].append(
            "no_data: 來源僅有共識值，沒有個別目標價" if cross_check is not None
            else "no_data: 沒有個別目標價紀錄")
    else:
        found["split_unresolved"] = suspects
        if today.n < rules.n_min:
            found["insufficient_analysts"].append(
                f"insufficient_analysts: 有效分析師 {today.n} < N_min {rules.n_min}")
        if freshness is not None and freshness < rules.freshness_min_share:
            found["stale"].append(
                f"stale: 近 {rules.freshness_days} 天更新比例 {freshness:.4f}"
                f" < {rules.freshness_min_share}")
    if len(history) < rules.h_min:
        found["insufficient_history"].append(
            f"insufficient_history: 合格歷史點 {len(history)} < H_min {rules.h_min}")
    reasons = tuple(r for k in _PRIORITY for r in found[k])
    status = next((k for k in _PRIORITY if found[k]), "ok")

    dates = sorted(r.published_on for r in today.effective)
    return ConsensusSnapshot(
        symbol=sym, as_of=as_of, status=status,
        n_analysts=today.n, mean=today.mean, stdev=today.stdev,
        dispersion=today.dispersion, high=today.high, low=today.low,
        history_points=len(history), percentile=percentile,
        history=tuple(history), reasons=reasons,
        freshness_share=freshness,
        # 偶數筆取較早的中間值，保證是一個真實的發布日
        median_published_on=dates[(len(dates) - 1) // 2] if dates else None,
        coverage=coverage, source=source, rules_version=rules.version,
        cross_check=cross_check, computed_at=computed_at)


@dataclass(frozen=True)
class GateResult:
    first: bool          # 第一關：自身歷史百分位 ≤ percentile_max
    second: bool         # 第二關：分歧度 ≤ dispersion_max
    selected: bool       # 兩關皆過
    reasons: tuple[str, ...]


def _ratio(name: str, x) -> Decimal:
    v = _dec(x)
    if not Decimal(0) <= v <= Decimal(1):
        raise ValueError(f"{name} 必須是 0–1 的比例：{x!r}")
    return v


def evaluate_gate(snapshot: ConsensusSnapshot, percentile_max,
                  dispersion_max) -> GateResult:
    """§4.4：讀取時套用使用者的兩道門檻（0–1 比例）。兩關各自只看自己的
    門檻；剛好等於（差距 ≤ 1e-9）算通過；status != ok 時兩關都不過。"""
    p_max = _ratio("percentile_max", percentile_max)
    d_max = _ratio("dispersion_max", dispersion_max)
    if snapshot.status != "ok":
        reasons = snapshot.reasons or (f"{snapshot.status}: 資料狀態不是 ok",)
        return GateResult(False, False, False, tuple(reasons))
    reasons = []
    with localcontext(_CTX):
        first = (snapshot.percentile is not None
                 and snapshot.percentile <= p_max + EPSILON)
        second = (snapshot.dispersion is not None
                  and snapshot.dispersion <= d_max + EPSILON)
    if not first:
        reasons.append(f"percentile: {snapshot.percentile} > {p_max}")
    if not second:
        reasons.append(f"dispersion: {snapshot.dispersion} > {d_max}")
    return GateResult(first, second, first and second, tuple(reasons))


TARGET_MONTH_RULES = ("fixed_12m", "median_published_plus_12m")


def target_month(snapshot: ConsensusSnapshot, today: date,
                 rule: str = "fixed_12m") -> str:
    """§5.1：Consensus Scenario 的月級 target_month（`YYYY-MM`）。#381 未決，
    暫定預設 `fixed_12m`。
    - `fixed_12m`：today 所在月 + 12 個月。
    - `median_published_plus_12m`：有效目標價發布日中位數 + 12 個月，但不早於
      today 的下個月（結果一定是尚未過完的月份）。"""
    if rule == "fixed_12m":
        month = _add_months(today.replace(day=1), 12)
    elif rule == "median_published_plus_12m":
        if snapshot.median_published_on is None:
            raise ValueError("Snapshot 沒有 median_published_on，無法套用此規則")
        month = max(_add_months(snapshot.median_published_on.replace(day=1), 12),
                    _add_months(today.replace(day=1), 1))
    else:
        raise ValueError(f"未知的 target_month 規則：{rule!r}（可用 {TARGET_MONTH_RULES}）")
    return f"{month.year:04d}-{month.month:02d}"
