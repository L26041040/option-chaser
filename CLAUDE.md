# Option Chaser

## 1. Operating rules

1. GitHub issues are the canonical task/spec source. If this file conflicts with the latest issue body, follow the issue.
2. Work ticket-by-ticket. For each completed ticket: implement → tests → `/code-review` → fix findings → commit → push → update/close the issue as appropriate.
3. Do not open a PR until the active ticket series is complete or the Owner explicitly asks.
4. Do not touch `#269 / SCALE-18` unless the Owner explicitly authorizes it.
5. Do not expose, request, log, copy, or test real plaintext passwords/secrets.
6. Do not take or paste screenshots unless the Owner explicitly asks. Browser verification is allowed when required by a ticket, but keep screenshot-heavy work to explicit visual-acceptance stages.
7. Session reports: Traditional Chinese with English technical terms kept in English. Put substantive report content in one complete code block. Number reports as `［回報#NNN］`.
8. Current report sequence: **097 used; next report is 098**.
9. **Do not append detailed ticket history to this file.** Keep this file short. After a ticket, update only the active checkpoint below in 1–2 lines. Detailed evidence belongs in GitHub issues, commits, and code review comments.
10. `CLAUDE_HISTORY.md` is the archived legacy project journal. **Do not read it by default.** Read it only when a specific historical question cannot be answered from the current issue/commit/docs.

## 2. Current active project — Seed Warm UI

Mother issue: **#330** (SEED-WARM-SPEC-001)

Canonical visual spec (Direction A · Seed Warm evolved):
`https://claude.ai/artifact/TS2KZEjtYPkzGuYDTFd4HA`

Working branch:
`ui-redesign/seed-warm`

Goal:
Fully re-implement Option Chaser's visual language as Direction A ("Seed Warm evolved": warm paper background, white cards, single terracotta accent, pill shape language, Plus Jakarta Sans + Noto Sans TC) — a full reproduction, not a token-only reskin of Obsidian Gold. Light mode only (dark mode out of scope, see #330). Product semantics, permissions, and backend behavior unchanged; `#269 / SCALE-18` untouched.

