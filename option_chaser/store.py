"""v5 spec §2/§3: 工作區檔案層。純 stdlib、零 wall-clock（時間由呼叫端傳入）。

events.jsonl 是唯一真實來源；scenario 檔的 status 欄位是快取；
groups.json 是全量可重建快取。所有寫入 temp 檔＋os.replace 原子替換。
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .vocabulary import EVENT_TYPES_V5


class WorkspaceIntegrityError(Exception):
    """快取與事件投影不一致（竄改型，spec §2.2）。"""


@dataclass(frozen=True)
class Scenario:
    schema_version: int
    id: str
    symbol: str
    direction: str          # "bullish" | "bearish"
    target_price: float
    target_date: str        # YYYY-MM-DD
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

def scenario_id(symbol: str, target_price: float, target_date: str,
                existing_ids: set[str]) -> str:
    """spec §2.2: {symbol}-{target:g 且 '.'→'p'}-{yyyymm}; 撞名 -2、-3（決定性）。"""
    price = format(target_price, "g").replace(".", "p")
    base = f"{symbol}-{price}-{target_date[:4]}{target_date[5:7]}"
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


def load_scenario(path) -> Scenario:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["strategies"] = tuple(data["strategies"])
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


def lifecycle_events(events: list[dict], sid: str) -> list[dict]:
    """spec §2.3: 行序權威。最後一筆 CREATED 之後的該 id 事件；
    若其後有 DELETED（或根本無 CREATED）→ 無現行生命週期。"""
    created = _last_index(events, sid, "SCENARIO_CREATED")
    deleted = _last_index(events, sid, "SCENARIO_DELETED")
    if created == -1 or deleted > created:
        return []
    return [e for i, e in enumerate(events)
            if i > created and e.get("scenario_id") == sid]


def project_status(events: list[dict], sid: str) -> str | None:
    created = _last_index(events, sid, "SCENARIO_CREATED")
    deleted = _last_index(events, sid, "SCENARIO_DELETED")
    if created == -1 or deleted > created:
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
    """相鄰提案（a 為 target_date 較早者）。確定性，零 LLM。"""
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
                         key=lambda s: (s.target_date, s.id))
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
