from types import SimpleNamespace

import pytest

from scripts.workspace_prism_integrity_report import (
    _repair_missing_primary,
    _repair_project_name,
)


def test_repair_project_name_uses_workspace_name() -> None:
    assert (
        _repair_project_name({"workspace_name": "Paper Workspace"})
        == "Paper Workspace Manuscript"
    )


def test_repair_project_name_falls_back_for_blank_workspace_name() -> None:
    assert _repair_project_name({"workspace_name": ""}) == "Workspace Manuscript"


@pytest.mark.asyncio
async def test_repair_missing_primary_creates_primary_project_for_each_workspace() -> None:
    calls: list[dict[str, str]] = []

    class FakeService:
        async def ensure_primary_project(
            self,
            workspace_id: str,
            *,
            user_id: str,
            project_name: str,
        ) -> SimpleNamespace:
            calls.append(
                {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "project_name": project_name,
                }
            )
            return SimpleNamespace(id=f"latex-{workspace_id}")

    repaired = await _repair_missing_primary(
        FakeService(),  # type: ignore[arg-type]
        [
            {
                "workspace_id": "ws-1",
                "user_id": "user-1",
                "workspace_name": "SCI",
            },
            {
                "workspace_id": "ws-2",
                "user_id": "user-2",
                "workspace_name": "",
            },
        ],
    )

    assert calls == [
        {
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "project_name": "SCI Manuscript",
        },
        {
            "workspace_id": "ws-2",
            "user_id": "user-2",
            "project_name": "Workspace Manuscript",
        },
    ]
    assert repaired == [
        {
            "workspace_id": "ws-1",
            "user_id": "user-1",
            "latex_project_id": "latex-ws-1",
        },
        {
            "workspace_id": "ws-2",
            "user_id": "user-2",
            "latex_project_id": "latex-ws-2",
        },
    ]
