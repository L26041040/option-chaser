"""分析師資料更新：一鍵建立、續跑、重試、429、每日上限、處理中標記（LIVE-T3／#398）。

票面 AC（OPTION-CHASER-LIVE-TICKET-CORRECTION-001 修正後）逐條釘住，全部用假上游
（`ScriptedSource`）＋凍結時鐘（`create_app(clock=)`，`ny_today()` 由
`tests/conftest.py` 凍結在 2026-09-28）：

- 初次建立分多次呼叫完成，不遺漏、不重複；
- **成功**後同一交易日重按不重打上游；
- **失敗**後冷卻內重按不重打、冷卻過後真的重試、重試達上限當日不再試、隔天恢復；
- 429＋`Retry-After: N`：取 N 與冷卻時間較長者；沒有 `Retry-After` 用 429 專用冷卻；
- 重試計入每日上限：已達上限時重試被拒絕（429）並說明原因，不打上游；
- 兩個 SU 同時觸發同一檔只打一次上游；處理中標記逾時後可以重新取得；
- 一檔失敗不影響其他檔；超過每日上限時停止並回報；
- 參數覆寫會改變行為，未設定時用預設值。
"""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api_app import main as main_module
from api_app.analyst_source import ProviderResult
from api_app.consensus_cache import RefreshPolicy
from api_app.main import create_app
from api_app.search_universe import REFRESH_PRIORITY
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import AnalystTargetRecord
from tests._role_session import grant_role

# 每日更新上限固定成 50（`_client` 預設）時，更新母體＝優先更新的 50 檔大型股
#（V2-01／#404：預設範圍改成 S&P 500 後，這些測試只關心更新機制本身）。
SAMPLE = list(REFRESH_PRIORITY)
T0 = 1_790_000_000.0          # 任意固定的 UTC epoch
UPDATE = "/api/opportunity/consensus/update"
STATUS = "/api/opportunity/consensus/status"
CRON = {"Authorization": "Bearer test-secret"}


class Clock:
    def __init__(self, t: float = T0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _ok(symbol: str) -> ProviderResult:
    recs = tuple(AnalystTargetRecord(symbol=symbol, analyst_key=f"F{i}", firm=f"F{i}",
                                     target_price=Decimal(p),
                                     published_on=date(2026, 9, 1))
                 for i, p in enumerate(("110", "115", "120", "125", "130")))
    return ProviderResult(records=recs, coverage="complete")


class ScriptedSource:
    """預設每檔都成功；`script[symbol]` 依序給出結果（用完後成功）。
    `"fail"`＝一般失敗、`("429", N|None)`＝限流、`"raise"`＝丟例外。"""

    name = "scripted"
    is_fixture = False

    def __init__(self, script=None, on_fetch=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[str] = []
        self.on_fetch = on_fetch

    def fetch(self, symbol, today):
        self.calls.append(symbol)
        if self.on_fetch:
            self.on_fetch(symbol)
        steps = self.script.get(symbol)
        step = steps.pop(0) if steps else "ok"
        if step == "ok":
            return _ok(symbol)
        if step == "fail":
            return ProviderResult(coverage="partial", error="上游回應狀態碼 500")
        if step == "raise":
            raise TimeoutError("上游逾時")
        kind, retry_after = step
        assert kind == "429"
        return ProviderResult(coverage="partial", error="Yahoo 限流（分析師資料 429）",
                              rate_limited=True, retry_after=retry_after)


def _client(source, *, clock=None, policy=None, role="superuser", storage=None,
            sleep=None, **kw):
    storage = storage or MemoryStorage()
    if role != "normal":
        grant_role(storage, role, owner_id="solo")
    kw.setdefault("consensus_refresh_symbol_cap", len(SAMPLE))
    app = create_app(identity_resolver=lambda: "solo", storage=storage,
                     analyst_source=source, cron_secret="test-secret",
                     clock=clock or Clock(),
                     consensus_refresh_policy=policy or RefreshPolicy(call_spacing_seconds=0),
                     consensus_refresh_sleep=sleep, **kw)
    return TestClient(app), storage


def _update(client, symbols=None, status=200):
    r = client.post(UPDATE, json={} if symbols is None else {"symbols": symbols})
    assert r.status_code == status, r.text
    return r.json()


def _status(client):
    r = client.get(STATUS)
    assert r.status_code == 200, r.text
    return r.json()


def _sym(body, symbol):
    return next(s for s in body["symbols"] if s["symbol"] == symbol)


def _run_to_end(client, limit=100):
    bodies = []
    body = _update(client)
    bodies.append(body)
    while body["remaining"] and limit:
        body = _update(client)
        bodies.append(body)
        limit -= 1
    return bodies


# ---------- 初次建立：分批、續跑、不遺漏不重複 ----------

def test_initial_build_completes_in_several_small_batches_without_gaps_or_repeats():
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=10))
    first = _update(client)
    assert len(first["processed_symbols"]) == 10
    assert len(first["remaining"]) == 40
    assert first["progress"] == {**first["progress"], "total": 50, "done": 10,
                                 "failed": 0}
    bodies = [first] + _run_to_end(client)[0:]
    assert len(source.calls) == len(set(source.calls)) == 50
    assert set(source.calls) == set(SAMPLE)
    last = bodies[-1]
    assert last["remaining"] == []
    assert last["progress"]["done"] == 50
    assert last["upstream_calls_today"] == 50


