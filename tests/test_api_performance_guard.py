"""REPAIR-10（#247，FIX-08a，#052 audit）：production-scale 效能守門，
固化成永久 CI 斷言——把 #240（FIX-02）用來判定 FIX-03 走向的那次
production-equivalent re-profile，搬到**這個票要求的正確層級**：
`api_app/main.py::_refresh_and_save()`（`POST /api/scenarios/{id}/
refresh` 的核心，`refresh_scenario`／`refresh_run` 共用），不是只測
`option_chaser.service.run_offline()`。

`_refresh_and_save()` 比 `run_offline()` 多做的事（per-family 代表
候選走訪、`ResultRecord` 落盤前的欄位組裝）理論上可能貢獻額外 wall
time，本票要直接量到含這些額外工作的完整數字，不是外推 #240 的引擎
層數字。

**既有 `tests/test_butterfly_performance.py` 的兩個失真維度，判斷
維持現狀、不修改，理由記錄於此**（AC 明文允許的「保留舊測試作為
另一種情境」分支）：
1. `dividend_loader=None`（q 停用，IV solver 完全不觸發）——那份
   測試量的是 T15／#230 自己的 AC（純枚舉／純估值成本在合理範圍），
   刻意排除 carry 校準這個變因，不是量測整條 production 路徑；本票
   新增的測試才是「真實非零 q」那個情境。
2. fixture 規模只有 production 尺度的 1/17（26 履約價 vs 60）——
   `xyz_v6_butterfly_ladder.json` 的密度是刻意對齊 wayfinder 地圖
   #216 的枚舉估計（該文件明文引用的數字），改動它的規模會讓
   `test_butterfly_performance.py` 自己的 docstring 引註失真，且
   會讓那份測試從「T15 自己的驗收基準」變成「這張票的驗收基準」，
   混淆兩張票各自的證據歸屬。

兩份測試因此**並存、各自守住不同的情境**——不是重複覆蓋：
`test_butterfly_performance.py` 守「正常規模＋q 停用」（T15 AC）、
本檔案守「production-scale＋真實非零 q＋完整 HTTP 刷新路徑」
（REPAIR-03／REPAIR-10 AC）。
"""
import time
from datetime import date

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord

FIX = "tests/fixtures/xyz_v8_production_scale.json"
ACCEPTANCE_THRESHOLD_SECONDS = 20.0


def _offline_rate_loader(today):
    """比照全站既有慣例（例如 `test_strategy_family.py`）——利率不是
    本票要驗證的變因，維持既有 fallback 常數利率，決定性、零網路。"""
    return None, "test：離線重放，未啟用利率曲線"


def _real_dividend_loader(symbol, today):
    """AC「真實 dividend_loader（q≠0，不是 None）」——回傳一份真正的
    `DividendHistory`（非空 distributions），讓 `_resolve_q()` 算出
    非零 `q_by_symbol`，`calibrate_leg()` 因此真的走 IV 反解分支，
    不是退回今天的 fallback 短路。"""
    history = DividendHistory(
        symbol=symbol, as_of="2026-07-14", source="yahoo", stale=False,
        distributions=(DividendRecord("2026-06-01", 3.5),))
    return history, "配息資料 yahoo（2026-07-14，1 筆，效能守門測試用固定值）"


def _client():
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=MemoryStorage(),
                                 rate_loader=_offline_rate_loader,
                                 dividend_loader=_real_dividend_loader))


def test_refresh_endpoint_completes_within_twenty_seconds_at_production_scale():
    """AC 本體：單一劇本三個 family 全開的完整 `POST /api/scenarios/
    {id}/refresh`（即 `_refresh_and_save()` 的 HTTP 入口），在
    production-scale 規模（5 到期日×60 履約價/側，600 張合約）＋
    真實非零 q 下，wall-clock 必須 ≤ 20 秒。

    走 `MemoryStorage`（不是真實 Postgres）——這條測試要隔離的是
    CPU-bound 的估值成本本身，不是資料庫 I/O 延遲；後者是另一個獨立
    的效能維度，混在同一個門檻裡會讓這條測試在慢速資料庫連線下誤紅，
    也會讓「超過 20 秒到底是估值算太久還是資料庫連太慢」變得無法
    分辨。"""
    client = _client()
    created = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-09",
        "strategies": ["single-leg", "vertical-spread", "butterfly"]})
    assert created.status_code == 201, created.text
    sc_id = created.json()["id"]

    t0 = time.perf_counter()
    r = client.post(f"/api/scenarios/{sc_id}/refresh")
    elapsed = time.perf_counter() - t0

    assert r.status_code == 200, r.text
    row = r.json()
    print(f"\n[REPAIR-10 效能守門] POST /refresh 耗時 {elapsed:.3f}s "
         f"（門檻 {ACCEPTANCE_THRESHOLD_SECONDS}s）")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS, (
        f"POST /api/scenarios/{{id}}/refresh 在 production-scale 規模下"
        f"耗時 {elapsed:.3f}s，超過 20 秒 acceptance threshold")

    # 確認這條測試真的測到重點：三個 family 都真的分析成功，不是
    # 因為某個環節提早失敗才「碰巧」跑得快。
    detail = client.get(f"/api/scenarios/{sc_id}").json()
    assert detail["representative_candidate"] is not None
    assert row["representative_candidate"] is not None


def test_refresh_endpoint_stays_fast_on_a_second_run_as_a_stability_check():
    """AC「新增的效能守門測試本身穩定（非 flaky，建議跑兩輪確認）」
    ——用一個獨立的第二次量測（不同 TestClient／不同劇本 id，避免
    任何跨呼叫狀態殘留）而非重跑同一個 pytest 檔案兩次，把「穩定性
    確認」直接寫成第二條測試，CI 每次跑都驗一次，不依賴人工重跑。"""
    client = _client()
    created = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-09",
        "strategies": ["single-leg", "vertical-spread", "butterfly"]})
    sc_id = created.json()["id"]

    t0 = time.perf_counter()
    r = client.post(f"/api/scenarios/{sc_id}/refresh")
    elapsed = time.perf_counter() - t0

    assert r.status_code == 200, r.text
    print(f"\n[REPAIR-10 效能守門／第二輪] 耗時 {elapsed:.3f}s")
    assert elapsed < ACCEPTANCE_THRESHOLD_SECONDS
