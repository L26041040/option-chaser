"""Market Data App adapter（Settings／#125）。stdlib urllib，比照 cboe.py。

目前唯一的「自訂」資料源（`api_app/providers.py` 白名單）。與 Cboe／
yfinance 的差別是它**要 token**：`Authorization: Bearer {token}`，因此
不可能有匿名路徑，也就不可能在使用者填入金鑰之前先驗證。

回應是 Market Data App 的**欄狀（columnar）JSON**：`{"s": "ok",
"optionSymbol": [...], "bid": [...], ...}`——每個欄位一個等長陣列，第 i
筆合約的值散在各陣列的第 i 格，不是一般的物件陣列。`s` 是狀態欄
（"ok"／"no_data"／"error"）。

⚠ **wire format 尚未經真實回應驗證**（#111 的工作）：本檔案的欄位對應
依官方文件（`docs/research/historical-options-iv-data-sources.md` §4.7、
`option-chain-data-sources.md` §3.6）撰寫。#111 拿到真實回應後，若欄位
名或形狀有出入，改的是 `_column_map`／`map_chain_payload` 這兩處，
呼叫端與 HTTP 接縫不受影響。任何解析失敗都收斂成 `FetchError`，因此
「對應寫錯」的後果是走備援（退回 Cboe），不是整個分析炸掉。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..models import (SCHEMA_VERSION, ChainSnapshot, FetchError,
                      OptionContract, QuotaExhausted)

SOURCE = "marketdata-app"

_BASE = "https://api.marketdata.app/v1"
_CHAIN_URL = _BASE + "/options/chain/{symbol}/"
# 驗證用的最省端點：只回該標的的到期日清單，不逐筆合約扣 credit
# （chain 端點即時查詢是「回幾筆扣幾個 credit」，拿它當連線測試等於
# 每按一次就燒掉使用者一整天的免費額度）。
_EXPIRATIONS_URL = _BASE + "/options/expirations/{symbol}/"
_TIMEOUT_SECONDS = 15.0

# 驗證用的標的：流動性高、必然存在，且與使用者的劇本無關——不拿使用者
# 某個劇本的標的去測，否則「測試連線」的結果會隨劇本而異。
_PROBE_SYMBOL = "AAPL"


def _http_get(url: str, token: str) -> str:
    req = Request(url, headers={"Authorization": f"Bearer {token}",
                                "User-Agent": "option-chaser",
                                "Accept": "application/json"})
    with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _num(value) -> float | None:
    """缺值口徑統一：`None`／非數字／0.0 一律當缺值。

    0.0 當缺值是沿用 `cboe.py` 既有的判斷（iv=0.0／last=0.0 映射成
    `None`）——報價為零不是「便宜」，是這一格沒有資料，讓它進到過濾器
    會被當成真報價。
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out == 0.0 else out


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rows(payload: dict) -> list[dict]:
    """欄狀 JSON → 一般的每筆一個 dict。

    以 `optionSymbol` 的長度為準，其餘欄位缺的補 `None`——vendor 對沒有
    資料的欄位可能整個不回傳那個陣列，逐欄 zip 會直接少掉整批合約。
    """
    symbols = payload.get("optionSymbol") or []
    keys = [k for k, v in payload.items() if isinstance(v, list)]
    out = []
    for i in range(len(symbols)):
        row = {}
        for k in keys:
            col = payload[k]
            row[k] = col[i] if i < len(col) else None
        out.append(row)
    return out


def _expiry(value) -> str:
    """到期日欄位是 Unix 秒（vendor 慣例），轉成 YYYY-MM-DD。

    已經是字串日期時原樣採用——文件兩處寫法不一致，兩種都吃，省得為了
    一個格式差異走備援。
    """
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()


def map_chain_payload(symbol: str, payload: dict, fetched_at: str) -> ChainSnapshot:
    """欄狀回應 → `ChainSnapshot`。形狀不對就拋，由 `fetch_chain` 收斂。"""
    status = payload.get("s")
    if status != "ok":
        raise FetchError(f"Market Data App 回報 s={status!r}（{symbol}）")

    contracts = []
    for row in _rows(payload):
        occ = row.get("optionSymbol")
        if not occ:
            continue
        side = str(row.get("side") or "").lower()
        if side not in ("call", "put"):
            continue
        contracts.append(OptionContract(
            contract_symbol=occ,
            option_type=side,
            strike=float(row["strike"]),
            expiry=_expiry(row.get("expiration")),
            bid=_num(row.get("bid")),
            ask=_num(row.get("ask")),
            last=_num(row.get("last")),
            volume=_int(row.get("volume")),
            open_interest=_int(row.get("openInterest")),
            implied_volatility=_num(row.get("iv")),
        ))
    if not contracts:
        raise FetchError(f"Market Data App 沒有回傳任何合約（{symbol}）")

    # 現價：`underlyingPrice` 逐筆重複同一個值，取第一個非空的即可。
    spot = next((_num(r.get("underlyingPrice")) for r in _rows(payload)
                 if _num(r.get("underlyingPrice")) is not None), None)
    if spot is None:
        raise FetchError(f"Market Data App 沒有回傳標的現價（{symbol}）")

    return ChainSnapshot(schema_version=SCHEMA_VERSION, symbol=symbol,
                         fetched_at=fetched_at, spot=spot, source=SOURCE,
                         contracts=tuple(contracts))


