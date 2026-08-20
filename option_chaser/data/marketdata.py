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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
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


@dataclass(frozen=True)
class HttpResponse:
    """成功回應的完整形狀（#144）——status／白名單標頭／body 三者皆存在
    才拿得出 diagnostics 要的 HTTP metadata。`headers` 只留
    `_RATE_LIMIT_HEADERS` 白名單裡的幾個，其餘一概不留：這是 redaction
    在最源頭就成立，不是靠後面某一層記得過濾。"""
    status: int
    headers: dict[str, str]
    body: str


# vendor 額度標頭（#144，欄名取自需求方實測的真實回應）。白名單本身就是
# 唯一允許離開這個模組的標頭子集——不整包保留 `resp.headers`。
_RATE_LIMIT_HEADERS = ("X-Api-Ratelimit-Limit", "X-Api-Ratelimit-Remaining",
                      "X-Api-Ratelimit-Consumed")


def _rate_limit_fields(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in _RATE_LIMIT_HEADERS:
        value = headers.get(name)
        if value is not None:
            out[name] = value
    return out


def _http_request(url: str, token: str) -> HttpResponse:
    """低層 primitive（#144）：status／白名單標頭／body 一起回，供需要
    HTTP metadata 的呼叫端（目前只有 `fetch_surface`）使用。非 2xx 時
    urllib 照舊拋 `HTTPError`——`HTTPError` 本身就帶 `.code`／`.headers`，
    呼叫端從例外物件取，不需要這個函式把失敗路徑轉成正常回傳值。"""
    req = Request(url, headers={"Authorization": f"Bearer {token}",
                                "User-Agent": "option-chaser",
                                "Accept": "application/json"})
    with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return HttpResponse(status=resp.status,
                            headers=_rate_limit_fields(resp.headers), body=body)


def _http_get(url: str, token: str) -> str:
    """向後相容的 body-only 介面。`fetch_chain`／`verify` 不需要 HTTP
    metadata，維持這個既有型別當它們的注入點——兩者的既有測試因此不必
    改動任何一行。"""
    return _http_request(url, token).body


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


def _empty_row_counts() -> dict:
    return {"raw_rows": 0, "parsed_call_rows": 0, "parsed_put_rows": 0,
           "dropped_missing_delta": 0, "dropped_missing_iv": 0,
           "dropped_missing_dte": 0, "dropped_unknown_side": 0}


def _parse_surface_rows(rows: list[dict]) -> tuple[dict[str, list], dict]:
    """一天的逐列資料 → (座標點, 筆數帳本)。

    帳本存在的理由是 #144：診斷要能回答「vendor 回 N 筆，究竟在哪一步
    變成 0 筆」，因此每一種被跳過的原因各自計數，而不是像原本那樣一句
    `continue` 就不留痕跡。**篩選條件本身逐字不變**——delta／iv／dte
    任一缺席就跳過，只是現在額外記下是哪一個缺席（多個同時缺席時記第
    一個判到的那個，跳過與否不受影響，因為原本就是同一個 `or` 短路）。
    """
    from ..ivhistory import SurfacePoint

    out: dict[str, list] = {"call": [], "put": []}
    counts = _empty_row_counts()
    counts["raw_rows"] = len(rows)
    for row in rows:
        side = str(row.get("side") or "").lower()
        if side not in out:
            counts["dropped_unknown_side"] += 1
            continue
        delta, iv, dte = row.get("delta"), _num(row.get("iv")), row.get("dte")
        if delta is None:
            counts["dropped_missing_delta"] += 1
            continue
        if iv is None:
            counts["dropped_missing_iv"] += 1
            continue
        if dte is None:
            counts["dropped_missing_dte"] += 1
            continue
        try:
            out[side].append(SurfacePoint(dte=int(dte), delta=abs(float(delta)),
                                          iv=iv))
        except (TypeError, ValueError):
            counts["dropped_missing_dte"] += 1
            continue
    counts["parsed_call_rows"] = len(out["call"])
    counts["parsed_put_rows"] = len(out["put"])
    return out, counts


def _parse_surface(payload: dict) -> tuple[dict[str, list], dict]:
    """`map_surface_payload` 與 `fetch_surface` 共用的唯一分支邏輯
    （#144）：回傳 (points, telemetry)，**不拋例外**——vendor 狀態要不要
    變成 `FetchError` 由呼叫端各自決定，但兩者都需要同一份 telemetry
    （一個給 observer、一個沿用既有行為直接拋出）。`telemetry` 一律帶
    齊 `vendor_status`／`vendor_errmsg`／筆數帳本這幾個 key，no_data／
    失敗兩條路徑上筆數帳本全為零，不是缺席。
    """
    status = payload.get("s")
    if status == "no_data":
        # 這個 (symbol, date, expiration) 組合當天沒有資料——例如目標
        # 到期日在那個歷史日期還沒掛牌。這是**帶了 `expiration` 篩選後
        # 的正常結果**，不是 vendor 故障：整鏈查詢很少見這個狀態，
        # 但單一到期日篩選常態性地會撲空，撲空不該讓整批 backfill 中止。
        return {"call": [], "put": []}, {"vendor_status": status,
                                         "vendor_errmsg": None,
                                         **_empty_row_counts()}
    if status != "ok":
        return {"call": [], "put": []}, {"vendor_status": status,
                                         "vendor_errmsg": payload.get("errmsg"),
                                         **_empty_row_counts()}
    points, counts = _parse_surface_rows(_rows(payload))
    return points, {"vendor_status": status, "vendor_errmsg": None, **counts}


def map_surface_payload(payload: dict) -> dict[str, list]:
    """欄狀回應 → 依權別分組的 `(dte, delta, iv)` 座標點。

    回傳 `{"call": [...], "put": [...]}`，值是
    `option_chaser.ivhistory.SurfacePoint`。delta 取絕對值——put 的 delta
    是負的，混進同一個網格插值會得到毫無意義的結果。

    缺 delta 或 iv 的那一筆直接跳過（不是補零）：那一格沒有座標就是
    沒有座標，補上去會在網格裡放一個假點，讓插值以為自己有依據。
    """
    points, telemetry = _parse_surface(payload)
    status = telemetry["vendor_status"]
    if status not in ("no_data", "ok"):
        raise FetchError(f"Market Data App 回報 s={status!r}")
    return points


def _raise_for_quota(e: Exception) -> None:
    """HTTP 429 ＝額度用完，抬成 `QuotaExhausted`。

    其餘失敗維持一般 `FetchError`——「今天別再試了」跟「這次剛好失敗」
    對使用者是兩件事，混成一句話等於要他自己猜。
    """
    if isinstance(e, HTTPError) and e.code == 429:
        raise QuotaExhausted("Market Data App 今日額度已用完") from e


# observer 是純 callback（一個 dict → None），這個模組本身不 import
# 任何診斷相關的東西——#144 的結構性要求：資料源層不該認識「診斷」這個
# 概念，接線交給呼叫端（`api_app`）。`None` ＝完全不做事，零額外成本。
SurfaceObserver = Callable[[dict], None]


def _notify(observer: SurfaceObserver | None, *, http_status: int | None,
           headers: dict | None, telemetry: dict) -> None:
    if observer is None:
        return
    observer({"http_status": http_status,
             **_rate_limit_fields(headers or {}), **telemetry})


def fetch_surface(symbol: str, on_date: str, token: str,
                  http_request=_http_request, expiration: str | None = None,
                  observer: SurfaceObserver | None = None,
                  ) -> dict[str, list]:
    """某一個歷史日期的整鏈，轉成 (dte, delta, iv) 座標點。

    這是 (tenor, delta) 逐日重錨定的原料——**不是**單一合約的歷史序列
    （那張合約的 tenor 每天縮短、delta 每天漂移，意義會漂掉，見
    `option_chaser/ivhistory.py` 檔頭）。

    **`expiration`（#134 修正）**：不帶這個參數時，vendor 對
    `chain?date=` 的預設行為是**只回下一個月選**（官方文件明載）——
    對到期日遠在天邊的候選（LEAPS）完全覆蓋不到，`iv_at()` 因此在
    禁止外插的規則下全部回 `None`，呈現成「連線成功但沒資料」。呼叫端
    （`ivhistory.nearby_expirations()`）會算出離目標 tenor 最近的幾個
    真實到期日，逐一帶這個參數分別打——每次只回一個到期日的合約，
    成本遠低於 `expiration=all` 回整條鏈。

    **`observer`（#144）**：每一次呼叫結束前（成功或失敗）都會被通知
    一次，帶 HTTP status／白名單 rate-limit 標頭／vendor `s`／
    `errmsg`／筆數帳本。預設 `None`——不影響既有呼叫端、不影響任何
    回傳值或例外型別，純粹是旁路的觀測用途（#144／#146 的接線點）。
    """
    url = _HISTORICAL_CHAIN_URL.format(symbol=symbol.upper(), date=on_date)
    if expiration:
        url += f"&expiration={expiration}"
    try:
        resp = http_request(url, token)
    except HTTPError as e:
        _notify(observer, http_status=e.code, headers=e.headers,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_row_counts()})
        _raise_for_quota(e)
        raise FetchError(
            f"Market Data App 歷史鏈抓取失敗（{symbol} {on_date}）: {e}") from e
    except Exception as e:  # noqa: BLE001
        _notify(observer, http_status=None, headers=None,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_row_counts()})
        raise FetchError(
            f"Market Data App 歷史鏈抓取失敗（{symbol} {on_date}）: {e}") from e

    try:
        payload = json.loads(resp.body)
    except Exception as e:  # noqa: BLE001
        _notify(observer, http_status=resp.status, headers=resp.headers,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_row_counts()})
        raise FetchError(
            f"Market Data App 歷史鏈抓取失敗（{symbol} {on_date}）: {e}") from e

    points, telemetry = _parse_surface(payload)
    _notify(observer, http_status=resp.status, headers=resp.headers,
           telemetry=telemetry)
    if telemetry["vendor_status"] not in ("no_data", "ok"):
        raise FetchError(f"Market Data App 回報 s={telemetry['vendor_status']!r}")
    return points


