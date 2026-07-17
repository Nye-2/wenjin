"""Ephemeral authority for one fenced Mission target write."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MissionWriteAuthority(BaseModel):
    """Bind one target-domain transaction to the active commit attempt."""

    mission_id: str = Field(min_length=1, max_length=36)
    mission_review_item_id: str = Field(min_length=1, max_length=36)
    mission_commit_id: str = Field(min_length=1, max_length=36)
    attempt_token: str = Field(min_length=16, max_length=160)


__all__ = ["MissionWriteAuthority"]
