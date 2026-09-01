"""FB5-01／FB5-02／FB5-03（#62／#63／#64）：過濾器不再刪除候選，經
HTTP API 驗證（後端唯一接縫，spec #47 裁示；spec #61 Testing Decisions
明列此接縫）。

引擎層行為（關卡組成、逐關淘汰數）由 `tests/test_filters.py` 直測；這裡
驗證使用者實際看得到的東西——同一份快照下，過濾器不再把候選池砍到只剩
唯一倖存者。「帶標示」的證明（`wide_spread_warning`／`quote_warning`
確實被觸發）用最小合成快照、不靠這份大 fixture——見
`tests/test_spread_quality_flag.py` 開頭的說明：
排名只留每級距第一名，被卡住的那筆不保證擠得進榜。FB5-03 的單調性違反
證明改走 `candidate_pool` 直接查找（見
`test_monotonicity_warning_reaches_the_serialized_candidate` 內的說明——
REPAIR-09／#246 之前 XYZC100D 剛好是平衡型級距的第一名可以直接從
`result["candidates"]` 讀到，該票之後不再是，見該測試 docstring）。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from option_chaser.data.snapshot import load_snapshot
from option_chaser.filters import is_spread_wide
from option_chaser.models import AnalysisParams
from option_chaser.ratecurve import RateCurve

# 既有 fixture（`tests/test_service.py` 亦用它）：10 個 call。修法前
# （FB5-01／FB5-02 之前）4 道硬門檻，池子只剩 6 組：
# - XYZC100D（strike 100.5, oi=5）只被 OI 關卡卡住 → FB5-01 放行，池子 7 組
# - XYZC102O（strike 102, bid 4.0/ask 6.0）只被 Spread 關卡卡住 → FB5-02
#   放行，池子 8 組
FIX = "tests/fixtures/xyz_v2_snapshot.json"
REQUEST = {"symbol": "XYZ", "target_price": 120.0, "target_month": "2026-08",
          "strategies": ["long-call"]}


# Hermetic（#236）：`create_app()` 的 `rate_loader`／`dividend_loader`
# **預設接的是真管線**（Treasury／Yahoo→FMP→Nasdaq）。這份 fixture 用的
# 假 symbol `"XYZ"` 恰好是**真實上市代號**，所以在連得到外網的環境裡，
# 預設 loader 會抓到那家公司的真實配息、算出非零 q、`carry_calibrated`
# 變 True，估值與級距排名跟著位移——下面幾條測試斷言的 `strike 100.5`
# 就是這樣掉出榜的。同一個坑 `scripts/gen_contract_sample.py` 早有紀錄。
#
# 因此這裡把兩個輸入都釘死。合成標的沒有配息（q=0），利率用一條固定
# 假曲線——這正是這幾條測試的既有期望值（FB5-01／#62 當初量到的那組
# 數字）成立的條件，不是為了讓測試變綠而調的參數。
_FAKE_RATE_CURVE = RateCurve(curve_date="2026-07-15",
                             nodes=((0.25, 0.045), (1.0, 0.043),
                                    (2.0, 0.041), (5.0, 0.040)))


def _fake_rate_loader(today):
    return _FAKE_RATE_CURVE, f"假曲線 {_FAKE_RATE_CURVE.curve_date}"


def _fake_dividend_loader(symbol, today):
    """合成標的不配息 → q=0。回傳 `None` 是這個介面表達「沒有配息資料」
    的既有方式（見 `service._resolve_q` 的 fallback 分層）。"""
    return None, "測試 fixture 的合成標的沒有配息"


def _client():
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 rate_loader=_fake_rate_loader,
                                 dividend_loader=_fake_dividend_loader))


def test_low_open_interest_candidate_survives_and_pool_grows():
    r = _client().post("/api/analyze", json=REQUEST)
    assert r.status_code == 200
    body = r.json()
    result = body["results"][0]
    pool = body["candidate_pool"]

    assert result["filter_report"] == {"total": 10, "passed": 8}
    # 「進得了候選池」（過濾器不刪除）與「擠進 `result["candidates"]`
    # 排行榜前段」是兩件獨立的事——REPAIR-09（#246）之前 strike 100.5
    # 剛好是它那個級距的排行榜冠軍，兩者恰好疊在一起看得到；修法後它的
    # 到期日（2026-10-16，晚於這份 fixture 的錨點）殘留時間價值被修正
    # 拿掉，不再是冠軍（見 `test_ranking_formula_still_picks_highest_
    # return_within_band`），但它依然完整通過品質過濾、依然在
    # `candidate_pool`（完整序列化結構，不論排行榜名次）裡——這才是本
    # 測試真正要證明的事：OI 關卡不再有生殺大權。
    strikes = {c["legs"][0]["strike"] for c in pool.values()}
    assert 100.5 in strikes, "OI=5 的合約應留在候選池裡，不再被 OI 關卡刷掉"


def test_wide_spread_candidate_survives_and_would_be_flagged():
    """FB5-02（#63）票上驗收標準逐字對照：「以既有 fixture 斷言：原本
    被此關卡刷掉的合約現在進得了榜、且帶標示」——兩半都要在同一份既有
    fixture、同一張合約上證明，不能各自散在不同資料上算數。

    「進得了榜」：HTTP 回應的 `filter_report.passed` 直接證明（見上一條
    測試同一份 fixture 的 OI 案例，這裡疊加 Spread 案例）。
    「帶標示」：`candidates` 只序列化每級距第一名，XYZC102O 選不上任何
    一級（見 `test_ranking_formula_still_picks_highest_return_within_band`
    的同一批候選數字），無法從 HTTP 回應直接讀到它的顯示旗標；
    改為直接從**同一份**既有 fixture 撈出這張合約的原始 bid/ask，用
    `is_spread_wide` 實際呼叫的同一個純函式驗證——這就是
    `wide_spread_warning`（MVP V3／#104）會不會被觸發的唯一判準，不是
    另外猜一個公式。
    """
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert result["filter_report"]["passed"] == 8   # 「進得了榜」

    snap = load_snapshot(FIX)
    xyzc102o = next(c for c in snap.contracts
                    if c.option_type == "call" and c.strike == 102.0)
    assert (xyzc102o.bid, xyzc102o.ask) == (4.0, 6.0), "fixture 內容變了，數字要跟著重算"
    p = AnalysisParams(target_price=120.0, target_month="2026-08")
    assert is_spread_wide(xyzc102o.bid, xyzc102o.ask, p) is True   # 「帶標示」


def test_per_expiry_pool_size_grows_not_just_the_aggregate():
    """票上寫的是「各到期日的候選池數量」，不是整批合約數——兩者可能
    脫鉤（某一期漲、另一期不變）。`expiry_counts` 是逐到期日的候選數，
    FB5-01／FB5-02 之前 2026-10-16 只有 4 組（XYZC100D 被 OI 卡住、
    XYZC102O 被 Spread 卡住），兩張票疊加後 6 組；另外兩個到期日各只有
    1 張合約，兩個關卡都沒擋過它們，數字理應不動——這一起斷言，證明
    修法不是全面亂動、只精準命中真正被卡住的那些合約。
    """
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert dict(result["expiry_counts"]) == {
        "2026-08-01": 1, "2026-10-16": 6, "2026-11-20": 1,
    }


def test_filter_stages_only_data_integrity_and_iv_remain():
    """spec #61 三分類：C 類（OI／成交量／價差寬度）全部不再是硬門檻，
    `filter_stages` 只剩 A 類（報價健全性）／B 類（IV 數學前提）＋
    T05（#226，Initial V2）新增的 B 類導出層安全網（正常報價下恆為
    0 筆移除，仍會作為一個 stage 出現，讓剔除是可見的而非靜默）。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    labels = [s["label"] for s in result["filter_stages"]]
    assert labels == ["報價異常", "IV 異常", "成本或報酬為不可能值（B 層安全網）"]
    assert not any(kw in l for l in labels
                   for kw in ("OI", "成交量", "Spread", "價差"))


