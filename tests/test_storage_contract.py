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

from dataclasses import replace

from api_app.diagnostics import RETENTION_LIMIT, DiagnosticEvent
from api_app.storage import (ChainBackoffEntry, ContractHistory,
                             DataSourceSettings, DividendCacheEntry,
                             IvBackfillRun, IvObservation, ProviderCredential,
                             ProviderVerification, RateCacheEntry,
                             ResultRecord, Scenario, ScenarioExists,
                             TreasuryYearCacheEntry, UsageSetting)
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
    # T02（#186）：schema 就緒檢查移到第一次真正呼叫 `_connect()`才做
    # （建構本身不再連線）——下面這段清庫用的是繞過 `st` 的原始
    # `psycopg.connect`，不會觸發那個惰性檢查，在全新的資料庫上會撞
    # `UndefinedTable`。先讓 `st` 自己碰一次 storage（等同 production
    # 第一個真正打到這個 adapter 的請求），schema 才會就緒。
    st._ensure_schema()
    # 清庫是測試自己的事，不放進正式 adapter（正式環境不該有 TRUNCATE）。
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, chain_backoff, "
                     "data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history, "
                     "diagnostics, operational_metrics RESTART IDENTITY")
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


# ---------- 就地更新（#132） ----------

def test_update_replaces_fields_but_keeps_identity(storage):
    storage.create_scenario(_scenario())
    storage.update_scenario(replace(_scenario(), target_price=999.0))
    got = storage.get_scenario("s1")
    assert got.id == "s1" and got.target_price == 999.0
    assert got.created_at == _scenario().created_at


def test_updating_a_missing_scenario_reports_false(storage):
    assert storage.update_scenario(_scenario("nope")) is False


def test_update_does_not_create_a_second_row(storage):
    storage.create_scenario(_scenario())
    storage.update_scenario(replace(_scenario(), target_price=999.0))
    assert len(storage.list_scenarios()) == 1


def test_clear_results_drops_results_and_snapshots_only(storage):
    """thesis 改了之後舊結果不能留；但事件是不可變的事實，不刪。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"x": 1})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={})

    storage.clear_results("s1")
    assert storage.latest_result("s1") is None
    assert storage.get_snapshot("s1", "2026-08-01T00:00:00+00:00") is None
    assert storage.get_scenario("s1") is not None
    assert len(storage.list_events(scenario_id="s1")) == 1


def test_clear_results_leaves_other_scenarios_alone(storage):
    for sid in ("s1", "s2"):
        storage.create_scenario(_scenario(sid))
        storage.save_result(ResultRecord(sid, "2026-08-01T00:00:00+00:00", {}))
    storage.clear_results("s1")
    assert storage.latest_result("s2") is not None


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


# ---------- 歷史時間戳索引（SCALE-02／#253，Scaling Foundation） ----------

def test_result_timestamps_starts_empty(storage):
    storage.create_scenario(_scenario())
    assert storage.result_timestamps("s1") == []


def test_result_timestamps_lists_the_normal_lockstep_case(storage):
    """正常路徑：`results`／`snapshots` 同一個 analyzed_at 都存在
    （production 今天唯一會發生的情況），兩張表窄查詢 UNION 後只出現
    一次。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"contracts": []})
    storage.save_result(ResultRecord("s1", "2026-08-02T00:00:00+00:00", {"n": 2}))
    storage.save_snapshot("s1", "2026-08-02T00:00:00+00:00", {"contracts": []})

    assert storage.result_timestamps("s1") == [
        "2026-08-01T00:00:00+00:00", "2026-08-02T00:00:00+00:00"]


def test_result_timestamps_falls_back_to_results_when_snapshot_is_missing(storage):
    """AC-2：`api_app/main.py::_refresh_and_save()` 對 `save_result()`／
    `save_snapshot()` 是兩次獨立呼叫、未包在同一個交易裡——中途中斷
    會留下一筆有 `results` 沒有 `snapshots` 的孤兒列。只讀
    `snapshots` 的話，這次分析的時間戳會從歷史索引裡憑空消失；本測試
    直接構造這個孤兒情境，證明它不會被靜默丟掉。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    # 刻意不呼叫 save_snapshot——模擬兩次寫入之間中斷的孤兒列。
    storage.save_result(ResultRecord("s1", "2026-08-02T00:00:00+00:00", {"n": 2}))
    storage.save_snapshot("s1", "2026-08-02T00:00:00+00:00", {"contracts": []})

    assert storage.result_timestamps("s1") == [
        "2026-08-01T00:00:00+00:00", "2026-08-02T00:00:00+00:00"]


def test_result_timestamps_also_covers_a_snapshot_without_a_result_row(storage):
    """對稱情況：只有 `snapshots`、沒有 `results`（同一種中斷情境，
    另一半沒寫成）——UNION 兩邊都要覆蓋，不是只補其中一個方向。"""
    storage.create_scenario(_scenario())
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"contracts": []})

    assert storage.result_timestamps("s1") == ["2026-08-01T00:00:00+00:00"]


def test_result_timestamps_does_not_duplicate_when_both_tables_agree(storage):
    """UNION 本身會去重——同一個時間戳兩邊都有時只回一次，不需要額外
    的 DISTINCT。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"contracts": []})

    assert storage.result_timestamps("s1") == ["2026-08-01T00:00:00+00:00"]


def test_result_timestamps_does_not_leak_across_scenarios(storage):
    storage.create_scenario(_scenario("s1"))
    storage.create_scenario(_scenario("s2", symbol="SPY"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"contracts": []})
    storage.save_result(ResultRecord("s2", "2026-08-02T00:00:00+00:00", {"n": 2}))
    storage.save_snapshot("s2", "2026-08-02T00:00:00+00:00", {"contracts": []})

    assert storage.result_timestamps("s1") == ["2026-08-01T00:00:00+00:00"]
    assert storage.result_timestamps("s2") == ["2026-08-02T00:00:00+00:00"]


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


# ---------- 配息資料快取（#123，per-symbol） ----------
#
# 與利率曲線快取同一套三態設計（成功／失敗皆留得住狀態），差異只在
# **鍵是 symbol**——q 是標的的性質，不是全站單一值，一個劇本抓 TLT
# 不該覆蓋另一個劇本抓 SPY 的快取。


def test_dividend_cache_starts_empty(storage):
    assert storage.get_dividend_cache("TLT") is None


def test_dividend_cache_roundtrips_a_successful_fetch(storage):
    entry = DividendCacheEntry(
        symbol="TLT", fetched_at="2026-08-10T12:00:00+00:00",
        history={"symbol": "TLT", "as_of": "2026-08-10", "source": "yahoo",
                "distributions": [["2026-08-03", 0.33]], "stale": False},
        note="配息資料 yahoo（2026-08-10，1 筆）")
    storage.save_dividend_cache(entry)
    assert storage.get_dividend_cache("TLT") == entry


def test_dividend_cache_roundtrips_market_day_and_attempted_day(storage):
    entry = DividendCacheEntry(
        symbol="TLT", fetched_at="2026-08-10T12:00:00+00:00",
        history={"symbol": "TLT", "as_of": "2026-08-10", "source": "yahoo",
                "distributions": [], "stale": False},
        note="配息資料 yahoo（2026-08-10，0 筆）",
        market_day="2026-08-10", attempted_day="2026-08-10")
    storage.save_dividend_cache(entry)
    assert storage.get_dividend_cache("TLT") == entry


def test_dividend_cache_can_record_a_failed_attempt(storage):
    entry = DividendCacheEntry(symbol="TLT", fetched_at="2026-08-10T12:00:00+00:00",
                               history=None, note="配息資料不可得")
    storage.save_dividend_cache(entry)
    assert storage.get_dividend_cache("TLT") == entry


