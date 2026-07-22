"""v6 spec §2.1: Artifact 淺色視覺 token。

色彩來源權威 = Artifact 淺色呈現（其 :root 預設值）。全站色彩／字體由
.streamlit/config.toml 承載（Streamlit 官方主題機制，覆蓋原生元件）；本模組
的 CSS 僅補足 config.toml 無法表達的自訂視覺元件（卡片陰影／膠囊／徽章／
里程碑軌），選擇器一律以 `.oc-` 前綴自訂類別為準，不得覆寫 Streamlit 內部
DOM（`.stButton`／`[data-testid=...]`）——與 render.py 既有 `.oc-thumb`/
`.oc-num` 慣例一致。
"""
from __future__ import annotations

import streamlit as st

TOKENS: dict[str, str] = {
    "bg": "#eef0f3",
    "chrome": "#f3f4f6",
    "chrome_ink": "#374151",
    "surface": "#ffffff",
    "ink": "#1c1f26",
    "dim": "#6b7280",
    "line": "#e3e6ea",
    "accent": "#ff4b4b",
    "pos": "#1a7f37",
    "neg": "#b22222",
}

THEME_CSS = f"""
.oc-card {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(15,18,25,.10);
  padding: 14px 18px;
  margin: 10px 0;
}}
.oc-pill {{
  display: inline-block;
  border-radius: 999px;
  padding: 1px 10px;
  font-size: 12.5px;
  border: 1px solid;
  white-space: nowrap;
}}
.oc-pill-active {{ color: {TOKENS['pos']}; border-color: {TOKENS['pos']}; background: #ecf9f0; }}
.oc-pill-reached {{ color: #7a5b00; border-color: #caa53d; background: #fff8e1; }}
.oc-pill-expired {{ color: {TOKENS['dim']}; border-color: {TOKENS['dim']}; background: #f3f4f6; }}
.oc-pill-invalidated {{ color: {TOKENS['neg']}; border-color: {TOKENS['neg']}; background: #fbeaea; }}
.oc-badge-ok {{ color: {TOKENS['pos']}; }}
.oc-badge-warn {{ color: #b45309; }}
.oc-badge-stale {{ color: {TOKENS['dim']}; }}
.oc-metric-tile {{
  background: {TOKENS['chrome']};
  border-radius: 10px;
  padding: 10px 16px;
  min-width: 140px;
  display: inline-block;
  margin: 0 8px 8px 0;
}}
.oc-metric-tile .oc-metric-label {{ font-size: 12px; color: {TOKENS['chrome_ink']}; }}
.oc-metric-tile .oc-metric-value {{ font-size: 22px; font-weight: 600; color: {TOKENS['ink']}; }}
.oc-rail-node {{ border-left: 2px solid {TOKENS['line']}; padding-left: 14px; margin: 6px 0; }}
.oc-rail-node.oc-rail-confirmed {{ border-left-color: {TOKENS['accent']}; }}
.oc-num {{ font-variant-numeric: tabular-nums; }}
.oc-thumb {{ display: inline-block; width: 46px; overflow: hidden; }}
"""


def inject() -> None:
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
