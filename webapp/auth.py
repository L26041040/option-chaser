"""Streamlit 的輕量密碼閘門。"""
from __future__ import annotations

import hmac
import os

import streamlit as st


def _configured_password() -> object:
    """Read local launcher password first, then deployment secrets."""

    environment_password = os.environ.get("APP_PASSWORD")

    if environment_password is not None:
        return environment_password

    try:
        return st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        return None


def require_password() -> None:
    """Stop the app until the current session passes the shared password.

    Local launchers may provide ``APP_PASSWORD`` as an environment variable.
    Hosted deployments continue to use Streamlit secrets. Missing or invalid
    configuration remains fail-closed.
    """

    configured_password = _configured_password()

    if not isinstance(configured_password, str) or not configured_password:
        st.error("尚未設定 APP_PASSWORD，App 已安全鎖定。")
        st.stop()

    if st.session_state.get("oc_authenticated") is True:
        return

    st.markdown("## Option Chaser")
    st.caption("私人測試版 · 請輸入存取密碼")

    with st.form("oc_password_form"):
        entered_password = st.text_input(
            "密碼",
            type="password",
            key="oc_password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "進入 Option Chaser",
            key="oc_password_submit",
            type="primary",
            width="stretch",
        )

    if submitted:
        if hmac.compare_digest(entered_password, configured_password):
            st.session_state["oc_authenticated"] = True
            st.session_state.pop("oc_password", None)
            st.rerun()

        st.error("密碼不正確，請再試一次。")

    st.stop()
