"use client";

import { ReactNode, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useWorkspaceEventStream } from "@/hooks/useWorkspaceEventStream";
import { useFeaturesStore } from "@/stores/features";
import { useThreadStore } from "@/stores/thread";
import { useExecutionStore } from "@/stores/execution";
import { useComputeStore } from "@/stores/compute";
import { useWorkspaceStore } from "@/stores/workspace";
import { CommandPalette } from "@/components/workspace/CommandPalette";
import { AppShellSidebar } from "@/components/workspace/AppShellSidebar";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams<{ id: string }>();
  const workspaceId = params?.id ?? "";
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useWorkspaceEventStream(workspaceId || null);
  const loadWorkspace = useWorkspaceStore((state) => state.loadWorkspace);
  const fetchArtifacts = useWorkspaceStore((state) => state.fetchArtifacts);
  const fetchActivity = useWorkspaceStore((state) => state.fetchActivity);
  const clearWorkspace = useWorkspaceStore((state) => state.clearWorkspace);
  const setActiveWorkspace = useFeaturesStore((state) => state.setActiveWorkspace);
  const fetchFeatures = useFeaturesStore((state) => state.fetchFeatures);
  const fetchSkills = useFeaturesStore((state) => state.fetchSkills);
  const clearFeatures = useFeaturesStore((state) => state.clearFeatures);
  const clearSkills = useFeaturesStore((state) => state.clearSkills);
  const clearMessages = useThreadStore((state) => state.clearMessages);
  const abortStream = useThreadStore((state) => state.abortStream);
  const hydrateExecutions = useExecutionStore((state) => state.hydrateWorkspace);
  const clearExecutions = useExecutionStore((state) => state.clearWorkspace);
  const hydrateCompute = useComputeStore((state) => state.hydrateWorkspace);
  const clearCompute = useComputeStore((state) => state.clearWorkspace);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    setActiveWorkspace(workspaceId);
    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchSkills(workspaceId);
    void fetchArtifacts(workspaceId);
    void fetchActivity(workspaceId);
    void hydrateExecutions(workspaceId);
    void hydrateCompute(workspaceId);
    return () => {
      abortStream();
      setActiveWorkspace(null);
      clearWorkspace();
      clearFeatures();
      clearSkills();
      clearExecutions(workspaceId);
      clearCompute(workspaceId);
      clearMessages();
    };
  }, [
    workspaceId,
    setActiveWorkspace,
    loadWorkspace,
    fetchFeatures,
    fetchSkills,
    fetchArtifacts,
    fetchActivity,
    hydrateExecutions,
    hydrateCompute,
    clearWorkspace,
    clearFeatures,
    clearSkills,
    clearExecutions,
    clearCompute,
    clearMessages,
    abortStream,
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
