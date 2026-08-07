"""劇本 CRUD／分析／歷史的 HTTP API 測試（V2／#50）。

後端唯一接縫＝HTTP API（spec #47）：儲存行為一律從 API 外部驗證，
不直接戳記憶體假體的內部狀態。假體與 Postgres adapter 的行為一致性
由 `tests/test_storage_contract.py` 保證（同一份契約、兩個實作都跑），
所以這裡用假體驗出來的結論對正式環境也成立。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- 建立與列出 ----------

def test_created_scenario_comes_back_with_an_id_and_mvp_defaults():
    sc = _create(_client())
    assert sc["id"]
    assert sc["symbol"] == "XYZ"
    assert sc["target_price"] == 130.0
    assert sc["target_month"] == "2026-09"
    assert sc["created_at"]
    assert sc["archived_at"] is None
    # 三欄表單（spec #47）：方向與策略是 MVP 固定值，不由前端送。
    assert sc["direction"] == "bullish"
    assert sc["strategies"] == ["bull-call-spread"]


def test_created_scenario_appears_in_the_list():
    c = _client()
    sc = _create(c)
    listed = c.get("/api/scenarios").json()
    assert [s["id"] for s in listed] == [sc["id"]]


def test_scenarios_persist_across_requests_in_the_same_storage():
    storage = MemoryStorage()
    sc = _create(_client(storage))
    # 換一個 app 實例（模擬 serverless 的下一次冷啟動），資料仍在
    assert _client(storage).get(f"/api/scenarios/{sc['id']}").json()["id"] == sc["id"]


def test_unknown_scenario_is_404():
    assert _client().get("/api/scenarios/nope").status_code == 404


def test_target_month_already_past_is_rejected():
    """生下來就過期的劇本不該存在（沿用既有 `ensure_month_open` 規則）。"""
    r = _client().post("/api/scenarios", json={**NEW, "target_month": "2020-01"})
    assert r.status_code == 400


def test_malformed_create_body_is_422():
    assert _client().post("/api/scenarios", json={"symbol": "XYZ"}).status_code == 422


# ---------- 封存＝軟刪除 ----------

def test_archiving_removes_it_from_the_list_but_keeps_the_record():
    c = _client()
    sc = _create(c)
    assert c.post(f"/api/scenarios/{sc['id']}/archive").status_code == 200

    assert c.get("/api/scenarios").json() == []
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["archived_at"] is not None


def test_archiving_is_idempotent_and_404s_on_unknown():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive")
    assert c.post(f"/api/scenarios/{sc['id']}/archive").status_code == 200
    assert c.post("/api/scenarios/nope/archive").status_code == 404


# ---------- 還原（TR2／#89） ----------

def test_restoring_brings_it_back_to_the_default_list():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    resp = c.post(f"/api/scenarios/{sc['id']}/restore")

    assert resp.status_code == 200
    assert [s["id"] for s in c.get("/api/scenarios").json()] == [sc["id"]]
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["archived_at"] is None


def test_restoring_leaves_an_audit_trail():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()
    c.post(f"/api/scenarios/{sc['id']}/restore").raise_for_status()

    events = [e["event"] for e in c.get(f"/api/scenarios/{sc['id']}/events").json()]
    assert events == ["SCENARIO_CREATED", "SCENARIO_ARCHIVED", "SCENARIO_RESTORED"]


def test_restoring_a_never_archived_scenario_is_a_noop_not_an_error():
    """跟 `archive` 對重複呼叫的處理同一種寬容：對呼叫端而言結果相同
    （已經不在垃圾桶了），視為冪等成功，不當成錯誤。"""
    c = _client()
    sc = _create(c)
    assert c.post(f"/api/scenarios/{sc['id']}/restore").status_code == 200
    events = [e["event"] for e in c.get(f"/api/scenarios/{sc['id']}/events").json()]
    assert events == ["SCENARIO_CREATED"]   # 沒有多寫一筆 SCENARIO_RESTORED


def test_restoring_404s_on_unknown():
    assert _client().post("/api/scenarios/nope/restore").status_code == 404


def test_restored_scenario_can_be_refreshed_again():
    """TR1（#88）的垃圾桶硬擋要在還原後解除——不是永久黏住。"""
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()
    c.post(f"/api/scenarios/{sc['id']}/restore").raise_for_status()

    assert c.post(f"/api/scenarios/{sc['id']}/refresh").status_code == 200


