"""SECURITY-FIX-02：匿名濫用防護（vendor 成本）——純函式與設定值。

三層，全部擋在「真的準備送出一個上游請求」那一刻
（`main.py::_vendor_attempt()`）——**每個 provider attempt 各扣一次**：
自訂 provider 失敗退回 Cboe、Cboe 失敗退回 yfinance，一次刷新就是二到
三個 attempt、扣二到三次（失敗的 attempt 也算，它一樣用掉了 vendor 的
速率與成本）。一般頁面／詳細頁／usage-summary 讀取完全不經過這裡：

1. **per-owner quota**（Normal User）：60／分、300／時、800／天。Super
   User／Super Admin 豁免這一層與第 3 層（都是 owner 層）——但仍受
   source burst 與下面的 global fuse。
2. **source burst**：同一個來源（IP；IPv6 聚合到 /64）120／分、600／時，
   **刻意沒有每日上限**——大型 NAT（公司、學校、電信）後面的一群真人
   共用一個 IP，每日上限會誤殺他們；這一層只抓明顯的機器速率。
3. **new-owner tier**：建立未滿 24 小時的匿名 owner，全體加總每天最多
   用 global fuse 的 40%（fuse 2000 → 800）。擋的是「刪 cookie＋換 IP」
   一直拿到新的 owner 額度、直接吃光整個 fuse——既有使用者永遠保有
   其餘 60%。

最後一道是既有的 global vendor fuse（`vendor_fuse.py`，不分角色）。
三層一次原子檢查（`Storage.rate_limit_consume()` 全有或全無）：被任何
一層擋下的那次不扣任何一層的額度。

**IP 只拿來限流，永遠不是 owner 身分**，也從不落盤：寫進資料庫的只有
`source_key()`——用獨立 secret（`SOURCE_HMAC_SECRET`）做的 HMAC，而且
key 每天輪替（同一個 IP 隔天算出不同的值），計數列本身也有保留期
（`purge_rate_limits()`）。沒有設定 secret 時 source 這一層（以及
登入限流）**明確停用**，不會悄悄改用寫死的 key。
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from option_chaser.models import FetchError

from .vendor_fuse import GlobalVendorFuseTripped

MINUTE = 60
HOUR = 3600
DAY = 86400

# Launch Safety Defaults（Owner 裁示）——不是 production 分布校準值，
# 是「正常真人幾乎不可能撞到、只攔明顯自動化」的寬鬆起點。全部可用
# 環境變數覆寫，`<=0` 停用該視窗。
OWNER_VENDOR_QUOTA_PER_MINUTE = 60
OWNER_VENDOR_QUOTA_PER_HOUR = 300
OWNER_VENDOR_QUOTA_PER_DAY = 800
SOURCE_VENDOR_BURST_PER_MINUTE = 120
SOURCE_VENDOR_BURST_PER_HOUR = 600
NEW_OWNER_TIER_SHARE = 0.4
NEW_OWNER_TIER_AGE_HOURS = 24
# 登入：只擋高速猜密碼，不做「全站連錯 N 次就鎖死」——那會讓攻擊者
# 可以故意讓 Owner 登不進去。每個來源各自計數。
LOGIN_ATTEMPTS_PER_MINUTE = 10
LOGIN_ATTEMPTS_PER_HOUR = 60

# rate-limit 計數列在視窗結束後多久可以清掉。
RATE_LIMIT_RETENTION_SECONDS = HOUR

_EASTERN = ZoneInfo("America/New_York")


class UsageLimited(FetchError):
    """這個 owner／來源短時間內準備打上游的次數超過上限——不是 vendor
    回的錯，是我們自己擋下來的。繼承 `FetchError`：既有降級鏈（刷新
    失敗隔離、Refresh Run 分組失敗）不必為了它改變行為，只有
    `_classify_fetch_failure()` 會把它分類成 `usage_limited`。"""


class NewOwnerTierExhausted(GlobalVendorFuseTripped):
    """新 owner 共用的那一份 fuse 額度今天用完了。對使用者來說就是
    「今天的查詢預算用完了」，所以直接沿用 fuse 的分類（子類別）。"""


def window_start(now_epoch: float, seconds: int) -> int:
    return int(now_epoch // seconds) * seconds


def ny_day_bounds(now_epoch: float) -> tuple[str, int]:
    """紐約日曆日（global fuse 的「今天」，見 `clock.ny_today()`）與它
    的起點 epoch——new-owner tier 必須跟 fuse 同一條日界線，才會是
    「fuse 當日額度的 40%」。"""
    local = datetime.fromtimestamp(now_epoch, _EASTERN)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.date().isoformat(), int(start.timestamp())


def new_owner_tier_pool(daily_budget: int, share: float) -> int:
    if daily_budget <= 0 or share <= 0:
        return 0
    return int(daily_budget * share)


# ---------- 可信的來源 IP ----------

def default_trusted_ip_header() -> str | None:
    """Vercel 會**覆寫** `x-forwarded-for`、不轉送外部送進來的值（官方
    文件 https://vercel.com/docs/headers/request-headers ：「Vercel
    overwrites this header and does not forward external IPs to prevent
    spoofing」；例外是 Enterprise 的 trusted proxy，本專案不適用）。
    所以只有**跑在 Vercel 上**（`VERCEL` 環境變數存在）才信任這個
    header；其他環境（本機、測試）一律用 TCP 連線的對端位址，不信任
    任何人都能自己塞的 header。`TRUSTED_CLIENT_IP_HEADER` 可以明確覆寫
    （`none`＝一律用對端位址）。"""
    override = os.environ.get("TRUSTED_CLIENT_IP_HEADER")
    if override is not None:
        return None if override.strip().lower() in ("", "none") else override.strip().lower()
    return "x-forwarded-for" if os.environ.get("VERCEL") else None


def client_ip(headers, peer: str | None, trusted_header: str | None) -> str | None:
    """回正規化後的 IP 字串；拿不到或不是合法 IP 就回 `None`（這個請求
    就不做 source 層限流——寧可少擋一次，也不把一堆請求算到同一個
    「未知」桶裡互相誤傷）。"""
    candidate = None
    if trusted_header:
        raw = headers.get(trusted_header)
        if raw:
            candidate = raw.split(",")[0].strip()
    else:
        candidate = peer
    if not candidate:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def source_network(ip: str) -> str:
    """IPv4 用完整位址；IPv6 聚合到 /64（一般用戶端一條線就拿到整個
    /64，逐位址限流形同虛設）；IPv4-mapped IPv6 當成 IPv4。"""
    addr = ipaddress.ip_address(ip)
    if addr.version == 6:
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def source_key(ip: str, secret: str, now_epoch: float) -> str:
    """HMAC-SHA256(每日衍生 key, 網段)。每日 key＝HMAC(secret, 日期)，
    所以同一個 IP 隔天得到完全不同的值——資料庫裡沒有任何東西能把
    不同天的行為串回同一個來源，也反推不回 IP。"""
    day = int(now_epoch // DAY)
    day_key = hmac.new(secret.encode(), f"source-key:{day}".encode(),
                       hashlib.sha256).digest()
    return hmac.new(day_key, source_network(ip).encode(),
                    hashlib.sha256).hexdigest()[:32]
