"""Streamlit Community Cloud 的輕量密碼閘門。"""
from __future__ import annotations

import hmac

import streamlit as st


def require_password() -> None:
    """在目前 session 通過密碼前停止執行 App。

    密碼只從 Streamlit secrets 讀取；未設定時採 fail-closed，避免公開部署
    意外暴露。這是測試版的單一共用密碼，不是使用者帳號系統。
    """
    try:
        configured_password = st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        st.error("部署尚未設定 APP_PASSWORD，App 已安全鎖定。")
        st.stop()

    if not isinstance(configured_password, str) or not configured_password:
        st.error("APP_PASSWORD 必須是非空白字串，App 已安全鎖定。")
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
            use_container_width=True,
        )

    if submitted:
        if hmac.compare_digest(entered_password, configured_password):
            st.session_state["oc_authenticated"] = True
            st.session_state.pop("oc_password", None)
            st.rerun()
        st.error("密碼不正確，請再試一次。")

    st.stop()
