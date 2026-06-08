"""Built-in harness tool declarations."""

from __future__ import annotations

from .contracts import HarnessToolSpec
from .tool_registry import HarnessToolRegistry

BUILTIN_TOOL_SPECS = (
    HarnessToolSpec(
        name="sandbox.list_dir",
        namespace="sandbox",
        description="List workspace directory entries.",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    ),
    HarnessToolSpec(
        name="sandbox.glob",
        namespace="sandbox",
        description="Find workspace files by glob pattern.",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    ),
    HarnessToolSpec(
        name="sandbox.grep",
        namespace="sandbox",
        description="Search workspace files with a regular expression.",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    ),
    HarnessToolSpec(
        name="sandbox.read_file",
        namespace="sandbox",
        description="Read a bounded preview of a workspace file.",
        input_schema={"type": "object"},
        risk_level="read",
        required_permissions=["filesystem.read"],
    ),
    HarnessToolSpec(
        name="sandbox.write_file",
        namespace="sandbox",
        description="Write a workspace file and record a diff.",
        input_schema={"type": "object"},
        risk_level="write",
        required_permissions=["filesystem.write", "filesystem.diff"],
    ),
    HarnessToolSpec(
        name="sandbox.str_replace",
        namespace="sandbox",
        description="Replace exactly one string in a workspace file and record a diff.",
        input_schema={"type": "object"},
        risk_level="write",
        required_permissions=["filesystem.write", "filesystem.diff"],
    ),
    HarnessToolSpec(
        name="sandbox.apply_patch",
        namespace="sandbox",
        description="Apply a structured multi-file workspace patch and record diffs.",
        input_schema={"type": "object"},
        risk_level="write",
        required_permissions=["filesystem.write", "filesystem.diff"],
    ),
    HarnessToolSpec(
        name="sandbox.register_dataset",
        namespace="sandbox",
        description="Register a reusable dataset entry in /workspace/datasets/manifest.json.",
        input_schema={"type": "object"},
        risk_level="write",
        required_permissions=["filesystem.write", "filesystem.diff"],
    ),
    HarnessToolSpec(
        name="sandbox.register_artifact",
        namespace="sandbox",
        description="Register user-facing artifact metadata in /workspace/reports/artifacts.json.",
        input_schema={"type": "object"},
        risk_level="write",
        required_permissions=["filesystem.write", "filesystem.diff"],
    ),
    HarnessToolSpec(
        name="sandbox.run_python",
        namespace="sandbox",
        description="Run a controlled Python script in the workspace sandbox.",
        input_schema={"type": "object"},
        risk_level="execute",
        required_permissions=["sandbox.run_python"],
    ),
)


def default_harness_tool_registry() -> HarnessToolRegistry:
    """Return a fresh registry containing built-in harness tools."""

    return HarnessToolRegistry(BUILTIN_TOOL_SPECS)
