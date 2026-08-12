"""儲存層的 port（介面）與領域型別（V2／#50）。

語意沿用既有工作區概念：劇本 CRUD、封存＝軟刪除（紀錄保留）、每次
刷新落下一份完整結果、事件為 append-only 紀錄。實作可替換——測試用
記憶體假體（`memory.py`），正式用 Neon Postgres（`postgres.py`）。

時間一律由呼叫端傳入 ISO 字串，儲存層零 wall-clock（沿用
`option_chaser/store.py` 的既有原則，測試才有決定性）。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol


@dataclass(frozen=True)
class Scenario:
    id: str
    symbol: str
    direction: str            # "bullish" | "bearish"
    target_price: float
    target_month: str         # YYYY-MM
    notes: str
    strategies: tuple[str, ...]
    created_at: str           # ISO 8601
    archived_at: str | None = None   # 非 None ＝ 已封存（軟刪除）
    # V7（#55）劇本區間兩端，選填。既有劇本讀回來是 None，行為不變。
    best_price: float | None = None
    worst_price: float | None = None

    def archived(self, ts: str) -> "Scenario":
        return replace(self, archived_at=ts)

    def restored(self) -> "Scenario":
        return replace(self, archived_at=None)


@dataclass(frozen=True)
class ResultRecord:
    scenario_id: str
    analyzed_at: str          # ISO 8601（＝快照的 fetched_at）
    view: dict                # store.serialize_result 的完整 view dict
    # baseline 期最高收益率（`store.best_return(view)`）。存成獨立欄位而
    # 不是每次從 view 現算：劇本清單只要這一個數字，卻得為此把整份 view
    # 撈回來。規則仍只有一份（引擎的純函式），這裡只是它的落盤結果。
    best_return: float | None = None
    # 代表候選的完整身分（`store.representative_candidate(view)`，
    # MVP-v2／#77、#78）：策略、各腿履約價與權別、實際到期日。與
    # `best_return` 同一個模式——規則只有一份，這裡只是落盤結果。形狀
    # 不假設腿數固定（單腳與價差共用），保留未來策略種類增加時不必
    # 改 schema 的空間。
    representative_candidate: dict | None = None
    # 這次分析當下的標的現價（`store.spot(view)`）。與 `best_return`／
    # `representative_candidate` 同一個模式：清單卡片只要這一個數字，
    # 不該為它把整份 view 撈回來。
    spot: float | None = None


@dataclass(frozen=True)
class ResultSummary:
    """劇本清單卡片要的欄位——不含 view。"""
    analyzed_at: str
    best_return: float | None
    representative_candidate: dict | None = None
    spot: float | None = None


@dataclass(frozen=True)
class RateCacheEntry:
    """利率曲線快取的一筆狀態（#67）——單一一筆、每次寫入即覆蓋，跨
    serverless 呼叫共用同一條曲線，也是 `/api/health` 運維診斷的資料
    來源。`curve` 是 `option_chaser.ratecurve.curve_to_dict()` 的輸出、
    目前沒有堪用曲線時為 `None`（見 `api_app.rate_cache` 的緊急備援窗
    邏輯——抓取失敗但舊曲線還沒過期時會沿用它，`curve` 因此不是簡單
    對應「這次嘗試有沒有成功」）；`note` 說明 `curve` 這個值的來龍去脈
    （成功來源與日期，或沿用舊曲線的原因，或純粹失敗的原因）。

    `last_success_at` 獨立於以上兩者：只在**真正成功**時前進，之後無論
    連續失敗多少次、或失敗久到超過緊急備援窗（`curve` 因此變回
    `None`），這個時間戳都不會被覆蓋掉——`/api/health` 靠它回答「最後
    一次成功取得利率曲線是什麼時候」，不會因為最近剛好在失敗就答不
    出來。

    `market_day`：同一市場日內只成功抓取一次的判準（利率一天內不會
    劇烈變動，沒必要每次刷新都重打來源）。存的是**呼叫端傳入的
    `today`**（`option_chaser.data.snapshot.snapshot_today()`，紐約
    曆日），不是 `fetched_at` 的日期部分——兩者時區不同（`fetched_at`
    是 UTC wall-clock），午夜前後直接切 `fetched_at` 的日期會跟「今天
    是哪個市場日」對不起來。只在**真正成功直接抓到**時前進；沿用
    緊急備援窗舊曲線那個分支不算，維持舊值，好讓當天稍後的呼叫仍會
    再次嘗試（同一市場日內的失敗重試節奏交給 `attempted_day`＋
    `_FAILURE_MAX_AGE` 短窗，見下）。

    `attempted_day`：**不論成功或失敗**、每次寫入都蓋成當次的
    `today`——跟 `market_day` 不同，這個欄位不代表「上次成功是哪天」，
    只代表「上次真的問過底層來源是哪個市場日」。存在的理由：短窗內
    避免同一輪刷新的 N 個劇本把同一個失敗中的來源打好幾次，這個
    dedup 判準只能用 `fetched_at` 的時間差（`market_day` 只在成功時
    前進，失敗／沿用舊曲線時查不到「今天」）；但單看時間差在市場日
    剛好跨過午夜的那幾分鐘會誤把「昨天的紀錄」當「今天也還新鮮」而
    沿用，`attempted_day` 就是用來擋這個邊界情況——時間差夠短
    **而且**是同一個市場日的嘗試，才算數。"""
    fetched_at: str          # 這筆狀態寫入的時間（ISO），不是曲線本身的日期
    curve: dict | None
    note: str
    last_success_at: str | None = None
    market_day: str | None = None
    attempted_day: str | None = None


@dataclass(frozen=True)
class DividendCacheEntry:
    """股利／配息資料快取的一筆狀態，**per-symbol**（#123）——與
    `RateCacheEntry` 的差異：q 是標的的性質，不是全站單一值，因此鍵是
    symbol 而非固定單一筆。欄位語意逐一對應 `RateCacheEntry`（同一套
    三態快取設計），差異只在：

    - `history` 存的是 `option_chaser.dividends.history_to_dict()` 的
      輸出（金額清單＋as_of），**不是算好的 q**——q 是比例，分母會隨
      每次分析的快照 spot 變動，快取比例會把一個過期的價格基準凍結
      進去（研究文件 `dividend-yield-source-selection.md` §7.5／§9
      第 5 點）。
    - 陳舊備援窗是 90 天而非利率的 7 天（同文件 §9：分配是月頻事件，
      7 天窗會讓一次短暫斷線就把使用者踢回 q=0 這個已知會印 +81% 的
      狀態）。
    """
    symbol: str
    fetched_at: str          # 這筆狀態寫入的時間（ISO），不是資料本身的日期
    history: dict | None
    note: str
    last_success_at: str | None = None
    market_day: str | None = None
    attempted_day: str | None = None


@dataclass(frozen=True)
class UsageSetting:
    """`Data / API` 其中一列的選擇（Settings／#124）。

    `mode` ＝ "default" | "custom"。`provider` 只在 custom 時有意義，且
    必須是 `api_app.providers.SUPPORTED_PROVIDERS` 裡的 id——自訂只能挑
    已內建 adapter 的資料源，不接受任意 endpoint／schema。
    """
    mode: str
    provider: str | None = None


@dataclass(frozen=True)
class DataSourceSettings:
    """兩列的模式選擇，單一一筆狀態（比照 `RateCacheEntry`，不是歷史序列）。

    **不含 token**：credential 是 per-Provider 的一把，存在
    `ProviderCredential`。兩列都選同一個 Provider 時因此天然共用同一把，
    不必也不該要求使用者輸入兩次（#124）。
    """
    market_data: UsageSetting
    historical_iv: UsageSetting
    updated_at: str


@dataclass(frozen=True)
class ProviderCredential:
    """某個 Provider 的一把 token。key ＝ provider id，不是資料用途。

    `token` 是完整明文，**只活在後端**：API 回應一律只給
    `providers.mask_token()` 的遮罩形式（#124 硬性 AC）。
    """
    provider: str
    token: str
    updated_at: str


@dataclass(frozen=True)
class ProviderVerification:
    """「測試連線」的結果（Settings／#125）。

    成功與失敗都存——設定頁重新載入時要看得到上次測的結果與時間，不必
    為了知道現況再打一次 vendor。`reason` 只在失敗時有值，而且是給人看
    的整句話（認證被拒／額度用盡／連不上），**不含 token**。
    """
    provider: str
    ok: bool
    reason: str | None
    checked_at: str


class Storage(Protocol):
    """API 層唯一的資料存取介面——不得繞過它直接碰 SQL 或檔案。"""

    def create_scenario(self, sc: Scenario) -> None:
        """id 已存在時拋 `ScenarioExists`。"""

    def get_scenario(self, scenario_id: str) -> Scenario | None: ...

    def list_scenarios(self, *, include_archived: bool = False) -> list[Scenario]:
        """依 created_at 遞增排序；預設不含已封存者。"""

    def archive_scenario(self, scenario_id: str, *, ts: str) -> bool:
        """回傳是否真的封存了（不存在或已封存回 False）。資料不刪除。"""

    def restore_scenario(self, scenario_id: str, *, ts: str) -> bool:
        """回傳是否真的還原了（不存在或本來就未封存回 False）。清空
        `archived_at`，results／snapshots／events 不受影響。`ts` 只為
        跟 `archive_scenario` 同一種呼叫慣例（呼叫端算一次 timestamp，
        同時餵給這裡與事件紀錄）保留，`Scenario` 沒有「還原於」欄位
        需要落盤。"""

    def delete_scenario(self, scenario_id: str) -> bool:
        """永久刪除（TR3／#90）。回傳是否真的刪了東西——**只允許刪除
        已封存的劇本**：不存在或尚未封存（`archived_at is None`）皆回
        `False`、資料原封不動，這是安全閘門，永久刪除必須先進垃圾桶。
        真的刪除時 cascade 清掉該 `scenario_id` 名下的
        results／snapshots／events，不留任何痕跡（不是軟刪除）。"""

    def save_result(self, rec: ResultRecord) -> None:
        """同一 (scenario_id, analyzed_at) 重複寫入即覆蓋（冪等）。"""

    def latest_result(self, scenario_id: str) -> ResultRecord | None: ...

    def latest_summaries(self) -> dict[str, ResultSummary]:
        """每個劇本最新一次結果的摘要，key ＝ scenario_id。

        沒跑過的劇本不出現在結果裡（呼叫端據此顯示「—」，而不是拿一個
        假的零值當成真的收益率）。專屬查詢的理由見契約測試：清單頁
        不該為了一個數字把每份 view（十萬字元等級）都搬一次。"""

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        """依 analyzed_at 遞增排序的完整歷史。

        排序依 `analyzed_at` 的字典序——所有產生端都輸出同一種格式的
        ISO 字串（UTC offset、秒精度），字典序才等於時間序。"""

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict) -> None:
        """原始選擇權鏈快照（`ChainSnapshot` 的 dict 形式）。

        與結果分開存：一份快照數百 KB（數千筆合約），歷史查詢
        （`result_history`）不該每次把它一起撈出來。"""

    def get_snapshot(self, scenario_id: str, analyzed_at: str) -> dict | None:
        ...

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict) -> None: ...

    def list_events(self, *, scenario_id: str | None = None) -> list[dict]:
        """依寫入順序（append-only）回傳。"""

    def get_rate_cache(self) -> RateCacheEntry | None:
        """尚未有任何嘗試（成功或失敗）時回 `None`。"""

    def save_rate_cache(self, entry: RateCacheEntry) -> None:
        """覆蓋既有那一筆——單一狀態，不是歷史序列。"""

    def get_dividend_cache(self, symbol: str) -> DividendCacheEntry | None:
        """該 symbol 尚未有任何嘗試（成功或失敗）時回 `None`。"""

    def save_dividend_cache(self, entry: DividendCacheEntry) -> None:
        """覆蓋該 symbol 既有那一筆——per-symbol 單一狀態，不是歷史序列。"""

    # ---------- 資料源設定與 credential（Settings／#124） ----------

    def get_settings(self) -> DataSourceSettings | None:
        """從未存過任何設定時回 `None`（呼叫端據此用兩列的預設值）。"""

    def save_settings(self, settings: DataSourceSettings) -> None:
        """覆蓋既有那一筆——單一狀態，不是歷史序列。"""

    def get_credential(self, provider: str) -> ProviderCredential | None: ...

    def save_credential(self, cred: ProviderCredential) -> None:
        """同一 provider 重複寫入即覆蓋（換 token 就是這條路徑）。"""

    def delete_credential(self, provider: str) -> bool:
        """回傳是否真的刪了東西（本來就沒存過回 `False`）。

        一併清掉該 provider 的驗證結果——那筆結果講的是「**那把** token
        能不能用」，token 沒了它就失去意義，留著會讓設定頁在沒有
        credential 的情況下顯示「已連線」。"""

    def get_verification(self, provider: str) -> ProviderVerification | None:
        """從未測過時回 `None`（＝「未設定」或「尚未驗證」）。"""

    def save_verification(self, v: ProviderVerification) -> None:
        """覆蓋該 provider 既有那一筆——單一狀態，不是歷史序列。"""

    @property
    def kind(self) -> str:
        """"memory" | "postgres"——供 /api/health 如實回報實際用的是哪個。"""


class ScenarioExists(Exception):
    pass
