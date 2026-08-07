"""儲存層契約測試（V2／#50）——同一份行為，兩個實作都要通過。

記憶體假體與 Postgres adapter 若行為不一致，測試綠燈就沒有意義：
用假體跑出來的結論不能保證正式環境成立。因此這份測試 parametrize
在兩個實作上，Postgres 那組打真的資料庫（本機起一個即可，見
`docs/deploy-vercel.md`）。

沒有 `OC_TEST_DATABASE_URL` 時 Postgres 那組會跳過——這是有意的
（它需要一個跑著的 PG server），但跳過原因會明白寫在測試輸出裡，
不是靜默通過。
"""
import os

import pytest

from api_app.storage import RateCacheEntry, ResultRecord, Scenario, ScenarioExists
from api_app.storage.memory import MemoryStorage

TEST_DB_URL = os.environ.get("OC_TEST_DATABASE_URL")


def _scenario(sid="s1", *, symbol="TLT", created_at="2026-08-01T00:00:00+00:00"):
    return Scenario(id=sid, symbol=symbol, direction="bullish",
                    target_price=120.0, target_month="2028-05", notes="",
                    strategies=("bull-call-spread",), created_at=created_at)


@pytest.fixture(params=["memory", "postgres"])
def storage(request):
    if request.param == "memory":
        yield MemoryStorage()
        return
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）才能"
                    "驗證 Postgres adapter；跳過＝這組沒被驗證過")
    import psycopg

    from api_app.storage.postgres import PostgresStorage
    st = PostgresStorage(TEST_DB_URL)
    # 清庫是測試自己的事，不放進正式 adapter（正式環境不該有 TRUNCATE）。
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache "
                     "RESTART IDENTITY")
    yield st


# ---------- 劇本 CRUD ----------

def test_created_scenario_can_be_read_back(storage):
    sc = _scenario()
    storage.create_scenario(sc)
    assert storage.get_scenario("s1") == sc


def test_missing_scenario_is_none_not_an_error(storage):
    assert storage.get_scenario("nope") is None


def test_duplicate_id_is_rejected(storage):
    storage.create_scenario(_scenario())
    with pytest.raises(ScenarioExists):
        storage.create_scenario(_scenario())


def test_list_is_ordered_by_creation_time(storage):
    storage.create_scenario(_scenario("b", created_at="2026-08-02T00:00:00+00:00"))
    storage.create_scenario(_scenario("a", created_at="2026-08-01T00:00:00+00:00"))
    assert [s.id for s in storage.list_scenarios()] == ["a", "b"]


def test_strategies_survive_the_roundtrip_as_a_tuple(storage):
    sc = _scenario()
    storage.create_scenario(sc)
    got = storage.get_scenario("s1")
    assert got.strategies == ("bull-call-spread",)
    assert isinstance(got.strategies, tuple)


# ---------- 封存＝軟刪除 ----------

def test_archiving_hides_from_the_default_list_but_keeps_the_record(storage):
    storage.create_scenario(_scenario())
    assert storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00") is True

    assert storage.list_scenarios() == []                      # 預設清單看不到
    archived = storage.get_scenario("s1")
    assert archived is not None                                # 但紀錄還在
    assert archived.archived_at == "2026-08-05T00:00:00+00:00"
    assert [s.id for s in storage.list_scenarios(include_archived=True)] == ["s1"]


def test_archiving_twice_or_a_missing_scenario_reports_false(storage):
    storage.create_scenario(_scenario())
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")
    assert storage.archive_scenario("s1", ts="2026-08-06T00:00:00+00:00") is False
    assert storage.archive_scenario("nope", ts="2026-08-06T00:00:00+00:00") is False


