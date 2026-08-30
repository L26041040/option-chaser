# option_chaser/report.py
"""Deterministic plain-text report (spec §7). No box-drawing characters."""
from __future__ import annotations

from datetime import date, timedelta
from datetime import date as _date

from .filters import FILTER_CLASS_LABELS, is_spread_wide
from .matrix import date_axis, matrix_lines, price_axis
from .models import (AnalysisParams, ChainSnapshot, FilterReport, QualityFlagCount,
                     is_bullish, leg_option_type)
from .ranking import BAND_LABELS, BAND_ORDER, build_reasons
from .valuation import ContractValuation, guidance_judgments, scenario_leg_value, spread_scenario_value

STRATEGY_LABELS = {
    "long-call": "Long Call",
    "long-put": "Long Put",
    "bull-call-spread": "Bull Call Spread",
    "bear-put-spread": "Bear Put Spread",
}


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _shift_name(shift: float) -> str:
    return "IV 不變" if shift == 0.0 else f"IV {shift * 100:+g}%"


def _spread_width_warning(prefix: str, bid: float, ask: float, p: AnalysisParams) -> str | None:
    """FB5-02（#63）：買賣價差過寬只標示、不刪除候選；訊息本身要說得出
    「寬到什麼程度」（票上明列的驗收標準），不能只給一個沒有量級的警告。
    `prefix` 供價差策略區分是買腿還是賣腿，單腿傳空字串。"""
    if not is_spread_wide(bid, ask, p):
        return None
    mid = (bid + ask) / 2.0
    return (f"- 警示: {prefix}買賣價差偏大（達 Mid 的 {_pct((ask - bid) / mid)}，"
            f"Bid ${_money(bid)} / Ask ${_money(ask)}）")


def _monotonicity_warning_line(prefix: str, contract_symbol: str,
                               violations: frozenset[str]) -> str | None:
    """FB5-03（#64）：無套利一致性違反只標示、不刪除候選；比照 FB5-02
    的 `_spread_width_warning` 同一種寫法——`violations` 是呼叫端算好的
    集合（`filters.monotonicity_violations()`），這裡只查表。`prefix`
    同上，區分買腿／賣腿，單腿傳空字串。"""
    if contract_symbol not in violations:
        return None
    return f"- 警示: {prefix}報價與鄰近履約價不一致，疑似陳舊報價"


def _val_line(name: str, val: float, cost: float) -> str:
    """spec §7: each scenario line = 估值 + 損益 + 報酬率 (per-share and per-contract)."""
    pnl = val - cost
    return (
        f"- {name}: ${_money(val)}（${val * 100:.0f}/張）"
        f"損益 {pnl:+.2f}（{pnl * 100:+.0f}/張）-> {_pct(pnl / cost)}"
    )


def _carry_suffix(p: AnalysisParams) -> str:
    """#113／#123（spec #117 §1／§2）：估值模型描述，接在 `_rate_line()`
    每個分支後面。**只描述這次分析的 `AnalysisParams.q_by_symbol` 是否
    有值**——不代表每一條腿實際都校準成功（逐候選可能不同，見
    `CandidateView.carry_calibrated`）。

    #123：q 管線未接（`q_by_symbol is None`）恆印今天的舊文字，行為不變
    ——涵蓋離線重放與 fallback 第 4 層（抓取失敗且無可用快取）兩種情況，
    兩者對使用者是同一句話（「未取得配息資料」不需要跟「離線模式」分開
    講）。有值時三態揭露（`q_source`／`q_as_of`／`q_stale`）比照
    `_rate_line()` 的曲線三態同一種寫法。
    """
    if p.q_by_symbol is None:
        return "無股利調整、Black-Scholes 歐式近似"
    source = f"，來源 {p.q_source}" if p.q_source else ""
    as_of = f"，資料截至 {p.q_as_of}" if p.q_as_of else ""
    stale = "，STALE（沿用陳舊備援窗）" if p.q_stale else ""
    return (f"股利殖利率調整 q={_pct(p.q_by_symbol)}{source}{as_of}{stale}"
           "（同快照、同模型逐腿反解 IV）、Bjerksund-Stensland (1993) 美式"
           "近似——個別候選若該腿反解失敗，會退回無股利調整的 "
           "Black-Scholes 歐式近似（見各候選是否標記「未經 carry 校準」）")


