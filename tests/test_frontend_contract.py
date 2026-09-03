"""前後端共用字彙的漂移防線。

契約樣本（`contracts/*.json`）管得住 view dict 的**欄位**，管不到那些
「後端會送出、前端必須認得」的**字串值**：失敗分層的 stage、策略代號。
這類東西不同步時不會壞掉，只會靜靜退化成通用文案——正是最難發現的那種
錯。這裡用結構性斷言把它們變成紅燈，做法沿用
`test_api_layer_never_touches_sql_directly`。

讀原始碼而不是跑前端：前端測試在 vitest（Node）那一側，Python 這邊唯一
能做的就是掃檔案。斷言刻意寬鬆（找得到就算數），只擋「整個漏掉」。
"""
import re
from pathlib import Path

from option_chaser.models import (DIRECTION_LABELS, DIRECTIONS, FAMILIES,
                                  STRATEGIES, STRATEGY_FAMILY)
from option_chaser.report import STRATEGY_LABELS


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_every_failure_stage_the_backend_emits_is_one_the_frontend_knows():
    """後端 `_fail(...)` 的分層字彙同時活在三個地方：`api_app/main.py`、
    前端 `api.ts` 的 `STAGES`、`scenarios.ts` 的 `failureLabel` switch。
    後端加第四種而前端沒跟上，畫面只會退成「刷新失敗」——使用者因此
    看不出重試有沒有意義，也就是 V4（#52）要消滅的那種無聲誤導。"""
    emitted = set(re.findall(r'_fail\("(\w+)"', _read("api_app/main.py")))
    assert emitted, "沒抓到任何 _fail(...)——這條測試的抓法過時了"

    # re.S：STAGES 被格式化成跨行時仍抓得到。抓不到就明說是這條測試的
    # 抓法過時了，而不是丟一個 AttributeError 讓人去猜。
    declared = re.search(r"const STAGES = \[(.*?)\]", _read("src/api.ts"), re.S)
    assert declared, "在 src/api.ts 找不到 STAGES 宣告——這條測試的抓法過時了"
    known = set(re.findall(r'"(\w+)"', declared.group(1)))
    labels = _read("src/scenarios.ts")

    assert emitted <= known, f"前端 api.ts 不認得這些分層：{emitted - known}"
    for stage in emitted:
        assert f'case "{stage}":' in labels, (
            f"scenarios.ts 的 failureLabel 沒有 {stage} 的說法，畫面會退成通用訊息")


def test_every_strategy_has_a_display_name_on_both_sides():
    """策略代號會原樣出現在 view dict 裡（`params.strategy`／
    `results[].strategy`），詳細頁要把它寫成人看得懂的名字。前端漏掉
    某個策略時會退回顯示原始代號——不會壞，但畫面上就多了一個
    `bull-call-spread` 這種東西。"""
    front = _read("src/detail.ts")
    for strategy in STRATEGIES:
        assert f'"{strategy}": "{STRATEGY_LABELS[strategy]}"' in front, (
            f"src/detail.ts 的 STRATEGY_LABELS 缺 {strategy}，或與後端"
            f" report.STRATEGY_LABELS 不一致（後端是 {STRATEGY_LABELS[strategy]!r}）")


def test_every_direction_has_a_display_name_on_both_sides():
    """OPTION-CHASER-CLOSEOUT-001：`option_chaser/store.py::
    serialize_result()` 新增的頂層 `direction` 欄位（`"bullish"`／
    `"bearish"`／`"flat"`）由 Scenario Detail 的「劇本設定」卡顯示
    ——`src/detail.ts::directionLabel()` 的 docstring 明講「與後端
    `DIRECTION_LABELS` 同一份字彙……漂移測試把關」，這裡就是那份
    漂移測試本身（先前只有註解宣稱，沒有真的補上，屬結構同 `test_
    every_strategy_has_a_display_name_on_both_sides` 的既有漏洞
    類型）。後端加了新方向而前端沒跟上時，畫面會退回顯示原始英文
    代號（`directionLabel()` 的 `?? direction` 備援），不會壞、但
    使用者會看到一個沒翻譯的字串。"""
    front = _read("src/detail.ts")
    for direction in DIRECTIONS:
        assert f'{direction}: "{DIRECTION_LABELS[direction]}"' in front, (
            f"src/detail.ts 的 DIRECTION_LABELS 缺 {direction}，或與後端"
            f" models.DIRECTION_LABELS 不一致（後端是 "
            f"{DIRECTION_LABELS[direction]!r}）")


