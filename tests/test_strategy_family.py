"""T06（#221，Initial V2 spec #217）：Strategy Family 詞彙、legacy
subtype→family 映射、分析時的 family×啟用集合展開。

`Scenario.strategies` 從今天起存的是 family 代碼（`single-leg`／
`vertical-spread`／`butterfly`），不是具體 subtype 字串
（`bull-call-spread` 這種）。既有資料（存 subtype 字串）不做遷移，
讀取端用唯一一張靜態對照表換算回 family。分析時再把 family 展開回
subtype 清單，交給既有引擎（`AnalysisRequest.strategies` 本身的介面
完全不變——`option_chaser/service.py` 從頭到尾只認識 subtype，family
概念只活在 `api_app/main.py` 這一層）。
"""
from datetime import date

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import Scenario as StoredScenario
from api_app.storage.memory import MemoryStorage
from option_chaser import service
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import (FAMILIES, FAMILY_SUBTYPES, SPREAD_STRATEGIES,
                                  STRATEGIES, STRATEGY_FAMILY,
                                  normalize_families, subtypes_of)

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


# ---------- 純函式：詞彙表與映射本身 ----------

def test_families_are_exactly_the_three_named_in_the_ticket():
    assert set(FAMILIES) == {"single-leg", "vertical-spread", "butterfly"}


def test_every_existing_subtype_maps_to_exactly_one_family():
    """唯一一張對照表：每個既有 subtype 都查得到 family，且 family 屬於
    `FAMILIES` 詞彙表——沒有第二處硬編碼的對應關係可以互相矛盾。"""
    for s in STRATEGIES:
        assert STRATEGY_FAMILY[s] in FAMILIES


def test_family_subtypes_round_trips_with_strategy_family():
    """`FAMILY_SUBTYPES` 與 `STRATEGY_FAMILY` 是同一份事實的正反兩面：
    對每個 subtype，`FAMILY_SUBTYPES[STRATEGY_FAMILY[subtype]]` 必須
    包含它自己。"""
    for s in STRATEGIES:
        fam = STRATEGY_FAMILY[s]
        assert s in FAMILY_SUBTYPES[fam]


def test_butterfly_now_has_two_subtypes():
    """T15（#230）落地——`call-fly`／`put-fly` 是 butterfly family 底下
    的具體結構，取代 T06／#221 當時「詞彙先行、subtype 未到位」的空
    tuple 狀態。"""
    assert FAMILY_SUBTYPES["butterfly"] == ("call-fly", "put-fly")


def test_strategy_family_keys_and_families_are_disjoint():
    """`normalize_families()` 靠這個互斥性判斷一個字串是舊 subtype
    還是新 family，不需要額外的版本欄位——這條測試把這個前提釘住。"""
    assert set(STRATEGY_FAMILY) & set(FAMILIES) == set()


# ---------- normalize_families() ----------

def test_normalize_families_maps_legacy_subtype_strings_to_family():
    assert normalize_families(("bull-call-spread",)) == ("vertical-spread",)
    assert normalize_families(("long-call",)) == ("single-leg",)


def test_normalize_families_leaves_family_strings_unchanged():
    assert normalize_families(("vertical-spread",)) == ("vertical-spread",)
    assert normalize_families(("single-leg",)) == ("single-leg",)


def test_normalize_families_dedupes_when_both_subtypes_of_same_family_present():
    """舊資料理論上可能存了同一個 family 底下的兩個 subtype
    （`("bull-call-spread", "bear-put-spread")`）——正規化後應收斂成
    一個 family，不是兩份重複。"""
    assert normalize_families(("bull-call-spread", "bear-put-spread")) == (
        "vertical-spread",)


def test_normalize_families_preserves_order_of_first_occurrence():
    assert normalize_families(("long-call", "bull-call-spread")) == (
        "single-leg", "vertical-spread")


# ---------- subtypes_of() ----------

def test_subtypes_of_expands_vertical_spread_to_both_directions():
    """展開回既有引擎認得的 subtype 清單——這是本票唯一真正改變行為的
    地方：一個 family 現在會展開成不只一個 subtype。方向不合的那個
    交給既有的 `skipped_direction` 閘門去擋，這裡不做方向判斷。"""
    assert subtypes_of(("vertical-spread",)) == SPREAD_STRATEGIES


def test_subtypes_of_dedupes_across_families():
    assert subtypes_of(("single-leg", "single-leg")) == (
        "long-call", "long-put")


