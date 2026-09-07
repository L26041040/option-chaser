"""SCALE-14（#265，Scaling Foundation Stage 1-3）：`GET /history` 切換
成 canonical read semantics——narrow hit／negative-cache gap／cache
miss（write-through）三態，不再整份讀取 `results.view`（AC-5）。

## 對照 AC

- AC-1：`tests/test_scale12_parity_proof.py` 已對 narrow＋resolver 本身
  做過 production-scale 全面 A/B，本檔案不重複；這裡驗證的是**接上
  HTTP 端點之後**三條分支各自的行為與 write-through 副作用。
- AC-2：`test_cache_miss_resolves_and_writes_through` 的第二次呼叫
  poison resolver，證明命中 narrow 後不再重付 replay 成本。
- AC-3：negative gap 也 write-through，第二次不重跑 resolver
  （`test_negative_cache_gap_never_recalls_the_resolver`）。
- AC-5：`tests/test_api_scenarios.py::test_api_layer_never_touches_
  sql_directly` 既有結構性掃描已涵蓋 `main.py` 不含 SQL 關鍵字；本檔案
  額外用 poison 手法直接證明**這條端點本身**在 hit／gap 分支不會呼叫
  resolver（資料庫層面是否整份讀 view 已由 Storage 實作與其契約測試
  把關，不在本檔案重複驗證）。
- AC-6：既有 `tests/test_api_history.py` 的 5 條測試（斷點語意／404／
  空歷史／唯讀／不存在的 key）全數保持原樣通過（`git diff` 確認零
  修改），證明 canonical read path 對既有 HTTP 契約逐位元相容。
- AC-7：`test_ac7_missing_fact_context_is_a_gap_that_is_not_cached`／
  `test_ac7_version_mismatch_is_a_gap_that_is_cached` 對照兩種
  「resolver 拒絕判定」的原因，證明只有真正穩定的事實（version
  mismatch）才 write-through，尚待 backfill 的暫時性缺口不會被永久
  錯誤快取（設計裁決見 `Storage.result_fact_contexts()` 附近的
  docstring 與 `main.py::get_spread_history()` 本身的說明）。

契約：`baseline_return`／`rank_in_expiry` 恆為 `null`——Audit 已證實
前端零消費者，鎖定測試見
`tests/test_frontend_contract.py`（若該檔案已涵蓋則不重複）與本檔案
`test_baseline_return_and_rank_in_expiry_are_always_null`。
"""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import store
from option_chaser.data.snapshot import load_snapshot
from option_chaser import history_resolver

FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"
NEW = {"symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
       "strategies": ["vertical-spread"]}


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _create_and_refresh(c):
    sc = c.post("/api/scenarios", json=NEW).json()
    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()
    return sc["id"], row["latest_analyzed_at"]


def _pick_visible_and_miss_candidates(view):
    """回傳 `(visible_key, visible_cost, miss_key, miss_cost)`——
    `visible_key` 是 narrow dual-write 真的覆蓋到的一組（有值），
    `miss_key` 是 `all_candidates` 裡真的有效、但沒被 dual-write 到
    narrow 的一組（moderate fixture 11 履約價/側，Vertical Spread
    每個到期日 `C(11,2)=55` 組合，遠超過 `expiry_top10` 的 10 名
    上限，這個情況必然存在）。"""
    visible = store.visible_candidate_costs(view)
    assert visible, "fixture 沒有任何 visible candidate，測試前提不成立"
    visible_key, visible_cost = next(iter(visible.items()))
    for r in view["results"]:
        for entry in r.get("all_candidates", []):
            if entry["candidate_key"] not in visible:
                return visible_key, visible_cost, entry["candidate_key"], entry["cost"]
    raise AssertionError("fixture 找不到任何 valid-but-not-visible 候選，"
                         "AC-4 對照組的測試前提不成立")


def _poisoned_resolver(monkeypatch):
    """把 `main.py` 實際呼叫的 `resolve_historical_cost` 換成一顆地雷
    ——narrow hit／negative-cache gap 分支結構上不該碰到它，呼叫到就
    直接讓測試炸掉，比事後翻閱程式碼更直接。"""
    def _boom(*args, **kwargs):
        raise AssertionError("resolve_historical_cost() 不該在這個分支被呼叫")
    monkeypatch.setattr("api_app.main.resolve_historical_cost", _boom)


def test_narrow_hit_never_calls_the_resolver(monkeypatch):
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    rec = storage.latest_result(sc_id, owner="solo")
    visible_key, visible_cost, _mk, _mc = _pick_visible_and_miss_candidates(rec.view)

    _poisoned_resolver(monkeypatch)
    r = c.get(f"/api/scenarios/{sc_id}/history",
             params={"candidate_key": visible_key})
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["cost"] == visible_cost
    assert entries[0]["analyzed_at"] == analyzed_at


def test_negative_cache_gap_never_recalls_the_resolver(monkeypatch):
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    # 直接寫入一筆 negative cache（模擬「上次呼叫已經跑過 resolver、
    # 判定 genuine gap」的既有狀態）——不透過 HTTP，本測試只關心第二次
    # 讀取是否真的不再重跑 resolver。
    from api_app.storage import NarrowHistoryEntry
    storage.save_narrow_history([NarrowHistoryEntry(
        scenario_id=sc_id, analyzed_at=analyzed_at,
        candidate_key="bull-call-spread|9999|10000|2099-01-01",
        cost=None, owner_id="solo")])

    _poisoned_resolver(monkeypatch)
    r = c.get(f"/api/scenarios/{sc_id}/history",
             params={"candidate_key": "bull-call-spread|9999|10000|2099-01-01"})
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["cost"] is None


