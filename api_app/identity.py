"""User identity resolver（Ownership A-1／SCALE-06，#256，Scaling
Foundation；cookie-based 切換＝PB-02／#294，Anonymous Public Beta）。

**A-1 只建立 data boundary，不是 authentication／privacy**（那是
out-of-scope 的 A-2）——`IdentityResolver` 本身仍是一個零參數
callable，不論背後實作是固定常數還是讀取 ContextVar，回傳值單純是
「這次 request 屬於誰」，不是驗證結果。

做成一個可注入的介面而不是到處寫死字串常數，純粹是讓 `create_app()`
的呼叫端（測試／軸二 Super User）可以替換掉「怎麼決定這次 request
屬於誰」這件事，不需要改任何讀寫這個值的下游程式碼——與
`RateCurveLoader`／`DividendLoader` 等既有 DI 介面同一種設計理由。

PB-02（#294）起，`create_app()` 的 production 預設從
`default_identity_resolver`（固定 `"solo"`）換成
`cookie_identity_resolver`（讀取這個模組自己的 ContextVar，值由
`main.py` 的 cookie middleware 解析或建立）。**`default_identity_
resolver()`／`SOLO_OWNER` 本身未被刪除、行為未變**（spec §18 明訂
本輪不要求刪除）——既有測試與未來任何想要「不管 cookie、固定回同一個
身份」的呼叫端仍可透過 `create_app(identity_resolver=
default_identity_resolver)`（或等價的 `lambda: SOLO_OWNER`）顯式選用，
這正是 DI 介面存在的目的。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

IdentityResolver = Callable[[], str]

# SCALE-06（#256）遺留：固定值，不做任何驗證。PB-02（#294）起不再是
# production 預設，保留供顯式選用（見檔頭說明）。
SOLO_OWNER = "solo"


def default_identity_resolver() -> str:
    """固定回傳 `SOLO_OWNER`，不做任何驗證、不讀取任何 request 狀態
    ——PB-02（#294）之前的唯一 production 行為。現在只在明確選用時
    才會被呼叫（見檔頭）。"""
    return SOLO_OWNER


# ---------- PB-02（#294）：cookie-based owner 解析 ----------
#
# 與 `diagnostics.py` 的 `correlation_id`／`owner_id` 兩個 ContextVar
# 同一種寫法（不從函式簽章往下傳）：`main.py` 的 cookie middleware 在
# request 開頭解析（或建立）出這次 request 的 owner_id，用
# `resolved_owner_scope()` 塞進這裡；`cookie_identity_resolver()`
# ——`create_app()` 新的 production 預設——單純讀取它，讓
# `IdentityResolver`「無參數 callable」的介面維持不變，main.py 內部
# 27 個既有 `identity_resolver()` 呼叫點因此不需要知道背後從常數換成
# 了 ContextVar 讀取。

_resolved_owner_id: ContextVar[str | None] = ContextVar(
    "resolved_owner_id", default=None)


@contextmanager
def resolved_owner_scope(owner_id: str | None) -> Iterator[str | None]:
    """`main.py` 的 cookie middleware 解析／建立出這次 request 的
    owner_id 之後（或判定這個路由被排除、`owner_id` 為 `None`）用這個
    context manager 包住 `call_next()`。"""
    token = _resolved_owner_id.set(owner_id)
    try:
        yield owner_id
    finally:
        _resolved_owner_id.reset(token)


def cookie_identity_resolver() -> str:
    """`create_app()` 起（PB-02／#294）的新 production 預設。**必須**
    在 middleware 已經呼叫過 cookie 解析／建立邏輯、並用
    `resolved_owner_scope()` 設定過非 `None` 的 owner_id 之後才能被
    呼叫；若在那之前、或在被排除的路由上（spec §4 的路由白名單）
    意外被呼叫，代表某段程式碼繞過了 middleware 的單一判斷點——寧可
    在這裡大聲失敗，也不要悄悄用一個沒人請求過的值建立 owner 或製造
    跨 owner 洩漏。"""
    owner_id = _resolved_owner_id.get()
    if owner_id is None:
        raise RuntimeError(
            "cookie_identity_resolver() 在這個 request 還沒有解析出 "
            "owner_id 前就被呼叫——代表某段程式碼繞過了 cookie "
            "middleware（_request_scope_middleware）的單一判斷點，"
            "或這個路由本應被排除在 owner-scoped 流程之外卻呼叫到了 "
            "identity_resolver()")
    return owner_id
