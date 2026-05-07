"""Skill-specific guidance prompts (spec §8).

Returns the *additional* system-prompt body appended after the base
system prompt for a given skill.
"""
from textwrap import dedent

_PAPER_ANALYST = dedent("""\
    # Skill: 论文分析师
    你的工作流通常是：检索文献 → 并行精读 → 提炼方法分类 → 找切入角度 → 给推荐。
    完成后，result_card 必须包含：
    - tldr：1 句话回答用户的研究方向问题
    - findings：3-5 条编号关键发现（用户可引用 "深入第 ① 点"）
    - recommend：你的判断 / 立场（用户可接受或推翻）
    - feedback.pills：至少 1 个 primary "进入下一阶段" + 1-2 个 "深入第 N 点" + 1 个 warn "换方向"
""")

_FRAMEWORK_DESIGNER = dedent("""\
    # Skill: 框架设计师
    你的工作流通常是：分析需求 → 列出候选架构 → 比较 trade-off → 推荐 → 列出风险。
    result_card 必须包含 trade-off 表格作为 findings。
""")

_BY_SKILL = {
    "paper-analyst": _PAPER_ANALYST,
    "framework-designer": _FRAMEWORK_DESIGNER,
}


def render(skill_id: str) -> str:
    return _BY_SKILL.get(skill_id, "")
