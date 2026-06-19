from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from src.agents.harness.langchain_adapter import TOOL_DEFINITIONS
from src.agents.harness.policy import resolve_harness_policy


def _ctx(
    *,
    capability_policy: dict[str, Any] | None = None,
    context_bundle: dict[str, Any] | None = None,
    requested_tools: tuple[str, ...] = (),
    skill: dict[str, Any] | None = None,
) -> HarnessRunContext:
    return HarnessRunContext(
        workspace_id="ws-1",
        user_id="user-1",
        execution_id="exec-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
        capability_policy=capability_policy or {},
        requested_tools=requested_tools,
        skill=skill or {},
        context_bundle=context_bundle or {},
    )


def _figure_spec(**overrides: Any) -> dict[str, Any]:
    spec = {
        "schema": "wenjin.figure_generation.spec.v1",
        "figure_id": "accuracy_curve",
        "title": "Accuracy Curve",
        "figure_type": "experiment_plot",
        "strategy": "matplotlib",
        "purpose": "Show model accuracy over time.",
        "output_targets": ["/workspace/outputs/figures/accuracy_curve/figure.png"],
        "dataset_paths": ["/workspace/datasets/results.csv"],
    }
    spec.update(overrides)
    return spec


def _sandbox_bundle(
    sandbox: Any,
    *,
    job_id: str = "job-image-1",
    environment_id: str = "env-image-1",
) -> dict[str, Any]:
    return {
        "_harness_sandbox": sandbox,
        "_harness_sandbox_job": {
            "sandbox_job_id": job_id,
            "sandbox_environment_id": environment_id,
        },
    }


@pytest.mark.asyncio
async def test_generate_figure_requires_permission() -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    tool = FigureGenerationTools(context=_ctx(), policy=HarnessPolicy())

    with pytest.raises(PermissionError, match="sandbox.generate_figure"):
        await tool.generate_figure(
            spec=_figure_spec(),
            source_code="print('figure')",
        )


@pytest.mark.asyncio
async def test_matplotlib_strategy_uses_run_python_and_registers_figure(monkeypatch) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools

    calls: list[dict[str, Any]] = []

    async def fake_run_python(self, **kwargs):
        calls.append(kwargs)
        return HarnessToolResult(
            preview_text="Python execution completed",
            structured_payload={
                "status": "completed",
                "sandbox_job_id": "job-1",
                "sandbox_environment_id": "env-1",
                "script_name": kwargs["script_name"],
                "generated_artifacts": [
                    {
                        "path": "/workspace/outputs/figures/accuracy_curve/figure.png",
                        "title": "Accuracy Curve",
                    }
                ],
                "execution_manifest": {
                    "schema": "wenjin.harness.run_python.execution_manifest.v1",
                    "tool": "sandbox.run_python",
                    "script_name": kwargs["script_name"],
                },
            },
        )

    monkeypatch.setattr(SandboxExecutionTools, "run_python", fake_run_python)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure", "sandbox.run_python"})),
    )

    result = await tool.generate_figure(
        spec=_figure_spec(),
        source_code="print('make figure')",
        dependency_hints=["matplotlib"],
    )

    assert calls == [
        {
            "script": "print('make figure')",
            "script_name": "accuracy_curve_figure.py",
            "dependency_hints": ["matplotlib"],
        }
    ]
    assert result.preview_text == "Generated figure via matplotlib: Accuracy Curve"
    assert result.structured_payload["schema"] == "wenjin.harness.figure_generation.v1"
    assert result.structured_payload["figure_spec"]["figure_id"] == "accuracy_curve"
    assert result.structured_payload["figure_manifest"]["primary_path"] == (
        "/workspace/outputs/figures/accuracy_curve/figure.png"
    )
    artifacts = result.structured_payload["generated_artifacts"]
    assert artifacts[0]["path"] == "/workspace/outputs/figures/accuracy_curve/figure.png"
    assert artifacts[0]["artifact_kind"] == "figure"
    assert result.structured_payload["run_python"]["execution_manifest"]["tool"] == "sandbox.run_python"


@pytest.mark.asyncio
async def test_code_strategy_requires_reviewable_generated_figure_artifact(monkeypatch) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools

    async def fake_run_python(self, **kwargs):
        return HarnessToolResult(
            preview_text="Python execution completed",
            structured_payload={
                "status": "completed",
                "sandbox_job_id": "job-1",
                "sandbox_environment_id": "env-1",
                "script_name": kwargs["script_name"],
                "generated_artifacts": [],
            },
        )

    monkeypatch.setattr(SandboxExecutionTools, "run_python", fake_run_python)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure", "sandbox.run_python"})),
    )

    with pytest.raises(RuntimeError, match="reviewable figure artifact"):
        await tool.generate_figure(
            spec=_figure_spec(),
            source_code="print('forgot to save figure')",
        )


