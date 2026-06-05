# Full Shell UIUX Audit

Date: 2026-06-05

This audit is the Phase 0 baseline for `docs/superpowers/specs/2026-06-05-full-shell-uiux-refactor-design.md` and `docs/superpowers/plans/2026-06-05-full-shell-uiux-refactor.md`.

## Audit Inputs

Generated files:

- `/tmp/wenjin-ui-actions.txt`: 574 action-related matches.
- `/tmp/wenjin-ui-token-debt.txt`: 86 token/visual-debt matches.
- `/tmp/wenjin-ui-technical-labels.txt`: 668 technical-label matches.

Commands used:

```bash
rg -n "button|<Button|role=\"tab\"|aria-label|title=|onClick" frontend/app/'(workbench)'/workspaces/'[id]' frontend/components/latex frontend/app/workspaces/page.tsx frontend/app/dashboard/admin -g '*.{ts,tsx}' > /tmp/wenjin-ui-actions.txt
rg -n -e "--v2-" -e "--glass-" -e "--brand-" -e "--compute-" -e "LiquidGlass" -e "orb" frontend/app frontend/components frontend/lib -g '*.{ts,tsx,css}' > /tmp/wenjin-ui-token-debt.txt
rg -n "workspaceId|executionId|node id|node_id|template id|raw|payload|tool_invocation|sandbox logs|focusedRunId|hydration|projection" frontend/app frontend/components frontend/lib -g '*.{ts,tsx}' > /tmp/wenjin-ui-technical-labels.txt
```

## Action Budget Findings

| Surface | Current visible action pressure | Primary issue | Target fix |
|---|---:|---|---|
| Workspace list | 28 matches in `frontend/app/workspaces/page.tsx` | Delete action appears as a peer card action and competes with entry/create actions | Move danger and utility actions to overflow; keep create as page primary and card open as card primary |
| Workspace chrome | `SurfaceSwitch`, `RoomsTopbar`, resizer, room buttons, command entry | Multiple navigation layers are always visible | Replace with one `WorkspaceChrome` and one Workspace Hub entry |
| Current work panel | `WorkbenchHeader` has tabs, interrupt, fullscreen, status; `RunView` has quick evidence/review actions | Overview/run/evidence/review are exposed as peer modes, and unavailable interrupt remains visible | Replace with Current Work Cockpit and one contextual next decision |
| Review surface | 24 matches in `ReviewView.tsx` | Filters, preview selection, item toggles, detail/edit actions, commit actions compete in one layer | Use Review Queue with primary accept/apply action, compact filters, and detail pane |
| Run diagnostics | `NodeInspector.tsx` exposes sandbox summary and input preview under run view | Technical execution details sit too close to default run view | Move node input/tool/sandbox trace into diagnostics drawer |
| Prism editor | 32 matches in `LatexInspector.tsx`, 19 in `LatexRewritePreviewPanel.tsx`, 15 in `LatexEditorPanes.tsx`, 14 in `LatexFileTree.tsx` | Save/compile/modes/rewrite/file actions/logs all behave like peer controls | Introduce Manuscript Bar, Prism Inspector, and file/action overflow |
| Admin console | 29 matches in admin models, 25 in users, 15 in release gate, repeated page-local headers | Admin pages use local action patterns and table controls | Route actions through shared `AdminPageHeader`, table toolbar, and overflow |
| Rooms | 15 matches in `TasksDrawer`, multiple drawer close/search/item actions | Drawer shell and item action hierarchy vary by room | Use shared drawer header, search, list item, and overflow patterns |

## Highest-Pressure Files

Action-related matches by file:

| File | Matches | Interpretation |
|---|---:|---|
| `frontend/components/latex/latex-editor/LatexInspector.tsx` | 32 | Prism inspector needs action grouping and lower default density |
| `frontend/app/dashboard/admin/models/page.tsx` | 29 | Admin model console needs shared header/table actions |
| `frontend/app/workspaces/page.tsx` | 28 | Workspace list needs danger action demotion |
| `frontend/app/dashboard/admin/users/page.tsx` | 25 | Admin user table needs row overflow/action grouping |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx` | 24 | Review Queue needs one primary decision path |
| `frontend/components/latex/latex-editor/LatexRewritePreviewPanel.tsx` | 19 | Prism rewrite preview needs inspector/action bar consolidation |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx` | 18 | Workbench header is a major navigation/action pressure source |
| `frontend/components/latex/latex-editor/LatexEditorPanes.tsx` | 15 | Editor/PDF mode actions should move into Prism shell |
| `frontend/app/(workbench)/workspaces/[id]/components/rooms/TasksDrawer.tsx` | 15 | Room drawer actions need shared shell treatment |

