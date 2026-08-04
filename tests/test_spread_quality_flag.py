"""FB5-02（#63）：買賣價差寬度不再是硬門檻，改成隨候選一併回傳的品質
標示——沿用既有機制（`CandidateView.quote_warning`／`.friction`），不新
造一套。

用最小、完全掌控的合成快照測試，不用大 fixture：這裡要驗證的是「特定
一組寬價差的合約，會不會被標示、標示的量級對不對」，用真實 JSON 快照
的話，排名（每級距只留第一名）可能把它擋在候選名單外，於是斷言不到。
`tests/test_api_filters.py` 另外用既有 `xyz_v2_snapshot.json` 驗證池子
層級的「進得了榜」（filter_report 通過數增加、關卡消失）——兩層合起來
才是 spec #61 指定的兩個接縫。
"""
from option_chaser import service
from option_chaser.data.snapshot import save_snapshot
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract, SCHEMA_VERSION

EXPIRY = "2026-10-16"


def _contract(sym, strike, bid, ask, volume=50):
    return OptionContract(
        contract_symbol=sym, option_type="call", strike=strike, expiry=EXPIRY,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=100, implied_volatility=0.30)


def _run(tmp_path, contracts, **params):
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=tuple(contracts))
    path = tmp_path / "snap.json"
    save_snapshot(snap, path)
    p = AnalysisParams(target_price=120.0, target_month="2026-08", **params)
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("long-call",))
    return service.run_offline(req, str(path))


def test_wide_spread_candidate_is_flagged_but_not_excluded(tmp_path):
    # spread 2.0, mid 5.0, 舊硬門檻 max(0.10, 0.15*5.0=0.75) -> 2.0 超標。
    # 唯一候選——沒有排名截斷的疑慮，斷言直接對準。
    wide = _contract("wide", strike=110.0, bid=4.0, ask=6.0)
    r = _run(tmp_path, [wide])
    res = r.results[0]
    assert res.status == "ok"          # FB5-02 核心：進得了榜，不是 empty
    assert len(res.candidates) == 1
    cv = res.candidates[0]
    assert cv.quote_warning is True    # 沿用既有機制，不是新欄位


def test_flag_carries_how_wide_via_existing_friction_field():
    """票上要求「標示內容說得出寬到什麼程度」——不新增欄位，量級資訊
    就是既有的 `friction`（Bid-Ask Spread 佔 Mid 的比例，已序列化、
    已在報告尾註顯示為「Bid-Ask Spread: X%」）。這裡釘住它的公式沒變、
    確實隨價差寬度增加。"""
    from option_chaser.scenarios import friction as friction_fn
    from option_chaser.valuation import evaluate_contract
    from datetime import date

    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    tight = evaluate_contract(_contract("t", 110.0, 4.9, 5.1), spot=100.0,
                              today=date(2026, 7, 15), p=p)
    wide = evaluate_contract(_contract("w", 110.0, 4.0, 6.0), spot=100.0,
                             today=date(2026, 7, 15), p=p)
    assert friction_fn(wide) > friction_fn(tight)


def test_narrow_spread_candidate_is_not_flagged_for_width(tmp_path):
    """緊價差不該無端被標——只有真正超過舊門檻公式的才標，不是「有價差
    就標」。避免這次改動把警示變成到處都是、失去意義。"""
    tight = _contract("tight", strike=110.0, bid=4.95, ask=5.05)
    r = _run(tmp_path, [tight])
    cv = r.results[0].candidates[0]
    assert cv.quote_warning is False
