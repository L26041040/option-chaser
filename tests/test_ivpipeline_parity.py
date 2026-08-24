"""T05（#189）：`option_chaser.ivpipeline` 與 `api_app/main.py` 現行
iv-history 編排的逐位元 parity 測試。

`api_app/main.py` 這一票完全不動（T10／#192 才切換呼叫路徑）——這裡
分別跑兩條路徑（真正的 HTTP endpoint 一次、新模組直接呼叫一次），拿
同一組輸入比對輸出，證明新模組現在就已經是既有行為的忠實搬遷，不是
先射箭再畫靶。

`diagnostics` 信封不比——那是 HTTP-request 生命週期的東西（correlation
id、per-request buffer），新模組刻意不知道它的存在（見模組 docstring）。
"""
import dataclasses
from datetime import date, timedelta

from fastapi.testclient import TestClient

from api_app import providers
from api_app.main import create_app
from api_app.storage.memory import MemoryStorage
from option_chaser import dividends as dividends_module
from option_chaser import ivpipeline
from option_chaser import ratecurve as ratecurve_module
from option_chaser.data.snapshot import load_snapshot
from option_chaser.dividends import DividendHistory, DividendRecord
from option_chaser.ivhistory import SurfacePoint
from option_chaser.ratecurve import RateCurve
from option_chaser.valuation import DAYS_PER_YEAR, american_price, days_between

FIX = "tests/fixtures/xyz_v4_six_expiries.json"
PROVIDER = providers.MARKETDATA_APP.id
TOKEN = "mdapp_live_SECRET1234abcd"

_RATE = RateCurve(curve_date="2026-07-31",
                  nodes=((0.5, 0.041), (1.0, 0.042), (2.0, 0.043), (3.0, 0.044)))
_DIV = DividendHistory(symbol="XYZ", as_of="2026-07-14", source="yahoo",
                       distributions=(DividendRecord("2026-06-01", 1.2),))
_RATE_CURVE_ROWS = (("2020-01-01", ((0.1, 0.04), (30.0, 0.04))),)


def _rate_loader(today):
    return _RATE, "假曲線"


def _dividend_loader(symbol, today):
    return _DIV, "假配息"


def _rate_curve_rows_2arg(from_date, to_date):
    """`create_app()` 的 DI 參數簽章（兩個位置參數）——main.py 內部
    包上 `treasury_cache.cached_rate_curve_rows()` 才變成三參數版。"""
    return _RATE_CURVE_ROWS


def _snap():
    return dataclasses.replace(load_snapshot(FIX), source="cboe")


def _grid():
    pts = [SurfacePoint(dte=dte, delta=d, iv=0.20 + 0.1 * d)
           for dte in (1, 30, 90, 365, 1200)
           for d in (0.0001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.9999)]
    return {"call": pts, "put": pts}


def _rich_surface(*_args, **_kwargs):
    return _grid()


def _synthetic_quote(date_str, *, option_type, strike, expiration,
                     spot=100.0, sigma):
    """跟 `tests/test_api_iv_history.py` 同一套手法：建一筆會在正式
    reconstruction 路徑精確反解回 `sigma` 的 quote dict。"""
    T = days_between(date.fromisoformat(date_str),
                     date.fromisoformat(expiration)) / DAYS_PER_YEAR
    curve = ratecurve_module.curve_asof(_RATE_CURVE_ROWS, date_str)
    r = ratecurve_module.rate_for_tenor(curve, T)
    q = dividends_module.compute_q_asof(
        _DIV, spot=spot, observation_date=date.fromisoformat(date_str))
    price = american_price(option_type, spot, strike, T, r, q, sigma)
    bid = max(price / 2.0, 1e-8)
    ask = max(price * 1.5, 1e-6)
    return {"date": date_str, "updated": 1, "dte": None,
           "bid": bid, "ask": ask, "mid": price,
           "underlying_price": spot, "vendor_iv": None}


