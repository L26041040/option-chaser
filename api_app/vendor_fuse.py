"""Global vendor fuse（PB-06／#299，Anonymous Public Beta）：全站每日
vendor 呼叫量軟性上限。

per-owner 額度（PB-05／#297）擋的是單一使用者失控；這裡擋的是
**很多使用者各自都在額度內、加總卻燒光 vendor 額度或 DB 空間**——
per-owner 機制結構上擋不到的那一類，必須是 system-wide、不分 owner
的另一道煞車。

**與既有 `chain_backoff.py` 刻意分離、不合併成一個狀態機**（票面明文
要求）：兩者都是 system-wide 的煞車，但語意不同——

- `chain_backoff`：**被動反應**。vendor 剛剛真的回了 429，記下
  `blocked_until`，在那之前先別打。狀態持久化在 `chain_backoff` 表，
  PK 是 `source` 單獨（provider-global）。
- 這裡（fuse）：**主動預算**。我們自己決定「今天已經打過這個數字了，
  先別再打」，與 vendor 有沒有抱怨無關。**沒有獨立的持久狀態**——
  直接即時查詢既有 `operational_metrics` 表裡今天的 `chain_fetch_
  count` 總和，達到門檻就是「觸發」，這本身就是這個機制唯一的真相
  來源，不需要另外記一個「fuse 是否已觸發」的旗標（那會是真正意義
  上的第二個狀態機，票面明文禁止）。

**計數來源沿用既有機制，不新建平行計數**：`chain_fetch_count` 早就
在 `api_app/main.py::_vendor_attempt()` 記錄「真的打了一次上游」
（S0／SCALE-08 既有指標 #1；每個 provider attempt 各一次，自訂 provider
也算）。這裡只新增一個**讀取**方法
（`Storage.metric_total()`）——對同一張表、同一個既有欄位做一次
targeted 的 SUM 查詢，取代呼叫端本來得撈出 `metric_summary()` 全部
30 天視窗桶再自己過濾加總（那份是給 `/api/ops/metrics` 偶爾一次的
人工查詢用，不該是每次抓鏈前都要付的代價）——不是新的計數維度，
是既有計數的一個更便宜的讀法。
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from option_chaser.models import FetchError


class GlobalVendorFuseTripped(FetchError):
    """今天全站 vendor 呼叫量已達 `GLOBAL_VENDOR_DAILY_BUDGET`——不是
    vendor 本身回的錯（那是 `RateLimitedError`，源自真實 HTTP 429），
    是我們自己主動決定今天不再打。

    刻意繼承 `FetchError`：既有降級鏈（`_fetch_chain()` 往上層的呼叫端
    一律 `except FetchError`）因此不會因為多了這個新狀態而意外改變
    既有行為——沒有特別處理這個子類的呼叫端，仍然得到「抓不到報價」
    的既有結果；`_classify_fetch_failure()` 才是唯一在乎兩者差異、
    會分開處理的地方（比照 `RateLimitedError` 當年的同一個理由，見
    `option_chaser/models.py::RateLimitedError` docstring）。"""


class _FuseStorage(Protocol):
    def metric_total(self, metric: str, bucket: str) -> int: ...


def today_chain_fetch_count(storage: _FuseStorage, today: date) -> int:
    """今天（`today` 的日粒度 bucket，沿用既有 `api_app.metrics` 的
    日界線語意，不自創第二種——SCALE-08 的 `bucket` 本來就是
    `date.isoformat()`）全站 `chain_fetch_count` 累計，跨全部
    source／symbol 加總——這正是「全站」兩個字的意思。不引入 owner
    維度：`operational_metrics` 結構上沒有這個欄位（AC-7 紅線），這裡
    的查詢也不需要它。"""
    return storage.metric_total("chain_fetch_count", today.isoformat())


def tripped(storage: _FuseStorage, today: date, budget: int) -> bool:
    """`budget <= 0` ＝停用（供 rollback／測試，比照 PB-05 兩個煞車
    的既有慣例）。

    查詢本身失敗（Storage 層例外）時**視為未觸發**（fail-open）——
    這是成本控制機制，不是安全邊界（票面 §9 明文），量測本身故障
    不該連帶讓整站的抓鏈功能一起掛掉，那會是拿一個次要的保護機制去
    拖垮它原本要保護的主功能，與 `api_app.metrics.record()`「觀測
    本身絕不能成為新的故障源」同一個哲學的鏡像版本（那裡包的是
    「寫入」失敗，這裡包的是「讀取」失敗）。"""
    if budget <= 0:
        return False
    try:
        return today_chain_fetch_count(storage, today) >= budget
    except Exception:  # noqa: BLE001 — 讀取失敗不得拖垮被保護的主流程
        return False