def test_open_interest_still_visible_on_each_leg():
    """未平倉量不是消失——只是不再有生殺大權，資料仍隨候選一併回傳。"""
    body = _client().post("/api/analyze", json=REQUEST).json()
    result, pool = body["results"][0], body["candidate_pool"]
    assert all("open_interest" in pool[k]["legs"][0] for k in result["candidates"])


def test_cost_convention_unchanged():
    """spec #61：本輪只改「哪些候選進得了排名」，不改成本口徑（附錄 A14.2）。"""
    body = _client().post("/api/analyze", json=REQUEST).json()
    result, pool = body["results"][0], body["candidate_pool"]
    for k in result["candidates"]:
        c = pool[k]
        leg = c["legs"][0]
        assert c["natural_cost"] == leg["ask"]  # 單腿最差成交＝Ask


def test_ranking_formula_still_picks_highest_return_within_band():
    """spec #61：本輪不改排名公式，這裡不是靠「ranking.py 沒被動過」就
    交差，而是真的算給你看。

    平衡型級距（`ranking.classify` 的 Delta 0.35–0.65）本身有 5 組候選
    競爭，`net_delta` 不受 REPAIR-09（#246）影響（Greeks 走 `today`／
    `t_now`，跟排名基準估值日是兩件事，已用 `git stash` 比對修法前後
    net_delta 逐位元相同）——變的只有各自的 `baseline_return`。

    REPAIR-09（#246）之前，XYZC100D（strike 100.5，到期日 2026-10-16，
    晚於這份 fixture 的錨點 2026-08-21）殘留時間價值把報酬率灌水到
    **2.8541**，蓋過同一級距內到期日早於錨點、不受影響的 strike 100.0
    （2026-08-01 到期，報酬率恆為 **2.7736**）。修法後 XYZC100D 的報酬率
    正確降到 **2.6111**（到期時是價外／輕度價內的內在價值，不再含時間
    價值），改由 strike 100.0 中選——已用 `git stash` 對照過修法前後
    完整候選池數字：
      修法前 100.5→2.8541（舊冠軍）／100.0→2.7736／102.0→2.2480／
             105.0→2.0990／95.0→0.0041
      修法後 100.5→2.6111 ／100.0→2.7736（新冠軍）／102.0→2.0000／
             105.0→1.7273／95.0→-0.1935
    若排名公式（依基準情境報酬率降冪排序取級內第一）壞了或方向反了，
    這裡不會是 100.0 中選——不是憑空斷言，是這組真實數字逼出來的。
    """
    body = _client().post("/api/analyze", json=REQUEST).json()
    result, pool = body["results"][0], body["candidate_pool"]
    balanced = next(pool[k] for k in result["candidates"]
                    if 0.35 <= abs(pool[k]["net_delta"]) <= 0.65)
    assert balanced["legs"][0]["strike"] == 100.0
    assert balanced["legs"][0]["expiry"] == "2026-08-01"


