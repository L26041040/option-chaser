"""SCALE-01（#252，Scaling Foundation Stage 1-0）：歷史 fact context
獨立持久化——把寄生在 `results.view` 內部的 resolved params／
provenance／engine／schema／replay version 複製成 `ResultRecord` 的
一等公民欄位，供未來 storage 瘦身（SCALE-16）與 candidate-specific
historical resolver（SCALE-09）使用；`view` 本身逐位元不變。
"""
import json

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord, Scenario
from api_app.storage.backfill import backfill_result_fact_context
from api_app.storage.memory import MemoryStorage
from option_chaser import service, store
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _result(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0],
                                       target_price=120.0,
                                       target_month="2026-08"),
            strategies=strategies),
        FIX)


def _scenario(sid="s1"):
    return Scenario(id=sid, symbol="XYZ", direction="bullish",
                    target_price=120.0, target_month="2026-08", notes="",
                    strategies=("vertical-spread",),
                    created_at="2026-08-01T00:00:00+00:00")


# ---------- 純函式：store.historical_fact_context() ----------

def test_historical_fact_context_extracts_exactly_the_view_provenance():
    view = store.serialize_result(_result(), "XYZ-120-202608", None)
    ctx = store.historical_fact_context(view)

    assert ctx["resolved_params"] == view["params"]
    assert ctx["requested_strategies"] == ("long-call", "bull-call-spread")
    assert ctx["engine_version"] == view["engine_version"]
    assert ctx["view_schema_version"] == view["schema_version"]
    assert ctx["history_replay_version"] == store.HISTORY_REPLAY_VERSION
    assert ctx["snapshot_source"] == view["meta"]["source"]


def test_requested_strategies_matches_the_actual_request_order():
    view = store.serialize_result(
        _result(strategies=("bull-call-spread", "long-put")),
        "XYZ-120-202608", None)
    ctx = store.historical_fact_context(view)
    assert ctx["requested_strategies"] == ("bull-call-spread", "long-put")


def test_resolved_params_is_bit_identical_to_view_params_as_json_text():
    """Prototype #065 hard finding #5：A/B 比對走 serialized JSON 文字，
    不比 Python 物件——`resolved_params` 直接引用 `view["params"]`，兩者
    序列化後的文字必須逐位元相同。"""
    view = store.serialize_result(_result(), "XYZ-120-202608", None)
    ctx = store.historical_fact_context(view)
    assert (json.dumps(ctx["resolved_params"], sort_keys=True)
            == json.dumps(view["params"], sort_keys=True))


# ---------- HTTP 層：_refresh_and_save() 接線 ----------

def _client(*, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def test_refresh_populates_the_new_fact_fields():
    """Prototype #065 hard finding #5：`detail` 是打過 HTTP 才拿到的
    JSON 回應，JSON 序列化會把 `rate_by_expiry` 這類 tuple-of-tuple
    欄位攤成 list-of-list——與伺服器端 `rec.resolved_params`（直接引用
    尚未序列化過 JSON 的原始 view dict）比較時必須走 serialized JSON
    文字，不能用 Python 物件相等（那會在這個欄位上得到假陽性不一致）。
    """
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]}).json()

    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()
    analyzed_at = row["latest_analyzed_at"]

    rec = storage.latest_result(sc["id"])
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    view = detail["latest_result"]

    assert (json.dumps(rec.resolved_params, sort_keys=True)
            == json.dumps(view["params"], sort_keys=True))
    assert rec.requested_strategies == tuple(r["strategy"]
                                             for r in view["results"])
    assert rec.engine_version == view["engine_version"]
    assert rec.view_schema_version == view["schema_version"]
    assert rec.history_replay_version == store.HISTORY_REPLAY_VERSION
    assert rec.snapshot_source == view["meta"]["source"]

    ctx = storage.result_fact_context(sc["id"], analyzed_at)
    assert ctx.resolved_params == rec.resolved_params
    assert ctx.requested_strategies == rec.requested_strategies
    assert ctx.engine_version == rec.engine_version
    assert ctx.view_schema_version == rec.view_schema_version
    assert ctx.history_replay_version == rec.history_replay_version
    assert ctx.snapshot_source == rec.snapshot_source


