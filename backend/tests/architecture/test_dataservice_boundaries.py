"""Architecture guards for the DataService migration."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SRC_ROOT = BACKEND_ROOT / "src"

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
RUNTIME_DATASERVICE_API_ALLOWED_FILES: set[str] = set()
RUNTIME_DIRECT_SQL_ALLOWED_FILES: set[str] = set()


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


class _CreditReservationMetadataVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "credit_reservation_id"
        ):
            self.violations.append(node.lineno)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "credit_reservation_id"
        ):
            self.violations.append(node.lineno)
        self.generic_visit(node)


def test_credit_reservation_metadata_visitor_flags_direct_key_reads() -> None:
    """The architecture guard must catch both get() and subscript reads."""
    tree = ast.parse(
        "\n".join(
            [
                "reservation_id = billing.get('credit_reservation_id')",
                "reservation_id = billing['credit_reservation_id']",
                "billing['credit_reservation_id'] = reservation_id",
            ]
        )
    )
    visitor = _CreditReservationMetadataVisitor()

    visitor.visit(tree)

    assert visitor.violations == [1, 2]


def test_credit_reservation_metadata_access_uses_canonical_helper() -> None:
    """Production code should not hand-roll execution billing metadata parsing."""
    allowed = {
        (SRC_ROOT / "billing" / "reservation_metadata.py").resolve(),
    }
    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        if path.resolve() in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _CreditReservationMetadataVisitor()
        visitor.visit(tree)
        relative = path.relative_to(SRC_ROOT)
        violations.extend(f"{relative}:{line}" for line in visitor.violations)
    assert not violations, (
        "Use src.billing.reservation_metadata for credit reservation metadata access:\n"
        + "\n".join(violations)
    )


def test_execution_node_detail_router_uses_execution_node_records() -> None:
    """Node detail must read node lifecycle rows, not the historical JSON blob."""
    router_path = SRC_ROOT / "gateway" / "routers" / "executions.py"
    source = router_path.read_text(encoding="utf-8")

    assert "record.node_states" not in source
    assert "find_node_by_node_id" in source


def test_dataservice_client_execution_api_lives_in_dedicated_mixin() -> None:
    """Keep the DataService client shell from absorbing every domain API."""
    client_path = SRC_ROOT / "dataservice_client" / "client.py"
    mixin_path = SRC_ROOT / "dataservice_client" / "execution_client.py"
    client_source = client_path.read_text(encoding="utf-8")

    assert mixin_path.exists()
    assert "ExecutionDataServiceClientMixin" in client_source
    assert "async def create_execution(" not in client_source
    assert "async def upsert_execution_node(" not in client_source
    assert "async def create_generation_record(" not in client_source


def test_dataservice_client_domain_apis_live_in_dedicated_mixins() -> None:
    """Keep domain DataService APIs out of the generic HTTP client shell."""
    client_path = SRC_ROOT / "dataservice_client" / "client.py"
    client_source = client_path.read_text(encoding="utf-8")
    expected = {
        "SourceDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "source_client.py",
            "forbidden_methods": [
                "async def create_source(",
                "async def import_source(",
                "async def list_sources(",
                "async def build_source_bibliography(",
                "async def create_provenance_link(",
            ],
        },
        "CreditDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "credit_client.py",
            "forbidden_methods": [
                "async def get_credit_summary(",
                "async def record_credit_consumption(",
                "async def create_credit_reservation(",
                "async def create_credit_redeem_code(",
                "async def record_credit_referral(",
            ],
        },
        "ModelCatalogDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "model_catalog_client.py",
            "forbidden_methods": [
                "async def list_model_catalog_models(",
                "async def create_model_catalog_model(",
                "async def update_model_catalog_health(",
                "async def list_model_catalog_runtime_models(",
            ],
        },
        "PricingDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "pricing_client.py",
            "forbidden_methods": [
                "async def simulate_pricing(",
                "async def list_pricing_policies(",
                "async def create_pricing_policy(",
                "async def disable_pricing_policy(",
            ],
        },
        "SandboxDataServiceClientMixin": {
            "file": SRC_ROOT / "dataservice_client" / "sandbox_client.py",
            "forbidden_methods": [
                "async def create_sandbox_environment(",
                "async def get_or_create_sandbox_environment(",
                "async def create_sandbox_job(",
                "async def acquire_sandbox_lease(",
                "async def register_sandbox_artifact(",
            ],
        },
    }
    for mixin, config in expected.items():
        assert config["file"].exists(), f"{mixin} module is missing"
        assert mixin in client_source
        for method in config["forbidden_methods"]:
            assert method not in client_source


def test_source_domain_service_is_facade_over_focused_services() -> None:
    """Source domain public service should stay a facade over focused services."""
    source_root = SRC_ROOT / "dataservice" / "domains" / "source"
    expected_files = {
        "context.py",
        "helpers.py",
        "import_service.py",
        "asset_service.py",
        "bibliography_service.py",
        "index_service.py",
        "projection_service.py",
    }
    missing = [name for name in sorted(expected_files) if not (source_root / name).exists()]
    assert not missing, f"Missing focused source services: {missing}"

    service_lines = (source_root / "service.py").read_text(encoding="utf-8").splitlines()
    assert len(service_lines) < 350
    service_source = "\n".join(service_lines)
    assert "SourceImportService" in service_source
    assert "SourceAssetService" in service_source
    assert "SourceBibliographyService" in service_source
    assert "SourceProjectionService" in service_source
    assert "SourceIndexService" in service_source
    assert "def _format_bibtex_entry(" not in service_source
    assert "def _serialize_reference_projection(" not in service_source


def test_upload_gateway_is_protocol_adapter_over_application_services() -> None:
    """Thread upload router should delegate orchestration to focused services."""
    upload_router = SRC_ROOT / "gateway" / "routers" / "uploads.py"
    expected_files = {
        SRC_ROOT / "application" / "services" / "upload_application_service.py",
        SRC_ROOT / "services" / "upload_preflight_policy.py",
        SRC_ROOT / "services" / "thread_upload_service.py",
        SRC_ROOT / "services" / "workspace_upload_service.py",
        SRC_ROOT / "services" / "layout_preprocess_orchestrator.py",
    }
    missing = [str(path.relative_to(SRC_ROOT)) for path in sorted(expected_files) if not path.exists()]
    assert not missing, f"Missing focused upload services: {missing}"

    source = upload_router.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 300
    assert "UploadApplicationService" in source
    assert "SourceLibraryImportService" not in source
    assert "KnowledgeService" not in source
    assert "persist_workspace_upload(" not in source
    assert "preprocess_file(" not in source


def test_sandbox_runtime_is_facade_over_installer_runner_and_artifacts() -> None:
    """Lead sandbox runtime should expose stable functions over focused helpers."""
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


def test_sandbox_runner_does_not_become_the_new_runtime_hotspot() -> None:
    """Sandbox execution internals should stay split beyond the public facade."""
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


def test_live_workflow_panel_uses_focused_local_modules() -> None:
    """LiveWorkflowPanel should stay a shell over local view-model modules."""
    panel_path = (
        REPO_ROOT
        / "frontend"
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "components"
        / "LiveWorkflowPanel.tsx"
    )
    module_root = panel_path.parent / "live-workflow"
    expected_files = {
        "types.ts",
        "utils.ts",
        "useLiveWorkflowViewModel.ts",
        "styles.ts",
    }
    missing = [name for name in sorted(expected_files) if not (module_root / name).exists()]
    assert not missing, f"Missing LiveWorkflowPanel focused modules: {missing}"

    source = panel_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1800
    assert "useLiveWorkflowViewModel" in source
    assert "const styles:" not in source
    assert "function buildEvidenceItems(" not in source


def test_live_workflow_panel_composes_focused_views() -> None:
    """LiveWorkflowPanel view sections should stay in focused local components."""
    panel_path = (
        REPO_ROOT
        / "frontend"
        / "app"
        / "(workbench)"
        / "workspaces"
        / "[id]"
        / "components"
        / "LiveWorkflowPanel.tsx"
    )
    module_root = panel_path.parent / "live-workflow"
    expected_files = {
        "WorkbenchHeader.tsx",
        "InterventionBar.tsx",
        "OverviewView.tsx",
        "RunView.tsx",
        "EvidenceView.tsx",
        "ReviewView.tsx",
        "ResultEditor.tsx",
        "NodeInspector.tsx",
        "shared.tsx",
    }
    missing = [name for name in sorted(expected_files) if not (module_root / name).exists()]
    assert not missing, f"Missing LiveWorkflowPanel focused view modules: {missing}"

    source = panel_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 900
    assert 'from "./live-workflow/WorkbenchHeader"' in source
    assert 'from "./live-workflow/OverviewView"' in source
    assert 'from "./live-workflow/RunView"' in source
    assert 'from "./live-workflow/EvidenceView"' in source
    assert 'from "./live-workflow/ReviewView"' in source
    for local_view in (
        "function WorkbenchHeader(",
        "function OverviewView(",
        "function RunView(",
        "function EvidenceView(",
        "function ReviewView(",
        "function ResultEditor(",
        "function NodeInspector(",
    ):
        assert local_view not in source


def test_latex_editor_shell_uses_focused_local_modules() -> None:
    """LatexEditorShell should shrink into a shell over local editor modules."""
    shell_path = REPO_ROOT / "frontend" / "components" / "latex" / "LatexEditorShell.tsx"
    module_root = shell_path.parent / "latex-editor"
    expected_files = {
        "fileKinds.ts",
        "feedbackAnchors.ts",
        "clientErrors.ts",
        "rewriteDisplay.ts",
        "prismOptimizationJobs.ts",
        "PrismMonacoEditor.tsx",
        "LatexRewritePreviewPanel.tsx",
    }
    missing = [name for name in sorted(expected_files) if not (module_root / name).exists()]
    assert not missing, f"Missing focused LatexEditorShell modules: {missing}"

    source = shell_path.read_text(encoding="utf-8")
    inspector_source = (module_root / "LatexInspector.tsx").read_text(encoding="utf-8")
    assert len(source.splitlines()) < 2400
    assert 'from "@/components/latex/latex-editor/PrismMonacoEditor"' in source
    assert (
        'from "@/components/latex/latex-editor/LatexRewritePreviewPanel"' in source
        or 'from "./LatexRewritePreviewPanel"' in inspector_source
    )
    assert "function buildFeedbackAnchor(" not in source
    assert "function resolveFeedbackRange(" not in source
    assert "const PrismMonacoEditor =" not in source


def test_latex_editor_shell_composes_second_stage_views() -> None:
    """LatexEditorShell should keep panes, inspector, and job/review orchestration local."""
    shell_path = REPO_ROOT / "frontend" / "components" / "latex" / "LatexEditorShell.tsx"
    module_root = shell_path.parent / "latex-editor"
    expected_files = {
        "types.ts",
        "useLatexFeedbackCreation.ts",
        "useLatexFeedbackPersistence.ts",
        "useLatexPdfSelectionMapping.ts",
        "usePrismOptimizationJobs.ts",
        "usePrismReviewQueue.ts",
        "LatexEditorProjectBar.tsx",
        "LatexResourceRail.tsx",
        "LatexEditorPanes.tsx",
        "LatexInspector.tsx",
        "LatexCompileLogDialog.tsx",
    }
    missing = [name for name in sorted(expected_files) if not (module_root / name).exists()]
    assert not missing, f"Missing second-stage LatexEditorShell modules: {missing}"

    source = shell_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1200
    assert 'from "@/components/latex/latex-editor/LatexEditorPanes"' in source
    assert 'from "@/components/latex/latex-editor/LatexInspector"' in source
    assert 'from "@/components/latex/latex-editor/usePrismOptimizationJobs"' in source
    assert 'from "@/components/latex/latex-editor/usePrismReviewQueue"' in source
    assert "const renderProjectBar =" not in source
    assert "const renderFeedbackInspector =" not in source
    assert "const renderPrismWorkspace =" not in source


def test_latex_editor_shell_delegates_feedback_workflow() -> None:
    """LatexEditorShell should keep feedback/rewrite orchestration in a focused hook."""
    shell_path = REPO_ROOT / "frontend" / "components" / "latex" / "LatexEditorShell.tsx"
    module_root = shell_path.parent / "latex-editor"
    workflow_path = module_root / "useLatexFeedbackWorkflow.ts"

    assert workflow_path.exists()

    source = shell_path.read_text(encoding="utf-8")
    workflow_source = workflow_path.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 800
    assert 'from "@/components/latex/latex-editor/useLatexFeedbackWorkflow"' in source
    assert "launchPrismOptimizationFromFeedback" not in source
    assert "rewriteFromFeedback" not in source
    assert "applyRewriteCandidate" not in source
    assert "undoLastRewrite" not in source
    assert "protectActiveFile" not in source
    assert "launchPrismOptimizationFromFeedback" in workflow_source
    assert "applyRewriteCandidate" in workflow_source


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


def test_credit_runtime_stays_on_dataservice_client_boundary() -> None:
    """Credit runtime services must not reopen legacy DB sessions after migration."""

    checked_files = [
        SRC_ROOT / "services" / "admin_dashboard_service.py",
        SRC_ROOT / "services" / "credit_grant_rule_service.py",
        SRC_ROOT / "services" / "credit_service.py",
        SRC_ROOT / "services" / "credit_redeem_service.py",
        SRC_ROOT / "services" / "referral_service.py",
        SRC_ROOT / "services" / "user_dashboard_service.py",
        SRC_ROOT / "gateway" / "routers" / "credits_redeem.py",
        SRC_ROOT / "gateway" / "routers" / "admin_redeem_codes.py",
    ]
    forbidden_imports = {
        "sqlalchemy.ext.asyncio",
        "src.database.session",
    }
    forbidden_names_by_module = {
        "src.database": {
            "AdminActionType",
            "CreditGrantRuleType",
            "CreditTransactionType",
            "get_db_session",
        },
    }

    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module in forbidden_imports:
                violations.append(f"{relative}:{node.lineno} imports {module}")
            forbidden_names = forbidden_names_by_module.get(module, set())
            imported_forbidden_names = sorted(
                alias.name for alias in node.names if alias.name in forbidden_names
            )
            if imported_forbidden_names:
                imported_names = ", ".join(imported_forbidden_names)
                violations.append(
                    f"{relative}:{node.lineno} imports {module}.{imported_names}"
                )
        for node in visitor.import_nodes:
            for alias in node.names:
                if alias.name in forbidden_imports:
                    violations.append(f"{relative}:{node.lineno} imports {alias.name}")

    assert not violations, (
        "Credit runtime must stay behind DataService client:\n" + "\n".join(violations)
    )


def test_auth_runtime_stays_on_account_dataservice_boundary() -> None:
    """Auth runtime must not reopen DB sessions after Account DataService migration."""

    checked_files = [
        SRC_ROOT / "gateway" / "auth_dependencies.py",
        SRC_ROOT / "gateway" / "routers" / "auth.py",
        SRC_ROOT / "services" / "auth.py",
        SRC_ROOT / "services" / "user_service.py",
    ]
    forbidden_imports = {"sqlalchemy.ext.asyncio"}
    forbidden_names_by_module = {
        "src.database": {"User", "get_db_session"},
        "src.gateway.deps.core": {"get_db"},
    }

    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module in forbidden_imports:
                violations.append(f"{relative}:{node.lineno} imports {module}")
            forbidden_names = forbidden_names_by_module.get(module, set())
            imported_forbidden_names = sorted(
                alias.name for alias in node.names if alias.name in forbidden_names
            )
            if imported_forbidden_names:
                imported_names = ", ".join(imported_forbidden_names)
                violations.append(
                    f"{relative}:{node.lineno} imports {module}.{imported_names}"
                )
        for node in visitor.import_nodes:
            for alias in node.names:
                if alias.name in forbidden_imports:
                    violations.append(f"{relative}:{node.lineno} imports {alias.name}")

    assert not violations, (
        "Auth runtime must use Account DataService only:\n" + "\n".join(violations)
    )


def test_gateway_process_stays_off_database_lifecycle() -> None:
    """Gateway process lifecycle and readiness must depend on DataService, not DB engine."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "app.py": (
            "from src.database import init_db",
            "from src.database import close_db",
            "await init_db()",
            "await close_db()",
        ),
        SRC_ROOT / "gateway" / "health.py": (
            "from src.database.session import engine",
            "from sqlalchemy import text",
            "engine.connect()",
            "check_database",
        ),
    }
    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Gateway must use DataService readiness instead of owning DB lifecycle:\n"
        + "\n".join(violations)
    )


