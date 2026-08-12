"""Market Data App adapter 的解析與驗證（Settings／#125）。

全程用合成 payload，不打網路。⚠ 這些 payload 的形狀依官方文件撰寫，
**尚未經真實回應驗證**（#111 的工作）——因此這份測試證明的是「拿到這種
形狀時我們解得對」，不是「vendor 真的回這種形狀」。兩者的差別很重要，
不要拿這裡的綠燈去宣稱 #111 完成。
"""
import json
from urllib.error import HTTPError

import pytest

from option_chaser.data import marketdata
from option_chaser.models import FetchError


def _payload(**over):
    base = {
        "s": "ok",
        "optionSymbol": ["AAPL260918C00200000", "AAPL260918P00200000"],
        "side": ["call", "put"],
        "strike": [200.0, 200.0],
        "expiration": [1789689600, 1789689600],   # 2026-09-18
        "bid": [12.5, 8.0],
        "ask": [12.9, 8.4],
        "last": [12.7, 8.2],
        "volume": [1200, 800],
        "openInterest": [5000, 3000],
        "iv": [0.24, 0.26],
        "underlyingPrice": [205.0, 205.0],
    }
    base.update(over)
    return base


def _fake_get(body):
    return lambda url, token: json.dumps(body)


# ---------- 解析 ----------

def test_columnar_payload_becomes_contracts():
    snap = marketdata.map_chain_payload("AAPL", _payload(), "2026-08-12T00:00:00+00:00")
    assert len(snap.contracts) == 2
    assert snap.spot == 205.0
    assert snap.source == "marketdata-app"


def test_each_contract_gets_its_own_column_values():
    """欄狀 JSON 的第 i 筆散在各陣列的第 i 格——錯位會讓 call 拿到 put
    的報價，而且不會有任何東西報錯。"""
    snap = marketdata.map_chain_payload("AAPL", _payload(), "t")
    call = next(c for c in snap.contracts if c.option_type == "call")
    put = next(c for c in snap.contracts if c.option_type == "put")
    assert (call.bid, call.ask) == (12.5, 12.9)
    assert (put.bid, put.ask) == (8.0, 8.4)


def test_unix_expiry_becomes_an_iso_date():
    snap = marketdata.map_chain_payload("AAPL", _payload(), "t")
    assert snap.contracts[0].expiry == "2026-09-18"


def test_string_expiry_is_accepted_too():
    """文件兩處寫法不一致，兩種都吃——為了一個格式差異走備援不划算。"""
    snap = marketdata.map_chain_payload(
        "AAPL", _payload(expiration=["2026-09-18", "2026-09-18"]), "t")
    assert snap.contracts[0].expiry == "2026-09-18"


def test_zero_quotes_are_missing_values_not_real_prices():
    """沿用 cboe.py 的既有口徑：0.0 不是「便宜」，是這一格沒資料。"""
    snap = marketdata.map_chain_payload(
        "AAPL", _payload(bid=[0.0, 8.0], iv=[0.0, 0.26]), "t")
    call = next(c for c in snap.contracts if c.option_type == "call")
    assert call.bid is None
    assert call.implied_volatility is None


def test_short_columns_do_not_silently_drop_contracts():
    """vendor 對沒資料的欄位可能整個不回傳那個陣列；逐欄 zip 會少掉整批
    合約，這裡要補 None 而不是縮短。"""
    snap = marketdata.map_chain_payload("AAPL", _payload(iv=[0.24]), "t")
    assert len(snap.contracts) == 2
    assert snap.contracts[1].implied_volatility is None


def test_rows_without_a_usable_side_are_skipped():
    snap = marketdata.map_chain_payload(
        "AAPL", _payload(side=["call", "spread"]), "t")
    assert [c.option_type for c in snap.contracts] == ["call"]


def test_non_ok_status_is_a_fetch_error():
    with pytest.raises(FetchError):
        marketdata.map_chain_payload("AAPL", {"s": "no_data"}, "t")


def test_empty_chain_is_a_fetch_error_not_an_empty_snapshot():
    """空快照會一路流進引擎變成「沒有合格候選」，把抓取失敗偽裝成
    市場上沒東西可買。"""
    with pytest.raises(FetchError):
        marketdata.map_chain_payload("AAPL", _payload(optionSymbol=[]), "t")


def test_missing_spot_is_a_fetch_error():
    with pytest.raises(FetchError):
        marketdata.map_chain_payload(
            "AAPL", _payload(underlyingPrice=[None, None]), "t")


def test_any_parse_failure_becomes_a_fetch_error(monkeypatch):
    """收斂成 FetchError 是備援鏈接得住的前提——這正是「wire format 寫錯
    的後果是走備援、不是分析炸掉」那句話的機制。"""
    with pytest.raises(FetchError):
        marketdata.fetch_chain("AAPL", "tok",
                               http_get=lambda url, token: "not json")


# ---------- 驗證 ----------

def _http_error(code):
    def raise_it(url, token):
        raise HTTPError(url, code, "boom", {}, None)
    return raise_it


def test_verify_accepts_a_working_token():
    got = marketdata.verify("tok", http_get=_fake_get({"s": "ok",
                                                       "expirations": ["2026-09-18"]}))
    assert got.ok is True
    assert got.reason is None


@pytest.mark.parametrize("code,expected", [
    (401, "認證被拒"),
    (403, "認證被拒"),
    (429, "額度用盡"),
])
def test_verify_distinguishes_the_failure_modes(code, expected):
    """三種失敗使用者能做的事不同（換 token／等明天／檢查網路），不能
    糊成一句「連不上」。"""
    got = marketdata.verify("tok", http_get=_http_error(code))
    assert got.ok is False
    assert expected in got.reason


def test_verify_reports_a_network_failure_as_such():
    def boom(url, token):
        raise OSError("dns 查不到")
    got = marketdata.verify("tok", http_get=boom)
    assert got.ok is False
    assert "連不上" in got.reason


def test_verify_catches_a_200_response_that_still_says_error():
    """vendor 也會用 200＋`s: "error"` 表達失敗，不是只靠 HTTP 狀態碼。"""
    got = marketdata.verify("tok", http_get=_fake_get(
        {"s": "error", "errmsg": "Invalid token"}))
    assert got.ok is False
    assert "Invalid token" in got.reason


def test_verify_never_puts_the_token_in_the_reason():
    got = marketdata.verify("SECRET-TOKEN-1234", http_get=_http_error(401))
    assert "SECRET-TOKEN-1234" not in (got.reason or "")


def test_verify_uses_the_cheap_endpoint_not_the_whole_chain():
    """chain 端點是「回幾筆扣幾個 credit」——拿它當連線測試，按一次就
    可能燒掉使用者一整天的免費額度。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return json.dumps({"s": "ok", "expirations": []})

    marketdata.verify("tok", http_get=spy)
    assert all("/options/chain/" not in u for u in seen)
    assert any("/options/expirations/" in u for u in seen)
