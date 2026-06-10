from __future__ import annotations

import json

import src.sandbox.workspace_layout as layout
from src.sandbox.workspace_layout import (
    WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH,
    WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH,
    WORKSPACE_MANIFEST_RELATIVE_PATH,
    WORKSPACE_PROTECTED_PATHS,
    WORKSPACE_ROOT,
    WORKSPACE_STANDARD_DIRS,
    build_agent_workspace_contract,
    build_artifact_manifest,
    build_dataset_provenance_manifest,
    build_workspace_sandbox_manifest,
    ensure_workspace_sandbox_layout,
)


def test_ensure_workspace_sandbox_layout_creates_standard_tree(tmp_path):
    manifest = ensure_workspace_sandbox_layout(
        tmp_path,
        workspace_id="ws-1",
        sandbox_id="workspace-ws-1",
        workspace_type="sci",
    )

    assert WORKSPACE_ROOT == "/workspace"
    for relative_path in WORKSPACE_STANDARD_DIRS:
        assert (tmp_path / relative_path).is_dir()

    manifest_path = tmp_path / WORKSPACE_MANIFEST_RELATIVE_PATH
    assert manifest_path.is_file()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted == manifest
    assert persisted["schema"] == "wenjin.workspace_sandbox.layout.v1"
    assert persisted["workspace_id"] == "ws-1"
    assert persisted["sandbox_id"] == "workspace-ws-1"
    assert persisted["workspace_type"] == "sci"
    assert persisted["virtual_root"] == "/workspace"
    assert persisted["directories"]["main"]["virtual_path"] == "/workspace/main"
    assert persisted["directories"]["outputs"]["review_surface"] == "artifact"
    assert persisted["datasets_manifest_path"] == "/workspace/datasets/manifest.json"
    assert persisted["task_scratch_root"] == "/workspace/tmp/tasks"
    assert persisted["workspace_profile"]["workspace_type"] == "sci"
    assert "/workspace/main/main.tex" in persisted["workspace_profile"]["primary_files"]
    assert "/workspace/reports/experiment-report.md" in persisted["workspace_profile"]["report_paths"]
    assert ".wenjin/**" in persisted["protected_paths"]


