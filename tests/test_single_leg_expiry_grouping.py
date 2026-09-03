"""T09（#222，Initial V2 spec #217）：單腿策略補齊到期日分組欄位。

`_single_leg_result()` 過去只填「各到期日最佳」（`expiry_best`），沒填
「各到期日前十名」（`expiry_top10`／`expiry_ranked`）——MVP 範圍當初
刻意只做 Spread（附錄A13）。後果是詳細頁拿不到基準候選，Long Call／
Long Put 的主圖、到期日結構、候選清單全部渲染不出來，且不拋錯。

本檔案鏡射 `tests/test_expiry_top10.py`（Spread 版本）的既有測試手法：
一個到期日刻意超過十組合格候選（驗證分組後各取前十而非跨到期日全域
前十），另一個只有一組、且收益率遠低於另一到期日的任何一組（驗證
分組不互相污染）。
"""
import json

from option_chaser import service, store
from option_chaser.models import AnalysisParams
from option_chaser.ranking import baseline_return

BIG_EXPIRY = "2026-10-16"     # 12 檔履約價 → 12 組合格 Long Call（>10）
SMALL_EXPIRY = "2026-08-21"   # 1 檔履約價，收益率遠低於 BIG_EXPIRY 全部


def _leg(sym, strike, expiry, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": expiry, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _snapshot(tmp_path):
    contracts = []
    for i in range(12):
        k = 80 + i * 5   # 80, 85, ..., 135：12 檔，涵蓋現價上下
        price = max(0.5, 20 - 0.15 * (k - 80))
        contracts.append(_leg(f"BIG{i}", k, BIG_EXPIRY,
                              round(price - 0.1, 2), round(price + 0.1, 2)))
    # 深度價外、target 130 追不上：baseline_return 遠低於 BIG_EXPIRY 任一組。
    contracts.append(_leg("SMALL0", 150, SMALL_EXPIRY, 2.95, 3.05))

    snap = {"schema_version": 2, "symbol": "XYZ",
           "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
           "source": "yfinance", "contracts": contracts}
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


def _run(tmp_path, strategy="long-call"):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy=strategy, target_price=130.0,
                                   target_month="2026-10", min_return=0.0),
        strategies=(strategy,)), _snapshot(tmp_path))


def test_each_expiry_gets_its_own_top10_not_a_global_slice(tmp_path):
    res = _run(tmp_path).results[0]
    ranked = dict(res.expiry_ranked)
    top10 = dict(res.expiry_top10)
    assert len(ranked[BIG_EXPIRY]) == 12          # 全部合格候選都保留
    assert len(top10[BIG_EXPIRY]) == 10           # 只有前十名建 CandidateView

    assert len(ranked[SMALL_EXPIRY]) == 1
    assert len(top10[SMALL_EXPIRY]) == 1
    assert top10[SMALL_EXPIRY][0].baseline_return < 0
    assert all(cv.baseline_return > top10[SMALL_EXPIRY][0].baseline_return
              for cv in top10[BIG_EXPIRY])


def test_top10_is_the_best_ten_within_its_own_expiry(tmp_path):
    res = _run(tmp_path).results[0]
    ranked = dict(res.expiry_ranked)[BIG_EXPIRY]
    top10 = dict(res.expiry_top10)[BIG_EXPIRY]

    ranked_returns = [baseline_return(v) for v in ranked]
    assert ranked_returns == sorted(ranked_returns, reverse=True)
    assert [service.candidate_key(cv) for cv in top10] == \
        [service.valuation_key(v) for v in ranked[:10]]


def test_no_cross_expiry_contamination(tmp_path):
    res = _run(tmp_path).results[0]
    for exp, group in res.expiry_ranked:
        assert all(v.contract.expiry == exp for v in group)


