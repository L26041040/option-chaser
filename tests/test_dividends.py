"""#123（spec #117 §2）q 純函式：TTM 金額 / spot、離群值抑制、序列化。

無 I/O、無 wall-clock——所有輸入為固定 fixture。抓取層見
`tests/test_data_dividends.py`。
"""
from __future__ import annotations

from datetime import date

import pytest

from option_chaser.dividends import (DividendHistory, DividendRecord, compute_q,
                                     history_from_dict, history_to_dict)
from option_chaser.models import ParamError

TODAY = date(2026, 8, 10)


def _history(records: tuple[tuple[str, float], ...], source="yahoo",
            stale=False) -> DividendHistory:
    return DividendHistory(
        symbol="TLT", as_of="2026-08-10", source=source, stale=stale,
        distributions=tuple(DividendRecord(ex_date=d, amount=a) for d, a in records))


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
