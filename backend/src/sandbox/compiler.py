"""Trusted argv compiler for typed sandbox operations."""

from __future__ import annotations

import json

from src.sandbox.contracts import (
    CompiledSandboxCommand,
    InstallDependenciesInput,
    RunNotebookInput,
    RunPythonInput,
    SandboxEnvironmentManifest,
    SandboxOperationInput,
    SandboxOperationKind,
    SandboxOperationRequest,
    SmokeCheckInput,
    content_hash_bytes,
)
from src.sandbox.exceptions import SandboxPolicyError
from src.sandbox.workspace_layout import workspace_task_scratch_path

_SMOKE_PROGRAM = """import json, statistics, sys
data = [2, 4, 6, 8]
print(json.dumps({"ok": True, "mean": statistics.mean(data), "python": sys.version.split()[0]}))
"""

_INSTALLER_PROGRAM = """import json, pathlib, subprocess, sys
root = pathlib.Path('/opt/wenjin/env')
packages = json.loads(sys.argv[1])
venv = root / 'venv'
subprocess.run([sys.executable, '-m', 'venv', '--copies', str(venv)], check=True)
python = venv / 'bin' / 'python'
report_path = root / 'install-report.json'
subprocess.run([str(python), '-m', 'pip', 'install', '--no-input', '--disable-pip-version-check', '--report', str(report_path), *packages], check=True)
report = json.loads(report_path.read_text(encoding='utf-8'))
lock = []
for item in report.get('install', []):
    metadata = item.get('metadata') or {}
    name, version = metadata.get('name'), metadata.get('version')
    hashes = ((item.get('download_info') or {}).get('archive_info') or {}).get('hashes') or {}
    sha256 = hashes.get('sha256')
    if not name or not version or not sha256:
        raise RuntimeError('dependency resolution did not produce a sha256 archive hash')
    lock.append(f'{name}=={version} --hash=sha256:{sha256}\\n')
(root / 'requirements.lock').write_text(''.join(sorted(lock, key=str.lower)), encoding='utf-8')
"""

_COMPILER_SOURCES = {
    SandboxOperationKind.RUN_PYTHON: "wenjin.sandbox.compiler.run_python.v2",
    SandboxOperationKind.RUN_NOTEBOOK: "wenjin.sandbox.compiler.run_notebook.v2",
    SandboxOperationKind.SMOKE_CHECK: _SMOKE_PROGRAM,
    SandboxOperationKind.INSTALL_DEPENDENCIES: _INSTALLER_PROGRAM,
}


class SandboxOperationCompiler:
    """Compile trusted typed inputs to an argv-only provider command."""

    def compile(
        self,
        request: SandboxOperationRequest,
        *,
        environment: SandboxEnvironmentManifest,
    ) -> CompiledSandboxCommand:
        operation_input = request.operation_input
        python = "/opt/wenjin/env/venv/bin/python" if isinstance(operation_input, RunPythonInput | RunNotebookInput) and operation_input.environment_id else "python3"
        provenance = request.provenance
        scratch = workspace_task_scratch_path(
            mission_id=provenance.mission_id,
            mission_item_seq=provenance.mission_item_seq,
            subagent_id=provenance.subagent_id,
        )
        env = {
            "HOME": scratch,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "MPLCONFIGDIR": f"{scratch}/matplotlib",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "WENJIN_TASK_SCRATCH": scratch,
            "WENJIN_WORKSPACE_ROOT": "/workspace",
        }
        argv: tuple[str, ...]
        if isinstance(operation_input, RunPythonInput):
            argv = (python, operation_input.script_path)
            cwd = "/workspace"
        elif isinstance(operation_input, RunNotebookInput):
            argv = (
                python,
                "-m",
                "jupyter",
                "nbconvert",
                "--execute",
                "--to",
                "notebook",
                "--output",
                operation_input.output_path,
                operation_input.notebook_path,
            )
            cwd = "/workspace"
        elif isinstance(operation_input, SmokeCheckInput):
            argv = ("python3", "-c", _SMOKE_PROGRAM)
            cwd = "/workspace"
        elif isinstance(operation_input, InstallDependenciesInput):
            argv = (
                "python3",
                "-c",
                _INSTALLER_PROGRAM,
                json.dumps(operation_input.packages, ensure_ascii=True, separators=(",", ":")),
            )
            cwd = "/opt/wenjin/env"
            env = {
                "HOME": "/tmp",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            }
        else:
            raise SandboxPolicyError("metadata operation cannot compile a provider command")
        return CompiledSandboxCommand(
            operation=request.operation,
            argv=argv,
            cwd=cwd,
            env=env,
            compiler_fingerprint=compiler_fingerprints()[request.operation],
        )


def compiler_fingerprints() -> dict[SandboxOperationKind, str]:
    return {operation: content_hash_bytes(source.encode()) for operation, source in _COMPILER_SOURCES.items()}


def artifact_inputs(
    operation_input: SandboxOperationInput,
) -> tuple[str | None, tuple[str, ...]]:
    if isinstance(operation_input, RunPythonInput):
        return (
            operation_input.script_path,
            operation_input.dataset_paths + operation_input.artifact_input_paths,
        )
    if isinstance(operation_input, RunNotebookInput):
        return operation_input.notebook_path, operation_input.dataset_paths
    return None, ()


def output_base_hashes(operation_input: SandboxOperationInput) -> dict[str, str]:
    if isinstance(operation_input, RunPythonInput):
        return dict(operation_input.output_base_hashes)
    if isinstance(operation_input, RunNotebookInput) and operation_input.base_content_hash:
        return {operation_input.output_path: operation_input.base_content_hash}
    return {}
