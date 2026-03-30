import type { WorkspaceFeature } from "@/lib/api";

type SearchParamsLike = {
  get(name: string): string | null;
  getAll(name: string): string[];
  keys(): IterableIterator<string>;
};

export interface WorkspaceChatEntrySeed {
  featureId: string;
  skillId: string | null;
  params: Record<string, unknown>;
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

export function parseWorkspaceChatEntrySeed(
  searchParams: SearchParamsLike
): WorkspaceChatEntrySeed | null {
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

function humanizeParamLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPromptValue(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const items = value
      .map((item) => formatPromptValue(item))
      .filter((item): item is string => Boolean(item));
    return items.length > 0 ? items.join(", ") : null;
  }
  return null;
}

export function buildWorkspaceChatEntryPrompt(options: {
  seed: WorkspaceChatEntrySeed;
  feature?: Pick<WorkspaceFeature, "name" | "description"> | null;
}): string {
  const { seed, feature } = options;

  if (seed.featureId === "__onboarding__") {
    const wsType = String(seed.params.__onboarding_type ?? "sci");
    return buildOnboardingEntryPrompt(wsType);
  }

  const featureLabel = feature?.name?.trim() || seed.featureId.replace(/_/g, " ");
  const promptLines = [`请帮我开始「${featureLabel}」。`];

  if (feature?.description?.trim()) {
    promptLines.push(`目标：${feature.description.trim()}`);
  }

  const paramLines = Object.entries(seed.params)
    .map(([key, value]) => {
      const formatted = formatPromptValue(value);
      if (!formatted) {
        return null;
      }
      return `- ${humanizeParamLabel(key)}: ${formatted}`;
    })
    .filter((line): line is string => Boolean(line));

  if (paramLines.length > 0) {
    promptLines.push("已知参数：");
    promptLines.push(...paramLines);
  }

  promptLines.push("请结合当前工作区上下文推进；如果信息仍不够，请直接指出还缺什么。");
  return promptLines.join("\n");
}

const onboardingPrompts: Record<string, string> = {
  thesis:
    "用户刚刚创建了一个「学位论文」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成从选题调研到终稿交付的全过程，然后问他论文题目或研究方向是什么。如果用户还没定题，引导他说说感兴趣的领域。",
  sci:
    "用户刚刚创建了一个「学术论文」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成文献调研、框架设计、论文撰写和投稿推荐等工作，然后问他论文的研究主题或方向。",
  proposal:
    "用户刚刚创建了一个「研究计划」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成课题背景调研、方案设计和计划书撰写，然后问他课题方向或已有的想法。",
  software_copyright:
    "用户刚刚创建了一个「软件著作权申请」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他生成软件说明书和申请材料，然后问他软件名称和主要功能。",
  patent:
    "用户刚刚创建了一个「专利申请」工作区。请用简洁友好的口吻欢迎用户，告诉他你可以帮他完成技术交底、权利要求书撰写和现有技术检索，然后问他要申请专利的技术方案是什么。",
};

export function buildOnboardingEntryPrompt(workspaceType: string): string {
  return onboardingPrompts[workspaceType] ?? onboardingPrompts.sci;
}
