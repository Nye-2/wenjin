"use client";

import { useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useChatStore } from "@/stores/chat";
import { ChatPanel } from "../../components/ChatPanel";

export default function ChatPage() {
  const { id: workspaceId, threadId } = useParams<{
    id: string;
    threadId: string;
  }>();
  const searchParams = useSearchParams();
  const skillFromUrl = searchParams.get("skill");

  const { loadThread, startNewThread, setCurrentSkill, threadId: currentThreadId } =
    useChatStore();

  useEffect(() => {
    if (threadId === "new") {
      if (currentThreadId !== null) {
        startNewThread();
      }
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
    <div className="flex h-full flex-col">
      <ChatPanel workspaceId={workspaceId} />
    </div>
  );
}
