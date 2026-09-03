"""REPAIR-10（#247，FIX-08a，#052 audit）：production-scale 效能守門，
固化成永久 CI 斷言——把 #240（FIX-02）用來判定 FIX-03 走向的那次
production-equivalent re-profile，搬到**這個票要求的正確層級**：
`api_app/main.py::_refresh_and_save()`（`POST /api/scenarios/{id}/
refresh` 的核心，`refresh_scenario`／`refresh_run` 共用），不是只測
`option_chaser.service.run_offline()`。

`_refresh_and_save()` 比 `run_offline()` 多做的事（per-family 代表
候選走訪、`ResultRecord` 落盤前的欄位組裝）理論上可能貢獻額外 wall
time，本票要直接量到含這些額外工作的完整數字，不是外推 #240 的引擎
層數字——**兩份測試共用同一套 production-scale fixture／真實 q／
20 秒門檻**（`tests/_production_scale_fixtures.py`，`/code-review`
Spec 軸抓到的真發現：原本兩邊各自複製一份，容易悄悄漂移成兩份不再
測同一件事的「production-scale 基準」），真正的差異只在**測哪一層**
——`tests/test_repair03_performance.py` 測引擎層 `run_offline()`，
本檔案測 HTTP／storage 層 `_refresh_and_save()`。

**既有 `tests/test_butterfly_performance.py` 的兩個失真維度，判斷
維持現狀、不修改，理由記錄於此**（AC 明文允許的「保留舊測試作為
另一種情境」分支）：
1. `dividend_loader=None`（q 停用，IV solver 完全不觸發）——那份
   測試量的是 T15／#230 自己的 AC（純枚舉／純估值成本在合理範圍），
   刻意排除 carry 校準這個變因，量的是「即使不校準也要夠快」這個
   獨立情境，不是量整條 production 路徑。
2. fixture 規模只有 production 尺度的 1/17（26 履約價 vs 60）——
   `xyz_v6_butterfly_ladder.json` 的密度是刻意對齊 wayfinder 地圖
   #216 的枚舉估計（該文件明文引用的數字），改動它的規模會讓
   `test_butterfly_performance.py` 自己的 docstring 引註失真，且
   會讓那份測試從「T15 自己的驗收基準」變成「這張票的驗收基準」，
   混淆兩張票各自的證據歸屬。

三份測試因此**並存、各自守住不同的情境**——不是重複覆蓋：
`test_butterfly_performance.py` 守「正常規模＋q 停用」（T15 AC）、
`test_repair03_performance.py` 守「production-scale＋真實非零 q＋
引擎層」（REPAIR-03 AC）、本檔案守「production-scale＋真實非零 q＋
完整 HTTP 刷新路徑」（REPAIR-10 AC）。
"""
import time

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from tests._production_scale_fixtures import (
    ACCEPTANCE_THRESHOLD_SECONDS, PRODUCTION_SCALE_FIXTURE as FIX,
    offline_rate_loader, real_dividend_loader)

# bullish 目標下真正跑完整估值的三個 subtype（另外三個是既有方向閘門
# `skipped_direction`，結構上不會走到昂貴計算，見下方測試的專屬斷言）。
_OK_SUBTYPES = ("long-call", "bull-call-spread", "call-fly")
_SKIPPED_SUBTYPES = ("long-put", "bear-put-spread", "put-fly")


def _client():
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=MemoryStorage(),
                                 rate_loader=offline_rate_loader,
                                 dividend_loader=real_dividend_loader))


