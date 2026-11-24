#!/usr/bin/env python
"""更新 repo 內的 S&P 500 成分股清單（V2-01／#404）。手動執行、可重跑。

來源：Wikipedia「List of S&P 500 companies」（CC BY-SA 4.0），經 MediaWiki
API 取一個**固定版本**（revision id），只取成分股表格的代號與公司名稱，產生
`api_app/sp500_constituents.py`，並印出與 repo 現有版本的差異報告（新增／
移除的代號）。執行期完全不連網：網站掛了、改版了，只是這支工具跑不動，
線上系統照用 repo 裡的最後一版。來源、授權與更新頻率見
`docs/spec/options-scanner/sp500-constituents.md`。

    SSL_CERT_FILE=/root/.ccr/ca-bundle.crt PYTHONPATH=. .venv/bin/python \\
        scripts/update_sp500_constituents.py            # 取最新版、寫檔、印差異
    ... scripts/update_sp500_constituents.py --dry-run  # 只印差異，不寫檔

解析或檢查（檔數、重複、代號格式）任一項不過就整個停下、不寫檔——寧可
沿用舊清單，也不寫進半份或格式不對的清單。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAGE_TITLE = "List of S&P 500 companies"
API_URL = "https://en.wikipedia.org/w/api.php"
# Wikimedia 要求自動化請求帶可辨識的 User-Agent；不帶任何個人資訊。
USER_AGENT = "option-chaser-constituents-updater/1.0 (manual, low-volume)"
OUTPUT = Path(__file__).resolve().parent.parent / "api_app" / "sp500_constituents.py"
LICENSE = "CC BY-SA 4.0"

# 指數 500 家公司、約 503 檔（多股權類別）；超出這個範圍代表頁面改版或解析錯了。
MIN_COUNT, MAX_COUNT = 490, 520
# canonical 代號：1–5 個字母，股權類別用一個 `.` 接一個字母（BRK.B、BF.B）。
_CANONICAL = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
_SYMBOL_TEMPLATE = re.compile(r"\{\{\s*[^|{}]+\|\s*([^|{}\s]+)\s*\}\}")
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_REF = re.compile(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)
_CELL_SPLIT = re.compile(r"\|\||^\s*\|", re.M)


class ParseError(ValueError):
    """頁面結構或清單內容不像 S&P 500 成分股表——不寫檔。"""


def _table(wikitext: str) -> str:
    start = wikitext.find('id="constituents"')
    if start < 0:
        raise ParseError('找不到 id="constituents" 的成分股表格（頁面可能改版）')
    end = wikitext.find("\n|}", start)
    if end < 0:
        raise ParseError("成分股表格沒有結尾（頁面可能改版）")
    return wikitext[start:end]


def _plain(cell: str) -> str:
    return " ".join(_LINK.sub(r"\1", cell).split()).strip()


def parse_constituents(wikitext: str) -> list[tuple[str, str]]:
    """成分股表格 → `[(代號, 公司名稱)]`，依表格順序。代號照 Wikipedia 原樣
    （它本來就用 canonical 點寫法 `BRK.B`）。"""
    table = _REF.sub("", _COMMENT.sub("", _table(wikitext)))
    out: list[tuple[str, str]] = []
    for row in table.split("\n|-")[1:]:
        cells = [c.strip() for c in _CELL_SPLIT.split(row) if c.strip()]
        if not cells or cells[0].startswith("!"):
            continue                                  # 表頭
        match = _SYMBOL_TEMPLATE.search(cells[0])
        if match is None or len(cells) < 2:
            raise ParseError(f"看不懂的成分股列：{row.strip()[:80]!r}")
        out.append((match.group(1).strip().upper(), _plain(cells[1])))
    return out


def validate(rows) -> None:
    rows = list(rows)
    if not MIN_COUNT <= len(rows) <= MAX_COUNT:
        raise ParseError(f"檔數 {len(rows)} 不在 {MIN_COUNT}–{MAX_COUNT} 之間")
    seen: set[str] = set()
    for symbol, _ in rows:
        if not _CANONICAL.fullmatch(symbol):
            raise ParseError(f"不合法的代號：{symbol!r}")
        if symbol in seen:
            raise ParseError(f"代號重複：{symbol}")
        seen.add(symbol)


def diff_report(old, new, *, old_version: str, new_version: str) -> str:
    """差異報告（純文字）：版本、檔數、新增與移除的代號（依代號排序）。"""
    old_map, new_map = dict(old), dict(new)
    added = sorted(set(new_map) - set(old_map))
    removed = sorted(set(old_map) - set(new_map))
    lines = [f"S&P 500 成分股：{old_version} → {new_version}",
             f"檔數：{len(old_map)} → {len(new_map)}",
             f"新增 {len(added)} 檔："]
    lines += [f"  + {s}  {new_map[s]}" for s in added]
    lines.append(f"移除 {len(removed)} 檔：")
    lines += [f"  - {s}  {old_map[s]}" for s in removed]
    return "\n".join(lines) + "\n"


def source_url(revision: int) -> str:
    title = urllib.parse.quote(PAGE_TITLE.replace(" ", "_"))
    return f"https://en.wikipedia.org/w/index.php?title={title}&oldid={revision}"


def render_module(rows, *, effective_date: str, revision: int,
                  retrieved_at: str) -> str:
    body = "\n".join(f"    ({json.dumps(s)}, {json.dumps(n, ensure_ascii=False)}),"
                     for s, n in rows)
    return f'''"""S&P 500 成分股清單（V2-01／#404）。**自動產生，請勿手改**——用
