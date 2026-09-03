# tests/test_store_serialize.py
"""v5 spec §3 + §7.4: 全欄位 round-trip、逐位元決定性、pct 兩態、
capital/max_loss/days 手算、data_quality 兩態、版本欄位。"""
import json
from datetime import date
from pathlib import Path

import option_chaser
from option_chaser import store
from option_chaser import service
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


def _cand(view: dict, key: str) -> dict:
    """T09（#191）：容器裡現在只有 `candidate_key`（字串），完整內容統一
    查頂層 `candidate_pool`——測試用這個小 helper 取代直接索引，避免每個
    呼叫點各自重複同一段解引用。"""
    return view["candidate_pool"][key]


def test_top_level_fields_and_versions():
    view = store.serialize_result(_result(), "XYZ-120-202608", 100000.0)
    # T04（#188）：1→2 report_text／methodology_text 移除。
    # T09（#191，MVP-v2 舊票）：2→3 候選內容集中進 `candidate_pool`，
    # 四個容器改存 key。
    # T12（#228，Initial V2）：3→4 每腿新增 side/quantity，候選新增
    # breakeven_points（純加法）。
    # T05（#226，Initial V2）：4→5 pair_report 新增 b_layer_removed
    # （純加法）。
    # T08（#225，Initial V2）：5→6 新增頂層 family_eligibility（純加法）。
    # T14（#233，Initial V2）：6→7 熱力圖 matrix 傳輸壓縮——座標軸去重
    # （新增頂層 `axis_sets`）＋格值攤平＋捨入，破壞性改變 `matrix`／
    # `comparator.matrix` 的既有形狀。
    # T15（#230，Initial V2）：7→8 候選新增 `profit_region`（Butterfly
    # 非單調結構的獲利區間，既有四策略恆為 `None`，純加法）。
    # OPTION-CHASER-CLOSEOUT-001：8→9 新增頂層 `direction`（Scenario
    # Detail 補劇本摘要要用的衍生方向，純加法，比照 T08／#225）。
    assert view["schema_version"] == 9
    assert isinstance(view["axis_sets"], list)
    assert view["engine_version"] == option_chaser.__version__ == "0.5.0"
    assert view["scenario_id"] == "XYZ-120-202608"
    assert view["analyzed_at"] == view["snapshot_ref"]["fetched_at"]
    assert view["capital_assumed"] == 100000.0
    assert view["data_quality"]["all_quotes_filtered"] is False
    assert view["params"]["target_price"] == 120.0
    assert view["today"] == _result().today.isoformat()
    assert view["meta"]["target_move"] == _result().meta.target_move
    assert isinstance(view["default_selection"], list)
    # T10（#24）：baseline 期本身＋其第 1 名，與既有 default_selection 並存。
    assert view["baseline_expiry"] == _result().baseline_expiry
    assert isinstance(view["baseline_selection"], list)
    json.dumps(view)   # 全結構可 JSON 化


def test_candidate_fields_hand_checked():
    result = _result(("long-call",))
    view = store.serialize_result(result, "S", 100000.0)
    res0 = view["results"][0]
    assert res0["strategy"] == "long-call" and res0["status"] == "ok"
    cand = _cand(view, res0["candidates"][0])
    cv = result.results[0].candidates[0]
    v = cv.valuation
    assert cand["candidate_key"] == service.candidate_key(cv)
    assert cand["mid_cost"] == v.mid
    # T12（附錄 A14.2）：資本／最大虧損以最差成交成本（單腿＝Ask）計
    assert cand["natural_cost"] == v.contract.ask
    assert cand["capital_per_contract"] == v.contract.ask * 100
    assert cand["max_loss_per_contract"] == v.contract.ask * 100  # debit 恆等於成本
    assert cand["pct_of_capital"] == (v.contract.ask * 100) / 100000.0
    today = result.today
    # 參考日＝日曆錨點（2026-08 的第三個星期五），不是任何被發明出來的目標日
    assert cand["days_to_target"] == (
        result.request.base_params.anchor - today).days
    assert result.request.base_params.anchor == date(2026, 8, 21)
    assert cand["days_to_expiry"] == (
        date.fromisoformat(v.contract.expiry) - today).days
    assert cand["legs"][0]["strike"] == v.contract.strike
    assert cand["legs"][0]["iv"] == v.contract.implied_volatility
    assert cand["scenario_vector"]["worst_code"] == cv.scenario.worst_code
    assert cand["max_profit"] is None                            # long-call
    assert cand["net_delta"] == v.delta
    # T14（#233，Initial V2）：`cells` 攤平成一維陣列＋捨入
    # （`store.MATRIX_CELL_DECIMALS`），`prices`／`dates` 移到頂層
    # `axis_sets`、候選只留 `axis_index` 引用。
    assert cand["matrix"]["cells"] == [
        round(v, store.MATRIX_CELL_DECIMALS)
        for row in cv.matrix.cells for v in row]
    axis = view["axis_sets"][cand["matrix"]["axis_index"]]
    assert axis["prices"] == [list(pt) for pt in cv.matrix.prices]
    assert axis["dates"] == [list(d) for d in cv.matrix.dates]


