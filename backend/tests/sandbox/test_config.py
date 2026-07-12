from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.sandbox.config import DockerEgressConfig, DockerSandboxConfig, SandboxSettings


def test_sandbox_settings_expose_only_docker_provider(tmp_path) -> None:
    settings = SandboxSettings(provider="docker", root_dir=tmp_path)

    assert settings.provider == "docker"
    assert settings.root_dir == tmp_path

    with pytest.raises(ValidationError):
        SandboxSettings(provider="local", root_dir=tmp_path)


def test_docker_image_reference_is_digest_pinned_when_digest_is_configured() -> None:
    digest = f"sha256:{'a' * 64}"
    config = DockerSandboxConfig(image="registry.example/sandbox:2", image_digest=digest)

    assert config.image_reference == f"registry.example/sandbox:2@{digest}"


def test_unconfined_seccomp_is_invalid() -> None:
    with pytest.raises(ValidationError, match="unconfined"):
        DockerSandboxConfig(seccomp_profile="unconfined")


def test_egress_configuration_must_be_complete() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        DockerEgressConfig(network_name="network-only")


def test_package_index_must_be_https_and_allowlisted() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        DockerEgressConfig(
            network_name="egress",
            proxy_url="http://proxy:3128",
            package_index_url="http://pypi.org/simple",
        )
    with pytest.raises(ValidationError, match="allowlisted"):
        DockerEgressConfig(
            network_name="egress",
            proxy_url="http://proxy:3128",
            package_index_url="https://packages.example.org/simple",
        )


def test_package_allowlist_rejects_ip_literals_and_proxy_credentials() -> None:
    with pytest.raises(ValidationError, match="public DNS"):
        DockerEgressConfig(allowed_package_hosts=("169.254.169.254",))
    with pytest.raises(ValidationError, match="credentials"):
        DockerEgressConfig(
            network_name="egress",
            proxy_url="http://user:pass@proxy:3128",
            package_index_url="https://pypi.org/simple",
        )
    with pytest.raises(ValidationError, match="isolated proxy container"):
        DockerEgressConfig(
            network_name="egress",
            proxy_url="http://127.0.0.1:3128",
            package_index_url="https://pypi.org/simple",
        )


def test_container_identity_cannot_be_root() -> None:
    with pytest.raises(ValidationError):
        DockerSandboxConfig(user_uid=0)
    with pytest.raises(ValidationError):
        DockerSandboxConfig(user_gid=0)
