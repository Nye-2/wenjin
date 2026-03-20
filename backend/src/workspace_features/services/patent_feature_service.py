"""Service helpers for patent workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. patent outline generation (说明书结构 + 权利要求草案),
2. prior art search payload (现有技术对比清单/新颖性风险点/规避建议).

Both functions support template-first fallback when LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from src.models.factory import create_chat_model
from src.models.router import list_user_selectable_models, route_writing_model
from src.task.progress import emit_runtime_update, get_runtime_state
from src.task.runtime_blocks import (
    advance_runtime_phase,
    append_runtime_activity,
    runtime_progress_for_phase,
    upsert_runtime_block,
)

logger = logging.getLogger(__name__)

PATENT_OUTPUT_LANGUAGE = "zh"


async def _emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    runtime = get_runtime_state()
    if runtime is None:
        return
    await emit_runtime_update(
        progress_value=max(runtime_progress_for_phase(runtime), 5),
        message=message,
        current_phase=current_phase,
        runtime=runtime,
        stage_transition=stage_transition,
    )


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
    """Build patent outline template with fallback content."""
    return {
        "sections": [
            {
                "id": "technical_field",
                "title": "技术领域",
                "content": (
                    f"本发明涉及{technical_field or '相关技术领域'}"
                    f"，具体涉及{innovation_description or '一种创新技术方案'}。"
                ),
                "source": "template",
                "hints": ["明确技术领域归属", "可参考IPC/CPC分类"],
            },
            {
                "id": "background_art",
                "title": "背景技术",
                "content": (
                    "现有技术在实现过程中存在以下问题：\n"
                    "1. 效率问题：现有方案处理速度较慢，难以满足大规模应用需求。\n"
                    "2. 准确性问题：在复杂场景下，现有技术的准确率有待提升。\n"
                    "3. 成本问题：现有方案实现成本较高，不利于推广应用。\n\n"
                    "因此，需要一种新的技术方案来解决上述问题。"
                ),
                "source": "template",
                "hints": ["调研现有技术", "描述技术痛点", "引用相关专利/文献"],
            },
            {
                "id": "invention_content",
                "title": "发明内容",
                "content": (
                    f"本发明的目的是提供{innovation_description or '一种创新技术方案'}，"
                    "以解决现有技术中存在的问题。\n\n"
                    "为达到上述目的，本发明采用如下技术方案：\n"
                    "（待补充具体技术方案描述）\n\n"
                    "本发明的有益效果是：\n"
                    "1. 提高了处理效率。\n"
                    "2. 改善了准确性。\n"
                    "3. 降低了实现成本。"
                ),
                "source": "template",
                "hints": ["描述技术目的", "说明技术方案", "列举有益效果"],
            },
            {
                "id": "drawings_description",
                "title": "附图说明",
                "content": (
                    "图1是本发明实施例的整体流程示意图。\n"
                    "图2是本发明实施例的系统结构示意图。\n"
                    "图3是本发明实施例的关键模块详细示意图。\n\n"
                    "（待补充具体附图及其说明）"
                ),
                "source": "template",
                "hints": ["准备流程图", "准备结构图", "标注关键组件"],
            },
            {
                "id": "detailed_implementation",
                "title": "具体实施方式",
                "content": (
                    f"下面结合附图和具体实施例对本发明作进一步详细描述。\n\n"
                    f"【应用场景】\n{application_scenario or '本发明可应用于相关领域。'}\n\n"
                    f"【实施方式】\n{implementation_method or '待补充具体实施方式描述。'}\n\n"
                    "以上实施例仅用于说明本发明的技术方案，而非对其限制。"
                ),
                "source": "template",
                "hints": ["详细描述实施步骤", "提供具体参数", "说明变体实施例"],
            },
        ],
        "claims_draft": {
            "independent_claims": [
                {
                    "id": "claim_1",
                    "type": "独立权利要求",
                    "content": (
                        f"1. 一种{innovation_description or '技术方法'}，其特征在于，包括：\n"
                        "步骤1：[待补充]\n"
                        "步骤2：[待补充]\n"
                        "步骤3：[待补充]。"
                    ),
                    "source": "template",
                },
            ],
            "dependent_claims": [
                {
                    "id": "claim_2",
                    "type": "从属权利要求",
                    "content": (
                        "2. 根据权利要求1所述的方法，其特征在于，[待补充附加技术特征]。"
                    ),
                    "source": "template",
                },
                {
                    "id": "claim_3",
                    "type": "从属权利要求",
                    "content": (
                        "3. 根据权利要求1所述的方法，其特征在于，[待补充附加技术特征]。"
                    ),
                    "source": "template",
                },
            ],
            "hints": [
                "独立权利要求应涵盖核心创新点",
                "从属权利要求用于补充技术特征",
                "建议准备10-20条权利要求",
            ],
        },
        "evidence_points_needed": [
            "技术领域具体分类（IPC/CPC）",
            "背景技术中的具体对比文献",
            "发明内容中的具体技术特征",
            "实施例中的具体参数和数据",
            "附图及其详细说明",
        ],
    }


def _extract_response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        return "\n".join(texts).strip()
    return str(content).strip()


def _parse_json_payload(raw_text: str) -> dict[str, Any] | None:
    if not raw_text:
        return None

    candidates = [raw_text.strip()]

    code_block_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        candidates.append(code_block_match.group(1).strip())

    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
        candidates.append(raw_text[first_brace : last_brace + 1].strip())

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
    return None


async def _try_generate_patent_outline_llm(
    *,
    innovation_description: str,
    technical_field: str,
    application_scenario: str,
    implementation_method: str,
    preferred_model: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt LLM generation for patent outline."""
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    prompt = "\n".join([
        "请根据以下信息生成专利说明书框架，返回 JSON 格式。",
        f"创新点描述：{innovation_description}",
        f"技术领域：{technical_field or '待补充'}",
        f"应用场景：{application_scenario or '待补充'}",
        f"预期实施方式：{implementation_method or '待补充'}",
        "",
        "你必须输出如下结构：",
        "{",
        '  "sections": [',
        '    {"id": "technical_field", "title": "技术领域", "content": "...", "hints": ["..."]},',
        '    {"id": "background_art", "title": "背景技术", "content": "...", "hints": ["..."]},',
        '    {"id": "invention_content", "title": "发明内容", "content": "...", "hints": ["..."]},',
        '    {"id": "drawings_description", "title": "附图说明", "content": "...", "hints": ["..."]},',
        '    {"id": "detailed_implementation", "title": "具体实施方式", "content": "...", "hints": ["..."]}',
        "  ],",
        '  "claims_draft": {',
        '    "independent_claims": [{"id": "claim_1", "type": "独立权利要求", "content": "..."}],',
        '    "dependent_claims": [{"id": "claim_2", "type": "从属权利要求", "content": "..."}],',
        '    "hints": ["..."]',
        "  }",
        "}",
        "",
        "要求：",
        "1. 内容专业、准确，符合专利说明书写作规范",
        "2. 权利要求应具有层次性，独立权利要求涵盖核心创新",
        "3. 避免模糊表述，尽量使用具体技术术语",
    ])

    try:
        response = await model.ainvoke([
            SystemMessage(content="你是专业的专利撰写助手，只输出 JSON。"),
            HumanMessage(content=prompt),
        ])
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, model_id, "llm_output_not_json"

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
    """Build patent outline artifact content with LLM generation + template fallback."""
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

    if llm_data is not None:
        # Mark LLM-generated content
        for section in llm_data.get("sections", []):
            section["source"] = "llm"
        for claim in llm_data.get("claims_draft", {}).get("independent_claims", []):
            claim["source"] = "llm"
        for claim in llm_data.get("claims_draft", {}).get("dependent_claims", []):
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
            "sections": llm_data.get("sections", template_data["sections"]),
            "claims_draft": llm_data.get("claims_draft", template_data["claims_draft"]),
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
                        for section in (llm_data.get("sections") or [])[:6]
                        if isinstance(section, dict)
                    ],
                },
            )
            claims = llm_data.get("claims_draft") or {}
            independent_claims = claims.get("independent_claims") if isinstance(claims, dict) else []
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

    result = {
        "schema_version": "v1",
        "output_language": PATENT_OUTPUT_LANGUAGE,
        "innovation_description": normalized_innovation,
        "technical_field": normalized_field,
        "application_scenario": normalized_scenario,
        "implementation_method": normalized_implementation,
        "generation_mode": "template_fallback",
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": template_data["sections"],
        "claims_draft": template_data["claims_draft"],
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
                    for section in template_data["sections"][:6]
                    if isinstance(section, dict)
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="专利框架已生成",
            description="已输出模板化说明书结构和权利要求草案。",
            tone="warning",
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
    """Build prior art search template with fallback content."""
    keywords_str = "、".join(keywords) if keywords else "相关技术"

    return {
        "search_scope": {
            "keywords": keywords,
            "ipc_codes": ipc_codes,
            "time_range": time_range,
            "suggested_databases": [
                "中国专利公布公告网",
                "USPTO",
                "EPO Espacenet",
                "Google Patents",
                "CNKI/万方（学术论文）",
            ],
        },
        "comparison_table": [
            {
                "id": "ref_1",
                "title": "[待填充] 相关专利1",
                "patent_number": "CNXXXXXX",
                "applicant": "待确认",
                "publication_date": "待确认",
                "key_features": ["特征1", "特征2", "特征3"],
                "comparison": {
                    "similarities": "与本发明的相似之处：[待分析]",
                    "differences": "与本发明的区别：[待分析]",
                    "novelty_assessment": "新颖性评估：[待评估]",
                },
            },
            {
                "id": "ref_2",
                "title": "[待填充] 相关专利2",
                "patent_number": "USXXXXXX",
                "applicant": "待确认",
                "publication_date": "待确认",
                "key_features": ["特征1", "特征2"],
                "comparison": {
                    "similarities": "与本发明的相似之处：[待分析]",
                    "differences": "与本发明的区别：[待分析]",
                    "novelty_assessment": "新颖性评估：[待评估]",
                },
            },
        ],
        "novelty_risks": [
            {
                "id": "risk_1",
                "level": "medium",
                "description": f"关键词「{keywords_str}」相关领域已有较多专利布局",
                "affected_claims": ["权利要求1", "权利要求2"],
                "mitigation": "建议进一步细化技术特征，突出差异化创新点",
            },
            {
                "id": "risk_2",
                "level": "low",
                "description": "部分从属权利要求可能与现有技术重叠",
                "affected_claims": ["权利要求3-5"],
                "mitigation": "补充附加技术特征，增强从属权利要求的创造性",
            },
        ],
        "avoidance_suggestions": [
            {
                "id": "suggestion_1",
                "category": "技术特征细化",
                "content": "建议在独立权利要求中增加核心技术特征，明确与现有技术的区别",
            },
            {
                "id": "suggestion_2",
                "category": "应用场景限定",
                "content": "可考虑将权利要求限定在特定应用场景，缩小保护范围但提高授权概率",
            },
            {
                "id": "suggestion_3",
                "category": "参数优化",
                "content": "引入具体技术参数作为权利要求特征，增强技术方案的确定性",
            },
        ],
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
    models = list_user_selectable_models(purpose="writing")
    if not models:
        return None, None, "no_generation_model_configured"

    try:
        model_id = route_writing_model(requested_model=preferred_model)
    except Exception:
        model_id = models[0].id

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        return None, model_id, f"langchain_message_import_failed: {exc}"

    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        return None, model_id, f"model_init_failed: {exc}"

    keywords_str = "、".join(keywords) if keywords else "相关技术"
    ipc_str = "、".join(ipc_codes) if ipc_codes else "未指定"

    prompt = "\n".join([
        "请根据以下检索条件生成现有技术对比分析报告，返回 JSON 格式。",
        f"检索关键词：{keywords_str}",
        f"IPC/CPC分类：{ipc_str}",
        f"时间范围：{time_range or '不限'}",
        "",
        "你必须输出如下结构：",
        "{",
        '  "search_scope": {"keywords": [...], "ipc_codes": [...], "time_range": "..."},',
        '  "comparison_table": [',
        '    {"id": "ref_1", "title": "专利名称", "patent_number": "...", "key_features": [...], ',
        '     "comparison": {"similarities": "...", "differences": "...", "novelty_assessment": "..."}}',
        "  ],",
        '  "novelty_risks": [',
        '    {"id": "risk_1", "level": "high/medium/low", "description": "...", "mitigation": "..."}',
        "  ],",
        '  "avoidance_suggestions": [',
        '    {"id": "suggestion_1", "category": "...", "content": "..."}',
        "  ]",
        "}",
        "",
        "要求：",
        "1. 分析专业、客观，符合专利审查实务",
        "2. 新颖性风险分级为 high/medium/low",
        "3. 规避建议具体可执行",
    ])

    try:
        response = await model.ainvoke([
            SystemMessage(content="你是专业的专利检索分析助手，只输出 JSON。"),
            HumanMessage(content=prompt),
        ])
    except Exception as exc:
        return None, model_id, f"llm_generation_failed: {exc}"

    parsed = _parse_json_payload(_extract_response_text(response))
    if parsed is None:
        return None, model_id, "llm_output_not_json"

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
    """Build prior art search artifact content with LLM generation + template fallback."""
    normalized_keywords = keywords if keywords else [workspace_name, workspace_description][:3]
    normalized_keywords = [k for k in normalized_keywords if k][:5]  # Limit to 5 keywords
    if not normalized_keywords:
        normalized_keywords = ["相关技术"]

    normalized_ipc = [code.strip().upper() for code in ipc_codes if code.strip()][:3]
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

    if llm_data is not None:
        search_scope = llm_data.get("search_scope", template_data["search_scope"])
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
            "comparison_table": llm_data.get("comparison_table", template_data["comparison_table"]),
            "novelty_risks": llm_data.get("novelty_risks", template_data["novelty_risks"]),
            "avoidance_suggestions": llm_data.get("avoidance_suggestions", template_data["avoidance_suggestions"]),
            "next_steps": template_data["next_steps"],
            "generated_at": _utc_now_iso(),
        }
        if runtime is not None:
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
            risks = result.get("novelty_risks")
            if isinstance(risks, list):
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
                            for risk in risks[:6]
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

    result = {
        "schema_version": "v1",
        "output_language": PATENT_OUTPUT_LANGUAGE,
        "keywords": normalized_keywords,
        "ipc_codes": normalized_ipc,
        "time_range": normalized_time_range,
        "generation_mode": "template_fallback",
        "model_id": model_id,
        "generation_error": generation_error,
        "search_scope": template_data["search_scope"],
        "comparison_table": template_data["comparison_table"],
        "novelty_risks": template_data["novelty_risks"],
        "avoidance_suggestions": template_data["avoidance_suggestions"],
        "next_steps": template_data["next_steps"],
        "generated_at": _utc_now_iso(),
    }
    if runtime is not None:
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
        risks = result.get("novelty_risks")
        if isinstance(risks, list):
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
                        for risk in risks[:6]
                        if isinstance(risk, dict)
                    ],
                },
        )
        append_runtime_activity(
            runtime,
            title="检索分析完成",
            description="已生成模板化对比条目、新颖性风险和规避建议。",
            tone="warning",
        )
        await _emit_bound_runtime(
            message="正在整理现有技术检索报告...",
            current_phase="finalize",
            stage_transition=True,
        )
    return result
