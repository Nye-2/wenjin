# Full Shell UIUX Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Wenjin full-shell UIUX refactor from `docs/superpowers/specs/2026-06-05-full-shell-uiux-refactor-design.md` without regressing the Chat -> Lead Agent -> Execution -> Review Queue -> Rooms/Prism product chain.

**Architecture:** Build shared shell/action primitives first, then migrate the product surfaces in dependency order: Workspace Chrome, Current Work Cockpit, Workspace Hub/Rooms, Prism Shell, Public/Auth/Workspace list/Admin, then cleanup and regression. Keep execution state canonical in existing stores and projections; UI refactor must only change presentation, action hierarchy, and progressive disclosure.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript, Tailwind, Zustand, lucide-react, Vitest, Playwright/browser smoke, Docker Compose.

---

## Current Constraints

- The worktree is already dirty. Do not revert unrelated files.
- New components must use `--wjn-*` tokens only.
- Do not reintroduce glass/orb/purple visual language.
- Do not change backend execution contracts.
- Do not make `run-ui-store` a business execution store.
- Do not bypass `execution-run-view.ts` for run projection.
- Do not remove technical detail; move it into detail or diagnostics surfaces.

## File Structure

### Shared UI Foundation

- Create `frontend/components/ui/icon-button.tsx`  
  A compact icon-only button wrapper with required accessible label.
- Create `frontend/components/ui/action-bar.tsx`  
  Shared action grouping for primary, secondary, overflow, and danger actions.
- Create `frontend/components/ui/overflow-menu.tsx`  
  Lightweight menu for low-frequency actions.
- Create `frontend/components/ui/status-chip.tsx`  
  Semantic status labels using `--wjn-*`.
- Create `frontend/components/ui/count-badge.tsx`  
  Small tabular count badge.
- Create `frontend/components/ui/section-header.tsx`  
  Shared section title/subtitle/action shell.
- Create `frontend/components/ui/disclosure-section.tsx`  
  Progressive disclosure wrapper for details and diagnostics.
- Create `frontend/components/ui/panel.tsx`  
  Solid white panel primitive for content surfaces.
Existing `frontend/components/ui/button.tsx` and `frontend/components/ui/card.tsx` remain as stable base primitives during Task 1. Later tasks may migrate local page styles to the new action/panel primitives, but Task 1 does not change their public API.

### Workspace Shell

- Create `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx`  
  Single trusted chrome replacing the current `SurfaceSwitch` + persistent room topbar pattern.
- Create `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer.tsx`  
  Grouped room navigation and search.
- Modify `frontend/app/(workbench)/workspaces/[id]/page.tsx`  
  Mount new shell and keep existing room drawers behind the hub.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`  
  Remove after `WorkspaceChrome` replaces all current callers.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/RoomsTopbar.tsx`  
  Remove after `WorkspaceHubDrawer` replaces all current callers.

### Current Work Cockpit

- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/CurrentWorkCockpit.tsx`  
  Default right-side cockpit view.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NextDecisionCard.tsx`  
  One primary next decision/action.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceSnapshot.tsx`  
  Compact evidence summary.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ResearchTeamRoster.tsx`  
  Compact team roster with expandable details.
- Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunDiagnosticsDrawer.tsx`  
  Node details, raw payload, tools, sandbox, and technical trace.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`  
  Use cockpit as default; keep evidence/review/history as details or drawers.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/WorkbenchHeader.tsx`  
  Remove tab-heavy header after cockpit owns navigation.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`  
  Use compact summary and move `NodeInspector` into diagnostics.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`  
  Align around one primary review action.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`  
  Make it a detail surface, not a peer top-level tab.
- Modify `frontend/lib/execution-run-view.ts`  
  Add only presentation helpers needed by cockpit; preserve canonical projection.

### Workspace Hub And Rooms

- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/DocumentsDrawer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/MemoryViewer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/DecisionsViewer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/TasksDrawer.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/components/rooms/SettingsPage.tsx`

Rooms keep existing data/API behavior and receive a shared drawer header/action hierarchy.

### Prism Shell

- Create `frontend/app/(workbench)/workspaces/[id]/prism/PrismShell.tsx`
- Create `frontend/app/(workbench)/workspaces/[id]/prism/ManuscriptBar.tsx`
- Create `frontend/app/(workbench)/workspaces/[id]/prism/PrismReviewInspector.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- Modify `frontend/app/(workbench)/workspaces/[id]/prism/PrismContextRail.tsx`
- Modify `frontend/components/latex/LatexEditorShell.tsx`
- Modify `frontend/components/latex/latex-editor/LatexEditorPanes.tsx`
- Modify `frontend/components/latex/latex-editor/LatexInspector.tsx`
- Modify `frontend/components/prism/PrismReviewList.tsx`

### Public/Auth/Workspace List/Admin

- Modify `frontend/app/page.tsx`
- Modify `frontend/app/pricing/page.tsx`
- Modify `frontend/app/(auth)/login/page.tsx`
- Modify `frontend/app/(auth)/register/page.tsx`
- Modify `frontend/app/workspaces/page.tsx`
- Modify `frontend/components/academic/workspace-card.tsx`
- Modify `frontend/app/dashboard/admin/layout.tsx`
- Modify `frontend/app/dashboard/admin/components/AdminPageHeader.tsx`
- Modify `frontend/app/dashboard/admin/components/AdminSidebar.tsx`
- Modify `frontend/app/dashboard/admin/**/page.tsx` as needed for shared action hierarchy.

### Tests And Docs

- Create `frontend/tests/unit/ui/action-hierarchy.test.tsx`
- Create `frontend/tests/unit/v2/WorkspaceChrome.test.tsx`
- Create `frontend/tests/unit/v2/CurrentWorkCockpit.test.tsx`
- Create `frontend/tests/unit/v2/WorkspaceHub.test.tsx`
- Create `frontend/tests/unit/v2/prism-shell.test.tsx`
- Modify `frontend/tests/unit/v2/layout.test.tsx`
- Modify `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
- Modify `frontend/tests/unit/v2/rooms/RunsDrawer.test.tsx`
- Modify `docs/current/wenjin-research-navigation-uiux.md`
- Modify `docs/current/documentation-map.md`

---

## Task 0: Phase 0 Audit And Guardrails

**Files:**
- Create: `docs/superpowers/plans/2026-06-05-full-shell-uiux-audit.md`
- No production code changes in this task.

- [ ] **Step 1: Inventory top-level workspace actions**

Run:

```bash
rg -n "button|<Button|role=\"tab\"|aria-label|title=|onClick" \
  frontend/app/'(workbench)'/workspaces/'[id]' \
  frontend/components/latex \
  frontend/app/workspaces/page.tsx \
  frontend/app/dashboard/admin \
  -g '*.{ts,tsx}' > /tmp/wenjin-ui-actions.txt
```

Expected: `/tmp/wenjin-ui-actions.txt` lists all button/action candidates.

- [ ] **Step 2: Inventory old tokens and visual debt**

Run:

```bash
rg -n -e "--v2-" -e "--glass-" -e "--brand-" -e "--compute-" -e "LiquidGlass" -e "orb" \
  frontend/app frontend/components frontend/lib \
  -g '*.{ts,tsx,css}' > /tmp/wenjin-ui-token-debt.txt
