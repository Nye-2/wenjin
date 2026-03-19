"use client";

import { ReactNode, useEffect } from "react";
import { useParams } from "next/navigation";
import { useFeaturesStore } from "@/stores/features";
import { useChatStore } from "@/stores/chat";
import { useWorkspaceStore } from "@/stores/workspace";

interface WorkbenchLayoutProps {
  children: ReactNode;
  params: Promise<{ id: string }>;
}

export default function WorkbenchLayout({ children }: WorkbenchLayoutProps) {
  const params = useParams();
  const workspaceId = params.id as string;
  const { loadWorkspace, fetchArtifacts, clearWorkspace } = useWorkspaceStore();
  const { fetchFeatures, clearFeatures } = useFeaturesStore();
  const { loadLatestThread, clearMessages } = useChatStore();

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchArtifacts(workspaceId);
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
    loadLatestThread,
    clearWorkspace,
    clearFeatures,
    clearMessages,
  ]);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {children}
    </div>
  );
}
