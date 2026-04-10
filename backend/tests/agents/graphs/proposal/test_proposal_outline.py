"""Tests for proposal_outline sub-graph helper functions."""

import pytest

from src.agents.graphs._shared import (
    _normalize_list,
    _normalize_text,
    _read_optional_int,
    _read_optional_str,
)


class TestReadOptionalStr:
    def test_none_value(self):
        assert _read_optional_str(None) is None

    def test_empty_string(self):
        assert _read_optional_str("") is None

    def test_whitespace_only(self):
        assert _read_optional_str("   ") is None

    def test_valid_string(self):
        assert _read_optional_str("  hello  ") == "hello"

    def test_numeric_value(self):
        assert _read_optional_str(123) == "123"


class TestReadOptionalInt:
    def test_none_value(self):
        assert _read_optional_int(None) is None

    def test_valid_int(self):
        assert _read_optional_int(42) == 42

    def test_string_int(self):
        assert _read_optional_int("24") == 24

    def test_invalid_string(self):
        assert _read_optional_int("invalid") is None

    def test_float_value(self):
        assert _read_optional_int(3.14) == 3


class TestNormalizeList:
    def test_none_value(self):
        assert _normalize_list(None) == []

    def test_empty_string(self):
        assert _normalize_list("") == []

    def test_comma_separated_string(self):
        result = _normalize_list("a, b, c")
        assert result == ["a", "b", "c"]

    def test_list_input(self):
        result = _normalize_list(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_max_items_limit(self):
        result = _normalize_list("1,2,3,4,5,6,7,8,9,10,11,12", max_items=5)
        assert len(result) == 5

    def test_whitespace_handling(self):
        result = _normalize_list("  a  ,  b  ,  c  ")
        assert result == ["a", "b", "c"]


class TestNormalizeText:
    def test_none_value(self):
        assert _normalize_text(None) == ""

    def test_none_with_fallback(self):
        assert _normalize_text(None, fallback="default") == "default"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_empty_with_fallback(self):
        assert _normalize_text("", fallback="default") == "default"

    def test_valid_string(self):
        assert _normalize_text("  hello  ") == "hello"

    def test_numeric_value(self):
        assert _normalize_text(123) == "123"


class TestProposalOutlineGraph:
    @pytest.mark.asyncio
    async def test_basic_execution(self, monkeypatch: pytest.MonkeyPatch):
        """Test basic graph execution with minimal payload."""
        from src.agents.graphs.proposal.proposal_outline import proposal_outline_graph
        from src.workspace_features.latex_sync import LatexSyncResult

        async def _fake_build_proposal_outline_payload(**kwargs):
            _ = kwargs
            return {
                "topic": "人工智能研究",
                "proposal_type": "national_natural_science",
                "proposal_type_label": "国家自然科学基金",
                "period_months": 36,
                "sections": [],
                "milestones": [],
                "risks": [],
                "generation_mode": "llm",
                "model_id": "mock-model",
                "generation_error": None,
                "generated_at": "2026-03-20T00:00:00+00:00",
            }

        async def _fake_sync_proposal_outline_payload(**kwargs):
            _ = kwargs
            return LatexSyncResult(
                latex_project_id="latex-proj-1",
                main_file="main.tex",
                section_map={"basis": "sections/01_basis.tex"},
                sync_conflicts=[{"logical_key": "basis", "path": "sections/01_basis.tex", "reason": "user_modified"}],
            )

        monkeypatch.setattr(
            "src.agents.graphs.proposal.proposal_outline.build_proposal_outline_payload",
            _fake_build_proposal_outline_payload,
        )
        monkeypatch.setattr(
            "src.agents.graphs.proposal.proposal_outline.sync_proposal_outline_payload",
            _fake_sync_proposal_outline_payload,
        )

        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "proposal",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "Test Proposal",
            "params": {
                "topic": "人工智能研究",
                "proposal_type": "national_natural_science",
            },
        }

        result = await proposal_outline_graph(initial_state, payload)

        assert "topic" in result
        assert "proposal_type" in result
        assert "sections" in result
        assert result["topic"] == "人工智能研究"
        assert result["proposal_type"] == "national_natural_science"
        assert result["latex_project_id"] == "latex-proj-1"
        assert result["main_file"] == "main.tex"
        assert result["section_map"] == {"basis": "sections/01_basis.tex"}
        assert result["sync_conflicts"] == [{"logical_key": "basis", "path": "sections/01_basis.tex", "reason": "user_modified"}]

    @pytest.mark.asyncio
    async def test_fallback_to_workspace_name(self, monkeypatch: pytest.MonkeyPatch):
        """Test that topic falls back to workspace name."""
        from src.agents.graphs.proposal.proposal_outline import proposal_outline_graph
        from src.workspace_features.latex_sync import LatexSyncResult

        async def _fake_build_proposal_outline_payload(**kwargs):
            return {
                "topic": kwargs["topic"],
                "proposal_type": kwargs["proposal_type"],
                "proposal_type_label": "科研项目",
                "period_months": 24,
                "sections": [],
                "milestones": [],
                "risks": [],
                "generation_mode": "llm",
                "model_id": "mock-model",
                "generation_error": None,
                "generated_at": "2026-03-20T00:00:00+00:00",
            }

        async def _fake_sync_proposal_outline_payload(**kwargs):
            _ = kwargs
            return LatexSyncResult()

        monkeypatch.setattr(
            "src.agents.graphs.proposal.proposal_outline.build_proposal_outline_payload",
            _fake_build_proposal_outline_payload,
        )
        monkeypatch.setattr(
            "src.agents.graphs.proposal.proposal_outline.sync_proposal_outline_payload",
            _fake_sync_proposal_outline_payload,
        )

        initial_state = {
            "messages": [],
            "workspace_id": "test-workspace",
            "workspace_type": "proposal",
        }
        payload = {
            "workspace_id": "test-workspace",
            "workspace_name": "Deep Learning Research",
            "params": {},
        }

        result = await proposal_outline_graph(initial_state, payload)

        assert "topic" in result
        assert result["topic"] == "Deep Learning Research"
