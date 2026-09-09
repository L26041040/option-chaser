#!/usr/bin/env python3
"""PROTOTYPE — 丟棄式。OPTION-STORAGE-PROTOTYPE-004。

問題：把 `results.view::all_candidates` 拿掉、改存 visible-only narrow history，
並讓缺格從 raw snapshot 重算——**功能、正確性、效能、儲存**四項是否同時成立？

這個檔案是一次性驗證用的量測台，不是產品程式碼。它：
  * 只寫進一個名為 `octest_proto_WIPE_ME` 的 scratch 資料庫
  * 不 import 任何 prototype 專屬狀態進 production 模組
  * 完成後可連同 docs/prototypes/ 整個刪除，production 不受影響

唯一「日後會被抽回正式模組」的東西是最上面的 `cost_from_snapshot()`——
它是純函式、零 I/O、零 vendor、零 credential，本輪要驗證的正是它。

跑法（一行）：
    PYTHONPATH=. .venv/bin/python docs/prototypes/PROTOTYPE_storage_foundation.py
"""
import dataclasses, json, os, random, statistics, sys, time
from pathlib import Path

REPO = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import psycopg
from option_chaser import service, store
from option_chaser.models import AnalysisParams
from option_chaser.data.snapshot import (load_snapshot, snapshot_from_dict,
                                        snapshot_to_csv)
from _production_scale_fixtures import (PRODUCTION_SCALE_FIXTURE,
                                        real_dividend_loader)

DSN = "postgresql://postgres@127.0.0.1:55432/octest_proto_WIPE_ME"
FIX = os.path.join(REPO, PRODUCTION_SCALE_FIXTURE)
REFRESHES = int(os.environ.get("PROTO_REFRESHES", "100"))
SEED = 20260906
CHECKPOINTS = (1, 30, 100)


# ═══════════════════════════════════════════════════════════════════════
# 純函式模組（唯一會被抽回正式程式碼的部分）
# ═══════════════════════════════════════════════════════════════════════
_OPTION_TYPE = {
    "long-call": "call", "long-put": "put",
    "bull-call-spread": "call", "bear-put-spread": "put",
    "call-fly": "call", "put-fly": "put",
}


def cost_from_snapshot(snap_dict: dict, candidate_key: str) -> float | None:
    """從當次 raw snapshot 逐位元重算某個候選的歷史 net cost。

    零 vendor 呼叫、零 credential、不跑 ranking／valuation 引擎——只是把
    `option_chaser.scenarios.natural_cost` 的算術套在快照裡那幾張合約的
    bid／ask 上。運算式順序刻意與 `scenarios.py:138-143` **逐字相同**，
    因為浮點加減不可交換，順序一變就拿不到逐位元一致。

    `candidate_key` 由 `service.valuation_key()` 產生，已完整編碼
    strategy＋全部履約價＋到期日，因此不需要任何額外的中繼資料。

    找不到任一腿就回傳 None（該候選在那次快照裡不存在）。
    """
    parts = candidate_key.split("|")
    strategy, expiry = parts[0], parts[-1]
    strikes = [float(x) for x in parts[1:-1]]
    otype = _OPTION_TYPE.get(strategy)
    if otype is None:
        return None

    by_key = {}
    for c in snap_dict["contracts"]:
        by_key[(c["option_type"], c["strike"], c["expiry"])] = c

    def leg(k):
        return by_key.get((otype, k, expiry))

    legs = [leg(k) for k in strikes]
    if any(l is None for l in legs):
        return None
    if any(l["bid"] is None or l["ask"] is None for l in legs):
        return None

    if len(legs) == 1:                                    # long-call / long-put
        return legs[0]["ask"]
    if len(legs) == 2:                                    # vertical spread
        return legs[0]["ask"] - legs[1]["bid"]
    if len(legs) == 3:                                    # butterfly
        return legs[0]["ask"] - 2.0 * legs[1]["bid"] + legs[2]["ask"]
    return None


def visible_keys(view: dict) -> set[str]:
    """OD-07／FR-2.2 的 visible 集合：各到期日 top10 ∪ expiry_best
    ∪ 跨 family 冠軍 ∪ per-family 代表。"""
    out: set[str] = set()
    for r in view.get("results") or []:
        for g in (r.get("expiry_top10") or []):
            out.update(g.get("candidate_keys") or [])
        for g in (r.get("expiry_best") or []):
            k = g.get("candidate_key") if isinstance(g, dict) else None
            if k:
                out.add(k)
    return out


