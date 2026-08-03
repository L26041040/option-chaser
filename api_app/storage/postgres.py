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

from . import ResultRecord, Scenario, ScenarioExists

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
    archived_at   TEXT
);
CREATE TABLE IF NOT EXISTS results (
    scenario_id   TEXT NOT NULL,
    analyzed_at   TEXT NOT NULL,
    view          JSONB NOT NULL,
    PRIMARY KEY (scenario_id, analyzed_at)
);
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
"""

_SCENARIO_COLS = ("id, symbol, direction, target_price, target_month, "
                  "notes, strategies, created_at, archived_at")


def _row_to_scenario(row) -> Scenario:
    return Scenario(id=row[0], symbol=row[1], direction=row[2],
                    target_price=row[3], target_month=row[4], notes=row[5],
                    strategies=tuple(row[6]), created_at=row[7],
                    archived_at=row[8])


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
        了，視為良性。"""
        if self._dsn in _schema_ready:
            return
        try:
            with self._connect() as conn:
                conn.execute(_SCHEMA)
        except (psycopg.errors.DuplicateTable, psycopg.errors.DuplicateObject,
                psycopg.errors.UniqueViolation):
            pass
        _schema_ready.add(self._dsn)

    # ---------- 劇本 ----------

    def create_scenario(self, sc: Scenario) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    f"INSERT INTO scenarios ({_SCENARIO_COLS}) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (sc.id, sc.symbol, sc.direction, sc.target_price,
                     sc.target_month, sc.notes, Jsonb(list(sc.strategies)),
                     sc.created_at, sc.archived_at))
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

    # ---------- 結果 ----------

    def save_result(self, rec: ResultRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO results (scenario_id, analyzed_at, view) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (scenario_id, analyzed_at) DO UPDATE "
                "SET view = EXCLUDED.view",
                (rec.scenario_id, rec.analyzed_at, Jsonb(rec.view)))

    def latest_result(self, scenario_id: str) -> ResultRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT scenario_id, analyzed_at, view FROM results "
                "WHERE scenario_id = %s ORDER BY analyzed_at DESC LIMIT 1",
                (scenario_id,)).fetchone()
        return ResultRecord(*row) if row else None

    def result_history(self, scenario_id: str) -> list[ResultRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT scenario_id, analyzed_at, view FROM results "
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
