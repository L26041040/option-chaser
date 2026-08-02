"""T9（#23）／需求三: 每個被選中到期日各自的完整前十名＋全部有效候選的
歷史五欄位序列化。合成兩個到期日的資料——一個到期日刻意超過十組合格候選
（驗證分組後各取前十，而不是跨到期日全域前十），另一個只有一組、且該組的
收益率遠低於另一到期日的任何一組（驗證分組不互相污染：真正的「跨到期日
全域前十」模型會把它整組排除，per-expiry 模型仍要保留它作為自己期別的
第 1 名）。
"""
import json

from option_chaser import service, store
from option_chaser.models import AnalysisParams
from option_chaser.ranking import spread_baseline_return

BIG_EXPIRY = "2026-10-16"     # 6 檔履約價 → C(6,2)=15 組合格 Spread（>10）
SMALL_EXPIRY = "2026-08-21"   # 2 檔履約價 → 1 組，且收益率遠低於 BIG_EXPIRY 全部


def _leg(sym, strike, expiry, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": expiry, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _snapshot(tmp_path):
    contracts = []
    for i, k in enumerate((100, 105, 110, 115, 120, 125)):
        price = 20 - 0.06 * (k - 100)
        contracts.append(_leg(f"BIG{i}", k, BIG_EXPIRY,
                              round(price - 0.1, 2), round(price + 0.1, 2)))
    # 深度價外、target 130 追不上：baseline_return 遠低於 BIG_EXPIRY 任一組。
    contracts.append(_leg("SMALL0", 150, SMALL_EXPIRY, 2.95, 3.05))
    contracts.append(_leg("SMALL1", 160, SMALL_EXPIRY, 0.46, 0.54))

    snap = {"schema_version": 2, "symbol": "XYZ",
           "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
           "source": "yfinance", "contracts": contracts}
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


def _run(tmp_path):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0, target_month="2026-10",
                                   min_return=0.0),
        strategies=("bull-call-spread",)), _snapshot(tmp_path))


def test_each_expiry_gets_its_own_top10_not_a_global_slice(tmp_path):
    res = _run(tmp_path).results[0]
    ranked = dict(res.expiry_ranked)
    top10 = dict(res.expiry_top10)
    assert len(ranked[BIG_EXPIRY]) == 15          # 全部合格候選都保留
    assert len(top10[BIG_EXPIRY]) == 10           # 只有前十名建 CandidateView

    # SMALL_EXPIRY 只有一組，且其收益率遠低於 BIG_EXPIRY 全部 15 組——若是
    # 「跨到期日全域前十」，這組必被排除；per-expiry 模型仍保留為該期第一名。
    assert len(ranked[SMALL_EXPIRY]) == 1
    assert len(top10[SMALL_EXPIRY]) == 1
    assert top10[SMALL_EXPIRY][0].baseline_return < 0
    assert all(cv.baseline_return > top10[SMALL_EXPIRY][0].baseline_return
              for cv in top10[BIG_EXPIRY])


def test_top10_is_the_best_ten_within_its_own_expiry(tmp_path):
    res = _run(tmp_path).results[0]
    ranked = dict(res.expiry_ranked)[BIG_EXPIRY]
    top10 = dict(res.expiry_top10)[BIG_EXPIRY]

    ranked_returns = [spread_baseline_return(sv) for sv in ranked]
    assert ranked_returns == sorted(ranked_returns, reverse=True)
    assert [service.candidate_key(cv) for cv in top10] == \
        [service.valuation_key(sv) for sv in ranked[:10]]


def test_no_cross_expiry_contamination(tmp_path):
    res = _run(tmp_path).results[0]
    for exp, group in res.expiry_ranked:
        assert all(sv.long_leg.expiry == exp for sv in group)


def test_all_valid_candidates_serialized_with_rank_in_expiry(tmp_path):
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    entries = strat["all_candidates"]

    assert len(entries) == 16   # 15（BIG_EXPIRY） + 1（SMALL_EXPIRY）
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


def test_history_entries_carry_key_cost_return_rank_but_no_heatmap(tmp_path):
    """歷史五欄位中的「更新時間」「標的價」在父層（`analyzed_at`／`meta.spot`）
    已有，不逐候選重複；Heatmap 矩陣只隨 Top10 成員入快照（附錄A10.3），
    輕量歷史欄位因此不含 matrix。"""
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    assert "analyzed_at" in view and view["meta"]["spot"] == 100.0
    strat = view["results"][0]
    for e in strat["all_candidates"]:
        assert set(e) == {"candidate_key", "expiry", "cost",
                          "baseline_return", "rank_in_expiry"}
        assert "matrix" not in e


def test_expiry_top10_candidates_carry_heatmap_matrix(tmp_path):
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    for group in strat["expiry_top10"]:
        assert group["candidates"]
        for cand in group["candidates"]:
            assert cand["matrix"]["cells"]


def test_expiry_top10_matches_expiry_ranked_prefix_and_expiry_field(tmp_path):
    result = _run(tmp_path)
    view = store.serialize_result(result, "XYZ-130-202610", None)
    strat = view["results"][0]
    for group in strat["expiry_top10"]:
        assert group["expiry"] in (BIG_EXPIRY, SMALL_EXPIRY)
        keys = [c["candidate_key"] for c in group["candidates"]]
        assert len(keys) == len(set(keys))   # 同一期內不重複


def test_existing_expiry_best_and_candidates_unaffected(tmp_path):
    """既有排名（每期第一名、全域前三）不因本票新增欄位而回歸（AC）。"""
    res = _run(tmp_path).results[0]
    assert len(res.expiry_best) == 2   # 兩檔到期日各自的第一名
    assert len(res.candidates) <= 3    # 全域前三（既有欄位，未被本票更動）
