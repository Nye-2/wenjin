import type { Artifact } from "@/stores/workspace";

export function findArtifactById(
  artifacts: Artifact[],
  artifactId: string | null | undefined
): Artifact | null {
  if (!artifactId) {
    return null;
  }
  return artifacts.find((artifact) => artifact.id === artifactId) ?? null;
}

export function findLatestArtifact(
  artifacts: Artifact[],
  acceptedTypes: string[]
): Artifact | null {
  const allowedTypes = new Set(acceptedTypes);
  const matches = artifacts
    .filter((artifact) => allowedTypes.has(artifact.type))
    .sort(
      (left, right) =>
        new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    );
  return matches[0] ?? null;
}

export function getArtifactContentRecord(
  artifact: Artifact | null | undefined
): Record<string, unknown> | null {
  if (!artifact?.content || typeof artifact.content !== "object") {
    return null;
  }
  return artifact.content as Record<string, unknown>;
}

export function readString(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

export function readStringArrayLike(
  value: unknown,
  maxItems: number = 8
): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => readString(item))
      .filter((item): item is string => Boolean(item))
      .slice(0, maxItems);
  }

  if (typeof value === "string") {
    return value
      .split(/[\n,，]+/)
      .map((item) => readString(item))
      .filter((item): item is string => Boolean(item))
      .slice(0, maxItems);
  }

  return [];
}

export function joinStringArrayLike(
  value: unknown,
  maxItems: number = 8
): string | null {
  const items = readStringArrayLike(value, maxItems);
  return items.length > 0 ? items.join(",") : null;
}

export function readStringList(value: unknown, maxItems: number = 5): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => readString(item))
    .filter((item): item is string => Boolean(item))
    .slice(0, maxItems);
}

export function readNamedSections(
  value: unknown,
  maxItems: number = 4
): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const record = item as Record<string, unknown>;
      return readString(record.title) ?? readString(record.name) ?? readString(record.id);
    })
    .filter((item): item is string => Boolean(item))
    .slice(0, maxItems);
}
