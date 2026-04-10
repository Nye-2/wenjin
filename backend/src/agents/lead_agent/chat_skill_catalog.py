"""Workspace-aware chat skill catalog shared by bridge and prompt."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkspaceChatSkillDefinition:
    """Declarative chat skill entry for a workspace.

    Each skill is a conversational entry point for a workspace feature.
    It defines how the LLM should guide the user through parameter collection
    and which feature to execute.
    """

    id: str
    name: str
    description: str
    feature_id: str
    defaults: tuple[tuple[str, Any], ...] = ()
    icon: str = "search"
    color: str = "navy"
    guidance_prompt: str = ""
    follow_up_skills: tuple[str, ...] = ()

    def to_mapping_entry(self) -> tuple[str, dict[str, Any]]:
        return self.feature_id, dict(self.defaults)

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "featureId": self.feature_id,
            "icon": self.icon,
            "color": self.color,
            "guidancePrompt": self.guidance_prompt,
            "followUpSkills": list(self.follow_up_skills),
        }


# ── Thesis Skills ──────────────────────────────────────────────

_THESIS_SKILLS = (
    WorkspaceChatSkillDefinition(
        id="deep-research",
        name="深度调研",
        description="系统性检索相关文献，分析研究空白和创新方向",
        feature_id="deep_research",
        icon="search",
        color="navy",
        guidance_prompt=(
            "请以对话方式引导用户明确调研主题。\n"
            "1. 先确认研究方向或感兴趣的领域\n"
            "2. 询问是否有特定关键词或已知的参考文献\n"
            "3. 了解调研的深度需求（综述级/快速了解）\n"
            "收集足够信息后，主动开始执行深度调研。"
        ),
        follow_up_skills=("literature-reviewer", "framework-designer"),
    ),
    WorkspaceChatSkillDefinition(
        id="literature-manager",
        name="文献管理",
        description="整理和分类工作区中的文献资料",
        feature_id="literature_management",
        icon="book-open",
        color="teal",
        guidance_prompt=(
            "询问用户想如何管理文献：\n"
            "1. 是否需要对已有文献进行分类整理\n"
            "2. 是否需要生成阅读笔记或摘要\n"
            "3. 是否需要查找和补充缺失的参考文献\n"
            "根据用户需求组织文献管理工作。"
        ),
        follow_up_skills=("deep-research",),
    ),
    WorkspaceChatSkillDefinition(
        id="literature-reviewer",
        name="开题调研",
        description="生成开题报告或文献综述风格的调研报告",
        feature_id="opening_research",
        defaults=(("report_type", "literature_review"),),
        icon="file-text",
        color="cyan",
        guidance_prompt=(
            "了解用户的开题需求：\n"
            "1. 研究方向和选题背景是什么\n"
            "2. 是否有导师指定的方向或要求\n"
            "3. 需要开题报告还是文献综述\n"
            "根据信息生成相应的调研报告框架。"
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceChatSkillDefinition(
        id="framework-designer",
        name="大纲设计",
        description="生成论文大纲和章节结构",
        feature_id="thesis_writing",
        defaults=(("action", "generate_outline"),),
        icon="list",
        color="navy",
        guidance_prompt=(
            "引导用户明确大纲需求：\n"
            "1. 确认论文题目和主要研究内容\n"
            "2. 了解预期的章节数量和深度\n"
            "3. 是否有特定的论文结构要求（如导师要求）\n"
            "收集信息后生成结构化的论文大纲。"
        ),
        follow_up_skills=("fullpaper-writer",),
    ),
    WorkspaceChatSkillDefinition(
        id="fullpaper-writer",
        name="论文撰写",
        description="基于大纲撰写论文全文或单个章节",
        feature_id="thesis_writing",
        defaults=(("action", "write_all"),),
        icon="pen",
        color="teal",
        guidance_prompt=(
            "确认用户的写作需求：\n"
            "1. 要撰写全文还是单个章节\n"
            "2. 如果是单章节，确认要写哪一章及其主题\n"
            "3. 了解目标字数和写作风格要求\n"
            "4. 是否有已有的大纲或草稿可以参考\n"
            "根据需求开始撰写。"
        ),
        follow_up_skills=("figure-designer", "doc-compiler"),
    ),
    WorkspaceChatSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="设计实验流程图、架构图和数据可视化",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=(
            "了解用户的图表需求：\n"
            "1. 要表达什么概念、流程或数据\n"
            "2. 图表类型（流程图/架构图/数据图表/对比图）\n"
            "3. 关联到论文的哪个章节\n"
            "根据描述设计和生成图表。"
        ),
        follow_up_skills=("doc-compiler",),
    ),
    WorkspaceChatSkillDefinition(
        id="doc-compiler",
        name="编译导出",
        description="编译论文并导出为最终格式",
        feature_id="compile_export",
        icon="package",
        color="slate",
        guidance_prompt=(
            "确认编译和导出需求：\n"
            "1. 要编译的内容范围（全文/部分章节）\n"
            "2. 输出格式（PDF/Word/LaTeX）\n"
            "3. 是否有特定的排版模板要求\n"
            "检查是否有缺失的章节或引用后开始编译。"
        ),
        follow_up_skills=(),
    ),
)


# ── SCI Skills ─────────────────────────────────────────────────

_SCI_SKILLS = (
    WorkspaceChatSkillDefinition(
        id="deep-research",
        name="文献检索",
        description="系统性检索学术文献，识别研究空白",
        feature_id="literature_search",
        icon="search",
        color="navy",
        guidance_prompt=(
            "引导用户明确检索需求：\n"
            "1. 检索的主题和关键词是什么\n"
            "2. 检索范围（时间、期刊、语言）\n"
            "3. 是否有特定的数据库偏好\n"
            "确认后直接开始系统性检索。"
        ),
        follow_up_skills=("paper-analyst", "literature-reviewer"),
    ),
    WorkspaceChatSkillDefinition(
        id="paper-analyst",
        name="论文分析",
        description="深入分析论文的方法、实验和创新点",
        feature_id="paper_analysis",
        icon="microscope",
        color="cyan",
        guidance_prompt=(
            "了解分析需求：\n"
            "1. 要分析的论文标题或请用户提供 PDF\n"
            "2. 分析重点：方法论/实验设计/结论/创新点\n"
            "3. 是否需要与其他论文进行对比分析\n"
            "明确后开始结构化分析。"
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceChatSkillDefinition(
        id="section-writer",
        name="章节写作",
        description="撰写论文的特定章节或段落",
        feature_id="writing",
        icon="pen",
        color="teal",
        guidance_prompt=(
            "了解写作需求：\n"
            "1. 要写的章节类型（Introduction/Method/Results/Discussion 等）\n"
            "2. 章节主题和核心论点\n"
            "3. 字数和写作风格要求\n"
            "4. 引用格式要求\n"
            "根据需求撰写该章节。"
        ),
        follow_up_skills=("peer-reviewer",),
    ),
    WorkspaceChatSkillDefinition(
        id="literature-reviewer",
        name="文献综述",
        description="将已有文献整理为结构化的文献综述",
        feature_id="literature_review",
        icon="book-open",
        color="cyan",
        guidance_prompt=(
            "了解综述需求：\n"
            "1. 综述的具体主题和范围\n"
            "2. 是否有已读的核心文献\n"
            "3. 综述的深度和篇幅要求\n"
            "4. 综述的组织方式（按主题/按时间/按方法）\n"
            "收集信息后开始生成文献综述。"
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceChatSkillDefinition(
        id="framework-designer",
        name="框架大纲",
        description="生成论文结构框架、摘要和关键词",
        feature_id="framework_outline",
        icon="list",
        color="navy",
        guidance_prompt=(
            "引导用户明确框架需求：\n"
            "1. 论文主题和核心创新点\n"
            "2. 期望的章节数量和结构\n"
            "3. 是否需要同时生成摘要和关键词\n"
            "根据信息生成结构化的论文框架。"
        ),
        follow_up_skills=("section-writer",),
    ),
    WorkspaceChatSkillDefinition(
        id="peer-reviewer",
        name="同行评审",
        description="从审稿人视角检查论文，指出薄弱环节",
        feature_id="peer_review",
        icon="shield-check",
        color="brass",
        guidance_prompt=(
            "确认评审需求：\n"
            "1. 确认要评审的论文内容（当前草稿/特定章节）\n"
            "2. 评审侧重点（创新性/方法论/实验/写作质量）\n"
            "3. 目标期刊的评审标准（如有）\n"
            "以审稿人视角给出结构化评审意见。"
        ),
        follow_up_skills=("journal-recommender",),
    ),
    WorkspaceChatSkillDefinition(
        id="journal-recommender",
        name="期刊推荐",
        description="根据论文主题和质量推荐目标期刊",
        feature_id="journal_recommend",
        icon="compass",
        color="teal",
        guidance_prompt=(
            "了解投稿需求：\n"
            "1. 论文的研究主题和方法\n"
            "2. 目标影响因子范围\n"
            "3. 是否有期刊类型偏好（综合/专业）\n"
            "4. 对审稿周期的要求\n"
            "根据论文特征推荐匹配的期刊并说明理由。"
        ),
        follow_up_skills=(),
    ),
)


# ── Proposal Skills ────────────────────────────────────────────

_PROPOSAL_SKILLS = (
    WorkspaceChatSkillDefinition(
        id="proposal-writer",
        name="计划书撰写",
        description="生成研究计划书或基金申请书框架",
        feature_id="proposal_outline",
        icon="file-text",
        color="navy",
        guidance_prompt=(
            "了解计划书需求：\n"
            "1. 研究课题方向和核心问题\n"
            "2. 目标基金类型（国自然/省基金/校级等）\n"
            "3. 是否有特定的格式要求\n"
            "4. 研究周期预期\n"
            "根据信息生成符合要求的计划书框架。"
        ),
        follow_up_skills=("experiment-designer",),
    ),
    WorkspaceChatSkillDefinition(
        id="background-scout",
        name="背景调研",
        description="分析研究领域现状和发展趋势",
        feature_id="background_research",
        icon="search",
        color="teal",
        guidance_prompt=(
            "了解调研需求：\n"
            "1. 要调研的具体背景问题\n"
            "2. 需要覆盖的范围和深度\n"
            "3. 关注的时间范围（近几年/全面梳理）\n"
            "明确后开始系统性背景调研。"
        ),
        follow_up_skills=("proposal-writer",),
    ),
    WorkspaceChatSkillDefinition(
        id="experiment-designer",
        name="实验设计",
        description="设计研究实验方案，包含假设和评估策略",
        feature_id="experiment_design",
        icon="flask-conical",
        color="cyan",
        guidance_prompt=(
            "引导实验设计：\n"
            "1. 研究假设是什么\n"
            "2. 实验目标和预期结果\n"
            "3. 可用的实验条件和资源\n"
            "4. 评估指标和成功标准\n"
            "根据信息设计完整的实验方案。"
        ),
        follow_up_skills=(),
    ),
)


# ── Software Copyright Skills ─────────────────────────────────

_SOFTWARE_COPYRIGHT_SKILLS = (
    WorkspaceChatSkillDefinition(
        id="copyright-writer",
        name="著作权材料",
        description="生成符合版权局要求的软件著作权登记材料",
        feature_id="copyright_materials",
        icon="file-text",
        color="navy",
        guidance_prompt=(
            "收集著作权申请所需信息：\n"
            "1. 软件名称和版本号\n"
            "2. 开发完成日期和首次发表日期\n"
            "3. 软件的核心功能和主要模块\n"
            "4. 申请类型（原始取得/继受取得）\n"
            "收集完毕后生成软件说明书等申请材料。"
        ),
        follow_up_skills=("tech-doc-writer",),
    ),
    WorkspaceChatSkillDefinition(
        id="tech-doc-writer",
        name="技术文档",
        description="撰写软件技术说明书或用户操作手册",
        feature_id="technical_description",
        icon="code",
        color="teal",
        guidance_prompt=(
            "了解文档需求：\n"
            "1. 软件的技术架构和主要技术栈\n"
            "2. 核心功能模块和数据流\n"
            "3. 目标读者（技术人员/审查员/用户）\n"
            "4. 需要的文档类型（技术说明/操作手册）\n"
            "根据需求撰写相应的技术文档。"
        ),
        follow_up_skills=(),
    ),
)


# ── Patent Skills ──────────────────────────────────────────────

_PATENT_SKILLS = (
    WorkspaceChatSkillDefinition(
        id="patent-drafter",
        name="专利撰写",
        description="撰写专利申请文件，包含权利要求书和说明书",
        feature_id="patent_outline",
        icon="lightbulb",
        color="navy",
        guidance_prompt=(
            "了解专利申请需求：\n"
            "1. 技术方案的核心创新点是什么\n"
            "2. 属于发明专利还是实用新型\n"
            "3. 技术领域和应用场景\n"
            "4. 与现有技术相比的主要优势\n"
            "收集信息后撰写权利要求书和说明书。"
        ),
        follow_up_skills=("prior-art-scout",),
    ),
    WorkspaceChatSkillDefinition(
        id="prior-art-scout",
        name="现有技术检索",
        description="检索相关专利和文献，评估技术方案新颖性",
        feature_id="prior_art_search",
        icon="search",
        color="brass",
        guidance_prompt=(
            "了解检索需求：\n"
            "1. 技术方案的关键特征和核心概念\n"
            "2. 检索范围（国内专利/国际专利/学术文献）\n"
            "3. 重点关注的技术领域\n"
            "确认后开始系统性现有技术检索。"
        ),
        follow_up_skills=("patent-drafter",),
    ),
)


# ── Aggregate Registry ─────────────────────────────────────────

WORKSPACE_CHAT_SKILLS: dict[str, tuple[WorkspaceChatSkillDefinition, ...]] = {
    "thesis": _THESIS_SKILLS,
    "sci": _SCI_SKILLS,
    "proposal": _PROPOSAL_SKILLS,
    "software_copyright": _SOFTWARE_COPYRIGHT_SKILLS,
    "patent": _PATENT_SKILLS,
}

SKILL_TO_FEATURE: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
    workspace_type: {
        skill.id: skill.to_mapping_entry()
        for skill in skills
    }
    for workspace_type, skills in WORKSPACE_CHAT_SKILLS.items()
}

FEATURE_TO_DEFAULT_SKILL: dict[str, dict[str, str]] = {
    "thesis": {
        "deep_research": "deep-research",
        "literature_management": "literature-manager",
        "opening_research": "literature-reviewer",
        "thesis_writing": "framework-designer",
        "figure_generation": "figure-designer",
        "compile_export": "doc-compiler",
    },
    "sci": {
        "literature_search": "deep-research",
        "paper_analysis": "paper-analyst",
        "writing": "section-writer",
        "literature_review": "literature-reviewer",
        "framework_outline": "framework-designer",
        "peer_review": "peer-reviewer",
        "journal_recommend": "journal-recommender",
    },
    "proposal": {
        "proposal_outline": "proposal-writer",
        "background_research": "background-scout",
        "experiment_design": "experiment-designer",
    },
    "software_copyright": {
        "copyright_materials": "copyright-writer",
        "technical_description": "tech-doc-writer",
    },
    "patent": {
        "patent_outline": "patent-drafter",
        "prior_art_search": "prior-art-scout",
    },
}


def list_workspace_chat_skills(
    workspace_type: str | None,
) -> tuple[WorkspaceChatSkillDefinition, ...]:
    """Return chat skill definitions for the given workspace type."""
    if not workspace_type:
        return ()
    return WORKSPACE_CHAT_SKILLS.get(workspace_type, ())


def get_skill_by_id(
    workspace_type: str | None,
    skill_id: str,
) -> WorkspaceChatSkillDefinition | None:
    """Look up a single skill by workspace type and skill ID."""
    for skill in list_workspace_chat_skills(workspace_type):
        if skill.id == skill_id:
            return skill
    return None


def get_default_skill_for_feature(
    workspace_type: str | None,
    feature_id: str,
) -> str | None:
    """Return the canonical entry skill for a feature, if one is defined."""
    if not workspace_type or not feature_id:
        return None
    return FEATURE_TO_DEFAULT_SKILL.get(workspace_type, {}).get(feature_id)


def list_feature_skills(
    workspace_type: str | None,
    feature_id: str,
) -> tuple[WorkspaceChatSkillDefinition, ...]:
    """Return all chat skills that can launch the given feature."""
    normalized_feature_id = str(feature_id or "").strip()
    if not workspace_type or not normalized_feature_id:
        return ()
    return tuple(
        skill
        for skill in list_workspace_chat_skills(workspace_type)
        if skill.feature_id == normalized_feature_id
    )


def list_feature_skill_ids(
    workspace_type: str | None,
    feature_id: str,
) -> tuple[str, ...]:
    """Return canonical chat skill IDs for a feature."""
    return tuple(skill.id for skill in list_feature_skills(workspace_type, feature_id))


def resolve_skill_for_feature(
    workspace_type: str | None,
    feature_id: str,
    *,
    params: Mapping[str, Any] | None = None,
    preferred_skill_id: str | None = None,
) -> WorkspaceChatSkillDefinition | None:
    """Resolve the canonical chat skill for a feature execution."""
    normalized_feature_id = str(feature_id or "").strip()
    if not workspace_type or not normalized_feature_id:
        return None

    normalized_params = params if isinstance(params, Mapping) else {}
    matching_skills = list_feature_skills(workspace_type, normalized_feature_id)
    if not matching_skills:
        return None

    normalized_preferred_skill_id = str(preferred_skill_id or "").strip()
    if normalized_preferred_skill_id:
        preferred_skill = get_skill_by_id(workspace_type, normalized_preferred_skill_id)
        if preferred_skill is not None and preferred_skill.feature_id == normalized_feature_id:
            preferred_defaults = dict(preferred_skill.defaults)
            if not normalized_params or not preferred_defaults:
                return preferred_skill
            if all(normalized_params.get(key) == value for key, value in preferred_defaults.items()):
                return preferred_skill

    if len(matching_skills) == 1:
        return matching_skills[0]

    for skill in matching_skills:
        defaults = dict(skill.defaults)
        if defaults and all(normalized_params.get(key) == value for key, value in defaults.items()):
            return skill

    if workspace_type == "thesis" and normalized_feature_id == "thesis_writing":
        action = str(normalized_params.get("action") or "").strip().lower()
        if action == "write_chapter":
            return get_skill_by_id(workspace_type, "fullpaper-writer")

    default_skill_id = get_default_skill_for_feature(workspace_type, normalized_feature_id)
    if not default_skill_id:
        return None
    return get_skill_by_id(workspace_type, default_skill_id)
