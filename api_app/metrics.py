"""S0 最小可觀測性（SCALE-08／#258，Scaling Foundation）。

**只有這七類，封頂**——AC-2 要求一條結構性測試鎖住這個清單「恰好七類」，
新增第八類必須明確改這裡（`tests/test_scale08_observability.py` 會紅）。
七類分兩種形狀：

- **持久化計數／量級**（`record()` 寫進獨立、極小的 `operational_metrics`
  表，`Storage.record_metric()`／`metric_summary()`）：
  `chain_fetch_count`、`chain_429_count`、`stale_serve_count`、
  `cold_miss_count`、`refresh_duration_ms`、`history_read_volume`。
- **query-time gauge**（不持久化，`Storage.table_size_metrics()` 即時
  查詢 `results`／`snapshots` 兩表大小、列數、單列大小分布）：`table_size`。

**這不是既有 `diagnostics` 系統的擴充，是刻意獨立的第二套**：
`diagnostics` 是 owner-scoped（SCALE-06 起）＋trim-on-write 只留最新
200 筆的**事件流**（服務「這一次 request 發生了什麼」）；這裡是
system-wide（不分 owner）＋day-bucket 聚合的**運維計數**（服務
「這七天／這個月，系統整體發生了多少次什麼」）。硬塞進 diagnostics
會讓兩種語意（owner-scoped vs system-wide、200-事件上限 vs 天級聚合）
互相污染，因此獨立成這個模組與獨立的資料表。

**只存允許的維度**：`source`（哪個上游，例如 `cboe`／`yfinance`／
`treasury`／`dividend`）與 `symbol`（哪個標的，只在真的按標的分的
指標上有意義）。**不存 `scenario_id`、`owner_id`、任何報價／合約／
chain payload**——見 `tests/test_scale08_observability.py` 的結構性
守門。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

METRIC_CATALOGUE = (
    "chain_fetch_count",
    "chain_429_count",
    "stale_serve_count",
    "cold_miss_count",
    "refresh_duration_ms",
    "table_size",
    "history_read_volume",
)

# `table_size` 是 query-time gauge，不經過 `record()`／`operational_
# metrics` 表——這裡單獨列出供 AC-1 的 operator 端點知道要用不同的
# 呼叫路徑組出它的答案。
PERSISTED_METRICS = tuple(m for m in METRIC_CATALOGUE if m != "table_size")

# 足以回答「昨天」與 rollout 前後比較即可（票面原話）；不是無限成長的
# 時序資料庫。每次 `record_metric()` 寫入時，兩個後端各自負責把同一個
# `metric` 底下比這個窗口更舊的桶清掉——見 `memory.py`／`postgres.py`
# 各自的實作，門檻定義只在這裡有一份。
RETENTION_DAYS = 30


class _MetricsStorage(Protocol):
    def record_metric(self, metric: str, bucket: str, *, source: str = "",
                      symbol: str = "", count: int = 0,
                      amount: float = 0.0) -> None: ...


def record(storage: _MetricsStorage, metric: str, today: date, *,
          source: str = "", symbol: str = "", count: int = 1,
          amount: float = 0.0) -> None:
    """唯一的記錄入口——與 `diagnostics.emit()` 同一個哲學：**觀測本身
    絕不能成為新的故障源**，整個包在 try/except 裡，storage 寫入失敗
    吞掉、不影響呼叫端的主流程（AC-5）。

    `metric` 必須是 `METRIC_CATALOGUE` 的成員——這裡用 `assert` 而非
    靜默略過：寫錯 metric 名稱是我們自己程式碼的 bug，應該在開發／
    測試階段就炸出來，不是被這層觀測本身的 fail-open 哲學悄悄蓋掉
    （fail-open 保護的是「storage 這一步本身失敗」，不是「呼叫端傳錯
    參數」）。"""
    assert metric in PERSISTED_METRICS, f"未知的 metric：{metric}"
    try:
        storage.record_metric(metric, today.isoformat(), source=source,
                              symbol=symbol, count=count, amount=amount)
    except Exception:  # noqa: BLE001 — 觀測失敗不得拖垮被觀測的主流程
        pass


def retention_cutoff(today_bucket: str) -> str:
    """`today_bucket`（"YYYY-MM-DD"）往回推 `RETENTION_DAYS` 天——早於
    這個日期的桶，兩個後端的 `record_metric()` 各自負責清掉。單一處
    定義換算規則，不讓兩個後端各自重算一次可能漂移的日期算術。"""
    d = date.fromisoformat(today_bucket)
    return (d - timedelta(days=RETENTION_DAYS)).isoformat()