def test_candidate_carries_l2_l3_cons_and_guidance_warnings():
    """V8（#56，spec R1 §4.2 A2）：買價指引 L2/L3、評語 cons、`guidance_
    judgments` 的警示文字——原本只活在 `report_text` 散文裡，本票補上
    序列化。值直接對照純函式的回傳，不是另外重算一次公式。"""
    from option_chaser.valuation import guidance_judgments

    result = _result(("long-call",))
    view = store.serialize_result(result, "S", None)
    cand = _cand(view, view["results"][0]["candidates"][0])
    cv = result.results[0].candidates[0]
    v = cv.valuation

    assert cand["l2"] == v.l2
    assert cand["l3"] == v.l3
    assert cand["cons"] == list(cv.cons)
    assert "pros" not in cand   # R1 §4.2 C 裁示：pros 不補序列化
    assert cand["guidance_warnings"] == guidance_judgments(
        v, result.request.base_params)


def test_spread_candidate_carries_l2_l3_cons_and_guidance_warnings():
    from option_chaser.valuation import spread_guidance_judgments

    result = _result(("bull-call-spread",))
    view = store.serialize_result(result, "S", None)
    cand = _cand(view, view["results"][0]["candidates"][0])
    cv = result.results[0].candidates[0]
    sv = cv.valuation

    assert cand["l2"] == sv.l2
    assert cand["l3"] == sv.l3
    assert cand["cons"] == list(cv.cons)
    assert cand["guidance_warnings"] == spread_guidance_judgments(
        sv, result.request.base_params)


def test_disclaimer_text_is_serialized_once_per_strategy():
    """V8（#56，spec R1 §4.1）：新版型「⑦ 免責聲明」是完整字串，內容
    出自 `report.py`（單一事實來源），不是前端另外拼出來的。"""
    from option_chaser.report import disclaimer_text

    result = _result(("long-call", "bull-call-spread"))
    view = store.serialize_result(result, "S", None)

    for r in view["results"]:
        assert r["disclaimer_text"] == disclaimer_text()
        # 免責段落要能自己說清楚，不能只是 CLI 那句精簡版的重複貼上——
        # 這是它存在的理由（R1 §4.4.4 明列的擴充內容）。
        assert "OCC" in r["disclaimer_text"]
        assert "FINRA" not in r["disclaimer_text"]   # 不得聲稱受其管轄


def test_report_text_and_methodology_text_are_not_in_the_view():
    """T04（#188）：這兩個欄位前端零引用（`methodology_text` 曾經宣告
    在契約型別裡，但既有前端測試明文斷言它從不被渲染），移出 View
    payload。`report_text` 仍是引擎欄位（CLI 直接讀 `StrategyResult.
    report_text`，不經過這個序列化函式）——這裡鎖的是「View 裡沒有」，
    不是「引擎不再算」。"""
    result = _result(("long-call", "bull-call-spread"))
    assert all(r.report_text for r in result.results)   # 引擎仍然算了

    view = store.serialize_result(result, "S", None)
    for r in view["results"]:
        assert "report_text" not in r
        assert "methodology_text" not in r
        assert "disclaimer_text" in r   # 沒被一併誤刪


def test_spread_legs_order_and_max_profit():
    result = _result(("bull-call-spread",))
    view = store.serialize_result(result, "S", None)
    cand = _cand(view, view["results"][0]["candidates"][0])
    sv = result.results[0].candidates[0].valuation
    assert cand["legs"][0]["strike"] == sv.long_leg.strike    # [0]=long
    assert cand["legs"][1]["strike"] == sv.short_leg.strike   # [1]=short
    assert cand["mid_cost"] == sv.net_mid
    assert cand["max_profit"] == sv.max_profit
    assert cand["net_delta"] == sv.net_delta


def test_pct_null_without_capital():
    view = store.serialize_result(_result(), "S", None)
    assert view["capital_assumed"] is None
    for res in view["results"]:
        for key in res["candidates"]:
            assert _cand(view, key)["pct_of_capital"] is None


