"""Lead Agent factory for Wenjin."""

import asyncio
import html
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

from src.agents.chat_agent.blocks import AgentMessage, TextBlock
from src.agents.chat_agent.dynamic_tools import DynamicToolNode
from src.agents.chat_agent.prompts import system as _system_prompts
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
    MissionContextMiddleware,
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
from src.agents.middlewares.capability_skill_preload import (
    CapabilitySkillPreloadMiddleware,
)
from src.agents.thread_state import ThreadState, create_thread_state, merge_thread_state
from src.config import get_default_model_id, get_model_config
from src.config.config_loader import get_app_config
from src.models import model_supports_vision
from src.services.references.boundaries import is_reference_library_bypass_tool

logger = logging.getLogger(__name__)

JsonObject = dict[str, Any]

_PROMPT_CONTEXT_CHAR_LIMITS = {
    "literature_context": 3000,
    "memory_context": 1800,
    "knowledge_context": 2200,
    "mission_prompt_context": 2000,
    "template_context": 3200,
}


def _build_system_prompt(workspace_type: str) -> str:
    """Build the workspace-type-aware Chat Agent system prompt."""

    return _system_prompts.render(workspace_type)


def _concat_text_blocks(msg: AgentMessage) -> str:
    """Join all TextBlock.content values from an AgentMessage.

    Used to populate GeneratedThreadReply.content alongside canonical blocks
    for transport surfaces that still expose a text summary.
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


def _supports_tool_calling(model_name: str) -> bool:
    """Return whether the configured model should be bound to chat tools."""
    try:
        model_config = get_model_config(model_name)
    except Exception:
        logger.debug("Unable to resolve tool support for model %s", model_name, exc_info=True)
        return True
    supports_tools = getattr(model_config, "supports_tools", None)
    return bool(supports_tools) if isinstance(supports_tools, bool) else True


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


def _render_workspace_capability_route_cards(
    caps: list[dict[str, Any]] | None,
) -> str:
    """Render bounded capability route cards for the chat prompt.

    Data is sourced from ``state["available_capabilities"]`` and
    populated by :class:`CapabilitySkillPreloadMiddleware` from the database.

    If *caps* is empty the rendering is skipped entirely — the chat agent
    will not advertise any durable team capability in that turn.
    """
    if not caps:
        return ""

    cap_items = []
    for c in caps:
        card = _render_capability_route_card(c)
        if card:
            cap_items.append(card)
    if not cap_items:
        return ""
    cap_block = (
        "<available_capabilities>\n"
        + "\n".join(cap_items)
        + "\n</available_capabilities>"
    )

    return _build_capability_routing_prompt(cap_block)


def _xml_attr(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _route_text_list(value: Any, *, limit: int = 3, max_chars: int = 160) -> str:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value if str(item or "").strip()]
    else:
        return ""
    text = "；".join(item.strip() for item in items[:limit] if item.strip())
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _route_minimum_context(routing: dict[str, Any]) -> str:
    minimum_context = routing.get("minimum_context")
    if not isinstance(minimum_context, dict):
        return ""
    required = [
        str(key)
        for key, value in minimum_context.items()
        if str(value).strip().lower() == "required"
    ]
    return ",".join(required[:4])


def _render_capability_route_card(capability: dict[str, Any]) -> str:
    definition = capability.get("definition_json")
    definition = definition if isinstance(definition, dict) else {}
    mission = definition.get("mission") if isinstance(definition.get("mission"), dict) else {}
    display = definition.get("display") if isinstance(definition.get("display"), dict) else {}
    tier = str(display.get("entry_tier") or capability.get("tier") or "primary")
    if tier == "hidden":
        return ""
    raw_routing = capability.get("routing")
    if not isinstance(raw_routing, dict):
        raw_routing = definition.get("routing") if isinstance(definition.get("routing"), dict) else {}
    routing = raw_routing if isinstance(raw_routing, dict) else {}
    ambiguity = routing.get("ambiguity") if isinstance(routing.get("ambiguity"), dict) else {}
    guidance = routing.get("user_guidance") if isinstance(routing.get("user_guidance"), dict) else {}

    when = _route_text_list(routing.get("when_to_use"))
    if not when:
        return ""
    not_for = _route_text_list(routing.get("not_for"))
    examples = _route_text_list(routing.get("positive_examples"))
    negative_examples = _route_text_list(routing.get("negative_examples"))
    minimum_context = _route_minimum_context(routing)
    overlaps = _route_text_list(ambiguity.get("overlaps_with"), limit=4, max_chars=120)
    launch_intro = str(guidance.get("launch_intro") or mission.get("user_promise") or "").strip()
    lightweight_answer_hint = str(guidance.get("lightweight_answer_hint") or "").strip()

    attrs = {
        "id": capability.get("id"),
        "name": capability.get("display_name"),
        "tier": tier,
        "surface": mission.get("primary_surface") or "",
        "when": when,
        "not_for": not_for,
        "examples": examples,
        "negative_examples": negative_examples,
        "minimum_context": minimum_context,
        "overlaps": overlaps,
        "launch_intro": launch_intro,
        "lightweight_answer_hint": lightweight_answer_hint,
    }
    serialized = " ".join(
        f'{key}="{_xml_attr(value)}"'
        for key, value in attrs.items()
        if str(value or "").strip()
    )
    return f"  <capability_route_card {serialized}/>"


def _build_capability_routing_prompt(cap_block: str) -> str:
    return f"""

