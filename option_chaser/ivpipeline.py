"""IV history pipeline（T05／#189）：Historical IV 的完整編排，下沉
成引擎深模組。

搬自 `api_app/main.py` 原本住在 `create_app()` closure 裡的 ~680 行
（backfill 配額規則、Exact-Contract Series 與 Legacy Re-anchor Series
兩條平行 pipeline 的執行與合併、point-in-time 的 r／q 組裝、以及
align-then-trim 這個正確性關鍵的順序決定）。**這一票只建置與測試模組
本身，main.py 的呼叫路徑完全不動**——production 行為在這一票結束時
逐位元不變，切換是 T10（#192）的事。

零 I/O、零全域狀態：vendor 合約歷史／surface 取得、Storage 讀寫、
時鐘（`today`／`now_utc_iso`）全部以參數注入（`VendorPorts`／
`StoragePorts`），可以完全用記憶體假體測試，不需要啟動整個 App、不需要
真的資料庫或網路。刻意不 import 任何 `api_app` 的型別——engine 不依賴
`api_app`，storage port 用的是 duck-typed 的欄位形狀（get_* 回傳值只要
有 `.points`／`.fetched_through`／`.symbol` 等對應屬性即可，`api_app.
storage` 的 `ContractHistory`／`IvBackfillRun`／`IvObservation` 天然
滿足），save_* 一律收明確的關鍵字參數而不是包好的物件，呼叫端
（main.py，T10 時）自己決定要不要包成它自己的 dataclass。

不含這次 request 的 diagnostics 落盤與回應信封——那是 HTTP-request
生命週期的關注點（correlation id、per-request buffer、severity 選擇
性落盤），本模組只透過 `emit_exact`／`emit_legacy` 兩個 callable 說出
「這一步發生了什麼」，不知道也不需要知道那些事件最後被存到哪裡。
"""
from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Callable, Protocol

from . import dividends, ivhistory, ivreconstruct, ivspread, ivtrend, ratecurve
from .models import FetchError, QuotaExhausted
from .valuation import DAYS_PER_YEAR, days_between

# ---------- Port 型別 ----------

EmitFn = Callable[..., None]
"""`emit(*, stage, severity, message, **context) -> None`——與
`api_app/diagnostics.py` 的 `emit()` 呼叫慣例一致，呼叫端（main.py）
負責把它接到真正的 `diagnostics.emit()`（帶 correlation id、secrets
遮罩等 HTTP-request 專屬的東西），本模組只認識這個最小呼叫介面。"""

# (provider, symbol, date, token, expiration=None, observer=None) ->
#   {"call": [SurfacePoint-like], "put": [...]}
HistoricalSurfaceFetch = Callable[..., dict]
# (provider, occ_symbol, from_date, to_date, token, observer=None) -> [quote dict, ...]
ContractHistoryFetch = Callable[..., list]
# (from_date, to_date, today) -> ((curve_date, ((tenor, rate), ...)), ...)
# 三個位置參數，不是兩個——這是 PERF-03 的年份為鍵持久快取版本
# （`api_app/treasury_cache.cached_rate_curve_rows()` 回傳的那個
# closure），呼叫端已經包好快取，本模組收到的就是這個已快取的版本，
# 不是底下未快取的 `treasury.fetch_curve_range`。
RateCurveRowsFetch = Callable[[date, date, date], tuple]
# (symbol, today) -> (DividendHistory | None, note)
DividendLoaderFn = Callable[[str, date], tuple]


@dataclasses.dataclass(frozen=True)
class VendorPorts:
    """對外資料源的三個注入點——都是**未快取**的來源；PERF-03／PERF-06
    那層 Storage-backed 快取是 `api_app` 的職責，包好之後再傳進來，
    本模組不知道底下有沒有快取。"""
    historical_surface: HistoricalSurfaceFetch
    contract_history: ContractHistoryFetch
    rate_curve_rows: RateCurveRowsFetch
    dividend_loader: DividendLoaderFn


class _ContractHistoryLike(Protocol):
    points: tuple
    fetched_through: str | None
    last_attempt_on: str | None
    last_status: str
    last_note: str | None


class _IvBackfillRunLike(Protocol):
    symbol: str
    ran_on: str
    outcome: str
    note: str | None


class _IvObservationLike(Protocol):
    observed_on: str
    surface: dict


