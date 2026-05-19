import type { WorkspaceCapability } from "@/lib/api";

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

function readStringParam(
  params: Record<string, unknown>,
  ...keys: string[]
): string {
  for (const key of keys) {
    const value = params[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

/**
 * Return the optional skill id encoded in the URL seed.  The legacy resolver
 * that mapped featureId → default skill via the in-process registry is gone;
 * capability/skill routing now happens server-side in the chat agent based on
 * the DB-backed capability catalog.
 */
export function resolveWorkspaceThreadEntrySkill(options: {
  seed: WorkspaceThreadEntrySeed | null | undefined;
}): string | null {
  return options.seed?.skillId ?? null;
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
  searchParams: SearchParamsLike | null | undefined
): WorkspaceThreadEntrySeed | null {
  if (!searchParams) {
    return null;
  }

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
 * Detailed LLM instructions are produced server-side via the DB-backed
 * capability catalog rendered into the chat system prompt.
 */
export function buildWorkspaceThreadEntryPrompt(options: {
  seed: WorkspaceThreadEntrySeed;
  feature?: Pick<WorkspaceCapability, "name" | "description"> | null;
}): string {
  const { seed, feature } = options;

  // Onboarding: brief greeting, not the full instruction block
  if (seed.featureId === "__onboarding__") {
    return "你好，我刚创建了这个工作区，请帮我开始。";
  }

  // Feature entry: brief request with feature name only
  const featureLabel = feature?.name?.trim() || seed.featureId.replace(/_/g, " ");
  if (
    typeof seed.params?.entry === "string" &&
    seed.params.entry.trim().toLowerCase() === "resume"
  ) {
    const executionId =
      typeof seed.params?.execution_id === "string"
        ? seed.params.execution_id.trim()
        : "";
    if (executionId) {
      return `请继续「${featureLabel}」的执行 (execution_id: ${executionId})。`;
    }
    return `请继续「${featureLabel}」的执行。`;
  }

  const followUpPrompt = readStringParam(seed.params, "follow_up_prompt");
  if (followUpPrompt) {
    return followUpPrompt;
  }

  const promptParts = [`请帮我开始「${featureLabel}」。`];
  const paperTitle = readStringParam(seed.params, "paper_title", "title");
  const paperAbstract = readStringParam(seed.params, "paper_abstract", "abstract");
  const topic = readStringParam(seed.params, "topic", "query");

  if (paperTitle) {
    promptParts.push(`论文标题：${paperTitle}。`);
  }
  if (paperAbstract) {
    promptParts.push(`摘要：${paperAbstract}。`);
  }
  if (topic) {
    promptParts.push(`研究主题：${topic}。`);
  }

  return promptParts.join(" ");
}

export function buildWorkspaceThreadEntryMetadata(options: {
  seed: WorkspaceThreadEntrySeed;
}): Record<string, unknown> {
  const { seed } = options;
  const params = { ...seed.params };
  const executionId =
    typeof params.execution_id === "string" && params.execution_id.trim()
      ? params.execution_id.trim()
      : null;

  return {
    entry_seed: {
      feature_id: seed.featureId,
      skill_id: seed.skillId,
      params,
    },
    orchestration: {
      feature_id: seed.featureId,
      source: "workspace_entry",
      entry:
        typeof params.entry === "string" && params.entry.trim()
          ? params.entry.trim()
          : "open",
      execution_id: executionId,
      params,
    },
  };
}
