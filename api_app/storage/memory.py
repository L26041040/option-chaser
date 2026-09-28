"""記憶體儲存假體（V2／#50）——測試用，程序結束即消失。

也是 `DATABASE_URL` 未設定時的退路：這種情況在正式部署上等於設定錯誤，
因此 `/api/health` 會如實回報 `storage: "memory"`，讓「資料不會存活」
這件事在畫面上看得見，而不是靜默丟失。
"""
from __future__ import annotations

import copy
import dataclasses
import threading
import json
from collections import deque
from collections.abc import Sequence
from contextlib import contextmanager

from . import (RETIRED_TABLES, SCENARIO_CHILD_TABLES, BrowserIdentity,
               ChainBackoffEntry, ContractHistory,
               DataSourceSettings, DividendCacheEntry, IvBackfillRun,
               IvObservation, LineageReport, MetricEntry, Owner,
               OwnerLifecycleFacts, OwnerMigrationConflict, OwnerSettingsBundle,
               OWNER_RATE_LIMIT_SCOPE, ProviderCredential, ProviderVerification,
               RateCacheEntry, RateLimitBucket,
               ResultFactContext, ResultRecord, ResultSummary, RoleSession,
               Scenario, ScenarioExists, SuperUserAuditEvent,
               TreasuryYearCacheEntry, require_owner,
               settings_bundle_merge_plan)
from ..diagnostics import RETENTION_LIMIT, DiagnosticEvent
from ..metrics import retention_cutoff

# SCALE-01 的 6 個 fact context 欄位——全部齊全的 ledger 列才可以安全地
# 清掉 SCALE-16 之前留下的完整 `view`。
_FACT_FIELDS = ("resolved_params", "requested_strategies", "engine_version",
                "view_schema_version", "history_replay_version",
                "snapshot_source")


