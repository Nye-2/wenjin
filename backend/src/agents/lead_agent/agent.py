"""Lead Agent factory for Wenjin."""

import asyncio
import logging
import time
import warnings
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from src.agents.lead_agent.blocks import AgentMessage, TextBlock
from src.agents.lead_agent.dynamic_tools import DynamicToolNode
from src.agents.lead_agent.prompts import skills as _skill_prompts
from src.agents.lead_agent.prompts import system as _system_prompts
from src.agents.lead_agent.structured_output import parse_with_fallback
from src.agents.middlewares import (
    CitationContextMiddleware,
    ClarificationMiddleware,
    DanglingToolCallMiddleware,
    DisciplineContextMiddleware,
    ExecutionMiddleware,
    KnowledgeContextMiddleware,
    LiteratureContextMiddleware,
    LLMErrorHandlingMiddleware,
    LoopDetectionMiddleware,
    MemoryMiddleware,
    SandboxAuditMiddleware,
    SandboxMiddleware,
    SummarizationMiddleware,
    ThreadDataMiddleware,
    TitleMiddleware,
    TodoListMiddleware,
    ToolErrorHandlingMiddleware,
    UploadsMiddleware,
    ViewImageMiddleware,
    WorkspaceContextMiddleware,
    resolve_summarization_settings,
)
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState, create_thread_state, merge_thread_state
from src.config import get_default_model_id
from src.config.config_loader import get_app_config
from src.models import model_supports_vision
from src.sandbox.runtime import get_sandbox_provider
from src.services.references.boundaries import is_reference_library_bypass_tool
from src.workspace_features.skills import list_workspace_thread_skills

logger = logging.getLogger(__name__)

JsonObject = dict[str, Any]

_PROMPT_CONTEXT_CHAR_LIMITS = {
    "literature_context": 3000,
    "memory_context": 1800,
    "knowledge_context": 2200,
    "template_context": 3200,
    "skill_guidance": 1400,
}


def _build_system_prompt(workspace_type: str, skill_id: str | None) -> str:
    """Build the base system prompt from the spec-driven prompt modules.

    Uses prompts.system.render for the workspace-type-aware base and
    prompts.skills.render for per-skill additional guidance (Plan 1 Tasks 4+5).
    """
    base = _system_prompts.render(workspace_type)
    skill = _skill_prompts.render(skill_id) if skill_id else ""
    return f"{base}\n\n{skill}".strip() if skill else base


def _concat_text_blocks(msg: AgentMessage) -> str:
    """Join all TextBlock.content values from an AgentMessage.

    Used to populate GeneratedThreadReply.content for legacy consumers
    that still read .content rather than .blocks.
    """
    parts = [
        block.content
        for block in msg.blocks
        if isinstance(block, TextBlock) and block.content.strip()
    ]
    return "\n\n".join(parts)


def _runtime_dict(config: RunnableConfig | None) -> JsonObject:
    """Return a mutable runtime-config mapping."""
    return dict(config) if isinstance(config, dict) else {}


def _coerce_json_object(value: object) -> JsonObject:
    """Normalize arbitrary config payloads to a JSON-like mapping."""
    return dict(value) if isinstance(value, dict) else {}


def _default_model_name() -> str:
    """Resolve the default model id used by the lead agent."""
    return get_default_model_id()


def _normalize_runtime_config(config: RunnableConfig | None) -> RunnableConfig:
    """Fill runtime defaults expected by the middleware/tool stack."""
    normalized = _runtime_dict(config)
    configurable = _coerce_json_object(normalized.get("configurable", {}))

    configurable["model_name"] = configurable.get("model_name") or _default_model_name()
    if configurable.get("supports_vision") is None:
        configurable.pop("supports_vision", None)
    configurable.setdefault("supports_vision", model_supports_vision(configurable["model_name"]))

    normalized["configurable"] = configurable
    return cast(RunnableConfig, normalized)


def _merge_runtime_config(
    base: RunnableConfig | None,
    override: RunnableConfig | None,
) -> RunnableConfig:
    """Merge a default runtime config with a request-specific override."""
    if base is None and override is None:
        return cast(RunnableConfig, {})
    if base is None:
        return cast(RunnableConfig, _runtime_dict(override))
    if override is None:
        return cast(RunnableConfig, _runtime_dict(base))

    merged = {**_runtime_dict(base), **_runtime_dict(override)}
    base_configurable = _coerce_json_object(base.get("configurable", {}))
    override_configurable = _coerce_json_object(override.get("configurable", {}))
    merged_configurable = {
        **base_configurable,
        **override_configurable,
    }
    if (
        "model_name" in override_configurable
        and "supports_vision" not in override_configurable
    ):
        merged_configurable.pop("supports_vision", None)
    elif override_configurable.get("supports_vision") is None:
        merged_configurable.pop("supports_vision", None)

    merged["configurable"] = merged_configurable
    return cast(RunnableConfig, merged)