def test_update_batch_size_defaults_to_ten():
    source = ScriptedSource()
    client, _ = _client(source)
    assert len(_update(client)["processed_symbols"]) == 10


def test_success_then_pressing_again_the_same_day_does_not_call_upstream():
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    _update(client)
    assert len(source.calls) == 50
    again = _update(client)
    assert len(source.calls) == 50
    assert again["processed_symbols"] == [] and again["remaining"] == []
    # 明確指定某檔也一樣不打：它今天已經成功。
    r = client.post(UPDATE, json={"symbols": ["AAPL"]})
    assert r.status_code == 409
    assert r.json()["detail"]["stage"] == "consensus_not_retryable"
    assert len(source.calls) == 50


def test_next_trading_day_fetches_again(monkeypatch):
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    _update(client)
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 29))
    _update(client)
    assert len(source.calls) == 100



def test_friday_success_is_not_refetched_over_the_weekend(monkeypatch):
    # 「同一交易日不再抓」：週五成功，週六、週日仍屬週五這個交易日；週一才重抓。
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 25))   # 週五
    _update(client)
    assert len(source.calls) == 50
    for weekend in (date(2026, 9, 26), date(2026, 9, 27)):
        monkeypatch.setattr(main_module, "ny_today", lambda d=weekend: d)
        body = _update(client)
        assert body["processed_symbols"] == []
        assert _sym(_status(client), "AAPL")["state"] == "done"
        assert client.get("/api/cron/consensus-refresh", headers=CRON).json()["processed"] == 0
    assert len(source.calls) == 50
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 28))   # 週一
    _update(client)
    assert len(source.calls) == 100


def test_retries_used_up_on_friday_resume_on_monday_not_saturday(monkeypatch):
    clock = Clock()
    source = ScriptedSource({"AAPL": ["fail"] * 10})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50,
                                             max_retries=0))
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 25))   # 週五
    _update(client)
    aapl = _sym(_status(client), "AAPL")
    assert aapl["state"] == "exhausted"
    assert aapl["next_retry_at"] == "2026-09-28T04:00:00+00:00"   # 下一個交易日（週一）零時
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 26))   # 週六
    assert _sym(_status(client), "AAPL")["state"] == "exhausted"
    assert client.post(UPDATE, json={"symbols": ["AAPL"]}).status_code == 409
    assert source.calls.count("AAPL") == 1
    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 28))   # 週一
    _update(client, ["AAPL"])
    assert source.calls.count("AAPL") == 2

# ---------- 失敗：冷卻、重試、上限、隔天恢復 ----------

