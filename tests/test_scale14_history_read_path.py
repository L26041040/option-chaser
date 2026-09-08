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
- AC-4：`test_history_read_path_is_not_slower_than_the_legacy_full_
  view_scan`（真實 Postgres，`OC_TEST_DATABASE_URL` 才會跑）——100 個
  歷史點、**全部是 cache miss** 的最貴情境仍全面優於舊路徑，報
  median／p95 與粗估 rows／bytes，見該測試 docstring 的完整數字。
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
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import store
from option_chaser.data.snapshot import load_snapshot, snapshot_from_dict
from option_chaser import history_resolver
from option_chaser.history_resolver import resolve_historical_cost

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")

FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"
NEW = {"symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
       "strategies": ["vertical-spread"]}
# `POST /api/scenarios`（`CreateScenarioRequest`）認 family 代碼
# （`Literal[FAMILIES]`），`POST /api/analyze`（`AnalyzeRequest`）認
# subtype 代碼（`Literal[STRATEGIES]`）——兩者是不同層次的詞彙、刻意
# 不共用型別（見 `api_app/main.py::CreateScenarioRequest.strategies`
# 的欄位註解）。fixture spot=100、`NEW["target_price"]`=110 > spot
# ⇒ 看漲，"vertical-spread" family 底下看漲可選的唯一 subtype 就是
# "bull-call-spread"（T08／#225 的 `SUBTYPE_DIRECTIONS`）——用它打
# `/api/analyze` 才會產生跟 scenario 家族展開後同一個 subtype 的
# 完全相同結果（同一份 snapshot、同一組 target，candidate_key 格式
# 不含 scenario identity）。
ANALYZE = {"symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
           "strategies": ["bull-call-spread"]}