def test_worker_process_stays_off_database_lifecycle() -> None:
    """Worker process bootstrap must not own DB engine lifecycle after DataService migration."""

    path = SRC_ROOT / "task" / "worker.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "from src.database import init_db",
        "from src.database import close_db",
        "reset_db_engine",
        "await init_db()",
        "await close_db()",
    )

    violations = [
        f"{path.relative_to(SRC_ROOT)} contains {token}"
        for token in forbidden_tokens
        if token in source
    ]
    assert not violations, (
        "Worker must use DataService client and avoid DB lifecycle ownership:\n"
        + "\n".join(violations)
    )


def test_runtime_type_hints_use_dataservice_contracts_not_database_models() -> None:
    """Runtime helper type hints must reference DataService payload contracts."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "application" / "handlers" / "thread_turn_handler.py": (
            "from src.database import Thread",
        ),
        SRC_ROOT / "services" / "thread_events.py": (
            "from src.database import Thread",
        ),
        SRC_ROOT / "gateway" / "routers" / "thread_serializers.py": (
            "from src.database import Thread",
        ),
        SRC_ROOT / "gateway" / "routers" / "workspaces_runtime.py": (
            "from src.database import Workspace",
        ),
    }
    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Runtime type hints must use DataService client contracts:\n"
        + "\n".join(violations)
    )


def test_audit_service_stays_on_audit_dataservice_boundary() -> None:
    """Audit runtime must expose only the Audit DataService client boundary."""

    path = SRC_ROOT / "services" / "audit_service.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "session_factory",
        "model=None",
        "_session_factory",
        "_model",
        "AsyncSession",
    )

    violations = [
        f"{path.relative_to(SRC_ROOT)} contains {token}"
        for token in forbidden_tokens
        if token in source
    ]
    assert not violations, (
        "AuditService must not expose legacy DB-shaped constructor state:\n"
        + "\n".join(violations)
    )


def test_reference_library_runtime_uses_dataservice_contract_boundary() -> None:
    """Reference Library runtime contracts must not import database model contracts."""

    checked_files = [
        SRC_ROOT / "gateway" / "routers" / "references.py",
        SRC_ROOT / "services" / "references" / "service.py",
    ]
    forbidden_import_modules = {"src.database", "src.database.base"}

    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module in forbidden_import_modules:
                violations.append(f"{relative}:{node.lineno} imports {module}")
        for node in visitor.import_nodes:
            for alias in node.names:
                if alias.name in forbidden_import_modules:
                    violations.append(f"{relative}:{node.lineno} imports {alias.name}")

    assert not violations, (
        "Reference Library runtime must use DataService client contracts, not DB models:\n"
        + "\n".join(violations)
    )


def test_runtime_code_does_not_use_legacy_artifact_surface_names() -> None:
    """Runtime code must use canonical workspace artifact names."""

    allowed_roots = {"database", "dataservice", "dataservice_app", "dataservice_client"}
    forbidden_tokens = ("legacy_artifact", "legacy-artifacts", "LegacyArtifact")
    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts and relative.parts[0] in allowed_roots:
            continue
        source = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Runtime code must use workspace artifact naming:\n" + "\n".join(violations)
    )


def test_prism_latex_adapter_has_no_public_latex_routes() -> None:
    """Prism adapter is the only public manuscript route surface."""

    checked_files = [
        SRC_ROOT / "gateway" / "app.py",
        *sorted((SRC_ROOT / "gateway" / "routers").glob("latex*.py")),
    ]
    forbidden_tokens = (
        'prefix="/latex"',
        "prefix='/latex'",
        '"/latex/',
        "'/latex/",
        '"/api/latex/',
        "'/api/latex/",
    )
    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        source = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    frontend_api = REPO_ROOT / "frontend" / "lib" / "api" / "latex.ts"
    source = frontend_api.read_text(encoding="utf-8")
    for token in ('"/latex/', "'/latex/", '"/api/latex/', "'/api/latex/"):
        if token in source:
            violations.append(f"{frontend_api.relative_to(REPO_ROOT)} contains {token}")

    assert not violations, (
        "Public LaTeX routes must live under Prism adapter only:\n" + "\n".join(violations)
    )


def test_prism_latex_runtime_stays_on_dataservice_boundary() -> None:
    """Prism LaTeX adapter runtime must not accept DB sessions."""

    checked_files = [
        SRC_ROOT / "services" / "latex" / "project_service.py",
        SRC_ROOT / "services" / "latex" / "template_service.py",
        SRC_ROOT / "services" / "latex" / "compile_service.py",
        SRC_ROOT / "services" / "workspace_latex_projects.py",
        SRC_ROOT / "services" / "workspace_prism_service.py",
        *sorted((SRC_ROOT / "gateway" / "routers").glob("latex*.py")),
    ]
    forbidden_imports = {"sqlalchemy.ext.asyncio"}
    forbidden_names_by_module = {"src.gateway.deps.core": {"get_db"}}
    forbidden_source_tokens = ("self.db", "db: AsyncSession", "Depends(get_db)")

    violations: list[str] = []
    for path in checked_files:
        relative = path.relative_to(SRC_ROOT)
        source = path.read_text(encoding="utf-8")
        for token in forbidden_source_tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")
        tree = ast.parse(source)
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module in forbidden_imports:
                violations.append(f"{relative}:{node.lineno} imports {module}")
            forbidden_names = forbidden_names_by_module.get(module, set())
            imported_forbidden_names = sorted(
                alias.name for alias in node.names if alias.name in forbidden_names
            )
            if imported_forbidden_names:
                violations.append(
                    f"{relative}:{node.lineno} imports {module}.{', '.join(imported_forbidden_names)}"
                )

    assert not violations, (
        "Prism LaTeX adapter runtime must use DataService only:\n" + "\n".join(violations)
    )


def test_gateway_runtime_drops_session_based_owner_commit_compute_boundaries() -> None:
    """Thread launch, execution commit, and compute must not depend on request DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "access_control.py": (
            "AsyncSession",
            "owner_check_session_from_service",
            "require_workspace_owner_by_session",
        ),
        SRC_ROOT / "gateway" / "services" / "run_launch.py": (
            "owner_check_session_from_service",
            "require_workspace_owner_by_session",
        ),
        SRC_ROOT / "gateway" / "routers" / "threads.py": (
            "owner_check_session_from_service",
            "require_workspace_owner_by_session",
        ),
        SRC_ROOT / "gateway" / "deps" / "threads.py": (
            "AsyncSession",
            "Depends(get_db)",
            "ThreadService(db",
        ),
        SRC_ROOT / "gateway" / "deps" / "academic.py": (
            "WorkspaceService(db",
        ),
        SRC_ROOT / "application" / "handlers" / "thread_turn_handler.py": (
            "from src.database import get_db_session",
        ),
        SRC_ROOT / "gateway" / "routers" / "execution_commit.py": (
            "AsyncSession",
            "Depends(get_db)",
            "ExecutionService(db",
        ),
        SRC_ROOT / "gateway" / "routers" / "compute.py": (
            "Depends(get_db)",
            "ComputeSessionService(db",
            "ComputeProjectionService(db",
        ),
        SRC_ROOT / "compute" / "session_service.py": (
            "db: AsyncSession",
            "self.db",
        ),
        SRC_ROOT / "compute" / "projection_service.py": (
            "db: AsyncSession",
            "self.db",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Gateway runtime still depends on session-based helper boundaries:\n"
        + "\n".join(violations)
    )


