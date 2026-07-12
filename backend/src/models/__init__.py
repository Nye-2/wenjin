"""Public model-routing surface with lazy imports.

Capability contracts are imported by DataService models, so eager imports here
would create a package cycle through ``config.llm_config``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "create_chat_model": ("src.models.factory", "create_chat_model"),
    "get_model_category": ("src.models.router", "get_model_category"),
    "list_user_selectable_models": ("src.models.router", "list_user_selectable_models"),
    "model_supports_reasoning_effort": ("src.models.router", "model_supports_reasoning_effort"),
    "model_supports_thinking": ("src.models.router", "model_supports_thinking"),
    "model_supports_vision": ("src.models.router", "model_supports_vision"),
    "route_chat_model": ("src.models.router", "route_chat_model"),
    "route_image_model": ("src.models.router", "route_image_model"),
    "route_model": ("src.models.router", "route_model"),
    "route_writing_model": ("src.models.router", "route_writing_model"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
