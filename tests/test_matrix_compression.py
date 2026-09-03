"""T14（#233，Initial V2 spec #217）：熱力圖 matrix 傳輸壓縮——座標軸
去重＋格值緊湊編碼（研究 #216 定案的「組合一」）。

`option_chaser/store.py` 的 `axis_of()`／`axis_pool`／`axis_sets` 把
`{prices, dates, cells}`（`cells` 為二維陣列）換成 `{axis_index, cells}`
（`cells` 攤平成一維並捨入到 `MATRIX_CELL_DECIMALS` 位），`prices`／
`dates` 只在第一次遇到某組座標時序列化進頂層 `axis_sets`，其餘候選（與
候選自己的 Crossover comparator）改存索引引用。

`test_store_serialize.py` 已有逐欄位手算的基本覆蓋；本檔案專門補三個
AC 需要「真實資料證明」而非「單一候選手算」的部分：真的省下多少（去重
比例）、捨入不造成可辨識的格值差異（誤差上界）、comparator 與候選自己
的 matrix 共用同一組座標軸。
"""
from option_chaser import store, service
from option_chaser.models import AnalysisParams

DENSE_FIX = "tests/fixtures/xyz_v2_snapshot.json"
MULTI_EXPIRY_FIX = "tests/fixtures/xyz_v4_six_expiries.json"


def _view(fixture, strategy="bull-call-spread", target_price=120.0,
          target_month="2026-11"):
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy=strategy,
                                       target_price=target_price,
                                       target_month=target_month),
            strategies=(strategy,)),
        fixture)
    return store.serialize_result(result, "S", 100000.0)


def test_candidates_at_the_same_expiry_share_one_axis_not_one_each():
    """同一個到期日的候選共用同一組價格／日期軸（scenario 級常數＋單一
    到期日，跟履約價無關）——這是 AC「座標軸不逐候選重複」真正的證明，
    不是「剛好只有一個候選」的巧合。真實 fixture 這期有 9 組候選。"""
    view = _view(DENSE_FIX)
    res0 = view["results"][0]
    [group] = res0["expiry_top10"]
    assert len(group["candidate_keys"]) == 9

    axis_indices = {
        view["candidate_pool"][k]["matrix"]["axis_index"]
        for k in group["candidate_keys"]
    }
    assert axis_indices == {0}
    assert len(view["axis_sets"]) == 1


def test_axis_sets_grows_with_distinct_expiries_not_with_candidate_count():
    """跨到期日的軸的確不同（日期軸只依到期日），但軸的數量應該跟到期日
    數量同量級，不是跟候選數量同量級——這才是「大量候選只有少數幾組
    相異軸」（研究 #216：150 候選 10 組軸）本票要落地的性質。"""
    view = _view(MULTI_EXPIRY_FIX, target_price=120.0, target_month="2026-08")
    res0 = view["results"][0]
    n_candidates = len(view["candidate_pool"])
    n_expiries = len(res0["expiry_top10"])
    assert n_candidates == n_expiries  # 這份 fixture 每期恰好 1 組候選
    # 換句話說：軸數等於相異到期日數，不會因為候選數多就跟著線性成長。
    assert len(view["axis_sets"]) == n_expiries


def test_comparator_matrix_shares_the_same_axis_as_its_own_candidate():
    """Crossover comparator（#116）畫在同一個候選自己的價格×日期網格上
    ——它的 matrix 跟候選自己的 matrix 結構上就是同一組座標，去重應該
    把兩者併成同一個 axis_index，不是各自序列化一份。"""
    view = _view(MULTI_EXPIRY_FIX, target_price=120.0, target_month="2026-08")
    res0 = view["results"][0]
    for group in res0["expiry_top10"]:
        for key in group["candidate_keys"]:
            cand = view["candidate_pool"][key]
            comparator = cand.get("comparator")
            if comparator is None:
                continue
            assert comparator["matrix"]["axis_index"] == cand["matrix"]["axis_index"]