def _render_workspace_available_skills(workspace_type: str | None) -> str:
    skills = list_workspace_thread_skills(workspace_type)
    if not skills:
        return ""
    lines = [
        "\n\n## Available Skills",
        "These skills name the workspace features the user can launch from chat.",
        "When the user asks for work that matches a skill, call the launch_feature tool directly instead of writing a proposal. Ask only for the minimum missing parameters before launching.",
    ]
    for skill in skills:
        defaults = dict(skill.defaults)
        default_text = (
            ", ".join(f"{key}={value}" for key, value in defaults.items())
            if defaults
            else "none"
        )
        follow_ups = ", ".join(skill.follow_up_skills) if skill.follow_up_skills else "none"
        lines.append(
            f"- {skill.id} -> {skill.feature_id}: {skill.description} "
            f"(defaults: {default_text}; next: {follow_ups})"
        )
    return "\n".join(lines)


def _extend_unique_tools(
    existing: list[BaseTool],
    new_tools: list[BaseTool],
) -> None:
    """Append tools while deduplicating by tool name."""
    seen_names = {
        tool.name
        for tool in existing
        if getattr(tool, "name", None)
    }

    for tool in new_tools:
        tool_name = getattr(tool, "name", None)
        if tool_name and tool_name in seen_names:
            continue
        if tool_name:
            seen_names.add(tool_name)
        existing.append(tool)


def _filter_reference_library_bypass_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """Remove direct paper-discovery tools that bypass workspace references."""
    return [
        tool
        for tool in tools
        if not is_reference_library_bypass_tool(getattr(tool, "name", ""))
    ]


_WORKSPACE_TYPE_PROMPTS: dict[str, str] = {
    "thesis": """
## 当前项目类型：学位论文

Chat 侧重点：帮助用户澄清选题、导师要求、章节逻辑、证据缺口和下一步动作；短段落修改、局部结构建议和小范围论证可以直接完成。

适合提议 Compute 的任务：深度调研、文献管理、开题/综述材料、大纲生成、全文或章节写作、图表生成。

质量边界：
- 不在 chat 中承诺完成全文、批量文献检索或图表生成；这些应通过 `launch_feature` 工具启动对应的 Compute feature。
- 论文内容必须标注待补充数据、待核验引用和 AI 辅助边界。
- 优先复用已有大纲、调研产物、文献库和上传材料，不让用户重复输入。""",

    "sci": """
## 当前项目类型：学术论文（SCI/EI）

Chat 侧重点：帮助用户快速判断 research gap、贡献表达、章节结构、实验补强和投稿策略；小范围英文改写、审稿意见解释和段落级建议可以直接完成。

适合提议 Compute 的任务：文献检索、论文分析、SCI 章节写作、文献综述、框架与摘要、图表生成、同行评审、期刊推荐。

质量边界：
- 不编造论文、引用、实验结果、影响因子、分区或审稿周期。
- 期刊推荐和文献线索必须提示"待核验"，除非已有可验证来源。
- 写作建议应优先围绕 research gap、contribution、method validity 和 experiment reproducibility。""",

    "proposal": """
## 当前项目类型：研究计划 / 基金申请

Chat 侧重点：帮助用户收敛研究目标、关键科学问题、创新性、可行性和评审风险；小范围目标改写、技术路线讨论和预算口径建议可以直接回答。

适合提议 Compute 的任务：申报书大纲、背景调研、实验设计、技术路线/流程图生成。

质量边界：
- 不把未知政策、预算标准或项目指南当作确定事实。
- 计划书内容必须区分"已具备依据"和"需要补证据/补数据"。
- 优先把用户已有方向转成 SMART 目标、可执行任务和评审可读的结构。""",

    "software_copyright": """
## 当前项目类型：软件著作权申请

Chat 侧重点：帮助用户确认软著材料口径、软件基础信息、模块命名、说明书结构和提交前核对项；简单清单、字段解释和局部文案可直接完成。

适合提议 Compute 的任务：著作权材料清单、技术说明书、架构图/流程图/模块关系图。

质量边界：
- 不替代官方审查或法律意见；申请主体、日期、代码页、截图要求需要用户最终确认。
- 技术说明必须与真实软件功能和源代码一致，不补造不存在的模块。
- 缺少软件名称、版本或核心模块时，只收集最小缺失信息。""",

    "patent": """
## 当前项目类型：专利申请

Chat 侧重点：帮助用户澄清技术方案、核心创新点、保护重点、交底材料缺口和新颖性风险；局部权利要求措辞讨论可以直接完成。

适合提议 Compute 的任务：专利框架/权利要求草案、现有技术检索、专利附图生成。

质量边界：
- 不替代专利代理师或法律意见；新颖性、创造性、公开风险和权利稳定性必须提示专业核验。
- 不编造专利号、对比文件或审查结论。
- 先收集核心技术特征和应用场景，再提议进入专利 feature。""",
}


def _truncate_prompt_block(text: str, *, max_chars: int) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    suffix = "\n...[truncated]"
    budget = max(0, max_chars - len(suffix))
    return normalized[:budget].rstrip() + suffix