@dataclasses.dataclass(frozen=True)
class StoragePorts:
    """六個 storage 方法，duck-typed 對照 `api_app.storage.Storage` 的
    同名方法——正式環境直接把 `PostgresStorage`／`MemoryStorage` 的
    對應 bound method 傳進來即可，兩者結構上都滿足，不需要轉接層。
    `save_*` 一律收明確關鍵字參數（不是包好的 dataclass），呼叫端自己
    決定要不要在 port 內部包成它自己的型別。"""
    get_contract_history: Callable[[str], _ContractHistoryLike | None]
    save_contract_history: Callable[..., None]
    get_iv_backfill_run: Callable[[str], _IvBackfillRunLike | None]
    save_iv_backfill_run: Callable[[str, str, str, str | None], None]
    iv_observation_dates: Callable[[str], list]
    save_iv_observation: Callable[[str, str, dict, str], None]
    iv_observations: Callable[[str], list]
    """依 `observed_on` 遞增排序回傳——`build_iv_history` 本身不排序，
    這是呼叫端（adapter）該保證的隱含契約，兩個既有 adapter 皆已如此。"""


# 一天份 backfill 到期日梯子的併發呼叫上限——PERF-05（#181）既有數值，
# 原樣沿用（T05 只搬遷，不調整）。T12（#195）會修的是「執行緒池建立
# 時機」，不是這個數值。
IV_BACKFILL_DAY_CONCURRENCY = 4
# 每個 symbol 每批最多補幾天——PERF-05 前既有數值，原樣沿用。
IV_BACKFILL_PER_RUN = 25


# ---------- 純函式：形狀轉換 ----------

def surface_to_rows(surface: dict) -> dict:
    """`SurfacePoint`-like → 三元組陣列（落盤用）。"""
    return {side: [[p.dte, p.delta, p.iv] for p in points]
            for side, points in surface.items()}


def rows_to_surface(rows: dict) -> dict:
    """落盤形式 → `SurfacePoint`。"""
    return {side: [ivhistory.SurfacePoint(dte=int(r[0]), delta=float(r[1]),
                                          iv=float(r[2]))
                   for r in (points or [])]
            for side, points in (rows or {}).items()}


def leg_contract_identity(leg: dict, underlying: str) -> dict:
    """一條腿的 exact contract identity（HIVT-02／#153）。"""
    return {"underlying": underlying, "expiration": leg["expiry"],
           "strike": leg["strike"], "option_type": leg["option_type"],
           "contract_symbol": leg["contract_symbol"]}


def iv_payload(candidate_key: str, points: list[dict], status: str,
              note: str | None, *, today: date) -> dict:
    """Historical IV 的回應形狀（legacy (tenor,delta) 家族，HIVT-04／
    #155 裁切後）。"""
    metrics = ivhistory.field_metrics(points, today=today)
    return {
        "candidate_key": candidate_key,
        "status": status,
        "normalized_skew_points": [
            {"date": p["date"], "normalized_skew": p["normalized_skew"]}
            for p in points],
        "metrics": {"normalized_skew": metrics["normalized_skew"]},
        "observations": len(points),
        "note": note,
    }


# ---------- 診斷事件組裝（只認識 emit callable，不認識落盤細節） ----------

def _rate_limit_context(telemetry: dict) -> dict:
    return {k: v for k, v in telemetry.items()
           if k.startswith("X-Api-Ratelimit-")}


def _identity_context(identity: dict) -> dict:
    return {"underlying": identity["underlying"],
            "expiration": identity["expiration"],
            "strike": identity["strike"],
            "option_type": identity["option_type"]}


def _emit_contract_history_telemetry(emit: EmitFn, telemetry: dict, *,
                                     provider: str, identity: dict,
                                     requested_from: str,
                                     requested_to: str) -> None:
    vendor_status = telemetry.get("vendor_status")
    emit(stage="vendor_fetch",
        severity="info" if vendor_status == "ok" else "error",
        message=f"vendor 回應 s={vendor_status!r}",
        provider=provider, contract_symbol=identity["contract_symbol"],
        **_identity_context(identity),
        requested_from=requested_from, requested_to=requested_to,
        http_status=telemetry.get("http_status"),
        vendor_status=vendor_status,
        vendor_errmsg=telemetry.get("vendor_errmsg"),
        raw_rows=telemetry.get("raw_rows"),
        **_rate_limit_context(telemetry))
    emit(stage="payload_parse",
        severity="warning" if (telemetry.get("raw_rows") or 0) > 0
                 and (telemetry.get("parsed_rows") or 0) == 0 else "info",
        message="解析單合約歷史欄狀回應",
        provider=provider, contract_symbol=identity["contract_symbol"],
        **_identity_context(identity),
        raw_rows=telemetry.get("raw_rows"),
        parsed_rows=telemetry.get("parsed_rows"),
        null_iv_count=telemetry.get("null_iv_count"),
        dropped_missing_date=telemetry.get("dropped_missing_date"))


