Option Chaser MVP V2 Specification

Status: FROZEN FOR IMPLEMENTATION
Version: MVP V2
Branch: feature/mvp-v2-simplification

1. Product Goal

Option Chaser MVP V2 accepts a simple market scenario and enumerates option debit spreads that could benefit if the scenario occurs.

The user provides only:

1. Symbol
2. Target month
3. Target price

The system automatically determines the trade direction, selects five relevant expiries, enumerates every valid spread pair within each expiry, and ranks the results by return calculated from the executable Ask-side entry cost.

MVP V2 prioritizes:

* Complete enumeration
* Transparent formulas
* Independent ranking for each expiry
* Minimal user input
* Reproducible results

It does not attempt to predict whether the scenario is correct.

⸻

2. User Input

Required fields:

symbol
target_month
target_price

Example:

symbol: TLT
target_month: 2028/01
target_price: 120

2.1 Symbol

The symbol is normalized to uppercase.

Example:

tlt

becomes:

TLT

2.2 Target Month

Accepted formats:

YYYY/M
YYYY/MM
YYYY-M
YYYY-MM

Examples:

2028/1
2028/01
2028-1
2028-01

All valid inputs are normalized to:

YYYY-MM

Example:

2028-01

Invalid or impossible months must produce a validation error.

2.3 Target Price

Target price must be a positive number.

The system compares target price with the current spot price:

target_price > spot
→ Bull Call Spread
target_price < spot
→ Bear Put Spread
target_price == spot
→ Validation error because trade direction cannot be inferred

The automatically inferred direction is shown to the user.

⸻

3. Expiry Selection

The system retrieves the actual expiries available for the symbol.

It then selects no more than five expiries surrounding the requested target month:

1. Resolve one actual expiry as the target-month baseline.
2. Select up to two expiries before the baseline.
3. Select up to two expiries after the baseline.
4. Include the baseline.
5. If one side has insufficient expiries, fill the remaining positions from the other side.
6. Return no duplicate expiries.
7. Return expiries in chronological order.

The exact deterministic baseline and tie-breaking algorithm must be implemented and tested in the dedicated expiry resolver.

The system must not invent expiry dates.

Each selected expiry is analyzed independently.

⸻

4. Core Enumeration

For each selected expiry, the system loads every available contract of the required option type:

Bullish scenario
→ Calls
Bearish scenario
→ Puts

If an expiry contains N distinct strikes, the enumerator generates:

N(N - 1) / 2

structurally valid spread pairs.

Enumeration must not use the legacy filtering or scoring system.

The enumerator must not reject contracts merely because of:

* Low open interest
* Zero volume
* High implied volatility
* Low implied volatility
* Wide bid-ask spread
* Delta
* A liquidity score
* A recommendation score

Quote validity is separate from liquidity filtering.

A pair that lacks the numeric quotes required to calculate an entry cost may be marked unrankable, but it must not silently alter the structural pairing rules.

⸻

5. Bull Call Spread

For a Bull Call Spread:

long strike < short strike

The system buys the lower-strike Call and sells the higher-strike Call.

Definitions:

spread_width = short_strike - long_strike

Executable quote estimates:

spread_ask = long_ask - short_bid
spread_mid = long_mid - short_mid
spread_bid = long_bid - short_ask

Each leg midpoint is:

mid = (bid + ask) / 2

Target payoff at expiry:

target_payoff =
min(
    max(target_price - long_strike, 0),
    spread_width
)

Maximum payoff:

max_payoff = spread_width

⸻

6. Bear Put Spread

For a Bear Put Spread:

long strike > short strike

The system buys the higher-strike Put and sells the lower-strike Put.

Definitions:

spread_width = long_strike - short_strike

Executable quote estimates:

spread_ask = long_ask - short_bid
spread_mid = long_mid - short_mid
spread_bid = long_bid - short_ask

Each leg midpoint is:

mid = (bid + ask) / 2

