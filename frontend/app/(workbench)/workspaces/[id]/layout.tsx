"use client";

import { ReactNode, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";
import { CommandPalette } from "@/components/workspace/CommandPalette";
import { AppShellSidebar } from "@/components/workspace/AppShellSidebar";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams();
  const workspaceId = params.id as string;
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useWorkspaceEventStream(workspaceId || null);
  const { loadWorkspace, fetchArtifacts, fetchActivity, clearWorkspace } = useWorkspaceStore();
  const { fetchFeatures, clearFeatures } = useFeaturesStore();
  const { loadLatestThread, clearMessages } = useChatStore();

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    void loadLatestThread(workspaceId);

    return () => {
      clearWorkspace();
      clearFeatures();
      clearMessages();
    };
  }, [
    workspaceId,
    loadWorkspace,
    fetchFeatures,
    fetchArtifacts,
    fetchActivity,
    loadLatestThread,
    clearWorkspace,
    clearFeatures,
    clearMessages,
  ]);

  return (
    <div className="h-screen flex bg-[var(--bg-base)]">
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