def test_byte_determinism():
    r = _result()
    a = store.serialize_result(r, "S", 100000.0)
    b = store.serialize_result(r, "S", 100000.0)
    dump = lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True)
    assert dump(a).encode("utf-8") == dump(b).encode("utf-8")


def test_data_quality_all_quotes_filtered(tmp_path):
    """兩態：正常 False；全部合約 bid/ask=0 → 每策略 empty 且報價異常 removed>=1 → True。"""
    src = json.loads(Path("tests/fixtures/xyz_v4_all_warning.json")
                     .read_text(encoding="utf-8"))
    for c in src["contracts"]:
        c["bid"] = 0.0
        c["ask"] = 0.0
    bad = tmp_path / "all_zero.json"
    bad.write_text(json.dumps(src), encoding="utf-8")
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="long-call",
                                       target_price=120.0,
                                       target_month="2026-08"),
            strategies=("long-call", "bull-call-spread")),
        str(bad))
    view = store.serialize_result(result, "S", None)
    assert all(r["status"] == "empty" for r in view["results"])
    assert view["data_quality"]["all_quotes_filtered"] is True


def test_filter_report_carries_contract_level_counts():
    """FB4-01（#60）：合約層級的「抓到幾筆／通過幾筆」必須如實上線。

    `n_qualified` 在 spread 路徑是**配對數**（`service._spread_result` 取
    `pair_report.passed`），拿它當合約數會把兩種東西混為一談；候選池診斷
    要的是合約數，所以 `filter_report.total`／`.passed` 必須自己上線，
    不能讓前端從 `n_qualified` 反推。
    """
    view = store.serialize_result(_result(), "S", None)
    for r in view["results"]:
        fr = r["filter_report"]
        # 各關是**循序**過濾（filters.apply_filters 逐關縮小 remaining），
        # 所以 total 恆等於 passed 加上各關砍掉的總和。
        assert fr["total"] == fr["passed"] + sum(s["removed"]
                                                 for s in r["filter_stages"])
        assert fr["passed"] >= 0

    spread = next(r for r in view["results"]
                  if r["strategy"] == "bull-call-spread")
    # 這正是不能用 n_qualified 當合約數的證據：spread 路徑兩者不同意義。
    assert spread["n_qualified"] == spread["pair_report"]["passed"]
    assert spread["filter_report"]["passed"] != spread["n_qualified"]


def test_best_return_is_public_and_baseline_expiry_only():
    """V3（#51）：劇本卡片的「最新收益率」與 Step 2 主圖同一口徑。

    這條規則原本只活在 `workspace._best_return`（Streamlit 檔案層的私有
    函式）。API 也要用同一條規則，複製一份等於讓 QA1-03（#30）修好的
    「卡片數字對不上主圖」有機會在新前端重演——所以提升為公開純函式，
    `workspace` 改為委派。
    """
    view = store.serialize_result(_result(), "S", None)
    group = next(g for g in view["expiry_groups"]
                 if g["expiry"] == view["baseline_expiry"])
    expected = max(_cand(view, row["candidate_key"])["baseline_return"]
                   for row in group["rows"])

    assert store.best_return(view) == expected
    assert store.best_return(None) is None

    # QA1-03 的 bug 版本是「取全部到期日的全域最大值」。要抓得到它，
    # 必須確認全域最大值真的落在**別的**到期日，然後斷言兩者不同——
    # 只斷言「子集最大值 ≤ 全集最大值」的話恆真，bug 版本照樣通過。
    everything = max(_cand(view, row["candidate_key"])["baseline_return"]
                     for g in view["expiry_groups"] for row in g["rows"])
    assert everything > expected, "這份 fixture 的全域最大值不在別期，測不到 QA1-03"
    assert store.best_return(view) != everything


def test_best_return_is_none_when_baseline_expiry_has_no_candidates():
    view = store.serialize_result(_result(), "S", None)
    empty = dict(view, baseline_expiry="2099-12-31")
    assert store.best_return(empty) is None


def test_representative_candidate_baseline_return_always_matches_best_return():
    """MVP-v2（#77、#78）：`best_return()` 由 `representative_candidate()`
    導出，兩者在結構上不可能對不上——這正是導出關係存在的理由，不是
    巧合。涵蓋單腳、價差、以及兩者並存三種請求形狀。"""
    for strategies in (("long-call",), ("bull-call-spread",),
                       ("long-call", "bull-call-spread")):
        view = store.serialize_result(_result(strategies), "S", None)
        rep = store.representative_candidate(view)
        assert rep is not None
        assert rep["baseline_return"] == store.best_return(view)

    assert store.representative_candidate(None) is None
    assert store.best_return(None) is None


