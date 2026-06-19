# Wenjin Global UIUX Redesign Design

## Goal

Unify Wenjin's Workbench, Prism, Rooms, and shared frontend surfaces into a more beautiful, more coherent, system-grade academic research workbench.

The redesign should keep the current product architecture: Chat Agent remains the left intent layer, Lead Agent / TeamKernel remains the right execution layer, Prism remains the manuscript surface, and Rooms remain persisted workspace stores. The work is a UIUX convergence and polish effort, not a new product architecture.

## Current Baseline

Wenjin already has the correct design direction documented in `docs/current/wenjin-research-navigation-uiux.md`: System-Grade Research Workbench, trusted chrome, quiet content, evidence-first execution, and review-before-commit. The frontend also already has `--wjn-*` tokens in `frontend/app/globals.css`, `WorkspaceChrome`, `WorkspaceHubDrawer`, `LiveWorkflowPanel`, `Prism`, and room drawers.

The weak point is implementation consistency. Workbench surfaces still contain many inline styles, local style dictionaries, compatibility tokens, and manual layout state. The UI often has the right facts but not always the right composition, beauty, or calm hierarchy.

## Design Decision

Use **Quiet Research OS** as the global baseline.

Prism adopts an **Editorial Studio** treatment inside the same visual system. The Evidence Command Center direction is used only as a stateful detail layer for execution and evidence, not as a permanent three-column chrome.

The product should feel institutional, polished, and calm. Beauty should come from proportion, spacing, typography, surface discipline, and clear state color, not from decorative effects.

## Product Brief

The product is Wenjin, an AI workbench for academic research and writing. It supports thesis, SCI, proposal, software copyright, and patent workspaces.

The redesign covers:

- Workbench route: `/workspaces/{workspace_id}`
- Prism route: `/workspaces/{workspace_id}/prism`
- Workspace Hub and Rooms drawers
- Shared UI primitives used by chat blocks, result cards, execution views, Prism review, drawers, and admin-like dense surfaces
- Global token, interaction, responsiveness, and visual QA rules

The visual source of truth is:

- `docs/current/wenjin-research-navigation-uiux.md`
- `frontend/app/globals.css` `--wjn-*` tokens
- Existing `WorkspaceChrome`, `LiveWorkflowPanel`, `WorkspaceHubDrawer`, Rooms, and Prism surfaces
- UI/UX Pro Max guidance retained for enterprise/B2B dashboards, academic typography, accessibility, layout, React performance, and data-dense review surfaces

## Non-Goals

This redesign does not:

- Replace Chat Agent, Lead Agent, TeamKernel, execution stores, or DataService contracts.
- Add a second execution state model or frontend-local execution truth.
- Reintroduce fixed room topbars or sandbox as a user-operable room.
- Add decorative ancient-style tokens, paper/tan themes, purple orb backgrounds, mascot agents, raw log panels, or permanent technical sidebars.
- Turn Workbench into a landing page or marketing surface.
- Remove Prism's editor, review, compile, PDF preview, protected scope, or apply/revert workflows.

## Visual System

### Global Baseline

Wenjin should use a cold institutional palette:

- Base surfaces: cold white, blue-gray, and slate-tinted backgrounds.
- Primary authority: navy and trusted blue.
- Evidence: teal.
- Review: amber.
- Success: green.
- Error: red.
- Premium emphasis: small gold stitch only for recommendations or critical confirmation.

Main content cards are solid white. Translucent material is reserved for trusted chrome, topbars, drawers, command bars, and modal shells. Large decorative gradients, glow fields, bokeh, or glass-card stacks are not allowed.

### Beauty Rules

The redesign must improve visual polish through these rules:

- Use 1px hairline borders with low opacity for structure.
- Use `8px` radius for controls, `10-12px` for compact surfaces, and `14-16px` for system panels, drawers, and raised shells.
- Use a restrained shadow scale: near surfaces use low blur and low opacity; drawers and modals can use larger but soft shadows.
- Use an 8px spacing rhythm with tighter 4px increments only inside compact controls.
- Use fewer text weights: regular body, medium labels, semibold headings, bold only for primary metrics or active state.
- Do not use negative letter spacing for new UI.
- Use Lucide icons for actions and navigation, with consistent stroke and sizing.
- Avoid text buttons where an established icon communicates the action; pair icon-only controls with `aria-label`, `title`, and tooltip.
- Keep motion to 140-220ms state feedback using transform and opacity only.