# ---------- 單合約歷史序列（HIVT-01／#152，HIVT-02／#153） ----------
#
# 跟上面的 `fetch_surface`（整鏈、逐日重錨定用）是**不同的端點、不同的
# 資料語意**：這裡一次呼叫回**同一張 exact contract**（同一 optionSymbol）
# 整段日期區間的歷史序列，spec #151 §2 絕對紅線要求的正是這個——不得
# 拿別的 strike／expiry 頂替。
#
# **回應形狀已由 #152 用真實請求驗證**（issue #152 留言存證，2026-08-17，
# `GET /v1/options/quotes/TLT281215C00094000/?from=&to=`），不是依文件
# 猜的：HTTP 狀態碼可能是 **203**（不是只有 200）。
#
# **HTTP 203 註解更正（HIVR-07／#166）**：先前這裡誤寫「vendor 對延遲
# 報價用 203」——vendor 官方文件（`api/universal-parameters/mode.md`）
# 明文：203＝**這次回應是從快取層回的**，且特地把「mode 對應 status
# code」點名為 "a common (incorrect) assumption"。既有*行為*本來就是對
# 的（見下方 `_http_request` 沿用既有的「urlopen 對任何 2xx 都不拋
# 例外」慣例，本檔案任何地方都沒有寫死 `status == 200`，203 因此天然
# 可用不需要特殊處理）——錯的只有這段對「為什麼」的解釋，不是行為本身。
# **資料新鮮度一律只看 `updated`（觀測本身的時戳），不看 HTTP 狀態碼**
# ——203 不代表舊、200 也不保證新，見 HIVR-07 新增的 `staleness` 診斷
# 事件（`api_app/main.py`）。
#
# 欄位是一般的欄狀 JSON（`s`／`optionSymbol`／
# `updated`／`iv`／`bid`／`ask`／... 皆為與 `optionSymbol` 等長的陣列，
# `updated` 是 Unix 秒，逐日一筆）；`iv` 存在但可能是 `null`（真實樣本：
# 近期資料常見前幾筆 `null`，bid/ask 仍有值）——這是「這天沒有可信的
# IV 報價」，不是「這天沒有資料」，**不得補值、不得插值、不得換合約**
# （spec #151 §2／§3 紅線，HIVT-02 §7 施工限制逐字重申）。

