"use client";

import { useMemo, useState } from "react";
import { Activity, BookOpen, FileText } from "lucide-react";
import { useWorkspaceStore, type Artifact } from "@/stores/workspace";
import { ArtifactLibrary } from "@/components/workspace/ArtifactLibrary";
import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import { KnowledgePanel } from "./KnowledgePanel";
import { LiteraturePanel } from "./LiteraturePanel";
import { cn } from "@/lib/utils";

type InspectorTab = "outputs" | "sources" | "activity";

interface WorkspaceInspectorProps {
  workspaceId: string;
}

const inspectorTabs: Array<{
  id: InspectorTab;
  label: string;
  icon: typeof FileText;
  description: string;
}> = [
  {
    id: "outputs",
    label: "成果",
    icon: FileText,
    description: "查看已经沉淀下来的草稿、结构化结果与交付物。",
  },
  {
    id: "sources",
    label: "文献",
    icon: BookOpen,
    description: "把上传的 PDF、文献信息与抽取状态留在当前主线旁边。",
  },
  {
    id: "activity",
    label: "活动",
    icon: Activity,
    description: "按时间线回看模块执行、对话推进与子代理活动。",
  },
];

export function WorkspaceInspector({ workspaceId }: WorkspaceInspectorProps) {
  const { artifacts, papers, activities } = useWorkspaceStore();
  const [activeTab, setActiveTab] = useState<InspectorTab>("outputs");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);

  const counts = useMemo(
    () => ({
      outputs: artifacts.length,
      sources: papers.length,
      activity: activities.length,
    }),
    [activities.length, artifacts.length, papers.length]
  );
  const activeTabMeta =
    inspectorTabs.find((tab) => tab.id === activeTab) ?? inspectorTabs[0];

  return (
    <>
      <aside className="inspector-panel flex h-full min-h-[420px] flex-col overflow-hidden rounded-[1.75rem]">
        <div className="border-b border-[var(--border-default)] px-4 py-4">
          <p className="section-accent text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
            Inspector
          </p>
          <h2 className="mt-2 text-lg font-semibold text-[var(--text-primary)]">
            证据与成果
          </h2>
          <p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">
            在当前主线旁边查看文献、活动与已沉淀产物。
          </p>
          <div className="mt-4 flex gap-2">
            {inspectorTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                  activeTab === tab.id
                    ? "border-[var(--accent-primary)]/25 bg-[var(--accent-primary)]/12 text-[var(--accent-primary)] shadow-sm"
                    : "border-[var(--border-default)] bg-white/78 text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
                )}
              >
                <tab.icon className="h-3.5 w-3.5" />
                <span>{tab.label}</span>
                <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                  {counts[tab.id]}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs leading-6 text-[var(--text-muted)]">
            {activeTabMeta.description}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
            {activeTab === "outputs" ? (
            <ArtifactLibrary onSelectArtifact={setSelectedArtifact} embedded />
          ) : null}
          {activeTab === "sources" ? (
            <LiteraturePanel workspaceId={workspaceId} embedded />
          ) : null}
          {activeTab === "activity" ? (
            <div className="h-full p-3">
              <KnowledgePanel workspaceId={workspaceId} embedded />
            </div>
          ) : null}
        </div>
      </aside>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedArtifact(null);
          }
        }}
      />
    </>
  );
}
