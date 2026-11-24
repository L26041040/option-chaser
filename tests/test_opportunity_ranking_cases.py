"""V2-06（#408）：結果表改版只動呈現，後端排序與名次不變。

與前端 `src/OpportunityPage.test.tsx` 讀同一份案例
（`contracts/opportunity_ranking_cases.json`）：同一組資料，前後端的排序與名次都要
等於手排的字面順序。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from api_app.opportunity_search import sort_rows
from api_app.opportunity_settings import SORTS

CASES = json.loads(
    Path("contracts/opportunity_ranking_cases.json").read_text(encoding="utf-8"))


def _ids(rows: list[dict]) -> list[str]:
    return [f'{r["symbol"]}/{r["family"]}' for r in rows]


def test_cases_cover_every_sort_option():
    assert sorted(CASES["expected"]) == sorted(SORTS)


@pytest.mark.parametrize("sort", sorted(CASES["expected"]))
def test_sort_rows_matches_shared_ranking(sort):
    rows = [dict(r) for r in CASES["rows"]]
    assert _ids(sort_rows(rows, sort)) == CASES["expected"][sort]
    # 與輸入順序無關：打亂後名次相同。
    shuffled = rows[:]
    random.Random(408).shuffle(shuffled)
    assert _ids(sort_rows(shuffled, sort)) == CASES["expected"][sort]
