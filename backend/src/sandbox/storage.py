"""Durable public workspace, environment, output-ref and receipt storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.sandbox.base import (
    SandboxReceiptClaim,
    SandboxReceiptState,
    SandboxReceiptStore,
)
from src.sandbox.contracts import (
    SandboxArtifactManifest,
    SandboxDatasetManifest,
    SandboxEnvironmentManifest,
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOutputRef,
    content_hash_bytes,
    environment_id,
    utc_now,
)
from src.sandbox.exceptions import (
    SandboxEnvironmentError,
    SandboxMaterializationError,
    SandboxOutputRefError,
    SandboxReceiptConflictError,
)
from src.sandbox.security import (
    ARTIFACT_ROOTS,
    PUBLIC_WORKSPACE_DIRS,
    SandboxPathError,
    is_artifact_path,
    is_dataset_path,
    require_read_before_write,
    resolve_public_host_path,
)


@dataclass(frozen=True, slots=True)
class SandboxWorkspacePaths:
    workspace_root: Path
    public_root: Path
    control_root: Path
    environments_root: Path


class _OutputRefMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_ref: str
    stream: Literal["stdout", "stderr"]
    content_hash: str
    size_bytes: int
    expires_at: datetime
    data_file: str

    @model_validator(mode="after")
    def validate_data_file(self) -> _OutputRefMetadata:
        if self.data_file != f"{self.output_ref}.bin":
            raise ValueError("output reference payload name is invalid")
        return self


class _ReceiptDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["claimed", "terminal"]
    operation_key: str
    sandbox_job_id: str
    request_hash: str
    claimed_at: datetime
    result: dict[str, Any] | None = None


class SandboxWorkspace:
    """Host-side storage with public/control/environment roots kept separate."""

    def __init__(
        self,
        *,
        sandbox_root: Path,
        workspace_id: str,
        output_ref_ttl_seconds: int,
    ) -> None:
        workspace_key = content_hash_bytes(workspace_id.encode()).removeprefix("sha256:")
        workspace_root = sandbox_root.resolve() / "workspaces" / workspace_key
        self.paths = SandboxWorkspacePaths(
            workspace_root=workspace_root,
            public_root=workspace_root / "public",
            control_root=workspace_root / "control",
            environments_root=sandbox_root.resolve() / "environments",
        )
        self.workspace_id = workspace_id
        self.output_ref_ttl_seconds = output_ref_ttl_seconds

    def initialize(self) -> None:
        sandbox_root = self.paths.workspace_root.parents[1]
        workspaces_root = self.paths.workspace_root.parent
        sandbox_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        workspaces_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.paths.workspace_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.paths.public_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.paths.control_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.paths.environments_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        for path, mode in (
            (sandbox_root, 0o750),
            (workspaces_root, 0o750),
            (self.paths.workspace_root, 0o750),
            (self.paths.public_root, 0o750),
            (self.paths.control_root, 0o700),
            (self.paths.environments_root, 0o750),
        ):
            path.chmod(mode)
        for name in PUBLIC_WORKSPACE_DIRS:
            (self.paths.public_root / name).mkdir(parents=True, exist_ok=True, mode=0o750)
        for name in ("artifact_objects", "receipts", "output_refs", "manifests"):
            (self.paths.control_root / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest = {
            "schema": "wenjin.sandbox.workspace.v2",
            "workspace_id": self.workspace_id,
            "public_virtual_root": "/workspace",
            "public_directories": list(PUBLIC_WORKSPACE_DIRS),
            "control_visible_to_operations": False,
        }
        _atomic_write_json(self.paths.control_root / "workspace.json", manifest, mode=0o600)

    def resolve_public_path(self, virtual_path: str) -> Path:
        self.initialize()
        return resolve_public_host_path(self.paths.public_root, virtual_path)

    def write_text(
        self,
        virtual_path: str,
        content: str,
        *,
        expected_content_hash: str | None,
    ) -> str:
        path = self.resolve_public_path(virtual_path)
        require_read_before_write(path, expected_content_hash=expected_content_hash)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        _reject_symlink_parent(path, self.paths.public_root)
        _atomic_write_bytes(path, content.encode(), mode=0o640)
        return content_hash_bytes(content.encode())

    def read_bytes(self, virtual_path: str) -> bytes:
        path = self.resolve_public_path(virtual_path)
        if path.is_symlink() or not path.is_file():
            raise SandboxPathError("sandbox file does not exist or is not regular")
        return path.read_bytes()

    def content_hash(self, virtual_path: str) -> str:
        path = self.resolve_public_path(virtual_path)
        if path.is_symlink() or not path.is_file():
            raise SandboxPathError("sandbox file does not exist or is not regular")
        return _content_hash_file(path)

    def public_size_bytes(self) -> int:
        self.initialize()
        return sum(path.stat().st_size for name in PUBLIC_WORKSPACE_DIRS for path in _walk_regular_files(self.paths.public_root / name))

    def artifact_manifests_for_paths(
        self,
        *,
        paths: tuple[str, ...],
        request: SandboxOperationRequest,
        sandbox_job_id: str,
        sandbox_environment_id: str,
        source_script: str | None,
        dataset_paths: tuple[str, ...],
        stdout_truncated: bool,
        stderr_truncated: bool,
        created_at: datetime,
    ) -> tuple[SandboxArtifactManifest, ...]:
        manifests: list[SandboxArtifactManifest] = []
        for path in sorted(set(paths)):
            if not is_artifact_path(path):
                raise SandboxPathError("staged output is outside reviewable artifact roots")
            host_path = self.resolve_public_path(path)
            if host_path.is_symlink() or not host_path.is_file():
                raise SandboxPathError("staged artifact is missing or unsafe")
            mime, _ = mimetypes.guess_type(host_path.name)
            object_ref, content_hash, size_bytes = self._seal_artifact_object(host_path)
            manifests.append(
                SandboxArtifactManifest(
                    path=path,
                    object_ref=object_ref,
                    kind=mime or "application/octet-stream",
                    content_hash=content_hash,
                    source_script=source_script,
                    dataset_paths=dataset_paths,
                    sandbox_environment_id=sandbox_environment_id,
                    sandbox_job_id=sandbox_job_id,
                    mission_id=request.provenance.mission_id,
                    mission_item_seq=request.provenance.mission_item_seq,
                    network_profile=request.network_profile,
                    stdout_truncated=stdout_truncated,
                    stderr_truncated=stderr_truncated,
                    size_bytes=size_bytes,
                    created_at=created_at,
                )
            )
        return tuple(manifests)

    def _seal_artifact_object(self, source: Path) -> tuple[str, str, int]:
        self.initialize()
        content_hash = _content_hash_file(source)
        object_ref = f"sbxobj_{content_hash.removeprefix('sha256:')}"
        root = self.paths.control_root / "artifact_objects"
        target = root / f"{object_ref}.bin"
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise SandboxPathError("sandbox artifact object is unsafe")
            if _content_hash_file(target) != content_hash:
                raise SandboxPathError("sandbox artifact object failed integrity check")
            os.chmod(target, 0o400)
            return object_ref, content_hash, target.stat().st_size
        _atomic_copy_file(source, target, mode=0o400)
        if _content_hash_file(target) != content_hash:
            target.unlink(missing_ok=True)
            raise SandboxPathError("sandbox artifact changed while being sealed")
        return object_ref, content_hash, target.stat().st_size

    def read_artifact_object(
        self,
        object_ref: str,
        *,
        expected_content_hash: str,
    ) -> bytes:
        self.initialize()
        expected_ref = f"sbxobj_{expected_content_hash.removeprefix('sha256:')}"
        if object_ref != expected_ref:
            raise SandboxPathError("sandbox artifact object identity is invalid")
        root = self.paths.control_root / "artifact_objects"
        path = root / f"{object_ref}.bin"
        if path.parent != root or path.is_symlink() or not path.is_file():
            raise SandboxPathError("sandbox artifact object is unavailable")
        content = path.read_bytes()
        if not content or content_hash_bytes(content) != expected_content_hash:
            raise SandboxPathError("sandbox artifact object failed integrity check")
        return content

    def register_dataset(
        self,
        *,
        path: str,
        source: str,
        license_name: str | None,
        pii_risk: Literal["none", "possible", "confirmed", "unknown"],
        uploaded_by: str,
        observed_at: datetime,
    ) -> SandboxDatasetManifest:
        if not is_dataset_path(path):
            raise SandboxPathError("datasets must live under /workspace/datasets")
        host_path = self.resolve_public_path(path)
        if host_path.is_symlink() or not host_path.is_file():
            raise SandboxPathError("dataset must be an existing regular file")
        source_hash = _content_hash_file(host_path)
        dataset_id = f"sbxdata_{source_hash.removeprefix('sha256:')}"
        return SandboxDatasetManifest(
            dataset_id=dataset_id,
            path=path,
            source=source,
            source_hash=source_hash,
            license=license_name,
            pii_risk=pii_risk,
            uploaded_by=uploaded_by,
            observed_at=observed_at,
        )

    def create_environment_staging(self, operation_key: str) -> Path:
        self.initialize()
        staging_root = self.paths.environments_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = staging_root / operation_key
        if staging.exists():
            raise SandboxMaterializationError("environment staging already exists and requires reconciliation")
        staging.mkdir(mode=0o770)
        return staging

    def discard_environment_staging(self, staging: Path | None) -> None:
        if staging is None or not staging.exists():
            return
        staging_root = (self.paths.environments_root / ".staging").resolve()
        resolved = staging.resolve(strict=False)
        if staging_root not in resolved.parents:
            raise SandboxEnvironmentError("refusing to remove unmanaged environment staging")
        shutil.rmtree(staging)

    def create_output_staging(self, operation_key: str) -> Path:
        self.initialize()
        if not operation_key.startswith("sbxop_"):
            raise SandboxPathError("invalid operation staging key")
        sandbox_root = self.paths.workspace_root.parents[1]
        staging_root = sandbox_root / "operation_staging"
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        staging = staging_root / operation_key
        if staging.exists():
            raise SandboxMaterializationError("output staging already exists and requires reconciliation")
        for name in ARTIFACT_ROOTS:
            (staging / name).mkdir(parents=True, exist_ok=True, mode=0o770)
        return staging

    def prepare_artifact_input_mountpoints(
        self,
        *,
        staging: Path,
        paths: tuple[str, ...],
    ) -> None:
        """Create inert files required for nested read-only Docker mounts."""

        resolved_staging = self._validated_output_staging(staging)
        mountpoints: list[Path] = []
        for path in paths:
            if not is_artifact_path(path):
                raise SandboxPathError(
                    "artifact input mountpoints must live under outputs or reports"
                )
            mountpoint = resolved_staging / path.removeprefix("/workspace/")
            if mountpoint.exists() or mountpoint.is_symlink():
                raise SandboxMaterializationError(
                    "artifact input mountpoint already exists and requires reconciliation"
                )
            mountpoints.append(mountpoint)
        created: list[Path] = []
        try:
            for mountpoint in mountpoints:
                mountpoint.parent.mkdir(parents=True, exist_ok=True, mode=0o770)
                mountpoint.touch(mode=0o400, exist_ok=False)
                created.append(mountpoint)
        except OSError as exc:
            for mountpoint in reversed(created):
                mountpoint.unlink(missing_ok=True)
            raise SandboxMaterializationError(
                "failed to prepare artifact input mountpoints"
            ) from exc

    def remove_artifact_input_mountpoints(
        self,
        *,
        staging: Path,
        paths: tuple[str, ...],
    ) -> None:
        """Remove inert nested-mount files after a confirmed container exit."""

        resolved_staging = self._validated_output_staging(staging)
        mountpoints = [
            resolved_staging / path.removeprefix("/workspace/") for path in paths
        ]
        for mountpoint in mountpoints:
            if (
                mountpoint.is_symlink()
                or not mountpoint.is_file()
                or mountpoint.stat().st_size != 0
            ):
                raise SandboxMaterializationError(
                    "artifact input mountpoint changed and requires reconciliation"
                )
        try:
            for mountpoint in mountpoints:
                mountpoint.unlink()
        except OSError as exc:
            raise SandboxMaterializationError(
                "failed to remove artifact input mountpoints"
            ) from exc

    def _validated_output_staging(self, staging: Path) -> Path:
        sandbox_root = self.paths.workspace_root.parents[1].resolve()
        resolved = staging.resolve(strict=True)
        if (
            sandbox_root not in resolved.parents
            or "operation_staging" not in resolved.parts
            or not resolved.name.startswith("sbxop_")
        ):
            raise SandboxPathError("operation output staging is outside the managed root")
        return resolved

    def discard_output_staging(self, staging: Path | None) -> None:
        if staging is None or not staging.exists():
            return
        sandbox_root = self.paths.workspace_root.parents[1].resolve()
        resolved = staging.resolve(strict=False)
        if sandbox_root not in resolved.parents or "operation_staging" not in resolved.parts:
            raise SandboxPathError("refusing to remove an unmanaged staging directory")
        shutil.rmtree(staging)

    def merge_staged_outputs(
        self,
        *,
        staging: Path,
        output_base_hashes: dict[str, str],
        max_workspace_bytes: int,
    ) -> tuple[str, ...]:
        """Validate all collisions before moving operation-local outputs public."""

        sandbox_root = self.paths.workspace_root.parents[1].resolve()
        resolved_staging = staging.resolve(strict=True)
        if sandbox_root not in resolved_staging.parents or "operation_staging" not in resolved_staging.parts:
            raise SandboxPathError("operation output staging is outside the managed root")
        staged: list[tuple[str, Path, Path]] = []
        for root_name in ARTIFACT_ROOTS:
            for source in _walk_regular_files(staging / root_name):
                relative = source.relative_to(staging).as_posix()
                virtual_path = f"/workspace/{relative}"
                target = self.resolve_public_path(virtual_path)
                staged.append((virtual_path, source, target))
        staged_paths = {path for path, _, _ in staged}
        output_base_hashes = {
            path: content_hash
            for path, content_hash in output_base_hashes.items()
            if path in staged_paths
        }
        projected_size = self.public_size_bytes()
        for virtual_path, source, target in staged:
            expected = output_base_hashes.get(virtual_path)
            if target.exists():
                if target.is_symlink() or not target.is_file():
                    raise SandboxPathError("existing artifact target is unsafe")
                if expected is None:
                    raise SandboxPathError("existing artifact writes require a base content hash")
                if _content_hash_file(target) != expected:
                    raise SandboxPathError(
                        f"output base content hash is stale for {virtual_path}; "
                        "read that output path again and use its current content hash"
                    )
                projected_size -= target.stat().st_size
            elif expected is not None:
                raise SandboxPathError("artifact base hash was supplied for a missing target")
            projected_size += source.stat().st_size
        if projected_size > max_workspace_bytes:
            raise SandboxPathError("workspace quota would be exceeded by staged outputs")
        temporary_targets: list[tuple[Path, Path]] = []
        try:
            for _, source, target in staged:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
                _reject_symlink_parent(target, self.paths.public_root)
                temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.staged")
                _atomic_copy_file(source, temporary, mode=0o640)
                temporary_targets.append((temporary, target))
            for temporary, target in temporary_targets:
                os.replace(temporary, target)
        except OSError as exc:
            raise SandboxMaterializationError("failed to materialize staged sandbox outputs") from exc
        finally:
            for temporary, _ in temporary_targets:
                temporary.unlink(missing_ok=True)
        self.discard_output_staging(staging)
        return tuple(sorted(staged_paths))

    def finalize_environment(
        self,
        *,
        staging: Path,
        image_digest: str,
        runtime: str,
        requested_packages: tuple[str, ...],
        created_at: datetime,
    ) -> tuple[SandboxEnvironmentManifest, Path]:
        lock_path = staging / "requirements.lock"
        venv_path = staging / "venv"
        if not lock_path.is_file() or not venv_path.is_dir():
            raise SandboxEnvironmentError("installer did not produce a lock and environment")
        lock_content = lock_path.read_bytes()
        env_id = environment_id(
            image_digest=image_digest,
            runtime=runtime,
            lock_content=lock_content,
        )
        manifest = SandboxEnvironmentManifest(
            environment_id=env_id,
            image_digest=image_digest,
            runtime=runtime,
            lock_hash=content_hash_bytes(lock_content),
            requested_packages=requested_packages,
            created_at=created_at,
        )
        target = self.paths.environments_root / env_id
        if target.exists():
            shutil.rmtree(staging)
            return self.load_environment(env_id), target
        _atomic_write_json(
            staging / "environment-manifest.json",
            manifest.model_dump(mode="json"),
            mode=0o440,
        )
        staging.rename(target)
        _seal_tree(target)
        return manifest, target

    def load_environment(self, environment_id_value: str) -> SandboxEnvironmentManifest:
        self.initialize()
        if not environment_id_value.startswith("sbxenv_"):
            raise SandboxEnvironmentError("invalid sandbox environment id")
        path = self.paths.environments_root / environment_id_value
        if path.is_symlink() or not path.is_dir():
            raise SandboxEnvironmentError("sandbox environment does not exist")
        manifest_path = path / "environment-manifest.json"
        try:
            manifest = SandboxEnvironmentManifest.model_validate_json(manifest_path.read_text())
        except (OSError, ValueError) as exc:
            raise SandboxEnvironmentError("sandbox environment manifest is invalid") from exc
        if manifest.environment_id != environment_id_value or not manifest.sealed:
            raise SandboxEnvironmentError("sandbox environment is not sealed")
        _assert_tree_read_only(path)
        return manifest

    def environment_path(self, environment_id_value: str) -> Path:
        self.load_environment(environment_id_value)
        return self.paths.environments_root / environment_id_value

    def write_output_ref(
        self,
        *,
        stream: Literal["stdout", "stderr"],
        content: bytes,
        now: datetime,
    ) -> SandboxOutputRef:
        self.initialize()
        output_ref = f"sbxout_{secrets.token_urlsafe(24)}"
        expires_at = now + timedelta(seconds=self.output_ref_ttl_seconds)
        data_file = f"{output_ref}.bin"
        root = self.paths.control_root / "output_refs"
        _atomic_write_bytes(root / data_file, content, mode=0o600)
        metadata = _OutputRefMetadata(
            output_ref=output_ref,
            stream=stream,
            content_hash=content_hash_bytes(content),
            size_bytes=len(content),
            expires_at=expires_at,
            data_file=data_file,
        )
        _atomic_write_json(root / f"{output_ref}.json", metadata.model_dump(mode="json"), mode=0o600)
        return SandboxOutputRef(
            output_ref=output_ref,
            stream=stream,
            content_hash=metadata.content_hash,
            size_bytes=metadata.size_bytes,
            expires_at=expires_at,
        )

    def read_output_ref(self, output_ref: str, *, now: datetime | None = None) -> bytes:
        self.initialize()
        if not output_ref.startswith("sbxout_") or any(char in output_ref for char in ("/", "\\", ".")):
            raise SandboxOutputRefError("invalid output reference")
        root = self.paths.control_root / "output_refs"
        try:
            metadata = _OutputRefMetadata.model_validate_json((root / f"{output_ref}.json").read_text())
        except (OSError, ValueError) as exc:
            raise SandboxOutputRefError("output reference does not exist") from exc
        current = now or datetime.now(UTC)
        if current >= metadata.expires_at:
            self._delete_output_ref(metadata)
            raise SandboxOutputRefError("output reference has expired")
        data_path = root / metadata.data_file
        if data_path.parent != root or data_path.is_symlink() or not data_path.is_file():
            raise SandboxOutputRefError("output reference payload is invalid")
        content = data_path.read_bytes()
        if content_hash_bytes(content) != metadata.content_hash:
            raise SandboxOutputRefError("output reference payload failed integrity check")
        return content

    def prune_output_refs(self, *, now: datetime | None = None) -> int:
        self.initialize()
        current = now or datetime.now(UTC)
        removed = 0
        for path in (self.paths.control_root / "output_refs").glob("sbxout_*.json"):
            try:
                metadata = _OutputRefMetadata.model_validate_json(path.read_text())
            except (OSError, ValueError):
                continue
            if current >= metadata.expires_at:
                self._delete_output_ref(metadata)
                removed += 1
        return removed

    def _delete_output_ref(self, metadata: _OutputRefMetadata) -> None:
        root = self.paths.control_root / "output_refs"
        data_path = root / metadata.data_file
        if data_path.parent != root:
            raise SandboxOutputRefError("output reference payload path is invalid")
        data_path.unlink(missing_ok=True)
        (root / f"{metadata.output_ref}.json").unlink(missing_ok=True)


class FilesystemSandboxReceiptStore(SandboxReceiptStore):
    """Atomic provider receipt cache under the trusted control root."""

    def __init__(self, workspace: SandboxWorkspace) -> None:
        self.workspace = workspace

    async def claim(
        self,
        request: SandboxOperationRequest,
        *,
        sandbox_job_id: str,
    ) -> SandboxReceiptClaim:
        return await asyncio.to_thread(self._claim_sync, request, sandbox_job_id)

    def _claim_sync(
        self,
        request: SandboxOperationRequest,
        sandbox_job_id: str,
    ) -> SandboxReceiptClaim:
        self.workspace.initialize()
        path = self._receipt_path(request.operation_key)
        claimed_at = utc_now()
        document = _ReceiptDocument(
            state="claimed",
            operation_key=request.operation_key,
            sandbox_job_id=sandbox_job_id,
            request_hash=_request_hash(request),
            claimed_at=claimed_at,
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            existing = self._read_receipt(path)
            if existing.request_hash != document.request_hash:
                raise SandboxReceiptConflictError("operation key is already bound to a different request") from None
            if existing.state == "terminal" and existing.result is not None:
                return SandboxReceiptClaim(
                    state=SandboxReceiptState.TERMINAL,
                    acquired=False,
                    existing_result=SandboxOperationResult.model_validate(existing.result),
                    claimed_at=existing.claimed_at,
                )
            return SandboxReceiptClaim(
                state=SandboxReceiptState.CLAIMED,
                acquired=False,
                claimed_at=existing.claimed_at,
            )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(document.model_dump_json())
            handle.flush()
            os.fsync(handle.fileno())
        return SandboxReceiptClaim(
            state=SandboxReceiptState.CLAIMED,
            acquired=True,
            claimed_at=claimed_at,
        )

    async def finalize(self, result: SandboxOperationResult) -> None:
        await asyncio.to_thread(self._finalize_sync, result)

    async def get(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxOperationResult | None:
        _ = mission_id
        claim = await self.inspect(mission_id, operation_key)
        return claim.existing_result if claim is not None else None

    async def inspect(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxReceiptClaim | None:
        _ = mission_id
        return await asyncio.to_thread(self._inspect_sync, operation_key)

    def _inspect_sync(self, operation_key: str) -> SandboxReceiptClaim | None:
        path = self._receipt_path(operation_key)
        if not path.exists():
            return None
        document = self._read_receipt(path)
        if document.state == "terminal" and document.result is not None:
            return SandboxReceiptClaim(
                state=SandboxReceiptState.TERMINAL,
                acquired=False,
                existing_result=SandboxOperationResult.model_validate(document.result),
                claimed_at=document.claimed_at,
            )
        return SandboxReceiptClaim(
            state=SandboxReceiptState.CLAIMED,
            acquired=False,
            claimed_at=document.claimed_at,
        )

    def _finalize_sync(self, result: SandboxOperationResult) -> None:
        path = self._receipt_path(result.operation_key)
        existing = self._read_receipt(path)
        if existing.sandbox_job_id != result.sandbox_job_id:
            raise SandboxReceiptConflictError("sandbox job does not own this operation receipt")
        if existing.state == "terminal":
            persisted = SandboxOperationResult.model_validate(existing.result)
            if persisted != result:
                raise SandboxReceiptConflictError("terminal sandbox receipt is immutable")
            return
        terminal = existing.model_copy(update={"state": "terminal", "result": result.model_dump(mode="json")})
        _atomic_write_json(path, terminal.model_dump(mode="json"), mode=0o600)

    def _receipt_path(self, operation_key: str) -> Path:
        if not operation_key.startswith("sbxop_") or any(char in operation_key for char in ("/", "\\", ".")):
            raise SandboxReceiptConflictError("invalid sandbox operation key")
        return self.workspace.paths.control_root / "receipts" / f"{operation_key}.json"

    @staticmethod
    def _read_receipt(path: Path) -> _ReceiptDocument:
        try:
            return _ReceiptDocument.model_validate_json(path.read_text())
        except (OSError, ValueError) as exc:
            raise SandboxReceiptConflictError("sandbox receipt is corrupt or unavailable") from exc


def _request_hash(request: SandboxOperationRequest) -> str:
    # The validated operation key already binds every effect-bearing field while
    # deliberately excluding lease epochs and renewable permission metadata.
    return content_hash_bytes(request.operation_key.encode())


def _walk_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    for current_root, dir_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in tuple(dir_names):
            if (current / name).is_symlink():
                raise SandboxPathError("symlink directory found in public workspace")
        for name in file_names:
            path = current / name
            if path.is_symlink():
                raise SandboxPathError("symlink file found in public workspace")
            if path.is_file():
                files.append(path)
    return files


def _reject_symlink_parent(path: Path, public_root: Path) -> None:
    root = public_root.resolve(strict=True)
    current = path.parent
    while current != root:
        if current.is_symlink():
            raise SandboxPathError("symlink parent is forbidden")
        if root not in current.resolve(strict=False).parents and current.resolve(strict=False) != root:
            raise SandboxPathError("write target escapes public workspace")
        current = current.parent


def _atomic_write_bytes(path: Path, content: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int) -> None:
    content = (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _atomic_write_bytes(path, content, mode=mode)


def _atomic_copy_file(source: Path, destination: Path, *, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.tmp")
    try:
        with source.open("rb") as source_handle:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(descriptor, "wb") as target_handle:
                while chunk := source_handle.read(1024 * 1024):
                    target_handle.write(chunk)
                target_handle.flush()
                os.fsync(target_handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _content_hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _seal_tree(root: Path) -> None:
    for current_root, dir_names, file_names in os.walk(root, topdown=False, followlinks=False):
        current = Path(current_root)
        for name in file_names:
            path = current / name
            if path.is_symlink():
                raise SandboxEnvironmentError("environment contains a symlink")
            current_mode = stat.S_IMODE(path.stat().st_mode)
            os.chmod(path, current_mode & ~0o222)
        for name in dir_names:
            path = current / name
            if path.is_symlink():
                raise SandboxEnvironmentError("environment contains a symlink")
            current_mode = stat.S_IMODE(path.stat().st_mode)
            os.chmod(path, (current_mode | 0o555) & ~0o222)
        current_mode = stat.S_IMODE(current.stat().st_mode)
        os.chmod(current, (current_mode | 0o555) & ~0o222)


def _assert_tree_read_only(root: Path) -> None:
    for current_root, dir_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in (*dir_names, *file_names):
            path = current / name
            if path.is_symlink() or path.stat().st_mode & 0o222:
                raise SandboxEnvironmentError("sealed environment is writable or contains symlinks")
