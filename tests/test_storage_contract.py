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
from api_app.storage import (ContractHistory, DataSourceSettings,
                             DividendCacheEntry, IvBackfillRun, IvObservation,
                             ProviderCredential, ProviderVerification,
                             RateCacheEntry, ResultRecord, Scenario,
                             ScenarioExists, UsageSetting)
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
        conn.execute("TRUNCATE scenarios, results, snapshots, events, rate_cache, "
                     "dividend_cache, data_source_settings, "
                     "provider_credentials, provider_verifications, "
                     "iv_observations, iv_backfill_runs, contract_iv_history, "
                     "diagnostics RESTART IDENTITY")
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


# ---------- Exact-contract 歷史 IV 快取（HIVT-02／#153） ----------

def _contract_history(symbol="TLT281215C00094000",
                      points=(("2026-06-29", None), ("2026-07-01", 0.185)),
                      fetched_through="2026-08-17",
                      last_attempt_on="2026-08-17", last_status="ok",
                      last_note=None):
    return ContractHistory(contract_symbol=symbol, points=tuple(points),
                           fetched_through=fetched_through,
                           last_attempt_on=last_attempt_on,
                           last_status=last_status, last_note=last_note)


def test_a_contract_starts_with_no_cached_history(storage):
    assert storage.get_contract_history("TLT281215C00094000") is None


def test_saved_contract_history_reads_back_identically(storage):
    storage.save_contract_history(_contract_history())
    assert storage.get_contract_history("TLT281215C00094000") == _contract_history()


def test_rewriting_the_same_contract_overwrites_rather_than_duplicates(storage):
    storage.save_contract_history(_contract_history(
        points=(("2026-07-01", 0.1),)))
    storage.save_contract_history(_contract_history(
        points=(("2026-07-01", 0.1), ("2026-07-02", 0.2)),
        fetched_through="2026-08-18", last_attempt_on="2026-08-18"))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.points == (("2026-07-01", 0.1), ("2026-07-02", 0.2))
    assert got.fetched_through == "2026-08-18"


def test_null_iv_points_round_trip_as_none(storage):
    storage.save_contract_history(_contract_history(
        points=(("2026-06-29", None), ("2026-07-01", 0.185))))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.points[0] == ("2026-06-29", None)
    assert got.points[1] == ("2026-07-01", 0.185)


def test_contracts_do_not_bleed_into_each_other(storage):
    """不同 strike／expiry／call-put 是不同的 OCC symbol，天然是不同的
    快取項目——這正是 exact contract identity 的紅線本身。"""
    storage.save_contract_history(_contract_history(symbol="TLT281215C00094000"))
    storage.save_contract_history(_contract_history(symbol="TLT281215C00100000",
                                                    points=(("2026-07-01", 0.3),)))
    a = storage.get_contract_history("TLT281215C00094000")
    b = storage.get_contract_history("TLT281215C00100000")
    assert a.points != b.points
    assert b.points == (("2026-07-01", 0.3),)


def test_never_successfully_fetched_history_has_no_fetched_through(storage):
    storage.save_contract_history(_contract_history(
        points=(), fetched_through=None, last_status="vendor",
        last_note="連線失敗"))
    got = storage.get_contract_history("TLT281215C00094000")
    assert got.fetched_through is None
    assert got.points == ()
    assert got.last_status == "vendor"


# ---------- Application diagnostics（DG-02／#145） ----------

def _diag(*, event_id="e1", correlation_id="c1", ts="2026-08-15T00:00:00+00:00",
         subsystem="historical_iv", stage="vendor_fetch", severity="error",
         message="boom", context=None):
    return DiagnosticEvent(event_id=event_id, correlation_id=correlation_id,
                           ts=ts, subsystem=subsystem, stage=stage,
                           severity=severity, message=message,
                           context=context or {})


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
                     "dividend_cache, data_source_settings, "
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
                     "dividend_cache, data_source_settings, "
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
                     "dividend_cache, data_source_settings, "
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