def test_dividend_cache_overwrites_rather_than_accumulates(storage):
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT", fetched_at="2026-08-10T00:00:00+00:00",
        history=None, note="配息資料不可得"))
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT", fetched_at="2026-08-10T06:00:00+00:00",
        history={"symbol": "TLT", "as_of": "2026-08-10", "source": "yahoo",
                "distributions": [["2026-08-03", 0.33]], "stale": False},
        note="配息資料 yahoo（2026-08-10，1 筆）"))

    entry = storage.get_dividend_cache("TLT")
    assert entry.fetched_at == "2026-08-10T06:00:00+00:00"
    assert entry.history["source"] == "yahoo"


def test_dividend_cache_does_not_leak_across_symbols(storage):
    """核心不變量：per-symbol 鍵，不是單一全站狀態（跟 rate_cache 的
    差異就在這裡）。"""
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="TLT", fetched_at="2026-08-10T00:00:00+00:00",
        history={"symbol": "TLT", "as_of": "2026-08-10", "source": "yahoo",
                "distributions": [["2026-08-03", 0.33]], "stale": False},
        note="TLT"))
    storage.save_dividend_cache(DividendCacheEntry(
        symbol="SPY", fetched_at="2026-08-10T00:00:00+00:00",
        history=None, note="SPY 配息資料不可得"))

    assert storage.get_dividend_cache("TLT").history["symbol"] == "TLT"
    assert storage.get_dividend_cache("SPY").history is None
    assert storage.get_dividend_cache("SPY").note == "SPY 配息資料不可得"


# ---------- Treasury 曲線列快取（PERF-03／#179，per-year） ----------

def test_treasury_year_cache_starts_empty(storage):
    assert storage.get_treasury_year_cache(2026) is None


def test_treasury_year_cache_roundtrips_a_successful_fetch(storage):
    entry = TreasuryYearCacheEntry(
        year=2026, fetched_at="2026-08-10T12:00:00+00:00",
        rows=[["2026-01-01", [[1.0, 0.041], [30.0, 0.043]]]],
        note="Treasury 2026 年曲線（1 個交易日）")
    storage.save_treasury_year_cache(entry)
    assert storage.get_treasury_year_cache(2026) == entry


def test_treasury_year_cache_roundtrips_market_day_and_attempted_day(storage):
    entry = TreasuryYearCacheEntry(
        year=2026, fetched_at="2026-08-10T12:00:00+00:00",
        rows=[["2026-01-01", [[1.0, 0.041]]]],
        note="Treasury 2026 年曲線",
        market_day="2026-08-10", attempted_day="2026-08-10")
    storage.save_treasury_year_cache(entry)
    assert storage.get_treasury_year_cache(2026) == entry


def test_treasury_year_cache_can_record_a_failed_attempt(storage):
    entry = TreasuryYearCacheEntry(year=2026, fetched_at="2026-08-10T12:00:00+00:00",
                                   rows=None, note="Treasury 曲線不可得")
    storage.save_treasury_year_cache(entry)
    assert storage.get_treasury_year_cache(2026) == entry


def test_treasury_year_cache_overwrites_rather_than_accumulates(storage):
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026, fetched_at="2026-08-10T00:00:00+00:00",
        rows=None, note="Treasury 曲線不可得"))
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026, fetched_at="2026-08-10T06:00:00+00:00",
        rows=[["2026-01-01", [[1.0, 0.041]]]],
        note="Treasury 2026 年曲線（1 個交易日）"))

    entry = storage.get_treasury_year_cache(2026)
    assert entry.fetched_at == "2026-08-10T06:00:00+00:00"
    assert entry.rows == [["2026-01-01", [[1.0, 0.041]]]]


def test_treasury_year_cache_does_not_leak_across_years(storage):
    """核心不變量（PIT 安全）：per-year 鍵，一個年份的紀錄不該覆蓋或
    污染另一個年份——這是本票存在的理由本身，不是順手測一下。"""
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2025, fetched_at="2026-08-10T00:00:00+00:00",
        rows=[["2025-01-01", [[1.0, 0.0111]]]], note="2025"))
    storage.save_treasury_year_cache(TreasuryYearCacheEntry(
        year=2026, fetched_at="2026-08-10T00:00:00+00:00",
        rows=None, note="2026 不可得"))

    assert storage.get_treasury_year_cache(2025).rows == [["2025-01-01", [[1.0, 0.0111]]]]
    assert storage.get_treasury_year_cache(2026).rows is None
    assert storage.get_treasury_year_cache(2026).note == "2026 不可得"


# ---------- Chain 429 backoff（SCALE-04／#255，provider-global） ----------

def test_chain_backoff_starts_empty(storage):
    assert storage.get_chain_backoff("cboe") is None


def test_chain_backoff_roundtrips_a_blocked_state(storage):
    entry = ChainBackoffEntry(
        source="cboe", blocked_until="2026-09-06T12:01:00+00:00",
        retry_after_seconds=34.0, consecutive_failures=1,
        observed_at="2026-09-06T12:00:00+00:00", last_success_at=None)
    storage.save_chain_backoff(entry)
    assert storage.get_chain_backoff("cboe") == entry


def test_chain_backoff_roundtrips_a_cleared_state(storage):
    entry = ChainBackoffEntry(
        source="cboe", blocked_until=None, retry_after_seconds=None,
        consecutive_failures=0, observed_at="2026-09-06T12:00:00+00:00",
        last_success_at="2026-09-06T12:00:00+00:00")
    storage.save_chain_backoff(entry)
    assert storage.get_chain_backoff("cboe") == entry


def test_chain_backoff_overwrites_rather_than_accumulates(storage):
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until="2026-09-06T12:01:00+00:00",
        retry_after_seconds=34.0, consecutive_failures=1,
        observed_at="2026-09-06T12:00:00+00:00", last_success_at=None))
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until=None, retry_after_seconds=None,
        consecutive_failures=0, observed_at="2026-09-06T12:05:00+00:00",
        last_success_at="2026-09-06T12:05:00+00:00"))

    entry = storage.get_chain_backoff("cboe")
    assert entry.blocked_until is None
    assert entry.consecutive_failures == 0


def test_chain_backoff_does_not_leak_across_sources(storage):
    """核心不變量（provider-global 鍵本身存在的理由）：不同 source
    各自獨立，一個 source 被限流不影響另一個。"""
    storage.save_chain_backoff(ChainBackoffEntry(
        source="cboe", blocked_until="2026-09-06T12:01:00+00:00",
        retry_after_seconds=34.0, consecutive_failures=1,
        observed_at="2026-09-06T12:00:00+00:00", last_success_at=None))

    assert storage.get_chain_backoff("yfinance") is None


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


# ---------- per-family 代表候選（T07／#224，Initial V2） ----------

_PER_FAMILY = {
    "vertical-spread": _REP,
    "single-leg": {"strategy": "long-call",
                  "legs": [{"strike": 110.0, "option_type": "call", "side": "buy"}],
                  "expiry": "2028-05-19", "baseline_return": 0.9},
}


def test_per_family_survives_the_result_roundtrip(storage):
    """與 `representative_candidate` 同一個模式：規則只有一份
    （`store.representative_candidates_by_family`），這裡只是落盤結果
    要能存得進、讀得回，含 `latest_result`／`result_history` 兩個
    讀取路徑，形狀不失真。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP,
        per_family=_PER_FAMILY))
    assert storage.latest_result("s1").per_family == _PER_FAMILY
    assert storage.result_history("s1")[0].per_family == _PER_FAMILY


def test_per_family_defaults_to_none(storage):
    """舊結果紀錄（本票之前寫入的、或本票之後但分析當下沒有 baseline
    期可比的）讀回來是 `None`，不是一個編出來的空 dict——`ResultRecord`
    的預設值本身就是 `None`，既有行為不受影響。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, best_return=None))
    assert storage.latest_result("s1").per_family is None


# ---------- 歷史 fact context（SCALE-01／#252，Scaling Foundation） ----------

_FACT_PARAMS = {"target_price": 120.0, "target_month": "2026-08"}


