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
