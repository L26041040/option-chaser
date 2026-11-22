"""LIVE-T2（#399）：個股共識詳細資料端點 `GET /api/opportunity/consensus/{symbol}`。

- 只限 SU／SA（Normal 403）；只讀全站共識快取，**不打上游**。
- 內容：目前有效集合（券商、原始目標價、發布日、分割換算後的值）、平均／
  標準差／D／自身歷史 midrank 百分位、每月 D 序列與合格點數、不合格原因；
  `gate` 依這位使用者的門檻算，與共識清單同一份。
- 輸入是錄下的真實 Yahoo 回應（`tests/fixtures/yahoo/`，回放、不連外），
  經每日更新 cron 寫進快取——與部署環境同一條路徑、同一組規則。
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import FixtureAnalystSource, YahooAnalystSource
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import ConsensusRules
from option_chaser.data.yahoo_analyst import FIRM_ALIASES
from tests._role_session import grant_role
from tests.test_yahoo_analyst_source import ReplayTransport

CRON = {"Authorization": "Bearer test-secret"}
_DEFAULT = {"mode": "default", "provider": None}
DAY = date(2026, 11, 21)


class NoUpstream:
    """快取已寫好之後換上的來源：任何抓取都是錯誤（證明詳細資料不打上游）。"""

    name = "yahoo-udh"
    is_fixture = False

    def fetch(self, symbol, today):
        raise AssertionError(f"detail endpoint hit upstream for {symbol}")


def _client(storage, source, *, role="superuser", owner="solo"):
    if role != "normal":
        grant_role(storage, role, owner_id=owner)
    return TestClient(create_app(
        identity_resolver=lambda: owner, storage=storage, analyst_source=source,
        cron_secret="test-secret", consensus_rules=ConsensusRules(aliases=FIRM_ALIASES)))


@pytest.fixture
def cached(monkeypatch):
    """NVDA／AAPL／BABA／WDFC／TSM 的真實樣本經每日 cron 寫進快取（評估日 2026-11-21）。"""
    monkeypatch.setattr(main_module, "ny_today", lambda: DAY)
    storage = MemoryStorage()
    client = _client(storage, YahooAnalystSource(transport=ReplayTransport()))
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "custom",
                               "custom_symbols": ["NVDA", "AAPL", "BABA",
                                                  "WDFC", "TSM"]}})
    assert r.status_code == 200, r.text
    r = client.get("/api/cron/consensus-refresh", headers=CRON)
    assert r.status_code == 200, r.text
    return storage


def _detail(client, symbol):
    r = client.get(f"/api/opportunity/consensus/{symbol}")
    assert r.status_code == 200, r.text
    return r.json()


def test_detail_shows_how_the_consensus_was_computed_from_real_targets(cached):
    body = _detail(_client(cached, NoUpstream()), "NVDA")
    item = body["item"]
    assert item["symbol"] == "NVDA" and item["status"] == "ok"
    assert item["as_of"] == "2026-11-21"
    assert item["n_analysts"] == len(body["effective"]) == 35
    assert body["detail_available"] is True
    # 每位券商一列：原始目標價、發布日、分割換算後的值
    bernstein = next(e for e in body["effective"] if e["firm"] == "Bernstein")
    assert bernstein == {"firm": "Bernstein", "analyst_key": "bernstein",
                         "target_price": 200.0, "adjusted_price": 200.0,
                         "published_on": "2026-11-12", "action": "Lowers",
                         "prior_target": 400.0}
    # 平均／標準差／D／百分位與清單同一份
    listing = next(i for i in _client(cached, NoUpstream())
                   .get("/api/opportunity/consensus").json()["items"]
                   if i["symbol"] == "NVDA")
    assert item == listing


def test_detail_carries_the_monthly_dispersion_series_and_qualified_count(cached):
    body = _detail(_client(cached, NoUpstream()), "NVDA")
    series = body["series"]
    assert len(series) == 60
    assert series[0]["on"] == "2021-11-30" and series[-1]["on"] == "2026-10-30"
    assert body["qualified_points"] == body["item"]["history_points"] == 60
    first = series[0]
    assert set(first) == {"on", "n_analysts", "mean", "stdev", "dispersion",
                          "qualified", "reason"}
    assert first["qualified"] is True and first["reason"] is None
    assert 0 < first["dispersion"] < 1


@pytest.mark.parametrize("symbol, status, reason_codes, n, points", [
    # 低覆蓋股：12 個月內只剩 DA Davidson 一家（2026-07-10，305）
    ("WDFC", "insufficient_analysts",
     ["insufficient_analysts", "stale", "insufficient_history"], 1, 0),
    # ADR：Yahoo 事件史短，合格歷史點只有 10 個
    ("TSM", "insufficient_history", ["insufficient_history"], 9, 10),
])
def test_insufficient_stock_shows_concrete_reasons_and_is_never_selected(
        cached, symbol, status, reason_codes, n, points):
    client = _client(cached, NoUpstream())
    # 門檻放到最寬：資料不足的股票仍不入選
    r = client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"percentile_max": 100, "dispersion_max": 100}})
    assert r.status_code == 200, r.text
    body = _detail(client, symbol)
    item = body["item"]
    assert item["status"] == status
    assert [x.split(":", 1)[0] for x in item["reasons"]] == reason_codes
    assert item["gate"] == {"first": False, "second": False, "selected": False,
                            "reasons": item["reasons"]}
    assert len(body["effective"]) == item["n_analysts"] == n
    assert body["qualified_points"] == points


def test_detail_reads_the_cache_only_and_never_calls_upstream(cached):
    client = _client(cached, NoUpstream())
    for symbol in ("NVDA", "AAPL", "BABA", "ZZZQ"):
        assert client.get(f"/api/opportunity/consensus/{symbol}").status_code == 200


def test_symbol_never_refreshed_says_so_with_no_numbers(cached):
    body = _detail(_client(cached, NoUpstream()), "ZZZQ")
    assert body["item"]["status"] == "no_data"
    assert body["item"]["reasons"] == ["no_data: 尚未更新"]
    assert body["item"]["gate"]["selected"] is False
    assert body["effective"] == [] and body["series"] == []
    assert body["qualified_points"] == 0 and body["detail_available"] is False


def test_lowercase_symbol_is_normalised_and_garbage_is_rejected(cached):
    client = _client(cached, NoUpstream())
    assert _detail(client, "nvda")["item"]["symbol"] == "NVDA"
    assert client.get("/api/opportunity/consensus/%3Cscript%3E").status_code == 400
    assert client.get("/api/opportunity/consensus/" + "A" * 20).status_code == 400


def test_normal_user_is_refused(cached):
    client = _client(cached, NoUpstream(), role="normal", owner="someone-else")
    r = client.get("/api/opportunity/consensus/NVDA")
    assert r.status_code == 403


def test_failed_refresh_without_any_earlier_data_reports_the_source_error(cached):
    # 母體裡的 MSFT 沒有錄製樣本 → 回放 404 → 來源回報失敗、沒有任何 Snapshot
    item = _detail(_client(cached, NoUpstream()), "MSFT")["item"]
    assert item["status"] == "source_error"
    assert item["reasons"][0].startswith("source_error:")


def test_unconfigured_source_says_not_configured():
    client = _client(MemoryStorage(), None)
    body = _detail(client, "NVDA")
    assert body["source"]["configured"] is False
    assert body["message"] == "尚未設定分析師資料來源"
    assert body["item"] is None and body["effective"] == [] and body["series"] == []


def test_fixture_source_detail_is_flagged_as_fixture():
    storage = MemoryStorage()
    client = _client(storage, FixtureAnalystSource("tests/fixtures/analyst_targets_fixture.json"))
    client.put("/api/settings", json={
        "market_data": _DEFAULT, "historical_iv": _DEFAULT,
        "opportunity_search": {"universe_id": "custom", "custom_symbols": ["AAA"]}})
    client.get("/api/cron/consensus-refresh", headers=CRON)
    body = _detail(client, "AAA")
    assert body["source"] == {"configured": True, "name": "fixture", "is_fixture": True}
    assert body["detail_available"] is True


def test_detail_from_another_day_than_the_snapshot_is_not_shown_as_current(cached):
    from dataclasses import replace
    rec = cached.get_consensus_detail("NVDA")
    cached.save_consensus_detail(replace(rec, as_of="2026-11-20"))
    body = _detail(_client(cached, NoUpstream()), "NVDA")
    assert body["detail_available"] is False
    assert body["effective"] == [] and body["series"] == []
    assert body["item"]["status"] == "ok"            # 摘要數字照常（來自 Snapshot）


def test_opportunity_detail_sample_matches_the_live_response():
    """`contracts/opportunity_detail_sample.json` 是前端 vitest／e2e 的 mock：
    必須與現在的後端逐欄相同（真實 NVDA 樣本、評估日 2026-11-21）。"""
    import json
    from pathlib import Path

    from scripts.gen_opportunity_detail_sample import build_sample
    sample_path = Path("contracts/opportunity_detail_sample.json")
    assert sample_path.exists(), "請跑 scripts/gen_opportunity_detail_sample.py"
    assert json.loads(sample_path.read_text(encoding="utf-8")) == build_sample(), (
        "scripts/gen_opportunity_detail_sample.py 重產，並確認前端 mock 跟著更新")
