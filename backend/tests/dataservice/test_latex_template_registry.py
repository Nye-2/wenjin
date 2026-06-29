"""Tests for registry-backed LaTeX template bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.domains.latex import service as latex_service_module
from src.dataservice.domains.latex.service import DataServiceLatexService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, _record: Any) -> None:
        return None


class FakeLatexRepository:
    def __init__(self, templates: dict[str, SimpleNamespace] | None = None) -> None:
        self.templates = templates or {}

    async def has_templates(self) -> bool:
        return bool(self.templates)

    async def get_template(self, template_id: str) -> SimpleNamespace | None:
        return self.templates.get(template_id)

    def create_template(self, values: dict[str, Any]) -> SimpleNamespace:
        record = SimpleNamespace(**values)
        self.templates[str(values["id"])] = record
        return record

    async def list_templates(self) -> list[SimpleNamespace]:
        return [self.templates[key] for key in sorted(self.templates)]


def _service(repository: FakeLatexRepository) -> tuple[DataServiceLatexService, FakeSession]:
    session = FakeSession()
    service = DataServiceLatexService(session, autocommit=True)  # type: ignore[arg-type]
    service.repository = repository  # type: ignore[assignment]
    return service, session


def _write_registry(root: Path, *, missing_asset: bool = False, mismatched_profile: bool = False) -> Path:
    assets = root / "assets"
    software = assets / "software_copyright_cn_application_pack"
    math = assets / "math_modeling_cumcm2026_paper_pack"
    software.mkdir(parents=True)
    if not missing_asset:
        math.mkdir(parents=True)
    (software / "visual-profile.yaml").write_text(
        "id: software_copyright_cn_default\nschema: wenjin.visual_profile.v1\n",
        encoding="utf-8",
    )
    if not missing_asset:
        (math / "visual-profile.yaml").write_text(
            (
                "id: wrong_profile\nschema: wenjin.visual_profile.v1\n"
                if mismatched_profile
                else "id: math_modeling_cumcm_default\nschema: wenjin.visual_profile.v1\n"
            ),
            encoding="utf-8",
        )
    registry = root / "registry.yaml"
    registry.write_text(
        """
schema_version: latex_template_registry.v1
templates:
  - id: software_copyright_cn_application_pack
    label: 软著申报材料包
    main_file: manual.tex
    category: software_copyright
    featured: true
    template_path: software_copyright_cn_application_pack
    metadata_json:
      visual_profile:
        id: software_copyright_cn_default
  - id: math_modeling_cumcm2026_paper_pack
    label: 数模国赛论文包
    main_file: main.tex
    category: math_modeling
    featured: true
    template_path: math_modeling_cumcm2026_paper_pack
    metadata_json:
      visual_profile:
        id: math_modeling_cumcm_default
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return registry


@pytest.mark.asyncio
async def test_registry_bootstrap_upserts_authoritative_templates_even_when_old_templates_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _write_registry(tmp_path)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_REGISTRY_PATH", registry, raising=False)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_ASSET_ROOT", tmp_path / "assets", raising=False)
    repository = FakeLatexRepository(
        {
            "acl": SimpleNamespace(
                id="acl",
                label="ACL",
                main_file="main.tex",
                category="academic",
                featured=True,
                template_path="acl",
                metadata_json={},
            )
        }
    )
    service, session = _service(repository)

    await service.ensure_default_templates()

    assert "acl" in repository.templates
    assert repository.templates["software_copyright_cn_application_pack"].metadata_json["visual_profile"]["id"] == (
        "software_copyright_cn_default"
    )
    assert repository.templates["math_modeling_cumcm2026_paper_pack"].metadata_json["visual_profile"]["id"] == (
        "math_modeling_cumcm_default"
    )
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_get_template_bootstraps_registry_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _write_registry(tmp_path)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_REGISTRY_PATH", registry, raising=False)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_ASSET_ROOT", tmp_path / "assets", raising=False)
    service, session = _service(FakeLatexRepository())

    template = await service.get_template("math_modeling_cumcm2026_paper_pack")

    assert template is not None
    assert template.id == "math_modeling_cumcm2026_paper_pack"
    assert template.metadata_json["visual_profile"]["id"] == "math_modeling_cumcm_default"
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_registry_bootstrap_fails_when_asset_directory_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _write_registry(tmp_path, missing_asset=True)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_REGISTRY_PATH", registry, raising=False)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_ASSET_ROOT", tmp_path / "assets", raising=False)
    service, _session = _service(FakeLatexRepository())

    with pytest.raises(FileNotFoundError, match="math_modeling_cumcm2026_paper_pack"):
        await service.ensure_default_templates()


@pytest.mark.asyncio
async def test_registry_bootstrap_validates_visual_profile_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _write_registry(tmp_path, mismatched_profile=True)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_REGISTRY_PATH", registry, raising=False)
    monkeypatch.setattr(latex_service_module, "_LATEX_TEMPLATE_ASSET_ROOT", tmp_path / "assets", raising=False)
    service, _session = _service(FakeLatexRepository())

    with pytest.raises(ValueError, match="math_modeling_cumcm_default"):
        await service.ensure_default_templates()