### Typography

Use the existing system stack:

```css
--wjn-font-sans: 'SF Pro Display', 'Inter', system-ui, -apple-system, 'PingFang SC', sans-serif;
--wjn-font-mono: 'JetBrains Mono', 'SF Mono', 'Menlo', monospace;
```

Do not introduce decorative academic serif fonts into the app chrome. Serif-like academic texture can appear only in manuscript/PDF content rendered by Prism, not in navigation, controls, or status UI.

## Surface Designs

### Workspace Chrome

Workspace Chrome is the trusted top-level shell. It owns:

- Workspace identity.
- Workbench / Prism surface switch.
- Running and pending-review summary.
- Workspace Hub entry.
- Compact contextual status.

It should not carry room navigation strips, raw execution diagnostics, or debug actions. Navigation should collapse before content does. On compact widths, inactive surface labels may become icon-only, but active surface and important review count remain clear.

Workbench and Prism surface labels may remain English if they are product terms, but the surrounding status language should be Chinese and user-facing: `运行中`, `待确认`, `已保存`, `已完成`.

### Workbench

Workbench is a two-layer work surface:

1. **Chat for intent** on the left.
2. **Current work projection** on the right.

The right side auto-selects the best view:

- Running execution: show current run progress first.
- Completed execution with review items: show review queue first.
- Completed execution with evidence but no review: show evidence first.
- No active work: show overview and capability entry.

Manual tab switching is allowed, but internal focus concepts must not leak into the product language. The user should not need to understand persistent `splitRatio`, `fullscreen`, `selectedRunId`, or manual focus recovery.

The default Workbench should be calm and not permanently three-column. When a run has substantial evidence, the evidence detail can appear as a contextual rail or detail pane. The rail is stateful and useful, not a fixed technical sidebar.

#### Workbench Layout Behavior

Desktop:

- Default split: Chat left, Workbench right.
- The split can be user-adjustable, but reset and persistence must not produce confusing stale layouts.
- Right side can enter focused mode for deep review, but this should be framed as `专注审阅` or `展开工作台`, not a technical fullscreen mode.

Tablet:

- Chat and Workbench use an adaptive split or stacked view depending on width.
- Review and evidence detail should use list-first behavior.

Mobile:

- Use a segmented top switch: `对话`, `进展`, `证据`, `确认`.
- Do not render three cramped panes.
- Primary action remains reachable at the bottom or top safe area without overlapping content.

### Chat Panel

Chat remains the intent, intervention, and result receipt surface.

The empty state should show workspace identity and two to four high-value starter prompts. It should not feel like a marketing hero.

Message blocks should use shared primitives for:

- Text block.
- Thinking block.
- Status line.
- Question card.
- Result card.
- Tool invocation.
- Tool result.

Thinking blocks remain in arrival order and are never prepended.

Result cards should remain review-first:

- Default all checked.
- One-click `全部接受`.
- Clear grouping by output kind.
- Prism file changes route to Prism review instead of ordinary room commit.

### Live Workflow Panel

Live Workflow is the execution truth projection. It should use `frontend/lib/execution-run-view.ts` as the single view model and avoid parsing raw node/tool JSON in components.

It should expose a polished five-step TeamKernel process:

1. 准备上下文
2. 组建团队
3. 成员执行
4. 质量闭环
5. 整理结果

Real-name team members appear as responsibility surfaces with role, status, latest readable snapshot, evidence count, and output ownership. Template ids, schema names, raw tools, and internal output refs belong in diagnostics.

Quality highlights should be short user-facing labels, such as `引用支撑`, `实验解释`, `统计稳健`, `语义保持`, and `学术风格`.

### Prism

Prism is the manuscript and material control surface. It should feel like an academic editing studio inside the Quiet Research OS, not like a debug editor.

Prism must support two primary modes:

#### Normal Prism Mode

Default mode is:

- Editor / manuscript surface.
- Review and provenance rail.
- Protected scope controls.
- Compile status summary.
- Pending change list and apply/reject/revert actions.

