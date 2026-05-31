import type { ExecutionNodeState } from "@/lib/api/types";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

export type EvidenceFilter = "all" | "outputs" | "nodes" | "sandbox";

export type EvidenceItem =
  | {
      id: string;
      source: "output";
      title: string;
      kind: string;
      summary: string;
      preview: WorkspaceResultPreview;
    }
  | {
      id: string;
      source: "node";
      title: string;
      kind: string;
      summary: string;
      nodeId: string;
      nodeState: ExecutionNodeState;
    };
