"""Neon Postgres 儲存 adapter（V2／#50）。

serverless 前提：函式壽命極短，不在程序內自行維護長連線，仍靠 Neon 的
pooler 端點負責連線池化。**PERF-01（#177）／T02（#186）修形**：同一個
HTTP request 期間共用同一條連線（`request_scope()`，由 `main.py` 的
middleware 進入時註冊、離開時歸還），不是像 warm `/iv-history` 這種一次
觸發十幾次 `Storage` method 呼叫的路徑那樣，每次呼叫都各自重新開一條
全新連線；**惰性**：scope 進入時不主動開連線，第一次真正呼叫到某個
`Storage` method 才開——完全不碰 storage 的 request 因此零連線握手。
沒有進到 `request_scope()`（例如測試直接呼叫 adapter method）或 scope
內共用連線已經試過且失敗時，退回逐次開連線的既有行為，見 `_connect()`。

大 JSON（結果 view dict，十萬字元等級）存 JSONB：psycopg 直接對應
Python dict，不需自己 `json.dumps`。時間欄位存 ISO 字串而非 timestamptz
——與引擎既有的 ISO 字串慣例一致，避免時區在邊界上被悄悄轉換。
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

import psycopg
from psycopg.types.json import Jsonb

from . import (ChainBackoffEntry, ContractHistory, DataSourceSettings,
               DividendCacheEntry, IvBackfillRun, IvObservation,
               ProviderCredential, ProviderVerification, RateCacheEntry,
               ResultFactContext, ResultRecord, ResultSummary, Scenario,
               ScenarioExists, TreasuryYearCacheEntry, UsageSetting)
from ..diagnostics import RETENTION_LIMIT, DiagnosticEvent

# 每個 lambda 程序只需建表一次。`IF NOT EXISTS` 在 Postgres 並非完全
# race-free（同時冷啟動可能撞上 duplicate 錯誤），因此除了這個旗標，
# 下面也把重複建立視為良性。
_schema_ready: set[str] = set()

class _ScopeState:
    """一個 `request_scope()` 的可變狀態——`conn` 惰性填入（T02／#186）：
    scope 剛進入時是 `None`，第一次真正呼叫 `_connect()` 才開。`failed`
    記著這個 scope 內共用連線是否已經試過且失敗，避免同一個 scope 反覆
    對著暫時連不上的資料庫重試。"""

    __slots__ = ("dsn", "conn", "failed")

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.conn = None
        self.failed = False


# PERF-01（#177）／T02（#186）：目前 request 的 scope 狀態——放在
# `contextvars.ContextVar`（模組層級）而不是 `PostgresStorage` 單例
# 物件的一般屬性上，避免併發 request 互相汙染彼此借到的連線（ASGI
# 併發處理多個 request 時，同一個 `PostgresStorage` 實例會被共用，
# 一般屬性沒有 per-request 隔離）。狀態物件存 `dsn` 一起是防禦性寫法：
# 理論上若同一個 process 裡有兩個不同 DSN 的 `PostgresStorage` 實例，
# 借到的連線也不會被錯誤的實例借走。
_request_scope_state: contextvars.ContextVar = contextvars.ContextVar(
    "postgres_request_scope_state", default=None)


class _BorrowedConnection:
    """讓 `with self._connect() as conn:` 這個既有呼叫慣例完全不用改
    ——借用中的連線在 `__exit__` 不真的關閉，它的生命週期歸
    `PostgresStorage.request_scope()` 的 `finally` 管，不是每個個別
    method 呼叫自己的 `with` 區塊。"""

    def __init__(self, conn) -> None:
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info) -> bool:
        return False   # 不吞例外、不關閉連線

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id            TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    direction     TEXT NOT NULL,
    target_price  DOUBLE PRECISION NOT NULL,
    target_month  TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    strategies    JSONB NOT NULL,
    created_at    TEXT NOT NULL,
    archived_at   TEXT,
    best_price    DOUBLE PRECISION,
    worst_price   DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS results (
    scenario_id             TEXT NOT NULL,
    analyzed_at             TEXT NOT NULL,
    view                    JSONB NOT NULL,
    best_return             DOUBLE PRECISION,
    representative_candidate JSONB,
    spot                    DOUBLE PRECISION,
    -- T07（#224，Initial V2）：per-family 代表候選與最高報酬，見
    -- `_MIGRATIONS` 底下同名欄位的 ALTER 說明。
    per_family              JSONB,
    -- T10（#227，Initial V2）：最近一次分析當下算出的 family 可選／
    -- 不可選 verdict，見 `_MIGRATIONS` 底下同名欄位的 ALTER 說明。
    family_eligibility      JSONB,
    PRIMARY KEY (scenario_id, analyzed_at)
);
-- V3（#51）／MVP-v2（#77、#78）加的欄位。既有部署已經有 results 表，
-- `CREATE TABLE IF NOT EXISTS` 不會補欄位——沒有這兩行，正式環境會在
-- INSERT 時炸 UndefinedColumn。
ALTER TABLE results ADD COLUMN IF NOT EXISTS best_return DOUBLE PRECISION;
ALTER TABLE results ADD COLUMN IF NOT EXISTS representative_candidate JSONB;
ALTER TABLE results ADD COLUMN IF NOT EXISTS spot DOUBLE PRECISION;
CREATE TABLE IF NOT EXISTS snapshots (
    scenario_id   TEXT NOT NULL,
    analyzed_at   TEXT NOT NULL,
    snapshot      JSONB NOT NULL,
    PRIMARY KEY (scenario_id, analyzed_at)
);
CREATE TABLE IF NOT EXISTS events (
    seq           BIGSERIAL PRIMARY KEY,
    ts            TEXT NOT NULL,
    scenario_id   TEXT,
    event         TEXT NOT NULL,
    payload       JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS results_scenario_idx ON results (scenario_id, analyzed_at);
CREATE INDEX IF NOT EXISTS events_scenario_idx ON events (scenario_id, seq);
-- 利率曲線快取（#67）：單一一筆狀態，不是歷史序列——`id` 固定為 1，
-- `CHECK` 讓「只有一列」在資料庫層面成立，不只是應用層的約定。
CREATE TABLE IF NOT EXISTS rate_cache (
    id                INTEGER PRIMARY KEY DEFAULT 1,
    fetched_at        TEXT NOT NULL,
    curve             JSONB,
    note              TEXT NOT NULL,
    last_success_at   TEXT,
    market_day        TEXT,
    attempted_day     TEXT,
    CHECK (id = 1)
);
-- 配息資料快取（#123）：**per-symbol**（q 是標的的性質，不是全站單一
-- 值，跟 rate_cache 的單筆設計不同），否則欄位語意逐一對應 rate_cache。
CREATE TABLE IF NOT EXISTS dividend_cache (
    symbol            TEXT PRIMARY KEY,
    fetched_at        TEXT NOT NULL,
    history           JSONB,
    note              TEXT NOT NULL,
    last_success_at   TEXT,
    market_day        TEXT,
    attempted_day     TEXT
);
-- Treasury 利率曲線列快取（PERF-03／#179）：per-year——歷史 reconstruction
-- 逐一觀測日查表，任何歷史日期的查詢結構上只可能被它所在年份的這筆
-- 紀錄滿足；欄位語意逐一對應 rate_cache／dividend_cache 同一套三態
-- 設計，差異只在「成功是否永久新鮮」由呼叫端依 year 是否早於今年判斷。
CREATE TABLE IF NOT EXISTS treasury_year_cache (
    year              INTEGER PRIMARY KEY,
    fetched_at        TEXT NOT NULL,
    rows              JSONB,
    note              TEXT NOT NULL,
    last_success_at   TEXT,
    market_day        TEXT,
    attempted_day     TEXT
);
-- SCALE-04（#255，Scaling Foundation Cboe 429 韌性）：上游限流的控制
-- 狀態，鍵是 **source**（provider-global，不分 symbol——見
-- docs/spec/scaling-foundation.md §8.4 2026-09-06 訂正）。
--
-- ⚠ RL-19（紅線）：這張表只存「上游現在讓不讓我打」的控制中繼資料，
-- **不得儲存任何 chain payload、市場報價、合約資料**。它與
-- ADR-0001／OD-05 evidence gate 卡住的 chain shared cache（存市場
-- 資料本身）是不同的東西，未來擴充這張表前務必重讀這條紅線。
CREATE TABLE IF NOT EXISTS chain_backoff (
    source                TEXT PRIMARY KEY,
    blocked_until         TEXT,
    retry_after_seconds   DOUBLE PRECISION,
    consecutive_failures  INTEGER NOT NULL,
    observed_at           TEXT NOT NULL,
    last_success_at       TEXT
);
-- 資料源設定（Settings／#124）：兩列的模式選擇，單一一筆狀態——跟
-- `rate_cache` 同一個 `id = 1` ＋ `CHECK` 的寫法。存 JSONB 而不是攤平成
-- 欄位：這份結構會隨資料用途增減而變（目前兩列），JSONB 讓它變動時
-- 不必每次都補一條 ALTER。
CREATE TABLE IF NOT EXISTS data_source_settings (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    settings      JSONB NOT NULL,
    updated_at    TEXT NOT NULL,
    CHECK (id = 1)
);
-- Provider credential（Settings／#124）：key 是 **provider**，不是資料
-- 用途——兩個用途選同一個 Provider 時共用這一列，使用者因此不必輸入
-- 同一把 token 兩次。
CREATE TABLE IF NOT EXISTS provider_credentials (
    provider      TEXT PRIMARY KEY,
    token         TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
-- 測試連線的結果（Settings／#125）：per-provider 單一狀態。與
-- credential 分兩張表——刪 token 時連帶刪這一筆（見 delete_credential），
-- 但存 token 不必動它（還沒測過就是還沒測過）。
CREATE TABLE IF NOT EXISTS provider_verifications (
    provider      TEXT PRIMARY KEY,
    ok            BOOLEAN NOT NULL,
    reason        TEXT,
    checked_at    TEXT NOT NULL
);
-- 歷史 IV 觀測（#129）：鍵是 **(symbol, 日期)**，沒有 scenario 欄位——
-- 同一 ticker 的所有 Scenario 共用同一份，資料模型上就不可能因 scenario
-- 不同而分家、重複燒 vendor 額度。
CREATE TABLE IF NOT EXISTS iv_observations (
    symbol        TEXT NOT NULL,
    observed_on   TEXT NOT NULL,
    surface       JSONB NOT NULL,
    fetched_at    TEXT NOT NULL,
    PRIMARY KEY (symbol, observed_on)
);
-- 每 symbol 每天只跑一個 backfill 批次（#130）：沒有這張表的話，同一天
-- 每開一個同 ticker 的 Scenario 就會再燒一批額度。
CREATE TABLE IF NOT EXISTS iv_backfill_runs (
    symbol        TEXT PRIMARY KEY,
    ran_on        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    note          TEXT
);
-- Exact-contract 歷史 IV 快取（HIVT-02／#153）：鍵是 OCC contract
-- symbol——exact contract identity 本身（spec #151 §2 絕對紅線）。跟
-- `iv_observations`（per-symbol、per-day、整條鏈）刻意不同的資料模型：
-- 單合約端點一次呼叫回整段區間，這裡整個合約的觀測史存成一筆 JSONB
-- 陣列，不是逐日一列。
CREATE TABLE IF NOT EXISTS contract_iv_history (
    contract_symbol   TEXT PRIMARY KEY,
    points            JSONB NOT NULL,
    fetched_through   TEXT,
    last_attempt_on   TEXT,
    last_status       TEXT NOT NULL,
    last_note         TEXT
);
-- Application diagnostics（DG-02／#145）：**不併進 `events` 表**——後者
-- 是 scenario-scoped、永不修剪的領域事實，這張是運維紀錄、會被修剪、
-- 且不必然掛在某個 scenario 底下。`seq` 沿用 `events` 同一個排序慣例
-- （時間戳字串同秒時仍有確定順序）。
CREATE TABLE IF NOT EXISTS diagnostics (
    seq             BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL,
    correlation_id  TEXT NOT NULL,
    ts              TEXT NOT NULL,
    subsystem       TEXT NOT NULL,
    stage           TEXT NOT NULL,
    severity        TEXT NOT NULL,
    message         TEXT NOT NULL,
    context         JSONB NOT NULL
);
"""

