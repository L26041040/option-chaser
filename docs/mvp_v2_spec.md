Option Chaser MVP V2 Specification

Status: FROZEN FOR IMPLEMENTATION
Version: MVP V2
Branch: feature/mvp-v2-simplification

⸻

1. Product Goal

Option Chaser MVP V2 accepts a simple market scenario and enumerates option debit spreads that could benefit if the scenario occurs.

The user provides only:

1. Symbol
2. Target month
3. Target price

The system automatically determines the trade direction, selects up to the configured number of relevant expiries, enumerates every valid spread pair within each expiry, and ranks the results by return calculated from the executable Ask-side entry cost.

MVP V2 prioritizes:

* Complete enumeration
* Transparent formulas
* Independent ranking for each expiry
* Minimal user input
* Reproducible results
* Explicit system settings
* Deterministic core behavior

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

3. System Settings Boundary

MVP V2 contains explicit system settings that control configurable output limits without changing the core financial formulas.

The initial settings are:

max_expiries = 5
top_spreads_per_expiry = 10

These values are defaults rather than permanent product limits.

The settings architecture must follow these rules:

1. Core functions must not directly read UI state.
2. Core functions must not directly read mutable global settings.
3. The UI or application layer creates or loads the settings.
4. The service layer passes the required setting values into the core functions.
5. Core functions remain deterministic for identical arguments.
6. Unit tests may provide explicit non-default setting values.
7. Changing a display or selection limit must not change structural pairing rules.
8. Changing a display or selection limit must not change quote formulas.
9. Changing a display or selection limit must not change payoff formulas.
10. Changing a display or selection limit must not change return formulas.

The initial settings model contains:

V2Settings
├─ max_expiries
└─ top_spreads_per_expiry

The initial default values are:

V2Settings(
    max_expiries=5,
    top_spreads_per_expiry=10,
)

Both values must be positive integers.

The settings interface may later be exposed through a gear icon or other application settings page.

Settings persistence and settings UI are later implementation stages.

⸻

4. Expiry Selection

The system retrieves the actual expiries available for the symbol.

It then selects no more than:

max_expiries

actual expiries surrounding the requested target month.

The default value is:

max_expiries = 5

The selection process is:

1. Resolve one actual expiry as the target-month baseline.
2. Include the baseline.
3. Divide the remaining preferred slots around the baseline.
4. Prefer the nearest expiries on each side.
5. When the configured limit is odd, distribute the remaining slots evenly around the baseline.
6. When the configured limit is even, give the later side the additional preferred slot.
7. If one side has insufficient expiries, fill the unused capacity from the other side.
8. Return no duplicate expiries.
9. Return expiries in chronological order.
10. Never return more than max_expiries.
11. If fewer actual expiries exist, return all available valid expiries.

Examples:

max_expiries = 5
→ baseline + up to 2 before + up to 2 after
max_expiries = 7
→ baseline + up to 3 before + up to 3 after
max_expiries = 4
→ baseline + up to 1 before + up to 2 after

The exact deterministic baseline and tie-breaking algorithm must be implemented and tested in the dedicated expiry resolver.

The target-month reference date is the third Friday of the requested month.

The actual available expiry nearest to that reference date becomes the baseline.

If two actual expiries are equally distant from the reference date, the later expiry becomes the baseline.

The system must not invent expiry dates.

Each selected expiry is analyzed independently.

⸻

5. Core Enumeration

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

Duplicate strikes inside one expiry chain are invalid because one structural strike pair must map to one unambiguous pair of contracts.

⸻

6. Bull Call Spread

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

7. Bear Put Spread

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

8. Pricing Architecture

Pricing responsibilities must be separated into three deterministic layers.

8.1 Quote Engine

The Quote Engine calculates market-quote-derived values only.

It may calculate:

long_mid
short_mid
spread_bid
spread_mid
spread_ask

It must not calculate:

* Spread payoff
* Target payoff
* Maximum payoff
* Entry cost
* Return
* Ranking

If a necessary quote is unavailable, the corresponding derived quote is unavailable.

Missing values must not be silently replaced with zero.

Quote validity must not alter the structural spread pairs produced by the enumerator.

8.2 Payoff Engine

The Payoff Engine calculates strategy payoff values only.

It receives values such as:

strategy
long_strike
short_strike
target_price

It must not require:

* Bid
* Ask
* Mid
* Implied volatility
* Open interest
* Volume

The Payoff Engine may calculate:

spread_width
target_payoff
max_payoff

