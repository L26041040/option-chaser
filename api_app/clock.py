"""API 層的 wall-clock 讀取——引擎維持零 I/O，「現在」只活在這裡。

`ny_today()` 是全站「今天」的唯一定義（紐約日曆日，與引擎
`snapshot_today()` 的市場日語意一致）；`now_utc_iso()` 供事件與
快照時間戳使用。原本住在已刪除的 Streamlit 時代 workspace.py。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ny_today() -> date:
    return datetime.now(_EASTERN).date()
