"""SCALE-05（#260，Scaling Foundation Cboe 429 韌性：使用者可見狀態）：
把 SCALE-04（#255）建好的 provider-global backoff 控制狀態，以結構化、
可測試、向後相容的方式揭露給使用者——不得靠解析 message 字串推回限流
狀態（AC-2）。

## AC 對照

- AC-1：`test_ac1_existing_non_rate_limited_failure_details_are_unchanged`
- AC-2：`test_rate_limited_metadata_is_structured_not_embedded_in_message`
- AC-6：`test_is_sustained_incident_*`（純函式 boundary tests）＋
  `test_single_and_batch_refresh_endpoints_agree_on_rate_limited_classification`
  （唯一 canonical 分類點，不在兩個端點各自硬編碼一次）
- AC-7：既有的 `test_every_failure_stage_the_backend_emits_is_one_
  the_frontend_knows`（`tests/test_frontend_contract.py`）用正則掃描
  `_fail(...)` 呼叫與 `src/api.ts` 的 `STAGES` 宣告，自動涵蓋新增的
  `"rate_limited"`——不必新開一條專屬測試，這裡只補後端字彙本身

前端（countdown／disable／sustained incident 文案）測試在 Vitest／
Playwright，不在這個檔案裡。
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api_app import chain_backoff
from api_app.main import create_app
from api_app.storage import ChainBackoffEntry
from api_app.storage.memory import MemoryStorage
from option_chaser.data import cboe, yf
from option_chaser.models import FetchError, RateLimitedError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ---------- AC-6：is_sustained_incident 純函式 boundary tests ----------

def test_is_sustained_incident_below_threshold_is_false():
    assert chain_backoff.is_sustained_incident(
        chain_backoff.INCIDENT_THRESHOLD_FAILURES - 1) is False


def test_is_sustained_incident_at_threshold_is_true():
    assert chain_backoff.is_sustained_incident(
        chain_backoff.INCIDENT_THRESHOLD_FAILURES) is True


def test_is_sustained_incident_above_threshold_is_true():
    assert chain_backoff.is_sustained_incident(
        chain_backoff.INCIDENT_THRESHOLD_FAILURES + 5) is True


def test_is_sustained_incident_zero_is_false():
    assert chain_backoff.is_sustained_incident(0) is False


# ---------- chain_backoff.status()：canonical 使用者可見投影 ----------

def test_status_returns_none_when_no_entry_exists():
    storage = MemoryStorage()
    assert chain_backoff.status(storage, "cboe") is None


def test_status_returns_none_when_window_has_expired():
    storage = MemoryStorage()
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe",
        blocked_until=_iso(_now() - timedelta(seconds=5)),
        retry_after_seconds=30.0, consecutive_failures=1,
        observed_at=_iso(_now() - timedelta(seconds=35)),
        last_success_at=None))
    assert chain_backoff.status(storage, "cboe") is None


def test_status_returns_full_metadata_when_currently_blocked():
    storage = MemoryStorage()
    blocked_until = _now() + timedelta(seconds=42)
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(blocked_until),
        retry_after_seconds=45.0, consecutive_failures=1,
        observed_at=_iso(_now()), last_success_at="2026-09-01T00:00:00+00:00"))

    result = chain_backoff.status(storage, "cboe")

    assert result is not None
    assert result["blocked_until"] == _iso(blocked_until)
    assert result["retry_after_seconds"] == 45.0
    assert result["last_success_at"] == "2026-09-01T00:00:00+00:00"
    assert result["incident"] is False
    # 剩餘秒數是即時計算的，允許測試執行耗時的些微誤差（比照既有
    # test_parse_retry_after_http_date 的容忍窗手法）。
    assert 35 <= result["remaining_seconds"] <= 42


def test_status_incident_flag_reflects_is_sustained_incident():
    storage = MemoryStorage()
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(_now() + timedelta(seconds=60)),
        retry_after_seconds=None,
        consecutive_failures=chain_backoff.INCIDENT_THRESHOLD_FAILURES,
        observed_at=_iso(_now()), last_success_at=None))

    result = chain_backoff.status(storage, "cboe")

    assert result is not None
    assert result["incident"] is True


def test_status_retry_after_seconds_can_be_none():
    """Cboe 沒給（或給的值解析不出來）`Retry-After` 時，`retry_after_
    seconds` 誠實回 `None`——不得因此整個 `status()` 都不回。"""
    storage = MemoryStorage()
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(_now() + timedelta(seconds=60)),
        retry_after_seconds=None, consecutive_failures=1,
        observed_at=_iso(_now()), last_success_at=None))

    result = chain_backoff.status(storage, "cboe")

    assert result is not None
    assert result["retry_after_seconds"] is None
    assert result["blocked_until"] is not None


def test_status_is_fail_open_when_storage_read_raises():
    class _BrokenStorage(MemoryStorage):
        def get_chain_backoff(self, source: str):  # noqa: D401
            raise RuntimeError("storage 掛了")

    assert chain_backoff.status(_BrokenStorage(), "cboe") is None


def test_status_a_successful_fetch_clears_visible_state(monkeypatch):
    """AC-5（Regression Red Line 的鏡像）：backoff 視窗過期後、下一次
    真正打上游成功，`status()` 要跟著看不到限流——這是既有
    `backoff_aware_fetch()` 成功清除狀態（SCALE-04）之後，SCALE-05
    這一層新增的可見度是否忠實反映底層狀態的直接證明。用假時鐘控制
    「視窗過期」這個時刻，避免依賴真實 sleep 造成測試變慢或脆弱。"""
    fake_now = _now()
    monkeypatch.setattr(chain_backoff, "_now", lambda: fake_now)

    storage = MemoryStorage()
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(fake_now + timedelta(seconds=30)),
        retry_after_seconds=60.0, consecutive_failures=2,
        observed_at=_iso(fake_now), last_success_at=None))
    assert chain_backoff.status(storage, "cboe") is not None

    # 時間走到視窗過期之後——`backoff_aware_fetch()` 不再短路，真的
    # 呼叫 `underlying`；這次成功，狀態應被清除。
    fake_now = fake_now + timedelta(seconds=31)
    monkeypatch.setattr(chain_backoff, "_now", lambda: fake_now)

    chain_backoff.backoff_aware_fetch(
        storage, "cboe", lambda symbol: _fake_snapshot(symbol), "TLT")

    assert chain_backoff.status(storage, "cboe") is None


def _fake_snapshot(symbol: str):
    from option_chaser.data.snapshot import load_snapshot
    return dataclasses.replace(
        load_snapshot("tests/fixtures/xyz_v4_six_expiries.json"), symbol=symbol)


# ---------- HTTP 層：`create_app()` 端到端 ----------

def _client(storage=None, **overrides) -> TestClient:
    """刻意不傳 `fetch=`——`_default_fetch()` 才會真的接上
    `chain_backoff`，比照 SCALE-04 既有 `_client_without_fetch_
    override()` 手法。"""
    return TestClient(create_app(storage=storage or MemoryStorage(), **overrides))


def _create_scenario(client: TestClient, symbol: str = "TLT") -> dict:
    r = client.post("/api/scenarios", json={
        "symbol": symbol, "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]})
    assert r.status_code == 201, r.text
    return r.json()


def _seed_blocked(storage: MemoryStorage, *, consecutive_failures: int = 1,
                  retry_after_seconds: float | None = 45.0,
                  last_success_at: str | None = None) -> None:
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(_now() + timedelta(seconds=90)),
        retry_after_seconds=retry_after_seconds,
        consecutive_failures=consecutive_failures,
        observed_at=_iso(_now()), last_success_at=last_success_at))


def _fail_both_vendors(monkeypatch) -> None:
    """cboe 與 yfinance 都失敗——backoff 短路本身就已經是零 vendor
    call，這裡監測 cboe 若被呼叫（不該發生，backoff 視窗內就短路了）
    直接炸掉測試，yfinance 則老實回一個 FetchError（比照
    `option_chaser/data/yf.py::fetch_chain` 對任何底層失敗的既有
    收斂行為）。"""
    def _cboe_landmine(symbol: str):
        raise AssertionError(
            "backoff 視窗內不該真的打 Cboe——這代表短路失效了")

    def _yf_fails(symbol: str):
        raise FetchError(f"yfinance 抓取失敗（{symbol}）：測試假體")

    monkeypatch.setattr(cboe, "fetch_chain", _cboe_landmine)
    monkeypatch.setattr(yf, "fetch_chain", _yf_fails)


def test_ac1_fail_helpers_existing_call_shape_is_byte_identical_without_extra():
    """AC-1：`_fail()` 既有三個呼叫端（`params`／`analyze`／
    `archived`）從未傳入 `**extra`，`detail` 因此逐位元等於改動前的
    `{stage, message}` 兩鍵字典——直接單元測試 `_fail()` 本身，避免
    依賴脆弱的 HTTP 路徑才能踩到某個特定分層。"""
    from api_app.main import _fail

    for stage in ("params", "analyze", "archived"):
        exc = _fail(stage, 400, "測試訊息")
        assert exc.detail == {"stage": stage, "message": "測試訊息"}


def test_ac1_archived_refresh_failure_detail_shape_is_unchanged():
    """既有全端到端案例：垃圾桶劇本刷新失敗仍是純 `{stage, message}`，
    不受本票新增 `**extra` 能力影響（呼叫端沒傳就不會出現）。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc = _create_scenario(c)
    ar = c.post(f"/api/scenarios/{sc['id']}/archive")
    assert ar.status_code == 200, ar.text

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 409
    assert set(r.json()["detail"].keys()) == {"stage", "message"}
    assert r.json()["detail"]["stage"] == "archived"


