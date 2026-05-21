"""Architecture guards for the DataService migration."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

from src.dataservice.app_boundary import FORBIDDEN_DOMAIN_IMPORT_PREFIXES

MIGRATED_LEGACY_MODEL_MODULES = {
    "src.database.models.decision",
    "src.database.models.memory_fact",
    "src.database.models.workspace_task",
    "src.database.models.sandbox",
    "src.database.models.library_item",
    "src.database.models.document_v2",
    "src.database.models.workspace_settings",
    "src.database.models.workspace_run",
    "src.database.models.compute_session",
    "src.database.models.execution",
    "src.database.models.execution_node",
    "src.database.models.prism",
    "src.database.models.reference",
}
MIGRATED_LEGACY_MODEL_NAMES = {
    "Decision",
    "MemoryFact",
    "WorkspaceTask",
    "Sandbox",
    "LibraryItem",
    "DocumentV2",
    "WorkspaceSettings",
    "WorkspaceRunRow",
    "ComputeSessionRecord",
    "ExecutionRecord",
    "ExecutionNodeRecord",
    "PrismReviewItem",
    "PrismSourceLink",
    "PrismProtectedSection",
    "WorkspaceReference",
    "ReferenceExternalId",
    "ReferenceAsset",
    "ReferenceOutlineNode",
    "ReferenceTextUnit",
    "ReferenceUsageEvent",
    "ReferenceBibtexSnapshot",
}
MODEL_OWNER_PACKAGES = {
    "database",
    "dataservice",
    "dataservice_app",
}
LEGACY_ALLOWED_FILES: set[str] = set()


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def test_dataservice_domains_do_not_import_runtime_layers() -> None:
    """Domain modules must stay below gateway/agent/runtime orchestration."""
    domain_root = SRC_ROOT / "dataservice" / "domains"
    violations: list[str] = []
    for path in _python_files(domain_root):
        for module in _imports(path):
            for prefix in FORBIDDEN_DOMAIN_IMPORT_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(f"{path.relative_to(SRC_ROOT)} imports {module}")
    assert not violations, "DataService domain layer imports forbidden runtime modules:\n" + "\n".join(violations)


def test_dataservice_domain_repositories_are_not_imported_by_runtime_code() -> None:
    """Runtime code should use DataService APIs/client, not domain repositories."""
    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts[:1] in (("dataservice",), ("dataservice_app",)):
            continue
        for module in _imports(path):
            if module.startswith("src.dataservice.domains"):
                violations.append(f"{relative} imports {module}")
    assert not violations, "Only DataService itself may import DataService domain modules:\n" + "\n".join(violations)


def test_runtime_code_does_not_import_migrated_legacy_room_or_sandbox_models() -> None:
    """Migrated room/sandbox models must be accessed through DataService APIs."""

    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        if relative.as_posix() in LEGACY_ALLOWED_FILES:
            continue
        if relative.parts and relative.parts[0] in MODEL_OWNER_PACKAGES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module in MIGRATED_LEGACY_MODEL_MODULES:
                    violations.append(f"{relative} imports {node.module}")
                if node.module in {"src.database", "src.database.models"}:
                    names = {alias.name for alias in node.names}
                    migrated = sorted(names.intersection(MIGRATED_LEGACY_MODEL_NAMES))
                    if migrated:
                        violations.append(f"{relative} imports migrated models {migrated}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in MIGRATED_LEGACY_MODEL_MODULES:
                        violations.append(f"{relative} imports {alias.name}")
    assert not violations, "Runtime code imports migrated legacy models:\n" + "\n".join(violations)


def test_runtime_code_does_not_access_thread_messages_json() -> None:
    """Conversation messages must flow through DataService conversation projections."""

    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts and relative.parts[0] in {"database", "dataservice", "dataservice_app"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "messages"
                and isinstance(node.value, ast.Name)
                and node.value.id == "thread"
            ):
                violations.append(f"{relative}:{node.lineno} accesses thread.messages")

    assert not violations, "Runtime code accesses legacy threads.messages JSON:\n" + "\n".join(violations)


def test_retired_room_service_facades_do_not_return() -> None:
    """Workspace room endpoints must use DataService APIs directly."""

    violations: list[str] = []
    rooms_root = SRC_ROOT / "services" / "rooms"
    if rooms_root.exists():
        retired_files = sorted(path.relative_to(SRC_ROOT) for path in rooms_root.rglob("*.py"))
        violations.extend(str(path) for path in retired_files)

    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        for module in _imports(path):
            if module == "src.services.rooms" or module.startswith("src.services.rooms."):
                violations.append(f"{relative} imports {module}")

    assert not violations, "Retired room service facades are present or imported:\n" + "\n".join(violations)
