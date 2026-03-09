# Phase 5: Frontend Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize Next.js frontend for performance, accessibility, and UX using best practices.

**Architecture:**
- React performance patterns (memo, useMemo, useCallback)
- Accessibility improvements (ARIA, keyboard nav, focus management)
- UX enhancements (loading skeletons, error boundaries, empty states)
- Next.js optimizations (dynamic imports, streaming)

**Tech Stack:** Next.js 14, React 18, Framer Motion, Tailwind CSS

---

## Pre-requisites

Verify frontend builds and runs:

```bash
cd /home/cjz/academiagpt-v2/frontend
npm run build 2>&1 | tail -20
```

---

### Task 1: Add React Performance Optimizations

**Files:**
- Modify: `frontend/components/chat/message-list.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- Create: `frontend/hooks/useStableCallback.ts`

**Step 1: Create useStableCallback hook**

```typescript
// hooks/useStableCallback.ts
import { useCallback, useRef } from 'react';

/**
 * Returns a stable callback that always calls the latest function.
 * Useful for avoiding unnecessary re-renders in child components.
 */
export function useStableCallback<T extends (...args: unknown[]) => unknown>(
  callback: T
): T {
  const ref = useRef<T>(callback);
  ref.current = callback;

  return useCallback(((...args: Parameters<T>) => ref.current(...args)) as T, []);
}
```

**Step 2: Optimize MessageList with memo**

Apply React.memo to MessageBubble, use useStableCallback for handlers.

**Step 3: Verify build**

```bash
npm run build
```

**Step 4: Commit**

```bash
git add frontend/hooks/ frontend/components/chat/
git commit -m "perf: add React performance optimizations to chat components"
```

---

### Task 2: Add Accessibility Improvements

**Files:**
- Modify: `frontend/components/chat/message-input.tsx`
- Modify: `frontend/components/chat/message-list.tsx`
- Create: `frontend/components/ui/skip-link.tsx`

**Step 1: Create SkipLink component**

```typescript
// components/ui/skip-link.tsx
"use client";

import { cn } from "@/lib/utils";

interface SkipLinkProps {
  href: string;
  children: React.ReactNode;
  className?: string;
}

export function SkipLink({ href, children, className }: SkipLinkProps) {
  return (
    <a
      href={href}
      className={cn(
        "sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50",
        "focus:px-4 focus:py-2 focus:bg-academic-primary focus:text-white focus:rounded-lg",
        className
      )}
    >
      {children}
    </a>
  );
}
```

**Step 2: Add ARIA labels and roles**

- Add `role="log"` and `aria-live="polite"` to message list
- Add `aria-label` to buttons
- Add keyboard navigation support

**Step 3: Verify with lighthouse**

```bash
npm run build && npm run start &
# Test accessibility
```

**Step 4: Commit**

```bash
git add frontend/components/ui/skip-link.tsx frontend/components/chat/
git commit -m "a11y: add accessibility improvements (ARIA, skip links)"
```

---

### Task 3: Add Loading Skeletons and Error Boundaries

**Files:**
- Create: `frontend/components/ui/skeleton.tsx`
- Create: `frontend/components/ui/error-boundary.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`

**Step 1: Create Skeleton component**

```typescript
// components/ui/skeleton.tsx
import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-slate-200 dark:bg-slate-800",
        className
      )}
    />
  );
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3 p-4">
      <Skeleton className="w-8 h-8 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  );
}
```

**Step 2: Create ErrorBoundary component**

```typescript
// components/ui/error-boundary.tsx
"use client";

import { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-4 text-center">
          <p className="text-red-500">Something went wrong.</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-2 px-4 py-2 bg-academic-primary text-white rounded-lg"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

**Step 3: Apply to workspace page**

Wrap panels with ErrorBoundary, add loading skeletons.

**Step 4: Verify build**

```bash
npm run build
```

**Step 5: Commit**

```bash
git add frontend/components/ui/skeleton.tsx frontend/components/ui/error-boundary.tsx frontend/app/
git commit -m "ux: add loading skeletons and error boundaries"
```

---

### Task 4: Optimize Framer Motion Animations

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/glass/liquid-glass-card.tsx`
- Create: `frontend/lib/animations.ts`

**Step 1: Create animation presets**

```typescript
// lib/animations.ts
export const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
};

export const staggerContainer = {
  animate: {
    transition: {
      staggerChildren: 0.1,
    },
  },
};

export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.95 },
};

// Reduced motion support
export const prefersReducedMotion = {
  initial: {},
  animate: {},
  exit: {},
};
```

**Step 2: Apply to components**

Use presets consistently, add reduced motion support.

**Step 3: Verify build**

```bash
npm run build
```

**Step 4: Commit**

```bash
git add frontend/lib/animations.ts frontend/app/ frontend/components/
git commit -m "perf: optimize Framer Motion animations with presets"
```

---

### Task 5: Add Dynamic Imports for Heavy Components

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Create: `frontend/components/workspace/lazy-panels.tsx`

**Step 1: Create lazy-loaded panels**

```typescript
// components/workspace/lazy-panels.tsx
import dynamic from 'next/dynamic';
import { MessageSkeleton } from '@/components/ui/skeleton';

export const LazyKnowledgePanel = dynamic(
  () => import('./KnowledgePanel').then(mod => ({ default: mod.KnowledgePanel })),
  {
    loading: () => (
      <div className="w-64 p-4 space-y-4">
        <MessageSkeleton />
        <MessageSkeleton />
      </div>
    ),
    ssr: false,
  }
);

export const LazyLiteraturePanel = dynamic(
  () => import('./LiteraturePanel').then(mod => ({ default: mod.LiteraturePanel })),
  {
    loading: () => (
      <div className="w-80 p-4 space-y-4">
        <MessageSkeleton />
        <MessageSkeleton />
      </div>
    ),
    ssr: false,
  }
);
```

**Step 2: Use in workspace page**

Replace direct imports with lazy versions.

**Step 3: Verify build and bundle size**

```bash
npm run build
npm run analyze  # If available
```

**Step 4: Commit**

```bash
git add frontend/components/workspace/lazy-panels.tsx frontend/app/
git commit -m "perf: add dynamic imports for heavy panel components"
```

---

### Task 6: Final Verification

**Step 1: Run full build**

```bash
cd /home/cjz/academiagpt-v2/frontend
npm run build 2>&1 | tail -30
```

**Step 2: Run lint**

```bash
npm run lint
```

**Step 3: Test frontend imports**

```bash
node -e "
const { SkipLink } = require('./components/ui/skip-link.tsx');
const { Skeleton, MessageSkeleton } = require('./components/ui/skeleton.tsx');
console.log('Phase 5 imports successful!');
"
```

**Step 4: Commit phase summary**

```bash
git add -A
git commit -m "docs: Phase 5 Frontend Optimization complete

- React performance optimizations (memo, stable callbacks)
- Accessibility improvements (ARIA, skip links)
- Loading skeletons and error boundaries
- Optimized Framer Motion animations
- Dynamic imports for heavy components"
```

---

## Post-Phase 5 Checklist

- [ ] All components build without errors
- [ ] Lighthouse accessibility score > 90
- [ ] No React warnings in console
- [ ] Animations respect prefers-reduced-motion
- [ ] Error boundaries catch and display errors gracefully

## What's Next: Phase 6

Phase 6 (Full Project Review) will use superpowers:requesting-code-review for comprehensive code review.
