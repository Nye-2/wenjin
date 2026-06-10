"""Research evidence surface declarations and capability-policy parsing."""

from __future__ import annotations

from typing import Any, Literal, cast, get_args

ResearchSurface = Literal[
    "literature",
    "experiment",
    "writing",
    "workflow_trace",
    "citation_strength",
    "experiment_interpretation",
    "paper_relevance",
    "statistical_robustness",
    "writing_semantic_preservation",
    "writing_academic_style",
    "output_ref_reuse",
]

DEFAULT_RESEARCH_SURFACES: tuple[ResearchSurface, ...] = ("literature", "experiment", "writing")
KNOWN_RESEARCH_SURFACES = frozenset(str(item) for item in get_args(ResearchSurface))


def required_surfaces_from_capability_policy(
    capability_policy: dict[str, Any] | None,
    *,
    default: tuple[ResearchSurface, ...] = DEFAULT_RESEARCH_SURFACES,
) -> tuple[ResearchSurface, ...]:
    """Read deterministic research evidence surfaces from capability policy."""

    policy = capability_policy if isinstance(capability_policy, dict) else {}
    research_evidence = policy.get("research_evidence")
    research_evidence = research_evidence if isinstance(research_evidence, dict) else {}
    raw_surfaces = _string_list(research_evidence.get("required_surfaces"))
    if not raw_surfaces:
        return default

    invalid = [surface for surface in raw_surfaces if surface not in KNOWN_RESEARCH_SURFACES]
    if invalid:
        raise ValueError(f"unknown research evidence surfaces: {', '.join(_unique(invalid))}")

    return tuple(cast(ResearchSurface, surface) for surface in _unique(raw_surfaces))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set | frozenset):
        raw = list(value)
    else:
        return []
    return _unique([text for item in raw for text in (_clean_text(item),) if text])


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""
