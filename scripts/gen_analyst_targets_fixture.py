#!/usr/bin/env python
"""重產分析師目標價測試資料 `tests/fixtures/analyst_targets_fixture.json`（OS-03／#392）。

**這是測試資料，非真實市場資料。** ticker 刻意用不存在的 AAA…GGG，
不借用任何真實公司代號，避免假數字被誤認成真實結果。只給
`api_app.analyst_source.FixtureAnalystSource` 讀，只在測試與本機驗證
腳本裡注入。

以評估日 2026-09-28（`tests/_frozen_clock.FROZEN_NY_TODAY`）設計，
在暫定資料品質規則（`option_chaser.consensus.ConsensusRules()` 預設值）
下每檔的預期結果：

| symbol | 情境 | 預期 |
|---|---|---|
| AAA | 兩關都過 | ok；percentile 6/44；dispersion ≈ 9.0% |
| BBB | 只過第一關 | ok；percentile 0；dispersion ≈ 15.1%（> 10%） |
| CCC | 只過第二關 | ok；percentile 1；dispersion ≈ 7.6% |
| DDD | 分析師不足 | insufficient_analysts（只有 3 位） |
| EEE | 有 4:1 分割（附分割事件） | ok；兩關都過 |
| FFF | 來源只有共識值、沒有個別目標價 | no_data |
| GGG | 來源回報錯誤 | 上游失敗（source_error） |

目前股價（V2-05／#407，`quote`：股票掃描階段取得的報價與時間）：

| symbol | 報價 | 預期目標漲跌幅 |
|---|---|---|
| AAA | 100.00（2026-09-25 收盤） | +20.0% |
| BBB | 110.00（2026-09-25 收盤） | −9.1% |
| CCC | 100.00（2026-09-25 收盤） | 0.0% |
| DDD | 100.00（2026-09-21 收盤，距 09-28 已 5 個交易日） | 股價過舊 |
| EEE | 440.00（2025-05-30 收盤，4:1 分割 2025-06-02 之前） | 分割基準不一致 |
| FFF | 150.00（2026-09-25 收盤） | 沒有平均目標價 |
| GGG | 無（來源失敗） | 尚未取得股價 |

每位分析師每半年（1 月、7 月）更新一次，2026-09 全體再更新一次（＝
「今天」的共識）。目標價 = base + offset × step，offset 為 −3…+3，
因此樣本標準差 = step × √(28/6)、分歧度 = 該值 ÷ base。

    PYTHONPATH=. .venv/bin/python scripts/gen_analyst_targets_fixture.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OUT = Path("tests/fixtures/analyst_targets_fixture.json")
FIRMS = ["Fixture Alpha", "Fixture Beta", "Fixture Gamma", "Fixture Delta",
         "Fixture Epsilon", "Fixture Zeta", "Fixture Eta"]
OFFSETS = [-3, -2, -1, 0, 1, 2, 3]
# 半年期：2023-01 … 2026-07（共 8 期），之後 2026-09 是「今天」的那一輪。
PERIODS = [(y, m) for y in (2023, 2024, 2025, 2026) for m in (1, 7)]


def _price(x: float) -> str:
    return f"{x:.2f}"


def _records(symbol, *, hist, today, analysts=7, split=None):
    """hist：每一期的 (base, step)；today：(base, step)；split：
    (effective_on, ratio)——生效日前發布的價格乘上 ratio（原始未調整值）。"""
    out = []
    for k in range(analysts):
        for i, (y, m) in enumerate(PERIODS):
            base, step = hist[i]
            published = date(y, m, 5 + k)
            price = base + OFFSETS[k] * step
            if split and published < split[0]:
                price *= split[1]
            out.append({"analyst_key": FIRMS[k], "firm": FIRMS[k],
                        "target_price": _price(price),
                        "published_on": published.isoformat(),
                        "action": "maintain"})
        base, step = today
        out.append({"analyst_key": FIRMS[k], "firm": FIRMS[k],
                    "target_price": _price(base + OFFSETS[k] * step),
                    "published_on": date(2026, 9, 1 + k).isoformat(),
                    "action": "raise"})
    return out


def _quote(price: str, on: str) -> dict:
    """美東 16:00:01（夏令時間＝20:00:01 UTC）的收盤報價。"""
    return {"price": price, "at": f"{on}T20:00:01+00:00"}


def main() -> None:
    wide = [(100, 6)] * 8
    aaa_hist = list(wide)
    aaa_hist[2] = (100, 4)   # 2024 上半年分歧度較低 → 6 個月底點低於今天
    symbols = {
        "AAA": {"coverage": "partial", "history_from": "2023-01-05",
                "records": _records("AAA", hist=aaa_hist, today=(120, 5)),
                "splits": []},
        "BBB": {"coverage": "unknown", "history_from": "2023-01-05",
                "records": _records("BBB", hist=[(100, 10)] * 8, today=(100, 7)),
                "splits": []},
        "CCC": {"coverage": "complete", "history_from": "2023-01-05",
                "records": _records("CCC", hist=[(100, 1.5)] * 8, today=(100, 3.5)),
                "splits": []},
        "DDD": {"coverage": "unknown", "history_from": "2023-01-05",
                "records": _records("DDD", hist=wide, today=(100, 3), analysts=3),
                "splits": []},
        "EEE": {"coverage": "partial", "history_from": "2023-01-05",
                "records": _records("EEE", hist=wide, today=(110, 4),
                                    split=(date(2025, 6, 2), 4)),
                "splits": [{"effective_on": "2025-06-02", "ratio": "4"}]},
        "FFF": {"coverage": "unknown", "records": [], "splits": [],
                "cross_check": {"consensus_mean_from_source": "150.00",
                                "n_from_source": 12}},
        "GGG": {"coverage": "unknown", "records": [], "splits": [],
                "error": "逾時（測試資料模擬上游失敗）"},
    }
    quotes = {"AAA": _quote("100.00", "2026-09-25"),
              "BBB": _quote("110.00", "2026-09-25"),
              "CCC": _quote("100.00", "2026-09-25"),
              "DDD": _quote("100.00", "2026-09-21"),
              "EEE": _quote("440.00", "2025-05-30"),
              "FFF": _quote("150.00", "2026-09-25")}
    for symbol, quote in quotes.items():
        symbols[symbol]["quote"] = quote
    doc = {"name": "fixture",
           "notice": "測試資料，非真實市場資料（OS-03／#392）；由 "
                     "scripts/gen_analyst_targets_fixture.py 產生",
           "symbols": symbols}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
