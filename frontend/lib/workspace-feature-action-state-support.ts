import type { Artifact, Workspace } from "@/stores/workspace";
import { readString } from "@/lib/artifact-utils";
import type {
  FeatureActionResolverContext,
  FeatureActionState,
  RouteSeedValue,
} from "@/lib/workspace-feature-action-types";

export function workspaceFallback(workspace: Workspace | null | undefined): string {
  return (
    readString(workspace?.description) ??
    readString(workspace?.name) ??
    "未命名任务"
  );
}

export function readNumberLike(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.trim();
    if (!normalized) {
      return null;
    }
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function withSourceArtifact(
  sourceArtifact: Artifact | null,
  params: Record<string, RouteSeedValue>
): Record<string, RouteSeedValue> {
  return sourceArtifact
    ? {
        ...params,
        source_artifact_id: sourceArtifact.id,
      }
    : params;
}

export function resolveExplicitSourceArtifactId(
  orchestrationParams?: Record<string, unknown> | null
): string | null {
  return (
    readString(orchestrationParams?.source_artifact_id) ??
    (Array.isArray(orchestrationParams?.context_artifact_ids)
      ? orchestrationParams.context_artifact_ids
          .map((item) => readString(item))
          .find((item): item is string => Boolean(item))
      : Array.isArray(orchestrationParams?.deep_research_artifact_ids)
        ? orchestrationParams.deep_research_artifact_ids
            .map((item) => readString(item))
            .find((item): item is string => Boolean(item))
        : null) ??
    null
  );
}

export function buildFeatureActionState(
  context: FeatureActionResolverContext,
  state: Omit<FeatureActionState, "sourceArtifact" | "followUpPrompt">
): FeatureActionState {
  return {
    sourceArtifact: context.sourceArtifact,
    followUpPrompt: context.followUpPrompt,
    ...state,
  };
}
