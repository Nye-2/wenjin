from __future__ import annotations

from pathlib import Path

from src.quality.mission_cutover_gate import build_cutover_report, main


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cutover_gate_scans_runtime_and_configuration_assets(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/runtime/old.py",
        "record: ExecutionRecord\naccepted_ids = []\n",
    )
    _write(
        tmp_path,
        "backend/tests/runtime/test_old.py",
        "record: ExecutionRecord\n",
    )
    _write(
        tmp_path,
        "docs/history.md",
        "ExecutionRecord and ChangeSet are historical.\n",
    )
    _write(
        tmp_path,
        "backend/src/quality/mission_cutover_gate.py",
        "ExecutionRecord is a scanner rule literal.\n",
    )
    _write(
        tmp_path,
        "backend/config.yaml",
        "subagents:\n  types:\n    scout:\n      allowed_tools: [read_file]\n",
    )
    _write(
        tmp_path,
        ".env.example",
        "SEMANTIC_SCHOLAR_API_KEY=\n",
    )
    _write(
        tmp_path,
        "backend/seed/skills/old.yaml",
        "allowed_tools: [web_search]\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["status"] == "failed"
    assert report["finding_count"] == 8
    assert report["counts_by_rule"] == {
        "old_execution_record": 1,
        "old_config_tool_id": 2,
        "old_fixed_subagent_config": 2,
        "old_review_ssot": 1,
        "old_search_provider": 1,
        "old_yaml_runtime_config": 1,
    }


def test_old_brand_config_is_rejected_without_scanning_unrelated_docs(tmp_path: Path) -> None:
    _write(tmp_path, "backend/src/config/config_loader.py", 'os.getenv("GUANLAN_CONFIG_PATH")\n')
    _write(tmp_path, ".env.example", "GUANLAN_CONFIG_PATH=/tmp/config.yaml\n")
    _write(tmp_path, "docs/history.md", "GUANLAN_CONFIG_PATH was historical.\n")

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 3
    assert report["counts_by_rule"] == {
        "old_brand_config": 2,
        "old_runtime_config_loader": 1,
    }


def test_retired_deployment_surfaces_are_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "docker-compose.local-build.yml", "  memory-worker:\n")
    _write(tmp_path, "backend/langgraph.json", "{}\n")
    _write(tmp_path, "backend/Makefile", "debug-langgraph:\n")

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 3
    assert report["counts_by_rule"] == {
        "old_langgraph_server_config": 1,
        "old_langgraph_server_surface": 1,
        "old_memory_worker": 1,
    }