class _ContractHistoryFake:
    """HTTP 路徑用：依 occ_symbol 回傳預先準備好的 quote 序列。"""

    def __init__(self, points_by_symbol):
        self._points = points_by_symbol

    def __call__(self, provider, occ_symbol, from_date, to_date, token,
                observer=None):
        return list(self._points.get(occ_symbol, []))


# ---------- 新模組這一側的純記憶體 storage 假體 ----------

@dataclasses.dataclass
class _ContractHistoryRow:
    points: tuple
    fetched_through: str | None
    last_attempt_on: str | None
    last_status: str
    last_note: str | None


@dataclasses.dataclass
class _BackfillRunRow:
    symbol: str
    ran_on: str
    outcome: str
    note: str | None


@dataclasses.dataclass
class _ObservationRow:
    observed_on: str
    surface: dict


class FakeIvStorage:
    """T05（#189）acceptance criteria 明文要求的「純記憶體假體」——不
    依賴 `api_app`，欄位形狀 duck-type 對照 `StoragePorts` 的期待。"""

    def __init__(self):
        self._contract_history: dict[str, _ContractHistoryRow] = {}
        self._backfill_runs: dict[str, _BackfillRunRow] = {}
        self._observations: dict[str, list[_ObservationRow]] = {}

    def get_contract_history(self, contract_symbol):
        return self._contract_history.get(contract_symbol)

    def save_contract_history(self, *, contract_symbol, points, fetched_through,
                              last_attempt_on, last_status, last_note):
        self._contract_history[contract_symbol] = _ContractHistoryRow(
            points=points, fetched_through=fetched_through,
            last_attempt_on=last_attempt_on, last_status=last_status,
            last_note=last_note)

    def get_iv_backfill_run(self, symbol):
        return self._backfill_runs.get(symbol)

    def save_iv_backfill_run(self, symbol, ran_on, outcome, note):
        self._backfill_runs[symbol] = _BackfillRunRow(symbol, ran_on, outcome, note)

    def iv_observation_dates(self, symbol):
        return sorted(o.observed_on for o in self._observations.get(symbol, []))

    def save_iv_observation(self, symbol, observed_on, surface, fetched_at):
        rows = self._observations.setdefault(symbol, [])
        rows[:] = [o for o in rows if o.observed_on != observed_on]
        rows.append(_ObservationRow(observed_on=observed_on, surface=surface))

    def iv_observations(self, symbol):
        """真正的 adapter（`api_app/storage/memory.py`／`postgres.py`）都依
        `observed_on` 遞增排序回傳——這是 port 的隱含契約（`build_iv_history`
        自己不排序），假體要忠實模擬才能驗出 parity。"""
        return sorted(self._observations.get(symbol, []),
                     key=lambda o: o.observed_on)


def _client(db, *, contract_history):
    return TestClient(create_app(
        storage=db, fetch=lambda s: _snap(), rate_loader=_rate_loader,
        dividend_loader=_dividend_loader,
        verify_provider=lambda p, t: providers.VerifyOutcome(True),
        historical_surface=_rich_surface, contract_history=contract_history,
        rate_curve_rows=_rate_curve_rows_2arg))


def _unlock(client):
    client.put("/api/settings", json={
        "market_data": {"mode": "default", "provider": None},
        "historical_iv": {"mode": "custom", "provider": PROVIDER}})
    client.put(f"/api/settings/credentials/{PROVIDER}", json={"token": TOKEN})
    client.post(f"/api/settings/credentials/{PROVIDER}/test")


def _scenario_and_candidate(client):
    sid = client.post("/api/scenarios", json={
        "symbol": "XYZ", "target_price": 130.0,
        "target_month": "2026-09"}).json()["id"]
    client.post(f"/api/scenarios/{sid}/refresh")
    view = client.get(f"/api/scenarios/{sid}").json()["latest_result"]
    pool = view["candidate_pool"]
    for r in view["results"]:
        for g in r.get("expiry_top10") or []:
            for key in g["candidate_keys"]:
                c = pool[key]
                if len(c["legs"]) >= 2:
                    return sid, c, view
    raise AssertionError("樣本裡沒有兩腿的候選可用")


