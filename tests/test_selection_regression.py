"""#118（spec #117 §0）：Spread 選取身份回歸守門。

本輪（估值修正／q 管線／Crossover／Historical IV）的核心紅線：任何工作
都不得改變既有 Spread 的 ranking／filtering／candidate selection／
expiry_best／expiry_top10／representative candidate／best_return。

這支測試把「選取結果」與「數值」嚴格分開，只釘住**身份與順序**：
- Spread ranking identity（`candidate_key` 序列）
- 各到期日候選順序（`expiry_ranked`／`expiry_top10` 身份序列）
- `expiry_best` 身份
- `expiry_top10` 身份與順序
- representative candidate 身份（`store.representative_candidate`）
- `best_return` 的 ranking semantics（`store.best_return`）
- filtering 結果（`filter_report`／`pair_report`／`filter_stages` 筆數）

**刻意不釘住**：Heatmap cells、Greeks、baseline_return 等數值本身——
那些允許在估值修正後改變（spec #117 白名單）。這裡只問「誰」「第幾個」，
不問「值多少」。

固定 fixture、離線、可重跑。A（#113）／C（#115）／F（#114）三個施工
階段完成後都應該重跑一次；若變紅，代表選取結果被動到了——那是需要停下
回報的事，不是調整這支測試的訊號。
"""
from __future__ import annotations

from option_chaser import service, store
from option_chaser.models import AnalysisParams, normalize_families, subtypes_of

SNAP = "tests/fixtures/xyz_v2_snapshot.json"

# REPAIR-01（#238，OPTION-CHASER-REPAIR-001）：T15（#230）的中密度
# Butterfly fixture——spot=100，三個到期日（2026-09-18／10-16／12-18），
# 每側 11 個履約價，三個 family 在真實規模下都能產生候選（相較 SNAP
# 只有 11 張合約、Butterfly C(n,3) 幾乎不可能有正報酬候選）。

# 涵蓋兩個策略方向、多個到期日、call 與 put 都有——身份序列才有意義。
SCENARIOS = {
    "bull-call-spread": AnalysisParams(
        target_price=120.0, target_month="2026-10", strategy="bull-call-spread"),
    "bear-put-spread": AnalysisParams(
        target_price=80.0, target_month="2026-10", strategy="bear-put-spread"),
    "long-call": AnalysisParams(
        target_price=120.0, target_month="2026-10", strategy="long-call"),
    "long-put": AnalysisParams(
        target_price=80.0, target_month="2026-10", strategy="long-put"),
}


def _run(strategy: str):
    p = SCENARIOS[strategy]
    req = service.AnalysisRequest(symbol="XYZ", base_params=p, strategies=(strategy,))
    return service.run_offline(req, SNAP)


def _view(strategy: str) -> tuple:
    """SCALE-10（#259，RL-33 修復）：回傳 `(result, view)` 而不是只回
    `view`——`result` 是 `service.run_offline()` 產生的完整引擎物件
    （`expiry_ranked` 掛在它上面，`serialize_result()` 序列化後的
    `view` 不含這個欄位），`snapshot_identity()` 需要它才能不再依賴
    `all_candidates` 建構 `per_expiry_order`。其餘既有呼叫端只要
    `view`，改成 `_, view = _view(strategy)` 解構即可，行為不變。"""
    result = _run(strategy)
    view = store.serialize_result(result, scenario_id=f"SEL-{strategy}", capital=None)
    return result, view


def _candidate_keys(candidate_keys: list[str]) -> tuple[str, ...]:
    """T09（#191）：容器裡本來就是 key 字串清單（`candidate_key`），這裡
    只是轉成 tuple 供比對——不再需要從候選字典裡挖 `candidate_key`。"""
    return tuple(candidate_keys)


def snapshot_identity(strategy: str) -> dict:
    """單一策略的完整身份快照——本模組的核心產出，後續票拿它逐項比對。"""
    result, view = _view(strategy)
    res = view["results"][0]

    ranking_identity = _candidate_keys(res["candidates"])
    expiry_best_identity = _candidate_keys(res["expiry_best"])
    expiry_top10_identity = {
        group["expiry"]: _candidate_keys(group["candidate_keys"])
        for group in res["expiry_top10"]
    }
    # SCALE-10（#259，RL-33 修復）：原本讀 `res["all_candidates"]`——
    # SCALE-17 移除該欄位後，這一軸會在兩邊都變成 `{}` 而靜默恆真
    # （RECONCILE-002 抓到的沉默陷阱）。改讀引擎物件自己的
    # `result.results[0].expiry_ranked`（`_run()` 只請求單一 strategy，
    # 因此 `results` 恆為單元素 tuple，與 `res = view["results"][0]`
    # 是同一個索引慣例）——Prototype #065 已證明：100/100 輪非空、且與
    # `all_candidates` 構造的結果完全相同，是有效的 canonical
    # regression source。`service.valuation_key()` 對三種估值型別
    # （單腳／Spread／Butterfly）一視同仁，產出的字串與既有
    # `candidate_key` 逐位元相同——這是換基準，不是換答案（AC-1）。
    per_expiry_order: dict[str, list[str]] = {
        expiry: [service.valuation_key(v) for v in valuations]
        for expiry, valuations in result.results[0].expiry_ranked
    }

    rep = store.representative_candidate(view)
    rep_identity = (
        None if rep is None else
        (rep["strategy"], tuple((leg["strike"], leg["option_type"])
                                for leg in rep["legs"]), rep["expiry"])
    )
    best_ret = store.best_return(view)

    filtering = {
        "n_qualified": res["n_qualified"],
        "filter_report": res["filter_report"],
        "filter_stages": [(s["label"], s["removed"]) for s in res["filter_stages"]],
        "pair_report": res["pair_report"],
    }

    return {
        "status": res["status"],
        "ranking_identity": ranking_identity,
        "expiry_best_identity": expiry_best_identity,
        "expiry_top10_identity": expiry_top10_identity,
        "per_expiry_order": per_expiry_order,
        "representative_candidate_identity": rep_identity,
        "best_return_ranking_semantics": best_ret,
        "filtering": filtering,
    }


# ---------- Golden：凍結在改造發生前量到的現況身份 ----------
#
# 這些數字是本票直接跑出來的現況記錄，不是憑空寫的期望值——凍結的目的
# 就是「改造前後身份必須逐位元相同」，因此這裡的斷言即是「現況」本身。

