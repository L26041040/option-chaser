"""SCALE-01（#252，Scaling Foundation Stage 1-0）：既有 `results` 列的
歷史 fact context backfill。

冪等、可續跑、可安全中斷：`option_chaser.store.historical_fact_
context()` 是純函式，對同一份 `view` 永遠算出同一組值；
`Storage.save_result()` 本身就是覆蓋語意（同一 `(scenario_id,
analyzed_at)` 重複寫入即覆蓋）。整批重跑因此不會產生任何 duplicate
side effect 或 drift——重跑只是把同一組值再寫一次；中斷在任何一列之後
都是安全的，直接重跑整批即可續跑，不需要記錄進度游標。

`view` 本身完全不被觸碰——`dataclasses.replace()` 只換掉新增的 6 個
欄位，其餘欄位（含 `view`）原樣帶回再寫入。

SCALE-16（#267，Stage 1-5）：本票之後寫入的 ledger 列 `rec.view` 恆為
`None`（不再背負完整 view payload）——這種列在寫入當下就已經帶著正確
的 fact context（`main.py::_refresh_and_save()` 直接算好才寫入），
不需要、也無法（沒有 `view` 可讀）重新推導，見下方 `rec.view is None`
的跳過分支。這不是本腳本邏輯上的缺口，是這批列根本不屬於本腳本要
服務的對象（「既有列尚未 backfill」）。
"""
from __future__ import annotations

import dataclasses

from option_chaser.store import historical_fact_context

from . import Storage


def backfill_result_fact_context(db: Storage) -> dict:
    """對每個劇本（含已封存）的每一筆歷史結果，補齊 SCALE-01 新增的
    6 個歷史 fact 欄位（`resolved_params`／`requested_strategies`／
    `engine_version`／`view_schema_version`／`history_replay_
    version`／`snapshot_source`）。

    回傳 `{"scenarios": N, "rows": M}` 供呼叫端（CLI 腳本／測試）回報
    處理量——不代表「這次真的改了幾筆」，重跑時每一列都會被重新寫入
    同一組值，這是刻意的冪等設計，不是缺陷。SCALE-16（#267）之後、
    `view is None` 的 ledger 列不計入 `rows`（這些列本來就沒有 view
    可供推導，也不需要——寫入當下已經帶著正確的 fact context）。

    SCALE-11（#262）：本函式是**跨全部 owner** 的一次性遷移工具，比照
    既有 `backfill_missing_owner_ids()` 同一類別——它的職責就是修復
    每一個 owner 的資料，不是替某一個 owner 服務的查詢路徑。
    `owner=None` 是 `list_scenarios()`／`result_history()` 唯一給這種
    admin 用途保留的顯式選項（無預設值、不會被誤用），不構成繞過
    owner boundary 的旁路。"""
    scenarios = 0
    rows = 0
    for sc in db.list_scenarios(owner=None, include_archived=True):
        scenarios += 1
        for rec in db.result_history(sc.id, owner=None):
            if rec.view is None:
                continue
            rows += 1
            context = historical_fact_context(rec.view)
            db.save_result(dataclasses.replace(rec, **context))
    return {"scenarios": scenarios, "rows": rows}
