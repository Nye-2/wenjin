"""Service helpers for patent workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. patent outline generation (说明书结构 + 权利要求草案),
2. prior art search payload (现有技术对比清单/新颖性风险点/规避建议).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.task.progress import get_runtime_state
from src.task.runtime_blocks import (
    append_runtime_activity,
    upsert_runtime_block,
)
from src.task.runtime_blocks import (
    emit_bound_runtime as _emit_bound_runtime,
)
from src.workspace_features.services.llm_json import (
    build_json_prompt,
    invoke_json_chat_model,
)

logger = logging.getLogger(__name__)

PATENT_OUTPUT_LANGUAGE = "zh"


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _truncate(value: str, max_len: int = 500) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _build_patent_outline_template(
    *,
    innovation_description: str,
    technical_field: str,
    application_scenario: str,
    implementation_method: str,
) -> dict[str, Any]:
    """Build supplemental guidance metadata for patent outline output."""
    _ = (innovation_description, technical_field, application_scenario, implementation_method)
    return {
        "evidence_points_needed": [
            "技术领域具体分类（IPC/CPC）",
            "背景技术中的具体对比文献",
            "发明内容中的具体技术特征",
            "实施例中的具体参数和数据",
            "附图及其详细说明",
        ],
    }


async def _try_generate_patent_outline_llm(
    *,
    innovation_description: str,
    technical_field: str,
    application_scenario: str,
    implementation_method: str,
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM generation for patent outline."""
    prompt = build_json_prompt(
        instruction="请根据以下信息生成专利说明书框架。",
        context_sections=[
            ("创新点描述", innovation_description),
            ("技术领域", technical_field or "未提供"),
            ("应用场景", application_scenario or "未提供"),
            ("预期实施方式", implementation_method or "未提供"),
        ],
        schema='{"sections":[{"id":"technical_field","title":"技术领域","content":"...","hints":["..."]}],"claims_draft":{"independent_claims":[{"id":"claim_1","type":"独立权利要求","content":"..."}],"dependent_claims":[{"id":"claim_2","type":"从属权利要求","content":"..."}],"hints":["..."]}}',
        requirements=[
            "内容专业、准确，符合专利说明书写作规范。",
            "权利要求应具有层次性，独立权利要求覆盖核心创新。",
            "避免模糊表述，尽量使用具体技术术语。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的专利撰写专家，负责把技术交底转成说明书框架和权利要求草案，并标注需要代理师核验的风险。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.3,
    )
    if parsed is None:
        return None, model_id, generation_error

    # Validate required structure
    if "sections" not in parsed or "claims_draft" not in parsed:
        return None, model_id, "llm_output_missing_required_fields"

    return parsed, model_id, None


async def build_patent_outline_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    innovation_description: str,
    technical_field: str,
    application_scenario: str,
    implementation_method: str,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build patent outline artifact content with LLM generation."""
    normalized_innovation = _normalize_text(innovation_description, workspace_description or workspace_name)
    normalized_field = _normalize_text(technical_field)
    normalized_scenario = _normalize_text(application_scenario)
    normalized_implementation = _normalize_text(implementation_method)
    runtime = get_runtime_state()

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "patent-scope",
                "kind": "metrics",
                "title": "创新输入",
                "entries": [
                    {"label": "创新点", "value": normalized_innovation},
                    {"label": "技术领域", "value": normalized_field or "未提供"},
                    {"label": "应用场景", "value": normalized_scenario or "未提供"},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="创新输入已整理",
            description="已确认创新点、技术领域和应用场景。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成说明书结构与权利要求草案...",
            current_phase="draft",
            stage_transition=True,
        )

    template_data = _build_patent_outline_template(
        innovation_description=normalized_innovation,
        technical_field=normalized_field,
        application_scenario=normalized_scenario,
        implementation_method=normalized_implementation,
    )

    llm_data, model_id, generation_error = await _try_generate_patent_outline_llm(
        innovation_description=normalized_innovation,
        technical_field=normalized_field,
        application_scenario=normalized_scenario,
        implementation_method=normalized_implementation,
        preferred_model=preferred_model,
    )

    if llm_data is None:
        if runtime is not None:
            append_runtime_activity(
                runtime,
                title="专利框架生成失败",
                description=f"模型未返回有效结构：{generation_error or 'unknown_error'}",
                tone="error",
            )
            await _emit_bound_runtime(
                message="专利框架生成失败，正在回传错误信息...",
                current_phase="finalize",
                stage_transition=True,
            )
        raise RuntimeError(
            f"patent_outline_llm_failed: {generation_error or 'unknown_error'}"
        )

    llm_sections = llm_data.get("sections")
    claims_draft = llm_data.get("claims_draft")
    if not isinstance(llm_sections, list) or not llm_sections:
        raise RuntimeError("patent_outline_llm_failed: llm_output_missing_sections")
    if not isinstance(claims_draft, dict):
        raise RuntimeError("patent_outline_llm_failed: llm_output_missing_claims")

    for section in llm_sections:
        if isinstance(section, dict):
            section["source"] = "llm"
    for claim in claims_draft.get("independent_claims", []):
        if isinstance(claim, dict):
            claim["source"] = "llm"
    for claim in claims_draft.get("dependent_claims", []):
        if isinstance(claim, dict):
            claim["source"] = "llm"

    result = {
        "schema_version": "v1",
        "output_language": PATENT_OUTPUT_LANGUAGE,
        "innovation_description": normalized_innovation,
        "technical_field": normalized_field,
        "application_scenario": normalized_scenario,
        "implementation_method": normalized_implementation,
        "generation_mode": "llm",
        "model_id": model_id,
        "generation_error": None,
        "sections": llm_sections,
        "claims_draft": claims_draft,
        "evidence_points_needed": template_data["evidence_points_needed"],
        "generated_at": _utc_now_iso(),
    }
    if runtime is not None:
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
                    for section in llm_sections[:6]
                    if isinstance(section, dict)
                ],
            },
        )
        independent_claims = claims_draft.get("independent_claims")
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
                        }
                        for index, claim in enumerate(independent_claims[:4])
                        if isinstance(claim, dict)
                    ],
                },
            )
        append_runtime_activity(
            runtime,
            title="专利框架已生成",
            description="已完成说明书结构和权利要求草案。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理专利框架产物...",
            current_phase="finalize",
            stage_transition=True,
        )
    return result


def _build_prior_art_template(
    *,
    keywords: list[str],
    ipc_codes: list[str],
    time_range: str,
) -> dict[str, Any]:
    """Build supplemental guidance metadata for prior-art output."""
    _ = (keywords, ipc_codes, time_range)
    return {
        "next_steps": [
            "补充具体检索结果到对比表",
            "针对高风险点调整权利要求书",
            "准备答复审查意见的预案",
        ],
    }


async def _try_generate_prior_art_llm(
    *,
    keywords: list[str],
    ipc_codes: list[str],
    time_range: str,
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM generation for prior art analysis."""
    keywords_str = "、".join(keywords) if keywords else "相关技术"
    ipc_str = "、".join(ipc_codes) if ipc_codes else "未指定"

    prompt = build_json_prompt(
        instruction="请根据以下检索条件生成现有技术对比分析报告。",
        context_sections=[
            ("检索关键词", keywords_str),
            ("IPC/CPC 分类", ipc_str),
            ("时间范围", time_range or "不限"),
        ],
        schema='{"search_scope":{"keywords":[],"ipc_codes":[],"time_range":"..."},"comparison_table":[{"id":"ref_1","title":"专利名称","patent_number":"...","key_features":[],"comparison":{"similarities":"...","differences":"...","novelty_assessment":"..."}}],"novelty_risks":[{"id":"risk_1","level":"high","description":"...","mitigation":"..."}],"avoidance_suggestions":[{"id":"suggestion_1","category":"...","content":"..."}]}',
        requirements=[
            "分析专业、客观，符合专利审查实务。",
            "新颖性风险分级使用 high/medium/low。",
            "comparison_table、novelty_risks、avoidance_suggestions 都要给出可执行内容。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的现有技术检索分析专家，负责基于检索条件输出对比表、新颖性风险和规避建议。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.3,
    )
    if parsed is None:
        return None, model_id, generation_error

    # Validate required structure
    required_keys = ["comparison_table", "novelty_risks", "avoidance_suggestions"]
    if not all(key in parsed for key in required_keys):
        return None, model_id, "llm_output_missing_required_fields"

    return parsed, model_id, None


async def build_prior_art_search_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    keywords: list[str],
    ipc_codes: list[str],
    time_range: str,
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build prior art search artifact content with LLM generation."""
    normalized_keywords = _normalize_list(keywords)
    if not normalized_keywords:
        normalized_keywords = [
            candidate
            for candidate in (
                _normalize_text(workspace_name),
                _normalize_text(workspace_description),
            )
            if candidate
        ][:3]
    normalized_keywords = normalized_keywords[:5]
    if not normalized_keywords:
        normalized_keywords = ["相关技术"]

    normalized_ipc = [code.upper() for code in _normalize_list(ipc_codes)][:3]
    normalized_time_range = _normalize_text(time_range, "近5年")
    runtime = get_runtime_state()

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "search-scope",
                "kind": "metrics",
                "title": "检索范围",
                "entries": [
                    {"label": "关键词", "value": "、".join(normalized_keywords)},
                    {"label": "IPC/CPC", "value": "、".join(normalized_ipc) or "未指定"},
                    {"label": "时间范围", "value": normalized_time_range},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="检索范围已确认",
            description="已整理关键词、分类号和时间范围。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在比对现有技术并识别新颖性风险...",
            current_phase="analysis",
            stage_transition=True,
        )

    template_data = _build_prior_art_template(
        keywords=normalized_keywords,
        ipc_codes=normalized_ipc,
        time_range=normalized_time_range,
    )

    llm_data, model_id, generation_error = await _try_generate_prior_art_llm(
        keywords=normalized_keywords,
        ipc_codes=normalized_ipc,
        time_range=normalized_time_range,
        preferred_model=preferred_model,
    )

    if llm_data is None:
        if runtime is not None:
            append_runtime_activity(
                runtime,
                title="现有技术检索失败",
                description=f"模型未返回有效检索结果：{generation_error or 'unknown_error'}",
                tone="error",
            )
            await _emit_bound_runtime(
                message="现有技术检索失败，正在回传错误信息...",
                current_phase="finalize",
                stage_transition=True,
            )
        raise RuntimeError(
            f"prior_art_search_llm_failed: {generation_error or 'unknown_error'}"
        )

    comparison_table = llm_data.get("comparison_table")
    novelty_risks = llm_data.get("novelty_risks")
    avoidance_suggestions = llm_data.get("avoidance_suggestions")
    if not isinstance(comparison_table, list):
        raise RuntimeError("prior_art_search_llm_failed: llm_output_missing_comparison_table")
    if not isinstance(novelty_risks, list):
        raise RuntimeError("prior_art_search_llm_failed: llm_output_missing_novelty_risks")
    if not isinstance(avoidance_suggestions, list):
        raise RuntimeError("prior_art_search_llm_failed: llm_output_missing_avoidance_suggestions")

    search_scope = llm_data.get("search_scope")
    if not isinstance(search_scope, dict):
        search_scope = {}
    search_scope["keywords"] = normalized_keywords
    search_scope["ipc_codes"] = normalized_ipc
    search_scope["time_range"] = normalized_time_range
    result = {
        "schema_version": "v1",
        "output_language": PATENT_OUTPUT_LANGUAGE,
        "keywords": normalized_keywords,
        "ipc_codes": normalized_ipc,
        "time_range": normalized_time_range,
        "generation_mode": "llm",
        "model_id": model_id,
        "generation_error": None,
        "search_scope": search_scope,
        "comparison_table": comparison_table,
        "novelty_risks": novelty_risks,
        "avoidance_suggestions": avoidance_suggestions,
        "next_steps": template_data["next_steps"],
        "generated_at": _utc_now_iso(),
    }
    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "comparison-table",
                "kind": "list",
                "title": "对比条目",
                "items": [
                    {
                        "title": str(item.get("title") or item.get("document") or "对比项"),
                        "description": str(
                            (item.get("comparison") or {}).get("novelty_assessment")
                            if isinstance(item.get("comparison"), dict)
                            else item.get("summary") or ""
                        )[:220],
                        "meta": str(item.get("patent_number") or ""),
                    }
                    for item in (comparison_table or [])[:6]
                    if isinstance(item, dict)
                ],
            },
        )
        if isinstance(novelty_risks, list):
            upsert_runtime_block(
                runtime,
                {
                    "id": "novelty-risks",
                    "kind": "list",
                    "title": "新颖性风险",
                    "items": [
                        {
                            "title": str(risk.get("description") or risk),
                            "description": str(risk.get("mitigation") or ""),
                            "meta": str(risk.get("level") or ""),
                        }
                        for risk in novelty_risks[:6]
                        if isinstance(risk, dict)
                    ],
                },
        )
        append_runtime_activity(
            runtime,
            title="检索分析完成",
            description="已生成对比条目、新颖性风险和规避建议。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理现有技术检索报告...",
            current_phase="finalize",
            stage_transition=True,
        )
    return result