def _create_production_scale_scenario(client):
    r = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-09",
        "strategies": ["single-leg", "vertical-spread", "butterfly"]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _assert_all_three_families_genuinely_succeeded(client, sc_id):
    """`/code-review` Spec 軸抓到的真缺口：先前的版本只檢查
    `representative_candidate is not None`（跨 family 冠軍），這個
    欄位即使兩個 family 全部失敗、只剩一個成功，一樣會是非 None——
    沒有真的證明「三個 family 都成功」，也沒有證明 IV 反解真的被
    觸發（`representative_candidate` 不含 `carry_calibrated`）。

    改為直接讀 `GET /api/scenarios/{id}` 的 `latest_result.results[]`
    （逐 subtype 的 `status`）＋`candidate_pool`（`store.
    project_for_detail()` 保留的候選池，`carry_calibrated` 欄位在
    這裡）——`results[].candidates` 本身是 T13／#231 刻意投影掉的
    欄位（`project_for_detail()` 明文移除，前端從未消費），因此不能
    拿它判斷成功與否，要看 `status` 與 `expiry_best`／`expiry_top10`
    引用到的 `candidate_pool` 條目。"""
    detail = client.get(f"/api/scenarios/{sc_id}").json()
    lr = detail["latest_result"]
    by_strategy = {r["strategy"]: r for r in lr["results"]}

    for subtype in _OK_SUBTYPES:
        assert by_strategy[subtype]["status"] == "ok", (
            f"{subtype} 應該真的分析成功，實際是 "
            f"{by_strategy[subtype]['status']}")
    for subtype in _SKIPPED_SUBTYPES:
        assert by_strategy[subtype]["status"] == "skipped_direction"

    # 確認至少一個 family 的候選真的走了 IV 反解分支（q 非零、有候選
    # 校準成功）——不是意外 fallback 短路讓這條測試表面通過。
    pool = lr["candidate_pool"]
    calibrated_seen = False
    for subtype in _OK_SUBTYPES:
        exp_best = by_strategy[subtype].get("expiry_best") or ()
        for key in exp_best:
            if pool[key]["carry_calibrated"]:
                calibrated_seen = True
    assert calibrated_seen, (
        "三個成功的 family 裡沒有任何候選 carry_calibrated=True——"
        "代表真實 q≠0 的 dividend_loader 沒有真的觸發 IV 反解分支")


def test_refresh_endpoint_completes_within_twenty_seconds_at_production_scale():
    """AC 本體：單一劇本三個 family 全開的完整 `POST /api/scenarios/
    {id}/refresh`（即 `_refresh_and_save()` 的 HTTP 入口），在
    production-scale 規模（5 到期日×60 履約價/側，600 張合約）＋
    真實非零 q 下，wall-clock 必須 ≤ 20 秒。

    走 `MemoryStorage`（不是真實 Postgres）——這條測試要隔離的是
    CPU-bound 的估值成本本身，不是資料庫 I/O 延遲；後者是另一個獨立
    的效能維度，混在同一個門檻裡會讓這條測試在慢速資料庫連線下誤紅，
    也會讓「超過 20 秒到底是估值算太久還是資料庫連太慢」變得無法
    分辨。AC 的「全套後端測試（記憶體＋真實 Postgres）綠燈」由完整
    測試套件的既有雙後端跑法涵蓋（本檔案不是那句話要驗證的對象，
    那句話驗證的是**整套**測試不因本票的改動而回歸，本票沒有動任何
    production code、不影響 Postgres adapter）。"""
    client = _client()
    sc_id = _create_production_scale_scenario(client)

    t0 = time.perf_counter()
    r = client.post(f"/api/scenarios/{sc_id}/refresh")
    elapsed = time.perf_counter() - t0

    assert r.status_code == 200, r.text
    print(f"\n[REPAIR-10 效能守門] POST /refresh 耗時 {elapsed:.3f}s "
         f"（門檻 {ACCEPTANCE_THRESHOLD_SECONDS}s）")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS, (
        f"POST /api/scenarios/{{id}}/refresh 在 production-scale 規模下"
        f"耗時 {elapsed:.3f}s，超過 20 秒 acceptance threshold")

    _assert_all_three_families_genuinely_succeeded(client, sc_id)


def test_refresh_endpoint_stays_fast_on_a_second_run_as_a_stability_check():
    """AC「新增的效能守門測試本身穩定（非 flaky，建議跑兩輪確認）」
    ——用一個獨立的第二次量測（不同 TestClient／不同劇本 id，避免
    任何跨呼叫狀態殘留）而非重跑同一個 pytest 檔案兩次，把「穩定性
    確認」直接寫成第二條測試，CI 每次跑都驗一次，不依賴人工重跑。"""
    client = _client()
    sc_id = _create_production_scale_scenario(client)

    t0 = time.perf_counter()
    r = client.post(f"/api/scenarios/{sc_id}/refresh")
    elapsed = time.perf_counter() - t0

    assert r.status_code == 200, r.text
    print(f"\n[REPAIR-10 效能守門／第二輪] 耗時 {elapsed:.3f}s")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS

    _assert_all_three_families_genuinely_succeeded(client, sc_id)
