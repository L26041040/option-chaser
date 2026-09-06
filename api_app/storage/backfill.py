"""SCALE-01（#252，Scaling Foundation Stage 1-0）：既有 `results` 列的
歷史 fact context backfill。

冪等、可續跑、可安全中斷：`option_chaser.store.historical_fact_
context()` 是純函式，對同一份 `view` 永遠算出同一組值；
`Storage.save_result()` 本身就是覆蓋語意（同一 `(scenario_id,
analyzed_at)` 重複寫入即覆蓋）。整批重跑因此不會產生任何 duplicate
side effect 或 drift——重跑只是把同一組值再寫一次；中斷在任何一列之後
都是安全的，直接重跑整批即可續跑，不需要記錄進度游標。

`view` 本身完全不被觸碰——`dataclasses.replace()` 只換掉新增的 5 個
欄位，其餘欄位（含 `view`）原樣帶回再寫入。
"""
from __future__ import annotations

import dataclasses

from option_chaser.store import historical_fact_context

from . import Storage


def backfill_result_fact_context(db: Storage) -> dict:
    """對每個劇本（含已封存）的每一筆歷史結果，補齊 SCALE-01 新增的
    5 個歷史 fact 欄位（`resolved_params`／`requested_strategies`／
    `engine_version`／`view_schema_version`／`history_replay_
    version`）。

    回傳 `{"scenarios": N, "rows": M}` 供呼叫端（CLI 腳本／測試）回報
    處理量——不代表「這次真的改了幾筆」，重跑時每一列都會被重新寫入
    同一組值，這是刻意的冪等設計，不是缺陷。"""
    scenarios = 0
    rows = 0
    for sc in db.list_scenarios(include_archived=True):
        scenarios += 1
        for rec in db.result_history(sc.id):
            rows += 1
            context = historical_fact_context(rec.view)
            db.save_result(dataclasses.replace(rec, **context))
    return {"scenarios": scenarios, "rows": rows}
