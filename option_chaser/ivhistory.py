"""(tenor, delta) 座標上的 IV 重錨定與相對位置（#126／#114）。

**為什麼要重錨定**：一張固定合約的 IV 序列，意義會隨合約變老而漂移
——今天的 90 天 25-delta，三個月後變成 0 天的深價外，兩者的 IV 不是
同一種東西，畫在同一條線上是誤導。所以歷史序列不是「這張合約過去的
IV」，而是「過去每一天，那天的鏈上與今天這個候選**同樣座標**的那個
IV 是多少」。

**紅線（spec #117 §5）**：這個模組只做 enrichment。本檔案是純函式，
不碰排序、不碰過濾、不碰候選選取——`ranking.py`／`filters.py` 都不
import 它，#118 的選取身份回歸守門因此在結構上就不可能被它影響。

**不外插**：座標落在當日資料的網格之外時回 `None`，呼叫端據此標成
「超出可比網格」。刻意不拿最近的一格頂替——那會讓一個其實沒有可比
基準的數字看起來跟其他日子一樣可信。
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass


@dataclass(frozen=True)
class SurfacePoint:
    """某一天的鏈上，一個合約的座標與 IV。

    `dte` ＝距到期天數（tenor），`delta` 取絕對值（呼叫端負責只餵同一
    種權別進來，call 與 put 的 delta 不可混在同一個網格裡插值）。
    """
    dte: int
    delta: float
    iv: float


def _interp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """兩點線性插值。x0 == x1 時退化成 y0（呼叫端已確保 x 落在兩者之間）。"""
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _iv_at_delta(points: list[SurfacePoint], delta: float) -> float | None:
    """同一個 tenor 上，沿 delta 軸插出目標 delta 的 IV。

    需要**左右都有**資料點才插——只有單邊就是外插，回 `None`。
    """
    if not points:
        return None
    ordered = sorted(points, key=lambda p: p.delta)
    deltas = [p.delta for p in ordered]
    if delta < deltas[0] or delta > deltas[-1]:
        return None
    i = bisect_left(deltas, delta)
    if i < len(deltas) and deltas[i] == delta:
        return ordered[i].iv
    lo, hi = ordered[i - 1], ordered[i]
    return _interp(delta, lo.delta, lo.iv, hi.delta, hi.iv)


def iv_at(points: list[SurfacePoint], *, tenor_days: int,
          delta: float) -> float | None:
    """某一天的鏈上，(tenor, delta) 這個座標的 IV。

    兩軸都要求在網格**之內**（左右各有資料），任一軸落在外面就回
    `None`——這正是「超出可比網格」那個狀態，不外插也不拿最長天期頂替。
    """
    if not points:
        return None
    by_tenor: dict[int, list[SurfacePoint]] = {}
    for p in points:
        by_tenor.setdefault(p.dte, []).append(p)

    tenors = sorted(by_tenor)
    if tenor_days < tenors[0] or tenor_days > tenors[-1]:
        return None

    if tenor_days in by_tenor:
        return _iv_at_delta(by_tenor[tenor_days], delta)

    i = bisect_left(tenors, tenor_days)
    lo_t, hi_t = tenors[i - 1], tenors[i]
    lo_iv = _iv_at_delta(by_tenor[lo_t], delta)
    hi_iv = _iv_at_delta(by_tenor[hi_t], delta)
    # 任一端在 delta 軸上就已經出界時，這個座標沒有完整的四角可插——
    # 用單邊硬湊出一個值等於偷偷外插。
    if lo_iv is None or hi_iv is None:
        return None
    return _interp(tenor_days, lo_t, lo_iv, hi_t, hi_iv)


# ATM 的操作型定義：|delta| ≈ 0.5。用 delta 而不是「履約價最接近現價」
# ——整個模組都活在 (tenor, delta) 座標系裡，換一套座標定義 ATM 會讓
# 分母與分子量的不是同一個東西。
ATM_DELTA = 0.5


def normalized_skew(*, sell_iv: float | None, buy_iv: float | None,
                    atm_iv: float | None) -> float | None:
    """賣腿 IV 減買腿 IV，除以當日 ATM 水準（#114 的頭條數字）。

    除以 ATM 是為了讓不同時期可比：整體波動抬高時，兩腿的絕對價差會
    跟著放大，但那不代表 skew 變陡。任一項缺值或 ATM 為零就回 `None`
    ——湊不出來就說湊不出來。
    """
    if sell_iv is None or buy_iv is None or not atm_iv:
        return None
    return (sell_iv - buy_iv) / atm_iv


def percentile(series: list[float], value: float) -> float | None:
    """`value` 在 `series` 裡的百分位（0–1）。

    用「小於等於的比例」，含等於——這樣一組全同值的序列會回 1.0 而不是
    0.0，而後者會把「跟過去一樣」說成「處於歷史最低」。空序列回 `None`。
    """
    if not series:
        return None
    return sum(1 for x in series if x <= value) / len(series)


@dataclass(frozen=True)
class Coordinate:
    """一條腿在 (tenor, delta) 座標系上的位置。"""
    tenor_days: int
    delta: float


def leg_coordinate(*, option_type: str, strike: float, iv: float | None,
                   spot: float, days_to_expiry: int, rate: float = 0.0,
                   q: float = 0.0) -> Coordinate | None:
    """一條腿現在落在哪個 (tenor, delta) 座標。

    delta 由既有的 `valuation.call_greeks` 算（put 用 call-put parity：
    |Δ_put| = 1 - Δ_call，取絕對值後與 call 的網格同一種量），**不另外
    實作一份 Black-Scholes**——多一份就多一個會跟主路徑漂移的來源。

    缺 IV、天期非正、履約價或現價非正時回 `None`：算不出座標就沒有這
    條腿的歷史序列可言，不硬湊一個。
    """
    if not iv or days_to_expiry <= 0 or strike <= 0 or spot <= 0:
        return None
    from .valuation import DAYS_PER_YEAR, call_greeks

    delta = call_greeks(spot, strike, days_to_expiry / DAYS_PER_YEAR, rate,
                        iv, q).delta
    if option_type == "put":
        delta = 1.0 - delta
    return Coordinate(tenor_days=days_to_expiry, delta=abs(delta))


def trading_days_back(today, window_days: int) -> list[str]:
    """從今天往回數 `window_days` 個曆日，濾掉週末，回 ISO 日期（由舊到新）。

    只濾週末、不處理美股假日：多打幾天假日的代價是那幾天回空（呼叫端
    當斷點處理），比內建一份會過期的假日表可靠。**今天不含**——當日的
    EOD 資料通常還沒結算，拿到的會是半天的東西。
    """
    from datetime import timedelta

    out = []
    for back in range(window_days, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() < 5:
            out.append(day.isoformat())
    return out


def spread_coordinates(candidate: dict, *, spot: float) -> dict | None:
    """候選的兩條腿各自的 (tenor, delta) 座標。

    以 view dict 裡那一份腿資料為準（`iv`／`strike`／`option_type`／
    `expiry`），不重新去快照裡找——同一個候選在同一份 view 裡只能有一組
    座標，兩處各算一次遲早會漂。

    買腿＝先出現的那條（引擎既有慣例，`legs[0]` 是買腿）。任一腿算不出
    座標就整組回 `None`：skew 是兩腿之差，缺一邊就沒有那個數字。

    **利率**：讀候選自己的 `rate_used`（`CandidateView.rate_used`，
    `leg_rate(p, expiry)` 查表結果，與正式估值管線完全同一個數字），
    不是另外取 0——delta 算出來要跟畫面上其他數字（催化價、Greeks）
    站在同一個假設上，兩套利率會讓同一個候選在不同區塊看到不一致的
    delta。**股利殖利率沿用 q=0**：這是 #122 既有紅線——分級用途的
    delta 本就恆用 q=0／vendor IV、不讀校準後的 carry，Historical IV
    座標屬於同一種「分級用途」，維持一致不是遺漏。
    """
    legs = candidate.get("legs") or []
    if len(legs) < 2:
        return None   # 單腳沒有 skew 可言（MVP 範圍限 Spread）
    dte = candidate.get("days_to_expiry")
    if not dte:
        return None
    rate = candidate.get("rate_used") or 0.0

    buy, sell = legs[0], legs[1]
    coords = {}
    for name, leg in (("buy", buy), ("sell", sell)):
        got = leg_coordinate(option_type=leg.get("option_type", "call"),
                             strike=leg.get("strike", 0.0), iv=leg.get("iv"),
                             spot=spot, days_to_expiry=int(dte), rate=rate)
        if got is None:
            return None
        coords[name] = got
    return coords


def nearby_expirations(known_expiries: list, *, today, tenor_days: int,
                       limit: int = 4) -> list:
    """從這個 Scenario 已經分析過的到期日裡，挑出離目標 tenor 最近的幾個。

    **這就是修正「長天期候選歷史 IV 全部無資料」的核心**：vendor 的
    historical chain 端點不帶 `expiration` 篩選時，只回「下一個月選」
    （官方文件明載），對到期日遠在天邊的 LEAPS 候選完全覆蓋不到；反過來
    帶 `expiration=all` 回整條鏈，一天可能上千張合約，免費額度一天就
    燒光。折衷＝**只鎖定離目標 tenor 最近的少數幾個到期日**，這些日期
    全部是**已經分析過的真實合約**（來自 `view["expiry_counts"]`，
    zero 額外 vendor 成本得知，不必另外查 expirations 清單）。

    回傳一個到期日的「梯子」而不是恰好兩個：回溯窗口內每一天要比的
    目標 tenor 都不一樣（`today + tenor_days` 隨 `today` 往回退而跟著
    往前移），恰好兩個到期日只能罩住窗口裡很小一段；`iv_at()` 既有的
    bisect 邏輯本來就會在當天實際抓到的到期日集合裡找相鄰的一對，
    梯子式的候選集讓不同歷史日各自配對到不同的一對，不需要在這裡另外
    寫配對邏輯。窗口較久遠的那一段仍可能沒有涵蓋到——`iv_at()` 誠實回
    `None`，觀測筆數如實反映在畫面上，不是靜默錯誤（沿用既有「缺席即
    斷點」原則，不是本函式該解決的問題）。

    **短天期候選刻意回空**（`_SHORT_TENOR_DAYS`）：vendor 預設（不帶
    `expiration`）本就回下一個月選，對這種候選原本就抓得到——回空讓
    呼叫端照舊用那個免費的預設請求，不必為了已經沒事的候選多打 3 倍
    vendor 請求。只在預設覆蓋不到的長天期才需要這份梯子，這正是需求方
    回報「連線成功但無資料」的那一類候選。
    """
    if tenor_days <= _SHORT_TENOR_DAYS or not known_expiries:
        return []
    from datetime import date as _date
    from datetime import timedelta

    target = today + timedelta(days=tenor_days)
    scored = sorted(
        set(known_expiries),
        key=lambda e: abs((_date.fromisoformat(e) - target).days),
    )
    return scored[:limit]


# 「下一個月選」正常狀況下離今天多遠——粗抓一個月的曆日再加點緩衝，
# 抓太緊會誤判成「預設抓不到」而多打不必要的 vendor 請求，抓太鬆會漏掉
# 真正需要梯子的長天期候選。抓不準沒有安全疑慮，只是多打幾次請求
# ，不影響正確性。
_SHORT_TENOR_DAYS = 45


def reanchor_spread(surface: dict, coords: dict) -> dict:
    """某一天的鏈上，兩腿座標與 ATM 各自的 IV，以及當日的 normalized skew。

    `surface` 是 `{"call": [SurfacePoint], "put": [...]}`。權別取買腿那一
    種——同一組 spread 的兩腿權別相同（MVP 只有 bull call spread），
    call 與 put 的 delta 網格不可混插。
    """
    points = surface.get("call") or []
    tenor = coords["buy"].tenor_days
    buy_iv = iv_at(points, tenor_days=tenor, delta=coords["buy"].delta)
    sell_iv = iv_at(points, tenor_days=tenor, delta=coords["sell"].delta)
    atm = iv_at(points, tenor_days=tenor, delta=ATM_DELTA)
    return {"buy_iv": buy_iv, "sell_iv": sell_iv, "atm_iv": atm,
            "normalized_skew": normalized_skew(sell_iv=sell_iv, buy_iv=buy_iv,
                                               atm_iv=atm)}


def percentiles_of(points: list[dict]) -> dict:
    """序列最後一筆在整段歷史裡的百分位，逐項算。

    出界（`None`）的日子不進母體——把它們當成某個數值會污染分位數；
    整段都出界時該項回 `None`（＝「超出可比網格」，呼叫端據此留白）。
    """
    out: dict[str, float | None] = {}
    for field in ("normalized_skew", "buy_iv", "sell_iv", "atm_iv"):
        series = [p[field] for p in points if p.get(field) is not None]
        latest = next((p[field] for p in reversed(points)
                       if p.get(field) is not None), None)
        out[field] = percentile(series, latest) if latest is not None else None
    return out


# ---------- 抽樣排程與時間加權（#128） ----------
#
# 為什麼不逐日抓：vendor 額度有限。一年 250+ 個 daily snapshot 抓不起，
# 但把窗縮成 30D／90D 又會失去 1Y percentile 的長期脈絡。折衷是
# **近期較密、遠期較疏**——近 90 天每週約 2 點（保住 IV spike／regime
# change 的辨識力），90 天到 1 年每週約 1 點（保住長期脈絡），全年約
# 60–70 點。

_DENSE_DAYS = 90          # 這之內算「近期」
_DENSE_PER_WEEK = 2
_SPARSE_PER_WEEK = 1
_WINDOW_DAYS = 365


def _week_seed(symbol: str, week_index: int) -> int:
    """決定性的偽亂數種子。

    **不能用內建 `hash()`**：str 的雜湊每個 process 都不同
    （PYTHONHASHSEED），排程會每次重啟就變，backfill 於是永遠在追一份
    移動的目標、已抓的日期全部作廢。
    """
    from zlib import crc32

    return crc32(f"{symbol}:{week_index}".encode())


def _pick(weekdays: list, count: int, seed: int) -> list:
    """從一週的交易日裡挑 `count` 天。

    挑哪天由種子決定而非固定星期幾——固定的話整份序列都落在同一個
    星期幾，任何具星期效應的市場結構都會被系統性地放大或抹平。
    兩點時刻意隔開，不讓它們黏在相鄰兩天（那等於只取到一個時點）。
    """
    n = len(weekdays)
    if n == 0:
        return []
    if count <= 1:
        return [weekdays[seed % n]]
    first = seed % n
    if n <= 2:
        return sorted(set(weekdays))
    # 至少隔 2 天，且間距本身也隨種子變化
    gap = 2 + (seed >> 8) % max(n - 2, 1)
    second = (first + gap) % n
    if second == first:
        second = (first + 2) % n
    return [weekdays[i] for i in sorted({first, second})]


def sampling_schedule(symbol: str, today, *, window_days: int = _WINDOW_DAYS,
                      dense_days: int = _DENSE_DAYS) -> list[str]:
    """這個 symbol 的歷史觀測**應該**落在哪些日期（由舊到新的 ISO 字串）。

    決定性：同一個 (symbol, today) 算兩次結果相同——backfill 靠這點才能
    「只補缺的」，否則每次都想抓不同日期、永遠補不完。

    今天不含（當日 EOD 通常還沒結算），週末不含。
    """
    from datetime import timedelta

    out: list[str] = []
    week = 0
    while True:
        # 這一週最新的那天（week 0 ＝昨天往回算七天）
        week_end = today - timedelta(days=1 + week * 7)
        age = (today - week_end).days
        if age > window_days:
            break
        days = [week_end - timedelta(days=i) for i in range(7)]
        weekdays = sorted(d for d in days
                          if d.weekday() < 5 and (today - d).days <= window_days)
        per_week = _DENSE_PER_WEEK if age <= dense_days else _SPARSE_PER_WEEK
        out.extend(d.isoformat() for d in _pick(weekdays, per_week,
                                                _week_seed(symbol, week)))
        week += 1
    return sorted(set(out))


# 單一觀測最多能代表多長的時間。沒有上限的話，一段長空窗會讓緊鄰它的
# 那一個點吃下整段權重——等於默認「這中間都跟它一樣」，那就是插值。
# 取稀疏段標稱間隔（7 天）的兩倍。
_MAX_REPRESENTED_DAYS = 14.0


def interval_weights(dates: list[str]) -> list[float]:
    """每個觀測代表多長的時間（天）。

    用 Voronoi 切法：每個點擁有「與前後鄰居的中點」之間那段。抽樣密度
    不均勻時，這讓近期高密度的點各自只代表很短的時間、遠期稀疏的點各自
    代表較長的時間，總和才與真實時間軸成比例——天真等權會讓最近數月被
    過度加權。

    每個點的代表區間有上限（`_MAX_REPRESENTED_DAYS`）：長空窗不該由旁邊
    那一個點代言。被截掉的部分就是「沒有資料的時間」，不補、不插值。

    回傳順序 ＝ **日期由舊到新**（與輸入順序無關）。呼叫端若要把權重配
    回自己的資料，必須先照日期排序再 zip——否則整組權重會錯位。
    """
    from datetime import date as _date

    if not dates:
        return []
    days = [_date.fromisoformat(d).toordinal() for d in sorted(dates)]
    if len(days) == 1:
        return [min(_MAX_REPRESENTED_DAYS, 1.0)]

    out = []
    for i, day in enumerate(days):
        left = (day - days[i - 1]) / 2 if i > 0 else (days[1] - day) / 2
        right = (days[i + 1] - day) / 2 if i < len(days) - 1 \
            else (day - days[-2]) / 2
        out.append(min(left + right, _MAX_REPRESENTED_DAYS))
    return out


def weighted_percentile(observations: list[tuple[str, float | None]],
                        value: float | None) -> float | None:
    """`value` 在這串觀測裡的時間加權百分位（0–1）。

    `observations` 是 (日期, 值) 對；**值為 `None` 的整筆剔除**——那一天
    沒有可比的資料，既不入母體、也不用鄰居的值補上去。剔除後才重算權重，
    所以缺漏表現為「那段時間沒人代表」（受上限保護），不是被偽造成有值。

    與 `percentile()` 一樣採「小於等於的比例」含等於：全同值序列因此回
    1.0 而不是 0.0，後者會把「跟過去一樣」說成「處於歷史最低」。
    """
    if value is None:
        return None
    # 先照日期排序：`interval_weights` 一律回「由舊到新」的順序，拿呼叫端
    # 的原始順序去 zip 會整組錯位（新舊顛倒時權重剛好前後對調）。
    known = sorted(((d, v) for d, v in observations if v is not None),
                   key=lambda pair: pair[0])
    if not known:
        return None
    dates = [d for d, _ in known]
    by_date = dict(zip(dates, interval_weights(dates)))
    weights = list(by_date.values())
    total = sum(weights)
    if total <= 0:
        return None
    hit = sum(by_date[d] for d, v in known if v <= value)
    return hit / total


# ---------- 趨勢統計量（#138／spec #137）----------
#
# Δ4w 回答「往哪走」，percentile 只回答「在哪裡」——兩者互補，不是誰
# 取代誰。基準取窗內**中位數**而不是單一最近點：percentile 站在全年
# 六十幾個點上，一筆爛報價幾乎推不動它，但趨勢若取單點基準，那天一筆
# 爛報價就能憑空捏造整個趨勢數字（spec #137 Gate 2 決策）。4 週這個
# 窗口落在 IV level 因子 half-life 的證據帶（3–7 週，見
# docs/research/rich-cheap-trend-entry-timing.md §4.1）內約一個
# half-life，窗寬 21 天讓密集抽樣段（近 90 天每週約 2 點）內典型有
# 約 6 筆觀測撐著中位數。

_TREND_WINDOW_START_DAYS = 42   # 回溯窗遠端
_TREND_WINDOW_END_DAYS = 21     # 回溯窗近端——窗寬涵蓋約 28 天前一帶


def trend_4w(observations: list[tuple[str, float | None]], *,
             latest: float | None, today) -> tuple[float | None, int]:
    """Δ4w＝`latest`（與 `field_metrics` 的 `value` 同一筆，不另做平滑）
    減去 `[today−42d, today−21d]` 窗內所有非 `None` 觀測的**中位數**。

    `latest` 由呼叫端傳入而不是這裡自己從 `observations` 推——這樣兩者
    保證是同一個數字，不會因為兩處各自判斷「最新」而漂移。

    窗內一筆有效觀測都沒有，或根本沒有 `latest` 可減 → `(None, 0)`：
    不外推、不拿窗外較近的點頂替（沿用 `iv_at()` 的不外插哲學）。

    回傳 `(Δ4w, 基準中位數背後的觀測筆數)`——後者是透明度欄位，讓使用者
    或除錯者知道這個趨勢數字站在多少筆觀測上（與 `count` 同精神）。
    """
    from datetime import timedelta
    from statistics import median

    if latest is None:
        return None, 0

    window_start = (today - timedelta(days=_TREND_WINDOW_START_DAYS)).isoformat()
    window_end = (today - timedelta(days=_TREND_WINDOW_END_DAYS)).isoformat()
    base_values = [v for d, v in observations
                   if v is not None and window_start <= d <= window_end]
    if not base_values:
        return None, 0
    return latest - median(base_values), len(base_values)


def field_metrics(points: list[dict], *, today) -> dict:
    """每個欄位的（現值、百分位、有效觀測筆數、Δ4w、Δ4w 基準筆數）
    ——呈現的最小單位（#133／#138）。

    **不設任何 coverage／樣本數門檻**：只要這個欄位至少有一筆有效觀測，
    就算出百分位並給。`count` 是這個百分位背後有幾筆觀測撐著，讓使用者
    自己判斷這個數字站不站得住腳——這是刻意的取捨：產品只呈現事實與
    資料量，不替使用者下「樣本不足所以不值得看」之類的可信度判斷。同一
    精神延伸到 `trend_4w`：只要基準窗內有至少一筆觀測就給，`count` 換成
    `trend_base_count` 揭露那個數字背後有幾筆撐著。

    唯一容許 `percentile` 為 `None` 的情況是 `count == 0`——這個欄位
    完全沒有可比較的歷史觀測（不是「不夠可信」，是真的沒有可比的東西）。
    這個情況下 `value` 也是 `None`：沒有觀測就沒有「最近一次的值」可言，
    `trend_4w` 同理跟著是 `None`。
    """
    out: dict[str, dict] = {}
    for field in ("normalized_skew", "buy_iv", "sell_iv", "atm_iv"):
        obs = [(p["date"], p.get(field)) for p in points]
        valid = [v for _, v in obs if v is not None]
        latest = valid[-1] if valid else None
        delta_4w, trend_base_count = trend_4w(obs, latest=latest, today=today)
        out[field] = {
            "value": latest,
            "percentile": weighted_percentile(obs, latest)
                         if latest is not None else None,
            "count": len(valid),
            "trend_4w": delta_4w,
            "trend_base_count": trend_base_count,
        }
    return out
