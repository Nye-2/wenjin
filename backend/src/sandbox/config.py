"""Sandbox vNext configuration and production security assertions."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config.app_config import root_env_file


class DockerEgressConfig(BaseModel):
    """Externally enforced package-index egress path."""

    model_config = {"extra": "forbid"}

    network_name: str | None = Field(default=None, max_length=100)
    proxy_url: str | None = Field(default=None, max_length=1000)
    package_index_url: str | None = Field(default=None, max_length=1000)
    allowed_package_hosts: tuple[str, ...] = (
        "pypi.org",
        "files.pythonhosted.org",
    )
    enforcement_attested: bool = False

    @model_validator(mode="after")
    def validate_complete_profile(self) -> DockerEgressConfig:
        configured = (self.network_name, self.proxy_url, self.package_index_url)
        if any(configured) and not all(configured):
            raise ValueError("network_name, proxy_url and package_index_url must be configured together")
        hosts = tuple(host.rstrip(".").lower() for host in self.allowed_package_hosts)
        if not hosts or any(not host or host in {"localhost", "metadata", "metadata.google.internal"} or "*" in host or _is_ip_literal(host) for host in hosts):
            raise ValueError("allowed_package_hosts must contain explicit public DNS names")
        if self.proxy_url:
            proxy = urlsplit(self.proxy_url)
            if proxy.scheme not in {"http", "https"} or not proxy.hostname:
                raise ValueError("proxy_url must be an absolute HTTP(S) URL")
            if proxy.username or proxy.password:
                raise ValueError("proxy_url may not contain credentials")
            proxy_host = proxy.hostname.rstrip(".").lower()
            if proxy_host in {"localhost", "metadata", "metadata.google.internal"} or _is_ip_literal(proxy_host):
                raise ValueError("proxy_url must name an isolated proxy container")
        if self.package_index_url:
            index = urlsplit(self.package_index_url)
            if index.scheme != "https" or not index.hostname:
                raise ValueError("package_index_url must be an absolute HTTPS URL")
            if index.hostname.rstrip(".").lower() not in hosts:
                raise ValueError("package_index_url host must be allowlisted")
        object.__setattr__(self, "allowed_package_hosts", hosts)
        return self


class DockerSandboxConfig(BaseModel):
    """Docker operation-container controls."""

    model_config = {"extra": "forbid"}

    image: str = Field(default="python:3.13-slim", min_length=1, max_length=500)
    image_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    user_uid: int = Field(default=65532, ge=1)
    user_gid: int = Field(default=65532, ge=1)
    seccomp_profile: str = Field(default="default", min_length=1, max_length=1000)
    allow_userns_remap_equivalent: bool = False
    allow_rootful_development: bool = False
    workspace_quota_attested: bool = False
    bind_mount_identity_attested: bool = False
    pull_missing_pinned_image: bool = True
    egress: DockerEgressConfig = Field(default_factory=DockerEgressConfig)

    @field_validator("seccomp_profile")
    @classmethod
    def reject_unconfined_seccomp(cls, value: str) -> str:
        if value.strip().lower() == "unconfined":
            raise ValueError("seccomp may not be unconfined")
        return value

    @property
    def image_reference(self) -> str:
        if "@sha256:" in self.image:
            return self.image
        if self.image_digest:
            return f"{self.image}@{self.image_digest}"
        return self.image


class SandboxSettings(BaseSettings):
    """Single-provider sandbox settings; local host execution is not supported."""

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=root_env_file(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    provider: Literal["docker"] = "docker"
    deployment_mode: Literal["development", "test", "production"] = "development"
    root_dir: Path = Path(".wenjin/sandbox")
    output_ref_ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    docker: DockerSandboxConfig = Field(default_factory=DockerSandboxConfig)


def get_sandbox_settings() -> SandboxSettings:
    return SandboxSettings()


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
