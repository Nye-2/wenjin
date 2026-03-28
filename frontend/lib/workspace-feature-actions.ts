import type { Artifact, Workspace } from "@/stores/workspace";
export {
  getArtifactAbstract,
  getArtifactDiscipline,
  getArtifactExcerpt,
  getArtifactObjective,
  getArtifactPaperTitle,
  getArtifactTopic,
  resolveFeatureSourceArtifact,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-action-artifacts";
import { resolveFeatureSourceArtifact } from "@/lib/workspace-feature-action-artifacts";
import { patentFeatureActionResolvers } from "@/lib/workspace-feature-action-resolver-patent";
import { proposalFeatureActionResolvers } from "@/lib/workspace-feature-action-resolver-proposal";
import { sciFeatureActionResolvers } from "@/lib/workspace-feature-action-resolver-sci";
import { softwareFeatureActionResolvers } from "@/lib/workspace-feature-action-resolver-software";
import { thesisFeatureActionResolvers } from "@/lib/workspace-feature-action-resolver-thesis";
import {
  buildFeatureActionState,
  resolveExplicitSourceArtifactId,
  workspaceFallback,
} from "@/lib/workspace-feature-action-state-support";
import type {
  FeatureActionResolverContext,
  FeatureActionState,
} from "@/lib/workspace-feature-action-types";

function createResolverContext(options: {
  featureId: string;
  feature?: { id: string; followUpPrompt?: string | null } | null;
  workspace: Workspace | null;
  artifacts: Artifact[];
  orchestrationParams?: Record<string, unknown> | null;
}): FeatureActionResolverContext {
  const { featureId, feature, workspace, artifacts, orchestrationParams } = options;

  return {
    featureId,
    workspace,
    sourceArtifact: resolveFeatureSourceArtifact(
      featureId,
      artifacts,
      resolveExplicitSourceArtifactId(orchestrationParams)
    ),
    orchestrationParams,
    fallbackTaskName: workspaceFallback(workspace),
    followUpPrompt: getFeatureFollowUpPrompt(feature ?? { id: featureId }),
  };
}

export function getFeatureFollowUpPrompt(
  feature: { id: string; followUpPrompt?: string | null }
): string {
  return feature.followUpPrompt ?? "";
}

export function resolveFeatureActionState(options: {
  featureId: string;
  feature?: { id: string; followUpPrompt?: string | null } | null;
  workspace: Workspace | null;
  artifacts: Artifact[];
  orchestrationParams?: Record<string, unknown> | null;
}): FeatureActionState {
  const context = createResolverContext(options);

  switch (context.featureId) {
    case "deep_research":
    case "literature_management":
    case "literature_search":
    case "paper_analysis":
    case "writing":
    case "literature_review":
    case "framework_outline":
    case "peer_review":
    case "journal_recommend":
      return sciFeatureActionResolvers[context.featureId](context);
    case "opening_research":
    case "thesis_writing":
    case "figure_generation":
    case "compile_export":
      return thesisFeatureActionResolvers[context.featureId](context);
    case "proposal_outline":
    case "background_research":
    case "experiment_design":
      return proposalFeatureActionResolvers[context.featureId](context);
    case "copyright_materials":
    case "technical_description":
      return softwareFeatureActionResolvers[context.featureId](context);
    case "patent_outline":
    case "prior_art_search":
      return patentFeatureActionResolvers[context.featureId](context);
    default:
      return buildFeatureActionState(context, {
        routeParams: {},
        rerunParams: null,
        rerunUnavailableReason: "当前卡片没有可复用的 artifact 执行上下文。",
      });
  }
}

export type { FeatureActionState } from "@/lib/workspace-feature-action-types";
