import type { ExecutionRecord } from "@/lib/api/types";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";

import type { EvidenceItem, EvidenceRiskLevel } from "./types";
import { buildSandboxSummary, formatJsonPreview, readString, truncate } from "./utils";

const HIGH_RISK_QUALITY_GATE_IDS = new Set([
  "evidence_contract_integrity",
  "claim_evidence_map_required",
  "claim_source_binding_checked",
  "no_fabricated_citations",
  "citation_and_evidence_required",
  "output_schema_min_shape",
]);

const EVIDENCE_GATE_KEYWORDS = [
  "evidence",
  "citation",
  "claim",
  "fabrication",
  "schema",
  "contract",
];

export function buildEvidenceItems(
  record: ExecutionRecord | null,
  previews: WorkspaceResultPreview[],
): EvidenceItem[] {
  if (!record) {
    return [];
  }
  const outputItems: EvidenceItem[] = previews.map((preview) => ({
    id: preview.id,
    source: "output",
    title: preview.title,
    kind: preview.kind,
    summary: [preview.subtitle, preview.previewText, ...preview.metadataLines]
      .filter(Boolean)
      .join(" · "),
    preview,
  }));
  const graphNodes = record.graph_structure?.nodes ?? [];
  const nodeById = new Map(graphNodes.map((node) => [node.id, node]));
  const nodeItems: EvidenceItem[] = Object.entries(record.node_states ?? {})
    .filter(([, state]) => Boolean(state.output || state.output_preview || state.tool_calls?.length))
    .map(([nodeId, state]) => {
      const node = nodeById.get(nodeId);
      const output = state.output ?? {};
      const title = node?.label ?? node?.task ?? nodeId;
      const sandbox = buildSandboxSummary(state);
      return {
        id: `node:${nodeId}`,
        source: "node",
        title,
        kind: sandbox ? "sandbox" : node?.type ?? "node",
        summary:
          sandbox?.join(" · ") ??
          state.output_preview ??
          readString(output.summary) ??
          truncate(formatJsonPreview(output), 180),
        nodeId,
        nodeState: state,
      };
    });
  const structuredItems: EvidenceItem[] = Object.entries(record.node_states ?? {})
    .flatMap(([nodeId, state]) => {
      const node = nodeById.get(nodeId);
      const title = node?.label ?? node?.task ?? state.label ?? nodeId;
      return buildStructuredEvidenceItems(nodeId, title, state.output);
    });
  return [...outputItems, ...nodeItems, ...structuredItems];
}

export function buildHighRiskOutputIds(
  record: ExecutionRecord | null,
  previews: WorkspaceResultPreview[],
): string[] {
  if (!record || previews.length === 0 || !hasHighRiskEvidenceContract(record)) {
    return [];
  }
  return previews.filter((preview) => preview.canCommit !== false).map((preview) => preview.id);
}

function buildStructuredEvidenceItems(
  nodeId: string,
  nodeTitle: string,
  output: Record<string, unknown> | null | undefined,
): EvidenceItem[] {
  if (!output) {
    return [];
  }
  return [
    ...buildClaimMapEvidenceItems(nodeId, nodeTitle, output),
    ...buildUnsupportedClaimItems(nodeId, nodeTitle, output),
    ...buildCitationAuditEvidenceItems(nodeId, nodeTitle, output),
    ...buildCitationRiskEvidenceItems(nodeId, nodeTitle, output),
  ];
}

function buildClaimMapEvidenceItems(
  nodeId: string,
  nodeTitle: string,
  output: Record<string, unknown>,
): EvidenceItem[] {
  return readArray(output.claim_evidence_map).flatMap((rawItem, index) => {
    const item = objectValue(rawItem);
    if (!item) {
      return [];
    }
    const claimId = readString(item.claim_id) ?? String(index + 1);
    const claimText = readString(item.claim_text) ?? readString(item.claim) ?? `Claim ${claimId}`;
    const status = readString(item.status);
    const citationKeys = readStringArray(item.citation_keys);
    const evidenceRefs = readEvidenceRefs(item.evidence_refs);
    const requiredFix = readString(item.required_fix);
    const riskLevel = riskLevelFromStatus(status);
    return [
      {
        id: `claim:${nodeId}:${claimId}`,
        source: "claim",
        title: claimText,
        kind: "claim",
        summary: summarizeEvidenceLine([
          `节点：${nodeTitle}`,
          status ? `状态：${status}` : null,
          citationKeys.length > 0 ? `引用：${citationKeys.join(", ")}` : null,
          requiredFix,
        ]),
        nodeId,
        claimStatus: status,
        citationKeys,
        evidenceRefs,
        riskLevel,
        riskReason: riskLevel === "none" ? null : requiredFix,
      },
    ];
  });
}

