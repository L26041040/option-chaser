"""約 500 檔每日續跑的公平輪替（V2-02／#403）。

在 `consensus_cache.refresh_symbols()`（cron 與 SU「繼續更新」共用的唯一核心）
這個接縫上，用凍結時鐘模擬連續多個交易日：

- 每日上游上限遠小於範圍時，每一檔都在 N＝ceil(範圍／每日處理量) 個交易日內
  輪到，沒有任何一檔連續被跳過超過 N 個交易日；
- 週末沒有 cron，天數依交易日計；
- 順序：從沒嘗試過 → 最久沒嘗試 → 同一天嘗試的以資料最舊者先。
"""
from __future__ import annotations

import math
import zlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from api_app import consensus_cache, search_universe
from api_app.analyst_source import ProviderResult
from api_app.consensus_cache import RefreshPolicy
from api_app.storage import ConsensusRefreshState
from api_app.storage.memory import MemoryStorage
from option_chaser.consensus import AnalystTargetRecord

UNIVERSE = list(search_universe.resolve_universe(None).symbols)
_EASTERN = consensus_cache._EASTERN


def _ok(symbol: str) -> ProviderResult:
    recs = tuple(AnalystTargetRecord(symbol=symbol, analyst_key=f"F{i}", firm=f"F{i}",
                                     target_price=Decimal(p),
                                     published_on=date(2026, 9, 1))
                 for i, p in enumerate(("110", "115", "120", "125", "130")))
    return ProviderResult(records=recs, coverage="complete")


class SimSource:
    """約一成的（代號, 日期）組合失敗，其餘成功；記下每次 fetch 的日期。"""

    name = "sim"
    is_fixture = False

    def __init__(self, fail_share: float = 0.1):
        self.fail_share = fail_share
        self.calls: list[tuple[str, date]] = []

    def fetch(self, symbol, today):
        self.calls.append((symbol, today))
        bucket = zlib.crc32(f"{symbol}|{today}".encode()) % 1000
        if bucket < self.fail_share * 1000:
            return ProviderResult(coverage="partial", error="上游回應狀態碼 500")
        return _ok(symbol)


def _trading_days(start: date, count: int) -> list[date]:
    out, day = [], start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def _epoch(day: date, hour: int, minute: int = 0) -> float:
    return datetime(day.year, day.month, day.day, hour, minute,
                    tzinfo=timezone.utc).timestamp()


def _simulate(storage, source, policy, *, start: date, trading_days: int,
              runs_per_day: int, per_run: int) -> list[date]:
    """每個交易日跑 `runs_per_day` 次 cron（每次最多 `per_run` 檔，間隔 30 分），
    週末一次都不跑（vercel.json 的條目只排週一到週五）。回傳模擬過的交易日。"""
    days = _trading_days(start, trading_days)
    for day in days:
        for run in range(runs_per_day):
            now = _epoch(day, 10, 0) + run * 1800
            clock = lambda: now                                   # noqa: E731
            done_before = len(source.calls)
            consensus_cache.refresh_symbols(
                storage, source, UNIVERSE, day,
                budget_exhausted=lambda: len(source.calls) - done_before >= per_run,
                policy=policy, clock=clock, sleep=lambda _s: None)
    return days


def test_daily_cap_far_below_the_universe_still_reaches_every_symbol_within_n_days():
    """每日上限 60（範圍 503 檔的八分之一）：N＝ceil(503/60)＝9 個交易日。
    模擬 6 週（含週末）：每一檔第一次被嘗試的交易日 ≤ N，之後兩次嘗試之間
    相隔不超過 N 個交易日——失敗的也一樣會再被輪到，不會被成功的擠掉。"""
    cap = 60
    storage, source = MemoryStorage(), SimSource()
    policy = RefreshPolicy(daily_upstream_cap=cap, call_spacing_seconds=0)
    days = _simulate(storage, source, policy, start=date(2026, 10, 1),   # 週四開始
                     trading_days=30, runs_per_day=4, per_run=28)
    n = math.ceil(len(UNIVERSE) / cap)
    assert n == 9
    index = {d: i for i, d in enumerate(days)}
    attempted: dict[str, list[int]] = {}
    for symbol, day in source.calls:
        attempted.setdefault(symbol, [])
        if not attempted[symbol] or attempted[symbol][-1] != index[day]:
            attempted[symbol].append(index[day])
    assert set(attempted) == set(UNIVERSE)
    assert max(v[0] for v in attempted.values()) < n            # 首輪 ≤ N 個交易日
    gaps = [b - a for v in attempted.values() for a, b in zip(v, v[1:])]
    assert max(gaps) <= n                                       # 沒有誰被跳過超過 N 天
    # 每天剛好用滿上限，沒有誰拿到兩份（上限內只做首次嘗試，重試排在最後）。
    per_day = {}
    for _symbol, day in source.calls:
        per_day[day] = per_day.get(day, 0) + 1
    assert set(per_day.values()) == {cap}


