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


def test_renamed_firms_count_as_one_analyst():
    aapl, _ = _fetch("AAPL")
    keys = {r.firm: r.analyst_key for r in aapl.records}
    assert keys["Cowen & Co."] == keys["TD Cowen"] == "TD Cowen"
    nomura = {r.analyst_key for r in aapl.records if r.firm.startswith("Nomura")}
    assert nomura == {"Nomura"}
    nvda, _ = _fetch("NVDA")
    keys = {r.firm: r.analyst_key for r in nvda.records}
    assert keys["SunTrust Robinson Humphrey"] == "Truist Securities"


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


def test_targets_left_unrefreshed_for_months_are_flagged_stale():
    from option_chaser.consensus import ConsensusRules, compute_snapshot
    result, _ = _fetch("BABA")
    # 錄製後 8 個月都沒有新資料 → 近 90 天內更新的比例為 0 → stale
    later = date(2027, 7, 20)
    snap = compute_snapshot(result.records, result.splits, later, ConsensusRules())
    assert snap.status in ("stale", "insufficient_analysts")
    assert snap.status != "ok"


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
            raise TimeoutError("timed out")
    result = YahooAnalystSource(transport=Down()).fetch("AAPL", TODAY)
    assert result.records == () and "逾時" in result.error


# --- 接線：部署環境預設啟用，緊急關閉開關可回到「尚未設定」 -------------------

def test_deployed_app_uses_the_real_source_by_default(monkeypatch):
    from api_app.analyst_source import analyst_source_from_env
    monkeypatch.delenv("OC_ANALYST_SOURCE", raising=False)
    source = analyst_source_from_env()
    assert isinstance(source, YahooAnalystSource) and source.is_fixture is False


@pytest.mark.parametrize("value", ["off", "OFF", "none", "disabled"])
def test_kill_switch_returns_to_not_configured(monkeypatch, value):
    from api_app.analyst_source import analyst_source_from_env
    monkeypatch.setenv("OC_ANALYST_SOURCE", value)
    assert analyst_source_from_env() is None
