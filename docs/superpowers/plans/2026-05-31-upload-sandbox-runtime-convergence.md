# Upload And Sandbox Runtime Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the upload gateway and lead-agent sandbox runtime hotspots into focused services while preserving existing API and subagent entry points.

**Architecture:** The upload router remains the FastAPI protocol adapter and delegates ownership checks plus upload use cases to an application service. The sandbox runtime remains the public facade for subagents and delegates dependency installation, command execution, and artifact collection to focused helpers.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, existing DataService-backed sandbox manager.

---

## File Structure

### Upload

- Create `backend/src/application/services/upload_application_service.py`
  - Owns `UploadApplicationService.upload_thread_files(...)`.
  - Accepts already injected services from the router.
  - Returns `ThreadUploadResponse` with the same response shape as today.
- Create `backend/src/services/upload_preflight_policy.py`
  - Owns file count checks, filename sanitization, content-size-limited reads, PDF/image parseability decisions.
  - Raises `HTTPException` with existing status codes and messages.
- Create `backend/src/services/thread_upload_service.py`
  - Owns thread upload directory, attachment URL/path construction, transient upload persistence.
  - Keeps `ThreadAttachment` construction out of the router.
- Create `backend/src/services/workspace_upload_service.py`
  - Owns workspace-context persistence, artifact creation, knowledge memory upsert, stored URL metadata.
  - Reuses existing low-level helpers from `src.services.workspace_uploads`.
- Create `backend/src/services/layout_preprocess_orchestrator.py`
  - Owns immediate vs async layout preprocess dispatch.
  - Keeps pending preprocess metadata and task payload construction in one place.
- Modify `backend/src/gateway/routers/uploads.py`
  - Keep `router`, `ThreadUploadResponse`, dependency injection, and request-to-service call only.
  - Keep external route `POST /threads/{thread_id}/uploads` unchanged.
- Modify `backend/tests/gateway/routers/test_uploads.py`
  - Patch new service import paths where behavior tests replace storage roots, source import, knowledge service, or workspace events.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add upload boundary guard.

### Sandbox

- Create `backend/src/agents/lead_agent/v2/sandbox_environment_installer.py`
  - Owns `ensure_python_environment(...)`, `install_dependencies(...)`, and package-installed checks.
  - Keeps install jobs `billable=False` and `network_policy="package_index_only"`.
- Create `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
  - Owns provider/manager resolution, environment acquisition, lease acquire/release, job status transitions, command execution.
  - Exposes focused operations for `smoke_check` and `run_python`.
- Create `backend/src/agents/lead_agent/v2/sandbox_runtime_session.py`
  - Owns provider/manager resolution, runtime context creation, lease acquire/release, failure status helpers.
- Create `backend/src/agents/lead_agent/v2/sandbox_script_executor.py`
  - Owns script validation, script path/hash construction, Python setup, dependency install, missing-module retry.
- Create `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
  - Owns stdout JSON parsing and markdown report/output shaping.
  - Keeps output shape stable for subagents.
- Modify `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
  - Keep `SandboxCommandExecutionError`, `require_run_python_allowed`, `run_python_smoke_check`, and `run_python_script`.
  - Delegate most implementation to installer/job runner/artifact collector.
- Modify `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`
  - Keep existing behavior tests green through the facade.
  - Add focused tests only where a helper boundary needs direct coverage.
- Modify `backend/tests/architecture/test_dataservice_boundaries.py`
  - Add sandbox runtime boundary guard.

## Task 1: Architecture Guards

**Files:**
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`

- [ ] **Step 1: Write failing upload boundary test**

Add:

```python
def test_upload_gateway_is_protocol_adapter_over_application_services() -> None:
    upload_router = SRC_ROOT / "gateway" / "routers" / "uploads.py"
    expected_files = {
        SRC_ROOT / "application" / "services" / "upload_application_service.py",
        SRC_ROOT / "services" / "upload_preflight_policy.py",
        SRC_ROOT / "services" / "thread_upload_service.py",
        SRC_ROOT / "services" / "workspace_upload_service.py",
        SRC_ROOT / "services" / "layout_preprocess_orchestrator.py",
    }
    missing = [str(path.relative_to(SRC_ROOT)) for path in expected_files if not path.exists()]
    assert not missing, f"Missing focused upload services: {missing}"

    source = upload_router.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 300
    assert "UploadApplicationService" in source
    assert "SourceLibraryImportService" not in source
    assert "KnowledgeService" not in source
    assert "persist_workspace_upload(" not in source
    assert "preprocess_file(" not in source
```

