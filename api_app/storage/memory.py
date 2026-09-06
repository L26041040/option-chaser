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
               ProviderCredential, ProviderVerification, RateCacheEntry,
               ResultFactContext, ResultRecord, ResultSummary, Scenario,
               ScenarioExists, TreasuryYearCacheEntry)
from ..diagnostics import RETENTION_LIMIT, DiagnosticEvent
from ..metrics import retention_cutoff


class MemoryStorage:
    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = {}
        self._results: dict[str, dict[str, ResultRecord]] = {}
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
        self._settings: DataSourceSettings | None = None
        self._credentials: dict[str, ProviderCredential] = {}
        self._verifications: dict[str, ProviderVerification] = {}
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

    def create_scenario(self, sc: Scenario) -> None:
        if sc.id in self._scenarios:
            raise ScenarioExists(sc.id)
        self._scenarios[sc.id] = sc

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        return self._scenarios.get(scenario_id)

    def list_scenarios(self, *, include_archived: bool = False) -> list[Scenario]:
        rows = [s for s in self._scenarios.values()
                if include_archived or s.archived_at is None]
        return sorted(rows, key=lambda s: (s.created_at, s.id))

    def update_scenario(self, sc: Scenario) -> bool:
        if sc.id not in self._scenarios:
            return False
        self._scenarios[sc.id] = sc
        return True

    def clear_results(self, scenario_id: str) -> None:
        self._results.pop(scenario_id, None)
        self._snapshots = {k: v for k, v in self._snapshots.items()
                           if k[0] != scenario_id}

    def archive_scenario(self, scenario_id: str, *, ts: str) -> bool:
        sc = self._scenarios.get(scenario_id)
        if sc is None or sc.archived_at is not None:
            return False
        self._scenarios[scenario_id] = sc.archived(ts)
        return True

    def restore_scenario(self, scenario_id: str, *, ts: str) -> bool:
        sc = self._scenarios.get(scenario_id)
        if sc is None or sc.archived_at is None:
            return False
        self._scenarios[scenario_id] = sc.restored()
        return True

    def delete_scenario(self, scenario_id: str) -> bool:
        sc = self._scenarios.get(scenario_id)
        if sc is None or sc.archived_at is None:
            return False
        del self._scenarios[scenario_id]
        self._results.pop(scenario_id, None)
        self._snapshots = {k: v for k, v in self._snapshots.items()
                           if k[0] != scenario_id}
        self._events = [e for e in self._events if e["scenario_id"] != scenario_id]
        return True

    # ---------- 結果 ----------

    def save_result(self, rec: ResultRecord) -> None:
        self._results.setdefault(rec.scenario_id, {})[rec.analyzed_at] = rec

    def latest_result(self, scenario_id: str) -> ResultRecord | None:
        hist = self.result_history(scenario_id)
        return hist[-1] if hist else None

    def latest_summaries(self) -> dict[str, ResultSummary]:
        out: dict[str, ResultSummary] = {}
        for sid in self._results:
            rec = self.latest_result(sid)
            if rec is not None:
                out[sid] = ResultSummary(
                    analyzed_at=rec.analyzed_at, best_return=rec.best_return,
                    representative_candidate=rec.representative_candidate,
                    spot=rec.spot, per_family=rec.per_family,
                    family_eligibility=rec.family_eligibility)
        return out

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        by_ts = self._results.get(scenario_id, {})
        return [by_ts[k] for k in sorted(by_ts)]

    def result_timestamps(self, scenario_id: str) -> list[str]:
        from_snapshots = {ts for (sid, ts) in self._snapshots if sid == scenario_id}
        from_results = set(self._results.get(scenario_id, {}))
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

    def get_snapshot(self, scenario_id: str, analyzed_at: str) -> dict | None:
        entry = self._snapshots.get((scenario_id, analyzed_at))
        return entry[0] if entry is not None else None

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

    def list_events(self, *, scenario_id: str | None = None) -> list[dict]:
        if scenario_id is None:
            return list(self._events)
        return [e for e in self._events if e["scenario_id"] == scenario_id]

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

    # ---------- 資料源設定與 credential（Settings／#124） ----------

    def get_settings(self) -> DataSourceSettings | None:
        return self._settings

    def save_settings(self, settings: DataSourceSettings) -> None:
        self._settings = settings

    def get_credential(self, provider: str) -> ProviderCredential | None:
        return self._credentials.get(provider)

    def save_credential(self, cred: ProviderCredential) -> None:
        self._credentials[cred.provider] = cred

    def delete_credential(self, provider: str) -> bool:
        # 驗證結果跟著走：它講的是「那把 token 能不能用」。
        self._verifications.pop(provider, None)
        return self._credentials.pop(provider, None) is not None

    def get_verification(self, provider: str) -> ProviderVerification | None:
        return self._verifications.get(provider)

    def save_verification(self, v: ProviderVerification) -> None:
        self._verifications[v.provider] = v

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

    def list_diagnostics(self, *, limit: int = 50) -> list[DiagnosticEvent]:
        # deque 存的是寫入順序（舊→新）；最新在最上要反過來。
        return list(reversed(self._diagnostics))[:limit]

    def clear_diagnostics(self) -> int:
        n = len(self._diagnostics)
        self._diagnostics.clear()
        return n

    # ---------- Ownership A-1 Expand（SCALE-06／#256） ----------

    def backfill_missing_owner_ids(self, owner_id: str) -> dict[str, int]:
        """5 張 row-scoped 表各自獨立掃描、只補 `owner_id is None` 的列
        ——條件式判斷讓重跑天然冪等（第二次呼叫全部回 0），不需要另外
        記錄「跑到哪裡了」的游標狀態。"""
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
                return {"row_count": 0, "total_bytes": None,
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