# ---------- 永久刪除（TR3／#90） ----------

def test_deleting_an_archived_scenario_removes_it_entirely():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    resp = c.delete(f"/api/scenarios/{sc['id']}")

    assert resp.status_code in (200, 204)
    assert c.get(f"/api/scenarios/{sc['id']}").status_code == 404


def test_deleting_an_unarchived_scenario_is_rejected():
    """安全閘門：永久刪除必須先進垃圾桶，不能一步到位刪掉還在使用中
    的劇本。"""
    c = _client()
    sc = _create(c)

    resp = c.delete(f"/api/scenarios/{sc['id']}")

    assert resp.status_code == 409
    # 拒絕不能悄悄地也把資料弄丟
    assert c.get(f"/api/scenarios/{sc['id']}").status_code == 200


def test_deleting_an_unknown_scenario_is_404():
    assert _client().delete("/api/scenarios/nope").status_code == 404


def test_deleting_removes_results_snapshots_and_events():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    c.delete(f"/api/scenarios/{sc['id']}").raise_for_status()

    # 劇本本身已經不存在，這些端點對它而言等同「劇本不存在」（404），
    # 不是回一份空清單——資料真的沒了，不是還在但查不到內容。
    assert c.get(f"/api/scenarios/{sc['id']}/results").status_code == 404
    assert c.get(f"/api/scenarios/{sc['id']}/events").status_code == 404


# ---------- 分析與結果歷史 ----------
#
# 刷新端點本身（回傳形狀、入庫、失敗分層）在 `test_api_refresh.py`（V4／#52）。

def test_result_history_lists_each_analysis_once():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh")
    c.post(f"/api/scenarios/{sc['id']}/refresh")   # 同一份快照＝同一時間戳

    hist = c.get(f"/api/scenarios/{sc['id']}/results").json()
    # 冪等：重跑同一次快照不該在歷史裡留兩筆
    assert len(hist) == 1
    assert hist[0]["analyzed_at"]


def test_detail_without_any_analysis_says_so_rather_than_faking_it():
    c = _client()
    sc = _create(c)
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["latest_result"] is None
    assert detail["latest_analyzed_at"] is None


# ---------- 事件紀錄 ----------

def test_creating_and_analysing_leave_an_audit_trail():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh")
    c.post(f"/api/scenarios/{sc['id']}/archive")

    events = c.get(f"/api/scenarios/{sc['id']}/events").json()
    assert [e["event"] for e in events] == [
        "SCENARIO_CREATED", "ANALYSIS_COMPLETED", "SCENARIO_ARCHIVED"]


# ---------- 健康檢查如實回報實際用的儲存後端 ----------

def test_health_reports_which_storage_backend_is_actually_in_use():
    body = _client().get("/api/health").json()
    assert body["storage"] == "memory"


def test_api_layer_never_touches_sql_directly():
    """AC：API 層只透過儲存介面存取資料。以「main.py 不認識 psycopg／
    不含 SQL 關鍵字」這個結構性事實表達——換掉儲存後端時不需要動它。"""
    src = open("api_app/main.py", encoding="utf-8").read()
    for forbidden in ("psycopg", "SELECT ", "INSERT ", "UPDATE ", "DELETE "):
        assert forbidden not in src, f"main.py 不該出現 {forbidden!r}"


# ---------- 清單卡片欄位（V3／#51） ----------

