# tests/test_redlines.py
"""v4 spec §6.1: banned-vocabulary scan over GUI sources and goldens."""
from pathlib import Path

BANNED = ["獲利機率", "機率加權", "勝率", "POP", "probability",
          "期望報酬", "expected profit", "Sharpe", "CVaR"]
TARGETS = [Path("webapp/app.py"), Path("webapp/views/help.py"),
           Path("option_chaser/glossary.py"),
           Path("option_chaser/store.py"), Path("option_chaser/workspace.py"),
           Path("option_chaser/vocabulary.py"),
           Path("webapp/render.py"), Path("webapp/views/workspace.py"),
           *sorted(Path("tests/fixtures").glob("golden_*.txt"))]


def test_no_banned_vocabulary():
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        for term in BANNED:
            assert term not in text, f"{term!r} found in {path}"


def test_new_copy_avoids_bare_probability_word():
    """v4-new files must not contain the bare word 機率 at all."""
    for path in [Path("option_chaser/glossary.py"),
                 Path("webapp/views/help.py"),
                 Path("option_chaser/scenarios.py"),
                 Path("option_chaser/store.py"),
                 Path("option_chaser/workspace.py"),
                 Path("option_chaser/vocabulary.py"),
                 Path("webapp/render.py"),
                 Path("webapp/views/workspace.py")]:
        assert "機率" not in path.read_text(encoding="utf-8"), path
