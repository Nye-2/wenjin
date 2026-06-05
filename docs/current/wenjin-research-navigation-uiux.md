# Wenjin Research Navigation UIUX

更新时间：2026-06-05

Wenjin keeps the name, but the product interface baseline is now **System-Grade Research Workbench**: a research operating-system surface with trusted chrome, quiet content, evidence-first execution, and mature institutional polish.

Current baseline spec: `docs/superpowers/specs/2026-06-04-system-grade-research-workbench-uiux-design.md`.

Current full-shell migration source: `docs/superpowers/specs/2026-06-05-full-shell-uiux-refactor-design.md`.

Workspace now uses a single trusted chrome for workspace identity, Workbench/Prism switching, running/review status, and the Workspace Hub entry. The previous permanent room topbar is removed. Rooms are reached through Workspace Hub, while technical execution details remain available behind run diagnostics instead of default panels.

The earlier Glass / visionOS direction in `docs/superpowers/specs/2026-05-09-v2-design-language.md` is superseded for new work. Existing `--v2-*` tokens may remain as compatibility aliases during migration, but new components should use `--wjn-*`.

## Positioning

Wenjin is a research and writing workbench for Chinese academic, software copyright, proposal, and patent workflows. The UI should make users feel that every agent action is traceable, reviewable, and grounded in workspace evidence.

## Principles

- Evidence over decoration: sources, artifacts, trace, and review state are more important than glow effects.
- Trusted chrome, quiet content: top-level shell carries identity, navigation, permission, state, command entry, and commit trust; content surfaces stay readable and low-noise.
- Chat for intent, Workbench for work: chat collects goals and interventions; right-side surfaces carry runs, evidence, complex previews, and review.
- Review before commit: generated material enters a review queue before it writes into rooms or Prism.
- Team agents as responsibility surfaces: real-name subagents should show role, status, capability readiness, output ownership, and quality gates. Template ids, raw tools, and raw skills belong in diagnostics, not default user-facing text. Do not present agents as mascot characters.
- Quiet density: support long sessions with compact controls, hairline dividers, restrained color, and stable layouts.
- Chinese professional context: labels should be short, concrete, and formal enough for thesis, software copyright, and patent users.
- Adaptive by default: layout, focus, and detail surfaces should react automatically to viewport width and current task state. Users should not need to manage internal UI modes such as "auto focus" or "manual lock".
- Progressive disclosure: primary screens show summaries and the next decision; dense details appear in secondary panes, fullscreen detail mode, drawers, or hover/tooltips.
- State is product language, not engineering language: expose "运行中", "待审阅", "已保存", "已完成"; do not expose concepts like local locks, focus ids, hydration, or projection internals.

## Visual System

- Base: cold white/gray/blue-gray surfaces, no paper/ink or decorative ancient style.
- Accent: institutional navy/blue for trusted chrome, primary actions, active agent state, and focus.
- Premium detail: minimal gold stitch for recommendations or critical confirmation only; no large gold fills.
- Semantic colors: teal for evidence, amber for review, green for committed/success, red for failure.
- Structure: 1px hairline borders, 8-10px radius for controls, 12-16px for system chrome and raised surfaces.
- Material: translucent material is allowed only for topbars, sidebars, drawers, command bars, and modal shell. Main content cards stay solid white.
- Motion: 140-220ms state feedback only; no large decorative orbs, looping glow, or playful character animation.

## Signature Components

- Trusted Chrome: workspace identity, surface switch, command bar, status summary, Prism review badge, and Workspace Hub entry.
- Trace Rail: current objective, node states, timing, tool/sandbox summaries, and artifact links.
- Evidence Ledger: literature, uploaded files, experiment results, and agent-derived evidence in one filterable surface.
- Review Queue: staged outputs, Prism file changes, accepted/rejected state, write links, and rollback affordances.
- Research Team Roster: real-name role seats, status stripes, capability readiness, quality gates, and output attribution.

## Interaction Density Rules

- Navigation should collapse before content does. In compact headers, inactive navigation items may show icon-only controls with `aria-label`, `title`, or tooltip text; active items can show icon + label.
- Controls should only use both icon and text when the command is primary or unfamiliar. Secondary controls should prefer icon-only with tooltip; repeated labels should be removed.
- Details should not compete with lists in narrow containers. List-first mode is the default; selecting an item can open a wider detail surface or fullscreen split view.
- Filters are second-level navigation, not full cards. Use compact segmented controls or pills for result types such as all, literature, documents, memory, decisions, and tasks.
- Text must be width-constrained. Long paper titles, file names, authors, and run names should use single-line or two-line truncation inside lists, with full content in the detail pane.
- Automatic context following is the default. Running work should surface the run view; completed work with staged outputs should surface review. Manual navigation is temporary unless there is an explicit "pin" concept with user-facing value.
- Avoid exposing maintenance actions as top-level UI. Recovery or debug controls belong in overflow menus, settings, or diagnostics surfaces unless they are part of the user's core workflow.

## Workspace Surfaces

- Workbench: the main navigation console for runs, evidence, and review.
- Prism: the manuscript/material control surface with editor, PDF compare mode, selection optimization, and diff review.
- Rooms: persistent workspace data reached through Workspace Hub. Rooms should feel like ledgers and stores, not a permanent peer navigation strip or chat extensions.

## Page Templates

- Public / entry surfaces: institutional white, trusted topbar, restrained deep-blue brand presence, path cards for workflow choices.
- Workbench: compact split system with chat-for-intent on the left and execution/evidence/review on the right.
- Prism: editor/PDF/inspector split with review attribution, source links, compile state, and staged changes.
- Admin / DataService: dense console layout with metric rows, tables, module cards, dialogs, and clear danger actions.

## Token Rules

- New UI uses `--wjn-*` only.
- `--v2-*`, `--brand-*`, `--compute-*`, and `--glass-*` are compatibility aliases while old components migrate.
- New UI must not introduce purple-blue orb backgrounds, paper/tan route-map styling, or decorative glass cards.