def test_every_subtype_maps_to_the_same_family_on_both_sides():
    """OPTION-CHASER-CLOSEOUT-003（PR #250 merge gate review 補件）：
    `src/family.ts` 的 `SUBTYPE_FAMILY`／`FAMILIES` 是後端
    `option_chaser/models.py::STRATEGY_FAMILY`／`FAMILIES` 的手抄副本
    ——`family.ts` 檔頭自己寫著「兩邊各自一份、內容必須逐字同步。新增
    subtype 時記得同時更新這裡」，但先前只有這句註解、沒有測試。

    **這個 bug class 已經真的咬過一次**：T15（#230）純後端票新增
    `call-fly`／`put-fly`，`SUBTYPE_FAMILY` 沒跟上，Butterfly 候選被
    歸進錯誤的 family 分頁，直到 T16（#232）前端票才補上（見
    `src/family.ts` 該兩行上方的註解）。當時沒有補守門測試，這裡補上
    ——沿用 `test_every_strategy_has_a_display_name_on_both_sides`／
    `test_every_direction_has_a_display_name_on_both_sides` 同一種
    「掃前端原始碼、比對後端真相來源」手法。

    漏掉某個 subtype 時 `familyOf()` 的 `?? subtype` 備援會讓它自成
    一個假 family，分頁列會多出一個代碼當標題的分頁，不會壞但明顯
    錯誤。"""
    front = _read("src/family.ts")
    for subtype, family in STRATEGY_FAMILY.items():
        assert f'"{subtype}": "{family}"' in front, (
            f"src/family.ts 的 SUBTYPE_FAMILY 缺 {subtype}，或與後端"
            f" models.STRATEGY_FAMILY 不一致（後端是 {family!r}）")

    # `FAMILIES` 要單獨從那個陣列宣告裡抓出來比對，不能只掃全檔有沒有
    # 出現過該字串——每個 family 代碼同時也是 `SUBTYPE_FAMILY` 的
    # **值**，掃全檔會讓這半永遠成立（本測試第一版就是這樣寫的，
    # 由 merge gate 的複審實驗抓到：把 `"butterfly"` 從 `FAMILIES`
    # 陣列刪掉、`SUBTYPE_FAMILY` 留著，測試照樣綠）。
    # `familiesOf()` 依 `FAMILIES` 的順序輸出分頁，所以順序也要鎖。
    declared = re.search(r"export const FAMILIES = \[(.*?)\]", front, re.S)
    assert declared, "在 src/family.ts 找不到 FAMILIES 宣告——這條測試的抓法過時了"
    front_families = re.findall(r'"([\w-]+)"', declared.group(1))
    assert front_families == list(FAMILIES), (
        f"src/family.ts 的 FAMILIES 與後端 models.FAMILIES 不同步"
        f"（前端 {front_families}，後端 {list(FAMILIES)}）——順序也要一致，"
        f"`familiesOf()` 依它決定分頁順序")


# MVP V3（#105，spec #102 決策 G）起，韌性 7 情境表已從 Analysis Report
# UI 移除（scenario_vector 欄位與後端計算維持不動，只是不再渲染）——
# 原本鎖住 `src/detail.ts` SCENARIO_NAMES 與後端字彙同步的
# `test_every_resilience_scenario_has_a_display_name_on_both_sides`
# 因此隨著被守護的 UI 一併移除，不留一個守著不存在畫面的測試。
