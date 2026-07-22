"""v6 spec §1.1：路由入口。所有金融計算一律經 option_chaser.service（沿用），
本檔僅宣告 st.navigation 頁面清單，不含任何業務邏輯。"""
from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Option Chaser", layout="wide")

page = st.navigation([
    st.Page("views/overview.py", title="戰情總覽", icon="📊", default=True),
    st.Page("views/workspace.py", title="劇本工作區", icon="🗂"),
    st.Page("views/quick.py", title="快速試算", icon="⚡"),
    st.Page("views/help.py", title="使用說明", icon="📖"),
    st.Page("views/detail.py", title="詳頁", url_path="detail", visibility="hidden"),
])
page.run()
