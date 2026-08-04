import csv
import io
from datetime import date
from option_chaser.models import (
    OptionContract, ChainSnapshot, SCHEMA_VERSION, SnapshotSchemaError,
    STRATEGIES, SINGLE_LEG_STRATEGIES, SPREAD_STRATEGIES,
    leg_option_type, is_bullish, PairReport,
)
from option_chaser.data.snapshot import (
    save_snapshot, load_snapshot, snapshot_from_dict, snapshot_today,
    snapshot_to_csv, find_contract,
)
import pytest


def make_snap():
    c = OptionContract(
        contract_symbol="XYZ261016C00110000", strike=110.0, expiry="2026-10-16",
        bid=3.0, ask=3.25, last=3.1, volume=152, open_interest=830,
        implied_volatility=0.38, option_type="call",
    )
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol="XYZ",
        fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
        source="yfinance", contracts=(c,),
    )


def test_roundtrip(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    assert load_snapshot(p) == snap


def test_snapshot_from_dict_roundtrips_through_asdict():
    """V8（#56）：`Storage.get_snapshot` 回傳的是 `dataclasses.asdict()`
    的 dict 形式（serverless 沒有檔案系統，走儲存層而非 `load_snapshot`
    那條讀檔路徑）——`snapshot_from_dict` 是這條路徑的還原函式，跟
    `load_snapshot` 共用同一段還原邏輯，這裡直接驗證還原後與原物件
    相等。"""
    import dataclasses

    snap = make_snap()
    assert snapshot_from_dict(dataclasses.asdict(snap)) == snap


def test_strategy_helpers():
    assert STRATEGIES == ("long-call", "long-put", "bull-call-spread", "bear-put-spread")
    assert set(SINGLE_LEG_STRATEGIES) == {"long-call", "long-put"}
    assert set(SPREAD_STRATEGIES) == {"bull-call-spread", "bear-put-spread"}
    assert leg_option_type("long-call") == "call"
    assert leg_option_type("bull-call-spread") == "call"
    assert leg_option_type("long-put") == "put"
    assert leg_option_type("bear-put-spread") == "put"
    assert is_bullish("long-call") and is_bullish("bull-call-spread")
    assert not is_bullish("long-put") and not is_bullish("bear-put-spread")


def test_schema_mismatch_updated_for_v2(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 99')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError):
        load_snapshot(p)


def test_schema_v1_rejected_with_refetch_message(tmp_path):
    snap = make_snap()
    p = tmp_path / "s.json"
    save_snapshot(snap, p)
    text = p.read_text(encoding="utf-8").replace('"schema_version": 2', '"schema_version": 1')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotSchemaError) as ei:
        load_snapshot(p)
    assert "請重新抓取" in str(ei.value)


def test_pair_report_shape():
    pr = PairReport(total_pairs=6, removed_sanity=2, passed=4)
    assert pr.passed == 4


def test_snapshot_today_eastern():
    # 21:30 EDT on 7/15 is still 7/15 in New York
    assert snapshot_today("2026-07-15T21:30:00-04:00") == date(2026, 7, 15)
    # 03:00 UTC on 7/16 is 23:00 EDT on 7/15 -> "today" is 7/15
    assert snapshot_today("2026-07-16T03:00:00+00:00") == date(2026, 7, 15)


# ---------- 原始資料 CSV 轉換（QA1-10／#37：取得／轉換／輸出三層分離的
# 「轉換」層——純函式，不碰檔案 I/O 或 Streamlit） ----------

def test_snapshot_to_csv_header_and_one_row():
    snap = make_snap()
    rows = list(csv.reader(io.StringIO(snapshot_to_csv(snap))))
    assert rows[0] == ["contract_symbol", "option_type", "strike", "expiry",
                       "bid", "ask", "last", "volume", "open_interest",
                       "implied_volatility"]
    assert rows[1] == ["XYZ261016C00110000", "call", "110.0", "2026-10-16",
                       "3.0", "3.25", "3.1", "152", "830", "0.38"]
    assert len(rows) == 2


def test_snapshot_to_csv_none_fields_are_blank_not_the_string_none():
    c = OptionContract(
        contract_symbol="XYZ261016C00999000", strike=999.0, expiry="2026-10-16",
        bid=None, ask=None, last=None, volume=0, open_interest=0,
        implied_volatility=None, option_type="call",
    )
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=(c,))
    rows = list(csv.reader(io.StringIO(snapshot_to_csv(snap))))
    assert rows[1][4:6] == ["", ""]           # bid, ask
    assert rows[1][6] == ""                   # last
    assert rows[1][9] == ""                   # implied_volatility


def test_snapshot_to_csv_covers_every_contract_in_order():
    c1 = OptionContract(contract_symbol="A", strike=100.0, expiry="2026-10-16",
                        bid=1.0, ask=1.1, last=1.05, volume=1, open_interest=1,
                        implied_volatility=0.3, option_type="call")
    c2 = OptionContract(contract_symbol="B", strike=105.0, expiry="2026-10-16",
                        bid=2.0, ask=2.1, last=2.05, volume=2, open_interest=2,
                        implied_volatility=0.4, option_type="call")
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=(c1, c2))
    rows = list(csv.reader(io.StringIO(snapshot_to_csv(snap))))
    assert [r[0] for r in rows[1:]] == ["A", "B"]


def test_snapshot_to_csv_empty_chain_is_header_only():
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=())
    rows = list(csv.reader(io.StringIO(snapshot_to_csv(snap))))
    assert len(rows) == 1


# ---------- 精確合約查找（D1／#14：找同履約價的另一 option_type 合約） ----------

def test_find_contract_returns_the_matching_contract():
    call = OptionContract(contract_symbol="C100", option_type="call", strike=100.0,
                          expiry="2026-10-16", bid=2.4, ask=2.5, last=2.45,
                          volume=10, open_interest=20, implied_volatility=0.3)
    put = OptionContract(contract_symbol="P100", option_type="put", strike=100.0,
                         expiry="2026-10-16", bid=1.4, ask=1.5, last=1.45,
                         volume=10, open_interest=20, implied_volatility=0.3)
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=(call, put))
    assert find_contract(snap, "call", 100.0, "2026-10-16") is call
    assert find_contract(snap, "put", 100.0, "2026-10-16") is put


def test_find_contract_returns_none_when_no_match():
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=())
    assert find_contract(snap, "call", 100.0, "2026-10-16") is None
