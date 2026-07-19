"""Option Chaser Web GUI（Streamlit）。所有金融計算一律經 option_chaser.service。"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from option_chaser import service
from option_chaser.models import AnalysisParams, FetchError, ParamError, SPREAD_STRATEGIES
from option_chaser.report import STRATEGY_LABELS

STRATEGY_ORDER = ("long-call", "bull-call-spread", "long-put", "bear-put-spread")
DEFAULT_CHECKED = {"long-call", "bull-call-spread"}


def cell_color(ret: float) -> str:
    """0% 為中心之紅綠雙向色階；顯示範圍鉗制 ±100%；|ret|<5% 中性。純函數。"""
    if abs(ret) < 0.05:
        return "#ededed"
    t = min(abs(ret), 1.0)
    target = (34, 139, 34) if ret > 0 else (178, 34, 34)
    r = round(255 - t * (255 - target[0]))
    g = round(255 - t * (255 - target[1]))
    b = round(255 - t * (255 - target[2]))
    return f"#{r:02x}{g:02x}{b:02x}"


def _price_tag(label: str) -> str:
    tag = label.replace("<現價>", " 現價").replace("<目標>", " 目標")
    return tag


def heatmap_html(mv: service.MatrixView) -> str:
    n = len(mv.dates)
    head_cells = []
    for j, (iso, lbl) in enumerate(mv.dates):
        suffix = ("*" if lbl == "*" else "") + ("（到期）" if j == n - 1 else "")
        head_cells.append(
            f'<th style="padding:4px 8px;white-space:nowrap">{iso[5:7]}/{iso[8:10]}{suffix}</th>')
    rows = []
    for i in range(len(mv.prices) - 1, -1, -1):
        price, plabel = mv.prices[i]
        cells = "".join(
            f'<td style="background:{cell_color(v)};color:#111;text-align:right;'
            f'padding:4px 8px">{v * 100:+.0f}%</td>'
            for v in mv.cells[i])
        rows.append(
            f'<tr><td style="padding:4px 8px;white-space:nowrap">'
            f'{price:.2f}{_price_tag(plabel)}</td>{cells}</tr>')
    return ('<div style="overflow-x:auto"><table style="border-collapse:collapse;'
            'font-family:monospace;font-size:13px">'
            f'<tr><th style="padding:4px 8px">價格</th>{"".join(head_cells)}</tr>'
            + "".join(rows) + "</table></div>"
            '<p style="font-size:12px;color:#666">此圖顯示在不同標的價格與日期下，'
            '以目前 Mid 價進場的模型報酬率。</p>')


def run_analysis(request, progress):
    return service.run(request, progress)


def _money(x: float) -> str:
    return f"{x:.2f}"


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _single_card(cv) -> str:
    v = cv.valuation
    c = v.contract
    warn = "；".join(cv.cons) if cv.cons else "無"
    return (f"**K={c.strike:g} / {c.expiry} 到期**\n\n"
            f"- Bid ${_money(c.bid)} / Mid ${_money(v.mid)} / Ask ${_money(c.ask)}"
            f"（每張 ${v.mid * 100:.0f}）｜IV {c.implied_volatility * 100:.0f}%｜"
            f"Delta {v.delta:.2f}\n"
            f"- Breakeven ${_money(v.breakeven)}｜劇本日估值 ${_money(v.baseline_value)}"
            f"｜損益 {v.baseline_value - v.mid:+.2f}｜"
            f"報酬率 {_pct((v.baseline_value - v.mid) / v.mid)}｜"
            f"最差進場 {_pct((v.baseline_value - c.ask) / c.ask)}\n"
            f"- 優點：{'；'.join(cv.pros)}\n- 警示：{warn}")


def _spread_card(cv) -> str:
    sv = cv.valuation
    warn = "；".join(cv.cons) if cv.cons else "無"
    return (f"**買 {sv.long_leg.strike:g} / 賣 {sv.short_leg.strike:g} / "
            f"{sv.long_leg.expiry} 到期（寬度 ${_money(sv.width)}）**\n\n"
            f"- Net Mid ${_money(sv.net_mid)}（每組 ${sv.net_mid * 100:.0f}）｜"
            f"最差（Natural）${_money(sv.net_worst)}｜最大虧損 ${_money(sv.net_mid)}｜"
            f"最大獲利 ${_money(sv.max_profit)}\n"
            f"- Breakeven ${_money(sv.breakeven)}｜劇本日估值 ${_money(sv.baseline_value)}"
            f"｜損益 {sv.baseline_value - sv.net_mid:+.2f}｜"
            f"報酬率 {_pct((sv.baseline_value - sv.net_mid) / sv.net_mid)}｜"
            f"最差進場 {_pct((sv.baseline_value - sv.net_worst) / sv.net_worst)}\n"
            f"- 優點：{'；'.join(cv.pros)}\n- 警示：{warn}")


def _render_results(result) -> None:
    m = result.meta
    st.subheader("劇本摘要")
    base = result.request.base_params
    lines = [f"{m.symbol} 現價 ${_money(m.spot)}",
             f"劇本：{base.target_date} 前到達 ${_money(base.target_price)}",
             f"資料時間：{m.fetched_at}（來源 {m.source}）",
             "已比較：" + "、".join(
                 STRATEGY_LABELS[r.strategy] for r in result.results
                 if r.status == "ok")]
    for r in result.results:
        if r.status != "ok":
            lines.append(f"（{STRATEGY_LABELS[r.strategy]}：{r.message}）")
    st.write("  \n".join(lines))

    if result.comparison:
        st.subheader("跨策略比較")
        header = "|策略|候選|到期日|進場成本|劇本報酬率|最差進場報酬率|Breakeven|最大獲利|\n|---|---|---|---|---|---|---|---|"
        rows = []
        for row in result.comparison:
            badge = "🏆最高報酬 " if row.strategy == result.best_strategy else ""
            mp = "無上限" if row.max_profit is None else f"${_money(row.max_profit)}"
            rows.append(
                f"|{badge}{STRATEGY_LABELS[row.strategy]}|{row.label}|{row.expiry}"
                f"|${_money(row.cost)}|{_pct(row.baseline_return)}"
                f"|{_pct(row.worst_return)}|${_money(row.breakeven)}|{mp}|")
        st.markdown(header + "\n" + "\n".join(rows))
        st.caption("最高報酬 ≠ 最佳投資：本系統不判斷劇本發生機率。")

    shown = [r for r in result.results]
    tabs = st.tabs([STRATEGY_LABELS[r.strategy] for r in shown])
    for tab, res in zip(tabs, shown):
        with tab:
            if res.status != "ok":
                st.info(res.message)
                continue
            for i, cv in enumerate(res.candidates):
                st.markdown(_spread_card(cv)
                            if res.strategy in SPREAD_STRATEGIES
                            else _single_card(cv))
                with st.expander("查看 Heatmap", expanded=(i == 0)):
                    st.markdown(heatmap_html(cv.matrix),
                                unsafe_allow_html=True)
            with st.expander("查看完整計算細節"):
                st.code(res.report_text, language=None)


st.set_page_config(page_title="Option Chaser", layout="wide")
st.title("Option Chaser")
st.caption("輸入你的價格劇本，Option Chaser 會自動掃描目前的選擇權鏈，"
           "比較單腿與價差策略，找出條件式報酬率最高的候選。")

with st.form("scenario"):
    symbol_in = st.text_input("標的", key="symbol", placeholder="TLT")
    target_price_in = st.number_input("目標價位", key="target_price",
                                      min_value=0.01, value=100.0, step=1.0)
    target_date_in = st.date_input("預計到達時間", key="target_date",
                                   value=date.today() + timedelta(days=180),
                                   min_value=date.today() + timedelta(days=1))
    checks = {s: st.checkbox(STRATEGY_LABELS[s], key=f"chk-{s}",
                             value=(s in DEFAULT_CHECKED))
              for s in STRATEGY_ORDER}
    submitted = st.form_submit_button(
        "開始分析", disabled=st.session_state.get("running", False))

def _do_analysis() -> None:
    """Runs on the rerun AFTER running=True, so the form above is already
    rendered disabled while this executes (two-phase rerun pattern)."""
    request = st.session_state.pop("pending_request")
    try:
        with st.status("分析中……", expanded=True) as status:
            result = run_analysis(request, status.write)
            status.update(label="分析完成", state="complete")
        st.session_state["result"] = result
        st.session_state.pop("error_msg", None)
    except FetchError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = (
            "找不到此標的，請確認代號是否正確。" if "資料不足" in str(e)
            else f"目前無法取得 {request.symbol} 的市場資料，請稍後再試。")
    except ParamError as e:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = str(e)
    except Exception:
        st.session_state.pop("result", None)
        st.session_state["error_msg"] = "分析過程發生錯誤，請稍後再試。"
    finally:
        st.session_state["running"] = False


if submitted and not st.session_state.get("running", False):
    sym = (symbol_in or "").strip().upper()
    strategies = tuple(s for s in STRATEGY_ORDER if checks[s])
    if not sym:
        st.error("請輸入標的代號。")
    elif not strategies:
        st.error("請至少勾選一種策略。")
    else:
        base = AnalysisParams(target_price=float(target_price_in),
                              target_date=target_date_in.isoformat())
        st.session_state["pending_request"] = service.AnalysisRequest(
            symbol=sym, base_params=base, strategies=strategies)
        st.session_state["running"] = True
        st.rerun()   # next run renders the form with disabled=True, THEN analyzes

if st.session_state.get("running", False) and "pending_request" in st.session_state:
    _do_analysis()
    st.rerun()       # re-enable the button and show results/errors

if st.session_state.get("error_msg"):
    st.error(st.session_state["error_msg"])
if "result" in st.session_state:
    _render_results(st.session_state["result"])
