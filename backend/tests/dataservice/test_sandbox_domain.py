"""DataService sandbox aggregate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactCreateCommand,
    SandboxEnvironmentCreateCommand,
    SandboxJobCreateCommand,
    SandboxJobUpdateCommand,
    SandboxLeaseAcquireCommand,
    SandboxLeaseReleaseCommand,
    SandboxLeaseRenewCommand,
)
from src.dataservice.domains.sandbox.models import (
    SandboxArtifactRecord,
    SandboxEnvironmentRecord,
    SandboxJobRecord,
)
from src.dataservice.domains.sandbox.policy import validate_python_job_contract
from src.dataservice.domains.sandbox.service import SandboxDataDomainService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _record(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {"created_at": now, "updated_at": now}
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeSandboxRepository:
    def __init__(self) -> None:
        self.environments: dict[str, SimpleNamespace] = {}
        self.jobs: dict[str, SimpleNamespace] = {}
        self.artifacts: dict[str, SimpleNamespace] = {}
        self.leases: dict[str, SimpleNamespace] = {}

    def create_environment(self, values: dict[str, Any]) -> SimpleNamespace:
        environment_id = f"env-{len(self.environments) + 1}"
        record = _record({"id": environment_id, **values})
        self.environments[environment_id] = record
        return record

    async def get_environment(self, environment_id: str) -> SimpleNamespace | None:
        return self.environments.get(environment_id)

    async def get_active_environment(self, workspace_id: str) -> SimpleNamespace | None:
        for record in self.environments.values():
            if record.workspace_id == workspace_id and record.state == "active":
                return record
        return None

    async def list_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.environments.values() if record.workspace_id == workspace_id]
        if state is not None:
            records = [record for record in records if record.state == state]
        return records[:limit]

    def create_job(self, values: dict[str, Any]) -> SimpleNamespace:
        job_id = f"job-{len(self.jobs) + 1}"
        record = _record(
            {
                "id": job_id,
                "operation": values.get("operation", "run_python"),
                "billable": values.get("billable", True),
                "status": "queued",
                "exit_code": None,
                "stdout_asset_id": None,
                "stderr_asset_id": None,
                "started_at": None,
                "finished_at": None,
                "error_text": None,
                **values,
            }
        )
        self.jobs[job_id] = record
        return record

    async def get_job(self, job_id: str) -> SimpleNamespace | None:
        return self.jobs.get(job_id)

    async def list_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        mission_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.jobs.values() if record.workspace_id == workspace_id]
        if sandbox_environment_id is not None:
            records = [record for record in records if record.sandbox_environment_id == sandbox_environment_id]
        if mission_id is not None:
            records = [record for record in records if record.mission_id == mission_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records[:limit]

    def create_lease(self, values: dict[str, Any]) -> SimpleNamespace:
        lease_id = f"lease-{len(self.leases) + 1}"
        record = _record({"id": lease_id, **values})
        self.leases[record.workspace_id] = record
        return record

    async def get_lease_for_update(self, workspace_id: str) -> SimpleNamespace | None:
        return self.leases.get(workspace_id)

    async def delete_lease(self, record: SimpleNamespace) -> None:
        self.leases.pop(record.workspace_id, None)

    def create_artifact(self, values: dict[str, Any]) -> SimpleNamespace:
        artifact_id = f"artifact-{len(self.artifacts) + 1}"
        record = _record(
            {
                "id": artifact_id,
                "mission_commit_id": None,
                **values,
            }
        )
        self.artifacts[artifact_id] = record
        return record

    async def get_artifact(self, artifact_id: str) -> SimpleNamespace | None:
        return self.artifacts.get(artifact_id)

    async def list_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.artifacts.values() if record.workspace_id == workspace_id]
        if sandbox_job_id is not None:
            records = [record for record in records if record.sandbox_job_id == sandbox_job_id]
        if materialization_status is not None:
            records = [record for record in records if record.materialization_status == materialization_status]
        return records[:limit]


def _service() -> tuple[SandboxDataDomainService, FakeSandboxRepository, None, FakeSession]:
    session = FakeSession()
    service = SandboxDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSandboxRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, None, session


def test_sandbox_models_are_registered_on_shared_metadata() -> None:
    assert SandboxEnvironmentRecord.__tablename__ in Base.metadata.tables
    assert SandboxJobRecord.__tablename__ in Base.metadata.tables
    assert SandboxArtifactRecord.__tablename__ in Base.metadata.tables


def test_python_job_contract_blocks_container_control() -> None:
    with pytest.raises(DataServiceValidationError):
        validate_python_job_contract(
            language="python",
            command="python -m subprocess docker ps",
            policy_json={"allow_docker_socket": False},
        )

    with pytest.raises(DataServiceValidationError):
        validate_python_job_contract(
            language="python",
            command="python analysis.py",
            policy_json={"allow_host_network": True},
        )


def test_install_dependency_contract_allows_workspace_venv_pip_install() -> None:
    validate_python_job_contract(
        operation="install_dependencies",
        language="python",
        command="/workspace/.wenjin/env/python/bin/python -m pip install scikit-learn pandas>=2",
        policy_json={"allow_package_install": True},
        package_specs=["scikit-learn", "pandas>=2"],
    )


@pytest.mark.parametrize(
    "package_spec",
    [
        "https://example.com/pkg.whl",
        "git+https://example.com/repo.git",
        "../pkg",
        "-r requirements.txt",
        "pkg; os_name == 'posix'",
    ],
)
def test_install_dependency_contract_rejects_unsafe_package_specs(package_spec: str) -> None:
    with pytest.raises(DataServiceValidationError):
        validate_python_job_contract(
            operation="install_dependencies",
            language="python",
            command=f"/workspace/.wenjin/env/python/bin/python -m pip install {package_spec}",
            policy_json={"allow_package_install": True},
            package_specs=[package_spec],
        )


def test_run_python_contract_allows_workspace_venv_python() -> None:
    validate_python_job_contract(
        operation="run_python",
        language="python",
        command="/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis.py",
        policy_json={"allow_python": True},
    )


@pytest.mark.asyncio
async def test_get_or_create_environment_uses_workspace_sandbox_identity() -> None:
    service, repository, _, _ = _service()

    first = await service.get_or_create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1", created_by="lead-agent"))
    second = await service.get_or_create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1", created_by="lead-agent"))

    assert first.id == second.id
    assert first.sandbox_id == "workspace-ws-1"
    assert first.metadata_json["provider_key"] == "workspace-ws-1"
    assert len(repository.environments) == 1


@pytest.mark.asyncio
async def test_get_or_create_environment_merges_current_runtime_metadata() -> None:
    service, repository, _, _ = _service()

    first = await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            metadata_json={
                "provider_key": "workspace-ws-1",
                "runtime_image": "python:old",
                "workspace_layout": {"workspace_type": "generic"},
                "operator_note": "preserve",
            },
        )
    )
    second = await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            metadata_json={
                "runtime_image": "python:new",
                "workspace_layout": {
                    "schema": "wenjin.workspace_sandbox.layout.v1",
                    "version": 1,
                    "workspace_type": "sci",
                },
                "workspace_profile": {
                    "schema": "wenjin.workspace_sandbox.type_profile.v1",
                    "workspace_type": "sci",
                },
            },
        )
    )

    assert first.id == second.id
    assert len(repository.environments) == 1
    assert second.metadata_json["provider_key"] == "workspace-ws-1"
    assert second.metadata_json["runtime_image"] == "python:new"
    assert second.metadata_json["operator_note"] == "preserve"
    assert second.metadata_json["workspace_layout"]["workspace_type"] == "sci"
    assert second.metadata_json["workspace_profile"]["workspace_type"] == "sci"


@pytest.mark.asyncio
async def test_get_or_create_environment_does_not_downgrade_known_workspace_profile() -> None:
    service, _, _, _ = _service()

    await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            metadata_json={
                "provider_key": "workspace-ws-1",
                "workspace_layout": {
                    "schema": "wenjin.workspace_sandbox.layout.v1",
                    "version": 1,
                    "workspace_type": "sci",
                },
                "workspace_profile": {
                    "schema": "wenjin.workspace_sandbox.type_profile.v1",
                    "workspace_type": "sci",
                },
            },
        )
    )
    second = await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            metadata_json={
                "runtime_image": "python:new",
                "workspace_layout": {
                    "schema": "wenjin.workspace_sandbox.layout.v1",
                    "version": 1,
                    "workspace_type": None,
                },
                "workspace_profile": {
                    "schema": "wenjin.workspace_sandbox.type_profile.v1",
                    "workspace_type": "generic",
                },
            },
        )
    )

    assert second.metadata_json["runtime_image"] == "python:new"
    assert second.metadata_json["workspace_layout"]["workspace_type"] == "sci"
    assert second.metadata_json["workspace_profile"]["workspace_type"] == "sci"


@pytest.mark.asyncio
async def test_create_environment_rejects_second_active_workspace_environment() -> None:
    service, _, _, _ = _service()
    await service.create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1"))

    with pytest.raises(DataServiceValidationError, match="active sandbox environment already exists"):
        await service.create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1", sandbox_id="another"))


@pytest.mark.asyncio
async def test_sandbox_job_records_operation_and_billable_flag() -> None:
    service, _, _, _ = _service()
    environment = await service.create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1"))

    job = await service.create_job(
        SandboxJobCreateCommand(
            workspace_id="ws-1",
            sandbox_environment_id=environment.id,
            operation="install_dependencies",
            billable=False,
            command="/workspace/.wenjin/env/python/bin/python -m pip install scikit-learn",
            metadata_json={"packages": ["scikit-learn"]},
        )
    )

    assert job.operation == "install_dependencies"
    assert job.billable is False
    assert job.metadata_json["packages"] == ["scikit-learn"]


@pytest.mark.asyncio
async def test_sandbox_lease_blocks_other_active_holder_and_releases() -> None:
    service, repository, _, _ = _service()

    lease = await service.acquire_lease(
        SandboxLeaseAcquireCommand(
            workspace_id="ws-1",
            sandbox_environment_id="env-1",
            holder_job_id="job-1",
            holder_mission_id="mission-1",
            lease_token="token-1",
            ttl_seconds=60,
        )
    )

    with pytest.raises(DataServiceValidationError, match="workspace sandbox is busy"):
        await service.acquire_lease(
            SandboxLeaseAcquireCommand(
                workspace_id="ws-1",
                sandbox_environment_id="env-1",
                holder_job_id="job-2",
                holder_mission_id="mission-2",
                lease_token="token-2",
                ttl_seconds=60,
            )
        )

    renewed = await service.renew_lease(SandboxLeaseRenewCommand(workspace_id="ws-1", lease_token="token-1", ttl_seconds=120))
    released = await service.release_lease(SandboxLeaseReleaseCommand(workspace_id="ws-1", lease_token="token-1"))

    assert lease.holder_job_id == "job-1"
    assert renewed is not None
    assert renewed.expires_at > lease.expires_at
    assert released is True
    assert repository.leases == {}


@pytest.mark.asyncio
async def test_environment_job_and_artifact_mission_commit_flow() -> None:
    service, repository, _, session = _service()

    environment = await service.create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            sandbox_id="sandbox-ext-1",
            provider="docker",
            workspace_path="/workspace",
        )
    )
    job = await service.create_job(
        SandboxJobCreateCommand(
            workspace_id="ws-1",
            sandbox_environment_id=environment.id,
            mission_id="mission-1",
            command="python analysis.py",
            script_hash="sha256:script",
            input_hashes_json={"dataset.csv": "sha256:data"},
        )
    )
    running = await service.update_job(job.id, SandboxJobUpdateCommand(status="running"))
    artifact = await service.register_artifact(
        SandboxArtifactCreateCommand(
            workspace_id="ws-1",
            sandbox_job_id=job.id,
            workspace_asset_id="asset-1",
            artifact_kind="figure",
            path="/workspace/outputs/figure.png",
            mime_type="image/png",
            content_hash="sha256:figure",
            reproducibility_json={
                "source_mission_id": "mission-1",
                "source_task_id": "experiment_runner",
                "sandbox_environment_id": environment.id,
                "source_script": "/workspace/scripts/analysis.py",
                "dataset_paths": ["/workspace/datasets/raw.csv"],
            },
            metadata_json={
                "title": "Experiment figure",
                "description": "User-facing figure produced by the sandbox run.",
                "notes": "Ready for review.",
            },
        )
    )
    listed = await service.list_artifacts(workspace_id="ws-1", materialization_status="pending_review")

    assert environment.policy_json["allow_python"] is True
    assert job.language == "python"
    assert running is not None
    assert running.started_at is not None
    assert artifact.mission_commit_id is None
    assert artifact.reproducibility_json["runtime_image"] == "python:3.13-slim"
    assert artifact.reproducibility_json["source_script"] == "/workspace/scripts/analysis.py"
    assert artifact.reproducibility_json["dataset_paths"] == ["/workspace/datasets/raw.csv"]
    assert listed[0].id == artifact.id
    assert repository.artifacts[artifact.id].materialization_status == "pending_review"
    assert session.commit_count == 4


@pytest.mark.asyncio
async def test_sandbox_artifact_materialization_binds_one_mission_commit() -> None:
    service, repository, _, _ = _service()
    repository.create_environment(
        {
            "workspace_id": "ws-1",
            "sandbox_id": "sandbox-ext-1",
            "provider": "docker",
            "state": "active",
            "workspace_path": None,
            "network_policy": "restricted_egress",
            "policy_json": {"allow_python": True},
            "resource_limits_json": {},
            "created_by": "test",
            "last_active_at": None,
            "released_at": None,
            "metadata_json": {},
        }
    )
    repository.create_job(
        {
            "workspace_id": "ws-1",
            "sandbox_environment_id": "env-1",
            "mission_id": "mission-1",
            "mission_item_seq": None,
            "language": "python",
            "runtime_image": "python:3.13-slim",
            "command": "python analysis.py",
            "script_hash": None,
            "input_hashes_json": {},
            "network_policy": "restricted_egress",
            "resource_limits_json": {},
            "policy_json": {},
            "metadata_json": {},
        }
    )
    artifact = repository.create_artifact(
        {
            "workspace_id": "ws-1",
            "sandbox_environment_id": "env-1",
            "sandbox_job_id": "job-1",
            "workspace_asset_id": "asset-1",
            "artifact_kind": "table",
            "path": "/mnt/user-data/table.csv",
            "mime_type": "text/csv",
            "content_hash": None,
            "reproducibility_json": {},
            "mission_commit_id": None,
            "materialization_status": "pending_review",
            "metadata_json": {},
        }
    )
    result = await service.mark_artifact_materialized(
        artifact.id,
        mission_commit_id="commit-1",
    )

    assert result is not None
    assert result.mission_commit_id == "commit-1"
    assert repository.artifacts[artifact.id].materialization_status == "applied"
