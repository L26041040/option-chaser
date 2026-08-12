"""自訂資料源的 Provider 註冊表與 token 遮罩（Settings／#124）。

**自訂不等於任意 API**：使用者只能從本檔案這份清單挑選，不能填入任意
endpoint 或 schema——每個 Provider 都得先在本系統有一支對應的 adapter
（`option_chaser/data/base.py` 的 `ChainProvider` 協定），資料才進得了
引擎。註冊表因此是白名單，不是建議清單。

UI 文案的用詞在此定調並由測試守門（#124）：寫「目前支援」，不寫
「推薦」；不做 vendor 比較、不寫未來規劃。理由是這份清單描述的是
**系統現在有沒有那支 adapter**，與哪一家比較好無關——寫成推薦會讓
使用者以為我們在替他選 vendor。
"""
from __future__ import annotations

from dataclasses import dataclass

# 兩個資料用途（Settings 的 `Data / API` 兩列）。
MARKET_DATA = "market_data"
HISTORICAL_IV = "historical_iv"
USAGES = (MARKET_DATA, HISTORICAL_IV)

# 每一列的兩種模式。
MODE_DEFAULT = "default"
MODE_CUSTOM = "custom"
MODES = (MODE_DEFAULT, MODE_CUSTOM)

# 「預設」是什麼，各列不同——Market Data 有內建免 credential 的來源，
# Historical IV 沒有（所以預設是「無」，模組整個不出現，見 #126）。
DEFAULT_LABELS = {MARKET_DATA: "Cboe", HISTORICAL_IV: "無"}


@dataclass(frozen=True)
class Provider:
    id: str
    label: str


# 目前只有一家。多一家就在這裡多一列，UI 與驗證都不必改。
MARKETDATA_APP = Provider(id="marketdata-app", label="Market Data App")
SUPPORTED_PROVIDERS: tuple[Provider, ...] = (MARKETDATA_APP,)


def is_supported(provider_id: str) -> bool:
    return any(p.id == provider_id for p in SUPPORTED_PROVIDERS)


def label_for(provider_id: str) -> str | None:
    for p in SUPPORTED_PROVIDERS:
        if p.id == provider_id:
            return p.label
    return None


# 遮罩後保留的尾碼長度——足以讓使用者認出「這是我貼的那把」，又不足以
# 重建 token。
_TAIL = 4
_BULLETS = "••••••••"


def mask_token(token: str) -> str:
    """遮罩形式——**這是 token 唯一允許離開後端的樣子**。

    前置的圓點是固定長度、不隨 token 長短變化：跟著變的話，遮罩本身就
    洩漏了長度。太短而無尾碼可露時整串遮掉，不退而露出更多。
    """
    if len(token) <= _TAIL:
        return _BULLETS
    return _BULLETS + token[-_TAIL:]
