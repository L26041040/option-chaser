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
from typing import Iterable

from . import __version__
from .models import AnalysisParams, ChainSnapshot
from .ranking import spread_baseline_return
from .report import disclaimer_text, methodology_lines
from .scenarios import natural_cost
from .service import AnalysisResult, CandidateView, candidate_key, valuation_key
from .timeframe import TargetMonth
from .valuation import SpreadValuation, guidance_judgments, spread_guidance_judgments
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

def representative_candidate(view: dict | None) -> dict | None:
    """劇本清單卡片要的「代表候選」完整身分（MVP-v2／#77、#78）：策略、
    各腿履約價與權別、實際到期日、報酬率。

    候選來源與 `best_return()` 逐字相同、同一次走訪：baseline 期（最接近
    目標年月的到期日）在 `expiry_groups` 裡那一組的 `rows`，取
    `baseline_return` 最高者（QA1-03／#30 修好的那條規則）。

    刻意**不讀** `comparison`／`results`／`expiry_top10`：`comparison` 每筆
    是該策略在**全部到期日**裡的全域最佳（`_comparison()`），拿它當來源會
    讓「baseline 期」這個限定詞失效，等於讓 QA1-03 的舊 bug 在這一層重演。
    這裡只在 baseline 期那組 `rows` 內取最大值，不做任何金融計算、不牽動
    哪些策略／候選進得了排名——排名結果早由 `expiry_groups` 決定好了。

    baseline 期不在 `expiry_groups`、該期零合格候選、或 view 本身為
    `None`（無快照）→ `None`（附錄 A10.2／A12：綠燈＋「—」，不是一組
    假的候選）。

    腿的順序沿用序列化層既有慣例：`[0]=long`（買腿），`[1]=short`（賣腿，
    僅價差策略才有）；只回顯示要用的履約價與權別，不重複整份 `_leg()`
    （報價／IV／量能等欄位留在詳細頁的完整 view，這裡只是清單卡片用）。
    """
    if view is None:
        return None
    group = next((g for g in view["expiry_groups"]
                 if g["expiry"] == view.get("baseline_expiry")), None)
    if group is None or not group["rows"]:
        return None
    best_row = max(group["rows"],
                   key=lambda row: row["candidate"]["baseline_return"])
    candidate = best_row["candidate"]
    return {
        "strategy": best_row["strategy"],
        "legs": [{"strike": leg["strike"], "option_type": leg["option_type"]}
                 for leg in candidate["legs"]],
        "expiry": group["expiry"],
        "baseline_return": candidate["baseline_return"],
    }


def best_return(view: dict | None) -> float | None:
    """baseline 期（最接近目標年月的到期日）本身的最高收益率——與 Step 2
    主圖同一口徑（QA1-03／#30：先前誤取全部到期日的全域最大值，較早到期日
    剛好報酬更高時卡片數字就會跟主圖對不上）。

    由 `representative_candidate()` 導出而非各走各的一次走訪
    （MVP-v2／#77、#78）：兩者必須在結構上不可能對不上，卡片上的報酬率
    才會永遠是它旁邊那組履約價真正算出來的數字。
    """
    rep = representative_candidate(view)
    return rep["baseline_return"] if rep is not None else None


def spot(view: dict | None) -> float | None:
    """這次分析當下的標的現價（`view["meta"]["spot"]`）。

    QA 修正：劇本庫卡片要顯示現價，才看得出「目標價／最高／最低離現在
    多遠」——沒有它，清單上一排目標價等於沒有比較基準。與 `best_return()`
    同一種角色：清單只要這一個數字，卻不該為它把整份 view 撈回來，所以
    落盤成獨立欄位；規則仍只有這一份純函式。

    view 為 `None`（從未成功分析過）或形狀不含 meta.spot（理論上不會，
    防禦性）時回 `None`——卡片據此顯示「—」，不是 0。
    """
    if not view:
        return None
    value = (view.get("meta") or {}).get("spot")
    return value if isinstance(value, (int, float)) else None


