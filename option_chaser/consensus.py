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
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Context, Decimal, localcontext
from typing import Iterable, Literal, Mapping, Sequence

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
    prior_target: Decimal | None = None          # 不進平均／標準差；只供疑似分割判斷（#399）
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
    # LIVE-T2（#399）：後一筆的 prior_target 等於前一筆原始目標價的相對誤差
    prior_target_tolerance: Decimal = Decimal("0.01")
    # 週線收盤排除疑似分割（`compute_snapshot(weekly_closes=)`）：收盤已調整
    # 所有來源知道的分割，所以「缺分割資訊」的分割仍會在收盤上留下一週的跳動。
    # 兩筆之間任一週 |ln(收盤比)| ≥ split_price_move_share × |ln r| → 不能排除；
    # 收盤相鄰兩點（含兩端）相隔超過 split_price_max_gap_days 天 → 覆蓋不足、不排除。
    split_price_move_share: Decimal = Decimal("0.5")
    split_price_max_gap_days: int = 10
    version: str = "provisional-split-price"

    def __post_init__(self) -> None:
        # 允許呼叫端傳 float／int；內部一律 Decimal
        for name in ("freshness_min_share", "split_ratio_tolerance",
                     "prior_target_tolerance", "split_price_move_share"):
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
        if not Decimal(0) < self.split_price_move_share <= Decimal(1):
            raise ValueError("split_price_move_share 必須介於 0（不含）–1")
        if self.split_price_max_gap_days < 1:
            raise ValueError("split_price_max_gap_days 必須 ≥ 1")


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
class EffectiveTarget:
    """有效集合 S(as_of) 的一筆（LIVE-T2／#399 個股詳細資料用）：原始目標價
    與以 as_of 為基準的分割換算值。`adjusted_price` 就是進平均／標準差的值。"""

    analyst_key: str                 # 正規化＋別名後的 key（去重依據）
    firm: str                        # 來源原始券商名（顯示用）
    target_price: Decimal            # 來源給的原始值
    published_on: date
    adjusted_price: Decimal
    action: str | None = None
    prior_target: Decimal | None = None


@dataclass(frozen=True)
class SeriesPoint:
    """每月歷史序列的一個取樣點（LIVE-T2／#399）：以 tᵢ 為評估日、同一組規則
    算出的當日數值。`qualified` 為真才進 `history`／百分位；不合格時 `reason`
    是 `insufficient_analysts`（n < N_min）或 `split_unresolved`。"""

    on: date
    n_analysts: int
    mean: Decimal | None
    stdev: Decimal | None
    dispersion: Decimal | None
    qualified: bool
    reason: str | None = None


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
    # LIVE-T2（#399）：個股詳細資料。`effective`＝S(as_of)（依 analyst_key
    # 排序）；`series`＝每個取樣日（由舊到新，含不合格點），`history` 是其中
    # qualified 點的 (tᵢ, D)。兩者都是 compute_snapshot 算 history 的同一份
    # 中間結果，不另外推導。
    effective: tuple[EffectiveTarget, ...] = ()
    series: tuple[SeriesPoint, ...] = ()


