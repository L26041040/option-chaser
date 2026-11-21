"""分析師目標價資料來源介面（OS-03／#392，母票 #389 §2）。

`create_app(analyst_source=...)` 注入一個 `AnalystSource`；`create_app()` 的
**預設 `None`＝尚未設定**（測試用）。部署環境由 `api/index.py` 經
`analyst_source_from_env()` 注入真實來源 `YahooAnalystSource`（LIVE-T1／#397；
Owner 決策見 #389 LIVE-DATA-DELIVERY-001），`OC_ANALYST_SOURCE=off` 可緊急關閉；
未設定時共識清單誠實顯示「尚未設定」，每日 cron 什麼都不做。

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
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from option_chaser.consensus import (AnalystTargetRecord, ConsensusCrossCheck,
                                     SplitEvent)
from option_chaser.data.yahoo_analyst import (YahooClient, YahooError,
                                              YahooSymbolData, split_basis_through)

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
        # 檔案沒寫抓取時間的紀錄：以這次抓取的日期（UTC 零時）為準——A3 的
        # 同日決勝靠 retrieved_at，不能留空。
        fetched = datetime.combine(today, time(0), tzinfo=timezone.utc)
        return ProviderResult(
            records=tuple(
                AnalystTargetRecord(
                    symbol=symbol, analyst_key=r["analyst_key"], firm=r["firm"],
                    target_price=Decimal(r["target_price"]),
                    published_on=date.fromisoformat(r["published_on"]),
                    source=f"{self.name}:file", action=r.get("action"),
                    retrieved_at=(datetime.fromisoformat(r["retrieved_at"])
                                  if r.get("retrieved_at") else fetched),
                    split_adjusted_through=(
                        date.fromisoformat(r["split_adjusted_through"])
                        if r.get("split_adjusted_through") else None))
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


class YahooAnalystSource:
    """真實來源：Yahoo `upgradeDowngradeHistory`（LIVE-T1／#397）。不需要金鑰。

    - `analyst_key` 就是 Yahoo 的券商名稱；改名別名表（`FIRM_ALIASES`）交給
      共識引擎既有的 `ConsensusRules.aliases`（#389 A3），部署環境由
      `api/index.py` 帶入。
    - 每筆紀錄的 `split_adjusted_through` 依發布當週股價判斷（Yahoo 的目標價
      混著分割前／後兩種基準，見 `split_basis_through`）。
    - Yahoo 沒有「終止覆蓋」事件 → `coverage` 一律 `partial`（研究已確認）。
    - `financialData` 的共識平均／人數只進 `cross_check`（L9）。
    - 失敗收斂成 `ProviderResult(error=...)`，不丟例外。
    """

    name = "yahoo-udh"
    is_fixture = False

    def __init__(self, transport=None):
        self.client = YahooClient(transport)

    def fetch(self, symbol: str, today: date) -> ProviderResult:
        try:
            data = self.client.fetch(symbol)
        except YahooError as e:
            hint = f"（Retry-After {e.retry_after} 秒）" if e.retry_after else ""
            return ProviderResult(coverage="partial", error=f"{e}{hint}")
        return self.to_provider_result(symbol, data)

    def to_provider_result(self, symbol: str, data: YahooSymbolData) -> ProviderResult:
        """已抓到的 `YahooSymbolData` → `ProviderResult`（純轉換，不打上游）。"""
        retrieved = datetime.now(timezone.utc)
        records = tuple(
            AnalystTargetRecord(
                symbol=symbol, analyst_key=t.firm, firm=t.firm,
                target_price=t.target_price, published_on=t.published_on,
                source=f"{self.name}:quoteSummary", action=t.action,
                prior_target=t.prior_target, retrieved_at=retrieved,
                split_adjusted_through=split_basis_through(
                    t, data.splits, data.weekly_closes))
            for t in data.summary.targets)
        summary = data.summary
        cross = (ConsensusCrossCheck(consensus_mean_from_source=summary.consensus_mean,
                                     n_from_source=summary.analyst_count)
                 if summary.consensus_mean is not None else None)
        return ProviderResult(
            records=records,
            splits=tuple(SplitEvent(symbol=symbol, effective_on=s.effective_on,
                                    ratio=s.ratio) for s in data.splits),
            coverage="partial",
            history_from=min((r.published_on for r in records), default=None),
            cross_check=cross)


ANALYST_SOURCE_ENV = "OC_ANALYST_SOURCE"
_ENABLED_VALUES = {"", "yahoo", "on"}


def analyst_source_from_env(env=None) -> AnalystSource | None:
    """部署環境（`api/index.py`）用的來源：**未設定時啟用 Yahoo**（不需要金鑰）。
    `OC_ANALYST_SOURCE` 只認 `yahoo`／`on`（或不設）為啟用，其他任何值（`off`
    或打錯字）一律關閉、回到「尚未設定」——寧可關掉也不誤開。只在函式冷啟動
    （模組載入）時讀一次，改了環境變數要重新部署才生效。

    `create_app()` 本身的預設仍是 `None`——上千條測試直接呼叫它，不能讓測試
    意外連外網。"""
    value = ((env if env is not None else os.environ).get(ANALYST_SOURCE_ENV) or "").strip()
    if value.casefold() not in _ENABLED_VALUES:
        return None
    return YahooAnalystSource()
