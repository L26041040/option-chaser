# tests/test_redlines.py
"""v4 spec §6.1: banned-vocabulary scan over GUI sources and goldens
＋ 附錄 A9 守則：除授權的 anchor 例外，任何「把年月補成某一天」的寫法都是缺陷。"""
import dataclasses
import re
from pathlib import Path

import pytest

from option_chaser.models import AnalysisParams
from option_chaser.store import Scenario

BANNED = ["獲利機率", "機率加權", "勝率", "POP", "probability",
          "期望報酬", "expected profit", "Sharpe", "CVaR"]
TARGETS = [Path("webapp/app.py"), Path("webapp/pages/1_說明.py"),
           Path("option_chaser/glossary.py"),
           Path("option_chaser/store.py"), Path("option_chaser/workspace.py"),
           Path("option_chaser/vocabulary.py"),
           Path("webapp/render.py"), Path("webapp/pages/0_劇本工作區.py"),
           *sorted(Path("tests/fixtures").glob("golden_*.txt"))]


def test_no_banned_vocabulary():
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        for term in BANNED:
            assert term not in text, f"{term!r} found in {path}"


def test_new_copy_avoids_bare_probability_word():
    """v4-new files must not contain the bare word 機率 at all."""
    for path in [Path("option_chaser/glossary.py"),
                 Path("webapp/pages/1_說明.py"),
                 Path("option_chaser/scenarios.py"),
                 Path("option_chaser/store.py"),
                 Path("option_chaser/workspace.py"),
                 Path("option_chaser/vocabulary.py"),
                 Path("webapp/render.py"),
                 Path("webapp/pages/0_劇本工作區.py")]:
        assert "機率" not in path.read_text(encoding="utf-8"), path


# ---------- 附錄 A9：年月不得被補成某一天 ----------

_SOURCE_ROOTS = (Path("option_chaser"), Path("webapp"))


def _sources():
    for root in _SOURCE_ROOTS:
        yield from sorted(p for p in root.rglob("*.py"))


def test_nothing_writes_a_target_date_anywhere_in_sources():
    """生產程式碼不得產生任何目標日期——沒有欄位指派、沒有具名參數、沒有 JSON 鍵。

    只讀不寫是允許的：`store.migrate_scenario` 必須認得舊檔的 target_date 鍵才
    能把它遷移掉。這裡鎖的是「寫出一天」的形狀。
    """
    written = re.compile(r'target_date\s*=|["\']target_date["\']\s*:')
    offenders = [str(p) for p in _sources()
                 if written.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_analysis_params_has_no_settable_date_field():
    fields = {f.name for f in dataclasses.fields(AnalysisParams)}
    assert "target_month" in fields and "target_date" not in fields
    with pytest.raises(TypeError):
        AnalysisParams(target_price=120.0, target_date="2028-01-21")


def test_anchor_is_derived_and_never_persisted():
    p = AnalysisParams(target_price=120.0, target_month="2028-01")
    assert p.anchor.isoformat() == "2028-01-21"      # 該月第三個星期五
    assert "anchor" not in dataclasses.asdict(p)     # 不進持久化
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.anchor = "2028-01-01"                      # 也無法被覆寫


def test_scenario_persists_month_not_a_day():
    fields = {f.name for f in dataclasses.fields(Scenario)}
    assert "target_month" in fields and "target_date" not in fields