def test_build_iv_history_matches_the_live_http_endpoint_bit_for_bit():
    """HTTP 端點（main.py 現行編排）與新模組直接呼叫，同一組輸入下
    candidate_key／status／normalized_skew_points／metrics／
    observations／note／legs／spread_gap 逐位元相同。"""
    db = MemoryStorage()
    client = _client(db, contract_history=lambda *a, **k: [])
    _unlock(client)
    sid, candidate, view = _scenario_and_candidate(client)
    key = candidate["candidate_key"]
    buy_leg, sell_leg = candidate["legs"][0], candidate["legs"][1]

    end = date.fromisoformat(buy_leg["expiry"]) - timedelta(days=100)
    buy_points = [_synthetic_quote((end - timedelta(days=2 - i)).isoformat(),
                                   option_type=buy_leg["option_type"],
                                   strike=buy_leg["strike"],
                                   expiration=buy_leg["expiry"], sigma=0.20 + 0.01 * i)
                 for i in range(3)]
    sell_points = [_synthetic_quote((end - timedelta(days=2 - i)).isoformat(),
                                    option_type=sell_leg["option_type"],
                                    strike=sell_leg["strike"],
                                    expiration=sell_leg["expiry"], sigma=0.30 + 0.01 * i)
                  for i in range(3)]
    points_by_symbol = {buy_leg["contract_symbol"]: buy_points,
                        sell_leg["contract_symbol"]: sell_points}

    # ---- 路徑一：真正的 HTTP endpoint（main.py 現行編排，完全不動） ----
    client_with_history = _client(
        db, contract_history=_ContractHistoryFake(points_by_symbol))
    _unlock(client_with_history)
    http_body = client_with_history.get(
        f"/api/scenarios/{sid}/iv-history",
        params={"candidate_key": key}).json()

    # ---- 路徑二：新模組直接呼叫，全新的純記憶體 storage ----
    from api_app.treasury_cache import cached_rate_curve_rows as _cache_curve
    from api_app.storage.memory import MemoryStorage as _MS
    rate_curve_rows_3arg = _cache_curve(_MS(), _rate_curve_rows_2arg)

    known_expiries = sorted({
        e for r in view.get("results") or []
        for e, _ in r.get("expiry_counts") or []})
    today = date.today()
    events: list[dict] = []

    def _emit(**kwargs):
        events.append(kwargs)

    fake_storage = FakeIvStorage()
    module_result = ivpipeline.build_iv_history(
        symbol="XYZ", candidate=candidate, spot=view["meta"]["spot"],
        known_expiries=known_expiries, provider=PROVIDER, token=TOKEN,
        today=today, now_utc_iso=lambda: "2026-01-01T00:00:00+00:00",
        vendor=ivpipeline.VendorPorts(
            historical_surface=_rich_surface,
            contract_history=_ContractHistoryFake(points_by_symbol),
            rate_curve_rows=rate_curve_rows_3arg,
            dividend_loader=_dividend_loader),
        storage=ivpipeline.StoragePorts(
            get_contract_history=fake_storage.get_contract_history,
            save_contract_history=fake_storage.save_contract_history,
            get_iv_backfill_run=fake_storage.get_iv_backfill_run,
            save_iv_backfill_run=fake_storage.save_iv_backfill_run,
            iv_observation_dates=fake_storage.iv_observation_dates,
            save_iv_observation=fake_storage.save_iv_observation,
            iv_observations=fake_storage.iv_observations),
        emit_exact=_emit, emit_legacy=_emit)

    for field in ("candidate_key", "status", "normalized_skew_points",
                 "metrics", "observations", "note", "legs", "spread_gap"):
        assert module_result[field] == http_body[field], field