def _rate_line(p: AnalysisParams) -> str:
    """RC1（#87，附錄 A14.1 修正）三態：

    - 期限對齊曲線（`rate_curve_used`，新鮮或陳舊備援皆標明 curve date，
      陳舊額外標 STALE）——與 `rate_by_expiry` 是否非空脫鉤，鏈上零合約
      時曲線仍算「用了」，只是沒有逐到期日的表可印。
    - 明示（`--rate`，`rate_explicit`）：維持現行乾淨寫法，不貼 FALLBACK
      標籤——那是使用者主動選擇，不是「本該有曲線卻失敗」。
    - 其餘所有常數情況（曲線徹底不可得、或離線重放這個模式本身沒有
      啟用管線）：明確標「FALLBACK」＋原因（`rate_note`），不冒充曲線
      日期——離線重放不是「乾淨」的第三態，它跟曲線失敗一樣是「這次
      用的是常數，不是曲線」，理由不同但呈現方式相同。
    """
    carry = _carry_suffix(p)
    if p.rate_curve_used:
        rates = "、".join(f"{e} {r * 100:.2f}%" for e, r in p.rate_by_expiry)
        detail = f"；各到期日 r: {rates}" if rates else ""
        stale = "，STALE（沿用陳舊備援窗）" if p.rate_curve_stale else ""
        return (f"- 無風險利率 期限對齊（Treasury 曲線 {p.rate_curve_date}"
                f"{stale}{detail}）、{carry}")
    if p.rate_explicit or not p.rate_note:
        return f"- 無風險利率 {_pct(p.rate)}、{carry}"
    return f"- 無風險利率 {_pct(p.rate)} · FALLBACK（{p.rate_note}）、{carry}"


def _header_lines(snap: ChainSnapshot, p: AnalysisParams, today: date) -> list[str]:
    bands = p.delta_bands
    return [
        "OPTION CHASER 報告",
        "",
        "[使用者假設]",
        f"- 策略: {STRATEGY_LABELS[p.strategy]}",
        f"- 劇本: {p.target_month} 到達 ${_money(p.target_price)}",
        f"- 到期日選取: 日曆錨點 {p.anchor.isoformat()} 前後至多五檔實際到期日",
        f"- 最低要求報酬率: {_pct(p.min_return)}",
        "",
        "[市場資料]",
        f"- 資料時間: {snap.fetched_at}（來源 {snap.source}，可能延遲）",
        f"- {snap.symbol} 現價: ${_money(snap.spot)}（分析基準日 {today.isoformat()}）",
        "",
        "[模型假設]",
        _rate_line(p),
        f"- IV 情境: {', '.join(_shift_name(s) for s in p.iv_shifts)}",
        f"- Delta 分級門檻: {bands[0]:g} / {bands[1]:g}（實務慣例級距）",
    ]


def _filter_lines(
    freport: FilterReport, p: AnalysisParams,
    quality_flags: tuple[QualityFlagCount, ...] = (),
) -> list[str]:
    """FB5-04（#65，spec #61）：每一關都標出屬於哪一類——「排除」（A／B類，
    算不出來）跟「標示」（C類，算得出來但不夠好看）在畫面上分得開，讓這一
    區自己說得出兩者的差別，不必回頭查程式碼或尾註。"""
    side = "Call 側" if leg_option_type(p.strategy) == "call" else "Put 側"
    lines = ["", "[過濾統計]", f"- 掃描合約（{side}）: {freport.total} 張"]
    for s in freport.stages:
        lines.append(f"- [{s.filter_class}類排除] {s.label}刷掉: {s.removed}")
    lines.append(f"- 合格: {freport.passed} 張")
    if quality_flags:
        lines.append(f"- [C類標示，不影響入選，計於上方{freport.passed}張合格內]:")
        for qf in quality_flags:
            lines.append(f"  - {qf.label}: {qf.count}")
    return lines


