"""Service helpers for software copyright workspace feature handlers.

This module keeps handler logic thin and reusable by encapsulating:
1. copyright-materials payload assembly,
2. technical-description payload assembly (LLM-only).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts import ArtifactType
from src.database import Artifact, get_db_session
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

COPYRIGHT_OUTPUT_LANGUAGE = "zh"


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _truncate(value: str, max_len: int = 280) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 3]}..."


def _normalize_list(value: Any) -> list[str]:
    """Normalize params values into a non-empty string list."""
    if isinstance(value, str):
        parts = [item.strip() for item in value.split(",")]
        return [item for item in parts if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _artifact_content(artifact: Artifact) -> dict[str, Any]:
    return artifact.content if isinstance(artifact.content, dict) else {}


async def _load_copyright_materials_artifact(workspace_id: str) -> dict[str, Any] | None:
    """Load existing copyright_materials artifact to extract software profile."""
    async with get_db_session() as db:
        service = ArtifactService(db)
        artifacts = await service.list_by_workspace(
            workspace_id=workspace_id,
            type=ArtifactType.COPYRIGHT_MATERIALS.value,
            limit=1,
        )
        if artifacts:
            return _artifact_content(artifacts[0])
    return None


def _build_required_materials(
    *,
    software_name: str,
    version: str,
    applicant_name: str,
    completion_date: str,
    highlights: list[str],
    target_platforms: list[str],
    source_modules: list[str],
) -> list[dict[str, Any]]:
    """Build a deterministic materials checklist artifact."""
    return [
        {
            "id": "application_form",
            "title": "软件著作权登记申请表",
            "status": "pending",
            "required_fields": [
                f"软件全称：{software_name}",
                f"版本号：{version}",
                f"申请人：{applicant_name}",
                f"开发完成日期：{completion_date}",
            ],
            "tips": [
                "名称需要与产品、原型图、说明文档保持一致。",
                "版本号建议采用 V1.0 / V1.0.0 这格式。",
            ],
        },
        {
            "id": "source_code_excerpt",
            "title": "源程序连续页",
            "status": "pending",
            "required_fields": [
                "准备前后各连续 30 页代码样本",
                "页眉标注软件名称、版本和页码",
                "每页不少于 50 行，核心逻辑优先",
            ],
            "suggested_modules": source_modules or [
                "启动入口与配置加载",
                "核心业务流程",
                "权限与数据持久化",
            ],
        },
        {
            "id": "manual_excerpt",
            "title": "软件说明书/操作手册",
            "status": "pending",
            "required_fields": [
                "包含软件简介、运行环境、主要功能、操作流程、界面截图",
                "截图需要覆盖核心页面与关键流程",
                "说明书名称应与软件全称一致",
            ],
            "recommended_sections": [
                "软件概述",
                "运行环境",
                "功能模块说明",
                "操作步骤",
                "部署与维护",
            ],
        },
        {
            "id": "identity_support",
            "title": "主体与权属证明材料",
            "status": "pending",
            "required_fields": [
                "申请人身份证明/营业执照",
                "委托代理材料（如有）",
                "合作开发协议/权属说明（如有多人或单位参与）",
            ],
            "notes": [
                "如果存在委托开发或合作开发，必须补齐权属归属说明",
                "公司申请时需统一盖章信息与申请表主体名称一致",
            ],
        },
        {
            "id": "feature_summary",
            "title": "软件功能亮点归纳",
            "status": "draft",
            "required_fields": highlights or [
                "核心业务流程",
                "权限与数据管理",
                "结果导出与报表",
            ],
            "platforms": target_platforms or ["Web", "Desktop", "Server"],
        },
    ]


def _build_review_checklist() -> list[str]:
    """Build review checklist for completeness verification."""
    return [
        "软件名称、版本号、申请人保持一致。",
        "截图、说明书标题与软件名称一致",
        "申请表和源代码中的信息必须完全填写",
        "软件功能亮点应具有原创性,不能使用空泛的功能描述",
    ]


async def build_copyright_materials_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    workspace_discipline: str,
    software_name: str,
    version: str,
    applicant_name: str,
    completion_date: str,
    highlights: list[str],
    target_platforms: list[str],
    source_modules: list[str],
) -> dict[str, Any]:
    """Build copyright-materials artifact payload without LaTeX side effects."""
    _ = workspace_id
    normalized_name = str(software_name or workspace_name or "待确认软件名称").strip() or "待确认软件名称"
    normalized_version = str(version or "V1.0").strip() or "V1.0"
    normalized_applicant = str(applicant_name or "待确认申请主体").strip() or "待确认申请主体"
    normalized_completion_date = (
        str(completion_date or "待确认开发完成日期").strip()
        or "待确认开发完成日期"
    )
    normalized_highlights = _normalize_list(highlights)
    normalized_platforms = _normalize_list(target_platforms)
    normalized_modules = _normalize_list(source_modules)

    required_materials = _build_required_materials(
        software_name=normalized_name,
        version=normalized_version,
        applicant_name=normalized_applicant,
        completion_date=normalized_completion_date,
        highlights=normalized_highlights,
        target_platforms=normalized_platforms,
        source_modules=normalized_modules,
    )
    review_checklist = _build_review_checklist()

    return {
        "schema_version": "v1",
        "output_language": COPYRIGHT_OUTPUT_LANGUAGE,
        "document_type": "copyright_materials",
        "workspace": {
            "id": workspace_id,
            "name": workspace_name,
            "type": "software_copyright",
            "discipline": workspace_discipline,
        },
        "software_profile": {
            "software_name": normalized_name,
            "version": normalized_version,
            "applicant_name": normalized_applicant,
            "completion_date": normalized_completion_date,
            "description": workspace_description,
            "highlights": normalized_highlights,
            "target_platforms": normalized_platforms,
            "source_modules": normalized_modules,
        },
        "required_materials": required_materials,
        "review_checklist": review_checklist,
        "next_actions": [
            "补齐基础信息后，先整理说明书目录与截图清单",
            "从核心模块中截取连续代码页，优先选择最能体现原创性的部分",
            "完成初稿后进行一次格式核对，再准备提交材料",
        ],
        "generated_at": _utc_now_iso(),
    }


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
                "系统提供完整的操作日志记录，便于安全审计。"
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
        "服务端部署在云服务器或本地服务器，提供统一的业务处理接口。"
        "客户端通过浏览器或专用客户端访问系统服务。"
        "系统支持水平扩展，可根据业务负载动态调整资源配置。"
    )


def _build_operation_steps_content(highlights: list[str]) -> str:
    if not highlights:
        highlights = ["用户登录系统", "选择功能模块", "执行业务操作", "查看操作结果"]
    steps = []
    for idx, step in enumerate(highlights[:6], start=1):
        steps.append(f"{idx}. {step}")
    return "系统主要操作流程如下：\n" + "\n".join(steps)


def _normalize_llm_sections(
    raw_sections: Any,
    template_sections: dict[str, Any],
) -> dict[str, Any] | None:
    """Normalize LLM response sections into the expected structure."""
    if not isinstance(raw_sections, dict):
        return None

    normalized: dict[str, Any] = {}

    section_keys = [
        "system_overview",
        "module_design",
        "data_flow",
        "deployment_architecture",
        "security_and_permissions",
        "operation_steps",
    ]

    for key in section_keys:
        template_section = template_sections.get(key, {})
        llm_section = raw_sections.get(key)

        if not isinstance(llm_section, dict):
            return None
        content = str(llm_section.get("content") or "").strip()
        if not content:
            return None
        normalized[key] = {
            "title": template_section.get("title", key),
            "content": content,
            "source": "llm",
        }
        # Preserve additional fields from template
        for field_key in ["modules", "architecture_type", "steps"]:
            if field_key in template_section:
                normalized[key][field_key] = template_section[field_key]
    return normalized


async def _try_generate_technical_sections(
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
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Attempt to generate technical description sections using LLM."""
    modules_str = "、".join(core_modules) if core_modules else "核心业务模块"
    db_str = "、".join(database_middleware) if database_middleware else "关系型数据库"
    proto_str = "、".join(interface_protocols) if interface_protocols else "HTTP/REST"
    highlights_str = "、".join(highlights[:4]) if highlights else "核心功能"

    prompt = build_json_prompt(
        instruction="请根据以下软件信息生成技术说明书内容。",
        context_sections=[
            ("软件名称", software_name),
            ("版本号", version),
            ("核心模块", modules_str),
            ("部署架构", deployment_architecture or "B/S架构"),
            ("数据库/中间件", db_str),
            ("接口协议", proto_str),
            ("功能亮点", highlights_str),
        ],
        schema='{"system_overview":{"content":"系统概述内容"},"module_design":{"content":"模块设计内容"},"data_flow":{"content":"数据流程内容"},"deployment_architecture":{"content":"部署架构内容"},"security_and_permissions":{"content":"安全与权限内容"},"operation_steps":{"content":"操作步骤内容"}}',
        requirements=[
            "内容应适合软件著作权登记的技术说明书。",
            "使用专业、规范的技术文档语言。",
            "每个章节内容不少于 100 字。",
            "避免空泛描述，尽量结合软件的具体特点。",
        ],
        output_language="zh",
    )

    parsed, model_id, generation_error = await invoke_json_chat_model(
        system_prompt="你是问津 Compute 的软件著作权技术文档专家，负责把真实软件信息转成登记材料可用的技术说明章节。",
        prompt=prompt,
        preferred_model=preferred_model,
        temperature=0.3,
    )
    if parsed is None:
        return None, model_id, generation_error

    sections = _normalize_llm_sections(parsed, template_sections)
    if sections is None:
        return None, model_id, "llm_sections_invalid"
    return sections, model_id, None