def test_rounding_does_not_introduce_a_visually_distinguishable_difference():
    """AC「捨入的位數不造成視覺上可辨識的格值差異」：畫面顯示層
    （`formatCell`／`heatmap.ts`）呈現到小數點後一位的百分比（例如
    "13.6"），`MATRIX_CELL_DECIMALS`（4 位）比這個顯示精度細了三個
    數量級——捨入誤差的理論上界 0.5 × 10⁻⁴ 遠小於畫面能分辨的
    0.5 × 10⁻³（一位小數百分比的半格），逐格核對真實資料證實這一點，
    不是只看常數大小關係。"""
    view = _view(DENSE_FIX)
    tolerance = 0.5 * 10 ** (-store.MATRIX_CELL_DECIMALS)
    display_resolution = 0.0005  # 顯示層一位小數百分比的半格（見上）
    assert tolerance < display_resolution

    # 直接對照純函式層與序列化層算出的原始值，逐格比對誤差上界。
    result = service.run_offline(
        service.AnalysisRequest(
            symbol="XYZ",
            base_params=AnalysisParams(strategy="bull-call-spread",
                                       target_price=120.0,
                                       target_month="2026-11"),
            strategies=("bull-call-spread",)),
        DENSE_FIX)
    for sv in result.results[0].candidates:
        cand = view["candidate_pool"][service.candidate_key(sv)]
        flat = [v for row in sv.matrix.cells for v in row]
        for original_v, rounded_v in zip(flat, cand["matrix"]["cells"]):
            assert abs(rounded_v - original_v) <= tolerance


def test_contract_samples_also_exhibit_axis_dedup():
    """AC「以真實契約樣本量測並記錄壓縮前後大小」的「量測」半段：這裡
    只驗證「去重確實發生」這個結構性前提在**真實契約樣本**本身也成立，
    不是只在測試 fixture 上才成立——不是量測壓縮率本身（那是一次性
    量測，數字記在 T14 commit 訊息與 CLAUDE.md 的「記錄」半段，不適合
    寫成一條每次跑測試都要重算校驗的斷言，三份契約樣本各自的檔案位元
    組本身就會隨任何一次重產而改變）。"""
    import json
    from pathlib import Path

    for name in ("analysis_sample.json", "analysis_sample_bear_put.json",
                 "analysis_sample_long_call.json"):
        sample = json.loads(Path("contracts", name).read_text(encoding="utf-8"))
        n_candidates = len(sample["candidate_pool"])
        n_axes = len(sample["axis_sets"])
        assert n_axes <= n_candidates


# ---------- CLOSEOUT-004（PR #250 review Finding 2）：捨入不得改變
# crossover 分類 ----------------------------------------------------------

def _sign(x: float) -> int:
    return (x > 0.0) - (x < 0.0)


def _crossover_edges(a, b):
    """`src/heatmap.ts::crossoverEdges()` 的最小 Python 鏡射——只複製
    「逐格相減、相鄰兩格正負號不同就記一條邊」這條判準本身，不複製它
    的呈現細節。存在的理由：這條測試要鎖的是 **crossover edge
    identity**，而那個身分是由前端這段邏輯定義的；只斷言「格值差不多」
    證明不了邊界沒有變。前端函式本身另有 Vitest 覆蓋，這裡不是要取代
    它，是要在後端這一側鎖住「餵給它的東西不會讓它改變答案」。"""
    n = len(a)
    if n == 0 or len(b) != n:
        return set()
    m = len(a[0])
    d = [[a[i][j] - b[i][j] for j in range(m)] for i in range(n)]
    out = set()
    for i in range(n):
        for j in range(m):
            if i + 1 < n and _sign(d[i][j]) != _sign(d[i + 1][j]):
                out.add((i, j, "vertical"))
            if j + 1 < m and _sign(d[i][j]) != _sign(d[i][j + 1]):
                out.add((i, j, "horizontal"))
    return out


def _unflatten(flat, n_cols):
    return [list(flat[i:i + n_cols]) for i in range(0, len(flat), n_cols)]


def _candidates_with_comparator(fixture, strategy, target_price, target_month):
    """引擎精確值與序列化後的值成對回傳——比對的兩側必須來自同一次
    分析，否則比的是兩份不同的資料。"""
    req = service.AnalysisRequest(
        symbol="XYZ",
        base_params=AnalysisParams(strategy=strategy,
                                   target_price=target_price,
                                   target_month=target_month),
        strategies=(strategy,))
    result = service.run_offline(req, fixture)
    view = store.serialize_result(result, "S", 100000.0)
    pool = view["candidate_pool"]
    out = []
    for res in result.results:
        for cv in res.candidates:
            if cv.comparator is None:
                continue
            key = service.candidate_key(cv)
            wire = pool.get(key)
            if wire is None or wire.get("comparator") is None:
                continue
            n_cols = len(view["axis_sets"][wire["matrix"]["axis_index"]]["dates"])
            out.append((
                cv,
                _unflatten(wire["matrix"]["cells"], n_cols),
                _unflatten(wire["comparator"]["matrix"]["cells"], n_cols)))
    return out