def test_execution_runtime_uses_dataservice_execution_boundary() -> None:
    """Execution runtime entrypoints must not construct execution services from DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "routers" / "executions.py": (
            "get_db_session",
            "ExecutionService(db",
            "from src.database import",
        ),
        SRC_ROOT / "tools" / "builtins" / "launch_feature.py": (
            "get_db_session",
            "ExecutionService(db",
            "from src.database import",
            "get_workspace_type",
            "IntegrityError",
        ),
        SRC_ROOT / "gateway" / "routers" / "capabilities.py": (
            "get_db_session",
            "session_factory=",
        ),
        SRC_ROOT / "task" / "recovery.py": (
            "get_db_session",
            "ExecutionService(db",
        ),
        SRC_ROOT / "task" / "service.py": (
            "ExecutionService(self._store.db",
        ),
        SRC_ROOT / "task" / "tasks" / "execution.py": (
            "get_db_session",
            "reset_db_engine",
            "ExecutionService(db",
            "ThreadService",
            "session_factory=",
            "db=",
            "_resolve_ws_type_with_fallback",
            'or "thesis"',
        ),
        SRC_ROOT / "task" / "tasks" / "base.py": (
            "get_db_session",
            "reset_db_engine",
            "ThreadService",
            "TaskStore(redis_client, db",
            "db=",
        ),
        SRC_ROOT / "gateway" / "deps" / "tasks.py": (
            "get_db_session",
            "TaskStore(redis_client, db",
        ),
        SRC_ROOT / "task" / "tasks" / "run.py": (
            "get_db_session",
            "reset_db_engine",
            "from src.database import",
            "ThreadService(db",
            "WorkspaceService(db",
        ),
        SRC_ROOT / "task" / "progress.py": (
            "get_db_session",
            "from src.database import",
            "TaskStore(self._redis, db",
        ),
        SRC_ROOT / "task" / "sse.py": (
            "get_db_session",
            "from src.database import",
            "TaskStore(redis_client, db",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Execution runtime must use DataService execution boundary:\n"
        + "\n".join(violations)
    )


def test_memory_runtime_uses_dataservice_knowledge_boundary() -> None:
    """Long-term memory runtime must not reopen legacy DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "services" / "user_memory_service.py": (
            "from src.database import",
            "get_db_session",
            "KnowledgeService(db",
            "db.commit",
        ),
        SRC_ROOT / "services" / "memory_compaction.py": (
            "from src.database import",
            "get_db_session",
            "KnowledgeService(db",
        ),
        SRC_ROOT / "services" / "knowledge_service.py": (
            "AsyncSession",
            "self.db",
            "_db",
        ),
        SRC_ROOT / "task" / "tasks" / "memory.py": (
            "from src.database import",
            "reset_db_engine",
        ),
        SRC_ROOT / "gateway" / "routers" / "uploads.py": (
            "AsyncSession",
            "Depends(get_db)",
            "KnowledgeService(db",
            "db.commit",
            "db.rollback",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Memory runtime must use DataService knowledge boundary:\n"
        + "\n".join(violations)
    )


