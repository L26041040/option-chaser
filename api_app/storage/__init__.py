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


@dataclass(frozen=True)
class ResultRecord:
    scenario_id: str
    analyzed_at: str          # ISO 8601（＝快照的 fetched_at）
    view: dict                # store.serialize_result 的完整 view dict
    # baseline 期最高收益率（`store.best_return(view)`）。存成獨立欄位而
    # 不是每次從 view 現算：劇本清單只要這一個數字，卻得為此把整份 view
    # 撈回來。規則仍只有一份（引擎的純函式），這裡只是它的落盤結果。
    best_return: float | None = None


@dataclass(frozen=True)
class ResultSummary:
    """劇本清單卡片要的兩個數字——不含 view。"""
    analyzed_at: str
    best_return: float | None


class Storage(Protocol):
    """API 層唯一的資料存取介面——不得繞過它直接碰 SQL 或檔案。"""

    def create_scenario(self, sc: Scenario) -> None:
        """id 已存在時拋 `ScenarioExists`。"""

    def get_scenario(self, scenario_id: str) -> Scenario | None: ...

    def list_scenarios(self, *, include_archived: bool = False) -> list[Scenario]:
        """依 created_at 遞增排序；預設不含已封存者。"""

    def archive_scenario(self, scenario_id: str, *, ts: str) -> bool:
        """回傳是否真的封存了（不存在或已封存回 False）。資料不刪除。"""

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

    @property
    def kind(self) -> str:
        """"memory" | "postgres"——供 /api/health 如實回報實際用的是哪個。"""


class ScenarioExists(Exception):
    pass
