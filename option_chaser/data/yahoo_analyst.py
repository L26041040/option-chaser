"""Yahoo Finance 逐券商分析師目標價（LIVE-T1／#397，母票 #389）。

來源：quoteSummary 的 `upgradeDowngradeHistory`（逐券商、逐事件，含
`currentPriceTarget`／`priorPriceTarget`／`epochGradeDate`），同一次呼叫順帶
`financialData` 的共識平均與人數（**只供稽核**，L9：絕不參與標準差）。分割
日曆與週線收盤來自同一個免費來源的 chart 端點。

存取方式就是 Yahoo 網頁本身的公開流程：先取得 cookie，再向 getcrumb 取一個
crumb，之後的 quoteSummary 請求帶上 crumb。User-Agent 與 repo 既有的 Yahoo
股利抓取（`dividends.py`）相同，是一般瀏覽器字串。**不使用**反機器人繞過、
TLS 指紋偽裝、代理池或付費服務；被擋就照實回報失敗原因（#397 護欄）。

條款：Yahoo 條款禁止自動化擷取與商業使用（研究文件
`docs/research/free-analyst-price-target-sources.md`）。Owner 已決定以個人自用
為優先、保留灰色地帶紀錄採用此來源（#389 LIVE-DATA-DELIVERY-001 決策）。

本模組只有 HTTP＋解析；把結果包成 `ProviderResult` 的是
`api_app.analyst_source.YahooAnalystSource`。對外失敗一律是 `YahooError`
（`FetchError` 子類，訊息是寫給人看的、不含底層例外原文，#345 B-3）。
"""
from __future__ import annotations

import http.client
import http.cookiejar
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping, Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ..models import FetchError, describe_fetch_exception
from .dividends import _TIMEOUT_SECONDS, _USER_AGENT

_NY = ZoneInfo("America/New_York")

COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
SUMMARY_URL = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
               "?modules=upgradeDowngradeHistory,financialData")
# 週線收盤（已做分割調整）：判斷每筆目標價是用哪個分割基準寫的；15 年涵蓋
# Yahoo 事件史的實際深度（熱門股約 1,000 列上限，最早約 2012 年）。
CHART_URL = ("https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
             "?range=15y&interval=1wk&events=splits")

# 券商改名／併購後沿用同一研究團隊：舊名 → 新名。交給共識引擎既有的
# `ConsensusRules.aliases`（#389 A3：先正規化再套別名表參數），部署環境由
# `api/index.py` 帶入。只收在真實資料裡實際出現兩種寫法、且確認是同一研究
# 團隊的改名；Credit Suisse → UBS 這類「被併購後停止出研究」的不合併，讓舊目標
# 價自然過期。大小寫差異（Keybanc／KeyBanc）由引擎 A3 的 casefold 處理。
FIRM_ALIASES: Mapping[str, str] = {
    "Cowen & Co.": "TD Cowen",                       # 2023 改名
    "SunTrust Robinson Humphrey": "Truist Securities",  # 2019–2020 合併改名
    "Nomura Instinet": "Nomura",                     # 同一研究部門的兩種寫法（同日重複出現）
    "Pacific Crest": "KeyBanc",                      # 併入 KeyBanc Capital Markets
    "Exane BNP Paribas": "BNP Paribas",              # Exane 併入 BNP Paribas
    "Atlantic Equities": "Redburn Atlantic",         # 2023 與 Redburn 合併
}

# 兩個分割基準至少差一倍才判斷；3:2 這類小比例分割，券商之間的目標價差異
# 就可能大過基準差，硬判會出錯 → 不判，視為原始值交給引擎（A2 規則）。
_MIN_DISTINGUISHABLE_LOG_RATIO = math.log(2)
_MAX_CLOSE_GAP_DAYS = 21


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def get(self, url: str) -> HttpResponse: ...


class UrllibTransport:
    """stdlib urllib＋cookie jar。非 2xx 不丟例外，回傳狀態碼讓上層判斷；
    連線層錯誤（逾時、DNS、連線中斷）照常丟出，由 `YahooClient` 收斂。"""

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


class YahooError(FetchError):
    """可回報給使用者的失敗（訊息即原因）；`rate_limited` 為真代表上游回 429，
    `retry_after` 是它給的秒數提示（沒給＝`None`）。"""

    def __init__(self, message: str, *, retry_after: int | None = None,
                 rate_limited: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.rate_limited = rate_limited


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
    ratio: Decimal              # numerator / denominator，例 4:1 → 4、1:10 → 0.1


@dataclass(frozen=True)
class QuoteSummary:
    targets: tuple[RawTarget, ...]
    consensus_mean: Decimal | None
    analyst_count: int | None
    history_rows: int           # 原始列數（含只有評級、沒有目標價的列；供覆蓋統計）


@dataclass(frozen=True)
class YahooSymbolData:
    summary: QuoteSummary
    splits: tuple[RawSplit, ...]
    weekly_closes: tuple[tuple[date, Decimal], ...]   # 分割調整後收盤，時間遞增


def _ny_date(epoch) -> date:
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).astimezone(_NY).date()


def _positive_decimal(value) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d > 0 else None


def _retry_after(headers: Mapping[str, str]) -> int | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return max(0, int(float(v)))
            except (ValueError, OverflowError):
                return None
    return None


def _parse_row(row) -> RawTarget | None:
    """一列 → RawTarget；只有評級、或欄位壞掉的列回 None（跳過，不讓整檔失敗）。"""
    if not isinstance(row, dict):
        return None
    pt = _positive_decimal(row.get("currentPriceTarget"))
    firm = str(row.get("firm") or "").strip()
    if pt is None or not firm:
        return None
    try:
        published_on = _ny_date(row["epochGradeDate"])
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None
    return RawTarget(firm=firm, target_price=pt, published_on=published_on,
                     action=row.get("priceTargetAction") or row.get("action") or None,
                     prior_target=_positive_decimal(row.get("priorPriceTarget")))


def parse_quote_summary(body: str) -> QuoteSummary:
    """quoteSummary 回應 → `QuoteSummary`。整體結構不對時丟 `YahooError`；
    個別壞掉的列跳過。"""
    try:
        doc = json.loads(body)
        result = (doc.get("quoteSummary") or {}).get("result")
    except (ValueError, AttributeError) as e:
        raise YahooError("回應格式無法解析（不是預期的 JSON）") from e
    if not result or not isinstance(result[0], dict):
        raise YahooError(_NOT_FOUND_ANALYST)
    entry = result[0]
    history = (entry.get("upgradeDowngradeHistory") or {}).get("history")
    if not isinstance(history, list):
        raise YahooError("回應缺少 upgradeDowngradeHistory（格式可能已改變）")
    targets = tuple(t for t in map(_parse_row, history) if t is not None)
    fin = entry.get("financialData") or {}
    mean = _positive_decimal((fin.get("targetMeanPrice") or {}).get("raw"))
    count = _positive_decimal((fin.get("numberOfAnalystOpinions") or {}).get("raw"))
    return QuoteSummary(targets, mean, int(count) if count else None, len(history))


def parse_chart(body: str) -> tuple[tuple[RawSplit, ...], tuple[tuple[date, Decimal], ...]]:
    """chart 回應 → (分割事件, 週線收盤)。收盤是 Yahoo 已做分割調整的值；
    個別壞掉的分割或收盤點跳過。"""
    try:
        result = json.loads(body)["chart"]["result"][0]
        raw_splits = ((result.get("events") or {}).get("splits") or {}).values()
        stamps = result.get("timestamp") or []
        closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        raise YahooError("股價／分割回應格式無法解析") from e
    splits = []
    for s in raw_splits:
        num = _positive_decimal(s.get("numerator")) if isinstance(s, dict) else None
        den = _positive_decimal(s.get("denominator")) if isinstance(s, dict) else None
        try:
            when = _ny_date(s["date"]) if num and den else None
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            when = None
        if when is not None:
            splits.append(RawSplit(when, num / den))
    weekly = []
    for t, c in zip(stamps, closes):
        price = _positive_decimal(c)
        try:
            when = _ny_date(t) if price is not None else None
        except (TypeError, ValueError, OverflowError, OSError):
            when = None
        if when is not None:
            weekly.append((when, price))
    return (tuple(sorted(splits, key=lambda s: s.effective_on)),
            tuple(sorted(weekly)))


def split_basis_through(target: RawTarget, splits, weekly_closes) -> date | None:
    """這筆目標價已反映到哪一天的分割（→ `AnalystTargetRecord.split_adjusted_through`）。

    實測（AAPL 2020-08-31 4:1）：分割宣布到生效之間，同一天有券商寫分割前的
    數字（美銀 470）、也有券商已改寫成分割後的數字（富國 121.25）；Yahoo 也回溯
    換算過部分更早的紀錄。一律「發布日早於分割就除以比例」會重複調整（A2）。

    判斷方式：取發布當週的收盤價（Yahoo 收盤已調整過全部分割，乘回發布日之後
    的所有分割比例得到當時的實際股價），依序假設「已反映前 k 次分割」，挑目標價
    與對應股價水準最接近（對數距離最小）的 k。只跨過比例相差至少一倍的分割
    （含反向合股）；遇到 3:2 這類分不清的分割就停在它之前。查不到當週股價時
    不猜，回 None（視為原始值，交給共識引擎照規則處理）。"""
    later = [s for s in splits if s.effective_on > target.published_on]
    if not later:
        return None
    close = _close_on_or_before(weekly_closes, target.published_on)
    if close is None:
        return None
    level = close
    for s in later:
        level *= s.ratio                       # 還原成發布當時的實際股價
    best_k, best_dist = 0, abs(math.log(target.target_price / level))
    for k, s in enumerate(later, start=1):
        if abs(math.log(s.ratio)) < _MIN_DISTINGUISHABLE_LOG_RATIO:
            break
        level = level / s.ratio
        dist = abs(math.log(target.target_price / level))
        if dist < best_dist:
            best_k, best_dist = k, dist
    return later[best_k - 1].effective_on if best_k else None