def test_result_fact_fields_survive_the_roundtrip(storage):
    """與 `per_family`／`representative_candidate` 同一個模式：規則只有
    一份（`option_chaser.store.historical_fact_context()`），這裡只是
    落盤結果要能存得進、讀得回，含 `latest_result`／`result_history`
    兩個讀取路徑，形狀不失真（尤其 `requested_strategies` 讀回仍是
    tuple，不是 JSONB 給的 list）。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        resolved_params=_FACT_PARAMS,
        requested_strategies=("long-call", "bull-call-spread"),
        engine_version="0.5.0", view_schema_version=9,
        history_replay_version=1, snapshot_source="cboe"))

    for rec in (storage.latest_result("s1"), storage.result_history("s1")[0]):
        assert rec.resolved_params == _FACT_PARAMS
        assert rec.requested_strategies == ("long-call", "bull-call-spread")
        assert isinstance(rec.requested_strategies, tuple)
        assert rec.engine_version == "0.5.0"
        assert rec.view_schema_version == 9
        assert rec.history_replay_version == 1
        assert rec.snapshot_source == "cboe"


def test_result_fact_fields_default_to_none(storage):
    """既有部署的舊列（本票之前寫入的）讀回來全部是 `None`——backfill
    腳本負責補齊，讀取端在那之前必須容忍這個狀態。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}))
    rec = storage.latest_result("s1")
    assert rec.resolved_params is None
    assert rec.requested_strategies is None
    assert rec.engine_version is None
    assert rec.view_schema_version is None
    assert rec.history_replay_version is None
    assert rec.snapshot_source is None


def test_result_fact_context_is_a_narrow_projection_of_the_same_row(storage):
    """AC-1：一個窄查詢就能取得完整 resolved params／analysis
    context／provenance／engine-schema-replay version，不需要
    `latest_result()`／`result_history()` 那種連 `view` 一起撈的
    寬查詢。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        resolved_params=_FACT_PARAMS,
        requested_strategies=("long-call",),
        engine_version="0.5.0", view_schema_version=9,
        history_replay_version=1, snapshot_source="cboe"))

    ctx = storage.result_fact_context("s1", "2026-08-01T00:00:00+00:00")

    assert ctx.scenario_id == "s1"
    assert ctx.analyzed_at == "2026-08-01T00:00:00+00:00"
    assert ctx.resolved_params == _FACT_PARAMS
    assert ctx.requested_strategies == ("long-call",)
    assert ctx.engine_version == "0.5.0"
    assert ctx.view_schema_version == 9
    assert ctx.history_replay_version == 1
    assert ctx.snapshot_source == "cboe"


def test_result_fact_context_is_none_for_a_missing_row(storage):
    storage.create_scenario(_scenario("s1"))
    assert storage.result_fact_context(
        "s1", "2099-01-01T00:00:00+00:00") is None


def test_result_fact_context_does_not_leak_across_scenarios(storage):
    storage.create_scenario(_scenario("s1"))
    storage.create_scenario(_scenario("s2", symbol="SPY"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        resolved_params=_FACT_PARAMS,
        requested_strategies=("long-call",), engine_version="0.5.0",
        view_schema_version=9, history_replay_version=1,
        snapshot_source="cboe"))

    assert storage.result_fact_context(
        "s2", "2026-08-01T00:00:00+00:00") is None


def test_latest_summaries_carries_per_family(storage):
    """清單查詢一併帶著 per-family map——本輪 UI 不消費它，但落盤與
    讀取路徑必須先接通，日後才可能零遷移切換顯示面。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP,
        per_family=_PER_FAMILY))
    assert storage.latest_summaries()["s1"].per_family == _PER_FAMILY


# ---------- family_eligibility（T10／#227，Initial V2） ----------

_FAMILY_ELIGIBILITY = {
    "single-leg": {"family": "single-leg", "eligible": True, "reason": None},
    "vertical-spread": {"family": "vertical-spread", "eligible": True,
                        "reason": None},
    "butterfly": {"family": "butterfly", "eligible": False,
                 "reason": "這個策略家族目前還沒有任何已啟用的具體結構。"},
}


def test_family_eligibility_survives_the_result_roundtrip(storage):
    """與 `per_family` 同一個模式：規則只有一份
    （`store._family_eligibility_map`），這裡只是落盤結果要能存得進、
    讀得回，含 `latest_result`／`result_history` 兩個讀取路徑。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP,
        family_eligibility=_FAMILY_ELIGIBILITY))
    assert storage.latest_result("s1").family_eligibility == _FAMILY_ELIGIBILITY
    assert storage.result_history("s1")[0].family_eligibility == _FAMILY_ELIGIBILITY


def test_family_eligibility_defaults_to_none(storage):
    """舊結果紀錄（本票之前寫入的）讀回來是 `None`，不是假造一份
    「全部可選」的 verdict。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, best_return=None))
    assert storage.latest_result("s1").family_eligibility is None


