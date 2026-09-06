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

from ..diagnostics import DiagnosticEvent


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
    # T07（#224，Initial V2）：每個 strategy family 各自的代表候選與
    # 最高報酬（`store.representative_candidates_by_family(view)`）。
    # Owner 裁示的「B 儲存＋A 顯示」——顯示面本輪仍只用上面的 scalar
    # 冠軍（跨 family），這份 map 純粹是額外落盤、供日後若要改成逐
    # family 顯示時零遷移可切換。鍵是 family 代碼（`"single-leg"`／
    # `"vertical-spread"`／`"butterfly"`），值與 `representative_
    # candidate` 同一種形狀（`{strategy, legs, expiry, baseline_
    # return}`）。純加法，預設 `None`——舊結果紀錄讀回來時這裡是
    # `None`；寫入端（`_refresh_and_save()`）在純函式回傳空 dict（沒有
    # baseline 期可比）時也一併落成 `None`，與 `representative_
    # candidate` 的既有慣例一致——這個欄位本來就只用 `None` 表達
    # 「沒有東西可顯示」，不新增第二種空值語意。
    per_family: dict | None = None
    # T10（#227，Initial V2）：最近一次分析當下算出的 family 可選／
    # 不可選 verdict（`store._family_eligibility_map()` 的輸出，鍵是
    # family 代碼）。與 `per_family` 同一個模式（額外落盤、供編輯表單
    # 讀取），差別是這個真的被本票的前端消費——編輯表單要顯示「這個
    # family 現在為什麼不可選」，不該為此把整份 view 撈回來。
    family_eligibility: dict | None = None
    # SCALE-01（#252，Scaling Foundation Stage 1-0）：以下 6 個欄位是
    # 這一列歷史 fact 「重建能力」真正所需、目前寄生在 `view` 內部的
    # 估值輸入與 provenance，獨立持久化成一等公民欄位——`view` 本身
    # 完全不變，這幾個欄位只是它們的**複本**（見
    # `option_chaser.store.historical_fact_context()`，唯一算出這些
    # 值的地方，新寫入與既有資料 backfill 共用同一份邏輯）。全部
    # 先 nullable：既有部署的舊列讀回來是 `None`，backfill 腳本負責
    # 把它們補齊，讀取端在 backfill 完成前必須容忍 `None`。
    #
    # 這些欄位存在的唯一理由是讓未來的 storage 瘦身（例如 SCALE-16
    # 停止永久保存完整 `view`）不會把「回答這個歷史時刻當時發生了
    # 什麼」的能力一併砍掉——它們本身**不是**給一般讀取路徑用的（那些
    # 路徑今天仍然讀 `view`），而是給未來的 candidate-specific
    # historical resolver（SCALE-09）當輸入。
    resolved_params: dict | None = None
    requested_strategies: tuple[str, ...] | None = None
    engine_version: str | None = None
    view_schema_version: int | None = None
    history_replay_version: int | None = None
    # `analyzed_at` 本身就是快照的 `fetched_at`（見上方欄位註解：
    # 「＝快照的 fetched_at」），provenance 的「fetched_at」半邊因此
    # 不需要另開欄位；`snapshot_source` 補上另外半邊（資料源，
    # `"cboe"`／`"yfinance"`——`view["meta"]["source"]`），`/code-review`
    # Spec 軸抓到的真缺口：原本 5 個欄位漏了這一項，provenance 只有
    # rate/q 那一半（藏在 `resolved_params` 裡）、沒有快照本身的
    # 資料源，仍得解析 `view` 才查得到，牴觸 AC-1。
    snapshot_source: str | None = None


@dataclass(frozen=True)
class ResultFactContext:
    """SCALE-01（#252）：`ResultRecord` 上述歷史 fact 欄位的**窄查詢
    投影**——刻意不含 `view`（也不含 `best_return`／
    `representative_candidate` 等其餘既有欄位），滿足 AC-1「用一個窄
    查詢取得完整 resolved params、analysis context、provenance、
    engine/schema/replay version，不解析 view」：Postgres adapter 的
    對應 SQL 從一開始就不 SELECT `view` 欄位，不是「查了再丟棄」。"""
    scenario_id: str
    analyzed_at: str
    resolved_params: dict | None
    requested_strategies: tuple[str, ...] | None
    engine_version: str | None
    view_schema_version: int | None
    history_replay_version: int | None
    snapshot_source: str | None


