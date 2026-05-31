# Workspace Sandbox Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one persistent workspace-level sandbox environment with automatic Python dependency installation, job-level billing, and DataService-owned audit records.

**Architecture:** DataService owns sandbox environment/job/lease facts; Lead Agent runtime owns workspace sandbox resolution, dependency installation, and retry; Docker provider keeps short-lived containers but mounts a stable workspace directory. Credit reservations remain per sandbox run job, while install jobs are audited and unbilled.

**Tech Stack:** Python 3.13, FastAPI/DataService, SQLAlchemy async, Alembic, Pydantic v2, Docker SDK, pytest.

---

## File Structure

- Modify `backend/src/dataservice/domains/sandbox/models.py`: add active-environment invariant index, job `operation` and `billable`, and lease model.
- Modify `backend/src/dataservice/domains/sandbox/contracts.py`: expose operation/billable/lease payload fields.
- Modify `backend/src/dataservice/domains/sandbox/policy.py`: make job validation operation-aware and validate package specs.
- Modify `backend/src/dataservice/domains/sandbox/repository.py`: add active environment helpers and lease CRUD.
- Modify `backend/src/dataservice/domains/sandbox/projection.py`: project new job fields and lease fields.
- Modify `backend/src/dataservice/domains/sandbox/service.py`: deterministic workspace sandbox id, active environment guard, job operation validation, lease acquire/renew/release.
- Modify `backend/src/dataservice_app/routers/sandbox.py`: expose lease endpoints.
- Modify `backend/src/dataservice_client/contracts/sandbox.py`: mirror DataService contracts for runtime use.
- Modify `backend/src/dataservice_client/client.py`: add sandbox lease client methods.
- Add `backend/alembic/versions/079_workspace_sandbox_convergence.py`: schema migration.
- Modify `backend/src/sandbox/providers/local.py`: allow `/workspace` virtual paths.
- Modify `backend/src/sandbox/providers/docker.py`: mount `/workspace`, support network profiles, preserve short-lived containers.
- Add `backend/src/agents/lead_agent/v2/workspace_sandbox.py`: DataService-backed workspace sandbox manager, lease wrapper, manifest helpers, dependency installer.
- Modify `backend/src/agents/lead_agent/v2/sandbox_runtime.py`: workspace-scoped provider key, `/workspace` paths, automatic dependency install/retry, job recording.
- Modify `backend/src/subagents/v2/types/sandbox.py`: pass dependency hints and sandbox job metadata through tool output and billing metadata.
- Modify `backend/src/dataservice/domains/credit/service.py`: prevent normal consumption from spending through reserved credits.
- Modify `backend/src/services/credit_service.py`: admission checks use spendable balance.
- Modify `docs/current/architecture.md` and `docs/current/workspace-current-state.md`: document single workspace sandbox behavior after implementation.
- Test files:
  - `backend/tests/dataservice/test_sandbox_domain.py`
  - `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`
  - `backend/tests/sandbox/test_docker_provider.py`
  - `backend/tests/sandbox/test_local_sandbox.py`
  - `backend/tests/dataservice/test_credit_domain.py`
  - `backend/tests/services/test_credit_service.py`

---

### Task 1: DataService Sandbox Contract And Schema

**Files:**
- Modify: `backend/src/dataservice/domains/sandbox/models.py`
- Modify: `backend/src/dataservice/domains/sandbox/contracts.py`
- Modify: `backend/src/dataservice/domains/sandbox/projection.py`
- Modify: `backend/src/dataservice/domains/sandbox/repository.py`
- Modify: `backend/src/dataservice/domains/sandbox/service.py`
- Modify: `backend/src/dataservice_app/routers/sandbox.py`
- Modify: `backend/src/dataservice_client/contracts/sandbox.py`
- Modify: `backend/src/dataservice_client/client.py`
- Create: `backend/alembic/versions/079_workspace_sandbox_convergence.py`
- Test: `backend/tests/dataservice/test_sandbox_domain.py`

- [ ] **Step 1: Write failing DataService tests**

Add these tests to `backend/tests/dataservice/test_sandbox_domain.py`:

