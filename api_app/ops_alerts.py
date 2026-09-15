"""PB-11（#303，Anonymous Public Beta）：daily digest 的四條 alert
判準——純函式，不做任何 I/O（不接觸 `Storage`／`chain_backoff`／
`request` 等），呼叫端（`main.py`）負責把既有資料源（`chain_backoff.
status()`／`metric_summary()`／`table_size_metrics()`）查好再餵進來。
這個分工讓四條規則本身可以完全離線、決定性地測試，不需要真的建一份
資料庫狀態去間接逼出每一種組合。

**票面 §7 明訂的四條**：
1. Cboe（或其他已知來源）連續 429 達 `chain_backoff.
   INCIDENT_THRESHOLD_FAILURES` 既有門檻——直接重用該模組的
   `is_sustained_incident()` 判準，不重新發明一個新門檻。
2. 清理排程（PB-08）連續 N 天沒有留下任何執行紀錄——`main.py` 用
   `Storage.metric_summary()` 查 `abandoned_owner_cleanup_count`
   這個 metric **是否存在**某天的桶（不是看 `count` 數值，PB-08
   設計是「即使清了 0 個 owner 也留一筆 count=0 的紀錄」，因此
   「查無紀錄」才是「排程根本沒跑到」的訊號，「count=0」是「排程
   跑了、剛好沒東西可清」，兩者語意不同，不能混為一談）。
3. 儲存用量超過設定上限的告警比例（建議 80%，`STORAGE_ALERT_RATIO`）
   ——`results`＋`snapshots` 兩表 `total_bytes` 加總，對照一個可設定
   的容量上限（預設對齊研究 #276／#273 記載的 Neon Free 約 0.5 GB）。
4. Vendor 抓取錯誤率（`chain_429_count` / `chain_fetch_count`，近 7
   天窗口）超過門檻（`CHAIN_ERROR_RATE_THRESHOLD`）——這是本站唯一
   已經在持久化追蹤、且直接對應「使用者體感到失敗有多頻繁」的既有
   指標對，不新增第二套錯誤率統計機制（一般性的「backend error
   rate」目前只由 PB-13 的 Sentry 承接，本站沒有、也不打算重造一份
   本地版本——那會是與 Sentry 重複維護的兩套真相來源）。
"""
from __future__ import annotations

from dataclasses import dataclass

CLEANUP_MISSED_DAYS_THRESHOLD = 2
STORAGE_ALERT_RATIO = 0.8
# Neon Free 官方文件記載的儲存上限約 0.5 GiB（研究 #273／#276），
# 作為未另行設定 `STORAGE_ALERT_CAP_BYTES` 時的保守預設值。
DEFAULT_STORAGE_CAP_BYTES = 512 * 1024 * 1024
CHAIN_ERROR_RATE_THRESHOLD = 0.10


@dataclass(frozen=True)
class AlertCondition:
    """一條 alert 判準的結果——`key` 是穩定識別字（供測試斷言、未來
    若有多個呈現管道也能各自認得同一個判準），`message` 是可以直接
    放進 digest 內文的白話句子，不需要呼叫端再組一次文字。"""
    key: str
    triggered: bool
    message: str


def evaluate_alerts(
    *,
    sustained_incident_sources: tuple[str, ...],
    cleanup_missed_days: int,
    storage_bytes: int,
    chain_429_count: int,
    chain_fetch_count: int,
    cleanup_missed_days_threshold: int = CLEANUP_MISSED_DAYS_THRESHOLD,
    storage_cap_bytes: int = DEFAULT_STORAGE_CAP_BYTES,
    storage_alert_ratio: float = STORAGE_ALERT_RATIO,
    chain_error_rate_threshold: float = CHAIN_ERROR_RATE_THRESHOLD,
) -> tuple[AlertCondition, ...]:
    """四條判準各自獨立計算，任一條的輸入缺席（例如
    `chain_fetch_count == 0`）不影響其他三條——與既有 `chain_backoff.
    status()` 的 fail-open 哲學一致：觀測不到就不觸發，不讓可觀測性
    機制本身的空白變成假警報。"""
    alerts = []

    alerts.append(AlertCondition(
        key="chain_sustained_incident",
        triggered=bool(sustained_incident_sources),
        message=(f"持續性限流事故：{', '.join(sustained_incident_sources)}"
                 if sustained_incident_sources else "無持續性限流事故"),
    ))

    cleanup_triggered = cleanup_missed_days >= cleanup_missed_days_threshold
    alerts.append(AlertCondition(
        key="cleanup_missed",
        triggered=cleanup_triggered,
        message=(f"清理排程已連續 {cleanup_missed_days} 天沒有執行紀錄"
                 if cleanup_triggered else "清理排程近期執行正常"),
    ))

    storage_ratio = (storage_bytes / storage_cap_bytes) if storage_cap_bytes > 0 else 0.0
    storage_triggered = storage_ratio >= storage_alert_ratio
    alerts.append(AlertCondition(
        key="storage_usage",
        triggered=storage_triggered,
        message=(f"儲存用量已達上限的 {storage_ratio:.0%}"
                 f"（{storage_bytes:,} / {storage_cap_bytes:,} bytes）"),
    ))

    error_rate = ((chain_429_count / chain_fetch_count)
                 if chain_fetch_count > 0 else 0.0)
    error_triggered = error_rate >= chain_error_rate_threshold
    alerts.append(AlertCondition(
        key="chain_error_rate",
        triggered=error_triggered,
        message=(f"近 7 天 vendor 抓取 429 比例 {error_rate:.0%}"
                 f"（{chain_429_count} / {chain_fetch_count} 次）"),
    ))

    return tuple(alerts)


__all__ = [
    "AlertCondition", "evaluate_alerts",
    "CLEANUP_MISSED_DAYS_THRESHOLD", "STORAGE_ALERT_RATIO",
    "DEFAULT_STORAGE_CAP_BYTES", "CHAIN_ERROR_RATE_THRESHOLD",
]
