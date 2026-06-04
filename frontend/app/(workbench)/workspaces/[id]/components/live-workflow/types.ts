import type { ExecutionNodeState } from "@/lib/api/types";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

export type EvidenceFilter = "all" | "outputs" | "nodes" | "claims" | "citations" | "sandbox";
export type EvidenceRiskLevel = "none" | "warning" | "high";

interface EvidenceCommon {
  id: string;
  title: string;
  kind: string;
  summary: string;
  claimStatus?: string | null;
  citationKeys?: string[];
  evidenceRefs?: string[];
  riskLevel?: EvidenceRiskLevel;
  riskReason?: string | null;
}

export type EvidenceItem =
  | (EvidenceCommon & {
      source: "output";
      preview: WorkspaceResultPreview;
    })
  | (EvidenceCommon & {
      source: "node";
      nodeId: string;
      nodeState: ExecutionNodeState;
    })
  | (EvidenceCommon & {
      source: "claim";
      nodeId: string;
    })
  | (EvidenceCommon & {
      source: "citation";
      nodeId: string;
    });
