# Option Chaser

## 1. Operating rules

1. GitHub issues are the canonical task/spec source. If this file conflicts with the latest issue body, follow the issue.
2. Work ticket-by-ticket. For each completed ticket: implement → tests → `/code-review` → fix findings → commit → push → update/close the issue as appropriate.
3. Do not open a PR until the active ticket series is complete or the Owner explicitly asks.
4. Do not touch `#269 / SCALE-18` unless the Owner explicitly authorizes it.
5. Do not expose, request, log, copy, or test real plaintext passwords/secrets.
6. Do not take or paste screenshots unless the Owner explicitly asks. Browser verification is allowed when required by a ticket, but keep screenshot-heavy work to explicit visual-acceptance stages.
7. Session reports: Traditional Chinese with English technical terms kept in English. Put substantive report content in one complete code block. Number reports as `［回報#NNN］`.
8. Current report sequence: **096 used; next report is 097**.
9. **Do not append detailed ticket history to this file.** Keep this file short. After a ticket, update only the active checkpoint below in 1–2 lines. Detailed evidence belongs in GitHub issues, commits, and code review comments.
10. `CLAUDE_HISTORY.md` is the archived legacy project journal. **Do not read it by default.** Read it only when a specific historical question cannot be answered from the current issue/commit/docs.

## 2. Current active project — Obsidian Gold UI

Mother issue: **#316**

Canonical visual spec:
`https://claude.ai/artifact/28tqiXF2o9UyQK6vDUXf5q`

Working branch:
`ui-redesign/graphite-amber`

Goal:
Implement the approved **Obsidian Gold** Binance-inspired visual design without changing product semantics.

### Completed
- **OG-01 #317** — Foundations: Obsidian Gold tokens, Geist + Noto Sans TC, shared primitives, StockLogo contract.
- **OG-02 #318** — Desktop chrome: 64px top bar, page-level navigation, full-width desktop shell.
- **OG-09 #319** — Mobile scenario library: 52px mobile top bar, dense rows, persistent bottom navigation.
- **OG-03 #320** — Desktop Markets-style scenario table + trash-page table skin (code-review follow-up) + required-move sub-text.
- **OG-06 #321** — Desktop detail page part I: 3-column shell, identity row, family/expiry/ranking table, Heatmap-follows-selection, PriceLadder. Right column + bottom tabs left as empty containers for OG-07.
- **OG-11 #322** — Settings subnav (desktop) / Super Admin backdoor (ops-metrics stats, owner status filter, type-to-confirm delete modals).
- **OG-07 #325** — desktop detail part II: right-column candidate panel (Entry/Payoff/Greeks/Report tabs, follows ranking-row selection) + bottom 4 tabs (cost history/pool diagnostics/analysis report/raw data). AnalysisReport renders exactly once (bottom tab, test-locked); right "Report" tab is a teaser + disclaimer + jump link. Desktop-only single-leg cost-history support added (frontend-only relaxation).
- **OG-04 #323** — scenario-list cost sparkline (the approved additive backend field). New `Storage.cost_sparklines()` batched query (VALUES+LATERAL, memory+Postgres contract tests, structural "no results.view" test, 100-row latency benchmark proving no N+1). `representative_candidate` projection gained a `candidate_key` field (needed to look up narrow history at list-time). Desktop-only `CostSparkline.tsx` hand-rolled SVG, green/red by direction, gap-broken. Mobile untouched.
- **OG-05 #324** — read-only `GET /api/me/usage-summary` (active scenarios/quota/AUTH-05 exemption/last activity/throttle interval, sourced from the same closure variables the create/refresh gates use, never touches `last_activity_at`) + desktop-only stats strip in `ScenarioList.tsx` (`UsageStatsStrip`, role via `useAuthRole()`). Super-Admin-only extra blocks (`OpsSuperAdminStats`) read the existing `/api/ops/metrics`, which gained one additive `vendor_fuse: {used, budget}` field; conditionally mounted so non-Super-Admin issues zero ops-metrics requests. Mobile untouched.
- **OG-08 #326** — desktop right column shows `<IvHistory>` (unmodified, self-gating, existing content) instead of `<CandidatePanel>` when the ranking table's *selected* candidate (not the cross-family champion — deliberate, documented, test-locked interpretation for internal consistency with OG-07's "right column follows selection" convention) is single-leg + role ≥ Super User + feature enabled. Gate logic (`useIvHistoryAccess()`/`supportsIvHistory()`/`isSuperUserRole()`) extracted from `IvHistory.tsx` as named exports so both consumers share one source of truth. Old global full-width mount now `!isDesktop`-gated (mobile-only); mobile behavior unchanged. Zero backend/API changes.