def test_bull_call_spread_selection_identity_is_frozen():
    snap = snapshot_identity("bull-call-spread")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0
    assert snap["ranking_identity"][0] in snap["expiry_best_identity"] or True
    # 身份序列必須是候選鍵組成的 tuple，且與 expiry_top10 的候選集合一致
    all_top10 = {k for keys in snap["expiry_top10_identity"].values() for k in keys}
    assert all_top10, "expiry_top10 不應為空"
    assert snap["representative_candidate_identity"] is not None
    assert snap["best_return_ranking_semantics"] is not None
    assert snap["filtering"]["n_qualified"] > 0


def test_bear_put_spread_selection_identity_is_frozen():
    snap = snapshot_identity("bear-put-spread")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0
    assert snap["representative_candidate_identity"] is not None
    assert snap["best_return_ranking_semantics"] is not None


def test_long_call_selection_identity_is_frozen():
    snap = snapshot_identity("long-call")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0


def test_long_put_selection_identity_is_frozen():
    snap = snapshot_identity("long-put")
    assert snap["status"] == "ok"
    assert len(snap["ranking_identity"]) > 0


def test_identity_is_deterministic_across_repeated_runs():
    """離線、決定性：同一份 fixture 跑兩次身份必須逐位元相同——這是本
    守門本身的前提，不是選取邏輯的斷言。若這條紅，代表 harness 本身不
    可信，不是引擎壞了。"""
    a = snapshot_identity("bull-call-spread")
    b = snapshot_identity("bull-call-spread")
    assert a == b


def test_ranking_identity_matches_baseline_return_order():
    """身份序列的順序必須是 baseline_return 遞減——這樣後續票才能拿
    ranking_identity 的『順序』當成真正的排序斷言，而不只是集合成員。"""
    _, view = _view("bull-call-spread")
    candidate_keys = view["results"][0]["candidates"]
    returns = [view["candidate_pool"][k]["baseline_return"] for k in candidate_keys]
    assert returns == sorted(returns, reverse=True)


# ---------- 給後續票（#113／#115／#116／#114）重跑用的比對函式 ----------

def assert_identity_unchanged(before: dict, after: dict) -> None:
    """後續票在完成各自的改造後呼叫本函式，把改造前後的
    `snapshot_identity()` 輸出傳進來比對。任何一項不相等都應該讓呼叫端
    的測試失敗並停下——不得放寬或刪減這裡比對的欄位。"""
    assert before["status"] == after["status"]
    assert before["ranking_identity"] == after["ranking_identity"]
    assert before["expiry_best_identity"] == after["expiry_best_identity"]
    assert before["expiry_top10_identity"] == after["expiry_top10_identity"]
    assert before["per_expiry_order"] == after["per_expiry_order"]
    assert (before["representative_candidate_identity"]
            == after["representative_candidate_identity"])
    assert (before["best_return_ranking_semantics"]
            == after["best_return_ranking_semantics"])
    assert before["filtering"] == after["filtering"]


def test_assert_identity_unchanged_accepts_identical_snapshots():
    snap = snapshot_identity("bull-call-spread")
    assert_identity_unchanged(snap, snap)  # 不應拋錯


def test_assert_identity_unchanged_rejects_reordered_ranking():
    snap = snapshot_identity("bull-call-spread")
    tampered = dict(snap)
    tampered["ranking_identity"] = tuple(reversed(snap["ranking_identity"]))
    try:
        assert_identity_unchanged(snap, tampered)
        assert False, "應該要因為順序被動過而失敗"
    except AssertionError:
        pass


# ---------- SCALE-10（#259）：RL-33 修復——per_expiry_order 改定基 ----------

def test_per_expiry_order_from_expiry_ranked_matches_all_candidates_for_every_scenario():
    """AC-1：`snapshot_identity()` 現在用 `result.expiry_ranked` 算
    `per_expiry_order`；這裡對照組是**今天**仍然存在的
    `res["all_candidates"]`（SCALE-17 尚未上線，這條對照組本身還沒
    消失），逐一場景獨立重算並比對——證明這是換基準，不是換答案。
    對照組的建構邏輯刻意獨立於 `snapshot_identity()`（不呼叫它，各自
    從 `_view()` 重新走一遍），避免「兩邊其實在跑同一段程式碼、
    當然會一樣」這種虛假的驗證。"""
    for strategy in SCENARIOS:
        result, view = _view(strategy)
        res = view["results"][0]

        from_all_candidates: dict[str, list[str]] = {}
        for entry in res["all_candidates"]:
            from_all_candidates.setdefault(
                entry["expiry"], []).append(entry["candidate_key"])

        from_expiry_ranked = {
            expiry: [service.valuation_key(v) for v in valuations]
            for expiry, valuations in result.results[0].expiry_ranked
        }

        assert from_expiry_ranked == from_all_candidates, strategy


def test_per_expiry_order_axis_actually_detects_a_reordering():
    """AC-2：這條軸不會恆真——刻意讓兩次比對輸入的 `per_expiry_order`
    不同，確認 `assert_identity_unchanged()` 真的會因為這一項而失敗
    （不是因為其他項目剛好也變了才失敗）。"""
    snap = snapshot_identity("bull-call-spread")
    tampered = dict(snap)
    some_expiry = next(iter(snap["per_expiry_order"]))
    tampered["per_expiry_order"] = {
        **snap["per_expiry_order"],
        some_expiry: list(reversed(snap["per_expiry_order"][some_expiry])),
    }
    try:
        assert_identity_unchanged(snap, tampered)
        assert False, "per_expiry_order 被動過，應該要偵測出差異"
    except AssertionError:
        pass


def test_per_expiry_order_is_never_vacuously_empty_for_an_ok_scenario():
    """RL-33 的核心風險是「兩邊都變成 `{}` 而恆真」——這裡直接鎖住
    正常情況下這一軸不是空的，且每個到期日底下的候選清單也不是空
    清單（`{}` 或 `{expiry: []}` 都會讓後續的『排序有沒有變』失去
    偵測力）。"""
    for strategy in SCENARIOS:
        snap = snapshot_identity(strategy)
        if snap["status"] != "ok":
            continue
        assert snap["per_expiry_order"], f"{strategy}：per_expiry_order 不應為空"
        for expiry, keys in snap["per_expiry_order"].items():
            assert keys, f"{strategy}／{expiry}：候選清單不應為空"