def test_dashboard_runtime_uses_dataservice_boundary() -> None:
    """Dashboard dependency construction must not require request DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "deps" / "dashboard.py": (
            "AsyncSession",
            "Depends(get_db)",
            "get_db",
            "DashboardService(db",
            "WorkspaceActivityService(db",
            "WorkspaceSummaryService(db",
        ),
        SRC_ROOT / "services" / "dashboard_service.py": (
            "AsyncSession",
            "self.db",
            "_db",
            "db:",
        ),
        SRC_ROOT / "services" / "workspace_summary_service.py": (
            "AsyncSession",
            "self.db",
            "DashboardService(\n            db",
            "WorkspaceActivityService(db",
            "ExecutionService(self.db",
            "isinstance(self.db",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Dashboard runtime must use DataService boundary:\n"
        + "\n".join(violations)
    )


def test_workspace_runtime_uses_dataservice_boundary() -> None:
    """Workspace route/action context must not reopen legacy DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "routers" / "workspaces.py": (
            "Depends(get_db)",
            "get_db,",
        ),
        SRC_ROOT / "agents" / "middlewares" / "workspace_context.py": (
            "from src.database import",
            "get_db_session",
            "TemplateService(template_db",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Workspace runtime must use DataService boundary:\n"
        + "\n".join(violations)
    )


