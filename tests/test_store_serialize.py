# tests/test_store_serialize.py
"""v5 spec §3 + §7.4: 全欄位 round-trip、逐位元決定性、pct 兩態、
capital/max_loss/days 手算、data_quality 兩態、版本欄位。"""
import json
from datetime import date
from pathlib import Path

import option_chaser
from option_chaser import store
from option_chaser import service
from option_chaser.models import AnalysisParams

FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _result(strategies=("long-call", "bull-call-spread")):
    return service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategies[0],
                                       target_price=120.0,
                                       target_month="2026-08"),
            strategies=strategies),
        FIX)


def test_top_level_fields_and_versions():
    view = store.serialize_result(_result(), "XYZ-120-202608", 100000.0)
    assert view["schema_version"] == 1
    assert view["engine_version"] == option_chaser.__version__ == "0.5.0"
    assert view["scenario_id"] == "XYZ-120-202608"
    assert view["analyzed_at"] == view["snapshot_ref"]["fetched_at"]
    assert view["capital_assumed"] == 100000.0
    assert view["data_quality"]["all_quotes_filtered"] is False
    assert view["params"]["target_price"] == 120.0
    assert view["today"] == _result().today.isoformat()
    assert view["meta"]["target_move"] == _result().meta.target_move
    assert isinstance(view["default_selection"], list)
    json.dumps(view)   # 全結構可 JSON 化


def test_candidate_fields_hand_checked():
    result = _result(("long-call",))
    view = store.serialize_result(result, "S", 100000.0)
    res0 = view["results"][0]
    assert res0["strategy"] == "long-call" and res0["status"] == "ok"
    cand = res0["candidates"][0]
    cv = result.results[0].candidates[0]
    v = cv.valuation
    assert cand["candidate_key"] == service.candidate_key(cv)
    assert cand["mid_cost"] == v.mid
    # T12（附錄 A14.2）：資本／最大虧損以最差成交成本（單腿＝Ask）計
    assert cand["natural_cost"] == v.contract.ask
    assert cand["capital_per_contract"] == v.contract.ask * 100
    assert cand["max_loss_per_contract"] == v.contract.ask * 100  # debit 恆等於成本
    assert cand["pct_of_capital"] == (v.contract.ask * 100) / 100000.0
    today = result.today
    # 參考日＝日曆錨點（2026-08 的第三個星期五），不是任何被發明出來的目標日
    assert cand["days_to_target"] == (
        result.request.base_params.anchor - today).days
    assert result.request.base_params.anchor == date(2026, 8, 21)
    assert cand["days_to_expiry"] == (
        date.fromisoformat(v.contract.expiry) - today).days
    assert cand["legs"][0]["strike"] == v.contract.strike
    assert cand["legs"][0]["iv"] == v.contract.implied_volatility
    assert cand["scenario_vector"]["worst_code"] == cv.scenario.worst_code
    assert cand["max_profit"] is None                            # long-call
    assert cand["net_delta"] == v.delta
    assert cand["matrix"]["cells"] == [list(r) for r in cv.matrix.cells]


def test_spread_legs_order_and_max_profit():
    result = _result(("bull-call-spread",))
    view = store.serialize_result(result, "S", None)
    cand = view["results"][0]["candidates"][0]
    sv = result.results[0].candidates[0].valuation
    assert cand["legs"][0]["strike"] == sv.long_leg.strike    # [0]=long
    assert cand["legs"][1]["strike"] == sv.short_leg.strike   # [1]=short
    assert cand["mid_cost"] == sv.net_mid
    assert cand["max_profit"] == sv.max_profit
    assert cand["net_delta"] == sv.net_delta


def test_pct_null_without_capital():
    view = store.serialize_result(_result(), "S", None)
    assert view["capital_assumed"] is None
    for res in view["results"]:
        for cand in res["candidates"]:
            assert cand["pct_of_capital"] is None


def test_byte_determinism(tmp_path):
    r = _result()
    a = store.serialize_result(r, "S", 100000.0)
    b = store.serialize_result(r, "S", 100000.0)
    dump = lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True)
    assert dump(a).encode("utf-8") == dump(b).encode("utf-8")
    p1 = store.save_result(tmp_path, "S", a)
    (tmp_path / "results" / "S2").mkdir(parents=True)
    p2 = Path(str(p1).replace("S", "S2", 1))
    store.save_result(tmp_path, "S2", b)
    assert p1.read_bytes() == p2.read_bytes()


def test_save_result_filename_windows_safe(tmp_path):
    view = store.serialize_result(_result(), "S", None)
    path = store.save_result(tmp_path, "S", view)
    expected_ts = view["snapshot_ref"]["fetched_at"].replace(":", "")
    assert path.name == f"{expected_ts}.json"
    assert ":" not in path.name
    assert store.latest_result_path(tmp_path, "S") == path
    assert store.load_result(path) == json.loads(
        path.read_text(encoding="utf-8"))


def test_latest_result_path_none_when_empty(tmp_path):
    assert store.latest_result_path(tmp_path, "NOPE") is None


def test_data_quality_all_quotes_filtered(tmp_path):
    """兩態：正常 False；全部合約 bid/ask=0 → 每策略 empty 且報價異常 removed>=1 → True。"""
    src = json.loads(Path("tests/fixtures/xyz_v4_all_warning.json")
                     .read_text(encoding="utf-8"))
    for c in src["contracts"]:
        c["bid"] = 0.0
        c["ask"] = 0.0
    bad = tmp_path / "all_zero.json"
    bad.write_text(json.dumps(src), encoding="utf-8")
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="long-call",
                                       target_price=120.0,
                                       target_month="2026-08"),
            strategies=("long-call", "bull-call-spread")),
        str(bad))
    view = store.serialize_result(result, "S", None)
    assert all(r["status"] == "empty" for r in view["results"])
    assert view["data_quality"]["all_quotes_filtered"] is True