### Current frontier
Unblocked next (OG-08 done; #319/#321/#325/#326 all complete):
- **OG-10 #327** — mobile detail. Then:
- **OG-12 #328** — final light/responsive/artifact parity/regression acceptance.

Do not redesign the approved artifact. Implementation questions should be resolved from the artifact + current issue body unless a true HITL decision is required.

## 3. Product semantics that must not drift during OG work

Visual work must not change:
- Scenario creation, ownership, archive/restore/delete semantics.
- The existing refresh triggers.
- Candidate generation, valuation, ranking, family eligibility/selection behavior.
- The rule that headline/champion semantics stay fixed where the tickets specify it.
- Historical IV engine, gating, and its removal/non-rendering scope for unsupported strategy shapes.
- Normal / Super User / Super Admin permission matrix.
- quota, refresh throttle, global vendor fuse.
- credential handling.
- PB-03 migration semantics.
- Existing API contracts, except the two explicitly approved additive OG endpoints/fields in #323 and #324.

Logo policy:
- Real company/ETF logos only.
- Logo.dev ticker endpoint with `fallback=404`.
- If unavailable, show no logo.
- Never substitute initials, monograms, generic stock icons, favicon guesses, or AI-generated logos.

## 4. Separate unresolved AUTH checkpoint

AUTH-01–06 are already merged to master and deployed.

**AUTH-07 #314** remains blocked on real Owner HITL:
- Owner browser identity must exist in production.
- Owner must identify the real production `owner_id`.
- PB-03 migration must be run against production `DATABASE_URL` (dry-run → confirm → idempotency rerun).
- Real-password SU/SA boundary checks are Owner-only.

This does not block Obsidian Gold UI implementation.

## 5. Testing / verification

Frontend:
```bash
npm install
npm run typecheck
npm test
npm run build
PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium npm run e2e
```

Backend full suite requires the real Postgres test backend when backend code is touched:
```bash
OC_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:55432/octest" \
PYTHONPATH=. .venv/bin/python -m pytest
```

Environment bootstrap if needed:
```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[api,yf]" pytest
```

If local Postgres is missing, use `scripts/dev_env.sh` first. Do not silently accept a test run that skipped the Postgres contract half when a backend ticket requires it.

## 6. Canonical references

Use the narrowest source needed; do not preload the project history.

- Active work/spec: latest GitHub issue body under #316 / child ticket.
- Visual truth: Obsidian Gold artifact above.
- Code truth: current branch + tests.
- Deployment instructions: `docs/deploy-vercel.md`.
- Older requirement history only if specifically needed: relevant `docs/` file or GitHub issue/commit.
- Legacy long journal: `CLAUDE_HISTORY.md` (read on demand only).

## 7. Session/context hygiene

- Do not read every OG issue up front; read only the current ticket and direct dependencies.
- Do not read `CLAUDE_HISTORY.md` during normal implementation.
- Do not paste full test logs or huge diffs back into context unless diagnosing a failure.
- Prefer targeted file reads/searches over dumping whole large files.
- If context starts degrading, finish the current coherent checkpoint, commit/push it, leave a concise issue checkpoint, and start a fresh session.
- `/clear` is not a substitute for keeping bootstrap context small; this file is intentionally kept compact for that reason.
