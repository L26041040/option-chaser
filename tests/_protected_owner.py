"""AUTH-04（#311，Anonymous Public Beta，三層角色模型 spec #307）共用
小工具：確保某個 owner_id 在 storage 的 `owners` 表裡有一列、並設定
`protected` 旗標——`_iv_history_gate()` 的核心依賴（見 `api_app/
main.py::_the_protected_owner_id()`）。

多個既有／新增的 iv-history 測試檔固定用 `identity_resolver=lambda:
"..."` 覆寫身份解析，完全繞過 PB-02 的 cookie／owner 表建立流程（那條
路徑只在 production 的 `cookie_identity_resolver` 才會觸發）——
`owners` 表因此原本一列都沒有。`Storage.set_owner_protected()` 對
不存在的 owner_id 是刻意的靜默 no-op（既有寫入端「不存在就安靜地
什麼都不做」慣例，見 `postgres.py`／`memory.py` 該方法 docstring），
所以必須先確保這一列真的存在，才呼叫它。
"""
from __future__ import annotations

from api_app.storage import BrowserIdentity, Owner


def ensure_owner(storage, owner_id: str, *, protected: bool = True) -> None:
    """比照 PB-03 遷移腳本的精神：先確保 `owner_id` 在 `owners` 表裡
    有一列（若沒有，補一筆最小、可辨識為測試用途的 owner＋配對的
    `BrowserIdentity`——`create_owner_with_token()` 的兩筆寫入視為
    同一次邏輯操作的既有分工），再設定 `protected` 旗標。

    `protected` 預設 `True`——多數呼叫端只是想要「這個 owner 存在且
    受保護」；AUTH-04 的邊界情況測試（0 個／多於 1 個 protected owner）
    需要明確建立**不受保護**的 owner，因此保留這個參數而非寫死。"""
    if storage.get_owner(owner_id) is None:
        storage.create_owner_with_token(
            Owner(owner_id=owner_id, created_at="2026-01-01T00:00:00+00:00"),
            BrowserIdentity(token=f"test-owner-{owner_id}",
                            owner_id=owner_id,
                            issued_at="2026-01-01T00:00:00+00:00",
                            last_seen_at="2026-01-01T00:00:00+00:00"))
    storage.set_owner_protected(owner_id, protected)


def ensure_protected_owner(storage, owner_id: str) -> None:
    """`ensure_owner(storage, owner_id, protected=True)` 的明確別名，
    供只需要「這個 owner 存在且受保護」的既有呼叫端使用（多數情況）。"""
    ensure_owner(storage, owner_id, protected=True)
