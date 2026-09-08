"""記憶體儲存假體（V2／#50）——測試用，程序結束即消失。

也是 `DATABASE_URL` 未設定時的退路：這種情況在正式部署上等於設定錯誤，
因此 `/api/health` 會如實回報 `storage: "memory"`，讓「資料不會存活」
這件事在畫面上看得見，而不是靜默丟失。
"""
from __future__ import annotations

import dataclasses
import json
from collections import deque
from contextlib import contextmanager

from . import (ChainBackoffEntry, ContractHistory, DataSourceSettings,
               DividendCacheEntry, IvBackfillRun, IvObservation, MetricEntry,
               NarrowHistoryEntry, ProviderCredential, ProviderVerification,
               RateCacheEntry, ResultFactContext, ResultRecord, ResultSummary,
               Scenario, ScenarioExists, TreasuryYearCacheEntry, require_owner)
from ..diagnostics import RETENTION_LIMIT, DiagnosticEvent
from ..identity import SOLO_OWNER
from ..metrics import retention_cutoff


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
        # SCALE-09（#261）：鍵是三個 identity 欄組成的 tuple，逐字對應
        # PK `(scenario_id, analyzed_at, candidate_key)`。
        self._narrow_history: dict[tuple[str, str, str], NarrowHistoryEntry] = {}
        # 舊表（SCALE-13／#264 之前）——凍結但仍可讀，供 read-through
        # 相容分支使用；這個方法起不再寫入。
        self._settings: DataSourceSettings | None = None
        self._credentials: dict[str, ProviderCredential] = {}
        self._verifications: dict[str, ProviderVerification] = {}
        # 新表（SCALE-13／#264）：per-owner 正確形狀。settings 鍵是
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

    # ---------- Narrow visible-candidate history（SCALE-09／#261） ----------

    def save_narrow_history(self, entries) -> None:
        # 比照既有 `save_result()`／`save_snapshot()`：寫入本身不強制
        # `owner_id` 非 None（沿用 SCALE-06 Expand 階段「寫入寬鬆、
        # 讀取才強制」的既有慣例，讓 `backfill_missing_owner_ids()`
        # 有辦法在測試裡模擬既有無 owner 舊列——`get_narrow_history_
        # entry()`／`narrow_history_for_candidate()` 兩個讀取方法已經
        # 強制 `owner` 非 None，正式 production 呼叫端一律傳入解析過
        # 的真實 owner，不依賴這裡的寫入端檢查）。
        for entry in entries:
            key = (entry.scenario_id, entry.analyzed_at, entry.candidate_key)
            self._narrow_history[key] = entry

    def get_narrow_history_entry(
        self, scenario_id: str, analyzed_at: str, candidate_key: str,
        *, owner: str,
    ) -> NarrowHistoryEntry | None:
        owner = require_owner(owner)
        entry = self._narrow_history.get((scenario_id, analyzed_at, candidate_key))
        if entry is None or entry.owner_id != owner:
            return None
        return entry

    def narrow_history_for_candidate(
        self, scenario_id: str, candidate_key: str, analyzed_ats, *, owner: str,
    ) -> dict[str, float | None]:
        owner = require_owner(owner)
        wanted = set(analyzed_ats)
        return {at: entry.cost
                for (sid, at, key), entry in self._narrow_history.items()
                if sid == scenario_id and key == candidate_key
                and at in wanted and entry.owner_id == owner}

    def result_spot_timestamps(
        self, scenario_id: str, *, owner: str,
    ) -> list[tuple[str, float | None]]:
        owner = require_owner(owner)
        dates = self.result_timestamps(scenario_id, owner=owner)
        out = []
        for at in dates:
            entry = self._snapshots.get((scenario_id, at))
            spot = None
            if entry is not None and entry[1] == owner:
                spot = entry[0].get("spot")
            out.append((at, spot))
        return out

    def result_fact_contexts(
        self, scenario_id: str, analyzed_ats, *, owner: str,
    ) -> dict[str, ResultFactContext]:
        owner = require_owner(owner)
        wanted = set(analyzed_ats)
        out: dict[str, ResultFactContext] = {}
        for at, rec in self._results.get(scenario_id, {}).items():
            if at not in wanted or rec.owner_id != owner:
                continue
            out[at] = ResultFactContext(
                scenario_id=scenario_id, analyzed_at=at,
                resolved_params=rec.resolved_params,
                requested_strategies=rec.requested_strategies,
                engine_version=rec.engine_version,
                view_schema_version=rec.view_schema_version,
                history_replay_version=rec.history_replay_version,
                snapshot_source=rec.snapshot_source)
        return out

    def snapshots_batch(
        self, scenario_id: str, analyzed_ats, *, owner: str,
    ) -> dict[str, dict]:
        owner = require_owner(owner)
        wanted = set(analyzed_ats)
        out: dict[str, dict] = {}
        for (sid, at), (snap, snap_owner) in self._snapshots.items():
            if sid == scenario_id and at in wanted and snap_owner == owner:
                out[at] = snap
        return out

    # ---------- 資料源設定與 credential（Settings／#124，owner 化 SCALE-13／#264） ----------

    def get_settings(self, *, owner: str) -> DataSourceSettings | None:
        owner = require_owner(owner)
        got = self._owner_settings.get(owner)
        if got is not None:
            return got
        # read-through：新表沒有，舊表（全站唯一一份）有——只有這個
        # owner 是 solo owner 時舊資料才有意義（舊表結構上沒有 owner
        # 維度，只能代表這個唯一存在過的 owner）。
        if owner == SOLO_OWNER and self._settings is not None:
            migrated = dataclasses.replace(self._settings, owner_id=owner)
            self._owner_settings[owner] = migrated   # write-through
            return migrated
        return None

    def save_settings(self, settings: DataSourceSettings) -> None:
        owner = require_owner(settings.owner_id)
        self._owner_settings[owner] = settings
        # 舊表這個方法起不再寫入（write-forward-only，見 Protocol
        # docstring）——`self._settings` 因此在這次呼叫之後會落後，
        # 這是刻意接受的代價：若真的切回舊程式碼路徑，讀到的會是遷移
        # 當下那一刻的值，不是最新值。

    def get_credential(self, provider: str, *, owner: str) -> ProviderCredential | None:
        owner = require_owner(owner)
        got = self._owner_credentials.get((owner, provider))
        if got is not None:
            return got
        if owner == SOLO_OWNER:
            legacy = self._credentials.get(provider)
            if legacy is not None:
                migrated = dataclasses.replace(legacy, owner_id=owner)
                self._owner_credentials[(owner, provider)] = migrated
                return migrated
        return None

    def save_credential(self, cred: ProviderCredential) -> None:
        owner = require_owner(cred.owner_id)
        self._owner_credentials[(owner, cred.provider)] = cred
        # 舊表這個方法起不再寫入（write-forward-only）。

    def delete_credential(self, provider: str, *, owner: str) -> bool:
        owner = require_owner(owner)
        # 驗證結果跟著走：它講的是「那把 token 能不能用」。
        self._owner_verifications.pop((owner, provider), None)
        new_removed = self._owner_credentials.pop((owner, provider), None) is not None
        old_removed = False
        if owner == SOLO_OWNER:
            # 新舊兩張表都要清——否則使用者明確刪除後，下次讀取的
            # read-through 還是會把舊表裡沒被清掉的資料復活（殭屍
            # 復活風險，見 Protocol docstring）。
            self._verifications.pop(provider, None)
            old_removed = self._credentials.pop(provider, None) is not None
        return new_removed or old_removed

    def get_verification(self, provider: str, *, owner: str) -> ProviderVerification | None:
        owner = require_owner(owner)
        got = self._owner_verifications.get((owner, provider))
        if got is not None:
            return got
        if owner == SOLO_OWNER:
            legacy = self._verifications.get(provider)
            if legacy is not None:
                migrated = dataclasses.replace(legacy, owner_id=owner)
                self._owner_verifications[(owner, provider)] = migrated
                return migrated
        return None

    def save_verification(self, v: ProviderVerification) -> None:
        owner = require_owner(v.owner_id)
        self._owner_verifications[(owner, v.provider)] = v
        # 舊表這個方法起不再寫入（write-forward-only）。

    def backfill_settings_to_owner(self, owner: str) -> dict[str, int]:
        counts = {"settings": 0, "credentials": 0, "verifications": 0}
        if self._settings is not None and owner not in self._owner_settings:
            self._owner_settings[owner] = dataclasses.replace(
                self._settings, owner_id=owner)
            counts["settings"] += 1
        for provider, cred in self._credentials.items():
            if (owner, provider) not in self._owner_credentials:
                self._owner_credentials[(owner, provider)] = dataclasses.replace(
                    cred, owner_id=owner)
                counts["credentials"] += 1
        for provider, v in self._verifications.items():
            if (owner, provider) not in self._owner_verifications:
                self._owner_verifications[(owner, provider)] = dataclasses.replace(
                    v, owner_id=owner)
                counts["verifications"] += 1
        return counts

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
        """6 張 row-scoped 表各自獨立掃描、只補 `owner_id is None` 的列
        ——條件式判斷讓重跑天然冪等（第二次呼叫全部回 0），不需要另外
        記錄「跑到哪裡了」的游標狀態。`narrow_history`（SCALE-14／
        #265 補上，`/code-review` Spec 軸抓到的真缺口）：SCALE-09 出貨
        時漏接 `owner_id`，這張表沒有搭其他遷移欄位可以順手帶上這個
        backfill，需要獨立列出來。"""
        counts = {"scenarios": 0, "results": 0, "snapshots": 0,
                 "events": 0, "diagnostics": 0, "narrow_history": 0}

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

        for key, entry in list(self._narrow_history.items()):
            if entry.owner_id is None:
                self._narrow_history[key] = dataclasses.replace(
                    entry, owner_id=owner_id)
                counts["narrow_history"] += 1

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