def test_admin_catalog_runtime_uses_dataservice_boundary() -> None:
    """Admin capability/skill catalog runtime must not accept DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "routers" / "admin_capabilities.py": (
            "from src.database import",
            "get_db_session",
            "Request",
            "CapabilityLoader(session=",
            "AdminCapabilityService(db",
        ),
        SRC_ROOT / "gateway" / "routers" / "admin_skills.py": (
            "from src.database import",
            "get_db_session",
            "Request",
            "SkillLoader(db",
            "AdminSkillService(db",
        ),
        SRC_ROOT / "services" / "admin_capability_service.py": (
            "AsyncSession",
            "self.db",
            "db: AsyncSession",
            "CrossRefValidator(db",
        ),
        SRC_ROOT / "services" / "admin_skill_service.py": (
            "AsyncSession",
            "self.db",
            "db: AsyncSession",
            "CrossRefValidator(db",
        ),
        SRC_ROOT / "services" / "capability_schema.py": (
            "self.db",
            "_existing_skill_ids(self.db",
            "_existing_skill_ids(db",
        ),
        SRC_ROOT / "services" / "capability_loader.py": (
            "AsyncSession",
            "self.session",
            "session: AsyncSession",
        ),
        SRC_ROOT / "services" / "skill_loader.py": (
            "AsyncSession",
            "self.session",
            "session: AsyncSession",
        ),
        SRC_ROOT / "services" / "agent_template_loader.py": (
            "AsyncSession",
            "self.session",
            "session: AsyncSession",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Admin catalog runtime must use DataService boundary:\n"
        + "\n".join(violations)
    )


def test_reference_library_runtime_uses_dataservice_boundary() -> None:
    """Reference Library gateway and BibTeX sync must not accept DB sessions."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "routers" / "references.py": (
            "AsyncSession",
            "Depends(get_db)",
            "get_db",
            "db: AsyncSession",
            "SourceBibliographyService(dataservice, db=",
        ),
        SRC_ROOT / "services" / "execution_commit_service.py": (
            "SourceBibliographyService(dataservice, db=",
            "getattr(self.execution, \"db\", None)",
        ),
        SRC_ROOT / "services" / "references" / "service.py": (
            "AsyncSession",
            "self.db",
            "db: AsyncSession",
            "db=",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Reference Library runtime must use DataService boundary:\n"
        + "\n".join(violations)
    )


