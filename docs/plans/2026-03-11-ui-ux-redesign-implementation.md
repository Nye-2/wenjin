# UI/UX Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform AcademiaGPT frontend from bright/playful style to "学术深空风" (Academic Deep Sky) dark academic theme.

**Architecture:** CSS variables-first approach with Tailwind config updates. Modify global styles, then glass components, then UI components, then page-level adjustments. Visual verification via dev server.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 3.4, Framer Motion

---

## Task 1: Update Global CSS Variables

**Files:**
- Modify: `frontend/app/globals.css`

**Step 1: Replace background and text color variables**

Replace lines 5-41 in `globals.css`:

```css
:root {
  /* Background Levels */
  --bg-base: #0C1222;
  --bg-elevated: #151D30;
  --bg-surface: #1E293B;
  --bg-muted: #243044;

  /* Accent Colors */
  --accent-primary: #2563EB;
  --accent-secondary: #38BDF8;
  --accent-tertiary: #0EA5E9;
  --accent-gold: #CA8A04;

  /* Semantic Colors */
  --semantic-success: #10B981;
  --semantic-warning: #F59E0B;
  --semantic-error: #EF4444;
  --semantic-info: #3B82F6;

  /* Text Colors */
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  --text-inverse: #0F172A;

  /* Border Colors */
  --border-default: #2D3A4F;
  --border-subtle: #1E293B;
  --border-focus: #3B82F6;

  /* Glass Effect - Updated */
  --glass-bg: rgba(21, 29, 48, 0.85);
  --glass-bg-elevated: rgba(30, 41, 59, 0.9);
  --glass-blur: blur(24px) saturate(120%);
  --glass-border: rgba(56, 189, 248, 0.12);
  --glass-shadow:
    0 4px 24px rgba(0, 0, 0, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
  --glass-shadow-elevated:
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);

  /* Motion Tokens - Keep existing */
  --ease-apple: cubic-bezier(0.16, 1, 0.3, 1);
  --duration-fast: 150ms;
  --duration-normal: 300ms;
  --duration-slow: 500ms;
}
```

**Step 2: Update body background**

Replace line 63-66:

```css
body {
  color: var(--text-primary);
  background: var(--bg-base);
}
```

**Step 3: Update glass-card classes**

Replace lines 69-85:

```css
@layer components {
  .glass-card {
    @apply relative overflow-hidden rounded-2xl;
    background: var(--glass-bg);
    backdrop-filter: var(--glass-blur);
    -webkit-backdrop-filter: var(--glass-blur);
    border: 1px solid var(--glass-border);
    box-shadow: var(--glass-shadow);
  }

  .glass-card-elevated {
    @apply glass-card;
    background: var(--glass-bg-elevated);
    box-shadow: var(--glass-shadow-elevated);
  }
}
```

**Step 4: Update gradient-text classes**

Replace lines 88-109:

```css
/* Gradient Text - Simplified */
.gradient-text {
  color: var(--text-primary);
}

.gradient-text-subtle {
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.gradient-text-shimmer {
  background: linear-gradient(
    90deg,
    var(--accent-primary) 0%,
    var(--accent-secondary) 50%,
    var(--accent-primary) 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: gradient-x 3s ease infinite;
}
```

**Step 5: Update scrollbar styles**

Replace lines 130-146:

```css
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-elevated);
}

::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--accent-primary);
}
```

**Step 6: Update selection and focus styles**

Replace lines 149-157:

```css
::selection {
  background: rgba(37, 99, 235, 0.3);
}

:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: 2px;
}
```

**Step 7: Update link styles**

Replace lines 160-167:

```css
a {
  color: var(--accent-secondary);
  transition: color var(--duration-fast) ease;
}

a:hover {
  color: var(--accent-primary);
}
```

**Step 8: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 9: Commit**

```bash
git add frontend/app/globals.css
git commit -m "style: update global CSS variables for Academic Deep Sky theme"
```

---

## Task 2: Update Tailwind Configuration

**Files:**
- Modify: `frontend/tailwind.config.ts`

**Step 1: Replace color configuration**

Replace lines 10-19:

```typescript
colors: {
  academic: {
    primary: "#2563EB",
    secondary: "#38BDF8",
    tertiary: "#0EA5E9",
    success: "#10B981",
    warning: "#F59E0B",
    error: "#EF4444",
    gold: "#CA8A04",
  },
  background: {
    base: "#0C1222",
    elevated: "#151D30",
    surface: "#1E293B",
    muted: "#243044",
  },
  border: {
    default: "#2D3A4F",
    subtle: "#1E293B",
    focus: "#3B82F6",
  },
},
```

