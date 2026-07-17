"""Model routing helpers for user-facing and internal model selection."""

from collections.abc import Iterable

from src.config import get_all_models, get_default_model_id, get_model_config, resolve_model_id
from src.config.llm_config import ModelConfig
from src.models.capability_profile import ModelCapabilityProfile, assess_profile_freshness

_ALL_CATEGORIES: tuple[str, ...] = ("llm", "image")


class InvalidRequestedModelError(ValueError):
    """Raised when an explicit user-selected model id is unknown or disallowed."""


def _current_profile(model: ModelConfig) -> ModelCapabilityProfile | None:
    profile = model.capability_profile
    evidence = model.capability_probe
    if profile is None or evidence is None:
        return None
    freshness = assess_profile_freshness(
        profile,
        evidence,
        model_id=model.id,
        model_name=model.model,
        base_url=model.base_url,
        generation_api=model.generation_api,
    )
    return profile if freshness.current else None


def _has_vision_capability(model: ModelConfig) -> bool:
    profile = _current_profile(model)
    return bool(profile and profile.vision)


def _has_strict_tool_capability(model: ModelConfig) -> bool:
    profile = _current_profile(model)
    return bool(profile and profile.has_strict_tools())


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
    allowed_categories: Iterable[str] = ("llm",),
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
    try:
        resolved = resolve_model_id(requested)
    except ValueError as exc:
        raise InvalidRequestedModelError(f"Unknown model id: {requested}") from exc

    model = get_model_config(resolved)
    if model is None:
        raise InvalidRequestedModelError(f"Unknown model id: {requested}")

    grouped = _grouped_models()
    category = _category_map(grouped).get(resolved)

    normalized_allowed = set(allowed_categories)
    if category not in normalized_allowed:
        expected = ", ".join(sorted(normalized_allowed)) or "no categories"
        raise InvalidRequestedModelError(
            f"Model '{requested}' is category '{category}' but this request allows: {expected}"
        )

    if require_tools and not _has_strict_tool_capability(model):
        raise InvalidRequestedModelError(
            f"Model '{requested}' has no current strict-tool capability probe"
        )

    if require_vision and not _has_vision_capability(model):
        raise InvalidRequestedModelError(
            f"Model '{requested}' does not support required vision inputs"
        )

    return requested


def get_model_category(model_id: str) -> str | None:
    """Get model category (llm/image) for a model id."""
    grouped = _grouped_models()
    return _category_map(grouped).get(model_id)


def list_user_selectable_models(
    *,
    purpose: str = "chat",
) -> list[ModelConfig]:
    """List models selectable by end users for a given purpose.

    Purposes:
    - ``chat``: text chat (llm)
    - ``writing``: long-form generation (llm)
    - ``image``: image generation only
    - ``all``: all user-facing categories (llm + image)
    """
    grouped = _grouped_models()
    if purpose == "image":
        return list(grouped.get("image", []))
    if purpose == "all":
        llm_models = grouped.get("llm", [])
        image_models = grouped.get("image", [])
        seen: set[str] = set()
        result: list[ModelConfig] = []
        for model in (*llm_models, *image_models):
            if model.id not in seen:
                seen.add(model.id)
                result.append(model)
        return result
    return list(grouped.get("llm", []))


def route_model(
    *,
    requested_model: str | None = None,
    thread_model: str | None = None,
    preferred_categories: Iterable[str] = ("llm",),
    allowed_categories: Iterable[str] = ("llm",),
    require_tools: bool = False,
    require_vision: bool = False,
) -> str:
    """Route to an effective model id using category and capability constraints."""
    grouped = _grouped_models()
    ordered_allowed = _ordered_allowed_categories(
        preferred_categories=preferred_categories,
        allowed_categories=allowed_categories,
    )
    if not ordered_allowed:
        raise ValueError("No allowed model categories configured for routing")
    allowed = set(ordered_allowed)

    category_by_id = _category_map(grouped)

    resolved_requested = _resolve_allowed_model_id(
        requested_model,
        allowed_categories=allowed,
        category_by_id=category_by_id,
    )
    if resolved_requested:
        _require_verified_capabilities(
            resolved_requested,
            require_tools=require_tools,
            require_vision=require_vision,
        )
        return resolved_requested
    if str(requested_model or "").strip():
        raise InvalidRequestedModelError(
            f"Requested model is unknown or outside the allowed categories: {requested_model}"
        )

    resolved_thread = _resolve_allowed_model_id(
        thread_model,
        allowed_categories=allowed,
        category_by_id=category_by_id,
    )
    if resolved_thread:
        _require_verified_capabilities(
            resolved_thread,
            require_tools=require_tools,
            require_vision=require_vision,
        )
        return resolved_thread
    if str(thread_model or "").strip():
        raise InvalidRequestedModelError(
            f"Thread model is unavailable or outside the allowed categories: {thread_model}"
        )

    # Pick the first model from allowed categories that satisfies constraints
    for category in ordered_allowed:
        for model in grouped.get(category, []):
            if require_tools and not _has_strict_tool_capability(model):
                continue
            if require_vision and not _has_vision_capability(model):
                continue
            return model.id

    # Use the default only when it satisfies the same verified constraints.
    fallback = get_default_model_id()
    fallback_category = category_by_id.get(fallback)
    fallback_model = get_model_config(fallback)
    if (
        fallback_category in allowed
        and fallback_model is not None
        and (not require_tools or _has_strict_tool_capability(fallback_model))
        and (not require_vision or _has_vision_capability(fallback_model))
    ):
        return fallback

    raise ValueError("No models configured for required routing categories")


def _ordered_allowed_categories(
    *,
    preferred_categories: Iterable[str],
    allowed_categories: Iterable[str],
) -> tuple[str, ...]:
    allowed = {
        category
        for category in allowed_categories
        if category in _ALL_CATEGORIES
    }
    ordered: list[str] = []
    for category in (*preferred_categories, *_ALL_CATEGORIES):
        if category in allowed and category not in ordered:
            ordered.append(category)
    return tuple(ordered)


def _require_verified_capabilities(
    model_id: str,
    *,
    require_tools: bool,
    require_vision: bool,
) -> None:
    model = get_model_config(model_id)
    if model is None:
        raise InvalidRequestedModelError(f"Unknown model id: {model_id}")
    if require_tools and not _has_strict_tool_capability(model):
        raise InvalidRequestedModelError(
            f"Model '{model_id}' has no current strict-tool capability probe"
        )
    if require_vision and not _has_vision_capability(model):
        raise InvalidRequestedModelError(
            f"Model '{model_id}' has no current vision capability probe"
        )


def route_chat_model(
    *,
    requested_model: str | None = None,
    thread_model: str | None = None,
    require_tools: bool = True,
    require_vision: bool = False,
) -> str:
    """Route text chat model from LLM models."""
    return route_model(
        requested_model=requested_model,
        thread_model=thread_model,
        preferred_categories=("llm",),
        allowed_categories=("llm",),
        require_tools=require_tools,
        require_vision=require_vision,
    )


def route_writing_model(
    *,
    requested_model: str | None = None,
) -> str:
    """Route writing model from LLM models."""
    return route_model(
        requested_model=requested_model,
        preferred_categories=("llm",),
        allowed_categories=("llm",),
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
    )
