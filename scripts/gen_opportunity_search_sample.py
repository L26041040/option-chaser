#!/usr/bin/env python
"""重產機會搜尋的契約樣本 `contracts/opportunity_search_sample.json`（OS-04／#393）。

比照 `gen_opportunity_consensus_sample.py`：樣本是一次真實
`POST /api/opportunity/search` 的完整回應——記憶體 storage、注入**測試資料
來源**（`FixtureAnalystSource`，ticker AAA…GGG）、母體設成自訂清單、跑一次
共識更新；選擇權鏈用固定 fixture（`xyz_v7_butterfly_moderate.json`，三個
家族都有候選），利率／配息用 `gen_contract_sample.py` 的固定假資料。
入選的兩檔裡 AAA 成功、EEE 模擬抓鏈失敗，樣本因此同時有 `rows` 與
`failures`；一次呼叫處理完（`refresh_run_group_limit=10`）。

**不連任何資料庫、不打任何外部網路**；評估日固定在 2026-09-28。後端
`test_opportunity_search_sample_matches_the_live_response` 逐欄比對，前端
vitest／e2e 的 mock 直接載入這份樣本。

    PYTHONPATH=. .venv/bin/python scripts/gen_opportunity_search_sample.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import FixtureAnalystSource
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError
from scripts.gen_contract_sample import _sample_dividend_loader, _sample_rate_loader

ANALYST_FIXTURE = Path("tests/fixtures/analyst_targets_fixture.json")
CHAIN_FIXTURE = Path("tests/fixtures/xyz_v7_butterfly_moderate.json")
OUT = Path("contracts/opportunity_search_sample.json")
AS_OF = date(2026, 9, 28)
SYMBOLS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
_DEFAULT = {"mode": "default", "provider": None}


def build_sample(storage: MemoryStorage | None = None) -> dict:
    """樣本內容；後端測試也呼叫這個函式產生「現在的」回應來比對。"""
    from tests._role_session import grant_role
    storage = storage or MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    chain = load_snapshot(str(CHAIN_FIXTURE))

    def fetch(symbol: str):
        if symbol == "EEE":
            raise FetchError("測試資料模擬上游失敗")
        return chain

    original = main_module.ny_today
    main_module.ny_today = lambda: AS_OF
    try:
        client = TestClient(main_module.create_app(
            identity_resolver=lambda: "solo", storage=storage, fetch=fetch,
            rate_loader=_sample_rate_loader, dividend_loader=_sample_dividend_loader,
            analyst_source=FixtureAnalystSource(ANALYST_FIXTURE),
            cron_secret="sample", refresh_run_group_limit=10))
        client.put("/api/settings", json={
            "market_data": _DEFAULT, "historical_iv": _DEFAULT,
            "opportunity_search": {"universe_id": "custom",
                                   "custom_symbols": SYMBOLS}}).raise_for_status()
        client.get("/api/cron/consensus-refresh",
                   headers={"Authorization": "Bearer sample"}).raise_for_status()
        r = client.post("/api/opportunity/search", json={})
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
