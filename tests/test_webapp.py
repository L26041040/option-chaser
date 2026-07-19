from datetime import date
import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

FIX = "tests/fixtures/xyz_v2_snapshot.json"


def _patched(monkeypatch):
    import option_chaser.service as svc
    real_offline = svc.run_offline
    monkeypatch.setattr(
        svc, "run",
        lambda req, progress=None: real_offline(req, FIX, progress))


def _fill_and_submit(at, symbol="XYZ", price=120.0,
                     checks=("long-call", "bull-call-spread")):
    at.text_input(key="symbol").set_value(symbol)
    at.number_input(key="target_price").set_value(price)
    at.date_input(key="target_date").set_value(date(2026, 8, 28))
    for s in ("long-call", "bull-call-spread", "long-put", "bear-put-spread"):
        at.checkbox(key=f"chk-{s}").set_value(s in checks)
    at.run()  # register widget states
    at.button[0].set_value(True).run(timeout=30)
    return at


def test_happy_path_renders_all_sections(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(m.value for m in at.markdown)
    assert "跨策略比較" in " ".join(s.value for s in at.subheader)
    assert "最高報酬" in body
    assert "overflow-x:auto" in body          # heatmap html present
    assert not at.exception


def test_summary_shows_scenario(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    body = " ".join(getattr(x, "value", "") for x in at.markdown) + \
           " ".join(getattr(x, "value", "") for x in at.text)
    assert "劇本" in body and "120" in body and "2026-08-28" in body


def test_direction_mismatch_partial(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, price=80.0,
                          checks=("long-call", "long-put"))
    texts = " ".join(getattr(x, "value", "") for x in at.info) + \
            " ".join(m.value for m in at.markdown)
    assert "未執行" in texts                    # skip message shown
    assert not at.exception


def test_empty_symbol_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, symbol="   ")
    assert any("請輸入標的代號" in e.value for e in at.error)


def test_no_strategy_error(monkeypatch):
    _patched(monkeypatch)
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, checks=())
    assert any("至少勾選一種策略" in e.value for e in at.error)


def test_fetch_error_mappings(monkeypatch):
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 回傳資料不足（XX）：無現價或無合約")))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at, symbol="XX")
    assert any("找不到此標的" in e.value for e in at.error)

    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("yfinance 抓取失敗（XX）: boom")))
    at2 = AppTest.from_file("webapp/app.py")
    at2.run()
    at2 = _fill_and_submit(at2, symbol="XX")
    assert any("請稍後再試" in e.value for e in at2.error)


def test_no_traceback_on_unexpected(monkeypatch):
    import option_chaser.service as svc
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(RuntimeError("boom")))
    at = AppTest.from_file("webapp/app.py")
    at.run()
    at = _fill_and_submit(at)
    assert any("分析過程發生錯誤" in e.value for e in at.error)
    assert not at.exception
