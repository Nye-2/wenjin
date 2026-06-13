"""Feedback revision service for LaTeX editor."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from src.models.factory import create_chat_model
from src.models.router import InvalidRequestedModelError, route_writing_model, validate_requested_model

logger = logging.getLogger(__name__)

RewriteScope = Literal["selection", "section", "document"]

_SECTION_LEVELS: dict[str, int] = {
    "section": 1,
    "subsection": 2,
    "subsubsection": 3,
    "paragraph": 4,
    "subparagraph": 5,
}

_SECTION_COMMAND_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\s*"
    r"(?:\[[^\]]*\])?\s*\{([^}]*)\}"
)

_SELECTION_REWRITE_PROMPT = """你是学术论文 LaTeX 改写助手。请根据用户点评，只改写指定选区。

【用户点评】
{comment}

【章节信息】
标题: {section_title}
层级: {section_level}

【上下文（选区前）】
{context_before}

【原选区】
{target_text}

【上下文（选区后）】
{context_after}

先在内部判断点评主要属于哪些维度：事实准确性、逻辑严密性、方法规范性、战略/评审适配度、完整性、表达清晰度。
不要输出这个判断，只把它用于决定改写重点。

要求：
1. 只改写原选区，不要改写选区外内容。
2. 保持 LaTeX 语法、引用、标签、术语风格与上下文一致。
3. 如原文包含 \\cite{{}}、\\ref{{}}、\\label{{}}、公式或环境，尽量保留并在此基础上优化。
4. 不要编造未给出的事实、数据、文献或实验结论；证据不足时用更稳妥的表述。
5. 不要输出解释。

输出 JSON：
{{
  "rewritten_text": "改写后的选区文本",
  "changes_summary": "一句话总结修改点"
}}
只返回 JSON。"""

_SECTION_REWRITE_PROMPT = """你是学术论文 LaTeX 改写助手。请根据用户点评，重写“当前 section”。

【用户点评】
{comment}

【用户划词（供你定位关注点）】
{selected_text}

【当前章节】
标题: {section_title}
层级: {section_level}

【章节原文】
{section_text}

【章节前文（不要改）】
{context_before}

【章节后文（不要改）】
{context_after}

先在内部判断点评主要属于哪些维度：事实准确性、逻辑严密性、方法规范性、战略/评审适配度、完整性、表达清晰度。
不要输出这个判断，只把它用于决定改写重点和保留要素。

要求：
1. 只输出当前章节的重写结果，不要包含章节前后文。
2. 章节的宏观结构尽量保持一致，针对点评进行实质修改。
3. 保持 LaTeX 语法、引用、标签、术语风格一致。
4. 不要编造未给出的事实、数据、文献或实验结论；证据不足时用更稳妥的表述。
5. 不要输出解释。

输出 JSON：
{{
  "rewritten_section": "重写后的完整章节文本",
  "changes_summary": "一句话总结修改点"
}}
只返回 JSON。"""

_DOCUMENT_REWRITE_PROMPT = """你是学术论文 LaTeX 改写助手。请根据用户点评，重写“完整主稿”。

【用户点评】
{comment}

【完整主稿】
{document_text}

先在内部判断点评主要属于哪些维度：事实准确性、逻辑严密性、方法规范性、战略/评审适配度、完整性、表达清晰度。
不要输出这个判断，只把它用于决定改写重点和保留要素。

要求：
1. 输出完整主稿的重写结果，不要只输出局部片段。
2. 保持 LaTeX 结构、引用、标签、公式、环境和术语风格一致。
3. 针对用户点评做实质修改，同时避免不必要的结构大改。
4. 不要编造未给出的事实、数据、文献或实验结论；证据不足时用更稳妥的表述。
5. 不要输出解释。

输出 JSON：
{{
  "rewritten_document": "重写后的完整主稿",
  "changes_summary": "一句话总结修改点"
}}
只返回 JSON。"""


@dataclass(frozen=True)
class HeadingMarker:
    """A LaTeX heading marker."""

    start: int
    level: int
    title: str
    kind: str


@dataclass(frozen=True)
class ResolvedRange:
    """Resolved text range."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ResolvedSection:
    """Resolved section block."""

    start: int
    end: int
    title: str
    level: str


