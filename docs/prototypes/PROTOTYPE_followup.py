#!/usr/bin/env python3
"""PROTOTYPE follow-up — 丟棄式。三件事：
  1. VACUUM FULL 後重量尺寸（排除 MVCC 膨脹，取真實 steady state）
  2. `/results` 回歸的根因與修法量測
  3. backfill 逐位元 parity 擴大到全部六個 subtype
"""
import json, os, statistics, sys, time, random
from pathlib import Path
REPO = str(Path(__file__).resolve().parents[2]); sys.path.insert(0, REPO)
import psycopg
sys.path.insert(0, os.path.join(REPO, "docs/prototypes"))
from PROTOTYPE_storage_foundation import cost_from_snapshot

DSN = "postgresql://postgres@127.0.0.1:55432/octest_proto_WIPE_ME"

def stats(xs):
    xs=sorted(xs); return statistics.median(xs), xs[min(len(xs)-1,int(round(.95*(len(xs)-1))))]
def bench(fn,n=15):
    xs=[]
    for _ in range(n):
        t=time.perf_counter(); fn(); xs.append(time.perf_counter()-t)
    return stats(xs)
def sz(cur,t):
    cur.execute(f"""SELECT pg_total_relation_size('{t}'),pg_relation_size('{t}'),
      pg_indexes_size('{t}'),COALESCE(pg_total_relation_size((SELECT reltoastrelid
      FROM pg_class WHERE oid='{t}'::regclass)),0)""")
    return cur.fetchone()

with psycopg.connect(DSN) as conn:
    conn.autocommit=True; cur=conn.cursor()
    TABLES=("a_results","a_snapshots","b_results_latest","b_snapshots","b_narrow")
    print("=== 1. VACUUM FULL 前後（排除 MVCC 膨脹）===")
    before={t:sz(cur,t) for t in TABLES}
    for t in TABLES: cur.execute(f"VACUUM FULL ANALYZE {t}")
    after={t:sz(cur,t) for t in TABLES}
    for t in TABLES:
        print(f"  {t:18s} before total={before[t][0]:12,}  after total={after[t][0]:12,}"
              f"  heap={after[t][1]:10,} idx={after[t][2]:9,} toast={after[t][3]:12,}")
    A=after['a_results'][0]+after['a_snapshots'][0]
    Bfixed=after['b_results_latest'][0]
    Bgrow=after['b_snapshots'][0]+after['b_narrow'][0]
    N=100
    print(f"\n  A 總量           {A:,} B      → 每次刷新 {A/N:,.0f} B")
    print(f"  B 成長部分       {Bgrow:,} B      → 每次刷新 {Bgrow/N:,.0f} B")
    print(f"  B current 固定   {Bfixed:,} B  (latest view，常數項非成長項)")
    print(f"  >> 總量比        {A/(Bgrow+Bfixed):.2f}x")
    print(f"  >> 邊際成長比    {(A/N)/(Bgrow/N):.2f}x   ← 決定何時撞牆的是這個")

    print("\n=== 2. /results 回歸：根因與修法 ===")
    r={}
    r['A: results 表 PK 索引']=bench(lambda:(cur.execute(
        "SELECT analyzed_at FROM a_results WHERE scenario_id='sc-proto' ORDER BY analyzed_at"),cur.fetchall()))
    r['B-壞: DISTINCT over narrow']=bench(lambda:(cur.execute(
        "SELECT DISTINCT analyzed_at FROM b_narrow WHERE scenario_id='sc-proto' ORDER BY analyzed_at"),cur.fetchall()))
    r['B-修: snapshots 表 PK 索引']=bench(lambda:(cur.execute(
        "SELECT analyzed_at FROM b_snapshots WHERE scenario_id='sc-proto' ORDER BY analyzed_at"),cur.fetchall()))
    for k,(m,p) in r.items(): print(f"  {k:30s} {m*1000:8.3f} / {p*1000:8.3f} ms")
    print(f"  >> 修法後 vs A: {r['A: results 表 PK 索引'][0]/r['B-修: snapshots 表 PK 索引'][0]:.2f}x")

    print("\n=== 3. 真實混合 /history（warm narrow + 只回填缺格）===")
    cur.execute("SELECT DISTINCT candidate_key FROM b_narrow LIMIT 1"); probe=cur.fetchone()[0]
    cur.execute("SELECT analyzed_at FROM b_snapshots WHERE scenario_id='sc-proto' ORDER BY analyzed_at")
    all_at=[a for (a,) in cur.fetchall()]
    cur.execute("SELECT analyzed_at FROM b_narrow WHERE candidate_key=%s",(probe,))
    have={a for (a,) in cur.fetchall()}
    gaps=[a for a in all_at if a not in have]
    print(f"  probe={probe}  總點數={len(all_at)}  narrow 命中={len(have)}  缺格={len(gaps)}")
    def mixed():
        cur.execute("SELECT analyzed_at,cost FROM b_narrow WHERE scenario_id='sc-proto' "
                    "AND candidate_key=%s",(probe,)); cur.fetchall()
        if gaps:
            cur.execute("SELECT analyzed_at,snapshot FROM b_snapshots WHERE analyzed_at = ANY(%s)",(gaps,))
            for a,s in cur.fetchall(): cost_from_snapshot(s,probe)
    m,p=bench(mixed,n=10); print(f"  混合讀取 {m*1000:.2f} / {p*1000:.2f} ms")

    print("\n=== 4. backfill 全 subtype 逐位元 parity ===")
    cur.execute("SELECT analyzed_at,view FROM a_results ORDER BY analyzed_at")
    rows=cur.fetchall()
    cur.execute("SELECT analyzed_at,snapshot FROM b_snapshots"); snaps=dict(cur.fetchall())
    rng=random.Random(7); per_sub={}; checked=exact=0; bad=[]
    for at,view in rows[::10]:                      # 每 10 次刷新取一份，共 10 份
        buckets={}
        for rr in view["results"]:
            for e in (rr.get("all_candidates") or []):
                buckets.setdefault(e["candidate_key"].split("|")[0],[]).append(e)
        for sub,es in buckets.items():
            for e in rng.sample(es,min(60,len(es))):
                checked+=1
                b=cost_from_snapshot(snaps[at],e["candidate_key"])
                if b is not None and b==e["cost"]:
                    exact+=1; per_sub[sub]=per_sub.get(sub,0)+1
                else: bad.append((at,e["candidate_key"],e["cost"],b))
    print(f"  checked={checked:,}  bitwise exact={exact:,}  mismatch={len(bad)}")
    for s,n in sorted(per_sub.items()): print(f"    {s:20s} {n:6,} 筆逐位元一致")
    if bad: print("  FIRST MISMATCH:",bad[:3])
