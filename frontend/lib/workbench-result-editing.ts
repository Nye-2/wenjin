import type { WorkbenchDraftEdit } from "@/stores/workbench-layout-store";

export type OutputOverride = {
  data?: Record<string, unknown>;
  preview?: string;
};

export type EditableResultKind =
  | "document"
  | "library_item"
  | "memory_fact"
  | "decision"
  | "task";

export type StagedResultOutput = {
  id: string;
  kind: EditableResultKind;
  preview?: string;
  default_checked?: boolean;
  data?: Record<string, unknown>;
};

const EDITABLE_FIELDS: Record<EditableResultKind, string[]> = {
  document: ["content", "name", "doc_kind"],
  library_item: ["title", "authors", "year", "doi", "url", "abstract"],
  memory_fact: ["category", "content", "confidence"],
  decision: ["key", "value"],
  task: ["title", "description", "priority"],
};

export function extractTaskReport(
  result?: Record<string, unknown> | null,
): Record<string, unknown> | null {
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    return null;
  }
  const nested = result.task_report;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    return nested as Record<string, unknown>;
  }
  return result;
}

export function extractTaskOutputs(
  result?: Record<string, unknown> | null,
): StagedResultOutput[] {
  const report = extractTaskReport(result);
  const outputs = report?.outputs;
  if (!Array.isArray(outputs)) {
    return [];
  }
  return outputs
    .map((item) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? (item as Record<string, unknown>)
        : null,
    )
    .filter((item): item is Record<string, unknown> => item !== null)
    .flatMap((item) => {
      const id = typeof item.id === "string" ? item.id.trim() : "";
      const kind = typeof item.kind === "string" ? item.kind : "";
      if (!id || !isEditableResultKind(kind)) {
        return [];
      }
      const data =
        item.data && typeof item.data === "object" && !Array.isArray(item.data)
          ? (item.data as Record<string, unknown>)
          : {};
      return [
        {
          id,
          kind,
          preview: typeof item.preview === "string" ? item.preview : undefined,
          default_checked: item.default_checked !== false,
          data,
        },
      ];
    });
}

export function applyDraftEditsToOutputs(
  outputs: StagedResultOutput[],
  draftEdits: Record<string, WorkbenchDraftEdit>,
): StagedResultOutput[] {
  return outputs.map((output) => {
    const edit = draftEdits[output.id];
    if (!edit) {
      return output;
    }
    return {
      ...output,
      preview: edit.preview ?? output.preview,
      data: edit.data
        ? {
            ...(output.data ?? {}),
            ...edit.data,
          }
        : output.data,
    };
  });
}

export function buildOutputOverrides(
  outputIds: string[],
  draftEdits: Record<string, WorkbenchDraftEdit>,
): Record<string, OutputOverride> | undefined {
  const outputIdSet = new Set(outputIds);
  const overrides: Record<string, OutputOverride> = {};
  for (const [outputId, edit] of Object.entries(draftEdits)) {
    if (!outputIdSet.has(outputId)) {
      continue;
    }
    const override: OutputOverride = {};
    if (edit.preview !== undefined) {
      override.preview = edit.preview;
    }
    if (edit.data && Object.keys(edit.data).length > 0) {
      override.data = edit.data;
    }
    if (override.preview !== undefined || override.data !== undefined) {
      overrides[outputId] = override;
    }
  }
  return Object.keys(overrides).length > 0 ? overrides : undefined;
}

export function getEditableFields(kind: string): string[] {
  return isEditableResultKind(kind) ? EDITABLE_FIELDS[kind] : [];
}

export function isEditableResultKind(kind: string): kind is EditableResultKind {
  return (
    kind === "document" ||
    kind === "library_item" ||
    kind === "memory_fact" ||
    kind === "decision" ||
    kind === "task"
  );
}

export function coerceEditableValue(
  kind: EditableResultKind,
  field: string,
  value: string,
): unknown {
  if (kind === "library_item" && field === "authors") {
    return value
      .split(/[,，]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (field === "year" || field === "priority") {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (field === "confidence") {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return value;
}

export function stringifyEditableValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}
