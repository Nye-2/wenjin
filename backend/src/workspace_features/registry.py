"""Canonical workspace feature registry."""

from dataclasses import dataclass, field

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
    task_type: str = "workspace_feature"
    panel: str | None = None
    stages: tuple[FeatureStageDefinition, ...] = field(default_factory=tuple)
    color: str | None = None

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
        task_type="deep_research",
        panel="deep_research_panel",
        color="purple",
        stages=(
            _stage("search", "搜索资料"),
            _stage("analyze", "分析信息"),
            _stage("synthesize", "综合整理"),
        ),
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="literature_management",
        name="文献管理",
        description="管理和组织论文参考文献",
        icon="book",
        agent="librarian",
        agent_label="Librarian",
        handler_key="thesis.literature_management",
        task_type="workspace_feature",
        panel=None,
        stages=(),
        color="emerald",
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="opening_research",
        name="开题调研",
        description="开题报告调研与撰写辅助",
        icon="clipboard",
        agent="scout",
        agent_label="Scout",
        handler_key="thesis.opening_research",
        task_type="workspace_feature",
        panel="opening_research_panel",
        color="amber",
        stages=(
            _stage("research", "调研背景"),
            _stage("outline", "生成大纲"),
            _stage("refine", "完善内容"),
        ),
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
        task_type="workspace_feature",
        panel="thesis_editor",
        color="blue",
        stages=(
            _stage("outline", "生成大纲"),
            _stage("write", "撰写内容"),
            _stage("revise", "修订完善"),
        ),
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="figure_generation",
        name="图表生成",
        description="规划和生成论文图表",
        icon="chart",
        agent="figure_planner",
        agent_label="FigurePlanner",
        handler_key="thesis.figure_generation",
        task_type="workspace_feature",
        panel="figure_panel",
        color="rose",
        stages=(
            _stage("analyze", "分析需求"),
            _stage("design", "设计方案"),
            _stage("generate", "生成图表"),
        ),
    ),
    WorkspaceFeatureDefinition(
        workspace_type="thesis",
        id="compile_export",
        name="编译导出",
        description="编译 LaTeX 并导出 PDF",
        icon="download",
        agent="thesis_writer",
        agent_label="ThesisWriter",
        handler_key="thesis.compile_export",
        task_type="workspace_feature",
        panel="compile_panel",
        color="indigo",
        stages=(
            _stage("compile", "编译 LaTeX"),
            _stage("preview", "预览检查"),
            _stage("export", "导出文件"),
        ),
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
    ),
    WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="paper_analysis",
        name="论文分析",
        description="分析论文结构和方法",
        icon="flask",
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
    ),
)

PROPOSAL_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="proposal_outline",
        name="申报书大纲",
        description="生成项目申报书大纲",
        icon="list",
        agent="writer",
        agent_label="Writer",
        handler_key="proposal.proposal_outline",
        panel="outline_editor",
        color="purple",
        stages=(
            _stage("analyze", "分析要求"),
            _stage("generate", "生成大纲"),
        ),
    ),
    WorkspaceFeatureDefinition(
        workspace_type="proposal",
        id="background_research",
        name="背景调研",
        description="调研项目背景和现状",
        icon="book",
        agent="scout",
        agent_label="Scout",
        handler_key="proposal.background_research",
        panel="literature_panel",
        color="emerald",
        stages=(
            _stage("search", "搜索资料"),
            _stage("summarize", "整理归纳"),
        ),
    ),
)

SOFTWARE_COPYRIGHT_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="software_copyright",
        id="copyright_materials",
        name="材料准备",
        description="整理软件著作权登记所需材料",
        icon="list",
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
    ),
    WorkspaceFeatureDefinition(
        workspace_type="software_copyright",
        id="technical_description",
        name="技术说明",
        description="撰写软件功能与技术实现说明",
        icon="file",
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
    ),
)

PATENT_FEATURES = (
    WorkspaceFeatureDefinition(
        workspace_type="patent",
        id="patent_outline",
        name="专利框架",
        description="生成专利说明书与权利要求书框架",
        icon="list",
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
