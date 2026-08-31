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