def test_archived_scenario_keeps_its_results(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T12:00:00+00:00", {"a": 1}))
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")
    assert storage.latest_result("s1").view == {"a": 1}


# ---------- 還原（TR2／#89） ----------

def test_restoring_an_archived_scenario_brings_it_back_to_the_default_list(storage):
    storage.create_scenario(_scenario())
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")

    assert storage.restore_scenario("s1", ts="2026-08-06T00:00:00+00:00") is True

    assert [s.id for s in storage.list_scenarios()] == ["s1"]     # 預設清單重新看得到
    restored = storage.get_scenario("s1")
    assert restored.archived_at is None


def test_restoring_a_never_archived_or_missing_scenario_reports_false(storage):
    storage.create_scenario(_scenario())
    assert storage.restore_scenario("s1", ts="2026-08-06T00:00:00+00:00") is False
    assert storage.restore_scenario("nope", ts="2026-08-06T00:00:00+00:00") is False


def test_restored_scenario_keeps_its_results(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T12:00:00+00:00", {"a": 1}))
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")
    storage.restore_scenario("s1", ts="2026-08-06T00:00:00+00:00")
    assert storage.latest_result("s1").view == {"a": 1}


# ---------- 永久刪除（TR3／#90） ----------
#
# 語意上只允許刪除已封存的劇本——這是安全閘門，永久刪除必須先進垃圾桶，
# 不能一步到位刪掉還在使用中的劇本。cascade 清掉 results／snapshots／
# events，不依賴 FK `ON DELETE CASCADE`（沿用專案既有「不用 FK 約束，
# 應用層自己保證一致性」的設計慣例）。

def test_deleting_an_archived_scenario_removes_it_and_everything_under_it(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T12:00:00+00:00", {"a": 1}))
    storage.save_snapshot("s1", "2026-08-01T12:00:00+00:00", {"contracts": []})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={})
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")

    assert storage.delete_scenario("s1") is True

    assert storage.get_scenario("s1") is None
    assert [s.id for s in storage.list_scenarios(include_archived=True)] == []
    assert storage.result_history("s1") == []
    assert storage.get_snapshot("s1", "2026-08-01T12:00:00+00:00") is None
    assert storage.list_events(scenario_id="s1") == []


def test_deleting_an_unarchived_scenario_is_rejected_and_keeps_everything(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T12:00:00+00:00", {"a": 1}))

    assert storage.delete_scenario("s1") is False

    assert storage.get_scenario("s1") is not None
    assert storage.latest_result("s1").view == {"a": 1}


def test_deleting_a_missing_scenario_reports_false(storage):
    assert storage.delete_scenario("nope") is False


def test_deleting_does_not_touch_other_scenarios(storage):
    storage.create_scenario(_scenario("s1"))
    storage.create_scenario(_scenario("s2"))
    storage.save_result(ResultRecord("s2", "2026-08-01T12:00:00+00:00", {"b": 1}))
    storage.archive_scenario("s1", ts="2026-08-05T00:00:00+00:00")

    storage.delete_scenario("s1")

    assert storage.get_scenario("s2") is not None
    assert storage.latest_result("s2").view == {"b": 1}


# ---------- 結果與歷史 ----------

def test_latest_result_is_the_newest_by_analyzed_at(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-02T12:00:00+00:00", {"n": 2}))
    storage.save_result(ResultRecord("s1", "2026-08-01T12:00:00+00:00", {"n": 1}))
    assert storage.latest_result("s1").view == {"n": 2}


def test_history_is_ordered_oldest_first(storage):
    storage.create_scenario(_scenario())
    for ts, n in (("2026-08-03T00:00:00+00:00", 3),
                  ("2026-08-01T00:00:00+00:00", 1),
                  ("2026-08-02T00:00:00+00:00", 2)):
        storage.save_result(ResultRecord("s1", ts, {"n": n}))
    assert [r.view["n"] for r in storage.result_history("s1")] == [1, 2, 3]


def test_saving_the_same_timestamp_twice_overwrites_rather_than_duplicates(storage):
    """同一次快照重跑（例如重試）不該在歷史裡留下兩筆。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 99}))
    hist = storage.result_history("s1")
    assert len(hist) == 1 and hist[0].view["n"] == 99


def test_no_results_yet_is_none_and_empty(storage):
    storage.create_scenario(_scenario())
    assert storage.latest_result("s1") is None
    assert storage.result_history("s1") == []


def test_results_do_not_leak_across_scenarios(storage):
    storage.create_scenario(_scenario("s1"))
    storage.create_scenario(_scenario("s2"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"who": 1}))
    assert storage.latest_result("s2") is None


def test_large_view_survives_the_roundtrip(storage):
    """實際 view dict 有十萬字元等級（含 Heatmap 矩陣），巢狀結構要完整。"""
    storage.create_scenario(_scenario())
    view = {"meta": {"spot": 82.25}, "results": [{"expiry_top10": [
        {"expiry": "2028-06-16", "candidates": [{"k": i} for i in range(50)]}]}],
        "nested": {"deep": {"list": list(range(200))}}}
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", view))
    assert storage.latest_result("s1").view == view


# ---------- 原始快照 ----------

def test_snapshot_is_stored_alongside_its_result_and_read_back(storage):
    """V8 的「原始資料 CSV」要拿當次的原始選擇權鏈——只存 view dict
    是不夠的（它沒有逐筆合約報價）。"""
    storage.create_scenario(_scenario())
    snap = {"schema_version": 2, "symbol": "TLT", "spot": 82.25,
            "source": "cboe", "fetched_at": "2026-08-01T00:00:00+00:00",
            "contracts": [{"strike": 100.0, "bid": 1.1, "ask": 1.2}]}
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", snap)
    assert storage.get_snapshot("s1", "2026-08-01T00:00:00+00:00") == snap


def test_missing_snapshot_is_none(storage):
    assert storage.get_snapshot("s1", "2026-08-01T00:00:00+00:00") is None


def test_snapshots_are_keyed_per_analysis(storage):
    storage.create_scenario(_scenario())
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"n": 1})
    storage.save_snapshot("s1", "2026-08-02T00:00:00+00:00", {"n": 2})
    assert storage.get_snapshot("s1", "2026-08-01T00:00:00+00:00") == {"n": 1}
    assert storage.get_snapshot("s1", "2026-08-02T00:00:00+00:00") == {"n": 2}


def test_result_history_does_not_drag_snapshots_along(storage):
    """歷史查詢（V9 走勢圖）會撈很多筆，不該每次附帶數百 KB 的快照。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"big": "x" * 1000})
    (rec,) = storage.result_history("s1")
    assert rec.view == {"n": 1}
    assert not hasattr(rec, "snapshot")


# ---------- 事件（append-only） ----------

def test_events_are_returned_in_append_order(storage):
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={"i": 1})
    storage.append_event(ts="2026-08-02T00:00:00+00:00", scenario_id="s1",
                         event="ANALYSIS_COMPLETED", payload={"i": 2})
    events = storage.list_events()
    assert [e["event"] for e in events] == ["SCENARIO_CREATED",
                                            "ANALYSIS_COMPLETED"]
    assert events[0]["payload"] == {"i": 1}
    assert events[0]["ts"] == "2026-08-01T00:00:00+00:00"


def test_events_can_be_filtered_by_scenario(storage):
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="A", payload={})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s2",
                         event="B", payload={})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id=None,
                         event="GLOBAL", payload={})
    assert [e["event"] for e in storage.list_events(scenario_id="s1")] == ["A"]
    assert len(storage.list_events()) == 3