def test_representative_candidate_is_none_when_baseline_expiry_has_no_candidates():
    view = store.serialize_result(_result(), "S", None)
    empty = dict(view, baseline_expiry="2099-12-31")
    assert store.representative_candidate(empty) is None


def test_representative_candidate_ignores_comparison_and_stays_baseline_scoped():
    """回歸防護（MVP-v2／#77、#78 的口徑鎖死裁示）：`comparison` 是各
    策略在**全部到期日**裡的全域最佳（`service._comparison`），範圍比
    baseline 期寬。若代表候選改讀它，等同讓 QA1-03（#30）的舊 bug 在這
    一層重演。這裡塞一個報酬率高上許多、但屬於別的到期日與策略的
    `comparison` 項目，確保代表候選不會被它帶走——它只認
    `expiry_groups` 裡 baseline 期那組 `rows`。
    """
    view = store.serialize_result(_result(), "S", None)
    decoy = [{"strategy": "long-call", "baseline_return": 999.0,
             "expiry": "1999-01-01", "label": "decoy", "cost": 0.0,
             "breakeven": 0.0, "max_profit": None}]
    poisoned = dict(view, comparison=decoy)

    rep = store.representative_candidate(poisoned)
    assert rep is not None
    assert rep["baseline_return"] != 999.0
    assert rep["expiry"] == view["baseline_expiry"]
    # 加了誘餌以外，其他一切不變——代表候選對 comparison 內容完全無感。
    assert rep == store.representative_candidate(view)


def test_representative_candidate_spread_legs_are_buy_then_sell():
    view = store.serialize_result(_result(("bull-call-spread",)), "S", None)
    rep = store.representative_candidate(view)
    assert rep["strategy"] == "bull-call-spread"
    assert len(rep["legs"]) == 2
    buy, sell = rep["legs"]
    assert buy["option_type"] == sell["option_type"] == "call"
    # Bull Call Spread：買低履約價、賣高履約價（glossary「BCS」定義）。
    assert buy["strike"] < sell["strike"]


def test_representative_candidate_single_leg_has_exactly_one_leg():
    """單腳策略（Long Call）只有一隻腿——結構上容得下未來若把單腳納入
    代表候選競爭時的形狀（本輪 ranking universe 不擴張，這裡只驗證
    schema 不假設腿數固定，見 spec #77〈Implementation Decisions〉一）。
    """
    view = store.serialize_result(_result(("long-call",)), "S", None)
    rep = store.representative_candidate(view)
    assert rep["strategy"] == "long-call"
    assert len(rep["legs"]) == 1
    assert rep["legs"][0]["option_type"] == "call"


# ---------- per-family 代表候選（T07／#224，Initial V2）----------

def test_representative_candidates_by_family_splits_by_family_not_strategy():
    """`long-call` 屬於 `single-leg` family，`bull-call-spread` 屬於
    `vertical-spread` family——兩者同時出現在同一次分析時，per-family
    map 應該各自有一筆，而不是被單一跨 family 冠軍蓋掉其中一個。"""
    view = store.serialize_result(_result(("long-call", "bull-call-spread")),
                                  "S", None)
    per_family = store.representative_candidates_by_family(view)
    assert set(per_family) == {"single-leg", "vertical-spread"}
    assert per_family["single-leg"]["strategy"] == "long-call"
    assert per_family["vertical-spread"]["strategy"] == "bull-call-spread"


def test_representative_candidates_by_family_max_equals_the_scalar_champion():
    """AC 明文要求的一致性保證：per-family map 裡的最高報酬取 `max()`
    後，等於跨 family 的 scalar 冠軍（`representative_candidate()`）
    ——兩者是同一個候選池、同一個排序鍵，只是分組粒度不同。"""
    for strategies in (("long-call",), ("bull-call-spread",),
                       ("long-call", "bull-call-spread")):
        view = store.serialize_result(_result(strategies), "S", None)
        per_family = store.representative_candidates_by_family(view)
        scalar = store.representative_candidate(view)
        assert max(v["baseline_return"] for v in per_family.values()) == \
            scalar["baseline_return"]


def test_representative_candidates_by_family_is_empty_dict_not_none_when_view_present():
    """與 `representative_candidate()` 回 `None` 的差異是刻意的
    （見函式 docstring）：這裡回空 dict，呼叫端不必為了「完全沒有任何
    family」多判斷一次 `None`。"""
    view = store.serialize_result(_result(), "S", None)
    empty = dict(view, baseline_expiry="2099-12-31")
    assert store.representative_candidates_by_family(empty) == {}
    assert store.representative_candidates_by_family(None) == {}


