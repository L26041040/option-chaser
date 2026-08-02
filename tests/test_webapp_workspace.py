# tests/test_webapp_workspace.py
"""v5 spec §7.7 ＋ T5（#19）: 工作區 GUI（AppTest）。

OC_WORKSPACE 隔離＋service seam 注入。群組區的 GUI 測試隨 T5 的
「群組區自首頁移除」一併撤下；其底層行為（關係確認、群組共用 snapshot、
群組重建）在 tests/test_workspace*.py 與 tests/test_store_groups.py 續測。
"""
from datetime import date

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from option_chaser import store, workspace
from webapp.render import return_md

PAGE = "webapp/app.py"
FIX = "tests/fixtures/xyz_v4_six_expiries.json"
TS = "2026-07-21T00:00:00+00:00"
OBSERVED = date(2026, 7, 21)   # 與 TS 同日：建立驗證不吃真實時鐘
# 與頁面同名的 session_state 旗標鍵（頁面檔名含數字前綴的中文字元，無法
# import，故在此複製常數字面值；兩邊改動需同步）。
AUTO_REFRESH_KEY = "ws-auto-refreshed"


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OC_WORKSPACE", str(tmp_path))
    import option_chaser.service as svc
    real_offline = svc.run_offline
    monkeypatch.setattr(svc, "run",
                        lambda req, progress=None: real_offline(req, FIX, progress))
    from option_chaser.data.snapshot import load_snapshot
    monkeypatch.setattr(svc, "fetch_and_save",
                        lambda symbol: (load_snapshot(FIX), FIX))
    return tmp_path


def _mk(ws_root, price=120.0, tmonth="2028-01"):
    return workspace.create_scenario(
        ws_root, symbol="XYZ", direction="bullish", target_price=price,
        target_month=tmonth, notes="", strategies=("long-call",), ts=TS,
        observed=OBSERVED)


def _body(at):
    return " ".join(m.value for m in at.markdown)


def _list_text(at):
    """側欄（清單）內的所有文字——卡片內容的斷言範圍。"""
    col = at.sidebar
    return " ".join([m.value for m in col.markdown]
                    + [b.label for b in col.button]
                    + [c.value for c in col.caption])


def _click_analyze(at, sid):
    """點右欄「分析」鈕並跑一輪（成功或失敗都可能發生，呼叫端自行斷言）。"""
    next(b for b in at.button
        if b.key == f"ws-an-{sid}").set_value(True).run(timeout=30)


# ---------- 建立表單（T4，#18） ----------

def test_create_via_form_appears_in_list(ws):
    """T4：三欄填寫即可建立；方向／策略由系統帶入 MVP 預設。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.text_input(key="ws-new-price").set_value("120")
    at.text_input(key="ws-new-month").set_value("2028/1")   # 四種寫法之一
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert not at.exception
    assert "XYZ" in _list_text(at)
    sc = workspace.list_scenarios(ws)[0]
    assert sc.id == "XYZ-120-202801"
    assert sc.target_month == "2028-01"
    assert sc.direction == "bullish"                 # 預設帶入,不經 UI
    assert sc.strategies == ("bull-call-spread",)    # MVP 預設策略
    assert sc.notes == ""                            # 備註欄已移除


def test_create_form_exposes_only_three_inputs(ws):
    """T4：方向／策略／備註不出現在建立表單。"""
    at = AppTest.from_file(PAGE)
    at.run()
    form_text_keys = {t.key for t in at.text_input}
    assert "ws-new-symbol" in form_text_keys
    assert "ws-new-month" in form_text_keys
    assert "ws-new-notes" not in form_text_keys
    assert not any(sb.key == "ws-new-direction" for sb in at.selectbox)
    assert not any((cb.key or "").startswith("ws-new-chk-")
                   for cb in at.checkbox)


def test_create_form_fields_start_blank(ws):
    """QA1-04（#31）：標的／目標價位／目標年月全部留白，不預填任何值
    （年月輔助下拉同樣不預先選中）。"""
    at = AppTest.from_file(PAGE)
    at.run()
    assert at.text_input(key="ws-new-symbol").value in (None, "")
    assert at.text_input(key="ws-new-price").value in (None, "")
    assert at.text_input(key="ws-new-month").value in (None, "")
    assert at.selectbox(key="ws-new-year").value is None
    assert at.selectbox(key="ws-new-month-dd").value is None


def test_month_dropdown_selection_fills_the_text_input(ws):
    """QA1-04（#31）：年／月輔助下拉與文字輸入並存；選好兩個下拉即自動把
    `YYYY/M` 填進文字框（可行範圍內的下拉→文字連動，見
    `_sync_month_dropdown_to_text` 註解）。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.selectbox(key="ws-new-year").set_value(2028).run(timeout=30)
    at.selectbox(key="ws-new-month-dd").set_value(1).run(timeout=30)
    assert at.text_input(key="ws-new-month").value == "2028/1"


