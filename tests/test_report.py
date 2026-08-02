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
                       "不漲保留率: ", "Bid-Ask Spread: "]:
            assert needle in text, (res.strategy, needle)
        assert "/股）" in text, "friction absolute amount must be shown (spec §2.3)"
        # T12（附錄 A14.2）：主數字改最差口徑後，原「Natural 成交報酬」列
        # 與基準情境列重合，已合併移除。
        assert "Natural 成交報酬" not in text
        assert "成本口徑" in text
