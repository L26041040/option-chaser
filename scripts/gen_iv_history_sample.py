#!/usr/bin/env python
"""重產 iv-history 回應的契約樣本（T10／#192）。

比照 `gen_contract_sample.py` 既有的產生與共用方式：`contracts/
iv_history_sample.json` 是一次真實 `GET /api/scenarios/{id}/iv-history`
呼叫的完整回應，用同一份 `xyz_v4_six_expiries.json` fixture 建立劇本、
跑一次分析拿到真實的 Spread 候選（買／賣兩腿都有），解鎖 Historical IV
並注入固定假體（Legacy 家族的曲面網格＋Exact-Contract 家族兩腿各自
40 天的真實可反解報價），因此樣本同時涵蓋：兩腿各自的統計量套組
（moving average／Bollinger／z-score／percentile／Δ4w）、Spread IV Gap、
Normalized Skew（Legacy 家族）——不是空殼或退化態。

契約變動時跑一次本腳本重產：

    PYTHONPATH=. .venv/bin/python scripts/gen_iv_history_sample.py
"""
import dataclasses
import json
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import dividends as dividends_module
from option_chaser import ratecurve as ratecurve_module
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ivhistory import SurfacePoint
from option_chaser.ratecurve import RateCurve
from option_chaser.valuation import DAYS_PER_YEAR, american_price, days_between

FIXTURE = Path("tests/fixtures/xyz_v4_six_expiries.json")
OUT = Path("contracts/iv_history_sample.json")
SCENARIO = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}
PROVIDER = providers.MARKETDATA_APP.id
TOKEN = "mdapp_sample_token_0000"

# 與 `gen_contract_sample.py` 同一份假曲線／假配息——同一套 point-in-time
# r／q 輸入，兩份契約樣本因此描述同一個「世界」，不會互相矛盾。
_RATE_CURVE_ROWS = (("2020-01-01", ((0.1, 0.041), (30.0, 0.044))),)
_DIV = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                       distributions=(DividendRecord("2026-06-01", 1.2),))


def _rate_loader(today):
    return (RateCurve(curve_date="2026-07-31",
                      nodes=((0.5, 0.041), (1.0, 0.042),
                             (2.0, 0.043), (3.0, 0.044))),
           "Treasury 曲線 2026-07-31")


def _dividend_loader(symbol, today):
    return _DIV, "配息資料 yahoo（2026-07-14，1 筆）"


def _rate_curve_rows(from_date, to_date):
    return _RATE_CURVE_ROWS


def _synthetic_quote(date_str, *, option_type, strike, expiration, spot, sigma):
    """一筆會在正式 reconstruction 路徑精確反解回 `sigma` 的 quote dict
    ——與 `tests/test_api_iv_history.py::_synthetic_quote` 同一個做法
    （同一套 `_RATE_CURVE_ROWS`／`_DIV` 假體、同一條 point-in-time 查表
    路徑），這裡獨立一份避免樣本腳本依賴測試檔案。"""
    T = days_between(date.fromisoformat(date_str),
                     date.fromisoformat(expiration)) / DAYS_PER_YEAR
    curve = ratecurve_module.curve_asof(_RATE_CURVE_ROWS, date_str)
    r = ratecurve_module.rate_for_tenor(curve, T)
    q = dividends_module.compute_q_asof(
        _DIV, spot=spot, observation_date=date.fromisoformat(date_str))
    price = american_price(option_type, spot, strike, T, r, q, sigma)
    bid = max(price / 2.0, 1e-8)
    ask = max(price * 1.5, 1e-6)
    return {"date": date_str, "updated": 1, "dte": None,
           "bid": bid, "ask": ask, "mid": price,
           "underlying_price": spot, "vendor_iv": None}


def _grid():
    """跟 `tests/test_api_iv_history.py::_grid()` 同一種「蓋得夠寬、
    任何合理座標都插得出來」的 Legacy 家族曲面。"""
    pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d)
           for dte in (1, 30, 90, 365, 1200)
           for d in (0.0001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.9999)]
    return {"call": pts, "put": pts}


