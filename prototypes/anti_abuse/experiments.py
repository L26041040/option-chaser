"""ANTI-ABUSE-PROTOTYPE-001 Part B–F：跑全部實驗，把結果寫成
`RESULTS.md` 並印出。純模擬，決定性（固定 seed）。

    cd prototypes/anti_abuse && python3 experiments.py
"""
from __future__ import annotations

import math
import random
from statistics import mean

from sim import (DAY, HOUR, MINUTE, Config, NoDedupe, SingleFlight, System,
                 TTLReuse, Window, fake_ipv4, fake_ipv6)
from workloads import (HOT, SCAN_UNIVERSE, make_normal_users, normal_user_events,
                       peak_in_window, per_owner_fetch_times, run_events)

OUT: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    OUT.append(line)


def table(headers: list[str], rows: list[list]) -> None:
    emit("| " + " | ".join(headers) + " |")
    emit("|" + "|".join("---" for _ in headers) + "|")
    for r in rows:
        emit("| " + " | ".join(str(x) for x in r) + " |")
    emit()


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


# =====================================================================
# 1. 校正：正常使用者到底用多少
# =====================================================================

def calibrate() -> dict:
    emit("## 1. 正常使用者用量校正（limit 從這裡推，不是憑感覺）")
    emit()
    emit("Profile（模擬輸入，可調）：light 60%（1–4 劇本、每天開 2 次、幾乎不手動）"
         "／typical 30%（3–7 劇本、每天開 5 次、每次 0.8 次手動）／power 10%"
         "（7–10 劇本、每天開 12 次、每次 2 次手動、25% 機率連按）。70% 的開啟"
         "落在美股盤中。一次完整刷新＝每個 distinct symbol 一次上游。")
    emit()
    result = {}
    rows = []
    for label, mult in (("baseline", 1.0), ("stress（power 開啟次數 ×2）", 2.0)):
        users = make_normal_users(5000, seed=11, power_multiplier=mult)
        per = {}
        for u in users:
            ft = per_owner_fetch_times(u)
            per.setdefault(u.profile.name, []).append(
                (peak_in_window(ft, MINUTE), peak_in_window(ft, HOUR), len(ft)))
        every = [r for v in per.values() for r in v]
        result[label] = {
            "mean_day": mean(r[2] for r in every),
            "max_min": max(r[0] for r in every),
            "max_hour": max(r[1] for r in every),
            "max_day": max(r[2] for r in every),
            "p99_day": pct([r[2] for r in every], 0.99),
        }
        for name in ("light", "typical", "power"):
            v = per[name]
            rows.append([label, name, len(v),
                         f"{pct([r[0] for r in v], .99)} / {max(r[0] for r in v)}",
                         f"{pct([r[1] for r in v], .99)} / {max(r[1] for r in v)}",
                         f"{pct([r[2] for r in v], .5)} / {pct([r[2] for r in v], .99)} / {max(r[2] for r in v)}"])
    table(["情境", "profile", "人數", "每分鐘 p99 / max", "每小時 p99 / max",
           "每天 p50 / p99 / max"], rows)
    b = result["baseline"]
    emit(f"- baseline 平均每人每天 **{b['mean_day']:.1f}** 次上游抓鏈 → 現行 global fuse 2000 "
         f"只撐得住約 **{2000 / b['mean_day']:.0f} DAU**（光正常流量就會碰到 fuse）。")
    s = result["stress（power 開啟次數 ×2）"]
    emit(f"- stress 情境平均 {s['mean_day']:.1f} 次／人／天 → 約 {2000 / s['mean_day']:.0f} DAU。")
    emit()
    return result


# =====================================================================
# 共用：schemes
# =====================================================================

def owner_windows(minute=60, hour=300, day=800):
    return (Window(MINUTE, minute), Window(HOUR, hour), Window(DAY, day))


def source_windows(minute=120, hour=600, day=1200):
    return (Window(MINUTE, minute), Window(HOUR, hour), Window(DAY, day))