def test_workspace_sandbox_layout_manifest_is_stable_when_recreated(tmp_path):
    first = ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")
    second = ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert second == first
    assert json.loads((tmp_path / WORKSPACE_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")) == first


def test_ensure_workspace_sandbox_layout_creates_guidance_and_keep_files(tmp_path):
    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1", workspace_type="sci")

    readme_path = tmp_path / "main" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    outputs_readme_path = tmp_path / "outputs" / "README.md"
    reports_readme_path = tmp_path / "reports" / "README.md"

    assert readme_path.is_file()
    assert "/workspace/datasets" in readme
    assert (tmp_path / "datasets" / "README.md").is_file()
    assert outputs_readme_path.is_file()
    assert reports_readme_path.is_file()
    assert "internal tool refs" in outputs_readme_path.read_text(encoding="utf-8")
    assert "/workspace/tmp/tasks/.harness" in reports_readme_path.read_text(encoding="utf-8")
    assert "/workspace/reports/artifacts.json" in reports_readme_path.read_text(encoding="utf-8")
    assert layout.is_workspace_guidance_path("/workspace/outputs/README.md")
    assert layout.is_workspace_guidance_path("/workspace/reports/README.md")
    assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/outputs/README.md")
    assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/reports/README.md")
    artifact_manifest = json.loads(
        (tmp_path / WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert artifact_manifest == {
        "schema": "wenjin.workspace_sandbox.artifact_manifest.v1",
        "version": 1,
        "root": "/workspace",
        "artifacts": [],
        "rules": [
            "Record user-reviewable generated artifacts under /workspace/outputs or /workspace/reports.",
            "Use /workspace virtual paths only.",
            "Do not register internal refs or protected files.",
            "Prefer title, artifact_kind, content_hash, source_script, dataset_paths, and review notes when known.",
        ],
    }
    dataset_manifest = json.loads(
        (tmp_path / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert dataset_manifest == {
        "schema": "wenjin.workspace_sandbox.dataset_provenance.v1",
        "version": 1,
        "root": "/workspace/datasets",
        "datasets": [],
        "rules": [
            "Record every reusable dataset or uploaded input used by sandbox experiments.",
            "Use /workspace/datasets virtual paths only.",
            "Keep secrets, API keys, credentials, and raw private tokens out of this manifest.",
            "Prefer stable source_id, content_hash, license, and preparation notes when known.",
        ],
    }
    assert "/workspace/scripts" in readme
    assert "/workspace/outputs" in readme
    assert "/workspace/reports" in readme
    assert ".wenjin" in readme
    for relative_path in ("datasets/.gitkeep", "scripts/.gitkeep", "outputs/.gitkeep", "reports/.gitkeep"):
        assert (tmp_path / relative_path).is_file()


def test_ensure_workspace_sandbox_layout_preserves_existing_main_readme(tmp_path):
    readme_path = tmp_path / "main" / "README.md"
    readme_path.parent.mkdir(parents=True)
    readme_path.write_text("custom workspace note\n", encoding="utf-8")

    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert readme_path.read_text(encoding="utf-8") == "custom workspace note\n"


def test_ensure_workspace_sandbox_layout_preserves_existing_dataset_manifest(tmp_path):
    manifest_path = tmp_path / WORKSPACE_DATASETS_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        '{"schema":"custom","datasets":[{"path":"/workspace/datasets/raw.csv"}]}\n',
        encoding="utf-8",
    )

    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert manifest_path.read_text(encoding="utf-8") == (
        '{"schema":"custom","datasets":[{"path":"/workspace/datasets/raw.csv"}]}\n'
    )


def test_ensure_workspace_sandbox_layout_preserves_existing_artifact_manifest(tmp_path):
    manifest_path = tmp_path / WORKSPACE_ARTIFACTS_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        '{"schema":"custom","artifacts":[{"path":"/workspace/outputs/result.csv"}]}\n',
        encoding="utf-8",
    )

    ensure_workspace_sandbox_layout(tmp_path, workspace_id="ws-1")

    assert manifest_path.read_text(encoding="utf-8") == (
        '{"schema":"custom","artifacts":[{"path":"/workspace/outputs/result.csv"}]}\n'
    )


def test_merge_dataset_provenance_manifest_adds_safe_refs_without_overwriting_existing():
    existing = build_dataset_provenance_manifest(
        datasets=[
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "title": "User-curated survey",
                "source_id": "user-source",
                "custom_note": "kept",
            }
        ]
    )

    merged = layout.merge_dataset_provenance_manifest(
        existing,
        [
            {
                "path": "/workspace/datasets/raw/survey.csv",
                "title": "Runtime title should not overwrite",
                "source_id": "runtime-source",
            },
            {
                "path": "/workspace/datasets/clean/panel.csv",
                "source_id": "source-2",
                "name": "panel.csv",
                "title": "Clean panel",
                "description": "Prepared source data",
                "format": "csv",
                "mime_type": "text/csv",
                "size_bytes": 2048,
                "content_hash": "sha256:abc",
                "license": "CC-BY-4.0",
                "preparation": "normalized columns",
                "created_at": "2026-06-08T00:00:00Z",
                "updated_at": "2026-06-08T01:00:00Z",
                "private_token": "must not persist",
            },
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/survey.csv",
            "title": "User-curated survey",
            "source_id": "user-source",
            "custom_note": "kept",
        },
        {
            "path": "/workspace/datasets/clean/panel.csv",
            "source_id": "source-2",
            "name": "panel.csv",
            "title": "Clean panel",
            "description": "Prepared source data",
            "format": "csv",
            "mime_type": "text/csv",
            "size_bytes": 2048,
            "content_hash": "sha256:abc",
            "license": "CC-BY-4.0",
            "preparation": "normalized columns",
            "created_at": "2026-06-08T00:00:00Z",
            "updated_at": "2026-06-08T01:00:00Z",
        },
    ]


def test_merge_dataset_provenance_manifest_rejects_non_dataset_and_guidance_refs():
    merged = layout.merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        [
            {"path": "/workspace/datasets"},
            {"path": "/workspace/datasets/manifest.json"},
            {"path": "/workspace/datasets/README.md"},
            {"path": "/workspace/datasets/.gitkeep"},
            {"path": "/workspace/outputs/result.csv"},
            {"path": "/workspace/tmp/tasks/.harness/outputs/exec/tool.txt"},
            {"path": "/workspace/main/.env"},
            {"path": "/mnt/user-data/datasets/raw.csv"},
            {"path": "/workspace/datasets/raw/valid.csv", "source_id": "source-1"},
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/valid.csv",
            "source_id": "source-1",
        }
    ]


def test_merge_dataset_provenance_manifest_drops_host_path_values():
    merged = layout.merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        [
            {
                "path": "/workspace/datasets/raw/valid.csv",
                "source_id": "source-1",
                "description": "copied from /Users/ze/private/raw.csv",
                "preparation": "safe preparation note",
            },
        ],
    )

    assert merged["datasets"] == [
        {
            "path": "/workspace/datasets/raw/valid.csv",
            "source_id": "source-1",
            "preparation": "safe preparation note",
        }
    ]


def test_merge_artifact_manifest_adds_safe_artifacts_without_overwriting_existing():
    existing = build_artifact_manifest(
        artifacts=[
            {
                "path": "/workspace/outputs/result.csv",
                "title": "User title",
                "artifact_kind": "table",
                "custom_note": "kept",
            }
        ]
    )

    merged = layout.merge_artifact_manifest(
        existing,
        [
            {
                "path": "/workspace/outputs/result.csv",
                "title": "Runtime title should not overwrite",
                "artifact_kind": "table",
            },
            {
                "path": "/workspace/reports/summary.md",
                "title": "Summary",
                "description": "Readable analysis summary",
                "artifact_kind": "report",
                "mime_type": "text/markdown",
                "size_bytes": 2048,
                "content_hash": "sha256:abc",
                "source_script": "/workspace/scripts/analysis.py",
                "dataset_paths": ["/workspace/datasets/raw.csv", "/workspace/.env"],
                "notes": "ready for review",
                "private_token": "must not persist",
            },
        ],
    )

    assert merged["artifacts"] == [
        {
            "path": "/workspace/outputs/result.csv",
            "title": "User title",
            "artifact_kind": "table",
            "custom_note": "kept",
        },
        {
            "path": "/workspace/reports/summary.md",
            "title": "Summary",
            "description": "Readable analysis summary",
            "artifact_kind": "report",
            "mime_type": "text/markdown",
            "size_bytes": 2048,
            "content_hash": "sha256:abc",
            "source_script": "/workspace/scripts/analysis.py",
            "dataset_paths": ["/workspace/datasets/raw.csv"],
            "notes": "ready for review",
        },
    ]


def test_merge_artifact_manifest_rejects_internal_guidance_and_non_artifact_refs():
    merged = layout.merge_artifact_manifest(
        build_artifact_manifest(),
        [
            {"path": "/workspace/reports/artifacts.json"},
            {"path": "/workspace/tmp/tasks/.harness/outputs/exec/tool.txt"},
            {"path": "/workspace/main/paper.tex"},
            {"path": "/workspace/datasets/raw.csv"},
            {"path": "/workspace/main/.env"},
            {"path": "/mnt/user-data/outputs/result.csv"},
            {"path": "/workspace/outputs/figure.png", "title": "Figure"},
        ],
    )

    assert merged["artifacts"] == [
        {
            "path": "/workspace/outputs/figure.png",
            "title": "Figure",
        }
    ]


def test_merge_artifact_manifest_accepts_only_safe_source_script_refs():
    merged = layout.merge_artifact_manifest(
        build_artifact_manifest(),
        [
            {
                "path": "/workspace/outputs/good.csv",
                "title": "Good",
                "source_script": "/workspace/scripts/analysis.py",
            },
            {
                "path": "/workspace/outputs/main-source.csv",
                "title": "Main source should be dropped",
                "source_script": "/workspace/main/paper.tex",
            },
            {
                "path": "/workspace/outputs/internal-source.csv",
                "title": "Internal source should be dropped",
                "source_script": "/workspace/tmp/tasks/.harness/outputs/exec/tool.py",
            },
            {
                "path": "/workspace/outputs/host-source.csv",
                "title": "Host source should be dropped",
                "source_script": "/Users/ze/private/analysis.py",
            },
            {
                "path": "/workspace/outputs/guidance-source.csv",
                "title": "Guidance source should be dropped",
                "source_script": "/workspace/scripts/.gitkeep",
            },
        ],
    )

    assert merged["artifacts"] == [
        {
            "path": "/workspace/outputs/good.csv",
            "title": "Good",
            "source_script": "/workspace/scripts/analysis.py",
        },
        {
            "path": "/workspace/outputs/main-source.csv",
            "title": "Main source should be dropped",
        },
        {
            "path": "/workspace/outputs/internal-source.csv",
            "title": "Internal source should be dropped",
        },
        {
            "path": "/workspace/outputs/host-source.csv",
            "title": "Host source should be dropped",
        },
        {
            "path": "/workspace/outputs/guidance-source.csv",
            "title": "Guidance source should be dropped",
        },
    ]


def test_merge_artifact_manifest_requires_python_source_script_refs():
    merged = layout.merge_artifact_manifest(
        build_artifact_manifest(),
        [
            {
                "path": "/workspace/outputs/notebook-result.csv",
                "title": "Notebook result should drop source",
                "source_script": "/workspace/scripts/analysis.ipynb",
            },
            {
                "path": "/workspace/outputs/notes-result.csv",
                "title": "Notes result should drop source",
                "source_script": "/workspace/scripts/notes.md",
            },
            {
                "path": "/workspace/outputs/python-result.csv",
                "title": "Python result keeps source",
                "source_script": "/workspace/scripts/reproduce.py",
            },
        ],
    )

    assert merged["artifacts"] == [
        {
            "path": "/workspace/outputs/notebook-result.csv",
            "title": "Notebook result should drop source",
        },
        {
            "path": "/workspace/outputs/notes-result.csv",
            "title": "Notes result should drop source",
        },
        {
            "path": "/workspace/outputs/python-result.csv",
            "title": "Python result keeps source",
            "source_script": "/workspace/scripts/reproduce.py",
        },
    ]


def test_workspace_sandbox_manifest_does_not_expose_mutable_contract_state():
    first = build_workspace_sandbox_manifest(workspace_id="ws-1")
    first["directories"]["main"]["purpose"] = "mutated"
    first["workspace_profile"]["primary_files"].append("/workspace/main/mutated.txt")

    second = build_workspace_sandbox_manifest(workspace_id="ws-2")

    assert second["directories"]["main"]["purpose"] == "primary_project"
    assert "/workspace/main/mutated.txt" not in second["workspace_profile"]["primary_files"]


def test_workspace_type_profiles_keep_one_common_layout_with_domain_guidance():
    sci_contract = build_agent_workspace_contract(workspace_id="ws-1", workspace_type="sci")
    patent_contract = build_agent_workspace_contract(workspace_id="ws-2", workspace_type="patent")
    generic_contract = build_agent_workspace_contract(workspace_id="ws-3", workspace_type="unknown")

    assert (
        set(sci_contract["directories"])
        == set(patent_contract["directories"])
        == set(generic_contract["directories"])
    )
    assert sci_contract["workspace_profile"] == {
        "schema": "wenjin.workspace_sandbox.type_profile.v1",
        "workspace_type": "sci",
        "label": "SCI paper workspace",
        "primary_files": [
            "/workspace/main/main.tex",
            "/workspace/main/refs.bib",
            "/workspace/main/README.md",
        ],
        "script_paths": [
            "/workspace/scripts/analysis.py",
            "/workspace/scripts/reproduce.py",
        ],
        "output_paths": [
            "/workspace/outputs/figures",
            "/workspace/outputs/tables",
            "/workspace/outputs/metrics",
        ],
        "report_paths": [
            "/workspace/reports/literature-review.md",
            "/workspace/reports/experiment-report.md",
            "/workspace/reports/revision-plan.md",
        ],
        "rules": [
            "Keep manuscript-facing files under /workspace/main.",
            "Keep reusable experiments under /workspace/scripts and generated figures/tables under /workspace/outputs.",
            "Keep readable research notes, audits, and revision plans under /workspace/reports.",
            "Register reusable datasets and generated reviewable artifacts through the manifest tools.",
        ],
    }
    assert patent_contract["workspace_profile"]["primary_files"] == [
        "/workspace/main/patent-draft.md",
        "/workspace/main/claims.md",
        "/workspace/main/drawings-notes.md",
    ]
    assert generic_contract["workspace_profile"]["workspace_type"] == "generic"
    assert generic_contract["workspace_profile"]["primary_files"] == ["/workspace/main/README.md"]


def test_all_workspace_type_profiles_use_valid_common_layout_paths():
    assert layout.WORKSPACE_SUPPORTED_TYPES == (
        "thesis",
        "sci",
        "proposal",
        "software_copyright",
        "patent",
    )
    for workspace_type in layout.WORKSPACE_SUPPORTED_TYPES:
        assert layout.validate_workspace_type_profile(workspace_type) == {
            "workspace_type": workspace_type,
            "valid": True,
            "errors": [],
        }


def test_workspace_sandbox_directory_contract_is_common_and_closed():
    assert layout.WORKSPACE_STANDARD_DIRS == (
        "main",
        "datasets",
        "scripts",
        "outputs",
        "reports",
        "tmp",
        "tmp/tasks",
        "tmp/tasks/.harness/outputs",
        ".wenjin/env",
        ".wenjin/cache",
    )
    assert layout.WORKSPACE_PATH_CLASSES["workspace"] == ["/workspace/main"]
    assert layout.WORKSPACE_PATH_CLASSES["datasets"] == ["/workspace/datasets"]
    assert layout.WORKSPACE_PATH_CLASSES["scripts"] == ["/workspace/scripts"]
    assert layout.WORKSPACE_PATH_CLASSES["artifacts"] == [
        "/workspace/outputs",
        "/workspace/reports",
    ]
    assert layout.WORKSPACE_PATH_CLASSES["scratch"] == ["/workspace/tmp"]
    assert layout.WORKSPACE_PATH_CLASSES["task_scratch"] == ["/workspace/tmp/tasks"]
    assert layout.WORKSPACE_ARTIFACT_ROOTS == (
        {
            "name": "outputs",
            "virtual_path": "/workspace/outputs",
            "artifact_kind": "sandbox_output",
        },
        {
            "name": "reports",
            "virtual_path": "/workspace/reports",
            "artifact_kind": "sandbox_report",
        },
    )


def test_agent_workspace_contract_exposes_path_classes():
    contract = build_agent_workspace_contract(workspace_id="ws-1", workspace_type="sci")

    assert contract["path_classes"]["workspace"] == ["/workspace/main"]
    assert contract["path_classes"]["datasets"] == ["/workspace/datasets"]
    assert contract["path_classes"]["scripts"] == ["/workspace/scripts"]
    assert contract["path_classes"]["artifacts"] == ["/workspace/outputs", "/workspace/reports"]
    assert contract["path_classes"]["scratch"] == ["/workspace/tmp"]
    assert contract["task_scratch_root"] == "/workspace/tmp/tasks"
    assert contract["path_classes"]["task_scratch"] == ["/workspace/tmp/tasks"]
    assert contract["path_classes"]["runtime"] == [
        "/workspace/.wenjin/env",
        "/workspace/.wenjin/cache",
    ]
    assert "/workspace/tmp/tasks/.harness/**" in contract["path_classes"]["internal"]
    assert "/workspace/tmp/tasks/.harness/outputs/**" not in contract["path_classes"]["internal"]
    assert (
        "Do not list or search internal harness refs; inspect explicit output refs with sandbox.read_output_ref."
        in contract["rules"]
    )
    assert (
        "Do not directly edit layout guidance paths; update dataset and artifact manifests through sandbox.register_dataset or sandbox.register_artifact."
        in contract["rules"]
    )
    assert "/workspace/outputs/README.md" in contract["path_classes"]["guidance"]
    assert "/workspace/reports/artifacts.json" in contract["path_classes"]["guidance"]


def test_agent_workspace_contract_exposes_operation_policy():
    contract = build_agent_workspace_contract(workspace_id="ws-1", workspace_type="sci")

    assert contract["operation_policy"] == {
        "schema": "wenjin.workspace_sandbox.operation_policy.v1",
        "direct_write_tools": {
            "tools": [
                "sandbox.write_file",
                "sandbox.str_replace",
                "sandbox.apply_patch",
            ],
            "allowed_roots": [
                "/workspace/main",
                "/workspace/datasets",
                "/workspace/scripts",
                "/workspace/outputs",
                "/workspace/reports",
                "/workspace/tmp",
            ],
            "allowed_root_files": ["/workspace/*"],
            "denied_path_classes": ["protected", "internal", "guidance"],
            "rule": "Direct write tools may edit root-level project files and files under project, dataset, script, output, report, and scratch roots, but not protected, internal, layout guidance, or arbitrary top-level directory paths.",
        },
        "manifest_update_tools": {
            "sandbox.register_dataset": {
                "manifest_path": "/workspace/datasets/manifest.json",
                "allowed_roots": ["/workspace/datasets"],
            },
            "sandbox.register_artifact": {
                "manifest_path": "/workspace/reports/artifacts.json",
                "allowed_roots": ["/workspace/outputs", "/workspace/reports"],
            },
        },
        "read_internal_output_ref_tool": "sandbox.read_output_ref",
    }


def test_workspace_user_editable_path_policy_is_centralized():
    assert layout.is_user_editable_workspace_path("/workspace/main.tex")
    assert layout.is_user_editable_workspace_path("/workspace/main/paper.tex")
    assert layout.is_user_editable_workspace_path("/workspace/datasets/raw.csv")
    assert layout.is_user_editable_workspace_path("/workspace/scripts/analysis.py")
    assert layout.is_user_editable_workspace_path("/workspace/outputs/figure.png")
    assert layout.is_user_editable_workspace_path("/workspace/reports/summary.md")
    assert layout.is_user_editable_workspace_path("/workspace/tmp/tasks/exec/member/scratch.json")

    assert not layout.is_user_editable_workspace_path("/workspace/.env")
    assert not layout.is_user_editable_workspace_path("/workspace/.wenjin/manifest.json")
    assert not layout.is_user_editable_workspace_path("/workspace/tmp/tasks/.harness/outputs/exec/tool.txt")
    assert not layout.is_user_editable_workspace_path("/workspace/datasets/manifest.json")
    assert not layout.is_user_editable_workspace_path("/workspace/reports/artifacts.json")
    assert not layout.is_user_editable_workspace_path("/workspace/outputs/README.md")
    assert not layout.is_user_editable_workspace_path("/workspace/ad_hoc/experiment.py")
    assert not layout.is_user_editable_workspace_path("/mnt/user-data/outputs/result.csv")


def test_workspace_task_scratch_path_is_stable_and_sanitized():
    scratch_path = layout.workspace_task_scratch_path(
        execution_id="exec 1/../../secret",
        node_id=".research/synth:v1",
    )

    assert scratch_path == "/workspace/tmp/tasks/exec_1_secret/research_synth_v1"
    assert scratch_path.startswith("/workspace/tmp/tasks/")
    assert not layout.is_workspace_internal_path(scratch_path)
    assert not layout.is_workspace_protected_path(scratch_path)
    assert not layout.is_user_reviewable_workspace_artifact_path(f"{scratch_path}/notes.md")


def test_workspace_task_contract_projects_member_scoped_paths():
    contract = layout.build_workspace_task_contract(
        execution_id="exec 1/../../secret",
        node_id=".research/synth:v1",
        invocation_id="tool run/1",
    )

    assert contract == {
        "schema": "wenjin.workspace_sandbox.task_contract.v1",
        "execution_id": "exec 1/../../secret",
        "node_id": ".research/synth:v1",
        "invocation_id": "tool run/1",
        "scratch_path": "/workspace/tmp/tasks/exec_1_secret/research_synth_v1",
        "output_ref_root": "/workspace/tmp/tasks/.harness/outputs/exec-1-secret/research-synth-v1/tool-run-1",
        "read_output_ref_tool": "sandbox.read_output_ref",
        "writable_scratch_roots": ["/workspace/tmp/tasks/exec_1_secret/research_synth_v1"],
        "reviewable_artifact_roots": ["/workspace/outputs", "/workspace/reports"],
        "manifest_paths": {
            "datasets": "/workspace/datasets/manifest.json",
            "artifacts": "/workspace/reports/artifacts.json",
        },
        "rules": [
            "Use scratch_path for temporary task-local files that should not become user-facing artifacts.",
            "Do not list, search, edit, register, or cite output_ref_root paths as user-facing artifacts.",
            "Inspect explicit output refs under output_ref_root only with sandbox.read_output_ref.",
            "Promote durable files to /workspace/outputs or /workspace/reports and register them with sandbox.register_artifact.",
        ],
    }
    assert layout.is_workspace_internal_path(f"{contract['output_ref_root']}/stdout.txt")
    assert layout.is_workspace_readable_internal_output_ref(f"{contract['output_ref_root']}/stdout.txt")
    assert not layout.is_user_reviewable_workspace_artifact_path(f"{contract['output_ref_root']}/stdout.txt")


def test_workspace_protected_paths_include_runtime_and_secret_material():
    assert WORKSPACE_PROTECTED_PATHS == (
        ".git/**",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "*.pem",
        "*.key",
        ".wenjin/**",
    )


def test_workspace_virtual_path_normalization_rejects_outside_and_traversal_paths():
    assert (
        layout.normalize_workspace_virtual_path("/workspace/main/paper.tex")
        == "/workspace/main/paper.tex"
    )
    assert (
        layout.normalize_workspace_virtual_path("/tmp/ws/workspace/reports/summary.md")
        == "/workspace/reports/summary.md"
    )
    assert layout.workspace_relative_path("/workspace/reports/summary.md") == "reports/summary.md"

    for invalid in (
        "/mnt/user-data/outputs/report.md",
        "/workspace/outputs/../secrets.txt",
        "/workspace/main\x00.tex",
    ):
        try:
            layout.normalize_workspace_virtual_path(invalid)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError(f"expected invalid workspace path: {invalid}")


def test_workspace_virtual_path_helper_is_strict_and_idempotent():
    assert layout.workspace_virtual_path("outputs/result.csv") == "/workspace/outputs/result.csv"
    assert layout.workspace_virtual_path("/workspace/reports/summary.md") == "/workspace/reports/summary.md"
    assert layout.workspace_virtual_path("") == "/workspace"

    for invalid in (
        "/tmp/host/result.csv",
        "outputs/../.env",
        "main\x00.tex",
    ):
        try:
            layout.workspace_virtual_path(invalid)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError(f"expected invalid workspace helper input: {invalid}")


def test_workspace_path_classification_is_centralized_for_harness_boundaries():
    assert layout.is_workspace_protected_path("/workspace/.wenjin")
    assert layout.is_workspace_protected_path("/workspace/.wenjin/state/debug.json")
    assert layout.is_workspace_protected_path("/workspace/.wenjin/env/python/bin/python")
    assert layout.is_workspace_protected_path("/workspace/.env")
    assert layout.is_workspace_protected_path("/workspace/.env.local")
    assert layout.is_workspace_protected_path("/workspace/main/.env")
    assert layout.is_workspace_protected_path("/workspace/scripts/.env.local")
    assert layout.is_workspace_internal_path(
        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/tool.txt"
    )
    assert layout.is_workspace_readable_internal_output_ref(
        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/tool.txt"
    )
    assert not layout.is_workspace_readable_internal_output_ref(
        "/workspace/.wenjin/state/debug.json"
    )
    assert not layout.is_user_reviewable_workspace_artifact_path(
        "/workspace/tmp/tasks/.harness/outputs/exec-1/node/tool.txt"
    )
    assert layout.is_user_reviewable_workspace_artifact_path("/workspace/outputs/figure.png")
    assert layout.is_user_reviewable_workspace_artifact_path("/workspace/reports/summary.md")
    assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/tmp/tasks/exec-1/draft.json")
    assert not layout.is_user_reviewable_workspace_artifact_path("/workspace/main/analysis.py")
    assert layout.workspace_artifact_root_for_path("/workspace/reports/summary.md") == {
        "name": "reports",
        "virtual_path": "/workspace/reports",
        "artifact_kind": "sandbox_report",
    }

    assert (
        layout.classify_workspace_path("/workspace/.wenjin/cache/pip/index")
        == "protected"
    )
    assert layout.classify_workspace_path("/workspace/.wenjin/state/debug.json") == "protected"
    assert layout.classify_workspace_path("/workspace/main/.env") == "protected"
    assert layout.classify_workspace_path("/workspace/scripts/.env.local") == "protected"
    assert layout.classify_workspace_path("/workspace/tmp/tasks/exec-1/draft.json") == "hidden"
    assert (
        layout.classify_workspace_path("/workspace/tmp/tasks/.harness/outputs/exec/tool.txt")
        == "internal"
    )
    assert layout.classify_workspace_path("/workspace/outputs/README.md") == "hidden"
    assert layout.classify_workspace_path("/workspace/reports/README.md") == "hidden"
    assert layout.classify_workspace_path("/workspace/reports/summary.md") == "artifact"
    assert layout.classify_workspace_path("/workspace/tmp/scratch.json") == "hidden"
    assert layout.classify_workspace_path("/workspace/main/paper.tex") == "workspace"
