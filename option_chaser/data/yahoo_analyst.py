"""Yahoo Finance 逐券商分析師目標價（LIVE-T1／#397，母票 #389）。

來源：quoteSummary 的 `upgradeDowngradeHistory`（逐券商、逐事件，含
`currentPriceTarget`／`priorPriceTarget`／`epochGradeDate`），同一次呼叫順帶
`financialData` 的共識平均與人數（**只供稽核**，L9：絕不參與標準差）。分割
日曆來自同一個免費來源的 chart events。

存取方式就是 Yahoo 網頁本身的公開流程：先取得 cookie，再向 getcrumb 取一個
crumb，之後的 quoteSummary 請求帶上 crumb。**不使用**任何反機器人繞過、
TLS 指紋偽裝、代理池或付費服務；被擋就照實回報失敗原因（#397 護欄）。

條款：Yahoo 條款禁止自動化擷取與商業使用（研究文件
`docs/research/free-analyst-price-target-sources.md`）。Owner 已決定以個人自用
為優先、保留灰色地帶紀錄採用此來源（#389 LIVE-DATA-DELIVERY-001 決策）。

本模組只有 HTTP＋解析；把結果包成 `ProviderResult` 的是
`api_app.analyst_source.YahooAnalystSource`。
"""
from __future__ import annotations

import http.cookiejar
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Mapping, Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_TIMEOUT_SECONDS = 15.0
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/128.0.0.0 Safari/537.36")

COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
SUMMARY_URL = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
               "?modules=upgradeDowngradeHistory,financialData&crumb={crumb}")
# 週線收盤（已做分割調整）：判斷每筆目標價是用哪個分割基準寫的；15 年涵蓋
# Yahoo 事件史的實際深度（熱門股約 1,000 列上限，最早約 2012 年）。
CHART_URL = ("https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
             "?range=15y&interval=1wk&events=splits")

# 券商改名／併購後沿用同一研究團隊：舊名併到新名，讓同一家只算一位分析師。
# 只收在真實資料裡實際出現兩種寫法、且確認是同一研究團隊的改名；Credit Suisse
# → UBS 這類「被併購後停止出研究」的不合併，讓舊目標價自然過期。大小寫差異
# （Keybanc／KeyBanc）由共識引擎 A3 的 casefold 處理。key 比對前做 casefold
# 與空白壓縮。
FIRM_ALIASES: Mapping[str, str] = {
    "cowen & co.": "TD Cowen",                       # 2023 改名
    "suntrust robinson humphrey": "Truist Securities",  # 2019–2020 合併改名
    "nomura instinet": "Nomura",                     # 同一研究部門的兩種寫法（同日重複出現）
    "pacific crest": "KeyBanc",                      # 併入 KeyBanc Capital Markets
    "exane bnp paribas": "BNP Paribas",              # Exane 併入 BNP Paribas
    "atlantic equities": "Redburn Atlantic",         # 2023 與 Redburn 合併
}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def get(self, url: str) -> HttpResponse: ...


class UrllibTransport:
    """stdlib urllib＋cookie jar。非 2xx 不丟例外，回傳狀態碼讓上層判斷；
    連線層錯誤（逾時、DNS）才丟 `OSError`。"""

    def __init__(self, timeout: float = _TIMEOUT_SECONDS):
        self._timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, url: str) -> HttpResponse:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                return HttpResponse(resp.status,
                                    resp.read().decode("utf-8", errors="replace"),
                                    dict(resp.headers.items()))
        except urllib.error.HTTPError as e:
            return HttpResponse(e.code, e.read().decode("utf-8", errors="replace"),
                                dict(e.headers.items()) if e.headers else {})


