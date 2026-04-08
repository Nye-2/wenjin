"""Short-lived signed URL support for protected asset routes."""

from __future__ import annotations

import hmac
import time
from functools import lru_cache
from hashlib import sha256
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from src.config import get_jwt_settings

_DEFAULT_TTL_SECONDS = 600
_WORKSPACE_ROUTE_PREFIX = "/api/workspaces/"
_THREAD_ROUTE_PREFIX = "/api/threads/"


def _normalize_secret() -> bytes:
    return get_jwt_settings().secret_key.encode("utf-8")


def _normalized_query_without_signature(url: str) -> str:
    parsed = urlparse(url)
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in {"sig"}
    ]
    if not filtered:
        return parsed.path
    return f"{parsed.path}?{urlencode(filtered, doseq=True)}"


class AssetUrlSigner:
    """Generate and verify short-lived signatures for asset routes."""

    def __init__(self, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._secret = _normalize_secret()

    def _sign_value(self, value: str) -> str:
        return hmac.new(self._secret, value.encode("utf-8"), sha256).hexdigest()

    def sign_url(self, url: str, *, ttl_seconds: int | None = None) -> str:
        ttl = ttl_seconds or self._ttl_seconds
        expires_at = int(time.time()) + max(int(ttl), 1)
        parsed = urlparse(url)
        query_items = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "sig"
        ]
        query_items = [(key, value) for key, value in query_items if key != "exp"]
        query_items.append(("exp", str(expires_at)))
        unsigned = urlunparse(
            parsed._replace(query=urlencode(query_items, doseq=True))
        )
        signature = self._sign_value(_normalized_query_without_signature(unsigned))
        query_items.append(("sig", signature))
        return urlunparse(
            parsed._replace(query=urlencode(query_items, doseq=True))
        )

    def verify_url(self, url: str) -> bool:
        parsed = urlparse(url)
        query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
        sig = str(query_items.get("sig") or "").strip()
        exp = str(query_items.get("exp") or "").strip()
        if not sig or not exp:
            return False

        try:
            expires_at = int(exp)
        except ValueError:
            return False
        if expires_at < int(time.time()):
            return False

        expected = self._sign_value(_normalized_query_without_signature(url))
        return hmac.compare_digest(expected, sig)

    def sign_workspace_file_url(
        self,
        workspace_id: str,
        relative_path: str,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        route_path = quote(str(relative_path or "").lstrip("/"), safe="/")
        return self.sign_url(
            f"/api/workspaces/{workspace_id}/files/{route_path}",
            ttl_seconds=ttl_seconds,
        )

    def sign_thread_artifact_url(
        self,
        thread_id: str,
        path: str,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        route_path = quote(str(path or "").lstrip("/"), safe="/")
        return self.sign_url(
            f"/api/threads/{thread_id}/artifacts/{route_path}",
            ttl_seconds=ttl_seconds,
        )

    def sign_thread_artifact_download_url(
        self,
        thread_id: str,
        path: str,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        route_path = quote(str(path or "").lstrip("/"), safe="/")
        return self.sign_url(
            f"/api/threads/{thread_id}/artifacts/{route_path}?download=true",
            ttl_seconds=ttl_seconds,
        )

    def recognizes_asset_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.path.startswith(_WORKSPACE_ROUTE_PREFIX) or parsed.path.startswith(
            _THREAD_ROUTE_PREFIX
        )


@lru_cache
def get_asset_url_signer() -> AssetUrlSigner:
    """Return singleton signer."""
    return AssetUrlSigner()