@pytest.mark.asyncio
async def test_code_strategy_enriches_artifacts_with_run_job_identity(monkeypatch) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools

    async def fake_run_python(self, **kwargs):
        return HarnessToolResult(
            preview_text="Python execution completed",
            structured_payload={
                "status": "completed",
                "sandbox_job_id": "job-1",
                "sandbox_environment_id": "env-1",
                "script_name": kwargs["script_name"],
                "generated_artifacts": [
                    {
                        "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
                        "path": "/workspace/outputs/figures/accuracy_curve/figure.png",
                        "artifact_kind": "sandbox_output",
                        "review_surface": "sandbox_artifact",
                        "materialization_status": "candidate",
                    }
                ],
            },
        )

    monkeypatch.setattr(SandboxExecutionTools, "run_python", fake_run_python)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure", "sandbox.run_python"})),
    )

    result = await tool.generate_figure(
        spec=_figure_spec(),
        source_code="print('make figure')",
    )

    artifact = result.structured_payload["generated_artifacts"][0]
    assert artifact["artifact_kind"] == "figure"
    assert artifact["sandbox_job_id"] == "job-1"
    assert artifact["sandbox_environment_id"] == "env-1"


@pytest.mark.asyncio
async def test_code_strategy_requires_run_python_permission() -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(PermissionError, match="sandbox.run_python"):
        await tool.generate_figure(
            spec=_figure_spec(),
            source_code="print('make figure')",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "expected_hint"),
    [
        ("mermaid", "mermaid-cli"),
        ("graphviz", "graphviz"),
        ("tikz", "tectonic"),
    ],
)
async def test_structured_diagram_strategies_add_renderer_dependency_hints(
    monkeypatch,
    strategy: str,
    expected_hint: str,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools

    calls: list[dict[str, Any]] = []

    async def fake_run_python(self, **kwargs):
        calls.append(kwargs)
        return HarnessToolResult(
            preview_text="Python execution completed",
            structured_payload={
                "status": "completed",
                "sandbox_job_id": "job-1",
                "sandbox_environment_id": "env-1",
                "generated_artifacts": [
                    {
                        "path": "/workspace/outputs/figures/accuracy_curve/figure.png",
                    }
                ],
            },
        )

    monkeypatch.setattr(SandboxExecutionTools, "run_python", fake_run_python)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure", "sandbox.run_python"})),
    )

    await tool.generate_figure(
        spec=_figure_spec(
            figure_type="method_flow",
            strategy=strategy,
            dataset_paths=[],
        ),
        source_code="print('render diagram')",
        dependency_hints=["custom-render-helper"],
    )

    assert calls[0]["dependency_hints"] == ["custom-render-helper", expected_hint]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "figure_type"),
    [
        ("matplotlib", "experiment_plot"),
        ("seaborn", "experiment_plot"),
        ("plotly_static", "experiment_plot"),
        ("mermaid", "method_flow"),
        ("graphviz", "method_flow"),
        ("tikz", "method_flow"),
    ],
)
async def test_code_strategies_require_source_code(strategy: str, figure_type: str) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(ValueError, match="source_code"):
        await tool.generate_figure(
            spec=_figure_spec(strategy=strategy, figure_type=figure_type, dataset_paths=[]),
        )


@pytest.mark.asyncio
async def test_generate_figure_rejects_invalid_figure_spec_at_boundary() -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        await tool.generate_figure(
            spec=_figure_spec(output_targets=["/workspace/tmp/not-reviewable.png"]),
            source_code="print('figure')",
        )


def test_policy_derives_generate_figure_from_render_figures() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={
                "sandbox_policy": {
                    "mode": "required",
                    "allowed_operations": ["render_figures"],
                },
            },
            requested_tools=("sandbox.generate_figure",),
            skill={
                "allowed_tools": [],
                "skill_json": {
                    "sandbox_access": {"mode": "optional", "profiles": ["visualization"]},
                },
            },
        )
    )

    assert policy.allowed_tools == ("sandbox.generate_figure",)
    assert policy.permissions == frozenset({"sandbox.generate_figure"})