```

Expected: `/tmp/wenjin-ui-token-debt.txt` lists compatibility aliases and remaining old visual usage.

- [ ] **Step 3: Inventory raw technical user-facing labels**

Run:

```bash
rg -n "workspaceId|executionId|node id|node_id|template id|raw|payload|tool_invocation|sandbox logs|focusedRunId|hydration|projection" \
  frontend/app frontend/components frontend/lib \
  -g '*.{ts,tsx}' > /tmp/wenjin-ui-technical-labels.txt
```

Expected: command may return matches; every user-facing match must be classified.

- [ ] **Step 4: Create audit markdown**

Create `docs/superpowers/plans/2026-06-05-full-shell-uiux-audit.md` with this structure:

```markdown
# Full Shell UIUX Audit

Date: 2026-06-05

## Action Budget Findings

| Surface | Current visible action pressure | Primary issue | Target fix |
|---|---|---|---|
| Workspace chrome | Surface switch + room buttons + command entry | Multiple navigation layers | WorkspaceChrome + WorkspaceHub |
| Current work panel | tabs + status + interrupt + fullscreen + quick actions | Too many peer actions | CurrentWorkCockpit + one next decision |
| Run view | evidence/review buttons + team + timeline + details | technical detail too close to default layer | diagnostics drawer |
| Prism | save + compile + modes + files + inspector + agent | toolbar overload | ManuscriptBar + inspector action bar |
| Workspace list | delete action appears at card top | danger action too prominent | overflow menu |
| Admin | many local header/action patterns | inconsistent console hierarchy | shared AdminPageHeader + table toolbar |

## Token Debt

Summarize `/tmp/wenjin-ui-token-debt.txt` by category.

## Technical Label Debt

Summarize `/tmp/wenjin-ui-technical-labels.txt` by whether the label is user-facing, detail-only, or diagnostic-only.

## Phase Priorities

1. Shared primitives.
2. WorkspaceChrome and WorkspaceHub.
3. CurrentWorkCockpit.
4. PrismShell.
5. Public/Auth/Workspace list/Admin cleanup.
```

- [ ] **Step 5: Self-check audit**

Run:

```bash
rg -n "TBD|TODO|fill in|unknown|later" docs/superpowers/plans/2026-06-05-full-shell-uiux-audit.md
```

Expected: no output.

---

## Task 1: Shared UI Foundation

**Files:**
- Create: `frontend/components/ui/icon-button.tsx`
- Create: `frontend/components/ui/action-bar.tsx`
- Create: `frontend/components/ui/overflow-menu.tsx`
- Create: `frontend/components/ui/status-chip.tsx`
- Create: `frontend/components/ui/count-badge.tsx`
- Create: `frontend/components/ui/section-header.tsx`
- Create: `frontend/components/ui/disclosure-section.tsx`
- Create: `frontend/components/ui/panel.tsx`
- Test: `frontend/tests/unit/ui/action-hierarchy.test.tsx`

- [ ] **Step 1: Write failing action hierarchy test**

Create `frontend/tests/unit/ui/action-hierarchy.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Archive, MoreHorizontal, Save, Trash2 } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";

