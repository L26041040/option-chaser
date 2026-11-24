"""V2-01（#404）：S&P 500 成分股清單與更新工具。

更新工具的解析測試用的是 2026-11-24 從 Wikipedia API 取回的 wikitext
**原文片段**（含實際出現過的幾種寫法：`{{NyseSymbol|…}}`、`{{NasdaqSymbol|…}}`、
`{{BZX link|…}}`、單一 `|` 開頭的列、同一行接下一格、`[[連結|顯示名]]`、
`(Class A)` 後綴、BRK.B 那行的 HTML 註解）。期望值是人工讀原文得出的字面值。
"""
from __future__ import annotations

import re

import pytest

from api_app import sp500_constituents as committed
from scripts import update_sp500_constituents as tool

WIKITEXT = """{{Short description|List of companies in the S&P 500}}
== S&P 500 component stocks ==
{| class="wikitable sortable mw-collapsible sticky-header" id="constituents"
|-
![[Ticker symbol|Symbol]]
! Security !! [[Global Industry Classification Standard|GICS]] Sector !! GICS Sub-Industry !! Headquarters Location !! Date added !! [[Central Index Key|CIK]] !! Founded
|-
|| {{NyseSymbol|MMM}}
|| [[3M]]
|| Industrials
|| Industrial Conglomerates
|| [[Saint Paul, Minnesota]]
|| 1957-03-04
|| 0000066740
|| 1902
|-
|| {{NasdaqSymbol|AMD}}
|| [[AMD|Advanced Micro Devices]]
|| Information Technology
|| Semiconductors
|| [[Santa Clara, California]]
|| 2017-03-20
|| 0000002488
|| 1969
|-
|| {{NyseSymbol|BRK.B}} <!-- DO NOT CHANGE THIS TICKER TO BRK-B. IT IS NOT CORRECT AND WILL BE REVERTED. YOU'VE BEEN WARNED! -->
|| [[Berkshire Hathaway]]
|| Financials
|| Multi-Sector Holdings
|| [[Omaha, Nebraska]]
|| 2010-02-16
|| 0001067983
|| 1839
|-
|| {{NasdaqSymbol|GOOGL}}
|| [[Alphabet Inc.]] (Class A)
|| Communication Services
|| Interactive Media & Services
|| [[Mountain View, California]]
|| 2014-04-03
|| 0001652044
|| 1998
|-
|| {{NasdaqSymbol|GOOG}}
|| [[Alphabet Inc.]] (Class C)
|| Communication Services
|| Interactive Media & Services
|| [[Mountain View, California]]
|| 2006-04-03
|| 0001652044
|| 1998
|-
|| {{BZX link|CBOE}}
|| [[Cboe Global Markets]]
|| Financials
|| Financial Exchanges & Data
|| [[Chicago]], Illinois
|| 2017-03-01
|| 0001374310
|| 1973
|-
||  {{NyseSymbol|EME}}
||  [[Emcor]]|| Industrials
|| Construction & Engineering
|| [[Norwalk, Connecticut]]
|| 2025-09-22
|| 0000105634
|| 1994
|-
| {{NyseSymbol|RDDT}}
|| [[Reddit]]
|| Communication Services
|| Interactive Media & Services
|| [[San Francisco]], California
|| 2026-03-23
|| 0001713445
|| 2005
|}

== Selected changes to the list of S&P 500 components ==
{| class="wikitable sortable" id="changes"
|-
|| {{NyseSymbol|ZZZZ}}
|| [[Not A Constituent]]
|}
"""


def test_parser_reads_every_row_of_the_constituents_table_only():
    assert tool.parse_constituents(WIKITEXT) == [
        ("MMM", "3M"),
        ("AMD", "Advanced Micro Devices"),
        ("BRK.B", "Berkshire Hathaway"),
        ("GOOGL", "Alphabet Inc. (Class A)"),
        ("GOOG", "Alphabet Inc. (Class C)"),
        ("CBOE", "Cboe Global Markets"),
        ("EME", "Emcor"),
        ("RDDT", "Reddit"),
    ]


def test_parser_refuses_a_page_without_the_constituents_table():
    with pytest.raises(tool.ParseError):
        tool.parse_constituents("{| class=\"wikitable\"\n|-\n|| x\n|}")


def test_validate_rejects_lists_that_cannot_be_the_index():
    rows = [(f"A{chr(65 + i // 26)}{chr(65 + i % 26)}", "x") for i in range(503)]
    tool.validate(rows)                                   # 503 檔、都合法：OK
    with pytest.raises(tool.ParseError, match="檔數"):
        tool.validate(rows[:100])
    with pytest.raises(tool.ParseError, match="重複"):
        tool.validate(rows[:502] + [rows[0]])
    with pytest.raises(tool.ParseError, match="代號"):
        tool.validate(rows[:502] + [("brk b", "x")])


def test_diff_report_lists_added_and_removed_symbols():
    old = [("AAA", "Alpha"), ("BBB", "Beta"), ("CCC", "Gamma")]
    new = [("AAA", "Alpha"), ("CCC", "Gamma"), ("DDD", "Delta"), ("EEE", "Epsilon")]
    report = tool.diff_report(old, new, old_version="2026-11-01",
                              new_version="2026-11-24")
    assert report == (
        "S&P 500 成分股：2026-11-01 → 2026-11-24\n"
        "檔數：3 → 4\n"
        "新增 2 檔：\n"
        "  + DDD  Delta\n"
        "  + EEE  Epsilon\n"
        "移除 1 檔：\n"
        "  - BBB  Beta\n")


def test_diff_report_says_so_when_nothing_changed():
    rows = [("AAA", "Alpha")]
    report = tool.diff_report(rows, rows, old_version="v1", new_version="v2")
    assert "新增 0 檔" in report and "移除 0 檔" in report


def test_rendered_module_round_trips():
    rows = [("BRK.B", "Berkshire Hathaway"), ("GOOGL", "Alphabet Inc. (Class A)"),
            ("ODD", 'Quote "and" backslash \\ name')]
    source = tool.render_module(rows, effective_date="2026-11-24", revision=123,
                                retrieved_at="2026-11-24T08:00:00Z")
    ns: dict = {}
    exec(compile(source, "<rendered>", "exec"), ns)
    assert ns["CONSTITUENTS"] == tuple(rows)
    assert ns["VERSION"] == "2026-11-24"
    assert ns["SOURCE_REVISION"] == 123
    assert "oldid=123" in ns["SOURCE_URL"]
    assert ns["LICENSE"] == "CC BY-SA 4.0"


# ---------- repo 內的清單本身 ----------

def test_committed_list_has_a_version_date_and_source():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", committed.VERSION)
    assert committed.LICENSE == "CC BY-SA 4.0"
    assert f"oldid={committed.SOURCE_REVISION}" in committed.SOURCE_URL


def test_committed_list_looks_like_the_sp500_with_both_share_classes():
    symbols = [s for s, _ in committed.CONSTITUENTS]
    assert 495 <= len(symbols) <= 510
    assert len(set(symbols)) == len(symbols)
    # 兩種股權類別都是各自的股票；股權類別一律 canonical 點寫法。
    assert {"GOOGL", "GOOG", "BRK.B", "BF.B", "AAPL", "MSFT"} <= set(symbols)
    assert not any("-" in s for s in symbols)
    tool.validate(committed.CONSTITUENTS)
