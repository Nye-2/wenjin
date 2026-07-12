import type {
  MissionReviewItemView,
  MissionSummary,
  MissionView,
} from "@/lib/api/mission-types";

export type MissionConsoleSurface =
  | "progress"
  | "review"
  | "evidence"
  | "artifacts"
  | "trace";

export function missionNeedsAttention(view: MissionView): boolean {
  return view.reviewSummary.pending > 0 || view.reviewSummary.needsMoreEvidence > 0;
}

export function defaultMissionSurface(view: MissionView): MissionConsoleSurface {
  if (missionNeedsAttention(view)) return "review";
  if (view.executionStatus === "running" || view.executionStatus === "planning") {
    return "progress";
  }
  if (view.artifactCount > 0) return "artifacts";
  if (view.evidenceCount > 0) return "evidence";
  return "progress";
}

export function missionDemandKey(view: MissionView): string | null {
  const active = ["created", "planning", "running", "waiting"].includes(
    view.executionStatus,
  );
  if (!active && !missionNeedsAttention(view)) return null;
  return [
    view.missionId,
    view.executionStatus,
    view.activeStage?.id ?? "",
    view.reviewSelectionRevision,
  ].join(":");
}

export function selectableReviewItems(
  view: MissionView,
): MissionReviewItemView[] {
  return view.reviewItems.filter(
    (item) => item.status === "pending" && item.batchAcceptable,
  );
}

export function suggestedReviewSelection(view: MissionView): string[] {
  return selectableReviewItems(view)
    .filter((item) => item.suggestedSelected)
    .map((item) => item.id);
}

export function missionStatusTone(
  status: MissionView["executionStatus"] | MissionSummary["executionStatus"],
): "neutral" | "active" | "success" | "warning" {
  if (status === "running" || status === "planning") return "active";
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "warning";
  return "neutral";
}

export function formatMissionDuration(seconds?: number | null): string {
  if (!seconds || seconds < 1) return "刚刚";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return remaining ? `${minutes} 分 ${remaining} 秒` : `${minutes} 分钟`;
}