def _is_weekend(day: str) -> bool:
    return date.fromisoformat(day).weekday() >= 5


def _emit_backfill_summary(emit: EmitFn, *, symbol: str, attempted_days: int,
                           saved_days: int, days_with_data: int,
                           days_no_data_expected: int,
                           days_no_data_unexpected: int,
                           aborted_on: str | None, abort_reason: str | None,
                           remaining_gap: int, outcome: str,
                           failed_expiration: str | None = None,
                           in_flight_after_failure_succeeded: int = 0,
                           in_flight_after_failure_failed: int = 0,
                           unstarted_due_to_failure: int = 0) -> None:
    emit(stage="backfill",
        severity="warning" if aborted_on or days_no_data_unexpected > 0
                 else "info",
        message=(f"backfill 在 {aborted_on} 中止：{abort_reason}"
                if aborted_on else "backfill 批次完成"),
        symbol=symbol, attempted_days=attempted_days, saved_days=saved_days,
        days_with_data=days_with_data,
        days_no_data_expected=days_no_data_expected,
        days_no_data_unexpected=days_no_data_unexpected,
        days_failed=1 if aborted_on else 0,
        aborted_on=aborted_on, abort_reason=abort_reason,
        remaining_gap=remaining_gap, outcome=outcome,
        failed_expiration=failed_expiration,
        in_flight_after_failure_succeeded=in_flight_after_failure_succeeded,
        in_flight_after_failure_failed=in_flight_after_failure_failed,
        unstarted_due_to_failure=unstarted_due_to_failure)


def reanchor_in_grid(reanchored: dict, coords: dict) -> bool:
    """這一天的座標是否至少有一個核心欄位真的查到值。"""
    sell = coords.get("sell")
    core_fields = ("buy_iv", "atm_iv") if sell is None else (
        "buy_iv", "sell_iv", "atm_iv", "normalized_skew")
    return not all(reanchored.get(f) is None for f in core_fields)


def _emit_reanchor_summary(emit: EmitFn, *, coords: dict, in_grid: int,
                           out_of_grid: int) -> None:
    buy = coords.get("buy")
    sell = coords.get("sell")
    total = in_grid + out_of_grid
    emit(stage="reanchor",
        severity="warning" if out_of_grid > 0 else "info",
        message=f"{total} 個歷史日期：{in_grid} 個落在網格內／"
                f"{out_of_grid} 個落在網格外",
        total_dates=total, in_grid_dates=in_grid, out_of_grid_dates=out_of_grid,
        tenor_days=buy.tenor_days if buy is not None else None,
        buy_delta=buy.delta if buy is not None else None,
        sell_delta=sell.delta if sell is not None else None)


def _emit_metrics(emit: EmitFn, points: list[dict], coords: dict, *,
                  today: date) -> None:
    metrics = ivhistory.field_metrics(points, today=today)
    applicable = (("buy_iv", "atm_iv") if coords.get("sell") is None
                 else tuple(metrics.keys()))
    for field_name in applicable:
        m = metrics[field_name]
        count = m["count"]
        emit(stage="metrics",
            severity="warning" if count == 0 else "info",
            message=f"{field_name} 沒有有效觀測" if count == 0
                    else f"{field_name} 指標計算完成",
            field=field_name, count=count,
            percentile_available=m["percentile"] is not None,
            trend_base_count=m["trend_base_count"])


def _emit_staleness(emit: EmitFn, *, identity: dict, observation: dict,
                    request_time: str, today: date) -> None:
    obs_date = date.fromisoformat(observation["date"])
    exp_date = date.fromisoformat(identity["expiration"])
    staleness_days = (today - obs_date).days
    computed_dte = days_between(obs_date, exp_date)
    emit(stage="staleness",
        severity="info" if staleness_days <= 1 else "warning",
        message=(f"最新觀測 {staleness_days} 天前" if staleness_days > 1
                else "最新觀測新鮮"),
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        date=obs_date.isoformat(), request_time=request_time,
        observation_timestamp=observation.get("updated"),
        staleness_days=staleness_days, vendor_dte=observation.get("dte"),
        computed_dte=computed_dte)


