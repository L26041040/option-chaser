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
.oc-product-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 2px 17px;
  margin-bottom: 20px;
  border-bottom: 1px solid {TOKENS['line']};
}}
.oc-brand-lockup {{
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}}
.oc-brand-mark {{
  display: inline-grid;
  place-items: center;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  border-radius: 13px;
  background: {TOKENS['ink']};
  color: {TOKENS['surface']};
  font-size: 13px;
  font-weight: 750;
  letter-spacing: .04em;
  box-shadow: 0 8px 20px rgba(28,31,38,.16);
}}
.oc-brand-name {{
  color: {TOKENS['ink']};
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.2;
}}
.oc-brand-subtitle {{
  color: {TOKENS['dim']};
  font-size: 12.5px;
  line-height: 1.45;
  margin-top: 2px;
}}
.oc-brand-context {{
  color: {TOKENS['chrome_ink']};
  background: {TOKENS['chrome']};
  border: 1px solid {TOKENS['line']};
  border-radius: 999px;
  padding: 5px 11px;
  font-size: 12px;
  white-space: nowrap;
}}
@media (max-width: 640px) {{
  .oc-product-header {{
    align-items: flex-start;
    padding-top: 12px;
    margin-bottom: 14px;
  }}
  .oc-brand-context {{
    display: none;
  }}
  .oc-brand-mark {{
    width: 38px;
    height: 38px;
    flex-basis: 38px;
    border-radius: 12px;
  }}
  .oc-brand-name {{
    font-size: 17px;
  }}
}}
.oc-card {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 8px;
  box-shadow: 0 8px 22px rgba(15,18,25,.08);
  padding: 14px 18px;
  margin: 10px 0;
}}
.oc-scenario-list-item {{
  padding: 13px 16px 14px;
  margin: 8px 0 6px;
}}
.oc-scenario-main {{
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-bottom: 10px;
}}
.oc-scenario-symbol {{
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  margin-right: auto;
}}
.oc-scenario-symbol strong {{
  color: {TOKENS['ink']};
  font-size: 18px;
  line-height: 1.15;
  white-space: nowrap;
}}
.oc-scenario-direction {{
  color: {TOKENS['chrome_ink']};
  background: {TOKENS['chrome']};
  border: 1px solid {TOKENS['line']};
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 12px;
  white-space: nowrap;
}}
.oc-field-label {{
  color: {TOKENS['dim']};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  white-space: nowrap;
}}
.oc-scenario-grid {{
  display: grid;
  grid-template-columns: minmax(56px, .72fr) minmax(76px, .9fr) minmax(84px, .95fr) minmax(100px, 1.1fr) minmax(72px, .8fr) minmax(82px, .9fr) minmax(160px, 1.65fr) minmax(92px, 1fr) minmax(112px, 1.15fr) minmax(86px, .95fr);
  gap: 8px 12px;
  align-items: start;
}}
.oc-scenario-field {{
  min-width: 0;
}}
.oc-scenario-field span {{
  display: block;
  color: {TOKENS['dim']};
  font-size: 11px;
  line-height: 1.25;
  margin-bottom: 2px;
  white-space: nowrap;
}}
.oc-scenario-field strong {{
  display: block;
  color: {TOKENS['ink']};
  font-size: 13px;
  font-weight: 600;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.oc-scenario-notes {{
  color: {TOKENS['dim']};
  border-top: 1px solid {TOKENS['line']};
  font-size: 12px;
  line-height: 1.45;
  margin-top: 11px;
  padding-top: 9px;
}}
@media (max-width: 700px) {{
  .oc-scenario-list-item {{
    padding: 12px 13px;
  }}
  .oc-scenario-main {{
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 11px;
  }}
  .oc-scenario-symbol {{
    flex-basis: 100%;
  }}
  .oc-scenario-grid {{
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px 12px;
  }}
  .oc-scenario-wide {{
    grid-column: 1 / -1;
  }}
  .oc-scenario-field strong {{
    white-space: normal;
    overflow-wrap: anywhere;
  }}
  .oc-scenario-field .oc-num {{
    white-space: nowrap;
  }}
}}
.oc-eyebrow {{
  display: block;
  color: {TOKENS['dim']};
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .08em;
  line-height: 1.2;
  text-transform: uppercase;
}}
.oc-section-label {{
  color: {TOKENS['dim']};
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .055em;
  margin-bottom: 8px;
  text-transform: uppercase;
}}
.oc-section-label small {{
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0;
  margin-left: 5px;
  text-transform: none;
}}
.oc-candidate-card {{
  overflow: hidden;
  padding: 0;
}}
.oc-candidate-header {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  padding: 18px 20px 16px;
}}
.oc-candidate-header h3 {{
  color: {TOKENS['ink']};
  font-size: 20px;
  line-height: 1.2;
  margin: 4px 0;
}}
.oc-candidate-header p {{
  color: {TOKENS['dim']};
  font-size: 12.5px;
  margin: 0;
  white-space: nowrap;
}}
.oc-candidate-return,
.oc-comparison-return {{
  min-width: 124px;
  text-align: right;
}}
.oc-candidate-return span,
.oc-comparison-return span {{
  color: {TOKENS['dim']};
  display: block;
  font-size: 11px;
  font-weight: 650;
}}
.oc-candidate-return strong {{
  color: {TOKENS['pos']};
  display: block;
  font-size: 27px;
  font-weight: 750;
  letter-spacing: -.025em;
  line-height: 1.1;
}}
.oc-candidate-quotes {{
  background: {TOKENS['chrome']};
  border-bottom: 1px solid {TOKENS['line']};
  border-top: 1px solid {TOKENS['line']};
  padding: 12px 20px 14px;
}}
.oc-quote-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
  gap: 8px;
}}
.oc-quote-item {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 7px;
  min-width: 0;
  padding: 8px 10px;
}}
.oc-quote-item span {{
  color: {TOKENS['dim']};
  display: block;
  font-size: 10.5px;
  line-height: 1.2;
  margin-bottom: 3px;
  white-space: nowrap;
}}
.oc-quote-item strong {{
  color: {TOKENS['ink']};
  display: block;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}}