_WEEK_CLOSE_OFFSET_DAYS = 4      # 週一標記的週線，收盤是當週最後一個交易日（≤ 週五）


def closes_by_close_date(weekly_closes, *, available_on: date | None = None
                         ) -> tuple[tuple[date, Decimal], ...]:
    """週線收盤改標成「收盤可得日」，給共識引擎的 `weekly_closes` 用（不用未來資訊）。

    Yahoo 的週線以**當週週一**標記，收盤卻是當週最後一個交易日的價格；照原
    標記篩「t 以前」會偷看到 t 之後最多 4 天的收盤。改成標記日 + 4 天（週五），
    但不晚於下一根的標記日。最後一根的收盤是**抓取當下的最新價**（週中抓取時
    它仍標週一；週末抓取時 Yahoo 多補一根週五標記的收盤），所以它的可得日不早
    於抓取日 `available_on`（美東）——取原標記與抓取日較晚者，保守。
    `available_on` 為 None 時最後一根照原標記（只供沒有抓取日的離線檢查）。"""
    out = []
    for i, (d, c) in enumerate(weekly_closes):
        if i + 1 < len(weekly_closes):
            nxt = weekly_closes[i + 1][0]
            d = min(date.fromordinal(d.toordinal() + _WEEK_CLOSE_OFFSET_DAYS), nxt)
        elif available_on is not None:
            d = max(d, available_on)
        out.append((d, c))
    return tuple(out)


def _close_on_or_before(weekly_closes, day: date) -> Decimal | None:
    best = None
    for d, c in weekly_closes:
        if d > day:
            break
        best = (d, c)
    if best is None or (day - best[0]).days > _MAX_CLOSE_GAP_DAYS:
        return None
    return best[1]


_NOT_FOUND_ANALYST = "Yahoo 沒有這個 symbol 的分析師資料"


def _raise_for_status(resp: HttpResponse, what: str, *,
                      not_found: str = _NOT_FOUND_ANALYST) -> None:
    if resp.status == 429:
        raise YahooError(f"Yahoo 限流（{what} 429）", retry_after=_retry_after(resp.headers),
                         rate_limited=True)
    if resp.status == 404:
        raise YahooError(not_found)
    if resp.status != 200:
        raise YahooError(f"{what}回應狀態碼 {resp.status}")


class YahooClient:
    """cookie＋crumb 流程；crumb 失效（401）時重取一次。"""

    def __init__(self, transport: Transport | None = None):
        self._t = transport or UrllibTransport()
        self._crumb: str | None = None

    def _get(self, url: str) -> HttpResponse:
        try:
            return self._t.get(url)
        except (OSError, http.client.HTTPException) as e:
            # 不放例外原文：可能帶內部主機名稱（#345 B-3）
            raise YahooError(f"連線失敗或逾時（{describe_fetch_exception(e)}）") from e

    def _refresh_crumb(self) -> str:
        self._get(COOKIE_URL)                  # 只為了取得 cookie；狀態碼不重要
        resp = self._get(CRUMB_URL)
        if resp.status == 429:
            raise YahooError("Yahoo 限流（取得 crumb 時 429）",
                             retry_after=_retry_after(resp.headers),
                             rate_limited=True)
        crumb = resp.body.strip()
        if resp.status != 200 or not crumb or len(crumb) > 64 or "<" in crumb:
            raise YahooError(f"無法取得 Yahoo crumb（狀態碼 {resp.status}）")
        self._crumb = crumb
        return crumb

    def get_with_crumb(self, url: str, what: str, *,
                       not_found: str = _NOT_FOUND_ANALYST) -> str:
        """帶 crumb 的 GET；crumb 過期（401）時重取一次。非 200 一律收斂成
        `YahooError`。選擇權鏈 adapter（`yahoo_options`）與本模組共用這一段。"""
        sep = "&" if "?" in url else "?"
        for attempt in (0, 1):
            crumb = self._crumb or self._refresh_crumb()
            resp = self._get(url + sep + "crumb=" + quote(crumb))
            if resp.status == 401 and attempt == 0:
                self._crumb = None             # crumb 過期：重取一次
                continue
            _raise_for_status(resp, what, not_found=not_found)
            return resp.body
        raise YahooError("Yahoo crumb 重取後仍被拒絕（401）")

    def fetch(self, symbol: str) -> YahooSymbolData:
        summary = parse_quote_summary(self.get_with_crumb(
            SUMMARY_URL.format(symbol=quote(symbol)), "分析師資料"))
        chart = self._get(CHART_URL.format(symbol=quote(symbol)))
        _raise_for_status(chart, "股價／分割")
        splits, weekly = parse_chart(chart.body)
        return YahooSymbolData(summary, splits, weekly)