def test_runtime_service_facades_do_not_keep_optional_db_sessions() -> None:
    """DataService-backed service facades must not retain optional DB constructors."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "services" / "thread_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
            "ThreadService(None",
            "list_workspace_types(self.db",
        ),
        SRC_ROOT / "services" / "template_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
        ),
        SRC_ROOT / "services" / "workspace_activity_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
            "get_workspace_type(self.db",
        ),
        SRC_ROOT / "services" / "admin_analytics_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
        ),
        SRC_ROOT / "services" / "workspace_skill_labels.py": (
            "AsyncSession",
            "db:",
        ),
        SRC_ROOT / "gateway" / "deps" / "threads.py": (
            "ThreadService(None",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Runtime service facades must not keep optional DB session boundaries:\n"
        + "\n".join(violations)
    )


def test_legacy_gateway_and_execution_helpers_do_not_keep_db_sessions() -> None:
    """Retired helper/facade entrypoints must not expose DB session construction."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "deps" / "core.py": (
            "AsyncSession",
            "get_db_session",
            "def get_db",
        ),
        SRC_ROOT / "gateway" / "deps" / "__init__.py": (
            '"get_db"',
        ),
        SRC_ROOT / "services" / "execution_service.py": (
            "AsyncSession",
            "self.db",
            "db: AsyncSession",
        ),
        SRC_ROOT / "task" / "store.py": (
            "AsyncSession",
            "db_session",
            "self._db",
            "def db",
        ),
        SRC_ROOT / "services" / "skill_resolver.py": (
            "AsyncSession",
            "session_factory",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Retired DB helper/session constructor boundaries are still present:\n"
        + "\n".join(violations)
    )


