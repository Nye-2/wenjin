"use client";

/**
 * WorkspaceAssets — below-workflow drawer holding artifacts, literature,
 * and workspace context tabs.
 */
import { useState } from "react";

import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import { ArtifactLibrary } from "@/components/workspace/ArtifactLibrary";
import type { Artifact } from "@/stores/workspace";

import { KnowledgePanel } from "../KnowledgePanel";
import { LiteraturePanel } from "../LiteraturePanel";

type Tab = "artifacts" | "literature" | "knowledge";

const TABS: Array<{ id: Tab; label: string; icon: string }> = [
  { id: "artifacts", label: "成果", icon: "📦" },
  { id: "literature", label: "文献", icon: "📚" },
  { id: "knowledge", label: "上下文", icon: "🧠" },
];

interface WorkspaceAssetsProps {
  workspaceId: string;
  defaultOpen: boolean;
}

export function WorkspaceAssets({
  workspaceId,
  defaultOpen,
}: WorkspaceAssetsProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [tab, setTab] = useState<Tab>("artifacts");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(
    null,
  );

  return (
    <>
      <div data-testid="workspace-assets">
        <div
          role="tablist"
          className="flex gap-3 border-b px-3 pt-2"
          style={{ borderBottomColor: "var(--compute-border-subtle)" }}
        >
          {TABS.map(({ id, label, icon }) => {
            const active = tab === id;
            return (
              <button
                key={id}
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (active) {
                    setOpen((v) => !v);
                  } else {
                    setTab(id);
                    setOpen(true);
                  }
                }}
                className="pb-1.5 text-[11.5px] transition-colors"
                style={{
                  color: active
                    ? "var(--compute-text-primary)"
                    : "var(--compute-text-muted)",
                  borderBottom: active && open
                    ? "1px solid var(--compute-accent-cyan)"
                    : "1px solid transparent",
                }}
              >
                {icon} {label}
              </button>
            );
          })}
        </div>

        {open && (
          <div
            className="max-h-[40vh] overflow-y-auto px-3 py-3"
            style={{ color: "var(--compute-text-secondary)" }}
          >
            {tab === "artifacts" && (
              <ArtifactLibrary
                onSelectArtifact={setSelectedArtifact}
                embedded
              />
            )}
            {tab === "literature" && (
              <LiteraturePanel workspaceId={workspaceId} embedded />
            )}
            {tab === "knowledge" && (
              <KnowledgePanel workspaceId={workspaceId} embedded />
            )}
          </div>
        )}
      </div>

      <ArtifactDetailDialog
        artifact={selectedArtifact}
        open={selectedArtifact !== null}
        onOpenChange={(o) => {
          if (!o) setSelectedArtifact(null);
        }}
      />
    </>
  );
}