def _resilience_lines(val, spot: float, today: date, p: AnalysisParams,
                      resilience_cache: dict | None = None) -> list[str]:
    """v4 spec §5: 7-scenario resilience section (report layer calls scenarios.py
    directly, same primitives as service — numbers stay identical).

    T09（#191）：`resilience_cache` 讓這裡與 View 路徑（`service._v4_fields`）
    共用同一次 `scenario_vector`／`completion_curve`／`completion_scan`
    計算結果（`scenarios.resilience_metrics()`，鍵是 `id(val)`）——不傳
    （`None`，預設）時每次都重算，行為與這個參數存在之前完全一樣。"""
    from .scenarios import SCENARIO_NAMES, resilience_metrics
    from .valuation import SpreadValuation
    rm = resilience_metrics(val, spot, today, p, cache=resilience_cache)
    sv, curve, k, be = rm.scenario, rm.curve, rm.threshold, rm.breakeven
    expiry = date.fromisoformat(
        val.long_leg.expiry if isinstance(val, SpreadValuation) else val.contract.expiry
    )
    tgt = p.anchor                            # 附錄 A9 錨點：估值參考日
    delay_delta = {"S4": 30, "S5": 90}
    lines = ["", "韌性向量（7 情境，Mid 口徑）:"]
    for code, ret in sv.entries:
        note = ""
        if code in delay_delta and expiry < tgt + timedelta(days=delay_delta[code]):
            note = "（合約先到期，內插價 payoff）"
        mark = "   ◀ 情境最壞" if code == sv.worst_code else ""
        lines.append(f"- {code} {SCENARIO_NAMES[code]}: {_pct(ret)}{note}{mark}")
    lines.append("劇本完成度: " + " | ".join(
        f"{int(k * 100)}%→{_pct(r)}" for k, r in curve))
    if k is None:
        thr = "— ⚠劇本全成仍不保本"
    elif k <= 0:
        thr = "0%（已保本）"
    else:
        thr = f"完成 {_pct(k)}（錨點日保本價 ${_money(be)}，基準IV）"
    retention = 1.0 + dict(sv.entries)["S1"]
    # T04（#220，#217 決策 D）：friction／Bid-Ask Spread 這一項已自
    # canonical model 退場，這一行不再印它——保本門檻／不漲保留率兩項
    # 維持不變。
    lines.append(f"保本門檻: {thr} | 不漲保留率: {_pct(retention)}")
    return lines


def _candidate_lines(
    v: ContractValuation, idx: int, band: str,
    ranked: dict[str, list[ContractValuation]],
    snap: ChainSnapshot, n_qualified: int, p: AnalysisParams, today: date,
    violations: frozenset[str] = frozenset(),
    resilience_cache: dict | None = None,
) -> list[str]:
    c = v.contract
    word = "高於" if c.option_type == "call" else "低於"
    lines = [
        "",
        f"{idx}) {BAND_LABELS[band]}: Strike ${_money(c.strike)} / {c.expiry} 到期",
        f"- 現在買入: Bid ${_money(c.bid)}（${c.bid * 100:.0f}/張）"
        f" / Mid ${_money(v.mid)}（${v.mid * 100:.0f}/張）"
        f" / Ask ${_money(c.ask)}（${c.ask * 100:.0f}/張）IV {_pct_iv(c.implied_volatility)}",
        f"- Delta {v.delta:.2f} / Theta {v.theta_per_day:.3f}每天 / Vega {v.vega_per_pct:.2f}",
        f"- Breakeven: ${_money(v.breakeven)}（{word}現價 {_pct(v.breakeven_vs_spot)}；"
        f"對目標價緩衝 {_pct(v.breakeven_vs_target)}）",
        f"- Lambda 有效槓桿: {v.effective_leverage:.1f}x",
    ]
    if c.volume == 0:
        lines.append("- 警示: 今日無成交，報價新鮮度存疑")
    width_warning = _spread_width_warning("", c.bid, c.ask, p)
    if width_warning:
        lines.append(width_warning)
    mono_warning = _monotonicity_warning_line("", c.contract_symbol, violations)
    if mono_warning:
        lines.append(mono_warning)
    lines.append("")
    # T12（附錄 A14.2）：主數字成本口徑＝Ask（保守成交假設）。原「Natural
    # 成交報酬」與基準情境列因此重合，已合併，不再另列。
    lines.append("劇本成立時（Ask 進場）:")
    lines.append(_val_line("保守底線", v.floor_value, c.ask))
    for shift, val in v.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, c.ask))
    lines.append("")
    lines.append("買價指引:")
    lines.append(f"- L1 硬上限（劇本內在價值）: ${_money(v.l1)}（${v.l1 * 100:.0f}/張）")
    lines.append(f"- L2 保守上限（最保守 IV 情境）: ${_money(v.l2)}（${v.l2 * 100:.0f}/張）")
    lines.append(
        f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: "
        f"${_money(v.l3)}（${v.l3 * 100:.0f}/張）"
    )
    judgments = guidance_judgments(v, p)
    if judgments:
        for m in judgments:
            lines.append(f"- 警示: {m}")
    else:
        lines.append("- 目前 Ask 低於全部三層天花板")
    lines += _resilience_lines(v, snap.spot, today, p, resilience_cache)
    pros, cons = build_reasons(v, band, ranked, snap.spot, n_qualified, p)
    lines.append("")
    lines.append("評語:")
    for s in pros:
        lines.append(f"- 優點: {s}")
    for s in cons:
        lines.append(f"- 代價: {s}")
    return lines


