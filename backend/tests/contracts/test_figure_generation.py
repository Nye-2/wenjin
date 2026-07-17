"""Tests for research figure generation public contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.contracts.figure_generation import (
    AcademicFigureBrief,
    AcademicVisualCandidate,
    AcademicVisualRenderInput,
    ExactVisualLabel,
    FigureArtifactManifest,
    FigureSpec,
    VisualCandidateRef,
)
from src.contracts.prism_context import PrismContextRef, split_utf8_selection


def _manifest(**updates) -> FigureArtifactManifest:
    payload = {
        "figure_id": "figure-1",
        "figure_type": "method_flow",
        "strategy": "graphviz",
        "evidence_level": "explanatory",
        "candidate": VisualCandidateRef(
            kind="sandbox_artifact",
            ref="sandbox-artifact:figure-1",
            content_hash="sha256:figure",
        ),
        "renderer_id": "graphviz",
        "renderer_version": "2.42.2",
        "source_code_ref": "sandbox-script:sha256:" + "a" * 64,
        "source_code_hash": "a" * 64,
        "context_hash": "b" * 64,
        "ai_generated": False,
    }
    payload.update(updates)
    return FigureArtifactManifest.model_validate(payload)


def _generative_brief(**updates) -> AcademicFigureBrief:
    payload = {
        "figure_spec": FigureSpec(
            figure_id="visual-1",
            title="Visual",
            figure_type="conceptual_illustration",
            strategy="llm_image",
            purpose="Explain the concept without representing empirical evidence",
            output_targets=["/workspace/outputs/figures/visual-1/figure.png"],
        ),
        "intended_use": "manuscript",
        "audience": "Computer science researchers",
        "target_language": "English",
        "aspect_ratio": "3:2",
        "composition": "A left-to-right conceptual composition",
    }
    payload.update(updates)
    return AcademicFigureBrief.model_validate(payload)


def test_data_plot_rejects_llm_image_strategy() -> None:
    with pytest.raises(ValidationError, match="data figures must use code"):
        FigureSpec(
            figure_id="fed_llm_curve",
            title="Federated LLM Accuracy",
            figure_type="data_plot",
            strategy="llm_image",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/fed_llm_curve/figure.png"],
        )


def test_evidence_level_rejects_llm_image_strategy() -> None:
    with pytest.raises(ValidationError, match="evidence figures cannot use"):
        FigureSpec(
            figure_id="software_dashboard_evidence",
            title="Software Dashboard Evidence",
            figure_type="graphical_abstract",
            strategy="llm_image",
            evidence_level="evidence",
            purpose="Stage a compliance evidence visual",
            output_targets=["/workspace/outputs/screenshots/software_copyright/dashboard.png"],
        )


def test_python_schematic_accepts_geometric_schematic() -> None:
    spec = FigureSpec(
        figure_id="model_geometry",
        title="Model Geometry",
        figure_type="geometric_schematic",
        strategy="python_schematic",
        evidence_level="evidence",
        visual_profile_id="math_modeling_cumcm_default",
        palette_id="okabe_ito_print_safe",
        purpose="Show the geometry used by the optimization model",
        output_targets=["/workspace/outputs/figures/math_modeling/model_geometry/figure.svg"],
    )

    assert spec.figure_type == "geometric_schematic"
    assert spec.strategy == "python_schematic"
    assert spec.visual_profile_id == "math_modeling_cumcm_default"


def test_matplotlib_figure_spec_accepts_workspace_output() -> None:
    spec = FigureSpec(
        figure_id="fed_llm_curve",
        title="Federated LLM Accuracy",
        figure_type="experiment_plot",
        strategy="matplotlib",
        purpose="Show benchmark trend",
        output_targets=["/workspace/outputs/figures/fed_llm_curve/figure.png"],
        dataset_paths=["/workspace/datasets/results.csv"],
    )

    assert spec.strategy == "matplotlib"
    assert spec.output_targets[0].startswith("/workspace/outputs/")


def test_matplotlib_figure_spec_accepts_verified_derived_data() -> None:
    spec = FigureSpec(
        figure_id="q3_policy_summary",
        title="Policy comparison",
        figure_type="statistical_chart",
        strategy="matplotlib",
        purpose="Plot verified third-question results",
        output_targets=["/workspace/outputs/figures/q3_policy_summary.png"],
        dataset_paths=["/workspace/outputs/q3_plot_data.csv"],
    )

    assert spec.dataset_paths == ["/workspace/outputs/q3_plot_data.csv"]


def test_figure_spec_rejects_same_path_as_input_and_output() -> None:
    path = "/workspace/outputs/figures/q3_policy_summary.png"

    with pytest.raises(ValidationError, match="must not overlap"):
        FigureSpec(
            figure_id="q3_policy_summary",
            title="Policy comparison",
            figure_type="statistical_chart",
            strategy="matplotlib",
            purpose="Plot verified third-question results",
            output_targets=[path],
            dataset_paths=[path],
        )


def test_deterministic_figure_spec_requires_exactly_one_reviewable_output_target() -> None:
    base = {
        "figure_id": "fed_llm_curve",
        "title": "Federated LLM Accuracy",
        "figure_type": "experiment_plot",
        "strategy": "matplotlib",
        "purpose": "Show benchmark trend",
    }

    with pytest.raises(ValidationError, match="exactly one reviewable output path"):
        FigureSpec.model_validate(base)

    with pytest.raises(ValidationError, match="at most 1 item"):
        FigureSpec.model_validate(
            {
                **base,
                "output_targets": [
                    "/workspace/outputs/figures/fed_llm_curve/figure.png",
                    "/workspace/outputs/figures/fed_llm_curve/figure.svg",
                ],
            }
        )


def test_academic_visual_schema_explains_reviewable_output_target_path() -> None:
    schema = AcademicVisualRenderInput.model_json_schema()
    output_targets = schema["$defs"]["FigureSpec"]["properties"]["output_targets"]
    dataset_paths = schema["$defs"]["FigureSpec"]["properties"]["dataset_paths"]

    assert output_targets["maxItems"] == 1
    assert output_targets["items"]["pattern"].startswith("^/workspace/")
    assert "Deterministic strategies require exactly one" in output_targets["description"]
    assert "/workspace/outputs/figures/q3_policy_summary.png" in output_targets["description"]
    assert dataset_paths["items"]["pattern"] == (
        r"^/workspace/(?:datasets|outputs|reports)/.+"
    )
    assert "verified derived data" in dataset_paths["description"]


def test_manifest_requires_reviewable_workspace_path() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        _manifest(intended_output_targets=("/workspace/.wenjin/cache/secret.png",))


def test_conceptual_llm_image_spec_is_accepted() -> None:
    spec = FigureSpec(
        figure_id="federated_learning_abstract",
        title="Federated Learning Graphical Abstract",
        figure_type="graphical_abstract",
        strategy="llm_image",
        purpose="Conceptually explain privacy-preserving model collaboration",
        output_targets=["/workspace/reports/figures/federated_learning_abstract/figure.png"],
        caption="Conceptual overview of privacy-preserving collaboration.",
        alt_text="A conceptual illustration of multiple sites training a shared model without sharing raw data.",
    )

    assert spec.figure_type == "graphical_abstract"
    assert spec.strategy == "llm_image"


def test_mechanism_illustration_llm_image_spec_is_accepted() -> None:
    spec = FigureSpec(
        figure_id="attention_mechanism",
        title="Attention Mechanism Illustration",
        figure_type="mechanism_illustration",
        strategy="llm_image",
        purpose="Conceptually explain how the method routes private signals",
        output_targets=["/workspace/reports/figures/attention_mechanism/figure.png"],
    )

    assert spec.figure_type == "mechanism_illustration"
    assert spec.strategy == "llm_image"


@pytest.mark.parametrize(
    "figure_type",
    ["architecture_diagram", "method_flow", "patent_drawing"],
)
@pytest.mark.parametrize("strategy", ["llm_image", "hybrid"])
def test_structured_figures_reject_llm_image_strategies(
    figure_type: str,
    strategy: str,
) -> None:
    with pytest.raises(ValidationError, match="structured figures"):
        FigureSpec(
            figure_id="structured_visual",
            title="Structured Visual",
            figure_type=figure_type,
            strategy=strategy,
            purpose="Show auditable structure",
            output_targets=["/workspace/outputs/figures/structured_visual/figure.png"],
        )


@pytest.mark.parametrize("strategy", ["graphviz"])
def test_data_figures_reject_non_chart_code_strategies(strategy: str) -> None:
    with pytest.raises(ValidationError, match="data figures must use chart code"):
        FigureSpec(
            figure_id="bad_data_strategy",
            title="Bad Data Strategy",
            figure_type="experiment_plot",
            strategy=strategy,
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/bad_data_strategy/figure.png"],
        )


def test_output_targets_outside_outputs_or_reports_are_rejected() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureSpec(
            figure_id="bad_target",
            title="Bad Target",
            figure_type="method_flow",
            strategy="graphviz",
            purpose="Show the method flow",
            output_targets=["/workspace/tmp/figures/bad_target/figure.png"],
        )


def test_dataset_paths_reject_protected_wenjin_and_traversal() -> None:
    with pytest.raises(ValidationError, match="unsafe workspace path"):
        FigureSpec(
            figure_id="unsafe_data",
            title="Unsafe Dataset",
            figure_type="experiment_plot",
            strategy="seaborn",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/unsafe_data/figure.png"],
            dataset_paths=["/workspace/.wenjin/cache/results.csv"],
        )

    with pytest.raises(ValidationError, match="unsafe workspace path"):
        FigureSpec(
            figure_id="traversal_data",
            title="Traversal Dataset",
            figure_type="experiment_plot",
            strategy="seaborn",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/traversal_data/figure.png"],
            dataset_paths=["/workspace/datasets/../private/results.csv"],
        )


def test_dataset_paths_reject_non_data_workspace_roots() -> None:
    with pytest.raises(ValidationError, match="visual data path must be under"):
        FigureSpec(
            figure_id="script_as_data",
            title="Script as data",
            figure_type="experiment_plot",
            strategy="matplotlib",
            purpose="Reject executable input roots",
            output_targets=["/workspace/outputs/figures/script_as_data.png"],
            dataset_paths=["/workspace/scripts/analysis.py"],
        )


@pytest.mark.parametrize(
    "dataset_path",
    [
        "/workspace/.wenjin",
        "/workspace/datasets/.wenjin",
    ],
)
def test_dataset_paths_reject_terminal_wenjin_segments(dataset_path: str) -> None:
    with pytest.raises(ValidationError, match="unsafe workspace path"):
        FigureSpec(
            figure_id="terminal_wenjin_dataset",
            title="Terminal Wenjin Dataset",
            figure_type="experiment_plot",
            strategy="matplotlib",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/terminal_wenjin_dataset/figure.png"],
            dataset_paths=[dataset_path],
        )


def test_output_targets_reject_terminal_wenjin_segments() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureSpec(
            figure_id="terminal_wenjin_output",
            title="Terminal Wenjin Output",
            figure_type="method_flow",
            strategy="graphviz",
            purpose="Show method flow",
            output_targets=["/workspace/outputs/.wenjin"],
        )


def test_manifest_intended_output_rejects_terminal_wenjin_segments() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        _manifest(intended_output_targets=("/workspace/outputs/.wenjin",))


@pytest.mark.parametrize(
    "output_target",
    [
        "/workspace/outputs/.env",
        "/workspace/outputs/secret.pem",
        "/workspace/outputs/secret.key",
    ],
)
def test_output_targets_reject_protected_artifact_paths(output_target: str) -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureSpec(
            figure_id="protected_output",
            title="Protected Output",
            figure_type="method_flow",
            strategy="graphviz",
            purpose="Show method flow",
            output_targets=[output_target],
        )


@pytest.mark.parametrize(
    "intended_output",
    [
        "/workspace/outputs/.env",
        "/workspace/outputs/secret.pem",
        "/workspace/outputs/secret.key",
    ],
)
def test_manifest_intended_output_rejects_protected_artifact_paths(intended_output: str) -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        _manifest(intended_output_targets=(intended_output,))


@pytest.mark.parametrize(
    "dataset_path",
    [
        "/workspace/.git/config",
        "/workspace/tmp/tasks/.wenjin/outputs/file.png",
        "/workspace/datasets/.env",
        "/workspace/datasets/secret.pem",
        "/workspace/datasets/secret.key",
    ],
)
def test_dataset_paths_reject_protected_and_internal_paths(dataset_path: str) -> None:
    with pytest.raises(ValidationError, match="unsafe workspace path"):
        FigureSpec(
            figure_id="protected_dataset",
            title="Protected Dataset",
            figure_type="experiment_plot",
            strategy="seaborn",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/protected_dataset/figure.png"],
            dataset_paths=[dataset_path],
        )


@pytest.mark.parametrize(
    "figure_type",
    [
        "conceptual_illustration",
        "experimental_setup_illustration",
        "academic_cover",
        "educational_explainer",
    ],
)
def test_new_generative_figure_types_accept_llm_image(figure_type: str) -> None:
    spec = FigureSpec(
        figure_id="generated-visual",
        title="Generated Visual",
        figure_type=figure_type,
        strategy="llm_image",
        purpose="Create a non-evidentiary academic illustration",
        output_targets=["/workspace/outputs/figures/generated-visual/figure.png"],
    )

    assert spec.figure_type == figure_type


def test_llm_image_is_rejected_for_non_generative_other_type() -> None:
    with pytest.raises(ValidationError, match="limited to generative figure types"):
        FigureSpec(
            figure_id="other-visual",
            title="Other Visual",
            figure_type="other",
            strategy="llm_image",
            purpose="Attempt an unclassified generated visual",
            output_targets=["/workspace/outputs/figures/other-visual/figure.png"],
        )


def test_generative_type_rejects_deterministic_chart_strategy() -> None:
    with pytest.raises(ValidationError, match="require llm_image or hybrid"):
        FigureSpec(
            figure_id="concept",
            title="Concept",
            figure_type="conceptual_illustration",
            strategy="matplotlib",
            purpose="Explain a concept",
            output_targets=["/workspace/outputs/figures/concept/figure.png"],
        )


@pytest.mark.parametrize("figure_type", ["geometric_schematic", "simulation_snapshot"])
def test_schematic_types_reject_non_schematic_strategy(figure_type: str) -> None:
    with pytest.raises(ValidationError, match="python_schematic"):
        FigureSpec(
            figure_id="schematic",
            title="Schematic",
            figure_type=figure_type,
            strategy="graphviz",
            purpose="Render exact geometry",
            output_targets=["/workspace/outputs/figures/schematic/figure.svg"],
        )


def test_exact_labels_require_hybrid_for_generative_figure() -> None:
    with pytest.raises(ValidationError, match="exact labels require hybrid"):
        _generative_brief(exact_labels=(ExactVisualLabel(key="server", text="Global model", semantic_anchor="center"),))

    brief = _generative_brief(
        figure_spec=FigureSpec(
            figure_id="visual-1",
            title="Visual",
            figure_type="conceptual_illustration",
            strategy="hybrid",
            purpose="Explain the concept with exact terminology",
            output_targets=["/workspace/outputs/figures/visual-1/figure.png"],
        ),
        exact_labels=(ExactVisualLabel(key="server", text="Global model", semantic_anchor="center"),),
    )

    assert brief.figure_spec.strategy == "hybrid"


def test_prism_context_requires_canonical_hash_and_utf8_byte_range() -> None:
    selection_hash = f"sha256:{'a' * 64}"
    context = PrismContextRef(
        workspace_id="ws-1",
        prism_project_id="project-1",
        file_id="file-1",
        base_revision_ref="revision-3",
        selection_hash=selection_hash,
        selection_byte_range=(10, 42),
    )

    assert context.selection_byte_range == (10, 42)
    with pytest.raises(ValidationError, match="selection_byte_range"):
        PrismContextRef(
            workspace_id="ws-1",
            prism_project_id="project-1",
            file_id="file-1",
            base_revision_ref="revision-3",
            selection_hash=selection_hash,
        )
    with pytest.raises(ValidationError, match="selection_hash"):
        PrismContextRef(
            workspace_id="ws-1",
            prism_project_id="project-1",
            file_id="file-1",
            base_revision_ref="revision-3",
            selection_hash="sha256:not-a-digest",
            selection_byte_range=(10, 42),
        )


def test_prism_selection_splits_only_at_utf8_boundaries() -> None:
    content = "A😀联邦B"
    start = len(b"A")
    end = start + len("😀联邦".encode())

    assert split_utf8_selection(content, (start, end)) == ("A", "😀联邦", "B")
    with pytest.raises(ValueError, match="UTF-8 boundaries"):
        split_utf8_selection(content, (start + 1, end))


@pytest.mark.parametrize(
    ("strategy", "figure_type", "render"),
    [
        (
            "matplotlib",
            "data_plot",
            {"kind": "code", "source_code": "print('plot')", "script_path": "/workspace/scripts/plot.py"},
        ),
        (
            "seaborn",
            "experiment_plot",
            {"kind": "code", "source_code": "print('plot')", "script_path": "/workspace/scripts/plot.py"},
        ),
        ("graphviz", "architecture_diagram", {"kind": "structured", "source": "digraph { A -> B }", "output_format": "svg"}),
        (
            "python_schematic",
            "geometric_schematic",
            {"kind": "code", "source_code": "print('shape')", "script_path": "/workspace/scripts/shape.py"},
        ),
        ("llm_image", "graphical_abstract", {"kind": "generative", "size": "1536x1024"}),
        ("hybrid", "academic_cover", {"kind": "generative", "size": "1024x1536"}),
    ],
)
def test_render_contract_routes_supported_strategies(strategy: str, figure_type: str, render: dict[str, object]) -> None:
    brief = _generative_brief(
        figure_spec=FigureSpec(
            figure_id="routed-visual",
            title="Routed Visual",
            figure_type=figure_type,
            strategy=strategy,
            purpose="Exercise the canonical strategy route",
            output_targets=["/workspace/outputs/figures/routed-visual/figure.png"],
        )
    )

    request = AcademicVisualRenderInput.model_validate({"brief": brief, "render": render})

    assert request.render.kind == render["kind"]


def test_render_payload_must_match_strategy() -> None:
    with pytest.raises(ValidationError, match="requires generative render payload"):
        AcademicVisualRenderInput.model_validate(
            {
                "brief": _generative_brief(),
                "render": {"kind": "structured", "source": "flowchart LR; A-->B", "output_format": "svg"},
            }
        )


def test_candidate_requires_one_primary_ref_and_image2_for_generative_output() -> None:
    payload = {
        "candidate_id": "candidate-1",
        "figure_id": "visual-1",
        "figure_type": "conceptual_illustration",
        "strategy": "llm_image",
        "evidence_level": "explanatory",
        "preview_ref": "preview:visual-1",
        "review_preview_ref": "preview:visual-1",
        "preview_hash": "sha256:preview",
        "content_hash": "sha256:content",
        "mime_type": "image/png",
        "width": 1536,
        "height": 1024,
        "renderer_id": "openai-images",
        "renderer_version": "v1",
        "provider_model": "gpt-image-2",
        "prompt_contract_version": "wenjin.academic_visual.prompt.v1",
        "source_prompt_hash": "a" * 64,
        "context_hash": "sha256:context",
        "ai_generated": True,
    }
    candidate = AcademicVisualCandidate.model_validate(payload)
    assert candidate.preview_ref == "preview:visual-1"

    with pytest.raises(ValidationError, match="exactly one primary"):
        AcademicVisualCandidate.model_validate({**payload, "sandbox_artifact_ref": "artifact:visual-1"})
    with pytest.raises(ValidationError, match="provider_model gpt-image-2"):
        AcademicVisualCandidate.model_validate({**payload, "provider_model": None})


def test_manifest_v2_uses_candidate_ref_and_rejects_v1_primary_path() -> None:
    manifest = _manifest(intended_output_targets=("/workspace/outputs/figures/flow/figure.svg",))

    assert manifest.schema == "wenjin.figure_generation.artifact.v2"
    assert manifest.candidate.kind == "sandbox_artifact"
    with pytest.raises(ValidationError):
        FigureArtifactManifest.model_validate(
            {
                "schema": "wenjin.figure_generation.artifact.v1",
                "figure_id": "legacy",
                "figure_type": "method_flow",
                "strategy": "graphviz",
                "primary_path": "/workspace/outputs/figures/legacy.svg",
            }
        )


def test_candidate_and_manifest_cannot_bypass_canonical_strategy_route() -> None:
    with pytest.raises(ValidationError, match="data figures must use code"):
        AcademicVisualCandidate.model_validate(
            {
                "candidate_id": "invalid-candidate",
                "figure_id": "results",
                "figure_type": "data_plot",
                "strategy": "llm_image",
                "evidence_level": "explanatory",
                    "preview_ref": "preview:results",
                    "review_preview_ref": "preview:results",
                "preview_hash": "sha256:preview",
                "content_hash": "sha256:content",
                "mime_type": "image/png",
                "renderer_id": "openai-images",
                "renderer_version": "v1",
                "provider_model": "gpt-image-2",
                "prompt_contract_version": "wenjin.academic_visual.prompt.v1",
                "source_prompt_hash": "a" * 64,
                "context_hash": "sha256:context",
                "ai_generated": True,
            }
        )

    with pytest.raises(ValidationError, match="requires sandbox_artifact candidate ref"):
        _manifest(
            candidate=VisualCandidateRef(
                kind="transient_preview",
                ref="preview:flow",
                content_hash="sha256:flow",
            )
        )


@pytest.mark.parametrize("legacy_type", ["line_chart", "bar_chart"])
def test_current_figure_type_rejects_legacy_chart_taxonomy(legacy_type: str) -> None:
    with pytest.raises(ValidationError, match="figure_type"):
        FigureSpec.model_validate(
            {
                "figure_id": "legacy-chart",
                "title": "Legacy chart",
                "figure_type": legacy_type,
                "strategy": "matplotlib",
                "purpose": "Reject removed taxonomy",
                "output_targets": ["/workspace/outputs/legacy-chart.png"],
            }
        )
