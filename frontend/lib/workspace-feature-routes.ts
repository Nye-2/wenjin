type RouteParamValue =
  | string
  | number
  | boolean
  | Array<string | number | boolean>
  | null
  | undefined;

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

  const pathname = `/workspaces/${workspaceId}/chat/new`;
  const query = new URLSearchParams();
  query.set("feature", featureId);
  appendWorkspaceFeatureQuery(query, params);

  const suffix = query.toString();
  return suffix ? `${pathname}?${suffix}` : pathname;
}
