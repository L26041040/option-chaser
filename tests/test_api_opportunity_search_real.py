"""LIVE-T4（#400）：機會搜尋接上**真實**資料的回放測試。

輸入全部是錄下的真實回應（回放、不連外）：

- 分析師目標價：Yahoo `upgradeDowngradeHistory`＋chart（`tests/fixtures/yahoo/`，
  `scripts/record_real_opportunity_fixture.py` 錄；JPM 錄於 2026-11-22 美東），
  經 #398 的正式更新路徑（`POST /api/opportunity/consensus/update`）寫進快取、
  #399 的歷史共識與資料品質規則判定。
- 選擇權 chain：`tests/fixtures/real_chain_JPM_2026-11-22.json`，走既有
  `service.fetch_chain()` 錄下（`source` 照實是 `yfinance`：沙箱連 Cboe 被
  Cloudflare 擋，既有降級鏈退到 yfinance）。

釘住：

- **計算等價（#389 §5.2／C5，真實 chain）**：搜尋列逐欄等於「手動建立同參數
  劇本」所得的同家族代表候選。
- **入選只來自真實歷史共識**：資料品質沒過的股票（歷史不足、分析師不足）即使門檻放到最寬也不會入選，也不能被指名搜尋。
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import YahooAnalystSource
from api_app.consensus_cache import RefreshPolicy
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import ConsensusRules
from option_chaser.data.snapshot import load_snapshot
from option_chaser.data.yahoo_analyst import FIRM_ALIASES
from scripts.gen_contract_sample import _sample_dividend_loader, _sample_rate_loader
from tests._role_session import grant_role
from tests.test_yahoo_analyst_source import ReplayTransport

DAY = date(2026, 11, 22)   # 樣本錄製日（美東）＝ chain 的 fetched_at 當天
REAL_CHAIN = "tests/fixtures/real_chain_JPM_2026-11-22.json"
ALL_FAMILIES = ["single-leg", "vertical-spread", "butterfly"]
_DEFAULT = {"mode": "default", "provider": None}


@pytest.fixture
def real_client(monkeypatch):
    monkeypatch.setattr(main_module, "ny_today", lambda: DAY)
    storage = MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    chain = load_snapshot(REAL_CHAIN)
    client = TestClient(create_app(
        identity_resolver=lambda: "solo", storage=storage,
        analyst_source=YahooAnalystSource(transport=ReplayTransport()),
        consensus_rules=ConsensusRules(aliases=FIRM_ALIASES),
        consensus_refresh_policy=RefreshPolicy(call_spacing_seconds=0),
        refresh_run_group_limit=10,
        fetch=lambda symbol: chain,
        rate_loader=_sample_rate_loader, dividend_loader=_sample_dividend_loader))
    return client, storage


def _build(client, symbols, **thresholds):
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "custom", "custom_symbols": symbols,
                               **thresholds}})
    assert r.status_code == 200, r.text
    while True:   # #398 的正式更新路徑，依 remaining 續跑到完
        r = client.post("/api/opportunity/consensus/update", json={})
        assert r.status_code == 200, r.text
        if not r.json()["remaining"]:
            break
    return {i["symbol"]: i for i in client.get("/api/opportunity/consensus").json()["items"]}


def test_real_chain_search_rows_equal_the_manually_created_scenario(real_client):
    client, storage = real_client
    items = _build(client, ["JPM"])          # 預設門檻 20%／10%
    jpm = items["JPM"]
    assert jpm["status"] == "ok" and jpm["gate"]["selected"] is True
    assert jpm["as_of"] == "2026-11-22" and jpm["target_month"] == "2027-11"

    r = client.post("/api/opportunity/search", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["processed"] == ["JPM"] and body["failures"] == []
    rows = {row["family"]: row for row in body["rows"]}
    assert set(rows) == set(ALL_FAMILIES)
    # 每列只帶自己的家族（#408）；同一組參數換回全部家族＝搜尋本身跑的劇本。
    scenario = {**rows["single-leg"]["scenario"], "strategies": ALL_FAMILIES}
    assert all(r["scenario"] == {**scenario, "strategies": [f]}
               for f, r in rows.items())
    assert scenario == {"symbol": "JPM", "target_price": jpm["mean"],
                        "target_month": "2027-11", "strategies": ALL_FAMILIES}

    created = client.post("/api/scenarios", json=scenario)
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    refreshed = client.post(f"/api/scenarios/{sid}/refresh")
    assert refreshed.status_code == 200, refreshed.text

    saved = storage.latest_result(sid, owner="solo")
    assert saved.view["meta"]["source"] == "yfinance"
    assert set(saved.per_family) == set(rows)
    for family, rep in saved.per_family.items():
        row = rows[family]
        candidate = saved.view["candidate_pool"][rep["candidate_key"]]
        assert (row["subtype"], row["candidate_key"], row["legs"], row["expiry"]) == (
            rep["strategy"], rep["candidate_key"], rep["legs"], rep["expiry"])
        assert row["target_return"] == rep["baseline_return"]
        assert row["entry_cost"] == candidate["natural_cost"]
        assert row["max_loss_per_contract"] == candidate["max_loss_per_contract"]
        assert row["breakeven"] == candidate["breakeven"]
        assert row["buffer_days"] == candidate["buffer_days"]
    card = refreshed.json()["representative_candidate"]
    best = max(rows.values(), key=lambda row: row["target_return"])
    assert card["candidate_key"] == best["candidate_key"]
    assert refreshed.json()["best_return"] == best["target_return"]


def test_insufficient_real_data_never_enters_the_search(real_client):
    """門檻放到最寬（100%／100%）：資料品質沒過的真實樣本仍然不入選——入選
    只看 #399 的 status，門檻救不回資料不足。指名搜尋也 400。"""
    client, _ = real_client
    items = _build(client, ["JPM", "TSM", "WDFC"],
                   percentile_max=100, dispersion_max=100)
    assert {s: i["status"] for s, i in items.items()} == {
        "JPM": "ok", "TSM": "insufficient_history",
        "WDFC": "insufficient_analysts"}
    assert [s for s, i in items.items() if i["gate"]["selected"]] == ["JPM"]
    for symbol in ("TSM", "WDFC"):
        assert items[symbol]["reasons"], symbol   # 原因照實列出
        r = client.post("/api/opportunity/search", json={"symbols": [symbol]})
        assert r.status_code == 400 and symbol in r.json()["detail"]
    body = client.post("/api/opportunity/search", json={}).json()
    assert body["processed"] == ["JPM"]
