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
            return None
        response = payload.get("response")
        if not isinstance(response, dict):
            response = payload if payload.get("status") == "completed" else None
        if response is None:
            raise ResponsesSearchSSEProtocolError(
                "response.completed event has no completed response payload"
            )
        try:
            parse_native_search_receipt(response)
        except NativeSearchReceiptError as exc:
            raise ResponsesSearchSSEProtocolError(
                "response.completed did not contain complete search receipts"
            ) from exc
        self._completed = True
        return response


__all__ = [
    "ResponsesSearchSSEParser",
    "ResponsesSearchSSEProtocolError",
]