- [ ] **Step 2: Write failing sandbox boundary test**

Add:

```python
def test_sandbox_runtime_is_facade_over_installer_runner_and_artifacts() -> None:
    runtime_root = SRC_ROOT / "agents" / "lead_agent" / "v2"
    runtime_path = runtime_root / "sandbox_runtime.py"
    expected_files = {
        "sandbox_environment_installer.py",
        "sandbox_job_runner.py",
        "sandbox_artifact_collector.py",
    }
    missing = [name for name in sorted(expected_files) if not (runtime_root / name).exists()]
    assert not missing, f"Missing focused sandbox runtime services: {missing}"

    source = runtime_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 300
    assert "SandboxEnvironmentInstaller" in source
    assert "SandboxJobRunner" in source
    assert "SandboxArtifactCollector" in source
    assert "async def _install_dependencies(" not in source
    assert "await sandbox.execute_command(" not in source
```

- [ ] **Step 3: Write failing sandbox runner hotspot test**

Add:

```python
def test_sandbox_runner_does_not_become_the_new_runtime_hotspot() -> None:
    runtime_root = SRC_ROOT / "agents" / "lead_agent" / "v2"
    expected_files = {
        "sandbox_runtime_session.py",
        "sandbox_script_executor.py",
    }
    missing = [name for name in sorted(expected_files) if not (runtime_root / name).exists()]
    assert not missing, f"Missing focused sandbox runner helpers: {missing}"

    runner_source = (runtime_root / "sandbox_job_runner.py").read_text(encoding="utf-8")
    assert len(runner_source.splitlines()) < 350
    assert "SandboxRuntimeSession" in runner_source
    assert "SandboxScriptExecutor" in runner_source
```

- [ ] **Step 4: Verify red**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_upload_gateway_is_protocol_adapter_over_application_services tests/architecture/test_dataservice_boundaries.py::test_sandbox_runtime_is_facade_over_installer_runner_and_artifacts tests/architecture/test_dataservice_boundaries.py::test_sandbox_runner_does_not_become_the_new_runtime_hotspot -q
```

Expected: FAIL because the new modules do not exist yet and the hotspot files are still over the target size.

## Task 2: Upload Service Split

**Files:**
- Create: `backend/src/services/upload_preflight_policy.py`
- Create: `backend/src/services/thread_upload_service.py`
- Create: `backend/src/services/layout_preprocess_orchestrator.py`
- Create: `backend/src/services/workspace_upload_service.py`
- Create: `backend/src/application/services/upload_application_service.py`
- Modify: `backend/src/gateway/routers/uploads.py`
- Modify: `backend/tests/gateway/routers/test_uploads.py`

- [ ] **Step 1: Extract preflight policy**

Move `_MAX_UPLOAD_FILES`, `_MAX_UPLOAD_SIZE_BYTES`, `_UPLOAD_READ_CHUNK_SIZE`, `_ASYNC_PREPROCESS_THRESHOLD_BYTES`, `_read_upload_content_with_limit`, `_is_async_preprocess_pdf`, and filename sanitization calls into `UploadPreflightPolicy`.

The service must expose:

```python
class UploadPreflightPolicy:
    def validate_file_count(self, files: Sequence[UploadFile]) -> None: ...
    async def read_content(self, upload: UploadFile) -> tuple[str, bytes]: ...
    def require_literature_pdf(self, *, filename: str, upload: UploadFile) -> None: ...
    def is_parseable(self, *, filename: str, content_type: str | None) -> bool: ...
    def should_async_preprocess(self, *, filename: str, content_type: str | None, size_bytes: int) -> bool: ...
```

- [ ] **Step 2: Extract thread upload service**

Move `_thread_upload_dir`, `_attachment_url`, `_build_attachment`, and transient file persistence into `ThreadUploadService`.

The service must expose:

```python
class ThreadUploadService:
    def upload_dir(self, thread_id: str) -> Path: ...
    def attachment_url(self, thread_id: str, filename: str) -> str: ...
    def build_attachment(...) -> ThreadAttachment: ...
    def persist_transient_file(self, *, thread_id: str, filename: str, content: bytes) -> Path: ...
