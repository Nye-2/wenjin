"""Tests for runtime serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from src.runtime.serialization import (
    dumps_json,
    encode_sse_data,
    serialize,
    serialize_lc_object,
    serialize_messages_tuple,
    serialize_public_values,
)


class _Payload(BaseModel):
    message: str
    count: int


def test_serialize_lc_object_handles_pydantic_and_nested_values():
    payload = {
        "model": _Payload(message="ok", count=2),
        "items": [1, {"x": _Payload(message="nested", count=1)}],
    }

    serialized = serialize_lc_object(payload)
    assert serialized == {
        "model": {"message": "ok", "count": 2},
        "items": [1, {"x": {"message": "nested", "count": 1}}],
    }


def test_serialize_public_values_strips_internal_runtime_keys():
    values = {
        "__runtime_task_id": "internal",
        "__interrupt__": {"x": 1},
        "messages": ["hello"],
        "count": 3,
    }
    assert serialize_public_values(values) == {"messages": ["hello"], "count": 3}


def test_serialize_messages_tuple_formats_chunk_and_metadata():
    chunk = _Payload(message="hello", count=1)
    metadata = {"node": "assistant"}
    result = serialize_messages_tuple((chunk, metadata))
    assert result == [{"message": "hello", "count": 1}, {"node": "assistant"}]


def test_serialize_values_mode_applies_channel_filter():
    result = serialize(
        {
            "__runtime_x": 1,
            "data": {"ts": datetime(2026, 4, 13, tzinfo=UTC)},
        },
        mode="values",
    )
    assert "__runtime_x" not in result
    assert "2026-04-13" in str(result["data"]["ts"])


def test_dumps_json_and_encode_sse_data_return_valid_frames():
    payload = {"time": datetime(2026, 4, 13, tzinfo=UTC), "ok": True}
    encoded = dumps_json(payload)
    assert '"ok": true' in encoded
    assert "2026-04-13" in encoded

    sse = encode_sse_data(payload)
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")


def test_encode_sse_data_respects_ensure_ascii_flag():
    sse = encode_sse_data({"text": "中文"}, ensure_ascii=False)
    assert '"text": "中文"' in sse
