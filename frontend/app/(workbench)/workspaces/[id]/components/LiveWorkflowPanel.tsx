"use client";

import { useMemo } from "react";

import { useExecutionStreamV2 } from "@/hooks/useExecutionStreamV2";
import type { WorkspaceTypeConfig } from "@/lib/workspace-suggestions";
import type { WorkspaceFeature } from "@/lib/api/types";
import { GraphCanvas } from "./GraphCanvas";
import { NodeDetailDrawer } from "./NodeDetailDrawer";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  typeConfig?: WorkspaceTypeConfig;
  features?: WorkspaceFeature[];
  className?: string;
  "data-testid"?: string;
}

export function LiveWorkflowPanel({
  workspaceId,
  typeConfig,
  features = [],
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  const { record, phases, selectedNodeId, selectNode, executionId } =
    useExecutionStreamV2(workspaceId);

  // Bridge new phases API back to old GraphCanvas nodes/edges format
  const nodes = useMemo(() => {
    if (!record?.graph_structure) return [];
    return record.graph_structure.nodes.map((n) => {
      const state = record.node_states[n.id];
      return {
        id: n.id,
        label: n.label ?? n.id,
        status: state?.status ?? "pending",
        phaseIndex: n.phase ? phases.findIndex((p) => p.name === n.phase) : 0,
      };
    });
  }, [record?.graph_structure, record?.node_states, phases]);

  const edges = useMemo(() => {
    if (!record?.graph_structure) return [];
    return record.graph_structure.edges.map((e) => ({
      source: e.from,
      target: e.to,
    }));
  }, [record?.graph_structure]);

  const hasExecution = nodes.length > 0 || executionId !== null;

  return (
    <div
      data-testid={testId}
      className={className}
      style={{
        background: "var(--v2-bg-gradient)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Light orbs */}
      <div
        style={{
          position: "absolute",
          top: "10%",
          left: "15%",
          width: 300,
          height: 300,
          background: "var(--v2-orb-purple)",
          borderRadius: "50%",
          filter: "blur(50px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "15%",
          right: "20%",
          width: 250,
          height: 250,
          background: "var(--v2-orb-blue)",
          borderRadius: "50%",
          filter: "blur(45px)",
        }}
      />

      {/* Graph content */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          height: "100%",
        }}
      >
        <>
          {/* ProductIntro — idle state */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              opacity: hasExecution ? 0 : 1,
              transition: "opacity 200ms var(--v2-ease-standard)",
              pointerEvents: hasExecution ? "none" : "auto",
            }}
          >
            {typeConfig && (
              <ProductIntro typeConfig={typeConfig} features={features} />
            )}
          </div>

          {/* Graph / loading — active state */}
          {hasExecution && (
            <div
              style={{
                opacity: nodes.length > 0 ? 1 : 0,
                transition: "opacity 200ms var(--v2-ease-standard)",
                width: "100%",
                height: "100%",
              }}
            >
              {nodes.length > 0 ? (
                <GraphCanvas
                  nodes={nodes}
                  edges={edges}
                  onNodeClick={selectNode}
                />
              ) : (
                <div
                  className="flex items-center justify-center h-full"
                  style={{ color: "var(--v2-text-tertiary)", fontSize: 13 }}
                >
                  准备中...
                </div>
              )}
            </div>
          )}
        </>
      </div>

      {/* Node detail drawer */}
      {selectedNodeId && executionId && (
        <NodeDetailDrawer
          executionId={executionId}
          nodeId={selectedNodeId}
          onClose={() => selectNode(null)}
        />
      )}
    </div>
  );
}

function iconToEmoji(icon: string | undefined): string {
  const map: Record<string, string> = {
    search: "🔍",
    microscope: "🔬",
    pen: "✍️",
    "book-open": "📚",
    list: "📋",
    image: "📊",
    "shield-check": "👀",
    compass: "🧭",
    layout: "🗂️",
    edit: "✏️",
    code: "💻",
    package: "📦",
    file: "📄",
  };
  if (!icon) return "✨";
  return map[icon] ?? "✨";
}

function ProductIntro({
  typeConfig,
  features,
}: {
  typeConfig: WorkspaceTypeConfig;
  features: WorkspaceFeature[];
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        padding: "32px 24px",
        animation: "v2-glass-in 500ms var(--v2-ease-standard)",
      }}
    >
      {/* Title */}
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color: "var(--v2-text-primary)",
          marginBottom: 6,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        文津{typeConfig.title}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--v2-text-tertiary)",
          marginBottom: 28,
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        {typeConfig.panelSubtitle}
      </div>

      {/* Feature cards — 2-column grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 10,
          width: "100%",
          maxWidth: 420,
        }}
      >
        {features.slice(0, 6).map((f) => (
          <div
            key={f.id}
            style={{
              padding: "14px 16px",
              borderRadius: "var(--v2-radius-lg)",
              background: "var(--v2-glass-bg-elevated)",
              backdropFilter: "blur(10px)",
              WebkitBackdropFilter: "blur(10px)",
              border: "1px solid var(--v2-glass-border)",
              boxShadow: "var(--v2-glass-shadow)",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: "var(--v2-text-primary)",
                marginBottom: 4,
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {iconToEmoji(f.icon)} {f.name}
            </div>
            <div
              style={{
                fontSize: 11.5,
                color: "var(--v2-text-tertiary)",
                lineHeight: 1.4,
                fontFamily: "var(--v2-font-sans)",
              }}
            >
              {f.description}
            </div>
          </div>
        ))}
      </div>

      {/* Rooms hint */}
      <div
        style={{
          marginTop: 24,
          fontSize: 11,
          color: "var(--v2-text-disabled)",
          textAlign: "center",
          fontFamily: "var(--v2-font-sans)",
        }}
      >
        顶部工具栏提供 8 个工作房间：
        <br />
        Library · Documents · Decisions · Memory · Tasks · Runs · Sandbox ·
        Settings
      </div>
    </div>
  );
}