# 遷移**必須與建表分開送**。psycopg 對「無參數、多語句」的 execute 走
# simple-query 協定，Postgres 會把整批包成一個 implicit transaction——
# 同時冷啟動撞上 DuplicateTable 時，整批（含這行 ALTER）會一起 rollback，
# 而下面仍會把 dsn 標成 ready，該 process 從此每次寫入都撞 UndefinedColumn。
_MIGRATIONS = """
ALTER TABLE results ADD COLUMN IF NOT EXISTS best_return DOUBLE PRECISION;
ALTER TABLE results ADD COLUMN IF NOT EXISTS representative_candidate JSONB;
ALTER TABLE results ADD COLUMN IF NOT EXISTS spot DOUBLE PRECISION;
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS best_price DOUBLE PRECISION;
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS worst_price DOUBLE PRECISION;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS last_success_at TEXT;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS market_day TEXT;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS attempted_day TEXT;
-- PC-03（#201，spec #198）：nullable——既有部署的舊列沒有這一欄，讀回
-- 時用跟 `emit()` 相同的規則（severity 為 warning／error 視為 true）
-- 補一份合理值，而不是硬性 NOT NULL 逼一次資料回填。
ALTER TABLE diagnostics ADD COLUMN IF NOT EXISTS user_facing BOOLEAN;
-- T07（#224，Initial V2）：既有部署的 results 表沒有這一欄——舊列
-- 讀回時是 NULL，`ResultRecord.per_family` 天然是 `None`，不影響任何
-- 既有行為（純加法欄位，非 NOT NULL，不需要資料回填）。
ALTER TABLE results ADD COLUMN IF NOT EXISTS per_family JSONB;
-- T10（#227，Initial V2）：既有部署的 results 表沒有這一欄——舊列
-- 讀回時是 NULL，`ResultRecord.family_eligibility` 天然是 `None`，
-- 不影響任何既有行為（純加法欄位）。
ALTER TABLE results ADD COLUMN IF NOT EXISTS family_eligibility JSONB;
-- SCALE-01（#252，Scaling Foundation Stage 1-0）：把寄生在 `view`
-- JSONB 內部的估值輸入與 provenance 複製成獨立、可窄查詢的欄位（見
-- `option_chaser.store.historical_fact_context()`）。既有部署的舊列
-- 讀回時全部是 NULL——backfill 腳本
-- （`scripts/backfill_result_fact_context.py`）負責補齊，讀取端在
-- backfill 完成前必須容忍 NULL。純加法，不影響 `view` 本身。
ALTER TABLE results ADD COLUMN IF NOT EXISTS resolved_params JSONB;
ALTER TABLE results ADD COLUMN IF NOT EXISTS requested_strategies JSONB;
ALTER TABLE results ADD COLUMN IF NOT EXISTS engine_version TEXT;
ALTER TABLE results ADD COLUMN IF NOT EXISTS view_schema_version INTEGER;
ALTER TABLE results ADD COLUMN IF NOT EXISTS history_replay_version INTEGER;
-- SCALE-01（`/code-review` Spec 軸回饋）：provenance 明文要求的
-- 「snapshot source」半邊——原本 5 個欄位只有 rate/q 那一半（藏在
-- resolved_params 裡），沒有快照本身的資料源，仍得解析 view 才查得
-- 到；「snapshot fetched_at」半邊不需要獨立欄位，`analyzed_at` 本身
-- 就是它。
ALTER TABLE results ADD COLUMN IF NOT EXISTS snapshot_source TEXT;
-- SCALE-06（#256，Scaling Foundation Ownership A-1 Expand）：5 張
-- row-scoped 表新增 nullable `owner_id`——只是資料 boundary 標記，
-- **不是** authentication／privacy（那是 out-of-scope 的 A-2）。既有
-- 部署的舊列讀回時是 NULL，`Storage.backfill_missing_owner_ids()`
-- 負責補齊；本票**不**在任何查詢路徑加過濾（那是 SCALE-11 的範圍）。
-- 3 張 singleton／provider-key 表（`provider_credentials`／
-- `data_source_settings`／`provider_verifications`）與 system-wide
-- 共用表（rate/treasury/dividend/IV caches、`chain_backoff`）刻意
-- 不在這裡——前者留給 SCALE-13 做結構遷移，後者本來就不該有 owner。
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS owner_id TEXT;
ALTER TABLE results ADD COLUMN IF NOT EXISTS owner_id TEXT;
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS owner_id TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS owner_id TEXT;
ALTER TABLE diagnostics ADD COLUMN IF NOT EXISTS owner_id TEXT;
"""

