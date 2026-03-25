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
  workspace: Workspace | null;
  artifacts: Artifact[];
  orchestrationParams?: Record<string, unknown> | null;
}): FeatureActionResolverContext {
  const { featureId, workspace, artifacts, orchestrationParams } = options;

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
    followUpPrompt: getFeatureFollowUpPrompt(featureId),
  };
}

export function getFeatureFollowUpPrompt(featureId: string): string {
  return {
    deep_research:
      "请基于这次深度调研继续收敛研究问题，并给出更具体的创新点与验证路径。",
    literature_management:
      "请基于这次文献盘点继续指出还缺哪些关键文献，并给出下一轮补充与筛选建议。",
    literature_search:
      "请基于这次检索结果筛出最值得精读的文献，并说明各自对后续写作的价值。",
    paper_analysis:
      "请基于这次论文分析继续拆解方法亮点、实验弱点和最值得复用的写法。",
    writing:
      "请基于这次章节草稿继续指出证据缺口、论证薄弱点和下一步最该补写的内容。",
    literature_review:
      "请基于这次文献综述继续细化研究空白，并给出 3 个可写成 SCI 的问题陈述。",
    framework_outline:
      "请基于这次框架结果继续细化摘要、关键词和章节 focus，并指出下一步最适合先写哪一章。",
    opening_research:
      "请基于这次研究报告继续补齐研究意义、可行性和技术路线中的薄弱环节。",
    thesis_writing:
      "请基于这次写作结果继续指出结构缺口、逻辑断点和下一步最该补写的部分。",
    figure_generation:
      "请基于这次图表结果继续优化图意表达，并给出适合写入正文的说明文字。",
    compile_export:
      "请基于这次编译结果继续定位错误或优化排版，并给出下一步修复建议。",
    peer_review:
      "请基于这次同行评审把修改建议按优先级排序，并给出可直接落稿的改写方案。",
    journal_recommend:
      "请基于这次期刊推荐比较前 3 个候选期刊的适配度、风险和投稿策略。",
    proposal_outline:
      "请基于这次申报书大纲继续细化研究目标、技术路线和里程碑安排。",
    background_research:
      "请基于这次背景调研继续收敛关键问题，并输出可直接写进申报书的现状综述。",
    experiment_design:
      "请基于这次实验设计继续细化变量定义、样本方案、实验步骤和评估指标。",
    copyright_materials:
      "请基于这次软著材料清单继续指出还缺哪些证明材料、代码页和截图要求。",
    technical_description:
      "请基于这次技术说明书继续补齐章节细节，并指出最需要补充的技术实现信息。",
    patent_outline:
      "请基于这次专利框架继续收敛权利要求边界，并指出说明书还需要补哪些实施细节。",
    prior_art_search:
      "请基于这次现有技术检索继续评估新颖性风险，并给出可执行的规避改写建议。",
  }[featureId] ?? "请继续基于当前结果往下推进下一步。";
}

export function resolveFeatureActionState(options: {
  featureId: string;
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