def test_kind_reports_the_actual_backend(storage, request):
    assert storage.kind == request.node.callspec.params["storage"]


def test_both_implementations_expose_the_whole_port(storage):
    """Protocol 在執行期不強制實作——少一個方法或打錯名字要靠這裡抓，
    否則只有「剛好被測到」才會發現。"""
    from api_app.storage import Storage
    required = [n for n in dir(Storage)
                if not n.startswith("_") and n != "kind"]
    missing = [n for n in required if not callable(getattr(storage, n, None))]
    assert not missing, f"{type(storage).__name__} 缺少：{missing}"
    assert isinstance(storage.kind, str)


# ---------- 利率曲線快取（#67） ----------
#
# 單一一筆、每次寫入即覆蓋——曲線最多日頻更新，不需要歷史，跟結果／
# 快照那種「每次分析各留一筆」是不同的資料形狀。成功與失敗都要留得住：
# 失敗也是「上一次嘗試的狀態」，`/api/health` 得說得出最近一次失敗的
# 原因，不能只有成功才寫。


def test_rate_cache_starts_empty(storage):
    assert storage.get_rate_cache() is None


def test_rate_cache_roundtrips_a_successful_fetch(storage):
    entry = RateCacheEntry(
        fetched_at="2026-08-05T12:00:00+00:00",
        curve={"curve_date": "2026-08-04", "nodes": [[1.0, 0.04]]},
        note="Treasury 曲線 2026-08-04")
    storage.save_rate_cache(entry)
    assert storage.get_rate_cache() == entry