def test_each_expiry_top10_first_place_matches_expiry_best(tmp_path):
    """AC 逐字：『各期第一名與該期最佳一致』——`expiry_top10[exp][0]`
    與 `expiry_best` 裡那個到期日的候選必須是同一個身份鍵。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    expiry_best_by_exp = {}
    for key in strat["expiry_best"]:
        exp = view["candidate_pool"][key]["legs"][0]["expiry"]
        expiry_best_by_exp[exp] = key
    for group in strat["expiry_top10"]:
        first_key = group["candidate_keys"][0]
        assert first_key == expiry_best_by_exp[group["expiry"]]


def test_all_valid_candidates_serialized_with_rank_in_expiry(tmp_path):
    """鏡射 `test_expiry_top10.py` 同名測試（Spread 版本）：`all_candidates`
    裡每個到期日自己的名次必須是連續的 1..N，且依名次排序後收益率遞減。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    entries = view["results"][0]["all_candidates"]

    assert len(entries) == 13   # 12（BIG_EXPIRY） + 1（SMALL_EXPIRY）
    by_expiry: dict[str, list[dict]] = {}
    for e in entries:
        by_expiry.setdefault(e["expiry"], []).append(e)
    for exp, group in by_expiry.items():
        ranks = [e["rank_in_expiry"] for e in group]
        assert sorted(ranks) == list(range(1, len(group) + 1))
        by_rank = {e["rank_in_expiry"]: e for e in group}
        returns_in_rank_order = [by_rank[r]["baseline_return"]
                                 for r in sorted(by_rank)]
        assert returns_in_rank_order == sorted(returns_in_rank_order,
                                               reverse=True)


def test_expiry_top10_candidates_carry_heatmap_matrix(tmp_path):
    """鏡射 `test_expiry_top10.py` 同名測試：單腿 `expiry_top10` 成員
    也必須真的帶著 Heatmap 矩陣——不能只是空殼引用。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    for group in strat["expiry_top10"]:
        assert group["candidate_keys"]
        for key in group["candidate_keys"]:
            assert view["candidate_pool"][key]["matrix"]["cells"]


def test_expiry_top10_matches_expiry_ranked_prefix_and_expiry_field(tmp_path):
    """鏡射 `test_expiry_top10.py` 同名測試：每組內不重複、`expiry` 欄位
    對得上真實到期日集合。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    for group in strat["expiry_top10"]:
        assert group["expiry"] in (BIG_EXPIRY, SMALL_EXPIRY)
        keys = group["candidate_keys"]
        assert len(keys) == len(set(keys))   # 同一期內不重複


def test_single_leg_candidate_is_resolved_by_find_candidate(tmp_path):
    """AC：單腿候選可以被既有『依 key 查找候選』讀取路徑正確解出——
    這是 T09 真正修補的縫（先前 `expiry_top10` 恆空，`find_candidate()`
    只能透過扁平 `candidates` 清單找到極少數候選）。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    for group in strat["expiry_top10"]:
        for key in group["candidate_keys"]:
            got = store.find_candidate(view, key)
            assert got is not None
            assert got["candidate_key"] == key
            assert len(got["legs"]) == 1


def test_single_leg_candidate_is_resolved_by_representative_candidate(tmp_path):
    """AC：單腿候選可以被『取代表候選』讀取路徑正確解出——baseline 期
    （最接近目標年月的到期日，這裡是 2026-10-16）本身的第一名。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    rep = store.representative_candidate(view)
    assert rep is not None
    assert rep["strategy"] == "long-call"
    assert len(rep["legs"]) == 1


def test_all_candidates_history_entries_have_no_attribute_error(tmp_path):
    """`_history_entry()` 過去只服務過 Spread（`spread_baseline_return`
    寫死），單腿路徑補上 `expiry_ranked` 後同一個函式第一次真的吃到
    `ContractValuation`——這條測試若沒改對型別分支會直接 AttributeError。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    entries = view["results"][0]["all_candidates"]
    assert len(entries) == 13   # 12（BIG_EXPIRY） + 1（SMALL_EXPIRY）
    for e in entries:
        assert set(e) == {"candidate_key", "expiry", "cost",
                          "baseline_return", "rank_in_expiry"}


def test_existing_expiry_best_and_candidates_unaffected(tmp_path):
    """既有欄位（每期第一名、全域前三／每個風險級距一名）不因本票新增
    欄位而回歸（AC：Spread 路徑逐位元不變；這裡順便確認單腿自己既有的
    欄位也沒被誤動）。"""
    res = _run(tmp_path).results[0]
    assert len(res.expiry_best) == 2
    assert len(res.candidates) <= 3


def test_long_put_also_gets_expiry_top10():
    """AC 明列 long-call 與 long-put 兩者皆須驗證，不是只做其中一個。"""
    result = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-put", target_price=80.0,
                                   target_month="2026-10", min_return=0.0),
        strategies=("long-put",)), "tests/fixtures/xyz_v2_snapshot.json")
    res = next(r for r in result.results if r.strategy == "long-put")
    assert res.status == "ok"
    assert res.expiry_top10
    for exp, group in res.expiry_top10:
        assert group
