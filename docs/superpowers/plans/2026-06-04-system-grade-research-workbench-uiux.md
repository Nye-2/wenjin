# System-Grade Research Workbench UIUX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Roll out the approved System-Grade Research Workbench visual baseline across Wenjin without changing backend contracts or workflow behavior.

**Architecture:** Converge visual tokens and shared primitives first, then migrate page templates in dependency order. Workbench remains the product anchor: chat stays quiet, execution/review/evidence surfaces carry state, and team real-name agents become a responsibility surface rather than decorative personas.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind utilities, Zustand, existing Wenjin API/projection contracts.

---

## File Structure

- Modify `frontend/app/globals.css`: define final `--wjn-*` system tokens, remap old aliases, remove decorative global behavior from default utilities.
- Modify `frontend/components/ui/button.tsx`: replace brand/teal gradient button defaults with system-grade navy/blue variants.
- Modify `frontend/components/ui/card.tsx`: make cards white, hairline, low-shadow by default.
- Modify `frontend/components/ui/badge.tsx`: align semantic chips to evidence/review/success/error tokens.
- Modify `frontend/components/layout/header.tsx`: upgrade public trusted chrome and logo treatment.
- Modify `frontend/components/workspace/WorkspaceSurfaceState.tsx`: remove old v2 gradient/glass empty/loading surface.
- Modify `frontend/components/auth/auth-shell.tsx`: remove old route-grid/orb/glass shell and migrate to institutional entry template.
- Modify `frontend/app/workspaces/page.tsx`: replace LiquidGlassCard and old route-card styling with workspace path/list cards.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`: strengthen trusted chrome and workspace identity.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/RoomsTopbar.tsx`: make rooms a compact system command/navigation rail.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`: update execution board, team roster, review/evidence panels to system-grade styling.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`: rename/reframe team panel as research team responsibility surface.
- Modify `frontend/components/prism/PrismReviewList.tsx` and selected `frontend/components/latex/latex-editor/*.tsx`: replace purple Prism accents with review/evidence tokens.
- Modify admin dashboard pages under `frontend/app/dashboard/admin/**`: align route cards and metric panels with admin console template.
- Modify docs:
  - `docs/current/wenjin-research-navigation-uiux.md`
  - `docs/current/documentation-map.md`

## Task 1: Token Convergence

**Files:**
- Modify: `frontend/app/globals.css`
- Test: `frontend/app/globals.css` color scan via `rg`

- [ ] **Step 1: Snapshot existing visual debt**

Run:

```bash
rg -n -g '*.tsx' -g '*.ts' -g '*.css' -- "--brand-|--compute-|--glass-|--v2-orb|--v2-bg-gradient|LiquidGlassCard|purple|rounded-2xl" frontend/app frontend/components frontend/lib
```

Expected: output lists legacy hotspots. Keep the list for migration validation.

- [ ] **Step 2: Rewrite `:root` token block**

Replace the multi-system root token section with a single `--wjn-*` system plus compatibility aliases. The new token block must include these values:

```css
--wjn-navy: #0f1f35;
--wjn-blue: #2c5da0;
--wjn-blue-strong: #234c87;
--wjn-gold: #e7b008;
--wjn-bg-base: #f5f7fa;
--wjn-bg-rail: #f8fafc;
--wjn-surface: #ffffff;
--wjn-surface-raised: rgba(255, 255, 255, 0.88);
--wjn-surface-subtle: #f1f5f9;
--wjn-line: rgba(15, 31, 53, 0.09);
--wjn-line-strong: rgba(15, 31, 53, 0.14);
--wjn-text: #0f1f35;
--wjn-text-secondary: rgba(15, 31, 53, 0.68);
--wjn-text-muted: rgba(15, 31, 53, 0.46);
--wjn-accent: var(--wjn-blue);
--wjn-accent-strong: var(--wjn-blue-strong);
--wjn-accent-soft: rgba(44, 93, 160, 0.10);
--wjn-accent-line: rgba(44, 93, 160, 0.24);
--wjn-evidence: #0f766e;
--wjn-evidence-soft: rgba(15, 118, 110, 0.10);
--wjn-review: #b45309;
--wjn-review-soft: rgba(180, 83, 9, 0.10);
--wjn-success: #15803d;
--wjn-error: #b91c1c;
--wjn-shadow-sm: 0 1px 2px rgba(12, 22, 36, 0.04);
--wjn-shadow-md: 0 12px 34px rgba(12, 22, 36, 0.07);
--wjn-shadow-lg: 0 24px 70px rgba(12, 22, 36, 0.13);
--wjn-radius: 8px;
--wjn-radius-md: 10px;
--wjn-radius-lg: 14px;
--wjn-radius-xl: 16px;
--wjn-duration-fast: 150ms;
--wjn-duration-medium: 220ms;
--wjn-ease-standard: cubic-bezier(0.2, 0.7, 0.3, 1);
```