def test_rate_cache_roundtrips_market_day_and_attempted_day(storage):
    """同一市場日只成功抓一次的判準（#74）——`market_day`／
    `attempted_day` 兩個新欄位要在 Postgres 跟記憶體假體都撐得住
    roundtrip，不是只有 dataclass 預設值 `None` 撐得住。"""
    entry = RateCacheEntry(
        fetched_at="2026-08-05T12:00:00+00:00",
        curve={"curve_date": "2026-08-04", "nodes": [[1.0, 0.04]]},
        note="Treasury 曲線 2026-08-04",
        market_day="2026-08-05", attempted_day="2026-08-05")
    storage.save_rate_cache(entry)
    assert storage.get_rate_cache() == entry


def test_rate_cache_can_record_a_failed_attempt(storage):
    entry = RateCacheEntry(fetched_at="2026-08-05T12:00:00+00:00",
                           curve=None, note="曲線不可得")
    storage.save_rate_cache(entry)
    assert storage.get_rate_cache() == entry


def test_rate_cache_overwrites_rather_than_accumulates(storage):
    storage.save_rate_cache(RateCacheEntry(
        fetched_at="2026-08-05T00:00:00+00:00", curve=None, note="曲線不可得"))
    storage.save_rate_cache(RateCacheEntry(
        fetched_at="2026-08-05T06:00:00+00:00",
        curve={"curve_date": "2026-08-05", "nodes": [[1.0, 0.041]]},
        note="Treasury 曲線 2026-08-05"))

    entry = storage.get_rate_cache()
    assert entry.fetched_at == "2026-08-05T06:00:00+00:00"
    assert entry.note == "Treasury 曲線 2026-08-05"


# ---------- 清單摘要（V3／#51） ----------

def test_latest_summaries_returns_the_newest_result_per_scenario(storage):
    """劇本清單要顯示每個劇本的最新收益率與資料時間。

    做成專屬查詢而不是「每個劇本各叫一次 `latest_result`」：view 一份
    十萬字元等級，清單頁把每個劇本的完整 view 都撈回來只為了取一個數字，
    在手機網路上是實打實的浪費。
    """
    storage.create_scenario(_scenario("s1"))
    storage.create_scenario(_scenario("s2", created_at="2026-08-02T00:00:00+00:00"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, 0.5))
    storage.save_result(ResultRecord("s1", "2026-08-03T00:00:00+00:00",
                                     {"n": 2}, 1.25))
    storage.save_result(ResultRecord("s2", "2026-08-02T00:00:00+00:00",
                                     {"n": 3}, None))

    summaries = storage.latest_summaries()
    assert summaries["s1"].analyzed_at == "2026-08-03T00:00:00+00:00"
    assert summaries["s1"].best_return == 1.25
    # 有跑過但該期零候選 → 有時間戳、收益率是 None（≠ 沒跑過）
    assert summaries["s2"].analyzed_at == "2026-08-02T00:00:00+00:00"
    assert summaries["s2"].best_return is None


def test_latest_summaries_omits_scenarios_that_never_ran(storage):
    """沒跑過就不該出現在摘要裡——卡片顯示「—」是呼叫端看不到鍵的結果，
    而不是靠一個假的零值。"""
    storage.create_scenario(_scenario("s1"))
    assert storage.latest_summaries() == {}


def test_best_return_survives_the_result_roundtrip(storage):
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, -0.4))
    assert storage.latest_result("s1").best_return == -0.4
    assert storage.result_history("s1")[0].best_return == -0.4


# ---------- 代表候選（MVP-v2／#77、#78） ----------

_REP = {"strategy": "bull-call-spread",
       "legs": [{"strike": 100.0, "option_type": "call"},
                {"strike": 105.0, "option_type": "call"}],
       "expiry": "2028-05-19", "baseline_return": 1.25}


def test_representative_candidate_survives_the_result_roundtrip(storage):
    """與 `best_return` 同一個模式：規則只有一份（引擎純函式），這裡只是
    落盤結果要能存得進、讀得回，形狀（`strategy`／`legs`／`expiry`）不失真。
    """
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP))
    assert storage.latest_result("s1").representative_candidate == _REP
    assert storage.result_history("s1")[0].representative_candidate == _REP


