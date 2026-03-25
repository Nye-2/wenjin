"""Execution capability checks used by workspace features."""

from __future__ import annotations

from src.config.llm_config import get_model_full_config
from src.models.router import route_image_model

from .types import ExecutionType


def execution_type_readiness(
    execution_service: object,
    execution_type: ExecutionType,
) -> tuple[bool, str | None]:
    """Check whether an execution type is actually runnable."""
    provider_map = getattr(execution_service, "PROVIDER_MAP", None)
    if not isinstance(provider_map, dict) or execution_type not in provider_map:
        return False, f"provider for {execution_type.value} is not registered"

    if execution_type != ExecutionType.AI_IMAGE:
        return True, None

    try:
        model_id = route_image_model(requested_model=None)
        config = get_model_full_config(model_id)
    except Exception as exc:
        return False, f"image model unavailable: {exc}"

    missing = [
        key
        for key in ("base_url", "api_key", "model")
        if not str(config.get(key) or "").strip()
    ]
    if missing:
        return False, f"image model config missing: {', '.join(missing)}"

    return True, None