def _history_entry(sv: SpreadValuation, expiry: str, rank_in_expiry: int) -> dict:
    """T9（#23，附錄A7）：全部有效候選的歷史五欄位之三（成本／收益率／期內
    名次）；另外兩欄（更新時間、標的價）不逐候選重複，共用父層 `analyzed_at`／
    `meta.spot`（既有設計，`_candidate()` 對完整 CandidateView 同樣不重複）。
    不建 CandidateView：這裡只需要輕量欄位，沒有 Heatmap 矩陣（附錄A10.3）。"""
    return {
        "candidate_key": valuation_key(sv),
        "expiry": expiry,
        # T12（附錄A14.2）：成本口徑統一走 natural_cost（＝最差成交假設），
        # 與 `_candidate()` 的 `natural_cost`／`cap_per` 同一條路徑，不直接
        # 讀 `sv.net_worst`（spread 之下數值恆等，但少一層轉譯依賴）。
        "cost": natural_cost(sv),
        "baseline_return": spread_baseline_return(sv),
        "rank_in_expiry": rank_in_expiry,
    }


def _leg(c) -> dict:
    return {"contract_symbol": c.contract_symbol, "option_type": c.option_type,
            "strike": c.strike, "expiry": c.expiry, "bid": c.bid,
            "ask": c.ask, "iv": c.implied_volatility, "volume": c.volume,
            "open_interest": c.open_interest}


def spread_cost_history(views: Iterable[dict], candidate_key: str) -> list[dict]:
    """V9（#57）：跨一個劇本的全部歷史快照（序列化 view dict），依 Spread
    身份鍵（`candidate_key`，已含策略／買賣履約價／到期日，見
    `service.valuation_key`）聚合出時間序列。

    與 Streamlit 版 `workspace.spread_history()`（T11／#25）同一套語意，
    只是輸入從「讀檔案路徑」換成「呼叫端已經備妥的 view dict 序列」——
    新架構（`api_app`）的 `Storage.result_history()` 回傳的是
    `ResultRecord`（`.view` 已經是這個形狀），沒有檔案路徑可讀；
    `workspace.spread_history()` 改為委派本函式，兩邊共用同一份邏輯。

    唯讀聚合：只讀 view dict，不寫入、不改變任何計算或保存範圍。某次
    快照的 `all_candidates` 找不到這個鍵（該候選當次不是有效候選，例如
    缺報價被過濾）→ 該筆仍然入列，但 cost／baseline_return／
    rank_in_expiry 皆為 None：如實呈現斷點，不插值、不跳過、不報錯；
    `analyzed_at`／`spot` 仍取自那次成功更新本身。範圍限定 Spread 路徑
    （`all_candidates` 只有 spread 策略填入，T9 附錄A13 既有 MVP 範圍）。
    """
    out = []
    for view in views:
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


def raw_snapshot_json(snap: ChainSnapshot) -> dict:
    """V8（#56）：原始資料（當次快照）——「免得你亂掰我卻查不到證據」
    （QA1-10／#37 原話，延續同一設計目標）。刻意不重用 `_leg()`：那個
    子集是候選腿專用的顯示欄位（省略 `last`），這裡要的是**逐筆合約的
    完整原樣**，跟 CSV 下載（`data.snapshot.snapshot_to_csv`）給的是同一
    份資料、同一組欄位，兩者不該對不上。"""
    return {
        "meta": {"symbol": snap.symbol, "spot": snap.spot,
                 "fetched_at": snap.fetched_at, "source": snap.source,
                 "contract_count": len(snap.contracts)},
        "contracts": [dataclasses.asdict(c) for c in snap.contracts],
    }


def _matrix_to_dict(mv) -> dict:
    """`MatrixView`／`ComparatorView.matrix` 共用的序列化形狀——#115 前
    只有 `CandidateView.matrix` 用得到，抽成小函式避免 comparator 的
    matrix 另外複製一份同樣的三行。"""
    return {"prices": [list(pt) for pt in mv.prices],
           "dates": [list(d) for d in mv.dates],
           "cells": [list(r) for r in mv.cells]}


