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
from .models import AnalysisParams
from .store import Scenario
from .timeframe import TargetMonth, ensure_month_open, month_is_over
from .vocabulary import RELATION_CHOICES

_EASTERN = ZoneInfo("America/New_York")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ny_today() -> date:
    return datetime.now(_EASTERN).date()


def _existing_ids(ws_root) -> set[str]:
    return {p.stem for p in store.list_scenario_files(ws_root)}


def create_scenario(ws_root, symbol: str, direction: str, target_price: float,
                    target_month: str, notes: str,
                    strategies: tuple[str, ...], *, ts: str | None = None,
                    observed: date | None = None) -> Scenario:
    """§2.5 次序：驗證年月 → 產 id → append CREATED → 寫檔 → 重建 groups。

    月級驗證：目標月已過完 → 拒絕（生下來就過期的劇本不該存在）；當月 → 允許。
    """
    ts = ts or now_utc_iso()
    ensure_month_open(TargetMonth.from_key(target_month), observed or ny_today())
    sid = store.scenario_id(symbol, target_price, target_month,
                            _existing_ids(ws_root))
    sc = Scenario(schema_version=store.SCENARIO_SCHEMA_VERSION, id=sid,
                  symbol=symbol, direction=direction,
                  target_price=target_price, target_month=target_month,
                  created_at=ts, notes=notes, group_id=f"G-{symbol}",
                  status="Active", strategies=tuple(strategies))
    store.append_event(ws_root, ts, sid, "SCENARIO_CREATED",
                       dataclasses.asdict(sc))
    store.save_scenario(ws_root, sc)
    _rebuild(ws_root)
    return sc


def _load_live(ws_root, events: list[dict]) -> list[Scenario]:
    """磁碟上的劇本檔，減去已被軟刪除者——移除後檔案仍在，只是不再現身。"""
    live = []
    for p in store.list_scenario_files(ws_root):
        sc = store.load_scenario(p)
        if not store.is_removed(events, sc.id):
            live.append(sc)
    return live


def _rebuild(ws_root) -> dict:
    events = store.read_events(ws_root)
    return store.rebuild_groups(ws_root, _load_live(ws_root, events), events)


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
    scenarios = _load_live(ws_root, events)

    # 3. 快取驗證/崩潰窗修復（竄改 → WorkspaceIntegrityError 上拋）
    scenarios = [store.reconcile_status(ws_root, sc, events)
                 for sc in scenarios]

    # 4. Expired 觀察式轉移（目標月最後一天過完且 Active——整個目標月內都有效）
    out = []
    for sc in scenarios:
        if (sc.status == "Active"
                and month_is_over(TargetMonth.from_key(sc.target_month),
                                  observed)):
            sc = store.change_status(
                ws_root, now_utc_iso(), sc, "Expired",
                reason="目標月已過完", by="system",
                extra_payload={"observed_at": observed.isoformat()})
        out.append(sc)

    # 5. groups 無條件重建（快取全量可重建）
    store.rebuild_groups(ws_root, out, store.read_events(ws_root))
    return sorted(out, key=lambda s: (s.symbol, s.target_month, s.id))


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


def remove_scenario(ws_root, sid: str, *, ts: str | None = None) -> None:
    """附錄 A8.2 手動移除＝事件溯源軟刪除：只寫一筆事件，檔案一個都不動。

    清單、群組與刷新都改由 `store.is_removed` 投影決定，因此移除後該劇本自然
    退場，而 events.jsonl 與 results/ 下的歷史仍可完整回溯。已移除者再移除
    不追加同義事件（冪等）。硬刪除仍在 `delete_scenario`，兩者不互相取代。
    """
    if store.is_removed(store.read_events(ws_root), sid):
        return
    store.append_event(ws_root, ts or now_utc_iso(), sid,
                       "SCENARIO_REMOVED", {})
    _rebuild(ws_root)


def load_groups(ws_root) -> dict:
    """spec §2.5: groups.json 任何過時/缺失 → 無條件重建（快取全量可重建，
    絕不回傳磁碟上可能被手改的版本）。"""
    return _rebuild(ws_root)


def _request_for(sc: Scenario) -> service.AnalysisRequest:
    """base_params 自 scenario 欄位；其餘 CLI 預設（spec §4）。"""
    base = AnalysisParams(target_price=sc.target_price,
                          target_month=sc.target_month,
                          strategy=sc.strategies[0])
    return service.AnalysisRequest(symbol=sc.symbol, base_params=base,
                                   strategies=tuple(sc.strategies))


