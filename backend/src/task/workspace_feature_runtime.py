"""Runtime builders for workspace feature execution."""

from __future__ import annotations

from typing import Any

from src.task.runtime_blocks import (
    append_runtime_activity,
    create_feature_runtime,
    upsert_runtime_block,
)


def _list_length(value: object) -> int:
    """Return the length of a list-like payload when available."""
    return len(value) if isinstance(value, list) else 0


def _as_dict(value: object) -> dict[str, Any]:
    """Normalize mixed result payloads to a string-keyed mapping."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _build_milestone_item(value: dict[str, Any] | str) -> dict[str, str]:
    """Normalize milestone payloads that may be structured objects or plain labels."""
    if isinstance(value, dict):
        return {
            "title": str(value.get("name") or "里程碑"),
            "description": str(value.get("description") or ""),
        }
    return {"title": str(value), "description": ""}


def _linked_latex_project_id(result: dict[str, Any]) -> str | None:
    value = result.get("latex_project_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _file_changes(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("file_changes")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _leader_workflow(result: dict[str, Any]) -> dict[str, Any]:
    value = result.get("leader_workflow")
    if isinstance(value, dict):
        return value
    return {}


def _quality_issues(quality_report: dict[str, Any]) -> list[dict[str, str]]:
    value = quality_report.get("issues")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _workflow_phase_items(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    phases = workflow.get("phases")
    if not isinstance(phases, list):
        return []

    items: list[dict[str, Any]] = []
    for phase in phases[:8]:
        if not isinstance(phase, dict):
            continue
        task_items = phase.get("tasks")
        tasks = task_items if isinstance(task_items, list) else []
        success_count = sum(
            1
            for task in tasks
            if isinstance(task, dict) and bool(task.get("success"))
        )
        total_count = len(tasks)
        error_text = str(phase.get("error") or "").strip()
        status_label = "成功" if bool(phase.get("success")) else "失败"
        description = error_text or f"{success_count}/{total_count} 子任务成功"
        items.append(
            {
                "title": str(phase.get("phase") or "workflow_phase"),
                "description": description,
                "meta": status_label,
                "badge": str(total_count),
            }
        )
    return items


_RESULT_BLOCK_PHASE_HINTS: dict[str, dict[str, str]] = {
    "deep_research": {
        "research-papers": "discovery",
        "discovery-summary": "discovery",
        "research-gaps": "gap_mining",
        "research-ideas": "synthesis",
        "recommended-actions": "finalize",
    },
    "literature_search": {
        "verified-papers": "retrieve",
    },
    "paper_analysis": {
        "analysis-sections": "analyze",
    },
    "writing": {
        "draft-preview": "draft",
        "references": "draft",
    },
    "literature_review": {
        "review-sections": "synthesize",
    },
    "framework_outline": {
        "framework-outline": "outline",
    },
    "peer_review": {
        "peer-review": "review",
    },
    "journal_recommend": {
        "journal-recommendations": "match",
    },
    "opening_research": {
        "sections": "report",
    },
    "background_research": {
        "sections": "research",
    },
    "proposal_outline": {
        "outline-sections": "outline",
        "milestones": "finalize",
    },
    "experiment_design": {
        "experiment-variables": "variables",
    },
    "patent_outline": {
        "patent-sections": "draft",
        "claims": "draft",
    },
    "prior_art_search": {
        "comparison-table": "analysis",
        "novelty-risks": "analysis",
    },
    "copyright_materials": {
        "required-materials": "materials",
        "review-checklist": "finalize",
    },
    "technical_description": {
        "technical-sections": "write",
    },
    "figure_generation": {
        "figure-output": "render",
        "figure-source": "render",
    },
    "literature_management": {
        "literature-summary": "analyze",
        "top-cited": "analyze",
        "recommendations": "finalize",
    },
    "thesis_writing": {
        "outline-chapters": "outline",
        "chapter-drafts": "draft",
        "chapter-draft": "draft",
    },
}

_FINALIZE_BLOCK_IDS = {
    "linked-latex-project",
    "file-changes",
    "leader-workflow",
    "leader-workflow-phases",
    "quality-gate",
    "quality-issues",
    "result-summary",
}


def _default_finalize_phase_id(runtime: dict[str, Any]) -> str | None:
    phases = runtime.get("phases")
    if not isinstance(phases, list) or not phases:
        return None
    for phase in reversed(phases):
        if isinstance(phase, dict):
            phase_id = str(phase.get("id") or "").strip()
            if phase_id:
                return phase_id
    return None


def _annotate_runtime_block_phases(feature_id: str, runtime: dict[str, Any]) -> None:
    blocks = runtime.get("blocks")
    if not isinstance(blocks, list):
        return

    feature_hints = _RESULT_BLOCK_PHASE_HINTS.get(feature_id, {})
    finalize_phase_id = _default_finalize_phase_id(runtime)
    if not feature_hints and not finalize_phase_id:
        return

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id") or "").strip()
        if not block_id:
            continue
        if block.get("phase_id"):
            continue
        hinted_phase = feature_hints.get(block_id)
        if hinted_phase:
            block["phase_id"] = hinted_phase
            continue
        if block_id in _FINALIZE_BLOCK_IDS and finalize_phase_id:
            block["phase_id"] = finalize_phase_id


def build_feature_runtime(
    feature_id: str,
    payload: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Create the initial runtime state for a workspace feature."""
    if feature_id == "deep_research":
        focus_areas = params.get("focus_areas")
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "研究主题",
                    "value": str(
                        params.get("topic")
                        or params.get("query")
                        or payload.get("workspace_name")
                        or "未命名研究主题"
                    ),
                },
                {
                    "label": "学科",
                    "value": str(
                        params.get("discipline")
                        or payload.get("workspace_discipline")
                        or "通用学科"
                    ),
                },
                {
                    "label": "关注点",
                    "value": str(len(focus_areas) if isinstance(focus_areas, list) else 0),
                },
            ],
        )
    if feature_id == "literature_search":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "关键词",
                    "value": str(
                        params.get("query")
                        or payload.get("workspace_name")
                        or "未指定"
                    ),
                },
                {
                    "label": "学科",
                    "value": str(
                        params.get("discipline")
                        or payload.get("workspace_discipline")
                        or "未指定"
                    ),
                },
            ],
        )
    if feature_id == "paper_analysis":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "论文标题",
                    "value": str(
                        params.get("paper_title")
                        or payload.get("workspace_name")
                        or "未命名论文"
                    ),
                },
                {"label": "Reference ID", "value": str(params.get("reference_id") or "未提供")},
            ],
        )
    if feature_id == "writing":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "标题",
                    "value": str(
                        params.get("paper_title")
                        or payload.get("workspace_name")
                        or "未命名论文"
                    ),
                },
                {"label": "章节", "value": str(params.get("section_type") or "introduction")},
                {"label": "目标字数", "value": str(params.get("target_words") or 1200)},
            ],
        )
    if feature_id == "literature_review":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "主题",
                    "value": str(
                        params.get("topic")
                        or payload.get("workspace_description")
                        or payload.get("workspace_name")
                        or "研究主题"
                    ),
                },
                {
                    "label": "学科",
                    "value": str(
                        params.get("discipline")
                        or payload.get("workspace_discipline")
                        or "未指定"
                    ),
                },
                {
                    "label": "上下文 Artifact",
                    "value": str(_list_length(params.get("context_artifact_ids"))),
                },
            ],
        )
    if feature_id == "framework_outline":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "论文标题",
                    "value": str(
                        params.get("paper_title")
                        or payload.get("workspace_name")
                        or "Untitled Paper"
                    ),
                },
                {
                    "label": "研究主题",
                    "value": str(
                        params.get("topic")
                        or payload.get("workspace_description")
                        or payload.get("workspace_name")
                        or "研究主题"
                    ),
                },
                {
                    "label": "上下文 Artifact",
                    "value": str(_list_length(params.get("context_artifact_ids"))),
                },
            ],
        )
    if feature_id == "peer_review":
        manuscript_excerpt = str(params.get("manuscript_excerpt") or "")
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "论文标题",
                    "value": str(
                        params.get("paper_title")
                        or payload.get("workspace_name")
                        or "Untitled Paper"
                    ),
                },
                {"label": "稿件长度", "value": str(len(manuscript_excerpt))},
                {
                    "label": "工作区",
                    "value": str(payload.get("workspace_name") or "未命名工作区"),
                },
            ],
        )
    if feature_id == "journal_recommend":
        abstract = str(params.get("abstract") or payload.get("workspace_description") or "")
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "论文标题",
                    "value": str(
                        params.get("paper_title")
                        or payload.get("workspace_name")
                        or "Untitled Paper"
                    ),
                },
                {
                    "label": "学科",
                    "value": str(
                        params.get("discipline")
                        or payload.get("workspace_discipline")
                        or "未指定"
                    ),
                },
                {"label": "摘要长度", "value": str(len(abstract))},
            ],
        )
    if feature_id == "opening_research":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "主题",
                    "value": str(params.get("topic") or payload.get("workspace_name") or "未指定主题"),
                },
                {"label": "报告类型", "value": str(params.get("report_type") or "opening_report")},
            ],
        )
    if feature_id == "background_research":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "关键词",
                    "value": str(params.get("keywords") or payload.get("workspace_name") or "未指定主题"),
                },
                {"label": "行业范围", "value": str(params.get("industry_scope") or "相关领域")},
                {"label": "时间范围", "value": str(params.get("time_range") or "近5年")},
            ],
        )
    if feature_id == "proposal_outline":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "主题",
                    "value": str(params.get("topic") or payload.get("workspace_name") or "未命名项目"),
                },
                {"label": "类型", "value": str(params.get("proposal_type") or "other")},
                {"label": "周期", "value": str(params.get("period_months") or 24)},
            ],
        )
    if feature_id == "experiment_design":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "研究主题",
                    "value": str(
                        params.get("topic")
                        or payload.get("workspace_name")
                        or payload.get("workspace_description")
                        or "研究主题"
                    ),
                },
                {
                    "label": "研究目标",
                    "value": str(params.get("objective") or payload.get("workspace_description") or "待补充"),
                },
                {
                    "label": "工作区",
                    "value": str(payload.get("workspace_name") or "未命名工作区"),
                },
            ],
        )
    if feature_id == "patent_outline":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "创新点",
                    "value": str(
                        params.get("innovation_description")
                        or payload.get("workspace_description")
                        or "未提供"
                    ),
                },
                {"label": "技术领域", "value": str(params.get("technical_field") or "未提供")},
                {"label": "应用场景", "value": str(params.get("application_scenario") or "未提供")},
            ],
        )
    if feature_id == "prior_art_search":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "关键词",
                    "value": str(params.get("keywords") or payload.get("workspace_name") or "相关技术"),
                },
                {"label": "IPC", "value": str(params.get("ipc_codes") or "未提供")},
                {"label": "时间范围", "value": str(params.get("time_range") or "近5年")},
            ],
        )
    if feature_id == "copyright_materials":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "软件名称",
                    "value": str(
                        params.get("software_name")
                        or payload.get("workspace_name")
                        or "待确认软件"
                    ),
                },
                {"label": "版本", "value": str(params.get("version") or "V1.0")},
                {"label": "亮点", "value": str(params.get("highlights") or "未提供")},
            ],
        )
    if feature_id == "technical_description":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "软件名称",
                    "value": str(
                        params.get("software_name")
                        or payload.get("workspace_name")
                        or "待确认软件"
                    ),
                },
                {"label": "版本", "value": str(params.get("version") or "V1.0")},
                {"label": "架构", "value": str(params.get("deployment_architecture") or "B/S架构")},
            ],
        )
    if feature_id == "figure_generation":
        chapter_value = params.get("chapter_index")
        return create_feature_runtime(
            feature_id,
            [
                {"label": "图表类型", "value": str(params.get("fig_type") or "flowchart")},
                {"label": "描述", "value": str(params.get("description") or "未提供")},
                {
                    "label": "章节",
                    "value": str(chapter_value) if chapter_value is not None else "未关联",
                },
            ],
        )
    if feature_id == "literature_management":
        return create_feature_runtime(
            feature_id,
            [
                {
                    "label": "主题",
                    "value": str(params.get("topic") or payload.get("workspace_name") or "研究主题"),
                },
                {"label": "工作区", "value": str(payload.get("workspace_name") or "未命名工作区")},
            ],
        )
    if feature_id == "thesis_writing":
        thesis_action = str(params.get("action") or "").strip().lower()
        if thesis_action == "write_chapter":
            runtime_key = "thesis_writing_chapter"
            phase_label = "章节写作"
        elif thesis_action == "write_all":
            runtime_key = "thesis_writing_full"
            phase_label = "全文生成"
        else:
            runtime_key = "thesis_writing_outline"
            phase_label = "大纲生成"
        return create_feature_runtime(
            runtime_key,
            [
                {
                    "label": "论文标题",
                    "value": str(params.get("paper_title") or payload.get("workspace_name") or "未命名论文"),
                },
                {"label": "阶段", "value": phase_label},
                {"label": "目标字数", "value": str(params.get("target_words") or 20000)},
            ],
        )
    return None


