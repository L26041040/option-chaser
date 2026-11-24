"""掃描股票範圍（Search Universe）登錄表（OS-02／#391 → V2-01／#404）。

後續票（共識清單、搜尋）只透過 `resolve_universe()` 拿「這位使用者要掃描
哪些股票」——這份測試釘住它的對外形狀：預設是 repo 內有版本日期的 S&P 500
成分股；舊的「大型股樣本」設定（`sample-large-cap`）一律遷移到 S&P 500；
自訂清單照常可用。
"""
from api_app import sp500_constituents
from api_app.search_universe import (CUSTOM, LEGACY_SAMPLE_LARGE_CAP,
                                     REFRESH_PRIORITY, SP500, resolve_universe,
                                     universe_options)

SP500_SYMBOLS = tuple(s for s, _ in sp500_constituents.CONSTITUENTS)


def test_unset_settings_resolve_to_the_sp500_constituents():
    resolved = resolve_universe(None)
    assert resolved.id == SP500 == "sp500"
    assert resolved.label == "S&P 500 成分股"
    assert resolved.provisional is False
    assert resolved.symbols == SP500_SYMBOLS
    assert 495 <= len(resolved.symbols) <= 510
    assert resolved.version_date == sp500_constituents.VERSION


def test_sp500_keeps_both_share_classes_as_separate_stocks():
    symbols = resolve_universe(None).symbols
    assert {"GOOGL", "GOOG", "BRK.B", "BF.B"} <= set(symbols)


def test_legacy_sample_setting_migrates_to_sp500():
    """舊設定 `sample-large-cap`（大型股樣本，已退役）不會壞：讀到就當 S&P 500。"""
    assert LEGACY_SAMPLE_LARGE_CAP == "sample-large-cap"
    resolved = resolve_universe({"universe_id": "sample-large-cap",
                                 "custom_symbols": ["ZZZZ"]})
    assert resolved.id == SP500
    assert resolved.symbols == SP500_SYMBOLS


def test_unknown_stored_universe_falls_back_to_the_default():
    assert resolve_universe({"universe_id": "gone-forever"}).id == SP500


def test_custom_universe_uses_the_users_own_list_in_order():
    resolved = resolve_universe({"universe_id": "custom",
                                 "custom_symbols": ["TSLA", "AAPL"]})
    assert resolved.id == CUSTOM
    assert resolved.label == "自訂清單"
    assert resolved.provisional is False
    assert resolved.symbols == ("TSLA", "AAPL")


def test_custom_list_saved_with_hyphens_reads_back_canonical():
    """V2-01 之前存下的 `BRK-B` 與新的 `BRK.B` 是同一檔，共識快取只有一個鍵。"""
    resolved = resolve_universe({"universe_id": "custom",
                                 "custom_symbols": ["BRK-B", "BRK.B", "BF-B"]})
    assert resolved.symbols == ("BRK.B", "BF.B")


def test_custom_symbols_are_ignored_while_sp500_is_selected():
    """自訂清單只在選 `custom` 時使用——切回 S&P 500 時保留清單但不拿來搜。"""
    resolved = resolve_universe({"universe_id": "sp500", "custom_symbols": ["ZZZZ"]})
    assert resolved.id == SP500
    assert "ZZZZ" not in resolved.symbols


def test_options_list_sp500_with_count_and_version_date_and_custom():
    options = {o["id"]: o for o in universe_options()}
    assert list(options) == ["sp500", "custom"]
    sp = options["sp500"]
    assert sp["label"] == "S&P 500 成分股"
    assert sp["provisional"] is False
    assert sp["symbol_count"] == len(SP500_SYMBOLS)
    assert sp["version_date"] == sp500_constituents.VERSION
    assert options["custom"] == {"id": "custom", "label": "自訂清單",
                                 "provisional": False, "symbol_count": None,
                                 "version_date": None}


def test_the_retired_sample_is_no_longer_offered():
    assert all(o["id"] != "sample-large-cap" for o in universe_options())
    assert all("暫定" not in o["label"] for o in universe_options())


def test_refresh_priority_is_fifty_sp500_members():
    """每日更新有上限（200，#403 再擴）時優先更新的大型股；必須全是成分股。"""
    assert len(REFRESH_PRIORITY) == 50
    assert len(set(REFRESH_PRIORITY)) == 50
    assert set(REFRESH_PRIORITY) <= set(SP500_SYMBOLS)
