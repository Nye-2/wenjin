import type { Artifact, Workspace } from "@/stores/workspace";
import { resolveFeatureAction } from "@/lib/api/workspace";
import type { FeatureActionState } from "@/lib/workspace-feature-action-types";

export function getFeatureFollowUpPrompt(
  feature: { id: string; followUpPrompt?: string | null }
): string {
  return feature.followUpPrompt ?? "";
}

export async function resolveFeatureActionState(options: {
  featureId: string;
  feature?: { id: string; followUpPrompt?: string | null } | null;
  workspace: Workspace | null;
  artifacts: Artifact[];
  orchestrationParams?: Record<string, unknown> | null;
}): Promise<FeatureActionState> {
  const { featureId, workspace, orchestrationParams } = options;

  if (!workspace) {
    return {
      sourceArtifact: null,
      followUpPrompt: getFeatureFollowUpPrompt(options.feature ?? { id: featureId }),
      routeParams: {},
      rerunParams: null,
      rerunUnavailableReason: "当前卡片没有可复用的 artifact 执行上下文。",
    };
  }

  try {
    const response = await resolveFeatureAction(workspace.id, featureId, {
      orchestration_params: orchestrationParams ?? null,
      source_artifact_id: null,
    });

    // Map backend response back to frontend types
    const sourceArtifact = options.artifacts.find(
      (a) => a.id === response.source_artifact_id
    ) ?? null;

    return {
      sourceArtifact,
      followUpPrompt: response.follow_up_prompt,
      routeParams: response.route_params as FeatureActionState["routeParams"],
      rerunParams: response.rerun_params,
      rerunUnavailableReason: response.rerun_unavailable_reason,
    };
  } catch {
    return {
      sourceArtifact: null,
      followUpPrompt: "",
      routeParams: {},
      rerunParams: null,
      rerunUnavailableReason: "当前卡片没有可复用的 artifact 执行上下文。",
    };
  }
}

export type { FeatureActionState } from "@/lib/workspace-feature-action-types";
