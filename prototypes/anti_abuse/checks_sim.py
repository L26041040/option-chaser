"""ANTI-ABUSE-PROTOTYPE-001：把模擬結論鎖成可重跑的斷言。

    cd prototypes/anti_abuse && python3 -m pytest checks_sim.py -p no:cacheprovider
"""
import random

from experiments import (attacker_cookie_reset, bg_events, owner_windows, run,
                         schemes, shift, source_windows)
from sim import DAY, HOUR, Config, SingleFlight, SourceKeyer, System, Window, fake_ipv4
from workloads import HOT, make_normal_users, normal_user_events, run_events

S2 = schemes()["S2 +owner+source"]
S3 = schemes()["S3 +deferred+create cap+SF+tiered fuse"]


def test_cookie_reset_does_not_restore_vendor_budget_with_source_bucket():
    """S2：同一個 IP 刪 cookie 重建 owner 幾次都一樣，一天最多燒到
    source 每日額度（1200），不是 owner 數 × owner 額度。"""
    s = run(schemes()["S2 +owner+source"],
            attacker_cookie_reset(lambda i: fake_ipv4(900_002)))
    m = s.summary()
    assert m["garbage_owners_created"] > 50            # 確實刪了很多次 cookie
    assert m["attacker_vendor_calls"] <= 1200          # 但總量被 source bucket 釘住


def test_cookie_reset_is_bounded_by_create_cap_and_tiered_fuse():
    s = run(schemes()["S3 +deferred+create cap+SF+tiered fuse"],
            bg_events() + shift(attacker_cookie_reset(lambda i: fake_ipv4(900_002))))
    m = s.summary()
    assert m["garbage_owners_created"] <= 30           # 每個 source 每天最多建 30 個
    assert m["attacker_vendor_calls"] <= 0.4 * 2000    # 新 owner 全體最多 40%
    assert m["legit_blocked"] == 0                     # 既有使用者不受影響


def test_ip_change_keeps_owner_and_owner_quota():
    s = System(schemes()["S2 +owner+source"])
    oid, cookie = s.visit(None, fake_ipv4(1), 0, legit=False, wants_owner=True)
    s.add_scenarios(oid, tuple(HOT), 0)
    for i in range(int(DAY / 15)):
        same, _ = s.visit(cookie, fake_ipv4(10_000 + i), i * 15.0, legit=False)
        assert same == oid                             # 換 IP 不換 owner
        s.full_refresh(oid, fake_ipv4(10_000 + i), i * 15.0, legit=False, spacing=0.1)
    assert s.summary()["owners_created"] == 1
    assert s.summary()["attacker_vendor_calls"] <= 800  # owner 額度沒有因為換 IP 重置


def test_hmac_source_key_hides_ip_rotates_daily_and_purges():
    k = SourceKeyer("hmac")
    ip = "198.18.0.7"
    day1, day2 = k.key(ip, 10), k.key(ip, DAY + 10)
    assert ip not in day1 and day1 != day2             # 不含明文、每日輪替
    assert k.key("fd00:0:1::1", 0) == k.key("fd00:0:1::ffff", 0)   # IPv6 聚合到 /64
    s = System(Config("x", source_windows=source_windows(), fuse_budget=0))
    oid, c = s.visit(None, ip, 0, legit=True, wants_owner=True)
    s.add_scenarios(oid, ("AAPL",), 0)
    s.fetch(oid, ip, "AAPL", 0, legit=True)
    assert len(s.source_limiter.state) == 1
    s.maintenance(3 * DAY)
    assert s.source_limiter.state == {}                 # 閒置 48h 後整筆丟掉


def test_single_flight_collapses_simultaneous_hot_ticker():
    sf = SingleFlight(latency=1.5, instances=1)
    rng = random.Random(0)
    times = sorted(random.Random(1).uniform(0, 2) for _ in range(100))
    assert sum(sf.upstream_needed("AAPL", t, rng) for t in times) <= 2


def test_deferred_creation_makes_cookieless_garbage_free():
    s = System(schemes()["S3 +deferred+create cap+SF+tiered fuse"])
    for k in range(10_000):
        s.visit(None, fake_ipv4(k % 50), k * 1.0, legit=False)
    assert s.summary()["owners_created"] == 0


def test_owner_limits_never_block_baseline_normal_users():
    """5,000 個 baseline 使用者、各自一個 IP、fuse 關閉：owner bucket
    （60/分、300/時、800/天）零誤擋。limit 是從這份分布的最大值往上取的。"""
    users = make_normal_users(5000, seed=11)
    s = System(Config("o", owner_windows=owner_windows(), fuse_budget=0))
    run_events(s, normal_user_events(users))
    assert s.summary()["legit_blocked"] == 0
