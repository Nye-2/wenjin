"""Technical Description sub-graph — LLM-powered software copyright technical description document generation.

This module implements the technical_description feature using LangGraph pattern:
- Parameter extraction and normalization
- LLM-powered section generation with template fallback
- Existing artifact loading for defaults
- Structured output with generation_mode tracking
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.academic.services import ArtifactService
from src.agents.workspace_lead_agent import register_feature_graph
from src.artifacts import ArtifactType
from src.config import get_gen_models
from src.database import get_db_session
from src.models.factory import create_chat_model

logger = logging.getLogger(__name__)

COPYRIGHT_OUTPUT_LANGUAGE = "zh"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_list(value: Any) -> list[str]:
    """Normalize params values into a non-empty string list."""
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


async def _load_copyright_materials_artifact(workspace_id: str) -> dict[str, Any] | None:
    """Load existing copyright_materials artifact to extract software profile."""
    async with get_db_session() as db:
        service = ArtifactService(db)
        artifacts = await service.list_by_workspace(
            workspace_id=workspace_id,
            artifact_type=ArtifactType.COPYRIGHT_MATERIALS.value,
            limit=1,
        )
        if artifacts:
            return _artifact_content(artifacts[0])
    except Exception:
        logger.exception("Failed to load copyright_materials artifact")
        return None


def _build_technical_description_template(
    *,
    software_name: str,
    version: str,
    core_modules: list[str],
    deployment_architecture: str,
    database_middleware: list[str],
    interface_protocols: list[str],
    highlights: list[str],
) -> dict[str, Any]:
    """Build a deterministic technical description skeleton with template content."""
    return {
        "system_overview": {
            "title": "系统概述",
            "content": (
                f"{software_name}（版本 {version}）是一款面向特定业务场景的软件系统。"
                "本系统采用现代化技术架构，支持高可用、可扩展的部署方案，"
                "能够满足用户的日常业务操作需求。"
            ),
            "source": "template",
        },
        "module_design": {
            "title": "模块设计",
            "content": _build_module_design_content(core_modules),
            "modules": core_modules or [
                "用户管理模块",
                "业务处理模块",
                "数据存储模块",
                "系统配置模块",
            ],
            "source": "template",
        },
        "data_flow": {
            "title": "数据流程",
            "content": (
                "系统采用标准的三层架构设计，数据从用户界面层输入，"
                "经过业务逻辑层处理，最终持久化到数据存储层。"
                "各层之间通过定义良好的接口进行通信，保证系统的松耦合。"
            ),
            "source": "template",
        },
        "deployment_architecture": {
            "title": "部署架构",
            "content": _build_deployment_content(deployment_architecture),
            "architecture_type": deployment_architecture or "B/S架构",
            "source": "template",
        },
        "security_and_permissions": {
            "title": "安全与权限",
            "content": (
                "系统实现了完善的用户认证与授权机制，支持基于角色的访问控制（RBAC）。"
                "敏感数据采用加密存储，通信链路支持HTTPS加密传输。"
                "系统提供完整的操作日志记录,便于安全审计。"
            ),
            "source": "template",
        },
        "operation_steps": {
            "title": "操作步骤",
            "content": _build_operation_steps_content(highlights),
            "steps": highlights or [
                "用户登录系统",
                "选择功能模块",
                "执行业务操作",
                "查看操作结果",
            ],
            "source": "template",
        },
    }


def _build_module_design_content(modules: list[str]) -> str:
    if not modules:
        modules = ["用户管理模块", "业务处理模块", "数据存储模块", "系统配置模块"]
    module_descriptions = []
    for module in modules[:6]:
        module_descriptions.append(f"- {module}：负责相关功能的数据处理与业务逻辑")
    return "系统主要包含以下核心模块：\n" + "\n".join(module_descriptions)


def _build_deployment_content(architecture: str) -> str:
    arch = architecture or "B/S架构"
    return (
        f"系统采用{arch}进行部署。"
        f"服务端部署在云服务器或本地服务器，提供统一的业务处理接口。"
        f"客户端通过浏览器或专用客户端访问系统服务。"
        f"系统支持水平扩展，可根据业务负载动态调整资源配置。"
    )


def _build_operation_steps_content(highlights: list[str]) -> str:
    if not highlights:
        highlights = ["用户登录系统", "选择功能模块", "执行业务操作", "查看操作结果"]
    steps = []
    for idx, highlight in enumerate(highlights, start= 1):
        steps.append(f"{idx}. {step}")
    return "系统主要操作流程如下：\n" + "\n".join(steps)


)


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_llm_sections(
    raw_sections: Any,
    template_sections: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize LLM-generated sections against template."""
    if not isinstance(raw_sections, dict):
        return None

    normalized: dict[str, Any] = {}
    for section_key in [
        "system_overview",
        "module_design",
        "data_flow",
        "deployment_architecture",
        "security_and_permissions",
        "operation_steps",
    ]:
        template_section = template_sections.get(section_key, {})
        content = str(raw_sections.get(section_key, {}).get("content") or "").strip()
        if content:
            normalized[section_key] = {
                "id": template_section["id"],
                "title": template_section["title"],
                "content": content,
                "source": "llm",
            }
        else:
            normalized[section_key] = {
                "id": template_section["id"],
                "title": template_section["title"],
                "content": template_section["content"],
                "source": "template",
            }

    # If LLM didn't provide meaningful content for any section, treat as invalid.
    if not any(section["source"] == "llm" for section in normalized):
        return None
    return normalized


