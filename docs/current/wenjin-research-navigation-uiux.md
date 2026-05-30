# Wenjin Research Navigation UIUX

更新时间：2026-05-29

Wenjin keeps the name, but the product interface should move from decorative glass toward an evidence-first research navigation system.

## Positioning

Wenjin is a research and writing workbench for Chinese academic, software copyright, proposal, and patent workflows. The UI should make users feel that every agent action is traceable, reviewable, and grounded in workspace evidence.

## Principles

- Evidence over decoration: sources, artifacts, trace, and review state are more important than glow effects.
- Chat for intent, Workbench for work: chat collects goals and interventions; right-side surfaces carry runs, evidence, complex previews, and review.
- Review before commit: generated material enters a review queue before it writes into rooms or Prism.
- Quiet density: support long sessions with compact controls, hairline dividers, restrained color, and stable layouts.
- Chinese professional context: labels should be short, concrete, and formal enough for thesis, software copyright, and patent users.
- Adaptive by default: layout, focus, and detail surfaces should react automatically to viewport width and current task state. Users should not need to manage internal UI modes such as "auto focus" or "manual lock".
- Progressive disclosure: primary screens show summaries and the next decision; dense details appear in secondary panes, fullscreen detail mode, drawers, or hover/tooltips.
- State is product language, not engineering language: expose "运行中", "待审阅", "已保存", "已完成"; do not expose concepts like local locks, focus ids, hydration, or projection internals.

## Visual System

- Base: cold white/gray surfaces, no paper/ink or decorative ancient style.
- Accent: low-saturation indigo for active agent state and focus.
- Semantic colors: teal for evidence, amber for review, green for committed/success, red for failure.
- Structure: 1px hairline borders, 8px radius for controls, 12px for raised surfaces.
- Motion: subtle running dots and trace lines only; no large decorative orbs.

## Signature Components

- Trace Rail: current objective, node states, timing, tool/sandbox summaries, and artifact links.
- Evidence Ledger: literature, uploaded files, experiment results, and agent-derived evidence in one filterable surface.
- Review Queue: staged outputs, Prism file changes, accepted/rejected state, write links, and rollback affordances.

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
- Rooms: persistent workspace data. Rooms should feel like ledgers and stores, not chat extensions.