def test_ac1_ordinary_fetch_failure_without_any_backoff_state_is_unchanged(
    monkeypatch,
):
    """一般 fetch 失敗（沒有任何 backoff 狀態）：`detail` 仍只有
    `{stage, message}`，新增能力不會滲透進沒有觸發限流分類的路徑。"""
    def _both_fail(symbol: str):
        raise FetchError(f"抓不到 {symbol}：測試假體")

    monkeypatch.setattr(cboe, "fetch_chain", _both_fail)
    monkeypatch.setattr(yf, "fetch_chain", _both_fail)

    storage = MemoryStorage()
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 502
    assert set(r.json()["detail"].keys()) == {"stage", "message"}
    assert r.json()["detail"]["stage"] == "fetch"


def test_rate_limited_metadata_is_structured_not_embedded_in_message(monkeypatch):
    """AC-2＋核心行為：backoff 視窗內、雙來源皆失敗時，單一劇本刷新
    回 429，`stage="rate_limited"`，且全部必要事實都是獨立的結構化
    欄位——不必解析 `message` 字串就能拿到 `blocked_until`。"""
    _fail_both_vendors(monkeypatch)
    storage = MemoryStorage()
    _seed_blocked(storage, consecutive_failures=1,
                 last_success_at="2026-09-01T00:00:00+00:00")
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["stage"] == "rate_limited"
    assert isinstance(detail["message"], str) and detail["message"]
    assert detail["blocked_until"] is not None
    assert detail["retry_after_seconds"] == 45.0
    assert isinstance(detail["remaining_seconds"], (int, float))
    assert detail["remaining_seconds"] > 0
    assert detail["last_success_at"] == "2026-09-01T00:00:00+00:00"
    assert detail["incident"] is False


