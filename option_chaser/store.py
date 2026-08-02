"""v5 spec §2/§3: 工作區檔案層。純 stdlib、零 wall-clock（時間由呼叫端傳入）。

events.jsonl 是唯一真實來源；scenario 檔的 status 欄位是快取；
groups.json 是全量可重建快取。所有寫入 temp 檔＋os.replace 原子替換。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import __version__
from .ranking import spread_baseline_return
from .scenarios import natural_cost
from .service import AnalysisResult, CandidateView, candidate_key, _valuation_key
from .timeframe import TargetMonth
from .valuation import SpreadValuation
from .vocabulary import EVENT_TYPES_V5


SCENARIO_SCHEMA_VERSION = 2   # v2: target_date（YYYY-MM-DD）→ target_month（YYYY-MM）


class WorkspaceIntegrityError(Exception):
    """快取與事件投影不一致（竄改型，spec §2.2）。"""


@dataclass(frozen=True)
class Scenario:
    schema_version: int
    id: str
    symbol: str
    direction: str          # "bullish" | "bearish"
    target_price: float
    target_month: str       # YYYY-MM（年月語意；不並存任何目標日期欄位）
    created_at: str         # ISO 8601 UTC
    notes: str
    group_id: str
    status: str             # vocabulary.SCENARIO_STATUSES
    strategies: tuple[str, ...]


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    _atomic_write_text(
        Path(path),
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


# ---------- Scenario ----------

def scenario_id(symbol: str, target_price: float, target_month: str,
                existing_ids: set[str]) -> str:
    """spec §2.2: {symbol}-{target:g 且 '.'→'p'}-{yyyymm}; 撞名 -2、-3（決定性）。

    ID 格式不變——原本就只取年月，換成年月輸入後輸出逐字相同，既有結果檔案與
    歷史仍然對得上。
    """
    month = TargetMonth.from_key(target_month)   # 順帶把關格式，不做字串切片
    price = format(target_price, "g").replace(".", "p")
    base = f"{symbol}-{price}-{month.year:04d}{month.month:02d}"
    if base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


def scenario_path(ws_root, sid: str) -> Path:
    return Path(ws_root) / "scenarios" / f"{sid}.json"


def save_scenario(ws_root, sc: Scenario) -> None:
    atomic_write_json(scenario_path(ws_root, sc.id), dataclasses.asdict(sc))


def migrate_scenario(data: dict) -> dict:
    """v1 → v2：舊的 target_date 取其年月成為 target_month。

    以「舊欄位是否還在」而非 schema_version 分派：版本號是敘述，欄位才是事實，
    而遷移要修的正是欄位。版本號因此是遷移的結果，不是它的前提。

    一個劇本都不丟，ID 不變（ID 本來就只用到年月）。
    """
    if "target_date" not in data:
        return data
    data = dict(data)
    data["target_month"] = data.pop("target_date")[:7]
    data["schema_version"] = SCENARIO_SCHEMA_VERSION
    return data


def load_scenario(path) -> Scenario:
    """載入劇本；遇到舊格式就地遷移並落盤。

    落盤是必要的：「不並存任何目標日期欄位」是對**磁碟**的要求，只在記憶體裡
    改名的話，一個從此只被列出、never 分析的舊劇本會永遠留著 target_date。
    寫入沿用 atomic replace，且遷移冪等——重跑不會產生第二種結果。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    data = migrate_scenario(raw)
    if data is not raw:
        atomic_write_json(Path(path), data)
    data = dict(data, strategies=tuple(data["strategies"]))
    return Scenario(**data)


def list_scenario_files(ws_root) -> list[Path]:
    d = Path(ws_root) / "scenarios"
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


# ---------- constraints ----------

