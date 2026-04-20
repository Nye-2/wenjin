"""Tests for TemplateService."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.template_service import TemplateService

pytestmark = pytest.mark.asyncio


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
def service(mock_db) -> TemplateService:
    return TemplateService(mock_db)


class TestActivate:
    async def test_returns_none_without_side_effect_when_template_missing(self, service, mock_db):
        service.get = AsyncMock(return_value=None)

        result = await service.activate("tpl-missing", "ws-1")

        assert result is None
        mock_db.execute.assert_not_awaited()
        mock_db.commit.assert_not_awaited()
        mock_db.refresh.assert_not_awaited()

    async def test_returns_none_without_side_effect_when_workspace_mismatch(self, service, mock_db):
        service.get = AsyncMock(
            return_value=SimpleNamespace(id="tpl-1", workspace_id="ws-2", is_active=False)
        )

        result = await service.activate("tpl-1", "ws-1")

        assert result is None
        mock_db.execute.assert_not_awaited()
        mock_db.commit.assert_not_awaited()
        mock_db.refresh.assert_not_awaited()

    async def test_deactivates_other_templates_and_activates_target(self, service, mock_db):
        template = SimpleNamespace(id="tpl-1", workspace_id="ws-1", is_active=False)
        service.get = AsyncMock(return_value=template)

        result = await service.activate("tpl-1", "ws-1")

        assert result is template
        assert template.is_active is True
        mock_db.execute.assert_awaited_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(template)


class TestDelete:
    async def test_delete_rejects_workspace_mismatch(self, service, mock_db):
        service.get = AsyncMock(
            return_value=SimpleNamespace(
                id="tpl-1",
                workspace_id="ws-2",
                source_file_path=None,
            )
        )

        result = await service.delete("tpl-1", "ws-1")

        assert result is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()

    async def test_delete_removes_source_file_when_path_is_managed(self, service, mock_db, tmp_path: Path):
        source_file = tmp_path / "ws-1" / "templates" / "thesis.cls"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("% class")

        template = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-1",
            source_file_path=str(source_file),
        )
        service.get = AsyncMock(return_value=template)

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
        mock_db.delete.assert_awaited_once_with(template)
        mock_db.commit.assert_awaited_once()

    async def test_delete_keeps_success_when_source_cleanup_is_not_applicable(self, service, mock_db):
        template = SimpleNamespace(
            id="tpl-1",
            workspace_id="ws-1",
            source_file_path="/tmp/outside-path.tex",
        )
        service.get = AsyncMock(return_value=template)

        with patch(
            "src.services.template_service.resolve_workspace_upload_stored_path",
            side_effect=ValueError("outside root"),
        ):
            result = await service.delete("tpl-1", "ws-1")

        assert result is True
        mock_db.delete.assert_awaited_once_with(template)
        mock_db.commit.assert_awaited_once()
