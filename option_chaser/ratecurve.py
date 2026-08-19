"""無風險利率曲線純函式模組（無 I/O、無全域狀態、無 wall-clock）。

需求來源：issue #26（T12-A）＋ `docs/research/risk-free-rate-for-bs.md` §5/§6/§8。

Treasury Daily Par Yield Curve（CMT）為半年複利 bond-equivalent 報價，且短端
bills 已由財政部換算成同一口徑，因此**全曲線用同一條轉換公式**：
`r_cc = 2·ln(1 + y/2)`。轉換後對連續複利 zero rate 做**相鄰節點線性插值**；
研究已量化 par→zero bootstrap 差 <1bp、插值基礎差個位數 bp，皆不做。

不外插：T 小於最短節點（1M）取 1M 值；T 大於最長節點取最長節點值。

抓取（HTTP）隔在 `option_chaser.data.treasury`；本模組只認文字與資料結構，
單元測試以固定曲線夾具離線重跑。
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree

from .models import ParamError


class CurveParseError(Exception):
    """曲線文字（CSV/XML）解析失敗——端點改版或回傳維護頁時的明確訊號。"""


@dataclass(frozen=True)
class RateCurve:
    """連續複利 zero rate 曲線。`nodes` = (年期, r_cc)，嚴格遞增、至少一節點。

    `stale`（RC1／#87）：這條曲線是不是「今天抓取失敗、沿用陳舊備援窗
    （本地檔案快取或 Neon 持久快取）的舊曲線」，不是它自己抓到那天算
    起的新鮮度。預設 `False`（一般解析／建構出來的曲線視為新鮮）；
    只有 `data/treasury.py` 的本地快取備援分支與 `api_app/rate_cache.py`
    的 Neon 緊急備援窗分支會把讀回來的舊曲線標成 `True`，供前端把
    「真曲線但陳舊」與「真曲線且新鮮」分開顯示（不得混為一談）。"""

    curve_date: str                          # 曲線資料日 YYYY-MM-DD
    nodes: tuple[tuple[float, float], ...]
    stale: bool = False

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ParamError("利率曲線至少需要一個節點")
        tenors = [t for t, _ in self.nodes]
        if any(b <= a for a, b in zip(tenors, tenors[1:])):
            raise ParamError(f"利率曲線節點年期必須嚴格遞增：{tenors}")


def par_to_continuous(y: float) -> float:
    """CMT par yield（半年複利 bond-equivalent，小數）→ 連續複利 zero rate。

    例（研究 §5）：y = 4.20% → 4.1565%。
    """
    return 2.0 * math.log(1.0 + y / 2.0)


def curve_from_par_yields(
    curve_date: str, pairs: tuple[tuple[float, float], ...]
) -> RateCurve:
    """(年期, par 小數) 逐節點轉連續複利，排序後建曲線。"""
    nodes = tuple(sorted((t, par_to_continuous(y)) for t, y in pairs))
    return RateCurve(curve_date=curve_date, nodes=nodes)


def rate_for_tenor(curve: RateCurve, tenor_years: float) -> float:
    """對連續複利 zero rate 相鄰節點線性插值；兩端夾住、不外插。"""
    nodes = curve.nodes
    if tenor_years <= nodes[0][0]:
        return nodes[0][1]
    if tenor_years >= nodes[-1][0]:
        return nodes[-1][1]
    for (t0, r0), (t1, r1) in zip(nodes, nodes[1:]):
        if t0 <= tenor_years <= t1:
            return r0 + (tenor_years - t0) * (r1 - r0) / (t1 - t0)
    raise AssertionError("unreachable: 節點嚴格遞增且已夾住兩端")


# ---------- Treasury 端點文字解析 ----------

# CSV 表頭如 "1 Mo"/"6 Mo"/"2 Yr"；歷史上亦出現過 "1.5 Month" 一類寫法。
_CSV_TENOR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(mo|month|yr|year)s?$",
                           re.IGNORECASE)
# XML 屬性如 BC_1MONTH / BC_1_5MONTH / BC_2YEAR；BC_30YEARDISPLAY 非 tenor。
_XML_TENOR_RE = re.compile(r"^BC_(\d+(?:_\d+)?)(MONTH|YEAR)$")


def _tenor_years(amount: str, unit: str) -> float:
    n = float(amount.replace("_", "."))
    return n / 12.0 if unit.lower().startswith("mo") else n


def _parse_curve_date(text: str) -> str:
    text = text.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        raise CurveParseError(f"無法解析曲線日期：{text!r}") from None


def _parse_percent(cell: str) -> float | None:
    try:
        return float(cell.strip()) / 100.0
    except (ValueError, AttributeError):
        return None                       # 空格／N/A → 該節點缺值，跳過


CurveRows = tuple[tuple[str, tuple[tuple[float, float], ...]], ...]


def parse_treasury_csv_rows(text: str) -> CurveRows:
    """Daily Treasury Par Yield Curve 年度 CSV → 全部有效資料列（曲線日, 節點）。

    只認得的 tenor 欄位進節點；不挑最新——由呼叫端決定要哪一列（`parse_treasury_csv`
    取全檔最大值；`curve_asof` 取不晚於某日期的最新一列）。任何一步落空都拋
    `CurveParseError`——寧可讓上層走 fallback，不默默給錯曲線。
    """
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as e:
        raise CurveParseError(f"CSV 解析失敗：{e}") from e
    if not rows:
        raise CurveParseError("CSV 無內容")
    header = [h.strip() for h in rows[0]]
    if not header or header[0].lower() != "date":
        raise CurveParseError(f"CSV 表頭不含 Date 欄：{header[:3]}")
    tenor_cols = {}
    for i, name in enumerate(header[1:], start=1):
        m = _CSV_TENOR_RE.match(name)
        if m:
            tenor_cols[i] = _tenor_years(m.group(1), m.group(2))
    if not tenor_cols:
        raise CurveParseError(f"CSV 表頭無可辨識的年期欄：{header}")

    result: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        curve_date = _parse_curve_date(row[0])
        pairs = tuple(
            (tenor, y)
            for i, tenor in tenor_cols.items()
            if i < len(row) and (y := _parse_percent(row[i])) is not None)
        if not pairs:
            continue
        result.append((curve_date, pairs))
    if not result:
        raise CurveParseError("CSV 無任何含利率節點的資料列")
    return tuple(result)


def parse_treasury_csv(text: str) -> RateCurve:
    """Daily Treasury Par Yield Curve 年度 CSV → 最新一列 → RateCurve。

    日期取全檔最大值（不假設列序）——實際挑選邏輯見 `parse_treasury_csv_rows`。
    """
    rows = parse_treasury_csv_rows(text)
    best = max(rows, key=lambda r: r[0])
    return curve_from_par_yields(*best)


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_treasury_xml_rows(text: str) -> CurveRows:
    """Treasury XML feed（Atom/OData）→ 全部有效 entry（曲線日, 節點）。

    不挑最新——理由與 `parse_treasury_csv_rows` 相同。
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as e:
        raise CurveParseError(f"XML 解析失敗：{e}") from e

    result: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    for entry in root.iter():
        if _localname(entry.tag) != "entry":
            continue
        curve_date: str | None = None
        pairs: list[tuple[float, float]] = []
        for el in entry.iter():
            name = _localname(el.tag)
            if name == "NEW_DATE" and el.text:
                curve_date = _parse_curve_date(el.text)
                continue
            m = _XML_TENOR_RE.match(name)
            if m and el.text and (y := _parse_percent(el.text)) is not None:
                pairs.append((_tenor_years(m.group(1), m.group(2)), y))
        if curve_date is None or not pairs:
            continue
        result.append((curve_date, tuple(pairs)))
    if not result:
        raise CurveParseError("XML 中沒有任何含日期與利率節點的 entry")
    return tuple(result)


