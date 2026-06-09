# Workspace Sandbox Filesystem Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the common `/workspace` filesystem contract so every Wenjin workspace sandbox gives agents clear writable destinations, keeps runtime/guidance files out of user artifact review, and exposes stable path semantics to Lead/Subagent context.

**Architecture:** Keep `backend/src/sandbox/workspace_layout.py` as the only filesystem source of truth. Providers create the tree through `ensure_workspace_sandbox_layout()`, harness/context code consumes `build_agent_workspace_contract()`, and artifact discovery/review uses the same protected/internal/guidance classification. Workspace-type differences remain profile guidance only, not separate provider layouts.

**Tech Stack:** Python 3.13, pytest, ruff, existing DataService sandbox metadata, existing Wenjin Harness file/Python tools.

---

## Scope Guard

Do this:

- Keep one common `/workspace` tree for `thesis`, `sci`, `proposal`, `software_copyright`, and `patent`.
- Add guidance files only when they reduce agent confusion and do not create review noise.
- Make path semantics machine-readable: workspace, dataset, script, artifact, scratch, protected, internal, guidance.
- Use TDD for every behavior change.
- Update the native harness release gate when a new regression suite becomes part of the contract.

Do not do this:

- Do not add Codex SDK, deer-flow runtime, cc-switch, ACP workspace, or a second sandbox root.
- Do not introduce `/mnt/user-data` aliases into new Wenjin harness paths.
- Do not open generic `sandbox.run_command`.
- Do not make outputs/reports guidance files appear as generated artifacts.

## External Lessons To Carry In

- Codex keeps command execution policy explicit and uses structured exec params instead of hidden shell strings. Wenjin should keep using argv-first audit and explicit sandbox policy metadata.
- Codex separates workspace-write policy from runtime/internal state. Wenjin should keep `.wenjin/**` and `/workspace/outputs/harness/**` invisible to model file tools.
- deer-flow has many small regression tests around virtual path mapping, traversal rejection, output truncation, and host path masking. Wenjin should keep adding compact regression tests rather than relying on broad smoke tests.
- deer-flow's guidance around "default workspace directory" is useful, but Wenjin should express it as `/workspace` contract JSON and guidance files, not as a parallel mount scheme.

## File Structure

- Modify `backend/src/sandbox/workspace_layout.py`: add guidance file constants, central guidance path classification, optional path class map, and profile validation helpers.
- Modify `backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`: skip all layout guidance paths via the central helper.
- Modify `backend/src/agents/harness/context_assembly.py`: project path class metadata from `build_agent_workspace_contract()` instead of relying only on prose rules.
- Modify `backend/tests/sandbox/test_workspace_layout.py`: assert guidance files are created/preserved, profile paths stay in valid roots, and guidance paths are not reviewable artifacts.
- Modify `backend/tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py`: assert outputs/reports README files are not discovered as artifacts.
- Modify `backend/tests/agents/harness/test_context_assembly.py`: assert harness context exposes path classes and guidance paths.
- Modify `docs/current/architecture.md`: document guidance path behavior and path class metadata.
- Modify `docs/current/native-harness-convergence-audit.md`: record verification for this hardening slice.

---

### Task 1: Add Outputs/Reports Guidance Without Artifact Noise

**Files:**
- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py`
- Docs: `docs/current/architecture.md`
- Docs: `docs/current/native-harness-convergence-audit.md`

- [x] **Step 1: Write failing layout guidance test**

Add assertions to `test_ensure_workspace_sandbox_layout_creates_guidance_and_keep_files`:

```python
outputs_readme = tmp_path / "outputs" / "README.md"
reports_readme = tmp_path / "reports" / "README.md"
assert outputs_readme.is_file()
assert reports_readme.is_file()
assert "/workspace/outputs/harness" in outputs_readme.read_text(encoding="utf-8")
assert "/workspace/reports/artifacts.json" in reports_readme.read_text(encoding="utf-8")
assert layout.is_workspace_guidance_path("/workspace/outputs/README.md")
assert layout.is_workspace_guidance_path("/workspace/reports/README.md")
assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/outputs/README.md")
assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/reports/README.md")
```

- [x] **Step 2: Write failing artifact discovery test**

Add this test to `backend/tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py`:

```python
@pytest.mark.asyncio
async def test_discover_generated_artifacts_skips_layout_guidance_files(tmp_path) -> None:
    ensure_workspace_sandbox_layout(tmp_path)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(tmp_path)})
    await sandbox.write_file("/workspace/reports/summary.md", "# Summary\n")

    generated = await discover_generated_artifacts(sandbox)

    assert [item["path"] for item in generated] == ["/workspace/reports/summary.md"]
    assert "/workspace/outputs/README.md" not in {item["path"] for item in generated}
    assert "/workspace/reports/README.md" not in {item["path"] for item in generated}