```

- [ ] **Step 3: Extract layout preprocess orchestration**

Move `_schedule_document_preprocess`, `_attach_workspace_preprocess_urls`, and immediate preprocess metadata handling into `LayoutPreprocessOrchestrator`.

The orchestrator must keep:

```python
async def schedule_document_preprocess(...) -> dict[str, object]: ...
async def preprocess_or_schedule(...) -> tuple[dict[str, object], bool]: ...
def attach_workspace_preprocess_urls(...) -> None: ...
```

- [ ] **Step 4: Extract workspace upload service**

Move workspace-context persistence, artifact creation, markdown preview lookup, and knowledge memory write into `WorkspaceUploadService`.

The service must expose:

```python
async def persist_context_upload(
    *,
    user_id: str,
    workspace_id: str,
    thread_id: str,
    upload_filename: str | None,
    saved_name: str,
    content_type: str | None,
    content: bytes,
    thread_path: Path,
    metadata: dict[str, object],
    artifact_service: Any,
    knowledge_service: KnowledgeService,
    task_service: Any,
    preprocess_orchestrator: LayoutPreprocessOrchestrator,
    deferred_preprocess: bool,
) -> WorkspaceUploadResult: ...
```

- [ ] **Step 5: Extract application service and slim router**

Move `_require_owned_thread`, `_require_owned_workspace`, `_ordered_refresh_targets`, literature import handling, per-file loop, and refresh event publishing into `UploadApplicationService`.

The router endpoint should construct:

```python
service = UploadApplicationService(
    thread_service=thread_service,
    workspace_service=workspace_service,
    artifact_service=artifact_service,
    task_service=task_service,
    upload_preprocessor=upload_preprocessor,
    dataservice=dataservice,
)
return await service.upload_thread_files(
    thread_id=thread_id,
    files=files,
    kind=kind,
    workspace_id=workspace_id,
    user_id=str(current_user.id),
)
```

- [ ] **Step 6: Verify upload behavior**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/gateway/routers/test_uploads.py -q
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_upload_gateway_is_protocol_adapter_over_application_services -q
```

Expected: PASS.

## Task 3: Sandbox Runtime Split

**Files:**
- Create: `backend/src/agents/lead_agent/v2/sandbox_environment_installer.py`
- Create: `backend/src/agents/lead_agent/v2/sandbox_job_runner.py`
- Create: `backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py`
- Create: `backend/src/agents/lead_agent/v2/sandbox_runtime_session.py`
- Create: `backend/src/agents/lead_agent/v2/sandbox_script_executor.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_runtime.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py`

- [ ] **Step 1: Extract installer**

Move environment setup and dependency installation into `SandboxEnvironmentInstaller`.

The installer must expose:

```python
class SandboxEnvironmentInstaller:
    async def ensure_python_environment(self, sandbox: Sandbox, *, timeout: int) -> CommandResult: ...
    async def install_dependencies(...) -> tuple[list[str], str]: ...
    def package_not_installed(self, package_spec: str, installed_packages: list[str]) -> bool: ...
```

- [ ] **Step 2: Extract artifact collector**

Move stdout JSON parsing and report/output creation into `SandboxArtifactCollector`.

The collector must expose:

```python
class SandboxArtifactCollector:
    def smoke_output(...) -> dict[str, Any]: ...
    def script_output(...) -> dict[str, Any]: ...
```

- [ ] **Step 3: Extract runtime session**

Move provider resolution, DataService manager selection, environment context, lease acquire/release, and failure status helpers into `SandboxRuntimeSession`.

The session must expose:

```python
class SandboxRuntimeSession:
    async def build_context(...) -> SandboxRuntimeContext: ...
    async def leased_sandbox(...) -> AsyncIterator[Any]: ...
```

- [ ] **Step 4: Extract script executor**

Move script validation, script path/hash planning, Python setup, dependency install, and missing-module retry into `SandboxScriptExecutor`.

The executor must expose:

```python
class SandboxScriptExecutor:
    def build_plan(...) -> SandboxScriptPlan: ...
    async def execute(...) -> SandboxScriptExecutionState: ...
```

- [ ] **Step 5: Extract job runner**

