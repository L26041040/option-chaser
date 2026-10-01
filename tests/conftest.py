"""測試共用的時間凍結（CLAUDE-MOBILE-CARD-OVERLAP-001 順帶修的 CI 定時炸彈）。

後端測試大量以 `tests/fixtures/xyz_v4_six_expiries.json`（到期日 2026-08～
2026-12）為前提，劇本目標年月寫死在 2026-08／09／10。建立劇本會經過
`ensure_month_open(month, ny_today())`——`ny_today()` 讀真實時鐘，所以只要
真實日期一跨過某個目標月（2026-10-01 起是 2026-09），那一批測試就一起變成
400「目標年月已經過完」，跟被測的程式碼毫無關係。

這裡把「今天」凍結在 fixture 仍然有效的日期，讓測試不隨真實日期腐爛。只換
`ny_today()` 這一個全站「今天」的定義（`api_app.clock` 檔頭明訂的唯一入口），
`now_utc_iso()` 等時間戳照舊讀真實時鐘。已經 `from api_app.clock import
ny_today` 的模組（`api_app.main` 與部分測試檔）各自持有原函式的參照，所以
逐一替換所有指向原函式的模組屬性，而不是只改 `api_app.clock` 一處。

個別測試若要另一個日期，照舊在測試裡自己 monkeypatch——會蓋過這裡的值。
"""
from __future__ import annotations

import sys
from datetime import date

import pytest

from api_app import clock

# fixture 的到期日與測試寫死的目標年月都還有效的日子（2026-09-29 CI 全綠時的
# 紐約日期）。
FROZEN_NY_TODAY = date(2026, 9, 28)

_ORIGINAL_NY_TODAY = clock.ny_today


@pytest.fixture(autouse=True)
def _freeze_ny_today(monkeypatch):
    frozen = lambda: FROZEN_NY_TODAY  # noqa: E731
    for module in list(sys.modules.values()):
        if getattr(module, "ny_today", None) is _ORIGINAL_NY_TODAY:
            monkeypatch.setattr(module, "ny_today", frozen)