def _strip_latex_comment(line: str) -> str:
    for index, char in enumerate(line):
        if char != "%":
            continue
        backslash_count = 0
        cursor = index - 1
        while cursor >= 0 and line[cursor] == "\\":
            backslash_count += 1
            cursor -= 1
        if backslash_count % 2 == 0:
            return line[:index]
    return line


def _normalize_anchor_segment(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _score_context_match(expected: str, actual: str) -> float:
    left = _normalize_anchor_segment(expected)
    right = _normalize_anchor_segment(actual)
    if not left or not right:
        return 0.0
    if left == right:
        return min(80.0, float(len(left) * 2))
    if right.endswith(left):
        return min(60.0, float(len(left) * 1.5))
    if left.endswith(right):
        return min(50.0, float(len(right) * 1.3))
    overlap = 0
    max_len = min(len(left), len(right), 60)
    for size in range(max_len, 7, -1):
        if left[-size:] == right[-size:]:
            overlap = size
            break
    return float(overlap)


def _count_lines_until(text: str, offset: int) -> int:
    line = 1
    safe_offset = max(0, min(offset, len(text)))
    for index in range(safe_offset):
        if text[index] == "\n":
            line += 1
    return line


def _collect_headings(content: str) -> list[HeadingMarker]:
    headings: list[HeadingMarker] = []
    cursor = 0
    for raw_line in content.splitlines(keepends=True):
        clean_line = _strip_latex_comment(raw_line.rstrip("\n"))
        for match in _SECTION_COMMAND_RE.finditer(clean_line):
            kind = str(match.group(1) or "").strip()
            title = str(match.group(2) or "").strip()
            if not kind:
                continue
            level = _SECTION_LEVELS.get(kind, 99)
            headings.append(
                HeadingMarker(
                    start=cursor + match.start(),
                    level=level,
                    title=title,
                    kind=kind,
                )
            )
        cursor += len(raw_line)
    return headings


def _find_nearest_heading(headings: list[HeadingMarker], position: int) -> HeadingMarker | None:
    nearest: HeadingMarker | None = None
    for heading in headings:
        if heading.start > position:
            break
        nearest = heading
    return nearest


def build_feedback_anchor(content: str, start: int, end: int) -> dict[str, Any]:
    """Build a robust anchor payload for a selected range."""
    safe_start = max(0, min(start, len(content)))
    safe_end = max(safe_start, min(end, len(content)))
    headings = _collect_headings(content)
    heading = _find_nearest_heading(headings, safe_start)
    return {
        "selected_text": content[safe_start:safe_end],
        "prefix": content[max(0, safe_start - 120):safe_start],
        "suffix": content[safe_end:min(len(content), safe_end + 120)],
        "heading_title": heading.title if heading else "",
        "heading_level": heading.kind if heading else "",
        "line_hint": _count_lines_until(content, safe_start),
    }


def resolve_feedback_range(
    *,
    content: str,
    selected_text: str,
    start: int | None,
    end: int | None,
    anchor: dict[str, Any] | None = None,
) -> ResolvedRange | None:
    """Resolve selection range even after nearby edits."""
    anchor_dict = anchor if isinstance(anchor, dict) else {}
    target_text = str(anchor_dict.get("selected_text") or selected_text or "")
    if not target_text:
        return None

    safe_start = max(0, min(int(start or 0), len(content)))
    default_end = safe_start + len(target_text)
    safe_end = max(safe_start, min(int(end if end is not None else default_end), len(content)))

    exact = content[safe_start:safe_end]
    if exact == target_text:
        return ResolvedRange(start=safe_start, end=safe_end, text=target_text)

    near_start = max(0, safe_start - 400)
    near_end = min(len(content), safe_end + 400 + len(target_text))
    nearby = content[near_start:near_end]
    nearby_index = nearby.find(target_text)
    if nearby_index >= 0:
        candidate_start = near_start + nearby_index
        return ResolvedRange(
            start=candidate_start,
            end=candidate_start + len(target_text),
            text=target_text,
        )

    candidate_starts: list[int] = []
    cursor = 0
    while cursor < len(content):
        found = content.find(target_text, cursor)
        if found < 0:
            break
        candidate_starts.append(found)
        if len(candidate_starts) >= 120:
            break
        cursor = found + max(1, len(target_text))

    if not candidate_starts:
        return None

    headings = _collect_headings(content)
    anchor_title = str(anchor_dict.get("heading_title") or "")
    anchor_level = str(anchor_dict.get("heading_level") or "")
    anchor_prefix = str(anchor_dict.get("prefix") or "")
    anchor_suffix = str(anchor_dict.get("suffix") or "")
    anchor_line = int(anchor_dict.get("line_hint") or 1)

    best_start: int | None = None
    best_score: float = float("-inf")
    for candidate_start in candidate_starts:
        candidate_end = candidate_start + len(target_text)
        score = 0.0
        score -= min(abs(candidate_start - safe_start), 3000) / 8.0

        actual_prefix = content[max(0, candidate_start - 120):candidate_start]
        actual_suffix = content[candidate_end:min(len(content), candidate_end + 120)]
        score += _score_context_match(anchor_prefix, actual_prefix)
        score += _score_context_match(anchor_suffix, actual_suffix)

        heading = _find_nearest_heading(headings, candidate_start)
        if heading and anchor_title and heading.title == anchor_title:
            score += 90.0
        if heading and anchor_level and heading.kind == anchor_level:
            score += 30.0

        line_distance = abs(_count_lines_until(content, candidate_start) - anchor_line)
        score -= min(line_distance, 200) / 3.0

        if score > best_score:
            best_score = score
            best_start = candidate_start

    if best_start is None:
        return None
    return ResolvedRange(
        start=best_start,
        end=best_start + len(target_text),
        text=target_text,
    )


def resolve_section_by_offset(content: str, offset: int) -> ResolvedSection:
    """Resolve the section block containing ``offset``."""
    safe_offset = max(0, min(offset, len(content)))
    headings = _collect_headings(content)
    current = _find_nearest_heading(headings, safe_offset)
    if current is None:
        return ResolvedSection(
            start=0,
            end=len(content),
            title="文档开头",
            level="document",
        )

    end = len(content)
    found_current = False
    for heading in headings:
        if heading.start == current.start and heading.kind == current.kind:
            found_current = True
            continue
        if not found_current:
            continue
        if heading.level <= current.level:
            end = heading.start
            break

    return ResolvedSection(
        start=current.start,
        end=end,
        title=current.title or "未命名章节",
        level=current.kind,
    )


def _parse_json_response(text: str) -> dict[str, Any] | None:
    clean_text = str(text or "").strip()
    if not clean_text:
        return None
    if clean_text.startswith("```"):
        lines = clean_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean_text = "\n".join(lines).strip()
    try:
        parsed = json.loads(clean_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _pick_model_id(model_id: str | None) -> str:
    try:
        requested = validate_requested_model(
            model_id,
            allowed_categories=("llm",),
            require_tools=False,
        )
    except InvalidRequestedModelError as exc:
        raise ValueError(str(exc)) from exc
    return route_writing_model(requested_model=requested)


async def _invoke_rewrite(prompt: str, *, model_id: str) -> tuple[str, dict[str, Any] | None]:
    model = create_chat_model(model_id, temperature=0.3)
    response = await model.ainvoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    parsed = _parse_json_response(str(content))
    return str(content), parsed


async def rewrite_with_feedback(
    *,
    content: str,
    comment: str,
    selected_text: str,
    selection_start: int | None = None,
    selection_end: int | None = None,
    anchor: dict[str, Any] | None = None,
    scope: RewriteScope = "section",
    requested_model_id: str | None = None,
) -> dict[str, Any]:
    """Rewrite selected range or containing section according to feedback."""
    if not comment.strip():
        raise ValueError("Feedback comment cannot be empty")

    model_id = _pick_model_id(requested_model_id)

    if scope == "document":
        if not content.strip():
            raise ValueError("Document content cannot be empty")
        prompt = _DOCUMENT_REWRITE_PROMPT.format(
            comment=comment.strip(),
            document_text=content,
        )
        raw_response, parsed = await _invoke_rewrite(prompt, model_id=model_id)
        rewritten_document = ""
        changes_summary = ""
        if isinstance(parsed, dict):
            rewritten_document = str(parsed.get("rewritten_document") or "").strip()
            changes_summary = str(parsed.get("changes_summary") or "").strip()
        if not rewritten_document:
            rewritten_document = raw_response.strip().strip("`")
        if not rewritten_document:
            raise RuntimeError("Model did not return rewritten document")
        return {
            "model_id": model_id,
            "scope": "document",
            "resolved_selection_start": 0,
            "resolved_selection_end": len(content),
            "target_start": 0,
            "target_end": len(content),
            "section_title": "全文",
            "section_level": "document",
            "rewritten_text": rewritten_document,
            "changes_summary": changes_summary,
        }

    resolved = resolve_feedback_range(
        content=content,
        selected_text=selected_text,
        start=selection_start,
        end=selection_end,
        anchor=anchor,
    )
    if resolved is None:
        raise ValueError("Unable to locate selected text in current file")

    section = resolve_section_by_offset(content, resolved.start)

    if scope == "selection":
        target_start = resolved.start
        target_end = resolved.end
        target_text = resolved.text
        prompt = _SELECTION_REWRITE_PROMPT.format(
            comment=comment.strip(),
            section_title=section.title,
            section_level=section.level,
            context_before=content[max(0, target_start - 260):target_start],
            target_text=target_text,
            context_after=content[target_end:min(len(content), target_end + 260)],
        )
        raw_response, parsed = await _invoke_rewrite(prompt, model_id=model_id)
        rewritten_text = ""
        changes_summary = ""
        if isinstance(parsed, dict):
            rewritten_text = str(parsed.get("rewritten_text") or "").strip()
            changes_summary = str(parsed.get("changes_summary") or "").strip()
        if not rewritten_text:
            # Fallback: tolerate non-JSON plain-text output
            rewritten_text = raw_response.strip().strip("`")
        if not rewritten_text:
            raise RuntimeError("Model did not return rewritten text")
        return {
            "model_id": model_id,
            "scope": "selection",
            "resolved_selection_start": resolved.start,
            "resolved_selection_end": resolved.end,
            "target_start": target_start,
            "target_end": target_end,
            "section_title": section.title,
            "section_level": section.level,
            "rewritten_text": rewritten_text,
            "changes_summary": changes_summary,
        }

    target_start = section.start
    target_end = section.end
    section_text = content[target_start:target_end]
    prompt = _SECTION_REWRITE_PROMPT.format(
        comment=comment.strip(),
        selected_text=resolved.text,
        section_title=section.title,
        section_level=section.level,
        section_text=section_text,
        context_before=content[max(0, target_start - 260):target_start],
        context_after=content[target_end:min(len(content), target_end + 260)],
    )
    raw_response, parsed = await _invoke_rewrite(prompt, model_id=model_id)
    rewritten_section = ""
    changes_summary = ""
    if isinstance(parsed, dict):
        rewritten_section = str(parsed.get("rewritten_section") or "").strip()
        changes_summary = str(parsed.get("changes_summary") or "").strip()
    if not rewritten_section:
        rewritten_section = raw_response.strip().strip("`")
    if not rewritten_section:
        raise RuntimeError("Model did not return rewritten section")
    return {
        "model_id": model_id,
        "scope": "section",
        "resolved_selection_start": resolved.start,
        "resolved_selection_end": resolved.end,
        "target_start": target_start,
        "target_end": target_end,
        "section_title": section.title,
        "section_level": section.level,
        "rewritten_text": rewritten_section,
        "changes_summary": changes_summary,
    }