{cap_block}

<feature_launch_system>
**MISSION PRIORITY: understand the user's goal → choose the right interaction → only launch when the task is ready**

You have access to workspace **mission capability route cards** above. Each
route card describes when a durable team task is useful, when a lightweight chat
answer is better, and what minimum context is needed. Internal stages are handled
by the Lead Agent; do not expose workflow-step choices, route-card internals, or internal workflow labels.

**Chat-first navigation rules:**
- `reuse_context`: before asking a clarification question, first reuse recent user turns,
  workspace context, uploaded material summaries, and active mission summaries.
  If the topic, goal, or materials are already available there, launch or answer
  from that context instead of asking the user to repeat it.
- `continue_with_active_mission`: when the user says "继续" or a close follow-up like
  "继续深化方法部分", and the mission context shows one clear active mission,
  "继续" should prefer the active mission when it is unambiguous instead of
  cold-starting or asking the user to restate context.
- `continue_disambiguation`: If "继续" could mean multiple selected or completed missions,
  ask one question to disambiguate which mission to continue before launching.
- `mission_plan_then_launch`: if the user asks "你打算怎么做" or otherwise asks how Wenjin
  will proceed, give a short editable plan in natural language first. Launch only
  when the user confirms.
- `no_menu_ui`: right-panel capability cards are internal. They are not the user
  interaction model. Do not ask the user to click a capability card, choose a
  route card, or pick an internal workflow label.

**Interaction decisions:**
- `answer_in_chat`: use for concepts, short local rewrites, quick discussion, or
  any request that can be handled without a durable artifact, team execution,
  sandbox, Prism review, or external evidence gathering.
- `ask_clarification`: use when one minimum launch context field is missing.
  Ask one useful question; 不要列清单，不要让用户填表.
- `draft_intake_spec`: REQUIRED before launching the super workflows
  `software_copyright_application_pack` and `math_modeling_paper_pack`.
  Use it to create a Markdown clarification spec card with exact launch params.
  For math modeling, always set programming_language to python. For software
  copyright, use mock backend code plus static frontend screenshots; do not use
  AI-generated UI images as application evidence.
- `offer_choices`: use when two capabilities are both plausible and the choice
  changes user expectation, cost, or deliverable. Offer two natural choices,
  for example "先找研究空白，还是直接进入初稿？"
- `launch_feature`: use when the user clearly asks for a durable multi-step
  deliverable and minimum context is present or safely inferable.

**STRICT RULE: Only call `launch_feature(feature_id=<capability_id>, params={{...}})`
after choosing `launch_feature`. If you call it, do it in the same turn. Without
an actual tool call, NOTHING runs.**