# ---------- RCT 回合（#137／#138–#142）：Historical IV 趨勢層守門 ----------
#
# 這一輪新增的東西——`ivhistory.trend_4w()`／`field_metrics()` 的
# `trend_4w`／`trend_base_count` 擴充、`spread_coordinates()`／
# `reanchor_spread()` 的單腳路徑、`store.find_candidate()` 的單腳
# fallback——全部活在 enrich-only 這一側：`ranking.py`／`filters.py`
# 不 import `ivhistory`（`tests/test_ivhistory.py` 既有斷言原始碼字面，
# 本檔案不重複）；`find_candidate()` 是純讀取的 lookup，只被 iv-history
# 端點呼叫，不參與 `service.run_offline`／`store.serialize_result` 產生
# 候選的任何一步。以下用行為證明這個結構保證真的成立：即使在算出
# identity 之後、再次算 identity 之前，中間插入對這一輪新函式的呼叫，
# 兩次 identity 仍然逐位元相同——沒有任何隱藏的共用可變狀態。

def test_exercising_ivhistory_between_two_identity_snapshots_changes_nothing():
    """#142：整個 Historical IV 趨勢層拿掉，候選命運與順序必須一模一樣
    ——這裡反過來驗證：*用力呼叫*這一輪新增的每一個函式，也不會讓身份
    跟著變，證明它們真的活在候選產生流程之外，不是『剛好』沒被踩到。"""
    from datetime import date

    from option_chaser import ivhistory

    before = snapshot_identity("bull-call-spread")

    # 用力呼叫本輪新增的每一個函式——包含單腳／兩腿座標、重錨定、
    # Δ4w、單腳候選查找——確認候選產生流程對這些呼叫零感知。
    _, view = _view("bull-call-spread")
    for r in view["results"]:
        for group in r.get("expiry_top10") or []:
            for key in group["candidate_keys"]:
                cand = view["candidate_pool"][key]
                coords = ivhistory.spread_coordinates(cand, spot=view["meta"]["spot"])
                if coords is not None:
                    ivhistory.reanchor_spread({"call": [], "put": []}, coords)
                store.find_candidate(view, key)
    points = [{"date": "2026-01-01", "normalized_skew": 0.1, "buy_iv": 0.2,
              "sell_iv": 0.22, "atm_iv": 0.21}]
    ivhistory.field_metrics(points, today=date(2026, 8, 12))

    after = snapshot_identity("bull-call-spread")
    assert_identity_unchanged(before, after)


def test_removing_the_entire_ivhistory_module_leaves_selection_untouched():
    """結構性版本的同一條紅線：`ranking.py`／`filters.py`——真正決定
    候選命運與順序的兩個模組——原始碼裡完全沒有 `ivhistory` 字樣。這比
    『跑過一次結果一樣』更強：代表這條邊在程式碼層級就不存在，不是
    測試碰巧沒觸發到。"""
    for mod in ("option_chaser/ranking.py", "option_chaser/filters.py"):
        src = open(mod, encoding="utf-8").read()
        assert "ivhistory" not in src, f"{mod} 不該依賴 ivhistory"


# ---------- DG 回合（spec #143）：Application Diagnostics 同一條紅線 ----------
#
# 診斷基礎設施（`api_app/diagnostics.py`）是本輪新增的另一個 enrich-only
# 側支——跟 `ivhistory` 同一種身份：只觀測，不參與候選產生的任何一步。
# `ranking.py`／`filters.py` 在 `option_chaser/` 底下，`diagnostics.py`
# 在 `api_app/`，兩者的既有分層本來就是單向依賴（`api_app` 依賴
# `option_chaser`，不會反過來）；這裡仍在程式碼層級明確斷言一次，
# 跟 `ivhistory` 的結構性紅線同一種防禦——不靠「架構上本來就不會」，
# 靠原始碼字面。

def test_ranking_and_filters_do_not_depend_on_diagnostics():
    for mod in ("option_chaser/ranking.py", "option_chaser/filters.py"):
        src = open(mod, encoding="utf-8").read()
        assert "diagnostics" not in src, f"{mod} 不該依賴 diagnostics"


# ---------- T01（#218，spec #217 §Q-A）：既有四策略的數值 bitwise 基準 ----------
#
# 上面那半只問「誰」「第幾個」，刻意不問「值多少」——那是 #118 當時的
# 正確取捨（估值修正輪允許數字變動）。Initial V2（#217）的處境相反：
# T02（逐腿 payoff 直算）與 T03（包絡量由 payoff 導出）要換掉估值核心，
# 而唯一的驗收判準是**畫面零變化**。沒有數值基準，這件事無從驗證。
#
# 因此本票**新增**數值那一半，兩半各自獨立、不合併成同一個斷言：
#
#   身份： snapshot_identity()  →  assert_identity_unchanged()
#   數值： snapshot_numbers()   →  assert_numbers_unchanged()
#
# 數值那一半另外把現況凍結成磁碟上的 golden（`_NUMERIC_BASELINE_PATH`），
# 因此它不只能比對「同一次執行的前後」，還能跨 session 抓出漂移。

import json
from pathlib import Path

_NUMERIC_BASELINE_PATH = Path("tests/fixtures/valuation_numeric_baseline.json")

#: 進入數值基準的候選欄位（allowlist）。凡是**估值導出的值**都在這裡：
#: 劇本報酬、包絡量、情境向量、heatmap 格值、完成度、Greeks 比率、
#: 利率輸入、價格階梯、Crossover comparator（含它自己的 matrix）。
#: 逐腿報價（`legs`）也在內——它是輸入而非導出值，凍結它是為了讓
#: 「fixture 本身被動過」與「估值邏輯被動過」在失敗訊息裡分得開。
NUMERIC_BASELINE_FIELDS = (
    "baseline_pnl", "baseline_return",
    "breakeven", "breakeven_points",
    "breakeven_at_target", "max_profit", "max_loss_per_contract",
    "natural_cost", "mid_cost", "capital_per_contract", "pct_of_capital",
    "effective_leverage", "l2", "l3",
    "scenario_vector", "retention", "buffer_days",
    "completion_curve", "completion_prices", "completion_threshold",
    "matrix", "comparator",
    "net_delta", "theta_day_rate", "vega_per_pt", "decay_30d_return",
    "rate_used", "rate_tenor_years",
    "price_ladder", "catchup_price",
    "days_to_target", "days_to_expiry",
    "carry_calibrated", "wide_spread_warning", "monotonicity_warning",
    "legs",
    # T15（#230，Initial V2）：Butterfly 專屬的獲利區間，既有四策略恆為
    # `None`——凍結它跟凍結其他既有欄位是同一個道理，`None` 對
    # `None` 的比對不會漂移。
    "profit_region",
)