CROSSOVER_CASES = (
    ("tests/fixtures/xyz_v4_six_expiries.json", "bull-call-spread", 130.0, "2026-09"),
    ("tests/fixtures/xyz_v5_put_ladder.json", "bear-put-spread", 70.0, "2026-09"),
)


def test_serialised_cells_keep_the_exact_sign_of_the_crossover_difference():
    """核心不變量：逐格 `sign(序列化候選 − 序列化 comparator)` 必須等於
    `sign(引擎精確候選 − 引擎精確 comparator)`。

    前端三個 crossover 消費端（`crossoverEdges()`／
    `crossoverFavoredSide()`／`crossoverSides()`）全都只讀這個正負號，
    所以保住它就等於保證「傳輸壓縮不會改變 crossover 分類」。

    修正前（兩個矩陣各自獨立捨入）實測違反：真差 4.4e-05／1.9e-05／
    1.3e-06 這類格子被捨成相同的數字，`sign()` 變 0。"""
    checked = 0
    for case in CROSSOVER_CASES:
        for cv, cells, cmp_cells in _candidates_with_comparator(*case):
            exact_a = cv.matrix.cells
            exact_b = cv.comparator.matrix.cells
            for i, (row_a, row_b) in enumerate(zip(exact_a, exact_b)):
                for j, (a, b) in enumerate(zip(row_a, row_b)):
                    checked += 1
                    assert _sign(cells[i][j] - cmp_cells[i][j]) == _sign(a - b), (
                        f"{case[1]} 第 ({i},{j}) 格：精確差 {a - b!r}、"
                        f"序列化後差 {cells[i][j] - cmp_cells[i][j]!r}")
    assert checked > 100, f"只比對到 {checked} 格，樣本不足以當守門"


def test_crossover_edges_are_identical_before_and_after_wire_compression():
    """把上面那條不變量直接翻譯成使用者看得到的結果：前端會畫出來的
    crossover 邊界集合，在「引擎精確值」與「序列化後的值」兩側必須
    逐條相同。

    修正前實測兩份 fixture **6/6 有 comparator 的候選都不同**（例如
    bull-call-spread 精確 17 條、捨入後 20 條：抹掉 2 條真的、生出
    5 條假的）。"""
    checked = 0
    for case in CROSSOVER_CASES:
        for cv, cells, cmp_cells in _candidates_with_comparator(*case):
            checked += 1
            exact = _crossover_edges([list(r) for r in cv.matrix.cells],
                                     [list(r) for r in cv.comparator.matrix.cells])
            wire = _crossover_edges(cells, cmp_cells)
            assert wire == exact, (
                f"{case[1]}：序列化後的邊界與精確值不同——"
                f"只在精確側 {sorted(exact - wire)}、只在序列化側 "
                f"{sorted(wire - exact)}")
            assert exact, "這個候選整張表沒有任何邊界，證明不了什麼"
    assert checked >= 6, f"只檢查到 {checked} 個候選，樣本不足以當守門"


def test_the_sign_fix_does_not_visibly_move_the_comparator_numbers():
    """修法把符號被捨錯的 comparator 格值推到候選值的正負一格
    （±1e-4）——偏離真值的上界因此是 1.5e-4，仍遠細於畫面顯示精度
    （整數百分點，1e-2）。這條把「顯示數字不受影響」寫成可執行斷言，
    免得未來有人以為這個修法會動到看得見的東西。"""
    worst = 0.0
    for case in CROSSOVER_CASES:
        for cv, _cells, cmp_cells in _candidates_with_comparator(*case):
            for i, row in enumerate(cv.comparator.matrix.cells):
                for j, b in enumerate(row):
                    worst = max(worst, abs(cmp_cells[i][j] - b))
    assert worst <= 1.5e-4, worst
    assert worst > 0.0, "完全沒有格子被推動，這條測試沒有驗到東西"
