import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
  variant?: "light" | "compute";
}

export function Skeleton({ className, variant = "light" }: SkeletonProps) {
  const bg =
    variant === "compute"
      ? "bg-compute-surface"
      : "bg-slate-200 dark:bg-slate-800";
  return (
    <div
      className={cn("animate-pulse rounded-md", bg, className)}
    />
  );
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3 p-4">
      <Skeleton className="h-8 w-8 flex-shrink-0 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  );
}

export function WorkspaceCardSkeleton() {
  return (
    <div className="glass-card space-y-4 p-6">
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <div className="flex gap-2">
        <Skeleton className="h-6 w-20 rounded-full" />
        <Skeleton className="h-6 w-24 rounded-full" />
      </div>
    </div>
  );
}

/* ── Compute Stage Skeletons ── */

export function ComputeHeaderSkeleton() {
  return (
    <div className="border-b border-compute-border px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton variant="compute" className="h-4 w-4 rounded-full" />
            <Skeleton variant="compute" className="h-5 w-40" />
          </div>
          <Skeleton variant="compute" className="h-3 w-56" />
        </div>
        <Skeleton variant="compute" className="h-7 w-20 rounded-full" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="space-y-2 rounded-xl border border-compute-border bg-compute-elevated px-3 py-2"
          >
            <Skeleton variant="compute" className="h-3 w-10" />
            <Skeleton variant="compute" className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="compute-card space-y-3 p-4">
      <div className="flex items-center gap-2">
        <Skeleton variant="compute" className="h-4 w-4 rounded-full" />
        <Skeleton variant="compute" className="h-4 w-24" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="space-y-2 rounded-xl border border-compute-border bg-compute-surface px-3 py-2"
        >
          <div className="flex items-center justify-between">
            <Skeleton variant="compute" className="h-4 w-2/3" />
            <Skeleton variant="compute" className="h-3 w-12" />
          </div>
          <Skeleton variant="compute" className="h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

export function ComputeStageSkeleton() {
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
      <div className="compute-card space-y-3 p-4">
        <div className="flex items-center gap-2">
          <Skeleton variant="compute" className="h-4 w-4 rounded-full" />
          <Skeleton variant="compute" className="h-4 w-32" />
        </div>
        <Skeleton variant="compute" className="h-20 w-full rounded-xl" />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <PanelSkeleton rows={3} />
        <PanelSkeleton rows={3} />
      </div>
      <div className="grid gap-4 xl:grid-cols-4">
        <PanelSkeleton rows={2} />
        <PanelSkeleton rows={2} />
        <PanelSkeleton rows={2} />
        <PanelSkeleton rows={2} />
      </div>
    </div>
  );
}
