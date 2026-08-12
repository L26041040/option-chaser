"""記憶體儲存假體（V2／#50）——測試用，程序結束即消失。

也是 `DATABASE_URL` 未設定時的退路：這種情況在正式部署上等於設定錯誤，
因此 `/api/health` 會如實回報 `storage: "memory"`，讓「資料不會存活」
這件事在畫面上看得見，而不是靜默丟失。
"""
from __future__ import annotations

from . import (DataSourceSettings, DividendCacheEntry, ProviderCredential,
               ProviderVerification, RateCacheEntry, ResultRecord,
               ResultSummary, Scenario, ScenarioExists)


class MemoryStorage:
    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = {}
        self._results: dict[str, dict[str, ResultRecord]] = {}
        self._snapshots: dict[tuple[str, str], dict] = {}
        self._events: list[dict] = []
        self._rate_cache: RateCacheEntry | None = None
        self._dividend_cache: dict[str, DividendCacheEntry] = {}
        self._settings: DataSourceSettings | None = None
        self._credentials: dict[str, ProviderCredential] = {}
        self._verifications: dict[str, ProviderVerification] = {}

    @property
    def kind(self) -> str:
        return "memory"

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
                    spot=rec.spot)
        return out

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        by_ts = self._results.get(scenario_id, {})
        return [by_ts[k] for k in sorted(by_ts)]

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict) -> None:
        self._snapshots[(scenario_id, analyzed_at)] = snapshot

    def get_snapshot(self, scenario_id: str, analyzed_at: str) -> dict | None:
        return self._snapshots.get((scenario_id, analyzed_at))

    # ---------- 事件 ----------

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict) -> None:
        self._events.append({"ts": ts, "scenario_id": scenario_id,
                             "event": event, "payload": payload})

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
