"""Core data structures and errors. Stdlib only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SCHEMA_VERSION = 2


class SnapshotSchemaError(Exception):
    pass


class FetchError(Exception):
    pass


class ParamError(Exception):
    pass


@dataclass(frozen=True)
class OptionContract:
    contract_symbol: str
    option_type: str
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
    """使用者主張的劇本參數。

    時間語意是**月級**的：`target_month`（YYYY-MM）是唯一的時間欄位，刻意不存在
    任何可被填入單一日期的目標日期欄位（附錄 A9 守則）。舊表面需要一個參考日時，
    一律取衍生的 `anchor`——它由年月純日曆算出，無法被外部覆寫、也不持久化。
    """

    target_price: float
    target_month: str  # YYYY-MM
    strategy: str = "long-call"
    top: int = 3
    iv_shifts: tuple[float, ...] = (-0.2, 0.0, 0.2)  # normalized: 0 included, sorted
    rate: float = 0.04
    # T12（附錄 A14.1）利率三欄：`rate` 是明示值或 fallback 常數；
    # `rate_explicit` 由 CLI 在使用者明示 --rate 時設起（跳過整條曲線管線）；
    # `rate_by_expiry`/`rate_note` 由 service 依「分析日→各到期日」年期自
    # Treasury 曲線解出（每腿自身剩餘年期，附錄 A14.1），使用者不直接填。
    rate_explicit: bool = False
    rate_by_expiry: tuple[tuple[str, float], ...] = ()
    rate_note: str = ""
    min_oi: int = 10
    min_volume: int = 0
    max_spread_pct: float = 0.15
    spread_floor: float = 0.10
    delta_bands: tuple[float, float] = (0.35, 0.65)
    min_return: float = 0.0
    force: bool = False
    matrix_all: bool = False

    @property
    def anchor(self) -> date:
        """目標月的日曆錨點（該月第三個星期五）。

        附錄 A9 授權的唯一例外：CLI 報告、單腳買價指引、情境曲線、days_to_target
        等舊表面需要一個參考日時取本值。是**衍生值**不是欄位——沒有任何入口能把
        它設成別的日子，也不會出現在 `dataclasses.asdict()` 的持久化結果裡。
        """
        from .timeframe import TargetMonth, calendar_anchor   # 避免模組循環匯入
        return calendar_anchor(TargetMonth.from_key(self.target_month))


@dataclass(frozen=True)
class FilterStageResult:
    label: str
    removed: int


@dataclass(frozen=True)
class FilterReport:
    total: int
    stages: tuple[FilterStageResult, ...]
    passed: int


STRATEGIES = ("long-call", "long-put", "bull-call-spread", "bear-put-spread")
SINGLE_LEG_STRATEGIES = ("long-call", "long-put")
SPREAD_STRATEGIES = ("bull-call-spread", "bear-put-spread")


def leg_option_type(strategy: str) -> str:
    """Which chain side the strategy trades (spec §4.1)."""
    return "call" if strategy in ("long-call", "bull-call-spread") else "put"


def is_bullish(strategy: str) -> bool:
    return strategy in ("long-call", "bull-call-spread")


@dataclass(frozen=True)
class PairReport:
    total_pairs: int
    removed_sanity: int
    passed: int
