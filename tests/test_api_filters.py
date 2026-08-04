"""FB5-01（#62）：過濾器不再刪除候選，經 HTTP API 驗證（後端唯一接縫，
spec #47 裁示；spec #61 Testing Decisions 明列此接縫）。

引擎層行為（關卡組成、逐關淘汰數）由 `tests/test_filters.py` 直測；這裡
驗證使用者實際看得到的東西——同一份快照下，過濾器不再把候選池砍到只剩
唯一倖存者。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from option_chaser.data.snapshot import load_snapshot

# 既有 fixture（`tests/test_service.py` 亦用它）：10 個 call，其中
# XYZC100D（strike 100.5, oi=5）報價／IV／價差三關皆正常，只有 OI 不足
# 10。修法前這一筆被 OI 關卡刷掉，池子剩 6 組；修法後留在池子裡，剩 7 組。
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

    assert result["filter_report"] == {"total": 10, "passed": 7}
    # single-leg 路徑的候選走 `candidates`，不是 `all_candidates`（T9
    # 附錄A13：`all_candidates` 只序列化 spread 路徑）。
    strikes = {c["legs"][0]["strike"] for c in result["candidates"]}
    assert 100.5 in strikes, "OI=5 的合約應留在候選池裡，不再被 OI 關卡刷掉"


def test_per_expiry_pool_size_grows_not_just_the_aggregate():
    """票上寫的是「各到期日的候選池數量」，不是整批合約數——兩者可能
    脫鉤（某一期漲、另一期不變）。`expiry_counts` 是逐到期日的候選數，
    修法前 2026-10-16 只有 4 組（XYZC100D 被 OI=5 卡住），修法後 5 組；
    另外兩個到期日各只有 1 張合約，OI 從未擋過它們，數字理應不動——
    這一起斷言，證明修法不是全面亂動、只精準命中真正被 OI 卡住的那期。
    """
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    assert dict(result["expiry_counts"]) == {
        "2026-08-01": 1, "2026-10-16": 5, "2026-11-20": 1,
    }


def test_filter_stages_no_longer_include_oi_or_volume():
    r = _client().post("/api/analyze", json=REQUEST)
    result = r.json()["results"][0]
    labels = [s["label"] for s in result["filter_stages"]]
    assert labels == ["報價異常", "IV 異常", "Spread 過寬"]
    assert not any("OI" in l or "成交量" in l for l in labels)


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
