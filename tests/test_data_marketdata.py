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


def _fake_request(body, *, status=200, headers=None):
    """`http_request` 注入用：成功回應（#144，取代舊的 `_fake_get`
    body-only 版本——`fetch_surface` 現在的注入點是 `HttpResponse`）。"""
    def request(url, token):
        return marketdata.HttpResponse(status=status, headers=headers or {},
                                       body=json.dumps(body))
    return request


def test_fetch_surface_targets_a_specific_expiration_when_given():
    """#134 修正：不帶 `expiration` 時 vendor 只回下一個月選，長天期候選
    永遠抓不到自己的座標——呼叫端算出目標到期日後，這裡要把它放進 URL。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return marketdata.HttpResponse(status=200, headers={},
                                       body=json.dumps(_surface_payload()))

    marketdata.fetch_surface("AAPL", "2026-08-01", "tok", http_request=spy,
                             expiration="2028-06-16")
    assert "date=2026-08-01" in seen[0]
    assert "expiration=2028-06-16" in seen[0]


def test_fetch_surface_omits_the_expiration_filter_when_not_given():
    """短天期候選不必多花這個篩選——vendor 預設的下一個月選本來就夠。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return marketdata.HttpResponse(status=200, headers={},
                                       body=json.dumps(_surface_payload()))

    marketdata.fetch_surface("AAPL", "2026-08-01", "tok", http_request=spy)
    assert "expiration=" not in seen[0]


# ---------- HTTP metadata primitive（#144）----------

def test_http_request_returns_status_headers_and_body(monkeypatch):
    """`_http_request` 是唯一真正打網路的低層 primitive——用一個假的
    `urlopen` context manager驗證它把 status／白名單標頭／body 都接出來。"""
    class _FakeHeaders:
        def get(self, name, default=None):
            return {"X-Api-Ratelimit-Limit": "100",
                    "X-Api-Ratelimit-Remaining": "42",
                    "X-Api-Ratelimit-Consumed": "1",
                    "Some-Other-Header": "should-not-leak"}.get(name, default)

    class _FakeResp:
        status = 200
        headers = _FakeHeaders()

        def read(self):
            return b'{"s": "ok"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(marketdata, "urlopen", lambda req, timeout: _FakeResp())
    got = marketdata._http_request("https://example.test/x", "tok")
    assert got.status == 200
    assert got.body == '{"s": "ok"}'
    assert got.headers == {"X-Api-Ratelimit-Limit": "100",
                           "X-Api-Ratelimit-Remaining": "42",
                           "X-Api-Ratelimit-Consumed": "1"}


def test_http_get_still_returns_only_the_body(monkeypatch):
    """`fetch_chain`／`verify` 的既有注入型別（body-only 字串）不受
    #144 影響——`_http_get` 是 `_http_request` 的薄殼。"""
    monkeypatch.setattr(marketdata, "_http_request",
                        lambda url, token: marketdata.HttpResponse(
                            status=200, headers={}, body="raw-body"))
    assert marketdata._http_get("https://example.test/x", "tok") == "raw-body"


# ---------- observer telemetry（#144）----------

def test_observer_sees_a_successful_fetch():
    events = []
    marketdata.fetch_surface("AAPL", "2026-08-01", "tok",
                             http_request=_fake_request(
                                 _surface_payload(),
                                 headers={"X-Api-Ratelimit-Remaining": "41"}),
                             observer=events.append)
    assert len(events) == 1
    got = events[0]
    assert got["http_status"] == 200
    assert got["X-Api-Ratelimit-Remaining"] == "41"
    assert got["vendor_status"] == "ok"
    assert got["vendor_errmsg"] is None
    # `_surface_payload()` 有 2 筆原始列，各是合格的 call／put 一筆。
    assert got["raw_rows"] == 2
    assert got["parsed_call_rows"] == 1
    assert got["parsed_put_rows"] == 1


def test_observer_sees_no_data_as_zero_rows_not_a_failure():
    events = []
    result = marketdata.fetch_surface(
        "AAPL", "2026-08-01", "tok",
        http_request=_fake_request({"s": "no_data"}), observer=events.append)
    assert result == {"call": [], "put": []}
    assert events[0]["vendor_status"] == "no_data"
    assert events[0]["raw_rows"] == 0


def test_observer_sees_a_vendor_reported_error():
    events = []
    with pytest.raises(FetchError):
        marketdata.fetch_surface(
            "AAPL", "2026-08-01", "tok",
            http_request=_fake_request({"s": "error", "errmsg": "bad request"}),
            observer=events.append)
    assert events[0]["vendor_status"] == "error"
    assert events[0]["vendor_errmsg"] == "bad request"


