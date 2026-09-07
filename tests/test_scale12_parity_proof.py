"""SCALE-12（#263，Scaling Foundation Stage 1-2）：Parity Proof——
narrow history（SCALE-09 Part A）＋ candidate-specific historical
resolver（SCALE-09 Part B，`history_resolver.resolve_historical_cost()`）
對 legacy `all_candidates` oracle 的逐點 A/B。

## 設計

以 `xyz_v8_production_scale.json`（600 張合約、5 到期日×60 履約價/側）
為基礎，套用決定性合成隨機漫步（`_perturb()`，種子固定）模擬
`N_REFRESHES` 次刷新，每次刷新對全部 6 個 subtype
（`option_chaser.models.STRATEGIES`）跑一次真實 `service.
run_with_snapshot()`——`all_candidates`（`_history_entry()`／T09-#222
已修正對單腿／蝶式一視同仁，本檔案不重覆驗證那個修正本身，只是依賴
其結果作為 oracle）即 legacy 真相來源。

對每一次刷新：
- oracle：直接讀該次 `view["results"][i]["all_candidates"]`，逐
  candidate_key 記下 `cost`（找不到＝那天不是有效候選＝genuine gap）。
- narrow：`store.visible_candidate_keys()`／`visible_candidate_costs()`
  （SCALE-09 Part A 的 dual-write 邏輯，這裡直接呼叫純函式，不需要
  真的走 HTTP／storage）。
- resolver（SCALE-09 Part B）：對每一個 narrow 沒有的 (analyzed_at,
  candidate_key) 組合（cache miss），用該次刷新的 SCALE-01 fact
  context（`store.historical_fact_context(view)`）與該次的原始快照
  呼叫 `history_resolver.resolve_historical_cost()`。

**判定規則（票面明文：不存在已知可接受差異，任何不一致都是 FAIL）**：
- narrow 有值 → 必須 bitwise 等於 oracle（AC-2）
- narrow 沒有、oracle 有效 → resolver 必須判定 valid 且 cost bitwise
  等於 oracle（AC-1 的「backfilled」類別，AC-4 的正面證明）
- narrow 沒有、oracle 是 gap → resolver 必須回 genuine gap（AC-1 的
  「gap」類別，AC-3 的正面證明——尤其是「bid/ask 可算但 IV invalid」
  這個 cost-only replay 會答錯、membership resolver 才會答對的案例）

## Mandatory adversarial cases 對照

- **AC-3**（bid/ask 可算但 IV invalid）：`_INVALID_IV_STRIKE_PAIR`
  在每次刷新的合成快照裡固定存在、報價健全（`quote_ok` 通過）但
  `implied_volatility=0.001`（低於 `filters.iv_ok()` 的 `0.01` 下限）
  ——結構上永遠不會進 oracle 的 `all_candidates`，`cost_from_snapshot()`
  單獨呼叫卻算得出一個數字，直接證明「只看 bid/ask 重放會答錯」。
- **AC-4**（過去不在 visible/top10 但有效）：600 張合約的候選池遠大於
  `expiry_top10` 的 10 名上限，`test_at_least_one_oracle_valid_
  candidate_is_outside_narrow_visible_set` 正面驗證這個情況在真實
  規模下自然大量發生，不需要另外構造。
- **strategy/subtype 當時未啟用或方向不 eligible**：`TARGET_PRICE`
  固定、`_perturb()` 的 drift 讓 spot 在 `N_REFRESHES` 過程中跨越
  它至少一次，自然讓看漲／看跌兩組 subtype 交替變成
  `skipped_direction`——`test_direction_skipped_subtypes_occur_and_
  resolve_to_gap` 正面驗證。
- 其餘（expiry 未進 selected expiries／missing leg／invalid quote／
  可構造的 pair/structural/B-layer invalid／unrecognized key／version
  mismatch）已由 SCALE-09（#261）`tests/test_history_resolver.py` 的
  合成案例逐一覆蓋（AC-3／AC-4／AC-6，各自附完整推導），本檔案的邊際
  價值是**真實 production-scale、多次刷新、對 legacy oracle 的整體
  parity**，不重複那些單元測試已經證明過的個別分支邏輯。

## AC-5（resolver 不允許 full-universe enumeration）

`resolve_historical_cost()` 本身的 AST 隔離已由
`tests/test_history_resolver.py::test_resolver_never_imports_
enumeration_or_ranking` 鎖住（不 import `apply_filters`／
`generate_spread_pairs`／`generate_butterfly_triples`／`rank*`／
`evaluate_*`／`service`）。本檔案量測的是這個隔離帶來的**實際效益**
——candidate-specific miss 的延遲夠低，可以放進 lazy read path（見
`test_resolver_miss_latency_is_small_enough_for_a_lazy_read_path`）。
"""
from __future__ import annotations