def _emit_reconstruction_ledger(emit: EmitFn, *, identity: dict, fetched: int,
                                series: list[tuple[str, float | None]],
                                failure_counts: dict[str, int]) -> None:
    reconstructed = sum(1 for _, iv in series if iv is not None)
    emit(stage="reconstruction",
        severity="info" if reconstructed > 0 else "warning",
        message="重建完成" if reconstructed > 0 else "整段序列沒有任何一筆重建成功",
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        fetched=fetched, reconstructed=reconstructed, usable=reconstructed,
        **{reason: failure_counts.get(reason, 0)
           for reason in ivreconstruct.FAILURE_REASONS})


def _emit_vendor_benchmark(emit: EmitFn, *, identity: dict, quotes: list[dict],
                           series: list[tuple[str, float | None]]) -> None:
    reconstructed_by_date = dict(series)
    present = 0
    excluded_degenerate = 0
    compared = 0
    total_abs_diff = 0.0
    for q in quotes:
        vendor_iv = q.get("vendor_iv")
        if vendor_iv is None:
            continue
        present += 1
        if not ivreconstruct.vendor_iv_is_benchmarkable(vendor_iv):
            excluded_degenerate += 1
            continue
        reconstructed = reconstructed_by_date.get(q["date"])
        if reconstructed is None:
            continue
        compared += 1
        total_abs_diff += abs(reconstructed - vendor_iv)
    mean_abs_diff = (total_abs_diff / compared) if compared else None
    emit(stage="vendor_benchmark", severity="info",
        message=(f"vendor IV 合理性比較：{present} 筆有值，"
                f"{excluded_degenerate} 筆被 gate 排除，{compared} 筆可比較"),
        contract_symbol=identity["contract_symbol"], **_identity_context(identity),
        vendor_iv_present=present,
        vendor_iv_excluded_degenerate=excluded_degenerate,
        vendor_iv_compared=compared, mean_abs_diff=mean_abs_diff)


_WINDOWED_STAT_FIELDS = frozenset(
    {"moving_average", "bollinger_bands", "current_zscore"})


def _leg_stat_is_available(field_name: str, value: Any) -> bool:
    if field_name == "moving_average":
        return bool(value) and value[-1][1] is not None
    if field_name == "bollinger_bands":
        upper = (value or {}).get("upper") or []
        return bool(upper) and upper[-1][1] is not None
    return value is not None


def _emit_leg_stat_metrics(emit: EmitFn, *, identity: dict, stats: dict,
                           observation_count: int) -> None:
    for field_name, value in stats.items():
        available = _leg_stat_is_available(field_name, value)
        windowed = ({"lookback_days": ivtrend.IV_TREND_LOOKBACK_DAYS}
                   if field_name in _WINDOWED_STAT_FIELDS else {})
        emit(stage="metrics",
            severity="info" if available else "warning",
            message=f"{field_name} 計算完成" if available
                    else f"{field_name} 回報 unavailable",
            **_identity_context(identity), field=field_name,
            count=observation_count, **windowed)


# ---------- Legacy (tenor, delta) 重錨定家族：cold backfill ----------

