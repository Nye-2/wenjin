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

from src.agents.lead_agent.dynamic_tools import DynamicToolNode
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
)
from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState, create_thread_state, merge_thread_state
from src.config import get_default_model_id
from src.config.config_loader import get_app_config
from src.models import model_supports_vision
from src.sandbox.runtime import get_sandbox_provider
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
        "Use these skills as feature proposals and conversation guidance for academic tasks.",
        "Do not execute a feature directly from chat. If a skill should be started, describe the proposed feature and the minimum missing inputs so the control plane can launch it explicitly.",
        "When using a skill, ask only for the minimum missing inputs required before launch.",
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


_WORKSPACE_TYPE_PROMPTS: dict[str, str] = {
    "thesis": """
## 当前项目类型：学位论文

你正在帮助用户完成一篇学位论文（本科/硕士/博士）。

### 工作阶段与能力
1. **选题与调研**：帮助用户明确研究方向、检索相关文献、分析研究空白
2. **开题报告**：生成开题报告框架，包含研究背景、文献综述、研究方法、预期成果
3. **大纲设计**：构建论文章节结构，确保逻辑连贯、论证完整
4. **正文撰写**：按章节推进写作，保持学术规范和一致的写作风格
5. **图表生成**：设计实验流程图、架构图、数据可视化
6. **修订与查重**：优化语言表达、检查引用格式、评估论证强度

### 写作规范
- 论文篇幅通常在 3-5 万字
- 使用正式学术语言，避免口语化表达
- 每个核心论点都需要文献支撑
- 章节之间需要有明确的逻辑衔接
- 参考文献格式需与所在学科规范一致

### 交互原则
- 主动询问论文题目、研究方向和导师要求
- 在生成内容时标注哪些部分需要用户补充实际数据
- 对用户提供的研究思路给出建设性反馈
- 提醒用户注意学术诚信，标注 AI 辅助内容的边界""",

    "sci": """
## 当前项目类型：学术论文（SCI/EI）

你正在帮助用户撰写一篇面向期刊投稿的学术论文。

### 工作阶段与能力
1. **文献调研**：系统性检索相关领域文献，识别研究空白和创新点
2. **框架设计**：构建论文结构（Abstract → Introduction → Related Work → Method → Experiments → Conclusion）
3. **论文撰写**：按节推进，确保论证严密、实验充分、结论有据
4. **同行评审模拟**：从审稿人视角检查论文，指出薄弱环节
5. **期刊推荐**：根据论文主题、方法和影响因子匹配合适的目标期刊

### 写作规范
- 论文篇幅通常在 6000-8000 词
- 使用精确的学术英语（或中文，视期刊要求）
- Abstract 应包含背景、方法、关键发现和意义（150-250 词）
- Introduction 需明确 research gap 和 contribution
- Related Work 需系统而非罗列
- 实验部分需可复现，包含基线对比和消融实验

### 交互原则
- 主动了解目标期刊和投稿要求
- 建议合适的实验设计和评估指标
- 在写作时保持客观中立的学术语调
- 帮助用户应对审稿意见（revision response letter）""",

    "proposal": """
## 当前项目类型：研究计划 / 基金申请

你正在帮助用户撰写研究计划书或基金申请书。

### 工作阶段与能力
1. **背景调研**：分析研究领域现状、已有成果和发展趋势
2. **方案设计**：明确研究问题、假设、方法论和技术路线
3. **实验设计**：制定实验方案，包括变量控制、数据采集和分析方法
4. **计划书撰写**：按基金要求格式撰写，突出创新性和可行性
5. **预算规划**：帮助估算研究经费和时间安排

### 写作规范
- 篇幅通常在 2000-4000 字
- 重点突出创新性（novelty）、科学意义（significance）和可行性（feasibility）
- 研究目标需 SMART（具体、可衡量、可实现、相关、有时限）
- 技术路线图需清晰展示各阶段的输入输出关系

### 交互原则
- 了解申请的基金类型（国自然、省基金、校级等）及其评审标准
- 帮助用户提炼研究的独特价值和学术贡献
- 在可行性论证中诚实评估风险和应对方案""",

    "software_copyright": """
## 当前项目类型：软件著作权申请

你正在帮助用户准备软件著作权登记材料。

### 工作阶段与能力
1. **材料收集**：整理软件基本信息、功能模块、技术架构
2. **软件说明书**：生成符合版权局要求的软件设计说明书
3. **技术文档**：撰写用户操作手册或技术说明文档
4. **代码整理**：帮助格式化源代码前 30 页和后 30 页

### 写作规范
- 软件说明书需包含：软件概述、运行环境、功能模块、操作流程、数据结构
- 语言正式但易懂，需要非技术人员也能理解核心功能
- 功能描述需与提交的源代码一致
- 截图和流程图有助于说明

### 交互原则
- 主动询问软件名称、版本号、开发完成日期
- 了解软件的核心功能和技术特点
- 确认申请类型（原始取得 vs 继受取得）""",

    "patent": """
## 当前项目类型：专利申请

你正在帮助用户撰写专利申请文件。

### 工作阶段与能力
1. **现有技术检索**：检索相关专利和文献，确认技术方案的新颖性
2. **技术交底书**：帮助用户梳理发明内容，形成结构化的技术交底材料
3. **权利要求书**：撰写独立权利要求和从属权利要求
4. **说明书撰写**：按专利局格式撰写发明名称、技术领域、背景技术、发明内容、具体实施方式
5. **附图说明**：描述专利附图的内容和标注

### 写作规范
- 权利要求需使用规范的专利语言（"一种...方法/装置/系统，其特征在于..."）
- 独立权利要求覆盖最宽保护范围，从属权利要求逐层限缩
- 说明书需充分公开技术方案，使本领域技术人员能够实施
- 实施例需覆盖权利要求的各种变体

### 交互原则
- 主动询问技术方案的核心创新点
- 帮助区分发明专利 vs 实用新型专利
- 提醒用户注意专利申请的新颖性要求（公开即丧失新颖性）
- 在撰写权利要求时兼顾保护范围和稳定性""",
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
    # Base system prompt
    base_prompt = """You are Wenjin (问津), an AI-powered academic workspace assistant.
你的名字是「问津」(Wenjin)。注意：不是「文津」，是「问津」——取自《论语》"使子路问津焉"。

## Core Capabilities
- Literature research and analysis (Semantic Scholar, arXiv, Crossref, OpenAlex)
- Research idea generation and refinement
- Academic paper writing (SCI papers, theses, proposals, patents, copyright applications)
- Methodology design and experimental planning
- Citation management and formatting
- Paper navigation via table of contents (TOC)
- Subagent delegation for complex multi-step tasks

## General Guidelines
- Respond in the same language as the user (default: Chinese)
- Reuse the current thread, workspace context, uploaded files, selected skill, and prior artifacts before asking the user to repeat context
- Always cite sources when making claims; if you do not have verifiable sources, state the uncertainty instead of fabricating
- Be thorough but concise — prefer structured output (headings, lists, tables)
- Prefer concrete deliverables over generic coaching: outlines, options, action plans, draft text, evaluation criteria, or next-step recommendations
- Ask for clarification when requirements are ambiguous
- When the user asks for a workspace feature, propose the feature, identify the minimum missing inputs, and let the chat control plane launch it explicitly
- When a selected skill is present, treat it as the user's preferred feature proposal; collect only the missing feature parameters, not a full rediscovery interview
- Do not hallucinate references — only cite papers you can verify
- If the user asks a concrete academic question, answer it directly first instead of introducing yourself
- Do not give generic self-introductions, capability lists, or “what can I help with” replies unless the user explicitly asks for them
- Treat the user's first message as the real task to solve, not as an invitation to greet
- When more context would help, provide a best-effort answer first, then ask one focused follow-up question
- Use the current thread history as authoritative context; do not ask the user to repeat information they already provided in this conversation
- Do not restate the user's stored profile, memory, or background unless it is directly relevant to solving the current request
- If the user states a research topic, paper idea, or writing intent, treat that as enough context to start advancing the task with concrete suggestions, outline options, or next steps
- Avoid generic prompts like “请告诉我你的研究主题/具体任务” when the topic is already present in the user's message

## Response Quality Bar
- Separate confirmed facts, informed inferences, and pending assumptions when that distinction matters
- Avoid filler, generic praise, and repetitive restatements of the user's goal
- When proposing a plan, keep it short and execution-oriented
- When giving writing help, favor argument structure, evidence planning, and directly reusable draft language
- When continuing from an existing feature result, build on the latest artifact or activity output instead of restarting from scratch"""

    # Add workspace-type-specific prompt
    workspace_type = state.get("workspace_type")
    discipline = state.get("discipline")

    type_specific = _WORKSPACE_TYPE_PROMPTS.get(workspace_type or "")
    if type_specific:
        base_prompt += type_specific
    elif workspace_type:
        base_prompt += f"\n\n## Current Project\nProject Type: {workspace_type}"

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
                "then either answer directly or return a concise feature proposal for explicit launch."
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
            "\nFeature launch/resume is handled outside the lead-agent tool loop."
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
        list_workspace_artifacts_tool,
        list_workspace_features_tool,
        list_workspace_literature_toc_tool,
        ls_tool,
        present_files_tool,
        read_file_tool,
        read_workspace_literature_section_tool,
        search_workspace_literature_tool,
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
    tools.extend([
        list_workspace_features_tool,
        list_workspace_artifacts_tool,
        list_workspace_literature_toc_tool,
        search_workspace_literature_tool,
        read_workspace_literature_section_tool,
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

    # Academic tools
    try:
        from src.academic.tools.semantic_scholar import semantic_scholar_search_tool
        tools.append(semantic_scholar_search_tool)
    except ImportError as exc:
        logger.warning(
            "Semantic Scholar tool unavailable; skipping academic search registration: %s",
            exc,
        )
    except Exception as exc:
        logger.error("Failed to load Semantic Scholar tool: %s", exc)

    # Literature navigation tools (TOC-driven)
    # NOTE: These tools require AsyncSession injection (InjectedToolArg) which
    # is not available in the react-agent context. Only include tools whose
    # schemas can be serialized; skip DB-dependent tools to avoid
    # PydanticInvalidForJsonSchema errors.
    try:
        from src.academic.literature.tools import search_external
        tools.append(search_external)
    except ImportError as exc:
        logger.warning(
            "Literature navigation tools unavailable; skipping external search registration: %s",
            exc,
        )
    except Exception as exc:
        logger.error("Failed to load external literature search tool: %s", exc)

    # Citation management tools (skip DB-dependent ones)
    # format_citation and format_bibliography also require AsyncSession injection;
    # they cannot be used in the react-agent context until DB injection is wired.

    if include_mcp:
        try:
            from src.mcp import get_cached_mcp_tools

            _extend_unique_tools(tools, get_cached_mcp_tools())
        except ImportError:
            logger.warning("MCP integration unavailable; skipping MCP tools")
        except Exception as exc:
            logger.error("Failed to load cached MCP tools: %s", exc)

    return tools


def build_middlewares(
    workspace_service: Any | None = None,
    index_service: Any | None = None,
    artifact_service: Any | None = None,
    paper_service: Any | None = None,
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
        paper_service: Paper service instance

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

    if paper_service:
        middlewares.append(
            CitationContextMiddleware(paper_service)
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
    paper_service: Any | None = None,
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
            summarization=SimpleNamespace(enabled=False, trigger="tokens:80000", keep="messages:10"),
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
                paper_service=paper_service,
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
    if mw_config.summarization.enabled:
        # Safely parse trigger and keep values
        try:
            trigger_str = getattr(mw_config.summarization, "trigger", "tokens:80000")
            keep_str = getattr(mw_config.summarization, "keep", "messages:10")
            trigger = int(trigger_str.split(":")[1]) if ":" in trigger_str else 80000
            keep = int(keep_str.split(":")[1]) if ":" in keep_str else 10
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning(f"Invalid summarization config, using defaults: {e}")
            trigger, keep = 80000, 10
        pipeline.append(SummarizationMiddleware(trigger_tokens=trigger, keep_messages=keep))

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

    if paper_service:
        pipeline.append(
            CitationContextMiddleware(paper_service)
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
    paper_service: Any | None = None,
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
            paper_service=paper_service,
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
    )


class _MiddlewareWrappedAgent:
    """Attach the repo's middleware chain around the LangGraph agent."""

    def __init__(
        self,
        agent: Any,
        *,
        middlewares: Sequence[Middleware] | None,
        default_config: RunnableConfig,
    ) -> None:
        self._agent = agent
        self._middlewares = middlewares or []
        self._default_config = default_config

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
        if not self._middlewares or not isinstance(result, dict):
            return result
        state = create_thread_state(result)
        return await middleware_after_model(state, runtime_config, self._middlewares)

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
    ) -> dict[str, Any] | None:
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
