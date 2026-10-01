"""測試用的凍結日期（CLAUDE-MOBILE-CARD-OVERLAP-001 順帶修的 CI 定時炸彈）。

後端測試大量以 `tests/fixtures/xyz_v4_six_expiries.json`（到期日 2026-08～
2026-12）為前提，劇本目標年月寫死在 2026-08／09／10。真實日期一跨過某個目標
月，那一批測試就一起變成 400「目標年月已經過完」，跟被測的程式碼毫無關係。

- `FROZEN_NY_TODAY`：`conftest.py` 把 `ny_today()` 凍結在這一天（建立／編輯劇本
  的 `ensure_month_open(month, ny_today())` 用它）。
- `fresh_fetched_at()`：測試要「剛抓的新鮮快照」時用它當 `fetched_at`——刷新時
  引擎以快照的 `fetched_at` 當「今天」（`snapshot_today()`），所以日期也得凍結；
  時刻沿用真實時刻，同一個測試裡前後兩次呼叫仍然遞增。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# fixture 的到期日與測試寫死的目標年月都還有效的日子（2026-09-29 CI 全綠時的
# 紐約日期）。
FROZEN_NY_TODAY = date(2026, 9, 28)
_EASTERN = ZoneInfo("America/New_York")


def fresh_fetched_at() -> str:
    """凍結日期（紐約）＋真實的紐約時刻，換回 UTC，格式同 `clock.now_utc_iso()`。"""
    real = datetime.now(_EASTERN)
    shifted = datetime.combine(FROZEN_NY_TODAY, real.timetz())
    return shifted.astimezone(timezone.utc).isoformat(timespec="seconds")
