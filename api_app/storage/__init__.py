"""儲存層的 port（介面）與領域型別（V2／#50）。

語意沿用既有工作區概念：劇本 CRUD、封存＝軟刪除（紀錄保留）、每次
刷新落下一份完整結果、事件為 append-only 紀錄。實作可替換——測試用
記憶體假體（`memory.py`），正式用 Neon Postgres（`postgres.py`）。

時間一律由呼叫端傳入 ISO 字串，儲存層零 wall-clock（沿用
`option_chaser/store.py` 的既有原則，測試才有決定性）。
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol, Sequence

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
    # SCALE-06（#256，Scaling Foundation Ownership A-1 Expand）：資料
    # boundary 用的 owner 標記——**不是** authentication／privacy
    # （那是 out-of-scope 的 A-2）。今天固定解析成同一個 solo-owner
    # 值（`api_app.identity.default_identity_resolver()`），純加法、
    # nullable：既有部署的舊列讀回來是 `None`，
    # `Storage.backfill_missing_owner_ids()` 負責補齊。本票**不**在任何
    # 查詢路徑套用過濾（那是 SCALE-11 的範圍）。
    owner_id: str | None = None

    def archived(self, ts: str) -> "Scenario":
        return replace(self, archived_at=ts)

    def restored(self) -> "Scenario":
        return replace(self, archived_at=None)


@dataclass(frozen=True)
class ResultRecord:
    scenario_id: str
    analyzed_at: str          # ISO 8601（＝快照的 fetched_at）
    # store.serialize_result 的完整 view dict。SCALE-16（#267，Stage
    # 1-5）起可為 `None`——這個型別現在同時服務兩種用途：historical
    # fact ledger（`results` 表，append-only，`view` 永遠是 `None`，
    # 完整 payload 不再永久累積）與 current full-view materialization
    # （`current_results` 表，`view` 永遠是完整 dict，覆寫更新）。
    # 呼叫端從欄位本身分不出這一列來自哪張表——分不出來是刻意的：
    # `ResultRecord` 只是共用的列形狀，「這是哪一種」完全由呼叫的是
    # `save_result()`（ledger）還是 `save_current_result()`（current）
    # 決定，型別本身不記錄這個維度。
    view: dict | None
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
    # SCALE-06（#256，Ownership A-1 Expand）：與 `Scenario.owner_id`
    # 同一個模式——資料 boundary 標記，非 privacy，nullable，本票不
    # 加任何查詢過濾。
    owner_id: str | None = None


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
class Owner:
    """PB-01（#292，Anonymous Public Beta）：匿名／已知使用者的資料
    boundary 本身——`owner_id` 沿用既有 SCALE-06 的 owner_id 概念
    （5+1 張 row-scoped 表既有的那個值），這張表替它掛上 lifecycle
    中繼資料，供 PB-08 判斷 abandoned／cleanup 使用。

    **本票是純 expand**：新建的 owner 列不會被任何既有查詢路徑讀到，
    `identity_resolver()` 仍固定回傳 `SOLO_OWNER`（切換是 PB-02 的
    範圍）。

    `protected`：純布林旗標，**不是** `owner_kind`——spec #291 §18
    明文禁止用「怎麼建立」決定「是什麼身份型態」這種設計。它只標記
    「這個 owner 的資料不受匿名 lifecycle cleanup 影響」（PB-03 會
    用它保護 Owner 自己遷移過去的資料），與這個 owner 最初怎麼被建立
    出來無關——任何 owner_id 理論上都可能被標記／解除標記。

    `last_activity_at`：「哪些動作算 activity」的語意判斷屬 PB-08，
    本票只建立欄位與讀寫方法（`touch_owner_activity()`），不先寫死
    任何判準。`None`＝這個 owner 還沒被記過任何一次 activity。

    `is_synthetic`（PB-07／#304，Anonymous Public Beta）：Controlled
    Beta 合成壓測 harness 產生的 owner 標記——**唯一的生產面作用是
    清理排程分開處理**（票面 §7 明文：不得擴散成別的行為差異）。
    PB-01 當時刻意**沒有**預先加這個欄位（避免數週內沒有消費端的
    欄位躺在 production），本票才是它真正的消費端。harness 產生的
    owner 由呼叫端在建構 `Owner` 物件時直接設 `True`——不經過任何
    HTTP 端點（一般使用者的 lazy-creation 路徑，`PB-02`，永遠產生
    `is_synthetic=False` 的 owner；沒有任何請求能讓自己被標記成
    synthetic，這不是一個可以透過網路操縱的旗標）。"""
    owner_id: str
    created_at: str
    last_activity_at: str | None = None
    protected: bool = False
    is_synthetic: bool = False


@dataclass(frozen=True)
class BrowserIdentity:
    """PB-01：cookie 帶的不透明 token → `owner_id` 的映射。

    **`token` 與 `owner_id` 刻意是兩個不同的值**——`tests/
    test_scale06_ownership_expand.py` 既有斷言 `owner_id` 永不出現
    在任何 HTTP 回應 body；cookie 本身就是回應的一部分，若 cookie
    值直接等於 `owner_id`，這條既有不變量在 cookie 簽發的那一刻就
    被打破。分開儲存同時讓 token 可被伺服器單方作廢（例如未來的
    找回機制）而不必變動 `owner_id`（研究 #275 的核心建議）。

    `issued_at`：這個 token 第一次被簽發的時間。`last_seen_at`：最近
    一次帶著這個 token 的請求時間——本票只建立欄位與續命方法
    （`touch_browser_identity()`），「多久沒見就算失效」屬 PB-02
    範圍。
    """
    token: str
    owner_id: str
    issued_at: str
    last_seen_at: str


@dataclass(frozen=True)
class OwnerLifecycleFacts:
    """SECURITY-FIX-01：匿名 owner 清理判定需要的全部原始事實，一次查齊
    （不是逐一 owner 再查 N 次）。

    - `last_seen_at`：這個 owner 名下所有 browser identity 裡最近的一次
      `last_seen_at`——任何帶有效 cookie 的請求都會推這個值，是新的
      inactivity 錨點。沒有任何 identity 列時為 `None`（例如合成壓測
      owner），呼叫端退回 `created_at`。
    - `has_data`：名下還有沒有使用者真正存下來的東西——劇本（含已封存）、
      per-owner 設定或 provider credential。沒有的就是「空 owner」。
    """
    owner_id: str
    created_at: str
    last_seen_at: str | None
    has_data: bool
    protected: bool


@dataclass(frozen=True)
class RateLimitBucket:
    """SECURITY-FIX-02：一個短時間窗計數格——`(scope, key)` 這個對象在
    `[window_start, window_start + window_seconds)` 這段時間內最多
    `limit` 次。視窗起點由呼叫端算（per-owner／source 用 UTC 對齊，
    new-owner tier 用 global fuse 同一條紐約日界線）。"""
    scope: str
    key: str
    window_seconds: int
    window_start: int
    limit: int


@dataclass(frozen=True)
class RoleSession:
    """AUTH-01（#308，三層角色模型 spec #307）：cookie 帶的不透明
    token → 角色（`"superuser" | "superadmin"`）的映射。

    刻意鏡射 `BrowserIdentity`（token → owner_id）的既有形狀，但是
    **獨立**的表／方法組——不與 `BrowserIdentity`／`Owner` 共用任何
    函式或資料列，這是軸一（Owner Identity）／軸二（User Level）維持
    正交的既有硬性約束（SUPERUSER-007）延伸到三層角色版本的具體落地。

    `token` 與 `role` 分開儲存的理由與 `BrowserIdentity` 完全相同：
    token 本身不含角色明文、不可反推，角色只能透過伺服器端查表得知，
    且 token 可被伺服器單方作廢（登出）而不需要變動任何其他狀態。

    **本票（AUTH-01）刻意只有四個欄位**——spec #307 2026-09-17 修正
    明確排除 password rotation／password fingerprint 設計，因此這裡
    沒有任何密碼雜湊、指紋或版本號欄位。`revoked_at` 為 `None` 代表
    仍然有效；一旦寫入非 `None` 值即視為永久失效，不會被清空重新
    啟用（要恢復存取需要重新登入產生新的 token）。

    `issued_at`：這個 token 第一次被簽發的時間，供未來除錯／稽核
    使用；本身不參與任何有效性判斷（AUTH-01 不設過期時間，是否要
    加過期時間屬未來範圍，非本票決定）。
    """
    token: str
    role: str
    issued_at: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class SuperUserAuditEvent:
    """PB-10（#301，Anonymous Public Beta）：Super Admin 高風險跨
    owner 操作的 audit trail。

    **刻意不是 `diagnostics` 或 `events`**（票面 §4 硬性約束，repo 現況
    已確認兩者語意衝突）：`diagnostics`（`api_app/diagnostics.py`）是
    owner-scoped 且 trim-on-write 只留全域最新 200 筆——正常診斷事件
    洪流會把 audit 記錄沖掉，那就不是 audit trail；`events` 是
    scenario-scoped 的領域事實（`SCENARIO_CREATED` 等），語意上不承載
    「誰對誰做了管理操作」。這張表是獨立、system-wide、**不設保留
    上限**的記錄面——高風險操作量體遠低於一般診斷事件（一次 Super
    Admin 動作才一筆，不是每個 request 都發），截斷它等於讓最需要
    留存的紀錄先消失，違背它存在的目的。

    `actor`：AUTH-03（#310）起這些高風險端點的授權門檻是三層角色的
    `minimum=SUPERADMIN`（取代 PB-09 當時單一共用的 `ADMIN_SECRET`），
    仍舊沒有多重身份機制（spec 明文禁止為此新增識別系統）——固定為
    `"superadmin"`，誠實反映現況，不是假裝有更細緻的身份可查。

    `target_owner_id`：這次操作影響的 owner；純瀏覽（無明確目標，
    例如列出全部 owner 這種不針對單一 owner 的動作）時可為 `None`。

    `detail`：操作內容的結構化描述（例如
    `{"deleted_rows": {"scenarios": 3, ...}}`）——**絕不含第三方
    token 明文**，呼叫端（`api_app/main.py`）只放進安全欄位（列數、
    布林值等），從不把 `ProviderCredential.token` 這類欄位塞進來。

    **`delete_owner()`（PB-04）刻意不清除這張表**——它不在
    `_OWNER_SCOPED_TABLES` 清單裡：audit trail 的目的正是留存「這個
    owner 曾經存在、曾經被刪除」這件事本身，若隨著被刪 owner 一起
    清空，等於刪除操作抹去了自己的證據。"""
    event_id: str
    ts: str
    actor: str
    action: str
    target_owner_id: str | None
    detail: dict


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

    `owner_id`（SCALE-13／#264）：新表 `owner_settings` 的 PK 本身就是
    `owner_id`（一人一筆單一狀態，取代舊表 `data_source_settings` 的
    `id=1` 單例）——這裡標 `str | None = None` 只是為了讓型別在讀取
    舊表相容分支（尚未遷移過的資料）時也能構造這個物件，寫入新表的
    正式路徑一律要求真值（`require_owner()` 守門，見
    `Storage.save_settings()`）。"""
    market_data: UsageSetting
    historical_iv: UsageSetting
    updated_at: str
    owner_id: str | None = None


