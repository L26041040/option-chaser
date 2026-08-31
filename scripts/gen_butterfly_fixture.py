#!/usr/bin/env python
"""產生 Butterfly 專用測試快照（T15／#230，Initial V2 spec #217）。

既有 fixture（`xyz_v2_snapshot.json`／`xyz_v4_six_expiries.json`）的
履約價梯子稀疏、且不對稱配置，湊出來的 3-履約價組合多半是嚴重
broken-wing（例如唯一可行的低/中/高＝95/105/130，寬度 10 vs 25），
在合理的目標價下算出來的最佳候選 `max_profit` 恆為負值——數學上正確
（見 `valuation.evaluate_butterfly` 的邊界案例測試），但不適合當
「代表正常情況」的契約樣本（沿用 `gen_contract_sample.py` 既有的
選樣原則：樣本要能展示這個新結構真正被期待呈現的樣子，例如一個
真正存在的獲利區間）。

本腳本用 BS93 定價出一組**對稱、密集**的履約價梯子（call／put 各
25 檔，5 個到期日），讓窮舉出的組合裡有大量對稱蝴蝶（寬度相等），
足以在合理目標價下產生正的 `max_profit`／非空 `profit_region`；密度
也足以驗證 T15 AC 的枚舉效能量級（單一到期日 C(25,3)=2300 組，五個
到期日合計約 11,500 組，量級對齊 wayfinder 地圖 #216 的枚舉估計）。

報價本身用 `option_chaser.valuation.american_price()`（production
定價函式本身）算出理論價，加一個小而不對稱的 bid/ask 價差（相對價差
隨到期日與價外程度些微放大，貼近真實市場「近月價平價差窄、遠月價外
價差寬」的形狀，但**不精確擬合任何真實報價**，純粹是為了讓過濾器與
品質標示邏輯有東西可以動作，不是要重現任何特定標的）——這是合成
fixture，不是真實市場資料快照，命名與既有慣例（v2／v4／v5 皆為合成
或半合成）一致。

    PYTHONPATH=. .venv/bin/python scripts/gen_butterfly_fixture.py
"""
import json
from datetime import date
from pathlib import Path

from option_chaser.data.snapshot import save_snapshot
from option_chaser.models import ChainSnapshot, OptionContract, SCHEMA_VERSION
from option_chaser.valuation import american_price

OUT = Path("tests/fixtures/xyz_v6_butterfly_ladder.json")
# 契約樣本／多數單元測試用的**中密度**版本——履約價梯子縮到 11 檔、
# 到期日縮到 3 個（`C(11,3)=165` 組×3＝495 組候選，`all_candidates`
# 歷史五欄位序列因此是幾百筆而非近萬筆）。密集版（`OUT`）只給效能
# 測試（`tests/test_butterfly_performance.py`）驗證枚舉/估值量級，
# 兩者刻意分開，不共用同一份——密集版拿去產契約樣本會生出 2MB+ 的
# JSON（`all_candidates` 近萬筆歷史序列撐大的，不是候選池本身）。
MODERATE_OUT = Path("tests/fixtures/xyz_v7_butterfly_moderate.json")

SPOT = 100.0
TODAY = date(2026, 7, 15)
EXPIRIES = ["2026-08-21", "2026-09-18", "2026-10-16", "2026-12-18", "2027-01-15"]
STRIKES = [round(60.0 + 4.0 * i, 1) for i in range(26)]  # 60..160，25 檔間距 4
MODERATE_EXPIRIES = ["2026-09-18", "2026-10-16", "2026-12-18"]
MODERATE_STRIKES = [round(85.0 + 3.0 * i, 1) for i in range(11)]  # 85..115
R, Q, SIGMA = 0.04, 0.0, 0.28


def _quote(option_type: str, strike: float, expiry: str, idx: int) -> OptionContract:
    T = (date.fromisoformat(expiry) - TODAY).days / 365.0
    theo = american_price(option_type, SPOT, strike, T, R, Q, SIGMA)
    # 相對價差：近月價平窄、遠月/深價外寬——純粹讓後續過濾/品質標示
    # 邏輯有真實可動作的變異，不代表任何真實市場觀察。
    moneyness = abs(strike - SPOT) / SPOT
    rel_spread = 0.02 + 0.03 * moneyness + 0.01 * T
    half = max(0.02, theo * rel_spread / 2.0)
    bid = round(max(0.01, theo - half), 2)
    ask = round(theo + half, 2)
    iv = SIGMA + 0.05 * moneyness * (1 if option_type == "call" else -1)
    return OptionContract(
        contract_symbol=f"XYZ{expiry.replace('-', '')}{option_type[0].upper()}{idx:03d}",
        option_type=option_type, strike=strike, expiry=expiry,
        bid=bid, ask=ask, last=round((bid + ask) / 2, 2),
        volume=10 + idx, open_interest=100 + idx * 3,
        implied_volatility=round(max(0.05, iv), 4),
    )


def _build(expiries: list[str], strikes: list[float]) -> ChainSnapshot:
    contracts = []
    idx = 0
    for expiry in expiries:
        for strike in strikes:
            for option_type in ("call", "put"):
                contracts.append(_quote(option_type, strike, expiry, idx))
                idx += 1
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol="XYZ",
        fetched_at="2026-07-15T21:30:00-04:00", spot=SPOT,
        source="synthetic-butterfly-fixture", contracts=tuple(contracts))


def main() -> None:
    dense = _build(EXPIRIES, STRIKES)
    OUT.parent.mkdir(exist_ok=True)
    save_snapshot(dense, OUT)
    print(f"寫入 {OUT}（{len(dense.contracts)} 張合約，"
         f"{OUT.stat().st_size / 1024:.1f} KB）")

    moderate = _build(MODERATE_EXPIRIES, MODERATE_STRIKES)
    save_snapshot(moderate, MODERATE_OUT)
    print(f"寫入 {MODERATE_OUT}（{len(moderate.contracts)} 張合約，"
         f"{MODERATE_OUT.stat().st_size / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