def test_failure_cooldown_retry_limit_and_next_day(monkeypatch):
    clock = Clock()
    source = ScriptedSource({"AAPL": ["fail"] * 10})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    _update(client)                                     # 第 1 次（失敗）
    assert source.calls.count("AAPL") == 1
    aapl = _sym(_status(client), "AAPL")
    assert aapl["state"] == "cooling"
    assert aapl["error"] == "上游回應狀態碼 500"
    assert aapl["retries_today"] == 0
    assert aapl["retryable_now"] is False

    clock.t += 899                                      # 冷卻內：不打
    _update(client)
    r = client.post(UPDATE, json={"symbols": ["AAPL"]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["stage"] == "consensus_not_retryable"
    assert detail["next_retry_at"] == aapl["next_retry_at"]
    assert source.calls.count("AAPL") == 1

    for n in (2, 3, 4):                                 # 冷卻過後真的重試，共 3 次重試
        clock.t += 901
        body = _update(client, ["AAPL"])
        assert body["processed_symbols"] == ["AAPL"]
        assert source.calls.count("AAPL") == n
    aapl = _sym(_status(client), "AAPL")
    assert aapl["state"] == "exhausted"
    assert aapl["retries_today"] == 3
    assert aapl["next_retry_at"] == "2026-09-29T04:00:00+00:00"   # 下一個美東日零時

    clock.t += 3 * 3600                                 # 用完了：當天再久也不試
    _update(client)
    assert client.post(UPDATE, json={"symbols": ["AAPL"]}).status_code == 409
    assert source.calls.count("AAPL") == 4

    monkeypatch.setattr(main_module, "ny_today", lambda: date(2026, 9, 29))
    _update(client, ["AAPL"])                           # 隔天恢復
    assert source.calls.count("AAPL") == 5


def test_one_failure_does_not_affect_the_others_and_is_recorded():
    source = ScriptedSource({"MSFT": ["raise"]})
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    body = _update(client)
    assert body["succeeded"] == 49 and body["failed"] == 1
    status = _status(client)
    assert _sym(status, "MSFT")["error"] == "資料來源丟出例外：上游逾時"
    assert _sym(status, "AAPL")["state"] == "done"
    assert status["progress"]["done"] == 49
    assert status["progress"]["failed"] == 1


# ---------- 429 ----------

@pytest.mark.parametrize("retry_after,blocked,allowed", [
    (3600, 3599, 3601),      # Retry-After 比冷卻長：照 Retry-After
    (60, 899, 901),          # Retry-After 比冷卻短：照冷卻（15 分）
    (None, 1799, 1801),      # 沒有 Retry-After：429 專用冷卻（30 分）
])
def test_429_honours_retry_after_or_the_429_cooldown(retry_after, blocked, allowed):
    clock = Clock()
    source = ScriptedSource({"AAPL": [("429", retry_after)]})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    _update(client)
    clock.t = T0 + blocked
    assert client.post(UPDATE, json={"symbols": ["AAPL"]}).status_code == 409
    assert source.calls.count("AAPL") == 1
    clock.t = T0 + allowed
    _update(client, ["AAPL"])
    assert source.calls.count("AAPL") == 2



def _iso(epoch):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()


def test_429_stops_the_run_at_once_and_pauses_every_later_call():
    # 「遇到 429：有 Retry-After 就遵守，沒有就冷卻 30 分鐘」——對整個來源，
    # 不是只對那一檔：同一次呼叫立刻停，後面的不再打上游。
    clock = Clock()
    third = sorted(SAMPLE)[2]
    source = ScriptedSource({third: [("429", None)]})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    body = _update(client)
    assert len(source.calls) == 3 and source.calls[-1] == third
    assert body["succeeded"] == 2 and body["failed"] == 1
    assert body["stopped_reason"] == "rate_limited"
    assert body["rate_limited_until"] == _iso(T0 + 1800)
    assert "429" in body["message"]
    assert len(body["remaining"]) == 47 and third not in body["remaining"]

    clock.t = T0 + 1799                                # 冷卻中：續跑、cron、重試都不打上游
    again = _update(client)
    assert again["processed_symbols"] == [] and again["stopped_reason"] == "rate_limited"
    assert again["rate_limited_until"] == _iso(T0 + 1800)
    assert len(again["remaining"]) == 47
    cron = client.get("/api/cron/consensus-refresh", headers=CRON).json()
    assert cron["processed"] == 0 and cron["stopped_reason"] == "rate_limited"
    r = client.post(UPDATE, json={"symbols": [body["remaining"][0]]})
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "consensus_rate_limited"
    assert r.json()["detail"]["rate_limited_until"] == _iso(T0 + 1800)
    assert _status(client)["rate_limited_until"] == _iso(T0 + 1800)
    assert len(source.calls) == 3

    clock.t = T0 + 1801                                # 冷卻結束：照常續跑
    resumed = _update(client)
    assert resumed["stopped_reason"] is None and resumed["rate_limited_until"] is None
    assert len(source.calls) == 3 + 48
    assert _status(client)["rate_limited_until"] is None


def test_source_wide_429_pause_honours_a_longer_retry_after():
    clock = Clock()
    first = sorted(SAMPLE)[0]
    source = ScriptedSource({first: [("429", 3600)]})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    body = _update(client)
    assert source.calls == [first]
    assert body["rate_limited_until"] == _iso(T0 + 3600)
    clock.t = T0 + 3599
    _update(client)
    assert len(source.calls) == 1
    clock.t = T0 + 3601                                # 其餘 49 檔＋冷卻已過的那一檔
    _update(client)
    assert len(source.calls) == 51

# ---------- 每日上限 ----------

def test_daily_cap_stops_the_build_and_rejects_retries_without_calling_upstream():
    clock = Clock()
    source = ScriptedSource({"AAPL": ["fail"]})
    client, _ = _client(source, clock=clock,
                        policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50,
                                             daily_upstream_cap=3))
    body = _update(client)
    assert len(source.calls) == 3
    assert body["stopped_reason"] == "daily_cap"
    assert "每日" in body["message"]
    assert len(body["remaining"]) == 47
    assert body["upstream_calls_today"] == 3 and body["daily_cap"] == 3

    clock.t += 901                                      # AAPL 冷卻已過，但上限已滿
    r = client.post(UPDATE, json={"symbols": ["AAPL"]})
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "consensus_daily_cap"
    assert len(source.calls) == 3
    again = _update(client)
    assert again["stopped_reason"] == "daily_cap" and again["processed_symbols"] == []
    assert len(source.calls) == 3


# ---------- 處理中標記 ----------

def test_two_concurrent_triggers_for_the_same_symbol_call_upstream_once():
    entered, release = threading.Event(), threading.Event()

    def block(symbol):
        entered.set()
        assert release.wait(10)

    source = ScriptedSource(on_fetch=block)
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0))
    results = {}
    worker = threading.Thread(
        target=lambda: results.update(a=client.post(UPDATE, json={"symbols": ["AAPL"]})))
    worker.start()
    assert entered.wait(10)
    source.on_fetch = None
    second = client.post(UPDATE, json={"symbols": ["AAPL"]})   # 另一位 SU 同時按
    assert second.status_code == 409
    assert second.json()["detail"]["state"] == "in_progress"
    assert _sym(_status(client), "AAPL")["state"] == "in_progress"
    release.set()
    worker.join(10)
    assert results["a"].status_code == 200
    assert source.calls == ["AAPL"]
    # 第一位做完之後，第三次也不重打（今天已成功）。
    assert client.post(UPDATE, json={"symbols": ["AAPL"]}).status_code == 409
    assert source.calls == ["AAPL"]


