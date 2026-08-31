"""T08（#225，Initial V2 spec #217）：衍生三態方向與 per-subtype
eligibility（family verdict＝OR）。

方向（bullish／bearish／flat）由 `target_price` 相對 `spot` 於分析
當下推導——衍生值，不落盤、不進事件（`derive_direction`）。每個
subtype 有一份「在哪些方向下適用」的資料（`SUBTYPE_DIRECTIONS`），
`subtype_eligible()` 純查表，取代舊版硬編碼的 `is_bullish(strategy)
-> strategy in ("long-call", "bull-call-spread")` 名字比對。
`family_eligibility()` 是 OR 投影：family 底下任一啟用 subtype 適用
即可選，不可選時附帶原因文字。
"""
import pytest

from option_chaser import service
from option_chaser.models import (
    DIRECTIONS, FAMILIES, FAMILY_SUBTYPES, STRATEGIES,
    derive_direction, family_eligibility, is_bullish, subtype_eligible,
)

FIX = "tests/fixtures/xyz_v2_snapshot.json"


# ---------- derive_direction()：三態、無容忍帶 ----------

def test_derive_direction_bullish_when_target_above_spot():
    assert derive_direction(120.0, 100.0) == "bullish"


def test_derive_direction_bearish_when_target_below_spot():
    assert derive_direction(80.0, 100.0) == "bearish"


def test_derive_direction_flat_only_on_exact_equality():
    assert derive_direction(100.0, 100.0) == "flat"


def test_derive_direction_has_no_tolerance_band():
    """AC 明文：不發明容忍帶——極接近但不等於現價的方向性劇本照常
    成立，不會被就近吸收成 flat。"""
    assert derive_direction(100.0001, 100.0) == "bullish"
    assert derive_direction(99.9999, 100.0) == "bearish"


def test_derive_direction_return_value_is_one_of_the_three_named_states():
    for target, spot in ((120.0, 100.0), (80.0, 100.0), (100.0, 100.0)):
        assert derive_direction(target, spot) in DIRECTIONS
    assert set(DIRECTIONS) == {"bullish", "bearish", "flat"}


# ---------- subtype_eligible()：資料驅動，取代硬編碼名字比對 ----------

def test_subtype_eligible_matches_existing_four_subtypes_directionality():
    """對既有四個 subtype，資料驅動版本必須與舊版 `is_bullish` 隱含的
    二元邏輯逐一吻合——這正是 AC「既有看漲劇本逐位元不變」得以成立
    的前提。"""
    assert subtype_eligible("long-call", "bullish")
    assert not subtype_eligible("long-call", "bearish")
    assert not subtype_eligible("long-call", "flat")

    assert subtype_eligible("bull-call-spread", "bullish")
    assert not subtype_eligible("bull-call-spread", "bearish")
    assert not subtype_eligible("bull-call-spread", "flat")

    assert subtype_eligible("long-put", "bearish")
    assert not subtype_eligible("long-put", "bullish")
    assert not subtype_eligible("long-put", "flat")

    assert subtype_eligible("bear-put-spread", "bearish")
    assert not subtype_eligible("bear-put-spread", "bullish")
    assert not subtype_eligible("bear-put-spread", "flat")


def test_subtype_eligible_unknown_subtype_is_false_not_a_crash():
    """未知 subtype（理論上不會發生）保守回 False，不是預設放行、
    也不拋例外——`SUBTYPE_DIRECTIONS.get(subtype, frozenset())`。

    T15（#230）：`call-fly` 現在是真正定義過的 subtype（`{bullish,
    flat}`），不再適合當「未知 subtype」的範例——這裡改用一個真正
    不存在的名字。"""
    assert subtype_eligible("nonexistent", "flat") is False
    assert subtype_eligible("nonexistent", "bullish") is False


