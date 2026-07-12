"""Sandbox network profile resolution after MissionRuntime permission checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.sandbox.base import ProviderNetworkConfig
from src.sandbox.contracts import SandboxNetworkProfile, SandboxOperationRequest
from src.sandbox.exceptions import SandboxPermissionRequired, SandboxPolicyError


@dataclass(frozen=True, slots=True)
class SandboxRuntimeNetworkPolicy:
    """Select an externally enforced network attachment for one operation."""

    package_index_network_name: str | None = None
    package_index_proxy_url: str | None = None
    package_index_url: str | None = None
    package_index_hosts: tuple[str, ...] = ()

    def prepare(self, request: SandboxOperationRequest, *, now: datetime) -> ProviderNetworkConfig:
        if request.network_profile == SandboxNetworkProfile.NONE:
            return ProviderNetworkConfig()
        grant = request.network_grant
        if grant is None or now >= grant.expires_at:
            raise SandboxPermissionRequired("sandbox network permission is missing or expired")
        if request.network_profile == SandboxNetworkProfile.EXPLICIT_EGRESS_ADMIN_ONLY:
            raise SandboxPolicyError("explicit sandbox egress is not available in phase one")
        if not (self.package_index_network_name and self.package_index_proxy_url and self.package_index_url and self.package_index_hosts):
            raise SandboxPolicyError("package-index egress enforcement is not configured")
        allowed = set(self.package_index_hosts)
        if grant.allowed_hosts and not set(grant.allowed_hosts).issubset(allowed):
            raise SandboxPolicyError("network grant exceeds the package-index allowlist")
        return ProviderNetworkConfig(
            profile=request.network_profile,
            network_name=self.package_index_network_name,
            proxy_url=self.package_index_proxy_url,
            package_index_url=self.package_index_url,
            allowed_hosts=self.package_index_hosts,
        )
