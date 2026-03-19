"use client";

import { ReactNode, useEffect } from "react";
import { useParams } from "next/navigation";
import { useFeaturesStore } from "@/stores/features";
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

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    void loadWorkspace(workspaceId);
    void fetchFeatures(workspaceId);
    void fetchArtifacts(workspaceId);

    return () => {
      clearWorkspace();
      clearFeatures();
    };
  }, [
    workspaceId,
    loadWorkspace,
    fetchFeatures,
    fetchArtifacts,
    clearWorkspace,
    clearFeatures,
  ]);

  return (
    <div className="h-screen flex flex-col bg-[var(--bg-base)]">
      {children}
    </div>
  );
}
