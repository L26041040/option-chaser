"""分析師共識的全站快取、每日更新與清單 view（OS-03／#392，母票 #389 §3／§7／§8）。

三件事，都只透過 `Storage` 與注入的 `AnalystSource`，數值一律交給
`option_chaser.consensus`（本模組不做任何共識計算）：

1. **更新**（`refresh_symbols()`，給 `GET /api/cron/consensus-refresh`）：
   比照 `api_app/dividend_cache.py` 的語意——
   - 同一交易日、同一來源，每個 symbol **最多抓一次上游**（成功或失敗都算
     嘗試過；失敗不在當天重試，不重試到耗盡額度，#389 §8）；
   - 成功 → 以 `compute_snapshot()` 算出當天的 Snapshot，寫一筆
     (symbol, as_of)；失敗 → 只記錄嘗試（`ConsensusRefreshState.error`），
     **上一份成功的 Snapshot 原樣保留**，清單照實標出它的 as_of；
   - **進度游標**＝每個 symbol 的 `attempted_day`：每次呼叫依「從沒嘗試過
     → 最久沒嘗試」的順序處理，受時間預算約束；跑不完的部分由下一次呼叫
     （或明天那次 cron）接續，不會因為清單尾巴每天都輪不到而永遠不更新。
2. **清單**（`consensus_view()`，給 `GET /api/opportunity/consensus`）：只讀
   快取、不打上游；讀取時才以使用者的兩道門檻 `evaluate_gate()`——改門檻
   立即生效，不必重抓。
3. **每日摘要統計**（`digest_counts()`）。

只採用**目前設定的來源**產生的快取（`source` 名稱比對）：來源換掉之後，
舊來源（例如測試資料）的 Snapshot 不會被當成新來源的結果顯示。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Sequence

from option_chaser import consensus
from option_chaser.consensus import ConsensusCrossCheck, ConsensusRules, ConsensusSnapshot

from . import search_universe
from .opportunity_settings import DEFAULT_DISPERSION_MAX, DEFAULT_PERCENTILE_MAX
from .analyst_source import AnalystSource
from .storage import ConsensusRefreshState, ConsensusSnapshotRecord, Storage

# 資料品質規則 R 與 target_month 規則：全站一份（不在使用者設定，#389 §6），
# 數值待 #385／#381。這裡只是**暫定預設**——實際值由
# `create_app(consensus_rules=, target_month_rule=)` 注入、一路傳進本模組，
# 改規則不必改程式（user story 40）。
DEFAULT_RULES = ConsensusRules()
DEFAULT_TARGET_MONTH_RULE = "fixed_12m"
# 每日更新母體的總上限（樣本優先；數值待 #386，`create_app(
# consensus_refresh_symbol_cap=)` 可覆寫）。
DEFAULT_REFRESH_SYMBOL_CAP = 200
NOT_CONFIGURED_MESSAGE = "尚未設定分析師資料來源"
_NOT_REFRESHED = "no_data: 尚未更新"
# 「有資料但不足」：資料品質規則沒過（不含完全沒資料、來源失敗）。
_INSUFFICIENT = ("insufficient_analysts", "insufficient_history", "stale",
                 "split_unresolved")


# ---------- Snapshot ⇄ JSON（Decimal 存字串，不失精度） ----------

def _decimal_to_str(x: Decimal | None) -> str | None:
    return None if x is None else str(x)


def snapshot_to_dict(s: ConsensusSnapshot) -> dict:
    return {
        "symbol": s.symbol, "as_of": s.as_of.isoformat(), "status": s.status,
        "n_analysts": s.n_analysts, "mean": _decimal_to_str(s.mean),
        "stdev": _decimal_to_str(s.stdev),
        "dispersion": _decimal_to_str(s.dispersion),
        "high": _decimal_to_str(s.high), "low": _decimal_to_str(s.low),
        "history_points": s.history_points,
        "percentile": _decimal_to_str(s.percentile),
        "history": [[t.isoformat(), str(d)] for t, d in s.history],
        "reasons": list(s.reasons),
        "freshness_share": _decimal_to_str(s.freshness_share),
        "median_published_on": (s.median_published_on.isoformat()
                                if s.median_published_on else None),
        "coverage": s.coverage, "source": s.source,
        "rules_version": s.rules_version,
        "cross_check": ({"consensus_mean_from_source":
                             _decimal_to_str(s.cross_check.consensus_mean_from_source),
                         "n_from_source": s.cross_check.n_from_source}
                        if s.cross_check else None),
        "computed_at": s.computed_at.isoformat() if s.computed_at else None,
    }


def _str_to_decimal(x: str | None) -> Decimal | None:
    return None if x is None else Decimal(x)


def snapshot_from_dict(d: dict) -> ConsensusSnapshot:
    cross = d.get("cross_check")
    return ConsensusSnapshot(
        symbol=d["symbol"], as_of=date.fromisoformat(d["as_of"]), status=d["status"],
        n_analysts=d["n_analysts"], mean=_str_to_decimal(d["mean"]),
        stdev=_str_to_decimal(d["stdev"]),
        dispersion=_str_to_decimal(d["dispersion"]),
        high=_str_to_decimal(d["high"]), low=_str_to_decimal(d["low"]),
        history_points=d["history_points"],
        percentile=_str_to_decimal(d["percentile"]),
        history=tuple((date.fromisoformat(t), Decimal(v)) for t, v in d["history"]),
        reasons=tuple(d["reasons"]),
        freshness_share=_str_to_decimal(d["freshness_share"]),
        median_published_on=(date.fromisoformat(d["median_published_on"])
                             if d.get("median_published_on") else None),
        coverage=d["coverage"], source=d["source"], rules_version=d["rules_version"],
        cross_check=(ConsensusCrossCheck(
            _str_to_decimal(cross["consensus_mean_from_source"]),
            cross["n_from_source"]) if cross else None),
        computed_at=(datetime.fromisoformat(d["computed_at"])
                     if d.get("computed_at") else None))


# ---------- 更新 ----------

def refresh_universe(storage: Storage, *,
                     cap: int = DEFAULT_REFRESH_SYMBOL_CAP) -> list[str]:
    """每日更新的母體 = 大型股樣本 ∪ **目前權限為 SU／SA** 的 owner 的自訂
    清單（#392；Normal 寫不進、也不會被併入——
    `Storage.opportunity_custom_symbols()` 只回特權 owner 的清單）。

    總數不超過 `cap`：樣本永遠排最前面，自訂清單依代號排序接在後面——
    決定性，同一份資料每天選出同一批，不會因為某位使用者的清單很長就把
    樣本擠出去。"""
    sample = search_universe.resolve_universe(None).symbols
    custom = storage.opportunity_custom_symbols()
    return list(dict.fromkeys([*sample, *sorted(custom)]))[:cap]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _refresh_one(storage: Storage, source: AnalystSource, symbol: str,
                 today: date, rules: ConsensusRules) -> str:
    """抓一檔、存結果；回傳 `"ok"`（成功算出 Snapshot，不論資料品質）或
    `"failed"`（來源回報錯誤或丟例外）。"""
    try:
        result = source.fetch(symbol, today)
        error = result.error
    except Exception as e:  # noqa: BLE001 — 來源出錯一律收斂成失敗，不讓 cron 炸掉
        result, error = None, f"資料來源丟出例外：{e}"
    now = _now()
    if error is None:
        snap = consensus.compute_snapshot(
            result.records, result.splits, today, rules, symbol=symbol,
            coverage=result.coverage, source=source.name,
            cross_check=result.cross_check, computed_at=now)
        storage.save_consensus_snapshot(ConsensusSnapshotRecord(
            symbol=symbol, as_of=today.isoformat(), source=source.name,
            is_fixture=bool(source.is_fixture), snapshot=snapshot_to_dict(snap),
            computed_at=now.isoformat()))
    storage.save_consensus_refresh_state(ConsensusRefreshState(
        symbol=symbol, source=source.name, attempted_day=today.isoformat(),
        attempted_at=now.isoformat(), error=error))
    return "ok" if error is None else "failed"


def refresh_symbols(storage: Storage, source: AnalystSource, symbols: Sequence[str],
                    today: date, *, budget_exhausted: Callable[[], bool],
                    rules: ConsensusRules = DEFAULT_RULES) -> dict:
    """處理今天（同一來源）還沒嘗試過的 symbol，最久沒嘗試的先；每處理完
    一檔檢查一次預算，至少處理一檔。回傳本次統計與 `remaining`（下次
    接續的 symbol，依處理順序）。"""
    day = today.isoformat()
    states = storage.consensus_refresh_states()

    def last_attempt(symbol: str) -> str:
        st = states.get(symbol)
        return st.attempted_day if st is not None and st.source == source.name else ""

    pending = sorted((s for s in dict.fromkeys(symbols) if last_attempt(s) != day),
                     key=lambda s: (last_attempt(s), s))
    done_today = len(set(symbols)) - len(pending)
    succeeded = failed = 0
    processed = 0
    for symbol in pending:
        if _refresh_one(storage, source, symbol, today, rules) == "ok":
            succeeded += 1
        else:
            failed += 1
        processed += 1
        if budget_exhausted():
            break
    return {"source": source.name, "as_of": day, "processed": processed,
            "succeeded": succeeded, "failed": failed,
            "already_attempted_today": done_today,
            "remaining": pending[processed:]}


# ---------- 清單 view ----------

def _decimal_to_float(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


def _pct_to_ratio(pct) -> Decimal:
    return Decimal(str(pct)) / 100


def rules_view(rules: ConsensusRules = DEFAULT_RULES,
               target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> dict:
    """清單回應的 `rules` 區塊——照實回報**這個 app 實際注入**的規則。"""
    return {"rules_version": rules.version, "provisional": True,
            "n_min": rules.n_min, "validity_months": rules.validity_months,
            "freshness_days": rules.freshness_days,
            "freshness_min_share": float(rules.freshness_min_share),
            "h_min": rules.h_min, "stdev_kind": rules.stdev_kind,
            "lookback_points": rules.lookback_points, "sampling": "month_end",
            "target_month_rule": target_month_rule}


def _gate_view(gate: consensus.GateResult) -> dict:
    return {"first": gate.first, "second": gate.second, "selected": gate.selected,
            "reasons": list(gate.reasons)}


def _item(symbol: str, status: str, *, reasons: Sequence[str], gate: dict,
          snap: ConsensusSnapshot | None = None,
          target_month: str | None = None) -> dict:
    """清單項目的唯一形狀（有無 Snapshot 都走這裡，鍵不會分家）。沒有
    Snapshot 時數值一律 `None`、人數與歷史點數為 0。"""
    def number(name: str) -> float | None:
        return _decimal_to_float(getattr(snap, name)) if snap else None
    return {"symbol": symbol, "status": status,
            "as_of": snap.as_of.isoformat() if snap else None,
            "n_analysts": snap.n_analysts if snap else 0,
            "mean": number("mean"), "stdev": number("stdev"),
            "dispersion": number("dispersion"), "percentile": number("percentile"),
            "history_points": snap.history_points if snap else 0,
            "coverage": snap.coverage if snap else None,
            "freshness_share": number("freshness_share"),
            "high": number("high"), "low": number("low"),
            "median_published_on": (snap.median_published_on.isoformat()
                                    if snap and snap.median_published_on else None),
            "reasons": list(reasons), "gate": gate,
            "target_month": target_month,
            "rules_version": snap.rules_version if snap else None,
            "refresh_error": None}


def _empty_item(symbol: str, status: str, reason: str) -> dict:
    return _item(symbol, status, reasons=[reason],
                 gate={"first": False, "second": False, "selected": False,
                       "reasons": [reason]})


def _snapshot_item(snap: ConsensusSnapshot, today: date, p_max: Decimal,
                   d_max: Decimal, target_month_rule: str) -> dict:
    try:
        month = consensus.target_month(snap, today, target_month_rule)
    except ValueError:
        month = None
    return _item(snap.symbol, snap.status, reasons=snap.reasons, snap=snap,
                 gate=_gate_view(consensus.evaluate_gate(snap, p_max, d_max)),
                 target_month=month)


def _items(storage: Storage, source: AnalystSource, symbols: Sequence[str],
           today: date, p_max: Decimal, d_max: Decimal,
           target_month_rule: str) -> list[dict]:
    snapshots = storage.latest_consensus_snapshots(symbols, source=source.name)
    states = storage.consensus_refresh_states()
    items = []
    for symbol in symbols:
        rec = snapshots.get(symbol)
        st = states.get(symbol)
        failure = st if (st is not None and st.source == source.name
                         and st.error is not None) else None
        if rec is None:
            items.append(_empty_item(symbol, "source_error",
                                     f"source_error: {failure.error}")
                         if failure else _empty_item(symbol, "no_data", _NOT_REFRESHED))
            continue
        item = _snapshot_item(snapshot_from_dict(rec.snapshot), today, p_max, d_max,
                              target_month_rule)
        if failure is not None and failure.attempted_day > rec.as_of:
            # 最新一次嘗試失敗：沿用上一份成功資料，as_of 照實是那一天。
            item["refresh_error"] = {"day": failure.attempted_day,
                                     "message": failure.error}
        items.append(item)
    return items


def _universe_items(storage: Storage, source: AnalystSource,
                    opportunity: dict, today: date,
                    target_month_rule: str) -> list[dict]:
    """這位使用者母體裡每一檔的清單項目（含依其門檻算出的 `gate`）——
    共識清單與搜尋（`selected_items()`）共用同一份，入選集合不會分家。"""
    universe = search_universe.resolve_universe(opportunity)
    return _items(storage, source, universe.symbols, today,
                  _pct_to_ratio(opportunity["percentile_max"]),
                  _pct_to_ratio(opportunity["dispersion_max"]), target_month_rule)


def selected_items(storage: Storage, source: AnalystSource,
                   opportunity: dict, today: date, *,
                   target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> list[dict]:
    """共識清單裡 `gate.selected` 的項目（母體順序）——機會搜尋（OS-04／
    #393）省略 `symbols` 時的預設集合，與 `consensus_view()` 逐項相同。"""
    return [i for i in _universe_items(storage, source, opportunity, today,
                                       target_month_rule)
            if i["gate"]["selected"]]


