"""T11（#25）：Spread 專屬歷史時間序列查詢（`workspace.spread_history`，
純唯讀聚合，不碰快照寫入格式）。

依序餵三份合成快照給同一個劇本，讓被追蹤的 Spread（100/110，寬度 10）
依序經歷「排名第 2」→「當次缺席（105 履約價報價正常，110 報價異常被濾掉，
此候選當次無法配對）」→「重新入榜且升到第 1」，驗證 AC 要求的「名次升降、
掉榜、回榜情境下，同鍵聚合為同一連續序列」與「缺席回傳斷點，不插值」。
"""
import json
from datetime import date
from pathlib import Path

from option_chaser import workspace

EXP = "2026-08-21"
TRACKED_KEY = f"bull-call-spread|100|110|{EXP}"


def _leg(sym, strike, bid, ask):
    return {"contract_symbol": sym, "option_type": "call", "strike": strike,
            "expiry": EXP, "bid": bid, "ask": ask, "last": None,
            "volume": 50, "open_interest": 100, "implied_volatility": 0.3}


def _write(tmp_path, name, fetched_at, contracts):
    snap = {"schema_version": 2, "symbol": "XYZ", "fetched_at": fetched_at,
           "spot": 100.0, "source": "yfinance", "contracts": contracts}
    f = Path(tmp_path) / f"{name}.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    return str(f)


def _snapshots(tmp_path):
    # A：追蹤鍵排名第 2（另有 105/110 排第 1、100/105 排第 3）。
    a = _write(tmp_path, "a", "2026-07-01T21:30:00-04:00", [
        _leg("A100", 100, 4.95, 5.05), _leg("A105", 105, 3.0, 3.1),
        _leg("A110", 110, 2.5, 2.6)])
    # B：110 履約價報價異常（bid=0）被濾掉——追蹤鍵當次無法配對，缺席。
    b = _write(tmp_path, "b", "2026-07-08T21:30:00-04:00", [
        _leg("B100", 100, 4.95, 5.05), _leg("B105", 105, 3.0, 3.1),
        _leg("B110", 110, 0.0, 0.05)])
    # C：追蹤鍵重新入榜，且升到第 1（100/105 這次比較貴，跌到第 2）。
    c = _write(tmp_path, "c", "2026-07-15T21:30:00-04:00", [
        _leg("C100", 100, 4.95, 5.05), _leg("C105", 105, 0.95, 1.05),
        _leg("C110", 110, 4.5, 4.6)])
    return a, b, c


def _create(ws_root):
    return workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=130.0,
        target_month="2026-08", notes="", strategies=("bull-call-spread",),
        ts="2026-07-01T00:00:00+00:00", observed=date(2026, 7, 1))


def test_history_is_a_single_continuous_series_across_rank_change_gap_and_reentry(tmp_path):
    a, b, c = _snapshots(tmp_path)
    sc = _create(tmp_path)
    for snap in (a, b, c):
        workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=snap)

    hist = workspace.spread_history(tmp_path, sc.id, TRACKED_KEY)
    assert len(hist) == 3   # 同一鍵，三次快照全部入列，缺席那次也算一筆

    # 依 fetched_at 時間序（檔名字典序＝時間序，既有 store.py 保證）。
    assert [e["analyzed_at"] for e in hist] == [
        "2026-07-01T21:30:00-04:00", "2026-07-08T21:30:00-04:00",
        "2026-07-15T21:30:00-04:00"]

    rank_1, rank_2, rank_3 = hist
    assert rank_1["rank_in_expiry"] == 2      # A：排名第 2
    assert rank_2["rank_in_expiry"] is None   # B：缺席＝斷點
    assert rank_2["cost"] is None
    assert rank_2["baseline_return"] is None
    assert rank_3["rank_in_expiry"] == 1      # C：重新入榜且升到第 1


def test_gap_entry_still_carries_the_update_time_and_spot(tmp_path):
    """斷點只缺該候選自己的三欄；那次更新本身成功，時間與標的價仍在
    （附錄：更新時間／標的價來自父層快照，不是候選自己的欄位）。"""
    a, b, c = _snapshots(tmp_path)
    sc = _create(tmp_path)
    workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=b)
    hist = workspace.spread_history(tmp_path, sc.id, TRACKED_KEY)
    assert len(hist) == 1
    assert hist[0]["analyzed_at"] == "2026-07-08T21:30:00-04:00"
    assert hist[0]["spot"] == 100.0
    assert hist[0]["cost"] is None


def test_unknown_scenario_returns_empty_list_not_an_error(tmp_path):
    assert workspace.spread_history(tmp_path, "NOPE", TRACKED_KEY) == []


def test_never_analyzed_scenario_has_empty_history(tmp_path):
    sc = _create(tmp_path)
    assert workspace.spread_history(tmp_path, sc.id, TRACKED_KEY) == []


def test_read_only_does_not_touch_snapshot_files(tmp_path):
    a, b, c = _snapshots(tmp_path)
    sc = _create(tmp_path)
    workspace.analyze_scenario(tmp_path, sc.id, snapshot_path=a)
    result_dir = Path(tmp_path) / "results" / sc.id
    before = {p: p.read_bytes() for p in result_dir.glob("*.json")}

    workspace.spread_history(tmp_path, sc.id, TRACKED_KEY)
    workspace.spread_history(tmp_path, sc.id, "some-other-key-not-present")

    after = {p: p.read_bytes() for p in result_dir.glob("*.json")}
    assert before == after and before   # 有檔案可比，且內容位元組級不變