def test_subtypes_of_butterfly_is_the_two_fly_subtypes():
    """T15（#230）：`butterfly` family 展開成 `call-fly`／`put-fly`，
    鏡射 `test_round_trip_legacy_single_subtype_expands_back_to_the_
    whole_family()` 對 `vertical-spread` 的同一種驗證。"""
    assert subtypes_of(("butterfly",)) == ("call-fly", "put-fly")


def test_round_trip_legacy_single_subtype_expands_back_to_the_whole_family():
    """核心行為：舊資料只存了一個 subtype（`bull-call-spread`），正規化
    →展開後會拿回整個 family 的 subtype 集合，不是只有原本那一個。這正是
    #221 AC 的重點——`bear-put-spread` 會出現在分析請求裡，但既有方向
    閘門會把它擋成 `skipped_direction`，使用者看到的候選與今天完全相同。"""
    legacy = ("bull-call-spread",)
    assert subtypes_of(normalize_families(legacy)) == SPREAD_STRATEGIES


# ---------- API 層：建立劇本存的是 family，不是 subtype ----------

def _offline_rate_loader(today):
    return None, "test：離線重放，未啟用利率曲線"


def _offline_dividend_loader(symbol, today):
    return None, "test：離線重放，未啟用股利管線"


def _client(storage=None):
    """固定注入 `None` 利率／股利 loader，比照 `run_offline()` 的預設
    決定性行為（零網路、恆用常數 rate／q=0）——這個檔案要跟直接呼叫
    `service.run_offline()` 的結果逐位元比對，若讓 `create_app()` 落到
    它自己的預設（真的 Treasury／Yahoo 網路 loader），兩條路徑的利率／
    股利輸入來源不同，會製造出與 T06 家族展開完全無關的假性數值差異。"""
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(),
                                 rate_loader=_offline_rate_loader,
                                 dividend_loader=_offline_dividend_loader))


def test_created_scenario_persists_a_family_code_not_a_subtype():
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09", "strategies": ["vertical-spread"]})
    assert r.status_code == 201, r.text
    sc = r.json()
    assert sc["strategies"] == ["vertical-spread"]


def test_refresh_saves_a_per_family_representative_alongside_the_scalar_champion():
    """T07（#224，Initial V2）：`_refresh_and_save()` 接上
    `store.representative_candidates_by_family()`——落盤的
    `ResultRecord.per_family` 要能指到 `_MVP_STRATEGIES` 唯一啟用的
    family（`vertical-spread`），且其報酬與既有的 scalar 冠軍
    （`representative_candidate`）一致（本輪只有一個 family 啟用，
    兩者理應完全相等）。"""
    storage = MemoryStorage()
    client = _client(storage)
    sc_id = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09", "strategies": ["vertical-spread"]}).json()["id"]
    client.post(f"/api/scenarios/{sc_id}/refresh")

    rec = storage.latest_result(sc_id)
    assert rec.per_family is not None
    assert set(rec.per_family) == {"vertical-spread"}
    assert rec.per_family["vertical-spread"] == rec.representative_candidate


def test_scenario_created_event_records_only_the_family():
    """AC：建立事件只記錄 family（使用者的選擇），不記錄任何依賴現價或
    當日而變的推導結果（例如展開後的 subtype 清單、方向 eligibility）。"""
    storage = MemoryStorage()
    r = _client(storage).post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09", "strategies": ["vertical-spread"]})
    sc_id = r.json()["id"]
    events = storage.list_events(scenario_id=sc_id)
    created = next(e for e in events if e["event"] == "SCENARIO_CREATED")
    assert created["payload"]["strategies"] == ["vertical-spread"]
    # 展開後才會出現的 subtype 字串（`bull-call-spread`／`bear-put-spread`）
    # 不該出現在事件 payload 裡——那是分析當下的推導結果，不是使用者的選擇。
    assert "bull-call-spread" not in created["payload"]["strategies"]
    assert "bear-put-spread" not in created["payload"]["strategies"]


# ---------- API 層：分析路徑展開 family，結果與 T06 之前逐位元相同 ----------