def analyze_scenario(ws_root, sid: str, progress=None, *,
                     snapshot_path: str | None = None,
                     ts: str | None = None,
                     rate_curve_loader=None) -> Path:
    """§2.5 例外次序：result 檔先落盤，ANALYSIS_COMPLETED 後補。
    分析前必先對帳：邏輯已刪（殘檔）→ 拋錯；崩潰窗 → 修復後續行。
    `rate_curve_loader` 僅供 networked 呼叫端（analyze_group 剛抓完 chain）
    傳入以啟用 T12 利率曲線；直接給 snapshot_path 的離線重放維持零網路。"""
    events = store.read_events(ws_root)
    if store.project_status(events, sid) is None:
        raise store.WorkspaceIntegrityError(f"劇本 {sid} 不存在、已刪除或已移除")
    sc = store.reconcile_status(
        ws_root, store.load_scenario(store.scenario_path(ws_root, sid)), events)
    req = _request_for(sc)
    if snapshot_path is None:
        result = service.run(req, progress)
    else:
        result = service.run_offline(req, snapshot_path, progress,
                                     rate_curve_loader=rate_curve_loader)
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
    loader = None
    if snapshot_path is None:
        _, snapshot_path = service.fetch_and_save(group["symbol"])
        loader = service.default_rate_curve_loader   # 剛抓完 chain＝網路情境
    return [analyze_scenario(ws_root, sid, progress,
                             snapshot_path=snapshot_path, ts=ts,
                             rate_curve_loader=loader)
            for sid in group["members"]]


def latest_result(ws_root, sid: str) -> dict | None:
    path = store.latest_result_path(ws_root, sid)
    return store.load_result(path) if path else None


def spread_history(ws_root, sid: str, candidate_key: str) -> list[dict]:
    """T11（#25）：跨該劇本全部歷史快照，依 Spread 身份鍵（`candidate_key`，
    已含到期日／買入履約價／賣出履約價；symbol 由劇本本身固定，見 T9
    `service.valuation_key`）聚合出時間序列。

    唯讀聚合：只讀取既有快照檔案，不寫入、不改變刷新的計算或保存範圍——
    T9 附錄A7 已保證每份快照全量保存該次全部有效候選，這裡只是換一種
    切法（按 Spread 身份橫向串接，而非單次快照縱向羅列）。

    某次快照的 `all_candidates` 找不到這個鍵（該候選當次不是有效候選，
    例如缺報價被過濾——非關鍵資料失敗，見附錄A12）→ 該筆仍然入列，
    但 cost／baseline_return／rank_in_expiry 皆為 None：如實呈現斷點，
    不插值、不跳過、不報錯；`analyzed_at`／`spot` 仍取自那次成功更新本身。
    """
    out = []
    for p in store.list_result_paths(ws_root, sid):
        view = store.load_result(p)
        entry = next((e for r in view["results"]
                     for e in r.get("all_candidates", [])
                     if e["candidate_key"] == candidate_key), None)
        out.append({
            "analyzed_at": view["analyzed_at"],
            "spot": view["meta"]["spot"],
            "cost": entry["cost"] if entry else None,
            "baseline_return": entry["baseline_return"] if entry else None,
            "rank_in_expiry": entry["rank_in_expiry"] if entry else None,
        })
    return out


# ---------- 劇本級狀態燈號（需求六／T6，純函式） ----------

SIGNAL_GREEN = "green"
SIGNAL_YELLOW = "yellow"
SIGNAL_RED = "red"
SIGNAL_UNKNOWN = "unknown"   # 尚未有過任何一次刷新，燈號無從判讀（非三色之一）

# 「刷新結果」的三種輸入態——與燈號顏色刻意分開命名，避免混淆「這次發生了
# 什麼」與「因此要顯示什麼顏色」。
REFRESH_OK = "ok"                            # 本次完整刷新成功
REFRESH_CRITICAL_FAILURE = "critical_failure"  # 關鍵資料（標的價格／到期日
                                              # option chain）取得或分析失敗
REFRESH_NEVER = "never"                      # 這張劇本從未成功或失敗過刷新