Move job creation/update and operation-level error mapping into `SandboxJobRunner`.

The runner must expose:

```python
class SandboxJobRunner:
    async def run_smoke_check(...) -> dict[str, Any]: ...
    async def run_python_script(...) -> dict[str, Any]: ...
```

- [ ] **Step 6: Slim facade**

Keep `sandbox_runtime.py` as the public API:

```python
async def run_python_smoke_check(...) -> dict[str, Any]:
    require_run_python_allowed(sandbox_policy)
    return await SandboxJobRunner(...).run_smoke_check(...)

async def run_python_script(...) -> dict[str, Any]:
    require_run_python_allowed(sandbox_policy)
    return await SandboxJobRunner(...).run_python_script(...)
```

- [ ] **Step 7: Verify sandbox behavior**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_sandbox_runtime_is_facade_over_installer_runner_and_artifacts tests/architecture/test_dataservice_boundaries.py::test_sandbox_runner_does_not_become_the_new_runtime_hotspot -q
```

Expected: PASS.

## Task 4: Phase Verification And Commit

**Files:**
- Verify all changed backend files.

- [ ] **Step 1: Format/lint**

Run:

```bash
cd backend && .venv/bin/python -m ruff check src/gateway/routers/uploads.py src/application/services/upload_application_service.py src/services/upload_preflight_policy.py src/services/thread_upload_service.py src/services/layout_preprocess_orchestrator.py src/services/workspace_upload_service.py src/agents/lead_agent/v2/sandbox_runtime.py src/agents/lead_agent/v2/sandbox_environment_installer.py src/agents/lead_agent/v2/sandbox_job_runner.py src/agents/lead_agent/v2/sandbox_artifact_collector.py src/agents/lead_agent/v2/sandbox_runtime_session.py src/agents/lead_agent/v2/sandbox_script_executor.py src/agents/lead_agent/v2/sandbox_errors.py tests/architecture/test_dataservice_boundaries.py tests/gateway/routers/test_uploads.py tests/agents/lead_agent/v2/test_sandbox_runtime.py
```

Expected: PASS.

- [ ] **Step 2: Focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py tests/gateway/routers/test_uploads.py tests/agents/lead_agent/v2/test_sandbox_runtime.py -q
```

Expected: PASS.

- [ ] **Step 3: Backend regression**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: PASS.

- [ ] **Step 4: Diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files changed before commit.

- [ ] **Step 5: Commit and push**

Run:

```bash
git add backend/src/gateway/routers/uploads.py backend/src/application/services/upload_application_service.py backend/src/services/upload_preflight_policy.py backend/src/services/thread_upload_service.py backend/src/services/layout_preprocess_orchestrator.py backend/src/services/workspace_upload_service.py backend/src/agents/lead_agent/v2/sandbox_runtime.py backend/src/agents/lead_agent/v2/sandbox_environment_installer.py backend/src/agents/lead_agent/v2/sandbox_job_runner.py backend/src/agents/lead_agent/v2/sandbox_artifact_collector.py backend/src/agents/lead_agent/v2/sandbox_runtime_session.py backend/src/agents/lead_agent/v2/sandbox_script_executor.py backend/src/agents/lead_agent/v2/sandbox_errors.py backend/tests/architecture/test_dataservice_boundaries.py backend/tests/gateway/routers/test_uploads.py backend/tests/agents/lead_agent/v2/test_sandbox_runtime.py docs/superpowers/plans/2026-05-31-upload-sandbox-runtime-convergence.md docs/superpowers/specs/2026-05-31-architecture-hotspot-convergence-design.md
git commit -m "refactor: split upload and sandbox runtime services"
git push
```

Expected: branch pushed with Phase 3 commit.

## Self-Review

- Spec coverage: covers Phase 3 upload router split, sandbox runtime split, sandbox runner anti-hotspot guard, one-workspace-one-sandbox preservation through `WorkspaceSandboxManager`, install-not-billed behavior, and job/run billing boundary through existing created-job assertions.
- Placeholder scan: no TODO/TBD/fill-later markers.
- Type consistency: upload response remains `ThreadUploadResponse`; sandbox facade exports remain unchanged for `SandboxPythonSubagent`.
- Risk: Upload tests currently patch symbols in `src.gateway.routers.uploads`; those patches must move to the new service modules as implementation changes.