def test_an_abandoned_in_progress_marker_can_be_taken_after_it_expires():
    clock = Clock()
    source = ScriptedSource()
    client, storage = _client(source, clock=clock,
                              policy=RefreshPolicy(call_spacing_seconds=0, lease_seconds=120))
    # 某次函式抓到一半被砍：標記留著、沒釋放。
    assert storage.acquire_consensus_refresh_lease("AAPL", "crashed", now=T0,
                                                   ttl_seconds=120)
    assert client.post(UPDATE, json={"symbols": ["AAPL"]}).status_code == 409
    assert source.calls == []
    clock.t += 120
    _update(client, ["AAPL"])
    assert source.calls == ["AAPL"]


# ---------- 參數：可覆寫、有預設 ----------

def test_policy_defaults_are_reported():
    client, _ = _client(ScriptedSource(), policy=RefreshPolicy())
    assert _status(client)["policy"] == {
        "max_retries": 3, "retry_cooldown_seconds": 900,
        "rate_limit_cooldown_seconds": 1800, "daily_upstream_cap": 900,
        "lease_seconds": 120, "call_spacing_seconds": 1.0, "batch_size": 10}


def test_policy_overrides_change_behaviour():
    clock = Clock()
    source = ScriptedSource({"AAPL": ["fail", "fail", ("429", None), "ok"]})
    client, _ = _client(source, clock=clock, policy=RefreshPolicy(
        max_retries=1, retry_cooldown_seconds=60, rate_limit_cooldown_seconds=120,
        daily_upstream_cap=60, call_spacing_seconds=0, batch_size=50))
    _update(client)
    clock.t += 61                                       # 冷卻 60 秒
    _update(client, ["AAPL"])
    assert source.calls.count("AAPL") == 2
    assert _sym(_status(client), "AAPL")["state"] == "exhausted"   # 只准重試 1 次
    assert _status(client)["daily_cap"] == 60


