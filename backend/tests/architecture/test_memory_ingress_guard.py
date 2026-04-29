"""Architecture guard: memory writes must enter through MemoryCaptureService."""

from __future__ import annotations

from pathlib import Path

_SRC_ROOT = Path(__file__).parents[2] / "src"
_ALLOWED_EXTRACT_CALLERS = {
    "services/memory_capture_service.py",
    "services/user_memory_service.py",
}


def test_memory_extraction_calls_are_owned_by_capture_service() -> None:
    """Call sites should not bypass the canonical memory capture ingress."""
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        rel = py_file.relative_to(_SRC_ROOT).as_posix()
        source = py_file.read_text()
        if "extract_and_persist_knowledge(" not in source:
            continue
        if rel not in _ALLOWED_EXTRACT_CALLERS:
            violations.append(rel)

    assert not violations, (
        "Long-term memory writes must go through src.services.memory_capture_service:\n"
        + "\n".join(violations)
    )


def test_feature_memory_capture_is_awaited_not_fire_and_forget() -> None:
    """Feature memory capture should not depend on process-local create_task."""
    source = (_SRC_ROOT / "task/handlers/workspace_feature_handler.py").read_text()
    assert "create_task" not in source
    assert "get_memory_capture_service" in source


def test_compat_memory_enqueue_delegates_to_capture_service() -> None:
    """Compatibility helper may remain, but it must not own persistence."""
    source = (_SRC_ROOT / "agents/memory/capture.py").read_text()
    assert "MemoryCaptureService" in source
    assert "extract_and_persist_knowledge" not in source
