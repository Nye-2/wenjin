import type { RunViewEvidenceItem } from "@/lib/execution-run-view";

export type EvidenceFilter =
  | "all"
  | "outputs"
  | "nodes"
  | "claims"
  | "citations"
  | "sandbox";

export type EvidenceItem = RunViewEvidenceItem;
