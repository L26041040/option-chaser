"""v6 spec §3.1：戰情總覽（首頁）。全部數字為既有資料彙總（計數/時間比對），
零金融公式。"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import streamlit as st

from option_chaser import store, workspace
from webapp.components import metric_tile
from webapp.theme import inject

WS_ROOT = Path(os.environ.get("OC_WORKSPACE", "workspace"))

inject()
st.title("戰情總覽")

scenarios = workspace.list_scenarios(WS_ROOT)

if not scenarios:
    # 注意：本頁獨立測試時（AppTest.from_file 直接載入本檔）尚無 st.navigation
    # 路由存在，st.page_link 要求目標檔案必須是「已在 st.navigation 註冊的頁面」
    # 否則丟例外——此處故意只用純文字指引，可點擊的頁面連結延後到 Task 12（路由
    # 建好後）以 st.page_link 升級並於 test_app_navigation.py 驗證整合行為。
    st.markdown("尚無劇本。前往「劇本工作區」建立第一個劇本。")
else:
    views = {sc.id: workspace.latest_result(WS_ROOT, sc.id) for sc in scenarios}
    groups = workspace.load_groups(WS_ROOT)

    active_n = sum(1 for sc in scenarios if sc.status == "Active")
    unanalyzed_n = sum(1 for sc in scenarios if views[sc.id] is None)
    bad_quality_n = sum(1 for sc in scenarios if views[sc.id] is not None and (
        views[sc.id]["data_quality"]["all_quotes_filtered"]
        or views[sc.id]["default_selection"] is None))
    reached_n = sum(1 for sc in scenarios if sc.status == "Reached")
    pending_relations = sum(
        1 for g in groups["groups"] for rel in g["relations"]
        if rel["confirmed"] == "undefined")
    analyzed_times = [v["analyzed_at"] for v in views.values() if v is not None]
    latest_time = max(analyzed_times) if analyzed_times else "—"

    tiles = "".join([
        metric_tile("Active 劇本數", str(active_n)),
        metric_tile("尚未分析", str(unanalyzed_n)),
        metric_tile("資料異常", str(bad_quality_n)),
        metric_tile("已完成", str(reached_n)),
        metric_tile("待確認關係", str(pending_relations)),
        metric_tile("最近分析時間", latest_time),
    ])
    st.markdown(tiles, unsafe_allow_html=True)

    st.subheader("劇本速覽")
    for sc in scenarios:
        st.markdown(f"**{sc.symbol}** {sc.status} ｜ 目標 ${sc.target_price:g} ｜ {sc.target_date}")
