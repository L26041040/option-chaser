"""股利／配息殖利率 q 的純函式模組（無 I/O、無全域狀態、無 wall-clock）。

需求來源：#123（spec #117 §2）＋研究文件
`docs/research/dividend-yield-source-selection.md` §7/§9/§13，以及
#120 的 production 實測確認（同文件 §12.4）。

q = 過去 365 天經常性現金分配總額 / 本次快照 spot——連續複利定義下的
一階近似（研究 §7.3 讀法第 2 點：`D/S` 與 `ln(1+D/S)` 在真實資料上差在
噪音內，取最簡單的 `D/S`）。**不建配息時間表、公式裡不出現配息次數**
（研究 §7.6：相位只值 0.007pp，但次數數錯值 0.16pp）。

抓取（HTTP）隔在 `option_chaser.data.dividends`；本模組只認資料結構，
單元測試以固定 fixture 離線重跑。
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .models import ParamError

TTM_WINDOW_DAYS = 365


class DividendParseError(Exception):
    """配息回應文字（JSON）解析失敗——端點改版或回傳非預期形狀時的明確
    訊號，比照 `ratecurve.CurveParseError` 同一種角色：純模組自己的例外
    型別，不依賴 I/O 層的 `FetchError`。抓取層（`data/dividends.py`）
    捕捉任意例外收斂成單一 `FetchError`，不需要認得這個型別本身。"""

# 異常單期分配的判斷門檻——研究文件 §8 明文「門檻屬實作票範圍，未經
# 驗證」，這是本票的實作判斷：單期金額超過同標的近 12 期中位數的 3 倍時
# 視為異常，以中位數取代該筆金額，避免單一特別股利主導 q（研究 §8
# 「異常分配的處理」段落；研究文件的實測示例是加一筆 $1.00 特別分配讓
# q 從 4.608% 跳到 5.153%，3 倍門檻足以攔住那種量級的離群值,同時不誤傷
# 正常配息本身的月間波動，例如研究 §12.2 提到的真實月配息 $0.301–$0.345
# 這種量級的正常波動遠小於 3 倍）。


@dataclass(frozen=True)
class DividendRecord:
    ex_date: str      # YYYY-MM-DD
    amount: float


@dataclass(frozen=True)
class DividendHistory:
    """管線持久化單位：金額清單 + as_of，不是算好的 q。

    研究 §7.5／§9 第 5 點：q 是比例，分母（spot）會隨行情變動，快取
    「算好的 q」會把一個過期的價格基準凍結進去；金額本身是歷史事實，
    幾乎不變，才是該快取的東西。

    `source`：實際取得這份資料的 vendor（"yahoo"／"fmp"／"nasdaq"），
    比照 `ChainSnapshot.source` 的既有誠實紀錄慣例。

    `stale`：與 `ratecurve.RateCurve.stale`（RC1／#87）同一個語意——
    這份是不是「今天抓取失敗、沿用陳舊備援窗（本地檔案或 Neon 持久
    快取）的舊資料」，不是它自己抓到那天算起的新鮮度。預設 `False`。
    """
    symbol: str
    as_of: str                                   # 資料截至日 YYYY-MM-DD
    source: str
    distributions: tuple[DividendRecord, ...]     # 只含經常性現金分配
    stale: bool = False


# ---------- 逐 vendor 回應文字解析（#120 §12.4 實測確認的形狀） ----------
#
# 純文字→資料結構，零 I/O——跟 `ratecurve.parse_treasury_csv`／
# `parse_treasury_xml` 同一種角色，比照放在純模組而非抓取層
# （`data/dividends.py` 只認「打哪個 URL、什麼時候該試下一棒」）。
# `today` 是必要參數：跟利率曲線不同，配息回應本身不帶「資料截至日」
# 這個概念（Yahoo/FMP/Nasdaq 的配息明細只有逐筆 ex-date，沒有一個
# 代表整份回應時效的欄位），`as_of` 只能是「我們現在抓的這一刻」。

def parse_yahoo_dividends(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise DividendParseError(f"Yahoo 回應非 JSON：{e}") from e
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        raise DividendParseError("Yahoo 回應無 chart.result")
    events = results[0].get("events") or {}
    divs = events.get("dividends") or {}
    try:
        records = tuple(
            DividendRecord(
                ex_date=datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat(),
                amount=float(d["amount"]))
            for ts, d in divs.items())
    except (KeyError, TypeError, ValueError) as e:
        raise DividendParseError(f"Yahoo events.dividends 形狀異常：{e}") from e
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="yahoo",
                           distributions=records)


def parse_fmp_dividends(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise DividendParseError(f"FMP 回應非 JSON：{e}") from e
    if not isinstance(data, list):
        raise DividendParseError(f"FMP 回應非預期的陣列形狀：{type(data).__name__}")
    records = []
    for row in data:
        try:
            records.append(DividendRecord(ex_date=row["date"], amount=float(row["dividend"])))
        except (KeyError, TypeError, ValueError):
            continue   # 單筆形狀不對不炸整份——盡量取得能取得的
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="fmp",
                           distributions=tuple(records))


def parse_nasdaq_dividends(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise DividendParseError(f"Nasdaq 回應非 JSON：{e}") from e
    rows = (((data.get("data") or {}).get("dividends") or {}).get("rows")) or []
    records = []
    for row in rows:
        raw_date, raw_amount = row.get("exOrEffDate"), row.get("amount")
        if not raw_date or not raw_amount:
            continue
        try:
            ex_date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
            amount = float(str(raw_amount).replace("$", "").strip())
        except (ValueError, TypeError):
            continue
        records.append(DividendRecord(ex_date=ex_date, amount=amount))
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="nasdaq",
                           distributions=tuple(records))


def _dampen_outliers(amounts: tuple[float, ...]) -> tuple[float, ...]:
    """單期金額 > 中位數 3 倍時，以中位數取代——避免一次性特別分配
    主導 q（研究 §8）。"""
    if len(amounts) < 2:
        return amounts
    med = statistics.median(amounts)
    if med <= 0:
        return amounts
    threshold = med * 3.0
    return tuple(med if a > threshold else a for a in amounts)


def compute_q(history: DividendHistory, spot: float, today: date) -> float:
    """TTM（過去 365 天）經常性現金分配總額 / spot。

    `distributions` 為空（fetch 成功但確定無配息，或窗內無配息）→
    q = 0.0——這是**正確答案**，不是降級（研究 §8 第 2 層）。
    """
    if spot <= 0:
        raise ParamError(f"spot 必須為正數：{spot}")
    cutoff = today - timedelta(days=TTM_WINDOW_DAYS)
    amounts = tuple(r.amount for r in history.distributions
                    if date.fromisoformat(r.ex_date) > cutoff)
    if not amounts:
        return 0.0
    return sum(_dampen_outliers(amounts)) / spot


def compute_q_asof(history: DividendHistory, spot: float,
                   observation_date: date) -> float:
    """point-in-time 版本（issue #161）：只計「以 `observation_date` 這天
    來看，市場已經知道」的分配——ex-date 落在
    `(observation_date − 365 天, observation_date]` 才計入。

    跟 `compute_q()`（即時分析用，只有下界）的唯一差異是多一個上界：
    `ex_date <= observation_date`。一筆分配的 ex-date 若晚於觀察日，
    代表那天它還沒除息，不可能影響那天的選擇權價格——算進去就是
    look-ahead bias（歷史 IV 重建需要點對點正確，這是本函式存在的
    理由）。分母用呼叫端傳入「那天」的標的價，不是今天的 spot。離群值
    抑制沿用既有 `_dampen_outliers`，不重新實作。
    """
    if spot <= 0:
        raise ParamError(f"spot 必須為正數：{spot}")
    cutoff = observation_date - timedelta(days=TTM_WINDOW_DAYS)
    amounts = tuple(
        r.amount for r in history.distributions
        if cutoff < date.fromisoformat(r.ex_date) <= observation_date)
    if not amounts:
        return 0.0
    return sum(_dampen_outliers(amounts)) / spot


# ---------- 快取序列化（data.dividends／api_app.dividend_cache 落盤用） ----------

def history_to_dict(history: DividendHistory) -> dict:
    return {"symbol": history.symbol, "as_of": history.as_of,
            "source": history.source,
            "distributions": [[r.ex_date, r.amount] for r in history.distributions],
            "stale": history.stale}


def history_from_dict(data: dict) -> DividendHistory:
    return DividendHistory(
        symbol=data["symbol"], as_of=data["as_of"],
        source=data.get("source", "unknown"),
        distributions=tuple(DividendRecord(ex_date=d, amount=float(a))
                            for d, a in data["distributions"]),
        stale=bool(data.get("stale", False)))