@dataclass(frozen=True)
class ResultSummary:
    """劇本清單卡片要的欄位——不含 view。"""
    analyzed_at: str
    best_return: float | None
    representative_candidate: dict | None = None
    spot: float | None = None
    # T07（#224，Initial V2）：與 `ResultRecord.per_family` 同一個模式，
    # 供清單卡片讀取——本輪 UI 尚未消費它（顯示面仍是單一冠軍），
    # 純粹型別同步／落盤攜帶。
    per_family: dict | None = None
    # T10（#227，Initial V2）：與 `ResultRecord.family_eligibility`
    # 同一個模式——編輯表單開啟時讀這裡，不打 detail 端點。
    family_eligibility: dict | None = None


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
class TreasuryYearCacheEntry:
    """Treasury 利率曲線列的快取，**per-year**（PERF-03／#179）——鍵是
    年份，不是「今天」：歷史 reconstruction 對任一觀測日 D 的查詢，結構
    上只可能被 D 所在年份的這筆紀錄滿足，快取鍵本身就不留「不小心套用
    到今天曲線回答歷史查詢」的路徑（本輪風險最高的一項，正確性必須靠
    鍵設計本身鎖死，不能只靠呼叫端小心）。

    `rows` 是 `option_chaser.data.treasury.fetch_curve_rows_for_year()`
    的輸出（`option_chaser.ratecurve.CurveRows`）序列化成 JSON 安全形狀
    `[[date, [[tenor, rate], ...]], ...]`；目前沒有堪用資料時為 `None`。
    其餘欄位語意逐一對應 `RateCacheEntry`／`DividendCacheEntry` 同一套
    三態快取設計（成功／近期嘗試失敗／陳舊備援），差異只在「成功是否
    永久新鮮」由呼叫端依 `year` 是否早於今年判斷，不是看這個 dataclass
    本身——過去年份一旦成功即永久有效（Treasury 不會回頭修正已公布的
    歷史曲線），當年比照既有市場日語意，隔天第一次請求才重新嘗試。
    """
    year: int
    fetched_at: str          # 這筆狀態寫入的時間（ISO），不是曲線本身的年份
    rows: list | None
    note: str
    last_success_at: str | None = None
    market_day: str | None = None
    attempted_day: str | None = None


@dataclass(frozen=True)
class ChainBackoffEntry:
    """SCALE-04（#255，Scaling Foundation Cboe 429 韌性）：上游限流的
    控制狀態——**provider-global 鍵**（`source` 單獨，不分 symbol，
    見 `docs/spec/scaling-foundation.md` §8.4 2026-09-06 訂正：沒有
    證據顯示 Cboe 限流是 per-symbol，安全預設是整個來源一起封鎖，
    否則使用者換個 symbol 就能繞過封鎖窗）。

    **RL-19（紅線）：這張表不得儲存任何 chain payload、任何市場報價、
    任何合約資料**。它只回答「上游現在讓不讓我打」，欄位逐一都是
    控制中繼資料，不是市場事實——這與 ADR-0001／OD-05 evidence gate
    卡住的 chain shared cache（存市場資料本身）是不同的東西，未來
    讀到這張表切勿誤讀成偷渡的 chain cache。

    `source`：PK，例如 `"cboe"`。
    `blocked_until`：封鎖窗結束時間（ISO 8601），`None`＝目前未封鎖。
    `retry_after_seconds`：上游最近一次給的原始 `Retry-After` 值
    （供揭露與診斷，`None`＝上游沒給或給的值解析不出來，這次改用
    保守預設退避時間）。
    `consecutive_failures`：目前連續幾次被限流，供 incident 判定
    （FR-5.7）——只在遇到 429 時遞增，一次成功即歸零。
    `observed_at`：最近一次觀測到限流的時間。
    `last_success_at`：最近一次成功抓取的時間——獨立於
    `blocked_until`／`consecutive_failures`，只在真正成功時前進。
    """
    source: str
    blocked_until: str | None
    retry_after_seconds: float | None
    consecutive_failures: int
    observed_at: str
    last_success_at: str | None = None


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