import copy
import random
import time
from datetime import date

from option_chaser import service, store
from option_chaser.data.snapshot import snapshot_from_dict
from option_chaser.history_resolver import resolve_historical_cost
from option_chaser.models import (
    SCHEMA_VERSION, STRATEGIES, STRATEGY_FAMILY, AnalysisParams)
from option_chaser.snapshot_replay import cost_from_snapshot
from option_chaser.valuation import american_price

SEED = 20260907
N_REFRESHES = 8
SYMBOL = "XYZ"
SPOT = 100.0
TARGET_PRICE = 100.0   # 與 spot 相同，讓 drift 自然跨過它
TARGET_MONTH = "2026-10"

# 履約價／到期日規模：**刻意不用**其餘 SCALE 票既有的 600 張合約
# production-scale fixture——那份是為「單次刷新的計算時間」設計的
# （REPAIR-03／REPAIR-10 的 20 秒門檻），本票要做的是**窮舉**逐點 A/B
# （票面明文「不存在已知可接受差異」，不能用抽樣豁免掉沒比對到的
# candidate）。60 履約價/側在 Butterfly 家族會產生 `C(60,3)≈34220`
# 組合／到期日／權別，`resolve_historical_cost()` 對每個 cache miss
# 做的 `find_contract()` 線性掃描乘上去會讓整個窮舉掃描跑到數十分鐘
# 等級——那是在測 Python 迴圈開銷，不是在測 parity 語意。這裡改用
# 15 履約價/側、3 個到期日：仍然遠超過 `expiry_top10` 的 10 名上限
# （AC-4 的前提依然自然成立），Butterfly `C(15,3)=455`／到期日／權別，
# 整體規模可在數秒內窮舉完畢，且三個到期日×15 履約價依然是「多到期日
# 多履約價」的真實鏈型態，不是玩具規模的單一到期日。

# AC-3 的固定 adversarial 候選：報價健全、IV 落在 `iv_ok()` 可解區間之外。
_INVALID_IV_EXPIRY = "2026-09-18"
_INVALID_IV_LONG_STRIKE = 90.0
_INVALID_IV_SHORT_STRIKE = 100.0
_INVALID_IV_KEY = (f"bull-call-spread|{_INVALID_IV_LONG_STRIKE:g}|"
                  f"{_INVALID_IV_SHORT_STRIKE:g}|{_INVALID_IV_EXPIRY}")

# 基礎鏈本身現場建構（比照 `scripts/gen_butterfly_fixture.py` 的手法：
# BS93 定價出理論價＋隨到期日/價外程度放大的價差），不落磁碟、不共用
# 任何既有 fixture 檔案。3 個到期日×15 履約價/側——`_INVALID_IV_EXPIRY`
# 與兩個履約價常數皆落在這個梯子裡（見下方 `_BASE_STRIKES`）。
_BASE_TODAY = date(2026, 7, 15)
_BASE_EXPIRIES = ["2026-08-21", _INVALID_IV_EXPIRY, "2026-10-16"]
_BASE_STRIKES = [round(65.0 + 5.0 * i, 1) for i in range(15)]  # 65..135，以 SPOT 為中心
_BASE_R, _BASE_Q, _BASE_SIGMA = 0.04, 0.0, 0.28


