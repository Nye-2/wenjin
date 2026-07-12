from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.sandbox.compiler import SandboxOperationCompiler
from src.sandbox.contracts import (
    InstallDependenciesInput,
    RunPythonInput,
    SandboxEnvironmentManifest,
    SandboxMissionProvenance,
    SandboxNetworkGrant,
    SandboxNetworkProfile,
    SandboxOperationRequest,
    content_hash_bytes,
    environment_id,
)

IMAGE_DIGEST = f"sha256:{'a' * 64}"


def _provenance(*, lease_epoch: int = 1, item_seq: int = 4) -> SandboxMissionProvenance:
    return SandboxMissionProvenance(
        workspace_id="workspace-1",
        mission_id="mission-1",
        mission_item_seq=item_seq,
        subagent_id="analysis-1",
        lease_epoch=lease_epoch,
    )


def test_operation_key_is_stable_across_lease_takeover() -> None:
    operation_input = RunPythonInput(script="print('ok')\n")
    first = SandboxOperationRequest.build(
        provenance=_provenance(lease_epoch=2),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )
    takeover = SandboxOperationRequest.build(
        provenance=_provenance(lease_epoch=9),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )

    assert first.operation_key == takeover.operation_key
    assert first.provenance.lease_epoch != takeover.provenance.lease_epoch


def test_operation_key_changes_for_new_mission_item() -> None:
    operation_input = RunPythonInput(script="print('ok')\n")
    hashes = {"script": content_hash_bytes(operation_input.script.encode())}

    first = SandboxOperationRequest.build(
        provenance=_provenance(item_seq=4),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes=hashes,
    )
    revised = SandboxOperationRequest.build(
        provenance=_provenance(item_seq=5),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes=hashes,
    )

    assert first.operation_key != revised.operation_key


def test_non_default_network_requires_permission_reference() -> None:
    with pytest.raises(ValidationError, match="permission reference"):
        SandboxOperationRequest.build(
            provenance=_provenance(),
            operation_input=InstallDependenciesInput(packages=("pandas==2.3.0",)),
            image_digest=IMAGE_DIGEST,
            network_profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
        )


def test_dependency_input_rejects_urls_and_environment_markers() -> None:
    for package in (
        "https://example.invalid/pkg.whl",
        "pkg @ https://example.invalid/pkg.whl",
        "pkg; python_version > '3.12'",
    ):
        with pytest.raises(ValidationError, match="unsafe package spec"):
            InstallDependenciesInput(packages=(package,))


def test_explicit_egress_requires_admin_scope() -> None:
    grant = SandboxNetworkGrant(
        permission_request_id="permission-1",
        approved_scope="mission",
        allowed_hosts=("example.org",),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    with pytest.raises(ValidationError, match="admin approval"):
        SandboxOperationRequest.build(
            provenance=_provenance(),
            operation_input=RunPythonInput(script="print('ok')\n"),
            image_digest=IMAGE_DIGEST,
            network_profile=SandboxNetworkProfile.EXPLICIT_EGRESS_ADMIN_ONLY,
            network_grant=grant,
            input_hashes={"script": content_hash_bytes(b"print('ok')\n")},
        )


def test_request_contract_has_no_old_execution_or_container_identity() -> None:
    operation_input = RunPythonInput(script="print('ok')\n")
    request = SandboxOperationRequest.build(
        provenance=_provenance(),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )
    serialized = request.model_dump_json()

    assert "execution_id" not in serialized
    assert "execution_node_id" not in serialized
    assert "container_id" not in serialized
    assert "session_id" not in serialized


def test_compiler_scopes_scratch_to_mission_subagent() -> None:
    operation_input = RunPythonInput(script="print('ok')\n")
    request = SandboxOperationRequest.build(
        provenance=_provenance(),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )
    lock_content = b""
    environment = SandboxEnvironmentManifest(
        environment_id=environment_id(
            image_digest=IMAGE_DIGEST,
            runtime="python3.13",
            lock_content=lock_content,
        ),
        image_digest=IMAGE_DIGEST,
        runtime="python3.13",
        lock_hash=content_hash_bytes(lock_content),
        created_at=datetime.now(UTC),
    )

    command = SandboxOperationCompiler().compile(request, environment=environment)

    expected = "/workspace/tmp/tasks/mission-1/analysis-1"
    assert command.env["WENJIN_TASK_SCRATCH"] == expected
    assert command.env["HOME"] == expected
    assert command.env["MPLCONFIGDIR"] == f"{expected}/matplotlib"
