"""Single source of truth for feature credit costs and billable task types.

All credit-related decisions (cost lookup, billability check) should import
from this module rather than maintaining local copies.
"""

from __future__ import annotations

from collections.abc import Mapping

FEATURE_COSTS: dict[str, int | dict[str, int]] = {
    "deep_research": 100,
    "literature_management": 20,
    "opening_research": 15,
    "thesis_writing": {
        "generate_outline": 20,
        "write_chapter": 60,
        "write_all": 200,
        "default": 200,
    },
    "figure_generation": 30,
    "compile_export": 10,
    "literature_search": 20,
    "paper_analysis": 25,
    "writing": 60,
    "proposal_outline": 30,
    "background_research": 20,
    "copyright_materials": 15,
    "technical_description": 30,
    "patent_outline": 40,
    "prior_art_search": 30,
}

BILLABLE_TASK_TYPES: frozenset[str] = frozenset({
    "workspace_feature",
    "deep_research",
    "thesis_generation",
    "literature_search",
})

FEATURE_DISPLAY_NAMES: dict[str, str] = {
    "deep_research": "深度调研",
    "literature_management": "文献管理",
    "opening_research": "开题调研",
    "thesis_writing": "论文写作",
    "figure_generation": "图表生成",
    "compile_export": "编译导出",
    "literature_search": "文献检索",
    "paper_analysis": "论文分析",
    "writing": "论文写作",
    "proposal_outline": "申报书大纲",
    "background_research": "背景调研",
    "copyright_materials": "材料准备",
    "technical_description": "技术说明",
    "patent_outline": "专利框架",
    "prior_art_search": "现有技术检索",
}

THESIS_ACTION_LABELS: dict[str, str] = {
    "generate_outline": "大纲生成",
    "write_chapter": "章节写作",
    "write_all": "完整写作",
}


def get_feature_cost(feature_id: str, action: str | None = None) -> int:
    """Resolve credit cost for a feature and optional action."""
    config = FEATURE_COSTS.get(feature_id, 0)
    if isinstance(config, Mapping):
        if action and action in config:
            return int(config[action])
        return int(config.get("default", 0))
    return int(config)
