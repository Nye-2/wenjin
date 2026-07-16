from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest

from src.sandbox.base import SandboxReceiptState
from src.sandbox.contracts import (
    RunPythonInput,
    SandboxMissionProvenance,
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOperationStatus,
    SandboxRetryDisposition,
    content_hash_bytes,
    sandbox_job_id,
)
from src.sandbox.exceptions import SandboxMaterializationError, SandboxOutputRefError
from src.sandbox.runtime import SandboxRuntime
from src.sandbox.security import SandboxPathError
from src.sandbox.storage import FilesystemSandboxReceiptStore, SandboxWorkspace

IMAGE_DIGEST = f"sha256:{'a' * 64}"


def _workspace(tmp_path) -> SandboxWorkspace:
    workspace = SandboxWorkspace(
        sandbox_root=tmp_path,
        workspace_id="workspace-1",
        output_ref_ttl_seconds=60,
    )
    workspace.initialize()
    return workspace


def _request(*, lease_epoch: int = 1) -> SandboxOperationRequest:
    operation_input = RunPythonInput(script="print('ok')\n")
    return SandboxOperationRequest.build(
        provenance=SandboxMissionProvenance(
            workspace_id="workspace-1",
            mission_id="mission-1",
            mission_item_seq=3,
            lease_epoch=lease_epoch,
        ),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )


def test_workspace_separates_public_control_and_environments(tmp_path) -> None:
    workspace = _workspace(tmp_path)

    assert workspace.paths.public_root.is_dir()
    assert workspace.paths.control_root.is_dir()
    assert workspace.paths.environments_root.is_dir()
    assert workspace.paths.control_root not in workspace.paths.public_root.parents
    assert not (workspace.paths.public_root / ".wenjin").exists()
    assert (workspace.paths.control_root / "workspace.json").is_file()
    assert (workspace.paths.control_root / "artifact_objects").is_dir()
    assert stat.S_IMODE(workspace.paths.control_root.stat().st_mode) & 0o077 == 0


