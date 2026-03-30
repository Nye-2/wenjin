type RouteParamValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

export const workspaceFeatureSkillMap: Record<string, string | null> = {
  deep_research: "deep-research",
  literature_management: "deep-research",
  opening_research: "literature-review",
  thesis_writing: null,
  figure_generation: null,
  compile_export: null,
  literature_search: "deep-research",
  paper_analysis: null,
  writing: null,
  literature_review: "literature-review",
  framework_outline: "framework-designer",
  peer_review: "peer-reviewer",
  journal_recommend: "journal-recommender",
  proposal_outline: "proposal-writer",
  background_research: null,
  experiment_design: "experiment-designer",
  copyright_materials: null,
  technical_description: null,
  patent_outline: null,
  prior_art_search: null,
};

function appendWorkspaceFeatureQuery(
  query: URLSearchParams,
  params?: Record<string, RouteParamValue>
) {
  for (const [key, rawValue] of Object.entries(params ?? {})) {
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
    for (const value of normalized) {
      query.append(key, value);
    }
  }
}

function resolveWorkspaceFeatureSkillId(
  featureId: string,
  params?: Record<string, RouteParamValue>
): string | null {
  if (featureId === "thesis_writing") {
    const action = String(params?.action ?? "").trim().toLowerCase();
    if (action === "generate_outline") {
      return "framework-designer";
    }
    return "fullpaper-writer";
  }

  return workspaceFeatureSkillMap[featureId] ?? null;
}

export function getWorkspaceFeatureRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  return getWorkspaceFeatureChatRoute(workspaceId, featureId, params);
}

export function getWorkspaceFeatureChatRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  if (!workspaceId || !featureId) {
    return null;
  }

  if (!(featureId in workspaceFeatureSkillMap)) {
    return null;
  }

  const pathname = `/workspaces/${workspaceId}/chat/new`;
  const query = new URLSearchParams();
  query.set("feature", featureId);

  const skillId = resolveWorkspaceFeatureSkillId(featureId, params);
  if (skillId) {
    query.set("skill", skillId);
  }

  appendWorkspaceFeatureQuery(query, params);

  const suffix = query.toString();
  return suffix ? `${pathname}?${suffix}` : pathname;
}
