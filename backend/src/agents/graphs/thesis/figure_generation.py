"""Figure Generation sub-graph — LLM-driven planning and code generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.workspace_lead_agent import register_feature_graph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy mapping (mirrors thesis_feature_service)
# ---------------------------------------------------------------------------
_FIGURE_STRATEGY_BY_TYPE: dict[str, str] = {
    "flowchart": "mermaid",
    "architecture": "mermaid",
    "diagram": "mermaid",
    "data_visualization": "python",
    "data_chart": "python",
    "chart": "python",
    "graph": "python",
    "concept_map": "kling",
    "concept": "kling",
}

_VALID_STRATEGIES = {"mermaid", "python", "kling"}


# ---------------------------------------------------------------------------
# Helper: resolve strategy from figure type
# ---------------------------------------------------------------------------
def _resolve_strategy(fig_type: str) -> str:
    """Map a figure type to its generation strategy.

    Unknown types default to ``mermaid``.
    """
    normalized = (fig_type or "").strip().lower()
    return _FIGURE_STRATEGY_BY_TYPE.get(normalized, "mermaid")


# ---------------------------------------------------------------------------
# Helper: build fallback source code per strategy
# ---------------------------------------------------------------------------
def _build_fallback_source(strategy: str, description: str) -> str:
    """Return template code for *strategy* when LLM generation fails."""
    desc = (description or "").replace("'", "").replace('"', "").replace("\n", " ").strip()
    if not desc:
        desc = "示例图表"

    if strategy == "python":
        title = desc[:40]
        return "\n".join([
            "import matplotlib.pyplot as plt",
            "",
            "labels = ['方案A', '方案B', '方案C', '方案D']",
            "values = [0.68, 0.74, 0.81, 0.79]",
            "",
            "fig, ax = plt.subplots(figsize=(8, 4.5))",
            "ax.bar(labels, values, color=['#2563eb', '#0891b2', '#16a34a', '#f59e0b'])",
            "ax.set_ylim(0, 1)",
            f"ax.set_title('{title}')",
            "ax.set_ylabel('Score')",
            "for idx, value in enumerate(values):",
            "    ax.text(idx, value + 0.02, f'{value:.2f}', ha='center')",
            "plt.tight_layout()",
            "plt.savefig('/workspace/output/chart.png', dpi=200)",
        ])

    if strategy == "kling":
        prompt_desc = desc[:120]
        return (
            "生成一张用于本科论文的学术概念图，风格简洁、信息层次清晰。"
            f"主题：{prompt_desc}。要求包含核心实体、关键关系和流程方向，可直接用于论文插图。"
        )

    # Default: mermaid
    summary = desc[:36]
    return "\n".join([
        "flowchart TD",
        f'  A["研究问题: {summary}"] --> B["方法设计"]',
        '  B --> C["实验验证"]',
        '  C --> D["结果分析"]',
        '  D --> E["结论与展望"]',
    ])


# ---------------------------------------------------------------------------
# Helper: parse JSON from LLM response
# ---------------------------------------------------------------------------
def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# LLM Step 1: Plan figure
# ---------------------------------------------------------------------------
_PLAN_FIGURE_PROMPT = """你是学术论文图表规划专家。根据以下信息，规划一张最优的学术图表。

图表类型: {fig_type}
图表描述: {description}
{chapter_context}
{memory_context}

请分析需求并返回 JSON:
{{
  "recommended_strategy": "mermaid 或 python 或 kling（选择最适合的生成策略）",
  "elements": ["图中应包含的关键元素1", "关键元素2", "关键元素3"],
  "layout": "布局建议（如：自上而下流程、左右对比、环形结构等）",
  "title_suggestion": "建议的图表标题"
}}

策略说明:
- mermaid: 适合流程图、架构图、时序图等结构化图表
- python: 适合数据可视化、柱状图、折线图、散点图等
- kling: 适合概念图、创意性插图等需要 AI 生成的图片

