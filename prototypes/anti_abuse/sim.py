"""ANTI-ABUSE-PROTOTYPE-001：匿名濫用防護的離線模擬器。

**完全獨立**：不 import `api_app`／`option_chaser`，不碰任何資料庫、網路、
secret。時間是模擬秒數，IP 是假的（TEST-NET／ULA 範圍），HMAC key 是
寫死的假值。它模擬的是「如果 production 加上這幾層，會發生什麼」，
不是 production 本身。

模型刻意貼齊 current master 的事實（見 `checks_current_master.py`）：

- 一次「完整刷新」＝ owner 名下每個 distinct symbol 各一次上游抓鏈
  （ADR-0001：只在單一 Refresh Run 內去重）。
- owner 身分只看 cookie；沒帶 cookie 的 owner-scoped 請求一律新建
  owner（`eager` 模式＝現況）。
- 全站只有一道 global fuse（`GLOBAL_VENDOR_DAILY_BUDGET`，預設 2000）。
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import random
from collections import Counter
from dataclasses import dataclass, field

DAY = 86_400
HOUR = 3_600
MINUTE = 60


# ---------- Layer 1／2 共用：固定視窗計數器 ----------

@dataclass(frozen=True)
class Window:
    seconds: int
    limit: int


class WindowedLimiter:
    """每個 key 對每個視窗各記一組 (視窗起點, 次數)。全部視窗都還有
    額度才放行，放行時全部視窗一起扣——被擋的請求不扣（不懲罰重試
    本身，只擋超額）。state 大小＝目前活著的 key 數。"""

    def __init__(self, windows: tuple[Window, ...]):
        self.windows = windows
        self.state: dict[str, list[list[int]]] = {}
        self.last_used: dict[str, float] = {}

    def allow(self, key: str, now: float, cost: int = 1) -> bool:
        if not self.windows:
            return True
        slots = self.state.setdefault(key, [[-1, 0] for _ in self.windows])
        for slot, w in zip(slots, self.windows):
            start = int(now // w.seconds) * w.seconds
            if slot[0] != start:
                slot[0], slot[1] = start, 0
            if slot[1] + cost > w.limit:
                return False
        for slot in slots:
            slot[1] += cost
        self.last_used[key] = now
        return True

    def purge(self, now: float, idle_seconds: float) -> int:
        """retention：閒置超過 `idle_seconds` 的 key 整筆丟掉——不永久
        保存任何 source identity。回傳丟掉幾筆。"""
        dead = [k for k, t in self.last_used.items() if now - t > idle_seconds]
        for k in dead:
            self.state.pop(k, None)
            self.last_used.pop(k, None)
        return len(dead)


# ---------- Layer 2：source key（不依賴 cookie） ----------

class SourceKeyer:
    """把 IP 轉成 abuse-control 用的 key。**只用來限流，不當資料
    identity**——owner 永遠只看 cookie，這裡算出來的東西不會寫進任何
    owner／scenario 資料。

    - `raw`：直接用 IP 字串（對照組：state 裡等於留著明文 IP）。
    - `hmac`：HMAC-SHA256(每日輪替的 key, 網段) 取前 16 hex。key 每
      `rotate_seconds` 換一次，舊 key 丟掉後同一個 IP 算出的值就對不
      回去——配合 limiter 的 idle purge，沒有任何東西能長期把某個 IP
      跟某段行為連起來。
    - IPv6 一律聚合到 /64（一般用戶端一條線就拿到整個 /64，逐位址
      限流形同虛設）；IPv4 用完整位址。
    """

    FAKE_BASE_SECRET = b"prototype-only-not-a-real-secret"

    def __init__(self, mode: str = "hmac", rotate_seconds: int = DAY):
        assert mode in {"raw", "hmac"}
        self.mode = mode
        self.rotate_seconds = rotate_seconds

    @staticmethod
    def network(ip: str) -> str:
        addr = ipaddress.ip_address(ip)
        if addr.version == 6:
            return str(ipaddress.ip_network(f"{ip}/64", strict=False))
        return ip

    def key(self, ip: str, now: float) -> str:
        net = self.network(ip)
        if self.mode == "raw":
            return net
        epoch = int(now // self.rotate_seconds)
        day_key = hmac.new(self.FAKE_BASE_SECRET, str(epoch).encode(),
                           hashlib.sha256).digest()
        return hmac.new(day_key, net.encode(), hashlib.sha256).hexdigest()[:16]


# ---------- Layer 3：global fuse ----------

class GlobalFuse:
    """全站每日上限（現況：flat 2000）。`new_owner_share` 非 None 時
    改成 tiered：建立未滿 `established_after` 秒的 owner，全體加總最多
    只能用掉當日 budget 的這個比例——剩下的保留給既有使用者。"""

    def __init__(self, budget: int, new_owner_share: float | None = None,
                 established_after: float = DAY):
        self.budget = budget
        self.new_owner_share = new_owner_share
        self.established_after = established_after
        self.day = -1
        self.used = 0
        self.used_by_new = 0

    def _roll(self, now: float) -> None:
        d = int(now // DAY)
        if d != self.day:
            self.day, self.used, self.used_by_new = d, 0, 0

    def allow(self, now: float, owner_age: float) -> bool:
        self._roll(now)
        if self.budget <= 0:
            return True                  # 停用（整個 fuse，含 tiered 部分）
        if self.used >= self.budget:
            return False
        is_new = owner_age < self.established_after
        if (self.new_owner_share is not None and is_new
                and self.used_by_new >= self.budget * self.new_owner_share):
            return False
        return True

    def charge(self, now: float, owner_age: float) -> None:
        self._roll(now)
        self.used += 1
        if owner_age < self.established_after:
            self.used_by_new += 1


# ---------- 上游去重 ----------

class NoDedupe:
    name = "none"

    def upstream_needed(self, symbol: str, now: float, rng: random.Random) -> bool:
        return True


class SingleFlight:
    """同一時刻同一 symbol 只打一次上游，其餘等那一次的結果。**不存
    payload**：結果只活在那次抓取進行中的 `latency` 秒內，抓完就沒了。

    `instances`：serverless 下 single-flight 只在同一個 instance 的記憶
    體內有效。`instances=1` 是最佳情況（所有並發請求都落在同一個可
    並發的 instance）；`instances=N` 是請求隨機分散到 N 個 instance、
    彼此看不到對方的 in-flight。"""

    def __init__(self, latency: float = 1.5, instances: int = 1):
        self.latency = latency
        self.instances = instances
        self.name = f"single-flight(inst={instances})"
        self.inflight_until: dict[tuple[int, str], float] = {}

    def upstream_needed(self, symbol: str, now: float, rng: random.Random) -> bool:
        inst = rng.randrange(self.instances)
        until = self.inflight_until.get((inst, symbol), -1.0)
        if now < until:
            return False
        self.inflight_until[(inst, symbol)] = now + self.latency
        return True


class TTLReuse:
    """極短 TTL 跨請求重用（**只模擬**）：抓完後 `ttl` 秒內同 symbol 的
    請求直接拿那份結果。這需要一個跨 instance 共享、存著 chain payload
    的地方——就是 ADR-0001 否決過的 shared chain cache，也是跨使用者
    重用市場資料，碰 licensing gate。這裡只算它能省多少。"""

    def __init__(self, ttl: float, latency: float = 1.5):
        self.ttl = ttl
        self.latency = latency
        self.name = f"ttl={int(ttl)}s"
        self.fresh_until: dict[str, float] = {}

    def upstream_needed(self, symbol: str, now: float, rng: random.Random) -> bool:
        if now < self.fresh_until.get(symbol, -1.0):
            return False
        self.fresh_until[symbol] = now + self.latency + self.ttl
        return True


# ---------- 整個系統 ----------

@dataclass
class OwnerRec:
    created_at: float
    scenarios: int = 0
    symbols: tuple[str, ...] = ()
    last_seen: float = 0.0
    last_activity: float | None = None
    garbage: bool = False       # 模擬用標記：這個 owner 是濫用流量造出來的


@dataclass
class Config:
    name: str
    owner_windows: tuple[Window, ...] = ()
    source_windows: tuple[Window, ...] = ()
    owner_create_windows: tuple[Window, ...] = ()   # 每個 source 可建幾個 owner
    global_owner_create_per_day: int = 0            # 全站每天最多建幾個 owner（0＝不限）
    fuse_budget: int = 2000
    fuse_new_owner_share: float | None = None
    eager_owner_creation: bool = True               # 現況：任何 GET 就建 owner
    source_mode: str = "hmac"
    dedupe: object = field(default_factory=NoDedupe)
    source_idle_purge: float = 2 * DAY
    # fair-share brake：fuse 用掉這個比例之後，今天已經用了 ≥ cap 次的
    # owner 先暫停，把剩下的額度留給還沒怎麼用的人（None＝關閉）
    fair_share_after: float | None = None
    fair_share_owner_cap: int = 100


class System:
    def __init__(self, cfg: Config, seed: int = 0):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.owner_limiter = WindowedLimiter(cfg.owner_windows)
        self.source_limiter = WindowedLimiter(cfg.source_windows)
        self.create_limiter = WindowedLimiter(cfg.owner_create_windows)
        self.global_create = WindowedLimiter(
            (Window(DAY, cfg.global_owner_create_per_day),)
            if cfg.global_owner_create_per_day else ())
        self.fuse = GlobalFuse(cfg.fuse_budget, cfg.fuse_new_owner_share)
        self.keyer = SourceKeyer(cfg.source_mode)
        self.owners: dict[str, OwnerRec] = {}
        self.cookie_to_owner: dict[str, str] = {}
        self.n = 0
        self.stats = Counter()
        self.peak_source_keys = 0
        self.owner_day_use: Counter = Counter()      # (owner, day) -> 今天已放行次數

    # --- identity ---
    def _new_owner(self, now: float, garbage: bool) -> str:
        self.n += 1
        oid = f"o{self.n}"
        self.owners[oid] = OwnerRec(created_at=now, last_seen=now, garbage=garbage)
        self.stats["owners_created"] += 1
        if garbage:
            self.stats["garbage_owners_created"] += 1
        return oid

    def visit(self, cookie: str | None, ip: str, now: float, *, legit: bool,
              wants_owner: bool = False) -> tuple[str | None, str | None]:
        """一個 owner-scoped 請求進來。回傳 (owner_id, cookie)。

        `eager`（現況）：沒 cookie 就建 owner。deferred：沒 cookie 的
        讀取不建任何東西，直到第一次寫入（`wants_owner=True`，也就是
        建立劇本）才建。建 owner 本身也受 per-source 建立速率限制。"""
        if cookie is not None and cookie in self.cookie_to_owner:
            oid = self.cookie_to_owner[cookie]
            self.owners[oid].last_seen = now
            return oid, cookie
        if not (self.cfg.eager_owner_creation or wants_owner):
            return None, None
        skey = self.keyer.key(ip, now)
        if not self.create_limiter.allow(skey, now):
            self.stats["owner_create_blocked" + ("" if legit else "_attacker")] += 1
            return None, None
        if not self.global_create.allow("site", now):
            self.stats["owner_create_blocked_global" + ("" if legit else "_attacker")] += 1
            return None, None
        oid = self._new_owner(now, garbage=not legit)
        cookie = f"c-{oid}"
        self.cookie_to_owner[cookie] = oid
        return oid, cookie

    def seed_owner(self, symbols: tuple[str, ...], now: float) -> tuple[str, str]:
        """上線前就已經存在的使用者：直接放進去，不經過建立速率限制
        （那些限制只管新進來的建立請求）。"""
        oid = self._new_owner(now, garbage=False)
        cookie = f"c-{oid}"
        self.cookie_to_owner[cookie] = oid
        self.add_scenarios(oid, symbols, now)
        return oid, cookie

    def add_scenarios(self, oid: str, symbols: tuple[str, ...], now: float) -> None:
        rec = self.owners[oid]
        rec.symbols = tuple(dict.fromkeys(rec.symbols + symbols))[:10]
        rec.scenarios = len(rec.symbols)
        rec.last_activity = now

    # --- 一次上游抓鏈嘗試 ---
    def fetch(self, oid: str, ip: str, symbol: str, now: float, *, legit: bool) -> str:
        who = "legit" if legit else "attacker"
        self.stats[f"{who}_fetch_requests"] += 1
        rec = self.owners[oid]
        age = now - rec.created_at
        if not self.fuse.allow(now, age):
            self.stats[f"{who}_blocked_fuse"] += 1
            return "blocked_fuse"
        day_key = (oid, int(now // DAY))
        if (self.cfg.fair_share_after is not None and self.fuse.budget > 0
                and self.fuse.used >= self.cfg.fair_share_after * self.fuse.budget
                and self.owner_day_use[day_key] >= self.cfg.fair_share_owner_cap):
            self.stats[f"{who}_blocked_fairshare"] += 1
            return "blocked_fairshare"
        if not self.owner_limiter.allow(oid, now):
            self.stats[f"{who}_blocked_owner"] += 1
            return "blocked_owner"
        skey = self.keyer.key(ip, now)
        if not self.source_limiter.allow(skey, now):
            self.stats[f"{who}_blocked_source"] += 1
            return "blocked_source"
        self.peak_source_keys = max(self.peak_source_keys, len(self.source_limiter.state))
        self.owner_day_use[day_key] += 1
        if not self.cfg.dedupe.upstream_needed(symbol, now, self.rng):
            self.stats[f"{who}_shared"] += 1
            return "shared"
        self.fuse.charge(now, age)
        self.stats["vendor_calls"] += 1
        self.stats[f"{who}_vendor_calls"] += 1
        return "upstream"

    def full_refresh(self, oid: str, ip: str, now: float, *, legit: bool,
                     spacing: float = 1.2) -> list[str]:
        """一次完整刷新：每個 distinct symbol 一次，間隔 `spacing` 秒
        （group_limit=1 的 Continuation，一組一個 HTTP 往返）。"""
        out = []
        for i, sym in enumerate(self.owners[oid].symbols):
            out.append(self.fetch(oid, ip, sym, now + i * spacing, legit=legit))
        return out

    def maintenance(self, now: float) -> None:
        self.source_limiter.purge(now, self.cfg.source_idle_purge)
        self.create_limiter.purge(now, self.cfg.source_idle_purge)
        self.owner_limiter.purge(now, self.cfg.source_idle_purge)

    # --- metrics ---
    def summary(self) -> dict:
        s = self.stats
        legit_req = s["legit_fetch_requests"]
        legit_blocked = (s["legit_blocked_owner"] + s["legit_blocked_source"]
                         + s["legit_blocked_fuse"] + s["legit_blocked_fairshare"])
        return {
            "vendor_calls": s["vendor_calls"],
            "legit_vendor_calls": s["legit_vendor_calls"],
            "attacker_vendor_calls": s["attacker_vendor_calls"],
            "legit_requests": legit_req,
            "legit_blocked": legit_blocked,
            "legit_blocked_by": {k: s[f"legit_blocked_{k}"]
                                 for k in ("owner", "source", "fuse", "fairshare")},
            "false_positive_rate": (legit_blocked / legit_req) if legit_req else 0.0,
            "owners_created": s["owners_created"],
            "garbage_owners_created": s["garbage_owners_created"],
            "db_rows_owner_plus_identity": 2 * len(self.owners),
            "limiter_state_keys": (len(self.owner_limiter.state)
                                   + len(self.source_limiter.state)
                                   + len(self.create_limiter.state)),
            "peak_source_keys": self.peak_source_keys,
            "legit_owner_create_blocked": (s["owner_create_blocked"]
                                           + s["owner_create_blocked_global"]),
        }


# ---------- 假 IP ----------

def fake_ipv4(i: int) -> str:
    """198.18.0.0/15（benchmark 保留段）裡的第 i 個位址。"""
    return str(ipaddress.IPv4Address("198.18.0.0") + i)


def fake_ipv6(i: int, host: int = 1) -> str:
    """fd00::/8（ULA）裡第 i 個 /64 的第 host 個位址。"""
    return str(ipaddress.IPv6Address(f"fd00:{i // 65536:x}:{i % 65536:x}::") + host)
