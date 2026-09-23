"""AUTH-05（#312，Anonymous Public Beta，三層角色模型 spec #307）：
Scenario quota 的 Super User／Super Admin 角色豁免。

**Global vendor fuse（PB-06／#299）明確不在本票豁免範圍內**——這是
本檔案最重要的一組測試（見「豁免不得波及 fuse」小節）：角色短路只
解除 per-owner 額度這一處使用者體驗類的既有限制，`_fetch_chain()`
內對三層角色一視同仁的全站每日 vendor 預算保險絲完全不受影響。

SW-10（#340，Owner 真機驗收）跟進：這個檔案原本還有一整組「refresh
throttle 豁免」測試——30 分鐘節流本身是 Owner 直接裁示整段移除的
產品層限制（見 `api_app/main.py::_refresh_and_save()` 檔頭說明），
角色對它的「豁免」這個概念因此也一併不存在了：現在不分角色、每次
呼叫刷新都會真的再抓一次。原本那組測試改寫成更簡單的「刷新永遠真的
再抓一次」regression 守門，其餘涉及 fuse 的測試移除節流窗設置後
保留（fuse 本身不受這輪改動影響）。

沿用既有 `tests/test_pb05_quota_and_throttle.py`／
`tests/test_pb06_global_vendor_fuse.py` 的 `_client()`／`_create()`
慣例，只多接上角色 cookie。
"""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app.clock import now_utc_iso, ny_today
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot
from tests._role_session import role_cookies

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
      "strategies": ["vertical-spread"]}


def _client(*, storage=None, owner="solo", role=None, fetch_calls=None,
           **overrides):
    storage = storage or MemoryStorage()
    base_snap = load_snapshot(FIX)

    def _fetch(symbol: str):
        if fetch_calls is not None:
            fetch_calls.append(symbol)
        # 既有 PB-05／PB-06 測試同一個理由：production 每次抓取都蓋成
        # 「現在」，固定 fixture 的歷史時間戳測不出節流窗是否生效。
        return dataclasses.replace(base_snap, fetched_at=now_utc_iso())

    cookies = role_cookies(storage, role) if role else None
    return TestClient(create_app(
        identity_resolver=lambda: owner, fetch=_fetch, storage=storage,
        **overrides),
        cookies=cookies)


def _create(client, **overrides):
    return client.post("/api/scenarios", json={**NEW, **overrides})


def _sym(i: int) -> str:
    """`_SYMBOL` 只准字母／`.`／`-`——既有測試踩過的坑。"""
    return "SY" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i]


def _seed_today_count(storage, count: int) -> None:
    if count <= 0:
        return
    storage.record_metric("chain_fetch_count", ny_today().isoformat(),
                          source="cboe", symbol="ANY", count=count)


def _client_with_metering(*, storage=None, owner="solo", role=None,
                          **overrides):
    """`_client()` 的 `fetch=` 是完整降級鏈的複合覆寫，結構上會完全
    繞過 `_metered_chain_fetch()`（`_effective_fetch = _default_fetch
    if fetch is service.fetch_chain else fetch`，見 `main.py` 該行
    註解）——`chain_fetch_count` 因此永遠不會被增加，多數既有測試
    （含 PB-05／PB-06）不在乎這件事，但「豁免而成功的動作仍正確計入
    既有 `operational_metrics`」這條 AC 恰好就是要驗證這個計數本身。
    改用 `cboe_fetch=`（不覆寫 `fetch`）——它只替換 `_default_fetch()`
    內部真正打 Cboe 的那一步，`_metered_chain_fetch()` 包裝原封不動，
    每次呼叫都會如實記一筆。"""
    storage = storage or MemoryStorage()
    base_snap = load_snapshot(FIX)

    def _cboe_fetch(symbol: str):
        return dataclasses.replace(base_snap, fetched_at=now_utc_iso())

    cookies = role_cookies(storage, role) if role else None
    return TestClient(create_app(
        identity_resolver=lambda: owner, cboe_fetch=_cboe_fetch,
        storage=storage, **overrides),
        cookies=cookies)


# ---------- Scenario quota 豁免 ----------

