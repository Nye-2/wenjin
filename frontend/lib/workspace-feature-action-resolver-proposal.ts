import { readString } from "@/lib/artifact-utils";
import {
  getArtifactObjective,
  getArtifactTopic,
} from "@/lib/workspace-feature-action-artifacts";
import {
  buildFeatureActionState,
  readNumberLike,
  withSourceArtifact,
} from "@/lib/workspace-feature-action-state-support";
import type { FeatureActionResolver } from "@/lib/workspace-feature-action-types";

export const proposalFeatureActionResolvers: Record<string, FeatureActionResolver> = {
  experiment_design: (context) => {
    const topic =
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    const objective =
      readString(context.orchestrationParams?.objective) ??
      getArtifactObjective(context.sourceArtifact) ??
      topic;
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, { topic, objective }),
      rerunParams: topic ? { topic, objective } : null,
      rerunUnavailableReason: topic
        ? null
        : "缺少可复用的研究目标或任务主题。",
    });
  },
  proposal_outline: (context) => {
    const topic =
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    const proposalType =
      readString(context.orchestrationParams?.proposal_type) ?? undefined;
    const periodMonths =
      readNumberLike(context.orchestrationParams?.period_months) ?? undefined;
    return buildFeatureActionState(context, {
      routeParams: {
        topic,
        proposal_type: proposalType,
        period_months: periodMonths,
      },
      rerunParams: topic
        ? {
            topic,
            proposal_type: proposalType,
            period_months: periodMonths,
          }
        : null,
      rerunUnavailableReason: topic ? null : "缺少可复用的课题主题。",
    });
  },
  background_research: (context) => {
    const keywords =
      readString(context.orchestrationParams?.keywords) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    const industryScope =
      readString(context.orchestrationParams?.industry_scope) ?? undefined;
    const timeRange =
      readString(context.orchestrationParams?.time_range) ?? undefined;
    return buildFeatureActionState(context, {
      routeParams: {
        keywords,
        industry_scope: industryScope,
        time_range: timeRange,
      },
      rerunParams: keywords
        ? {
            keywords,
            industry_scope: industryScope,
            time_range: timeRange,
          }
        : null,
      rerunUnavailableReason: keywords ? null : "缺少可复用的调研关键词。",
    });
  },
};
