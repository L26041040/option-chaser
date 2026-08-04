"""V1（#48）：HTTP API 契約測試——後端的**唯一測試接縫**（spec #47 裁示）。

以測試客戶端直測 FastAPI app，不起真伺服器、不打真網路：資料源由
`create_app(fetch=...)` 注入。引擎計算的正確性不在這裡重測（
`option_chaser/` 既有全套測試負責），這裡只驗證 HTTP 契約：狀態碼、
錯誤映射、以及回應主體確實是引擎既有的 view dict 序列化。"""
import json
from pathlib import Path

from fastapi.testclient import TestClient   # 缺 fastapi 要紅燈，不可 importorskip

from api_app.main import create_app
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import FetchError, ParamError

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
CONTRACT_SAMPLE = Path("contracts/analysis_sample.json")

# 與 `scripts/gen_contract_sample.py` 同一組參數（契約樣本比對需一致）。
REQUEST = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
           "strategies": ["bull-call-spread"]}


def _client(fetch=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=fetch or (lambda symbol: snap)))


def test_health_reports_ok_and_engine_version():
    r = _client().get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["engine_version"]


def test_analyze_returns_the_engine_view_dict():
    r = _client().post("/api/analyze", json=REQUEST)
    assert r.status_code == 200
    view = r.json()
    # 契約＝既有 `store.serialize_result` 的 view dict，前端零金融計算：
    # 每個顯示數字都已由引擎算好。
    assert view["meta"]["symbol"] == "XYZ"
    assert view["meta"]["spot"] > 0
    assert view["meta"]["source"]           # 資料源如實記錄（Cboe 可達性可由此驗證）
    assert view["baseline_expiry"]
    assert view["results"] and view["results"][0]["strategy"] == "bull-call-spread"
    assert "expiry_top10" in view["results"][0]


def test_analyze_passes_the_requested_symbol_to_the_data_source():
    seen = []
    snap = load_snapshot(FIX)

    def fetch(symbol):
        seen.append(symbol)
        return snap

    _client(fetch).post("/api/analyze", json=dict(REQUEST, symbol="TLT"))
    assert seen == ["TLT"]


def test_analyze_does_not_write_to_the_filesystem(tmp_path, monkeypatch):
    """serverless 檔案系統唯讀——分析路徑不得落盤。"""
    client = _client()
    monkeypatch.chdir(tmp_path)
    assert client.post("/api/analyze", json=REQUEST).status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_fetch_failure_maps_to_502():
    def boom(symbol):
        raise FetchError("both sources down")

    r = _client(boom).post("/api/analyze", json=REQUEST)
    assert r.status_code == 502
    assert "detail" in r.json()


def test_engine_param_error_maps_to_400(monkeypatch):
    """ParamError 來自引擎（`run_with_snapshot` 的請求驗證），不是資料源
    ——V4（#52）把抓鏈與分析拆成兩個失敗環節後，這裡也照真實來源模擬。"""
    from option_chaser import service

    def boom(*args, **kwargs):
        raise ParamError("bad month")

    monkeypatch.setattr(service, "run_with_snapshot", boom)
    r = _client().post("/api/analyze", json=REQUEST)
    assert r.status_code == 400


def test_malformed_body_maps_to_422():
    r = _client().post("/api/analyze", json={"symbol": "XYZ"})   # 缺必填欄位
    assert r.status_code == 422


def test_unknown_strategy_is_rejected_before_reaching_the_engine():
    called = []

    def fetch(symbol):
        called.append(symbol)
        return load_snapshot(FIX)

    r = _client(fetch).post("/api/analyze",
                            json=dict(REQUEST, strategies=["not-a-strategy"]))
    assert r.status_code == 422
    assert called == []


# ---------- 契約樣本：前端 mock 與後端 fixture 共用同一份 ----------

def test_contract_sample_matches_the_live_api_response():
    """spec #47 裁示：前端 mock 所用的 API 樣本與後端 fixture 共用同一份，
    防止兩邊契約漂移。樣本以 `scripts/gen_contract_sample.py` 重產。"""
    assert CONTRACT_SAMPLE.exists(), (
        "契約樣本不存在，請跑 scripts/gen_contract_sample.py")
    expected = json.loads(CONTRACT_SAMPLE.read_text(encoding="utf-8"))
    actual = _client().post("/api/analyze", json=REQUEST).json()
    assert actual == expected, (
        "API 回應與契約樣本不一致——契約已變動，請跑 "
        "scripts/gen_contract_sample.py 重產樣本，並確認前端跟著更新")


def test_symbol_is_restricted_to_ticker_shaped_input():
    """symbol 會被代入資料源 URL，不讓路徑片段之類的東西進去。"""
    for bad in ("../evil", "A/B", "", "TOOLONGSYMBOL"):
        r = _client().post("/api/analyze", json=dict(REQUEST, symbol=bad))
        assert r.status_code == 422, bad


def test_duplicate_strategies_are_analysed_once():
    r = _client().post("/api/analyze",
                       json=dict(REQUEST,
                                 strategies=["bull-call-spread"] * 3))
    assert r.status_code == 200
    assert len(r.json()["results"]) == 1
