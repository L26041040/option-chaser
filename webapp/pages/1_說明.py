"""webapp/pages/1_說明.py — v4 spec §4.6: Streamlit multipage help page.

Pure static content, no financial calculations. The glossary section is
generated from `option_chaser.glossary.GLOSSARY` (single source that also
feeds the main app's hover tooltips — see webapp/app.py's `_abbr`).

Wording avoids the v4 spec §6.1 banned-vocabulary red line list entirely
(uses 「非統計推論」 phrasing where a chance-related word might otherwise be
used), per spec §6.1/§6.4.
"""
from __future__ import annotations

import streamlit as st

from option_chaser.glossary import GLOSSARY

st.set_page_config(page_title="Option Chaser 說明", layout="wide")

st.title("說明")
st.caption("三步教學、名詞表、免責事項與模型假設。純文字說明頁，不做任何計算。")

st.header("三步教學")

st.subheader("Step 1　寫劇本")
st.markdown(
    "四項輸入的意義：\n"
    "- **標的**：要分析的股票代號。\n"
    "- **現價**：資料快照當下的市價（非即時報價）。\n"
    "- **目標價位**：你設定的劇本假設價格，不是模型的預測。\n"
    "- **預計到達時間**：劇本假設中，標的到達目標價的日期。\n"
)

st.subheader("Step 2　看主圖")
st.markdown(
    "主圖是一張 Heatmap：左軸為價格、每一欄為一個日期、每一格為以 Mid 進場的模型報酬率。"
    "左軸中**粗體**的價格列是關鍵價位，其餘為等距內插價。\n"
)
st.markdown(
    "四個關鍵讀法：\n"
    "- **現價列**＝不漲情境：標的完全不漲時的模型報酬率。\n"
    "- **目標列**＝劇本成立：標的到達目標價時的模型報酬率。\n"
    "- **超標列**＝超漲：漲幅超過目標價一截時的模型報酬率。\n"
    "- **深跌列**＝容錯底線：跌破現價一截時的模型報酬率，作為下檔參考。\n"
)

st.subheader("Step 3　比候選")
st.markdown(
    "比較表按到期日分組：**組間**＝到期日的時間階梯（到期日越晚，緩衝天數越多）；"
    "**組內**＝同一到期日下各策略的候選，如同一份購物清單。\n"
)
st.markdown(
    "標章意義：\n"
    "- 🚀：全體合格候選中劇本報酬最高的候選。\n"
    "- 🛡️：全體合格候選中情境最壞報酬最高（最強韌性）的候選。\n"
    "- ⚠：警示——該候選任一腿今日無成交，或成交摩擦超過門檻。\n"
    "- ◀：目前主圖選中的候選。\n"
)
st.markdown(
    "緩衝天數的取捨：到期日離劇本日**近**，到期價值與劇本價值收斂較完全，"
    "但時間容錯低；到期日離劇本日**遠**，收斂不完全，時間容錯較高，"
    "但需承擔更長時間的不確定性與時間價值流失。"
)

st.header("名詞表")
_rows = ["|名詞|說明|", "|---|---|"]
for term, desc in GLOSSARY.items():
    _rows.append(f"|{term}|{desc}|")
st.markdown("\n".join(_rows))

st.header("免責事項")
st.markdown(
    "- 本工具所有數字皆為模型估計，非保證成交價格。\n"
    "- 本工具不構成投資建議。\n"
    "- 報價資料可能延遲約 15 分鐘，實際成交以下單當下報價為準。\n"
)

st.header("模型假設")
st.markdown(
    "- 估值假設無股利調整（q=0）。\n"
    "- 隱含波動率（IV）假設由今日恆定至劇本日。\n"
    "- 延遲情境（晚 30／90 天）採線性價格路徑，屬模型假設，非市場預測。\n"
    "- 估值採 Black-Scholes 歐式模型，並以美式選擇權之內在價值鉗制下限。\n"
)

st.caption(
    "註：本頁與 GUI 內所有「情境最壞」相關文案，皆指 7 個固定壓力情境中的最低報酬率，"
    "屬透明情境集合的最壞值，非統計推論、亦非所有可能情況的最壞。"
)
