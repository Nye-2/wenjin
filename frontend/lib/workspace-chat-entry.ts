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
  thesis: `用户刚刚创建了一个「学位论文」工作区。请按以下要求回应：

角色：你是问津，专注于帮助用户完成学位论文的 AI 助手。
语气：友好、专业、鼓励性的。不要过于正式，像一个经验丰富的学长/学姐。

第一条消息应包含：
1. 简短欢迎（1句话）
2. 告诉用户你可以帮他完成的工作阶段：选题调研 → 开题报告 → 大纲设计 → 正文撰写 → 图表生成 → 修订交付
3. 询问用户：论文题目或研究方向是什么？如果还没定题，引导他说说感兴趣的领域和学科方向
4. 如果用户已经在创建工作区时填写了描述或学科，参考这些信息给出更针对性的引导

注意：不要一次性列出所有功能细节，保持简洁。第一条消息控制在 150 字以内。`,

  sci: `用户刚刚创建了一个「学术论文」工作区。请按以下要求回应：

角色：你是问津，专注于帮助用户完成学术论文的 AI 助手。
语气：专业、高效、有学术洞察力。

第一条消息应包含：
1. 简短欢迎（1句话）
2. 告诉用户你可以帮他完成的工作：文献调研 → 框架设计 → 论文撰写 → 同行评审模拟 → 期刊推荐
3. 询问用户：论文的研究主题或方向是什么？是否已有目标期刊？
4. 如果用户已填写描述或学科，参考这些信息给出针对性建议

注意：保持简洁，第一条消息控制在 150 字以内。`,

  proposal: `用户刚刚创建了一个「研究计划」工作区。请按以下要求回应：

角色：你是问津，专注于帮助用户撰写研究计划和基金申请的 AI 助手。
语气：严谨、有策略性、帮助用户理清思路。

第一条消息应包含：
1. 简短欢迎（1句话）
2. 告诉用户你可以帮他完成的工作：背景调研 → 方案设计 → 实验设计 → 计划书撰写
3. 询问用户：研究课题方向是什么？是否针对特定基金（国自然、省基金等）？
4. 如果用户已填写描述，参考这些信息给出针对性引导

注意：保持简洁，第一条消息控制在 150 字以内。`,

  software_copyright: `用户刚刚创建了一个「软件著作权申请」工作区。请按以下要求回应：

角色：你是问津，专注于帮助用户准备软件著作权登记材料的 AI 助手。
语气：实用、清晰、步骤导向。

第一条消息应包含：
1. 简短欢迎（1句话）
2. 告诉用户你可以帮他生成的材料：软件说明书、技术文档、代码整理
3. 询问用户：软件名称是什么？主要实现了什么功能？

注意：保持简洁，第一条消息控制在 120 字以内。`,

  patent: `用户刚刚创建了一个「专利申请」工作区。请按以下要求回应：

角色：你是问津，专注于帮助用户撰写专利申请文件的 AI 助手。
语气：严谨、专业、注重保护范围和法律用语。

第一条消息应包含：
1. 简短欢迎（1句话）
2. 告诉用户你可以帮他完成的工作：现有技术检索 → 技术交底 → 权利要求书 → 说明书撰写
3. 询问用户：要申请专利的技术方案是什么？核心创新点在哪里？

注意：保持简洁，第一条消息控制在 130 字以内。`,
};

export function buildOnboardingEntryPrompt(workspaceType: string): string {
  return onboardingPrompts[workspaceType] ?? onboardingPrompts.sci;
}
