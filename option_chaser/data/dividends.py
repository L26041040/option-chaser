"""股利／配息資料抓取與快取——q 管線的網路模組（#123，spec #117 §2）。

Primary = Yahoo chart `events.dividends`（#120 production 實測確認，見
`docs/research/dividend-yield-source-selection.md` §12.4：TLT 匿名
HTTP 200、24 筆歷史配息、與 Nasdaq 獨立來源交叉印證誤差 1.6%）。
backup 鏈 Yahoo → FMP → Nasdaq，形狀比照 `treasury.py` 既有慣例：純
stdlib `urllib`、單一 User-Agent、逾時、任何連線／解析失敗收斂成單一
`FetchError`。

FMP 需要免費金鑰（環境變數 `FMP_API_KEY`）——研究文件 §13-6 明列為待
需求方裁示的 ToS／申請取捨，本模組未設定時這一棒直接視為失敗、鏈自動
落到 Nasdaq，不當例外處理、不阻塞其餘來源。

資本利得分配（`events.capitalGains`）在 Yahoo 解析層直接不讀取，只取
`events.dividends`——研究 §8：只計經常性現金分配。FMP／Nasdaq 兩個
backup 沒有已查證的資本利得標記欄位可用（研究文件未能查證，見該文
§7），這是已知、記錄在案的簡化，不是遺漏。
"""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..dividends import DividendHistory, DividendRecord, history_from_dict, history_to_dict
from ..models import FetchError

_TIMEOUT_SECONDS = 15.0
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0.0.0 Safari/537.36")

YAHOO_URL = ("https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
            "?range=2y&interval=1d&events=div,splits,capitalGains")
FMP_URL = ("https://financialmodelingprep.com/stable/dividends"
          "?symbol={symbol}&limit=40&apikey={key}")
NASDAQ_URL = "https://api.nasdaq.com/api/quote/{symbol}/dividends?assetclass={cls}"

DEFAULT_CACHE_DIR = Path("snapshots")
CACHE_MAX_AGE_DAYS = 90   # 研究 §9：分配月頻更新，7 天窗（利率用）會把
                          # 使用者踢回 q=0 這個已知會印 +81% 的狀態


def _status_error(status: int) -> FetchError:
    return FetchError(f"狀態碼 {status}（非 200，視為此來源失敗）")


def _http_get(url: str, headers: dict | None = None) -> str:
    req = Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        raise _status_error(e.code) from e
    if status != 200:
        raise _status_error(status)
    return body


# ---------- 逐 vendor 解析（#120 §12.4 實測確認的形狀） ----------

def _parse_yahoo(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise FetchError(f"Yahoo 回應非 JSON：{e}") from e
    results = (data.get("chart") or {}).get("result") or []
    if not results:
        raise FetchError("Yahoo 回應無 chart.result")
    events = results[0].get("events") or {}
    divs = events.get("dividends") or {}
    try:
        records = tuple(
            DividendRecord(
                ex_date=datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat(),
                amount=float(d["amount"]))
            for ts, d in divs.items())
    except (KeyError, TypeError, ValueError) as e:
        raise FetchError(f"Yahoo events.dividends 形狀異常：{e}") from e
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="yahoo",
                           distributions=records)


def _parse_fmp(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise FetchError(f"FMP 回應非 JSON：{e}") from e
    if not isinstance(data, list):
        raise FetchError(f"FMP 回應非預期的陣列形狀：{type(data).__name__}")
    records = []
    for row in data:
        try:
            records.append(DividendRecord(ex_date=row["date"], amount=float(row["dividend"])))
        except (KeyError, TypeError, ValueError):
            continue   # 單筆形狀不對不炸整份——盡量取得能取得的
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="fmp",
                           distributions=tuple(records))


def _parse_nasdaq(symbol: str, text: str, today: date) -> DividendHistory:
    try:
        data = json.loads(text)
    except ValueError as e:
        raise FetchError(f"Nasdaq 回應非 JSON：{e}") from e
    rows = (((data.get("data") or {}).get("dividends") or {}).get("rows")) or []
    records = []
    for row in rows:
        raw_date, raw_amount = row.get("exOrEffDate"), row.get("amount")
        if not raw_date or not raw_amount:
            continue
        try:
            ex_date = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
            amount = float(str(raw_amount).replace("$", "").strip())
        except (ValueError, TypeError):
            continue
        records.append(DividendRecord(ex_date=ex_date, amount=amount))
    return DividendHistory(symbol=symbol, as_of=today.isoformat(), source="nasdaq",
                           distributions=tuple(records))


