# tests/test_status.py
"""v6 spec §6.1/§6.2: 狀態推導八分類（展示層純函數，逐列鎖定）。"""
from datetime import date

from webapp import status


def _view(all_quotes_filtered=False, has_selection=True, fetched_at="2026-07-22T10:00:00+00:00"):
    return {
        "default_selection": ["2026-08-01", "long-call|100|2026-08-01"] if has_selection else None,
        "data_quality": {"all_quotes_filtered": all_quotes_filtered, "fetched_at": fetched_at},
        "snapshot_ref": {"fetched_at": fetched_at},
    }


def test_not_yet_analyzed():
    assert status.derive_result_status(None) == "尚未分析"


def test_has_candidates():
    assert status.derive_result_status(_view(has_selection=True)) == "有可用候選"


def test_no_qualified_candidates():
    v = _view(has_selection=False, all_quotes_filtered=False)
    assert status.derive_result_status(v) == "無合格候選"


def test_insufficient_quote_data():
    v = _view(has_selection=False, all_quotes_filtered=True)
    assert status.derive_result_status(v) == "報價資料不足"


def test_insufficient_takes_priority_even_with_selection():
    """all_quotes_filtered=True 理論上不會與 has_selection=True 並存（服務端保證），
    但推導函數仍應以 all_quotes_filtered 為優先判準（防禦性一致）。"""
    v = _view(has_selection=True, all_quotes_filtered=True)
    assert status.derive_result_status(v) == "報價資料不足"


def test_quality_tone_normal():
    v = _view(fetched_at="2026-07-22T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "正常"


def test_quality_tone_insufficient_quote_wins():
    v = _view(all_quotes_filtered=True, fetched_at="2026-07-22T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "報價不足"


def test_quality_tone_historical():
    v = _view(fetched_at="2026-07-15T10:00:00-04:00")
    assert status.quality_tone(v, observed=date(2026, 7, 22)) == "歷史資料"


def test_quality_tone_none_view_is_normal_placeholder():
    assert status.quality_tone(None, observed=date(2026, 7, 22)) == "正常"


def test_messages_no_synthetic_fallback_path():
    """誠實聲明：程式內無 synthetic/last-trade fallback 資料路徑。"""
    import inspect
    src = inspect.getsource(status)
    assert "synthetic" not in src.lower()
    assert "last_trade" not in src.lower() and "last-trade" not in src.lower()


def test_is_legacy_schema_v1_vs_v2():
    assert status.is_legacy_schema({"schema_version": 1}) is True
    assert status.is_legacy_schema({"schema_version": 2}) is False
    assert status.is_legacy_schema({}) is True   # 缺欄視同 v1（get 預設 1）


def test_legacy_result_message_defined():
    assert "重新分析" in status.LEGACY_RESULT_MESSAGE