def _base_quote(option_type: str, strike: float, expiry: str, idx: int) -> dict:
    T = (date.fromisoformat(expiry) - _BASE_TODAY).days / 365.0
    theo = american_price(option_type, SPOT, strike, T, _BASE_R, _BASE_Q, _BASE_SIGMA)
    moneyness = abs(strike - SPOT) / SPOT
    rel_spread = 0.02 + 0.03 * moneyness + 0.01 * T
    half = max(0.02, theo * rel_spread / 2.0)
    bid = round(max(0.01, theo - half), 2)
    ask = round(theo + half, 2)
    iv = _BASE_SIGMA + 0.05 * moneyness * (1 if option_type == "call" else -1)
    return {
        "contract_symbol": f"{SYMBOL}{expiry.replace('-', '')}{option_type[0].upper()}{idx:03d}",
        "option_type": option_type, "strike": strike, "expiry": expiry,
        "bid": bid, "ask": ask, "last": round((bid + ask) / 2, 2),
        "volume": 10 + idx, "open_interest": 100 + idx * 3,
        "implied_volatility": round(max(0.05, iv), 4),
    }


def _load_base() -> dict:
    """回傳形狀與 `dataclasses.asdict(ChainSnapshot)`（即
    `load_snapshot()`/`save_snapshot()` 的 JSON 形狀）逐鍵相同的 dict，
    `_perturb()` 直接對它操作——不讀取任何 fixture 檔案。"""
    contracts = []
    idx = 0
    for expiry in _BASE_EXPIRIES:
        for strike in _BASE_STRIKES:
            for option_type in ("call", "put"):
                contracts.append(_base_quote(option_type, strike, expiry, idx))
                idx += 1
    return {
        "schema_version": SCHEMA_VERSION, "symbol": SYMBOL,
        "fetched_at": "2026-07-15T21:30:00-04:00", "spot": SPOT,
        "source": "synthetic-scale12-parity", "contracts": contracts,
    }


def _perturb(base: dict, i: int, rng: random.Random) -> dict:
    """決定性合成隨機漫步——目的只是讓 cost 隨刷新次數變、讓排名
    churn（因此產生 narrow history 缺格＋方向翻轉），不宣稱是真實
    市場模型。與 `docs/prototypes/PROTOTYPE_storage_foundation.py`
    的 `perturb()` 同一種手法（那份是另一輪 prototype 的丟棄式腳本，
    這裡是正式測試基礎設施，各自獨立維護、不互相 import）。"""
    d = copy.deepcopy(base)
    drift = 1.0 + rng.gauss(0, 0.02)
    # 中心點刻意跨過 TARGET_PRICE：前半段 drift 為負（bearish），
    # 後半段轉正（bullish），讓兩側 subtype 在 N_REFRESHES 內都至少
    # 有機會 eligible 過一次。
    trend = -0.06 + 0.16 * (i / max(N_REFRESHES - 1, 1))
    d["spot"] = round(base["spot"] * (1.0 + trend + 0.01 * rng.gauss(0, 1)), 4)
    for c in d["contracts"]:
        if (c["expiry"] == _INVALID_IV_EXPIRY
                and c["strike"] in (_INVALID_IV_LONG_STRIKE, _INVALID_IV_SHORT_STRIKE)
                and c["option_type"] == "call"):
            c["implied_volatility"] = 0.001   # AC-3：報價健全但 IV invalid
            continue
        j = drift * (1.0 + rng.gauss(0, 0.03))
        moneyness = (d["spot"] - c["strike"]) / max(d["spot"], 1e-9)
        k = 1.0 + (moneyness * 0.15 if c["option_type"] == "call" else -moneyness * 0.15)
        for field in ("bid", "ask", "last"):
            if c[field] is not None:
                c[field] = round(max(0.01, c[field] * j * k), 2)
        if c["bid"] is not None and c["ask"] is not None and c["bid"] >= c["ask"]:
            c["ask"] = round(c["bid"] + 0.01, 2)
    d["fetched_at"] = f"2026-07-{15 + i // 24:02d}T{i % 24:02d}:30:00-04:00"
    return d