def test_policy_comes_from_environment_when_not_injected(monkeypatch):
    monkeypatch.setenv("CONSENSUS_MAX_RETRIES", "1")
    monkeypatch.setenv("CONSENSUS_RETRY_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("CONSENSUS_RATE_LIMIT_COOLDOWN_SECONDS", "120")
    monkeypatch.setenv("CONSENSUS_DAILY_UPSTREAM_CAP", "70")
    monkeypatch.setenv("CONSENSUS_CALL_SPACING_SECONDS", "0")
    monkeypatch.setenv("CONSENSUS_REFRESH_BATCH_SIZE", "nope")     # 打錯：用預設
    storage = MemoryStorage()
    grant_role(storage, "superuser", owner_id="solo")
    client = TestClient(create_app(identity_resolver=lambda: "solo", storage=storage,
                                   analyst_source=ScriptedSource()))
    assert _status(client)["policy"] == {
        "max_retries": 1, "retry_cooldown_seconds": 60,
        "rate_limit_cooldown_seconds": 120, "daily_upstream_cap": 70,
        "lease_seconds": 120, "call_spacing_seconds": 0.0, "batch_size": 10}


def test_calls_are_spaced_by_the_configured_interval():
    sleeps: list[float] = []
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=1.5, batch_size=3),
                        sleep=sleeps.append)
    _update(client)
    assert len(source.calls) == 3
    assert sleeps == [1.5, 1.5]          # 第一次之前不等


def test_fixture_sources_have_no_upstream_so_they_are_not_spaced():
    sleeps: list[float] = []
    source = ScriptedSource()
    source.is_fixture = True
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=1.5, batch_size=3),
                        sleep=sleeps.append)
    _update(client)
    assert len(source.calls) == 3 and sleeps == []


# ---------- cron 共用同一套核心 ----------

def test_cron_obeys_the_same_retry_rules():
    clock = Clock()
    source = ScriptedSource({"AAPL": ["fail", "fail"]})
    client, _ = _client(source, clock=clock)
    assert client.get("/api/cron/consensus-refresh", headers=CRON).json()["remaining"] == []
    client.get("/api/cron/consensus-refresh", headers=CRON)
    assert source.calls.count("AAPL") == 1               # 冷卻內 cron 也不重打
    clock.t += 901
    client.get("/api/cron/consensus-refresh", headers=CRON)
    assert source.calls.count("AAPL") == 2
    assert len(source.calls) == 51
    assert _status(client)["upstream_calls_today"] == 51


# ---------- 狀態 API ----------