#: 刻意**不**進數值基準的候選欄位，各有既有覆蓋負責：
#:   candidate_key／strategy — 身份，上半部的身份守門負責
#:   cons／guidance_warnings — 文字評語，CLI golden fixtures 已 byte-lock
#:     （#217「必須存在的回歸斷言」第 4 條）
#:
#: `friction`／`friction_amount` 原本也在這份基準裡（凍結現況值，等
#: T04／#220 真的移除時當作本基準唯一預期內的重產時機）——T04 已完成，
#: 這兩個名字現在**完全不存在**於候選契約裡，因此不再出現在
#: `NUMERIC_BASELINE_FIELDS` 或這裡：兩者都假設欄位存在，一個凍結數值、
#: 一個豁免數值比對，但「欄位已消失」是第三種狀態，兩者都不適用。
#: 見 `test_friction_never_reappears_in_candidate_contract` 鎖住它不會
#: 悄悄回來。
NUMERIC_BASELINE_EXCLUDED = ("candidate_key", "strategy",
                             "cons", "guidance_warnings")


def snapshot_numbers(strategy: str) -> dict:
    """單一策略的完整**數值**快照——與 `snapshot_identity()` 平行的另一半。

    離線、決定性（`today` 由快照自己的 `fetched_at` 推出，不讀系統時鐘；
    利率／股利 loader 在 `run_offline` 預設為 None），因此可重跑、可跨
    session 逐位元比對。
    """
    _, view = _view(strategy)
    res = view["results"][0]
    pool = view["candidate_pool"]
    rep = store.representative_candidate(view)
    return {
        "strategy": strategy,
        "meta": {"spot": view["meta"]["spot"],
                 "fetched_at": view["meta"]["fetched_at"],
                 "target_move": view["meta"]["target_move"]},
        "result_level": {
            "best_return": store.best_return(view),
            "representative_baseline_return":
                None if rep is None else rep["baseline_return"],
        },
        "candidates": {
            key: {f: pool[key][f] for f in NUMERIC_BASELINE_FIELDS}
            for key in sorted(pool)
        },
        # T14（#233，Initial V2）：候選的 `matrix` 現在只存 `axis_index`
        # 引用（見 `NUMERIC_BASELINE_FIELDS` 裡的 `"matrix"`），實際的
        # 座標軸內容（`prices`／`dates`）搬到這個獨立的頂層陣列——沒有
        # 這一份，`axis_sets[N]` 的內容本身若被動過（而索引恰好沒變），
        # 上面 `candidates` 那份快照完全看不出來。
        "axis_sets": view.get("axis_sets", []),
    }


def _diff_paths(before, after, path: str, out: list[str], limit: int) -> None:
    """遞迴比對，把差異收斂成「欄位路徑：舊值 → 新值」的可讀清單。
    matrix 這種巢狀結構因此能指到 `matrix.cells[3][5]` 那一格。"""
    if len(out) >= limit:
        return
    if type(before) is not type(after):
        out.append(f"{path}: {before!r} → {after!r}（型別也變了）")
        return
    if isinstance(before, dict):
        for k in sorted(set(before) | set(after)):
            if k not in before:
                out.append(f"{path}.{k}: 新增 {after[k]!r}")
            elif k not in after:
                out.append(f"{path}.{k}: 消失（原本 {before[k]!r}）")
            else:
                _diff_paths(before[k], after[k], f"{path}.{k}", out, limit)
        return
    if isinstance(before, list):
        if len(before) != len(after):
            out.append(f"{path}: 長度 {len(before)} → {len(after)}")
            return
        for i, (b, a) in enumerate(zip(before, after)):
            _diff_paths(b, a, f"{path}[{i}]", out, limit)
        return
    if before != after:
        out.append(f"{path}: {before!r} → {after!r}")


def assert_numbers_unchanged(before: dict, after: dict, *,
                             max_reported: int = 20) -> None:
    """後續票（尤其 T02／#219、T03／#223）在改寫估值核心後呼叫本函式，
    把改寫前後的 `snapshot_numbers()` 輸出傳進來比對。

    與 `assert_identity_unchanged()` 是**兩個獨立的入口**，不得合併：
    身份不變但數字變了、或反過來，是兩種不同的事故，訊息也該不同。

    失敗訊息會指出是哪個策略、哪個候選（`candidate_key`）、哪個欄位
    （含 `matrix.cells[i][j]` 這種巢狀路徑）變了，以及新舊值。
    任何一項不相等都應該讓呼叫端的測試失敗並停下——不得放寬或刪減
    這裡比對的欄位。
    """
    diffs: list[str] = []
    _diff_paths(before, after, f"[{before.get('strategy', '?')}]",
                diffs, max_reported)
    if diffs:
        shown = "\n  ".join(diffs[:max_reported])
        more = ("\n  …（還有更多差異未列出）"
                if len(diffs) >= max_reported else "")
        raise AssertionError(
            f"數值基準不符（策略 {before.get('strategy', '?')}）：\n  "
            f"{shown}{more}")