```python
@pytest.mark.asyncio
async def test_get_or_create_environment_uses_workspace_sandbox_identity() -> None:
    service, repository, _, _ = _service()

    first = await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(workspace_id="ws-1", created_by="lead-agent")
    )
    second = await service.get_or_create_environment(
        SandboxEnvironmentCreateCommand(workspace_id="ws-1", created_by="lead-agent")
    )

    assert first.id == second.id
    assert first.sandbox_id == "workspace-ws-1"
    assert first.metadata_json["provider_key"] == "workspace-ws-1"
    assert len(repository.environments) == 1


@pytest.mark.asyncio
async def test_create_environment_rejects_second_active_workspace_environment() -> None:
    service, _, _, _ = _service()
    await service.create_environment(SandboxEnvironmentCreateCommand(workspace_id="ws-1"))

    with pytest.raises(DataServiceValidationError, match="active sandbox environment already exists"):
        await service.create_environment(
            SandboxEnvironmentCreateCommand(workspace_id="ws-1", sandbox_id="another")
        )


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
```

Also update `FakeSandboxRepository.create_job()` defaults to include:

```python
"operation": values.get("operation", "run_python"),
"billable": values.get("billable", True),
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py -q
```

Expected: FAIL because projections/contracts do not expose `operation`, `billable`, deterministic sandbox ids, or active-environment rejection.

- [ ] **Step 3: Implement schema and contracts**

In `backend/src/dataservice/domains/sandbox/models.py`, add imports and fields:

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text

Index(
    "uq_sandbox_environments_one_active_workspace",
    "workspace_id",
    unique=True,
    postgresql_where=text("state = 'active'"),
    sqlite_where=text("state = 'active'"),
),

