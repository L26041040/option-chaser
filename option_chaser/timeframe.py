"""年月語意與到期日選取規則（純函式，無 I/O、無全域狀態）。

需求來源：`docs/modifyRequestV1.md` §二/§三＋附錄 A2/A5/A9。

使用者的市場判斷是**月級**的（「TLT 在 2028 年 1 月左右到達 105」），系統因此
不得把年月映射成任何單一日期。本模組是附錄 A9 授權例外的唯一合法來源：
`calendar_anchor()` 回傳的是**日曆錨點**（探索中心／舊表面的顯示參考日），
不是「目標日期」，也不得被持久化成 target_date。

五件事：
- `parse_target_month()` — 四種寫法歸一為 (年, 月)
- `calendar_anchor()`    — 該月第三個星期五，純日曆計算
- `month_is_over()`      — 目標月最後一天是否已過完
- `ensure_month_open()`  — 把上一條變成所有入口共用的拒絕規則
- `select_expiries()`    — 六點規則，從實際到期日中選出至多五檔
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .models import ParamError

FRIDAY = 4                # date.weekday(): Mon=0 … Fri=4
MAX_EXPIRIES = 5          # baseline + 前 2 + 後 2
_PER_SIDE = 2

_INPUT_RE = re.compile(r"^(\d{4}|\d{2})/(\d{1,2})$")
_KEY_RE = re.compile(r"^(\d{4})-(\d{2})$")


@dataclass(frozen=True)
class TargetMonth:
    """使用者主張的目標年月。刻意不帶「日」——年月就是完整的語意。"""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ParamError(f"月份必須介於 1-12：{self.month}")

    def key(self) -> str:
        """持久化形式（YYYY-MM）。"""
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def from_key(cls, key: str) -> "TargetMonth":
        """讀回持久化形式。與 `parse_target_month` 分開：使用者輸入寬鬆，
        存檔格式嚴格。"""
        m = _KEY_RE.match(key.strip())
        if not m:
            raise ParamError(f"目標年月格式必須為 YYYY-MM：{key!r}")
        return cls(int(m.group(1)), int(m.group(2)))

    def last_day(self) -> date:
        return date(self.year, self.month,
                    calendar.monthrange(self.year, self.month)[1])


@dataclass(frozen=True)
class ExpirySelection:
    """六點規則的選取結果。`expiries` 已排序、去重，且必定包含 `baseline`。"""

    baseline: str
    expiries: tuple[str, ...]


def parse_target_month(text: str) -> TargetMonth:
    """把 2028/1、2028/01、28/1、28/01 歸一為同一個 (年, 月)。

    兩位數年份視為本世紀（28 → 2028）。無法解析時拋 `ParamError`，
    不猜測、不默默吞掉。
    """
    m = _INPUT_RE.match(text.strip())
    if not m:
        raise ParamError(
            f"目標年月請輸入 2028/1、2028/01、28/1 或 28/01 之一的寫法：{text!r}")
    year_text, month_text = m.group(1), m.group(2)
    year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
    return TargetMonth(year, int(month_text))  # 月份範圍由 TargetMonth 把關


def calendar_anchor(month: TargetMonth) -> date:
    """該月第三個星期五（附錄 A9 的 `anchor`）。純日曆，不查市場資料。"""
    first = date(month.year, month.month, 1)
    first_friday = first + timedelta(days=(FRIDAY - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def month_is_over(month: TargetMonth, today: date) -> bool:
    """目標月最後一天是否已過完。最後一天當天不算過完，翌日才算。"""
    return today > month.last_day()


def ensure_month_open(month: TargetMonth, today: date) -> TargetMonth:
    """月級驗證的單一出口：已過完 → 拒絕；當月（含最後一天）→ 放行。

    建立劇本、CLI、service 三個入口共用同一條規則與同一句錯誤訊息——判定散落
    在各層是「某一層偷偷放寬」的溫床。回傳原 month 以便串接。
    """
    if month_is_over(month, today):
        raise ParamError(
            f"目標年月 {month.key()} 已經過完（判定日 {today.isoformat()}）")
    return month


def tradable_expiries(expiries: Iterable[str], today: date) -> set[str]:
    """尚未到期（`expiry > today`，嚴格大於）的到期日子集合——T3
    （#17）既有前提「已到期／當日到期的合約 T<=0，Greeks 無定義，
    根本不是可分析的標的」的純日期版本。`service._scoped_to_
    selected_expiries()` 與 `history_resolver.resolve_historical_
    cost()` 共用同一個判準（SCALE-09／#261 code review 抽出，避免
    兩處各自維護一份可能漂移的複本）。"""
    return {e for e in expiries if date.fromisoformat(e) > today}


def select_expiries(expiries: Iterable[str], anchor: date) -> ExpirySelection:
    """六點規則：錨點 → baseline → 前 2 後 2，至多五檔。

    baseline 為距錨點最近的實際到期日（同距取**較晚**者）。某一側不足時，
    缺額由另一側依距離補足；鏈上不足五檔時有幾檔用幾檔。

    到期日的取捨完全由本函式負責——`filters` 不再設任何到期日下限，
    因此 baseline **前方**的到期日（可能早於目標月）會如實出現在結果中。
    """
    exps = sorted(set(expiries))
    if not exps:
        raise ParamError("到期日清單為空，無法選取")

    baseline = min(
        exps,
        key=lambda e: (abs((date.fromisoformat(e) - anchor).days),
                       -date.fromisoformat(e).toordinal()),
    )
    i = exps.index(baseline)
    before, after = exps[:i], exps[i + 1:]

    take_before, take_after = before[-_PER_SIDE:], after[:_PER_SIDE]
    deficit = (MAX_EXPIRIES - 1) - len(take_before) - len(take_after)
    if deficit > 0:
        # 缺額只可能出現在一側；由另一側繼續向外依距離補足。
        if len(take_before) < _PER_SIDE:
            take_after = after[:_PER_SIDE + deficit]
        else:
            take_before = before[-(_PER_SIDE + deficit):]

    return ExpirySelection(
        baseline=baseline,
        expiries=tuple(take_before) + (baseline,) + tuple(take_after),
    )
