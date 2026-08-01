"""T5（#19）／需求五: 卡片收益率的著色規則（純字串函式）。"""
import pytest

pytest.importorskip("streamlit")

from webapp.render import return_md


def test_positive_return_is_green():
    assert return_md(5.204) == ":green[+520.4%]"


def test_negative_return_is_red():
    assert return_md(-0.317) == ":red[-31.7%]"


def test_missing_return_is_a_dash():
    """尚無成功快照／該次零候選（附錄 A8.1、A10.2）。"""
    assert return_md(None) == "—"


def test_flat_return_is_not_coloured():
    assert return_md(0.0) == "+0.0%"