operation: Mapped[str] = mapped_column(String(50), nullable=False, default="run_python", server_default="run_python")
billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
```

Add `SandboxLeaseRecord`:

```python
class SandboxLeaseRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sandbox_leases"
    __table_args__ = (
        Index("uq_sandbox_leases_workspace", "workspace_id", unique=True),
        Index("ix_sandbox_leases_expires_at", "expires_at"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    sandbox_environment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sandbox_environments.id", ondelete="CASCADE"), nullable=True)
    holder_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    holder_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_token: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
```

In contracts/client contracts add:

```python
operation: str = Field(default="run_python", pattern="^(run_python|smoke_check|install_dependencies)$")
billable: bool = True
```

and lease create/release/projection Pydantic models with `workspace_id`, `sandbox_environment_id`, `holder_job_id`, `holder_execution_id`, `lease_token`, `ttl_seconds`, `metadata_json`.

- [ ] **Step 4: Implement service behavior**

In `SandboxDataDomainService`, add deterministic id helper:

```python
def _workspace_sandbox_id(workspace_id: str) -> str:
    return f"workspace-{workspace_id}"[:100]
```

Use it in `create_environment()` when `command.sandbox_id` is absent, add `metadata_json.provider_key`, and reject a second active environment:

```python
if command.state == "active":
    existing = await self.repository.get_active_environment(command.workspace_id)
    if existing is not None:
        raise DataServiceValidationError("active sandbox environment already exists", detail={"workspace_id": command.workspace_id})
```

In `get_or_create_environment()`, return the existing active record; otherwise call `create_environment()`.

Pass `operation` and `billable` into `create_job()`, and project them in `job_to_projection()`.

Add lease repository/service/router/client methods:

```python
async def acquire_lease(command: SandboxLeaseAcquireCommand) -> SandboxLeaseProjection:
    raise NotImplementedError


async def renew_lease(command: SandboxLeaseRenewCommand) -> SandboxLeaseProjection | None:
    raise NotImplementedError


async def release_lease(command: SandboxLeaseReleaseCommand) -> bool:
    raise NotImplementedError
```

Acquire behavior: if no row or row expired, create/update lease; if the same `lease_token` owns it, renew; otherwise raise `DataServiceValidationError("workspace sandbox is busy")`.

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/079_workspace_sandbox_convergence.py`:

```python
"""workspace sandbox convergence

Revision ID: 079_workspace_sandbox_convergence
Revises: 078_model_catalog_image_category
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "079_workspace_sandbox_convergence"
down_revision = "078_model_catalog_image_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sandbox_job_records", sa.Column("operation", sa.String(length=50), server_default="run_python", nullable=False))
    op.add_column("sandbox_job_records", sa.Column("billable", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_index(
        "uq_sandbox_environments_one_active_workspace",
        "sandbox_environments",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "sandbox_leases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_environment_id", sa.String(length=36), nullable=True),
        sa.Column("holder_job_id", sa.String(length=36), nullable=False),
        sa.Column("holder_execution_id", sa.String(length=36), nullable=True),
        sa.Column("lease_token", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sandbox_environment_id"], ["sandbox_environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_sandbox_leases_workspace", "sandbox_leases", ["workspace_id"], unique=True)
    op.create_index("ix_sandbox_leases_expires_at", "sandbox_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sandbox_leases_expires_at", table_name="sandbox_leases")
    op.drop_index("uq_sandbox_leases_workspace", table_name="sandbox_leases")
    op.drop_table("sandbox_leases")
    op.drop_index("uq_sandbox_environments_one_active_workspace", table_name="sandbox_environments")
    op.drop_column("sandbox_job_records", "billable")
    op.drop_column("sandbox_job_records", "operation")
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/dataservice/domains/sandbox backend/src/dataservice_app/routers/sandbox.py backend/src/dataservice_client/contracts/sandbox.py backend/src/dataservice_client/client.py backend/alembic/versions/079_workspace_sandbox_convergence.py backend/tests/dataservice/test_sandbox_domain.py
git commit -m "feat: converge sandbox dataservice contracts"
```

---

### Task 2: Operation-Aware Sandbox Validation

**Files:**
- Modify: `backend/src/dataservice/domains/sandbox/policy.py`
- Modify: `backend/src/dataservice/domains/sandbox/service.py`
- Test: `backend/tests/dataservice/test_sandbox_domain.py`

- [ ] **Step 1: Write failing validation tests**

Add:

```python
def test_install_dependency_contract_allows_workspace_venv_pip_install() -> None:
    validate_python_job_contract(
        operation="install_dependencies",
        language="python",
        command="/workspace/.wenjin/env/python/bin/python -m pip install scikit-learn pandas>=2",
        policy_json={"allow_package_install": True},
        package_specs=["scikit-learn", "pandas>=2"],
    )


@pytest.mark.parametrize("package_spec", ["https://example.com/pkg.whl", "git+https://example.com/repo.git", "../pkg", "-r requirements.txt", "pkg; os_name == 'posix'"])
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py::test_install_dependency_contract_allows_workspace_venv_pip_install tests/dataservice/test_sandbox_domain.py::test_install_dependency_contract_rejects_unsafe_package_specs tests/dataservice/test_sandbox_domain.py::test_run_python_contract_allows_workspace_venv_python -q
```

Expected: FAIL because `operation` and venv interpreter validation are unsupported.

- [ ] **Step 3: Implement operation-aware validator**

Update `validate_python_job_contract()` signature:

```python
def validate_python_job_contract(
    *,
    operation: str = "run_python",
    language: str,
    command: str,
    policy_json: dict[str, Any],
    package_specs: list[str] | None = None,
) -> None:
```

Add helpers:

```python
_SAFE_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\\[[A-Za-z0-9_,.-]+\\])?(?:\\s*(?:==|!=|~=|>=|<=|>|<)\\s*[A-Za-z0-9_.!*+-]+)?$")
_WORKSPACE_VENV_PYTHON = "/workspace/.wenjin/env/python/bin/python"


def validate_package_specs(package_specs: list[str]) -> list[str]:
    normalized = []
    for raw in package_specs:
        value = " ".join(str(raw).strip().split())
        if not value or "://" in value or value.startswith(("-", ".", "/")) or "@" in value or ";" in value:
            raise DataServiceValidationError("Unsafe sandbox package spec", detail={"package": raw})
        if not _SAFE_PACKAGE_RE.match(value):
            raise DataServiceValidationError("Unsafe sandbox package spec", detail={"package": raw})
        normalized.append(value)
    return normalized
```

Allow Python entrypoints:

```python
allowed_python_entrypoints = {"python", "python3", _WORKSPACE_VENV_PYTHON}
```

For `install_dependencies`, require `allow_package_install` and command tokens shaped as `[python, "-m", "pip", "install", package_spec_1, package_spec_2]` or `[python, "-m", "pip", "show", package_name_1, package_name_2]` with package spec validation.

- [ ] **Step 4: Pass operation/package specs from service**

In `SandboxDataDomainService.create_job()`:

```python
metadata_json = dict(command.metadata_json or {})
validate_python_job_contract(
    operation=command.operation,
    language=command.language,
    command=command.command,
    policy_json=policy_json,
    package_specs=list(metadata_json.get("packages") or []),
)
```

- [ ] **Step 5: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice/domains/sandbox/policy.py backend/src/dataservice/domains/sandbox/service.py backend/tests/dataservice/test_sandbox_domain.py
git commit -m "feat: validate sandbox operations"
```

---

### Task 3: Docker Provider Network Profiles And Workspace Mount

**Files:**
- Modify: `backend/src/sandbox/providers/local.py`
- Modify: `backend/src/sandbox/providers/docker.py`
- Test: `backend/tests/sandbox/test_docker_provider.py`
- Test: `backend/tests/sandbox/test_local_sandbox.py`

- [ ] **Step 1: Write failing provider tests**

In `backend/tests/sandbox/test_docker_provider.py`, update expectations and add install profile test:

```python
assert (tmp_path / "thread-1" / "workspace").exists()
assert (tmp_path / "thread-1" / "workspace" / ".wenjin" / "env").exists()
assert kwargs["working_dir"] == "/workspace"
assert kwargs["network_disabled"] is True
assert "/workspace" in [volume["bind"] for volume in kwargs["volumes"].values()]


@pytest.mark.asyncio
async def test_docker_sandbox_install_command_uses_package_index_network(tmp_path):
    docker_client = _FakeDockerClient()
    provider = DockerSandboxProvider(base_dir=str(tmp_path), image="wenjin/sandbox:test", docker_client=docker_client)
    sandbox = await provider.acquire("workspace-ws-1")

    await sandbox.execute_command("python -m pip show pandas", network_profile="package_index_only")

    kwargs = docker_client.run_container.await_args.kwargs
    assert kwargs["network_disabled"] is False
    assert kwargs["labels"]["wenjin.sandbox.network_profile"] == "package_index_only"
```

In `backend/tests/sandbox/test_local_sandbox.py`, add:

```python
def test_local_sandbox_allows_workspace_virtual_paths(tmp_path):
    sandbox = LocalSandbox(id="sandbox-1", path_mappings={"/workspace": str(tmp_path / "workspace")})
    assert sandbox._resolve_path("/workspace/analysis.py").endswith("analysis.py")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_docker_provider.py tests/sandbox/test_local_sandbox.py -q
```

Expected: FAIL because `/workspace` and `network_profile` are unsupported.

- [ ] **Step 3: Implement provider changes**

In `LocalSandbox`:

```python
ALLOWED_VIRTUAL_PREFIXES = frozenset(["/mnt/user-data", "/workspace"])
self._workspace_path = path_mappings.get("/workspace") or path_mappings.get("/mnt/user-data/workspace")
```

In `DockerSandbox`:

```python
_CONTAINER_WORKSPACE_ROOT = "/workspace"

async def execute_command(self, command: str, timeout: int = 300, *, network_profile: str = "none") -> CommandResult:
    network_disabled = network_profile == "none"
```

In `DockerSandboxProvider.acquire()` create:

```python
workspace_path = Path(self.base_dir) / thread_id / "workspace"
for subdir in (".wenjin/env", ".wenjin/cache", "datasets", "scripts", "outputs"):
    (workspace_path / subdir).mkdir(parents=True, exist_ok=True)
path_mappings = {"/workspace": str(workspace_path)}
```

Pass Docker labels:

```python
"wenjin.sandbox.network_profile": network_profile,
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_docker_provider.py tests/sandbox/test_local_sandbox.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/sandbox/providers/local.py backend/src/sandbox/providers/docker.py backend/tests/sandbox/test_docker_provider.py backend/tests/sandbox/test_local_sandbox.py
git commit -m "feat: add workspace sandbox docker profiles"
```

---

### Task 4: Workspace Sandbox Runtime Manager

**Files:**
- Create: `backend/src/agents/lead_agent/v2/workspace_sandbox.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`

- [ ] **Step 1: Write failing runtime manager tests**

Add fake manager and assertions:

```python
class _FakeWorkspaceSandboxManager:
    def __init__(self) -> None:
        self.created_jobs = []
        self.updated_jobs = []

    async def get_or_create_environment(self, *, workspace_id, sandbox_policy, resource_limits, runtime_image):
        return type("Env", (), {"id": "env-1", "sandbox_id": f"workspace-{workspace_id}", "metadata_json": {"provider_key": f"workspace-{workspace_id}"}})()

    async def create_job(self, **kwargs):
        self.created_jobs.append(kwargs)
        return type("Job", (), {"id": "job-1", "operation": kwargs["operation"]})()

    async def update_job(self, job_id, **kwargs):
        self.updated_jobs.append({"job_id": job_id, **kwargs})

    async def acquire_lease(self, **kwargs):
        return None

    async def release_lease(self, **kwargs):
        return None
```

Update `test_run_python_script_writes_script_and_returns_report()` to pass `manager=manager` and assert:

```python
assert provider.acquired == ["workspace-ws-1"]
assert provider.sandbox.files["/workspace/scripts/analysis_probe.py"].startswith("import json")
assert provider.sandbox.commands[0][0] == "/workspace/.wenjin/env/python/bin/python /workspace/scripts/analysis_probe.py"
assert result["sandbox_environment_id"] == "env-1"
assert result["sandbox_job_id"] == "job-1"
assert manager.created_jobs[0]["operation"] == "run_python"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: FAIL because manager and workspace-scoped key are unsupported.

- [ ] **Step 3: Implement manager**

Create `workspace_sandbox.py` with:

```python
class WorkspaceSandboxManager:
    def __init__(self, dataservice: AsyncDataServiceClient | None = None) -> None:
        self._dataservice = dataservice

    async def get_or_create_environment(
        self,
        *,
        workspace_id: str,
        sandbox_policy: dict[str, Any],
        resource_limits: dict[str, Any],
        runtime_image: str,
    ) -> SandboxEnvironmentPayload:
        raise NotImplementedError

    async def create_job(
        self,
        *,
        workspace_id: str,
        environment_id: str,
        execution_id: str,
        node_id: str,
        operation: str,
        billable: bool,
        command: str,
        runtime_image: str,
        sandbox_policy: dict[str, Any],
        resource_limits: dict[str, Any],
        metadata: dict[str, Any],
    ) -> SandboxJobPayload:
        raise NotImplementedError

    async def update_job(
        self,
        job_id: str,
        *,
        status: str,
        exit_code: int | None = None,
        error_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError

    async def acquire_lease(self, *, workspace_id: str, environment_id: str, job_id: str, execution_id: str) -> str:
        raise NotImplementedError

    async def release_lease(self, *, workspace_id: str, lease_token: str) -> None:
        raise NotImplementedError
```

Use `dataservice_client()` when no client is injected.

Add helper:

```python
def workspace_provider_key(workspace_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", f"workspace-{workspace_id}")[:100]
```

- [ ] **Step 4: Update sandbox runtime**

In `sandbox_runtime.py`:

```python
def _workspace_sandbox_key(*, workspace_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", f"workspace-{workspace_id}")[:100]
```

Use `/workspace/scripts/{safe_name}` and venv Python:

```python
script_path = f"/workspace/scripts/{safe_name}"
command = f"/workspace/.wenjin/env/python/bin/python {script_path}"
```

Before executing, call manager `get_or_create_environment()`, `create_job()`, `acquire_lease()`, `update_job(running)`, and release lease in `finally`.

- [ ] **Step 5: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/lead_agent/v2/workspace_sandbox.py backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py
git commit -m "feat: add workspace sandbox runtime manager"
```

---

### Task 5: Automatic Dependency Installation And Retry

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/workspace_sandbox.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Modify: `backend/src/subagents/v2/types/sandbox.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`

- [ ] **Step 1: Write failing dependency tests**

Add a sequential fake sandbox:

```python
class _SequenceSandbox(_FakeSandbox):
    def __init__(self, results):
        super().__init__(results[0])
        self.results = list(results)

    async def execute_command(self, command: str, timeout: int = 300, **kwargs) -> CommandResult:
        self.commands.append((command, timeout, kwargs))
        return self.results.pop(0)
```

Add test:

```python
@pytest.mark.asyncio
async def test_run_python_script_installs_dependency_hint_before_execution() -> None:
    provider = _FakeProvider(CommandResult(stdout="Name: scikit-learn\nVersion: 1.6.1\n", stderr="", exit_code=0))
    manager = _FakeWorkspaceSandboxManager()

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import sklearn\nprint('ok')\n",
        script_name="analysis_probe.py",
        dependency_hints=["scikit-learn"],
        provider=provider,
        manager=manager,
    )

    commands = [item[0] for item in provider.sandbox.commands]
    assert any("pip install scikit-learn" in command for command in commands)
    assert result["dependency_install"]["packages"] == ["scikit-learn"]
    assert result["dependency_install"]["billable"] is False
```

Add retry test with first script run failing:

```python
@pytest.mark.asyncio
async def test_run_python_script_auto_installs_missing_module_and_retries() -> None:
    provider = _SequenceProvider([
        CommandResult(stdout="", stderr="ModuleNotFoundError: No module named 'sklearn'", exit_code=1),
        CommandResult(stdout="Name: scikit-learn\nVersion: 1.6.1\n", stderr="", exit_code=0),
        CommandResult(stdout='{"ok": true}', stderr="", exit_code=0),
    ])

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import sklearn\nprint('ok')\n",
        script_name="analysis_probe.py",
        dependency_hints=[],
        provider=provider,
        manager=_FakeWorkspaceSandboxManager(),
    )

    assert result["status"] == "completed"
    assert result["dependency_install"]["packages"] == ["scikit-learn"]
    assert result["retry_count"] == 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: FAIL because dependency installer and retry are missing.