def _historical_surface(*_args, **_kwargs):
    return _grid()


def _leg_history(*, option_type, strike, expiration, spot):
    """60 個日曆天回溯、只灌交易日、每天 IV 緩慢漂移——真實序列才撐得出
    有意義的 moving average／Bollinger／z-score／percentile／Δ4w，不是
    退化成單點或空序列。錨點用**今天**回溯（不是到期日回溯）：Δ4w 的
    基準窗是 [today-42, today-21]，序列得真的涵蓋這段才有值可看，樣本
    才能示範完整欄位集合，不是留白。"""
    start = date.today() - timedelta(days=60)
    out = []
    d = start
    n = 0
    while d <= date.today():
        if d.weekday() < 5:   # 只灌交易日，跟真實資料一樣有週末空窗
            sigma = 0.22 + 0.001 * n
            out.append(_synthetic_quote(
                d.isoformat(), option_type=option_type, strike=strike,
                expiration=expiration, spot=spot, sigma=sigma))
            n += 1
        d += timedelta(days=1)
    return out


def main() -> None:
    snap = load_snapshot(FIXTURE)
    db = MemoryStorage()
    client = TestClient(create_app(
        storage=db, fetch=lambda s: snap,
        rate_loader=_rate_loader, dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=_historical_surface,
        contract_history=lambda *a, **kw: [],  # 逐腿假體另外掛，見下方
        rate_curve_rows=_rate_curve_rows))

    created = client.post("/api/scenarios", json=SCENARIO).json()
    sid = created["id"]
    client.post(f"/api/scenarios/{sid}/refresh").raise_for_status()
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    key = None
    for r in view["results"]:
        for group in r.get("expiry_top10") or []:
            if group["candidate_keys"]:
                key = group["candidate_keys"][0]
                break
        if key:
            break
    if key is None:
        raise SystemExit("樣本 fixture 沒有產生任何候選，無法產生 iv-history 樣本")
    cand = view["candidate_pool"][key]
    buy, sell = cand["legs"][0], cand["legs"][1]

    points_by_symbol = {
        buy["contract_symbol"]: _leg_history(
            option_type=buy["option_type"], strike=buy["strike"],
            expiration=buy["expiry"], spot=view["meta"]["spot"]),
        sell["contract_symbol"]: _leg_history(
            option_type=sell["option_type"], strike=sell["strike"],
            expiration=sell["expiry"], spot=view["meta"]["spot"]),
    }

    def _contract_history(provider, occ_symbol, from_date, to_date, token,
                          observer=None):
        return points_by_symbol.get(occ_symbol, [])

    client_with_legs = TestClient(create_app(
        storage=db, fetch=lambda s: snap,
        rate_loader=_rate_loader, dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=_historical_surface,
        contract_history=_contract_history,
        rate_curve_rows=_rate_curve_rows))
    client_with_legs.put("/api/settings", json={
        "market_data": {"mode": "default", "provider": None},
        "historical_iv": {"mode": "custom", "provider": PROVIDER}})
    client_with_legs.put(f"/api/settings/credentials/{PROVIDER}",
                         json={"token": TOKEN})
    client_with_legs.post(f"/api/settings/credentials/{PROVIDER}/test")

    resp = client_with_legs.get(f"/api/scenarios/{sid}/iv-history",
                                params={"candidate_key": key})
    resp.raise_for_status()
    payload = resp.json()
    # correlation id 每次執行都不同（DG-02／#145，隨機 UUID）——樣本要
    # 釘住的是形狀，換成固定值，跟 `gen_contract_sample.py` 的 FROZEN
    # 欄位處理同一個道理。
    payload["diagnostics"]["correlation_id"] = "sample-correlation-id"

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {OUT}（{OUT.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