def _render_template_context(template_context: dict[str, Any]) -> str:
    template_name = template_context.get("name", "自定义模板")
    lines: list[str] = ["## 写作模板规范", f"当前工作区已配置写作模板：{template_name}"]

    structure = template_context.get("structure")
    if isinstance(structure, dict):
        chapters = structure.get("chapters", [])
        if chapters:
            lines.append("")
            lines.append("### 章节结构要求")
            for ch in chapters:
                if not isinstance(ch, dict):
                    continue
                title = ch.get("title", "")
                desc = ch.get("description", "")
                wc = ch.get("suggested_word_count", "")
                required = "必需" if ch.get("required") else "可选"
                line = f"- {title} ({required})"
                if desc:
                    line += f"：{desc}"
                if wc:
                    line += f" [{wc}字]"
                lines.append(line)

    format_spec = template_context.get("format_spec")
    if isinstance(format_spec, dict):
        lines.append("")
        lines.append("### 排版格式")
        for key, value in format_spec.items():
            if value is None:
                continue
            label = key.replace("_", " ").title()
            if isinstance(value, dict):
                formatted = ", ".join(f"{k}: {v}" for k, v in value.items() if v)
                lines.append(f"- {label}: {formatted}")
            else:
                lines.append(f"- {label}: {value}")

    content_guidelines = template_context.get("content_guidelines")
    if isinstance(content_guidelines, dict):
        lines.append("")
        lines.append("### 内容要求")
        for key, value in content_guidelines.items():
            if value is None:
                continue
            label = key.replace("_", " ").title()
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        lines.append(
                            f"- {item.get('chapter', '')}: {item.get('requirement', '')}"
                        )
            else:
                lines.append(f"- {label}: {value}")

    lines.extend(
        [
            "",
            "请严格按照以上模板规范生成内容。如果用户的需求与模板规范冲突，优先询问用户。",
        ]
    )
    return "\n".join(lines)