@dataclass(frozen=True)
class ProviderCredential:
    """某個 Provider 的一把 token。key ＝ (owner_id, provider)——
    SCALE-13／#264 之前是單純 `provider`（全站唯一一把），新表
    `owner_credentials` 把它擴成複合鍵，兩個 owner 可以各自保存不同
    token。`owner_id` 語意同 `DataSourceSettings`。

    `token` 是完整明文，**只活在後端**：API 回應一律只給
    `providers.mask_token()` 的遮罩形式（#124 硬性 AC）。
    """
    provider: str
    token: str
    updated_at: str
    owner_id: str | None = None


@dataclass(frozen=True)
class ProviderVerification:
    """「測試連線」的結果（Settings／#125）。key ＝ (owner_id,
    provider)——SCALE-13／#264 起與 `ProviderCredential` 同一種複合鍵
    擴充，`owner_id` 語意相同。

    成功與失敗都存——設定頁重新載入時要看得到上次測的結果與時間，不必
    為了知道現況再打一次 vendor。`reason` 只在失敗時有值，而且是給人看
    的整句話（認證被拒／額度用盡／連不上），**不含 token**。
    """
    provider: str
    ok: bool
    reason: str | None
    checked_at: str
    owner_id: str | None = None


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


def require_owner(owner: str | None) -> str:
    """SCALE-11（#262）／`/code-review` 抓到的真缺口：`owner: str`
    這個型別標註在 Python 執行期完全不強制——`memory.py`／
    `postgres.py` 兩個後端過去各自用 `==`／`!=` 比對 `owner_id`，
    若呼叫端不慎傳入 `owner=None`，`None` 會被當成一個合法的過濾值，
    對尚未 backfill（同樣是 `owner_id=None`）的舊列悄悄「配對成功」
    ——等於在型別系統看不到的地方重新開了一個不經 owner scope 的
    旁路。兩個後端共用同一份守門實作（而非各自複製一份可能漂移的
    檢查），讓凡是簽章寫著 `owner: str`（非 optional）的 15 個方法
    之一，只要真的傳入 `None` 就會在執行期立刻拋錯，不會被 `==`／
    `!=` 悄悄吃掉。**唯一例外**：`list_scenarios()`／
    `result_history()` 的簽章本身是 `owner: str | None`，那是
    `backfill_result_fact_context()` 僅有的合法跨 owner 遷移用途，
    這兩個方法不呼叫本函式。"""
    if owner is None:
        raise TypeError(
            "owner 不得為 None——只有 list_scenarios()/result_history() "
            "允許 owner=None 代表跨 owner 的遷移用途")
    return owner