describe("ActionBar", () => {
  it("renders one primary action, secondary actions, and overflow without exposing hidden actions as peer buttons", () => {
    render(
      <ActionBar
        primary={{ label: "全部接受", onClick: () => undefined }}
        secondary={[{ label: "查看证据", onClick: () => undefined, icon: Archive }]}
        overflow={[
          { label: "复制 ID", onClick: () => undefined, icon: MoreHorizontal },
          { label: "删除", onClick: () => undefined, icon: Trash2, tone: "danger" },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "全部接受" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看证据" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "更多操作" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制 ID" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删除" })).not.toBeInTheDocument();
  });

  it("requires accessible labels for icon-only actions", () => {
    render(
      <ActionBar
        secondary={[
          {
            label: "保存",
            icon: Save,
            iconOnly: true,
            onClick: () => undefined,
          },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: "保存" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && npm run test -- tests/unit/ui/action-hierarchy.test.tsx
```

Expected: FAIL because `@/components/ui/action-bar` does not exist.

- [ ] **Step 3: Implement `IconButton`**

Create `frontend/components/ui/icon-button.tsx`:

```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger";
};

export function IconButton({
  label,
  children,
  className,
  tone = "default",
  title,
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={title ?? label}
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--wjn-radius)] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wjn-blue)] disabled:pointer-events-none disabled:opacity-45",
        tone === "danger"
          ? "border-[rgba(185,28,28,0.24)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)] hover:bg-[rgba(185,28,28,0.14)]"
          : "border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text-secondary)] hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-text)]",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Implement `OverflowMenu`**

Create `frontend/components/ui/overflow-menu.tsx`:

```tsx
"use client";

import { useState, type ComponentType } from "react";
import { MoreHorizontal } from "lucide-react";

import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

export type OverflowMenuItem = {
  label: string;
  onClick: () => void;
  icon?: ComponentType<{ className?: string }>;
  tone?: "default" | "danger";
  disabled?: boolean;
};

export function OverflowMenu({ items }: { items: OverflowMenuItem[] }) {
  const [open, setOpen] = useState(false);

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="relative inline-flex">
      <IconButton label="更多操作" onClick={() => setOpen((current) => !current)}>
        <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
      </IconButton>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-9 z-40 min-w-36 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-1 shadow-[var(--wjn-shadow-md)]"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
                className={cn(
                  "flex h-8 w-full items-center gap-2 rounded-[var(--wjn-radius)] px-2 text-left text-xs font-medium transition-colors disabled:pointer-events-none disabled:opacity-45",
                  item.tone === "danger"
                    ? "text-[var(--wjn-error)] hover:bg-[var(--wjn-error-soft)]"
                    : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]",
                )}
              >
                {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Implement `ActionBar`**

Create `frontend/components/ui/action-bar.tsx`:

```tsx
"use client";

import type { ComponentType } from "react";

import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { OverflowMenu, type OverflowMenuItem } from "@/components/ui/overflow-menu";
import { cn } from "@/lib/utils";

export type ActionBarAction = {
  label: string;
  onClick: () => void;
  icon?: ComponentType<{ className?: string }>;
  disabled?: boolean;
  iconOnly?: boolean;
  tone?: "default" | "danger";
};

export function ActionBar({
  primary,
  secondary = [],
  overflow = [],
  className,
}: {
  primary?: ActionBarAction;
  secondary?: ActionBarAction[];
  overflow?: OverflowMenuItem[];
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-center justify-end gap-2", className)}>
      {secondary.map((action) => {
        const Icon = action.icon;
        if (action.iconOnly) {
          return (
            <IconButton
              key={action.label}
              label={action.label}
              disabled={action.disabled}
              tone={action.tone}
              onClick={action.onClick}
            >
              {Icon ? <Icon className="h-4 w-4" aria-hidden="true" /> : null}
            </IconButton>
          );
        }
        return (
          <Button
            key={action.label}
            type="button"
            variant={action.tone === "danger" ? "destructive" : "outline"}
            size="sm"
            disabled={action.disabled}
            onClick={action.onClick}
            className="gap-1.5"
          >
            {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
            {action.label}
          </Button>
        );
      })}
      {overflow.length > 0 ? <OverflowMenu items={overflow} /> : null}
      {primary ? (
        <Button
          type="button"
          size="sm"
          disabled={primary.disabled}
          onClick={primary.onClick}
          className="gap-1.5"
        >
          {primary.icon ? <primary.icon className="h-3.5 w-3.5" aria-hidden="true" /> : null}
          {primary.label}
        </Button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 6: Implement remaining primitives**

Create `frontend/components/ui/status-chip.tsx`:

```tsx
import { cn } from "@/lib/utils";

const STATUS_CLASS = {
  neutral: "border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] text-[var(--wjn-text-secondary)]",
  running: "border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue-strong)]",
  review: "border-[rgba(180,83,9,0.24)] bg-[var(--wjn-review-soft)] text-[var(--wjn-review)]",
  success: "border-[rgba(21,128,61,0.22)] bg-[var(--wjn-success-soft)] text-[var(--wjn-success)]",
  error: "border-[rgba(185,28,28,0.22)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)]",
} as const;

export function StatusChip({
  label,
  tone = "neutral",
  className,
}: {
  label: string;
  tone?: keyof typeof STATUS_CLASS;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 max-w-full items-center rounded-[var(--wjn-radius-pill)] border px-2 text-[11px] font-semibold leading-none",
        STATUS_CLASS[tone],
        className,
      )}
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
```

Create `frontend/components/ui/count-badge.tsx`:

```tsx
import { cn } from "@/lib/utils";

export function CountBadge({
  count,
  tone = "default",
  className,
}: {
  count: number;
  tone?: "default" | "review" | "success";
  className?: string;
}) {
  if (count <= 0) {
    return null;
  }
  return (
    <span
      className={cn(
        "wjn-tabular inline-flex h-4 min-w-4 items-center justify-center rounded-[var(--wjn-radius-pill)] px-1 text-[10px] font-bold leading-none text-white",
        tone === "review"
          ? "bg-[var(--wjn-review)]"
          : tone === "success"
            ? "bg-[var(--wjn-success)]"
            : "bg-[var(--wjn-blue)]",
        className,
      )}
    >
      {Math.min(count, 99)}
    </span>
  );
}
```

Create `frontend/components/ui/section-header.tsx`:

```tsx
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--wjn-text-muted)]">
            {eyebrow}
          </div>
        ) : null}
        <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">{title}</div>
        {description ? (
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--wjn-text-secondary)]">
            {description}
          </div>
        ) : null}
      </div>
      {actions ? <div className="shrink-0">{actions}</div> : null}
    </div>
  );
}
```

Create `frontend/components/ui/disclosure-section.tsx`:

```tsx
import type { ReactNode } from "react";

export function DisclosureSection({
  label,
  children,
  defaultOpen = false,
}: {
  label: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white"
    >
      <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-[var(--wjn-text-secondary)] marker:text-[var(--wjn-text-muted)]">
        {label}
      </summary>
      <div className="border-t border-[var(--wjn-line)] p-3">{children}</div>
    </details>
  );
}
```

Create `frontend/components/ui/panel.tsx`:

```tsx
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)]",
        className,
      )}
      {...props}
    />
  );
}
```

- [ ] **Step 7: Run shared primitive tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/ui/action-hierarchy.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: PASS.

---

## Task 2: WorkspaceChrome And WorkspaceHub

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- Test: `frontend/tests/unit/v2/WorkspaceChrome.test.tsx`
- Test: `frontend/tests/unit/v2/WorkspaceHub.test.tsx`

- [ ] **Step 1: Write WorkspaceChrome failing test**

Create `frontend/tests/unit/v2/WorkspaceChrome.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceChrome } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome";

describe("WorkspaceChrome", () => {
  it("renders one trusted chrome with surface switch and hub entry but without raw workspace id", () => {
    render(
      <WorkspaceChrome
        workspaceId="787153c9-3e09-4a48-b683-e261bf8d18b3"
        workspaceName="Federated LLM Study"
        workspaceTypeLabel="SCI论文"
        activeSurface="workbench"
        pendingReviewCount={2}
        activeRunCount={1}
        onOpenHub={() => undefined}
      />,
    );

    expect(screen.getByRole("link", { name: "Wenjin" })).toHaveAttribute("href", "/workspaces");
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Prism" })).toHaveAttribute("href", "/workspaces/787153c9-3e09-4a48-b683-e261bf8d18b3/prism");
    expect(screen.getByRole("button", { name: "资料库" })).toBeInTheDocument();
    expect(screen.getByText("Federated LLM Study")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("787153")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run WorkspaceChrome test to verify it fails**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/WorkspaceChrome.test.tsx
```

Expected: FAIL because `WorkspaceChrome` does not exist.

- [ ] **Step 3: Implement WorkspaceChrome**

Create `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome.tsx` with these exported props:

```tsx
"use client";

import Link from "next/link";
import { Archive, Search } from "lucide-react";

import { CountBadge } from "@/components/ui/count-badge";
import { StatusChip } from "@/components/ui/status-chip";
import { syncCurrentAuthCookie } from "@/stores/auth";

export type WorkspaceSurface = "workbench" | "prism";

export function WorkspaceChrome({
  workspaceId,
  workspaceName,
  workspaceTypeLabel,
  activeSurface,
  pendingReviewCount,
  activeRunCount,
  onOpenHub,
}: {
  workspaceId: string;
  workspaceName?: string | null;
  workspaceTypeLabel?: string | null;
  activeSurface: WorkspaceSurface;
  pendingReviewCount: number;
  activeRunCount: number;
  onOpenHub: () => void;
}) {
  return (
    <header className="wjn-topbar grid shrink-0 grid-cols-[minmax(190px,auto)_minmax(180px,1fr)_auto] items-center gap-3 px-3 py-2 sm:px-4">
      <Link
        href="/workspaces"
        aria-label="Wenjin"
        onClick={syncCurrentAuthCookie}
        className="flex min-w-0 items-center gap-3 rounded-[var(--wjn-radius)] text-[var(--wjn-text)] no-underline outline-none transition-colors hover:text-[var(--wjn-blue)] focus-visible:ring-2 focus-visible:ring-[var(--wjn-accent-line)]"
      >
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[rgba(255,255,255,0.56)] bg-[linear-gradient(145deg,var(--wjn-navy),var(--wjn-blue)_72%,#4d78b9)] text-[13px] font-semibold text-white shadow-[0_10px_24px_rgba(44,93,160,0.20)]">
          问
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold tracking-[-0.01em] text-[var(--wjn-text)]">Wenjin</div>
          <div className="hidden truncate text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--wjn-text-muted)] sm:block">
            Research OS
          </div>
        </div>
      </Link>
      <div className="hidden min-w-0 items-center gap-3 md:flex">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">
            {workspaceName ?? "Workspace"}
          </div>
          <div className="truncate text-[11px] text-[var(--wjn-text-muted)]">
            {workspaceTypeLabel ?? "工作空间"}
          </div>
        </div>
        {activeRunCount > 0 ? <StatusChip label="运行中" tone="running" /> : null}
        {pendingReviewCount > 0 ? <StatusChip label="待审阅" tone="review" /> : null}
      </div>
      <div className="flex min-w-0 items-center justify-end gap-2">
        <button
          type="button"
          className="hidden h-9 min-w-0 items-center gap-2 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white px-3 text-left text-xs text-[var(--wjn-text-muted)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-text)] lg:flex"
          aria-label="启动任务、查找资料或召集团队"
          title="启动任务、查找资料或召集团队"
        >
          <Search className="h-3.5 w-3.5 shrink-0 text-[var(--wjn-blue)]" aria-hidden="true" />
          <span className="truncate">启动任务、查找资料或召集团队...</span>
          <span className="ml-auto rounded border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--wjn-text-muted)]">
            ⌘K
          </span>
        </button>
        <nav
          role="tablist"
          aria-label="工作空间表面"
          className="flex shrink-0 items-center gap-1 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white p-1 shadow-[var(--wjn-shadow-sm)]"
        >
          <SurfaceTab href={`/workspaces/${workspaceId}`} active={activeSurface === "workbench"} label="Workbench" />
          <SurfaceTab href={`/workspaces/${workspaceId}/prism`} active={activeSurface === "prism"} label="Prism" count={pendingReviewCount} />
        </nav>
        <button
          type="button"
          aria-label="资料库"
          title="资料库"
          onClick={onOpenHub}
          className="relative inline-flex h-9 items-center gap-2 rounded-[var(--wjn-radius-lg)] border border-[var(--wjn-line)] bg-white px-3 text-xs font-semibold text-[var(--wjn-text-secondary)] shadow-[var(--wjn-shadow-sm)] transition-colors hover:border-[var(--wjn-accent-line)] hover:text-[var(--wjn-text)]"
        >
          <Archive className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">资料库</span>
          <CountBadge count={pendingReviewCount} tone="review" />
        </button>
      </div>
    </header>
  );
}

function SurfaceTab({ href, active, label, count = 0 }: { href: string; active: boolean; label: string; count?: number }) {
  return (
    <Link
      role="tab"
      aria-selected={active}
      href={href}
      onClick={syncCurrentAuthCookie}
      className={[
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[var(--wjn-radius)] px-3 text-[12.5px] font-semibold transition-colors",
        active
          ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
          : "text-[var(--wjn-text-secondary)] hover:bg-[rgba(15,23,42,0.05)] hover:text-[var(--wjn-text)]",
      ].join(" ")}
    >
      {label}
      <CountBadge count={count} tone="review" />
    </Link>
  );
}
```

- [x] **Step 4: Write WorkspaceHubDrawer failing test**

Create `frontend/tests/unit/v2/WorkspaceHubDrawer.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceHubDrawer } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer";

describe("WorkspaceHubDrawer", () => {
  it("presents room entry points as a lightweight hub without technical identifiers", () => {
    const onRoomSelect = vi.fn();
    render(
      <WorkspaceHubDrawer
        open
        activeRoom={null}
        completedRunCount={1}
        pendingReviewCount={2}
        onClose={() => undefined}
        onRoomSelect={onRoomSelect}
      />,
    );

    expect(screen.getByRole("dialog", { name: "资料库" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "文献资料" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "文档成果" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行记录，1 项新完成" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "审阅与决策，2 项待审阅" })).toBeInTheDocument();
    expect(screen.queryByText(/workspace/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sandbox/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "文献资料" }));
    expect(onRoomSelect).toHaveBeenCalledWith("library");
  });
});
```

- [x] **Step 5: Run WorkspaceHubDrawer test to verify it fails**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/WorkspaceHubDrawer.test.tsx
```

Expected: FAIL because `WorkspaceHubDrawer` does not exist.

- [x] **Step 6: Implement WorkspaceHubDrawer**

Create `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer.tsx`:

```tsx
"use client";

import { BookOpen, CheckSquare, FileText, History, ListTodo, MemoryStick, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { CountBadge } from "@/components/ui/count-badge";

export type WorkspaceHubRoomKey =
  | "library"
  | "documents"
  | "decisions"
  | "memory"
  | "runs"
  | "tasks"
  | "settings";

const GROUPS: Array<{
  title: string;
  items: Array<{ key: WorkspaceHubRoomKey; label: string; icon: LucideIcon }>;
}> = [
  {
    title: "资料",
    items: [
      { key: "library", label: "文献", icon: BookOpen },
      { key: "documents", label: "文档", icon: FileText },
    ],
  },
  {
    title: "产出",
    items: [
      { key: "decisions", label: "决策", icon: CheckSquare },
      { key: "memory", label: "记忆", icon: MemoryStick },
    ],
  },
  {
    title: "运行",
    items: [
      { key: "runs", label: "运行历史", icon: History },
      { key: "tasks", label: "任务", icon: ListTodo },
    ],
  },
  {
    title: "设置",
    items: [{ key: "settings", label: "设置", icon: Settings }],
  },
];

export function WorkspaceHubDrawer({
  open,
  activeRoom,
  activeRunCount,
  completedRunCount,
  pendingReviewCount,
  onClose,
  onRoomSelect,
}: {
  open: boolean;
  activeRoom: RoomKey | null;
  activeRunCount: number;
  completedRunCount: number;
  pendingReviewCount: number;
  onClose: () => void;
  onRoomSelect: (room: RoomKey) => void;
}) {
  if (!open) {
    return null;
  }

  return (
    <aside className="absolute right-4 top-[58px] z-30 w-[320px] max-w-[calc(100vw-32px)] rounded-[var(--wjn-radius-xl)] border border-[var(--wjn-line)] bg-white p-3 shadow-[var(--wjn-shadow-lg)]">
      <SectionHeader
        eyebrow="Workspace Hub"
        title="资料库"
        description="文献、文档、记忆、运行记录和设置统一放在这里。"
        actions={
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--wjn-radius)] px-2 py-1 text-xs font-semibold text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)]"
          >
            关闭
          </button>
        }
      />
      <div className="mt-3 space-y-3">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--wjn-text-muted)]">
              {group.title}
            </div>
            <div className="grid gap-1">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = activeRoom === item.key;
                const count =
                  item.key === "runs"
                    ? activeRunCount || completedRunCount
                    : item.key === "documents"
                      ? pendingReviewCount
                      : 0;
                return (
                  <button
                    key={item.key}
                    type="button"
                    aria-label={item.label === "运行历史" ? "运行历史" : item.label}
                    onClick={() => onRoomSelect(item.key)}
                    className={[
                      "flex h-9 items-center gap-2 rounded-[var(--wjn-radius)] px-2 text-left text-xs font-semibold transition-colors",
                      active
                        ? "bg-[var(--wjn-accent-soft)] text-[var(--wjn-accent-strong)]"
                        : "text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)] hover:text-[var(--wjn-text)]",
                    ].join(" ")}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    <CountBadge count={count} tone={item.key === "documents" ? "review" : "default"} />
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </aside>
  );
}
```

- [ ] **Step 7: Mount WorkspaceChrome and WorkspaceHubDrawer**

Modify `frontend/app/(workbench)/workspaces/[id]/page.tsx`:

- Replace direct `SurfaceSwitch` + `RoomsTopbar` render with `WorkspaceChrome`.
- Keep `activeRoom` state and room drawers unchanged.
- Add local `hubOpen` state.
- Pass `onOpenHub={() => setHubOpen(true)}`.
- Render `WorkspaceHubDrawer` near the shell root.
- When hub selects a room, call `setActiveRoom(room)` and close the hub.

- [ ] **Step 8: Update Prism route shell**

Modify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`:

- Use `WorkspaceChrome` with `activeSurface="prism"`.
- Provide `workspaceName` from loaded surface if available; fallback to `"Prism"`.
- Keep existing `LatexEditorShell` behavior.

- [ ] **Step 9: Run shell tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/WorkspaceChrome.test.tsx tests/unit/v2/WorkspaceHub.test.tsx tests/unit/v2/layout.test.tsx tests/unit/v2/prism-surface.test.tsx
```

Expected: PASS. If existing layout assertions still expect `RoomsTopbar`, update them to assert the Hub entry and room drawer behavior.

---

## Task 3: Current Work Cockpit

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/CurrentWorkCockpit.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NextDecisionCard.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceSnapshot.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ResearchTeamRoster.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunDiagnosticsDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Test: `frontend/tests/unit/v2/CurrentWorkCockpit.test.tsx`
- Test: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`

- [ ] **Step 1: Write cockpit failing test**

Create `frontend/tests/unit/v2/CurrentWorkCockpit.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CurrentWorkCockpit } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/CurrentWorkCockpit";
import type { RunView } from "@/lib/execution-run-view";

const run: RunView = {
  id: "run-1",
  title: "联邦学习结合大模型",
  summary: "正在整理证据和研究定位。",
  status: "running",
  progress: 42,
  nodeCount: 4,
  completedNodeCount: 1,
  durationLabel: "2 分钟",
  team: {
    members: [
      {
        id: "literature_specialist",
        displayName: "文献专家",
        status: "running",
        effectiveTools: ["semantic_scholar"],
        effectiveSkills: [],
      },
    ],
    qualityGates: [],
  },
};

describe("CurrentWorkCockpit", () => {
  it("shows the current objective, compact team, evidence snapshot, and one primary next decision", () => {
    const onOpenReview = vi.fn();
    render(
      <CurrentWorkCockpit
        run={run}
        evidenceCount={8}
        pendingReviewCount={3}
        canInterrupt
        onOpenEvidence={() => undefined}
        onOpenReview={onOpenReview}
        onOpenDiagnostics={() => undefined}
        onInterrupt={() => undefined}
      />,
    );

    expect(screen.getByText("联邦学习结合大模型")).toBeInTheDocument();
    expect(screen.getByText("文献专家")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "处理待审阅结果" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "查看证据" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "处理待审阅结果" }));
    expect(onOpenReview).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run cockpit test to verify it fails**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/CurrentWorkCockpit.test.tsx
```

Expected: FAIL because `CurrentWorkCockpit` does not exist.

- [ ] **Step 3: Implement `NextDecisionCard`**

Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/NextDecisionCard.tsx`:

```tsx
import { CheckCircle2, Database, PauseCircle } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";
import { Panel } from "@/components/ui/panel";
import { SectionHeader } from "@/components/ui/section-header";

export function NextDecisionCard({
  pendingReviewCount,
  evidenceCount,
  canInterrupt,
  onOpenReview,
  onOpenEvidence,
  onInterrupt,
}: {
  pendingReviewCount: number;
  evidenceCount: number;
  canInterrupt: boolean;
  onOpenReview: () => void;
  onOpenEvidence: () => void;
  onInterrupt: () => void;
}) {
  const primary =
    pendingReviewCount > 0
      ? { label: "处理待审阅结果", icon: CheckCircle2, onClick: onOpenReview }
      : evidenceCount > 0
        ? { label: "查看关键证据", icon: Database, onClick: onOpenEvidence }
        : undefined;

  return (
    <Panel className="p-3">
      <SectionHeader
        eyebrow="Next Decision"
        title={primary ? "下一步" : "等待任务推进"}
        description={primary ? "当前只保留最重要的用户动作。" : "问津会在需要你判断时把动作放到这里。"}
        actions={
          <ActionBar
            primary={primary}
            overflow={
              canInterrupt
                ? [{ label: "中断并补充", icon: PauseCircle, onClick: onInterrupt }]
                : []
            }
          />
        }
      />
    </Panel>
  );
}
```

- [ ] **Step 4: Implement `ResearchTeamRoster`**

Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ResearchTeamRoster.tsx`:

```tsx
import { Users } from "lucide-react";

import { DisclosureSection } from "@/components/ui/disclosure-section";
import { Panel } from "@/components/ui/panel";
import { SectionHeader } from "@/components/ui/section-header";
import { StatusChip } from "@/components/ui/status-chip";
import type { RunViewTeam } from "@/lib/execution-run-view";

export function ResearchTeamRoster({ team }: { team: RunViewTeam | null | undefined }) {
  if (!team || team.members.length === 0) {
    return null;
  }

  return (
    <Panel className="p-3">
      <SectionHeader
        eyebrow="Research Team"
        title="研究团队"
        description={`${team.members.length} 个成员正在按职责推进。`}
      />
      <div className="mt-3 grid gap-1.5">
        {team.members.slice(0, 4).map((member) => (
          <div key={member.id} className="flex min-w-0 items-center gap-2 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-[var(--wjn-surface-subtle)] px-2 py-2">
            <Users className="h-3.5 w-3.5 shrink-0 text-[var(--wjn-blue)]" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-semibold text-[var(--wjn-text)]">{member.displayName}</div>
              <div className="truncate text-[11px] text-[var(--wjn-text-muted)]">{memberCapabilitySummary(member)}</div>
            </div>
            <StatusChip label={workItemStatusLabel(member.status)} tone={member.status === "running" ? "running" : "neutral"} />
          </div>
        ))}
      </div>
      <div className="mt-3">
        <DisclosureSection label="团队权限与质量门">
          <div className="space-y-2 text-xs text-[var(--wjn-text-secondary)]">
            {team.members.map((member) => (
              <div key={member.id}>
                <span className="font-semibold text-[var(--wjn-text)]">{member.displayName}</span>
                <span> · {member.effectiveTools.length + member.effectiveSkills.length} 项权限/技能</span>
              </div>
            ))}
            {team.qualityGates.map((gate) => (
              <div key={gate.id}>质量门：{gate.id} · {gate.status}</div>
            ))}
          </div>
        </DisclosureSection>
      </div>
    </Panel>
  );
}

function workItemStatusLabel(status: string): string {
  if (status === "launching") return "准备中";
  if (status === "running") return "处理中";
  if (status === "completed" || status === "passed" || status === "pass") return "已完成";
  if (status === "failed" || status === "fail" || status === "failed_partial") return "失败";
  if (status === "review" || status === "warning") return "待审阅";
  return "待命";
}

function memberCapabilitySummary(member: RunViewTeam["members"][number]): string {
  const count = member.effectiveTools.length + member.effectiveSkills.length;
  if (count > 0) return "权限与技能已配置";
  if (member.status === "running" || member.status === "launching") return "正在处理";
  if (member.status === "completed") return "已完成";
  return "按任务需要待命";
}
```

- [ ] **Step 5: Implement `EvidenceSnapshot` and `CurrentWorkCockpit`**

Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceSnapshot.tsx`:

```tsx
import { Database } from "lucide-react";

import { Panel } from "@/components/ui/panel";
import { SectionHeader } from "@/components/ui/section-header";

export function EvidenceSnapshot({
  evidenceCount,
  onOpenEvidence,
}: {
  evidenceCount: number;
  onOpenEvidence: () => void;
}) {
  return (
    <Panel className="p-3">
      <SectionHeader
        eyebrow="Evidence"
        title="证据摘要"
        description={evidenceCount > 0 ? "已有可用于判断和写作的材料。" : "任务推进后会在这里沉淀证据。"}
        actions={
          evidenceCount > 0 ? (
            <button
              type="button"
              onClick={onOpenEvidence}
              className="inline-flex h-8 items-center gap-1.5 rounded-[var(--wjn-radius)] border border-[var(--wjn-line)] bg-white px-2 text-xs font-semibold text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]"
            >
              <Database className="h-3.5 w-3.5" aria-hidden="true" />
              详情
            </button>
          ) : null
        }
      />
      <div className="wjn-tabular mt-3 text-2xl font-semibold text-[var(--wjn-text)]">{evidenceCount}</div>
    </Panel>
  );
}
```

Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/CurrentWorkCockpit.tsx`:

```tsx
import { Activity } from "lucide-react";

import { Panel } from "@/components/ui/panel";
import { SectionHeader } from "@/components/ui/section-header";
import { StatusChip } from "@/components/ui/status-chip";
import type { RunView } from "@/lib/execution-run-view";

import { EvidenceSnapshot } from "./EvidenceSnapshot";
import { NextDecisionCard } from "./NextDecisionCard";
import { ResearchTeamRoster } from "./ResearchTeamRoster";

export function CurrentWorkCockpit({
  run,
  evidenceCount,
  pendingReviewCount,
  canInterrupt,
  onOpenEvidence,
  onOpenReview,
  onOpenDiagnostics,
  onInterrupt,
}: {
  run: RunView | null;
  evidenceCount: number;
  pendingReviewCount: number;
  canInterrupt: boolean;
  onOpenEvidence: () => void;
  onOpenReview: () => void;
  onOpenDiagnostics: () => void;
  onInterrupt: () => void;
}) {
  if (!run) {
    return (
      <div className="grid h-full place-items-center p-6">
        <Panel className="max-w-md p-5 text-center">
          <SectionHeader
            eyebrow="Current Work"
            title="还没有进行中的任务"
            description="在左侧描述研究目标后，问津会组织团队、沉淀证据，并把下一步动作放在这里。"
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="mx-auto grid max-w-4xl gap-3">
        <Panel className="p-4">
          <SectionHeader
            eyebrow="Current Work"
            title={run.title}
            description={run.summary}
            actions={<StatusChip label={statusLabel(run.status)} tone={run.status === "running" ? "running" : "neutral"} />}
          />
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-[var(--wjn-radius-pill)] bg-[var(--wjn-surface-subtle)]">
              <div className="h-full rounded-[var(--wjn-radius-pill)] bg-[var(--wjn-blue)]" style={{ width: `${Math.max(4, Math.min(100, run.progress ?? 0))}%` }} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px] text-[var(--wjn-text-muted)]">
              <span>{run.completedNodeCount ?? 0}/{run.nodeCount ?? 0} 步完成</span>
              <button type="button" onClick={onOpenDiagnostics} className="inline-flex items-center gap-1 font-semibold text-[var(--wjn-text-secondary)] hover:text-[var(--wjn-text)]">
                <Activity className="h-3 w-3" aria-hidden="true" />
                运行详情
              </button>
            </div>
          </div>
        </Panel>
        <NextDecisionCard
          pendingReviewCount={pendingReviewCount}
          evidenceCount={evidenceCount}
          canInterrupt={canInterrupt}
          onOpenReview={onOpenReview}
          onOpenEvidence={onOpenEvidence}
          onInterrupt={onInterrupt}
        />
        <ResearchTeamRoster team={run.team} />
        <EvidenceSnapshot evidenceCount={evidenceCount} onOpenEvidence={onOpenEvidence} />
      </div>
    </div>
  );
}

function statusLabel(status: string): string {
  if (status === "running") return "运行中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "cancelled") return "已取消";
  return "处理中";
}
```

- [ ] **Step 6: Move diagnostics into drawer**

Create `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/RunDiagnosticsDrawer.tsx`:

```tsx
import type { ExecutionRecord } from "@/lib/api/types";

import { DisclosureSection } from "@/components/ui/disclosure-section";
import { Panel } from "@/components/ui/panel";
import { SectionHeader } from "@/components/ui/section-header";

import { NodeInspector } from "./NodeInspector";

export function RunDiagnosticsDrawer({
  open,
  record,
  selectedNodeId,
  onClose,
}: {
  open: boolean;
  record: ExecutionRecord | null;
  selectedNodeId: string | null;
  onClose: () => void;
}) {
  if (!open || !record) {
    return null;
  }
  const nodeId =
    selectedNodeId && record.node_states[selectedNodeId]
      ? selectedNodeId
      : Object.keys(record.node_states)[0] ?? null;
  const node = nodeId
    ? record.graph_structure?.nodes.find((item) => item.id === nodeId) ?? { id: nodeId, type: record.node_states[nodeId]?.node_type ?? "node" }
    : null;
  const state = nodeId ? record.node_states[nodeId] : null;

  return (
    <div className="absolute inset-y-0 right-0 z-30 w-[420px] max-w-full border-l border-[var(--wjn-line)] bg-[var(--wjn-bg-base)] p-3 shadow-[var(--wjn-shadow-lg)]">
      <Panel className="h-full overflow-y-auto p-3">
        <SectionHeader
          eyebrow="Diagnostics"
          title="运行详情"
          description="节点输入输出、工具调用和诊断信息只在这里展示。"
          actions={
            <button type="button" onClick={onClose} className="rounded-[var(--wjn-radius)] px-2 py-1 text-xs font-semibold text-[var(--wjn-text-secondary)] hover:bg-[var(--wjn-surface-subtle)]">
              关闭
            </button>
          }
        />
        <div className="mt-3">
          <DisclosureSection label="节点详情" defaultOpen>
            <NodeInspector node={node} state={state} />
          </DisclosureSection>
        </div>
      </Panel>
    </div>
  );
}
```

- [ ] **Step 7: Wire cockpit into LiveWorkflowPanel**

Modify `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`:

- Compute `const selectedRunView = selectedRecord ? runViewFromExecution(selectedRecord) : null`.
- Replace the default `WorkbenchHeader` tab shell with `CurrentWorkCockpit`.
- Keep `ReviewView` and `EvidenceView` reachable through local detail state.
- Use `RunDiagnosticsDrawer` for technical details.
- Keep intervention logic unchanged, but expose it through `NextDecisionCard`/overflow instead of a permanently disabled header button.

- [ ] **Step 8: Run cockpit tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/CurrentWorkCockpit.test.tsx tests/unit/v2/LiveWorkflowPanel.test.tsx tests/unit/lib/execution-run-view.test.ts
```

Expected: PASS. Update existing `LiveWorkflowPanel` tests to assert fewer peer actions and no default raw technical payload.

---

## Task 4: Workspace Hub Room Drawer Convergence

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/LibraryDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/DocumentsDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/RunsDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/TasksDrawer.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/rooms/SettingsPage.tsx`
- Test: `frontend/tests/unit/v2/rooms/RunsDrawer.test.tsx`

- [ ] **Step 1: Update room action hierarchy tests**

Modify `frontend/tests/unit/v2/rooms/RunsDrawer.test.tsx` to assert:

```tsx
expect(screen.getByRole("heading", { name: "运行历史" })).toBeInTheDocument();
expect(screen.queryByText("输入预览")).not.toBeInTheDocument();
expect(screen.getByRole("button", { name: "运行详情" })).toBeInTheDocument();
```

- [ ] **Step 2: Move low-frequency room actions into overflow**

For each room drawer:

- Primary action stays in the drawer header.
- Delete/export/copy id actions move to `OverflowMenu`.
- Raw details move to `DisclosureSection`.
- Long titles use `truncate` or `line-clamp-2`.

- [ ] **Step 3: Run room tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/rooms/RunsDrawer.test.tsx tests/unit/v2/rooms/LibraryDrawer.test.tsx tests/unit/v2/rooms/DocumentsDrawer.test.tsx tests/unit/v2/rooms/TasksDrawer.test.tsx
```

Expected: PASS.

---

## Task 5: Prism Shell

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/prism/PrismShell.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/prism/ManuscriptBar.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/prism/PrismReviewInspector.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- Modify: `frontend/components/latex/LatexEditorShell.tsx`
- Modify: `frontend/components/prism/PrismReviewList.tsx`
- Test: `frontend/tests/unit/v2/prism-shell.test.tsx`

- [ ] **Step 1: Write PrismShell failing test**

Create `frontend/tests/unit/v2/prism-shell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ManuscriptBar } from "@/app/(workbench)/workspaces/[id]/prism/ManuscriptBar";

describe("ManuscriptBar", () => {
  it("prioritizes review when pending changes exist", () => {
    render(
      <ManuscriptBar
        title="Federated LLM Study"
        mainFile="main.tex"
        saved
        compiling={false}
        pendingReviewCount={2}
        onSave={() => undefined}
        onCompile={() => undefined}
        onOpenReview={() => undefined}
      />,
    );

    expect(screen.getByText("Federated LLM Study")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "审阅修改" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run PrismShell test to verify it fails**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/prism-shell.test.tsx
```

Expected: FAIL because `ManuscriptBar` does not exist.

- [ ] **Step 3: Implement ManuscriptBar**

Create `frontend/app/(workbench)/workspaces/[id]/prism/ManuscriptBar.tsx`:

```tsx
"use client";

import { CheckCircle2, FileText, Play, Save } from "lucide-react";

import { ActionBar } from "@/components/ui/action-bar";
import { StatusChip } from "@/components/ui/status-chip";

export function ManuscriptBar({
  title,
  mainFile,
  saved,
  compiling,
  pendingReviewCount,
  onSave,
  onCompile,
  onOpenReview,
}: {
  title: string;
  mainFile: string;
  saved: boolean;
  compiling: boolean;
  pendingReviewCount: number;
  onSave: () => void;
  onCompile: () => void;
  onOpenReview: () => void;
}) {
  const primary =
    pendingReviewCount > 0
      ? { label: "审阅修改", icon: CheckCircle2, onClick: onOpenReview }
      : !saved
        ? { label: "保存", icon: Save, onClick: onSave }
        : { label: compiling ? "编译中" : "编译", icon: Play, onClick: onCompile, disabled: compiling };

  return (
    <div className="flex min-h-12 items-center gap-3 border-b border-[var(--wjn-line)] bg-white px-4">
      <FileText className="h-4 w-4 shrink-0 text-[var(--wjn-blue)]" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-[var(--wjn-text)]">{title}</div>
        <div className="truncate text-[11px] text-[var(--wjn-text-muted)]">主文件 {mainFile}</div>
      </div>
      <StatusChip label={saved ? "已保存" : "未保存"} tone={saved ? "success" : "review"} />
      <ActionBar
        primary={primary}
        secondary={pendingReviewCount > 0 ? [{ label: compiling ? "编译中" : "编译", icon: Play, onClick: onCompile, disabled: compiling }] : []}
      />
    </div>
  );
}
```

- [ ] **Step 4: Mount Prism shell**

Modify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx` and `frontend/components/latex/LatexEditorShell.tsx` so:

- Workspace-level chrome stays `WorkspaceChrome`.
- Prism-level `ManuscriptBar` controls save/compile/review priority.
- Existing editor/PDF/inspector behavior remains intact.
- File protection, delete project, compile logs, BibTeX sync move to overflow/tool drawer.

- [ ] **Step 5: Run Prism tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/v2/prism-shell.test.tsx tests/unit/v2/prism-surface.test.tsx
```

Expected: PASS.

---

## Task 6: Public, Auth, Workspace List, Admin Convergence

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/pricing/page.tsx`
- Modify: `frontend/app/(auth)/login/page.tsx`
- Modify: `frontend/app/(auth)/register/page.tsx`
- Modify: `frontend/app/workspaces/page.tsx`
- Modify: `frontend/app/dashboard/admin/layout.tsx`
- Modify: `frontend/app/dashboard/admin/components/AdminPageHeader.tsx`
- Modify: `frontend/app/dashboard/admin/components/AdminSidebar.tsx`
- Test: `frontend/tests/unit/home-page.test.tsx`
- Test: `frontend/tests/unit/v2/layout.test.tsx`
- Test: `frontend/tests/unit/admin-models-page.test.tsx`

- [ ] **Step 1: Update workspace list tests**

Modify or add a test in `frontend/tests/unit/v2/layout.test.tsx` or create `frontend/tests/unit/workspaces-page-actions.test.tsx` to assert:

```tsx
expect(screen.getByRole("button", { name: "新建工作空间" })).toBeInTheDocument();
expect(screen.queryByRole("button", { name: "Delete workspace" })).not.toBeInTheDocument();
expect(screen.getAllByRole("button", { name: "更多操作" }).length).toBeGreaterThan(0);
```

- [ ] **Step 2: Move workspace card danger actions into overflow**

Modify `frontend/app/workspaces/page.tsx`:

- Remove visible delete button from card top.
- Add row/card overflow menu.
- Keep card primary action as entering workspace.
- Keep create workspace as page primary action.

- [ ] **Step 3: Simplify Auth pages**

Modify login/register:

- Keep form and one alternate auth link.
- Remove secondary marketing CTAs that compete with form submission.
- Keep mature white/navy style.

- [ ] **Step 4: Align Admin header actions**

Modify `AdminPageHeader`:

- Use `ActionBar`.
- Allow exactly one `primaryAction`.
- Put secondary/danger actions in overflow.

- [ ] **Step 5: Run page tests**

Run:

```bash
cd frontend && npm run test -- tests/unit/home-page.test.tsx tests/unit/v2/layout.test.tsx tests/unit/admin-models-page.test.tsx
```

Expected: PASS.

---

## Task 7: Cleanup, Docs, And Regression

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `docs/current/wenjin-research-navigation-uiux.md`
- Modify: `docs/current/documentation-map.md`
- Modify: `docs/current/workspace-current-state.md` if shell behavior changes user-visible room behavior.

- [ ] **Step 1: Scan for disallowed new token usage**

Run:

```bash
rg -n -e "--v2-" -e "--glass-" -e "--brand-" -e "--compute-" \
  frontend/app frontend/components frontend/lib \
  -g '*.{ts,tsx,css}'
```

Expected: remaining matches are compatibility aliases in `frontend/app/globals.css` or explicitly documented old components only. New components from this plan have no matches.

- [ ] **Step 2: Scan for raw technical default labels**

Run:

```bash
rg -n "输入预览|raw payload|node input|tool_invocation|template id|workspace id|execution id|sandbox logs" \
  frontend/app frontend/components \
  -g '*.{ts,tsx}'
```

Expected: matches only inside diagnostics/detail components or test fixtures.

- [ ] **Step 3: Run focused unit suite**

Run:

```bash
cd frontend && npm run test -- \
  tests/unit/ui/action-hierarchy.test.tsx \
  tests/unit/ui/commit-action-bar.test.tsx \
  tests/unit/v2/WorkspaceChrome.test.tsx \
  tests/unit/v2/WorkspaceChromeAuth.test.tsx \
  tests/unit/v2/WorkspaceHubDrawer.test.tsx \
  tests/unit/v2/LiveWorkflowPanel.test.tsx \
  tests/unit/v2/layout.test.tsx \
  tests/unit/v2/prism-surface.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run full frontend typecheck and build**

Run:

```bash
cd frontend && npm run typecheck && npm run build
```

Expected: both commands exit 0.

- [ ] **Step 5: Rebuild local Docker frontend**

Run:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build frontend nginx
docker compose ps frontend nginx gateway dataservice
```

Expected: frontend, nginx, gateway, and dataservice are healthy.

- [ ] **Step 6: Browser smoke**

Verify in browser:

1. Open `http://localhost:2026/`.
2. Confirm login state does not redirect unexpectedly.
3. Open `/workspaces`.
4. Enter a workspace.
5. Confirm there is one main workspace chrome.
6. Open Workspace Hub and enter Library/Documents/Runs.
7. Switch Workbench -> Prism -> Workbench.
8. Confirm Current Work Cockpit default view hides raw technical details.
9. Confirm team real-name roster uses display names.
10. Open Admin model or credit page.

Expected: no login regression, no blank pages, no overlapping text, no default technical payload.

- [ ] **Step 7: Update docs**

Update `docs/current/wenjin-research-navigation-uiux.md`:

```markdown
Current full-shell migration source: `docs/superpowers/specs/2026-06-05-full-shell-uiux-refactor-design.md`.

Workspace now uses a single trusted chrome, a Workspace Hub for rooms, and Current Work Cockpit as the default execution surface. Technical run details are available through diagnostics instead of default panels.
```

Update `docs/current/documentation-map.md` if it lacks the new full-shell spec entry.

---

## Implementation Order

1. Task 0 Audit.
2. Task 1 Shared UI Foundation.
3. Task 2 WorkspaceChrome and WorkspaceHub.
4. Task 3 Current Work Cockpit.
5. Task 4 Workspace Hub Room Drawer Convergence.
6. Task 5 Prism Shell.
7. Task 6 Public/Auth/Workspace List/Admin Convergence.
8. Task 7 Cleanup, Docs, Regression.

## Implementation Record 2026-06-05

Completed in this pass:

- Added shared action primitives: `ActionBar`, `IconButton`, `OverflowMenu`, `CountBadge`, `StatusChip`, `SectionHeader`, `DisclosureSection`, and `Panel`.
- Replaced the old workspace `SurfaceSwitch` plus permanent `RoomsTopbar` with `WorkspaceChrome` and `WorkspaceHubDrawer`.
- Routed Workbench and Prism through the same trusted chrome. Prism keeps Hub access by routing room entries back to the Workbench room URL.
- Moved room navigation into Workspace Hub with user-facing labels: 文献资料, 文档成果, 审阅与决策, 项目记忆, 运行记录, 任务清单, 工作设置.
- Removed default exposure of raw workspace id, sandbox metric, input preview, and technical subagent template names from the top-level workbench view.
- Moved global running/review status ownership to WorkspaceChrome so the right workbench does not duplicate “运行中”.
- Replaced `CommitActionBar` three-peer-button layout with shared action hierarchy: primary accept-all, secondary selected-save, overflow discard.
- Changed team member capability copy from “权限与技能已配置” to “能力已就绪”.
- Updated current UIUX docs to point to the full-shell migration source.

Verified:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
cd frontend && npm run test -- \
  tests/unit/v2/layout.test.tsx \
  tests/unit/v2/WorkspaceChrome.test.tsx \
  tests/unit/v2/WorkspaceChromeAuth.test.tsx \
  tests/unit/v2/WorkspaceHubDrawer.test.tsx \
  tests/unit/v2/prism-surface.test.tsx \
  tests/unit/v2/LiveWorkflowPanel.test.tsx \
  tests/unit/ui/action-hierarchy.test.tsx \
  tests/unit/ui/commit-action-bar.test.tsx
docker compose -f docker-compose.yml -f docker-compose.local-build.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.local-build.yml ps
```

Browser smoke on `http://localhost:2026`:

- Logged in to the local compose instance.
- Opened `/workspaces` and entered a workspace.
- Verified one workspace chrome, no old room topbar, no raw workspace id text, no default sandbox metric, no default input preview, no default raw `literature_synthesizer` label.
- Opened Workspace Hub and verified user-facing room entries with no raw id or sandbox text.
- Switched Workbench -> Prism while logged in and confirmed there was no login redirect.
- Verified Prism also uses WorkspaceChrome and keeps the Hub entry.
- Opened Admin models and credit pricing pages; both rendered under the admin shell without login regression.
- Filtered browser logs for `localhost:2026`: no warnings or errors.

Operational note:

- Running `docker compose up --build -d frontend` against the default compose file can fail if the database revision is newer than the prebuilt remote backend image. Local verification must use `docker-compose.local-build.yml` so backend images include local Alembic revisions.

## Completion Criteria

- The spec requirements in `docs/superpowers/specs/2026-06-05-full-shell-uiux-refactor-design.md` map to implemented surfaces or documented diagnostics.
- Workspace top-level navigation is reduced to one trusted chrome.
- Rooms are reachable through Workspace Hub rather than seven permanent peer buttons.
- Current Work Cockpit shows one primary next decision.
- Technical run details are default-hidden but accessible.
- Prism has a manuscript-level action hierarchy.
- Workspace list danger actions are in overflow.
- Admin uses consistent console action grouping.
- Tests, typecheck, build, Docker health, and browser smoke all pass.
