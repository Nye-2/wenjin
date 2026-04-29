import type { Artifact, Workspace } from "@/stores/workspace";
import {
  resolveFeatureActionState,
  type FeatureActionState,
} from "@/lib/workspace-feature-actions";
import { getWorkspaceFeatureRoute } from "@/lib/workspace-feature-routes";

export interface WorkspaceFeatureActionContext {
  featureId: string | null;
  route: string | null;
  routeParams: FeatureActionState["routeParams"] | null;
  followUpPrompt: string | null;
  rerunParams: Record<string, unknown> | null;
  rerunUnavailableReason: string | null;
}

export function readWorkspaceFeatureOrchestrationParams(
  value: unknown
): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

export function resolveWorkspaceFeatureActionContext(options: {
  workspaceId: string;
  featureId: string | null | undefined;
  feature?: { id: string; followUpPrompt?: string | null; defaultSkillId?: string | null } | null;
  workspace: Workspace | null | undefined;
  artifacts: Artifact[];
  orchestrationParams?: Record<string, unknown> | null;
}): WorkspaceFeatureActionContext {
  const { workspaceId, featureId, feature, workspace, artifacts, orchestrationParams } = options;
  if (!featureId) {
    return {
      featureId: null,
      route: null,
      routeParams: null,
      followUpPrompt: null,
      rerunParams: null,
      rerunUnavailableReason: null,
    };
  }

  const actionState = resolveFeatureActionState({
    featureId,
    feature: feature ?? null,
    workspace: workspace ?? null,
    artifacts,
    orchestrationParams: orchestrationParams ?? null,
  });

  return {
    featureId,
    route: getWorkspaceFeatureRoute(
      workspaceId,
      featureId,
      {
        ...(feature?.defaultSkillId ? { skill: feature.defaultSkillId } : {}),
        ...(actionState.routeParams ?? {}),
      }
    ),
    routeParams: actionState.routeParams,
    followUpPrompt: actionState.followUpPrompt,
    rerunParams: actionState.rerunParams,
    rerunUnavailableReason: actionState.rerunUnavailableReason,
  };
}
