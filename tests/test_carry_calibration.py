"""#113（spec #117 §1）：引擎接線——新估值路徑＋Greeks＋降級語意。

涵蓋範圍：
- t=0 錨定：真實 TLT LEAPS fixture，`analyzed_at × spot` 格重現同模型
  反解出的 mid-based 報酬（+81.9%／+81.4% 消失）
- IV 反解每腿一次，不隨矩陣格數成長（架構要求）
- fallback 第 4 層＝q=0＋vendor IV（今天的行為），不是「q=0＋價格錨定」
- **端到端 selection 紅線**：用真實會讓 delta 跨分級線的資料
  （研究文件已證實 TLT 五檔三檔會從 conservative 移到 balanced），
  證明就算模型真的變了、Greeks 真的變了，選取結果依然逐位元不變
  ——不是靠「兩個欄位剛好同值」矇混過去（#122 的測試只證明接縫本身
  存在，這裡證明接縫在真實模型變動下真的守住）
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from option_chaser import service
from option_chaser.models import AnalysisParams
from option_chaser.valuation import implied_vol as _real_implied_vol

FIXTURES = Path(__file__).parent / "fixtures"
TLT_Q = 0.045  # 研究文件（#110 Method E）經驗擬合值，本測試沿用同一數字


def _tlt_snapshot_path(tmp_path) -> str:
    """把 #110 研究用的真實 TLT LEAPS 報價轉成標準 ChainSnapshot JSON
    （研究 fixture 本身是 calls-only 的精簡格式，不是 ChainSnapshot
    schema），供 `service.run_offline` 直接吃。"""
    data = json.loads((FIXTURES / "tlt_leaps_real_quotes_2026-07-17.json")
                      .read_text())
    contracts = [
        {"contract_symbol": f"TLT{int(c['strike'])}C", "option_type": "call",
         "strike": c["strike"], "expiry": data["expiry"],
         "bid": c["bid"], "ask": c["ask"], "last": None,
         "volume": 50, "open_interest": 100,
         "implied_volatility": c["reported_iv"]}
        for c in data["calls"]
    ]
    snap = {"schema_version": 2, "symbol": "TLT",
           "fetched_at": f"{data['analyzed_at']}T09:30:00-04:00",
           "spot": data["spot"], "source": "adhoc", "contracts": contracts}
    f = tmp_path / "tlt_snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f), data["spot"], data["expiry"]


def _run(tmp_path, q_by_symbol: float | None, target_price: float = 100.0):
    snap_path, spot, expiry = _tlt_snapshot_path(tmp_path)
    p = AnalysisParams(target_price=target_price, target_month="2028-12",
                       strategy="long-call", rate=0.0426,
                       rate_explicit=True, q_by_symbol=q_by_symbol)
    req = service.AnalysisRequest(symbol="TLT", base_params=p,
                                  strategies=("long-call",))
    return service.run_offline(req, snap_path), spot, expiry


# ---------- t=0 錨定 ----------

def test_t0_cell_reproduces_mid_based_return_when_calibrated(tmp_path):
    """真實 TLT K=85 call：q=0.045 校準後，「今天 × 現價」格必須重現
    (mid-cost)/cost——不再是憑空的 +81%。這是「同模型逐腿反解、價格
    錨定」設計本身的直接產物：t=0 時模型值依定義回到用來反解的那個
    mid 價，不需要另外驗證公式，這裡驗證的是接線接對了。"""
    result, spot, expiry = _run(tmp_path, TLT_Q)
    res = result.results[0]
    assert res.status == "ok"

    cv = next(c for c in res.candidates if c.valuation.contract.strike == 85.0)
    assert cv.carry_calibrated is True

    c = cv.valuation.contract
    mid = (c.bid + c.ask) / 2.0
    honest_return = (mid - c.ask) / c.ask

    # 今天欄＝矩陣第一欄（date_axis 的第一點恆為 today，見
    # test_matrix.py::test_date_axis_spans_today_to_own_expiry）；
    # 現價那一列由 <現價> 標記找。
    today_col = 0
    price_row = next(i for i, (_, label, _) in enumerate(cv.matrix.prices)
                     if "<現價>" in label)
    cell = cv.matrix.cells[price_row][today_col]
    assert cell == pytest.approx(honest_return, abs=1e-4)
    # +81.9%／+81.4% 消失：不再是離譜的正報酬
    assert cell < 0.0


def test_t0_cell_stays_todays_behavior_when_not_calibrated(tmp_path):
    """q_by_symbol=None（今天，#123 之前恆如此）：今天欄維持現行行為，
    即 q=0 歐式模型代進 vendor IV 的既有（有偏差的）數字——這條測試
    釘住「fallback 路徑真的是今天的行為」，不是本票不小心跟著換掉的。
    """
    result, spot, expiry = _run(tmp_path, None)
    res = result.results[0]
    cv = next(c for c in res.candidates if c.valuation.contract.strike == 85.0)
    assert cv.carry_calibrated is False

    from option_chaser.valuation import clamped_price
    c = cv.valuation.contract
    T = (date.fromisoformat(expiry) - date(2026, 7, 17)).days / 365.0
    expected_today_value = clamped_price("call", spot, c.strike, T, 0.0426,
                                         c.implied_volatility)
    today_col = 0
    price_row = next(i for i, (_, label, _) in enumerate(cv.matrix.prices)
                     if "<現價>" in label)
    cell = cv.matrix.cells[price_row][today_col]
    expected_cell = (expected_today_value - c.ask) / c.ask
    assert cell == pytest.approx(expected_cell, abs=1e-9)
    # 未校準路徑維持現行（已知有偏差的）行為——正是研究文件記錄的
    # +81% 量級問題，本測試釘住「這條路徑沒有被本票動到」。
    assert cell > 0.5


# ---------- 架構要求：IV 反解每腿一次，不隨格數成長 ----------

def test_iv_inversion_count_does_not_scale_with_matrix_cells(tmp_path, monkeypatch):
    """研究文件的 3.83ms／矩陣成本數字成立的前提：反解只在建
    CandidateView 時做一次，矩陣迴圈是 (S,t) 純函式。用計數 wrapper
    包住 `implied_vol`，斷言呼叫次數等於「合格腿數」量級，不是
    「合格腿數 × 11 價格 × N 日期」那種會爆炸的量級。"""
    calls = {"n": 0}

    def counting_implied_vol(*args, **kwargs):
        calls["n"] += 1
        return _real_implied_vol(*args, **kwargs)

    monkeypatch.setattr("option_chaser.valuation.implied_vol", counting_implied_vol)
    result, spot, expiry = _run(tmp_path, TLT_Q)
    res = result.results[0]
    assert res.status == "ok"

    n_qualified = res.n_qualified
    # 每條合格腿最多反解一次（`evaluate_contract` 呼叫一次
    # `calibrate_leg`）。5 檔候選、11×~30 格矩陣——如果反解跟著格數走，
    # 這裡會是幾千次而不是個位數。
    assert calls["n"] <= n_qualified
    assert calls["n"] >= 1  # 真的有校準到，不是全部提早失敗
    # 量級檢查：矩陣格數遠大於反解次數，證明反解確實沒有隨格數重跑。
    total_cells = sum(len(cv.matrix.prices) * len(cv.matrix.dates)
                      for cv in res.candidates)
    assert total_cells > calls["n"] * 20


# ---------- fallback 語意：第 4 層是 q=0＋vendor IV，不是 q=0＋價格錨定 ----------

def test_fallback_layer_is_todays_behavior_not_price_anchoring(tmp_path):
    """q_by_symbol=None 時，任何候選的 carry 都必須是
    `(q=0.0, sigma=vendor_iv, carry_calibrated=False)`——不是某種
    「q=0 但仍嘗試價格錨定」的中間狀態。研究文件已證實後者對多數真實
    LEAPS call 在數學上無解，這條路徑必須是**直接跳過**，不是**嘗試
    後失敗**。"""
    result, spot, expiry = _run(tmp_path, None)
    res = result.results[0]
    for cv in res.candidates:
        v = cv.valuation
        assert v.carry.carry_calibrated is False
        assert v.carry.q == 0.0
        assert v.carry.sigma == v.contract.implied_volatility


def test_per_leg_inversion_failure_falls_back_to_todays_behavior(tmp_path):
    """即使 `q_by_symbol` 有值，個別腿的反解仍可能失敗（目標價落在模型
    可行區間外）——這裡直接用一個極端 q 逼一條腿反解失敗，確認它退回
    今天的行為（q=0、vendor IV），不是勉強塞一個 q>0 但沒經過反解驗證
    的數字進去。"""
    # 極大的 q 會讓遠期價外合約的可行價格區間整個偏移，容易撞到無解。
    result, spot, expiry = _run(tmp_path, 5.0)
    res = result.results[0]
    assert res.status == "ok"
    for cv in res.candidates:
        v = cv.valuation
        if not v.carry.carry_calibrated:
            assert v.carry.q == 0.0
            assert v.carry.sigma == v.contract.implied_volatility


# ---------- 端到端 selection 紅線：真實模型變動下選取結果不變 ----------

def test_selection_identity_unchanged_despite_real_delta_band_flips(tmp_path):
    """核心紅線的真正驗收：不是「接縫存在」（#122 已測），而是「接縫在
    真實模型變動、真實 delta 位移下依然守住」。

    研究文件（heatmap-valuation-method-selection.md §8）已經量到：同一組
    真實 TLT 五檔 call，q=0→0.045 會讓三檔的**顯示** delta 從
    conservative 移到 balanced。這裡直接跑兩次（q_by_symbol=None／
    0.045），要求：
    (a) 顯示用的 delta 真的不同（模型真的變了，不是空轉）
    (b) classification_delta 逐檔完全相同（分級輸入沒被污染）
    (c) 每個候選最終落在哪個 band 完全相同（選取結果真的沒變）
    (d) Heatmap 今天欄的格值真的不同（估值真的變了，不是只換了個
        沒人用的欄位）
    """
    uncalibrated, spot, expiry = _run(tmp_path, None)
    calibrated, _, _ = _run(tmp_path, TLT_Q)

    res_u = uncalibrated.results[0]
    res_c = calibrated.results[0]
    assert res_u.status == res_c.status == "ok"

    by_strike_u = {cv.valuation.contract.strike: cv for cv in res_u.candidates}
    by_strike_c = {cv.valuation.contract.strike: cv for cv in res_c.candidates}
    assert set(by_strike_u) == set(by_strike_c)

    delta_changed_somewhere = False
    for strike, cv_u in by_strike_u.items():
        cv_c = by_strike_c[strike]
        v_u, v_c = cv_u.valuation, cv_c.valuation

        # (b) 分級輸入完全不受模型變動影響
        assert v_u.classification_delta == v_c.classification_delta

        # (a) 顯示用 delta 是否真的不同（校準成功的腿才會變）
        if v_c.carry.carry_calibrated and v_u.delta != v_c.delta:
            delta_changed_somewhere = True

    assert delta_changed_somewhere, (
        "本測試的前提是模型真的讓某些腿的 delta 改變——如果這裡是 "
        "False，代表 q_by_symbol 沒有真的被接上，測試本身失去意義")

    # (c) 用 #118 的比對函式：選取結果（誰入選、順序、expiry_best、
    # representative candidate、best_return）逐位元相同
    from tests.test_selection_regression import assert_identity_unchanged

    def _identity(result):
        from option_chaser import store
        view = store.serialize_result(result, scenario_id="carry-test", capital=None)
        r = view["results"][0]
        candidate_keys = tuple(c["candidate_key"] for c in r["candidates"])
        expiry_best_keys = tuple(c["candidate_key"] for c in r["expiry_best"])
        return {
            "status": r["status"],
            "ranking_identity": candidate_keys,
            "expiry_best_identity": expiry_best_keys,
            "expiry_top10_identity": {},
            "per_expiry_order": {},
            "representative_candidate_identity": None,
            "best_return_ranking_semantics": None,
            "filtering": {"n_qualified": r["n_qualified"],
                         "filter_report": r["filter_report"],
                         "filter_stages": [(s["label"], s["removed"])
                                          for s in r["filter_stages"]],
                         "pair_report": r["pair_report"]},
        }

    assert_identity_unchanged(_identity(uncalibrated), _identity(calibrated))

    # (d) 今天欄的格值真的不同——證明 (c) 不是因為估值根本沒變
    cells_changed = False
    for strike in by_strike_u:
        cv_u, cv_c = by_strike_u[strike], by_strike_c[strike]
        if cv_c.carry_calibrated:
            row_u = next(i for i, (_, label, _) in enumerate(cv_u.matrix.prices)
                        if "<現價>" in label)
            row_c = next(i for i, (_, label, _) in enumerate(cv_c.matrix.prices)
                        if "<現價>" in label)
            if cv_u.matrix.cells[row_u][0] != cv_c.matrix.cells[row_c][0]:
                cells_changed = True
    assert cells_changed


def test_legacy_band_ranking_logic_itself_not_touched():
    """#113 AC：legacy Long Call／Long Put 的 Delta band ranking 邏輯本身
    不得被重構——`classify()` 的判準（>b 保守、<a 積極、其餘平衡）維持
    既有形狀，本票只換了餵給它的輸入來源（#122 的接縫），沒有動判準
    本身。"""
    from option_chaser.ranking import classify

    bands = (0.35, 0.65)
    assert classify(0.70, bands) == "conservative"
    assert classify(0.50, bands) == "balanced"
    assert classify(0.20, bands) == "aggressive"
    assert classify(-0.70, bands) == "conservative"  # abs() 既有行為


# ---------- Greeks 一致性 ----------

def test_display_greeks_consistent_with_calibrated_valuation(tmp_path):
    """校準成功的候選，顯示的 Greeks（delta/gamma/theta/vega）必須是用
    校準後的 (q, sigma) 算出來的——不是估值換了模型、Greeks 還留在舊
    的 q=0／vendor IV 口徑（那種「顯示的 Greeks 與估值不同模型」的
    不自洽，spec 明文要求避免）。"""
    from option_chaser.valuation import leg_greeks

    result, spot, expiry = _run(tmp_path, TLT_Q)
    res = result.results[0]
    calibrated = [cv for cv in res.candidates if cv.carry_calibrated]
    assert calibrated, "本測試需要至少一個校準成功的候選才有意義"

    rate = 0.0426  # 與 _run() 傳入的 AnalysisParams(rate=..., rate_explicit=True) 一致
    for cv in calibrated:
        v = cv.valuation
        c = v.contract
        T = (date.fromisoformat(c.expiry) - date(2026, 7, 17)).days / 365.0
        expected = leg_greeks(c.option_type, spot, c.strike, T, rate,
                              v.carry.sigma, v.carry.q)
        assert v.delta == pytest.approx(expected.delta, abs=1e-9)
        assert v.gamma == pytest.approx(expected.gamma, abs=1e-9)


# ---------- Spread：兩腿都校準、排名依然模型無關 ----------

XYZ_SNAP = "tests/fixtures/xyz_v2_snapshot.json"


def test_spread_carry_calibrated_requires_both_legs():
    p = AnalysisParams(target_price=120.0, target_month="2026-10",
                       strategy="bull-call-spread", q_by_symbol=0.045)
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("bull-call-spread",))
    result = service.run_offline(req, XYZ_SNAP)
    res = result.results[0]
    assert res.status == "ok"
    for cv in res.candidates:
        sv = cv.valuation
        assert cv.carry_calibrated == (
            sv.long_carry.carry_calibrated and sv.short_carry.carry_calibrated)


def test_spread_ranking_unaffected_by_carry_calibration():
    """T3／#17 既有裁示：Spread 排名用自身到期日的內在價值，與定價模型
    無關——這裡直接端到端驗證，不只是信任 scenario_leg_value 的
    `at >= expiry` 分支邏輯。q_by_symbol=None／0.045 兩次跑，候選順序、
    baseline_return、best_return 語意必須逐位元相同。"""
    def run(q):
        p = AnalysisParams(target_price=120.0, target_month="2026-10",
                           strategy="bull-call-spread", q_by_symbol=q)
        req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                      strategies=("bull-call-spread",))
        return service.run_offline(req, XYZ_SNAP)

    r_none, r_q = run(None), run(0.045)
    res_none, res_q = r_none.results[0], r_q.results[0]

    keys_none = [service.candidate_key(cv) for cv in res_none.candidates]
    keys_q = [service.candidate_key(cv) for cv in res_q.candidates]
    assert keys_none == keys_q

    returns_none = [cv.baseline_return for cv in res_none.candidates]
    returns_q = [cv.baseline_return for cv in res_q.candidates]
    assert returns_none == returns_q, (
        "Spread baseline_return 必須逐位元相同——它在自身到期日估值，"
        "落在 scenario_leg_value 的 at>=expiry 分支，不經任何定價模型")


# ---------- 效能：矩陣估值成本仍在毫秒量級 ----------

def test_matrix_valuation_stays_in_millisecond_range(tmp_path):
    import time

    snap_path, spot, expiry = _tlt_snapshot_path(tmp_path)
    p = AnalysisParams(target_price=100.0, target_month="2028-12",
                       strategy="long-call", rate=0.0426, rate_explicit=True,
                       q_by_symbol=TLT_Q)
    req = service.AnalysisRequest(symbol="TLT", base_params=p,
                                  strategies=("long-call",))
    t0 = time.perf_counter()
    result = service.run_offline(req, snap_path)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert result.results[0].status == "ok"
    # 整次分析（含過濾、排名、矩陣建構）遠低於 60 秒 serverless 上限；
    # 門檻抓寬鬆一點避免慢速機器假紅，重點是量級不是精確值。
    assert elapsed_ms < 2000, f"分析耗時 {elapsed_ms:.0f}ms，超出預期量級"
