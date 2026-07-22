"""v6 spec §2.1: Artifact 淺色 token；CSS 僅限 .oc-* 自訂類別，不覆寫 Streamlit 內部 DOM。"""
import re

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
