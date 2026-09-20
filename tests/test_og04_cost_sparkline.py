"""OG-04（#323）：劇本清單「淨成本走勢」sparkline 欄。

契約：`Storage.cost_sparklines()` 本身的多後端行為由
`tests/test_storage_contract.py` 覆蓋（跟既有 `narrow_history_for_
candidate()` 同一份紀律）；這個檔案專門驗證票面另外兩條 AC——

- 清單回傳的 sparkline 序列與既有 `/history` 端點對同一 candidate_key
  的序列逐點一致（截尾後）。
- 100 列的真實 Postgres 延遲有守門斷言（批次查詢不得退化成 N+1）。
"""
from __future__ import annotations

import dataclasses
import os
import time

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
NEW = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
       "strategies": ["vertical-spread"]}


def _client(fetch, storage=None):
    return TestClient(create_app(identity_resolver=lambda: "solo", fetch=fetch,
                                 storage=storage or MemoryStorage()))


def _create(client, **overrides):
    r = client.post("/api/scenarios", json={**NEW, **overrides})
    assert r.status_code == 201, r.text
    return r.json()


def test_list_sparkline_matches_the_history_endpoint_for_the_same_candidate():
    """兩次刷新（不同快照，價位小幅變動避免冠軍換人）之後，清單列的
    `cost_sparkline` 必須跟 `/history?candidate_key=<冠軍 key>` 回來的
    序列逐點一致——同一份 narrow history，只是清單頁截尾成最近幾筆。
    截尾方向必須是「留最新的那幾筆」，不是任意一段。"""
    base = load_snapshot(FIX)
    snaps = [base, dataclasses.replace(
        base, fetched_at="2026-07-15T21:45:00-04:00", spot=base.spot * 1.01)]
    calls = {"n": 0}

    def fetch(symbol):
        snap = snaps[min(calls["n"], len(snaps) - 1)]
        calls["n"] += 1
        return snap

    client = _client(fetch)
    sc = _create(client)
    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()
    client.post(f"/api/scenarios/{sc['id']}/refresh").raise_for_status()

    row = client.get("/api/scenarios").json()[0]
    key = row["representative_candidate"]["candidate_key"]
    history = client.get(
        f"/api/scenarios/{sc['id']}/history?candidate_key={key}").json()

    expected = [[e["analyzed_at"], e["cost"]] for e in history["entries"]]
    assert row["cost_sparkline"] == expected


def test_list_sparkline_is_null_when_scenario_never_analyzed():
    client = _client(lambda symbol: load_snapshot(FIX))
    sc = _create(client)
    row = client.get("/api/scenarios").json()[0]
    assert row["cost_sparkline"] is None
    assert row["representative_candidate"] is None


@pytest.mark.skipif(not TEST_DB_URL,
                    reason="需要 OC_TEST_DATABASE_URL 才能量測真實延遲")
def test_cost_sparklines_batch_of_100_is_not_slower_than_naive_n_plus_1():
    """AC「清單端點的效能不得退化成 N+1」：100 個 (scenario_id,
    candidate_key) 配對，比較批次查詢（一次往返）與逐一查詢（100 次
    往返，模擬沒做這個優化的樸素寫法）——批次版本必須明顯更快，不只是
    打平（2× 安全邊際，比照既有 SCALE-02／SCALE-14 benchmark 同一套
    紀律）。逐一查詢用既有 `narrow_history_for_candidate()`（傳入這個
    候選在資料庫裡唯一的那個 `analyzed_at`）模擬「如果沒有批次方法，
    清單端點得怎麼做」，不是憑空捏造一個更慢的比較對象。"""
    import psycopg

    from api_app.storage import NarrowHistoryEntry, Scenario
    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, narrow_history RESTART IDENTITY")

    owner = "solo"
    n = 100
    pairs = [(f"s{i}", f"k{i}") for i in range(n)]
    for i, (sid, key) in enumerate(pairs):
        st.create_scenario(Scenario(
            id=sid, symbol="XYZ", direction="bullish", target_price=110.0,
            target_month="2026-10", notes="", strategies=("vertical-spread",),
            created_at="2026-08-01T00:00:00+00:00", owner_id=owner))
        st.save_narrow_history([NarrowHistoryEntry(
            scenario_id=sid, analyzed_at="2026-08-01T00:00:00+00:00",
            candidate_key=key, cost=float(i), owner_id=owner)])

    def median_ms(fn, rounds=15):
        samples = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            fn()
            samples.append((time.perf_counter() - t0) * 1000)
        samples.sort()
        return samples[len(samples) // 2]

    def batched():
        st.cost_sparklines(pairs, owner=owner, limit=20)

    def naive_n_plus_1():
        for sid, key in pairs:
            st.narrow_history_for_candidate(
                sid, key, ["2026-08-01T00:00:00+00:00"], owner=owner)

    batched_ms = median_ms(batched)
    naive_ms = median_ms(naive_n_plus_1, rounds=5)   # 100 次往返，跑少幾輪就夠看出量級

    # 2× 安全邊際：批次版本不只是打平，必須明顯快於逐一查詢版本。
    assert batched_ms * 2 < naive_ms, (
        f"批次查詢（{batched_ms:.2f}ms）沒有明顯快於逐一查詢"
        f"（{naive_ms:.2f}ms）——清單端點可能悄悄退化成 N+1")
