from __future__ import annotations

import os
import struct
import zlib
from datetime import UTC, datetime, timedelta

import pytest

from src.review_commit_runtime.preview_store import MissionPreviewStore


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _png(*, text_metadata: bool = False, pixel: bytes = b"\x00\x00\x00\x00") -> bytes:
    if len(pixel) != 4:
        raise ValueError("test PNG pixels must be one RGBA sample")
    content = b"\x89PNG\r\n\x1a\n"
    content += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    if text_metadata:
        content += _png_chunk(b"tEXt", b"author\x00private")
    content += _png_chunk(b"IDAT", zlib.compress(b"\x00" + pixel))
    content += _png_chunk(b"IEND", b"")
    return content


@pytest.mark.asyncio
async def test_store_sanitizes_raster_metadata_and_verifies_hash(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(text_metadata=True),
        mime_type="image/png",
        filename="figure.png",
        metadata={"figure_id": "figure-1"},
    )

    preview = await store.read(descriptor.ref, workspace_id="workspace-1")

    assert b"private" not in preview.content
    assert preview.descriptor.content_hash == descriptor.content_hash
    assert preview.descriptor.metadata == {"figure_id": "figure-1"}


@pytest.mark.asyncio
async def test_store_fails_closed_across_workspaces_and_on_tampering(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(),
        mime_type="image/png",
        filename="figure.png",
    )

    with pytest.raises(LookupError, match="review_preview_not_found"):
        await store.read(descriptor.ref, workspace_id="workspace-2")

    payload = next((tmp_path / "objects" / "workspace-1").glob("**/payload"))
    payload.write_bytes(payload.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="review_preview_integrity_failed"):
        await store.read(descriptor.ref, workspace_id="workspace-1")


@pytest.mark.asyncio
async def test_store_sanitizes_svg_and_cleans_expired_refs(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=(
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
            b'<script>alert(1)</script><a href="https://example.com"><text>safe</text></a></svg>'
        ),
        mime_type="image/svg+xml",
        filename="figure.svg",
        expires_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    preview = await store.read(descriptor.ref, workspace_id="workspace-1")
    assert b"script" not in preview.content
    assert b"onload" not in preview.content
    assert b"https://example.com" not in preview.content

    deleted = await store.cleanup_expired(now=datetime.now(UTC) + timedelta(minutes=1))
    assert deleted == [descriptor.ref]
    with pytest.raises(LookupError):
        await store.read(descriptor.ref, workspace_id="workspace-1")


@pytest.mark.asyncio
async def test_store_rejects_svg_doctype_before_xml_parsing(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)

    with pytest.raises(ValueError, match="preview_svg_unsafe"):
        await store.put(
            workspace_id="workspace-1",
            content=(
                b'<!DOCTYPE svg [<!ENTITY payload "expanded">]>'
                b'<svg xmlns="http://www.w3.org/2000/svg"><text>&payload;</text></svg>'
            ),
            mime_type="image/svg+xml",
            filename="unsafe.svg",
        )


@pytest.mark.asyncio
async def test_cleanup_bounds_ref_and_object_deletions(tmp_path) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    expires_at = datetime.now(UTC) + timedelta(seconds=1)
    descriptors = [
        await store.put(
            workspace_id="workspace-1",
            content=_png(pixel=bytes((index, 0, 0, 0))),
            mime_type="image/png",
            filename=f"figure-{index}.png",
            expires_at=expires_at,
        )
        for index in (1, 2)
    ]
    cutoff = expires_at + timedelta(minutes=1)

    first = await store.cleanup_expired(now=cutoff, limit=1)

    assert len(first) == 1
    assert len(list((tmp_path / "refs").glob("*/*.json"))) == 1
    assert len(list((tmp_path / "objects").glob("*/*/*/payload"))) == 1

    second = await store.cleanup_expired(now=cutoff, limit=1)

    assert sorted(first + second) == sorted(descriptor.ref for descriptor in descriptors)
    assert not list((tmp_path / "refs").glob("*/*.json"))
    assert not list((tmp_path / "objects").glob("*/*/*/payload"))


@pytest.mark.asyncio
async def test_cleanup_does_not_hide_object_io_failures(tmp_path, monkeypatch) -> None:
    store = MissionPreviewStore(tmp_path, default_ttl_seconds=3600, max_bytes=1024 * 1024)
    descriptor = await store.put(
        workspace_id="workspace-1",
        content=_png(),
        mime_type="image/png",
        filename="figure.png",
    )
    next((tmp_path / "refs").glob("*/*.json")).unlink()
    object_path = next((tmp_path / "objects").glob("*/*/*/payload"))
    os.utime(object_path, (0, 0))
    original_stat = type(object_path).stat

    def fail_object_stat(path, *args, **kwargs):
        if path == object_path:
            raise PermissionError("preview object unreadable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(type(object_path), "stat", fail_object_stat)

    with pytest.raises(PermissionError, match="preview object unreadable"):
        await store.cleanup_expired(now=descriptor.expires_at + timedelta(seconds=1))
