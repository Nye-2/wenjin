"""Tests for TaskBrief and TaskReport Pydantic contracts."""

import pytest
from pydantic import ValidationError

from src.agents.contracts import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    ResultError,
    TaskBrief,
    TaskData,
    TaskOutput,
    TaskReport,
)

# ---------------------------------------------------------------------------
# TaskBrief tests
# ---------------------------------------------------------------------------


class TestTaskBrief:
    def test_valid_minimal(self):
        brief = TaskBrief(
            capability_id="scholar_search",
            raw_message="Search for papers on transformers",
            workspace_id="ws-001",
        )
        assert brief.capability_id == "scholar_search"
        assert brief.raw_message == "Search for papers on transformers"
        assert brief.workspace_id == "ws-001"
        assert brief.user_id == ""
        assert brief.brief == {}
        assert brief.decisions == {}

    def test_capability_id_non_empty(self):
        with pytest.raises(ValidationError):
            TaskBrief(
                capability_id="",
                raw_message="Some message",
                workspace_id="ws-001",
            )

    def test_raw_message_non_empty(self):
        with pytest.raises(ValidationError):
            TaskBrief(
                capability_id="scholar_search",
                raw_message="",
                workspace_id="ws-001",
            )

    def test_with_brief_and_decisions(self):
        brief = TaskBrief(
            capability_id="outline",
            brief={"topic": "LLM alignment", "depth": 3},
            raw_message="Create an outline",
            decisions={"style": "academic", "language": "en"},
            workspace_id="ws-999",
        )
        assert brief.brief["topic"] == "LLM alignment"
        assert brief.decisions["style"] == "academic"

    def test_workspace_id_defaults_to_empty_string(self):
        brief = TaskBrief(
            capability_id="cap",
            raw_message="msg",
        )
        assert brief.workspace_id == ""

    def test_decisions_default_empty_dict(self):
        brief = TaskBrief(capability_id="cap", raw_message="msg")
        assert brief.decisions == {}

    def test_serialisation_round_trip(self):
        brief = TaskBrief(
            capability_id="cap",
            raw_message="msg",
            user_id="user-1",
            decisions={"k": "v"},
        )
        restored = TaskBrief.model_validate(brief.model_dump())
        assert restored == brief


# ---------------------------------------------------------------------------
# TaskReport tests
# ---------------------------------------------------------------------------


class TestTaskReport:
    def _make_report(self, **kwargs):
        defaults = dict(
            execution_id="exec-abc",
            capability_id="scholar_search",
            status="completed",
            duration_seconds=42,
            narrative="Found 3 papers.",
        )
        defaults.update(kwargs)
        return TaskReport(**defaults)

    def test_valid_minimal(self):
        report = self._make_report()
        assert report.execution_id == "exec-abc"
        assert report.status == "completed"
        assert report.outputs == []
        assert report.errors == []
        assert report.token_usage is None

    def test_status_enum_completed(self):
        report = self._make_report(status="completed")
        assert report.status == "completed"

    def test_status_enum_failed_partial(self):
        report = self._make_report(status="failed_partial")
        assert report.status == "failed_partial"

    def test_status_enum_cancelled(self):
        report = self._make_report(status="cancelled")
        assert report.status == "cancelled"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            self._make_report(status="unknown_status")

    def test_library_item_output(self):
        output = LibraryItemOutput(
            id="out-1",
            preview="Attention Is All You Need",
            kind="library_item",
            data=LibraryItemData(
                title="Attention Is All You Need",
                authors=["Vaswani", "Shazeer"],
                year=2017,
                doi="10.1234/example",
            ),
        )
        report = self._make_report(outputs=[output])
        assert len(report.outputs) == 1
        item = report.outputs[0]
        assert item.kind == "library_item"
        assert item.data.title == "Attention Is All You Need"
        assert item.data.year == 2017

    def test_document_output(self):
        output = DocumentOutput(
            id="out-2",
            preview="thesis_draft.pdf",
            kind="document",
            data=DocumentData(
                name="thesis_draft.pdf",
                mime_type="application/pdf",
                storage_path="/docs/thesis_draft.pdf",
                size_bytes=204800,
                doc_kind="thesis",
            ),
        )
        report = self._make_report(outputs=[output])
        assert report.outputs[0].kind == "document"
        assert report.outputs[0].data.name == "thesis_draft.pdf"

    def test_memory_fact_output(self):
        output = MemoryFactOutput(
            id="out-3",
            preview="User prefers LaTeX",
            kind="memory_fact",
            data=MemoryFactData(content="User prefers LaTeX", category="preference", confidence=0.9),
        )
        report = self._make_report(outputs=[output])
        assert report.outputs[0].kind == "memory_fact"
        assert report.outputs[0].data.confidence == 0.9

    def test_decision_output(self):
        output = DecisionOutput(
            id="out-4",
            preview="style=IEEE",
            kind="decision",
            data=DecisionData(key="style", value="IEEE", confidence=1.0),
        )
        report = self._make_report(outputs=[output])
        assert report.outputs[0].kind == "decision"
        assert report.outputs[0].data.key == "style"

    def test_task_output(self):
        output = TaskOutput(
            id="out-5",
            preview="Review related work",
            kind="task",
            data=TaskData(title="Review related work", description="Summarise prior art", priority=1),
        )
        report = self._make_report(outputs=[output])
        assert report.outputs[0].kind == "task"
        assert report.outputs[0].data.title == "Review related work"

    def test_mixed_outputs(self):
        outputs = [
            LibraryItemOutput(
                id="o1",
                preview="Paper A",
                kind="library_item",
                data=LibraryItemData(title="Paper A", authors=["Smith"]),
            ),
            DecisionOutput(
                id="o2",
                preview="style=APA",
                kind="decision",
                data=DecisionData(key="style", value="APA"),
            ),
        ]
        report = self._make_report(outputs=outputs)
        assert len(report.outputs) == 2
        assert report.outputs[0].kind == "library_item"
        assert report.outputs[1].kind == "decision"

    def test_wrong_kind_data_shape_raises(self):
        """Wrong data shape for a given kind must raise ValidationError."""
        with pytest.raises((ValidationError, TypeError)):
            LibraryItemOutput(
                id="bad",
                preview="bad",
                kind="library_item",
                data=DecisionData(key="k", value="v"),  # wrong data type
            )

    def test_errors_field(self):
        errors = [
            ResultError(phase="search", task="scholar_search", error="timeout"),
        ]
        report = self._make_report(errors=errors)
        assert len(report.errors) == 1
        assert report.errors[0].phase == "search"
        assert report.errors[0].error == "timeout"

    def test_token_usage_and_cost(self):
        report = self._make_report(
            token_usage={"input": 1000, "output": 500, "total": 1500},
            cost_estimate="$0.012",
        )
        assert report.token_usage["total"] == 1500
        assert report.cost_estimate == "$0.012"

    def test_serialisation_round_trip(self):
        output = LibraryItemOutput(
            id="o1",
            preview="Paper X",
            kind="library_item",
            data=LibraryItemData(title="Paper X", authors=["Doe"]),
        )
        report = self._make_report(outputs=[output])
        restored = TaskReport.model_validate(report.model_dump())
        assert restored.outputs[0].kind == "library_item"
        assert restored.outputs[0].data.title == "Paper X"
