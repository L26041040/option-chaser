"""Core data structures and errors. Stdlib only."""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1


class SnapshotSchemaError(Exception):
    pass


class FetchError(Exception):
    pass


class ParamError(Exception):
    pass


@dataclass(frozen=True)
class OptionContract:
    contract_symbol: str
    strike: float
    expiry: str  # YYYY-MM-DD
    bid: float | None
    ask: float | None
    last: float | None
    volume: int
    open_interest: int
    implied_volatility: float | None


@dataclass(frozen=True)
class ChainSnapshot:
    schema_version: int
    symbol: str
    fetched_at: str  # ISO 8601 with UTC offset
    spot: float
    source: str
    contracts: tuple[OptionContract, ...]


@dataclass(frozen=True)
class AnalysisParams:
    target_price: float
    target_date: str  # YYYY-MM-DD
    min_days_after: int = 0
    min_expiry: str | None = None
    top: int = 3
    iv_shifts: tuple[float, ...] = (-0.2, 0.0, 0.2)  # normalized: 0 included, sorted
    rate: float = 0.04
    min_oi: int = 10
    min_volume: int = 0
    max_spread_pct: float = 0.15
    spread_floor: float = 0.10
    delta_bands: tuple[float, float] = (0.35, 0.65)
    min_return: float = 0.0
    delay_days: int = 0  # resolved from effective_buffer at param resolution
    force: bool = False


@dataclass(frozen=True)
class FilterStageResult:
    label: str
    removed: int


@dataclass(frozen=True)
class FilterReport:
    total: int
    stages: tuple[FilterStageResult, ...]
    passed: int