def _dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def dispersion_percentile(history: Iterable, today) -> Decimal:
    """Midrank 百分位（OPTION-CHASER-SCANNER-PR-REVIEW-001，取代 A1 的嚴格小於）：
    `(#{D < 今天} + 0.5 × #{D = 今天}) / n`，差距 ≤ 1e-9 視為相等。

    為什麼不用嚴格小於：歷史每期都 8%、今天也 8% 時，嚴格小於得 0%，會把
    「跟平常一樣」誤判成「歷史最低 20%」。Midrank 讓同值落在中間（50%）；
    歷史全 0、今天 0 也是 50%，不另設特例放行。"""
    values = [_dec(h) for h in history]
    if not values:
        raise ValueError("dispersion_percentile 需要至少一個歷史點")
    with localcontext(_CTX):
        t = _dec(today)
        lower = sum(1 for v in values if v < t - EPSILON)
        equal = sum(1 for v in values if abs(v - t) <= EPSILON)
        return (Decimal(lower) + Decimal(equal) / 2) / len(values)


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
    """以 t 為基準的分割調整價（§4.1 步驟 2＋A2＋A4）。每次都從來源給的值重算，
    不回寫。只看發布日之後的分割 s（published_on < s.effective_on）：

    - 該套用（s.effective_on ≤ t）但來源尚未反映（> split_adjusted_through）→ ÷ ratio
    - 來源已反映（≤ split_adjusted_through）但 t 還在分割前（> t）→ × ratio 還原
      （PR #396 Codex 審查：否則回推歷史取樣點時，已調整與原始紀錄基準不一）
    - 其餘不動，所以 A2「不重複調整」仍成立。"""
    price = _dec(r.target_price)
    through = r.split_adjusted_through
    for s in splits:
        if s.effective_on <= r.published_on:
            continue
        wanted = s.effective_on <= t
        reflected = through is not None and s.effective_on <= through
        if wanted and not reflected:
            price = price / _dec(s.ratio)
        elif reflected and not wanted:
            price = price * _dec(s.ratio)
    return price


def _effective_set(records: Keyed, t: date,
                   rules: ConsensusRules) -> Keyed:
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
    return [(k, latest[k]) for k in sorted(latest)
            if latest[k].published_on >= oldest_valid]


@dataclass(frozen=True)
class _DayStats:
    n: int
    effective_keyed: tuple[tuple[str, AnalystTargetRecord], ...] = ()
    mean: Decimal | None = None
    stdev: Decimal | None = None
    dispersion: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


