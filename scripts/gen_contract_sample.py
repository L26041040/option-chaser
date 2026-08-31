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
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ratecurve import RateCurve

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

# #115（spec #117 §4）：Crossover comparator 需要「每個策略各一個範例，
# call／put comparator 都有覆蓋」。單一 `/api/analyze` 呼叫只能吃一個
# target_price，方向（bull/bear）互斥（`_analyze` 的 mismatch 判斷：
# 同一個 target_price 不可能同時大於與小於 spot），且 `force` 沒有
# 暴露在 `/api/analyze` 的公開 schema 上（刻意——不為了產樣本而擴大
# production API 面）。因此 put 覆蓋走**獨立**的第二份樣本，不是硬湊
# 進主樣本：獨立 fixture（`xyz_v5_put_ladder.json`，鏡射既有
# `xyz_v4_six_expiries.json` 的 call 梯，履約價鏡射到 spot 另一側）＋
# 獨立 target_price（低於 spot，方向天然成立、不需要 force）。
PUT_FIXTURE = Path("tests/fixtures/xyz_v5_put_ladder.json")
PUT_OUT = Path("contracts/analysis_sample_bear_put.json")
PUT_REQUEST = {"symbol": "XYZ", "target_price": 70.0, "target_month": "2026-09",
               "strategies": ["bear-put-spread"]}

# T09（#222）：單腿到期日分組（`expiry_top10`／`expiry_ranked`）的契約
# 樣本——同一份主 fixture、同一個 target_price（bullish，long-call 天生
# 方向相容），走**獨立**的第三份樣本而不是硬湊進主樣本，理由與上面 put
# 樣本相同：主樣本已被前端 mock／E2E 大量引用，混進第二個策略會改變它的
# 既有形狀（`results` 從一筆變兩筆），這份樣本存在的唯一理由是示範單腿
# 到期日分組，不需要也不該牽動主樣本。
LONG_CALL_OUT = Path("contracts/analysis_sample_long_call.json")
LONG_CALL_REQUEST = {"symbol": "XYZ", "target_price": 130.0,
                     "target_month": "2026-09", "strategies": ["long-call"]}

# 隨執行時間變動的欄位換成固定值：樣本要釘住形狀，不是當下的鐘。
FROZEN = {"id": "sample-id", "created_at": "2026-08-01T00:00:00+00:00",
          "days_to_anchor": 653}

# 利率（#67）：`create_app()` 現在預設接真的 Treasury loader，樣本產生
# script 若沿用預設會在沙箱（無網路）裡打出「曲線不可得」，而且結果隨
# 執行環境的連線能力變動——樣本要釘住的是形狀，注入一個固定的假曲線，
# 代表「期限對齊成功」這個較豐富、較有代表性的狀態（而不是失敗態的
# 空 `rate_by_expiry`）。
SAMPLE_RATE_CURVE = RateCurve(curve_date="2026-07-31",
                              nodes=((0.5, 0.041), (1.0, 0.042),
                                     (2.0, 0.043), (3.0, 0.044)))


def _sample_rate_loader(today):
    return SAMPLE_RATE_CURVE, f"Treasury 曲線 {SAMPLE_RATE_CURVE.curve_date}"


# 配息（#123）：同一個理由——`create_app()` 預設接真的 Yahoo→FMP→Nasdaq
# loader，沙箱裡會打出「配息資料不可得」，且結果隨執行環境的連線能力
# 變動。注入固定假歷史，代表「取得配息、q 校準成功」這個較豐富、較有
# 代表性的狀態。
SAMPLE_DIVIDEND_HISTORY = DividendHistory(
    symbol="XYZ", as_of="2026-07-14", source="yahoo",
    distributions=(DividendRecord("2026-06-01", 1.2),
                  DividendRecord("2026-03-01", 1.2)))


def _sample_dividend_loader(symbol, today):
    n = len(SAMPLE_DIVIDEND_HISTORY.distributions)
    return (SAMPLE_DIVIDEND_HISTORY,
           f"配息資料 {SAMPLE_DIVIDEND_HISTORY.source}"
           f"（{SAMPLE_DIVIDEND_HISTORY.as_of}，{n} 筆）")


def freeze_row(row: dict) -> dict:
    return {**row, **FROZEN}


def main() -> None:
    snap = load_snapshot(FIXTURE)
    client = TestClient(create_app(fetch=lambda symbol: snap,
                                   rate_loader=_sample_rate_loader,
                                   dividend_loader=_sample_dividend_loader))
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
                                       storage=MemoryStorage(),
                                       rate_loader=_sample_rate_loader,
                                       dividend_loader=_sample_dividend_loader))
    created = row_client.post("/api/scenarios", json=SCENARIO).json()
    row_client.post(f"/api/scenarios/{created['id']}/refresh").raise_for_status()
    row = row_client.get("/api/scenarios").json()[0]
    ROW_OUT.write_text(json.dumps(freeze_row(row), ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {ROW_OUT}")

    # #115：獨立的 put-comparator 樣本，見上方 PUT_FIXTURE 註解。
    put_snap = load_snapshot(PUT_FIXTURE)
    put_client = TestClient(create_app(fetch=lambda symbol: put_snap,
                                       rate_loader=_sample_rate_loader,
                                       dividend_loader=_sample_dividend_loader))
    put_resp = put_client.post("/api/analyze", json=PUT_REQUEST)
    put_resp.raise_for_status()
    PUT_OUT.write_text(json.dumps(put_resp.json(), ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")
    print(f"寫入 {PUT_OUT}（{PUT_OUT.stat().st_size:,} bytes）")

    # T09（#222）：獨立的單腿到期日分組樣本，見上方 LONG_CALL_OUT 註解。
    lc_resp = client.post("/api/analyze", json=LONG_CALL_REQUEST)
    lc_resp.raise_for_status()
    LONG_CALL_OUT.write_text(json.dumps(lc_resp.json(), ensure_ascii=False,
                                        indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(f"寫入 {LONG_CALL_OUT}（{LONG_CALL_OUT.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