def per_expiry_order_from_engine(result) -> dict:
    """RL-33 的修復候選：不經 `all_candidates`，直接從引擎的
    `expiry_ranked` 取得 per-expiry 排序——這是真正的 canonical ranking
    source，`all_candidates` 只是它的序列化副本。"""
    out: dict[str, list[str]] = {}
    for r in result.results:
        for exp, ranked in (r.expiry_ranked or ()):
            out.setdefault(exp, []).extend(service.valuation_key(sv) for sv in ranked)
    return out


def per_expiry_order_from_all_candidates(view: dict) -> dict:
    """今天 `test_selection_regression.py:78-80` 的做法（對照組）。"""
    out: dict[str, list[str]] = {}
    for r in view["results"]:
        for e in (r.get("all_candidates") or []):
            out.setdefault(e["expiry"], []).append(e["candidate_key"])
    return out


# ═══════════════════════════════════════════════════════════════════════
# 以下全是量測台，丟棄
# ═══════════════════════════════════════════════════════════════════════
def perturb(base: dict, i: int, rng: random.Random) -> dict:
    """把 fixture 推成第 i 次刷新的市場狀態。合成的隨機漫步——目的只是
    讓 cost 隨時間變、讓排名churn（因此產生 narrow history 缺格），
    不宣稱是真實市場模型。"""
    d = json.loads(json.dumps(base))
    drift = 1.0 + rng.gauss(0, 0.012)
    d["spot"] = round(base["spot"] * (1.0 + 0.02 * rng.gauss(0, 1) + 0.0015 * i), 4)
    for c in d["contracts"]:
        j = drift * (1.0 + rng.gauss(0, 0.02))
        moneyness = (d["spot"] - c["strike"]) / max(d["spot"], 1e-9)
        k = 1.0 + (moneyness * 0.15 if c["option_type"] == "call" else -moneyness * 0.15)
        for f in ("bid", "ask", "last"):
            if c[f] is not None:
                c[f] = round(max(0.01, c[f] * j * k), 2)
        if c["bid"] is not None and c["ask"] is not None and c["bid"] >= c["ask"]:
            c["ask"] = round(c["bid"] + 0.01, 2)
    d["fetched_at"] = f"2026-09-06T{i // 60:02d}:{i % 60:02d}:00+00:00"
    return d


def stats(xs):
    xs = sorted(xs)
    p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]
    return statistics.median(xs), p95


def sizes(cur, table):
    cur.execute(f"""SELECT pg_total_relation_size('{table}'),
                           pg_relation_size('{table}'),
                           pg_indexes_size('{table}'),
                           COALESCE(pg_total_relation_size(
                             (SELECT reltoastrelid FROM pg_class
                              WHERE oid='{table}'::regclass)),0)""")
    return cur.fetchone()


