"""Workspace feature skill catalog shared by chat ingress and prompts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkspaceThreadSkillDefinition:
    """Declarative thread skill entry for a workspace.

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


_CHAT_FEATURE_CONTRACT = (
    "Chat 侧职责：这是一个 Compute feature 提案入口，不在聊天里承诺已经启动或完成。"
    "先复用工作区、线程、上传材料和已有产物，只追问最小缺失信息；"
    "信息足够时输出简短 feature 提案，等待控制面显式启动。"
)


def _guidance(
    *,
    purpose: str,
    minimum_inputs: tuple[str, ...],
    output: str,
    not_for: str | None = None,
) -> str:
    """Build a consistent chat-side guidance contract for a thread skill."""
    lines = [
        _CHAT_FEATURE_CONTRACT,
        f"适合启动：{purpose}",
        "最少输入：",
        *[f"- {item}" for item in minimum_inputs],
        f"输出产物：{output}",
    ]
    if not_for:
        lines.append(f"不适合：{not_for}")
    lines.extend(
        [
            "启动判断：如果最少输入已经具备，只需复述 feature、关键参数和预期产物；不要继续做完整访谈。",
            "证据边界：涉及文献、专利、实验数据、期刊信息或法规事实时，必须标注待核验，不要编造来源。",
        ]
    )
    return "\n".join(lines)


# ── Thesis Skills ──────────────────────────────────────────────

_THESIS_SKILLS = (
    WorkspaceThreadSkillDefinition(
        id="deep-research",
        name="深度调研",
        description="适合把论文方向系统化调研为文献线索、趋势和研究空白",
        feature_id="deep_research",
        icon="search",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户需要系统理解一个论文方向、补齐文献线索、识别研究空白或收敛选题。",
            minimum_inputs=(
                "研究主题、方向或问题陈述",
                "可选：关键词、学科、时间范围或已知参考文献",
                "期望深度：快速扫描、综述级梳理或选题收敛",
            ),
            output="候选文献线索、趋势分支、研究空白、可推进的问题陈述和下一步阅读建议。",
        ),
        follow_up_skills=("literature-reviewer", "framework-designer"),
    ),
    WorkspaceThreadSkillDefinition(
        id="literature-manager",
        name="文献管理",
        description="适合整理工作区文献、生成分类、阅读计划和补缺建议",
        feature_id="literature_management",
        icon="book-open",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户已有一批文献，需要分类、去重、质量诊断、阅读笔记或补充检索建议。",
            minimum_inputs=(
                "要整理的文献范围：全部、指定论文或上传材料",
                "整理目标：分类、阅读笔记、摘要、引用计划或缺口清单",
            ),
            output="文献主题聚类、质量评估、阅读/引用建议和需要补充的关键文献方向。",
        ),
        follow_up_skills=("deep-research",),
    ),
    WorkspaceThreadSkillDefinition(
        id="literature-reviewer",
        name="开题调研",
        description="适合把选题背景整理为开题报告或文献综述型材料",
        feature_id="opening_research",
        defaults=(("report_type", "literature_review"),),
        icon="file-text",
        color="cyan",
        guidance_prompt=_guidance(
            purpose="用户需要开题报告、文献综述或可行性分析的研究背景材料。",
            minimum_inputs=(
                "选题、研究方向或拟解决的问题",
                "目标产物：开题报告、文献综述或可行性分析",
                "可选：导师要求、学校模板、已读文献或工作区产物",
            ),
            output="按开题/综述结构组织的背景、现状、问题、方法路线和待补证据清单。",
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="framework-designer",
        name="大纲设计",
        description="适合把论文主题收敛为章节结构、摘要和写作路线",
        feature_id="thesis_writing",
        defaults=(("action", "generate_outline"),),
        icon="list",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户已经有论文题目或研究方向，需要生成可执行的章节大纲和写作计划。",
            minimum_inputs=(
                "论文题目或研究主题",
                "目标字数、学位层次或章节数量要求（如有）",
                "可选：Deep Research 产物、导师要求或已有草稿",
            ),
            output="结构化论文大纲、章节定位、建议字数、关键论点和后续章节写作入口。",
        ),
        follow_up_skills=("fullpaper-writer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="fullpaper-writer",
        name="论文撰写",
        description="适合基于大纲和证据撰写全文草稿或指定章节",
        feature_id="thesis_writing",
        defaults=(("action", "write_all"),),
        icon="pen",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户需要在既有大纲、章节计划或文献线索基础上产出论文正文草稿。",
            minimum_inputs=(
                "写作范围：全文、指定章节或指定小节",
                "论文题目、章节标题/索引或已有大纲",
                "目标字数、写作语言和可用引用线索（如有）",
            ),
            output="可落库的章节/全文草稿、引用线索、缺证据标记和后续修订建议。",
            not_for="没有题目、大纲和文献基础时的一键全文生成；应先启动调研或大纲设计。",
        ),
        follow_up_skills=("figure-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="适合把论文中的流程、架构、数据或概念转成图表产物",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要论文图表、流程图、架构图、数据图或概念图，并希望进入图表生成流程。",
            minimum_inputs=(
                "图表要表达的概念、流程、结构或数据关系",
                "图表类型或使用场景：流程图、架构图、数据图、概念图等",
                "所属章节、图题/图注意图或风格要求（如有）",
            ),
            output="图表规划、生成策略、可渲染图表产物和可写入正文的图注说明。",
        ),
        follow_up_skills=(),
    ),
)


