"""單劇本刷新端點與失敗分層（V4／#52）。

刷新＝抓鏈（Cboe 優先、失敗退 yfinance）→引擎分析→結果與原始快照入庫。
回應是**卡片列**（與清單同形狀），不是整份 view：客戶端要依序刷新 N 個
劇本並即時更新每張卡，每次拖回十萬字元級的 view 在手機上是實打實的浪費
（同 V3／#51 清單端點的理由）。

失敗分層是本票的重點：「抓不到報價」與「分析失敗」是兩件不同的事，
使用者能做的處置也不同，所以錯誤主體帶 `stage`——只回一個 500 或一顆
黃燈，畫面就只能說「失敗了」。
"""
import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError, ParamError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}


def _client(*, fetch=None, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=fetch or (lambda symbol: snap),
                                 storage=storage or MemoryStorage()))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def _detail(resp):
    """FastAPI 把 HTTPException 的主體放在 detail 裡。"""
    return resp.json()["detail"]


# ---------- 成功 ----------

def test_refresh_returns_the_card_row_not_the_whole_view():
    c = _client()
    sc = _create(c)

    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()

    assert row["best_return"] is not None
    assert row["latest_analyzed_at"]
    # view 的兩個大欄位不該出現——回應要小到可以逐一刷新
    assert "results" not in row
    assert "meta" not in row


def test_refresh_row_has_the_same_shape_as_a_list_row():
    """客戶端刷新完是直接把回傳值換掉清單裡那一列。形狀只要差一個欄位，
    卡片就會在刷新後少顯示一樣東西。"""
    c = _client()
    sc = _create(c)

    refreshed = c.post(f"/api/scenarios/{sc['id']}/refresh").json()
    listed = c.get("/api/scenarios").json()[0]

    assert refreshed == listed


def test_refresh_stores_the_result_and_the_raw_snapshot():
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = _create(c)

    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()

    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["latest_result"]["meta"]["symbol"] == "XYZ"
    assert detail["latest_analyzed_at"] == row["latest_analyzed_at"]
    # 原始逐筆報價只有分析當下拿得到（view 裡沒有），事後補不回來
    snap = storage.get_snapshot(sc["id"], row["latest_analyzed_at"])
    assert snap is not None and snap["contracts"]


def test_refresh_leaves_an_audit_trail():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    events = [e["event"] for e in c.get(f"/api/scenarios/{sc['id']}/events").json()]
    assert events == ["SCENARIO_CREATED", "ANALYSIS_COMPLETED"]


def test_refresh_on_unknown_scenario_is_404():
    assert _client().post("/api/scenarios/nope/refresh").status_code == 404


# ---------- 降級（主源失敗、備援接手） ----------

def test_refresh_falls_back_to_yfinance_and_records_that_it_did(monkeypatch):
    """降級態：Cboe 掛掉 → 退回 yfinance → 快照的 `source` 如實記錄是誰
    回答的。

    這裡**不注入** `fetch`，走的是正式路徑 `service.fetch_chain`——注入一個
    「直接回傳 source=yfinance 的快照」只會驗到假體自己，降級鏈有沒有接上
    完全測不到。改成讓真正的兩個 adapter 一個爆一個回答。
    """
    import dataclasses

    from option_chaser.data import cboe, yf

    fallback = dataclasses.replace(load_snapshot(FIX), source="yfinance")
    monkeypatch.setattr(cboe, "fetch_chain", lambda symbol: (_ for _ in ()).throw(
        FetchError("Cboe 沒回應")))
    monkeypatch.setattr(yf, "fetch_chain", lambda symbol: fallback)

    storage = MemoryStorage()
    c = TestClient(create_app(storage=storage))     # fetch 用預設的降級鏈
    sc = _create(c)

    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()

    assert storage.get_snapshot(sc["id"], row["latest_analyzed_at"])["source"] == "yfinance"
    # API 不能把 source 覆寫成固定值——那樣畫面上「資料來源」永遠是對的，
    # 也就永遠沒有資訊。
    view = c.get(f"/api/scenarios/{sc['id']}").json()["latest_result"]
    assert view["meta"]["source"] == "yfinance"