This is best for AI rewriting, local manuscript edits, reviewing pending file changes, source attribution, and protected-scope management.

#### PDF Preview Expanded Mode

Prism must include an Overleaf-like PDF preview stage. The PDF preview is a first-class working surface, not a diagnostic artifact.

Expanded mode is:

- Editor on the left.
- PDF preview stage in the center or right, depending on available width.
- Slim review/provenance rail.

Open triggers:

- User clicks PDF preview or compile.
- Compile completes successfully.
- User selects a review item that needs layout validation.
- User enters PDF compare mode.
- User chooses final proofread or visual inspection.

Required PDF controls:

- Compile / refresh.
- Sync scroll between source and PDF when available.
- Fit width / fit page.
- Page navigation.
- Zoom.
- PDF fullscreen / collapse preview.
- Compile status and error summary.

Responsive behavior:

- Desktop wide: allow editor + PDF + slim review rail.
- Desktop medium: allow editor + PDF, with review in a drawer or collapsible side rail.
- Narrow screens: use segmented views `编辑`, `PDF`, `审阅`; do not crush editor, PDF, and rail into unusable columns.

Review coupling:

- Review items can focus changed ranges in editor and corresponding PDF location when mapping exists.
- Review rail shows source links, semantic/style contracts, quality risk, and apply/reject actions.
- The PDF preview should reflect pending state clearly: compiled current file, pending preview, or applied version.

### Rooms

Rooms are ledgers and stores reached from Workspace Hub:

- Library: literature and citations.
- Documents: reports, drafts, attachments, and deliverables.
- Decisions: accepted/rejected decisions and review outcomes.
- Memory: durable facts and preferences.
- Run History: historical execution records.
- Tasks: follow-up items.
- Settings: workspace configuration.

Rooms should not feel like chat extensions or debug panes. Use compact lists, type filters, search, clear empty states, and detail drawers.

List-first is the default. On wide screens a selected item can open a detail pane. On narrow screens selection opens a detail surface or fullscreen split.

Long paper titles, file names, authors, URLs, and run names must be truncated in lists and fully visible in details.

### Admin and Dense Console Surfaces

Admin and DataService-like surfaces should use the same tokens but a denser pattern:

- Metric rows.
- Tables.
- Module cards.
- Dialogs.
- Clear danger actions.

They should remain utilitarian and should not inherit Workbench empty-state styling or Prism editorial styling.

## Component Architecture

### New UI Primitives

Introduce or converge shared primitives before large surface rewrites:

- `WjnShell`
- `WjnTopbar`
- `WjnPanel`
- `WjnSection`
- `WjnToolbar`
- `WjnSegmentedControl`
- `WjnIconButton`
- `WjnStatusChip`
- `WjnCountBadge`
- `WjnEmptyState`
- `WjnList`
- `WjnListItem`
- `WjnDetailPane`
- `WjnDrawer`
- `WjnReviewRail`
- `WjnPdfStage`

Existing `CountBadge`, `StatusChip`, `IconButton`, dialog, scroll, markdown, and code components should be reused or migrated rather than duplicated.

### Token Governance

New UI must use `--wjn-*` tokens directly.

Compatibility aliases can remain while old components migrate, but new work must not add:

- `--v2-*`
- `--brand-*`
- `--compute-*`
- `--glass-*`

unless the file is explicitly maintaining compatibility for old surfaces.

### Styling Policy

Reduce inline styles in Workbench, Prism, Rooms, and shared components.

Use a small set of shared classes and component variants for recurring layout and visual behavior. Inline styles remain acceptable only for dynamic dimensions and values that must be computed at runtime, such as split width, progress width, context menu position, or PDF zoom transform.

The existing local `live-workflow/styles.ts` can be used as an intermediate migration source, but the target state is reusable primitives and token-backed classes.

## State and Data Flow

The redesign must preserve current frontend data boundaries:

- `frontend/lib/execution-run-view.ts` remains execution projection truth.
- `frontend/stores/run-ui-store.ts` remains UI focus and badge state only.
- `frontend/stores/execution-store.ts` remains execution record state.
- `frontend/stores/chat-store.ts` remains chat block state.
- `frontend/stores/workbench-layout-store.ts` should be narrowed to user-visible layout preferences, not internal automatic focus state.