# ── SCI Skills ─────────────────────────────────────────────────

_SCI_SKILLS = (
    WorkspaceThreadSkillDefinition(
        id="deep-research",
        name="文献检索",
        description="适合围绕 SCI 主题做系统检索、筛选和研究空白识别",
        feature_id="literature_search",
        icon="search",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户需要为 SCI 选题建立候选文献池、筛选高相关论文或识别 research gap。",
            minimum_inputs=(
                "检索主题、问题陈述或关键词",
                "学科/领域和可选筛选条件：年份、语言、期刊/会议范围",
                "可选：已有核心文献或数据库偏好",
            ),
            output="候选论文、高相关命中、检索过滤建议、研究方向摘要和待核验来源提示。",
        ),
        follow_up_skills=("paper-analyst", "literature-reviewer"),
    ),
    WorkspaceThreadSkillDefinition(
        id="paper-analyst",
        name="论文分析",
        description="适合拆解单篇论文的方法、实验、结论和可复用写法",
        feature_id="paper_analysis",
        icon="microscope",
        color="cyan",
        guidance_prompt=_guidance(
            purpose="用户需要对论文标题、PDF、摘要或工作区论文做结构化深读。",
            minimum_inputs=(
                "论文标题、reference_id、PDF/上传材料或摘要",
                "分析重点：方法、实验、结论、创新点、写法或对比",
                "可选：要比较的论文或目标章节用途",
            ),
            output="方法/实验/结论/创新点拆解、质量评估、可复用写作点和后续研究建议。",
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="section-writer",
        name="章节写作",
        description="适合基于已有上下文撰写 SCI 指定章节或段落草稿",
        feature_id="writing",
        icon="pen",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户需要撰写 Introduction、Method、Results、Discussion 等指定 SCI 章节。",
            minimum_inputs=(
                "章节类型或章节标题",
                "论文题目、章节核心论点或要表达的贡献",
                "目标字数、语言、引用风格和可用上下文产物（如有）",
            ),
            output="英文 SCI 章节草稿、段落结构、参考线索和证据不足标记。",
            not_for="缺少题目、论点和实验/文献证据时的完整论文生成；应先做框架或检索。",
        ),
        follow_up_skills=("peer-reviewer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="literature-reviewer",
        name="文献综述",
        description="适合把已有文献和主题整理为 SCI 相关工作/综述结构",
        feature_id="literature_review",
        icon="book-open",
        color="cyan",
        guidance_prompt=_guidance(
            purpose="用户需要把文献池沉淀为 Related Work、综述摘要或研究空白分析。",
            minimum_inputs=(
                "综述主题和范围",
                "已有核心文献、检索产物或工作区文献上下文",
                "组织方式：按主题、方法、时间、任务或争议点",
            ),
            output="结构化文献综述、关键论文作用、研究空白和可写成论文的问题陈述。",
        ),
        follow_up_skills=("framework-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="framework-designer",
        name="框架大纲",
        description="适合把 SCI 选题收敛为摘要、关键词、贡献和章节框架",
        feature_id="framework_outline",
        icon="list",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户已有论文主题或初步贡献，需要形成 SCI 摘要、关键词和整体结构。",
            minimum_inputs=(
                "论文题目或研究主题",
                "核心创新点、方法路线或目标贡献",
                "可选：目标期刊、上下文产物、章节结构偏好",
            ),
            output="Abstract、keywords、章节框架、贡献点表达和下一章写作建议。",
        ),
        follow_up_skills=("section-writer", "figure-designer"),
    ),
    WorkspaceThreadSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="适合为 SCI 方法、实验或结果设计图表与示意图",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要方法图、实验流程图、架构图、数据图或论文示意图。",
            minimum_inputs=(
                "图表要表达的核心概念、流程、模块或数据关系",
                "图表类型和计划放入的章节",
                "可选：风格、配色、数据输入或图注意图",
            ),
            output="图表规划、生成策略、图表产物和可进入论文的 caption/说明文字。",
        ),
        follow_up_skills=("peer-reviewer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="peer-reviewer",
        name="同行评审",
        description="适合从审稿人视角定位稿件薄弱点并形成修订动作",
        feature_id="peer_review",
        icon="shield-check",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户有论文草稿、摘要或章节，需要审稿式质量诊断和修改优先级。",
            minimum_inputs=(
                "要评审的稿件内容：当前草稿、摘要、章节或粘贴片段",
                "评审侧重点：创新性、方法、实验、写作质量或目标期刊标准",
                "可选：目标期刊/会议或审稿意见上下文",
            ),
            output="总体评价、优点、主要问题、优先级修订动作和可直接落稿的改写方向。",
        ),
        follow_up_skills=("journal-recommender",),
    ),
    WorkspaceThreadSkillDefinition(
        id="journal-recommender",
        name="期刊推荐",
        description="适合基于论文画像推荐候选期刊和投稿策略",
        feature_id="journal_recommend",
        icon="compass",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户需要根据论文主题、摘要和质量定位投稿期刊或备选梯队。",
            minimum_inputs=(
                "论文题目、摘要或研究主题",
                "学科方向和方法/实验类型",
                "可选：影响因子、分区、审稿周期、开放获取或出版社偏好",
            ),
            output="论文画像、候选期刊、适配理由、投稿前补强点和信息待核验提示。",
            not_for="把未核验的分区、影响因子、版面费或审稿周期当作确定事实。",
        ),
        follow_up_skills=(),
    ),
)


