"""SCALE-16（#267，Scaling Foundation Stage 1-5）：historical fact
ledger（`results`，append-only、每 refresh 一列、`view` 恆為 `None`）
與 current full-view materialization（`current_results`，每 scenario
一列、覆寫更新、`view` 恆為完整 dict）分離。

本檔案專門驗證 #267 issue 本文逐條列出的 Acceptance Criteria；
`tests/test_storage_contract.py`／`tests/test_api_iv_history.py`／
`tests/test_api_refresh.py`／`tests/test_scale01_historical_fact.py`／
`tests/test_scale14_history_read_path.py` 已經在各自既有的測試範圍內
順手驗證過這個切分不破壞既有行為（`latest_result()`／
`latest_summaries()` 改讀 `current_results` 後逐一修正過），這裡不
重複，只補 issue 明文點名、之前沒有專屬測試覆蓋的幾條。
"""
from __future__ import annotations

import dataclasses
import json
import os

import pytest
from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage import ResultRecord, Scenario
from api_app.storage.memory import MemoryStorage
from option_chaser import service, store
from option_chaser.data.snapshot import load_snapshot
from option_chaser.models import AnalysisParams

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")
FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"


def _client(*, storage=None):
    snap = load_snapshot(FIX)
    return TestClient(create_app(fetch=lambda symbol: snap,
                                 storage=storage or MemoryStorage()))


def _client_with_advancing_snapshot(*, storage=None):
    """每次 `fetch()` 回傳一份 `fetched_at` 不同的快照——用來模擬「N 次
    真正不同時間點的 refresh」。固定快照（`_client()`）反覆 refresh 會
    因為 `analyzed_at` 相同而在 `(scenario_id, analyzed_at)` PK 上
    UPSERT 成同一列，這是既有、正確的冪等行為，不是本票要驗證的
    「N 次相異 refresh」情境。"""
    base = load_snapshot(FIX)
    counter = {"n": 0}

    def fetch(symbol):
        counter["n"] += 1
        ts = f"2026-07-{(counter['n'] % 28) + 1:02d}T21:30:00-04:00"
        return dataclasses.replace(base, fetched_at=ts)

    return TestClient(create_app(fetch=fetch,
                                 storage=storage or MemoryStorage()))


# ---------- AC-1：N 次 refresh ⇒ N 筆 fact rows + 恆定 1 份 current view ----------

def test_n_refreshes_produce_n_fact_rows_and_exactly_one_current_view():
    """AC-1：切換後同一 scenario 連續 N 次 refresh ⇒ N 筆 historical
    fact rows + 恆定 1 份 current full view；每一筆 fact 都保有
    SCALE-01 context/provenance/version。"""
    storage = MemoryStorage()
    c = _client_with_advancing_snapshot(storage=storage)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
        "strategies": ["vertical-spread"]}).json()

    n = 5
    for _ in range(n):
        c.post(f"/api/scenarios/{sc['id']}/refresh")

    ledger = storage.result_history(sc["id"], owner="solo")
    assert len(ledger) == n
    for rec in ledger:
        # 每一筆歷史 fact row：view 已剝離，SCALE-01 六個 context 欄位
        # 皆保有（不是只有最新一筆才有——每次 refresh 都各自完整）。
        assert rec.view is None
        assert rec.resolved_params is not None
        assert rec.requested_strategies is not None
        assert rec.engine_version is not None
        assert rec.view_schema_version is not None
        assert rec.history_replay_version == store.HISTORY_REPLAY_VERSION
        assert rec.snapshot_source is not None

    current = storage.latest_result(sc["id"], owner="solo")
    assert current is not None
    assert current.view is not None
    # 「恆定 1 份」——不是「最新的一份長得像只有一份」，是這張表本身
    # 對這個 scenario 只可能有一列（PK=scenario_id）。MemoryStorage
    # 用 dict 天然保證；Postgres 那半由 AC-1 的 postgres 版本
    # （下面 `test_current_results_table_has_exactly_one_row_per_
    # scenario_after_n_refreshes`）直接數資料列驗證。


@pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")
def test_current_results_table_has_exactly_one_row_per_scenario_after_n_refreshes():
    """AC-1 的 Postgres 版本：不透過 `latest_result()` 這層抽象，直接
    對 `current_results` 表 `SELECT COUNT(*)`——證明「恆定 1 份」是
    這張表的資料事實，不是查詢方法剛好只回一筆的巧合。"""
    import psycopg

    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, current_results, "
                     "snapshots RESTART IDENTITY")

    c = _client_with_advancing_snapshot(storage=st)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
        "strategies": ["vertical-spread"]}).json()

    n = 5
    for _ in range(n):
        c.post(f"/api/scenarios/{sc['id']}/refresh")

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) FROM current_results WHERE scenario_id = %s",
            (sc["id"],)).fetchone()[0]
        ledger_count = conn.execute(
            "SELECT COUNT(*) FROM results WHERE scenario_id = %s",
            (sc["id"],)).fetchone()[0]
    assert row_count == 1
    assert ledger_count == n


# ---------- AC-2：current detail 與切換前 serialized parity ----------
#
# `/code-review` Spec 軸抓到：AC-2「current detail/heatmap/champion/
# ranking/user-visible payload 與切換前 serialized parity」只靠既有
# HTTP 測試套件（`test_detail_projection.py` 等）在改動後仍然通過來
# 間接佐證，沒有一條測試直接對照「切換前會回什麼」與「切換後回
# 什麼」。這裡補上：`store.project_for_detail()`（T13／#231，服務
# `GET /api/scenarios/{id}` 這個端點傳輸投影，本身早就會剝除
# `all_candidates`／`candidates`——SCALE-17 之前它就是這樣）套用在
# 「引擎直接算出、完全沒碰過 storage」的新鮮 view 上，即為「切換前
# 這個端點理應回傳的內容」（因為 T13 這個函式本身沒有被 SCALE-16/17
# 改動，它的輸入輸出關係是舊行為的真實代表，不是重新發明一份假設）；
# 拿它跟真的走完整條新路徑（`create_scenario` → `refresh` →
# `GET /api/scenarios/{id}`，經過 dual-write／SCALE-17 剝除／
# current_results 讀取）拿到的真實 HTTP 回應逐位元比對。