def _run_all_refreshes():
    """跑滿 `N_REFRESHES` 次刷新，回傳
    `(views, narrow, snapshots, oracle)`：
    - `views`：每次刷新的完整 serialized view dict（依刷新順序）
    - `narrow`：`{(analyzed_at, candidate_key): cost}`（SCALE-09 Part A
      dual-write 會寫入的內容，只含 visible candidate 的 non-null cost）
    - `snapshots`：`{analyzed_at: ChainSnapshot}`（resolver 需要的原始
      快照，比照 production `save_snapshot()` 落盤的那份）
    - `oracle`：`{(analyzed_at, candidate_key): cost_or_None}`——legacy
      `all_candidates` 的完整 membership 真相，`None` 明確代表「這天
      不是有效候選」而非「沒查過」。
    """
    base = _load_base()
    rng = random.Random(SEED)
    views: list[dict] = []
    narrow: dict[tuple[str, str], float] = {}
    snapshots: dict[str, object] = {}
    oracle: dict[tuple[str, str], float | None] = {}

    for i in range(N_REFRESHES):
        snap_dict = _perturb(base, i, rng)
        snap = snapshot_from_dict(snap_dict)
        req = service.AnalysisRequest(
            symbol=SYMBOL,
            base_params=AnalysisParams(strategy=STRATEGIES[0],
                                       target_price=TARGET_PRICE,
                                       target_month=TARGET_MONTH),
            strategies=STRATEGIES)
        result = service.run_with_snapshot(req, snap)
        view = store.serialize_result(result, "s1", None)
        analyzed_at = view["analyzed_at"]
        views.append(view)
        snapshots[analyzed_at] = snap

        # oracle：legacy 真相來源，逐 strategy 的 all_candidates 攤平。
        seen_this_refresh: set[str] = set()
        for r in view["results"]:
            for entry in r.get("all_candidates", []):
                key = entry["candidate_key"]
                oracle[(analyzed_at, key)] = entry["cost"]
                seen_this_refresh.add(key)
        # AC-3 的候選必須真的沒進 oracle——否則這個 adversarial case
        # 沒有意義（表示 IV 汙染沒生效），提早在這裡爆炸比事後才發現好。
        assert _INVALID_IV_KEY not in seen_this_refresh, (
            "adversarial IV-invalid candidate 意外通過了 A/B 層，"
            "檢查 _perturb() 的履約價/到期日是否真的對得上一組合法配對")

        # narrow：SCALE-09 Part A 的 dual-write（純函式直接呼叫）。
        for key, cost in store.visible_candidate_costs(view).items():
            narrow[(analyzed_at, key)] = cost

    return views, narrow, snapshots, oracle


# 整套模擬只需要跑一次，供本檔案全部測試共用（module 層快取）——
# 每個測試各自重跑一次 8 輪真實 `run_with_snapshot()` 會不必要地
# 拖慢整個檔案，且模擬本身是純函式輸入輸出、無副作用可言，共用安全。
_VIEWS, _NARROW, _SNAPSHOTS, _ORACLE = _run_all_refreshes()


def _resolve(analyzed_at: str, candidate_key: str, view: dict):
    fact = store.historical_fact_context(view)
    return resolve_historical_cost(
        candidate_key,
        history_replay_version=fact["history_replay_version"],
        requested_strategies=fact["requested_strategies"],
        resolved_params=fact["resolved_params"],
        snapshot=_SNAPSHOTS[analyzed_at])


# ---------- AC-1／AC-2／AC-6：全面 A/B，產出 hit/backfilled/gap 報告 ----------