def backfill_iv(symbol: str, provider: str, token: str,
                target_expirations: list[str], *,
                today: date, now_utc_iso: Callable[[], str],
                vendor: VendorPorts, storage: StoragePorts,
                emit: EmitFn) -> tuple[str, str | None]:
    """把這個 symbol 的歷史觀測往前補一批，回傳 (狀態, 說明)。

    四條規則（已有的日期不重抓／每個 symbol 每天一批／每批有上限／
    只鎖定 target_expirations 這幾個到期日）逐字沿用 PERF-05 之前的
    既有邏輯，`emit` 只負責說出已經在發生的事，不參與判斷。
    """
    run = storage.get_iv_backfill_run(symbol)
    if run is not None and run.ran_on == today.isoformat():
        emit(stage="cache", severity="info", message="今天已跑過 backfill，沿用既有結論",
            symbol=symbol, already_ran_today=True, outcome=run.outcome)
        return run.outcome, run.note

    wanted = ivhistory.sampling_schedule(symbol, today)
    have = set(storage.iv_observation_dates(symbol))
    missing = [d for d in wanted if d not in have]
    emit(stage="cache", severity="info", message="計算 backfill 缺口",
        symbol=symbol, wanted_days=len(wanted), have_days=len(have),
        missing_days=len(missing), already_ran_today=False)
    expirations = target_expirations or [None]

    def _fetch_day_bounded(day: str):
        """一天份的到期日梯子，有上限的併發呼叫（PERF-05 既有設計，
        T05 原樣沿用；執行緒池建立時機的修正是 T12 的事）。"""
        merged: dict[str, list] = {"call": [], "put": []}
        first_failure = None
        after_ok = after_fail = dispatched = 0
        idx = 0
        while idx < len(expirations) and first_failure is None:
            batch = expirations[idx: idx + IV_BACKFILL_DAY_CONCURRENCY]
            idx += len(batch)
            dispatched += len(batch)
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                futures = {pool.submit(vendor.historical_surface, provider,
                                      symbol, day, token, expiration=exp): exp
                          for exp in batch}
                for future in as_completed(futures):
                    exp = futures[future]
                    try:
                        got = future.result()
                    except QuotaExhausted as e:
                        if first_failure is None:
                            first_failure = ("quota", e, exp)
                        else:
                            after_fail += 1
                        continue
                    except FetchError as e:
                        if first_failure is None:
                            first_failure = ("vendor", e, exp)
                        else:
                            after_fail += 1
                        continue
                    if first_failure is not None:
                        after_ok += 1
                    merged["call"].extend(got.get("call") or [])
                    merged["put"].extend(got.get("put") or [])
        return merged, first_failure, after_ok, after_fail, dispatched

    outcome, note = "ok", None
    attempted_days = 0
    saved_days = 0
    days_with_data = 0
    days_no_data_expected = 0
    days_no_data_unexpected = 0
    aborted_on: str | None = None
    abort_reason: str | None = None
    failed_expiration = None
    in_flight_after_failure_succeeded = 0
    in_flight_after_failure_failed = 0
    total_dispatched = 0
    schedule = sorted(missing, reverse=True)[:IV_BACKFILL_PER_RUN]
    for day in schedule:
        attempted_days += 1
        merged, first_failure, after_ok, after_fail, dispatched = \
            _fetch_day_bounded(day)
        total_dispatched += dispatched

        def _save_day(merged=merged, day=day) -> bool:
            storage.save_iv_observation(
                symbol, day, surface_to_rows(merged), now_utc_iso())
            return bool(merged["call"] or merged["put"])

        if first_failure is not None:
            reason, exc, failed_expiration = first_failure
            outcome, note = reason, str(exc)
            aborted_on, abort_reason = day, reason
            in_flight_after_failure_succeeded += after_ok
            in_flight_after_failure_failed += after_fail
            if merged["call"] or merged["put"]:
                _save_day()
                saved_days += 1
                days_with_data += 1
            break

        if _save_day():
            days_with_data += 1
        elif _is_weekend(day):
            days_no_data_expected += 1
        else:
            days_no_data_unexpected += 1
        saved_days += 1

    total_planned = len(expirations) * len(schedule)
    unstarted_due_to_failure = (total_planned - total_dispatched
                                if aborted_on else 0)

    _emit_backfill_summary(
        emit, symbol=symbol, attempted_days=attempted_days,
        saved_days=saved_days, days_with_data=days_with_data,
        days_no_data_expected=days_no_data_expected,
        days_no_data_unexpected=days_no_data_unexpected,
        aborted_on=aborted_on, abort_reason=abort_reason,
        remaining_gap=len(missing) - saved_days, outcome=outcome,
        failed_expiration=failed_expiration,
        in_flight_after_failure_succeeded=in_flight_after_failure_succeeded,
        in_flight_after_failure_failed=in_flight_after_failure_failed,
        unstarted_due_to_failure=unstarted_due_to_failure)

    storage.save_iv_backfill_run(symbol, today.isoformat(), outcome, note)
    return outcome, note


# ---------- Exact-Contract Series 家族 ----------

