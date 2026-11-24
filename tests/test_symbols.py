"""V2-01（#404）：股權類別代號的唯一對照規則。

系統內部（設定、共識快取、劇本、搜尋結果）一律存 **canonical** 寫法
`BRK.B`（S&P／Cboe／一般寫法）；只有組上游 URL 的那一刻才換成各來源的寫法。
期望值是來源的實際行為（2026-11-24 實測：Yahoo `BRK.B` 回 404、`BRK-B`
回 200），不是拿函式自己算。
"""
import pytest

from option_chaser.symbols import canonical_symbol, cboe_symbol, yahoo_symbol


@pytest.mark.parametrize("raw, expected", [
    ("BRK.B", "BRK.B"),
    ("BRK-B", "BRK.B"),
    ("brk-b", "BRK.B"),
    (" bf.b ", "BF.B"),
    ("BRK/B", "BRK.B"),
    ("AAPL", "AAPL"),
    ("GOOGL", "GOOGL"),
    ("GOOG", "GOOG"),
])
def test_canonical_form_uses_the_dot(raw, expected):
    assert canonical_symbol(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("BRK.B", "BRK-B"), ("BRK-B", "BRK-B"), ("BF.B", "BF-B"), ("AAPL", "AAPL"),
])
def test_yahoo_uses_the_hyphen(raw, expected):
    assert yahoo_symbol(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("BRK.B", "BRK.B"), ("BRK-B", "BRK.B"), ("BF.B", "BF.B"), ("AAPL", "AAPL"),
])
def test_cboe_uses_the_dot(raw, expected):
    assert cboe_symbol(raw) == expected


def test_share_classes_stay_separate_stocks():
    assert canonical_symbol("GOOGL") != canonical_symbol("GOOG")
    assert canonical_symbol("BRK.B") != canonical_symbol("BRK.A")
