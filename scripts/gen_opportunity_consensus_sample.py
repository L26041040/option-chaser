#!/usr/bin/env python
"""重產共識清單的契約樣本 `contracts/opportunity_consensus_sample.json`（OS-03／#392）。

比照 `gen_contract_sample.py`：樣本是一次真實 `GET /api/opportunity/consensus`
的完整回應——記憶體 storage、注入**測試資料來源**
（`FixtureAnalystSource`，ticker AAA…GGG，`source.is_fixture = true`）、
母體設成自訂清單 AAA…GGG、跑一次 `GET /api/cron/consensus-refresh`。
樣本因此涵蓋 ok（兩關皆過／只過一關）、資料不足、無資料、來源失敗。

**不連任何資料庫、不打任何外部網路**；評估日固定在 2026-09-28
（`tests/_frozen_clock.FROZEN_NY_TODAY`），讓樣本可重現。後端
`test_opportunity_consensus_sample_matches_the_live_response` 逐欄比對，
前端 vitest／e2e 的 mock 直接載入這份樣本。

    PYTHONPATH=. .venv/bin/python scripts/gen_opportunity_consensus_sample.py
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
OUT = Path("contracts/opportunity_consensus_sample.json")
AS_OF = date(2026, 9, 28)
SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
_DEFAULT = {"mode": "default", "provider": None}


def build_sample(storage: MemoryStorage | None = None) -> dict:
    """樣本內容；後端測試也呼叫這個函式產生「現在的」回應來比對。"""
    from tests._role_session import grant_role
    storage = storage or MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    original = main_module.ny_today
    main_module.ny_today = lambda: AS_OF
    try:
        client = TestClient(main_module.create_app(
            identity_resolver=lambda: "solo", storage=storage,
            analyst_source=FixtureAnalystSource(FIXTURE), cron_secret="sample"))
        client.put("/api/settings", json={
            "market_data": _DEFAULT, "historical_iv": _DEFAULT,
            "opportunity_search": {"universe_id": "custom",
                                   "custom_symbols": SYMBOLS}}).raise_for_status()
        client.get("/api/cron/consensus-refresh",
                   headers={"Authorization": "Bearer sample"}).raise_for_status()
        r = client.get("/api/opportunity/consensus")
        r.raise_for_status()
        return r.json()
    finally:
        main_module.ny_today = original


def main() -> None:
    OUT.write_text(json.dumps(build_sample(), ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