def schemes(fuse=2000):
    return {
        "S0 現況": Config("S0", fuse_budget=fuse),
        "S1 +owner": Config("S1", owner_windows=owner_windows(), fuse_budget=fuse),
        "S2 +owner+source": Config("S2", owner_windows=owner_windows(),
                                   source_windows=source_windows(), fuse_budget=fuse),
        "S3 +deferred+create cap+SF+tiered fuse": Config(
            "S3", owner_windows=owner_windows(), source_windows=source_windows(),
            owner_create_windows=(Window(HOUR, 10), Window(DAY, 30)),
            global_owner_create_per_day=300,
            eager_owner_creation=False, dedupe=SingleFlight(instances=1),
            fuse_budget=fuse, fuse_new_owner_share=0.4),
        "S4 = S3 + fair-share brake": Config(
            "S4", owner_windows=owner_windows(), source_windows=source_windows(),
            owner_create_windows=(Window(HOUR, 10), Window(DAY, 30)),
            global_owner_create_per_day=300,
            eager_owner_creation=False, dedupe=SingleFlight(instances=1),
            fuse_budget=fuse, fuse_new_owner_share=0.4,
            fair_share_after=0.6, fair_share_owner_cap=100),
    }


# =====================================================================
# 攻擊者行為
# =====================================================================

def attacker_same_owner(ip: str, period: float = 15.0, start: float = 0.0,
                        symbols=tuple(HOT)):
    """同一個 cookie 狂刷：10 個 symbol，每 `period` 秒一次完整刷新。"""
    state = {"oid": None, "cookie": None}

    def step(system, t):
        if state["oid"] is None:
            oid, c = system.visit(None, ip, t, legit=False, wants_owner=True)
            if oid is None:
                return
            state["oid"], state["cookie"] = oid, c
            system.add_scenarios(oid, symbols, t)
        system.visit(state["cookie"], ip, t, legit=False)
        system.full_refresh(state["oid"], ip, t, legit=False, spacing=0.1)

    return [(start + i * period, 10_000 + i, step) for i in range(int((DAY - start) / period))]


def attacker_cookie_reset(ip_fn, period: float = 15.0, symbols=tuple(HOT)):
    """被 owner bucket 擋到就丟 cookie、重新建 owner＋10 個劇本，繼續打。
    `ip_fn(i)`：第 i 步用哪個 IP（固定一個＝同 IP；每次換＝輪替）。"""
    state = {"oid": None, "cookie": None, "i": 0, "rotate": False}

    def step(system, t):
        state["i"] += 1
        ip = ip_fn(state["i"])
        if state["oid"] is None or state["rotate"]:
            oid, c = system.visit(None, ip, t, legit=False, wants_owner=True)
            if oid is None:
                return                     # 建 owner 被擋
            state["oid"], state["cookie"], state["rotate"] = oid, c, False
            system.add_scenarios(oid, symbols, t)
        system.visit(state["cookie"], ip, t, legit=False)
        out = system.full_refresh(state["oid"], ip, t, legit=False, spacing=0.1)
        if "blocked_owner" in out:
            state["rotate"] = True         # 丟 cookie

    return [(i * period, 20_000 + i, step) for i in range(int(DAY / period))]


def attacker_rotate_everything(pool: int, period: float = 2.0, symbols=tuple(HOT)):
    """每一步都換 IP、換 cookie（新 owner＋10 劇本）。"""
    counter = {"i": 0}

    def step(system, t):
        counter["i"] += 1
        ip = fake_ipv4(500_000 + counter["i"] % pool)
        oid, c = system.visit(None, ip, t, legit=False, wants_owner=True)
        if oid is None:
            return
        system.add_scenarios(oid, symbols, t)
        system.full_refresh(oid, ip, t, legit=False, spacing=0.05)

    return [(i * period, 30_000 + i, step) for i in range(int(DAY / period))]