8.3 Return Engine

The Return Engine combines quote-derived values with payoff-derived values.

It may calculate:

entry_cost
ask_return
ask_return_percent
rankable

It must not perform ranking or truncate the result collection.

The intended dependency flow is:

SpreadPair
↓
Quote Engine
↓
Payoff Engine
↓
Return Engine
↓
Ranking Engine

These responsibilities must not be merged into one function merely for convenience.

⸻

9. Entry Cost and Return

Option quotes are expressed per share.

The standard option contract multiplier is initially:

contract_multiplier = 100

The multiplier must be passed explicitly or use a deterministic default.

It must not be inferred from UI state inside the core calculation.

The displayed contract entry cost is:

entry_cost = spread_ask × contract_multiplier

The primary ranking metric is Ask Return:

ask_return =
(target_payoff - spread_ask) / spread_ask

Percentage display:

ask_return_percent = ask_return × 100

Only rows with a finite and strictly positive spread_ask can receive an Ask Return ranking.

A spread is unrankable when spread_ask is:

* Missing
* Non-finite
* Zero
* Negative

An unrankable spread remains part of the complete structural enumeration count.

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

10. Ranking Output

Each expiry has its own independent ranking table.

For every expiry:

1. Generate all structurally valid pairs.
2. Calculate spread quotes.
3. Calculate target payoff.
4. Calculate Ask Return for rankable rows.
5. Sort Ask Return from highest to lowest.
6. Apply deterministic tie-breaking.
7. Return no more than:

top_spreads_per_expiry

    ranked rows.

The default value is:

top_spreads_per_expiry = 10

If fewer rankable rows exist, return all rankable rows.

The system must not combine all expiries into one global ranking table.

The configured row limit changes only the number of ranked rows returned.

It must not change:

* Total structural pair count
* Rankable pair count
* Pair construction
* Quote calculations
* Payoff calculations
* Return calculations

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

11. Market Data Boundary

The V2 core enumerator and pricing functions must not directly download market data.

Market-data responsibilities belong to a separate adapter or service layer.

Required market-data operations:

fetch_spot(symbol)
list_expiries(symbol)
fetch_expiry_chain(symbol, expiry, option_type)

The service layer is responsible for:

1. Reading the three user inputs.
2. Loading or receiving V2Settings.
3. Fetching spot price.
4. Inferring strategy direction.
5. Resolving up to settings.max_expiries expiries.
6. Fetching only the required option chains.
7. Calling the pure core analysis once per expiry.
8. Ranking up to settings.top_spreads_per_expiry rows per expiry.
9. Returning independent expiry results.

Every market-data response must identify:

source
fetched_at
is_historical

Fallback data sources are implemented later and must not change the core pairing, quote, payoff, return, or ranking formulas.

⸻

12. MVP V2 User Interface

The functional V2 interface will contain:

Symbol
Target Month
Target Price

The main result view will show:

* Automatically inferred direction
* Current spot price
* Up to settings.max_expiries expiry tabs
* Total pair count for each expiry
* Rankable pair count
* Data source and timestamp
* Up to settings.top_spreads_per_expiry ranked spreads for each expiry

With default settings, this means:

Up to 5 expiry tabs
Up to 10 ranked spreads per expiry

Spread results are the primary output.

Single-leg Call or Put analysis is secondary and must not affect spread ranking.

A later settings interface may allow the user to change:

Max expiries
Rows per expiry

The settings interface must create or update a validated settings object.

It must not directly modify the internal state of core calculation modules.

Heatmaps, watchlists, saved snapshots, settings persistence, and iOS visual styling are later implementation stages.

⸻

13. Explicit Non-Goals

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
* Settings persistence
* Full settings UI
* iOS styling
* Removal of legacy files
* Generic strategy plug-in framework
* Multi-leg strategies beyond the initial debit spreads

These features must not be added incidentally while implementing the V2 core.

The initial architecture may preserve clean boundaries for later strategy expansion, but it must not prematurely implement an abstract strategy framework.

⸻

14. Implementation Discipline

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
9. Keep quote, payoff, return, and ranking responsibilities separated.
10. Do not make core functions depend directly on mutable global settings.
11. Do not allow output limits to change underlying financial calculations.
12. Do not add new strategies while constructing the initial pricing foundation.
13. Public compatibility imports must remain stable unless changed in a dedicated migration.
14. Every configurable limit must be validated and explicitly passed through the application or service boundary.

This specification is authoritative for MVP V2 unless it is changed through a dedicated specification commit.