def load_constraints(ws_root) -> dict:
    path = Path(ws_root) / "constraints.json"
    if not path.exists():
        return {"schema_version": 1, "total_capital": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_constraints(ws_root, total_capital: float | None) -> None:
    atomic_write_json(Path(ws_root) / "constraints.json",
                      {"schema_version": 1, "total_capital": total_capital})


# ---------- events.jsonl ----------

ALLOWED_TRANSITIONS: set[tuple[str, str]] = {
    ("Active", "Reached"), ("Active", "Invalidated"), ("Active", "Expired")}


def _events_path(ws_root) -> Path:
    return Path(ws_root) / "events.jsonl"


def append_event(ws_root, ts: str, scenario_id: str | None, event: str,
                 payload: dict) -> None:
    """spec §6: event 值域鎖定 EVENT_TYPES_V5（v7 預留在 v5 拒寫）。"""
    if event not in EVENT_TYPES_V5:
        raise ValueError(f"事件值不在 v5 詞彙表內: {event}")
    line = json.dumps({"ts": ts, "scenario_id": scenario_id,
                       "event": event, "payload": payload},
                      ensure_ascii=False, sort_keys=True)
    path = _events_path(ws_root)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _atomic_write_text(path, existing + line + "\n")


def read_events(ws_root) -> list[dict]:
    path = _events_path(ws_root)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _last_index(events: list[dict], sid: str, etype: str) -> int:
    idx = -1
    for i, e in enumerate(events):
        if e.get("scenario_id") == sid and e.get("event") == etype:
            idx = i
    return idx


# 終結現行生命週期的兩種事件：硬刪除與軟刪除（附錄 A8.2）。兩者對投影的
# 作用相同——差別只在檔案，不在語意。
_LIFECYCLE_ENDING = ("SCENARIO_DELETED", "SCENARIO_REMOVED")


def _lifecycle_start(events: list[dict], sid: str) -> int:
    """spec §2.3: 行序權威。回傳最後一筆 CREATED 的行序；
    其後若有刪除／移除（或根本無 CREATED）→ -1（無現行生命週期）。"""
    created = _last_index(events, sid, "SCENARIO_CREATED")
    if created == -1:
        return -1
    ended = max(_last_index(events, sid, e) for e in _LIFECYCLE_ENDING)
    return -1 if ended > created else created


def is_removed(events: list[dict], sid: str) -> bool:
    """附錄 A8.2 軟刪除投影：最後一筆移除事件晚於最後一筆建立 → 已移除。"""
    return (_last_index(events, sid, "SCENARIO_REMOVED")
            > _last_index(events, sid, "SCENARIO_CREATED"))


def lifecycle_events(events: list[dict], sid: str) -> list[dict]:
    start = _lifecycle_start(events, sid)
    if start == -1:
        return []
    return [e for i, e in enumerate(events)
            if i > start and e.get("scenario_id") == sid]


def project_status(events: list[dict], sid: str) -> str | None:
    if _lifecycle_start(events, sid) == -1:
        return None
    status = "Active"
    for e in lifecycle_events(events, sid):
        if e["event"] == "STATUS_CHANGED":
            status = e["payload"]["to"]
    return status


def reconcile_status(ws_root, sc: Scenario, events: list[dict]) -> Scenario:
    """spec §2.2 兩型：崩潰窗修復（快取==最後 STATUS_CHANGED 的 from）／竄改拋錯。"""
    projected = project_status(events, sc.id)
    if projected is None:
        raise WorkspaceIntegrityError(
            f"劇本 {sc.id} 檔案存在但事件投影無現行生命週期")
    if sc.status == projected:
        return sc
    changes = [e for e in lifecycle_events(events, sc.id)
               if e["event"] == "STATUS_CHANGED"]
    if changes and sc.status == changes[-1]["payload"]["from"]:
        repaired = dataclasses.replace(sc, status=projected)
        save_scenario(ws_root, repaired)     # 修復快取，不追加事件
        return repaired
    raise WorkspaceIntegrityError(
        f"劇本 {sc.id} 狀態快取 {sc.status} 與事件投影 {projected} 不一致（非崩潰窗型）")


def change_status(ws_root, ts: str, sc: Scenario, to: str, reason: str,
                  by: str = "user", extra_payload: dict | None = None) -> Scenario:
    """先 append 事件、再改快取（spec §2.5 統一寫入次序）。"""
    if (sc.status, to) not in ALLOWED_TRANSITIONS:
        raise ValueError(f"非法狀態轉移: {sc.status} -> {to}")
    payload = {"from": sc.status, "to": to, "reason": reason, "by": by}
    if extra_payload:
        payload.update(extra_payload)
    append_event(ws_root, ts, sc.id, "STATUS_CHANGED", payload)
    updated = dataclasses.replace(sc, status=to)
    save_scenario(ws_root, updated)
    return updated


# ---------- groups.json（全量可重建快取，spec §2.4） ----------

def propose_relation(a: Scenario, b: Scenario) -> str:
    """相鄰提案（a 為 target_month 較早者）。確定性，零 LLM。"""
    if a.direction != b.direction:
        return "exclusive-candidate"
    if a.direction == "bullish":
        progressing = a.target_price <= b.target_price
    else:
        progressing = a.target_price >= b.target_price
    return "milestone-path" if progressing else "review-needed"


def rebuild_groups(ws_root, scenarios: list[Scenario],
                   events: list[dict]) -> dict:
    """members/proposed 由 scenario 檔決定性重建；confirmed 由事件投影
    （行序權威＋生命週期界定：僅計入 pair 兩成員各自最新 CREATED 之後者）。"""
    by_symbol: dict[str, list[Scenario]] = {}
    for sc in scenarios:
        by_symbol.setdefault(sc.symbol, []).append(sc)

    groups = []
    for symbol in sorted(by_symbol):
        members = sorted(by_symbol[symbol],
                         key=lambda s: (s.target_month, s.id))
        relations = []
        for a, b in zip(members, members[1:]):
            confirmed, confirmed_at = "undefined", None
            created_a = _last_index(events, a.id, "SCENARIO_CREATED")
            created_b = _last_index(events, b.id, "SCENARIO_CREATED")
            for i, e in enumerate(events):
                if (e.get("event") == "GROUP_RELATION_CONFIRMED"
                        and set(e["payload"].get("pair", [])) == {a.id, b.id}
                        and i > created_a and i > created_b):
                    confirmed = e["payload"]["choice"]
                    confirmed_at = e["ts"]
            relations.append({"pair": [a.id, b.id],
                              "proposed": propose_relation(a, b),
                              "confirmed": confirmed,
                              "confirmed_at": confirmed_at})
        groups.append({"id": f"G-{symbol}", "symbol": symbol,
                       "members": [m.id for m in members],
                       "relations": relations})
    data = {"schema_version": 1, "groups": groups}
    atomic_write_json(Path(ws_root) / "groups.json", data)
    return data


# ---------- ScenarioResult 契約（spec §3） ----------

def _history_entry(sv: SpreadValuation, expiry: str, rank_in_expiry: int) -> dict:
    """T9（#23，附錄A7）：全部有效候選的歷史五欄位之三（成本／收益率／期內
    名次）；另外兩欄（更新時間、標的價）不逐候選重複，共用父層 `analyzed_at`／
    `meta.spot`（既有設計，`_candidate()` 對完整 CandidateView 同樣不重複）。
    不建 CandidateView：這裡只需要輕量欄位，沒有 Heatmap 矩陣（附錄A10.3）。"""
    return {
        "candidate_key": _valuation_key(sv),
        "expiry": expiry,
        "cost": sv.net_worst,
        "baseline_return": spread_baseline_return(sv),
        "rank_in_expiry": rank_in_expiry,
    }


def _leg(c) -> dict:
    return {"contract_symbol": c.contract_symbol, "option_type": c.option_type,
            "strike": c.strike, "expiry": c.expiry, "bid": c.bid,
            "ask": c.ask, "iv": c.implied_volatility, "volume": c.volume,
            "open_interest": c.open_interest}


def _candidate(cv: CandidateView, strategy: str, capital: float | None,
               today: date, anchor: date) -> dict:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        legs = [_leg(v.long_leg), _leg(v.short_leg)]   # [0]=long, [1]=short
        mid_cost, expiry = v.net_mid, v.long_leg.expiry
        max_profit, net_delta = v.max_profit, v.net_delta
    else:
        legs = [_leg(v.contract)]
        mid_cost, expiry = v.mid, v.contract.expiry
        # 與 service._comparison 相同定義（long-call 無上限 → None）
        max_profit = (None if strategy == "long-call"
                      else v.contract.strike - v.contract.ask)
        net_delta = v.delta
    # T12（附錄 A14.2）：資本／最大虧損以最差成交成本計（natural_cost 即
    # 買 Ask／賣 Bid 口徑）；mid_cost 保留為次要顯示欄位。
    cap_per = natural_cost(v) * 100
    return {
        "candidate_key": candidate_key(cv),
        "strategy": strategy,
        "legs": legs,
        "mid_cost": mid_cost,
        "natural_cost": natural_cost(v),
        "baseline_pnl": cv.baseline_pnl,
        "baseline_return": cv.baseline_return,
        "scenario_vector": {"entries": [list(e) for e in cv.scenario.entries],
                            "worst_code": cv.scenario.worst_code,
                            "worst_return": cv.scenario.worst_return},
        "completion_curve": [list(e) for e in cv.completion_curve],
        "completion_prices": list(cv.completion_prices),
        "completion_threshold": cv.completion_threshold,
        "breakeven_at_target": cv.breakeven_at_target,
        "retention": cv.retention,
        "friction": cv.friction,
        "friction_amount": cv.friction_amount,
        "buffer_days": cv.buffer_days,
        "quote_warning": cv.quote_warning,
        "theta_day_rate": cv.theta_day_rate,
        "vega_per_pt": cv.vega_per_pt,
        "decay_30d_return": cv.decay_30d_return,
        "net_delta": net_delta,
        "breakeven": v.breakeven,
        "max_profit": max_profit,
        "effective_leverage": v.effective_leverage,
        "matrix": {"prices": [list(p) for p in cv.matrix.prices],
                   "dates": [list(d) for d in cv.matrix.dates],
                   "cells": [list(r) for r in cv.matrix.cells]},
        # spec §3 新增四組（乘除法與日期差，非估值邏輯）
        "capital_per_contract": cap_per,
        "max_loss_per_contract": cap_per,   # debit 恆等於成本
        "pct_of_capital": (cap_per / capital) if capital else None,
        # 參考日＝日曆錨點（附錄 A9）；年月本身不映射成任何一天。
        "days_to_target": (anchor - today).days,
        "days_to_expiry": (date.fromisoformat(expiry) - today).days,
    }


def serialize_result(result: AnalysisResult, scenario_id: str,
                     capital: float | None) -> dict:
    base = result.request.base_params
    today = result.today

    def cand(cv, strategy):
        return _candidate(cv, strategy, capital, today, base.anchor)

    def strat(r):
        return {
            "strategy": r.strategy, "status": r.status, "message": r.message,
            "n_qualified": r.n_qualified,
            "filter_stages": ([{"label": s.label, "removed": s.removed}
                               for s in r.filter_report.stages]
                              if r.filter_report else []),
            "pair_report": ({"total_pairs": r.pair_report.total_pairs,
                             "removed_sanity": r.pair_report.removed_sanity,
                             "passed": r.pair_report.passed}
                            if r.pair_report else None),
            "candidates": [cand(cv, r.strategy) for cv in r.candidates],
            "expiry_best": [cand(cv, r.strategy) for cv in r.expiry_best],
            "expiry_counts": [list(e) for e in r.expiry_counts],
            # T9（#23）：各到期日自己的前十名（含 Heatmap 矩陣，供 T10 詳細頁）。
            "expiry_top10": [{"expiry": exp,
                              "candidates": [cand(cv, r.strategy) for cv in cvs]}
                             for exp, cvs in r.expiry_top10],
            # T9（附錄A7）：該次全部有效候選的歷史五欄位（不只入榜者）；
            # 更新時間／標的價共用父層 analyzed_at／meta.spot，不逐候選重複。
            "all_candidates": [_history_entry(sv, exp, rank)
                              for exp, ranked_group in r.expiry_ranked
                              for rank, sv in enumerate(ranked_group, start=1)],
            "report_text": r.report_text,
        }

    def group(g):
        return {"expiry": g.expiry, "buffer_days": g.buffer_days,
                "hidden_count": g.hidden_count,
                "rows": [{"strategy": row.strategy,
                          "badges": list(row.badges),
                          "candidate": cand(row.candidate, row.strategy)}
                         for row in g.rows]}

    all_quotes_filtered = bool(result.results) and all(
        r.status == "empty" and r.filter_report is not None and any(
            s.label == "報價異常" and s.removed >= 1
            for s in r.filter_report.stages)
        for r in result.results)

    m = result.meta
    return {
        "schema_version": 1,
        "engine_version": __version__,
        "analyzed_at": m.fetched_at,
        "scenario_id": scenario_id,
        "params": {**dataclasses.asdict(base),
                   "iv_shifts": list(base.iv_shifts),
                   "delta_bands": list(base.delta_bands)},
        "snapshot_ref": {"path": m.snapshot_path, "fetched_at": m.fetched_at,
                         "source": m.source, "spot": m.spot},
        "meta": {"symbol": m.symbol, "spot": m.spot,
                 "fetched_at": m.fetched_at, "source": m.source,
                 "snapshot_path": m.snapshot_path,
                 "target_move": m.target_move},
        "capital_assumed": capital,
        "data_quality": {"fetched_at": m.fetched_at,
                         "all_quotes_filtered": all_quotes_filtered},
        "results": [strat(r) for r in result.results],
        "expiry_groups": [group(g) for g in result.expiry_groups],
        "hidden_expiries": list(result.hidden_expiries),
        "default_selection": (list(result.default_selection)
                              if result.default_selection else None),
        "comparison": [dataclasses.asdict(c) for c in result.comparison],
        "best_strategy": result.best_strategy,
        "today": today.isoformat(),
    }


def save_result(ws_root, scenario_id: str, view: dict) -> Path:
    """檔名 = fetched_at.replace(':','')（Windows 安全；字典序＝時間序）。"""
    ts = view["snapshot_ref"]["fetched_at"].replace(":", "")
    path = Path(ws_root) / "results" / scenario_id / f"{ts}.json"
    atomic_write_json(path, view)
    return path


def load_result(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_result_path(ws_root, scenario_id: str) -> Path | None:
    d = Path(ws_root) / "results" / scenario_id
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    return files[-1] if files else None
