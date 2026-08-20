"""Spread IV Gap：買／賣兩腿 exact-contract reconstructed IV 序列對齊成
一條 Spread 專屬序列，外加帶 guardrail 的 4 週變化比例（SIG-01／#172，
spec #171）。

跟 `ivreconstruct.py`／`ivtrend.py` 同層、同一套紀律：純函式、零 I/O、
零全域狀態。物理上不 import `ivhistory.py`——spec #151 §0／§7 隔離紅線
延伸到這個新模組（跟 `ivtrend.py`／`ivreconstruct.py` 同理，見兩者各自
的模組說明）。

對齊完的 Gap 序列形狀跟 `ivtrend.py` 既有統計函式吃的輸入相容
（`list[tuple[str, float]]`——這裡永遠非 null，是 `list[tuple[str,
float | None]]` 的子集），因此 `trim_to_window`／`moving_average`／
`bollinger_bands`／`historical_percentile`／`delta_4w`／
`history_span_days` 直接對 Gap 序列呼叫，零修改（spec #171 決策）。
"""
from __future__ import annotations

# 0.5 個 vol point——不叫 IV_GAP_PERCENT_MIN_BASE：這個常數只守
# delta_4w_ratio 的 baseline 除數，不是百分比欄位（見下方
# spread_delta_4w_ratio_status 的欄位定義）。判斷值本身是保守取值，非
# 精算，日後可調整、不影響架構（跟 ivreconstruct.py 的
# VENDOR_IV_BENCHMARK_MIN 同一種先例）。
IV_GAP_RATIO_MIN_BASE = 0.005

STATUS_OK = "ok"
STATUS_NO_BASELINE = "no_baseline"
STATUS_NEAR_ZERO_BASE = "near_zero_base"
STATUS_SIGN_FLIP = "sign_flip"


def align_spread_gap(buy_points: list[tuple[str, float | None]],
                     sell_points: list[tuple[str, float | None]],
                     ) -> list[tuple[str, float]]:
    """買／賣兩腿各自的原始（裁窗前）reconstructed `(date, iv|None)`
    序列 → 一條 Spread IV Gap 序列。

    只保留兩條輸入序列在同一天都有非 `None` iv 的日期，`gap = 賣腿 iv
    − 買腿 iv`；任一天只有一腿有值、或兩腿都沒有值，該天完全不進輸出
    （不是一筆 `gap: None` 的 observation——輸出的 gap 永遠是
    `float`，絕不是 `None`）。輸出依 date 嚴格遞增排序，不管輸入兩條
    序列本身有沒有排序。

    兩條輸入序列各自不得有重複日期——這個前提由既有上游不變量保證
    （`_ensure_contract_history()` 的 `{date: quote}` dict 合併）。若這個
    前提被違反（上游出現真正的 bug），這裡 fail-fast 直接拋錯，不用
    dict 覆寫語意悄悄留下其中一筆、掩蓋上游的錯誤。
    """
    buy_map = _to_date_map(buy_points, side="buy")
    sell_map = _to_date_map(sell_points, side="sell")

    common_dates = sorted(set(buy_map) & set(sell_map))
    return [(d, sell_map[d] - buy_map[d]) for d in common_dates]


def _to_date_map(points: list[tuple[str, float | None]], *,
                 side: str) -> dict[str, float]:
    seen: set[str] = set()
    out: dict[str, float] = {}
    for d, iv in points:
        if d in seen:
            raise AssertionError(
                f"{side} 腿的 reconstructed 序列出現重複日期：{d}"
                "——上游 _ensure_contract_history() 的不變量被違反")
        seen.add(d)
        if iv is not None:
            out[d] = iv
    return out


def spread_delta_4w_ratio_status(current_gap: float | None,
                                 delta_4w: float | None,
                                 ) -> tuple[float | None, str]:
    """`delta_4w`（既有 `ivtrend.delta_4w()` 對 Gap 序列的既有回傳值，
    絕對值、vol-point 單位）＋`current_gap`（`points[-1]` 的 gap）代數
    反推 `baseline_gap = current_gap − delta_4w`，回傳
    `(ratio, status)` 一對值：

    - `delta_4w` 為 `None` → `(None, "no_baseline")`
    - `abs(baseline_gap) < IV_GAP_RATIO_MIN_BASE`（嚴格 `<`，恰好等於
      門檻不算近零）→ `(None, "near_zero_base")`
    - 上一條沒觸發，且 `baseline_gap` 與 `current_gap` 正負號不同
      （`current_gap` 恰好是 0、`baseline_gap` 不近零時，兩者正負號
      天然不同，無需另外特判）→ `(None, "sign_flip")`
    - 兩道 guardrail 都沒觸發 → `("ok", delta_4w / abs(baseline_gap))`
      ——不乘 100，比照 `current_percentile` 的 0–1 尺度慣例。
    """
    if delta_4w is None:
        return None, STATUS_NO_BASELINE

    baseline_gap = current_gap - delta_4w
    if abs(baseline_gap) < IV_GAP_RATIO_MIN_BASE:
        return None, STATUS_NEAR_ZERO_BASE

    if _sign(current_gap) != _sign(baseline_gap):
        return None, STATUS_SIGN_FLIP

    return delta_4w / abs(baseline_gap), STATUS_OK


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0
