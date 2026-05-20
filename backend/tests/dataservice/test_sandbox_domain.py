"""DataService sandbox aggregate tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.database.base import Base
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.review.contracts import (
    ReviewBatchDetailProjection,
    ReviewBatchProjection,
    ReviewItemProjection,
)
from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactCreateCommand,
    SandboxEnvironmentCreateCommand,
    SandboxJobCreateCommand,
    SandboxJobUpdateCommand,
)
from src.dataservice.domains.sandbox.models import (
    SandboxArtifactRecord,
    SandboxEnvironmentRecord,
    SandboxJobRecord,
)
from src.dataservice.domains.sandbox.policy import validate_python_job_contract
from src.dataservice.domains.sandbox.review_handler import build_sandbox_artifact_review_handler
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
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = [record for record in self.jobs.values() if record.workspace_id == workspace_id]
        if sandbox_environment_id is not None:
            records = [record for record in records if record.sandbox_environment_id == sandbox_environment_id]
        if execution_id is not None:
            records = [record for record in records if record.execution_id == execution_id]
        if status is not None:
            records = [record for record in records if record.status == status]
        return records[:limit]

    def create_artifact(self, values: dict[str, Any]) -> SimpleNamespace:
        artifact_id = f"artifact-{len(self.artifacts) + 1}"
        record = _record(
            {
                "id": artifact_id,
                "review_batch_id": None,
                "review_item_id": None,
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


class FakeReviewService:
    def __init__(self) -> None:
        self.created_commands: list[Any] = []

    async def create_batch(self, command: Any) -> ReviewBatchDetailProjection:
        self.created_commands.append(command)
        return ReviewBatchDetailProjection(
            batch=ReviewBatchProjection(
                id="review-batch-1",
                workspace_id=command.workspace_id,
                execution_id=command.execution_id,
                source_type=command.source_type,
                source_id=command.source_id,
                review_kind=command.review_kind,
                status="pending",
                title=command.title,
                summary=command.summary,
                schema_version="review_batch.v1",
                item_count=len(command.items),
                accepted_count=0,
                rejected_count=0,
                applied_count=0,
                failed_count=0,
                payload_json=command.payload_json,
            ),
            items=[
                ReviewItemProjection(
                    id="review-item-1",
                    batch_id="review-batch-1",
                    workspace_id=command.workspace_id,
                    source_item_id=item.source_item_id,
                    item_kind=item.item_kind,
                    target_domain=item.target_domain,
                    target_kind=item.target_kind,
                    target_ref_json=item.target_ref_json,
                    status="pending",
                    title=item.title,
                    summary=item.summary,
                    payload_json=item.payload_json,
                    preview_json=item.preview_json,
                    provenance_json=item.provenance_json,
                    sort_order=item.sort_order,
                )
                for item in command.items
            ],
        )


def _service() -> tuple[SandboxDataDomainService, FakeSandboxRepository, FakeReviewService, FakeSession]:
    session = FakeSession()
    service = SandboxDataDomainService(session, autocommit=True)  # type: ignore[arg-type]
    repository = FakeSandboxRepository()
    review_service = FakeReviewService()
    service.repository = repository  # type: ignore[assignment]
    service.review_service = review_service  # type: ignore[assignment]
    return service, repository, review_service, session


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


@pytest.mark.asyncio
async def test_environment_job_and_artifact_review_flow() -> None:
    service, repository, review_service, session = _service()

    environment = await service.create_environment(
        SandboxEnvironmentCreateCommand(
            workspace_id="ws-1",
            sandbox_id="sandbox-ext-1",
            provider="docker",
            workspace_path="/mnt/user-data/ws-1",
        )
    )
    job = await service.create_job(
        SandboxJobCreateCommand(
            workspace_id="ws-1",
            sandbox_environment_id=environment.id,
            execution_id="exec-1",
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
            path="/mnt/user-data/ws-1/figure.png",
            mime_type="image/png",
            content_hash="sha256:figure",
        )
    )
    listed = await service.list_artifacts(workspace_id="ws-1", materialization_status="pending_review")

    assert environment.policy_json["allow_python"] is True
    assert job.language == "python"
    assert running is not None
    assert running.started_at is not None
    assert artifact.review_batch_id == "review-batch-1"
    assert artifact.review_item_id == "review-item-1"
    assert artifact.reproducibility_json["runtime_image"] == "python:3.13-slim"
    assert listed[0].id == artifact.id
    assert review_service.created_commands[0].items[0].target_domain == "sandbox"
    assert repository.artifacts[artifact.id].materialization_status == "pending_review"
    assert session.commit_count == 4


@pytest.mark.asyncio
async def test_sandbox_artifact_review_handler_marks_artifact_applied() -> None:
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
            "execution_id": "exec-1",
            "execution_node_id": None,
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
            "review_batch_id": "batch-1",
            "review_item_id": "review-item-1",
            "materialization_status": "pending_review",
            "metadata_json": {},
        }
    )
    handler = build_sandbox_artifact_review_handler(service)

    result = await handler(
        ReviewItemProjection(
            id="review-item-1",
            batch_id="batch-1",
            workspace_id="ws-1",
            item_kind="sandbox_artifact",
            target_domain="sandbox",
            target_kind="sandbox_artifact",
            target_ref_json={"sandbox_artifact_id": artifact.id},
            status="accepted",
            title="Accept table",
        )
    )

    assert result["applied"] is True
    assert repository.artifacts[artifact.id].materialization_status == "applied"
