"""DataService client errors."""

from __future__ import annotations

import httpx


class DataServiceClientError(RuntimeError):
    """Raised when DataService returns an error or malformed payload."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: object | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload

    @classmethod
    def from_response(cls, response: httpx.Response) -> DataServiceClientError:
        try:
            payload: object = response.json()
        except ValueError:
            payload = response.text
        message = f"DataService request failed with HTTP {response.status_code}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                message = str(error["message"])
        return cls(message, status_code=response.status_code, payload=payload)
