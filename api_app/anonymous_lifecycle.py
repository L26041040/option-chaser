"""Anonymous owner lifecycle（PB-08／#300，Anonymous Public Beta）：
三段式生命週期的純函式判準——Active →（`abandoned_after_days`）
Abandoned →（再 `grace_period_days`）Eligible for hard delete。

**衍生狀態，不持久化**（比照既有 Direction／衍生三態設計原則：不落盤
判定結果本身，只落盤支撐判定的原始事實）——`owners` 表只存
`last_activity_at`（PB-01 既有欄位），「這個 owner 現在算不算
abandoned」永遠是即時算出來的，不是另一個欄位。這也是為什麼
`classify()` 是純函式：給定同一組輸入，任何時候呼叫都得到相同答案，
不需要一個「上次算出來是什麼」的快取狀態。

**這個模組完全不知道 `protected` 這件事**——「protected owner 結構性
排除在清理查詢之外」（spec §7 明文）落在**查詢**這一層，不是分類
邏輯這一層：呼叫端（`api_app/main.py` 的清理端點）必須先把
`protected` 的 owner 從候選清單濾掉，才把剩下的傳進來——這裡沒有第二
道防線去補救「不小心忘記濾」的錯誤，安全性建立在單一、清楚的把關點
上，而非分散成好幾個各自都要做對的判斷。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

LifecycleState = Literal["active", "abandoned", "eligible_for_hard_delete"]


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def classify(*, last_activity_at: str | None, created_at: str,
            now: datetime, abandoned_after_days: int,
            grace_period_days: int) -> LifecycleState:
    """倒數的錨點——`last_activity_at` 有值就用它，`None`（這個 owner
    從未被記過任何一次真人 activity，例如只造訪過網站列出清單、什麼都
    沒做）就退回 `created_at`。**不是特殊情況**：lazy creation
    （PB-02）在任何 owner-scoped 讀取端點就會建立一列 owner，光是
    「被建立過」不等於「有人真的在用這個網站」，這類 owner 理當跟著
    自己的建立時間開始倒數，不該因為從未觸發過任何一種真人操作而永遠
    不過期。

    讀不懂任一時間戳（理論上不該發生——兩者皆為既有機制寫入的合法
    ISO 字串）時保守回 `"active"`：分類失敗的後果不該是誤刪，寧可
    這一輪不清、留給下一次成功解析。"""
    anchor = _parse(last_activity_at) or _parse(created_at)
    if anchor is None:
        return "active"
    age = now - anchor
    if age >= timedelta(days=abandoned_after_days + grace_period_days):
        return "eligible_for_hard_delete"
    if age >= timedelta(days=abandoned_after_days):
        return "abandoned"
    return "active"