# 冷啟動競爭下的良性錯誤：別人已經建好／加好了。
_BENIGN = (psycopg.errors.DuplicateTable, psycopg.errors.DuplicateObject,
           psycopg.errors.DuplicateColumn, psycopg.errors.UniqueViolation)

_RESULT_COLS = ("scenario_id, analyzed_at, view, best_return, "
                "representative_candidate, spot, per_family, "
                "family_eligibility, resolved_params, requested_strategies, "
                "engine_version, view_schema_version, history_replay_version, "
                "snapshot_source, owner_id")

# SCALE-01（#252）：`result_fact_context()` 的窄查詢欄位——刻意不含
# `view`／`best_return`／`representative_candidate` 等，這是它與
# `_RESULT_COLS` 唯一的差異來源。
_RESULT_FACT_COLS = ("resolved_params, requested_strategies, "
                     "engine_version, view_schema_version, "
                     "history_replay_version, snapshot_source")

# `_row_to_result()` 用來對 `requested_strategies` 做 list→tuple 轉換
# 的欄位位置——算一次存起來，不必每讀一列就重新 `.split(", ").index(...)`
# 一次（`result_history()` 對長歷史的劇本會呼叫這條路徑很多次）。
_REQUESTED_STRATEGIES_IDX = _RESULT_COLS.split(", ").index(
    "requested_strategies")

_SCENARIO_COLS = ("id, symbol, direction, target_price, target_month, "
                  "notes, strategies, created_at, archived_at, "
                  "best_price, worst_price, owner_id")

# PERF-02（#178）：`append_diagnostic()`／`append_diagnostics()` 共用
# 同一份欄位清單與 trim-on-write 查詢——單筆／批次寫入本來就該是同一套
# SQL 的兩種呼叫方式，不是各自維護一份容易漂移的複本。trim 只留全域
# 最新 RETENTION_LIMIT 筆：子查詢在不到上限時回空，`seq <= NULL`
# 恆假，DELETE 是安全的 no-op。
_DIAGNOSTICS_INSERT_COLS = ("(event_id, correlation_id, ts, subsystem, "
                           "stage, severity, user_facing, message, context, "
                           "owner_id)")