仅返回 JSON。"""


async def _plan_figure(
    fig_type: str,
    description: str,
    chapter_context: str | None,
    memory_context: str | None,
) -> dict[str, Any] | None:
    """Step 1: LLM plans optimal figure. Returns None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.3)
    except Exception:
        return None

    ch_text = f"\n所属章节上下文:\n{chapter_context}" if chapter_context else ""
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt = _PLAN_FIGURE_PROMPT.format(
        fig_type=fig_type,
        description=description,
        chapter_context=ch_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        plan = _parse_json_response(content)
        if plan is None:
            return None
        # Validate recommended_strategy
        rec = (plan.get("recommended_strategy") or "").strip().lower()
        if rec in _VALID_STRATEGIES:
            plan["recommended_strategy"] = rec
        else:
            plan.pop("recommended_strategy", None)
        return plan
    except Exception:
        logger.exception("Step 1 (plan_figure) failed")
        return None


# ---------------------------------------------------------------------------
# LLM Step 2: Generate figure code
# ---------------------------------------------------------------------------
_GENERATE_MERMAID_PROMPT = """你是 Mermaid 图表语法专家。根据以下规划生成 Mermaid 代码。

图表描述: {description}
{plan_context}
{memory_context}

要求:
1. 生成完整的 Mermaid 语法代码
2. 节点标签使用中文
3. 布局清晰、层次分明
4. 仅返回 Mermaid 代码，不要包含 ```mermaid 标记"""

_GENERATE_PYTHON_PROMPT = """你是 Python 数据可视化专家。根据以下规划生成 matplotlib 绑定代码。

图表描述: {description}
{plan_context}
{memory_context}

要求:
1. 使用 matplotlib 生成图表
2. 图表标题和标签使用中文（需设置中文字体支持）
3. 配色专业美观
4. 最后必须调用 plt.savefig('/workspace/output/chart.png', dpi=200)
5. 仅返回完整的 Python 代码，不要包含 ```python 标记"""

_GENERATE_KLING_PROMPT = """你是 AI 图片生成提示词专家。根据以下规划生成高质量的图片生成提示词。

图表描述: {description}
{plan_context}
{memory_context}

要求:
1. 生成适合学术论文的概念图/插图提示词
2. 风格简洁、信息层次清晰
3. 包含核心实体、关键关系和流程方向
4. 可直接用于论文插图
5. 仅返回提示词文本"""

_STRATEGY_PROMPTS: dict[str, str] = {
    "mermaid": _GENERATE_MERMAID_PROMPT,
    "python": _GENERATE_PYTHON_PROMPT,
    "kling": _GENERATE_KLING_PROMPT,
}


async def _generate_figure_code(
    strategy: str,
    description: str,
    plan: dict[str, Any] | None,
    memory_context: str | None,
) -> str | None:
    """Step 2: LLM generates figure code/prompt. Returns None on failure."""
    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.3)
    except Exception:
        return None

    plan_text = ""
    if plan:
        plan_text = "\n图表规划:\n" + json.dumps(plan, ensure_ascii=False, indent=2)
    mem_text = f"\n用户记忆上下文:\n{memory_context}" if memory_context else ""

    prompt_template = _STRATEGY_PROMPTS.get(strategy, _STRATEGY_PROMPTS["mermaid"])
    prompt = prompt_template.format(
        description=description,
        plan_context=plan_text,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        # Strip potential markdown fences
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()
        return text if text else None
    except Exception:
        logger.exception("Step 2 (generate_figure_code) failed")
        return None


# ---------------------------------------------------------------------------
# Main graph entry point
# ---------------------------------------------------------------------------
@register_feature_graph("figure_generation", workspace_type="thesis")
async def figure_generation_graph(
    initial_state: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute 2-step figure generation pipeline.

    Pipeline:
        1. plan_figure — LLM analyzes context and plans the figure
        2. generate_figure_code — LLM generates code/prompt based on plan

    Each step has fallback. Output is code/prompt ready for downstream execution.
    """
    params = payload.get("params", {})
    fig_type = str(params.get("fig_type", params.get("figure_type", "flowchart"))).strip().lower()
    description = str(params.get("description", "")).strip()
    chapter_index = params.get("chapter_index")
    if chapter_index is not None:
        try:
            chapter_index = int(chapter_index)
        except (TypeError, ValueError):
            chapter_index = None

    chapter_context = str(params.get("chapter_context", "")).strip() or None
    memory_context = initial_state.get("knowledge_context")

    # Resolve default strategy from fig_type
    strategy = _resolve_strategy(fig_type)

    # Step 1: Plan figure (LLM)
    figure_plan = await _plan_figure(
        fig_type=fig_type,
        description=description,
        chapter_context=chapter_context,
        memory_context=memory_context,
    )

    # Allow plan to override strategy
    if figure_plan and figure_plan.get("recommended_strategy"):
        strategy = figure_plan["recommended_strategy"]

    # Step 2: Generate figure code (LLM)
    generated_code = await _generate_figure_code(
        strategy=strategy,
        description=description,
        plan=figure_plan,
        memory_context=memory_context,
    )

    # Determine pipeline step results
    planning_ok = figure_plan is not None
    code_gen_ok = generated_code is not None

    # Fallback to template if LLM code generation failed
    if not code_gen_ok:
        generated_code = _build_fallback_source(strategy, description)

    generation_mode = "llm" if code_gen_ok else "template_fallback"

    # Build result — source_code for mermaid/python, prompt for kling
    result: dict[str, Any] = {
        "figure_type": fig_type,
        "description": description,
        "chapter_index": chapter_index,
        "strategy": strategy,
        "source_code": generated_code if strategy != "kling" else None,
        "prompt": generated_code if strategy == "kling" else None,
        "figure_plan": figure_plan,
        "generation_mode": generation_mode,
        "pipeline_steps": {
            "figure_planning": planning_ok,
            "code_generation": code_gen_ok,
        },
        "status": "generated_code",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    return result