```

- [x] **Step 3: Verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py::test_ensure_workspace_sandbox_layout_creates_guidance_and_keep_files tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py::test_discover_generated_artifacts_skips_layout_guidance_files -q
```

Expected: fail because outputs/reports README files and `is_workspace_guidance_path()` do not exist yet.

- [x] **Step 4: Implement minimal layout guidance**

Add constants and helper in `workspace_layout.py`:

```python
WORKSPACE_OUTPUTS_README_RELATIVE_PATH = "outputs/README.md"
WORKSPACE_REPORTS_README_RELATIVE_PATH = "reports/README.md"
WORKSPACE_GUIDANCE_RELATIVE_PATHS = (
    WORKSPACE_MAIN_README_RELATIVE_PATH,
    WORKSPACE_DATASETS_README_RELATIVE_PATH,
    WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH,
    WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH,
    "datasets/.gitkeep",
    "scripts/.gitkeep",
    "outputs/.gitkeep",
    "reports/.gitkeep",
    WORKSPACE_OUTPUTS_README_RELATIVE_PATH,
    WORKSPACE_REPORTS_README_RELATIVE_PATH,
)

def is_workspace_guidance_path(path: str) -> bool:
    try:
        relative = workspace_relative_path(path)
    except ValueError:
        return False
    return relative in WORKSPACE_GUIDANCE_RELATIVE_PATHS
```

Write the two README files in `_ensure_workspace_guidance_files()` only when missing. Then update artifact helpers:

```python
if is_workspace_guidance_path(path):
    return None
```

and in `sandbox_artifact_discovery.py`:

```python
from src.sandbox.workspace_layout import is_workspace_guidance_path

def _is_guidance_artifact_path(path: str) -> bool:
    return is_workspace_guidance_path(path)
```

- [x] **Step 5: Verify GREEN**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py -q
```

Expected: all selected tests pass.

- [x] **Step 6: Commit**

Run:

```bash
git add backend/src/sandbox/workspace_layout.py backend/src/agents/lead_agent/v2/sandbox_artifact_discovery.py backend/tests/sandbox/test_workspace_layout.py backend/tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py docs/current/architecture.md docs/current/native-harness-convergence-audit.md docs/superpowers/plans/2026-06-09-workspace-sandbox-filesystem-contract-hardening.md
git commit -m "feat: harden sandbox guidance artifacts"
```

---

### Task 2: Add Path Class Metadata To Agent Contract

**Files:**
- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/agents/harness/context_assembly.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`
- Test: `backend/tests/agents/harness/test_context_assembly.py`

- [x] **Step 1: Write failing contract test**

Add a test that expects:

```python
contract = build_agent_workspace_contract(workspace_id="ws-1", workspace_type="sci")
assert contract["path_classes"]["workspace"] == ["/workspace/main"]
assert "/workspace/datasets" in contract["path_classes"]["datasets"]
assert "/workspace/scripts" in contract["path_classes"]["scripts"]
assert "/workspace/outputs" in contract["path_classes"]["artifacts"]
assert "/workspace/reports" in contract["path_classes"]["artifacts"]
assert "/workspace/tmp" in contract["path_classes"]["scratch"]
assert "/workspace/outputs/harness/**" in contract["path_classes"]["internal"]
```

