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
                       "不漲保留率: "]:
            assert needle in text, (res.strategy, needle)
        # T04（#220，#217 決策 D）：friction／Bid-Ask Spread 自 canonical
        # model 退場，這一行不再印它——保本門檻／不漲保留率兩項維持不變。
        assert "Bid-Ask Spread" not in text
        # T12（附錄 A14.2）：主數字改最差口徑後，原「Natural 成交報酬」列
        # 與基準情境列重合，已合併移除。
        assert "Natural 成交報酬" not in text
        assert "成本口徑" in text


def test_monotonicity_warning_line_appears_in_the_text_report():
    """FB5-03（#64）：無套利一致性違反在 CLI 純文字報告裡也要說得出來，
    不是只有網頁前端看得到——這份既有 fixture（xyz_v2_snapshot.json）
    剛好自然帶著一組真實違反（XYZC100D vs XYZC102O），端到端跑一次
    `service.run_offline` 就能在報告文字裡看到警示行與尾註說明。"""
    from option_chaser import service
    from option_chaser.models import AnalysisParams
    result = service.run_offline(service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy="long-call", target_price=120.0,
                                   target_month="2026-08", min_return=0.0),
        strategies=("long-call",)),
        "tests/fixtures/xyz_v2_snapshot.json")
    text = result.results[0].report_text
    assert "報價與鄰近履約價不一致，疑似陳舊報價" in text
    assert "無套利一致性" in text
