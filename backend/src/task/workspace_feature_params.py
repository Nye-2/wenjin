"""Workspace feature param helpers.

Workspace feature task payloads must keep business params exclusively under
``payload["params"]``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def coerce_workspace_feature_params(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Read canonical workspace feature params from ``payload['params']``."""
    if not isinstance(payload, Mapping):
        return {}

    params = payload.get("params")
    if isinstance(params, Mapping):
        return dict(params)
    return {}