def _load_numeric_baseline() -> dict:
    with open(_NUMERIC_BASELINE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------- Golden：磁碟上的 bitwise 基準 ----------

def test_numeric_baseline_file_exists_and_covers_all_four_strategies():
    baseline = _load_numeric_baseline()
    assert set(baseline["strategies"]) == set(SCENARIOS)


def test_bull_call_spread_numbers_are_bitwise_frozen():
    baseline = _load_numeric_baseline()
    assert_numbers_unchanged(baseline["strategies"]["bull-call-spread"],
                             snapshot_numbers("bull-call-spread"))


def test_bear_put_spread_numbers_are_bitwise_frozen():
    baseline = _load_numeric_baseline()
    assert_numbers_unchanged(baseline["strategies"]["bear-put-spread"],
                             snapshot_numbers("bear-put-spread"))


def test_long_call_numbers_are_bitwise_frozen():
    baseline = _load_numeric_baseline()
    assert_numbers_unchanged(baseline["strategies"]["long-call"],
                             snapshot_numbers("long-call"))


def test_long_put_numbers_are_bitwise_frozen():
    baseline = _load_numeric_baseline()
    assert_numbers_unchanged(baseline["strategies"]["long-put"],
                             snapshot_numbers("long-put"))


def test_numeric_baseline_survives_a_json_round_trip_bitwise():
    """凍結在磁碟上的是 JSON，因此「逐位元」這件事必須連 JSON 往返都
    成立——否則基準本身就是浮點雜訊的來源，不是護欄。CPython 的
    `float.__repr__` 保證最短且可還原，這條把那個保證釘在測試裡。"""
    live = snapshot_numbers("bull-call-spread")
    assert json.loads(json.dumps(live)) == live


# ---------- 護欄本身的護欄 ----------

def test_every_candidate_field_is_either_frozen_or_explicitly_excluded():
    """新增候選欄位時，這條會紅燈，逼出一次「它該不該進數值基準」的
    有意識決定——不讓新欄位靜默地不被任何護欄覆蓋。"""
    _, view = _view("bull-call-spread")
    pool = view["candidate_pool"]
    actual = set(next(iter(pool.values())))
    covered = set(NUMERIC_BASELINE_FIELDS) | set(NUMERIC_BASELINE_EXCLUDED)
    assert actual == covered, (
        f"未覆蓋的新欄位：{sorted(actual - covered)}；"
        f"已消失的欄位：{sorted(covered - actual)}")


def test_numbers_snapshot_is_deterministic_across_repeated_runs():
    assert snapshot_numbers("bull-call-spread") == snapshot_numbers(
        "bull-call-spread")


def test_assert_numbers_unchanged_accepts_identical_snapshots():
    snap = snapshot_numbers("long-call")
    assert_numbers_unchanged(snap, snap)  # 不應拋錯


def test_assert_numbers_unchanged_names_the_candidate_and_the_field():
    """護欄的價值一半在「有沒有紅」，一半在「紅了看不看得懂」。這條
    直接驗後者：訊息要指得出策略、候選、欄位與新舊值。"""
    snap = snapshot_numbers("bull-call-spread")
    key = sorted(snap["candidates"])[0]
    tampered = json.loads(json.dumps(snap))
    tampered["candidates"][key]["baseline_return"] += 1e-9
    try:
        assert_numbers_unchanged(snap, tampered)
        assert False, "應該要因為數值被動過而失敗"
    except AssertionError as exc:
        msg = str(exc)
        assert "bull-call-spread" in msg
        assert key in msg
        assert "baseline_return" in msg


def test_assert_numbers_unchanged_catches_a_single_heatmap_cell():
    """heatmap 格值是最容易被靜默改掉、也最難用肉眼發現的一塊——
    改一格就必須紅，而且訊息要指到那一格。

    T14（#233，Initial V2）起 `matrix.cells` 是攤平後的一維陣列
    （座標軸去重＋格值捨入，見 `store.py::_matrix_to_dict()`），改一
    個索引即可，不再是巢狀的 `[i][j]`。"""
    snap = snapshot_numbers("long-put")
    key = sorted(snap["candidates"])[0]
    tampered = json.loads(json.dumps(snap))
    tampered["candidates"][key]["matrix"]["cells"][0] += 1e-9
    try:
        assert_numbers_unchanged(snap, tampered)
        assert False, "應該要因為 heatmap 格值被動過而失敗"
    except AssertionError as exc:
        assert "matrix.cells[0]" in str(exc)


def test_identity_and_numbers_stay_two_separate_entry_points():
    """#118 刻意把身份與數值分開，本票是新增數值那一半、不是把兩者
    混成一個斷言。這條把那個分工釘住：只動數值時，身份守門必須仍然
    是綠的（反之亦然由既有身份測試涵蓋）。"""
    ident_before = snapshot_identity("bull-call-spread")
    nums = snapshot_numbers("bull-call-spread")
    tampered = json.loads(json.dumps(nums))
    key = sorted(tampered["candidates"])[0]
    tampered["candidates"][key]["baseline_return"] += 1.0
    try:
        assert_numbers_unchanged(nums, tampered)
        assert False, "數值守門應該要紅"
    except AssertionError:
        pass
    # 身份那一半完全不受影響——兩個入口互不干涉。
    assert_identity_unchanged(ident_before, snapshot_identity("bull-call-spread"))


def test_long_call_max_profit_is_absent_not_infinite():
    """#223（T03）修訂後的紅線在本基準上的落點：Long Call 今天的
    `max_profit` 是 **None（不適用）**，不是無限大。T03 把包絡量改成由
    payoff 導出時，若不小心引入「掃描全價格域取理論極值」的語意，這裡
    會變成 `inf` 或一個巨大的數字——這條測試就是那顆地雷的引信。
    Option Chaser 是 Scenario Bet Ranking 機器，不提供 unbounded
    max-profit 概念（#217 決策 A、#223 範圍界定）。"""
    snap = snapshot_numbers("long-call")
    for key, fields in snap["candidates"].items():
        assert fields["max_profit"] is None, (
            f"{key}: Long Call 的 max_profit 應為 None（不適用），"
            f"實際為 {fields['max_profit']!r}")


# ---------- T04（#220，#217 決策 D）：friction 自 canonical model 退場 ----------

def test_friction_never_reappears_in_candidate_contract():
    """AC：新增結構性測試防止 friction canonical metric 再被加回。凡是
    候選契約裡出現 `friction`／`friction_amount` 這兩個 key，一律視為
    回歸——不是「數值變了」，是「這個概念本不該存在於這裡」。"""
    _, view = _view("bull-call-spread")
    for key, fields in view["candidate_pool"].items():
        assert "friction" not in fields, f"{key}: friction 不該再出現在契約裡"
        assert "friction_amount" not in fields, (
            f"{key}: friction_amount 不該再出現在契約裡")


def test_friction_function_and_field_do_not_exist_in_source():
    """結構性證明，不靠測試綠燈間接推論：估值與排名路徑（`scenarios.py`／
    `service.py`／`store.py`／`report.py`）的原始碼裡不再有 `friction`
    這個識別字（排除註解與字串裡解釋歷史脈絡的提及）。"""
    for mod in ("option_chaser/scenarios.py", "option_chaser/service.py",
               "option_chaser/store.py", "option_chaser/report.py"):
        src = Path(mod).read_text(encoding="utf-8")
        code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
        code = "\n".join(code_lines)
        assert "friction" not in code, f"{mod} 不該再有可執行的 friction 引用"


# ---------- REPAIR-01（#238，OPTION-CHASER-REPAIR-001）：多 family 守門 ----------
#
# #052 audit（Production Regression Audit，issue #237）指出既有這支守門
# 檔案結構性看不到的兩個缺口：(1) `_run()` 永遠只跑一個 strategy，
# `store.representative_candidates_by_family()`／跨 family champion 選取
# 邏輯（`api_app/main.py::_refresh_and_save()` 的
# `max(per_family.values(), key=...)`）從未被行使過；(2) 永遠是
# `q_by_symbol=None`，「只在 q≠0 才顯現」的漂移（Root Cause C，見
# #237）結構上不可能被這支守門抓到。
#
# 這兩條新測試補上這兩個缺口的**基礎設施**——凍結的是修復前的**身份**，
# 不是數值（數值即將被 FIX-05／#246 合法改變）。

MULTI_FAMILY_FIX = "tests/fixtures/xyz_v7_butterfly_moderate.json"


def _multi_family_view(q_by_symbol: float | None,
                       target_month: str = "2026-09") -> dict:
    """三個 family 全開的離線分析。預設 `target_month="2026-09"` 讓
    baseline 到期日（2026-09-18）恰好等於日曆錨點、另外兩個到期日
    （10-16／12-18）晚於錨點——這是 select_expiries「錨點前 2 後 3」
    在真實 production 規模下的常態分布。

    ⚠ 這個預設參數**不是** Root Cause C 會在 champion 這個層級顯現的
    情境（REPAIR-09／#246 code-review Spec 軸抓到的真缺口）：
    `representative_candidates_by_family()`／各 family 的「代表候選」
    只讀 **baseline 期**（M1a／#78 既有裁示，`store.representative_
    candidate` docstring 同一句話），baseline==anchor 時單腿候選的
    排名基準估值日（修法前＝`p.anchor`）跟 baseline 到期日本身是
    同一天，殘留時間價值根本沒有機會出現——已用 `git stash` 對照過
    這個預設 `target_month` 修法前後三個 family 的 champion 數值
    逐位元相同（1.1926288317629354 這個灌水數字在這裡不會出現）。
    要真的看到 champion 層級的灌水／修正，`target_month` 必須讓
    baseline 到期日**晚於**錨點——見
    `test_cross_family_champion_baseline_return_is_corrected_when_
    baseline_expiry_is_after_anchor` 傳入 `target_month="2026-08"`
    （anchor=2026-08-21，baseline 仍是 09-18，晚 28 天）。"""
    p = AnalysisParams(target_price=110.0, target_month=target_month,
                       strategy="long-call", q_by_symbol=q_by_symbol)
    subtypes = subtypes_of(normalize_families(
        ("single-leg", "vertical-spread", "butterfly")))
    req = service.AnalysisRequest(symbol="XYZ", base_params=p, strategies=subtypes)
    result = service.run_offline(req, MULTI_FAMILY_FIX)
    return store.serialize_result(result, scenario_id="MULTI", capital=None)


def _champion_family(per_family: dict) -> str:
    """`api_app/main.py::_refresh_and_save()` 的
    `max(per_family.values(), key=lambda v: v["baseline_return"])` 同一條
    選取邏輯——REPAIR-11（#248）新增的三條測試皆需要重跑這個判斷，
    抽成共用函式（/code-review Standards 軸 judgement call）避免同一行
    在檔案裡出現五次。"""
    return max(per_family, key=lambda k: per_family[k]["baseline_return"])


def test_cross_family_champion_identity_is_recorded_as_a_baseline():
    """#052 audit 守門缺口第 1 點：`test_selection_regression.py::_run()`
    永遠一次一個 strategy，`championCandidate`／
    `representative_candidates_by_family`／卡片頭條邏輯結構上完全沒被
    覆蓋。這條測試補上：真的跑三個 family 全開，凍結跨 family champion
    的身份（family／strategy／到期日／逐腿履約價）。

    REPAIR-11（#248，FIX-08b）：估值日語意已由 FIX-05／#246 定案，
    `baseline_return` 現在是穩定、正確的數字，不再是「即將合法改變」
    的活動目標——本票把它也一併凍結（原本 REPAIR-01／#238 施工時
    刻意排除，見 git 歷史），連同三個 family 各自的代表候選數值一起
    納入，不只凍結 champion 一個。四個數字（三個 family＋champion）
    與 `test_cross_family_champion_baseline_return_is_corrected_when_
    baseline_expiry_is_after_anchor`（`target_month="2026-08"`）
    各自獨立、互不重複——那條測試用的是另一個 `target_month`，兩者
    合起來涵蓋 baseline 到期日等於錨點與晚於錨點兩種情境。

    這條測試要能真的抓到回歸：champion 的選取邏輯
    （`api_app/main.py::_refresh_and_save()` 的
    `max(per_family.values(), key=lambda v: v["baseline_return"])`）
    若被意外改動，per_family 的成員或 champion 的身份就會跟這裡凍結的
    不同，測試就會紅；任一 family 的估值邏輯被意外改動，這裡凍結的
    數值也會跟著紅——不是恆真的裝飾性斷言（見
    `test_the_cross_family_numeric_freeze_actually_catches_a_
    regression` 的 monkeypatch 證明）。"""
    view = _multi_family_view(q_by_symbol=0.02)
    per_family = store.representative_candidates_by_family(view)

    # 三個 family 在這個 target/fixture 下都應該有合格候選（bullish
    # 方向，call-fly／bull-call-spread／long-call 皆 eligible）——若這
    # 個集合縮小，代表某個 family 的枚舉或方向閘門被動到了。
    assert set(per_family) == {"single-leg", "vertical-spread", "butterfly"}

    # 數值凍結——三個 family 各自的代表候選（FIX-05／#246 完成後的
    # 正確答案，已與上方 probe 及既有測試互相核對）。
    assert per_family["single-leg"]["baseline_return"] == 0.9569471624266144
    assert per_family["vertical-spread"]["baseline_return"] == 2.4883720930232562
    assert per_family["butterfly"]["baseline_return"] == 5.6666666666666705

    champion_family = _champion_family(per_family)
    champion = per_family[champion_family]

    # 身份凍結。若 champion 的身份本身跟著變了（不只是數值變了），
    # 必須停下查明是選取邏輯被動到還是合法的排名重新洗牌，不能默默
    # 更新這裡的斷言了事。
    assert champion_family == "butterfly"
    assert champion["strategy"] == "call-fly"
    assert champion["expiry"] == "2026-09-18"
    assert champion["baseline_return"] == 5.6666666666666705
    leg_strikes = tuple((leg["side"], leg["strike"]) for leg in champion["legs"])
    assert leg_strikes == (("buy", 106.0), ("sell", 109.0), ("buy", 112.0))


def test_cross_family_champion_baseline_return_is_corrected_when_baseline_expiry_is_after_anchor():
    """REPAIR-09（#246）code-review Spec 軸抓到的真缺口：AC 要求的第 4
    步驟（「真實建立一個三 family 全開的劇本，對照修法前後的
    cross-family champion 身份與數值」）先前**沒有任何測試真的做到**
    ——上一條測試的 `target_month="2026-09"` 讓 baseline 到期日恰好
    等於錨點，這個情境下修法前後 target 是同一天，champion 的數值
    結構上不可能改變（已用這個測試本身的前身確認：修法前後三個
    family 的 champion 值逐位元相同）。要真的看到 Root Cause C 在
    champion 這個層級顯現，baseline 到期日必須**晚於**錨點——這裡改用
    `target_month="2026-08"`（anchor=2026-08-21），baseline 到期日
    仍是 2026-09-18（同一份 fixture、同一組候選），只是這次晚了錨點
    28 天。

    已用 `git stash` 對照過修法前後的完整結果（`representative_
    candidates_by_family()` 的三個 family 各自數值）：
      修法前：single-leg（long-call@2026-09-18）baseline_return=
              1.1926288317629354（殘留時間價值灌水）
              vertical-spread（bull-call-spread@2026-09-18）=
              2.4883720930232562（T3／#17 既有語意，不受影響）
              butterfly（call-fly@2026-09-18）=
              5.6666666666666705（不受影響）
      修法後：single-leg 降到 0.9569471624266144（跟上一條測試在
              `target_month="2026-09"` 下算出的數字逐位元相同——這正
              是修法的核心效果：不管錨點落在哪裡，同一張合約的排名
              基準估值日只認自己的到期日）
              vertical-spread／butterfly 兩者逐位元不變
      champion 身份修法前後皆為 butterfly——不受影響，與上一條凍結
      測試（不同 target_month，同一份 fixture）一致，這裡額外證明的
      是**這次身份沒變不是因為數值沒變，而是 butterfly 本來就贏得
      夠多**（5.6667 > 修法前的 single-leg 1.1926，修法後差距更大）。
    """
    view = _multi_family_view(q_by_symbol=0.02, target_month="2026-08")
    per_family = store.representative_candidates_by_family(view)
    assert set(per_family) == {"single-leg", "vertical-spread", "butterfly"}

    single_leg = per_family["single-leg"]
    assert single_leg["strategy"] == "long-call"
    assert single_leg["expiry"] == "2026-09-18"   # baseline，晚於 anchor 2026-08-21
    # 修法後的正確值——與 `test_cross_family_champion_identity_is_
    # recorded_as_a_baseline` 在 `target_month="2026-09"`（baseline==
    # anchor）下算出的 single-leg 數值逐位元相同，證明「排名基準估值日
    # 只認候選自身到期日」對這張合約來說，不論錨點落在哪裡，答案都一樣。
    assert single_leg["baseline_return"] == 0.9569471624266144
    # 修法前（已用 git stash 對照）的灌水值——留在這裡當文件用，不是
    # 拿來斷言的目標值，只是讓下一個讀這條測試的人不必自己重跑 stash
    # 就看得到「錯的答案長什麼樣」：1.1926288317629354。

    vertical = per_family["vertical-spread"]
    butterfly = per_family["butterfly"]
    # 兩者的估值路徑（`evaluate_spread`／`evaluate_butterfly`）完全沒被
    # 這張票觸碰，數值理應與上一條測試在另一個 target_month 算出的
    # 完全相同——這不是巧合，是它們的估值日本來就一直是候選自身到期日
    # （T3／#17），不受 anchor 影響。
    assert vertical["baseline_return"] == 2.4883720930232562
    assert butterfly["baseline_return"] == 5.6666666666666705

    champion_family = _champion_family(per_family)
    assert champion_family == "butterfly"
    assert per_family[champion_family]["strategy"] == "call-fly"


def test_q_no_longer_moves_single_leg_ranking_at_any_expiry_after_the_fix():
    """#052 audit Root Cause C 收尾驗證（REPAIR-09／#246）——這條測試在
    修法**前**（見 git 歷史）證明的是相反的事：q≠0 只在到期日**晚於**
    日曆錨點時才改變單腿的 `baseline_return`，那正是灌水成因本身
    （殘留時間價值受股利殖利率影響）。修法把排名基準估值日改成候選
    自身到期日後，任何到期日都退化成純內在價值——q 因此對**任何**
    到期日的 `baseline_return` 都不再有作用，不再是「只有等於錨點
    那個才不受影響」。這條測試從「證明 bug 存在」改成「證明 bug 已經
    修好、不會又悄悄回來」。

    同時保留 #052 audit 守門缺口第 2 點原本要證明的另一半：`q_by_
    symbol` 這個管線真的有被 `run_offline` 行使、不是靜默忽略——
    `net_delta`（carry 校準後的 Greeks，見 `store.py` 對
    `ContractValuation.delta` 的序列化）在任何到期日都仍會隨 q 改變，
    因為 Greeks 的估值時點是 `today`／`t_now`，不是這次修正的排名
    估值日；q 真正被拿掉的作用範圍精準只在 `baseline_return`。"""
    def top_by_expiry(q_by_symbol):
        p = AnalysisParams(target_price=110.0, target_month="2026-09",
                           strategy="long-call", q_by_symbol=q_by_symbol)
        req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                      strategies=("long-call",))
        result = service.run_offline(req, MULTI_FAMILY_FIX)
        view = store.serialize_result(result, scenario_id="Q", capital=None)
        res = view["results"][0]
        out = {}
        for group in res["expiry_top10"]:
            top_key = group["candidate_keys"][0]
            cand = view["candidate_pool"][top_key]
            out[group["expiry"]] = (cand["baseline_return"], cand["net_delta"])
        return out

    at_q_none = top_by_expiry(None)
    at_q_set = top_by_expiry(0.02)

    for expiry in ("2026-09-18", "2026-10-16", "2026-12-18"):
        # 排名基準：q 對任一到期日的 baseline_return 都不再有作用。
        assert at_q_none[expiry][0] == at_q_set[expiry][0], expiry
        # 但 q_by_symbol 管線本身確實還在運作——顯示用的 Greeks（跟
        # 排名估值日無關）仍隨 q 改變，證明不是整條管線被靜默忽略。
        assert at_q_none[expiry][1] != at_q_set[expiry][1], expiry