def test_catalog_and_academic_facades_do_not_keep_db_constructors() -> None:
    """Catalog and academic facades must expose DataService-only constructors."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "services" / "capability_resolver.py": (
            "session_factory",
        ),
        SRC_ROOT / "gateway" / "routers" / "capabilities.py": (
            "from src.database import User",
            "current_user: User",
        ),
        SRC_ROOT / "academic" / "services" / "workspace_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
            "database session",
        ),
        SRC_ROOT / "gateway" / "deps" / "academic.py": (
            "WorkspaceService(None",
        ),
        SRC_ROOT / "task" / "tasks" / "run.py": (
            "WorkspaceService(None",
        ),
        SRC_ROOT / "academic" / "services" / "generation_service.py": (
            "AsyncSession",
            "self.db",
            "db:",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Catalog/academic runtime facades still expose DB constructor boundaries:\n"
        + "\n".join(violations)
    )


def test_workspace_asset_runtime_projections_do_not_read_legacy_metadata_fields() -> None:
    """Workspace asset projections must use canonical metadata fields only."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "gateway" / "routers" / "workspace_rooms.py": (
            "legacy_kind",
            "legacy_parent_id",
            "legacy_version",
        ),
        SRC_ROOT / "services" / "workspace_activity_service.py": (
            "legacy_kind",
        ),
    }

    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Workspace asset runtime projections still read legacy metadata fields:\n"
        + "\n".join(violations)
    )


def test_gateway_routers_do_not_type_auth_subjects_as_database_users() -> None:
    """Gateway auth subjects must use AccountAuthSubject, not the DB User model."""

    violations: list[str] = []
    for path in sorted((SRC_ROOT / "gateway" / "routers").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in (
            "from src.database import User",
            "current_user: User",
            "_current_user: User",
            "admin: User",
            "_admin: User",
            "user: User",
            "current_user: User | None",
        ):
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Gateway routers still type auth subjects as database User models:\n"
        + "\n".join(violations)
    )


def test_prism_adapter_metadata_uses_canonical_field_names() -> None:
    """Workspace Prism adapter metadata must not expose legacy metadata fields."""

    checked_files = [
        SRC_ROOT / "services" / "workspace_prism_service.py",
        SRC_ROOT / "dataservice" / "domains" / "prism" / "adapters" / "latex.py",
    ]
    violations: list[str] = []
    for path in checked_files:
        source = path.read_text(encoding="utf-8")
        if "legacy_metadata" in source:
            violations.append(f"{path.relative_to(SRC_ROOT)} contains legacy_metadata")
    assert not violations, (
        "Prism adapter metadata still exposes legacy fields:\n"
        + "\n".join(violations)
    )


def test_feature_launch_context_does_not_keep_plain_param_compatibility() -> None:
    """Feature launch params must stay on the canonical TaskBrief wrapper shape."""

    path = SRC_ROOT / "application" / "services" / "feature_launch_context.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "extract_feature_params",
        "plain-param",
        "legacy",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Feature launch context still accepts non-canonical execution params: "
        + ", ".join(violations)
    )


