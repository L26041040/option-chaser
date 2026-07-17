# Option Chaser

Long Call scenario optimizer. Given YOUR scenario (target price + target date),
it scans the current option chain, filters for tradeability, valuates every
qualifying Long Call with Black-Scholes under your scenario, bands candidates
by Delta (conservative / balanced / aggressive), and prints a deterministic
plain-text report with price-ceiling guidance.

It does NOT predict stocks, judge your scenario, estimate probabilities, or
give investment advice. Same snapshot + same params = byte-identical output.

## Install

    pip install -e .

## Run (online; saves a snapshot under snapshots/)

    option-chaser NVDA --target-price 220 --target-date 2026-09-30 --min-days-after 45

## Re-run offline from a snapshot

    option-chaser NVDA --target-price 220 --target-date 2026-09-30 \
        --min-days-after 45 --snapshot snapshots/NVDA_xxxx.json

## Key flags

    --min-days-after N    expiry must be >= target-date + N days (hard gate)
    --min-expiry DATE     absolute expiry floor
    --iv-shifts CSV       IV scenarios, default -0.2,0,0.2 (0 always included)
    --min-return X        L3 price ceiling = baseline value / (1+X)
    --max-spread-pct / --spread-floor / --min-oi / --min-volume   tradeability gates
    --delta-bands A,B     banding thresholds, default 0.35,0.65
    --md PATH             also write the report to a file

## Tests (all offline)

    python -m pytest

Spec: docs/superpowers/specs/2026-07-15-option-chaser-mvp-design.md