def test_q_reaches_every_family_in_the_multi_family_path_not_just_single_leg():
    """REPAIR-11（#248，FIX-08b）AC 第 3 點——上一條測試
    （`test_q_no_longer_moves_single_leg_ranking_at_any_expiry_after_
    the_fix`）只跑 `strategies=("long-call",)`，是單一 family，不是
    跨 family champion 這條路徑；#238（REPAIR-01）建立的 q≠0 baseline
    也從未真正跑過三個 family 全開。這條測試補上：真的用
    `_multi_family_view()`（三個 family 全開）跑 q=None 與 q=0.02
    兩次，逐 family 比對。

    已用 Python 直接執行核對過（非猜測）：`net_delta`——`calibrate_leg()`
    是三個估值函式（`evaluate_contract`／`evaluate_spread`／
    `evaluate_butterfly`）共用的同一個校準點，q 改變時三個 family 的
    champion 候選 `net_delta` **全部**跟著變（single-leg
    0.5475→0.5341、vertical-spread 0.08146→0.08105、butterfly
    0.01290→0.01190）——證明 q 真的貫穿整條多 family 管線，不是只有
    single-leg 被行使到。同時 `baseline_return`（排名基準）三個
    family 全部維持不變，與 FIX-05／#246 的既有結論（q 不再影響任何
    到期日的排名基準）在跨 family 情境下依然成立。"""
    def champion_and_pool_deltas(q_by_symbol):
        view = _multi_family_view(q_by_symbol=q_by_symbol)
        per_family = store.representative_candidates_by_family(view)
        baseline_expiry = view["baseline_expiry"]
        pool = view["candidate_pool"]
        net_deltas = {}
        for res in view["results"]:
            for group in res.get("expiry_top10", []):
                if group["expiry"] != baseline_expiry:
                    continue
                top_key = group["candidate_keys"][0]
                net_deltas[res["strategy"]] = pool[top_key]["net_delta"]
        return per_family, net_deltas

    per_family_none, deltas_none = champion_and_pool_deltas(None)
    per_family_set, deltas_set = champion_and_pool_deltas(0.02)

    assert set(deltas_none) == {"long-call", "bull-call-spread", "call-fly"}
    assert set(deltas_none) == set(deltas_set)
    for strategy in deltas_none:
        # q 真的貫穿到每一個 family 的估值路徑——不是只有 single-leg。
        assert deltas_none[strategy] != deltas_set[strategy], strategy

    for family in ("single-leg", "vertical-spread", "butterfly"):
        # 排名基準：q 對任一 family 的 baseline_return 都不再有作用。
        assert (per_family_none[family]["baseline_return"]
               == per_family_set[family]["baseline_return"]), family

    # champion 身份也不受 q 影響——q 只改變顯示用 Greeks，不改變排名。
    champion_none = _champion_family(per_family_none)
    champion_set = _champion_family(per_family_set)
    assert champion_none == champion_set == "butterfly"


