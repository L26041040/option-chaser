"""v5 spec §4: 工作區編排層（store 與 GUI 之間；不碰估值）。

wall-clock 僅在本層（now_utc_iso / ny_today）；store 保持純函數。
觀察日基準 = America/New_York（與引擎 snapshot_today 一致，spec §2.2）。
"""
from __future__ import annotations

import dataclasses
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import store
from .data.snapshot import load_snapshot
from .store import Scenario
from .vocabulary import RELATION_CHOICES

_EASTERN = ZoneInfo("America/New_York")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ny_today() -> date:
    return datetime.now(_EASTERN).date()


def _existing_ids(ws_root) -> set[str]:
    return {p.stem for p in store.list_scenario_files(ws_root)}


def create_scenario(ws_root, symbol: str, direction: str, target_price: float,
                    target_date: str, notes: str,
                    strategies: tuple[str, ...], *, ts: str | None = None
                    ) -> Scenario:
    """§2.5 次序：產 id → append CREATED → 寫檔 → 重建 groups。"""
    ts = ts or now_utc_iso()
    sid = store.scenario_id(symbol, target_price, target_date,
                            _existing_ids(ws_root))
    sc = Scenario(schema_version=1, id=sid, symbol=symbol, direction=direction,
                  target_price=target_price, target_date=target_date,
                  created_at=ts, notes=notes, group_id=f"G-{symbol}",
                  status="Active", strategies=tuple(strategies))
    store.append_event(ws_root, ts, sid, "SCENARIO_CREATED",
                       dataclasses.asdict(sc))
    store.save_scenario(ws_root, sc)
    _rebuild(ws_root)
    return sc


def _rebuild(ws_root) -> dict:
    scenarios = [store.load_scenario(p)
                 for p in store.list_scenario_files(ws_root)]
    return store.rebuild_groups(ws_root, scenarios, store.read_events(ws_root))


def list_scenarios(ws_root, *, observed: date | None = None) -> list[Scenario]:
    """spec §2.5 載入期對帳（全部冪等）＋ Expired 觀察式轉移 ＋ groups 重建。"""
    ws = Path(ws_root)
    (ws / "scenarios").mkdir(parents=True, exist_ok=True)
    observed = observed or ny_today()
    events = store.read_events(ws_root)

    # 1. DELETED 末事件殘檔 → 完成刪除（冪等）
    dead = {e["scenario_id"] for e in events if e["event"] == "SCENARIO_DELETED"
            if store.project_status(events, e["scenario_id"]) is None}
    for sid in dead:
        p = store.scenario_path(ws_root, sid)
        if p.exists():
            p.unlink()
        rdir = ws / "results" / sid
        if rdir.is_dir():
            shutil.rmtree(rdir)

    # 2. 載入 scenario 檔（CREATED 無檔 → 自然忽略：只迭代存在的檔）
    scenarios = [store.load_scenario(p)
                 for p in store.list_scenario_files(ws_root)]

    # 3. 快取驗證/崩潰窗修復（竄改 → WorkspaceIntegrityError 上拋）
    scenarios = [store.reconcile_status(ws_root, sc, events)
                 for sc in scenarios]

    # 4. Expired 觀察式轉移（觀察日 > target_date 且 Active）
    out = []
    for sc in scenarios:
        if (sc.status == "Active"
                and observed > date.fromisoformat(sc.target_date)):
            sc = store.change_status(
                ws_root, now_utc_iso(), sc, "Expired",
                reason="target_date 已過", by="system",
                extra_payload={"observed_at": observed.isoformat()})
        out.append(sc)

    # 5. groups 無條件重建（快取全量可重建）
    store.rebuild_groups(ws_root, out, store.read_events(ws_root))
    return sorted(out, key=lambda s: (s.symbol, s.target_date, s.id))


def set_status(ws_root, sid: str, to: str, reason: str,
               *, ts: str | None = None) -> Scenario:
    """變更前必先對帳（崩潰窗修復／竄改拋錯）——不信任快取直接轉移。"""
    events = store.read_events(ws_root)
    sc = store.reconcile_status(
        ws_root, store.load_scenario(store.scenario_path(ws_root, sid)), events)
    return store.change_status(ws_root, ts or now_utc_iso(), sc, to, reason)


def confirm_relation(ws_root, group_id: str, pair: tuple[str, str],
                     choice: str, *, ts: str | None = None) -> None:
    if choice not in RELATION_CHOICES:
        raise ValueError(f"未知關係選項: {choice}")
    store.append_event(ws_root, ts or now_utc_iso(), None,
                       "GROUP_RELATION_CONFIRMED",
                       {"group_id": group_id, "pair": list(pair),
                        "choice": choice})
    _rebuild(ws_root)


def delete_scenario(ws_root, sid: str, *, ts: str | None = None) -> None:
    """§2.5 次序：先事件、後刪檔、後重建群組；殘局由 list_scenarios 補完。"""
    store.append_event(ws_root, ts or now_utc_iso(), sid,
                       "SCENARIO_DELETED", {})
    p = store.scenario_path(ws_root, sid)
    if p.exists():
        p.unlink()
    rdir = Path(ws_root) / "results" / sid
    if rdir.is_dir():
        shutil.rmtree(rdir)
    _rebuild(ws_root)


def load_groups(ws_root) -> dict:
    """spec §2.5: groups.json 任何過時/缺失 → 無條件重建（快取全量可重建，
    絕不回傳磁碟上可能被手改的版本）。"""
    return _rebuild(ws_root)


def default_direction(symbol: str, target_price: float,
                      snapshots_dir="snapshots") -> str | None:
    """建立表單預設方向：該 symbol 最近 snapshot 的 spot 推得（spec §2.2）。"""
    d = Path(snapshots_dir)
    if not d.is_dir():
        return None
    files = sorted(d.glob(f"{symbol}_*.json"))
    if not files:
        return None
    snap = load_snapshot(files[-1])
    return "bullish" if target_price > snap.spot else "bearish"