**Super workflow intake rule:**
- For `software_copyright_application_pack` or `math_modeling_paper_pack`, first
  guide the user toward a complete spec and call `draft_intake_spec`.
- If the user explicitly approves a ready spec or says "开始做/执行/按这个来",
  call `launch_feature` using the params from that spec in the same turn.
- If the user is still clarifying, update the spec with `draft_intake_spec`;
  do not launch yet.

**MANDATORY Launch Scenarios:**
1. Clear durable deliverable matching a route card + minimum context → call launch_feature
2. User clicks a suggestion pill or enters through a capability deep-link + route is clear → call launch_feature
3. Sufficient context already in conversation/workspace → launch immediately

**STRICT ENFORCEMENT:**
- ❌ DO NOT say "已启动" / "我来帮你启动" without actually calling the tool
- ❌ DO NOT turn concept explanations, short sentence edits, or lightweight chat into team tasks
- ❌ DO NOT expose capability id, schema id, trigger phrases, route-card labels, route-card internals, or internal workflow labels to users
- ❌ DO NOT make up status messages — the Mission Console shows real status
- ✅ Clear multi-step task: call `launch_feature` IN THE SAME TURN
- ✅ Missing minimum params: ask ONE focused question, launch next turn
- ✅ Ambiguous but actionable: offer two natural choices, not a long menu
- ✅ Small question: answer directly and optionally mention a deeper team task

**Example (correct):**
User: "帮我调研 X 主题的文献"
You: call launch_feature(feature_id="thesis_research_pack", params={{"goal": "X"}})
You: "好的，我已经启动论文研究包，进度会在 Mission Console 中显示。"

**Example (plan first):**
User: "你打算怎么做？"
You: "我会先梳理你的研究问题和现有材料，再确认证据缺口，随后启动合适的任务去产出初稿或文献定位。这个计划你要我直接按它开始吗？"

**Example (lightweight):**
User: "联邦学习是什么？"
You: "联邦学习是一种让多方在不直接共享原始数据的情况下共同训练模型的方法。这个问题我可以先直接解释，不需要启动团队任务。"

**Example (clarify):**
User: "帮我写 SCI"
You: "可以。你想围绕哪个具体研究问题或已有材料来写？有了主题后我就能让论文团队开始搭结构和证据链。"

**Example (choice):**
User: "联邦学习结合大模型这个方向帮我看看"
You: "这可以有两个做法：先让文献专家找研究空白和创新点，或者直接让论文团队按 SCI 初稿方向推进。你想先做哪一个？"

