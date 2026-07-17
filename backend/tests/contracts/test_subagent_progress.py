import pytest

from src.contracts.subagent_progress import (
    subagent_progress_sha256,
    validate_subagent_progress_identity,
)


def _terminal_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "job_id": "job-1",
        "lifecycle_phase": "terminal",
        "result": {"summary": "done"},
    }
    progress_hash = subagent_progress_sha256(
        summary="done",
        payload_json=payload,
    )
    payload.update(
        {
            "progress_id": "subagent-terminal:job-1",
            "progress_sha256": progress_hash,
        }
    )
    return payload


def test_terminal_progress_identity_is_content_hash_bound() -> None:
    payload = _terminal_payload()

    progress_id, progress_hash = validate_subagent_progress_identity(
        summary="done",
        payload_json=payload,
    )

    assert progress_id == "subagent-terminal:job-1"
    assert progress_hash == payload["progress_sha256"]


def test_terminal_progress_identity_rejects_content_tampering() -> None:
    payload = _terminal_payload()
    payload["result"] = {"summary": "changed"}

    with pytest.raises(ValueError, match="identity or hash"):
        validate_subagent_progress_identity(
            summary="done",
            payload_json=payload,
        )