_DIAGNOSTICS_TRIM_SQL = (
    "DELETE FROM diagnostics WHERE seq <= ("
    "SELECT seq FROM diagnostics ORDER BY seq DESC OFFSET %s LIMIT 1)")


def _usage_to_dict(u: UsageSetting) -> dict:
    return {"mode": u.mode, "provider": u.provider}


def _usage_from_dict(d: dict | None) -> UsageSetting:
    """讀回時對缺漏寬容：舊的那一筆設定可能還沒有新加的資料用途，
    當成「預設」而不是炸掉——預設是安全的那一邊（不啟用自訂資料源）。"""
    if not d:
        return UsageSetting(mode="default", provider=None)
    return UsageSetting(mode=d.get("mode", "default"), provider=d.get("provider"))


def _row_to_scenario(row) -> Scenario:
    return Scenario(id=row[0], symbol=row[1], direction=row[2],
                    target_price=row[3], target_month=row[4], notes=row[5],
                    strategies=tuple(row[6]), created_at=row[7],
                    archived_at=row[8],
                    best_price=row[9], worst_price=row[10],
                    owner_id=row[11])


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        """T02（#186）：建構本身不再連線／不再確保 schema——那個代價
        現在掛在第一次真正呼叫 `_connect()` 上（見下），才能跟該次
        request 自己要用的共用連線一起分攤，而不是在 middleware 為了
        判斷「這個 adapter 有沒有 `request_scope`」而呼叫 `_db()` 時，
        於 scope 都還沒進入前就先付掉。"""
        self._dsn = dsn

    @property
    def kind(self) -> str:
        return "postgres"

    def _raw_connect(self):
        """實際借用／開連線的邏輯，不含 schema 就緒檢查——供 `_connect()`
        （已確保 schema 就緒後）與 `_ensure_schema()` 自己（就緒檢查
        本身要用連線）共用，避免兩者互相呼叫造成無窮遞迴。"""
        state = _request_scope_state.get()
        if state is None or state.dsn != self._dsn or state.failed:
            return psycopg.connect(self._dsn, autocommit=True)
        if state.conn is None:
            try:
                state.conn = psycopg.connect(self._dsn, autocommit=True)
            except Exception:  # noqa: BLE001 — 這次共用開不成，這次呼叫退回逐次開連線
                state.failed = True
                return psycopg.connect(self._dsn, autocommit=True)
        return _BorrowedConnection(state.conn)

    def _connect(self):
        """T02（#186）：連線改成**惰性**——scope 內第一次真正呼叫
        `_connect()` 時才開、開好後存回 scope 狀態物件供同一 scope
        內其餘呼叫重用；完全不碰 storage 的 request 因此零連線。

        沒有進到 `request_scope()`（測試直接呼叫 adapter method）或
        scope 內先前已經開失敗過（`state.failed`）時，退回今天
        「開一條、`with` 結束就關」的既有行為。

        第一次呼叫時順便確保 schema 就緒（`_ensure_schema()` 內部走
        `_raw_connect()`，不會回頭呼叫這裡造成遞迴）——這樣冷啟動後
        第一個真正碰 storage 的 request，schema 的兩次連線也能跟這次
        request 本身要用的共用連線一起分攤，而不是額外多付兩條。
        """
        if self._dsn not in _schema_ready:
            self._ensure_schema()
        return self._raw_connect()

    @contextmanager
    def request_scope(self):
        """PERF-01（#177）／T02（#186）修形：一次 HTTP request 期間，
        這個實例的全部 `Storage` method 呼叫共用同一條連線——由
        `main.py` 的 middleware 在每個 request 最外層呼叫。

        **惰性**：進入時只註冊一個空的 scope 狀態，不主動開連線；第一次
        真正呼叫到 `_connect()` 時才開（見上）。完全不碰 storage 的
        request（例如健康檢查）因此零連線握手，這是 T02 相對 PERF-01
        （進入就無條件開一條）的主要修正。

        scope 結束時（無論成功或例外）都在 `finally` 關閉「如果有開過」
        的那條連線並清空 ContextVar。開連線本身失敗時不讓那次呼叫跟著
        炸掉——退回逐次開連線的既有行為，且該次失敗後這個 scope 剩餘的
        呼叫不再嘗試共用（`state.failed`），避免對著暫時連不上的資料庫
        重複重試。

        `autocommit=True` 連著這條共用連線走，共用之後每個敘述依然
        各自 autocommit——沒有因為共用連線而引入橫跨多個敘述的隱含
        交易。
        """
        state = _ScopeState(self._dsn)
        token = _request_scope_state.set(state)
        try:
            yield
        finally:
            _request_scope_state.reset(token)
            if state.conn is not None:
                try:
                    state.conn.close()
                except Exception:  # noqa: BLE001 — 關閉失敗不影響這次 request 已經跑完的結果
                    pass

    def _ensure_schema(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` 冪等——單人專案不值得為此扛一整套
        migration 工具鏈；schema 有實質變動時再引入。

        每個程序只跑一次（省下每次冷啟動的一趟 DDL 往返）；多個冷啟動
        同時建表時 Postgres 可能拋 duplicate-object，那代表別人已經建好
        了，視為良性。

        建表與遷移**各送一次**：同批送的話，建表撞上冷啟動競爭會讓遷移
        跟著 rollback（見 `_MIGRATIONS` 的說明）。ready 只在兩批都不是
        致命錯誤時才標記——標了卻沒真的建好，後面每次寫入都會炸。

        T02（#186）：走 `_raw_connect()` 而非 `_connect()`——`_connect()`
        本身在就緒檢查沒過時會回頭呼叫這裡，兩者互相呼叫會無窮遞迴；
        `_raw_connect()` 不含就緒檢查，且一樣享有 scope 內的惰性連線
        共用（如果已經在 scope 內、且這是第一次真正用到連線，這兩次
        `_raw_connect()` 呼叫會開同一條、供這次 request 剩餘操作繼續
        重用）。"""
        if self._dsn in _schema_ready:
            return
        for stmt in (_SCHEMA, _MIGRATIONS):
            try:
                with self._raw_connect() as conn:
                    conn.execute(stmt)
            except _BENIGN:
                pass
        _schema_ready.add(self._dsn)

    # ---------- 劇本 ----------

    def create_scenario(self, sc: Scenario) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    f"INSERT INTO scenarios ({_SCENARIO_COLS}) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sc.id, sc.symbol, sc.direction, sc.target_price,
                     sc.target_month, sc.notes, Jsonb(list(sc.strategies)),
                     sc.created_at, sc.archived_at,
                     sc.best_price, sc.worst_price, sc.owner_id))
            except psycopg.errors.UniqueViolation as e:
                raise ScenarioExists(sc.id) from e

    def get_scenario(self, scenario_id: str) -> Scenario | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_SCENARIO_COLS} FROM scenarios WHERE id = %s",
                (scenario_id,)).fetchone()
        return _row_to_scenario(row) if row else None

    def list_scenarios(self, *, include_archived: bool = False) -> list[Scenario]:
        sql = f"SELECT {_SCENARIO_COLS} FROM scenarios"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY created_at, id"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [_row_to_scenario(r) for r in rows]

    def update_scenario(self, sc: Scenario) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE scenarios SET symbol = %s, direction = %s, "
                "target_price = %s, target_month = %s, notes = %s, "
                "strategies = %s, best_price = %s, worst_price = %s "
                "WHERE id = %s",
                (sc.symbol, sc.direction, sc.target_price, sc.target_month,
                 sc.notes, Jsonb(list(sc.strategies)), sc.best_price,
                 sc.worst_price, sc.id))
            return cur.rowcount == 1   # 連線關閉前讀

    def clear_results(self, scenario_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM results WHERE scenario_id = %s",
                        (scenario_id,))
            conn.execute("DELETE FROM snapshots WHERE scenario_id = %s",
                        (scenario_id,))

    def archive_scenario(self, scenario_id: str, *, ts: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE scenarios SET archived_at = %s "
                "WHERE id = %s AND archived_at IS NULL", (ts, scenario_id))
            return cur.rowcount == 1   # 連線關閉前讀

    def restore_scenario(self, scenario_id: str, *, ts: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE scenarios SET archived_at = NULL "
                "WHERE id = %s AND archived_at IS NOT NULL", (scenario_id,))
            return cur.rowcount == 1   # 連線關閉前讀

    def delete_scenario(self, scenario_id: str) -> bool:
        # 安全閘門在 DELETE FROM scenarios 那一行的 WHERE 子句本身檢查
        # （id 存在＋已封存）：rowcount==1 才代表真的刪了，這時才進一步
        # cascade 清 results／snapshots／events——避免對一個其實沒被
        # 刪除的劇本（未封存或不存在）誤刪其他表的資料。三張表各自一次
        # DELETE（不依賴 FK `ON DELETE CASCADE`，沿用專案既有「不用 FK
        # 約束，應用層自己保證一致性」的設計慣例）。
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM scenarios WHERE id = %s AND archived_at IS NOT NULL",
                (scenario_id,))
            if cur.rowcount != 1:
                return False
            conn.execute("DELETE FROM results WHERE scenario_id = %s",
                        (scenario_id,))
            conn.execute("DELETE FROM snapshots WHERE scenario_id = %s",
                        (scenario_id,))
            conn.execute("DELETE FROM events WHERE scenario_id = %s",
                        (scenario_id,))
            return True

    # ---------- 結果 ----------

    def save_result(self, rec: ResultRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO results (scenario_id, analyzed_at, view, "
                "best_return, representative_candidate, spot, per_family, "
                "family_eligibility, resolved_params, requested_strategies, "
                "engine_version, view_schema_version, history_replay_version, "
                "snapshot_source, owner_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (scenario_id, analyzed_at) DO UPDATE "
                "SET view = EXCLUDED.view, best_return = EXCLUDED.best_return, "
                "representative_candidate = EXCLUDED.representative_candidate, "
                "spot = EXCLUDED.spot, per_family = EXCLUDED.per_family, "
                "family_eligibility = EXCLUDED.family_eligibility, "
                "resolved_params = EXCLUDED.resolved_params, "
                "requested_strategies = EXCLUDED.requested_strategies, "
                "engine_version = EXCLUDED.engine_version, "
                "view_schema_version = EXCLUDED.view_schema_version, "
                "history_replay_version = EXCLUDED.history_replay_version, "
                "snapshot_source = EXCLUDED.snapshot_source, "
                "owner_id = EXCLUDED.owner_id",
                (rec.scenario_id, rec.analyzed_at, Jsonb(rec.view),
                 rec.best_return,
                 Jsonb(rec.representative_candidate)
                 if rec.representative_candidate is not None else None,
                 rec.spot,
                 Jsonb(rec.per_family) if rec.per_family is not None else None,
                 Jsonb(rec.family_eligibility)
                 if rec.family_eligibility is not None else None,
                 Jsonb(rec.resolved_params)
                 if rec.resolved_params is not None else None,
                 Jsonb(list(rec.requested_strategies))
                 if rec.requested_strategies is not None else None,
                 rec.engine_version, rec.view_schema_version,
                 rec.history_replay_version, rec.snapshot_source,
                 rec.owner_id))

    @staticmethod
    def _row_to_result(row) -> ResultRecord:
        """SCALE-01（#252）：`requested_strategies` 從 JSONB 讀回是
        `list`——`ResultRecord(*row)` 直接 splat 不會做任何型別轉換，
        這裡補上 list→tuple（比照既有 `_row_to_scenario()` 對
        `strategies` 的處理），`None`（尚未 backfill 的舊列）原樣穿透。
        其餘欄位（dict／str／int／`None`）JSONB／純量本來就對應正確
        的 Python 型別，不需轉換。"""
        row = list(row)
        if row[_REQUESTED_STRATEGIES_IDX] is not None:
            row[_REQUESTED_STRATEGIES_IDX] = tuple(row[_REQUESTED_STRATEGIES_IDX])
        return ResultRecord(*row)

    def latest_result(self, scenario_id: str) -> ResultRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_RESULT_COLS} FROM results "
                "WHERE scenario_id = %s ORDER BY analyzed_at DESC LIMIT 1",
                (scenario_id,)).fetchone()
        return self._row_to_result(row) if row else None

    def latest_summaries(self) -> dict[str, ResultSummary]:
        """`DISTINCT ON` 一趟取回每個劇本的最新一筆——**不選 view 欄位**，
        清單頁因此不會把每份十萬字元的 view 從資料庫搬過來。
        `representative_candidate` 是小型 JSONB（幾個履約價與策略代號），
        跟 `best_return` 同樣可以安全地隨這條清單查詢一起選（MVP-v2／
        #77、#78）——這正是它獨立落盤成一個欄位、而不是每次從 view
        現算的理由。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (scenario_id) scenario_id, analyzed_at, "
                "best_return, representative_candidate, spot, per_family, "
                "family_eligibility "
                "FROM results ORDER BY scenario_id, analyzed_at DESC").fetchall()
        return {r[0]: ResultSummary(analyzed_at=r[1], best_return=r[2],
                                    representative_candidate=r[3], spot=r[4],
                                    per_family=r[5], family_eligibility=r[6])
                for r in rows}

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_RESULT_COLS} FROM results "
                "WHERE scenario_id = %s ORDER BY analyzed_at",
                (scenario_id,)).fetchall()
        return [self._row_to_result(r) for r in rows]

    def result_timestamps(self, scenario_id: str) -> list[str]:
        # SCALE-02（#253）：兩段皆窄查詢——`snapshots` 用它自己的主鍵，
        # `results` 這半只選 `analyzed_at`，完全不觸碰 `view` JSONB
        # 欄位。UNION（非 UNION ALL）本身就會去重與排序前的集合運算，
        # 外層 ORDER BY 只負責排序，不需要另外 DISTINCT。
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT analyzed_at FROM ("
                "  SELECT analyzed_at FROM snapshots WHERE scenario_id = %s"
                "  UNION"
                "  SELECT analyzed_at FROM results WHERE scenario_id = %s"
                ") AS ts ORDER BY analyzed_at",
                (scenario_id, scenario_id)).fetchall()
        return [r[0] for r in rows]

    def result_fact_context(self, scenario_id: str,
                            analyzed_at: str) -> ResultFactContext | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_RESULT_FACT_COLS} FROM results "
                "WHERE scenario_id = %s AND analyzed_at = %s",
                (scenario_id, analyzed_at)).fetchone()
        if row is None:
            return None
        (resolved_params, requested_strategies, engine_version,
         view_schema_version, history_replay_version, snapshot_source) = row
        return ResultFactContext(
            scenario_id=scenario_id, analyzed_at=analyzed_at,
            resolved_params=resolved_params,
            requested_strategies=(tuple(requested_strategies)
                                  if requested_strategies is not None else None),
            engine_version=engine_version,
            view_schema_version=view_schema_version,
            history_replay_version=history_replay_version,
            snapshot_source=snapshot_source)

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict, *, owner_id: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (scenario_id, analyzed_at, snapshot, "
                "owner_id) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (scenario_id, analyzed_at) DO UPDATE "
                "SET snapshot = EXCLUDED.snapshot, "
                "owner_id = EXCLUDED.owner_id",
                (scenario_id, analyzed_at, Jsonb(snapshot), owner_id))

    def get_snapshot(self, scenario_id: str, analyzed_at: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot FROM snapshots "
                "WHERE scenario_id = %s AND analyzed_at = %s",
                (scenario_id, analyzed_at)).fetchone()
        return row[0] if row else None

    def get_snapshot_owner(self, scenario_id: str,
                           analyzed_at: str) -> str | None:
        """SCALE-06（#256）：窄讀取，只選 `owner_id`——不撈 `snapshot`
        JSONB（數百 KB 等級）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT owner_id FROM snapshots "
                "WHERE scenario_id = %s AND analyzed_at = %s",
                (scenario_id, analyzed_at)).fetchone()
        return row[0] if row else None

    # ---------- 事件 ----------

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict,
                     owner_id: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, scenario_id, event, payload, "
                "owner_id) VALUES (%s, %s, %s, %s, %s)",
                (ts, scenario_id, event, Jsonb(payload), owner_id))

    def list_events(self, *, scenario_id: str | None = None) -> list[dict]:
        sql = "SELECT ts, scenario_id, event, payload, owner_id FROM events"
        params: tuple = ()
        if scenario_id is not None:
            sql += " WHERE scenario_id = %s"
            params = (scenario_id,)
        sql += " ORDER BY seq"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{"ts": r[0], "scenario_id": r[1], "event": r[2],
                 "payload": r[3], "owner_id": r[4]} for r in rows]

    # ---------- 利率曲線快取 ----------

    def get_rate_cache(self) -> RateCacheEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT fetched_at, curve, note, last_success_at, market_day, "
                "attempted_day FROM rate_cache WHERE id = 1").fetchone()
        return (RateCacheEntry(fetched_at=row[0], curve=row[1], note=row[2],
                               last_success_at=row[3], market_day=row[4],
                               attempted_day=row[5])
                if row else None)

    def save_rate_cache(self, entry: RateCacheEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO rate_cache "
                "(id, fetched_at, curve, note, last_success_at, market_day, "
                "attempted_day) "
                "VALUES (1, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE "
                "SET fetched_at = EXCLUDED.fetched_at, curve = EXCLUDED.curve, "
                "note = EXCLUDED.note, last_success_at = EXCLUDED.last_success_at, "
                "market_day = EXCLUDED.market_day, "
                "attempted_day = EXCLUDED.attempted_day",
                (entry.fetched_at, Jsonb(entry.curve) if entry.curve is not None else None,
                 entry.note, entry.last_success_at, entry.market_day,
                 entry.attempted_day))

    # ---------- 配息資料快取（#123，per-symbol） ----------

    def get_dividend_cache(self, symbol: str) -> DividendCacheEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT symbol, fetched_at, history, note, last_success_at, "
                "market_day, attempted_day FROM dividend_cache "
                "WHERE symbol = %s", (symbol,)).fetchone()
        return (DividendCacheEntry(symbol=row[0], fetched_at=row[1], history=row[2],
                                   note=row[3], last_success_at=row[4],
                                   market_day=row[5], attempted_day=row[6])
                if row else None)

    def save_dividend_cache(self, entry: DividendCacheEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO dividend_cache "
                "(symbol, fetched_at, history, note, last_success_at, market_day, "
                "attempted_day) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (symbol) DO UPDATE "
                "SET fetched_at = EXCLUDED.fetched_at, history = EXCLUDED.history, "
                "note = EXCLUDED.note, last_success_at = EXCLUDED.last_success_at, "
                "market_day = EXCLUDED.market_day, "
                "attempted_day = EXCLUDED.attempted_day",
                (entry.symbol, entry.fetched_at,
                 Jsonb(entry.history) if entry.history is not None else None,
                 entry.note, entry.last_success_at, entry.market_day,
                 entry.attempted_day))

    # ---------- Treasury 曲線列快取（PERF-03／#179，per-year） ----------

    def get_treasury_year_cache(self, year: int) -> TreasuryYearCacheEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT year, fetched_at, rows, note, last_success_at, "
                "market_day, attempted_day FROM treasury_year_cache "
                "WHERE year = %s", (year,)).fetchone()
        return (TreasuryYearCacheEntry(year=row[0], fetched_at=row[1], rows=row[2],
                                       note=row[3], last_success_at=row[4],
                                       market_day=row[5], attempted_day=row[6])
                if row else None)

    def save_treasury_year_cache(self, entry: TreasuryYearCacheEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO treasury_year_cache "
                "(year, fetched_at, rows, note, last_success_at, market_day, "
                "attempted_day) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (year) DO UPDATE "
                "SET fetched_at = EXCLUDED.fetched_at, rows = EXCLUDED.rows, "
                "note = EXCLUDED.note, last_success_at = EXCLUDED.last_success_at, "
                "market_day = EXCLUDED.market_day, "
                "attempted_day = EXCLUDED.attempted_day",
                (entry.year, entry.fetched_at,
                 Jsonb(entry.rows) if entry.rows is not None else None,
                 entry.note, entry.last_success_at, entry.market_day,
                 entry.attempted_day))

    # ---------- Chain 429 backoff（SCALE-04／#255，provider-global） ----------

    def get_chain_backoff(self, source: str) -> ChainBackoffEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT source, blocked_until, retry_after_seconds, "
                "consecutive_failures, observed_at, last_success_at "
                "FROM chain_backoff WHERE source = %s", (source,)).fetchone()
        return (ChainBackoffEntry(source=row[0], blocked_until=row[1],
                                  retry_after_seconds=row[2],
                                  consecutive_failures=row[3], observed_at=row[4],
                                  last_success_at=row[5])
                if row else None)

    def save_chain_backoff(self, entry: ChainBackoffEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chain_backoff "
                "(source, blocked_until, retry_after_seconds, "
                "consecutive_failures, observed_at, last_success_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (source) DO UPDATE "
                "SET blocked_until = EXCLUDED.blocked_until, "
                "retry_after_seconds = EXCLUDED.retry_after_seconds, "
                "consecutive_failures = EXCLUDED.consecutive_failures, "
                "observed_at = EXCLUDED.observed_at, "
                "last_success_at = EXCLUDED.last_success_at",
                (entry.source, entry.blocked_until, entry.retry_after_seconds,
                 entry.consecutive_failures, entry.observed_at,
                 entry.last_success_at))

    # ---------- 資料源設定與 credential（Settings／#124） ----------

    def get_settings(self) -> DataSourceSettings | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT settings, updated_at FROM data_source_settings "
                "WHERE id = 1").fetchone()
        if not row:
            return None
        blob = row[0]
        return DataSourceSettings(
            market_data=_usage_from_dict(blob.get("market_data")),
            historical_iv=_usage_from_dict(blob.get("historical_iv")),
            updated_at=row[1])

    def save_settings(self, settings: DataSourceSettings) -> None:
        blob = {"market_data": _usage_to_dict(settings.market_data),
                "historical_iv": _usage_to_dict(settings.historical_iv)}
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO data_source_settings (id, settings, updated_at) "
                "VALUES (1, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET settings = EXCLUDED.settings, "
                "updated_at = EXCLUDED.updated_at",
                (Jsonb(blob), settings.updated_at))

    def get_credential(self, provider: str) -> ProviderCredential | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT provider, token, updated_at FROM provider_credentials "
                "WHERE provider = %s", (provider,)).fetchone()
        return ProviderCredential(*row) if row else None

    def save_credential(self, cred: ProviderCredential) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO provider_credentials (provider, token, updated_at) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (provider) DO UPDATE SET token = EXCLUDED.token, "
                "updated_at = EXCLUDED.updated_at",
                (cred.provider, cred.token, cred.updated_at))

    def delete_credential(self, provider: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM provider_credentials WHERE provider = %s",
                (provider,))
            removed = cur.rowcount == 1   # 連線關閉前讀
            # 驗證結果跟著走：它講的是「那把 token 能不能用」。無論剛才
            # 有沒有刪到 credential 都清——沒有 credential 卻留著一筆
            # 「已連線」是更糟的狀態。
            conn.execute(
                "DELETE FROM provider_verifications WHERE provider = %s",
                (provider,))
            return removed

    def get_verification(self, provider: str) -> ProviderVerification | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT provider, ok, reason, checked_at FROM "
                "provider_verifications WHERE provider = %s",
                (provider,)).fetchone()
        return ProviderVerification(*row) if row else None

    def save_verification(self, v: ProviderVerification) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO provider_verifications "
                "(provider, ok, reason, checked_at) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (provider) DO UPDATE SET ok = EXCLUDED.ok, "
                "reason = EXCLUDED.reason, checked_at = EXCLUDED.checked_at",
                (v.provider, v.ok, v.reason, v.checked_at))

    # ---------- 歷史 IV 觀測快取（#129，per-symbol） ----------

    def save_iv_observation(self, obs: IvObservation) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO iv_observations "
                "(symbol, observed_on, surface, fetched_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (symbol, observed_on) DO UPDATE "
                "SET surface = EXCLUDED.surface, "
                "fetched_at = EXCLUDED.fetched_at",
                (obs.symbol, obs.observed_on, Jsonb(obs.surface), obs.fetched_at))

    def iv_observation_dates(self, symbol: str) -> list[str]:
        """只選日期欄——backfill 要的是缺口，不是幾十天份的曲面。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT observed_on FROM iv_observations WHERE symbol = %s "
                "ORDER BY observed_on", (symbol,)).fetchall()
        return [r[0] for r in rows]

    def iv_observations(self, symbol: str) -> list[IvObservation]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT symbol, observed_on, surface, fetched_at "
                "FROM iv_observations WHERE symbol = %s ORDER BY observed_on",
                (symbol,)).fetchall()
        return [IvObservation(*r) for r in rows]

    def get_iv_backfill_run(self, symbol: str) -> IvBackfillRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT symbol, ran_on, outcome, note FROM iv_backfill_runs "
                "WHERE symbol = %s", (symbol,)).fetchone()
        return IvBackfillRun(*row) if row else None

    def save_iv_backfill_run(self, run: IvBackfillRun) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO iv_backfill_runs (symbol, ran_on, outcome, note) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (symbol) DO UPDATE SET ran_on = EXCLUDED.ran_on, "
                "outcome = EXCLUDED.outcome, note = EXCLUDED.note",
                (run.symbol, run.ran_on, run.outcome, run.note))

    # ---------- Exact-contract 歷史 IV 快取（HIVT-02／#153） ----------

    def get_contract_history(self, contract_symbol: str) -> ContractHistory | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT contract_symbol, points, fetched_through, "
                "last_attempt_on, last_status, last_note "
                "FROM contract_iv_history WHERE contract_symbol = %s",
                (contract_symbol,)).fetchone()
        if row is None:
            return None
        # HIVR-04（#163）：`points` 現在是逐日 quote dict 的 JSONB 陣列
        # （不是舊版 `[date, iv]` 二元組陣列）——psycopg 把 JSON object
        # 讀回 Python dict，這裡原樣傳遞，不重新拆解成固定欄位。舊格式
        # 列（元素是 list 而非 dict）的辨識與「當 cache miss 重抓」由
        # 呼叫端（`api_app/main.py`）負責，storage 層不解讀形狀。
        points = tuple(row[1])
        return ContractHistory(contract_symbol=row[0], points=points,
                               fetched_through=row[2], last_attempt_on=row[3],
                               last_status=row[4], last_note=row[5])

    def save_contract_history(self, history: ContractHistory) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO contract_iv_history (contract_symbol, points, "
                "fetched_through, last_attempt_on, last_status, last_note) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (contract_symbol) DO UPDATE "
                "SET points = EXCLUDED.points, "
                "fetched_through = EXCLUDED.fetched_through, "
                "last_attempt_on = EXCLUDED.last_attempt_on, "
                "last_status = EXCLUDED.last_status, "
                "last_note = EXCLUDED.last_note",
                (history.contract_symbol, Jsonb(list(history.points)),
                 history.fetched_through, history.last_attempt_on,
                 history.last_status, history.last_note))

    # ---------- Application diagnostics（DG-02／#145） ----------

    def append_diagnostic(self, event: DiagnosticEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO diagnostics {_DIAGNOSTICS_INSERT_COLS} "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (event.event_id, event.correlation_id, event.ts,
                 event.subsystem, event.stage, event.severity,
                 event.user_facing, event.message,
                 Jsonb(event.context), event.owner_id))
            conn.execute(_DIAGNOSTICS_TRIM_SQL, (RETENTION_LIMIT,))

    def append_diagnostics(self, events: list[DiagnosticEvent]) -> None:
        """批次版（PERF-02／#178）：一次多列 INSERT，不是逐筆迴圈呼叫
        `append_diagnostic()`——政策（哪些 event 值得進資料庫）掛在
        `main.py` 呼叫端，這裡只負責把給定的清單一次寫完。trim-on-write
        插入後只跑一次，跟逐筆寫入「每筆各自跑一次」比較，兩者都是
        「只留全域最新 RETENTION_LIMIT 筆」，最終保留集合完全一致。"""
        if not events:
            return
        values_sql = ", ".join(
            ["(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"] * len(events))
        params: list = []
        for event in events:
            params.extend([event.event_id, event.correlation_id, event.ts,
                          event.subsystem, event.stage, event.severity,
                          event.user_facing, event.message,
                          Jsonb(event.context), event.owner_id])
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO diagnostics {_DIAGNOSTICS_INSERT_COLS} "
                f"VALUES {values_sql}", params)
            conn.execute(_DIAGNOSTICS_TRIM_SQL, (RETENTION_LIMIT,))

    def list_diagnostics(self, *, limit: int = 50) -> list[DiagnosticEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, correlation_id, ts, subsystem, stage, "
                "severity, user_facing, message, context, owner_id "
                "FROM diagnostics ORDER BY seq DESC LIMIT %s",
                (limit,)).fetchall()
        # `user_facing`（r[6]）為 NULL 只會發生在遷移前寫入的舊列——套用
        # 跟 `diagnostics.emit()` 完全相同的預設規則補值，讀回的行為因此
        # 對新舊列一致，不會讓查詢端還要另外處理 NULL。`owner_id`（r[9]）
        # 為 NULL 則原樣穿透——不像 `user_facing` 有個明確的推導規則，
        # `None` 本身就是這個欄位合法、穩定的值（見 `DiagnosticEvent`
        # 欄位註解）。
        return [DiagnosticEvent(
            event_id=r[0], correlation_id=r[1], ts=r[2], subsystem=r[3],
            stage=r[4], severity=r[5],
            user_facing=r[6] if r[6] is not None else r[5] in ("warning", "error"),
            message=r[7], context=r[8], owner_id=r[9]) for r in rows]

    def clear_diagnostics(self) -> int:
        with self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
            conn.execute("DELETE FROM diagnostics")
        return n

    # ---------- Ownership A-1 Expand（SCALE-06／#256） ----------

    def backfill_missing_owner_ids(self, owner_id: str) -> dict[str, int]:
        """5 張 row-scoped 表各自一條 `UPDATE ... WHERE owner_id IS
        NULL`——條件式 WHERE 讓重跑天然冪等（第二次呼叫全部回 0），
        `cur.rowcount` 直接就是「這次真的補了幾筆」，不需要另外
        SELECT COUNT 再 UPDATE 兩趟。"""
        tables = ("scenarios", "results", "snapshots", "events", "diagnostics")
        counts: dict[str, int] = {}
        with self._connect() as conn:
            for table in tables:
                cur = conn.execute(
                    f"UPDATE {table} SET owner_id = %s "
                    "WHERE owner_id IS NULL", (owner_id,))
                counts[table] = cur.rowcount
        return counts