class YahooError(Exception):
    """可回報給使用者的失敗（訊息即原因）；`retry_after` 是 429 的秒數提示。"""

    def __init__(self, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class RawTarget:
    """upgradeDowngradeHistory 的一列（已丟掉沒有目標價的純評級列）。"""

    firm: str
    target_price: Decimal
    published_on: date          # 美東日期
    action: str | None
    prior_target: Decimal | None


@dataclass(frozen=True)
class RawSplit:
    effective_on: date
    ratio: Decimal              # numerator / denominator，例 4:1 → 4


@dataclass(frozen=True)
class YahooSymbolData:
    targets: tuple[RawTarget, ...]
    splits: tuple[RawSplit, ...]
    weekly_closes: tuple[tuple[date, float], ...]   # 分割調整後收盤，時間遞增
    consensus_mean: Decimal | None
    analyst_count: int | None
    history_rows: int = 0       # 原始列數（含只有評級、沒有目標價的列；供覆蓋統計）


def _ny_date(epoch: int | float) -> date:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(_NY).date()


def _retry_after(headers: Mapping[str, str]) -> int | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return max(0, int(float(v)))
            except ValueError:
                return None
    return None


def parse_quote_summary(body: str) -> tuple[tuple[RawTarget, ...], Decimal | None, int | None, int]:
    """→ (逐券商目標價, 共識平均, 共識人數, 原始列數)。目標價為 0／缺漏的列（只有評級）丟棄。"""
    try:
        doc = json.loads(body)
        result = (doc.get("quoteSummary") or {}).get("result")
    except (ValueError, AttributeError) as e:
        raise YahooError(f"回應格式無法解析：{e}") from e
    if not result:
        raise YahooError("Yahoo 沒有這個 symbol 的分析師資料")
    entry = result[0]
    history = (entry.get("upgradeDowngradeHistory") or {}).get("history")
    if history is None:
        raise YahooError("回應缺少 upgradeDowngradeHistory（格式可能已改變）")
    targets: list[RawTarget] = []
    for row in history:
        pt = row.get("currentPriceTarget")
        if not pt or not row.get("firm") or not row.get("epochGradeDate"):
            continue
        prior = row.get("priorPriceTarget")
        targets.append(RawTarget(
            firm=str(row["firm"]).strip(), target_price=Decimal(str(pt)),
            published_on=_ny_date(row["epochGradeDate"]),
            action=row.get("priceTargetAction") or row.get("action") or None,
            prior_target=Decimal(str(prior)) if prior else None))
    fin = entry.get("financialData") or {}
    mean = (fin.get("targetMeanPrice") or {}).get("raw")
    count = (fin.get("numberOfAnalystOpinions") or {}).get("raw")
    return (tuple(targets), Decimal(str(mean)) if mean else None,
            int(count) if count else None, len(history))


def parse_chart(body: str) -> tuple[tuple[RawSplit, ...], tuple[tuple[date, float], ...]]:
    """→ (分割事件, 週線收盤)。收盤是 Yahoo 已做分割調整的值。"""
    try:
        result = json.loads(body)["chart"]["result"][0]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise YahooError(f"股價／分割回應格式無法解析：{e}") from e
    splits = sorted(
        (RawSplit(_ny_date(s["date"]),
                  Decimal(str(s["numerator"])) / Decimal(str(s["denominator"])))
         for s in ((result.get("events") or {}).get("splits") or {}).values()
         if s.get("numerator") and s.get("denominator")),
        key=lambda s: s.effective_on)
    stamps = result.get("timestamp") or []
    quote_ = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote_.get("close") or []
    weekly = tuple((_ny_date(t), float(c)) for t, c in zip(stamps, closes)
                   if c is not None and c > 0 and math.isfinite(c))
    return tuple(splits), weekly


class YahooClient:
    """cookie＋crumb 流程；crumb 失效（401）時重取一次。"""

    def __init__(self, transport: Transport | None = None):
        self._t = transport or UrllibTransport()
        self._crumb: str | None = None

    def _get(self, url: str) -> HttpResponse:
        try:
            return self._t.get(url)
        except OSError as e:
            raise YahooError(f"連線失敗或逾時：{e}") from e

    def _refresh_crumb(self) -> str:
        self._get(COOKIE_URL)                  # 只為了取得 cookie；狀態碼不重要
        resp = self._get(CRUMB_URL)
        crumb = resp.body.strip()
        if resp.status == 429:
            raise YahooError("Yahoo 限流（取得 crumb 時 429）",
                             retry_after=_retry_after(resp.headers))
        if resp.status != 200 or not crumb or len(crumb) > 64 or "<" in crumb:
            raise YahooError(f"無法取得 Yahoo crumb（狀態碼 {resp.status}）")
        self._crumb = crumb
        return crumb

    def _summary(self, symbol: str) -> str:
        for attempt in (0, 1):
            crumb = self._crumb or self._refresh_crumb()
            resp = self._get(SUMMARY_URL.format(symbol=quote(symbol), crumb=quote(crumb)))
            if resp.status == 401 and attempt == 0:
                self._crumb = None             # crumb 過期：重取一次
                continue
            if resp.status == 429:
                raise YahooError("Yahoo 限流（429）", retry_after=_retry_after(resp.headers))
            if resp.status == 404:
                raise YahooError("Yahoo 沒有這個 symbol 的分析師資料")
            if resp.status != 200:
                raise YahooError(f"Yahoo 回應狀態碼 {resp.status}")
            return resp.body
        raise YahooError("Yahoo crumb 重取後仍被拒絕（401）")

    def fetch(self, symbol: str) -> YahooSymbolData:
        targets, mean, count, rows = parse_quote_summary(self._summary(symbol))
        chart = self._get(CHART_URL.format(symbol=quote(symbol)))
        if chart.status == 429:
            raise YahooError("Yahoo 限流（股價／分割 429）",
                             retry_after=_retry_after(chart.headers))
        if chart.status != 200:
            raise YahooError(f"股價／分割回應狀態碼 {chart.status}")
        splits, weekly = parse_chart(chart.body)
        return YahooSymbolData(targets, splits, weekly, mean, count, rows)


_MAX_CLOSE_GAP_DAYS = 21


def split_basis_through(target: RawTarget, splits, weekly_closes) -> date | None:
    """這筆目標價已反映到哪一天的分割（→ `AnalystTargetRecord.split_adjusted_through`）。

    實測（AAPL 2020-08-31 4:1）：分割宣布到生效之間，同一天有券商寫分割前的
    數字（美銀 470）、也有券商已改寫成分割後的數字（富國 121.25）。一律「發布日
    早於分割就除以比例」會把後者重複調整（A2）。

    判斷方式：取發布當週的收盤價（Yahoo 收盤已調整過全部分割，乘回發布日之後
    的所有分割比例得到當時的實際股價），依序假設「已反映前 k 次分割」，挑目標價
    與對應股價水準最接近（對數距離最小）的 k。分割比例 ≥ 2 時兩種假設相差至少
    一倍，比券商之間的目標價差異大得多。查不到當週股價時不猜，回 None（視為
    原始值，交給共識引擎照規則處理）。"""
    later = [s for s in splits if s.effective_on > target.published_on]
    if not later:
        return None
    close = _close_on_or_before(weekly_closes, target.published_on)
    if close is None:
        return None
    price = Decimal(str(close))
    for s in later:
        price *= s.ratio                       # 還原成發布當時的實際股價
    best_k, best_dist = 0, None
    level = price
    for k in range(len(later) + 1):
        if k:
            level = level / later[k - 1].ratio
        dist = abs(math.log(float(target.target_price) / float(level)))
        if best_dist is None or dist < best_dist:
            best_k, best_dist = k, dist
    return later[best_k - 1].effective_on if best_k else None


def _close_on_or_before(weekly_closes, day: date) -> float | None:
    best = None
    for d, c in weekly_closes:
        if d > day:
            break
        best = (d, c)
    if best is None or (day - best[0]).days > _MAX_CLOSE_GAP_DAYS:
        return None
    return best[1]
