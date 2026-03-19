export const workspaceFeatureRouteMap: Record<string, string> = {
  deep_research: "deep-research",
  literature_management: "literature",
  opening_research: "opening-research",
  thesis_writing: "thesis-writing",
  figure_generation: "figure-generation",
  compile_export: "compile-export",
  literature_search: "literature-search",
  paper_analysis: "paper-analysis",
  writing: "writing",
  proposal_outline: "proposal-outline",
  background_research: "background-research",
  copyright_materials: "copyright-materials",
  technical_description: "technical-description",
  patent_outline: "patent-outline",
  prior_art_search: "prior-art-search",
};

export function getWorkspaceFeatureRoute(
  workspaceId: string,
  featureId: string | null | undefined
): string | null {
  if (!workspaceId || !featureId) {
    return null;
  }

  const route = workspaceFeatureRouteMap[featureId];
  return route ? `/workspaces/${workspaceId}/${route}` : null;
}
