"""Model routing helpers for user-facing and internal model selection."""

from collections.abc import Iterable

from src.config import get_all_models, get_default_model_id, get_model_config, resolve_model_id
from src.config.llm_config import ModelConfig

_ALL_CATEGORIES: tuple[str, ...] = ("llm", "image")
_VISION_HINT_TAGS: tuple[str, ...] = ("vision", "vl")
_THINKING_HINT_PREFIXES: tuple[str, ...] = ("claude", "deepseek-")
_REASONING_HINT_TAGS: tuple[str, ...] = ("gpt-5", "doubao")


class InvalidRequestedModelError(ValueError):
    """Raised when an explicit user-selected model id is unknown or disallowed."""


def _supports_vision_raw(raw_model: str) -> bool:
    normalized = raw_model.lower().strip()
    if not normalized:
        return False
    return any(tag in normalized for tag in _VISION_HINT_TAGS)


def _supports_thinking_raw(raw_model: str) -> bool:
    normalized = raw_model.lower().strip()
    if not normalized:
        return False
    return normalized.startswith(_THINKING_HINT_PREFIXES)


def _supports_reasoning_effort_raw(raw_model: str) -> bool:
    normalized = raw_model.lower().strip()
    if not normalized:
        return False
    return any(tag in normalized for tag in _REASONING_HINT_TAGS)


def _supports_vision(model: ModelConfig) -> bool:
    if getattr(model, "supports_vision", False):
        return True
    raw_model = (model.model or "").lower()
    return _supports_vision_raw(raw_model)


def _supports_thinking(model: ModelConfig) -> bool:
    if getattr(model, "supports_thinking", False):
        return True
    raw_model = (model.model or "").lower()
    return _supports_thinking_raw(raw_model)


def _supports_reasoning_effort(model: ModelConfig) -> bool:
    if getattr(model, "supports_reasoning_effort", False):
        return True
    raw_model = (model.model or "").lower()
    return _supports_reasoning_effort_raw(raw_model)


def model_supports_vision(model_id_or_name: str | None) -> bool:
    """Return whether a model supports vision inputs."""
    normalized = (model_id_or_name or "").strip()
    if not normalized:
        return False

    model = get_model_config(normalized)
    if model is not None:
        return _supports_vision(model)

    return _supports_vision_raw(normalized)


def model_supports_thinking(model_id_or_name: str | None) -> bool:
    """Return whether a model supports visible thinking/reasoning traces."""
    normalized = (model_id_or_name or "").strip()
    if not normalized:
        return False

    model = get_model_config(normalized)
    if model is not None:
        return _supports_thinking(model)

    return _supports_thinking_raw(normalized)


def model_supports_reasoning_effort(model_id_or_name: str | None) -> bool:
    """Return whether a model supports reasoning_effort."""
    normalized = (model_id_or_name or "").strip()
    if not normalized:
        return False

    model = get_model_config(normalized)
    if model is not None:
        return _supports_reasoning_effort(model)

    return _supports_reasoning_effort_raw(normalized)


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
    if requested == "default":
        return requested

    model = get_model_config(requested)
    if model is None:
        raise InvalidRequestedModelError(f"Unknown model id: {requested}")

    grouped = _grouped_models()
    category = _category_map(grouped).get(requested)

    normalized_allowed = set(allowed_categories)
    is_image_task = normalized_allowed == {"image"}
    is_llm_task = "llm" in normalized_allowed

    if is_image_task and category != "image":
        raise InvalidRequestedModelError(
            f"Model '{requested}' is not an image model and cannot be used for image tasks"
        )
    if is_llm_task and category == "image":
        raise InvalidRequestedModelError(
            f"Model '{requested}' is an image model and cannot be used for non-image tasks"
        )

    if require_tools and not model.supports_tools:
        raise InvalidRequestedModelError(
            f"Model '{requested}' does not support required tool execution"
        )

    if require_vision and not _supports_vision(model):
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
    allowed = {c for c in allowed_categories if c in _ALL_CATEGORIES}
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

    # Pick the first model from allowed categories that satisfies constraints
    for category in allowed:
        for model in grouped.get(category, []):
            if require_tools and not model.supports_tools:
                continue
            if require_vision and not _supports_vision(model):
                continue
            return model.id

    # Fallback to default model if it belongs to an allowed category
    fallback = get_default_model_id()
    fallback_category = category_by_id.get(fallback)
    if fallback_category in allowed:
        return fallback

    raise ValueError("No models configured for required routing categories")


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
