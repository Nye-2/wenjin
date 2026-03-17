"""Tests for memory compaction."""

from unittest.mock import AsyncMock, patch

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
    @patch("src.database.get_db_session")
    async def test_skips_when_few_entries(self, mock_session):
        mock_db = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session.return_value.__aexit__ = AsyncMock()

        with patch("src.services.knowledge_service.KnowledgeService") as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_active = AsyncMock(return_value=[])
            result = await compact_user_memory("user1")
            assert result["compacted_count"] == 0
