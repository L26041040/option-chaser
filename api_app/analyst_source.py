"""分析師目標價資料來源介面（OS-03／#392，母票 #389 §2）。

`create_app(analyst_source=...)` 注入一個 `AnalystSource`；**預設 `None`
＝尚未設定**。本輪**沒有任何真實來源**（Yahoo 等自動擷取屬獨立決策，
#389 §12 B1–B3，未啟用）——未設定時共識清單誠實顯示「尚未設定」，
每日 cron 什麼都不做。

`FixtureAnalystSource` 讀固定 JSON（`tests/fixtures/analyst_targets_fixture.json`，
ticker 為不存在的 AAA…GGG），**只在測試與本機驗證腳本裡注入**；它的
`is_fixture = True` 一路傳到 API 回應，前端必須標示「測試資料，非真實
市場資料」。

規則（#389 §2）：
- provider 只能回傳「每筆都有個別目標價與日期」的紀錄；只有共識平均／
  人數的來源只能放進 `cross_check`，永遠不參與計算（L9）。
- `coverage = partial | unknown` 必須照實往下傳。
- 失敗用 `error` 回報（逾時、限流、格式改變、無此 symbol），不要丟例外；
  呼叫端（`api_app/consensus_cache.py`）仍會把例外收斂成失敗。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from option_chaser.consensus import (AnalystTargetRecord, ConsensusCrossCheck,
                                     SplitEvent)

COVERAGES = ("complete", "partial", "unknown")


@dataclass(frozen=True)
class ProviderResult:
    """一檔 symbol 的抓取結果（#389 §2 `ProviderResult`）。"""

    records: tuple[AnalystTargetRecord, ...] = ()
    splits: tuple[SplitEvent, ...] = ()
    coverage: str = "unknown"
    history_from: date | None = None
    error: str | None = None
    cross_check: ConsensusCrossCheck | None = None   # 只供稽核（L9）

    def __post_init__(self) -> None:
        if self.coverage not in COVERAGES:
            raise ValueError(f"coverage 必須是 {COVERAGES} 之一：{self.coverage!r}")


class AnalystSource(Protocol):
    """可注入的分析師資料來源。`name` 進快取與 API 回應（來源換了，舊來源
    的快取不會被當成新來源的結果）；`is_fixture` 為真代表測試資料。"""

    name: str
    is_fixture: bool

    def fetch(self, symbol: str, today: date) -> ProviderResult: ...


class FixtureAnalystSource:
    """讀固定 JSON 檔的來源——**測試資料，非真實市場資料**。檔案裡沒有的
    symbol 回空結果（＝沒有個別目標價 → `no_data`），不是錯誤。"""

    is_fixture = True

    def __init__(self, path: str | Path):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        self.name: str = doc.get("name", "fixture")
        self._symbols: dict[str, dict] = doc["symbols"]

    def fetch(self, symbol: str, today: date) -> ProviderResult:
        entry = self._symbols.get(symbol)
        if entry is None:
            return ProviderResult()
        if entry.get("error"):
            return ProviderResult(coverage=entry.get("coverage", "unknown"),
                                  error=entry["error"])
        cross = entry.get("cross_check")
        history_from = entry.get("history_from")
        return ProviderResult(
            records=tuple(
                AnalystTargetRecord(
                    symbol=symbol, analyst_key=r["analyst_key"], firm=r["firm"],
                    target_price=Decimal(r["target_price"]),
                    published_on=date.fromisoformat(r["published_on"]),
                    source=f"{self.name}:file", action=r.get("action"))
                for r in entry.get("records", ())),
            splits=tuple(
                SplitEvent(symbol=symbol,
                           effective_on=date.fromisoformat(s["effective_on"]),
                           ratio=Decimal(s["ratio"]))
                for s in entry.get("splits", ())),
            coverage=entry.get("coverage", "unknown"),
            history_from=date.fromisoformat(history_from) if history_from else None,
            cross_check=ConsensusCrossCheck(
                consensus_mean_from_source=Decimal(cross["consensus_mean_from_source"]),
                n_from_source=cross.get("n_from_source")) if cross else None)