Tickets (sub-issues of #330, expand→contract order): SW-01 #331 (Foundations) → SW-02 #332 (desktop chrome) ∥ SW-04 #333 (mobile library) → SW-03 #334 (desktop library) ∥ SW-06 #335 (mobile detail) ∥ SW-07 #336 (forms/settings/privacy/login/Super Admin) → SW-05 #337 (desktop detail) → SW-08 #338 (charts) → SW-09 #339 (contract + acceptance).

### Completed
- **OG-01–OG-12 (#317–#328)** — Obsidian Gold, fully superseded by Seed Warm. Archived detail: `CLAUDE_HISTORY.md` / closed issues.
- **SW-01 #331** — Foundations: Seed Warm token set (paper/card/ink/mute/accent/up/down/warn + text-safe `-text` variants, WCAG-checked), light-only (`prefers-color-scheme` branch removed, `color-scheme: light`), Plus Jakarta Sans + Noto Sans TC web fonts, new `.pbtn`/`.pnav`/`.pseg`/`.pchip`/`.ptag`/`.pcard`/`.pstat`/`.pinp`/`.pdot`/`.pbar`/`.pinfo` primitives, `InfoTooltip` shared component, terracotta `BrandMark`. Expand phase: old OG token *names* kept (repointed to Seed Warm values) so untouched screens don't break; structural/layout migration is SW-02 onward.
- **SW-02 #332** — Desktop chrome: `TopBar` on `.pnav`/`.pbtn` (current page via `aria-current="page"`, not a class), 64px→68px top bar (3 dependent sticky/fixed offsets updated), pill role badge, Settings subnav (`.settings-subnav`) pill-ified scoped to that surface only (shared `.chip` untouched). Footer already satisfied SW-02's AC via SW-01's token expand alone.
- **SW-04 #333** — Mobile library: single "＋ 建立劇本" entry in a new title row (`.mobile-home-head`), replacing `Dashboard.tsx` (deleted, "跨劇本指標規劃中" placeholder gone) and `CreateEntry.tsx` (deleted; its always-mounted-hidden-panel mechanism moved inline into `App.tsx`). `BottomNav` down to 3 tabs (no `create`); `openCreateFromAnywhere` removed since there's no longer a cross-screen create shortcut — this is a disclosed, deliberate one-more-tap trade-off, not an oversight. `BetaNotice` stays persistently visible (PB-12/#302 AC9 is a hard requirement — a hover/focus tooltip would violate it; SEED-WARM-SPEC-001's "downgrade to tooltip" language doesn't apply here). New `MobileStatsStrip` (3 real `usage-summary` fields only — a "best return" 4th stat was tried and reverted: it duplicated the exact percentage text already on a scenario card, causing `getByText` collisions across ~8 unrelated existing e2e tests; SW-03 should avoid the same trap). `.mnav` 52px→60px. `CompactScenarioList`'s cards now share one `.pcard` (hairline-divided rows, not individually bordered).
- **SW-03 #334** — Desktop library: title 32px/800 + subtitle (count + last batch-update time, derived client-side like SW-04); refresh button on `.pbtn`; `.seg` filter pills upgraded to `var(--radius-pill)` globally (safe — pure shape, shared by 4 consumers, no DOM/text change). Table 11 cols → 9: 現價/目標價 merged into `.lib-cell-price` ("現價 → 目標價" + "還需 ±x%"), 更新時間 merged into `.lib-cell-status` (dot + visible status text, kept the `title` attr too for back-compat) — both keep separate text nodes per sub-value so exact-text test queries still resolve. Expired rows now dim (`.compact-card.expired`, opacity 0.5, mutually exclusive with `.locked`/`.failed` per existing `cardFailureVariant` guard). Empty-state copy fixed (pointed at the top-right CTA, not the no-longer-adjacent form). Vendor-fuse/429 stat block moved out of the library entirely into `SuperUserAdmin.tsx`'s existing `OpsStats()` (reuses its existing `getOpsMetrics()` call — zero new request); library page now issues zero `/api/ops/metrics` requests for any role. Skipped as redundant: a title-side info tooltip repeating Beta/retention facts (BetaNotice already renders those persistently on desktop, per OG-02) and moving the "worst-fill/non-advice/privacy" footer line into an always-visible bottom bar (already surfaced via the page's persistent `Footer` + existing header caption; not worth restructuring `selectMode`'s conditional batch-bar for a text relocation).
- **SW-06 #335** — Mobile detail page: new 60px `.detail-bar` header (back/symbol/refresh; mobile only, structurally disjoint from desktop's `.toolbar` — no shared JSX/class) and new `MobileHero` white card (logo+symbol+direction pill, champion return + family subtitle, "目標 X · 目標月", 4-stat grid reusing existing fields — `days_to_anchor`/`formatDaysLeft()` for "距目標", nothing re-derived). Wording: `CandidatePool.tsx`'s shared "候選池"→"候選策略" and mobile `EntryPanel`'s "最差成交口徑"→"以最差成交價計算" (both required matching test/e2e string updates, including on the desktop bottom-tab that also renders the shared `CandidatePool` component — disclosed, not SW-05 scope creep since it's one shared component with one heading). `FamilyTabs` champion badge is `aria-hidden` (avoids breaking `getByRole` name-based assertions). Chip pill-shape + badge-positioning CSS is scoped to `@media (max-width: 1099px) { .detail-page .chip }` specifically to avoid leaking into desktop `DesktopDetail.tsx`'s and `Settings.tsx`'s shared `.chip` usage before SW-05/SW-07 run (caught by `/code-review` Spec axis). Extracted a shared `DirectionTag` sub-component (desktop identity row + new mobile hero) per `/code-review` Standards axis duplicate-code finding. Disclosed gaps (no data source / no defined action, not implemented): header "公司名" and "更多" menu. Zero backend/API changes.

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
