"use client";

import { Suspense, useEffect, useRef } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { ChatPanel } from "../components/ChatPanel";
import { parseWorkspaceChatEntrySeed } from "@/lib/workspace-chat-entry";
import { WorkspaceInspector } from "../components/WorkspaceInspector";

function ChatPageInner() {
  const { id: workspaceId } = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchParamString = searchParams.toString();
  const skillFromUrl = searchParams.get("skill");
  const entrySeed = parseWorkspaceChatEntrySeed(searchParams);
  const isOnboarding = searchParams.get("onboarding") === "true";

  const { workspace } = useWorkspaceStore();
  const {
    isWorkspaceThreadLoading,
    activeSkill,
    ensureWorkspaceThread,
    setCurrentSkill,
  } = useChatStore();
  const initializedSelectionRef = useRef<string | null>(null);
  const cleanedQueryKeyRef = useRef<string | null>(null);

  const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
    featureId: "__onboarding__",
    skillId: null,
    params: { __onboarding_type: workspace.type },
  } : null);

  useEffect(() => {
    if (!workspaceId || isWorkspaceThreadLoading) {
      return;
    }
    const selectionKey = `${workspaceId}:__single_thread__`;
    if (initializedSelectionRef.current === selectionKey) {
      return;
    }

    if (skillFromUrl && skillFromUrl !== activeSkill) {
      setCurrentSkill(skillFromUrl);
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
      <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="chat-container min-h-0 overflow-hidden rounded-[1.75rem]">
          <ChatPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />
        </div>
        <div className="min-h-0 overflow-hidden rounded-[1.75rem]">
          <WorkspaceInspector workspaceId={workspaceId} />
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageInner />
    </Suspense>
  );
}