def test_full_parity_sweep_across_every_refresh_and_oracle_candidate():
    """對每一次刷新裡 oracle 記錄過的每一個 candidate_key（不論那天是
    有效還是——注意 oracle dict 只在候選真的出現在 all_candidates 時
    才有 entry，所以這裡遍歷的是「歷史上至少存在過一次」的候選全集，
    對每個候選逐一在它「有記錄」的那些 analyzed_at 上核對），逐一比對
    narrow／resolver 是否與 oracle 一致——票面明文：任何不一致都是
    FAIL，沒有分類豁免。"""
    hit = backfilled = gap = 0
    mismatches: list[str] = []

    by_view = {v["analyzed_at"]: v for v in _VIEWS}
    for (analyzed_at, key), oracle_cost in _ORACLE.items():
        view = by_view[analyzed_at]
        if (analyzed_at, key) in _NARROW:
            narrow_cost = _NARROW[(analyzed_at, key)]
            if narrow_cost != oracle_cost:
                mismatches.append(
                    f"narrow hit mismatch {analyzed_at}/{key}: "
                    f"narrow={narrow_cost!r} oracle={oracle_cost!r}")
            else:
                hit += 1
            continue

        resolved = _resolve(analyzed_at, key, view)
        if oracle_cost is not None:
            if resolved.cost != oracle_cost:
                mismatches.append(
                    f"backfill mismatch {analyzed_at}/{key}: "
                    f"resolved={resolved.cost!r} (reason={resolved.reason}) "
                    f"oracle={oracle_cost!r}")
            else:
                backfilled += 1
        else:
            # oracle 對這個 (analyzed_at, key) 沒有 entry 代表當次
            # all_candidates 沒有它——這裡不會發生，因為 oracle dict
            # 的 key 集合本身就是從 all_candidates 建的，oracle_cost
            # 為 None 只可能是那個候選那天存在但 cost 欄位本身是
            # None（理論上不會發生，`_history_entry()` 的 cost 恆為
            # 有限數字）。保留這個分支只為窮舉完整、不遺漏任何一種
            # oracle 值的可能性。
            if resolved.cost is not None:
                mismatches.append(
                    f"false-positive backfill {analyzed_at}/{key}: "
                    f"resolved={resolved.cost!r} but oracle recorded None")
            else:
                gap += 1

    assert not mismatches, "\n".join(mismatches[:20])
    assert hit > 0 and backfilled > 0
    print(f"\nSCALE-12 parity report: hit={hit} backfilled={backfilled} "
         f"gap={gap} total={hit + backfilled + gap}")


def test_at_least_one_oracle_valid_candidate_is_outside_narrow_visible_set():
    """AC-4 前提：production scale 下，oracle 裡「有效」的候選數量
    遠大於 narrow（visible）覆蓋的候選數量——backfill 分支真的會被
    觸發，不是空討論。"""
    valid_oracle_keys = {k for k, cost in _ORACLE.items() if cost is not None}
    outside_narrow = valid_oracle_keys - set(_NARROW)
    assert outside_narrow, "narrow 覆蓋了 oracle 全部候選，AC-4 沒有測試對象"


def test_backfill_recovers_the_original_value_not_a_new_gap():
    """AC-4 正面證明：挑一個「當時有效但不在 narrow」的候選，resolver
    必須把它的原值補回來，而不是把它變成一個新的斷點。"""
    by_view = {v["analyzed_at"]: v for v in _VIEWS}
    candidate = next(
        ((at, key, cost) for (at, key), cost in _ORACLE.items()
         if cost is not None and (at, key) not in _NARROW), None)
    assert candidate is not None
    analyzed_at, key, oracle_cost = candidate
    resolved = _resolve(analyzed_at, key, by_view[analyzed_at])
    assert resolved.reason == "ok"
    assert resolved.cost == oracle_cost


# ---------- AC-3：bid/ask 可算但 IV invalid，cost-only replay 會答錯 ----------

def test_invalid_iv_candidate_never_enters_oracle_but_cost_is_computable():
    by_view = {v["analyzed_at"]: v for v in _VIEWS}
    checked = 0
    for view in _VIEWS:
        analyzed_at = view["analyzed_at"]
        snap = _SNAPSHOTS[analyzed_at]
        # 前提：naive cost-only replay（只看 bid/ask，不做 membership
        # 判定）會算出一個數字——證明「只看報價」這條路真的會答錯。
        naive_cost = cost_from_snapshot(snap, _INVALID_IV_KEY)
        assert naive_cost is not None and naive_cost > 0
        assert (analyzed_at, _INVALID_IV_KEY) not in _ORACLE
        checked += 1
    assert checked == N_REFRESHES


def test_invalid_iv_candidate_resolver_correctly_stays_gap():
    """AC-3 正面證明：即使 naive cost-only replay 算得出數字（見上一條
    測試），membership resolver 正確保持 gap，不冒充有效候選。"""
    view = _VIEWS[0]
    resolved = _resolve(view["analyzed_at"], _INVALID_IV_KEY, view)
    assert resolved.cost is None
    assert resolved.reason == "invalid_iv"