def test_every_symbol_gets_fresh_data_within_n_trading_days_when_the_source_is_healthy():
    """上游健康時「嘗試」就是「更新」：每一檔的資料日期最舊不超過 N 個交易日前。"""
    cap = 100
    storage, source = MemoryStorage(), SimSource(fail_share=0)
    policy = RefreshPolicy(daily_upstream_cap=cap, call_spacing_seconds=0)
    days = _simulate(storage, source, policy, start=date(2026, 10, 5),
                     trading_days=20, runs_per_day=4, per_run=28)
    n = math.ceil(len(UNIVERSE) / cap)
    snaps = storage.latest_consensus_snapshots(UNIVERSE, source=source.name)
    assert set(snaps) == set(UNIVERSE)
    oldest = min(date.fromisoformat(r.as_of) for r in snaps.values())
    assert days.index(oldest) >= len(days) - n


def test_weekends_roll_over_by_trading_day():
    """週五跑不完的，週一接著跑——週六、週日沒有 cron，不算被跳過的交易日；
    週一先跑週五沒輪到的，週五已經跑過的排在後面。"""
    storage, source = MemoryStorage(), SimSource(fail_share=0)
    policy = RefreshPolicy(daily_upstream_cap=200, call_spacing_seconds=0)
    friday, monday = date(2026, 10, 9), date(2026, 10, 12)
    _simulate(storage, source, policy, start=friday, trading_days=1,
              runs_per_day=8, per_run=28)
    friday_done = [s for s, _ in source.calls]
    assert len(friday_done) == 200
    source.calls.clear()
    _simulate(storage, source, policy, start=monday, trading_days=1,
              runs_per_day=8, per_run=28)
    monday_done = [s for s, _ in source.calls]
    leftovers = [s for s in UNIVERSE if s not in set(friday_done)]
    assert len(leftovers) == len(UNIVERSE) - 200
    assert len(monday_done) == 200 and set(monday_done) <= set(leftovers)


def _state(symbol, day, *, at_hour=10, success_day=None, error=None):
    at = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
        hours=at_hour)
    return ConsensusRefreshState(
        symbol=symbol, source="sim", attempted_day=day.isoformat(),
        attempted_at=at.isoformat(), error=error, attempts=1,
        last_success_at=(datetime.combine(success_day, datetime.min.time(),
                                          tzinfo=timezone.utc).isoformat()
                         if success_day else None))


def test_rotation_order_is_never_tried_then_oldest_attempt_then_oldest_data():
    storage, source = MemoryStorage(), SimSource(fail_share=0)
    today = date(2026, 10, 14)
    mon, fri, thu = date(2026, 10, 12), date(2026, 10, 9), date(2026, 10, 8)
    for st in (
        _state("DDD", mon, at_hour=9, success_day=mon),        # 昨天、資料最新
        _state("CCC", mon, at_hour=11, success_day=thu),       # 昨天、資料較舊
        _state("EEE", mon, at_hour=12, error="x"),             # 昨天失敗、從沒成功
        _state("BBB", fri, success_day=fri),                   # 上週五
        _state("FFF", thu, success_day=thu),                   # 上週四
    ):
        storage.save_consensus_refresh_state(st)
    body = consensus_cache.refresh_symbols(
        storage, source, ["DDD", "CCC", "EEE", "BBB", "FFF", "AAA"], today,
        budget_exhausted=lambda: False,
        policy=RefreshPolicy(call_spacing_seconds=0), clock=lambda: _epoch(today, 15),
        sleep=lambda _s: None, batch_limit=1)
    order = body["processed_symbols"] + body["remaining"]
    assert order == ["AAA", "FFF", "BBB", "EEE", "CCC", "DDD"]
