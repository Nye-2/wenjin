"""Architecture guards for the DataService migration."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

from src.dataservice.app_boundary import FORBIDDEN_DOMAIN_IMPORT_PREFIXES

MIGRATED_LEGACY_MODEL_MODULES = {
    "src.database.models.workspace",
    "src.database.models.artifact",
    "src.database.models.thread",
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
    "src.database.models.generation",
    "src.database.models.task",
    "src.database.models.admin_log",
    "src.database.models.knowledge",
    "src.database.models.workspace_template",
    "src.database.models.audit_log",
    "src.database.models.latex_project",
    "src.database.models.latex_template",
    "src.database.models.latex_compile_history",
    "src.database.models.credit_grant_rule",
    "src.database.models.credit",
    "src.database.models.credit_redeem_code",
    "src.database.models.credit_redemption",
    "src.database.models.referral",
    "src.database.models.prism",
    "src.database.models.reference",
}
MIGRATED_LEGACY_MODEL_NAMES = {
    "Workspace",
    "Artifact",
    "Thread",
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
    "GenerationRecord",
    "TaskRecord",
    "AdminLog",
    "KnowledgeCategory",
    "UserKnowledge",
    "WorkspaceTemplate",
    "AuditLog",
    "LatexProject",
    "LatexTemplate",
    "LatexCompileHistory",
    "CreditGrantRule",
    "CreditTransaction",
    "CreditTransactionType",
    "CreditRedeemCode",
    "CreditRedemption",
    "Referral",
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
RUNTIME_DATASERVICE_API_ALLOWED_ROOTS = {
    "dataservice",
    "dataservice_app",
    "dataservice_client",
}
RUNTIME_DATASERVICE_API_ALLOWED_FILES = {
    "services/workspace_latex_projects.py",
    "services/workspace_prism_service.py",
}
RUNTIME_DIRECT_SQL_ALLOWED_FILES = {
    "gateway/routers/dev_test_hooks.py",
    "services/admin_capability_service.py",
    "services/admin_skill_service.py",
    "services/capability_loader.py",
    "services/capability_resolver.py",
    "services/dashboard_service.py",
    "services/skill_loader.py",
    "services/skill_resolver.py",
    "services/workspace_prism_service.py",
    "services/workspace_summary_service.py",
}


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


def _is_type_checking_guard(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.import_from_nodes: list[ast.ImportFrom] = []
        self.import_nodes: list[ast.Import] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.import_from_nodes.append(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.import_nodes.append(node)


class _RuntimeSqlVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    @staticmethod
    def _is_session_receiver(node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in {"session", "db"}
        return (
            isinstance(node, ast.Attribute)
            and node.attr in {"session", "db"}
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "select":
            self.violations.append(node.lineno)
        elif isinstance(func, ast.Attribute):
            if func.attr in {"execute", "get"} and self._is_session_receiver(func.value):
                self.violations.append(node.lineno)
        self.generic_visit(node)


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


def test_runtime_code_uses_dataservice_client_not_in_process_apis() -> None:
    """Runtime code should call standalone DataService through the HTTP client."""
    violations: list[str] = []
    observed_allowed: set[str] = set()
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        relative_posix = relative.as_posix()
        if relative.parts and relative.parts[0] in RUNTIME_DATASERVICE_API_ALLOWED_ROOTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        file_violations: list[str] = []
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module.startswith("src.dataservice.") and module.endswith("_api"):
                file_violations.append(f"{relative}:{node.lineno} imports {module}")
        for node in visitor.import_nodes:
            for alias in node.names:
                if alias.name.startswith("src.dataservice.") and alias.name.endswith("_api"):
                    file_violations.append(f"{relative}:{node.lineno} imports {alias.name}")
        if not file_violations:
            continue
        if relative_posix in RUNTIME_DATASERVICE_API_ALLOWED_FILES:
            observed_allowed.add(relative_posix)
            continue
        violations.extend(file_violations)

    stale_allowed = sorted(RUNTIME_DATASERVICE_API_ALLOWED_FILES - observed_allowed)
    assert not stale_allowed, "Remove stale DataService API runtime allowlist entries:\n" + "\n".join(stale_allowed)
    assert not violations, "Runtime code must use dataservice_client, not in-process DataService APIs:\n" + "\n".join(violations)


def test_runtime_code_does_not_run_business_sql() -> None:
    """Runtime business code should not query database tables directly."""
    violations: list[str] = []
    observed_allowed: set[str] = set()
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        relative_posix = relative.as_posix()
        if relative.parts and relative.parts[0] in MODEL_OWNER_PACKAGES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeSqlVisitor()
        visitor.visit(tree)
        if not visitor.violations:
            continue
        if relative_posix in RUNTIME_DIRECT_SQL_ALLOWED_FILES:
            observed_allowed.add(relative_posix)
            continue
        violations.extend(f"{relative}:{line} runs direct runtime SQL" for line in visitor.violations)

    stale_allowed = sorted(RUNTIME_DIRECT_SQL_ALLOWED_FILES - observed_allowed)
    assert not stale_allowed, "Remove stale direct SQL runtime allowlist entries:\n" + "\n".join(stale_allowed)
    assert not violations, "Runtime code must route business data access through DataService client:\n" + "\n".join(violations)


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
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            if node.module is None:
                continue
            if node.module in MIGRATED_LEGACY_MODEL_MODULES:
                violations.append(f"{relative} imports {node.module}")
            if node.module in {"src.database", "src.database.models"}:
                names = {alias.name for alias in node.names}
                migrated = sorted(names.intersection(MIGRATED_LEGACY_MODEL_NAMES))
                if migrated:
                    violations.append(f"{relative} imports migrated models {migrated}")
        for node in visitor.import_nodes:
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
