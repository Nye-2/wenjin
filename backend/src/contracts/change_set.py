"""Workspace write review ChangeSet contracts."""

from __future__ import annotations

from typing import Any, Literal, Self, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WriteMode = Literal["auto_draft", "ask_workspace_write", "strict_review"]
ChangeRisk = Literal["low", "medium", "high", "critical"]
ApplyState = Literal["draft_applied", "staged", "accepted", "rejected", "blocked", "undone"]
ChangeMaterializationOperation = Literal[
    "library.import_source",
    "documents.upsert_prism_file",
    "memory.merge_items",
    "decisions.set",
    "tasks.create",
    "sandbox.materialize_artifact",
    "settings.update",
]

DEFAULT_WRITE_MODE: WriteMode = "auto_draft"
VALID_WRITE_MODES = set(get_args(WriteMode))

_HIGH_RISKS = {"high", "critical"}
_HIGH_RISK_DEFAULT_STATES = {"staged", "blocked"}


def normalize_write_mode(value: object | None) -> WriteMode:
    """Return a valid workspace write mode or raise ValueError."""
    raw_value = DEFAULT_WRITE_MODE if value is None else str(value).strip()
    if raw_value in VALID_WRITE_MODES:
        return cast(WriteMode, raw_value)
    raise ValueError(f"Invalid write_mode: {value}. Must be one of: {sorted(VALID_WRITE_MODES)}")


class ChangeTarget(BaseModel):
    """Workspace object location affected by a change unit."""

    model_config = ConfigDict(extra="forbid")

    room: str = Field(min_length=1, max_length=80)
    object_type: str = Field(min_length=1, max_length=80)
    object_id: str | None = Field(default=None, max_length=160)
    path: str | None = Field(default=None, max_length=500)
    section_id: str | None = Field(default=None, max_length=160)

    @field_validator("room", "object_type", mode="before")
    @classmethod
    def _clean_required_text(cls, value: Any) -> str:
        text = _clean_text(value)
        if not text:
            raise ValueError("field must not be blank")
        return text

    @field_validator("object_id", "path", "section_id", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: Any) -> str | None:
        text = _clean_text(value)
        return text or None


class ChangeMaterialization(BaseModel):
    """Typed room write command carried by a materializable ChangeUnit."""

    model_config = ConfigDict(extra="forbid")

    operation: ChangeMaterializationOperation
    payload: dict[str, Any]


class ChangeUnit(BaseModel):
    """Single reviewable write operation in a ChangeSet."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    target: ChangeTarget
    action: str = Field(min_length=1, max_length=80)
    risk: ChangeRisk
    risk_reasons: list[str] = Field(default_factory=list, max_length=12)
    default_apply_state: ApplyState
    requires_confirmation: bool
    diff: dict[str, Any]
    provenance: dict[str, Any]
    rollback: dict[str, Any]
    materialization: ChangeMaterialization | None = None

    @field_validator("id", "action", mode="before")
    @classmethod
    def _clean_required_text(cls, value: Any) -> str:
        text = _clean_text(value)
        if not text:
            raise ValueError("field must not be blank")
        return text

    @field_validator("risk_reasons", mode="before")
    @classmethod
    def _clean_risk_reasons(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list | tuple | set | frozenset):
            raise ValueError("risk_reasons must be a list")
        return _unique_strings(value)[:12]

    @model_validator(mode="after")
    def _validate_review_requirements(self) -> Self:
        if self.risk in _HIGH_RISKS:
            if not self.risk_reasons:
                raise ValueError("high and critical changes require risk_reasons")
            if not self.requires_confirmation:
                raise ValueError("high and critical changes require requires_confirmation=true")
            if self.default_apply_state not in _HIGH_RISK_DEFAULT_STATES:
                raise ValueError(
                    "high and critical changes require default_apply_state to be staged or blocked"
                )
        if self.default_apply_state == "blocked" and not self.risk_reasons:
            raise ValueError("blocked changes require a risk reason or explanatory reason")
        if (
            self.provenance.get("source") == "task_report.outputs"
            and self.default_apply_state != "blocked"
            and self.materialization is None
        ):
            raise ValueError("task_report output ChangeUnits require materialization")
        return self


class ChangeSet(BaseModel):
    """Collection of reviewable workspace write operations for one execution."""

    model_config = ConfigDict(extra="forbid")

    execution_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    write_mode: WriteMode
    units: list[ChangeUnit] = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=700)
    created_at: str = Field(min_length=1, max_length=80)

    @field_validator("execution_id", "workspace_id", "summary", "created_at", mode="before")
    @classmethod
    def _clean_required_text(cls, value: Any) -> str:
        text = _clean_text(value)
        if not text:
            raise ValueError("field must not be blank")
        return text

    @model_validator(mode="after")
    def _validate_unit_ids_are_unique(self) -> Self:
        seen: set[str] = set()
        duplicates: list[str] = []
        for unit in self.units:
            if unit.id in seen:
                duplicates.append(unit.id)
                continue
            seen.add(unit.id)
        if duplicates:
            raise ValueError(f"duplicate ChangeUnit ids: {', '.join(_unique_strings(duplicates))}")
        return self


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result