def test_current_detail_response_has_serialized_parity_with_the_pre_cutover_shape():
    """AC-2：current detail 的 user-visible payload 與切換前
    serialized parity——不是「兩者恰好都通過同一組既有斷言」，是
    直接逐位元比對兩條路徑算出來的 JSON。

    「切換前這個端點理應回傳的內容」不是另外用引擎裸呼叫重算（那樣
    得自己重現 `create_app()` 預設 loader 的 note 文字等旁支細節，
    容易做出看似嚴謹、實則比對到不相關雜訊的測試）——改用同一個
    `TestClient` 打 `POST /api/analyze`：AC-3 已明文保證這條路徑
    完全不受 SCALE-16/17 影響（`test_scale17_persisted_projection.py`
    專屬驗證過），因此它的回應就是「引擎對這份參數算出來的原始
    view」，且與 `GET /api/scenarios/{id}/refresh` 共用同一組
    loader／snapshot 注入，天生不會有旁支差異。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
        "strategies": ["vertical-spread"]}).json()
    c.post(f"/api/scenarios/{sc['id']}/refresh")

    # 真實走完整條新路徑（dual-write ＋ current_results 讀取 ＋ T13
    # 傳輸投影）拿到的回應。
    detail = c.get(f"/api/scenarios/{sc['id']}").json()

    # 「切換前這個端點理應回傳的內容」：同一個 client、同一組 loader，
    # 走 AC-3 保證不受影響的 `/api/analyze` 拿到未剝除的原始 view，
    # 套用未曾被 SCALE-16/17 改動過的既有 `project_for_detail()`。
    # 劇本用 "vertical-spread" family（T06／#221 展開成
    # bull-call-spread／bear-put-spread 兩個 subtype，方向不合的那個
    # 仍會以 `status="skipped_direction"` 留在 `results[]` 裡，不是
    # 被移除），`/api/analyze` 不做 family 展開、要顯式帶出同一組
    # subtype 才會產生同樣兩筆 `results[]` entry，否則只請求一個
    # subtype 會少一筆、逐位元比對必然失敗——不是 SCALE-16/17 造成的
    # 差異，是兩個端點本身的既有語意不同（family 展開 vs 明確
    # subtype），對照組要按照這個既有語意建構才公平。
    raw_view = c.post("/api/analyze", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
        "strategies": ["bull-call-spread", "bear-put-spread"]}).json()
    pre_cutover_shape = store.project_for_detail(raw_view)
    # `/api/analyze` 是一次性分析、恆用固定的 adhoc scenario id
    # （`_ADHOC_SCENARIO_ID`，`main.py` 既有常數），真正的劇本則有它
    # 自己的 id——這是兩個端點本身既有、預期中的差異，不是 SCALE-16/17
    # 造成的資料不一致，正規化掉才能公平比對其餘內容。
    pre_cutover_shape = {**pre_cutover_shape, "scenario_id": sc["id"]}

    assert json.dumps(detail["latest_result"], sort_keys=True) == \
        json.dumps(pre_cutover_shape, sort_keys=True)
    # 摘要層（champion／ranking／heatmap 依賴的候選池）同樣逐位元核對，
    # 不只比對「有沒有這個 key」。
    assert (detail["latest_result"]["candidate_pool"]
           == pre_cutover_shape["candidate_pool"])
    assert (detail["representative_candidate"]
           == store.representative_candidate(raw_view))


# ---------- AC-3：pre-cutover legacy row 的 full view byte-for-byte 未變 ----------

def test_pre_cutover_legacy_row_view_survives_post_cutover_activity_unchanged():
    """AC-3：本票不得刪／NULL pre-cutover legacy historical view
    payload。模擬「這一列是切換前寫的、`view` 帶著完整內容」，切換後
    對同一個 scenario 繼續正常操作（再刷新、讀 current、讀歷史），
    這一列本身必須逐位元不變——因為程式碼裡沒有任何路徑會回頭改寫
    `results` 表既有列（`save_result()` 是 append-only INSERT ...
    ON CONFLICT DO UPDATE，衝突鍵是 `(scenario_id, analyzed_at)`，
    新 refresh 一定是新的 `analyzed_at`，結構上碰不到舊列）。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc_id = "legacy-sc"
    storage.create_scenario(Scenario(
        id=sc_id, symbol="XYZ", direction="bullish", target_price=110.0,
        target_month="2026-10", notes="", strategies=("vertical-spread",),
        created_at="2026-08-01T00:00:00+00:00", owner_id="solo"))

    legacy_view = store.serialize_result(
        service.run_with_snapshot(
            service.AnalysisRequest(
                symbol="XYZ",
                base_params=AnalysisParams(strategy="bull-call-spread",
                                           target_price=110.0,
                                           target_month="2026-10"),
                strategies=("bull-call-spread",)),
            load_snapshot(FIX)),
        sc_id, None)
    legacy_rec = ResultRecord(sc_id, "2026-08-01T00:00:00+00:00",
                              legacy_view, owner_id="solo")
    storage.save_result(legacy_rec)   # 切換前的既有寫入方式：view 帶完整內容
    legacy_json_before = json.dumps(
        storage.result_history(sc_id, owner="solo")[0].view, sort_keys=True)

    # 切換後的新活動：真的刷新（走 SCALE-16 的新雙寫路徑）、讀 current、
    # 讀歷史——這一切都不該碰到上面那一列。
    c.post(f"/api/scenarios/{sc_id}/refresh")
    c.get(f"/api/scenarios/{sc_id}")
    storage.result_history(sc_id, owner="solo")

    ledger = storage.result_history(sc_id, owner="solo")
    assert len(ledger) == 2   # legacy 那筆 + 本次新 refresh 那筆
    legacy_after = next(r for r in ledger
                        if r.analyzed_at == "2026-08-01T00:00:00+00:00")
    assert json.dumps(legacy_after.view, sort_keys=True) == legacy_json_before
    assert legacy_after.view == legacy_view   # 逐位元（Python 物件層級）未變


# ---------- AC-4：post-cutover fact rows 不攜完整 view ----------

def test_post_cutover_fact_row_never_carries_a_view_even_when_analysis_is_large():
    """AC-4：新 refresh 仍 append 一筆 historical fact row，但該 row
    不再攜帶完整 view payload——不論這次分析本身多大（多 family、多
    候選），fact row 的 `view` 恆為 `None`。"""
    storage = MemoryStorage()
    c = _client(storage=storage)
    sc = c.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 110.0, "target_month": "2026-10",
        "strategies": ["vertical-spread", "butterfly"]}).json()   # 多 family

    c.post(f"/api/scenarios/{sc['id']}/refresh")

    ledger = storage.result_history(sc["id"], owner="solo")
    assert len(ledger) == 1
    assert ledger[0].view is None
    # 對照組：current 那份必須真的是完整 view（否則畫面會壞掉）——
    # 這條同時證明「view=None」不是因為分析本身失敗或空手。
    current = storage.latest_result(sc["id"], owner="solo")
    assert current.view is not None
    assert current.view["results"]


# ---------- AC-7：owner A/B current full views 互不可見 ----------

def test_current_full_view_is_owner_isolated():
    """AC-7：owner A／B 各自的 current full view 互不可見。
    （`tests/test_storage_contract.py` 已對 `latest_result()`／
    `latest_summaries()` 的既有 owner 隔離契約補了正／負向雙重斷言，
    這裡是本票 issue 明文點名 AC 的專屬覆蓋，走真實 `save_current_
    result()` 寫入路徑而非借用既有 fixture helper。）"""
    storage = MemoryStorage()
    a_id, b_id = "owner-a-sc", "owner-b-sc"
    for sid, owner in ((a_id, "owner-a"), (b_id, "owner-b")):
        storage.create_scenario(Scenario(
            id=sid, symbol="XYZ", direction="bullish", target_price=110.0,
            target_month="2026-10", notes="", strategies=("vertical-spread",),
            created_at="2026-08-01T00:00:00+00:00", owner_id=owner))
        storage.save_current_result(ResultRecord(
            sid, "2026-08-01T00:00:00+00:00", {"marker": owner},
            owner_id=owner))

    assert storage.latest_result(a_id, owner="owner-a").view == {"marker": "owner-a"}
    assert storage.latest_result(b_id, owner="owner-b").view == {"marker": "owner-b"}
    # 跨 owner 讀取自己看得到的 scenario id，但傳錯 owner——一律 None，
    # 與「這個 scenario 根本不存在」的回應無法區分（既有 fail-closed
    # 慣例，SCALE-11）。
    assert storage.latest_result(a_id, owner="owner-b") is None
    assert storage.latest_result(b_id, owner="owner-a") is None
    assert set(storage.latest_summaries(owner="owner-a")) == {a_id}
    assert set(storage.latest_summaries(owner="owner-b")) == {b_id}


# ---------- AC-5／AC-6：真實 Postgres physical storage benchmark ----------

def _real_production_view():
    """真實引擎算出的 production-scale view（5 到期日×60 履約價/側，
    4 個 debit subtype 全開——貼近真實多 family 使用情境），
    `q_by_symbol=None` 跳過 IV 反解（本benchmark 量的是 storage
    大小，不是 calibration 運算時間，REPAIR-03／#240 已經另外驗證過
    calibration 本身的效能）。"""
    snap = load_snapshot("tests/fixtures/xyz_v8_production_scale.json")
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="bull-call-spread",
                                   target_price=110.0, target_month="2026-10"),
        strategies=("bull-call-spread", "bear-put-spread",
                    "call-fly", "put-fly"))
    result = service.run_with_snapshot(req, snap)
    return store.serialize_result(result, "bench", None)


@pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")
def test_scale16_physical_storage_margin_growth_30_and_100_refreshes():
    """AC-5：用真實 PostgreSQL physical sizes 重新量 30/100 refresh
    邊際成長，把新增 historical fact row 成本算進去；不沿用 Prototype
    58.70× 當成未量測的最終數字。

    ## 量測方法

    真實引擎算出的 production-scale view（4 個 debit subtype 全開，
    600 張合約、5 到期日×60 履約價/側）：logical JSON 20,950,391
    bytes，其中 `all_candidates` 佔 98.31%（`strip_persisted_all_
    candidates()` 後剩 353,567 bytes）——與 Audit 原文「97.82%」量級
    吻合，差異來自不同 fixture／啟用 subtype 組合，非量測誤差。

    **OLD 基準**（SCALE-16／SCALE-17 這兩張票之前、也就是今天
    production 實際在跑的形狀）：每次 refresh 對 `results` 表寫入
    一筆帶完整 view（含 all_candidates）的新列，PK
    `(scenario_id, analyzed_at)`，逐 refresh 累積、無上限成長。

    **NEW 形狀**（本票＋SCALE-17 完成後）：每次 refresh 對 `results`
    寫入一筆 `view=None` 的極小 fact row（`resolved_params`／
    `requested_strategies`／provenance／version 幾個小欄位），
    `current_results` 只覆寫同一列（PK=scenario_id，不隨 N 增長）。

    ## 為何不是 Prototype 的 58.70×，以及差距怎麼解釋

    Prototype #065／SCALE-12 的 58.70× 量的是「visible-only narrow
    history 取代『每次留存全部候選歷史』」這件事本身的邊際成長比——
    分子分母都不含 `all_candidates` 從 view 裡整個消失這一刀（那是
    C1／SCALE-17 的貢獻，Prototype 當時方案裡 view 的 `all_candidates`
    仍完整保留在**歷史** row 上，只是額外多存一份 narrow）。本測試
    量的是完全不同的兩個形狀替換：「每次都留一份完整 view（含 all_
    candidates）」→「歷史只留 fact、完整 view 只覆寫一份」，因此
    數字結構上不會、也不應該與 58.70× 相同——這裡驗證的是
    order-of-magnitude 優於 baseline（AC-5 明文門檻），不是重現
    Prototype 的那個數字。

    ## `/code-review` Spec 軸抓到的真缺口，已修正

    本測試**曾經**只跑一種情境：N 次覆寫全部做完、只在最後 VACUUM 一次
    （`run_new(n, vacuum_between_writes=False)`），量到 N=100 時邊際
    成長 166,052 B/refresh、19.49×。`/code-review` Spec 軸指出這個數字
    「比 Prototype B 的 45,384 B/refresh 還大，即使新 ledger row 本身
    比 narrow-history 寫入更小」，質疑解釋不完整——**查證後確認這個
    質疑成立**：連續覆寫同一列、中途不 VACUUM，死 tuple 在整個 burst
    期間持續累積到 burst 結尾才一次清掉，量到的其實是「MVCC 冷啟動
    膨脹」而非 production 穩態足跡。直接拆解驗證：`results`（純
    append）邊際成長穩定在 1,475 B/refresh；`current_results`（單列
    覆寫）在「連續覆寫、只在最後 VACUUM 一次」情境下量到
    164,577 B/refresh（幾乎線性隨 N 累積），但在「每次覆寫後就
    VACUUM」情境下只有 4,260 B/refresh——**40 倍的差距，完全來自
    benchmark 方法本身，不是形狀改變帶來的真實成本**。

    Production 的真實存取節奏支持「每次覆寫都 VACUUM」這個情境才是
    穩態代表值：refresh 只有三個既有觸發時機（開站／建立劇本／使用者
    手動全量刷新，見 CONTEXT.md），單一劇本兩次 refresh 之間天然有
    數十分鐘到數小時的間隔，遠遠超過 autovacuum 預設 1 分鐘的
    naptime；本測試因此同時量測**兩種**情境並各自算出對 OLD 基準的
    倍數：「連續 burst、只在最後 VACUUM 一次」當保守下限（仍需通過
    AC-5 至少一個數量級的門檻），「每次覆寫都 VACUUM」當 production
    穩態代表值（供最終報告使用，不是及格線）——不是挑對自己有利的
    數字通過，兩個數字都印出來、都有各自的物理意義說明。
    """
    import psycopg

    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, current_results, "
                     "snapshots RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS scale16_bench_old")
        # OLD 基準：模擬「本票之前」的 `results` 形狀——單一表，
        # PK (scenario_id, analyzed_at)，view 帶完整內容、無上限累積。
        conn.execute("CREATE TABLE scale16_bench_old ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, "
                     "PRIMARY KEY (scenario_id, analyzed_at))")

    view = _real_production_view()
    fact = store.historical_fact_context(view)
    stripped_view = store.strip_persisted_all_candidates(view)
    st.create_scenario(Scenario(
        id="bench", symbol="XYZ", direction="bullish", target_price=110.0,
        target_month="2026-10", notes="", strategies=("vertical-spread",),
        created_at="2026-08-01T00:00:00+00:00", owner_id="solo"))

    def table_bytes(conn, table, where_scenario=None):
        # `pg_total_relation_size` 含 TOAST＋索引，是使用者真正在乎
        # 的「這張表在磁碟上占多少空間」，不是邏輯 JSON 長度。
        return conn.execute(
            f"SELECT pg_total_relation_size('{table}')").fetchone()[0]

    def run_old(n):
        from psycopg.types.json import Jsonb

        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("TRUNCATE scale16_bench_old")
            conn.execute("VACUUM FULL scale16_bench_old")
            before = table_bytes(conn, "scale16_bench_old")
            for i in range(n):
                ts = f"2026-08-{(i % 28) + 1:02d}T{i:02d}:00:00+00:00"
                conn.execute(
                    "INSERT INTO scale16_bench_old (scenario_id, analyzed_at, view) "
                    "VALUES (%s, %s, %s)",
                    ("bench", ts, Jsonb(view)))
            conn.execute("VACUUM FULL scale16_bench_old")
            after = table_bytes(conn, "scale16_bench_old")
        return before, after

    def run_new(n, *, vacuum_between_writes):
        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("TRUNCATE results, current_results")
            conn.execute("VACUUM FULL results")
            conn.execute("VACUUM FULL current_results")
            before = (table_bytes(conn, "results")
                      + table_bytes(conn, "current_results"))
        vconn = psycopg.connect(TEST_DB_URL, autocommit=True) if vacuum_between_writes else None
        try:
            for i in range(n):
                ts = f"2026-08-{(i % 28) + 1:02d}T{i:02d}:00:00+00:00"
                rec = ResultRecord("bench", ts, None, owner_id="solo", **fact)
                st.save_result(rec)
                st.save_current_result(dataclasses.replace(rec, view=stripped_view))
                if vacuum_between_writes:
                    # 正常（非 FULL）VACUUM——模擬 production 的真實
                    # 存取型態：refresh 之間天然有數十分鐘到數小時的
                    # 間隔（三個觸發時機的既有規則，不是緊湊寫入迴圈），
                    # autovacuum 的預設 1 分鐘 naptime 遠遠來得及在下
                    # 一次 refresh 前把上一次覆寫留下的死 tuple 收掉。
                    vconn.execute("VACUUM current_results")
        finally:
            if vconn is not None:
                vconn.close()
        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("VACUUM results")
            conn.execute("VACUUM current_results")
            after = (table_bytes(conn, "results")
                    + table_bytes(conn, "current_results"))
        return before, after

    results = {}
    for n in (30, 100):
        old_before, old_after = run_old(n)
        new_before_pess, new_after_pess = run_new(n, vacuum_between_writes=False)
        new_before_ss, new_after_ss = run_new(n, vacuum_between_writes=True)
        old_margin = (old_after - old_before) / n
        new_margin_pessimistic = (new_after_pess - new_before_pess) / n
        new_margin_steady_state = (new_after_ss - new_before_ss) / n
        results[n] = (old_margin, new_margin_pessimistic, new_margin_steady_state)

    for n, (old_margin, pess_margin, ss_margin) in results.items():
        pess_ratio = old_margin / pess_margin if pess_margin > 0 else float("inf")
        ss_ratio = old_margin / ss_margin if ss_margin > 0 else float("inf")
        print(f"\n[SCALE-16 AC-5] N={n}: OLD {old_margin:,.0f} B/refresh, "
              f"NEW（連續覆寫、burst 結束才 VACUUM 一次，悲觀情境）"
              f"{pess_margin:,.0f} B/refresh（{pess_ratio:.2f}x）, "
              f"NEW（每次覆寫都 VACUUM，模擬 production 真實稀疏存取節奏）"
              f"{ss_margin:,.0f} B/refresh（{ss_ratio:.2f}x）")
        # AC-5 門檻：至少 order-of-magnitude（10×）優於 baseline——用
        # 悲觀情境（連續 burst、VACUUM 追不上）當及格線，這是保守下限，
        # 不是挑對自己有利的數字通過。
        assert pess_ratio >= 10.0, (
            f"N={n}：新形狀邊際成長（悲觀情境）只比舊形狀好 "
            f"{pess_ratio:.2f}x，未達 AC-5 要求的至少一個數量級")

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS scale16_bench_old")