def fetch_chain(symbol: str, token: str, http_get=_http_get) -> ChainSnapshot:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        payload = json.loads(http_get(_CHAIN_URL.format(symbol=symbol.upper()),
                                      token))
        return map_chain_payload(symbol, payload, fetched_at)
    except FetchError:
        raise
    except Exception as e:  # noqa: BLE001 — 任何網路／解析／形狀失敗都是
        # 抓取失敗，收斂成 FetchError 讓上游的備援鏈接得住。
        raise FetchError(f"Market Data App 抓取失敗（{symbol}）: {e}") from e


class VerifyResult:
    """`verify` 的結果——成功與失敗都是正常回傳值，不是例外。

    失敗原因要能給使用者看（設定頁的「驗證失敗」狀態要說得出為什麼），
    包成例外反而讓呼叫端得為了拿一句話而 try/except。
    """

    def __init__(self, ok: bool, reason: str | None = None) -> None:
        self.ok = ok
        self.reason = reason


def verify(token: str, http_get=_http_get) -> VerifyResult:
    """用最省的端點確認這把 token 真的能用。

    **不吞掉區別**：認證被拒、額度用盡、連不上是三種不同的處境，使用者
    能做的事也不同（換 token／等明天／檢查網路），所以各自回不同的話。
    """
    try:
        raw = http_get(_EXPIRATIONS_URL.format(symbol=_PROBE_SYMBOL), token)
    except HTTPError as e:
        if e.code in (401, 403):
            return VerifyResult(False, "認證被拒——請確認 token 是否正確、是否已失效")
        if e.code == 429:
            return VerifyResult(False, "額度用盡——今日的請求配額已用完")
        return VerifyResult(False, f"資料源回應錯誤（HTTP {e.code}）")
    except Exception as e:  # noqa: BLE001 — 連不上／逾時／DNS 皆歸此類
        return VerifyResult(False, f"連不上資料源：{e}")

    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        return VerifyResult(False, "資料源回應無法解析")

    status = payload.get("s")
    if status == "ok":
        return VerifyResult(True)
    # vendor 也會用 200＋`s: "error"` 表達錯誤，不是只靠 HTTP 狀態碼。
    message = payload.get("errmsg") or f"s={status!r}"
    return VerifyResult(False, f"資料源回報失敗：{message}")


# ---------- 歷史曲面（#126） ----------

_HISTORICAL_CHAIN_URL = _BASE + "/options/chain/{symbol}/?date={date}"


def map_surface_payload(payload: dict) -> dict[str, list]:
    """欄狀回應 → 依權別分組的 `(dte, delta, iv)` 座標點。

    回傳 `{"call": [...], "put": [...]}`，值是
    `option_chaser.ivhistory.SurfacePoint`。delta 取絕對值——put 的 delta
    是負的，混進同一個網格插值會得到毫無意義的結果。

    缺 delta 或 iv 的那一筆直接跳過（不是補零）：那一格沒有座標就是
    沒有座標，補上去會在網格裡放一個假點，讓插值以為自己有依據。
    """
    from ..ivhistory import SurfacePoint

    if payload.get("s") != "ok":
        raise FetchError(f"Market Data App 回報 s={payload.get('s')!r}")

    out: dict[str, list] = {"call": [], "put": []}
    for row in _rows(payload):
        side = str(row.get("side") or "").lower()
        if side not in out:
            continue
        delta, iv, dte = row.get("delta"), _num(row.get("iv")), row.get("dte")
        if delta is None or iv is None or dte is None:
            continue
        try:
            out[side].append(SurfacePoint(dte=int(dte), delta=abs(float(delta)),
                                          iv=iv))
        except (TypeError, ValueError):
            continue
    return out


def _raise_for_quota(e: Exception) -> None:
    """HTTP 429 ＝額度用完，抬成 `QuotaExhausted`。

    其餘失敗維持一般 `FetchError`——「今天別再試了」跟「這次剛好失敗」
    對使用者是兩件事，混成一句話等於要他自己猜。
    """
    if isinstance(e, HTTPError) and e.code == 429:
        raise QuotaExhausted("Market Data App 今日額度已用完") from e


def fetch_surface(symbol: str, on_date: str, token: str,
                  http_get=_http_get) -> dict[str, list]:
    """某一個歷史日期的整鏈，轉成 (dte, delta, iv) 座標點。

    這是 (tenor, delta) 逐日重錨定的原料——**不是**單一合約的歷史序列
    （那張合約的 tenor 每天縮短、delta 每天漂移，意義會漂掉，見
    `option_chaser/ivhistory.py` 檔頭）。
    """
    try:
        raw = http_get(_HISTORICAL_CHAIN_URL.format(symbol=symbol.upper(),
                                                    date=on_date), token)
        return map_surface_payload(json.loads(raw))
    except FetchError:
        raise
    except Exception as e:  # noqa: BLE001
        _raise_for_quota(e)
        raise FetchError(
            f"Market Data App 歷史鏈抓取失敗（{symbol} {on_date}）: {e}") from e
