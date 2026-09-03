"""T12（#228，Initial V2）：Candidate 共用骨架——`legs[]` 陣列，
1-4 腿容量上限，每一腿顯式攜帶 `side`／`quantity`。

範圍界定（Owner 2026-08-30 修訂，見 #228）：schema 的數值欄位是
**透傳**，不是本票要建的引擎——既有四策略的 `max_profit`／`max_loss`／
`breakeven` 沿用既有公式與既有型別逐位元不變，本票只改變候選被
**傳輸**進共用骨架的形狀。`breakeven_points` 的兩點容量純粹是預留給
Butterfly（T15／#230）未來用的傳輸空間，本票不實作產生兩點的邏輯。
"""
import pytest

from option_chaser import service, store
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def _view(strategy="bull-call-spread", target_price=120.0):
    p = AnalysisParams(target_price=target_price, target_month="2026-10",
                       strategy=strategy)
    result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=p,
                                strategies=(strategy,)), FIX)
    return store.serialize_result(result, "XYZ-120-202610", None)


# ---------- 1 <= len(legs) <= 4：canonical boundary ----------

def test_validate_leg_count_accepts_one_to_four_legs():
    for n in (1, 2, 3, 4):
        store._validate_leg_count([object()] * n)   # 不應拋錯


def test_validate_leg_count_rejects_zero_legs():
    with pytest.raises(ValueError, match="1 到 4"):
        store._validate_leg_count([])


def test_validate_leg_count_rejects_more_than_four_legs():
    with pytest.raises(ValueError, match="1 到 4"):
        store._validate_leg_count([object()] * 5)


def test_candidate_serialization_calls_the_boundary_check(monkeypatch):
    """不只是「函式存在」——真的接在 `_candidate()` 的候選建構路徑上。"""
    calls = []
    original = store._validate_leg_count

    def _spy(legs):
        calls.append(len(legs))
        return original(legs)

    monkeypatch.setattr(store, "_validate_leg_count", _spy)
    view = _view()
    assert calls, "`_candidate()` 應該呼叫過 `_validate_leg_count`"
    assert all(1 <= n <= 4 for n in calls)


# ---------- 每一腿的顯式 side／quantity ----------

def test_two_leg_spread_candidate_has_explicit_buy_sell_sides():
    view = _view("bull-call-spread")
    pool = view["candidate_pool"]
    for cand in pool.values():
        assert len(cand["legs"]) == 2
        assert cand["legs"][0]["side"] == "buy"
        assert cand["legs"][1]["side"] == "sell"
        assert cand["legs"][0]["quantity"] == 1
        assert cand["legs"][1]["quantity"] == 1


def test_single_leg_candidate_has_explicit_buy_side():
    view = _view("long-call", target_price=120.0)
    pool = view["candidate_pool"]
    for cand in pool.values():
        assert len(cand["legs"]) == 1
        assert cand["legs"][0]["side"] == "buy"
        assert cand["legs"][0]["quantity"] == 1


# ---------- 每個候選帶著它實際的 subtype 代碼 ----------

def test_candidate_strategy_field_is_already_the_concrete_subtype():
    """AC：『每個候選帶著它實際的 subtype 代碼』——既有 `strategy` 欄位
    本來就是具體 subtype 字串（不是 T06／#221 的 family 代碼；family→
    subtype 展開在 `api_app/main.py` 那一層就完成了，`AnalysisRequest.
    strategies` 與這裡從頭到尾只認識 subtype）。不新增一個名字不同、
    值卻恆等的 `subtype` 欄位。"""
    from option_chaser.models import STRATEGIES

    for strategy in ("long-call", "long-put", "bull-call-spread",
                     "bear-put-spread"):
        target = 120.0 if strategy in ("long-call", "bull-call-spread") else 80.0
        view = _view(strategy, target_price=target)
        pool = view["candidate_pool"]
        assert pool, f"{strategy}: 應該至少有一個候選"
        for cand in pool.values():
            assert cand["strategy"] == strategy
            assert cand["strategy"] in STRATEGIES   # 是 subtype，不是 family


# ---------- breakeven_points：純加法，1 點路徑逐位元不變 ----------

def test_breakeven_points_wraps_the_existing_scalar_breakeven():
    for strategy, target in (("bull-call-spread", 120.0),
                             ("bear-put-spread", 80.0),
                             ("long-call", 120.0), ("long-put", 80.0)):
        view = _view(strategy, target_price=target)
        for cand in view["candidate_pool"].values():
            assert cand["breakeven_points"] == [cand["breakeven"]]


# ---------- representative_candidate() 也帶 side（前端讀取路徑） ----------

def test_representative_candidate_legs_carry_side():
    view = _view("bull-call-spread")
    rep = store.representative_candidate(view)
    assert rep is not None
    assert [leg["side"] for leg in rep["legs"]] == ["buy", "sell"]


def test_representative_candidate_falls_back_to_position_for_legacy_views():
    """既有已儲存的 View（schema_version < 4，序列化當下還沒有 `side`
    欄位）讀取端維持相容——用位置回推，不做資料遷移。"""
    view = _view("bull-call-spread")
    # 模擬一份舊 View：candidate_pool 裡的 legs 沒有 side 欄位。
    for cand in view["candidate_pool"].values():
        for leg in cand["legs"]:
            leg.pop("side", None)
    rep = store.representative_candidate(view)
    assert rep is not None
    assert [leg["side"] for leg in rep["legs"]] == ["buy", "sell"]


# ---------- schema_version 升版 ----------

def test_schema_version_is_at_least_four():
    """T12（#228）落地時是 4；後續票（T05／#226 起）可能再升版——這裡
    只鎖住『不小於 4』，逐字等於哪個數字交給各自票的專屬測試釘住
    （見 tests/test_store_serialize.py）。"""
    view = _view()
    assert view["schema_version"] >= 4