def test_policy_forbids_generate_figure_without_render_figures() -> None:
    policy = resolve_harness_policy(
        _ctx(
            capability_policy={
                "sandbox_policy": {
                    "mode": "required",
                    "allowed_operations": ["run_python"],
                },
            },
            requested_tools=("sandbox.generate_figure",),
            skill={
                "allowed_tools": [],
                "skill_json": {
                    "sandbox_access": {"mode": "optional", "profiles": ["visualization"]},
                },
            },
        )
    )

    assert "sandbox.generate_figure" not in policy.allowed_tools
    assert "sandbox.generate_figure" in policy.denied_tools
    assert "sandbox.generate_figure" not in policy.permissions


def test_langchain_adapter_registers_generate_figure_tool_definition() -> None:
    args_schema, handler = TOOL_DEFINITIONS["sandbox.generate_figure"]

    assert args_schema.model_fields["spec"].annotation == dict[str, Any]
    assert "source_code" in args_schema.model_fields
    assert "source_prompt" in args_schema.model_fields
    assert "dependency_hints" in args_schema.model_fields
    assert handler.__name__ == "_generate_figure"


@pytest.mark.asyncio
async def test_llm_image_strategy_never_requires_or_exposes_api_key(monkeypatch) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    async def fake_generate_llm_image(self, *, figure_spec, source_prompt, dependency_hints):
        return [
            {
                    "path": "/workspace/reports/figures/privacy_abstract/figure.png",
                    "title": figure_spec.title,
                    "artifact_kind": "figure",
                    "sandbox_job_id": "job-image-1",
                    "sandbox_environment_id": "env-image-1",
                    "review_surface": "sandbox_artifact",
                    "materialization_status": "candidate",
                    "provider_job_id": "image-job-1",
                    "api_key": "sk-secret-provider-key",
                    "token": "token-value",
                "access_token": "access-token-value",
                "password": "password-value",
                "credential": "credential-value",
                "credentials": "credentials-value",
                "private_key": "private-key-value",
                "private-key": "private-hyphen-value",
                "privateKey": "private-camel-value",
                "refresh_token": "refresh-token-value",
                "accessToken": "access-camel-value",
                "metadata": {
                    "authorization": "Bearer secret-token",
                    "raw_secret": "hidden",
                },
            }
        ]

    monkeypatch.setattr(FigureGenerationTools, "_generate_llm_image", fake_generate_llm_image)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    result = await tool.generate_figure(
        spec=_figure_spec(
            figure_id="privacy_abstract",
            title="Privacy Abstract",
            figure_type="graphical_abstract",
            strategy="llm_image",
            output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
        ),
        source_prompt="Draw a privacy-preserving collaboration diagram.",
    )

    payload_text = json.dumps(result.structured_payload, ensure_ascii=False, sort_keys=True).lower()
    assert result.structured_payload["generated_artifacts"][0]["artifact_kind"] == "figure"
    assert "api_key" not in payload_text
    assert "authorization" not in payload_text
    assert "secret" not in payload_text
    assert "token-value" not in payload_text
    assert "access-token-value" not in payload_text
    assert "password-value" not in payload_text
    assert "credential-value" not in payload_text
    assert "credentials-value" not in payload_text
    assert "private-key-value" not in payload_text
    assert "private-hyphen-value" not in payload_text
    assert "private-camel-value" not in payload_text
    assert "refresh-token-value" not in payload_text
    assert "access-camel-value" not in payload_text


@pytest.mark.asyncio
async def test_llm_image_strategy_redacts_secret_prompt_and_scalar_metadata(monkeypatch) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools

    raw_prompt = "Render this with sk-secret-prompt and Authorization Bearer prompt-token."

    async def fake_generate_llm_image(self, *, figure_spec, source_prompt, dependency_hints):
        return [
            {
                    "path": "/workspace/reports/figures/privacy_abstract/figure.png",
                    "title": figure_spec.title,
                    "artifact_kind": "figure",
                    "sandbox_job_id": "job-image-1",
                    "sandbox_environment_id": "env-image-1",
                    "review_surface": "sandbox_artifact",
                    "materialization_status": "candidate",
                    "provider_message": "used token sk-secret-provider and api-key provider-key",
                    "nested": ["Bearer nested-token", {"message": "authorization nested-secret"}],
                }
        ]

    monkeypatch.setattr(FigureGenerationTools, "_generate_llm_image", fake_generate_llm_image)
    tool = FigureGenerationTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    result = await tool.generate_figure(
        spec=_figure_spec(
            figure_id="privacy_abstract",
            title="Privacy Abstract",
            figure_type="graphical_abstract",
            strategy="llm_image",
            output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
        ),
        source_prompt=raw_prompt,
    )

    payload_text = json.dumps(result.structured_payload, ensure_ascii=False, sort_keys=True).lower()
    assert "sk-secret" not in payload_text
    assert "bearer prompt-token" not in payload_text
    assert "provider-key" not in payload_text
    assert "nested-token" not in payload_text
    assert "nested-secret" not in payload_text
    assert result.structured_payload["figure_manifest"]["source_prompt"] != raw_prompt


