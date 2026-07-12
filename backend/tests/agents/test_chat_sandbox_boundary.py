from pathlib import Path


def test_workspace_agent_does_not_import_sandbox_runtime() -> None:
    source = Path("src/agents/workspace_agent/agent.py").read_text(encoding="utf-8")

    assert "src.sandbox" not in source
    assert "DockerSandboxProvider" not in source
    assert "SandboxMiddleware" not in source
    assert "SandboxAuditMiddleware" not in source
    assert "AgentSandboxSmokeMiddleware" not in source
