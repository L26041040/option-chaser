"""T10（#24）／附錄A8.5: 詳細頁進頁預設選中——baseline 期自己的第 1 名。

刻意構造兩個到期日、且非 baseline 那檔收益率更高，藉此證明
`baseline_selection` 與既有 `default_selection`（v4 舊有、跨到期日全域
最高報酬語意，app.py 快速分析頁仍在用）是兩個語意不同的欄位：baseline_
selection 只認 baseline 期自己的第 1 名，不管其他到期日報酬多高。
"""
import json

from option_chaser import service
from option_chaser.models import AnalysisParams
from option_chaser.ranking import spread_baseline_return

LOW_RETURN_EXPIRY = "2026-08-21"    # 第三個星期五＝錨點命中，較低收益率
HIGH_RETURN_EXPIRY = "2026-10-16"   # 較高收益率


def _leg(sym, strike, expiry, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": expiry, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _snapshot(tmp_path):
    contracts = [
        _leg("A0", 100, LOW_RETURN_EXPIRY, 4.95, 5.05),
        _leg("A1", 110, LOW_RETURN_EXPIRY, 0.95, 1.05),
        _leg("B0", 100, HIGH_RETURN_EXPIRY, 3.97, 4.03),
        _leg("B1", 110, HIGH_RETURN_EXPIRY, 0.47, 0.53),
    ]
    snap = {"schema_version": 2, "symbol": "XYZ",
           "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
           "source": "yfinance", "contracts": contracts}
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


def _run(tmp_path, target_month):
    return service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0,
                                   target_month=target_month, min_return=0.0),
        strategies=("bull-call-spread",)), _snapshot(tmp_path))


def test_baseline_expiry_is_calendar_anchor_nearest_actual_expiry(tmp_path):
    """2026-08 的日曆錨點（第三個星期五）恰好命中 LOW_RETURN_EXPIRY。"""
    r = _run(tmp_path, "2026-08")
    assert r.baseline_expiry == LOW_RETURN_EXPIRY


def test_baseline_selection_stays_pinned_to_baseline_even_when_another_expiry_scores_higher(tmp_path):
    """HIGH_RETURN_EXPIRY 收益率更高，但不是 baseline——baseline_selection
    仍只認 baseline 期自己的第 1 名，這正是它與 `default_selection`
    （跨到期日全域最高報酬）不同的地方。"""
    r = _run(tmp_path, "2026-08")
    res = r.results[0]
    ranked = dict(res.expiry_ranked)
    low_return = spread_baseline_return(ranked[LOW_RETURN_EXPIRY][0])
    high_return = spread_baseline_return(ranked[HIGH_RETURN_EXPIRY][0])
    assert high_return > low_return   # 前提：非 baseline 期確實收益更高

    assert r.baseline_selection == (
        LOW_RETURN_EXPIRY, service.valuation_key(ranked[LOW_RETURN_EXPIRY][0]))
    assert r.default_selection == (
        HIGH_RETURN_EXPIRY, service.valuation_key(ranked[HIGH_RETURN_EXPIRY][0]))
    assert r.baseline_selection != r.default_selection


def test_baseline_selection_matches_default_when_baseline_is_also_the_global_best(tmp_path):
    """反例佐證：baseline 期恰好也是全域最高報酬時，兩個欄位自然重合——
    差異只來自「認哪一期」，不是算法本身錯誤。"""
    r = _run(tmp_path, "2026-10")
    assert r.baseline_expiry == HIGH_RETURN_EXPIRY
    assert r.baseline_selection == r.default_selection


def test_baseline_selection_is_none_when_baseline_expiry_has_no_qualified_candidate(tmp_path):
    """baseline 期只有一檔履約價、無法配對成 Spread（附錄A10.2：零合格候選）：
    該到期日仍因為有實際到期日而被六點規則選為 baseline（有掛牌就算
    tradable），但零合格候選代表沒有值可預設選中。"""
    contracts = [_leg("A0", 100, LOW_RETURN_EXPIRY, 4.95, 5.05),
                # HIGH_RETURN_EXPIRY 正常兩檔，確保仍是「有其他到期日可選」
                # 而不是鏈上零到期日（附錄A12.2）的另一種情況。
                _leg("B0", 100, HIGH_RETURN_EXPIRY, 3.97, 4.03),
                _leg("B1", 110, HIGH_RETURN_EXPIRY, 0.47, 0.53)]
    snap = {"schema_version": 2, "symbol": "XYZ",
           "fetched_at": "2026-07-15T21:30:00-04:00", "spot": 100.0,
           "source": "yfinance", "contracts": contracts}
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")

    r = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=130.0, target_month="2026-08",
                                   min_return=0.0),
        strategies=("bull-call-spread",)), str(f))
    assert r.baseline_expiry == LOW_RETURN_EXPIRY
    assert r.baseline_selection is None
    # HIGH_RETURN_EXPIRY 仍正常產生候選——baseline 零候選不擋其他到期日。
    assert dict(r.results[0].expiry_ranked)[HIGH_RETURN_EXPIRY]
