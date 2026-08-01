"""T5（#19）／需求五: 劇本卡片模型（純函式，零 Streamlit）。

卡片恰五項：標的／目標價／目標年月／目前最高「目標達成並持有至到期收益率」／
一個燈號位置。收益率取自該次分析結果已預算好的 baseline_return，卡片層不做
任何金融計算。
"""
import dataclasses

from option_chaser import workspace
from option_chaser.store import Scenario

TS = "2026-07-21T00:00:00+00:00"

SC = Scenario(schema_version=2, id="XYZ-120-202801", symbol="XYZ",
              direction="bullish", target_price=120.0, target_month="2028-01",
              created_at=TS, notes="", group_id="G-XYZ", status="Active",
              strategies=("bull-call-spread",))


def _view(*, candidates=(), expiry_best=(), status="ok"):
    def cand(r):
        return {"baseline_return": r}
    return {"results": [{"strategy": "bull-call-spread", "status": status,
                         "candidates": [cand(r) for r in candidates],
                         "expiry_best": [cand(r) for r in expiry_best]}]}


def test_card_carries_exactly_the_five_display_fields():
    card = workspace.card_of(SC, _view(expiry_best=(1.2,)))
    assert {f.name for f in dataclasses.fields(card)} == {
        "id", "symbol", "target_price", "target_month", "best_return", "signal"}
    assert (card.symbol, card.target_price, card.target_month) == (
        "XYZ", 120.0, "2028-01")
    assert card.id == SC.id


def test_best_return_is_the_max_over_all_candidates_of_the_result():
    view = _view(candidates=(3.1, 2.0), expiry_best=(0.4, 5.2, 1.0))
    assert workspace.card_of(SC, view).best_return == 5.2


def test_no_snapshot_yet_shows_no_return():
    """附錄 A8.1：尚無任何成功快照的劇本，收益率顯示「—」。"""
    assert workspace.card_of(SC, None).best_return is None


def test_zero_candidate_result_shows_no_return():
    """附錄 A10.2：抓取成功但過濾後零候選，收益率同樣是「—」（不是 0%）。"""
    assert workspace.card_of(SC, _view()).best_return is None


def test_failed_strategy_results_are_not_read():
    """status 非 ok 的策略結果不參與——沒有可信的收益率可取。"""
    view = _view(candidates=(9.9,), status="empty")
    assert workspace.card_of(SC, view).best_return is None


def test_negative_best_return_is_reported_as_is():
    """全部虧損時照實回報負值（卡片上以紅色呈現），不夾成 0 也不變成「—」。"""
    assert workspace.card_of(SC, _view(expiry_best=(-0.31, -0.72))).best_return \
        == -0.31


def test_signal_is_a_placeholder_until_the_light_ticket():
    """T6（#20）接手燈號邏輯；本票只保留卡片上的單一顯示位置。"""
    assert workspace.card_of(SC, None).signal == "unknown"
