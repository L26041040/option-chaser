"""Option Chaser MVP V2 interactive evaluation page."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from option_chaser.v2 import (
    ApiContractError,
    evaluate_api_payload,
)
from webapp.v2_presenter import (
    DEFAULT_CHAIN_ROWS,
    V2PresenterError,
    build_evaluation_payload,
    candidate_display_rows,
)


_RESULT_KEY = "v2-evaluation-result"
_CHAIN_KEY = "v2-chain-editor"


def _default_expiry() -> date:
    """Return a stable future placeholder expiry for manual evaluation."""

    return date.today() + timedelta(days=365)


def _format_currency(value: object) -> str:
    if value is None:
        return "—"

    return f"${float(value):,.2f}"


def _format_percent(value: object) -> str:
    if value is None:
        return "—"

    return f"{float(value):,.1f}%"


st.title("V2 價差試算")
st.caption(
    "新版計算核心的獨立操作頁。目前先以可編輯 Option Chain 驗證完整流程，"
    "不會呼叫舊版分析服務。"
)

with st.expander("這一版在測什麼？", expanded=False):
    st.markdown(
        """
- 列舉同一到期日內的所有合法 Debit Spread
- 使用 Ask 口徑計算實際進場成本
- 計算目標價下的到期價值與報酬
- 保留缺少報價或無法排名的候選
- 尚未套用 Ranking Engine，因此目前顯示結構順序
        """
    )

with st.form("v2-evaluation-form"):
    left, middle, right = st.columns(3)

    with left:
        strategy = st.selectbox(
            "策略",
            options=("bull_call", "bear_put"),
            format_func=lambda value: (
                "Bull Call Spread"
                if value == "bull_call"
                else "Bear Put Spread"
            ),
        )

    with middle:
        expiry = st.date_input(
            "到期日",
            value=_default_expiry(),
            min_value=date.today() + timedelta(days=1),
        )

    with right:
        target_price = st.number_input(
            "目標價",
            min_value=0.01,
            value=115.0,
            step=1.0,
        )

    contract_multiplier = st.number_input(
        "合約乘數",
        min_value=0.01,
        value=100.0,
        step=1.0,
        help="美股標準選擇權通常為 100。",
    )

    st.subheader("Option Chain")

    chain_rows = st.data_editor(
        list(DEFAULT_CHAIN_ROWS),
        key=_CHAIN_KEY,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "strike": st.column_config.NumberColumn(
                "Strike",
                required=True,
                min_value=0.01,
                format="%.2f",
            ),
            "bid": st.column_config.NumberColumn(
                "Bid",
                min_value=0.0,
                format="%.2f",
            ),
            "ask": st.column_config.NumberColumn(
                "Ask",
                min_value=0.0,
                format="%.2f",
            ),
            "implied_volatility": st.column_config.NumberColumn(
                "IV",
                min_value=0.0,
                format="%.4f",
            ),
            "open_interest": st.column_config.NumberColumn(
                "Open Interest",
                min_value=0.0,
                format="%.0f",
            ),
            "volume": st.column_config.NumberColumn(
                "Volume",
                min_value=0.0,
                format="%.0f",
            ),
        },
    )

    submitted = st.form_submit_button(
        "計算全部價差",
        type="primary",
        use_container_width=True,
    )

if submitted:
    try:
        payload = build_evaluation_payload(
            strategy=strategy,
            expiry=expiry.isoformat(),
            target_price=target_price,
            contract_multiplier=contract_multiplier,
            chain_rows=chain_rows,
        )

        st.session_state[_RESULT_KEY] = evaluate_api_payload(
            payload
        )
        st.session_state.pop("v2-evaluation-error", None)

    except (V2PresenterError, ApiContractError) as exc:
        st.session_state.pop(_RESULT_KEY, None)
        st.session_state["v2-evaluation-error"] = str(exc)

if st.session_state.get("v2-evaluation-error"):
    st.error(st.session_state["v2-evaluation-error"])

response = st.session_state.get(_RESULT_KEY)

if response is not None:
    st.divider()
    st.subheader("計算結果")

    metric_a, metric_b, metric_c, metric_d = st.columns(4)

    metric_a.metric(
        "原始合約",
        int(response["source_contract_count"]),
    )
    metric_b.metric(
        "全部組合",
        int(response["candidate_count"]),
    )
    metric_c.metric(
        "可排名",
        int(response["rankable_count"]),
    )
    metric_d.metric(
        "資料不足",
        int(response["unrankable_count"]),
    )

    display_rows = candidate_display_rows(response)
    rankable_rows = [
        row
        for row in display_rows
        if row["狀態"] == "可排名"
    ]
    unrankable_rows = [
        row
        for row in display_rows
        if row["狀態"] != "可排名"
    ]

    st.markdown("### 可排名候選")

    if rankable_rows:
        st.dataframe(
            rankable_rows,
            use_container_width=True,
            hide_index=True,
            column_config={
                "進場成本": st.column_config.NumberColumn(
                    "進場成本",
                    format="$%.2f",
                ),
                "目標損益": st.column_config.NumberColumn(
                    "目標損益",
                    format="$%.2f",
                ),
                "目標報酬率 (%)": st.column_config.NumberColumn(
                    "目標報酬率",
                    format="%.1f%%",
                ),
                "Candidate Key": None,
            },
        )
    else:
        st.info("目前沒有具備完整 Ask 報價的可排名候選。")

    with st.expander(
        f"查看資料不足候選（{len(unrankable_rows)}）",
        expanded=False,
    ):
        if unrankable_rows:
            st.dataframe(
                unrankable_rows,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Candidate Key": None,
                },
            )
        else:
            st.success("全部候選皆具備完整報價。")

    st.caption(
        "目前尚未排序。下一階段 Ranking Engine 完成後，"
        "此區會直接改成推薦結果與前三名比較。"
    )