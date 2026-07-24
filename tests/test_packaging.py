"""v6 spec §8: packaging fix — webapp installable, version unified."""
import re
import tomllib
from pathlib import Path

import option_chaser


def test_version_matches_pyproject():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == option_chaser.__version__ == "0.6.0"


def test_streamlit_floor_is_1_57():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    gui = pyproject["project"]["optional-dependencies"]["gui"]
    assert any(re.match(r"streamlit>=1\.57", dep) for dep in gui), gui


def test_webapp_package_included():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    include = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "webapp*" in include


def test_streamlit_config_exists_and_light():
    text = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert 'base = "light"' in text
    assert "#eef0f3" in text  # backgroundColor
    assert "#ff4b4b" in text  # primaryColor


def test_streamlit_cloud_requirements_install_project_with_gui():
    text = Path("requirements.txt").read_text(encoding="utf-8")
    assert "-e .[gui]" in text.splitlines()


def test_streamlit_secret_file_is_ignored():
    ignored = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".streamlit/secrets.toml" in ignored


def test_cloud_preview_persistence_warning_is_documented():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "測試版資料可能重啟後消失" in readme


def test_webapp_importable_from_subprocess_without_pythonpath(tmp_path):
    """No-PYTHONPATH import proof: subprocess run from an unrelated cwd."""
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "import webapp.render; print('OK')"],
        capture_output=True, text=True, cwd=str(tmp_path), env=env)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