Compatibility aliases must map `--accent-primary`, `--accent-secondary`, `--border-default`, `--bg-base`, `--bg-elevated`, `--text-primary`, `--text-secondary`, `--v2-accent-purple-*`, and `--glass-*` to system-grade values so old components do not break while being migrated.

- [ ] **Step 3: Replace decorative global utilities**

Update `.wjn-shell-bg`, `.route-card`, `.route-card-hover`, `.glass-card`, `.glass-card-elevated`, `.gradient-text-subtle`, `.badge-premium`, `:focus-visible`, scrollbar, selection, and text area styles to use `--wjn-*`.

Concrete rules:

- `.glass-card` becomes a white raised card alias, not translucent glass.
- `.route-card` becomes white/raised institutional card, not paper/tan.
- `.route-grid`, `.route-topography`, `.atmosphere-mesh`, `.hero-glow` must be visually subdued or unused by migrated pages.
- `:focus-visible` uses `var(--wjn-blue)`.

- [ ] **Step 4: Run token scan**

Run:

```bash
rg -n -- "--wjn-navy|--wjn-blue|--brand-|--compute-|--glass-|--v2-orb|--v2-bg-gradient" frontend/app/globals.css
```

Expected: `--wjn-*` values and compatibility aliases remain; decorative orb tokens are absent from active styling.

## Task 2: Shared UI Primitives

**Files:**
- Modify: `frontend/components/ui/button.tsx`
- Modify: `frontend/components/ui/card.tsx`
- Modify: `frontend/components/ui/badge.tsx`
- Modify: `frontend/components/workspace/WorkspaceSurfaceState.tsx`
- Test: `cd frontend && npm run typecheck`

- [ ] **Step 1: Update button variants**

Change default button to solid navy, outline to white hairline, secondary to accent-soft, ghost to quiet hover, and link to blue. Default button must not use `bg-gradient-to-r`.

Required default variant class:

```ts
"bg-[var(--wjn-navy)] text-white shadow-[0_8px_20px_rgba(15,31,53,0.16)] hover:bg-[var(--wjn-blue-strong)] active:translate-y-0"
```

- [ ] **Step 2: Update card primitive**

Use:

```ts
"rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)]"
```

Card footer border uses `--wjn-line`.

- [ ] **Step 3: Update badge semantic variants**

Map variants:

- `default`: blue accent.
- `secondary`: neutral.
- `success`: evidence/success.
- `warning`: review.
- `destructive`: error.
- `outline`: neutral hairline.

- [ ] **Step 4: Update WorkspaceSurfaceState**

Remove `var(--v2-bg-gradient)`, `var(--v2-glass-*)`, and purple accent classes. Use `wjn-shell-bg`, white card, and evidence/review/error tones.

- [ ] **Step 5: Typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS. Fix class or typing errors before moving on.

## Task 3: Entry Surfaces

**Files:**
- Modify: `frontend/components/layout/header.tsx`
- Modify: `frontend/components/auth/auth-shell.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/workspaces/page.tsx`
- Modify: `frontend/components/academic/workspace-card.tsx`
- Test: `cd frontend && npm run typecheck`

- [ ] **Step 1: Header trusted chrome**

Update header to use:

- translucent white topbar.
- logo tile with navy/blue material gradient.
- no scale animation larger than existing subtle translate/hover.
- primary auth CTA with solid navy.
- secondary auth CTA as quiet text/outline.

- [ ] **Step 2: Auth shell**

Remove route-grid/orb background and paper/tan shell. Use two-column institutional layout:

- left side: product highlights in white cards.
- right side: auth form card.
- no `rounded-[2rem]` default card shape.
- no `var(--brand-*)` usage in migrated markup.

- [ ] **Step 3: Workspace list**

Remove `LiquidGlassCard` import and route-card dependency from workspace list. Workspace cards become path/list cards:

- white card.
- 14px radius.
- type chip uses `--wjn-blue`, `--wjn-evidence`, `--wjn-review`, neutral.
- latest/recommended uses `--wjn-gold` only as text/border, not large fill.

- [ ] **Step 4: Landing smoke check**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS.

## Task 4: Workbench Shell and Command Layer

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/RoomsTopbar.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Test: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`

- [ ] **Step 1: SurfaceSwitch becomes system chrome**

Use SurfaceSwitch as the top trusted chrome:

- logo + Wenjin.
- workspace id.
- Workbench/Prism tabs.
- Prism review badge.
- visual language from spec: white translucent shell, navy identity, hairline borders.

- [ ] **Step 2: RoomsTopbar becomes compact navigation rail**

Use concise room chips. Running/completed run badges use `--wjn-blue` and `--wjn-success`.

- [ ] **Step 3: Add command bar affordance**

Add a non-invasive command bar visual control in the workbench shell:

- label: `启动任务、查找资料或召集团队...`
- shortcut hint: `⌘K`
- no behavior change in this phase unless an existing command palette hook is already wired.

- [ ] **Step 4: Run panel unit tests**

Run:

```bash
cd frontend && npx vitest run tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected: PASS.

