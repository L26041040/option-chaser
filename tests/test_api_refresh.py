"""單劇本刷新端點與失敗分層（V4／#52）。

刷新＝抓鏈（Cboe 優先、失敗退 yfinance）→引擎分析→結果與原始快照入庫。
回應是**卡片列**（與清單同形狀），不是整份 view：客戶端要依序刷新 N 個
劇本並即時更新每張卡，每次拖回十萬字元級的 view 在手機上是實打實的浪費
（同 V3／#51 清單端點的理由）。

失敗分層是本票的重點：「抓不到報價」與「分析失敗」是兩件不同的事，
使用者能做的處置也不同，所以錯誤主體帶 `stage`——只回一個 500 或一顆
黃燈，畫面就只能說「失敗了」。
"""
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord
from api_app.storage.memory import MemoryStorage
from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError, ParamError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(*, fetch=None, storage=None, **overrides):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=fetch or (lambda symbol: snap),
                                 storage=storage or MemoryStorage(), **overrides))


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


# ---------- 過期劇本不再刷新（#68） ----------
#
# 「已過期」＝目標月最後一天已過完（`timeframe.month_is_over`），與
# `days_to_anchor`（距日曆錨點的天數）是不同的判準，見
# `test_api_scenarios.py` 的說明。這裡的重點是：這個端點是**所有**刷新
# 入口共用的唯一擋點（批次與逐張皆然），過期劇本進來就直接短路——不抓
# 鏈、不跑引擎、不入庫、不留事件。


def _expired_scenario(storage, **overrides):
    """繞過 `POST /api/scenarios` 的建立期擋下規則，直接把一個目標月
    已過完的劇本放進儲存層——這是唯一能測到「本來就過期的劇本」這個
    狀態的辦法（正常建立路徑本來就不允許生出這種劇本）。"""
    from api_app.storage import Scenario as StoredScenario

    sc = StoredScenario(
        id="expired-1", symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2020-01", notes="", strategies=("bull-call-spread",),
        created_at="2019-06-01T00:00:00+00:00", **overrides)
    storage.create_scenario(sc)
    return sc


def test_refresh_on_an_expired_scenario_does_not_touch_the_data_source():
    storage = MemoryStorage()
    _expired_scenario(storage)

    def boom(symbol):
        raise AssertionError("過期劇本不該抓鏈")

    c = TestClient(create_app(fetch=boom, storage=storage))
    row = c.post("/api/scenarios/expired-1/refresh").json()

    assert row["expired"] is True
    assert row["latest_analyzed_at"] is None
    assert row["best_return"] is None


def test_refresh_on_an_expired_scenario_does_not_touch_prior_results():
    """已過期劇本若本來就有一份既有分析結果，刷新請求不能把它動掉——
    只是不再花資源刷新，既有結果照樣留著能看。"""
    storage = MemoryStorage()
    _expired_scenario(storage)
    storage.save_result(ResultRecord(
        scenario_id="expired-1", analyzed_at="2019-12-01T00:00:00+00:00",
        view={"meta": {"symbol": "XYZ"}}, best_return=0.42))

    def boom(symbol):
        raise AssertionError("過期劇本不該抓鏈")

    c = TestClient(create_app(fetch=boom, storage=storage))
    row = c.post("/api/scenarios/expired-1/refresh").json()

    assert row["latest_analyzed_at"] == "2019-12-01T00:00:00+00:00"
    assert row["best_return"] == 0.42
    # 沒有寫入新的一筆——歷史只有原本那一筆
    assert len(storage.result_history("expired-1")) == 1


def test_refresh_on_an_expired_scenario_leaves_no_new_event():
    storage = MemoryStorage()
    _expired_scenario(storage)

    def boom(symbol):
        raise AssertionError("過期劇本不該抓鏈")

    c = TestClient(create_app(fetch=boom, storage=storage))
    c.post("/api/scenarios/expired-1/refresh")

    events = [e["event"] for e in c.get("/api/scenarios/expired-1/events").json()]
    assert events == []   # 直接用 storage 塞進去的劇本本來就沒有 SCENARIO_CREATED


def test_refresh_on_an_expired_scenario_still_404s_when_unknown():
    """過期劇本的擋點不能蓋掉既有的「劇本不存在」規則。"""
    c = TestClient(create_app(storage=MemoryStorage()))
    assert c.post("/api/scenarios/nope/refresh").status_code == 404


