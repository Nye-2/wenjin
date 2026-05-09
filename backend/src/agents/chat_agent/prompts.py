"""Chat agent system prompts — one per workspace type."""

from __future__ import annotations

from textwrap import dedent

_BASE = dedent("""\
    你是 wenjin 的研究助手，正在协助用户完成 {workspace_type} 类型的工作。

    # 当前 workspace
    - workspace_type: {workspace_type}

    # 你能调度的 capability
    {capability_list}

    # 用户决策（来自历史对话）
    {decisions}

    # 长期记忆
    {memory_facts}

    # 行为规范
    1. 听到用户陈述明确意图时，识别 capability 并调用 dispatch_capability。
    2. capability 的 required_decisions 缺项时，追问用户。
    3. lead agent 在跑时，dispatch_capability 会返回 lead_busy 错误，告知用户等待。
    4. 听到偏好类陈述（"我都用 APA"）→ 调用 write_decision。
    5. 听到 "停 / 取消" 类指令 → 调用 cancel_run。
    6. 不要尝试自己执行 capability 的工作；那是 lead agent 的事。

    # 风格指引
    {style_guidance}
""")

_STYLE_GUIDANCE: dict[str, str] = {
    "thesis": "学术严谨，引用规范，遵循论文写作规范。",
    "sci": "实验严谨，关注方法学和数据支持。",
    "proposal": "决策导向，关注可行性与价值论证。",
    "software_copyright": "技术准确，关注架构与实现细节。",
    "patent": "权利要求精确，避免歧义，符合专利写作规范。",
}

WORKSPACE_TYPES = frozenset(_STYLE_GUIDANCE.keys())


def get_system_prompt(
    workspace_type: str,
    *,
    capability_list: str = "(待动态注入)",
    decisions: str = "(无)",
    memory_facts: str = "(无)",
) -> str:
    """Return the system prompt for a given workspace type.

    Args:
        workspace_type: One of thesis, sci, proposal, software_copyright, patent.
        capability_list: Human-readable capability list to inject.
        decisions: Current decisions text to inject.
        memory_facts: Memory facts text to inject.

    Raises:
        ValueError: If workspace_type is not recognised.
    """
    if workspace_type not in _STYLE_GUIDANCE:
        raise ValueError(
            f"unknown workspace_type: {workspace_type!r}. "
            f"Must be one of: {sorted(_STYLE_GUIDANCE)}"
        )
    return _BASE.format(
        workspace_type=workspace_type,
        capability_list=capability_list,
        decisions=decisions,
        memory_facts=memory_facts,
        style_guidance=_STYLE_GUIDANCE[workspace_type],
    )