def consensus_view(storage: Storage, source: AnalystSource | None,
                   opportunity: dict, today: date, *,
                   rules: ConsensusRules = DEFAULT_RULES,
                   target_month_rule: str = DEFAULT_TARGET_MONTH_RULE) -> dict:
    """`GET /api/opportunity/consensus` 的完整回應。`opportunity` 是
    `opportunity_settings.effective()` 的輸出（門檻為百分比 0–100）。"""
    universe = search_universe.resolve_universe(opportunity)
    thresholds = {"percentile_max": opportunity["percentile_max"],
                  "dispersion_max": opportunity["dispersion_max"]}
    if source is None:
        items: list[dict] = []
        source_view = {"configured": False, "name": None, "is_fixture": False}
    else:
        items = _universe_items(storage, source, opportunity, today,
                                target_month_rule)
        source_view = {"configured": True, "name": source.name,
                       "is_fixture": bool(source.is_fixture)}
    with_data = [i for i in items if i["status"] not in ("no_data", "source_error")]
    coverage = {c: 0 for c in ("complete", "partial", "unknown")}
    for i in with_data:
        coverage[i["coverage"]] = coverage.get(i["coverage"], 0) + 1
    body = {
        "source": source_view,
        "universe": {"id": universe.id, "label": universe.label,
                     "provisional": universe.provisional,
                     "symbols": len(universe.symbols),
                     "with_data": len(with_data),
                     "insufficient": sum(1 for i in with_data
                                         if i["status"] in _INSUFFICIENT),
                     "coverage": coverage,
                     "as_of": max((i["as_of"] for i in items if i["as_of"]),
                                  default=None)},
        "thresholds": thresholds,
        "rules": rules_view(rules, target_month_rule),
        "items": items,
    }
    if source is None:
        body["message"] = NOT_CONFIGURED_MESSAGE
    return body