def _candidate(cv: CandidateView, strategy: str, capital: float | None,
               today: date, anchor: date, p: AnalysisParams) -> dict:
    v = cv.valuation
    if isinstance(v, SpreadValuation):
        legs = [_leg(v.long_leg), _leg(v.short_leg)]   # [0]=long, [1]=short
        mid_cost, expiry = v.net_mid, v.long_leg.expiry
        max_profit, net_delta = v.max_profit, v.net_delta
        guidance_warnings = spread_guidance_judgments(v, p)
    else:
        legs = [_leg(v.contract)]
        mid_cost, expiry = v.mid, v.contract.expiry
        # 與 service._comparison 相同定義（long-call 無上限 → None）
        max_profit = (None if strategy == "long-call"
                      else v.contract.strike - v.contract.ask)
        net_delta = v.delta
        guidance_warnings = guidance_judgments(v, p)
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
        # MVP V3（#104，spec #102 決策 F）：`quote_warning`（選取閘門用的
        # 複合旗標）不對外序列化——只有 `wide_spread_warning`（僅
        # is_spread_wide）進契約，前端 UI 一律改接這個顯示旗標。
        "wide_spread_warning": cv.wide_spread_warning,
        # FB5-03（#64）：獨立欄位，不併進 wide_spread_warning——見 service.py
        # 的 CandidateView.monotonicity_warning 欄位註解。
        "monotonicity_warning": cv.monotonicity_warning,
        # #113（spec #117 contracts 表）：這組候選的估值是否經過 carry
        # 校準。False 時前端必須說得出「這組估值未經 carry 校準」。
        "carry_calibrated": cv.carry_calibrated,
        "theta_day_rate": cv.theta_day_rate,
        "vega_per_pt": cv.vega_per_pt,
        "decay_30d_return": cv.decay_30d_return,
        # MVP V3（#112，spec #102 決策 H）：這組候選實際用於估值的利率與
        # 年期——Analysis Report → Model & Assumptions 的 Rate used／
        # Tenor 兩項，取代原本只顯示「用了某條曲線」的模糊呈現。
        "rate_used": cv.rate_used,
        "rate_tenor_years": cv.rate_tenor_years,
        "net_delta": net_delta,
        "breakeven": v.breakeven,
        "max_profit": max_profit,
        "effective_leverage": v.effective_leverage,
        # V8（#56，spec R1 §4.2 A2）：買價指引天花板 L2/L3——純文字報告
        # 早就在印，只是沒進契約。單腿另有 L1（＝ `floor_value`，保守
        # 底線），本票依票上 A2 表只列的兩項不補 L1（v.l1 對單腿等於
        # `floor_value`，價差沒有 L1）。
        "l2": v.l2, "l3": v.l3,
        # V8：買 Ask 超過哪些天花板的警示文字（`valuation.guidance_
        # judgments`／`spread_guidance_judgments`，同一組門檻早就用來
        # 決定純文字報告的「- 警示: ...」行，這裡只是把回傳值序列化）。
        "guidance_warnings": guidance_warnings,
        # V8：評語「代價」（cons）——「優點」pros 依 R1 §4.2 C 裁示不補
        # 序列化（與關鍵指標表重複，見 CLAUDE.md V8 記錄）。
        "cons": list(cv.cons),
        # D1（#14）：Long Call 追平價格——None＝不適用（單腳）或無法計算
        # （同履約價 Call 報價缺失），render 層負責區分並顯示。
        "catchup_price": cv.catchup_price,
        # 檢視回饋：這個生成式的迴圈變數原本借用 `p`，跟本函式自己的
        # `p: AnalysisParams` 參數同名，在同一個函式體裡容易讓人誤讀成
        # 同一個東西（雖然 Python 3 生成式有獨立作用域，實際不會互相
        # 污染）。改用 `pt`（price point）避免這個混淆。
        "matrix": _matrix_to_dict(cv.matrix),
        # #115（spec #117 §4）：Crossover 對照——None＝單腿候選（無意義）
        # 或買腿報價缺失（結構上不該發生的防禦性 case）。matrix 用同一個
        # `_matrix_to_dict` 序列化，跟主 matrix 同形狀。
        "comparator": ({"option_type": cv.comparator.option_type,
                       "strike": cv.comparator.strike,
                       "expiry": cv.comparator.expiry,
                       "cost": cv.comparator.cost,
                       "matrix": _matrix_to_dict(cv.comparator.matrix)}
                      if cv.comparator is not None else None),
        # spec §3 新增四組（乘除法與日期差，非估值邏輯）
        "capital_per_contract": cap_per,
        # V7（#55）：劇本區間三價位對照。兩端都沒設時是空陣列，呈現層據此
        # 不畫這一區（不是畫一個只有一格的表）。
        "price_ladder": [{"label": pt.label, "price": pt.price, "return": pt.ret}
                         for pt in cv.price_ladder],
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
        # V8（#56，spec R1 §4.2 A2）：`_candidate()` 現在還要算買價指引
        # 警示（`guidance_judgments`／`spread_guidance_judgments`），兩者
        # 只讀 `p.iv_shifts`，不讀 `p.strategy`——`base` 不必為每個 `r`
        # 各自替換 strategy 也正確，跟既有 `base.anchor` 的用法一致。
        return _candidate(cv, strategy, capital, today, base.anchor, base)

    def strat(r):
        return {
            "strategy": r.strategy, "status": r.status, "message": r.message,
            "n_qualified": r.n_qualified,
            # FB4-01（#60）：合約層級的抓到／通過筆數。不可由 `n_qualified`
            # 反推——spread 路徑的 `n_qualified` 是**配對數**
            # （`service._spread_result` 取 `pair_report.passed`）。
            "filter_report": ({"total": r.filter_report.total,
                               "passed": r.filter_report.passed}
                              if r.filter_report else None),
            "filter_stages": ([{"label": s.label, "removed": s.removed,
                               "filter_class": s.filter_class}
                               for s in r.filter_report.stages]
                              if r.filter_report else []),
            # FB5-04（#65，spec #61）：C 類品質標示在整個合格池裡的計數
            # （`filters.quality_flag_counts()`）——跟 `filter_stages`
            # （A／B 兩類「排除」）並排但語意不同，前端據此分開呈現。
            "quality_flags": [{"label": qf.label, "count": qf.count}
                              for qf in r.quality_flags],
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
            # V8（#56，spec R1 §4.1）：新版型「⑥ 方法與假設」／「⑦ 免責
            # 聲明」要獨立顯示、不再是 `report_text` 尾端的散文——內容
            # 出自同一個 `report.py`（單一事實來源），只是拆成欄位。
            # 每個策略各印一份而非全域一份：`p.spread_floor`／
            # `max_spread_pct` 理論上策略間相同，但方法論文字本就是
            # 逐 `render()`／`render_spreads()` 呼叫產生的，跟著 `r` 走
            # 才不會在契約裡無中生有一個「全域方法論」概念。
            "methodology_text": "\n".join(methodology_lines(base)).strip("\n"),
            "disclaimer_text": disclaimer_text(),
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
        # T10（#24，附錄A8.5）：詳細頁進頁預設——baseline 期本身、及其第 1 名。
        # 與 `default_selection`（v4 舊有、跨到期日全域最高報酬避警示語意）
        # 刻意分開，兩者服務不同的產品決策。
        "baseline_expiry": result.baseline_expiry,
        "baseline_selection": (list(result.baseline_selection)
                               if result.baseline_selection else None),
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


def list_result_paths(ws_root, scenario_id: str) -> list[Path]:
    """該劇本全部歷史快照檔案，依檔名（＝fetched_at，字典序＝時間序）排序。
    `results/<sid>/` 目錄結構的唯一存取點——`latest_result_path()`／
    `workspace.spread_history()`（T11，#25）都透過這裡讀，不各自 glob。"""
    d = Path(ws_root) / "results" / scenario_id
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


def latest_result_path(ws_root, scenario_id: str) -> Path | None:
    files = list_result_paths(ws_root, scenario_id)
    return files[-1] if files else None
