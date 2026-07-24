"""Option Chaser 應用程式外殼與路由入口。

所有金融計算一律經 option_chaser.service（沿用）；本檔只負責產品 header、
頁面寬度與 st.navigation，不含任何業務邏輯。
"""
from __future__ import annotations

import streamlit as st

from webapp.auth import require_password
from webapp.theme import inject, product_header_html

st.set_page_config(
    page_title="Option Chaser",
    page_icon=":material/query_stats:",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"Get help": None, "Report a Bug": None, "About": None},
)

require_password()

page = st.navigation([
    st.Page(
        "views/overview.py",
        title="戰情總覽",
        icon=":material/space_dashboard:",
        default=True,
    ),
    st.Page("views/workspace.py", title="劇本工作區", icon=":material/view_list:"),
    st.Page("views/quick.py", title="快速試算", icon=":material/bolt:"),
    st.Page("views/help.py", title="使用說明", icon=":material/help:"),
    st.Page("views/detail.py", title="詳頁", url_path="detail", visibility="hidden"),
], position="top")

inject()
with st.container(key="oc-page-shell", width=1180):
    st.markdown(product_header_html(), unsafe_allow_html=True)
    page.run()