async def build_technical_description_payload(
    *,
    workspace_id: str,
    workspace_name: str,
    workspace_description: str,
    software_name: str,
    version: str,
    core_modules: list[str],
    deployment_architecture: str,
    database_middleware: list[str],
    interface_protocols: list[str],
    highlights: list[str],
    preferred_model: str | None = None,
) -> dict[str, Any]:
    """Build technical description artifact content with LLM generation.

    This function:
    1. Tries to load existing copyright_materials artifact for default values
    2. Uses template schema for section structure
    3. Requires LLM generation for section content
    4. Returns a structured payload suitable for artifact persistence
    """
    # Try to load existing copyright_materials for defaults
    existing_materials = await _load_copyright_materials_artifact(workspace_id)
    if existing_materials:
        software_profile = existing_materials.get("software_profile", {})
        if not software_name:
            software_name = str(software_profile.get("software_name") or workspace_name or "待确认软件")
        if not version:
            version = str(software_profile.get("version") or "V1.0")

    # Normalize inputs
    normalized_name = (software_name or workspace_name or "待确认软件").strip()
    normalized_version = (version or "V1.0").strip()
    normalized_modules = _normalize_list(core_modules)
    normalized_architecture = (deployment_architecture or "B/S架构").strip()
    normalized_db = _normalize_list(database_middleware)
    normalized_protocols = _normalize_list(interface_protocols)
    normalized_highlights = _normalize_list(highlights)
    runtime = get_runtime_state()

    if runtime is not None:
        upsert_runtime_block(
            runtime,
            {
                "id": "software-profile",
                "kind": "metrics",
                "title": "软件画像",
                "entries": [
                    {"label": "软件名称", "value": normalized_name},
                    {"label": "版本", "value": normalized_version},
                    {"label": "架构", "value": normalized_architecture},
                    {"label": "核心模块", "value": str(len(normalized_modules))},
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="技术画像已整理",
            description="已汇总软件名称、架构和模块信息。",
            tone="info",
        )
        await _emit_bound_runtime(
            message="正在生成技术说明书章节...",
            current_phase="write",
            stage_transition=True,
        )

    # Build template sections first
    template_sections = _build_technical_description_template(
        software_name=normalized_name,
        version=normalized_version,
        core_modules=normalized_modules,
        deployment_architecture=normalized_architecture,
        database_middleware=normalized_db,
        interface_protocols=normalized_protocols,
        highlights=normalized_highlights,
    )

    # Try LLM generation
    llm_sections, model_id, generation_error = await _try_generate_technical_sections(
        software_name=normalized_name,
        version=normalized_version,
        core_modules=normalized_modules,
        deployment_architecture=normalized_architecture,
        database_middleware=normalized_db,
        interface_protocols=normalized_protocols,
        highlights=normalized_highlights,
        template_sections=template_sections,
        preferred_model=preferred_model,
    )

    if llm_sections is None:
        if runtime is not None:
            append_runtime_activity(
                runtime,
                title="技术说明书生成失败",
                description=f"模型未返回有效章节：{generation_error or 'unknown_error'}",
                tone="error",
            )
            await _emit_bound_runtime(
                message="技术说明书生成失败，正在回传错误信息...",
                current_phase="finalize",
                stage_transition=True,
            )
        raise RuntimeError(
            f"technical_description_llm_failed: {generation_error or 'unknown_error'}"
        )

    sections = llm_sections
    generation_mode = "llm"

    if runtime is not None:
        section_values = [
            section
            for section in sections.values()
            if isinstance(section, dict)
        ]
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
                        "meta": str(section.get("source") or generation_mode),
                    }
                    for section in section_values[:8]
                ],
            },
        )
        append_runtime_activity(
            runtime,
            title="说明书章节已生成",
            description=f"已输出 {len(section_values)} 个技术说明书章节。",
            tone="success",
        )
        await _emit_bound_runtime(
            message="正在整理技术说明书产物...",
            current_phase="finalize",
            stage_transition=True,
        )

    result = {
        "schema_version": "v1",
        "output_language": COPYRIGHT_OUTPUT_LANGUAGE,
        "document_type": ArtifactType.TECHNICAL_DESCRIPTION.value,
        "workspace": {
            "id": workspace_id,
            "name": workspace_name,
            "description": workspace_description,
        },
        "software_profile": {
            "software_name": normalized_name,
            "version": normalized_version,
            "core_modules": normalized_modules,
            "deployment_architecture": normalized_architecture,
            "database_middleware": normalized_db,
            "interface_protocols": normalized_protocols,
            "highlights": normalized_highlights,
        },
        "generation_mode": generation_mode,
        "model_id": model_id,
        "generation_error": None,
        "sections": sections,
        "generated_at": _utc_now_iso(),
        "upgrade": {
            "auto_upgrade": False,
            "can_regenerate_with_llm": False,
            "last_error": None,
        },
    }
    return result
