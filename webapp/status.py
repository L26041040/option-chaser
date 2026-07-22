# webapp/status.py
"""v6 spec §6: 劇本顯示狀態推導（展示層純函數，非新狀態機——沿用既有
Scenario.status／result dict 資料，僅做分類判斷，零金融公式）。

quality_tone 優先序（工程決策，spec 未明定精確優先序時的完成）：
報價不足 > 歷史資料 > 正常——報價不足更具行動急迫性，優先呈現。

誠實聲明（spec §6.1）：引擎不存在「以最後成交價／虛構報價頂替」的降級
資料路徑，本模組亦無對應觸發判斷；「使用測試性頂替資料」狀態文案僅為
未來 vocabulary 保留，本檔不實作。
"""
from __future__ import annotations

from datetime import date

from option_chaser.data.snapshot import snapshot_today

INSUFFICIENT_QUOTE_MESSAGE = "已完成分析，但目前報價資料不足，沒有可用候選。"
EMPTY_CANDIDATE_MESSAGE = "已完成分析，目前沒有符合條件的候選。"
LEGACY_RESULT_MESSAGE = "舊版分析結果，重新分析以顯示完整價格。"


def is_legacy_schema(view: dict) -> bool:
    """v6 spec §4.3：result 檔 schema_version < 2 即缺 natural_per_contract／
    max_profit_per_contract／cap_price（Task 2 新欄），components/views 應顯示
    LEGACY_RESULT_MESSAGE 並以 .get() 降級讀取，而非 KeyError。"""
    return view.get("schema_version", 1) < 2


def derive_result_status(view: dict | None) -> str:
    if view is None:
        return "尚未分析"
    if view["data_quality"]["all_quotes_filtered"]:
        return "報價資料不足"
    if view["default_selection"] is not None:
        return "有可用候選"
    return "無合格候選"


def quality_tone(view: dict | None, observed: date) -> str:
    if view is None:
        return "正常"
    if view["data_quality"]["all_quotes_filtered"]:
        return "報價不足"
    if snapshot_today(view["snapshot_ref"]["fetched_at"]) != observed:
        return "歷史資料"
    return "正常"
