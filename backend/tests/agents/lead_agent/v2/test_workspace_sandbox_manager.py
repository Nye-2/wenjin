from __future__ import annotations

from src.agents.lead_agent.v2.workspace_sandbox import WorkspaceSandboxManager
from src.dataservice_client.contracts.sandbox import (
    SandboxEnvironmentCreatePayload,
    SandboxEnvironmentPayload,
)


class _FakeDataService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, SandboxEnvironmentCreatePayload]] = []

    async def get_or_create_sandbox_environment(
        self,
        workspace_id: str,
        command: SandboxEnvironmentCreatePayload,
    ) -> SandboxEnvironmentPayload:
        self.calls.append((workspace_id, command))
        return SandboxEnvironmentPayload(
            id="env-1",
            workspace_id=workspace_id,
            sandbox_id=command.sandbox_id or "",
            provider=command.provider,
            state=command.state,
            workspace_path=command.workspace_path,
            network_policy=command.network_policy,
            policy_json=command.policy_json,
            resource_limits_json=command.resource_limits_json,
            created_by=command.created_by,
            metadata_json=command.metadata_json,
        )


async def test_workspace_sandbox_manager_records_layout_metadata() -> None:
    dataservice = _FakeDataService()
    manager = WorkspaceSandboxManager(dataservice=dataservice)  # type: ignore[arg-type]

    environment = await manager.get_or_create_environment(
        workspace_id="ws-1",
        workspace_type="sci",
        sandbox_policy={"mode": "required"},
        resource_limits={"cpu": 1, "memory_mb": 512},
        runtime_image="python:3.13-slim",
    )

    [(workspace_id, command)] = dataservice.calls
    assert workspace_id == "ws-1"
    assert command.sandbox_id == "workspace-ws-1"
    assert environment.metadata_json["provider_key"] == "workspace-ws-1"
    assert environment.metadata_json["runtime_image"] == "python:3.13-slim"
    assert environment.metadata_json["workspace_layout"] == {
        "schema": "wenjin.workspace_sandbox.layout.v1",
        "version": 1,
        "virtual_root": "/workspace",
        "manifest_path": "/workspace/.wenjin/manifest.json",
        "datasets_manifest_path": "/workspace/datasets/manifest.json",
        "artifacts_manifest_path": "/workspace/reports/artifacts.json",
        "workspace_type": "sci",
    }
    assert environment.metadata_json["workspace_profile"]["schema"] == (
        "wenjin.workspace_sandbox.type_profile.v1"
    )
    assert environment.metadata_json["workspace_profile"]["workspace_type"] == "sci"
    assert "/workspace/main/main.tex" in environment.metadata_json["workspace_profile"]["primary_files"]