class MemoryStorage:
    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = {}
        self._results: dict[str, dict[str, ResultRecord]] = {}
        # SCALE-16（#267，Stage 1-5）：current full-view materialization
        # ——每個 scenario_id 恆定一列，覆寫更新。與上面的
        # `self._results`（historical fact ledger，append-only）分開
        # 儲存：ledger 列的 `view` 恆為 `None`，這裡的 `view` 恆為完整
        # dict。`latest_result()`／`latest_summaries()` 改讀這裡。
        self._current_results: dict[str, ResultRecord] = {}
        # SCALE-06（#256）：value 改成 `(snapshot_dict, owner_id)`——
        # 快照本身是原始 dict（不是像 `Scenario`／`ResultRecord` 那樣的
        # dataclass，沒有欄位可以直接掛 `owner_id`），用 tuple 包一層是
        # 最小改動；`get_snapshot()` 的既有回傳形狀（純 `dict | None`）
        # 因此保持不變，`owner_id` 走新增的 `get_snapshot_owner()`。
        self._snapshots: dict[tuple[str, str], tuple[dict, str | None]] = {}
        self._events: list[dict] = []
        self._rate_cache: RateCacheEntry | None = None
        self._dividend_cache: dict[str, DividendCacheEntry] = {}
        self._treasury_year_cache: dict[int, TreasuryYearCacheEntry] = {}
        self._chain_backoff: dict[str, ChainBackoffEntry] = {}
        # PB-01（#292，Anonymous Public Beta）：owner registry ＋
        # browser identity——鍵分別是 `owner_id`／`token`，兩張表
        # 各自獨立，token 與 owner_id 刻意不是同一個值（見
        # `BrowserIdentity` docstring）。
        self._owners: dict[str, Owner] = {}
        self._browser_identities: dict[str, BrowserIdentity] = {}
        self._claim_lock = threading.Lock()
        # SECURITY-FIX-02：(scope, key, window_seconds, window_start) -> count
        self._rate_limits: dict[tuple[str, str, int, int], int] = {}
        # AUTH-01（#308，三層角色模型）：與 owner registry／browser
        # identity 刻意獨立的第三張表——鍵是 role-session token，值不含
        # 任何 owner_id 關聯（軸一／軸二正交）。
        self._role_sessions: dict[str, RoleSession] = {}
        # PB-10（#301）：append-only、**無** `maxlen`——與
        # `self._diagnostics` 刻意不同的保留政策，見
        # `SuperUserAuditEvent` docstring。
        self._audit_log: list[SuperUserAuditEvent] = []
        # SCALE-13（#264）：per-owner 正確形狀。（legacy singleton 表已在
        # CLAUDE-DB-HYGIENE-002 退役，記憶體假體不再模擬它們。）settings 鍵是
        # `owner_id` 本身；credentials／verifications 鍵是
        # `(owner_id, provider)`。
        self._owner_settings: dict[str, DataSourceSettings] = {}
        self._owner_credentials: dict[tuple[str, str], ProviderCredential] = {}
        self._owner_verifications: dict[tuple[str, str], ProviderVerification] = {}
        # 鍵是 (symbol, 日期)——**沒有 scenario 維度**，見 IvObservation。
        self._iv: dict[tuple[str, str], IvObservation] = {}
        self._iv_runs: dict[str, IvBackfillRun] = {}
        # 鍵是 OCC contract symbol——exact contract identity 本身
        # （HIVT-02／#153），見 ContractHistory。
        self._contract_history: dict[str, ContractHistory] = {}
        # `deque(maxlen=)` 就是 trim-on-write：滿了之後新的一筆自動把
        # 最舊的擠掉，跟 Postgres 那邊的 `DELETE ... OFFSET` 是同一條上限
        # 的兩種實作，契約測試才有意義。
        self._diagnostics: deque[DiagnosticEvent] = deque(maxlen=RETENTION_LIMIT)
        # S0（SCALE-08／#258）：鍵是 (metric, bucket, source, symbol)——
        # 與 `MetricEntry` 的複合主鍵一一對應。
        self._metrics: dict[tuple[str, str, str, str], MetricEntry] = {}
        # `transaction()` 的巢狀深度——只有最外層負責快照／還原。
        self._txn_depth = 0

    @property
    def kind(self) -> str:
        return "memory"

    @contextmanager
    def request_scope(self):
        """T02（#186）：純 no-op——記憶體假體沒有連線可共用，這裡存在
        的唯一理由是讓 `main.py` 的 middleware 走跟 production（Postgres）
        同一條 `with scope():` 分支，而不是 `getattr(..., None)` 拿不到
        就整段跳過。這樣以 `TestClient`＋記憶體假體為主的既有 HTTP 測試
        套件，才真正涵蓋到這段 middleware 控制流（而不只是那幾條
        Postgres-only 的 adapter 層測試）。"""
        yield

    _NON_STATE_ATTRS = ("_claim_lock", "_txn_depth")

    @contextmanager
    def transaction(self):
        """CLAUDE-DB-HYGIENE-002：最外層進入時整份狀態深拷貝一份，區塊內
        拋例外就整份還原——跟 Postgres 的 rollback 同一種「全有或全無」
        語意，契約測試才比得起來。巢狀呼叫併入最外層。"""
        if self._txn_depth:
            self._txn_depth += 1
            try:
                yield
            finally:
                self._txn_depth -= 1
            return
        saved = {k: copy.deepcopy(v) for k, v in self.__dict__.items()
                 if k not in self._NON_STATE_ATTRS}
        self._txn_depth = 1
        try:
            yield
        except BaseException:
            self.__dict__.update(saved)
            raise
        finally:
            self._txn_depth = 0

    # ---------- 劇本 ----------

    def _owned_scenario(self, scenario_id: str, owner: str) -> Scenario | None:
        """五個劇本 CRUD 方法共用的「這個 id 存在且屬於這個 owner」
        判準（`/code-review` Standards 軸抓到的重複邏輯，抽出後五處
        呼叫點只剩各自獨有的額外條件，例如 archive/restore 各自的
        `archived_at` 檢查）。"""
        sc = self._scenarios.get(scenario_id)
        if sc is None or sc.owner_id != owner:
            return None
        return sc

    def create_scenario(self, sc: Scenario) -> None:
        if sc.id in self._scenarios:
            raise ScenarioExists(sc.id)
        self._scenarios[sc.id] = sc

    def get_scenario(self, scenario_id: str, *, owner: str) -> Scenario | None:
        owner = require_owner(owner)
        return self._owned_scenario(scenario_id, owner)

    def list_scenarios(self, *, owner: str | None,
                       include_archived: bool = False) -> list[Scenario]:
        rows = [s for s in self._scenarios.values()
                if (include_archived or s.archived_at is None)
                and (owner is None or s.owner_id == owner)]
        return sorted(rows, key=lambda s: (s.created_at, s.id))

    def update_scenario(self, sc: Scenario, *, owner: str) -> bool:
        owner = require_owner(owner)
        if self._owned_scenario(sc.id, owner) is None:
            return False
        self._scenarios[sc.id] = sc
        return True

    def clear_results(self, scenario_id: str, *, owner: str) -> None:
        owner = require_owner(owner)
        if self._owned_scenario(scenario_id, owner) is None:
            return
        self._results.pop(scenario_id, None)
        self._current_results.pop(scenario_id, None)
        self._snapshots = {k: v for k, v in self._snapshots.items()
                           if k[0] != scenario_id}

    def archive_scenario(self, scenario_id: str, *, owner: str, ts: str) -> bool:
        owner = require_owner(owner)
        sc = self._owned_scenario(scenario_id, owner)
        if sc is None or sc.archived_at is not None:
            return False
        self._scenarios[scenario_id] = sc.archived(ts)
        return True

    def restore_scenario(self, scenario_id: str, *, owner: str, ts: str) -> bool:
        owner = require_owner(owner)
        sc = self._owned_scenario(scenario_id, owner)
        if sc is None or sc.archived_at is None:
            return False
        self._scenarios[scenario_id] = sc.restored()
        return True

    def delete_scenario(self, scenario_id: str, *, owner: str) -> bool:
        owner = require_owner(owner)
        sc = self._owned_scenario(scenario_id, owner)
        if sc is None or sc.archived_at is None:
            return False
        del self._scenarios[scenario_id]
        self._results.pop(scenario_id, None)
        self._current_results.pop(scenario_id, None)
        self._snapshots = {k: v for k, v in self._snapshots.items()
                           if k[0] != scenario_id}
        self._events = [e for e in self._events if e["scenario_id"] != scenario_id]
        return True

    # ---------- 結果 ----------

    def save_result(self, rec: ResultRecord) -> None:
        self._results.setdefault(rec.scenario_id, {})[rec.analyzed_at] = rec

    def save_current_result(self, rec: ResultRecord) -> None:
        self._current_results[rec.scenario_id] = rec

    def latest_result(self, scenario_id: str, *, owner: str) -> ResultRecord | None:
        owner = require_owner(owner)
        rec = self._current_results.get(scenario_id)
        return rec if rec is not None and rec.owner_id == owner else None

    def latest_summaries(self, *, owner: str) -> dict[str, ResultSummary]:
        owner = require_owner(owner)
        return {sid: ResultSummary(
                    analyzed_at=rec.analyzed_at, best_return=rec.best_return,
                    representative_candidate=rec.representative_candidate,
                    spot=rec.spot, per_family=rec.per_family,
                    family_eligibility=rec.family_eligibility)
                for sid, rec in self._current_results.items()
                if rec.owner_id == owner}

    def result_history(self, scenario_id: str, *,
                       owner: str | None) -> list[ResultRecord]:
        by_ts = self._results.get(scenario_id, {})
        rows = [by_ts[k] for k in sorted(by_ts)]
        if owner is None:
            return rows
        return [r for r in rows if r.owner_id == owner]

    def result_timestamps(self, scenario_id: str, *, owner: str) -> list[str]:
        # 兩邊都用各自那張表自己的 `owner_id` 欄位過濾（SCALE-06 早就
        # 讓 `snapshots`／`results` 兩張表各自攜帶這個值），不查父劇本
        # ——與 Postgres 那邊「WHERE 子句上各加一個條件」的既有承諾
        # 同一種形狀，兩後端可直接比對行為。
        owner = require_owner(owner)
        from_snapshots = {ts for (sid, ts), (_snap, o) in self._snapshots.items()
                          if sid == scenario_id and o == owner}
        from_results = {ts for ts, rec in self._results.get(scenario_id, {}).items()
                        if rec.owner_id == owner}
        return sorted(from_snapshots | from_results)

    def result_fact_context(self, scenario_id: str,
                            analyzed_at: str) -> ResultFactContext | None:
        rec = self._results.get(scenario_id, {}).get(analyzed_at)
        if rec is None:
            return None
        return ResultFactContext(
            scenario_id=scenario_id, analyzed_at=analyzed_at,
            resolved_params=rec.resolved_params,
            requested_strategies=rec.requested_strategies,
            engine_version=rec.engine_version,
            view_schema_version=rec.view_schema_version,
            history_replay_version=rec.history_replay_version,
            snapshot_source=rec.snapshot_source)

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict, *, owner_id: str | None = None) -> None:
        self._snapshots[(scenario_id, analyzed_at)] = (snapshot, owner_id)

    def get_snapshot(self, scenario_id: str, analyzed_at: str, *,
                     owner: str) -> dict | None:
        owner = require_owner(owner)
        entry = self._snapshots.get((scenario_id, analyzed_at))
        if entry is None or entry[1] != owner:
            return None
        return entry[0]

    def get_snapshot_owner(self, scenario_id: str,
                           analyzed_at: str) -> str | None:
        entry = self._snapshots.get((scenario_id, analyzed_at))
        return entry[1] if entry is not None else None

    # ---------- 事件 ----------

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict,
                     owner_id: str | None = None) -> None:
        self._events.append({"ts": ts, "scenario_id": scenario_id,
                             "event": event, "payload": payload,
                             "owner_id": owner_id})

    def list_events(self, *, scenario_id: str | None = None,
                    owner: str) -> list[dict]:
        owner = require_owner(owner)
        rows = [e for e in self._events if e.get("owner_id") == owner]
        if scenario_id is None:
            return rows
        return [e for e in rows if e["scenario_id"] == scenario_id]

    # ---------- 利率曲線快取 ----------

    def get_rate_cache(self) -> RateCacheEntry | None:
        return self._rate_cache

    def save_rate_cache(self, entry: RateCacheEntry) -> None:
        self._rate_cache = entry

    # ---------- 配息資料快取（#123，per-symbol） ----------

    def get_dividend_cache(self, symbol: str) -> DividendCacheEntry | None:
        return self._dividend_cache.get(symbol)

    def save_dividend_cache(self, entry: DividendCacheEntry) -> None:
        self._dividend_cache[entry.symbol] = entry

    # ---------- Treasury 曲線列快取（PERF-03／#179，per-year） ----------

    def get_treasury_year_cache(self, year: int) -> TreasuryYearCacheEntry | None:
        return self._treasury_year_cache.get(year)

    def save_treasury_year_cache(self, entry: TreasuryYearCacheEntry) -> None:
        self._treasury_year_cache[entry.year] = entry

    def get_chain_backoff(self, source: str) -> ChainBackoffEntry | None:
        return self._chain_backoff.get(source)

    def save_chain_backoff(self, entry: ChainBackoffEntry) -> None:
        self._chain_backoff[entry.source] = entry

    # ---------- solo → Owner 一次性遷移（PB-03／#295） ----------

    # 搬遷的逐表步驟——依序執行、全部包在 `transaction()` 裡（測試可以把
    # 其中一步換成會拋錯的版本，驗證中途失敗會整批還原）。
    _MIGRATE_STEPS = ("scenarios", "results", "snapshots", "events",
                      "diagnostics", "current_results", "owner_settings",
                      "owner_credentials", "owner_verifications")

    def migrate_owner(self, *, from_owner: str, to_owner: str) -> dict[str, int]:
        with self.transaction():
            conflicts, redundant = settings_bundle_merge_plan(
                self.owner_settings_bundle(from_owner),
                self.owner_settings_bundle(to_owner))
            if conflicts:
                raise OwnerMigrationConflict(conflicts)
            self._drop_redundant_source_rows(from_owner, redundant)
            return {table: getattr(self, f"_migrate_{table}")(
                        from_owner, to_owner, redundant)
                    for table in self._MIGRATE_STEPS}

    def _drop_redundant_source_rows(self, from_owner: str,
                                    redundant: list[str]) -> None:
        """內容跟 target 等價的 source 列：target 已經有同一份，source 那一
        列直接丟掉（視同已經搬過）。"""
        for item in redundant:
            table, _, provider = item.partition(":")
            if table == "owner_settings":
                self._owner_settings.pop(from_owner, None)
            elif table == "owner_credentials":
                self._owner_credentials.pop((from_owner, provider), None)
            elif table == "owner_verifications":
                self._owner_verifications.pop((from_owner, provider), None)

    @staticmethod
    def _redundant_count(table: str, redundant: list[str]) -> int:
        return sum(1 for item in redundant if item.partition(":")[0] == table)

    def _migrate_scenarios(self, frm: str, to: str, _r) -> int:
        n = 0
        for sid, sc in list(self._scenarios.items()):
            if sc.owner_id == frm:
                self._scenarios[sid] = dataclasses.replace(sc, owner_id=to)
                n += 1
        return n

    def _migrate_results(self, frm: str, to: str, _r) -> int:
        n = 0
        for by_ts in self._results.values():
            for ts, rec in list(by_ts.items()):
                if rec.owner_id == frm:
                    by_ts[ts] = dataclasses.replace(rec, owner_id=to)
                    n += 1
        return n

    def _migrate_snapshots(self, frm: str, to: str, _r) -> int:
        n = 0
        for key, (snap, owner_id) in list(self._snapshots.items()):
            if owner_id == frm:
                self._snapshots[key] = (snap, to)
                n += 1
        return n

    def _migrate_events(self, frm: str, to: str, _r) -> int:
        n = 0
        for event in self._events:
            if event.get("owner_id") == frm:
                event["owner_id"] = to
                n += 1
        return n

    def _migrate_diagnostics(self, frm: str, to: str, _r) -> int:
        n = 0
        migrated = deque(maxlen=self._diagnostics.maxlen)
        for ev in self._diagnostics:
            if ev.owner_id == frm:
                ev = dataclasses.replace(ev, owner_id=to)
                n += 1
            migrated.append(ev)
        self._diagnostics = migrated
        return n

    def _migrate_current_results(self, frm: str, to: str, _r) -> int:
        n = 0
        for sid, rec in list(self._current_results.items()):
            if rec.owner_id == frm:
                self._current_results[sid] = dataclasses.replace(rec, owner_id=to)
                n += 1
        return n

    def _migrate_owner_settings(self, frm: str, to: str, redundant) -> int:
        n = self._redundant_count("owner_settings", redundant)
        if frm in self._owner_settings:
            settings = self._owner_settings.pop(frm)
            self._owner_settings[to] = dataclasses.replace(settings, owner_id=to)
            n += 1
        return n

    def _migrate_owner_credentials(self, frm: str, to: str, redundant) -> int:
        n = self._redundant_count("owner_credentials", redundant)
        for key in list(self._owner_credentials):
            if key[0] == frm:
                cred = self._owner_credentials.pop(key)
                self._owner_credentials[(to, key[1])] = dataclasses.replace(
                    cred, owner_id=to)
                n += 1
        return n

    def _migrate_owner_verifications(self, frm: str, to: str, redundant) -> int:
        n = self._redundant_count("owner_verifications", redundant)
        for key in list(self._owner_verifications):
            if key[0] == frm:
                ver = self._owner_verifications.pop(key)
                self._owner_verifications[(to, key[1])] = dataclasses.replace(
                    ver, owner_id=to)
                n += 1
        return n

    # ---------- legacy NULL-owner 劇本血緣救援（CLAUDE-DB-HYGIENE-002） ----------

    def _child_rows(self):
        """`(table, scenario_id, owner_id, setter)`：逐一走訪 4 張劇本子表。
        `setter(new_owner)` 就地改那一列的 owner。"""
        for by_ts in self._results.values():
            for ts, rec in list(by_ts.items()):
                yield ("results", rec.scenario_id, rec.owner_id,
                       lambda o, by_ts=by_ts, ts=ts, rec=rec:
                       by_ts.__setitem__(ts, dataclasses.replace(rec, owner_id=o)))
        for sid, rec in list(self._current_results.items()):
            yield ("current_results", sid, rec.owner_id,
                   lambda o, sid=sid, rec=rec: self._current_results.__setitem__(
                       sid, dataclasses.replace(rec, owner_id=o)))
        for key, (snap, owner_id) in list(self._snapshots.items()):
            yield ("snapshots", key[0], owner_id,
                   lambda o, key=key, snap=snap:
                   self._snapshots.__setitem__(key, (snap, o)))
        for event in self._events:
            if event["scenario_id"] is None:
                continue
            yield ("events", event["scenario_id"], event.get("owner_id"),
                   lambda o, event=event: event.__setitem__("owner_id", o))

    def claim_null_owner_lineage(self, *, to_owner: str, legacy_owners=(),
                                 dry_run: bool = False) -> dict[str, int]:
        to_owner = require_owner(to_owner)
        with self.transaction():
            null_ids = {sid for sid, sc in self._scenarios.items()
                        if sc.owner_id is None}
            allowed = {None, to_owner, *legacy_owners}
            conflicts = sorted({f"scenario_child:{table}:{sid}"
                                for table, sid, owner, _set in self._child_rows()
                                if sid in null_ids and owner not in allowed})
            if conflicts:
                raise OwnerMigrationConflict(conflicts)
            future = {to_owner, *legacy_owners} if dry_run else {to_owner}
            claimed = null_ids | {sid for sid, sc in self._scenarios.items()
                                  if sc.owner_id in future}
            counts = {"scenarios": len(null_ids),
                      **{t: 0 for t in SCENARIO_CHILD_TABLES}}
            for table, sid, owner, setter in list(self._child_rows()):
                if owner is None and sid in claimed:
                    counts[table] += 1
                    if not dry_run:
                        setter(to_owner)
            if not dry_run:
                for sid in null_ids:
                    self._scenarios[sid] = dataclasses.replace(
                        self._scenarios[sid], owner_id=to_owner)
            return counts

    def lineage_report(self, owner_id: str) -> LineageReport:
        owned = {sid for sid, sc in self._scenarios.items()
                 if sc.owner_id == owner_id}
        mismatch = {t: 0 for t in SCENARIO_CHILD_TABLES}
        orphans = {t: 0 for t in SCENARIO_CHILD_TABLES}
        for table, sid, owner, _set in self._child_rows():
            if sid in owned and owner != owner_id:
                mismatch[table] += 1
            if owner == owner_id and sid not in self._scenarios:
                orphans[table] += 1
        return LineageReport(child_owner_mismatch=mismatch, child_orphans=orphans)

    def owner_row_counts(self, owner_id: str | None) -> dict[str, int]:
        return {
            "scenarios": sum(1 for sc in self._scenarios.values()
                             if sc.owner_id == owner_id),
            "results": sum(1 for by_ts in self._results.values()
                           for r in by_ts.values() if r.owner_id == owner_id),
            "snapshots": sum(1 for (_s, o) in self._snapshots.values()
                             if o == owner_id),
            "events": sum(1 for e in self._events if e.get("owner_id") == owner_id),
            "diagnostics": sum(1 for d in self._diagnostics
                               if d.owner_id == owner_id),
            "current_results": sum(1 for r in self._current_results.values()
                                   if r.owner_id == owner_id),
            "owner_settings": int(owner_id in self._owner_settings),
            "owner_credentials": sum(1 for k in self._owner_credentials
                                     if k[0] == owner_id),
            "owner_verifications": sum(1 for k in self._owner_verifications
                                       if k[0] == owner_id),
        }

    def table_row_counts(self) -> dict[str, dict]:
        def entry(n: int) -> dict:
            return {"rows": n, "bytes": None}
        return {
            "scenarios": entry(len(self._scenarios)),
            "results": entry(sum(len(v) for v in self._results.values())),
            "current_results": entry(len(self._current_results)),
            "snapshots": entry(len(self._snapshots)),
            "events": entry(len(self._events)),
            "diagnostics": entry(len(self._diagnostics)),
            "owner_settings": entry(len(self._owner_settings)),
            "owner_credentials": entry(len(self._owner_credentials)),
            "owner_verifications": entry(len(self._owner_verifications)),
            "owners": entry(len(self._owners)),
            "browser_identities": entry(len(self._browser_identities)),
            "role_sessions": entry(len(self._role_sessions)),
            "superuser_audit_log": entry(len(self._audit_log)),
            "rate_limits": entry(len(self._rate_limits)),
            "operational_metrics": entry(len(self._metrics)),
        }

    # ---------- Owner-wide 刪除原語（PB-04／#296） ----------

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}

        removed = [sid for sid, sc in self._scenarios.items()
                  if sc.owner_id == owner_id]
        for sid in removed:
            del self._scenarios[sid]
        counts["scenarios"] = len(removed)

        n = 0
        for sid in list(self._results):
            by_ts = self._results[sid]
            for ts in list(by_ts):
                if by_ts[ts].owner_id == owner_id:
                    del by_ts[ts]
                    n += 1
            if not by_ts:
                del self._results[sid]
        counts["results"] = n

        n = 0
        for key in list(self._snapshots):
            _, snap_owner = self._snapshots[key]
            if snap_owner == owner_id:
                del self._snapshots[key]
                n += 1
        counts["snapshots"] = n

        before = len(self._events)
        self._events = [e for e in self._events if e.get("owner_id") != owner_id]
        counts["events"] = before - len(self._events)

        before = len(self._diagnostics)
        remaining_diag = deque(
            (e for e in self._diagnostics if e.owner_id != owner_id),
            maxlen=self._diagnostics.maxlen)
        counts["diagnostics"] = before - len(remaining_diag)
        self._diagnostics = remaining_diag

        removed_cur = [sid for sid, rec in self._current_results.items()
                      if rec.owner_id == owner_id]
        for sid in removed_cur:
            del self._current_results[sid]
        counts["current_results"] = len(removed_cur)

        n = 1 if self._owner_settings.pop(owner_id, None) is not None else 0
        counts["owner_settings"] = n

        n = 0
        for key in list(self._owner_credentials):
            if key[0] == owner_id:
                del self._owner_credentials[key]
                n += 1
        counts["owner_credentials"] = n

        n = 0
        for key in list(self._owner_verifications):
            if key[0] == owner_id:
                del self._owner_verifications[key]
                n += 1
        counts["owner_verifications"] = n

        dead = [slot for slot in self._rate_limits
                if slot[0] == OWNER_RATE_LIMIT_SCOPE and slot[1] == owner_id]
        for slot in dead:
            del self._rate_limits[slot]
        counts["rate_limits"] = len(dead)

        n = 0
        for token in list(self._browser_identities):
            if self._browser_identities[token].owner_id == owner_id:
                del self._browser_identities[token]
                n += 1
        counts["browser_identities"] = n

        n = 1 if self._owners.pop(owner_id, None) is not None else 0
        counts["owners"] = n

        return counts

    def reset_beta_data(self, *,
                        keep_metrics: Sequence[tuple[str, str]] = ()) -> dict[str, int]:
        with self.transaction():
            kept = {oid for oid, o in self._owners.items() if o.protected}
            counts = {
                "scenarios": len(self._scenarios),
                "results": sum(len(v) for v in self._results.values()),
                "current_results": len(self._current_results),
                "snapshots": len(self._snapshots),
                "events": len(self._events),
                "diagnostics": len(self._diagnostics),
            }
            self._scenarios.clear()
            self._results.clear()
            self._current_results.clear()
            self._snapshots.clear()
            self._events = []
            self._diagnostics.clear()

            def drop(table: dict, owner_of) -> int:
                dead = [k for k, v in table.items() if owner_of(k, v) not in kept]
                for k in dead:
                    del table[k]
                return len(dead)

            counts["owner_settings"] = drop(self._owner_settings, lambda k, v: k)
            counts["owner_credentials"] = drop(self._owner_credentials,
                                               lambda k, v: k[0])
            counts["owner_verifications"] = drop(self._owner_verifications,
                                                 lambda k, v: k[0])
            counts["browser_identities"] = drop(self._browser_identities,
                                                lambda k, v: v.owner_id)
            counts["owners"] = drop(self._owners, lambda k, v: k)
            active = [oid for oid, o in self._owners.items()
                      if o.last_activity_at is not None]
            for oid in active:
                self._owners[oid] = dataclasses.replace(
                    self._owners[oid], last_activity_at=None)
            counts["owner_activity"] = len(active)
            counts["rate_limits"] = len(self._rate_limits)
            self._rate_limits.clear()
            keep = set(keep_metrics)
            dead_metrics = [k for k in self._metrics if (k[0], k[1]) not in keep]
            for k in dead_metrics:
                del self._metrics[k]
            counts["operational_metrics"] = len(dead_metrics)
        return counts

    # ---------- Owner registry ＋ Browser Identity（PB-01／#292） ----------

    def get_owner(self, owner_id: str) -> Owner | None:
        return self._owners.get(owner_id)

    def resolve_owner_by_token(self, token: str) -> str | None:
        identity = self._browser_identities.get(token)
        return identity.owner_id if identity else None

    def create_owner_with_token(self, owner: Owner,
                                identity: BrowserIdentity) -> None:
        self._owners[owner.owner_id] = owner
        self._browser_identities[identity.token] = identity

    def claim_browser_token(self, token: str, owner: Owner, *,
                            now: str) -> tuple[str, bool]:
        # 與 postgres 的 PK 等價：一把鎖保證「檢查＋寫入」不被並發
        # 請求（TestClient 的多執行緒）切開。
        with self._claim_lock:
            existing = self._browser_identities.get(token)
            if existing is not None:
                return existing.owner_id, False
            self._owners[owner.owner_id] = owner
            self._browser_identities[token] = BrowserIdentity(
                token=token, owner_id=owner.owner_id,
                issued_at=now, last_seen_at=now)
            return owner.owner_id, True

    def owner_lifecycle_facts(self) -> list[OwnerLifecycleFacts]:
        last_seen: dict[str, str] = {}
        for identity in self._browser_identities.values():
            prev = last_seen.get(identity.owner_id)
            if prev is None or identity.last_seen_at > prev:
                last_seen[identity.owner_id] = identity.last_seen_at
        with_scenarios = {sc.owner_id for sc in self._scenarios.values()}
        with_settings = set(self._owner_settings)
        with_credentials = {owner_id for owner_id, _ in self._owner_credentials}
        facts = [OwnerLifecycleFacts(
                     owner_id=o.owner_id, created_at=o.created_at,
                     last_seen_at=last_seen.get(o.owner_id),
                     has_data=(o.owner_id in with_scenarios
                               or o.owner_id in with_settings
                               or o.owner_id in with_credentials),
                     protected=o.protected)
                 for o in self._owners.values()]
        return sorted(facts, key=lambda f: (f.created_at, f.owner_id))

    def rate_limit_consume(self, buckets: Sequence[RateLimitBucket]) -> int | None:
        with self._claim_lock:
            slots = [(b.scope, b.key, b.window_seconds, b.window_start)
                     for b in buckets]
            for i, (slot, b) in enumerate(zip(slots, buckets)):
                if self._rate_limits.get(slot, 0) >= b.limit:
                    return i
            for slot in slots:
                self._rate_limits[slot] = self._rate_limits.get(slot, 0) + 1
        return None

    def purge_rate_limits(self, *, before_epoch: int) -> int:
        with self._claim_lock:
            dead = [slot for slot in self._rate_limits
                    if slot[3] + slot[2] < before_epoch]
            for slot in dead:
                del self._rate_limits[slot]
        return len(dead)

    def touch_browser_identity(self, token: str, *, now: str) -> bool:
        identity = self._browser_identities.get(token)
        if identity is None:
            return False
        self._browser_identities[token] = dataclasses.replace(
            identity, last_seen_at=now)
        return True

    def touch_owner_activity(self, owner_id: str, *, now: str) -> None:
        owner = self._owners.get(owner_id)
        if owner is None:
            return
        self._owners[owner_id] = dataclasses.replace(
            owner, last_activity_at=now)

    def set_owner_protected(self, owner_id: str, protected: bool) -> None:
        owner = self._owners.get(owner_id)
        if owner is None:
            return
        self._owners[owner_id] = dataclasses.replace(
            owner, protected=protected)

    def list_owners(self) -> list[Owner]:
        return list(self._owners.values())

    def list_protected_owners(self) -> list[Owner]:
        return [o for o in self._owners.values() if o.protected]

    # ---------- Role session（AUTH-01／#308，三層角色模型） ----------

    def create_role_session(self, session: RoleSession) -> None:
        self._role_sessions[session.token] = session

    def resolve_role_session(self, token: str) -> RoleSession | None:
        session = self._role_sessions.get(token)
        if session is None or session.revoked_at is not None:
            return None
        return session

    def revoke_role_session(self, token: str, *, now: str) -> bool:
        session = self._role_sessions.get(token)
        if session is None or session.revoked_at is not None:
            return False
        self._role_sessions[token] = dataclasses.replace(
            session, revoked_at=now)
        return True

    # ---------- Super User audit trail（PB-10／#301） ----------

    def append_audit_event(self, event: SuperUserAuditEvent) -> None:
        self._audit_log.append(event)

    def list_audit_events(self, *, limit: int = 200) -> list[SuperUserAuditEvent]:
        return list(reversed(self._audit_log))[:limit]

    # ---------- 資料源設定與 credential（Settings／#124，owner 化 SCALE-13／#264） ----------

    def get_settings(self, *, owner: str) -> DataSourceSettings | None:
        owner = require_owner(owner)
        return self._owner_settings.get(owner)

    def save_settings(self, settings: DataSourceSettings) -> None:
        owner = require_owner(settings.owner_id)
        self._owner_settings[owner] = settings

    def get_credential(self, provider: str, *, owner: str) -> ProviderCredential | None:
        owner = require_owner(owner)
        return self._owner_credentials.get((owner, provider))

    def save_credential(self, cred: ProviderCredential) -> None:
        owner = require_owner(cred.owner_id)
        self._owner_credentials[(owner, cred.provider)] = cred

    def delete_credential(self, provider: str, *, owner: str) -> bool:
        owner = require_owner(owner)
        # 驗證結果跟著走：它講的是「那把 token 能不能用」。
        self._owner_verifications.pop((owner, provider), None)
        return self._owner_credentials.pop((owner, provider), None) is not None

    def get_verification(self, provider: str, *, owner: str) -> ProviderVerification | None:
        owner = require_owner(owner)
        return self._owner_verifications.get((owner, provider))

    def save_verification(self, v: ProviderVerification) -> None:
        owner = require_owner(v.owner_id)
        self._owner_verifications[(owner, v.provider)] = v

    def owner_settings_bundle(self, owner_id: str) -> OwnerSettingsBundle:
        return OwnerSettingsBundle(
            settings=self._owner_settings.get(owner_id),
            credentials={p: c for (o, p), c in self._owner_credentials.items()
                         if o == owner_id},
            verifications={p: v for (o, p), v in self._owner_verifications.items()
                           if o == owner_id})

    def legacy_settings_bundle(self) -> OwnerSettingsBundle | None:
        # 記憶體假體從來沒有 legacy singleton 表。
        return None

    def adopt_legacy_settings(self, owner: str) -> dict[str, int]:
        return {"settings": 0, "credentials": 0, "verifications": 0}

    # ---------- 歷史 IV 觀測快取（#129，per-symbol） ----------

    def save_iv_observation(self, obs: IvObservation) -> None:
        self._iv[(obs.symbol, obs.observed_on)] = obs

    def iv_observation_dates(self, symbol: str) -> list[str]:
        return sorted(d for (sym, d) in self._iv if sym == symbol)

    def iv_observations(self, symbol: str) -> list[IvObservation]:
        return [self._iv[(symbol, d)] for d in self.iv_observation_dates(symbol)]

    def get_iv_backfill_run(self, symbol: str) -> IvBackfillRun | None:
        return self._iv_runs.get(symbol)

    def save_iv_backfill_run(self, run: IvBackfillRun) -> None:
        self._iv_runs[run.symbol] = run

    # ---------- Exact-contract 歷史 IV 快取（HIVT-02／#153） ----------

    def get_contract_history(self, contract_symbol: str) -> ContractHistory | None:
        return self._contract_history.get(contract_symbol)

    def save_contract_history(self, history: ContractHistory) -> None:
        self._contract_history[history.contract_symbol] = history

    # ---------- Application diagnostics（DG-02／#145） ----------

    def append_diagnostic(self, event: DiagnosticEvent) -> None:
        self._diagnostics.append(event)

    def append_diagnostics(self, events: list[DiagnosticEvent]) -> None:
        # `deque(maxlen=...)` 的 `extend()` 逐一 push、超過上限時左端
        # 自動擠掉最舊的——跟逐筆呼叫 `append_diagnostic()` 的 trim
        # 效果完全一致，只是一次呼叫做完。
        self._diagnostics.extend(events)

    def list_diagnostics(self, *, limit: int = 50,
                         owner: str) -> list[DiagnosticEvent]:
        owner = require_owner(owner)
        # deque 存的是寫入順序（舊→新）；最新在最上要反過來，owner 過濾
        # 在反轉之後做（跟反轉順序無關，先過濾後反轉結果相同，這裡選
        # 反轉在前只是沿用既有寫法的順序）。
        return [e for e in reversed(self._diagnostics)
               if e.owner_id == owner][:limit]

    def clear_diagnostics(self, *, owner: str) -> int:
        owner = require_owner(owner)
        kept = deque((e for e in self._diagnostics if e.owner_id != owner),
                    maxlen=RETENTION_LIMIT)
        removed = len(self._diagnostics) - len(kept)
        self._diagnostics = kept
        return removed

    # ---------- Ownership A-1 Expand（SCALE-06／#256） ----------

    def backfill_missing_owner_ids(self, owner_id: str) -> dict[str, int]:
        """5 張 row-scoped 表各自獨立掃描、只補 `owner_id is None` 的列
        ——條件式判斷讓重跑天然冪等（第二次呼叫全部回 0），不需要另外
        記錄「跑到哪裡了」的游標狀態。SW-12（#342）：原本第 6 張表
        `narrow_history` 隨 Spread 淨成本走勢功能整個退休一併移除。"""
        counts = {"scenarios": 0, "results": 0, "snapshots": 0,
                 "events": 0, "diagnostics": 0}

        for sid, sc in list(self._scenarios.items()):
            if sc.owner_id is None:
                self._scenarios[sid] = dataclasses.replace(sc, owner_id=owner_id)
                counts["scenarios"] += 1

        for by_ts in self._results.values():
            for ts, rec in list(by_ts.items()):
                if rec.owner_id is None:
                    by_ts[ts] = dataclasses.replace(rec, owner_id=owner_id)
                    counts["results"] += 1

        for key, (snap, owner) in list(self._snapshots.items()):
            if owner is None:
                self._snapshots[key] = (snap, owner_id)
                counts["snapshots"] += 1

        for e in self._events:
            if e.get("owner_id") is None:
                e["owner_id"] = owner_id
                counts["events"] += 1

        for i in range(len(self._diagnostics)):
            d = self._diagnostics[i]
            if d.owner_id is None:
                self._diagnostics[i] = dataclasses.replace(d, owner_id=owner_id)
                counts["diagnostics"] += 1

        return counts

    # ---------- Ownership A-1 Contract（SCALE-13／#264） ----------

    def owner_id_null_counts(self) -> dict[str, int]:
        scenarios = sum(1 for sc in self._scenarios.values()
                        if sc.owner_id is None)
        results = sum(1 for by_ts in self._results.values()
                     for rec in by_ts.values() if rec.owner_id is None)
        snapshots = sum(1 for (_snap, owner) in self._snapshots.values()
                        if owner is None)
        events = sum(1 for e in self._events if e.get("owner_id") is None)
        diagnostics = sum(1 for d in self._diagnostics if d.owner_id is None)
        # 3 張新表的 key 本身就含 owner_id（settings 是 dict key，
        # credentials／verifications 是 tuple key 的第一個元素）——
        # 結構上不可能存在 owner_id 為 None 的項目，恆為 0。
        return {"scenarios": scenarios, "results": results,
               "snapshots": snapshots, "events": events,
               "diagnostics": diagnostics, "owner_settings": 0,
               "owner_credentials": 0, "owner_verifications": 0}

    # ---------- S0 最小可觀測性（SCALE-08／#258） ----------

    def record_metric(self, metric: str, bucket: str, *, source: str = "",
                      symbol: str = "", count: int = 0,
                      amount: float = 0.0) -> None:
        key = (metric, bucket, source, symbol)
        existing = self._metrics.get(key)
        if existing is None:
            self._metrics[key] = MetricEntry(
                metric=metric, bucket=bucket, source=source, symbol=symbol,
                count=count, total=amount, max_value=amount)
        else:
            self._metrics[key] = dataclasses.replace(
                existing, count=existing.count + count,
                total=existing.total + amount,
                max_value=max(existing.max_value, amount))

        # trim-on-write：同一個 metric 底下比 cutoff 更舊的桶整批清掉。
        cutoff = retention_cutoff(bucket)
        for k in [k for k in self._metrics
                 if k[0] == metric and k[1] < cutoff]:
            del self._metrics[k]

    def metric_summary(self) -> list[MetricEntry]:
        return list(self._metrics.values())

    def metric_total(self, metric: str, bucket: str) -> int:
        return sum(e.count for e in self._metrics.values()
                  if e.metric == metric and e.bucket == bucket)

    def table_size_metrics(self) -> dict:
        def _stats(records: list[dict]) -> dict:
            if not records:
                # `total_bytes`（「這張表現在佔多少空間」）對空表是良好
                # 定義的 0——跟 Postgres 對空表回真實非零頁面配置一樣，
                # 兩者都是「有答案」，只是這裡沒有真正的頁面可算，回 0
                # 是誠實的近似值。`avg_row_bytes`／`max_row_bytes`（單列
                # 大小的統計量）對零列沒有數學上有意義的答案，維持
                # `None`——這是 `/code-review` SCALE-08 抓到的真缺口：
                # 原本 `total_bytes` 也回 `None`，跟 Postgres 對空表的
                # 行為不一致。
                return {"row_count": 0, "total_bytes": 0,
                       "avg_row_bytes": None, "max_row_bytes": None}
            # 記憶體假體沒有真正的磁碟頁面/TOAST——用 JSON 序列化長度
            # 當近似值（跟正式 Postgres 的實際落盤大小不會逐位元相同，
            # 但足夠回答「大概多大、有沒有持續變大」這個 S0 要問的
            # 問題；真正的量測基準是 Postgres adapter 那一份）。
            sizes = [len(json.dumps(r, default=str)) for r in records]
            return {"row_count": len(records), "total_bytes": sum(sizes),
                   "avg_row_bytes": sum(sizes) / len(sizes),
                   "max_row_bytes": max(sizes)}

        result_views = [dataclasses.asdict(r)
                        for by_ts in self._results.values()
                        for r in by_ts.values()]
        snapshot_dicts = [snap for (snap, _owner) in self._snapshots.values()]
        return {"results": _stats(result_views),
               "snapshots": _stats(snapshot_dicts)}

    def scenario_count_total(self) -> int:
        return len(self._scenarios)

    # ---------- 資料生命週期 retention（CLAUDE-DB-HYGIENE-002） ----------

    def snapshot_timestamps(self, scenario_id: str, *, owner: str) -> list[str]:
        owner = require_owner(owner)
        return sorted(ts for (sid, ts), (_snap, o) in self._snapshots.items()
                      if sid == scenario_id and o == owner)

    def purge_snapshots(self, *, historical_since: str, max_historical: int,
                        dry_run: bool = False) -> int:
        by_scenario: dict[str, list[str]] = {}
        for sid, ts in self._snapshots:
            by_scenario.setdefault(sid, []).append(ts)
        doomed: list[tuple[str, str]] = []
        for sid, stamps in by_scenario.items():
            stamps.sort(reverse=True)
            pinned = {stamps[0]}
            current = self._current_results.get(sid)
            if current is not None:
                pinned.add(current.analyzed_at)
            historical = [ts for ts in stamps if ts not in pinned]
            for rank, ts in enumerate(historical):
                if rank >= max_historical or ts < historical_since:
                    doomed.append((sid, ts))
        if not dry_run:
            for key in doomed:
                del self._snapshots[key]
        return len(doomed)

    @staticmethod
    def _fact_complete(rec: ResultRecord) -> bool:
        return all(getattr(rec, f) is not None for f in _FACT_FIELDS)

    def result_view_stats(self) -> dict[str, int]:
        with_view = [r for by_ts in self._results.values()
                     for r in by_ts.values() if r.view is not None]
        clearable = sum(1 for r in with_view if self._fact_complete(r))
        return {"with_view": len(with_view),
                "missing_fact_context": len(with_view) - clearable,
                "clearable": clearable}

    def clear_historical_result_views(self, *, dry_run: bool = False) -> int:
        n = 0
        for by_ts in self._results.values():
            for ts, rec in list(by_ts.items()):
                if rec.view is not None and self._fact_complete(rec):
                    n += 1
                    if not dry_run:
                        by_ts[ts] = dataclasses.replace(rec, view=None)
        return n

    def purge_role_sessions(self, *, revoked_before: str, issued_before: str,
                            dry_run: bool = False) -> int:
        doomed = [t for t, s in self._role_sessions.items()
                  if (s.revoked_at is not None and s.revoked_at < revoked_before)
                  or s.issued_at < issued_before]
        if not dry_run:
            for t in doomed:
                del self._role_sessions[t]
        return len(doomed)

    def purge_audit_events(self, *, before: str, dry_run: bool = False) -> int:
        kept = [e for e in self._audit_log if e.ts >= before]
        n = len(self._audit_log) - len(kept)
        if not dry_run:
            self._audit_log = kept
        return n

    def purge_events(self, *, before: str, dry_run: bool = False) -> int:
        kept = [e for e in self._events if e["ts"] >= before]
        n = len(self._events) - len(kept)
        if not dry_run:
            self._events = kept
        return n

    def retired_tables_present(self) -> list[str]:
        return []

    def drop_retired_tables(self, tables) -> list[str]:
        unknown = set(tables) - set(RETIRED_TABLES)
        if unknown:
            raise ValueError(f"不是已退役的表：{sorted(unknown)}")
        return []
