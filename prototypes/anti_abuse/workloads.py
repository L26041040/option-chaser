"""模擬用的流量：正常使用者 profile＋十種 attack scenario。

正常使用者的 profile 是**模擬輸入**，不是量測值——參數全部寫在這裡、
可調，結果報告裡會一併列出，並做敏感度測試（power user 行為加倍）。
上線前應該用 production `operational_metrics.chain_fetch_count` 的真實
分布（唯讀）校正一次。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from sim import DAY, HOUR, MINUTE, System, fake_ipv4, fake_ipv6

# ---------- ticker universe ----------

HOT = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ", "AMZN", "META", "AMD", "GOOGL"]
UNIVERSE = HOT + [f"TK{i:04d}" for i in range(490)]          # 500 檔
SCAN_UNIVERSE = [f"SC{i:05d}" for i in range(6000)]           # 掃描用：美股選擇權標的量級


def zipf_weights(n: int, s: float = 1.1) -> list[float]:
    w = [1 / (k ** s) for k in range(1, n + 1)]
    total = sum(w)
    return [x / total for x in w]


_W = zipf_weights(len(UNIVERSE))


def pick_symbols(rng: random.Random, k: int) -> tuple[str, ...]:
    """k 個劇本的 symbol（熱門股集中，允許同 symbol 多個劇本）。"""
    return tuple(dict.fromkeys(rng.choices(UNIVERSE, weights=_W, k=k)))


def poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < l:
            return k
        k += 1


# ---------- 正常使用者 ----------

@dataclass(frozen=True)
class Profile:
    name: str
    share: float
    scenarios: tuple[int, int]
    opens_per_day: float
    manual_per_open: float
    burst_prob: float          # 某次打開時「不耐煩連按」的機率


PROFILES = (
    Profile("light", 0.60, (1, 4), 2.0, 0.2, 0.00),
    Profile("typical", 0.30, (3, 7), 5.0, 0.8, 0.05),
    Profile("power", 0.10, (7, 10), 12.0, 2.0, 0.25),
)

MARKET_OPEN = 13.5 * HOUR       # 09:30 ET ≈ 13:30 UTC
MARKET_CLOSE = 20 * HOUR


def _open_time(rng: random.Random, day: int) -> float:
    if rng.random() < 0.7:
        t = rng.uniform(MARKET_OPEN, MARKET_CLOSE)
    else:
        t = rng.uniform(0, DAY)
    return day * DAY + t


@dataclass
class Action:
    t: float
    kind: str        # "refresh"
    user: int


def normal_user_plan(rng: random.Random, profile: Profile, user: int,
                     day: int = 0, power_multiplier: float = 1.0) -> list[float]:
    """一個使用者一天內每次「完整刷新」的時間點（打開 app＝一次自動
    完整刷新，手動按＝再一次）。"""
    times: list[float] = []
    opens = poisson(rng, profile.opens_per_day
                    * (power_multiplier if profile.name == "power" else 1.0))
    for _ in range(opens):
        t = _open_time(rng, day)
        times.append(t)
        if rng.random() < profile.burst_prob:
            # 連按兩次：5–20 秒內
            for _ in range(2):
                t += rng.uniform(5, 20)
                times.append(t)
        for _ in range(poisson(rng, profile.manual_per_open)):
            t += rng.expovariate(1 / 90)
            times.append(t)
    return sorted(times)


def assign_profile(rng: random.Random) -> Profile:
    r, acc = rng.random(), 0.0
    for p in PROFILES:
        acc += p.share
        if r < acc:
            return p
    return PROFILES[-1]


@dataclass
class NormalUser:
    idx: int
    profile: Profile
    symbols: tuple[str, ...]
    ip: str
    refresh_times: list[float]


def make_normal_users(n: int, seed: int, *, ip_fn=None, day: int = 0,
                      power_multiplier: float = 1.0) -> list[NormalUser]:
    rng = random.Random(seed)
    users = []
    for i in range(n):
        p = assign_profile(rng)
        k = rng.randint(*p.scenarios)
        ip = ip_fn(i) if ip_fn else (fake_ipv6(i) if rng.random() < 0.4 else fake_ipv4(i))
        users.append(NormalUser(i, p, pick_symbols(rng, k), ip,
                                normal_user_plan(rng, p, i, day, power_multiplier)))
    return users


def per_owner_fetch_times(u: NormalUser, spacing: float = 1.2) -> list[float]:
    return [t + j * spacing for t in u.refresh_times for j in range(len(u.symbols))]


def peak_in_window(times: list[float], window: float) -> int:
    """固定視窗（跟 limiter 同一種對齊）裡的最大次數。"""
    counts: dict[int, int] = {}
    for t in times:
        b = int(t // window)
        counts[b] = counts.get(b, 0) + 1
    return max(counts.values(), default=0)


# ---------- 把一組事件按時間跑進 System ----------

def run_events(system: System, events: list[tuple[float, int, callable]]) -> None:
    """events: (t, 同時刻排序用序號, fn(system, t))。每小時做一次
    maintenance（limiter retention purge）。"""
    events.sort(key=lambda e: (e[0], e[1]))
    next_maint = HOUR
    for t, _, fn in events:
        while t >= next_maint:
            system.maintenance(next_maint)
            next_maint += HOUR
        fn(system, t)


def normal_user_events(users: list[NormalUser], established: bool = False) -> list:
    """正常使用者：第一次刷新前先「建立劇本」（有 cookie 之後一路沿用）。

    `established=True`：這批人是**既有**使用者——owner 在 t=0（前一天）
    就建好了，當天的刷新全部平移到第二天（t ≥ DAY）。攻擊情境都用這個
    模式，才是「站上已經有人在用，攻擊者這時候進來」的穩態。"""
    events = []
    for u in users:
        state = {"oid": None, "cookie": None}
        if established:
            def create(system, t, u=u, state=state):
                state["oid"], state["cookie"] = system.seed_owner(u.symbols, t)
            events.append((float(u.idx), -1, create))

        def refresh(system, t, u=u, state=state):
            if state["oid"] is None:
                oid, cookie = system.visit(None, u.ip, t, legit=True, wants_owner=True)
                if oid is None:
                    system.stats["legit_could_not_get_owner"] += 1
                    return
                state["oid"], state["cookie"] = oid, cookie
                system.add_scenarios(oid, u.symbols, t)
            system.visit(state["cookie"], u.ip, t, legit=True)
            system.full_refresh(state["oid"], u.ip, t, legit=True)

        for j, t in enumerate(u.refresh_times):
            events.append((t + (DAY if established else 0), j, refresh))
    return events