def test_model_flags_are_rejected_across_catalog_and_admin_surfaces(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/src/database/models/model_catalog.py",
        "supports_tools = True\n",
    )
    _write(
        tmp_path,
        "frontend/lib/api/types.ts",
        "export type Display = { supports_vision: boolean };\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {"model_capability_compatibility_flags": 2}


def test_old_model_provider_protocol_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "frontend/lib/api/admin-models.ts",
        "export type Model = { provider_protocol: string };\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 1
    assert report["findings"][0]["rule_id"] == "old_model_provider_protocol"


def test_old_execution_provenance_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "frontend/lib/api/v2/library.ts",
        'const source = "execution:run-1";\n',
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 1
    assert report["findings"][0]["rule_id"] == "old_execution_provenance"


def test_old_thread_checkpoint_api_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/gateway/routers/threads.py",
        '@router.get("/threads/{thread_id}/state")\n',
    )
    _write(
        tmp_path,
        "frontend/lib/api/types.ts",
        "export interface PlatformThreadHistoryEntry {}\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {"old_thread_checkpoint_api": 2}


def test_product_capability_rules_allow_model_capability_profiles(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/models/capability_profile.py",
        "class ModelCapabilityProfile:\n    pass\n",
    )
    _write(
        tmp_path,
        "backend/src/workspace/settings.py",
        "capability_overrides = {}\nfeature_tasks = []\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {
        "old_feature_task_metric": 1,
        "old_product_capability_contract": 1,
    }


def test_report_only_does_not_fail_active_migration(tmp_path: Path) -> None:
    _write(tmp_path, "backend/src/execution/engine.py", "launch_feature()\n")

    assert main(["--project-root", str(tmp_path), "--report-only"]) == 0
    assert main(["--project-root", str(tmp_path)]) == 1


def test_forbidden_runtime_paths_fail_even_without_old_symbols(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/dataservice/domains/operations/empty.py",
        '"""Apparently harmless module."""\n',
    )
    _write(
        tmp_path,
        "backend/seed/capabilities/sci/policy.yaml",
        "schema_version: mission_policy.v1\n",
    )
    _write(tmp_path, "backend/src/agents/middlewares/base.py", "pass\n")
    _write(tmp_path, "backend/src/agents/thread_state.py", "pass\n")
    _write(tmp_path, "backend/src/tools/builtins/artifacts.py", "pass\n")
    _write(tmp_path, "frontend/components/latex/LatexEditorShell.tsx", "export {}\n")
    _write(tmp_path, "frontend/stores/latex.ts", "export {}\n")
    _write(tmp_path, "frontend/lib/api/latex.ts", "export {}\n")

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 8
    assert report["counts_by_rule"] == {
        "old_agent_middleware_path": 1,
        "old_agent_thread_state_path": 1,
        "old_capability_seed_path": 1,
        "old_builtin_tool_path": 1,
        "old_operations_path": 1,
        "old_frontend_latex_state_path": 2,
        "old_parallel_latex_editor_path": 1,
    }


def test_parallel_prism_review_and_direct_latex_frontend_routes_are_rejected(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "frontend/lib/api/workspace.ts",
        'fetch("/prism/latex-adapter/projects/project-1")\n',
    )
    _write(
        tmp_path,
        "frontend/lib/api/types.ts",
        "export type Surface = { file_changes: unknown[] };\n",
    )
    _write(
        tmp_path,
        "backend/src/gateway/routers/workspaces_contracts.py",
        "applied_file_changes: list[dict] = []\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 3
    assert report["counts_by_rule"] == {
        "old_frontend_latex_adapter_route": 1,
        "old_prism_dual_review_projection": 2,
    }


def test_direct_latex_docker_client_and_compile_router_paths_are_rejected(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "backend/src/services/latex/docker_client.py",
        "class DockerClient: pass\n",
    )
    _write(
        tmp_path,
        "backend/src/gateway/routers/latex_compile.py",
        "router = object()\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {
        "old_latex_compile_router_path": 1,
        "old_latex_direct_docker_client_path": 1,
    }


def test_removed_runtime_modules_and_billing_compatibility_are_rejected(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "backend/src/mcp/runtime.py", "pass\n")
    _write(tmp_path, "backend/src/subagents/__init__.py", "pass\n")
    _write(tmp_path, "backend/src/thesis/config.py", "pass\n")
    _write(tmp_path, "backend/src/task/tasks/memory.py", "pass\n")
    _write(tmp_path, "backend/src/dataservice/sandbox_api.py", "pass\n")
    _write(
        tmp_path,
        "backend/src/services/legacy_billing.py",
        "CreditReservationScope = object\n",
    )
    _write(
        tmp_path,
        "frontend/lib/api/credit.ts",
        'fetch("/internal/v1/credit/reservations")\n',
    )
    _write(tmp_path, "docker-compose.yml", "services:\n  memory-worker: {}\n")

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 8
    assert report["counts_by_rule"] == {
        "old_billing_compatibility_surface": 1,
        "old_dataservice_sandbox_path": 1,
        "old_external_credit_reservation_transport": 1,
        "old_mcp_runtime_path": 1,
        "old_memory_capture_path": 1,
        "old_memory_worker": 1,
        "old_subagents_path": 1,
        "old_thesis_runtime_path": 1,
    }


def test_hardcoded_registration_credit_bonus_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/services/credit_service.py",
        "REGISTRATION_BONUS = 100\n"
        "async def grant_registration_bonus(user_id: str): ...\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {
        "hardcoded_registration_credit_bonus": 2
    }


def test_clean_production_tree_passes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/mission/runtime.py",
        "class MissionRuntime:\n    pass\n",
    )

    report = build_cutover_report(tmp_path)

    assert report == {
        "status": "passed",
        "finding_count": 0,
        "counts_by_rule": {},
        "findings": [],
    }
