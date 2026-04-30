import { readString } from "@/lib/artifact-utils";
import {
  getArtifactAbstract,
  getArtifactDiscipline,
  getArtifactExcerpt,
  getArtifactPaperTitle,
  getArtifactTopic,
} from "@/lib/workspace-feature-action-artifacts";
import {
  buildFeatureActionState,
  readNumberLike,
  withSourceArtifact,
} from "@/lib/workspace-feature-action-state-support";
import type { FeatureActionResolver } from "@/lib/workspace-feature-action-types";

export const sciFeatureActionResolvers: Record<string, FeatureActionResolver> = {
  deep_research: (context) => {
    const topic =
      readString(context.orchestrationParams?.topic) ??
      readString(context.orchestrationParams?.query) ??
      context.fallbackTaskName;
    return buildFeatureActionState(context, {
      routeParams: { topic },
      rerunParams: topic ? { topic, query: topic } : null,
      rerunUnavailableReason: topic ? null : "缺少可复用的研究主题。",
    });
  },
  literature_management: (context) => {
    const query =
      readString(context.orchestrationParams?.query) ??
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, { query }),
      rerunParams: query ? { topic: query } : null,
      rerunUnavailableReason: query ? null : "缺少可复用的文献主题。",
    });
  },
  literature_search: (context) => {
    const query =
      readString(context.orchestrationParams?.query) ??
      readString(context.orchestrationParams?.topic) ??
      context.fallbackTaskName;
    const discipline =
      readString(context.orchestrationParams?.discipline) ??
      getArtifactDiscipline(context.sourceArtifact, context.workspace);
    return buildFeatureActionState(context, {
      routeParams: { query, discipline },
      rerunParams: query
        ? {
            query,
            discipline: discipline ?? undefined,
          }
        : null,
      rerunUnavailableReason: query ? null : "缺少可复用的检索主题。",
    });
  },
  paper_analysis: (context) => {
    const referenceId = readString(context.orchestrationParams?.reference_id);
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      getArtifactPaperTitle(context.sourceArtifact) ??
      context.fallbackTaskName;
    const paperAbstract =
      readString(context.orchestrationParams?.paper_abstract) ??
      getArtifactAbstract(context.sourceArtifact);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        reference_id: referenceId,
        paper_title: paperTitle,
        paper_abstract: paperAbstract,
      }),
      rerunParams: referenceId || paperTitle
        ? {
            reference_id: referenceId ?? undefined,
            paper_title: paperTitle,
            paper_abstract: paperAbstract ?? undefined,
          }
        : null,
      rerunUnavailableReason:
        referenceId || paperTitle ? null : "缺少可复用的参考文献标识或标题。",
    });
  },
  writing: (context) => {
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      getArtifactPaperTitle(context.sourceArtifact) ??
      readString(context.workspace?.name) ??
      "Untitled Paper";
    const sectionType =
      readString(context.orchestrationParams?.section_type) ??
      readString(context.orchestrationParams?.section);
    const targetWords = readNumberLike(context.orchestrationParams?.target_words);
    const contextArtifactIds = Array.isArray(
      context.orchestrationParams?.context_artifact_ids
    )
      ? context.orchestrationParams.context_artifact_ids
          .map((item) => readString(item))
          .filter((item): item is string => Boolean(item))
      : context.sourceArtifact
        ? [context.sourceArtifact.id]
        : [];
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        paper_title: paperTitle,
        section_type: sectionType,
        target_words: targetWords ?? undefined,
        context_artifact_ids:
          contextArtifactIds.length > 0 ? contextArtifactIds : undefined,
      }),
      rerunParams: paperTitle
        ? {
            paper_title: paperTitle,
            section_type: sectionType ?? undefined,
            target_words: targetWords ?? undefined,
            context_artifact_ids:
              contextArtifactIds.length > 0 ? contextArtifactIds : undefined,
          }
        : null,
      rerunUnavailableReason: paperTitle ? null : "缺少可复用的论文标题。",
    });
  },
  literature_review: (context) => {
    const topic =
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    const discipline =
      readString(context.orchestrationParams?.discipline) ??
      getArtifactDiscipline(context.sourceArtifact, context.workspace);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        topic,
        discipline,
      }),
      rerunParams: topic
        ? {
            topic,
            discipline: discipline ?? undefined,
            context_artifact_ids: context.sourceArtifact
              ? [context.sourceArtifact.id]
              : undefined,
          }
        : null,
      rerunUnavailableReason: topic ? null : "缺少可复用的综述主题。",
    });
  },
  framework_outline: (context) => {
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      getArtifactPaperTitle(context.sourceArtifact) ??
      readString(context.workspace?.name) ??
      "Untitled Paper";
    const topic =
      readString(context.orchestrationParams?.topic) ??
      getArtifactTopic(context.sourceArtifact) ??
      context.fallbackTaskName;
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        paper_title: paperTitle,
        topic,
      }),
      rerunParams: paperTitle && topic
        ? {
            paper_title: paperTitle,
            topic,
            context_artifact_ids: context.sourceArtifact
              ? [context.sourceArtifact.id]
              : undefined,
          }
        : null,
      rerunUnavailableReason:
        paperTitle && topic ? null : "缺少可复用的论文标题或研究主题。",
    });
  },
  peer_review: (context) => {
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      getArtifactPaperTitle(context.sourceArtifact) ??
      readString(context.workspace?.name) ??
      "Untitled Paper";
    const manuscriptExcerpt =
      getArtifactExcerpt(context.sourceArtifact) ??
      readString(context.orchestrationParams?.manuscript_excerpt);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        paper_title: paperTitle,
      }),
      rerunParams: manuscriptExcerpt
        ? {
            paper_title: paperTitle,
            manuscript_excerpt: manuscriptExcerpt,
          }
        : null,
      rerunUnavailableReason: manuscriptExcerpt
        ? null
        : "缺少可直接审阅的稿件内容。",
    });
  },
  journal_recommend: (context) => {
    const paperTitle =
      readString(context.orchestrationParams?.paper_title) ??
      getArtifactPaperTitle(context.sourceArtifact) ??
      readString(context.workspace?.name) ??
      "Untitled Paper";
    const discipline =
      readString(context.orchestrationParams?.discipline) ??
      getArtifactDiscipline(context.sourceArtifact, context.workspace);
    const abstract =
      getArtifactAbstract(context.sourceArtifact) ??
      readString(context.orchestrationParams?.abstract);
    return buildFeatureActionState(context, {
      routeParams: withSourceArtifact(context.sourceArtifact, {
        paper_title: paperTitle,
        discipline,
      }),
      rerunParams: abstract
        ? {
            paper_title: paperTitle,
            abstract,
            discipline: discipline ?? undefined,
          }
        : null,
      rerunUnavailableReason: abstract
        ? null
        : "缺少可用于投稿画像的摘要或研究简介。",
    });
  },
};