@pytest.mark.skipif(not TEST_DB_URL, reason="需要 OC_TEST_DATABASE_URL")
def test_scale16_normal_vacuum_controls_dead_tuples_on_current_results():
    """AC-6：current overwrite 前/後 dead-tuple 量測；確認正常
    autovacuum（這裡用手動觸發的一般 `VACUUM`，等價於 autovacuum
    真正做的事，只是不等它自己的排程觸發——測試需要決定性）能控制
    MVCC growth，不依賴人工 `VACUUM FULL`。

    `current_results` 是本票唯一會被 `UPDATE`（`INSERT ... ON
    CONFLICT DO UPDATE`）的新表——每次覆寫都在 Postgres MVCC 下產生
    一個新版本、把舊版本標記為死 tuple，是這裡唯一有 bloat 風險的
    地方；`results` 純 append，不會有這個問題。
    """
    import psycopg

    from api_app.storage.postgres import PostgresStorage

    st = PostgresStorage(TEST_DB_URL)
    st._ensure_schema()
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, current_results, "
                     "snapshots RESTART IDENTITY")
        # 本機測試 Postgres 有真的在跑的 autovacuum launcher（`ps aux`
        # 可見）——這條測試要對「量到的死 tuple 數字」做決定性斷言，
        # 若背景 autovacuum 剛好在量測窗口內對這張小表跑過一輪，
        # `n_dead_tup` 會提早被清成 0，讓「VACUUM 前後的差異」這個
        # 對照組本身失去意義（初次實測就發生過這個 race：量到
        # `dead_before=1` 而非預期的 49）。先關掉這張表的 autovacuum，
        # 讓「覆寫留下死 tuple」與「手動 VACUUM 清掉它」兩個階段的
        # 因果順序不受背景行程搶跑影響；測試結束前會再打開。
        conn.execute("ALTER TABLE current_results "
                     "SET (autovacuum_enabled = false)")

    try:
        st.create_scenario(Scenario(
            id="vac-bench", symbol="XYZ", direction="bullish", target_price=110.0,
            target_month="2026-10", notes="", strategies=("vertical-spread",),
            created_at="2026-08-01T00:00:00+00:00", owner_id="solo"))

        # 刻意用貼近 production 真實 `current_results.view` 大小的內容
        # （~350KB，SCALE-17 剝除 all_candidates 後量到的量級，見上面
        # AC-5 benchmark），不是隨手湊的小字串——首次用 1KB marker
        # 實測發現 Postgres 的 HOT-update 機制會在單一 page 內就地更新
        # 這種小 row，opportunistic pruning 自動把死 tuple 壓到
        # 幾乎為零、完全不需要 VACUUM，這雖然也是「MVCC growth 受控」
        # 的一種真實證據，但驗證不到 AC-6 真正要問的問題：現實大小的
        # view 會被 TOAST 成多頁儲存，HOT 機制在這裡不適用，死 tuple
        # 會真的累積，VACUUM 的角色在這個尺度才看得出來（已用相同腳本
        # 對照驗證：1KB 時 dead_tup 停在 1，350KB 時 dead_tup=49，
        # 逐一對應 50 次覆寫的其中 49 次）。
        big_view = {"marker": "x" * 350_000}
        n = 50
        for i in range(n):
            st.save_current_result(ResultRecord(
                "vac-bench", f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00",
                big_view, owner_id="solo"))

        def dead_live(conn):
            # `pg_stat_user_tables` 是 VACUUM 直接維護的統計視圖，不是
            # 推算值——這裡讀到的數字就是 VACUUM 實際回報的結果。
            conn.execute("ANALYZE current_results")
            row = conn.execute(
                "SELECT n_dead_tup, n_live_tup FROM pg_stat_user_tables "
                "WHERE relname = 'current_results'").fetchone()
            return row

        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            dead_before, live_before = dead_live(conn)
            size_before = conn.execute(
                "SELECT pg_total_relation_size('current_results')").fetchone()[0]
            assert live_before == 1   # PK=scenario_id，覆寫 N 次後仍只有 1 筆活列
            # 自動 vacuum 已關閉，N 次覆寫留下的死 tuple 必須還在
            # （第一次 INSERT 不算覆寫，其餘 N-1 次才各留一個死版本；
            # 依 Postgres 版本／HOT update 細節，觀察到的數字可能略高
            # 於 N-1，門檻定為 N-1 而非要求逐一相等）。
            assert dead_before >= n - 1

            conn.execute("VACUUM current_results")   # 正常 VACUUM，非 FULL
            dead_after, live_after = dead_live(conn)
            size_after = conn.execute(
                "SELECT pg_total_relation_size('current_results')").fetchone()[0]

        print(f"\n[SCALE-16 AC-6] before VACUUM: dead={dead_before} "
              f"live={live_before} size={size_before:,}B / after VACUUM: "
              f"dead={dead_after} live={live_after} size={size_after:,}B")

        # 正常 VACUUM（非 FULL）不歸還磁碟空間給作業系統，但會把死
        # tuple 標記為可重用（下次 INSERT/UPDATE 不需要再向檔案系統要
        # 新的 page）——這正是「不依賴人工 VACUUM FULL 就能控制 MVCC
        # growth」的意思：死 tuple 計數清零，證明空間已回收供未來覆寫
        # 重用，磁碟大小本身不會因為「VACUUM 沒有做 FULL」而繼續無上限
        # 累積。
        assert dead_after == 0
        assert live_after == 1
        # 再覆寫一輪，驗證空間確實被重用而非繼續往外擴張。
        for i in range(n):
            st.save_current_result(ResultRecord(
                "vac-bench", f"2026-09-{(i % 28) + 1:02d}T00:00:00+00:00",
                big_view, owner_id="solo"))
        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("VACUUM current_results")
            size_after_second_round = conn.execute(
                "SELECT pg_total_relation_size('current_results')").fetchone()[0]
        print(f"[SCALE-16 AC-6] after a second round of {n} overwrites + "
              f"VACUUM: size={size_after_second_round:,}B (first round "
              f"after-VACUUM was {size_after:,}B)")
        # 空間被重用時，第二輪覆寫後的大小不該遠大於第一輪——允許小幅
        # page-level 開銷差異，但不應該是「又長出一整輪的量」。
        assert size_after_second_round <= size_after * 1.5
    finally:
        # 這是共用測試資料庫的一張表——測試結束後把 autovacuum 開關
        # 還原，不讓這條測試的設定洩漏出去影響後續測試或這個資料庫
        # 未來的正常運作。
        with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
            conn.execute("ALTER TABLE current_results "
                         "SET (autovacuum_enabled = true)")
