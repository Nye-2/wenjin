"""Documentation guards for the current Compute-centered architecture."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_ROOTS = [
    REPO_ROOT / "docs" / "architecture",
    REPO_ROOT / "docs" / "product",
    REPO_ROOT / "backend" / "docs",
]
DOC_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "backend" / "README.md",
    REPO_ROOT / "frontend" / "README.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "documentation-map.md",
]

FORBIDDEN_CURRENT_DOC_PHRASES = (
    "run_workspace_feature",
    "FeaturePanelHost",
    "FeatureWorkbenchShell",
    "workspace-result",
    "lead-agent + tool",
    "direct feature bridge",
    "Panel Adapter",
    "Feature Panel",
    "panel 主消费",
    "右侧 Feature 面板",
)

REQUIRED_CURRENT_DOC_PHRASES = (
    "ChatTurnRouter",
    "FeatureCommandHandler",
    "FeatureIngressService",
    "Compute",
    "WenjinPrism",
)


def _current_docs() -> list[Path]:
    docs: list[Path] = []
    for root in DOC_ROOTS:
        docs.extend(path for path in root.rglob("*.md") if path.is_file())
    docs.extend(path for path in DOC_FILES if path.is_file())
    return sorted(docs)


def test_current_docs_do_not_reintroduce_legacy_feature_tool_loop() -> None:
    """Current docs must not describe the removed chat-feature tool loop."""
    violations: list[str] = []
    for path in _current_docs():
        body = path.read_text(encoding="utf-8")
        for phrase in FORBIDDEN_CURRENT_DOC_PHRASES:
            if phrase in body:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {phrase}")
    assert not violations, (
        "Current architecture/product docs contain legacy feature-loop wording:\n"
        + "\n".join(violations)
    )


def test_current_docs_name_compute_centered_fact_sources() -> None:
    """Docs must keep the current chat/feature/compute/Prism sources explicit."""
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in _current_docs()
    )
    missing = [
        phrase for phrase in REQUIRED_CURRENT_DOC_PHRASES
        if phrase not in combined
    ]
    assert not missing, (
        "Current docs should name the Compute-centered fact sources; missing: "
        + ", ".join(missing)
    )