.oc-candidate-fundamentals {{
  display: grid;
  grid-template-columns: minmax(180px, .72fr) minmax(300px, 1.4fr) minmax(180px, .7fr);
  gap: 0;
}}
.oc-candidate-cost,
.oc-candidate-risk {{
  padding: 15px 20px 17px;
}}
.oc-candidate-cost {{
  border-right: 1px solid {TOKENS['line']};
}}
.oc-risk-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(90px, 1fr));
  gap: 12px;
}}
.oc-value-pair span {{
  color: {TOKENS['dim']};
  display: block;
  font-size: 10.5px;
  line-height: 1.25;
  margin-bottom: 3px;
}}
.oc-value-pair strong {{
  color: {TOKENS['ink']};
  display: block;
  font-size: 15px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
}}
.oc-value-pair-secondary {{
  margin-top: 10px;
}}
.oc-value-pair-secondary strong {{
  color: {TOKENS['chrome_ink']};
  font-size: 13px;
  font-weight: 600;
}}
.oc-spread-cap {{
  align-self: stretch;
  background: #f1f8f2;
  border-left: 1px solid #cde6d3;
  color: {TOKENS['pos']};
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 14px 18px;
}}
.oc-spread-cap span {{
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: .035em;
  text-transform: uppercase;
}}
.oc-spread-cap strong {{
  display: block;
  font-size: 19px;
  line-height: 1.25;
  margin: 2px 0;
  white-space: nowrap;
}}
.oc-spread-cap small {{
  color: #4d7658;
  font-size: 10.5px;
  line-height: 1.35;
}}
.oc-candidate-legacy {{
  background: #fff8e8;
  color: #9a6200;
  font-size: 11px;
  padding: 8px 20px;
}}
.oc-comparison-board {{
  min-width: 0;
  margin: 10px 0 22px;
}}
.oc-comparison-board-header {{
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 12px;
}}
.oc-comparison-board-header h3 {{
  color: {TOKENS['ink']};
  font-size: 18px;
  margin: 3px 0 0;
}}
.oc-comparison-board-header p {{
  color: {TOKENS['dim']};
  font-size: 11.5px;
  line-height: 1.4;
  margin: 0;
  max-width: 490px;
  text-align: right;
}}
.oc-comparison-expiry {{
  margin-bottom: 14px;
}}
.oc-comparison-expiry-title {{
  align-items: baseline;
  color: {TOKENS['ink']};
  display: flex;
  gap: 8px;
  padding: 4px 2px 7px;
}}
.oc-comparison-expiry-title strong {{
  font-size: 13px;
}}
.oc-comparison-expiry-title span {{
  color: {TOKENS['dim']};
  font-size: 11px;
}}
.oc-comparison-row {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 8px;
  box-shadow: 0 5px 16px rgba(15,18,25,.055);
  margin-bottom: 8px;
  overflow: hidden;
}}
.oc-comparison-row-header {{
  align-items: center;
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 11px 14px 10px;
}}
.oc-comparison-title {{
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}}
.oc-comparison-title strong {{
  color: {TOKENS['ink']};
  font-size: 14px;
}}
.oc-comparison-row-header p {{
  color: {TOKENS['dim']};
  font-size: 11.5px;
  margin: 2px 0 0;
  white-space: nowrap;
}}
.oc-comparison-badge {{
  background: {TOKENS['chrome']};
  border: 1px solid {TOKENS['line']};
  border-radius: 999px;
  color: {TOKENS['chrome_ink']};
  font-size: 10px;
  padding: 1px 7px;
  white-space: nowrap;
}}
.oc-comparison-return strong {{
  color: {TOKENS['pos']};
  display: inline-block;
  font-size: 19px;
  line-height: 1.1;
}}
.oc-comparison-return small {{
  color: {TOKENS['dim']};
  display: block;
  font-size: 10px;
  margin-top: 2px;
}}
.oc-comparison-grid {{
  border-top: 1px solid {TOKENS['line']};
  display: grid;
  grid-template-columns: minmax(300px, 1.45fr) minmax(145px, .62fr) minmax(260px, 1.05fr) minmax(155px, .58fr);
}}
.oc-comparison-quotes,
.oc-comparison-cost,
.oc-comparison-risk {{
  min-width: 0;
  padding: 11px 14px 13px;
}}
.oc-comparison-quotes,
.oc-comparison-cost {{
  border-right: 1px solid {TOKENS['line']};
}}
.oc-comparison-quotes {{
  background: {TOKENS['chrome']};
}}
.oc-comparison-quotes .oc-quote-grid {{
  grid-template-columns: repeat(auto-fit, minmax(62px, 1fr));
  gap: 5px;
}}
.oc-comparison-quotes .oc-quote-item {{
  padding: 6px 7px;
}}
.oc-comparison-quotes .oc-quote-item strong {{
  font-size: 12.5px;
}}
.oc-comparison-cost .oc-value-pair strong {{
  font-size: 13px;
}}
.oc-comparison-risk .oc-risk-grid {{
  gap: 8px;
}}
.oc-comparison-risk .oc-value-pair strong {{
  font-size: 13px;
}}
.oc-comparison-footer {{
  align-items: center;
  background: #fafbfc;
  border-top: 1px solid {TOKENS['line']};
  color: {TOKENS['dim']};
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 7px 14px;
  font-size: 10.5px;
}}
.oc-comparison-footer strong {{
  color: {TOKENS['chrome_ink']};
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}}
.oc-heatmap-panel {{
  background: {TOKENS['surface']};
  border: 1px solid {TOKENS['line']};
  border-radius: 9px;
  box-shadow: 0 7px 20px rgba(15,18,25,.065);
  margin: 8px 0 18px;
  overflow: hidden;
}}
.oc-heatmap-header {{
  align-items: end;
  display: flex;
  gap: 24px;
  justify-content: space-between;
  padding: 15px 17px 13px;
}}
.oc-heatmap-header h3 {{
  color: {TOKENS['ink']};
  font-size: 17px;
  margin: 3px 0 2px;
}}
.oc-heatmap-header p {{
  color: {TOKENS['dim']};
  font-size: 11.5px;
  line-height: 1.4;
  margin: 0;
}}
.oc-heatmap-legend {{
  color: {TOKENS['dim']};
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 10px;
  white-space: nowrap;
}}
.oc-heatmap-legend span {{
  align-items: center;
  display: inline-flex;
  gap: 4px;
}}
.oc-heatmap-legend i {{
  border: 1px solid rgba(28,31,38,.09);
  border-radius: 3px;
  display: inline-block;
  height: 9px;
  width: 9px;
}}
.oc-legend-loss {{ background: #f4c6c6; }}
.oc-legend-flat {{ background: #ededed; }}
.oc-legend-gain {{ background: #b9dfbf; }}
.oc-heatmap-scroll {{
  border-bottom: 1px solid {TOKENS['line']};
  border-top: 1px solid {TOKENS['line']};
  padding: 10px 12px;
}}
.oc-heatmap-table {{
  min-width: 650px;
  width: 100%;
}}
.oc-heatmap-table th {{
  color: {TOKENS['dim']};
  font-size: 10.5px;
  font-weight: 650;
  text-align: right;
}}
.oc-heatmap-table td {{
  border-bottom: 2px solid {TOKENS['surface']};
  border-right: 2px solid {TOKENS['surface']};
  font-variant-numeric: tabular-nums;
}}
.oc-heatmap-cap-row {{
  box-shadow: inset 0 0 0 999px rgba(231,245,234,.36);
}}
.oc-heatmap-cap-zone {{
  background: #e7f5ea;
  border-radius: 999px;
  color: {TOKENS['pos']};
  display: inline-block;
  font-size: 9.5px;
  font-weight: 700;
  padding: 2px 6px;
  white-space: nowrap;
}}
.oc-cap-boundary {{
  box-shadow: inset 0 2px 0 #72a97e;
}}
.oc-heatmap-caption {{
  color: {TOKENS['dim']};
  font-size: 10.5px;
  line-height: 1.45;
  padding: 10px 17px 12px;
}}
.oc-heatmap-caption p {{
  margin: 0;
}}
.oc-heatmap-cap-note {{
  border: 1px solid #cde6d3;
  border-radius: 7px;
  display: grid;
  gap: 2px 12px;
  grid-template-columns: auto auto minmax(160px, 1fr);
  margin-top: 9px;
  padding: 9px 11px;
}}
.oc-heatmap-cap-note strong {{
  font-size: 13px;
}}
.oc-heatmap-cap-note small {{
  align-self: center;
}}
@media (max-width: 760px) {{
  .oc-candidate-header {{
    align-items: start;
    gap: 12px;
    padding: 15px;
  }}
  .oc-candidate-header p {{
    white-space: normal;
  }}
  .oc-candidate-return {{
    min-width: 92px;
  }}
  .oc-candidate-return strong {{
    font-size: 22px;
  }}
  .oc-candidate-quotes {{
    padding: 11px 15px 13px;
  }}
  .oc-quote-grid {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}
  .oc-candidate-fundamentals {{
    grid-template-columns: 1fr;
  }}
  .oc-candidate-cost {{
    border-bottom: 1px solid {TOKENS['line']};
    border-right: 0;
  }}
  .oc-candidate-cost,
  .oc-candidate-risk {{
    padding: 13px 15px;
  }}
  .oc-spread-cap {{
    border-left: 0;
    border-top: 1px solid #cde6d3;
    padding: 12px 15px;
  }}
  .oc-comparison-board-header {{
    align-items: start;
    display: block;
  }}
  .oc-comparison-board-header p {{
    margin-top: 5px;
    text-align: left;
  }}
  .oc-comparison-row-header {{
    align-items: start;
    gap: 10px;
  }}
  .oc-comparison-return {{
    min-width: 82px;
  }}
  .oc-comparison-grid {{
    grid-template-columns: 1fr;
  }}
  .oc-comparison-quotes,
  .oc-comparison-cost {{
    border-bottom: 1px solid {TOKENS['line']};
    border-right: 0;
  }}
  .oc-comparison-quotes .oc-quote-grid {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}
  .oc-comparison-risk .oc-risk-grid {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}
  .oc-heatmap-header {{
    align-items: start;
    display: block;
  }}
  .oc-heatmap-legend {{
    margin-top: 9px;
  }}
  .oc-heatmap-scroll {{
    padding: 8px;
  }}
  .oc-heatmap-caption {{
    padding: 10px 12px;
  }}
  .oc-heatmap-cap-note {{
    grid-template-columns: 1fr;
  }}
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


def product_header_html() -> str:
    """Return the product-owned shell header; never includes Artifact chrome."""
    return (
        '<header class="oc-product-header" aria-label="Option Chaser">'
        '<div class="oc-brand-lockup">'
        '<span class="oc-brand-mark" aria-hidden="true">OC</span>'
        '<div><div class="oc-brand-name">Option Chaser</div>'
        '<div class="oc-brand-subtitle">選擇權劇本分析</div></div>'
        '</div>'
        '<div class="oc-brand-context">劇本 · 候選 · 情境</div>'
        '</header>'
    )


def inject() -> None:
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
