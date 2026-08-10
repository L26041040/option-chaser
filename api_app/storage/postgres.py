"""Neon Postgres 儲存 adapter（V2／#50）。

serverless 前提：函式壽命極短，每次請求開新連線（Neon 的 pooler 端點
負責連線池化），不在程序內自行維護長連線。

大 JSON（結果 view dict，十萬字元等級）存 JSONB：psycopg 直接對應
Python dict，不需自己 `json.dumps`。時間欄位存 ISO 字串而非 timestamptz
——與引擎既有的 ISO 字串慣例一致，避免時區在邊界上被悄悄轉換。
"""
from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from . import (DividendCacheEntry, RateCacheEntry, ResultRecord, ResultSummary,
              Scenario, ScenarioExists)

# 每個 lambda 程序只需建表一次。`IF NOT EXISTS` 在 Postgres 並非完全
# race-free（同時冷啟動可能撞上 duplicate 錯誤），因此除了這個旗標，
# 下面也把重複建立視為良性。
_schema_ready: set[str] = set()

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
    PRIMARY KEY (scenario_id, analyzed_at)
);
-- V3（#51）／MVP-v2（#77、#78）加的欄位。既有部署已經有 results 表，
-- `CREATE TABLE IF NOT EXISTS` 不會補欄位——沒有這兩行，正式環境會在
-- INSERT 時炸 UndefinedColumn。
ALTER TABLE results ADD COLUMN IF NOT EXISTS best_return DOUBLE PRECISION;
ALTER TABLE results ADD COLUMN IF NOT EXISTS representative_candidate JSONB;
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
"""

# 遷移**必須與建表分開送**。psycopg 對「無參數、多語句」的 execute 走
# simple-query 協定，Postgres 會把整批包成一個 implicit transaction——
# 同時冷啟動撞上 DuplicateTable 時，整批（含這行 ALTER）會一起 rollback，
# 而下面仍會把 dsn 標成 ready，該 process 從此每次寫入都撞 UndefinedColumn。
_MIGRATIONS = """
ALTER TABLE results ADD COLUMN IF NOT EXISTS best_return DOUBLE PRECISION;
ALTER TABLE results ADD COLUMN IF NOT EXISTS representative_candidate JSONB;
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS best_price DOUBLE PRECISION;
ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS worst_price DOUBLE PRECISION;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS last_success_at TEXT;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS market_day TEXT;
ALTER TABLE rate_cache ADD COLUMN IF NOT EXISTS attempted_day TEXT;
"""

# 冷啟動競爭下的良性錯誤：別人已經建好／加好了。
_BENIGN = (psycopg.errors.DuplicateTable, psycopg.errors.DuplicateObject,
           psycopg.errors.DuplicateColumn, psycopg.errors.UniqueViolation)

_RESULT_COLS = "scenario_id, analyzed_at, view, best_return, representative_candidate"

_SCENARIO_COLS = ("id, symbol, direction, target_price, target_month, "
                  "notes, strategies, created_at, archived_at, "
                  "best_price, worst_price")


def _row_to_scenario(row) -> Scenario:
    return Scenario(id=row[0], symbol=row[1], direction=row[2],
                    target_price=row[3], target_month=row[4], notes=row[5],
                    strategies=tuple(row[6]), created_at=row[7],
                    archived_at=row[8],
                    best_price=row[9], worst_price=row[10])


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ensure_schema()

    @property
    def kind(self) -> str:
        return "postgres"

    def _connect(self):
        return psycopg.connect(self._dsn, autocommit=True)

    def _ensure_schema(self) -> None:
        """`CREATE TABLE IF NOT EXISTS` 冪等——單人專案不值得為此扛一整套
        migration 工具鏈；schema 有實質變動時再引入。

        每個程序只跑一次（省下每次冷啟動的一趟 DDL 往返）；多個冷啟動
        同時建表時 Postgres 可能拋 duplicate-object，那代表別人已經建好
        了，視為良性。

        建表與遷移**各送一次**：同批送的話，建表撞上冷啟動競爭會讓遷移
        跟著 rollback（見 `_MIGRATIONS` 的說明）。ready 只在兩批都不是
        致命錯誤時才標記——標了卻沒真的建好，後面每次寫入都會炸。"""
        if self._dsn in _schema_ready:
            return
        for stmt in (_SCHEMA, _MIGRATIONS):
            try:
                with self._connect() as conn:
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
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sc.id, sc.symbol, sc.direction, sc.target_price,
                     sc.target_month, sc.notes, Jsonb(list(sc.strategies)),
                     sc.created_at, sc.archived_at,
                     sc.best_price, sc.worst_price))
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
                "best_return, representative_candidate) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (scenario_id, analyzed_at) DO UPDATE "
                "SET view = EXCLUDED.view, best_return = EXCLUDED.best_return, "
                "representative_candidate = EXCLUDED.representative_candidate",
                (rec.scenario_id, rec.analyzed_at, Jsonb(rec.view),
                 rec.best_return,
                 Jsonb(rec.representative_candidate)
                 if rec.representative_candidate is not None else None))

    def latest_result(self, scenario_id: str) -> ResultRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_RESULT_COLS} FROM results "
                "WHERE scenario_id = %s ORDER BY analyzed_at DESC LIMIT 1",
                (scenario_id,)).fetchone()
        return ResultRecord(*row) if row else None

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
                "best_return, representative_candidate FROM results "
                "ORDER BY scenario_id, analyzed_at DESC").fetchall()
        return {r[0]: ResultSummary(analyzed_at=r[1], best_return=r[2],
                                    representative_candidate=r[3])
                for r in rows}

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_RESULT_COLS} FROM results "
                "WHERE scenario_id = %s ORDER BY analyzed_at",
                (scenario_id,)).fetchall()
        return [ResultRecord(*r) for r in rows]

    def save_snapshot(self, scenario_id: str, analyzed_at: str,
                      snapshot: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (scenario_id, analyzed_at, snapshot) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (scenario_id, analyzed_at) DO UPDATE "
                "SET snapshot = EXCLUDED.snapshot",
                (scenario_id, analyzed_at, Jsonb(snapshot)))

    def get_snapshot(self, scenario_id: str, analyzed_at: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT snapshot FROM snapshots "
                "WHERE scenario_id = %s AND analyzed_at = %s",
                (scenario_id, analyzed_at)).fetchone()
        return row[0] if row else None

    # ---------- 事件 ----------

    def append_event(self, *, ts: str, scenario_id: str | None,
                     event: str, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, scenario_id, event, payload) "
                "VALUES (%s, %s, %s, %s)",
                (ts, scenario_id, event, Jsonb(payload)))

    def list_events(self, *, scenario_id: str | None = None) -> list[dict]:
        sql = "SELECT ts, scenario_id, event, payload FROM events"
        params: tuple = ()
        if scenario_id is not None:
            sql += " WHERE scenario_id = %s"
            params = (scenario_id,)
        sql += " ORDER BY seq"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{"ts": r[0], "scenario_id": r[1], "event": r[2],
                 "payload": r[3]} for r in rows]

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
