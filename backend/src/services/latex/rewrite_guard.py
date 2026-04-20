"""Strict structural guardrails for LaTeX rewrite preview/apply."""

from __future__ import annotations

import re
from typing import Literal

_CITATION_RE = re.compile(r"\\cite[a-zA-Z]*\{[^{}]*\}")
_LABEL_RE = re.compile(r"\\label\{[^{}]*\}")
_REF_RE = re.compile(r"\\ref\{[^{}]*\}")
_ENV_RE = re.compile(r"\\(begin|end)\{([^{}]+)\}")
_VERBATIM_BLOCK_RE = re.compile(
    r"\\begin\{(?P<env>verbatim\*?|lstlisting|minted|Verbatim)\}"
    r"(?:\[[^\]]*\])?"
    r"(?:\{[^{}]*\})*"
    r"[\s\S]*?"
    r"\\end\{(?P=env)\}",
    re.IGNORECASE,
)


class LatexStructureValidationError(ValueError):
    """Raised when rewrite content violates strict structural constraints."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _strip_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines(keepends=True):
        cut = len(line)
        for idx, char in enumerate(line):
            if char == "%" and not _is_escaped(line, idx):
                cut = idx
                break
        lines.append(line[:cut] + ("\n" if line.endswith("\n") else ""))
    return "".join(lines)


def _strip_verbatim_blocks(text: str) -> str:
    return _VERBATIM_BLOCK_RE.sub("", text)


def _validate_brace_balance(text: str) -> None:
    sanitized = _strip_verbatim_blocks(text)
    depth = 0
    in_comment = False
    for index, char in enumerate(sanitized):
        if in_comment:
            if char == "\n":
                in_comment = False
            continue
        if char == "%" and not _is_escaped(sanitized, index):
            in_comment = True
            continue
        if char == "{" and not _is_escaped(sanitized, index):
            depth += 1
            continue
        if char == "}" and not _is_escaped(sanitized, index):
            depth -= 1
            if depth < 0:
                raise LatexStructureValidationError(
                    code="brace_unbalanced",
                    message="Detected unmatched closing brace.",
                )
    if depth != 0:
        raise LatexStructureValidationError(
            code="brace_unbalanced",
            message="Detected unmatched opening brace.",
        )


def _validate_environment_stack(text: str) -> None:
    stripped = _strip_comments(_strip_verbatim_blocks(text))
    stack: list[str] = []
    for match in _ENV_RE.finditer(stripped):
        op = str(match.group(1) or "")
        env_name = str(match.group(2) or "").strip()
        if not env_name:
            continue
        if op == "begin":
            stack.append(env_name)
            continue
        if not stack:
            raise LatexStructureValidationError(
                code="environment_unbalanced",
                message=f"Detected unmatched \\end{{{env_name}}}.",
            )
        expected = stack.pop()
        if expected != env_name:
            raise LatexStructureValidationError(
                code="environment_unbalanced",
                message=f"Environment mismatch: expected \\end{{{expected}}}, got \\end{{{env_name}}}.",
            )
    if stack:
        raise LatexStructureValidationError(
            code="environment_unbalanced",
            message=f"Detected unmatched \\begin{{{stack[-1]}}}.",
        )


def _validate_math_delimiters(text: str) -> None:
    stripped = _strip_comments(_strip_verbatim_blocks(text))
    inline_open = False
    block_open = False
    bracket_depth = 0
    paren_depth = 0
    index = 0

    while index < len(stripped):
        if stripped.startswith("\\[", index):
            bracket_depth += 1
            index += 2
            continue
        if stripped.startswith("\\]", index):
            bracket_depth -= 1
            if bracket_depth < 0:
                raise LatexStructureValidationError(
                    code="math_delimiter_unbalanced",
                    message="Detected unmatched \\].",
                )
            index += 2
            continue
        if stripped.startswith("\\(", index):
            paren_depth += 1
            index += 2
            continue
        if stripped.startswith("\\)", index):
            paren_depth -= 1
            if paren_depth < 0:
                raise LatexStructureValidationError(
                    code="math_delimiter_unbalanced",
                    message="Detected unmatched \\).",
                )
            index += 2
            continue

        char = stripped[index]
        if char == "$" and not _is_escaped(stripped, index):
            if stripped.startswith("$$", index):
                block_open = not block_open
                index += 2
                continue
            if not block_open:
                inline_open = not inline_open
            index += 1
            continue
        index += 1

    if inline_open or block_open or bracket_depth != 0 or paren_depth != 0:
        raise LatexStructureValidationError(
            code="math_delimiter_unbalanced",
            message="Detected unbalanced math delimiters.",
        )


def _extract_items(pattern: re.Pattern[str], text: str) -> set[str]:
    return {match.group(0).strip() for match in pattern.finditer(text)}


def _validate_reference_preservation(original_text: str, rewritten_text: str) -> None:
    old_citations = _extract_items(_CITATION_RE, original_text)
    new_citations = _extract_items(_CITATION_RE, rewritten_text)
    if old_citations - new_citations:
        raise LatexStructureValidationError(
            code="citation_drop",
            message="Rewrite removed existing citation markers.",
        )

    old_labels = _extract_items(_LABEL_RE, original_text)
    new_labels = _extract_items(_LABEL_RE, rewritten_text)
    if old_labels - new_labels:
        raise LatexStructureValidationError(
            code="label_drop",
            message="Rewrite removed existing label markers.",
        )

    old_refs = _extract_items(_REF_RE, original_text)
    new_refs = _extract_items(_REF_RE, rewritten_text)
    if old_refs - new_refs:
        raise LatexStructureValidationError(
            code="ref_drop",
            message="Rewrite removed existing reference markers.",
        )


def validate_rewrite_segment(
    *,
    original_text: str,
    rewritten_text: str,
    scope: Literal["selection", "section"] | None = None,
    target_start: int | None = None,
    target_end: int | None = None,
    resolved_selection_start: int | None = None,
    resolved_selection_end: int | None = None,
) -> None:
    """Validate segment-level safety for rewrite candidates."""
    if scope == "selection":
        if (
            target_start is None
            or target_end is None
            or resolved_selection_start is None
            or resolved_selection_end is None
            or target_start != resolved_selection_start
            or target_end != resolved_selection_end
        ):
            raise LatexStructureValidationError(
                code="boundary_leak",
                message="Selection rewrite expanded outside requested range.",
            )

    _validate_brace_balance(rewritten_text)
    _validate_math_delimiters(rewritten_text)
    _validate_reference_preservation(original_text, rewritten_text)


def validate_latex_document_structure(content: str) -> None:
    """Validate full-document structural safety after applying rewrite."""
    _validate_brace_balance(content)
    _validate_environment_stack(content)
    _validate_math_delimiters(content)
