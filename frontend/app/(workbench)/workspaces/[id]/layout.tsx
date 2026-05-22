"use client";

import { ReactNode, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useFeaturesStore } from "@/stores/features";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useComputeStore } from "@/stores/compute";
import { useWorkspaceStore } from "@/stores/workspace";
import { useRunUiStore } from "@/stores/run-ui-store";
import { CommandPalette } from "@/components/workspace/CommandPalette";
import { AppShellSidebar } from "@/components/workspace/AppShellSidebar";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const workspaceId = params?.id ?? "";
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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
  const setActiveWorkspace = useFeaturesStore((state) => state.setActiveWorkspace);
  const fetchFeatures = useFeaturesStore((state) => state.fetchFeatures);
  const clearFeatures = useFeaturesStore((state) => state.clearFeatures);
  const resetChat = useChatStoreV2((state) => state.reset);
  const resetRunUi = useRunUiStore((state) => state.reset);
  const hydrateCompute = useComputeStore((state) => state.hydrateWorkspace);
  const clearCompute = useComputeStore((state) => state.clearWorkspace);

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

    setActiveWorkspace(workspaceId);
    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    void hydrateCompute(workspaceId);
    return () => {
      setActiveWorkspace(null);
      clearWorkspace();
      clearFeatures();
      clearCompute(workspaceId);
      resetChat();
      resetRunUi();
    };
  }, [
    workspaceId,
    workspaceNotFound,
    router,
    setActiveWorkspace,
    loadWorkspace,
    fetchFeatures,
    fetchArtifacts,
    fetchActivity,
    hydrateCompute,
    clearWorkspace,
    clearFeatures,
    clearCompute,
    resetChat,
    resetRunUi,
  ]);

  return (
    <div className="flex h-screen bg-[var(--bg-base)]">
      <AppShellSidebar
        workspaceId={workspaceId}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
      />
      <div className="flex-1 flex flex-col min-w-0">
        {children}
      </div>
      <CommandPalette workspaceId={workspaceId} />
    </div>
  );
}