def attacker_preaged(n_owners: int, n_ips: int, period: float = 15.0):
    """預先養號：第 1 天用 `n_ips` 個 IP 建好 `n_owners` 個 owner（各 10 個
    劇本），第 2 天（已滿 24h＝tiered fuse 眼中的「既有使用者」）全部一起
    狂刷。這是 tiered fuse 的誠實反例。"""
    owners: list[tuple[str, str, str]] = []
    evs = []
    for k in range(n_owners):
        ip = fake_ipv4(950_000 + k % n_ips)

        # 聰明的攻擊者：每個 owner 用不同的 10 檔，讓去重幫不上忙
        own = tuple(SCAN_UNIVERSE[k * 10:(k + 1) * 10])

        def mk(system, t, ip=ip, own=own):
            oid, c = system.visit(None, ip, t, legit=False, wants_owner=True)
            if oid is not None:
                system.add_scenarios(oid, own, t)
                owners.append((oid, c, ip))
        evs.append((100.0 + k * 400, 70_000 + k, mk))

    def step(system, t):
        for oid, c, ip in owners:
            system.visit(c, ip, t, legit=False)
            system.full_refresh(oid, ip, t, legit=False, spacing=0.1)
    evs += [(DAY + 13 * HOUR + i * period, 71_000 + i, step)
            for i in range(int(8 * HOUR / period))]
    return evs


