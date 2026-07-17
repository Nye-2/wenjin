"""Hash-bound references to an exact Prism text selection."""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrismContextRef(BaseModel):
    """Locate one selection using UTF-8 byte offsets against an immutable revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=120)
    prism_project_id: str = Field(min_length=1, max_length=120)
    file_id: str = Field(min_length=1, max_length=120)
    base_revision_ref: str = Field(min_length=1, max_length=2048)
    selection_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_byte_range: tuple[int, int]

    @field_validator("selection_byte_range")
    @classmethod
    def _validate_selection_locator(cls, value: tuple[int, int]) -> tuple[int, int]:
        start, end = value
        if start < 0 or end <= start:
            raise ValueError("selection_byte_range must be a non-empty forward range")
        return value


def split_utf8_selection(
    content: str,
    selection_byte_range: tuple[int, int],
) -> tuple[str, str, str]:
    """Split text at exact UTF-8 boundaries, rejecting stale or malformed offsets."""

    encoded = content.encode("utf-8")
    start, end = selection_byte_range
    if start < 0 or end <= start or end > len(encoded):
        raise ValueError("Prism selection is outside the current file")
    try:
        prefix = encoded[:start].decode("utf-8")
        selection = encoded[start:end].decode("utf-8")
        suffix = encoded[end:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Prism selection does not align to UTF-8 boundaries") from exc
    return prefix, selection, suffix


def prism_selection_hash(selection: str) -> str:
    return f"sha256:{hashlib.sha256(selection.encode('utf-8')).hexdigest()}"


__all__ = ["PrismContextRef", "prism_selection_hash", "split_utf8_selection"]