`scripts/update_sp500_constituents.py` 更新，說明見
`docs/spec/options-scanner/sp500-constituents.md`。

資料來源：Wikipedia「{PAGE_TITLE}」revision {revision}
（{source_url(revision)}），
授權 {LICENSE}（https://creativecommons.org/licenses/by-sa/4.0/）。本檔只收
代號與公司名稱兩欄；本檔內容依同一授權提供（姓名標示：Wikipedia 貢獻者）。

代號一律 canonical 點寫法（`BRK.B`、`BF.B`），各資料來源的寫法由
`option_chaser.symbols` 轉換；GOOGL／GOOG 等多股權類別各自是一檔。
"""

# 版本＝生效日期：取用的 Wikipedia 版本的編輯日期（UTC）。
VERSION = {json.dumps(effective_date)}
SOURCE_REVISION = {revision}
SOURCE_URL = {json.dumps(source_url(revision))}
RETRIEVED_AT = {json.dumps(retrieved_at)}
LICENSE = {json.dumps(LICENSE)}

CONSTITUENTS: tuple[tuple[str, str], ...] = (
{body}
)
'''


def fetch_latest() -> tuple[str, int, str]:
    """回 `(wikitext, revision id, revision timestamp)`。一個請求。"""
    query = urllib.parse.urlencode({
        "action": "query", "prop": "revisions", "titles": PAGE_TITLE,
        "rvprop": "ids|timestamp|content", "rvslots": "main",
        "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rev = payload["query"]["pages"][0]["revisions"][0]
    return rev["slots"]["main"]["content"], int(rev["revid"]), rev["timestamp"]


def _committed():
    try:
        from api_app import sp500_constituents as current
    except ImportError:
        return [], "（尚無）"
    return list(current.CONSTITUENTS), f"{current.VERSION}（rev {current.SOURCE_REVISION}）"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="只印差異，不寫檔")
    args = parser.parse_args(argv)

    wikitext, revision, timestamp = fetch_latest()
    rows = parse_constituents(wikitext)
    validate(rows)
    effective = timestamp[:10]
    old_rows, old_version = _committed()
    print(diff_report(old_rows, rows, old_version=old_version,
                      new_version=f"{effective}（rev {revision}）"), end="")
    if args.dry_run:
        print("（--dry-run：未寫檔）")
        return 0
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    OUTPUT.write_text(render_module(rows, effective_date=effective, revision=revision,
                                    retrieved_at=retrieved), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
