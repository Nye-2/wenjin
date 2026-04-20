type RouteParamValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

function readFirstRouteParamValue(rawValue: RouteParamValue): string | null {
  if (rawValue === null || rawValue === undefined || rawValue === "") {
    return null;
  }

  const values = Array.isArray(rawValue) ? rawValue : [rawValue];
  for (const value of values) {
    const normalized = String(value).trim();
    if (normalized) {
      return normalized;
    }
  }

  return null;
}

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

export function getWorkspaceFeatureRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  return getWorkspaceFeatureThreadRoute(workspaceId, featureId, params);
}

export function getWorkspaceFeatureThreadRoute(
  workspaceId: string,
  featureId: string | null | undefined,
  params?: Record<string, RouteParamValue>
): string | null {
  if (!workspaceId || !featureId) {
    return null;
  }

  const pathname = `/workspaces/${workspaceId}/chat`;
  const query = new URLSearchParams();
  query.set("feature", featureId);

  const explicitSkillId = readFirstRouteParamValue(params?.skill);
  if (explicitSkillId) {
    query.set("skill", explicitSkillId);
  }

  if (params) {
    const queryParams = { ...params };
    delete queryParams.skill;
    appendWorkspaceFeatureQuery(query, queryParams);
  }

  const suffix = query.toString();
  return suffix ? `${pathname}?${suffix}` : pathname;
}