- [ ] **Step 3: Implement dependency helpers**

In `workspace_sandbox.py`:

```python
MODULE_TO_PACKAGE = {"sklearn": "scikit-learn", "PIL": "pillow", "cv2": "opencv-python", "yaml": "PyYAML", "bs4": "beautifulsoup4", "skimage": "scikit-image", "dateutil": "python-dateutil"}
MISSING_MODULE_RE = re.compile(r"No module named ['\"]([^'\"]+)['\"]")
```

Add:

```python
def packages_from_dependency_hints(hints: list[str]) -> list[str]:
    return validate_package_specs(hints)


def package_from_stderr(stderr: str) -> str | None:
    match = MISSING_MODULE_RE.search(stderr or "")
    if not match:
        return None
    module = match.group(1).split(".")[0]
    return MODULE_TO_PACKAGE.get(module, module)


async def install_python_packages(
    sandbox: Any,
    packages: list[str],
    timeout: int,
    manager: WorkspaceSandboxManager,
    environment: SandboxEnvironmentPayload,
    execution_id: str,
    node_id: str,
) -> dict[str, Any]:
    raise NotImplementedError
```

Installer command:

```python
"/workspace/.wenjin/env/python/bin/python -m pip install " + " ".join(shlex.quote(pkg) for pkg in packages)
```

