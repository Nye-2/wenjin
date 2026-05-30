import type { Artifact, Workspace } from "@/stores/workspace";

export type RouteSeedValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

export interface FeatureActionState {
  sourceArtifact: Artifact | null;
  routeParams: Record<string, RouteSeedValue>;
  followUpPrompt: string;
  rerunParams: Record<string, unknown> | null;
  rerunUnavailableReason: string | null;
}

export interface FeatureActionResolverContext {
  featureId: string;
  workspace: Workspace | null;
  sourceArtifact: Artifact | null;
  orchestrationParams?: Record<string, unknown> | null;
  followUpPrompt: string;
}

export type FeatureActionResolver = (
  context: FeatureActionResolverContext
) => FeatureActionState;