_QUOTES_URL = _BASE + "/options/quotes/{occ_symbol}/?from={from_date}&to={to_date}"


def _observation_date(value) -> str | None:
    """`updated` 欄位（Unix 秒）→ YYYY-MM-DD。形狀不對就回 `None`，呼叫端
    當「這筆缺日期，跳過」處理——不是整批失敗（比照 `_parse_surface_rows`
    對缺 delta／iv／dte 的處理方式，一筆問題不牽連其他筆）。"""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _empty_history_counts() -> dict:
    return {"raw_rows": 0, "parsed_rows": 0, "null_iv_count": 0,
           "dropped_missing_date": 0}


def _parse_contract_history(payload: dict) -> tuple[list[dict], dict]:
    """單合約欄狀回應 → ([quote, ...], telemetry)。不拋例外——比照
    `_parse_surface`，vendor 狀態要不要變成 `FetchError` 交給呼叫端決定。

    每筆 quote 是一個 dict（HIVR-04／#163：比舊版 `(date, iv)` 更寬，
    保留 reconstruction（#164）需要的原始欄位，不再只留下剛好是 vendor
    給 null 的那一個）：

    - `date`：觀測日。**推導方式不變**——仍取自這一列自己的 `updated`
      （不是 `date.today()`／request date）；這段既有邏輯本來就是對的
      （見 `_observation_date`），本票不改
    - `updated`：原始 Unix 秒（整數），供未來稽核／staleness 判讀
      （HIVR-07／#166）用，不經過 `_num()`——時間戳不是「可能合理為零」
      的量，直接原樣保留或解析失敗回 `None`
    - `dte`／`bid`／`ask`／`mid`／`underlying_price`：走既有 `_num()`
      （`None`／非數字／0.0 一律缺值，與這個檔案其他地方的缺值口徑
      一致）
    - `vendor_iv`：走既有 `_num()`；**只作 benchmark／診斷參考，
      canonical series 不得直接採用它**（#164 起的 reconstruction 自己
      反解；#168 用結構性測試鎖死這條規則，本票只負責把這個欄位留住
      不丟）。**`vendor_iv` 為 `None` 的那一筆仍然進 `points`**——那天
      有觀測、只是沒有可信 IV，這跟「那天根本沒有這一筆」（vendor
      沒回、或缺 `updated` 因此連日期都定不出來）是不同的兩件事，只有
      後者才會被跳過（見 `dropped_missing_date`）
    """
    status = payload.get("s")
    if status != "ok":
        return [], {"vendor_status": status,
                    "vendor_errmsg": payload.get("errmsg")
                    if isinstance(payload, dict) else None,
                    **_empty_history_counts()}

    rows = _rows(payload)
    points: list[dict] = []
    null_iv_count = 0
    dropped_missing_date = 0
    for row in rows:
        d = _observation_date(row.get("updated"))
        if d is None:
            dropped_missing_date += 1
            continue
        iv = _num(row.get("iv"))
        if iv is None:
            null_iv_count += 1
        try:
            updated = int(row.get("updated"))
        except (TypeError, ValueError):
            updated = None
        points.append({
            "date": d, "updated": updated, "dte": _num(row.get("dte")),
            "bid": _num(row.get("bid")), "ask": _num(row.get("ask")),
            "mid": _num(row.get("mid")),
            "underlying_price": _num(row.get("underlyingPrice")),
            "vendor_iv": iv,
        })

    return points, {"vendor_status": status, "vendor_errmsg": None,
                    "raw_rows": len(rows), "parsed_rows": len(points),
                    "null_iv_count": null_iv_count,
                    "dropped_missing_date": dropped_missing_date}