def test_status_reports_each_symbol_and_the_overall_progress():
    clock = Clock()
    source = ScriptedSource({"ABBV": ["fail"]})  # 同為從沒試過時依代號排序：第 2 檔
    client, _ = _client(source, clock=clock, policy=RefreshPolicy(call_spacing_seconds=0))
    before = _status(client)
    assert before["source"] == {"configured": True, "name": "scripted", "is_fixture": False}
    assert before["progress"] == {"total": 50, "done": 0, "failed": 0, "pending": 50,
                                  "in_progress": 0}
    assert _sym(before, "AAPL") == {
        "symbol": "AAPL", "state": "pending", "last_success_at": None,
        "last_attempt_at": None, "error": None, "retries_today": 0,
        "next_retry_at": None, "retryable_now": True, "as_of": None}
    _update(client)
    after = _status(client)
    aapl, msft = _sym(after, "AAPL"), _sym(after, "ABBV")
    assert aapl["state"] == "done" and aapl["as_of"] == "2026-09-28"
    assert aapl["last_success_at"] == aapl["last_attempt_at"] == "2026-09-21T14:13:20+00:00"
    assert aapl["retryable_now"] is False
    assert msft["state"] == "cooling" and msft["last_success_at"] is None
    assert msft["next_retry_at"] == "2026-09-21T14:28:20+00:00"
    assert after["data_as_of"] == "2026-09-28"
    assert after["today"] == "2026-09-28"
    assert after["upstream_calls_today"] == 10


# ---------- 權限與未設定 ----------

def test_normal_user_cannot_update_or_read_status():
    client, _ = _client(ScriptedSource(), role="normal")
    assert client.post(UPDATE, json={}).status_code == 403
    assert client.get(STATUS).status_code == 403


@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_superuser_and_superadmin_can_update(role):
    client, _ = _client(ScriptedSource(), role=role)
    assert client.post(UPDATE, json={}).status_code == 200


def test_unconfigured_source_refuses_update_and_status_says_so():
    client, _ = _client(None)
    r = client.post(UPDATE, json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "尚未設定分析師資料來源"
    body = _status(client)
    assert body["source"]["configured"] is False and body["symbols"] == []


def test_retry_symbol_outside_the_update_universe_is_400():
    source = ScriptedSource()
    client, _ = _client(source)
    assert client.post(UPDATE, json={"symbols": ["ZZZZ"]}).status_code == 400
    assert source.calls == []



def test_retry_symbols_are_normalised_before_the_universe_check():
    source = ScriptedSource()
    client, _ = _client(source)
    body = _update(client, [" aapl ", "AAPL"])
    assert body["processed_symbols"] == ["AAPL"]
    assert source.calls == ["AAPL"]


def test_409_names_every_symbol_that_cannot_be_retried():
    source = ScriptedSource()
    client, _ = _client(source, policy=RefreshPolicy(call_spacing_seconds=0, batch_size=50))
    _update(client)                                     # 全部今天已成功
    r = client.post(UPDATE, json={"symbols": ["AAPL", "MSFT"]})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["symbol"] == "AAPL" and detail["state"] == "done"   # 舊欄位不變
    assert [s["symbol"] for s in detail["skipped"]] == ["AAPL", "MSFT"]
    assert {s["state"] for s in detail["skipped"]} == {"done"}
    assert "AAPL" in detail["message"] and "MSFT" in detail["message"]

# ---------- 契約樣本 ----------

def test_update_and_status_samples_match_the_live_responses():
    """`contracts/` 兩份樣本＝現在的真實回應（前端 mock 直接載入它們）。改了
    回應形狀就重跑 `scripts/gen_opportunity_consensus_update_sample.py`。"""
    import json
    from pathlib import Path

    from scripts.gen_opportunity_consensus_update_sample import (STATUS_OUT, UPDATE_OUT,
                                                                 build_samples)
    update, status = build_samples()
    assert json.loads(Path(UPDATE_OUT).read_text(encoding="utf-8")) == update
    assert json.loads(Path(STATUS_OUT).read_text(encoding="utf-8")) == status
    assert {"done", "cooling", "pending"} <= {s["state"] for s in status["symbols"]}