@dataclass(frozen=True)
class IvObservation:
    """某個 **underlying symbol** 在某一天的歷史選擇權曲面（#129）。

    鍵是 **(symbol, 日期)**，**刻意不帶 scenario 身分**——同一 ticker 的
    所有 Scenario 共用同一份歷史資料，各自再投影到需要的 (tenor, delta)
    座標。target price 不同、target month 不同、scenario id 不同，都不
    構成向 vendor 重抓的理由（vendor 額度有限，重抓是純浪費）。

    `surface` 是 `{"call": [[dte, delta, iv], ...], "put": [...]}`——存成
    三元組陣列而不是具名物件，一天的鏈有數千筆，欄位名重複數千次只是
    在燒儲存空間。
    """
    symbol: str
    observed_on: str          # YYYY-MM-DD（市場日，不是抓取時間）
    surface: dict
    fetched_at: str           # ISO 8601，這筆是什麼時候抓回來的


@dataclass(frozen=True)
class IvBackfillRun:
    """某 symbol 最近一次 backfill 批次的結果（#130）。

    存在的理由是「**同一 symbol 每天只跑一個 backfill job**」：沒有這筆
    紀錄的話，同一天每開一個同 ticker 的 Scenario 就會再燒一批額度，正是
    需求方要避免的浪費。也讓「今日額度已用完」不必每次都再打一次
    vendor 才知道。

    `outcome` ＝ "ok" | "quota" | "vendor"，`ran_on` 是市場日（紐約曆日）。
    """
    symbol: str
    ran_on: str
    outcome: str
    note: str | None = None


@dataclass(frozen=True)
class ContractHistory:
    """某個 **exact option contract**（同一 underlying／expiration／strike／
    option_type 的組合，spec #151 §2 絕對紅線）的歷史 IV 觀測快取
    （HIVT-02／#153）。

    鍵是 **OCC contract symbol**——這就是 exact contract identity 本身
    （不同 strike／expiry／call-put 天然是不同 symbol），不需要另外組
    複合鍵。跟 `IvObservation`（per-symbol、per-day、整條鏈，(tenor,
    delta) 重錨定家族專用）刻意不同的資料模型：vendor 的單合約端點一次
    呼叫回整段日期區間（已由 #152 真實驗證：真實 TLT LEAPS 案例 34 筆
    觀測只花 1 credit），這裡整個合約的觀測史因此存成**一筆**，不是
    逐日一筆。

    `points` 是逐日 quote dict 的 tuple，依日期遞增排序（HIVR-04／#163
    起的寬版形狀：`date`／`updated`／`dte`／`bid`／`ask`／`mid`／
    `underlying_price`／`vendor_iv` 八個 key——比 HIVT-02／#153 當初的
    `(date, iv)` 二元組寬，保留 reconstruction（#164）需要的原始欄位，
    `vendor_iv` 為 `None` 就是 vendor 那天真的沒給可信報價（missing
    observation），不補、不插值、不換合約（spec #151 §2／§3 紅線）。
    **這個型別本身不驗證形狀**——storage 是啞的 port，`points` 裡混進
    HIVR-04 之前的舊版 `(date, iv)` 二元組在型別系統上不會被擋下；舊
    格式的辨識與「當 cache miss 重抓」由呼叫端（`api_app/main.py`）
    負責，見那裡的 docstring。

    `fetched_through`：上一次成功呼叫時用的 `to=` 日期——下一次刷新只
    抓這個日期之後到今天的缺口，不是每次整年重抓。從未成功過時是
    `None`。

    `last_attempt_on`：上一次嘗試呼叫 vendor 的日期（不論成功失敗）——
    比照 `IvBackfillRun.ran_on`，用來擋「同一天內對已快取合約的重複
    vendor 請求」（HIVT-02 acceptance criteria 明文要求同一天內重複請求
    的 vendor 呼叫次數為 0）。

    `last_status`／`last_note`：比照 `IvBackfillRun.outcome`／`note`
    （"ok"｜"quota"｜"vendor"）——只描述**這次嘗試**，已快取的 `points`
    不因今天補不下去就被藏起來（沿用既有 #133 原則）。
    """
    contract_symbol: str
    points: tuple[dict, ...]
    fetched_through: str | None
    last_attempt_on: str | None
    last_status: str
    last_note: str | None = None