def test_adding_a_new_subtype_only_needs_data_not_logic():
    """AC：新增 subtype 只需加資料，不需修改判斷邏輯——用一個臨時
    monkeypatch 進資料表本身（不改任何函式原始碼）證明
    `subtype_eligible`／`family_eligibility` 立刻認得新資料。"""
    from option_chaser import models

    original = dict(models.SUBTYPE_DIRECTIONS)
    try:
        models.SUBTYPE_DIRECTIONS["fake-fly"] = frozenset({"flat"})
        assert subtype_eligible("fake-fly", "flat") is True
        assert subtype_eligible("fake-fly", "bullish") is False
    finally:
        models.SUBTYPE_DIRECTIONS.clear()
        models.SUBTYPE_DIRECTIONS.update(original)


# ---------- is_bullish()：資料驅動、不再是硬編碼名字比對 ----------

def test_is_bullish_still_matches_existing_behavior():
    """既有呼叫端（Heatmap／CLI 報告的價格軸走向）不在本票改動範圍
    內——重新定義後對既有四個 subtype 的回傳值必須逐位元不變。"""
    assert is_bullish("long-call") and is_bullish("bull-call-spread")
    assert not is_bullish("long-put") and not is_bullish("bear-put-spread")


def test_is_bullish_no_longer_hardcodes_the_name_tuple():
    """結構性證明：`is_bullish` 的編譯後常數池不再含舊版硬編碼的
    `("long-call", "bull-call-spread")` 名字元組——用 bytecode 常數
    檢查（不是原始碼文字比對，`models.py` 別處可能仍以文件形式提到
    這兩個名字），比照 T05（#226）驗證『不重建新概念』時用過的同一種
    手法。"""
    consts = is_bullish.__code__.co_consts
    assert ("long-call", "bull-call-spread") not in consts


# ---------- family_eligibility()：OR 投影 ----------

def test_family_eligibility_vertical_spread_is_eligible_in_both_directions():
    """Vertical Spread 底下有 bull-call-spread（bullish）與
    bear-put-spread（bearish）——OR 投影下兩個方向都可選。"""
    for direction in ("bullish", "bearish"):
        v = family_eligibility("vertical-spread", direction)
        assert v.eligible is True
        assert v.reason is None


def test_family_eligibility_single_leg_is_eligible_in_both_directions():
    for direction in ("bullish", "bearish"):
        v = family_eligibility("single-leg", direction)
        assert v.eligible is True
        assert v.reason is None


def test_family_eligibility_ineligible_when_no_subtype_matches_direction():
    """今天沒有任何 subtype 支援 flat——vertical-spread／single-leg
    在 flat 方向下都不可選，且原因文字提到目前方向。"""
    for family in ("vertical-spread", "single-leg"):
        v = family_eligibility(family, "flat")
        assert v.eligible is False
        assert v.reason is not None
        assert "持平" in v.reason


def test_family_eligibility_butterfly_is_eligible_in_every_direction():
    """T15（#230）落地後：Owner 2026-08-27「可選／不可選矩陣定案」——
    Butterfly 是唯一在看漲／看跌／持平三個方向都可選的 family（call-fly
    收 `{bullish, flat}`、put-fly 收 `{bearish, flat}`，聯集涵蓋全部
    三個方向）。"""
    for direction in DIRECTIONS:
        v = family_eligibility("butterfly", direction)
        assert v.eligible is True
        assert v.reason is None


def test_family_eligibility_covers_every_named_family():
    for family in FAMILIES:
        v = family_eligibility(family, "bullish")
        assert v.family == family


def test_family_eligibility_reason_is_none_only_when_eligible():
    for family in FAMILIES:
        for direction in DIRECTIONS:
            v = family_eligibility(family, direction)
            assert (v.reason is None) == v.eligible