TECHNICAL_DESCRIPTION_PROMPT = """请根据以下软件信息生成技术说明书内容，返回 JSON。

软件名称：{software_name}
版本号：{version}
核心模块：{core_modules_str}
部署架构：{deployment_architecture}
数据库/中间件：{database_middleware_str}
接口协议：{interface_protocols_str}
功能亮点：{highlights_str}
{memory_context}

你必须输出 JSON 结构：
{{
  "system_overview": {{"content": "..."}},
  "module_design": {{"content": ..., "modules": [...], "source": "llm"},
  "data_flow": {{"content": ..., "source": "llm"},
  "deployment_architecture": {{"content": ..., "architecture_type": "..."}},
  "security_and_permissions": {{"content": ...}},
  "operation_steps": {{"content": ..., "steps": [...], "source": "llm"}
}}

要求：
1. 内容应适合软件著作权登记的技术说明书
2. 使用专业、规范的技术文档语言
3. 每个章节内容不少于100字
4. 避免空泛的描述，尽量结合软件的具体特点
"""


async def _llm_generate_technical_sections(
    *,
    software_name: str,
    version: str,
    core_modules: list[str],
    deployment_architecture: str,
    database_middleware: list[str],
    interface_protocols: list[str],
    highlights: list[str],
    template_sections: dict[str, Any],
    preferred_model: str | None,
    memory_context: str | None,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt to generate technical description sections using LLM."""
    from src.config import get_gen_models
    from src.models.factory import create_chat_model

    from langchain_core.messages import HumanMessage, SystemMessage

    models = get_gen_models()
    if not models:
        return None, None, None, "no_generation_model_configured"

    model_id = preferred_model or models[0].id
    if not any(model.id == model_id for model in models):
        model_id = models[0].id
    try:
        model = create_chat_model(model_id, temperature=0.3)
    except Exception as exc:
        logger.exception("Failed to create model")
        return None, model_id, f"model_init_failed: {exc}"
    # Prepare input strings
    modules_str = "、".join(core_modules) if core_modules else "核心业务模块"
    db_str = "、".join(database_middleware) if database_middleware else "关系型数据库"
    proto_str = "、".join(interface_protocols) if interface_protocols else "HTTP/REST"
    highlights_str = "、".join(highlights[:4]) if highlights else "核心功能"
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = TECHNICAL_DESCRIPTION_PROMPT.format(
        software_name=software_name,
        version=version,
        core_modules_str=modules_str,
        deployment_architecture=deployment_architecture or "B/S架构",
        database_middleware=db_str,
        interface_protocols=proto_str,
        highlights_str=highlights_str,
        memory_context=mem_text,
    )
    try:
        response = await model.ainvoke([
            SystemMessage(content="你是一个专业的软件技术文档撰写助手，只输出 JSON 格式的内容。"),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        logger.exception("LLM generation failed")
        return None, model_id, f"llm_generation_failed: {exc}"
    parsed = _parse_json_response(content)
    if parsed is None:
        return None, model_id, "llm_output_not_json"
    sections = _normalize_llm_sections(parsed, template_sections)
    if sections is None:
        return None, model_id, "llm_sections_invalid"
    return sections, model_id, None


@register_feature_graph("technical_description", workspace_type="software_copyright")
async def technical_description_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute technical description generation with LLM-enhanced analysis.

    Pipeline: load defaults -> template sections -> LLM sections -> output
    Falls back to template mode if LLM unavailable.
    """
    params = payload.get("params", {})
    workspace_id = str(payload.get("workspace_id", ""))
    workspace_name = str(payload.get("workspace_name", ""))
    workspace_description = str(payload.get("workspace_description", ""))

    # Step 1: Extract and normalize parameters
    software_name = str(params.get("software_name") or workspace_name or "待确认软件").strip()
    version = str(params.get("version") or params.get("software_version") or "V1.0").strip()
    core_modules = _normalize_list(params.get("core_modules"))
    deployment_architecture = str(params.get("deployment_architecture") or "B/S架构").strip()
    database_middleware = _normalize_list(params.get("database_middleware"))
    interface_protocols = _normalize_list(params.get("interface_protocols"))
    highlights = _normalize_list(params.get("highlights"))
    preferred_model = params.get("model_id")
    memory_context = initial_state.get("knowledge_context")

    # Step 2: Try to load existing copyright_materials for defaults
    existing_materials = await _load_copyright_materials_artifact(workspace_id)
    if existing_materials:
        software_profile = existing_materials.get("software_profile", {})
        if not software_name or software_name == "待确认软件":
            software_name = str(software_profile.get("software_name") or workspace_name or "待确认软件")
        if not version or version == "V1.0":
            version = str(software_profile.get("version") or "V1.0")

    # Step 3: Build template sections first
    template_sections = _build_technical_description_template(
        software_name=software_name,
        version=version,
        core_modules=core_modules,
        deployment_architecture=deployment_architecture,
        database_middleware=database_middleware,
        interface_protocols=interface_protocols,
        highlights=highlights,
    )
    # Step 4: Try LLM generation
    llm_sections, model_id, generation_error = await _llm_generate_technical_sections(
        software_name=software_name,
        version=version,
        core_modules=core_modules,
        deployment_architecture=deployment_architecture,
        database_middleware=database_middleware,
        interface_protocols=interface_protocols,
        highlights=highlights,
        template_sections=template_sections,
        preferred_model=preferred_model,
        memory_context=memory_context,
    )
    # Step 5: Build final output with fallback
    if llm_sections is not None:
        sections = llm_sections
        generation_mode = "llm"
    else:
        sections = template_sections
        generation_mode = "template_fallback"
    # Step 6: Return structured output
    return {
        "schema_version": "v1",
        "output_language": COPYRIGHT_OUTPUT_LANGUAGE,
        "document_type": ArtifactType.TECHNICAL_DESCRIPTION.value,
        "workspace": {
            "id": workspace_id,
            "name": workspace_name,
            "description": workspace_description,
        },
        "software_profile": {
            "software_name": software_name,
            "version": version,
            "core_modules": core_modules,
            "deployment_architecture": deployment_architecture,
            "database_middleware": database_middleware,
            "interface_protocols": interface_protocols,
            "highlights": highlights,
        },
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": generation_error,
        "sections": sections,
        "generated_at": _utc_now_iso(),
        "upgrade": {
            "auto_upgrade": True,
            "can_regenerate_with_llm": generation_mode == "template_fallback",
            "last_error": generation_error,
        },
    }
