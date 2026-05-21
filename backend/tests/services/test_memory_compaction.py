"""Tests for memory compaction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.database.models.knowledge import KnowledgeCategory
from src.services.memory_compaction import _parse_compact_result, compact_user_memory


class TestParseCompactResult:
    def test_valid_json(self):
        text = '{"compacted": [{"category": "preference", "content": "APA", "confidence": 0.9}], "summary": "ok"}'
        result = _parse_compact_result(text)
        assert len(result["compacted"]) == 1
        assert result["summary"] == "ok"

    def test_fenced_json(self):
        text = '```json\n{"compacted": [], "summary": "test"}\n```'
        result = _parse_compact_result(text)
        assert result["summary"] == "test"

    def test_invalid_returns_empty(self):
        result = _parse_compact_result("not json")
        assert result["compacted"] == []
        assert result["summary"] == ""


class TestCompactUserMemory:
    @pytest.mark.asyncio
    @patch("src.database.get_db_session")
    async def test_skips_when_few_entries(self, mock_session):
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=[])
            result = await compact_user_memory("user1")
            assert result["compacted_count"] == 0

    @pytest.mark.asyncio
    @patch("src.database.get_db_session")
    async def test_uses_exact_workspace_scope(self, mock_session):
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=[])

            result = await compact_user_memory("user1", workspace_context="ws-1")

        assert result["compacted_count"] == 0
        mock_svc.list_active.assert_awaited_once()
        assert mock_svc.list_active.await_args.kwargs["workspace_context"] == "ws-1"
        assert mock_svc.list_active.await_args.kwargs["include_global"] is False

    @pytest.mark.asyncio
    @patch("src.models.factory.create_chat_model")
    @patch("src.models.router.route_model", return_value="utility-primary")
    @patch("src.database.get_db_session")
    async def test_llm_failure_does_not_archive_entries(
        self,
        mock_session,
        _mock_route_model,
        mock_create_chat_model,
    ):
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_model = mock_create_chat_model.return_value
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("llm down"))

        entries = [
            SimpleNamespace(
                id=f"k-{index}",
                category=KnowledgeCategory.CONTEXT,
                content=f"entry-{index}",
                confidence=0.7,
                is_active=True,
            )
            for index in range(10)
        ]

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=entries)
            mock_svc.archive_low_confidence = AsyncMock()

            with pytest.raises(RuntimeError, match="llm down"):
                await compact_user_memory("user1")

        mock_svc.archive_low_confidence.assert_not_awaited()
        mock_db.flush.assert_not_awaited()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.models.factory.create_chat_model")
    @patch("src.models.router.route_model", return_value="utility-primary")
    @patch("src.database.get_db_session")
    async def test_empty_compaction_result_does_not_archive_entries(
        self,
        mock_session,
        _mock_route_model,
        mock_create_chat_model,
    ):
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_model = mock_create_chat_model.return_value
        mock_model.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content='{"compacted": [], "summary": ""}')
        )
        entries = [
            SimpleNamespace(
                id=f"k-{index}",
                category=KnowledgeCategory.CONTEXT,
                content=f"entry-{index}",
                confidence=0.7,
                is_active=True,
            )
            for index in range(10)
        ]

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=entries)
            mock_svc.upsert = AsyncMock()

            result = await compact_user_memory("user1")

        assert result["skipped_reason"] == "empty_compaction_result"
        assert all(entry.is_active for entry in entries)
        mock_svc.upsert.assert_not_awaited()
        mock_db.flush.assert_not_awaited()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.models.factory.create_chat_model")
    @patch("src.models.router.route_model", return_value="utility-primary")
    @patch("src.database.get_db_session")
    async def test_preserves_preferences_when_llm_omits_them(
        self,
        mock_session,
        _mock_route_model,
        mock_create_chat_model,
    ):
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_model = mock_create_chat_model.return_value
        mock_model.ainvoke = AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"compacted": [{"category": "context", '
                    '"content": "阶段性研究摘要", "confidence": 0.8}], '
                    '"summary": "用户当前研究处于调研阶段，需要继续补齐证据链。"}'
                )
            )
        )
        entries = [
            SimpleNamespace(
                id="k-pref",
                category=KnowledgeCategory.PREFERENCE,
                content="用户偏好 IEEE 引用格式",
                confidence=0.9,
                is_active=True,
            ),
            *[
                SimpleNamespace(
                    id=f"k-{index}",
                    category=KnowledgeCategory.CONTEXT,
                    content=f"entry-{index}",
                    confidence=0.7,
                    is_active=True,
                )
                for index in range(9)
            ],
        ]

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=entries)
            mock_svc.update = AsyncMock()
            mock_svc.upsert = AsyncMock()

            result = await compact_user_memory("user1")

        assert result["archived_count"] == 10
        assert mock_svc.update.await_count == 10
        persisted_contents = [call.args[2] for call in mock_svc.upsert.await_args_list]
        assert "用户偏好 IEEE 引用格式" in persisted_contents