def test_cache_miss_resolves_and_writes_through(monkeypatch):
    """AC-2／AC-3／AC-4 的正面證明：第一次呼叫是真正的 cache miss，
    resolver 算出正確值並落盤；第二次呼叫（resolver 已被拆彈）改為
    narrow hit，不再重付 replay 成本，且答案不變。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    rec = storage.latest_result(sc_id, owner="solo")
    _vk, _vc, miss_key, miss_cost = _pick_visible_and_miss_candidates(rec.view)

    assert storage.get_narrow_history_entry(
        sc_id, analyzed_at, miss_key, owner="solo") is None   # 前提：真的還沒 materialize

    r1 = c.get(f"/api/scenarios/{sc_id}/history",
              params={"candidate_key": miss_key})
    assert r1.status_code == 200
    entries1 = r1.json()["entries"]
    assert len(entries1) == 1
    assert entries1[0]["cost"] == miss_cost

    written = storage.get_narrow_history_entry(
        sc_id, analyzed_at, miss_key, owner="solo")
    assert written is not None, "resolver 判定的結果沒有 write-through 落盤"
    assert written.cost == miss_cost

    _poisoned_resolver(monkeypatch)
    r2 = c.get(f"/api/scenarios/{sc_id}/history",
              params={"candidate_key": miss_key})
    assert r2.status_code == 200
    assert r2.json()["entries"][0]["cost"] == miss_cost


def test_ac7_missing_fact_context_is_a_gap_that_is_not_cached():
    """AC-7：`resolved_params` 尚未 backfill（既有存量資料的既有狀態）
    時必須誠實回 gap，不猜測；且**不 write-through**——這個缺口是
    「metadata 還沒補齊」而非「resolver 判定過的穩定事實」，日後補齊
    後應該還有機會重新正確判定，不能被這一次的 `None` 永久卡死。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    rec = storage.latest_result(sc_id, owner="solo")
    _vk, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(rec.view)

    # 模擬既有存量資料尚未跑過 SCALE-01 backfill：resolved_params 等
    # fact-context 欄位為 None。
    storage.save_result(dataclasses.replace(rec, resolved_params=None))

    r = c.get(f"/api/scenarios/{sc_id}/history",
             params={"candidate_key": miss_key})
    assert r.status_code == 200
    assert r.json()["entries"][0]["cost"] is None

    assert storage.get_narrow_history_entry(
        sc_id, analyzed_at, miss_key, owner="solo") is None, (
        "missing_fact_context 不該被 write-through 成永久 negative cache")


def test_ac7_version_mismatch_is_a_gap_that_is_cached():
    """對照組：`history_replay_version` 不支援是那一天資料本身的穩定
    事實（除非重新整份分析，否則不會自己改變），與上一條測試刻意
    相反——這種 gap **應該** write-through，不必每次都重新判定一次。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    rec = storage.latest_result(sc_id, owner="solo")
    _vk, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(rec.view)

    storage.save_result(dataclasses.replace(
        rec, history_replay_version=history_resolver.HISTORY_REPLAY_VERSION + 1))

    r = c.get(f"/api/scenarios/{sc_id}/history",
             params={"candidate_key": miss_key})
    assert r.status_code == 200
    assert r.json()["entries"][0]["cost"] is None

    written = storage.get_narrow_history_entry(
        sc_id, analyzed_at, miss_key, owner="solo")
    assert written is not None, "version_mismatch 是穩定事實，應該 write-through"
    assert written.cost is None


def test_baseline_return_and_rank_in_expiry_are_always_null():
    """契約：兩個既有欄位保留為 nullable placeholder，新 canonical path
    不重算——不論 hit 或 miss 分支皆同。"""
    storage = MemoryStorage()
    c = _client(storage)
    sc_id, analyzed_at = _create_and_refresh(c)
    rec = storage.latest_result(sc_id, owner="solo")
    visible_key, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(rec.view)

    for key in (visible_key, miss_key):
        r = c.get(f"/api/scenarios/{sc_id}/history", params={"candidate_key": key})
        entry = r.json()["entries"][0]
        assert entry["baseline_return"] is None
        assert entry["rank_in_expiry"] is None


def test_frontend_never_reads_history_baseline_return_or_rank_in_expiry():
    """結構性鎖定（`/code-review` 沿用既有 AST/文字掃描慣例）：
    `HistoryEntry.baseline_return`／`.rank_in_expiry` 只在
    `src/api.ts` 的型別宣告與測試 fixture 出現，`src/spreadHistory.ts`
    （唯一消費端）不得讀取這兩個欄位——防止未來有人把它們拿去做
    功能，違反 AC「新 canonical history path 可回 null，但必須有
    contract test 鎖定、不得被前端拿來做功能」。"""
    src = open("src/spreadHistory.ts", encoding="utf-8").read()
    assert ".baseline_return" not in src
    assert ".rank_in_expiry" not in src