def test_latest_summaries_carries_family_eligibility(storage):
    """清單查詢一併帶著 family_eligibility——編輯表單開啟時讀這裡，
    不打 detail 端點。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_result(ResultRecord(
        "s1", "2026-08-01T00:00:00+00:00", {"n": 1},
        best_return=1.25, representative_candidate=_REP,
        family_eligibility=_FAMILY_ELIGIBILITY))
    assert storage.latest_summaries()["s1"].family_eligibility == _FAMILY_ELIGIBILITY


# ---------- 資料源設定與 credential（Settings／#124） ----------

_CUSTOM = UsageSetting(mode="custom", provider="marketdata-app")
_DEFAULT_USAGE = UsageSetting(mode="default", provider=None)


def _settings(market=_CUSTOM, iv=_DEFAULT_USAGE):
    return DataSourceSettings(market_data=market, historical_iv=iv,
                              updated_at="2026-08-12T00:00:00+00:00")


def test_settings_start_out_unset(storage):
    """從未存過＝`None`，不是一個假的空設定——呼叫端據此用預設值。"""
    assert storage.get_settings() is None


def test_saved_settings_read_back_identically(storage):
    storage.save_settings(_settings())
    assert storage.get_settings() == _settings()


def test_saving_settings_again_overwrites_the_single_row(storage):
    storage.save_settings(_settings())
    storage.save_settings(_settings(market=_DEFAULT_USAGE, iv=_CUSTOM))
    got = storage.get_settings()
    assert got.market_data == _DEFAULT_USAGE
    assert got.historical_iv == _CUSTOM


def test_credentials_start_out_absent(storage):
    assert storage.get_credential("marketdata-app") is None


def test_saved_credential_reads_back_in_full(storage):
    """遮罩是 API 回應層的事；儲存層必須保住完整 token，否則 #125 的
    測試連線就沒有東西可用。"""
    cred = ProviderCredential(provider="marketdata-app", token="tok-abcd1234",
                              updated_at="2026-08-12T00:00:00+00:00")
    storage.save_credential(cred)
    assert storage.get_credential("marketdata-app") == cred


def test_saving_a_credential_again_replaces_the_token(storage):
    for token in ("first-0000", "second-1111"):
        storage.save_credential(ProviderCredential(
            provider="marketdata-app", token=token,
            updated_at="2026-08-12T00:00:00+00:00"))
    assert storage.get_credential("marketdata-app").token == "second-1111"


def test_credentials_are_keyed_by_provider_and_do_not_collide(storage):
    """一個 Provider 一把——這正是兩個資料用途能共用同一把的原因。"""
    for pid in ("marketdata-app", "another-vendor"):
        storage.save_credential(ProviderCredential(
            provider=pid, token=f"tok-{pid}",
            updated_at="2026-08-12T00:00:00+00:00"))
    assert storage.get_credential("marketdata-app").token == "tok-marketdata-app"
    assert storage.get_credential("another-vendor").token == "tok-another-vendor"


def test_deleting_a_credential_reports_whether_it_removed_anything(storage):
    storage.save_credential(ProviderCredential(
        provider="marketdata-app", token="tok",
        updated_at="2026-08-12T00:00:00+00:00"))
    assert storage.delete_credential("marketdata-app") is True
    assert storage.delete_credential("marketdata-app") is False
    assert storage.get_credential("marketdata-app") is None


def test_deleting_one_credential_leaves_the_others_alone(storage):
    for pid in ("marketdata-app", "another-vendor"):
        storage.save_credential(ProviderCredential(
            provider=pid, token="tok", updated_at="2026-08-12T00:00:00+00:00"))
    storage.delete_credential("marketdata-app")
    assert storage.get_credential("another-vendor") is not None


def test_deleting_a_credential_leaves_the_settings_alone(storage):
    """清 token 不等於改設定——使用者可能只是要換一把。"""
    storage.save_settings(_settings())
    storage.save_credential(ProviderCredential(
        provider="marketdata-app", token="tok",
        updated_at="2026-08-12T00:00:00+00:00"))
    storage.delete_credential("marketdata-app")
    assert storage.get_settings() == _settings()


# ---------- 測試連線的結果（Settings／#125） ----------

def _verification(ok=True, reason=None):
    return ProviderVerification(provider="marketdata-app", ok=ok, reason=reason,
                                checked_at="2026-08-12T01:00:00+00:00")


def test_verification_starts_out_absent(storage):
    assert storage.get_verification("marketdata-app") is None


def test_saved_verification_reads_back_identically(storage):
    v = _verification(ok=False, reason="認證被拒")
    storage.save_verification(v)
    assert storage.get_verification("marketdata-app") == v


def test_retesting_overwrites_the_previous_result(storage):
    storage.save_verification(_verification(ok=False, reason="連不上"))
    storage.save_verification(_verification(ok=True))
    got = storage.get_verification("marketdata-app")
    assert got.ok is True and got.reason is None


def test_deleting_the_credential_also_drops_its_verification(storage):
    """驗證結果講的是「那把 token 能不能用」——token 沒了它就失去意義，
    留著會讓設定頁在沒有 credential 的情況下顯示「已連線」。"""
    storage.save_credential(ProviderCredential(
        provider="marketdata-app", token="tok",
        updated_at="2026-08-12T00:00:00+00:00"))
    storage.save_verification(_verification())
    storage.delete_credential("marketdata-app")
    assert storage.get_verification("marketdata-app") is None


def test_saving_a_credential_does_not_invent_a_verification(storage):
    """存 token 不等於測過——設定頁據此顯示「尚未驗證」而不是「已連線」。"""
    storage.save_credential(ProviderCredential(
        provider="marketdata-app", token="tok",
        updated_at="2026-08-12T00:00:00+00:00"))
    assert storage.get_verification("marketdata-app") is None


# ---------- 歷史 IV 觀測快取（#129，per-symbol） ----------

def _obs(symbol="TLT", on="2026-05-04", iv=0.2):
    return IvObservation(symbol=symbol, observed_on=on,
                         surface={"call": [[30, 0.5, iv]], "put": []},
                         fetched_at="2026-08-12T00:00:00+00:00")


def test_a_symbol_starts_with_no_observations(storage):
    assert storage.iv_observation_dates("TLT") == []
    assert storage.iv_observations("TLT") == []


def test_saved_observation_reads_back_identically(storage):
    storage.save_iv_observation(_obs())
    assert storage.iv_observations("TLT") == [_obs()]


def test_observations_come_back_in_date_order(storage):
    for on in ("2026-06-01", "2026-04-01", "2026-05-01"):
        storage.save_iv_observation(_obs(on=on))
    assert [o.observed_on for o in storage.iv_observations("TLT")] == [
        "2026-04-01", "2026-05-01", "2026-06-01"]


def test_rewriting_the_same_day_overwrites_rather_than_duplicates(storage):
    storage.save_iv_observation(_obs(iv=0.2))
    storage.save_iv_observation(_obs(iv=0.9))
    got = storage.iv_observations("TLT")
    assert len(got) == 1
    assert got[0].surface["call"][0][2] == 0.9


def test_dates_query_does_not_need_the_surfaces(storage):
    """backfill 只需要知道還缺哪幾天——為此把數十天的曲面整包撈出來是
    離譜的浪費，所以這是一支獨立查詢。"""
    for on in ("2026-05-04", "2026-05-11"):
        storage.save_iv_observation(_obs(on=on))
    assert storage.iv_observation_dates("TLT") == ["2026-05-04", "2026-05-11"]


def test_symbols_do_not_bleed_into_each_other(storage):
    storage.save_iv_observation(_obs(symbol="TLT"))
    storage.save_iv_observation(_obs(symbol="SPY"))
    assert storage.iv_observation_dates("TLT") == ["2026-05-04"]
    assert storage.iv_observation_dates("SPY") == ["2026-05-04"]
    assert storage.iv_observations("TLT")[0].symbol == "TLT"


def test_the_cache_carries_no_scenario_identity(storage):
    """同一 ticker 的所有 Scenario 共用同一份——資料模型上就不可能因
    scenario 不同而分家、重複燒 vendor 額度。"""
    storage.save_iv_observation(_obs())
    assert not hasattr(_obs(), "scenario_id")
    # 兩個不同劇本讀到的是同一筆
    for sid in ("s1", "s2"):
        storage.create_scenario(_scenario(sid))
    assert storage.iv_observations("TLT") == storage.iv_observations("TLT")


def test_deleting_a_scenario_keeps_the_symbol_cache(storage):
    """別的劇本還在用，而且重抓要再燒一次 quota。"""
    storage.create_scenario(_scenario("s1"))
    storage.save_iv_observation(_obs())
    storage.archive_scenario("s1", ts="2026-08-12T00:00:00+00:00")
    assert storage.delete_scenario("s1") is True
    assert storage.iv_observation_dates("TLT") == ["2026-05-04"]


def test_backfill_run_starts_absent(storage):
    assert storage.get_iv_backfill_run("TLT") is None


def test_backfill_run_reads_back_and_overwrites(storage):
    storage.save_iv_backfill_run(IvBackfillRun("TLT", "2026-08-11", "quota", "額度"))
    storage.save_iv_backfill_run(IvBackfillRun("TLT", "2026-08-12", "ok", None))
    got = storage.get_iv_backfill_run("TLT")
    assert (got.ran_on, got.outcome, got.note) == ("2026-08-12", "ok", None)


def test_backfill_runs_are_per_symbol(storage):
    storage.save_iv_backfill_run(IvBackfillRun("TLT", "2026-08-12", "ok"))
    assert storage.get_iv_backfill_run("SPY") is None


# ---------- Exact-contract 歷史 IV 快取（HIVT-02／#153，寬版欄位
# HIVR-04／#163） ----------

def _quote(date, vendor_iv, *, updated=1782763200, dte=800.0, bid=1.5,
          ask=6.5, mid=4.0, underlying_price=84.5):
    """一筆寬版 quote dict（HIVR-04／#163 起的 `ContractHistory.points`
    形狀）——欄位齊全才能同時驗證「儲存層原樣往返」與「舊格式列可辨識」
    兩件事。"""
    return {"date": date, "updated": updated, "dte": dte, "bid": bid,
           "ask": ask, "mid": mid, "underlying_price": underlying_price,
           "vendor_iv": vendor_iv}


def _contract_history(symbol="TLT281215C00094000",
                      points=None,
                      fetched_through="2026-08-17",
                      last_attempt_on="2026-08-17", last_status="ok",
                      last_note=None):
    if points is None:
        points = (_quote("2026-06-29", None), _quote("2026-07-01", 0.185))
    return ContractHistory(contract_symbol=symbol, points=tuple(points),
                           fetched_through=fetched_through,
                           last_attempt_on=last_attempt_on,
                           last_status=last_status, last_note=last_note)


def test_a_contract_starts_with_no_cached_history(storage):
    assert storage.get_contract_history("TLT281215C00094000") is None


def test_saved_contract_history_reads_back_identically(storage):
    storage.save_contract_history(_contract_history())
    assert storage.get_contract_history("TLT281215C00094000") == _contract_history()


def test_saved_quote_retains_every_reconstruction_field(storage):
    """HIVR-04（#163）AC：storage 要能存回並讀出寬版欄位（不只
    date／vendor_iv），reconstruction（#164）才有東西可用。"""
    storage.save_contract_history(_contract_history(
        points=(_quote("2026-07-01", 0.185, updated=1782936000, dte=799.0,
                       bid=2.56, ask=3.7, mid=3.13, underlying_price=84.7),)))
    got = storage.get_contract_history("TLT281215C00094000")
    q = got.points[0]
    assert q["date"] == "2026-07-01"
    assert q["updated"] == 1782936000
    assert q["dte"] == 799.0
    assert q["bid"] == 2.56
    assert q["ask"] == 3.7
    assert q["mid"] == 3.13
    assert q["underlying_price"] == 84.7
    assert q["vendor_iv"] == 0.185