function buildUnsupportedClaimItems(
  nodeId: string,
  nodeTitle: string,
  output: Record<string, unknown>,
): EvidenceItem[] {
  return readArray(output.unsupported_claims).flatMap((rawItem, index) => {
    const item = objectValue(rawItem);
    if (!item) {
      return [];
    }
    const claimId = readString(item.claim_id) ?? `unsupported-${index + 1}`;
    const claimText =
      readString(item.claim_text) ?? readString(item.claim) ?? `未支持论断 ${index + 1}`;
    const requiredFix = readString(item.required_fix) ?? readString(item.fix);
    return [
      {
        id: `claim:${nodeId}:${claimId}:unsupported`,
        source: "claim",
        title: claimText,
        kind: "claim",
        summary: summarizeEvidenceLine([
          `节点：${nodeTitle}`,
          "状态：unsupported",
          requiredFix,
        ]),
        nodeId,
        claimStatus: "unsupported",
        citationKeys: readStringArray(item.citation_keys),
        evidenceRefs: readEvidenceRefs(item.evidence_refs),
        riskLevel: "high",
        riskReason: requiredFix ?? "论断缺少可靠证据绑定。",
      },
    ];
  });
}

function buildCitationAuditEvidenceItems(
  nodeId: string,
  nodeTitle: string,
  output: Record<string, unknown>,
): EvidenceItem[] {
  return readArray(output.citation_key_audit).flatMap((rawItem, index) => {
    const item = objectValue(rawItem);
    if (!item) {
      return [];
    }
    const citationKey = readString(item.citation_key) ?? `citation-${index + 1}`;
    const claimText = readString(item.claim_text) ?? readString(item.claim_id);
    const status = readString(item.status);
    const riskLevel = riskLevelFromStatus(status);
    const citationKeys = [citationKey, ...readStringArray(item.citation_keys)]
      .filter((value, keyIndex, all) => value && all.indexOf(value) === keyIndex);
    return [
      {
        id: `citation:${nodeId}:${citationKey}:${index}`,
        source: "citation",
        title: claimText ? `${citationKey} · ${claimText}` : citationKey,
        kind: "citation",
        summary: summarizeEvidenceLine([
          `节点：${nodeTitle}`,
          status ? `状态：${status}` : null,
          readString(item.required_fix),
        ]),
        nodeId,
        claimStatus: status,
        citationKeys,
        evidenceRefs: readEvidenceRefs(item.evidence_refs),
        riskLevel,
        riskReason: riskLevel === "none" ? null : readString(item.required_fix),
      },
    ];
  });
}

function buildCitationRiskEvidenceItems(
  nodeId: string,
  nodeTitle: string,
  output: Record<string, unknown>,
): EvidenceItem[] {
  const fabricationRisks: EvidenceItem[] = readArray(output.fabrication_risks).flatMap(
    (rawItem, index) => {
      const item = objectValue(rawItem);
      if (!item) {
        return [];
      }
      const citationKey = readString(item.citation_key) ?? `fabrication-risk-${index + 1}`;
      const reason = readString(item.risk) ?? readString(item.reason) ?? readString(item.required_fix);
      return [
        {
          id: `citation:${nodeId}:${citationKey}:fabrication`,
          source: "citation",
          title: citationKey,
          kind: "citation",
          summary: summarizeEvidenceLine([
            `节点：${nodeTitle}`,
            "状态：疑似编造引用",
            reason,
          ]),
          nodeId,
          claimStatus: "fabrication_risk",
          citationKeys: [citationKey],
          evidenceRefs: readEvidenceRefs(item.evidence_refs),
          riskLevel: "high" as const,
          riskReason: reason ?? "引用无法绑定到已验证来源。",
        },
      ];
    },
  );
  const missingSources: EvidenceItem[] = readArray(output.missing_sources).flatMap(
    (rawItem, index) => {
      const item = objectValue(rawItem);
      if (!item) {
        return [];
      }
      const citationKey =
        readString(item.citation_key) ?? readString(item.claim_id) ?? `missing-source-${index + 1}`;
      const reason = readString(item.reason) ?? readString(item.required_fix);
      return [
        {
          id: `citation:${nodeId}:${citationKey}:missing`,
          source: "citation",
          title: citationKey,
          kind: "citation",
          summary: summarizeEvidenceLine([
            `节点：${nodeTitle}`,
            "状态：来源缺失",
            reason,
          ]),
          nodeId,
          claimStatus: "missing_source",
          citationKeys: [citationKey],
          evidenceRefs: readEvidenceRefs(item.evidence_refs),
          riskLevel: "high" as const,
          riskReason: reason ?? "引用来源缺失。",
        },
      ];
    },
  );
  return [...fabricationRisks, ...missingSources];
}

