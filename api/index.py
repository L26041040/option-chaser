"""Vercel Python function：整個 HTTP API 的單一進入點。

`vercel.json` 把 `/api/(.*)` 全部 rewrite 到這裡，FastAPI 再依**原始
路徑**自己路由——這點是實測確認的（2026-08-03）：對
`/api/probe/scenarios/abc/archive` 打進來時，app 回的是 FastAPI 自己的
404，而不是 rewrite 目的地 `/api/health` 的 200，證明 ASGI 收到的是
原始路徑而非改寫後路徑。因此動態路徑（`/api/scenarios/{id}/archive`）
可以正常運作，不需要為每條路由各開一個檔案。
"""
import sys
from pathlib import Path

# `api_app` 與 `option_chaser` 都不是被 pip 安裝的套件（pyproject 的
# packages.find 只收 option_chaser*），repo 根目錄也不保證在 sys.path
# 上——明確加進來。
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api_app.main import create_app  # noqa: E402

app = create_app()   # 直接賦值：進入點偵測認的是這個，不是匯入再轉出