def ensure_contract_history(identity: dict, provider: str, token: str, *,
                            today: date, now_utc_iso: Callable[[], str],
                            vendor: VendorPorts, storage: StoragePorts,
                            emit: EmitFn) -> tuple[list[dict], str, str | None]:
    """一條腿的 exact contract 歷史：快取命中且今天已嘗試過就不打
    vendor，否則只補 `fetched_through` 之後到今天的缺口（HIVT-02／
    #153）。回傳 `(points, status, note)`。"""
    occ_symbol = identity["contract_symbol"]
    cached = storage.get_contract_history(occ_symbol)
    today_iso = today.isoformat()

    # HIVR-04（#163）：舊格式 `[date, iv]` 二元組視為 cache miss 整批重抓。
    if cached is not None and cached.points and not isinstance(
            cached.points[0], dict):
        cached = None

    if cached is not None and cached.last_attempt_on == today_iso:
        emit(stage="cache", severity="info",
            message="今天已嘗試過這張合約，沿用既有結論",
            contract_symbol=occ_symbol, **_identity_context(identity),
            already_fetched_today=True,
            fetched_through=cached.fetched_through,
            observations_returned=len(cached.points))
        return list(cached.points), cached.last_status, cached.last_note

    existing_points = list(cached.points) if cached is not None else []
    fetched_through = cached.fetched_through if cached is not None else None
    from_date = ((date.fromisoformat(fetched_through) + timedelta(days=1))
                .isoformat() if fetched_through
                else (today - timedelta(days=ivtrend.IV_TREND_MAX_HISTORY_DAYS))
                .isoformat())
    to_date = today_iso

    emit(stage="cache", severity="info", message="計算歷史缺口",
        contract_symbol=occ_symbol, **_identity_context(identity),
        requested_from=from_date, requested_to=to_date,
        already_fetched_today=False, fetched_through=fetched_through)

    def _observer(telemetry):
        _emit_contract_history_telemetry(
            emit, telemetry, provider=provider, identity=identity,
            requested_from=from_date, requested_to=to_date)

    try:
        new_points = vendor.contract_history(provider, occ_symbol, from_date,
                                             to_date, token, observer=_observer)
    except QuotaExhausted as e:
        status, note = "quota", str(e)
    except FetchError as e:
        status, note = "vendor", str(e)
    else:
        merged = {q["date"]: q for q in existing_points}
        merged.update({q["date"]: q for q in new_points})
        merged_points = [merged[d] for d in sorted(merged)]
        storage.save_contract_history(
            contract_symbol=occ_symbol, points=tuple(merged_points),
            fetched_through=to_date, last_attempt_on=today_iso,
            last_status="ok", last_note=None)
        emit(stage="database_write", severity="info",
            message="寫入合約歷史觀測", contract_symbol=occ_symbol,
            **_identity_context(identity),
            observations_returned=len(new_points),
            null_iv_count=sum(1 for q in new_points
                              if q["vendor_iv"] is None))
        if new_points:
            _emit_staleness(emit, identity=identity,
                            observation=max(new_points, key=lambda q: q["date"]),
                            request_time=now_utc_iso(), today=today)
        return merged_points, "ok", None

    storage.save_contract_history(
        contract_symbol=occ_symbol, points=tuple(existing_points),
        fetched_through=fetched_through, last_attempt_on=today_iso,
        last_status=status, last_note=note)
    emit(stage="database_write", severity="warning",
        message="vendor 這次嘗試失敗，沿用既有觀測",
        contract_symbol=occ_symbol, **_identity_context(identity),
        observations_returned=len(existing_points))
    return existing_points, status, note


def _fetch_rate_curve_rows(dates: list[str], *, today: date,
                           vendor: VendorPorts) -> tuple:
    """HIVR-06（#165）：涵蓋 `dates` 全部日期所需年份的曲線列。空輸入或
    抓取失敗都回空 tuple——呼叫端據此讓每一筆觀測記成 `no_rate`，不擋
    其餘計算（這裡刻意不拋出，抓取失敗不是使用者能做什麼的錯誤）。"""
    if not dates:
        return ()
    from_date = date.fromisoformat(min(dates))
    to_date = date.fromisoformat(max(dates))
    try:
        return vendor.rate_curve_rows(from_date, to_date, today)
    except Exception:  # noqa: BLE001 — 抓不到就讓下游逐筆記 no_rate
        return ()


def rate_by_date_for_leg(rows: tuple, quotes: list[dict],
                         expiration: str) -> dict[str, float]:
    """逐一觀測日：那天的曲線 → 那天到 expiration 的年期 → 期限對齊
    利率。與 `ivreconstruct.reconstruct_iv_series()` 算 T 的方式一致。"""
    exp_date = date.fromisoformat(expiration)
    out: dict[str, float] = {}
    for q in quotes:
        d = q["date"]
        if d in out:
            continue
        curve = ratecurve.curve_asof(rows, d)
        if curve is None:
            continue
        T = days_between(date.fromisoformat(d), exp_date) / DAYS_PER_YEAR
        out[d] = ratecurve.rate_for_tenor(curve, T)
    return out


def dividend_yield_by_date_for_leg(history, quotes: list[dict]) -> dict[str, float]:
    """逐一觀測日：那天的 q＝那筆觀測自己的 underlying_price。"""
    if history is None:
        return {}
    out: dict[str, float] = {}
    for q in quotes:
        spot = q.get("underlying_price")
        if spot is None or spot <= 0:
            continue
        d = q["date"]
        out[d] = dividends.compute_q_asof(
            history, spot=spot, observation_date=date.fromisoformat(d))
    return out


