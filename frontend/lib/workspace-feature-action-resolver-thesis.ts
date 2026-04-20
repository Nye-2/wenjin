import { readString } from "@/lib/artifact-utils";
import {
  getArtifactTopic,
  summarizeArtifactContext,
} from "@/lib/workspace-feature-action-artifacts";
import {
  buildFeatureActionState,
  readNumberLike,
} from "@/lib/workspace-feature-action-state-support";
import type { FeatureActionResolver } from "@/lib/workspace-feature-action-types";

export const thesisFeatureActionResolvers: Record<string, FeatureActionResolver> = {
  opening_research: (context) => {
    const topic =
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    const reportType =
      readString(context.orchestrationParams?.report_type) ?? "opening_report";
    return buildFeatureActionState(context, {
      routeParams: { topic, report_type: reportType },
      rerunParams: topic ? { topic, report_type: reportType } : null,
      rerunUnavailableReason: topic ? null : "缺少可复用的研究主题。",
    });
  },
  thesis_writing: (context) => {
    const action =
      readString(context.orchestrationParams?.action) ?? "generate_outline";
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      readString(context.workspace?.name) ??
      "未命名论文";
    const targetWords = readNumberLike(context.orchestrationParams?.target_words);
    const chapterTitle = readString(context.orchestrationParams?.chapter_title);
    const chapterIndex = readNumberLike(context.orchestrationParams?.chapter_index);
    const deepResearchArtifactIds = Array.isArray(
      context.orchestrationParams?.deep_research_artifact_ids
    )
      ? context.orchestrationParams.deep_research_artifact_ids
          .map((item) => readString(item))
          .filter((item): item is string => Boolean(item))
      : [];
    const rerunParams: Record<string, unknown> = {
      action,
      paper_title: paperTitle,
    };
    if (targetWords !== null) {
      rerunParams.target_words = targetWords;
    }
    if (chapterTitle) {
      rerunParams.chapter_title = chapterTitle;
    }
    if (chapterIndex !== null) {
      rerunParams.chapter_index = chapterIndex;
    }
    if (deepResearchArtifactIds.length > 0) {
      rerunParams.deep_research_artifact_ids = deepResearchArtifactIds;
    }
    return buildFeatureActionState(context, {
      routeParams: {
        action,
        paper_title: paperTitle,
        target_words: targetWords ?? undefined,
        chapter_title: chapterTitle,
        chapter_index: chapterIndex ?? undefined,
      },
      rerunParams,
      rerunUnavailableReason: null,
    });
  },
  figure_generation: (context) => {
    const description =
      readString(context.orchestrationParams?.description) ??
      summarizeArtifactContext(context.sourceArtifact) ??
      null;
    const figureType =
      readString(context.orchestrationParams?.type) ??
      readString(context.orchestrationParams?.fig_type) ??
      "flowchart";
    const chapterIndex = readNumberLike(context.orchestrationParams?.chapter_index);
    return buildFeatureActionState(context, {
      routeParams: {
        description,
        type: figureType,
        chapter_index: chapterIndex ?? undefined,
      },
      rerunParams: description
        ? {
            description,
            type: figureType,
            chapter_index: chapterIndex ?? undefined,
          }
        : null,
      rerunUnavailableReason: description
        ? null
        : "缺少可复用的图表描述。",
    });
  },
};
