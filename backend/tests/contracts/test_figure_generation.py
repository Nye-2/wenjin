"""Tests for research figure generation public contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.contracts.figure_generation import FigureArtifactManifest, FigureSpec


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


def test_manifest_requires_reviewable_workspace_path() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureArtifactManifest(
            figure_id="bad",
            figure_type="graphical_abstract",
            strategy="llm_image",
            primary_path="/workspace/.wenjin/cache/secret.png",
        )


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


@pytest.mark.parametrize("strategy", ["mermaid", "graphviz", "tikz"])
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
            strategy="mermaid",
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
            strategy="mermaid",
            purpose="Show method flow",
            output_targets=["/workspace/outputs/.wenjin"],
        )


def test_manifest_primary_path_rejects_terminal_wenjin_segments() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureArtifactManifest(
            figure_id="terminal_wenjin_primary",
            figure_type="method_flow",
            strategy="mermaid",
            primary_path="/workspace/outputs/.wenjin",
        )


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
            strategy="mermaid",
            purpose="Show method flow",
            output_targets=[output_target],
        )


@pytest.mark.parametrize(
    "primary_path",
    [
        "/workspace/outputs/.env",
        "/workspace/outputs/secret.pem",
        "/workspace/outputs/secret.key",
    ],
)
def test_manifest_primary_path_rejects_protected_artifact_paths(primary_path: str) -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureArtifactManifest(
            figure_id="protected_primary",
            figure_type="method_flow",
            strategy="mermaid",
            primary_path=primary_path,
        )


@pytest.mark.parametrize(
    "dataset_path",
    [
        "/workspace/.git/config",
        "/workspace/tmp/tasks/.harness/outputs/file.png",
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
