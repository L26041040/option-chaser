# NOTE (test infra adaptation, not a spec change):
# `webapp/app.py` is a Streamlit script — the whole file executes top-level
# `st.*` calls (st.set_page_config, `with st.form(...)`, etc.) on any plain
# Python import. Doing `from webapp.app import cell_color` directly at
# module scope here would run that script exactly once *outside* of
# AppTest's managed runtime (no ScriptRunContext). Streamlit's DeltaGenerator
# for `st.form()` degrades in that bare-import case to permanently stamping
# `_form_data` onto the process-wide singleton main DeltaGenerator (it has no
# cursor to allocate a proper child block), which then makes every later
# `st.form(...)` call in the *same process* raise "Forms cannot be nested in
# other forms" — including inside tests/test_webapp.py's AppTest-driven runs,
# since pytest imports all test modules during collection regardless of file
# order. To keep this file import-side-effect-free for the rest of the
# session, we fetch `cell_color`'s source from a throwaway subprocess (which
# takes the one-time bare-import poison to its own grave) and exec it locally.
# This changes nothing about the assertions below or the function under test.
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_cell_color():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, "-c",
         "import inspect, webapp.app as m; print(inspect.getsource(m.cell_color))"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(_REPO_ROOT),
        env=env, check=True,
    )
    ns: dict = {}
    exec(result.stdout, ns)
    return ns["cell_color"]


cell_color = _load_cell_color()


def test_neutral_band():
    assert cell_color(0.0) == "#ededed" == cell_color(0.049) == cell_color(-0.049)


def test_zero_centered_signs():
    assert cell_color(0.5) != cell_color(-0.5)


def test_clamp_saturation():
    assert cell_color(1.0) == cell_color(9.43)      # +943% same as +100%
    assert cell_color(-1.0) == cell_color(-5.1)


def test_deterministic():
    assert cell_color(0.37) == cell_color(0.37)
