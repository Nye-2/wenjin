"""Security helpers for admin-managed model catalog entries."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ModelCatalogSecurityError(ValueError):
    """Raised when model catalog secret or URL validation fails."""


class ModelApiKeyCipher:
    """Encrypt and decrypt model provider API keys with AES-GCM."""

    _VERSION_PREFIX = "v1:"
    _NONCE_BYTES = 12

    def __init__(self, key: str | bytes) -> None:
        self._aesgcm = AESGCM(_normalize_master_key(key))

    def encrypt(self, plaintext: str, *, aad: str) -> str:
        if not plaintext:
            raise ModelCatalogSecurityError("Model API key cannot be empty")
        nonce = os.urandom(self._NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{self._VERSION_PREFIX}{payload}"

    def decrypt(self, token: str, *, aad: str) -> str:
        if not token.startswith(self._VERSION_PREFIX):
            raise ModelCatalogSecurityError("Unsupported model API key ciphertext version")
        try:
            payload = base64.urlsafe_b64decode(token.removeprefix(self._VERSION_PREFIX).encode("ascii"))
            nonce = payload[: self._NONCE_BYTES]
            ciphertext = payload[self._NONCE_BYTES :]
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad.encode("utf-8"))
        except Exception as exc:
            raise ModelCatalogSecurityError("Unable to decrypt model API key") from exc
        return plaintext.decode("utf-8")


def encrypt_api_key(api_key: str, *, model_id: str, master_key: str | bytes) -> str:
    """Encrypt a provider API key and bind it to a model catalog identity."""

    return ModelApiKeyCipher(master_key).encrypt(api_key, aad=_model_aad(model_id))


def decrypt_api_key(ciphertext: str, *, model_id: str, master_key: str | bytes) -> str:
    """Decrypt a provider API key for the expected model catalog identity."""

    return ModelApiKeyCipher(master_key).decrypt(ciphertext, aad=_model_aad(model_id))


def api_key_last4(api_key: str) -> str:
    """Return the last four characters stored for admin-safe display."""

    return api_key.strip()[-4:]


def redact_api_key(api_key: str | None) -> str | None:
    """Return a stable display-safe API key mask."""

    if api_key is None:
        return None
    value = api_key.strip()
    last4 = api_key_last4(value)
    return f"sk-****{last4}" if last4 else "sk-****"


def api_key_fingerprint(api_key: str, *, master_key: str | bytes | None = None) -> str:
    """Create a non-reversible fingerprint for duplicate detection and audit."""

    if master_key is not None:
        return hmac.new(_normalize_master_key(master_key), api_key.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def load_model_secret_key(*, env: Mapping[str, str] | None = None) -> bytes:
    """Load the model-catalog encryption key from env or a mounted secret file."""

    source = os.environ if env is None else env
    key_file = str(source.get("MODEL_SECRET_KEY_FILE") or "").strip()
    if key_file:
        try:
            return _normalize_master_key(Path(key_file).read_text(encoding="utf-8").strip())
        except OSError as exc:
            raise ModelCatalogSecurityError("Unable to read MODEL_SECRET_KEY_FILE") from exc

    inline_key = str(source.get("MODEL_SECRET_KEY") or "").strip()
    if not inline_key:
        raise ModelCatalogSecurityError("MODEL_SECRET_KEY or MODEL_SECRET_KEY_FILE is required")
    return _normalize_master_key(inline_key)


def validate_model_base_url(
    url: str,
    *,
    allow_private_network: bool = False,
    require_https: bool = True,
) -> str:
    """Validate and normalize a model provider base URL.

    Admins may explicitly allow local development URLs, but production defaults reject
    non-HTTPS and private-network targets to avoid SSRF-style provider configuration.
    """

    value = url.strip()
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ModelCatalogSecurityError("Model base URL must include http(s) scheme and host")
    if require_https and scheme != "https":
        raise ModelCatalogSecurityError("Model base URL must use HTTPS")
    if parsed.username or parsed.password:
        raise ModelCatalogSecurityError("Model base URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ModelCatalogSecurityError("Model base URL must not include query or fragment")

    host = parsed.hostname.rstrip(".").lower()
    if not allow_private_network and _is_private_target(host):
        raise ModelCatalogSecurityError("Model base URL must not target localhost or private networks")

    return value.rstrip("/")


def _model_aad(model_id: str) -> str:
    normalized = model_id.strip()
    if not normalized:
        raise ModelCatalogSecurityError("model_id is required for model API key encryption")
    return f"model_catalog:{normalized}"


def _normalize_master_key(key: str | bytes) -> bytes:
    raw = _decode_key(key)
    if len(raw) < 32:
        raise ModelCatalogSecurityError("Model API key encryption key must be at least 32 bytes")
    if len(raw) == 32:
        return raw
    return hashlib.sha256(raw).digest()


def _decode_key(key: str | bytes) -> bytes:
    if isinstance(key, bytes):
        return key
    value = key.strip()
    if value.startswith("base64:"):
        value = value.removeprefix("base64:")
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception:
        decoded = b""
    if len(decoded) == 32:
        if not any(decoded):
            raise ModelCatalogSecurityError("MODEL_SECRET_KEY cannot use the all-zero placeholder")
        return decoded
    decoded = value.encode("utf-8")
    if decoded and not any(decoded):
        raise ModelCatalogSecurityError("MODEL_SECRET_KEY cannot use the all-zero placeholder")
    return decoded


def _is_private_target(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )
