#!/usr/bin/env python
"""重產既有四策略的數值 bitwise 基準（T01／#218，spec #217 §Q-A）。

`tests/fixtures/valuation_numeric_baseline.json` 凍結 `long-call`／
`long-put`／`bull-call-spread`／`bear-put-spread` 四個既有策略在固定
fixture（`tests/fixtures/xyz_v2_snapshot.json`）上的**估值輸出**：
劇本報酬、包絡量、情境向量、heatmap 格值、完成度、Greeks 比率、
Crossover comparator 等（完整欄位清單見
`tests/test_selection_regression.py::NUMERIC_BASELINE_FIELDS`）。

Initial V2 的 T02（逐腿 payoff 直算）與 T03（包絡量由 payoff 導出）
要換掉估值核心，唯一的驗收判準是**畫面零變化**——這份基準就是那個
「零變化」的可執行證明。

**什麼時候可以重跑這支腳本**：只有在數字**確定是刻意改變**的時候，
而且要跟需求方確認過。已知的合法時機只有一個：T04（#220）把 friction
自 canonical model 移除（#217 決策 D）。T02／T03 期間跑出差異＝有 bug，
不是基準過期。

    PYTHONPATH=. .venv/bin/python scripts/gen_numeric_baseline.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 快照與比對邏輯的單一來源就是守門測試本身——這裡刻意不複製一份，
# 否則基準與守門會各自漂移。
sys.path.insert(0, str(ROOT / "tests"))

from test_selection_regression import (  # noqa: E402
    SCENARIOS, SNAP, _NUMERIC_BASELINE_PATH, snapshot_numbers,
)

OUT = ROOT / _NUMERIC_BASELINE_PATH


def main() -> None:
    payload = {
        "_about": (
            "既有四策略的數值 bitwise 基準（T01／#218）。由 "
            "scripts/gen_numeric_baseline.py 產生，勿手改。"
            "重產條件見該腳本 docstring。"),
        "fixture": SNAP,
        "strategies": {s: snapshot_numbers(s) for s in sorted(SCENARIOS)},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    n = sum(len(v["candidates"]) for v in payload["strategies"].values())
    print(f"寫入 {OUT}（{len(payload['strategies'])} 個策略、{n} 個候選、"
          f"{OUT.stat().st_size / 1024:.1f} KB）")


if __name__ == "__main__":
    main()