def test_family_eligibility_is_pure_data_driven_not_hardcoded_per_family():
    """反過度耦合：`family_eligibility()` 本身不須認得任何具體 family
    名字或 subtype 名字——把它跑在一個完全虛構的 family／方向組合上
    （只要 `FAMILY_SUBTYPES` 查得到）也該正確運作。"""
    from option_chaser import models

    original = dict(models.FAMILY_SUBTYPES)
    try:
        models.FAMILY_SUBTYPES["made-up-family"] = ("fake-fly",)
        models.SUBTYPE_DIRECTIONS["fake-fly"] = frozenset({"flat"})
        assert family_eligibility("made-up-family", "flat").eligible is True
        assert family_eligibility("made-up-family", "bullish").eligible is False
    finally:
        models.FAMILY_SUBTYPES.clear()
        models.FAMILY_SUBTYPES.update(original)
        del models.SUBTYPE_DIRECTIONS["fake-fly"]


# ---------- service._analyze()：閘門改用 subtype_eligible，逐位元不變 ----------

def _params(strategy, target):
    from option_chaser.models import AnalysisParams
    return AnalysisParams(target_price=target, target_month="2026-08",
                          strategy=strategy)


def test_gate_still_skips_the_wrong_direction_subtype():
    result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=_params("long-call", 80.0),
                                strategies=("long-call", "long-put")), FIX)
    by_strategy = {r.strategy: r for r in result.results}
    assert by_strategy["long-call"].status == "skipped_direction"
    assert by_strategy["long-put"].status == "ok"


def test_gate_message_names_the_skipped_and_available_strategies():
    result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=_params("long-call", 80.0),
                                strategies=("long-call",)), FIX)
    msg = result.results[0].message
    assert "Long Call" in msg
    assert "看跌" in msg


def test_gate_message_mentions_available_alternatives_when_any_exist():
    result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=_params("bull-call-spread", 80.0),
                                strategies=("bull-call-spread",)), FIX)
    msg = result.results[0].message
    assert "可改選" in msg
    assert "Long Put" in msg or "Bear Put Spread" in msg


def test_force_still_bypasses_the_direction_gate():
    """`force=True` 既有的旁路行為不受本票影響——閘門判斷式換了，
    `and not base.force` 這個短路條件原封不動。"""
    import dataclasses

    p = dataclasses.replace(_params("long-call", 80.0), force=True)
    result = service.run_offline(
        service.AnalysisRequest(symbol="XYZ", base_params=p,
                                strategies=("long-call",)), FIX)
    assert result.results[0].status != "skipped_direction"


# ---------- store.serialize_result()：family_eligibility 進契約 ----------

def _result(strategies=("long-call",), target=120.0):
    from option_chaser.models import AnalysisParams
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0], target_price=target,
                                       target_month="2026-08"),
            strategies=strategies),
        "tests/fixtures/xyz_v4_six_expiries.json")


def test_family_eligibility_appears_in_the_contract_for_every_family():
    """涵蓋全部 `FAMILIES`，不只這次請求的 strategies——建立／編輯表單
    需要看到全部三個 family 的 checkbox 狀態。"""
    from option_chaser import store

    view = store.serialize_result(_result(("long-call",), 120.0), "S", None)
    assert set(view["family_eligibility"]) == set(FAMILIES)


def test_family_eligibility_direction_matches_target_vs_spot():
    from option_chaser import store

    view = store.serialize_result(_result(("long-call",), 120.0), "S", None)
    # spot 在這份 fixture 低於 120，方向應為 bullish：single-leg／
    # vertical-spread／butterfly（T15／#230 起）皆可選。
    assert view["family_eligibility"]["single-leg"]["eligible"] is True
    assert view["family_eligibility"]["vertical-spread"]["eligible"] is True
    assert view["family_eligibility"]["butterfly"]["eligible"] is True


def test_family_eligibility_field_is_purely_additive_to_the_schema():
    view = None
    import option_chaser.store as store_mod
    view = store_mod.serialize_result(_result(), "S", None)
    assert view["schema_version"] >= 6
    assert "family_eligibility" in view
