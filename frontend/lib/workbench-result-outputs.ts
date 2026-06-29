export type StagedResultKind =
  | "document"
  | "figure"
  | "library_item"
  | "decision"
  | "task"
  | "reference"
  | "dataset"
  | "artifact"
  | "prism_change"
  | "warning";

export type StagedResultOutput = {
  id: string;
  kind: StagedResultKind;
  preview?: string;
  default_checked?: boolean;
  data?: Record<string, unknown>;
};

const USER_VISIBLE_STAGED_OUTPUT_KINDS = new Set<string>([
  "document",
  "figure",
  "library_item",
  "decision",
  "task",
  "reference",
  "dataset",
  "artifact",
  "prism_change",
  "warning",
]);

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
  const reportStatus =
    typeof report?.status === "string" ? report.status : "completed";
  const canDefaultCheck = reportStatus === "completed";
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
      if (!id || !isUserVisibleStagedResultKind(kind)) {
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
          default_checked: canDefaultCheck && item.default_checked !== false,
          data,
        },
      ];
    });
}

export function isUserVisibleStagedResultKind(
  kind: string,
): kind is StagedResultKind {
  return USER_VISIBLE_STAGED_OUTPUT_KINDS.has(kind);
}
