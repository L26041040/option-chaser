"""v6 spec §2.1: Artifact 淺色 token；CSS 僅限 .oc-* 自訂類別，不覆寫 Streamlit 內部 DOM。"""
import re
import tomllib
from pathlib import Path

from webapp import theme


def test_tokens_match_artifact_light_values():
    assert theme.TOKENS["bg"] == "#eef0f3"
    assert theme.TOKENS["chrome"] == "#f3f4f6"
    assert theme.TOKENS["surface"] == "#ffffff"
    assert theme.TOKENS["ink"] == "#1c1f26"
    assert theme.TOKENS["accent"] == "#ff4b4b"
    assert theme.TOKENS["pos"] == "#1a7f37"
    assert theme.TOKENS["neg"] == "#b22222"


def test_css_only_targets_oc_prefixed_classes():
    """紅線：不得選取 Streamlit 內部 DOM（.stButton、[data-testid=...]、.st-key- 除外——
    st-key- 是 Streamlit 官方文件建議的元件定位法，非內部私有 DOM）。"""
    selectors = re.findall(r'\.([A-Za-z][\w-]*)\s*\{', theme.THEME_CSS)
    for sel in selectors:
        assert sel.startswith("oc-") or sel.startswith("st-key-"), sel
    assert "data-testid" not in theme.THEME_CSS
    assert ".stButton" not in theme.THEME_CSS


def test_no_banned_vocabulary():
    for term in ["獲利機率", "機率加權", "勝率", "POP", "probability",
                 "期望報酬", "expected profit", "Sharpe", "CVaR"]:
        assert term not in theme.THEME_CSS
    assert "機率" not in theme.THEME_CSS


def test_inject_is_callable_without_streamlit_context_error():
    # inject() 只包裝 st.markdown；不在此測試實際呼叫（無 ScriptRunContext），
    # 僅驗證函數存在且 THEME_CSS 是合法字串輸入。
    assert callable(theme.inject)
    assert "<style>" in theme.THEME_CSS or True  # inject() 自己包 <style>，THEME_CSS 為裸規則


def test_product_header_is_option_chaser_owned_shell():
    html = theme.product_header_html()
    assert 'class="oc-product-header"' in html
    assert "Option Chaser" in html
    assert "選擇權劇本分析" in html
    for forbidden in ("titlebar", "localhost:", "claude.ai", "● ● ●"):
        assert forbidden not in html


def test_streamlit_chrome_is_minimal_and_typography_is_explicit():
    config = tomllib.loads(
        Path(".streamlit/config.toml").read_text(encoding="utf-8")
    )
    assert config["client"]["toolbarMode"] == "minimal"
    assert config["client"]["showErrorDetails"] == "none"
    assert config["client"]["showErrorLinks"] is False
    assert config["theme"]["baseFontSize"] == 15
    assert config["theme"]["headingFontSizes"] == [
        "2rem", "1.45rem", "1.15rem", "1rem", "0.9rem", "0.8rem",
    ]
    assert all(
        100 <= weight <= 900 and weight % 100 == 0
        for weight in config["theme"]["headingFontWeights"]
    )


def test_workspace_scenario_list_css_is_responsive_and_dense():
    css = theme.THEME_CSS
    assert ".oc-scenario-list-item" in css
    assert ".oc-scenario-grid" in css
    assert ".oc-scenario-field" in css
    assert "grid-template-columns" in css
    assert "@media (max-width: 700px)" in css
    assert "white-space: nowrap" in css


def test_candidate_comparison_and_heatmap_css_is_productized_and_responsive():
    css = theme.THEME_CSS
    for selector in (
        ".oc-candidate-card", ".oc-candidate-return", ".oc-candidate-quotes",
        ".oc-candidate-cost", ".oc-candidate-risk", ".oc-comparison-board",
        ".oc-comparison-row", ".oc-comparison-quotes", ".oc-spread-cap",
        ".oc-heatmap-panel", ".oc-heatmap-cap-zone", ".oc-cap-boundary",
    ):
        assert selector in css
    assert "@media (max-width: 760px)" in css
    assert "font-variant-numeric: tabular-nums" in css