def scenario_signal(target_month: TargetMonth, observed: date,
                    refresh: str) -> str:
    """劇本級狀態燈號（需求六）：輸入刷新結果與日曆，輸出顏色。

    紅燈只問日曆（目標月最後一天是否已過完），不問任何刷新結果，且優先於
    綠與黃（附錄 A2.4：失效劇本不會偽裝成活的）。

    個別合約缺報價屬於候選過濾（`filters.py`/`FilterReport`），走另一個不
    拋例外的通道，因此根本不會、也不該被轉譯成 `REFRESH_CRITICAL_FAILURE`
    餵進來——只有整個到期日 chain 或標的價格等關鍵資料失敗（`FetchError`）
    才算。`REFRESH_NEVER` 對應尚無任何成功快照的劇本，回傳 `SIGNAL_UNKNOWN`
    （非三色之一，卡片上的中性佔位）。
    """
    if month_is_over(target_month, observed):
        return SIGNAL_RED
    if refresh == REFRESH_CRITICAL_FAILURE:
        return SIGNAL_YELLOW
    if refresh == REFRESH_NEVER:
        return SIGNAL_UNKNOWN
    return SIGNAL_GREEN


@dataclasses.dataclass(frozen=True)
class ScenarioCard:
    """左側清單卡片的完整內容——恰五項，多一項都不放（需求五）。

    刻意不含腿別、成本、佔本金等技術數字：那些屬於詳細頁。
    """
    id: str
    symbol: str
    target_price: float
    target_month: str
    best_return: float | None   # 無快照／零候選 → None（卡片顯示「—」）
    signal: str


def _best_return(view: dict | None) -> float | None:
    """該次分析結果中最高的「目標達成並持有至到期收益率」。

    baseline_return 是 service 已預算好的欄位（T3 起＝各 Spread 自身到期日的
    內在價值），這裡只取最大值，不做任何金融計算。掃描 `expiry_best`（每個
    到期日的最佳）與 `candidates`（整體前三名）的聯集，最大值必在其中。

    無快照 → None（附錄 A8.1）；抓取成功但零候選 → 同樣 None，不是 0%
    （附錄 A10.2：那是綠燈＋「—」，不是一個真的收益率）。
    """
    if view is None:
        return None
    returns = [c["baseline_return"]
               for r in view["results"] if r["status"] == "ok"
               for c in (*r["candidates"], *r["expiry_best"])]
    return max(returns) if returns else None


def _card_sort_key(card: ScenarioCard) -> tuple[int, float]:
    """紅燈沉底；其餘依 best_return 降序；無值者（無快照或零候選）居中，
    落在有值者之後、紅燈之前——同一分組內若同樣無值，靠 sort 的穩定性
    沿用呼叫端傳入的原始順序（需求五、附錄A6、T8）。"""
    if card.signal == SIGNAL_RED:
        group = 2
    elif card.best_return is None:
        group = 1
    else:
        group = 0
    value = card.best_return if card.best_return is not None else float("-inf")
    return (group, -value)


def sort_cards(cards: list[ScenarioCard]) -> list[ScenarioCard]:
    """左側清單排序（需求五／附錄A6／T8）：聚合函式，只重排卡片視圖——不碰
    `list_scenarios()` 既有的 (symbol, target_month, id) 回傳順序。

    規則：
    - 依各卡片 `best_return`（黃燈已是上一份成功快照的值，見 `card_of`）降序。
    - 紅燈一律沉底，組內仍依 `best_return`（最後已知值）降序。
    - 無值（無快照或零候選，`best_return is None`）者排在有值者之後、紅燈之前。
    """
    return sorted(cards, key=_card_sort_key)


def card_of(sc: Scenario, view: dict | None, *, observed: date | None = None,
           critical_failure: bool = False) -> ScenarioCard:
    """劇本＋其最新分析結果 → 卡片。view 為 None 代表尚無成功快照。

    `critical_failure`＝目前這次（session 內）刷新是否為關鍵資料（標的價格／
    到期日 option chain）取得或分析失敗——個別合約缺報價的候選過濾走另一個
    不拋例外的通道（`filters.py`），不會、也不該被轉譯成這個旗標（需求六）。
    """
    if critical_failure:
        refresh = REFRESH_CRITICAL_FAILURE
    elif view is None:
        refresh = REFRESH_NEVER
    else:
        refresh = REFRESH_OK
    signal = scenario_signal(TargetMonth.from_key(sc.target_month),
                             observed or ny_today(), refresh)
    return ScenarioCard(id=sc.id, symbol=sc.symbol,
                        target_price=sc.target_price,
                        target_month=sc.target_month,
                        best_return=_best_return(view),
                        signal=signal)