@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_the_eleventh_scenario_succeeds_for_an_exempt_role(role):
    storage = MemoryStorage()
    c = _client(storage=storage, role=role)
    for i in range(10):
        assert _create(c, symbol=_sym(i)).status_code == 201
    r = _create(c, symbol="SYX")
    assert r.status_code == 201


def test_normal_user_quota_behavior_is_unchanged_by_this_ticket():
    """AC：Normal User 的既有行為與 PB-05 上線後完全不變——同一批
    請求，沒有角色 cookie 時仍在第 11 筆被拒。"""
    storage = MemoryStorage()
    c = _client(storage=storage)  # 無角色 cookie ＝ Normal
    for i in range(10):
        assert _create(c, symbol=_sym(i)).status_code == 201
    r = _create(c, symbol="SYX")
    assert r.status_code != 500
    assert 400 <= r.status_code < 500
    assert "10" in r.json()["detail"]


def test_mixed_batch_normal_is_still_blocked_super_user_still_succeeds():
    """同一份 storage 裡，Normal 與豁免角色各自獨立跑滿自己的額度
    判斷——豁免只影響帶著角色 cookie 的那個請求本身，不會「借用」給
    別的 owner，也不影響 Normal User 這一側原本就會被擋下的事實。"""
    storage = MemoryStorage()
    normal = _client(storage=storage, owner="a-normal-owner")
    exempt = _client(storage=storage, owner="an-exempt-owner",
                     role="superuser")
    for i in range(10):
        assert _create(normal, symbol=_sym(i)).status_code == 201
        assert _create(exempt, symbol=_sym(i)).status_code == 201
    assert _create(normal, symbol="SYX").status_code >= 400
    assert _create(exempt, symbol="SYX").status_code == 201


# ---------- 刷新永遠真的再抓一次（節流整段移除後的 regression 守門）----------

@pytest.mark.parametrize("role", [None, "superuser", "superadmin"])
def test_refresh_always_fetches_again_regardless_of_role(role):
    """SW-10（#340，Owner 真機驗收）：節流整段移除後，不分角色，第二次
    呼叫刷新一律真的再抓一次——不再有「30 分鐘內沿用舊資料」這件事，
    也不再需要角色豁免這個概念（`role=None` 即無角色 cookie，等同
    Normal User）。"""
    storage = MemoryStorage()
    calls: list[str] = []
    c = _client(storage=storage, role=role, fetch_calls=calls)
    sid = _create(c).json()["id"]

    r1 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r1.status_code == 200
    assert len(calls) == 1

    r2 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r2.status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize("role", [None, "superuser", "superadmin"])
def test_refresh_run_also_always_fetches_again_regardless_of_role(role):
    """同一條規則同時涵蓋批次端點（`POST /api/scenarios/refresh-run`）
    ——不只是單劇本刷新那一條路徑。"""
    storage = MemoryStorage()
    calls: list[str] = []
    c = _client(storage=storage, role=role, fetch_calls=calls)
    sid = _create(c).json()["id"]

    c.post(f"/api/scenarios/{sid}/refresh")
    assert len(calls) == 1

    r = c.post("/api/scenarios/refresh-run", json={"scenario_ids": [sid]})
    assert r.status_code == 200
    body = r.json()
    assert body["results"] == [{"scenario_id": sid, "ok": True,
                                "row": body["results"][0]["row"]}]
    assert len(calls) == 2


# ---------- 角色豁免不得波及全站 vendor fuse（票面核心正面驗收） ----------