def test_representative_candidate_defaults_to_none(storage):
    """沒有代表候選（劇本從未成功分析、或該期零合格候選）時是 `None`，
    不是一組編出來的假資料——`ResultRecord` 的預設值本身就是 `None`。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, best_return=None))
    assert storage.latest_result("s1").representative_candidate is None


def test_latest_summaries_carries_the_representative_candidate(storage):
    """清單查詢（`latest_summaries`）跟卡片一樣需要代表候選，不只是
    `best_return` 那個數字——這正是它獨立落盤成一個欄位、而不是每次從
    `view` 現算的理由：清單頁不該為了這幾個履約價把整份 view 搬一次。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP))
    assert storage.latest_summaries()["s1"].representative_candidate == _REP


# ---------- schema 遷移（V3／#51） ----------

def test_existing_results_table_gains_the_new_column():
    """既有部署的 `results` 表是**沒有** `best_return` 的舊版；
    `CREATE TABLE IF NOT EXISTS` 對已存在的表什麼都不做，所以補欄位只能
    靠 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。

    這條路徑在全新資料庫上跑不到（建表時就含該欄位），而它正是已經接上
    Neon 的正式環境會走的那一條——不測就等於沒驗過。
    """
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        # 這個測試不吃 `storage` fixture（它要自己控制建表順序），所以
        # 得自己清乾淨——否則殘留的劇本會讓它以 ScenarioExists 失敗，
        # 看起來像遷移壞了，其實是測試自己髒。
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache "
                     "RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS results")
        # V2 時期的舊表：沒有 best_return
        conn.execute("CREATE TABLE results ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, PRIMARY KEY (scenario_id, analyzed_at))")

    # 每個程序只建一次 schema 的快取要清掉，否則這裡不會真的跑到 DDL
    pg._schema_ready.discard(TEST_DB_URL)
    st = pg.PostgresStorage(TEST_DB_URL)

    # 遷移後寫得進去也讀得回來（沒遷移的話這裡是 UndefinedColumn）
    st.create_scenario(_scenario("mig"))
    st.save_result(ResultRecord("mig", "2026-08-01T00:00:00+00:00", {"n": 1}, 0.75))
    assert st.latest_summaries()["mig"].best_return == 0.75


def test_existing_results_table_gains_the_representative_candidate_column():
    """既有部署的 `results` 表在 MVP-v2（#77、#78）之前只有到
    `best_return` 為止——`representative_candidate` 一樣得靠
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 補上，同一條路徑、同一個
    理由（見 `test_existing_results_table_gains_the_new_column`）。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache "
                     "RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS results")
        # V3 時期的舊表：有 best_return，還沒有 representative_candidate。
        conn.execute("CREATE TABLE results ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, best_return DOUBLE PRECISION, "
                     "PRIMARY KEY (scenario_id, analyzed_at))")

    pg._schema_ready.discard(TEST_DB_URL)
    st = pg.PostgresStorage(TEST_DB_URL)

    st.create_scenario(_scenario("mig2"))
    st.save_result(ResultRecord("mig2", "2026-08-01T00:00:00+00:00", {"n": 1},
                               best_return=0.75, representative_candidate=_REP))
    assert st.latest_summaries()["mig2"].representative_candidate == _REP


def test_migration_still_applies_when_table_creation_hits_a_race():
    """冷啟動競爭：建表那一批已經被別人建好而拋錯時，遷移**不能**跟著死。

    同一批 DDL 送出去會被包成一個 implicit transaction——建表拋錯就整批
    rollback（含 ALTER），而 `_schema_ready` 仍會被標記，該 process 從此
    每次寫入都撞 UndefinedColumn，直到 lambda 被回收。
    """
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache "
                     "RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS results")
        conn.execute("CREATE TABLE results ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, PRIMARY KEY (scenario_id, analyzed_at))")

    # 讓建表那一批拋出「已存在」——模擬另一個冷啟動剛好搶先建好
    original = pg._SCHEMA
    pg._schema_ready.discard(TEST_DB_URL)
    try:
        pg._SCHEMA = "CREATE TABLE scenarios (id TEXT PRIMARY KEY);"   # 已存在 → DuplicateTable
        st = pg.PostgresStorage(TEST_DB_URL)
    finally:
        pg._SCHEMA = original

    # 建表批失敗了，遷移批仍要生效
    st.create_scenario(_scenario("race"))
    st.save_result(ResultRecord("race", "2026-08-01T00:00:00+00:00", {"n": 1}, 0.5))
    assert st.latest_summaries()["race"].best_return == 0.5