Run with `network_profile="package_index_only"`.

- [ ] **Step 4: Wire runtime install and retry**

In `run_python_script()`:

1. Normalize `dependency_hints`.
2. Install hints before running script.
3. On `ModuleNotFoundError`, install mapped package and retry up to two times.
4. Return `dependency_install`, `retry_count`, `sandbox_environment_id`, `sandbox_job_id`.

- [ ] **Step 5: Pass dependency hints from subagent**

In `SandboxPythonSubagent.run()` pass:

```python
dependency_hints=list(ctx.inputs.get("dependency_hints") or [])
```

Add dependency install summary to tool call args/output.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/lead_agent/v2/workspace_sandbox.py backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/src/subagents/v2/types/sandbox.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py
git commit -m "feat: auto-install sandbox dependencies"
```

---

### Task 6: Credit Reservation Spendable Balance Fix

**Files:**
- Modify: `backend/src/dataservice/domains/credit/service.py`
- Modify: `backend/src/services/credit_service.py`
- Test: `backend/tests/dataservice/test_credit_domain.py`
- Test: `backend/tests/services/test_credit_service.py`

- [ ] **Step 1: Write failing credit tests**

In `backend/tests/dataservice/test_credit_domain.py` add:

```python
@pytest.mark.asyncio
async def test_record_consumption_respects_reserved_credits() -> None:
    user = SimpleNamespace(id="user-1", credits=10, reserved_credits=8, total_credits_spent=0)
    service = _service_with_user(user)

    with pytest.raises(CreditOverdraftLimitError):
        await service.record_consumption(
            user_id="user-1",
            transaction_type=CreditTransactionType.WORKFLOW_CONSUME,
            amount=3,
            description="charge",
            metadata={"max_overdraft_credits": 0},
        )
