"""編輯劇本（#132）。

重點是身分：編輯之後必須還是**同一個**劇本，而不是刪掉重建一個長得像
的；以及誠實：thesis 改了就不能再把舊結果當成新的。
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ratecurve import RateCurve

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
_RATE = RateCurve(curve_date="2026-07-31",
                  nodes=((0.5, 0.041), (1.0, 0.042), (2.0, 0.043), (3.0, 0.044)))
_DIV = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                       distributions=(DividendRecord("2026-06-01", 1.2),))


@pytest.fixture
def db():
    return MemoryStorage()


@pytest.fixture
def client(db):
    snap = dataclasses.replace(load_snapshot(FIX), source="cboe")
    return TestClient(create_app(
        storage=db, fetch=lambda s: snap,
        rate_loader=lambda today: (_RATE, "假曲線"),
        dividend_loader=lambda symbol, today: (_DIV, "假配息")))


def _create(client, **over):
    body = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
           "strategies": ["vertical-spread"]}
    body.update(over)
    return client.post("/api/scenarios", json=body).json()


def _edit(client, sid, **over):
    # T10（#227）：`strategies` 現在也是必填——編輯表單永遠送出目前
    # 完整的勾選集合，這裡預設沿用建立時的同一個 family，個別測試需要
    # 驗證增減 family 時用 `strategies=[...]` 覆寫。
    body = {"target_price": 140.0, "target_month": "2026-09",
           "strategies": ["vertical-spread"]}
    body.update(over)
    return client.patch(f"/api/scenarios/{sid}", json=body)


# ---------- 身分 ----------

def test_editing_keeps_the_same_scenario_id(client):
    """不得用刪除＋重建假裝編輯——那會換掉身分，讓結果／快照／事件全成
    孤兒，而使用者只是改了個目標價。"""
    sid = _create(client)["id"]
    assert _edit(client, sid).json()["id"] == sid


def test_editing_keeps_the_creation_time(client):
    created = _create(client)
    assert _edit(client, created["id"]).json()["created_at"] \
        == created["created_at"]


def test_the_scenario_count_does_not_grow(client):
    sid = _create(client)["id"]
    _edit(client, sid)
    assert len(client.get("/api/scenarios").json()) == 1


def test_the_symbol_survives_an_edit(client):
    sid = _create(client)["id"]
    assert _edit(client, sid).json()["symbol"] == "XYZ"


# ---------- 標的不可改 ----------

def test_the_request_model_has_no_symbol_field_at_all(client, db):
    """標的不可改不是靠前端把輸入框反灰——請求模型根本沒有那個欄位。
    多送一個 `symbol` 會被忽略，標的原封不動。"""
    sid = _create(client)["id"]
    body = client.patch(f"/api/scenarios/{sid}",
                        json={"target_price": 140.0, "target_month": "2026-09",
                              "strategies": ["vertical-spread"],
                              "symbol": "SPY"}).json()
    assert body["symbol"] == "XYZ"
    assert db.get_scenario(sid).symbol == "XYZ"


# ---------- 可編輯欄位 ----------

def test_target_price_and_month_are_updated(client):
    sid = _create(client)["id"]
    body = _edit(client, sid, target_price=155.5, target_month="2026-10").json()
    assert body["target_price"] == 155.5
    assert body["target_month"] == "2026-10"


def test_the_optional_range_can_be_edited_too(client):
    sid = _create(client)["id"]
    body = _edit(client, sid, target_price=140.0, best_price=180.0,
                 worst_price=100.0).json()
    assert (body["best_price"], body["worst_price"]) == (180.0, 100.0)


def test_editing_is_not_a_back_door_around_validation(client):
    """區間方向與建立同一條規則。"""
    sid = _create(client)["id"]
    assert _edit(client, sid, target_price=140.0,
                 best_price=100.0).status_code == 422


def test_a_month_that_is_already_over_is_refused(client):
    sid = _create(client)["id"]
    assert _edit(client, sid, target_month="2020-01").status_code == 400


def test_editing_something_that_does_not_exist_is_404(client):
    assert _edit(client, "nope").status_code == 404


# ---------- 舊結果不得冒充新結果 ----------

def test_changing_the_thesis_drops_the_stale_result(client, db):
    """目標價餵進 baseline_return、目標月決定選哪些到期日——兩者一改，
    舊結果的每個數字都是對著另一個問題算出來的。"""
    sid = _create(client)["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    assert db.latest_result(sid) is not None

    body = _edit(client, sid, target_price=140.0).json()
    assert db.latest_result(sid) is None
    assert body["latest_analyzed_at"] is None
    assert body["best_return"] is None


def test_saving_without_changing_anything_keeps_the_result(client, db):
    """使用者可能只是打開表單又存了一次——不該白白丟掉一次分析。"""
    created = _create(client)
    sid = created["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    before = db.latest_result(sid).analyzed_at

    body = _edit(client, sid, target_price=created["target_price"],
                 target_month=created["target_month"]).json()
    assert db.latest_result(sid).analyzed_at == before
    assert body["latest_analyzed_at"] == before


def test_the_scenario_can_be_analysed_again_after_an_edit(client, db):
    sid = _create(client)["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    _edit(client, sid, target_price=140.0)
    assert client.post(f"/api/scenarios/{sid}/refresh").status_code == 200
    assert db.latest_result(sid) is not None


def test_an_edit_is_recorded_as_an_event(client, db):
    sid = _create(client)["id"]
    _edit(client, sid)
    assert any(e["event"] == "SCENARIO_EDITED"
               for e in db.list_events(scenario_id=sid))


def test_editing_does_not_wipe_the_event_history(client, db):
    """事件是不可變的事實，不隨 thesis 改變而消失。"""
    sid = _create(client)["id"]
    _edit(client, sid, target_price=140.0)
    events = [e["event"] for e in db.list_events(scenario_id=sid)]
    assert "SCENARIO_CREATED" in events


# ---------- 不重抓歷史 IV ----------

def test_editing_keeps_the_symbol_iv_cache(client, db):
    """同 ticker 的歷史快取繼續共用，不因劇本被編輯而重新 backfill。"""
    from api_app.storage import IvObservation

    sid = _create(client)["id"]
    db.save_iv_observation(IvObservation(
        symbol="XYZ", observed_on="2026-05-04",
        surface={"call": [[30, 0.5, 0.2]], "put": []},
        fetched_at="2026-08-12T00:00:00+00:00"))
    _edit(client, sid, target_price=140.0)
    assert db.iv_observation_dates("XYZ") == ["2026-05-04"]
