"use client";

import { useExecutionStreamV2 } from "@/hooks/useExecutionStreamV2";
import { GraphCanvas } from "./GraphCanvas";
import { NodeDetailDrawer } from "./NodeDetailDrawer";

interface LiveWorkflowPanelProps {
  workspaceId: string;
  className?: string;
  "data-testid"?: string;
}

export function LiveWorkflowPanel({
  workspaceId,
  className,
  "data-testid": testId,
}: LiveWorkflowPanelProps) {
  const { nodes, edges, selectedNodeId, selectNode, executionId } =
    useExecutionStreamV2(workspaceId);

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
        {nodes.length > 0 ? (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            onNodeClick={selectNode}
          />
        ) : (
          <div
            className="flex items-center justify-center h-full text-sm"
            style={{ color: "var(--v2-text-tertiary)" }}
          >
            No active execution
          </div>
        )}
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
