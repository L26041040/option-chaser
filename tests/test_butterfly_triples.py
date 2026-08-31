"""T15（#230，Initial V2 spec #217）：`generate_butterfly_triples()`——
比照既有 `test_spread_pairs.py` 同一種寫法。"""
from option_chaser.models import AnalysisParams, OptionContract
from option_chaser.filters import generate_butterfly_triples

P_CALL_FLY = AnalysisParams(target_price=100.0, target_month="2026-08",
                            strategy="call-fly")


def make(sym, strike, bid, ask, expiry="2026-10-16", opt="call"):
    return OptionContract(contract_symbol=sym, option_type=opt, strike=strike,
                          expiry=expiry, bid=bid, ask=ask, last=None,
                          volume=10, open_interest=100, implied_volatility=0.35)


def test_combinations_and_sorted_strikes():
    legs = [make("A", 90.0, 8.0, 8.2), make("B", 100.0, 3.0, 3.2),
            make("C", 110.0, 0.5, 0.7),
            make("N", 95.0, 5.0, 5.2, expiry="2026-11-20")]
    triples, rep = generate_butterfly_triples(legs, P_CALL_FLY)
    # 同到期日 C(3,3)=1（Oct16）；Nov20 只有 1 張合約，組不出三元組
    assert rep.total_pairs == 1
    [(lo, mid, hi)] = triples
    assert lo.strike < mid.strike < hi.strike
    assert lo.expiry == mid.expiry == hi.expiry


def test_sanity_rejects_non_positive_average_debit():
    """A 層健全性：net_mid <= 0 的組合不成立——不是報價壞了，是這三個
    履約價湊不出一個有意義的 Butterfly（見 filters.generate_butterfly_
    triples docstring）。"""
    # 中腿 mid 遠比兩翼貴：賣 2 口中腿收到的錢遠超過買兩翼付出的錢
    legs = [make("A", 90.0, 0.5, 0.6), make("B", 100.0, 20.0, 20.2),
            make("C", 110.0, 0.2, 0.3)]
    triples, rep = generate_butterfly_triples(legs, P_CALL_FLY)
    assert triples == []
    assert rep.removed_sanity == 1 and rep.total_pairs == 1


def test_five_strikes_yields_ten_combinations():
    legs = [make(str(i), 90.0 + i * 5, 5.0, 5.2) for i in range(5)]
    triples, rep = generate_butterfly_triples(legs, P_CALL_FLY)
    assert rep.total_pairs == 10  # C(5,3)


def test_the_function_itself_does_not_filter_by_option_side():
    """權別過濾是 `apply_filters()`（`service._butterfly_result()` 呼叫
    端在傳進來之前已篩過）的職責，不是 `generate_butterfly_triples()`
    的——這裡直接驗證「沒篩過的話會怎樣」這個結構事實：call／put 混在
    一起，`by_expiry` 只依到期日分組，不依權別。6 張合約
    （3 履約價×call/put 各一張）同到期日 `C(6,3)=20` 組合，但相同
    履約價的 call／put 一組時（例如 90-call／90-put／100-call）會撞上
    `lo.strike == mid.strike` 的既有去重防呆而被跳過——3 個相異履約價
    × 每個各自選 call 或 put（2^3=8）才是履約價互不相等的組合，
    `20-8=12` 組因此被跳過，只剩 8 組真正進入配對。"""
    calls = [make("A", 90.0, 8.0, 8.2), make("B", 100.0, 3.0, 3.2),
            make("C", 110.0, 0.5, 0.7)]
    puts = [make("D", 90.0, 8.0, 8.2, opt="put"),
           make("E", 100.0, 3.0, 3.2, opt="put"),
           make("F", 110.0, 0.5, 0.7, opt="put")]
    triples, rep = generate_butterfly_triples(calls + puts, P_CALL_FLY)
    assert rep.total_pairs == 8
    for lo, mid, hi in triples:
        assert lo.strike < mid.strike < hi.strike