def test_rewriting_the_same_contract_overwrites_rather_than_duplicates(storage):
    storage.save_contract_history(_contract_history(
        points=(_quote("2026-07-01", 0.1),)))
    storage.save_contract_history(_contract_history(
        points=(_quote("2026-07-01", 0.1), _quote("2026-07-02", 0.2)),
        fetched_through="2026-08-18", last_attempt_on="2026-08-18"))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.points == (_quote("2026-07-01", 0.1), _quote("2026-07-02", 0.2))
    assert got.fetched_through == "2026-08-18"


def test_null_iv_points_round_trip_as_none(storage):
    storage.save_contract_history(_contract_history(
        points=(_quote("2026-06-29", None), _quote("2026-07-01", 0.185))))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.points[0]["date"] == "2026-06-29"
    assert got.points[0]["vendor_iv"] is None
    assert got.points[1]["date"] == "2026-07-01"
    assert got.points[1]["vendor_iv"] == 0.185


def test_contracts_do_not_bleed_into_each_other(storage):
    """不同 strike／expiry／call-put 是不同的 OCC symbol，天然是不同的
    快取項目——這正是 exact contract identity 的紅線本身。"""
    storage.save_contract_history(_contract_history(symbol="TLT281215C00094000"))
    storage.save_contract_history(_contract_history(
        symbol="TLT281215C00100000", points=(_quote("2026-07-01", 0.3),)))
    a = storage.get_contract_history("TLT281215C00094000")
    b = storage.get_contract_history("TLT281215C00100000")
    assert a.points != b.points
    assert b.points == (_quote("2026-07-01", 0.3),)


def test_never_successfully_fetched_history_has_no_fetched_through(storage):
    storage.save_contract_history(_contract_history(
        points=(), fetched_through=None, last_status="vendor",
        last_note="連線失敗"))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.fetched_through is None
    assert got.points == ()
    assert got.last_status == "vendor"


def test_an_old_shape_date_iv_tuple_row_is_structurally_distinguishable(storage):
    """HIVR-04（#163）AC：HIVT-02 時代的舊格式列是 `(date, iv)` 二元組
    （沒有欄位名），新格式是 dict——storage 本身是啞的 port、不解讀
    形狀，只需要如實往返，讓呼叫端（`api_app/main.py`）能用
    `isinstance(points[0], dict)` 分辨。這裡驗證的是「storage 忠實
    保存了舊格式的原始樣貌，沒有把它悄悄轉型成看起來像新格式」。"""
    storage.save_contract_history(ContractHistory(
        contract_symbol="TLT281215C00094000",
        points=(("2026-06-29", None), ("2026-07-01", 0.185)),
        fetched_through="2026-08-17", last_attempt_on="2026-08-17",
        last_status="ok", last_note=None))
    got = storage.get_contract_history("TLT281215C00094000")
    assert not isinstance(got.points[0], dict)


# ---------- Application diagnostics（DG-02／#145） ----------

def _diag(*, event_id="e1", correlation_id="c1", ts="2026-08-15T00:00:00+00:00",
         subsystem="historical_iv", stage="vendor_fetch", severity="error",
         user_facing=None, message="boom", context=None, owner_id=None):
    # PC-03（#201）：`user_facing` 省略時鏡射 `severity`——跟 `emit()`
    # 的預設規則同一套，這裡直接構造 `DiagnosticEvent`（繞過 `emit()`）
    # 因此要自己套一次，不然這批既有測試全部要逐一補這個新欄位。
    if user_facing is None:
        user_facing = severity in ("warning", "error")
    return DiagnosticEvent(event_id=event_id, correlation_id=correlation_id,
                           ts=ts, subsystem=subsystem, stage=stage,
                           severity=severity, user_facing=user_facing,
                           message=message, context=context or {},
                           owner_id=owner_id)


def test_diagnostics_start_out_empty(storage):
    assert storage.list_diagnostics() == []


def test_appended_diagnostic_reads_back_identically(storage):
    storage.append_diagnostic(_diag(context={"symbol": "TLT"}))
    got = storage.list_diagnostics()
    assert len(got) == 1
    assert got[0].event_id == "e1"
    assert got[0].correlation_id == "c1"
    assert got[0].subsystem == "historical_iv"
    assert got[0].stage == "vendor_fetch"
    assert got[0].severity == "error"
    assert got[0].message == "boom"
    assert got[0].context == {"symbol": "TLT"}


def test_diagnostic_user_facing_round_trips_for_both_true_and_false(storage):
    """PC-03（#201）：`user_facing` 是獨立於 `severity` 的欄位——存 True
    讀回 True、存 False 讀回 False，兩個布林值都要能存活過 round-trip，
    不能只驗其中一個方向（例如剛好都是 truthy 就測不出 Postgres 那端
    欄位型別／讀取邏輯搞錯的情況）。"""
    storage.append_diagnostic(_diag(event_id="t1", severity="warning",
                                    user_facing=True))
    storage.append_diagnostic(_diag(event_id="t2", severity="warning",
                                    user_facing=False))
    got = {e.event_id: e.user_facing for e in storage.list_diagnostics()}
    assert got == {"t1": True, "t2": False}


def test_diagnostics_come_back_newest_first(storage):
    for i in range(3):
        storage.append_diagnostic(_diag(event_id=f"e{i}",
                                        ts=f"2026-08-15T00:0{i}:00+00:00"))
    assert [e.event_id for e in storage.list_diagnostics()] == ["e2", "e1", "e0"]


def test_diagnostics_list_respects_the_limit(storage):
    for i in range(5):
        storage.append_diagnostic(_diag(event_id=f"e{i}"))
    got = storage.list_diagnostics(limit=2)
    assert len(got) == 2
    assert got[0].event_id == "e4"


def test_clear_diagnostics_empties_the_list_and_reports_the_count(storage):
    for i in range(3):
        storage.append_diagnostic(_diag(event_id=f"e{i}"))
    n = storage.clear_diagnostics()
    assert n == 3
    assert storage.list_diagnostics() == []


def test_clear_diagnostics_on_an_empty_store_reports_zero(storage):
    assert storage.clear_diagnostics() == 0


def test_diagnostics_retention_is_capped_globally(storage):
    """trim-on-write：寫超過上限後，最舊的被淘汰、最新的都在、總數不
    超過上限——兩個實作在這裡必須是同一個行為。"""
    total = RETENTION_LIMIT + 20
    for i in range(total):
        storage.append_diagnostic(_diag(event_id=f"e{i}"))
    got = storage.list_diagnostics(limit=RETENTION_LIMIT + 50)
    assert len(got) == RETENTION_LIMIT
    # 最新的一筆（最後寫入）在最上，最舊的那 20 筆被擠掉。
    assert got[0].event_id == f"e{total - 1}"
    kept_ids = {e.event_id for e in got}
    assert f"e{total - 1}" in kept_ids
    assert "e0" not in kept_ids
    assert "e19" not in kept_ids
    assert "e20" in kept_ids


def test_append_diagnostics_batch_writes_all_events(storage):
    """PERF-02（#178）：複數形式的批次寫入，跟逐筆呼叫單筆版並存、
    不取代——這裡驗證批次版本身就能把整批寫進去、讀得回來。"""
    events = [_diag(event_id=f"b{i}", ts=f"2026-08-15T00:0{i}:00+00:00")
             for i in range(3)]
    storage.append_diagnostics(events)
    got = {e.event_id for e in storage.list_diagnostics(limit=10)}
    assert got == {"b0", "b1", "b2"}


