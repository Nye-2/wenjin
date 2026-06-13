"""Diff helpers for LaTeX feedback rewrite preview/apply."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

TokenKind = Literal["text", "latex_cmd", "citation", "label", "math", "env"]
DiffOpKind = Literal["equal", "insert", "delete", "replace"]
RewriteDiffScope = Literal["selection", "section", "document"]

_TOKEN_PATTERN = re.compile(
    r"\\cite[a-zA-Z]*\{[^{}]*\}"
    r"|\\ref\{[^{}]*\}"
    r"|\\label\{[^{}]*\}"
    r"|\\begin\{[^{}]*\}"
    r"|\\end\{[^{}]*\}"
    r"|\\\[[\s\S]*?\\\]"
    r"|\\\([\s\S]*?\\\)"
    r"|\$\$[\s\S]*?\$\$"
    r"|\$[^$\n]*\$"
    r"|\\[a-zA-Z]+\*?"
    r"|\\."
    r"|\s+"
    r"|[^\s]+",
    re.DOTALL,
)
_CITATION_RE = re.compile(r"\\cite[a-zA-Z]*\{[^{}]*\}")
_LABEL_RE = re.compile(r"\\label\{[^{}]*\}")
_ESCAPED_BRACE_RE = re.compile(r"\\[{}]")


@dataclass(frozen=True)
class Token:
    text: str
    kind: TokenKind


def compute_content_hash(content: str) -> str:
    """Compute a stable hash for full file content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_range_hash(start: int, end: int, segment: str) -> str:
    """Compute a stable hash for the rewrite target range."""
    payload = f"{start}:{end}:{segment}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _classify_token(token: str) -> TokenKind:
    if token.startswith("\\cite"):
        return "citation"
    if token.startswith("\\label"):
        return "label"
    if token.startswith("\\begin{") or token.startswith("\\end{"):
        return "env"
    if token.startswith("$") or token.startswith("\\[") or token.startswith("\\("):
        return "math"
    if token.startswith("\\"):
        return "latex_cmd"
    return "text"


def tokenize_latex(text: str) -> list[Token]:
    """Tokenize LaTeX text into stable semantic-ish tokens."""
    tokens: list[Token] = []
    for match in _TOKEN_PATTERN.finditer(text):
        raw = match.group(0)
        if not raw:
            continue
        tokens.append(Token(text=raw, kind=_classify_token(raw)))
    return tokens


def _offsets(tokens: list[Token]) -> list[int]:
    result = [0]
    total = 0
    for token in tokens:
        total += len(token.text)
        result.append(total)
    return result


def _dominant_kind(left_tokens: list[Token], right_tokens: list[Token]) -> TokenKind:
    priority: dict[TokenKind, int] = {
        "citation": 6,
        "label": 5,
        "math": 4,
        "env": 3,
        "latex_cmd": 2,
        "text": 1,
    }
    kinds = [token.kind for token in left_tokens] + [token.kind for token in right_tokens]
    if not kinds:
        return "text"
    return max(kinds, key=lambda item: priority[item])


def _extract_items(pattern: re.Pattern[str], text: str) -> set[str]:
    return {match.group(0).strip() for match in pattern.finditer(text)}


def _brace_balance_score(text: str) -> int:
    stripped = _ESCAPED_BRACE_RE.sub("", text)
    return stripped.count("{") - stripped.count("}")


def _math_signature(text: str) -> tuple[int, int, int, int]:
    inline = len(re.findall(r"(?<!\\)\$", text))
    block = len(re.findall(r"\$\$", text))
    bracket = len(re.findall(r"\\\[|\\\]", text))
    paren = len(re.findall(r"\\\(|\\\)", text))
    return inline, block, bracket, paren


def _risk_flags(
    *,
    original_text: str,
    rewritten_text: str,
    scope: RewriteDiffScope,
    target_start: int,
    target_end: int,
    resolved_selection_start: int,
    resolved_selection_end: int,
) -> list[str]:
    flags: list[str] = []
    if scope == "selection" and (
        target_start != resolved_selection_start
        or target_end != resolved_selection_end
    ):
        flags.append("boundary_leak")

    old_citations = _extract_items(_CITATION_RE, original_text)
    new_citations = _extract_items(_CITATION_RE, rewritten_text)
    if old_citations - new_citations:
        flags.append("citation_drop")

    old_labels = _extract_items(_LABEL_RE, original_text)
    new_labels = _extract_items(_LABEL_RE, rewritten_text)
    if old_labels - new_labels:
        flags.append("label_drop")

    if _math_signature(original_text) != _math_signature(rewritten_text):
        flags.append("math_structure_change")

    if _brace_balance_score(rewritten_text) != 0:
        flags.append("brace_unbalanced")

    return flags