function hasHighRiskEvidenceContract(record: ExecutionRecord): boolean {
  if (readQualityGateRecords(record).some(isHighRiskQualityGate)) {
    return true;
  }
  return Object.values(record.node_states ?? {}).some((state) =>
    hasHighRiskStructuredOutput(state.output),
  );
}

function readQualityGateRecords(record: ExecutionRecord): Array<Record<string, unknown>> {
  const runtimeState = record.runtime_state;
  const direct = readArray(runtimeState?.quality_gates);
  const nested = readArray(objectValue(runtimeState?.team)?.quality_gates);
  return [...direct, ...nested]
    .map(objectValue)
    .filter((gate): gate is Record<string, unknown> => Boolean(gate));
}

function isHighRiskQualityGate(gate: Record<string, unknown>): boolean {
  const id = readString(gate.gate_id) ?? readString(gate.id) ?? "";
  const status = readString(gate.status)?.toLowerCase();
  if (status !== "fail") {
    return false;
  }
  const severity = readString(gate.severity)?.toLowerCase();
  return (
    severity === "high" ||
    HIGH_RISK_QUALITY_GATE_IDS.has(id) ||
    EVIDENCE_GATE_KEYWORDS.some((keyword) => id.toLowerCase().includes(keyword))
  );
}

function hasHighRiskStructuredOutput(output: Record<string, unknown> | null | undefined): boolean {
  if (!output) {
    return false;
  }
  if (objectValue(output.contract_error)) {
    return true;
  }
  if (
    readArray(output.unsupported_claims).length > 0 ||
    readArray(output.fabrication_risks).length > 0 ||
    readArray(output.missing_sources).length > 0
  ) {
    return true;
  }
  return [...readArray(output.claim_evidence_map), ...readArray(output.citation_key_audit)]
    .map(objectValue)
    .some((item) => riskLevelFromStatus(readString(item?.status)) === "high");
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function readArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readStringArray(value: unknown): string[] {
  return readArray(value)
    .map(readString)
    .filter((item): item is string => Boolean(item));
}

function readEvidenceRefs(value: unknown): string[] {
  return readArray(value)
    .map((rawItem) => {
      const stringItem = readString(rawItem);
      if (stringItem) {
        return stringItem;
      }
      const item = objectValue(rawItem);
      if (!item) {
        return null;
      }
      return (
        readString(item.citation_key) ??
        readString(item.ref_id) ??
        readString(item.artifact_id) ??
        readString(item.id) ??
        readString(item.title)
      );
    })
    .filter((item): item is string => Boolean(item));
}

function riskLevelFromStatus(status: string | null | undefined): EvidenceRiskLevel {
  if (!status) {
    return "none";
  }
  const normalized = status.toLowerCase();
  if (
    [
      "unsupported",
      "missing",
      "fabricated",
      "fabrication_risk",
      "fail",
      "failed",
      "invalid",
      "unmatched",
    ].includes(normalized) ||
    normalized.includes("missing") ||
    normalized.includes("fabricat")
  ) {
    return "high";
  }
  if (
    [
      "partial",
      "weak",
      "warning",
      "unverified",
      "needs_revision",
      "needs_review",
    ].includes(normalized)
  ) {
    return "warning";
  }
  return "none";
}

function summarizeEvidenceLine(parts: Array<string | null | undefined>): string {
  return truncate(parts.filter((part): part is string => Boolean(part)).join(" · "), 220);
}
