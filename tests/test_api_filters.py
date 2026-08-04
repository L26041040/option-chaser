"""FB5-01／FB5-02（#62／#63）：過濾器不再刪除候選，經 HTTP API 驗證
（後端唯一接縫，spec #47 裁示；spec #61 Testing Decisions 明列此接縫）。

引擎層行為（關卡組成、逐關淘汰數）由 `tests/test_filters.py` 直測；這裡
驗證使用者實際看得到的東西——同一份快照下，過濾器不再把候選池砍到只剩
唯一倖存者。「帶標示」的證明（quote_warning 確實被觸發）用最小合成快照、
不靠這份大 fixture——見 `tests/test_spread_quality_flag.py` 開頭的說明：
排名只留每級距第一名，被卡住的那筆不保證擠得進榜。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from option_chaser.data.snapshot import load_snapshot
from option_chaser.filters import is_spread_wide
from option_chaser.models import AnalysisParams

# 既有 fixture（`tests/test_service.py` 亦用它）：10 個 call。修法前
# （FB5-01／FB5-02 之前）4 道硬門檻，池子只剩 6 組：
# - XYZC100D（strike 100.5, oi=5）只被 OI 關卡卡住 → FB5-01 放行，池子 7 組
# - XYZC102O（strike 102, bid 4.0/ask 6.0）只被 Spread 關卡卡住 → FB5-02
#   放行，池子 8 組
FIX = "tests/fixtures/xyz_v2_snapshot.json"
REQUEST = {"symbol": "XYZ", "target_price": 120.0, "target_month": "2026-08",
          "strategies": ["long-call"]}


def _client():
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap))


def test_low_open_interest_candidate_survives_and_pool_grows():
    r = _client().post("/api/analyze", json=REQUEST)
    assert r.status_code == 200
    result = r.json()["results"][0]

    assert result["filter_report"] == {"total": 10, "passed": 8}
    # single-leg 路徑的候選走 `candidates`，不是 `all_candidates`（T9
    # 附錄A13：`all_candidates` 只序列化 spread 路徑）。
    strikes = {c["legs"][0]["strike"] for c in result["candidates"]}
    assert 100.5 in strikes, "OI=5 的合約應留在候選池裡，不再被 OI 關卡刷掉"


def test_wide_spread_candidate_survives_and_would_be_flagged():
    """FB5-02（#63）票上驗收標準逐字對照：「以既有 fixture 斷言：原本
    被此關卡刷掉的合約現在進得了榜、且帶標示」——兩半都要在同一份既有
    fixture、同一張合約上證明，不能各自散在不同資料上算數。

    「進得了榜」：HTTP 回應的 `filter_report.passed` 直接證明（見上一條
    測試同一份 fixture 的 OI 案例，這裡疊加 Spread 案例）。
    「帶標示」：`candidates` 只序列化每級距第一名，XYZC102O 選不上任何
    一級（見 `test_ranking_formula_still_picks_highest_return_within_band`
    的同一批候選數字），無法從 HTTP 回應直接讀到它的 `quote_warning`；
    改為直接從**同一份**既有 fixture 撈出這張合約的原始 bid/ask，用
    `service._v4_fields` 實際呼叫的同一個純函式驗證——這就是
    `quote_warning` 會不會被觸發的唯一判準，不是另外猜一個公式。
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
    `filter_stages` 只剩 A 類（報價健全性）與 B 類（IV 數學前提）。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    labels = [s["label"] for s in result["filter_stages"]]
    assert labels == ["報價異常", "IV 異常"]
    assert not any(kw in l for l in labels
                   for kw in ("OI", "成交量", "Spread", "價差"))


def test_open_interest_still_visible_on_each_leg():
    """未平倉量不是消失——只是不再有生殺大權，資料仍隨候選一併回傳。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert all("open_interest" in c["legs"][0] for c in result["candidates"])


def test_cost_convention_unchanged():
    """spec #61：本輪只改「哪些候選進得了排名」，不改成本口徑（附錄 A14.2）。"""
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    for c in result["candidates"]:
        leg = c["legs"][0]
        assert c["natural_cost"] == leg["ask"]  # 單腿最差成交＝Ask


def test_ranking_formula_still_picks_highest_return_within_band():
    """spec #61：本輪不改排名公式，這裡不是靠「ranking.py 沒被動過」就
    交差，而是真的算給你看。

    平衡型級距（`ranking.classify` 的 Delta 0.35–0.65）修法後有 4 組候選
    競爭，包含新留下來的 XYZC100D（strike 100.5，基準報酬率最高，見票上
    附表）：
      100.5 → 2.841（新留下）／100.0 → 2.774／105.0 → 2.087／95.0 → 0.003
    若排名公式（依基準情境報酬率降冪排序取級內第一）壞了或方向反了，
    這裡不會是 100.5 中選——不是憑空斷言，是這組真實數字逼出來的。
    """
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    balanced = next(c for c in result["candidates"]
                    if 0.35 <= abs(c["net_delta"]) <= 0.65)
    assert balanced["legs"][0]["strike"] == 100.5
