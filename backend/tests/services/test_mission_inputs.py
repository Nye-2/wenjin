from __future__ import annotations

import hashlib
from dataclasses import asdict

import fitz
import pytest

from src.application.results import ThreadTurnAttachment
from src.services.mission_inputs import MissionInputService, MissionInputStore


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_pdf_attachment_is_sealed_and_rehydrated_from_message_history(tmp_path) -> None:
    thread_root = tmp_path / "threads"
    input_root = tmp_path / "mission-inputs"
    upload_dir = thread_root / "thread-1" / "user-data" / "uploads"
    upload_dir.mkdir(parents=True)
    content = _pdf_bytes("Question 1: optimize shuttle departures under a capacity constraint.")
    (upload_dir / "problem.pdf").write_bytes(content)
    service = MissionInputService(
        store=MissionInputStore(input_root),
        thread_data_root=thread_root,
    )

    prepared = service.prepare(
        workspace_id="workspace-1",
        thread_id="thread-1",
        attachments=(
            ThreadTurnAttachment(
                name="problem.pdf",
                path="/mnt/user-data/uploads/problem.pdf",
                kind="transient",
                content_type="application/pdf",
                size_bytes=len(content),
                metadata={"preprocess": {"status": "disabled"}},
            ),
        ),
    )

    assert len(prepared.manifests) == 1
    manifest = prepared.manifests[0]
    assert manifest.input_ref == manifest.content_hash.replace("sha256:", "mission-input:")
    assert manifest.source_content_hash == f"sha256:{hashlib.sha256(content).hexdigest()}"
    assert prepared.contexts[0].status == "ready"
    hydrated = service.collect_from_messages(
        [
            {
                "role": "user",
                "content": "先读赛题",
                "metadata": {
                    "mission_inputs": [manifest.model_dump(mode="json")],
                    "attachment_contexts": [
                        prepared.contexts[0].model_dump(
                            mode="json",
                            exclude={"excerpt", "current_message"},
                            exclude_none=True,
                        )
                    ],
                },
            },
            {"role": "user", "content": "确认后继续", "metadata": {}},
        ],
        workspace_id="workspace-1",
        thread_id="thread-1",
    )

    assert hydrated.manifests == (manifest,)
    assert "Question 1" in str(hydrated.contexts[0].excerpt)
    assert hydrated.contexts[0].current_message is False


def test_mission_input_store_detects_object_tampering(tmp_path) -> None:
    store = MissionInputStore(tmp_path)
    manifest = store.put_text(
        workspace_id="workspace-1",
        thread_id="thread-1",
        filename="problem.txt",
        mime_type="text/plain",
        extractor="plain_text",
        text="capacity = 40",
        source_content_hash=f"sha256:{'b' * 64}",
        source_size_bytes=13,
    )
    digest = manifest.input_ref.removeprefix("mission-input:")
    target = tmp_path / "thread-1" / "mission-inputs" / digest[:2] / digest / "content.txt"
    target.chmod(0o600)
    target.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity"):
        store.read_text(manifest, workspace_id="workspace-1")


def test_noncanonical_thread_path_is_rejected_without_legacy_resolution(tmp_path) -> None:
    service = MissionInputService(
        store=MissionInputStore(tmp_path / "inputs"),
        thread_data_root=tmp_path / "threads",
    )
    prepared = service.prepare(
        workspace_id="workspace-1",
        thread_id="thread-1",
        attachments=(
            ThreadTurnAttachment(
                name="problem.txt",
                path="uploads/problem.txt",
                content_type="text/plain",
            ),
        ),
    )

    assert prepared.manifests == ()
    assert prepared.contexts[0].status == "unreadable"


def test_malformed_pdf_is_reported_as_unreadable(tmp_path) -> None:
    thread_root = tmp_path / "threads"
    upload_dir = thread_root / "thread-1" / "user-data" / "uploads"
    upload_dir.mkdir(parents=True)
    content = b"not-a-pdf"
    (upload_dir / "problem.pdf").write_bytes(content)
    service = MissionInputService(
        store=MissionInputStore(tmp_path / "inputs"),
        thread_data_root=thread_root,
    )

    prepared = service.prepare(
        workspace_id="workspace-1",
        thread_id="thread-1",
        attachments=(
            ThreadTurnAttachment(
                name="problem.pdf",
                path="/mnt/user-data/uploads/problem.pdf",
                content_type="application/pdf",
                size_bytes=len(content),
            ),
        ),
    )

    assert prepared.manifests == ()
    assert prepared.contexts[0].status == "unreadable"


def test_pending_historical_attachment_is_promoted_after_preprocess_completes(tmp_path) -> None:
    thread_root = tmp_path / "threads"
    parsed_dir = thread_root / "thread-1" / "user-data" / "uploads" / "_preprocessed" / "problem"
    parsed_dir.mkdir(parents=True)
    source = b"scanned-pdf-source"
    upload = parsed_dir.parents[1] / "problem.pdf"
    upload.write_bytes(source)
    parsed = parsed_dir / "page-1.md"
    parsed.write_text("Question 1: build and validate the optimization model.", encoding="utf-8")
    service = MissionInputService(
        store=MissionInputStore(tmp_path / "inputs"),
        thread_data_root=thread_root,
    )
    attachment = ThreadTurnAttachment(
        name="problem.pdf",
        path="/mnt/user-data/uploads/problem.pdf",
        content_type="application/pdf",
        size_bytes=len(source),
        metadata={
            "preprocess": {
                "status": "succeeded",
                "markdown_paths": ["/mnt/user-data/uploads/_preprocessed/problem/page-1.md"],
            }
        },
    )

    hydrated = service.collect_from_messages(
        [
            {
                "role": "user",
                "content": "先读取题目",
                "metadata": {
                    "attachments": [asdict(attachment)],
                    "attachment_contexts": [
                        {
                            "name": "problem.pdf",
                            "content_type": "application/pdf",
                            "size_bytes": len(source),
                            "status": "pending",
                            "detail": "文件正在解析，完成后即可继续。",
                        }
                    ],
                },
            }
        ],
        workspace_id="workspace-1",
        thread_id="thread-1",
    )

    assert len(hydrated.manifests) == 1
    assert hydrated.contexts[0].status == "ready"
    assert "Question 1" in str(hydrated.contexts[0].excerpt)