def fetch_dividends(symbol: str, today: date, http_get=_http_get) -> DividendHistory:
    """Yahoo → FMP（需金鑰，未設定即跳過）→ Nasdaq。全敗拋 `FetchError`。

    研究 §13-2 既有紀律：Yahoo 已於 #120 production 實測確認，成功即
    不追測其餘來源；這裡的鏈是「Yahoo 這次失敗才輪到下一棒」，不是
    「每次都全打一輪」。
    """
    errors: list[str] = []
    try:
        return _parse_yahoo(symbol, http_get(YAHOO_URL.format(symbol=symbol)), today)
    except Exception as e:  # noqa: BLE001 — 連線與解析失敗一律走下一備援
        errors.append(f"Yahoo：{e}")

    fmp_key = os.environ.get("FMP_API_KEY")
    if fmp_key:
        try:
            url = FMP_URL.format(symbol=symbol, key=fmp_key)
            return _parse_fmp(symbol, http_get(url), today)
        except Exception as e:  # noqa: BLE001
            errors.append(f"FMP：{e}")
    else:
        errors.append("FMP：FMP_API_KEY 未設定，略過（研究文件 §13-6 待需求方裁示）")

    for asset_class in ("stocks", "etf"):   # 研究 §5.3：先試 stocks，400 才試 etf
        try:
            url = NASDAQ_URL.format(symbol=symbol, cls=asset_class)
            return _parse_nasdaq(symbol, http_get(url, {"Accept": "application/json"}), today)
        except Exception as e:  # noqa: BLE001
            errors.append(f"Nasdaq（{asset_class}）：{e}")

    raise FetchError(f"配息資料抓取失敗：{'; '.join(errors)}")


# ---------- 本地檔案快取（比照 treasury.py，per-symbol） ----------

def _cache_path(symbol: str, cache_dir: Path) -> Path:
    return cache_dir / f"dividend_cache_{symbol}.json"


def _write_cache(cache_path: Path, today: date, history: DividendHistory) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"schema_version": 1, "fetched_on": today.isoformat(),
                       "history": history_to_dict(history)},
                      ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8")
    except OSError:
        pass                      # 快取寫不進去不影響本次分析（下次再試）


def _read_cache(cache_path: Path) -> tuple[date, DividendHistory] | None:
    try:
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        return (date.fromisoformat(data["fetched_on"]),
                history_from_dict(data["history"]))
    except Exception:  # noqa: BLE001 — 缺檔／壞檔／舊格式一律視為無快取
        return None


def load_dividend_history(
    symbol: str, today: date, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=fetch_dividends
) -> tuple[DividendHistory | None, str]:
    """三層 fallback，回傳 (歷史或 None, 報告參數行註記)。

    (a) 抓取成功（含確定無配息）→ 快取並回新鮮歷史；
    (b) 抓取失敗 → 快取在 90 日曆日內 → 用快取，標 stale、註記快取日期
        （研究 §9：90 天窗，非利率沿用的 7 天——分配是月頻事件）；
    (c) 無快取或超窗 → (None, 註記)，由呼叫端退回今天的完整行為
        （q_by_symbol 維持 None，不是「q=0 加價格錨定」）。
    """
    cache_path = _cache_path(symbol, cache_dir)
    try:
        history = fetch(symbol, today)
    except Exception:  # noqa: BLE001 — 任何抓取失敗都進入快取層
        history = None
    if history is not None:
        _write_cache(cache_path, today, history)
        n = len(history.distributions)
        return history, f"配息資料 {history.source}（{history.as_of}，{n} 筆）"
    cached = _read_cache(cache_path)
    if cached is not None:
        fetched_on, cached_history = cached
        if (today - fetched_on).days <= CACHE_MAX_AGE_DAYS:
            stale_history = dataclasses.replace(cached_history, stale=True)
            return stale_history, (f"配息資料 {cached_history.source}"
                                   f"（快取於 {fetched_on.isoformat()}）")
    return None, "配息資料不可得"