def test_incident_flag_true_when_consecutive_failures_reach_threshold(monkeypatch):
    _fail_both_vendors(monkeypatch)
    storage = MemoryStorage()
    _seed_blocked(storage,
                 consecutive_failures=chain_backoff.INCIDENT_THRESHOLD_FAILURES)
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 429
    assert r.json()["detail"]["incident"] is True


def test_refresh_run_batch_surfaces_rate_limited_stage_with_metadata(monkeypatch):
    """批次端點（`refresh-run`）走的是自己的 group-level 抓鏈路徑
    （與單一劇本刷新經 `_analyze()` 不同函式），必須套用同一份分類
    判準——不是各自硬編碼一次。"""
    _fail_both_vendors(monkeypatch)
    storage = MemoryStorage()
    _seed_blocked(storage, consecutive_failures=2)
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sc["id"]]})

    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 1
    entry = results[0]
    assert entry["ok"] is False
    assert entry["stage"] == "rate_limited"
    assert entry["blocked_until"] is not None
    assert entry["retry_after_seconds"] == 45.0
    assert entry["remaining_seconds"] > 0
    assert entry["incident"] is False


def test_single_and_batch_refresh_endpoints_agree_on_rate_limited_classification(
    monkeypatch,
):
    """AC-6：兩個端點對同一個 backoff 狀態必須給出完全一致的分類
    （stage 與全部 metadata 鍵集合），證明分類判準只有一份、不是兩處
    各自維護一份可能漂移的邏輯。"""
    _fail_both_vendors(monkeypatch)
    storage = MemoryStorage()
    _seed_blocked(storage, consecutive_failures=1)
    c = _client(storage)
    sc_single = _create_scenario(c, "AAA")
    sc_batch = _create_scenario(c, "BBB")

    r_single = c.post(f"/api/scenarios/{sc_single['id']}/refresh")
    r_batch = c.post("/api/scenarios/refresh-run",
                     json={"scenario_ids": [sc_batch["id"]]})

    single_detail = r_single.json()["detail"]
    batch_detail = r_batch.json()["results"][0]
    assert single_detail["stage"] == batch_detail["stage"] == "rate_limited"
    single_keys = set(single_detail.keys()) - {"message"}
    batch_keys = set(batch_detail.keys()) - {"message", "scenario_id", "ok"}
    assert single_keys == batch_keys
    for key in single_keys - {"stage", "remaining_seconds"}:
        assert single_detail[key] == batch_detail[key]
    # `remaining_seconds` 是即時計算的（`chain_backoff.status()` 每次
    # 呼叫都重新算一次「現在」），兩次呼叫之間隔著一次真實 HTTP 往返，
    # 容許 ±1 秒誤差——這條測試要證明的是「兩處算法一致」，不是「兩次
    # 呼叫剛好落在同一整秒」。
    assert abs(single_detail["remaining_seconds"]
              - batch_detail["remaining_seconds"]) <= 1


