"""Streamlit Community Cloud 密碼閘門。"""
from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest


def _locked_app(password: str | None = "test-password") -> AppTest:
    at = AppTest.from_file("webapp/app.py")

    if password is None:
        # AppTest only replaces the real Streamlit secrets when its test
        # secrets dictionary is non-empty. A harmless sentinel forces that
        # replacement while intentionally leaving APP_PASSWORD absent.
        at.secrets["_TEST_SENTINEL"] = True
    else:
        at.secrets["APP_PASSWORD"] = password

    return at
    

def test_missing_secret_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    at = _locked_app(password=None).run()

    assert not at.exception
    assert any("APP_PASSWORD" in error.value for error in at.error)
    assert not at.title


def test_wrong_password_stays_locked(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    at = _locked_app().run()
    at.text_input(key="oc_password").set_value("wrong-password")
    at.button(key="oc_password_submit").click().run()

    assert not at.exception
    assert any("密碼不正確" in error.value for error in at.error)
    assert "oc_authenticated" not in at.session_state
    assert not at.title


def test_correct_password_unlocks_app(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    at = _locked_app().run()
    at.text_input(key="oc_password").set_value("test-password")
    at.button(key="oc_password_submit").click().run()

    assert not at.exception
    assert at.session_state["oc_authenticated"] is True
    assert "戰情總覽" in " ".join(title.value for title in at.title)


def test_password_is_not_embedded_in_tracked_deployment_files():
    forbidden = "325" + "125"
    paths = [
        Path("webapp/app.py"),
        Path("webapp/auth.py"),
        Path("README.md"),
        Path("requirements.txt"),
    ]
    for path in paths:
        if path.exists():
            assert forbidden not in path.read_text(encoding="utf-8"), path
