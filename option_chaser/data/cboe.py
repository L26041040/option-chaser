"""Cboe 延遲報價 adapter（FB3-01／#44）。stdlib urllib，比照 treasury.py。

主資料源：`cdn.cboe.com` 官方延遲報價 JSON——單一 GET 回傳該標的全部
掛牌序列（所有到期日含 LEAPS）。換源理由（診斷全文見 issue #44 與
`docs/research/option-chain-data-sources.md`）：Yahoo 盤外把 bid/ask
歸零、品質過濾把遠期候選池殺光；Cboe 盤外凍結收盤報價不歸零
（需求方 2026-08-02 休市時段實測確認）。

注意：此端點無官方 API 文件、無 SLA，失敗時由 `service.fetch_and_save`
自動退回 yfinance（快照 `source` 欄位如實記錄實際用了哪個源）。
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..models import (SCHEMA_VERSION, ChainSnapshot, FetchError,
                      OptionContract, RateLimitedError)

_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
_TIMEOUT_SECONDS = 15.0


def parse_retry_after(value: str | None) -> float | None:
    """SCALE-04（#255）：`Retry-After` 標頭有兩種合法形式（RFC 9110
    §10.2.3）——delta-seconds（純數字字串，如 `"34"`）或 HTTP-date
    （如 `"Wed, 21 Oct 2026 07:28:00 GMT"`）。缺失、空字串或兩種格式
    都解析不出來時回 `None`——呼叫端改用保守預設值，不當成 0 秒。"""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return seconds if seconds >= 0 else None
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    delta = (target - datetime.now(timezone.utc)).total_seconds()
    return delta if delta >= 0 else None


def _http_get(url: str) -> str:
    req = Request(url, headers={"User-Agent": "option-chaser"})
    with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_occ_symbol(occ: str) -> tuple[str, str, float]:
    """OCC 代號 → (expiry, option_type, strike)。

    如 `TLT260731C00065000` → ("2026-07-31", "call", 65.0)。root symbol
    長度不定，從尾端定位：8 位 strike×1000、1 位 C/P、6 位 yymmdd。
    形狀不對就拋 ValueError——`fetch_chain` 會收斂成 FetchError，
    觸發 yfinance 備援。"""
    if len(occ) < 16 or occ[-9] not in "CP" or not occ[-8:].isdigit() \
            or not occ[-15:-9].isdigit():
        raise ValueError(f"無法解析的 OCC 代號：{occ!r}")
    strike = int(occ[-8:]) / 1000.0
    cp = occ[-9]
    yymmdd = occ[-15:-9]
    expiry = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    return expiry, "call" if cp == "C" else "put", strike


def _clean_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _positive_or_none(value) -> float | None:
    """Cboe 以 0.0 表示「無資料」（深度 ITM 的 iv、從未成交的 last）——
    一律映射為缺值 None，與 yfinance adapter 的缺值口徑（NaN→None）
    一致，原始資料表／CSV 也不會顯示誤導的 0.0。

    注意：這**不改變**過濾結果——`filters.iv_ok` 對 None 與 0.0 同樣
    判定「IV 異常」。缺 IV 的合約本來就必須排除：估值引擎的 BS 定價
    需要 IV（`evaluate_contract` 明文 assert），這是過濾器在保護引擎，
    不是誤殺。"""
    f = _clean_float(value)
    return None if f is None or f <= 0.0 else f


def map_payload(symbol: str, payload: dict, fetched_at: str) -> ChainSnapshot:
    data = payload["data"]
    spot = _clean_float(data.get("current_price")) or _clean_float(data.get("close"))
    contracts = []
    for o in data.get("options", ()):
        expiry, option_type, strike = parse_occ_symbol(o["option"])
        contracts.append(OptionContract(
            contract_symbol=str(o["option"]),
            option_type=option_type, strike=strike, expiry=expiry,
            bid=_clean_float(o.get("bid")),
            ask=_clean_float(o.get("ask")),
            last=_positive_or_none(o.get("last_trade_price")),
            volume=int(_clean_float(o.get("volume")) or 0),
            open_interest=int(_clean_float(o.get("open_interest")) or 0),
            implied_volatility=_positive_or_none(o.get("iv")),
        ))
    if not contracts or spot is None or spot <= 0:
        raise FetchError(f"Cboe 回傳資料不足（{symbol}）：無現價或無合約")
    return ChainSnapshot(
        schema_version=SCHEMA_VERSION, symbol=symbol, fetched_at=fetched_at,
        spot=spot, source="cboe", contracts=tuple(contracts),
    )


def fetch_chain(symbol: str, http_get=_http_get) -> ChainSnapshot:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        payload = json.loads(http_get(_URL.format(symbol=symbol.upper())))
        return map_payload(symbol, payload, fetched_at)
    except FetchError:
        raise
    except HTTPError as e:
        # SCALE-04（#255）：429 抬成專屬 `RateLimitedError`（`FetchError`
        # 子類，既有降級鏈相容——見該例外類別 docstring），其餘 HTTP
        # 錯誤碼維持既有的通用 `FetchError` 收斂行為，不新增分層。
        if e.code == 429:
            retry_after = parse_retry_after(e.headers.get("Retry-After")
                                            if e.headers else None)
            raise RateLimitedError(
                f"Cboe 限流（{symbol}）：HTTP 429",
                retry_after_seconds=retry_after) from e
        raise FetchError(f"Cboe 抓取失敗（{symbol}）: HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001 — 任何網路／解析／形狀失敗都是
        # 抓取失敗：必須收斂成 FetchError，service.fetch_and_save 的
        # yfinance 備援才接得住（如 Cboe 回錯誤物件缺 "data" 鍵）。
        raise FetchError(f"Cboe 抓取失敗（{symbol}）: {e}") from e