**Step 2: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/tailwind.config.ts
git commit -m "style: update Tailwind colors for Academic Deep Sky theme"
```

---

## Task 3: Update LiquidGlassCard Component

**Files:**
- Modify: `frontend/components/glass/liquid-glass-card.tsx`

**Step 1: Update component styles**

Replace the entire file content:

```tsx
"use client";

import { forwardRef } from "react";
import { motion, HTMLMotionProps } from "framer-motion";
import { cn } from "@/lib/utils";
import { scaleIn, defaultTransition } from "@/lib/animations";

interface LiquidGlassCardProps extends HTMLMotionProps<"div"> {
  variant?: "default" | "elevated" | "floating";
  glow?: boolean;
}

export const LiquidGlassCard = forwardRef<HTMLDivElement, LiquidGlassCardProps>(
  ({ className, variant = "default", glow = false, children, ...props }, ref) => {
    return (
      <motion.div
        ref={ref}
        className={cn(
          "relative overflow-hidden rounded-2xl",
          "bg-[var(--glass-bg)]",
          "backdrop-blur-[var(--glass-blur)]",
          "border border-[var(--glass-border)]",
          "shadow-[var(--glass-shadow)]",
          variant === "elevated" && "bg-[var(--glass-bg-elevated)] shadow-[var(--glass-shadow-elevated)]",
          variant === "floating" && "hover:shadow-[var(--glass-shadow-elevated)] hover:-translate-y-0.5 transition-transform duration-200",
          glow && "before:absolute before:inset-0 before:rounded-2xl before:p-[1px] before:bg-gradient-to-br before:from-[var(--accent-secondary)]/20 before:to-transparent",
          className
        )}
        variants={scaleIn}
        initial="initial"
        animate="animate"
        transition={{ ...defaultTransition, duration: 0.3 }}
        {...props}
      >
        {children}
      </motion.div>
    );
  }
);

LiquidGlassCard.displayName = "LiquidGlassCard";
```

**Step 2: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/components/glass/liquid-glass-card.tsx
git commit -m "style: update LiquidGlassCard for Academic Deep Sky theme"
```

---

## Task 4: Update GradientText Component

**Files:**
- Modify: `frontend/components/glass/gradient-text.tsx`

**Step 1: Add variant support for gradient text**

Replace the entire file content:

```tsx
"use client";

import { cn } from "@/lib/utils";

interface GradientTextProps {
  children: React.ReactNode;
  variant?: "default" | "subtle" | "shimmer";
  className?: string;
}

export function GradientText({
  children,
  variant = "default",
  className,
}: GradientTextProps) {
  if (variant === "default") {
    return (
      <span className={cn("text-[var(--text-primary)]", className)}>
        {children}
      </span>
    );
  }

  if (variant === "subtle") {
    return (
      <span
        className={cn(
          "bg-gradient-to-r from-[var(--accent-primary)] to-[var(--accent-secondary)] bg-clip-text text-transparent",
          className
        )}
      >
        {children}
      </span>
    );
  }

  // shimmer variant
  return (
    <span className={cn("gradient-text-shimmer", className)}>
      {children}
    </span>
  );
}
```

**Step 2: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/components/glass/gradient-text.tsx
git commit -m "style: update GradientText with variant support"
```

---

## Task 5: Update Button Component

**Files:**
- Modify: `frontend/components/ui/button.tsx`

**Step 1: Update button variants**

Replace the entire file content:

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]",
        destructive:
          "bg-red-500/15 text-[var(--semantic-error)] border border-red-500/30 hover:bg-red-500/25",
        outline:
          "border border-[var(--border-default)] bg-transparent hover:bg-[var(--bg-surface)] hover:border-[var(--accent-secondary)] text-[var(--text-primary)]",
        secondary:
          "bg-[var(--accent-primary)]/15 text-[var(--accent-secondary)] border border-[var(--accent-secondary)]/30 hover:bg-[var(--accent-primary)]/25",
        ghost:
          "hover:bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
        link:
          "text-[var(--accent-secondary)] underline-offset-4 hover:underline hover:text-[var(--accent-primary)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 rounded-lg px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

**Step 2: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/components/ui/button.tsx
git commit -m "style: update Button variants for Academic Deep Sky theme"
```