def test_runtime_hashes_and_mounts_derived_artifact_inputs_read_only(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact_path = "/workspace/outputs/q3_plot_data.csv"
    workspace.write_text(
        artifact_path,
        "policy,cost\nB0,1\n",
        expected_content_hash=None,
    )
    operation_input = RunPythonInput(
        script="print('ok')\n",
        artifact_input_paths=(artifact_path,),
    )
    runtime = object.__new__(SandboxRuntime)

    input_hashes = runtime._input_hashes(workspace, operation_input)
    request = SandboxOperationRequest.build(
        provenance=SandboxMissionProvenance(
            workspace_id="workspace-1",
            mission_id="mission-1",
            lease_epoch=1,
        ),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes=input_hashes,
    )
    staging = workspace.create_output_staging(request.operation_key)
    mounts = runtime._mounts(
        workspace,
        request=request,
        environment_path=None,
        environment_staging=None,
        output_staging=staging,
    )

    assert input_hashes[f"artifact:{artifact_path}"] == workspace.content_hash(
        artifact_path
    )
    artifact_mount = next(mount for mount in mounts if mount.target == artifact_path)
    assert artifact_mount.source == workspace.resolve_public_path(artifact_path)
    assert artifact_mount.read_only is True
    mountpoint = staging / "outputs" / "q3_plot_data.csv"
    assert mountpoint.is_file()
    assert mountpoint.stat().st_size == 0
    workspace.remove_artifact_input_mountpoints(
        staging=staging,
        paths=(artifact_path,),
    )
    assert not mountpoint.exists()
    workspace.discard_output_staging(staging)


def test_existing_file_write_requires_current_base_hash(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    path = "/workspace/scripts/analysis.py"
    first_hash = workspace.write_text(path, "print(1)\n", expected_content_hash=None)

    with pytest.raises(SandboxPathError, match="base content hash"):
        workspace.write_text(path, "print(2)\n", expected_content_hash=None)
    with pytest.raises(SandboxPathError, match="stale"):
        workspace.write_text(
            path,
            "print(2)\n",
            expected_content_hash=content_hash_bytes(b"wrong"),
        )

    second_hash = workspace.write_text(
        path,
        "print(2)\n",
        expected_content_hash=first_hash,
    )
    assert second_hash == content_hash_bytes(b"print(2)\n")


def test_stale_output_hash_error_names_the_output_path(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    output_path = "/workspace/outputs/result.json"
    workspace.write_text(output_path, '{"value":1}\n', expected_content_hash=None)
    staging = tmp_path / "operation_staging" / "job-1"
    staged_output = staging / "outputs" / "result.json"
    staged_output.parent.mkdir(parents=True)
    staged_output.write_text('{"value":2}\n')

    with pytest.raises(
        SandboxPathError,
        match=r"output base content hash is stale for /workspace/outputs/result.json",
    ):
        workspace.merge_staged_outputs(
            staging=staging,
            output_base_hashes={output_path: content_hash_bytes(b"stale")},
            max_workspace_bytes=1_000_000,
        )


def test_symlink_escape_is_rejected(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.paths.public_root / "scripts" / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SandboxPathError, match="symlink"):
        workspace.write_text(
            "/workspace/scripts/link/escape.py",
            "print('no')\n",
            expected_content_hash=None,
        )


def test_output_refs_are_opaque_integrity_checked_and_expire(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    now = datetime.now(UTC)
    output = workspace.write_output_ref(
        stream="stdout",
        content=b"full redacted output",
        now=now,
    )

    assert output.output_ref.startswith("sbxout_")
    assert "/" not in output.output_ref
    assert workspace.read_output_ref(output.output_ref, now=now) == b"full redacted output"
    with pytest.raises(SandboxOutputRefError, match="expired"):
        workspace.read_output_ref(output.output_ref, now=now + timedelta(seconds=61))


def test_registered_artifact_bytes_survive_public_path_replacement(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    path = "/workspace/outputs/result.json"
    original = b'{"objective":4}\n'
    original_hash = workspace.write_text(
        path,
        original.decode(),
        expected_content_hash=None,
    )
    [manifest] = workspace.artifact_manifests_for_paths(
        paths=(path,),
        request=_request(),
        sandbox_job_id="sbxjob_immutable",
        sandbox_environment_id="sbxenv_immutable",
        source_script="/workspace/scripts/analysis.py",
        dataset_paths=(),
        stdout_truncated=False,
        stderr_truncated=False,
        created_at=datetime.now(UTC),
    )

    workspace.write_text(
        path,
        '{"objective":9}\n',
        expected_content_hash=original_hash,
    )

    assert workspace.read_bytes(path) != original
    assert workspace.read_artifact_object(
        manifest.object_ref,
        expected_content_hash=manifest.content_hash,
    ) == original
    object_path = (
        workspace.paths.control_root
        / "artifact_objects"
        / f"{manifest.object_ref}.bin"
    )
    assert stat.S_IMODE(object_path.stat().st_mode) & 0o222 == 0


def test_corrupt_output_ref_cannot_escape_control_root_during_cleanup(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    now = datetime.now(UTC)
    output = workspace.write_output_ref(stream="stdout", content=b"output", now=now)
    outside = workspace.paths.control_root / "outside.txt"
    outside.write_text("keep")
    metadata_path = workspace.paths.control_root / "output_refs" / f"{output.output_ref}.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["data_file"] = "../outside.txt"
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(SandboxOutputRefError, match="does not exist"):
        workspace.read_output_ref(output.output_ref, now=now + timedelta(seconds=61))

    assert outside.read_text() == "keep"


def test_environment_is_content_addressed_and_sealed(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    staging = workspace.create_environment_staging("sbxop_install")
    (staging / "venv" / "bin").mkdir(parents=True)
    python = staging / "venv" / "bin" / "python"
    python.write_bytes(b"#!/bin/sh\n")
    os.chmod(python, 0o755)
    (staging / "requirements.lock").write_text("numpy==2.3.0\n")

    manifest, path = workspace.finalize_environment(
        staging=staging,
        image_digest=IMAGE_DIGEST,
        runtime="python3.13",
        requested_packages=("numpy==2.3.0",),
        created_at=datetime.now(UTC),
    )

    assert path.name == manifest.environment_id
    assert workspace.load_environment(manifest.environment_id) == manifest
    sealed_python = path / "venv" / "bin" / "python"
    assert stat.S_IMODE(sealed_python.stat().st_mode) & 0o111
    assert stat.S_IMODE(sealed_python.stat().st_mode) & 0o222 == 0


def test_existing_staging_is_preserved_for_reconciliation(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    operation_key = f"sbxop_{'c' * 64}"
    output_staging = workspace.create_output_staging(operation_key)
    output_marker = output_staging / "outputs" / "partial.txt"
    output_marker.write_text("partial")
    environment_staging = workspace.create_environment_staging(operation_key)
    environment_marker = environment_staging / "partial.lock"
    environment_marker.write_text("partial")

    with pytest.raises(SandboxMaterializationError, match="reconciliation"):
        workspace.create_output_staging(operation_key)
    with pytest.raises(SandboxMaterializationError, match="reconciliation"):
        workspace.create_environment_staging(operation_key)

    assert output_marker.read_text() == "partial"
    assert environment_marker.read_text() == "partial"


@pytest.mark.asyncio
async def test_receipt_store_reuses_terminal_result_for_duplicate_delivery(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    store = FilesystemSandboxReceiptStore(workspace)
    request = _request()
    job_id = sandbox_job_id(request.operation_key)
    claim = await store.claim(request, sandbox_job_id=job_id)
    assert claim.acquired
    now = datetime.now(UTC)
    result = SandboxOperationResult(
        operation_key=request.operation_key,
        sandbox_job_id=job_id,
        provenance=request.provenance,
        operation=request.operation,
        image_digest=request.image_digest,
        policy_version=request.policy_version,
        command_schema_version=request.command_schema_version,
        status=SandboxOperationStatus.SUCCEEDED,
        retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
        exit_code=0,
        started_at=now,
        finished_at=now,
    )
    await store.finalize(result)

    duplicate = await store.claim(request, sandbox_job_id=job_id)

    assert duplicate.state == SandboxReceiptState.TERMINAL
    assert not duplicate.acquired
    assert duplicate.existing_result == result


@pytest.mark.asyncio
async def test_incomplete_receipt_is_not_blindly_reclaimed(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    store = FilesystemSandboxReceiptStore(workspace)
    request = _request()
    job_id = sandbox_job_id(request.operation_key)

    first = await store.claim(request, sandbox_job_id=job_id)
    duplicate = await store.claim(request, sandbox_job_id=job_id)

    assert first.acquired
    assert duplicate.state == SandboxReceiptState.CLAIMED
    assert not duplicate.acquired


@pytest.mark.asyncio
async def test_receipt_identity_survives_mission_lease_takeover(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    store = FilesystemSandboxReceiptStore(workspace)
    first_request = _request(lease_epoch=1)
    takeover_request = _request(lease_epoch=2)

    assert takeover_request.operation_key == first_request.operation_key
    first = await store.claim(
        first_request,
        sandbox_job_id=sandbox_job_id(first_request.operation_key),
    )
    takeover = await store.claim(
        takeover_request,
        sandbox_job_id=sandbox_job_id(takeover_request.operation_key),
    )

    assert first.acquired
    assert takeover.state == SandboxReceiptState.CLAIMED
    assert not takeover.acquired