def build_latex_rewrite_diff(
    *,
    original_text: str,
    rewritten_text: str,
    target_start: int,
    scope: RewriteDiffScope,
    target_end: int,
    resolved_selection_start: int,
    resolved_selection_end: int,
) -> dict[str, object]:
    """Build structured hunks/ops/stats/risk flags for rewrite preview."""
    left_tokens = tokenize_latex(original_text)
    right_tokens = tokenize_latex(rewritten_text)
    left_text = [token.text for token in left_tokens]
    right_text = [token.text for token in right_tokens]
    left_offsets = _offsets(left_tokens)
    right_offsets = _offsets(right_tokens)
    matcher = SequenceMatcher(a=left_text, b=right_text, autojunk=False)

    total_stats = {
        "chars_added": 0,
        "chars_deleted": 0,
        "tokens_changed": 0,
        "citation_changed": 0,
        "label_changed": 0,
        "math_changed": 0,
    }

    hunks: list[dict[str, object]] = []
    grouped = matcher.get_grouped_opcodes(n=3)
    for group in grouped:
        if not group:
            continue
        first = group[0]
        last = group[-1]
        hunk_ops: list[dict[str, object]] = []
        hunk_stats = {
            "chars_added": 0,
            "chars_deleted": 0,
            "tokens_changed": 0,
            "citation_changed": 0,
            "label_changed": 0,
            "math_changed": 0,
        }
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                continue
            old_segment = "".join(left_text[i1:i2])
            new_segment = "".join(right_text[j1:j2])
            op_kind: DiffOpKind = "replace" if tag == "replace" else tag  # type: ignore[assignment]
            dominant = _dominant_kind(left_tokens[i1:i2], right_tokens[j1:j2])
            hunk_stats["tokens_changed"] += max(i2 - i1, j2 - j1)
            hunk_stats["chars_added"] += len(new_segment)
            hunk_stats["chars_deleted"] += len(old_segment)
            if dominant == "citation":
                hunk_stats["citation_changed"] += 1
            if dominant == "label":
                hunk_stats["label_changed"] += 1
            if dominant == "math":
                hunk_stats["math_changed"] += 1

            hunk_ops.append(
                {
                    "op": op_kind,
                    "token_kind": dominant,
                    "old_text": old_segment,
                    "new_text": new_segment,
                    "old_start": target_start + left_offsets[i1],
                    "old_end": target_start + left_offsets[i2],
                    "new_start": target_start + right_offsets[j1],
                    "new_end": target_start + right_offsets[j2],
                }
            )

        for key in total_stats:
            total_stats[key] += hunk_stats[key]

        hunk_risk_flags: list[str] = []
        if hunk_stats["citation_changed"] > 0:
            hunk_risk_flags.append("citation_change")
        if hunk_stats["label_changed"] > 0:
            hunk_risk_flags.append("label_change")
        if hunk_stats["math_changed"] > 0:
            hunk_risk_flags.append("math_change")
        if hunk_stats["tokens_changed"] > 80:
            hunk_risk_flags.append("large_change")

        hunks.append(
            {
                "old_start": target_start + left_offsets[first[1]],
                "old_end": target_start + left_offsets[last[2]],
                "new_start": target_start + right_offsets[first[3]],
                "new_end": target_start + right_offsets[last[4]],
                "ops": hunk_ops,
                "stats": hunk_stats,
                "risk_flags": hunk_risk_flags,
            }
        )

    risk_flags = _risk_flags(
        original_text=original_text,
        rewritten_text=rewritten_text,
        scope=scope,
        target_start=target_start,
        target_end=target_end,
        resolved_selection_start=resolved_selection_start,
        resolved_selection_end=resolved_selection_end,
    )
    return {
        "hunks": hunks,
        "stats": total_stats,
        "risk_flags": risk_flags,
    }
