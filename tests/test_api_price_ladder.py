"""V7（#55）：最好／最差價位的三價位對照，經 HTTP API 驗證。

後端唯一接縫＝HTTP API（spec #47），所以「兩個新欄位有沒有存活、有沒有
算出三價位報酬」全部從外部打端點驗證，不戳儲存假體的內部狀態。

三個要釘住的邊界（票上明列）：兩端都不填／只填一端／兩端都填。
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


def _analyzed(client, **overrides):
    """建立→刷新→取回詳細頁 view。"""
    sc = _create(client, **overrides)
    assert client.post(f"/api/scenarios/{sc['id']}/refresh").status_code == 200
    detail = client.get(f"/api/scenarios/{sc['id']}").json()
    assert detail["latest_result"] is not None
    return detail


def _ladder(view):
    """baseline 期第 1 名候選的三價位對照。"""
    result = view["results"][0]
    top = next(c["candidates"] for e, c in
               [(g["expiry"], g) for g in result["expiry_top10"]]
               if e == view["baseline_expiry"])
    return top[0]["price_ladder"]


# ---------- 欄位存活 ----------

def test_best_and_worst_prices_survive_create_and_read_back():
    c = _client()
    sc = _create(c, best_price=150.0, worst_price=110.0)
    assert sc["best_price"] == 150.0
    assert sc["worst_price"] == 110.0
    assert c.get(f"/api/scenarios/{sc['id']}").json()["best_price"] == 150.0


def test_omitting_both_prices_is_fine_and_reads_back_as_null():
    sc = _create(_client())
    assert sc["best_price"] is None
    assert sc["worst_price"] is None


def test_existing_scenarios_without_the_new_fields_still_list_fine():
    """既有劇本不受影響（票上明列）——沒填兩端的劇本照樣列得出來。"""
    c = _client()
    _create(c)
    _create(c, best_price=150.0)
    assert len(c.get("/api/scenarios").json()) == 2


# ---------- 三價位報酬 ----------

def test_ladder_has_only_target_when_neither_end_is_set():
    ladder = _ladder(_analyzed(_client())["latest_result"])
    assert [p["label"] for p in ladder] == ["target"]
    assert ladder[0]["price"] == 130.0


def test_ladder_includes_the_one_end_that_is_set():
    ladder = _ladder(_analyzed(_client(), best_price=150.0)["latest_result"])
    assert [p["label"] for p in ladder] == ["worst", "target", "best"][1:]
    assert [p["price"] for p in ladder] == [130.0, 150.0]


def test_ladder_is_ordered_worst_target_best_when_both_set():
    view = _analyzed(_client(), best_price=150.0, worst_price=110.0)["latest_result"]
    ladder = _ladder(view)
    assert [p["label"] for p in ladder] == ["worst", "target", "best"]
    assert [p["price"] for p in ladder] == [110.0, 130.0, 150.0]


def test_ladder_returns_never_decrease_as_price_rises():
    """看漲劇本：價位越高、報酬不會更低。

    斷言是「不遞減」而不是「嚴格遞增」，因為價差的報酬**有天花板**——
    估值最多到寬度，所以標的價一旦漲過賣腿履約價，再高也不會更賺
    （`test_spread_return_is_capped_by_width` 釘住這條性質）。本測試的
    fixture 在目標價 130 時就已觸頂，最好價位 150 因此與目標同值；那是
    正確行為，不是漏算。
    """
    view = _analyzed(_client(), best_price=150.0, worst_price=110.0)["latest_result"]
    rets = [p["return"] for p in _ladder(view)]
    assert rets[0] <= rets[1] <= rets[2]
    # 最差端必須真的比較差——否則這個對照沒有告訴使用者任何事
    assert rets[0] < rets[-1]


def test_target_entry_matches_the_headline_return_for_every_candidate():
    """三價位裡的「目標」必須等於該候選的主數字——同口徑才能並排讀。

    **掃全部到期日的全部候選**，不只 baseline 那一組：baseline 期的到期日
    恰好就是日曆錨點，只驗證它等於什麼都沒驗證（價差的估值日是自身到期日，
    T3／#17，只有在錨點那一期兩者才重合）。這條是回歸測試。
    """
    view = _analyzed(_client(), best_price=150.0)["latest_result"]
    checked = 0
    for group in view["results"][0]["expiry_top10"]:
        for cand in group["candidates"]:
            target = next(p for p in cand["price_ladder"] if p["label"] == "target")
            assert target["return"] == cand["baseline_return"], (
                f"{group['expiry']} / {cand['candidate_key']}")
            checked += 1
    # 涵蓋面本身要有保障：只跑到 baseline 一組的話這個測試又變空的
    assert len({g["expiry"] for g in view["results"][0]["expiry_top10"]}) > 1
    assert checked > 1


# ---------- 排名口徑不變 ----------

def test_setting_the_two_ends_does_not_change_ranking_or_best_return():
    """票上明列：排名與清單收益率口徑不變（仍為目標價）。"""
    plain = _analyzed(_client())
    withends = _analyzed(_client(), best_price=150.0, worst_price=110.0)
    assert (plain["latest_result"]["baseline_expiry"]
            == withends["latest_result"]["baseline_expiry"])
    assert plain["best_return"] == withends["best_return"]


# ---------- 方向合理性 ----------

def test_best_below_target_is_rejected_with_a_readable_message():
    """看漲劇本的「最好」低於目標價是填反了；擋在 API 而不是靜靜算出
    一組看不懂的數字（票上「依工程判斷處理並記錄」的裁示）。"""
    r = _client().post("/api/scenarios", json={**NEW, "best_price": 120.0})
    assert r.status_code == 422
    assert "最好價位" in r.text


def test_worst_above_target_is_rejected_with_a_readable_message():
    r = _client().post("/api/scenarios", json={**NEW, "worst_price": 140.0})
    assert r.status_code == 422
    assert "最差價位" in r.text


def test_zero_or_negative_prices_are_rejected():
    for field in ("best_price", "worst_price"):
        r = _client().post("/api/scenarios", json={**NEW, field: 0})
        assert r.status_code == 422, field
