"""Vercel Python function：GET /api/health。

Vercel 依檔案系統路由——`api/health.py` 即 `/api/health`，因此不需要
任何 rewrite 把 `/api/*` 導過來（rewrite 是否保留原始路徑在不同專案
模式下行為不同，靠檔名對齊路由可完全避開這個不確定性）。

前 6 行的 sys.path 前置在 `api/analyze.py` 是重複的——刻意如此：這兩個
檔案是各自獨立的 lambda 進入點，共用一個 helper 反而要先假設「同目錄
可匯入」，那正是這裡要消除的假設。
"""
import sys
from pathlib import Path

# `api_app` 與 `option_chaser` 都不是被 pip 安裝的套件（requirements.txt
# 只裝第三方依賴），repo 根目錄也不保證在 sys.path 上——明確加進來。
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api_app.main import create_app  # noqa: E402

app = create_app()   # 直接賦值：進入點偵測認的是這個，不是匯入再轉出
