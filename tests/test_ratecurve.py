# tests/test_ratecurve.py
"""T12(A) 純函式層：par→連續複利轉換、相鄰節點線性插值、CSV/XML 曲線解析。

全部離線；夾具曲線固定，可重跑覆核（issue #26 驗收）。
"""
import math
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures"

from option_chaser.models import ParamError
from option_chaser.ratecurve import (CurveParseError, RateCurve,
                                     curve_from_dict, curve_from_par_yields,
                                     curve_to_dict, par_to_continuous,
                                     parse_treasury_csv, parse_treasury_xml,
                                     rate_for_tenor)

ONE_MONTH = 1.0 / 12.0

# 研究 §8 夾具曲線（par，小數）：1M 4.30%、3M 4.25%、6M 4.15%、1Y 4.00%、
# 2Y 4.20%、3Y 4.30%。
FIXTURE_PAR = ((1 / 12, 0.0430), (3 / 12, 0.0425), (6 / 12, 0.0415),
               (1.0, 0.0400), (2.0, 0.0420), (3.0, 0.0430))
CURVE = curve_from_par_yields("2026-07-31", FIXTURE_PAR)


# ---------- 轉換公式 ----------

def test_par_to_continuous_research_example():
    # 研究 §5 數值例：y = 4.20% → r_cc = 4.1565%
    assert par_to_continuous(0.0420) == pytest.approx(0.041565, abs=5e-7)


def test_par_to_continuous_is_2_ln_1_plus_half():
    for y in (0.0, 0.01, 0.0430, 0.05):
        assert par_to_continuous(y) == pytest.approx(2.0 * math.log(1.0 + y / 2.0))


def test_curve_from_par_yields_converts_every_node():
    for (t, y), (t2, r) in zip(FIXTURE_PAR, CURVE.nodes):
        assert t2 == t
        assert r == pytest.approx(par_to_continuous(y))


# ---------- 插值 ----------

def test_rate_at_exact_node():
    assert rate_for_tenor(CURVE, 1.0) == pytest.approx(par_to_continuous(0.0400))
    assert rate_for_tenor(CURVE, 3.0) == pytest.approx(par_to_continuous(0.0430))


def test_rate_between_nodes_is_linear_on_cc_zero():
    # 1Y–2Y 中點：連續複利 zero rate 線性插值（研究 §6：linear-on-zero）
    lo, hi = par_to_continuous(0.0400), par_to_continuous(0.0420)
    assert rate_for_tenor(CURVE, 1.5) == pytest.approx((lo + hi) / 2.0)
    # 非中點：1Y + 0.25
    assert rate_for_tenor(CURVE, 1.25) == pytest.approx(lo + 0.25 * (hi - lo))


def test_rate_below_one_month_clamps_to_first_node():
    first = par_to_continuous(0.0430)
    assert rate_for_tenor(CURVE, 0.0) == pytest.approx(first)
    assert rate_for_tenor(CURVE, ONE_MONTH / 2) == pytest.approx(first)


def test_rate_above_last_node_clamps_no_extrapolation():
    last = par_to_continuous(0.0430)
    assert rate_for_tenor(CURVE, 10.0) == pytest.approx(last)


def test_curve_requires_sorted_unique_nonempty_nodes():
    with pytest.raises(ParamError):
        RateCurve(curve_date="2026-07-31", nodes=())
    with pytest.raises(ParamError):
        RateCurve(curve_date="2026-07-31",
                  nodes=((2.0, 0.04), (1.0, 0.04)))
    with pytest.raises(ParamError):
        RateCurve(curve_date="2026-07-31",
                  nodes=((1.0, 0.04), (1.0, 0.05)))


# ---------- CSV 解析 ----------

CSV_TEXT = '''Date,"1 Mo","2 Mo","3 Mo","4 Mo","6 Mo","1 Yr","2 Yr","3 Yr","5 Yr","7 Yr","10 Yr","20 Yr","30 Yr"
07/30/2026,4.31,4.29,4.26,4.24,4.16,4.01,4.19,4.29,4.40,4.48,4.55,4.80,4.90
07/31/2026,4.30,4.28,4.25,4.23,4.15,4.00,4.20,4.30,4.41,4.49,4.56,4.81,4.91
'''


def test_parse_csv_picks_latest_row_and_converts():
    curve = parse_treasury_csv(CSV_TEXT)
    assert curve.curve_date == "2026-07-31"
    nodes = dict(curve.nodes)
    assert nodes[1 / 12] == pytest.approx(par_to_continuous(0.0430))
    assert nodes[2.0] == pytest.approx(par_to_continuous(0.0420))
    assert nodes[30.0] == pytest.approx(par_to_continuous(0.0491))
    assert [t for t, _ in curve.nodes] == sorted(t for t, _ in curve.nodes)


def test_parse_csv_rows_out_of_order_still_latest():
    lines = CSV_TEXT.strip().splitlines()
    swapped = "\n".join([lines[0], lines[2], lines[1]]) + "\n"
    assert parse_treasury_csv(swapped).curve_date == "2026-07-31"


