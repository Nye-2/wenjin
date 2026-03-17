"""Tests for thesis writing enhancement sub-graph."""

from __future__ import annotations

import pytest

from src.agents.graphs.thesis.thesis_writing import (
    _build_review_fallback,
    _parse_json_response,
    _validate_review_result,
)


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------
class TestParseJsonResponse:
    def test_valid_json(self):
        result = _parse_json_response('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_fenced_json(self):
        text = '```json\n{"overall_score": 8.0}\n```'
        result = _parse_json_response(text)
        assert result == {"overall_score": 8.0}

    def test_fenced_no_lang(self):
        text = '```\n{"a": 1}\n```'
        result = _parse_json_response(text)
        assert result == {"a": 1}

    def test_invalid_json(self):
        assert _parse_json_response("not json at all") is None

    def test_json_list_returns_none(self):
        assert _parse_json_response('[1, 2, 3]') is None

    def test_empty_string(self):
        assert _parse_json_response("") is None

    def test_whitespace_padding(self):
        result = _parse_json_response('  \n {"ok": true} \n  ')
        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# _build_review_fallback
# ---------------------------------------------------------------------------
class TestBuildReviewFallback:
    def test_returns_correct_structure(self):
        result = _build_review_fallback("Introduction")
        assert result["overall_score"] == 0
        assert result["issues"] == []
        assert result["strengths"] == []
        assert result["revision_needed"] is False
        assert result["revision_instructions"] is None

    def test_all_keys_present(self):
        result = _build_review_fallback("任意标题")
        expected_keys = {"overall_score", "issues", "strengths", "revision_needed", "revision_instructions"}
        assert set(result.keys()) == expected_keys

    def test_passes_validation(self):
        result = _build_review_fallback("Test Section")
        assert _validate_review_result(result) is True


# ---------------------------------------------------------------------------
# _validate_review_result
# ---------------------------------------------------------------------------
class TestValidateReviewResult:
    def test_valid_full_review(self):
        review = {
            "overall_score": 7.5,
            "issues": [
                {"type": "logic", "severity": "medium", "description": "desc", "suggestion": "fix"}
            ],
            "strengths": ["Good structure"],
            "revision_needed": True,
            "revision_instructions": "Please fix logic flow",
        }
        assert _validate_review_result(review) is True

    def test_valid_minimal_review(self):
        review = {
            "overall_score": 9,
            "issues": [],
            "strengths": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is True

    def test_missing_overall_score(self):
        review = {
            "issues": [],
            "strengths": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_missing_issues(self):
        review = {
            "overall_score": 5.0,
            "strengths": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_missing_strengths(self):
        review = {
            "overall_score": 5.0,
            "issues": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_missing_revision_needed(self):
        review = {
            "overall_score": 5.0,
            "issues": [],
            "strengths": [],
        }
        assert _validate_review_result(review) is False

    def test_invalid_score_type_string(self):
        review = {
            "overall_score": "high",
            "issues": [],
            "strengths": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_invalid_issues_type(self):
        review = {
            "overall_score": 5.0,
            "issues": "none",
            "strengths": [],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_invalid_strengths_type(self):
        review = {
            "overall_score": 5.0,
            "issues": [],
            "strengths": "good",
            "revision_needed": False,
        }
        assert _validate_review_result(review) is False

    def test_invalid_revision_needed_type(self):
        review = {
            "overall_score": 5.0,
            "issues": [],
            "strengths": [],
            "revision_needed": "yes",
        }
        assert _validate_review_result(review) is False

    def test_integer_score_valid(self):
        review = {
            "overall_score": 8,
            "issues": [],
            "strengths": ["Well written"],
            "revision_needed": False,
        }
        assert _validate_review_result(review) is True

    def test_empty_dict(self):
        assert _validate_review_result({}) is False


# ---------------------------------------------------------------------------
# Action routing logic
# ---------------------------------------------------------------------------
class TestActionRouting:
    """Verify correct mode selection based on action parameter."""

    def test_review_action_detected(self):
        params = {"action": "review_section", "section_title": "Ch1", "section_content": "text"}
        action = str(params.get("action", "")).strip()
        assert action == "review_section"

    def test_revise_action_detected(self):
        params = {"action": "revise_section", "section_title": "Ch1", "section_content": "text"}
        action = str(params.get("action", "")).strip()
        assert action == "revise_section"

    def test_default_action_empty_string(self):
        params = {"section_title": "Ch1", "section_content": "text"}
        action = str(params.get("action", "")).strip()
        assert action == ""
        assert action != "review_section"
        assert action != "revise_section"

    def test_default_action_missing_key(self):
        params = {"section_title": "Ch1"}
        action = str(params.get("action", "")).strip()
        assert action == ""

    def test_whitespace_action_treated_as_default(self):
        params = {"action": "  ", "section_title": "Ch1"}
        action = str(params.get("action", "")).strip()
        assert action == ""
        assert action != "review_section"
        assert action != "revise_section"

    def test_unknown_action_treated_as_default(self):
        params = {"action": "unknown_action", "section_title": "Ch1"}
        action = str(params.get("action", "")).strip()
        assert action != "review_section"
        assert action != "revise_section"


# ---------------------------------------------------------------------------
# Integration-style tests (async, mocked LLM)
# ---------------------------------------------------------------------------
class TestHandleReviewSection:
    """Test _handle_review_section with mocked LLM."""

    @pytest.mark.asyncio
    async def test_fallback_when_no_llm(self, monkeypatch):
        """When LLM import fails, should return template_fallback."""
        from src.agents.graphs.thesis import thesis_writing

        async def _mock_review(*args, **kwargs):
            return None

        monkeypatch.setattr(thesis_writing, "_review_section", _mock_review)

        result = await thesis_writing._handle_review_section(
            params={"section_title": "Introduction", "section_content": "Some text"},
            memory_context=None,
        )

        assert result["action"] == "review_section"
        assert result["generation_mode"] == "template_fallback"
        assert result["review"]["overall_score"] == 0
        assert result["review"]["revision_needed"] is False
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_llm_success(self, monkeypatch):
        """When LLM returns valid review, should return llm mode."""
        from src.agents.graphs.thesis import thesis_writing

        mock_review = {
            "overall_score": 8.0,
            "issues": [],
            "strengths": ["Well structured"],
            "revision_needed": False,
            "revision_instructions": None,
        }

        async def _mock_review_fn(*args, **kwargs):
            return mock_review

        monkeypatch.setattr(thesis_writing, "_review_section", _mock_review_fn)

        result = await thesis_writing._handle_review_section(
            params={"section_title": "Methods", "section_content": "Content"},
            memory_context=None,
        )

        assert result["action"] == "review_section"
        assert result["generation_mode"] == "llm"
        assert result["review"]["overall_score"] == 8.0


class TestHandleReviseSection:
    """Test _handle_revise_section with mocked LLM."""

    @pytest.mark.asyncio
    async def test_fallback_when_no_llm(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        async def _mock_revise(*args, **kwargs):
            return None

        monkeypatch.setattr(thesis_writing, "_revise_section", _mock_revise)

        result = await thesis_writing._handle_revise_section(
            params={
                "section_title": "Ch1",
                "section_content": "original text",
                "revision_instructions": "fix logic",
                "revision_round": 1,
            },
            memory_context=None,
        )

        assert result["action"] == "revise_section"
        assert result["generation_mode"] == "template_fallback"
        assert result["revised_content"] == "original text"
        assert result["revision_round"] == 1

    @pytest.mark.asyncio
    async def test_llm_success(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        async def _mock_revise(*args, **kwargs):
            return {"revised_content": "improved text", "changes_summary": "fixed logic"}

        monkeypatch.setattr(thesis_writing, "_revise_section", _mock_revise)

        result = await thesis_writing._handle_revise_section(
            params={
                "section_title": "Ch1",
                "section_content": "original",
                "revision_instructions": "fix logic",
                "revision_round": 1,
            },
            memory_context=None,
        )

        assert result["action"] == "revise_section"
        assert result["generation_mode"] == "llm"
        assert result["revised_content"] == "improved text"
        assert result["changes_summary"] == "fixed logic"

    @pytest.mark.asyncio
    async def test_revision_round_clamped(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        async def _mock_revise(*args, **kwargs):
            return {"revised_content": "text", "changes_summary": "ok"}

        monkeypatch.setattr(thesis_writing, "_revise_section", _mock_revise)

        result = await thesis_writing._handle_revise_section(
            params={
                "section_title": "Ch1",
                "section_content": "original",
                "revision_instructions": "fix",
                "revision_round": 5,
            },
            memory_context=None,
        )

        assert result["revision_round"] == 2  # clamped to _MAX_REVISION_ROUNDS


class TestHandleReviewAndRevise:
    """Test the full review-and-revise loop."""

    @pytest.mark.asyncio
    async def test_no_revision_needed(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        review_no_revision = {
            "overall_score": 9.0,
            "issues": [],
            "strengths": ["Excellent"],
            "revision_needed": False,
            "revision_instructions": None,
        }

        async def _mock_review(*args, **kwargs):
            return review_no_revision

        monkeypatch.setattr(thesis_writing, "_review_section", _mock_review)

        result = await thesis_writing._handle_review_and_revise(
            params={"section_title": "Ch1", "section_content": "good text"},
            memory_context=None,
        )

        assert result["action"] == "review_and_revise"
        assert result["total_rounds"] == 1
        assert result["final_content"] == "good text"
        assert result["original_content"] == "good text"
        assert result["generation_mode"] == "llm"
        assert result["rounds"][0]["revised_content"] is None

    @pytest.mark.asyncio
    async def test_one_revision_then_pass(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        call_count = {"review": 0}

        async def _mock_review(*args, **kwargs):
            call_count["review"] += 1
            if call_count["review"] == 1:
                return {
                    "overall_score": 5.0,
                    "issues": [{"type": "logic", "severity": "high", "description": "bad", "suggestion": "fix"}],
                    "strengths": [],
                    "revision_needed": True,
                    "revision_instructions": "Fix logic flow",
                }
            return {
                "overall_score": 8.5,
                "issues": [],
                "strengths": ["Improved"],
                "revision_needed": False,
                "revision_instructions": None,
            }

        async def _mock_revise(*args, **kwargs):
            return {"revised_content": "improved text", "changes_summary": "fixed logic"}

        monkeypatch.setattr(thesis_writing, "_review_section", _mock_review)
        monkeypatch.setattr(thesis_writing, "_revise_section", _mock_revise)

        result = await thesis_writing._handle_review_and_revise(
            params={"section_title": "Ch1", "section_content": "original"},
            memory_context=None,
        )

        assert result["action"] == "review_and_revise"
        assert result["total_rounds"] == 2
        assert result["original_content"] == "original"
        assert result["final_content"] == "improved text"
        assert result["rounds"][0]["revised_content"] == "improved text"
        assert result["rounds"][1]["revised_content"] is None  # no revision in round 2

    @pytest.mark.asyncio
    async def test_all_fallback(self, monkeypatch):
        from src.agents.graphs.thesis import thesis_writing

        async def _mock_review(*args, **kwargs):
            return None

        monkeypatch.setattr(thesis_writing, "_review_section", _mock_review)

        result = await thesis_writing._handle_review_and_revise(
            params={"section_title": "Ch1", "section_content": "text"},
            memory_context=None,
        )

        assert result["generation_mode"] == "template_fallback"
        assert result["total_rounds"] == 1
        # Fallback review has revision_needed=False, so loop ends after 1 round
