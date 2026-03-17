"""Tests for artifact versioning in ArtifactService.

This module tests the version-aware artifact creation including:
- Auto-increment version when same workspace+type+title exists
- Parent artifact linking for version chains
- Explicit parent_artifact_id override
- Version history listing
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.academic.services.artifact_service import ArtifactService


def _make_mock_artifact(
    id: str = "artifact-1",
    workspace_id: str = "ws-1",
    type: str = "research_idea",
    title: str = "My Research",
    version: int = 1,
    parent_artifact_id: str | None = None,
    status: str = "draft",
    content: dict | None = None,
):
    """Create a mock Artifact with the given attributes."""
    artifact = MagicMock()
    artifact.id = id
    artifact.workspace_id = workspace_id
    artifact.type = type
    artifact.title = title
    artifact.version = version
    artifact.parent_artifact_id = parent_artifact_id
    artifact.status = status
    artifact.content = content or {"body": "test"}
    return artifact


def _make_db_session():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


class TestCreateFirstVersion:
    """Tests for creating the first version of an artifact."""

    @pytest.mark.asyncio
    async def test_create_first_version(self):
        """Creating artifact with no existing versions gives version=1, no auto parent."""
        db = _make_db_session()

        service = ArtifactService(db)

        with patch.object(service, "_find_latest_version", new_callable=AsyncMock) as mock_find, \
             patch("src.academic.services.artifact_service.Artifact") as MockArtifact, \
             patch("src.academic.services.artifact_service.ArtifactType") as MockType:
            mock_find.return_value = None
            mock_instance = MagicMock()
            MockArtifact.return_value = mock_instance
            MockType.side_effect = lambda v: v

            result = await service.create(
                workspace_id="ws-1",
                type="research_idea",
                content={"body": "test"},
                title="My Research",
            )

            # _find_latest_version was called with the right args
            mock_find.assert_awaited_once_with("ws-1", "research_idea", "My Research")

            # Verify Artifact was created with version=1, no parent
            MockArtifact.assert_called_once()
            call_kwargs = MockArtifact.call_args[1]
            assert call_kwargs["version"] == 1
            assert call_kwargs["parent_artifact_id"] is None
            assert call_kwargs["title"] == "My Research"
            assert call_kwargs["status"] == "draft"


class TestCreateAutoIncrementsVersion:
    """Tests for auto-incrementing version on duplicate workspace+type+title."""

    @pytest.mark.asyncio
    async def test_create_auto_increments_version(self):
        """Creating with same workspace+type+title gives version=N+1, parent set."""
        db = _make_db_session()

        existing = _make_mock_artifact(
            id="existing-v3",
            version=3,
        )

        service = ArtifactService(db)

        with patch.object(service, "_find_latest_version", new_callable=AsyncMock) as mock_find, \
             patch("src.academic.services.artifact_service.Artifact") as MockArtifact, \
             patch("src.academic.services.artifact_service.ArtifactType") as MockType:
            mock_find.return_value = existing
            mock_instance = MagicMock()
            MockArtifact.return_value = mock_instance
            MockType.side_effect = lambda v: v

            result = await service.create(
                workspace_id="ws-1",
                type="research_idea",
                content={"body": "test v4"},
                title="My Research",
            )

            mock_find.assert_awaited_once_with("ws-1", "research_idea", "My Research")

            MockArtifact.assert_called_once()
            call_kwargs = MockArtifact.call_args[1]
            assert call_kwargs["version"] == 4
            assert call_kwargs["parent_artifact_id"] == "existing-v3"


class TestCreateRespectsExplicitParent:
    """Tests for explicit parent_artifact_id override."""

    @pytest.mark.asyncio
    async def test_create_respects_explicit_parent(self):
        """If caller passes parent_artifact_id, use it instead of auto."""
        db = _make_db_session()

        existing = _make_mock_artifact(id="existing-v1", version=1)

        service = ArtifactService(db)

        with patch.object(service, "_find_latest_version", new_callable=AsyncMock) as mock_find, \
             patch("src.academic.services.artifact_service.Artifact") as MockArtifact, \
             patch("src.academic.services.artifact_service.ArtifactType") as MockType:
            mock_find.return_value = existing
            mock_instance = MagicMock()
            MockArtifact.return_value = mock_instance
            MockType.side_effect = lambda v: v

            result = await service.create(
                workspace_id="ws-1",
                type="research_idea",
                content={"body": "test"},
                title="My Research",
                parent_artifact_id="explicit-parent-id",
            )

            call_kwargs = MockArtifact.call_args[1]
            # Explicit parent takes precedence over auto-linked parent
            assert call_kwargs["parent_artifact_id"] == "explicit-parent-id"
            # Version still increments based on existing
            assert call_kwargs["version"] == 2


class TestCreateNoVersioningWithoutTitle:
    """Tests for skipping versioning when title is None."""

    @pytest.mark.asyncio
    async def test_create_no_versioning_without_title(self):
        """If title is None, version stays 1 (no lookup)."""
        db = _make_db_session()

        service = ArtifactService(db)

        with patch.object(service, "_find_latest_version", new_callable=AsyncMock) as mock_find, \
             patch("src.academic.services.artifact_service.Artifact") as MockArtifact, \
             patch("src.academic.services.artifact_service.ArtifactType") as MockType:
            mock_instance = MagicMock()
            MockArtifact.return_value = mock_instance
            MockType.side_effect = lambda v: v

            result = await service.create(
                workspace_id="ws-1",
                type="research_idea",
                content={"body": "untitled artifact"},
                title=None,
            )

            call_kwargs = MockArtifact.call_args[1]
            assert call_kwargs["version"] == 1
            assert call_kwargs["parent_artifact_id"] is None
            assert call_kwargs["title"] is None

            # _find_latest_version should NOT have been called (title is None)
            mock_find.assert_not_awaited()


class TestFindLatestVersion:
    """Tests for _find_latest_version private method."""

    @pytest.mark.asyncio
    async def test_find_latest_version_none(self):
        """No matching artifact returns None."""
        db = _make_db_session()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        service = ArtifactService(db)
        result = await service._find_latest_version("ws-1", "research_idea", "Nonexistent")

        assert result is None
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_latest_version_found(self):
        """Matching artifact returns it."""
        db = _make_db_session()

        existing = _make_mock_artifact(id="found-1", version=5)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        service = ArtifactService(db)
        result = await service._find_latest_version("ws-1", "research_idea", "My Research")

        assert result is not None
        assert result.id == "found-1"
        assert result.version == 5
        db.execute.assert_called_once()


class TestListVersions:
    """Tests for list_versions method."""

    @pytest.mark.asyncio
    async def test_list_versions_empty(self):
        """No versions returns empty list."""
        db = _make_db_session()

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        db.execute.return_value = mock_result

        service = ArtifactService(db)
        result = await service.list_versions("ws-1", "research_idea", "Nonexistent")

        assert result == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_versions_ordered(self):
        """Multiple versions returned newest first."""
        db = _make_db_session()

        v3 = _make_mock_artifact(id="v3", version=3)
        v2 = _make_mock_artifact(id="v2", version=2)
        v1 = _make_mock_artifact(id="v1", version=1)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [v3, v2, v1]
        mock_result.scalars.return_value = mock_scalars
        db.execute.return_value = mock_result

        service = ArtifactService(db)
        result = await service.list_versions("ws-1", "research_idea", "My Research")

        assert len(result) == 3
        assert result[0].version == 3
        assert result[1].version == 2
        assert result[2].version == 1
        db.execute.assert_called_once()