def apply_prompt_template(
    state: ThreadState,
    config: RunnableConfig,
) -> str:
    """Apply prompt template with academic context.

    Args:
        state: Current thread state
        config: Runtime configuration

    Returns:
        System prompt string
    """
    # Base system prompt — sourced from spec-driven prompt modules (Plan 1 Tasks 4+5).
    workspace_type = state.get("workspace_type")
    discipline = state.get("discipline")
    configurable_for_skill = config.get("configurable", {})
    _skill_id_for_base = (
        configurable_for_skill.get("selected_skill")
        or state.get("current_skill")
    )
    base_prompt = _build_system_prompt(workspace_type or "", _skill_id_for_base)

    if discipline:
        discipline_label = discipline.replace("_", " ").title()
        base_prompt += f"\n学科领域：{discipline_label}"

    # Add literature context
    literature_context = state.get("literature_context", "")
    if literature_context:
        base_prompt += "\n\n" + _truncate_prompt_block(
            literature_context,
            max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["literature_context"],
        )

    # Add long-term user memory context
    memory_context = state.get("memory_context", "")
    if memory_context:
        base_prompt += "\n\n" + _truncate_prompt_block(
            memory_context,
            max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["memory_context"],
        )

    # Add knowledge context
    knowledge_context = state.get("knowledge_context", "")
    if knowledge_context:
        base_prompt += "\n\n" + _truncate_prompt_block(
            knowledge_context,
            max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["knowledge_context"],
        )

    # Add discipline norms
    discipline_norms = state.get("discipline_norms", {})
    if discipline_norms:
        base_prompt += "\n\n## Writing Guidelines"
        if "citation_style" in discipline_norms:
            base_prompt += f"\n- Citation Style: {discipline_norms['citation_style']}"
        if "writing_style" in discipline_norms:
            base_prompt += f"\n- Writing Style: {discipline_norms['writing_style']}"
        if "structure" in discipline_norms:
            base_prompt += f"\n- Paper Structure: {' → '.join(discipline_norms['structure'])}"

    # Add template context
    template_context = state.get("template_context")
    if template_context:
        template_block = _render_template_context(template_context)
        base_prompt += "\n\n" + _truncate_prompt_block(
            template_block,
            max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["template_context"],
        )

    configurable = config.get("configurable", {})
    selected_skill = (
        configurable.get("selected_skill")
        or state.get("current_skill")
    )
    if selected_skill:
        from src.workspace_features.skills import get_skill_by_id
        skill_def = get_skill_by_id(workspace_type, selected_skill)
        base_prompt += "\n\n## Preferred Skill"
        base_prompt += f"\nThe user selected `{selected_skill}` for this turn."
        if skill_def and skill_def.guidance_prompt:
            base_prompt += f"\nBound feature: `{skill_def.feature_id}`."
            base_prompt += "\n\n" + _truncate_prompt_block(
                skill_def.guidance_prompt,
                max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["skill_guidance"],
            )
            if skill_def.defaults:
                defaults = ", ".join(
                    f"{key}={value}"
                    for key, value in skill_def.defaults
                )
                base_prompt += f"\nDefault params: {defaults}."
            if skill_def.follow_up_skills:
                base_prompt += "\nLikely next skills: " + ", ".join(skill_def.follow_up_skills) + "."
            base_prompt += (
                "\nExecution policy: first identify the minimum missing inputs, "
                "then call the launch_feature tool directly to start the run "
                "(do not write a proposal and wait)."
            )
        else:
            base_prompt += "\nUse it as the default approach unless the request clearly requires a different toolchain."

    thread_id = configurable.get("thread_id")
    workspace_id = configurable.get("workspace_id")
    user_id = configurable.get("user_id")
    if workspace_id or thread_id or user_id:
        base_prompt += "\n\n## Runtime Context"
        if workspace_id:
            base_prompt += f"\n- Workspace ID: {workspace_id}"
        if thread_id:
            base_prompt += f"\n- Thread ID: {thread_id}"
        if user_id:
            base_prompt += f"\n- User ID: {user_id}"
        base_prompt += (
            "\nWorkspace tools automatically receive these ids from runtime context."
            "\nUse the launch_feature tool to start workspace features when the user's request matches a skill."
        )

    base_prompt += _render_workspace_available_skills(workspace_type)

    return base_prompt


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
    include_execution: bool = False,
    model_name: str | None = None,
) -> list[BaseTool]:
    """Get available tools based on configuration.

    Args:
        groups: Tool groups to include (None = all)
        include_mcp: Include MCP tools
        include_execution: Include execution tools that require tool middleware
        model_name: Model name for model-specific tools

    Returns:
        List of tools
    """
    tools: list[BaseTool] = []

    # Import built-in tools
    from src.tools.builtins import (
        ask_clarification_tool,
        bash_tool,
        glob_tool,
        grep_tool,
        launch_feature_tool,
        list_reference_library_tool,
        list_workspace_artifacts_tool,
        list_workspace_features_tool,
        ls_tool,
        present_files_tool,
        read_file_tool,
        read_reference_outline_node_tool,
        search_reference_text_units_tool,
        str_replace_tool,
        view_image_tool,
        write_file_tool,
    )

    # File system tools
    tools.extend([
        bash_tool,
        read_file_tool,
        write_file_tool,
        str_replace_tool,
        ls_tool,
        glob_tool,
        grep_tool,
        view_image_tool,
    ])

    # Interaction tools
    tools.append(ask_clarification_tool)
    tools.append(launch_feature_tool)
    tools.extend([
        list_workspace_features_tool,
        list_workspace_artifacts_tool,
        list_reference_library_tool,
        search_reference_text_units_tool,
        read_reference_outline_node_tool,
    ])

    # Output tools
    tools.append(present_files_tool)

    if include_execution:
        try:
            from src.tools.execution import get_execution_tools

            _extend_unique_tools(tools, get_execution_tools())
        except ImportError:
            logger.warning("Execution tools unavailable; skipping execution tool registration")
        except Exception as exc:
            logger.error("Failed to load execution tools: %s", exc)

    # Literature retrieval must stay inside Reference Library services/features.
    # Do not expose direct external search tools here; otherwise chat can cite
    # papers that never entered workspace_references / BibTeX / usage tracking.

    if include_mcp:
        try:
            from src.mcp import get_cached_mcp_tools

            _extend_unique_tools(
                tools,
                _filter_reference_library_bypass_tools(get_cached_mcp_tools()),
            )
        except ImportError:
            logger.warning("MCP integration unavailable; skipping MCP tools")
        except Exception as exc:
            logger.error("Failed to load cached MCP tools: %s", exc)

    return tools


def build_middlewares(
    workspace_service: Any | None = None,
    index_service: Any | None = None,
    artifact_service: Any | None = None,
    reference_service: Any | None = None,
) -> list[Middleware]:
    """Build middleware chain for the agent.

    Order matters! Middlewares execute in order:
    1. WorkspaceContextMiddleware - Load workspace config
    2. LiteratureContextMiddleware - Index-based TOC navigation
    3. KnowledgeContextMiddleware - Load artifacts
    4. DisciplineContextMiddleware - Load discipline norms
    5. CitationContextMiddleware - Track citations (after_model only)

    Args:
        workspace_service: Workspace service instance
        index_service: IndexService instance for literature navigation
        artifact_service: Artifact service instance
        reference_service: Reference service instance

    Returns:
        List of middleware instances
    """
    middlewares: list[Middleware] = []

    if workspace_service:
        middlewares.append(
            WorkspaceContextMiddleware(workspace_service)
        )

    if index_service:
        middlewares.append(
            LiteratureContextMiddleware(index_service)
        )

    if artifact_service:
        middlewares.append(
            KnowledgeContextMiddleware(artifact_service)
        )

    middlewares.append(DisciplineContextMiddleware())

    if reference_service:
        middlewares.append(
            CitationContextMiddleware(reference_service)
        )

    return middlewares


def validate_pipeline(pipeline: list[Middleware]) -> None:
    """Validate middleware ordering constraints.

    Raises ValueError if constraints are violated.
    """
    if not pipeline:
        return

    for i, mw in enumerate(pipeline):
        if getattr(mw, "position", None) == "first" and i != 0:
            raise ValueError(f"{type(mw).__name__} must be first in the pipeline, found at index {i}")
        if getattr(mw, "position", None) == "last" and i != len(pipeline) - 1:
            raise ValueError(f"{type(mw).__name__} must be last in the pipeline, found at index {i}")


