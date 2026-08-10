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

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from .models import ParamError

TTM_WINDOW_DAYS = 365

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