def test_observer_sees_http_429_before_quota_exhausted_is_raised():
    from option_chaser.models import QuotaExhausted

    events = []

    def request(url, token):
        raise HTTPError(url, 429, "boom",
                        {"X-Api-Ratelimit-Remaining": "0"}, None)

    with pytest.raises(QuotaExhausted):
        marketdata.fetch_surface("AAPL", "2026-08-01", "tok",
                                 http_request=request, observer=events.append)
    assert events[0]["http_status"] == 429
    assert events[0]["X-Api-Ratelimit-Remaining"] == "0"


def test_observer_sees_a_connection_failure():
    events = []

    def request(url, token):
        raise OSError("dns 查不到")

    with pytest.raises(FetchError):
        marketdata.fetch_surface("AAPL", "2026-08-01", "tok",
                                 http_request=request, observer=events.append)
    assert events[0]["http_status"] is None
    assert events[0]["vendor_status"] is None


def test_observer_sees_the_drop_reason_breakdown_when_raw_beats_parsed():
    """raw>0、parsed=0 是需求方點名要能診斷的那個情境（#146 的前置）——
    這裡先確認帳本本身在 #144 層級就是正確的。"""
    events = []
    marketdata.fetch_surface(
        "AAPL", "2026-08-01", "tok",
        http_request=_fake_request(_surface_payload(delta=[None, None])),
        observer=events.append)
    got = events[0]
    assert got["raw_rows"] == 2
    assert got["parsed_call_rows"] == 0
    assert got["parsed_put_rows"] == 0
    assert got["dropped_missing_delta"] == 2


def test_fetch_surface_default_observer_is_a_no_op():
    """`observer` 不傳時完全不影響既有行為（#144 的零行為變更保證）。"""
    got = marketdata.fetch_surface(
        "AAPL", "2026-08-01", "tok", http_request=_fake_request(_surface_payload()))
    assert got["call"] and got["put"]


# ---------- 單合約歷史序列（HIVT-01／#152，HIVT-02／#153） ----------
#
# 欄位形狀取自 #152 issue 留言存證的真實回應（2026-08-17，
# GET /v1/options/quotes/TLT281215C00094000/?from=2025-08-17&to=2026-08-17，
# HTTP 203，34 筆觀測），不是依文件猜的。

def _contract_history_payload(*, dates=None, ivs=None, status="ok"):
    if status != "ok":
        return {"s": status, "errmsg": "boom" if status == "error" else None}
    dates = dates if dates is not None else [1782763200, 1782849600, 1782936000]
    ivs = ivs if ivs is not None else [None, None, 0.185]
    n = len(dates)
    return {
        "s": "ok",
        "optionSymbol": ["TLT281215C00094000"] * n,
        "underlying": ["TLT"] * n,
        "expiration": [1860864000] * n,
        "side": ["call"] * n,
        "strike": [94] * n,
        "firstTraded": [1700000000] * n,
        "dte": [800] * n,
        "updated": dates,
        "bid": [1.5, 1.0, 2.56][:n],
        "bidSize": [1, 1, 1][:n],
        "mid": [4.0, 3.5, 3.13][:n],
        "ask": [6.5, 6.0, 3.7][:n],
        "askSize": [1, 1, 1][:n],
        "last": [0, 0, 0][:n],
        "openInterest": [10, 10, 10][:n],
        "volume": [0, 0, 0][:n],
        "inTheMoney": [False, False, False][:n],
        "intrinsicValue": [0, 0, 0][:n],
        "extrinsicValue": [4.0, 3.5, 3.13][:n],
        "underlyingPrice": [84.5, 84.6, 84.7][:n],
        "iv": ivs,
        "delta": [0.5, 0.5, 0.5][:n],
        "gamma": [0.01, 0.01, 0.01][:n],
        "theta": [-0.01, -0.01, -0.01][:n],
        "vega": [0.1, 0.1, 0.1][:n],
    }


def _fake_contract_request(payload, *, status=200, headers=None):
    def request(url, token):
        return marketdata.HttpResponse(status=status, headers=headers or {},
                                       body=json.dumps(payload))
    return request


def test_columnar_history_payload_becomes_date_iv_pairs():
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(_contract_history_payload()))
    assert got == [("2026-06-29", None), ("2026-06-30", None),
                   ("2026-07-01", 0.185)]


def test_http_203_is_a_success_not_a_failure():
    """真實 vendor 驗證發現的 bug class（#152）：Market Data App 對延遲
    報價回 HTTP 203，不是只有 200。不得因為 `status != 200` 就當失敗。"""
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(_contract_history_payload(),
                                            status=203))
    assert len(got) == 3