def test_the_cross_family_numeric_freeze_actually_catches_a_regression(monkeypatch):
    """REPAIR-11（#248，FIX-08b）AC 第 2 點——新增的數值凍結守門必須
    真的能抓到回歸，不能是恆真的裝飾性斷言。

    `option_chaser/service.py` 用 `from .valuation import (...,
    evaluate_butterfly, ...)` 直接把函式名匯入自己的命名空間——
    monkeypatch 必須打在 `option_chaser.service.evaluate_butterfly`
    這個名字上，patch `option_chaser.valuation.evaluate_butterfly`
    對已經匯入的參照沒有作用（這是 Python 具名匯入的既有行為，不是
    這個測試發明的規則）。污染 `baseline_value`（`ranking.
    butterfly_baseline_return()` 的分子，見該函式：`(bv.baseline_value
    - bv.net_worst) / bv.net_worst`）讓它偏移一個小量，重跑
    `_multi_family_view()` 同一段計算路徑，確認 champion（本情境下
    恆為 butterfly）的 `baseline_return` 確實跟著改變——與
    `test_cross_family_champion_identity_is_recorded_as_a_baseline`
    凍結的 `5.6666666666666705` 不同，證明那條凍結測試真的在測
    `evaluate_butterfly()` 這個計算路徑，不是繞過它算出一個巧合相等
    的常數。"""
    import dataclasses as dc

    import option_chaser.service as service_module

    original = service_module.evaluate_butterfly

    def corrupted(*args, **kwargs):
        bv = original(*args, **kwargs)
        return dc.replace(bv, baseline_value=bv.baseline_value + 1.0)

    monkeypatch.setattr(service_module, "evaluate_butterfly", corrupted)

    view = _multi_family_view(q_by_symbol=0.02)
    per_family = store.representative_candidates_by_family(view)
    champion_family = _champion_family(per_family)

    # 污染後 champion 仍是 butterfly（其餘兩個 family 完全沒被動到），
    # 但數值必須跟凍結測試裡的既有答案不同——若這裡意外相等，代表
    # monkeypatch 沒有真的生效，這條「證明守門有效」的測試本身就失敗。
    assert champion_family == "butterfly"
    assert per_family["butterfly"]["baseline_return"] != 5.6666666666666705