@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_exempt_role_refresh_is_still_blocked_by_a_tripped_fuse(role):
    """整張票最重要的一條：即使是 quota 豁免角色，全站每日 vendor
    預算已經用盡時（模擬「其他流量把預算燒光了」，沿用既有 PB-06
    測試的 `_seed_today_count()` 手法——`_client()` 的 `fetch=`
    覆寫繞過了 metering，不能依賴第一次刷新自然把預算用完，得直接
    灌值），`_fetch_chain()` 內的 fuse 一樣擋下它、非 500——證明本票
    的角色短路完全沒有波及 fuse 檢查本身。

    SW-10（#340）跟進：原本這裡還會先讓 scenario「處於節流窗內」才
    測 fuse——節流本身已經整段移除，fuse 現在對**每一次**刷新呼叫
    都無條件生效，不需要先製造一個節流窗場景才測得到。"""
    storage = MemoryStorage()
    c = _client(storage=storage, role=role, global_vendor_daily_budget=1)
    sid = _create(c).json()["id"]

    r1 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r1.status_code == 200
    first_analyzed_at = r1.json()["latest_analyzed_at"]

    _seed_today_count(storage, 1)  # 模擬預算在窗內被其他流量用盡

    r2 = c.post(f"/api/scenarios/{sid}/refresh")
    assert r2.status_code == 429
    assert r2.status_code < 500
    assert r2.json()["detail"]["stage"] == "vendor_budget_exhausted"

    # 被 fuse 擋下的失敗刷新不是靜默成功——劇本本身（若呼叫端另外查
    # 一次）仍看得到上一次成功的舊資料，不是被覆寫成空值或錯誤狀態。
    detail_view = c.get(f"/api/scenarios/{sid}").json()
    assert detail_view["latest_analyzed_at"] == first_analyzed_at


@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_exempt_role_cannot_create_an_eleventh_scenario_worth_of_extra_vendor_load_around_a_tripped_fuse(
        role):
    """額度豁免只解除「能不能建立這張劇本」——不代表被豁免角色建立的
    劇本在刷新時能繞過全站預算保險絲，兩件事互不相關，這裡用第 11 張
    劇本直接驗證。"""
    storage = MemoryStorage()
    _seed_today_count(storage, 10)
    c = _client(storage=storage, role=role, global_vendor_daily_budget=10)
    for i in range(10):
        assert _create(c, symbol=_sym(i)).status_code == 201
    r = _create(c, symbol="SYX")
    assert r.status_code == 201  # 額度本身確實豁免

    sid = r.json()["id"]
    refresh_resp = c.post(f"/api/scenarios/{sid}/refresh")
    assert refresh_resp.status_code == 429
    assert refresh_resp.json()["detail"]["stage"] == "vendor_budget_exhausted"


def test_normal_user_is_blocked_by_the_same_tripped_fuse_for_comparison():
    """對照組：Normal User 面對同一顆已觸發的 fuse，行為與豁免角色
    完全一致（本來就該一致——fuse 對三層角色一視同仁）。"""
    storage = MemoryStorage()
    _seed_today_count(storage, 10)
    c = _client(storage=storage, global_vendor_daily_budget=10)
    sid = _create(c).json()["id"]

    r = c.post(f"/api/scenarios/{sid}/refresh")
    assert r.status_code == 429
    assert r.json()["detail"]["stage"] == "vendor_budget_exhausted"


# ---------- 豁免而成功的動作仍計入既有 operational_metrics ----------

@pytest.mark.parametrize("role", ["superuser", "superadmin"])
def test_a_second_refresh_by_an_exempt_role_still_records_the_existing_metric(
        role):
    """AC：Super User／Super Admin 的刷新動作，仍正確計入既有
    `operational_metrics`。用 `_client_with_metering()`（見該函式
    docstring）而非一般的 `_client()`，否則 `fetch=` 覆寫會讓
    metering 整層被繞過、這條測試永遠量不出任何東西。

    SW-10（#340）跟進：原本這裡的敘事是「這次刷新本該被節流但因豁免
    而真的再抓一次」——節流整段移除後，第二次刷新本來就會真的再抓一次
    （不分角色），這裡只是確認這個動作仍然被既有指標記錄，不是節流
    豁免帶出的特殊行為。"""
    storage = MemoryStorage()
    c = _client_with_metering(storage=storage, role=role)
    sid = _create(c).json()["id"]

    c.post(f"/api/scenarios/{sid}/refresh")
    baseline = storage.metric_total("chain_fetch_count",
                                    ny_today().isoformat())
    assert baseline >= 1

    c.post(f"/api/scenarios/{sid}/refresh")
    after = storage.metric_total("chain_fetch_count", ny_today().isoformat())
    assert after == baseline + 1
