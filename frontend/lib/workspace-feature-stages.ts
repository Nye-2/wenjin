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
  thesis_research_pack: "research",
  sci_literature_positioning: "research",
  proposal_background_pack: "research",
  prior_art_and_novelty_pack: "research",

  // Stage: collection
  thesis_empirical_analysis: "collection",
  sci_empirical_package: "collection",
  software_evidence_pack: "collection",
  reproducibility_audit: "collection",

  // Stage: structure
  idea_to_thesis_manuscript: "structure",
  research_question_to_paper: "structure",
  idea_to_proposal_package: "structure",
  technical_route_package: "structure",
  software_copyright_application_pack: "structure",
  invention_to_patent_draft: "structure",
  claims_strategy: "structure",

  // Stage: writing
  thesis_revision_pass: "writing",
  response_to_reviewers: "writing",
  proposal_polish_for_review: "writing",
  software_technical_manual: "writing",
  software_architecture_diagrams: "writing",
  embodiment_and_drawings: "writing",
  office_action_response: "writing",

  // Stage: review
  thesis_defense_pack: "review",
  thesis_reference_curation: "review",
  sci_revision_for_journal: "review",
  journal_submission_strategy: "review",
  feasibility_and_risk_review: "review",
};

export function getFeatureStageId(featureId: string): string {
  return featureStageMap[featureId] ?? "research";
}

export function getStageById(stageId: string): WorkspaceStage | undefined {
  return workspaceStages.find((s) => s.id === stageId);
}
