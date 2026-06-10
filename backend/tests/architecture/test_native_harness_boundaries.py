"""Architecture guards for the Wenjin-native harness boundary."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"

NATIVE_HARNESS_ROOTS = (
    SRC_ROOT / "agents" / "harness",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "team",
)
NATIVE_HARNESS_FILES = (
    SRC_ROOT / "sandbox" / "__init__.py",
    SRC_ROOT / "sandbox" / "paths.py",
    SRC_ROOT / "sandbox" / "providers" / "docker.py",
    SRC_ROOT / "sandbox" / "providers" / "local.py",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "sandbox_artifact_discovery.py",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "sandbox_artifact_review.py",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "sandbox_job_runner.py",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "sandbox_runtime_session.py",
    SRC_ROOT / "agents" / "lead_agent" / "v2" / "workspace_sandbox.py",
    SRC_ROOT / "sandbox" / "workspace_layout.py",
)

FORBIDDEN_NATIVE_HARNESS_MARKERS = (
    "/mnt/user-data",
    "sandbox.run_command",
    "codex_sdk",
    "cc-switch",
    "deer-flow",
)


def _native_harness_python_files() -> list[Path]:
    files: set[Path] = set()
    for root in NATIVE_HARNESS_ROOTS:
        files.update(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    files.update(NATIVE_HARNESS_FILES)
    return sorted(path for path in files if path.exists())


def test_native_harness_keeps_single_workspace_root_and_no_external_runtime_markers() -> None:
    """Native harness production code must stay on Wenjin's `/workspace` contract."""

    violations: list[str] = []
    for path in _native_harness_python_files():
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_NATIVE_HARNESS_MARKERS:
            if marker in text:
                violations.append(f"{path.relative_to(BACKEND_ROOT)} contains {marker!r}")

    assert not violations, (
        "Native harness must not reintroduce old thread-data aliases, generic shell "
        "runtime, or external agent runtime markers:\n" + "\n".join(violations)
    )
