"use client";

import { Suspense, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { ChatPanel } from "../components/ChatPanel";
import { parseWorkspaceChatEntrySeed } from "@/lib/workspace-chat-entry";
import { WorkspaceInspector } from "../components/WorkspaceInspector";

function ChatPageInner() {
  const { id: workspaceId } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const skillFromUrl = searchParams.get("skill");
  const entrySeed = parseWorkspaceChatEntrySeed(searchParams);
  const isOnboarding = searchParams.get("onboarding") === "true";

  const { workspace } = useWorkspaceStore();
  const { loadThread, startNewThread, setCurrentSkill } = useChatStore();

  const effectiveEntrySeed = entrySeed ?? (isOnboarding && workspace ? {
    featureId: "__onboarding__",
    skillId: null,
    params: { __onboarding_type: workspace.type },
  } : null);

  useEffect(() => {
    // Single thread model: load existing thread or start new
    const threads = useChatStore.getState().threads;
    if (threads.length > 0) {
      void loadThread(threads[0].id);
    } else {
      startNewThread();
    }
    if (skillFromUrl) {
      setCurrentSkill(skillFromUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

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
