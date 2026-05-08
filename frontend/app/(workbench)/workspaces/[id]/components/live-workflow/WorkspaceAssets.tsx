"use client";

/**
 * WorkspaceAssets · Plan 3 T4
 *
 * The right panel's "below the workflow" drawer that holds the
 * cross-run sediment: produced artifacts, literature library, and
 * workspace context. Mounts the existing ArtifactLibrary /
 * LiteraturePanel / KnowledgePanel components in `embedded` mode.
 *
 * Design intent (spec §4.1): when no run is active the panel is
 * default-open — users see what they have. When a run is in flight
 * it folds into a single header so the live workflow can dominate.
 */
import { useState } from "react";

import { ArtifactDetailDialog } from "@/components/workspace/ArtifactDetailDialog";
import { ArtifactLibrary } from "@/components/workspace/ArtifactLibrary";
import type { Artifact } from "@/stores/workspace";

import { KnowledgePanel } from "../KnowledgePanel";
import { LiteraturePanel } from "../LiteraturePanel";

type Tab = "artifacts" | "literature" | "knowledge";

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
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-3 py-2 text-left text-[12px] font-medium"
          style={{
            color: "var(--compute-text-primary)",
            borderBottom: open
              ? "1px solid var(--compute-border-subtle)"
              : undefined,
          }}
        >
          <span>📚 文献 · 📦 成果 · 🧠 上下文</span>
          <span style={{ color: "var(--compute-text-muted)" }}>
            {open ? "▾" : "▸"}
          </span>
        </button>

        {open && (
          <>
            <div
              role="tablist"
              className="flex gap-3 border-b px-3 pt-2"
              style={{ borderBottomColor: "var(--compute-border-subtle)" }}
            >
              {(
                [
                  ["artifacts", "成果"],
                  ["literature", "文献"],
                  ["knowledge", "上下文"],
                ] as Array<[Tab, string]>
              ).map(([id, label]) => {
                const active = tab === id;
                return (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={active}
                    onClick={() => setTab(id)}
                    className="pb-1.5 text-[11.5px] transition-colors"
                    style={{
                      color: active
                        ? "var(--compute-text-primary)"
                        : "var(--compute-text-muted)",
                      borderBottom: active
                        ? "1px solid var(--compute-accent-cyan)"
                        : "1px solid transparent",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

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
          </>
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