class Storage(Protocol):
    """API 層唯一的資料存取介面——不得繞過它直接碰 SQL 或檔案。"""

    def create_scenario(self, sc: Scenario) -> None:
        """id 已存在時拋 `ScenarioExists`。"""

    def get_scenario(self, scenario_id: str, *, owner: str) -> Scenario | None:
        """SCALE-11（#262，Ownership A-1 Enforce）：`owner` 為必填
        keyword-only 參數——存在但屬於別的 owner 的劇本，與根本不存在，
        對呼叫端而言必須是同一種結果（`None`），這是 AC-2「猜到另一
        owner 的 scenario_id 也不能讀到資料」成立的關鍵：不能讓
        呼叫端從回應差異分辨出「這個 id 存在，只是不是你的」。"""

    def list_scenarios(self, *, owner: str | None,
                       include_archived: bool = False) -> list[Scenario]:
        """依 created_at 遞增排序；預設不含已封存者。

        `owner`：SCALE-11 必填 keyword-only（無預設值，逼呼叫端每次
        明確做選擇）。production HTTP 路徑一律傳目前解析出的 owner
        字串；`owner=None` 是唯一的例外——**只給
        `api_app.storage.backfill.backfill_result_fact_context()`
        這種跨全部 owner 的一次性遷移腳本使用**，代表「不過濾、列出
        全部」，比照既有 `backfill_missing_owner_ids()` 的既有先例
        （那個方法本身就是要看見全部資料才能修復它，不是一般查詢
        路徑）。這不是預設值——沒有任何呼叫端能「不小心」漏帶 owner
        就拿到全部資料，要拿到就得顯式寫 `owner=None`，grep 得到。"""

    def update_scenario(self, sc: Scenario, *, owner: str) -> bool:
        """就地更新一個既有劇本（#132）。回傳是否真的更新了（不存在、
        或存在但屬於別的 owner，皆回 `False`）。

        **同一個 id，不是刪除＋重建**：重建會換掉身分，讓所有以
        scenario_id 為鍵的東西（結果、快照、事件）變成孤兒，而使用者只是
        改了個目標價。`id` 與 `created_at` 由呼叫端負責原樣帶回。

        SCALE-11：比對的是資料庫裡**既有那一列**的 `owner_id`，不是
        `sc.owner_id`（`update_scenario()` 本來就刻意不寫入
        `sc.owner_id`，見既有 `test_updating_a_scenario_does_not_
        touch_its_owner_id`——`sc` 這個參數上的 `owner_id` 欄位值
        本來就不代表任何權威，不能拿來做授權判斷）。"""

    def clear_results(self, scenario_id: str, *, owner: str) -> None:
        """清掉該劇本的全部結果與原始快照，保留劇本本身與事件紀錄（#132）。

        用於 thesis 改變之後：目標價餵進 baseline_return、目標月決定選哪
        些到期日，兩者一改，舊結果的每個數字都是對著另一個問題算出來的。
        留著它們就是拿舊結果冒充新的。事件不刪——那是不可變的事實。

        SCALE-16（#267）：一併清掉 `current_results` 那一份——否則
        thesis 改變後，historical ledger 雖然清空了，`latest_result()`
        （現在讀 `current_results`）仍會回傳改變前那份過期的完整
        view，使用者會在詳細頁看到「對著舊問題算出來的答案」冒充新
        結果，這正是本方法存在的目的所要防止的那種狀態。

        `owner` 不符時整個是 no-op（不清空別人的資料）。"""

    def archive_scenario(self, scenario_id: str, *, owner: str, ts: str) -> bool:
        """回傳是否真的封存了（不存在、已封存、或屬於別的 owner，皆回
        False）。資料不刪除。"""

    def restore_scenario(self, scenario_id: str, *, owner: str, ts: str) -> bool:
        """回傳是否真的還原了（不存在、本來就未封存、或屬於別的
        owner，皆回 False）。清空 `archived_at`，results／snapshots／
        events 不受影響。`ts` 只為跟 `archive_scenario` 同一種呼叫慣例
        （呼叫端算一次 timestamp，同時餵給這裡與事件紀錄）保留，
        `Scenario` 沒有「還原於」欄位需要落盤。"""

    def delete_scenario(self, scenario_id: str, *, owner: str) -> bool:
        """永久刪除（TR3／#90）。回傳是否真的刪了東西——**只允許刪除
        已封存、且屬於這個 owner 的劇本**：不存在、尚未封存
        （`archived_at is None`）、或屬於別的 owner，皆回 `False`、
        資料原封不動，這是安全閘門，永久刪除必須先進垃圾桶。
        真的刪除時 cascade 清掉該 `scenario_id` 名下的
        results／snapshots／events／**current_results**（SCALE-16／
        #267 新增，同一種「劇本沒了、它的資料也不該留著」道理），不留
        任何痕跡（不是軟刪除）。"""

    def save_result(self, rec: ResultRecord) -> None:
        """SCALE-16（#267，Stage 1-5）：寫進 historical fact ledger——
        每次刷新恆定新增**一列**（PK 含 `analyzed_at`），append-only，
        同一 `(scenario_id, analyzed_at)` 重複寫入才覆蓋（冪等）。
        呼叫端自本票起一律傳入 `rec.view=None`（歷史列不再永久保存
        完整 view payload），但 SCALE-01 的 6 個 fact context 欄位、
        `best_return`／`representative_candidate`／`spot`／
        `per_family`／`family_eligibility` 仍照常寫入——這一列存在的
        目的正是永久保留「這個歷史時刻當時發生了什麼」的事實，只是不
        再連帶背負它的完整衍生 payload。舊資料（本票之前寫入、`view`
        非 `None` 的既有列）**原封不動**，本方法對它們的既有內容零
        影響（不做任何 UPDATE／NULL 化）。"""

    def save_current_result(self, rec: ResultRecord) -> None:
        """SCALE-16（#267，Stage 1-5）：current full-view
        materialization——每個 `scenario_id` 恆定**一份**，覆寫更新
        （PK 是 `scenario_id` 本身，不含 `analyzed_at`）。`rec.view`
        必須是完整、非 `None` 的 view dict——這張表存在的唯一理由就是
        持有它，供 current detail／heatmap／champion／ranking／
        `/iv-history` 等既有 hot read path 使用（`latest_result()` 自
        本票起改讀這張表，不再讀 historical ledger）。與
        `save_result()`（ledger，append-only）分開呼叫、分開寫入，
        `main.py::_refresh_and_save()` 對同一次刷新算出的
        `ResultRecord` 各呼叫一次，兩邊各自扮演自己的角色。"""

    def latest_result(self, scenario_id: str, *, owner: str) -> ResultRecord | None:
        """SCALE-16（#267）：改讀 `current_results`（不再是 historical
        ledger 裡 `analyzed_at` 最大的那一列）——語意對呼叫端沒有變化
        （仍然是「這個劇本現在的完整結果」），只是來源換成一張恆定
        一列、不需要 `ORDER BY ... LIMIT 1` 掃描歷史的表，且該列的
        `view` 保證非 `None`（`save_current_result()` 的唯一寫入來源
        本來就要求如此）。這個劇本從未成功刷新過（含 thesis 改變後
        `clear_results()` 剛清空）時回 `None`。"""

    def latest_summaries(self, *, owner: str) -> dict[str, ResultSummary]:
        """每個劇本最新一次結果的摘要，key ＝ scenario_id，範圍限定
        `owner` 名下的劇本。

        沒跑過的劇本不出現在結果裡（呼叫端據此顯示「—」，而不是拿一個
        假的零值當成真的收益率）。專屬查詢的理由見契約測試：清單頁
        不該為了一個數字把每份 view（十萬字元等級）都搬一次。

        SCALE-16（#267）：改讀 `current_results`——每個劇本恆定一列，
        不再需要對 historical ledger 做 `DISTINCT ON`／`ORDER BY`
        才能挑出最新一筆（該表本身就是最新一筆，不含 view 欄位的
        窄選取沿用既有慣例）。"""

    def result_history(self, scenario_id: str, *, owner: str | None) -> list[ResultRecord]:
        """依 analyzed_at 遞增排序的完整歷史。

        排序依 `analyzed_at` 的字典序——所有產生端都輸出同一種格式的
        ISO 字串（UTC offset、秒精度），字典序才等於時間序。

        `owner`：SCALE-11 必填 keyword-only。`owner=None` 比照
        `list_scenarios()` 的同一種例外，只給
        `backfill_result_fact_context()` 使用（該腳本已經從
        `list_scenarios(owner=None)` 拿到跨全部 owner 的劇本清單，
        對每一筆歷史結果一視同仁地補齊 fact context，不該再對它們的
        owner 過濾一次）；production HTTP 路徑一律傳真實 owner 字串，
        不符的劇本回空清單（與「這個劇本不存在」同一種行為）。"""

    def result_timestamps(self, scenario_id: str, *, owner: str) -> list[str]:
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

        SCALE-11：`owner` 是繼 `scenario_id` 之後**第二個**（也是最後
        一個）過濾參數——當年 SCALE-02 的 docstring 已預告「直接在這裡
        的兩段 WHERE 子句上各加一個條件即可覆蓋，不構成繞過 owner
        boundary 的旁路」，這裡就是那個承諾的兌現。劇本不屬於這個
        owner 時回空清單，不拋錯（與「這個劇本不存在」同一種行為，
        呼叫端在此之前已經過 `_require()` 授權，這裡是防禦性的第二
        層，不是主要判斷點）。"""

    def result_fact_context(self, scenario_id: str,
                            analyzed_at: str) -> ResultFactContext | None:
        """SCALE-01（#252）：單一 `(scenario_id, analyzed_at)` 的窄查詢
        ——只回傳 `ResultFactContext` 的欄位，不觸碰／不解析 `view`
        （Postgres 這條路徑的 SQL 一開始就不 SELECT `view`）。找不到
        這個 fact row 時回 `None`；找得到但尚未 backfill（各欄位皆為
        `None`）時回傳一個全欄位皆 `None` 的 `ResultFactContext`，
        呼叫端據此分辨「這列還沒 backfill」與「這列根本不存在」。"""

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict, *, owner_id: str | None = None) -> None:
        """原始選擇權鏈快照（`ChainSnapshot` 的 dict 形式）。

        與結果分開存：一份快照數百 KB（數千筆合約），歷史查詢
        （`result_history`）不該每次把它一起撈出來。

        `owner_id`（SCALE-06／#256）：選填，預設 `None`——與
        `Scenario.owner_id` 同一個資料 boundary 標記，本票不查詢
        過濾。"""

    def get_snapshot(self, scenario_id: str, analyzed_at: str, *,
                     owner: str) -> dict | None:
        """SCALE-11：`owner` 不符時回 `None`（與「這一列不存在」同一種
        行為）。"""

    def get_snapshot_owner(self, scenario_id: str,
                           analyzed_at: str) -> str | None:
        """SCALE-06（#256）：窄讀取，只回這一列的 `owner_id`，不解析／
        回傳快照本身（那份是數百 KB 等級，`get_snapshot()` 已有的用途
        不該為了讀一個欄位被迫多做一次）。找不到這一列與「這一列存在但
        `owner_id` 尚未 backfill」都回 `None`——與 `get_snapshot()` 找不到
        列時的既有語意一致（呼叫端本來就無法從 `None` 分辨這兩種情況，
        `result_fact_context()` 才需要分辨「找不到」與「NULL」，那是
        因為它回傳一整個具名物件；這裡只回一個值，`None` 天然涵蓋兩種
        情況，不需要引入哨兵）。"""

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict,
                     owner_id: str | None = None) -> None: ...

    def list_events(self, *, scenario_id: str | None = None,
                    owner: str) -> list[dict]:
        """依寫入順序（append-only）回傳。

        SCALE-11：`owner` 必填 keyword-only——`scenario_id=None`
        （既有的「不指定就回全部」語意）過去會回傳**每一個 owner**
        的事件，是本票明文點名「不得漏 diagnostics」同一類別裡最寬
        的既有開放面之一。加上 `owner` 之後，即使不指定
        `scenario_id`，也只回落盤時記到這個 owner 名下的事件。"""

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

    # ---------- 資料源設定與 credential（Settings／#124，owner 化 SCALE-13／#264） ----------
    #
    # SCALE-13（#264）：這 3 個概念從「單例／provider-key」升級成
    # per-owner。**不是原地改 PK**——那需要在同一個 migration 裡先
    # backfill 舊列的 owner_id 才能安全套用新 PK 約束，風險與部署順序
    # 依賴都比「另開一組新表」高。改成 additive-first：新表
    # （`owner_settings`／`owner_credentials`／`owner_verifications`）
    # 從第一天就是正確的 per-owner 形狀，舊表（`data_source_settings`／
    # `provider_credentials`／`provider_verifications`）原樣保留、
    # **停止寫入但仍可讀**——這就是票面「先 dual-read...再停止舊 shape
    # 的 production read/write」的落地：write 全部只進新表；read 對
    # 新表 miss 時 fall back 讀舊表（read-through），讀到就順手 write-
    # through 進新表（下次直接命中新表），讓 AC-1「solo-owner 下行為
    # 逐位元不變」不必依賴任何人先手動跑過 backfill 腳本才成立——正式
    # 環境既有資料（若存在）在被讀到的當下就自動遷移完畢。`delete_
    # credential()` 因此必須**同時清舊表與新表**：否則使用者明確刪除
    # 後，下次讀取的 read-through 還是會把舊表裡沒被清掉的資料復活
    # （唯一會被這條「殭屍復活」風險咬到的操作）。

    def get_settings(self, *, owner: str) -> DataSourceSettings | None:
        """這個 owner 從未存過任何設定、也沒有可 read-through 的舊資料
        時回 `None`（呼叫端據此用兩列的預設值）。"""

    def save_settings(self, settings: DataSourceSettings) -> None:
        """寫進新表 `owner_settings`，覆蓋既有那一筆——單一狀態，不是
        歷史序列。`settings.owner_id` 必須非 `None`（`require_owner()`
        守門）；舊表 `data_source_settings` 這個方法起不再寫入。"""

    def get_credential(self, provider: str, *, owner: str) -> ProviderCredential | None: ...

    def save_credential(self, cred: ProviderCredential) -> None:
        """寫進新表 `owner_credentials`，同一個 (owner, provider) 重複
        寫入即覆蓋（換 token 就是這條路徑）。`cred.owner_id` 必須非
        `None`；舊表這個方法起不再寫入。"""

    def delete_credential(self, provider: str, *, owner: str) -> bool:
        """回傳是否真的刪了東西（本來就沒存過回 `False`）——只看新表
        `owner_credentials` 有沒有這一列決定回傳值，但**新舊兩張表都
        會清**（見上方區塊說明的殭屍復活風險）。

        一併清掉該 (owner, provider) 的驗證結果——那筆結果講的是
        「**那把** token 能不能用」，token 沒了它就失去意義，留著會讓
        設定頁在沒有 credential 的情況下顯示「已連線」。"""

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

    def get_verification(self, provider: str, *, owner: str) -> ProviderVerification | None:
        """從未測過、也沒有可 read-through 的舊資料時回 `None`
        （＝「未設定」或「尚未驗證」）。"""

    def save_verification(self, v: ProviderVerification) -> None:
        """寫進新表 `owner_verifications`，覆蓋該 (owner, provider)
        既有那一筆——單一狀態，不是歷史序列。`v.owner_id` 必須非
        `None`；舊表這個方法起不再寫入。"""

    def backfill_settings_to_owner(self, owner: str) -> dict[str, int]:
        """SCALE-13（#264）：**明確、可重跑**的批次遷移（AC-3）——不是
        只靠上面三個 read-through 方法「有人剛好去讀才順便搬」，而是
        比照既有 `backfill_missing_owner_ids()` 給操作者一個可以主動
        執行、結果可驗證的動作。

        只搬「新表這個 owner 還沒有」的那一列／那幾列（settings 用
        `owner` 本身查、credentials／verifications 用 `(owner,
        provider)` 逐一查）——**永遠不覆蓋新表已經存在的資料**，不論
        那份資料是先前跑過這個方法留下的，還是使用者在這之間透過
        `save_*()` 自己存過的新值。這讓它天生冪等：重跑對「已經搬過」
        的部分全部回 0，且不會用舊表的陳舊值蓋掉更新的新表資料
        （AC-3「可重跑、可中斷續跑」）。

        回傳 `{"settings": 0|1, "credentials": N, "verifications": M}`
        ——與 `backfill_missing_owner_ids()` 同一種「表名 → 補了幾筆」
        的計數形狀。舊表（`data_source_settings`／`provider_
        credentials`／`provider_verifications`）本身**不受影響、不被
        清空**——這是 additive-first 遷移的一部分，不是單向搬家。"""

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

    def list_diagnostics(self, *, limit: int = 50,
                         owner: str) -> list[DiagnosticEvent]:
        """最新在最上（依寫入順序反排），只回落盤時記到這個 owner
        名下的事件（SCALE-11，`owner` 必填 keyword-only）。"""

    def clear_diagnostics(self, *, owner: str) -> int:
        """清空這個 owner 名下的診斷事件，回傳清掉的筆數
        （SCALE-11——過去無條件清空全部 owner 的資料，是本票明文點名
        「不得漏 diagnostics」的另一個既有開放面）。"""

    # ---------- Ownership A-1 Expand（SCALE-06／#256） ----------

    def backfill_missing_owner_ids(self, owner_id: str) -> dict[str, int]:
        """對 5 張 row-scoped 表（`scenarios`／`results`／`snapshots`／
        `events`／`diagnostics`——SCALE-06／#256 原始 5 張；SW-12／
        #342 前還多一張 SCALE-14／#265 補上的 `narrow_history`，該表
        隨 Spread 淨成本走勢功能整個退休一併移除）**既有**
        `owner_id IS NULL` 的列，整批補上 `owner_id`。回傳
        `{table_name: 更新筆數}`。

        冪等、可重跑：條件式的 `WHERE owner_id IS NULL` 讓重跑只影響
        「還沒補過」的列，不會覆蓋已經有值（含未來若真的支援多重
        owner）的既有資料，重跑第二次全部回 0。**這 5 張表以外的表
        （3 張 singleton user tables、system-wide 市場事實表、
        `chain_backoff`）本方法不觸碰**——見票面範圍界線。

        ⚠ **SCALE-11（#262）部署順序（`/code-review` Spec 軸點名的
        風險，記錄於此供部署前查核）**：一旦 SCALE-11 的 owner query
        boundary 上線（`require_owner()` 等機制強制拒絕 `owner=None`，
        `get_scenario()`／`archive_scenario()` 等改用逐字比對
        `owner_id`），`owner_id IS NULL` 的舊列會對**任何**已解析出的
        身分（含 `identity.SOLO_OWNER`＝`"solo"`）永遠比對失敗——不是
        「讀不到」而已，是連 `_require()` 這個 chokepoint 都會回
        404，等於那些劇本連編輯／封存／刷新都做不到。這是刻意的
        fail-closed 設計，**不是遺漏**，但正式環境部署 SCALE-11 之前
        必須先跑過 `scripts/backfill_owner_ids.py`（呼叫本方法）——
        順序顛倒會讓既有存量資料看起來像全部憑空消失。"""

    # ---------- Ownership A-1 Contract（SCALE-13／#264） ----------

    def owner_id_null_counts(self) -> dict[str, int]:
        """AC-5：對「5＋3 共 8 張 user tables」各自回報目前還有幾筆
        `owner_id IS NULL`——結構性核對用，不是拿來觸發任何行為。

        **5 張**＝SCALE-06 原始 row-scoped 表（`scenarios`／`results`／
        `snapshots`／`events`／`diagnostics`，跟 `backfill_missing_
        owner_ids()` 同一份清單——票面（#264）明文只算「5＋3」，
        SCALE-09／14 才出現的 `narrow_history` 不在這張票枚舉的表列
        裡，本方法刻意不多加；該表已隨 SW-12／#342 Spread 淨成本走勢
        功能退休整個移除，這句話現在恆真）。**3 張**＝
        本票新增的 `owner_settings`／`owner_credentials`／
        `owner_verifications`——它們的 `owner_id` 是 PK 的一部分，
        Postgres／記憶體兩邊都結構上不可能存在 NULL（查詢它們只是
        為了讓呼叫端用同一份 8 表清單一次核對完畢，不必另外記得
        哪 3 張不必查），因此**恆為 0**，不是假設出來的。

        本票**刻意不**把這 5 張既有表的 `owner_id` 收斂成 DB 層級
        `NOT NULL`（`ALTER COLUMN ... SET NOT NULL`）——這 5 張表的
        `owner_id IS NULL` 目前是被至少 14 處既有 storage 契約測試
        （`tests/test_storage_contract.py`）刻意寫入、用來模擬「尚未
        backfill 的舊列」以驗證 `backfill_missing_owner_ids()` 冪等性
        與 SCALE-11 fail-closed 行為本身正確性的必要手段；對 Postgres
        後端加上硬性 `NOT NULL` 會讓這些測試全數以
        `NotNullViolation` 失敗，等於為了一個 AC-5 字面上沒有要求
        （AC-1～AC-7 沒有任何一條要求 DB 層級約束）的額外保證，犧牲
        既有、仍在使用中的回歸覆蓋。SCALE-11 的 `require_owner()`
        fail-closed 讀取路徑已經達成同等的實務保證——任何
        `owner_id IS NULL` 的舊列對任何身分都永久查不到，這正是
        NOT NULL 想要的行為，只是強制點不同（應用層而非 schema
        層）。這是刻意記錄的取捨，Owner 若仍要 DB 層級約束，需要先
        另開一票把那些測試改成不依賴 dataclass 建構式寫入 NULL（例如
        改用繞過型別驗證的原生 SQL helper），非本票能安全一併完成。"""

    # ---------- solo → Owner 一次性遷移（PB-03／#295，Anonymous
    # Public Beta） ----------

    def migrate_owner(self, *, from_owner: str, to_owner: str) -> dict[str, int]:
        """把 `from_owner` 名下全部資料搬到 `to_owner`——逐表
        `UPDATE ... SET owner_id = to_owner WHERE owner_id = from_owner`。
        **冪等**：搬過一次後 `from_owner` 底下已無列，重跑對已搬過的表
        全部回 0（PB-03 AC「腳本重跑第二次為 no-op」）。

        涵蓋**這 9 張表**（PB-03／#295 §6 明文要求不得沿用既有任一份
        既有清單——見下方差異說明；PB-04／#296 的 `delete_owner()`
        共用同一份清單，兩者是本站僅有的兩個「owner-scoped 表」全量
        操作。SW-12／#342 起原本第 10 張 `narrow_history` 隨 Spread
        淨成本走勢功能整個退休一併移除）：
        `scenarios`／`results`／`snapshots`／`events`／`diagnostics`／
        `current_results`／`owner_settings`／
        `owner_credentials`／`owner_verifications`。

        **與既有兩份清單的差異**（PB-03 施工前 repo 現況已確認兩份
        既有清單互相不一致，此處記錄避免未來誤以為可以照抄）：
        - `backfill_missing_owner_ids()` 只有 5 張（同上少
          `current_results`／`owner_settings`／`owner_credentials`／
          `owner_verifications`）——它服務的是「把 `NULL` 補成某個
          值」（`WHERE owner_id IS NULL`），本方法服務的是「把某個
          既有值換成另一個值」（`WHERE owner_id = from_owner`），
          目的不同、範圍也因此不同，不能互相替代。
        - `owner_id_null_counts()` 涵蓋另外 8 張（5 張 row-scoped ＋
          3 張 `owner_*`）。

        回傳 `{table_name: 受影響列數}`。"""

    # ---------- Owner-wide 刪除原語（PB-04／#296，Anonymous Public
    # Beta） ----------

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        """把 `owner_id` 名下全部資料徹底清除——沿用
        `migrate_owner()` 那份 9 張表清單（本站目前**唯一**「owner-
        scoped 表清單」，兩個方法共用，見兩後端實作裡的
        `_OWNER_SCOPED_TABLES` 常數／等義結構），**外加**
        `browser_identities`／`owners` 兩張身份基礎表本身——本方法是
        本站第一個、也是目前唯一一個「刪掉一個 owner」的原語，
        PB-08（閒置清理排程）與 PB-10（Super User 刪除他人資料）都
        直接呼叫它，不是各自重寫一份可能漂移的複本。

        **明確不觸碰**的 shared market facts 表（system-wide，與任何
        單一 owner 無關）：`rate_cache`／`treasury_year_cache`／
        `dividend_cache`／`chain_backoff`／`operational_metrics`／
        `contract_iv_history`／`iv_observations`／`iv_backfill_runs`
        ——這些表結構上沒有 `owner_id` 欄位。

        **單一交易內完成**（postgres 無 FK cascade，全部手動
        DELETE，避免任一張表刪到一半中斷留下半刪狀態）。

        刪掉 `browser_identities`／`owners` 是刻意的：自助刪除
        （PB-04）之後不得留下一顆指向已刪除 owner 的 cookie——下一次
        帶著那顆舊 cookie 的請求在 `resolve_owner_by_token()` 會查
        不到，直接走 PB-02（#294）既有的「token 查不到＝新訪客」
        lazy-creation 路徑自動拿到一個全新身份，不需要另外設計一套
        「重新簽發」邏輯。

        回傳 `{table_name: 受影響列數}`，含 `owners`／
        `browser_identities` 兩張（共 12 個鍵）。這個 owner_id 本來就
        不存在時，全部鍵值皆為 0（不拋錯——「刪除一個不存在的東西」
        視同已經達成目標狀態，冪等）。"""

    # ---------- Owner registry ＋ Browser Identity（PB-01／#292，
    # Anonymous Public Beta，expand，零行為變更） ----------

    def get_owner(self, owner_id: str) -> Owner | None:
        """這個 owner_id 尚未在 `owners` 表建立過列時回 `None`——既有
        `SOLO_OWNER`（`"solo"`）在本票之前從未寫進這張新表，因此本票
        上線當下對它呼叫這個方法也會回 `None`（純粹反映這張表是全新
        的，不代表 solo owner 不存在——它仍然活在既有 5+1 張表裡）。"""

    def resolve_owner_by_token(self, token: str) -> str | None: ...

    def create_owner_with_token(self, owner: Owner,
                                identity: BrowserIdentity) -> None:
        """依 cookie token 建立新 owner＋token（spec §3／§4 的唯一建立
        路徑）——兩筆寫入視為同一次邏輯操作的兩半，呼叫端（PB-02）保證
        `identity.owner_id == owner.owner_id`。`token`／`owner_id`
        皆須事先確定不存在（呼叫端用密碼學安全隨機來源產生，衝突機率
        可忽略），本方法**不**檢查衝突後靜默覆寫——衝突時兩後端各自
        按資料庫既有的 PK 違反行為處理（不吞掉、不假裝成功）。"""

    def touch_browser_identity(self, token: str, *, now: str) -> bool:
        """續命 `last_seen_at`。回傳是否真的更新到東西（token 不存在
        時回 `False`，呼叫端據此判斷這把 cookie 已失效，需要走建立新
        owner 的路徑）。"""

    def touch_owner_activity(self, owner_id: str, *, now: str) -> None:
        """更新 `last_activity_at`。owner 不存在時安靜地什麼都不做
        （不拋錯）——「哪些動作算 activity」與「activity 發生時 owner
        是否保證已存在」都是 PB-02／PB-08 的範圍，本方法只負責寫入這
        個值，不對呼叫時機做任何假設。"""

    def set_owner_protected(self, owner_id: str, protected: bool) -> None:
        """讀寫 `protected` 旗標的寫入半邊；讀取走 `get_owner()`。owner
        不存在時安靜地什麼都不做（不拋錯，理由同 `touch_owner_
        activity()`）。"""

    def claim_browser_token(self, token: str, owner: Owner, *,
                            now: str) -> tuple[str, bool]:
        """SECURITY-FIX-01（deferred owner creation）：把一顆「還沒綁定
        任何 owner」的 cookie token 原子地綁到一個新 owner 上。

        回傳 `(實際綁定的 owner_id, 這次是不是真的新建)`。同一顆 token
        若已經被綁定（包含同一瞬間另一個 serverless instance 搶先綁定），
        **不建立新 owner**，直接回既有的 owner_id 與 `False`——正確性
        建立在 `browser_identities.token` 這個 PK 上，不靠任何
        process-local lock，因此多個 instance 同時首次寫入也只會得到
        一個 owner。"""

    def owner_lifecycle_facts(self) -> list[OwnerLifecycleFacts]:
        """全部 owner 的清理判定原始事實（見 `OwnerLifecycleFacts`），
        一次查詢取得。本方法不套用任何判準——判準在
        `api_app.anonymous_lifecycle.classify()`，這裡只供事實。"""

    def rate_limit_consume(self, buckets: Sequence[RateLimitBucket]) -> int | None:
        """SECURITY-FIX-02：短時間窗濫用計數的「檢查＋扣一次」，**跨所有
        bucket 原子、全有或全無**。

        任何一個 bucket 已經達到上限就回那個 bucket 在 `buckets` 裡的
        索引、**全部都不扣**；全部還有額度才全部加一、回 `None`。呼叫端
        因此可以把「這一次上游抓取」要過的每一層（per-owner、source、
        new-owner tier）一次交進來：被任何一層擋下的那次，不會先在前面
        幾層被扣掉額度——額度只算真的放行（＝真的打上游）的那幾次。

        並發下是精確的，不是軟性上限：多個 serverless instance 同時扣
        同一格時，後到的會等先到的交易結束再讀到新的計數（Postgres 用
        列鎖、依主鍵順序上鎖避免死結；記憶體後端用 lock）。"""

    def purge_rate_limits(self, *, before_epoch: int) -> int:
        """刪掉視窗在 `before_epoch` 之前就已經結束的計數列，回傳刪了
        幾列。source 狀態因此不會被永久保存。"""

    def list_owners(self) -> list[Owner]:
        """跨 owner 的列舉逃生門——供 PB-08 依 lifecycle 條件（例如
        `last_activity_at` 早於某個截止日、且 `protected` 為否）掃描
        待清理的 owner。本方法本身**不套用任何 lifecycle 判準**，只是
        原樣回傳全部 owner 列；篩選邏輯留給 PB-08（沿用既有
        `list_scenarios(owner=None)`／`result_history(owner=None)`
        「刻意的跨 owner 逃生門，語意由呼叫端決定」先例）。"""

    def list_protected_owners(self) -> list[Owner]:
        """只回 `protected=True` 的 owner（#345 A-4）。Historical IV 每次
        請求都要找「那一個」protected owner——用這個窄查詢，不必每次把
        整張 `owners` 表載進記憶體。判準（恰好一個才算數）仍在
        `api_app.main._the_protected_owner_id()`，這裡只負責篩出候選。"""

    # ---------- Role session（AUTH-01／#308，三層角色模型） ----------
    #
    # 本區塊是 spec #307 的儲存層地基，**純 expand**——不接任何 HTTP
    # 端點、不讀任何環境變數、不修改 `identity_resolver()` 或既有
    # `is_superuser()` 行為。呼叫端（AUTH-02）負責產生 token（沿用
    # 既有 `secrets.token_urlsafe(32)` 慣例，比照 `create_owner_
    # with_token()` 的既有分工：token 由呼叫端生成，Storage 只負責
    # 存取）與比對密碼，這裡只回答「這個 token 現在算哪個角色、還
    # 有沒有效」。

    def create_role_session(self, session: RoleSession) -> None:
        """寫入一筆全新的 role session（呼叫端已生成 token、決定好
        `role`）。token 須事先確定不存在（呼叫端用密碼學安全隨機來源
        產生，衝突機率可忽略）——本方法不檢查衝突後靜默覆寫，衝突時
        兩後端各自按資料庫既有的 PK 違反行為處理。"""

    def resolve_role_session(self, token: str) -> RoleSession | None:
        """依 token 查詢。找不到，或找到但 `revoked_at` 非 `None`
        （已撤銷），皆回 `None`——呼叫端不需要另外檢查 `revoked_at`
        欄位，這個方法已經把「還算不算有效」這個判斷做完了。"""

    def revoke_role_session(self, token: str, *, now: str) -> bool:
        """登出：把這個 token 標記為已撤銷（`revoked_at = now`）。
        `now` 由呼叫端傳入（`api_app.clock.now_utc_iso()`），比照既有
        `touch_browser_identity()`／`touch_owner_activity()` 的既有
        分工——Storage 層不自己讀時鐘。回傳是否真的更新到東西（token
        不存在或早已撤銷過時回 `False`），讓呼叫端能分辨「這個 token
        本來就是無效的」與「這次操作真的生效了」。"""

    # ---------- Super User audit trail（PB-10／#301） ----------

    def append_audit_event(self, event: SuperUserAuditEvent) -> None:
        """寫入一筆 Super User 高風險操作紀錄——append-only，**無保留
        上限**（見 `SuperUserAuditEvent` docstring，這是它與
        `diagnostics`／`operational_metrics` 兩者刻意不同之處）。"""

    def list_audit_events(self, *, limit: int = 200) -> list[SuperUserAuditEvent]:
        """最新在最上，供 Super User 自己查閱／稽核使用。`limit`
        只決定這次查詢回幾筆，不是保留政策本身——底層紀錄不會因為
        沒被查詢就消失（與 `list_diagnostics(limit=...)` 的
        `RETENTION_LIMIT` 語意不同，那裡的上限是真的物理刪除）。"""

    # ---------- S0 最小可觀測性（SCALE-08／#258） ----------

    def record_metric(self, metric: str, bucket: str, *, source: str = "",
                      symbol: str = "", count: int = 0,
                      amount: float = 0.0) -> None:
        """`api_app.metrics.record()` 唯一呼叫的寫入點——upsert 到
        `(metric, bucket, source, symbol)` 這個桶：`count`／`total`
        累加，`max_value` 取較大值。同時把同一個 `metric` 底下比
        `api_app.metrics.retention_cutoff(bucket)` 更舊的桶清掉
        （trim-on-write，比照既有 `diagnostics` 表的既有慣例，只是
        這裡按天而非按總筆數裁，讓「回答昨天」這件事永遠可行）——
        AC-3 要求 bounded，不得無限成長。"""

    def metric_summary(self) -> list[MetricEntry]:
        """目前還在 retention 窗內的全部桶——供 operator 端點彙整成
        `METRIC_CATALOGUE` 全部類別（SCALE-08 當時七類，PB-08／#300
        起八類）的答案。不分頁、不搜尋（AC-6：這是給運維人工核對用，
        不是給一般使用者的 API）。"""

    def metric_total(self, metric: str, bucket: str) -> int:
        """PB-06（#299，Anonymous Public Beta）：`(metric, bucket)`
        這個切片下、跨全部 `source`／`symbol` 的 `count` 總和——
        `Global Vendor Fuse`（`api_app.vendor_fuse`）每次抓鏈前都要
        查一次，因此需要比 `metric_summary()`（撈出整個 30 天視窗
        全部桶）便宜的 targeted 查詢，同一張表、同一個既有欄位，不是
        新的計數維度。查無資料時回 `0`，不是 `None`——「今天還沒有
        任何一次抓取」是合法的、不特殊的初始狀態。"""

    def table_size_metrics(self) -> dict:
        """S0 第 6 項——`results`／`snapshots` 兩表的列數、總大小、
        單列大小分布，**query-time gauge，不持久化**（每次呼叫即時
        查詢，不寫進 `operational_metrics`）。回傳形狀：
        `{"results": {"row_count", "total_bytes", "avg_row_bytes",
        "max_row_bytes"}, "snapshots": {同上}}`——任一表沒有任何列時
        對應的大小/分布欄位為 `None`（沒有東西可以算平均／最大值，
        不是假裝成 0）。"""

    def scenario_count_total(self) -> int:
        """PB-11（#303，Anonymous Public Beta）：site-wide 劇本總數
        （跨全部 owner，含已封存）——**query-time gauge，不持久化**，
        與 `table_size_metrics()` 同一種形狀（單純 `COUNT(*)`，不是
        撈出每一列再數）。供 `/api/ops/metrics` 算「每個 owner 平均
        幾個劇本」使用；本方法不接受 `owner` 參數、不做任何過濾——
        這正是它跟既有 `list_scenarios(owner=...)` 不同的地方，也是
        SCALE-08 AC-7 紅線（`operational_metrics` 無 `owner_id`）
        自然成立的原因之一：這裡連 `operational_metrics` 表都不碰。"""

    @property
    def kind(self) -> str:
        """"memory" | "postgres"——供 /api/health 如實回報實際用的是哪個。"""

    def request_scope(self) -> AbstractContextManager[None]:
        """一次 HTTP request 期間的資源 scope——由 `main.py` 的
        `_request_scope_middleware` 在每個 request 最外層 `with` 起來。

        ARCH-REVIEW-001（#343）：兩個後端本來就都實作了這個方法
        （`postgres.py` 共用同一條惰性連線；`memory.py` 是純 no-op，
        它的 docstring 明說「存在的唯一理由是讓 middleware 走跟
        production 同一條分支」），唯獨 Protocol 沒宣告，於是 middleware
        只能 `getattr(_db(), "request_scope", None)` 去猜——抽象在這裡
        是漏的：契約沒講的東西，呼叫端卻依賴它存在。補進契約後
        middleware 直接呼叫，契約測試也涵蓋得到。

        對沒有連線概念的後端，實作成 no-op contextmanager 即可，不是
        選配。"""


@dataclass(frozen=True)
class MetricEntry:
    """S0 最小可觀測性（SCALE-08／#258，見 `api_app/metrics.py`）：一個
    `(metric, bucket, source, symbol)` 桶的目前聚合值。**只存這幾個
    純量欄位**——不存 `scenario_id`／`owner_id`／任何報價或合約資料
    （AC-7 紅線）。

    `source`／`symbol` 未使用時為空字串 `""`、不是 `None`——複合主鍵裡
    `NULL` 在 SQL 語意上不等於自己（`NULL != NULL`），會讓 Postgres 的
    `ON CONFLICT` upsert 對「兩個維度都缺席」的列每次都當成新列插入，
    而不是疊加到同一個桶；空字串沒有這個問題，兩個後端因此可以共用
    同一套「缺席維度＝空字串」語意。

    `count`：這個桶累積的事件次數。`total`：累積量值總和（供
    `refresh_duration_ms` 這類需要平均值的指標；純計數型指標不傳
    `amount`，維持 0）。`max_value`：這個桶目前看過的單筆最大值（供
    概略回答「量級大概多大」，不是完整分位數）——這個欄位在
    `MetricEntry` 直接建構時預設 `None` 只是型別上允許，實際透過
    `Storage.record_metric()` 寫入的列一定會是浮點數（純計數型指標
    `amount` 恆為 0.0，因此 `max_value` 也會穩定停在 0.0，不是
    `None`——`None` 不代表任何特別語意，只是尚未寫過的列在型別系統
    上的合法初值）。"""
    metric: str
    bucket: str            # 日粒度 "YYYY-MM-DD"
    source: str = ""
    symbol: str = ""
    count: int = 0
    total: float = 0.0
    max_value: float | None = None


class ScenarioExists(Exception):
    pass