def build_pipeline(
    config: RunnableConfig | None,
    workspace_service: Any | None = None,
    index_service: Any | None = None,
    artifact_service: Any | None = None,
    reference_service: Any | None = None,
    sandbox_provider: Any | None = None,
    memory_queue: Any | None = None,
    memory_capture_enabled: bool = True,
) -> list[Middleware]:
    """Build the middleware pipeline for the lead agent.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  SandboxMiddleware          - Infrastructure (new)
    4.  ExecutionMiddleware        - Tool execution routing (conditional)
    5.  DanglingToolCallMiddleware - Fix
    6.  SandboxAuditMiddleware     - Tool safety auditing
    7.  ToolErrorHandlingMiddleware - Tool failure degradation
    8.  LLMErrorHandlingMiddleware - LLM retry/fallback/circuit guard
    9.  SummarizationMiddleware    - Context management (conditional)
    10. MemoryMiddleware           - Context management (conditional)
    11. WorkspaceContextMiddleware - Academic (conditional)
    12. LiteratureContextMiddleware - Academic (conditional)
    13. KnowledgeContextMiddleware - Academic (conditional)
    14. DisciplineContextMiddleware - Academic
    15. TodoListMiddleware         - Interaction (conditional)
    16. ViewImageMiddleware        - Interaction
    17. LoopDetectionMiddleware    - Control (loop break)
    18. TitleMiddleware            - Post-processing
    19. CitationContextMiddleware  - Post-processing (conditional)
    20. ClarificationMiddleware    - Control (MUST BE LAST)
    """
    config = _normalize_runtime_config(config)
    configurable = _coerce_json_object(config.get("configurable", {}))
    is_plan_mode = configurable.get("is_plan_mode", False)

    # Get middleware config with error handling
    try:
        app_config: Any = get_app_config()
        mw_config: Any = app_config.middlewares
    except Exception as e:
        logger.warning(f"Failed to load app config, using defaults: {e}")
        # Create a minimal default config
        from types import SimpleNamespace
        mw_config = SimpleNamespace(
            summarization=SimpleNamespace(
                enabled=False,
                trigger="tokens:80000",
                keep="messages:10",
                model_name=None,
            ),
            llm_error_handling=SimpleNamespace(enabled=True),
        )
        app_config = SimpleNamespace(middlewares=mw_config, memory=None)

    pipeline: list[Middleware] = []

    # --- Infrastructure layer (1-3) ---
    pipeline.append(ThreadDataMiddleware())
    pipeline.append(UploadsMiddleware())

    # Sandbox (3) - resolve default provider when sandboxing is configured
    if sandbox_provider is None:
        sandbox_provider = get_sandbox_provider()

    if sandbox_provider:
        pipeline.append(SandboxMiddleware(sandbox_provider))

    # Execution (4) - compile / render tools routed through ExecutionService
    try:
        from src.thesis.execution import get_execution_service

        execution_service = get_execution_service()
    except Exception as exc:
        logger.warning("Failed to resolve execution service: %s", exc)
        execution_service = None

    if execution_service is not None:
        pipeline.append(
            ExecutionMiddleware(
                execution_service,
                reference_service=reference_service,
            )
        )

    # --- Fix layer (5) ---
    pipeline.append(DanglingToolCallMiddleware())

    # Tool safety and error degradation
    pipeline.append(SandboxAuditMiddleware())
    pipeline.append(ToolErrorHandlingMiddleware())

    # LLM resilience (retry/fallback/circuit-breaker)
    llm_mw_enabled = bool(getattr(getattr(mw_config, "llm_error_handling", None), "enabled", True))
    if llm_mw_enabled:
        circuit_breaker = getattr(app_config, "circuit_breaker", None)
        failure_threshold = getattr(circuit_breaker, "failure_threshold", 5)
        recovery_timeout_sec = getattr(circuit_breaker, "recovery_timeout_sec", 60)
        pipeline.append(
            LLMErrorHandlingMiddleware(
                circuit_failure_threshold=failure_threshold if isinstance(failure_threshold, int) else 5,
                circuit_recovery_timeout_sec=recovery_timeout_sec if isinstance(recovery_timeout_sec, int) else 60,
                load_from_app_config=False,
            )
        )

    # --- Context management layer (6-7) ---
    summarization_settings = resolve_summarization_settings(mw_config.summarization)
    if summarization_settings.enabled:
        pipeline.append(SummarizationMiddleware.from_settings(summarization_settings))

    # Memory (6) - requires queue
    memory_config = getattr(app_config, "memory", None)
    if memory_config and getattr(memory_config, "enabled", False):
        pipeline.append(
            MemoryMiddleware(
                queue=memory_queue,
                enabled=True,
                inject_enabled=getattr(memory_config, "injection_enabled", True),
                capture_enabled=memory_capture_enabled,
            )
        )

    # --- Academic context layer (8-11) ---
    if workspace_service:
        pipeline.append(
            WorkspaceContextMiddleware(workspace_service)
        )
    if index_service:
        pipeline.append(
            LiteratureContextMiddleware(index_service)
        )
    if artifact_service:
        pipeline.append(
            KnowledgeContextMiddleware(artifact_service)
        )
    pipeline.append(DisciplineContextMiddleware())

    # --- Interaction layer (12-14) ---
    # TodoList (12) - plan mode only
    if is_plan_mode:
        pipeline.append(TodoListMiddleware())

    # ViewImage (13) - always present, handles vision internally
    pipeline.append(ViewImageMiddleware())

    pipeline.append(LoopDetectionMiddleware())

    # --- Post-processing layer ---
    pipeline.append(TitleMiddleware())

    if reference_service:
        pipeline.append(
            CitationContextMiddleware(reference_service)
        )

    # --- MUST BE LAST (17) ---
    pipeline.append(ClarificationMiddleware())

    validate_pipeline(pipeline)
    return pipeline


