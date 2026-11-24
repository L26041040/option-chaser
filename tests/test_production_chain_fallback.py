"""OPTION-CHASER-PRODUCTION-DELIVERY-001：預設抓鏈降級鏈 Cboe → Yahoo 直連 →
yfinance（只有裝了才試），以及 `/api/health` 的 `opportunity` 診斷。

Cboe 從部分網路被 Cloudflare 擋（307 → cdn-api.cboe.com → 403），Vercel 又不裝
yfinance——Yahoo 直連（stdlib）是 production 在 Cboe 被擋時唯一的真實來源。
這裡走**正式的** `_default_fetch()`（不覆寫 `fetch=`），Cboe 用 `cboe_fetch=` DI
注入失敗、Yahoo／yfinance 用 monkeypatch 模組屬性注入，零網路。每個上游 attempt
各自過一次 `_vendor_attempt()`（fuse、額度、指標）。
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app import metrics
from api_app.analyst_source import YahooAnalystSource
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import service
from option_chaser.data import yahoo_options, yf
from option_chaser.data.snapshot import load_snapshot
from option_chaser.data.yahoo_options import YahooOptionsClient
from option_chaser.models import FetchError, RateLimitedError
from scripts.gen_contract_sample import _sample_dividend_loader, _sample_rate_loader
from tests.test_yahoo_options import OptionsReplayTransport

DAY = date(2026, 11, 23)                       # Yahoo fixture 錄製日（美東）
RECORDED_AT = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
SCENARIO = {"symbol": "AAPL", "target_price": 370.0, "target_month": "2027-01",
            "strategies": ["single-leg", "vertical-spread", "butterfly"]}
FIX = "tests/fixtures/xyz_v4_six_expiries.json"


class Scripted:
    """計數的抓鏈假體；`error` 不是 None 時丟它。"""

    def __init__(self, snap=None, error: Exception | None = None):
        self.snap, self.error, self.calls = snap, error, 0

    def __call__(self, symbol):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snap


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(main_module, "ny_today", lambda: DAY)
    transport = OptionsReplayTransport()
    yahoo = Scripted()        # 只用來計數／注入錯誤；成功時走真的 adapter＋回放

    def yahoo_fetch(symbol):
        yahoo.calls += 1
        if yahoo.error is not None:
            raise yahoo.error
        return YahooOptionsClient(transport).fetch_chain(symbol, now=lambda: RECORDED_AT)

    yfin = Scripted(dataclasses.replace(
        YahooOptionsClient(OptionsReplayTransport()).fetch_chain(
            "AAPL", now=lambda: RECORDED_AT), source="yfinance"))
    monkeypatch.setattr(yahoo_options, "fetch_chain", yahoo_fetch)
    monkeypatch.setattr(yf, "fetch_chain", yfin)
    monkeypatch.setattr(yf, "available", lambda: True)
    cboe = Scripted(error=FetchError("Cboe 抓取失敗（AAPL）: HTTP 403"))
    storage = MemoryStorage()
    client = TestClient(create_app(
        identity_resolver=lambda: "solo", storage=storage, cboe_fetch=cboe,
        rate_loader=_sample_rate_loader, dividend_loader=_sample_dividend_loader))
    sc = client.post("/api/scenarios", json=SCENARIO)
    assert sc.status_code == 201, sc.text
    return dict(client=client, storage=storage, sid=sc.json()["id"], cboe=cboe,
                yahoo=yahoo, yf=yfin, transport=transport)


def _refresh(env):
    return env["client"].post(f"/api/scenarios/{env['sid']}/refresh")


def _metrics(storage) -> dict:
    out: dict = {}
    for e in storage.metric_summary():
        out[(e.metric, e.source)] = out.get((e.metric, e.source), 0) + e.count
    return out


def test_cboe_blocked_falls_back_to_yahoo_and_the_real_chain_is_analyzed(env):
    r = _refresh(env)
    assert r.status_code == 200, r.text
    saved = env["storage"].latest_result(env["sid"], owner="solo")
    assert saved.view["meta"]["source"] == "yahoo"
    assert set(saved.per_family) == {"single-leg", "vertical-spread", "butterfly"}
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 1, 0)
    # cookie＋crumb＋3 個到期日頁
    assert len(env["transport"].calls) == 5
    m = _metrics(env["storage"])
    assert m.get(("chain_fetch_count", "cboe")) == 1
    assert m.get(("chain_fetch_count", "yahoo")) == 1
    assert ("chain_fetch_count", "yfinance") not in m


def test_yahoo_failure_falls_back_to_yfinance_when_installed(env):
    env["yahoo"].error = FetchError("Yahoo 選擇權抓取失敗（AAPL）：連線失敗或逾時")
    r = _refresh(env)
    assert r.status_code == 200, r.text
    saved = env["storage"].latest_result(env["sid"], owner="solo")
    assert saved.view["meta"]["source"] == "yfinance"
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 1, 1)
    m = _metrics(env["storage"])
    assert [m.get(("chain_fetch_count", s)) for s in ("cboe", "yahoo", "yfinance")] == [1, 1, 1]


def test_all_sources_failing_is_a_fetch_failure(env, monkeypatch):
    env["yahoo"].error = FetchError("Yahoo 選擇權抓取失敗（AAPL）：測試")
    env["yf"].error = FetchError("yfinance 抓取失敗（AAPL）：測試")
    r = _refresh(env)
    assert r.status_code == 502 and r.json()["detail"]["stage"] == "fetch"
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 1, 1)


def test_without_yfinance_the_yahoo_failure_is_the_reported_error(env, monkeypatch):
    """production（沒裝 yfinance）：Yahoo 也失敗就到此為止，回報 Yahoo 的原因。"""
    monkeypatch.setattr(yf, "available", lambda: False)
    env["yahoo"].error = FetchError("Yahoo 選擇權抓取失敗（AAPL）：狀態碼 500")
    r = _refresh(env)
    assert r.status_code == 502 and r.json()["detail"]["stage"] == "fetch"
    assert "Yahoo 選擇權抓取失敗" in r.json()["detail"]["message"]
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 1, 0)


def test_a_yahoo_429_is_metered_as_a_429_attempt(env):
    env["yahoo"].error = RateLimitedError("Yahoo 選擇權限流（AAPL）", retry_after_seconds=30)
    assert _refresh(env).status_code == 200            # 退到 yfinance
    m = _metrics(env["storage"])
    assert m.get(("chain_429_count", "yahoo")) == 1
    assert m.get(("chain_fetch_count", "yahoo")) == 1


def test_the_yahoo_attempt_refused_by_the_global_fuse_is_never_sent(env):
    """Cboe 用掉今天最後一次 vendor 預算：Yahoo attempt 被 fuse 擋下、完全不送出，
    也不會被當成 Yahoo 失敗而退到 yfinance。"""
    storage = env["storage"]
    used = storage.metric_total("chain_fetch_count", DAY.isoformat())
    metrics.record(storage, "chain_fetch_count", DAY, count=2000 - 1 - used)
    r = _refresh(env)
    assert r.status_code == 429 and r.json()["detail"]["stage"] == "vendor_budget_exhausted"
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 0, 0)


def test_cboe_success_never_touches_yahoo(env):
    env["cboe"].error = None
    env["cboe"].snap = dataclasses.replace(env["yf"].snap, source="cboe")
    assert _refresh(env).status_code == 200
    assert (env["cboe"].calls, env["yahoo"].calls, env["yf"].calls) == (1, 0, 0)


# ---------- service.fetch_chain（離線／CLI 路徑）同一個順序 ----------

def _snap(source):
    return dataclasses.replace(load_snapshot(FIX), source=source)


def _fail(name):
    def f(symbol):
        raise FetchError(f"{name} down")
    return f


def test_service_fetch_chain_order_is_cboe_then_yahoo_then_yfinance(monkeypatch):
    from option_chaser.data import cboe

    monkeypatch.setattr(cboe, "fetch_chain", _fail("cboe"))
    monkeypatch.setattr(yahoo_options, "fetch_chain", lambda s: _snap("yahoo"))
    monkeypatch.setattr(yf, "fetch_chain", lambda s: pytest.fail("yfinance 不該被呼叫"))
    assert service.fetch_chain("XYZ").source == "yahoo"

    monkeypatch.setattr(yahoo_options, "fetch_chain", _fail("yahoo"))
    monkeypatch.setattr(yf, "fetch_chain", lambda s: _snap("yfinance"))
    assert service.fetch_chain("XYZ").source == "yfinance"

    monkeypatch.setattr(yf, "fetch_chain", _fail("yfinance"))
    with pytest.raises(FetchError):
        service.fetch_chain("XYZ")


# ---------- /api/health 的 opportunity 診斷 ----------

def test_health_reports_no_analyst_source_by_default():
    body = TestClient(create_app(storage=MemoryStorage())).get("/api/health").json()
    assert body["opportunity"] == {"analyst_source": None, "configured": False}


def test_health_reports_the_configured_analyst_source_without_any_network_call():
    class NoCalls:
        def get(self, url):
            raise AssertionError(f"/api/health 不該連外：{url}")

    app = create_app(storage=MemoryStorage(),
                     analyst_source=YahooAnalystSource(transport=NoCalls()))
    body = TestClient(app).get("/api/health").json()
    assert body["opportunity"] == {"analyst_source": "yahoo-udh", "configured": True}


# ---------- V2-01（#404）：「存成劇本」的股權類別代號 ----------

def test_share_class_scenario_is_saved_canonical_and_each_source_gets_its_spelling(
        monkeypatch):
    """劇本建立時 `brk-b` 存成 canonical `BRK.B`；重算時 Cboe 收到 `BRK.B`、Yahoo
    URL 用 `BRK-B`（真實錄下的 BRK-B 第一頁回放），結果掛 `BRK.B`。"""
    monkeypatch.setattr(main_module, "ny_today", lambda: DAY)
    transport = OptionsReplayTransport()
    monkeypatch.setattr(yahoo_options, "fetch_chain",
                        lambda symbol: YahooOptionsClient(transport).fetch_chain(
                            symbol, now=lambda: RECORDED_AT))
    monkeypatch.setattr(yf, "available", lambda: False)
    asked_cboe: list[str] = []

    def cboe(symbol):
        asked_cboe.append(symbol)
        raise FetchError(f"Cboe 抓取失敗（{symbol}）: HTTP 403")

    storage = MemoryStorage()
    client = TestClient(create_app(
        identity_resolver=lambda: "solo", storage=storage, cboe_fetch=cboe,
        rate_loader=_sample_rate_loader, dividend_loader=_sample_dividend_loader))
    sc = client.post("/api/scenarios", json={**SCENARIO, "symbol": "brk-b",
                                             "target_price": 600.0,
                                             "target_month": "2026-11"})
    assert sc.status_code == 201, sc.text
    assert sc.json()["symbol"] == "BRK.B"
    sid = sc.json()["id"]
    r = client.post(f"/api/scenarios/{sid}/refresh")
    assert asked_cboe == ["BRK.B"]
    option_calls = transport.option_calls
    assert option_calls and all("/v7/finance/options/BRK-B?" in u for u in option_calls)
    assert r.status_code == 200, r.text
    saved = storage.latest_result(sid, owner="solo")
    assert saved.view["meta"]["source"] == "yahoo"
    assert saved.view["meta"]["symbol"] == "BRK.B"
