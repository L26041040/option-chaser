"""LIVE-T1（#397）：Yahoo upgradeDowngradeHistory 真實資料來源。

測試全部用 `tests/fixtures/yahoo/` 裡**錄下的真實 Yahoo 回應**（2026-11-22
錄製，不含任何秘密），HTTP 層由假 transport 回放，測試本身不連外。期望值
是用獨立的一次性腳本直接數 fixture 得出的字面常數，不是拿 adapter 自己算。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from api_app.analyst_source import YahooAnalystSource
from option_chaser.data.yahoo_analyst import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures" / "yahoo"
TODAY = date(2026, 11, 20)


class ReplayTransport:
    """依 URL 回放錄下的回應；記錄每次請求，讓測試看得到呼叫順序。"""

    def __init__(self, *, crumb_status: int = 200, summary_statuses=None):
        self.calls: list[str] = []
        self.crumb_status = crumb_status
        self.summary_statuses = list(summary_statuses or [])

    def get(self, url: str) -> HttpResponse:
        self.calls.append(url)
        if "getcrumb" in url:
            return HttpResponse(self.crumb_status, "crumbXYZ", {})
        if "fc.yahoo.com" in url:
            return HttpResponse(404, "", {})
        symbol = url.split("?")[0].rstrip("/").split("/")[-1]
        if "quoteSummary" in url:
            if self.summary_statuses:
                status, headers = self.summary_statuses.pop(0)
                if status != 200:
                    return HttpResponse(status, '{"finance":{"error":{}}}', headers)
            path = FIXTURES / f"{symbol}.quote_summary.json"
        else:
            path = FIXTURES / f"{symbol}.chart.json"
        if not path.exists():
            return HttpResponse(404, '{"quoteSummary":{"result":null,"error":'
                                     '{"code":"Not Found","description":"Quote not found"}}}', {})
        return HttpResponse(200, path.read_text(encoding="utf-8"), {})


def _fetch(symbol: str, **kw):
    transport = ReplayTransport(**kw)
    return YahooAnalystSource(transport=transport).fetch(symbol, TODAY), transport


def test_aapl_returns_every_real_firm_target_and_drops_rating_only_rows():
    result, _ = _fetch("AAPL")
    assert result.error is None
    # fixture：971 列，其中 950 列帶目標價（21 列只有評級 → 丟棄）
    assert len(result.records) == 950
    assert len({r.firm for r in result.records}) == 58
    assert all(r.target_price > 0 for r in result.records)
    assert min(r.published_on for r in result.records) == date(2012, 9, 12)
    assert result.coverage == "partial"          # Yahoo 沒有「終止覆蓋」事件
    assert result.history_from == date(2012, 9, 12)


def test_cross_check_carries_yahoo_consensus_only_for_audit():
    result, _ = _fetch("AAPL")
    assert result.cross_check.consensus_mean_from_source == Decimal("345.6313")
    assert result.cross_check.n_from_source == 39


def test_split_calendar_comes_from_the_free_chart_events():
    result, _ = _fetch("NVDA")
    assert [(s.effective_on, s.ratio) for s in result.splits] == [
        (date(2021, 7, 20), Decimal(4)), (date(2024, 6, 10), Decimal(10))]
    no_split, _ = _fetch("BABA")
    assert no_split.splits == ()


# --- 分割基準：Yahoo 的目標價有些已換成分割後的數字、有些沒有 ---------------

def _record(result, firm, published_on):
    [r] = [r for r in result.records if r.firm == firm and r.published_on == published_on]
    return r


def test_each_target_is_tagged_with_the_split_basis_it_was_written_in():
    result, _ = _fetch("AAPL")
    # 2020-08-31 4:1 分割前三週：富國寫 121.25（已是分割後基準）、美銀寫 470（分割前）
    wells = _record(result, "Wells Fargo", date(2020, 8, 5))
    bofa = _record(result, "B of A Securities", date(2020, 8, 5))
    assert wells.target_price == Decimal("121.25")
    assert wells.split_adjusted_through == date(2020, 8, 31)
    assert bofa.target_price == Decimal("470")
    assert bofa.split_adjusted_through is None
    # 分割之後發布的紀錄本來就是新基準，不需要標記
    after = [r for r in result.records if r.published_on > date(2020, 8, 31)]
    assert all(r.split_adjusted_through is None for r in after)


def test_consensus_across_a_split_does_not_blow_up_with_mixed_bases():
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    result, _ = _fetch("AAPL")
    rules = ConsensusRules(h_min=1)
    # 分割生效前一個交易日：有效集合混著兩種基準；換算後應是正常的分歧度
    # 當時股價約 500（週線 124.81×4）、分割後基準約 125；兩種基準混算是 235。
    before = compute_snapshot(result.records, result.splits, date(2020, 8, 28), rules)
    assert before.status == "ok"                 # 不再被判成 split_unresolved
    assert before.mean > Decimal(250)            # 落在分割前基準
    after = compute_snapshot(result.records, result.splits, date(2020, 9, 30), rules)
    assert after.status == "ok"
    assert after.mean < Decimal(125)             # 分割後基準


@pytest.mark.parametrize("as_of, low, high", [
    # 分割前股價約 500：換錯基準的目標價會落在 ~125（少一個 4 倍）或 ~2000
    (date(2020, 8, 28), Decimal(150), Decimal(1000)),
    # 分割後股價約 115：換錯會落在 ~30 或 ~500
    (date(2020, 9, 30), Decimal(40), Decimal(250)),
])
def test_no_adjusted_target_is_off_by_a_split_factor(as_of, low, high):
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    result, _ = _fetch("AAPL")
    snap = compute_snapshot(result.records, result.splits, as_of, ConsensusRules(h_min=1))
    assert snap.n_analysts >= 20
    # high／low＝有效集合換算分割後的最高／最低個別目標價
    assert low < snap.low and snap.high < high, (snap.low, snap.high)


def test_renamed_firms_count_as_one_analyst_through_the_engine_alias_table():
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    from option_chaser.data.yahoo_analyst import FIRM_ALIASES
    result, _ = _fetch("AAPL")
    # Adapter 不改名：analyst_key 就是 Yahoo 的券商名稱
    assert all(r.analyst_key == r.firm for r in result.records)
    # 2020-05-01 同一天出現「Nomura」與「Nomura Instinet」兩筆（同一研究部門）
    as_of = date(2020, 5, 29)
    plain = compute_snapshot(result.records, result.splits, as_of, ConsensusRules(h_min=1))
    merged = compute_snapshot(result.records, result.splits, as_of,
                              ConsensusRules(h_min=1, aliases=FIRM_ALIASES))
    assert merged.n_analysts == plain.n_analysts - 1


# --- 新鮮度與覆蓋缺口（真實樣本） ---------------------------------------------

def test_coverage_gap_is_visible_against_yahoos_own_analyst_count():
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    result, _ = _fetch("AAPL")
    snap = compute_snapshot(result.records, result.splits, TODAY, ConsensusRules(),
                            coverage=result.coverage, cross_check=result.cross_check)
    # Yahoo 自家共識 39 人；事件史只收有發布動作的券商 → 有效人數較少，照實標示
    assert snap.coverage == "partial"
    assert snap.cross_check.n_from_source == 39
    assert 5 <= snap.n_analysts < 39


def test_targets_not_refreshed_recently_are_flagged_stale():
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    result, _ = _fetch("BABA")
    # BABA 2014-09 上市，券商集中在上市後啟動覆蓋：一個月後大多是新目標價，
    # 隔年 2 月時大多已超過 90 天沒更新 → stale（真實歷史狀態，不是編的日期）
    fresh = compute_snapshot(result.records, result.splits, date(2014, 11, 15), ConsensusRules())
    assert fresh.freshness_share >= Decimal("0.5")
    stale = compute_snapshot(result.records, result.splits, date(2015, 2, 15), ConsensusRules())
    assert stale.status == "stale"
    assert stale.freshness_share < Decimal("0.5")


# --- 失敗處理：回報原因，不丟例外、不讓整批失敗 -------------------------------

def test_expired_crumb_is_refreshed_once_and_the_fetch_succeeds():
    result, transport = _fetch("AAPL", summary_statuses=[(401, {}), (200, {})])
    assert result.error is None and len(result.records) == 950
    assert sum("getcrumb" in u for u in transport.calls) == 2


def test_rate_limit_is_reported_with_the_retry_after_hint():
    result, _ = _fetch("AAPL", summary_statuses=[(429, {"Retry-After": "120"})])
    assert result.records == ()
    assert "429" in result.error and "120" in result.error


def test_unknown_symbol_is_reported_as_no_analyst_data():
    result, _ = _fetch("ZZZZQ")
    assert result.records == ()
    assert "沒有這個 symbol" in result.error


def test_crumb_endpoint_refusal_is_a_reported_failure():
    result, _ = _fetch("AAPL", crumb_status=403)
    assert result.records == () and "crumb" in result.error


def test_connection_failure_is_a_reported_failure():
    class Down:
        def get(self, url):
            raise TimeoutError("connect to internal-proxy.corp:3128 timed out")
    result = YahooAnalystSource(transport=Down()).fetch("AAPL", TODAY)
    assert result.records == () and "逾時" in result.error
    assert "internal-proxy" not in result.error          # 不外洩例外原文（#345 B-3）


def test_truncated_response_is_a_reported_failure():
    import http.client

    class Truncated:
        def get(self, url):
            raise http.client.IncompleteRead(b"{", 100)
    result = YahooAnalystSource(transport=Truncated()).fetch("AAPL", TODAY)
    assert result.records == () and result.error


# --- 接線：部署環境預設啟用，緊急關閉開關可回到「尚未設定」 -------------------

def test_deployed_app_uses_the_real_source_by_default(monkeypatch):
    from api_app.analyst_source import analyst_source_from_env
    monkeypatch.delenv("OC_ANALYST_SOURCE", raising=False)
    source = analyst_source_from_env()
    assert isinstance(source, YahooAnalystSource) and source.is_fixture is False


@pytest.mark.parametrize("value", ["yahoo", "Yahoo", "on", ""])
def test_explicit_enable_values_keep_the_real_source(monkeypatch, value):
    from api_app.analyst_source import analyst_source_from_env
    monkeypatch.setenv("OC_ANALYST_SOURCE", value)
    assert isinstance(analyst_source_from_env(), YahooAnalystSource)


@pytest.mark.parametrize("value", ["off", "OFF", "none", "disabled", "of", "yahooo"])
def test_kill_switch_and_typos_return_to_not_configured(monkeypatch, value):
    from api_app.analyst_source import analyst_source_from_env
    monkeypatch.setenv("OC_ANALYST_SOURCE", value)
    assert analyst_source_from_env() is None             # 寧可關掉也不誤開


# --- 分割基準的邊界：比例太小不判、反向合股照判 -------------------------------

def _target(price, published_on):
    from option_chaser.data.yahoo_analyst import RawTarget
    return RawTarget(firm="X", target_price=Decimal(price), published_on=published_on,
                     action=None, prior_target=None)


def _weekly(day, adjusted_close):
    return ((day, Decimal(adjusted_close)),)


def test_small_split_ratios_are_not_guessed():
    from option_chaser.data.yahoo_analyst import RawSplit, split_basis_through
    split = RawSplit(date(2024, 3, 1), Decimal("1.5"))          # 3:2
    # 分割前股價 150（調整後收盤 100）；看空目標 112 介於兩種基準之間 → 不猜
    assert split_basis_through(_target("112", date(2024, 2, 1)), (split,),
                               _weekly(date(2024, 1, 29), "100")) is None


def test_reverse_split_basis_is_detected():
    from option_chaser.data.yahoo_analyst import RawSplit, split_basis_through
    reverse = RawSplit(date(2024, 3, 1), Decimal("0.1"))        # 1:10 合股
    weekly = _weekly(date(2024, 1, 29), "50")                   # 調整後 50 → 當時實際 5
    assert split_basis_through(_target("6", date(2024, 2, 1)), (reverse,), weekly) is None
    assert split_basis_through(_target("60", date(2024, 2, 1)), (reverse,), weekly) \
        == date(2024, 3, 1)


def test_missing_price_week_leaves_the_target_as_raw():
    from option_chaser.data.yahoo_analyst import RawSplit, split_basis_through
    split = RawSplit(date(2024, 3, 1), Decimal(4))
    assert split_basis_through(_target("120", date(2024, 2, 1)), (split,), ()) is None


# --- 格式異常：壞掉的列跳過、整體結構不對才報錯，都不丟例外 -----------------

def test_malformed_rows_are_skipped_not_raised():
    import json
    from option_chaser.data.yahoo_analyst import parse_quote_summary
    body = json.dumps({"quoteSummary": {"result": [{"upgradeDowngradeHistory": {"history": [
        "not-a-row",
        {"firm": "A", "currentPriceTarget": "abc", "epochGradeDate": 1700000000},
        {"firm": "B", "currentPriceTarget": 100, "epochGradeDate": "soon"},
        {"firm": "C", "currentPriceTarget": -5, "epochGradeDate": 1700000000},
        {"firm": "D", "currentPriceTarget": 120, "epochGradeDate": 1700000000},
    ]}}]}})
    summary = parse_quote_summary(body)
    assert [t.firm for t in summary.targets] == ["D"]
    assert summary.history_rows == 5


@pytest.mark.parametrize("body", ["<html>blocked</html>", '{"quoteSummary": {"result": [{}]}}'])
def test_unexpected_shape_is_a_reported_failure(body):
    class Odd(ReplayTransport):
        def get(self, url):
            if "quoteSummary" in url:
                self.calls.append(url)
                return HttpResponse(200, body, {})
            return super().get(url)
    result = YahooAnalystSource(transport=Odd()).fetch("AAPL", TODAY)
    assert result.records == () and result.error


def test_bad_split_entries_are_skipped():
    import json
    from option_chaser.data.yahoo_analyst import parse_chart
    body = json.dumps({"chart": {"result": [{
        "events": {"splits": {"a": {"numerator": 4, "denominator": 1},
                              "b": {"date": 1598880600, "numerator": 4, "denominator": 1}}},
        "timestamp": [1598880600, "x"], "indicators": {"quote": [{"close": [120.0, None]}]}}]}})
    splits, weekly = parse_chart(body)
    assert [(s.effective_on, s.ratio) for s in splits] == [(date(2020, 8, 31), Decimal(4))]
    assert len(weekly) == 1


def test_unparseable_retry_after_is_ignored():
    result, _ = _fetch("AAPL", summary_statuses=[(429, {"Retry-After": "inf"})])
    assert "429" in result.error and "Retry-After" not in result.error