def test_null_iv_is_preserved_as_missing_not_dropped_not_defaulted():
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(
            _contract_history_payload(ivs=[None, None, None])))
    assert len(got) == 3
    assert all(iv is None for _, iv in got)


def test_zero_iv_is_also_treated_as_missing():
    """既有 `_num()` 缺值口徑（0.0 一律缺值）延伸到這裡，跟這個檔案其他
    地方一致——報價為零不是「便宜」，是這一格沒有資料。"""
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(
            _contract_history_payload(ivs=[0.0, 0.1, 0.2])))
    assert got[0][1] is None


def test_points_are_sorted_by_date_ascending_regardless_of_payload_order():
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(_contract_history_payload(
            dates=[1782936000, 1782763200, 1782849600],
            ivs=[0.3, 0.1, 0.2])))
    assert [d for d, _ in got] == ["2026-06-29", "2026-06-30", "2026-07-01"]


def test_row_missing_updated_date_is_dropped_others_still_parsed():
    payload = _contract_history_payload()
    payload["updated"] = [1782763200, None, 1782936000]
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(payload))
    assert len(got) == 2


def test_non_ok_status_is_a_fetch_error_not_a_silent_empty_result():
    with pytest.raises(FetchError):
        marketdata.fetch_contract_history(
            "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
            http_request=_fake_contract_request(
                _contract_history_payload(status="error")))


def test_url_carries_the_exact_contract_symbol_and_date_range():
    seen = []

    def spy(url, token):
        seen.append(url)
        return marketdata.HttpResponse(status=200, headers={},
                                       body=json.dumps(_contract_history_payload()))

    marketdata.fetch_contract_history("TLT281215C00094000", "2025-08-17",
                                      "2026-08-17", "tok", http_request=spy)
    assert "TLT281215C00094000" in seen[0]
    assert "from=2025-08-17" in seen[0]
    assert "to=2026-08-17" in seen[0]


def test_out_of_range_from_date_is_not_a_precondition_to_request():
    """#152 真實驗證：`from` 早於掛牌日期不報錯，vendor 自動截斷到真正
    存在的歷史——這裡只驗證 adapter 不會因為傳了一個很早的 `from` 就
    自己先擋下請求（`http_request` 收到的 URL 原樣帶著呼叫端傳入的
    `from`，adapter 不做任何 listing-date 相關的 preflight）。"""
    seen = []

    def spy(url, token):
        seen.append(url)
        return marketdata.HttpResponse(status=200, headers={},
                                       body=json.dumps(_contract_history_payload()))

    marketdata.fetch_contract_history("TLT281215C00094000", "2021-08-18",
                                      "2026-08-17", "tok", http_request=spy)
    assert "from=2021-08-18" in seen[0]


def test_contract_history_observer_sees_telemetry():
    events = []
    marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(
            _contract_history_payload(),
            headers={"X-Api-Ratelimit-Consumed": "1"}),
        observer=events.append)
    assert len(events) == 1
    got = events[0]
    assert got["http_status"] == 200
    assert got["X-Api-Ratelimit-Consumed"] == "1"
    assert got["vendor_status"] == "ok"
    assert got["raw_rows"] == 3
    assert got["parsed_rows"] == 3
    assert got["null_iv_count"] == 2


def test_contract_history_observer_sees_vendor_error():
    events = []
    with pytest.raises(FetchError):
        marketdata.fetch_contract_history(
            "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
            http_request=_fake_contract_request(
                _contract_history_payload(status="error")),
            observer=events.append)
    assert events[0]["vendor_status"] == "error"
    assert events[0]["vendor_errmsg"] == "boom"


def test_contract_history_observer_sees_http_429_before_quota_exhausted():
    from option_chaser.models import QuotaExhausted

    events = []

    def request(url, token):
        raise HTTPError(url, 429, "boom", {"X-Api-Ratelimit-Remaining": "0"}, None)

    with pytest.raises(QuotaExhausted):
        marketdata.fetch_contract_history(
            "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
            http_request=request, observer=events.append)
    assert events[0]["http_status"] == 429


def test_contract_history_observer_sees_a_connection_failure():
    events = []

    def request(url, token):
        raise OSError("dns 查不到")

    with pytest.raises(FetchError):
        marketdata.fetch_contract_history(
            "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
            http_request=request, observer=events.append)
    assert events[0]["http_status"] is None
    assert events[0]["vendor_status"] is None


def test_contract_history_default_observer_is_a_no_op():
    got = marketdata.fetch_contract_history(
        "TLT281215C00094000", "2025-08-17", "2026-08-17", "tok",
        http_request=_fake_contract_request(_contract_history_payload()))
    assert len(got) == 3
