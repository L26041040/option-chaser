"""FB3-01（#44）：Cboe 延遲報價 JSON adapter。

fixture 取自需求方 2026-08-02 於美股休市時段實測 `cdn.cboe.com` 的回傳
片段（見 issue #44 診斷紀錄）——盤外 bid/ask 凍結收盤值不歸零，正是
換源的理由。測試不打真網路：HTTP 層用注入的 fake http_get（比照
`data/treasury.py` 的 `fetch_curve(today, http_get=...)` 慣例）。"""
import json

import pytest

from option_chaser.data.cboe import fetch_chain, map_payload, parse_occ_symbol
from option_chaser.data.snapshot import load_snapshot, save_snapshot
from option_chaser.models import FetchError

# 需求方實測回傳的節選：一檔正常 call（iv=0.0 的深度 ITM）、一檔廢紙
# put（bid=0）、一檔小數履約價 call（iv 正常）。
PAYLOAD = {
    "timestamp": "2026-08-01 03:43:59",
    "data": {
        "current_price": 86.11,
        "close": 86.11,
        "options": [
            {"option": "TLT260731C00065000", "bid": 17.15, "bid_size": 43.0,
             "ask": 17.3, "ask_size": 46.0, "iv": 0.0, "open_interest": 0.0,
             "volume": 0.0, "delta": 1.0, "gamma": 0.0, "vega": 0.0,
             "theta": 0.0, "rho": 0.0, "theo": 17.235,
             "last_trade_price": 21.55, "last_trade_time": "2026-06-30T15:48:24",
             "prev_day_close": 17.8249998092651},
            {"option": "TLT260731P00065000", "bid": 0.0, "bid_size": 0.0,
             "ask": 0.01, "ask_size": 77.0, "iv": 0.0, "open_interest": 3.0,
             "volume": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0,
             "theta": 0.0, "rho": 0.0, "theo": 0.0,
             "last_trade_price": 0.01, "last_trade_time": "2026-07-13T12:38:12",
             "prev_day_close": 0.00499999988824129},
            {"option": "TLT260731C00079500", "bid": 2.67, "bid_size": 31.0,
             "ask": 2.79, "ask_size": 14.0, "iv": 2.8028, "open_interest": 42.0,
             "volume": 137.0, "delta": 1.0, "gamma": 0.0, "vega": 0.0,
             "theta": 0.0, "rho": 0.0, "theo": 2.735,
             "last_trade_price": 2.61, "last_trade_time": "2026-07-31T11:40:00",
             "prev_day_close": 3.29999995231628},
        ],
    },
}


# ---------- OCC 代號解析（純函式） ----------

def test_parse_occ_symbol_call():
    assert parse_occ_symbol("TLT260731C00065000") == ("2026-07-31", "call", 65.0)


def test_parse_occ_symbol_put():
    assert parse_occ_symbol("TLT260731P00065000") == ("2026-07-31", "put", 65.0)


def test_parse_occ_symbol_fractional_strike():
    assert parse_occ_symbol("TLT260731C00079500") == ("2026-07-31", "call", 79.5)


def test_parse_occ_symbol_longer_root():
    # root symbol 長度不定（如 BRKB），從尾端定位：8 位 strike×1000、
    # 1 位 C/P、6 位 yymmdd。
    assert parse_occ_symbol("BRKB280121C00500000") == ("2028-01-21", "call", 500.0)


# ---------- 欄位映射（純函式） ----------

def _snap():
    return map_payload("TLT", PAYLOAD, fetched_at="2026-08-02T14:30:00+00:00")


def test_map_payload_basics():
    snap = _snap()
    assert snap.symbol == "TLT"
    assert snap.source == "cboe"
    assert snap.spot == 86.11
    assert snap.fetched_at == "2026-08-02T14:30:00+00:00"
    assert len(snap.contracts) == 3


def test_map_payload_contract_fields():
    c = _snap().contracts[0]
    assert c.contract_symbol == "TLT260731C00065000"
    assert (c.option_type, c.strike, c.expiry) == ("call", 65.0, "2026-07-31")
    assert (c.bid, c.ask) == (17.15, 17.3)
    assert c.last == 21.55
    assert c.volume == 0 and isinstance(c.volume, int)
    assert c.open_interest == 0 and isinstance(c.open_interest, int)


def test_map_payload_iv_zero_becomes_none_missing_value_convention():
    """Cboe 以 iv=0.0 表示「無資料」→ 映射為 None，與 yfinance adapter 的
    缺值口徑（NaN→None）一致。注意：過濾結果不變——`iv_ok` 對 None 與
    0.0 同樣排除，缺 IV 的合約本來就不能進 BS 估值（引擎明文 assert）；
    這裡只是缺值表示法的統一，原始資料表不顯示誤導的 0.0。"""
    snap = _snap()
    assert snap.contracts[0].implied_volatility is None      # iv 0.0 → None
    assert snap.contracts[2].implied_volatility == 2.8028    # 正常值照留


def test_map_payload_roundtrips_through_snapshot_store(tmp_path):
    snap = _snap()
    p = tmp_path / "cboe.json"
    save_snapshot(snap, p)
    assert load_snapshot(p) == snap


# ---------- fetch_chain（HTTP 注入） ----------

def test_fetch_chain_uses_injected_http_get():
    urls = []

    def fake_get(url):
        urls.append(url)
        return json.dumps(PAYLOAD)

    snap = fetch_chain("TLT", http_get=fake_get)
    assert snap.source == "cboe"
    assert len(snap.contracts) == 3
    assert urls == [
        "https://cdn.cboe.com/api/global/delayed_quotes/options/TLT.json"]


def test_fetch_chain_http_failure_raises_fetch_error():
    def fake_get(url):
        raise OSError("blocked")

    with pytest.raises(FetchError):
        fetch_chain("TLT", http_get=fake_get)


def test_fetch_chain_empty_options_raises_fetch_error():
    empty = {"data": {"current_price": 86.11, "close": 86.11, "options": []}}
    with pytest.raises(FetchError):
        fetch_chain("TLT", http_get=lambda url: json.dumps(empty))


def test_fetch_chain_bad_spot_raises_fetch_error():
    bad = dict(PAYLOAD, data=dict(PAYLOAD["data"], current_price=0.0, close=0.0))
    with pytest.raises(FetchError):
        fetch_chain("TLT", http_get=lambda url: json.dumps(bad))


def test_fetch_chain_payload_without_data_key_raises_fetch_error():
    """Cboe 回 200 但內容是錯誤物件（無 "data" 鍵）——必須收斂成
    FetchError，`service.fetch_and_save` 的 yfinance 備援才接得住，
    不能讓 KeyError 裸奔到使用者面前。"""
    with pytest.raises(FetchError):
        fetch_chain("TLT", http_get=lambda url: json.dumps({"error": "nope"}))


def test_fetch_chain_malformed_occ_symbol_raises_fetch_error():
    bad = {"data": {"current_price": 86.11,
                    "options": [{"option": "GARBAGE", "bid": 1.0, "ask": 1.1}]}}
    with pytest.raises(FetchError):
        fetch_chain("TLT", http_get=lambda url: json.dumps(bad))


def test_parse_occ_symbol_rejects_malformed_input():
    for bad in ("GARBAGE", "", "TLT260731X00065000", "TLT26073C100065000"):
        with pytest.raises(ValueError):
            parse_occ_symbol(bad)