# ── Proposal Skills ────────────────────────────────────────────

_PROPOSAL_SKILLS = (
    WorkspaceThreadSkillDefinition(
        id="proposal-writer",
        name="计划书撰写",
        description="适合把研究课题整理为计划书/基金申报书框架",
        feature_id="proposal_outline",
        icon="file-text",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户需要形成研究计划书、基金申请书或项目申报书的主体框架。",
            minimum_inputs=(
                "研究课题方向、核心问题或项目主题",
                "申报类型：国自然、省部级、校级、企业联合等",
                "研究周期、格式要求或评审侧重点（如有）",
            ),
            output="申报书章节大纲、研究目标、技术路线、里程碑、风险和预算框架。",
        ),
        follow_up_skills=("experiment-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="background-scout",
        name="背景调研",
        description="适合为申报书调研领域现状、问题清单和可行方向",
        feature_id="background_research",
        icon="search",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户需要为项目立项依据、领域现状或问题清单补背景调研。",
            minimum_inputs=(
                "调研关键词、主题或背景问题",
                "行业/学科范围",
                "时间范围和深度：近几年、全面梳理或竞品/技术路线对比",
            ),
            output="现状综述、主要问题、可行技术方向、参考线索和待核验标记。",
        ),
        follow_up_skills=("proposal-writer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="experiment-designer",
        name="实验设计",
        description="适合把研究目标转成可检验假设、变量和评估方案",
        feature_id="experiment_design",
        icon="flask-conical",
        color="cyan",
        guidance_prompt=_guidance(
            purpose="用户需要为研究计划设计实验路线、变量控制、评估指标或风险预案。",
            minimum_inputs=(
                "研究主题和目标",
                "可检验假设或预期结果",
                "可用数据/样本/设备/资源和评估标准（如有）",
            ),
            output="研究假设、变量定义、实验步骤、评价指标、风险和备选方案。",
        ),
        follow_up_skills=("figure-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="适合为申报书设计技术路线图、流程图和里程碑图",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要把技术路线、研究流程、模块关系或进度安排转为图表。",
            minimum_inputs=(
                "要展示的技术路线、实施流程或里程碑",
                "图表对应的申报书章节",
                "希望突出内容：创新点、关键任务、模块关系或时间安排",
            ),
            output="结构清晰的路线/流程图规划、图表产物和申报书可用图注说明。",
        ),
        follow_up_skills=(),
    ),
)