def test_representative_candidates_by_family_ignores_comparison_and_stays_baseline_scoped():
    """同 `representative_candidate()` 的既有回歸防護（MVP-v2／#77、#78
    口徑鎖死裁示）：per-family 版本必須看到完全相同的候選池，否則
    「max 後等於 scalar 冠軍」這條一致性保證會失效。"""
    view = store.serialize_result(_result(), "S", None)
    decoy = [{"strategy": "bull-call-spread", "baseline_return": 999.0,
             "expiry": "1999-01-01", "label": "decoy", "cost": 0.0,
             "breakeven": 0.0, "max_profit": None}]
    poisoned = dict(view, comparison=decoy)

    per_family = store.representative_candidates_by_family(poisoned)
    assert all(v["baseline_return"] != 999.0 for v in per_family.values())
    assert per_family == store.representative_candidates_by_family(view)


def test_representative_candidates_by_family_single_leg_has_exactly_one_leg():
    view = store.serialize_result(_result(("long-call",)), "S", None)
    per_family = store.representative_candidates_by_family(view)
    assert len(per_family["single-leg"]["legs"]) == 1


# ---------- find_candidate：單腳候選查找（#139／spec #137）----------
#
# 施工中發現：`find_candidate` 原本只掃 `expiry_top10`（T9 附錄A7 明文
# 「範圍限定 Spread 路徑，single-leg 依 MVP 範圍不動」——單腳策略的
# `expiry_top10` 恆為空）。這比 ivhistory 的座標層更上層，若不修，
# Historical IV 端點對任何單腳候選都會 404（`find_candidate` 找不到，
# 不會走到 ivhistory 那一步）——屬 #139 修改邊界明文涵蓋的「端點的
# 候選判別」，同票範圍。

def test_find_candidate_locates_a_single_leg_candidate_via_the_flat_list():
    view = store.serialize_result(_result(("long-call",)), "S", None)
    key = view["results"][0]["candidates"][0]
    got = store.find_candidate(view, key)
    assert got is not None
    assert got["candidate_key"] == key
    assert len(got["legs"]) == 1


def test_find_candidate_still_locates_a_spread_candidate_via_expiry_top10():
    """回歸：兩腿路徑的既有行為不變——一樣走 `expiry_top10`。"""
    view = store.serialize_result(_result(("bull-call-spread",)), "S", None)
    r0 = view["results"][0]
    key = r0["expiry_top10"][0]["candidate_keys"][0]
    got = store.find_candidate(view, key)
    assert got is not None
    assert got["candidate_key"] == key
    assert len(got["legs"]) == 2


def test_find_candidate_does_not_widen_lookup_for_spread_strategies():
    """兩腿策略只認 `expiry_top10`——候選有沒有入榜是既有規則的一部分，
    不因為新增的單腳 fallback 而擴大查找範圍。用一個確實存在於扁平
    `candidates` 清單、但刻意假設它已不在 `expiry_top10`（例如打錯的
    key）來確認 fallback 不會誤判成功；這裡直接驗證「不存在的 key 對
    有 expiry_top10 的策略仍是 None」，避免依賴內部排名細節。"""
    view = store.serialize_result(_result(("bull-call-spread",)), "S", None)
    assert store.find_candidate(view, "not-a-real-key") is None


def test_find_candidate_unknown_key_is_none_not_an_error():
    view = store.serialize_result(_result(("long-call",)), "S", None)
    assert store.find_candidate(view, "no-such-candidate") is None


def test_raw_snapshot_json_carries_meta_and_every_contract():
    """V8（#56）：原始資料查看區——`_leg()` 是候選腿專用的精簡子集，
    這裡要的是逐筆合約完整原樣，`raw_snapshot_json` 不能重用 `_leg()`。"""
    from option_chaser.data.snapshot import load_snapshot

    snap = load_snapshot(FIX)
    raw = store.raw_snapshot_json(snap)

    assert raw["meta"] == {"symbol": snap.symbol, "spot": snap.spot,
                           "fetched_at": snap.fetched_at, "source": snap.source,
                           "contract_count": len(snap.contracts)}
    assert len(raw["contracts"]) == len(snap.contracts)
    assert raw["contracts"][0]["contract_symbol"] == snap.contracts[0].contract_symbol
    assert raw["contracts"][0]["last"] == snap.contracts[0].last
    json.dumps(raw)