- [x] **Step 2: Verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py::test_agent_workspace_contract_exposes_path_classes -q
```

Expected: fail because `path_classes` is missing.

- [x] **Step 3: Implement path classes**

Add `WORKSPACE_PATH_CLASSES` in `workspace_layout.py`:

```python
WORKSPACE_PATH_CLASSES = {
    "workspace": ["/workspace/main"],
    "datasets": ["/workspace/datasets"],
    "scripts": ["/workspace/scripts"],
    "artifacts": ["/workspace/outputs", "/workspace/reports"],
    "scratch": ["/workspace/tmp"],
    "runtime": ["/workspace/.wenjin/env", "/workspace/.wenjin/cache"],
    "protected": list(WORKSPACE_PROTECTED_PATHS),
    "internal": list(WORKSPACE_INTERNAL_PATHS),
    "guidance": [f"/workspace/{path}" for path in WORKSPACE_GUIDANCE_RELATIVE_PATHS],
}
```

Return a deep copy from `build_workspace_sandbox_manifest()` and `build_agent_workspace_contract()`.

- [x] **Step 4: Project path classes in harness context**

In `_sandbox_contract()`, include:

```python
"path_classes": _safe_path_classes(contract.get("path_classes")),
"guidance_paths": _safe_string_list((contract.get("path_classes") or {}).get("guidance")),
```

Add a context test asserting:

```python
assert bundle["sandbox"]["path_classes"]["artifacts"] == ["/workspace/outputs", "/workspace/reports"]
assert "/workspace/outputs/README.md" in bundle["sandbox"]["guidance_paths"]
```

- [x] **Step 5: Verify GREEN**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/harness/test_context_assembly.py -q
```

Expected: all selected tests pass.

---

### Task 3: Add Profile Invariant Gate

**Files:**
- Modify: `backend/src/sandbox/workspace_layout.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`

- [x] **Step 1: Write failing invariant test**

Add:

```python
def test_all_workspace_type_profiles_use_valid_common_layout_paths():
    for workspace_type in layout.WORKSPACE_SUPPORTED_TYPES:
        report = layout.validate_workspace_type_profile(workspace_type)
        assert report == {
            "workspace_type": workspace_type,
            "valid": True,
            "errors": [],
        }
```

- [x] **Step 2: Verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py::test_all_workspace_type_profiles_use_valid_common_layout_paths -q
```

Expected: fail because `WORKSPACE_SUPPORTED_TYPES` and `validate_workspace_type_profile()` are missing.

- [x] **Step 3: Implement validator**

Add:

```python
WORKSPACE_SUPPORTED_TYPES = ("thesis", "sci", "proposal", "software_copyright", "patent")

def validate_workspace_type_profile(workspace_type: str) -> dict[str, Any]:
    profile = workspace_type_profile(workspace_type)
    errors: list[str] = []
    expected_roots = {
        "primary_files": "/workspace/main/",
        "script_paths": "/workspace/scripts/",
        "output_paths": "/workspace/outputs",
        "report_paths": "/workspace/reports/",
    }
    for field, root in expected_roots.items():
        values = profile.get(field)
        if not isinstance(values, list) or not values:
            errors.append(f"{field} must be a non-empty list")
            continue
        for value in values:
            try:
                normalized = normalize_workspace_virtual_path(str(value))
            except ValueError:
                errors.append(f"{field} contains invalid path: {value}")
                continue
            if is_workspace_protected_path(normalized) or is_workspace_internal_path(normalized):
                errors.append(f"{field} contains protected/internal path: {normalized}")
            if root.endswith("/") and not normalized.startswith(root):
                errors.append(f"{field} path must be under {root}: {normalized}")
            if not root.endswith("/") and normalized != root and not normalized.startswith(f"{root}/"):
                errors.append(f"{field} path must be under {root}: {normalized}")
    return {"workspace_type": workspace_type, "valid": not errors, "errors": errors}
```

- [x] **Step 4: Add release-gate architecture check**

Extend `native_harness_quality_gate` coverage only if this test becomes part of the selected release suite. Otherwise leave the current gate unchanged and keep this as local sandbox layout coverage.

---

## Verification Command

Run after all tasks in this plan:

```bash
cd backend && .venv/bin/python -m pytest tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/harness/test_context_assembly.py -q
cd backend && .venv/bin/ruff check src/sandbox/workspace_layout.py src/agents/lead_agent/v2/sandbox_artifact_discovery.py src/agents/harness/context_assembly.py tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/harness/test_context_assembly.py
git diff --check
```

Expected:

```text
pytest: all selected tests pass
ruff: All checks passed!
git diff --check: no output
```
