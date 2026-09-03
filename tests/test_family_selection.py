"""T10（#227，Initial V2 spec #217）：建立／編輯表單的 Strategy Family
勾選與 eligibility 呈現。

使用者第一次可以自己決定這個劇本要看哪幾類策略——建立與編輯劇本的
請求新增 `strategies` 欄位（family 代碼），後端以白名單（pydantic
`Literal[FAMILIES]`）驗證，前端下拉只是方便。同時把 T08 算出來的
family verdict（`family_eligibility`）額外落到卡片列這個輕量形狀，
供編輯表單顯示「這個 family 現在為什麼不可選」，不必為此打 detail
端點。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _offline_rate_loader(today):
    return None, "test：離線重放，未啟用利率曲線"


def _offline_dividend_loader(symbol, today):
    return None, "test：離線重放，未啟用股利管線"


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(),
                                 rate_loader=_offline_rate_loader,
                                 dividend_loader=_offline_dividend_loader))


# ---------- 建立：白名單、至少一個 ----------

def test_create_accepts_a_single_family():
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg"]})
    assert r.status_code == 201, r.text
    assert r.json()["strategies"] == ["single-leg"]


def test_create_accepts_multiple_families():
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg", "vertical-spread"]})
    assert r.status_code == 201, r.text
    assert r.json()["strategies"] == ["single-leg", "vertical-spread"]


def test_create_rejects_empty_family_selection():
    """AC：至少要選一個才能送出——後端才是真正的防線。"""
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": []})
    assert r.status_code == 422


def test_create_rejects_a_missing_strategies_field():
    """沒有預設值——不送這個欄位是不合法的送出，不是「沿用預設」。"""
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"})
    assert r.status_code == 422


def test_create_rejects_an_unknown_family_name():
    """白名單只認 `FAMILIES`，不接受具體 subtype 字串——那是分析當下
    才展開的推導結果，不是使用者的選擇。"""
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["bull-call-spread"]})
    assert r.status_code == 422


def test_create_rejects_a_completely_made_up_family_name():
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["not-a-real-family"]})
    assert r.status_code == 422


def test_create_deduplicates_a_repeated_family():
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg", "single-leg"]})
    assert r.status_code == 201, r.text
    assert r.json()["strategies"] == ["single-leg"]


# ---------- 編輯：可以增減 family ----------

def _create(client, **over):
    body = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
           "strategies": ["vertical-spread"]}
    body.update(over)
    return client.post("/api/scenarios", json=body).json()


def test_edit_can_add_a_family():
    client = _client()
    sid = _create(client)["id"]
    r = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread", "single-leg"]})
    assert r.status_code == 200, r.text
    assert set(r.json()["strategies"]) == {"vertical-spread", "single-leg"}


def test_edit_can_remove_a_family():
    client = _client()
    sid = _create(client, strategies=["vertical-spread", "single-leg"])["id"]
    r = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg"]})
    assert r.status_code == 200, r.text
    assert r.json()["strategies"] == ["single-leg"]


def test_edit_rejects_an_empty_family_selection():
    client = _client()
    sid = _create(client)["id"]
    r = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09", "strategies": []})
    assert r.status_code == 422


def test_edit_family_change_takes_effect_on_the_next_refresh():
    """AC：儲存後下次刷新生效——不會自動多出使用者沒有勾選的 family。"""
    client = _client()
    sid = _create(client, strategies=["vertical-spread"])["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    assert {r["strategy"] for r in view["results"]} == {
        "bull-call-spread", "bear-put-spread"}

    client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg"]})
    client.post(f"/api/scenarios/{sid}/refresh")
    view2 = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    assert {r["strategy"] for r in view2["results"]} == {
        "long-call", "long-put"}


def test_changing_only_strategies_clears_the_stale_result():
    """family 選擇改變視同 thesis 改變——舊結果是對著另一組 family
    跑出來的，不該冒充新的。"""
    client = _client()
    db = MemoryStorage()
    client = _client(db)
    sid = _create(client)["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    assert db.latest_result(sid) is not None

    body = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg"]}).json()
    assert db.latest_result(sid) is None
    assert body["latest_analyzed_at"] is None


def test_legacy_subtype_string_normalizes_before_comparing_for_thesis_change():
    """既有劇本的 `strategies` 可能仍是遷移前的 legacy subtype 字串
    （#221）——編輯時送出正規化後代表同一個 family 的選擇，不該被誤判
    成『family 變了』而白白清掉還沒過期的結果。"""
    db = MemoryStorage()
    client = _client(db)
    created = _create(client)
    sid = created["id"]
    # 直接改寫成 legacy 字串，模擬遷移前建立的舊劇本。
    sc = db.get_scenario(sid)
    import dataclasses
    db.update_scenario(dataclasses.replace(
        sc, strategies=("bull-call-spread", "bear-put-spread")))
    client.post(f"/api/scenarios/{sid}/refresh")
    assert db.latest_result(sid) is not None

    # 送出「同一個 family」（vertical-spread，正規化後與上面的 legacy
    # subtype 字串等價）——不該觸發 thesis_changed。
    body = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]}).json()
    assert db.latest_result(sid) is not None
    assert body["latest_analyzed_at"] is not None


# ---------- family_eligibility 落在卡片列，供編輯表單讀取 ----------

def test_newly_created_scenario_has_no_family_eligibility_yet():
    """沒有可顯示的 verdict——不是假造一份「全部可選」。"""
    r = _client().post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["single-leg"]})
    assert r.json()["family_eligibility"] is None


def test_family_eligibility_appears_on_the_row_after_refresh():
    client = _client()
    sid = _create(client)["id"]
    row = client.post(f"/api/scenarios/{sid}/refresh").json()
    assert set(row["family_eligibility"]) == {
        "single-leg", "vertical-spread", "butterfly"}
    # T15（#230）：Butterfly 是三個方向都可選的 family（Owner 2026-08-27
    # 「可選／不可選矩陣定案」），不論這個劇本的方向為何都應是 True。
    assert row["family_eligibility"]["butterfly"]["eligible"] is True


def test_family_eligibility_appears_in_the_list_endpoint():
    """清單端點（`GET /api/scenarios`）跟卡片列同一個形狀——不必打
    detail 就能看到最近一次的 verdict。"""
    client = _client()
    sid = _create(client)["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    rows = client.get("/api/scenarios").json()
    row = next(r for r in rows if r["id"] == sid)
    assert row["family_eligibility"] is not None
    assert row["family_eligibility"]["vertical-spread"]["eligible"] is True


def test_family_eligibility_survives_the_storage_roundtrip_via_edit_response():
    """編輯回應（`PATCH`）同樣帶著 family_eligibility——沿用刷新前的
    最近一次 verdict，不是重新計算。"""
    client = _client()
    sid = _create(client)["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    body = client.patch(f"/api/scenarios/{sid}", json={
        "target_price": 130.0, "target_month": "2026-09",
        "strategies": ["vertical-spread"]}).json()
    # target_price／strategies 都沒變（同一個值再送一次）——沒有
    # thesis_changed，因此保留舊 verdict，不是 None。
    assert body["family_eligibility"] is not None


# ---------- T17（#234，Initial V2）：持平劇本（target_price == spot）
# 全程不被拒絕，只有 Butterfly 可選 ----------

def test_flat_scenario_creates_analyses_and_refreshes_without_being_rejected():
    """AC：目標價位等於現價的劇本可以建立、分析、刷新，全程不被拒絕
    ——這是 T17 要修的兩件事（方向閘門＋價格網格塌陷）合起來的端到端
    證明。

    改用 T15（#230）既有的中密度 Butterfly fixture
    （`xyz_v7_butterfly_moderate.json`，spot 同樣是 100.0）而非本檔案
    其餘測試共用的 `xyz_v4_six_expiries.json`——後者履約價梯子太稀疏，
    C(n,3) 枚舉排不出任何正 max_profit 的三腿組合（`status="empty"`，
    這是候選池密度不足，不是方向閘門或本票要修的問題），T15 施工時已
    確認過這個限制、專門為此另建了這份 fixture。"""
    client = _client()
    snap = load_snapshot("tests/fixtures/xyz_v7_butterfly_moderate.json")
    client = TestClient(create_app(
        fetch=lambda symbol: snap, storage=MemoryStorage(),
        rate_loader=_offline_rate_loader, dividend_loader=_offline_dividend_loader))
    sid = _create(client, target_price=100.0,
                  strategies=["single-leg", "vertical-spread", "butterfly"])["id"]

    row = client.post(f"/api/scenarios/{sid}/refresh").json()
    assert row["representative_candidate"] is not None, (
        "持平劇本被全面拒絕——一個候選都沒有")

    elig = row["family_eligibility"]
    assert elig["butterfly"]["eligible"] is True
    assert elig["butterfly"]["reason"] is None
    for family in ("single-leg", "vertical-spread"):
        assert elig[family]["eligible"] is False
        assert "持平" in elig[family]["reason"]

    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    results_by_strategy = {r["strategy"]: r for r in view["results"]}
    # Call/Put／Vertical 四個 subtype 全部被方向閘門擋下，不是分析失敗。
    for strategy in ("long-call", "long-put",
                     "bull-call-spread", "bear-put-spread"):
        assert results_by_strategy[strategy]["status"] == "skipped_direction"
    # Butterfly 兩個 subtype 至少一個真的產生候選（同一個合格池，call-fly／
    # put-fly 兩者皆為 flat-eligible，取決於哪邊報價撐得出正的 max_profit）。
    # 契約形狀：候選鍵在 `expiry_top10[].candidate_keys`（T13／#231 payload
    # 投影後的既有形狀），不是頂層 `candidates` 欄位。
    butterfly_results = [results_by_strategy[s] for s in ("call-fly", "put-fly")]

    def _keys(r):
        return [k for g in (r["expiry_top10"] or []) for k in g["candidate_keys"]]

    assert any(r["status"] == "ok" and _keys(r) for r in butterfly_results), (
        "Butterfly 在持平方向下一個候選都沒產生")

    for r in butterfly_results:
        if r["status"] != "ok":
            continue
        for key in _keys(r):
            cand = view["candidate_pool"][key]
            # T17 修正前：completion_curve 五個點全部塌成同一個報酬率
            # （因為底層的 5 個取樣點全部塌成 spot 本身）。
            curve_returns = [pt[1] for pt in cand["completion_curve"]]
            assert len(set(curve_returns)) > 1, (
                f"{key} 的完成度曲線仍然整條退化成同一個值")
            # 七情境向量同理：S2/S3（半程／大半程）不能塌成同一個數字。
            entries = dict(cand["scenario_vector"]["entries"])
            assert len({entries["S1"], entries["S2"], entries["S3"]}) > 1, (
                f"{key} 的七情境向量 S1/S2/S3 仍然塌成同一個數字")

    # 刷新（第二次）同樣不被拒絕——AC 明文要求「建立、分析、刷新」三者
    # 全程都要走得通，不只是建立那一刻。
    row2 = client.post(f"/api/scenarios/{sid}/refresh").json()
    assert row2["representative_candidate"] is not None
