"""Strict event-boundary parser for Responses native-search SSE streams."""

from __future__ import annotations

import json
from typing import Any

from src.services.search.model_native import (
    NativeSearchReceiptError,
    parse_native_search_receipt,
)


class ResponsesSearchSSEProtocolError(ValueError):
    """The stream ended or emitted a completion without verified search receipts."""


class ResponsesSearchSSEParser:
    """Accumulate SSE fields and stop exactly at a verified response.completed event."""

    def __init__(self) -> None:
        self._event_name: str | None = None
        self._data_lines: list[str] = []
        self._completed = False
        self._completed_output_items: dict[int, dict[str, Any]] = {}

    def feed_line(self, line: str) -> dict[str, Any] | None:
        if self._completed:
            raise ResponsesSearchSSEProtocolError(
                "search SSE parser received data after its completion boundary"
            )
        normalized = line.rstrip("\r\n")
        if not normalized:
            return self._dispatch()
        if normalized.startswith(":"):
            return None
        field, separator, value = normalized.partition(":")
        if not separator:
            return None
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            self._event_name = value.strip()
        elif field == "data":
            self._data_lines.append(value)
            if self._event_name == "response.completed":
                try:
                    json.loads("\n".join(self._data_lines))
                except json.JSONDecodeError:
                    return None
                return self._dispatch()
        return None

    def finish(self) -> dict[str, Any]:
        pending = self._dispatch()
        if pending is not None:
            return pending
        raise ResponsesSearchSSEProtocolError(
            "search SSE stream ended before a verified response.completed event"
        )

    def _dispatch(self) -> dict[str, Any] | None:
        event_name = self._event_name
        raw_data = "\n".join(self._data_lines).strip()
        self._event_name = None
        self._data_lines.clear()
        if not raw_data:
            return None
        if raw_data == "[DONE]":
            raise ResponsesSearchSSEProtocolError(
                "search SSE stream sent DONE before a verified completion event"
            )
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ResponsesSearchSSEProtocolError(
                "search SSE event data is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ResponsesSearchSSEProtocolError(
                "search SSE event data must be an object"
            )
        resolved_event = str(event_name or payload.get("type") or "").strip()
        if resolved_event in {"response.failed", "response.error", "error"}:
            raise ResponsesSearchSSEProtocolError(
                f"search SSE provider emitted terminal event: {resolved_event}"
            )
        if resolved_event != "response.completed":
            self._record_incremental_receipt(resolved_event, payload)
            return None
        response = payload.get("response")
        if not isinstance(response, dict):
            response = payload if payload.get("status") == "completed" else None
        if response is None:
            raise ResponsesSearchSSEProtocolError(
                "response.completed event has no completed response payload"
            )
        completed_response = self._merge_completed_output(response)
        try:
            parse_native_search_receipt(completed_response)
        except NativeSearchReceiptError as exc:
            raise ResponsesSearchSSEProtocolError(
                "response.completed did not contain complete search receipts"
            ) from exc
        self._completed = True
        return completed_response

    def _record_incremental_receipt(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        if event_name != "response.output_item.done":
            return
        output_index = payload.get("output_index")
        item = payload.get("item")
        if not isinstance(output_index, int) or output_index < 0:
            return
        if not isinstance(item, dict) or item.get("status") != "completed":
            return
        self._completed_output_items[output_index] = dict(item)

    def _merge_completed_output(
        self,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._completed_output_items:
            return response
        final_output = response.get("output")
        output_by_index = {
            index: item
            for index, item in enumerate(final_output)
            if isinstance(item, dict)
        } if isinstance(final_output, list) else {}
        output_by_index.update(self._completed_output_items)
        merged = dict(response)
        merged["output"] = [
            output_by_index[index]
            for index in sorted(output_by_index)
        ]
        return merged


__all__ = [
    "ResponsesSearchSSEParser",
    "ResponsesSearchSSEProtocolError",
]