def test_list_carries_the_card_numbers_so_the_client_needs_one_request():
    """劇本清單卡片要顯示最新收益率與資料時間。若清單只回劇本欄位，
    前端就得為每張卡各打一次 detail（每次拖回十萬字元的 view）——
    手機上這是實打實的浪費，所以清單自己帶。"""
    client = _client()
    ran = _create(client, target_price=130.0)
    never = _create(client, target_price=140.0)
    client.post(f"/api/scenarios/{ran['id']}/refresh").raise_for_status()

    rows = {r["id"]: r for r in client.get("/api/scenarios").json()}

    assert rows[ran["id"]]["latest_analyzed_at"]
    # 與詳細頁 baseline 期的最高收益率同一個數字（同一條純函式）
    view = client.get(f"/api/scenarios/{ran['id']}").json()["latest_result"]
    from option_chaser import store
    assert rows[ran["id"]]["best_return"] == store.best_return(view)

    # 沒跑過的劇本：兩個欄位都是 None（＝卡片顯示「—」），不是 0
    assert rows[never["id"]]["latest_analyzed_at"] is None
    assert rows[never["id"]]["best_return"] is None


def test_list_carries_the_representative_candidate_matching_best_return(
        ):
    """MVP-v2（#77、#78）：清單列除了報酬率，還要有產生它的那組候選——
    策略、各腿履約價、實際到期日。三個端點（建立／列出／刷新）共用同一個
    組裝函式，這裡逐一驗證都帶著、且與 `store.representative_candidate`
    同一份規則算出來的值逐位相同（口徑恆等，需求方裁示的硬紅線）。"""
    from option_chaser import store

    client = _client()
    ran = _create(client, target_price=130.0)
    never = _create(client, target_price=140.0)
    refreshed = client.post(
        f"/api/scenarios/{ran['id']}/refresh").raise_for_status().json()

    view = client.get(f"/api/scenarios/{ran['id']}").json()["latest_result"]
    expected = store.representative_candidate(view)

    rows = {r["id"]: r for r in client.get("/api/scenarios").json()}
    assert rows[ran["id"]]["representative_candidate"] == expected
    assert rows[ran["id"]]["representative_candidate"]["baseline_return"] == \
        rows[ran["id"]]["best_return"]
    assert refreshed["representative_candidate"] == expected

    # 沒跑過的劇本：誠實地說「尚未分析」，不是一組編出來的候選。
    assert rows[never["id"]]["representative_candidate"] is None


def test_list_does_not_ship_the_whole_view():
    """卡片只要兩個數字。清單順手把 view 塞進去的話，一頁十個劇本就是
    一 MB 級的回應。"""
    client = _client()
    sc = _create(client)
    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    row = client.get("/api/scenarios").json()[0]
    assert "latest_result" not in row
    assert "view" not in row


def test_reanalysis_updates_the_card_to_the_newer_numbers():
    """清單讀的必須是**最新**那一筆結果，不是第一筆。

    兩次都餵同一份快照的話，時間戳與數字都一樣，測不出讀新讀舊的差別
    ——所以第二次餵一份 `fetched_at` 與價格都不同的快照。
    """
    import dataclasses

    snaps = [load_snapshot(FIX)]
    # 同一天稍晚的一次刷新（跨到未來會讓目標月變成過去式，引擎會擋）
    snaps.append(dataclasses.replace(
        snaps[0], fetched_at="2026-07-15T21:45:00-04:00", spot=snaps[0].spot * 1.5))
    calls = {"n": 0}

    def fetch(symbol):
        snap = snaps[min(calls["n"], len(snaps) - 1)]
        calls["n"] += 1
        return snap

    client = TestClient(create_app(fetch=fetch, storage=MemoryStorage()))
    sc = _create(client)

    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    first = client.get("/api/scenarios").json()[0]

    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    again = client.get("/api/scenarios").json()[0]

    assert first["latest_analyzed_at"] == "2026-07-15T21:30:00-04:00"
    assert again["latest_analyzed_at"] == "2026-07-15T21:45:00-04:00"
    # 標的價漲五成，baseline 期的收益率不可能原封不動
    assert again["best_return"] != first["best_return"]


