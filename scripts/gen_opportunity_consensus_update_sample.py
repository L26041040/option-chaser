#!/usr/bin/env python
"""重產「更新分析師資料」的兩份契約樣本（LIVE-T3／#398）：

- `contracts/opportunity_consensus_update_sample.json`：一次真實
  `POST /api/opportunity/consensus/update`（第一批，有 `remaining`）的完整回應；
- `contracts/opportunity_consensus_status_sample.json`：緊接著的
  `GET /api/opportunity/consensus/status`。

比照 `gen_opportunity_consensus_sample.py`：記憶體 storage、注入**測試資料來源**
（`FixtureAnalystSource`，GGG 模擬上游失敗）、SU 的自訂清單 AAA…GGG 併進更新
母體、評估日固定 2026-09-28、時鐘固定——**不連任何資料庫、不打任何外部網路**，
樣本可重現。樣本因此涵蓋已完成、冷卻中（失敗）與還沒試的檔。後端
`test_update_and_status_samples_match_the_live_responses` 逐欄比對，前端
vitest／e2e 的 mock 直接載入這兩份樣本。

    PYTHONPATH=. .venv/bin/python scripts/gen_opportunity_consensus_update_sample.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import FixtureAnalystSource
from api_app.storage.memory import MemoryStorage

FIXTURE = Path("tests/fixtures/analyst_targets_fixture.json")
UPDATE_OUT = Path("contracts/opportunity_consensus_update_sample.json")
STATUS_OUT = Path("contracts/opportunity_consensus_status_sample.json")
AS_OF = date(2026, 9, 28)
NOW = 1_790_600_000.0          # 2026-09-28T12:53:20Z（美東 08:53）
SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
_DEFAULT = {"mode": "default", "provider": None}


def build_samples() -> tuple[dict, dict]:
    """（update 回應, status 回應）；後端測試也呼叫它產生「現在的」回應來比對。"""
    from tests._role_session import grant_role
    storage = MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    original = main_module.ny_today
    main_module.ny_today = lambda: AS_OF
    try:
        client = TestClient(main_module.create_app(
            identity_resolver=lambda: "solo", storage=storage,
            analyst_source=FixtureAnalystSource(FIXTURE), clock=lambda: NOW,
            # 更新母體固定成「優先更新的 50 檔＋自訂 7 檔」：預設範圍改成
            # S&P 500（#404）後，樣本仍只示範更新機制，不帶幾百檔成分股。
            consensus_refresh_symbol_cap=57,
            consensus_refresh_policy=main_module.consensus_cache.RefreshPolicy(
                batch_size=25)))   # 一批涵蓋到 GGG（依代號排序第 23 檔）
        client.put("/api/settings", json={
            "market_data": _DEFAULT, "historical_iv": _DEFAULT,
            "opportunity_search": {"universe_id": "custom",
                                   "custom_symbols": SYMBOLS}}).raise_for_status()
        update = client.post("/api/opportunity/consensus/update", json={})
        update.raise_for_status()
        status = client.get("/api/opportunity/consensus/status")
        status.raise_for_status()
        return update.json(), status.json()
    finally:
        main_module.ny_today = original


def main() -> None:
    update, status = build_samples()
    for out, body in ((UPDATE_OUT, update), (STATUS_OUT, status)):
        out.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