def reconstruct_leg_series(identity: dict, quotes: list[dict],
                           rate_rows: tuple, dividend_history, *,
                           emit: EmitFn) -> list[tuple[str, float | None]]:
    """寬版 quote 序列 → reconstruction → (date, iv) 序列——每一筆都
    重新反解，包含 vendor 剛好給了非 null iv 的那些（spec #159：全期間
    同一把尺）。緊接著發帳本事件與 vendor IV 合理性比較。"""
    rate_by_date = rate_by_date_for_leg(rate_rows, quotes, identity["expiration"])
    q_by_date = dividend_yield_by_date_for_leg(dividend_history, quotes)
    series, failure_counts = ivreconstruct.reconstruct_iv_series(
        identity["option_type"], identity["strike"], identity["expiration"],
        quotes, rate_by_date, q_by_date)
    _emit_reconstruction_ledger(emit, identity=identity, fetched=len(quotes),
                                series=series, failure_counts=failure_counts)
    _emit_vendor_benchmark(emit, identity=identity, quotes=quotes, series=series)
    return series


def leg_historical_iv_payload(identity: dict, points: list[tuple],
                              status: str, note: str | None, *,
                              today: date, emit: EmitFn) -> dict:
    """`LegHistoricalIv` 的完整形狀：原始序列＋描述性欄位＋統計量套組。"""
    trimmed = ivtrend.trim_to_window(points, today=today)
    valid = sorted((d, iv) for d, iv in trimmed if iv is not None)
    latest_iv = valid[-1][1] if valid else None

    ma = ivtrend.moving_average(trimmed)
    bands = ivtrend.bollinger_bands(trimmed)
    zscore = ivtrend.current_zscore(trimmed)
    percentile = ivtrend.historical_percentile(trimmed, latest_iv)
    d4w = ivtrend.delta_4w(trimmed, latest=latest_iv, today=today)

    _emit_leg_stat_metrics(
        emit, identity=identity, observation_count=len(valid),
        stats={"moving_average": ma, "bollinger_bands": bands,
              "current_zscore": zscore,
              "historical_percentile": percentile, "delta_4w": d4w})

    return {
        "contract": identity,
        "points": [
            {"date": d, "iv": iv,
             "low_confidence": ivreconstruct.is_low_confidence(
                 d, identity["expiration"])}
            for d, iv in trimmed
        ],
        "moving_average": [{"date": d, "value": v} for d, v in ma],
        "bollinger_upper": [{"date": d, "value": v} for d, v in bands["upper"]],
        "bollinger_lower": [{"date": d, "value": v} for d, v in bands["lower"]],
        "current_percentile": percentile,
        "current_zscore": zscore,
        "delta_4w": d4w,
        "observation_count": len(valid),
        "history_span_days": ivtrend.history_span_days(trimmed),
        "lookback_days_config": ivtrend.IV_TREND_LOOKBACK_DAYS,
        "status": status,
        "note": note,
    }


def spread_gap_payload(buy_series: list[tuple[str, float | None]],
                       sell_series: list[tuple[str, float | None]], *,
                       today: date) -> dict:
    """`spread_gap` 區塊的完整形狀（SIG-01／#172）：先對齊、再裁窗。"""
    aligned = ivspread.align_spread_gap(buy_series, sell_series)
    trimmed = ivtrend.trim_to_window(aligned, today=today)
    current_gap = trimmed[-1][1] if trimmed else None

    ma = ivtrend.moving_average(trimmed)
    bands = ivtrend.bollinger_bands(trimmed)
    percentile = ivtrend.historical_percentile(trimmed, current_gap)
    d4w = ivtrend.delta_4w(trimmed, latest=current_gap, today=today)
    ratio, status = ivspread.spread_delta_4w_ratio_status(current_gap, d4w)

    return {
        "points": [{"date": d, "gap": g} for d, g in trimmed],
        "moving_average": [{"date": d, "value": v} for d, v in ma],
        "bollinger_upper": [{"date": d, "value": v} for d, v in bands["upper"]],
        "bollinger_lower": [{"date": d, "value": v} for d, v in bands["lower"]],
        "current_percentile": percentile,
        "delta_4w": d4w,
        "delta_4w_ratio": ratio,
        "delta_4w_status": status,
        "observation_count": len(trimmed),
        "shared_history_span_days": ivtrend.history_span_days(trimmed),
    }