---

## Task 6: Update Input Component

**Files:**
- Modify: `frontend/components/ui/input.tsx`

**Step 1: Read current input component** (already read, now update)

Replace the entire file content:

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-muted)]/50 px-4 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
          "focus:outline-none focus:border-[var(--border-focus)] focus:ring-2 focus:ring-[var(--accent-primary)]/20",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "transition-all duration-200",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
```

**Step 2: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 3: Commit**

```bash
git add frontend/components/ui/input.tsx
git commit -m "style: update Input styles for Academic Deep Sky theme"
```

---

## Task 7: Update Card Component

**Files:**
- Modify: `frontend/components/ui/card.tsx`

**Step 1: Read current card component** (need to read first)

**Step 2: Update card styles with new theme colors**

**Step 3: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
git add frontend/components/ui/card.tsx
git commit -m "style: update Card styles for Academic Deep Sky theme"
```

---

## Task 8: Update Badge Component

**Files:**
- Modify: `frontend/components/ui/badge.tsx`

**Step 1: Read current badge component** (need to read first)

**Step 2: Update badge styles with new theme colors**

**Step 3: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
git add frontend/components/ui/badge.tsx
git commit -m "style: update Badge styles for Academic Deep Sky theme"
```

---

## Task 9: Update Homepage

**Files:**
- Modify: `frontend/app/page.tsx`

**Step 1: Update decorative gradient backgrounds**

Replace lines 72-76:

```tsx
{/* Decorative gradient */}
<div className="absolute inset-0 -z-10 overflow-hidden">
  <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[var(--accent-primary)]/10 rounded-full blur-3xl" />
  <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[var(--accent-secondary)]/10 rounded-full blur-3xl" />
</div>
```

**Step 2: Update GradientText to use default variant**

Replace line 45:

```tsx
<GradientText>AcademiaGPT</GradientText>
```

Replace line 84:

```tsx
<GradientText variant="subtle">Powerful Features</GradientText>
```

**Step 3: Update CTA button style**

Replace lines 123-131:

```tsx
<motion.a
  href="/workspaces"
  className="inline-flex items-center gap-2 px-8 py-4 text-base font-semibold text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] rounded-xl cursor-pointer hover:shadow-lg transition-shadow"
  whileHover={{ scale: 1.02 }}
  whileTap={{ scale: 0.98 }}
>
  Create Workspace
  <Send className="w-4 h-4" />
</motion.a>
```

**Step 4: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 5: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "style: update Homepage for Academic Deep Sky theme"
```

---

## Task 10: Update Workspaces Page

**Files:**
- Modify: `frontend/app/workspaces/page.tsx`

**Step 1: Update page background**

Replace line 83:

```tsx
<div className="min-h-screen bg-[var(--bg-base)]">
```

**Step 2: Update input styles**

Replace lines 113-118:

```tsx
<input
  type="text"
  placeholder="Search workspaces..."
  value={searchQuery}
  onChange={(e) => setSearchQuery(e.target.value)}
  className="w-full pl-10 pr-4 py-3 rounded-xl bg-[var(--bg-muted)]/50 border border-[var(--border-default)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--border-focus)] focus:ring-2 focus:ring-[var(--accent-primary)]/20 outline-none transition-all"
/>
```

**Step 3: Update button gradient**

Replace lines 129-137:

```tsx
<motion.button
  onClick={() => setShowCreateModal(true)}
  className="flex items-center gap-2 px-6 py-3 rounded-xl text-white bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] font-medium hover:shadow-lg transition-shadow"
  whileHover={{ scale: 1.02 }}
  whileTap={{ scale: 0.98 }}
>
  <Plus className="w-5 h-5" />
  New Workspace
</motion.button>
```

**Step 4: Update modal input styles**

Replace all input/textarea/select styles in the modal (lines 224-291) to use new theme variables.

**Step 5: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 6: Commit**

```bash
git add frontend/app/workspaces/page.tsx
git commit -m "style: update Workspaces page for Academic Deep Sky theme"
```

---

## Task 11: Update Workbench Layout and Page

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/layout.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: Update layout background**

Replace line 12 in layout.tsx:

```tsx
<div className="h-screen flex flex-col bg-[var(--bg-base)]">
```