## Task 5: Team Agent Responsibility Surface

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/styles.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/utils.ts`
- Test: `frontend/tests/unit/lib/execution-run-view.test.ts`
- Test: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`

- [ ] **Step 1: Reframe copy**

Rename visible team panel title from `执行团队` to `研究团队` or `执行委员会`. Keep `aria-label="执行团队"` if tests rely on it, or update tests deliberately.

Member rows must show:

- display name.
- template id.
- status.
- first tools/skills.
- responsibility metadata when available.

- [ ] **Step 2: Upgrade team styles**

Use white rows with left responsibility stripe:

- running: blue.
- passed/success: evidence green.
- review/warning: review amber.
- failed: error red.
- queued: neutral line.

- [ ] **Step 3: Quality gates**

Quality gates should read as trust checks, not decorative chips. Use compact rows or a strip with labels and status badges.

- [ ] **Step 4: Tests**

Run:

```bash
cd frontend && npx vitest run tests/unit/lib/execution-run-view.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected: PASS.

## Task 6: Rooms, Review, Prism, and Admin Cleanup

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/*.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
- Modify: `frontend/components/prism/PrismReviewList.tsx`
- Modify: `frontend/components/latex/latex-editor/LatexInspector.tsx`
- Modify: `frontend/components/latex/latex-editor/PrismOptimizationTraceDialog.tsx`
- Modify: `frontend/app/dashboard/admin/**/*.tsx`
- Test: `cd frontend && npm run typecheck`

- [ ] **Step 1: Replace purple active states**

Replace `--v2-accent-purple-*` in touched files with:

- active/focus: `--wjn-blue` / `--wjn-accent-soft`.
- review: `--wjn-review` / `--wjn-review-soft`.
- evidence/pass: `--wjn-evidence` / `--wjn-evidence-soft`.

- [ ] **Step 2: Replace old route-card admin visuals**

Admin cards use white console style:

- `rounded-[var(--wjn-radius-lg)]`
- `border-[var(--wjn-line)]`
- `bg-[var(--wjn-surface)]`
- `shadow-[var(--wjn-shadow-sm)]`

- [ ] **Step 3: Prism review states**

Prism review list must distinguish:

- selected item: blue line/soft background.
- pending review: amber.
- accepted/saved: evidence green.
- failed: error red.

- [ ] **Step 4: Typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS.

## Task 7: Documentation and Verification

**Files:**
- Modify: `docs/current/wenjin-research-navigation-uiux.md`
- Modify: `docs/current/documentation-map.md`
- Verify: browser pages

- [ ] **Step 1: Update current docs**

Update current UIUX doc so it points to `2026-06-04-system-grade-research-workbench-uiux-design.md` as the current baseline and marks the May glass spec as superseded.

- [ ] **Step 2: Run full frontend verification**

Run:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npx vitest run
```

Expected: all pass or failures are documented with exact failing tests and cause.

- [ ] **Step 3: Browser QA**

Start dev server:

```bash
cd frontend && npm run dev
```

Open and inspect:

- `/`
- `/login`
- `/register`
- `/workspaces`
- `/workspaces/<existing-id>`
- `/workspaces/<existing-id>/prism`
- `/dashboard/admin`
- `/dashboard/admin/models`
- `/dashboard/admin/capabilities`
- `/dashboard/admin/credits`

Fix visual regressions before final review.

- [ ] **Step 4: Final visual debt scan**

Run:

```bash
rg -n -g '*.tsx' -g '*.ts' -g '*.css' -- "--brand-|--compute-|--glass-|--v2-orb|--v2-bg-gradient|LiquidGlassCard|purple|rounded-2xl" frontend/app frontend/components frontend/lib
```

Expected: remaining matches are either compatibility aliases, intentionally untouched legacy components with follow-up noted, or false positives. No migrated surface should depend on old visual grammar.

- [ ] **Step 5: Commit**

Run:

```bash
git status --short
git add docs/superpowers/specs/2026-06-04-system-grade-research-workbench-uiux-design.md docs/superpowers/plans/2026-06-04-system-grade-research-workbench-uiux.md docs/current/wenjin-research-navigation-uiux.md docs/current/documentation-map.md frontend
git commit -m "feat: roll out system-grade research workbench ui"
```

Expected: one commit containing visual baseline docs, UI migration, tests, and cleanup.

## Self-Review

- Spec coverage: tasks cover tokens, shared UI, entry pages, workbench shell, team agent surface, rooms/review/Prism/Admin, docs, tests, and browser QA.
- Placeholder scan: no `TBD`, `TODO`, or underspecified implementation-only steps remain.
- Type consistency: all referenced paths exist in the current repository; token names match the spec and are introduced before use.