def test_not_currently_blocked_falls_through_to_ordinary_fetch_stage(monkeypatch):
    """AC-1 的另一面：backoff entry 存在過（例如已經清除，或視窗已過
    期），但目前並未封鎖——一般 fetch 失敗，不得誤標成 rate_limited。"""
    def _both_fail(symbol: str):
        raise FetchError(f"抓不到 {symbol}：測試假體")

    monkeypatch.setattr(cboe, "fetch_chain", _both_fail)
    monkeypatch.setattr(yf, "fetch_chain", _both_fail)

    storage = MemoryStorage()
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=_iso(_now() - timedelta(seconds=10)),
        retry_after_seconds=30.0, consecutive_failures=1,
        observed_at=_iso(_now() - timedelta(seconds=40)),
        last_success_at=None))
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 502
    assert r.json()["detail"]["stage"] == "fetch"


def test_a_genuine_429_this_request_is_classified_as_rate_limited_even_without_a_preexisting_entry(
    monkeypatch,
):
    """沒有預先存在的 backoff entry（第一次就撞見 429），cboe 429 讓
    entry 被寫入之後、yfinance 備援也失敗——這次請求本身仍要被分類成
    rate_limited，不是「剛好還沒建立過 backoff 狀態」就退回一般 fetch
    失敗。"""
    def _cboe_429(symbol: str):
        raise RateLimitedError("429", retry_after_seconds=20.0)

    def _yf_fails(symbol: str):
        raise FetchError(f"yfinance 抓取失敗（{symbol}）：測試假體")

    monkeypatch.setattr(cboe, "fetch_chain", _cboe_429)
    monkeypatch.setattr(yf, "fetch_chain", _yf_fails)

    storage = MemoryStorage()
    c = _client(storage)
    sc = _create_scenario(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["stage"] == "rate_limited"
    assert detail["retry_after_seconds"] == 20.0