def test_refreshing_a_scenario_expands_the_family_and_keeps_today_bitwise_identical():
    """建立劇本走的是 family（`vertical-spread`），刷新後主策略
    （`bull-call-spread`）的候選／排名／劇本報酬必須與直接呼叫引擎、
    只傳 `strategies=("bull-call-spread",)` 逐位元相同——family 展開
    只是多了一個被方向閘門擋掉的 `bear-put-spread` 條目，不改變既有
    subtype 的任何輸出。

    T13（#231，Initial V2）起，`GET /api/scenarios/{id}` 回傳的是
    `store.project_for_detail()` 投影後的瘦身版（`results[].candidates`
    這個全量清單不再上 wire）——這條測試要驗證的是**儲存層**全保真，
    因此改讀 `storage.latest_result(sc_id).view`（落盤那份，未經投影），
    不是 HTTP 回應。這正是 T13 AC「儲存的內容維持全保真」該用的驗證
    方式，比先前透過 HTTP 回應間接驗證更貼近實際保證的對象。
    """
    storage = MemoryStorage()
    c = _client(storage)
    r = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09", "strategies": ["vertical-spread"]})
    sc_id = r.json()["id"]
    c.post(f"/api/scenarios/{sc_id}/refresh")
    view = storage.latest_result(sc_id).view

    by_strategy = {res["strategy"]: res for res in view["results"]}
    assert set(by_strategy) == {"bull-call-spread", "bear-put-spread"}
    assert by_strategy["bull-call-spread"]["status"] == "ok"
    assert by_strategy["bear-put-spread"]["status"] == "skipped_direction"
    assert by_strategy["bear-put-spread"]["candidates"] == []

    # 直接呼叫引擎、只傳既有 subtype，逐位元比對 bull-call-spread 這一份。
    direct = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=_base_params_for(view),
        strategies=("bull-call-spread",)), FIX)
    from option_chaser import store as store_module
    direct_view = store_module.serialize_result(direct, scenario_id=sc_id,
                                                capital=None)
    direct_res = direct_view["results"][0]
    assert by_strategy["bull-call-spread"]["candidates"] == direct_res["candidates"]
    assert (by_strategy["bull-call-spread"]["expiry_best"]
            == direct_res["expiry_best"])
    assert (by_strategy["bull-call-spread"]["expiry_top10"]
            == direct_res["expiry_top10"])
    for key in by_strategy["bull-call-spread"]["candidates"]:
        assert view["candidate_pool"][key] == direct_view["candidate_pool"][key]


def _base_params_for(view):
    from option_chaser.models import AnalysisParams
    p = view["params"]
    return AnalysisParams(target_price=p["target_price"],
                          target_month=p["target_month"],
                          strategy="bull-call-spread", min_return=0.0)


def test_a_legacy_scenario_with_a_bare_subtype_still_refreshes_as_before():
    """既有資料不遷移：舊劇本存的是裸 subtype 字串
    （`bull-call-spread`，不是 family），刷新後照樣只分析這一個
    subtype——`normalize_families()` 把它換算回 `vertical-spread`
    family，展開後拿回同一組（`bull-call-spread`、`bear-put-spread`），
    行為與新資料完全一致，不需要任何遷移腳本。"""
    storage = MemoryStorage()
    sc = StoredScenario(
        id="legacy-1", symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-09", notes="", strategies=("bull-call-spread",),
        created_at="2019-06-01T00:00:00+00:00")
    storage.create_scenario(sc)
    c = _client(storage)
    c.post("/api/scenarios/legacy-1/refresh")
    view = c.get("/api/scenarios/legacy-1").json()["latest_result"]

    by_strategy = {res["strategy"]: res for res in view["results"]}
    assert set(by_strategy) == {"bull-call-spread", "bear-put-spread"}
    assert by_strategy["bull-call-spread"]["status"] == "ok"
    assert by_strategy["bear-put-spread"]["status"] == "skipped_direction"


# ---------- direction 欄位是 legacy 遺留，不再被任何判斷邏輯讀取 ----------

def test_direction_field_is_never_read_by_any_decision_logic():
    """結構性證明：`sc.direction`／`Scenario.direction` 在 `api_app/` 與
    `option_chaser/` 原始碼裡只出現在寫入（建立時填入 `_MVP_DIRECTION`）
    與純顯示（`_scenario_json` 把它原樣塞進回應 dict）兩處，從未出現在
    任何比較式或條件判斷裡——不靠『反正沒被踩到』，靠原始碼字面。"""
    import re
    from pathlib import Path

    hits: list[str] = []
    for base in ("api_app", "option_chaser"):
        for path in Path(base).rglob("*.py"):
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                if re.search(r"\.direction\b", line):
                    hits.append(f"{path}:{lineno}: {line.strip()}")

    assert hits, "預期至少找得到既有的寫入／顯示兩處引用"
    forbidden_patterns = ("==", "!=", " in ", "is_bullish(")
    for hit in hits:
        for pat in forbidden_patterns:
            assert pat not in hit, (
                f"`.direction` 出現在疑似判斷邏輯裡，違反 T06 AC：{hit}")
