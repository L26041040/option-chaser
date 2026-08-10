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
    # V7（#55）劇本區間的兩端，選填。**只供呈現層做三價位對照，不進排名**
    # （spec #47 明文：仍以目標價排名），因此預設 None 時全線行為與既有完全
    # 相同。方向合理性（看漲時 worst <= target <= best）在 API 邊界擋，不在
    # 這裡——引擎收到什麼價位就算什麼價位。
    best_price: float | None = None
    worst_price: float | None = None
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
    # RC1（#87）：顯示語意用的結構化三態訊號，獨立於 `rate_by_expiry`
    # 是否非空（那個判準會被「曲線成功但鏈上零合約」這種邊界情況混淆）。
    # `rate_curve_used` 真代表這次真的取得一條 `RateCurve`（新鮮或陳舊
    # 備援皆算），此時 `rate` 本身其實沒被用在估值上（用的是
    # `rate_by_expiry` 查表，查不到才落回 `rate`）——三欄只給呈現層讀，
    # 不影響任何金融計算。
    rate_curve_used: bool = False
    rate_curve_date: str | None = None
    rate_curve_stale: bool = False
    # #113（spec #117 §1）：股利殖利率 q，供 BS93 美式近似＋同模型 IV
    # 反解使用。`None`＝尚未取得（今天：q 管線 #123 還沒接上，一律
    # `None`）——引擎在這個狀態下走**今天的完整行為**：q=0、直接採用
    # vendor IV（見 `valuation.calibrate_leg`），不是「q=0 加價格錨定」
    # ——後者對很多真實 LEAPS call 在數學上無解（研究文件已證實）。
    # 這是**單一數值，不分到期日**（q 是標的的性質，不像利率逐到期日
    # 查表）——`ratecurve.py` 的 per-expiry 查表模式在這裡不適用。
    # #123 會把這欄從 q 管線接上真實數值；本欄位只是接縫，不含任何
    # 抓取／快取邏輯。
    q_by_symbol: float | None = None
    # FB5-01（#62，spec #61）：未平倉量與成交量不再是門檻參數——移除，不留
    # 「看起來在做事、其實沒有」的欄位。未平倉量本身仍在 `OptionContract`
    # 上、隨候選一併序列化，只是不再左右誰進得了候選池。
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
    # FB5-04（#65，spec #61，檢視回饋更名 `cls`→`filter_class`：`cls` 在
    # Python 是 classmethod 慣用參數名，這裡指的是完全不同的東西，容易
    # 誤讀）：這一關屬於三分類的哪一類——"A"＝資料健全性、"B"＝數學前提。
    # C 類（品質標示）從不出現在這裡：它從不淘汰候選，所以不是「一關」，
    # 是 `filters.quality_flag_counts()` 另外算的計數。
    filter_class: str


@dataclass(frozen=True)
class FilterReport:
    total: int
    stages: tuple[FilterStageResult, ...]
    passed: int


@dataclass(frozen=True)
class QualityFlagCount:
    """FB5-04（#65，spec #61，檢視回饋新增）：C 類品質標示的一項計數。

    獨立成型別而不是裸 `tuple[str, int]`，跟 `FilterStageResult`（A／B類）
    同一個模式——兩者都是「一個標籤配一個數字」，值得用同一種方式表示，
    不必讓呼叫端猜 tuple 的兩個位置各是什麼。"""
    label: str
    count: int


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
