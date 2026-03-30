// frontend/lib/workspace-feature-stages.ts

export interface WorkspaceStage {
  id: string;
  title: string;
  description: string;
}

export const workspaceStages: WorkspaceStage[] = [
  { id: "research", title: "背景调研", description: "明确问题边界与任务目标" },
  { id: "collection", title: "资料收集", description: "把来源、文献与证据放进同一条线" },
  { id: "structure", title: "结构设计", description: "组织论证路径与章节框架" },
  { id: "writing", title: "写作修订", description: "持续推进正文、申报文本与说明材料" },
  { id: "review", title: "评审交付", description: "整理输出、检查清单并完成交付" },
];

export const featureStageMap: Record<string, string> = {
  // Stage: research
  deep_research: "research",
  background_research: "research",
  opening_research: "research",
  prior_art_search: "research",
  literature_search: "research",

  // Stage: collection
  literature_management: "collection",
  literature_review: "collection",
  paper_analysis: "collection",

  // Stage: structure
  framework_outline: "structure",
  proposal_outline: "structure",
  patent_outline: "structure",
  experiment_design: "structure",

  // Stage: writing
  thesis_writing: "writing",
  writing: "writing",
  figure_generation: "writing",
  copyright_materials: "writing",
  technical_description: "writing",

  // Stage: review
  peer_review: "review",
  journal_recommend: "review",
  compile_export: "review",
};

export function getFeatureStageId(featureId: string): string {
  return featureStageMap[featureId] ?? "research";
}

export function getStageById(stageId: string): WorkspaceStage | undefined {
  return workspaceStages.find((s) => s.id === stageId);
}
