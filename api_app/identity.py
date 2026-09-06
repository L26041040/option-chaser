"""User identity resolver（Ownership A-1／SCALE-06，#256，Scaling
Foundation）。

**A-1 只建立 data boundary，不是 authentication／privacy**（那是
out-of-scope 的 A-2）——一個固定、無驗證的 solo-owner identity resolver
不能防止冒充，它只是把「每一筆資料屬於誰」這個維度先物理地存在資料
裡，供未來 A-2 接上真正的驗證機制時，查詢過濾（SCALE-11）與資料遷移
（SCALE-13）不需要再回頭補欄位。

做成一個可注入的介面（`IdentityResolver`）而不是到處寫死字串常數，
純粹是讓 `create_app()` 的呼叫端（測試／未來 A-2）可以替換掉「怎麼
決定這次 request 屬於誰」這件事，不需要改任何讀寫這個值的下游程式碼
——與 `RateCurveLoader`／`DividendLoader` 等既有 DI 介面同一種設計
理由。
"""
from __future__ import annotations

from typing import Callable

IdentityResolver = Callable[[], str]

# 今天唯一存在的 owner——固定值，不做任何驗證。
SOLO_OWNER = "solo"


def default_identity_resolver() -> str:
    """production 預設：固定 solo-owner。"""
    return SOLO_OWNER