def _pct_iv(iv: float) -> str:
    return f"{iv * 100:.0f}%"


def _matrix_block(value_fn, cost, spot, p, today, expiry) -> list[str]:
    prices = price_axis(spot, p.target_price, is_bullish(p.strategy),
                        best_price=p.best_price, worst_price=p.worst_price)
    dates = date_axis(today, expiry)
    return (["", "P/L 矩陣（報酬率，最差進場）:"]
            + matrix_lines(value_fn, cost, prices, dates))


# V8（#56，spec R1 §4.2 A2）：CLI 純文字報告用的精簡免責句——維持原文，
# 不因為新增網頁版擴充免責（見 `disclaimer_text()`）而改動既有 CLI 輸出。
_DISCLAIMER_LINE = "- 免責: 模型估計非保證價格，不構成投資建議"


def _model_limitation_line(p: AnalysisParams) -> str:
    """#113（spec #117 §10-6／honest disclosure）：模型限制尾註。

    `q_by_symbol is None`（q 管線未接、離線重放、或 fallback 第 4 層：
    抓取失敗且無可用快取，#123）維持既有措辭逐字不變。有 q 時**只能
    宣稱**「carry 從完全沒有變成量級正確」——
    **不得**宣稱 Heatmap 已經準了：用一個連續 q 描述固定美元配息，本身
    在網格邊緣就帶有模型誤差（研究文件 §7.7），且逐候選是否真的校準
    成功還要看 `carry_calibrated`。
    """
    if p.q_by_symbol is None:
        return "- 模型限制: 無股利調整（q=0）、歐式近似、IV 乘法情境"
    return ("- 模型限制: 股利殖利率 carry 從完全沒有變成量級正確（同快照"
           "校準），但不代表 Heatmap 數字已經準確——連續 q 描述固定美元"
           "配息本身在網格邊緣仍有模型誤差；反解失敗的腿退回無股利調整"
           "的歐式近似；IV 乘法情境")


