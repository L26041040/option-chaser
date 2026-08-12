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


# ---------- 歷史曲面（#126／#134）----------

def _surface_payload(**over):
    base = {
        "s": "ok",
        "optionSymbol": ["AAPL260918C00200000", "AAPL260918P00200000"],
        "side": ["call", "put"],
        "dte": [37, 37],
        "delta": [0.32, -0.29],
        "iv": [0.24, 0.26],
    }
    base.update(over)
    return base


def test_surface_payload_becomes_points_grouped_by_side():
    got = marketdata.map_surface_payload(_surface_payload())
    assert [(p.dte, p.delta, p.iv) for p in got["call"]] == [(37, 0.32, 0.24)]
    # put 的 delta 取絕對值——跟 call 的網格混在一起插值才有意義。
    assert [(p.dte, p.delta, p.iv) for p in got["put"]] == [(37, 0.29, 0.26)]


def test_rows_missing_delta_or_iv_or_dte_are_skipped():
    got = marketdata.map_surface_payload(
        _surface_payload(delta=[None, -0.29], iv=[0.24, 0.0]))
    assert got["call"] == []
    assert got["put"] == []   # iv=0.0 經 `_num` 視為缺值


def test_no_data_status_is_an_empty_surface_not_an_error():
    """`no_data` 是帶了 `expiration` 篩選後的正常撲空（#134）——那個到期
    日在那個歷史日期還沒掛牌，不是 vendor 故障，不該讓整批 backfill 中止。"""
    got = marketdata.map_surface_payload({"s": "no_data"})
    assert got == {"call": [], "put": []}


def test_error_status_is_still_a_fetch_error():
    with pytest.raises(FetchError):
        marketdata.map_surface_payload({"s": "error", "errmsg": "boom"})


def test_fetch_surface_targets_a_specific_expiration_when_given():
    """#134 修正：不帶 `expiration` 時 vendor 只回下一個月選，長天期候選
    永遠抓不到自己的座標——呼叫端算出目標到期日後，這裡要把它放進 URL。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return json.dumps(_surface_payload())

    marketdata.fetch_surface("AAPL", "2026-08-01", "tok", http_get=spy,
                             expiration="2028-06-16")
    assert "date=2026-08-01" in seen[0]
    assert "expiration=2028-06-16" in seen[0]


def test_fetch_surface_omits_the_expiration_filter_when_not_given():
    """短天期候選不必多花這個篩選——vendor 預設的下一個月選本來就夠。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return json.dumps(_surface_payload())

    marketdata.fetch_surface("AAPL", "2026-08-01", "tok", http_get=spy)
    assert "expiration=" not in seen[0]
