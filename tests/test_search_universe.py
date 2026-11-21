"""Search Universe 登錄表（OS-02／#391，母票 #389 §6）。

後續票（共識清單、搜尋）只透過 `resolve_universe()` 拿「這位使用者要搜
哪些股票」——這份測試釘住它的對外形狀與兩條文案紅線：大型股樣本是**暫定**
的靜態清單，絕不自稱 S&P 500。
"""
from api_app.search_universe import (CUSTOM, SAMPLE_LARGE_CAP, resolve_universe,
                                     universe_options)


def test_unset_settings_resolve_to_the_provisional_large_cap_sample():
    universe_id, label, provisional, symbols = resolve_universe(None)
    assert universe_id == SAMPLE_LARGE_CAP == "sample-large-cap"
    assert label == "大型股樣本（暫定，清單來源待 #382）"
    assert provisional is True
    assert 40 <= len(symbols) <= 60
    assert len(set(symbols)) == len(symbols)
    assert {"AAPL", "MSFT", "NVDA"} <= set(symbols)
    assert all(s == s.upper() for s in symbols)


def test_the_sample_never_calls_itself_sp500():
    for option in universe_options():
        assert "S&P" not in option["label"]
        assert "500" not in option["label"]


def test_custom_universe_uses_the_users_own_list_in_order():
    resolved = resolve_universe({"universe_id": "custom",
                                 "custom_symbols": ["TSLA", "AAPL"]})
    assert resolved.id == CUSTOM
    assert resolved.label == "自訂清單"
    assert resolved.provisional is False
    assert resolved.symbols == ("TSLA", "AAPL")


def test_custom_symbols_are_ignored_while_the_sample_is_selected():
    """自訂清單只在選 `custom` 時使用——切回樣本時保留清單但不拿來搜。"""
    resolved = resolve_universe({"universe_id": "sample-large-cap",
                                 "custom_symbols": ["ZZZZ"]})
    assert resolved.id == SAMPLE_LARGE_CAP
    assert resolved.symbols == resolve_universe(None).symbols
    assert "ZZZZ" not in resolved.symbols


def test_options_list_both_universes_with_their_sizes():
    options = {o["id"]: o for o in universe_options()}
    assert set(options) == {"sample-large-cap", "custom"}
    assert options["sample-large-cap"]["provisional"] is True
    assert options["sample-large-cap"]["symbol_count"] == len(
        resolve_universe(None).symbols)
    assert options["custom"]["provisional"] is False
