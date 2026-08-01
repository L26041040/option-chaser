# tests/test_report.py
"""v4: CLI report resilience section (spec §5)."""


def test_resilience_section_present_and_formatted():
    from option_chaser import service
    from option_chaser.models import AnalysisParams
    result = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call", "bull-call-spread")),
        "tests/fixtures/xyz_v2_snapshot.json")
    ok = [r for r in result.results if r.status == "ok"]
    assert ok, "fixture must yield ok results (non-vacuous guard)"
    for res in ok:
        text = res.report_text
        for needle in ["韌性向量（7 情境，Mid 口徑）:", "- S1 不漲: ",
                       "◀ 情境最壞", "劇本完成度: ", "保本門檻: ",
                       "不漲保留率: ", "成交摩擦: "]:
            assert needle in text, (res.strategy, needle)
        assert "/股）" in text, "friction absolute amount must be shown (spec §2.3)"
        assert "最差進場（Ask）基準報酬率" not in text
        if res.strategy == "long-call":
            assert "Natural 成交報酬" in text
