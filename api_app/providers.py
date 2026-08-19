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


# ---------- Provider 存取的可注入接縫（Settings／#125） ----------

@dataclass(frozen=True)
class VerifyOutcome:
    """「這把 token 現在能不能用」。失敗時 `reason` 是給人看的整句話，
    **絕不含 token**。"""
    ok: bool
    reason: str | None = None


def default_verify(provider_id: str, token: str) -> VerifyOutcome:
    """真實驗證：依 provider 分派到對應 adapter。

    可被 `create_app(verify_provider=...)` 覆寫——測試因此全程離線，不打
    真 vendor（#125 硬性 AC）。
    """
    if provider_id == MARKETDATA_APP.id:
        from option_chaser.data import marketdata

        got = marketdata.verify(token)
        return VerifyOutcome(got.ok, got.reason)
    return VerifyOutcome(False, f"不支援的資料源：{provider_id}")


def default_fetch_chain(provider_id: str, symbol: str, token: str):
    """自訂資料源的抓鏈路徑。失敗一律是 `FetchError`（adapter 已收斂），
    由呼叫端決定要不要退回預設來源。"""
    if provider_id == MARKETDATA_APP.id:
        from option_chaser.data import marketdata

        return marketdata.fetch_chain(symbol, token)
    from option_chaser.models import FetchError

    raise FetchError(f"不支援的資料源：{provider_id}")


def default_historical_surface(provider_id: str, symbol: str, on_date: str,
                               token: str, expiration: str | None = None,
                               observer=None,
                               ) -> dict[str, list]:
    """某一歷史日期的 (dte, delta, iv) 座標點，依權別分組（#126／#134）。

    `expiration` 是可選的到期日篩選（#134）：不帶時交給 vendor 用預設
    行為（下一個月選），帶了就只回那一個到期日的合約——由呼叫端
    （`api_app.main._backfill_iv`）決定要不要篩、篩哪些。

    `observer`（#144／#146）：原樣轉給 `marketdata.fetch_surface`——這一層
    只是接線，不解讀 telemetry 內容，也不 import 任何診斷模組。
    """
    if provider_id == MARKETDATA_APP.id:
        from option_chaser.data import marketdata

        return marketdata.fetch_surface(symbol, on_date, token,
                                        expiration=expiration,
                                        observer=observer)
    from option_chaser.models import FetchError

    raise FetchError(f"不支援的資料源：{provider_id}")


def default_contract_history(provider_id: str, occ_symbol: str, from_date: str,
                             to_date: str, token: str, observer=None,
                             ) -> list[dict]:
    """一張 exact contract 在 `[from_date, to_date]` 的歷史 quote 序列
    （HIVT-02／#153，寬版欄位見 HIVR-04／#163）——跟
    `default_historical_surface`（整鏈、逐日重錨定用）是不同的資料
    語意，這裡對應的是 spec #151 §2 絕對紅線的 exact-contract 家族，
    兩者不共用呼叫路徑。

    `observer`：原樣轉給 `marketdata.fetch_contract_history`——這一層
    只是接線，不解讀 telemetry 內容，也不 import 任何診斷模組（比照
    `default_historical_surface` 既有慣例）。
    """
    if provider_id == MARKETDATA_APP.id:
        from option_chaser.data import marketdata

        return marketdata.fetch_contract_history(occ_symbol, from_date, to_date,
                                                  token, observer=observer)
    from option_chaser.models import FetchError

    raise FetchError(f"不支援的資料源：{provider_id}")
