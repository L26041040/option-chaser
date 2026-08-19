"""#123（spec #117 §2）q 純函式：逐 vendor 回應解析、TTM 金額 / spot、
離群值抑制、序列化。

無 I/O、無 wall-clock——所有輸入為固定 fixture，比照
`tests/test_ratecurve.py` 對 `parse_treasury_csv`／`parse_treasury_xml`
的既有慣例（純文字→資料結構直接測，不經過 HTTP 抓取層）。抓取鏈與
本地檔案快取的 I/O 層測試見 `tests/test_data_dividends.py`。
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from option_chaser.dividends import (DividendHistory, DividendParseError,
                                     DividendRecord, compute_q, compute_q_asof,
                                     history_from_dict, history_to_dict,
                                     parse_fmp_dividends, parse_nasdaq_dividends,
                                     parse_yahoo_dividends)
from option_chaser.models import ParamError

TODAY = date(2026, 8, 10)


def _history(records: tuple[tuple[str, float], ...], source="yahoo",
            stale=False) -> DividendHistory:
    return DividendHistory(
        symbol="TLT", as_of="2026-08-10", source=source, stale=stale,
        distributions=tuple(DividendRecord(ex_date=d, amount=a) for d, a in records))


# ---------- parse_yahoo_dividends：#120 §12.4 實測確認的形狀 ----------

def test_parse_yahoo_dividends_extracts_amount_and_ex_date():
    body = json.dumps({"chart": {"result": [{"events": {"dividends": {
        "1785816600": {"amount": 0.330, "date": 1785816600},
        "1783224600": {"amount": 0.318, "date": 1783224600},
    }}}]}})
    history = parse_yahoo_dividends("TLT", body, TODAY)
    assert history.symbol == "TLT" and history.source == "yahoo"
    assert history.as_of == TODAY.isoformat()
    assert len(history.distributions) == 2
    assert {r.amount for r in history.distributions} == {0.330, 0.318}


def test_parse_yahoo_dividends_with_no_dividends_key_is_empty_not_an_error():
    """研究 §8 第 2 層：確定無配息的標的（如 YETI）回應形狀。"""
    body = json.dumps({"chart": {"result": [{"events": {}}]}})
    history = parse_yahoo_dividends("YETI", body, TODAY)
    assert history.distributions == ()


def test_parse_yahoo_dividends_ignores_capital_gains():
    """研究 §8：只計經常性現金分配，`events.capitalGains` 不讀取。"""
    body = json.dumps({"chart": {"result": [{"events": {
        "dividends": {"1785816600": {"amount": 0.33, "date": 1785816600}},
        "capitalGains": {"1785816600": {"amount": 5.0, "date": 1785816600}},
    }}]}})
    history = parse_yahoo_dividends("TLT", body, TODAY)
    assert len(history.distributions) == 1
    assert history.distributions[0].amount == 0.33


def test_parse_yahoo_dividends_rejects_garbage():
    with pytest.raises(DividendParseError):
        parse_yahoo_dividends("TLT", "<html>maintenance</html>", TODAY)
    with pytest.raises(DividendParseError):
        parse_yahoo_dividends("TLT", json.dumps({"chart": {"result": []}}), TODAY)


# ---------- parse_fmp_dividends ----------

def test_parse_fmp_dividends_extracts_date_and_dividend_fields():
    body = json.dumps([{"date": "2026-08-03", "dividend": 0.330, "adjDividend": 0.330},
                       {"date": "2026-07-01", "dividend": 0.318, "adjDividend": 0.318}])
    history = parse_fmp_dividends("TLT", body, TODAY)
    assert history.source == "fmp"
    assert len(history.distributions) == 2
    assert history.distributions[0] == DividendRecord("2026-08-03", 0.330)


def test_parse_fmp_dividends_skips_malformed_rows_without_failing_the_batch():
    body = json.dumps([{"date": "2026-08-03", "dividend": 0.330},
                       {"date": "2026-07-01"},          # 缺 dividend 欄
                       {"dividend": 0.30}])              # 缺 date 欄
    history = parse_fmp_dividends("TLT", body, TODAY)
    assert len(history.distributions) == 1


def test_parse_fmp_dividends_rejects_a_non_array_shape():
    with pytest.raises(DividendParseError):
        parse_fmp_dividends("TLT", json.dumps({"error": "not an array"}), TODAY)


# ---------- parse_nasdaq_dividends ----------

def test_parse_nasdaq_dividends_extracts_and_normalizes_amount_and_date():
    body = json.dumps({"data": {"dividends": {"rows": [
        {"exOrEffDate": "08/03/2026", "amount": "$0.330000", "type": "CASH"},
        {"exOrEffDate": "07/01/2026", "amount": "$0.318000", "type": "CASH"},
    ]}}})
    history = parse_nasdaq_dividends("TLT", body, TODAY)
    assert history.source == "nasdaq"
    assert history.distributions[0] == DividendRecord("2026-08-03", 0.330)


def test_parse_nasdaq_dividends_skips_rows_missing_date_or_amount():
    body = json.dumps({"data": {"dividends": {"rows": [
        {"exOrEffDate": "08/03/2026", "amount": "$0.330000"},
        {"exOrEffDate": "07/01/2026"},        # 缺 amount
        {"amount": "$0.30"},                  # 缺 exOrEffDate
    ]}}})
    history = parse_nasdaq_dividends("TLT", body, TODAY)
    assert len(history.distributions) == 1


def test_parse_nasdaq_dividends_rejects_garbage():
    with pytest.raises(DividendParseError):
        parse_nasdaq_dividends("TLT", "<html>err</html>", TODAY)


# ---------- compute_q：TTM 加總 / spot ----------

def test_no_distributions_yields_zero_not_none():
    """研究 §8 第 2 層：確定無配息 → q=0，是正確答案，不是降級。"""
    assert compute_q(_history(()), spot=52.0, today=TODAY) == 0.0


def test_ttm_sums_only_entries_within_the_trailing_365_days():
    records = (
        ("2026-08-03", 0.330), ("2026-07-01", 0.318),
        # 明確在窗外（> 365 天前）：不計入
        ("2024-01-01", 5.0),
        # 剛好 365 天前（exclusive 邊界，cutoff = today - 365 天）：不計入
        ("2025-08-10", 9.0),
    )
    q = compute_q(_history(records), spot=82.245, today=TODAY)
    assert q == pytest.approx((0.330 + 0.318) / 82.245)


def test_boundary_at_exactly_365_days_ago_is_excluded():
    cutoff = TODAY.toordinal() - 365
    from datetime import date as _d
    boundary_date = _d.fromordinal(cutoff).isoformat()
    q = compute_q(_history(((boundary_date, 10.0),)), spot=100.0, today=TODAY)
    assert q == 0.0


def test_real_tlt_sample_from_120_probe_sums_correctly():
    """#120 production 實測（run 31408756757）log 裡實際印出的 6 筆最新
    樣本（`sample_recent_entries`，非全部 12 筆——探測腳本只印最新 6 筆，
    其餘 6 筆真實金額本文未記錄，不得杜撰）。這 6 筆本身的加總與 spot
    做除法要對得起來，不斷言完整 12 筆的加總（那需要真實資料，不在
    這份 log 摘要裡）。"""
    six_real_entries = (("2026-08-03", 0.330), ("2026-07-01", 0.318),
                        ("2026-06-01", 0.336), ("2026-05-01", 0.315),
                        ("2026-04-01", 0.345), ("2026-03-02", 0.301))
    q = compute_q(_history(six_real_entries), spot=82.245, today=TODAY)
    assert q == pytest.approx(sum(a for _, a in six_real_entries) / 82.245)


def test_non_positive_spot_is_rejected():
    with pytest.raises(ParamError):
        compute_q(_history((("2026-08-03", 0.33),)), spot=0.0, today=TODAY)


# ---------- 異常單期分配抑制（研究 §8） ----------

def test_one_off_special_distribution_is_dampened_to_the_median():
    """研究 §8 實測示例的量級：正常月配息附近加一筆遠大於中位數的特別
    分配，不該讓它主導 q——單期 > 中位數 3 倍時以中位數取代。"""
    normal = [("2026-0%d-01" % m, 0.30 + 0.01 * m) for m in range(1, 9)]
    special = ("2026-08-03", 5.00)   # 遠大於其餘 ~0.3 量級
    history = _history(tuple(normal) + (special,))
    q = compute_q(history, spot=82.0, today=TODAY)
    undamped = compute_q(_history(tuple(normal) + (special,)), spot=82.0,
                         today=TODAY)
    # 抑制後的加總必須嚴格小於「照單全收」的加總（特別分配確實被壓低）
    naive_sum = sum(a for _, a in normal) + 5.00
    assert q * 82.0 < naive_sum
    assert q == undamped   # 函式本身就內建抑制，兩次呼叫一致


def test_normal_month_to_month_variation_is_not_dampened():
    """正常配息的月間波動（研究樣本量級 $0.301–$0.345）遠小於 3 倍門檻，
    不該被誤判成離群值、被拉平。"""
    records = (("2026-08-03", 0.330), ("2026-07-01", 0.318),
              ("2026-06-01", 0.336), ("2026-05-01", 0.315))
    q = compute_q(_history(records), spot=82.245, today=TODAY)
    assert q == pytest.approx(sum(a for _, a in records) / 82.245)


def test_single_distribution_is_never_dampened():
    """只有一筆時沒有「中位數」可比較，不該被自己判成離群值。"""
    q = compute_q(_history((("2026-08-03", 5.0),)), spot=100.0, today=TODAY)
    assert q == pytest.approx(0.05)


# ---------- compute_q_asof：point-in-time（issue #161，擋 look-ahead） ----------

def test_a_distribution_ex_dated_after_the_observation_date_is_excluded():
    """load-bearing 保證：那天市場還不知道的分配不能算進那天的 q，
    否則就是 look-ahead bias（本票存在的理由）。"""
    observation_date = date(2026, 7, 1)
    future_ex_date = date(2026, 7, 2)   # 觀察日之後才除息
    history = _history(((future_ex_date.isoformat(), 0.33),))
    q = compute_q_asof(history, spot=82.0, observation_date=observation_date)
    assert q == 0.0


def test_a_distribution_exactly_on_the_observation_date_is_included():
    observation_date = date(2026, 7, 1)
    history = _history(((observation_date.isoformat(), 0.33),))
    q = compute_q_asof(history, spot=82.0, observation_date=observation_date)
    assert q == pytest.approx(0.33 / 82.0)


def test_a_distribution_older_than_the_trailing_window_is_excluded():
    observation_date = date(2026, 8, 10)
    cutoff = observation_date.toordinal() - 365
    from datetime import date as _d
    too_old = _d.fromordinal(cutoff).isoformat()          # 剛好 365 天前（exclusive）
    history = _history(((too_old, 10.0),))
    assert compute_q_asof(history, spot=100.0,
                          observation_date=observation_date) == 0.0


def test_asof_divides_by_the_spot_supplied_for_that_date_not_a_default():
    history = _history((("2026-07-01", 0.33),))
    q = compute_q_asof(history, spot=41.0, observation_date=date(2026, 7, 1))
    assert q == pytest.approx(0.33 / 41.0)


def test_asof_reuses_the_same_outlier_dampening_as_compute_q():
    observation_date = date(2026, 8, 3)
    normal = [("2026-0%d-01" % m, 0.30 + 0.01 * m) for m in range(1, 8)]
    special = ("2026-08-03", 5.00)
    history = _history(tuple(normal) + (special,))
    q_asof = compute_q_asof(history, spot=82.0, observation_date=observation_date)
    naive_sum = sum(a for _, a in normal) + 5.00
    assert q_asof * 82.0 < naive_sum


def test_asof_with_no_qualifying_distributions_yields_zero():
    """研究 §8 第 2 層一致的口徑：窗內無合格分配 → q=0，是正確答案，
    不是失敗。"""
    q = compute_q_asof(_history(()), spot=52.0, observation_date=date(2026, 8, 10))
    assert q == 0.0


def test_asof_non_positive_spot_is_rejected():
    with pytest.raises(ParamError):
        compute_q_asof(_history((("2026-07-01", 0.33),)), spot=0.0,
                       observation_date=date(2026, 7, 1))


def test_existing_compute_q_for_live_analysis_is_unaffected_by_asof_addition():
    """既有 `compute_q()`（無上界，today 語意）維持不動——本票只加點對點
    版本，不改既有即時分析路徑。"""
    records = (("2026-08-03", 0.330), ("2026-07-01", 0.318))
    q = compute_q(_history(records), spot=82.245, today=TODAY)
    assert q == pytest.approx((0.330 + 0.318) / 82.245)


# ---------- 序列化 roundtrip（快取落盤用） ----------

def test_history_survives_dict_roundtrip():
    history = _history((("2026-08-03", 0.33), ("2026-07-01", 0.318)),
                       source="nasdaq", stale=True)
    assert history_from_dict(history_to_dict(history)) == history


def test_history_from_dict_defaults_missing_source_and_stale():
    """既有已落盤的快取在這兩個欄位存在前寫入——讀回來要有安全預設，
    不因為欄位新增就讓舊快取整批失效（比照 `ratecurve.curve_from_dict`
    對 `stale` 的既有處理）。"""
    data = {"symbol": "TLT", "as_of": "2026-08-01",
            "distributions": [["2026-08-01", 0.3]]}
    history = history_from_dict(data)
    assert history.source == "unknown"
    assert history.stale is False
