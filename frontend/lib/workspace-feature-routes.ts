type RouteParamValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

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
  literature_review: "literature-review",
  framework_outline: "framework-outline",
  peer_review: "peer-review",
  journal_recommend: "journal-recommend",
  proposal_outline: "proposal-outline",
  background_research: "background-research",
  experiment_design: "experiment-design",
  copyright_materials: "copyright-materials",
  technical_description: "technical-description",
  patent_outline: "patent-outline",
  prior_art_search: "prior-art-search",
};

export function getWorkspaceFeatureRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  if (!workspaceId || !featureId) {
    return null;
  }

  const route = workspaceFeatureRouteMap[featureId];
  if (!route) {
    return null;
  }

  const pathname = `/workspaces/${workspaceId}/${route}`;
  if (!params) {
    return pathname;
  }

  const query = new URLSearchParams();
  for (const [key, rawValue] of Object.entries(params)) {
    if (rawValue === null || rawValue === undefined || rawValue === "") {
      continue;
    }

    const values = Array.isArray(rawValue) ? rawValue : [rawValue];
    const normalized = values
      .map((value) => String(value).trim())
      .filter(Boolean);
    if (normalized.length === 0) {
      continue;
    }
    query.set(key, normalized.join(","));
  }

  const suffix = query.toString();
  return suffix ? `${pathname}?${suffix}` : pathname;
}
