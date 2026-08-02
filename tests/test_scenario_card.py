"""T5（#19）／需求五: 劇本卡片模型（純函式，零 Streamlit）。

卡片恰五項：標的／目標價／目標年月／目前最高「目標達成並持有至到期收益率」／
一個燈號位置。收益率取自該次分析結果已預算好的 baseline_return，卡片層不做
任何金融計算。QA1-03（#30）：取值範圍限定 baseline 期（最接近目標年月的
到期日）自己的候選，不是全部到期日的全域最大值——與 Step 2 主圖同一口徑。
"""
import dataclasses
from datetime import date

from option_chaser import workspace
from option_chaser.store import Scenario

TS = "2026-07-21T00:00:00+00:00"
NOT_OVER = date(2028, 1, 15)   # 2028-01 尚未過完
OVER = date(2028, 2, 1)        # 2028-01 已過完

SC = Scenario(schema_version=2, id="XYZ-120-202801", symbol="XYZ",
              direction="bullish", target_price=120.0, target_month="2028-01",
              created_at=TS, notes="", group_id="G-XYZ", status="Active",
              strategies=("bull-call-spread",))


def _view(*, groups=(), baseline_expiry=None):
    """groups: [(expiry, [baseline_return, ...]), ...]——每個到期日一組候選，
    卡片層只讀得到 `candidate.baseline_return`，其餘欄位無關。"""
    return {
        "baseline_expiry": baseline_expiry,
        "expiry_groups": [
            {"expiry": exp,
             "rows": [{"candidate": {"baseline_return": r}} for r in returns]}
            for exp, returns in groups],
    }


def test_card_carries_exactly_the_five_display_fields():
    view = _view(groups=[("2028-01", [1.2])], baseline_expiry="2028-01")
    card = workspace.card_of(SC, view)
    assert {f.name for f in dataclasses.fields(card)} == {
        "id", "symbol", "target_price", "target_month", "best_return", "signal"}
    assert (card.symbol, card.target_price, card.target_month) == (
        "XYZ", 120.0, "2028-01")
    assert card.id == SC.id


def test_best_return_is_the_max_within_the_baseline_expiry_only():
    """QA1-03（#30）迴歸測試：較早到期日報酬更高時不得取代 baseline 期的
    數字——先前的缺陷正是誤取全部到期日的全域最大值。"""
    view = _view(groups=[("2026-11", [9.9]), ("2027-01", [2.1, 0.4])],
                baseline_expiry="2027-01")
    assert workspace.card_of(SC, view).best_return == 2.1


def test_no_snapshot_yet_shows_no_return():
    """附錄 A8.1：尚無任何成功快照的劇本，收益率顯示「—」。"""
    assert workspace.card_of(SC, None).best_return is None


def test_zero_candidate_in_baseline_expiry_shows_no_return():
    """附錄 A10.2：baseline 期抓取成功但過濾後零候選，收益率同樣是「—」
    （不是 0%），不得借用其他到期日的候選。"""
    view = _view(groups=[("2027-01", [])], baseline_expiry="2027-01")
    assert workspace.card_of(SC, view).best_return is None


def test_baseline_expiry_missing_from_groups_shows_no_return():
    """baseline 期本身零合格候選、或鏈上零到期日時不在 `expiry_groups`
    裡——同樣顯示「—」，不落回其他到期日（附錄A8.5、A12）。"""
    view = _view(groups=[("2026-11", [9.9])], baseline_expiry="2027-01")
    assert workspace.card_of(SC, view).best_return is None


def test_negative_best_return_is_reported_as_is():
    """全部虧損時照實回報負值（卡片上以紅色呈現），不夾成 0 也不變成「—」。"""
    view = _view(groups=[("2028-01", [-0.31, -0.72])], baseline_expiry="2028-01")
    assert workspace.card_of(SC, view).best_return == -0.31


def test_never_refreshed_scenario_shows_unknown_signal():
    """尚無任何一次刷新（成功或失敗）→ 燈號中性佔位，不是三色之一。"""
    assert workspace.card_of(SC, None, observed=NOT_OVER).signal == \
        workspace.SIGNAL_UNKNOWN


def test_successful_refresh_shows_green():
    view = _view(groups=[("2028-01", [1.2])], baseline_expiry="2028-01")
    card = workspace.card_of(SC, view, observed=NOT_OVER)
    assert card.signal == workspace.SIGNAL_GREEN


def test_critical_failure_shows_yellow_even_with_a_prior_view():
    """關鍵資料失敗 → 黃燈，即使仍有（舊的）成功快照可顯示。"""
    view = _view(groups=[("2028-01", [1.2])], baseline_expiry="2028-01")
    card = workspace.card_of(SC, view, observed=NOT_OVER, critical_failure=True)
    assert card.signal == workspace.SIGNAL_YELLOW


def test_month_over_is_red_regardless_of_view_or_failure():
    """需求六：紅燈優先於綠與黃——月份過完的劇本不會因為有快照而偽裝成綠燈，
    也不會因為同時發生刷新失敗而被誤判成只是黃燈。"""
    view = _view(groups=[("2028-01", [1.2])], baseline_expiry="2028-01")
    assert workspace.card_of(SC, view, observed=OVER).signal == \
        workspace.SIGNAL_RED
    assert workspace.card_of(
        SC, None, observed=OVER, critical_failure=True).signal == \
        workspace.SIGNAL_RED


def test_individual_quote_failure_still_shows_green():
    """需求六關鍵分層：個別合約缺報價（過濾後零候選）不是關鍵資料失敗，
    chain 本身成功 → 仍為綠燈，收益率顯示「—」。"""
    view = _view(groups=[("2028-01", [])], baseline_expiry="2028-01")
    card = workspace.card_of(SC, view, observed=NOT_OVER)
    assert card.signal == workspace.SIGNAL_GREEN
    assert card.best_return is None