ContractHistoryObserver = Callable[[dict], None]


def fetch_contract_history(occ_symbol: str, from_date: str, to_date: str,
                           token: str, http_request=_http_request,
                           observer: ContractHistoryObserver | None = None,
                           ) -> list[dict]:
    """一張 **exact contract**（`occ_symbol`）在 `[from_date, to_date]`
    區間的歷史 quote 序列，依日期遞增排序。每筆是一個 dict——形狀見
    `_parse_contract_history`（HIVR-04／#163：`date`／`updated`／
    `dte`／`bid`／`ask`／`mid`／`underlying_price`／`vendor_iv`）。

    一次呼叫回整段區間（已由 #152 真實驗證確認，真實 TLT LEAPS 案例
    34 筆觀測只花 1 credit）——呼叫端因此不需要像 `fetch_surface` 那樣
    逐日打，`from_date`／`to_date` 由呼叫端依快取缺口算好再傳進來
    （HIVT-02／#153 的漸進式刷新邏輯）。

    `from_date` 早於這張合約實際掛牌日期時**不報錯**（已由 #152 真實
    驗證：對真實合約打 5 年前的 `from` 一樣 200 系列＋`s=ok`，vendor 自動
    只回真正存在的那段），呼叫端不需要另外查 listing date 才能決定
    `from_date`。

    `observer`（比照 `fetch_surface`）：每次呼叫結束前（成功或失敗）都
    會被通知一次，帶 HTTP status／白名單 rate-limit 標頭／vendor
    `s`／`errmsg`／筆數帳本（`raw_rows`／`parsed_rows`／`null_iv_count`／
    `dropped_missing_date`）。
    """
    url = _QUOTES_URL.format(occ_symbol=occ_symbol, from_date=from_date,
                             to_date=to_date)
    try:
        resp = http_request(url, token)
    except HTTPError as e:
        _notify(observer, http_status=e.code, headers=e.headers,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_history_counts()})
        _raise_for_quota(e)
        raise FetchError(
            f"Market Data App 單合約歷史抓取失敗（{occ_symbol}）: {e}") from e
    except Exception as e:  # noqa: BLE001
        _notify(observer, http_status=None, headers=None,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_history_counts()})
        raise FetchError(
            f"Market Data App 單合約歷史抓取失敗（{occ_symbol}）: {e}") from e

    try:
        payload = json.loads(resp.body)
    except Exception as e:  # noqa: BLE001
        _notify(observer, http_status=resp.status, headers=resp.headers,
               telemetry={"vendor_status": None, "vendor_errmsg": None,
                          **_empty_history_counts()})
        raise FetchError(
            f"Market Data App 單合約歷史抓取失敗（{occ_symbol}）: {e}") from e

    points, telemetry = _parse_contract_history(payload)
    _notify(observer, http_status=resp.status, headers=resp.headers,
           telemetry=telemetry)
    if telemetry["vendor_status"] != "ok":
        raise FetchError(
            f"Market Data App 回報 s={telemetry['vendor_status']!r}（{occ_symbol}）")
    return sorted(points, key=lambda q: q["date"])