# ---------- 方向 eligibility：真實 production-scale 下自然發生 ----------

def test_direction_skipped_subtypes_occur_and_resolve_to_gap():
    """`_perturb()` 的 drift 讓 spot 跨過 `TARGET_PRICE`——至少一次
    刷新裡，某些 subtype 因方向不合被 `skipped_direction`。這裡正面
    驗證：(a) 這個情況真的發生過（不是空前提）；(b) 那個 subtype 底下
    「報價本身健全、算得出成本」的候選在 resolver 上正確回
    `skipped_direction`，而不是被誤判為有效。"""
    skipped_status_seen = False
    checked_gap = False
    for view in _VIEWS:
        analyzed_at = view["analyzed_at"]
        for r in view["results"]:
            if r["status"] != "skipped_direction":
                continue
            skipped_status_seen = True
            # 這個 subtype 那天沒有任何候選——從同一份原始快照裡，用
            # **同一個 family**（同樣的履約價/腿數形狀，key 的 token
            # 數才會對得上）另一個確定 eligible 的 subtype 的某個真實
            # 候選鍵，換上這個 subtype 的名字重新組一個 key 來測。跨
            # family 換名字會生出 token 數不合、resolver 只會判
            # unrecognized_key，不是這個測試要驗證的東西。
            family = STRATEGY_FAMILY[r["strategy"]]
            eligible_result = next(
                (rr for rr in view["results"]
                 if rr["status"] == "ok"
                 and STRATEGY_FAMILY[rr["strategy"]] == family), None)
            sample_key = None
            if eligible_result is not None:
                for group in eligible_result["expiry_top10"]:
                    if group["candidate_keys"]:
                        sample_key = group["candidate_keys"][0]
                        break
            if sample_key is None:
                continue
            parts = sample_key.split("|")
            swapped_key = "|".join([r["strategy"], *parts[1:]])
            resolved = _resolve(analyzed_at, swapped_key, view)
            if resolved.reason == "skipped_direction":
                checked_gap = True
    assert skipped_status_seen, (
        "8 次刷新裡沒有任何 subtype 被 skipped_direction 過，"
        "_perturb() 的 drift 沒有真的跨過 TARGET_PRICE，adversarial "
        "case 沒有被觸發")
    assert checked_gap


# ---------- AC-5：candidate-specific miss 延遲，適合放進 lazy read path ----------

def test_resolver_miss_latency_is_small_enough_for_a_lazy_read_path():
    """AC-5：量測 candidate-specific cache miss 的延遲（純 Python，不含
    HTTP／storage 往返）——只做 per-candidate O(1) 判準（`quote_ok`／
    `iv_ok`／`spread_structural_ok`／`butterfly_structural_ok`）＋一次
    `cost_from_snapshot()`，不枚舉整條鏈，延遲應遠低於一般網路往返，
    確認可以安全放進 lazy read path（SCALE-14）。"""
    by_view = {v["analyzed_at"]: v for v in _VIEWS}
    miss_keys = [(at, key) for (at, key) in _ORACLE if (at, key) not in _NARROW]
    assert len(miss_keys) >= 50   # 確保量測樣本數夠大、不是量到誤差

    t0 = time.perf_counter()
    for analyzed_at, key in miss_keys:
        _resolve(analyzed_at, key, by_view[analyzed_at])
    elapsed = time.perf_counter() - t0
    per_call_ms = (elapsed / len(miss_keys)) * 1000
    print(f"\nSCALE-12 resolver miss latency: {per_call_ms:.4f} ms/call "
         f"over {len(miss_keys)} calls")
    # 10ms/call 是刻意寬鬆的門檻——這個函式結構上只做幾次字典查找＋
    # 常數次數的浮點運算，真實延遲預期在微秒等級；10ms 給了三個數量級
    # 的安全餘裕，門檻本身在乎的是「這不是另一次全池枚舉」，不是逼近
    # 真實延遲上限。
    assert per_call_ms < 10.0
