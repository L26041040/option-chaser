"""#123（spec #117 §2）接線：`_resolve_q` 的三層 fallback 一路傳到
`AnalysisParams.q_by_symbol`／三態揭露欄位／報告文字。全部離線（loader
為注入的假物件）。"""
from datetime import date

import pytest

from option_chaser import service
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.models import AnalysisParams

SNAP = "tests/fixtures/xyz_v4_six_expiries.json"
SPOT = 100.0   # 見 fixture


def _request():
    return service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08"),
        strategies=("long-call",))


def _history(amount=4.0, source="yahoo", stale=False, as_of="2026-07-14"):
    return DividendHistory(symbol="XYZ", as_of=as_of, source=source, stale=stale,
                           distributions=(DividendRecord("2026-06-01", amount),))


# ---------- 三層 fallback → q_by_symbol ----------

def test_no_loader_leaves_q_by_symbol_none():
    """離線重放（無 loader）：q 管線不啟用，走既有行為，不是 layer 4
    的「fetch 失敗」——兩者對使用者是同一句話，但語意不同（無 note）。"""
    result = service.run_offline(_request(), SNAP)
    p = result.request.base_params
    assert p.q_by_symbol is None
    assert p.q_note == ""
    assert "無股利調整" in result.results[0].report_text


def test_successful_fetch_with_distributions_computes_q_from_this_snapshots_spot():
    def loader(symbol, today):
        assert symbol == "XYZ"
        return _history(amount=4.0), "配息資料 yahoo（2026-07-14，1 筆）"

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    p = result.request.base_params
    assert p.q_by_symbol == pytest.approx(4.0 / SPOT)
    assert p.q_source == "yahoo"
    assert p.q_as_of == "2026-07-14"
    assert p.q_stale is False
    assert f"q={p.q_by_symbol * 100:.1f}%" in result.results[0].report_text
    assert "來源 yahoo" in result.results[0].report_text


def test_confirmed_no_dividends_yields_q_zero_not_none():
    """研究 §8 第 2 層：抓到、確定無配息 → q=0，狀態仍是 fresh，不是
    退回 None（那是第 4 層的語意，兩者不可混淆）。"""
    empty_history = DividendHistory(symbol="XYZ", as_of="2026-07-14",
                                    source="yahoo", distributions=())

    def loader(symbol, today):
        return empty_history, "配息資料 yahoo（2026-07-14，0 筆）"

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    p = result.request.base_params
    assert p.q_by_symbol == 0.0
    assert p.q_by_symbol is not None   # 明確不是「未取得」
    assert p.q_stale is False


def test_fetch_failure_with_no_cache_leaves_q_by_symbol_none_with_a_note():
    """fallback 第 4 層：loader 回 (None, note) → q_by_symbol 維持
    None（走今天的完整行為），但 q_note 說得出原因。"""
    def loader(symbol, today):
        return None, "配息資料不可得"

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    p = result.request.base_params
    assert p.q_by_symbol is None
    assert p.q_note == "配息資料不可得"
    assert "無股利調整" in result.results[0].report_text


def test_stale_cached_history_is_recomputed_against_this_snapshots_spot():
    """fallback 第 3 層：抓取失敗但快取在窗內——q 仍然用**這次快照的
    spot**現算，不是快取時當初的 spot（研究 §7.5：快取的是金額，不是
    比例）。"""
    def loader(symbol, today):
        return (_history(amount=4.0, stale=True, as_of="2026-07-01"),
                "配息資料 yahoo（快取於 2026-07-01）")

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    p = result.request.base_params
    assert p.q_by_symbol == pytest.approx(4.0 / SPOT)   # 用本次快照 spot=100.0
    assert p.q_stale is True
    assert p.q_as_of == "2026-07-01"
    assert "STALE" in result.results[0].report_text


def test_loader_is_called_with_the_snapshots_symbol_and_todays_market_day():
    calls = []

    def loader(symbol, today):
        calls.append((symbol, today))
        return None, "配息資料不可得"

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    assert calls == [("XYZ", result.today)]


# ---------- carry_calibrated 沿路串到候選（#113 既有接縫的驗收） ----------

def test_q_from_pipeline_flows_into_candidate_carry_calibrated_flag():
    """端到端：#123 解出的 q 真的餵進 #113 既有的 `calibrate_leg`——
    至少一個候選被標記 carry_calibrated=True，不是接線接假的。"""
    def loader(symbol, today):
        return _history(amount=4.0), "配息資料 yahoo（2026-07-14，1 筆）"

    result = service.run_offline(_request(), SNAP, dividend_loader=loader)
    candidates = result.results[0].candidates
    assert candidates, "測試資料應至少有一組候選"
    assert any(cv.carry_calibrated for cv in candidates)
