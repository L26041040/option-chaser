"""測試共用的時間凍結（CLAUDE-MOBILE-CARD-OVERLAP-001 順帶修的 CI 定時炸彈）。

後端測試大量以 `tests/fixtures/xyz_v4_six_expiries.json`（到期日 2026-08～
2026-12）為前提，劇本目標年月寫死在 2026-08／09／10。兩條路徑都讀真實時鐘：

- 建立劇本：`ensure_month_open(month, ny_today())`；
- 刷新：引擎以快照的 `fetched_at` 當「今天」（`snapshot_today()`），而不少
  測試的「新鮮快照」用 `now_utc_iso()` 當 `fetched_at`。

只要真實日期一跨過某個目標月（2026-10-01 起是 2026-09），那一批測試就一起
變成 400「目標年月已經過完」，跟被測的程式碼毫無關係。

這裡把 `api_app.clock` 的兩個時鐘入口（`ny_today()`／`now_utc_iso()`，該模組
檔頭明訂的全站「現在」唯一來源）凍結在 fixture 仍然有效的日期：日期固定、
時刻沿用真實時刻（同一個測試裡前後兩次呼叫仍然遞增，順序與「剛剛」的語意
不變）。已經 `from api_app.clock import ...` 的模組（`api_app.main` 與部分測試
檔）各自持有原函式的參照，所以逐一替換所有指向原函式的模組屬性，而不是只改
`api_app.clock` 一處。

個別測試若要另一個日期，照舊在測試裡自己 monkeypatch——會蓋過這裡的值。
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from api_app import clock

# fixture 的到期日與測試寫死的目標年月都還有效的日子（2026-09-29 CI 全綠時的
# 紐約日期）。
FROZEN_NY_TODAY = date(2026, 9, 28)
_EASTERN = ZoneInfo("America/New_York")

_ORIGINALS = {"ny_today": clock.ny_today, "now_utc_iso": clock.now_utc_iso}


def _frozen_ny_today() -> date:
    return FROZEN_NY_TODAY


def _frozen_now_utc_iso() -> str:
    """凍結日期（紐約）＋真實的紐約時刻，換回 UTC，格式同 `clock.now_utc_iso()`。"""
    real = datetime.now(_EASTERN)
    shifted = datetime.combine(FROZEN_NY_TODAY, real.timetz())
    return shifted.astimezone(timezone.utc).isoformat(timespec="seconds")


_FROZEN = {"ny_today": _frozen_ny_today, "now_utc_iso": _frozen_now_utc_iso}


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    for module in list(sys.modules.values()):
        for name, original in _ORIGINALS.items():
            if getattr(module, name, None) is original:
                monkeypatch.setattr(module, name, _FROZEN[name])