def test_list_carries_the_target_month_anchor_and_days_left():
    """卡片要顯示「距到期天數」。錨點是「該月第三個星期五」這條領域規則
    （`timeframe.calendar_anchor`），而「今天」在後端是紐約日曆
    （`ny_today`）——兩者都不該讓瀏覽器自己猜，所以由後端算好送出。"""
    from datetime import date

    from option_chaser.timeframe import TargetMonth, calendar_anchor
    from option_chaser.workspace import ny_today

    client = _client()
    _create(client)
    row = client.get("/api/scenarios").json()[0]

    anchor = calendar_anchor(TargetMonth.from_key("2026-09"))
    assert row["target_anchor"] == anchor.isoformat()
    assert row["days_to_anchor"] == (anchor - ny_today()).days
    assert date.fromisoformat(row["target_anchor"]).weekday() == 4   # 星期五


def test_days_left_goes_negative_rather_than_clamping_to_zero():
    """目標月已過的舊劇本（建立時還沒過）要如實顯示已經過期幾天，
    夾到 0 會讓它看起來還有救。"""
    from datetime import date

    from option_chaser.timeframe import TargetMonth, calendar_anchor
    from api_app.storage import Scenario as StoredScenario

    storage = MemoryStorage()
    storage.create_scenario(StoredScenario(
        id="old", symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2020-01", notes="", strategies=("bull-call-spread",),
        created_at="2019-06-01T00:00:00+00:00"))
    row = _client(storage).get("/api/scenarios").json()[0]

    anchor = calendar_anchor(TargetMonth.from_key("2020-01"))
    assert row["target_anchor"] == anchor.isoformat()
    assert row["days_to_anchor"] < 0


# ---------- 過期劇本標記（#68） ----------
#
# 「過期」在這裡指目標月**最後一天已過完**（`timeframe.month_is_over`），
# 與 `days_to_anchor`（距日曆錨點的天數，可能提早轉負）是兩個不同的
# 判準——前者才是拿來擋批次刷新的那個（見 test_api_refresh.py）。


def test_a_scenario_with_a_month_already_over_is_marked_expired():
    from api_app.storage import Scenario as StoredScenario

    storage = MemoryStorage()
    storage.create_scenario(StoredScenario(
        id="old", symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2020-01", notes="", strategies=("bull-call-spread",),
        created_at="2019-06-01T00:00:00+00:00"))
    row = _client(storage).get("/api/scenarios").json()[0]

    assert row["expired"] is True


def test_a_scenario_with_a_month_still_open_is_not_marked_expired():
    client = _client()
    _create(client)
    row = client.get("/api/scenarios").json()[0]

    assert row["expired"] is False


def test_create_returns_the_same_shape_as_a_list_row():
    """建立後前端要能直接把回傳值放進清單。回傳一個少了欄位的變體，
    客戶端就得為「剛建立的」與「列出來的」維護兩種型別。"""
    client = _client()
    created = _create(client)
    listed = client.get("/api/scenarios").json()[0]
    assert created == listed


def test_scenario_row_sample_matches_the_live_list_response():
    """劇本清單列的形狀也走共用契約樣本（V1 立下的紀律，V3 補上）。

    前端四處 fixture 與 E2E 都吃 `contracts/scenario_row_sample.json`；
    沒有這條，後端把 `days_to_anchor` 改名或拿掉 `target_anchor`，前端
    測試一條都不會紅。只比對**欄位集合**——值裡有時間，會隨執行時間變。
    """
    import json
    from pathlib import Path

    sample_path = Path("contracts/scenario_row_sample.json")
    assert sample_path.exists(), "請跑 scripts/gen_contract_sample.py"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    client = _client()
    sc = _create(client)
    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    row = client.get("/api/scenarios").json()[0]

    assert set(row) == set(sample), (
        "清單列的欄位與契約樣本不一致——請跑 scripts/gen_contract_sample.py "
        "重產，並確認前端 fixture 跟著更新")
