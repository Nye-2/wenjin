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

const featureEntryInstructions: Record<string, string> = {
  deep_research:
    "请以对话方式引导用户明确调研主题。先确认研究方向，再询问是否有特定关键词或已知参考文献。收集足够信息后，主动开始执行深度调研。",
  literature_search:
    "询问用户要检索的主题和关键词。了解检索范围（时间、期刊、语言）。确认后直接开始检索。",
  literature_review:
    "询问用户要综述的具体主题和范围。了解是否有已读的核心文献。确认综述的深度和篇幅要求。",
  literature_management:
    "询问用户想整理哪些文献，是否需要分类或生成阅读笔记。",
  opening_research:
    "先了解用户的研究方向和选题背景。询问是否有导师指定的方向或要求。根据信息生成开题报告框架。",
  background_research:
    "询问用户要调研的具体背景问题。了解需要覆盖的范围和深度。",
  thesis_writing:
    "先确认用户要做什么：生成大纲、撰写全文还是写单章节。如果是大纲，询问论文题目和主要研究内容；如果是写章节，询问要写哪一章及章节主题。",
  writing:
    "询问用户要写的具体章节或段落主题。了解写作要求（字数、风格、引用格式）。",
  framework_outline:
    "询问论文主题和核心创新点。了解用户期望的章节数量和深度。",
  paper_analysis:
    "询问要分析的论文标题或提供 PDF。明确分析重点：方法、实验、结论还是创新点。",
  peer_review:
    "询问要评审的论文内容或主题。以审稿人视角给出结构化评审意见。",
  journal_recommend:
    "了解论文主题、方法和目标影响因子范围。推荐匹配的期刊并说明理由。",
  figure_generation:
    "询问要表达的概念、流程或数据。了解图表类型（流程图、架构图、数据图表）。",
  proposal_outline:
    "了解研究课题和目标基金类型。询问是否有特定格式要求。",
  experiment_design:
    "了解研究假设和目标。询问实验条件、变量和评估指标。",
  compile_export:
    "确认要编译的内容范围和输出格式。检查是否有缺失的章节或引用。",
  copyright_materials:
    "询问软件名称、版本和核心功能。了解申请类型（原始取得/继受取得）。",
  technical_description:
    "询问软件的技术架构和主要功能模块。了解目标读者（技术人员/审查员）。",
  patent_outline:
    "了解发明的技术领域和核心创新点。区分发明专利还是实用新型。",
  prior_art_search:
    "询问技术方案的关键特征。确认检索范围（国内/国际专利、学术文献）。",
};

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

  const instruction = featureEntryInstructions[seed.featureId];
  if (instruction) {
    promptLines.push("");
    promptLines.push(`引导要求：${instruction}`);
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
