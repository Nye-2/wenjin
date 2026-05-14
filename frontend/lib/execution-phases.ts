import type { ExecutionGraphNode, ExecutionRecord } from "@/lib/api/types";

export interface PhaseGroup {
  name: string;
  index: number;
  nodes: ExecutionGraphNode[];
}

export function groupExecutionPhases(
  record: ExecutionRecord | null | undefined,
): PhaseGroup[] {
  if (!record?.graph_structure?.nodes) return [];

  const phaseMap = new Map<string, { index: number; nodes: ExecutionGraphNode[] }>();
  let idx = 0;
  for (const node of record.graph_structure.nodes) {
    const phaseName = node.phase || "default";
    if (!phaseMap.has(phaseName)) {
      phaseMap.set(phaseName, { index: idx, nodes: [] });
      idx += 1;
    }
    phaseMap.get(phaseName)!.nodes.push(node);
  }

  return Array.from(phaseMap.entries()).map(([name, data]) => ({
    name,
    index: data.index,
    nodes: data.nodes,
  }));
}