def test_parse_csv_skips_empty_cells():
    text = ('Date,"1 Mo","2 Mo","1 Yr"\n'
            "07/31/2026,4.30,N/A,4.00\n")
    curve = parse_treasury_csv(text)
    assert [t for t, _ in curve.nodes] == [1 / 12, 1.0]


def test_parse_csv_rejects_garbage():
    with pytest.raises(CurveParseError):
        parse_treasury_csv("<html>maintenance</html>")
    with pytest.raises(CurveParseError):
        parse_treasury_csv('Date,"1 Mo"\n')            # 無資料列
    with pytest.raises(CurveParseError):
        parse_treasury_csv('Date,"1 Mo"\n07/31/2026,\n')  # 無可用節點


def test_parse_csv_against_a_real_captured_response():
    """#74 硬化的回歸樣本：`tests/fixtures/treasury_csv_sample.txt` 是
    2026-08-05 在 Vercel 上對 Treasury CSV 端點實測的真實回應（見
    `docs/research/interest-rate-source-selection.md` 追記章節），不是
    手刻的最小夾具——端點真的改版時，這條測試會先紅，而不是等到
    production 才發現解析器跟不上真實欄位。"""
    text = (_FIXTURES / "treasury_csv_sample.txt").read_text(encoding="utf-8")
    curve = parse_treasury_csv(text)
    assert curve.curve_date == "2026-08-04"
    nodes = dict(curve.nodes)
    assert nodes[1 / 12] == pytest.approx(par_to_continuous(0.0378))
    assert nodes[1.0] == pytest.approx(par_to_continuous(0.0404))
    assert nodes[2.0] == pytest.approx(par_to_continuous(0.0420))
    assert nodes[30.0] == pytest.approx(par_to_continuous(0.0518))
    assert len(curve.nodes) == 14   # 樣本表頭的全部 14 個年期欄位


# ---------- XML 解析（備援端點） ----------

XML_TEXT = '''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry><content><m:properties>
    <d:NEW_DATE>2026-07-30T00:00:00</d:NEW_DATE>
    <d:BC_1MONTH>4.31</d:BC_1MONTH>
    <d:BC_1YEAR>4.01</d:BC_1YEAR>
    <d:BC_2YEAR>4.19</d:BC_2YEAR>
    <d:BC_30YEAR>4.90</d:BC_30YEAR>
    <d:BC_30YEARDISPLAY>4.90</d:BC_30YEARDISPLAY>
  </m:properties></content></entry>
  <entry><content><m:properties>
    <d:NEW_DATE>2026-07-31T00:00:00</d:NEW_DATE>
    <d:BC_1MONTH>4.30</d:BC_1MONTH>
    <d:BC_1YEAR>4.00</d:BC_1YEAR>
    <d:BC_2YEAR>4.20</d:BC_2YEAR>
    <d:BC_30YEAR>4.91</d:BC_30YEAR>
    <d:BC_30YEARDISPLAY>4.91</d:BC_30YEARDISPLAY>
  </m:properties></content></entry>
</feed>
'''


def test_parse_xml_latest_entry_and_converts():
    curve = parse_treasury_xml(XML_TEXT)
    assert curve.curve_date == "2026-07-31"
    nodes = dict(curve.nodes)
    assert nodes[1 / 12] == pytest.approx(par_to_continuous(0.0430))
    assert nodes[2.0] == pytest.approx(par_to_continuous(0.0420))
    # BC_30YEARDISPLAY 不是 tenor，不得混入
    assert len(curve.nodes) == 4


def test_parse_xml_rejects_garbage():
    with pytest.raises(CurveParseError):
        parse_treasury_xml("not xml at all")
    with pytest.raises(CurveParseError):
        parse_treasury_xml("<feed></feed>")


def test_parse_xml_against_a_real_captured_response():
    """#74 硬化的回歸樣本：`tests/fixtures/treasury_xml_sample.txt` 是
    2026-08-05 在 Vercel 上對 Treasury XML 端點實測的真實回應（兩筆
    完整 entry，id=140／141），理由同上一條 CSV 版本——鎖住真實欄位
    命名（`d:BC_1MONTH`／`d:NEW_DATE` 等）與命名空間，不是手刻夾具。"""
    text = (_FIXTURES / "treasury_xml_sample.txt").read_text(encoding="utf-8")
    curve = parse_treasury_xml(text)
    assert curve.curve_date == "2026-01-05"   # 兩筆 entry 裡較新的那筆
    nodes = dict(curve.nodes)
    assert nodes[1 / 12] == pytest.approx(par_to_continuous(0.0371))
    assert nodes[1.0] == pytest.approx(par_to_continuous(0.0347))
    assert nodes[2.0] == pytest.approx(par_to_continuous(0.0346))
    assert nodes[30.0] == pytest.approx(par_to_continuous(0.0485))
    assert len(curve.nodes) == 14   # 不含 BC_30YEARDISPLAY（非 tenor）


# ---------- 快取序列化 round-trip ----------

def test_curve_dict_round_trip():
    assert curve_from_dict(curve_to_dict(CURVE)) == CURVE