Recommended split:

- Persist only meaningful user preferences such as desired Workbench split size and Prism PDF preview open state.
- Do not persist automatic active tab if it creates stale restoration.
- Do not expose internal lock/focus states in UI labels.
- Preserve selected run and selected node only when it improves history navigation, not when a new active run should take focus.

## Interaction Rules

### Accessibility

All new UI must satisfy:

- Keyboard navigation for all controls.
- Visible focus rings.
- Icon-only buttons with `aria-label`, `title`, and tooltip.
- Sequential heading hierarchy.
- No color-only meaning.
- Contrast of at least 4.5:1 for normal text and 3:1 for large text or non-text UI indicators.

### Touch and Responsive

- Minimum interactive target: 44px.
- Minimum gap between adjacent touch targets: 8px.
- No horizontal page scroll on 375px width.
- Fixed or sticky bars must reserve content inset so they do not cover content.
- Tables and dense ledgers must switch to card/list layouts or internal scroll wrappers on narrow screens.

### Motion

- Use 140-220ms for state changes.
- Use transform and opacity only.
- Respect `prefers-reduced-motion`.
- Do not animate large layout reflows, width/height, or decorative background effects.

### Loading and Error States

Loading should reserve space. Use skeletons or quiet progress indicators for async content that takes more than 300ms.

Errors should state:

- What failed.
- Whether user work is safe.
- The next recovery action.

Prism compile errors should be shown near the PDF/compile controls and link to relevant editor location if available.

Execution failures should appear in Live Workflow as user-facing status and recovery guidance, with diagnostics behind an overflow or detail surface.

## Implementation Units

This design should be implemented in small, testable units:

1. Token and primitive convergence.
2. Workbench shell and adaptive layout.
3. Live Workflow view polish.
4. Chat and block primitive polish.
5. Workspace Hub and Rooms ledger polish.
6. Prism normal mode polish.
7. Prism PDF preview expanded mode.
8. Accessibility and responsive QA.
9. Visual regression and smoke tests.

Each unit should preserve current API contracts and avoid changing execution behavior.

## Testing and QA

### Static Checks

- `cd frontend && npm run typecheck`
- `cd frontend && npx vitest run`
- `cd frontend && npm run build`

### Browser QA

Use browser screenshots and interaction checks for:

- Workbench empty state.
- Workbench active run.
- Workbench completed run with review items.
- Workbench evidence detail.
- Workspace Hub drawer.
- Library / Documents / Runs / Tasks drawers.
- Prism normal editor + review mode.
- Prism PDF preview expanded mode.
- Prism narrow responsive mode.

### Viewports

Verify at:

- 375px mobile.
- 768px tablet.
- 1024px desktop.
- 1440px desktop.

### Accessibility QA

Check:

- Keyboard tab order.
- Focus visibility.
- Icon-only button labels.
- Dialog and drawer escape behavior.
- Review and PDF preview controls reachable by keyboard.
- No horizontal scroll on mobile.
- Reduced motion behavior.

## Acceptance Criteria

The redesign is acceptable when:

- Workbench, Prism, and Rooms visibly share one token-backed system.
- New UI uses `--wjn-*` tokens and does not add new compatibility-token dependencies.
- Workbench no longer feels like separate chat, run, evidence, and review widgets pasted together.
- Prism includes a polished PDF preview expanded mode with Overleaf-like working behavior.
- Rooms feel like ledgers/stores with clear list-detail hierarchy.
- Manual layout controls are framed in user-facing language or made automatic.
- Default UI does not expose schema names, raw tool JSON, internal refs, execution projection internals, or debug logs.
- All icon-only controls have accessible labels and visible focus.
- Mobile and tablet layouts remain usable without cramped three-column panes.
- The visual system is more beautiful through proportion, hierarchy, spacing, and surface treatment while staying quiet and professional.

## Rollout Notes

Implement in a single product direction but in multiple pull-request-sized steps. The first implementation plan should start with primitives and Workbench/Prism shell structure because those decisions reduce churn in subsequent surface work.

Do not start by recoloring individual cards. Start by establishing the shell, primitives, and layout rules that make later polish consistent.