async def middleware_before_model(
    state: ThreadState,
    config: RunnableConfig,
    middlewares: Sequence[Middleware],
) -> ThreadState:
    """Execute all middlewares before model call.

    Args:
        state: Current state
        config: Runtime config
        middlewares: List of middlewares

    Returns:
        Updated state
    """
    current_state = state
    for middleware in middlewares:
        try:
            updates = await middleware.before_model(current_state, config)
            if isinstance(updates, dict):
                # Merge updates into state (ThreadState is dict-like)
                current_state = merge_thread_state(current_state, updates)
        except Exception:
            logger.exception(
                "Middleware %s.before_model failed, skipping",
                type(middleware).__name__,
            )
    return current_state


async def middleware_after_model(
    state: ThreadState,
    config: RunnableConfig,
    middlewares: Sequence[Middleware],
) -> ThreadState:
    """Execute all middlewares after model call.

    Args:
        state: Current state
        config: Runtime config
        middlewares: List of middlewares

    Returns:
        Updated state
    """
    current_state = state
    for middleware in middlewares:
        try:
            updates = await middleware.after_model(current_state, config)
            if isinstance(updates, dict):
                current_state = merge_thread_state(current_state, updates)
        except Exception:
            logger.exception(
                "Middleware %s.after_model failed, skipping",
                type(middleware).__name__,
            )
    return current_state


def make_lead_agent(
    config: RunnableConfig,
    middlewares: Sequence[Middleware] | None = None,
    *,
    workspace_service: Any | None = None,
    index_service: Any | None = None,
    artifact_service: Any | None = None,
    reference_service: Any | None = None,
    sandbox_provider: Any | None = None,
    memory_queue: Any | None = None,
) -> "_MiddlewareWrappedAgent":
    """Factory function to create the lead agent.

    This is the entry point registered in langgraph.json.

    Args:
        config: Runtime configuration
        middlewares: Optional list of middleware instances. If not provided,
                    default pipeline will be built using build_pipeline().

    Returns:
        Compiled agent graph
    """
    # Get configuration
    config = _normalize_runtime_config(config)
    configurable = _coerce_json_object(config.get("configurable", {}))
    model_name = configurable["model_name"]
    thinking_enabled = configurable.get("thinking_enabled", False)
    reasoning_effort = configurable.get("reasoning_effort")

    from src.models.factory import create_chat_model
    base_model = create_chat_model(
        model_name,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
    )

    # Use provided middlewares or build pipeline
    if middlewares is None:
        middlewares = build_pipeline(
            config,
            workspace_service=workspace_service,
            index_service=index_service,
            artifact_service=artifact_service,
            reference_service=reference_service,
            sandbox_provider=sandbox_provider,
            memory_queue=memory_queue,
        )

    include_execution_tools = any(
        isinstance(middleware, ExecutionMiddleware)
        for middleware in (middlewares or [])
    )

    def _load_tools() -> list[BaseTool]:
        return get_available_tools(
            include_execution=include_execution_tools,
            model_name=model_name,
        )

    tool_node = DynamicToolNode(_load_tools, middlewares=middlewares)

    def _resolve_model(_state: ThreadState, _runtime: RunnableConfig) -> Any:
        current_tools = tool_node.list_available_tools()
        if not current_tools:
            return base_model
        return base_model.bind_tools(current_tools)

    # Build system prompt for the agent
    def prompt_fn(state: JsonObject) -> list[Any]:
        """Generate the full chat prompt payload for the model."""
        thread_state = create_thread_state(state)
        system_prompt = apply_prompt_template(thread_state, config)
        return [
            SystemMessage(content=system_prompt),
            *list(thread_state.get("messages", [])),
        ]

    # Create react agent
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*create_react_agent has been moved to `langchain.agents`.*",
            category=Warning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*AgentStatePydantic has been moved to `langchain.agents`.*",
            category=Warning,
        )
        agent = create_react_agent(
            cast(Any, _resolve_model),
            tool_node,
            prompt=prompt_fn,
            state_schema=ThreadState,
            checkpointer=MemorySaver(),
        )

    return _MiddlewareWrappedAgent(
        agent,
        middlewares=middlewares,
        default_config=config,
        base_model=base_model,
    )