def methodology_lines(p: AnalysisParams) -> list[str]:
    """V8（#56，spec R1 §4.2 A2）：方法論尾註——`_footer_lines()` 扣掉免責
    那一行的其餘全部，供 API 序列化成獨立的「方法與假設」欄位（新版型
    ⑥，`docs/research/option-strategy-report-conventions.md` §4.1）。
    CLI 的 `render()`／`render_spreads()` 仍呼叫 `_footer_lines()`（本函式
    ＋免責合併），文字內容完全不變，只是免責從中段移到尾端——R1 §2.1
    「免責與方法在最後」，兩者本來就該相鄰墊底，不該讓免責卡在方法論
    中間打斷整段。"""
    return [
        "",
        "[尾註]",
        "- 估值: Black-Scholes 歐式 call，N(x) = 0.5*(1+erf(x/sqrt(2)))，T = 日曆日/365",
        "- Put: P = K·e^(-rT)·N(-d2) - S·N(-d1)；估值鉗制 value = max(BS, 內在價值, 0)",
        "- T <= 0 時以內在價值 max(S-K, 0) 取代 BS",
        "- 保守底線 = max(目標價 - Strike, 0)（無套利下限）",
        "- IV 情境: sigma' = sigma * (1 + shift)",
        "- 買價天花板: L1 = max(目標價-Strike, 0); L2 = BS(最保守 IV 情境); L3 = 基準估值/(1+min-return)",
        "- 價差: V = 長腿 − 短腿，鉗制至 [0, 寬度]；價差無 L1，L2 = 全部 IV 情境最小值（情境包絡，非無套利下限）",
        "- 成本口徑: 主數字（排名、矩陣、Breakeven、佔本金）＝最差成交假設"
        "（單腿=Ask；價差=買 Ask − 賣 Bid），定位保守成交假設收益；實際成交"
        "可能更好或更差，非理論下限。Mid 僅供參考",
        "- Breakeven = Strike ± 最差成本（到期持有觀點，提前平倉不適用）",
        "- Lambda = Delta * 現價 / 最差成本（低權利金合約會放大，僅供量級參考）",
        "- 矩陣: 11 價格 × ≤7 日期；IV 按快照值恆定；末欄為到期 payoff；估值含美式內在價值鉗制",
        "- 到期日選取: 目標月第三個星期五為日曆錨點，取距錨點最近的實際到期日為"
        "baseline（同距取較晚），再取其前 2 後 2（一側不足由另一側補足），至多五檔；"
        "窮舉僅及於這些到期日",
        # FB5-04（#65，spec #61）：三分類人話說明——A／B 兩類是「算不出來」
        # 硬門檻，C 類是「算得出來但不夠好看」的標示，兩者行為不同、待遇
        # 不同，尾註得說清楚是哪一種，不能含混成同一句「過濾」。
        f"- 過濾 [A類 {FILTER_CLASS_LABELS['A']}，硬門檻]: 報價存在且不交叉"
        "（不含任何到期日條件，到期日取捨見下）",
        f"- 過濾 [B類 {FILTER_CLASS_LABELS['B']}，硬門檻]: IV 落在可解區間 (0.01-5.0)",
        # 檢視回饋修正：未平倉量沒有門檻可標示（見 `quality_flag_counts`
        # docstring），原樣顯示於各候選腿，不在 [過濾統計] 逐項計數——
        # 不能跟真的有計數的另外三項寫在同一句，讓讀者以為四項都有數字。
        f"- 過濾 [C類 {FILTER_CLASS_LABELS['C']}，只標不刪，spec #61]: 未平倉量"
        "原樣顯示於各候選腿，不設門檻；成交量、買賣價差寬度、無套利一致性"
        "——不影響候選是否入選，[過濾統計]區逐項計數；買賣價差"
        f"超過 max({p.spread_floor:g}, {p.max_spread_pct:g}*Mid) 時逐候選附警示，"
        "見各候選「買賣價差偏大」",
        "- 無套利一致性: 同到期日、同類型的相鄰履約價 Ask 應單調（call 非"
        "遞增、put 非遞減），違反時僅標示、不影響候選是否入選，spec #61；"
        "見各候選「報價與鄰近履約價不一致，疑似陳舊報價」",
        "- 排名: Delta 分級（實務慣例），級內以基準情境報酬率（最差進場）排序",
        _model_limitation_line(p),
        "- 韌性向量 7 情境: S1 不漲(S=現價) / S2 半程(完成度50%價位) / S3 大半程"
        "(完成度75%價位) / S4 晚30天到達 / S5 晚90天到達 / S6 IV最保守"
        "(全部 IV 情境估值之最小值) / S7 Natural成交(成本改採 Ask，價差為長Ask−短Bid)"
        "；除 S4/S5 外估值日皆為日曆錨點、基準 IV",
        "- 延遲情境（S4/S5）路徑假設: 到達日 = 日曆錨點 + 30 或 90 天；估值日價格採"
        "現價與目標價之線性內插 S(d) = 現價 + (目標價−現價)×(d−今日)/(到達日−今日)；"
        "合約先到期時以到期日內插價計算 payoff（模型假設，非市場預測）",
        "- 保本門檻掃描定義（後綴條件）: 沿劇本路徑網格 k∈[-0.20,1.00]（步長0.001）"
        "由 k=1.0 反向掃描；k* 為使『對所有 j∈[k*,1.0] 估值皆不低於 Mid 成本』成立的"
        "最小 k；非單調曲線亦適用，避免『先達標後回落』的假保本門檻",
        "- 情境最壞＝7 個固定情境的最低值，屬透明情境集合的最壞值，非統計推論、"
        "亦非所有可能情況的最壞",
    ]


