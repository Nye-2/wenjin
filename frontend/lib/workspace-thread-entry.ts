import type { WorkspaceThreadSkill, WorkspaceFeature } from "@/lib/api";

type SearchParamsLike = {
  get(name: string): string | null;
  getAll(name: string): string[];
  keys(): IterableIterator<string>;
};

export interface WorkspaceThreadEntrySeed {
  featureId: string;
  skillId: string | null;
  params: Record<string, unknown>;
}

export function resolveWorkspaceThreadEntrySkill(options: {
  seed: WorkspaceThreadEntrySeed | null | undefined;
  skills: WorkspaceThreadSkill[];
}): string | null {
  const seed = options.seed;
  if (!seed) {
    return null;
  }
  if (seed.skillId) {
    return seed.skillId;
  }
  const matchedSkill = options.skills.find(
    (skill) => skill.featureId === seed.featureId
  );
  return matchedSkill?.id ?? null;
}

function coerceScalarParamValue(value: string): string | number | boolean {
  const normalized = value.trim();
  if (normalized === "true") {
    return true;
  }
  if (normalized === "false") {
    return false;
  }
  if (/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(normalized)) {
    const parsed = Number(normalized);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return value;
}

export function parseWorkspaceThreadEntrySeed(
  searchParams: SearchParamsLike
): WorkspaceThreadEntrySeed | null {
  const featureId = searchParams.get("feature")?.trim();
  if (!featureId) {
    return null;
  }

  const skillId = searchParams.get("skill")?.trim() || null;
  const params: Record<string, unknown> = {};

  for (const key of new Set(searchParams.keys())) {
    if (key === "feature" || key === "skill") {
      continue;
    }

    const rawValues = searchParams
      .getAll(key)
      .map((value) => value.trim())
      .filter(Boolean);
    if (rawValues.length === 0) {
      continue;
    }

    params[key] =
      rawValues.length === 1
        ? coerceScalarParamValue(rawValues[0])
        : rawValues.map(coerceScalarParamValue);
  }

  return {
    featureId,
    skillId,
    params,
  };
}

/**
 * Build a brief, user-visible message for the thread.
 * Detailed LLM instructions are handled by the backend's guidance_prompt
 * in the system prompt — NOT sent as user message content.
 */
export function buildWorkspaceThreadEntryPrompt(options: {
  seed: WorkspaceThreadEntrySeed;
  feature?: Pick<WorkspaceFeature, "name" | "description"> | null;
}): string {
  const { seed, feature } = options;

  // Onboarding: brief greeting, not the full instruction block
  if (seed.featureId === "__onboarding__") {
    return "你好，我刚创建了这个工作区，请帮我开始。";
  }

  // Feature entry: brief request with feature name only
  const featureLabel = feature?.name?.trim() || seed.featureId.replace(/_/g, " ");
  return `请帮我开始「${featureLabel}」。`;
}

// Onboarding prompts have been moved to the backend system prompt.
// The workspace-type-specific guidance is now in:
// 1. _WORKSPACE_TYPE_PROMPTS in agent.py (system prompt per workspace type)
// 2. guidance_prompt in workspace_features/skills.py (per-skill LLM instructions)
