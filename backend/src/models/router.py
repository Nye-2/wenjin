"""Model routing helpers for user-facing and internal model selection."""

from collections.abc import Iterable

from src.config import get_all_models, get_default_model_id, get_model_config, resolve_model_id
from src.config.llm_config import ModelConfig

_ALL_CATEGORIES: tuple[str, ...] = ("tool", "gen", "utility", "image")
_USER_TEXT_CATEGORIES: tuple[str, ...] = ("tool", "gen")
_WRITING_TEXT_CATEGORIES: tuple[str, ...] = ("gen", "tool")
_USER_ALL_CATEGORIES: tuple[str, ...] = ("tool", "gen", "image")


class InvalidRequestedModelError(ValueError):
    """Raised when an explicit user-selected model id is unknown or disallowed."""


def _supports_vision(model: ModelConfig) -> bool:
    raw_model = (model.model or "").lower()
    return any(tag in raw_model for tag in ("vision", "vl", "gpt-4o"))


def _grouped_models() -> dict[str, list[ModelConfig]]:
    grouped = get_all_models()
    return {
        category: list(grouped.get(category, []))
        for category in _ALL_CATEGORIES
    }


def _category_map(grouped: dict[str, list[ModelConfig]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for category in _ALL_CATEGORIES:
        for model in grouped.get(category, []):
            mapping.setdefault(model.id, category)
    return mapping


def _ordered_categories(
    preferred_categories: Iterable[str],
    allowed_categories: set[str],
) -> list[str]:
    ordered: list[str] = []
    for category in preferred_categories:
        if category in allowed_categories and category not in ordered:
            ordered.append(category)
    for category in _ALL_CATEGORIES:
        if category in allowed_categories and category not in ordered:
            ordered.append(category)
    return ordered


def _iter_candidates(
    grouped: dict[str, list[ModelConfig]],
    *,
    preferred_categories: Iterable[str],
    allowed_categories: set[str],
    require_tools: bool,
    require_vision: bool,
) -> list[ModelConfig]:
    ordered_categories = _ordered_categories(preferred_categories, allowed_categories)
    candidates: list[ModelConfig] = []
    seen: set[str] = set()

    for category in ordered_categories:
        for model in grouped.get(category, []):
            if model.id in seen:
                continue
            seen.add(model.id)

            if require_tools and not (model.supports_tools or category == "tool"):
                continue
            if require_vision and not _supports_vision(model):
                continue
            candidates.append(model)

    return candidates


def _resolve_allowed_model_id(
    raw_model_id: str | None,
    *,
    allowed_categories: set[str],
    category_by_id: dict[str, str],
) -> str | None:
    requested = (raw_model_id or "").strip()
    if not requested:
        return None

    try:
        resolved_id = resolve_model_id(requested)
    except ValueError:
        return None
    category = category_by_id.get(resolved_id)
    if category is None or category not in allowed_categories:
        return None
    return resolved_id


def validate_requested_model(
    raw_model_id: str | None,
    *,
    allowed_categories: Iterable[str] = _USER_TEXT_CATEGORIES,
    require_tools: bool = False,
    require_vision: bool = False,
) -> str | None:
    """Validate an explicit user-selected model id without silently rerouting it.

    This helper is intended for request-entry validation. Automatic routing may still
    choose defaults when no explicit model was selected, but once a user provides a
    model id we either honor that exact selection (including the ``default`` alias)
    or raise an explicit error.
    """
    requested = (raw_model_id or "").strip()
    if not requested:
        return None
    if requested == "default":
        return requested

    model = get_model_config(requested)
    if model is None:
        raise InvalidRequestedModelError(f"Unknown model id: {requested}")

    grouped = _grouped_models()
    allowed = {category for category in allowed_categories if category in _ALL_CATEGORIES}
    category = _category_map(grouped).get(requested)
    if category is None or category not in allowed:
        allowed_text = ", ".join(sorted(allowed)) or "none"
        raise InvalidRequestedModelError(
            f"Model '{requested}' is not allowed for categories: {allowed_text}"
        )

    if require_tools and not (model.supports_tools or category == "tool"):
        raise InvalidRequestedModelError(
            f"Model '{requested}' does not support required tool execution"
        )

    if require_vision and not _supports_vision(model):
        raise InvalidRequestedModelError(
            f"Model '{requested}' does not support required vision inputs"
        )

    return requested


def get_model_category(model_id: str) -> str | None:
    """Get model category (tool/gen/utility/image) for a model id."""
    grouped = _grouped_models()
    return _category_map(grouped).get(model_id)


def list_user_selectable_models(
    *,
    purpose: str = "chat",
) -> list[ModelConfig]:
    """List models selectable by end users for a given purpose.

    Purposes:
    - ``chat``: text chat (tool + gen, tool-first)
    - ``writing``: long-form generation (gen + tool, gen-first)
    - ``image``: image generation only
    - ``all``: all user-facing categories (tool + gen + image)
    """
    grouped = _grouped_models()
    if purpose == "writing":
        preferred = _WRITING_TEXT_CATEGORIES
        allowed = set(_USER_TEXT_CATEGORIES)
    elif purpose == "image":
        preferred = ("image",)
        allowed = {"image"}
    elif purpose == "all":
        preferred = ("tool", "gen", "image")
        allowed = set(_USER_ALL_CATEGORIES)
    else:
        preferred = _USER_TEXT_CATEGORIES
        allowed = set(_USER_TEXT_CATEGORIES)

    return _iter_candidates(
        grouped,
        preferred_categories=preferred,
        allowed_categories=allowed,
        require_tools=False,
        require_vision=False,
    )


def route_model(
    *,
    requested_model: str | None = None,
    thread_model: str | None = None,
    preferred_categories: Iterable[str] = _USER_TEXT_CATEGORIES,
    allowed_categories: Iterable[str] = _USER_TEXT_CATEGORIES,
    require_tools: bool = False,
    require_vision: bool = False,
) -> str:
    """Route to an effective model id using category and capability constraints."""
    grouped = _grouped_models()
    allowed = {category for category in allowed_categories if category in _ALL_CATEGORIES}
    if not allowed:
        raise ValueError("No allowed model categories configured for routing")

    category_by_id = _category_map(grouped)

    resolved_requested = _resolve_allowed_model_id(
        requested_model,
        allowed_categories=allowed,
        category_by_id=category_by_id,
    )
    if resolved_requested:
        return resolved_requested

    resolved_thread = _resolve_allowed_model_id(
        thread_model,
        allowed_categories=allowed,
        category_by_id=category_by_id,
    )
    if resolved_thread:
        return resolved_thread

    candidates = _iter_candidates(
        grouped,
        preferred_categories=preferred_categories,
        allowed_categories=allowed,
        require_tools=require_tools,
        require_vision=require_vision,
    )
    if candidates:
        return candidates[0].id

    fallback = get_default_model_id()
    fallback_category = category_by_id.get(fallback)
    if fallback_category in allowed:
        return fallback

    relaxed_candidates = _iter_candidates(
        grouped,
        preferred_categories=preferred_categories,
        allowed_categories=allowed,
        require_tools=False,
        require_vision=False,
    )
    if relaxed_candidates:
        return relaxed_candidates[0].id

    raise ValueError("No models configured for required routing categories")


def route_chat_model(
    *,
    requested_model: str | None = None,
    thread_model: str | None = None,
    require_tools: bool = True,
    require_vision: bool = False,
) -> str:
    """Route text chat model (tool-first, utility excluded from selection)."""
    return route_model(
        requested_model=requested_model,
        thread_model=thread_model,
        preferred_categories=_USER_TEXT_CATEGORIES,
        allowed_categories=_USER_TEXT_CATEGORIES,
        require_tools=require_tools,
        require_vision=require_vision,
    )


def route_writing_model(
    *,
    requested_model: str | None = None,
) -> str:
    """Route writing model (gen-first, then tool, utility excluded)."""
    return route_model(
        requested_model=requested_model,
        preferred_categories=_WRITING_TEXT_CATEGORIES,
        allowed_categories=_USER_TEXT_CATEGORIES,
        require_tools=False,
        require_vision=False,
    )


def route_image_model(
    *,
    requested_model: str | None = None,
) -> str:
    """Route image generation model."""
    return route_model(
        requested_model=requested_model,
        preferred_categories=("image",),
        allowed_categories=("image",),
        require_tools=False,
        require_vision=False,
    )