# ---------- 垃圾桶劇本不再刷新（TR1／#88） ----------
#
# 跟過期劇本（#68）的擋法刻意不同：過期是「還是能看，只是不再花資源
# 更新」的靜默短路（回既有卡片列，200）；垃圾桶是「使用者主動把它丟
# 掉了」，任何背景動作都不該再發生，錯誤要明確到前端分辨得出「這是
# 因為在垃圾桶」而不是其他失敗原因——回一個帶得出原因的 4xx，不是
# 靜靜地回一份「無害的舊資料」。


def test_refresh_on_an_archived_scenario_is_rejected_and_touches_nothing():
    c = _client()
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    resp = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert resp.status_code == 409
    assert _detail(resp)["stage"] == "archived"
    # 沒有新結果，也沒有新事件——不抓鏈、不跑引擎、不入庫
    assert c.get(f"/api/scenarios/{sc['id']}/results").json() == []
    events = [e["event"] for e in c.get(f"/api/scenarios/{sc['id']}/events").json()]
    assert events == ["SCENARIO_CREATED", "SCENARIO_ARCHIVED"]


def test_refresh_on_an_archived_scenario_never_reaches_fetch():
    """跟過期擋點同一種驗法（`test_refresh_on_an_expired_scenario_does_
    not_touch_the_data_source`）：注入一個一被呼叫就讓測試失敗的假
    `fetch`，證明擋點在抓鏈之前，不是抓完才發現分析失敗。"""
    storage = MemoryStorage()
    c = TestClient(create_app(storage=storage))
    sc = _create(c)
    c.post(f"/api/scenarios/{sc['id']}/archive").raise_for_status()

    def boom(symbol):
        raise AssertionError("垃圾桶劇本不該抓鏈")

    blocked_client = TestClient(create_app(fetch=boom, storage=storage))
    resp = blocked_client.post(f"/api/scenarios/{sc['id']}/refresh")

    assert resp.status_code == 409
    assert _detail(resp)["stage"] == "archived"

# 垃圾桶擋點不會蓋掉「劇本不存在」的既有規則——`_require()` 在
# `archived_at` 檢查之前就先跑，跟過期擋點同一個順序保證，已經由
# `test_refresh_on_an_expired_scenario_still_404s_when_unknown`／
# 這個檔案最上面的 `test_refresh_on_unknown_scenario_is_404` 蓋到，
# 不必為垃圾桶再重複一次同一組斷言。


# ---------- 一輪刷新（E1／#190，T06） ----------
#
# 批次版的單劇本刷新：接受一組 scenario id（省略＝全部未過期劇本），
# Run 內同 symbol 只抓一次 Chain（ADR-0001），任一劇本失敗不中止整輪
# （Partial Success／P2）。`_refresh_and_save()` 已經涵蓋的過期／
# 分析失敗分層邏輯這裡不重複逐項驗證，只驗批次特有的行為：分組去重、
# 部分成功、垃圾桶／過期劇本在批次裡的位置。
#
# 2026-08-26 真機驗收後：`REFRESH_RUN_GROUP_LIMIT` 預設 1，單次呼叫
# 只完成一個 symbol 分組就回傳——這一節大部分測試只用單一 symbol
# （分組本身不受影響，`remaining` 依然是空陣列），涉及**多個 distinct
# symbol**、且原本斷言「一次呼叫就全部做完」的測試改用下面的
# `_run_to_completion()`（循環呼叫直到 `remaining` 清空，語意等同
# 前端 `runBatch()` 的 Continuation 迴圈）——這幾條測試在意的是最終
# 結果與失敗隔離，不是「幾次 HTTP 往返做完」，改用它才不會把「這個
# 產品特性現在需要幾次往返」誤寫死進斷言裡。專門測「單次回應到底
# 涵蓋幾個分組」這件事本身的測試在下面 Continuation 小節。