def _footer_lines(p: AnalysisParams) -> list[str]:
    return methodology_lines(p) + [_DISCLAIMER_LINE]


def disclaimer_text() -> str:
    """V8（#56，spec R1 §4.4.4）：網頁新版型獨立、不折疊的免責段落，
    涵蓋 R1 明列的四點（模型估計非保證價格／不構成投資建議／本工具非
    經紀商亦非投資顧問／選擇權風險請參閱 OCC ODD），且措辭不聲稱本產品
    受 FINRA 或任何監理規範管轄（R1 §2.5 前言、§4.4 第 4 點）。不依賴
    任何參數——固定文案，不是引擎計算值，但集中放在 report.py 維持
    「報告文案單一來源」，CLI 的精簡版（`_DISCLAIMER_LINE`）維持不變、
    不被本函式取代。"""
    return (
        "模型估計非保證價格，不構成投資建議。本工具並非經紀商，亦非"
        "投資顧問，不提供個人化投資建議，本工具與任何監理機構之揭露"
        "規範皆無關。選擇權交易涉及重大風險，可能損失全部投入本金，"
        "交易前請參閱 OCC《Characteristics and Risks of Standardized "
        "Options》（選擇權風險揭露文件）。"
    )


def render_filter_only(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport, today: date
) -> str:
    lines = _header_lines(snap, p, today) + _filter_lines(freport, p)
    lines += ["", "過濾後無合格合約，不產生推薦。", ""]
    return "\n".join(lines)


def render(
    snap: ChainSnapshot, p: AnalysisParams, freport: FilterReport,
    ranked: dict[str, list[ContractValuation]], n_qualified: int, today: date,
    violations: frozenset[str] = frozenset(),
    quality_flags: tuple[QualityFlagCount, ...] = (),
    resilience_cache: dict | None = None,
) -> str:
    """`resilience_cache`：T09（#191）——與 View 路徑共用韌性／完成度
    計算的快取字典，見 `_resilience_lines()` 說明；不傳（`None`）不影響
    既有行為，本函式既有呼叫端（含測試）不需要改動。"""
    lines = _header_lines(snap, p, today) + _filter_lines(freport, p, quality_flags)
    idx = 0
    for band in BAND_ORDER:
        lines.append("")
        lines.append(f"=== {BAND_LABELS[band]}（{_band_range(band, p)}） ===")
        if not ranked[band]:
            lines.append("- 此級距無合格合約")
            continue
        for j, v in enumerate(ranked[band]):
            idx += 1
            lines += _candidate_lines(v, idx, band, ranked, snap, n_qualified, p,
                                      today, violations, resilience_cache)
            if j == 0 or p.matrix_all:
                c = v.contract
                lines += _matrix_block(
                    lambda S, d, c=c, carry=v.carry:
                        scenario_leg_value(c, S, d, p, carry=carry),
                    c.ask, snap.spot, p, today, _date.fromisoformat(c.expiry),
                )
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)


def _band_range(band: str, p: AnalysisParams) -> str:
    a, b = p.delta_bands
    if band == "conservative":
        return f"Delta > {b:g}"
    if band == "aggressive":
        return f"Delta < {a:g}"
    return f"Delta {a:g}-{b:g}"


def _pair_lines(pr) -> list[str]:
    return ["", "[配對統計]", f"- 配對總數: {pr.total_pairs}",
            f"- 健全性淘汰: {pr.removed_sanity}", f"- 合格組數: {pr.passed}"]


