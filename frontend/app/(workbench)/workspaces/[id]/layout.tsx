"use client";

import { ReactNode, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useFeaturePanelStore } from "@/stores/panels";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useTaskStore } from "@/stores/task";
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
  const { fetchFeatures, fetchSkills, clearFeatures, clearSkills } = useFeaturesStore();
  const hydratePanels = useFeaturePanelStore((state) => state.hydrateWorkspace);
  const clearPanels = useFeaturePanelStore((state) => state.clearWorkspace);
  const { clearMessages, abortStream } = useChatStore();
  const clearWorkspaceTasks = useTaskStore((state) => state.clearWorkspaceTasks);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId).then(() =>
      hydratePanels(
        workspaceId,
        (featureId) => useFeaturesStore.getState().getFeatureById(featureId)
      )
    );
    void fetchSkills(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    return () => {
      abortStream();
      clearWorkspace();
      clearFeatures();
      clearSkills();
      clearWorkspaceTasks(workspaceId);
      clearPanels(workspaceId);
      clearMessages();
    };
  }, [
    workspaceId,
    loadWorkspace,
    fetchFeatures,
    fetchSkills,
    fetchArtifacts,
    fetchActivity,
    clearWorkspace,
    clearFeatures,
    clearSkills,
    clearWorkspaceTasks,
    clearPanels,
    clearMessages,
    abortStream,
    hydratePanels,
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