def _day_stats(records: Keyed, splits: list[SplitEvent],
               t: date, rules: ConsensusRules) -> _DayStats:
    """§4.2：以 t 為基準的當日數值；n < 2（樣本）或 n == 0 時不算統計量。"""
    effective = tuple(_effective_set(records, t, rules))
    prices = [_adjusted_price(r, splits, t) for _, r in effective]
    n = len(prices)
    min_n = 2 if rules.stdev_kind == "sample" else 1
    if n < min_n:
        return _DayStats(n=n, effective_keyed=effective)
    mean = sum(prices, Decimal(0)) / n
    ss = sum(((p - mean) ** 2 for p in prices), Decimal(0))
    stdev = (ss / (n - 1 if rules.stdev_kind == "sample" else n)).sqrt()
    return _DayStats(n=n, effective_keyed=effective, mean=mean, stdev=stdev,
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


def _near_split_ratio(q: Decimal, rules: ConsensusRules) -> Decimal | None:
    """q（或 1/q）接近哪個常見分割比例；都不接近回 None。"""
    for ratio in rules.split_ratios:
        if any(abs(x - ratio) <= ratio * rules.split_ratio_tolerance for x in (q, 1 / q)):
            return ratio
    return None


def _explained_by_prior(prev: AnalystTargetRecord, nxt: AnalystTargetRecord,
                        splits: list[SplitEvent], t: date,
                        rules: ConsensusRules) -> bool:
    """後一筆自己寫了前值（`prior_target`）→ 前值→後一筆是券商**明確寫的**
    調整，不是缺分割資訊（LIVE-T2／#399：NVDA Bernstein 400→200、prior=400、
    Lowers）。只剩「前一筆→前值」這段可能藏著分割，兩種情況算有交代：

    - 前值等於前一筆的原始目標價（相對誤差 ≤ `prior_target_tolerance`）：
      Yahoo 的前值寫在前一筆當時的基準上（例：AMZN 2022 分割後的 Adjusts
      紀錄 prior=3125＝前一筆原值）。
    - 中間漏記了一次調整（NVDA Raymond James 165 →〔漏 291〕→ 323、prior=291）：
      把前值放到後一筆的基準、以 t 換算後，前一筆→前值不接近任何分割比例。

    `Adjusts`（Yahoo 用來標示「因分割改寫基準」）不算交代——那正是這條
    啟發式規則要抓的情況。prior_target 只作判斷依據，不進任何平均或標準差。"""
    if nxt.prior_target is None or _dec(nxt.prior_target) <= 0:
        return False
    if (nxt.action or "").strip().casefold() == "adjusts":
        return False
    prior = _dec(nxt.prior_target)
    raw_prev = _dec(prev.target_price)
    if abs(prior - raw_prev) <= raw_prev * rules.prior_target_tolerance:
        return True
    factor = _adjusted_price(nxt, splits, t) / _dec(nxt.target_price)
    gap = _adjusted_price(prev, splits, t) / (prior * factor)
    return _near_split_ratio(gap, rules) is None


Closes = Sequence[tuple[date, Decimal]]   # (收盤可得日, 分割調整後收盤)，時間遞增


def _explained_by_prices(prev: AnalystTargetRecord, nxt: AnalystTargetRecord,
                         ratio: Decimal, closes: Closes | None,
                         splits: list[SplitEvent], rules: ConsensusRules) -> bool:
    """週線收盤證明兩筆之間沒有分割 → 這次跳動是真的調整（AMD Piper Sandler
    300→600、INTC Evercore ISI 45→131：兩檔都沒有分割）。

    來源的收盤已調整它知道的每一次分割；我們缺分割資訊、來源收盤卻沒調整的
    那次分割，會在收盤上留下一週約 r 倍的跳動。兩個條件都成立才算排除：

    - 覆蓋：有一個收盤在 prev 發布日當天或之前、有一個在 nxt 發布日當天或
      之後，中間相鄰收盤（含與兩個發布日的距離）都不超過
      `split_price_max_gap_days` 天。
    - 沒有任何一週 |ln(收盤比)| ≥ `split_price_move_share` × |ln r|。
    - 這段收盤期間沒有**已知**分割：收盤早已把已知分割調整掉，看不出「分割
      後仍用舊基準寫」這類錯誤（AVGO Cantor 2024-07-16 2000 → 隔天 200）。

    `closes` 只含評估日 t（含）以前可得的收盤（呼叫端已篩，不用未來資訊）。
    `Adjusts`（Yahoo 標示「因分割改寫基準」）一律不排除，與前值規則一致。"""
    if closes is None or (nxt.action or "").strip().casefold() == "adjusts":
        return False
    start, end = prev.published_on, nxt.published_on
    first = max((i for i, (d, _) in enumerate(closes) if d <= start), default=None)
    last = min((i for i, (d, _) in enumerate(closes) if d >= end), default=None)
    if first is None or last is None:
        return False
    window = closes[first:last + 1]
    if any(window[0][0] <= s.effective_on <= window[-1][0] for s in splits):
        return False
    gap = rules.split_price_max_gap_days
    if (start - window[0][0]).days > gap or (window[-1][0] - end).days > gap:
        return False
    limit = float(rules.split_price_move_share) * abs(math.log(float(ratio)))
    for (d0, c0), (d1, c1) in zip(window, window[1:]):
        if (d1 - d0).days > gap or abs(math.log(float(c1) / float(c0))) >= limit:
            return False
    return True


def _split_suspects(records: Keyed, splits: list[SplitEvent], t: date,
                    rules: ConsensusRules,
                    closes: Closes | None = None) -> list[str]:
    """評估日 t 的疑似分割：同一 analyst_key（同一券商的同一位分析師）前後
    兩筆、**兩筆都落在有效期 V 內**（published_on ∈ [t − V, t]），套用以 t
    為基準的已知分割後，比值仍接近常見分割比例 → 疑似有分割但缺分割資訊。

    只看有效期內的配對：已經過期的舊紀錄不在任何 S(t) 裡，多年前的一次
    目標價腰斬不能讓今天變成 `split_unresolved`。歷史取樣點也用同一條規則、
    以各自的取樣日為 t 判斷（`compute_snapshot()`）。後一筆以自己寫的前值
    交代了這次調整時不算（`_explained_by_prior()`）；週線收盤證明兩筆之間
    沒有分割時也不算（`_explained_by_prices()`，`closes` 為 None＝不使用）。"""
    if closes is not None:
        closes = [(d, c) for d, c in closes if d <= t]     # 只用 t 以前可得的收盤
    oldest_valid = _add_months(t, -rules.validity_months)
    by_key: dict[str, list[AnalystTargetRecord]] = {}
    for key, r in records:
        if oldest_valid <= r.published_on <= t:
            by_key.setdefault(key, []).append(r)
    found = []
    for key in sorted(by_key):
        seq = sorted(by_key[key], key=_recency)
        for prev, nxt in zip(seq, seq[1:]):
            if prev.published_on == nxt.published_on:
                continue
            ratio = _near_split_ratio(
                _adjusted_price(prev, splits, t) / _adjusted_price(nxt, splits, t), rules)
            if (ratio is None or _explained_by_prior(prev, nxt, splits, t, rules)
                    or _explained_by_prices(prev, nxt, ratio, closes, splits, rules)):
                continue
            found.append(
                f"split_unresolved: {nxt.firm or key} 目標價 "
                f"{prev.target_price} → {nxt.target_price}"
                f"（{prev.published_on}→{nxt.published_on}）接近"
                f" {ratio}:1 分割比例，但缺分割資訊")
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
                     computed_at: datetime | None = None,
                     weekly_closes: Iterable[tuple[date, Decimal]] | None = None,
                     ) -> ConsensusSnapshot:
    """§4.1–4.3：一檔股票在評估日 as_of 的 Consensus Snapshot。

    只用 published_on ≤ as_of 的紀錄、effective_on ≤ as_of 的分割（A4）。
    `cross_check` 只原樣帶進 Snapshot，不參與計算（L9）。純函式：不讀時鐘，
    `computed_at` 由呼叫端提供。

    `weekly_closes`：來源的週線收盤 (收盤可得日, 已調整全部已知分割的收盤)。
    提供時，疑似分割的配對若在收盤上看不到對應的一週跳動就不算疑似分割
    （`_explained_by_prices()`）；每個評估日只用當天以前可得的收盤。`None`
    （預設）＝不使用，行為與先前完全相同。
    """
    rules = rules or ConsensusRules()
    records = list(records)
    closes = (None if weekly_closes is None
              else sorted((d, _dec(c)) for d, c in weekly_closes if _dec(c) > 0))
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
        series = []
        for t in sample_dates:
            past = _day_stats(records, splits, t, rules)
            # 取樣日自己的有效期內有無法解釋的疑似分割 → D(t) 不可信，不計入。
            if past.n < rules.n_min or past.dispersion is None:
                reason = "insufficient_analysts"
            elif _split_suspects(records, splits, t, rules, closes):
                reason = "split_unresolved"
            else:
                reason = None
                history.append((t, past.dispersion))
            series.append(SeriesPoint(on=t, n_analysts=past.n, mean=past.mean,
                                      stdev=past.stdev, dispersion=past.dispersion,
                                      qualified=reason is None, reason=reason))
        effective = tuple(
            EffectiveTarget(analyst_key=key, firm=r.firm, target_price=_dec(r.target_price),
                            published_on=r.published_on,
                            adjusted_price=_adjusted_price(r, splits, as_of),
                            action=r.action, prior_target=r.prior_target)
            for key, r in today.effective_keyed)
        percentile = None
        if history and today.dispersion is not None:
            percentile = dispersion_percentile([d for _, d in history],
                                               today.dispersion)
        freshness = None
        if today.n:
            fresh = sum(1 for _, r in today.effective_keyed
                        if (as_of - r.published_on).days <= rules.freshness_days)
            freshness = Decimal(fresh) / today.n
        suspects = _split_suspects(records, splits, as_of, rules, closes)

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

    dates = sorted(r.published_on for _, r in today.effective_keyed)
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
        cross_check=cross_check, computed_at=computed_at,
        effective=effective, series=tuple(series))


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
