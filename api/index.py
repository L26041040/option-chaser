"""Vercel Python function 進入點（V1／#48）。

Vercel 支援直接載入 ASGI app；真正的應用在 `api_app/`（可被 pytest
以測試客戶端直測，不需要起伺服器）。此檔刻意只做轉接，不放任何邏輯。
"""
from api_app.main import app

__all__ = ["app"]
