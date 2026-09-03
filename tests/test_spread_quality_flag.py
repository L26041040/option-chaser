"""FB5-02／FB5-03（#63／#64）：候選品質標示——只標不刪，不影響誰進得了
候選池。買賣價差寬度沿用既有機制（`CandidateView.quote_warning`）；
單調性違反走獨立欄位（`.monotonicity_warning`），見各自測試前的說明。

MVP V3（#104，spec #102 決策 F）起，選取閘門與顯示語意分家：
`quote_warning`（zero_vol or wide_spread，不對外序列化，只供內部挑選
default_pair）與 `wide_spread_warning`（僅 `is_spread_wide`，⚠ 徽章與
候選池文案認的顯示旗標）分開算。T04（#220，#217 決策 D）把 `quote_
warning` 原本的第三個條件（friction>25%）連同 friction 本身自
canonical model 整個移除，不新增任何替代指標——本檔案下半段
（`test_zero_volume_alone_does_not_trigger_the_display_flag` 起）驗證
剩下兩個條件確實分開算。

用最小、完全掌控的合成快照測試，不用大 fixture：這裡要驗證的是「特定
一組合約會不會被標示、標示對不對」，用真實 JSON 快照的話，排名（每級距
只留第一名）可能把它擋在候選名單外，於是斷言不到。`tests/test_api_
filters.py` 另外用既有 `xyz_v2_snapshot.json` 驗證池子層級的「進得了榜」
（filter_report 通過數增加、關卡消失）——兩層合起來才是 spec #61 指定
的兩個接縫。
"""
from option_chaser import service
from option_chaser.data.snapshot import save_snapshot
from option_chaser.models import AnalysisParams, ChainSnapshot, OptionContract, SCHEMA_VERSION

EXPIRY = "2026-10-16"


def _contract(sym, strike, bid, ask, volume=50, option_type="call"):
    return OptionContract(
        contract_symbol=sym, option_type=option_type, strike=strike, expiry=EXPIRY,
        bid=bid, ask=ask, last=(bid + ask) / 2, volume=volume,
        open_interest=100, implied_volatility=0.30)


def _run(tmp_path, contracts, **params):
    snap = ChainSnapshot(schema_version=SCHEMA_VERSION, symbol="XYZ",
                         fetched_at="2026-07-15T21:30:00-04:00", spot=100.0,
                         source="yfinance", contracts=tuple(contracts))
    path = tmp_path / "snap.json"
    save_snapshot(snap, path)
    p = AnalysisParams(target_price=120.0, target_month="2026-08", **params)
    req = service.AnalysisRequest(symbol="XYZ", base_params=p,
                                  strategies=("long-call",))
    return service.run_offline(req, str(path))


def test_wide_spread_candidate_is_flagged_but_not_excluded(tmp_path):
    # spread 2.0, mid 5.0, 舊硬門檻 max(0.10, 0.15*5.0=0.75) -> 2.0 超標。
    # 唯一候選——沒有排名截斷的疑慮，斷言直接對準。
    # friction=(6-5)/5=20%（<25%）、volume=50（預設，非零）——這組候選
    # 只靠 is_spread_wide 一項觸發，MVP V3（#104）AC 三案例之一：
    # 「is_spread_wide 為真才觸發顯示旗標」，不與另外兩個條件混在一起。
    wide = _contract("wide", strike=110.0, bid=4.0, ask=6.0)
    r = _run(tmp_path, [wide])
    res = r.results[0]
    assert res.status == "ok"          # FB5-02 核心：進得了榜，不是 empty
    assert len(res.candidates) == 1
    cv = res.candidates[0]
    assert cv.quote_warning is True    # 沿用既有機制，不是新欄位
    assert cv.wide_spread_warning is True   # MVP V3（#104）顯示旗標


# T04（#220，#217 決策 D）：`test_flag_carries_how_wide_via_existing_
# friction_field` 已隨 friction 整個移除——「標示內容說得出寬到什麼
# 程度」這個票上要求，票上明文「不新增任何替代的 friction 指標」，
# 因此不補一個新欄位頂替，量級資訊改為使用者從逐腿 Bid/Ask 自行判讀。


def test_narrow_spread_candidate_is_not_flagged_for_width(tmp_path):
    """緊價差不該無端被標——只有真正超過舊門檻公式的才標，不是「有價差
    就標」。避免這次改動把警示變成到處都是、失去意義。"""
    tight = _contract("tight", strike=110.0, bid=4.95, ask=5.05)
    r = _run(tmp_path, [tight])
    cv = r.results[0].candidates[0]
    assert cv.quote_warning is False
    assert cv.wide_spread_warning is False


# --- MVP V3（#104，spec #102 決策 F）：顯示旗標 wide_spread_warning 收斂
# 成單一判準——volume==0 不再觸發顯示，即使 quote_warning（選取閘門用的
# 複合旗標）仍然為真。T04（#220）之後 quote_warning 只剩 zero_vol 與
# wide_spread 兩個條件，friction 那一項已整個移除、不補替代指標。
# --- ---

def test_zero_volume_alone_does_not_trigger_the_display_flag(tmp_path):
    """volume==0 單獨存在（價差窄）：`quote_warning` 仍因零成交量觸發，
    但顯示旗標不再認這個條件——LEAPS／冷門履約價零成交是常態，不該被
    說成報價可疑。"""
    quiet = _contract("quiet", strike=110.0, bid=4.95, ask=5.05, volume=0)
    r = _run(tmp_path, [quiet])
    cv = r.results[0].candidates[0]
    assert cv.quote_warning is True         # 選取閘門：零成交量仍算一種觸發
    assert cv.wide_spread_warning is False  # 顯示：零成交量不再算數


# --- FB5-03（#64）：無套利一致性違反，走獨立的 `monotonicity_warning`
# 欄位——嚴重性與生成方式都與寬價差／零成交不同（配對關係違反，不是
# 單一數值超標），不混進 `quote_warning`。 ---

def test_monotonicity_violation_reaches_candidate_view(tmp_path):
    """需求方原話的最小重現，換一組數字：深價內（履約價 80）比深價外
    （履約價 130）還便宜（call 應該反過來）。兩張合約 delta 落在不同
    級距（保守型 vs 積極型），兩者都留在 `res.candidates` 裡，斷言才
    對得準——不是排名截斷後只剩一個。"""
    k80 = _contract("K80", strike=80.0, bid=9.8, ask=10.0)
    k130 = _contract("K130", strike=130.0, bid=11.8, ask=12.0)  # 違反：比 K80 貴
    r = _run(tmp_path, [k80, k130])
    res = r.results[0]
    assert res.status == "ok"   # 只標不刪，兩張都進得了榜
    by_strike = {cv.valuation.contract.strike: cv for cv in res.candidates}
    assert set(by_strike) == {80.0, 130.0}
    assert by_strike[80.0].monotonicity_warning is True
    assert by_strike[130.0].monotonicity_warning is True
    # 不該汙染既有的 quote_warning／wide_spread_warning——三個都是獨立
    # 欄位，各自的觸發條件不同。
    assert by_strike[80.0].quote_warning is False
    assert by_strike[80.0].wide_spread_warning is False


def test_monotone_quotes_are_not_flagged(tmp_path):
    """該不誤報的不誤報：正常遞減的 call 報價不該被標。"""
    k80 = _contract("K80", strike=80.0, bid=19.8, ask=20.0)
    k130 = _contract("K130", strike=130.0, bid=0.8, ask=1.0)
    r = _run(tmp_path, [k80, k130])
    for cv in r.results[0].candidates:
        assert cv.monotonicity_warning is False
