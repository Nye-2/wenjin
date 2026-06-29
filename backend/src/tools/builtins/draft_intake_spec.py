"""draft_intake_spec builtin tool — stages a Markdown launch spec for review."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError

from src.agents.contracts.intake_spec import IntakeSpecV1


class DraftIntakeSpecInput(BaseModel):
    workspace_type: str = Field(
        ...,
        description="Workspace type. Supported super workflows: software_copyright, math_modeling.",
    )
    capability_id: str = Field(
        ...,
        description="Capability id to launch after approval.",
    )
    title: str = Field(..., description="Human-facing title for the clarification spec.")
    markdown: str = Field(
        ...,
        description="Full Markdown spec that the user can review before execution.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Exact params to pass to launch_feature once the user approves.",
    )
    status: str = Field(
        default="draft",
        description="draft while information is missing, ready when approval can launch.",
    )
    missing_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    spec_id: str | None = Field(default=None)
    revision: int = Field(default=1)


def _runtime_value(config: RunnableConfig | None, key: str) -> str | None:
    configurable = (config or {}).get("configurable") if isinstance(config, Mapping) else None
    if not isinstance(configurable, Mapping):
        return None
    value = str(configurable.get(key) or "").strip()
    return value or None


@tool("draft_intake_spec", args_schema=DraftIntakeSpecInput)
async def draft_intake_spec_tool(
    workspace_type: str,
    capability_id: str,
    title: str,
    markdown: str,
    params: dict[str, Any] | None = None,
    status: str = "draft",
    missing_fields: list[str] | None = None,
    assumptions: list[str] | None = None,
    spec_id: str | None = None,
    revision: int = 1,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Create a renderable intake spec card for a super workflow."""

    workspace_id = _runtime_value(config, "workspace_id")
    if not workspace_id:
        return {
            "status": "advisory",
            "code": "missing_runtime_context",
            "detail": "缺少 workspace_id，无法生成可执行的澄清 Spec。",
        }

    try:
        spec = IntakeSpecV1(
            spec_id=spec_id or f"intake-{uuid4().hex}",
            revision=revision,
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            capability_id=capability_id,
            title=title,
            status=status,
            markdown=markdown,
            params=dict(params or {}),
            missing_fields=list(missing_fields or []),
            assumptions=list(assumptions or []),
        )
    except ValidationError as exc:
        return {
            "status": "advisory",
            "code": "invalid_intake_spec",
            "detail": str(exc),
            "context": {
                "workspace_type": workspace_type,
                "capability_id": capability_id,
            },
        }

    return {
        "status": spec.status,
        "intake_spec": spec.model_dump(mode="json"),
    }