def _run(client, scenario_ids=None):
    body = {} if scenario_ids is None else {"scenario_ids": scenario_ids}
    resp = client.post("/api/scenarios/refresh-run", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _run_to_completion(client, scenario_ids=None):
    """循環呼叫直到 `remaining` 清空，回傳合併後的 `results`——跟前端
    `runBatch()` 的 Continuation 迴圈同一個邏輯，供只在意「整輪跑完
    的最終結果」而不在意「幾次往返」的測試使用。"""
    out = _run(client, scenario_ids=scenario_ids)
    results = list(out["results"])
    remaining = out["remaining"]
    while remaining:
        out = _run(client, scenario_ids=remaining)
        results.extend(out["results"])
        remaining = out["remaining"]
    return {"results": results, "remaining": []}


def _by_id(run_response, scenario_id):
    return next(r for r in run_response["results"] if r["scenario_id"] == scenario_id)


def test_refresh_run_with_omitted_ids_covers_all_non_expired_scenarios():
    c = _client()
    a = _create(c, symbol="XYZ")
    b = _create(c, symbol="XYZ")

    out = _run(c)

    ids = {r["scenario_id"] for r in out["results"]}
    assert ids == {a["id"], b["id"]}
    assert all(r["ok"] for r in out["results"])
    assert out["remaining"] == []


def test_refresh_run_with_explicit_ids_only_touches_those():
    c = _client()
    a = _create(c, symbol="XYZ")
    b = _create(c, symbol="XYZ")

    out = _run(c, scenario_ids=[a["id"]])

    assert [r["scenario_id"] for r in out["results"]] == [a["id"]]
    # 沒被排進這一輪的劇本維持「尚未分析」，不受影響（P4 的範圍收斂
    # 靠的正是呼叫端只送它想刷新的那個 id，這裡驗的是端點本身確實
    # 只動了送進來的那些）。
    untouched = c.get(f"/api/scenarios/{b['id']}").json()
    assert untouched["latest_analyzed_at"] is None


def test_refresh_run_deduplicates_chain_fetch_within_the_same_symbol():
    calls = []

    def fetch(symbol):
        calls.append(symbol)
        return load_snapshot(FIX)

    c = _client(fetch=fetch)
    a = _create(c, symbol="XYZ")
    b = _create(c, symbol="XYZ")
    d = _create(c, symbol="SPY")

    # XYZ、SPY 是兩個不同分組，預設 `REFRESH_RUN_GROUP_LIMIT=1` 下這一輪
    # 會分兩次往返才做完——用 `_run_to_completion` 驗證最終結果，去重
    # 本身（同一組內只抓一次）不受影響。
    out = _run_to_completion(c, scenario_ids=[a["id"], b["id"], d["id"]])

    assert sorted(calls) == ["SPY", "XYZ"]   # XYZ 只抓一次，即使兩個劇本共用
    assert all(r["ok"] for r in out["results"])


def test_refresh_run_partial_success_one_symbol_failing_does_not_block_another():
    def fetch(symbol):
        if symbol == "BAD":
            raise FetchError("BAD 沒回應")
        return load_snapshot(FIX)

    c = _client(fetch=fetch)
    good = _create(c, symbol="XYZ")
    bad = _create(c, symbol="BAD")

    # 兩個不同分組，預設分組上限下這一輪要分兩次往返——`_run_to_
    # completion` 驗的是「失敗的那個不會擋住另一個最終完成」，不是
    # 「兩個 symbol 是否擠進同一次回應」（那件事本身另有專屬測試）。
    out = _run_to_completion(c, scenario_ids=[good["id"], bad["id"]])

    good_r = _by_id(out, good["id"])
    bad_r = _by_id(out, bad["id"])
    assert good_r["ok"] is True
    assert bad_r["ok"] is False
    assert bad_r["stage"] == "fetch"
    assert "BAD 沒回應" in bad_r["message"]
    # 失敗的那個沒有留下任何結果——保留「尚未分析」，不是半吊子資料
    assert c.get(f"/api/scenarios/{bad['id']}/results").json() == []


def test_refresh_run_failed_scenario_keeps_its_prior_result():
    """P2：失敗的劇本保留上一輪的舊資料，不是被清空。"""
    storage = MemoryStorage()
    c = TestClient(create_app(fetch=lambda symbol: load_snapshot(FIX), storage=storage))
    sc = _create(c, symbol="XYZ")
    c.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    first = c.get(f"/api/scenarios/{sc['id']}").json()["latest_analyzed_at"]

    def boom(symbol):
        raise FetchError("這次抓不到")
    c2 = TestClient(create_app(fetch=boom, storage=storage))

    out = _run(c2, scenario_ids=[sc["id"]])

    assert _by_id(out, sc["id"])["ok"] is False
    still = c2.get(f"/api/scenarios/{sc['id']}").json()
    assert still["latest_analyzed_at"] == first   # 舊結果原封不動


def test_refresh_run_an_engine_failure_reports_the_analyze_stage(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("引擎爆了")
    monkeypatch.setattr(service, "run_with_snapshot", boom)
    c = _client()
    sc = _create(c)

    out = _run(c, scenario_ids=[sc["id"]])

    r = _by_id(out, sc["id"])
    assert r["ok"] is False
    assert r["stage"] == "analyze"


def test_refresh_run_skips_archived_scenarios_without_blocking_others():
    c = _client()
    ok_sc = _create(c, symbol="XYZ")
    trashed = _create(c, symbol="XYZ")
    c.post(f"/api/scenarios/{trashed['id']}/archive").raise_for_status()

    out = _run(c, scenario_ids=[ok_sc["id"], trashed["id"]])

    assert _by_id(out, ok_sc["id"])["ok"] is True
    trashed_r = _by_id(out, trashed["id"])
    assert trashed_r["ok"] is False
    assert trashed_r["stage"] == "archived"


def test_refresh_run_short_circuits_expired_scenarios_without_fetching():
    storage = MemoryStorage()
    expired = _expired_scenario(storage)

    def boom(symbol):
        raise AssertionError("過期劇本不該抓鏈")
    c = TestClient(create_app(fetch=boom, storage=storage))

    out = _run(c, scenario_ids=[expired.id])

    r = _by_id(out, expired.id)
    assert r["ok"] is True
    assert r["row"]["expired"] is True


def test_refresh_run_with_omitted_ids_excludes_expired_scenarios():
    """省略 id 的預設範圍是「全部未過期劇本」（CONTEXT.md Refresh
    Trigger 定義）——過期劇本根本不排進這一輪，不是排進去了才短路。"""
    storage = MemoryStorage()
    expired = _expired_scenario(storage)
    c = TestClient(create_app(fetch=lambda symbol: load_snapshot(FIX), storage=storage))
    live = _create(c, symbol="XYZ")

    out = _run(c)

    ids = {r["scenario_id"] for r in out["results"]}
    assert ids == {live["id"]}
    assert expired.id not in ids


def test_refresh_run_a_symbol_group_of_only_expired_scenarios_never_fetches():
    """省下一趟白跑的網路往返：一整組（同 symbol）全是過期或垃圾桶劇本
    時，這個 symbol 完全不必抓鏈——不是「抓了但沒用上」。"""
    storage = MemoryStorage()
    expired = _expired_scenario(storage)

    def boom(symbol):
        raise AssertionError("這組全過期，不該抓鏈")
    c = TestClient(create_app(fetch=boom, storage=storage))

    out = _run(c, scenario_ids=[expired.id])
    assert _by_id(out, expired.id)["ok"] is True


def test_refresh_run_silently_skips_ids_that_no_longer_exist():
    c = _client()
    sc = _create(c, symbol="XYZ")

    out = _run(c, scenario_ids=[sc["id"], "nope"])

    assert [r["scenario_id"] for r in out["results"]] == [sc["id"]]


def test_refresh_run_updates_the_scenario_list():
    """批次刷新完，清單端點讀到的是這一輪剛落地的新結果——批次端點與
    清單共用同一份儲存層寫入路徑，不是自己另存一份客戶端看不到的狀態。"""
    c = _client()
    sc = _create(c, symbol="XYZ")

    out = _run(c, scenario_ids=[sc["id"]])

    listed = c.get("/api/scenarios").json()[0]
    assert listed["latest_analyzed_at"] == _by_id(out, sc["id"])["row"]["latest_analyzed_at"]


# ---------- Continuation（T07／#193） ----------
#
# server 端時間預算：每處理完一個劇本就檢查剩餘預算，預算用完就停止取
# 新工作，回傳「已完成的 rows ＋ remaining ids」。可注入
# （`create_app(refresh_run_budget=...)`），測試用「人為調小預算」或
# 「人為拉長單一劇本處理時間」逼出耗盡，不假裝時間流逝。


def test_refresh_run_with_a_zero_budget_only_completes_the_first_scenario():
    c = _client(refresh_run_budget=timedelta(seconds=0))
    ids = [_create(c, symbol="XYZ")["id"] for _ in range(3)]

    out = _run(c, scenario_ids=ids)

    assert len(out["results"]) == 1
    assert out["results"][0]["ok"] is True
    assert out["remaining"] == ids[1:]


def test_refresh_run_budget_exhaustion_covers_every_id_exactly_once():
    """已完成 ＋ remaining 合起來要等於送進去的全集，不遺漏、不重複。"""
    c = _client(refresh_run_budget=timedelta(seconds=0))
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    ids = [_create(c, symbol=s)["id"] for s in symbols]

    out = _run(c, scenario_ids=ids)

    done_ids = [r["scenario_id"] for r in out["results"]]
    assert done_ids + out["remaining"] == ids
    assert len(set(done_ids) & set(out["remaining"])) == 0


def test_refresh_run_a_slow_scenario_can_exhaust_the_budget_mid_batch():
    """人為拉長單一劇本的處理時間（而不是把預算調成 0）也要能逼出
    Continuation——驗的是真實耗時觸發，不是只驗「預算等於 0」這個
    退化情況。"""
    def slow_fetch(symbol):
        time.sleep(0.05)
        return load_snapshot(FIX)

    c = _client(fetch=slow_fetch, refresh_run_budget=timedelta(seconds=0.02))
    symbols = ["AAA", "BBB", "CCC"]
    ids = [_create(c, symbol=s)["id"] for s in symbols]

    out = _run(c, scenario_ids=ids)

    assert len(out["results"]) < len(ids)
    assert out["remaining"]


def test_refresh_run_continuation_resumes_and_matches_a_single_pass():
    """用同一組 remaining id 再打一次，最終結果要跟一次做完的結果一致
    （用同一份固定快照，`analyzed_at` 由快照本身的 `fetched_at` 決定，
    兩條路徑因此逐位元可比）。「一次做完」這個比較基準本身需要顯式調大
    `refresh_run_group_limit`——預設值 1 下兩個 distinct symbol 天生
    就會分兩次，不再是「一次做完」的自然結果，這裡要的正是那個對照組。"""
    storage_once = MemoryStorage()
    once = _client(storage=storage_once, refresh_run_group_limit=10)
    once_ids = [_create(once, symbol="XYZ")["id"], _create(once, symbol="SPY")["id"]]
    single_pass = _run(once, scenario_ids=once_ids)
    assert single_pass["remaining"] == []

    storage_split = MemoryStorage()
    tiny = _client(storage=storage_split, refresh_run_budget=timedelta(seconds=0))
    split_ids = [_create(tiny, symbol="XYZ")["id"], _create(tiny, symbol="SPY")["id"]]
    first = _run(tiny, scenario_ids=split_ids)
    assert first["remaining"]   # 這批確實還沒做完

    normal = _client(storage=storage_split)
    second = _run(normal, scenario_ids=first["remaining"])
    assert second["remaining"] == []

    def _rows_by_symbol(run_response, ids_by_symbol):
        return {sym: next(r for r in run_response["results"]
                          if r["scenario_id"] == sid)["row"]
               for sym, sid in ids_by_symbol.items()}

    once_by_symbol = {"XYZ": once_ids[0], "SPY": once_ids[1]}
    split_by_symbol = {"XYZ": split_ids[0], "SPY": split_ids[1]}
    once_rows = _rows_by_symbol(single_pass, once_by_symbol)
    split_results = first["results"] + second["results"]
    split_rows = {sym: next(r for r in split_results if r["scenario_id"] == sid)["row"]
                 for sym, sid in split_by_symbol.items()}
    for sym in ("XYZ", "SPY"):
        assert once_rows[sym]["best_return"] == split_rows[sym]["best_return"]
        assert once_rows[sym]["latest_analyzed_at"] == split_rows[sym]["latest_analyzed_at"]


def test_refresh_run_a_realistic_batch_now_completes_progressively_not_in_one_call():
    """2026-08-26 真機驗收：這條測試的舊版本斷言「常見規模在預設時間
    預算下單次請求就該處理完」——那正是本輪要修掉的體驗（backend 批次
    處理完才一次把全部卡片解鎖／更新，使用者要等整輪跑完才看得到任何
    一張新資料）。`REFRESH_RUN_GROUP_LIMIT` 預設 1 之後，即使離 45 秒
    預算還很遠，單次回應也只涵蓋一個 symbol 分組——前端既有的
    Continuation 迴圈因此會逐組（在這份資料裡等於逐張，因為 12 個劇本
    分屬 3 個不同 symbol、每組 4 個）取得結果並立即解鎖，不必等其餘
    兩組。"""
    c = _client()   # 預設 REFRESH_RUN_BUDGET，不注入任何人為延遲
    symbols = ["XYZ", "SPY", "QQQ"]
    ids = [_create(c, symbol=symbols[i % len(symbols)])["id"] for i in range(12)]

    first = _run(c, scenario_ids=ids)

    # 第一次回應只完成第一個 symbol 分組（XYZ，插入順序最早）的 4 個
    # 劇本，其餘 8 個原樣進 remaining——這就是「逐組解鎖」在單次回應
    # 層級的樣子。
    assert len(first["results"]) == 4
    assert all(r["ok"] for r in first["results"])
    assert len(first["remaining"]) == 8

    # 整輪最終仍然會做完全部 12 個、全部成功——這個產品保證沒有變，
    # 變的只是「幾次往返才看得到」。
    out = _run_to_completion(c, scenario_ids=ids)
    assert len(out["results"]) == len(ids)
    assert all(r["ok"] for r in out["results"])
    assert out["remaining"] == []


def test_refresh_run_three_distinct_symbols_unlock_one_group_at_a_time():
    """需求方 2026-08-26 真機驗收明確要求的驗收情境：A／B／C 三個不同
    symbol（各自獨立分組，`REFRESH_RUN_GROUP_LIMIT` 預設 1）——A 先
    完成，B／C 這時都還在 remaining（尚未鎖定解除）；再打一次才輪到
    B，這時 C 仍在 remaining、不必等它；C 那組中間刻意安插一個抓取
    失敗的劇本，驗證失敗不會擋住同一組其餘劇本、也不會擋住更前面已經
    完成的 A／B。"""
    def fetch(symbol):
        if symbol == "C":
            raise FetchError("C 沒回應")
        return load_snapshot(FIX)

    c = _client(fetch=fetch)
    a = _create(c, symbol="A")
    b = _create(c, symbol="B")
    c_ok = _create(c, symbol="C")
    ids = [a["id"], b["id"], c_ok["id"]]

    first = _run(c, scenario_ids=ids)
    assert [r["scenario_id"] for r in first["results"]] == [a["id"]]
    assert first["results"][0]["ok"] is True
    # B、C 都還沒處理——不是「A 完成、B 也順便跟著做了一半」。
    assert first["remaining"] == [b["id"], c_ok["id"]]

    second = _run(c, scenario_ids=first["remaining"])
    assert [r["scenario_id"] for r in second["results"]] == [b["id"]]
    assert second["results"][0]["ok"] is True
    # 不必等 C：這次回應完全不提 C，C 原封不動留在 remaining。
    assert second["remaining"] == [c_ok["id"]]

    third = _run(c, scenario_ids=second["remaining"])
    assert third["remaining"] == []
    c_result = _by_id(third, c_ok["id"])
    assert c_result["ok"] is False
    assert c_result["stage"] == "fetch"
    # C 這組的失敗完全不影響已經在前兩次回應裡落地的 A／B。
    a_row = c.get(f"/api/scenarios/{a['id']}").json()
    b_row = c.get(f"/api/scenarios/{b['id']}").json()
    assert a_row["latest_analyzed_at"] is not None
    assert b_row["latest_analyzed_at"] is not None


# ---------- REPAIR-08（#245，FIX-04）：analysis_deadline_seconds DI 接線 ----------
#
# `/code-review` Standards 軸抓到的真缺口：這個新的 `create_app()`
# DI 參數（比照既有 `refresh_run_budget`／`chain_cache_ttl` 同一種
# 「可注入」慣例，見上方 test_refresh_run_budget_exhaustion_* 系列）
# 只在引擎層（`tests/test_analysis_soft_deadline.py`，直接呼叫
# `service.run_offline()`）有測試，`api_app/main.py::create_app()`
# 的實際接線（`analysis_deadline_seconds` → `_analyze()` closure →
# `service.run_with_snapshot(..., deadline_seconds=...)`）本身沒有
# 任何一條測試走過——AC 的「不是整個 request 掛掉」講的正是 HTTP
# request 這一層，這裡才是真正該驗證的地方。

def test_a_past_analysis_deadline_degrades_the_refresh_response_gracefully():
    """`analysis_deadline_seconds` 已過期時，`POST /api/scenarios/
    {id}/refresh` 必須正常回應（200，不是 500、不是掛住），且回應與
    後續 `GET` 的 `latest_result` 都看得出對應 subtype 被標記
    `timed_out`——證明 DI 參數真的從 `create_app()` 一路接到引擎層，
    不是只有引擎層自己測得到。"""
    c = _client(analysis_deadline_seconds=-1.0)
    sc = _create(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 200, r.text
    row = r.json()
    # deadline 已過期，`vertical-spread` family 底下唯一 eligible 的
    # bull-call-spread 也被擋下，這個劇本因此沒有任何候選——代表候選
    # 欄位如實反映「什麼都沒算出來」，不是靜默回傳舊資料冒充成功。
    assert row["representative_candidate"] is None

    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    by_strategy = {res["strategy"]: res
                  for res in detail["latest_result"]["results"]}
    assert by_strategy["bull-call-spread"]["status"] == "timed_out"
    assert by_strategy["bear-put-spread"]["status"] == "skipped_direction"


def test_a_slow_fetch_counts_against_the_analysis_deadline_too():
    """`/code-review` Spec 軸抓到的真發現：deadline 計時點原本擺在
    抓鏈**之後**才啟動，票面自己點名的異常輸入情境（「vendor 回應
    異常慢」）完全不受保護——已修正為在抓鏈之前就起算。這裡直接證明：
    人為拉長抓鏈本身的耗時（比照上面 `test_refresh_run_a_slow_
    scenario_can_exhaust_the_budget_mid_batch` 同一種真實 `time.sleep`
    手法，不是調小 deadline 這種退化情況），deadline 只給 100ms、
    抓鏈刻意睡 300ms——抓鏈本身就吃光預算，分析階段連開始都不會開始。

    ⚠ 校準紀錄：`TestClient` 對**第一次**請求有可觀的一次性暖機成本
    （實測跨 ASGI 分派＋惰性單例初始化＋pydantic 編譯，第一次請求
    ~1.2 秒，之後同一個 client 穩定在 ~35ms），這個成本發生在
    `_analyze()` closure 內部（`deadline` 已經開始計時之後），會讓
    任何極短的 deadline（例如原本嘗試的 20ms）在**第一次**請求上
    無論有沒有本票的 bug 都必定逾時——那不是在測本票的修法，是在測
    `TestClient` 的暖機成本，是一條偽陽性測試。已改為先送一次快速
    warm-up 請求付清暖機成本，用**同一個**已暖機的 client 才進行
    真正的計時比較；100ms／300ms 兩個數字經本地實測驗證：暖機後的
    正常（快速抓鏈）耗時穩定在 ~35ms，遠低於 100ms 門檻不會誤觸發，
    300ms 的刻意延遲則穩定超過門檻。"""
    calls = {"n": 0}

    def flaky_fetch(symbol):
        calls["n"] += 1
        if calls["n"] == 1:
            return load_snapshot(FIX)   # warm-up：快速，不佔用 deadline 測試
        time.sleep(0.3)
        return load_snapshot(FIX)

    c = _client(fetch=flaky_fetch, analysis_deadline_seconds=0.1)
    sc = _create(c)
    warmup = c.post(f"/api/scenarios/{sc['id']}/refresh")
    assert warmup.status_code == 200, warmup.text

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 200, r.text
    assert r.json()["representative_candidate"] is None
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    by_strategy = {res["strategy"]: res
                  for res in detail["latest_result"]["results"]}
    assert by_strategy["bull-call-spread"]["status"] == "timed_out"


def test_the_default_analysis_deadline_never_fires_during_a_normal_refresh():
    """既有大量 refresh 測試（本檔案通篇）在本票之前就已經全數通過，
    本身就是「預設 45 秒 deadline 不影響正常規模」的隱性證明——這裡
    額外補一條明確、指名道姓的正面斷言，不必推論。"""
    c = _client()   # 不覆寫 analysis_deadline_seconds，用真正的預設值
    sc = _create(c)

    r = c.post(f"/api/scenarios/{sc['id']}/refresh")

    assert r.status_code == 200, r.text
    assert r.json()["representative_candidate"] is not None
    detail = c.get(f"/api/scenarios/{sc['id']}").json()
    statuses = {res["strategy"]: res["status"]
               for res in detail["latest_result"]["results"]}
    assert "timed_out" not in statuses.values()