# ── Software Copyright Skills ─────────────────────────────────

_SOFTWARE_COPYRIGHT_SKILLS = (
    WorkspaceThreadSkillDefinition(
        id="copyright-writer",
        name="著作权材料",
        description="适合整理软著登记基础信息、材料清单和核对项",
        feature_id="copyright_materials",
        icon="file-text",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户需要准备软件著作权登记材料、申请信息和提交前核对清单。",
            minimum_inputs=(
                "软件名称和版本号",
                "申请主体、开发完成日期或首次发表日期（可待补）",
                "核心功能、主要模块、目标平台或源代码模块（如有）",
            ),
            output="软著材料清单、软件画像、说明书/代码页准备建议、提交前核对项。",
        ),
        follow_up_skills=("tech-doc-writer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="tech-doc-writer",
        name="技术文档",
        description="适合生成软著技术说明书、模块说明和操作流程文档",
        feature_id="technical_description",
        icon="code",
        color="teal",
        guidance_prompt=_guidance(
            purpose="用户需要软著技术说明书、操作手册、模块设计或数据流程说明。",
            minimum_inputs=(
                "软件名称和版本号",
                "核心模块、部署架构、数据库/中间件和接口协议（可部分缺失）",
                "目标文档类型：技术说明、操作手册或审查材料",
            ),
            output="系统概述、模块设计、数据流、部署架构、安全权限和操作步骤章节。",
        ),
        follow_up_skills=("figure-designer",),
    ),
    WorkspaceThreadSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="适合为软著材料生成架构图、流程图和模块关系图",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要把软件架构、业务流程、数据流程或模块关系画成软著材料图。",
            minimum_inputs=(
                "软件核心模块和模块关系",
                "需要展示的业务流程、数据流程或部署结构",
                "图表用途：技术说明、操作流程、材料解释或截图补充",
            ),
            output="软著材料可用的结构图/流程图规划、图表产物和说明文字。",
        ),
        follow_up_skills=(),
    ),
)


# ── Patent Skills ──────────────────────────────────────────────

_PATENT_SKILLS = (
    WorkspaceThreadSkillDefinition(
        id="patent-drafter",
        name="专利撰写",
        description="适合把技术方案整理为专利说明书框架和权利要求草案",
        feature_id="patent_outline",
        icon="lightbulb",
        color="navy",
        guidance_prompt=_guidance(
            purpose="用户需要从技术方案、创新点或交底材料生成专利撰写框架。",
            minimum_inputs=(
                "核心创新点或技术方案描述",
                "技术领域、应用场景和预期实施方式（可部分缺失）",
                "专利类型或保护重点：方法、装置、系统、实用新型等",
            ),
            output="说明书章节框架、独立/从属权利要求草案、实施例提示和证据补充点。",
            not_for="替代专利代理师完成法律意见；新颖性、创造性和权利稳定性仍需专业核验。",
        ),
        follow_up_skills=("prior-art-scout", "figure-designer"),
    ),
    WorkspaceThreadSkillDefinition(
        id="prior-art-scout",
        name="现有技术检索",
        description="适合围绕技术特征做现有技术对比和新颖性风险识别",
        feature_id="prior_art_search",
        icon="search",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要检索相近专利/文献，评估技术方案的新颖性风险和规避方向。",
            minimum_inputs=(
                "关键技术特征、关键词或核心概念",
                "检索范围：国内专利、国际专利、学术文献或 IPC/CPC 分类",
                "时间范围和重点技术领域（如有）",
            ),
            output="检索范围、对比表、新颖性风险、规避建议和后续权利要求调整方向。",
        ),
        follow_up_skills=("patent-drafter",),
    ),
    WorkspaceThreadSkillDefinition(
        id="figure-designer",
        name="图表设计",
        description="适合为专利交底和说明书生成结构图、流程图和关系图",
        feature_id="figure_generation",
        icon="image",
        color="brass",
        guidance_prompt=_guidance(
            purpose="用户需要把专利技术方案、装置结构、方法流程或实施例关系画成说明书附图。",
            minimum_inputs=(
                "技术方案的结构组成、步骤流程或模块关系",
                "图表对应的权利要求、实施例或说明书章节",
                "希望突出展示的创新机制和附图标注需求（如有）",
            ),
            output="专利图表规划、图表产物、附图说明和可写入说明书的描述文本。",
        ),
        follow_up_skills=("patent-drafter",),
    ),
)