def test_append_diagnostics_on_an_empty_list_is_a_no_op(storage):
    storage.append_diagnostics([])
    assert storage.list_diagnostics() == []


def test_append_diagnostics_batch_matches_looping_the_singular_method_on_retention(storage):
    """核心不變量：批次寫入與逐筆寫入在 trim-on-write 上必須產生完全
    一致的最終保留集合——不是「差不多」，是同一組 event_id、同一個
    順序。用兩個獨立的 storage 實例分別跑批次版／逐筆版，比對最終
    狀態。"""
    total = RETENTION_LIMIT + 20
    events = [_diag(event_id=f"e{i}", ts=f"t{i}") for i in range(total)]

    storage.append_diagnostics(events)
    batch_result = [(e.event_id, e.ts) for e in storage.list_diagnostics(
        limit=RETENTION_LIMIT + 50)]

    looped = MemoryStorage()
    for event in events:
        looped.append_diagnostic(event)
    looped_result = [(e.event_id, e.ts) for e in looped.list_diagnostics(
        limit=RETENTION_LIMIT + 50)]

    assert batch_result == looped_result


# ---------- Ownership A-1 Expand（SCALE-06／#256） ----------
#
# 只涵蓋 5 張 row-scoped 表——`provider_credentials`／
# `data_source_settings`／`provider_verifications` 三張 singleton／
# provider-key 表刻意不在這裡（留給 SCALE-13 做結構遷移），
# system-wide 共用表（rate/treasury/dividend/IV caches、
# `chain_backoff`）本來就不該有這個維度，見下方 AC-5 結構性測試。

def test_owner_id_round_trips_on_a_scenario(storage):
    storage.create_scenario(_scenario())
    got = storage.get_scenario("s1")
    assert got.owner_id is None   # 未指定時 nullable，不是空字串
    storage.create_scenario(_scenario(sid="s2"))
    storage.get_scenario("s2")   # 冪等讀取不影響下面這筆的獨立驗證


def test_owner_id_can_be_set_when_creating_a_scenario(storage):
    from dataclasses import replace as _replace
    sc = _replace(_scenario(), owner_id="alice")
    storage.create_scenario(sc)
    assert storage.get_scenario("s1").owner_id == "alice"


def test_updating_a_scenario_does_not_touch_its_owner_id():
    """`update_scenario()` 刻意不動 `owner_id`——編輯 thesis 不該連帶
    改變資料 boundary。這是設計決策，用 memory 假體驗證一次即可（不是
    兩個後端各自獨立需要驗證的行為差異，是同一份呼叫慣例）。"""
    from dataclasses import replace as _replace
    storage = MemoryStorage()
    sc = _replace(_scenario(), owner_id="alice")
    storage.create_scenario(sc)
    updated = _replace(sc, notes="改過的 thesis")
    storage.update_scenario(updated)
    assert storage.get_scenario("s1").owner_id == "alice"


def test_owner_id_round_trips_on_a_result(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}, owner_id="alice"))
    assert storage.latest_result("s1").owner_id == "alice"


def test_owner_id_round_trips_on_a_snapshot(storage):
    storage.create_scenario(_scenario())
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"n": 1},
                          owner_id="alice")
    # 窄讀取不影響既有 `get_snapshot()` 的形狀——仍是純快照 dict，不是
    # 一個帶著 owner_id 的信封。
    assert storage.get_snapshot("s1", "2026-08-01T00:00:00+00:00") == {"n": 1}
    assert storage.get_snapshot_owner("s1", "2026-08-01T00:00:00+00:00") == "alice"


def test_snapshot_owner_is_none_when_unspecified_or_missing(storage):
    storage.create_scenario(_scenario())
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"n": 1})
    assert storage.get_snapshot_owner("s1", "2026-08-01T00:00:00+00:00") is None
    # 這一列根本不存在——跟「存在但 owner 尚未 backfill」用同一個 `None`
    # 表達（見 `Storage.get_snapshot_owner()` docstring 的理由）。
    assert storage.get_snapshot_owner("s1", "2099-01-01T00:00:00+00:00") is None


def test_owner_id_round_trips_on_an_event(storage):
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={}, owner_id="alice")
    (event,) = storage.list_events()
    assert event["owner_id"] == "alice"


def test_event_owner_id_defaults_to_none(storage):
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={})
    (event,) = storage.list_events()
    assert event["owner_id"] is None


def test_owner_id_round_trips_on_a_diagnostic(storage):
    storage.append_diagnostic(_diag(event_id="d1"))   # owner_id 預設 None
    assert storage.list_diagnostics()[0].owner_id is None
    storage.append_diagnostic(_diag(event_id="d2", owner_id="alice"))
    by_id = {e.event_id: e.owner_id for e in storage.list_diagnostics(limit=10)}
    assert by_id == {"d1": None, "d2": "alice"}


def test_backfill_missing_owner_ids_sets_solo_owner_on_every_legacy_row(storage):
    """AC-1／AC-2：5 張表各留一筆沒有 owner 的舊列，一次 backfill 全部
    補齊，回傳的計數逐表對得上。"""
    storage.create_scenario(_scenario())          # owner_id=None
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1}))    # owner_id=None
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"n": 1})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={})
    storage.append_diagnostic(_diag(event_id="d1"))

    counts = storage.backfill_missing_owner_ids("solo")
    assert counts == {"scenarios": 1, "results": 1, "snapshots": 1,
                      "events": 1, "diagnostics": 1}

    assert storage.get_scenario("s1").owner_id == "solo"
    assert storage.latest_result("s1").owner_id == "solo"
    assert storage.get_snapshot_owner("s1", "2026-08-01T00:00:00+00:00") == "solo"
    assert storage.list_events()[0]["owner_id"] == "solo"
    assert storage.list_diagnostics()[0].owner_id == "solo"


def test_backfill_missing_owner_ids_is_idempotent_on_rerun(storage):
    """AC-2：重跑 backfill 0 drift／0 duplicate side effect——第二次呼叫
    對「已經補過」的列全部回 0，不重複計數、不覆蓋。"""
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00", {"n": 1}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00", {"n": 1})
    storage.append_event(ts="2026-08-01T00:00:00+00:00", scenario_id="s1",
                         event="SCENARIO_CREATED", payload={})
    storage.append_diagnostic(_diag(event_id="d1"))

    first = storage.backfill_missing_owner_ids("solo")
    assert all(v == 1 for v in first.values())

    second = storage.backfill_missing_owner_ids("solo")
    assert second == {"scenarios": 0, "results": 0, "snapshots": 0,
                      "events": 0, "diagnostics": 0}

    # 結果不變——不是「回 0 但其實悄悄改了值」。
    assert storage.get_scenario("s1").owner_id == "solo"


def test_backfill_does_not_overwrite_a_row_that_already_has_an_owner(storage):
    """既有值有 owner 的列不該被覆蓋成 backfill 傳入的值——`WHERE
    owner_id IS NULL` 的條件式語意，不是無條件蓋掉。"""
    from dataclasses import replace as _replace

    storage.create_scenario(_replace(_scenario(), owner_id="alice"))
    counts = storage.backfill_missing_owner_ids("solo")
    assert counts["scenarios"] == 0
    assert storage.get_scenario("s1").owner_id == "alice"


def test_backfill_on_an_empty_store_reports_zero_for_every_table(storage):
    counts = storage.backfill_missing_owner_ids("solo")
    assert counts == {"scenarios": 0, "results": 0, "snapshots": 0,
                      "events": 0, "diagnostics": 0}


# ---------- AC-5：結構性——3 張 singleton 表與 system-wide 表零 owner ----------