def test_both_sources_down_is_a_fetch_failure_through_the_real_chain(monkeypatch):
    """兩個源都掛才算失敗（同樣走正式降級鏈，不注入 fetch）。"""
    from option_chaser.data import cboe, yf

    def down(symbol):
        raise FetchError("沒回應")

    monkeypatch.setattr(cboe, "fetch_chain", down)
    monkeypatch.setattr(yf, "fetch_chain", down)

    c = TestClient(create_app(storage=MemoryStorage()))
    sc = _create(c)

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert resp.status_code == 502
    assert _detail(resp)["stage"] == "fetch"


def test_an_internal_bug_is_not_dressed_up_as_a_data_source_outage(monkeypatch):
    """抓鏈那一段若是我們自己的程式爆了（不是 FetchError），不可以貼上
    「抓不到報價、可稍後重試」——那句話會叫使用者去重試一個重試不會好的
    東西。不知道是哪一段就不要說。"""
    def bug(symbol):
        raise TypeError("我們自己的 bug")

    # `raise_server_exceptions=False`：讓 TestClient 表現得跟正式部署一樣
    # （回 500），而不是把例外原地丟給測試。
    c = TestClient(create_app(fetch=bug, storage=MemoryStorage()),
                   raise_server_exceptions=False)
    sc = _create(c)

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert resp.status_code == 500
    assert "stage" not in resp.text   # 沒把握是哪一段就不要編一個出來


# ---------- 失敗分層 ----------

def test_a_dead_data_source_says_so_and_stores_nothing():
    def boom(symbol):
        raise FetchError("Cboe 與 yfinance 皆無回應")

    c = _client(fetch=boom)
    sc = _create(c)

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert resp.status_code == 502
    assert _detail(resp)["stage"] == "fetch"
    assert "Cboe 與 yfinance 皆無回應" in _detail(resp)["message"]
    # 抓不到就沒有結果——不能留下一筆看起來成功的紀錄
    assert c.get(f"/api/scenarios/{sc['id']}/results").json() == []


def test_an_engine_failure_is_a_different_stage_from_a_dead_source(monkeypatch):
    """抓得到報價、但算不出來——使用者能做的事不同（重試沒用，是程式或
    資料本身的問題），所以不能跟「抓不到報價」共用同一句話。"""
    def boom(*args, **kwargs):
        raise RuntimeError("引擎爆了")

    monkeypatch.setattr(service, "run_with_snapshot", boom)
    c = _client()
    sc = _create(c)

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert resp.status_code == 500
    assert _detail(resp)["stage"] == "analyze"
    assert c.get(f"/api/scenarios/{sc['id']}/results").json() == []


def test_a_bad_scenario_parameter_is_neither_of_the_above(monkeypatch):
    def boom(*args, **kwargs):
        raise ParamError("目標月不在可分析範圍")

    monkeypatch.setattr(service, "run_with_snapshot", boom)
    c = _client()
    sc = _create(c)

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert resp.status_code == 400
    assert _detail(resp)["stage"] == "params"
    assert "目標月不在可分析範圍" in _detail(resp)["message"]


@pytest.mark.parametrize("stage_error, expected, status", [
    (FetchError("x"), "fetch", 502),
    (ParamError("x"), "params", 400),
])
def test_the_adhoc_endpoint_reports_the_same_stages(monkeypatch, stage_error,
                                                    expected, status):
    """一次性分析端點（V1 遺留）與劇本刷新走同一條錯誤映射——兩處各自
    發明一套錯誤格式的話，前端就得認兩種。狀態碼一起驗：只看 stage 的話，
    把 fetch 映射成 500 這條測試照樣綠。"""
    if isinstance(stage_error, FetchError):
        c = _client(fetch=lambda symbol: (_ for _ in ()).throw(stage_error))
    else:
        monkeypatch.setattr(
            service, "run_with_snapshot",
            lambda *a, **k: (_ for _ in ()).throw(stage_error))
        c = _client()

    resp = c.post("/api/analyze", json={**NEW, "strategies": ["bull-call-spread"]})

    assert resp.status_code == status
    assert _detail(resp)["stage"] == expected

# 分層字彙與前端是否同步，見 `tests/test_frontend_contract.py`。