class Storage(Protocol):
    """API 層唯一的資料存取介面——不得繞過它直接碰 SQL 或檔案。"""

    def create_scenario(self, sc: Scenario) -> None:
        """id 已存在時拋 `ScenarioExists`。"""

    def get_scenario(self, scenario_id: str) -> Scenario | None: ...

    def list_scenarios(self, *, include_archived: bool = False) -> list[Scenario]:
        """依 created_at 遞增排序；預設不含已封存者。"""

    def update_scenario(self, sc: Scenario) -> bool:
        """就地更新一個既有劇本（#132）。回傳是否真的更新了（不存在回
        `False`）。

        **同一個 id，不是刪除＋重建**：重建會換掉身分，讓所有以
        scenario_id 為鍵的東西（結果、快照、事件）變成孤兒，而使用者只是
        改了個目標價。`id` 與 `created_at` 由呼叫端負責原樣帶回。"""

    def clear_results(self, scenario_id: str) -> None:
        """清掉該劇本的全部結果與原始快照，保留劇本本身與事件紀錄（#132）。

        用於 thesis 改變之後：目標價餵進 baseline_return、目標月決定選哪
        些到期日，兩者一改，舊結果的每個數字都是對著另一個問題算出來的。
        留著它們就是拿舊結果冒充新的。事件不刪——那是不可變的事實。"""

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

    def result_timestamps(self, scenario_id: str) -> list[str]:
        """SCALE-02（#253，Scaling Foundation C2）：這個劇本歷史上有
        哪幾次分析時間戳——依遞增排序，**不撈 `view`**。主要索引來源是
        `snapshots` 的 `(scenario_id, analyzed_at)` 主鍵（Prototype #065
        實測：對這張表做這個查詢比對 narrow 候選表做 `DISTINCT` 快
        1.58×；對 narrow 候選表做 `DISTINCT` 反而慢 12.6×，**這個方法
        本身不得走那條路**），輔以 `results` 表同一個主鍵的窄查詢
        UNION 補回——理由：`api_app/main.py::_refresh_and_save()` 對
        `save_result()`／`save_snapshot()` 是兩次獨立呼叫、未包在同一
        個交易裡，兩者之間若中斷（逾時／崩潰），會留下一筆有 `results`
        沒有 `snapshots` 的孤兒列；只讀 `snapshots` 會讓那次分析的
        時間戳從歷史索引裡憑空消失。兩邊都只選 `analyzed_at`
        （`results` 這邊的 SELECT 完全不觸碰 `view` 欄位），UNION 本身
        會處理去重，不需要額外的 `DISTINCT`。

        本方法只吃 `scenario_id`，之後 SCALE-11 要替 `snapshots`／
        `results` 兩張表加上 owner 過濾時，直接在這裡的兩段 WHERE
        子句上各加一個條件即可覆蓋，不構成繞過 owner boundary 的旁路。
        """

    def result_fact_context(self, scenario_id: str,
                            analyzed_at: str) -> ResultFactContext | None:
        """SCALE-01（#252）：單一 `(scenario_id, analyzed_at)` 的窄查詢
        ——只回傳 `ResultFactContext` 的欄位，不觸碰／不解析 `view`
        （Postgres 這條路徑的 SQL 一開始就不 SELECT `view`）。找不到
        這個 fact row 時回 `None`；找得到但尚未 backfill（各欄位皆為
        `None`）時回傳一個全欄位皆 `None` 的 `ResultFactContext`，
        呼叫端據此分辨「這列還沒 backfill」與「這列根本不存在」。"""

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

    # ---------- Treasury 曲線列快取（PERF-03／#179，per-year） ----------

    def get_treasury_year_cache(self, year: int) -> TreasuryYearCacheEntry | None:
        """該年份尚未有任何嘗試（成功或失敗）時回 `None`。"""

    def save_treasury_year_cache(self, entry: TreasuryYearCacheEntry) -> None:
        """覆蓋該年份既有那一筆——per-year 單一狀態，不是歷史序列。"""

    # ---------- Chain 429 backoff（SCALE-04／#255，provider-global） ----------

    def get_chain_backoff(self, source: str) -> ChainBackoffEntry | None:
        """該來源尚未有任何觀測（成功或限流）時回 `None`。"""

    def save_chain_backoff(self, entry: ChainBackoffEntry) -> None:
        """覆蓋該來源既有那一筆——provider-global 單一狀態，不是歷史
        序列，鍵是 `entry.source`（不分 symbol，見
        `ChainBackoffEntry` docstring）。"""

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

    # ---------- 歷史 IV 觀測快取（#129，per-symbol） ----------

    def save_iv_observation(self, obs: IvObservation) -> None:
        """同一 (symbol, 日期) 重複寫入即覆蓋（冪等）。"""

    def iv_observation_dates(self, symbol: str) -> list[str]:
        """這個 symbol 已經有哪些日期（遞增）。

        **不回傳曲面本身**：backfill 只需要知道「還缺哪幾天」，為此把
        數十天、每天數千筆的資料整包撈出來是離譜的浪費。"""

    def iv_observations(self, symbol: str) -> list[IvObservation]:
        """依日期遞增回傳該 symbol 的全部觀測。"""

    def get_iv_backfill_run(self, symbol: str) -> IvBackfillRun | None:
        """該 symbol 最近一次 backfill 批次；從未跑過回 `None`。"""

    def save_iv_backfill_run(self, run: IvBackfillRun) -> None:
        """覆蓋該 symbol 既有那一筆——單一狀態，不是歷史序列。"""

    def get_verification(self, provider: str) -> ProviderVerification | None:
        """從未測過時回 `None`（＝「未設定」或「尚未驗證」）。"""

    def save_verification(self, v: ProviderVerification) -> None:
        """覆蓋該 provider 既有那一筆——單一狀態，不是歷史序列。"""

    # ---------- Exact-contract 歷史 IV 快取（HIVT-02／#153） ----------

    def get_contract_history(self, contract_symbol: str) -> ContractHistory | None:
        """該 exact contract 尚未有任何觀測快取時回 `None`。"""

    def save_contract_history(self, history: ContractHistory) -> None:
        """同一 `contract_symbol` 重複寫入即覆蓋（冪等）——整份觀測史是
        單一狀態，不是逐日一筆。"""

    # ---------- Application diagnostics（DG-02／#145） ----------

    def append_diagnostic(self, event: DiagnosticEvent) -> None:
        """寫入一筆診斷事件。**trim-on-write**：寫入後只保留全域最新
        `diagnostics.RETENTION_LIMIT` 筆，較舊的直接淘汰——不是靠背景
        清理 job（serverless 沒有地方掛），上限因此是結構性的。"""

    def append_diagnostics(self, events: list[DiagnosticEvent]) -> None:
        """批次版（PERF-02／#178）——與單筆版 `append_diagnostic()` 並存，
        不取代（既有呼叫端／測試直接呼叫單筆版的地方不受影響）。同一份
        trim-on-write 語意：整批寫完後只保留全域最新
        `diagnostics.RETENTION_LIMIT` 筆，跟逐筆呼叫單筆版比較，最終
        保留集合完全一致。空清單是合法的 no-op。"""

    def list_diagnostics(self, *, limit: int = 50) -> list[DiagnosticEvent]:
        """最新在最上（依寫入順序反排）。"""

    def clear_diagnostics(self) -> int:
        """清空，回傳清掉的筆數。"""

    @property
    def kind(self) -> str:
        """"memory" | "postgres"——供 /api/health 如實回報實際用的是哪個。"""


class ScenarioExists(Exception):
    pass