```

In `backend/tests/services/test_credit_service.py`, add a fake client spendable test:

```python
@pytest.mark.asyncio
async def test_can_start_sandbox_operation_uses_spendable_balance() -> None:
    client = _FakeCreditDataService(balance=10, reserved_balance=10)
    service = CreditService(dataservice=client)

    assert await service.can_start_sandbox_operation("user-1", "run_python") is False
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_credit_domain.py tests/services/test_credit_service.py -q
```

Expected: FAIL because normal consumption and admission checks ignore reservations.

- [ ] **Step 3: Implement DataService spendable check**

In `record_consumption()`:

```python
reserved_before = int(getattr(user, "reserved_credits", 0) or 0)
spendable_before = balance_before - reserved_before
projected_spendable = spendable_before - credits_to_charge
overdraft_floor = -_max_overdraft_credits(metadata)
if projected_spendable < overdraft_floor:
    raise CreditOverdraftLimitError("credit overdraft limit exceeded")
```

Do not subtract from `reserved_credits` for normal consumption.

- [ ] **Step 4: Implement service spendable helper**

Add to `CreditService`:

```python
async def get_spendable_balance(self, user_id: str) -> int:
    summary = await self.get_credit_summary(user_id)
    return int(summary.get("credits", 0) or 0) - int(summary.get("reserved_credits", 0) or 0)
