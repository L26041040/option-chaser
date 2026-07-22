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

from . import service, store
from .data.snapshot import load_snapshot
from .models import AnalysisParams
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


def _request_for(sc: Scenario) -> service.AnalysisRequest:
    """base_params 自 scenario 欄位；其餘 CLI 預設（spec §4）。"""
    base = AnalysisParams(target_price=sc.target_price,
                          target_date=sc.target_date,
                          strategy=sc.strategies[0])
    return service.AnalysisRequest(symbol=sc.symbol, base_params=base,
                                   strategies=tuple(sc.strategies))


def analyze_scenario(ws_root, sid: str, progress=None, *,
                     snapshot_path: str | None = None,
                     ts: str | None = None) -> Path:
    """§2.5 例外次序：result 檔先落盤，ANALYSIS_COMPLETED 後補。
    分析前必先對帳：邏輯已刪（殘檔）→ 拋錯；崩潰窗 → 修復後續行。"""
    events = store.read_events(ws_root)
    if store.project_status(events, sid) is None:
        raise store.WorkspaceIntegrityError(f"劇本 {sid} 不存在或已刪除")
    sc = store.reconcile_status(
        ws_root, store.load_scenario(store.scenario_path(ws_root, sid)), events)
    req = _request_for(sc)
    if snapshot_path is None:
        result = service.run(req, progress)
    else:
        result = service.run_offline(req, snapshot_path, progress)
    capital = store.load_constraints(ws_root)["total_capital"]
    view = store.serialize_result(result, sc.id, capital)
    path = store.save_result(ws_root, sc.id, view)
    store.append_event(ws_root, ts or now_utc_iso(), sc.id,
                       "ANALYSIS_COMPLETED",
                       {"result_path": str(path),
                        "snapshot_ref": view["snapshot_ref"]})   # 完整物件（spec §2.3）
    return path


def analyze_group(ws_root, group_id: str, progress=None, *,
                  snapshot_path: str | None = None,
                  ts: str | None = None) -> list[Path]:
    """一次抓取共用 snapshot；全成員 result 的 snapshot_ref.path 相同（spec §4）。"""
    groups = load_groups(ws_root)
    group = next(g for g in groups["groups"] if g["id"] == group_id)
    if snapshot_path is None:
        _, snapshot_path = service.fetch_and_save(group["symbol"])
    return [analyze_scenario(ws_root, sid, progress,
                             snapshot_path=snapshot_path, ts=ts)
            for sid in group["members"]]


def latest_result(ws_root, sid: str) -> dict | None:
    path = store.latest_result_path(ws_root, sid)
    return store.load_result(path) if path else None


def scenario_exists(ws_root, symbol: str, target_price: float,
                    target_date: str) -> str | None:
    """base id（無撞名後綴）是否已有劇本檔。供 UI 撞名預檢與 adopt_result 共用。"""
    base_id = store.scenario_id(symbol, target_price, target_date, set())
    return base_id if store.scenario_path(ws_root, base_id).exists() else None


def adopt_result(ws_root, result: service.AnalysisResult, notes: str = "",
                 *, ts: str | None = None) -> tuple[Scenario, Path]:
    """v6 spec §1.2：快速試算「保存為劇本」——重用當次分析結果，不重新分析。
    §2.5 次序：create_scenario（事件先行）→ result 檔先落盤 → ANALYSIS_COMPLETED。"""
    ts = ts or now_utc_iso()
    req = result.request
    base = req.base_params
    symbol, target_price, target_date = req.symbol, base.target_price, base.target_date
    if scenario_exists(ws_root, symbol, target_price, target_date) is not None:
        raise ValueError(f"劇本已存在：{symbol} {target_price:g} {target_date}")
    direction = "bullish" if target_price > result.meta.spot else "bearish"
    sc = create_scenario(ws_root, symbol=symbol, direction=direction,
                         target_price=target_price, target_date=target_date,
                         notes=notes, strategies=req.strategies, ts=ts)
    capital = store.load_constraints(ws_root)["total_capital"]
    view = store.serialize_result(result, sc.id, capital)
    path = store.save_result(ws_root, sc.id, view)
    store.append_event(ws_root, ts, sc.id, "ANALYSIS_COMPLETED",
                       {"result_path": str(path),
                        "snapshot_ref": view["snapshot_ref"]})
    return sc, path