def test_create_rejects_unparseable_month(ws):
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.text_input(key="ws-new-price").set_value("120")
    at.text_input(key="ws-new-month").set_value("明年一月")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("目標年月" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []


def test_create_rejects_blank_or_non_positive_price(ws):
    """QA1-04（#31）：目標價位改純文字輸入、不留預設值——留白、非數字、
    非正數皆須擋下，不得像舊版 `st.number_input` 一樣悄悄落回某個預設值。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.text_input(key="ws-new-month").set_value("2028/1")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("目標價位" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []

    at.text_input(key="ws-new-price").set_value("-5")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    assert any("目標價位" in e.value for e in at.error)
    assert workspace.list_scenarios(ws) == []


# ---------- 版面與卡片（T5，#19） ----------

def test_scenario_list_lives_in_collapsible_sidebar(ws):
    """QA1-02（#29）：清單改放 `st.sidebar`，不再是 `st.columns([0.2, 0.8])`
    ——後者窄螢幕會自然堆疊、清單整段疊在主畫面上方（回報的缺陷）。
    sidebar 在桌面上是常駐左欄、窄螢幕自動收合成漢堡選單拉出的側欄，兩種
    行為皆由 Streamlit 框架本身保證，不需要應用層另外判斷視窗寬度。"""
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    assert any(b.key == "ws-refresh-all" for b in at.sidebar.button)
    assert not any(round(c.weight, 2) == 0.2 for c in at.columns)


def test_card_carries_the_five_items_and_nothing_technical(ws):
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    text = _list_text(at)
    card = workspace.card_of(sc, workspace.latest_result(ws, sc.id))
    assert "XYZ" in text and "120.00" in text and "2028-01" in text
    assert return_md(card.best_return) in text          # 最高收益率
    assert "🟢" in text                                   # 需求六：完整刷新成功＝綠燈
    # 不得出現：完整腿資訊、佔本金等技術數字、生命週期 badge
    assert "買 " not in text and "賣 " not in text
    assert "佔本金" not in text and "情境最壞" not in text
    assert "Active" not in text


def test_card_return_is_coloured_by_sign(ws):
    """著色規則本身（正綠負紅）由 `test_card_render.py` 對 `return_md` 純函式
    覆蓋；這裡只驗證卡片實際顯示的字串跟 `return_md(card.best_return)`
    一致——不管 baseline 期真實報酬的正負號（QA1-03／#30：取值口徑改為
    baseline 期後，同一份 fixture 的正負號本就可能與舊口徑不同）。"""
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    card = workspace.card_of(sc, workspace.latest_result(ws, sc.id))
    assert card.best_return is not None
    assert return_md(card.best_return) in _list_text(at)


def test_card_without_analysis_shows_a_dash(ws):
    """附錄 A8.1：尚無成功快照的劇本，卡片收益率顯示「—」。

    停用 T7 自動刷新（見下方 `AUTO_REFRESH_KEY`）：本測試驗證的是卡片渲染邏輯，
    與「開站是否自動刷新」正交——T7 的自動刷新行為由專屬測試涵蓋。
    """
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True
    at.run()
    assert "—" in _list_text(at)
    assert "⚪" in _list_text(at)          # 需求六：從未刷新過＝中性佔位


def test_month_over_scenario_shows_red_signal(ws):
    """需求六：紅燈只問日曆、不依賴市場資料，優先於綠與黃。"""
    workspace.create_scenario(
        ws, symbol="OLD", direction="bullish", target_price=100.0,
        target_month="2026-01", notes="", strategies=("long-call",),
        ts=TS, observed=date(2026, 1, 15))
    at = AppTest.from_file(PAGE)
    at.run()
    assert "🔴" in _list_text(at)


def test_card_click_opens_that_scenario_detail(ws):
    a = _mk(ws, price=110.0, tmonth="2028-01")
    b = _mk(ws, price=130.0, tmonth="2028-12")
    workspace.analyze_scenario(ws, b.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    next(bt for bt in at.button
         if bt.key == f"ws-card-{b.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert at.session_state["ws-detail"] == b.id
    subheaders = " ".join(s.value for s in at.subheader)
    assert "130.00" in subheaders and "Step 2" in subheaders
    assert a.id != b.id


def test_group_section_is_not_rendered(ws):
    """附錄 A8.6：群組區自首頁隱藏（底層邏輯保留，見 test_store_groups.py）。"""
    _mk(ws, price=110.0, tmonth="2028-01")
    _mk(ws, price=120.0, tmonth="2028-12")
    at = AppTest.from_file(PAGE)
    at.run()
    page = _body(at) + " ".join(s.value for s in at.subheader)
    assert "劇本群組" not in page and "里程碑路徑" not in page
    assert not any((bt.key or "").startswith(("ws-rel-", "ws-gan-", "ws-rean-"))
                   for bt in at.button)
    # 底層仍然重建群組（只是不再曝露於此頁）
    assert len(workspace.load_groups(ws)["groups"][0]["members"]) == 2


# ---------- 清單編輯工具（T5，#19；附錄 A6/A8.2） ----------

def test_remove_tool_is_hidden_until_edit_mode(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not any(bt.key == f"ws-rm-{sc.id}" for bt in at.button)
    at.toggle(key="ws-edit").set_value(True).run(timeout=30)
    assert any(bt.key == f"ws-rm-{sc.id}" for bt in at.button)


def test_remove_takes_a_second_confirmation(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.toggle(key="ws-edit").set_value(True).run(timeout=30)
    next(bt for bt in at.button
         if bt.key == f"ws-rm-{sc.id}").set_value(True).run(timeout=30)
    assert workspace.list_scenarios(ws) != []            # 還沒真的移除
    next(bt for bt in at.button
         if bt.key == f"ws-rm-no-{sc.id}").set_value(True).run(timeout=30)
    assert workspace.list_scenarios(ws) != []            # 取消＝什麼都沒發生


def test_remove_soft_deletes_and_keeps_history(ws):
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    at.toggle(key="ws-edit").set_value(True).run(timeout=30)
    next(bt for bt in at.button
         if bt.key == f"ws-rm-{sc.id}").set_value(True).run(timeout=30)
    next(bt for bt in at.button
         if bt.key == f"ws-rm-yes-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert workspace.list_scenarios(ws) == []            # 清單不再包含
    assert "XYZ" not in _list_text(at)
    assert list((ws / "results" / sc.id).glob("*.json"))  # 歷史檔案還在
    assert any(e["event"] == "SCENARIO_REMOVED"
               for e in store.read_events(ws))


# ---------- 詳細頁（右欄） ----------

def test_analysis_error_stays_visible(ws, monkeypatch):
    """失敗不 rerun：st.error 留在畫面上（durable feedback）。"""
    sc = _mk(ws)
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("boom")))
    at = AppTest.from_file(PAGE)
    at.run()
    _click_analyze(at, sc.id)
    assert any("boom" in e.value for e in at.error)
    assert not at.exception


def test_critical_failure_marks_signal_yellow_on_next_render(ws, monkeypatch):
    """需求六：關鍵資料（FetchError）失敗 → 黃燈；卡片顯示上次成功更新時間。

    失敗當下刻意不 rerun（見上一測試），黃燈因此反映在下一次渲染——與同一
    session 內任何後續互動（切頁、點其他卡片）等效，這裡用再呼叫一次
    `at.run()` 模擬。
    """
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    prior = workspace.latest_result(ws, sc.id)
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(FetchError("網路不通")))
    at = AppTest.from_file(PAGE)
    at.run()
    _click_analyze(at, sc.id)
    assert any("網路不通" in e.value for e in at.error)
    at.run()
    text = _list_text(at)
    assert "🟡" in text
    assert prior["analyzed_at"] in text


def test_param_error_does_not_flip_signal_to_yellow(ws, monkeypatch):
    """附錄 A12／需求六：個別合約報價失敗與關鍵資料失敗是可辨識的不同通道
    ——非 `FetchError` 的例外（如 `ParamError`）不得被誤判為刷新失敗。"""
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    import option_chaser.service as svc
    from option_chaser.models import ParamError
    monkeypatch.setattr(svc, "run", lambda req, progress=None:
                        (_ for _ in ()).throw(ParamError("不相干的驗證錯誤")))
    at = AppTest.from_file(PAGE)
    at.run()
    _click_analyze(at, sc.id)
    assert any("不相干的驗證錯誤" in e.value for e in at.error)
    at.run()
    text = _list_text(at)
    assert "🟢" in text
    assert "🟡" not in text


def test_status_buttons_with_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key=f"ws-reason-{sc.id}").set_value("到價")
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert not at.exception
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Reached"


def test_status_button_requires_reason(ws):
    sc = _mk(ws)
    at = AppTest.from_file(PAGE)
    at.run()
    next(b for b in at.button
         if b.key == f"ws-reach-{sc.id}").set_value(True).run(timeout=30)
    assert any("請填原因" in e.value for e in at.error)
    assert store.load_scenario(store.scenario_path(ws, sc.id)).status == "Active"


def test_capital_pct_shown_in_detail_after_analysis(ws):
    sc = _mk(ws)
    store.save_constraints(ws, 100000.0)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert any("佔本金" in c.value for c in at.caption)


def test_detail_page_renders_four_steps(ws):
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    subheaders = " ".join(s.value for s in at.subheader)
    assert "Step 2" in subheaders and "Step 3" in subheaders \
        and "Step 4" in subheaders


def test_comparison_table_has_no_thumbnails_and_row_selects_on_click(ws):
    """QA1-05（#32）：到期日分組比較表的候選卡片改窄版整列可點——舊版
    「一整條寬列」＋thumbnail＋獨立「選看」鈕已拿掉，點整列即選中該候選。"""
    sc = _mk(ws)
    workspace.analyze_scenario(ws, sc.id, snapshot_path=FIX, ts=TS)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    body = " ".join(m.value for m in at.markdown)
    assert 'class="oc-thumb"' not in body

    before = at.session_state["ws-selected-key"]
    row_buttons = [b for b in at.button
                  if b.key and b.key.startswith("sel-")
                  and not b.key.startswith("sel-top10-")]
    assert row_buttons, "到期日分組比較表應至少有一個可點的候選列"
    other = next((b for b in row_buttons if b.key != f"sel-{before}"),
                row_buttons[0])
    other.set_value(True).run(timeout=30)
    assert not at.exception
    assert at.session_state["ws-selected-key"] == other.key[len("sel-"):]


def test_unanalyzed_scenario_detail_invites_analysis(ws):
    """停用 T7 自動刷新——見 `test_card_without_analysis_shows_a_dash` 的說明。"""
    _mk(ws)
    at = AppTest.from_file(PAGE)
    at.session_state[AUTO_REFRESH_KEY] = True
    at.run()
    assert any("尚無分析結果" in i.value for i in at.info)


# ---------- 自動／手動刷新與原子快照（T7，#21） ----------

def test_auto_refresh_happens_once_per_session(ws, monkeypatch):
    """需求七：開站首次載入自動刷新；同一 session 內多次 rerun 只打一次 API。"""
    sc = _mk(ws)
    calls = []
    import option_chaser.service as svc
    real_offline = svc.run_offline

    def counting_run(req, progress=None):
        calls.append(1)
        return real_offline(req, FIX, progress)

    monkeypatch.setattr(svc, "run", counting_run)
    at = AppTest.from_file(PAGE)
    at.run()
    assert len(calls) == 1
    assert workspace.latest_result(ws, sc.id) is not None
    at.run()   # 模擬同 session 內任何互動（切頁／點卡片／展開）造成的 rerun
    at.run()
    assert len(calls) == 1


def test_auto_refresh_skips_expired_scenarios(ws, monkeypatch):
    """需求七：只刷新未過期劇本——紅燈（目標月已過完）劇本不消耗 API。

    月份必須在「建立當下」合法（`observed` 落在該月內），靠真實時鐘在
    測試執行當下（沙箱日期晚於 2026-06）已經過完，模擬「建立後時間流逝」。
    """
    workspace.create_scenario(
        ws, symbol="OLD", direction="bullish", target_price=100.0,
        target_month="2026-06", notes="", strategies=("long-call",), ts=TS,
        observed=date(2026, 6, 15))
    calls = []
    import option_chaser.service as svc
    monkeypatch.setattr(svc, "run", lambda req, progress=None: calls.append(1))
    at = AppTest.from_file(PAGE)
    at.run()
    assert calls == []


def test_manual_refresh_button_refetches_all(ws, monkeypatch):
    """需求七：手動刷新鈕可再次刷新——不受「同 session 只自動一次」限制。"""
    sc = _mk(ws)
    calls = []
    import option_chaser.service as svc
    real_offline = svc.run_offline

    def counting_run(req, progress=None):
        calls.append(1)
        return real_offline(req, FIX, progress)

    monkeypatch.setattr(svc, "run", counting_run)
    at = AppTest.from_file(PAGE)
    at.run()
    assert len(calls) == 1                          # 自動刷新
    next(b for b in at.button
         if b.key == "ws-refresh-all").set_value(True).run(timeout=30)
    assert len(calls) == 2                           # 手動刷新再打一次
    assert not at.exception
    assert workspace.latest_result(ws, sc.id) is not None


def test_refresh_all_one_failure_does_not_block_others(ws, monkeypatch):
    """需求七：多劇本其一關鍵資料失敗時，其餘劇本照常完成。"""
    a = _mk(ws, price=110.0, tmonth="2028-01")
    b = _mk(ws, price=130.0, tmonth="2028-12")
    import option_chaser.service as svc
    from option_chaser.models import FetchError
    real_offline = svc.run_offline

    def flaky_run(req, progress=None):
        if req.base_params.target_price == a.target_price:
            raise FetchError("boom")
        return real_offline(req, FIX, progress)

    monkeypatch.setattr(svc, "run", flaky_run)
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert workspace.latest_result(ws, a.id) is None       # 失敗，無快照
    assert workspace.latest_result(ws, b.id) is not None   # 照常完成
    text = _list_text(at)
    assert "🟡" in text and "🟢" in text


def test_create_triggers_immediate_first_analysis(ws):
    """需求七：建立劇本立即觸發首次刷新，完成後卡片即有數字。"""
    at = AppTest.from_file(PAGE)
    at.run()
    at.text_input(key="ws-new-symbol").set_value("XYZ")
    at.text_input(key="ws-new-price").set_value("120")
    at.text_input(key="ws-new-month").set_value("2028/1")
    at.run()
    next(b for b in at.button
         if b.key == "ws-new-create").set_value(True).run(timeout=30)
    sc = workspace.list_scenarios(ws)[0]
    view = workspace.latest_result(ws, sc.id)
    assert view is not None
    assert return_md(workspace.card_of(sc, view).best_return) in _list_text(at)
