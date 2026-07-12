"""Deterministic staleness review for workspace memory prompt injection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class MemoryFactStatus(StrEnum):
    CURRENT = "current"
    CONFLICTING = "conflicting"
    EXPIRED = "expired"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True, slots=True)
class MemoryFact:
    section: str
    content: str


@dataclass(frozen=True, slots=True)
class ReviewedMemoryFact:
    fact: MemoryFact
    status: MemoryFactStatus
    reason: str


@dataclass(frozen=True, slots=True)
class MemoryStalenessReview:
    facts: tuple[ReviewedMemoryFact, ...]

    @property
    def current(self) -> tuple[ReviewedMemoryFact, ...]:
        return tuple(item for item in self.facts if item.status == MemoryFactStatus.CURRENT)

    @property
    def attention(self) -> tuple[ReviewedMemoryFact, ...]:
        return tuple(item for item in self.facts if item.status != MemoryFactStatus.CURRENT)


_STABLE_SECTIONS = frozenset({"user preferences", "working constraints"})
_EXPLICIT_EXPIRED_RE = re.compile(
    r"(?:\[\s*status\s*:\s*expired\s*\]|已过期|已失效|已废弃|已取消|不再适用)",
    re.IGNORECASE,
)
_EXPIRY_DATE_RE = re.compile(
    r"(?:\[\s*(?:expires|valid[_ -]?until)\s*:\s*|有效期至\s*|截止(?:日期)?(?:为|至)\s*)"
    r"(?P<date>\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s*\]?",
    re.IGNORECASE,
)
_CORRECTION_MARKER_RE = re.compile(
    r"(?:不再|不要|改为|改成|换成|更换为|更新为|现在(?:用|使用|采用|目标)|instead of|no longer|switch(?:ed)? to)",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_.+-]{1,}|[\u4e00-\u9fff]{2,}")
_SLOT_PATTERNS: dict[str, re.Pattern[str]] = {
    "target_venue": re.compile(
        r"(?:目标期刊|投稿期刊|目标会议|投稿会议)\s*(?:是|为|设为|改为|改成|换成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
    "citation_style": re.compile(
        r"(?:引用格式|引用风格|参考文献格式|citation style)\s*(?:是|为|采用|使用|改为|改成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
    "language": re.compile(
        r"(?:写作语言|论文语言|输出语言)\s*(?:是|为|采用|使用|改为|改成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
    "research_topic": re.compile(
        r"(?:研究方向|研究主题|论文主题|当前选题|选题)\s*(?:是|为|聚焦|改为|改成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
    "model": re.compile(
        r"(?:模型|基座模型|model)\s*(?:是|为|采用|使用|改用|改为|改成|换成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
    "dataset": re.compile(
        r"(?:数据集|实验数据|dataset)\s*(?:是|为|采用|使用|改用|改为|改成|换成|:|：)?\s*([^，。；;\n]+)",
        re.IGNORECASE,
    ),
}


def review_workspace_memory(
    content_markdown: str | None,
    *,
    current_context: str | None,
    today: date | None = None,
) -> MemoryStalenessReview:
    """Classify stored facts without mutating or re-authoring memory."""

    context = _normalize_text(current_context)
    context_slots = _extract_slots(context)
    reviewed = tuple(
        _review_fact(
            fact,
            context=context,
            context_slots=context_slots,
            today=today or date.today(),
        )
        for fact in parse_workspace_memory_facts(content_markdown)
    )
    return MemoryStalenessReview(facts=reviewed)


def parse_workspace_memory_facts(content_markdown: str | None) -> tuple[MemoryFact, ...]:
    """Parse the canonical sectioned Markdown into bounded, atomic facts."""

    facts: list[MemoryFact] = []
    section = "Project Context"
    for raw_line in str(content_markdown or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            section = line[3:].strip() or section
            continue
        content = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        if not content or content == "...":
            continue
        facts.append(MemoryFact(section=section[:100], content=content[:1000]))
        if len(facts) >= 100:
            break
    return tuple(facts)


def _review_fact(
    fact: MemoryFact,
    *,
    context: str,
    context_slots: dict[str, str],
    today: date,
) -> ReviewedMemoryFact:
    if _is_expired(fact.content, today=today):
        return ReviewedMemoryFact(fact, MemoryFactStatus.EXPIRED, "stored fact is explicitly expired")

    fact_text = _normalize_text(fact.content)
    fact_slots = _extract_slots(fact_text)
    for slot, fact_value in fact_slots.items():
        context_value = context_slots.get(slot)
        if context_value is None:
            continue
        if _values_compatible(fact_value, context_value):
            return ReviewedMemoryFact(fact, MemoryFactStatus.CURRENT, f"confirmed by current {slot}")
        return ReviewedMemoryFact(fact, MemoryFactStatus.CONFLICTING, f"current {slot} differs")

    if context and _CORRECTION_MARKER_RE.search(context) and _shares_subject(fact_text, context):
        return ReviewedMemoryFact(
            fact,
            MemoryFactStatus.CONFLICTING,
            "current conversation explicitly replaces related information",
        )

    if context and _is_reconfirmed(fact_text, context):
        return ReviewedMemoryFact(fact, MemoryFactStatus.CURRENT, "reconfirmed by current context")

    if fact.section.strip().lower() in _STABLE_SECTIONS:
        return ReviewedMemoryFact(fact, MemoryFactStatus.CURRENT, "stable preference or constraint")

    return ReviewedMemoryFact(
        fact,
        MemoryFactStatus.NEEDS_CONFIRMATION,
        "project information was not confirmed by the current objective",
    )


def _is_expired(content: str, *, today: date) -> bool:
    if _EXPLICIT_EXPIRED_RE.search(content):
        return True
    match = _EXPIRY_DATE_RE.search(content)
    if match is None:
        return False
    normalized = re.sub(r"[/.年月]", "-", match.group("date")).rstrip("日-")
    try:
        return date.fromisoformat(normalized) < today
    except ValueError:
        return False


def _extract_slots(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    for name, pattern in _SLOT_PATTERNS.items():
        matches = list(pattern.finditer(text))
        if matches:
            slots[name] = _normalize_value(matches[-1].group(1))
    return slots


def _values_compatible(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _shares_subject(left: str, right: str) -> bool:
    left_tokens = _meaningful_tokens(left)
    right_tokens = _meaningful_tokens(right)
    common = left_tokens & right_tokens
    if any(re.fullmatch(r"[a-z][a-z0-9_.+-]{3,}", token) for token in common):
        return True
    return len(common) >= 2 and len(common) / max(1, len(left_tokens)) >= 0.25


def _is_reconfirmed(left: str, right: str) -> bool:
    normalized_left = _normalize_value(left)
    normalized_right = _normalize_value(right)
    if normalized_left and normalized_left in normalized_right:
        return True
    left_tokens = _meaningful_tokens(left)
    common = left_tokens & _meaningful_tokens(right)
    return len(common) >= 2 and len(common) / max(1, len(left_tokens)) >= 0.6


def _meaningful_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for match in _WORD_RE.finditer(text.lower()):
        token = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.update(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.add(token)
    return tokens


def _normalize_value(value: str) -> str:
    value = _CORRECTION_MARKER_RE.sub("", value)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").split())