**Example (WRONG):**
User: "帮我调研 X"
You: "已启动深度调研..." [WITHOUT calling launch_feature]
^ This is the most serious error.
</feature_launch_system>"""


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
    # Base system prompt — sourced from the workspace-type prompt module.
    workspace_type = state.get("workspace_type")
    discipline = state.get("discipline")
    base_prompt = _build_system_prompt(workspace_type or "")

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

    mission_prompt_context = state.get("mission_prompt_context")
    if mission_prompt_context:
        base_prompt += "\n\n" + _truncate_prompt_block(
            mission_prompt_context,
            max_chars=_PROMPT_CONTEXT_CHAR_LIMITS["mission_prompt_context"],
        )

    configurable = config.get("configurable", {})
    selected_skill = (
        configurable.get("selected_skill")
        or state.get("current_skill")
    )
    if selected_skill:
        # Thread/deep-link skill names are only route hints now. The capability
        # catalog remains the source of truth for launchable team work.
        base_prompt += (
            "\n\n## Capability Route Hint"
            f"\nThe incoming thread carried route hint `{selected_skill}`. "
            "Treat it only as a hint: choose a matching "
            "<capability_route_card> when one fits the user request, otherwise "
            "answer, clarify, or offer choices. Do not expose this identifier."
        )

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
            "\nUse the launch_feature tool only when the user's request matches a capability route card."
        )

    base_prompt += _render_workspace_capability_route_cards(
        state.get("available_capabilities"),
    )

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
        draft_intake_spec_tool,
        launch_feature_tool,
        list_capabilities_tool,
        list_reference_library_tool,
        list_workspace_artifacts_tool,
        present_files_tool,
        read_reference_outline_node_tool,
        search_reference_text_units_tool,
        view_image_tool,
    )

    # Interaction tools
    tools.append(ask_clarification_tool)
    tools.append(draft_intake_spec_tool)
    tools.append(launch_feature_tool)
    tools.extend([
        list_capabilities_tool,
        list_workspace_artifacts_tool,
        list_reference_library_tool,
        search_reference_text_units_tool,
        read_reference_outline_node_tool,
    ])

    # Output tools
    tools.append(present_files_tool)
    tools.append(view_image_tool)

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

    # Must follow WorkspaceContextMiddleware so workspace_type is in state.
    middlewares.append(CapabilitySkillPreloadMiddleware())
    middlewares.append(MissionContextMiddleware())

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
    memory_queue: Any | None = None,
    memory_capture_enabled: bool = True,
) -> list[Middleware]:
    """Build the middleware pipeline for the lead agent.

    Order:
    1.  ThreadDataMiddleware       - Infrastructure
    2.  UploadsMiddleware          - Infrastructure
    3.  ExecutionMiddleware        - Tool execution routing (conditional)
    5.  DanglingToolCallMiddleware - Fix
    6.  ToolErrorHandlingMiddleware - Tool failure degradation
    7.  LLMErrorHandlingMiddleware - LLM retry/fallback/circuit guard
    8.  SummarizationMiddleware    - Context management (conditional)
    9.  MemoryMiddleware           - Context management (conditional)
    10. WorkspaceContextMiddleware - Academic (conditional)
    11. LiteratureContextMiddleware - Academic (conditional)
    12. KnowledgeContextMiddleware - Academic (conditional)
    13. DisciplineContextMiddleware - Academic
    14. TodoListMiddleware         - Interaction (conditional)
    15. ViewImageMiddleware        - Interaction
    16. LoopDetectionMiddleware    - Control (loop break)
    17. TitleMiddleware            - Post-processing
    18. CitationContextMiddleware  - Post-processing (conditional)
    19. ClarificationMiddleware    - Control (MUST BE LAST)
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

    # Tool error degradation
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
    # Must follow WorkspaceContextMiddleware so workspace_type is in state.
    pipeline.append(CapabilitySkillPreloadMiddleware())
    pipeline.append(MissionContextMiddleware())
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


def make_chat_agent(
    config: RunnableConfig,
    middlewares: Sequence[Middleware] | None = None,
    *,
    workspace_service: Any | None = None,
    index_service: Any | None = None,
    artifact_service: Any | None = None,
    reference_service: Any | None = None,
    memory_queue: Any | None = None,
) -> "_MiddlewareWrappedAgent":
    """Factory: build the conversational chat agent for a workspace thread.

    This is the left-panel agent the user talks to.  It runs in the gateway
    process and dispatches workspace capabilities to the right-side
    :class:`LeadAgentRuntime` via the ``launch_feature`` tool.

    Registered as the LangGraph entrypoint in ``langgraph.json``.

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
        if not _supports_tool_calling(model_name):
            return base_model
        return base_model.bind_tools(current_tools)

    # Build system prompt for the agent.  Capability/skill catalog is provided
    # by CapabilitySkillPreloadMiddleware writing into state before the model
    # call, so prompt_fn can stay synchronous.
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

        # The ReAct loop above already streamed the model's text to the user.
        # Wrap the same text as a single TextBlock for the canonical
        # response_blocks representation — no second LLM call needed.
        # Status/question/result cards come from infrastructure events
        # (worker, execution.completed), not from re-parsing chat text.
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
                    try:
                        text_block = TextBlock(content=final_text)
                        agent_msg = AgentMessage(blocks=[text_block])
                        new_blocks = [
                            b.model_dump(exclude_none=True)
                            for b in agent_msg.blocks
                        ]
                        existing_blocks = list(state.get("response_blocks") or [])
                        state = merge_thread_state(
                            state, {"response_blocks": existing_blocks + new_blocks}
                        )

                    except Exception:
                        logger.exception(
                            "_apply_after_model failed to build response_blocks; "
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