Target payoff at expiry:

target_payoff =
min(
    max(long_strike - target_price, 0),
    spread_width
)

Maximum payoff:

max_payoff = spread_width

⸻

7. Entry Cost and Return

Option quotes are expressed per share.

The displayed contract entry cost is:

entry_cost = spread_ask × 100

The primary ranking metric is Ask Return:

ask_return =
(target_payoff - spread_ask) / spread_ask

Percentage display:

ask_return_percent = ask_return × 100

Only rows with a finite and strictly positive spread_ask can receive an Ask Return ranking.

The system must not replace Ask Return with:

* Mid-price return
* Bid-price return
* Expected value
* Probability of profit
* A weighted score
* A Pareto score
* A resilience score
* A liquidity score

Bid and Mid values may be displayed for reference, but they do not control ranking.

⸻

8. Ranking Output

Each expiry has its own independent ranking table.

For every expiry:

1. Generate all structurally valid pairs.
2. Calculate spread quotes.
3. Calculate target payoff.
4. Calculate Ask Return for rankable rows.
5. Sort Ask Return from highest to lowest.
6. Return the first ten rows.

The system must not combine all expiries into one global Top 10.

Each expiry result must retain at least:

expiry
rank
strategy
long_strike
short_strike
long_bid
long_ask
short_bid
short_ask
spread_bid
spread_mid
spread_ask
entry_cost
spread_width
target_payoff
ask_return
long_iv
short_iv

The result must also retain:

total_pair_count
rankable_pair_count
data_source
fetched_at
is_historical

⸻

9. Market Data Boundary

The V2 core enumerator must not directly download market data.

Market-data responsibilities belong to a separate adapter or service layer.

Required market-data operations:

fetch_spot(symbol)
list_expiries(symbol)
fetch_expiry_chain(symbol, expiry, option_type)

The service layer is responsible for:

1. Reading the three user inputs.
2. Fetching spot price.
3. Inferring strategy direction.
4. Resolving five expiries.
5. Fetching only the required option chains.
6. Calling the pure enumerator once per expiry.
7. Returning five independent expiry results.

Every market-data response must identify:

source
fetched_at
is_historical

Fallback data sources are implemented later and must not change the core payoff or ranking formulas.

⸻

10. MVP V2 User Interface

The functional V2 interface will contain:

Symbol
Target Month
Target Price

The main result view will show:

* Automatically inferred direction
* Current spot price
* Up to five expiry tabs
* Total pair count for each expiry
* Rankable pair count
* Data source and timestamp
* Top 10 spreads for each expiry

Spread results are the primary output.

Single-leg Call or Put analysis is secondary and must not affect spread ranking.

Heatmaps, watchlists, saved snapshots, and iOS visual styling are later implementation stages.

⸻

11. Explicit Non-Goals

The first V2 implementation does not include:

* Legacy Delta grouping
* Legacy contract filters
* Open-interest thresholds
* Volume thresholds
* Bid-ask-width thresholds
* Global Top 3 recommendations
* Seven-scenario analysis
* Resilience scoring
* Pareto ranking
* Greeks-based ranking
* AI-generated recommendations
* Automatic position sizing
* Portfolio interaction analysis
* Watchlist persistence
* Scheduled snapshots
* iOS styling
* Removal of legacy files

These features must not be added incidentally while implementing the V2 core.

⸻

12. Implementation Discipline

MVP V2 is built as a separate path from the legacy application.

Rules:

1. Implement one micro-step per commit.
2. Do not modify unrelated legacy files.
3. Do not perform opportunistic refactoring.
4. Add deterministic unit tests for every formula and resolver.
5. Network access must not be required by core unit tests.
6. Use fixed fixtures for service and market-data tests.
7. Preserve the legacy application until V2 passes final acceptance.
8. Clean up legacy code only in the final dedicated cleanup stage.

This specification is authoritative for MVP V2 unless it is changed through a dedicated specification commit.