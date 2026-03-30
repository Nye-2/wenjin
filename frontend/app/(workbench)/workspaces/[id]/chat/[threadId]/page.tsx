"use client";

import { useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { ChatPanel } from "../../components/ChatPanel";
import { parseWorkspaceChatEntrySeed } from "@/lib/workspace-chat-entry";
import { WorkspaceInspector } from "../../components/WorkspaceInspector";

export default function ChatPage() {
  const { id: workspaceId, threadId } = useParams<{
    id: string;
    threadId: string;
  }>();
  const searchParams = useSearchParams();
  const skillFromUrl = searchParams.get("skill");
  const entrySeed = parseWorkspaceChatEntrySeed(searchParams);
  const isOnboarding = searchParams.get("onboarding") === "true";

  const { workspace } = useWorkspaceStore();
  const { loadThread, startNewThread, setCurrentSkill, threadId: currentThreadId } =
    useChatStore();

  // If onboarding and no feature seed, create synthetic onboarding seed
  const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
    featureId: "__onboarding__",
    skillId: null,
    params: { __onboarding_type: workspace.type },
  } : null);

  useEffect(() => {
    if (threadId === "new") {
      startNewThread();
      if (skillFromUrl) {
        setCurrentSkill(skillFromUrl);
      }
    } else if (threadId && threadId !== currentThreadId) {
      void loadThread(threadId);
    }
    // Only re-run when the route params change, not when store state changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, skillFromUrl]);

  return (
    <div className="flex h-full flex-col overflow-hidden p-4 sm:p-6">
      <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-h-0 overflow-hidden rounded-[1.75rem] border border-[var(--border-default)] bg-[rgba(251,248,242,0.88)]">
          <ChatPanel workspaceId={workspaceId} entrySeed={effectiveEntrySeed} />
        </div>
        <div className="min-h-0 overflow-hidden">
          <WorkspaceInspector workspaceId={workspaceId} />
        </div>
      </div>
    </div>
  );
}
