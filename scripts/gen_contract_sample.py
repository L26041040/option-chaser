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
from option_chaser.data.snapshot import load_snapshot

FIXTURE = Path("tests/fixtures/xyz_v4_six_expiries.json")
OUT = Path("contracts/analysis_sample.json")
# 目標月選 2026-09：該 fixture 在 2026-08 的 baseline 期恰好零合格候選
# （買賣價差超標被濾光），不適合當骨架樣本——樣本要代表正常情況。
REQUEST = {"symbol": "XYZ", "target_price": 130.0, "target_month": "2026-09",
           "strategies": ["bull-call-spread"]}


def main() -> None:
    snap = load_snapshot(FIXTURE)
    client = TestClient(create_app(fetch=lambda symbol: snap))
    resp = client.post("/api/analyze", json=REQUEST)
    resp.raise_for_status()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(resp.json(), ensure_ascii=False, indent=2,
                              sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {OUT}（{OUT.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