def attacker_scan(ip_fn, per_owner: int = 10, period: float = 1.0):
    """地毯式掃描：每個 owner 建 10 個**不同** symbol，依序掃完整個
    universe。熱門股去重對它完全無效。"""
    state = {"i": 0, "oid": None, "left": 0}

    def step(system, t):
        i = state["i"]
        state["i"] += 1
        ip = ip_fn(i)
        if state["oid"] is None or state["left"] == 0:
            oid, _ = system.visit(None, ip, t, legit=False, wants_owner=True)
            if oid is None:
                return
            state["oid"], state["left"] = oid, per_owner
            base = (i // per_owner) * per_owner
            system.add_scenarios(oid, tuple(SCAN_UNIVERSE[(base + k) % len(SCAN_UNIVERSE)]
                                            for k in range(per_owner)), t)
        sym = system.owners[state["oid"]].symbols[per_owner - state["left"]]
        state["left"] -= 1
        system.fetch(state["oid"], ip, sym, t, legit=False)

    return [(i * period, 40_000 + i, step) for i in range(int(DAY / period))]


# =====================================================================
# 2. Part F：十個 attack scenario × 四個 scheme
# =====================================================================

BG_USERS = 22      # 背景正常流量：seed 22 下一天 995 次抓鏈 ≈ fuse 的 50%


def background(seed=22, n=BG_USERS):
    return make_normal_users(n, seed=seed)


def bg_events():
    """背景＝既有使用者（前一天就建好 owner），當天流量在第二天。"""
    return normal_user_events(background(), established=True)


def shift(events, dt=DAY):
    return [(t + dt, k, fn) for t, k, fn in events]


def run(cfg: Config, events: list, seed: int = 0) -> System:
    s = System(cfg, seed=seed)
    run_events(s, events)
    return s


def scenario_rows(name: str, build_events, fuse: int = 2000) -> list[list]:
    rows = []
    for label, cfg in schemes(fuse).items():
        s = run(cfg, build_events())
        m = s.summary()
        rows.append([name, label, m["vendor_calls"], m["attacker_vendor_calls"],
                     m["legit_blocked"], f"{m['false_positive_rate'] * 100:.2f}%",
                     "/".join(str(v) for v in m["legit_blocked_by"].values()),
                     m["legit_owner_create_blocked"],
                     m["garbage_owners_created"], m["db_rows_owner_plus_identity"],
                     m["limiter_state_keys"],
                     ("—" if s.fuse.budget <= 0 else
                      "是" if s.fuse.used >= s.fuse.budget else "否")])
    return rows


def part_f() -> None:
    emit("## 2. Part F：十個 attack scenario（攻擊日＝第 2 天；背景 "
         f"{BG_USERS} 個**既有**正常使用者，一天約 995 次抓鏈≈fuse 50%）")
    emit()
    emit("Scheme：S0＝現況；S1＝＋owner bucket（60/分、300/時、800/天）；S2＝S1＋"
         "source bucket（120/分、600/時、1200/天）；S3＝S2＋deferred owner creation"
         "＋每個 source 每小時最多建 10 個／每天 30 個 owner＋single-flight＋tiered fuse"
         "（新 owner 全體最多用當日 40%）＋全站每天最多建 300 個 owner；S4＝S3＋fair-share "
         "brake（fuse 用掉 60% 後，今天已用 ≥100 次的 owner 暫停）。")
    emit()
    headers = ["#", "scheme", "上游總數", "攻擊者上游", "正常被擋", "誤擋率", "被誰擋（owner/source/fuse/fair）",
               "正常建 owner 被擋", "垃圾 owner", "owner+identity 列", "limiter key", "fuse 觸發"]
    rows: list[list] = []

    rows += scenario_rows("1 正常", bg_events)
    rows += scenario_rows("2 同 owner 狂刷", lambda: bg_events()
                          + shift(attacker_same_owner(fake_ipv4(900_001))))
    rows += scenario_rows("3 刪 cookie 同 IP", lambda: bg_events()
                          + shift(attacker_cookie_reset(lambda i: fake_ipv4(900_002))))

    def ip_change():
        # 正常使用者整天在 wifi／行動網路間切換：每次刷新換一個 IP
        users = background()
        for u in users:
            u.ip = None
        evs = []
        for u in users:
            state = {"oid": None, "cookie": None, "k": 0}

            def create(system, t, u=u, state=state):
                state["oid"], state["cookie"] = system.seed_owner(u.symbols, t)
            evs.append((float(u.idx), -1, create))

            def refresh(system, t, u=u, state=state):
                state["k"] += 1
                ip = fake_ipv6(u.idx * 100 + state["k"]) if state["k"] % 2 else fake_ipv4(u.idx * 100 + state["k"])
                if state["oid"] is None:
                    oid, c = system.visit(None, ip, t, legit=True, wants_owner=True)
                    state["oid"], state["cookie"] = oid, c
                    system.add_scenarios(oid, u.symbols, t)
                oid, _ = system.visit(state["cookie"], ip, t, legit=True)
                assert oid == state["oid"]          # 換 IP 不換 owner
                system.full_refresh(state["oid"], ip, t, legit=True)
            for j, t in enumerate(u.refresh_times):
                evs.append((t + DAY, j, refresh))
        return evs
    rows += scenario_rows("4 換 IP、cookie 不變", ip_change)

    def nat():
        # NAT 後面的人也是既有使用者；為了不讓 fuse 本身把結果洗掉，這
        # 一格另外把 fuse 關掉（只看 owner／source bucket 的誤擋）
        nat_users = make_normal_users(200, seed=31, ip_fn=lambda i: "198.18.255.254")
        return bg_events() + normal_user_events(nat_users, established=True)
    rows += scenario_rows("5 200 人共用 NAT（fuse 關閉）", nat, fuse=0)

    def nat_new():
        nat_users = make_normal_users(200, seed=31, ip_fn=lambda i: "198.18.255.254")
        return bg_events() + shift(normal_user_events(nat_users))
    rows += scenario_rows("5b 200 個新使用者同一天從同一 NAT 進來（fuse 關閉）", nat_new, fuse=0)

    def hundred_aapl():
        evs = bg_events()
        for k in range(100):
            def step(system, t, k=k):
                oid, c = system.visit(None, fake_ipv4(700_000 + k), t, legit=True, wants_owner=True)
                if oid is None:
                    return
                system.add_scenarios(oid, ("AAPL",), t)
                system.fetch(oid, fake_ipv4(700_000 + k), "AAPL", t, legit=True)
            evs.append((MARKET_OPEN_T + random.Random(k).uniform(0, 2), 50_000 + k, step))
        return evs
    rows += scenario_rows("6 100 人同時 AAPL", hundred_aapl)

    def hot_four():
        evs = bg_events()
        for k in range(100):
            sym = ("AAPL", "NVDA", "MSFT", "TSLA")[k % 4]
            def step(system, t, k=k, sym=sym):
                oid, _ = system.visit(None, fake_ipv4(710_000 + k), t, legit=True, wants_owner=True)
                if oid is None:
                    return
                system.add_scenarios(oid, (sym,), t)
                system.fetch(oid, fake_ipv4(710_000 + k), sym, t, legit=True)
            evs.append((MARKET_OPEN_T + random.Random(k).uniform(0, 2), 51_000 + k, step))
        return evs
    rows += scenario_rows("7 熱門 4 檔集中", hot_four)

    rows += scenario_rows("8 地毯式掃 ticker（同 IP）",
                          lambda: bg_events()
                          + shift(attacker_scan(lambda i: fake_ipv4(900_003))))
    rows += scenario_rows("9 cookie+IP 全輪替（1000 IP 池）",
                          lambda: bg_events()
                          + shift(attacker_rotate_everything(pool=1000)))

    rows += scenario_rows("11a 預先養號 5 個 owner、1 個 IP",
                          lambda: bg_events() + attacker_preaged(5, 1))
    rows += scenario_rows("11b 預先養號 5 個 owner、5 個 IP",
                          lambda: bg_events() + attacker_preaged(5, 5))

    def garbage():
        evs = bg_events()
        for k in range(10_000):
            def step(system, t, k=k):
                system.visit(None, fake_ipv4(800_000 + k % 50), t, legit=False)
            evs.append((DAY + k * 5.0, 60_000 + k, step))
        return evs
    rows += scenario_rows("10 10,000 次無 cookie 建 owner（50 IP）", garbage)

    table(headers, rows)


MARKET_OPEN_T = DAY + 13.5 * HOUR + 60


# =====================================================================
# 3. Part C：cookie reset 攻擊細節
# =====================================================================

def part_c() -> None:
    emit("## 3. Part C：cookie reset 攻擊")
    emit()
    rows = []
    for label, cfg in schemes().items():
        s = run(cfg, attacker_cookie_reset(lambda i: fake_ipv4(900_002)))
        m = s.summary()
        per_owner = (m["attacker_vendor_calls"] / m["garbage_owners_created"]
                     if m["garbage_owners_created"] else 0)
        rows.append([label, m["garbage_owners_created"], m["attacker_vendor_calls"],
                     f"{per_owner:.0f}", m["db_rows_owner_plus_identity"],
                     s.stats["owner_create_blocked_attacker"]])
    table(["scheme（只有攻擊者，同一個 IP，每 15 秒一次完整刷新）", "建出的 owner",
           "上游呼叫", "每個 owner 平均燒掉", "owner+identity 列", "建 owner 被擋次數"], rows)

    emit("換 IP、cookie 不變（同一個攻擊者 cookie，每一步換 IP）：")
    emit()
    rows = []
    for label, cfg in list(schemes().items())[1:3]:
        s = System(cfg)
        oid, c = s.visit(None, fake_ipv4(1), 0, legit=False, wants_owner=True)
        s.add_scenarios(oid, tuple(HOT), 0)
        for i in range(int(DAY / 15)):
            t = i * 15.0
            ip = fake_ipv4(10_000 + i)
            same, _ = s.visit(c, ip, t, legit=False)
            assert same == oid
            s.full_refresh(oid, ip, t, legit=False, spacing=0.1)
        m = s.summary()
        rows.append([label, m["owners_created"], m["attacker_vendor_calls"],
                     s.stats["attacker_blocked_owner"]])
    table(["scheme", "owner 數（應為 1）", "上游呼叫（應 ≤ owner 每日上限 800）",
           "被 owner bucket 擋"], rows)

    emit("cookie＋IP 全輪替：只剩 global fuse。攻擊者在 fuse 觸發前最多燒多少、正常"
         "使用者被擋多少（IP 池大小 × fuse 形式）：")
    emit()
    rows = []
    for pool in (10, 100, 1000):
        for tiered in (None, 0.4):
            cfg = Config("rot", owner_windows=owner_windows(), source_windows=source_windows(),
                         owner_create_windows=(Window(HOUR, 10), Window(DAY, 30)),
                         global_owner_create_per_day=300,
                         eager_owner_creation=False, dedupe=SingleFlight(),
                         fuse_new_owner_share=tiered)
            # 背景正常使用者是「既有」owner：先讓他們在前一天建好
            s = run(cfg, bg_events() + shift(attacker_rotate_everything(pool=pool)))
            m = s.summary()
            rows.append([pool, "tiered 40%" if tiered else "flat", m["attacker_vendor_calls"],
                         m["legit_vendor_calls"], m["legit_blocked"],
                         f"{m['false_positive_rate'] * 100:.1f}%", m["garbage_owners_created"]])
    table(["IP 池", "fuse", "攻擊者上游", "正常上游", "正常被擋", "誤擋率", "垃圾 owner"], rows)


def part_c_fuse_size() -> None:
    emit("預先養號攻擊（5 個前一天建好的 owner、5 個 IP、每個 owner 用不同 10 檔）"
         "對 fuse 大小的敏感度——owner 每日上限固定 800：")
    emit()
    rows = []
    for fuse in (2000, 5000, 10000):
        for label, cfg in list(schemes(fuse).items())[3:]:
            s = run(cfg, bg_events() + attacker_preaged(5, 5))
            m = s.summary()
            rows.append([fuse, label, m["attacker_vendor_calls"], m["legit_blocked"],
                         f"{m['false_positive_rate'] * 100:.1f}%",
                         "是" if s.fuse.used >= s.fuse.budget else "否"])
    table(["fuse", "scheme", "攻擊者上游", "正常被擋", "誤擋率", "fuse 觸發"], rows)


# =====================================================================
# 4. Part B：source bucket 取捨（NAT vs cookie reset）
# =====================================================================

def part_b() -> None:
    emit("## 4. Part B：source bucket 門檻取捨")
    emit()
    emit("NAT 後面 N 個正常使用者（混合 profile）的誤擋率，對照同一個 IP 上 "
         "cookie-reset 攻擊者一天能燒掉的上游（上限＝source 每日額度）：")
    emit()
    rows = []
    for src_day in (400, 800, 1200, 2400):
        cells = [src_day, f"{src_day / 2000 * 100:.0f}%"]
        for n in (5, 20, 50, 200):
            fps = []
            for seed in (41, 42, 43):
                users = make_normal_users(n, seed=seed, ip_fn=lambda i: "198.18.255.254")
                cfg = Config("b", owner_windows=owner_windows(),
                             source_windows=source_windows(minute=max(120, src_day // 10),
                                                           hour=max(600, src_day // 2),
                                                           day=src_day),
                             fuse_budget=0)
                s = run(cfg, normal_user_events(users))
                fps.append(s.summary()["false_positive_rate"])
            cells.append(f"{mean(fps) * 100:.1f}%")
        rows.append(cells)
    table(["source 每日", "佔 fuse 2000", "NAT 5 人", "NAT 20 人", "NAT 50 人", "NAT 200 人"], rows)

    emit("raw IP vs HMAC key（同一份流量，只換 key 形式）：")
    emit()
    users = make_normal_users(500, seed=51)
    rows = []
    for mode in ("raw", "hmac"):
        cfg = Config("k", source_windows=source_windows(), fuse_budget=0, source_mode=mode)
        s = System(cfg)
        run_events(s, normal_user_events(users))
        sample = next(iter(s.source_limiter.state))
        s.maintenance(3 * DAY)
        rows.append([mode, s.peak_source_keys, sample,
                     len(s.source_limiter.state)])
    table(["mode", "峰值 key 數", "state 裡存的東西（範例）", "閒置 48h purge 後剩下"], rows)


# =====================================================================
# 5. Part D：熱門 ticker 去重
# =====================================================================

def burst_requests(symbols: list[str], window: float, seed: int = 0):
    rng = random.Random(seed)
    return sorted((rng.uniform(0, window), s) for s in symbols)


def dedupe_upstream(dedupe, reqs) -> int:
    rng = random.Random(99)
    return sum(1 for t, s in reqs if dedupe.upstream_needed(s, t, rng))


def part_d() -> None:
    emit("## 5. Part D：熱門 ticker 去重（上游呼叫次數）")
    emit()
    workloads = {
        "100× AAPL（2 秒內）": ["AAPL"] * 100,
        "25×AAPL/NVDA/MSFT/TSLA（2 秒內）": [s for s in ("AAPL", "NVDA", "MSFT", "TSLA") for _ in range(25)],
        "100 個不同 ticker（2 秒內）": SCAN_UNIVERSE[:100],
        "惡意掃 6000 檔（1 檔/秒）": SCAN_UNIVERSE,
    }
    modes = [lambda: NoDedupe(), lambda: SingleFlight(1.5, 1), lambda: SingleFlight(1.5, 10),
             lambda: TTLReuse(10), lambda: TTLReuse(30), lambda: TTLReuse(60)]
    names = [m().name for m in modes]
    rows = []
    for label, syms in workloads.items():
        if label.startswith("惡意"):
            reqs = [(i * 1.0, s) for i, s in enumerate(syms)]
        else:
            reqs = burst_requests(syms, 2.0)
        rows.append([label] + [dedupe_upstream(m(), reqs) for m in modes])

    # 真實一天：正常使用者的全部抓鏈，照時間排
    for n in (40, 500):
        users = make_normal_users(n, seed=61)
        reqs = sorted((t + j * 1.2, sym) for u in users for t in u.refresh_times
                      for j, sym in enumerate(u.symbols))
        rows.append([f"正常一天 {n} DAU（{len(reqs)} 次請求）"]
                    + [dedupe_upstream(m(), reqs) for m in modes])
    table(["workload"] + names, rows)
    emit("- single-flight 不存 payload；`inst=10` 代表請求隨機落在 10 個 instance、彼此"
         "看不到對方的 in-flight（serverless 的保守情況）。")
    emit("- TTL 需要跨 instance 共享的 chain payload store＝ADR-0001 否決過的 shared "
         "chain cache，也是跨使用者重用市場資料（licensing gate）。只模擬，不建議做。")
    emit()


# =====================================================================
# 6. Part E：owner 垃圾與 cleanup policy
# =====================================================================

def part_e() -> None:
    emit("## 6. Part E：owner 垃圾與 cleanup（模擬 150 天，每天 cron 一次）")
    emit()
    rng = random.Random(71)
    # 族群：(類型, 建立日, 有劇本?, 之後造訪的日子, 來源 IP 群組)
    pop = []
    for k in range(10_000):      # 無 cookie 垃圾請求：eager 下每個都是空 owner
        pop.append(("garbage-empty", k % 30, False, [], k % 50))
    for k in range(10_000):      # cookie reset：建了劇本，之後再也不出現
        pop.append(("reset-with-scenarios", k % 30, True, [], 1000 + (k // 30) % 20))
    for k in range(2_000):       # 正常使用者首次造訪 fan-out 多出來的那個 owner
        pop.append(("normal-fanout-dup", rng.randrange(60), False, [], 5000 + k))
    for k in range(1_000):       # 真正的使用者（有劇本）
        start = rng.randrange(20)
        kind = rng.choices(["daily-passive", "weekly", "vacation-45d", "return-after-60d",
                            "return-after-100d", "gone-forever"],
                           weights=[30, 25, 15, 10, 10, 10])[0]
        visits = {
            "daily-passive": list(range(start + 1, 150)),
            "weekly": list(range(start + 7, 150, 7)),
            "vacation-45d": list(range(start + 1, start + 10)) + list(range(start + 55, 150, 3)),
            "return-after-60d": [start + 60, start + 61],
            "return-after-100d": [start + 100, start + 101],
            "gone-forever": [],
        }[kind]
        pop.append((f"real-{kind}", start, True, visits, 10_000 + k))
    order = sorted(range(len(pop)), key=lambda i: (pop[i][1], i))   # ORDER BY created_at

    def simulate(policy: str, *, deferred: bool, batch: int, never_returned_days=None,
                 source_cap_day=0, global_cap_day=0, keep_days=187):
        exists: dict[int, dict] = {}
        created = blocked_real = 0
        lost_real = set()
        peak = 0
        for day in range(150):
            todays = [i for i in order if pop[i][1] == day]
            random.Random(day).shuffle(todays)               # 當天建立請求交錯到達
            per_source: dict[int, int] = {}
            global_n = 0
            for i in todays:
                kind, _, has_sc, _, src = pop[i]
                if deferred and not has_sc:
                    continue                                 # 沒寫入就不建 owner
                if source_cap_day and per_source.get(src, 0) >= source_cap_day:
                    blocked_real += kind.startswith("real")
                    continue
                if global_cap_day and global_n >= global_cap_day:
                    blocked_real += kind.startswith("real")
                    continue
                per_source[src] = per_source.get(src, 0) + 1
                global_n += 1
                exists[i] = {"created": day, "last_activity": day, "last_seen": day,
                             "has_sc": has_sc, "returned": False}
                created += 1
            for i, o in exists.items():
                if day in pop[i][3]:
                    o["last_seen"] = day
                    o["returned"] = o["returned"] or day > o["created"]
            candidates = [i for i in order if i in exists]
            checked = candidates if batch == 0 else candidates[:batch]
            victims = []
            for i in checked:
                o = exists[i]
                if policy == "A":
                    dead = day - o["last_activity"] >= 37
                else:
                    age = day - o["last_seen"]
                    if not o["has_sc"]:
                        dead = age >= 1
                    elif never_returned_days is not None and not o["returned"]:
                        dead = age >= never_returned_days
                    else:
                        dead = age >= keep_days
                if dead:
                    victims.append(i)
            for i in victims:
                if pop[i][0].startswith("real") and any(v > day for v in pop[i][3]):
                    lost_real.add(i)
                del exists[i]
            peak = max(peak, len(exists))
        left_garbage = sum(1 for i in exists if not pop[i][0].startswith("real"))
        return [created, peak, len(exists), left_garbage, len(lost_real), blocked_real]

    rows = []
    for label, kw in (
            ("A 現行（37 天無手動操作；每天只看最舊 200 個）",
             dict(policy="A", deferred=False, batch=200)),
            ("A 現行但批次不設限", dict(policy="A", deferred=False, batch=0)),
            ("B 空 owner 1 天；有劇本看 last_seen 187 天",
             dict(policy="B", deferred=False, batch=0)),
            ("C = B＋deferred＋每 source 30/天＋全站 300/天",
             dict(policy="B", deferred=True, batch=0, source_cap_day=30, global_cap_day=300)),
            ("D = C＋有劇本但從未回訪者 30 天",
             dict(policy="B", deferred=True, batch=0, source_cap_day=30, global_cap_day=300,
                  never_returned_days=30)),
            ("D' = C＋從未回訪者 90 天",
             dict(policy="B", deferred=True, batch=0, source_cap_day=30, global_cap_day=300,
                  never_returned_days=90)),
            ("D'' = C＋從未回訪者 120 天",
             dict(policy="B", deferred=True, batch=0, source_cap_day=30, global_cap_day=300,
                  never_returned_days=120))):
        rows.append([label] + simulate(**kw))
    table(["policy", "建出的 owner", "峰值 owner 數", "第 150 天 owner 數",
           "第 150 天殘留垃圾", "真實使用者被刪後又回來", "真實使用者建 owner 被擋"], rows)
    emit("族群：10,000 次無 cookie 垃圾請求（50 IP）、10,000 個 cookie-reset 身分（20 IP，"
         "每個都建了劇本、之後不再出現）、2,000 個首次造訪 fan-out 重複 owner、1,000 個真實"
         "使用者（30% 每天被動打開、25% 每週一次、15% 放假 45 天後回來、10% 60 天後回來、"
         "10% 100 天後回來、10% 再也不來）。真人的『手動操作』只發生在建立劇本那天，之後"
         "都只是打開看——現況下這不推 `last_activity_at`。")
    emit()


def main() -> None:
    emit("# ANTI-ABUSE-PROTOTYPE-001 模擬結果")
    emit()
    emit("由 `prototypes/anti_abuse/experiments.py` 產生；純模擬，固定 seed，可重跑。")
    emit()
    calibrate()
    part_f()
    part_c()
    part_c_fuse_size()
    part_b()
    part_d()
    part_e()
    with open("RESULTS.md", "w") as f:
        f.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
