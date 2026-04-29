"""Canonical workspace feature registry."""

from dataclasses import dataclass, field

from src.task.registry import WORKSPACE_FEATURE_TASK

FIGURE_GENERATION_GRAPH_MODULE = "src.agents.graphs.thesis.figure_generation"

CANONICAL_WORKSPACE_TYPES = (
    "sci",
    "thesis",
    "proposal",
    "software_copyright",
    "patent",
)


@dataclass(frozen=True, slots=True)
class FeatureStageDefinition:
    """Immutable feature stage definition."""

    id: str
    label: str


@dataclass(frozen=True, slots=True)
class WorkspaceFeatureDefinition:
    """Canonical feature definition shared across router and task dispatch."""

    workspace_type: str
    id: str
    name: str
    description: str
    icon: str
    agent: str
    agent_label: str
    handler_key: str
    task_type: str = WORKSPACE_FEATURE_TASK
    panel: str | None = None
    stages: tuple[FeatureStageDefinition, ...] = field(default_factory=tuple)
    color: str | None = None
    graph_module: str | None = None
    follow_up_prompt: str | None = None

    def to_api_dict(self) -> dict:
        """Serialize to the frontend API contract."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "agent": self.agent,
            "agentLabel": self.agent_label,
            "taskType": self.task_type,
            "handlerKey": self.handler_key,
            "panel": self.panel,
            "stages": [
                {"id": stage.id, "label": stage.label}
                for stage in self.stages
            ],
            "color": self.color,
            "followUpPrompt": self.follow_up_prompt,
        }


def _stage(id: str, label: str) -> FeatureStageDefinition:
    return FeatureStageDefinition(id=id, label=label)


THESIS_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="deep_research",
        name="深度调研",
        description="深度调研论文主题，收集资料与信息",
        icon="search",
        agent="scout",
        agent_label="Scout",
        handler_key="thesis.deep_research",
        panel="deep_research_panel",
        color="purple",
        stages=(
            _stage("search", "搜索资料"),
            _stage("analyze", "分析信息"),
            _stage("synthesize", "综合整理"),
        ),
        follow_up_prompt="请基于这次深度调研继续收敛研究问题，并给出更具体的创新点与验证路径。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="literature_management",
        name="文献管理",
        description="管理和组织论文参考文献",
        icon="book-open",
        agent="librarian",
        agent_label="Librarian",
        handler_key="thesis.literature_management",
        panel=None,
        stages=(),
        color="emerald",
        follow_up_prompt="请基于这次文献盘点继续指出还缺哪些关键文献，并给出下一轮补充与筛选建议。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="opening_research",
        name="开题调研",
        description="开题报告调研与撰写辅助",
        icon="file-text",
        agent="scout",
        agent_label="Scout",
        handler_key="thesis.opening_research",
        panel="opening_research_panel",
        color="amber",
        stages=(
            _stage("research", "调研背景"),
            _stage("outline", "生成大纲"),
            _stage("refine", "完善内容"),
        ),
        follow_up_prompt="请基于这次研究报告继续补齐研究意义、可行性和技术路线中的薄弱环节。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="thesis_writing",
        name="论文写作",
        description="大纲生成与章节内容撰写",
        icon="pen",
        agent="thesis_writer",
        agent_label="ThesisWriter",
        handler_key="thesis.thesis_writing",
        panel="thesis_editor",
        color="blue",
        stages=(
            _stage("outline", "生成大纲"),
            _stage("write", "撰写内容"),
            _stage("revise", "修订完善"),
        ),
        follow_up_prompt="请基于这次写作结果继续指出结构缺口、逻辑断点和下一步最该补写的部分。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="figure_generation",
        name="图表生成",
        description="规划和生成论文图表",
        icon="image",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="thesis.figure_generation",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
        graph_module=FIGURE_GENERATION_GRAPH_MODULE,
        follow_up_prompt="请基于这次图表结果继续优化图意表达，并给出适合写入正文的说明文字。",
    ),
)

SCI_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="literature_search",
        name="文献检索",
        description="检索相关学术文献",
        icon="search",
        agent="scout",
        agent_label="Scout",
        handler_key="sci.literature_search",
        panel="literature_panel",
        color="emerald",
        stages=(
            _stage("search", "检索文献"),
            _stage("filter", "筛选结果"),
        ),
        follow_up_prompt="请基于这次检索结果筛出最值得精读的文献，并说明各自对后续写作的价值。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="paper_analysis",
        name="论文分析",
        description="分析论文结构和方法",
        icon="microscope",
        agent="analyst",
        agent_label="Analyst",
        handler_key="sci.paper_analysis",
        panel="analysis_panel",
        color="purple",
        stages=(
            _stage("parse", "解析论文"),
            _stage("analyze", "深度分析"),
            _stage("summarize", "生成摘要"),
        ),
        follow_up_prompt="请基于这次论文分析继续拆解方法亮点、实验弱点和最值得复用的写法。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="writing",
        name="论文写作",
        description="撰写学术论文内容",
        icon="pen",
        agent="writer",
        agent_label="Writer",
        handler_key="sci.writing",
        panel="editor_panel",
        color="amber",
        stages=(
            _stage("plan", "规划结构"),
            _stage("write", "撰写内容"),
            _stage("revise", "修订完善"),
        ),
        follow_up_prompt="请基于这次章节草稿继续指出证据缺口、论证薄弱点和下一步最该补写的内容。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="literature_review",
        name="文献综述",
        description="基于现有主题与上下文生成结构化文献综述",
        icon="book-open",
        agent="reviewer",
        agent_label="Reviewer",
        handler_key="sci.literature_review",
        panel="analysis_panel",
        color="cyan",
        stages=(
            _stage("collect", "整理文献"),
            _stage("synthesize", "综合观点"),
            _stage("draft", "生成综述"),
        ),
        follow_up_prompt="请基于这次文献综述继续细化研究空白，并给出 3 个可写成 SCI 的问题陈述。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="framework_outline",
        name="框架与摘要",
        description="生成论文摘要、关键词与整体大纲",
        icon="list",
        agent="planner",
        agent_label="Planner",
        handler_key="sci.framework_outline",
        panel="editor_panel",
        color="blue",
        stages=(
            _stage("position", "定位研究"),
            _stage("outline", "生成框架"),
            _stage("abstract", "补摘要"),
        ),
        follow_up_prompt="请基于这次框架结果继续细化摘要、关键词和章节 focus，并指出下一步最适合先写哪一章。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="figure_generation",
        name="图表生成",
        description="规划和生成论文图表与示意图",
        icon="image",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="sci.figure_generation",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
        graph_module=FIGURE_GENERATION_GRAPH_MODULE,
        follow_up_prompt="请基于这次图表结果继续优化图意表达，并给出适合写入正文的说明文字。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="peer_review",
        name="同行评审",
        description="对当前稿件进行审稿式批评与修改建议输出",
        icon="shield-check",
        agent="reviewer",
        agent_label="Reviewer",
        handler_key="sci.peer_review",
        panel="analysis_panel",
        color="rose",
        stages=(
            _stage("inspect", "审阅稿件"),
            _stage("score", "评估质量"),
            _stage("advise", "生成建议"),
        ),
        follow_up_prompt="请基于这次同行评审把修改建议按优先级排序，并给出可直接落稿的改写方案。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="journal_recommend",
        name="期刊推荐",
        description="根据论文主题与摘要推荐潜在投稿期刊",
        icon="compass",
        agent="advisor",
        agent_label="Advisor",
        handler_key="sci.journal_recommend",
        panel="analysis_panel",
        color="amber",
        stages=(
            _stage("profile", "提炼论文画像"),
            _stage("match", "匹配期刊"),
            _stage("rank", "输出建议"),
        ),
        follow_up_prompt="请基于这次期刊推荐比较前 3 个候选期刊的适配度、风险和投稿策略。",
    ),
)

PROPOSAL_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="proposal_outline",
        name="申报书大纲",
        description="生成项目申报书大纲",
        icon="file-text",
        agent="writer",
        agent_label="Writer",
        handler_key="proposal.proposal_outline",
        panel="outline_editor",
        color="purple",
        stages=(
            _stage("analyze", "分析要求"),
            _stage("generate", "生成大纲"),
        ),
        follow_up_prompt="请基于这次申报书大纲继续细化研究目标、技术路线和里程碑安排。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="background_research",
        name="背景调研",
        description="调研项目背景和现状",
        icon="search",
        agent="scout",
        agent_label="Scout",
        handler_key="proposal.background_research",
        panel="literature_panel",
        color="emerald",
        stages=(
            _stage("search", "搜索资料"),
            _stage("summarize", "整理归纳"),
        ),
        follow_up_prompt="请基于这次背景调研继续收敛关键问题，并输出可直接写进申报书的现状综述。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="experiment_design",
        name="实验设计",
        description="围绕课题生成研究假设、变量设计与评估方案",
        icon="flask-conical",
        agent="designer",
        agent_label="Designer",
        handler_key="proposal.experiment_design",
        panel="outline_editor",
        color="indigo",
        stages=(
            _stage("hypothesis", "明确假设"),
            _stage("variables", "设计变量"),
            _stage("evaluation", "规划评估"),
        ),
        follow_up_prompt="请基于这次实验设计继续细化变量定义、样本方案、实验步骤和评估指标。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="figure_generation",
        name="图表生成",
        description="生成申报书中的技术路线图与流程图",
        icon="image",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="proposal.figure_generation",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
        graph_module=FIGURE_GENERATION_GRAPH_MODULE,
        follow_up_prompt="请基于这次图表结果继续优化图意表达，并给出可直接写入申报书的图注说明。",
    ),
)

SOFTWARE_COPYRIGHT_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="software_copyright",
        id="copyright_materials",
        name="材料准备",
        description="整理软件著作权登记所需材料",
        icon="file-text",
        agent="writer",
        agent_label="Writer",
        handler_key="software_copyright.copyright_materials",
        panel="outline_editor",
        color="violet",
        stages=(
            _stage("collect", "收集材料"),
            _stage("organize", "整理说明"),
            _stage("review", "核对格式"),
        ),
        follow_up_prompt="请基于这次软著材料清单继续指出还缺哪些证明材料、代码页和截图要求。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="software_copyright",
        id="technical_description",
        name="技术说明",
        description="撰写软件功能与技术实现说明",
        icon="code",
        agent="writer",
        agent_label="Writer",
        handler_key="software_copyright.technical_description",
        panel="editor_panel",
        color="indigo",
        stages=(
            _stage("analyze", "分析软件"),
            _stage("draft", "生成说明"),
            _stage("revise", "优化内容"),
        ),
        follow_up_prompt="请基于这次技术说明书继续补齐章节细节，并指出最需要补充的技术实现信息。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="software_copyright",
        id="figure_generation",
        name="图表生成",
        description="生成软著材料中的架构图、流程图与界面关系图",
        icon="image",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="software_copyright.figure_generation",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
        graph_module=FIGURE_GENERATION_GRAPH_MODULE,
        follow_up_prompt="请基于这次图表结果继续优化结构表达，并给出软著材料可用的图示说明文字。",
    ),
)

PATENT_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="patent",
        id="patent_outline",
        name="专利框架",
        description="生成专利说明书与权利要求书框架",
        icon="lightbulb",
        agent="writer",
        agent_label="Writer",
        handler_key="patent.patent_outline",
        panel="outline_editor",
        color="rose",
        stages=(
            _stage("analyze", "分析创新点"),
            _stage("structure", "生成框架"),
            _stage("refine", "完善结构"),
        ),
        follow_up_prompt="请基于这次专利框架继续收敛权利要求边界，并指出说明书还需要补哪些实施细节。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="patent",
        id="prior_art_search",
        name="现有技术检索",
        description="检索相关专利与文献，辅助新颖性分析",
        icon="search",
        agent="scout",
        agent_label="Scout",
        handler_key="patent.prior_art_search",
        panel="literature_panel",
        color="amber",
        stages=(
            _stage("search", "检索材料"),
            _stage("compare", "对比分析"),
        ),
        follow_up_prompt="请基于这次现有技术检索继续评估新颖性风险，并给出可执行的规避改写建议。",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="patent",
        id="figure_generation",
        name="图表生成",
        description="生成专利交底与说明书中的结构图、流程图和关系图",
        icon="image",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="patent.figure_generation",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
        graph_module=FIGURE_GENERATION_GRAPH_MODULE,
        follow_up_prompt="请基于这次图表结果继续优化技术方案表达，并给出专利说明书可用的图示描述。",
    ),
)

FEATURES_BY_WORKSPACE_TYPE: dict[str, tuple[WorkspaceFeatureDefinition, ...]] = {
    "thesis": THESIS_FEATURES,
    "sci": SCI_FEATURES,
    "proposal": PROPOSAL_FEATURES,
    "software_copyright": SOFTWARE_COPYRIGHT_FEATURES,
    "patent": PATENT_FEATURES,
}

FEATURES_BY_HANDLER_KEY: dict[str, WorkspaceFeatureDefinition] = {
    feature.handler_key: feature
    for feature in (
        *THESIS_FEATURES,
        *SCI_FEATURES,
        *PROPOSAL_FEATURES,
        *SOFTWARE_COPYRIGHT_FEATURES,
        *PATENT_FEATURES,
    )
}


def list_workspace_features(workspace_type: str) -> list[WorkspaceFeatureDefinition]:
    """Return features for a canonical workspace type."""
    return list(FEATURES_BY_WORKSPACE_TYPE.get(workspace_type, ()))


def get_workspace_feature(
    workspace_type: str,
    feature_id: str,
) -> WorkspaceFeatureDefinition | None:
    """Look up a feature by workspace type and feature id."""
    for feature in FEATURES_BY_WORKSPACE_TYPE.get(workspace_type, ()):
        if feature.id == feature_id:
            return feature
    return None


def get_workspace_feature_by_handler(
    handler_key: str,
) -> WorkspaceFeatureDefinition | None:
    """Look up a feature definition by handler key."""
    return FEATURES_BY_HANDLER_KEY.get(handler_key)


def iter_workspace_features() -> tuple[WorkspaceFeatureDefinition, ...]:
    """Iterate over all registered workspace features."""
    return tuple(FEATURES_BY_HANDLER_KEY.values())
