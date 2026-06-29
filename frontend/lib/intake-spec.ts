import type { Message } from "@/stores/chat-store";

export type IntakeWorkspaceType = "software_copyright" | "math_modeling";
export type IntakeCapabilityId =
  | "software_copyright_application_pack"
  | "math_modeling_paper_pack";
export type IntakeSpecStatus = "draft" | "ready";

export type IntakeSpecV1 = {
  schema_version: "wenjin.intake_spec.v1";
  spec_id: string;
  revision: number;
  workspace_id: string;
  workspace_type: IntakeWorkspaceType;
  capability_id: IntakeCapabilityId;
  title: string;
  status: IntakeSpecStatus;
  markdown: string;
  params: Record<string, unknown>;
  missing_fields: string[];
  assumptions: string[];
};

type RecordValue = Record<string, unknown>;

const SUPER_WORKFLOW_CAPABILITIES = new Set<string>([
  "software_copyright_application_pack",
  "math_modeling_paper_pack",
]);

function isRecord(value: unknown): value is RecordValue {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

export function isSuperWorkflowCapability(capabilityId: string): boolean {
  return SUPER_WORKFLOW_CAPABILITIES.has(capabilityId);
}

export function isIntakeSpecRecord(value: unknown): value is IntakeSpecV1 {
  if (!isRecord(value)) {
    return false;
  }
  const workspaceType = readString(value.workspace_type);
  const capabilityId = readString(value.capability_id);
  const status = readString(value.status);
  return (
    value.schema_version === "wenjin.intake_spec.v1" &&
    Boolean(readString(value.spec_id)) &&
    typeof value.revision === "number" &&
    Boolean(readString(value.workspace_id)) &&
    (workspaceType === "software_copyright" || workspaceType === "math_modeling") &&
    (capabilityId === "software_copyright_application_pack" ||
      capabilityId === "math_modeling_paper_pack") &&
    (status === "draft" || status === "ready") &&
    Boolean(readString(value.title)) &&
    Boolean(readString(value.markdown)) &&
    isRecord(value.params)
  );
}

function normalizeIntakeSpec(value: unknown): IntakeSpecV1 | null {
  if (!isIntakeSpecRecord(value)) {
    return null;
  }
  return {
    schema_version: "wenjin.intake_spec.v1",
    spec_id: value.spec_id,
    revision: value.revision,
    workspace_id: value.workspace_id,
    workspace_type: value.workspace_type,
    capability_id: value.capability_id,
    title: value.title,
    status: value.status,
    markdown: value.markdown,
    params: { ...value.params },
    missing_fields: readStringArray(value.missing_fields),
    assumptions: readStringArray(value.assumptions),
  };
}

export function readIntakeSpecFromToolResultData(data: unknown): IntakeSpecV1 | null {
  if (!isRecord(data)) {
    return null;
  }
  const direct = normalizeIntakeSpec(data.intake_spec);
  if (direct) {
    return direct;
  }
  const output = isRecord(data.output) ? data.output : null;
  return output ? normalizeIntakeSpec(output.intake_spec) : null;
}

export function findLatestIntakeSpec(
  messages: Message[],
  workspaceId?: string,
): IntakeSpecV1 | null {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex];
    if (message.role !== "assistant") {
      continue;
    }
    for (let blockIndex = message.blocks.length - 1; blockIndex >= 0; blockIndex -= 1) {
      const block = message.blocks[blockIndex];
      if (block.kind !== "tool_result") {
        continue;
      }
      const spec = readIntakeSpecFromToolResultData(block);
      if (!spec) {
        continue;
      }
      if (workspaceId && spec.workspace_id !== workspaceId) {
        continue;
      }
      return spec;
    }
  }
  return null;
}
