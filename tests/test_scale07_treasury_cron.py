"""SCALE-07（#257，Scaling Foundation Treasury Cron ＋ 保留既有同步
refresh-on-miss fallback）：`GET /api/cron/warm-rate-cache`。

## AC 對照

- AC-1：`test_a_correctly_authorized_cron_hit_warms_the_cache_for_
  subsequent_normal_analysis`
- AC-2：`test_missing_secret_is_401_and_touches_nothing`／
  `test_wrong_secret_is_401_and_touches_nothing`
- AC-3：`test_two_cron_hits_on_the_same_day_are_idempotent`
- AC-4：`test_sync_fallback_still_works_when_cron_never_ran`
- AC-5：`test_vendor_failure_does_not_fake_a_fresh_market_day`
- AC-6：`test_no_background_continuation_or_waitunlt_dependency`
- AC-7：全套既有測試套件本身
"""
import dataclasses
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from option_chaser.ratecurve import RateCurve

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}
AUTH = {"Authorization": "Bearer test-secret"}


def _fresh_snapshot():
    """`_analyze()` 的 `today` 完全由快照自己的 `fetched_at` 決定（F4，
    不吃 wall clock），跟 cron 端點用的 `ny_today()`（真的讀系統時鐘）
    是兩條獨立的『今天』來源——production 環境下兩者恆一致（真實抓到
    的快照 `fetched_at` 就是抓取當下），但既有 fixture 的 `fetched_at`
    是寫死的舊日期。這裡把它蓋成「現在」，讓兩條今天的來源在測試裡
    真正對齊，才對得起 AC-1『warms it for subsequent normal use』。"""
    snap = load_snapshot(FIX)
    return dataclasses.replace(
        snap, fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _client(*, cron_secret="test-secret", rate_loader=None, storage=None):
    snap = _fresh_snapshot()
    kwargs = {}
    if rate_loader is not None:
        kwargs["rate_loader"] = rate_loader
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage(),
                                 cron_secret=cron_secret, **kwargs))


def _counting_loader(curve: RateCurve | None = None, note: str = "ok"):
    calls: list[date] = []

    def loader(today: date):
        calls.append(today)
        return (curve if curve is not None
                else RateCurve(curve_date=today.isoformat(),
                              nodes=((1.0, 0.04),)),
               note)

    loader.calls = calls
    return loader


def test_a_correctly_authorized_cron_hit_warms_the_cache_for_subsequent_normal_analysis():
    """AC-1：正確 Bearer secret 的 GET cron invocation 讓 rate_cache
    命中，之後正常 analysis 不再 cold-fetch（`rate_loader` 只被真正
    的 underlying 呼叫一次，即使後面又跑了一次分析）。"""
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(rate_loader=loader, storage=storage)

    r = c.get("/api/cron/warm-rate-cache", headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert len(loader.calls) == 1

    entry = storage.get_rate_cache()
    assert entry is not None
    assert entry.curve is not None

    # 正常 analysis 路徑（建立劇本→刷新）應該直接命中剛剛暖好的快取，
    # 不再呼叫底層 `rate_loader`。
    r2 = c.post("/api/scenarios", json=NEW)
    sid = r2.json()["id"]
    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(loader.calls) == 1   # 沒有變成 2


def test_missing_secret_is_401_and_touches_nothing():
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(rate_loader=loader, storage=storage)

    r = c.get("/api/cron/warm-rate-cache")   # 沒帶 Authorization
    assert r.status_code == 401
    assert loader.calls == []
    assert storage.get_rate_cache() is None


def test_wrong_secret_is_401_and_touches_nothing():
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(rate_loader=loader, storage=storage)

    r = c.get("/api/cron/warm-rate-cache",
              headers={"Authorization": "Bearer not-the-secret"})
    assert r.status_code == 401
    assert loader.calls == []
    assert storage.get_rate_cache() is None


def test_cron_secret_not_configured_fails_closed_even_with_a_plausible_header():
    """`cron_secret=None`（模擬 production 環境變數也沒設）——不管
    Authorization 帶什麼都一律 401，不會因為「反正沒設就放行」而變成
    一個形同虛設的驗證。"""
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(cron_secret=None, rate_loader=loader, storage=storage)

    r = c.get("/api/cron/warm-rate-cache",
              headers={"Authorization": "Bearer Anything"})
    assert r.status_code == 401
    assert loader.calls == []


def test_two_cron_hits_on_the_same_day_are_idempotent():
    """AC-3：同日連打兩次，第二次不重複造成昂貴 fetch——直接複用
    `cached_loader()` 既有的 `market_day` 判準，不新寫一套 idempotency
    邏輯。"""
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(rate_loader=loader, storage=storage)

    c.get("/api/cron/warm-rate-cache", headers=AUTH)
    c.get("/api/cron/warm-rate-cache", headers=AUTH)
    assert len(loader.calls) == 1


def test_sync_fallback_still_works_when_cron_never_ran():
    """AC-4：刻意不跑 cron，當天第一個正常 analysis 仍可透過既有同步
    fallback 完成——cron 端點存在與否，不影響既有的 refresh-on-miss
    路徑。"""
    storage = MemoryStorage()
    loader = _counting_loader()
    c = _client(rate_loader=loader, storage=storage)   # 從未打 cron

    r = c.post("/api/scenarios", json=NEW)
    sid = r.json()["id"]
    refresh = c.post(f"/api/scenarios/{sid}/refresh")
    assert refresh.status_code == 200, refresh.text
    assert len(loader.calls) == 1   # 同步 fallback 自己觸發了一次抓取


def test_vendor_failure_does_not_fake_a_fresh_market_day():
    """AC-5：vendor 失敗（或非交易日尚未發布）時，`ok` 誠實回 False，
    且不偽造成功的 `market_day`——下一次呼叫（不論是 cron 或正常
    analysis）仍會真的重試，不會被一筆假新鮮的快取擋住。"""
    storage = MemoryStorage()

    def failing_loader(today: date):
        return None, "Treasury 尚未發布今天的資料"

    c = _client(rate_loader=failing_loader, storage=storage)

    r = c.get("/api/cron/warm-rate-cache", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is False

    entry = storage.get_rate_cache()
    assert entry is not None
    assert entry.curve is None
    assert entry.market_day is None   # 沒有被偽造成「今天已經新鮮」


def test_no_background_continuation_or_waitunlt_dependency():
    """AC-6：本票新增的程式碼結構上不引入 Python background
    continuation／waitUntil 類依賴——純同步函式，沒有 async 背景任務、
    沒有對 `waitUntil` 之類 API 的引用。"""
    import ast
    import inspect

    from api_app import main as main_module

    source = inspect.getsource(main_module)
    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "waitUntil" not in names | attrs
    assert "create_task" not in names | attrs
    assert "ensure_future" not in names | attrs
    # `cron_warm_rate_cache` 本身是普通同步函式（非 `async def`）。
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cron_warm_rate_cache":
            found = True
            break
    else:
        found = False
    assert found, "找不到 cron_warm_rate_cache——結構性斷言本身失效"