# ── Aggregate Registry ─────────────────────────────────────────

WORKSPACE_THREAD_SKILLS: dict[str, tuple[WorkspaceThreadSkillDefinition, ...]] = {
    "thesis": _THESIS_SKILLS,
    "sci": _SCI_SKILLS,
    "proposal": _PROPOSAL_SKILLS,
    "software_copyright": _SOFTWARE_COPYRIGHT_SKILLS,
    "patent": _PATENT_SKILLS,
}

SKILL_TO_FEATURE: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {workspace_type: {skill.id: skill.to_mapping_entry() for skill in skills} for workspace_type, skills in WORKSPACE_THREAD_SKILLS.items()}

FEATURE_TO_DEFAULT_SKILL: dict[str, dict[str, str]] = {
    "thesis": {
        "deep_research": "deep-research",
        "literature_management": "literature-manager",
        "opening_research": "literature-reviewer",
        "thesis_writing": "framework-designer",
        "figure_generation": "figure-designer",
    },
    "sci": {
        "literature_search": "deep-research",
        "paper_analysis": "paper-analyst",
        "writing": "section-writer",
        "literature_review": "literature-reviewer",
        "framework_outline": "framework-designer",
        "figure_generation": "figure-designer",
        "peer_review": "peer-reviewer",
        "journal_recommend": "journal-recommender",
    },
    "proposal": {
        "proposal_outline": "proposal-writer",
        "background_research": "background-scout",
        "experiment_design": "experiment-designer",
        "figure_generation": "figure-designer",
    },
    "software_copyright": {
        "copyright_materials": "copyright-writer",
        "technical_description": "tech-doc-writer",
        "figure_generation": "figure-designer",
    },
    "patent": {
        "patent_outline": "patent-drafter",
        "prior_art_search": "prior-art-scout",
        "figure_generation": "figure-designer",
    },
}


def list_workspace_thread_skills(
    workspace_type: str | None,
) -> tuple[WorkspaceThreadSkillDefinition, ...]:
    """Return thread skill definitions for the given workspace type."""
    if not workspace_type:
        return ()
    return WORKSPACE_THREAD_SKILLS.get(workspace_type, ())


def get_skill_by_id(
    workspace_type: str | None,
    skill_id: str,
) -> WorkspaceThreadSkillDefinition | None:
    """Look up a single skill by workspace type and skill ID."""
    for skill in list_workspace_thread_skills(workspace_type):
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
) -> tuple[WorkspaceThreadSkillDefinition, ...]:
    """Return all thread skills that can launch the given feature."""
    normalized_feature_id = str(feature_id or "").strip()
    if not workspace_type or not normalized_feature_id:
        return ()
    return tuple(skill for skill in list_workspace_thread_skills(workspace_type) if skill.feature_id == normalized_feature_id)


def list_feature_skill_ids(
    workspace_type: str | None,
    feature_id: str,
) -> tuple[str, ...]:
    """Return canonical thread skill IDs for a feature."""
    return tuple(skill.id for skill in list_feature_skills(workspace_type, feature_id))


def resolve_skill_for_feature(
    workspace_type: str | None,
    feature_id: str,
    *,
    params: Mapping[str, Any] | None = None,
    preferred_skill_id: str | None = None,
) -> WorkspaceThreadSkillDefinition | None:
    """Resolve the canonical thread skill for a feature execution."""
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
