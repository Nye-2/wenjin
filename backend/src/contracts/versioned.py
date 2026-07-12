"""Canonical hashing primitives for immutable runtime contracts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ImmutableContractRef(BaseModel):
    """A content-addressed reference recorded by MissionRun and MissionItem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    schema_version: str
    sha256: str

    @field_validator("contract_id", "schema_version")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("contract references require non-empty identifiers")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        return value


class ImmutableContentRef(BaseModel):
    """A content-addressed reference for exemplars and bounded resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref_id: str
    sha256: str

    @field_validator("ref_id")
    @classmethod
    def validate_ref_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content references require ref_id")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be a 64-character lowercase hex digest")
        return value


def canonical_contract_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    """Serialize contract data deterministically for hashing and pinning."""

    payload = value.model_dump(mode="json", exclude_none=True) if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def contract_sha256(value: BaseModel | dict[str, Any]) -> str:
    return hashlib.sha256(canonical_contract_bytes(value)).hexdigest()
