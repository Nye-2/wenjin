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
    assert report["finding_count"] == 7
    assert report["counts_by_rule"] == {
        "old_execution_record": 1,
        "old_config_tool_id": 2,
        "old_fixed_subagent_config": 2,
        "old_review_ssot": 1,
        "old_search_provider": 1,
    }


def test_old_brand_config_is_rejected_without_scanning_unrelated_docs(tmp_path: Path) -> None:
    _write(tmp_path, "backend/src/config/config_loader.py", 'os.getenv("GUANLAN_CONFIG_PATH")\n')
    _write(tmp_path, ".env.example", "GUANLAN_CONFIG_PATH=/tmp/config.yaml\n")
    _write(tmp_path, "docs/history.md", "GUANLAN_CONFIG_PATH was historical.\n")

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {"old_brand_config": 2}


def test_model_flags_are_scoped_to_catalog_runtime(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "backend/src/database/models/model_catalog.py",
        "supports_tools = True\n",
    )
    _write(
        tmp_path,
        "frontend/lib/api/types.ts",
        "export type Display = { supports_tools: boolean };\n",
    )

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 1
    assert report["findings"][0]["rule_id"] == "model_capability_compatibility_flags"


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

    report = build_cutover_report(tmp_path)

    assert report["finding_count"] == 2
    assert report["counts_by_rule"] == {
        "old_capability_seed_path": 1,
        "old_operations_path": 1,
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
