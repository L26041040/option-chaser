"""Core data structures and errors. Stdlib only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SCHEMA_VERSION = 2


class SnapshotSchemaError(Exception):
    pass


class FetchError(Exception):
    pass


class QuotaExhausted(FetchError):
    """vendor 今日額度用完（#130）。

    刻意繼承 `FetchError`：既有的降級鏈（`service.fetch_chain` 的
    Cboe→yfinance、自訂來源的 fallback）一律 `except FetchError`，額度
    用完時那些路徑的行為不該改變。子類只是讓**在乎**的呼叫端分得出
    「今天不用再試了」與「這次剛好失敗、待會可以重試」——兩者對使用者
    的意義完全不同。
    """


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
    # #123：q 的三態揭露，比照 RC1（#87）的 `rate_curve_used`／
    # `rate_curve_date`／`rate_curve_stale` 同一套設計——只描述「這次
    # q 從哪裡來、多新鮮」，不影響任何金融計算，`report.py`／API 契約
    # 純格式化這幾個欄位。`q_source` 是實際取得資料的 vendor
    # （"yahoo"／"fmp"／"nasdaq"）；`q_as_of` 是配息資料截至日；
    # `q_stale` 與 `q_by_symbol is None` 脫鉤——`q_by_symbol` 仍可能
    # 在陳舊備援窗內算出一個值（第 3 層 fallback），此時 `q_stale=True`
    # 但 `q_by_symbol` 不是 `None`。`q_note` 是完整的來源／陳舊註記
    # 文字（比照 `rate_note`），供離線重放或管線完全不可得時仍能說明
    # 原因。
    q_source: str | None = None
    q_as_of: str | None = None
    q_stale: bool = False
    q_note: str = ""
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
    # T05（#226，Initial V2 spec #217，`/code-review` Spec 軸回饋）：這一關
    # 剔除掉的候選身份範例（合約代碼，或 spread 兩腿合約代碼的組合），供
    # 診斷指認「是哪一組」——不是完整清單（呼叫端自行決定要留幾筆，通常
    # 只取前幾筆當範例），純粹是「這一關砍了幾筆」之外再加一句「砍了誰」。
    # 預設空 tuple：既有兩個呼叫端（`quote_ok`／`iv_ok`）在補上這個欄位前
    # 就已存在，不能因此要求它們全部改寫。
    removed_examples: tuple[str, ...] = ()


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

# T06（#221，Initial V2 spec #217）：Strategy Family 詞彙。
#
# Family 是使用者持久化的選擇（`Scenario.strategies` 存的是這個），
# Subtype（上面 `STRATEGIES` 的四個具體策略代碼）是分析當下由
# family×方向展開出的結構，從不持久化、從不是使用者可見的選項。
#
# "butterfly" 現在還沒有任何 subtype 可以展開（call-fly／put-fly 是
# T15／#230 的範圍）——先把詞彙定下來是 #221 本票明文要求的（family
# 代碼就是 single-leg／vertical-spread／butterfly 這三個），`FAMILY_
# SUBTYPES["butterfly"]` 暫時是空 tuple，不是預留的空殼架構。
FAMILIES = ("single-leg", "vertical-spread", "butterfly")

# 唯一一張 subtype → family 的靜態對照表，全站共用，沒有第二處硬編碼
# 對應關係。新資料寫入 family 代碼；舊資料（`Scenario.strategies` 裡
# 存的是 subtype 字串）在讀取端用這張表換算回 family，不做資料遷移
# ——兩個字串集合（`STRATEGY_FAMILY` 的 key 與 `FAMILIES`）互斥，讀取
# 時不需要額外的版本欄位就能判斷一個字串屬於哪一邊。
STRATEGY_FAMILY: dict[str, str] = {
    "long-call": "single-leg",
    "long-put": "single-leg",
    "bull-call-spread": "vertical-spread",
    "bear-put-spread": "vertical-spread",
}

# family → 該 family 目前擁有的全部 subtype（不分方向）。方向是否
# 「啟用」由 `subtype_eligible()`／既有的 `skipped_direction` 機制
# 在分析當下判斷，這裡只負責「這個 family 底下有哪些 subtype」。
FAMILY_SUBTYPES: dict[str, tuple[str, ...]] = {
    "single-leg": SINGLE_LEG_STRATEGIES,
    "vertical-spread": SPREAD_STRATEGIES,
    "butterfly": (),
}


def normalize_families(raw: tuple[str, ...]) -> tuple[str, ...]:
    """讀取層正規化：`Scenario.strategies` 可能是舊資料（存 subtype
    字串，例如遷移前建立的 `("bull-call-spread",)`）或新資料（存
    family 字串，例如 `("vertical-spread",)`）。兩者字串集合互斥，
    因此逐一查 `STRATEGY_FAMILY`：查得到就是舊 subtype、換算成 family；
    查不到就當作它已經是 family 字串，原樣保留。去重、保序。"""
    out: list[str] = []
    for v in raw:
        fam = STRATEGY_FAMILY.get(v, v)
        if fam not in out:
            out.append(fam)
    return tuple(out)


def subtypes_of(families: tuple[str, ...]) -> tuple[str, ...]:
    """使用者選的 family 集合 → 分析要跑的 subtype 清單，去重、保序。

    這是分析時序的展開點：呼叫端先用 `normalize_families()` 把讀到的
    `Scenario.strategies` 正規化成 family 集合，再用本函式展開成
    `AnalysisRequest.strategies` 要的 subtype tuple。哪些 subtype 因
    方向與目標價矛盾而被跳過，不是這裡的事——那是既有的
    `skipped_direction` 機制（`service._analyze`），本函式一律展開
    family 底下的全部 subtype，讓既有的方向閘門在分析當下自己過濾。"""
    out: list[str] = []
    for fam in families:
        for s in FAMILY_SUBTYPES[fam]:
            if s not in out:
                out.append(s)
    return tuple(out)


def leg_option_type(strategy: str) -> str:
    """Which chain side the strategy trades (spec §4.1)."""
    return "call" if strategy in ("long-call", "bull-call-spread") else "put"


# T08（#225，Initial V2 spec #217）：Direction（方向，衍生三態，
# CONTEXT.md「策略與方向」一節）——看漲／看跌／持平，由 `target_price`
# 相對 spot 於分析當下算出，永不落盤、不進事件（`Scenario` 本身沒有
# 這個欄位，這裡是純函式的回傳值，不是 dataclass 欄位）。
DIRECTIONS = ("bullish", "bearish", "flat")

DIRECTION_LABELS: dict[str, str] = {
    "bullish": "看漲", "bearish": "看跌", "flat": "持平",
}

# 每個 subtype 適用哪些方向——取代硬編碼的策略名字比對（舊版
# `is_bullish(strategy) -> strategy in ("long-call", "bull-call-spread")`）。
# 新增 subtype（T15／#230 的 call-fly／put-fly，預期收 `{"flat"}`）只需
# 在這裡加一筆資料，`subtype_eligible()`／`family_eligibility()` 兩個
# 判斷函式完全不需要修改。
SUBTYPE_DIRECTIONS: dict[str, frozenset[str]] = {
    "long-call": frozenset({"bullish"}),
    "bull-call-spread": frozenset({"bullish"}),
    "long-put": frozenset({"bearish"}),
    "bear-put-spread": frozenset({"bearish"}),
}


def derive_direction(target_price: float, spot: float) -> str:
    """方向由目標價位相對現價於**分析當下**推導，三態、無容忍帶
    （AC 明文：不發明容忍帶，極接近但不等於現價的方向性劇本照常成立）
    ——只有完全相等才算 `"flat"`。"""
    if target_price > spot:
        return "bullish"
    if target_price < spot:
        return "bearish"
    return "flat"


def subtype_eligible(subtype: str, direction: str) -> bool:
    """這個 subtype 在這個方向下適不適用——資料驅動，取代舊版
    `is_bullish` 的硬編碼名字比對。未知 subtype（理論上不會發生，
    `STRATEGY_FAMILY`／`SUBTYPE_DIRECTIONS` 兩張表本應同步）保守回
    `False`，不是預設放行。"""
    return direction in SUBTYPE_DIRECTIONS.get(subtype, frozenset())


def is_bullish(strategy: str) -> bool:
    """T08（#225）：改為資料驅動（查 `SUBTYPE_DIRECTIONS`），不再是
    硬編碼的名字比對——對既有四個 subtype 逐位元行為不變，這個函式
    服務的是 Heatmap／CLI 報告的價格軸走向這類與 eligibility gate
    無關的既有用途，不在本票改動範圍內。"""
    return "bullish" in SUBTYPE_DIRECTIONS.get(strategy, frozenset())


@dataclass(frozen=True)
class FamilyEligibility:
    """T08（#225，Initial V2 spec #217）：Family 的可選／不可選 verdict
    ——旗下任一啟用 subtype 在目前方向下適用即為可選（OR 投影）。
    `reason` 只在不可選時有值，供前端直接顯示（frontend 只渲染，永遠
    不自行計算 eligibility，CONTEXT.md「Eligibility」一節）。"""
    family: str
    eligible: bool
    reason: str | None = None


def family_eligibility(family: str, direction: str) -> FamilyEligibility:
    """OR 投影：`family_eligible ⟺ 旗下任一啟用 subtype 在這個方向下
    適用`。不可選有兩種成因，訊息分開表達：
    - 這個 family 底下目前一個 subtype 都沒有（`butterfly` 在 T15 之
      前的現況）——與方向無關，方向再怎麼換都一樣不可選；
    - 底下已有的 subtype 都存在，只是沒有一個適用目前這個方向。

    純資料驅動：不論哪一種成因，`family_eligibility()` 本身都不需要
    知道具體是哪個 subtype、哪個 family——`FAMILY_SUBTYPES`／
    `SUBTYPE_DIRECTIONS` 兩張表換了內容，這個函式一行都不用改。"""
    subtypes = FAMILY_SUBTYPES.get(family, ())
    if not subtypes:
        return FamilyEligibility(
            family=family, eligible=False,
            reason="這個策略家族目前還沒有任何已啟用的具體結構。")
    if any(subtype_eligible(s, direction) for s in subtypes):
        return FamilyEligibility(family=family, eligible=True, reason=None)
    label = DIRECTION_LABELS.get(direction, direction)
    return FamilyEligibility(
        family=family, eligible=False,
        reason=f"目前劇本方向為「{label}」，這個策略家族底下已啟用的"
              "策略都不適用這個方向。")


@dataclass(frozen=True)
class PairReport:
    total_pairs: int
    removed_sanity: int
    passed: int
    # T05（#226，Initial V2 spec #217）：B 層（導出層數學安全網）在配對
    # 這個單位上的淘汰數——與 `removed_sanity`（配對時既有的「結構合法性」
    # 檢查，A 層／per-subtype 規則）獨立成不同欄位，因為淘汰依據不同：
    # 這裡是「算出來的成本／報酬是不可能值」，不是「配對本身不成立」。
    # 預設 0：既有呼叫端（`generate_spread_pairs()`）不知道也不需要知道
    # B 層，只有 `_spread_result()` 事後補上這個數字。
    b_layer_removed: int = 0
    # T05（`/code-review` Spec 軸回饋）：B 層在配對這個單位上淘汰掉的組合
    # 身份範例（買腿／賣腿合約代碼組成的字串），與 `b_layer_removed`（純
    # 計數）配對成同一種「數字＋範例」形狀，比照 `FilterStageResult.
    # removed_examples` 同一個模式——兩者都是「一個計數配一份可指認的
    # 範例清單」。預設空 tuple，理由與 `b_layer_removed` 相同。
    b_layer_removed_examples: tuple[str, ...] = ()
