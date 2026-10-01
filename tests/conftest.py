"""測試共用的 `ny_today()` 凍結（見 `tests/_frozen_clock.py` 的來龍去脈）。

只凍結 `ny_today()`（「今天是哪個交易日」），**不**凍結 `now_utc_iso()`／
`time.time()`：那兩者驅動 owner 年資（new-owner tier）、rate-limit 視窗等「距今
多久」的判斷，凍結其中一邊而另一邊照走真實時鐘會讓那些測試錯亂。需要新鮮快照
的測試改用 `_frozen_clock.fresh_fetched_at()` 當 `fetched_at`。

已經 `from api_app.clock import ny_today` 的模組（`api_app.main` 與部分測試檔）
各自持有原函式的參照，所以逐一替換所有指向原函式的模組屬性，而不是只改
`api_app.clock` 一處。個別測試若要另一個日期，照舊自己 monkeypatch——會蓋過
這裡的值。
"""
from __future__ import annotations

import sys

import pytest

from api_app import clock
from tests._frozen_clock import FROZEN_NY_TODAY

_ORIGINAL_NY_TODAY = clock.ny_today


def _frozen_ny_today():
    return FROZEN_NY_TODAY


@pytest.fixture(autouse=True)
def _freeze_ny_today(monkeypatch):
    for module in list(sys.modules.values()):
        if getattr(module, "ny_today", None) is _ORIGINAL_NY_TODAY:
            monkeypatch.setattr(module, "ny_today", _frozen_ny_today)
