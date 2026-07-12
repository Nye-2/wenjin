"use client";

import { ReactNode, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useWorkspaceStore } from "@/stores/workspace";
import { useMissionUiStore } from "@/stores/mission-ui-store";
import { CommandPalette } from "@/components/workspace/CommandPalette";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const workspaceId = params?.id ?? "";
  const workspaceNotFound = useWorkspaceStore(
    (state) => state.workspaceNotFound,
  );
  // Hold the SSE subscription until we've confirmed the workspace exists —
  // otherwise a stale tab pointing at a non-existent id (e.g. ``/workspaces/v2``)
  // hammers the gateway with reconnect attempts before the redirect fires.
  useWorkspaceEventStream(workspaceNotFound ? null : workspaceId || null);
  const loadWorkspace = useWorkspaceStore((state) => state.loadWorkspace);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const fetchActivity = useWorkspaceStore((state) => state.fetchActivity);
  const clearWorkspace = useWorkspaceStore((state) => state.clearWorkspace);
  const resetChat = useChatStoreV2((state) => state.reset);
  const resetMissionUi = useMissionUiStore((state) => state.clearWorkspaceFocus);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }
    if (workspaceNotFound) {
      // Workspace does not exist (or no longer accessible). Bounce back to
      // the picker instead of polling its endpoints in a loop.
      router.replace("/workspaces");
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    return () => {
      clearWorkspace();
      resetChat();
      resetMissionUi();
    };
  }, [
    workspaceId,
    workspaceNotFound,
    router,
    loadWorkspace,
    fetchArtifacts,
    fetchActivity,
    clearWorkspace,
    resetChat,
    resetMissionUi,
  ]);

  return (
    <div className="flex h-screen bg-[var(--wjn-bg-base)]">
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
      <CommandPalette workspaceId={workspaceId} />
    </div>
  );
}
