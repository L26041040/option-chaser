#!/usr/bin/env python
"""重產個股共識詳細資料的契約樣本 `contracts/opportunity_detail_sample.json`（LIVE-T2／#399）。

樣本是一次真實 `GET /api/opportunity/consensus-detail/NVDA` 的完整回應：記憶體
storage、注入真實來源 `YahooAnalystSource`，但 HTTP 層回放
`tests/fixtures/yahoo/` 裡**錄下的真實 Yahoo 回應**（不連外）、規則與部署
環境相同（`ConsensusRules(aliases=FIRM_ALIASES)`）、評估日固定 2026-11-21，
先跑一次每日更新 cron 再讀詳細資料。

**不連任何資料庫、不打任何外部網路**。後端
`test_opportunity_detail_sample_matches_the_live_response` 逐欄比對，前端
vitest／e2e 的 mock 直接載入這份樣本。

    PYTHONPATH=. .venv/bin/python scripts/gen_opportunity_detail_sample.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import YahooAnalystSource
from api_app.consensus_cache import RefreshPolicy
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import ConsensusRules
from option_chaser.data.yahoo_analyst import FIRM_ALIASES

OUT = Path("contracts/opportunity_detail_sample.json")
AS_OF = date(2026, 11, 21)
SYMBOL = "NVDA"
_DEFAULT = {"mode": "default", "provider": None}


def build_sample() -> dict:
    from tests._role_session import grant_role
    from tests.test_yahoo_analyst_source import ReplayTransport
    storage = MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    original = main_module.ny_today
    main_module.ny_today = lambda: AS_OF
    try:
        client = TestClient(main_module.create_app(
            identity_resolver=lambda: "solo", storage=storage,
            analyst_source=YahooAnalystSource(transport=ReplayTransport()),
            cron_secret="sample", consensus_rules=ConsensusRules(aliases=FIRM_ALIASES),
            consensus_refresh_policy=RefreshPolicy(call_spacing_seconds=0)))
        client.put("/api/settings", json={
            "market_data": _DEFAULT, "historical_iv": _DEFAULT,
            "opportunity_search": {"universe_id": "custom",
                                   "custom_symbols": [SYMBOL]}}).raise_for_status()
        client.get("/api/cron/consensus-refresh",
                   headers={"Authorization": "Bearer sample"}).raise_for_status()
        r = client.get(f"/api/opportunity/consensus-detail/{SYMBOL}")
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