# ---------- 每日摘要 ----------

def digest_counts(storage: Storage, source: AnalystSource | None,
                  today: date) -> dict | None:
    """今天（同一來源）的更新統計；來源未設定回 `None`。入選數以預設門檻
    （#389 §6：20%／10%）計算——門檻是每位使用者自己的設定，摘要只看全站。"""
    if source is None:
        return None
    p_max = _pct_to_ratio(DEFAULT_PERCENTILE_MAX)
    d_max = _pct_to_ratio(DEFAULT_DISPERSION_MAX)
    day = today.isoformat()
    attempted = [st for st in storage.consensus_refresh_states().values()
                 if st.source == source.name and st.attempted_day == day]
    ok_symbols = [st.symbol for st in attempted if st.error is None]
    snaps = storage.latest_consensus_snapshots(ok_symbols, source=source.name)
    todays = [snapshot_from_dict(r.snapshot) for r in snaps.values() if r.as_of == day]
    return {"source": source.name, "is_fixture": bool(source.is_fixture),
            "succeeded": len(ok_symbols),
            "failed": len(attempted) - len(ok_symbols),
            "insufficient": sum(1 for s in todays if s.status != "ok"),
            "selected": sum(1 for s in todays
                            if consensus.evaluate_gate(s, p_max, d_max).selected)}
