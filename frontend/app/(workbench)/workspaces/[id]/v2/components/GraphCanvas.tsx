"use client";
import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { PhaseNode, type PhaseNodeData } from "./PhaseNode";

const nodeTypes = { phase: PhaseNode };

interface GraphCanvasProps {
  nodes: Array<{
    id: string;
    label: string;
    status: string;
    phaseIndex?: number;
  }>;
  edges: Array<{ source: string; target: string }>;
  onNodeClick?: (nodeId: string) => void;
}

export function GraphCanvas({ nodes, edges, onNodeClick }: GraphCanvasProps) {
  const rfNodes: Node[] = useMemo(() => {
    // Group by phase, compute positions
    const phases = new Map<number, typeof nodes>();
    nodes.forEach((n) => {
      const pi = n.phaseIndex ?? 0;
      if (!phases.has(pi)) phases.set(pi, []);
      phases.get(pi)!.push(n);
    });

    const result: Node[] = [];
    phases.forEach((phaseNodes, phaseIndex) => {
      const y = phaseIndex * 140 + 60;
      const count = phaseNodes.length;
      phaseNodes.forEach((n, i) => {
        const x = count === 1 ? 300 : (i + 1) * (600 / (count + 1));
        result.push({
          id: n.id,
          type: "phase",
          position: { x, y },
          data: { label: n.label, status: n.status } as PhaseNodeData,
        });
      });
    });
    return result;
  }, [nodes]);

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((e, i) => ({
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        animated: false,
        style: { stroke: "rgba(20, 20, 30, 0.15)", strokeWidth: 1.5 },
      })),
    [edges],
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.id);
    },
    [onNodeClick],
  );

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      onNodeClick={handleNodeClick}
      fitView
      proOptions={{ hideAttribution: true }}
      style={{ background: "transparent" }}
    >
      <Background color="rgba(20, 20, 30, 0.04)" gap={24} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