```

Use it in `can_start_thread_turn()`, `can_start_feature_task()`, and `can_start_sandbox_operation()`.

- [ ] **Step 5: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_credit_domain.py tests/services/test_credit_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice/domains/credit/service.py backend/src/services/credit_service.py backend/tests/dataservice/test_credit_domain.py backend/tests/services/test_credit_service.py
git commit -m "fix: respect reserved credits in consumption"
```

---

### Task 7: Documentation And Verification

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Test: targeted backend tests and frontend typecheck

- [ ] **Step 1: Update current architecture docs**

Add to `docs/current/architecture.md` non-negotiable boundaries:

```markdown
40. Sandbox runtime is workspace-scoped: one active sandbox environment per workspace, many sandbox jobs, persistent files/dependency environment, no persistent container processes.
41. Sandbox dependency installation is owned by Lead Agent sandbox runtime. Subagents may pass dependency hints but must not execute package-manager shell commands directly.
42. Sandbox install jobs are audited and unbilled; sandbox run jobs remain billable through credit reservation and settlement.
```

Update `docs/current/workspace-current-state.md` section 4:

```markdown
Sandbox 是 Lead Agent 内部执行基座。每个 workspace 最多一个 active sandbox environment；实验代码、数据集、输出和 Python 依赖环境在该 workspace sandbox 内持续存在。每次实验是独立 sandbox job，短生命周期 Docker 容器执行后销毁，进程不跨 job 保留。
```

- [ ] **Step 2: Run targeted backend tests**

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/sandbox/test_docker_provider.py tests/sandbox/test_local_sandbox.py tests/dataservice/test_credit_domain.py tests/services/test_credit_service.py tests/subagents -q
```

Expected: FAIL if `tests/subagents` is absent. Use the concrete command below for this repository:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_domain.py tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/sandbox/test_docker_provider.py tests/sandbox/test_local_sandbox.py tests/dataservice/test_credit_domain.py tests/services/test_credit_service.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broader existing regression set**

```bash
cd backend && .venv/bin/python -m pytest tests/execution/test_engine.py tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/gateway/routers/test_admin_pricing.py tests/gateway/routers/test_admin_models.py -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend typecheck**

```bash
cd frontend && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Final review**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files modified before final commit.

- [ ] **Step 6: Commit**

```bash
git add docs/current/architecture.md docs/current/workspace-current-state.md
git commit -m "docs: document workspace sandbox runtime"
```