## Token Debt

The 86 token/visual-debt matches are currently concentrated in `frontend/app/globals.css`.

Categories:

| Category | Location | Current role | Target |
|---|---|---|---|
| `--brand-*` aliases | `frontend/app/globals.css:52-59` | Compatibility mapping to `--wjn-*` | Keep temporarily as documented aliases; do not use in new components |
| `--compute-*` aliases | `frontend/app/globals.css:88-101` and class usage in the lower compatibility class section | Compatibility mapping and old compute classes | Migrate compute classes to `--wjn-*` during cleanup |
| `--v2-*` aliases | `frontend/app/globals.css:103-151` | Compatibility mapping for old v2 components | Keep temporarily; no new component may reference |
| `--compute-*` class usage | `frontend/app/globals.css:367-459`, `538-561`, `703` | Old compute visual layer | Replace with `--wjn-*` when old compute classes are migrated |

No `LiquidGlass` component references remain in scanned source. The deleted `frontend/components/glass/*` files indicate the old glass component family is already being removed.

## Technical Label Debt

The 668 technical-label matches include API/client code, test IDs, typed payload variables, and user-facing labels. They should not all be removed. The important split is default user-facing versus detail/diagnostic/internal.

### Default User-Facing Or Near-Default Issues

| File | Match | Classification | Target |
|---|---|---|---|
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector.tsx` | `输入预览`, sandbox summary | Diagnostic-only | Move behind `RunDiagnosticsDrawer` |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx` | `"Sandbox"` filter label | Detail-only | Rename to user-facing “实验产物” or hide in detail filter |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/OverviewView.tsx` | `实验环境` metric | Detail-only | Remove from default cockpit; show under diagnostics/evidence details |
| `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx` | sandbox count on run tab | Internal pressure | Remove with tab-heavy header |
| `frontend/app/(workbench)/workspaces/[id]/page.tsx` | visible workspace id chip through `RoomsTopbar` | Default user-facing | Hide from default chrome; keep in settings/diagnostics |

### Internal Or Acceptable Technical Matches

| File group | Reason |
|---|---|
| `frontend/lib/api/*` | API payload names and typed client contracts are internal |
| `frontend/lib/execution-run-view.ts` | Projection helpers are internal and canonical |
| `frontend/components/latex/latex-editor/*` hooks | PDF selection payload and anchor mapping are internal implementation details |
| `data-testid` fields in room drawers | Test selectors are not user-facing |
| `ChatPanel.tsx` metadata payload construction | Internal launch/intervention metadata |

## Phase Priorities

1. **Shared primitives**  
   Add `ActionBar`, `OverflowMenu`, `StatusChip`, `SectionHeader`, `DisclosureSection`, and `Panel` so subsequent surfaces do not keep writing local action hierarchies.

2. **WorkspaceChrome and WorkspaceHub**  
   Replace `SurfaceSwitch` + `RoomsTopbar` with one trusted chrome and a hub drawer. This removes the largest always-visible navigation burden.

3. **CurrentWorkCockpit**  
   Replace top-level Overview/Run/Evidence/Review tab pressure with a default cockpit that shows objective, progress, team, evidence summary, and one next decision.

4. **PrismShell**  
   Introduce a manuscript-level action hierarchy because Prism currently has the highest action pressure.

5. **Workspace list and Admin cleanup**  
   Move danger/low-frequency actions to overflow and normalize admin console headers.

6. **Token cleanup and browser regression**  
   Keep old token aliases during migration, then remove old class usage once surfaces no longer depend on it.

## Guardrails For Implementation

- Do not remove existing data access or execution behavior while reducing UI density.
- Do not hide review, evidence, or diagnostics without providing a reachable detail path.
- Do not add new components that reference `--v2-*`, `--glass-*`, `--brand-*`, or `--compute-*`.
- Do not show raw execution payload, node input, workspace id, or sandbox logs in default surfaces.
- Do not leave permanently disabled text buttons in the main action area.
- Do not preserve old `SurfaceSwitch` or `RoomsTopbar` as compatibility wrappers after the new shell is mounted.