**Step 2: Update page backgrounds**

Replace all `bg-gradient-to-b from-slate-50 to-indigo-50/30 dark:from-slate-950 dark:to-indigo-950/30` with `bg-[var(--bg-base)]` in page.tsx.

**Step 3: Update header styles**

Replace line 88 in page.tsx:

```tsx
<header className="h-16 flex items-center justify-between px-4 bg-[var(--glass-bg)] backdrop-blur-xl border-b border-[var(--glass-border)]">
```

**Step 4: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/layout.tsx frontend/app/\(workbench\)/workspaces/\[id\]/page.tsx
git commit -m "style: update Workbench layout for Academic Deep Sky theme"
```

---

## Task 12: Update ChatPanel Component

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`

**Step 1: Update header and input area backgrounds**

Replace lines 114 and 166:

```tsx
// Line 114
<div className="px-6 py-4 border-b border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl">

// Line 166
<div className="p-4 border-t border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-xl">
```

**Step 2: Update textarea styles**

Replace lines 186-193:

```tsx
className={cn(
  "w-full px-4 py-3 rounded-xl resize-none",
  "bg-[var(--bg-muted)]/70 backdrop-blur-sm",
  "border border-[var(--border-default)] focus:border-[var(--border-focus)]",
  "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
  "focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20",
  "transition-all duration-200"
)}
```

**Step 3: Update button styles**

Replace lines 201-206:

```tsx
className={cn(
  "px-4 py-3 rounded-xl flex items-center justify-center",
  "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white",
  "hover:shadow-lg transition-shadow",
  "disabled:opacity-50 disabled:cursor-not-allowed"
)}
```

**Step 4: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 5: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/ChatPanel.tsx
git commit -m "style: update ChatPanel for Academic Deep Sky theme"
```

---

## Task 13: Update KnowledgePanel and LiteraturePanel

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiteraturePanel.tsx`

**Step 1: Read both panel components**

**Step 2: Update backgrounds and borders to use new theme variables**

**Step 3: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
git add frontend/app/\(workbench\)/workspaces/\[id\]/components/KnowledgePanel.tsx frontend/app/\(workbench\)/workspaces/\[id\]/components/LiteraturePanel.tsx
git commit -m "style: update side panels for Academic Deep Sky theme"
```

---

## Task 14: Update Auth Pages

**Files:**
- Modify: `frontend/app/(auth)/login/page.tsx`
- Modify: `frontend/app/(auth)/register/page.tsx`

**Step 1: Read both auth pages**

**Step 2: Update backgrounds and form styles to use new theme variables**

**Step 3: Verify changes**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 4: Commit**

```bash
git add frontend/app/\(auth\)/login/page.tsx frontend/app/\(auth\)/register/page.tsx
git commit -m "style: update auth pages for Academic Deep Sky theme"
```

---

## Task 15: Final Verification and Polish

**Files:**
- None (verification only)

**Step 1: Full build verification**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run build`
Expected: Build succeeds without errors

**Step 2: Start dev server for visual verification**

Run: `cd /home/cjz/academiagpt-v2/frontend && npm run dev`
Expected: Dev server starts successfully

**Step 3: Manual visual check**

Visit these pages and verify:
- `/` - Homepage (dark background, proper contrast)
- `/workspaces` - Workspace list (cards visible, text readable)
- `/workspaces/[id]` - Workbench (panels visible, chat working)
- `/login` - Login page (form readable)

**Step 4: Create summary commit if any additional fixes were made**

```bash
git add -A
git commit -m "style: final polish for Academic Deep Sky theme"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Global CSS Variables | globals.css |
| 2 | Tailwind Config | tailwind.config.ts |
| 3 | LiquidGlassCard | components/glass/ |
| 4 | GradientText | components/glass/ |
| 5 | Button | components/ui/ |
| 6 | Input | components/ui/ |
| 7 | Card | components/ui/ |
| 8 | Badge | components/ui/ |
| 9 | Homepage | app/page.tsx |
| 10 | Workspaces Page | app/workspaces/ |
| 11 | Workbench Layout | app/(workbench)/ |
| 12 | ChatPanel | app/(workbench)/components/ |
| 13 | Side Panels | KnowledgePanel, LiteraturePanel |
| 14 | Auth Pages | login, register |
| 15 | Final Verification | - |

**Total estimated tasks: 15**
**Each task: 2-5 minutes**