def _spread_candidate_lines(sv, idx, n_pairs, p, spot: float, today: date,
                            violations: frozenset[str] = frozenset(),
                            resilience_cache: dict | None = None) -> list[str]:
    from .ranking import build_spread_reasons
    from .valuation import spread_guidance_judgments
    ll, sl = sv.long_leg, sv.short_leg
    lines = [
        "",
        f"{idx + 1}) 買 K={_money(ll.strike)} / 賣 K={_money(sl.strike)} / {ll.expiry} 到期（寬度 ${_money(sv.width)}）",
        f"- 買腿 {ll.contract_symbol}: Bid ${_money(ll.bid)} / Ask ${_money(ll.ask)} IV {_pct_iv(ll.implied_volatility)}",
        f"- 賣腿 {sl.contract_symbol}: Bid ${_money(sl.bid)} / Ask ${_money(sl.ask)} IV {_pct_iv(sl.implied_volatility)}",
        f"- 淨成本: Mid ${_money(sv.net_mid)}（${sv.net_mid * 100:.0f}/張） / 最差 ${_money(sv.net_worst)}（${sv.net_worst * 100:.0f}/張）",
        f"- 最大獲利: ${_money(sv.max_profit)}（${sv.max_profit * 100:.0f}/張） / 淨Delta {sv.net_delta:.2f} / Lambda {sv.effective_leverage:.1f}x",
        f"- Breakeven: ${_money(sv.breakeven)}（對目標價緩衝 {_pct(sv.breakeven_vs_target)}）",
    ]
    for prefix, leg in (("買腿", ll), ("賣腿", sl)):
        warning = _spread_width_warning(prefix, leg.bid, leg.ask, p)
        if warning:
            lines.append(warning)
        mono_warning = _monotonicity_warning_line(prefix, leg.contract_symbol, violations)
        if mono_warning:
            lines.append(mono_warning)
    lines += [
        "",
        "劇本成立時（最差進場）:",
    ]
    for shift, val in sv.scenario_values:
        lines.append(_val_line(_shift_name(shift), val, sv.net_worst))
    lines.append(_val_line("IV 情境最低值", sv.l2, sv.net_worst))
    lines += ["", "買價指引:",
              f"- L2 保守上限（IV 情境最低值）: ${_money(sv.l2)}（${sv.l2 * 100:.0f}/張）",
              f"- L3 要求報酬上限（min-return {_pct(p.min_return)}）: ${_money(sv.l3)}（${sv.l3 * 100:.0f}/張）"]
    judgments = spread_guidance_judgments(sv, p)
    if judgments:
        lines += [f"- 警示: {m}" for m in judgments]
    else:
        lines.append("- 目前最差進場成本低於全部天花板")
    lines += _resilience_lines(sv, spot, today, p, resilience_cache)
    pros, cons = build_spread_reasons(sv, idx, n_pairs, p)
    lines += ["", "評語:"] + [f"- 優點: {s}" for s in pros] + [f"- 代價: {s}" for s in cons]
    return lines


def render_spreads(snap, p, freport, pair_report, ranked, n_pairs, today,
                   violations: frozenset[str] = frozenset(),
                   quality_flags: tuple[QualityFlagCount, ...] = (),
                   resilience_cache: dict | None = None) -> str:
    """`resilience_cache`：T09（#191）——與 View 路徑共用韌性／完成度
    計算的快取字典，見 `_resilience_lines()` 說明；不傳（`None`）不影響
    既有行為，本函式既有呼叫端（含測試）不需要改動。"""
    lines = (_header_lines(snap, p, today) + _filter_lines(freport, p, quality_flags)
            + _pair_lines(pair_report))
    if not ranked:
        lines += ["", "無合格價差組合，不產生推薦。", ""]
        return "\n".join(lines)
    for i, sv in enumerate(ranked):
        lines += _spread_candidate_lines(sv, i, n_pairs, p, snap.spot, today,
                                         violations, resilience_cache)
        if i == 0 or p.matrix_all:
            lng, sht = sv.long_leg, sv.short_leg
            lc, sc = sv.long_carry, sv.short_carry
            lines += _matrix_block(
                lambda S, d, lng=lng, sht=sht, lc=lc, sc=sc:
                    spread_scenario_value(lng, sht, S, d, p, long_carry=lc, short_carry=sc),
                sv.net_worst, snap.spot, p, today, _date.fromisoformat(lng.expiry),
            )
    lines += _footer_lines(p)
    lines.append("")
    return "\n".join(lines)