def main():
    print(f"PROTOTYPE storage foundation — {REFRESHES} refreshes, seed={SEED}")
    print(f"fixture: {PRODUCTION_SCALE_FIXTURE}\n")
    base_snap = dataclasses.asdict(load_snapshot(FIX))
    rng = random.Random(SEED)

    p = AnalysisParams(target_price=110.0, target_month="2026-09", strategy="long-call")
    req = service.AnalysisRequest(
        symbol="XYZ", base_params=p,
        strategies=("long-call", "long-put", "bull-call-spread",
                    "bear-put-spread", "call-fly", "put-fly"))

    with psycopg.connect(DSN) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        for t in ("a_results", "a_snapshots", "b_results_latest", "b_snapshots", "b_narrow"):
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        cur.execute("""CREATE TABLE a_results (scenario_id TEXT, analyzed_at TEXT,
                       view JSONB NOT NULL, PRIMARY KEY (scenario_id, analyzed_at))""")
        cur.execute("""CREATE TABLE a_snapshots (scenario_id TEXT, analyzed_at TEXT,
                       snapshot JSONB NOT NULL, PRIMARY KEY (scenario_id, analyzed_at))""")
        cur.execute("""CREATE TABLE b_results_latest (scenario_id TEXT PRIMARY KEY,
                       analyzed_at TEXT NOT NULL, view JSONB NOT NULL)""")
        cur.execute("""CREATE TABLE b_snapshots (scenario_id TEXT, analyzed_at TEXT,
                       snapshot JSONB NOT NULL, PRIMARY KEY (scenario_id, analyzed_at))""")
        cur.execute("""CREATE TABLE b_narrow (scenario_id TEXT, analyzed_at TEXT,
                       candidate_key TEXT, cost DOUBLE PRECISION,
                       PRIMARY KEY (scenario_id, analyzed_at, candidate_key))""")

        T = {k: [] for k in ("serialize", "a_save_result", "a_snap_write",
                             "b_save_result", "b_snap_write", "b_narrow_write")}
        growth, parity_fail, backfill = [], [], {"checked": 0, "exact": 0, "mismatch": [],
                                                 "gaps_filled": 0}
        detail_mismatch = 0
        guard = {"engine_nonempty": 0, "matches_all_candidates": 0, "rounds": 0}
        a_cost_hist, vis_hist = {}, {}

        for i in range(REFRESHES):
            snap_d = perturb(base_snap, i, rng)
            at = snap_d["fetched_at"]
            snap_path = f"/tmp/proto_snap_{i}.json"
            Path(snap_path).write_text(json.dumps(snap_d))
            result = service.run_offline(req, snap_path, dividend_loader=real_dividend_loader)
            os.unlink(snap_path)

            t0 = time.perf_counter()
            view = store.serialize_result(result, "sc-proto", None)
            T["serialize"].append(time.perf_counter() - t0)

            view_b = json.loads(json.dumps(view))
            for r in view_b["results"]:
                r.pop("all_candidates", None)

            # --- Baseline A：完整 view + snapshot，逐次累積 ---
            t0 = time.perf_counter()
            cur.execute("INSERT INTO a_results VALUES (%s,%s,%s)",
                        ("sc-proto", at, json.dumps(view)))
            T["a_save_result"].append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            cur.execute("INSERT INTO a_snapshots VALUES (%s,%s,%s)",
                        ("sc-proto", at, json.dumps(snap_d)))
            T["a_snap_write"].append(time.perf_counter() - t0)

            # --- Prototype B：latest-only view + snapshot + narrow rows ---
            t0 = time.perf_counter()
            cur.execute("""INSERT INTO b_results_latest VALUES (%s,%s,%s)
                           ON CONFLICT (scenario_id) DO UPDATE
                           SET analyzed_at=EXCLUDED.analyzed_at, view=EXCLUDED.view""",
                        ("sc-proto", at, json.dumps(view_b)))
            T["b_save_result"].append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            cur.execute("INSERT INTO b_snapshots VALUES (%s,%s,%s)",
                        ("sc-proto", at, json.dumps(snap_d)))
            T["b_snap_write"].append(time.perf_counter() - t0)

            vis = visible_keys(view)
            entries = {e["candidate_key"]: e["cost"]
                       for r in view["results"] for e in (r.get("all_candidates") or [])}
            rows = [("sc-proto", at, k, entries[k]) for k in vis if k in entries]
            t0 = time.perf_counter()
            cur.executemany("INSERT INTO b_narrow VALUES (%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING", rows)
            T["b_narrow_write"].append(time.perf_counter() - t0)

            a_cost_hist[at] = entries
            vis_hist[at] = vis

            # --- Raw Data / CSV parity：兩邊 snapshot 必須完全相同 ---
            cur.execute("SELECT snapshot FROM a_snapshots WHERE analyzed_at=%s", (at,))
            sa = cur.fetchone()[0]
            cur.execute("SELECT snapshot FROM b_snapshots WHERE analyzed_at=%s", (at,))
            sb = cur.fetchone()[0]
            if sa != sb:
                parity_fail.append((at, "raw_snapshot"))
            elif snapshot_to_csv(snapshot_from_dict(sa)) != \
                    snapshot_to_csv(snapshot_from_dict(sb)):
                parity_fail.append((at, "csv_export"))

            # --- functional parity：current detail wire 必須逐位元相同 ---
            # 比 JSON 文字而不是 Python 物件：production 兩邊都會經 JSONB
            # 序列化，而 `view_b` 是 json round-trip 產生的（tuple→list），
            # 直接比物件會有假陽性。JSON 文字才是真正的 wire 等價。
            def wire(v):
                return json.dumps(store.project_for_detail(v),
                                  sort_keys=True, separators=(',', ':'))
            if wire(view) != wire(view_b):
                detail_mismatch += 1
            for fn, label in ((store.representative_candidate, "champion"),
                              (store.best_return, "best_return")):
                if fn(view) != fn(view_b):
                    parity_fail.append((at, label))

            # --- RL-33 regression-guard repair ---
            eng = per_expiry_order_from_engine(result)
            ac = per_expiry_order_from_all_candidates(view)
            guard["rounds"] += 1
            if eng and all(v for v in eng.values()):
                guard["engine_nonempty"] += 1
            if eng == ac:
                guard["matches_all_candidates"] += 1

            if (i + 1) in CHECKPOINTS:
                snapshot_row = {}
                for t in ("a_results", "a_snapshots", "b_results_latest",
                          "b_snapshots", "b_narrow"):
                    snapshot_row[t] = sizes(cur, t)
                cur.execute("SELECT count(*) FROM b_narrow")
                snapshot_row["narrow_rows"] = cur.fetchone()[0]
                growth.append((i + 1, snapshot_row))
                print(f"  [{i+1:3d}] checkpoint recorded")
            elif (i + 1) % 10 == 0:
                print(f"  [{i+1:3d}] ...")

        # ═══ Snapshot backfill proof ═══
        print("\n=== SNAPSHOT BACKFILL PROOF ===")
        cur.execute("SELECT analyzed_at, snapshot FROM b_snapshots ORDER BY analyzed_at")
        snaps = dict(cur.fetchall())
        cur.execute("SELECT analyzed_at, candidate_key, cost FROM b_narrow")
        narrow = {(a, k): c for a, k, c in cur.fetchall()}

        tracked = sorted(vis_hist[max(vis_hist)])            # 最新一次的 visible 集合
        by_strategy = {}
        for k in tracked:
            by_strategy.setdefault(k.split("|")[0], []).append(k)
        sample = [ks[0] for ks in by_strategy.values()]

        for at in sorted(a_cost_hist):
            for k in tracked:
                a_cost = a_cost_hist[at].get(k)
                if a_cost is None:
                    continue
                backfill["checked"] += 1
                b = cost_from_snapshot(snaps[at], k)
                if b is not None and b == a_cost:
                    backfill["exact"] += 1
                    if (at, k) not in narrow:
                        backfill["gaps_filled"] += 1
                else:
                    backfill["mismatch"].append((at, k, a_cost, b))

        # ═══ Read-path performance ═══
        print("=== READ PATH ===")
        R = {}

        def bench(label, fn, n=15):
            xs = []
            for _ in range(n):
                t0 = time.perf_counter(); fn(); xs.append(time.perf_counter() - t0)
            R[label] = stats(xs)

        latest_at = max(a_cost_hist)
        bench("A current detail read", lambda: (
            cur.execute("SELECT view FROM a_results WHERE scenario_id='sc-proto' "
                        "AND analyzed_at=%s", (latest_at,)), cur.fetchone()))
        bench("B current detail read", lambda: (
            cur.execute("SELECT view FROM b_results_latest WHERE scenario_id='sc-proto'"),
            cur.fetchone()))
        probe = tracked[0]
        bench("A /history (read all views)", lambda: (
            cur.execute("SELECT view FROM a_results WHERE scenario_id='sc-proto'"),
            cur.fetchall()), n=3)
        bench("B /history warm narrow", lambda: (
            cur.execute("SELECT analyzed_at, cost FROM b_narrow WHERE scenario_id='sc-proto' "
                        "AND candidate_key=%s ORDER BY analyzed_at", (probe,)), cur.fetchall()))

        def backfill_read():
            cur.execute("SELECT analyzed_at, snapshot FROM b_snapshots "
                        "WHERE scenario_id='sc-proto' ORDER BY analyzed_at")
            for a, s in cur.fetchall():
                cost_from_snapshot(s, probe)
        bench("B /history full backfill", backfill_read, n=3)
        bench("A /results query", lambda: (
            cur.execute("SELECT analyzed_at FROM a_results WHERE scenario_id='sc-proto' "
                        "ORDER BY analyzed_at"), cur.fetchall()))
        bench("B /results query", lambda: (
            cur.execute("SELECT DISTINCT analyzed_at FROM b_narrow "
                        "WHERE scenario_id='sc-proto' ORDER BY analyzed_at"), cur.fetchall()))

        out = {
            "refreshes": REFRESHES, "seed": SEED,
            "write_timing": {k: stats(v) for k, v in T.items()},
            "read_timing": R,
            "growth": growth,
            "backfill": {**backfill, "sampled_strategies": sorted(by_strategy)},
            "parity": {"detail_wire_mismatch": detail_mismatch,
                       "other_failures": parity_fail},
            "guard": guard,
            "visible_per_refresh": len(vis_hist[latest_at]),
            "all_candidates_per_refresh": len(a_cost_hist[latest_at]),
        }
        Path("/tmp/proto_result.json").write_text(json.dumps(out, indent=1, default=str))
        print("\nWROTE /tmp/proto_result.json")


if __name__ == "__main__":
    main()
