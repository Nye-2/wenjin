"""Intake spec contract for one-step super workflows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IntakeWorkspaceType = Literal["software_copyright", "math_modeling"]
IntakeCapabilityId = Literal[
    "software_copyright_application_pack",
    "math_modeling_paper_pack",
]
IntakeSpecStatus = Literal["draft", "ready"]

_CAPABILITY_BY_WORKSPACE: dict[str, str] = {
    "software_copyright": "software_copyright_application_pack",
    "math_modeling": "math_modeling_paper_pack",
}
_AI_IMAGE_MARKERS = {
    "ai",
    "ai_image",
    "gpt-image",
    "gpt-image2",
    "image_model",
    "llm_image",
    "text_to_image",
}


def _contains_ai_image_marker(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower().replace("_", "-")
        compact = normalized.replace("-", "_")
        if normalized == "ai" or compact == "ai":
            return True
        return any(
            marker != "ai" and (marker in normalized or marker in compact)
            for marker in _AI_IMAGE_MARKERS
        )
    if isinstance(value, dict):
        return any(_contains_ai_image_marker(item) for item in value.values())
    if isinstance(value, list | tuple | set):
        return any(_contains_ai_image_marker(item) for item in value)
    return False


class IntakeSpecV1(BaseModel):
    """Markdown clarification spec authored by Chat Agent before launch.

    The spec is intentionally small: it is a renderable plan plus the exact
    `launch_feature.params` payload that approval should pass to Lead Agent.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.intake_spec.v1"] = "wenjin.intake_spec.v1"
    spec_id: str = Field(..., min_length=1, max_length=120)
    revision: int = Field(default=1, ge=1)
    workspace_id: str = Field(..., min_length=1, max_length=120)
    workspace_type: IntakeWorkspaceType
    capability_id: IntakeCapabilityId
    title: str = Field(..., min_length=1, max_length=160)
    status: IntakeSpecStatus = "draft"
    markdown: str = Field(..., min_length=12, max_length=12000)
    params: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _validate_super_workflow_rules(self) -> "IntakeSpecV1":
        expected_capability = _CAPABILITY_BY_WORKSPACE[self.workspace_type]
        if self.capability_id != expected_capability:
            raise ValueError(
                f"capability_id must be {expected_capability!r} for workspace_type {self.workspace_type!r}"
            )

        params = dict(self.params)
        if self.workspace_type == "math_modeling":
            language = str(params.get("programming_language") or "python").strip().lower()
            if language != "python":
                raise ValueError("math_modeling params.programming_language must be 'python'")
            params["programming_language"] = "python"
            if self.status == "ready" and not str(params.get("problem_statement") or "").strip():
                raise ValueError("math_modeling ready specs require params.problem_statement")

        if self.workspace_type == "software_copyright":
            if self.status == "ready" and not str(params.get("software_name") or "").strip():
                raise ValueError("software_copyright ready specs require params.software_name")
            visual_strategy = params.get("visual_strategy")
            if _contains_ai_image_marker(visual_strategy):
                raise ValueError(
                    "software_copyright visual_strategy.ui_screenshots must use static_frontend_screenshot, not AI-generated UI evidence"
                )

        self.params = params
        return self
