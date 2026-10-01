# Option Chaser

## 1. Operating rules

1. GitHub issues are the canonical task/spec source. If this file conflicts with the latest issue body, follow the issue.
2. Work ticket-by-ticket. For each completed ticket: implement → tests → `/code-review` → fix findings → commit → push → update/close the issue as appropriate.
3. Do not open a PR until the active ticket series is complete or the Owner explicitly asks.
4. Do not touch `#269 / SCALE-18` unless the Owner explicitly authorizes it.
5. Do not expose, request, log, copy, or test real plaintext passwords/secrets.
6. Do not take or paste screenshots unless the Owner explicitly asks. Browser verification is allowed when required by a ticket, but keep screenshot-heavy work to explicit visual-acceptance stages.
7. Session reports: Traditional Chinese with English technical terms kept in English. Put substantive report content in one complete code block. Number reports as `［回報#NNN］`.
   All times in reports use **Taiwan time (Asia/Taipei, UTC+8)**, written like `2026-09-27 22:09 (台灣)`; convert any UTC timestamp from tools/APIs before reporting.
8. Current report sequence: **127 used; next report is 128**.
9. **Do not append detailed ticket history to this file.** Keep this file short. After a ticket, update only the active checkpoint below in 1–2 lines. Detailed evidence belongs in GitHub issues, commits, and code review comments.
10. `CLAUDE_HISTORY.md` is the archived legacy project journal. **Do not read it by default.** Read it only when a specific historical question cannot be answered from the current issue/commit/docs.

## 2. Current active project — Seed Warm UI

**Status: complete, including SW-10/SW-11/SW-12 real-device acceptance
and final cleanup rounds.** SW-01–SW-09 (#331–#339, mother issue
**#330** SEED-WARM-SPEC-001), SW-10 (#340), SW-11 (#341), and SW-12
(#342, final cleanup: ⚠️/🚩 user-UI removed entirely, Spread net-cost
history feature fully retired — UI/API/write-path/tests, Heatmap/
Crossover explanation collapsed to one sentence + ⓘ, desktop normal
signal-dot removed) all implemented, tested, code-reviewed, and pushed
to `ui-redesign/seed-warm`. Full detail: closed issues #331-#342. Per
rule 3, **no PR opened** — waiting on Owner real-device acceptance
before cue to open one. Two open items still need Owner action outside
this repo (unchanged since SW-11): (1) from SW-10 #340, confirm
`SUPERUSER_PASSWORD`/`SUPERADMIN_PASSWORD` are scoped to the Preview
environment in Vercel's project settings (see `docs/deploy-vercel.md`),
not just Production; (2) from SW-11 #341, desktop `ScenarioList.tsx`'s
normal-state signal-dot has since also been removed in SW-12 #342, so
this item is now resolved.

ARCH-REVIEW-001 (#343) followed: a five-track architecture health check
of the finished branch. Three tracks returned "no material finding" and
were left alone; fixed only a stale-detail-cache bug after edit, an
archived-edit lifecycle gap, a `request_scope` Protocol leak, table-list
drift guards, and dead symbols/docs (commit `a039a85`). Its one open
item is closed: the Owner dropped the Production `narrow_history` table
(LEGACY-CLEANUP-003).

PR #344 (`ui-redesign/seed-warm` → master) is open; post-review fixes
pushed to it: AUTH-P1-FIX-001 (`8fdc1e3`) and SW-13 usage-summary
refresh (shared `src/usageSummaryStore.ts`). Do not merge without Owner.

DB-LIFECYCLE-AUDIT-001 (audit only): `docs/audits/db-lifecycle-audit-2026-09.md`. Its P1s are implemented by
CLAUDE-DB-HYGIENE-002/003 (PR #347, merged `68d8e30`). **Production rescue done 2026-09-28 (台灣)** by HYGIENE-008's temporary cold-start hook (PR #348, removed by the follow-up cleanup PR): target 18 scenarios / 14 active, NULL + solo = 0, retired tables dropped, all invariants pass. AUTH-07 data migration is therefore complete.

CLAUDE-SETTINGS-ROLE-IA-001: role-aware Settings — Normal sees only Delete / Disclaimer / Login (bottom); SU unchanged; SA gets an entry to the standalone Admin page `#/admin` (`src/AdminPage.tsx`, mounts existing `SuperUserAdmin`, redirects non-SA to `#/settings`).

CLAUDE-BETA-LAUNCH-FINAL-001: `#/admin` Beta Reset (type `Reset`) + select-all batch delete (protected refused); Normal feedback → SA inbox; SU manages its own credentials; `/clear` hook never strands archives on dead branches (recovers them instead).

CLAUDE-MOBILE-CARD-OVERLAP-001: mobile card strategy pill moved to its own `.compact-strategy-row` (no longer overlays Exp); tests freeze `ny_today()` via `tests/conftest.py` + `tests/_frozen_clock.py`.

CLAUDE-MOBILE-CARD-VERTICAL-ROWS-001: mobile card is one-row-per-item (main row → `.compact-price-row` → `.compact-target-time-row` → left-aligned `.compact-strategy-row` → Exp), normal font sizes; PR #353's `useFitText` auto-fit was removed.

Public Beta security hardening: PR #346 (`security/public-beta-hardening`)
covers #345 A-1–A-4 and B-1–B-7 — merged.

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

**AUTH-07 #314** data migration is **done** (2026-09-28, 台灣): the Owner's
production identity exists, its `owner_id` was identified, and the canonical
rescue (PB-03 solo migration + NULL-owner lineage) ran in Production via
HYGIENE-008 (dry-run reviewed → executed → post-run plan all zero). Do not
rerun it. The only remaining AUTH-07 item is Owner-only: real-password SU/SA
boundary checks.

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
- Visual truth: Seed Warm Direction A artifact (`https://claude.ai/artifact/TS2KZEjtYPkzGuYDTFd4HA`), superseding the retired Obsidian Gold artifact.
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