@pytest.mark.asyncio
async def test_default_llm_image_adapter_materializes_png_without_exposing_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.execution.types import ProviderResult
    from src.sandbox.providers.local import LocalSandbox

    async def fake_execute(self, *, content, work_dir, options, docker_client=None):
        _ = self, docker_client
        assert content == "Render with sk-secret-prompt"
        assert options["figure_id"] == "privacy_abstract"
        output_dir = Path(work_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "privacy_abstract.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return ProviderResult(
            success=True,
            output_files=["output/privacy_abstract.png"],
            metadata={
                "provider": "ai_image",
                "model_id": "image-model",
                "model": "hidden-model",
                "api_key": "sk-secret-provider",
            },
        )

    monkeypatch.setattr("src.execution.providers.ai_image.AIImageProvider.execute", fake_execute)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
    tool = FigureGenerationTools(
        context=_ctx(
            context_bundle={
                "_harness_sandbox": sandbox,
                "_harness_sandbox_job": {
                    "sandbox_job_id": "job-image-1",
                    "sandbox_environment_id": "env-image-1",
                },
            }
        ),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    result = await tool.generate_figure(
        spec=_figure_spec(
            figure_id="privacy_abstract",
            title="Privacy Abstract",
            figure_type="graphical_abstract",
            strategy="llm_image",
            output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
        ),
        source_prompt="Render with sk-secret-prompt",
    )

    target_path = workspace / "reports" / "figures" / "privacy_abstract" / "figure.png"
    assert target_path.read_bytes() == b"\x89PNG\r\n\x1a\nimage"
    artifact = result.structured_payload["generated_artifacts"][0]
    assert artifact["schema"] == "wenjin.sandbox.generated_artifact_candidate.v1"
    assert artifact["path"] == "/workspace/reports/figures/privacy_abstract/figure.png"
    assert artifact["artifact_kind"] == "figure"
    assert artifact["mime_type"] == "image/png"
    assert artifact["review_surface"] == "sandbox_artifact"
    assert artifact["materialization_status"] == "candidate"
    assert artifact["sandbox_job_id"] == "job-image-1"
    assert artifact["sandbox_environment_id"] == "env-image-1"
    assert artifact["provider"] == "ai_image"
    assert artifact["model_id"] == "image-model"
    assert result.structured_payload["figure_manifest"]["source_prompt"].startswith("redacted:sha256:")
    payload_text = json.dumps(result.structured_payload, ensure_ascii=False, sort_keys=True).lower()
    assert "sk-secret" not in payload_text
    assert "api_key" not in payload_text


@pytest.mark.asyncio
async def test_default_llm_image_adapter_redacts_provider_failure_message(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.execution.types import ProviderResult
    from src.sandbox.providers.local import LocalSandbox

    async def fake_execute(self, *, content, work_dir, options, docker_client=None):
        _ = self, content, work_dir, options, docker_client
        return ProviderResult(
            success=False,
            error_message=(
                "upstream said sk-secret-provider and Authorization Bearer token-value "
                "and api-key provider-key"
            ),
        )

    monkeypatch.setattr("src.execution.providers.ai_image.AIImageProvider.execute", fake_execute)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
    tool = FigureGenerationTools(
        context=_ctx(context_bundle=_sandbox_bundle(sandbox, job_id="job-failure-1", environment_id="env-image-1")),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await tool.generate_figure(
            spec=_figure_spec(
                figure_id="privacy_abstract",
                title="Privacy Abstract",
                figure_type="graphical_abstract",
                strategy="llm_image",
                output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
            ),
            source_prompt="Render a safe diagram.",
        )

    error_text = str(exc_info.value).lower()
    assert "upstream said" in error_text
    assert "sk-secret" not in error_text
    assert "authorization" not in error_text
    assert "bearer token" not in error_text
    assert "provider-key" not in error_text


@pytest.mark.asyncio
async def test_default_llm_image_adapter_rejects_symlinked_output_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.execution.types import ProviderResult
    from src.sandbox.providers.local import LocalSandbox

    async def fake_execute(self, *, content, work_dir, options, docker_client=None):
        _ = self, content, options, docker_client
        output_dir = Path(work_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "privacy_abstract.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return ProviderResult(
            success=True,
            output_files=["output/privacy_abstract.png"],
            metadata={"provider": "ai_image"},
        )

    monkeypatch.setattr("src.execution.providers.ai_image.AIImageProvider.execute", fake_execute)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    protected = workspace / ".env"
    protected.write_text("OPENAI_API_KEY=keep-me\n", encoding="utf-8")
    target = workspace / "reports" / "figures" / "privacy_abstract" / "figure.png"
    target.parent.mkdir(parents=True)
    target.symlink_to(protected)
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
    tool = FigureGenerationTools(
        context=_ctx(context_bundle=_sandbox_bundle(sandbox, job_id="job-symlink-1", environment_id="env-image-1")),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(RuntimeError, match="symlink"):
        await tool.generate_figure(
            spec=_figure_spec(
                figure_id="privacy_abstract",
                title="Privacy Abstract",
                figure_type="graphical_abstract",
                strategy="llm_image",
                output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
            ),
            source_prompt="Render a safe diagram.",
        )

    assert target.is_symlink()
    assert protected.read_text(encoding="utf-8") == "OPENAI_API_KEY=keep-me\n"


@pytest.mark.asyncio
async def test_default_llm_image_adapter_requires_reverse_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.execution.types import ProviderResult

    class ResolveOnlySandbox:
        def __init__(self, workspace_root: Path) -> None:
            self.workspace_root = workspace_root

        def _resolve_path(self, path: str) -> str:
            if path == "/workspace":
                return str(self.workspace_root)
            if path.startswith("/workspace/"):
                return str(self.workspace_root / path.removeprefix("/workspace/"))
            raise ValueError(path)

    async def fake_execute(self, *, content, work_dir, options, docker_client=None):
        _ = self, content, options, docker_client
        output_dir = Path(work_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "privacy_abstract.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return ProviderResult(
            success=True,
            output_files=["output/privacy_abstract.png"],
            metadata={"provider": "ai_image"},
        )

    monkeypatch.setattr("src.execution.providers.ai_image.AIImageProvider.execute", fake_execute)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = FigureGenerationTools(
        context=_ctx(
            context_bundle=_sandbox_bundle(
                ResolveOnlySandbox(workspace),
                job_id="job-reverse-1",
                environment_id="env-image-1",
            )
        ),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(RuntimeError, match="reverse"):
        await tool.generate_figure(
            spec=_figure_spec(
                figure_id="privacy_abstract",
                title="Privacy Abstract",
                figure_type="graphical_abstract",
                strategy="llm_image",
                output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
            ),
            source_prompt="Render a safe diagram.",
        )

    assert not (workspace / "reports" / "figures" / "privacy_abstract" / "figure.png").exists()


@pytest.mark.asyncio
async def test_default_llm_image_adapter_rejects_parent_symlink_outside_artifact_roots(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.agents.harness.figure_generation_tools import FigureGenerationTools
    from src.execution.types import ProviderResult
    from src.sandbox.providers.local import LocalSandbox

    async def fake_execute(self, *, content, work_dir, options, docker_client=None):
        _ = self, content, options, docker_client
        output_dir = Path(work_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "privacy_abstract.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return ProviderResult(
            success=True,
            output_files=["output/privacy_abstract.png"],
            metadata={"provider": "ai_image"},
        )

    monkeypatch.setattr("src.execution.providers.ai_image.AIImageProvider.execute", fake_execute)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main").mkdir()
    (workspace / "reports").mkdir()
    (workspace / "reports" / "figures").symlink_to(workspace / "main")
    sandbox = LocalSandbox(id="workspace-ws-1", path_mappings={"/workspace": str(workspace)})
    tool = FigureGenerationTools(
        context=_ctx(context_bundle=_sandbox_bundle(sandbox, job_id="job-parent-symlink-1", environment_id="env-image-1")),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure"})),
    )

    with pytest.raises(RuntimeError, match="reviewable"):
        await tool.generate_figure(
            spec=_figure_spec(
                figure_id="privacy_abstract",
                title="Privacy Abstract",
                figure_type="graphical_abstract",
                strategy="llm_image",
                output_targets=["/workspace/reports/figures/privacy_abstract/figure.png"],
            ),
            source_prompt="Render a safe diagram.",
        )

    assert not (workspace / "main" / "privacy_abstract" / "figure.png").exists()