def resolve_runtime_next_phase(feature_id: str, params: dict[str, Any]) -> str | None:
    """Resolve the phase that should be active right after bootstrapping."""
    if feature_id == "deep_research":
        return None
    if feature_id == "literature_search":
        return "retrieve"
    if feature_id == "paper_analysis":
        return "analyze"
    if feature_id == "writing":
        return "draft"
    if feature_id == "literature_review":
        return "synthesize"
    if feature_id == "framework_outline":
        return "outline"
    if feature_id == "peer_review":
        return "review"
    if feature_id == "journal_recommend":
        return "match"
    if feature_id == "opening_research":
        return "research_status"
    if feature_id == "background_research":
        return "scope"
    if feature_id == "proposal_outline":
        return "outline"
    if feature_id == "experiment_design":
        return None
    if feature_id == "patent_outline":
        return "draft"
    if feature_id == "prior_art_search":
        return "analysis"
    if feature_id == "copyright_materials":
        return "materials"
    if feature_id == "technical_description":
        return "write"
    if feature_id == "figure_generation":
        return "render"
    if feature_id == "literature_management":
        return "analyze"
    if feature_id == "thesis_writing":
        return "draft" if str(params.get("action") or "").strip().lower() == "write_chapter" else "outline"
    return None


def enrich_runtime_with_result(
    feature_id: str,
    runtime: dict[str, Any],
    result: dict[str, Any],
    artifacts: list[dict[str, str]],
    *,
    quality_report: dict[str, Any] | None = None,
) -> None:
    """Attach feature-specific result blocks to the runtime state."""
    append_runtime_activity(
        runtime,
        title="结果已整理",
        description=f"{feature_id} 已完成结构化输出并写入 artifact。",
        tone="success",
    )
    result_metrics = [
        {"label": "生成模式", "value": str(result.get("generation_mode") or "unknown")},
        {"label": "Artifact", "value": str(len(artifacts))},
    ]

    if feature_id == "deep_research":
        corpus = _as_dict(result.get("corpus"))
        discovery = _as_dict(result.get("discovery"))
        ideas = result.get("ideas")
        gaps = result.get("gaps")
        recommended_actions = result.get("recommended_actions")
        cross_validation = _as_dict(result.get("cross_validation"))
        verified_papers: list[Any] | None = corpus.get("verified_papers")
        if not isinstance(verified_papers, list):
            verified_papers = result.get("verified_papers") if isinstance(result.get("verified_papers"), list) else []
        result_metrics.insert(1, {"label": "已验证文献", "value": str(corpus.get("verified_count") or len(verified_papers))})
        result_metrics.insert(
            2,
            {"label": "研究空白", "value": str(len(gaps) if isinstance(gaps, list) else 0)},
        )
        result_metrics.insert(
            3,
            {"label": "研究创意", "value": str(len(ideas) if isinstance(ideas, list) else 0)},
        )
        validation_score = cross_validation.get("validation_score")
        if validation_score is not None:
            result_metrics.append({"label": "验证评分", "value": str(validation_score)})
        if isinstance(verified_papers, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "research-papers",
                    "kind": "list",
                    "title": "Semantic Scholar 已验证文献",
                    "description": "调研阶段检索并同步到参考库的可核验文献",
                    "items": [
                        {
                            "title": str(item.get("title") or "Untitled"),
                            "description": str(item.get("abstract") or item.get("significance") or "")[:220],
                            "meta": str(item.get("venue") or item.get("doi") or item.get("external_id") or ""),
                            "badge": str(item.get("year") or "") or None,
                        }
                        for item in verified_papers[:6]
                        if isinstance(item, dict)
                    ],
                },
            )
        if isinstance(gaps, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "research-gaps",
                    "kind": "list",
                    "title": "研究空白",
                    "items": [
                        {
                            "title": str(item.get("title") or item.get("description") or "研究空白"),
                            "description": str(item.get("description") or item.get("evidence") or ""),
                            "meta": str(item.get("priority") or ""),
                        }
                        for item in gaps[:6]
                        if isinstance(item, dict)
                    ],
                },
            )
        if isinstance(ideas, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "research-ideas",
                    "kind": "list",
                    "title": "研究创意",
                    "items": [
                        {
                            "title": str(item.get("title") or "研究创意"),
                            "description": str(item.get("description") or item.get("novelty_assessment") or ""),
                            "meta": str(item.get("novelty_assessment") or ""),
                        }
                        for item in ideas[:6]
                        if isinstance(item, dict)
                    ],
                },
            )
        if isinstance(recommended_actions, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "recommended-actions",
                    "kind": "list",
                    "title": "建议动作",
                    "items": [
                        {
                            "title": str(item.get("action") or "建议动作"),
                            "description": str(item.get("reason") or ""),
                        }
                        for item in recommended_actions[:5]
                        if isinstance(item, dict)
                    ],
                },
            )
        if discovery:
            upsert_runtime_block(
                runtime,
                {
                    "id": "discovery-summary",
                    "kind": "metrics",
                    "title": "发现摘要",
                    "entries": [
                        {
                            "label": "经典文献",
                            "value": str(_list_length(discovery.get("seminal_works"))),
                        },
                        {
                            "label": "近期文献",
                            "value": str(_list_length(discovery.get("recent_works"))),
                        },
                        {
                            "label": "趋势",
                            "value": str(_list_length(discovery.get("trends"))),
                        },
                    ],
                },
            )
    elif feature_id == "literature_search":
        verified_papers = result.get("verified_papers")
        unverified_leads = result.get("unverified_leads")
        result_metrics.insert(1, {"label": "已验证论文", "value": str(len(verified_papers) if isinstance(verified_papers, list) else 0)})
        result_metrics.insert(2, {"label": "未验证线索", "value": str(len(unverified_leads) if isinstance(unverified_leads, list) else 0)})
        upsert_runtime_block(
            runtime,
            {
                "id": "verified-papers",
                "kind": "list",
                "title": "Semantic Scholar 已验证论文",
                "description": "结果来自 Semantic Scholar 元数据，不包含模型生成论文。",
                "items": [
                    {
                        "title": str(item.get("title") or "Untitled"),
                        "description": str(item.get("abstract") or ""),
                        "meta": str(item.get("venue") or item.get("doi") or item.get("external_id") or ""),
                        "badge": str(item.get("year") or "") or None,
                    }
                    for item in (verified_papers or [])[:5]
                    if isinstance(item, dict)
                ],
            },
        )
    elif feature_id == "paper_analysis":
        sections = result.get("sections")
        upsert_runtime_block(
            runtime,
            {
                "id": "analysis-sections",
                "kind": "list",
                "title": "分析分区",
                "description": "方法、实验、结论与创新点",
                "items": [
                    {
                        "title": str(section.get("title") or key),
                        "description": str(section.get("content") or "")[:220],
                        "meta": (
                            f"{len(section.get('key_points', []))} 个要点"
                            if isinstance(section.get("key_points"), list)
                            else ""
                        ),
                    }
                    for key, section in (sections or {}).items()
                    if isinstance(section, dict)
                ],
            },
        )
    elif feature_id == "writing":
        upsert_runtime_block(
            runtime,
            {
                "id": "draft-preview",
                "kind": "text",
                "title": "草稿预览",
                "description": str(result.get("section_title") or result.get("section_type") or "章节草稿"),
                "content": str(result.get("content") or "")[:1200],
            },
        )
        references = result.get("references")
        if isinstance(references, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "references",
                    "kind": "list",
                    "title": "参考建议",
                    "items": [{"title": str(reference), "description": ""} for reference in references[:6]],
                },
            )
    elif feature_id == "literature_review":
        sections = result.get("sections")
        upsert_runtime_block(
            runtime,
            {
                "id": "review-sections",
                "kind": "list",
                "title": "综述章节",
                "description": "文献综述的核心结构",
                "items": [
                    {
                        "title": str(section.get("title") or "未命名章节"),
                        "description": str(section.get("content") or "")[:220],
                    }
                    for section in (sections or [])[:6]
                    if isinstance(section, dict)
                ],
            },
        )
    elif feature_id == "framework_outline":
        sections = result.get("sections")
        upsert_runtime_block(
            runtime,
            {
                "id": "framework-outline",
                "kind": "list",
                "title": "论文框架",
                "items": [
                    {
                        "title": str(section.get("title") or "Section"),
                        "description": str(section.get("focus") or "")[:180],
                    }
                    for section in (sections or [])[:8]
                    if isinstance(section, dict)
                ],
            },
        )
    elif feature_id == "peer_review":
        weaknesses = result.get("weaknesses")
        upsert_runtime_block(
            runtime,
            {
                "id": "peer-review",
                "kind": "list",
                "title": "主要问题",
                "items": [{"title": str(item), "description": ""} for item in (weaknesses or [])[:6]],
            },
        )
    elif feature_id == "journal_recommend":
        journals = result.get("journals")
        upsert_runtime_block(
            runtime,
            {
                "id": "journal-recommendations",
                "kind": "list",
                "title": "推荐期刊",
                "items": [
                    {
                        "title": str(item.get("name") or "未命名期刊"),
                        "description": str(item.get("reason") or ""),
                        "meta": str(item.get("fit") or ""),
                    }
                    for item in (journals or [])[:6]
                    if isinstance(item, dict)
                ],
            },
        )
    elif feature_id in {"opening_research", "background_research"}:
        sections = result.get("sections")
        upsert_runtime_block(
            runtime,
            {
                "id": "sections",
                "kind": "list",
                "title": "报告章节",
                "description": "已生成的结构化章节内容",
                "items": [
                    {
                        "title": str(section.get("title") or "未命名章节"),
                        "description": str(section.get("content") or "")[:220],
                        "meta": str(section.get("source") or ""),
                    }
                    for section in (sections or [])[:6]
                    if isinstance(section, dict)
                ],
            },
        )
    elif feature_id == "proposal_outline":
        sections = result.get("sections")
        upsert_runtime_block(
            runtime,
            {
                "id": "outline-sections",
                "kind": "list",
                "title": "大纲章节",
                "description": "申报书章节与摘要",
                "items": [
                    {
                        "title": str(section.get("title") or "未命名章节"),
                        "description": str(section.get("content") or "")[:220],
                        "meta": str(section.get("source") or ""),
                    }
                    for section in (sections or [])[:6]
                    if isinstance(section, dict)
                ],
            },
        )
        upsert_runtime_block(
            runtime,
            {
                "id": "milestones",
                "kind": "list",
                "title": "里程碑",
                "items": [
                    _build_milestone_item(item)
                    for item in (result.get("milestones") or [])[:5]
                    if isinstance(item, dict) or isinstance(item, str)
                ],
            },
        )
    elif feature_id == "experiment_design":
        variables = result.get("variables")
        upsert_runtime_block(
            runtime,
            {
                "id": "experiment-variables",
                "kind": "list",
                "title": "变量设计",
                "items": [
                    {
                        "title": str(item.get("name") or "未命名变量"),
                        "description": str(item.get("definition") or ""),
                        "meta": str(item.get("type") or ""),
                    }
                    for item in (variables or [])[:6]
                    if isinstance(item, dict)
                ],
            },
        )
    elif feature_id == "patent_outline":
        sections = result.get("sections")
        claims = result.get("claims_draft") or {}
        independent_claims = claims.get("independent_claims") if isinstance(claims, dict) else []
        upsert_runtime_block(
            runtime,
            {
                "id": "patent-sections",
                "kind": "list",
                "title": "说明书框架",
                "items": [
                    {
                        "title": str(section.get("title") or "未命名章节"),
                        "description": str(section.get("content") or "")[:220],
                        "meta": str(section.get("source") or ""),
                    }
                    for section in (sections or [])[:6]
                    if isinstance(section, dict)
                ],
            },
        )
        if isinstance(independent_claims, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "claims",
                    "kind": "list",
                    "title": "独立权利要求",
                    "items": [
                        {
                            "title": str(claim.get("title") or claim.get("claim") or f"权利要求 {index + 1}"),
                            "description": str(claim.get("content") or claim.get("claim") or "")[:220],
                            "meta": str(claim.get("source") or ""),
                        }
                        for index, claim in enumerate(independent_claims[:4])
                        if isinstance(claim, dict)
                    ],
                },
            )
    elif feature_id == "prior_art_search":
        comparison_table = result.get("comparison_table")
        upsert_runtime_block(
            runtime,
            {
                "id": "comparison-table",
                "kind": "list",
                "title": "对比条目",
                "items": [
                    {
                        "title": str(item.get("title") or item.get("document") or "对比项"),
                        "description": str(item.get("difference") or item.get("summary") or "")[:220],
                        "meta": str(item.get("risk_level") or ""),
                    }
                    for item in (comparison_table or [])[:6]
                    if isinstance(item, dict)
                ],
            },
        )
        novelty_risks = result.get("novelty_risks")
        if isinstance(novelty_risks, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "novelty-risks",
                    "kind": "list",
                    "title": "新颖性风险",
                    "items": [{"title": str(risk), "description": ""} for risk in novelty_risks[:6]],
                },
            )
    elif feature_id == "copyright_materials":
        required_materials = result.get("required_materials")
        review_checklist = result.get("review_checklist")
        upsert_runtime_block(
            runtime,
            {
                "id": "required-materials",
                "kind": "list",
                "title": "材料清单",
                "items": [
                    {
                        "title": str(item.get("title") or item.get("name") or "材料项"),
                        "description": str(item.get("description") or item.get("content") or "")[:220],
                        "meta": str(item.get("priority") or ""),
                    }
                    for item in (required_materials or [])[:8]
                    if isinstance(item, dict)
                ],
            },
        )
        if isinstance(review_checklist, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "review-checklist",
                    "kind": "list",
                    "title": "核对清单",
                    "items": [{"title": str(item), "description": ""} for item in review_checklist[:6]],
                },
            )
    elif feature_id == "technical_description":
        sections = result.get("sections")
        if isinstance(sections, dict):
            section_values = [
                section for section in sections.values() if isinstance(section, dict)
            ]
        elif isinstance(sections, list):
            section_values = [
                section for section in sections if isinstance(section, dict)
            ]
        else:
            section_values = []
        upsert_runtime_block(
            runtime,
            {
                "id": "technical-sections",
                "kind": "list",
                "title": "说明书章节",
                "items": [
                    {
                        "title": str(section.get("title") or "未命名章节"),
                        "description": str(section.get("content") or "")[:220],
                        "meta": str(section.get("source") or ""),
                    }
                    for section in section_values[:8]
                ],
            },
        )
    elif feature_id == "figure_generation":
        chapter_value = result.get("chapter_index")
        upsert_runtime_block(
            runtime,
            {
                "id": "figure-output",
                "kind": "metrics",
                "title": "图表输出",
                "entries": [
                    {"label": "策略", "value": str(result.get("strategy") or "unknown")},
                    {
                        "label": "格式",
                        "value": str(
                            (result.get("render_data") or {}).get("format")
                            if isinstance(result.get("render_data"), dict)
                            else "unknown"
                        ),
                    },
                    {
                        "label": "章节",
                        "value": str(chapter_value) if chapter_value is not None else "未关联",
                    },
                ],
            },
        )
        source_text = str(result.get("source_code") or result.get("prompt") or "")
        if source_text:
            upsert_runtime_block(
                runtime,
                {
                    "id": "figure-source",
                    "kind": "text",
                    "title": "图表源码/提示词",
                    "content": source_text[:1400],
                },
            )
    elif feature_id == "literature_management":
        summary = _as_dict(result.get("summary"))
        top_cited = result.get("top_cited")
        recommendations = result.get("recommended_actions") or result.get("smart_recommendations")
        upsert_runtime_block(
            runtime,
            {
                "id": "literature-summary",
                "kind": "metrics",
                "title": "文献盘点",
                "entries": [
                    {"label": "总文献", "value": str(summary.get("total") or 0)},
                    {"label": "核心文献", "value": str(summary.get("core_count") or 0)},
                    {"label": "平均引用", "value": str(summary.get("avg_citations") or 0)},
                ],
            },
        )
        if isinstance(top_cited, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "top-cited",
                    "kind": "list",
                    "title": "高引用文献",
                    "items": [
                        {
                            "title": str(item.get("title") or "Untitled"),
                            "description": "",
                            "meta": str(item.get("year") or ""),
                            "badge": str(item.get("citation_count") or item.get("citations") or ""),
                        }
                        for item in top_cited[:6]
                        if isinstance(item, dict)
                    ],
                },
            )
        if isinstance(recommendations, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "recommendations",
                    "kind": "list",
                    "title": "建议动作",
                    "items": [{"title": str(item), "description": ""} for item in recommendations[:6]],
                },
            )
    elif feature_id == "thesis_writing":
        action = str(result.get("action") or "").strip().lower()
        if action == "generate_outline":
            outline = result.get("outline") if isinstance(result.get("outline"), dict) else {}
            chapters = outline.get("chapters") if isinstance(outline, dict) else []
            if isinstance(chapters, list):
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "outline-chapters",
                        "kind": "list",
                        "title": "章节大纲",
                        "items": [
                            {
                                "title": str(chapter.get("title") or "未命名章节"),
                                "description": "、".join(str(item) for item in (chapter.get("keyPoints") or [])[:3]),
                                "meta": str(chapter.get("position") or ""),
                                "badge": str(chapter.get("targetWords") or ""),
                            }
                            for chapter in chapters[:8]
                            if isinstance(chapter, dict)
                        ],
                    },
                )
        elif action == "write_all":
            outline = result.get("outline") if isinstance(result.get("outline"), dict) else {}
            chapters = outline.get("chapters") if isinstance(outline, dict) else []
            generated_chapters = result.get("chapters")
            if isinstance(chapters, list):
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "outline-chapters",
                        "kind": "list",
                        "title": "章节大纲",
                        "items": [
                            {
                                "title": str(chapter.get("title") or "未命名章节"),
                                "description": "、".join(str(item) for item in (chapter.get("keyPoints") or [])[:3]),
                                "meta": str(chapter.get("position") or ""),
                                "badge": str(chapter.get("targetWords") or ""),
                            }
                            for chapter in chapters[:8]
                            if isinstance(chapter, dict)
                        ],
                    },
                )
            if isinstance(generated_chapters, list):
                upsert_runtime_block(
                    runtime,
                    {
                        "id": "chapter-drafts",
                        "kind": "list",
                        "title": "章节草稿",
                        "items": [
                            {
                                "title": str(chapter.get("chapter_title") or chapter.get("title") or "章节草稿"),
                                "description": str(chapter.get("markdown") or chapter.get("content") or "")[:220],
                                "meta": f"目标 {chapter.get('target_words') or chapter.get('targetWords') or 0} 字",
                            }
                            for chapter in generated_chapters[:8]
                            if isinstance(chapter, dict)
                        ],
                    },
                )
        elif action == "write_chapter":
            chapter = _as_dict(result.get("chapter"))
            content_text = str(chapter.get("markdown") or chapter.get("content") or "")
            upsert_runtime_block(
                runtime,
                {
                    "id": "chapter-draft",
                    "kind": "text",
                    "title": str(chapter.get("chapter_title") or chapter.get("title") or "章节草稿"),
                    "content": content_text[:1600],
                },
            )

    latex_project_id = _linked_latex_project_id(result)
    if latex_project_id:
        upsert_runtime_block(
            runtime,
            {
                "id": "linked-latex-project",
                "kind": "metrics",
                "title": "关联 LaTeX 项目",
                "entries": [
                    {"label": "项目 ID", "value": latex_project_id[:8]},
                    {"label": "主文件", "value": str(result.get("main_file") or "main.tex")},
                ],
            },
        )

    file_changes = _file_changes(result)
    if file_changes:
        upsert_runtime_block(
            runtime,
            {
                "id": "file-changes",
                "kind": "list",
                "title": "Prism 待确认写入",
                "description": "生成内容已进入 WenjinPrism 待确认队列，确认后才会落稿。",
                "items": [
                    {
                        "title": str(item.get("path") or item.get("logical_key") or "未命名文件"),
                        "description": str(item.get("reason") or "feature_proposal"),
                    }
                    for item in file_changes[:8]
                ],
            },
        )

    workflow = _leader_workflow(result)
    if workflow:
        strategy = str(workflow.get("strategy") or "dynamic")
        status = str(workflow.get("status") or "unknown")
        phase_count = workflow.get("phase_count")
        if phase_count is None:
            phase_count = len(workflow.get("phases") or []) if isinstance(workflow.get("phases"), list) else 0
        task_count = workflow.get("task_count")
        if task_count is None:
            phase_list = workflow.get("phases") if isinstance(workflow.get("phases"), list) else []
            task_count = sum(
                len(phase.get("tasks") or [])  # type: ignore[misc]
                for phase in phase_list
                if isinstance(phase, dict)
            )
        result_metrics.append({"label": "Workflow", "value": status})
        result_metrics.append({"label": "子任务数", "value": str(task_count)})
        upsert_runtime_block(
            runtime,
            {
                "id": "leader-workflow",
                "kind": "metrics",
                "title": "Leader 编排",
                "entries": [
                    {"label": "策略", "value": strategy},
                    {"label": "状态", "value": status},
                    {"label": "阶段", "value": str(phase_count)},
                    {"label": "子任务", "value": str(task_count)},
                ],
            },
        )
        phase_items = _workflow_phase_items(workflow)
        if phase_items:
            upsert_runtime_block(
                runtime,
                {
                    "id": "leader-workflow-phases",
                    "kind": "list",
                    "title": "Workflow 阶段",
                    "description": "feature leader 的子代理编排执行结果",
                    "items": phase_items,
                },
            )

    if isinstance(quality_report, dict):
        quality_status = str(quality_report.get("status") or "unknown")
        quality_score = quality_report.get("score")
        issues = _quality_issues(quality_report)
        warning_count = sum(
            1
            for item in issues
            if str(item.get("severity") or "").strip().lower() == "warning"
        )
        error_count = sum(
            1
            for item in issues
            if str(item.get("severity") or "").strip().lower() == "error"
        )
        result_metrics.append({"label": "质量", "value": quality_status})
        if quality_score is not None:
            result_metrics.append({"label": "质量分", "value": str(quality_score)})
        if warning_count > 0:
            result_metrics.append({"label": "质量告警", "value": str(warning_count)})
        if error_count > 0:
            result_metrics.append({"label": "质量错误", "value": str(error_count)})
        upsert_runtime_block(
            runtime,
            {
                "id": "quality-gate",
                "kind": "metrics",
                "title": "质量门禁",
                "entries": [
                    {"label": "状态", "value": quality_status},
                    {"label": "评分", "value": str(quality_score if quality_score is not None else "-")},
                    {"label": "告警", "value": str(warning_count)},
                    {"label": "错误", "value": str(error_count)},
                ],
            },
        )
        if issues:
            upsert_runtime_block(
                runtime,
                {
                    "id": "quality-issues",
                    "kind": "list",
                    "title": "质量问题",
                    "description": "输出质量检查发现的问题。",
                    "items": [
                        {
                            "title": str(item.get("code") or "quality_issue"),
                            "description": str(item.get("message") or ""),
                            "meta": str(item.get("severity") or ""),
                        }
                        for item in issues[:8]
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="质量检查完成",
            description=str(quality_report.get("summary") or "质量检查已完成。"),
            tone=(
                "danger"
                if quality_status == "fail"
                else "warning"
                if quality_status == "warn"
                else "success"
            ),
        )

    upsert_runtime_block(
        runtime,
        {
            "id": "result-summary",
            "kind": "metrics",
            "title": "输出概览",
            "entries": result_metrics,
        },
    )
    _annotate_runtime_block_phases(feature_id, runtime)