def test_monotonicity_warning_reaches_the_serialized_candidate():
    """FB5-03（#64）票上驗收標準：「標示出現在候選的序列化結構中」。

    這份既有 fixture 剛好自然帶著一組真實的單調性違反：XYZC100D（strike
    100.5, ask 5.4, 到期 2026-10-16）比 XYZC102O（strike 102, ask 6.0，
    同一到期日）便宜，call 履約價越高應該越便宜（或持平），這裡反過來了
    ——跟需求方原話「100/105/110，105 卻比 100 便宜」同一個形狀。

    REPAIR-09（#246）之前，XYZC100D 剛好是平衡型級距的第一名，可以直接
    從 `result["candidates"]`（每級距只留冠軍的排行榜）撈到。修法後
    XYZC100D 的到期日（2026-10-16）晚於這份 fixture 的錨點
    （2026-08-21），殘留時間價值被修正拿掉，報酬率從 2.8541 降到
    2.6111——不再是同級距的冠軍（見
    `test_ranking_formula_still_picks_highest_return_within_band`，冠軍
    換成到期日早於錨點、不受影響的 strike 100.0）。這證明的是「標示
    出現在候選的序列化結構中」——XYZC100D 依然通過品質過濾、依然帶著
    `monotonicity_warning`，只是不再擠進**排行榜前段**，兩者是獨立的
    事：`candidate_pool` 才是完整的序列化結構（不論有沒有進排行榜），
    直接按 key 查找。

    也順便釘住這是**獨立欄位**：`wide_spread_warning`（MVP V3／#104 顯示
    旗標，取代已不對外序列化的 `quote_warning`）不該被單調性違反污染
    （XYZC100D 本身報價／價差都正常，`wide_spread_warning` 應為 False）。
    """
    body = _client().post("/api/analyze", json=REQUEST).json()
    pool = body["candidate_pool"]
    xyzc100d = pool["long-call|100.5|2026-10-16"]
    assert xyzc100d["monotonicity_warning"] is True
    assert xyzc100d["wide_spread_warning"] is False
    assert "quote_warning" not in xyzc100d


def test_monotonicity_violation_does_not_shrink_the_pool():
    """FB5-03（#64）核心裁示：只標不刪。同一份 fixture 裡確實存在違反
    （見上一條測試），`filter_report.passed` 不因此減少——與 FB5-01／
    FB5-02 疊加的數字（8）完全一致。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert result["filter_report"]["passed"] == 8


def test_filter_stages_carry_their_class_over_http():
    """FB5-04（#65，spec #61）票上驗收標準：分類要「在程式碼中明確可讀」
    ——這裡驗證它也確實走過序列化，到得了實際的 HTTP 回應，不是只活在
    `filters.py` 內部。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert [(s["label"], s["filter_class"]) for s in result["filter_stages"]] == [
        ("報價異常", "A"), ("IV 異常", "B"),
        ("成本或報酬為不可能值（B 層安全網）", "B"),
    ]


def test_quality_flags_reach_http_response_and_never_shrink_the_pool():
    """FB5-04（#65，spec #61）：C 類品質標示在整個合格池裡的計數要到得了
    HTTP 回應——這份 fixture 已知的三筆疑慮全部疊加：XYZC102O 買賣價差
    偏大（見上面 `test_wide_spread_candidate_survives_and_would_be_flagged`）、
    XYZC100D／XYZC102O 這對單調性違反（見
    `test_monotonicity_warning_reaches_the_serialized_candidate`），
    另有 1 筆今日無成交。無論標示多少筆，`filter_report.passed` 都維持
    8——這是「標示」不是「排除」的直接證明。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    flags = dict((f["label"], f["count"]) for f in result["quality_flags"])
    assert flags["買賣價差偏大"] == 1
    assert flags["報價與鄰近履約價不一致，疑似陳舊報價"] == 2
    assert flags["今日無成交量"] == 1
    assert result["filter_report"]["passed"] == 8