class _MiddlewareWrappedAgent:
    """Attach the repo's middleware chain around the LangGraph agent."""

    def __init__(
        self,
        agent: Any,
        *,
        middlewares: Sequence[Middleware] | None,
        default_config: RunnableConfig,
        base_model: Any = None,
    ) -> None:
        self._agent = agent
        self._middlewares = middlewares or []
        self._default_config = default_config
        self._base_model = base_model

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        runtime_config = _normalize_runtime_config(
            _merge_runtime_config(self._default_config, config)
        )
        state = create_thread_state(input or {})
        if self._middlewares:
            state = await middleware_before_model(state, runtime_config, self._middlewares)
        if self._should_skip_model_call(state):
            return await self._apply_after_model(state, runtime_config)

        result = await self._ainvoke_with_retry(state, runtime_config, **kwargs)
        return await self._apply_after_model(result, runtime_config)

    def invoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        runtime_config = _normalize_runtime_config(
            _merge_runtime_config(self._default_config, config)
        )
        state = create_thread_state(input or {})
        if self._middlewares:
            state = asyncio.run(
                middleware_before_model(state, runtime_config, self._middlewares)
            )
        if self._should_skip_model_call(state):
            return asyncio.run(self._apply_after_model(state, runtime_config))

        result = self._invoke_with_retry(state, runtime_config, **kwargs)
        if not self._middlewares or not isinstance(result, dict):
            return result
        return asyncio.run(
            self._apply_after_model(result, runtime_config)
        )

    def astream_with_result(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> "_StreamingAgentRun":
        runtime_config = _normalize_runtime_config(
            _merge_runtime_config(self._default_config, config)
        )
        result_future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        stream_mode = kwargs.get("stream_mode")

        async def _iterator() -> Any:
            final_stream_result: dict[str, Any] | None = None
            try:
                state = create_thread_state(input or {})
                if self._middlewares:
                    state = await middleware_before_model(
                        state,
                        runtime_config,
                        self._middlewares,
                    )
                if self._should_skip_model_call(state):
                    result = await self._apply_after_model(state, runtime_config)
                    if not result_future.done():
                        result_future.set_result(result)
                    return

                async for item in self._agent.astream(
                    state,
                    config=runtime_config,
                    **kwargs,
                ):
                    final_stream_result = self._extract_stream_result(
                        stream_mode,
                        item,
                        final_stream_result,
                    )
                    yield item

                if final_stream_result is None:
                    raise RuntimeError(
                        "astream_with_result requires stream_mode to include 'values'"
                    )

                result = await self._apply_after_model(
                    final_stream_result,
                    runtime_config,
                )
                if not result_future.done():
                    result_future.set_result(result)
            except Exception as exc:
                if not result_future.done():
                    result_future.set_exception(exc)
                raise

        return _StreamingAgentRun(_iterator(), result_future)

    async def _apply_after_model(
        self,
        result: Any,
        runtime_config: RunnableConfig,
    ) -> Any:
        if not isinstance(result, dict):
            return result
        state = create_thread_state(result)
        if self._middlewares:
            state = await middleware_after_model(state, runtime_config, self._middlewares)

        # Two-step react+structured flow: create_react_agent handles tool-calling
        # (step 1), then we reparse the final message through parse_with_fallback
        # to produce AgentBlock-structured output (step 2). This is two LLM calls
        # but provides a clean seam — the ReAct graph stays untouched and the
        # structured output contract is enforced consistently.
        if self._base_model is not None and not state.get("response_blocks"):
            messages = list(state.get("messages") or [])
            if messages:
                last_msg = messages[-1]
                last_content = getattr(last_msg, "content", None)
                if isinstance(last_content, list):
                    # Multi-part content: join text pieces
                    text_parts = [
                        part.get("text", "")
                        for part in last_content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    final_text = "\n".join(text_parts).strip()
                elif isinstance(last_content, str):
                    final_text = last_content.strip()
                else:
                    final_text = ""

                if final_text:
                    configurable = _coerce_json_object(
                        runtime_config.get("configurable", {})
                    )
                    run_id = (
                        configurable.get("thread_id")
                        or configurable.get("run_id")
                        or "unknown"
                    )
                    try:
                        agent_msg: AgentMessage = await parse_with_fallback(
                            llm=self._base_model,
                            prompt=final_text,
                            run_id=str(run_id),
                        )
                        new_blocks = [
                            b.model_dump(exclude_none=True)
                            for b in agent_msg.blocks
                        ]
                        existing_blocks = list(state.get("response_blocks") or [])
                        state = merge_thread_state(
                            state, {"response_blocks": existing_blocks + new_blocks}
                        )

                        # Spec §6.2 B3 — persist result_card when the agent
                        # emits one.  Failures must not interrupt the chat flow.
                        from src.agents.lead_agent.blocks import ResultCardBlock
                        for block in agent_msg.blocks:
                            if isinstance(block, ResultCardBlock):
                                try:
                                    from src.database.session import get_db_session
                                    from src.services.workspace_run_service import (
                                        WorkspaceRunService,
                                    )
                                    async with get_db_session() as db:
                                        svc = WorkspaceRunService(db)
                                        await svc.complete_run(
                                            block.run_id,
                                            result_card=block.model_dump(
                                                exclude_none=True
                                            ),
                                            stats=block.stats.model_dump(),
                                        )
                                except Exception:
                                    logger.exception(
                                        "workspace_run.complete_run failed for run_id=%s",
                                        block.run_id,
                                    )
                    except Exception:
                        logger.exception(
                            "parse_with_fallback failed in _apply_after_model; "
                            "response_blocks will be empty for this turn"
                        )

        return state

    @staticmethod
    def _should_skip_model_call(state: ThreadState) -> bool:
        return bool(state.get("_skip_model_call"))

    def _find_llm_error_middleware(self) -> Any | None:
        for middleware in self._middlewares:
            if type(middleware).__name__ == "LLMErrorHandlingMiddleware":
                return middleware
        return None

    async def _handle_model_error(
        self,
        state: ThreadState,
        runtime_config: RunnableConfig,
        error: Exception,
    ) -> ThreadState | None:
        for middleware in self._middlewares:
            try:
                updates = await middleware.on_model_error(state, runtime_config, error)
            except Exception:
                logger.exception(
                    "Middleware %s.on_model_error failed, skipping",
                    type(middleware).__name__,
                )
                continue
            if isinstance(updates, dict):
                return merge_thread_state(state, updates)
        return None

    async def _ainvoke_with_retry(
        self,
        state: ThreadState,
        runtime_config: RunnableConfig,
        **kwargs: Any,
    ) -> Any:
        llm_middleware = self._find_llm_error_middleware()
        if llm_middleware is None:
            try:
                return await self._agent.ainvoke(state, config=runtime_config, **kwargs)
            except Exception as exc:
                handled = await self._handle_model_error(state, runtime_config, exc)
                if handled is not None:
                    return handled
                raise

        attempt = 1
        while True:
            try:
                result = await self._agent.ainvoke(state, config=runtime_config, **kwargs)
                llm_middleware.record_success()
                return result
            except Exception as exc:
                if llm_middleware.should_passthrough(exc):
                    raise

                retriable, reason = llm_middleware.classify_error(exc)
                if retriable and attempt < llm_middleware.retry_max_attempts:
                    wait_ms = llm_middleware.build_retry_delay_ms(attempt, exc)
                    llm_middleware.log_retry(attempt, wait_ms, reason, exc)
                    await asyncio.sleep(wait_ms / 1000)
                    attempt += 1
                    continue

                if retriable:
                    llm_middleware.record_failure()

                handled = await self._handle_model_error(state, runtime_config, exc)
                if handled is not None:
                    return handled
                raise

    def _invoke_with_retry(
        self,
        state: ThreadState,
        runtime_config: RunnableConfig,
        **kwargs: Any,
    ) -> Any:
        llm_middleware = self._find_llm_error_middleware()
        if llm_middleware is None:
            try:
                return self._agent.invoke(state, config=runtime_config, **kwargs)
            except Exception as exc:
                handled = asyncio.run(self._handle_model_error(state, runtime_config, exc))
                if handled is not None:
                    return handled
                raise

        attempt = 1
        while True:
            try:
                result = self._agent.invoke(state, config=runtime_config, **kwargs)
                llm_middleware.record_success()
                return result
            except Exception as exc:
                if llm_middleware.should_passthrough(exc):
                    raise

                retriable, reason = llm_middleware.classify_error(exc)
                if retriable and attempt < llm_middleware.retry_max_attempts:
                    wait_ms = llm_middleware.build_retry_delay_ms(attempt, exc)
                    llm_middleware.log_retry(attempt, wait_ms, reason, exc)
                    time.sleep(wait_ms / 1000)
                    attempt += 1
                    continue

                if retriable:
                    llm_middleware.record_failure()

                handled = asyncio.run(self._handle_model_error(state, runtime_config, exc))
                if handled is not None:
                    return handled
                raise

    @staticmethod
    def _extract_stream_result(
        stream_mode: Any,
        item: Any,
        current: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if isinstance(item, dict):
            return item

        if not isinstance(item, tuple) or len(item) != 2:
            return current

        if isinstance(stream_mode, (list, tuple, set)):
            mode, data = item
            if mode == "values" and isinstance(data, dict):
                return data
            return current

        mode = stream_mode or "values"
        if mode == "values" and isinstance(item[1], dict):
            return item[1]
        return current

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)


class _StreamingAgentRun:
    """Async iterator wrapper that exposes the final streamed result."""

    def __init__(
        self,
        iterator: Any,
        result_future: asyncio.Future[Any],
    ) -> None:
        self._iterator = iterator
        self._result_future = result_future

    def __aiter__(self) -> Any:
        return self._iterator

    async def result(self) -> Any:
        return await self._result_future
