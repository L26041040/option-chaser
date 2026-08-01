"""Treasury 利率曲線抓取與快取——估值輸入層唯二的網路模組之一（另一為 yf）。

需求：issue #26（T12-A）＋研究 §8。免鑰單一 GET：當年 CSV 為主、XML 為備援、
年初空檔再退前一年 CSV。成功即快取（JSON＋fetched_on）；失敗用快取
（陳舊窗 7 日曆日）；無快取或超窗回 (None, 註記)，由 service 退回固定 0.04
並在報告參數行標示。研究中端點 URL 為搜尋索引轉述，以實際回應為準——因此
解析失敗（端點改版／維護頁）與連線失敗同樣走備援與 fallback，不炸分析。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from ..models import FetchError
from ..ratecurve import (RateCurve, curve_from_dict, curve_to_dict,
                         parse_treasury_csv, parse_treasury_xml)

CSV_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
           "interest-rates/daily-treasury-rates.csv/{year}/all"
           "?type=daily_treasury_yield_curve&field_tdr_date_value={year}"
           "&_format=csv")
XML_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
           "interest-rates/pages/xml?data=daily_treasury_yield_curve"
           "&field_tdr_date_value={year}")

# 與 chain snapshot 同住 snapshots/：兩者都是「分析輸入的本地留存」。
DEFAULT_CACHE_PATH = Path("snapshots") / "treasury_curve_cache.json"
CACHE_MAX_AGE_DAYS = 7
_TIMEOUT_SECONDS = 15.0


def _http_get(url: str) -> str:
    req = Request(url, headers={"User-Agent": "option-chaser"})
    with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_curve(today: date, http_get=_http_get) -> RateCurve:
    """當年 CSV → 當年 XML → 前一年 CSV（年初尚無當年資料）。全敗拋 FetchError。"""
    attempts = ((CSV_URL, today.year, parse_treasury_csv),
                (XML_URL, today.year, parse_treasury_xml),
                (CSV_URL, today.year - 1, parse_treasury_csv))
    errors: list[str] = []
    for url_tpl, year, parse in attempts:
        try:
            return parse(http_get(url_tpl.format(year=year)))
        except Exception as e:  # noqa: BLE001 — 連線與解析失敗一律走下一備援
            errors.append(f"{year}/{parse.__name__}: {e}")
    raise FetchError(f"Treasury 曲線抓取失敗：{'; '.join(errors)}")


def _write_cache(cache_path: Path, today: date, curve: RateCurve) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"schema_version": 1,
                        "fetched_on": today.isoformat(),
                        "curve": curve_to_dict(curve)},
                       ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8")
    except OSError:
        pass                      # 快取寫不進去不影響本次分析（下次再試）


def _read_cache(cache_path: Path) -> tuple[date, RateCurve] | None:
    try:
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        return (date.fromisoformat(data["fetched_on"]),
                curve_from_dict(data["curve"]))
    except Exception:  # noqa: BLE001 — 缺檔／壞檔／舊格式一律視為無快取
        return None


def load_rate_curve(today: date, cache_path: Path = DEFAULT_CACHE_PATH,
                    fetch=fetch_curve) -> tuple[RateCurve | None, str]:
    """三層 fallback，回傳 (曲線或 None, 報告參數行註記)。

    (a) 抓取成功 → 快取並回新鮮曲線；
    (b) 抓取失敗 → 快取在 7 日曆日內 → 用快取，註記快取日期；
    (c) 無快取或超窗 → (None, 註記)，由呼叫端退固定利率。
    """
    try:
        curve = fetch(today)
    except Exception:  # noqa: BLE001 — 任何抓取失敗都進入快取層
        curve = None
    if curve is not None:
        _write_cache(Path(cache_path), today, curve)
        return curve, f"Treasury 曲線 {curve.curve_date}"
    cached = _read_cache(Path(cache_path))
    if cached is not None:
        fetched_on, cached_curve = cached
        if (today - fetched_on).days <= CACHE_MAX_AGE_DAYS:
            return cached_curve, (f"Treasury 曲線 {cached_curve.curve_date}"
                                  f"（快取於 {fetched_on.isoformat()}）")
    return None, "曲線不可得"