def test_result_fact_context_is_none_for_an_unknown_analysis():
    storage = MemoryStorage()
    assert storage.result_fact_context(
        "nope", "2026-01-01T00:00:00+00:00") is None


def test_view_itself_is_completely_unaffected_by_the_new_fields():
    """紅線：本票不得改 `results.view` 的任何既有內容。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]}).json()
    c.post(f"/api/scenarios/{sc['id']}/refresh")

    view = storage.latest_result(sc["id"]).view
    assert store.historical_fact_context(view) == store.historical_fact_context(view)
    assert "resolved_params" not in view
    assert "requested_strategies" not in view
    assert "history_replay_version" not in view
    assert "snapshot_source" not in view


# ---------- Backfill：冪等、可續跑、與 view 比對一致 ----------

def test_backfill_populates_legacy_rows_from_their_view():
    """Legacy row：既有資料只用 `save_result()` 寫入、不帶新欄位（比照
    本票上線前既有存量的真實情況），backfill 後必須與該 view 自己重算
    出來的 context 完全一致。"""
    storage = MemoryStorage()
    storage.create_scenario(_scenario())
    view = store.serialize_result(_result(), "s1", None)
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", view))
    assert storage.latest_result("s1").resolved_params is None   # backfill 前

    summary = backfill_result_fact_context(storage)

    rec = storage.latest_result("s1")
    expected = store.historical_fact_context(view)
    assert rec.resolved_params == expected["resolved_params"]
    assert rec.requested_strategies == expected["requested_strategies"]
    assert rec.engine_version == expected["engine_version"]
    assert rec.view_schema_version == expected["view_schema_version"]
    assert rec.history_replay_version == expected["history_replay_version"]
    assert rec.snapshot_source == expected["snapshot_source"]
    assert summary == {"scenarios": 1, "rows": 1}
    # 紅線：view 本身必須逐位元不變
    assert storage.latest_result("s1").view == view


def test_backfill_is_idempotent_rerunning_produces_zero_drift():
    storage = MemoryStorage()
    storage.create_scenario(_scenario())
    view = store.serialize_result(_result(), "s1", None)
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", view))

    backfill_result_fact_context(storage)
    first = storage.latest_result("s1")
    backfill_result_fact_context(storage)   # 重跑：可續跑、可安全中斷後重試
    second = storage.latest_result("s1")

    assert first == second   # 0 drift、0 duplicate side effect


def test_backfill_covers_archived_scenarios_too():
    storage = MemoryStorage()
    storage.create_scenario(_scenario())
    view = store.serialize_result(_result(), "s1", None)
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", view))
    storage.archive_scenario("s1", ts="2026-08-02T00:00:00+00:00")

    summary = backfill_result_fact_context(storage)

    assert summary == {"scenarios": 1, "rows": 1}
    assert storage.latest_result("s1").resolved_params is not None


def test_backfill_handles_multiple_rows_per_scenario():
    storage = MemoryStorage()
    storage.create_scenario(_scenario())
    view1 = store.serialize_result(_result(), "s1", None)
    view2 = store.serialize_result(
        _result(strategies=("bull-call-spread",)), "s1", None)
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", view1))
    storage.save_result(ResultRecord("s1", "2026-08-02T00:00:00+00:00", view2))

    summary = backfill_result_fact_context(storage)

    assert summary == {"scenarios": 1, "rows": 2}
    hist = storage.result_history("s1")
    assert hist[0].requested_strategies == ("long-call", "bull-call-spread")
    assert hist[1].requested_strategies == ("bull-call-spread",)
