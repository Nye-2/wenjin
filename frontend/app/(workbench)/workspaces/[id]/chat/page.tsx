"use client";

import { Suspense, useEffect, useMemo, useRef } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useThreadStore } from "@/stores/thread";
import { useExecutionStore } from "@/stores/execution";
import { useWorkspaceStore } from "@/stores/workspace";
import { ThreadPanel } from "../components/ThreadPanel";
import { parseWorkspaceThreadEntrySeed } from "@/lib/workspace-thread-entry";
import { WorkspaceInspector } from "../components/WorkspaceInspector";
import { cn } from "@/lib/utils";
import type { ExecutionSession } from "@/lib/api";

const EMPTY_EXECUTION_SESSIONS: ExecutionSession[] = [];
const EMPTY_EXECUTION_IDS: string[] = [];

function ThreadPageInner() {
  const params = useParams<{ id: string }>();
  const workspaceId = params?.id ?? "";
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const searchParams = useSearchParams();
  const searchParamString = searchParams?.toString() ?? "";
  const skillFromUrl = searchParams?.get("skill") ?? null;
  const entrySeed = searchParams ? parseWorkspaceThreadEntrySeed(searchParams) : null;
  const isOnboarding = searchParams?.get("onboarding") === "true";

  const workspace = useWorkspaceStore((state) => state.workspace);
  const executionSessions = useExecutionStore(
    (state) => state.byWorkspace[workspaceId] ?? EMPTY_EXECUTION_SESSIONS
  );
  const activeExecutionId = useExecutionStore(
    (state) => state.activeExecutionIdByWorkspace[workspaceId] ?? null
  );
  const dismissedExecutionIds = useExecutionStore(
    (state) => state.dismissedExecutionIdsByWorkspace[workspaceId] ?? EMPTY_EXECUTION_IDS
  );
  const isWorkspaceThreadLoading = useThreadStore(
    (state) => state.isWorkspaceThreadLoading
  );
  const activeSkill = useThreadStore((state) => state.activeSkill);
  const ensureWorkspaceThread = useThreadStore(
    (state) => state.ensureWorkspaceThread
  );
  const setCurrentSkill = useThreadStore((state) => state.setCurrentSkill);
  const initializedSelectionRef = useRef<string | null>(null);
  const cleanedQueryKeyRef = useRef<string | null>(null);

  const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
    featureId: "__onboarding__",
    skillId: null,
    params: { __onboarding_type: workspace.type },
  } : null);
  const computeStageExpanded = useMemo(() => {
    const visibleExecutions = executionSessions.filter(
      (execution) => !dismissedExecutionIds.includes(execution.id)
    );
    const activeExecution =
      visibleExecutions.find((execution) => execution.id === activeExecutionId) ??
      visibleExecutions.find((execution) =>
        ["launching", "pending", "running", "awaiting_user_input"].includes(
          execution.status
        )
      ) ??
      null;
    return Boolean(activeExecution);
  }, [activeExecutionId, dismissedExecutionIds, executionSessions]);

  useEffect(() => {
    if (!workspaceId || isWorkspaceThreadLoading) {
      return;
    }
    const selectionKey = `${workspaceId}:__single_thread__`;
    if (initializedSelectionRef.current === selectionKey) {
      return;
    }

    if (skillFromUrl && skillFromUrl !== activeSkill) {
      setCurrentSkill(skillFromUrl, workspaceId);
    }

    let cancelled = false;

    const initialize = async () => {
      initializedSelectionRef.current = selectionKey;
      await ensureWorkspaceThread(workspaceId, {
        skill: skillFromUrl,
      });
      if (cancelled) {
        return;
      }
    };

    void initialize();

    return () => {
      cancelled = true;
    };
  }, [
    activeSkill,
    ensureWorkspaceThread,
    isWorkspaceThreadLoading,
    setCurrentSkill,
    skillFromUrl,
    workspaceId,
  ]);

  useEffect(() => {
    if (!workspaceId || isWorkspaceThreadLoading) {
      return;
    }
    const selectionKey = `${workspaceId}:__single_thread__`;
    if (initializedSelectionRef.current !== selectionKey) {
      return;
    }

    if (!searchParamString.includes("thread=")) {
      return;
    }

    const cleanKey = `${workspaceId}:${searchParamString}`;
    if (cleanedQueryKeyRef.current === cleanKey) {
      return;
    }

    const nextParams = new URLSearchParams(searchParamString);
    if (nextParams.has("thread")) {
      nextParams.delete("thread");
    } else {
      return;
    }

    const nextQuery = nextParams.toString();
    const currentUrl = searchParamString ? `${pathname}?${searchParamString}` : pathname;
    const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
    if (nextUrl === currentUrl) {
      return;
    }

    cleanedQueryKeyRef.current = cleanKey;
    router.replace(nextUrl, {
      scroll: false,
    });
  }, [
    isWorkspaceThreadLoading,
    pathname,
    router,
    searchParamString,
    workspaceId,
  ]);

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 sm:p-6 atmosphere-mesh">
      <div
        className={cn(
          "grid h-full min-h-0 grid-cols-1 gap-4",
          computeStageExpanded
            ? "xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]"
            : "xl:grid-cols-[minmax(0,1fr)_minmax(430px,520px)]"
        )}
      >
        <div className="chat-container min-h-0 overflow-hidden rounded-[1.75rem]">
          <ThreadPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />
        </div>
        <div className="min-h-0 overflow-hidden rounded-[1.75rem]">
          <WorkspaceInspector workspaceId={workspaceId} />
        </div>
      </div>
    </div>
  );
}

export default function ThreadPage() {
  return (
    <Suspense>
      <ThreadPageInner />
    </Suspense>
  );
}
