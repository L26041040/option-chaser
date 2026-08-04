#!/usr/bin/env python
"""重產 API 契約樣本（V1／#48）。

`contracts/analysis_sample.json` 是**前端 mock 與後端 fixture 共用的
同一份樣本**（spec #47 裁示），用來防止兩邊契約漂移：
- 後端：`tests/test_api_analyze.py` 斷言 API 實際回應等於這份樣本
- 前端：元件測試與 E2E 直接載入這份樣本當 mock 回應

契約變動時跑一次本腳本重產，然後確認前端跟著更新：

    PYTHONPATH=. .venv/bin/python scripts/gen_contract_sample.py
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser.data.snapshot import load_snapshot

FIXTURE = Path("tests/fixtures/xyz_v4_six_expiries.json")
OUT = Path("contracts/analysis_sample.json")
# V3（#51）：劇本清單列的形狀。前端四處 fixture 與 E2E 都吃這一份，
# 後端改欄位而沒重產樣本 → `test_scenario_row_sample_matches...` 先紅。
ROW_OUT = Path("contracts/scenario_row_sample.json")
# 目標月選 2026-09：該 fixture 在 2026-08 的 baseline 期恰好零合格候選
# （買賣價差超標被濾光），不適合當骨架樣本——樣本要代表正常情況。
REQUEST = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
           "strategies": ["bull-call-spread"]}
SCENARIO = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09"}

# 隨執行時間變動的欄位換成固定值：樣本要釘住形狀，不是當下的鐘。
FROZEN = {"id": "sample-id", "created_at": "2026-08-01T00:00:00+00:00",
          "days_to_anchor": 653}


def freeze_row(row: dict) -> dict:
    return {**row, **FROZEN}


def main() -> None:
    snap = load_snapshot(FIXTURE)
    client = TestClient(create_app(fetch=lambda symbol: snap))
    resp = client.post("/api/analyze", json=REQUEST)
    resp.raise_for_status()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(resp.json(), ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {OUT}（{OUT.stat().st_size:,} bytes）")

    # 劇本清單列：建立一個劇本並跑一次分析，取清單的第一列當樣本。
    # 時間相關欄位（created_at／latest_analyzed_at／days_to_anchor）會隨
    # 執行時間變動，換成固定值——樣本要釘住的是**形狀**，不是當下的鐘。
    row_client = TestClient(create_app(fetch=lambda symbol: snap,
                                       storage=MemoryStorage()))
    created = row_client.post("/api/scenarios", json=SCENARIO).json()
    row_client.post(f"/api/scenarios/{created['id']}/analyze").raise_for_status()
    row = row_client.get("/api/scenarios").json()[0]
    ROW_OUT.write_text(json.dumps(freeze_row(row), ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {ROW_OUT}")


if __name__ == "__main__":
    main()
