"""利率曲線接線、快取與狀態語意（#67）。

Production 分析路徑正式接上利率曲線——這裡注入的 `rate_loader` 只是
測試替身，不代表選型（選型是 #73／#74，本票 provider 無關）。三種
狀態要能分辨：期限對齊成功／取得失敗退回固定 4%／使用者明確指定利率
（`rate_explicit`，本輪 web 路徑不可達，維持既有行為不變）。
"""
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.ratecurve import RateCurve

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}
CURVE = RateCurve(curve_date="2026-07-15", nodes=((0.5, 0.04), (2.0, 0.042)))


def _client(*, rate_loader, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(),
                                 rate_loader=rate_loader))


def _create_and_refresh(client, **overrides):
    sc = client.post("/api/scenarios", json={**NEW, **overrides})
    assert sc.status_code == 201, sc.text
    sid = sc.json()["id"]
    row = client.post(f"/api/scenarios/{sid}/refresh")
    assert row.status_code == 200, row.text
    return client.get(f"/api/scenarios/{sid}").json()["latest_result"]


# ---------- 三種狀態可分辨 ----------

def test_a_working_rate_source_replaces_the_offline_replay_note():
    view = _create_and_refresh(
        _client(rate_loader=lambda today: (CURVE, "Treasury 曲線 2026-07-15")))

    assert view["params"]["rate_note"] != "離線重放，未啟用利率曲線"
    assert "Treasury 曲線" in view["params"]["rate_note"]
    # 期限對齊——每個入選到期日各自一個利率，不是全部套同一個常數
    assert view["params"]["rate_by_expiry"]
    # RC1（#87）：結構化三態訊號，前端據此分流顯示，不靠字串猜。
    assert view["params"]["rate_curve_used"] is True
    assert view["params"]["rate_curve_date"] == "2026-07-15"
    assert view["params"]["rate_curve_stale"] is False


def test_a_failing_rate_source_falls_back_to_the_fixed_rate_without_failing_the_analysis():
    view = _create_and_refresh(
        _client(rate_loader=lambda today: (None, "測試來源目前打不通")))

    assert view["params"]["rate"] == 0.04
    assert view["params"]["rate_note"] == "測試來源目前打不通"
    assert view["params"]["rate_by_expiry"] == []
    # RC1（#87）：真正 fallback——沒有曲線，也就沒有 curve date 可掛。
    assert view["params"]["rate_curve_used"] is False
    assert view["params"]["rate_curve_date"] is None


def test_a_stale_curve_is_visible_on_the_analysis_params():
    """RC1（#87）：Neon 緊急備援窗沿用陳舊曲線時，`rate_curve_stale`
    要能讓前端明確標示 STALE，不是靜靜地跟新鮮曲線顯示成一樣。"""
    stale_curve = RateCurve(curve_date="2026-07-01", nodes=((1.0, 0.04),),
                            stale=True)
    view = _create_and_refresh(
        _client(rate_loader=lambda today: (
            stale_curve,
            "Treasury 曲線 2026-07-01（沿用快取，最新一次嘗試失敗：曲線不可得）")))

    assert view["params"]["rate_curve_used"] is True
    assert view["params"]["rate_curve_date"] == "2026-07-01"
    assert view["params"]["rate_curve_stale"] is True


# ---------- 一輪刷新共用同一條曲線 ----------

def test_multiple_scenarios_refreshed_in_one_round_share_the_same_curve_fetch():
    """開站／功能列鈕的一輪刷新對 N 個劇本各打一次 /refresh——底層
    provider 只該被呼叫一次，其餘命中快取。"""
    calls = []

    def loader(today):
        calls.append(today)
        return CURVE, "Treasury 曲線 2026-07-15"

    client = _client(rate_loader=loader)
    _create_and_refresh(client, symbol="AAA")
    _create_and_refresh(client, symbol="BBB")

    assert len(calls) == 1


# ---------- 資料源是可替換的接縫 ----------

def test_provider_is_swappable_without_touching_the_refresh_endpoint():
    """換一個完全不像 Treasury 的假 provider，刷新端點的行為（回傳
    形狀、200、快取生效）原封不動——它不知道也不需要知道背後是誰。"""
    fake_curve = RateCurve(curve_date="2099-01-01", nodes=((1.0, 0.09),))
    view = _create_and_refresh(
        _client(rate_loader=lambda today: (fake_curve, "假來源 2099-01-01")))

    assert view["params"]["rate_note"] == "假來源 2099-01-01"


# ---------- 運維診斷 ----------

def test_rate_status_is_visible_on_health_for_ops_diagnosis():
    client = _client(rate_loader=lambda today: (CURVE, "Treasury 曲線 2026-07-15"))
    _create_and_refresh(client)

    body = client.get("/api/health").json()
    assert body["rate"]["note"] == "Treasury 曲線 2026-07-15"
    assert body["rate"]["ok"] is True
    assert body["rate"]["fetched_at"]
    assert body["rate"]["last_success_at"]


def test_rate_status_reflects_a_failure_too():
    client = _client(rate_loader=lambda today: (None, "曲線不可得"))
    _create_and_refresh(client)

    body = client.get("/api/health").json()
    assert body["rate"]["ok"] is False
    assert body["rate"]["note"] == "曲線不可得"
    # 從沒成功過——不能因為剛好在失敗就編出一個時間
    assert body["rate"]["last_success_at"] is None


def test_rate_status_before_any_analysis_says_so():
    body = _client(
        rate_loader=lambda today: (CURVE, "x")).get("/api/health").json()
    assert body["rate"] is None