def test_feature_action_resolution_does_not_synthesize_workspace_goal_fallbacks() -> None:
    """Follow-up/rerun state must require explicit mission params or source artifacts."""

    path = SRC_ROOT / "services" / "feature_action_resolution_service.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "_workspace_fallback",
        "未命名任务",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Feature action resolver still synthesizes implicit workspace goals: "
        + ", ".join(violations)
    )


def test_workspace_uploads_do_not_accept_legacy_root_prefixed_relative_paths() -> None:
    """Stored upload paths must be absolute-under-root or workspace-relative."""

    path = SRC_ROOT / "services" / "workspace_uploads.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "Backward-compat",
        "legacy_candidate",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Workspace upload resolver still accepts legacy root-prefixed relative paths: "
        + ", ".join(violations)
    )


def test_react_subagent_does_not_silently_ignore_requested_tools() -> None:
    """React subagents must fail when requested tool names cannot be resolved."""

    path = SRC_ROOT / "subagents" / "v2" / "types" / "react.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "TODO:",
        "plain model invoke is used when tools list is empty after resolution",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "React subagent still documents silent tool fallback: "
        + ", ".join(violations)
    )


def test_catalog_skill_projection_does_not_synthesize_legacy_skill_json() -> None:
    """Catalog skill rows must carry canonical skill_json from the seed/DB."""

    path = SRC_ROOT / "dataservice" / "domains" / "catalog" / "projection.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "_legacy_skill_json",
        "not skill_json",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Catalog skill projection still synthesizes legacy skill_json: "
        + ", ".join(violations)
    )


def test_source_domain_does_not_name_current_reference_projection_as_compat() -> None:
    """Source Library projections are current contracts, not compatibility helpers."""

    path = SRC_ROOT / "dataservice" / "domains" / "source" / "service.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "_serialize_reference_compat",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Source domain still names current reference projection as compat: "
        + ", ".join(violations)
    )


def test_conversation_block_payloads_do_not_persist_legacy_kind() -> None:
    """Canonical conversation blocks must not preserve old kind shadow fields."""

    path = SRC_ROOT / "dataservice" / "domains" / "conversation" / "block_protocol.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "legacy_kind",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Conversation block protocol still persists old kind shadow fields: "
        + ", ".join(violations)
    )


def test_execution_generation_contracts_do_not_label_current_usage_projection_legacy() -> None:
    """Generation usage contracts are current DataService projections."""

    path = SRC_ROOT / "dataservice" / "domains" / "execution" / "contracts.py"
    source = path.read_text(encoding="utf-8")
    forbidden_tokens = (
        "legacy generation",
        "legacy skill-generation",
    )
    violations = [token for token in forbidden_tokens if token in source]
    assert not violations, (
        "Execution generation contracts still label current usage projection as legacy: "
        + ", ".join(violations)
    )


def test_dataservice_internal_contracts_do_not_keep_legacy_or_fallback_naming() -> None:
    """DataService internal names should describe current contracts directly."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "dataservice" / "domains" / "rooms" / "models.py": (
            "legacy deletion/archive gate",
        ),
        SRC_ROOT / "dataservice" / "domains" / "source" / "service.py": (
            "fallback=",
            "fallback:",
            "return cleaned or fallback",
        ),
    }
    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(SRC_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "DataService internal contracts still use stale legacy/fallback naming:\n"
        + "\n".join(violations)
    )


def test_workspace_capability_runtime_comments_do_not_keep_legacy_guidance() -> None:
    """Runtime comments should describe current capability routing directly."""

    forbidden_tokens_by_file = {
        SRC_ROOT / "agents" / "chat_agent" / "agent.py": (
            "legacy consumers",
            "legacy per-skill guidance prompt",
        ),
        REPO_ROOT / "frontend" / "lib" / "workspace-thread-entry.ts": (
            "legacy resolver",
        ),
    }
    violations: list[str] = []
    for path, tokens in forbidden_tokens_by_file.items():
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT)
        for token in tokens:
            if token in source:
                violations.append(f"{relative} contains {token}")

    assert not violations, (
        "Workspace capability runtime comments still describe removed legacy paths:\n"
        + "\n".join(violations)
    )


def test_production_source_does_not_keep_unscoped_legacy_labels() -> None:
    """Production source should describe current contracts, not old paths."""

    checked_roots = [
        SRC_ROOT,
        REPO_ROOT / "frontend" / "app",
        REPO_ROOT / "frontend" / "components",
        REPO_ROOT / "frontend" / "hooks",
        REPO_ROOT / "frontend" / "lib",
        REPO_ROOT / "frontend" / "stores",
    ]
    violations: list[str] = []
    for root in checked_roots:
        for path in _python_files(root) if root == SRC_ROOT else sorted(root.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            source = path.read_text(encoding="utf-8")
            if "legacy" in source.lower():
                violations.append(str(path.relative_to(REPO_ROOT)))

    assert not violations, (
        "Production source still contains unscoped legacy labels:\n"
        + "\n".join(violations)
    )


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
