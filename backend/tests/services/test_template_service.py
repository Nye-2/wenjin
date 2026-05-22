"""Tests for TemplateService."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.template_service import TemplateService

pytestmark = pytest.mark.asyncio


class FakeTemplateClient:
    def __init__(self) -> None:
        self.templates: dict[str, SimpleNamespace] = {}
        self.activate_workspace_template = AsyncMock(side_effect=self._activate)
        self.delete_workspace_template = AsyncMock(side_effect=self._delete)

    async def get_workspace_template(self, template_id: str):
        return self.templates.get(template_id)

    async def _activate(self, *, workspace_id: str, template_id: str):
        template = self.templates.get(template_id)
        if template is None or template.workspace_id != workspace_id:
            return None
        template.is_active = True
        return template

    async def _delete(self, template_id: str, *, workspace_id: str | None = None):
        template = self.templates.get(template_id)
        if template is None:
            return False
        if workspace_id is not None and template.workspace_id != workspace_id:
            return False
        self.templates.pop(template_id, None)
        return True


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def fake_client() -> FakeTemplateClient:
    return FakeTemplateClient()


@pytest.fixture
def service(fake_client) -> TemplateService:
    return TemplateService(dataservice=fake_client)


class TestActivate:
    async def test_returns_none_without_side_effect_when_template_missing(self, service, fake_client):
        result = await service.activate("tpl-missing", "ws-1")

        assert result is None
        fake_client.activate_workspace_template.assert_awaited_once_with(
            workspace_id="ws-1",
            template_id="tpl-missing",
        )

    async def test_returns_none_without_side_effect_when_workspace_mismatch(self, service, fake_client):
        fake_client.templates["tpl-1"] = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-2",
            is_active=False,
        )

        result = await service.activate("tpl-1", "ws-1")

        assert result is None
        assert fake_client.templates["tpl-1"].is_active is False

    async def test_deactivates_other_templates_and_activates_target(self, service, fake_client):
        template = SimpleNamespace(id="tpl-1", workspace_id="ws-1", is_active=False)
        fake_client.templates["tpl-1"] = template

        result = await service.activate("tpl-1", "ws-1")

        assert result is template
        assert template.is_active is True


class TestDelete:
    async def test_delete_rejects_workspace_mismatch(self, service, fake_client):
        fake_client.templates["tpl-1"] = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-2",
            source_file_path=None,
        )

        result = await service.delete("tpl-1", "ws-1")

        assert result is False
        fake_client.delete_workspace_template.assert_not_awaited()

    async def test_delete_removes_source_file_when_path_is_managed(self, service, fake_client, tmp_path: Path):
        source_file = tmp_path / "ws-1" / "templates" / "thesis.cls"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("% class")

        template = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-1",
            source_file_path=str(source_file),
        )
        fake_client.templates["tpl-1"] = template

        with patch(
            "src.services.template_service.resolve_workspace_upload_stored_path",
            return_value=source_file,
        ), patch(
            "src.services.template_service.workspace_upload_root",
            return_value=tmp_path / "ws-1",
        ):
            result = await service.delete("tpl-1", "ws-1")

        assert result is True
        assert source_file.exists() is False
        fake_client.delete_workspace_template.assert_awaited_once_with(
            "tpl-1",
            workspace_id="ws-1",
        )

    async def test_delete_keeps_success_when_source_cleanup_is_not_applicable(self, service, fake_client):
        template = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-1",
            source_file_path="/tmp/outside-path.tex",
        )
        fake_client.templates["tpl-1"] = template

        with patch(
            "src.services.template_service.resolve_workspace_upload_stored_path",
            side_effect=ValueError("outside root"),
        ):
            result = await service.delete("tpl-1", "ws-1")

        assert result is True
        fake_client.delete_workspace_template.assert_awaited_once_with(
            "tpl-1",
            workspace_id="ws-1",
        )