def test_singleton_and_system_wide_dataclasses_have_no_owner_field():
    """SCALE-06 明文範圍界線：3 張 singleton／provider-key user 表
    （留給 SCALE-13 做結構遷移）與全部 system-wide 共用表（rate／
    treasury／dividend／IV caches、`chain_backoff`）都不該在這一票
    悄悄長出 `owner_id`——這是純結構性檢查，不需要打真資料庫。"""
    import dataclasses as dc

    from api_app.storage import (ChainBackoffEntry, ContractHistory,
                                 DataSourceSettings, DividendCacheEntry,
                                 IvBackfillRun, IvObservation,
                                 ProviderCredential, ProviderVerification,
                                 RateCacheEntry, TreasuryYearCacheEntry)

    # 3 張 singleton／provider-key user 表——留給 SCALE-13。
    singleton_user_tables = (ProviderCredential, DataSourceSettings,
                             ProviderVerification)
    # system-wide 共用表——不分 owner 是既有、正確的設計，永遠不該加。
    system_wide_tables = (RateCacheEntry, DividendCacheEntry,
                          TreasuryYearCacheEntry, ChainBackoffEntry,
                          IvObservation, IvBackfillRun, ContractHistory)

    for cls in singleton_user_tables + system_wide_tables:
        field_names = {f.name for f in dc.fields(cls)}
        assert "owner_id" not in field_names, cls.__name__


def test_the_five_row_scoped_dataclasses_do_have_an_owner_field():
    """反向驗證：確實該有的 5 張表（`ResultFactContext`／
    `ResultSummary` 這種「窄投影」型別不算——它們本來就不是完整的
    row 本身，`DiagnosticEvent` 定義在 `diagnostics.py` 不在這裡）。"""
    import dataclasses as dc

    from api_app.storage import ResultRecord, Scenario

    assert "owner_id" in {f.name for f in dc.fields(Scenario)}
    assert "owner_id" in {f.name for f in dc.fields(ResultRecord)}
    from api_app.diagnostics import DiagnosticEvent
    assert "owner_id" in {f.name for f in dc.fields(DiagnosticEvent)}


# ---------- S0 最小可觀測性（SCALE-08／#258） ----------

def test_record_metric_creates_a_new_bucket(storage):
    storage.record_metric("chain_fetch_count", "2026-09-06",
                          source="cboe", symbol="TLT", count=1)
    (entry,) = storage.metric_summary()
    assert entry.metric == "chain_fetch_count"
    assert entry.bucket == "2026-09-06"
    assert entry.source == "cboe"
    assert entry.symbol == "TLT"
    assert entry.count == 1
    assert entry.total == 0.0


def test_record_metric_accumulates_into_the_same_bucket(storage):
    for _ in range(3):
        storage.record_metric("chain_fetch_count", "2026-09-06",
                              source="cboe", symbol="TLT", count=1)
    (entry,) = storage.metric_summary()
    assert entry.count == 3


def test_record_metric_keeps_different_dimensions_separate(storage):
    storage.record_metric("chain_fetch_count", "2026-09-06",
                          source="cboe", symbol="TLT", count=1)
    storage.record_metric("chain_fetch_count", "2026-09-06",
                          source="cboe", symbol="SPY", count=1)
    storage.record_metric("chain_fetch_count", "2026-09-06",
                          source="yfinance", symbol="TLT", count=1)
    entries = {(e.source, e.symbol): e.count for e in storage.metric_summary()}
    assert entries == {("cboe", "TLT"): 1, ("cboe", "SPY"): 1,
                       ("yfinance", "TLT"): 1}


def test_record_metric_tracks_sum_and_max_for_amount_based_metrics():
    """`refresh_duration_ms` 這類需要平均值（`total／count`）與量級
    （`max_value`）的指標——每次呼叫累加 `total`、取較大值進
    `max_value`。"""
    storage = MemoryStorage()
    storage.record_metric("refresh_duration_ms", "2026-09-06",
                          count=1, amount=120.0)
    storage.record_metric("refresh_duration_ms", "2026-09-06",
                          count=1, amount=80.0)
    storage.record_metric("refresh_duration_ms", "2026-09-06",
                          count=1, amount=200.0)
    (entry,) = storage.metric_summary()
    assert entry.count == 3
    assert entry.total == 400.0
    assert entry.max_value == 200.0
    assert entry.total / entry.count == pytest.approx(133.33, rel=1e-3)


def test_metric_summary_on_an_empty_store_is_empty(storage):
    assert storage.metric_summary() == []


def test_old_buckets_for_the_same_metric_are_trimmed_on_write(storage):
    """AC-3：bounded——寫入比 retention 窗更舊的桶，會在下一次同一個
    metric 被寫入時被清掉（trim-on-write，比照既有 diagnostics 表的
    既有慣例，只是這裡按天而非按總筆數裁）。"""
    from api_app.metrics import RETENTION_DAYS

    old_bucket = "2020-01-01"   # 遠早於任何合理的 today - RETENTION_DAYS
    storage.record_metric("chain_fetch_count", old_bucket, count=1)
    assert len(storage.metric_summary()) == 1

    # 寫入一個「今天」的桶，觸發同一個 metric 底下的 trim。
    storage.record_metric("chain_fetch_count", "2026-09-06", count=1)
    remaining = {e.bucket for e in storage.metric_summary()}
    assert old_bucket not in remaining
    assert "2026-09-06" in remaining
    assert RETENTION_DAYS > 0   # 護欄本身要有意義——不是 0 天窗口


def test_trimming_one_metric_does_not_touch_another_metrics_buckets(storage):
    """trim 只清同一個 `metric` 底下的舊桶——不同 metric 各自獨立的
    retention 窗，不會因為某個高流量指標常寫入就把另一個低流量指標
    的舊資料一起清掉（也不會反過來互相保護）。"""
    old_bucket = "2020-01-01"
    storage.record_metric("chain_429_count", old_bucket, count=1)
    storage.record_metric("chain_fetch_count", "2026-09-06", count=1)
    remaining = {(e.metric, e.bucket) for e in storage.metric_summary()}
    assert ("chain_429_count", old_bucket) in remaining
    assert ("chain_fetch_count", "2026-09-06") in remaining


def test_table_size_metrics_on_empty_tables_reports_zero_rows_and_no_size(storage):
    """`total_bytes`（這張表現在佔多少實體空間）對空表兩個後端都是
    良好定義、非 `None` 的答案——`memory.py` 回 0（沒有真正頁面可算，
    誠實近似）、Postgres 回真實頁面配置（通常是一個空表的固定開銷，
    不會是 0），兩者數值**不跨後端比較**、只各自保證「有答案」這件事
    一致（`/code-review` SCALE-08 抓到：原本 memory.py 對空表回
    `None`，跟 Postgres 對空表的行為不一致）。`avg_row_bytes`／
    `max_row_bytes`（單列大小統計量）對零列沒有數學上有意義的答案，
    兩後端一致回 `None`。"""
    stats = storage.table_size_metrics()
    assert set(stats) == {"results", "snapshots"}
    for table_stats in stats.values():
        assert table_stats["row_count"] == 0
        assert table_stats["total_bytes"] is not None
        assert table_stats["total_bytes"] >= 0
        assert table_stats["avg_row_bytes"] is None
        assert table_stats["max_row_bytes"] is None


def test_table_size_metrics_reflects_actual_row_count(storage):
    storage.create_scenario(_scenario())
    storage.save_result(ResultRecord("s1", "2026-08-01T00:00:00+00:00",
                                     {"n": 1, "padding": "x" * 500}))
    storage.save_snapshot("s1", "2026-08-01T00:00:00+00:00",
                          {"padding": "y" * 300})
    stats = storage.table_size_metrics()
    assert stats["results"]["row_count"] == 1
    assert stats["results"]["avg_row_bytes"] > 0
    assert stats["snapshots"]["row_count"] == 1
    assert stats["snapshots"]["avg_row_bytes"] > 0


def test_metric_entry_has_no_disallowed_fields():
    """AC-7：只允許 `source`／`symbol` 兩個維度——不得有 `scenario_id`／
    `owner_id`／任何報價或合約欄位。"""
    import dataclasses as dc

    from api_app.storage import MetricEntry

    field_names = {f.name for f in dc.fields(MetricEntry)}
    assert field_names == {"metric", "bucket", "source", "symbol",
                           "count", "total", "max_value"}
    banned = ("scenario", "owner", "candidate", "quote", "bid", "ask",
             "chain", "contract", "strike", "premium")
    for name in field_names:
        for b in banned:
            assert b not in name.lower(), (name, b)


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
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
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
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
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


