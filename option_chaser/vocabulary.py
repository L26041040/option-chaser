"""v5 spec §6: State/Event/Action 詞彙表（文件＋常數，零引擎邏輯）。

- EVENT_TYPES_V5: v5 生效 5 種（store/workspace 寫事件僅允許這些）。
- EVENT_TYPES_V7_RESERVED: v7 預留 5 種（本版僅常數定義，寫入被拒）。
- ACTION_TYPES: 11 種，v5 全部僅文件用途（無任何程式碼觸發）。
"""
from __future__ import annotations

SCENARIO_STATUSES: tuple[str, ...] = ("Active", "Reached", "Expired", "Invalidated")

EVENT_TYPES_V5: tuple[str, ...] = (
    "SCENARIO_CREATED", "STATUS_CHANGED", "ANALYSIS_COMPLETED",
    "GROUP_RELATION_CONFIRMED", "SCENARIO_DELETED")

EVENT_TYPES_V7_RESERVED: tuple[str, ...] = (
    "PRICE_REACHED", "TARGET_DATE_ARRIVED", "EXPIRY_BUFFER_LOW",
    "LIQUIDITY_DEGRADED", "REANALYSIS_REQUESTED")

EVENT_TYPES: tuple[str, ...] = EVENT_TYPES_V5 + EVENT_TYPES_V7_RESERVED

ACTION_TYPES: tuple[str, ...] = (
    "HOLD", "OPEN", "ADD", "REDUCE", "CLOSE", "RECOVER_PRINCIPAL",
    "KEEP_RUNNER", "ROLL_TO_NEXT_MILESTONE", "SWITCH_SCENARIO",
    "HOLD_CASH", "RERUN_ANALYSIS")

RELATION_CHOICES: tuple[str, ...] = (
    "milestone-path", "independent", "exclusive", "undefined")