# ---------- 進入點：兩個家族一起跑，合併成一份回應 ----------

def build_iv_history(*, symbol: str, candidate: dict, spot: float,
                     known_expiries: list[str], provider: str, token: str,
                     today: date, now_utc_iso: Callable[[], str],
                     vendor: VendorPorts, storage: StoragePorts,
                     emit_exact: EmitFn, emit_legacy: EmitFn) -> dict:
    """一個候選的完整 Historical IV 回應——Exact-Contract Series（逐腿）
    與 Legacy Re-anchor Series（(tenor, delta) 重錨定，含 Spread IV
    Gap）兩條獨立 pipeline 都跑完才合併回應，形狀與 T05 之前
    `api_app/main.py` 的 `iv_history()` 端點編排完全一致（不含
    `diagnostics` 信封——那由呼叫端在 flush 之後另外附加）。

    `candidate` 是 `store.find_candidate()` 的結果（含 `legs`／
    `days_to_expiry`）；`known_expiries` 是這個劇本全部策略結果裡出現
    過的到期日聯集（跨策略去重）；`spot` 是這次分析當下的標的現價。
    """
    # ---- Exact-Contract Series（逐腿） ----
    legs_payload: dict[str, dict] = {}
    candidate_legs = candidate.get("legs") or []
    leg_names = ("buy", "sell") if len(candidate_legs) >= 2 else ("buy",)
    leg_fetches = []
    for name, leg in zip(leg_names, candidate_legs):
        identity = leg_contract_identity(leg, symbol)
        leg_points, leg_status, leg_note = ensure_contract_history(
            identity, provider, token, today=today, now_utc_iso=now_utc_iso,
            vendor=vendor, storage=storage, emit=emit_exact)
        leg_fetches.append((name, identity, leg_points, leg_status, leg_note))

    # HIVR-06（#165）：point-in-time r／q 輸入兩腿共用，一次抓好即可。
    all_dates = [q["date"] for _, _, points, _, _ in leg_fetches for q in points]
    rate_rows = _fetch_rate_curve_rows(all_dates, today=today, vendor=vendor)
    dividend_history, _div_note = vendor.dividend_loader(symbol, today)

    reconstructed_by_name: dict[str, list[tuple[str, float | None]]] = {}
    for name, identity, leg_points, leg_status, leg_note in leg_fetches:
        reconstructed = reconstruct_leg_series(
            identity, leg_points, rate_rows, dividend_history, emit=emit_exact)
        reconstructed_by_name[name] = reconstructed
        legs_payload[name] = leg_historical_iv_payload(
            identity, reconstructed, leg_status, leg_note,
            today=today, emit=emit_exact)

    spread_gap = None
    if "sell" in reconstructed_by_name:
        spread_gap = spread_gap_payload(
            reconstructed_by_name["buy"], reconstructed_by_name["sell"],
            today=today)

    # ---- Legacy (tenor, delta) Re-anchor Series ----
    target_expirations = ivhistory.nearby_expirations(
        known_expiries, today=today,
        tenor_days=candidate.get("days_to_expiry") or 0)
    outcome, note = backfill_iv(symbol, provider, token, target_expirations,
                                today=today, now_utc_iso=now_utc_iso,
                                vendor=vendor, storage=storage, emit=emit_legacy)

    coords = ivhistory.spread_coordinates(candidate, spot=spot)
    if coords is None:
        return {**iv_payload(candidate["candidate_key"], [], outcome,
                             "這個候選算不出 (tenor, delta) 座標", today=today),
               "legs": legs_payload,
               **({"spread_gap": spread_gap} if spread_gap is not None else {})}

    points = []
    in_grid = 0
    out_of_grid = 0
    for obs in storage.iv_observations(symbol):
        surface = rows_to_surface(obs.surface)
        reanchored = ivhistory.reanchor_spread(surface, coords)
        if reanchor_in_grid(reanchored, coords):
            in_grid += 1
        else:
            out_of_grid += 1
        points.append({"date": obs.observed_on, **reanchored})

    _emit_reanchor_summary(emit_legacy, coords=coords,
                           in_grid=in_grid, out_of_grid=out_of_grid)
    _emit_metrics(emit_legacy, points, coords, today=today)

    return {**iv_payload(candidate["candidate_key"], points, outcome, note,
                         today=today),
           "legs": legs_payload,
           **({"spread_gap": spread_gap} if spread_gap is not None else {})}
