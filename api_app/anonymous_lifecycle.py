"""Anonymous owner lifecycle（PB-08／#300 → SECURITY-FIX-01）：清理判定
的純函式判準。

SECURITY-FIX-01（Owner 裁示）改寫了倒數的錨點與天數：

- **錨點是 browser identity 的 `last_seen_at`**——任何帶有效 cookie 的
  請求都會推這個值（包含開站自動刷新、只打開來看）。PB-08 原本用的
  `last_activity_at`（只有建立／編輯／手動刷新等六種操作才推）已經不再
  參與判定：「只看不改」的使用者會在第 37 天被整個刪掉，而他昨天才
  打開過——這正是這次要修的資料遺失。
- **有資料的 owner**：`retention_days`（預設 180）沒有任何有效 cookie
  回訪 → abandoned；再過 `grace_period_days`（預設 7）→ 可刪。
- **空 owner**（沒有劇本、設定、credential）：`empty_retention_days`
  （預設 1）沒回訪就可刪。deferred owner creation 之後這種 owner 本來
  就很少；刪掉也不會讓使用者失去任何東西——那顆 cookie 只是變回「還沒
  綁定」，下次建立東西時自然拿到新 owner。
- 沒有任何 identity 列（例如合成壓測 owner）時退回 `created_at`。

**衍生狀態，不持久化**：判定結果永遠即時算，不落盤。

**這個模組完全不知道 `protected` 這件事**——protected owner 在**查詢**
這一層（`main.py` 的清理端點）就先被濾掉，單一把關點。
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


def classify(*, last_seen_at: str | None, created_at: str, has_data: bool,
            now: datetime, retention_days: int, grace_period_days: int,
            empty_retention_days: int) -> LifecycleState:
    """讀不懂時間戳（理論上不該發生）時保守回 `"active"`：分類失敗的
    後果不該是誤刪，寧可這一輪不清。"""
    anchor = _parse(last_seen_at) or _parse(created_at)
    if anchor is None:
        return "active"
    age = now - anchor
    if not has_data:
        return ("eligible_for_hard_delete"
                if age >= timedelta(days=empty_retention_days) else "active")
    if age >= timedelta(days=retention_days + grace_period_days):
        return "eligible_for_hard_delete"
    if age >= timedelta(days=retention_days):
        return "abandoned"
    return "active"
