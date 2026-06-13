"""Shared contracts for DataService-backed expert/team presentation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExpertTone = Literal["professional", "witty_professional"]

_STATUS_KEYS = {"queued", "running", "blocked", "completed", "failed"}


class ExpertProfileV1(BaseModel):
    """Public identity for an agent template."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.expert_profile.v1"] = "wenjin.team.expert_profile.v1"
    public_name: str = Field(min_length=1, max_length=40)
    short_name: str | None = Field(default=None, max_length=16)
    role_title: str = Field(min_length=1, max_length=40)
    avatar_label: str | None = Field(default=None, max_length=3)
    tone: ExpertTone = "professional"
    tagline: str | None = Field(default=None, max_length=80)
    status_phrases: dict[str, str] = Field(default_factory=dict)
    preview_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("public_name", "role_title", mode="before")
    @classmethod
    def _clean_required_text_field(cls, value: Any) -> str:
        text = _clean_text(value)
        if not text:
            raise ValueError("field must not be blank")
        return text

    @field_validator("short_name", "avatar_label", "tagline", mode="before")
    @classmethod
    def _clean_optional_text_field(cls, value: Any) -> str | None:
        text = _clean_text(value)
        return text or None

    @field_validator("status_phrases")
    @classmethod
    def _validate_status_phrases(cls, value: dict[str, str]) -> dict[str, str]:
        result: dict[str, str] = {}
        invalid: list[str] = []
        for key, phrase in value.items():
            clean_key = str(key or "").strip()
            if clean_key not in _STATUS_KEYS:
                invalid.append(clean_key)
                continue
            clean_phrase = _clean_text(phrase)[:60]
            if clean_phrase:
                result[clean_key] = clean_phrase
        if invalid:
            raise ValueError(f"status_phrases has unknown status keys: {', '.join(invalid)}")
        return result

    @field_validator("preview_preferences")
    @classmethod
    def _bound_preview_preferences(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result = dict(value)
        raw_kinds = result.get("primary_kinds")
        if isinstance(raw_kinds, list | tuple | set):
            result["primary_kinds"] = _unique_strings(raw_kinds)[:8]
        elif raw_kinds is not None:
            result.pop("primary_kinds", None)
        return result


class ExpertProfileOverrideV1(BaseModel):
    """Capability-local display override for an expert profile."""

    model_config = ConfigDict(extra="forbid")

    public_name: str | None = Field(default=None, min_length=1, max_length=40)
    short_name: str | None = Field(default=None, max_length=16)
    role_title: str | None = Field(default=None, min_length=1, max_length=40)
    avatar_label: str | None = Field(default=None, max_length=3)
    tone: ExpertTone | None = None
    tagline: str | None = Field(default=None, max_length=80)
    status_phrases: dict[str, str] = Field(default_factory=dict)
    preview_preferences: dict[str, Any] = Field(default_factory=dict)

    @field_validator("public_name", "short_name", "role_title", "avatar_label", "tagline", mode="before")
    @classmethod
    def _clean_optional_text_field(cls, value: Any) -> str | None:
        text = _clean_text(value)
        return text or None

    @field_validator("status_phrases")
    @classmethod
    def _validate_status_phrases(cls, value: dict[str, str]) -> dict[str, str]:
        return ExpertProfileV1(
            public_name="placeholder",
            role_title="placeholder",
            status_phrases=value,
        ).status_phrases

    @field_validator("preview_preferences")
    @classmethod
    def _bound_preview_preferences(cls, value: dict[str, Any]) -> dict[str, Any]:
        return ExpertProfileV1(
            public_name="placeholder",
            role_title="placeholder",
            preview_preferences=value,
        ).preview_preferences


class CapabilityTeamPresentationV1(BaseModel):
    """Capability extension for expert-team display customization."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.team.presentation.v1"] = "wenjin.team.presentation.v1"
    leader_virtual_member: ExpertProfileOverrideV1 | None = None
    template_overrides: dict[str, ExpertProfileOverrideV1] = Field(default_factory=dict)


def resolve_expert_profile(
    *,
    base_profile: ExpertProfileV1 | dict[str, Any] | None,
    display_role: str,
    override: ExpertProfileOverrideV1 | dict[str, Any] | None = None,
) -> ExpertProfileV1:
    """Resolve template profile plus capability display override."""

    if isinstance(base_profile, ExpertProfileV1):
        data = base_profile.model_dump(mode="json")
    elif isinstance(base_profile, dict):
        data = ExpertProfileV1.model_validate(base_profile).model_dump(mode="json")
    else:
        role = _clean_text(display_role) or "专家"
        data = {
            "public_name": role,
            "role_title": role,
            "avatar_label": role[:1] or "专",
            "tone": "professional",
        }

    if override:
        override_model = (
            override
            if isinstance(override, ExpertProfileOverrideV1)
            else ExpertProfileOverrideV1.model_validate(override)
        )
        override_data = override_model.model_dump(exclude_none=True, mode="json")
        merged_status = {
            **dict(data.get("status_phrases") or {}),
            **dict(override_data.pop("status_phrases", {}) or {}),
        }
        merged_preview_preferences = {
            **dict(data.get("preview_preferences") or {}),
            **dict(override_data.pop("preview_preferences", {}) or {}),
        }
        data.update(override_data)
        if merged_status:
            data["status_phrases"] = merged_status
        if merged_preview_preferences:
            data["preview_preferences"] = merged_preview_preferences

    if not data.get("avatar_label"):
        data["avatar_label"] = str(data.get("public_name") or "专")[:1]
    return ExpertProfileV1.model_validate(data)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result