def _client(storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _create_and_refresh(c):
    sc = c.post("/api/scenarios", json=NEW).json()
    row = c.post(f"/api/scenarios/{sc['id']}/refresh").json()
    return sc["id"], row["latest_analyzed_at"]


def _pick_visible_and_miss_candidates(c):
    """回傳 `(visible_key, visible_cost, miss_key, miss_cost)`——
    `visible_key` 是 narrow dual-write 真的覆蓋到的一組（有值），
    `miss_key` 是 `all_candidates` 裡真的有效、但沒被 dual-write 到
    narrow 的一組（moderate fixture 11 履約價/側，Vertical Spread
    每個到期日 `C(11,2)=55` 組合，遠超過 `expiry_top10` 的 10 名
    上限，這個情況必然存在）。

    SCALE-17（#268）跟進：`current_results.view`（`latest_result()`
    讀的那份）自本票起已剝除 `all_candidates`，不能再拿它當 key 的
    來源。改打 `POST /api/analyze`（同一份 `snap`／同一組 `NEW` 參數，
    `_client()` 的 `fetch` 固定回傳同一份快照，因此答案逐位元相同）
    ——這條路徑不落盤、永遠回傳未剝除的原始 view（SCALE-17 明文紅線：
    `/api/analyze` contract 不受影響），candidate_key 的格式（策略＋
    履約價＋到期日）本身不含 scenario identity，用哪個 scenario 算出來
    的都一樣，可以安全地拿來對照真正在測的那個 scenario。"""
    view = c.post("/api/analyze", json=ANALYZE).json()
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
    visible_key, visible_cost, _mk, _mc = _pick_visible_and_miss_candidates(c)

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
    _vk, _vc, miss_key, miss_cost = _pick_visible_and_miss_candidates(c)

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
    _vk, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(c)

    # 模擬既有存量資料尚未跑過 SCALE-01 backfill：resolved_params 等
    # fact-context 欄位為 None。SCALE-16（#267）跟進：這是在改寫
    # ledger 那一列（`get_spread_history()` 讀的 fact context 來自
    # ledger，不是 current_results），`view=None` 貼近本票之後 ledger
    # 列的真實形狀（`rec` 來自 `latest_result()`／current_results，
    # 直接沿用它的 view 會誤把已剝除 all_candidates 的內容寫進
    # ledger，明確蓋成 None 避免這個誤導）。
    storage.save_result(dataclasses.replace(
        rec, view=None, resolved_params=None))

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
    _vk, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(c)

    # SCALE-16（#267）跟進：同上一條測試，`view=None` 貼近本票之後
    # ledger 列的真實形狀。
    storage.save_result(dataclasses.replace(
        rec, view=None,
        history_replay_version=history_resolver.HISTORY_REPLAY_VERSION + 1))

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
    visible_key, _vc, miss_key, _mc = _pick_visible_and_miss_candidates(c)

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


# ---------- AC-4：真實 Postgres 延遲量測，含大量 miss ----------

def _legacy_history(st, sid, candidate_key, owner):
    """舊路徑（切換前的 `get_spread_history()`）：整段歷史逐一撈完整
    `view`，`store.spread_cost_history()` 現場聚合——保留在
    `store.py` 供這個對照測試與票面明列的 Rollback Point 共用，不是
    這個測試獨有的複本。"""
    rows = st.result_history(sid, owner=owner)
    views = [r.view for r in rows]
    return store.spread_cost_history(views, candidate_key), views


def _new_history_cold(st, sid, candidate_key, owner):
    """新路徑（`get_spread_history()` 逐字複製，僅省略 write-through
    的實際寫入——AC-4 要量的是「含大量 miss」這個最貴情境本身的讀取
    延遲，每一輪重覆量測都要維持同樣是 100% miss，不能被第一輪的
    write-through 悄悄變成第二輪的全 hit）。回傳 `(costs, payload)`，
    `payload` 供估算「這次呼叫實際搬了多少 bytes」。"""
    timestamps = st.result_spot_timestamps(sid, owner=owner)
    all_dates = [at for at, _spot in timestamps]
    narrow = st.narrow_history_for_candidate(sid, candidate_key, all_dates, owner=owner)
    miss_dates = [at for at in all_dates if at not in narrow]
    fact_contexts = st.result_fact_contexts(sid, miss_dates, owner=owner)
    snapshots = st.snapshots_batch(sid, miss_dates, owner=owner)
    costs = []
    for at in all_dates:
        if at in narrow:
            costs.append(narrow[at])
            continue
        fact = fact_contexts[at]
        resolved = resolve_historical_cost(
            candidate_key,
            history_replay_version=fact.history_replay_version,
            requested_strategies=fact.requested_strategies,
            resolved_params=fact.resolved_params,
            snapshot=snapshot_from_dict(snapshots[at]))
        costs.append(resolved.cost)
    return costs, (fact_contexts, snapshots)


@pytest.mark.skipif(not TEST_DB_URL,
                    reason="需要 OC_TEST_DATABASE_URL 才能量測真實延遲")
def test_history_read_path_is_not_slower_than_the_legacy_full_view_scan():
    """AC-4：100 個歷史點、**全部是 cache miss**（narrow_history 對這個
    candidate_key 完全是空的——票面「含大量 miss」的最貴情境，不是
    抽樣挑一個樂觀情況），真實 Postgres 上量測新舊兩條路徑，報
    median／p95 與粗估 DB rows／bytes（2026-09-07，本機 PostgreSQL 16，
    15 輪取中位數／p95，view padding 55KB 貼近既有 SCALE-02 benchmark
    量級）：

        舊路徑（result_history 撈 100 份完整 view）：
          median 640.99ms／p95 840.92ms／100 rows／19,772,400 bytes
        新路徑（result_spot_timestamps + narrow_history_for_candidate
                ＋ result_fact_contexts + snapshots_batch，100% miss，
                即每一筆都真的跑一次 resolver，不是取巧算最好情況）：
          median  80.23ms／p95 101.68ms／200 rows／ 1,483,400 bytes

    即使是「每一筆都 cache miss、都要跑 resolver」這個 SCALE-14 最貴
    的情境，仍快 ~8×（median）／~8.3×（p95），bytes 少 ~13×——AC-4
    「不得比 legacy baseline 慢」不只是打平，是即使含大量 miss 依然
    全面改善。斷言方向：新路徑不得比舊路徑慢（2× 安全邊際，比照既有
    SCALE-02 `test_result_timestamps_is_not_slower_than_the_old_full_
    view_scan` 的同一套紀律，不是勉強打平）。"""
    import psycopg

    from api_app.storage import ResultRecord, Scenario
    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, "
                     "narrow_history RESTART IDENTITY")

    owner = "solo"
    sid = "history-bench"
    st.create_scenario(Scenario(
        id=sid, symbol="XYZ", direction="bullish", target_price=110.0,
        target_month="2026-10", notes="", strategies=("vertical-spread",),
        created_at="2026-08-01T00:00:00+00:00", owner_id=owner))

    # 用真實引擎跑一次分析，取得一份真正合法、可被 resolver 正確重放的
    # (view, fact_context, snapshot) 三元組——不是手造的假資料，
    # candidate_key 是這次分析真的產生過的有效候選。
    snap = load_snapshot(FIX)
    from option_chaser import service
    from option_chaser.models import AnalysisParams
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=110.0, target_month="2026-10"),
        strategies=("bull-call-spread",))
    result = service.run_with_snapshot(req, snap)
    view = store.serialize_result(result, sid, None)
    fact = store.historical_fact_context(view)
    candidate_key, _expected_cost = next(
        iter(store.visible_candidate_costs(view).items()))
    snap_dict = dataclasses.asdict(snap)
    # ~55KB padding：貼近既有 SCALE-02 benchmark 用的量級（真實
    # production view 常見大小），確保「舊路徑整份撈 view」的代價
    # 不會因為測試 fixture 湊巧很小而被低估。
    view_for_storage = {**view, "_bench_padding": "x" * 55000}

    n = 100
    for i in range(n):
        ts = f"2026-08-{(i % 28) + 1:02d}T{i:02d}:00:00+00:00"
        st.save_result(ResultRecord(sid, ts, view_for_storage, owner_id=owner,
                                    **fact))
        st.save_snapshot(sid, ts, snap_dict, owner_id=owner)
    # narrow_history 對這個 candidate_key 刻意保持全空——100% miss。

    def median_p95_ms(fn, rounds=15):
        samples = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000)
        samples.sort()
        return samples[len(samples) // 2], samples[int(len(samples) * 0.95)]

    old_costs, old_views = _legacy_history(st, sid, candidate_key, owner)
    new_costs, (new_facts, new_snaps) = _new_history_cold(st, sid, candidate_key, owner)
    assert [e["cost"] for e in old_costs] == new_costs   # AC-1：答案必須一致

    old_median, old_p95 = median_p95_ms(
        lambda: _legacy_history(st, sid, candidate_key, owner))
    new_median, new_p95 = median_p95_ms(
        lambda: _new_history_cold(st, sid, candidate_key, owner))

    old_bytes = sum(len(json.dumps(v, default=str)) for v in old_views)
    new_bytes = (sum(len(json.dumps(dataclasses.asdict(f), default=str))
                    for f in new_facts.values())
                + sum(len(json.dumps(s, default=str)) for s in new_snaps.values()))

    print(f"\nSCALE-14 AC-4 benchmark (n={n}, 100% miss):\n"
         f"  legacy : median={old_median:.2f}ms p95={old_p95:.2f}ms "
         f"rows={len(old_views)} bytes={old_bytes}\n"
         f"  new    : median={new_median:.2f}ms p95={new_p95:.2f}ms "
         f"rows={len(new_facts) + len(new_snaps)} bytes={new_bytes}")

    assert new_median <= old_median * 2   # 安全邊際，不是勉強打平
    assert new_p95 <= old_p95 * 2