def parse_treasury_xml(text: str) -> RateCurve:
    """Treasury XML feed（Atom/OData）→ 最新 entry → RateCurve（CSV 之備援）。"""
    rows = parse_treasury_xml_rows(text)
    best = max(rows, key=lambda r: r[0])
    return curve_from_par_yields(*best)


def curve_asof(rows: CurveRows, observation_date: str) -> RateCurve | None:
    """從一批（曲線日, 節點）資料列挑「不晚於 observation_date 的最新一列」建曲線。

    用於歷史 IV 重建的逐日點對點利率查詢（issue #160）：`observation_date`
    落在週末／假日等曲線資料缺席的日子時，取前一個有資料的交易日
    （ISO 日期字串可直接字典序比較，不需另外剖析成 `date`）。找不到任何
    不晚於 `observation_date` 的資料列（例如目標日早於資料起點）回傳
    `None`——不外插，讓呼叫端自行決定如何處理缺口。
    """
    eligible = [r for r in rows if r[0] <= observation_date]
    if not eligible:
        return None
    best = max(eligible, key=lambda r: r[0])
    return curve_from_par_yields(*best)


# ---------- 快取序列化（data.treasury 落盤用） ----------

def curve_to_dict(curve: RateCurve) -> dict:
    return {"curve_date": curve.curve_date,
            "nodes": [list(n) for n in curve.nodes],
            "stale": curve.stale}


def curve_from_dict(data: dict) -> RateCurve:
    # `.get("stale", False)`：既有已落盤的快取（本地檔案或 Neon）在這個
    # 欄位存在前寫入，沒有這把鑰匙——讀回來一律當「非陳舊」，不因為
    # 欄位新增就讓舊快取整批失效。
    return RateCurve(curve_date=data["curve_date"],
                     nodes=tuple((float(t), float(r))
                                 for t, r in data["nodes"]),
                     stale=bool(data.get("stale", False)))
