from pathlib import Path


def test_glossary_importable_without_streamlit():
    src = Path("option_chaser/glossary.py").read_text(encoding="utf-8")
    assert "streamlit" not in src

    import option_chaser.glossary as g
    assert len(g.GLOSSARY) >= 16
    required = ["劇本報酬", "情境最壞", "成交摩擦",
                "完成度門檻", "不漲保留率", "到期緩衝", "保本價", "Mid",
                "Natural", "BCS", "BPS", "Delta", "Theta", "Vega", "IV"]
    for term in required:
        assert term in g.GLOSSARY
