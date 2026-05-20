"""Idempotency helpers for DataService commands."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def make_request_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 hash for a command payload."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class IdempotencyScope(BaseModel):
    """Logical uniqueness scope for a DataService command."""

    source_service: str = Field(min_length=1, max_length=80)
    command_name: str = Field(min_length=1, max_length=120)
    workspace_id: str | None = None
    actor_user_id: str | None = None


def make_scope_hash(scope: IdempotencyScope) -> str:
    """Return a deterministic scope hash.

    The persisted hash avoids nullable-column uniqueness pitfalls while keeping
    the human-readable scope fields queryable for operations and debugging.
    """
    return hashlib.sha256(scope.model_dump_json(exclude_none=False).encode("utf-8")).hexdigest()