def test_existing_results_table_gains_the_per_family_column():
    """T07（#224，Initial V2）：既有部署的 `results` 表在本票之前只有到
    `spot` 為止——`per_family` 一樣得靠 `ALTER TABLE ... ADD COLUMN
    IF NOT EXISTS` 補上，同一條路徑、同一個理由（見
    `test_existing_results_table_gains_the_new_column`）。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
                     "RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS results")
        # T07 之前的舊表：有 best_return／representative_candidate／
        # spot，還沒有 per_family。
        conn.execute("CREATE TABLE results ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, best_return DOUBLE PRECISION, "
                     "representative_candidate JSONB, spot DOUBLE PRECISION, "
                     "PRIMARY KEY (scenario_id, analyzed_at))")

    pg._schema_ready.discard(TEST_DB_URL)
    st = pg.PostgresStorage(TEST_DB_URL)

    st.create_scenario(_scenario("mig3"))
    st.save_result(ResultRecord("mig3", "2026-08-01T00:00:00+00:00", {"n": 1},
                               best_return=0.75, representative_candidate=_REP,
                               per_family=_PER_FAMILY))
    assert st.latest_summaries()["mig3"].per_family == _PER_FAMILY


def test_existing_results_table_gains_the_family_eligibility_column():
    """T10（#227，Initial V2）：既有部署的 `results` 表在本票之前只有到
    `per_family` 為止——`family_eligibility` 一樣得靠 `ALTER TABLE ...
    ADD COLUMN IF NOT EXISTS` 補上，同一條路徑、同一個理由（見
    `test_existing_results_table_gains_the_new_column`）。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
                     "RESTART IDENTITY")
        conn.execute("DROP TABLE IF EXISTS results")
        # T10 之前的舊表：有 per_family，還沒有 family_eligibility。
        conn.execute("CREATE TABLE results ("
                     "scenario_id TEXT NOT NULL, analyzed_at TEXT NOT NULL, "
                     "view JSONB NOT NULL, best_return DOUBLE PRECISION, "
                     "representative_candidate JSONB, spot DOUBLE PRECISION, "
                     "per_family JSONB, "
                     "PRIMARY KEY (scenario_id, analyzed_at))")

    pg._schema_ready.discard(TEST_DB_URL)
    st = pg.PostgresStorage(TEST_DB_URL)

    st.create_scenario(_scenario("mig4"))
    st.save_result(ResultRecord("mig4", "2026-08-01T00:00:00+00:00", {"n": 1},
                               best_return=0.75, representative_candidate=_REP,
                               family_eligibility=_FAMILY_ELIGIBILITY))
    assert st.latest_summaries()["mig4"].family_eligibility == _FAMILY_ELIGIBILITY


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
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
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


# ---------- Request-scoped 連線（PERF-01／#177，T02／#186 修形） ----------
#
# adapter 層級測試，不透過 HTTP endpoint（spec 明文要求）：monkeypatch
# 真正的 `psycopg.connect` 成計數版本，直接驗證 `request_scope()` 讓
# 一個 scope 內任意多個不同 method 呼叫只開一條連線。

def test_multiple_calls_within_a_request_scope_share_a_single_connection():
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    st = pg.PostgresStorage(TEST_DB_URL)
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
                     "RESTART IDENTITY")

    connect_calls = []
    real_connect = psycopg.connect

    def counting_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    import api_app.storage.postgres as pg_module
    original_connect = pg_module.psycopg.connect
    pg_module.psycopg.connect = counting_connect
    borrowed_conn = None
    try:
        with st.request_scope():
            # 一個 scope 內呼叫好幾個不同的 method——恰好一次 connect()
            # （惰性：第一次真正用到才開，這裡是 create_scenario）。
            st.create_scenario(_scenario("scope1"))
            st.get_rate_cache()
            st.get_dividend_cache("TLT")
            st.list_diagnostics()
            # 抓住這個 scope 實際借用中的連線物件本身——下面要驗證的是
            # *這一條*連線確實被關閉，不是只驗證「離開後可以再開一條
            # 新的」（那樣即使舊連線從沒被關閉、只是被丟棄，斷言一樣會
            # 通過，驗不到 `finally` 真的呼叫了 `conn.close()`）。
            held = pg_module._request_scope_state.get()
            assert held is not None
            borrowed_conn = held.conn
        assert len(connect_calls) == 1
    finally:
        pg_module.psycopg.connect = original_connect

    # 離開 scope 後：ContextVar 清空，且**這一條**借用中的連線物件本身
    # 確實被關閉——不是換一條新的、舊的置之不理。
    assert pg_module._request_scope_state.get() is None
    assert borrowed_conn is not None
    assert borrowed_conn.closed

    # 下一次呼叫（scope 外）照舊各自開一條新的，不會誤用一條已經關閉的
    # 連線。
    assert st.get_rate_cache() is None   # 沒炸掉＝沒有沿用一條已關閉的連線


def test_a_scope_with_no_storage_calls_never_opens_a_connection():
    """T02（#186）的核心承諾：完全不碰 storage 的 request 零連線
    握手——進 scope、什麼都不呼叫、離開，`connect()` 一次都不該被
    呼叫過。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    st = pg.PostgresStorage(TEST_DB_URL)

    connect_calls = []
    real_connect = psycopg.connect

    def counting_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return real_connect(*args, **kwargs)

    import api_app.storage.postgres as pg_module
    original_connect = pg_module.psycopg.connect
    pg_module.psycopg.connect = counting_connect
    try:
        with st.request_scope():
            pass   # 故意什麼都不做
        assert connect_calls == []
    finally:
        pg_module.psycopg.connect = original_connect


def test_request_scope_reconnects_correctly_for_a_fresh_request_afterwards():
    """離開 scope 後再進一次新的 scope——確認不會沿用上一個 scope 已經
    關閉的連線物件（ContextVar 每次 scope 都設一條新的）。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    st = pg.PostgresStorage(TEST_DB_URL)
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
                     "RESTART IDENTITY")

    with st.request_scope():
        st.create_scenario(_scenario("scope2"))
    with st.request_scope():
        # 新的 scope、新的連線——這裡如果誤用了上一個已關閉的連線會直接炸掉。
        assert st.get_scenario("scope2") is not None


def test_a_failure_opening_the_shared_connection_falls_back_to_a_per_call_one():
    """T02（#186）：惰性設計下，「開連線失敗」發生在 scope 內**第一次
    真正呼叫到 storage** 的那一刻，不是 `request_scope()` 的 `__enter__`
    本身（那裡現在什麼都不連）。那次呼叫本身不該跟著炸掉——退回逐次
    開連線，且這個 scope 剩餘的呼叫不再嘗試共用（`state.failed`）。"""
    if not TEST_DB_URL:
        pytest.skip("需要 OC_TEST_DATABASE_URL（一個跑著的 Postgres）")
    import psycopg

    from api_app.storage import postgres as pg

    st = pg.PostgresStorage(TEST_DB_URL)
    with psycopg.connect(TEST_DB_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, treasury_year_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history "
                     "RESTART IDENTITY")

    import api_app.storage.postgres as pg_module
    original_connect = pg_module.psycopg.connect
    call_count = {"n": 0}

    def flaky_connect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("db 暫時連不上")
        return original_connect(*args, **kwargs)

    pg_module.psycopg.connect = flaky_connect
    try:
        with st.request_scope():
            # 第一次真正用到 storage：共用連線開不成（第 1 次 connect
            # 呼叫故意失敗），這次呼叫本身退回逐次開連線（第 2 次
            # connect 呼叫成功），正常拿到結果，不炸掉。
            assert st.get_rate_cache() is None
            state = pg_module._request_scope_state.get()
            assert state is not None
            assert state.failed is True
            assert state.conn is None
    finally:
        pg_module.psycopg.connect = original_connect

    # scope 結束後，正常呼叫（連線已恢復）不受影響。
    assert st.get_rate_cache() is None
