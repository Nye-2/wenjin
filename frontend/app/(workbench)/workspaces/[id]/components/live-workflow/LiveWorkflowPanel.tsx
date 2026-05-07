"use client";

import { useEffect, useRef } from "react";

import { useWorkflowStore } from "@/stores/workflow-store";

import { RunList } from "./RunList";
import { WorkspaceAssets } from "./WorkspaceAssets";
import { useWorkflowSubscription } from "./useWorkflowSubscription";

interface LiveWorkflowPanelProps {
  workspaceId: string;
}

export function LiveWorkflowPanel({ workspaceId }: LiveWorkflowPanelProps) {
  useWorkflowSubscription(workspaceId);

  const runs = useWorkflowStore((s) => s.runs);
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const pausedRunIds = useWorkflowStore((s) => s.pausedRunIds);
  const followCurrent = useWorkflowStore((s) => s.followCurrent);
  const setFollow = useWorkflowStore((s) => s.setFollow);
  const pauseRun = useWorkflowStore((s) => s.pauseRun);
  const resumeRun = useWorkflowStore((s) => s.resumeRun);

  const hasActiveRun = runs.some(
    (r) => r.status === "running" || r.status === "paused",
  );
  const isPaused = currentRunId ? pausedRunIds.has(currentRunId) : false;

  const scrollerRef = useRef<HTMLDivElement>(null);
  const lastFollowSnapTime = useRef(0);

  // Auto-follow the running phase as it changes.
  useEffect(() => {
    if (!followCurrent || !scrollerRef.current) return;
    const el = scrollerRef.current.querySelector<HTMLElement>(
      "[data-phase-status='running']",
    );
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    // Mark this scroll as programmatic so onScroll doesn't disable follow.
    lastFollowSnapTime.current = Date.now();
  }, [followCurrent, runs]);

  function onScroll(ev: React.UIEvent<HTMLDivElement>) {
    // Ignore scrolls within ~600ms of a programmatic snap.
    if (Date.now() - lastFollowSnapTime.current < 600) return;

    const el = ev.currentTarget;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;

    // User scrolled "above the fold" → pause follow.
    if (distanceFromBottom > 80 && followCurrent) setFollow(false);
    // User scrolled back to the bottom → resume follow.
    if (distanceFromBottom <= 80 && !followCurrent) setFollow(true);
  }

  return (
    <div
      className="flex h-full flex-col"
      style={{
        background: "var(--compute-bg-base)",
        borderLeft: "1px solid var(--compute-border)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{
          borderBottom: "1px solid var(--compute-border)",
        }}
      >
        <span
          className="text-[13px] font-semibold"
          style={{ color: "var(--compute-text-primary)" }}
        >
          实时工作台
        </span>
        {currentRunId && (
          <button
            onClick={() => {
              if (isPaused) {
                resumeRun(currentRunId);
              } else {
                pauseRun(currentRunId);
              }
            }}
            className="rounded px-2.5 py-1 text-[11px] font-medium transition-opacity hover:opacity-80"
            style={{
              background: "var(--compute-bg-elevated)",
              border: "1px solid var(--compute-border-subtle)",
              color: "var(--compute-text-secondary)",
            }}
          >
            {isPaused ? "继续" : "在下个安全点暂停"}
          </button>
        )}
      </div>

      {/* Body (scrollable) */}
      <div
        ref={scrollerRef}
        onScroll={onScroll}
        className="relative flex-1 overflow-y-auto px-3 py-3"
      >
        {runs.length > 0 && (
          <RunList runs={runs} currentRunId={currentRunId} />
        )}
        <div className={runs.length > 0 ? "mt-3" : ""}>
          <WorkspaceAssets defaultOpen={!hasActiveRun} />
        </div>

        {/* Floating "回到当前进度" button when follow is paused */}
        {!followCurrent && hasActiveRun && (
          <button
            type="button"
            onClick={() => {
              setFollow(true);
              const el = scrollerRef.current?.querySelector<HTMLElement>(
                "[data-phase-status='running']",
              );
              el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }}
            className="sticky bottom-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1.5 text-[11.5px] font-medium shadow-md transition-opacity hover:opacity-90"
            style={{
              background: "var(--compute-accent-cyan)",
              color: "#FFFFFF",
            }}
          >
            ↓ 回到当前进度
          </button>
        )}
      </div>
    </div>
  );
}
