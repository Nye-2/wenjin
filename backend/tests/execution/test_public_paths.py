from src.execution.public_paths import (
    get_default_sandbox_dir,
    sandbox_path_to_public_url,
)
from src.execution.path_utils import normalize_thread_id


def test_sandbox_path_to_public_url_with_thread_id():
    url = sandbox_path_to_public_url(
        "/mnt/user-data/execution/latex_compile/run-1/main.pdf",
        thread_id="thread-123",
    )
    assert url == "/uploads/sandboxes/thread-123/execution/latex_compile/run-1/main.pdf"


def test_sandbox_path_to_public_url_defaults_thread():
    url = sandbox_path_to_public_url(
        "/mnt/user-data/execution/mermaid_diagram/run-1/chart.svg",
        thread_id=None,
    )
    assert url == "/uploads/sandboxes/default/execution/mermaid_diagram/run-1/chart.svg"


def test_sandbox_path_to_public_url_rejects_unknown_path():
    assert sandbox_path_to_public_url("/tmp/random/output.pdf", thread_id="x") is None


def test_sandbox_path_to_public_url_sanitizes_thread_id():
    thread_id = "../../unsafe//thread"
    url = sandbox_path_to_public_url(
        "/mnt/user-data/execution/latex_compile/run-1/main.pdf",
        thread_id=thread_id,
    )
    assert url == (
        f"/uploads/sandboxes/{normalize_thread_id(thread_id)}"
        "/execution/latex_compile/run-1/main.pdf"
    )


def test_get_default_sandbox_dir_returns_string():
    value = get_default_sandbox_dir()
    assert isinstance(value, str)
    assert value.endswith("uploads/sandboxes") or value.endswith("/app/uploads/sandboxes")
